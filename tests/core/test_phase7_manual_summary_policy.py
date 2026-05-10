"""Provider-free guards for the Phase 7 manual live canary policy."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from tests.helpers.persona_summary import (
    assert_persona_summary_valid,
    make_phase7_live_canary_summary,
    phase7_live_canary_policy,
    validate_persona_summary,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK_PATH = REPO_ROOT / "docs" / "dev" / "phase7-live-persona-canary.md"
GITIGNORE_PATH = REPO_ROOT / ".gitignore"

VALID_PUBLIC_SUMMARY = make_phase7_live_canary_summary()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _first_row(summary: dict[str, object]) -> dict[str, object]:
    rows = summary["rows"]
    assert isinstance(rows, list)
    row = rows[0]
    assert isinstance(row, dict)
    return row


def _has_finding(findings: tuple[str, ...], prefix: str, suffix: str = "") -> bool:
    return any(finding.startswith(prefix) and finding.endswith(suffix) for finding in findings)


def test_phase7_manual_live_canary_runbook_documents_the_policy_shape() -> None:
    runbook = _read(RUNBOOK_PATH)

    for required_fragment in (
        "Manual live is opt-in",
        "Raw artifacts stay ignored/operator-local",
        "sanitized class-only summary",
        "Release and publish jobs must not launch provider CLIs",
        "Nightly is deferred",
        "`workflow_dispatch`",
        "`schedule`",
        "phase7.live-persona-canary-summary.v1",
        "tests.helpers.persona_summary",
    ):
        assert required_fragment in runbook


def test_phase7_manual_public_summary_shape_is_class_only_and_opt_in() -> None:
    assert_persona_summary_valid(VALID_PUBLIC_SUMMARY, phase7_live_canary_policy())


@pytest.mark.parametrize(
    "raw_key",
    [
        "raw_prompt",
        "stdout",
        "stderr",
        "argv",
        "env",
        "auth_path",
        "account_id",
        "provider_reply",
        "provider_output",
        "transcript_path",
        "command_line",
        "file_hash",
        "session_id",
        "home_path",
        "raw_prompt_class",
        "provider_reply_class",
        "command_line_class",
        "auth_path_class",
        "file_hash_class",
        "stdout_count",
        "stderr_counts",
        "argv_class",
        "env_counts",
        "secret_classes",
    ],
)
def test_phase7_manual_public_summary_rejects_raw_public_keys(raw_key: str) -> None:
    summary = deepcopy(VALID_PUBLIC_SUMMARY)
    _first_row(summary)[raw_key] = "redacted"

    findings = validate_persona_summary(summary, phase7_live_canary_policy()).findings

    assert any(finding.startswith("forbidden_key:") for finding in findings)


@pytest.mark.parametrize(
    "raw_value",
    [
        "Prompt text: run the whole phase and tell me the answer",
        "raw prompt: run the whole phase and tell me the answer",
        "raw provider reply: the derivation is complete",
        "provider_reply:accepted",
        "stdout",
        "stderr",
        "argv",
        "env",
        "command line: gpd progress --raw",
        "stdout.jsonl",
        "stderr.txt",
        "transcript excerpt from provider",
        "codex exec --json -o output.json -",
        "/Users/example/.codex/auth.json",
        r"C:\Users\example\.gemini",
        "../outside/transcript.md",
        "researcher@example.com",
        "0123456789abcdef0123456789abcdef01234567",
        "OPENAI_API_KEY",
        "Bearer sk-test-secret",
        "ghp_0123456789abcdef0123456789abcdef",
        "a" * 48,
    ],
)
def test_phase7_manual_public_summary_rejects_raw_public_values(raw_value: str) -> None:
    summary = deepcopy(VALID_PUBLIC_SUMMARY)
    _first_row(summary)["finding_classes"] = [raw_value]

    findings = validate_persona_summary(summary, phase7_live_canary_policy()).findings

    assert any(finding.startswith("raw_value:") for finding in findings)


def test_phase7_manual_public_summary_rejects_raw_values_under_class_count_and_counts() -> None:
    summary = deepcopy(VALID_PUBLIC_SUMMARY)
    row = _first_row(summary)
    row["runtime_class"] = "stdout"
    row["leak_count"] = "raw provider reply: hello"
    row["event_class_counts"] = {"env": 1}

    findings = validate_persona_summary(summary, phase7_live_canary_policy()).findings

    assert _has_finding(findings, "raw_value:raw_stream_or_capture:", ".runtime_class")
    assert _has_finding(findings, "raw_value:provider_prompt_or_reply:", ".leak_count")
    assert _has_finding(findings, "invalid_count_value:", ".leak_count")
    assert _has_finding(findings, "raw_value:count_key:", ".env")


@pytest.mark.parametrize(
    ("value", "expected_finding"),
    [
        (True, "invalid_count_value:row_count"),
        (-1, "invalid_count_value:row_count"),
        ("1", "invalid_count_value:row_count"),
        (1.5, "invalid_count_value:row_count"),
    ],
)
def test_phase7_manual_public_summary_rejects_invalid_scalar_counts(value: object, expected_finding: str) -> None:
    summary = deepcopy(VALID_PUBLIC_SUMMARY)
    summary["row_count"] = value

    findings = validate_persona_summary(summary, phase7_live_canary_policy()).findings

    assert expected_finding in findings


def test_phase7_manual_public_summary_rejects_missing_required_scalar_count() -> None:
    summary = deepcopy(VALID_PUBLIC_SUMMARY)
    del summary["row_count"]

    findings = validate_persona_summary(summary, phase7_live_canary_policy()).findings

    assert "required_policy:row_count" in findings


@pytest.mark.parametrize(
    ("count_map", "expected_finding_prefix"),
    [
        ({"redaction_pass": True}, "invalid_count_value:"),
        ({"redaction_pass": -1}, "invalid_count_value:"),
        ({"redaction_pass": "1"}, "invalid_count_value:"),
        ({"redaction_pass": 1.5}, "invalid_count_value:"),
        ({"stdout": 1}, "raw_value:count_key:"),
    ],
)
def test_phase7_manual_public_summary_rejects_invalid_count_maps(
    count_map: dict[str, object], expected_finding_prefix: str
) -> None:
    summary = deepcopy(VALID_PUBLIC_SUMMARY)
    _first_row(summary)["event_class_counts"] = count_map

    findings = validate_persona_summary(summary, phase7_live_canary_policy()).findings

    assert any(finding.startswith(expected_finding_prefix) for finding in findings)


def test_phase7_manual_public_summary_rejects_row_count_mismatch() -> None:
    summary = deepcopy(VALID_PUBLIC_SUMMARY)
    summary["row_count"] = 2

    findings = validate_persona_summary(summary, phase7_live_canary_policy()).findings

    assert "required_policy:row_count" in findings


def test_phase7_manual_public_summary_rejects_non_list_rows() -> None:
    summary = deepcopy(VALID_PUBLIC_SUMMARY)
    summary["rows"] = {"row_id": "LP-RO-RUNTIME"}

    findings = validate_persona_summary(summary, phase7_live_canary_policy()).findings

    assert "required_policy:rows" in findings


def test_phase7_manual_public_summary_rejects_failing_redaction_scan() -> None:
    summary = deepcopy(VALID_PUBLIC_SUMMARY)
    redaction_scan = summary["redaction_scan"]
    assert isinstance(redaction_scan, dict)
    redaction_scan["status_class"] = "fail"

    findings = validate_persona_summary(summary, phase7_live_canary_policy()).findings

    assert _has_finding(findings, "required_policy:", "redaction_scan.status_class")


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("release_publish_provider_launch_allowed", True),
        ("nightly_status_class", "enabled"),
        ("nightly_allowed_triggers", ["pull_request"]),
        ("public_artifact_class", "raw_transcript"),
    ],
)
def test_phase7_manual_public_summary_rejects_incorrect_required_policy_fields(
    field_name: str, field_value: object
) -> None:
    summary = deepcopy(VALID_PUBLIC_SUMMARY)
    summary[field_name] = field_value

    findings = validate_persona_summary(summary, phase7_live_canary_policy()).findings

    assert any(finding.startswith(f"required_policy:{field_name}") for finding in findings)


@pytest.mark.parametrize(
    "command_line",
    [
        "codex exec --json -o output.json -",
        "env FOO=bar uv run codex exec -",
        "command claude --print hello",
        "npx opencode run",
        "npm exec gemini -- --prompt hello",
    ],
)
def test_phase7_manual_public_summary_rejects_provider_command_lines(command_line: str) -> None:
    summary = deepcopy(VALID_PUBLIC_SUMMARY)
    _first_row(summary)["next_step_class"] = command_line

    findings = validate_persona_summary(summary, phase7_live_canary_policy()).findings

    assert any(finding.startswith("raw_value:provider_command_line:") for finding in findings)


def test_phase7_raw_live_artifacts_remain_operator_local_under_ignored_tmp() -> None:
    gitignore_lines = {line.strip() for line in _read(GITIGNORE_PATH).splitlines()}

    assert "tmp/" in gitignore_lines
    assert VALID_PUBLIC_SUMMARY["raw_artifact_retention_class"] == "operator_local_ignored_tmp"
