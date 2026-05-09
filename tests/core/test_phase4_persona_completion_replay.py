"""Provider-free Phase 4 completion and verification replay rows."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers.phase4_persona.completion import (
    SCHEMA_VERSION,
    CompletionReplayRow,
    completion_replay_rows,
    score_completion_replay_row,
)


def test_phase4_completion_replay_rows_are_provider_free_and_owned() -> None:
    rows = completion_replay_rows()

    assert len(rows) == 9
    assert {row.row_id for row in rows} == {
        "P4-COMP-01",
        "P4-COMP-02",
        "P4-COMP-03",
        "P4-COMP-04",
        "P4-COMP-05",
        "P4-COMP-06",
        "P4-COMP-07",
        "P4-COMP-08",
        "P4-COMP-09",
    }
    assert all(row.schema_version == SCHEMA_VERSION for row in rows)
    assert all(row.surface == "completion" for row in rows)
    assert all(row.runtime_scope == "provider_free" for row in rows)
    assert all(row.provider_launch_allowed is False for row in rows)
    assert all(row.network_allowed is False for row in rows)
    assert all(row.raw_artifacts_allowed is False for row in rows)

    repo_root = Path(__file__).resolve().parents[2]
    for row in rows:
        for owner in (*row.source_owners, *row.test_owners):
            assert (repo_root / owner).exists(), f"{row.row_id} owner missing: {owner}"


def test_phase4_completion_replay_rows_cover_required_completion_cases() -> None:
    rows = completion_replay_rows()

    assert {row.expected_finding for row in rows} >= {
        "missing_verification_blocks_closeout",
        "gaps_found_verification_blocks",
        "human_needed_verification_blocks",
        "expert_needed_verification_blocks",
        "passed_verification_allows_readiness",
        "bounded_segment_blocks_closeout",
        "proof_redteam_not_passed_blocks_closeout",
        "runtime_verify_work_suggestion",
        "closeout_readiness_read_only",
    }


@pytest.mark.parametrize("row", completion_replay_rows(), ids=lambda row: f"{row.row_id}-{row.scenario}")
def test_phase4_persona_completion_replay(
    row: CompletionReplayRow,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcome = score_completion_replay_row(row, tmp_path, monkeypatch)

    assert outcome.provider_launch_allowed is False
    assert outcome.network_allowed is False
    assert outcome.raw_artifacts_allowed is False
    assert outcome.finding_id == row.expected_finding
    assert outcome.result_class == row.expected_result_class
    assert row.expected_finding in outcome.finding_id
    assert outcome.read_only is True
    if row.expected_ready is not None:
        assert outcome.ready is row.expected_ready
    if row.expected_state_status_class is not None:
        assert outcome.state_status_class == row.expected_state_status_class
    if row.expected_next_action_class is not None:
        assert outcome.next_action_class == row.expected_next_action_class
    if row.expect_no_mutation:
        assert outcome.mutated is False


def test_phase4_completion_runtime_verify_work_row_rejects_structural_verify_phase(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = next(row for row in completion_replay_rows() if row.row_id == "P4-COMP-08")

    outcome = score_completion_replay_row(row, tmp_path, monkeypatch)

    assert outcome.commands
    assert all("verify-work" in command for command in outcome.commands)
    assert all("gpd verify phase" not in command for command in outcome.commands)
    assert outcome.failure_classes == ("runtime_verify_work", "no_structural_verify_phase", "read_only")


def test_phase4_completion_readiness_row_does_not_mutate_state_roadmap_or_checkpoint_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = next(row for row in completion_replay_rows() if row.row_id == "P4-COMP-09")

    outcome = score_completion_replay_row(row, tmp_path, monkeypatch)

    assert outcome.ready is True
    assert outcome.mutated is False
    assert outcome.result_class == "read_only_ready_closeout"
    assert outcome.next_action_class == "phase_complete"
