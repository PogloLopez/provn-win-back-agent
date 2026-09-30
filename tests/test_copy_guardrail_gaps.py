"""Gap tests: pass cases per copy rule, render failure telemetry, pipeline statuses."""

import pytest
from jinja2 import UndefinedError

from tests.test_copy import CART, GOOD, PERSONA, PROPOSAL, REMINDER, RULES, codes
from tests.test_pipeline import CARTS, OFFER_1001, pipeline
from winback.copy_models import EmailDraft
from winback.copywriter import fallback_draft, render_email
from winback.guardrails import blocking, check_copy
from winback.offer_models import OfferProposal
from winback.pipeline import CartStatus
from winback.telemetry import Telemetry, make_engine

PARKING = OfferProposal(
    **(PROPOSAL.model_dump() | {"offers": [{"type": "free_parking", "value": 1}]})
)
PARKING_GOOD = {
    "subject": "Your {{section}} seats are holding the line",
    "body": "Hi there, we added {{free_parking}}. Parking sorted. {{checkout_link}}",
}


@pytest.mark.parametrize(
    ("draft", "proposal", "code"),
    [
        (GOOD, PROPOSAL, "RAW_VALUE"),  # values only via placeholders
        (GOOD, PROPOSAL, "UNKNOWN_PLACEHOLDER"),  # granted placeholder is fine
        (GOOD, PROPOSAL, "MISSING_PLACEHOLDER"),
        (GOOD | {"body": GOOD["body"] + " Scrum down and tackle it."}, PROPOSAL, "BANNED_TERM"),
        (GOOD | {"body": GOOD["body"] + " Whenever you're ready."}, PROPOSAL, "SCARCITY_CLAIM"),
        (GOOD, PROPOSAL, "EMOJI"),
        (GOOD | {"body": GOOD["body"] + " Enjoy the discount."}, PROPOSAL, "UNGRANTED_OFFER"),
        (PARKING_GOOD, PARKING, "UNGRANTED_OFFER"),  # granted keyword may appear
        (
            GOOD | {"body": "{{ checkout_link }} {{ discount_pct }}"},
            PROPOSAL,
            "MALFORMED_PLACEHOLDER",
        ),
        (GOOD, PROPOSAL, "EMPTY_COPY"),
    ],
)
def test_each_copy_rule_has_a_passing_case(draft, proposal, code):
    assert code not in codes(draft, proposal)


@pytest.mark.parametrize(
    "draft",
    [GOOD | {"subject": "   "}, GOOD | {"body": " \n "}],
)
def test_empty_copy_blocks(draft):
    assert "EMPTY_COPY" in codes(draft)


def test_ungranted_offer_blocks_for_each_offer_type_on_reminder():
    for name, offer in RULES.offers.items():
        body = f"Hi, {offer.keywords[0]} for you. {{{{checkout_link}}}}"
        assert "UNGRANTED_OFFER" in codes(GOOD | {"body": body}, REMINDER), name


def test_long_subject_is_a_warning_only():
    draft = EmailDraft(**(GOOD | {"subject": "Your {{section}} seats " + "a" * 80}))
    violations = check_copy(draft, PROPOSAL, PERSONA, RULES)
    assert [v.code for v in violations] == ["TOO_LONG"]
    assert blocking(violations) == []


def test_render_email_records_failure_and_raises():
    telemetry = Telemetry(make_engine("sqlite://"))
    draft = EmailDraft(subject="Hi", body="{{free_parking}} {{checkout_link}}")
    with pytest.raises(UndefinedError):
        render_email(draft, CART, PROPOSAL, RULES, telemetry)
    events = [(e.stage, e.status) for e in telemetry.events()]
    assert events == [("render", "fail")]


def test_render_email_fails_on_missing_placeholder_in_subject():
    telemetry = Telemetry(make_engine("sqlite://"))
    draft = EmailDraft(subject="{{seat_upgrade}}", body="{{checkout_link}}")
    with pytest.raises(UndefinedError):
        render_email(draft, CART, PROPOSAL, RULES, telemetry)


def test_copy_escalation_marks_cart_needs_attention_with_fallback():
    bad = GOOD | {"body": "Get 10% off!"}
    outcome = pipeline([OFFER_1001, bad, bad, bad]).process(CARTS["C-1001"])
    assert outcome.status is CartStatus.NEEDS_ATTENTION
    assert outcome.offer.status == "ok"
    assert outcome.email.draft == fallback_draft(outcome.offer.proposal)
    assert outcome.error is None


def test_failed_cart_records_error_and_no_results():
    outcome = pipeline([OFFER_1001]).process(CARTS["C-1001"])  # copy call runs out of replies
    assert outcome.status is CartStatus.FAILED
    assert outcome.offer is None and outcome.email is None
    assert outcome.error
