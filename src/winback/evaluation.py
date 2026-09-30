"""Baselines vs pipeline: what do the Rules Engine, business rules and guardrails actually add?

Three systems on the same carts, scored by the same deterministic checks:
- plain LLM: one call, incentive names only, no rules
- LLM + rules in the prompt: the same call with both rule files pasted in, no code checks
- pipeline: the full system
Run: uv run python -m winback.evaluation --runs 3
"""

import argparse
import json
import statistics
import time
from collections import Counter
from datetime import UTC, datetime

from pydantic import BaseModel

from winback.business_rules import BusinessRules, load_business_rules
from winback.carts import Cart, load_carts
from winback.guardrails import blocking, check_offer
from winback.llm import LLM, load_models_config
from winback.offer_models import Decision, OfferProposal, ProposedOffer
from winback.pipeline import CartStatus, Pipeline
from winback.rules_engine import Outcome, Strict, load_triage_rules, triage
from winback.settings import CONFIG_DIR, PROMPTS_DIR, ROOT
from winback.telemetry import Stage, Telemetry, make_engine

BASELINE_PROMPT = (PROMPTS_DIR / "baseline.md").read_text(encoding="utf-8")
RULES_APPENDIX = "\n\n## Club rules you must follow\n\n" + "\n\n".join(
    f"`{name}`:\n```yaml\n{(CONFIG_DIR / name).read_text(encoding='utf-8')}```"
    for name in ("triage_rules.yaml", "business_rules.yaml")
)
REPORT_PATH = ROOT / "docs" / "evaluation.md"
PLAIN, PROMPTED, PIPELINE = (
    "Plain LLM",
    "LLM + rules in the prompt",
    "Pipeline (rules + guardrails)",
)


class BaselineCart(Strict):
    cart_id: str
    contact: bool
    offers: list[ProposedOffer]
    reason: str


class BaselineRun(Strict):
    carts: list[BaselineCart]


class Decided(BaseModel):
    """One cart's final decision, from any system, in a comparable shape."""

    cart_id: str
    contact: bool
    offers: list[ProposedOffer]


class Score(BaseModel):
    contacted: int
    contacted_skipped: list[str]  # the Rules Engine never contacts these (consent, reseller...)
    contacted_too_early: list[str]  # the Rules Engine waits on these (DEFER)
    policy_violations: dict[str, list[str]]  # cart -> blocking guardrail codes
    incentive_cost_usd: float
    escalated: int = 0  # pipeline only: NEEDS_ATTENTION or failed


def incentive_cost(offers: list[ProposedOffer], cart: Cart, rules: BusinessRules) -> float:
    """Face-value cost of the offers, also for values outside the catalogue."""
    total = 0.0
    for offer in offers:
        catalogue = rules.offers.get(offer.type)
        if catalogue is None:
            continue
        try:
            total += rules.offer_cost(offer.type, offer.value, cart)
        except ValueError:  # a flag offer with an off-catalogue value: price its dearest level
            total += max((lvl.cost_usd or 0) for lvl in catalogue.levels)
    return round(total, 2)


def score(decisions: list[Decided], carts: dict[str, Cart], rules: BusinessRules) -> Score:
    triage_rules = load_triage_rules()
    skipped, early, violations, cost, contacted = [], [], {}, 0.0, 0
    for decided in decisions:
        if not decided.contact:
            continue
        cart = carts[decided.cart_id]
        result = triage(cart, triage_rules)
        contacted += 1
        cost += incentive_cost(decided.offers, cart, rules)
        if result.outcome is Outcome.SKIP:
            skipped.append(f"{cart.cart_id} ({result.reason_codes[0]})")
            continue
        if result.outcome is Outcome.DEFER:
            early.append(f"{cart.cart_id} ({result.reason_codes[0]})")
            continue
        proposal = OfferProposal(
            cart_id=cart.cart_id,
            decision=Decision.OFFER if decided.offers else Decision.REMINDER_ONLY,
            offers=decided.offers,
            reason="(not scored)",
            reason_codes_cited=[],
            confidence=0.5,
        )
        checked = check_offer(proposal, cart, result, rules, check_reason=False)
        if codes := sorted({v.code for v in blocking(checked)}):
            violations[cart.cart_id] = codes
    return Score(
        contacted=contacted,
        contacted_skipped=skipped,
        contacted_too_early=early,
        policy_violations=violations,
        incentive_cost_usd=round(cost, 2),
    )


