"""Shared facade for return validation, classification, and mutation gates."""

from __future__ import annotations

import re
from collections.abc import Mapping
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from gpd.core.return_contract import (
    VALID_RETURN_STATUSES,
    GpdReturnValidationResult,
    validate_gpd_return_markdown,
)

__all__ = [
    "ReturnGateFailure",
    "ReturnGateFailureClass",
    "ReturnGateFailureClassValue",
    "ReturnGateFailureStage",
    "ReturnGateResult",
    "classify_return_validation",
    "return_gate_failure_from_validation_error",
    "return_gate_from_repair_classification",
    "return_gate_from_validation_result",
    "validate_return_gate_markdown",
]


class ReturnGateFailureClass(StrEnum):
    """Stable failure classes for return gates and applicator routing."""

    RETURN_MISSING = "return_missing"
    RETURN_MALFORMED_REPAIRABLE = "return_malformed_repairable"
    RETURN_MALFORMED_BLOCKING = "return_malformed_blocking"
    ARTIFACT_MISSING = "artifact_missing"
    ARTIFACT_STALE = "artifact_stale"
    ARTIFACT_PATH_REPAIRABLE = "artifact_path_repairable"
    ARTIFACT_ROOT_BLOCKED = "artifact_root_blocked"
    VALIDATOR_FAILED = "validator_failed"
    APPLICATOR_FAILED = "applicator_failed"


ReturnGateFailureClassValue = Literal[
    "return_missing",
    "return_malformed_repairable",
    "return_malformed_blocking",
    "artifact_missing",
    "artifact_stale",
    "artifact_path_repairable",
    "artifact_root_blocked",
    "validator_failed",
    "applicator_failed",
]
ReturnGateFailureStage = Literal["return", "status", "artifact", "validator", "applicator"]


class ReturnGateFailure(BaseModel):
    """Structured detail for one return-gate failure."""

    failure_class: ReturnGateFailureClass
    code: str
    message: str
    path: str | None = None
    command: str | None = None
    repairable: bool = False
    stage: ReturnGateFailureStage = "return"
    source_class: str | None = None


class ReturnGateResult(BaseModel):
    """Common non-destructive result shape for return gates.

    ``accepted``/``accepted_for_success`` mean the return is schema-valid and
    matches the caller's required status. ``passed`` is the full invoked gate.
    Future artifact, validator, and applicator adapters can be stricter than
    acceptance without changing the return-level vocabulary.
    """

    passed: bool
    accepted: bool = False
    valid: bool = False
    schema_valid: bool = False
    status_accepted: bool = False
    accepted_for_success: bool = False
    safe_to_apply: bool = False
    mutates: bool = False
    mutated: bool = False

    primary_failure_class: ReturnGateFailureClass | None = None
    failure_classes: list[ReturnGateFailureClass] = Field(default_factory=list)
    failures: list[ReturnGateFailure] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    hints: list[str] = Field(default_factory=list)
    repair_hint: str | None = None

    primary_class: str | None = None
    primary_classification: str | None = None
    source_failure_classes: list[str] = Field(default_factory=list)
    recovery_route: str | None = None
    selected_route: str | None = None
    next_action_class: str | None = None

    status: str | None = None
    required_status: str | None = None
    fields: dict[str, object] = Field(default_factory=dict)
    files_written: list[str] = Field(default_factory=list)
    checked_files: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


_FENCED_BLOCK_RE = re.compile(r"```(?P<language>[^\n`]*)\n(?P<body>[\s\S]*?)```")
_RAW_GPD_RETURN_YAML_RE = re.compile(r"(?m)^\s*gpd_return\s*:")
_RAW_GPD_RETURN_JSON_RE = re.compile(r"""["']gpd_return["']\s*:""")
_UNWRAPPED_RETURN_YAML_RE = re.compile(r"(?m)^\s*(status|files_written|issues|next_actions)\s*:")

