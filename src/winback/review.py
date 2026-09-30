"""Marketer review: runs and cards persisted, plus approve / reject / edit / feedback actions."""

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from pydantic import BaseModel
from sqlalchemy import JSON, Column, DateTime
from sqlalchemy.engine import Engine
from sqlmodel import Field, Session, SQLModel, select

from winback import placeholders
from winback.carts import Cart, load_carts
from winback.copy_models import EmailDraft
from winback.copywriter import render_email
from winback.feedback_analyst import FeedbackAnalysis, FeedbackCategory, Target, analyze
from winback.guarded import Status
from winback.guardrails import Violation, blocking, check_copy, check_offer
from winback.offer_models import Decision, OfferProposal, ProposedOffer
from winback.pipeline import CartOutcome, CartStatus, Pipeline, _status
from winback.telemetry import Stage, Telemetry

MIN_SECONDS_BETWEEN_RUNS = 20  # the public demo spends the Groq free tier

REJECT_REASONS = {
    "too_generous": FeedbackCategory.OFFER_TOO_GENEROUS,
    "wrong_tone": FeedbackCategory.TONE_OFF,
    "should_not_contact": FeedbackCategory.SHOULD_NOT_CONTACT,
    "other": FeedbackCategory.OTHER,
}


class Review(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


def _now() -> datetime:
    return datetime.now(UTC)


class Run(SQLModel, table=True):
    __tablename__ = "runs"

    id: str = Field(primary_key=True)
    created_at: datetime = Field(default_factory=_now, sa_column=Column(DateTime(timezone=True)))


class Card(SQLModel, table=True):
    __tablename__ = "cards"

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    cart_id: str
    review: str = Review.PENDING
    reject_reason: str | None = None
    outcome: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    updated_at: datetime = Field(default_factory=_now, sa_column=Column(DateTime(timezone=True)))


class TooManyRuns(Exception):
    pass


class ActionBlocked(Exception):
    """The marketer's change breaks a guardrail; the UI shows the violations."""

    def __init__(self, violations: list[Violation]):
        super().__init__("; ".join(v.message for v in violations))
        self.violations = violations


class FeedbackResult(BaseModel):
    card: dict[str, Any]
    analysis: FeedbackAnalysis | None
    routed_to: Target | None
    note: str


class ReviewService:
    def __init__(self, engine: Engine, pipeline_factory: Callable[[Telemetry], Pipeline]):
        self.engine = engine
        self.pipeline_factory = pipeline_factory
        SQLModel.metadata.create_all(engine)

    # ---- runs -------------------------------------------------------------------------------
    def start_run(self) -> str:
        with Session(self.engine) as session:
            last = session.exec(select(Run).order_by(Run.created_at.desc())).first()
            if last and _now() - _aware(last.created_at) < timedelta(
                seconds=MIN_SECONDS_BETWEEN_RUNS
            ):
                raise TooManyRuns(f"wait {MIN_SECONDS_BETWEEN_RUNS}s between demo runs")
            run = Run(id=uuid.uuid4().hex[:12])
            session.add(run)
            session.commit()
            return run.id

    def stream_run(self, run_id: str, carts: list[Cart] | None = None) -> Iterator[dict]:
        """Run the pipeline and yield each saved card as soon as its cart finishes."""
        pipeline = self.pipeline_factory(Telemetry(self.engine, run_id))
        for outcome in pipeline.run(carts or load_carts()):
            yield self._save(Card(run_id=run_id, cart_id=outcome.cart.cart_id), outcome)

    def cards(self, run_id: str) -> list[dict]:
        with Session(self.engine) as session:
            rows = session.exec(select(Card).where(Card.run_id == run_id).order_by(Card.id))
            return [_view(c) for c in rows]

    # ---- actions ----------------------------------------------------------------------------
    def approve(self, card_id: int) -> dict:
        card, outcome, pipeline = self._load(card_id)
        if outcome.status not in (CartStatus.READY, CartStatus.NEEDS_ATTENTION):
            raise ActionBlocked([Violation(code="NOTHING_TO_SEND", message="no email to approve")])
        # Cheap insurance: what gets approved must still pass every guardrail.
        if outcome.offer and outcome.email:
            problems = blocking(
                check_copy(
                    outcome.email.draft,
                    outcome.offer.proposal,
                    pipeline.persona,
                    pipeline.rules,
                    placeholders.values(outcome.cart, outcome.offer.proposal, pipeline.rules),
                )
            )
            if outcome.offer.status is Status.OK:
                problems += blocking(
                    check_offer(
                        outcome.offer.proposal,
                        outcome.cart,
                        outcome.triage,
                        pipeline.rules,
                        check_reason=False,
                    )
                )
            if problems:
                raise ActionBlocked(problems)
        card.review = Review.APPROVED
        self._ui_event(pipeline, card, "approve")
        return self._save(card, outcome)

    def reject(self, card_id: int, reason: str) -> dict:
        if reason not in REJECT_REASONS:
            raise ActionBlocked([Violation(code="BAD_REASON", message=f"unknown reason {reason}")])
        card, outcome, pipeline = self._load(card_id)
        card.review, card.reject_reason = Review.REJECTED, reason
        self._ui_event(pipeline, card, "reject", [REJECT_REASONS[reason]])
        return self._save(card, outcome)

    def edit(
        self,
        card_id: int,
        offers: list[ProposedOffer] | None = None,
        subject: str | None = None,
        body: str | None = None,
    ) -> dict:
        """Edit offer values and/or text. Both are re-checked by the same guardrails as the AI.

        Telemetry is written only after every check passes, and the card goes back to pending:
        the marketer must approve what they now see.
        """
        card, outcome, pipeline = self._load(card_id)
        if outcome.offer is None or outcome.email is None:
            raise ActionBlocked(
                [Violation(code="NOTHING_TO_EDIT", message="no offer on this card")]
            )
        if any(t is not None and not t.strip() for t in (subject, body)):
            raise ActionBlocked([Violation(code="EMPTY_COPY", message="text cannot be empty")])
        cart, result = outcome.cart, outcome.triage
        old, old_draft = outcome.offer.proposal, outcome.email.draft

        proposal, offer_warnings = old, outcome.offer.warnings
        offer_changed = offers is not None and offers != old.offers
        if offer_changed:
            decision = Decision.OFFER if offers else Decision.REMINDER_ONLY
            reason = f"Edited by the marketer. Original: {old.reason}"
            proposal = old.model_copy(
                update={"offers": offers, "decision": decision, "reason": reason}
            )
            violations = check_offer(proposal, cart, result, pipeline.rules, check_reason=False)
            if blocked := blocking(violations):
                raise ActionBlocked(blocked)
            offer_warnings = [v for v in violations if v not in blocked]

        draft = EmailDraft(
            subject=subject if subject is not None else old_draft.subject,
            body=body if body is not None else old_draft.body,
        )
        text_changed = draft != old_draft
        values = placeholders.values(cart, proposal, pipeline.rules)
        copy_violations = blocking(
            check_copy(draft, proposal, pipeline.persona, pipeline.rules, values)
        )
        if copy_violations and (text_changed or not offer_changed):
            raise ActionBlocked(copy_violations)
        if copy_violations:
            # New offer, untouched wording that no longer fits it: the Copywriter rewrites.
            email = pipeline.copy(
                cart, result, proposal, feedback="The marketer changed the offer."
            )
        else:
            rendered = render_email(draft, cart, proposal, pipeline.rules, pipeline.telemetry)
            email = outcome.email.model_copy(
                update={"draft": draft, "email": rendered, "status": Status.OK}
            )

        if offer_changed:
            category = _value_edit_category(old, proposal, cart, pipeline)
            self._ui_event(pipeline, card, "edit_offer", [category], _offer_diff(old, proposal))
        if text_changed:
            analysis = analyze(
                cart=cart,
                triage=result,
                proposal=proposal,
                llm=pipeline.llm,
                telemetry=pipeline.telemetry,
                before=old_draft,
                after=draft,
            ).value
            codes = [analysis.feedback_category] if analysis else ["feedback_unclassified"]
            self._ui_event(pipeline, card, "edit_text", codes)

        offer_status = Status.OK if offer_changed else outcome.offer.status
        offer = outcome.offer.model_copy(
            update={"proposal": proposal, "status": offer_status, "warnings": offer_warnings}
        )
        updated = outcome.model_copy(
            update={"offer": offer, "email": email, "status": _status(offer, email)}
        )
        card.review, card.reject_reason = Review.PENDING, None
        return self._save(card, updated)

    def feedback(self, card_id: int, text: str) -> FeedbackResult:
        """Classify the feedback, then regenerate with the agent it targets."""
        card, outcome, pipeline = self._load(card_id)
        if outcome.offer is None:
            raise ActionBlocked(
                [Violation(code="NOTHING_TO_EDIT", message="no offer on this card")]
            )
        cart, result = outcome.cart, outcome.triage
        guarded = analyze(
            cart=cart,
            triage=result,
            proposal=outcome.offer.proposal,
            llm=pipeline.llm,
            telemetry=pipeline.telemetry,
            feedback=text,
        )
        analysis = guarded.value
        if analysis is None:
            note = "The feedback could not be classified; it was logged for review."
            return FeedbackResult(card=_view(card), analysis=None, routed_to=None, note=note)

        instruction = f"{text}\nAnalyst instruction: {analysis.instruction}"
        target = analysis.target_component
        if target is Target.OFFER_STRATEGIST:
            offer = pipeline.offer(cart, result, feedback=instruction)
            email = pipeline.copy(cart, result, offer.proposal)
        elif target is Target.COPYWRITER:
            offer = outcome.offer
            email = pipeline.copy(cart, result, offer.proposal, feedback=instruction)
        else:
            self._ui_event(pipeline, card, "feedback_logged", [analysis.feedback_category])
            note = f"Logged for the team: {analysis.summary} (affects {target})."
            return FeedbackResult(card=_view(card), analysis=analysis, routed_to=None, note=note)

        self._ui_event(pipeline, card, "feedback", [analysis.feedback_category, target])
        updated = outcome.model_copy(
            update={"offer": offer, "email": email, "status": _status(offer, email)}
        )
        card.review, card.reject_reason = Review.PENDING, None
        note = f"Sent to the {target.replace('_', ' ')}: {analysis.instruction}"
        return FeedbackResult(
            card=self._save(card, updated), analysis=analysis, routed_to=target, note=note
        )

    def options(self, card_id: int) -> dict:
        """Everything the edit form needs: allowed values and caps for this cart."""
        _, outcome, pipeline = self._load(card_id)
        policy = pipeline.rules.segments[outcome.triage.segment]
        return {
            "menu": pipeline.rules.menu(outcome.cart, outcome.triage),
            "max_offers": policy.max_offers,
            "total_cost_cap_usd": pipeline.rules.cost_cap(outcome.triage),
            "placeholders": sorted(
                placeholders.allowed(outcome.offer.proposal) if outcome.offer else []
            ),
        }

    # ---- helpers ----------------------------------------------------------------------------
    def _load(self, card_id: int) -> tuple[Card, CartOutcome, Pipeline]:
        with Session(self.engine) as session:
            card = session.get(Card, card_id)
        if card is None:
            raise KeyError(card_id)
        pipeline = self.pipeline_factory(Telemetry(self.engine, card.run_id))
        return card, CartOutcome.model_validate(card.outcome), pipeline

    def _save(self, card: Card, outcome: CartOutcome) -> dict:
        card.outcome = outcome.model_dump(mode="json")
        card.updated_at = _now()
        with Session(self.engine) as session:
            session.add(card)
            session.commit()
            session.refresh(card)
            return _view(card)

    @staticmethod
    def _ui_event(
        pipeline: Pipeline,
        card: Card,
        action: str,
        codes: list[str] | None = None,
        payload: dict | None = None,
    ) -> None:
        pipeline.telemetry.record(
            Stage.UI_ACTION,
            action,
            cart_id=card.cart_id,
            reason_codes=[str(c) for c in codes or []],
            payload=payload or {},
        )


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)  # SQLite drops tzinfo


