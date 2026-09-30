import json

import pytest
from fastapi.testclient import TestClient

from tests.test_copy import GOOD as GOOD_COPY
from tests.test_feedback_analyst import ANALYSIS
from tests.test_pipeline import CARTS, OFFER_1001
from tests.test_review import Harness
from winback.api import create_app

CARTS_UNDER_TEST = [CARTS["C-1001"], CARTS["C-1003"]]


@pytest.fixture
def api(tmp_path, monkeypatch):
    def make(replies):
        harness = Harness(replies, tmp_path / "api.db")
        # The stream endpoint runs the whole dataset; keep it to two carts here.
        original = harness.service.stream_run
        monkeypatch.setattr(
            harness.service, "stream_run", lambda run_id: original(run_id, CARTS_UNDER_TEST)
        )
        return TestClient(create_app(lambda: harness.service)), harness

    return make


def sse_events(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def start(client) -> tuple[str, dict]:
    run_id = client.post("/api/runs").json()["run_id"]
    events = sse_events(client.get(f"/api/runs/{run_id}/stream").text)
    cards = {data["cart_id"]: data for kind, data in events if kind == "card"}
    assert events[-1] == ("done", {"telemetry_failures": 0})
    return run_id, cards


def test_health(api):
    client, _ = api([])
    assert client.get("/api/health").json() == {"ok": True}


def test_run_streams_cards_then_done(api):
    client, _ = api([OFFER_1001, GOOD_COPY])
    run_id, cards = start(client)
    assert cards["C-1001"]["status"] == "ready"
    assert cards["C-1003"]["status"] == "skipped"
    assert len(client.get(f"/api/runs/{run_id}/cards").json()) == 2


def test_second_run_too_soon_is_429(api):
    client, _ = api([])
    client.post("/api/runs")
    assert client.post("/api/runs").status_code == 429


def test_actions(api):
    client, _ = api([OFFER_1001, GOOD_COPY])
    _, cards = start(client)
    card_id = cards["C-1001"]["id"]
    assert client.get(f"/api/cards/{card_id}/options").json()["total_cost_cap_usd"] == 30
    assert client.post(f"/api/cards/{card_id}/approve").json()["review"] == "approved"
    rejected = client.post(f"/api/cards/{card_id}/reject", json={"reason": "wrong_tone"})
    assert rejected.json()["reject_reason"] == "wrong_tone"


def test_blocked_edit_returns_violations(api):
    client, _ = api([OFFER_1001, GOOD_COPY])
    _, cards = start(client)
    response = client.post(
        f"/api/cards/{cards['C-1001']['id']}/edit",
        json={"offers": [{"type": "discount_pct", "value": 40}]},
    )
    assert response.status_code == 422
    assert response.json()["violations"][0]["code"] == "DISCOUNT_OUT_OF_RANGE"


def test_feedback_regenerates(api):
    perk = OFFER_1001 | {"offers": [{"type": "early_entry", "value": 1}]}
    perk_copy = GOOD_COPY | {"body": "Hi there, we've added {{early_entry}}. {{checkout_link}}"}
    client, _ = api([OFFER_1001, GOOD_COPY, ANALYSIS, perk, perk_copy])
    _, cards = start(client)
    result = client.post(
        f"/api/cards/{cards['C-1001']['id']}/feedback", json={"text": "Too generous"}
    ).json()
    assert result["routed_to"] == "offer_strategist"
    assert "early entry" in result["card"]["email"]["email"]["body"]


def test_unknown_card_is_404(api):
    client, _ = api([])
    assert client.post("/api/cards/999/approve").status_code == 404


def test_a_run_streams_only_once(api):
    client, _ = api([OFFER_1001, GOOD_COPY])
    run_id, _ = start(client)
    assert client.get(f"/api/runs/{run_id}/stream").status_code == 409
    assert client.get("/api/runs/nope/stream").status_code == 404


def test_mid_stream_failure_is_reported_as_an_event(api, monkeypatch):
    client, harness = api([])

    def broken(run_id):
        raise RuntimeError("database went away")
        yield  # pragma: no cover

    monkeypatch.setattr(harness.service, "stream_run", broken)
    run_id = client.post("/api/runs").json()["run_id"]
    events = sse_events(client.get(f"/api/runs/{run_id}/stream").text)
    assert events[-1][0] == "error"
    assert "database went away" in events[-1][1]["detail"]


def test_unknown_reject_reason_is_rejected_by_validation(api):
    client, _ = api([OFFER_1001, GOOD_COPY])
    _, cards = start(client)
    response = client.post(f"/api/cards/{cards['C-1001']['id']}/reject", json={"reason": "meh"})
    assert response.status_code == 422
