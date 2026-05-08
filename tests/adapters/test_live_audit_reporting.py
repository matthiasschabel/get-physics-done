from __future__ import annotations

import json

from tests.helpers.live_audit_harness.reporting import (
    provider_attempt_report_schema,
    render_fake_matrix_report,
    render_trend_dashboard,
)


def test_fake_matrix_report_counts_and_orders_rows_deterministically() -> None:
    scores = [
        {
            "row_id": "row-b",
            "scenario_id": "VERIFY-PROOF-GAP",
            "persona_id": "P40_physics_verification_researcher",
            "fixture_id": "F32",
            "provider_runtime": "gemini",
            "provider_adapter": "gemini",
            "fake_mode": "missing-final",
            "command_surface": "$gpd-verify-work",
            "read_only_expected": True,
            "status": "completed",
            "result_class": "warn",
            "observed_write_count": 0,
            "unexpected_write_count": 0,
            "raw_transcript": "SHOULD_NOT_LEAK",
            "provider_output": {"stdout": "SHOULD_NOT_LEAK"},
        },
        {
            "row_id": "row-a",
            "scenario_id": "HELP-BEGINNER",
            "persona_id": "P00_zero_coder",
            "fixture_id": "F01",
            "provider_runtime": "codex",
            "provider_adapter": "codex",
            "fake_mode": "success",
            "command_surface": "$gpd-start",
            "read_only_expected": True,
            "status": "completed",
            "result_class": "pass",
            "observed_write_count": 0,
            "unexpected_write_count": 0,
        },
    ]

    report = render_fake_matrix_report(scores, scenario_set_id="phase7-test-set", repo_head="abc123")
    report_again = render_fake_matrix_report(scores, scenario_set_id="phase7-test-set", repo_head="abc123")

    assert report == report_again
    assert report["schema"] == "phase7.fake_matrix_report.v1"
    assert report["provider_subprocess_allowed"] is False
    assert report["scenario_set_id"] == "phase7-test-set"
    assert report["repo_head"] == "abc123"
    assert [row["row_id"] for row in report["rows"]] == ["row-a", "row-b"]
    assert report["fake_modes"] == ["missing-final", "success"]
    assert report["aggregates"] == {
        "row_count": 2,
        "status_counts": {"completed": 2},
        "result_class_counts": {"green": 1, "yellow": 1},
        "provider_runtime_counts": {"codex": 1, "gemini": 1},
        "fake_mode_counts": {"missing-final": 1, "success": 1},
        "read_only_expected_count": 2,
        "mutation_allowed_count": 0,
        "observed_write_count": 0,
        "unexpected_write_count": 0,
        "provider_subprocess_attempts": 0,
        "network_attempts": 0,
        "unique_finding_count": 0,
        "unique_s0_s1_finding_count": 0,
    }
    assert "SHOULD_NOT_LEAK" not in json.dumps(report, sort_keys=True)


def test_fake_matrix_report_aggregates_findings_by_id() -> None:
    scores = [
        {
            "row_id": "row-c",
            "scenario_id": "EXEC-USER-STEER",
            "persona_id": "P30_planning_execution_researcher",
            "provider_runtime": "claude-code",
            "provider_adapter": "claude-code",
            "status": "completed",
            "result": "fail",
            "findings": [
                {"id": "stop_ignored", "severity": "S0", "category": "stop_handling"},
                {"id": "workspace_write", "severity": "S2", "category": "write_boundary"},
            ],
        },
        {
            "row_id": "row-d",
            "scenario_id": "PLAN-DIRTY-GIT",
            "persona_id": "P30_planning_execution_researcher",
            "provider_runtime": "codex",
            "provider_adapter": "codex",
            "status": "completed",
            "result": "warn",
            "findings": [{"id": "workspace_write", "severity": "S1", "category": "write_boundary"}],
        },
    ]

    report = render_fake_matrix_report(scores, scenario_set_id="phase7-test-set")

    assert report["findings"] == [
        {
            "finding_id": "stop_ignored",
            "severity": "S0",
            "categories": ["stop_handling"],
            "count": 1,
            "row_ids": ["row-c"],
        },
        {
            "finding_id": "workspace_write",
            "severity": "S1",
            "categories": ["write_boundary"],
            "count": 2,
            "row_ids": ["row-c", "row-d"],
        },
    ]
    assert report["aggregates"]["unique_finding_count"] == 2
    assert report["aggregates"]["unique_s0_s1_finding_count"] == 2


def test_trend_dashboard_ready_pending_and_fail_decisions() -> None:
    green_scores = [
        {
            "row_id": "row-a",
            "scenario_id": "HELP-BEGINNER",
            "persona_id": "P00_zero_coder",
            "provider_runtime": "codex",
            "provider_adapter": "codex",
            "command_bucket": "start",
            "risk_tier": "low",
            "status": "completed",
            "result": "pass",
        }
    ]
    ready_report = render_fake_matrix_report(green_scores, scenario_set_id="phase7-test-set")

    dashboard = render_trend_dashboard(ready_report)

    assert dashboard["schema"] == "phase7.trend_dashboard.v1"
    assert dashboard["decision"] == "ready_for_manual_phase8"
    assert dashboard["metrics"]["pass_rate_overall"] == 1.0
    assert dashboard["metrics"]["pass_rate_by_runtime"] == {"codex": 1.0}

    pending_report = render_fake_matrix_report(
        [{**green_scores[0], "row_id": "row-b", "result": "warn"}],
        scenario_set_id="phase7-test-set",
    )
    assert render_trend_dashboard(pending_report)["decision"] == "pending"

    red_report = render_fake_matrix_report(
        [{**green_scores[0], "row_id": "row-c", "result": "red"}],
        scenario_set_id="phase7-test-set",
    )
    red_dashboard = render_trend_dashboard(red_report)
    assert red_dashboard["decision"] == "fail"
    assert red_dashboard["gates"]["acceptance_classification"] == "fail"

    attempted_provider_report = render_fake_matrix_report(
        [{**green_scores[0], "row_id": "row-d", "provider_subprocess_attempts": 1}],
        scenario_set_id="phase7-test-set",
    )
    attempted_dashboard = render_trend_dashboard(attempted_provider_report)
    assert attempted_dashboard["decision"] == "fail"
    assert attempted_dashboard["gates"]["default_pytest_no_network"] == "fail"


def test_provider_attempt_report_schema_is_manual_nightly_only_skeleton() -> None:
    schema = provider_attempt_report_schema()

    assert schema["schema"] == "phase8.provider_attempt_report.v1"
    assert schema["schema_kind"] == "class_only_schema_skeleton"
    assert schema["default_pytest_policy"] == {
        "live_rows_in_default_pytest": False,
        "provider_subprocess_allowed_in_default_pytest": False,
        "allowed_live_collections": ["manual", "nightly"],
        "required_pytest_marker": "live_provider",
        "provider_attempts_count_against_live_budget": True,
    }
    assert schema["properties"]["rows"]["manual_or_nightly_only"] is True
    assert not _contains_key(schema, "raw_transcript")
    assert not _contains_key(schema, "provider_output")
    assert not _contains_key(schema, "stdout")
    assert not _contains_key(schema, "stderr")


def _contains_key(value: object, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(child, key) for child in value.values())
    if isinstance(value, list):
        return any(_contains_key(child, key) for child in value)
    return False
