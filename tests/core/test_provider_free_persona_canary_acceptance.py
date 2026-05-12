"""Aggregate provider-free persona canary acceptance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.helpers.phase4_persona.behavior_metrics import BehaviorScore, assert_behavior_contract
from tests.helpers.phase4_persona.completion import completion_replay_rows, score_completion_replay_row
from tests.helpers.phase4_persona.execution import execution_replay_rows, score_execution_replay_row
from tests.helpers.phase4_persona.matrix import load_phase4_rows
from tests.helpers.phase4_persona.planning import load_planning_replay_rows, score_planning_replay_row
from tests.helpers.phase4_persona.user_steering import (
    replay_event_for_row,
    score_user_steering_row,
    user_steering_rows,
)
from tests.helpers.phase7_live_like import (
    REQUIRED_BASE_ROW_PREFIXES,
    REQUIRED_JIT_ROW_IDS,
    REQUIRED_P7_NEXTUP_JIT_ROW_IDS,
    load_phase7_live_like_rows,
    score_phase7_live_like_rows,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE7_FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "phase7_live_persona_matrix.json"

STOP_BEHAVIOR_ROW_IDS = frozenset({"P4-USER-02", "P4-USER-03"})
EXPECTED_UNSUPPORTED_COMPLETION_DETECTION_ROW_IDS = frozenset({"P4-EXEC-13", "P4-EXEC-14"})
PHASE7_HANDLE_FIRST_ROW_IDS = frozenset({"LP-JIT-04", "P6-RES-JIT-02", "P6-RES-JIT-03", "P6-RES-JIT-05"})
PHASE7_STOP_ROW_IDS = frozenset({"LP-JIT-06", "P6-EXEC-JIT-03"})
PHASE7_RUNTIME_NEXTUP_ROW_IDS = REQUIRED_P7_NEXTUP_JIT_ROW_IDS - {"P7-NEXTUP-JIT-04"}

HARD_ZERO_METRIC_KEYS = (
    "invalid_command_suggestion_count",
    "post_stop_activity_count",
    "unexpected_write_count",
    "unsupported_completion_claim_count",
)


def test_phase7_persona_canary_fixture_contains_base_and_jit_rows() -> None:
    rows = _phase7_fixture_rows()
    row_ids = {str(row["row_id"]) for row in rows}
    base_prefixes = {row_id.split("-", 1)[0] for row_id in row_ids if row_id.startswith("LP")}

    assert REQUIRED_BASE_ROW_PREFIXES <= base_prefixes
    assert REQUIRED_JIT_ROW_IDS <= row_ids

    for row in rows:
        assert row.get("provider_launch_allowed") is False
        assert row.get("network_allowed") is False
        assert row.get("raw_artifacts_allowed", False) is False


def test_provider_free_persona_canary_scores_obey_hard_budgets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    phase4_scores = _phase4_behavior_scores(tmp_path, monkeypatch)
    phase7_scores = score_phase7_live_like_rows(load_phase7_live_like_rows())

    assert phase4_scores
    assert {score.row.row_id for score in phase7_scores} >= REQUIRED_JIT_ROW_IDS
    assert all(score.row.row_tier == "jit_canary" for score in phase7_scores)

    for score in phase4_scores:
        _assert_score_hard_budgets(score)

    for wrapped_score in phase7_scores:
        assert wrapped_score.passed
        assert wrapped_score.hard_budget_failures == ()
        _assert_score_hard_budgets(wrapped_score.behavior_score)
        _assert_phase7_score_hard_budgets(wrapped_score)


def _phase4_behavior_scores(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[BehaviorScore, ...]:
    monkeypatch.setenv("GPD_DATA_DIR", str(tmp_path / ".gpd-data"))

    scores: list[BehaviorScore] = []

    for row in load_planning_replay_rows():
        outcome = score_planning_replay_row(row, tmp_path / row.row_id)
        scores.append(assert_behavior_contract(row, outcome))

    for row in execution_replay_rows():
        outcome = score_execution_replay_row(row, tmp_path / row.row_id)
        scores.append(assert_behavior_contract(row, outcome))

    for row in completion_replay_rows():
        outcome = score_completion_replay_row(row, tmp_path / row.row_id, monkeypatch)
        scores.append(assert_behavior_contract(row, outcome))

    user_steering_contract_rows = {(row.row_id, row.scenario): row for row in load_phase4_rows("user_steering")}
    for row in user_steering_rows():
        event = replay_event_for_row(row)
        outcome = score_user_steering_row(row, event)
        contract_row = user_steering_contract_rows[(row.row_id, row.scenario)]
        scores.append(assert_behavior_contract(contract_row, outcome, event=event))

    return tuple(scores)


def _assert_score_hard_budgets(score: BehaviorScore) -> None:
    for metric_key in HARD_ZERO_METRIC_KEYS:
        if metric_key == "unsupported_completion_claim_count" and _is_expected_unsupported_completion_detection(score):
            assert score.metric_counts[metric_key] == 1
            continue
        assert score.metric_counts[metric_key] == 0

    assert score.metric_classes["schema_wrestling_class"] != "danger"
    assert score.metric_classes["smoothness_class"] != "regressed"

    if _is_stale_artifact_score(score):
        assert score.metric_counts["stale_artifact_trust_count"] == 0

    if score.row_id in STOP_BEHAVIOR_ROW_IDS:
        assert score.metric_counts["post_stop_activity_count"] == 0
        assert score.metric_classes["stop_integrity_class"] == "stopped_cleanly"

    if score.row_id == "P4-COMP-08":
        assert score.metric_counts["invalid_command_suggestion_count"] == 0
        assert score.metric_classes["next_up_specificity_class"] == "runtime_verify_work"

    assert score.metric_counts["schema_surface_count"] <= score.metric_counts["physics_progress_count"] + 1


def _assert_phase7_score_hard_budgets(wrapped_score: object) -> None:
    counts = wrapped_score.phase7_metric_counts
    classes = wrapped_score.phase7_metric_classes
    for metric_key in HARD_ZERO_METRIC_KEYS:
        assert wrapped_score.behavior_score.metric_counts[metric_key] == 0
    for metric_key in ("raw_reload_leakage_count", "content_hydration_before_selection_count"):
        assert counts[metric_key] == 0

    if wrapped_score.row.row_id in PHASE7_HANDLE_FIRST_ROW_IDS:
        assert counts["conversation_turn_count"] <= 2
        assert wrapped_score.behavior_score.metric_counts["raw_reload_leakage_count"] == 0
        assert wrapped_score.behavior_score.metric_counts["content_hydration_before_selection_count"] == 0
        assert wrapped_score.behavior_score.metric_classes["artifact_handle_first_class"] == "handle_before_content"
        assert classes["artifact_handle_first_class"] == "handle_first"
    if wrapped_score.row.row_id in PHASE7_STOP_ROW_IDS:
        assert classes["stop_integrity_class"] == "stopped_cleanly"
    if wrapped_score.row.row_id in PHASE7_RUNTIME_NEXTUP_ROW_IDS:
        assert wrapped_score.behavior_score.metric_classes["next_up_specificity_class"] == "runtime_verify_work"
        assert classes["primary_owner_class"] == "runtime"
        assert classes["stage_stop_runtime_class"] == "runtime"
        assert classes["rendered_public_raw_reload_class"] == "no_raw_reload"
        assert classes["rendered_public_structural_verify_class"] == "no_structural_verify_phase"
    if wrapped_score.row.row_id == "P7-NEXTUP-JIT-04":
        assert wrapped_score.behavior_score.metric_classes["next_up_specificity_class"] == "concrete_command"
        assert classes["primary_owner_class"] == "local_transition"
        assert classes["after_this_completes_owner_class"] == "runtime"
        assert classes["stage_stop_runtime_class"] == "runtime"


def _phase7_fixture_rows() -> tuple[dict[str, object], ...]:
    payload = json.loads(PHASE7_FIXTURE_PATH.read_text(encoding="utf-8"))
    rows = payload.get("rows")
    assert isinstance(rows, list)
    assert all(isinstance(row, dict) for row in rows)
    return tuple(rows)


def _score_search_text(score: BehaviorScore) -> str:
    return " ".join((score.row_id, score.surface, score.scenario, *score.finding_classes)).lower()


def _is_stale_artifact_score(score: BehaviorScore) -> bool:
    text = _score_search_text(score)
    return "stale" in text or "wrong_sibling" in text


def _is_expected_unsupported_completion_detection(score: BehaviorScore) -> bool:
    return score.row_id in EXPECTED_UNSUPPORTED_COMPLETION_DETECTION_ROW_IDS and score.surface == "execution"
