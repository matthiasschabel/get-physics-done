"""Provider-free Phase 11 live-comparison helpers."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Final, Literal, cast

from tests.helpers.live_audit_harness.live_capabilities import RuntimeLiveCapability, iter_live_capabilities
from tests.helpers.live_audit_harness.redaction import (
    validate_provider_report_redaction,
    validate_provider_report_safety,
)
from tests.helpers.live_audit_harness.reporting import (
    PROVIDER_ATTEMPT_REPORT_SCHEMA,
    validate_provider_attempt_report,
)

PHASE11_LIVE_COMPARISON_MATRIX_SCHEMA: Final[str] = "phase11.live-comparison-matrix.v1"
PHASE11_LIVE_COMPARISON_REPORT_SCHEMA: Final[str] = "phase11.live-comparison-report.v1"
PHASE11_LIVE_READINESS_ROW_SCHEMA: Final[str] = "phase11.live-readiness-row.v1"

PHASE11_REQUIRED_SOURCE_CLASSES: Final[frozenset[str]] = frozenset({"manual", "nightly"})
PHASE11_ALLOWED_SOURCE_CLASSES: Final[frozenset[str]] = frozenset({"manual", "nightly"})
PHASE11_REQUIRED_MATRIX_SOURCE_CLASSES: Final[frozenset[str]] = frozenset({"manual_live", "nightly_live"})
PHASE11_ALLOWED_MATRIX_SOURCE_CLASSES: Final[frozenset[str]] = frozenset(
    {"manual", "nightly", "manual_live", "nightly_live"}
)
PHASE11_REQUIRED_REPORT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "schema",
        "comparison_id",
        "repo_head",
        "source_reports",
        "source_collection_classes",
        "provider_subprocess_allowed_in_default_pytest",
        "network_allowed_in_default_pytest",
        "manual_or_nightly_only",
        "rows",
        "aggregates",
        "comparison_verdicts",
        "retention_manifest",
        "decision",
        "next_allowed_action",
    }
)

Phase11Decision = Literal["accept", "needs_repair", "blocked"]

_GENERATED_AT: Final[str] = "1970-01-01T00:00:00Z"
_RESULT_RANK: Final[Mapping[str, int]] = {
    "green": 0,
    "yellow": 1,
    "red": 2,
    "invalid_evidence": 3,
    "unknown": 9,
    "missing": 10,
}
_BEHAVIOR_ACCEPTANCE_RANK: Final[Mapping[str, int]] = {
    "accepted": 0,
    "pending": 1,
    "rejected": 2,
    "unknown": 9,
    "missing": 10,
}
_HARD_SEVERITIES: Final[frozenset[str]] = frozenset({"S0", "S1"})
_PRODUCT_OR_HARNESS_FINDING_CLASSES: Final[frozenset[str]] = frozenset(
    {"product_behavior", "harness_contract", "reporting_contract"}
)
_PROVIDER_ENVIRONMENT_FINDING_CLASSES: Final[frozenset[str]] = frozenset({"provider_environment", "auth_quota"})
_UNSUPPORTED_ATTEMPT_STATUSES: Final[frozenset[str]] = frozenset({"deferred", "setup_refused", "unsupported"})
_UNSAFE_PHASE11_FIELD_NAMES: Final[frozenset[str]] = frozenset(
    {
        "args",
        "argv",
        "auth",
        "authheader",
        "authpath",
        "authorization",
        "env",
        "environment",
        "envvalues",
        "exactargv",
        "fullargv",
        "fullenv",
        "homepath",
        "prompt",
        "prompthash",
        "prompttext",
        "provideroutput",
        "providerreply",
        "providerresponse",
        "providerstderr",
        "providerstdout",
        "rawauth",
        "rawdiff",
        "rawenv",
        "rawoutput",
        "rawpath",
        "rawprompt",
        "rawprompttext",
        "rawprovideroutput",
        "rawstderr",
        "rawstdout",
        "rawtranscript",
        "stderr",
        "stderrtext",
        "stdout",
        "stdouttext",
        "transcript",
        "transcripttext",
        "writtencontent",
    }
)
_UNSAFE_PHASE11_FIELD_MARKERS: Final[tuple[str, ...]] = (
    "argvdump",
    "authfile",
    "authheader",
    "authpath",
    "envdump",
    "environmentdump",
    "promptinargv",
    "provideroutput",
    "providerresponse",
    "providerstderr",
    "providerstdout",
    "rawauth",
    "rawprovider",
    "rawtranscript",
    "transcripttext",
)
_PATHY_VALUE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:^|[\s'\"=:(])(?:/Users/[^/\s'\";:]+|/home/[^/\s'\";:]+|/root(?:/|[\s'\";:]|$)|"
    r"[A-Za-z]:\\Users\\[^\\\s'\";:]+)"
)


@dataclass(frozen=True, slots=True)
class Phase11ComparisonMatrix:
    schema: str
    matrix_id: str
    source_collection_classes: tuple[str, ...]
    default_pytest_policy: Mapping[str, object]
    row_metrics: tuple[str, ...]
    rows: tuple[Mapping[str, object], ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "matrix_id": self.matrix_id,
            "source_collection_classes": list(self.source_collection_classes),
            "default_pytest_policy": dict(self.default_pytest_policy),
            "row_metrics": list(self.row_metrics),
            "rows": [dict(row) for row in self.rows],
        }


@dataclass(frozen=True, slots=True)
class Phase11SourceClass:
    source_class: str
    input_class: str
    retention_class: str


@dataclass(frozen=True, slots=True)
class Phase11DefaultPytestPolicy:
    launch_policy: str
    default_pytest: bool
    provider_subprocess_allowed: bool
    network_allowed: bool
    required_pytest_markers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Phase11RowContract:
    row_contract_id: str
    contract_style: str
    launch_policy: str
    default_pytest: bool
    provider_subprocess_allowed: bool
    network_allowed: bool
    required_pytest_markers: tuple[str, ...]
    required_source_classes: tuple[str, ...]
    required_comparison_classes: tuple[str, ...]
    forbidden_comparison_classes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Phase11LiveComparisonRow:
    row_id: str
    runtime: str
    scenario_id: str
    source_class: str
    row_contract_id: str
    launch_policy: str
    default_pytest: bool
    provider_subprocess_allowed: bool
    network_allowed: bool
    required_pytest_markers: tuple[str, ...]
    result_class: str
    comparison_classes: tuple[str, ...]
    finding_classes: tuple[str, ...]
    retention_ref_classes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Phase11LiveComparisonMatrix:
    schema: str
    matrix_id: str
    default_pytest_policy: Phase11DefaultPytestPolicy
    source_classes: tuple[Phase11SourceClass, ...]
    row_contracts: tuple[Phase11RowContract, ...]
    rows: tuple[Phase11LiveComparisonRow, ...]


def default_phase11_comparison_matrix_path(repo_root: Path) -> Path:
    """Return the tracked Phase 11 live-comparison matrix fixture path."""

    return repo_root / "tests" / "fixtures" / "live_audit" / "phase11" / "live_comparison_matrix.json"


def default_phase11_live_comparison_matrix_path(repo_root: Path) -> Path:
    """Alias for the Phase 11 live-comparison matrix fixture path."""

    return default_phase11_comparison_matrix_path(repo_root)


def load_phase11_comparison_matrix(path: Path) -> Phase11ComparisonMatrix:
    """Load and validate a compact provider-free Phase 11 comparison fixture."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    return validate_phase11_comparison_matrix(_required_mapping(payload, "phase11 comparison matrix payload"))


