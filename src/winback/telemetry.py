"""Telemetry: one `events` row per pipeline checkpoint (SQLite locally, Postgres when deployed)."""

import logging
import os
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Column, DateTime
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool
from sqlmodel import Field, Session, SQLModel, create_engine, select

from winback import settings  # noqa: F401  (loads .env)

log = logging.getLogger(__name__)


class Stage(StrEnum):
    TRIAGE = "triage"
    OFFER = "offer"
    OFFER_GUARDRAIL = "offer_guardrail"
    COPY = "copy"
    COPY_GUARDRAIL = "copy_guardrail"
    RENDER = "render"
    UI_ACTION = "ui_action"
    FEEDBACK = "feedback"


class Event(SQLModel, table=True):
    __tablename__ = "events"

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    cart_id: str | None = Field(default=None, index=True)
    stage: str
    status: str
    reason_codes: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    model: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cached_tokens: int | None = None
    latency_ms: int | None = None
    attempt: int | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), sa_column=Column(DateTime(timezone=True))
    )


def normalize_database_url(url: str) -> str:
    """Accept Supabase's copy-paste URL: force the psycopg v3 driver, drop `pgbouncer=true`."""
    parsed = make_url(url)
    if parsed.drivername in ("postgres", "postgresql"):
        parsed = parsed.set(drivername="postgresql+psycopg")
    return parsed.difference_update_query(["pgbouncer"]).render_as_string(hide_password=False)


def make_engine(url: str | None = None) -> Engine:
    url = normalize_database_url(url or os.environ.get("DATABASE_URL", "sqlite:///winback.db"))
    if url.startswith("postgresql"):
        # Supabase pooler: no server-side prepared statements, no client-side pool.
        engine = create_engine(url, poolclass=NullPool, connect_args={"prepare_threshold": None})
    else:
        engine = create_engine(url)
    SQLModel.metadata.create_all(engine)
    return engine


class Telemetry:
    def __init__(self, engine: Engine, run_id: str | None = None):
        self.engine = engine
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.failures = 0  # surfaced to the UI as "telemetry degraded"

    def record(self, stage: Stage, status: str, **fields: Any) -> None:
        """Write one event. A telemetry failure is logged, never raised into the pipeline."""
        try:
            with Session(self.engine) as session:
                session.add(Event(run_id=self.run_id, stage=stage, status=status, **fields))
                session.commit()
        except Exception:
            self.failures += 1
            log.exception("telemetry write failed: %s/%s", stage, status)

    def events(self, **filters: Any) -> list[Event]:
        with Session(self.engine) as session:
            query = select(Event).filter_by(run_id=self.run_id, **filters).order_by(Event.id)
            return list(session.exec(query))