def _view(card: Card) -> dict:
    return {
        "id": card.id,
        "run_id": card.run_id,
        "cart_id": card.cart_id,
        "review": card.review,
        "reject_reason": card.reject_reason,
        **card.outcome,
    }


def _cost(proposal: OfferProposal, cart: Cart, pipeline: Pipeline) -> float:
    return sum(pipeline.rules.offer_cost(o.type, o.value, cart) for o in proposal.offers)


def _value_edit_category(
    old: OfferProposal, new: OfferProposal, cart: Cart, pipeline: Pipeline
) -> FeedbackCategory:
    """Structured edits are classified in code, no LLM needed (D-013)."""
    if {o.type for o in old.offers} != {o.type for o in new.offers}:
        return FeedbackCategory.WRONG_OFFER_TYPE
    before, after = _cost(old, cart, pipeline), _cost(new, cart, pipeline)
    if after < before:
        return FeedbackCategory.OFFER_TOO_GENEROUS
    if after > before:
        return FeedbackCategory.OFFER_TOO_WEAK
    return FeedbackCategory.OTHER


def _offer_diff(old: OfferProposal, new: OfferProposal) -> dict:
    return {
        "before": [o.model_dump() for o in old.offers],
        "after": [o.model_dump() for o in new.offers],
    }
