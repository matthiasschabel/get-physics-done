from __future__ import annotations

import copy
import json

import pytest

from scripts.validate_phase8_provider_report import main as validate_phase8_report_main
from scripts.validate_phase8_provider_report import validate_report
from tests.helpers.live_audit_harness.reporting import (
    provider_attempt_report_validation_errors,
    render_provider_attempt_markdown,
    render_provider_attempt_report,
    validate_provider_attempt_report,
)


def _phase12_clean_smoke_report(*, decision: str | None = None) -> dict[str, object]:
    kwargs: dict[str, object] = {}
    if decision is not None:
        kwargs["decision"] = decision
    return render_provider_attempt_report(
        [
            {
                "row_id": "row-phase12-smoke",
                "scenario_id": "HELP-BEGINNER",
                "persona_id": "P00_zero_coder",
                "provider_runtime": "codex",
                "launch_policy": "manual_live",
                "attempt_status": "completed",
                "result_class": "green",
                "command_bucket": "start",
                "prompt_budget": {"max_prompt_tokens": 500, "prompt_tokens_estimate": 200},
                "retention_refs": ["provider-attempt-json"],
            }
        ],
        attempt_id="attempt-phase12-smoke",
        batch_id="batch-phase12-smoke",
        scenario_set_id="phase12-release-smoke",
        row_set_sha256="phase12-smoke",
        budget_id="budget-phase12-smoke",
        repo_head="abc123",
        provider_set=["codex"],
        runtime_capabilities=[{"runtime": "codex", "live_runner_status": "ready"}],
        **kwargs,
    )


