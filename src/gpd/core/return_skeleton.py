"""Role-aware skeleton renderer for canonical ``gpd_return`` envelopes."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

from gpd.core.return_contract import (
    ALLOWED_RETURN_EXTENSION_FIELDS,
    REQUIRED_RETURN_FIELDS,
    RETURN_ENVELOPE_STATUS_CONTRACTS,
    VALID_RETURN_STATUSES,
    GpdReturnEnvelope,
    validate_gpd_return_markdown,
)

__all__ = [
    "APPLICATOR_OWNED_METADATA_FIELDS",
    "GPD_RETURN_ROLE_PROFILES",
    "KNOWN_RETURN_FIELD_NAMES",
    "RETURN_STATUS_ORDER",
    "GpdReturnRoleProfile",
    "GpdReturnSkeleton",
    "build_gpd_return_skeleton",
    "list_gpd_return_profiles",
    "render_gpd_return_markdown",
    "render_gpd_return_yaml",
]


APPLICATOR_OWNED_METADATA_FIELDS: frozenset[str] = frozenset({"recorded_at", "recorded_by", "updated_at"})
"""Metadata assigned by the applicator/state layer, never by generated returns."""

KNOWN_RETURN_FIELD_NAMES: frozenset[str] = frozenset(GpdReturnEnvelope.model_fields) | ALLOWED_RETURN_EXTENSION_FIELDS
"""All top-level fields known to the canonical return contract."""

_STATUS_ORDER_SEED = ("completed", "checkpoint", "blocked", "failed")
RETURN_STATUS_ORDER: tuple[str, ...] = tuple(
    status for status in _STATUS_ORDER_SEED if status in VALID_RETURN_STATUSES
) + tuple(sorted(VALID_RETURN_STATUSES - set(_STATUS_ORDER_SEED)))
"""Stable display/test order for statuses, derived from the canonical status set."""

_STATUS_RESTRICTED_FIELDS: frozenset[str] = frozenset(
    field_name for contract in RETURN_ENVELOPE_STATUS_CONTRACTS.values() for field_name in contract.structured_fields
)
_CHECKPOINT_RESUME_FILE_REQUIRED = (
    "checkpoint applicator skeletons require resume_file with an existing continuation target supplied by the callsite"
)
_CHECKPOINT_INTENT_FIELD = "checkpoint_intent"
_CHECKPOINT_INTENT_UNAVAILABLE = (
    "checkpoint_intent skeletons require canonical return contract support from the checkpoint-intent applicator slice"
)


class GpdReturnRoleProfile(BaseModel):
    """Rendering hints for a role-specific ``gpd_return`` skeleton."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile_id: str
    agent_names: tuple[str, ...] = ()
    required_fields: tuple[str, ...] = REQUIRED_RETURN_FIELDS
    role_fields_by_status: dict[str, tuple[str, ...]]
    default_render_fields_by_status: dict[str, tuple[str, ...]]
    local_callsite_fields: tuple[str, ...] = ()