_TOP_LEVEL_SHAPE_MARKERS = (
    "expected a mapping",
    "missing top-level gpd_return key",
    "unexpected top-level key",
    "gpd_return must be a mapping",
)
_LIST_DRIFT_MARKERS = (
    "files_written must be a list",
    "issues must be a list",
    "next_actions must be a list",
    "approved_plans must be a list",
    "blocked_plans must be a list",
    "checkpoint_hashes must be a list",
    "decisions must be a list",
    "blockers must be a list",
    "Input should be a valid list",
)
_FIELD_SHAPE_MARKERS = (
    "must be a list",
    "must be a mapping",
    "must be a string",
    "must be a boolean",
    "must be a non-empty string",
    "not a number",
    "Input should be a valid",
)

_RICH_TO_GATE_CLASS: dict[str, ReturnGateFailureClass] = {
    "missing_block": ReturnGateFailureClass.RETURN_MISSING,
    "unfenced_candidate": ReturnGateFailureClass.RETURN_MALFORMED_REPAIRABLE,
    "wrong_fence_language": ReturnGateFailureClass.RETURN_MALFORMED_REPAIRABLE,
    "yaml_parse_error": ReturnGateFailureClass.RETURN_MALFORMED_REPAIRABLE,
    "top_level_shape_error": ReturnGateFailureClass.RETURN_MALFORMED_REPAIRABLE,
    "missing_required_fields": ReturnGateFailureClass.RETURN_MALFORMED_REPAIRABLE,
    "invalid_status": ReturnGateFailureClass.RETURN_MALFORMED_REPAIRABLE,
    "scalar_list_drift": ReturnGateFailureClass.RETURN_MALFORMED_REPAIRABLE,
    "field_shape_error": ReturnGateFailureClass.RETURN_MALFORMED_REPAIRABLE,
    "unknown_field": ReturnGateFailureClass.RETURN_MALFORMED_REPAIRABLE,
    "status_field_forbidden": ReturnGateFailureClass.RETURN_MALFORMED_BLOCKING,
    "transport_payload_in_return": ReturnGateFailureClass.RETURN_MALFORMED_BLOCKING,
    "applicator_owned_metadata": ReturnGateFailureClass.RETURN_MALFORMED_BLOCKING,
    "continuation_schema_error": ReturnGateFailureClass.RETURN_MALFORMED_BLOCKING,
    "valid_non_completed": ReturnGateFailureClass.RETURN_MALFORMED_BLOCKING,
    "ambiguous_multiple_returns": ReturnGateFailureClass.RETURN_MALFORMED_BLOCKING,
}
_REPAIRABLE_SOURCE_CLASSES = {
    "missing_block",
    "unfenced_candidate",
    "wrong_fence_language",
    "yaml_parse_error",
    "top_level_shape_error",
    "missing_required_fields",
    "invalid_status",
    "scalar_list_drift",
    "field_shape_error",
    "unknown_field",
}
_REPAIR_HINTS: dict[str, str] = {
    "valid": "The return envelope validates and is acceptable for the requested status.",
    "missing_block": "Retry the child with one fenced ```yaml block whose top-level key is gpd_return.",
    "unfenced_candidate": "Retry with the candidate return wrapped in a canonical ```yaml gpd_return block.",
    "wrong_fence_language": "Retry with the return in a yaml/yml fence, not a JSON or unlabeled fence.",
    "yaml_parse_error": "Retry with parseable YAML inside the fenced gpd_return block.",
    "top_level_shape_error": "Retry with exactly one top-level gpd_return mapping in the YAML block.",
    "missing_required_fields": "Retry with status, files_written, issues, and next_actions present.",
    "invalid_status": "Retry with one canonical lowercase status: completed, checkpoint, blocked, or failed.",
    "scalar_list_drift": "Retry with list-valued return fields encoded as YAML arrays or sequences.",
    "field_shape_error": "Retry with field values matching the return schema shape.",
    "unknown_field": "Retry after removing typo or callsite-owned top-level fields from gpd_return.",
    "status_field_forbidden": "Stop and surface the status/field mismatch; do not patch durable fields in place.",
    "transport_payload_in_return": "Stop and surface the transport payload; child returns must not carry execution segments.",
    "applicator_owned_metadata": "Stop and surface the applicator-owned metadata; the applicator must supply it.",
    "continuation_schema_error": "Stop and surface the continuation schema error before any durable application.",
    "valid_non_completed": "Route by the typed non-completed status instead of treating it as a malformed return.",
    "ambiguous_multiple_returns": "Retry with exactly one canonical gpd_return block.",
}


