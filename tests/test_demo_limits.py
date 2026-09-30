"""Demo limits: unclassified feedback counts toward the per-card cap; the Vercel shim imports."""

import importlib.util
from pathlib import Path

import pytest

from tests.test_copy import GOOD as GOOD_COPY
from tests.test_feedback_analyst import ANALYSIS
from tests.test_pipeline import OFFER_1001
from tests.test_review import harness  # noqa: F401  (fixture)
from winback.llm import DemoLimits, load_models_config
from winback.review import DemoLimitReached

UNCLASSIFIABLE = ANALYSIS | {"instruction": ""}  # agent target without instruction: retried


def test_config_has_demo_limits():
    limits = load_models_config().demo_limits
    assert limits.max_runs_per_day >= 1 and limits.max_feedback_per_card >= 1


def test_unclassified_feedback_counts_toward_cap(harness):  # noqa: F811
    attempts = load_models_config().guardrail_retries + 1
    h = harness([OFFER_1001, GOOD_COPY, *[UNCLASSIFIABLE] * attempts])
    h.service.limits = DemoLimits(
        min_seconds_between_runs=0, max_runs_per_day=5, max_feedback_per_card=1
    )
    _, cards = h.run()
    result = h.service.feedback(cards["C-1001"]["id"], "too generous")
    assert result.analysis is None
    sent = len(h.client.requests)
    with pytest.raises(DemoLimitReached, match="feedback limit"):
        h.service.feedback(cards["C-1001"]["id"], "again")
    assert len(h.client.requests) == sent


def test_vercel_shim_exposes_fastapi_app():
    path = Path(__file__).parent.parent / "app.py"
    spec = importlib.util.spec_from_file_location("vercel_app_shim", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    routes = {r.path for r in module.app.routes}
    assert "/api/health" in routes and "/api/runs" in routes
