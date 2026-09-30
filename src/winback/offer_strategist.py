"""Offer Strategist: LLM proposes Offer.json; guardrails check it; retry, then NEEDS_ATTENTION."""

import json
from enum import StrEnum

import groq
from pydantic import BaseModel

from winback.business_rules import BusinessRules
from winback.carts import Cart
from winback.guardrails import Severity, Violation, blocking, check_offer
from winback.llm import LLM, LLMOutputError
from winback.offer_models import Decision, OfferProposal
from winback.rules_engine import TriageResult
from winback.settings import PROMPTS_DIR
from winback.telemetry import Stage, Telemetry

ROLE = "offer_strategist"
SYSTEM_PROMPT = (PROMPTS_DIR / "offer_strategist.md").read_text(encoding="utf-8")


class OfferStatus(StrEnum):
    OK = "ok"
    NEEDS_ATTENTION = "needs_attention"


class OfferAttempt(BaseModel):
    raw: str
    violations: list[Violation]


class OfferResult(BaseModel):
    cart_id: str
    status: OfferStatus
    proposal: OfferProposal  # the accepted proposal, or the safe default when escalated
    warnings: list[Violation]
    attempts: list[OfferAttempt]


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

    attempts: list[OfferAttempt] = []
    for attempt in range(1, llm.config.guardrail_retries + 2):
        try:
            proposal, raw, usage = llm.structured(ROLE, messages, OfferProposal)
            violations = check_offer(proposal, cart, triage, rules)
            telemetry.record(
                Stage.OFFER,
                "ok",
                cart_id=cart.cart_id,
                attempt=attempt,
                payload=proposal.model_dump(),
                **usage.telemetry_fields(),
            )
        except (LLMOutputError, groq.APIError) as exc:
            # Off-schema reply, or Groq still failing after transient retries.
            code = "BAD_JSON" if isinstance(exc, LLMOutputError) else "LLM_UNAVAILABLE"
            proposal, raw = None, getattr(exc, "raw", "")
            violations = [Violation(code=code, message=str(exc)[:300])]
            usage = exc.usage.telemetry_fields() if isinstance(exc, LLMOutputError) else {}
            telemetry.record(
                Stage.OFFER,
                code.lower(),
                cart_id=cart.cart_id,
                attempt=attempt,
                reason_codes=[code],
                **usage,
            )

        blockers = blocking(violations)
        if proposal is not None:
            telemetry.record(
                Stage.OFFER_GUARDRAIL,
                "fail" if blockers else "pass",
                cart_id=cart.cart_id,
                attempt=attempt,
                reason_codes=[v.code for v in violations],
            )
        attempts.append(OfferAttempt(raw=raw, violations=violations))
        if proposal is not None and not blockers:
            return OfferResult(
                cart_id=cart.cart_id,
                status=OfferStatus.OK,
                proposal=proposal,
                warnings=[v for v in violations if v.severity is Severity.WARN],
                attempts=attempts,
            )
        messages += [
            {"role": "assistant", "content": raw or "(invalid output)"},
            {
                "role": "user",
                "content": "Your proposal broke these rules. Fix them and answer again:\n"
                + "\n".join(f"- {v.code}: {v.message}" for v in blockers),
            },
        ]

    telemetry.record(
        Stage.OFFER,
        OfferStatus.NEEDS_ATTENTION,
        cart_id=cart.cart_id,
        attempt=len(attempts),
        reason_codes=sorted({v.code for a in attempts for v in a.violations}),
    )
    return OfferResult(
        cart_id=cart.cart_id,
        status=OfferStatus.NEEDS_ATTENTION,
        proposal=safe_default(cart, len(attempts)),
        warnings=[],
        attempts=attempts,
    )
