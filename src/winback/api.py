"""HTTP API for the marketer UI. Run locally: uv run uvicorn winback.api:app --reload"""

import json
import logging
from collections.abc import Iterator
from functools import cache
from typing import Literal

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from winback.carts import load_carts
from winback.offer_models import ProposedOffer
from winback.pipeline import Pipeline
from winback.review import (
    ActionBlocked,
    CardNotFound,
    FeedbackResult,
    ReviewService,
    RunAlreadyStreamed,
    RunNotFound,
    TooManyRuns,
)
from winback.telemetry import make_engine

log = logging.getLogger(__name__)


class RejectBody(BaseModel):
    reason: Literal["too_generous", "wrong_tone", "should_not_contact", "other"]


class EditBody(BaseModel):
    offers: list[ProposedOffer] | None = Field(default=None, max_length=5)
    subject: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=5000)


class FeedbackBody(BaseModel):
    text: str = Field(min_length=3, max_length=1000)


@cache
def default_service() -> ReviewService:
    return ReviewService(make_engine(), Pipeline.default)


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def create_app(get_service=default_service) -> FastAPI:
    app = FastAPI(title="Seawolves Win-Back API")
    service = Depends(get_service)

    def error(status: int, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=status, content={"detail": str(exc)})

    @app.exception_handler(ActionBlocked)
    def _blocked(_: Request, exc: ActionBlocked) -> JSONResponse:
        violations = [v.model_dump() for v in exc.violations]
        return JSONResponse(status_code=422, content={"violations": violations})

    app.exception_handler(CardNotFound)(lambda _, exc: error(404, f"card {exc} not found"))
    app.exception_handler(RunNotFound)(lambda _, exc: error(404, f"run {exc} not found"))
    app.exception_handler(RunAlreadyStreamed)(lambda _, exc: error(409, exc))
    app.exception_handler(TooManyRuns)(lambda _, exc: error(429, exc))

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    @app.post("/api/runs", status_code=201)
    def start_run(svc: ReviewService = service) -> dict:
        return {"run_id": svc.start_run(), "total": len(load_carts())}

    @app.get("/api/runs/{run_id}/stream")
    def stream(run_id: str, svc: ReviewService = service) -> StreamingResponse:
        """Server-sent events: one `card` per cart as it finishes, then `done` (or `error`).

        Each run streams once (404 unknown, 409 already streamed), so a browser reconnect
        cannot re-run the LLMs. The client should close the EventSource on `done`.
        """
        svc.claim_run(run_id)

        def events() -> Iterator[str]:
            try:
                for card in svc.stream_run(run_id):
                    yield _sse("card", card)
            except Exception as exc:
                log.exception("run %s failed mid-stream", run_id)
                yield _sse("run_failed", {"detail": f"run stopped: {exc!r}"[:500]})
                return
            yield _sse("done", {"telemetry_failures": svc.telemetry_failures.get(run_id, 0)})

        headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
        return StreamingResponse(events(), media_type="text/event-stream", headers=headers)

    @app.get("/api/runs/{run_id}/cards")
    def cards(run_id: str, svc: ReviewService = service) -> list[dict]:
        return svc.cards(run_id)

    @app.get("/api/cards/{card_id}/options")
    def options(card_id: int, svc: ReviewService = service) -> dict:
        return svc.options(card_id)

    @app.post("/api/cards/{card_id}/approve")
    def approve(card_id: int, svc: ReviewService = service) -> dict:
        return svc.approve(card_id)

    @app.post("/api/cards/{card_id}/reject")
    def reject(card_id: int, body: RejectBody, svc: ReviewService = service) -> dict:
        return svc.reject(card_id, body.reason)

    @app.post("/api/cards/{card_id}/edit")
    def edit(card_id: int, body: EditBody, svc: ReviewService = service) -> dict:
        return svc.edit(card_id, offers=body.offers, subject=body.subject, body=body.body)

    @app.post("/api/cards/{card_id}/feedback")
    def feedback(card_id: int, body: FeedbackBody, svc: ReviewService = service) -> FeedbackResult:
        return svc.feedback(card_id, body.text)

    return app


app = create_app()
