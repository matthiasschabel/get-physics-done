"""Schema checks for the provider-free Phase 10 lifecycle matrix fixture."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.helpers.live_audit_harness.phase9_schema import (
    LAUNCH_POLICY,
    REQUIRED_SIDECARS,
    ROW_ROLES,
    SCHEMA_ID,
)
from tests.helpers.live_audit_harness.phase10_lifecycle import (
    EXPECTED_PHASE10_SCENARIO_IDS,
    PHASE10_LIFECYCLE_MATRIX_ID,
    default_phase10_lifecycle_matrix_path,
    load_phase10_lifecycle_matrix,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_phase10_lifecycle_matrix_loads_through_phase9_provider_free_schema() -> None:
    matrix = load_phase10_lifecycle_matrix(default_phase10_lifecycle_matrix_path(_REPO_ROOT))

    assert matrix.schema == SCHEMA_ID
    assert matrix.matrix_id == PHASE10_LIFECYCLE_MATRIX_ID
    assert set(matrix.required_sidecars) == REQUIRED_SIDECARS
    assert tuple(row.scenario_id for row in matrix.rows) == EXPECTED_PHASE10_SCENARIO_IDS
    assert {row.row_role for row in matrix.rows} == ROW_ROLES
    assert {row.runtime for row in matrix.rows} == {"claude-code", "codex", "gemini", "opencode"}
    assert {row.behavior_contract_id for row in matrix.rows} == {
        contract.behavior_contract_id for contract in matrix.behavior_contracts
    }
    assert {row.sidecar_profile_id for row in matrix.rows} == {
        profile.sidecar_profile_id for profile in matrix.sidecar_profiles
    }


def test_phase10_lifecycle_rows_are_default_pytest_fake_provider_free() -> None:
    matrix = load_phase10_lifecycle_matrix(default_phase10_lifecycle_matrix_path(_REPO_ROOT))

    assert matrix.rows
    assert {row.launch_policy for row in matrix.rows} == {LAUNCH_POLICY}
    assert {row.default_pytest for row in matrix.rows} == {True}
    assert {row.provider_subprocess_allowed for row in matrix.rows} == {False}
    assert {row.network_allowed for row in matrix.rows} == {False}
    assert {row.required_pytest_markers for row in matrix.rows} == {()}
    assert all(set(row.required_sidecars) == REQUIRED_SIDECARS for row in matrix.rows)
    assert all(set(contract.required_sidecars) == REQUIRED_SIDECARS for contract in matrix.behavior_contracts)


def test_phase10_lifecycle_loader_requires_exact_life_scenario_ids(tmp_path: Path) -> None:
    payload = json.loads(default_phase10_lifecycle_matrix_path(_REPO_ROOT).read_text(encoding="utf-8"))
    for row in payload["rows"]:
        if row["scenario_id"] == "LIFE-VERIFY-GAPS":
            row["scenario_id"] = "LIFE-VERIFY-GAPZ"
            break
    path = tmp_path / "missing-scenario.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="expected LIFE scenario"):
        load_phase10_lifecycle_matrix(path)