def validate_return_gate_markdown(
    content: str,
    *,
    required_status: str | None = "completed",
) -> ReturnGateResult:
    """Validate one raw markdown return and adapt it to the shared gate shape."""

    validation = validate_gpd_return_markdown(content)
    return classify_return_validation(validation, content=content, required_status=required_status)


def classify_return_validation(
    validation: GpdReturnValidationResult,
    *,
    content: str | None = None,
    required_status: str | None = "completed",
) -> ReturnGateResult:
    """Convert a strict return-contract validation result to ``ReturnGateResult``."""

    normalized_required_status = _normalize_required_status(required_status)
    warnings = list(validation.warnings)
    fields = dict(validation.fields)
    status = _status_from_fields(fields)

    if validation.passed:
        status_accepted = normalized_required_status is None or status == normalized_required_status
        if status_accepted:
            return ReturnGateResult(
                passed=True,
                accepted=True,
                valid=True,
                schema_valid=True,
                status_accepted=True,
                accepted_for_success=True,
                safe_to_apply=True,
                status=status,
                required_status=normalized_required_status,
                fields=fields,
                files_written=_files_written_from_fields(fields),
                warnings=warnings,
                primary_class="valid",
                primary_classification="valid",
            )

        message = f"gpd_return.status must be {normalized_required_status!r}, got {status!r}"
        failure = _failure_from_source_class(
            "valid_non_completed",
            code="required_status_mismatch",
            message=message,
            stage="status",
        )
        return _build_result(
            failures=[failure],
            errors=[message],
            warnings=warnings,
            schema_valid=True,
            status=status,
            required_status=normalized_required_status,
            fields=fields,
            files_written=_files_written_from_fields(fields),
            primary_class="valid_non_completed",
            primary_classification="valid_non_completed",
            source_failure_classes=["valid_non_completed"],
            hints=[_REPAIR_HINTS["valid_non_completed"]],
        )

    failures = [return_gate_failure_from_validation_error(error, content=content) for error in validation.errors]
    primary_source_class = failures[0].source_class if failures else "field_shape_error"
    hint = _REPAIR_HINTS.get(primary_source_class or "", _REPAIR_HINTS["field_shape_error"])
    return _build_result(
        failures=failures,
        errors=list(validation.errors),
        warnings=warnings,
        required_status=normalized_required_status,
        primary_class=primary_source_class,
        primary_classification=primary_source_class,
        source_failure_classes=_source_failure_classes(failures),
        hints=[hint],
    )


return_gate_from_validation_result = classify_return_validation


