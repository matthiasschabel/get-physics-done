"""Read-only validation for child return/artifact handoff tuples."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from gpd.core.child_gate_snippets import ChildGateTuple, child_gate_tuple_from_payload
from gpd.core.handoff_artifacts import (
    HandoffArtifactValidationResult,
    HandoffFailure,
    HandoffFailureClass,
    validate_handoff_artifacts_markdown,
)

SafeChildHandoffValidatorId = Literal[
    "readable",
    "plan-contract",
    "plan-preflight",
    "proof-redteam",
    "summary-contract",
    "verification-contract",
    "verification-report",
    "paper-section-readable",
]

SAFE_CHILD_HANDOFF_VALIDATORS: frozenset[str] = frozenset(
    (
        "readable",
        "plan-contract",
        "plan-preflight",
        "proof-redteam",
        "summary-contract",
        "verification-contract",
        "verification-report",
        "paper-section-readable",
    )
)
"""Validator ids this wrapper may dispatch without evaluating shell text."""

_YAML_FENCE_RE = re.compile(r"```ya?ml\s*\n([\s\S]*?)```")


class ChildHandoffValidatorResult(BaseModel):
    """Result for one whitelisted child-handoff validator."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    validator_id: str
    passed: bool
    checked_files: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ChildHandoffValidationRequest(BaseModel):
    """Typed input for read-only child handoff validation."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True, extra="forbid")

    project_root: Path
    return_markdown: str
    gate: ChildGateTuple
    fresh_after: datetime | None = None


class ChildHandoffValidationResult(BaseModel):
    """Tuple-aware child handoff validation result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    passed: bool
    mutated: bool = False
    mutates: bool = False
    gate_id: str
    return_profile: str
    required_status: str
    status: str | None = None
    primary_failure_class: HandoffFailureClass | None = None
    failure_classes: list[HandoffFailureClass] = Field(default_factory=list)
    failures: list[HandoffFailure] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checked_files: list[str] = Field(default_factory=list)
    expected_artifacts: list[str] = Field(default_factory=list)
    expected_globs: list[str] = Field(default_factory=list)
    allowed_roots: list[str] = Field(default_factory=list)
    validator_results: list[ChildHandoffValidatorResult] = Field(default_factory=list)
    status_route: dict[str, str] = Field(default_factory=dict)
    failure_route: dict[str, str] = Field(default_factory=dict)
    selected_route: str
    next_action_class: str
    applicator_command: str = "none"
    applicator_ran: bool = False
    artifact_result: HandoffArtifactValidationResult


__all__ = [
    "SAFE_CHILD_HANDOFF_VALIDATORS",
    "ChildHandoffValidationRequest",
    "ChildHandoffValidationResult",
    "ChildHandoffValidatorResult",
    "parse_child_gate_markdown",
    "validate_child_handoff",
]


def parse_child_gate_markdown(content: str) -> ChildGateTuple:
    """Parse a raw or fenced YAML ``child_gate`` tuple."""

    for yaml_text in _candidate_yaml_payloads(content):
        try:
            payload = yaml.safe_load(yaml_text)
        except yaml.YAMLError:
            continue
        if not isinstance(payload, Mapping):
            continue
        if "child_gate" in payload or {"id", "role"} <= set(payload):
            return child_gate_tuple_from_payload(payload)
    raise ValueError("No child_gate YAML block found")


