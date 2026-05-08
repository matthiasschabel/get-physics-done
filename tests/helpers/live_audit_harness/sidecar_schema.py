"""Phase 9 provider-free sidecar bundle validation helpers."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Final, cast

from tests.helpers.live_audit_harness.phase8_schema import LIVE_PROVIDER_MARKER, REQUIRED_ARTIFACTS

SIDECAR_BUNDLE_SCHEMA: Final[str] = "phase9.live-audit-sidecar-bundle.v1"
STATUS_SCHEMA: Final[str] = "phase9.live-audit-status.v1"
WRITE_CLASSIFICATION_SCHEMA: Final[str] = "phase9.live-audit-write-classification.v1"
EVIDENCE_PACKET_SCHEMA: Final[str] = "phase9.live-audit-evidence-packet.v1"

REQUIRED_SIDECARS: Final[tuple[str, ...]] = (
    "status.json",
    "stdout.jsonl",
    "normalized-events.jsonl",
    "final.md",
    "write-classification.json",
    "evidence-packet.json",
)
JSON_SIDECARS: Final[frozenset[str]] = frozenset({"status.json", "write-classification.json", "evidence-packet.json"})
JSONL_SIDECARS: Final[frozenset[str]] = frozenset({"stdout.jsonl", "normalized-events.jsonl"})
MAX_FINAL_BYTES: Final[int] = 64 * 1024

_STATUS_SCHEMAS: Final[frozenset[str]] = frozenset({"phase7.fake-runner-status.v1", STATUS_SCHEMA})
_WRITE_SCHEMAS: Final[frozenset[str]] = frozenset(
    {"phase7.fake-runner-write-classification.v1", WRITE_CLASSIFICATION_SCHEMA}
)
_EVIDENCE_SCHEMAS: Final[frozenset[str]] = frozenset({"phase7.fake-runner-evidence-packet.v1", EVIDENCE_PACKET_SCHEMA})
_ARTIFACT_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "status.json": ("status", "status.json"),
    "stdout.jsonl": ("stdout", "stdout.jsonl"),
    "normalized-events.jsonl": ("normalized_events", "normalized-events.jsonl"),
    "final.md": ("final", "final.md"),
    "write-classification.json": ("write_classification", "write-classification.json"),
    "evidence-packet.json": ("evidence_packet", "evidence-packet.json"),
}
_PROVIDER_ATTEMPT_FLAG_KEYS: Final[frozenset[str]] = frozenset(
    {
        "http_request_attempted",
        "network_attempted",
        "network_used",
        "provider_cli_argv_recorded",
        "provider_launched",
        "raw_provider_output_recorded",
        "subprocess_invoked",
    }
)
_PROVIDER_ATTEMPT_COUNT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "http_request_attempt_count",
        "network_attempt_count",
        "network_attempts",
        "provider_subprocess_attempt_count",
        "provider_subprocess_attempts",
    }
)
_ALLOWED_FLAG_FIELD_NAMES: Final[frozenset[str]] = frozenset(
    {
        "httprequestattempted",
        "networkattempted",
        "networkused",
        "providercliargvrecorded",
        "providerlaunched",
        "rawprovideroutputrecorded",
        "subprocessinvoked",
    }
)
_FORBIDDEN_RAW_FIELD_NAMES: Final[frozenset[str]] = frozenset(
    {
        "accountemail",
        "accountidentifier",
        "accountid",
        "args",
        "arguments",
        "argv",
        "authfile",
        "authheader",
        "authpath",
        "authorization",
        "commandargv",
        "credentialfile",
        "credentialpath",
        "env",
        "envdump",
        "environ",
        "environment",
        "environmentvariables",
        "fullargv",
        "fullenv",
        "homepath",
        "localpath",
        "privatekey",
        "privatepath",
        "processargv",
        "processenv",
        "providerargv",
        "providerenv",
        "provideroutput",
        "providerresponse",
        "providerstderr",
        "providerstdout",
        "rawauth",
        "rawenv",
        "rawoutput",
        "rawpath",
        "rawprompt",
        "rawprovideroutput",
        "rawproviderresponse",
        "rawstderr",
        "rawstdout",
        "rawtranscript",
        "realpath",
        "stderr",
        "transcript",
    }
)
_FORBIDDEN_RAW_FIELD_MARKERS: Final[tuple[str, ...]] = (
    "accountidentifier",
    "argvdump",
    "authheader",
    "authmaterial",
    "envdump",
    "provideroutput",
    "providerresponse",
    "providerstderr",
    "providerstdout",
    "rawauth",
    "rawenv",
    "rawprompt",
    "rawprovider",
    "rawstderr",
    "rawstdout",
    "rawtranscript",
    "secretfile",
    "secretpath",
    "stderrtext",
    "stdouttext",
    "transcripttext",
)


@dataclass(frozen=True, slots=True)
class SidecarSchemaFailure:
    sidecar: str
    failure_class: str
    field: str
    severity: str = "invalid_evidence"
    repairability_class: str = "fixture_repair_required"

    def to_payload(self) -> dict[str, str]:
        return {
            "sidecar": self.sidecar,
            "failure_class": self.failure_class,
            "field": self.field,
            "severity": self.severity,
            "repairability_class": self.repairability_class,
        }


class SidecarSchemaError(ValueError):
    """Raised when a sidecar bundle has class-only schema failures."""

    def __init__(self, failures: Sequence[SidecarSchemaFailure]) -> None:
        self.failures = tuple(failures)
        failure_classes = ", ".join(sorted({failure.failure_class for failure in self.failures}))
        super().__init__(f"sidecar bundle validation failed: {failure_classes}")


@dataclass(frozen=True, slots=True)
class SidecarBundle:
    schema: str
    row_id: str
    row_root: Path
    required_artifacts: tuple[str, ...]
    sidecar_statuses: dict[str, str]
    status: dict[str, object]
    stdout_events: tuple[dict[str, object], ...]
    normalized_events: tuple[dict[str, object], ...]
    write_classification: dict[str, object]
    evidence_packet: dict[str, object]
    provider_free: bool = True
    schema_failures: tuple[SidecarSchemaFailure, ...] = ()

    def to_class_only_payload(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "row_id": self.row_id,
            "required_artifacts": list(self.required_artifacts),
            "sidecar_statuses": dict(self.sidecar_statuses),
            "provider_free": self.provider_free,
            "schema_failures": [failure.to_payload() for failure in self.schema_failures],
        }


def validate_sidecar_bundle(row_root: Path, row_contract: object) -> SidecarBundle:
    """Validate the six fake/live-audit sidecars as one provider-free bundle."""

    bundle, failures = _load_sidecar_bundle(row_root, row_contract)
    if failures:
        raise SidecarSchemaError(failures)
    return bundle


def collect_sidecar_schema_failures(row_root: Path, row_contract: object) -> tuple[SidecarSchemaFailure, ...]:
    """Return class-only validation failures without raising."""

    _bundle, failures = _load_sidecar_bundle(row_root, row_contract)
    return failures


def validate_status_payload(payload: Mapping[str, object], *, row_id: str) -> dict[str, object]:
    failures: list[SidecarSchemaFailure] = []
    status = dict(payload)
    _validate_schema_version(status, allowed=_STATUS_SCHEMAS, sidecar="status.json", failures=failures)
    _validate_payload_row_id(status, expected_row_id=row_id, sidecar="status.json", failures=failures)
    _validate_provider_free_payload(status, sidecar="status.json", failures=failures)
    _scan_raw_fields(status, sidecar="status.json", failures=failures)
    if failures:
        raise SidecarSchemaError(failures)
    return status


def validate_normalized_event_record(
    payload: Mapping[str, object], *, row_id: str, line_number: int
) -> dict[str, object]:
    failures: list[SidecarSchemaFailure] = []
    event = dict(payload)
    _validate_optional_record_row_id(
        event,
        expected_row_id=row_id,
        sidecar="normalized-events.jsonl",
        field=f"line[{line_number}].row_id",
        failures=failures,
    )
    _scan_raw_fields(event, sidecar="normalized-events.jsonl", failures=failures)
    if failures:
        raise SidecarSchemaError(failures)
    return event


def validate_write_classification_payload(
    payload: Mapping[str, object],
    *,
    row_id: str,
    write_policy: Mapping[str, object] | None = None,
) -> dict[str, object]:
    failures: list[SidecarSchemaFailure] = []
    write_classification = dict(payload)
    _validate_schema_version(
        write_classification,
        allowed=_WRITE_SCHEMAS,
        sidecar="write-classification.json",
        failures=failures,
    )
    _validate_payload_row_id(
        write_classification, expected_row_id=row_id, sidecar="write-classification.json", failures=failures
    )
    _validate_provider_free_payload(write_classification, sidecar="write-classification.json", failures=failures)
    _scan_raw_fields(write_classification, sidecar="write-classification.json", failures=failures)
    _validate_reserved_write_records(write_classification, failures=failures)
    _ = write_policy
    if failures:
        raise SidecarSchemaError(failures)
    return write_classification


def validate_evidence_packet_payload(
    payload: Mapping[str, object],
    *,
    row_id: str,
    required_artifacts: Sequence[str] = REQUIRED_SIDECARS,
) -> dict[str, object]:
    failures: list[SidecarSchemaFailure] = []
    evidence_packet = dict(payload)
    _validate_schema_version(
        evidence_packet,
        allowed=_EVIDENCE_SCHEMAS,
        sidecar="evidence-packet.json",
        failures=failures,
    )
    _validate_payload_row_id(evidence_packet, expected_row_id=row_id, sidecar="evidence-packet.json", failures=failures)
    _validate_provider_free_payload(evidence_packet, sidecar="evidence-packet.json", failures=failures)
    _scan_raw_fields(evidence_packet, sidecar="evidence-packet.json", failures=failures)
    _ = tuple(required_artifacts)
    if failures:
        raise SidecarSchemaError(failures)
    return evidence_packet


def _load_sidecar_bundle(
    row_root: Path, row_contract: object
) -> tuple[SidecarBundle, tuple[SidecarSchemaFailure, ...]]:
    failures: list[SidecarSchemaFailure] = []
    row_root = row_root.resolve(strict=False)
    expected_row_id = _row_contract_id(row_contract) or row_root.name
    required_artifacts = _required_artifacts(row_contract)

    _validate_row_contract_provider_free(row_contract, failures)
    sidecar_statuses = _validate_required_files(row_root, failures)

    status = _read_json_sidecar(row_root / "status.json", "status.json", failures)
    write_classification = _read_json_sidecar(
        row_root / "write-classification.json", "write-classification.json", failures
    )
    evidence_packet = _read_json_sidecar(row_root / "evidence-packet.json", "evidence-packet.json", failures)
    stdout_events = _read_jsonl_sidecar(row_root / "stdout.jsonl", "stdout.jsonl", expected_row_id, failures)
    normalized_events = _read_jsonl_sidecar(
        row_root / "normalized-events.jsonl", "normalized-events.jsonl", expected_row_id, failures
    )

    if status:
        _validate_schema_version(status, allowed=_STATUS_SCHEMAS, sidecar="status.json", failures=failures)
        _validate_payload_row_id(status, expected_row_id=expected_row_id, sidecar="status.json", failures=failures)
        _validate_provider_free_payload(status, sidecar="status.json", failures=failures)
        _scan_raw_fields(status, sidecar="status.json", failures=failures)

    if write_classification:
        _validate_schema_version(
            write_classification,
            allowed=_WRITE_SCHEMAS,
            sidecar="write-classification.json",
            failures=failures,
        )
        _validate_payload_row_id(
            write_classification,
            expected_row_id=expected_row_id,
            sidecar="write-classification.json",
            failures=failures,
        )
        _validate_provider_free_payload(write_classification, sidecar="write-classification.json", failures=failures)
        _scan_raw_fields(write_classification, sidecar="write-classification.json", failures=failures)
        _validate_write_paths(write_classification, row_root=row_root, failures=failures)
        _validate_reserved_write_records(write_classification, failures=failures)

    if evidence_packet:
        _validate_schema_version(
            evidence_packet,
            allowed=_EVIDENCE_SCHEMAS,
            sidecar="evidence-packet.json",
            failures=failures,
        )
        _validate_payload_row_id(
            evidence_packet,
            expected_row_id=expected_row_id,
            sidecar="evidence-packet.json",
            failures=failures,
        )
        _validate_provider_free_payload(evidence_packet, sidecar="evidence-packet.json", failures=failures)
        _scan_raw_fields(evidence_packet, sidecar="evidence-packet.json", failures=failures)
        _validate_evidence_paths(
            evidence_packet, row_root=row_root, required_artifacts=required_artifacts, failures=failures
        )

    for sidecar, events in (("stdout.jsonl", stdout_events), ("normalized-events.jsonl", normalized_events)):
        for line_number, event in enumerate(events, start=1):
            _validate_optional_record_row_id(
                event,
                expected_row_id=expected_row_id,
                sidecar=sidecar,
                field=f"line[{line_number}].row_id",
                failures=failures,
            )
            _scan_raw_fields(event, sidecar=sidecar, failures=failures)

    bundle = SidecarBundle(
        schema=SIDECAR_BUNDLE_SCHEMA,
        row_id=expected_row_id,
        row_root=row_root,
        required_artifacts=required_artifacts,
        sidecar_statuses=sidecar_statuses,
        status=status,
        stdout_events=tuple(stdout_events),
        normalized_events=tuple(normalized_events),
        write_classification=write_classification,
        evidence_packet=evidence_packet,
        provider_free=True,
        schema_failures=tuple(failures),
    )
    return bundle, tuple(failures)


def _validate_required_files(row_root: Path, failures: list[SidecarSchemaFailure]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    if not row_root.is_dir():
        _add_failure(failures, "row_root", "missing_row_root", "row_root")
    for sidecar in REQUIRED_SIDECARS:
        path = row_root / sidecar
        if not path.exists():
            statuses[sidecar] = "missing"
            _add_failure(failures, sidecar, "missing_required_sidecar", sidecar)
            continue
        if not path.is_file():
            statuses[sidecar] = "invalid"
            _add_failure(failures, sidecar, "invalid_sidecar_type", sidecar)
            continue
        try:
            resolved = path.resolve(strict=True)
        except OSError:
            statuses[sidecar] = "invalid"
            _add_failure(failures, sidecar, "invalid_path", sidecar)
            continue
        if not _is_relative_to(resolved, row_root):
            statuses[sidecar] = "invalid"
            _add_failure(failures, sidecar, "row_root_escape", sidecar)
            continue
        if sidecar == "final.md" and path.stat().st_size > MAX_FINAL_BYTES:
            statuses[sidecar] = "invalid"
            _add_failure(failures, sidecar, "final_too_large", sidecar)
            continue
        statuses[sidecar] = "present"
    return statuses


def _read_json_sidecar(path: Path, sidecar: str, failures: list[SidecarSchemaFailure]) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (JSONDecodeError, OSError, UnicodeDecodeError):
        _add_failure(failures, sidecar, "malformed_json", sidecar)
        return {}
    if not isinstance(payload, Mapping):
        _add_failure(failures, sidecar, "malformed_json", sidecar)
        return {}
    return dict(cast(Mapping[str, object], payload))


def _read_jsonl_sidecar(
    path: Path,
    sidecar: str,
    expected_row_id: str,
    failures: list[SidecarSchemaFailure],
) -> list[dict[str, object]]:
    if not path.is_file():
        return []
    records: list[dict[str, object]] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except JSONDecodeError:
                    _add_failure(failures, sidecar, "malformed_jsonl", f"line[{line_number}]")
                    continue
                if not isinstance(payload, Mapping):
                    _add_failure(failures, sidecar, "malformed_jsonl", f"line[{line_number}]")
                    continue
                record = dict(cast(Mapping[str, object], payload))
                _validate_optional_record_row_id(
                    record,
                    expected_row_id=expected_row_id,
                    sidecar=sidecar,
                    field=f"line[{line_number}].row_id",
                    failures=failures,
                )
                records.append(record)
    except (OSError, UnicodeDecodeError):
        _add_failure(failures, sidecar, "malformed_jsonl", sidecar)
    if not records:
        _add_failure(failures, sidecar, "malformed_jsonl", "empty")
    return records


def _validate_schema_version(
    payload: Mapping[str, object],
    *,
    allowed: frozenset[str],
    sidecar: str,
    failures: list[SidecarSchemaFailure],
) -> None:
    schema_version = payload.get("schema_version")
    if not isinstance(schema_version, str) or schema_version not in allowed:
        _add_failure(failures, sidecar, "invalid_schema_version", "schema_version")


def _validate_payload_row_id(
    payload: Mapping[str, object],
    *,
    expected_row_id: str,
    sidecar: str,
    failures: list[SidecarSchemaFailure],
) -> None:
    row_id = payload.get("row_id")
    if row_id != expected_row_id:
        _add_failure(failures, sidecar, "row_id_mismatch", "row_id")


def _validate_optional_record_row_id(
    payload: Mapping[str, object],
    *,
    expected_row_id: str,
    sidecar: str,
    field: str,
    failures: list[SidecarSchemaFailure],
) -> None:
    row_id = payload.get("row_id")
    if row_id is not None and row_id != expected_row_id:
        _add_failure(failures, sidecar, "row_id_mismatch", field)


def _validate_provider_free_payload(
    payload: Mapping[str, object], *, sidecar: str, failures: list[SidecarSchemaFailure]
) -> None:
    for key in _PROVIDER_ATTEMPT_FLAG_KEYS:
        value = payload.get(key)
        if value is True:
            _add_failure(failures, sidecar, "provider_free_violation", key)
    for key in _PROVIDER_ATTEMPT_COUNT_KEYS:
        value = payload.get(key)
        if isinstance(value, int) and value > 0:
            _add_failure(failures, sidecar, "provider_free_violation", key)


def _validate_row_contract_provider_free(row_contract: object, failures: list[SidecarSchemaFailure]) -> None:
    launch_policy = _as_string(_read(row_contract, "launch_policy"), default="")
    default_pytest = _read(row_contract, "default_pytest")
    if launch_policy != "fake" and default_pytest is not True:
        return
    provider_allowed = _read(row_contract, "provider_subprocess_allowed")
    network_allowed = _read(row_contract, "network_allowed")
    if provider_allowed is True:
        _add_failure(failures, "row_contract", "provider_free_violation", "provider_subprocess_allowed")
    if network_allowed is True:
        _add_failure(failures, "row_contract", "provider_free_violation", "network_allowed")
    if LIVE_PROVIDER_MARKER in _string_items(_read(row_contract, "required_pytest_markers")):
        _add_failure(failures, "row_contract", "provider_free_violation", "required_pytest_markers")


def _scan_raw_fields(
    value: object,
    *,
    sidecar: str,
    failures: list[SidecarSchemaFailure],
    field: str = "",
) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_string = str(key)
            child_field = f"{field}.{key_string}" if field else key_string
            normalized_key = _normalize_key(key_string)
            if _is_forbidden_raw_key(normalized_key):
                _add_failure(failures, sidecar, "raw_field_forbidden", child_field)
            _scan_raw_fields(item, sidecar=sidecar, failures=failures, field=child_field)
    elif _is_sequence(value):
        for index, item in enumerate(value):
            _scan_raw_fields(item, sidecar=sidecar, failures=failures, field=f"{field}[{index}]")


def _is_forbidden_raw_key(normalized_key: str) -> bool:
    if normalized_key in _ALLOWED_FLAG_FIELD_NAMES:
        return False
    return normalized_key in _FORBIDDEN_RAW_FIELD_NAMES or any(
        marker in normalized_key for marker in _FORBIDDEN_RAW_FIELD_MARKERS
    )


def _validate_write_paths(
    write_classification: Mapping[str, object],
    *,
    row_root: Path,
    failures: list[SidecarSchemaFailure],
) -> None:
    for index, record in enumerate(_mapping_sequence(write_classification.get("writes"))):
        relative_path = record.get("relative_path")
        if isinstance(relative_path, str):
            _validate_relative_path(
                relative_path, "write-classification.json", f"writes[{index}].relative_path", failures
            )
        resolved_path = record.get("resolved_path")
        if resolved_path is not None:
            _validate_contained_path(
                resolved_path,
                row_root=row_root,
                sidecar="write-classification.json",
                field=f"writes[{index}].resolved_path",
                failures=failures,
            )


def _validate_reserved_write_records(
    write_classification: Mapping[str, object], *, failures: list[SidecarSchemaFailure]
) -> None:
    for index, record in enumerate(_mapping_sequence(write_classification.get("writes"))):
        relative_path = record.get("relative_path")
        classification = record.get("classification")
        if (
            isinstance(relative_path, str)
            and _is_reserved_harness_sidecar(relative_path)
            and classification != "harness_log"
        ):
            _add_failure(
                failures,
                "write-classification.json",
                "reserved_harness_sidecar_write",
                f"writes[{index}].relative_path",
            )


def _validate_evidence_paths(
    evidence_packet: Mapping[str, object],
    *,
    row_root: Path,
    required_artifacts: Sequence[str],
    failures: list[SidecarSchemaFailure],
) -> None:
    row_root_value = evidence_packet.get("row_root")
    if row_root_value is not None:
        _validate_row_root_value(row_root_value, row_root=row_root, failures=failures)

    artifacts = _mapping(evidence_packet.get("artifacts"))
    for artifact_name in required_artifacts:
        artifact_payload = _artifact_payload(artifacts, artifact_name)
        if not artifact_payload:
            _add_failure(failures, "evidence-packet.json", "artifact_missing", f"artifacts.{artifact_name}")
            continue
        if artifact_payload.get("exists") is not True:
            _add_failure(failures, "evidence-packet.json", "artifact_missing", f"artifacts.{artifact_name}.exists")
        _validate_artifact_location(artifact_payload, artifact_name=artifact_name, row_root=row_root, failures=failures)


def _validate_artifact_location(
    artifact_payload: Mapping[str, object],
    *,
    artifact_name: str,
    row_root: Path,
    failures: list[SidecarSchemaFailure],
) -> None:
    location = artifact_payload.get("path", artifact_payload.get("artifact_ref"))
    if location is None:
        return
    if not isinstance(location, str) or not location:
        _add_failure(failures, "evidence-packet.json", "invalid_path", f"artifacts.{artifact_name}.path")
        return
    if Path(location).name != artifact_name:
        _add_failure(failures, "evidence-packet.json", "invalid_path", f"artifacts.{artifact_name}.path")
        return
    _validate_contained_path(
        location,
        row_root=row_root,
        sidecar="evidence-packet.json",
        field=f"artifacts.{artifact_name}.path",
        failures=failures,
    )


def _artifact_payload(artifacts: Mapping[str, object], artifact_name: str) -> Mapping[str, object]:
    for key in _ARTIFACT_ALIASES.get(artifact_name, (artifact_name,)):
        payload = artifacts.get(key)
        if isinstance(payload, Mapping):
            return cast(Mapping[str, object], payload)
    return {}


def _validate_row_root_value(value: object, *, row_root: Path, failures: list[SidecarSchemaFailure]) -> None:
    if not isinstance(value, str) or not value:
        _add_failure(failures, "evidence-packet.json", "invalid_path", "row_root")
        return
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = row_root / candidate
    if candidate.resolve(strict=False) != row_root:
        _add_failure(failures, "evidence-packet.json", "row_root_escape", "row_root")


def _validate_contained_path(
    value: object,
    *,
    row_root: Path,
    sidecar: str,
    field: str,
    failures: list[SidecarSchemaFailure],
) -> None:
    if not isinstance(value, str) or not value:
        _add_failure(failures, sidecar, "invalid_path", field)
        return
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = row_root / candidate
    resolved = candidate.resolve(strict=False)
    if not _is_relative_to(resolved, row_root):
        _add_failure(failures, sidecar, "row_root_escape", field)


def _validate_relative_path(
    value: str,
    sidecar: str,
    field: str,
    failures: list[SidecarSchemaFailure],
) -> None:
    path = Path(value)
    if path.is_absolute() or any(part == ".." for part in path.parts) or value.startswith("~/"):
        _add_failure(failures, sidecar, "invalid_path", field)


def _required_artifacts(row_contract: object) -> tuple[str, ...]:
    declared = tuple(_string_items(_read(row_contract, "required_artifacts")))
    if not declared:
        return REQUIRED_SIDECARS
    merged = [*declared]
    for artifact in REQUIRED_SIDECARS:
        if artifact not in merged:
            merged.append(artifact)
    return tuple(artifact for artifact in merged if artifact in REQUIRED_ARTIFACTS or artifact in REQUIRED_SIDECARS)


def _row_contract_id(row_contract: object) -> str:
    return _as_string(_read(row_contract, "row_id", "scenario_run_id", "run_id"), default="")


def _read(source: object, *keys: str) -> object:
    for key in keys:
        if isinstance(source, Mapping) and key in source:
            return source[key]
        if hasattr(source, key):
            return getattr(source, key)
    return None


def _mapping(value: object | None) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _mapping_sequence(value: object | None) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return ()
    return tuple(cast(Mapping[str, object], item) for item in value if isinstance(item, Mapping))


def _string_items(value: object | None) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _as_string(value: object | None, *, default: str) -> str:
    return value if isinstance(value, str) and value else default


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray)


def _is_reserved_harness_sidecar(value: str) -> bool:
    path = Path(value)
    return len(path.parts) == 1 and path.parts[0] in REQUIRED_SIDECARS


def _normalize_key(key: str) -> str:
    return "".join(character for character in key.lower() if character.isalnum())


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _add_failure(
    failures: list[SidecarSchemaFailure],
    sidecar: str,
    failure_class: str,
    field: str,
) -> None:
    failure = SidecarSchemaFailure(sidecar=sidecar, failure_class=failure_class, field=field)
    if failure not in failures:
        failures.append(failure)


__all__ = [
    "EVIDENCE_PACKET_SCHEMA",
    "JSON_SIDECARS",
    "JSONL_SIDECARS",
    "REQUIRED_SIDECARS",
    "SIDECAR_BUNDLE_SCHEMA",
    "STATUS_SCHEMA",
    "WRITE_CLASSIFICATION_SCHEMA",
    "SidecarBundle",
    "SidecarSchemaError",
    "SidecarSchemaFailure",
    "collect_sidecar_schema_failures",
    "validate_evidence_packet_payload",
    "validate_normalized_event_record",
    "validate_sidecar_bundle",
    "validate_status_payload",
    "validate_write_classification_payload",
]
