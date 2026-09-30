import json

import httpx
import pytest
from groq import APIConnectionError

from tests.fakes import FakeChatClient, assert_groq_strict
from winback.business_rules import load_business_rules
from winback.carts import load_carts
from winback.guarded import Status
from winback.llm import LLM, load_models_config
from winback.offer_models import Decision, OfferProposal
from winback.offer_strategist import build_request, propose_offer
from winback.rules_engine import load_triage_rules, triage
from winback.telemetry import Telemetry, make_engine

RULES = load_business_rules()
CONFIG = load_models_config()
CART = next(c for c in load_carts() if c.cart_id == "C-1001")
TRIAGE = triage(CART, load_triage_rules())

GOOD = {
    "cart_id": "C-1001",
    "decision": "offer",
    "offers": [{"type": "early_entry", "value": 1}],
    "reason": "Loyal fan who left the cart three hours ago; a free recognition perk is enough.",
    "reason_codes_cited": ["SEGMENT_LOYAL", "STAGE_EARLY"],
    "confidence": 0.8,
}
BAD = GOOD | {"offers": [{"type": "discount_pct", "value": 30}]}


def run(replies, **kwargs):
    client = FakeChatClient(replies)
    telemetry = Telemetry(make_engine("sqlite://"))
    result = propose_offer(
        CART, TRIAGE, rules=RULES, llm=LLM(CONFIG, client), telemetry=telemetry, **kwargs
    )
    return result, client, telemetry


def test_offer_schema_is_groq_strict():
    assert_groq_strict(OfferProposal.model_json_schema())


def test_request_contains_only_the_filtered_menu():
    request = build_request(CART, TRIAGE, RULES)
    assert request["policy"]["total_cost_cap_usd"] == 30
    assert {o["type"] for o in request["menu"]} <= {"discount_pct", "free_parking", "early_entry"}
    assert all("expected_value_usd" in o for o in request["menu"])
    assert request["policy"]["reminder_expected_value_usd"] == 4.8


def test_first_valid_proposal_is_accepted():
    result, client, telemetry = run([GOOD])
    assert result.status is Status.OK
    assert result.proposal.offers[0].type == "early_entry"
    assert len(client.requests) == 1
    assert [(e.stage, e.status) for e in telemetry.events()] == [
        ("offer", "ok"),
        ("offer_guardrail", "pass"),
    ]


def test_violation_is_fed_back_and_retried():
    result, client, telemetry = run([BAD, GOOD])
    assert result.status is Status.OK
    assert len(result.attempts) == 2
    retry_prompt = client.requests[1]["messages"][-1]["content"]
    assert "DISCOUNT_OUT_OF_RANGE" in retry_prompt
    guardrail = [e.status for e in telemetry.events(stage="offer_guardrail")]
    assert guardrail == ["fail", "pass"]


def test_persistent_violations_escalate_with_safe_default():
    result, client, _ = run([BAD, BAD, "not json"])
    assert result.status is Status.NEEDS_ATTENTION
    assert result.proposal.decision is Decision.REMINDER_ONLY
    assert result.proposal.offers == []
    assert len(client.requests) == CONFIG.guardrail_retries + 1
    assert result.attempts[-1].violations[0].code == "BAD_JSON"


def test_groq_outage_escalates_instead_of_crashing(monkeypatch):
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda _: None)
    down = APIConnectionError(request=httpx.Request("POST", "https://x"))
    result, _, telemetry = run([down] * 30)  # 6 transient retries x 3 guarded attempts
    assert result.status is Status.NEEDS_ATTENTION
    assert {e.status for e in telemetry.events()} == {"llm_unavailable", "needs_attention"}


def test_marketer_feedback_is_passed_to_the_model():
    _, client, _ = run([GOOD], feedback="too generous")
    assert "too generous" in client.requests[0]["messages"][-1]["content"]


@pytest.mark.live
def test_live_offer_passes_guardrails():
    telemetry = Telemetry(make_engine("sqlite://"))
    result = propose_offer(CART, TRIAGE, rules=RULES, llm=LLM(CONFIG), telemetry=telemetry)
    print(json.dumps(result.model_dump(mode="json"), indent=2))
    assert result.status is Status.OK
