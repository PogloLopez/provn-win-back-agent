"""Deterministic guardrails. Each check returns violations; BLOCK ones trigger a retry."""

import re
from enum import StrEnum

from pydantic import BaseModel

from winback import placeholders
from winback.business_rules import BusinessRules, Unit
from winback.carts import Cart
from winback.copy_models import EmailDraft
from winback.offer_models import Decision, OfferProposal
from winback.rules_engine import TriageResult

MIN_REASON_CHARS = 20
MAX_SUBJECT_CHARS = 70  # prompt asks for < 60; warn with some slack
MAX_BODY_WORDS = 150  # prompt asks for 60-120
RAW_VALUE = re.compile(r"[0-9$%]")
EMOJI = re.compile(r"[\U0001F000-\U0001FAFF☀-➿⬀-⯿️]")


class Severity(StrEnum):
    BLOCK = "block"
    WARN = "warn"


class Violation(BaseModel):
    code: str
    message: str
    severity: Severity = Severity.BLOCK


def check_offer(
    proposal: OfferProposal, cart: Cart, triage: TriageResult, rules: BusinessRules
) -> list[Violation]:
    """Every rule the offer must satisfy, checked against the config and the triage result."""
    out: list[Violation] = []

    def block(code: str, message: str) -> None:
        out.append(Violation(code=code, message=message))

    if proposal.cart_id != cart.cart_id:
        block("WRONG_CART", f"cart_id must be {cart.cart_id}")

    if proposal.decision is Decision.OFFER and not proposal.offers:
        block("EMPTY_OFFER", "decision 'offer' needs at least one offer")
    if proposal.decision is not Decision.OFFER and proposal.offers:
        block("UNEXPECTED_OFFERS", f"decision '{proposal.decision}' must have no offers")

    policy = rules.segments[triage.segment]
    types = [o.type for o in proposal.offers]
    if len(types) != len(set(types)):
        block("DUPLICATE_OFFER", "each offer type may appear once")
    if len(types) > policy.max_offers:
        block("TOO_MANY_OFFERS", f"at most {policy.max_offers} offers for {triage.segment}")

    total_cost = 0.0
    for offer in proposal.offers:
        catalogue = rules.offers.get(offer.type)
        if catalogue is None or offer.type not in policy.allowed:
            block("OFFER_NOT_ALLOWED", f"{offer.type} is not allowed for {triage.segment}")
            continue
        if catalogue.level(offer.value) is None:
            block("UNKNOWN_LEVEL", f"{offer.type} has no level {offer.value}")
            continue
        if catalogue.unit is Unit.PERCENT and not (
            policy.min_discount_pct <= offer.value <= policy.max_discount_pct
        ):
            block(
                "DISCOUNT_OUT_OF_RANGE",
                f"{offer.value}% outside {policy.min_discount_pct}-{policy.max_discount_pct}%",
            )
        total_cost += rules.offer_cost(offer.type, offer.value, cart)

    cap = rules.cost_cap(triage)
    if total_cost > cap:
        block("OVER_COST_CAP", f"total cost ${total_cost:.2f} exceeds cap ${cap:.2f}")

    if len(proposal.reason.strip()) < MIN_REASON_CHARS:
        block("NO_REASON", "reason must explain the decision")
    cited = set(proposal.reason_codes_cited)
    if not cited:
        block("UNGROUNDED_REASON", "cite at least one triage reason code")
    elif unknown := cited - set(triage.reason_codes):
        block("UNGROUNDED_REASON", f"codes not in triage: {sorted(unknown)}")

    if not 0 <= proposal.confidence <= 1:
        block("BAD_CONFIDENCE", "confidence must be between 0 and 1")

    menu_costs = [o["cost_usd"] for o in rules.menu(cart, triage)]
    if proposal.offers and menu_costs and total_cost >= max(menu_costs) > min(menu_costs):
        out.append(
            Violation(
                code="MOST_EXPENSIVE_OPTION",
                message=f"${total_cost:.2f} spent although a ${min(menu_costs):.2f} option existed",
                severity=Severity.WARN,
            )
        )
    return out


def blocking(violations: list[Violation]) -> list[Violation]:
    return [v for v in violations if v.severity is Severity.BLOCK]


def check_copy(
    draft: EmailDraft, proposal: OfferProposal, persona: dict, rules: BusinessRules
) -> list[Violation]:
    """The draft may only reference what the offer granted, in the persona's voice rules."""
    out: list[Violation] = []

    def block(code: str, message: str) -> None:
        out.append(Violation(code=code, message=message))

    text = f"{draft.subject}\n{draft.body}"
    lowered = text.lower()
    used = placeholders.used(text)
    if extra := used - placeholders.allowed(proposal):
        block("UNKNOWN_PLACEHOLDER", f"not granted by the offer: {sorted(extra)}")
    if missing := placeholders.required(proposal) - used:
        block("MISSING_PLACEHOLDER", f"must include: {[f'{{{{{m}}}}}' for m in sorted(missing)]}")

    stripped = placeholders.PLACEHOLDER.sub("", text)
    if raw := sorted(set(RAW_VALUE.findall(stripped))):
        block("RAW_VALUE", f"write numbers, $ and % only through placeholders (found {raw})")
    if "{" in stripped or "}" in stripped:
        block("MALFORMED_PLACEHOLDER", "placeholders must look like {{name}}")
    if not draft.subject.strip() or not draft.body.strip():
        block("EMPTY_COPY", "subject and body are required")

    lexicon = persona["rugby_lexicon"]
    if banned := [t for t in lexicon["banned_terms"] if re.search(rf"\b{re.escape(t)}\b", lowered)]:
        block("BANNED_TERM", f"off-brand terms: {banned}")
    # Scarcity and offer keywords match substrings on purpose ("upgraded" still hints at an
    # upgrade): a false positive costs one retry, a false negative reaches a fan.
    if scarcity := [t for t in lexicon["scarcity_terms"] if t in lowered]:
        block("SCARCITY_CLAIM", f"no scarcity or deadline claims: {scarcity}")
    if EMOJI.search(text):
        block("EMOJI", "no emojis")

    granted = {o.type for o in proposal.offers}
    for name, offer in rules.offers.items():
        if name not in granted and (hits := [k for k in offer.keywords if k in lowered]):
            block("UNGRANTED_OFFER", f"mentions {name} ({hits}) but it was not offered")

    words = len(draft.body.split())
    if len(draft.subject) > MAX_SUBJECT_CHARS or words > MAX_BODY_WORDS:
        out.append(
            Violation(
                code="TOO_LONG",
                message=f"subject {len(draft.subject)} chars, body {words} words",
                severity=Severity.WARN,
            )
        )
    return out
