"""Copywriter: LLM drafts the email with placeholders; copy guardrails check it; then render."""

import json

from jinja2 import TemplateError
from pydantic import BaseModel

from winback import placeholders
from winback.business_rules import BusinessRules
from winback.carts import Cart
from winback.copy_models import EmailDraft
from winback.guarded import Attempt, Status, guarded_call
from winback.guardrails import Violation, check_copy
from winback.llm import LLM
from winback.offer_models import OfferProposal
from winback.rules_engine import Outcome, TriageResult
from winback.settings import PROMPTS_DIR
from winback.telemetry import Stage, Telemetry

ROLE = "copywriter"
PERSONA_PATH = PROMPTS_DIR / "seattle_seawolves_persona.json"


def load_persona() -> dict:
    return json.loads(PERSONA_PATH.read_text(encoding="utf-8"))


def system_prompt(persona: dict) -> str:
    template = (PROMPTS_DIR / "copywriter.md").read_text(encoding="utf-8")
    return template.replace("{persona}", json.dumps(persona, indent=1))


class RenderedEmail(BaseModel):
    subject: str
    body: str


class CopyResult(BaseModel):
    cart_id: str
    status: Status
    draft: EmailDraft  # the accepted draft, or the plain fallback when escalated
    email: RenderedEmail
    warnings: list[Violation]
    attempts: list[Attempt]


def build_request(
    cart: Cart, triage: TriageResult, proposal: OfferProposal, rules: BusinessRules, persona: dict
) -> dict:
    rendered = placeholders.values(cart, proposal, rules)
    return {
        "decision": proposal.decision,
        "offers": [
            {"placeholder": f"{{{{{o.type}}}}}", "what_it_is": rules.offers[o.type].description}
            for o in proposal.offers
        ],
        "cart": {"section": cart.section},
        "tone": persona["tone_by_contact_stage"][triage.contact_stage],
        "caution": triage.outcome is Outcome.CAUTION,
        "placeholders_render_as": {
            f"{{{{{p}}}}}": rendered[p] for p in sorted(placeholders.allowed(proposal))
        },
        "required_placeholders": sorted(f"{{{{{p}}}}}" for p in placeholders.required(proposal)),
    }


def fallback_draft(proposal: OfferProposal) -> EmailDraft:
    """Plain, always-valid draft so the marketer has something to edit when the LLM fails."""
    perks = "".join(f"\nWe've also added {{{{{o.type}}}}}." for o in proposal.offers)
    return EmailDraft(
        subject="Your Seawolves seats are still waiting",
        body=(
            "Hi there,\n\nYour {{seats}} in the {{section}} are still holding the line."
            f"{perks}\n\nFinish your order here: {{{{checkout_link}}}}\n\n"
            "Together We Hunt,\nSeattle Seawolves"
        ),
    )


def write_copy(
    cart: Cart,
    triage: TriageResult,
    proposal: OfferProposal,
    *,
    rules: BusinessRules,
    persona: dict,
    llm: LLM,
    telemetry: Telemetry,
    feedback: str | None = None,
) -> CopyResult:
    request = build_request(cart, triage, proposal, rules, persona)
    messages = [
        {"role": "system", "content": system_prompt(persona)},
        {"role": "user", "content": json.dumps(request)},
    ]
    if feedback:
        messages.append({"role": "user", "content": f"Marketer feedback to address: {feedback}"})

    outcome = guarded_call(
        llm=llm,
        role=ROLE,
        messages=messages,
        schema=EmailDraft,
        check=lambda draft: check_copy(
            draft, proposal, persona, rules, placeholders.values(cart, proposal, rules)
        ),
        telemetry=telemetry,
        cart_id=cart.cart_id,
        llm_stage=Stage.COPY,
        guard_stage=Stage.COPY_GUARDRAIL,
    )
    draft = outcome.value or fallback_draft(proposal)
    return CopyResult(
        cart_id=cart.cart_id,
        status=outcome.status,
        draft=draft,
        email=render_email(draft, cart, proposal, rules, telemetry),
        warnings=outcome.warnings,
        attempts=outcome.attempts,
    )


def render_email(
    draft: EmailDraft,
    cart: Cart,
    proposal: OfferProposal,
    rules: BusinessRules,
    telemetry: Telemetry,
) -> RenderedEmail:
    """Fill placeholders from the offer. Raises if the draft references a missing value."""
    context = placeholders.values(cart, proposal, rules)
    try:
        email = RenderedEmail(
            subject=placeholders.render(draft.subject, context),
            body=placeholders.render(draft.body, context),
        )
    except TemplateError as exc:
        telemetry.record(Stage.RENDER, "fail", cart_id=cart.cart_id, payload={"error": str(exc)})
        raise
    telemetry.record(Stage.RENDER, "ok", cart_id=cart.cart_id)
    return email
