"""Offer Strategist output contract (Offer.json). Strict: every field required, no extras."""

from enum import StrEnum

from winback.rules_engine import Strict


class Decision(StrEnum):
    OFFER = "offer"
    REMINDER_ONLY = "reminder_only"
    NO_OFFER = "no_offer"


class ProposedOffer(Strict):
    type: str
    value: float


class OfferProposal(Strict):
    cart_id: str
    decision: Decision
    offers: list[ProposedOffer]
    reason: str
    reason_codes_cited: list[str]
    confidence: float