def test_provider_attempt_report_renders_aggregates_prompt_budget_and_markdown() -> None:
    rows = [
        {
            "row_id": "row-codex",
            "scenario_id": "HELP-BEGINNER",
            "scenario_template_id": "T-start-help",
            "persona_id": "P00_zero_coder",
            "provider_runtime": "codex",
            "provider_adapter": "codex",
            "launch_policy": "manual_live",
            "attempt_status": "completed",
            "result_class": "green",
            "command_bucket": "start",
            "prompt_budget": {
                "max_prompt_tokens": 1000,
                "prompt_tokens_estimate": 450,
                "completion_tokens_estimate": 150,
                "observed_total_tokens": 580,
            },
            "sidecar_statuses": {"provider-attempt.json": "present"},
            "write_status": "not_written",
            "retention_refs": ["provider-attempt-json"],
        },
        {
            "row_id": "row-gemini",
            "scenario_id": "VERIFY-PROOF-GAP",
            "scenario_template_id": "T-verify-gap",
            "persona_id": "P40_physics_verification_researcher",
            "provider_runtime": "gemini",
            "provider_adapter": "gemini",
            "launch_policy": "nightly_live",
            "attempt_status": "completed",
            "result_class": "red",
            "command_bucket": "verify",
            "prompt_budget": {
                "max_prompt_tokens": 1000,
                "prompt_tokens_estimate": 900,
                "completion_tokens_estimate": 300,
                "observed_total_tokens": 1180,
            },
            "findings": [
                {
                    "finding_id": "verify.trusted_stale_artifact",
                    "finding_class": "product_behavior",
                    "severity": "S1",
                    "summary": "Trusted a stale verification artifact.",
                }
            ],
            "sidecar_statuses": {"provider-attempt.json": "present"},
            "write_status": "not_written",
            "retention_refs": ["provider-attempt-json"],
        },
    ]

    report = render_provider_attempt_report(
        rows,
        attempt_id="attempt-20260508-001",
        batch_id="batch-20260508-nightly",
        scenario_set_id="phase8-smoke",
        row_set_sha256="abc123",
        budget_id="budget-phase8-nightly",
        provider_set=["codex", "gemini", "opencode"],
        runtime_capabilities=[
            {
                "runtime": "codex",
                "live_runner_status": "ready",
                "headless_command_shape_id": "codex.exec.prompt-file.v1",
                "prompt_transport_class": "stdin_prompt_file",
                "auth_probe_class": "class_only_auth_probe",
                "event_stream_class": "notify_hook",
            },
            {
                "runtime": "gemini",
                "live_runner_status": "ready",
                "headless_command_shape_id": "gemini.prompt.v1",
                "prompt_transport_class": "prompt_flag",
                "auth_probe_class": "class_only_auth_probe",
                "event_stream_class": "final_text",
            },
        ],
        auth_profile={
            "profile_id": "nightly-class-only",
            "auth_status_class": "ready",
            "quota_status_class": "within_budget",
        },
        findings=[
            {
                "finding_id": "quota.class_only",
                "finding_class": "auth_quota",
                "severity": "S2",
                "row_ids": ["row-gemini"],
                "summary": "Quota was recorded as a class-only status.",
            }
        ],
        retention_manifest={
            "artifacts": [
                {
                    "artifact_id": "provider-attempt-json",
                    "artifact_ref": "provider-attempt.json",
                    "retention_class": "committed_redacted",
                    "material_class": "sanitized_report",
                    "safe_to_commit": True,
                },
                {
                    "artifact_id": "operator-local-session",
                    "artifact_ref": "operator-local-session",
                    "retention_class": "operator_local_raw",
                    "material_class": "raw_provider_material",
                    "safe_to_commit": False,
                    "local_only": True,
                },
                {
                    "artifact_id": "prompt-material",
                    "artifact_ref": "prompt-material",
                    "retention_class": "never_record",
                    "material_class": "prompt_material",
                    "safe_to_commit": False,
                    "local_only": True,
                },
            ]
        },
    )

    validate_provider_attempt_report(report)

    assert report["decision"] == "needs_repair"
    assert report["provider_attempt_count"] == 2
    assert report["aggregates"]["runtime_counts"] == {"codex": 1, "gemini": 1}
    assert report["aggregates"]["persona_counts"] == {
        "P00_zero_coder": 1,
        "P40_physics_verification_researcher": 1,
    }
    assert report["aggregates"]["finding_class_counts"] == {
        "auth_quota": 1,
        "product_behavior": 1,
    }
    assert report["prompt_budget"]["total_tokens_estimate"] == 1800
    assert report["prompt_budget"]["over_budget_rows"] == ["row-gemini"]
    assert report["retention_manifest"]["classes"]["operator_local_raw"]["safe_to_commit"] is False
    assert {capability["runtime"]: capability["live_runner_status"] for capability in report["runtime_capabilities"]}[
        "opencode"
    ] == "deferred"

    markdown = render_provider_attempt_markdown(report)

    assert markdown.startswith("# Phase 8 Provider Attempt Report\n\n**Decision:** NEEDS_REPAIR")
    assert "## Runtime Capabilities" in markdown
    assert "opencode" in markdown
    assert "headless command/output/auth contract is not ready" in markdown
    assert "row-gemini" in markdown
    assert "operator_local_raw" in markdown


def test_provider_attempt_report_surfaces_deferred_runtime_rows() -> None:
    report = render_provider_attempt_report(
        [
            {
                "row_id": "row-opencode",
                "scenario_id": "START-OPENCODE",
                "persona_id": "P00_zero_coder",
                "provider_runtime": "opencode",
                "launch_policy": "deferred",
                "attempt_status": "deferred",
                "result_class": "yellow",
                "command_bucket": "start",
                "prompt_budget": {"max_prompt_tokens": 500, "prompt_tokens_estimate": 0},
                "retention_refs": ["provider-attempt-json"],
            }
        ],
        attempt_id="attempt-20260508-002",
        batch_id="batch-20260508-manual",
        scenario_set_id="phase8-smoke",
        row_set_sha256="def456",
        budget_id="budget-phase8-manual",
        provider_set=["opencode"],
    )

    assert report["decision"] == "blocked"
    assert report["unsupported_or_deferred_rows"] == ["row-opencode"]

    markdown = render_provider_attempt_markdown(report)

    assert "## Unsupported Or Deferred Rows" in markdown
    assert "row-opencode" in markdown
    assert "deferred" in markdown


