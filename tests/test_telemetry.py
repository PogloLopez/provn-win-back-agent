from sqlmodel import create_engine

from winback.telemetry import Stage, Telemetry, make_engine, normalize_database_url


def test_supabase_url_is_normalized():
    raw = "postgresql://u:p@aws-0-us-east-1.pooler.supabase.com:6543/postgres?pgbouncer=true"
    assert normalize_database_url(raw) == (
        "postgresql+psycopg://u:p@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
    )
    assert normalize_database_url("sqlite:///x.db") == "sqlite:///x.db"
    assert normalize_database_url("postgresql://u:p@h:5432/db?pgbouncer=true&sslmode=require") == (
        "postgresql+psycopg://u:p@h:5432/db?sslmode=require"
    )


def test_events_round_trip():
    telemetry = Telemetry(make_engine("sqlite://"))
    telemetry.record(Stage.TRIAGE, "ELIGIBLE", cart_id="C-1", reason_codes=["SEGMENT_LOYAL"])
    telemetry.record(Stage.OFFER, "ok", cart_id="C-1", payload={"x": 1}, tokens_in=10)
    events = telemetry.events()
    assert [e.stage for e in events] == ["triage", "offer"]
    assert events[0].reason_codes == ["SEGMENT_LOYAL"]
    assert events[1].payload == {"x": 1}


def test_telemetry_failure_does_not_raise(caplog):
    telemetry = Telemetry(create_engine("sqlite://"))  # no `events` table
    telemetry.record(Stage.OFFER, "ok")
    assert "telemetry write failed" in caplog.text
    assert telemetry.failures == 1
