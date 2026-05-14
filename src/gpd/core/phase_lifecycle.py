"""Read-only phase lifecycle decisions shared by closeout-facing surfaces."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from gpd.command_labels import canonical_command_label
from gpd.core.command_run_hints import (
    KIND_LOCAL_CLI_HELPER_COMMAND,
    KIND_RUNTIME_COMMAND_LABEL,
    KIND_UNKNOWN_DISPLAY_ONLY,
    NEXT_COMMAND_OWNER_LOCAL_HELPER,
    NEXT_COMMAND_OWNER_LOCAL_READONLY,
    NEXT_COMMAND_OWNER_LOCAL_TRANSITION,
    NEXT_COMMAND_OWNER_RUNTIME,
    NextCommand,
    build_command_run_hint,
    classify_next_command,
)
from gpd.core.constants import ProjectLayout
from gpd.core.next_command_rendering import (
    render_next_up_block,
)
from gpd.core.phases import PhaseAmbiguityError, find_phase, roadmap_analyze
from gpd.core.state import load_state_json_readonly
from gpd.core.utils import (
    compare_phase_numbers,
    is_phase_complete,
    matching_phase_artifact_count,
    phase_normalize,
)
from gpd.core.verification_status import read_verification_status, verification_path_for_phase

_NEXT_UP_HINT_SOURCE = "phase-closeout-readiness"

_PROOF_REQUIRED_RE = re.compile(
    r"\b("
    r"proof_bearing\s*:\s*true|"
    r"proof-bearing|"
    r"proof_obligation|"
    r"proof_audit|"
    r"claim_kind\s*:\s*(theorem|lemma|corollary|proposition)"
    r")\b",
    re.IGNORECASE,
)

OWNER_RUNTIME = NEXT_COMMAND_OWNER_RUNTIME
OWNER_LOCAL_TRANSITION = NEXT_COMMAND_OWNER_LOCAL_TRANSITION
OWNER_LOCAL_HELPER = NEXT_COMMAND_OWNER_LOCAL_HELPER
ROLE_PRIMARY = "primary"
ROLE_SECONDARY = "secondary"

LifecycleDecisionKind = Literal[
    "needs_execution",
    "needs_verification",
    "ready_for_closeout",
    "blocked_closeout",
    "closed_ready_next_phase",
    "closed_milestone_complete",
]
CanonicalLifecycleClass = Literal[
    "needs_execution",
    "needs_verification",
    "ready_for_local_closeout",
    "blocked_closeout",
    "closed_ready_next_phase",
    "closed_needs_milestone_audit",
    "closed_ready_for_milestone_archive",
    "archived_ready_for_next_milestone",
]
LifecycleNextUpStatus = Literal["ready", "blocked", "closed"]


def _runtime_label_for_action(action: str, *, argument: str | None = None) -> str:
    label = canonical_command_label(action)
    return f"{label} {argument}" if argument else label


class LifecycleNextUp(BaseModel):
    """Canonical lifecycle-owned next-up object with legacy JSON projection."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid", arbitrary_types_allowed=True)

    schema_version: int = 1
    source: str = "phase-lifecycle"
    status: LifecycleNextUpStatus
    status_class: CanonicalLifecycleClass
    phase: str
    primary: NextCommand
    primary_label: str
    after_this_completes: NextCommand | None = None
    secondary: list[NextCommand] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    rendered_markdown: str
    stage_stop_next_runtime_command: str | None = None
    stage_stop_also_available: list[str] = Field(default_factory=list)

    @property
    def primary_owner(self) -> str:
        return self.primary.owner

    @property
    def primary_command_text(self) -> str:
        return self.primary.command

    @classmethod
    def ready_local_transition(
        cls,
        *,
        phase: str,
        closeout_command: str,
        cleanup_command: str | None,
    ) -> Self:
        primary = _local_transition_next_command(command=closeout_command, action="phase-complete", phase=phase)
        after_this_completes = _runtime_next_command(
            action="suggest-next",
            reason="choose the next safe workflow route after the local phase transition completes",
        )
        secondary: list[NextCommand] = []
        if cleanup_command is not None:
            secondary.append(_cleanup_next_command(command=cleanup_command, phase=phase))
        rendered = render_next_up_block(
            primary=primary,
            after_this_completes=after_this_completes,
            secondary=secondary,
        )
        return cls(
            status="ready",
            status_class="ready_for_local_closeout",
            phase=phase,
            primary=primary,
            primary_label="Primary local transition",
            after_this_completes=after_this_completes,
            secondary=secondary,
            rendered_markdown=rendered.markdown,
            stage_stop_next_runtime_command=rendered.stage_stop_next_runtime_command,
            stage_stop_also_available=list(rendered.stage_stop_also_available),
        )

    @classmethod
    def blocked_runtime(
        cls,
        *,
        phase: str,
        blockers: list[str],
        action: str | None,
        status_class: CanonicalLifecycleClass | None = None,
    ) -> Self:
        primary = _blocked_next_command(phase=phase, blockers=blockers, blocked_action=action)
        rendered = render_next_up_block(primary=primary)
        return cls(
            status="blocked",
            status_class=status_class or _blocked_status_class(primary.action),
            phase=phase,
            primary=primary,
            primary_label="Primary",
            blockers=list(blockers),
            rendered_markdown=rendered.markdown,
            stage_stop_next_runtime_command=rendered.stage_stop_next_runtime_command,
            stage_stop_also_available=list(rendered.stage_stop_also_available),
        )

    @classmethod
    def closed_runtime(
        cls,
        *,
        phase: str,
        next_phase: str | None,
        status_class: CanonicalLifecycleClass,
        milestone_version: str | None = None,
    ) -> Self:
        if next_phase is not None:
            primary = _runtime_next_command(action="plan-phase", phase=next_phase)
            status_class = "closed_ready_next_phase"
        elif status_class == "closed_ready_for_milestone_archive":
            primary = _runtime_next_command_with_argument(action="complete-milestone", argument=milestone_version)
        elif status_class == "archived_ready_for_next_milestone":
            primary = _runtime_next_command(action="new-milestone")
        else:
            primary = _runtime_next_command(action="audit-milestone")
            status_class = "closed_needs_milestone_audit"

        rendered = render_next_up_block(primary=primary)
        return cls(
            status="closed",
            status_class=status_class,
            phase=phase,
            primary=primary,
            primary_label="Primary",
            rendered_markdown=rendered.markdown,
            stage_stop_next_runtime_command=rendered.stage_stop_next_runtime_command,
            stage_stop_also_available=list(rendered.stage_stop_also_available),
        )

    @model_validator(mode="after")
    def _validate_lifecycle_invariants(self) -> Self:
        if self.status == "ready":
            if self.primary.owner != OWNER_LOCAL_TRANSITION or self.primary.action != "phase-complete":
                raise ValueError("ready lifecycle next-up requires a phase-complete local transition primary")
            if self.after_this_completes is None or self.after_this_completes.owner != OWNER_RUNTIME:
                raise ValueError("ready lifecycle next-up requires an after-this-completes runtime route")
            if self.stage_stop_next_runtime_command != self.after_this_completes.command:
                raise ValueError("ready lifecycle stage-stop route must match after-this-completes")
            if self.primary.requires_user_initiated_runtime_command:
                raise ValueError("local transition primary must not require a user-initiated runtime command")
            if any(command.owner != OWNER_LOCAL_HELPER for command in self.secondary):
                raise ValueError("ready lifecycle secondary commands must be local helpers")
        elif self.status == "blocked":
            if self.primary.owner != OWNER_RUNTIME:
                raise ValueError("blocked lifecycle next-up requires a runtime primary")
            if self.primary.action not in {"execute-phase", "verify-work", "resume-work"}:
                raise ValueError("blocked lifecycle primary action is not a closeout recovery route")
            if self.after_this_completes is not None:
                raise ValueError("blocked lifecycle next-up cannot have after-this-completes")
            if not self.blockers:
                raise ValueError("blocked lifecycle next-up requires blockers")
        elif self.status == "closed":
            if self.primary.owner != OWNER_RUNTIME:
                raise ValueError("closed lifecycle next-up requires a runtime primary")
            if self.primary.action not in {
                "plan-phase",
                "audit-milestone",
                "complete-milestone",
                "new-milestone",
            }:
                raise ValueError("closed lifecycle primary action is not a closed-phase route")
            if self.after_this_completes is not None:
                raise ValueError("closed lifecycle next-up cannot have after-this-completes")
            if "gpd phase complete" in self.rendered_markdown:
                raise ValueError("closed lifecycle next-up must not repeat local phase closeout")
        return self

    @field_serializer("primary", "after_this_completes", when_used="json")
    def _serialize_next_command(self, value: NextCommand | None) -> dict[str, object] | None:
        return value.as_dict() if value is not None else None

    @field_serializer("secondary", when_used="json")
    def _serialize_secondary_commands(self, value: list[NextCommand]) -> list[dict[str, object]]:
        return [command.as_dict() for command in value]

    def as_legacy_next_up_dict(self, *, hint_source: str = _NEXT_UP_HINT_SOURCE) -> dict[str, object]:
        """Return the legacy ``next_up`` JSON shape generated from canonical fields."""

        primary_hint = _hint_from_next_command(
            self.primary,
            role=ROLE_PRIMARY,
            owner=self.primary.owner,
            source=hint_source,
        )
        secondary_hints = [
            hint
            for command in self.secondary
            if (
                hint := _hint_from_next_command(
                    command,
                    role=ROLE_SECONDARY,
                    owner=command.owner,
                    source=hint_source,
                )
            )
            is not None
        ]
        commands = [hint for hint in (primary_hint, *secondary_hints) if hint is not None]
        primary_command = _typed_command_payload(self.primary, role=ROLE_PRIMARY)
        secondary_commands = [_typed_command_payload(command, role=ROLE_SECONDARY) for command in self.secondary]

        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "source": self.source,
            "phase": self.phase,
            "status": self.status,
            "status_class": self.status_class,
            "lifecycle_class": self.status_class,
            "primary": self.primary.command,
            "primary_owner": self.primary.owner,
            "primary_label": self.primary_label,
            "commands": commands,
            "primary_command": primary_command,
            "primary_next_command": dict(primary_command),
            "secondary": secondary_hints,
            "secondary_commands": secondary_commands,
            "secondary_next_commands": [dict(command) for command in secondary_commands],
            "rendered_markdown": self.rendered_markdown,
            "stage_stop_next_runtime_command": self.stage_stop_next_runtime_command,
            "stage_stop_also_available": list(self.stage_stop_also_available),
        }
        if self.after_this_completes is not None:
            after = _typed_command_payload(self.after_this_completes)
            payload["after_this_completes"] = after
            payload["after_this_completes_next_command"] = dict(after)
        if self.blockers or self.status == "blocked":
            payload["blockers"] = list(self.blockers)
        return payload

    def to_compat_dict(self, *, hint_source: str = _NEXT_UP_HINT_SOURCE) -> dict[str, object]:
        """Alias for consumers using the explorer-proposed method name."""

        return self.as_legacy_next_up_dict(hint_source=hint_source)


