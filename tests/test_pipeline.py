from tests.fakes import FakeChatClient
from tests.test_copy import GOOD as GOOD_COPY
from tests.test_offer_strategist import BAD as BAD_OFFER
from tests.test_offer_strategist import GOOD as GOOD_OFFER
from winback.business_rules import load_business_rules
from winback.carts import load_carts
from winback.copywriter import load_persona
from winback.llm import LLM, load_models_config
from winback.pipeline import CartStatus, Pipeline
from winback.rules_engine import load_triage_rules
from winback.telemetry import Telemetry, make_engine

CARTS = {c.cart_id: c for c in load_carts()}
OFFER_1001 = GOOD_OFFER | {"offers": [{"type": "discount_pct", "value": 10}]}


def pipeline(replies) -> Pipeline:
    return Pipeline(
        triage_rules=load_triage_rules(),
        rules=load_business_rules(),
        persona=load_persona(),
        llm=LLM(load_models_config(), FakeChatClient(replies)),
        telemetry=Telemetry(make_engine("sqlite://")),
    )


def test_skip_and_defer_never_call_the_llm():
    p = pipeline([])
    assert p.process(CARTS["C-1003"]).status is CartStatus.SKIPPED
    assert p.process(CARTS["C-1004"]).status is CartStatus.DEFERRED
    assert [e.stage for e in p.telemetry.events()] == ["triage", "triage"]


def test_eligible_cart_goes_end_to_end():
    outcome = pipeline([OFFER_1001, GOOD_COPY]).process(CARTS["C-1001"])
    assert outcome.status is CartStatus.READY
    assert "10% off your order" in outcome.email.email.body


def test_offer_escalation_still_produces_a_reminder_email():
    outcome = pipeline([BAD_OFFER] * 3 + [GOOD_COPY | {"body": "{{checkout_link}} see you"}])
    result = outcome.process(CARTS["C-1001"])
    assert result.status is CartStatus.NEEDS_ATTENTION
    assert result.offer.proposal.offers == []
    assert result.email.email.body.startswith("https://example.com/checkout/C-1001")


def test_run_streams_every_cart():
    replies = [OFFER_1001, GOOD_COPY]
    p = pipeline(replies)
    outcomes = list(p.run([CARTS["C-1001"], CARTS["C-1003"], CARTS["C-1004"]]))
    assert sorted(o.cart.cart_id for o in outcomes) == ["C-1001", "C-1003", "C-1004"]
    assert p.telemetry.failures == 0
    assert len(p.telemetry.events(stage="triage")) == 3


def test_unexpected_error_fails_one_cart_not_the_run():
    p = pipeline([])  # no replies queued: the LLM call raises IndexError
    outcomes = {o.cart.cart_id: o for o in p.run([CARTS["C-1001"], CARTS["C-1003"]])}
    assert outcomes["C-1001"].status is CartStatus.FAILED
    assert "IndexError" in outcomes["C-1001"].error
    assert outcomes["C-1003"].status is CartStatus.SKIPPED
    assert p.telemetry.events(stage="pipeline")[0].status == "failed"
