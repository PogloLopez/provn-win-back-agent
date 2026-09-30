"""Telemetry rows written by the offer retry / NEEDS_ATTENTION path."""

from tests.test_offer_strategist import BAD, CONFIG, GOOD, run
from winback.guardrails import Severity
from winback.offer_strategist import OfferStatus


def test_each_attempt_is_numbered_and_carries_usage():
    _, _, telemetry = run([BAD, GOOD])
    offers = telemetry.events(stage="offer")
    assert [e.attempt for e in offers] == [1, 2]
    assert all(e.tokens_in == 100 and e.tokens_out == 20 for e in offers)
    assert all(e.cached_tokens == 40 and e.model for e in offers)
    guard = telemetry.events(stage="offer_guardrail")
    assert [e.attempt for e in guard] == [1, 2]
    assert "DISCOUNT_OUT_OF_RANGE" in guard[0].reason_codes
    assert guard[1].reason_codes == []


def test_escalation_rows_per_attempt():
    result, _, telemetry = run([BAD, BAD, "not json"])
    assert result.status is OfferStatus.NEEDS_ATTENTION
    rows = [(e.stage, e.status, e.attempt) for e in telemetry.events()]
    assert rows == [
        ("offer", "ok", 1),
        ("offer_guardrail", "fail", 1),
        ("offer", "ok", 2),
        ("offer_guardrail", "fail", 2),
        ("offer", "bad_json", 3),
        ("offer", "needs_attention", 3),
    ]
    assert result.attempts[-1].raw == "not json"  # raw reply kept for the marketer
    bad_json = telemetry.events(status="bad_json")[0]
    assert bad_json.reason_codes == ["BAD_JSON"]
    assert bad_json.tokens_in == 100  # usage kept even when the reply is off-schema
    assert len(result.attempts) == CONFIG.guardrail_retries + 1


def test_bad_json_then_valid_recovers():
    result, client, _ = run(["not json", GOOD])
    assert result.status is OfferStatus.OK
    assert "BAD_JSON" in client.requests[1]["messages"][-1]["content"]


def test_warning_is_surfaced_on_accepted_offer():
    parking = GOOD | {"offers": [{"type": "free_parking", "value": 1}]}
    result, client, telemetry = run([parking])
    assert result.status is OfferStatus.OK
    assert len(client.requests) == 1  # a WARN does not trigger a retry
    assert [w.severity for w in result.warnings] == [Severity.WARN]
    guard = telemetry.events(stage="offer_guardrail")[0]
    assert (guard.status, guard.reason_codes) == ("pass", ["MOST_EXPENSIVE_OPTION"])