def test_provider_attempt_report_validation_rejects_raw_and_unsafe_retention_material() -> None:
    with pytest.raises(ValueError, match="raw_transcript"):
        render_provider_attempt_report(
            [
                {
                    "row_id": "row-raw",
                    "scenario_id": "RAW-LEAK",
                    "persona_id": "P00_zero_coder",
                    "provider_runtime": "codex",
                    "raw_transcript": "provider text must stay local",
                }
            ],
            attempt_id="attempt-raw",
            batch_id="batch-raw",
            scenario_set_id="phase8-smoke",
            row_set_sha256="raw",
            budget_id="budget-raw",
        )

    report = render_provider_attempt_report(
        [
            {
                "row_id": "row-safe",
                "scenario_id": "HELP-BEGINNER",
                "persona_id": "P00_zero_coder",
                "provider_runtime": "codex",
                "attempt_status": "completed",
                "result_class": "green",
                "command_bucket": "start",
                "prompt_budget": {"max_prompt_tokens": 500, "prompt_tokens_estimate": 200},
                "retention_refs": ["provider-attempt-json"],
            }
        ],
        attempt_id="attempt-safe",
        batch_id="batch-safe",
        scenario_set_id="phase8-smoke",
        row_set_sha256="safe",
        budget_id="budget-safe",
        runtime_capabilities=[{"runtime": "codex", "live_runner_status": "ready"}],
    )

    raw_report = copy.deepcopy(report)
    raw_report["rows"][0]["provider_output"] = {"stdout": "provider transcript"}
    assert "provider_output" in provider_attempt_report_validation_errors(raw_report)[0]

    account_report = copy.deepcopy(report)
    account_report["auth_profile"]["account_identifier"] = "researcher@example.com"
    with pytest.raises(ValueError, match="account_identifier"):
        validate_provider_attempt_report(account_report)

    unsafe_retention_report = copy.deepcopy(report)
    unsafe_retention_report["retention_manifest"]["artifacts"][0]["material_class"] = "raw_provider_material"
    unsafe_retention_report["retention_manifest"]["artifacts"][0]["safe_to_commit"] = True
    with pytest.raises(ValueError, match="raw provider material"):
        validate_provider_attempt_report(unsafe_retention_report)


def test_phase8_provider_report_release_validator_accepts_clean_smoke(tmp_path) -> None:
    report = render_provider_attempt_report(
        [
            {
                "row_id": "row-release-smoke",
                "scenario_id": "HELP-BEGINNER",
                "persona_id": "P00_zero_coder",
                "provider_runtime": "codex",
                "launch_policy": "manual_live",
                "attempt_status": "completed",
                "result_class": "green",
                "command_bucket": "start",
                "prompt_budget": {"max_prompt_tokens": 500, "prompt_tokens_estimate": 200},
                "retention_refs": ["provider-attempt-json"],
            }
        ],
        attempt_id="attempt-release-smoke",
        batch_id="batch-release-smoke",
        scenario_set_id="phase8-release-smoke",
        row_set_sha256="release-smoke",
        budget_id="budget-release-smoke",
        repo_head="abc123",
        provider_set=["codex"],
        runtime_capabilities=[{"runtime": "codex", "live_runner_status": "ready"}],
    )

    validate_report(
        report, require_smoke=True, expected_repo_head="abc123", max_provider_attempts=1, max_mutating_rows=0
    )

    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    assert (
        validate_phase8_report_main(["--input", str(report_path), "--require-smoke", "--expected-repo-head", "abc123"])
        == 0
    )


def test_phase12_release_validator_rejects_wrong_repo_head() -> None:
    report = _phase12_clean_smoke_report()

    with pytest.raises(ValueError, match="repo_head"):
        validate_report(report, require_smoke=True, expected_repo_head="def456")


@pytest.mark.parametrize("decision", ["needs_repair", "blocked", "pending"])
def test_phase12_release_validator_rejects_non_accept_decision_when_smoke_required(decision: str) -> None:
    report = _phase12_clean_smoke_report(decision=decision)

    with pytest.raises(ValueError, match="decision='accept'"):
        validate_report(report, require_smoke=True, expected_repo_head="abc123")


def test_phase12_release_validator_rejects_provider_attempts_above_cap() -> None:
    report = _phase12_clean_smoke_report()

    with pytest.raises(ValueError, match="provider_attempt_count .* exceeds --max-provider-attempts"):
        validate_report(report, require_smoke=True, expected_repo_head="abc123", max_provider_attempts=0)


