"""Provider-free Phase 7 live-like adapter tests."""

from __future__ import annotations

import inspect

from tests.helpers import phase7_live_like
from tests.helpers.phase7_live_like import (
    LP_JIT_ROW_IDS,
    load_phase7_live_like_rows,
    score_phase7_live_like_rows,
)


def test_phase7_live_like_loader_consumes_tracked_matrix() -> None:
    rows = load_phase7_live_like_rows()

    assert {row.row_id for row in rows} >= {"LP01-START-PROJECTLESS-READONLY", "LP12-GEMINI-POLICY-DENIAL"}
    assert all(row.provider_launch_allowed is False for row in rows)
    assert all(row.network_allowed is False for row in rows)


def test_phase7_live_like_scores_lp_jit_rows_with_hard_budgets() -> None:
    rows = load_phase7_live_like_rows()
    scores = score_phase7_live_like_rows(rows)
    scores_by_prefix = {"-".join(score.row.row_id.split("-", 3)[:3]): score for score in scores}

    assert tuple(scores_by_prefix) == LP_JIT_ROW_IDS
    assert all(score.passed for score in scores)
    assert all(score.hard_budget_failures == () for score in scores)
    assert all(score.behavior_score.metric_counts["unexpected_write_count"] == 0 for score in scores)
    assert all(score.phase7_metric_counts["raw_reload_leakage_count"] == 0 for score in scores)
    assert all(
        score.phase7_metric_counts["schema_surface_count"] <= score.phase7_metric_counts["physics_progress_count"] + 1
        for score in scores
    )
    assert scores_by_prefix["LP-JIT-03"].behavior_score.metric_counts["stale_artifact_trust_count"] == 0
    assert scores_by_prefix["LP-JIT-04"].phase7_metric_classes["artifact_handle_first_class"] == "handle_first"
    assert scores_by_prefix["LP-JIT-06"].phase7_metric_classes["stop_integrity_class"] == "stopped_cleanly"
    assert scores_by_prefix["LP-JIT-07"].behavior_score.metric_counts["invalid_command_suggestion_count"] == 0
    assert scores_by_prefix["LP-JIT-08"].behavior_score.metric_counts["unsupported_completion_claim_count"] == 0


def test_phase7_live_like_helper_has_no_execution_or_network_surface() -> None:
    source = inspect.getsource(phase7_live_like)

    for forbidden in ("subprocess", "create_subprocess", "os.environ", "socket", "urllib", "requests"):
        assert forbidden not in source
