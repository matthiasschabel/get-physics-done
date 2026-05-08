"""Provider-free guards for the Phase 7 manual live canary policy."""

from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path

import pytest

from gpd.adapters.runtime_catalog import iter_runtime_descriptors
from tests.helpers.github_actions import (
    github_actions_workflow_paths,
    iter_workflow_steps,
    load_github_actions_workflow,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK_PATH = REPO_ROOT / "docs" / "dev" / "phase7-live-persona-canary.md"
GITIGNORE_PATH = REPO_ROOT / ".gitignore"

SAFE_LITERAL_KEYS = {
    "schema_version",
    "report_id",
    "row_id",
    "row_count",
    "finding_count",
    "release_publish_provider_launch_allowed",
}
SAFE_CONTAINER_KEYS = {
    "aggregate_class_counts",
    "event_class_counts",
    "finding_classes",
    "nightly_allowed_triggers",
    "redaction_scan",
    "rows",
}
SAFE_NIGHTLY_TRIGGERS = {"workflow_dispatch", "schedule"}
RAW_KEY_FRAGMENTS = (
    "account",
    "argv",
    "auth",
    "command",
    "content",
    "diff",
    "env",
    "hash",
    "home",
    "path",
    "prompt",
    "provider",
    "reply",
    "session",
    "stderr",
    "stdout",
    "token",
    "transcript",
)
RAW_VALUE_PATTERNS = {
    "local_path": re.compile(r"(?:^|[\s`'\"])(?:/Users/|/home/|/private/|[A-Za-z]:\\Users\\)"),
    "parent_traversal": re.compile(r"(?:^|/)\.\.(?:/|$)"),
    "secret_value": re.compile(
        r"(?:Bearer\s+|sk-[A-Za-z0-9]|ghp_[A-Za-z0-9]|OPENAI_API_KEY|ANTHROPIC_API_KEY|GEMINI_API_KEY)"
    ),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "account_identifier": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "raw_artifact_file": re.compile(
        r"\b(?:prompt\.txt|command\.json|env\.json|stdout\.jsonl|stderr\.txt|transcript\.md)\b"
    ),
    "provider_output": re.compile(r"\b(?:raw provider reply|final answer text|transcript excerpt)\b", re.I),
}
PROVIDER_LAUNCH_PATTERNS = tuple(
    (
        descriptor.runtime_name,
        re.compile(rf"(?<![\w/-]){re.escape(descriptor.launch_command.split()[0])}(?:\s|$)", re.I),
    )
    for descriptor in iter_runtime_descriptors()
)
PHASE7_NIGHTLY_WORKFLOW_RE = re.compile(r"(?:phase7|live[-_ ]persona|persona[-_ ]canary|nightly)", re.I)

VALID_PUBLIC_SUMMARY: dict[str, object] = {
    "schema_version": "phase7.live-persona-canary-summary.v1",
    "report_id": "phase7-manual-canary-summary-fixture",
    "execution_mode_class": "manual_opt_in",
    "trigger_class": "operator_local_manual",
    "raw_artifact_retention_class": "operator_local_ignored_tmp",
    "public_artifact_class": "sanitized_class_only_summary",
    "provider_launch_source_class": "manual_operator",
    "release_publish_provider_launch_allowed": False,
    "nightly_status_class": "deferred",
    "nightly_allowed_triggers": ["workflow_dispatch", "schedule"],
    "row_count": 1,
    "aggregate_class_counts": {"blocked": 1, "no_write": 1},
    "redaction_scan": {
        "status_class": "pass",
        "finding_count": 0,
        "finding_classes": [],
    },
    "rows": [
        {
            "row_id": "LP-RO-RUNTIME",
            "runtime_class": "runtime_catalog_member",
            "persona_class": "zero_coder_recovery",
            "workflow_class": "read_only_setup_recovery",
            "launch_policy_class": "manual_opt_in",
            "write_class": "no_write",
            "result_class": "blocked",
            "next_step_class": "operator_review",
            "artifact_retention_class": "operator_local_ignored_tmp",
            "redaction_status_class": "pass",
            "finding_classes": ["provider_auth_unknown"],
            "event_class_counts": {"setup_refusal": 1, "redaction_pass": 1},
        }
    ],
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _event_names(on_value: object) -> set[str]:
    if isinstance(on_value, str):
        return {on_value}
    if isinstance(on_value, list):
        return {str(event) for event in on_value}
    if isinstance(on_value, dict):
        return {str(event) for event in on_value}
    raise AssertionError(f"Unsupported GitHub Actions trigger shape: {on_value!r}")


def _key_is_class_only_or_policy_safe(key: str) -> bool:
    if key in SAFE_LITERAL_KEYS or key in SAFE_CONTAINER_KEYS:
        return True
    if key.endswith(("_class", "_classes")):
        return True
    if key.endswith(("_count", "_counts")):
        return True
    return not any(fragment in key.lower() for fragment in RAW_KEY_FRAGMENTS)


def _record_string_findings(value: str, path: tuple[str, ...], findings: list[str]) -> None:
    for finding_class, pattern in RAW_VALUE_PATTERNS.items():
        if pattern.search(value):
            findings.append(f"raw_value:{finding_class}:{'.'.join(path)}")


def _public_summary_policy_findings(value: object, path: tuple[str, ...] = ()) -> list[str]:
    findings: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                findings.append(f"non_string_key:{'.'.join(path)}")
                continue
            child_path = (*path, key)
            if not _key_is_class_only_or_policy_safe(key):
                findings.append(f"forbidden_key:{'.'.join(child_path)}")
            if key.endswith("_counts"):
                if not isinstance(child, Mapping) or not all(
                    isinstance(count_key, str) and isinstance(count_value, int)
                    for count_key, count_value in child.items()
                ):
                    findings.append(f"invalid_count_map:{'.'.join(child_path)}")
                continue
            findings.extend(_public_summary_policy_findings(child, child_path))
        return findings
    if isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_public_summary_policy_findings(child, (*path, str(index))))
        return findings
    if isinstance(value, str):
        _record_string_findings(value, path, findings)
        return findings
    if value is None or isinstance(value, bool | int):
        return findings
    findings.append(f"unsupported_value_type:{'.'.join(path)}:{type(value).__name__}")
    return findings


def _assert_required_manual_policy(summary: Mapping[str, object]) -> None:
    assert summary["schema_version"] == "phase7.live-persona-canary-summary.v1"
    assert summary["execution_mode_class"] == "manual_opt_in"
    assert summary["trigger_class"] == "operator_local_manual"
    assert summary["raw_artifact_retention_class"] == "operator_local_ignored_tmp"
    assert summary["public_artifact_class"] == "sanitized_class_only_summary"
    assert summary["provider_launch_source_class"] == "manual_operator"
    assert summary["release_publish_provider_launch_allowed"] is False
    assert summary["nightly_status_class"] == "deferred"
    assert set(summary["nightly_allowed_triggers"]) <= SAFE_NIGHTLY_TRIGGERS


def _provider_launch_matches(text: str) -> list[str]:
    return [name for name, pattern in PROVIDER_LAUNCH_PATTERNS if pattern.search(text)]


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
    ):
        assert required_fragment in runbook


