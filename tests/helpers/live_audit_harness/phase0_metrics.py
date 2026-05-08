"""Provider-free Phase 0 behavior metrics for live-audit class-only artifacts."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from tests.helpers.live_audit_harness.phase8_schema import Phase8Matrix

PHASE0_LIVE_AUDIT_METRICS_SCHEMA: Final[str] = "phase0.live-audit-behavior-metrics.v1"

_MISSING: Final[object] = object()
_NESTED_SOURCES: Final[tuple[str, ...]] = (
    "behavior",
    "contract",
    "evidence_packet",
    "features",
    "metadata",
    "row",
    "run",
    "score",
    "status",
    "write_classification",
)
_WORK_EVENT_MARKERS: Final[frozenset[str]] = frozenset(
    {"child", "command", "file_write", "patch", "subagent", "tool", "write"}
)


@dataclass(frozen=True, slots=True)
class Phase0LiveAuditMetrics:
    """Class-only counts used to freeze Phase 0 fake/live-audit behavior."""

    schema: str
    row_count: int
    result_class_counts: dict[str, int]
    finding_class_counts: dict[str, int]
    finding_id_counts: dict[str, int]
    finding_severity_counts: dict[str, int]
    finding_count: int
    accepted_row_count: int
    rejected_row_count: int
    pending_behavior_row_count: int
    s0_s1_finding_count: int
    setup_turn_count: int
    recovery_turn_count: int
    duplicate_question_count: int
    schema_failure_count: int
    false_success_count: int
    write_violation_count: int
    stop_violation_count: int
    post_stop_activity_count: int
    prompt_budget_finding_count: int
    provider_subprocess_attempt_count: int
    network_attempt_count: int
    launch_policy_counts: dict[str, int]
    default_pytest_row_count: int

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "class_only": True,
            "provider_free": True,
            "row_count": self.row_count,
            "result_class_counts": self.result_class_counts,
            "finding_class_counts": self.finding_class_counts,
            "finding_id_counts": self.finding_id_counts,
            "finding_severity_counts": self.finding_severity_counts,
            "finding_count": self.finding_count,
            "accepted_row_count": self.accepted_row_count,
            "rejected_row_count": self.rejected_row_count,
            "pending_behavior_row_count": self.pending_behavior_row_count,
            "s0_s1_finding_count": self.s0_s1_finding_count,
            "setup_turn_count": self.setup_turn_count,
            "recovery_turn_count": self.recovery_turn_count,
            "duplicate_question_count": self.duplicate_question_count,
            "schema_failure_count": self.schema_failure_count,
            "false_success_count": self.false_success_count,
            "write_violation_count": self.write_violation_count,
            "stop_violation_count": self.stop_violation_count,
            "post_stop_activity_count": self.post_stop_activity_count,
            "prompt_budget_finding_count": self.prompt_budget_finding_count,
            "provider_subprocess_attempt_count": self.provider_subprocess_attempt_count,
            "network_attempt_count": self.network_attempt_count,
            "launch_policy_counts": self.launch_policy_counts,
            "default_pytest_row_count": self.default_pytest_row_count,
        }


def collect_phase0_live_audit_metrics(
    *,
    phase8_matrix: Phase8Matrix | None = None,
    rows: Sequence[object] = (),
    scores: Sequence[object] = (),
    reports: Sequence[Mapping[str, object]] = (),
    sidecars: Sequence[object] = (),
    schema_failures: Sequence[object] = (),
) -> Phase0LiveAuditMetrics:
    """Collect provider-free Phase 0 behavior metrics from class-only records."""

    builder = _MetricsBuilder()
    if phase8_matrix is not None:
        builder.add_phase8_matrix(phase8_matrix)
    for row in rows:
        builder.add_row(row)
    for score in scores:
        builder.add_score(score)
    for report in reports:
        builder.add_report(report)
    for sidecar in sidecars:
        builder.add_sidecar(sidecar)
    for failure in schema_failures:
        builder.add_schema_failure(failure)
    return builder.build()


def collect_phase0_live_audit_metrics_from_artifact_roots(
    row_roots: Sequence[Path],
    *,
    scores: Sequence[object] = (),
    reports: Sequence[Mapping[str, object]] = (),
    phase8_matrix: Phase8Matrix | None = None,
) -> Phase0LiveAuditMetrics:
    """Collect metrics from fake/live-audit row roots without reading raw final/stdout text."""

    sidecars = [_load_sidecar_bundle(row_root) for row_root in row_roots]
    return collect_phase0_live_audit_metrics(
        phase8_matrix=phase8_matrix,
        scores=scores,
        reports=reports,
        sidecars=sidecars,
    )


class _MetricsBuilder:
    def __init__(self) -> None:
        self._row_ids: set[str] = set()
        self._anonymous_row_count = 0
        self.result_class_counts: Counter[str] = Counter()
        self.finding_class_counts: Counter[str] = Counter()
        self.finding_id_counts: Counter[str] = Counter()
        self.finding_severity_counts: Counter[str] = Counter()
        self.behavior_acceptance_counts: Counter[str] = Counter()
        self.launch_policy_counts: Counter[str] = Counter()
        self.default_pytest_row_count = 0
        self.setup_turn_count = 0
        self.recovery_turn_count = 0
        self.provider_subprocess_attempt_count = 0
        self.network_attempt_count = 0
        self._duplicate_question_incidents: set[tuple[str, str]] = set()
        self._schema_failure_incidents: set[tuple[str, str]] = set()
        self._false_success_incidents: set[tuple[str, str]] = set()
        self._write_violation_incidents: set[tuple[str, str]] = set()
        self._stop_violation_incidents: set[tuple[str, str]] = set()
        self._post_stop_incidents: set[tuple[str, str]] = set()
        self._prompt_budget_incidents: set[tuple[str, str]] = set()
        self._s0_s1_finding_incidents: set[tuple[str, str]] = set()

    def add_phase8_matrix(self, matrix: Phase8Matrix) -> None:
        for row in matrix.rows:
            self._add_row_id(row.row_id)
            self.launch_policy_counts[row.launch_policy] += 1
            if row.default_pytest:
                self.default_pytest_row_count += 1

    def add_row(self, row: object, *, include_findings: bool = True) -> None:
        row_id = self._row_id(row)
        self._add_row_id(row_id)
        self._add_result(row, row_id=row_id)
        self._add_launch_policy(row)
        self._add_default_pytest(row)
        self._add_turn_counts(row, row_id=row_id)
        self._add_attempt_counts(row)
        self._add_write_metrics(row, row_id=row_id)
        self._add_prompt_budget(row, row_id=row_id)
        self._add_stop_activity(row, row_id=row_id)
        self._add_behavior_acceptance(row, row_id=row_id)
        if include_findings:
            self._add_findings(_records(_read(row, "findings")), default_row_id=row_id)
            for finding_id in _string_items(_read(row, "finding_ids")):
                self._add_finding({"finding_id": finding_id}, default_row_id=row_id)
        score = _read(row, "score")
        if score is not None and score is not row:
            self.add_score(score, default_row_id=row_id)

    def add_score(self, score: object, *, default_row_id: str = "") -> None:
        row_id = self._row_id(score, default=default_row_id)
        self._add_row_id(row_id)
        result_class = _normalize_result_class(_read(score, "result", "result_class", "observed_result_class"))
        if result_class:
            self.result_class_counts[result_class] += 1
        if result_class == "invalid_evidence":
            self._add_incident(self._schema_failure_incidents, row_id, "schema_failure")
        self._add_behavior_acceptance(score, row_id=row_id)
        self._add_findings(_records(_read(score, "findings")), default_row_id=row_id)

    def add_report(self, report: Mapping[str, object]) -> None:
        rows = _mapping_sequence(report.get("rows"))
        for row in rows:
            self.add_row(row, include_findings=False)
        self._add_findings(_mapping_sequence(report.get("findings")), default_row_id="")
        self._add_report_prompt_budget(report)
        if not rows:
            aggregates = _mapping(_read(report, "aggregates"))
            for _ in range(_non_negative_int(aggregates.get("row_count"))):
                self._add_row_id("")
            self.provider_subprocess_attempt_count += _non_negative_int(
                _read(report, "provider_subprocess_attempts", "provider_attempt_count")
            )
            self.network_attempt_count += _non_negative_int(_read(report, "network_attempts"))

    def add_sidecar(self, sidecar: object) -> None:
        row_id = self._row_id(sidecar)
        self._add_row_id(row_id)
        self._add_turn_counts(sidecar, row_id=row_id)
        self._add_attempt_counts(sidecar)
        self._add_write_metrics(sidecar, row_id=row_id)
        self._add_prompt_budget(sidecar, row_id=row_id)
        self._add_stop_activity(sidecar, row_id=row_id)
        self._add_events(_records(_read(sidecar, "events", "normalized_events")), row_id=row_id)
        score = _read(sidecar, "semantic_score", "score")
        if score is not None:
            self.add_score(score, default_row_id=row_id)

    def add_schema_failure(self, failure: object) -> None:
        row_id = self._row_id(failure)
        failure_id = _as_string(_read(failure, "schema_failure_id", "error_id", "finding_id"), default="schema")
        self._add_incident(self._schema_failure_incidents, row_id, failure_id)

    def build(self) -> Phase0LiveAuditMetrics:
        return Phase0LiveAuditMetrics(
            schema=PHASE0_LIVE_AUDIT_METRICS_SCHEMA,
            row_count=len(self._row_ids) + self._anonymous_row_count,
            result_class_counts=_counter_payload(self.result_class_counts),
            finding_class_counts=_counter_payload(self.finding_class_counts),
            finding_id_counts=_counter_payload(self.finding_id_counts),
            finding_severity_counts=_counter_payload(self.finding_severity_counts),
            finding_count=sum(self.finding_id_counts.values()),
            accepted_row_count=self.behavior_acceptance_counts.get("accepted", 0),
            rejected_row_count=self.behavior_acceptance_counts.get("rejected", 0),
            pending_behavior_row_count=self.behavior_acceptance_counts.get("pending", 0),
            s0_s1_finding_count=len(self._s0_s1_finding_incidents),
            setup_turn_count=self.setup_turn_count,
            recovery_turn_count=self.recovery_turn_count,
            duplicate_question_count=len(self._duplicate_question_incidents),
            schema_failure_count=len(self._schema_failure_incidents),
            false_success_count=len(self._false_success_incidents),
            write_violation_count=len(self._write_violation_incidents),
            stop_violation_count=len(self._stop_violation_incidents),
            post_stop_activity_count=len(self._post_stop_incidents),
            prompt_budget_finding_count=len(self._prompt_budget_incidents),
            provider_subprocess_attempt_count=self.provider_subprocess_attempt_count,
            network_attempt_count=self.network_attempt_count,
            launch_policy_counts=_counter_payload(self.launch_policy_counts),
            default_pytest_row_count=self.default_pytest_row_count,
        )

    def _row_id(self, source: object, *, default: str = "") -> str:
        return _as_string(_read(source, "row_id", "scenario_run_id", "run_id"), default=default)

    def _add_row_id(self, row_id: str) -> None:
        if row_id:
            self._row_ids.add(row_id)
        else:
            self._anonymous_row_count += 1

    def _add_result(self, source: object, *, row_id: str) -> None:
        result_class = _normalize_result_class(_read(source, "result", "result_class", "observed_result_class"))
        if not result_class:
            return
        self.result_class_counts[result_class] += 1
        if result_class == "invalid_evidence":
            self._add_incident(self._schema_failure_incidents, row_id, "schema_failure")

    def _add_launch_policy(self, source: object) -> None:
        launch_policy = _as_string(_read(source, "launch_policy", "mode"), default="")
        if launch_policy:
            self.launch_policy_counts[launch_policy] += 1

    def _add_default_pytest(self, source: object) -> None:
        if _truthy(_read(source, "default_pytest")) is True:
            self.default_pytest_row_count += 1

    def _add_turn_counts(self, source: object, *, row_id: str) -> None:
        self.setup_turn_count += _count_like(_read(source, "setup_turn_count", "setup_turns"))
        self.recovery_turn_count += _count_like(_read(source, "recovery_turn_count", "recovery_turns"))
        for turn in _records(_read(source, "turns", "turn_events")):
            self._add_turn_record(turn, row_id=row_id)

    def _add_events(self, events: Sequence[object], *, row_id: str) -> None:
        for index, event in enumerate(events):
            self._add_turn_record(event, row_id=row_id)
            if _event_is_post_stop_activity(event):
                self._add_incident(self._post_stop_incidents, row_id, f"event.{index}")

    def _add_turn_record(self, record: object, *, row_id: str) -> None:
        labels = _record_labels(record)
        if any("setup" in label for label in labels):
            self.setup_turn_count += 1
        if any("recover" in label for label in labels):
            self.recovery_turn_count += 1
        if _event_is_post_stop_activity(record):
            self._add_incident(self._post_stop_incidents, row_id, f"turn.{len(self._post_stop_incidents)}")

    def _add_attempt_counts(self, source: object) -> None:
        self.provider_subprocess_attempt_count += _attempt_count(
            source,
            count_keys=(
                "provider_subprocess_attempt_count",
                "provider_subprocess_attempts",
                "attempted_subprocesses",
            ),
            flag_keys=(
                "provider_subprocess_attempted",
                "provider_launch_attempted",
                "provider_launched",
                "subprocess_invoked",
            ),
        )
        self.network_attempt_count += _attempt_count(
            source,
            count_keys=("network_attempt_count", "network_attempts"),
            flag_keys=("network_attempted", "network_used", "http_request_attempted"),
        )

    def _add_write_metrics(self, source: object, *, row_id: str) -> None:
        count = _non_negative_int(_read(source, "write_violation_count", "unexpected_write_count"))
        summary = _mapping(_read(source, "summary"))
        count += _non_negative_int(summary.get("forbidden_materialized"))
        for write in _records(_read(source, "writes", "write_events", "observed_writes")):
            if _write_is_violation(write):
                count += 1
        if count or _write_status_is_violation(_read(source, "write_status", "write_class")):
            self._add_incident(self._write_violation_incidents, row_id, "write.violation")

    def _add_prompt_budget(self, source: object, *, row_id: str) -> None:
        prompt_budget = _mapping(_read(source, "prompt_budget", "prompt_metrics"))
        if not prompt_budget:
            return
        status = _as_string(prompt_budget.get("status"), default="").casefold()
        overflow = _non_negative_int(_read(prompt_budget, "overflow_tokens", "over_budget_tokens"))
        prompt_tokens = _non_negative_int(_read(prompt_budget, "prompt_tokens", "prompt_tokens_estimate"))
        token_budget = _non_negative_int(_read(prompt_budget, "token_budget", "max_prompt_tokens"))
        over_budget = _truthy(_read(prompt_budget, "over_budget", "budget_overflow"))
        if (
            status == "over_budget"
            or overflow
            or over_budget is True
            or (prompt_tokens and token_budget and prompt_tokens > token_budget)
        ):
            self._add_incident(self._prompt_budget_incidents, row_id, "prompt_budget.over_budget")
        leaked_count = _non_negative_int(_read(prompt_budget, "hidden_marker_count", "prompt_echo_count"))
        if leaked_count or _records(_read(prompt_budget, "leaked_markers", "hidden_markers")):
            self._add_incident(self._prompt_budget_incidents, row_id, "prompt_budget.hidden_marker")

    def _add_report_prompt_budget(self, report: Mapping[str, object]) -> None:
        prompt_budget = _mapping(report.get("prompt_budget"))
        for row_id in _string_items(prompt_budget.get("over_budget_rows")):
            self._add_incident(self._prompt_budget_incidents, row_id, "report.prompt_budget.over_budget")

    def _add_stop_activity(self, source: object, *, row_id: str) -> None:
        if _truthy(_read(source, "post_stop_activity")) is True:
            self._add_incident(self._post_stop_incidents, row_id, "post_stop_activity")
        post_stop_count = _non_negative_int(
            _read(source, "post_stop_activity_count", "post_stop_command_count", "post_stop_write_count")
        )
        for index in range(post_stop_count):
            self._add_incident(self._post_stop_incidents, row_id, f"post_stop.{index}")

    def _add_findings(self, findings: Sequence[object], *, default_row_id: str) -> None:
        for finding in findings:
            self._add_finding(finding, default_row_id=default_row_id)

    def _add_finding(self, finding: object, *, default_row_id: str) -> None:
        finding_id = _finding_id(finding)
        if not finding_id:
            return
        finding_class = _finding_class(finding)
        severity = _finding_severity(finding)
        row_ids = _finding_row_ids(finding, default_row_id=default_row_id)
        impact_count = max(len(row_ids), 1)
        self.finding_id_counts[finding_id] += impact_count
        self.finding_class_counts[finding_class] += impact_count
        self.finding_severity_counts[severity] += impact_count
        for row_id in row_ids or ("",):
            marker = f"{finding_id} {finding_class}".casefold()
            if severity in {"S0", "S1"}:
                self._add_incident(self._s0_s1_finding_incidents, row_id, finding_id)
            if "duplicate_question" in marker or "duplicate_questions" in marker or "asks_duplicate_question" in marker:
                self._add_incident(self._duplicate_question_incidents, row_id, finding_id)
            if "invalid_evidence" in marker or "schema_failure" in marker or "schema_validation" in marker:
                self._add_incident(self._schema_failure_incidents, row_id, "schema_failure")
            if "fake_execution_claim" in marker or "false_success" in marker or "unproven_execution" in marker:
                self._add_incident(self._false_success_incidents, row_id, finding_id)
            if "wrong_workspace_write" in marker or "write_violation" in marker or "forbidden_write" in marker:
                self._add_incident(self._write_violation_incidents, row_id, finding_id)
            if "stop_ignored" in marker or "post_stop" in marker:
                self._add_incident(self._stop_violation_incidents, row_id, finding_id)
            if "post_stop" in marker:
                self._add_incident(self._post_stop_incidents, row_id, finding_id)
            if "prompt_budget" in marker or "prompt_budget_leakage" in marker:
                self._add_incident(self._prompt_budget_incidents, row_id, finding_id)

    def _add_behavior_acceptance(self, source: object, *, row_id: str) -> None:
        acceptance = _behavior_acceptance(source)
        if acceptance:
            self.behavior_acceptance_counts[acceptance] += 1

    def _add_incident(self, incidents: set[tuple[str, str]], row_id: str, incident_id: str) -> None:
        incidents.add((row_id or f"anonymous-{len(incidents)}", incident_id))


def _load_sidecar_bundle(row_root: Path) -> dict[str, object]:
    status = _read_json_if_present(row_root / "status.json")
    write_classification = _read_json_if_present(row_root / "write-classification.json")
    evidence_packet = _read_json_if_present(row_root / "evidence-packet.json")
    semantic_score = _read_json_if_present(row_root / "semantic-score.json")
    events = _read_event_summaries_if_present(row_root / "normalized-events.jsonl")
    row_id = _as_string(
        _read(status, "row_id"),
        default=_as_string(_read(write_classification, "row_id"), default=_as_string(_read(evidence_packet, "row_id"))),
    )
    return {
        "row_id": row_id,
        "status": status,
        "write_classification": write_classification,
        "evidence_packet": evidence_packet,
        "semantic_score": semantic_score,
        "events": events,
    }


def _read_json_if_present(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return dict(payload) if isinstance(payload, Mapping) else {}


def _read_event_summaries_if_present(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        return []
    events: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, Mapping):
                raise ValueError(f"{path}:{line_number}: expected JSON object")
            metadata = payload.get("metadata")
            metadata_payload = dict(metadata) if isinstance(metadata, Mapping) else {}
            events.append(
                {
                    "kind": _as_string(payload.get("kind"), default=_as_string(payload.get("type"))),
                    "event_type": _as_string(payload.get("event_type")),
                    "metadata": metadata_payload,
                    "after_stop": payload.get("after_stop"),
                    "post_stop": payload.get("post_stop"),
                    "turn_class": payload.get("turn_class"),
                    "phase": payload.get("phase"),
                    "stage": payload.get("stage"),
                }
            )
    return events


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


def _read_direct(source: object, key: str, *, default: object = _MISSING) -> object:
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _mapping(value: object | None) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _mapping_sequence(value: object | None) -> list[dict[str, object]]:
    return [dict(item) for item in _records(value) if isinstance(item, Mapping)]


def _records(value: object | None) -> tuple[object, ...]:
    if value is None or isinstance(value, str | bytes):
        return ()
    if isinstance(value, Mapping):
        return (value,)
    if isinstance(value, Iterable):
        return tuple(value)
    return ()


def _string_items(value: object | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Mapping):
        return tuple(str(key) for key in value)
    if isinstance(value, Iterable):
        return tuple(str(item) for item in value)
    return (str(value),)


def _as_string(value: object | None, *, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip()
        return text if text else default
    return str(value)


def _truthy(value: object | None) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"1", "allowed", "pass", "passed", "present", "true", "yes"}:
            return True
        if normalized in {"0", "absent", "fail", "failed", "false", "forbidden", "missing", "no"}:
            return False
    return None


def _non_negative_int(value: object | None) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    return 0


def _count_like(value: object | None) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int | float | str):
        return _non_negative_int(value)
    return len(_records(value))


def _attempt_count(source: object, *, count_keys: Sequence[str], flag_keys: Sequence[str]) -> int:
    for key in count_keys:
        value = _read(source, key)
        if value is not None:
            return _non_negative_int(value)
    for key in flag_keys:
        if _truthy(_read(source, key)) is True:
            return 1
    return 0


def _normalize_result_class(value: object | None) -> str:
    result = _as_string(value).casefold().replace("-", "_")
    aliases = {
        "fail": "red",
        "failed": "red",
        "invalid": "invalid_evidence",
        "invalid_evidence": "invalid_evidence",
        "pass": "green",
        "passed": "green",
        "red": "red",
        "success": "green",
        "warn": "yellow",
        "warning": "yellow",
        "yellow": "yellow",
    }
    return aliases.get(result, result if result in {"green", "yellow", "red"} else "")


def _finding_id(finding: object) -> str:
    return _as_string(_read(finding, "finding_id", "id", "code"), default="")


def _finding_class(finding: object) -> str:
    return _as_string(
        _read(finding, "finding_class", "detector", "category", "dimension", "kind"),
        default="unknown",
    )


def _finding_severity(finding: object) -> str:
    severity = _as_string(_read(finding, "severity", "max_severity"), default="unknown").upper()
    return severity if severity in {"S0", "S1", "S2", "S3"} else "unknown"


def _finding_row_ids(finding: object, *, default_row_id: str) -> tuple[str, ...]:
    row_ids = _string_items(_read(finding, "row_ids"))
    row_id = _as_string(_read(finding, "row_id"), default="")
    if row_id:
        row_ids = (*row_ids, row_id)
    if not row_ids and default_row_id:
        row_ids = (default_row_id,)
    return tuple(sorted(set(row_ids)))


def _behavior_acceptance(source: object) -> str:
    explicit = _explicit_behavior_acceptance(source)
    if explicit == "rejected":
        return "rejected"

    findings = _records(_read(source, "findings"))
    if any(_finding_severity(finding) in {"S0", "S1"} for finding in findings):
        return "rejected"
    if _non_negative_int(_read(source, "false_success_count")) > 0:
        return "rejected"
    if _non_negative_int(_read(source, "write_violation_count", "unexpected_write_count")) > 0:
        return "rejected"
    if _non_negative_int(_read(source, "stop_violation_count", "post_stop_activity_count")) > 0:
        return "rejected"
    if _truthy(_read(source, "post_stop_activity")) is True:
        return "rejected"
    if _write_status_is_violation(_read(source, "write_status", "write_class")):
        return "rejected"

    result_class = _normalize_result_class(_read(source, "result", "result_class", "observed_result_class"))
    if result_class in {"red", "invalid_evidence"}:
        return "rejected"
    if explicit:
        return explicit
    if result_class == "green":
        return "accepted"
    if result_class in {"yellow"}:
        return "pending"
    return ""


def _explicit_behavior_acceptance(source: object) -> str:
    rejected = _read(source, "rejected", "behavior_rejected", "semantic_rejected")
    if isinstance(rejected, bool) and rejected:
        return "rejected"

    accepted = _read(source, "accepted", "behavior_accepted", "semantic_accepted")
    if isinstance(accepted, bool):
        return "accepted" if accepted else "rejected"

    value = _read(
        source,
        "behavior_acceptance",
        "semantic_acceptance",
        "acceptance",
        "acceptance_status",
        "row_acceptance",
    )
    normalized = _as_string(value, default="").casefold().replace("-", "_")
    if normalized in {"accept", "accepted", "green", "pass", "passed", "ready"}:
        return "accepted"
    if normalized in {
        "fail",
        "failed",
        "hard_fail",
        "invalid",
        "invalid_evidence",
        "not_accepted",
        "red",
        "reject",
        "rejected",
    }:
        return "rejected"
    if normalized in {"blocked", "needs_repair", "pending", "warn", "warning", "yellow"}:
        return "pending"
    return ""


def _write_is_violation(write: object) -> bool:
    role = _as_string(_read(write, "role", "path_role", "classification")).casefold()
    status = _as_string(_read(write, "status", "policy")).casefold()
    return (
        role in {"active_checkout", "outside_authority", "runtime_or_home"}
        or status in {"forbidden", "unexpected", "violation"}
        or _truthy(_read(write, "allowed", "permitted", "authorized")) is False
        or _truthy(_read(write, "violation", "unexpected", "forbidden")) is True
    )


def _write_status_is_violation(value: object | None) -> bool:
    return _as_string(value).casefold() in {"forbidden", "unexpected", "violation", "write_violation"}


def _record_labels(record: object) -> tuple[str, ...]:
    metadata = _mapping(_read(record, "metadata"))
    labels = [
        _as_string(_read(record, "kind", "type", "event_type", "name")),
        _as_string(_read(record, "turn_class", "phase", "stage", "purpose")),
        _as_string(_read(metadata, "turn_class", "phase", "stage", "purpose")),
    ]
    return tuple(label.casefold() for label in labels if label)


def _event_is_post_stop_activity(event: object) -> bool:
    metadata = _mapping(_read(event, "metadata"))
    after_stop = _truthy(_read(event, "after_stop", "post_stop"))
    if after_stop is None:
        after_stop = _truthy(_read(metadata, "after_stop", "post_stop"))
    if after_stop is not True:
        return False
    labels = _record_labels(event)
    return any(any(marker in label for marker in _WORK_EVENT_MARKERS) for label in labels) or not labels


def _counter_payload(counter: Counter[str]) -> dict[str, int]:
    return dict(sorted((key, count) for key, count in counter.items() if count))


__all__ = (
    "PHASE0_LIVE_AUDIT_METRICS_SCHEMA",
    "Phase0LiveAuditMetrics",
    "collect_phase0_live_audit_metrics",
    "collect_phase0_live_audit_metrics_from_artifact_roots",
)