class PhaseCloseoutReadiness(BaseModel):
    """Read-only decision payload for whether a phase may be closed out."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    phase: str
    ready: bool
    mutation_allowed: bool
    read_only: bool = True
    mutated: bool = False
    project_root: str
    phase_dir: str | None = None
    plan_count: int = 0
    summary_count: int = 0
    all_plans_complete: bool = False
    incomplete_plans: list[str] = Field(default_factory=list)
    verification_path: str | None = None
    verification_status: str | None = None
    verification_routing_status: str = "missing"
    require_verification: bool = False
    proof_redteam_required: bool = False
    proof_redteam_ready: bool = True
    proof_redteam_artifacts: list[str] = Field(default_factory=list)
    active_bounded_segment: bool = False
    checkpoint_tags: list[str] = Field(default_factory=list)
    preserve_checkpoint_tags: bool = True
    recovery_artifacts: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    closeout_command: str | None = None
    cleanup_command: str | None = None
    closeout_command_hint: dict[str, object] | None = None
    cleanup_command_hint: dict[str, object] | None = None
    lifecycle_next_up: LifecycleNextUp | None = None
    next_up: dict[str, object] = Field(default_factory=dict)


class PhaseLifecycleDecision(BaseModel):
    """Read-only lifecycle classification for one phase."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    phase: str
    project_root: str
    phase_dir: str | None = None
    state_current_phase: str | None = None
    state_status: str | None = None
    roadmap_complete: bool = False
    disk_complete: bool = False
    plan_count: int = 0
    summary_count: int = 0
    verification_path: str | None = None
    verification_status: str | None = None
    verification_routing_status: str = "missing"
    closeout_ready: bool = False
    closeout_blockers: list[str] = Field(default_factory=list)
    closeout_warnings: list[str] = Field(default_factory=list)
    phase_closed: bool = False
    next_phase: str | None = None
    decision: LifecycleDecisionKind
    lifecycle_class: CanonicalLifecycleClass
    primary_action: str | None = None
    primary_owner: str | None = None
    primary_command: str | None = None
    lifecycle_next_up: LifecycleNextUp | None = None
    next_up: dict[str, object] = Field(default_factory=dict)
    closeout_readiness: PhaseCloseoutReadiness


