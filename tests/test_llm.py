import httpx
import pytest
from groq import BadRequestError, RateLimitError

from tests.fakes import FakeChatClient, assert_groq_strict
from winback.llm import LLM, LLMOutputError, load_models_config
from winback.rules_engine import Strict

CONFIG = load_models_config()


class Answer(Strict):
    ok: bool


def test_answer_schema_is_groq_strict():
    assert_groq_strict(Answer.model_json_schema())


def test_structured_call_parses_and_reports_usage():
    client = FakeChatClient([{"ok": True}])
    parsed, raw, usage = LLM(CONFIG, client).structured("copywriter", [], Answer)
    assert parsed.ok is True
    assert raw == '{"ok": true}'
    assert (usage.tokens_in, usage.tokens_out, usage.cached_tokens) == (100, 20, 40)
    request = client.requests[0]
    assert request["model"] == CONFIG.roles["copywriter"].model
    assert request["response_format"]["json_schema"]["strict"] is True


def test_off_schema_reply_raises_with_usage():
    with pytest.raises(LLMOutputError) as exc:
        LLM(CONFIG, FakeChatClient(['{"nope": 1}'])).structured("copywriter", [], Answer)
    assert exc.value.usage.tokens_in == 100


def test_rate_limit_is_retried(monkeypatch):
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda _: None)
    response = httpx.Response(429, request=httpx.Request("POST", "https://x"))
    client = FakeChatClient([RateLimitError("slow down", response=response, body=None), {"ok": 1}])
    parsed, _, _ = LLM(CONFIG, client).structured("copywriter", [], Answer)
    assert parsed.ok is True
    assert len(client.requests) == 2


def test_groq_json_validate_failed_becomes_output_error():
    response = httpx.Response(400, request=httpx.Request("POST", "https://x"))
    error = BadRequestError(
        "bad json",
        response=response,
        body={"code": "json_validate_failed"},  # SDK unwraps "error"
    )
    with pytest.raises(LLMOutputError):
        LLM(CONFIG, FakeChatClient([error])).structured("copywriter", [], Answer)


@pytest.mark.live
def test_live_groq_strict_json():
    parsed, _, usage = LLM(CONFIG).structured(
        "copywriter", [{"role": "user", "content": "Reply with ok=true."}], Answer
    )
    assert parsed.ok is True
    assert usage.tokens_in > 0
