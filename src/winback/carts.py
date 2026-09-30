"""Stale cart records and loading."""

import csv
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator

DEFAULT_CARTS_PATH = Path(__file__).parents[2] / "data" / "stale_carts.csv"


class Cart(BaseModel):
    """One stale cart. Times are relative to the dataset snapshot."""

    cart_id: str
    fan_id: str
    seats: int = Field(ge=1)
    section: str
    cart_value: float = Field(ge=0)
    hours_since_abandon: float = Field(ge=0)
    lifetime_tickets: int = Field(ge=0)
    days_since_last_purchase: int | None = Field(default=None, ge=0)  # None = never purchased
    email_opt_in: bool

    @field_validator("days_since_last_purchase", mode="before")
    @classmethod
    def _blank_is_never(cls, v: object) -> object:
        return None if v == "" else v

    @model_validator(mode="after")
    def _purchase_history_consistent(self) -> "Cart":
        if (self.lifetime_tickets == 0) != (self.days_since_last_purchase is None):
            raise ValueError("lifetime_tickets == 0 exactly when there is no last purchase")
        return self


def load_carts(path: Path = DEFAULT_CARTS_PATH) -> list[Cart]:
    """Load all carts. A malformed row raises ValidationError; rows are never skipped."""
    with path.open(newline="", encoding="utf-8") as f:
        return [Cart.model_validate(row) for row in csv.DictReader(f)]
