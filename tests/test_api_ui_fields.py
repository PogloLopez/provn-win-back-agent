"""Covers the API fields the marketer UI reads: run `total`, options `values`/`phrases`."""

from tests.test_api import api, start  # noqa: F401  (fixture reuse)
from tests.test_copy import GOOD as GOOD_COPY
from tests.test_pipeline import OFFER_1001
from winback.carts import load_carts


def test_start_run_reports_total_carts(api):  # noqa: F811
    client, _ = api([])
    body = client.post("/api/runs").json()
    assert body["total"] == len(load_carts())
    assert isinstance(body["run_id"], str)


def test_options_phrases_cover_every_menu_choice(api):  # noqa: F811
    client, _ = api([OFFER_1001, GOOD_COPY])
    _, cards = start(client)
    options = client.get(f"/api/cards/{cards['C-1001']['id']}/options").json()
    assert "placeholders" not in options
    for option in options["menu"]:
        assert f"{option['value']:g}" in options["phrases"][option["type"]]
    assert all(isinstance(v, str) and v for v in options["values"].values())


def test_options_for_card_without_offer_has_empty_values(api):  # noqa: F811
    client, _ = api([OFFER_1001, GOOD_COPY])
    _, cards = start(client)
    response = client.get(f"/api/cards/{cards['C-1003']['id']}/options")
    assert response.status_code == 200
    assert response.json()["values"] == {}