def validate_child_handoff(
    project_root: Path,
    return_markdown: str,
    gate: ChildGateTuple | Mapping[str, object] | str,
    *,
    fresh_after: datetime | None = None,
) -> ChildHandoffValidationResult:
    """Validate one child return against a callsite-owned child gate tuple.

    This helper is read-only. It validates artifacts and dispatches only named
    safe validators; it never evaluates validator strings as shell commands and
    never runs applicators.
    """

    gate_tuple = _coerce_gate(gate)
    request = ChildHandoffValidationRequest(
        project_root=project_root,
        return_markdown=return_markdown,
        gate=gate_tuple,
        fresh_after=fresh_after,
    )

    artifact_result = validate_handoff_artifacts_markdown(
        request.project_root,
        request.return_markdown,
        expected_artifacts=_expected_artifact_paths(gate_tuple),
        expected_globs=_expected_artifact_globs(gate_tuple),
        allowed_roots=list(gate_tuple.allowed_roots),
        require_files_written=any(artifact.required for artifact in gate_tuple.expected_artifacts),
        require_status=gate_tuple.required_status,
        fresh_after=request.fresh_after,
    )

    validator_results: list[ChildHandoffValidatorResult] = []
    validator_failures: list[HandoffFailure] = []
    validator_errors: list[str] = []
    validator_warnings: list[str] = []
    if artifact_result.passed:
        for raw_validator in gate_tuple.validators:
            normalized_validator = _safe_validator_id(raw_validator)
            if normalized_validator is None:
                continue
            if normalized_validator not in SAFE_CHILD_HANDOFF_VALIDATORS:
                message = (
                    f"unsupported child-handoff validator {raw_validator!r}; use a named safe validator id"
                )
                validator_failures.append(
                    _handoff_failure(
                        HandoffFailureClass.VALIDATOR_FAILED,
                        "unsupported_validator",
                        message,
                        command=raw_validator,
                    )
                )
                validator_errors.append(message)
                validator_results.append(
                    ChildHandoffValidatorResult(
                        validator_id=raw_validator,
                        passed=False,
                        errors=[message],
                    )
                )
                continue

            validator_result = _run_safe_validator(
                request.project_root,
                normalized_validator,
                artifact_result.checked_files,
            )
            validator_results.append(validator_result)
            if not validator_result.passed:
                validator_errors.extend(validator_result.errors)
                validator_warnings.extend(validator_result.warnings)
                validator_failures.append(
                    _handoff_failure(
                        HandoffFailureClass.VALIDATOR_FAILED,
                        f"{normalized_validator}_failed",
                        "; ".join(validator_result.errors) or f"{normalized_validator} failed",
                        command=normalized_validator,
                    )
                )

    failures = [*artifact_result.failures, *validator_failures]
    failure_classes = _failure_classes(failures)
    passed = artifact_result.passed and not validator_failures
    warnings = [*artifact_result.warnings, *validator_warnings]
    if gate_tuple.applicator.command != "none":
        warnings.append(
            f"child-handoff validation is read-only; applicator {gate_tuple.applicator.command!r} was not run"
        )

    selected_route = _selected_route(gate_tuple, passed=passed, status=artifact_result.status, failures=failures)
    return ChildHandoffValidationResult(
        passed=passed,
        gate_id=gate_tuple.id,
        return_profile=gate_tuple.return_profile,
        required_status=gate_tuple.required_status,
        status=artifact_result.status,
        primary_failure_class=failure_classes[0] if failure_classes else None,
        failure_classes=failure_classes,
        failures=failures,
        errors=[*artifact_result.errors, *validator_errors],
        warnings=warnings,
        checked_files=list(artifact_result.checked_files),
        expected_artifacts=list(artifact_result.expected_artifacts),
        expected_globs=list(artifact_result.expected_globs),
        allowed_roots=list(artifact_result.allowed_roots),
        validator_results=validator_results,
        status_route=dict(gate_tuple.status_route),
        failure_route={failure_class.value: route for failure_class, route in gate_tuple.failure_route.items()},
        selected_route=selected_route,
        next_action_class=selected_route,
        applicator_command=gate_tuple.applicator.command,
        applicator_ran=False,
        artifact_result=artifact_result,
    )


def _coerce_gate(gate: ChildGateTuple | Mapping[str, object] | str) -> ChildGateTuple:
    if isinstance(gate, ChildGateTuple):
        return gate
    if isinstance(gate, str):
        return parse_child_gate_markdown(gate)
    return child_gate_tuple_from_payload(gate)


