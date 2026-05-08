"""Schema validation tests for the provider-free Phase 9 behavior matrix."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import cast

import pytest

from gpd.adapters.runtime_catalog import list_runtime_names
from tests.helpers.live_audit_harness.phase9_schema import (
    LAUNCH_POLICY,
    REQUIRED_SIDECARS,
    ROW_ROLES,
    RUNTIMES,
    SCHEMA_ID,
    Phase9BehaviorMatrix,
    default_phase9_behavior_matrix_path,
    load_phase9_behavior_matrix,
    validate_phase9_behavior_matrix,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EXPECTED_CONTRACTS = {
    "beginner_menu_no_writes",
    "stale_artifact_not_trusted",
    "stop_honored",
    "setup_refusal_class_only",
    "execution_claim_requires_evidence",
    "child_checkpoint_not_final",
    "wrong_workspace_refused",
    "prompt_budget_stress",
    "opencode_deferred_visible",
    "sidecar_bundle_integrity",
}
_EXPECTED_SENTINEL_FINDINGS = {
    "stop_ignored.post_stop_work",
    "stale_artifact_trusted.trusted_stale_artifact",
    "wrong_workspace_write.forbidden_write",
    "ambiguous_child_handoff.missing_typed_return",
    "prompt_budget_leakage.hidden_prompt_leak",
    "fake_execution_claim.unproven_execution",
    "setup_refusal.raw_auth_or_account_leak",
    "opencode_deferred.claimed_live_ready",
    "invalid_evidence.missing_required_sidecar",
}


def _fixture_payload() -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads(default_phase9_behavior_matrix_path(_REPO_ROOT).read_text(encoding="utf-8")),
    )


def _rows(payload: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], payload["rows"])


def _contracts(payload: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], payload["behavior_contracts"])


def _profiles(payload: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], payload["sidecar_profiles"])


def _profile_by_id(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    return {cast(str, profile["sidecar_profile_id"]): profile for profile in _profiles(payload)}


def _first_row(payload: dict[str, object], *, row_role: str = "green") -> dict[str, object]:
    for row in _rows(payload):
        if row["row_role"] == row_role:
            return row
    raise AssertionError(f"fixture has no row_role={row_role!r}")


def test_default_phase9_behavior_matrix_fixture_validates_provider_free_contract() -> None:
    matrix = load_phase9_behavior_matrix(default_phase9_behavior_matrix_path(_REPO_ROOT))

    assert isinstance(matrix, Phase9BehaviorMatrix)
    assert matrix.schema == SCHEMA_ID
    assert RUNTIMES == tuple(list_runtime_names())
    assert matrix.default_pytest_policy.launch_policy == LAUNCH_POLICY
    assert matrix.default_pytest_policy.default_pytest is True
    assert matrix.default_pytest_policy.provider_subprocess_allowed is False
    assert matrix.default_pytest_policy.network_allowed is False
    assert matrix.required_sidecars == (
        "status.json",
        "stdout.jsonl",
        "normalized-events.jsonl",
        "final.md",
        "write-classification.json",
        "evidence-packet.json",
    )

    assert {contract.behavior_contract_id for contract in matrix.behavior_contracts} == _EXPECTED_CONTRACTS
    assert {row.row_role for row in matrix.rows} == ROW_ROLES
    assert all(row.row_id.startswith(f"P9-{row.runtime.upper()}-") for row in matrix.rows)
    assert all(set(row.required_sidecars) == REQUIRED_SIDECARS for row in matrix.rows)
    assert all(set(contract.required_sidecars) == REQUIRED_SIDECARS for contract in matrix.behavior_contracts)


def test_phase9_rows_are_default_pytest_fake_provider_free_rows() -> None:
    matrix = load_phase9_behavior_matrix(default_phase9_behavior_matrix_path(_REPO_ROOT))

    assert matrix.rows
    assert {row.launch_policy for row in matrix.rows} == {"fake"}
    assert {row.default_pytest for row in matrix.rows} == {True}
    assert {row.provider_subprocess_allowed for row in matrix.rows} == {False}
    assert {row.network_allowed for row in matrix.rows} == {False}
    assert {row.required_pytest_markers for row in matrix.rows} == {()}


def test_phase9_green_rows_cover_core_behavior_contracts_with_green_profiles() -> None:
    matrix = load_phase9_behavior_matrix(default_phase9_behavior_matrix_path(_REPO_ROOT))
    contracts = {contract.behavior_contract_id: contract for contract in matrix.behavior_contracts}
    profiles = {profile.sidecar_profile_id: profile for profile in matrix.sidecar_profiles}
    green_rows = [row for row in matrix.rows if row.row_role == "green"]

    assert {row.behavior_contract_id for row in green_rows} == _EXPECTED_CONTRACTS
    for row in green_rows:
        contract = contracts[row.behavior_contract_id]
        profile = profiles[row.sidecar_profile_id]
        assert profile.expected_behavior_result_class == "green"
        assert set(contract.required_behavior_classes).issubset(profile.observed_behavior_classes)
        assert set(contract.forbidden_behavior_classes).isdisjoint(profile.observed_behavior_classes)
        assert profile.expected_finding_ids == ()
        assert profile.expected_schema_failure_classes == ()


def test_phase9_bad_behavior_sentinels_are_schema_valid_non_green_controls() -> None:
    matrix = load_phase9_behavior_matrix(default_phase9_behavior_matrix_path(_REPO_ROOT))
    profiles = {profile.sidecar_profile_id: profile for profile in matrix.sidecar_profiles}
    sentinel_rows = [row for row in matrix.rows if row.row_role == "bad_behavior_sentinel"]
    finding_ids = set()
    schema_failure_classes = set()

    assert sentinel_rows
    for row in sentinel_rows:
        profile = profiles[row.sidecar_profile_id]
        assert profile.expected_behavior_result_class in {"yellow", "red", "invalid_evidence"}
        assert profile.expected_finding_ids or profile.expected_schema_failure_classes
        finding_ids.update(profile.expected_finding_ids)
        schema_failure_classes.update(profile.expected_schema_failure_classes)

    assert finding_ids == _EXPECTED_SENTINEL_FINDINGS
    assert schema_failure_classes == {"missing_required_sidecar"}


@pytest.mark.parametrize(
    ("field_name", "bad_value", "match"),
    [
        ("launch_policy", "manual_live", "launch_policy"),
        ("default_pytest", False, "default_pytest"),
        ("provider_subprocess_allowed", True, "provider_subprocess_allowed"),
        ("network_allowed", True, "network_allowed"),
        ("required_pytest_markers", ["live_provider"], "required_pytest_markers"),
    ],
)
def test_validate_phase9_behavior_matrix_rejects_rows_that_escape_provider_free_contract(
    field_name: str,
    bad_value: object,
    match: str,
) -> None:
    payload = _fixture_payload()
    _first_row(payload)[field_name] = bad_value

    with pytest.raises(ValueError, match=match):
        validate_phase9_behavior_matrix(payload)


def test_validate_phase9_behavior_matrix_rejects_missing_required_row_sidecar() -> None:
    payload = _fixture_payload()
    sidecars = cast(list[str], _first_row(payload)["required_sidecars"])
    sidecars.remove("evidence-packet.json")

    with pytest.raises(ValueError, match="six required sidecars"):
        validate_phase9_behavior_matrix(payload)


def test_validate_phase9_behavior_matrix_rejects_missing_required_contract_sidecar() -> None:
    payload = _fixture_payload()
    sidecars = cast(list[str], _contracts(payload)[0]["required_sidecars"])
    sidecars.remove("normalized-events.jsonl")

    with pytest.raises(ValueError, match="six required sidecars"):
        validate_phase9_behavior_matrix(payload)


def test_validate_phase9_behavior_matrix_rejects_green_profile_missing_required_behavior_class() -> None:
    payload = _fixture_payload()
    row = _first_row(payload)
    profile = _profile_by_id(payload)[cast(str, row["sidecar_profile_id"])]
    observed_classes = cast(list[str], profile["observed_behavior_classes"])
    observed_classes.remove("workspace_classified_projectless")

    with pytest.raises(ValueError, match="missing required behavior classes"):
        validate_phase9_behavior_matrix(payload)


def test_validate_phase9_behavior_matrix_rejects_green_profile_with_expected_failure() -> None:
    payload = _fixture_payload()
    row = _first_row(payload)
    profile = _profile_by_id(payload)[cast(str, row["sidecar_profile_id"])]
    cast(list[str], profile["expected_finding_ids"]).append("fake_execution_claim.unproven_execution")

    with pytest.raises(ValueError, match="green profiles must not expect failures"):
        validate_phase9_behavior_matrix(payload)


def test_validate_phase9_behavior_matrix_rejects_bad_sentinel_with_green_profile() -> None:
    payload = _fixture_payload()
    sentinel = _first_row(payload, row_role="bad_behavior_sentinel")
    sentinel["sidecar_profile_id"] = cast(str, _first_row(payload)["sidecar_profile_id"])

    with pytest.raises(ValueError, match="non-green sidecar profile"):
        validate_phase9_behavior_matrix(payload)


def test_validate_phase9_behavior_matrix_rejects_unknown_profile_reference() -> None:
    payload = _fixture_payload()
    _first_row(payload)["sidecar_profile_id"] = "missing_profile"

    with pytest.raises(ValueError, match="sidecar_profile_id"):
        validate_phase9_behavior_matrix(payload)


def test_validate_phase9_behavior_matrix_rejects_duplicate_row_id() -> None:
    payload = _fixture_payload()
    _rows(payload)[1]["row_id"] = _rows(payload)[0]["row_id"]

    with pytest.raises(ValueError, match="duplicate row_id"):
        validate_phase9_behavior_matrix(payload)


def test_validate_phase9_behavior_matrix_rejects_row_id_runtime_mismatch() -> None:
    payload = _fixture_payload()
    _first_row(payload)["runtime"] = "opencode"

    with pytest.raises(ValueError, match="row_id"):
        validate_phase9_behavior_matrix(payload)


def test_validate_phase9_behavior_matrix_rejects_non_class_behavior_values() -> None:
    payload = _fixture_payload()
    cast(list[str], _contracts(payload)[0]["required_behavior_classes"]).append("asks user for raw transcript")

    with pytest.raises(ValueError, match="class token"):
        validate_phase9_behavior_matrix(payload)


@pytest.mark.parametrize("field_name", ["raw_auth_state", "provider_output", "argv", "env", "home_path"])
def test_validate_phase9_behavior_matrix_rejects_raw_fields_recursively(field_name: str) -> None:
    payload = _fixture_payload()
    _profiles(payload)[0][field_name] = "private value would go here"

    with pytest.raises(ValueError, match="forbidden raw auth/env/path/provider-output field"):
        validate_phase9_behavior_matrix(payload)


def test_phase9_fixture_keeps_runtime_coverage_compact_and_useful() -> None:
    matrix = load_phase9_behavior_matrix(default_phase9_behavior_matrix_path(_REPO_ROOT))
    role_counts = Counter(row.row_role for row in matrix.rows)

    assert role_counts["green"] == len(_EXPECTED_CONTRACTS)
    assert role_counts["bad_behavior_sentinel"] == len(_EXPECTED_SENTINEL_FINDINGS)
    assert {row.runtime for row in matrix.rows} == set(RUNTIMES)
