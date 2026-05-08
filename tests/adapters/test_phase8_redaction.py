from __future__ import annotations

from copy import deepcopy
from typing import cast

import pytest

from tests.helpers.live_audit_harness.redaction import (
    SAFE_TO_COMMIT_RETENTION_CLASSES,
    validate_provider_report_safety,
)


def _safe_report() -> dict[str, object]:
    return {
        "schema": "phase8.provider_attempt_report.v1",
        "attempt_id": "attempt-phase8-001",
        "batch_id": "batch-phase8-001",
        "row_set_sha256": "0" * 64,
        "repo_head": "abc1234",
        "provider_set": ["codex", "gemini"],
        "auth_profile": {
            "codex": {"status_class": "ready", "account_class": "operator_configured"},
            "gemini": {"status_class": "metadata_only", "account_class": "not_recorded"},
        },
        "runtime_capabilities": [
            {
                "runtime": "codex",
                "runner_status": "ready",
                "auth_probe_class": "metadata_only",
                "event_stream_class": "normalized_events",
            }
        ],
        "budget_consumption": {"attempted_subprocesses": 1, "timeouts": 0, "mutating_rows": 0},
        "rows": [
            {
                "row_id": "codex-P00-help",
                "provider_runtime": "codex",
                "persona_id": "P00_zero_coder",
                "scenario_id": "HELP-BEGINNER",
                "command_bucket": "start",
                "prompt_budget": {"budget_class": "small", "limit_class": "bounded"},
                "sidecar_status": "sanitized",
                "attempt_status": "completed",
                "write_status": "read_only",
                "retention_refs": ["provider-attempt-summary.json", "codex-raw-transcript.local"],
            }
        ],
        "findings": [{"finding_id": "none", "finding_class": "product_behavior", "severity": "S3"}],
        "retention_manifest": [
            {
                "artifact_ref": "provider-attempt-summary.json",
                "retention_class": "committed_redacted",
                "material_class": "sanitized_report",
                "safe_to_commit": True,
            },
            {
                "artifact_ref": "codex-raw-transcript.local",
                "retention_class": "operator_local_raw",
                "material_class": "provider_transcript",
                "safe_to_commit": False,
                "local_only": True,
            },
            {
                "artifact_ref": "prompt-argv",
                "retention_class": "never_record",
                "material_class": "prompt_in_argv",
                "safe_to_commit": False,
                "retained": False,
            },
        ],
    }


def _with_report_mutation(path: tuple[object, ...], value: object) -> dict[str, object]:
    report = deepcopy(_safe_report())
    target: object = report
    for part in path[:-1]:
        if isinstance(part, int):
            target = cast(list[object], target)[part]
        else:
            target = cast(dict[str, object], target)[part]
    last = path[-1]
    if isinstance(last, int):
        cast(list[object], target)[last] = value
    else:
        cast(dict[str, object], target)[last] = value
    return report


def test_provider_report_safety_accepts_sanitized_report_with_retention_manifest() -> None:
    report = _safe_report()

    validate_provider_report_safety(report)

    assert SAFE_TO_COMMIT_RETENTION_CLASSES == frozenset({"committed_redacted"})


@pytest.mark.parametrize(
    ("path", "value", "match"),
    [
        (("rows", 0, "raw_transcript"), "full provider transcript", "raw provider output/transcript field"),
        (("rows", 0, "provider_output"), {"text": "provider said yes"}, "raw provider output/transcript field"),
        (("rows", 0, "stdout"), "provider stdout", "raw provider output/transcript field"),
        (("rows", 0, "stderr"), "provider stderr", "raw provider output/transcript field"),
        (("rows", 0, "argv"), ["codex", "exec", "full prompt text"], "argv/env dump field"),
        (("rows", 0, "env"), {"OPENAI_API_KEY": "redacted"}, "argv/env dump field"),
        (("auth_profile", "codex", "auth_path"), "/isolated/home/.codex/auth.json", "auth path field"),
    ],
)
def test_provider_report_safety_rejects_raw_provider_dump_fields(
    path: tuple[object, ...], value: object, match: str
) -> None:
    report = _with_report_mutation(path, value)

    with pytest.raises(ValueError, match=match):
        validate_provider_report_safety(report)


@pytest.mark.parametrize(
    ("path", "value", "match"),
    [
        (("auth_profile", "codex", "token_status"), "sk-ant-" + "a" * 28, "secret-looking token"),
        (("auth_profile", "codex", "header_class"), "Authorization: Bearer " + "a" * 24, "authorization header"),
        (("auth_profile", "codex", "key_class"), "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----", "private-key"),
        (("source_root",), "/Users/sergio/GitHub/get-physics-done", "real home path"),
        (("auth_profile", "codex", "account_class"), "sergio@example.com", "account identifier"),
        (("auth_profile", "codex", "storage_class"), "~/.config/gcloud/application_default_credentials.json", "home path"),
    ],
)
def test_provider_report_safety_rejects_sensitive_string_values(
    path: tuple[object, ...], value: object, match: str
) -> None:
    report = _with_report_mutation(path, value)

    with pytest.raises(ValueError, match=match):
        validate_provider_report_safety(report)


def test_provider_report_safety_allows_email_outside_auth_provider_context() -> None:
    report = _with_report_mutation(("operator_contact_class",), "owner@example.com")

    validate_provider_report_safety(report)


def test_provider_report_safety_requires_retention_class_for_manifest_entries() -> None:
    report = _safe_report()
    manifest = cast(list[dict[str, object]], report["retention_manifest"])
    del manifest[0]["retention_class"]

    with pytest.raises(ValueError, match="missing retention_class"):
        validate_provider_report_safety(report)


def test_provider_report_safety_requires_every_referenced_artifact_in_manifest() -> None:
    report = _safe_report()
    rows = cast(list[dict[str, object]], report["rows"])
    retention_refs = cast(list[str], rows[0]["retention_refs"])
    retention_refs.append("untracked-artifact.json")

    with pytest.raises(ValueError, match="has no retention manifest entry"):
        validate_provider_report_safety(report)


def test_provider_report_safety_rejects_unsafe_retention_class_marked_safe_to_commit() -> None:
    report = _safe_report()
    manifest = cast(list[dict[str, object]], report["retention_manifest"])
    manifest[1]["safe_to_commit"] = True

    with pytest.raises(ValueError, match="safe_to_commit is true for an unsafe retention class"):
        validate_provider_report_safety(report)


def test_provider_report_safety_rejects_raw_provider_material_as_committed() -> None:
    report = _safe_report()
    manifest = cast(list[dict[str, object]], report["retention_manifest"])
    manifest[1]["retention_class"] = "committed_redacted"
    manifest[1]["safe_to_commit"] = True

    with pytest.raises(ValueError, match="raw provider material"):
        validate_provider_report_safety(report)


def test_provider_report_safety_requires_unsafe_classes_to_be_local_or_unretained() -> None:
    report = _safe_report()
    manifest = cast(list[dict[str, object]], report["retention_manifest"])
    del manifest[1]["local_only"]

    with pytest.raises(ValueError, match="local-only or not-retained"):
        validate_provider_report_safety(report)
