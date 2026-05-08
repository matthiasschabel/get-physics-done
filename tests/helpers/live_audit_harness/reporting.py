"""Deterministic Phase 7 live-audit report rendering helpers."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from hashlib import sha256

from gpd.adapters.runtime_catalog import iter_runtime_descriptors

FAKE_MATRIX_REPORT_SCHEMA = "phase7.fake_matrix_report.v1"
TREND_DASHBOARD_SCHEMA = "phase7.trend_dashboard.v1"
PROVIDER_ATTEMPT_REPORT_SCHEMA = "phase8.provider_attempt_report.v1"

_GENERATED_AT = "1970-01-01T00:00:00Z"
_MISSING = object()
_NESTED_SOURCES = ("row", "run", "scenario", "score", "metadata", "contract")
_SEVERITY_RANK = {"S0": 0, "S1": 1, "S2": 2, "S3": 3, "unknown": 99}
_PROVIDER_FINDING_CLASSES = frozenset(
    {
        "product_behavior",
        "harness_contract",
        "provider_environment",
        "auth_quota",
        "prompt_budget",
        "artifact_retention",
        "reporting_contract",
    }
)
_PROVIDER_DECISIONS = frozenset({"accept", "needs_repair", "blocked", "pending"})
_PROVIDER_LAUNCH_POLICIES = frozenset({"manual_live", "nightly_live", "setup_refusal", "deferred"})
_PROVIDER_ATTEMPT_STATUSES = frozenset(
    {"not_started", "attempted", "completed", "failed", "timeout", "setup_refused", "deferred", "unsupported"}
)
_RUNTIME_LIVE_STATUSES = frozenset({"ready", "metadata_only", "deferred", "unsupported"})
_RETENTION_CLASS_DEFAULTS = {
    "committed_redacted": {
        "safe_to_commit": True,
        "local_only": False,
        "description": "Sanitized class-only summary committed to the repository.",
    },
    "operator_local_raw": {
        "safe_to_commit": False,
        "local_only": True,
        "description": "Operator-local raw material that is never uploaded as a committed artifact.",
    },
    "discard_after_summary": {
        "safe_to_commit": False,
        "local_only": True,
        "description": "Temporary material discarded after the sanitized summary is rendered.",
    },
    "never_record": {
        "safe_to_commit": False,
        "local_only": True,
        "description": "Sensitive material that must not be written to disk.",
    },
}
_FORBIDDEN_PROVIDER_REPORT_KEYS = frozenset(
    {
        "args",
        "account_identifier",
        "account_id",
        "argv",
        "auth_header",
        "authorization",
        "environment",
        "env",
        "full_argv",
        "process_env",
        "prompt",
        "prompt_in_argv",
        "prompt_text",
        "provider_argv",
        "provider_output",
        "provider_stderr",
        "provider_stdout",
        "raw_auth",
        "raw_output",
        "raw_prompt",
        "raw_provider_output",
        "raw_stderr",
        "raw_stdout",
        "raw_transcript",
        "stderr",
        "stdout",
        "transcript",
    }
)
_TOKEN_VALUE_RE = re.compile(
    r"(?:\bBearer\s+[A-Za-z0-9._~+/=-]{12,}|\bsk-[A-Za-z0-9_-]{20,}\b|\bgh[pousr]_[A-Za-z0-9_]{20,}\b)",
    re.IGNORECASE,
)
_PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_REAL_HOME_PATH_RE = re.compile(r"(?:/Users/[^/\s]+/|/home/[^/\s]+/|[A-Za-z]:\\Users\\[^\\\s]+\\)")


def render_fake_matrix_report(
    scores: Sequence[object], *, scenario_set_id: str, repo_head: str = "unknown"
) -> dict[str, object]:
    """Render a deterministic provider-free fake matrix report from score-like objects."""

    rendered_rows: list[dict[str, object]] = []
    finding_records: list[dict[str, str]] = []
    for index, score in enumerate(scores):
        row, row_findings = _render_row(score, index)
        rendered_rows.append(row)
        finding_records.extend(row_findings)

    rows = sorted(rendered_rows, key=_row_order_key)
    findings = _aggregate_findings(finding_records)
    aggregates = _aggregate_rows(rows, findings)
    row_set_sha256 = _stable_sha256(rows)

    return {
        "schema": FAKE_MATRIX_REPORT_SCHEMA,
        "generated_at": _GENERATED_AT,
        "repo_head": repo_head,
        "source_tree_status": "not_inspected",
        "runtime_catalog_sha256": "not_computed",
        "scenario_set_id": scenario_set_id,
        "row_set_sha256": row_set_sha256,
        "fake_modes": sorted({str(row["fake_mode"]) for row in rows}),
        "provider_subprocess_allowed": False,
        "rows": rows,
        "aggregates": aggregates,
        "findings": findings,
        "quarantine": [str(row["row_id"]) for row in rows if row.get("quarantined") is True],
    }


def render_trend_dashboard(matrix_report: Mapping[str, object]) -> dict[str, object]:
    """Render Phase 8 promotion status from a deterministic fake matrix report."""

    rows = _rows_from_report(matrix_report)
    findings = _findings_from_report(matrix_report)
    aggregates = _mapping_from_report(matrix_report, "aggregates")
    row_count = len(rows)
    provider_subprocess_attempts = _as_int(aggregates.get("provider_subprocess_attempts"), default=0)
    network_attempts = _as_int(aggregates.get("network_attempts"), default=0)
    red_or_invalid_rows = [str(row.get("row_id", "")) for row in rows if _is_red_or_invalid(row)]
    non_green_rows = [str(row.get("row_id", "")) for row in rows if row.get("result_class") != "green"]

    gates = {
        "fake_runner_contract": _gate(row_count > 0 and _all_rows_have(rows, "fake_mode")),
        "scenario_identity": _identity_gate(rows, "scenario_id"),
        "persona_identity": _identity_gate(rows, "persona_id"),
        "adapter_policy": _gate(provider_subprocess_attempts == 0 and _all_rows_have(rows, "provider_adapter")),
        "auth_quota_metadata": _gate(provider_subprocess_attempts == 0),
        "acceptance_classification": _classification_gate(red_or_invalid_rows, non_green_rows, row_count),
        "report_rendering": _gate(matrix_report.get("schema") == FAKE_MATRIX_REPORT_SCHEMA),
        "default_pytest_no_network": _gate(provider_subprocess_attempts == 0 and network_attempts == 0),
    }
    decision = _trend_decision(
        row_count=row_count,
        red_or_invalid_rows=red_or_invalid_rows,
        non_green_rows=non_green_rows,
        provider_subprocess_attempts=provider_subprocess_attempts,
        network_attempts=network_attempts,
        gates=gates,
    )

    return {
        "schema": TREND_DASHBOARD_SCHEMA,
        "generated_at": _GENERATED_AT,
        "source_schema": matrix_report.get("schema", "unknown"),
        "scenario_set_id": matrix_report.get("scenario_set_id", "unknown"),
        "row_set_sha256": matrix_report.get("row_set_sha256", "unknown"),
        "metrics": {
            "row_count": row_count,
            "pass_rate_overall": _pass_rate(rows),
            "pass_rate_by_runtime": _pass_rate_by(rows, "provider_runtime"),
            "pass_rate_by_command_bucket": _pass_rate_by(rows, "command_bucket"),
            "pass_rate_by_risk_tier": _pass_rate_by(rows, "risk_tier"),
            "status_counts": _counter_dict(str(row.get("status", "unknown")) for row in rows),
            "result_class_counts": _counter_dict(str(row.get("result_class", "unknown")) for row in rows),
            "unique_s0_s1_finding_count": sum(1 for finding in findings if finding.get("severity") in {"S0", "S1"}),
            "rows_quarantined": len([row for row in rows if row.get("quarantined") is True]),
            "provider_subprocess_attempts": provider_subprocess_attempts,
            "network_attempts": network_attempts,
        },
        "gates": gates,
        "decision": decision,
        "decision_reasons": _decision_reasons(
            red_or_invalid_rows=red_or_invalid_rows,
            non_green_rows=non_green_rows,
            provider_subprocess_attempts=provider_subprocess_attempts,
            network_attempts=network_attempts,
            row_count=row_count,
        ),
    }


def provider_attempt_report_schema() -> dict[str, object]:
    """Return a class-only Phase 8 provider attempt report schema skeleton."""

    return {
        "schema": PROVIDER_ATTEMPT_REPORT_SCHEMA,
        "schema_kind": "class_only_schema_skeleton",
        "rendered_report_contract": True,
        "title": "Phase 8 manual/nightly provider attempt report",
        "default_pytest_policy": {
            "live_rows_in_default_pytest": False,
            "provider_subprocess_allowed_in_default_pytest": False,
            "allowed_live_collections": ["manual", "nightly"],
            "required_pytest_marker": "live_provider",
            "provider_attempts_count_against_live_budget": True,
        },
        "required": [
            "schema",
            "attempt_id",
            "batch_id",
            "scenario_set_id",
            "row_set_sha256",
            "repo_head",
            "source_root",
            "source_tree_status",
            "provider_set",
            "runtime_capabilities",
            "auth_profile",
            "budget_id",
            "provider_attempt_count",
            "budget_consumption",
            "prompt_budget",
            "rows",
            "findings",
            "product_findings",
            "harness_readiness_findings",
            "provider_environment_findings",
            "retention_manifest",
            "aggregates",
            "unsupported_or_deferred_rows",
            "decision",
            "next_allowed_action",
        ],
        "properties": {
            "schema": {"const": PROVIDER_ATTEMPT_REPORT_SCHEMA},
            "attempt_id": {"type": "string"},
            "batch_id": {"type": "string"},
            "scenario_set_id": {"type": "string"},
            "row_set_sha256": {"type": "string"},
            "repo_head": {"type": "string"},
            "source_root": {"type": "string", "redaction": "category_or_isolated_root_only"},
            "source_tree_status": {"type": "string"},
            "provider_set": {"type": "array", "items": {"type": "string"}},
            "runtime_capabilities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "runtime",
                        "display_name",
                        "command_prefix",
                        "launch_command",
                        "live_runner_status",
                        "headless_command_shape_id",
                        "prompt_transport_class",
                        "auth_probe_class",
                        "event_stream_class",
                    ],
                },
            },
            "auth_profile": {
                "type": "object",
                "metadata_only": True,
                "secret_material_allowed": False,
                "account_identifier_allowed": False,
            },
            "budget_id": {"type": "string"},
            "provider_attempt_count": {"type": "integer", "minimum": 0},
            "budget_consumption": {
                "type": "object",
                "required": ["attempted_subprocesses", "timeouts", "mutating_rows"],
            },
            "prompt_budget": {
                "type": "object",
                "required": [
                    "budget_id",
                    "max_prompt_tokens",
                    "total_tokens_estimate",
                    "observed_total_tokens",
                    "status_counts",
                    "over_budget_rows",
                ],
            },
            "rows": {
                "type": "array",
                "manual_or_nightly_only": True,
                "items": {
                    "type": "object",
                    "required": [
                        "row_id",
                        "scenario_id",
                        "scenario_template_id",
                        "provider_runtime",
                        "provider_adapter",
                        "persona_id",
                        "launch_policy",
                        "status",
                        "attempt_status",
                        "result_class",
                        "command_bucket",
                        "prompt_budget",
                        "sidecar_statuses",
                        "write_classification",
                        "write_status",
                        "finding_ids",
                        "retention_refs",
                    ],
                    "properties": {
                        "row_id": {"type": "string"},
                        "scenario_id": {"type": "string"},
                        "scenario_template_id": {"type": "string"},
                        "provider_runtime": {"type": "string"},
                        "provider_adapter": {"type": "string"},
                        "persona_id": {"type": "string"},
                        "launch_policy": {"enum": sorted(_PROVIDER_LAUNCH_POLICIES)},
                        "status": {"type": "string"},
                        "attempt_status": {"enum": sorted(_PROVIDER_ATTEMPT_STATUSES)},
                        "result_class": {"enum": ["green", "yellow", "red", "invalid_evidence"]},
                        "command_bucket": {"type": "string"},
                        "prompt_budget": {"type": "object"},
                        "sidecar_statuses": {"type": "object"},
                        "write_classification": {"type": "object"},
                        "write_status": {"type": "string"},
                        "finding_ids": {"type": "array", "items": {"type": "string"}},
                        "retention_refs": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["finding_id", "finding_class", "severity", "row_ids"],
                    "properties": {
                        "finding_class": {"enum": sorted(_PROVIDER_FINDING_CLASSES)},
                    },
                },
            },
            "product_findings": {"type": "array"},
            "harness_readiness_findings": {"type": "array"},
            "provider_environment_findings": {"type": "array"},
            "retention_manifest": {
                "type": "object",
                "required": ["classes", "artifacts"],
                "classes": sorted(_RETENTION_CLASS_DEFAULTS),
            },
            "aggregates": {
                "type": "object",
                "required": [
                    "runtime_counts",
                    "persona_counts",
                    "scenario_counts",
                    "finding_class_counts",
                ],
            },
            "unsupported_or_deferred_rows": {"type": "array", "items": {"type": "string"}},
            "decision": {"enum": sorted(_PROVIDER_DECISIONS)},
            "next_allowed_action": {"type": "string"},
        },
        "committed_evidence_policy": {
            "redacted_normalized_summaries_only": True,
            "provider_text_committed": False,
            "operator_local_evidence_requires_redaction": True,
        },
    }


def render_provider_attempt_report(
    rows: Sequence[object],
    *,
    attempt_id: str,
    batch_id: str,
    scenario_set_id: str,
    row_set_sha256: str,
    budget_id: str,
    repo_head: str = "unknown",
    source_root: str = "isolated_runtime_workspace",
    source_tree_status: str = "not_inspected",
    provider_set: Sequence[str] | None = None,
    runtime_capabilities: Sequence[object] | None = None,
    auth_profile: Mapping[str, object] | None = None,
    budget_consumption: Mapping[str, object] | None = None,
    prompt_budget: Mapping[str, object] | None = None,
    findings: Sequence[object] = (),
    retention_manifest: Mapping[str, object] | Sequence[object] | None = None,
    decision: str | None = None,
    next_allowed_action: str | None = None,
) -> dict[str, object]:
    """Render a sanitized Phase 8 provider-attempt report from class-only row records."""

    _raise_for_unsafe_provider_attempt_payload(rows, "rows")
    _raise_for_unsafe_provider_attempt_payload(findings, "findings")
    _raise_for_unsafe_provider_attempt_payload(runtime_capabilities or (), "runtime_capabilities")
    _raise_for_unsafe_provider_attempt_payload(auth_profile or {}, "auth_profile")
    _raise_for_unsafe_provider_attempt_payload(budget_consumption or {}, "budget_consumption")
    _raise_for_unsafe_provider_attempt_payload(prompt_budget or {}, "prompt_budget")
    _raise_for_unsafe_provider_attempt_payload(retention_manifest or {}, "retention_manifest")

    rendered_rows: list[dict[str, object]] = []
    row_finding_records: list[dict[str, object]] = []
    for index, row_source in enumerate(rows):
        row, row_findings = _render_provider_attempt_row(row_source, index)
        rendered_rows.append(row)
        row_finding_records.extend(row_findings)

    rendered_rows = sorted(rendered_rows, key=_row_order_key)
    normalized_provider_set = _normalize_provider_set(provider_set, rendered_rows)
    runtime_table = _runtime_capability_table(
        provider_set=normalized_provider_set,
        provided=runtime_capabilities or (),
    )
    rendered_findings = _render_provider_findings(findings, row_finding_records)
    retention = _normalize_retention_manifest(retention_manifest)
    prompt_budget_summary = _render_prompt_budget_summary(
        rendered_rows,
        budget_id=budget_id,
        prompt_budget=prompt_budget or {},
    )
    budget_summary = _render_budget_consumption(
        rendered_rows,
        prompt_budget_summary=prompt_budget_summary,
        budget_consumption=budget_consumption or {},
    )
    unsupported_or_deferred_rows = _unsupported_or_deferred_rows(rendered_rows, runtime_table)
    normalized_decision = _provider_decision(
        rendered_rows,
        rendered_findings,
        unsupported_or_deferred_rows,
        prompt_budget_summary,
        explicit_decision=decision,
    )

    report = {
        "schema": PROVIDER_ATTEMPT_REPORT_SCHEMA,
        "generated_at": _GENERATED_AT,
        "attempt_id": attempt_id,
        "batch_id": batch_id,
        "scenario_set_id": scenario_set_id,
        "row_set_sha256": row_set_sha256,
        "repo_head": repo_head,
        "source_root": source_root,
        "source_tree_status": source_tree_status,
        "provider_set": normalized_provider_set,
        "runtime_capabilities": runtime_table,
        "auth_profile": _normalize_auth_profile(auth_profile or {}, normalized_provider_set),
        "budget_id": budget_id,
        "provider_attempt_count": budget_summary["attempted_subprocesses"],
        "budget_consumption": budget_summary,
        "prompt_budget": prompt_budget_summary,
        "rows": rendered_rows,
        "findings": rendered_findings,
        "product_findings": _findings_by_class(rendered_findings, {"product_behavior"}),
        "harness_readiness_findings": _findings_by_class(
            rendered_findings,
            {"harness_contract", "reporting_contract"},
        ),
        "provider_environment_findings": _findings_by_class(
            rendered_findings,
            {"provider_environment", "auth_quota"},
        ),
        "retention_manifest": retention,
        "aggregates": _aggregate_provider_attempt_rows(rendered_rows, rendered_findings),
        "unsupported_or_deferred_rows": unsupported_or_deferred_rows,
        "decision": normalized_decision,
        "next_allowed_action": next_allowed_action or _next_allowed_action(normalized_decision),
    }
    validate_provider_attempt_report(report)
    return report


def validate_provider_attempt_report(report: Mapping[str, object]) -> dict[str, object]:
    """Validate a sanitized Phase 8 provider-attempt report or raise ``ValueError``."""

    errors = provider_attempt_report_validation_errors(report)
    if errors:
        raise ValueError("; ".join(errors))
    return dict(report)


def provider_attempt_report_validation_errors(report: Mapping[str, object]) -> list[str]:
    """Return validation errors for a sanitized Phase 8 provider-attempt report."""

    errors = _unsafe_provider_attempt_payload_errors(report, "report")
    if report.get("schema") != PROVIDER_ATTEMPT_REPORT_SCHEMA:
        errors.append(f"report.schema must be exactly {PROVIDER_ATTEMPT_REPORT_SCHEMA!r}")

    for key in provider_attempt_report_schema()["required"]:
        if key not in report:
            errors.append(f"report missing required key {key!r}")

    decision = _as_string(report.get("decision"), default="")
    if decision not in _PROVIDER_DECISIONS:
        errors.append(f"report.decision must be one of {sorted(_PROVIDER_DECISIONS)}")

    runtime_statuses: dict[str, str] = {}
    for index, capability in enumerate(_mapping_sequence(report.get("runtime_capabilities"))):
        context = f"report.runtime_capabilities[{index}]"
        runtime = _as_string(capability.get("runtime"), default="")
        status = _as_string(capability.get("live_runner_status"), default="")
        if not runtime:
            errors.append(f"{context}.runtime is required")
        if status not in _RUNTIME_LIVE_STATUSES:
            errors.append(f"{context}.live_runner_status must be one of {sorted(_RUNTIME_LIVE_STATUSES)}")
        runtime_statuses[runtime] = status
        for key in (
            "display_name",
            "command_prefix",
            "launch_command",
            "headless_command_shape_id",
            "prompt_transport_class",
            "auth_probe_class",
            "event_stream_class",
        ):
            if not _as_string(capability.get(key), default=""):
                errors.append(f"{context}.{key} is required")

    row_ids: set[str] = set()
    for index, row in enumerate(_mapping_sequence(report.get("rows"))):
        context = f"report.rows[{index}]"
        row_id = _as_string(row.get("row_id"), default="")
        if not row_id:
            errors.append(f"{context}.row_id is required")
        elif row_id in row_ids:
            errors.append(f"duplicate provider attempt row_id {row_id!r}")
        row_ids.add(row_id)

        launch_policy = _as_string(row.get("launch_policy"), default="")
        if launch_policy not in _PROVIDER_LAUNCH_POLICIES:
            errors.append(f"{context}.launch_policy must be one of {sorted(_PROVIDER_LAUNCH_POLICIES)}")
        attempt_status = _as_string(row.get("attempt_status"), default="")
        if attempt_status not in _PROVIDER_ATTEMPT_STATUSES:
            errors.append(f"{context}.attempt_status must be one of {sorted(_PROVIDER_ATTEMPT_STATUSES)}")
        if _as_string(row.get("result_class"), default="") not in {"green", "yellow", "red", "invalid_evidence"}:
            errors.append(f"{context}.result_class must be green, yellow, red, or invalid_evidence")
        if not isinstance(row.get("prompt_budget"), Mapping):
            errors.append(f"{context}.prompt_budget must be a mapping")
        if not _string_sequence(row.get("retention_refs")):
            errors.append(f"{context}.retention_refs must contain artifact ids")

        runtime = _as_string(row.get("provider_runtime"), default="")
        if runtime and runtime not in runtime_statuses:
            errors.append(f"{context}.provider_runtime {runtime!r} missing from runtime_capabilities")

    for index, finding in enumerate(_mapping_sequence(report.get("findings"))):
        context = f"report.findings[{index}]"
        finding_class = _as_string(finding.get("finding_class"), default="")
        if finding_class not in _PROVIDER_FINDING_CLASSES:
            errors.append(f"{context}.finding_class must be one of {sorted(_PROVIDER_FINDING_CLASSES)}")
        if not _as_string(finding.get("finding_id"), default=""):
            errors.append(f"{context}.finding_id is required")
        if not _string_sequence(finding.get("row_ids")):
            errors.append(f"{context}.row_ids must be non-empty")

    retention = report.get("retention_manifest")
    if isinstance(retention, Mapping):
        errors.extend(_retention_manifest_errors(retention, report.get("rows")))
    else:
        errors.append("report.retention_manifest must be a mapping")

    prompt_summary = report.get("prompt_budget")
    if isinstance(prompt_summary, Mapping):
        if "over_budget_rows" not in prompt_summary:
            errors.append("report.prompt_budget.over_budget_rows is required")
    else:
        errors.append("report.prompt_budget must be a mapping")

    return errors


def render_provider_attempt_markdown(report: Mapping[str, object]) -> str:
    """Render a deterministic markdown summary for a sanitized provider attempt report."""

    validate_provider_attempt_report(report)
    decision = str(report.get("decision", "pending")).upper()
    next_allowed_action = str(report.get("next_allowed_action", "complete_provider_attempt_report"))
    lines = [
        "# Phase 8 Provider Attempt Report",
        "",
        f"**Decision:** {decision}",
        f"**Next allowed action:** {next_allowed_action}",
        "",
        "## Gate Summary",
        "",
        _markdown_table(
            ("Field", "Value"),
            (
                ("Attempt", report.get("attempt_id", "unknown")),
                ("Batch", report.get("batch_id", "unknown")),
                ("Scenario set", report.get("scenario_set_id", "unknown")),
                ("Row set", report.get("row_set_sha256", "unknown")),
                ("Repo head", report.get("repo_head", "unknown")),
                ("Budget", report.get("budget_id", "unknown")),
            ),
        ),
        "",
        "## Runtime Capabilities",
        "",
        _markdown_table(
            (
                "Runtime",
                "Status",
                "Command",
                "Prompt transport",
                "Auth probe",
                "Events",
                "Deferred reason",
            ),
            (
                (
                    capability.get("runtime", "unknown"),
                    capability.get("live_runner_status", "unknown"),
                    capability.get("launch_command", "unknown"),
                    capability.get("prompt_transport_class", "unknown"),
                    capability.get("auth_probe_class", "unknown"),
                    capability.get("event_stream_class", "unknown"),
                    capability.get("deferred_reason", ""),
                )
                for capability in _mapping_sequence(report.get("runtime_capabilities"))
            ),
        ),
        "",
        "## Runtime Matrix",
        "",
        _markdown_table(
            ("Runtime", "Persona", "Scenario", "Rows", "Results", "Attempt status"),
            _runtime_matrix_rows(_mapping_sequence(report.get("rows"))),
        ),
        "",
        "## Critical Findings",
        "",
        _markdown_table(
            ("Finding", "Class", "Severity", "Rows", "Summary"),
            _critical_finding_rows(_mapping_sequence(report.get("findings"))),
        ),
        "",
        "## Prompt Budget",
        "",
        _markdown_table(
            ("Field", "Value"),
            (
                ("Max tokens", _mapping_from_report(report, "prompt_budget").get("max_prompt_tokens", 0)),
                (
                    "Estimated tokens",
                    _mapping_from_report(report, "prompt_budget").get("total_tokens_estimate", 0),
                ),
                (
                    "Observed tokens",
                    _mapping_from_report(report, "prompt_budget").get("observed_total_tokens", 0),
                ),
                (
                    "Over-budget rows",
                    ", ".join(_string_sequence(_mapping_from_report(report, "prompt_budget").get("over_budget_rows")))
                    or "none",
                ),
            ),
        ),
        "",
        "## Retention Manifest",
        "",
        _markdown_table(
            ("Class", "Safe to commit", "Local only", "Description"),
            _retention_class_markdown_rows(_mapping_from_report(report, "retention_manifest")),
        ),
        "",
        _markdown_table(
            ("Artifact", "Retention", "Material", "Safe to commit"),
            _retention_artifact_markdown_rows(_mapping_from_report(report, "retention_manifest")),
        ),
        "",
        "## Unsupported Or Deferred Rows",
        "",
        _markdown_table(
            ("Row", "Runtime", "Launch policy", "Attempt status"),
            _unsupported_markdown_rows(
                _mapping_sequence(report.get("rows")),
                _string_sequence(report.get("unsupported_or_deferred_rows")),
            ),
        ),
        "",
    ]
    return "\n".join(lines)


def _render_provider_attempt_row(source: object, index: int) -> tuple[dict[str, object], list[dict[str, object]]]:
    scenario_id = _as_string(_read(source, "scenario_id"), default="unknown")
    provider_runtime = _as_string(_read(source, "provider_runtime", "runtime", "provider"), default="unknown")
    provider_adapter = _as_string(_read(source, "provider_adapter", "adapter"), default=provider_runtime)
    launch_policy = _normalize_launch_policy(_read(source, "launch_policy", "mode"), source)
    row_id = _as_string(_read(source, "row_id", "scenario_run_id", "run_id"), default="")
    if not row_id:
        row_id = _fallback_row_id(
            index=index,
            scenario_id=scenario_id,
            provider_runtime=provider_runtime,
            fake_mode=launch_policy,
        )

    finding_records = _provider_attempt_finding_records(source, row_id=row_id)
    finding_ids = sorted(
        {
            *[str(record["finding_id"]) for record in finding_records],
            *_string_sequence(_read(source, "finding_ids", default=())),
        }
    )
    prompt_budget = _normalize_row_prompt_budget(_read(source, "prompt_budget", default={}), source)
    attempt_status = _normalize_attempt_status(_read(source, "attempt_status", "status"), launch_policy=launch_policy)

    result_class = _normalize_result_class(_read(source, "result_class", "result", "observed_result_class"))
    if result_class == "unknown":
        result_class = "yellow" if launch_policy in {"setup_refusal", "deferred"} else "invalid_evidence"

    row = {
        "row_id": row_id,
        "scenario_id": scenario_id,
        "scenario_template_id": _as_string(
            _read(source, "scenario_template_id", "template_id", "fixture_id"),
            default=scenario_id,
        ),
        "provider_runtime": provider_runtime,
        "provider_adapter": provider_adapter,
        "persona_id": _as_string(_read(source, "persona_id"), default="unknown"),
        "launch_policy": launch_policy,
        "status": _as_string(_read(source, "status", "terminal_status"), default=attempt_status),
        "attempt_status": attempt_status,
        "result_class": result_class,
        "command_surface": _as_string(_read(source, "command_surface", "command_slug"), default="unknown"),
        "command_bucket": _as_string(
            _read(source, "command_bucket", "command_surface", "command_slug"), default="unknown"
        ),
        "risk_tier": _as_string(_read(source, "risk_tier"), default="unknown"),
        "prompt_budget": prompt_budget,
        "sidecar_statuses": _status_mapping(_read(source, "sidecar_statuses"), default={}),
        "write_classification": _mapping_or_empty(_read(source, "write_classification")),
        "write_status": _as_string(_read(source, "write_status", "write_class"), default="not_written"),
        "provider_subprocess_attempts": _provider_subprocess_attempt_count(source, launch_policy, attempt_status),
        "finding_ids": finding_ids,
        "retention_refs": _retention_refs_from_row(source),
    }
    return row, finding_records


def _normalize_provider_set(provider_set: Sequence[str] | None, rows: Sequence[Mapping[str, object]]) -> list[str]:
    if provider_set is not None:
        return _string_sequence(provider_set)
    return _string_sequence([row.get("provider_runtime", "unknown") for row in rows])


def _runtime_capability_table(*, provider_set: Sequence[str], provided: Sequence[object]) -> list[dict[str, object]]:
    provided_by_runtime = {
        _as_string(_read(item, "runtime", "runtime_name", "provider_runtime"), default=""): item
        for item in provided
        if _as_string(_read(item, "runtime", "runtime_name", "provider_runtime"), default="")
    }
    rows: list[dict[str, object]] = []
    catalog_runtimes: set[str] = set()
    for descriptor in iter_runtime_descriptors():
        runtime = descriptor.runtime_name
        catalog_runtimes.add(runtime)
        row = {
            "runtime": runtime,
            "display_name": descriptor.display_name,
            "command_prefix": descriptor.command_prefix,
            "launch_command": descriptor.launch_command,
            "provider_requested": runtime in set(provider_set),
            "live_runner_status": "deferred" if runtime == "opencode" else "metadata_only",
            "headless_command_shape_id": f"{runtime}.catalog-launch-command",
            "prompt_transport_class": _prompt_transport_class(descriptor.command_prefix),
            "auth_probe_class": "class_only_status",
            "event_stream_class": descriptor.capabilities.telemetry_source
            if descriptor.capabilities.telemetry_source != "none"
            else "metadata_only",
            "timeout_seconds_default": 600,
            "prompt_budget_default": {
                "max_prompt_tokens": 0,
                "status": "not_reported",
            },
        }
        if runtime == "opencode":
            row["deferred_reason"] = "headless command/output/auth contract is not ready"
        if runtime in provided_by_runtime:
            row = _merge_runtime_capability(row, provided_by_runtime[runtime])
        rows.append(row)

    for runtime in sorted(set(provider_set) | set(provided_by_runtime) - catalog_runtimes):
        if runtime in catalog_runtimes:
            continue
        if runtime in provided_by_runtime:
            rows.append(
                _merge_runtime_capability(
                    _unsupported_runtime_capability(runtime, provider_requested=runtime in set(provider_set)),
                    provided_by_runtime[runtime],
                )
            )
        else:
            rows.append(_unsupported_runtime_capability(runtime, provider_requested=True))

    return sorted(rows, key=lambda row: str(row["runtime"]))


def _merge_runtime_capability(base: Mapping[str, object], provided: object) -> dict[str, object]:
    row = dict(base)
    if not isinstance(provided, Mapping):
        return row
    for key in (
        "display_name",
        "command_prefix",
        "launch_command",
        "live_runner_status",
        "headless_command_shape_id",
        "prompt_transport_class",
        "auth_probe_class",
        "event_stream_class",
        "deferred_reason",
    ):
        value = _as_string(provided.get(key), default="")
        if value:
            row[key] = value
    status = _as_string(row.get("live_runner_status"), default="unsupported")
    if status not in _RUNTIME_LIVE_STATUSES:
        row["live_runner_status"] = "unsupported"
    timeout = _as_non_negative_int(provided.get("timeout_seconds_default"), default=-1)
    if timeout >= 0:
        row["timeout_seconds_default"] = timeout
    prompt_budget_default = provided.get("prompt_budget_default")
    if isinstance(prompt_budget_default, Mapping):
        row["prompt_budget_default"] = _normalize_row_prompt_budget(prompt_budget_default, {})
    return row


def _unsupported_runtime_capability(runtime: str, *, provider_requested: bool) -> dict[str, object]:
    return {
        "runtime": runtime,
        "display_name": runtime,
        "command_prefix": "unsupported",
        "launch_command": "unsupported",
        "provider_requested": provider_requested,
        "live_runner_status": "unsupported",
        "headless_command_shape_id": "unsupported",
        "prompt_transport_class": "unsupported",
        "auth_probe_class": "unsupported",
        "event_stream_class": "unsupported",
        "timeout_seconds_default": 0,
        "prompt_budget_default": {"max_prompt_tokens": 0, "status": "not_reported"},
        "deferred_reason": "runtime is not present in the runtime catalog",
    }


def _normalize_auth_profile(payload: Mapping[str, object], provider_set: Sequence[str]) -> dict[str, object]:
    runtime_statuses = []
    raw_runtime_statuses = payload.get("runtime_statuses")
    if _is_sequence(raw_runtime_statuses):
        for item in raw_runtime_statuses:
            if not isinstance(item, Mapping):
                continue
            runtime = _as_string(_read(item, "runtime", "provider_runtime"), default="")
            if not runtime:
                continue
            runtime_statuses.append(
                {
                    "runtime": runtime,
                    "auth_status_class": _as_string(item.get("auth_status_class"), default="not_reported"),
                    "quota_status_class": _as_string(item.get("quota_status_class"), default="not_reported"),
                    "setup_status_class": _as_string(item.get("setup_status_class"), default="not_reported"),
                }
            )
    if not runtime_statuses:
        runtime_statuses = [
            {
                "runtime": runtime,
                "auth_status_class": "not_reported",
                "quota_status_class": "not_reported",
                "setup_status_class": "not_reported",
            }
            for runtime in provider_set
        ]

    return {
        "profile_id": _as_string(payload.get("profile_id"), default="class-only"),
        "metadata_only": True,
        "secret_material_allowed": False,
        "account_identifier_allowed": False,
        "auth_status_class": _as_string(payload.get("auth_status_class"), default="not_reported"),
        "quota_status_class": _as_string(payload.get("quota_status_class"), default="not_reported"),
        "runtime_statuses": sorted(runtime_statuses, key=lambda item: str(item["runtime"])),
    }


def _render_provider_findings(
    top_level_findings: Sequence[object],
    row_finding_records: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    records = list(row_finding_records)
    for item in top_level_findings:
        records.extend(_provider_finding_records_from_item(item, default_row_id="unknown-row"))
    grouped: dict[str, dict[str, object]] = {}
    for record in records:
        finding_id = _as_string(record.get("finding_id"), default="")
        if not finding_id:
            continue
        grouped.setdefault(
            finding_id,
            {
                "finding_id": finding_id,
                "finding_classes": set(),
                "severity": "unknown",
                "title": "",
                "summary": "",
                "row_ids": set(),
            },
        )
        current = grouped[finding_id]
        classes = current["finding_classes"]
        row_ids = current["row_ids"]
        if isinstance(classes, set):
            classes.add(_normalize_finding_class(record.get("finding_class")))
        if isinstance(row_ids, set):
            row_ids.update(_string_sequence(record.get("row_ids")))
        current["severity"] = _more_severe(str(current["severity"]), _normalize_severity(record.get("severity")))
        if not current["title"]:
            current["title"] = _as_string(record.get("title"), default=finding_id)
        if not current["summary"]:
            current["summary"] = _as_string(record.get("summary"), default="")

    findings: list[dict[str, object]] = []
    for grouped_record in grouped.values():
        classes = grouped_record["finding_classes"]
        row_ids = grouped_record["row_ids"]
        class_list = sorted(str(finding_class) for finding_class in classes) if isinstance(classes, set) else []
        row_id_list = sorted(str(row_id) for row_id in row_ids) if isinstance(row_ids, set) else []
        findings.append(
            {
                "finding_id": grouped_record["finding_id"],
                "finding_class": _primary_finding_class(class_list),
                "finding_classes": class_list,
                "severity": grouped_record["severity"],
                "title": grouped_record["title"],
                "summary": grouped_record["summary"],
                "row_ids": row_id_list or ["unknown-row"],
            }
        )
    return sorted(findings, key=lambda finding: str(finding["finding_id"]))


def _provider_attempt_finding_records(source: object, *, row_id: str) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    raw_findings = _read(source, "findings", default=())
    if _is_sequence(raw_findings):
        for item in raw_findings:
            records.extend(_provider_finding_records_from_item(item, default_row_id=row_id))
    for finding_id in _string_sequence(_read(source, "finding_ids", default=())):
        if finding_id not in {str(record["finding_id"]) for record in records}:
            records.append(
                {
                    "finding_id": finding_id,
                    "finding_class": "reporting_contract",
                    "severity": "unknown",
                    "title": finding_id,
                    "summary": "",
                    "row_ids": [row_id],
                }
            )
    return records


def _provider_finding_records_from_item(item: object, *, default_row_id: str) -> list[dict[str, object]]:
    if isinstance(item, Mapping):
        finding_id = _as_string(_read(item, "finding_id", "id", "code"), default="")
        if not finding_id:
            return []
        row_ids = _string_sequence(_read(item, "row_ids", default=()))
        row_id = _as_string(_read(item, "row_id"), default="")
        if row_id:
            row_ids = sorted({*row_ids, row_id})
        if not row_ids:
            row_ids = [default_row_id]
        return [
            {
                "finding_id": finding_id,
                "finding_class": _normalize_finding_class(_read(item, "finding_class", "class", "category")),
                "severity": _normalize_severity(_read(item, "severity", "max_severity")),
                "title": _as_string(_read(item, "title", "label"), default=finding_id),
                "summary": _as_string(_read(item, "summary", "message"), default=""),
                "row_ids": row_ids,
            }
        ]
    finding_id = _as_string(item, default="")
    if not finding_id:
        return []
    return [
        {
            "finding_id": finding_id,
            "finding_class": "reporting_contract",
            "severity": "unknown",
            "title": finding_id,
            "summary": "",
            "row_ids": [default_row_id],
        }
    ]


def _normalize_retention_manifest(source: Mapping[str, object] | Sequence[object] | None) -> dict[str, object]:
    classes = {key: dict(value) for key, value in _RETENTION_CLASS_DEFAULTS.items()}
    artifact_source: object = ()
    if isinstance(source, Mapping):
        raw_classes = source.get("classes")
        if isinstance(raw_classes, Mapping):
            for key, value in raw_classes.items():
                class_id = _as_string(key, default="")
                if class_id not in classes or not isinstance(value, Mapping):
                    continue
                classes[class_id].update(
                    {
                        "safe_to_commit": _as_bool(
                            value.get("safe_to_commit"), default=classes[class_id]["safe_to_commit"]
                        ),
                        "local_only": _as_bool(value.get("local_only"), default=classes[class_id]["local_only"]),
                        "description": _as_string(
                            value.get("description"), default=str(classes[class_id]["description"])
                        ),
                    }
                )
        artifact_source = source.get("artifacts", ())
    elif _is_sequence(source):
        artifact_source = source

    artifacts = _normalize_retention_artifacts(artifact_source)
    if not artifacts:
        artifacts = _normalize_retention_artifacts(
            (
                {"artifact_id": "provider-attempt-json", "artifact_ref": "provider-attempt.json"},
                {"artifact_id": "semantic-score-json", "artifact_ref": "semantic-score.json"},
                {"artifact_id": "redaction-report-json", "artifact_ref": "redaction-report.json"},
            )
        )
    return {
        "classes": dict(sorted(classes.items())),
        "artifacts": sorted(artifacts, key=lambda artifact: str(artifact["artifact_id"])),
    }


def _normalize_retention_artifacts(source: object) -> list[dict[str, object]]:
    artifacts: list[dict[str, object]] = []
    if not _is_sequence(source):
        return artifacts
    for index, item in enumerate(source):
        if isinstance(item, Mapping):
            artifact_id = _as_string(_read(item, "artifact_id", "id"), default=f"artifact-{index:04d}")
            retention_class = _normalize_retention_class(item.get("retention_class"))
            safe_default = retention_class == "committed_redacted"
            local_default = retention_class != "committed_redacted"
            artifacts.append(
                {
                    "artifact_id": artifact_id,
                    "artifact_ref": _as_string(_read(item, "artifact_ref", "ref"), default=artifact_id),
                    "retention_class": retention_class,
                    "material_class": _as_string(item.get("material_class"), default="sanitized_report"),
                    "safe_to_commit": _as_bool(item.get("safe_to_commit"), default=safe_default),
                    "local_only": _as_bool(item.get("local_only"), default=local_default),
                }
            )
        else:
            artifact_id = _as_string(item, default="")
            if artifact_id:
                artifacts.append(
                    {
                        "artifact_id": artifact_id,
                        "artifact_ref": artifact_id,
                        "retention_class": "committed_redacted",
                        "material_class": "sanitized_report",
                        "safe_to_commit": True,
                        "local_only": False,
                    }
                )
    return artifacts


def _render_prompt_budget_summary(
    rows: Sequence[Mapping[str, object]],
    *,
    budget_id: str,
    prompt_budget: Mapping[str, object],
) -> dict[str, object]:
    row_budgets = [_mapping_or_empty(row.get("prompt_budget")) for row in rows]
    total_estimate = sum(_as_non_negative_int(row.get("total_tokens_estimate"), default=0) for row in row_budgets)
    observed_total = sum(_as_non_negative_int(row.get("observed_total_tokens"), default=0) for row in row_budgets)
    explicit_max = _as_non_negative_int(prompt_budget.get("max_prompt_tokens"), default=-1)
    max_tokens = (
        explicit_max
        if explicit_max >= 0
        else sum(_as_non_negative_int(row.get("max_prompt_tokens"), default=0) for row in row_budgets)
    )
    over_budget_rows = [
        str(row.get("row_id", "unknown"))
        for row in rows
        if _mapping_or_empty(row.get("prompt_budget")).get("status") == "over_budget"
    ]
    return {
        "budget_id": _as_string(prompt_budget.get("budget_id"), default=budget_id),
        "max_prompt_tokens": max_tokens,
        "total_tokens_estimate": total_estimate,
        "observed_total_tokens": observed_total,
        "remaining_prompt_tokens": max(max_tokens - total_estimate, 0) if max_tokens else 0,
        "status_counts": _counter_dict(str(row.get("status", "not_reported")) for row in row_budgets),
        "over_budget_rows": sorted(over_budget_rows),
    }


def _render_budget_consumption(
    rows: Sequence[Mapping[str, object]],
    *,
    prompt_budget_summary: Mapping[str, object],
    budget_consumption: Mapping[str, object],
) -> dict[str, object]:
    attempted_subprocesses = _as_non_negative_int(
        budget_consumption.get("attempted_subprocesses"),
        default=sum(_as_non_negative_int(row.get("provider_subprocess_attempts"), default=0) for row in rows),
    )
    return {
        "attempted_subprocesses": attempted_subprocesses,
        "timeouts": _as_non_negative_int(
            budget_consumption.get("timeouts"),
            default=sum(1 for row in rows if row.get("attempt_status") == "timeout"),
        ),
        "mutating_rows": _as_non_negative_int(
            budget_consumption.get("mutating_rows"),
            default=sum(1 for row in rows if row.get("write_status") == "mutating"),
        ),
        "max_attempts": _as_non_negative_int(budget_consumption.get("max_attempts"), default=attempted_subprocesses),
        "max_mutating_rows": _as_non_negative_int(
            budget_consumption.get("max_mutating_rows"),
            default=sum(1 for row in rows if row.get("write_status") == "mutating"),
        ),
        "prompt_tokens_estimated": _as_non_negative_int(prompt_budget_summary.get("total_tokens_estimate"), default=0),
        "prompt_tokens_observed": _as_non_negative_int(prompt_budget_summary.get("observed_total_tokens"), default=0),
        "rows_over_prompt_budget": len(_string_sequence(prompt_budget_summary.get("over_budget_rows"))),
    }


def _aggregate_provider_attempt_rows(
    rows: Sequence[Mapping[str, object]],
    findings: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    return {
        "row_count": len(rows),
        "runtime_counts": _counter_dict(str(row.get("provider_runtime", "unknown")) for row in rows),
        "persona_counts": _counter_dict(str(row.get("persona_id", "unknown")) for row in rows),
        "scenario_counts": _counter_dict(str(row.get("scenario_id", "unknown")) for row in rows),
        "command_bucket_counts": _counter_dict(str(row.get("command_bucket", "unknown")) for row in rows),
        "risk_tier_counts": _counter_dict(str(row.get("risk_tier", "unknown")) for row in rows),
        "result_class_counts": _counter_dict(str(row.get("result_class", "unknown")) for row in rows),
        "attempt_status_counts": _counter_dict(str(row.get("attempt_status", "unknown")) for row in rows),
        "write_status_counts": _counter_dict(str(row.get("write_status", "unknown")) for row in rows),
        "finding_class_counts": _counter_dict(str(finding.get("finding_class", "unknown")) for finding in findings),
        "row_finding_class_counts": _row_finding_class_counts(rows, findings),
        "runtime_persona_counts": _compound_counter(rows, "provider_runtime", "persona_id"),
        "runtime_scenario_counts": _compound_counter(rows, "provider_runtime", "scenario_id"),
    }


def _row_finding_class_counts(
    rows: Sequence[Mapping[str, object]],
    findings: Sequence[Mapping[str, object]],
) -> dict[str, int]:
    row_ids = {str(row.get("row_id", "")) for row in rows}
    values: list[str] = []
    for finding in findings:
        finding_class = str(finding.get("finding_class", "unknown"))
        for row_id in _string_sequence(finding.get("row_ids")):
            if row_id in row_ids:
                values.append(finding_class)
    return _counter_dict(values)


def _compound_counter(rows: Sequence[Mapping[str, object]], *keys: str) -> dict[str, int]:
    return _counter_dict(" / ".join(str(row.get(key, "unknown")) for key in keys) for row in rows)


def _unsupported_or_deferred_rows(
    rows: Sequence[Mapping[str, object]],
    runtime_capabilities: Sequence[Mapping[str, object]],
) -> list[str]:
    statuses = {
        str(capability.get("runtime", "")): str(capability.get("live_runner_status", "unsupported"))
        for capability in runtime_capabilities
    }
    unsupported_rows = []
    for row in rows:
        runtime = str(row.get("provider_runtime", ""))
        if (
            statuses.get(runtime) in {"metadata_only", "deferred", "unsupported"}
            or row.get("launch_policy") in {"setup_refusal", "deferred"}
            or row.get("attempt_status") in {"setup_refused", "deferred", "unsupported"}
        ):
            unsupported_rows.append(str(row.get("row_id", "")))
    return sorted(row_id for row_id in unsupported_rows if row_id)


def _provider_decision(
    rows: Sequence[Mapping[str, object]],
    findings: Sequence[Mapping[str, object]],
    unsupported_or_deferred_rows: Sequence[str],
    prompt_budget_summary: Mapping[str, object],
    *,
    explicit_decision: str | None,
) -> str:
    if explicit_decision:
        decision = _as_string(explicit_decision, default="pending")
        return decision if decision in _PROVIDER_DECISIONS else "pending"
    if not rows:
        return "pending"
    if unsupported_or_deferred_rows:
        return "blocked"
    if _string_sequence(prompt_budget_summary.get("over_budget_rows")):
        return "needs_repair"
    if any(row.get("result_class") in {"red", "invalid_evidence"} for row in rows):
        return "needs_repair"
    if any(finding.get("severity") in {"S0", "S1"} for finding in findings):
        return "needs_repair"
    if all(row.get("result_class") == "green" and row.get("attempt_status") == "completed" for row in rows):
        return "accept"
    return "pending"


def _next_allowed_action(decision: str) -> str:
    if decision == "accept":
        return "publish_sanitized_report"
    if decision == "needs_repair":
        return "repair_provider_attempt_findings"
    if decision == "blocked":
        return "resolve_provider_runtime_or_mark_deferred"
    return "complete_manual_or_nightly_attempt"


def _findings_by_class(findings: Sequence[Mapping[str, object]], classes: set[str]) -> list[dict[str, object]]:
    return [dict(finding) for finding in findings if str(finding.get("finding_class", "")) in classes]


def _retention_manifest_errors(retention: Mapping[str, object], rows: object) -> list[str]:
    errors: list[str] = []
    classes = retention.get("classes")
    artifacts = _mapping_sequence(retention.get("artifacts"))
    if not isinstance(classes, Mapping):
        errors.append("report.retention_manifest.classes must be a mapping")
        classes = {}
    for required_class in _RETENTION_CLASS_DEFAULTS:
        if required_class not in classes:
            errors.append(f"report.retention_manifest.classes missing {required_class!r}")

    artifact_ids: set[str] = set()
    for index, artifact in enumerate(artifacts):
        context = f"report.retention_manifest.artifacts[{index}]"
        artifact_id = _as_string(artifact.get("artifact_id"), default="")
        retention_class = _as_string(artifact.get("retention_class"), default="")
        material_class = _as_string(artifact.get("material_class"), default="")
        safe_to_commit = _as_bool(artifact.get("safe_to_commit"), default=False)
        local_only = _as_bool(artifact.get("local_only"), default=False)
        if not artifact_id:
            errors.append(f"{context}.artifact_id is required")
        artifact_ids.add(artifact_id)
        if not retention_class:
            errors.append(f"{context}.retention_class is required")
        elif retention_class not in classes:
            errors.append(f"{context}.retention_class {retention_class!r} is not declared")
        if retention_class != "committed_redacted" and safe_to_commit:
            errors.append(f"{context} uses unsafe retention class {retention_class!r} with safe_to_commit=true")
        if retention_class in {"operator_local_raw", "discard_after_summary"} and not local_only:
            errors.append(f"{context} uses {retention_class!r} but local_only=false")
        if retention_class == "never_record" and (safe_to_commit or not local_only):
            errors.append(f"{context} uses never_record but is not marked local-only and unsafe to commit")
        if "raw" in material_class.casefold() and safe_to_commit:
            errors.append(f"{context} marks raw provider material as safe to commit")

    for row_index, row in enumerate(_mapping_sequence(rows)):
        for ref in _string_sequence(row.get("retention_refs")):
            if ref not in artifact_ids:
                errors.append(f"report.rows[{row_index}].retention_refs contains unknown artifact id {ref!r}")
    return errors


def _raise_for_unsafe_provider_attempt_payload(value: object, context: str) -> None:
    errors = _unsafe_provider_attempt_payload_errors(value, context)
    if errors:
        raise ValueError("; ".join(errors))


def _unsafe_provider_attempt_payload_errors(value: object, context: str) -> list[str]:
    errors: list[str] = []
    _collect_unsafe_provider_attempt_payload_errors(value, context, (), errors)
    return errors


def _collect_unsafe_provider_attempt_payload_errors(
    value: object,
    context: str,
    path: tuple[str, ...],
    errors: list[str],
) -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = _as_string(raw_key, default="")
            key_marker = key.casefold()
            child_context = f"{context}.{key}" if key else context
            if key_marker in _FORBIDDEN_PROVIDER_REPORT_KEYS:
                errors.append(f"{child_context} is a forbidden raw provider/auth field")
            _collect_unsafe_provider_attempt_payload_errors(child, child_context, (*path, key_marker), errors)
        return
    if _is_sequence(value):
        for index, child in enumerate(value):
            _collect_unsafe_provider_attempt_payload_errors(child, f"{context}[{index}]", (*path, str(index)), errors)
        return
    if not isinstance(value, str):
        return
    if _TOKEN_VALUE_RE.search(value):
        errors.append(f"{context} contains token-looking material")
    if _PRIVATE_KEY_RE.search(value):
        errors.append(f"{context} contains private-key material")
    if _REAL_HOME_PATH_RE.search(value):
        errors.append(f"{context} contains a real home path")
    if _EMAIL_RE.search(value) and any(
        part in {"auth_profile", "auth", "provider", "account", "email"} for part in path
    ):
        errors.append(f"{context} contains an account identifier")


def _markdown_table(headers: Sequence[object], rows: object) -> str:
    rendered_rows = [tuple(row) for row in rows] if _is_sequence(rows) or not isinstance(rows, str) else []
    if not rendered_rows:
        rendered_rows = [tuple("none" if index == 0 else "" for index in range(len(headers)))]
    header = "| " + " | ".join(_markdown_cell(value) for value in headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_markdown_cell(value) for value in row) + " |" for row in rendered_rows]
    return "\n".join([header, separator, *body])


def _markdown_cell(value: object) -> str:
    return str(value).replace("\n", " ").replace("|", "\\|")


def _runtime_matrix_rows(rows: Sequence[Mapping[str, object]]) -> list[tuple[object, ...]]:
    grouped: dict[tuple[str, str, str], dict[str, object]] = {}
    for row in rows:
        key = (
            str(row.get("provider_runtime", "unknown")),
            str(row.get("persona_id", "unknown")),
            str(row.get("scenario_id", "unknown")),
        )
        grouped.setdefault(key, {"count": 0, "results": Counter(), "statuses": Counter()})
        grouped[key]["count"] = int(grouped[key]["count"]) + 1
        results = grouped[key]["results"]
        statuses = grouped[key]["statuses"]
        if isinstance(results, Counter):
            results[str(row.get("result_class", "unknown"))] += 1
        if isinstance(statuses, Counter):
            statuses[str(row.get("attempt_status", "unknown"))] += 1

    table_rows = []
    for (runtime, persona, scenario), payload in sorted(grouped.items()):
        results = payload["results"]
        statuses = payload["statuses"]
        table_rows.append(
            (
                runtime,
                persona,
                scenario,
                payload["count"],
                _counter_summary(results if isinstance(results, Counter) else Counter()),
                _counter_summary(statuses if isinstance(statuses, Counter) else Counter()),
            )
        )
    return table_rows


def _critical_finding_rows(findings: Sequence[Mapping[str, object]]) -> list[tuple[object, ...]]:
    critical = [finding for finding in findings if finding.get("severity") in {"S0", "S1"}]
    selected = critical or list(findings)[:5]
    return [
        (
            finding.get("finding_id", "unknown"),
            finding.get("finding_class", "unknown"),
            finding.get("severity", "unknown"),
            ", ".join(_string_sequence(finding.get("row_ids"))),
            finding.get("summary", ""),
        )
        for finding in selected
    ]


def _retention_class_markdown_rows(retention: Mapping[str, object]) -> list[tuple[object, ...]]:
    classes = retention.get("classes")
    if not isinstance(classes, Mapping):
        return []
    rows = []
    for class_id, payload in sorted(classes.items()):
        mapping = _mapping_or_empty(payload)
        rows.append(
            (
                class_id,
                mapping.get("safe_to_commit", False),
                mapping.get("local_only", True),
                mapping.get("description", ""),
            )
        )
    return rows


def _retention_artifact_markdown_rows(retention: Mapping[str, object]) -> list[tuple[object, ...]]:
    return [
        (
            artifact.get("artifact_id", "unknown"),
            artifact.get("retention_class", "unknown"),
            artifact.get("material_class", "unknown"),
            artifact.get("safe_to_commit", False),
        )
        for artifact in _mapping_sequence(retention.get("artifacts"))
    ]


def _unsupported_markdown_rows(
    rows: Sequence[Mapping[str, object]],
    unsupported_row_ids: Sequence[str],
) -> list[tuple[object, ...]]:
    unsupported = set(unsupported_row_ids)
    return [
        (
            row.get("row_id", "unknown"),
            row.get("provider_runtime", "unknown"),
            row.get("launch_policy", "unknown"),
            row.get("attempt_status", "unknown"),
        )
        for row in rows
        if str(row.get("row_id", "")) in unsupported
    ]


def _normalize_launch_policy(value: object, source: object) -> str:
    launch_policy = _as_string(value, default="").casefold()
    aliases = {
        "manual": "manual_live",
        "manual-live": "manual_live",
        "manual_live": "manual_live",
        "nightly": "nightly_live",
        "nightly-live": "nightly_live",
        "nightly_live": "nightly_live",
        "setup-refusal": "setup_refusal",
        "setup_refusal": "setup_refusal",
        "setup_refused": "setup_refusal",
        "deferred": "deferred",
    }
    if launch_policy in aliases:
        return aliases[launch_policy]
    status = _as_string(_read(source, "attempt_status", "status"), default="").casefold()
    if status in {"setup_refused", "setup_refusal"}:
        return "setup_refusal"
    if status == "deferred":
        return "deferred"
    return "manual_live"


def _normalize_attempt_status(value: object, *, launch_policy: str) -> str:
    status = _as_string(value, default="").casefold()
    aliases = {
        "not_started": "not_started",
        "pending": "not_started",
        "attempted": "attempted",
        "running": "attempted",
        "completed": "completed",
        "complete": "completed",
        "success": "completed",
        "succeeded": "completed",
        "failed": "failed",
        "fail": "failed",
        "timeout": "timeout",
        "timed_out": "timeout",
        "setup_refusal": "setup_refused",
        "setup_refused": "setup_refused",
        "deferred": "deferred",
        "unsupported": "unsupported",
    }
    if status in aliases:
        return aliases[status]
    if launch_policy == "setup_refusal":
        return "setup_refused"
    if launch_policy == "deferred":
        return "deferred"
    return "not_started"


def _normalize_row_prompt_budget(value: object, source: object) -> dict[str, object]:
    payload = _mapping_or_empty(value)
    max_prompt_tokens = _as_non_negative_int(
        _first_mapping_value(payload, "max_prompt_tokens", "max_tokens", "limit"),
        default=_as_non_negative_int(_read(source, "max_prompt_tokens"), default=0),
    )
    prompt_tokens_estimate = _as_non_negative_int(
        _first_mapping_value(payload, "prompt_tokens_estimate", "input_tokens_estimate"),
        default=_as_non_negative_int(_read(source, "prompt_tokens_estimate"), default=0),
    )
    completion_tokens_estimate = _as_non_negative_int(
        _first_mapping_value(payload, "completion_tokens_estimate", "output_tokens_estimate"),
        default=_as_non_negative_int(_read(source, "completion_tokens_estimate"), default=0),
    )
    total_tokens_estimate = _as_non_negative_int(
        _first_mapping_value(payload, "total_tokens_estimate", "estimated_total_tokens"),
        default=prompt_tokens_estimate + completion_tokens_estimate,
    )
    observed_prompt_tokens = _as_non_negative_int(
        _first_mapping_value(payload, "observed_prompt_tokens", "input_tokens_observed"),
        default=0,
    )
    observed_completion_tokens = _as_non_negative_int(
        _first_mapping_value(payload, "observed_completion_tokens", "output_tokens_observed"),
        default=0,
    )
    observed_total_tokens = _as_non_negative_int(
        _first_mapping_value(payload, "observed_total_tokens", "total_tokens_observed"),
        default=observed_prompt_tokens + observed_completion_tokens,
    )
    status = _as_string(payload.get("status"), default="")
    if not status:
        if max_prompt_tokens == 0 and total_tokens_estimate == 0 and observed_total_tokens == 0:
            status = "not_reported"
        elif max_prompt_tokens and total_tokens_estimate > max_prompt_tokens:
            status = "over_budget"
        else:
            status = "within_budget"
    overflow_tokens = max(total_tokens_estimate - max_prompt_tokens, 0) if max_prompt_tokens else 0
    return {
        "budget_id": _as_string(payload.get("budget_id"), default="row_prompt_budget"),
        "max_prompt_tokens": max_prompt_tokens,
        "prompt_tokens_estimate": prompt_tokens_estimate,
        "completion_tokens_estimate": completion_tokens_estimate,
        "total_tokens_estimate": total_tokens_estimate,
        "observed_prompt_tokens": observed_prompt_tokens,
        "observed_completion_tokens": observed_completion_tokens,
        "observed_total_tokens": observed_total_tokens,
        "status": status,
        "overflow_tokens": overflow_tokens,
    }


def _provider_subprocess_attempt_count(source: object, launch_policy: str, attempt_status: str) -> int:
    explicit = _as_non_negative_int(_read(source, "provider_subprocess_attempts"), default=-1)
    if explicit >= 0:
        return explicit
    if launch_policy in {"manual_live", "nightly_live"} and attempt_status in {
        "attempted",
        "completed",
        "failed",
        "timeout",
        "setup_refused",
    }:
        return 1
    return 0


def _retention_refs_from_row(source: object) -> list[str]:
    refs = _string_sequence(_read(source, "retention_refs", "retention_artifact_ids", default=()))
    return refs or ["provider-attempt-json"]


def _mapping_or_empty(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _mapping_sequence(value: object) -> list[dict[str, object]]:
    if not _is_sequence(value):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _first_mapping_value(mapping: Mapping[str, object], *keys: str) -> object:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _as_non_negative_int(value: object, *, default: int) -> int:
    candidate = _as_int(value, default=default)
    if candidate < 0:
        return default
    return candidate


def _normalize_finding_class(value: object) -> str:
    finding_class = _as_string(value, default="reporting_contract").casefold().replace("-", "_")
    aliases = {
        "artifact": "artifact_retention",
        "artifact_retention": "artifact_retention",
        "auth": "auth_quota",
        "auth_quota": "auth_quota",
        "environment": "provider_environment",
        "harness": "harness_contract",
        "harness_contract": "harness_contract",
        "product": "product_behavior",
        "product_behavior": "product_behavior",
        "prompt": "prompt_budget",
        "prompt_budget": "prompt_budget",
        "provider_environment": "provider_environment",
        "reporting": "reporting_contract",
        "reporting_contract": "reporting_contract",
        "retention": "artifact_retention",
    }
    return aliases.get(finding_class, "reporting_contract")


def _primary_finding_class(classes: Sequence[str]) -> str:
    priority = (
        "product_behavior",
        "harness_contract",
        "provider_environment",
        "auth_quota",
        "prompt_budget",
        "artifact_retention",
        "reporting_contract",
    )
    class_set = set(classes)
    for finding_class in priority:
        if finding_class in class_set:
            return finding_class
    return "reporting_contract"


def _normalize_retention_class(value: object) -> str:
    retention_class = _as_string(value, default="committed_redacted").casefold().replace("-", "_")
    if retention_class in _RETENTION_CLASS_DEFAULTS:
        return retention_class
    return "committed_redacted"


def _prompt_transport_class(command_prefix: str) -> str:
    if command_prefix.startswith("$"):
        return "dollar_command"
    if command_prefix.startswith("/"):
        return "slash_command"
    return "unknown"


def _counter_summary(counter: Counter[str]) -> str:
    if not counter:
        return "none"
    return ", ".join(f"{key}:{counter[key]}" for key in sorted(counter))


def _render_row(source: object, index: int) -> tuple[dict[str, object], list[dict[str, str]]]:
    scenario_id = _as_string(_read(source, "scenario_id"), default="unknown")
    provider_runtime = _as_string(_read(source, "provider_runtime", "runtime", "provider"), default="unknown")
    provider_adapter = _as_string(_read(source, "provider_adapter", "adapter"), default=provider_runtime)
    fake_mode = _as_string(_read(source, "fake_mode", "mode"), default="deterministic_fake")
    row_id = _as_string(_read(source, "row_id", "scenario_run_id", "run_id"), default="")
    if not row_id:
        row_id = _fallback_row_id(
            index=index, scenario_id=scenario_id, provider_runtime=provider_runtime, fake_mode=fake_mode
        )
    result_class = _normalize_result_class(_read(source, "result_class", "result", "observed_result_class"))
    finding_records = _finding_records(source, row_id=row_id)
    finding_ids = sorted({record["finding_id"] for record in finding_records})

    row = {
        "row_id": row_id,
        "scenario_id": scenario_id,
        "run_key": _as_string(_read(source, "run_key"), default=scenario_id.replace("-", "_")),
        "persona_id": _as_string(_read(source, "persona_id"), default="unknown"),
        "fixture_id": _as_string(_read(source, "fixture_id"), default="unknown"),
        "provider_runtime": provider_runtime,
        "provider_adapter": provider_adapter,
        "fake_mode": fake_mode,
        "command_surface": _as_string(_read(source, "command_surface", "command_slug"), default="unknown"),
        "command_bucket": _as_string(_read(source, "command_bucket", "command_surface"), default="unknown"),
        "risk_tier": _as_string(_read(source, "risk_tier"), default="unknown"),
        "read_only_expected": _as_bool(_read(source, "read_only_expected"), default=True),
        "allow_mutation": _as_bool(_read(source, "allow_mutation"), default=False),
        "status": _as_string(_read(source, "status", "terminal_status"), default="unknown"),
        "result_class": result_class,
        "sidecar_statuses": _status_mapping(_read(source, "sidecar_statuses"), default={}),
        "observed_write_count": _as_int(_read(source, "observed_write_count", "write_count"), default=0),
        "unexpected_write_count": _as_int(_read(source, "unexpected_write_count"), default=0),
        "provider_subprocess_attempts": _as_int(_read(source, "provider_subprocess_attempts"), default=0),
        "network_attempts": _as_int(_read(source, "network_attempts"), default=0),
        "finding_ids": finding_ids,
        "quarantined": _as_bool(_read(source, "quarantined", "quarantine"), default=False),
    }
    return row, finding_records


def _read(source: object, *keys: str, default: object = _MISSING) -> object:
    sources = [source]
    for nested_key in _NESTED_SOURCES:
        nested = _read_direct(source, nested_key, default=_MISSING)
        if nested is not _MISSING and nested is not None:
            sources.append(nested)

    for candidate in sources:
        for key in keys:
            value = _read_direct(candidate, key, default=_MISSING)
            if value is not _MISSING:
                return value
    if default is not _MISSING:
        return default
    return None


def _read_direct(source: object, key: str, *, default: object) -> object:
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _as_string(value: object, *, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip()
        return text if text else default
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return default


def _as_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _as_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _normalize_result_class(value: object) -> str:
    result = _as_string(value, default="unknown").casefold()
    if result in {"pass", "passed", "success", "succeeded", "green"}:
        return "green"
    if result in {"warn", "warning", "yellow"}:
        return "yellow"
    if result in {"fail", "failed", "failure", "error", "red"}:
        return "red"
    if result in {"invalid", "invalid_evidence", "malformed_evidence"}:
        return "invalid_evidence"
    if result in {"blocked", "pending", "setup_refused", "timeout"}:
        return result
    return "unknown"


def _status_mapping(value: object, *, default: dict[str, object]) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return dict(default)
    statuses: dict[str, object] = {}
    for key, status_value in value.items():
        key_text = _as_string(key, default="")
        if not key_text:
            continue
        if isinstance(status_value, (str, bool, int)):
            statuses[key_text] = _as_string(status_value, default="unknown")
        elif isinstance(status_value, Mapping):
            statuses[key_text] = _as_string(status_value.get("status"), default="unknown")
        else:
            statuses[key_text] = "unknown"
    return dict(sorted(statuses.items()))


def _finding_records(source: object, *, row_id: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    raw_findings = _read(source, "findings", default=())
    if _is_sequence(raw_findings):
        for raw_finding in raw_findings:
            if isinstance(raw_finding, Mapping):
                finding_id = _as_string(
                    _read(raw_finding, "finding_id", "id", "code", default=""),
                    default="",
                )
                if finding_id:
                    records.append(
                        {
                            "finding_id": finding_id,
                            "severity": _normalize_severity(_read(raw_finding, "severity", "max_severity")),
                            "category": _as_string(
                                _read(raw_finding, "category", "dimension", "kind", default="unknown"),
                                default="unknown",
                            ),
                            "row_id": row_id,
                        }
                    )
            else:
                finding_id = _as_string(raw_finding, default="")
                if finding_id:
                    records.append(
                        {
                            "finding_id": finding_id,
                            "severity": "unknown",
                            "category": "unknown",
                            "row_id": row_id,
                        }
                    )

    raw_finding_ids = _read(source, "finding_ids", default=())
    for finding_id in _string_sequence(raw_finding_ids):
        if finding_id not in {record["finding_id"] for record in records}:
            records.append(
                {
                    "finding_id": finding_id,
                    "severity": "unknown",
                    "category": "unknown",
                    "row_id": row_id,
                }
            )
    return records


def _normalize_severity(value: object) -> str:
    severity = _as_string(value, default="unknown").upper()
    if severity in _SEVERITY_RANK:
        return severity
    return "unknown"


def _string_sequence(value: object) -> list[str]:
    if not _is_sequence(value):
        return []
    return sorted({_as_string(item, default="") for item in value if _as_string(item, default="")})


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _aggregate_findings(records: Sequence[dict[str, str]]) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    for record in records:
        finding_id = record["finding_id"]
        grouped.setdefault(
            finding_id,
            {
                "finding_id": finding_id,
                "severity": "unknown",
                "categories": set(),
                "row_ids": set(),
            },
        )
        current = grouped[finding_id]
        current["severity"] = _more_severe(str(current["severity"]), record["severity"])
        categories = current["categories"]
        row_ids = current["row_ids"]
        if isinstance(categories, set):
            categories.add(record["category"])
        if isinstance(row_ids, set):
            row_ids.add(record["row_id"])

    findings: list[dict[str, object]] = []
    for finding_id, grouped_record in grouped.items():
        categories = grouped_record["categories"]
        row_ids = grouped_record["row_ids"]
        category_list = sorted(str(category) for category in categories) if isinstance(categories, set) else []
        row_id_list = sorted(str(row_id) for row_id in row_ids) if isinstance(row_ids, set) else []
        findings.append(
            {
                "finding_id": finding_id,
                "severity": grouped_record["severity"],
                "categories": category_list,
                "count": len(row_id_list),
                "row_ids": row_id_list,
            }
        )
    return sorted(findings, key=lambda finding: str(finding["finding_id"]))


def _more_severe(left: str, right: str) -> str:
    left_rank = _SEVERITY_RANK.get(left, _SEVERITY_RANK["unknown"])
    right_rank = _SEVERITY_RANK.get(right, _SEVERITY_RANK["unknown"])
    return right if right_rank < left_rank else left


def _aggregate_rows(rows: Sequence[dict[str, object]], findings: Sequence[dict[str, object]]) -> dict[str, object]:
    return {
        "row_count": len(rows),
        "status_counts": _counter_dict(str(row["status"]) for row in rows),
        "result_class_counts": _counter_dict(str(row["result_class"]) for row in rows),
        "provider_runtime_counts": _counter_dict(str(row["provider_runtime"]) for row in rows),
        "fake_mode_counts": _counter_dict(str(row["fake_mode"]) for row in rows),
        "read_only_expected_count": sum(1 for row in rows if row["read_only_expected"] is True),
        "mutation_allowed_count": sum(1 for row in rows if row["allow_mutation"] is True),
        "observed_write_count": sum(_as_int(row.get("observed_write_count"), default=0) for row in rows),
        "unexpected_write_count": sum(_as_int(row.get("unexpected_write_count"), default=0) for row in rows),
        "provider_subprocess_attempts": sum(
            _as_int(row.get("provider_subprocess_attempts"), default=0) for row in rows
        ),
        "network_attempts": sum(_as_int(row.get("network_attempts"), default=0) for row in rows),
        "unique_finding_count": len(findings),
        "unique_s0_s1_finding_count": sum(1 for finding in findings if finding.get("severity") in {"S0", "S1"}),
    }


def _counter_dict(values: object) -> dict[str, int]:
    if not _is_sequence(values):
        values = list(values) if values is not None else []
    return dict(sorted(Counter(str(value) for value in values).items()))


def _row_order_key(row: Mapping[str, object]) -> tuple[str, str, str, str]:
    return (
        str(row.get("row_id", "")),
        str(row.get("provider_runtime", "")),
        str(row.get("provider_adapter", "")),
        str(row.get("fake_mode", "")),
    )


def _stable_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return sha256(payload).hexdigest()


def _fallback_row_id(index: int, scenario_id: str, provider_runtime: str, fake_mode: str) -> str:
    parts = [part for part in (scenario_id, provider_runtime, fake_mode) if part and part != "unknown"]
    if parts:
        return "::".join(parts)
    return f"row-{index:04d}"


def _rows_from_report(report: Mapping[str, object]) -> list[dict[str, object]]:
    rows = report.get("rows")
    if not _is_sequence(rows):
        return []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _findings_from_report(report: Mapping[str, object]) -> list[dict[str, object]]:
    findings = report.get("findings")
    if not _is_sequence(findings):
        return []
    return [dict(finding) for finding in findings if isinstance(finding, Mapping)]


def _mapping_from_report(report: Mapping[str, object], key: str) -> dict[str, object]:
    value = report.get(key)
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _pass_rate(rows: Sequence[Mapping[str, object]]) -> float:
    if not rows:
        return 0.0
    green_count = sum(1 for row in rows if row.get("result_class") == "green")
    return round(green_count / len(rows), 6)


def _pass_rate_by(rows: Sequence[Mapping[str, object]], key: str) -> dict[str, float]:
    grouped: dict[str, list[Mapping[str, object]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get(key, "unknown")), []).append(row)
    return {group_key: _pass_rate(group_rows) for group_key, group_rows in sorted(grouped.items())}


def _is_red_or_invalid(row: Mapping[str, object]) -> bool:
    return row.get("result_class") in {"red", "invalid_evidence"}


def _all_rows_have(rows: Sequence[Mapping[str, object]], key: str) -> bool:
    return bool(rows) and all(_as_string(row.get(key), default="") not in {"", "unknown"} for row in rows)


def _identity_gate(rows: Sequence[Mapping[str, object]], key: str) -> str:
    if not rows:
        return "pending"
    values = [_as_string(row.get(key), default="") for row in rows]
    if any(value in {"", "unknown"} for value in values):
        return "pending"
    if key == "scenario_id":
        row_ids = [_as_string(row.get("row_id"), default="") for row in rows]
        if len(row_ids) != len(set(row_ids)):
            return "fail"
    return "pass"


def _classification_gate(red_or_invalid_rows: Sequence[str], non_green_rows: Sequence[str], row_count: int) -> str:
    if red_or_invalid_rows:
        return "fail"
    if row_count == 0 or non_green_rows:
        return "pending"
    return "pass"


def _gate(condition: bool) -> str:
    return "pass" if condition else "fail"


def _trend_decision(
    *,
    row_count: int,
    red_or_invalid_rows: Sequence[str],
    non_green_rows: Sequence[str],
    provider_subprocess_attempts: int,
    network_attempts: int,
    gates: Mapping[str, str],
) -> str:
    if red_or_invalid_rows or provider_subprocess_attempts > 0 or network_attempts > 0:
        return "fail"
    if row_count == 0 or non_green_rows or any(status != "pass" for status in gates.values()):
        return "pending"
    return "ready_for_manual_phase8"


def _decision_reasons(
    *,
    red_or_invalid_rows: Sequence[str],
    non_green_rows: Sequence[str],
    provider_subprocess_attempts: int,
    network_attempts: int,
    row_count: int,
) -> list[str]:
    reasons: list[str] = []
    if row_count == 0:
        reasons.append("no_rows")
    if red_or_invalid_rows:
        reasons.append("red_or_invalid_evidence_rows_present")
    elif non_green_rows:
        reasons.append("non_green_rows_pending")
    if provider_subprocess_attempts > 0:
        reasons.append("provider_subprocess_attempts_present")
    if network_attempts > 0:
        reasons.append("network_attempts_present")
    if not reasons:
        reasons.append("all_fake_gates_passed")
    return reasons