def test_phase12_release_validator_rejects_mutating_rows_above_cap() -> None:
    report = _phase12_clean_smoke_report()
    budget = dict(report["budget_consumption"])
    budget["mutating_rows"] = 1
    report["budget_consumption"] = budget

    with pytest.raises(ValueError, match=r"budget_consumption\.mutating_rows .* exceeds --max-mutating-rows"):
        validate_report(report, require_smoke=True, expected_repo_head="abc123", max_mutating_rows=0)


@pytest.mark.parametrize(
    "mutator",
    [
        pytest.param(lambda report: report.pop("provider_attempt_count"), id="missing-provider-attempt-count"),
        pytest.param(
            lambda report: report.__setitem__("provider_attempt_count", "many"), id="malformed-provider-attempt-count"
        ),
    ],
)
def test_phase12_release_validator_fails_closed_on_missing_or_malformed_provider_attempt_count(
    mutator,
) -> None:
    report = _phase12_clean_smoke_report()
    mutator(report)

    with pytest.raises(ValueError, match="provider_attempt_count|provider attempts"):
        validate_report(report, require_smoke=True, expected_repo_head="abc123", max_provider_attempts=1)


@pytest.mark.parametrize(
    "mutator",
    [
        pytest.param(lambda report: report.__setitem__("budget_consumption", "malformed"), id="malformed-budget"),
        pytest.param(
            lambda report: report.__setitem__(
                "budget_consumption",
                {
                    "attempted_subprocesses": 1,
                    "timeouts": 0,
                },
            ),
            id="missing-mutating-rows",
        ),
        pytest.param(
            lambda report: report.__setitem__(
                "budget_consumption",
                {
                    "attempted_subprocesses": 1,
                    "timeouts": 0,
                    "mutating_rows": "many",
                },
            ),
            id="malformed-mutating-rows",
        ),
    ],
)
def test_phase12_release_validator_fails_closed_on_missing_or_malformed_mutating_rows(mutator) -> None:
    report = _phase12_clean_smoke_report()
    mutator(report)

    with pytest.raises(ValueError, match="budget_consumption|mutating_rows|mutating rows"):
        validate_report(report, require_smoke=True, expected_repo_head="abc123", max_mutating_rows=0)


@pytest.mark.parametrize(
    ("finding_key", "finding_class", "severity"),
    [
        ("product_findings", "product_behavior", "S0"),
        ("product_findings", "product_behavior", "S1"),
        ("harness_readiness_findings", "harness_contract", "S0"),
        ("harness_readiness_findings", "harness_contract", "S1"),
        ("provider_environment_findings", "provider_environment", "S0"),
        ("provider_environment_findings", "provider_environment", "S1"),
    ],
)
def test_phase12_release_validator_rejects_s0_s1_product_harness_and_provider_environment_findings(
    finding_key: str,
    finding_class: str,
    severity: str,
) -> None:
    report = _phase12_clean_smoke_report()
    report[finding_key] = [
        {
            "finding_id": f"phase12.{finding_class}.{severity.lower()}",
            "finding_class": finding_class,
            "severity": severity,
            "row_ids": ["row-phase12-smoke"],
            "summary": "Open hard finding must block release smoke.",
        }
    ]

    with pytest.raises(ValueError, match=f"{finding_key}: severity {severity}"):
        validate_report(report, require_smoke=True, expected_repo_head="abc123")


def test_phase8_provider_report_release_validator_rejects_sanitized_intake_as_required_smoke() -> None:
    intake = {
        "schema": "phase8.live-provider-gate.sanitized-intake.v1",
        "repo_head": "abc123",
        "provider_launch_performed": False,
        "provider_material_retained": False,
        "retention_manifest": {
            "entries": [
                {
                    "artifact_ref": "phase8-provider-smoke-report.json",
                    "retention_class": "committed_redacted",
                    "material_class": "sanitized_report",
                    "safe_to_commit": True,
                }
            ]
        },
    }

    validate_report(intake, expected_repo_head="abc123")
    with pytest.raises(ValueError, match="not an accepted Phase 8 provider-attempt smoke report"):
        validate_report(
            intake,
            require_smoke=True,
            expected_repo_head="abc123",
            max_provider_attempts=0,
            max_mutating_rows=0,
        )
