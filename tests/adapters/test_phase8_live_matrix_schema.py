"""Schema validation tests for the provider-free Phase 8 matrix fixture."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import cast

import pytest

from gpd.adapters.runtime_catalog import list_runtime_names
from tests.helpers.live_audit_harness.phase8_schema import (
    LAUNCH_POLICIES,
    LIVE_LAUNCH_POLICIES,
    LIVE_ONLY_ARTIFACTS,
    LIVE_PROVIDER_MARKER,
    REQUIRED_ARTIFACTS,
    RUNTIMES,
    SCHEMA_ID,
    Phase8Matrix,
    default_phase8_matrix_path,
    load_phase8_matrix,
    validate_phase8_matrix,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _fixture_payload() -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads(default_phase8_matrix_path(_REPO_ROOT).read_text(encoding="utf-8")),
    )


def _rows(payload: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], payload["rows"])


def _templates(payload: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], payload["scenario_templates"])


def _first_row_with_policy(payload: dict[str, object], launch_policy: str) -> dict[str, object]:
    for row in _rows(payload):
        if row["launch_policy"] == launch_policy:
            return row
    raise AssertionError(f"fixture has no {launch_policy!r} row")


def test_default_phase8_matrix_fixture_validates_class_only_contract() -> None:
    matrix = load_phase8_matrix(default_phase8_matrix_path(_REPO_ROOT))

    assert isinstance(matrix, Phase8Matrix)
    assert matrix.schema == SCHEMA_ID
    assert RUNTIMES == tuple(list_runtime_names())
    assert {row.runtime for row in matrix.rows} == set(RUNTIMES)
    assert {row.launch_policy for row in matrix.rows} == LAUNCH_POLICIES
    assert all(REQUIRED_ARTIFACTS.issubset(template.required_artifacts) for template in matrix.scenario_templates)
    assert all(row.row_id.startswith(f"P8-{row.runtime.upper()}-") for row in matrix.rows)

    template_counts = Counter(row.scenario_template_id for row in matrix.rows)
    assert template_counts["HELP-BEGINNER"] > 1


def test_phase8_fake_rows_are_default_pytest_provider_free() -> None:
    matrix = load_phase8_matrix(default_phase8_matrix_path(_REPO_ROOT))
    fake_rows = [row for row in matrix.rows if row.launch_policy == "fake"]

    assert fake_rows
    assert all(row.default_pytest for row in fake_rows)
    assert {row.provider_subprocess_allowed for row in fake_rows} == {False}
    assert {row.network_allowed for row in fake_rows} == {False}
    assert {row.required_pytest_markers for row in fake_rows} == {()}
    assert {row.budget_policy.mode for row in fake_rows} == {"none"}
    assert {row.live_artifacts for row in fake_rows} == {()}


def test_phase8_live_rows_require_live_marker_budget_and_live_artifacts() -> None:
    matrix = load_phase8_matrix(default_phase8_matrix_path(_REPO_ROOT))
    live_rows = [row for row in matrix.rows if row.launch_policy in LIVE_LAUNCH_POLICIES]

    assert live_rows
    assert {row.default_pytest for row in live_rows} == {False}
    assert {row.provider_subprocess_allowed for row in live_rows} == {True}
    assert {row.network_allowed for row in live_rows} == {True}
    assert all(LIVE_PROVIDER_MARKER in row.required_pytest_markers for row in live_rows)
    assert {row.budget_policy.mode for row in live_rows} == {"required_live_budget"}
    assert all(row.budget_policy.budget_id_class for row in live_rows)
    assert all(LIVE_ONLY_ARTIFACTS.issubset(row.live_artifacts) for row in live_rows)


@pytest.mark.parametrize(
    ("field_name", "bad_value", "match"),
    [
        ("default_pytest", False, "default_pytest"),
        ("provider_subprocess_allowed", True, "provider_subprocess_allowed"),
        ("network_allowed", True, "network_allowed"),
    ],
)
def test_validate_phase8_matrix_rejects_fake_rows_that_escape_default_pytest_contract(
    field_name: str,
    bad_value: object,
    match: str,
) -> None:
    payload = _fixture_payload()
    _first_row_with_policy(payload, "fake")[field_name] = bad_value

    with pytest.raises(ValueError, match=match):
        validate_phase8_matrix(payload)


def test_validate_phase8_matrix_rejects_live_rows_without_marker() -> None:
    payload = _fixture_payload()
    _first_row_with_policy(payload, "manual_live")["required_pytest_markers"] = []

    with pytest.raises(ValueError, match=LIVE_PROVIDER_MARKER):
        validate_phase8_matrix(payload)


def test_validate_phase8_matrix_rejects_live_rows_without_budget() -> None:
    payload = _fixture_payload()
    _first_row_with_policy(payload, "manual_live")["budget_policy"] = {"mode": "none"}

    with pytest.raises(ValueError, match="required_live_budget"):
        validate_phase8_matrix(payload)


def test_validate_phase8_matrix_rejects_live_rows_missing_live_artifact() -> None:
    payload = _fixture_payload()
    live_artifacts = cast(list[str], _first_row_with_policy(payload, "nightly_live")["live_artifacts"])
    live_artifacts.remove("redaction-report.json")

    with pytest.raises(ValueError, match="live_artifacts"):
        validate_phase8_matrix(payload)


@pytest.mark.parametrize(
    ("launch_policy", "required_key"),
    [
        ("setup_refusal", "setup_refusal_class"),
        ("deferred", "deferred_reason_class"),
    ],
)
def test_validate_phase8_matrix_requires_policy_specific_class_fields(
    launch_policy: str,
    required_key: str,
) -> None:
    payload = _fixture_payload()
    del _first_row_with_policy(payload, launch_policy)[required_key]

    with pytest.raises(ValueError, match=required_key):
        validate_phase8_matrix(payload)


def test_validate_phase8_matrix_allows_scenario_templates_shared_across_runtimes() -> None:
    payload = _fixture_payload()
    template_usage = Counter(cast(str, row["scenario_template_id"]) for row in _rows(payload))

    assert template_usage["HELP-BEGINNER"] > 1
    validate_phase8_matrix(payload)


def test_validate_phase8_matrix_rejects_duplicate_row_id_but_not_duplicate_template_use() -> None:
    payload = _fixture_payload()
    _rows(payload)[1]["row_id"] = _rows(payload)[0]["row_id"]

    with pytest.raises(ValueError, match="duplicate row_id"):
        validate_phase8_matrix(payload)


def test_validate_phase8_matrix_rejects_row_id_runtime_mismatch() -> None:
    payload = _fixture_payload()
    _rows(payload)[0]["runtime"] = "gemini"

    with pytest.raises(ValueError, match="row_id"):
        validate_phase8_matrix(payload)


def test_validate_phase8_matrix_rejects_unknown_runtime() -> None:
    payload = _fixture_payload()
    _rows(payload)[0]["runtime"] = "llm-cli"

    with pytest.raises(ValueError, match="runtime"):
        validate_phase8_matrix(payload)


def test_validate_phase8_matrix_rejects_unknown_launch_policy() -> None:
    payload = _fixture_payload()
    _rows(payload)[0]["launch_policy"] = "provider_live"

    with pytest.raises(ValueError, match="launch_policy"):
        validate_phase8_matrix(payload)


@pytest.mark.parametrize("field_name", ["raw_auth_state", "provider_output", "stdout", "auth_path"])
def test_validate_phase8_matrix_rejects_raw_fields_recursively(field_name: str) -> None:
    payload = _fixture_payload()
    _templates(payload)[0]["class_only_contract"] = {"nested": {field_name: "private value would go here"}}

    with pytest.raises(ValueError, match="forbidden raw auth/path/provider-output field"):
        validate_phase8_matrix(payload)