def _candidate_yaml_payloads(content: str) -> tuple[str, ...]:
    stripped = content.strip()
    candidates: list[str] = []
    if stripped:
        candidates.append(stripped)
    candidates.extend(match.group(1).strip() for match in _YAML_FENCE_RE.finditer(content))
    return tuple(candidates)


def _expected_artifact_paths(gate: ChildGateTuple) -> list[str]:
    return [
        artifact.path
        for artifact in gate.expected_artifacts
        if artifact.required and artifact.kind == "path" and artifact.must_be_named_in_files_written
    ]


def _expected_artifact_globs(gate: ChildGateTuple) -> list[str]:
    return [
        artifact.path
        for artifact in gate.expected_artifacts
        if artifact.required and artifact.kind == "glob" and artifact.must_be_named_in_files_written
    ]


def _safe_validator_id(raw_validator: str) -> str | None:
    normalized = raw_validator.strip()
    lowered = normalized.casefold()
    if not normalized or lowered in {"none", "n/a", "not_applicable"}:
        return None
    if lowered in SAFE_CHILD_HANDOFF_VALIDATORS:
        return lowered
    if lowered.startswith("gpd validate handoff-artifacts"):
        return None
    command_prefixes = {
        "gpd validate plan-contract": "plan-contract",
        "gpd validate plan-preflight": "plan-preflight",
        "gpd validate proof-redteam": "proof-redteam",
        "gpd validate summary-contract": "summary-contract",
        "gpd validate verification-contract": "verification-contract",
    }
    for prefix, validator_id in command_prefixes.items():
        if lowered.startswith(prefix):
            return validator_id
    return normalized


def _run_safe_validator(
    project_root: Path,
    validator_id: str,
    checked_files: list[str],
) -> ChildHandoffValidatorResult:
    root = project_root.expanduser().resolve(strict=False)
    targets = _validator_targets(validator_id, checked_files)
    if not targets:
        return ChildHandoffValidatorResult(
            validator_id=validator_id,
            passed=False,
            errors=[f"{validator_id} validator had no matching checked artifacts"],
        )

    errors: list[str] = []
    warnings: list[str] = []
    for relpath in targets:
        path = (root / relpath).resolve(strict=False)
        try:
            if validator_id in {"readable", "paper-section-readable"}:
                _validate_readable_text(path, relpath=relpath, require_non_empty=validator_id == "paper-section-readable")
            elif validator_id == "plan-contract":
                errors.extend(_frontmatter_errors(path, relpath=relpath, schema="plan"))
            elif validator_id == "plan-preflight":
                item_errors, item_warnings = _plan_preflight_messages(path, relpath=relpath)
                errors.extend(item_errors)
                warnings.extend(item_warnings)
            elif validator_id == "summary-contract":
                errors.extend(_frontmatter_errors(path, relpath=relpath, schema="summary"))
            elif validator_id in {"verification-contract", "verification-report"}:
                errors.extend(_verification_contract_errors(path, relpath=relpath))
            elif validator_id == "proof-redteam":
                errors.extend(_proof_redteam_errors(path, relpath=relpath, project_root=root))
            else:  # pragma: no cover - caller filters unsupported ids.
                errors.append(f"unsupported child-handoff validator {validator_id!r}")
        except OSError as exc:
            errors.append(f"{relpath}: validator read failed: {exc}")
        except ValueError as exc:
            errors.append(f"{relpath}: {exc}")

    return ChildHandoffValidatorResult(
        validator_id=validator_id,
        passed=not errors,
        checked_files=targets,
        errors=errors,
        warnings=warnings,
    )


def _validator_targets(validator_id: str, checked_files: list[str]) -> list[str]:
    if validator_id in {"readable", "paper-section-readable"}:
        return list(checked_files)
    suffixes_by_validator = {
        "plan-contract": ("-PLAN.md",),
        "plan-preflight": ("-PLAN.md",),
        "summary-contract": ("-SUMMARY.md", "SUMMARY.md"),
        "verification-contract": ("-VERIFICATION.md", "VERIFICATION.md"),
        "verification-report": ("-VERIFICATION.md", "VERIFICATION.md"),
        "proof-redteam": ("PROOF-REDTEAM.md",),
    }
    suffixes = suffixes_by_validator.get(validator_id, ())
    return [path for path in checked_files if path.endswith(suffixes)]


