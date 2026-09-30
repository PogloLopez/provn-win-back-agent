"""Rules Engine (triage): deterministic SKIP / DEFER / CAUTION / ELIGIBLE per cart."""

from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from winback.carts import Cart, load_carts

DEFAULT_RULES_PATH = Path(__file__).parents[2] / "config" / "triage_rules.yaml"
RANGE_FIELDS = (
    "seats",
    "cart_value",
    "hours_since_abandon",
    "lifetime_tickets",
    "days_since_last_purchase",
)


class Strict(BaseModel):
    """Config models reject unknown keys, so a typo in the YAML fails loudly."""

    model_config = ConfigDict(extra="forbid")


class Condition(Strict):
    """AND of all set fields. `min_*` / `max_*` bounds are inclusive."""

    email_opt_in: bool | None = None
    never_purchased: bool | None = None
    min_seats: int | None = None
    max_seats: int | None = None
    min_cart_value: float | None = None
    max_cart_value: float | None = None
    min_hours_since_abandon: float | None = None
    max_hours_since_abandon: float | None = None
    min_lifetime_tickets: int | None = None
    max_lifetime_tickets: int | None = None
    min_days_since_last_purchase: int | None = None
    max_days_since_last_purchase: int | None = None

    @model_validator(mode="after")
    def _bounds_ordered(self) -> "Condition":
        for field in RANGE_FIELDS:
            lo, hi = getattr(self, f"min_{field}"), getattr(self, f"max_{field}")
            if lo is not None and hi is not None and lo > hi:
                raise ValueError(f"min_{field} > max_{field}")
        return self

    def matches(self, cart: Cart) -> bool:
        if self.email_opt_in is not None and cart.email_opt_in != self.email_opt_in:
            return False
        never = cart.days_since_last_purchase is None
        if self.never_purchased is not None and never != self.never_purchased:
            return False
        for field in RANGE_FIELDS:
            lo, hi = getattr(self, f"min_{field}"), getattr(self, f"max_{field}")
            if lo is None and hi is None:
                continue
            value = getattr(cart, field)
            if value is None or (lo is not None and value < lo) or (hi is not None and value > hi):
                return False
        return True

    @property
    def is_catch_all(self) -> bool:
        return not self.model_dump(exclude_none=True)


class CodedRule(Strict):
    code: str
    when: Condition


class Signal(CodedRule):
    weight: int = Field(ge=1)


class Caution(Strict):
    threshold: int = Field(ge=1)
    signals: list[Signal]


class NamedRule(Strict):
    name: str
    when: Condition


class TriageRules(Strict):
    skip: list[CodedRule]
    defer: list[CodedRule]
    caution: Caution
    segments: list[NamedRule]
    contact_stages: list[NamedRule]

    @field_validator("segments", "contact_stages")
    @classmethod
    def _require_catch_all(cls, rules: list[NamedRule]) -> list[NamedRule]:
        if not rules or not rules[-1].when.is_catch_all:
            raise ValueError("last entry must be a catch-all (`when: {}`)")
        return rules


class Outcome(StrEnum):
    SKIP = "SKIP"
    DEFER = "DEFER"
    CAUTION = "CAUTION"
    ELIGIBLE = "ELIGIBLE"


class TriageResult(BaseModel):
    cart_id: str
    outcome: Outcome
    reason_codes: list[str]
    segment: str
    contact_stage: str
    caution_score: int


def load_triage_rules(path: Path = DEFAULT_RULES_PATH) -> TriageRules:
    with path.open(encoding="utf-8") as f:
        return TriageRules.model_validate(yaml.safe_load(f))


def _first_match(rules: list[NamedRule], cart: Cart) -> str:
    return next(r.name for r in rules if r.when.matches(cart))


def triage(cart: Cart, rules: TriageRules) -> TriageResult:
    segment = _first_match(rules.segments, cart)
    stage = _first_match(rules.contact_stages, cart)
    context = [f"SEGMENT_{segment.upper()}", f"STAGE_{stage.upper()}"]
    signals = [s for s in rules.caution.signals if s.when.matches(cart)]
    score = sum(s.weight for s in signals)

    if skips := [r.code for r in rules.skip if r.when.matches(cart)]:
        outcome, codes = Outcome.SKIP, skips
    elif defers := [r.code for r in rules.defer if r.when.matches(cart)]:
        outcome, codes = Outcome.DEFER, defers
    else:
        outcome = Outcome.CAUTION if score >= rules.caution.threshold else Outcome.ELIGIBLE
        codes = [s.code for s in signals]

    return TriageResult(
        cart_id=cart.cart_id,
        outcome=outcome,
        reason_codes=codes + context,
        segment=segment,
        contact_stage=stage,
        caution_score=score,
    )


if __name__ == "__main__":
    rules = load_triage_rules()
    for result in (triage(c, rules) for c in load_carts()):
        print(f"{result.cart_id}  {result.outcome:<8}  {', '.join(result.reason_codes)}")
