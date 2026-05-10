"""Provider-free Phase 7 live-like adapter tests."""

from __future__ import annotations

import inspect
import json
from dataclasses import fields

from tests.helpers import phase7_live_like
from tests.helpers.phase4_persona.interaction_events import FakePersonaTrace, FakePersonaTurn
from tests.helpers.phase7_live_like import (
    LP_JIT_ROW_IDS,
    PHASE7_LIVE_PERSONA_MATRIX_PATH,
    Phase7LiveLikeRow,
    load_phase7_live_like_rows,
    score_phase7_live_like_row,
    score_phase7_live_like_rows,
)


def test_phase7_live_like_loader_consumes_tracked_matrix() -> None:
    rows = load_phase7_live_like_rows()

    assert {row.row_id for row in rows} >= {"LP01-START-PROJECTLESS-READONLY", "LP12-GEMINI-POLICY-DENIAL"}
    assert all(row.provider_launch_allowed is False for row in rows)
    assert all(row.network_allowed is False for row in rows)


def test_phase7_live_like_matrix_has_no_raw_transcripts_or_provider_launch_fields() -> None:
    payload = json.loads(PHASE7_LIVE_PERSONA_MATRIX_PATH.read_text(encoding="utf-8"))
    forbidden_keys = {
        "raw_prompt",
        "raw_reply",
        "raw_transcript",
        "provider_stdout",
        "provider_stderr",
        "provider_argv",
        "provider_env",
        "provider_path",
        "provider_account",
        "api_key",
        "token",
        "secret",
    }
    row_fields = {field.name for field in fields(Phase7LiveLikeRow)}

    assert forbidden_keys.isdisjoint(row_fields)
    for row in payload["rows"]:
        assert forbidden_keys.isdisjoint(row)
        assert row.get("provider_launch_allowed", False) is False
        assert row.get("network_allowed", False) is False
        assert row.get("raw_artifacts_allowed", False) is False


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


def test_lp_jit_04_uses_shared_handle_before_content_detector() -> None:
    row = _row_by_id("LP-JIT-04")
    score = score_phase7_live_like_row(row)

    assert score.passed
    assert score.hard_budget_failures == ()
    assert score.behavior_score.metric_counts["content_hydration_before_selection_count"] == 0
    assert score.behavior_score.metric_classes["artifact_handle_first_class"] == "handle_before_content"
    assert score.phase7_metric_classes["artifact_handle_first_class"] == "handle_first"


def test_lp_jit_04_rejects_content_before_handle_regression() -> None:
    row = _row_by_id("LP-JIT-04")
    trace = FakePersonaTrace(
        row_id="LP_JIT_04_BAD_CONTENT_FIRST",
        persona_class=row.persona_class,
        prompt_variant_class=row.prompt_variant_class,
        turns=(
            FakePersonaTurn(
                turn_index=0,
                speaker_class="assistant",
                intent_class="reference_review",
                action_class="concrete_command",
                physics_progress_class="artifact_verified",
                content_hydration_class="content_loaded",
            ),
            FakePersonaTurn(
                turn_index=1,
                speaker_class="assistant",
                intent_class="reference_choice",
                action_class="select_reference",
                artifact_handle_class="handle_selected",
            ),
        ),
    )
    score = score_phase7_live_like_row(row, trace_override=trace)

    assert not score.passed
    assert score.behavior_score.metric_counts["content_hydration_before_selection_count"] == 1
    assert score.behavior_score.metric_classes["artifact_handle_first_class"] == "content_before_handle"
    assert "content_hydration_before_selection_count" in score.hard_budget_failures


def test_phase7_live_like_helper_has_no_execution_or_network_surface() -> None:
    source = inspect.getsource(phase7_live_like)

    for forbidden in ("subprocess", "create_subprocess", "os.environ", "socket", "urllib", "requests"):
        assert forbidden not in source


def _row_by_id(row_id: str) -> Phase7LiveLikeRow:
    rows = load_phase7_live_like_rows()
    return next(row for row in rows if row.row_id == row_id)
