import pytest

from tests.fakes import FakeChatClient, assert_groq_strict
from tests.test_copy import CART, GOOD, PROPOSAL, TRIAGE
from winback.copy_models import EmailDraft
from winback.feedback_analyst import FeedbackAnalysis, FeedbackCategory, Target, analyze
from winback.llm import LLM, load_models_config
from winback.telemetry import Telemetry, make_engine

CONFIG = load_models_config()
ANALYSIS = {
    "feedback_category": "offer_too_generous",
    "target_component": "offer_strategist",
    "severity": "medium",
    "summary": "The discount is more than this loyal fan needs.",
    "instruction": "Offer a no-cost perk instead of a discount.",
}


def run(replies, **kwargs):
    client = FakeChatClient(replies)
    telemetry = Telemetry(make_engine("sqlite://"))
    result = analyze(
        cart=CART,
        triage=TRIAGE,
        proposal=PROPOSAL,
        llm=LLM(CONFIG, client),
        telemetry=telemetry,
        **kwargs,
    ).value
    return result, client, telemetry


def test_schema_is_groq_strict():
    assert_groq_strict(FeedbackAnalysis.model_json_schema())


def test_feedback_is_classified():
    result, client, telemetry = run([ANALYSIS], feedback="too generous")
    assert result.feedback_category is FeedbackCategory.OFFER_TOO_GENEROUS
    assert result.target_component is Target.OFFER_STRATEGIST
    assert '"kind": "feedback"' in client.requests[0]["messages"][1]["content"]
    assert telemetry.events()[0].stage == "feedback"


def test_text_edit_sends_before_and_after():
    after = EmailDraft(**(GOOD | {"body": GOOD["body"].replace("Hi there", "Hello")}))
    _, client, _ = run(
        [ANALYSIS | {"feedback_category": "tone_off"}], before=EmailDraft(**GOOD), after=after
    )
    payload = client.requests[0]["messages"][1]["content"]
    assert '"kind": "text_edit"' in payload and "Hello" in payload


def test_agent_target_without_instruction_is_retried():
    result, client, _ = run([ANALYSIS | {"instruction": ""}, ANALYSIS], feedback="too generous")
    assert result is not None
    assert len(client.requests) == 2


def test_empty_input_is_rejected():
    with pytest.raises(ValueError, match="feedback"):
        run([])


@pytest.mark.live
def test_live_feedback_routes_to_offer_strategist():
    telemetry = Telemetry(make_engine("sqlite://"))
    result = analyze(
        cart=CART,
        triage=TRIAGE,
        proposal=PROPOSAL,
        llm=LLM(CONFIG),
        telemetry=telemetry,
        feedback="10% is too much for someone who buys anyway. Give a perk, not a discount.",
    ).value
    assert result.target_component is Target.OFFER_STRATEGIST
    assert result.feedback_category in {
        FeedbackCategory.OFFER_TOO_GENEROUS,
        FeedbackCategory.WRONG_OFFER_TYPE,
    }