def _validate_readable_text(path: Path, *, relpath: str, require_non_empty: bool = False) -> None:
    text = path.read_text(encoding="utf-8")
    if require_non_empty and not text.strip():
        raise ValueError("artifact text is empty")


def _frontmatter_errors(path: Path, *, relpath: str, schema: str) -> list[str]:
    from gpd.core.frontmatter import validate_frontmatter

    validation = validate_frontmatter(path.read_text(encoding="utf-8"), schema, source_path=path)
    errors = [f"{relpath}: {error}" for error in validation.errors]
    errors.extend(f"{relpath}: missing required frontmatter field: {field}" for field in validation.missing)
    return errors


def _plan_preflight_messages(path: Path, *, relpath: str) -> tuple[list[str], list[str]]:
    from gpd.core.tool_preflight import build_plan_tool_preflight

    result = build_plan_tool_preflight(path)
    errors = [f"{relpath}: {error}" for error in result.errors]
    errors.extend(f"{relpath}: {condition}" for condition in result.blocking_conditions)
    warnings = [f"{relpath}: {warning}" for warning in result.warnings]
    if not result.passed and not errors:
        errors.append(f"{relpath}: plan preflight failed")
    return errors, warnings


def _verification_contract_errors(path: Path, *, relpath: str) -> list[str]:
    from gpd.core.correctness_validators import validate_verification_oracle_evidence
    from gpd.core.frontmatter import validate_frontmatter

    content = path.read_text(encoding="utf-8")
    schema_result = validate_frontmatter(content, "verification", source_path=path)
    oracle_result = validate_verification_oracle_evidence(content, source_path=path)
    errors = [f"{relpath}: {error}" for error in schema_result.errors]
    errors.extend(f"{relpath}: missing required frontmatter field: {field}" for field in schema_result.missing)
    errors.extend(f"{relpath}: {error}" for error in oracle_result.errors)
    return errors


def _proof_redteam_errors(path: Path, *, relpath: str, project_root: Path) -> list[str]:
    from gpd.core.proof_redteam import validate_proof_redteam_artifact

    result = validate_proof_redteam_artifact(path, project_root=project_root)
    if _validation_result_is_valid(result):
        return []
    if hasattr(result, "errors"):
        errors = result.errors
        if isinstance(errors, list | tuple):
            return [f"{relpath}: {error}" for error in errors]
    return [f"{relpath}: proof-redteam validator failed"]


def _validation_result_is_valid(result: object) -> bool:
    for field_name in ("valid", "passed"):
        if isinstance(result, Mapping) and isinstance(result.get(field_name), bool):
            return bool(result[field_name])
        value = getattr(result, field_name, None)
        if isinstance(value, bool):
            return value
    errors = result.get("errors") if isinstance(result, Mapping) else getattr(result, "errors", None)
    if isinstance(errors, list | tuple):
        return len(errors) == 0
    return True


def _handoff_failure(
    failure_class: HandoffFailureClass,
    code: str,
    message: str,
    *,
    command: str | None = None,
) -> HandoffFailure:
    return HandoffFailure(
        failure_class=failure_class,
        code=code,
        message=message,
        command=command,
        repairable=False,
    )


def _failure_classes(failures: list[HandoffFailure]) -> list[HandoffFailureClass]:
    classes: list[HandoffFailureClass] = []
    for failure in failures:
        if failure.failure_class not in classes:
            classes.append(failure.failure_class)
    return classes


def _selected_route(
    gate: ChildGateTuple,
    *,
    passed: bool,
    status: str | None,
    failures: list[HandoffFailure],
) -> str:
    if passed:
        return gate.status_route.get(status or "", "accept")
    failure_classes = _failure_classes(failures)
    if failure_classes:
        return gate.failure_route.get(failure_classes[0], "fail_closed")
    return "fail_closed"