def return_gate_from_repair_classification(classification: object) -> ReturnGateResult:
    """Convert the existing repair-classifier result without importing it here."""

    primary_class = _string_or_none(_read_field(classification, "primary_class", None))
    primary_classification = _string_or_none(_read_field(classification, "primary_classification", primary_class))
    source_failure_classes = _string_list(_read_field(classification, "failure_classes", []))
    valid = bool(_read_field(classification, "valid", False))
    accepted_for_success = bool(_read_field(classification, "accepted_for_success", False))
    status = _string_or_none(_read_field(classification, "status", None))
    required_status = _string_or_none(_read_field(classification, "required_status", None))
    fields = _mapping_to_dict(_read_field(classification, "fields", {}))
    warnings = _string_list(_read_field(classification, "warnings", []))
    errors = _string_list(_read_field(classification, "errors", []))
    repair_hint = _string_or_none(_read_field(classification, "repair_hint", None))
    recovery_route = _string_or_none(_read_field(classification, "recovery_route", None))
    notes = _string_list(_read_field(classification, "notes", []))

    if primary_class == "valid":
        return ReturnGateResult(
            passed=True,
            accepted=True,
            valid=valid,
            schema_valid=valid,
            status_accepted=True,
            accepted_for_success=accepted_for_success,
            safe_to_apply=bool(_read_field(classification, "safe_to_apply", accepted_for_success)),
            status=status,
            required_status=required_status,
            fields=fields,
            files_written=_files_written_from_fields(fields),
            warnings=warnings,
            hints=[repair_hint] if repair_hint else [],
            repair_hint=repair_hint,
            primary_class=primary_class,
            primary_classification=primary_classification,
            source_failure_classes=source_failure_classes,
            recovery_route=recovery_route,
            notes=notes,
        )

    source_class = primary_classification or primary_class or "field_shape_error"
    code = "required_status_mismatch" if source_class == "valid_non_completed" else source_class
    message = _repair_failure_message(
        source_class,
        status=status,
        required_status=required_status,
        errors=errors,
    )
    failure = _failure_from_source_class(source_class, code=code, message=message)
    if source_class == "valid_non_completed":
        failure.stage = "status"
    result_errors = errors or [message]
    hint = repair_hint or _REPAIR_HINTS.get(source_class)

    return _build_result(
        failures=[failure],
        errors=result_errors,
        warnings=warnings,
        schema_valid=valid,
        status=status,
        required_status=required_status,
        fields=fields,
        files_written=_files_written_from_fields(fields),
        primary_class=primary_class,
        primary_classification=primary_classification,
        source_failure_classes=source_failure_classes or [source_class],
        hints=[hint] if hint else [],
        repair_hint=hint,
        recovery_route=recovery_route,
        notes=notes,
    )


def return_gate_failure_from_validation_error(
    error: str,
    *,
    content: str | None = None,
) -> ReturnGateFailure:
    """Map one strict validation error to a shared return-gate failure."""

    source_class = _source_class_from_validation_error(error, content=content)
    return _failure_from_source_class(source_class, message=error)


def _normalize_required_status(status: str | None) -> str | None:
    if status is None:
        return None
    normalized = status.strip()
    if normalized not in VALID_RETURN_STATUSES:
        allowed = ", ".join(sorted(VALID_RETURN_STATUSES))
        raise ValueError(f"required status must be one of: {allowed}")
    return normalized


def _build_result(
    *,
    failures: list[ReturnGateFailure],
    errors: list[str],
    warnings: list[str],
    schema_valid: bool = False,
    status: str | None = None,
    required_status: str | None = None,
    fields: dict[str, object] | None = None,
    files_written: list[str] | None = None,
    primary_class: str | None = None,
    primary_classification: str | None = None,
    source_failure_classes: list[str] | None = None,
    hints: list[str] | None = None,
    repair_hint: str | None = None,
    recovery_route: str | None = None,
    notes: list[str] | None = None,
) -> ReturnGateResult:
    failure_classes = _failure_classes(failures)
    status_accepted = schema_valid and not failures
    return ReturnGateResult(
        passed=False,
        accepted=False,
        valid=schema_valid,
        schema_valid=schema_valid,
        status_accepted=status_accepted,
        accepted_for_success=False,
        safe_to_apply=False,
        primary_failure_class=failure_classes[0] if failure_classes else None,
        failure_classes=failure_classes,
        failures=failures,
        errors=errors,
        warnings=warnings,
        hints=hints or [],
        repair_hint=repair_hint or ((hints or [None])[0]),
        primary_class=primary_class,
        primary_classification=primary_classification,
        source_failure_classes=source_failure_classes or [],
        recovery_route=recovery_route,
        status=status,
        required_status=required_status,
        fields=fields or {},
        files_written=files_written or [],
        notes=notes or [],
    )


def _failure_from_source_class(
    source_class: str,
    *,
    message: str,
    code: str | None = None,
    stage: ReturnGateFailureStage = "return",
) -> ReturnGateFailure:
    failure_class = _RICH_TO_GATE_CLASS.get(source_class, ReturnGateFailureClass.RETURN_MALFORMED_REPAIRABLE)
    return ReturnGateFailure(
        failure_class=failure_class,
        code=code or source_class,
        message=message,
        repairable=source_class in _REPAIRABLE_SOURCE_CLASSES,
        stage=stage,
        source_class=source_class,
    )