class GpdReturnSkeleton(BaseModel):
    """Typed payload for copy-safe return skeletons and future CLI output."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    profile_id: str
    status: str
    envelope: dict[str, object]
    yaml_payload: str
    markdown: str
    required_fields: list[str] = Field(default_factory=list)
    role_fields: list[str] = Field(default_factory=list)
    status_allowed_fields: list[str] = Field(default_factory=list)
    validation_commands: list[str] = Field(default_factory=list)
    authoring_rules: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    applicator_ready: bool = False


def build_gpd_return_skeleton(
    *,
    role: str,
    status: str = "completed",
    files_written: Iterable[str] = (),
    issues: Iterable[str] = (),
    next_actions: Iterable[str] = (),
    phase: str | None = None,
    plan: str | None = None,
    include_applicator_fields: bool = False,
    include_checkpoint_intent: bool = False,
    checkpoint_reason: str | None = None,
    checkpoint_waiting_reason: str | None = None,
    resume_file: str | None = None,
    project_root: str | Path | None = None,
    extra_fields: Mapping[str, object] | None = None,
) -> GpdReturnSkeleton:
    """Build a validated role-aware ``gpd_return`` skeleton.

    Profiles only choose conservative defaults for known return fields. The
    canonical envelope model remains the validation authority.
    """

    profile = _profile_for_role(role)
    normalized_status = _normalize_status(status)
    normalized_phase = _normalize_optional_text(phase, field_name="phase")
    normalized_plan = _normalize_optional_text(plan, field_name="plan")

    envelope: dict[str, object] = {
        "status": normalized_status,
        "files_written": _normalize_string_sequence(files_written, field_name="files_written"),
        "issues": _normalize_string_sequence(issues, field_name="issues"),
        "next_actions": _normalize_string_sequence(next_actions, field_name="next_actions"),
    }

    for field_name in profile.default_render_fields_by_status[normalized_status]:
        if field_name in REQUIRED_RETURN_FIELDS or field_name == "continuation_update":
            continue
        envelope[field_name] = _default_value_for_field(field_name, phase=normalized_phase, plan=normalized_plan)

    if normalized_phase is not None:
        _assert_field_can_be_rendered("phase", status=normalized_status)
        envelope["phase"] = normalized_phase
    if normalized_plan is not None:
        _assert_field_can_be_rendered("plan", status=normalized_status)
        envelope["plan"] = normalized_plan

    if extra_fields:
        for field_name, value in extra_fields.items():
            _assert_field_can_be_rendered(field_name, status=normalized_status)
            envelope[field_name] = value

    warnings: list[str] = []
    applicator_ready = False
    if include_applicator_fields and include_checkpoint_intent:
        raise ValueError("choose either checkpoint_intent or checkpoint applicator fields, not both")

    if include_applicator_fields:
        if normalized_status == "checkpoint":
            normalized_resume_file = _normalize_checkpoint_resume_file(resume_file, project_root=project_root)
            envelope["continuation_update"] = {
                "bounded_segment": _checkpoint_bounded_segment_payload(
                    normalized_resume_file,
                    phase=normalized_phase,
                    plan=normalized_plan,
                )
            }
            applicator_ready = True
        else:
            warnings.append("Applicator continuation fields are generated only for checkpoint skeletons.")
    elif include_checkpoint_intent:
        if normalized_status != "checkpoint":
            raise ValueError("checkpoint_intent skeletons require status 'checkpoint'")
        if not _contract_supports_checkpoint_intent():
            raise ValueError(_CHECKPOINT_INTENT_UNAVAILABLE)
        envelope[_CHECKPOINT_INTENT_FIELD] = _checkpoint_intent_payload(
            checkpoint_reason=checkpoint_reason,
            checkpoint_waiting_reason=checkpoint_waiting_reason,
            phase=normalized_phase,
            plan=normalized_plan,
        )
        warnings.append(
            "Checkpoint intent is child-authored pause intent; durable resume context must be supplied to the applicator."
        )
    elif normalized_status == "checkpoint":
        warnings.append(
            "Checkpoint envelope shape validates; add checkpoint_intent for child-owned pause intent or applicator fields for durable continuation."
        )

    payload = _validate_and_dump_envelope(envelope)
    yaml_payload = render_gpd_return_yaml(payload)
    markdown = render_gpd_return_markdown(payload)
    validation = validate_gpd_return_markdown(markdown)
    if not validation.passed:
        raise ValueError("rendered gpd_return skeleton failed canonical validation: " + "; ".join(validation.errors))

    warnings.extend(validation.warnings)
    return GpdReturnSkeleton(
        profile_id=profile.profile_id,
        status=normalized_status,
        envelope=payload,
        yaml_payload=yaml_payload,
        markdown=markdown,
        required_fields=list(REQUIRED_RETURN_FIELDS),
        role_fields=list(profile.role_fields_by_status[normalized_status]),
        status_allowed_fields=list(_fields_allowed_for_status(normalized_status)),
        validation_commands=_validation_commands(applicator_ready=applicator_ready),
        authoring_rules=_authoring_rules(),
        warnings=warnings,
        applicator_ready=applicator_ready,
    )


def render_gpd_return_yaml(envelope: Mapping[str, object]) -> str:
    """Render a canonical YAML payload with the required top-level key."""

    payload = _validate_and_dump_envelope(envelope)
    return (
        yaml.safe_dump(
            {"gpd_return": payload},
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=999999,
        ).rstrip()
        + "\n"
    )


def render_gpd_return_markdown(envelope: Mapping[str, object]) -> str:
    """Render a fenced Markdown ``gpd_return`` block."""

    return f"```yaml\n{render_gpd_return_yaml(envelope).rstrip()}\n```\n"


def list_gpd_return_profiles(*, role: str | None = None, status: str | None = None) -> dict[str, object]:
    """List role/status rendering metadata for CLI and prompt snippet surfaces."""

    normalized_role = _normalize_identifier(role, field_name="role") if role is not None else None
    if normalized_role is not None and normalized_role not in GPD_RETURN_ROLE_PROFILES:
        roles = ", ".join(sorted(GPD_RETURN_ROLE_PROFILES))
        raise ValueError(f"unknown gpd_return role profile '{role}'. Must be one of: {roles}")

    normalized_status = _normalize_status(status) if status is not None else None
    selected_statuses = [normalized_status] if normalized_status is not None else list(RETURN_STATUS_ORDER)

    profiles: list[dict[str, object]] = []
    for profile_id in sorted(GPD_RETURN_ROLE_PROFILES):
        if normalized_role is not None and profile_id != normalized_role:
            continue
        profile = GPD_RETURN_ROLE_PROFILES[profile_id]
        profiles.append(
            {
                "profile_id": profile.profile_id,
                "agent_names": list(profile.agent_names),
                "required_fields": list(profile.required_fields),
                "local_callsite_fields": list(profile.local_callsite_fields),
                "statuses": {
                    status_id: {
                        "role_fields": list(profile.role_fields_by_status[status_id]),
                        "default_render_fields": list(profile.default_render_fields_by_status[status_id]),
                    }
                    for status_id in selected_statuses
                },
            }
        )

    return {
        "profiles": profiles,
        "roles": sorted(GPD_RETURN_ROLE_PROFILES),
        "statuses": list(RETURN_STATUS_ORDER),
        "mutated": False,
        "mutates": False,
    }


def _profile_for_role(role: str) -> GpdReturnRoleProfile:
    normalized_role = _normalize_identifier(role, field_name="role")
    try:
        return GPD_RETURN_ROLE_PROFILES[normalized_role]
    except KeyError as exc:
        roles = ", ".join(sorted(GPD_RETURN_ROLE_PROFILES))
        raise ValueError(f"unknown gpd_return role profile '{role}'. Must be one of: {roles}") from exc


def _normalize_status(status: str) -> str:
    normalized = _normalize_identifier(status, field_name="status")
    if normalized not in VALID_RETURN_STATUSES:
        statuses = ", ".join(RETURN_STATUS_ORDER)
        raise ValueError(f"unknown gpd_return status '{status}'. Must be one of: {statuses}")
    return normalized


def _normalize_identifier(value: str, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip().lower()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def _normalize_optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def _normalize_string_sequence(values: Iterable[str], *, field_name: str) -> list[str]:
    if isinstance(values, str):
        raise ValueError(f"{field_name} must be an iterable of strings, not a string")

    normalized: list[str] = []
    for index, value in enumerate(values):
        if not isinstance(value, str):
            raise ValueError(f"{field_name}[{index}] must be a string")
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"{field_name}[{index}] must be a non-empty string")
        normalized.append(stripped)
    return normalized


def _normalize_checkpoint_resume_file(resume_file: str | None, *, project_root: str | Path | None) -> str:
    normalized = _normalize_optional_text(resume_file, field_name="resume_file")
    if normalized is None:
        raise ValueError(_CHECKPOINT_RESUME_FILE_REQUIRED)

    resume_path = Path(normalized)
    if resume_path.is_absolute():
        raise ValueError("checkpoint applicator resume_file must be project-relative")

    if project_root is not None:
        root = Path(project_root).resolve()
        resolved = (root / resume_path).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError("checkpoint applicator resume_file must stay inside the project root") from exc
        if not resolved.is_file():
            raise ValueError("checkpoint applicator resume_file must point to an existing project file")

    return normalized


def _checkpoint_bounded_segment_payload(resume_file: str, *, phase: str | None, plan: str | None) -> dict[str, object]:
    payload: dict[str, object] = {
        "resume_file": resume_file,
        "segment_status": "paused",
    }
    if phase is not None:
        payload["phase"] = phase
    if plan is not None:
        payload["plan"] = plan
    return payload


def _checkpoint_intent_payload(
    *,
    checkpoint_reason: str | None,
    checkpoint_waiting_reason: str | None,
    phase: str | None,
    plan: str | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "checkpoint_reason": _normalize_optional_text(checkpoint_reason, field_name="checkpoint_reason")
        or "checkpoint",
        "waiting_reason": _normalize_optional_text(
            checkpoint_waiting_reason,
            field_name="checkpoint_waiting_reason",
        )
        or "Parent/applicator resume context required.",
    }
    if phase is not None:
        payload["phase"] = phase
    if plan is not None:
        payload["plan"] = plan
    return payload


def _validate_and_dump_envelope(envelope: Mapping[str, object]) -> dict[str, object]:
    try:
        validated = GpdReturnEnvelope.model_validate(dict(envelope))
    except PydanticValidationError as exc:
        errors = "; ".join(_format_validation_error(exc))
        raise ValueError(f"invalid gpd_return skeleton: {errors}") from exc
    return validated.model_dump(mode="json", exclude_none=True, exclude_unset=True)


def _format_validation_error(exc: PydanticValidationError) -> list[str]:
    errors: list[str] = []
    for item in exc.errors():
        location = ".".join(str(part) for part in item.get("loc", ())) or "gpd_return"
        message = str(item.get("msg", "validation error"))
        if message.startswith("Value error, "):
            message = message[len("Value error, ") :]
        errors.append(f"{location}: {message}")
    return errors


def _assert_field_can_be_rendered(field_name: str, *, status: str) -> None:
    if field_name not in KNOWN_RETURN_FIELD_NAMES:
        raise ValueError(f"unknown gpd_return field '{field_name}'")
    if not _field_allowed_for_status(field_name, status):
        raise ValueError(f"status '{status}' does not allow gpd_return field '{field_name}'")


def _fields_allowed_for_status(status: str) -> tuple[str, ...]:
    allowed_fields: list[str] = []
    for field_name in GpdReturnEnvelope.model_fields:
        if _field_allowed_for_status(field_name, status):
            allowed_fields.append(field_name)
    for field_name in sorted(ALLOWED_RETURN_EXTENSION_FIELDS):
        if _field_allowed_for_status(field_name, status):
            allowed_fields.append(field_name)
    return tuple(allowed_fields)


def _field_allowed_for_status(field_name: str, status: str) -> bool:
    if field_name not in KNOWN_RETURN_FIELD_NAMES:
        return False
    if field_name == _CHECKPOINT_INTENT_FIELD and status != "checkpoint":
        return False
    if field_name in _STATUS_RESTRICTED_FIELDS:
        return field_name in RETURN_ENVELOPE_STATUS_CONTRACTS[status].structured_fields
    return True


def _contract_supports_checkpoint_intent() -> bool:
    return _field_allowed_for_status(_CHECKPOINT_INTENT_FIELD, "checkpoint")


def _default_value_for_field(field_name: str, *, phase: str | None, plan: str | None) -> object:
    if field_name == "phase":
        return phase or "unknown"
    if field_name == "plan":
        return plan or "unknown"
    try:
        value = _FIELD_DEFAULTS[field_name]
    except KeyError as exc:
        raise ValueError(f"no conservative skeleton default registered for gpd_return field '{field_name}'") from exc
    if isinstance(value, list):
        return list(value)
    if isinstance(value, dict):
        return dict(value)
    return value


def _validation_commands(*, applicator_ready: bool) -> list[str]:
    commands = ["gpd validate-return <return-file.md>"]
    if applicator_ready:
        commands.append("gpd apply-return-updates <return-file.md>")
    return commands


def _authoring_rules() -> list[str]:
    return [
        "Keep concrete artifact paths, allowed writes, validators, and failure routes in the workflow callsite.",
        "Use only fields accepted by the canonical gpd_return contract.",
        "Treat role profiles as rendering hints, not as schema authority.",
    ]


def _profile(
    *,
    profile_id: str,
    agent_names: tuple[str, ...],
    role_fields: tuple[str, ...],
    default_render_fields: tuple[str, ...],
    local_callsite_fields: tuple[str, ...],
) -> GpdReturnRoleProfile:
    role_fields = _dedupe(role_fields)
    default_render_fields = _dedupe(default_render_fields)
    _assert_known_profile_fields(role_fields)
    _assert_known_profile_fields(default_render_fields)
    unknown_defaults = sorted(set(default_render_fields) - set(role_fields))
    if unknown_defaults:
        fields = ", ".join(unknown_defaults)
        raise ValueError(f"profile '{profile_id}' default fields are not declared role fields: {fields}")

    return GpdReturnRoleProfile(
        profile_id=profile_id,
        agent_names=agent_names,
        role_fields_by_status={
            status: _filter_fields_for_status(role_fields, status) for status in RETURN_STATUS_ORDER
        },
        default_render_fields_by_status={
            status: _filter_fields_for_status(_with_status_default_additions(default_render_fields, status), status)
            for status in RETURN_STATUS_ORDER
        },
        local_callsite_fields=local_callsite_fields,
    )


def _assert_known_profile_fields(fields: Iterable[str]) -> None:
    unknown_fields = sorted(set(fields) - KNOWN_RETURN_FIELD_NAMES)
    if unknown_fields:
        raise ValueError(f"unknown gpd_return profile field(s): {', '.join(unknown_fields)}")


def _filter_fields_for_status(fields: Iterable[str], status: str) -> tuple[str, ...]:
    return tuple(field_name for field_name in _dedupe(fields) if _field_allowed_for_status(field_name, status))


def _with_status_default_additions(fields: tuple[str, ...], status: str) -> tuple[str, ...]:
    if status in {"checkpoint", "blocked", "failed"}:
        return _dedupe((*fields, "blockers"))
    return fields


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)


_FIELD_DEFAULTS: dict[str, object] = {
    "approximations": [],
    "approved_plans": [],
    "blocked_plans": [],
    "blockers": [],
    "checks_performed": [],
    "confidence": "unassessed",
    "context_pressure": "normal",
    "conventions": [],
    "dimensions_checked": [],
    "dimensions_evaluated": [],
    "duration_seconds": 0,
    "field_assessment": "pending",
    "focus": "unspecified",
    "issues_found": [],
    "major_issues": [],
    "minor_issues": [],
    "papers_reviewed": 0,
    "phase_checked": "unknown",
    "plans": [],
    "plans_created": 0,
    "recommendation": "needs_review",
    "reference_maps": [],
    "revision_guidance": [],
    "revision_round": 1,
    "roadmap_updates": [],
    "score": "unscored",
    "tasks_completed": 0,
    "tasks_total": 0,
    "verification_status": "gaps_found",
    "waves": [],
}


_CALLSITE_FIELDS = (
    "expected_artifacts",
    "allowed_roots",
    "allowed_write_paths",
    "validator_commands",
    "applicator",
    "failure_route",
    "retry_policy",
)

GPD_RETURN_ROLE_PROFILES: dict[str, GpdReturnRoleProfile] = {
    "executor": _profile(
        profile_id="executor",
        agent_names=("gpd-executor",),
        role_fields=(
            "phase",
            "plan",
            "tasks_completed",
            "tasks_total",
            "duration_seconds",
            "state_updates",
            "contract_updates",
            "decisions",
            "blockers",
            "continuation_update",
            "conventions_used",
            "checkpoint_hashes",
            "confidence",
        ),
        default_render_fields=("phase", "plan", "tasks_completed", "tasks_total", "duration_seconds"),
        local_callsite_fields=_CALLSITE_FIELDS,
    ),
    "planner": _profile(
        profile_id="planner",
        agent_names=("gpd-planner",),
        role_fields=(
            "phase",
            "plans_created",
            "waves",
            "plans",
            "roadmap_updates",
            "conventions",
            "approximations",
            "context_pressure",
            "blockers",
            "continuation_update",
        ),
        default_render_fields=(
            "phase",
            "plans_created",
            "waves",
            "plans",
            "roadmap_updates",
            "conventions",
            "approximations",
            "context_pressure",
        ),
        local_callsite_fields=_CALLSITE_FIELDS,
    ),
    "checker": _profile(
        profile_id="checker",
        agent_names=("gpd-plan-checker",),
        role_fields=(
            "approved_plans",
            "blocked_plans",
            "dimensions_checked",
            "revision_round",
            "revision_guidance",
            "blockers",
            "continuation_update",
        ),
        default_render_fields=(
            "approved_plans",
            "blocked_plans",
            "dimensions_checked",
            "revision_round",
            "revision_guidance",
        ),
        local_callsite_fields=_CALLSITE_FIELDS,
    ),
    "verifier": _profile(
        profile_id="verifier",
        agent_names=("gpd-verifier",),
        role_fields=(
            "phase_checked",
            "checks_performed",
            "verification_status",
            "score",
            "confidence",
            "blockers",
            "continuation_update",
        ),
        default_render_fields=("phase_checked", "checks_performed", "verification_status", "score", "confidence"),
        local_callsite_fields=_CALLSITE_FIELDS,
    ),
    "referee": _profile(
        profile_id="referee",
        agent_names=("gpd-referee",),
        role_fields=(
            "recommendation",
            "confidence",
            "score",
            "major_issues",
            "minor_issues",
            "issues_found",
            "dimensions_evaluated",
            "blockers",
            "continuation_update",
        ),
        default_render_fields=(
            "recommendation",
            "confidence",
            "score",
            "major_issues",
            "minor_issues",
            "issues_found",
            "dimensions_evaluated",
        ),
        local_callsite_fields=_CALLSITE_FIELDS,
    ),
    "reviewer": _profile(
        profile_id="reviewer",
        agent_names=("gpd-literature-reviewer",),
        role_fields=(
            "recommendation",
            "confidence",
            "score",
            "major_issues",
            "minor_issues",
            "issues_found",
            "dimensions_evaluated",
            "blockers",
            "continuation_update",
        ),
        default_render_fields=(
            "recommendation",
            "confidence",
            "score",
            "major_issues",
            "minor_issues",
            "issues_found",
            "dimensions_evaluated",
        ),
        local_callsite_fields=_CALLSITE_FIELDS,
    ),
    "researcher": _profile(
        profile_id="researcher",
        agent_names=("gpd-project-researcher", "gpd-phase-researcher"),
        role_fields=(
            "focus",
            "papers_reviewed",
            "field_assessment",
            "reference_maps",
            "confidence",
            "blockers",
            "continuation_update",
        ),
        default_render_fields=("focus", "papers_reviewed", "field_assessment", "reference_maps", "confidence"),
        local_callsite_fields=_CALLSITE_FIELDS,
    ),
    "synthesizer": _profile(
        profile_id="synthesizer",
        agent_names=("gpd-research-synthesizer",),
        role_fields=(
            "focus",
            "papers_reviewed",
            "field_assessment",
            "reference_maps",
            "confidence",
            "blockers",
            "continuation_update",
        ),
        default_render_fields=("focus", "papers_reviewed", "field_assessment", "reference_maps", "confidence"),
        local_callsite_fields=_CALLSITE_FIELDS,
    ),
    "roadmapper": _profile(
        profile_id="roadmapper",
        agent_names=("gpd-roadmapper",),
        role_fields=(
            "phase",
            "plans_created",
            "waves",
            "plans",
            "roadmap_updates",
            "conventions",
            "approximations",
            "context_pressure",
            "blockers",
            "continuation_update",
        ),
        default_render_fields=(
            "phase",
            "plans_created",
            "waves",
            "plans",
            "roadmap_updates",
            "conventions",
            "approximations",
            "context_pressure",
        ),
        local_callsite_fields=_CALLSITE_FIELDS,
    ),
}
