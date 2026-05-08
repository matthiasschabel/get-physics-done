"""Compact prompt snippets for spawned-child return and artifact gates."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Literal, Self, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gpd.core.handoff_artifacts import HandoffFailureClass
from gpd.core.return_skeleton import RETURN_STATUS_ORDER, list_gpd_return_profiles, normalize_return_profile_id

ChildGateSnippetId = Literal[
    "return_profile",
    "child_artifact_gate",
    "continuation_boundary",
    "verification_status_authority",
    "prose_is_not_authority",
]

CHILD_GATE_SNIPPET_IDS: tuple[ChildGateSnippetId, ...] = (
    "return_profile",
    "child_artifact_gate",
    "continuation_boundary",
    "verification_status_authority",
    "prose_is_not_authority",
)

__all__ = [
    "CHILD_GATE_SNIPPET_IDS",
    "ChildGateApplicator",
    "ChildGateArtifact",
    "ChildGateFreshness",
    "ChildGateSnippetId",
    "ChildGateTuple",
    "child_gate_snippet_ids",
    "child_gate_tuple_from_payload",
    "render_child_gate_prompt_block",
    "render_child_gate_snippet",
    "render_child_gate_snippets",
    "render_child_gate_tuple",
]


class ChildGateArtifact(BaseModel):
    """One callsite-owned child artifact expectation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    kind: Literal["path", "glob"] = "path"
    required: bool = True
    must_be_named_in_files_written: bool = True

    @field_validator("path", mode="before")
    @classmethod
    def _normalize_path(cls, value: object) -> str:
        return _normalize_text(value, field_name="path")

    def to_payload(self) -> dict[str, object]:
        return {
            "path": self.path,
            "kind": self.kind,
            "required": self.required,
            "must_be_named_in_files_written": self.must_be_named_in_files_written,
        }


class ChildGateFreshness(BaseModel):
    """Presentation tuple for freshness checks owned by the callsite."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    marker: str | None = None
    require_mtime_at_or_after_marker: bool = False
    preexisting_artifacts: Literal["recovery_evidence_only", "allowed", "blocked", "not_applicable"] = (
        "recovery_evidence_only"
    )

    @field_validator("marker", mode="before")
    @classmethod
    def _normalize_marker(cls, value: object) -> str | None:
        return _normalize_optional_text(value, field_name="marker")

    @model_validator(mode="after")
    def _require_marker_when_mtime_gate_is_enabled(self) -> Self:
        if self.require_mtime_at_or_after_marker and self.marker is None:
            raise ValueError("freshness marker is required when mtime freshness is enabled")
        return self

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "require_mtime_at_or_after_marker": self.require_mtime_at_or_after_marker,
            "preexisting_artifacts": self.preexisting_artifacts,
        }
        if self.marker is not None:
            payload = {"marker": self.marker, **payload}
        return payload


class ChildGateApplicator(BaseModel):
    """Presentation tuple for callsite-owned durable effects."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    command: str = "none"
    require_passed_true: bool = False

    @model_validator(mode="before")
    @classmethod
    def _normalize_compact_applicator(cls, value: object) -> object:
        if isinstance(value, str):
            return {"command": value}
        return value

    @field_validator("command", mode="before")
    @classmethod
    def _normalize_command(cls, value: object) -> str:
        return _normalize_text(value, field_name="command")

    @model_validator(mode="after")
    def _reject_passed_gate_without_applicator(self) -> Self:
        if self.command == "none" and self.require_passed_true:
            raise ValueError("applicator require_passed_true requires a command")
        return self

    def to_payload(self) -> dict[str, object]:
        return {
            "command": self.command,
            "require_passed_true": self.require_passed_true,
        }


