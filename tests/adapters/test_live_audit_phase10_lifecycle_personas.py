"""Provider-free execution/reporting tests for Phase 10 lifecycle personas."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import pytest

from tests.helpers.live_audit_harness.phase9_matrix import (
    CORE_REQUIRED_SIDECARS,
    PHASE9_SEMANTIC_SCORE_SCHEMA,
    SEMANTIC_SCORE_SIDECAR,
    execute_phase9_behavior_matrix,
    expand_phase9_fake_rows,
)
from tests.helpers.live_audit_harness.reporting import render_fake_matrix_report, render_trend_dashboard
from tests.helpers.live_audit_harness.scorer import RESULT_GREEN
from tests.helpers.live_audit_harness.sidecar_schema import validate_sidecar_bundle

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PHASE10_MATRIX_CANDIDATES = (
    _REPO_ROOT / "tests" / "fixtures" / "live_audit" / "phase10" / "lifecycle_persona_matrix.json",
    _REPO_ROOT / "tests" / "fixtures" / "live_audit" / "phase10" / "lifecycle_matrix.json",
    _REPO_ROOT / "tests" / "fixtures" / "live_audit" / "phase10" / "behavior_matrix.json",
)
_EXPECTED_LIFE_SCENARIO_IDS = {
    "LIFE-PLAN-HAPPY",
    "LIFE-PLAN-STEERED",
    "LIFE-EXEC-FINAL-PLAN",
    "LIFE-EXEC-MALFORMED-RETURN",
    "LIFE-VERIFY-COMPLETE",
    "LIFE-VERIFY-GAPS",
    "LIFE-INTERRUPTED-AGENT",
    "LIFE-RECOVERABLE-DRIFT",
}


def _repo_roots(tmp_path: Path) -> tuple[Path, Path]:
    repo_root = tmp_path / "repo"
    repo_tmp = repo_root / "tmp"
    repo_tmp.mkdir(parents=True)
    (repo_root / "src").mkdir()
    return repo_root, repo_tmp


def _phase10_matrix_payload() -> dict[str, object]:
    for path in _PHASE10_MATRIX_CANDIDATES:
        if path.is_file():
            return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
    pytest.skip("Worker 1 Phase 10 lifecycle matrix fixture is not available yet")


def _phase10_rows(payload: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    rows = expand_phase9_fake_rows(payload)
    assert rows, "Phase 10 lifecycle fixture must expose provider-free fake rows"
    return tuple(rows)


def _row_id(row: Mapping[str, object]) -> str:
    return str(row["row_id"])


def _scenario_id(row: Mapping[str, object]) -> str:
    return str(row.get("scenario_id", ""))


def _row_role(row: Mapping[str, object]) -> str:
    return str(row.get("row_role", ""))


def _sidecar_contract(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "row_id": _row_id(row),
        "launch_policy": row.get("launch_policy"),
        "default_pytest": row.get("default_pytest"),
        "provider_subprocess_allowed": row.get("provider_subprocess_allowed"),
        "network_allowed": row.get("network_allowed"),
        "required_pytest_markers": row.get("required_pytest_markers", []),
        "required_artifacts": list(CORE_REQUIRED_SIDECARS),
    }


def _report_rows(
    rows: Sequence[Mapping[str, object]],
    results: Sequence[object],
) -> list[dict[str, object]]:
    row_by_id = {_row_id(row): row for row in rows}
    report_rows: list[dict[str, object]] = []
    for result in results:
        row = row_by_id[str(result.row_id)]
        runtime = str(row.get("runtime") or row.get("provider_runtime") or "unknown")
        score = result.score
        report_rows.append(
            {
                "row_id": result.row_id,
                "scenario_id": _scenario_id(row),
                "persona_id": str(row.get("persona_id", "unknown")),
                "provider_runtime": runtime,
                "provider_adapter": str(row.get("provider_adapter") or runtime),
                "fake_mode": str(row.get("fake_mode") or _row_role(row) or "lifecycle_fake"),
                "command_surface": str(row.get("command_surface") or row.get("command_slug") or "unknown"),
                "command_bucket": str(
                    row.get("command_bucket") or row.get("command_slug") or row.get("behavior_contract_id") or "unknown"
                ),
                "risk_tier": str(row.get("risk_tier") or row.get("risk_class") or "unknown"),
                "read_only_expected": True,
                "allow_mutation": bool(row.get("allow_mutation", False)),
                "status": "completed",
                "result_class": score.result,
                "accepted": result.accepted,
                "sidecar_statuses": dict.fromkeys(CORE_REQUIRED_SIDECARS, "present"),
                "provider_subprocess_attempts": int(bool(result.provider_subprocess_attempted)),
                "network_attempts": int(bool(result.network_attempted)),
                "launch_policy": row.get("launch_policy"),
                "default_pytest": row.get("default_pytest"),
                "findings": [finding.to_payload() for finding in score.findings],
            }
        )
    return report_rows


def test_phase10_lifecycle_fixture_covers_all_life_scenario_ids() -> None:
    rows = _phase10_rows(_phase10_matrix_payload())
    life_scenario_ids = {_scenario_id(row) for row in rows if _scenario_id(row).startswith("LIFE-")}

    assert life_scenario_ids == _EXPECTED_LIFE_SCENARIO_IDS
    assert {row["launch_policy"] for row in rows} == {"fake"}
    assert {row["default_pytest"] for row in rows} == {True}
    assert {row["provider_subprocess_allowed"] for row in rows} == {False}
    assert {row["network_allowed"] for row in rows} == {False}
    assert all(set(cast(Sequence[str], row["required_artifacts"])) == set(CORE_REQUIRED_SIDECARS) for row in rows)
    assert any(_row_role(row) == "green" for row in rows)
    assert any(_row_role(row) == "bad_behavior_sentinel" for row in rows)


def test_phase10_lifecycle_matrix_executes_and_writes_semantic_sidecars(tmp_path: Path) -> None:
    payload = _phase10_matrix_payload()
    rows = _phase10_rows(payload)
    repo_root, repo_tmp = _repo_roots(tmp_path)

    results = execute_phase9_behavior_matrix(payload, repo_root=repo_root, output_root=repo_tmp / "phase10")

    row_by_id = {_row_id(row): row for row in rows}
    result_by_id = {result.row_id: result for result in results}
    green_row_ids = {_row_id(row) for row in rows if _row_role(row) == "green"}
    sentinel_row_ids = {_row_id(row) for row in rows if _row_role(row) == "bad_behavior_sentinel"}

    assert set(result_by_id) == set(row_by_id)
    assert green_row_ids
    assert sentinel_row_ids
    assert {row_id for row_id in green_row_ids if not result_by_id[row_id].accepted} == set()
    assert {row_id for row_id in sentinel_row_ids if result_by_id[row_id].accepted} == set()
    assert all(result.expectation_met is True for result in results)
    assert all(result.provider_subprocess_attempted is False for result in results)
    assert all(result.network_attempted is False for result in results)

    for result in results:
        bundle = validate_sidecar_bundle(result.row_root, _sidecar_contract(row_by_id[result.row_id]))
        assert bundle.provider_free is True
        assert set(bundle.sidecar_statuses) == set(CORE_REQUIRED_SIDECARS)
        assert set(bundle.sidecar_statuses.values()) == {"present"}
        assert result.sidecar_validation.valid is True
        assert result.semantic_score_path.name == SEMANTIC_SCORE_SIDECAR
        assert result.semantic_score_path.is_file()

        semantic_score = json.loads(result.semantic_score_path.read_text(encoding="utf-8"))
        assert semantic_score["schema"] == PHASE9_SEMANTIC_SCORE_SCHEMA
        assert semantic_score["row_id"] == result.row_id
        assert semantic_score["accepted"] is result.accepted
        assert semantic_score["score"]["result"] == result.score.result
        assert semantic_score["provider_subprocess_attempted"] is False
        assert semantic_score["network_attempted"] is False

    report = render_fake_matrix_report(_report_rows(rows, results), scenario_set_id="phase10-lifecycle-personas")
    dashboard = render_trend_dashboard(report)

    assert report["committed_evidence_policy"]["class_only_rows"] is True
    assert report["committed_evidence_policy"]["class_only_behavior_metrics"] is True
    assert report["committed_evidence_policy"]["raw_transcripts_committed"] is False
    assert report["committed_evidence_policy"]["raw_provider_output_committed"] is False
    assert report["aggregates"]["accepted_row_count"] == len(green_row_ids)
    assert report["aggregates"]["rejected_row_count"] == len(sentinel_row_ids)
    assert dashboard["gates"]["fake_runner_contract"] == "pass"
    assert dashboard["gates"]["adapter_policy"] == "pass"
    assert dashboard["gates"]["default_pytest_no_network"] == "pass"
    assert dashboard["gates"]["behavior_acceptance"] == "fail"
    assert dashboard["decision"] == "fail"

    hard_lifecycle_findings = [
        finding
        for finding in cast(Sequence[Mapping[str, object]], report["findings"])
        if finding.get("severity") in {"S0", "S1"}
    ]
    assert hard_lifecycle_findings
    assert dashboard["gates"]["behavior_hard_findings"] == "fail"
    assert dashboard["gates"]["behavior_hard_metrics"] == "fail"


def test_phase10_lifecycle_report_dashboard_rejects_class_only_s0_s1_findings() -> None:
    scores = [
        {
            "row_id": "P10-CODEX-LIFE-GREEN",
            "scenario_id": "LIFE-PLAN-HAPPY",
            "persona_id": "P10P01_LIFECYCLE_OPERATOR",
            "provider_runtime": "codex",
            "provider_adapter": "codex",
            "fake_mode": "lifecycle_green",
            "command_surface": "gpd:plan-phase",
            "command_bucket": "plan-phase",
            "risk_tier": "medium",
            "status": "completed",
            "result_class": RESULT_GREEN,
            "accepted": True,
        },
        {
            "row_id": "P10-CODEX-LIFE-SENTINEL",
            "scenario_id": "LIFE-EXEC-MALFORMED-RETURN",
            "persona_id": "P10P01_LIFECYCLE_OPERATOR",
            "provider_runtime": "codex",
            "provider_adapter": "codex",
            "fake_mode": "lifecycle_sentinel",
            "command_surface": "gpd:execute-phase",
            "command_bucket": "execute-phase",
            "risk_tier": "high",
            "status": "completed",
            "result_class": RESULT_GREEN,
            "accepted": False,
            "raw_transcript": "SHOULD_NOT_LEAK",
            "provider_output": {"stdout": "SHOULD_NOT_LEAK"},
            "findings": [
                {
                    "finding_id": "child_report.missing_embedded_gpd_return",
                    "severity": "S1",
                    "category": "child_report",
                },
                {
                    "finding_id": "stop_ignored.post_stop_work",
                    "severity": "S0",
                    "category": "stop_ignored",
                },
            ],
        },
    ]

    report = render_fake_matrix_report(scores, scenario_set_id="phase10-lifecycle-personas")
    dashboard = render_trend_dashboard(report)
    rendered_rows = {str(row["row_id"]): row for row in cast(Sequence[Mapping[str, object]], report["rows"])}

    assert rendered_rows["P10-CODEX-LIFE-GREEN"]["behavior_acceptance"] == "accepted"
    assert rendered_rows["P10-CODEX-LIFE-SENTINEL"]["behavior_acceptance"] == "rejected"
    assert "s0_s1_finding" in rendered_rows["P10-CODEX-LIFE-SENTINEL"]["behavior_rejection_reasons"]
    assert report["behavior_metrics"]["class_only"] is True
    assert report["behavior_metrics"]["provider_free"] is True
    assert report["behavior_metrics"]["rejected_row_ids"] == ["P10-CODEX-LIFE-SENTINEL"]
    assert report["aggregates"]["unique_s0_s1_finding_count"] == 2
    assert dashboard["gates"]["behavior_acceptance"] == "fail"
    assert dashboard["gates"]["behavior_hard_findings"] == "fail"
    assert dashboard["gates"]["behavior_hard_metrics"] == "fail"
    assert dashboard["decision"] == "fail"
    assert "SHOULD_NOT_LEAK" not in json.dumps({"report": report, "dashboard": dashboard}, sort_keys=True)
