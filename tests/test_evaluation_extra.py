import pytest

from tests.fakes import FakeChatClient
from winback.business_rules import load_business_rules
from winback.carts import load_carts
from winback.evaluation import baseline_decisions, incentive_cost, telemetry_summary
from winback.llm import LLM, load_models_config
from winback.offer_models import ProposedOffer
from winback.telemetry import Stage, Telemetry, make_engine

RULES = load_business_rules()
CARTS = {c.cart_id: c for c in load_carts()}


def entry(cart_id):
    return {"cart_id": cart_id, "contact": True, "offers": [], "reason": "x"}


@pytest.mark.parametrize(
    "ids",
    [["C-1001", "C-1001"], ["C-1001", "C-9999"], ["C-1001", "C-1003", "C-9999"]],
    ids=["repeat", "invented", "extra"],
)
def test_baseline_that_repeats_or_invents_a_cart_is_rejected(ids):
    llm = LLM(load_models_config(), FakeChatClient([{"carts": [entry(c) for c in ids]}]))
    with pytest.raises(ValueError, match="one per input cart"):
        baseline_decisions([CARTS["C-1001"], CARTS["C-1003"]], llm)


def test_flag_offer_off_catalogue_value_priced_at_dearest_level():
    cart = CARTS["C-1001"]
    offers = [
        ProposedOffer(type="free_parking", value=3),
        ProposedOffer(type="seat_upgrade", value=1),
    ]
    assert incentive_cost(offers, cart, RULES) == 15 + 25


def test_unknown_offer_type_costs_nothing():
    offers = [ProposedOffer(type="free_beer", value=1)]
    assert incentive_cost(offers, CARTS["C-1001"], RULES) == 0.0


def test_telemetry_summary_ignores_llm_stage_failures_and_splits_escalations():
    telemetry = Telemetry(make_engine("sqlite://"))
    telemetry.record(Stage.OFFER, "bad_json", reason_codes=["BAD_JSON"])
    telemetry.record(Stage.OFFER_GUARDRAIL, "fail", reason_codes=["A", "B"])
    telemetry.record(Stage.OFFER_GUARDRAIL, "fail", reason_codes=["A"])
    telemetry.record(Stage.OFFER, "needs_attention")
    telemetry.record(Stage.COPY, "needs_attention")
    summary = telemetry_summary(telemetry.engine)
    assert "| offer_guardrail | 2 | 2 (100%) | A x2, B x1 |" in summary
    assert "| copy_guardrail | 0 | 0 | none |" in summary
    assert "offer x1" in summary and "copy x1" in summary
    assert "BAD_JSON" not in summary


def test_telemetry_summary_empty_db():
    summary = telemetry_summary(make_engine("sqlite://"))
    assert "Escalated to the marketer after all retries: none." in summary