def baseline_decisions(
    carts: list[Cart], llm: LLM, *, with_rules: bool = False, telemetry: Telemetry | None = None
) -> list[Decided]:
    """One LLM call over all carts. Raises if it drops, repeats or invents a cart."""
    messages = [
        {"role": "system", "content": BASELINE_PROMPT + (RULES_APPENDIX if with_rules else "")},
        {"role": "user", "content": json.dumps([c.model_dump() for c in carts])},
    ]
    run, _, usage = llm.structured("baseline", messages, BaselineRun)
    if telemetry:
        status = "baseline_with_rules" if with_rules else "baseline"
        telemetry.record(Stage.OFFER, status, payload=run.model_dump(), **usage.telemetry_fields())
    returned = [c.cart_id for c in run.carts]
    if sorted(returned) != sorted(c.cart_id for c in carts):
        raise ValueError(f"baseline returned carts {returned}, expected one per input cart")
    return [Decided(cart_id=c.cart_id, contact=c.contact, offers=c.offers) for c in run.carts]


def pipeline_decisions(carts: list[Cart], pipeline: Pipeline) -> tuple[list[Decided], int]:
    decided, escalated = [], 0
    for outcome in pipeline.run(carts):
        if outcome.status in (CartStatus.NEEDS_ATTENTION, CartStatus.FAILED):
            escalated += 1
        contact = outcome.status in (CartStatus.READY, CartStatus.NEEDS_ATTENTION)
        offers = outcome.offer.proposal.offers if outcome.offer else []
        decided.append(Decided(cart_id=outcome.cart.cart_id, contact=contact, offers=offers))
    return decided, escalated


def telemetry_summary(engine) -> str:
    """Guardrail outcomes over every run recorded in the events table, as markdown."""
    from sqlmodel import Session, select

    from winback.telemetry import Event

    stages = [Stage.OFFER_GUARDRAIL.value, Stage.COPY_GUARDRAIL.value]
    with Session(engine) as session:
        rows = session.exec(select(Event).where(Event.stage.in_(stages))).all()
        escalated = session.exec(select(Event).where(Event.status == "needs_attention")).all()
    lines = ["| Check | Attempts checked | Blocked | Top reasons |", "|---|---|---|---|"]
    for stage in stages:
        checked = [r for r in rows if r.stage == stage]
        failed = [r for r in checked if r.status == "fail"]
        reasons = Counter(c for r in failed for c in r.reason_codes).most_common(4)
        top = ", ".join(f"{code} x{n}" for code, n in reasons) or "none"
        share = f" ({len(failed) / len(checked):.0%})" if checked else ""
        lines.append(f"| {stage} | {len(checked)} | {len(failed)}{share} | {top} |")
    by_stage = Counter(r.stage for r in escalated)
    lines.append("")
    lines.append(
        "Escalated to the marketer after all retries: "
        + (", ".join(f"{stage} x{n}" for stage, n in by_stage.items()) or "none")
        + "."
    )
    return "\n".join(lines)


