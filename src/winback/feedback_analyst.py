"""Feedback Analyst: classifies marketer feedback and text edits into a fixed taxonomy."""

import json
from enum import StrEnum

from winback.carts import Cart
from winback.copy_models import EmailDraft
from winback.guarded import Guarded, guarded_call
from winback.guardrails import Violation
from winback.llm import LLM
from winback.offer_models import OfferProposal
from winback.rules_engine import Strict, TriageResult
from winback.settings import PROMPTS_DIR
from winback.telemetry import Stage, Telemetry

ROLE = "feedback_analyst"
SYSTEM_PROMPT = (PROMPTS_DIR / "feedback_analyst.md").read_text(encoding="utf-8")


class FeedbackCategory(StrEnum):
    OFFER_TOO_GENEROUS = "offer_too_generous"
    OFFER_TOO_WEAK = "offer_too_weak"
    WRONG_OFFER_TYPE = "wrong_offer_type"
    TONE_OFF = "tone_off"
    FACTUAL_ERROR = "factual_error"
    OFF_BRAND = "off_brand"
    SHOULD_NOT_CONTACT = "should_not_contact"
    OTHER = "other"


class Target(StrEnum):
    OFFER_STRATEGIST = "offer_strategist"
    COPYWRITER = "copywriter"
    TRIAGE = "triage"
    BUSINESS_RULES = "business_rules"
    PERSONA = "persona"


class FeedbackSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FeedbackAnalysis(Strict):
    feedback_category: FeedbackCategory
    target_component: Target
    severity: FeedbackSeverity
    summary: str
    instruction: str


ROUTABLE = {Target.OFFER_STRATEGIST, Target.COPYWRITER}


def _check(analysis: FeedbackAnalysis) -> list[Violation]:
    if analysis.target_component in ROUTABLE and not analysis.instruction.strip():
        return [Violation(code="NO_INSTRUCTION", message="agent targets need an instruction")]
    return []


def analyze(
    *,
    cart: Cart,
    triage: TriageResult,
    proposal: OfferProposal,
    llm: LLM,
    telemetry: Telemetry,
    feedback: str | None = None,
    before: EmailDraft | None = None,
    after: EmailDraft | None = None,
) -> Guarded[FeedbackAnalysis]:
    """Classify free-text feedback, or a text edit (before -> after)."""
    if not feedback and not (before and after):
        raise ValueError("pass feedback text, or both before and after drafts")
    request = {
        "kind": "feedback" if feedback else "text_edit",
        "feedback": feedback,
        "before": before.model_dump() if before else None,
        "after": after.model_dump() if after else None,
        "offer": proposal.model_dump(mode="json"),
        "cart": cart.model_dump(),
        "triage": triage.model_dump(mode="json"),
    }
    return guarded_call(
        llm=llm,
        role=ROLE,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(request)},
        ],
        schema=FeedbackAnalysis,
        check=_check,
        telemetry=telemetry,
        cart_id=cart.cart_id,
        llm_stage=Stage.FEEDBACK,
        guard_stage=Stage.FEEDBACK,
    )
