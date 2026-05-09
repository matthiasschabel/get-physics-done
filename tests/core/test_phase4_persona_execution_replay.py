"""Provider-free Phase 4 execution and child-return replay tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers.phase4_persona.execution import (
    ExecutionReplayRow,
    execution_replay_rows,
    score_execution_replay_row,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_phase4_execution_replay_rows_are_provider_free_and_owned() -> None:
    rows = execution_replay_rows()

    assert len(rows) == 14
    assert len({row.row_id for row in rows}) == len(rows)
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
    for row in rows:
        assert all((REPO_ROOT / owner).exists() for owner in row.source_owners)
        assert all((REPO_ROOT / owner).exists() for owner in row.test_owners)


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
