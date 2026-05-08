"""Schema validation tests for the provider-free Phase 7 live-audit fixture."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest

from gpd.adapters.runtime_catalog import list_runtime_names
from tests.helpers.live_audit_harness.schema import (
    REQUIRED_ARTIFACTS,
    RUNTIMES,
    ScenarioSet,
    default_scenario_path,
    load_scenario_set,
    validate_scenario_set,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REQUIRED_SCENARIOS = {
    "HELP-BEGINNER",
    "EXEC-USER-STEER",
    "VERIFY-STALE-ARTIFACT",
    "WRONG-WORKSPACE-WRITE",
    "FAKE-EXECUTION-CLAIM",
    "AMBIGUOUS-CHILD-HANDOFF",
    "PROMPT-BUDGET-LEAK",
}


def _fixture_payload() -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads(default_scenario_path(_REPO_ROOT).read_text(encoding="utf-8")),
    )


def _rows(payload: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], payload["scenario_rows"])


def _personas(payload: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], payload["personas"])


def test_default_scenario_fixture_validates_provider_free_rows() -> None:
    scenario_set = load_scenario_set(default_scenario_path(_REPO_ROOT))

    assert isinstance(scenario_set, ScenarioSet)
    assert RUNTIMES == tuple(list_runtime_names())
    assert {row.scenario_id for row in scenario_set.rows} == _REQUIRED_SCENARIOS
    assert {row.provider_launch_allowed for row in scenario_set.rows} == {False}
    assert all(row.runtime in RUNTIMES for row in scenario_set.rows)
    assert all(REQUIRED_ARTIFACTS.issubset(row.required_artifacts) for row in scenario_set.rows)
    assert {persona.persona_id for persona in scenario_set.personas}.issuperset(
        row.persona_id for row in scenario_set.rows
    )


def test_validate_scenario_set_rejects_wrong_schema_version() -> None:
    payload = _fixture_payload()
    payload["schema_version"] = "phase7.persona-scenario-set.v2"

    with pytest.raises(ValueError, match="schema_version"):
        validate_scenario_set(payload)


def test_validate_scenario_set_rejects_provider_launch_enabled_row() -> None:
    payload = _fixture_payload()
    _rows(payload)[0]["provider_launch_allowed"] = True

    with pytest.raises(ValueError, match="provider_launch_allowed"):
        validate_scenario_set(payload)


def test_validate_scenario_set_rejects_duplicate_persona_id() -> None:
    payload = _fixture_payload()
    duplicate = deepcopy(_personas(payload)[0])
    _personas(payload).append(duplicate)

    with pytest.raises(ValueError, match="duplicate persona_id"):
        validate_scenario_set(payload)


def test_validate_scenario_set_rejects_duplicate_row_id() -> None:
    payload = _fixture_payload()
    _rows(payload)[1]["row_id"] = _rows(payload)[0]["row_id"]

    with pytest.raises(ValueError, match="duplicate row_id"):
        validate_scenario_set(payload)


def test_validate_scenario_set_rejects_duplicate_scenario_id() -> None:
    payload = _fixture_payload()
    _rows(payload)[1]["scenario_id"] = _rows(payload)[0]["scenario_id"]

    with pytest.raises(ValueError, match="duplicate scenario_id"):
        validate_scenario_set(payload)


def test_validate_scenario_set_rejects_unknown_persona_reference() -> None:
    payload = _fixture_payload()
    _rows(payload)[0]["persona_id"] = "P7P99_MISSING"

    with pytest.raises(ValueError, match="does not reference a declared persona"):
        validate_scenario_set(payload)


def test_validate_scenario_set_rejects_unknown_runtime() -> None:
    payload = _fixture_payload()
    _rows(payload)[0]["runtime"] = "llm-cli"

    with pytest.raises(ValueError, match="runtime"):
        validate_scenario_set(payload)


def test_validate_scenario_set_rejects_missing_required_artifact() -> None:
    payload = _fixture_payload()
    artifacts = cast(list[str], _rows(payload)[0]["required_artifacts"])
    artifacts.remove("evidence-packet.json")

    with pytest.raises(ValueError, match="missing required artifacts"):
        validate_scenario_set(payload)


def test_validate_scenario_set_rejects_absolute_write_policy_path() -> None:
    payload = _fixture_payload()
    write_policy = cast(dict[str, object], _rows(payload)[0]["write_policy"])
    forbidden_paths = cast(list[str], write_policy["forbidden_paths"])
    forbidden_paths.append("/Users/sergio/private-output")

    with pytest.raises(ValueError, match="must be relative"):
        validate_scenario_set(payload)


@pytest.mark.parametrize("field_name", ["raw_auth_state", "raw_path", "raw_provider_output"])
def test_validate_scenario_set_rejects_raw_public_fields(field_name: str) -> None:
    payload = _fixture_payload()
    _rows(payload)[0][field_name] = "private value would go here"

    with pytest.raises(ValueError, match="forbidden raw auth/path/provider-output field"):
        validate_scenario_set(payload)
