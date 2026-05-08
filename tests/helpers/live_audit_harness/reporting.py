"""Deterministic Phase 7 live-audit report rendering helpers."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from hashlib import sha256

FAKE_MATRIX_REPORT_SCHEMA = "phase7.fake_matrix_report.v1"
TREND_DASHBOARD_SCHEMA = "phase7.trend_dashboard.v1"
PROVIDER_ATTEMPT_REPORT_SCHEMA = "phase8.provider_attempt_report.v1"

_GENERATED_AT = "1970-01-01T00:00:00Z"
_MISSING = object()
_NESTED_SOURCES = ("row", "run", "scenario", "score", "metadata", "contract")
_SEVERITY_RANK = {"S0": 0, "S1": 1, "S2": 2, "S3": 3, "unknown": 99}


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
            "unique_s0_s1_finding_count": sum(
                1 for finding in findings if finding.get("severity") in {"S0", "S1"}
            ),
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
            "auth_profile",
            "budget_id",
            "provider_attempt_count",
            "budget_consumption",
            "rows",
            "product_findings",
            "harness_readiness_findings",
            "provider_environment_findings",
            "decision",
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
            "rows": {
                "type": "array",
                "manual_or_nightly_only": True,
                "items": {
                    "type": "object",
                    "required": [
                        "row_id",
                        "scenario_id",
                        "provider_runtime",
                        "provider_adapter",
                        "launch_policy",
                        "status",
                        "result_class",
                        "sidecar_statuses",
                        "write_classification",
                        "finding_ids",
                    ],
                    "properties": {
                        "row_id": {"type": "string"},
                        "scenario_id": {"type": "string"},
                        "provider_runtime": {"type": "string"},
                        "provider_adapter": {"type": "string"},
                        "launch_policy": {"enum": ["manual", "nightly"]},
                        "status": {"type": "string"},
                        "result_class": {"enum": ["green", "yellow", "red", "invalid_evidence"]},
                        "sidecar_statuses": {"type": "object"},
                        "write_classification": {"type": "object"},
                        "finding_ids": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "product_findings": {"type": "array"},
            "harness_readiness_findings": {"type": "array"},
            "provider_environment_findings": {"type": "array"},
            "decision": {"enum": ["accept", "needs_repair", "blocked"]},
        },
        "committed_evidence_policy": {
            "redacted_normalized_summaries_only": True,
            "provider_text_committed": False,
            "operator_local_evidence_requires_redaction": True,
        },
    }


def _render_row(source: object, index: int) -> tuple[dict[str, object], list[dict[str, str]]]:
    scenario_id = _as_string(_read(source, "scenario_id"), default="unknown")
    provider_runtime = _as_string(_read(source, "provider_runtime", "runtime", "provider"), default="unknown")
    provider_adapter = _as_string(_read(source, "provider_adapter", "adapter"), default=provider_runtime)
    fake_mode = _as_string(_read(source, "fake_mode", "mode"), default="deterministic_fake")
    row_id = _as_string(_read(source, "row_id", "scenario_run_id", "run_id"), default="")
    if not row_id:
        row_id = _fallback_row_id(index=index, scenario_id=scenario_id, provider_runtime=provider_runtime, fake_mode=fake_mode)
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
