"""Provider-free Phase 4 planning persona replay tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers.phase4_persona.planning import (
    PlanningReplayRow,
    load_planning_replay_rows,
    score_planning_replay_row,
)


def test_phase4_planning_persona_rows_are_provider_free_and_class_only() -> None:
    rows = load_planning_replay_rows()

    assert len(rows) == 5
    assert [row.row_id for row in rows] == [f"P4-PLAN-{index:02d}" for index in range(1, 6)]
    assert len({row.scenario for row in rows}) == len(rows)
    assert all(row.provider_launch_allowed is False for row in rows)
    assert all(row.network_allowed is False for row in rows)
    assert all(row.raw_artifacts_allowed is False for row in rows)
    assert {row.expected_finding for row in rows} == {
        "plan_phase_bootstrap_lazy_loading",
        "missing_phase_no_target_invention",
        "project_contract_authority_block",
        "dirty_worktree_hard_stop",
        "proof_bearing_checker_audit_visibility",
    }


@pytest.mark.parametrize(
    "row",
    load_planning_replay_rows(),
    ids=lambda row: f"{row.row_id}-{row.scenario}",
)
def test_phase4_planning_persona_replay_rows(
    row: PlanningReplayRow,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GPD_DATA_DIR", str(tmp_path / ".gpd-data"))

    outcome = score_planning_replay_row(row, tmp_path)

    assert outcome.provider_launch_allowed is False
    assert outcome.finding_id == row.expected_finding
    assert outcome.result_class == row.expected_result_class
    assert row.expected_finding in outcome.failure_classes
    assert outcome.mutated is row.expected_mutated
    assert outcome.evidence_classes
    assert all("/Users/" not in evidence_class for evidence_class in outcome.evidence_classes)
