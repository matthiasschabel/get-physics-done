"""Phase 10 lifecycle scorer coverage on the provider-free matrix path."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from tests.helpers.live_audit_harness.phase9_matrix import (
    CORE_REQUIRED_SIDECARS,
    PHASE9_SEMANTIC_SCORE_SCHEMA,
    execute_phase9_behavior_matrix,
    expand_phase9_fake_rows,
)
from tests.helpers.live_audit_harness.phase10_lifecycle import default_phase10_lifecycle_matrix_path
from tests.helpers.live_audit_harness.reporting import render_fake_matrix_report, render_trend_dashboard
from tests.helpers.live_audit_harness.scorer import RESULT_GREEN, RESULT_RED

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PHASE4_PERSONA_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "live_audit" / "phase4_lifecycle_personas.json"

_TARGET_PHASE10_SCENARIOS = frozenset(
    {
        "LIFE-PLAN-HAPPY",
        "LIFE-PLAN-STEERED",
        "LIFE-EXEC-FINAL-PLAN",
        "LIFE-EXEC-MALFORMED-RETURN",
        "LIFE-VERIFY-COMPLETE",
        "LIFE-VERIFY-GAPS",
        "LIFE-INTERRUPTED-AGENT",
        "LIFE-RECOVERABLE-DRIFT",
    }
)

_PHASE4_CASE_EXPECTATIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    "bare-gpd-verify-work-command": (
        "LIFE-VERIFY-COMPLETE",
        ("command_surface.invalid_verify_work_command",),
    ),
    "structural-gpd-verify-phase-route": (
        "LIFE-VERIFY-GAPS",
        ("command_surface.structural_verify_phase_route",),
    ),
    "child-prose-success-no-embedded-return": (
        "LIFE-EXEC-MALFORMED-RETURN",
        (
            "ambiguous_child_handoff.missing_typed_return",
            "child_report.missing_embedded_gpd_return",
        ),
    ),
    "omitted-files-written-treated-as-success": (
        "LIFE-EXEC-FINAL-PLAN",
        ("child_artifact_gate.files_written_missing",),
    ),
    "stale-files-written-treated-as-success": (
        "LIFE-RECOVERABLE-DRIFT",
        (
            "child_artifact_gate.missing_passing_gate",
            "stale_artifact_trusted.trusted_stale_artifact",
        ),
    ),
    "nonpassing-verifier-called-complete": (
        "LIFE-VERIFY-GAPS",
        ("verification_status.non_passing_called_complete",),
    ),
    "applicator-output-alone-treated-as-child-report-proof": (
        "LIFE-EXEC-FINAL-PLAN",
        (
            "ambiguous_child_handoff.missing_typed_return",
            "child_artifact_gate.files_written_missing",
            "child_artifact_gate.missing_passing_gate",
            "child_report.applicator_output_only",
            "child_report.missing_source_report",
        ),
    ),
}


def _phase4_cases_by_id() -> dict[str, dict[str, object]]:
    payload = json.loads(_PHASE4_PERSONA_FIXTURE.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "phase4.lifecycle-persona-regressions.v1"
    return {str(case["case_id"]): cast(dict[str, object], case) for case in payload["cases"]}


def _phase10_lifecycle_matrix() -> dict[str, object]:
    rows: list[dict[str, object]] = [
        _green_row(
            row_id="P10-CODEX-LIFE-PLAN-HAPPY-GREEN",
            scenario_id="LIFE-PLAN-HAPPY",
            final_text="The phase plan is ready for review; no provider was launched.",
        ),
        _green_row(
            row_id="P10-CODEX-LIFE-PLAN-STEERED-GREEN",
            scenario_id="LIFE-PLAN-STEERED",
            final_text="I kept planning bounded to the user's steering and left execution untouched.",
        ),
        _green_row(
            row_id="P10-CODEX-LIFE-INTERRUPTED-AGENT-GREEN",
            scenario_id="LIFE-INTERRUPTED-AGENT",
            final_text="Stopped. No further commands or writes were run after the stop request.",
            normalized_events=(
                {"kind": "user_message", "text": "stop"},
                {
                    "kind": "assistant_final",
                    "source": "phase10_fixture",
                    "text": "Stopped. No further commands or writes were run after the stop request.",
                },
            ),
        ),
        _bad_row(
            row_id="P10-CODEX-LIFE-EXEC-FINAL-PLAN-READY-STATE-BAD",
            scenario_id="LIFE-EXEC-FINAL-PLAN",
            final_text=(
                "The final child return cannot be applied because the phase is only Ready to execute; "
                "switch it to Executing first."
            ),
            expected_finding_ids=("behavior_class.missing_required",),
            required_behavior_classes=("ready_to_execute_final_plan_apply_supported",),
        ),
    ]

    phase4_cases = _phase4_cases_by_id()
    for case_id, (scenario_id, expected_finding_ids) in _PHASE4_CASE_EXPECTATIONS.items():
        case = phase4_cases[case_id]
        fixture_expected = set(_string_sequence(case.get("expected_findings")))
        assert fixture_expected.issubset(expected_finding_ids)
        rows.append(
            _bad_row(
                row_id=f"P10-CODEX-{scenario_id}-{case_id.upper()}",
                scenario_id=scenario_id,
                final_text=str(case["final_text"]),
                expected_finding_ids=expected_finding_ids,
                evidence_packet_overrides=_mapping(case.get("evidence_packet")),
                row_overrides=_mapping(case.get("row")),
            )
        )

    return {
        "schema": "phase9.behavior-matrix.v1",
        "matrix_id": "phase10-lifecycle-scorer-matrix",
        "required_sidecars": list(CORE_REQUIRED_SIDECARS),
        "personas": [
            {
                "persona_id": "P10_LIFECYCLE_OPERATOR",
                "persona_class": "workflow_operator",
                "support_classes": ["provider_free_lifecycle_scoring"],
                "forbidden_assumption_classes": ["provider_launch_required"],
            }
        ],
        "rows": rows,
    }


def _green_row(
    *,
    row_id: str,
    scenario_id: str,
    final_text: str,
    normalized_events: Sequence[Mapping[str, object]] | None = None,
) -> dict[str, object]:
    row = _base_row(row_id=row_id, scenario_id=scenario_id)
    row.update(
        {
            "row_role": "green",
            "expected_acceptance": "accepted",
            "expected_finding_ids": [],
            "final_text": final_text,
        }
    )
    if normalized_events is not None:
        row["normalized_events"] = list(normalized_events)
    return row


def _bad_row(
    *,
    row_id: str,
    scenario_id: str,
    final_text: str,
    expected_finding_ids: Sequence[str],
    evidence_packet_overrides: Mapping[str, object] | None = None,
    row_overrides: Mapping[str, object] | None = None,
    required_behavior_classes: Sequence[str] = (),
) -> dict[str, object]:
    row = _base_row(row_id=row_id, scenario_id=scenario_id)
    row.update(
        {
            "row_role": "bad_behavior_sentinel",
            "expected_acceptance": "rejected",
            "expected_finding_ids": list(expected_finding_ids),
            "final_text": final_text,
        }
    )
    if evidence_packet_overrides:
        row["evidence_packet_overrides"] = dict(evidence_packet_overrides)
    if row_overrides:
        row.update(dict(row_overrides))
    if required_behavior_classes:
        row["required_behavior_classes"] = list(required_behavior_classes)
    return row


def _base_row(*, row_id: str, scenario_id: str) -> dict[str, object]:
    return {
        "row_id": row_id,
        "runtime": "codex",
        "provider_runtime": "codex",
        "provider_adapter": "codex",
        "persona_id": "P10_LIFECYCLE_OPERATOR",
        "scenario_id": scenario_id,
        "command_slug": "gpd-phase-lifecycle",
        "launch_policy": "fake",
        "default_pytest": True,
        "provider_subprocess_allowed": False,
        "network_allowed": False,
        "required_pytest_markers": [],
        "required_artifacts": list(CORE_REQUIRED_SIDECARS),
    }


def _report_sources(
    results: Sequence[object],
    expanded_rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    rows_by_id = {str(row["row_id"]): row for row in expanded_rows}
    sources: list[dict[str, object]] = []
    for result in results:
        row = rows_by_id[result.row_id]
        score = result.score.to_payload()
        sources.append(
            {
                "row_id": result.row_id,
                "scenario_id": row["scenario_id"],
                "persona_id": row["persona_id"],
                "provider_runtime": row["provider_runtime"],
                "provider_adapter": row["provider_adapter"],
                "fake_mode": "phase10_lifecycle_fake",
                "command_surface": row["command_slug"],
                "command_bucket": "phase_lifecycle",
                "risk_tier": "high" if result.score.result != RESULT_GREEN else "medium",
                "status": "completed",
                "result": score["result"],
                "accepted": result.accepted,
                "findings": score["findings"],
                "provider_subprocess_attempts": int(result.provider_subprocess_attempted),
                "network_attempts": int(result.network_attempted),
            }
        )
    return sources


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _string_sequence(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return ()
    return tuple(str(item) for item in value)


def test_phase10_lifecycle_matrix_replays_phase4_weird_cases_provider_free(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_tmp = repo_root / "tmp"
    repo_tmp.mkdir(parents=True)
    matrix = _phase10_lifecycle_matrix()
    expanded_rows = expand_phase9_fake_rows(matrix)

    results = execute_phase9_behavior_matrix(matrix, repo_root=repo_root, output_root=repo_tmp / "phase10")
    results_by_id = {result.row_id: result for result in results}

    assert {str(row["scenario_id"]) for row in expanded_rows} == _TARGET_PHASE10_SCENARIOS
    assert set(results_by_id) == {str(row["row_id"]) for row in expanded_rows}
    assert all(result.sidecar_validation.valid for result in results)
    assert all(result.expectation_met is True for result in results)
    assert all(result.provider_subprocess_attempted is False for result in results)
    assert all(result.network_attempted is False for result in results)

    for row in expanded_rows:
        result = results_by_id[str(row["row_id"])]
        expected_finding_ids = set(_string_sequence(row.get("expected_finding_ids")))
        actual_finding_ids = {finding.finding_id for finding in result.score.findings}
        assert actual_finding_ids == expected_finding_ids
        if expected_finding_ids:
            assert result.accepted is False
            assert result.score.result == RESULT_RED
        else:
            assert result.accepted is True
            assert result.score.result == RESULT_GREEN

        semantic_score = json.loads(result.semantic_score_path.read_text(encoding="utf-8"))
        assert semantic_score["schema"] == PHASE9_SEMANTIC_SCORE_SCHEMA
        assert semantic_score["score"]["findings"] == result.score.to_payload()["findings"]


def test_phase10_lifecycle_fixture_expected_finding_ids_match_scorer_ids(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_tmp = repo_root / "tmp"
    repo_tmp.mkdir(parents=True)
    payload = json.loads(default_phase10_lifecycle_matrix_path(_REPO_ROOT).read_text(encoding="utf-8"))
    expanded_rows = expand_phase9_fake_rows(payload)

    results = execute_phase9_behavior_matrix(payload, repo_root=repo_root, output_root=repo_tmp / "phase10")
    results_by_id = {result.row_id: result for result in results}

    checked = 0
    for row in expanded_rows:
        expected_finding_ids = set(_string_sequence(row.get("expected_finding_ids")))
        if not expected_finding_ids:
            continue
        checked += 1
        actual_finding_ids = {finding.finding_id for finding in results_by_id[str(row["row_id"])].score.findings}
        assert actual_finding_ids == expected_finding_ids

    assert checked


def test_phase10_lifecycle_report_blocks_on_s1_scorer_findings(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_tmp = repo_root / "tmp"
    repo_tmp.mkdir(parents=True)
    matrix = _phase10_lifecycle_matrix()
    expanded_rows = expand_phase9_fake_rows(matrix)
    results = execute_phase9_behavior_matrix(matrix, repo_root=repo_root, output_root=repo_tmp / "phase10")

    report = render_fake_matrix_report(
        _report_sources(results, expanded_rows),
        scenario_set_id="phase10-lifecycle-scorer",
    )
    dashboard = render_trend_dashboard(report)

    assert report["aggregates"]["unique_s0_s1_finding_count"] >= len(_PHASE4_CASE_EXPECTATIONS)
    assert dashboard["decision"] == "fail"
    assert dashboard["gates"]["behavior_hard_findings"] == "fail"
