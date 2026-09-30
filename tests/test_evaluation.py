import pytest

from tests.fakes import FakeChatClient, assert_groq_strict
from winback.business_rules import load_business_rules
from winback.carts import load_carts
from winback.evaluation import (
    BaselineRun,
    Decided,
    Score,
    baseline_decisions,
    incentive_cost,
    report,
    score,
    telemetry_summary,
)
from winback.llm import LLM, load_models_config
from winback.offer_models import ProposedOffer

RULES = load_business_rules()
CARTS = {c.cart_id: c for c in load_carts()}


def decided(cart_id, contact=True, **offers):
    return Decided(
        cart_id=cart_id,
        contact=contact,
        offers=[ProposedOffer(type=t, value=v) for t, v in offers.items()],
    )


def test_baseline_schema_is_groq_strict():
    assert_groq_strict(BaselineRun.model_json_schema())


def test_contacting_skipped_or_deferred_carts_is_wrong():
    result = score([decided("C-1003"), decided("C-1004")], CARTS, RULES)
    assert result.contacted_skipped == ["C-1003 (SKIP_NO_OPT_IN)"]
    assert result.contacted_too_early == ["C-1004 (DEFER_TOO_RECENT)"]


def test_offers_outside_policy_are_flagged():
    result = score(
        [decided("C-1001", discount_pct=30), decided("C-1002", extra_seat=1)], CARTS, RULES
    )
    # 30% exceeds the loyal cap of 15%; one extra seat is within the first-timer policy.
    assert result.policy_violations == {"C-1001": ["DISCOUNT_OUT_OF_RANGE"]}


def test_not_contacting_costs_nothing():
    result = score([decided("C-1003", contact=False)], CARTS, RULES)
    assert (result.contacted, result.incentive_cost_usd, result.contacted_skipped) == (0, 0.0, [])


def test_incentive_cost_handles_off_catalogue_values():
    cart = CARTS["C-1004"]  # $540, 6 seats
    offers = [
        ProposedOffer(type="discount_pct", value=25),
        ProposedOffer(type="extra_seat", value=2),
    ]
    assert incentive_cost(offers, cart, RULES) == 135 + 180


def test_baseline_call_parses_one_entry_per_cart():
    reply = {
        "carts": [
            {"cart_id": c, "contact": True, "offers": [], "reason": "nudge"}
            for c in ("C-1001", "C-1003")
        ]
    }
    llm = LLM(load_models_config(), FakeChatClient([reply]))
    result = baseline_decisions([CARTS["C-1001"], CARTS["C-1003"]], llm)
    assert [d.cart_id for d in result] == ["C-1001", "C-1003"]


def test_report_renders_a_row_per_system():
    s = Score(
        contacted=5,
        contacted_skipped=["C-1003 (x)"],
        contacted_too_early=[],
        policy_violations={},
        incentive_cost_usd=10,
    )
    clean = s.model_copy(update={"contacted_skipped": []})
    text = report({"Plain LLM": [s], "Pipeline": [clean]}, runs=1, cart_count=5)
    assert "| Plain LLM | 5.0 | 1.0 | 0.0 |" in text
    assert "| Pipeline | 5.0 | 0.0 | 0.0 |" in text
    assert "contacted C-1003 (x) x1" in text


def test_baseline_that_drops_a_cart_is_rejected():
    reply = {"carts": [{"cart_id": "C-1001", "contact": True, "offers": [], "reason": "x"}]}
    llm = LLM(load_models_config(), FakeChatClient([reply]))
    with pytest.raises(ValueError, match="one per input cart"):
        baseline_decisions([CARTS["C-1001"], CARTS["C-1003"]], llm)


def test_prompted_baseline_gets_both_rule_files():
    reply = {"carts": [{"cart_id": "C-1001", "contact": False, "offers": [], "reason": "x"}]}
    client = FakeChatClient([reply])
    baseline_decisions([CARTS["C-1001"]], LLM(load_models_config(), client), with_rules=True)
    system = client.requests[0]["messages"][0]["content"]
    assert "SKIP_NO_OPT_IN" in system and "max_offer_cost_usd" in system


def test_telemetry_summary_counts_guardrail_outcomes():
    from winback.telemetry import Stage, Telemetry, make_engine

    telemetry = Telemetry(make_engine("sqlite://"))
    telemetry.record(Stage.COPY_GUARDRAIL, "fail", reason_codes=["RAW_VALUE"])
    telemetry.record(Stage.COPY_GUARDRAIL, "pass")
    telemetry.record(Stage.OFFER_GUARDRAIL, "pass")
    telemetry.record(Stage.COPY, "needs_attention")
    summary = telemetry_summary(telemetry.engine)
    assert "| copy_guardrail | 2 | 1 (50%) | RAW_VALUE x1 |" in summary
    assert "| offer_guardrail | 1 | 0 (0%) | none |" in summary
    assert "copy x1" in summary