def load_phase11_live_comparison_matrix(path: Path) -> Phase11LiveComparisonMatrix:
    """Load and validate the class-only Phase 11 live-comparison fixture."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    return validate_phase11_live_comparison_matrix(_required_mapping(payload, "phase11 live comparison matrix payload"))


def validate_phase11_comparison_matrix(payload: Mapping[str, object]) -> Phase11ComparisonMatrix:
    """Validate the compact Phase 11 live-comparison fixture contract."""

    validate_phase11_payload_safety(payload, context="phase11_comparison_matrix")

    schema = _required_str(payload, "schema", "phase11_comparison_matrix")
    if schema != PHASE11_LIVE_COMPARISON_MATRIX_SCHEMA:
        raise ValueError(f"phase11_comparison_matrix.schema must be exactly {PHASE11_LIVE_COMPARISON_MATRIX_SCHEMA!r}")

    source_classes = _source_collection_classes_from_fixture(payload)
    source_class_set = set(source_classes)
    has_manual_nightly = PHASE11_REQUIRED_SOURCE_CLASSES.issubset(source_class_set)
    has_live_manual_nightly = PHASE11_REQUIRED_MATRIX_SOURCE_CLASSES.issubset(source_class_set)
    if not has_manual_nightly and not has_live_manual_nightly:
        raise ValueError("phase11_comparison_matrix missing manual/nightly source collection classes")
    unknown_sources = sorted(source_class_set.difference(PHASE11_ALLOWED_MATRIX_SOURCE_CLASSES))
    if unknown_sources:
        raise ValueError(f"phase11_comparison_matrix has unsupported source collection classes: {unknown_sources!r}")

    default_pytest_policy = _default_pytest_policy_from_fixture(payload)
    _validate_default_pytest_policy(default_pytest_policy, "phase11_comparison_matrix.default_pytest_policy")

    row_metrics = _row_metrics_from_fixture(payload)
    rows = _rows_from_fixture(payload)
    _validate_fixture_rows(rows)

    return Phase11ComparisonMatrix(
        schema=schema,
        matrix_id=_optional_str(payload, "matrix_id", "phase11_comparison_matrix")
        or "phase11-live-comparison-matrix-v1",
        source_collection_classes=source_classes,
        default_pytest_policy=default_pytest_policy,
        row_metrics=row_metrics,
        rows=rows,
    )


def validate_phase11_comparison_fixture(payload: Mapping[str, object]) -> Phase11ComparisonMatrix:
    """Backward-compatible alias for fixture validation."""

    return validate_phase11_comparison_matrix(payload)


def validate_phase11_live_comparison_matrix(payload: Mapping[str, object]) -> Phase11LiveComparisonMatrix:
    """Validate the Phase 11 class-only live-comparison matrix fixture."""

    validate_phase11_payload_safety(payload, context="phase11_live_comparison_matrix")
    schema = _required_str(payload, "schema", "phase11_live_comparison_matrix")
    if schema != PHASE11_LIVE_COMPARISON_MATRIX_SCHEMA:
        raise ValueError(
            f"phase11_live_comparison_matrix.schema must be exactly {PHASE11_LIVE_COMPARISON_MATRIX_SCHEMA!r}"
        )

    policy = _parse_live_matrix_policy(
        _required_mapping(payload.get("default_pytest_policy"), "phase11_live_comparison_matrix.default_pytest_policy")
    )
    source_classes = _parse_live_matrix_source_classes(payload.get("source_classes"))
    source_class_ids = frozenset(source.source_class for source in source_classes)
    missing_sources = sorted(PHASE11_REQUIRED_MATRIX_SOURCE_CLASSES.difference(source_class_ids))
    if missing_sources:
        raise ValueError(f"phase11 live comparison source classes missing {missing_sources!r}")

    row_contracts = _parse_live_matrix_row_contracts(payload.get("row_contracts"))
    contract_by_id = {contract.row_contract_id: contract for contract in row_contracts}
    rows = _parse_live_matrix_rows(
        payload.get("rows"), source_class_ids=source_class_ids, contract_by_id=contract_by_id
    )
    _validate_live_matrix_row_order(payload, rows)

    return Phase11LiveComparisonMatrix(
        schema=schema,
        matrix_id=_required_str(payload, "matrix_id", "phase11_live_comparison_matrix"),
        default_pytest_policy=policy,
        source_classes=source_classes,
        row_contracts=row_contracts,
        rows=rows,
    )


def build_phase11_live_readiness_rows(runtime_filter: Sequence[str] | None = None) -> tuple[dict[str, object], ...]:
    """Derive provider-free Phase 11 live-readiness rows from the capability registry."""

    return tuple(_readiness_row(capability) for capability in iter_live_capabilities(runtime_filter))


def derive_phase11_live_readiness_rows(runtime_filter: Sequence[str] | None = None) -> tuple[dict[str, object], ...]:
    """Alias for callers that name the helper after the derivation step."""

    return build_phase11_live_readiness_rows(runtime_filter)


def build_live_readiness_matrix(runtime_filter: Sequence[str] | None = None) -> dict[str, object]:
    """Render the Phase 11 readiness matrix without probing providers or auth."""

    rows = build_phase11_live_readiness_rows(runtime_filter)
    return {
        "schema": "phase11.live-readiness-matrix.v1",
        "generated_at": _GENERATED_AT,
        "provider_subprocess_allowed": False,
        "provider_launch_performed": False,
        "environment_checks_performed": False,
        "rows": list(rows),
        "aggregates": {
            "runtime_count": len(rows),
            "contract_status_counts": _counter_dict(row["contract_status"] for row in rows),
            "environment_status_counts": _counter_dict(row["environment_status"] for row in rows),
            "launch_eligibility_counts": _counter_dict(row["launch_eligibility"] for row in rows),
            "provider_launch_performed_count": sum(1 for row in rows if row["provider_launch_performed"] is True),
        },
    }


def validate_live_readiness_matrix(payload: Mapping[str, object]) -> dict[str, object]:
    """Validate provider-free Phase 11 live-readiness matrix semantics."""

    errors: list[str] = []
    try:
        validate_phase11_payload_safety(payload, context="phase11_live_readiness_matrix")
    except ValueError as exc:
        errors.append(str(exc))

    if payload.get("provider_launch_performed") is not False:
        errors.append("phase11_live_readiness_matrix.provider_launch_performed must be false")
    rows = _mapping_sequence(
        payload.get(
            "rows",
            payload.get(
                "runtime_readiness_rows", payload.get("runtime_readiness", payload.get("runtime_capabilities"))
            ),
        )
    )
    if not rows:
        errors.append("phase11_live_readiness_matrix.rows must be non-empty")
    for index, row in enumerate(rows):
        context = f"phase11_live_readiness_matrix.rows[{index}]"
        if row.get("catalog_runtime", row.get("catalog_present")) is not True:
            errors.append(f"{context}.catalog_runtime must be true")
        if row.get("environment_status") != "not_checked":
            errors.append(f"{context}.environment_status must be not_checked")
        if row.get("auth_status") != "not_checked":
            errors.append(f"{context}.auth_status must be not_checked")
        if row.get("quota_status") != "not_checked":
            errors.append(f"{context}.quota_status must be not_checked")
        if row.get("auth_probe_performed") is not False:
            errors.append(f"{context}.auth_probe_performed must be false")
        if row.get("quota_probe_performed") is not False:
            errors.append(f"{context}.quota_probe_performed must be false")
        if row.get("provider_launch_performed") is not False:
            errors.append(f"{context}.provider_launch_performed must be false")
        if _as_string(row.get("live_runner_status", row.get("live_readiness_status")), default="") not in {
            "ready",
            "metadata_only",
            "deferred",
        }:
            errors.append(f"{context}.live_runner_status must be ready, metadata_only, or deferred")

    if errors:
        raise ValueError("; ".join(errors))
    return dict(payload)


def phase11_comparison_row_key(row: Mapping[str, object]) -> str:
    """Return the deterministic non-raw row key used for Phase 11 comparison joins."""

    return "::".join(
        _row_key_part(row.get(key)) for key in ("provider_runtime", "persona_id", "scenario_id", "command_bucket")
    )


def render_phase11_live_comparison_report(
    manual_report: Mapping[str, object] | None = None,
    nightly_report: Mapping[str, object] | None = None,
    *,
    comparison_id: str = "phase11-live-comparison",
    repo_head: str = "unknown",
    source_reports: Sequence[Mapping[str, object]] | None = None,
    manual_artifact_ref: str = "manual-provider-attempt-report.json",
    nightly_artifact_ref: str = "nightly-provider-attempt-report.json",
    matrix: Mapping[str, object] | Phase11ComparisonMatrix | None = None,
) -> dict[str, object]:
    """Render ``phase11.live-comparison-report.v1`` from sanitized Phase 8 reports."""

    if matrix is not None:
        if isinstance(matrix, Phase11ComparisonMatrix):
            matrix_payload: Mapping[str, object] = matrix.to_payload()
        else:
            matrix_payload = matrix
        validate_phase11_comparison_matrix(matrix_payload)

    normalized_sources = _normalize_source_inputs(
        manual_report=manual_report,
        nightly_report=nightly_report,
        source_reports=source_reports,
        manual_artifact_ref=manual_artifact_ref,
        nightly_artifact_ref=nightly_artifact_ref,
    )

    source_metadata = [_source_metadata(source) for source in normalized_sources]
    source_collection_classes = tuple(sorted({str(source["collection_class"]) for source in source_metadata}))
    rows = _comparison_rows(normalized_sources)
    aggregates = _comparison_aggregates(rows, source_metadata)
    product_behavior_findings = _finding_records_from_rows(rows, "product_finding_ids", "product_behavior")
    provider_environment_findings = _finding_records_from_rows(
        rows,
        "provider_environment_finding_ids",
        "provider_environment",
    )
    aggregates.update(
        {
            "product_behavior_finding_count": len(product_behavior_findings),
            "provider_environment_finding_count": len(provider_environment_findings),
        }
    )
    verdicts = _comparison_verdicts(rows, source_metadata, aggregates)
    decision = _comparison_decision(verdicts)

    report: dict[str, object] = {
        "schema": PHASE11_LIVE_COMPARISON_REPORT_SCHEMA,
        "generated_at": _GENERATED_AT,
        "comparison_id": comparison_id,
        "repo_head": repo_head,
        "provider_free": True,
        "provider_subprocess_allowed_by_this_script": False,
        "source_reports": source_metadata,
        "source_collection_classes": list(source_collection_classes),
        "provider_subprocess_allowed_in_default_pytest": False,
        "network_allowed_in_default_pytest": False,
        "manual_or_nightly_only": True,
        "join_policy": {
            "join_key": "provider_runtime::persona_id::scenario_id::command_bucket",
            "case_sensitive": True,
            "duplicates_are_invalid": True,
            "order_is_not_semantic": True,
        },
        "live_readiness_rows": list(build_phase11_live_readiness_rows()),
        "rows": rows,
        "aggregates": aggregates,
        "comparison_verdicts": verdicts,
        "product_behavior_findings": product_behavior_findings,
        "provider_environment_findings": provider_environment_findings,
        "retention_manifest": _phase11_retention_manifest(),
        "decision": decision,
        "decision_reasons": _decision_reasons(verdicts),
        "next_allowed_action": _next_allowed_action(decision),
    }
    validate_phase11_live_comparison_report(report)
    return report


def render_phase11_comparison_report(
    manual_report: Mapping[str, object] | None = None,
    nightly_report: Mapping[str, object] | None = None,
    *,
    comparison_id: str = "phase11-live-comparison",
    repo_head: str = "unknown",
    source_reports: Sequence[Mapping[str, object]] | None = None,
    manual_artifact_ref: str = "manual-provider-attempt-report.json",
    nightly_artifact_ref: str = "nightly-provider-attempt-report.json",
    matrix: Mapping[str, object] | Phase11ComparisonMatrix | None = None,
) -> dict[str, object]:
    """Short alias for the live comparison report renderer."""

    return render_phase11_live_comparison_report(
        manual_report,
        nightly_report,
        comparison_id=comparison_id,
        repo_head=repo_head,
        source_reports=source_reports,
        manual_artifact_ref=manual_artifact_ref,
        nightly_artifact_ref=nightly_artifact_ref,
        matrix=matrix,
    )


def render_live_comparison_report(
    manual_report: Mapping[str, object] | None = None,
    nightly_report: Mapping[str, object] | None = None,
    *,
    comparison_id: str = "phase11-live-comparison",
    repo_head: str = "unknown",
    source_reports: Sequence[Mapping[str, object]] | None = None,
    manual_artifact_ref: str = "manual-provider-attempt-report.json",
    nightly_artifact_ref: str = "nightly-provider-attempt-report.json",
    matrix: Mapping[str, object] | Phase11ComparisonMatrix | None = None,
) -> dict[str, object]:
    """Compatibility alias for Phase 11 live-comparison rendering."""

    return render_phase11_live_comparison_report(
        manual_report,
        nightly_report,
        comparison_id=comparison_id,
        repo_head=repo_head,
        source_reports=source_reports,
        manual_artifact_ref=manual_artifact_ref,
        nightly_artifact_ref=nightly_artifact_ref,
        matrix=matrix,
    )


def validate_phase11_live_comparison_report(report: Mapping[str, object]) -> dict[str, object]:
    """Validate a sanitized Phase 11 live-comparison report."""

    errors = phase11_live_comparison_report_validation_errors(report)
    if errors:
        raise ValueError("; ".join(errors))
    return dict(report)


def validate_phase11_comparison_report(report: Mapping[str, object]) -> dict[str, object]:
    """Short alias for the live-comparison report validator."""

    return validate_phase11_live_comparison_report(report)


def validate_live_comparison_report(report: Mapping[str, object]) -> dict[str, object]:
    """Compatibility alias for the Phase 11 live-comparison validator."""

    return validate_phase11_live_comparison_report(report)


def phase11_live_comparison_report_validation_errors(report: Mapping[str, object]) -> list[str]:
    """Return deterministic validation errors for a Phase 11 comparison report."""

    errors: list[str] = []
    try:
        validate_phase11_payload_safety(report, context="phase11_live_comparison_report")
    except ValueError as exc:
        errors.append(str(exc))

    if report.get("schema") != PHASE11_LIVE_COMPARISON_REPORT_SCHEMA:
        errors.append(f"report.schema must be exactly {PHASE11_LIVE_COMPARISON_REPORT_SCHEMA!r}")

    for key in sorted(PHASE11_REQUIRED_REPORT_KEYS):
        if key not in report:
            errors.append(f"report missing required key {key!r}")

    if report.get("provider_subprocess_allowed_in_default_pytest") is not False:
        errors.append("report.provider_subprocess_allowed_in_default_pytest must be false")
    if report.get("network_allowed_in_default_pytest") is not False:
        errors.append("report.network_allowed_in_default_pytest must be false")
    if report.get("manual_or_nightly_only") is not True:
        errors.append("report.manual_or_nightly_only must be true")

    source_classes = _string_tuple(report.get("source_collection_classes"))
    decision = _as_string(report.get("decision"), default="")
    missing_sources = sorted(PHASE11_REQUIRED_SOURCE_CLASSES.difference(source_classes))
    if missing_sources and decision != "blocked":
        errors.append(f"report.source_collection_classes missing {missing_sources!r}")
    unknown_sources = sorted(set(source_classes).difference(PHASE11_ALLOWED_SOURCE_CLASSES))
    if unknown_sources:
        errors.append(f"report.source_collection_classes has unsupported values {unknown_sources!r}")

    source_report_classes = []
    for index, source in enumerate(_mapping_sequence(report.get("source_reports"))):
        context = f"report.source_reports[{index}]"
        collection_class = _as_string(source.get("collection_class"), default="")
        if collection_class not in PHASE11_ALLOWED_SOURCE_CLASSES:
            errors.append(f"{context}.collection_class must be manual or nightly")
        source_report_classes.append(collection_class)
        if source.get("report_schema") != PROVIDER_ATTEMPT_REPORT_SCHEMA:
            errors.append(f"{context}.report_schema must be {PROVIDER_ATTEMPT_REPORT_SCHEMA!r}")
        for key in (
            "attempt_id",
            "batch_id",
            "scenario_set_id",
            "row_set_sha256",
            "provider_attempt_count",
            "decision",
            "artifact_ref",
        ):
            if _as_string(source.get(key), default="") == "":
                errors.append(f"{context}.{key} is required")

    row_keys: set[str] = set()
    comparison_row_ids: set[str] = set()
    for index, row in enumerate(_mapping_sequence(report.get("rows"))):
        context = f"report.rows[{index}]"
        comparison_row_id = _as_string(row.get("comparison_row_id"), default="")
        row_key = _as_string(row.get("row_key"), default="")
        if not comparison_row_id:
            errors.append(f"{context}.comparison_row_id is required")
        elif comparison_row_id in comparison_row_ids:
            errors.append(f"duplicate comparison_row_id {comparison_row_id!r}")
        comparison_row_ids.add(comparison_row_id)
        if not row_key:
            errors.append(f"{context}.row_key is required")
        elif row_key in row_keys:
            errors.append(f"duplicate row_key {row_key!r}")
        row_keys.add(row_key)
        expected_key = phase11_comparison_row_key(row)
        if row_key and row_key != expected_key:
            errors.append(f"{context}.row_key must be derived from runtime/persona/scenario/command")
        if _as_string(row.get("delta_class"), default="") not in {
            "unchanged",
            "changed",
            "improved",
            "regressed",
            "manual_missing",
            "nightly_missing",
        }:
            errors.append(f"{context}.delta_class is invalid")
        if row.get("manual_result_class") in {"red", "invalid_evidence"} and row.get("manual_presence") == "present":
            pass
        if row.get("nightly_result_class") in {"red", "invalid_evidence"} and row.get("nightly_presence") == "present":
            pass
        if not _string_tuple(row.get("retention_refs")):
            errors.append(f"{context}.retention_refs must be non-empty")

    retention = report.get("retention_manifest")
    if isinstance(retention, Mapping):
        errors.extend(_phase11_retention_errors(retention))
    else:
        errors.append("report.retention_manifest must be a mapping")

    if decision not in {"accept", "needs_repair", "blocked"}:
        errors.append("report.decision must be accept, needs_repair, or blocked")

    return errors


def render_phase11_live_comparison_markdown(report: Mapping[str, object]) -> str:
    """Render deterministic Markdown for a sanitized Phase 11 comparison report."""

    validate_phase11_live_comparison_report(report)
    decision = _as_string(report.get("decision"), default="blocked").upper()
    lines = [
        "# Phase 11 Live Comparison Report",
        "",
        f"**Comparison:** {_as_string(report.get('comparison_id'), default='unknown')}",
        f"**Decision:** {decision}",
        f"**Next allowed action:** {_as_string(report.get('next_allowed_action'), default='complete_inputs')}",
        "",
        "## Source Reports",
        "",
        _markdown_table(
            ("Class", "Attempt", "Batch", "Rows", "Attempts", "Decision", "Artifact"),
            (
                (
                    source.get("collection_class", "unknown"),
                    source.get("attempt_id", "unknown"),
                    source.get("batch_id", "unknown"),
                    source.get("row_count", 0),
                    source.get("provider_attempt_count", 0),
                    source.get("decision", "unknown"),
                    source.get("artifact_ref", "unknown"),
                )
                for source in _mapping_sequence(report.get("source_reports"))
            ),
        ),
        "",
        "## Aggregate Deltas",
        "",
        _markdown_table(
            ("Metric", "Value"),
            ((key, _json_cell(value)) for key, value in sorted(_mapping_or_empty(report.get("aggregates")).items())),
        ),
        "",
        "## Comparison Verdicts",
        "",
        _markdown_table(
            ("Gate", "Status", "Reason"),
            (
                (
                    verdict.get("gate", "unknown"),
                    verdict.get("verdict", verdict.get("status", "unknown")),
                    verdict.get("reason", ""),
                )
                for verdict in _mapping_sequence(report.get("comparison_verdicts"))
            ),
        ),
        "",
        "## Provider Environment Findings",
        "",
        _markdown_table(
            ("Finding", "Rows"),
            (
                (
                    finding.get("finding_id", "unknown"),
                    ", ".join(_string_tuple(finding.get("row_keys"))),
                )
                for finding in _mapping_sequence(report.get("provider_environment_findings"))
            ),
        ),
        "",
        "## Product Behavior Findings",
        "",
        _markdown_table(
            ("Finding", "Rows"),
            (
                (
                    finding.get("finding_id", "unknown"),
                    ", ".join(_string_tuple(finding.get("row_keys"))),
                )
                for finding in _mapping_sequence(report.get("product_behavior_findings"))
            ),
        ),
        "",
        "## Rows",
        "",
        _markdown_table(
            (
                "Row key",
                "Runtime",
                "Persona",
                "Scenario",
                "Command",
                "Manual",
                "Nightly",
                "Delta",
                "Flags",
            ),
            (
                (
                    row.get("row_key", "unknown"),
                    row.get("provider_runtime", "unknown"),
                    row.get("persona_id", "unknown"),
                    row.get("scenario_id", "unknown"),
                    row.get("command_bucket", "unknown"),
                    row.get("manual_result_class", "missing"),
                    row.get("nightly_result_class", "missing"),
                    row.get("delta_class", "unknown"),
                    ", ".join(_string_tuple(row.get("regression_flags"))) or "none",
                )
                for row in _mapping_sequence(report.get("rows"))
            ),
        ),
        "",
        "## Retention Manifest",
        "",
        _markdown_table(
            ("Artifact", "Retention", "Material", "Safe to commit"),
            (
                (
                    artifact.get("artifact_ref", "unknown"),
                    artifact.get("retention_class", "unknown"),
                    artifact.get("material_class", "unknown"),
                    artifact.get("safe_to_commit", False),
                )
                for artifact in _mapping_sequence(_mapping_or_empty(report.get("retention_manifest")).get("artifacts"))
            ),
        ),
        "",
    ]
    return "\n".join(lines)


def render_phase11_comparison_markdown(report: Mapping[str, object]) -> str:
    """Short alias for the live-comparison Markdown renderer."""

    return render_phase11_live_comparison_markdown(report)


def render_live_comparison_markdown(report: Mapping[str, object]) -> str:
    """Compatibility alias for Phase 11 live-comparison Markdown."""

    return render_phase11_live_comparison_markdown(report)


def validate_phase11_payload_safety(value: object, *, context: str = "phase11_payload") -> None:
    """Reject raw provider/auth/prompt/env/path fields in Phase 11 committed payloads."""

    if isinstance(value, Mapping):
        validate_provider_report_redaction(value, context=context)
    issues: list[str] = []
    _collect_phase11_safety_issues(value, context, issues)
    if issues:
        raise ValueError("phase11 payload redaction validation failed: " + "; ".join(issues))


def _source_collection_classes_from_fixture(payload: Mapping[str, object]) -> tuple[str, ...]:
    for key in ("source_collection_classes", "source_classes", "collection_classes"):
        classes = _string_tuple(payload.get(key))
        if classes:
            return tuple(sorted(dict.fromkeys(classes)))

    sources = payload.get("sources")
    if sources is None and _mapping_sequence(payload.get("source_classes")):
        sources = payload.get("source_classes")
    classes: list[str] = []
    for source in _mapping_sequence(sources):
        collection_class = _as_string(
            source.get("collection_class", source.get("source_class", source.get("class"))),
            default="",
        )
        if collection_class:
            classes.append(collection_class)
    if classes:
        return tuple(sorted(dict.fromkeys(classes)))
    raise ValueError("phase11_comparison_matrix.source_collection_classes is required")


def _default_pytest_policy_from_fixture(payload: Mapping[str, object]) -> Mapping[str, object]:
    for key in (
        "default_pytest_policy",
        "default_pytest_provider_free_policy",
        "provider_free_policy",
    ):
        value = payload.get(key)
        if isinstance(value, Mapping):
            return cast(Mapping[str, object], value)
    raise ValueError("phase11_comparison_matrix.default_pytest_policy is required")


def _validate_default_pytest_policy(policy: Mapping[str, object], context: str) -> None:
    if policy.get("provider_subprocess_allowed") is not False:
        raise ValueError(f"{context}.provider_subprocess_allowed must be false")
    if policy.get("network_allowed") is not False:
        raise ValueError(f"{context}.network_allowed must be false")
    if policy.get("live_rows_in_default_pytest") is True:
        raise ValueError(f"{context}.live_rows_in_default_pytest must be false when present")
    if policy.get("default_pytest") is False:
        raise ValueError(f"{context}.default_pytest must be true when present")
    markers = _string_tuple(
        policy.get(
            "required_pytest_markers",
            policy.get("required_markers", ()),
        )
    )
    if markers:
        raise ValueError(f"{context}.required_pytest_markers must be empty")


def _row_metrics_from_fixture(payload: Mapping[str, object]) -> tuple[str, ...]:
    for key in ("row_metrics", "metrics_to_compare", "comparison_metrics"):
        metrics = _string_tuple(payload.get(key))
        if metrics:
            return metrics
    return (
        "result_class",
        "attempt_status",
        "finding_ids",
        "write_status",
        "prompt_budget",
    )


def _rows_from_fixture(payload: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    rows = _mapping_sequence(payload.get("rows"))
    if not rows:
        raise ValueError("phase11_comparison_matrix.rows must contain at least one row")
    return tuple(cast(Mapping[str, object], row) for row in rows)


def _validate_fixture_rows(rows: Sequence[Mapping[str, object]]) -> None:
    row_ids: set[str] = set()
    row_keys: set[str] = set()
    for index, row in enumerate(rows):
        context = f"phase11_comparison_matrix.rows[{index}]"
        row_id = _as_string(row.get("row_id"), default="")
        if not row_id:
            raise ValueError(f"{context}.row_id is required")
        if row_id in row_ids:
            raise ValueError(f"duplicate phase11 comparison row_id {row_id!r}")
        row_ids.add(row_id)
        row_key = _as_string(row.get("row_key"), default="")
        if row_key:
            if row_key in row_keys:
                raise ValueError(f"duplicate phase11 comparison row_key {row_key!r}")
            row_keys.add(row_key)

        if row.get("provider_subprocess_allowed") is True:
            raise ValueError(f"{context}.provider_subprocess_allowed must be false for provider-free comparison")
        if row.get("network_allowed") is True:
            raise ValueError(f"{context}.network_allowed must be false for provider-free comparison")
        if row.get("default_pytest") is False:
            raise ValueError(f"{context}.default_pytest must be true when present")
        if _string_tuple(row.get("required_pytest_markers")):
            raise ValueError(f"{context}.required_pytest_markers must be empty")


def _parse_live_matrix_policy(mapping: Mapping[str, object]) -> Phase11DefaultPytestPolicy:
    policy = Phase11DefaultPytestPolicy(
        launch_policy=_required_str(mapping, "launch_policy", "phase11_live_comparison_matrix.default_pytest_policy"),
        default_pytest=_required_bool(
            mapping, "default_pytest", "phase11_live_comparison_matrix.default_pytest_policy"
        ),
        provider_subprocess_allowed=_required_bool(
            mapping,
            "provider_subprocess_allowed",
            "phase11_live_comparison_matrix.default_pytest_policy",
        ),
        network_allowed=_required_bool(
            mapping, "network_allowed", "phase11_live_comparison_matrix.default_pytest_policy"
        ),
        required_pytest_markers=_string_tuple(mapping.get("required_pytest_markers")),
    )
    if policy.launch_policy != "fake":
        raise ValueError("phase11 default_pytest_policy.launch_policy must be fake")
    if policy.default_pytest is not True:
        raise ValueError("phase11 default_pytest_policy.default_pytest must be true")
    if policy.provider_subprocess_allowed is not False:
        raise ValueError("phase11 default_pytest_policy.provider_subprocess_allowed must be false")
    if policy.network_allowed is not False:
        raise ValueError("phase11 default_pytest_policy.network_allowed must be false")
    if policy.required_pytest_markers:
        raise ValueError("phase11 default_pytest_policy.required_pytest_markers must be empty")
    return policy


def _parse_live_matrix_source_classes(value: object) -> tuple[Phase11SourceClass, ...]:
    source_classes: list[Phase11SourceClass] = []
    seen: set[str] = set()
    for index, item in enumerate(_mapping_sequence(value)):
        context = f"phase11_live_comparison_matrix.source_classes[{index}]"
        source_class = _required_str(item, "source_class", context)
        if source_class in seen:
            raise ValueError(f"duplicate phase11 source_class {source_class!r}")
        seen.add(source_class)
        if source_class not in PHASE11_ALLOWED_MATRIX_SOURCE_CLASSES:
            raise ValueError(f"{context}.source_class is not a supported source class")
        source_classes.append(
            Phase11SourceClass(
                source_class=source_class,
                input_class=_required_str(item, "input_class", context),
                retention_class=_required_str(item, "retention_class", context),
            )
        )
    if not source_classes:
        raise ValueError("phase11_live_comparison_matrix.source_classes must be non-empty")
    return tuple(source_classes)


def _parse_live_matrix_row_contracts(value: object) -> tuple[Phase11RowContract, ...]:
    contracts: list[Phase11RowContract] = []
    seen: set[str] = set()
    for index, item in enumerate(_mapping_sequence(value)):
        context = f"phase11_live_comparison_matrix.row_contracts[{index}]"
        row_contract_id = _required_str(item, "row_contract_id", context)
        if row_contract_id in seen:
            raise ValueError(f"duplicate phase11 row_contract_id {row_contract_id!r}")
        seen.add(row_contract_id)
        contract = Phase11RowContract(
            row_contract_id=row_contract_id,
            contract_style=_required_str(item, "contract_style", context),
            launch_policy=_required_str(item, "launch_policy", context),
            default_pytest=_required_bool(item, "default_pytest", context),
            provider_subprocess_allowed=_required_bool(item, "provider_subprocess_allowed", context),
            network_allowed=_required_bool(item, "network_allowed", context),
            required_pytest_markers=_string_tuple(item.get("required_pytest_markers")),
            required_source_classes=_string_tuple(item.get("required_source_classes")),
            required_comparison_classes=_string_tuple(item.get("required_comparison_classes")),
            forbidden_comparison_classes=_string_tuple(item.get("forbidden_comparison_classes")),
        )
        if not PHASE11_REQUIRED_MATRIX_SOURCE_CLASSES.issubset(contract.required_source_classes):
            raise ValueError(
                f"{context}.required_source_classes must include manual_live and nightly_live source classes"
            )
        if contract.launch_policy != "fake":
            raise ValueError(f"{context}.launch_policy must be fake")
        if contract.default_pytest is not True:
            raise ValueError(f"{context}.default_pytest must be true")
        if contract.provider_subprocess_allowed is not False:
            raise ValueError(f"{context}.provider_subprocess_allowed must be false")
        if contract.network_allowed is not False:
            raise ValueError(f"{context}.network_allowed must be false")
        if contract.required_pytest_markers:
            raise ValueError(f"{context}.required_pytest_markers must be empty")
        contracts.append(contract)
    if not contracts:
        raise ValueError("phase11_live_comparison_matrix.row_contracts must be non-empty")
    return tuple(contracts)


def _parse_live_matrix_rows(
    value: object,
    *,
    source_class_ids: frozenset[str],
    contract_by_id: Mapping[str, Phase11RowContract],
) -> tuple[Phase11LiveComparisonRow, ...]:
    rows: list[Phase11LiveComparisonRow] = []
    seen: set[str] = set()
    runtime_ids = {str(row["runtime"]) for row in build_phase11_live_readiness_rows()}
    for index, item in enumerate(_mapping_sequence(value)):
        context = f"phase11_live_comparison_matrix.rows[{index}]"
        row_id = _required_str(item, "row_id", context)
        if row_id in seen:
            raise ValueError(f"duplicate phase11 row_id {row_id!r}")
        seen.add(row_id)
        runtime = _required_str(item, "runtime", context)
        if runtime not in runtime_ids:
            raise ValueError(f"{context}.runtime must be catalog-backed")
        source_class = _required_str(item, "source_class", context)
        if source_class not in source_class_ids:
            raise ValueError(f"{context}.source_class must reference a declared source class")
        row_contract_id = _required_str(item, "row_contract_id", context)
        contract = contract_by_id.get(row_contract_id)
        if contract is None:
            raise ValueError(f"{context}.row_contract_id must reference a declared contract")
        row = Phase11LiveComparisonRow(
            row_id=row_id,
            runtime=runtime,
            scenario_id=_required_str(item, "scenario_id", context),
            source_class=source_class,
            row_contract_id=row_contract_id,
            launch_policy=_required_str(item, "launch_policy", context),
            default_pytest=_required_bool(item, "default_pytest", context),
            provider_subprocess_allowed=_required_bool(item, "provider_subprocess_allowed", context),
            network_allowed=_required_bool(item, "network_allowed", context),
            required_pytest_markers=_string_tuple(item.get("required_pytest_markers")),
            result_class=_normalize_result_class(item.get("result_class")),
            comparison_classes=_string_tuple(item.get("comparison_classes")),
            finding_classes=_string_tuple(item.get("finding_classes")),
            retention_ref_classes=_string_tuple(item.get("retention_ref_classes")),
        )
        if row.source_class not in contract.required_source_classes:
            raise ValueError(f"{context}.source_class is not allowed by row contract source classes")
        if row.launch_policy != contract.launch_policy:
            raise ValueError(f"{context}.launch_policy must match row contract")
        if row.default_pytest != contract.default_pytest:
            raise ValueError(f"{context}.default_pytest must match row contract")
        if row.provider_subprocess_allowed != contract.provider_subprocess_allowed:
            raise ValueError(f"{context}.provider_subprocess_allowed must match row contract")
        if row.network_allowed != contract.network_allowed:
            raise ValueError(f"{context}.network_allowed must match row contract")
        if row.required_pytest_markers != contract.required_pytest_markers:
            raise ValueError(f"{context}.required_pytest_markers must match row contract")
        missing_classes = sorted(set(contract.required_comparison_classes).difference(row.comparison_classes))
        if missing_classes:
            raise ValueError(f"{context}.comparison_classes missing required classes {missing_classes!r}")
        forbidden_classes = sorted(set(contract.forbidden_comparison_classes).intersection(row.comparison_classes))
        if forbidden_classes:
            raise ValueError(f"{context}.comparison_classes contains forbidden classes {forbidden_classes!r}")
        rows.append(row)
    if not rows:
        raise ValueError("phase11_live_comparison_matrix.rows must be non-empty")
    return tuple(rows)


def _validate_live_matrix_row_order(payload: Mapping[str, object], rows: Sequence[Phase11LiveComparisonRow]) -> None:
    deterministic = payload.get("deterministic_validation")
    if not isinstance(deterministic, Mapping):
        return
    expected_order = tuple(_string_list_preserve_order(deterministic.get("row_order")))
    observed_order = tuple(row.row_id for row in rows)
    if expected_order and observed_order != expected_order:
        raise ValueError("phase11_live_comparison_matrix deterministic row_order does not match rows")


def _readiness_row(capability: RuntimeLiveCapability) -> dict[str, object]:
    payload = capability.to_json()
    live_runner_status = _as_string(payload.get("live_runner_status"), default="metadata_only")
    if live_runner_status == "ready":
        phase_scope = "live_contract_ready"
        launch_eligibility = "preflight_ready"
        refusal_reason_class = None
        required_for_live_provider_set = True
    elif live_runner_status == "deferred":
        phase_scope = "metadata_deferred"
        launch_eligibility = "refused"
        refusal_reason_class = "provider_not_live_ready"
        required_for_live_provider_set = False
    else:
        phase_scope = "metadata_only"
        launch_eligibility = "refused"
        refusal_reason_class = "provider_not_live_ready"
        required_for_live_provider_set = False

    return {
        "schema_version": PHASE11_LIVE_READINESS_ROW_SCHEMA,
        "runtime": payload["runtime_id"],
        "runtime_id": payload["runtime_id"],
        "display_name": payload["display_name"],
        "catalog_present": True,
        "catalog_runtime": True,
        "contract_status": live_runner_status,
        "live_runner_status": live_runner_status,
        "live_readiness_status": live_runner_status,
        "headless_command_shape_id": payload["headless_command_shape_id"],
        "prompt_transport_class": payload["prompt_transport_class"],
        "auth_probe_class": payload["auth_probe_class"],
        "event_stream_class": payload["event_stream_class"],
        "deferred_reason": payload.get("deferred_reason"),
        "phase11_projection_scope": phase_scope,
        "required_for_live_provider_set": required_for_live_provider_set,
        "environment_status": "not_checked",
        "environment_issue_class": None,
        "auth_status": "not_checked",
        "quota_status": "not_checked",
        "auth_probe_performed": False,
        "quota_probe_performed": False,
        "launch_eligibility": launch_eligibility,
        "refusal_reason_class": refusal_reason_class,
        "provider_launch_performed": False,
        "secret_material_recorded": False,
        "evidence": [
            "tests.helpers.live_audit_harness.live_capabilities.iter_live_capabilities",
        ],
    }


def _normalize_source_inputs(
    *,
    manual_report: Mapping[str, object] | None,
    nightly_report: Mapping[str, object] | None,
    source_reports: Sequence[Mapping[str, object]] | None,
    manual_artifact_ref: str,
    nightly_artifact_ref: str,
) -> tuple[dict[str, object], ...]:
    sources: list[dict[str, object]] = []
    if manual_report is not None:
        sources.append(
            _normalize_source_report(
                manual_report,
                collection_class="manual",
                artifact_ref=manual_artifact_ref,
            )
        )
    if nightly_report is not None:
        sources.append(
            _normalize_source_report(
                nightly_report,
                collection_class="nightly",
                artifact_ref=nightly_artifact_ref,
            )
        )
    for index, report in enumerate(source_reports or ()):
        report_payload = report.get("report") if isinstance(report.get("report"), Mapping) else report
        report_mapping = _required_mapping(report_payload, f"phase11 source_reports[{index}].report")
        collection_class = _as_string(report.get("collection_class"), default="")
        if not collection_class:
            collection_class = _collection_class_from_report(report_mapping)
        artifact_ref = _as_string(
            report.get("artifact_ref") if "artifact_ref" in report else report_mapping.get("artifact_ref"),
            default=f"{collection_class or 'source'}-provider-attempt-report-{index:02d}.json",
        )
        sources.append(
            _normalize_source_report(
                report_mapping,
                collection_class=collection_class,
                artifact_ref=artifact_ref,
            )
        )

    classes = Counter(str(source["collection_class"]) for source in sources)
    for source_class, count in classes.items():
        if count > 1:
            raise ValueError(f"at most one {source_class!r} source report is allowed")
    unexpected = sorted(set(classes).difference(PHASE11_ALLOWED_SOURCE_CLASSES))
    if unexpected:
        raise ValueError(f"unsupported source report collection classes: {unexpected!r}")
    return tuple(sorted(sources, key=lambda source: str(source["collection_class"])))


def _normalize_source_report(
    report: Mapping[str, object],
    *,
    collection_class: str,
    artifact_ref: str,
) -> dict[str, object]:
    collection_class = _normalize_collection_class(collection_class, report)
    if collection_class not in PHASE11_ALLOWED_SOURCE_CLASSES:
        raise ValueError(f"source report collection_class must be manual or nightly, got {collection_class!r}")
    _validate_phase8_provider_source(report, context=f"phase11_{collection_class}_source_report")

    rows = _source_rows(report, collection_class=collection_class)
    return {
        "collection_class": collection_class,
        "artifact_ref": artifact_ref,
        "report": dict(report),
        "rows": rows,
    }


def _collection_class_from_report(report: Mapping[str, object]) -> str:
    explicit = _as_string(
        report.get("collection_class", report.get("source_collection_class")),
        default="",
    )
    return _normalize_collection_class(explicit, report)


def _normalize_collection_class(value: str, report: Mapping[str, object]) -> str:
    normalized = value.strip().casefold().replace("-", "_")
    if normalized in {"manual", "manual_live"}:
        return "manual"
    if normalized in {"nightly", "nightly_live", "scheduled"}:
        return "nightly"

    launch_policies = {
        _as_string(row.get("launch_policy"), default="") for row in _mapping_sequence(report.get("rows"))
    }
    if launch_policies == {"manual_live"}:
        return "manual"
    if launch_policies == {"nightly_live"}:
        return "nightly"
    return normalized or "unknown"


def _validate_phase8_provider_source(report: Mapping[str, object], *, context: str) -> None:
    validate_provider_attempt_report(report)
    validate_phase11_payload_safety(report, context=context)
    validate_provider_report_safety(report, context=context)


def _source_metadata(source: Mapping[str, object]) -> dict[str, object]:
    report = _required_mapping(source.get("report"), "phase11 source report")
    rows = _mapping_sequence(source.get("rows"))
    return {
        "report_schema": report.get("schema", "unknown"),
        "collection_class": source["collection_class"],
        "attempt_id": report.get("attempt_id", "unknown"),
        "batch_id": report.get("batch_id", "unknown"),
        "scenario_set_id": report.get("scenario_set_id", "unknown"),
        "row_set_sha256": report.get("row_set_sha256", "unknown"),
        "repo_head": report.get("repo_head", "unknown"),
        "provider_set": _string_tuple(report.get("provider_set")),
        "provider_attempt_count": _as_int(report.get("provider_attempt_count"), default=0),
        "decision": report.get("decision", "unknown"),
        "row_count": len(rows),
        "artifact_ref": source["artifact_ref"],
    }


def _source_rows(report: Mapping[str, object], *, collection_class: str) -> list[dict[str, object]]:
    findings_by_row = _findings_by_row(report)
    rows: list[dict[str, object]] = []
    row_keys: set[str] = set()
    for index, row in enumerate(_mapping_sequence(report.get("rows"))):
        normalized_row = _source_row(row, findings_by_row=findings_by_row, collection_class=collection_class)
        row_key = str(normalized_row["row_key"])
        if row_key in row_keys:
            raise ValueError(f"duplicate Phase 11 source row key {row_key!r} in {collection_class} report")
        row_keys.add(row_key)
        normalized_row["source_index"] = index
        rows.append(normalized_row)
    return sorted(rows, key=lambda item: str(item["row_key"]))


def _source_row(
    row: Mapping[str, object],
    *,
    findings_by_row: Mapping[str, Sequence[Mapping[str, object]]],
    collection_class: str,
) -> dict[str, object]:
    row_id = _as_string(row.get("row_id"), default="")
    row_findings = [dict(finding) for finding in findings_by_row.get(row_id, ())]
    row_finding_ids = _string_tuple(row.get("finding_ids"))
    for finding_id in row_finding_ids:
        if finding_id not in {str(finding.get("finding_id", "")) for finding in row_findings}:
            row_findings.append(
                {
                    "finding_id": finding_id,
                    "finding_class": "reporting_contract",
                    "severity": "unknown",
                    "row_ids": [row_id],
                }
            )

    normalized = {
        "source_collection_class": collection_class,
        "row_id": row_id,
        "row_key": phase11_comparison_row_key(row),
        "provider_runtime": _as_string(row.get("provider_runtime"), default="unknown"),
        "persona_id": _as_string(row.get("persona_id"), default="unknown"),
        "scenario_id": _as_string(row.get("scenario_id"), default="unknown"),
        "scenario_template_id": _as_string(row.get("scenario_template_id"), default="unknown"),
        "command_bucket": _as_string(row.get("command_bucket"), default="unknown"),
        "launch_policy": _as_string(row.get("launch_policy"), default="unknown"),
        "attempt_status": _as_string(row.get("attempt_status"), default="unknown"),
        "result_class": _normalize_result_class(row.get("result_class")),
        "status": _as_string(row.get("status"), default="unknown"),
        "write_status": _as_string(row.get("write_status"), default="unknown"),
        "prompt_budget": _mapping_or_empty(row.get("prompt_budget")),
        "finding_ids": sorted(
            {str(finding.get("finding_id", "")) for finding in row_findings if finding.get("finding_id")}
        ),
        "finding_classes": sorted(
            {_as_string(finding.get("finding_class"), default="reporting_contract") for finding in row_findings}
        ),
        "max_finding_severity": _max_finding_severity(row_findings),
        "product_harness_s0_s1_finding_ids": sorted(
            {str(finding.get("finding_id", "")) for finding in row_findings if _is_product_or_harness_s0_s1(finding)}
        ),
        "product_finding_ids": sorted(
            {
                str(finding.get("finding_id", ""))
                for finding in row_findings
                if _as_string(finding.get("finding_class"), default="") == "product_behavior"
            }
        ),
        "provider_environment_finding_ids": sorted(
            {
                str(finding.get("finding_id", ""))
                for finding in row_findings
                if _as_string(finding.get("finding_class"), default="") in _PROVIDER_ENVIRONMENT_FINDING_CLASSES
            }
        ),
        "retention_refs": _string_tuple(row.get("retention_refs")),
        "unsupported_or_deferred": _source_row_is_unsupported_or_deferred(row),
    }
    return normalized


def _findings_by_row(report: Mapping[str, object]) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for finding in _mapping_sequence(report.get("findings")):
        row_ids = _string_tuple(finding.get("row_ids"))
        for row_id in row_ids:
            grouped.setdefault(row_id, []).append(dict(finding))
    return grouped


def _comparison_rows(sources: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    by_class = {str(source["collection_class"]): _rows_by_key(source) for source in sources}
    manual_rows = by_class.get("manual", {})
    nightly_rows = by_class.get("nightly", {})
    all_keys = sorted(set(manual_rows) | set(nightly_rows))
    rows: list[dict[str, object]] = []
    for row_key in all_keys:
        manual = manual_rows.get(row_key)
        nightly = nightly_rows.get(row_key)
        representative = manual or nightly
        if representative is None:
            continue
        delta_class, regression_flags = _delta_and_regression_flags(manual, nightly)
        finding_ids = sorted(
            {
                *(_string_tuple(manual.get("finding_ids")) if manual else ()),
                *(_string_tuple(nightly.get("finding_ids")) if nightly else ()),
            }
        )
        retention_refs = sorted(
            {
                "phase11-live-comparison-report.json",
                "phase11-live-comparison-summary.md",
                *(_string_tuple(manual.get("retention_refs")) if manual else ()),
                *(_string_tuple(nightly.get("retention_refs")) if nightly else ()),
            }
        )
        rows.append(
            {
                "comparison_row_id": f"phase11-live-comparison:{row_key}",
                "row_key": row_key,
                "provider_runtime": representative["provider_runtime"],
                "persona_id": representative["persona_id"],
                "scenario_id": representative["scenario_id"],
                "scenario_template_id": representative["scenario_template_id"],
                "command_bucket": representative["command_bucket"],
                "manual_presence": "present" if manual else "missing",
                "nightly_presence": "present" if nightly else "missing",
                "manual_row_id": manual.get("row_id") if manual else None,
                "nightly_row_id": nightly.get("row_id") if nightly else None,
                "manual_result_class": manual.get("result_class") if manual else "missing",
                "nightly_result_class": nightly.get("result_class") if nightly else "missing",
                "manual_attempt_status": manual.get("attempt_status") if manual else "missing",
                "nightly_attempt_status": nightly.get("attempt_status") if nightly else "missing",
                "manual_write_status": manual.get("write_status") if manual else "missing",
                "nightly_write_status": nightly.get("write_status") if nightly else "missing",
                "delta_class": delta_class,
                "regression_flags": regression_flags,
                "finding_ids": finding_ids,
                "finding_classes": sorted(
                    {
                        *(_string_tuple(manual.get("finding_classes")) if manual else ()),
                        *(_string_tuple(nightly.get("finding_classes")) if nightly else ()),
                    }
                ),
                "product_harness_s0_s1_finding_ids": sorted(
                    {
                        *(_string_tuple(manual.get("product_harness_s0_s1_finding_ids")) if manual else ()),
                        *(_string_tuple(nightly.get("product_harness_s0_s1_finding_ids")) if nightly else ()),
                    }
                ),
                "product_finding_ids": sorted(
                    {
                        *(_string_tuple(manual.get("product_finding_ids")) if manual else ()),
                        *(_string_tuple(nightly.get("product_finding_ids")) if nightly else ()),
                    }
                ),
                "provider_environment_finding_ids": sorted(
                    {
                        *(_string_tuple(manual.get("provider_environment_finding_ids")) if manual else ()),
                        *(_string_tuple(nightly.get("provider_environment_finding_ids")) if nightly else ()),
                    }
                ),
                "retention_refs": retention_refs,
                "unsupported_or_deferred": (manual or {}).get("unsupported_or_deferred") is True
                or (nightly or {}).get("unsupported_or_deferred") is True,
            }
        )
    return rows


def _rows_by_key(source: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    rows: dict[str, Mapping[str, object]] = {}
    for row in _mapping_sequence(source.get("rows")):
        row_key = _as_string(row.get("row_key"), default="")
        if row_key in rows:
            raise ValueError(f"duplicate Phase 11 source row key {row_key!r}")
        rows[row_key] = row
    return rows


def _delta_and_regression_flags(
    manual: Mapping[str, object] | None,
    nightly: Mapping[str, object] | None,
) -> tuple[str, list[str]]:
    if manual is None:
        return "manual_missing", ["manual_row_missing"]
    if nightly is None:
        return "nightly_missing", ["nightly_row_missing"]

    flags: list[str] = []
    manual_result = _as_string(manual.get("result_class"), default="unknown")
    nightly_result = _as_string(nightly.get("result_class"), default="unknown")
    result_delta = _rank_delta(manual_result, nightly_result, _RESULT_RANK)
    if result_delta == "regressed":
        flags.append("result_class_regressed")

    manual_acceptance = _behavior_acceptance_from_row(manual)
    nightly_acceptance = _behavior_acceptance_from_row(nightly)
    acceptance_delta = _rank_delta(manual_acceptance, nightly_acceptance, _BEHAVIOR_ACCEPTANCE_RANK)
    if acceptance_delta == "regressed":
        flags.append("behavior_acceptance_regressed")

    if _source_row_has_red_or_invalid(nightly) and not _source_row_has_red_or_invalid(manual):
        flags.append("red_or_invalid_introduced")
    if _string_tuple(nightly.get("product_harness_s0_s1_finding_ids")):
        flags.append("product_or_harness_s0_s1_finding")
    if _string_tuple(nightly.get("product_finding_ids")) and _string_tuple(
        nightly.get("product_harness_s0_s1_finding_ids")
    ):
        flags.append("new_s0_s1_product_finding")

    if flags:
        return "regressed", sorted(set(flags))
    if result_delta == "improved" or acceptance_delta == "improved":
        return "improved", []
    if manual_result != nightly_result or manual.get("attempt_status") != nightly.get("attempt_status"):
        return "changed", []
    return "unchanged", []


def _comparison_aggregates(
    rows: Sequence[Mapping[str, object]],
    source_metadata: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    manual_only = [row for row in rows if row.get("nightly_presence") == "missing"]
    nightly_only = [row for row in rows if row.get("manual_presence") == "missing"]
    common = [
        row for row in rows if row.get("manual_presence") == "present" and row.get("nightly_presence") == "present"
    ]
    red_or_invalid = [
        str(row.get("row_key", ""))
        for row in rows
        if row.get("manual_result_class") in {"red", "invalid_evidence"}
        or row.get("nightly_result_class") in {"red", "invalid_evidence"}
    ]
    regression_rows = [str(row.get("row_key", "")) for row in rows if row.get("delta_class") == "regressed"]
    product_harness_s0_s1_rows = [
        str(row.get("row_key", "")) for row in rows if _string_tuple(row.get("product_harness_s0_s1_finding_ids"))
    ]
    provider_environment_rows = [
        str(row.get("row_key", "")) for row in rows if _string_tuple(row.get("provider_environment_finding_ids"))
    ]
    unsupported_rows = [str(row.get("row_key", "")) for row in rows if row.get("unsupported_or_deferred") is True]
    return {
        "row_count": len(rows),
        "source_report_count": len(source_metadata),
        "comparison_row_count": len(rows),
        "manual_row_count": sum(
            _as_int(source.get("row_count"), default=0)
            for source in source_metadata
            if source.get("collection_class") == "manual"
        ),
        "nightly_row_count": sum(
            _as_int(source.get("row_count"), default=0)
            for source in source_metadata
            if source.get("collection_class") == "nightly"
        ),
        "missing_manual_report_count": 0
        if any(source.get("collection_class") == "manual" for source in source_metadata)
        else 1,
        "missing_nightly_report_count": 0
        if any(source.get("collection_class") == "nightly" for source in source_metadata)
        else 1,
        "common_row_count": len(common),
        "manual_only_row_count": len(manual_only),
        "nightly_only_row_count": len(nightly_only),
        "missing_manual_row_count": len(nightly_only),
        "missing_nightly_row_count": len(manual_only),
        "delta_class_counts": _counter_dict(row.get("delta_class", "unknown") for row in rows),
        "manual_result_class_counts": _counter_dict(row.get("manual_result_class", "missing") for row in rows),
        "nightly_result_class_counts": _counter_dict(row.get("nightly_result_class", "missing") for row in rows),
        "runtime_counts": _counter_dict(row.get("provider_runtime", "unknown") for row in rows),
        "regression_count": len(regression_rows),
        "regressed_row_count": len(regression_rows),
        "red_or_invalid_behavior_count": len(red_or_invalid),
        "product_harness_s0_s1_finding_count": len(product_harness_s0_s1_rows),
        "provider_environment_issue_count": len(provider_environment_rows),
        "unsupported_or_deferred_row_count": len(unsupported_rows),
        "all_rows_unsupported_or_deferred": bool(rows) and len(unsupported_rows) == len(rows),
        "regression_row_keys": sorted(regression_rows),
        "red_or_invalid_row_keys": sorted(red_or_invalid),
        "product_harness_s0_s1_row_keys": sorted(product_harness_s0_s1_rows),
        "provider_environment_issue_row_keys": sorted(provider_environment_rows),
        "unsupported_or_deferred_row_keys": sorted(unsupported_rows),
    }


def _comparison_verdicts(
    rows: Sequence[Mapping[str, object]],
    source_metadata: Sequence[Mapping[str, object]],
    aggregates: Mapping[str, object],
) -> list[dict[str, object]]:
    source_classes = {str(source.get("collection_class", "")) for source in source_metadata}
    return [
        _source_present_verdict("manual", "manual" in source_classes),
        _source_present_verdict("nightly", "nightly" in source_classes),
        _verdict(
            "manual_nightly_only",
            source_classes <= PHASE11_ALLOWED_SOURCE_CLASSES,
            "only manual/nightly source reports were included",
            "unsupported source collection class was included",
        ),
        _verdict(
            "row_key_join_complete",
            bool(rows) and _as_int(aggregates.get("common_row_count"), default=0) == len(rows),
            "all comparison rows have manual and nightly entries",
            "one or more comparison rows are missing a manual or nightly entry",
        ),
        _verdict(
            "not_deferred_only",
            not _as_bool(aggregates.get("all_rows_unsupported_or_deferred"), default=False),
            "at least one comparison row has a supported ready-runtime attempt",
            "all comparison rows are unsupported or deferred",
        ),
        _verdict(
            "no_red_or_invalid_behavior",
            _as_int(aggregates.get("red_or_invalid_behavior_count"), default=0) == 0,
            "no red or invalid behavior rows were observed",
            "red or invalid behavior rows were observed",
            finding_class="product_behavior",
        ),
        _verdict(
            "no_product_or_harness_s0_s1",
            _as_int(aggregates.get("product_harness_s0_s1_finding_count"), default=0) == 0,
            "no S0/S1 product or harness findings were observed",
            "S0/S1 product or harness findings were observed",
            finding_class="product_behavior",
        ),
        _verdict(
            "no_regressions",
            _as_int(aggregates.get("regression_count"), default=0) == 0,
            "no row-level regressions were observed",
            "row-level regressions were observed",
            finding_class="product_behavior",
        ),
        _provider_environment_verdict(aggregates),
        _verdict(
            "default_pytest_provider_free",
            True,
            "comparison rendering is provider-free in default pytest",
            "comparison rendering attempted provider or network access",
        ),
    ]


def _finding_records_from_rows(
    rows: Sequence[Mapping[str, object]],
    row_key: str,
    finding_class: str,
) -> list[dict[str, object]]:
    finding_ids: set[str] = set()
    for row in rows:
        finding_ids.update(_string_tuple(row.get(row_key)))
    return [
        {
            "finding_id": finding_id,
            "finding_class": finding_class,
            "row_keys": sorted(
                str(row.get("row_key", "")) for row in rows if finding_id in _string_tuple(row.get(row_key))
            ),
        }
        for finding_id in sorted(finding_ids)
    ]


def _source_present_verdict(collection_class: str, present: bool) -> dict[str, object]:
    return {
        "gate": f"{collection_class}_source_present",
        "status": "pass" if present else "fail",
        "verdict": "pass" if present else "blocked",
        "collection_class": collection_class,
        "reason": (
            f"{collection_class} sanitized Phase 8 provider-attempt report is present"
            if present
            else f"{collection_class} sanitized Phase 8 provider-attempt report is missing"
        ),
    }


def _comparison_decision(verdicts: Sequence[Mapping[str, object]]) -> Phase11Decision:
    failed = {str(verdict.get("gate", "")) for verdict in verdicts if verdict.get("status") != "pass"}
    blocked_gates = {
        "manual_source_present",
        "nightly_source_present",
        "manual_nightly_only",
        "row_key_join_complete",
        "not_deferred_only",
    }
    if failed & blocked_gates:
        return "blocked"
    if failed:
        return "needs_repair"
    return "accept"


def _decision_reasons(verdicts: Sequence[Mapping[str, object]]) -> list[str]:
    failed = [str(verdict.get("gate", "")) for verdict in verdicts if verdict.get("status") != "pass"]
    return failed or ["all_phase11_live_comparison_gates_passed"]


def _provider_environment_verdict(aggregates: Mapping[str, object]) -> dict[str, object]:
    count = _as_int(aggregates.get("provider_environment_finding_count"), default=0)
    return {
        "gate": "provider_environment_separated",
        "status": "pass",
        "verdict": "blocked" if count else "pass",
        "finding_class": "provider_environment",
        "reason": "provider-environment findings are counted separately from product behavior",
    }


def _next_allowed_action(decision: str) -> str:
    if decision == "accept":
        return "publish_sanitized_phase11_comparison"
    if decision == "needs_repair":
        return "repair_product_or_harness_regressions"
    return "complete_manual_and_nightly_provider_attempts"


def _verdict(
    gate: str,
    passed: bool,
    pass_reason: str,
    fail_reason: str,
    *,
    finding_class: str | None = None,
) -> dict[str, object]:
    payload = {
        "gate": gate,
        "status": "pass" if passed else "fail",
        "verdict": "pass" if passed else "fail",
        "reason": pass_reason if passed else fail_reason,
    }
    if finding_class is not None:
        payload["finding_class"] = finding_class
    return payload


def _phase11_retention_manifest() -> dict[str, object]:
    return {
        "classes": {
            "committed_redacted": {
                "safe_to_commit": True,
                "local_only": False,
                "description": "Sanitized Phase 11 comparison artifact committed to the repository.",
            }
        },
        "artifacts": [
            {
                "artifact_id": "phase11-live-comparison-report-json",
                "artifact_ref": "phase11-live-comparison-report.json",
                "retention_class": "committed_redacted",
                "material_class": "sanitized_report",
                "safe_to_commit": True,
                "local_only": False,
            },
            {
                "artifact_id": "phase11-live-comparison-summary-md",
                "artifact_ref": "phase11-live-comparison-summary.md",
                "retention_class": "committed_redacted",
                "material_class": "sanitized_summary",
                "safe_to_commit": True,
                "local_only": False,
            },
        ],
    }


def _phase11_retention_errors(retention: Mapping[str, object]) -> list[str]:
    errors: list[str] = []
    classes = retention.get("classes")
    if not isinstance(classes, Mapping):
        errors.append("report.retention_manifest.classes must be a mapping")
    elif "committed_redacted" not in classes:
        errors.append("report.retention_manifest.classes missing 'committed_redacted'")

    artifacts = _mapping_sequence(retention.get("artifacts"))
    if not artifacts:
        errors.append("report.retention_manifest.artifacts must be non-empty")
    for index, artifact in enumerate(artifacts):
        context = f"report.retention_manifest.artifacts[{index}]"
        if not _as_string(artifact.get("artifact_ref"), default=""):
            errors.append(f"{context}.artifact_ref is required")
        if artifact.get("retention_class") != "committed_redacted":
            errors.append(f"{context}.retention_class must be committed_redacted")
        if artifact.get("safe_to_commit") is not True:
            errors.append(f"{context}.safe_to_commit must be true")
        if artifact.get("local_only") is True:
            errors.append(f"{context}.local_only must be false")
        material_class = _as_string(artifact.get("material_class"), default="")
        if not material_class.startswith("sanitized_"):
            errors.append(f"{context}.material_class must be sanitized")
    return errors


def _source_row_is_unsupported_or_deferred(row: Mapping[str, object]) -> bool:
    return (
        _as_string(row.get("launch_policy"), default="") in {"setup_refusal", "deferred"}
        or _as_string(row.get("attempt_status"), default="") in _UNSUPPORTED_ATTEMPT_STATUSES
    )


def _source_row_has_red_or_invalid(row: Mapping[str, object]) -> bool:
    return _as_string(row.get("result_class"), default="unknown") in {"red", "invalid_evidence"}


def _behavior_acceptance_from_row(row: Mapping[str, object]) -> str:
    if _source_row_has_red_or_invalid(row):
        return "rejected"
    if _string_tuple(row.get("product_harness_s0_s1_finding_ids")):
        return "rejected"
    if _as_string(row.get("result_class"), default="unknown") == "green":
        return "accepted"
    return "pending"


def _rank_delta(left: str, right: str, ranks: Mapping[str, int]) -> str:
    left_rank = ranks.get(left, ranks["unknown"])
    right_rank = ranks.get(right, ranks["unknown"])
    if right_rank < left_rank:
        return "improved"
    if right_rank > left_rank:
        return "regressed"
    return "unchanged"


def _max_finding_severity(findings: Sequence[Mapping[str, object]]) -> str:
    severity = "none"
    rank = {"S0": 0, "S1": 1, "S2": 2, "S3": 3, "unknown": 4, "none": 5}
    for finding in findings:
        candidate = _normalize_severity(finding.get("severity"))
        if rank[candidate] < rank[severity]:
            severity = candidate
    return severity


def _is_product_or_harness_s0_s1(finding: Mapping[str, object]) -> bool:
    return (
        _normalize_severity(finding.get("severity")) in _HARD_SEVERITIES
        and _as_string(finding.get("finding_class"), default="") in _PRODUCT_OR_HARNESS_FINDING_CLASSES
    )


def _normalize_severity(value: object) -> str:
    severity = _as_string(value, default="unknown").upper()
    return severity if severity in {"S0", "S1", "S2", "S3"} else "unknown"


def _normalize_result_class(value: object) -> str:
    result = _as_string(value, default="unknown").casefold()
    if result in {"pass", "passed", "success", "succeeded", "green"}:
        return "green"
    if result in {"warn", "warning", "yellow", "setup_refused", "blocked", "pending"}:
        return "yellow"
    if result in {"fail", "failed", "failure", "error", "red"}:
        return "red"
    if result in {"invalid", "invalid_evidence", "malformed_evidence"}:
        return "invalid_evidence"
    return "unknown"


def _collect_phase11_safety_issues(value: object, context: str, issues: list[str]) -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = _as_string(raw_key, default="")
            normalized_key = _normalize_key(key)
            child_context = f"{context}.{key}" if key else context
            if normalized_key in _UNSAFE_PHASE11_FIELD_NAMES or any(
                marker in normalized_key for marker in _UNSAFE_PHASE11_FIELD_MARKERS
            ):
                issues.append(f"{child_context} is a forbidden raw provider/auth/prompt/env/path field")
            _collect_phase11_safety_issues(child, child_context, issues)
        return
    if _is_sequence(value):
        for index, child in enumerate(value):
            _collect_phase11_safety_issues(child, f"{context}[{index}]", issues)
        return
    if isinstance(value, str) and (_PATHY_VALUE_RE.search(value) or value.startswith("~/")):
        issues.append(f"{context} contains a real home path")


def _required_mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{context} must be a mapping")
    for key in value:
        if not isinstance(key, str):
            raise ValueError(f"{context} keys must be strings")
    return cast(Mapping[str, object], value)


def _mapping_or_empty(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _mapping_sequence(value: object) -> list[dict[str, object]]:
    if not _is_sequence(value):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _required_str(mapping: Mapping[str, object], key: str, context: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{context}.{key} must be a non-empty string")
    return value


def _optional_str(mapping: Mapping[str, object], key: str, context: str) -> str | None:
    if key not in mapping:
        return None
    return _required_str(mapping, key, context)


def _required_bool(mapping: Mapping[str, object], key: str, context: str) -> bool:
    value = mapping.get(key)
    if type(value) is not bool:
        raise ValueError(f"{context}.{key} must be a boolean")
    return value


def _as_string(value: object, *, default: str) -> str:
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
        normalized = value.casefold().strip()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
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


def _string_tuple(value: object) -> tuple[str, ...]:
    if not _is_sequence(value):
        return ()
    strings = sorted({_as_string(item, default="") for item in value if _as_string(item, default="")})
    return tuple(strings)


def _string_list_preserve_order(value: object) -> list[str]:
    if not _is_sequence(value):
        return []
    strings: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _as_string(item, default="")
        if text and text not in seen:
            seen.add(text)
            strings.append(text)
    return strings


def _counter_dict(values: object) -> dict[str, int]:
    if not _is_sequence(values):
        values = list(values) if values is not None else []
    return dict(sorted(Counter(str(value) for value in values).items()))


def _row_key_part(value: object) -> str:
    text = _as_string(value, default="unknown")
    return text.replace("|", "_").replace("\n", " ").strip() or "unknown"


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.casefold())


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


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


def _json_cell(value: object) -> str:
    if isinstance(value, (Mapping, Sequence)) and not isinstance(value, str):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


def stable_phase11_sha256(value: object) -> str:
    """Return the stable JSON SHA-256 used by Phase 11 helper reports."""

    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


__all__ = [
    "PHASE11_ALLOWED_SOURCE_CLASSES",
    "PHASE11_ALLOWED_MATRIX_SOURCE_CLASSES",
    "PHASE11_LIVE_COMPARISON_MATRIX_SCHEMA",
    "PHASE11_LIVE_COMPARISON_REPORT_SCHEMA",
    "PHASE11_LIVE_READINESS_ROW_SCHEMA",
    "PHASE11_REQUIRED_MATRIX_SOURCE_CLASSES",
    "PHASE11_REQUIRED_SOURCE_CLASSES",
    "Phase11ComparisonMatrix",
    "Phase11DefaultPytestPolicy",
    "Phase11Decision",
    "Phase11LiveComparisonMatrix",
    "Phase11LiveComparisonRow",
    "Phase11RowContract",
    "Phase11SourceClass",
    "build_live_readiness_matrix",
    "build_phase11_live_readiness_rows",
    "default_phase11_comparison_matrix_path",
    "default_phase11_live_comparison_matrix_path",
    "derive_phase11_live_readiness_rows",
    "load_phase11_comparison_matrix",
    "load_phase11_live_comparison_matrix",
    "phase11_comparison_row_key",
    "phase11_live_comparison_report_validation_errors",
    "render_live_comparison_markdown",
    "render_live_comparison_report",
    "render_phase11_comparison_markdown",
    "render_phase11_comparison_report",
    "render_phase11_live_comparison_markdown",
    "render_phase11_live_comparison_report",
    "stable_phase11_sha256",
    "validate_live_comparison_report",
    "validate_live_readiness_matrix",
    "validate_phase11_comparison_fixture",
    "validate_phase11_comparison_matrix",
    "validate_phase11_comparison_report",
    "validate_phase11_live_comparison_matrix",
    "validate_phase11_live_comparison_report",
    "validate_phase11_payload_safety",
]
