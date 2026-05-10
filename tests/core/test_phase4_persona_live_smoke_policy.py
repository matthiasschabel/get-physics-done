"""Provider-free guards for the Phase 4 persona live-smoke policy."""

from __future__ import annotations

import json
import re
import shlex
from copy import deepcopy
from pathlib import Path

import pytest

from gpd.adapters.runtime_catalog import iter_runtime_descriptors
from scripts.validate_phase4_persona_summary import SCHEMA_VERSION, main, validate_summary
from tests.helpers.github_actions import (
    github_actions_workflow_paths,
    iter_workflow_steps,
    load_github_actions_workflow,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK_PATH = REPO_ROOT / "docs" / "dev" / "phase4-persona-live-smoke.md"
VALID_PUBLIC_SUMMARY: dict[str, object] = {
    "schema_version": SCHEMA_VERSION,
    "report_id": "phase4-persona-live-smoke-summary-fixture",
    "execution_mode_class": "manual_opt_in",
    "trigger_class": "operator_local_manual",
    "raw_artifact_retention_class": "operator_local_ignored_tmp",
    "public_artifact_class": "sanitized_class_only_summary",
    "provider_launch_source_class": "manual_operator",
    "ci_provider_launch_allowed": False,
    "allowed_trigger_classes": ["operator_local_manual"],
    "row_count": 2,
    "aggregate_class_counts": {"blocked_before_execution": 1, "stopped_before_dispatch": 1},
    "behavior_class_counts": {"smooth": 1, "acceptable": 1},
    "behavior_metric_counts": {
        "invalid_command_suggestion_count": 0,
        "schema_repair_loop_count": 0,
        "unexpected_write_count": 0,
    },
    "redaction_scan": {
        "status_class": "pass",
        "finding_count": 0,
        "finding_classes": [],
    },
    "rows": [
        {
            "row_id": "P4-USER-01",
            "runtime_class": "codex_runtime",
            "persona_class": "user_steering",
            "workflow_class": "execute_phase",
            "gate_class": "claim_deliverable_alignment",
            "result_class": "blocked_before_execution",
            "next_action_class": "gpd:execute-phase",
            "write_class": "no_write",
            "smoothness_class": "smooth",
            "schema_wrestling_class": "none",
            "next_up_specificity_class": "concrete_command",
            "mutation_guard_class": "no_write",
            "invalid_command_suggestion_count": 0,
            "redaction_status_class": "pass",
            "finding_classes": ["alignment_answer_required"],
            "event_class_counts": {"ask_user_missing": 1, "dispatch_blocked": 1},
        },
        {
            "row_id": "P4-USER-02",
            "runtime_class": "claude_runtime",
            "persona_class": "user_steering",
            "workflow_class": "execute_phase",
            "gate_class": "alignment_abort",
            "result_class": "stopped_before_dispatch",
            "next_action_class": "gpd:execute-phase",
            "write_class": "no_write",
            "smoothness_class": "acceptable",
            "schema_wrestling_class": "none",
            "next_up_specificity_class": "bounded_resume",
            "mutation_guard_class": "no_write",
            "invalid_command_suggestion_count": 0,
            "redaction_status_class": "pass",
            "finding_classes": ["user_abort_stops_dispatch"],
            "event_class_counts": {"abort_selected": 1, "dispatch_blocked": 1},
        },
    ],
}

_PROVIDER_LAUNCH_COMMANDS = tuple(
    sorted({Path(shlex.split(descriptor.launch_command)[0]).name for descriptor in iter_runtime_descriptors()})
)
_PROVIDER_COMMAND_SET = frozenset(_PROVIDER_LAUNCH_COMMANDS)
_SHELL_SEGMENT_SPLIT_RE = re.compile(r"(?:&&|\|\||[;|()])")
_SHELL_ASSIGNMENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*")
_PROVIDER_SECRET_ENV_RE = re.compile(
    r"(?<![A-Z0-9_])"
    r"(?:OPENAI|ANTHROPIC|CLAUDE|GEMINI|GOOGLE|CODEX|OPENCODE)_"
    r"(?:API_KEY|AUTH_TOKEN|OAUTH_TOKEN|ACCESS_TOKEN|SECRET|TOKEN|CREDENTIALS|"
    r"CREDENTIALS_JSON|SERVICE_ACCOUNT)"
    r"(?![A-Z0-9_])"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _shell_tokens(segment: str) -> list[str]:
    try:
        return shlex.split(segment, comments=True)
    except ValueError:
        return []


def _provider_command_in_tokens(tokens: list[str]) -> str | None:
    remaining = list(tokens)
    while remaining and _SHELL_ASSIGNMENT_RE.fullmatch(remaining[0]):
        remaining.pop(0)
    while remaining and remaining[0] in {"builtin", "command", "exec", "sudo", "time"}:
        remaining.pop(0)
    if remaining and remaining[0] == "env":
        remaining.pop(0)
        while remaining and (remaining[0].startswith("-") or _SHELL_ASSIGNMENT_RE.fullmatch(remaining[0])):
            remaining.pop(0)
    if len(remaining) >= 3 and remaining[:2] in (["uv", "run"], ["poetry", "run"], ["pipx", "run"]):
        remaining = remaining[2:]
    if remaining and remaining[0] in {"npx", "pnpm", "yarn"}:
        remaining.pop(0)
        while remaining and remaining[0].startswith("-"):
            remaining.pop(0)
    if len(remaining) >= 2 and remaining[:2] == ["npm", "exec"]:
        remaining = remaining[2:]
    if not remaining:
        return None
    command = Path(remaining[0]).name
    return command if command in _PROVIDER_COMMAND_SET else None


def _workflow_provider_launches(script: str) -> list[tuple[int, str, str]]:
    launches: list[tuple[int, str, str]] = []
    for line_no, line in enumerate(script.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for segment in _SHELL_SEGMENT_SPLIT_RE.split(stripped):
            segment = segment.strip()
            if not segment:
                continue
            provider_command = _provider_command_in_tokens(_shell_tokens(segment))
            if provider_command is not None:
                launches.append((line_no, provider_command, segment))
    return launches


def test_phase4_live_smoke_runbook_documents_manual_only_sanitized_policy() -> None:
    runbook = _read(RUNBOOK_PATH)

    for required_fragment in (
        "Manual live is opt-in",
        "launch provider CLIs",
        "provider secret environment names",
        "Raw live artifacts stay ignored and operator-local",
        "sanitized class-only summary",
        "scripts/validate_phase4_persona_summary.py",
        "phase4.persona-live-smoke-summary.v1",
    ):
        assert required_fragment in runbook


def test_phase4_public_summary_validator_accepts_sanitized_class_only_summary() -> None:
    result = validate_summary(VALID_PUBLIC_SUMMARY)

    assert result.valid is True
    assert result.findings == ()


@pytest.mark.parametrize(
    "raw_key",
    [
        "raw_prompt",
        "provider_reply",
        "stdout",
        "stderr",
        "transcript",
        "argv",
        "env",
        "auth_path",
        "account_id",
        "absolute_path",
        "file_hash",
        "token_value",
        "command_line",
        "provider_output",
        "note",
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
def test_phase4_public_summary_validator_rejects_raw_keys(raw_key: str) -> None:
    summary = deepcopy(VALID_PUBLIC_SUMMARY)
    rows = summary["rows"]
    assert isinstance(rows, list)
    row = rows[0]
    assert isinstance(row, dict)
    row[raw_key] = "redacted"

    result = validate_summary(summary)

    assert any(finding.startswith("forbidden_key:") for finding in result.findings)


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
        r"C:\Users\example\.gemini\auth.json",
        "../outside/transcript.md",
        "researcher@example.com",
        "0123456789abcdef0123456789abcdef01234567",
        "OPENAI_API_KEY",
        "Bearer sk-testsecret1234567890",
        "ghp_0123456789abcdef0123456789abcdef",
        "a" * 48,
    ],
)
def test_phase4_public_summary_validator_rejects_raw_values(raw_value: str) -> None:
    summary = deepcopy(VALID_PUBLIC_SUMMARY)
    rows = summary["rows"]
    assert isinstance(rows, list)
    row = rows[0]
    assert isinstance(row, dict)
    row["finding_classes"] = [raw_value]

    result = validate_summary(summary)

    assert any(finding.startswith("raw_value:") for finding in result.findings)


@pytest.mark.parametrize(
    ("field_name", "field_value", "expected_finding_prefix"),
    [
        ("invalid_command_suggestion_count", -1, "invalid_count_value:"),
        ("schema_repair_loop_count", True, "invalid_count_value:"),
        ("behavior_metric_counts", {"invalid_command_suggestion_count": "0"}, "invalid_count_value:"),
        ("behavior_metric_counts", {"stdout": 1}, "raw_value:"),
    ],
)
def test_phase4_public_summary_validator_rejects_invalid_behavior_counts(
    field_name: str, field_value: object, expected_finding_prefix: str
) -> None:
    summary = deepcopy(VALID_PUBLIC_SUMMARY)
    rows = summary["rows"]
    assert isinstance(rows, list)
    row = rows[0]
    assert isinstance(row, dict)
    row[field_name] = field_value

    result = validate_summary(summary)

    assert any(finding.startswith(expected_finding_prefix) for finding in result.findings)


def test_phase4_public_summary_validator_cli_accepts_and_rejects(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    valid_path = tmp_path / "valid-summary.json"
    valid_path.write_text(json.dumps(VALID_PUBLIC_SUMMARY), encoding="utf-8")

    assert main([str(valid_path)]) == 0
    assert "phase4 persona summary valid" in capsys.readouterr().out

    invalid = deepcopy(VALID_PUBLIC_SUMMARY)
    invalid["rows"][0]["provider_reply"] = "redacted"
    invalid_path = tmp_path / "invalid-summary.json"
    invalid_path.write_text(json.dumps(invalid), encoding="utf-8")

    assert main([str(invalid_path)]) == 1
    captured = capsys.readouterr()
    assert "not sanitized/class-only" in captured.err
    assert "forbidden_key:rows.0.provider_reply" in captured.err


def test_phase4_live_smoke_policy_keeps_github_workflows_provider_free() -> None:
    failures: list[str] = []

    for path in github_actions_workflow_paths(REPO_ROOT):
        workflow = load_github_actions_workflow(path)
        for job_id, step in iter_workflow_steps(workflow):
            step_name = step.get("name", "<unnamed>")
            run_script = step.get("run")
            if isinstance(run_script, str):
                for line_no, provider_command, segment in _workflow_provider_launches(run_script):
                    failures.append(
                        f"{path.relative_to(REPO_ROOT)}:{job_id}:{step_name}: line {line_no} "
                        f"runs provider CLI {provider_command!r}: {segment}"
                    )
            uses = step.get("uses")
            if isinstance(uses, str) and Path(uses.split("/", 1)[0]).name in _PROVIDER_COMMAND_SET:
                failures.append(f"{path.relative_to(REPO_ROOT)}:{job_id}:{step_name}: uses {uses!r}")

    assert failures == [], (
        "Phase 4 live smoke evidence may be validated in CI, but workflows must not launch provider CLIs "
        f"({', '.join(_PROVIDER_LAUNCH_COMMANDS)}):\n" + "\n".join(failures)
    )


def test_phase4_live_smoke_policy_keeps_github_workflows_free_of_provider_secret_env_names() -> None:
    failures: list[str] = []

    for path in github_actions_workflow_paths(REPO_ROOT):
        raw_text = path.read_text(encoding="utf-8")
        for match in _PROVIDER_SECRET_ENV_RE.finditer(raw_text):
            line_no = raw_text.count("\n", 0, match.start()) + 1
            failures.append(f"{path.relative_to(REPO_ROOT)}:{line_no}: references {match.group(0)}")

    assert failures == [], (
        "GitHub workflows must not receive live provider secret env names for Phase 4 manual smoke:\n"
        + "\n".join(failures)
    )
