"""Provider-free Phase 7 persona public-artifact redaction contract."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

_ALLOWED_PRIVATE_SURFACE_KEYS = {
    "account_identifiers_recorded",
    "auth_boundary",
    "auth_hash_recorded",
    "auth_material_recorded",
    "auth_path_recorded",
    "auth_state_class",
    "argv_prompt_redacted",
    "argv_values_recorded",
    "env_values_recorded",
    "home_scope_class",
    "network_allowed",
    "normalized_event_classes_only",
    "private_path_recorded",
    "prompt_boundary",
    "prompt_channel_class",
    "prompt_hash_recorded",
    "prompt_in_argv",
    "prompt_in_stdin",
    "prompt_retention_class",
    "prompt_text_recorded",
    "provider_blocker_class",
    "provider_launch_allowed",
    "provider_launch_performed",
    "provider_output_boundary",
    "provider_reply_recorded",
    "provider_subprocess_allowed",
    "raw_artifact_retention",
    "raw_stderr_recorded",
    "raw_stdout_recorded",
    "raw_transcript_recorded",
    "runtime_home_scope_class",
    "stderr_recorded",
    "stdout_recorded",
    "token_values_recorded",
}

_FORBIDDEN_KEY_CLASSES = (
    ("raw_prompt_key", re.compile(r"(^|[_-])raw[_-]?prompt($|[_-])|^prompt$")),
    ("stdout_key", re.compile(r"(^|[_-])raw[_-]?stdout($|[_-])|^stdout$")),
    ("stderr_key", re.compile(r"(^|[_-])raw[_-]?stderr($|[_-])|^stderr$")),
    ("transcript_key", re.compile(r"(^|[_-])raw[_-]?transcript($|[_-])|^transcript$")),
    ("argv_key", re.compile(r"(^|[_-])argv($|[_-])|args?($|[_-])")),
    ("env_key", re.compile(r"(^|[_-])env($|[_-])|environment")),
    ("provider_reply_key", re.compile(r"provider[_-]?reply|provider[_-]?output")),
    ("auth_key", re.compile(r"(^|[_-])auth($|[_-])|auth[_-]?path|auth[_-]?file")),
    ("account_key", re.compile(r"(^|[_-])account($|[_-])|account[_-]?(id|email)")),
    ("token_key", re.compile(r"(^|[_-])token($|[_-])|api[_-]?key|secret")),
    ("session_key", re.compile(r"(^|[_-])session($|[_-])|session[_-]?id")),
    ("home_path_key", re.compile(r"home[_-]?path")),
)

_FORBIDDEN_VALUE_CLASSES = (
    ("private_key_value", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("bearer_token_value", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}")),
    ("token_value", re.compile(r"\b(?:sk|ghp|xox[baprs])-[A-Za-z0-9_-]{12,}")),
    ("email_value", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("home_path_value", re.compile(r"(?:/Users/[^/\s]+|/home/[^/\s]+|C:\\Users\\[^\\\s]+)")),
    ("absolute_private_path_value", re.compile(r"(?:/private/(?:var|tmp)|/var/folders|/Volumes/[^/\s]+)")),
    ("account_value", re.compile(r"\b(?:acct|account|org|tenant)[_-][A-Za-z0-9_-]{8,}\b", re.IGNORECASE)),
    ("session_value", re.compile(r"\b(?:session|sess)[_-][A-Za-z0-9_-]{8,}\b", re.IGNORECASE)),
)

_SENSITIVE_RECORDED_FLAGS = {
    "account_identifiers_recorded",
    "auth_hash_recorded",
    "auth_material_recorded",
    "auth_path_recorded",
    "argv_values_recorded",
    "env_values_recorded",
    "final_text_recorded",
    "private_path_recorded",
    "prompt_hash_recorded",
    "prompt_text_recorded",
    "provider_reply_recorded",
    "raw_stderr_recorded",
    "raw_stdout_recorded",
    "raw_transcript_recorded",
    "stderr_recorded",
    "stdout_recorded",
    "token_values_recorded",
}

_PHASE7_FIXTURE_CANDIDATES = (
    REPO_ROOT / "tests/fixtures/phase7_live_persona_matrix.json",
    REPO_ROOT / "tests/fixtures/persona_matrix/phase7_minimal_live_rows.json",
    REPO_ROOT / "tests/fixtures/persona_matrix/phase7_public_summary.json",
)

_INLINE_PUBLIC_REPORT = {
    "schema_version": "phase7.persona-public-report.v1",
    "report_id": "phase7-provider-free-persona-redaction-v1",
    "generated_by": "provider_free_fixture",
    "provider_launch_performed": False,
    "network_allowed": False,
    "row_count": 2,
    "rows": [
        {
            "row_id": "LP01-START-PROJECTLESS-READONLY",
            "persona_class": "zero_coder",
            "workflow_id": "start",
            "runtime_scope": ["all_supported"],
            "launch_policy": {
                "mode": "provider_free_fake",
                "collection": "default_pytest",
                "provider_subprocess_allowed": False,
                "network_allowed": False,
                "live_marker_required": False,
            },
            "expected_behavior": {
                "required_event_classes": [
                    "workspace_classified_projectless",
                    "official_command_names_visible",
                ],
                "forbidden_event_classes": [
                    "provider_launch_attempted",
                    "raw_prompt_or_provider_output_exposed",
                ],
            },
            "redaction": {
                "status": "pass",
                "finding_classes": [],
                "class_only_public_result": True,
            },
        },
        {
            "row_id": "LP10-AUTH-PERMISSION-BLOCK",
            "persona_class": "runtime_power_user",
            "workflow_id": "auth_permission_block",
            "runtime_scope": ["all_supported"],
            "provider_launch_allowed": False,
            "network_allowed": False,
            "prompt_boundary": {
                "prompt_channel_class": "unknown",
                "prompt_in_argv": False,
                "prompt_in_stdin": False,
                "argv_prompt_redacted": True,
                "prompt_text_recorded": False,
                "prompt_hash_recorded": False,
                "prompt_retention_class": "not_recorded",
            },
            "auth_boundary": {
                "auth_state_class": "metadata_only",
                "provider_blocker_class": "provider_auth_unknown",
                "account_identifiers_recorded": False,
                "auth_material_recorded": False,
                "auth_path_recorded": False,
                "auth_hash_recorded": False,
                "token_values_recorded": False,
                "stdout_recorded": False,
                "stderr_recorded": False,
            },
            "runtime_boundary": {
                "runtime_home_scope_class": "not_recorded",
                "env_values_recorded": False,
                "argv_values_recorded": False,
                "private_path_recorded": False,
            },
            "provider_output_boundary": {
                "provider_reply_recorded": False,
                "raw_stdout_recorded": False,
                "raw_stderr_recorded": False,
                "raw_transcript_recorded": False,
                "final_text_recorded": False,
                "normalized_event_classes_only": True,
            },
            "semantic_score": {
                "result_class": "blocked",
                "finding_classes": ["provider_auth_unknown"],
                "event_class_counts": {"provider_boundary": 1},
            },
            "redaction": {
                "status": "pass",
                "finding_classes": [],
                "class_only_public_result": True,
            },
        },
    ],
    "aggregate_counts": {"blocked": 1, "pass": 1},
    "redaction_scan": {
        "status": "pass",
        "finding_count": 0,
        "finding_classes": [],
    },
}


def _fixture_payloads() -> list[dict[str, object]]:
    payloads = [_INLINE_PUBLIC_REPORT]
    for path in _PHASE7_FIXTURE_CANDIDATES:
        if path.exists():
            payloads.append(json.loads(path.read_text(encoding="utf-8")))
    return payloads


def _rows_from_payload(payload: dict[str, object]) -> list[dict[str, object]]:
    rows = payload.get("rows")
    if isinstance(rows, list):
        return rows
    if isinstance(payload.get("matrix_rows"), list):
        return payload["matrix_rows"]
    if isinstance(payload.get("fixtures"), list):
        return []
    raise AssertionError("Phase 7 public payload must expose rows or matrix_rows")


def _scan_public_artifact(value: object) -> tuple[str, ...]:
    findings: set[str] = set()

    def visit(node: object) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                normalized_key = str(key).lower()
                if normalized_key not in _ALLOWED_PRIVATE_SURFACE_KEYS:
                    for finding_class, pattern in _FORBIDDEN_KEY_CLASSES:
                        if pattern.search(normalized_key):
                            findings.add(finding_class)
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)
        elif isinstance(node, str):
            for finding_class, pattern in _FORBIDDEN_VALUE_CLASSES:
                if pattern.search(node):
                    findings.add(finding_class)

    visit(value)
    return tuple(sorted(findings))


def _assert_provider_free_row(row: dict[str, object]) -> None:
    launch_policy = row.get("launch_policy")
    if isinstance(launch_policy, dict):
        assert launch_policy.get("mode") == "provider_free_fake"
        assert launch_policy.get("provider_subprocess_allowed") is False
        assert launch_policy.get("network_allowed") is False
        assert launch_policy.get("live_marker_required") is False
    else:
        assert row.get("provider_launch_allowed") is False
        assert row.get("network_allowed") is False


def _assert_sensitive_flags_false(node: object) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _SENSITIVE_RECORDED_FLAGS:
                assert value is False, f"{key} must be false in public Phase 7 artifacts"
            if key == "normalized_event_classes_only":
                assert value is True
            _assert_sensitive_flags_false(value)
    elif isinstance(node, list):
        for value in node:
            _assert_sensitive_flags_false(value)


def test_phase7_public_rows_are_provider_free_and_class_only() -> None:
    for payload in _fixture_payloads():
        assert payload.get("provider_launch_performed", False) is False
        assert payload.get("network_allowed", False) is False
        assert _scan_public_artifact(payload) == ()

        rows = _rows_from_payload(payload)
        assert rows
        for row in rows:
            _assert_provider_free_row(row)
            _assert_sensitive_flags_false(row)


@pytest.mark.parametrize(
    ("key", "expected_class"),
    [
        ("raw_prompt", "raw_prompt_key"),
        ("prompt", "raw_prompt_key"),
        ("stdout", "stdout_key"),
        ("stderr", "stderr_key"),
        ("transcript", "transcript_key"),
        ("argv", "argv_key"),
        ("env", "env_key"),
        ("provider_reply", "provider_reply_key"),
        ("auth", "auth_key"),
        ("account", "account_key"),
        ("token", "token_key"),
        ("session", "session_key"),
        ("home_path", "home_path_key"),
    ],
)
def test_phase7_redaction_rejects_forbidden_public_keys(key: str, expected_class: str) -> None:
    findings = _scan_public_artifact({"schema_version": "phase7.test", key: "sentinel"})

    assert expected_class in findings
    assert "sentinel" not in findings


@pytest.mark.parametrize(
    ("value", "expected_class"),
    [
        ("/Users/example/.codex/auth.json", "home_path_value"),
        ("/private/var/folders/operator/auth.json", "absolute_private_path_value"),
        ("researcher@example.com", "email_value"),
        ("-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----", "private_key_value"),
        ("Bearer abcdefghijklmnopqrstuvwxyz", "bearer_token_value"),
        ("sk-test_0123456789abcdef", "token_value"),
        ("acct_0123456789abcdef", "account_value"),
        ("session_0123456789abcdef", "session_value"),
    ],
)
def test_phase7_redaction_rejects_forbidden_public_values(value: str, expected_class: str) -> None:
    findings = _scan_public_artifact({"schema_version": "phase7.test", "status_class": value})

    assert expected_class in findings
    assert value not in findings
