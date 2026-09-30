import pytest
from jinja2 import UndefinedError

from tests.fakes import FakeChatClient, assert_groq_strict
from winback import placeholders
from winback.business_rules import load_business_rules
from winback.carts import load_carts
from winback.copy_models import EmailDraft
from winback.copywriter import fallback_draft, load_persona, system_prompt, write_copy
from winback.guarded import Status
from winback.guardrails import blocking, check_copy
from winback.llm import LLM, load_models_config
from winback.offer_models import OfferProposal
from winback.rules_engine import load_triage_rules, triage
from winback.telemetry import Telemetry, make_engine

RULES = load_business_rules()
PERSONA = load_persona()
CONFIG = load_models_config()
CART = next(c for c in load_carts() if c.cart_id == "C-1001")
TRIAGE = triage(CART, load_triage_rules())
PROPOSAL = OfferProposal(
    cart_id="C-1001",
    decision="offer",
    offers=[{"type": "discount_pct", "value": 10}],
    reason="Loyal fan who left the cart early; a small discount helps finish the play.",
    reason_codes_cited=["SEGMENT_LOYAL"],
    confidence=0.7,
)
REMINDER = PROPOSAL.model_copy(update={"decision": "reminder_only", "offers": []})

GOOD = {
    "subject": "Your {{section}} seats are holding the line",
    "body": (
        "Hi there,\n\nYour {{seats}} in {{section}} are still waiting, and we've "
        "added {{discount_pct}} to help you finish the play.\n\n"
        "Get back in the game: {{checkout_link}}\n\nTogether We Hunt"
    ),
}


def codes(draft: dict, proposal=PROPOSAL):
    return {v.code for v in check_copy(EmailDraft(**draft), proposal, PERSONA, RULES)}


def test_draft_schema_is_groq_strict():
    assert_groq_strict(EmailDraft.model_json_schema())


def test_system_prompt_embeds_persona_and_keeps_placeholder_braces():
    prompt = system_prompt(PERSONA)
    assert "Together We Hunt" in prompt
    assert "{{checkout_link}}" in prompt


def test_good_draft_passes():
    assert codes(GOOD) == set()


@pytest.mark.parametrize(
    ("body_change", "code"),
    [
        ("Get 10% off now", "RAW_VALUE"),
        ("Only $86 left to pay", "RAW_VALUE"),
        ("{{free_parking}}", "UNKNOWN_PLACEHOLDER"),
        ("Plus free parking on matchday!", "UNGRANTED_OFFER"),
        ("Seats are selling out fast", "SCARCITY_CLAIM"),
        ("Score a touchdown with us", "BANNED_TERM"),
        ("See you there \U0001f3c9", "EMOJI"),
        ("Use {section} here", "MALFORMED_PLACEHOLDER"),
    ],
)
def test_each_copy_rule_blocks(body_change, code):
    assert code in codes(GOOD | {"body": GOOD["body"] + "\n" + body_change})


def test_granted_offer_and_checkout_link_are_required():
    body = "Hi there, your seats in {{section}} are waiting."
    assert "MISSING_PLACEHOLDER" in codes(GOOD | {"body": body})


def test_reminder_must_not_mention_a_discount():
    body = "Hi there, come back for a discount. {{checkout_link}}"
    assert "UNGRANTED_OFFER" in codes(GOOD | {"body": body}, REMINDER)


@pytest.mark.parametrize("proposal", [PROPOSAL, REMINDER])
def test_fallback_draft_always_passes(proposal):
    draft = fallback_draft(proposal)
    assert blocking(check_copy(draft, proposal, PERSONA, RULES)) == []


def test_render_fills_values_from_the_offer():
    context = placeholders.values(CART, PROPOSAL, RULES)
    text = placeholders.render(GOOD["body"], context)
    assert "10% off your order" in text
    assert "https://example.com/checkout/C-1001" in text
    assert "{{" not in text


def test_render_fails_loudly_on_missing_value():
    with pytest.raises(UndefinedError):
        placeholders.render("{{free_parking}}", placeholders.values(CART, PROPOSAL, RULES))


def run(replies):
    telemetry = Telemetry(make_engine("sqlite://"))
    result = write_copy(
        CART,
        TRIAGE,
        PROPOSAL,
        rules=RULES,
        persona=PERSONA,
        llm=LLM(CONFIG, FakeChatClient(replies)),
        telemetry=telemetry,
    )
    return result, telemetry


def test_write_copy_renders_accepted_draft():
    result, telemetry = run([GOOD])
    assert result.status is Status.OK
    assert "10% off your order" in result.email.body
    stages = [(e.stage, e.status) for e in telemetry.events()]
    assert stages == [("copy", "ok"), ("copy_guardrail", "pass"), ("render", "ok")]


def test_write_copy_escalates_to_fallback_draft():
    bad = GOOD | {"body": "Get 10% off!"}
    result, _ = run([bad, bad, bad])
    assert result.status is Status.NEEDS_ATTENTION
    assert result.draft == fallback_draft(PROPOSAL)
    assert "10% off your order" in result.email.body


@pytest.mark.live
def test_live_copy_passes_guardrails():
    telemetry = Telemetry(make_engine("sqlite://"))
    result = write_copy(
        CART, TRIAGE, PROPOSAL, rules=RULES, persona=PERSONA, llm=LLM(CONFIG), telemetry=telemetry
    )
    print(result.email.subject, "\n", result.email.body, "\n", result.attempts)
    assert result.status is Status.OK


def test_single_seat_renders_singular():
    one = CART.model_copy(update={"seats": 1})
    assert placeholders.values(one, PROPOSAL, RULES)["seats"] == "1 seat"
    assert placeholders.values(CART, PROPOSAL, RULES)["seats"] == "2 seats"


def test_long_copy_is_a_warning_only():
    long_body = GOOD["body"] + " word" * 200
    violations = check_copy(EmailDraft(**(GOOD | {"body": long_body})), PROPOSAL, PERSONA, RULES)
    assert [v.code for v in violations] == ["TOO_LONG"]
    assert blocking(violations) == []


def test_marketer_feedback_reaches_the_copywriter():
    client = FakeChatClient([GOOD])
    write_copy(
        CART,
        TRIAGE,
        PROPOSAL,
        rules=RULES,
        persona=PERSONA,
        llm=LLM(CONFIG, client),
        telemetry=Telemetry(make_engine("sqlite://")),
        feedback="warmer, less salesy",
    )
    assert "warmer, less salesy" in client.requests[0]["messages"][-1]["content"]