def test_phase7_manual_public_summary_shape_is_class_only_and_opt_in() -> None:
    _assert_required_manual_policy(VALID_PUBLIC_SUMMARY)

    assert _public_summary_policy_findings(VALID_PUBLIC_SUMMARY) == []


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
        "transcript_path",
        "command_line",
        "file_hash",
    ],
)
def test_phase7_manual_public_summary_rejects_raw_public_keys(raw_key: str) -> None:
    summary = deepcopy(VALID_PUBLIC_SUMMARY)
    summary["rows"][0][raw_key] = "redacted"

    findings = _public_summary_policy_findings(summary)

    assert any(finding.startswith("forbidden_key:") for finding in findings)


@pytest.mark.parametrize(
    "raw_value",
    [
        "/Users/example/.codex/auth.json",
        r"C:\Users\example\.gemini",
        "../outside/transcript.md",
        "Bearer sk-test-secret",
        "-----BEGIN PRIVATE KEY-----",
        "researcher@example.com",
        "tmp/live-audit-v3/stdout.jsonl",
        "raw provider reply: hello",
    ],
)
def test_phase7_manual_public_summary_rejects_raw_public_values(raw_value: str) -> None:
    summary = deepcopy(VALID_PUBLIC_SUMMARY)
    summary["rows"][0]["finding_classes"] = [raw_value]

    findings = _public_summary_policy_findings(summary)

    assert any(finding.startswith("raw_value:") for finding in findings)


def test_phase7_raw_live_artifacts_remain_operator_local_under_ignored_tmp() -> None:
    gitignore_lines = {line.strip() for line in _read(GITIGNORE_PATH).splitlines()}

    assert "tmp/" in gitignore_lines
    assert VALID_PUBLIC_SUMMARY["raw_artifact_retention_class"] == "operator_local_ignored_tmp"


def test_phase7_release_and_publish_workflows_do_not_launch_live_providers() -> None:
    for workflow_name in ("release.yml", "publish-release.yml"):
        workflow_path = REPO_ROOT / ".github" / "workflows" / workflow_name
        workflow = load_github_actions_workflow(workflow_path)

        assert _event_names(workflow["on"]) == {"workflow_dispatch"}
        launch_sites: list[str] = []
        for job_id, step in iter_workflow_steps(workflow):
            step_text = "\n".join(str(step.get(key, "")) for key in ("name", "uses", "run"))
            matches = _provider_launch_matches(step_text)
            if matches:
                launch_sites.append(f"{workflow_name}:{job_id}:{step.get('name', '<unnamed>')}:{matches}")

        assert launch_sites == []


def test_phase7_live_or_nightly_workflows_are_manual_or_schedule_only() -> None:
    candidate_paths = []
    for workflow_path in github_actions_workflow_paths(REPO_ROOT):
        workflow_text = _read(workflow_path)
        if PHASE7_NIGHTLY_WORKFLOW_RE.search(f"{workflow_path.name}\n{workflow_text}"):
            candidate_paths.append(workflow_path)

    for workflow_path in candidate_paths:
        workflow = load_github_actions_workflow(workflow_path)
        events = _event_names(workflow["on"])
        assert events <= SAFE_NIGHTLY_TRIGGERS, (
            f"{workflow_path.relative_to(REPO_ROOT)} must use workflow_dispatch/schedule only, got {sorted(events)}"
        )
