import itertools

import pytest

from tests.fakes import FakeChatClient
from tests.test_copy import GOOD as GOOD_COPY
from tests.test_feedback_analyst import ANALYSIS
from tests.test_pipeline import CARTS, OFFER_1001
from winback.business_rules import load_business_rules
from winback.copywriter import load_persona
from winback.llm import LLM, load_models_config
from winback.offer_models import ProposedOffer
from winback.pipeline import Pipeline
from winback.review import ActionBlocked, Review, ReviewService, TooManyRuns
from winback.rules_engine import load_triage_rules
from winback.telemetry import Telemetry, make_engine


class Harness:
    """ReviewService over in-memory SQLite, with one fake Groq client shared by every pipeline."""

    def __init__(self, replies, db_path):
        self.client = FakeChatClient(replies)
        # A file DB: pipeline threads and card writes use separate connections, like Postgres.
        self.engine = make_engine(f"sqlite:///{db_path}")
        self.service = ReviewService(self.engine, self.pipeline)

    def pipeline(self, telemetry: Telemetry) -> Pipeline:
        return Pipeline(
            triage_rules=load_triage_rules(),
            rules=load_business_rules(),
            persona=load_persona(),
            llm=LLM(load_models_config(), self.client),
            telemetry=telemetry,
        )

    def run(self, cart_ids=("C-1001", "C-1003")):
        run_id = self.service.start_run()
        cards = list(self.service.stream_run(run_id, [CARTS[c] for c in cart_ids]))
        return run_id, {c["cart_id"]: c for c in cards}

    def events(self, run_id, **filters):
        return Telemetry(self.engine, run_id).events(**filters)


_db_ids = itertools.count()


@pytest.fixture
def harness(tmp_path):
    return lambda replies: Harness(replies, tmp_path / f"review{next(_db_ids)}.db")


def test_run_saves_a_card_per_cart(harness):
    h = harness([OFFER_1001, GOOD_COPY])
    run_id, cards = h.run()
    assert cards["C-1001"]["status"] == "ready"
    assert cards["C-1003"]["status"] == "skipped"
    assert {c["cart_id"] for c in h.service.cards(run_id)} == {"C-1001", "C-1003"}


def test_runs_are_rate_limited(harness):
    h = harness([])
    h.service.start_run()
    with pytest.raises(TooManyRuns):
        h.service.start_run()


def test_approve_and_reject_are_recorded(harness):
    h = harness([OFFER_1001, GOOD_COPY])
    run_id, cards = h.run()
    assert h.service.approve(cards["C-1001"]["id"])["review"] == Review.APPROVED
    rejected = h.service.reject(cards["C-1001"]["id"], "too_generous")
    assert (rejected["review"], rejected["reject_reason"]) == ("rejected", "too_generous")
    actions = h.events(run_id, stage="ui_action")
    assert [(e.status, e.reason_codes) for e in actions] == [
        ("approve", []),
        ("reject", ["offer_too_generous"]),
    ]


def test_skipped_cart_cannot_be_approved(harness):
    h = harness([OFFER_1001, GOOD_COPY])
    _, cards = h.run()
    with pytest.raises(ActionBlocked):
        h.service.approve(cards["C-1003"]["id"])


def test_value_edit_is_guarded_and_classified_in_code(harness):
    h = harness([OFFER_1001, GOOD_COPY])
    run_id, cards = h.run()
    card_id = cards["C-1001"]["id"]
    with pytest.raises(ActionBlocked) as blocked:
        h.service.edit(card_id, offers=[ProposedOffer(type="discount_pct", value=30)])
    assert blocked.value.violations[0].code == "DISCOUNT_OUT_OF_RANGE"

    edited = h.service.edit(card_id, offers=[ProposedOffer(type="discount_pct", value=5)])
    assert "5% off your order" in edited["email"]["email"]["body"]
    event = h.events(run_id, stage="ui_action")[0]
    assert (event.status, event.reason_codes) == ("edit_offer", ["offer_too_generous"])


def test_text_edit_with_raw_value_is_blocked(harness):
    h = harness([OFFER_1001, GOOD_COPY])
    _, cards = h.run()
    with pytest.raises(ActionBlocked) as blocked:
        h.service.edit(
            cards["C-1001"]["id"], body="Get 10% off! {{checkout_link}} {{discount_pct}}"
        )
    assert blocked.value.violations[0].code == "RAW_VALUE"