def _failure_classes(failures: list[ReturnGateFailure]) -> list[ReturnGateFailureClass]:
    classes: list[ReturnGateFailureClass] = []
    for failure in failures:
        if failure.failure_class not in classes:
            classes.append(failure.failure_class)
    return classes


def _source_failure_classes(failures: list[ReturnGateFailure]) -> list[str]:
    classes: list[str] = []
    for failure in failures:
        if failure.source_class and failure.source_class not in classes:
            classes.append(failure.source_class)
    return classes


def _source_class_from_validation_error(error: str, *, content: str | None) -> str:
    if error == "No gpd_return YAML block found":
        return _classify_missing_block(content or "")
    if error.startswith("Multiple gpd_return YAML blocks found:"):
        return "ambiguous_multiple_returns"
    if error.startswith("Missing required field:"):
        return "missing_required_fields"

    if "gpd_return YAML parse error" in error:
        if _contains_any(error, _TOP_LEVEL_SHAPE_MARKERS):
            return "top_level_shape_error"
        return "yaml_parse_error"
    if "canonical lowercase" in error or "Invalid status" in error or "status must be" in error:
        return "invalid_status"
    if "Unknown gpd_return top-level field" in error:
        return "unknown_field"
    if "status '" in error and "does not allow gpd_return field" in error:
        return "status_field_forbidden"
    if "execution_segment" in error:
        return "transport_payload_in_return"
    if "applicator-owned" in error:
        return "applicator_owned_metadata"
    if "continuation_update" in error or "bounded_segment" in error or "handoff" in error:
        return "continuation_schema_error"
    if _contains_any(error, _LIST_DRIFT_MARKERS):
        return "scalar_list_drift"
    if _contains_any(error, _FIELD_SHAPE_MARKERS):
        return "field_shape_error"
    return "field_shape_error"


def _classify_missing_block(content: str) -> str:
    for match in _FENCED_BLOCK_RE.finditer(content):
        language = match.group("language").strip().lower()
        body = match.group("body")
        if language in {"yaml", "yml"} and _looks_like_unwrapped_return_yaml(body):
            return "top_level_shape_error"
        if language not in {"yaml", "yml"} and _contains_gpd_return_candidate(body):
            return "wrong_fence_language"

    if _contains_gpd_return_candidate(content) or _looks_like_unwrapped_return_yaml(content):
        return "unfenced_candidate"
    return "missing_block"


def _contains_gpd_return_candidate(content: str) -> bool:
    return bool(_RAW_GPD_RETURN_YAML_RE.search(content) or _RAW_GPD_RETURN_JSON_RE.search(content))


def _looks_like_unwrapped_return_yaml(content: str) -> bool:
    found_fields = {match.group(1) for match in _UNWRAPPED_RETURN_YAML_RE.finditer(content)}
    return "status" in found_fields and bool(found_fields.intersection({"files_written", "issues", "next_actions"}))


def _contains_any(content: str, markers: tuple[str, ...]) -> bool:
    return any(marker in content for marker in markers)


def _status_from_fields(fields: Mapping[str, object]) -> str | None:
    status = fields.get("status")
    return status if isinstance(status, str) else None


def _files_written_from_fields(fields: Mapping[str, object]) -> list[str]:
    files_written = fields.get("files_written")
    if not isinstance(files_written, list):
        return []
    return [item for item in files_written if isinstance(item, str)]


def _repair_failure_message(
    source_class: str,
    *,
    status: str | None,
    required_status: str | None,
    errors: list[str],
) -> str:
    if source_class == "valid_non_completed":
        return f"gpd_return.status must be {required_status!r}, got {status!r}"
    if errors:
        return errors[0]
    return _REPAIR_HINTS.get(source_class, source_class)


def _read_field(value: object, field_name: str, default: object) -> object:
    if isinstance(value, Mapping):
        return value.get(field_name, default)
    return getattr(value, field_name, default)


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    raw = getattr(value, "value", value)
    return raw if isinstance(raw, str) else str(raw)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in (_string_or_none(item) for item in value) if item is not None]


def _mapping_to_dict(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}
