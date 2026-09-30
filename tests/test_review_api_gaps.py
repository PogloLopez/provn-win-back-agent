"""Gap coverage for review actions, API error codes and SSE framing (verifier-added)."""

import json

import pytest
from sqlmodel import Session

from tests import test_api, test_review
from tests.test_api import sse_events, start
from tests.test_copy import GOOD as GOOD_COPY
from tests.test_feedback_analyst import ANALYSIS
from tests.test_pipeline import OFFER_1001
from winback.review import ActionBlocked, Card

api = test_api.api  # shared fixtures
harness = test_review.harness

# ---- review service ---------------------------------------------------------------------


def test_edit_on_skipped_card_is_blocked(harness):
    h = harness([OFFER_1001, GOOD_COPY])
    _, cards = h.run()
    with pytest.raises(ActionBlocked) as blocked:
        h.service.edit(cards["C-1003"]["id"], subject="Hi")
    assert blocked.value.violations[0].code == "NOTHING_TO_EDIT"


def test_blank_text_edit_is_blocked(harness):
    h = harness([OFFER_1001, GOOD_COPY])
    _, cards = h.run()
    with pytest.raises(ActionBlocked) as blocked:
        h.service.edit(cards["C-1001"]["id"], body="   ")
    assert blocked.value.violations[0].code == "EMPTY_COPY"


def test_feedback_on_skipped_card_is_blocked(harness):
    h = harness([OFFER_1001, GOOD_COPY])
    _, cards = h.run()
    with pytest.raises(ActionBlocked):
        h.service.feedback(cards["C-1003"]["id"], "too generous")


def test_feedback_routed_to_copywriter_keeps_offer(harness):
    tone = ANALYSIS | {"feedback_category": "tone_off", "target_component": "copywriter"}
    new_copy = GOOD_COPY | {"subject": "A friendlier hello"}
    h = harness([OFFER_1001, GOOD_COPY, tone, new_copy])
    _, cards = h.run()
    before = cards["C-1001"]["offer"]
    result = h.service.feedback(cards["C-1001"]["id"], "Warmer tone please")
    assert result.routed_to == "copywriter"
    assert result.card["offer"] == before
    assert result.card["email"]["draft"]["subject"] == "A friendlier hello"
    assert "Analyst instruction" in h.client.requests[3]["messages"][-1]["content"]


def test_unclassifiable_feedback_leaves_card_untouched(harness):
    h = harness([OFFER_1001, GOOD_COPY, "not json", "not json", "not json"])
    _, cards = h.run()
    result = h.service.feedback(cards["C-1001"]["id"], "???")
    assert (result.analysis, result.routed_to) == (None, None)
    assert result.card["email"] == cards["C-1001"]["email"]


def test_feedback_regeneration_clears_reject_reason(harness):
    """A regenerated card is pending again, so the stale reject reason must go (as in edit)."""
    perk = OFFER_1001 | {"offers": [{"type": "early_entry", "value": 1}]}
    perk_copy = GOOD_COPY | {"body": "Hi there, we've added {{early_entry}}. {{checkout_link}}"}
    h = harness([OFFER_1001, GOOD_COPY, ANALYSIS, perk, perk_copy])
    _, cards = h.run()
    card_id = cards["C-1001"]["id"]
    h.service.reject(card_id, "too_generous")
    result = h.service.feedback(card_id, "Too generous")
    assert (result.card["review"], result.card["reject_reason"]) == ("pending", None)


def test_approve_rechecks_guardrails_on_stored_card(harness):
    h = harness([OFFER_1001, GOOD_COPY])
    _, cards = h.run()
    card_id = cards["C-1001"]["id"]
    with Session(h.engine) as session:  # simulate a tampered / stale stored offer
        card = session.get(Card, card_id)
        outcome = json.loads(json.dumps(card.outcome))
        outcome["offer"]["proposal"]["offers"] = [{"type": "discount_pct", "value": 40}]
        card.outcome = outcome
        session.add(card)
        session.commit()
    with pytest.raises(ActionBlocked) as blocked:
        h.service.approve(card_id)
    assert blocked.value.violations
    assert h.service.cards(cards["C-1001"]["run_id"])[0]["review"] != "approved"


# ---- API error codes --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "/api/cards/999/options", None),
        ("post", "/api/cards/999/reject", {"reason": "other"}),
        ("post", "/api/cards/999/edit", {"subject": "x"}),
        ("post", "/api/cards/999/feedback", {"text": "too generous"}),
    ],
)
def test_unknown_card_is_404_everywhere(api, method, path, body):
    client, _ = api([])
    kwargs = {"json": body} if body is not None else {}
    response = getattr(client, method)(path, **kwargs)
    assert response.status_code == 404
    assert "999" in response.json()["detail"]


def test_409_and_429_carry_a_detail(api):
    client, _ = api([OFFER_1001, GOOD_COPY])
    run_id, _ = start(client)
    conflict = client.get(f"/api/runs/{run_id}/stream")
    assert conflict.status_code == 409 and run_id in conflict.json()["detail"]
    too_many = client.post("/api/runs")
    assert too_many.status_code == 429 and "wait" in too_many.json()["detail"]


def test_request_validation_is_422(api):
    client, _ = api([OFFER_1001, GOOD_COPY])
    _, cards = start(client)
    card_id = cards["C-1001"]["id"]
    assert client.post(f"/api/cards/{card_id}/feedback", json={"text": "no"}).status_code == 422
    assert client.post(f"/api/cards/{card_id}/edit", json={"body": "x" * 5001}).status_code == 422
    assert client.post("/api/cards/abc/approve").status_code == 422


def test_blank_edit_via_api_returns_violations(api):
    client, _ = api([OFFER_1001, GOOD_COPY])
    _, cards = start(client)
    response = client.post(f"/api/cards/{cards['C-1001']['id']}/edit", json={"subject": " "})
    assert response.status_code == 422
    assert response.json()["violations"][0]["code"] == "EMPTY_COPY"


def test_approving_skipped_card_via_api_is_422(api):
    client, _ = api([OFFER_1001, GOOD_COPY])
    _, cards = start(client)
    response = client.post(f"/api/cards/{cards['C-1003']['id']}/approve")
    assert response.status_code == 422
    assert response.json()["violations"][0]["code"] == "NOTHING_TO_SEND"


# ---- SSE --------------------------------------------------------------------------------


def test_sse_headers_and_framing(api):
    client, _ = api([OFFER_1001, GOOD_COPY])
    run_id = client.post("/api/runs").json()["run_id"]
    response = client.get(f"/api/runs/{run_id}/stream")
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.text.endswith("\n\n")
    events = sse_events(response.text)
    assert [kind for kind, _ in events] == ["card", "card", "done"]
    assert all(data["run_id"] == run_id for kind, data in events if kind == "card")


def test_mid_stream_failure_after_a_card_keeps_the_card(api, monkeypatch):
    client, harness_ = api([OFFER_1001, GOOD_COPY])
    original = harness_.service.stream_run

    def half(run_id):
        yield next(iter(original(run_id)))
        raise RuntimeError("boom")

    monkeypatch.setattr(harness_.service, "stream_run", half)
    run_id = client.post("/api/runs").json()["run_id"]
    events = sse_events(client.get(f"/api/runs/{run_id}/stream").text)
    assert [kind for kind, _ in events] == ["card", "error"]
    assert len(client.get(f"/api/runs/{run_id}/cards").json()) == 1
