"""Offer Strategist: LLM proposes Offer.json; guardrails check it; retry, then NEEDS_ATTENTION."""

import json

from pydantic import BaseModel

from winback.business_rules import BusinessRules
from winback.carts import Cart
from winback.guarded import Attempt, Status, guarded_call
from winback.guardrails import Violation, check_offer
from winback.llm import LLM
from winback.offer_models import Decision, OfferProposal
from winback.rules_engine import TriageResult
from winback.settings import PROMPTS_DIR
from winback.telemetry import Stage, Telemetry

ROLE = "offer_strategist"
SYSTEM_PROMPT = (PROMPTS_DIR / "offer_strategist.md").read_text(encoding="utf-8")


class OfferResult(BaseModel):
    cart_id: str
    status: Status
    proposal: OfferProposal  # the accepted proposal, or the safe default when escalated
    warnings: list[Violation]
    attempts: list[Attempt]


def build_request(cart: Cart, triage: TriageResult, rules: BusinessRules) -> dict:
    policy = rules.segments[triage.segment]
    return {
        "cart": cart.model_dump(),
        "triage": triage.model_dump(),
        "policy": {
            "max_offers": policy.max_offers,
            "total_cost_cap_usd": rules.cost_cap(triage),
            "reminder_expected_value_usd": round(
                rules.reminder_conversion_rate * cart.cart_value, 2
            ),
        },
        "menu": rules.menu(cart, triage),
    }


def safe_default(cart: Cart, attempts: int) -> OfferProposal:
    return OfferProposal(
        cart_id=cart.cart_id,
        decision=Decision.REMINDER_ONLY,
        offers=[],
        reason=(
            f"Automatic fallback after {attempts} proposals broke business rules. "
            "Review before sending."
        ),
        reason_codes_cited=[],
        confidence=0.0,
    )


def propose_offer(
    cart: Cart,
    triage: TriageResult,
    *,
    rules: BusinessRules,
    llm: LLM,
    telemetry: Telemetry,
    feedback: str | None = None,
) -> OfferResult:
    """Ask for an offer, re-prompting with violations up to `guardrail_retries` times."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(build_request(cart, triage, rules))},
    ]
    if feedback:
        messages.append({"role": "user", "content": f"Marketer feedback to address: {feedback}"})

    outcome = guarded_call(
        llm=llm,
        role=ROLE,
        messages=messages,
        schema=OfferProposal,
        check=lambda proposal: check_offer(proposal, cart, triage, rules),
        telemetry=telemetry,
        cart_id=cart.cart_id,
        llm_stage=Stage.OFFER,
        guard_stage=Stage.OFFER_GUARDRAIL,
    )
    return OfferResult(
        cart_id=cart.cart_id,
        status=outcome.status,
        proposal=outcome.value or safe_default(cart, len(outcome.attempts)),
        warnings=outcome.warnings,
        attempts=outcome.attempts,
    )
