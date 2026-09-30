"""Boundary and reason-code checks for the triage rules (inclusive min_/max_ bounds)."""

import pytest

from winback.carts import load_carts
from winback.rules_engine import Outcome, load_triage_rules, triage

RULES = load_triage_rules()
CARTS = {c.cart_id: c for c in load_carts()}


def run(cart_id: str, **overrides):
    return triage(CARTS[cart_id].model_copy(update=overrides), RULES)


@pytest.mark.parametrize(
    ("cart_id", "overrides", "outcome", "code"),
    [
        ("C-1001", {"seats": 10}, Outcome.SKIP, "SKIP_SUSPECTED_RESELLER"),
        ("C-1001", {"seats": 9}, Outcome.ELIGIBLE, None),
        ("C-1001", {"hours_since_abandon": 168}, Outcome.SKIP, "SKIP_OUTSIDE_WINDOW"),
        ("C-1001", {"hours_since_abandon": 167.9}, Outcome.ELIGIBLE, "SIGNAL_OLD_CART"),
        ("C-1004", {"hours_since_abandon": 2}, Outcome.DEFER, "DEFER_TOO_RECENT"),
        ("C-1004", {"hours_since_abandon": 2.1}, Outcome.ELIGIBLE, None),
        ("C-1005", {"days_since_last_purchase": 730}, Outcome.SKIP, "SKIP_DORMANT"),
        ("C-1005", {"days_since_last_purchase": 729}, Outcome.CAUTION, "SIGNAL_LAPSED"),
        ("C-1002", {"cart_value": 400}, Outcome.CAUTION, "SIGNAL_LARGE_FIRST_CART"),
        ("C-1002", {"cart_value": 399.99}, Outcome.ELIGIBLE, None),
    ],
)
def test_rule_boundaries_are_inclusive(cart_id, overrides, outcome, code):
    result = run(cart_id, **overrides)
    assert result.outcome is outcome
    if code:
        assert code in result.reason_codes


def test_caution_score_below_threshold_stays_eligible_but_keeps_signal():
    result = run("C-1001", hours_since_abandon=80)
    assert (result.outcome, result.caution_score) == (Outcome.ELIGIBLE, 1)
    assert "SIGNAL_OLD_CART" in result.reason_codes


def test_caution_score_at_threshold_flags_caution():
    result = run("C-1001", hours_since_abandon=80, days_since_last_purchase=200)
    assert (result.outcome, result.caution_score) == (Outcome.CAUTION, 2)


def test_golden_c1005_cites_all_three_signals():
    result = run("C-1005")
    assert result.caution_score == 3
    for code in ("SIGNAL_OLD_CART", "SIGNAL_LAPSED", "SIGNAL_LOW_ENGAGEMENT"):
        assert code in result.reason_codes


def test_skip_reports_every_matching_skip_code_and_no_signals():
    result = run("C-1005", email_opt_in=False, seats=12)
    assert result.outcome is Outcome.SKIP
    assert {"SKIP_NO_OPT_IN", "SKIP_SUSPECTED_RESELLER"} <= set(result.reason_codes)
    assert not any(c.startswith("SIGNAL_") for c in result.reason_codes)


def test_eligible_golden_carts_carry_no_skip_or_defer_codes():
    for cart_id in ("C-1001", "C-1002"):
        codes = run(cart_id).reason_codes
        assert not any(c.startswith(("SKIP_", "DEFER_")) for c in codes)
