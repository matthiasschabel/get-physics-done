from __future__ import annotations

import json

from tests.helpers.live_audit_harness.reporting import render_fake_matrix_report, render_trend_dashboard


def test_phase9_behavior_dashboard_fails_green_rows_with_rejections_or_s0_s1_findings() -> None:
    scores = [
        {
            "row_id": "row-green",
            "scenario_id": "HELP-BEGINNER",
            "persona_id": "P00_zero_coder",
            "provider_runtime": "codex",
            "provider_adapter": "codex",
            "fake_mode": "success",
            "command_surface": "$gpd-start",
            "status": "completed",
            "result_class": "green",
        },
        {
            "row_id": "row-rejected",
            "scenario_id": "VERIFY-PROOF-GAP",
            "persona_id": "P40_physics_verification_researcher",
            "provider_runtime": "codex",
            "provider_adapter": "codex",
            "fake_mode": "schema-valid-bad-row",
            "command_surface": "$gpd-verify-work",
            "status": "completed",
            "result_class": "green",
            "accepted": False,
            "setup_turn_count": 1,
            "recovery_turn_count": 1,
            "raw_transcript": "SHOULD_NOT_LEAK",
        },
        {
            "row_id": "row-green-hard-findings",
            "scenario_id": "EXEC-USER-STEER",
            "persona_id": "P30_planning_execution_researcher",
            "provider_runtime": "codex",
            "provider_adapter": "codex",
            "fake_mode": "false-success",
            "command_surface": "$gpd-execute-phase",
            "status": "completed",
            "result_class": "green",
            "unexpected_write_count": 1,
            "post_stop_activity": True,
            "prompt_budget": {"status": "over_budget"},
            "provider_output": {"stdout": "SHOULD_NOT_LEAK"},
            "findings": [
                {
                    "finding_id": "fake_execution_claim.unproven_execution",
                    "severity": "S1",
                    "category": "fake_execution_claim",
                },
                {
                    "finding_id": "stop_ignored.post_stop_work",
                    "severity": "S0",
                    "category": "stop_handling",
                },
                {
                    "finding_id": "duplicate_questions.repeated_semantic_bucket",
                    "severity": "S2",
                    "category": "duplicate_questions",
                },
                {
                    "finding_id": "prompt_budget_leakage.prompt_over_budget",
                    "severity": "S2",
                    "category": "prompt_budget_leakage",
                },
                {
                    "finding_id": "invalid_evidence.schema_validation",
                    "severity": "S3",
                    "category": "schema_validation",
                },
            ],
        },
    ]

    report = render_fake_matrix_report(scores, scenario_set_id="phase9-behavior-test")
    rows = {str(row["row_id"]): row for row in report["rows"]}

    assert rows["row-rejected"]["result_class"] == "green"
    assert rows["row-rejected"]["behavior_acceptance"] == "rejected"
    assert rows["row-rejected"]["behavior_rejection_reasons"] == ["explicit_rejected"]
    assert rows["row-green-hard-findings"]["result_class"] == "green"
    assert rows["row-green-hard-findings"]["behavior_acceptance"] == "rejected"
    assert "s0_s1_finding" in rows["row-green-hard-findings"]["behavior_rejection_reasons"]

    aggregates = report["aggregates"]
    assert aggregates["result_class_counts"] == {"green": 3}
    assert aggregates["behavior_acceptance_counts"] == {"accepted": 1, "rejected": 2}
    assert aggregates["accepted_row_count"] == 1
    assert aggregates["rejected_row_count"] == 2
    assert aggregates["setup_turn_count"] == 1
    assert aggregates["recovery_turn_count"] == 1
    assert aggregates["duplicate_question_count"] == 1
    assert aggregates["false_success_count"] == 1
    assert aggregates["write_violation_count"] == 1
    assert aggregates["stop_violation_count"] == 1
    assert aggregates["post_stop_activity_count"] >= 1
    assert aggregates["prompt_budget_finding_count"] >= 1
    assert aggregates["schema_failure_count"] == 1
    assert aggregates["unique_s0_s1_finding_count"] == 2

    behavior_metrics = report["behavior_metrics"]
    assert behavior_metrics["class_only"] is True
    assert behavior_metrics["provider_free"] is True
    assert behavior_metrics["rejected_row_ids"] == ["row-green-hard-findings", "row-rejected"]
    assert behavior_metrics["s0_s1_finding_row_count"] == 1
    assert "prompt_budget_leakage.prompt_over_budget" in behavior_metrics["finding_id_counts"]
    assert "invalid_evidence.schema_validation" in behavior_metrics["finding_id_counts"]

    dashboard = render_trend_dashboard(report)

    assert dashboard["metrics"]["pass_rate_overall"] == 1.0
    assert dashboard["metrics"]["rejected_behavior_row_count"] == 2
    assert dashboard["metrics"]["unique_s0_s1_finding_count"] == 2
    assert dashboard["gates"]["acceptance_classification"] == "fail"
    assert dashboard["gates"]["behavior_acceptance"] == "fail"
    assert dashboard["gates"]["behavior_hard_findings"] == "fail"
    assert dashboard["gates"]["behavior_hard_metrics"] == "fail"
    assert dashboard["decision"] == "fail"
    assert "rejected_behavior_rows_present" in dashboard["decision_reasons"]
    assert "s0_s1_behavior_findings_present" in dashboard["decision_reasons"]

    serialized = json.dumps({"dashboard": dashboard, "report": report}, sort_keys=True)
    assert "SHOULD_NOT_LEAK" not in serialized
    assert report["committed_evidence_policy"]["raw_provider_output_committed"] is False