def report(
    systems: dict[str, list[Score]], runs: int, cart_count: int, guardrails: str = ""
) -> str:
    def mean(values) -> str:
        return f"{statistics.mean(values):.1f}"

    def row(name: str, scores: list[Score]) -> str:
        cost = [s.incentive_cost_usd for s in scores]
        cells = [
            mean(s.contacted for s in scores),
            mean(len(s.contacted_skipped) for s in scores),
            mean(len(s.contacted_too_early) for s in scores),
            mean(len(s.policy_violations) for s in scores),
            f"${statistics.mean(cost):.2f} (${min(cost):.2f}-${max(cost):.2f})",
            mean(s.escalated for s in scores),
        ]
        return f"| {name} | " + " | ".join(cells) + " |"

    def mistakes(scores: list[Score]) -> str:
        counter = Counter(c for s in scores for cs in s.policy_violations.values() for c in cs)
        contacted = Counter(w for s in scores for w in s.contacted_skipped + s.contacted_too_early)
        parts = [f"{code} x{n}" for code, n in counter.most_common()]
        parts += [f"contacted {w} x{n}" for w, n in contacted.most_common()]
        return ", ".join(parts) or "none"

    header = (
        "| System | Carts contacted | Contacted a skipped cart | Contacted too early "
        "| Carts breaking offer rules | Incentive cost | Escalated to marketer |\n"
        "|---|---|---|---|---|---|---|"
    )
    rows = "\n".join(row(name, scores) for name, scores in systems.items())
    notes = "\n".join(f"- **{name}**: {mistakes(scores)}" for name, scores in systems.items())
    return f"""# Evaluation

Generated by `uv run python -m winback.evaluation --runs {runs}` on {datetime.now(UTC).date()}.
Method: [[architecture#Evaluation]].

Three systems see the same {cart_count} carts, all on the Offer Strategist's model, and are
scored by the same deterministic checks. Numbers are means over {runs} runs.

- **{PLAIN}**: one call; `prompts/baseline.md` names the incentives but gives no rules.
- **{PROMPTED}**: the same call with `triage_rules.yaml` and `business_rules.yaml` pasted into
  the prompt. This isolates what the code adds beyond good prompting.
- **{PIPELINE}**: the full system.

{header}
{rows}

- **Contacted a skipped cart**: the Rules Engine never contacts it (e.g. no email consent).
- **Contacted too early**: the Rules Engine waits (abandoned under the minimum delay).
- **Breaking offer rules**: offer type, level, discount range, count or total $ cap outside the
  business rules for that fan. An offer of an unknown type or level skips the $ cap check, so
  this count is conservative.
- **Incentive cost**: face value with the illustrative business rules, as if every contacted
  fan redeemed. Contacting a cart the rules would hold back also adds its incentive cost.
- **Escalated**: pipeline carts where the guardrails gave up (safe default) or processing failed.

Mistakes across all runs:

{notes}

## Guardrail catches in live telemetry

Every attempt the guardrails checked across all runs recorded in the `events` table (demo,
evaluation and test runs), so it includes attempts that were retried and then passed.

{guardrails or "(no telemetry available)"}

## Caveat

**Read this with care.** The checks are the club's own rules, so the pipeline passes them by
construction. What the table shows is how often a model breaks those rules when nothing
enforces them, even when it is told them, and what it gives away. It says nothing about
whether any system's offers convert better; that needs real send and purchase data (online
metrics in [[architecture#Evaluation]]).
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--pause", type=float, default=20, help="seconds between LLM systems")
    args = parser.parse_args()

    carts = load_carts()
    by_id = {c.cart_id: c for c in carts}
    rules = load_business_rules()
    llm = LLM(load_models_config())
    telemetry = Telemetry(make_engine(), run_id=f"eval-{datetime.now(UTC):%Y%m%d%H%M%S}")

    systems: dict[str, list[Score]] = {PLAIN: [], PROMPTED: [], PIPELINE: []}
    for i in range(args.runs):
        for name, with_rules in ((PLAIN, False), (PROMPTED, True)):
            time.sleep(args.pause)  # stay under the Groq free tier tokens-per-minute cap
            decided = baseline_decisions(carts, llm, with_rules=with_rules, telemetry=telemetry)
            systems[name].append(score(decided, by_id, rules))
        decided, escalated = pipeline_decisions(carts, Pipeline.default(telemetry))
        systems[PIPELINE].append(
            score(decided, by_id, rules).model_copy(update={"escalated": escalated})
        )
        print(
            f"run {i + 1}/{args.runs}: "
            + " | ".join(
                f"{name}: {scores[-1].incentive_cost_usd}" for name, scores in systems.items()
            )
        )

    text = report(systems, args.runs, len(carts), telemetry_summary(telemetry.engine))
    REPORT_PATH.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
