"""End-to-end run: Rules Engine -> Offer Strategist -> Copywriter, per cart, concurrently."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel

from winback.business_rules import BusinessRules, load_business_rules
from winback.carts import Cart, load_carts
from winback.copywriter import CopyResult, load_persona, write_copy
from winback.guarded import Status
from winback.llm import LLM, load_models_config
from winback.offer_models import OfferProposal
from winback.offer_strategist import OfferResult, propose_offer
from winback.rules_engine import Outcome, TriageResult, TriageRules, load_triage_rules, triage
from winback.telemetry import Stage, Telemetry, make_engine

MAX_WORKERS = 2  # Groq free tier: keep concurrency low


class CartStatus(StrEnum):
    SKIPPED = "skipped"
    DEFERRED = "deferred"
    READY = "ready"  # offer and email passed every guardrail; waiting for the marketer
    NEEDS_ATTENTION = "needs_attention"  # a guardrail escalated; safe defaults are in place
    FAILED = "failed"  # unexpected error; the marketer sees the reason, the run continues


class CartOutcome(BaseModel):
    cart: Cart
    triage: TriageResult
    status: CartStatus
    offer: OfferResult | None = None
    email: CopyResult | None = None
    error: str | None = None


@dataclass
class Pipeline:
    triage_rules: TriageRules
    rules: BusinessRules
    persona: dict
    llm: LLM
    telemetry: Telemetry

    @classmethod
    def default(cls, telemetry: Telemetry | None = None) -> "Pipeline":
        llm = LLM(load_models_config())
        llm.client  # build the Groq client once, before worker threads share it  # noqa: B018
        return cls(
            triage_rules=load_triage_rules(),
            rules=load_business_rules(),
            persona=load_persona(),
            llm=llm,
            telemetry=telemetry or Telemetry(make_engine()),
        )

    def process(self, cart: Cart) -> CartOutcome:
        """Never raises: an unexpected error becomes a FAILED outcome with its reason."""
        result = triage(cart, self.triage_rules)
        try:
            return self._process(cart, result)
        except Exception as exc:
            self.telemetry.record(
                Stage.PIPELINE,
                CartStatus.FAILED,
                cart_id=cart.cart_id,
                payload={"error": repr(exc)[:500]},
            )
            return CartOutcome(
                cart=cart, triage=result, status=CartStatus.FAILED, error=repr(exc)[:500]
            )

    def _process(self, cart: Cart, result: TriageResult) -> CartOutcome:
        self.telemetry.record(
            Stage.TRIAGE, result.outcome, cart_id=cart.cart_id, reason_codes=result.reason_codes
        )
        if result.outcome is Outcome.SKIP:
            return CartOutcome(cart=cart, triage=result, status=CartStatus.SKIPPED)
        if result.outcome is Outcome.DEFER:
            return CartOutcome(cart=cart, triage=result, status=CartStatus.DEFERRED)

        offer = self.offer(cart, result)
        email = self.copy(cart, result, offer.proposal)
        return CartOutcome(
            cart=cart, triage=result, status=_status(offer, email), offer=offer, email=email
        )

    def offer(self, cart: Cart, result: TriageResult, feedback: str | None = None) -> OfferResult:
        return propose_offer(
            cart,
            result,
            rules=self.rules,
            llm=self.llm,
            telemetry=self.telemetry,
            feedback=feedback,
        )

    def copy(
        self,
        cart: Cart,
        result: TriageResult,
        proposal: OfferProposal,
        feedback: str | None = None,
    ) -> CopyResult:
        return write_copy(
            cart,
            result,
            proposal,
            rules=self.rules,
            persona=self.persona,
            llm=self.llm,
            telemetry=self.telemetry,
            feedback=feedback,
        )

    def run(self, carts: list[Cart]) -> Iterator[CartOutcome]:
        """Yield each cart's outcome as soon as it finishes (for streaming to the UI)."""
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = [pool.submit(self.process, cart) for cart in carts]
            for future in as_completed(futures):
                yield future.result()


def _status(offer: OfferResult, email: CopyResult) -> CartStatus:
    if Status.NEEDS_ATTENTION in (offer.status, email.status):
        return CartStatus.NEEDS_ATTENTION
    return CartStatus.READY


def main() -> None:
    pipeline = Pipeline.default()
    print(f"run {pipeline.telemetry.run_id}")
    for outcome in pipeline.run(load_carts()):
        line = f"{outcome.cart.cart_id}  {outcome.triage.outcome:<8} -> {outcome.status}"
        if outcome.offer:
            p = outcome.offer.proposal
            offers = ", ".join(f"{o.type}={o.value:g}" for o in p.offers) or "-"
            line += f"\n    {p.decision}: {offers}\n    why: {p.reason}"
        if outcome.email:
            line += f"\n    subject: {outcome.email.email.subject}"
        print(line)
    if pipeline.telemetry.failures:
        print(f"WARNING: {pipeline.telemetry.failures} telemetry writes failed")


if __name__ == "__main__":
    main()
