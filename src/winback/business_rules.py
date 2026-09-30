"""Business rules: offer catalogue, per-segment policy, and offer cost."""

from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import Field, model_validator

from winback.carts import Cart
from winback.rules_engine import Outcome, Strict, TriageResult

DEFAULT_BUSINESS_RULES_PATH = Path(__file__).parents[2] / "config" / "business_rules.yaml"


class Unit(StrEnum):
    PERCENT = "percent"
    SEATS = "seats"
    FLAG = "flag"


class Level(Strict):
    value: float
    conversion_rate: float = Field(ge=0, le=1)
    cost_usd: float | None = Field(default=None, ge=0)  # required for flag offers only


class OfferType(Strict):
    description: str
    unit: Unit
    levels: list[Level] = Field(min_length=1)

    @model_validator(mode="after")
    def _flag_costs_known(self) -> "OfferType":
        if self.unit is Unit.FLAG and any(lvl.cost_usd is None for lvl in self.levels):
            raise ValueError("flag offers need cost_usd on every level")
        return self

    def level(self, value: float) -> Level | None:
        return next((lvl for lvl in self.levels if lvl.value == value), None)


class SegmentPolicy(Strict):
    allowed: list[str]
    min_discount_pct: float = Field(default=0, ge=0, le=100)
    max_discount_pct: float = Field(ge=0, le=100)
    max_offer_cost_usd: float = Field(ge=0)
    max_offers: int = Field(ge=1)


class BusinessRules(Strict):
    reminder_conversion_rate: float = Field(ge=0, le=1)
    offers: dict[str, OfferType]
    segments: dict[str, SegmentPolicy]
    caution_max_offer_cost_usd: float = Field(ge=0)

    @model_validator(mode="after")
    def _allowed_offers_exist(self) -> "BusinessRules":
        for name, policy in self.segments.items():
            if unknown := set(policy.allowed) - set(self.offers):
                raise ValueError(f"segment {name} allows unknown offers: {sorted(unknown)}")
        return self

    def cost_cap(self, triage: TriageResult) -> float:
        cap = self.segments[triage.segment].max_offer_cost_usd
        if triage.outcome is Outcome.CAUTION:
            cap = min(cap, self.caution_max_offer_cost_usd)
        return cap

    def offer_cost(self, offer_type: str, value: float, cart: Cart) -> float:
        offer = self.offers[offer_type]
        match offer.unit:
            case Unit.PERCENT:
                return round(cart.cart_value * value / 100, 2)
            case Unit.SEATS:
                return round(cart.cart_value / cart.seats * value, 2)
            case Unit.FLAG:
                level = offer.level(value)
                if level is None:
                    raise ValueError(f"{offer_type} has no level {value}")
                return level.cost_usd or 0.0

    def menu(self, cart: Cart, triage: TriageResult) -> list[dict]:
        """Options this cart may receive, each with cost and conversion rate.

        Each option fits the caps on its own; combined offers must still fit the total cap.
        """
        policy = self.segments[triage.segment]
        cap = self.cost_cap(triage)
        options = []
        for name in policy.allowed:
            offer = self.offers[name]
            for lvl in offer.levels:
                if offer.unit is Unit.PERCENT and not (
                    policy.min_discount_pct <= lvl.value <= policy.max_discount_pct
                ):
                    continue
                cost = self.offer_cost(name, lvl.value, cart)
                if cost <= cap:
                    options.append(
                        {
                            "type": name,
                            "value": lvl.value,
                            "unit": offer.unit.value,
                            "description": offer.description,
                            "cost_usd": cost,
                            "conversion_rate": lvl.conversion_rate,
                        }
                    )
        return options


def load_business_rules(path: Path = DEFAULT_BUSINESS_RULES_PATH) -> BusinessRules:
    with path.open(encoding="utf-8") as f:
        return BusinessRules.model_validate(yaml.safe_load(f))
