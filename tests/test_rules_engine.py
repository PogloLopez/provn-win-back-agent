import pytest
from pydantic import ValidationError

from winback.carts import Cart, load_carts
from winback.rules_engine import Outcome, TriageRules, load_triage_rules, triage

RULES = load_triage_rules()
CARTS = {c.cart_id: c for c in load_carts()}


def run(cart_id: str, **overrides):
    return triage(CARTS[cart_id].model_copy(update=overrides), RULES)


# Golden set: expected triage for the brief's sample data (docs/architecture.md).
@pytest.mark.parametrize(
    ("cart_id", "outcome", "segment", "stage", "code"),
    [
        ("C-1001", Outcome.ELIGIBLE, "loyal", "early", None),
        ("C-1002", Outcome.ELIGIBLE, "first_timer", "mid", None),
        ("C-1003", Outcome.SKIP, "regular", "late", "SKIP_NO_OPT_IN"),
        ("C-1004", Outcome.DEFER, "premium", "early", "DEFER_TOO_RECENT"),
        ("C-1005", Outcome.CAUTION, "lapsed", "late", "SIGNAL_LAPSED"),
    ],
)
def test_golden_set(cart_id, outcome, segment, stage, code):
    result = run(cart_id)
    assert (result.outcome, result.segment, result.contact_stage) == (outcome, segment, stage)
    if code:
        assert code in result.reason_codes


def test_every_result_carries_segment_and_stage_codes():
    for cart in CARTS.values():
        codes = triage(cart, RULES).reason_codes
        assert any(c.startswith("SEGMENT_") for c in codes)
        assert any(c.startswith("STAGE_") for c in codes)


# Synthetic adversarial carts.
def test_opt_out_beats_everything_even_for_premium():
    result = run("C-1004", email_opt_in=False, hours_since_abandon=24)
    assert result.outcome is Outcome.SKIP
    assert "SKIP_NO_OPT_IN" in result.reason_codes


def test_suspected_reseller_is_skipped():
    assert run("C-1001", seats=12).outcome is Outcome.SKIP


def test_dormant_one_off_fan_is_skipped():
    result = run("C-1005", days_since_last_purchase=3650)
    assert result.outcome is Outcome.SKIP
    assert "SKIP_DORMANT" in result.reason_codes


def test_cart_outside_window_is_skipped():
    assert run("C-1002", hours_since_abandon=200).outcome is Outcome.SKIP


def test_skip_wins_over_defer():
    assert run("C-1004", email_opt_in=False).outcome is Outcome.SKIP


def test_large_first_cart_needs_caution():
    result = run("C-1002", cart_value=600)
    assert result.outcome is Outcome.CAUTION
    assert "SIGNAL_LARGE_FIRST_CART" in result.reason_codes


def test_deferred_cart_becomes_eligible_on_a_later_run():
    assert run("C-1004", hours_since_abandon=5).outcome is Outcome.ELIGIBLE


def test_never_purchased_does_not_match_purchase_ranges():
    cart = Cart(
        cart_id="X",
        fan_id="F",
        seats=2,
        section="Upper Deck",
        cart_value=50,
        hours_since_abandon=5,
        lifetime_tickets=0,
        days_since_last_purchase=None,
        email_opt_in=True,
    )
    assert "SIGNAL_LAPSED" not in triage(cart, RULES).reason_codes


# Config validation.
def test_segments_require_catch_all():
    data = RULES.model_dump(exclude_none=True)
    data["segments"] = data["segments"][:-1]
    with pytest.raises(ValidationError, match="catch-all"):
        TriageRules.model_validate(data)


def test_unknown_condition_field_is_rejected():
    data = RULES.model_dump(exclude_none=True)
    data["skip"][0]["when"]["min_seatz"] = 3
    with pytest.raises(ValidationError):
        TriageRules.model_validate(data)


def test_inverted_bounds_are_rejected():
    data = RULES.model_dump(exclude_none=True)
    data["defer"][0]["when"] = {"min_seats": 5, "max_seats": 2}
    with pytest.raises(ValidationError, match="min_seats > max_seats"):
        TriageRules.model_validate(data)
