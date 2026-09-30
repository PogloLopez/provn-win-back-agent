"""Shared LLM loop: call, check with guardrails, re-prompt with violations, then escalate."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

import groq
from pydantic import BaseModel

from winback.guardrails import Severity, Violation, blocking
from winback.llm import LLM, LLMOutputError
from winback.telemetry import Stage, Telemetry


class Status(StrEnum):
    OK = "ok"
    NEEDS_ATTENTION = "needs_attention"


class Attempt(BaseModel):
    raw: str
    violations: list[Violation]


@dataclass
class Guarded[T: BaseModel]:
    value: T | None  # None when every attempt was blocked
    attempts: list[Attempt]
    warnings: list[Violation]

    @property
    def status(self) -> Status:
        return Status.OK if self.value is not None else Status.NEEDS_ATTENTION


def guarded_call[T: BaseModel](
    *,
    llm: LLM,
    role: str,
    messages: list[dict[str, str]],
    schema: type[T],
    check: Callable[[T], list[Violation]],
    telemetry: Telemetry,
    cart_id: str,
    llm_stage: Stage,
    guard_stage: Stage,
) -> Guarded[T]:
    """Up to `guardrail_retries` re-prompts; every attempt and the escalation are recorded."""
    messages = list(messages)
    attempts: list[Attempt] = []
    for attempt in range(1, llm.config.guardrail_retries + 2):
        try:
            value, raw, usage = llm.structured(role, messages, schema)
            telemetry.record(
                llm_stage,
                "ok",
                cart_id=cart_id,
                attempt=attempt,
                payload=value.model_dump(mode="json"),
                **usage.telemetry_fields(),
            )
            violations = check(value)
        except (LLMOutputError, groq.APIError) as exc:
            # Off-schema reply, or Groq still failing after transient retries.
            code = "BAD_JSON" if isinstance(exc, LLMOutputError) else "LLM_UNAVAILABLE"
            value, raw = None, getattr(exc, "raw", "")
            violations = [Violation(code=code, message=str(exc)[:300])]
            usage = exc.usage.telemetry_fields() if isinstance(exc, LLMOutputError) else {}
            telemetry.record(
                llm_stage,
                code.lower(),
                cart_id=cart_id,
                attempt=attempt,
                reason_codes=[code],
                **usage,
            )

        blockers = blocking(violations)
        if value is not None:
            telemetry.record(
                guard_stage,
                "fail" if blockers else "pass",
                cart_id=cart_id,
                attempt=attempt,
                reason_codes=[v.code for v in violations],
            )
        attempts.append(Attempt(raw=raw, violations=violations))
        if value is not None and not blockers:
            warnings = [v for v in violations if v.severity is Severity.WARN]
            return Guarded(value=value, attempts=attempts, warnings=warnings)
        messages += [
            {"role": "assistant", "content": raw or "(invalid output)"},
            {
                "role": "user",
                "content": "Your answer broke these rules. Fix them and answer again:\n"
                + "\n".join(f"- {v.code}: {v.message}" for v in blockers),
            },
        ]

    telemetry.record(
        llm_stage,
        Status.NEEDS_ATTENTION,
        cart_id=cart_id,
        attempt=len(attempts),
        reason_codes=sorted({v.code for a in attempts for v in a.violations}),
    )
    return Guarded(value=None, attempts=attempts, warnings=[])
