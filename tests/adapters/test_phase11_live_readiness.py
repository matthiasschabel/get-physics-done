"""Provider-free tests for the Phase 11 live readiness helper."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import cast

import pytest

from gpd.adapters.runtime_catalog import list_runtime_names
from tests.helpers.live_audit_harness.phase11_comparison import (
    build_live_readiness_matrix,
    validate_live_readiness_matrix,
)

_READY_RUNTIMES = {"claude-code", "codex", "gemini"}
_DEFERRED_RUNTIME = "opencode"
_NOT_CHECKED = "not_checked"


def _jsonable(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    to_json = getattr(value, "to_json", None)
    if callable(to_json):
        return _jsonable(to_json())
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    return value


def _matrix_payload() -> dict[str, object]:
    payload = _jsonable(build_live_readiness_matrix())
    assert isinstance(payload, dict)
    validate_live_readiness_matrix(payload)
    return cast(dict[str, object], payload)


def _rows(payload: Mapping[str, object]) -> list[dict[str, object]]:
    for key in ("rows", "runtime_readiness_rows", "runtime_readiness", "runtime_capabilities"):
        value = payload.get(key)
        if isinstance(value, list):
            rows = []
            for index, row in enumerate(value):
                assert isinstance(row, dict), f"{key}[{index}] must be a mapping"
                rows.append(cast(dict[str, object], row))
            return rows
    raise AssertionError("live readiness matrix must expose runtime rows")


def _runtime_id(row: Mapping[str, object]) -> str:
    for key in ("runtime_id", "runtime"):
        value = row.get(key)
        if isinstance(value, str):
            return value
    raise AssertionError("readiness row must expose runtime_id or runtime")


def _readiness_status(row: Mapping[str, object]) -> str:
    for key in ("live_readiness_status", "live_runner_status", "readiness_status"):
        value = row.get(key)
        if isinstance(value, str):
            return value
    raise AssertionError("readiness row must expose a readiness status")


def _row_by_runtime(payload: Mapping[str, object]) -> dict[str, dict[str, object]]:
    return {_runtime_id(row): row for row in _rows(payload)}


def test_phase11_live_readiness_matrix_is_catalog_backed_and_provider_free() -> None:
    payload = _matrix_payload()
    runtime_ids = [_runtime_id(row) for row in _rows(payload)]
    rows_by_runtime = _row_by_runtime(payload)

    assert runtime_ids == list_runtime_names()
    assert payload["provider_launch_performed"] is False
    assert {runtime for runtime, row in rows_by_runtime.items() if _readiness_status(row) == "ready"} == _READY_RUNTIMES

    for runtime, row in rows_by_runtime.items():
        assert row["catalog_runtime"] is True
        assert row["environment_status"] == _NOT_CHECKED
        assert row["provider_launch_performed"] is False
        if runtime in _READY_RUNTIMES:
            assert _readiness_status(row) == "ready"


def test_phase11_live_readiness_matrix_keeps_opencode_deferred_with_reason() -> None:
    row = _row_by_runtime(_matrix_payload())[_DEFERRED_RUNTIME]

    assert _readiness_status(row) == "deferred"
    assert isinstance(row["deferred_reason"], str)
    assert row["deferred_reason"].strip()
    assert "headless" in row["deferred_reason"].lower()


def test_phase11_live_readiness_matrix_does_not_imply_auth_or_quota_probe() -> None:
    payload = _matrix_payload()
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["provider_launch_performed"] is False
    assert "within_budget" not in serialized
    for row in _rows(payload):
        assert row["auth_status"] == _NOT_CHECKED
        assert row["quota_status"] == _NOT_CHECKED
        assert row["auth_probe_performed"] is False
        assert row["quota_probe_performed"] is False


@pytest.mark.parametrize(
    ("field_name", "bad_value", "match"),
    [
        ("environment_status", "ready", "environment_status"),
        ("auth_status", "ready", "auth_status"),
        ("quota_status", "within_budget", "quota_status"),
        ("auth_probe_performed", True, "auth_probe_performed"),
        ("quota_probe_performed", True, "quota_probe_performed"),
        ("provider_launch_performed", True, "provider_launch_performed"),
    ],
)
def test_validate_phase11_live_readiness_matrix_rejects_probe_or_launch_claims(
    field_name: str,
    bad_value: object,
    match: str,
) -> None:
    payload = copy.deepcopy(_matrix_payload())
    _rows(payload)[0][field_name] = bad_value

    with pytest.raises(ValueError, match=match):
        validate_live_readiness_matrix(payload)