def _relative(project_root: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.resolve(strict=False).relative_to(project_root.resolve(strict=False)).as_posix()
    except ValueError:
        return path.resolve(strict=False).as_posix()


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _phase_requires_proof_redteam(phase_dir: Path) -> bool:
    for path in sorted(phase_dir.glob("*.md")):
        if path.name.endswith("-PROOF-REDTEAM.md") or path.name == "PROOF-REDTEAM.md":
            continue
        content = _read_text(path)
        if content and _PROOF_REQUIRED_RE.search(content):
            return True
    return False


def _proof_redteam_status(project_root: Path, phase_dir: Path) -> tuple[bool, bool, list[str], list[str]]:
    artifacts = sorted(
        [
            *phase_dir.glob("*-PROOF-REDTEAM.md"),
            *phase_dir.glob("PROOF-REDTEAM.md"),
        ],
        key=lambda path: path.name,
    )
    artifact_refs = [_relative(project_root, artifact) or artifact.as_posix() for artifact in artifacts]
    required = _phase_requires_proof_redteam(phase_dir)
    if not artifacts:
        return (
            required,
            not required,
            artifact_refs,
            (["proof-bearing work requires a passed proof-redteam artifact"] if required else []),
        )

    from gpd.core.proof_redteam import validate_proof_redteam_artifact

    errors: list[str] = []
    for artifact in artifacts:
        result = validate_proof_redteam_artifact(artifact, project_root=project_root)
        if not result.valid:
            errors.extend(f"{_relative(project_root, artifact)}: {error}" for error in result.errors)
            continue
        if result.status != "passed":
            errors.append(f"{_relative(project_root, artifact)} reports status {result.status!r}; expected 'passed'")
    return required or bool(artifacts), not errors, artifact_refs, errors


def _active_bounded_segment(project_root: Path) -> tuple[bool, dict[str, object] | None, list[str]]:
    state = load_state_json_readonly(project_root)
    if not isinstance(state, dict):
        return False, None, []
    continuation = state.get("continuation")
    if not isinstance(continuation, dict):
        return False, None, []
    bounded = continuation.get("bounded_segment")
    if not isinstance(bounded, dict) or not bounded:
        return False, None, []
    status = str(bounded.get("segment_status") or "").strip().lower()
    if status in {"completed", "complete", "done", "finished"}:
        return False, bounded, []
    return True, bounded, ["active bounded segment must be resumed or cleared before phase closeout"]


def _phase_recovery_artifacts(project_root: Path, phase_dir: Path) -> list[str]:
    artifacts: list[Path] = []
    for pattern in ("*RECOVERY*.md", "*recovery*.md"):
        artifacts.extend(phase_dir.glob(pattern))
    return sorted({ref for artifact in artifacts if (ref := _relative(project_root, artifact)) is not None})


def _checkpoint_tags(project_root: Path, phase: str) -> tuple[list[str], list[str]]:
    try:
        from gpd.core.wave_checkpoints import list_wave_checkpoints

        result = list_wave_checkpoints(project_root, phase=phase, namespace="phase")
    except Exception as exc:  # noqa: BLE001 - readiness is read-only and should degrade to a warning
        return [], [f"checkpoint tag inventory unavailable: {exc}"]
    return result.tags, result.errors


def _with_ordered_notes(notes: object, *extra_notes: str) -> list[str]:
    values = [str(note) for note in notes] if isinstance(notes, list) else []
    for note in extra_notes:
        if note not in values:
            values.append(note)
    return values


def _with_role(payload: dict[str, object], *, role: str | None, owner: str | None = None) -> dict[str, object]:
    result = dict(payload)
    if owner is not None:
        result["owner"] = owner
        result["notes"] = _with_ordered_notes(result.get("notes"), owner)
    if role is not None:
        result["role"] = role
        result["notes"] = _with_ordered_notes(result.get("notes"), f"{role}_next_up")
    if result.get("owner") in {OWNER_LOCAL_TRANSITION, OWNER_LOCAL_HELPER, NEXT_COMMAND_OWNER_LOCAL_READONLY}:
        result["requires_user_initiated_runtime_command"] = False
        result["fresh_context_recommended"] = False
        result["notes"] = _with_ordered_notes(result.get("notes"), "display_copy_safe")
    return result


def _typed_command_payload(next_command: NextCommand, *, role: str | None = None) -> dict[str, object]:
    return _with_role(next_command.as_dict(), role=role)


def _hint_from_next_command(
    next_command: NextCommand | None,
    *,
    role: str | None = None,
    owner: str | None = None,
    source: str = _NEXT_UP_HINT_SOURCE,
) -> dict[str, object] | None:
    if next_command is None:
        return None
    payload = next_command.as_run_hint(source=source)
    return _with_role(payload, role=role, owner=owner)


def _hint(
    command: str | None,
    *,
    action: str | None,
    phase: str,
    owner: str | None = None,
    role: str | None = None,
) -> dict[str, object] | None:
    hint = build_command_run_hint(command=command, source=_NEXT_UP_HINT_SOURCE, action=action, phase=phase)
    if hint is not None:
        payload = dict(hint)
    elif not command:
        return None
    else:
        payload = {
            "source": "phase-closeout-readiness",
            "kind": "unknown_display_only",
            "command": command,
            "action": action,
            "phase": phase,
            "execution": "not_executed",
            "notes": ["display_only"],
        }

    if owner is not None:
        payload["owner"] = owner
        payload["notes"] = _with_ordered_notes(payload.get("notes"), owner)
    if role is not None:
        payload["role"] = role
        payload["notes"] = _with_ordered_notes(payload.get("notes"), f"{role}_next_up")
    if owner in {OWNER_LOCAL_TRANSITION, OWNER_LOCAL_HELPER}:
        payload["requires_user_initiated_runtime_command"] = False
        payload["fresh_context_recommended"] = False
        payload["notes"] = _with_ordered_notes(payload.get("notes"), "display_copy_safe")
    return payload


def _runtime_command_label(action: str, *, phase: str | None = None) -> str:
    return _runtime_label_for_action(action, argument=phase)


def _runtime_next_command(*, action: str, phase: str | None = None, reason: str | None = None) -> NextCommand:
    label = _runtime_command_label(action, phase=phase)
    classified = classify_next_command(command=label, action=action, phase=phase, reason=reason)
    if classified is not None and classified.owner == OWNER_RUNTIME and classified.kind == KIND_RUNTIME_COMMAND_LABEL:
        return classified
    return NextCommand(
        label=label,
        action=action,
        owner=OWNER_RUNTIME,
        phase=phase,
        reason=reason,
        kind=KIND_RUNTIME_COMMAND_LABEL,
        requires_user_initiated_runtime_command=True,
        fresh_context_recommended=True,
        notes=("user_initiated_runtime_command_required",),
    )


def _runtime_next_command_with_argument(
    *,
    action: str,
    argument: str | None = None,
    reason: str | None = None,
) -> NextCommand:
    label = _runtime_label_for_action(action, argument=argument)
    classified = classify_next_command(command=label, action=action, reason=reason)
    if classified is not None and classified.owner == OWNER_RUNTIME and classified.kind == KIND_RUNTIME_COMMAND_LABEL:
        return classified
    return NextCommand(
        label=label,
        action=action,
        owner=OWNER_RUNTIME,
        reason=reason,
        kind=KIND_RUNTIME_COMMAND_LABEL,
        requires_user_initiated_runtime_command=True,
        fresh_context_recommended=True,
        notes=("user_initiated_runtime_command_required",),
    )


def _blocked_status_class(action: str | None) -> CanonicalLifecycleClass:
    if action == "execute-phase":
        return "needs_execution"
    if action == "verify-work":
        return "needs_verification"
    return "blocked_closeout"


def _local_transition_next_command(*, command: str, action: str, phase: str) -> NextCommand:
    classified = classify_next_command(command=command, action=action, phase=phase)
    if classified is not None and classified.owner == OWNER_LOCAL_TRANSITION:
        return classified
    return NextCommand(
        label=command,
        action=action,
        owner=OWNER_LOCAL_TRANSITION,
        phase=phase,
        kind=KIND_UNKNOWN_DISPLAY_ONLY,
        notes=("display_copy_safe", "not_executed"),
    )


def _cleanup_next_command(*, command: str, phase: str) -> NextCommand:
    classified = classify_next_command(command=command, action="checkpoint-cleanup", phase=phase)
    if classified is not None and classified.owner == OWNER_LOCAL_HELPER:
        return classified
    return NextCommand(
        label=command,
        action="checkpoint-cleanup",
        owner=OWNER_LOCAL_HELPER,
        phase=phase,
        kind=KIND_LOCAL_CLI_HELPER_COMMAND,
        notes=("display_copy_safe", "not_executed"),
    )


def _blocked_next_command(*, phase: str, blockers: list[str], blocked_action: str | None) -> NextCommand:
    if blocked_action is None:
        if any("bounded segment" in blocker for blocker in blockers):
            blocked_action = "resume-work"
        elif any(
            "verification" in blocker or "proof-redteam" in blocker or "proof-bearing" in blocker
            for blocker in blockers
        ):
            blocked_action = "verify-work"
        else:
            blocked_action = "execute-phase"
    if blocked_action == "resume-work":
        return _runtime_next_command(action="resume-work")
    if blocked_action == "verify-work":
        return _runtime_next_command(action="verify-work", phase=phase)
    return _runtime_next_command(action="execute-phase", phase=phase)


def _closeout_blocked_action(
    *,
    all_plans_complete: bool,
    active_segment: bool,
    blockers: list[str],
) -> str | None:
    if not all_plans_complete:
        return "execute-phase"
    if active_segment:
        return "resume-work"
    if any(
        "verification" in blocker or "proof-redteam" in blocker or "proof-bearing" in blocker for blocker in blockers
    ):
        return "verify-work"
    return None


def _next_up_payload(
    *,
    phase: str,
    ready: bool,
    closeout_command: str | None,
    cleanup_command: str | None,
    blockers: list[str],
    blocked_action: str | None = None,
) -> LifecycleNextUp:
    if ready and closeout_command is not None:
        return LifecycleNextUp.ready_local_transition(
            phase=phase,
            closeout_command=closeout_command,
            cleanup_command=cleanup_command,
        )

    return LifecycleNextUp.blocked_runtime(
        phase=phase,
        blockers=blockers,
        action=blocked_action,
    )


def _state_position(project_root: Path) -> tuple[str | None, str | None]:
    state = load_state_json_readonly(project_root)
    if not isinstance(state, dict):
        return None, None
    position = state.get("position")
    if not isinstance(position, dict):
        return None, None
    return _state_text(position.get("current_phase")), _state_text(position.get("status"))


def _state_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == "\u2014" or text.lower() in {"none", "no", "not set", "[not set]"}:
        return None
    return text


def _phase_closure(
    project_root: Path,
    phase: str,
) -> tuple[bool, bool, str | None, str | None, str | None]:
    normalized_phase = phase_normalize(phase)
    roadmap_complete = False
    next_phase: str | None = None
    for roadmap_phase in roadmap_analyze(project_root).phases:
        roadmap_number = phase_normalize(roadmap_phase.number)
        if roadmap_number == normalized_phase:
            roadmap_complete = roadmap_phase.roadmap_complete
            continue
        if compare_phase_numbers(roadmap_number, normalized_phase) > 0 and next_phase is None:
            next_phase = roadmap_number

    state_current_phase, state_status = _state_position(project_root)
    normalized_state_phase = phase_normalize(state_current_phase) if state_current_phase else None
    state_status_lower = state_status.lower() if state_status else ""
    state_advanced = (
        normalized_state_phase is not None
        and compare_phase_numbers(normalized_state_phase, normalized_phase) > 0
        and state_status_lower in {"ready to plan", "complete", "milestone complete"}
    )
    state_milestone_closed = normalized_state_phase is None and state_status_lower == "milestone complete"
    return (
        roadmap_complete or state_advanced or state_milestone_closed,
        roadmap_complete,
        next_phase,
        state_current_phase,
        state_status,
    )


def _milestone_version(project_root: Path) -> str | None:
    try:
        from gpd.core.phases import get_milestone_info

        version = str(get_milestone_info(project_root).version).strip()
    except Exception:  # noqa: BLE001 - lifecycle routing should degrade to audit-first
        return None
    return version or None


def _milestone_audit_status(project_root: Path, version: str | None) -> str | None:
    if not version:
        return None
    audit_path = ProjectLayout(project_root).gpd / f"{version}-MILESTONE-AUDIT.md"
    if not audit_path.exists():
        return None
    try:
        from gpd.core.frontmatter import extract_frontmatter

        frontmatter, _body = extract_frontmatter(audit_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - malformed audit should not skip the audit-first route
        return None
    status = frontmatter.get("status") if isinstance(frontmatter, dict) else None
    return str(status).strip().lower() if status is not None else None


def _milestone_archive_exists(project_root: Path, version: str | None) -> bool:
    if not version:
        return False
    archive_dir = ProjectLayout(project_root).gpd / "milestones"
    return (archive_dir / f"{version}-ROADMAP.md").exists() or (archive_dir / f"{version}-REQUIREMENTS.md").exists()


def _closed_milestone_status_class(project_root: Path, version: str | None) -> CanonicalLifecycleClass:
    if _milestone_archive_exists(project_root, version):
        return "archived_ready_for_next_milestone"
    if _milestone_audit_status(project_root, version) == "passed":
        return "closed_ready_for_milestone_archive"
    return "closed_needs_milestone_audit"


def _closed_next_up(
    *,
    project_root: Path,
    phase: str,
    next_phase: str | None,
    milestone_complete: bool,
) -> LifecycleNextUp:
    if not milestone_complete and next_phase is not None:
        return LifecycleNextUp.closed_runtime(
            phase=phase,
            next_phase=next_phase,
            status_class="closed_ready_next_phase",
        )

    version = _milestone_version(project_root)
    return LifecycleNextUp.closed_runtime(
        phase=phase,
        next_phase=None,
        status_class=_closed_milestone_status_class(project_root, version),
        milestone_version=version,
    )


def _decision_from_closeout(
    *,
    closeout: PhaseCloseoutReadiness,
    lifecycle_next_up: LifecycleNextUp,
    phase_closed: bool,
    next_phase: str | None,
    state_status: str | None,
) -> tuple[LifecycleDecisionKind, CanonicalLifecycleClass, str | None, str | None, str | None]:
    action = lifecycle_next_up.primary.action
    owner = lifecycle_next_up.primary.owner
    command = lifecycle_next_up.primary.command

    if phase_closed:
        milestone_complete = (state_status or "").lower() == "milestone complete" or next_phase is None
        decision: LifecycleDecisionKind = (
            "closed_milestone_complete" if milestone_complete else "closed_ready_next_phase"
        )
        return decision, lifecycle_next_up.status_class, action, owner, command

    if not closeout.all_plans_complete:
        return "needs_execution", lifecycle_next_up.status_class, action, owner, command

    if closeout.active_bounded_segment:
        return "blocked_closeout", lifecycle_next_up.status_class, action, owner, command

    if any("verification" in blocker for blocker in closeout.blockers):
        return "needs_verification", lifecycle_next_up.status_class, action, owner, command

    if closeout.ready:
        return "ready_for_closeout", lifecycle_next_up.status_class, action, owner, command

    return "blocked_closeout", lifecycle_next_up.status_class, action, owner, command


def _missing_project_decision(
    project_root: Path,
    phase: str,
    *,
    require_verification: bool,
) -> PhaseLifecycleDecision:
    blockers = ["phase closeout requires a visible GPD/ project root"]
    next_up = _next_up_payload(
        phase=phase,
        ready=False,
        closeout_command=None,
        cleanup_command=None,
        blockers=blockers,
    )
    next_up_payload = next_up.as_legacy_next_up_dict()
    closeout = PhaseCloseoutReadiness(
        phase=phase,
        ready=False,
        mutation_allowed=False,
        project_root=project_root.as_posix(),
        require_verification=require_verification,
        preserve_checkpoint_tags=True,
        blockers=blockers,
        lifecycle_next_up=next_up,
        next_up=next_up_payload,
    )
    return PhaseLifecycleDecision(
        phase=phase,
        project_root=project_root.as_posix(),
        decision="blocked_closeout",
        lifecycle_class=next_up.status_class,
        primary_action=next_up.primary.action,
        primary_owner=next_up.primary.owner,
        primary_command=next_up.primary.command,
        lifecycle_next_up=next_up,
        next_up=next_up_payload,
        closeout_readiness=closeout,
    )


def _missing_phase_decision(
    project_root: Path,
    phase: str,
    *,
    require_verification: bool,
    blockers: list[str],
) -> PhaseLifecycleDecision:
    next_up = _next_up_payload(
        phase=phase,
        ready=False,
        closeout_command=None,
        cleanup_command=None,
        blockers=blockers,
    )
    next_up_payload = next_up.as_legacy_next_up_dict()
    closeout = PhaseCloseoutReadiness(
        phase=phase,
        ready=False,
        mutation_allowed=False,
        project_root=project_root.as_posix(),
        require_verification=require_verification,
        preserve_checkpoint_tags=True,
        blockers=blockers,
        lifecycle_next_up=next_up,
        next_up=next_up_payload,
    )
    return PhaseLifecycleDecision(
        phase=phase,
        project_root=project_root.as_posix(),
        decision="blocked_closeout",
        lifecycle_class=next_up.status_class,
        primary_action=next_up.primary.action,
        primary_owner=next_up.primary.owner,
        primary_command=next_up.primary.command,
        lifecycle_next_up=next_up,
        next_up=next_up_payload,
        closeout_readiness=closeout,
    )


def phase_lifecycle_decision(
    cwd: Path,
    phase: str,
    *,
    require_verification: bool = True,
) -> PhaseLifecycleDecision:
    """Return the read-only lifecycle decision for one phase."""

    project_root = cwd.expanduser().resolve(strict=False)
    normalized_phase = phase_normalize(str(phase).strip())
    blockers: list[str] = []
    warnings: list[str] = []

    if not ProjectLayout(project_root).gpd.is_dir():
        return _missing_project_decision(
            project_root,
            normalized_phase,
            require_verification=require_verification,
        )

    try:
        phase_info = find_phase(project_root, normalized_phase)
    except PhaseAmbiguityError as exc:
        phase_info = None
        blockers.append(str(exc))
    if phase_info is None:
        blockers.append(f"Phase {normalized_phase} not found")
        return _missing_phase_decision(
            project_root,
            normalized_phase,
            require_verification=require_verification,
            blockers=blockers,
        )

    phase_dir = project_root / phase_info.directory
    plan_count = len(phase_info.plans)
    summary_count = matching_phase_artifact_count(phase_info.plans, phase_info.summaries)
    all_plans_complete = is_phase_complete(plan_count, summary_count)
    incomplete_plans = list(phase_info.incomplete_plans)
    if plan_count == 0:
        blockers.append("phase has no plans to close out")
    if not all_plans_complete:
        blockers.append(f"phase summaries incomplete: {summary_count}/{plan_count} plans have summaries")
        blockers.extend(f"missing summary for {plan}" for plan in incomplete_plans)

    verification_path = verification_path_for_phase(project_root, phase_info.phase_number)
    verification = read_verification_status(verification_path) if verification_path else None
    verification_status = verification.status if verification is not None else None
    verification_routing_status = verification.routing_status if verification is not None else "missing"
    verification_ref = _relative(project_root, verification_path)

    if require_verification and verification_status != "passed":
        if verification_path is None:
            blockers.append("canonical verification report missing")
        elif verification is not None and verification.errors:
            blockers.extend(f"canonical verification report blocked: {error}" for error in verification.errors)
        else:
            blockers.append(
                "canonical verification report must have top-level frontmatter status 'passed'; "
                f"got {verification_routing_status!r}"
            )
    elif not require_verification and verification_status != "passed":
        warnings.append(f"canonical verification status is {verification_routing_status!r}")

    proof_required, proof_ready, proof_artifacts, proof_errors = _proof_redteam_status(project_root, phase_dir)
    if not proof_ready:
        blockers.extend(proof_errors)

    active_segment, _bounded_segment, active_segment_blockers = _active_bounded_segment(project_root)
    blockers.extend(active_segment_blockers)

    recovery_artifacts = _phase_recovery_artifacts(project_root, phase_dir)
    if recovery_artifacts:
        warnings.append("phase recovery artifacts present; checkpoint tags should be preserved")

    tags, tag_warnings = _checkpoint_tags(project_root, phase_info.phase_number)
    warnings.extend(tag_warnings)

    phase_closed, roadmap_complete, next_phase, state_current_phase, state_status = _phase_closure(
        project_root,
        phase_info.phase_number,
    )
    if phase_closed:
        blockers.append("phase already closed; no closeout mutation needed")

    ready = not blockers
    preserve_checkpoint_tags = bool(blockers or recovery_artifacts)
    closeout_command = f"gpd phase complete {phase_info.phase_number}" if ready else None
    cleanup_command = (
        f"gpd --raw phase checkpoint cleanup --phase {phase_info.phase_number} "
        "--namespace phase --policy successful-closeout"
        if ready and not preserve_checkpoint_tags
        else None
    )
    next_up = _next_up_payload(
        phase=phase_info.phase_number,
        ready=ready,
        closeout_command=closeout_command,
        cleanup_command=cleanup_command,
        blockers=blockers,
        blocked_action=_closeout_blocked_action(
            all_plans_complete=all_plans_complete,
            active_segment=active_segment,
            blockers=blockers,
        ),
    )
    if phase_closed:
        next_up = _closed_next_up(
            project_root=project_root,
            phase=phase_info.phase_number,
            next_phase=next_phase,
            milestone_complete=(state_status or "").lower() == "milestone complete" or next_phase is None,
        )
    next_up_payload = next_up.as_legacy_next_up_dict()

    closeout = PhaseCloseoutReadiness(
        phase=phase_info.phase_number,
        ready=ready,
        mutation_allowed=ready,
        project_root=project_root.as_posix(),
        phase_dir=_relative(project_root, phase_dir),
        plan_count=plan_count,
        summary_count=summary_count,
        all_plans_complete=all_plans_complete,
        incomplete_plans=incomplete_plans,
        verification_path=verification_ref,
        verification_status=verification_status,
        verification_routing_status=verification_routing_status,
        require_verification=require_verification,
        proof_redteam_required=proof_required,
        proof_redteam_ready=proof_ready,
        proof_redteam_artifacts=proof_artifacts,
        active_bounded_segment=active_segment,
        checkpoint_tags=tags,
        preserve_checkpoint_tags=preserve_checkpoint_tags,
        recovery_artifacts=recovery_artifacts,
        blockers=blockers,
        warnings=warnings,
        closeout_command=closeout_command,
        cleanup_command=cleanup_command,
        closeout_command_hint=_hint(
            closeout_command,
            action="phase-complete",
            phase=phase_info.phase_number,
            owner=OWNER_LOCAL_TRANSITION,
            role=ROLE_PRIMARY,
        ),
        cleanup_command_hint=_hint(
            cleanup_command,
            action="checkpoint-cleanup",
            phase=phase_info.phase_number,
            owner=OWNER_LOCAL_HELPER,
            role=ROLE_SECONDARY,
        ),
        lifecycle_next_up=next_up,
        next_up=next_up_payload,
    )
    decision, lifecycle_class, primary_action, primary_owner, primary_command = _decision_from_closeout(
        closeout=closeout,
        lifecycle_next_up=next_up,
        phase_closed=phase_closed,
        next_phase=next_phase,
        state_status=state_status,
    )

    return PhaseLifecycleDecision(
        phase=phase_info.phase_number,
        project_root=project_root.as_posix(),
        phase_dir=_relative(project_root, phase_dir),
        state_current_phase=state_current_phase,
        state_status=state_status,
        roadmap_complete=roadmap_complete,
        disk_complete=all_plans_complete,
        plan_count=plan_count,
        summary_count=summary_count,
        verification_path=verification_ref,
        verification_status=verification_status,
        verification_routing_status=verification_routing_status,
        closeout_ready=closeout.ready,
        closeout_blockers=closeout.blockers,
        closeout_warnings=closeout.warnings,
        phase_closed=phase_closed,
        next_phase=next_phase,
        decision=decision,
        lifecycle_class=lifecycle_class,
        primary_action=primary_action,
        primary_owner=primary_owner,
        primary_command=primary_command,
        lifecycle_next_up=next_up,
        next_up=next_up_payload,
        closeout_readiness=closeout,
    )


__all__ = [
    "CanonicalLifecycleClass",
    "LifecycleNextUp",
    "OWNER_LOCAL_HELPER",
    "OWNER_LOCAL_TRANSITION",
    "OWNER_RUNTIME",
    "PhaseCloseoutReadiness",
    "PhaseLifecycleDecision",
    "phase_lifecycle_decision",
]