def test_text_edit_is_rendered_and_analyzed(harness):
    tone = ANALYSIS | {"feedback_category": "tone_off", "target_component": "copywriter"}
    h = harness([OFFER_1001, GOOD_COPY, tone])
    run_id, cards = h.run()
    body = GOOD_COPY["body"].replace("Hi there", "Hello friend")
    edited = h.service.edit(cards["C-1001"]["id"], body=body)
    assert edited["email"]["email"]["body"].startswith("Hello friend")
    assert h.events(run_id, stage="ui_action")[-1].reason_codes == ["tone_off"]


def test_feedback_routes_to_offer_strategist_and_regenerates(harness):
    perk = OFFER_1001 | {"offers": [{"type": "early_entry", "value": 1}]}
    h = harness([OFFER_1001, GOOD_COPY, ANALYSIS, perk, GOOD_COPY | {"body": _perk_body()}])
    _, cards = h.run()
    result = h.service.feedback(cards["C-1001"]["id"], "Too generous, give a perk")
    assert result.routed_to == "offer_strategist"
    assert result.card["offer"]["proposal"]["offers"] == [{"type": "early_entry", "value": 1.0}]
    assert "Analyst instruction" in h.client.requests[3]["messages"][-1]["content"]


def test_feedback_about_rules_is_logged_not_regenerated(harness):
    rules = ANALYSIS | {"target_component": "business_rules", "instruction": ""}
    h = harness([OFFER_1001, GOOD_COPY, rules])
    _, cards = h.run()
    result = h.service.feedback(cards["C-1001"]["id"], "Loyal fans should never get discounts")
    assert result.routed_to is None
    assert "Logged for the team" in result.note
    assert len(h.client.requests) == 3


def _perk_body() -> str:
    return "Hi there, we've added {{early_entry}} for you. {{checkout_link}}"


def test_edit_resets_review_to_pending(harness):
    h = harness([OFFER_1001, GOOD_COPY])
    _, cards = h.run()
    card_id = cards["C-1001"]["id"]
    h.service.reject(card_id, "too_generous")
    edited = h.service.edit(card_id, offers=[ProposedOffer(type="discount_pct", value=5)])
    assert (edited["review"], edited["reject_reason"]) == ("pending", None)


def test_offer_edit_regenerates_copy_when_old_wording_no_longer_fits(harness):
    perk_copy = GOOD_COPY | {"body": _perk_body()}
    h = harness([OFFER_1001, GOOD_COPY, perk_copy])
    _, cards = h.run()
    edited = h.service.edit(
        cards["C-1001"]["id"], offers=[ProposedOffer(type="early_entry", value=1)]
    )
    assert "early entry" in edited["email"]["email"]["body"]
    assert "The marketer changed the offer." in h.client.requests[2]["messages"][-1]["content"]


def test_blocked_text_in_a_combined_edit_records_nothing(harness):
    h = harness([OFFER_1001, GOOD_COPY])
    run_id, cards = h.run()
    with pytest.raises(ActionBlocked):
        h.service.edit(
            cards["C-1001"]["id"],
            offers=[ProposedOffer(type="discount_pct", value=5)],
            body="Now 5% off! {{checkout_link}} {{discount_pct}}",
        )
    assert h.events(run_id, stage="ui_action") == []


def test_fixing_a_needs_attention_offer_clears_the_flag(harness):
    from tests.test_offer_strategist import BAD as BAD_OFFER

    reminder_copy = GOOD_COPY | {"body": "Hi there, your {{seats}} are waiting. {{checkout_link}}"}
    h = harness([BAD_OFFER, BAD_OFFER, BAD_OFFER, reminder_copy, ANALYSIS])
    _, cards = h.run(("C-1001",))
    assert cards["C-1001"]["status"] == "needs_attention"
    approved = h.service.approve(cards["C-1001"]["id"])  # the safe default can still be sent
    assert approved["review"] == "approved"
    fixed = h.service.edit(
        cards["C-1001"]["id"],
        offers=[ProposedOffer(type="early_entry", value=1)],
        body="Hi there, we've added {{early_entry}}. {{checkout_link}}",
    )
    assert (fixed["status"], fixed["review"]) == ("ready", "pending")