class ChildGateTuple(BaseModel):
    """Prompt-visible child gate tuple; validation remains in existing gate code."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    role: str
    return_profile: str
    required_status: str = "completed"
    expected_artifacts: tuple[ChildGateArtifact, ...] = ()
    allowed_roots: tuple[str, ...] = ()
    freshness: ChildGateFreshness | None = None
    validators: tuple[str, ...] = ()
    applicator: ChildGateApplicator = Field(default_factory=ChildGateApplicator)
    failure_route: dict[HandoffFailureClass, str] = Field(default_factory=lambda: dict(_DEFAULT_FAILURE_ROUTE))
    status_route: dict[str, str] = Field(default_factory=dict)
    write_allowlist: tuple[str, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def _infer_return_profile(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        payload = dict(value)
        if "freshness" not in payload and "freshness_marker" in payload:
            payload["freshness"] = {
                "marker": _normalize_freshness_marker(payload.pop("freshness_marker")),
                "require_mtime_at_or_after_marker": True,
                "preexisting_artifacts": "recovery_evidence_only",
            }
        if "write_allowlist" not in payload and "allowed_write_paths" in payload:
            payload["write_allowlist"] = payload.pop("allowed_write_paths")
        raw_failure_route = payload.get("failure_route")
        if isinstance(raw_failure_route, Mapping):
            failure_route: dict[str, object] = {}
            status_route = dict(payload.get("status_route", {})) if isinstance(payload.get("status_route"), Mapping) else {}
            for key, route in raw_failure_route.items():
                key_text = str(key)
                if key_text in {failure_class.value for failure_class in HandoffFailureClass}:
                    failure_route[key_text] = route
                else:
                    status_route[key_text] = route
            payload["failure_route"] = failure_route
            if status_route:
                payload["status_route"] = status_route
        raw_profile = payload.get("return_profile")
        if isinstance(raw_profile, str) and raw_profile.strip():
            payload["return_profile"] = _profile_id_for_role_or_profile(raw_profile)
            return payload
        raw_role = payload.get("role")
        if not isinstance(raw_role, str) or not raw_role.strip():
            return payload
        payload["return_profile"] = _profile_id_for_role_or_profile(raw_role)
        return payload

    @field_validator("id", "role", mode="before")
    @classmethod
    def _normalize_required_text(cls, value: object, info) -> str:
        return _normalize_text(value, field_name=info.field_name)

    @field_validator("return_profile", mode="before")
    @classmethod
    def _normalize_return_profile(cls, value: object) -> str:
        return _profile_id_for_role_or_profile(_normalize_text(value, field_name="return_profile"))

    @field_validator("required_status", mode="before")
    @classmethod
    def _normalize_required_status(cls, value: object) -> str:
        normalized = _normalize_text(value, field_name="required_status").lower()
        if normalized not in RETURN_STATUS_ORDER:
            statuses = ", ".join(RETURN_STATUS_ORDER)
            raise ValueError(f"unknown gpd_return status '{value}'. Must be one of: {statuses}")
        return normalized

    @field_validator("allowed_roots", "validators", mode="before")
    @classmethod
    def _normalize_text_tuple(cls, value: object, info) -> tuple[str, ...]:
        return _normalize_text_sequence(value, field_name=info.field_name)

    @field_validator("expected_artifacts", mode="before")
    @classmethod
    def _normalize_expected_artifacts(cls, value: object) -> object:
        if value is None:
            return ()
        if not isinstance(value, Iterable) or isinstance(value, (str, bytes, Mapping)):
            return value
        return [
            {"path": item} if isinstance(item, str) else item
            for item in value
        ]

    @field_validator("write_allowlist", mode="before")
    @classmethod
    def _normalize_write_allowlist(cls, value: object) -> tuple[str, ...]:
        return _normalize_text_sequence(value, field_name="write_allowlist")

    @field_validator("failure_route", mode="before")
    @classmethod
    def _normalize_failure_route(cls, value: object) -> dict[HandoffFailureClass, str]:
        if value is None:
            return dict(_DEFAULT_FAILURE_ROUTE)
        if isinstance(value, str):
            route = _normalize_text(value, field_name="failure_route")
            return dict.fromkeys(HandoffFailureClass, route)
        if not isinstance(value, Mapping):
            raise ValueError("failure_route must be a mapping")
        normalized: dict[HandoffFailureClass, str] = {}
        for raw_failure_class, raw_action in value.items():
            try:
                failure_class = HandoffFailureClass(str(raw_failure_class))
            except ValueError as exc:
                known = ", ".join(failure.value for failure in HandoffFailureClass)
                raise ValueError(
                    f"unknown handoff failure class '{raw_failure_class}'. Must be one of: {known}"
                ) from exc
            normalized[failure_class] = _normalize_text(raw_action, field_name=f"failure_route.{failure_class.value}")
        return normalized or dict(_DEFAULT_FAILURE_ROUTE)

    @field_validator("status_route", mode="before")
    @classmethod
    def _normalize_status_route(cls, value: object) -> dict[str, str]:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise ValueError("status_route must be a mapping")
        return {
            _normalize_text(raw_key, field_name="status_route key"): _normalize_text(
                raw_value,
                field_name=f"status_route.{raw_key}",
            )
            for raw_key, raw_value in value.items()
        }

    @model_validator(mode="after")
    def _ensure_return_profile_supports_status(self) -> Self:
        profiles = list_gpd_return_profiles(role=self.return_profile, status=self.required_status)
        if not profiles["profiles"]:
            raise ValueError(
                f"return profile '{self.return_profile}' has no status metadata for '{self.required_status}'"
            )
        return self

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id,
            "role": self.role,
            "return_profile": self.return_profile,
            "required_status": self.required_status,
        }
        if self.expected_artifacts:
            payload["expected_artifacts"] = [artifact.to_payload() for artifact in self.expected_artifacts]
        if self.allowed_roots:
            payload["allowed_roots"] = list(self.allowed_roots)
        if self.freshness is not None:
            payload["freshness"] = self.freshness.to_payload()
        if self.validators:
            payload["validators"] = list(self.validators)
        if self.write_allowlist:
            payload["write_allowlist"] = list(self.write_allowlist)
        payload["applicator"] = self.applicator.to_payload()
        payload["failure_route"] = {
            failure_class.value: self.failure_route[failure_class]
            for failure_class in HandoffFailureClass
            if failure_class in self.failure_route
        }
        if self.status_route:
            payload["status_route"] = dict(self.status_route)
        return payload


_DEFAULT_FAILURE_ROUTE: dict[HandoffFailureClass, str] = {
    HandoffFailureClass.RETURN_MISSING: "retry_once",
    HandoffFailureClass.RETURN_MALFORMED_REPAIRABLE: "repair_prompt_once",
    HandoffFailureClass.RETURN_MALFORMED_BLOCKING: "fail_closed",
    HandoffFailureClass.ARTIFACT_MISSING: "retry_once_or_main_context_fallback",
    HandoffFailureClass.ARTIFACT_STALE: "retry_once",
    HandoffFailureClass.ARTIFACT_PATH_REPAIRABLE: "repair_path_once",
    HandoffFailureClass.ARTIFACT_ROOT_BLOCKED: "fail_closed",
    HandoffFailureClass.VALIDATOR_FAILED: "revision_loop",
    HandoffFailureClass.APPLICATOR_FAILED: "fail_closed_with_mutation_report",
}


def child_gate_snippet_ids() -> tuple[ChildGateSnippetId, ...]:
    """Return the stable snippet id order."""

    return CHILD_GATE_SNIPPET_IDS


def child_gate_tuple_from_payload(payload: Mapping[str, object]) -> ChildGateTuple:
    """Build a tuple from either a raw tuple payload or ``{"child_gate": ...}``."""

    candidate = payload.get("child_gate") if "child_gate" in payload else payload
    if not isinstance(candidate, Mapping):
        raise ValueError("child_gate payload must be a mapping")
    return ChildGateTuple.model_validate(candidate)


def render_child_gate_tuple(gate: ChildGateTuple | Mapping[str, object]) -> str:
    """Render a deterministic fenced YAML child-gate tuple."""

    gate_tuple = gate if isinstance(gate, ChildGateTuple) else child_gate_tuple_from_payload(gate)
    rendered = yaml.safe_dump(
        {"child_gate": gate_tuple.to_payload()},
        default_flow_style=False,
        allow_unicode=False,
        sort_keys=False,
        width=999999,
    ).rstrip()
    return f"```yaml\n{rendered}\n```\n"


def render_child_gate_snippet(
    snippet_id: ChildGateSnippetId | str,
    *,
    role: str | None = None,
    status: str | None = None,
) -> str:
    """Render one compact deterministic child-gate snippet."""

    normalized = _normalize_snippet_id(snippet_id)
    if normalized == "return_profile":
        return _render_return_profile_snippet(role=role, status=status)
    if normalized == "child_artifact_gate":
        return _render_child_artifact_gate_snippet()
    if normalized == "continuation_boundary":
        return _render_continuation_boundary_snippet()
    if normalized == "verification_status_authority":
        return _render_verification_status_authority_snippet()
    if normalized == "prose_is_not_authority":
        return _render_prose_is_not_authority_snippet()
    raise AssertionError(f"unhandled child gate snippet id: {normalized}")


def render_child_gate_snippets(
    snippet_ids: Iterable[ChildGateSnippetId | str],
    *,
    role: str | None = None,
    status: str | None = None,
) -> str:
    """Render multiple snippets separated by one blank line."""

    return (
        "\n\n".join(
            render_child_gate_snippet(snippet_id, role=role, status=status).rstrip() for snippet_id in snippet_ids
        ).rstrip()
        + "\n"
    )


def render_child_gate_prompt_block(
    gate: ChildGateTuple | Mapping[str, object],
    *,
    snippets: Iterable[ChildGateSnippetId | str] = (
        "child_artifact_gate",
        "continuation_boundary",
        "prose_is_not_authority",
    ),
) -> str:
    """Render local snippets plus the callsite tuple."""

    gate_tuple = gate if isinstance(gate, ChildGateTuple) else child_gate_tuple_from_payload(gate)
    rendered_snippets = render_child_gate_snippets(
        snippets,
        role=gate_tuple.return_profile,
        status=gate_tuple.required_status,
    ).rstrip()
    return f"{rendered_snippets}\n\n{render_child_gate_tuple(gate_tuple)}"


def _render_return_profile_snippet(*, role: str | None, status: str | None) -> str:
    profile_id = _profile_id_for_role_or_profile(role) if role is not None else None
    payload = list_gpd_return_profiles(role=profile_id, status=status)

    if profile_id is None:
        roles = ", ".join(f"`{profile}`" for profile in payload["roles"])
        return (
            "Return profile: list metadata with `gpd return profiles`; exact YAML comes from "
            "`gpd return skeleton --role <role> --status <status>`. Profiles are rendering hints; "
            "`return_contract.py` remains the validator authority. Available profiles: "
            f"{roles}."
        )

    profiles = cast(list[dict[str, object]], payload["profiles"])
    profile = profiles[0]
    status_map = cast(dict[str, dict[str, list[str]]], profile["statuses"])
    status_ids = tuple(status_map)

    if len(status_ids) == 1:
        status_id = status_ids[0]
        role_fields = status_map[status_id]["role_fields"]
        field_text = _format_backtick_list(role_fields) or "required fields only"
        return (
            f"Return profile: `{profile_id}` / `{status_id}`; exact YAML: "
            f"`gpd return skeleton --role {profile_id} --status {status_id}`. Role fields: {field_text}. "
            "Profiles are rendering hints; `return_contract.py` validates, and the workflow callsite supplies "
            "artifacts, roots, validators, applicator, and failure route."
        )

    statuses = " | ".join(status_ids)
    return (
        f"Return profile: `{profile_id}` supports `{statuses}`. Exact YAML: "
        f"`gpd return skeleton --role {profile_id} --status <status>`. Profiles are rendering hints; "
        "`return_contract.py` validates, and the workflow callsite supplies artifacts, roots, validators, "
        "applicator, and failure route."
    )


def _render_child_artifact_gate_snippet() -> str:
    failure_classes = ", ".join(f"`{failure_class.value}`" for failure_class in HandoffFailureClass)
    return (
        "Child artifact gate: apply `references/orchestration/child-artifact-gate.md`; accept success only after "
        "a valid fenced `gpd_return.status`, expected `files_written` artifacts, path/freshness checks, validators, "
        "and any applicator pass. Failure classes: "
        f"{failure_classes}."
    )


def _render_continuation_boundary_snippet() -> str:
    return (
        "Continuation boundary: apply `references/orchestration/continuation-boundary.md`; a spawned child is one-shot; "
        "`status: checkpoint` stops the child. "
        "The parent presents the checkpoint and starts a fresh continuation; `checkpoint_intent` is child intent, "
        "while durable resume context is applicator-owned."
    )


def _render_verification_status_authority_snippet() -> str:
    return (
        "Verification status authority: apply `references/verification/verification-status-authority.md`; runtime "
        "`gpd_return.status` routes the handoff; verification report frontmatter `status` records verifier outcome; "
        "target labels like `VERIFIED`, `PARTIAL`, `FAILED`, and `UNCERTAIN` classify evidence."
    )


def _render_prose_is_not_authority_snippet() -> str:
    return (
        "Prose is not authority: headings, success text, files, commits, and preexisting artifacts are presentation "
        "or recovery evidence only; typed return, artifact gate, validators, and applicator decide acceptance."
    )


def _normalize_snippet_id(snippet_id: ChildGateSnippetId | str) -> ChildGateSnippetId:
    normalized = _normalize_text(snippet_id, field_name="snippet_id")
    if normalized not in CHILD_GATE_SNIPPET_IDS:
        known = ", ".join(CHILD_GATE_SNIPPET_IDS)
        raise ValueError(f"unknown child gate snippet id '{snippet_id}'. Must be one of: {known}")
    return cast(ChildGateSnippetId, normalized)


def _profile_id_for_role_or_profile(value: str | None) -> str:
    return normalize_return_profile_id(value)


def _normalize_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def _normalize_freshness_marker(value: object) -> str:
    marker = _normalize_text(value, field_name="freshness_marker")
    if marker.casefold().startswith("after "):
        return marker[6:].strip()
    return marker


def _normalize_optional_text(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _normalize_text(value, field_name=field_name)


def _normalize_text_sequence(value: object, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = (value,)
    if not isinstance(value, Iterable):
        raise ValueError(f"{field_name} must be an iterable of strings")

    normalized: list[str] = []
    for index, item in enumerate(value):
        normalized.append(_normalize_text(item, field_name=f"{field_name}[{index}]"))
    return tuple(normalized)


def _format_backtick_list(values: Iterable[str], *, limit: int = 8) -> str:
    value_list = list(values)
    displayed = value_list[:limit]
    formatted = ", ".join(f"`{value}`" for value in displayed)
    remaining = len(value_list) - len(displayed)
    if remaining > 0:
        return f"{formatted}, +{remaining} more"
    return formatted
