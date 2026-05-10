"""Provider-free Phase 4 execution and child-return replay tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers.phase4_persona.behavior_metrics import score_behavior_metrics
from tests.helpers.phase4_persona.execution import (
    ExecutionReplayRow,
    execution_replay_rows,
    score_execution_replay_row,
)
from tests.helpers.phase4_persona.matrix import (
    NEXT_UP_SPECIFICITY_CLASSES,
    PERSONA_CLASSES,
    PHASE4_PERSONA_SCHEMA_VERSION,
    SCHEMA_WRESTLING_CLASSES,
    SMOOTHNESS_CLASSES,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_phase4_execution_replay_rows_are_provider_free_and_owned() -> None:
    rows = execution_replay_rows()
    rows_by_scenario = {row.scenario: row for row in rows}

    assert len(rows) == 14
    assert len({row.row_id for row in rows}) == len(rows)
    assert all(row.schema_version == PHASE4_PERSONA_SCHEMA_VERSION for row in rows)
    assert all(row.surface == "execution" for row in rows)
    assert all(row.fixture_family.endswith("_class") for row in rows)
    assert all(row.runtime_scope == ("provider_free",) for row in rows)
    assert {row.persona_class for row in rows} <= set(PERSONA_CLASSES)
    assert all(row.prompt_variant_class for row in rows)
    assert all(row.metadata_source in {"canonical_fixture", "compatibility_adapter"} for row in rows)
    assert {row.scenario for row in rows} == {
        "valid_final_plan_ready_to_execute",
        "invalid_gpd_verify_work_surface",
        "invalid_gpd_verify_phase_surface",
        "prose_success_no_return",
        "multiple_gpd_returns",
        "unfenced_raw_return_candidate",
        "empty_files_written_required_artifact",
        "omitted_files_written_field",
        "stale_artifact",
        "wrong_sibling_artifact",
        "checkpoint_missing_bounded_context",
        "checkpoint_with_bounded_context",
        "intermediate_plan_cannot_complete_phase",
        "applicator_result_prose_only",
    }
    assert all(row.provider_launch_allowed is False for row in rows)
    assert all(row.network_allowed is False for row in rows)
    assert all(row.raw_artifacts_allowed is False for row in rows)
    assert all(row.behavior_contract_id for row in rows)
    assert {row.expected_smoothness_class for row in rows} <= set(SMOOTHNESS_CLASSES)
    assert {row.expected_schema_wrestling_class for row in rows} <= set(SCHEMA_WRESTLING_CLASSES)
    assert {row.expected_next_up_specificity_class for row in rows} <= set(NEXT_UP_SPECIFICITY_CLASSES)
    assert {row.expected_mutation_guard_class for row in rows} <= {"no_write", "expected_write_only"}
    for row in rows:
        assert all((REPO_ROOT / owner).exists() for owner in row.source_owners)
        assert all((REPO_ROOT / owner).exists() for owner in row.test_owners)

    split_owner = "src/gpd/specs/workflows/execute-phase/wave-return-checkpoint.md"
    if (REPO_ROOT / split_owner).is_file():
        assert split_owner in rows_by_scenario["prose_success_no_return"].source_owners
        assert split_owner in rows_by_scenario["stale_artifact"].source_owners
        assert split_owner in rows_by_scenario["checkpoint_missing_bounded_context"].source_owners


@pytest.mark.parametrize("row", execution_replay_rows(), ids=lambda row: f"{row.row_id}-{row.scenario}")
def test_phase4_persona_execution_replay(
    row: ExecutionReplayRow,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GPD_DATA_DIR", str(tmp_path / ".gpd-data"))

    outcome = score_execution_replay_row(row, tmp_path)

    assert outcome.row_id == row.row_id
    assert outcome.finding_id == row.expected_finding
    assert outcome.result_class == row.expected_result_class
    assert outcome.accepted is row.expected_accepted
    assert outcome.mutated is row.expected_mutated
    assert outcome.provider_launch_allowed is False
    assert outcome.network_allowed is False
    assert outcome.raw_artifacts_allowed is False
    if not row.mutation_allowed:
        assert outcome.mutated is False
    if not row.expected_accepted:
        assert row.expected_finding in outcome.failure_classes
    if row.expected_state_status_class is not None:
        assert outcome.state_status_class == row.expected_state_status_class
    if row.expected_next_action_class is not None:
        assert outcome.next_action_class == row.expected_next_action_class
    assert _smoothness_class(row, outcome) == row.expected_smoothness_class
    assert _schema_wrestling_class(outcome) == row.expected_schema_wrestling_class
    if outcome.next_action_class is not None:
        assert _next_up_specificity_class(outcome.next_action_class) == row.expected_next_up_specificity_class
    assert _mutation_guard_class(row, outcome) == row.expected_mutation_guard_class
    _assert_metric_bounds(row, outcome)
    _assert_behavior_score(row, outcome)


def test_phase4_execution_replay_rows_pin_high_risk_behavior_classes(tmp_path: Path) -> None:
    rows = {row.scenario: row for row in execution_replay_rows()}

    for scenario in {
        "prose_success_no_return",
        "multiple_gpd_returns",
        "unfenced_raw_return_candidate",
        "omitted_files_written_field",
        "applicator_result_prose_only",
    }:
        outcome = score_execution_replay_row(rows[scenario], tmp_path / scenario)
        score = score_behavior_metrics(rows[scenario], outcome)

        assert outcome.accepted is False
        assert outcome.mutated is False
        assert score.metric_counts["schema_repair_loop_count"] >= 1
        assert "return_envelope" in score.structured_authority_sources
        assert "return_repair_classifier" in score.structured_authority_sources

    for scenario in {"stale_artifact", "wrong_sibling_artifact"}:
        outcome = score_execution_replay_row(rows[scenario], tmp_path / scenario)
        score = score_behavior_metrics(rows[scenario], outcome)

        assert outcome.accepted is False
        assert outcome.mutated is False
        assert score.metric_counts["stale_artifact_trust_count"] == 0
        assert "artifact_gate" in score.structured_authority_sources

    invalid_phase = score_execution_replay_row(rows["invalid_gpd_verify_phase_surface"], tmp_path / "invalid-phase")
    assert "structural_verify_phase" in invalid_phase.failure_classes

    checkpoint = score_execution_replay_row(rows["checkpoint_missing_bounded_context"], tmp_path / "checkpoint")
    checkpoint_score = score_behavior_metrics(rows["checkpoint_missing_bounded_context"], checkpoint)
    assert checkpoint.accepted is False
    assert checkpoint.mutated is False
    assert "bounded_continuation" in checkpoint_score.structured_authority_sources


def _smoothness_class(row: ExecutionReplayRow, outcome) -> str:
    if outcome.mutated and not row.mutation_allowed:
        return "regressed"
    if _schema_wrestling_class(outcome) != "none":
        return "clunky"
    if outcome.result_class in {"accepted", "checkpoint_recorded"}:
        return "smooth"
    if row.scenario in {"invalid_gpd_verify_work_surface", "invalid_gpd_verify_phase_surface"}:
        return "acceptable"
    if outcome.result_class == "blocked":
        return "acceptable"
    return "smooth"


def _schema_wrestling_class(outcome) -> str:
    classes = set(outcome.failure_classes)
    classes.add(outcome.finding_id)
    if {"return_malformed_blocking", "applicator_output_only"}.intersection(classes):
        return "high"
    if {"return_missing", "return_malformed_repairable", "unfenced_candidate"}.intersection(classes):
        return "minor"
    return "none"


def _next_up_specificity_class(next_action_class: str | None) -> str:
    if next_action_class is None or next_action_class == "unknown":
        return "none"
    if next_action_class == "runtime_verify_work":
        return "runtime_verify_work"
    if next_action_class == "resume_work":
        return "bounded_resume"
    return "concrete_command"


def _mutation_guard_class(row: ExecutionReplayRow, outcome) -> str:
    if outcome.mutated and not row.mutation_allowed:
        return "unexpected_write"
    if outcome.mutated:
        return "expected_write_only"
    return "no_write"


def _assert_metric_bounds(row: ExecutionReplayRow, outcome) -> None:
    score = score_behavior_metrics(row, outcome)
    for metric_name, expected_count in row.expected_metric_bounds:
        observed = _observed_metric_count(metric_name, row, outcome)
        shared_observed = score.metric_counts[metric_name]
        if expected_count == 0:
            assert observed == expected_count
            assert shared_observed == expected_count
        else:
            assert observed >= expected_count
            assert shared_observed >= expected_count


def _assert_behavior_score(row: ExecutionReplayRow, outcome) -> None:
    score = score_behavior_metrics(row, outcome)

    assert score.row_id == row.row_id
    assert score.surface == row.surface
    assert score.scenario == row.scenario
    assert score.metric_classes["schema_wrestling_class"] == row.expected_schema_wrestling_class
    assert score.metric_classes["next_up_specificity_class"] == row.expected_next_up_specificity_class
    assert score.metric_classes["mutation_guard_class"] == row.expected_mutation_guard_class
    assert all(isinstance(value, int) for value in score.metric_counts.values())
    assert all(isinstance(value, str) for value in score.metric_classes.values())


def _observed_metric_count(metric_name: str, row: ExecutionReplayRow, outcome) -> int:
    match metric_name:
        case "invalid_command_suggestion_count":
            return 0
        case "prose_claim_mismatch_count":
            return int(row.scenario in {"prose_success_no_return", "multiple_gpd_returns", "applicator_result_prose_only"})
        case "schema_repair_loop_count":
            return int(_schema_wrestling_class(outcome) != "none")
        case "stale_artifact_trust_count":
            return 0
        case "structured_authority_coverage":
            return int(
                outcome.accepted
                or bool(outcome.failure_classes)
                or bool(outcome.applied_operations)
                or bool(outcome.checked_artifact_classes)
            )
        case "unsupported_completion_claim_count":
            return int(row.scenario in {"intermediate_plan_cannot_complete_phase", "applicator_result_prose_only"})
        case "unexpected_write_count":
            return int(outcome.mutated and not row.mutation_allowed)
    raise AssertionError(f"unhandled execution behavior metric: {metric_name}")
