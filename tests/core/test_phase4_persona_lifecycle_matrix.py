"""Provider-free Phase 4 persona lifecycle replay smoke."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers.phase4_persona.replay import PersonaRow, load_phase4_rows, score_phase4_row

_EXECUTION_COMPLETION_REGISTRY_ROWS = (
    PersonaRow(
        row_id="P4-EXEC-05",
        surface="execution",
        scenario="intermediate_plan_cannot_complete_phase",
        expected_finding="intermediate_plan_completion_blocked",
        expected_result_class="blocked_no_mutation",
        expected_state_status_class="unchanged",
        expected_next_action_class="continue_phase_execution",
    ),
    PersonaRow(
        row_id="P4-COMP-01",
        surface="completion",
        scenario="missing_verification_blocks_closeout",
        expected_finding="verification_missing",
        expected_result_class="blocked_no_mutation",
        expected_state_status_class="unchanged",
        expected_next_action_class="run_verify_work",
    ),
    PersonaRow(
        row_id="P4-COMP-02",
        surface="completion",
        scenario="non_passing_verification_records_blocked",
        expected_finding="verification_non_passing",
        expected_result_class="blocked_no_mutation",
        expected_state_status_class="blocked",
        expected_next_action_class="repair_verification_gaps",
    ),
    PersonaRow(
        row_id="P4-COMP-03",
        surface="completion",
        scenario="active_bounded_segment_routes_resume_work",
        expected_finding="closeout_authority_blocks_premature_completion",
        expected_result_class="blocked_no_mutation",
        expected_state_status_class="unchanged",
        expected_next_action_class="gpd_resume_work",
    ),
    PersonaRow(
        row_id="P4-COMP-04",
        surface="completion",
        scenario="passed_verification_closeout_readiness_read_only",
        expected_finding="closeout_ready",
        expected_result_class="ready_read_only_no_mutation",
        expected_state_status_class="unchanged",
        expected_next_action_class="phase_complete_available",
    ),
)


def test_phase4_persona_lifecycle_matrix_rows_are_provider_free_and_class_only() -> None:
    rows = load_phase4_rows()

    assert len(rows) == 5
    assert {row.surface for row in rows} == {"execution", "completion"}
    assert all(row.provider_launch_allowed is False for row in rows)
    assert all(row.network_allowed is False for row in rows)
    assert all(row.raw_artifacts_allowed is False for row in rows)
    assert {row.expected_finding for row in rows} >= {
        "invalid_verify_command_surface",
        "return_missing",
        "artifact_stale",
        "checkpoint_missing_bounded_segment",
        "closeout_authority_blocks_premature_completion",
    }


@pytest.mark.parametrize("row", load_phase4_rows(), ids=lambda row: f"{row.row_id}-{row.scenario}")
def test_phase4_persona_lifecycle_matrix(
    row: PersonaRow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outcome = score_phase4_row(row, tmp_path, monkeypatch)

    assert outcome.provider_launch_allowed is False
    assert outcome.finding_id == row.expected_finding
    assert outcome.result_class == row.expected_result_class
    assert row.expected_finding in outcome.failure_classes
    assert outcome.accepted is False
    if not row.mutation_allowed:
        assert outcome.mutated is False
    if row.expected_state_status_class is not None:
        assert outcome.state_status_class == row.expected_state_status_class
    if row.expected_next_action_class is not None:
        assert outcome.next_action_class == row.expected_next_action_class


@pytest.mark.parametrize(
    "row",
    _EXECUTION_COMPLETION_REGISTRY_ROWS,
    ids=lambda row: f"{row.row_id}-{row.scenario}",
)
def test_phase4_execution_completion_registry_rows_score_through_shared_replay(
    row: PersonaRow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outcome = score_phase4_row(row, tmp_path, monkeypatch)

    assert outcome.finding_id == row.expected_finding
    assert outcome.result_class == row.expected_result_class
    assert row.expected_finding in outcome.failure_classes
    assert outcome.mutated is False
    assert outcome.state_status_class == row.expected_state_status_class
    assert outcome.next_action_class == row.expected_next_action_class
    assert outcome.accepted is (row.expected_result_class == "ready_read_only_no_mutation")
