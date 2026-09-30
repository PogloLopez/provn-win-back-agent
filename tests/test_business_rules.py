import pytest
from pydantic import ValidationError

from winback.business_rules import BusinessRules, load_business_rules
from winback.carts import load_carts
from winback.rules_engine import load_triage_rules, triage

RULES = load_business_rules()
TRIAGE_RULES = load_triage_rules()
CARTS = {c.cart_id: c for c in load_carts()}


def menu_for(cart_id, **overrides):
    cart = CARTS[cart_id].model_copy(update=overrides)
    result = triage(cart, TRIAGE_RULES)
    return cart, result, RULES.menu(cart, result)


def test_every_triage_segment_has_a_policy():
    assert {s.name for s in TRIAGE_RULES.segments} == set(RULES.segments)


def test_offer_cost_by_unit():
    cart = CARTS["C-1002"]  # $140, 4 seats
    assert RULES.offer_cost("discount_pct", 10, cart) == 14.0
    assert RULES.offer_cost("extra_seat", 1, cart) == 35.0
    assert RULES.offer_cost("free_parking", 1, cart) == 15


def test_menu_respects_segment_allow_list_and_discount_cap():
    _, _, menu = menu_for("C-1001")  # loyal: max 15%
    assert {o["type"] for o in menu} <= {"discount_pct", "free_parking", "early_entry"}
    assert max(o["value"] for o in menu if o["type"] == "discount_pct") == 15


def test_menu_respects_dollar_cap_for_big_carts():
    _, _, menu = menu_for("C-1004", hours_since_abandon=5)  # premium, $540, cap $120
    discounts = [o["value"] for o in menu if o["type"] == "discount_pct"]
    assert discounts == [15, 20]  # premium floor is 15%; 30% would cost $162
    assert all(o["cost_usd"] <= 120 for o in menu)


def test_caution_carts_get_the_tighter_cap():
    _, result, menu = menu_for("C-1005")
    assert RULES.cost_cap(result) == 10
    assert "free_parking" not in {o["type"] for o in menu}  # $15 > $10


def test_unknown_allowed_offer_is_rejected():
    data = RULES.model_dump(exclude_none=True)
    data["segments"]["loyal"]["allowed"].append("free_beer")
    with pytest.raises(ValidationError, match="free_beer"):
        BusinessRules.model_validate(data)


def test_flag_offer_without_cost_is_rejected():
    data = RULES.model_dump(exclude_none=True)
    del data["offers"]["free_parking"]["levels"][0]["cost_usd"]
    with pytest.raises(ValidationError, match="cost_usd"):
        BusinessRules.model_validate(data)


def test_unknown_flag_level_raises_clearly():
    with pytest.raises(ValueError, match="no level"):
        RULES.offer_cost("free_parking", 3, CARTS["C-1001"])
