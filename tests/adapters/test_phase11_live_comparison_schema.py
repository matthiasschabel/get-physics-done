"""Schema checks for the provider-free Phase 11 live-comparison matrix."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from gpd.adapters.runtime_catalog import list_runtime_names
from tests.helpers.live_audit_harness.phase11_comparison import (
    Phase11LiveComparisonMatrix,
    default_phase11_live_comparison_matrix_path,
    load_phase11_live_comparison_matrix,
    validate_phase11_live_comparison_matrix,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA_ID = "phase11.live-comparison-matrix.v1"
_MATRIX_ID = "phase11-live-comparison-class-matrix-v1"
_SOURCE_CLASSES = {"manual_live", "nightly_live"}
_ROW_IDS = ("P11-CODEX-MANUAL-LP-001", "P11-CODEX-NIGHTLY-LP-001")
_REQUIRED_COMPARISON_CLASSES = {
    "class_only_result_class",
    "class_only_finding_classes",
    "class_only_retention_refs",
}


def _fixture_payload() -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads(default_phase11_live_comparison_matrix_path(_REPO_ROOT).read_text(encoding="utf-8")),
    )


def _rows(payload: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], payload["rows"])


def _contracts(payload: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], payload["row_contracts"])


def test_phase11_live_comparison_fixture_validates_class_only_contract() -> None:
    matrix = load_phase11_live_comparison_matrix(default_phase11_live_comparison_matrix_path(_REPO_ROOT))

    assert isinstance(matrix, Phase11LiveComparisonMatrix)
    assert matrix.schema == _SCHEMA_ID
    assert matrix.matrix_id == _MATRIX_ID
    assert {source.source_class for source in matrix.source_classes} == _SOURCE_CLASSES
    assert tuple(row.row_id for row in matrix.rows) == _ROW_IDS
    assert {row.runtime for row in matrix.rows} <= set(list_runtime_names())


def test_phase11_manual_and_nightly_sources_are_default_pytest_provider_free() -> None:
    matrix = load_phase11_live_comparison_matrix(default_phase11_live_comparison_matrix_path(_REPO_ROOT))
    policy = matrix.default_pytest_policy

    assert policy.launch_policy == "fake"
    assert policy.default_pytest is True
    assert policy.provider_subprocess_allowed is False
    assert policy.network_allowed is False
    assert policy.required_pytest_markers == ()
    assert {row.source_class for row in matrix.rows} == _SOURCE_CLASSES
    assert {row.launch_policy for row in matrix.rows} == {"fake"}
    assert {row.default_pytest for row in matrix.rows} == {True}
    assert {row.provider_subprocess_allowed for row in matrix.rows} == {False}
    assert {row.network_allowed for row in matrix.rows} == {False}
    assert {row.required_pytest_markers for row in matrix.rows} == {()}


def test_phase11_rows_follow_lp_style_row_contracts() -> None:
    matrix = load_phase11_live_comparison_matrix(default_phase11_live_comparison_matrix_path(_REPO_ROOT))
    contract_by_id = {contract.row_contract_id: contract for contract in matrix.row_contracts}

    assert set(contract_by_id) == {"lp_phase11_live_comparison_provider_free"}
    for row in matrix.rows:
        contract = contract_by_id[row.row_contract_id]
        assert contract.contract_style == "launch_policy_row_contract"
        assert set(contract.required_source_classes) == _SOURCE_CLASSES
        assert row.source_class in contract.required_source_classes
        assert row.launch_policy == contract.launch_policy
        assert row.default_pytest == contract.default_pytest
        assert row.provider_subprocess_allowed == contract.provider_subprocess_allowed
        assert row.network_allowed == contract.network_allowed
        assert row.required_pytest_markers == contract.required_pytest_markers
        assert _REQUIRED_COMPARISON_CLASSES.issubset(row.comparison_classes)
        assert set(contract.forbidden_comparison_classes).isdisjoint(row.comparison_classes)


@pytest.mark.parametrize("field_name", ["raw_transcript", "provider_output", "auth_path", "env", "home_path"])
def test_validate_phase11_live_comparison_rejects_raw_fields_recursively(field_name: str) -> None:
    payload = _fixture_payload()
    _rows(payload)[0]["class_only_probe"] = {"nested": {field_name: "private value would go here"}}

    with pytest.raises(ValueError, match="raw|provider|auth|path|env"):
        validate_phase11_live_comparison_matrix(payload)


def test_phase11_live_comparison_validation_is_deterministic() -> None:
    payload = _fixture_payload()

    assert tuple(row["row_id"] for row in _rows(payload)) == tuple(
        cast(dict[str, object], payload["deterministic_validation"])["row_order"]
    )
    assert validate_phase11_live_comparison_matrix(payload) == validate_phase11_live_comparison_matrix(payload)

    _rows(payload).reverse()
    with pytest.raises(ValueError, match="deterministic|row_order|row order"):
        validate_phase11_live_comparison_matrix(payload)


def test_validate_phase11_live_comparison_rejects_contract_source_class_drift() -> None:
    payload = _fixture_payload()
    required_source_classes = cast(list[str], _contracts(payload)[0]["required_source_classes"])
    required_source_classes.remove("nightly_live")

    with pytest.raises(ValueError, match="source_class|source classes"):
        validate_phase11_live_comparison_matrix(payload)
