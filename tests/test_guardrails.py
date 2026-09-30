import pytest

from winback.business_rules import load_business_rules
from winback.carts import load_carts
from winback.guardrails import Severity, blocking, check_offer
from winback.offer_models import OfferProposal
from winback.rules_engine import load_triage_rules, triage

RULES = load_business_rules()
TRIAGE_RULES = load_triage_rules()
CARTS = {c.cart_id: c for c in load_carts()}


def check(cart_key="C-1001", cart_overrides=None, **fields):
    cart = CARTS[cart_key].model_copy(update=cart_overrides or {})
    result = triage(cart, TRIAGE_RULES)
    proposal = {
        "cart_id": cart.cart_id,
        "decision": "offer",
        "offers": [{"type": "early_entry", "value": 1}],
        "reason": "Loyal fan who dropped the cart early; a small perk is enough.",
        "reason_codes_cited": ["SEGMENT_LOYAL"],
        "confidence": 0.7,
    } | fields
    return check_offer(OfferProposal.model_validate(proposal), cart, result, RULES)


def codes(violations):
    return {v.code for v in violations}


def test_valid_proposal_passes():
    assert check() == []


@pytest.mark.parametrize(
    ("fields", "code"),
    [
        ({"cart_id": "C-9999"}, "WRONG_CART"),
        ({"offers": []}, "EMPTY_OFFER"),
        ({"decision": "reminder_only"}, "UNEXPECTED_OFFERS"),
        ({"offers": [{"type": "seat_upgrade", "value": 1}]}, "OFFER_NOT_ALLOWED"),
        ({"offers": [{"type": "free_beer", "value": 1}]}, "OFFER_NOT_ALLOWED"),
        ({"offers": [{"type": "discount_pct", "value": 12}]}, "UNKNOWN_LEVEL"),
        ({"offers": [{"type": "discount_pct", "value": 20}]}, "DISCOUNT_OUT_OF_RANGE"),
        ({"reason": "ok"}, "NO_REASON"),
        ({"reason_codes_cited": []}, "UNGROUNDED_REASON"),
        ({"reason_codes_cited": ["SEGMENT_PREMIUM"]}, "UNGROUNDED_REASON"),
        ({"confidence": 1.5}, "BAD_CONFIDENCE"),
        (
            {
                "offers": [
                    {"type": "early_entry", "value": 1},
                    {"type": "early_entry", "value": 1},
                ]
            },
            "DUPLICATE_OFFER",
        ),
    ],
)
def test_each_rule_blocks(fields, code):
    assert code in codes(blocking(check(**fields)))


def test_total_cost_over_cap_blocks_even_if_each_offer_fits():
    # loyal cap $30: 15% of $96 ($14.40) + parking ($15) = $29.40 fits; on a $120 cart it does not
    offers = [{"type": "discount_pct", "value": 15}, {"type": "free_parking", "value": 1}]
    assert "OVER_COST_CAP" not in codes(check(offers=offers))
    over = check(cart_overrides={"cart_value": 120}, offers=offers)
    assert "OVER_COST_CAP" in codes(blocking(over))


def test_too_many_offers_blocks():
    offers = [{"type": "free_parking", "value": 1}, {"type": "early_entry", "value": 1}]
    assert "TOO_MANY_OFFERS" in codes(
        check("C-1002", offers=offers, reason_codes_cited=["SEGMENT_FIRST_TIMER"])
    )


def test_caution_cart_gets_tighter_cap():
    violations = check(
        "C-1005",
        offers=[{"type": "free_parking", "value": 1}],
        reason_codes_cited=["SIGNAL_LAPSED"],
    )
    assert "OVER_COST_CAP" in codes(violations)


def test_most_expensive_option_is_a_warning_not_a_block():
    assert check(offers=[{"type": "discount_pct", "value": 15}]) == []  # $14.40 < $15 parking
    violations = check(offers=[{"type": "free_parking", "value": 1}])
    assert [v.severity for v in violations] == [Severity.WARN]
    assert blocking(violations) == []
