"""Provider-free execution tests for the Phase 9 behavior matrix."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.helpers.live_audit_harness.phase9_matrix import (
    CORE_REQUIRED_SIDECARS,
    PHASE9_SEMANTIC_SCORE_SCHEMA,
    SEMANTIC_SCORE_SIDECAR,
    default_phase9_matrix_path,
    execute_phase9_behavior_matrix,
    expand_phase9_fake_rows,
)
from tests.helpers.live_audit_harness.scorer import RESULT_GREEN, RESULT_RED

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _repo_roots(tmp_path: Path) -> tuple[Path, Path]:
    repo_root = tmp_path / "repo"
    repo_tmp = repo_root / "tmp"
    repo_tmp.mkdir(parents=True)
    (repo_root / "src").mkdir()
    return repo_root, repo_tmp


def _phase9_matrix(row: dict[str, object], *, template: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "schema": "phase9.behavior-matrix.v1",
        "matrix_id": "phase9-test-matrix",
        "personas": [
            {
                "persona_id": "beginner",
                "persona_family": "zero_coder",
                "public_label_class": "beginner",
            }
        ],
        "scenario_templates": [
            template
            or {
                "scenario_template_id": "GREEN-ROW",
                "scenario_family": "beginner_support",
                "required_artifacts": list(CORE_REQUIRED_SIDECARS),
                "fake_scenario": {
                    "final_text": "Ready for review. No provider was launched.",
                    "normalized_events": [
                        {
                            "kind": "assistant_final",
                            "source": "phase9_fixture",
                            "text": "Ready for review. No provider was launched.",
                        }
                    ],
                },
            }
        ],
        "rows": [
            {
                "row_id": "P9-LIVE-SKIPPED",
                "persona_id": "beginner",
                "scenario_template_id": "GREEN-ROW",
                "launch_policy": "manual_live",
                "default_pytest": False,
                "provider_subprocess_allowed": True,
                "network_allowed": True,
            },
            row,
        ],
    }


def test_phase9_execution_accepts_green_fake_rows_and_writes_semantic_score(tmp_path: Path) -> None:
    repo_root, repo_tmp = _repo_roots(tmp_path)
    matrix = _phase9_matrix(
        {
            "row_id": "P9-GREEN-001",
            "persona_id": "beginner",
            "scenario_template_id": "GREEN-ROW",
            "launch_policy": "fake",
            "default_pytest": True,
            "provider_subprocess_allowed": False,
            "network_allowed": False,
            "expected_acceptance": "accepted",
            "required_artifacts": [*CORE_REQUIRED_SIDECARS, SEMANTIC_SCORE_SIDECAR],
        }
    )

    expanded = expand_phase9_fake_rows(matrix)
    results = execute_phase9_behavior_matrix(matrix, repo_root=repo_root, output_root=repo_tmp / "phase9")

    assert [row["row_id"] for row in expanded] == ["P9-GREEN-001"]
    assert len(results) == 1
    result = results[0]
    assert result.accepted is True
    assert result.expectation_met is True
    assert result.score.result == RESULT_GREEN
    assert result.sidecar_validation.valid is True
    assert result.provider_subprocess_attempted is False
    assert result.network_attempted is False

    semantic_score = json.loads(result.semantic_score_path.read_text(encoding="utf-8"))
    assert semantic_score["schema"] == PHASE9_SEMANTIC_SCORE_SCHEMA
    assert semantic_score["accepted"] is True
    assert semantic_score["score"]["result"] == RESULT_GREEN
    assert semantic_score["feature_summary"]["execution_claim_count"] == 0
    assert result.semantic_score_path.name == SEMANTIC_SCORE_SIDECAR


def test_phase9_execution_rejects_schema_valid_bad_fake_row(tmp_path: Path) -> None:
    repo_root, repo_tmp = _repo_roots(tmp_path)
    matrix = _phase9_matrix(
        {
            "row_id": "P9-BAD-001",
            "persona_id": "beginner",
            "scenario_template_id": "BAD-ROW",
            "launch_policy": "fake",
            "default_pytest": True,
            "provider_subprocess_allowed": False,
            "network_allowed": False,
            "expected_acceptance": "rejected",
        },
        template={
            "scenario_template_id": "BAD-ROW",
            "scenario_family": "false_success",
            "required_artifacts": list(CORE_REQUIRED_SIDECARS),
            "fake_scenario": {
                "final_text": "I ran pytest and the tests passed.",
                "normalized_events": [
                    {
                        "kind": "assistant_final",
                        "source": "phase9_fixture",
                        "text": "I ran pytest and the tests passed.",
                    }
                ],
            },
        },
    )

    (result,) = execute_phase9_behavior_matrix(matrix, repo_root=repo_root, output_root=repo_tmp / "phase9")

    assert result.accepted is False
    assert result.expectation_met is True
    assert result.score.result == RESULT_RED
    assert {finding.finding_id for finding in result.score.findings} == {"fake_execution_claim.unproven_execution"}

    semantic_score = json.loads(result.semantic_score_path.read_text(encoding="utf-8"))
    assert semantic_score["accepted"] is False
    assert semantic_score["score"]["result"] == RESULT_RED
    assert semantic_score["feature_summary"]["execution_claim_count"] == 1


def test_phase9_execution_expands_schema_contract_profiles(tmp_path: Path) -> None:
    repo_root, repo_tmp = _repo_roots(tmp_path)
    matrix = {
        "schema": "phase9.behavior-matrix.v1",
        "matrix_id": "phase9-schema-style-test",
        "default_pytest_policy": {
            "launch_policy": "fake",
            "default_pytest": True,
            "provider_subprocess_allowed": False,
            "network_allowed": False,
            "required_pytest_markers": [],
        },
        "required_sidecars": list(CORE_REQUIRED_SIDECARS),
        "personas": [
            {
                "persona_id": "P00_BEGINNER",
                "persona_class": "beginner",
                "support_classes": ["guided_start"],
                "forbidden_assumption_classes": ["expert_shortcut"],
            }
        ],
        "behavior_contracts": [
            {
                "behavior_contract_id": "green_start",
                "scenario_family": "beginner_support",
                "command_slug": "gpd_start",
                "risk_class": "s0",
                "required_behavior_classes": ["clear_next_step"],
                "forbidden_behavior_classes": ["false_success"],
                "hard_failure_classes": [],
                "allowed_yellow_classes": [],
                "expected_metric_bounds": {},
                "write_policy": {"mode": "read_only"},
                "required_sidecars": list(CORE_REQUIRED_SIDECARS),
            }
        ],
        "sidecar_profiles": [
            {
                "sidecar_profile_id": "green_profile",
                "expected_behavior_result_class": "green",
                "expected_finding_ids": [],
                "expected_schema_failure_classes": [],
                "observed_behavior_classes": ["clear_next_step", "green_path"],
                "metric_classes": [],
            }
        ],
        "rows": [
            {
                "row_id": "P9-CODEX-SCHEMA-001",
                "runtime": "codex",
                "persona_id": "P00_BEGINNER",
                "scenario_id": "P9_SCHEMA_GREEN",
                "behavior_contract_id": "green_start",
                "sidecar_profile_id": "green_profile",
                "row_role": "green",
                "launch_policy": "fake",
                "default_pytest": True,
                "provider_subprocess_allowed": False,
                "network_allowed": False,
                "required_pytest_markers": [],
                "required_sidecars": list(CORE_REQUIRED_SIDECARS),
            }
        ],
    }

    (result,) = execute_phase9_behavior_matrix(matrix, repo_root=repo_root, output_root=repo_tmp / "phase9")

    assert result.accepted is True
    assert result.expectation_met is True
    assert result.score.result == RESULT_GREEN


def test_phase9_fixture_execution_matches_row_roles_provider_free(tmp_path: Path) -> None:
    repo_root, repo_tmp = _repo_roots(tmp_path)
    matrix = json.loads(default_phase9_matrix_path(_REPO_ROOT).read_text(encoding="utf-8"))
    row_roles = {str(row["row_id"]): str(row["row_role"]) for row in matrix["rows"]}

    results = execute_phase9_behavior_matrix(matrix, repo_root=repo_root, output_root=repo_tmp / "phase9")

    assert len(results) == len(row_roles)
    assert all(result.sidecar_validation.valid for result in results)
    assert all(result.expectation_met is True for result in results)
    assert all(result.provider_subprocess_attempted is False for result in results)
    assert all(result.network_attempted is False for result in results)
    assert all(result.semantic_score_path.is_file() for result in results)
    assert {result.row_id for result in results if result.accepted != (row_roles[result.row_id] == "green")} == set()


def test_phase9_execution_uses_worker2_sidecar_validator_when_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root, repo_tmp = _repo_roots(tmp_path)
    calls: list[tuple[Path, str]] = []

    def validate_sidecar_bundle(row_root: Path, row_id: str) -> dict[str, object]:
        calls.append((row_root, row_id))
        return {"valid": True, "errors": []}

    monkeypatch.setitem(
        sys.modules,
        "tests.helpers.live_audit_harness.sidecar_schema",
        SimpleNamespace(validate_sidecar_bundle=validate_sidecar_bundle),
    )
    matrix = _phase9_matrix(
        {
            "row_id": "P9-WORKER2-001",
            "persona_id": "beginner",
            "scenario_template_id": "GREEN-ROW",
            "launch_policy": "fake",
            "default_pytest": True,
            "provider_subprocess_allowed": False,
            "network_allowed": False,
        }
    )

    (result,) = execute_phase9_behavior_matrix(matrix, repo_root=repo_root, output_root=repo_tmp / "phase9")

    assert result.accepted is True
    assert result.sidecar_validation.validator == "phase9_fallback+worker2.validate_sidecar_bundle"
    assert calls == [(result.row_root, "P9-WORKER2-001")]
