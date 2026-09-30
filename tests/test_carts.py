import pytest
from pydantic import ValidationError

from winback.carts import Cart, load_carts


def test_sample_dataset_loads():
    carts = {c.cart_id: c for c in load_carts()}
    assert list(carts) == ["C-1001", "C-1002", "C-1003", "C-1004", "C-1005"]
    assert carts["C-1002"].days_since_last_purchase is None
    assert carts["C-1003"].email_opt_in is False
    assert carts["C-1004"].seats == 6


def test_malformed_row_fails_loudly(tmp_path):
    bad = tmp_path / "carts.csv"
    bad.write_text(
        "cart_id,fan_id,seats,section,cart_value,hours_since_abandon,lifetime_tickets,"
        "days_since_last_purchase,email_opt_in\nC-9,F-9,0,Club,10,1,1,1,true\n"
    )
    with pytest.raises(ValidationError):
        load_carts(bad)


@pytest.mark.parametrize(("tickets", "days"), [(0, 30), (3, None)])
def test_inconsistent_purchase_history_is_rejected(tickets, days):
    row = load_carts()[0].model_dump() | {
        "lifetime_tickets": tickets,
        "days_since_last_purchase": days,
    }
    with pytest.raises(ValidationError, match="last purchase"):
        Cart.model_validate(row)
