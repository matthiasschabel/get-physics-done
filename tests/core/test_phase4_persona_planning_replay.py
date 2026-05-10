"""Provider-free Phase 4 planning persona replay tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers.phase4_persona.behavior_metrics import assert_behavior_contract
from tests.helpers.phase4_persona.matrix import (
    NEXT_UP_SPECIFICITY_CLASSES,
    PERSONA_CLASSES,
    SCHEMA_WRESTLING_CLASSES,
    SMOOTHNESS_CLASSES,
)
from tests.helpers.phase4_persona.planning import (
    PlanningReplayRow,
    load_planning_replay_rows,
    score_planning_replay_row,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_phase4_planning_persona_rows_are_provider_free_and_class_only() -> None:
    rows = load_planning_replay_rows()

    assert len(rows) == 5
    assert [row.row_id for row in rows] == [f"P4-PLAN-{index:02d}" for index in range(1, 6)]
    assert all(row.surface == "planning" for row in rows)
    assert all(row.fixture_family.endswith("_class") for row in rows)
    assert all(row.runtime_scope == ("provider_free",) for row in rows)
    assert {row.persona_class for row in rows} <= set(PERSONA_CLASSES)
    assert all(row.prompt_variant_class for row in rows)
    assert all(row.metadata_source in {"canonical_fixture", "compatibility_adapter"} for row in rows)
    assert len({row.scenario for row in rows}) == len(rows)
    assert all(row.provider_launch_allowed is False for row in rows)
    assert all(row.network_allowed is False for row in rows)
    assert all(row.raw_artifacts_allowed is False for row in rows)
    assert all(row.behavior_contract_id for row in rows)
    assert {row.expected_smoothness_class for row in rows} <= set(SMOOTHNESS_CLASSES)
    assert {row.expected_schema_wrestling_class for row in rows} <= set(SCHEMA_WRESTLING_CLASSES)
    assert {row.expected_next_up_specificity_class for row in rows} <= set(NEXT_UP_SPECIFICITY_CLASSES)
    assert all(row.expected_mutation_guard_class == "no_write" for row in rows)
    assert {row.expected_finding for row in rows} == {
        "plan_phase_bootstrap_lazy_loading",
        "missing_phase_no_target_invention",
        "project_contract_authority_block",
        "dirty_worktree_hard_stop",
        "proof_bearing_checker_audit_visibility",
    }
    for row in rows:
        assert all((REPO_ROOT / owner).exists() for owner in row.source_owners)
        assert all((REPO_ROOT / owner).exists() for owner in row.test_owners)


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
    assert_behavior_contract(row, outcome)
