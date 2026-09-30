"""Groq client for strict-JSON calls, with transient-error retries and usage accounting."""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

import groq
import yaml
from pydantic import BaseModel, Field, ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from winback.rules_engine import Strict
from winback.settings import CONFIG_DIR

DEFAULT_MODELS_PATH = CONFIG_DIR / "models.yaml"
TRANSIENT_ERRORS = (groq.RateLimitError, groq.APIConnectionError, groq.InternalServerError)


class RoleConfig(Strict):
    model: str
    temperature: float = Field(ge=0, le=2)
    reasoning_effort: Literal["low", "medium", "high"]


class ModelsConfig(Strict):
    roles: dict[str, RoleConfig]
    guardrail_retries: int = Field(ge=0)


def load_models_config(path: Path = DEFAULT_MODELS_PATH) -> ModelsConfig:
    with path.open(encoding="utf-8") as f:
        return ModelsConfig.model_validate(yaml.safe_load(f))


@dataclass(frozen=True)
class LLMUsage:
    model: str
    tokens_in: int
    tokens_out: int
    cached_tokens: int
    latency_ms: int

    def telemetry_fields(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cached_tokens": self.cached_tokens,
            "latency_ms": self.latency_ms,
        }


class LLMOutputError(Exception):
    """The model answered, but not in the requested schema."""

    def __init__(self, message: str, usage: LLMUsage, raw: str = ""):
        super().__init__(message)
        self.usage = usage
        self.raw = raw


class ChatClient(Protocol):
    """The slice of the Groq client we use; tests pass a fake."""

    chat: Any


class LLM:
    def __init__(self, config: ModelsConfig, client: ChatClient | None = None):
        self.config = config
        self._client = client

    @property
    def client(self) -> ChatClient:
        if self._client is None:
            self._client = groq.Groq(max_retries=0)  # retries are handled below
        return self._client

    def structured[T: BaseModel](
        self, role: str, messages: list[dict[str, str]], schema: type[T]
    ) -> tuple[T, str, LLMUsage]:
        """Call `role`'s model and parse the reply into `schema`. Returns (parsed, raw, usage)."""
        cfg = self.config.roles[role]
        try:
            response, latency_ms = self._create(
                model=cfg.model,
                temperature=cfg.temperature,
                reasoning_effort=cfg.reasoning_effort,
                messages=messages,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__,
                        "strict": True,
                        "schema": schema.model_json_schema(),
                    },
                },
            )
        except groq.BadRequestError as exc:
            if _error_code(exc) != "json_validate_failed":
                raise
            # Groq rejected its own output against the schema: same path as a bad reply.
            raise LLMOutputError(str(exc), LLMUsage(cfg.model, 0, 0, 0, 0)) from exc
        raw = response.choices[0].message.content or ""
        usage = _usage(response, cfg.model, latency_ms)
        try:
            return schema.model_validate_json(raw), raw, usage
        except ValidationError as exc:
            raise LLMOutputError(str(exc), usage, raw) from exc

    @retry(
        retry=retry_if_exception_type(TRANSIENT_ERRORS),
        wait=wait_exponential(multiplier=2, max=30),
        stop=stop_after_attempt(6),  # ~60 s of backoff: enough for the free tier per-minute cap
        reraise=True,
    )
    def _create(self, **kwargs: Any) -> tuple[Any, int]:
        """One attempt; latency excludes backoff between attempts."""
        started = time.perf_counter()
        response = self.client.chat.completions.create(**kwargs)
        return response, int((time.perf_counter() - started) * 1000)


def _usage(response: Any, model: str, latency_ms: int) -> LLMUsage:
    u = response.usage
    details = getattr(u, "prompt_tokens_details", None)
    return LLMUsage(
        model=model,
        tokens_in=u.prompt_tokens,
        tokens_out=u.completion_tokens,
        cached_tokens=getattr(details, "cached_tokens", 0) or 0,
        latency_ms=latency_ms,
    )


def _error_code(exc: groq.APIStatusError) -> str | None:
    body = exc.body if isinstance(exc.body, dict) else {}
    error = body.get("error", body)
    return error.get("code") if isinstance(error, dict) else None
