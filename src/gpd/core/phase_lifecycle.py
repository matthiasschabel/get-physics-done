"""Read-only phase lifecycle decisions shared by closeout-facing surfaces."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gpd.core.command_run_hints import build_command_run_hint
from gpd.core.constants import ProjectLayout
from gpd.core.phases import PhaseAmbiguityError, find_phase, roadmap_analyze
from gpd.core.state import load_state_json_readonly
from gpd.core.utils import (
    compare_phase_numbers,
    is_phase_complete,
    matching_phase_artifact_count,
    phase_normalize,
)
from gpd.core.verification_status import read_verification_status, verification_path_for_phase

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

OWNER_RUNTIME = "runtime"
OWNER_LOCAL_TRANSITION = "local_transition"
OWNER_LOCAL_HELPER = "local_helper"
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
    primary_action: str | None = None
    primary_owner: str | None = None
    primary_command: str | None = None
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


def _hint(
    command: str | None,
    *,
    action: str | None,
    phase: str,
    owner: str | None = None,
    role: str | None = None,
) -> dict[str, object] | None:
    hint = build_command_run_hint(command=command, source="phase-closeout-readiness", action=action, phase=phase)
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


def _next_up_payload(
    *,
    phase: str,
    ready: bool,
    closeout_command: str | None,
    cleanup_command: str | None,
    blockers: list[str],
) -> dict[str, object]:
    if ready and closeout_command is not None:
        primary_hint = _hint(
            closeout_command,
            action="phase-complete",
            phase=phase,
            owner=OWNER_LOCAL_TRANSITION,
            role=ROLE_PRIMARY,
        )
        secondary_commands: list[dict[str, object]] = []
        if cleanup_command is not None:
            cleanup_hint = _hint(
                cleanup_command,
                action="checkpoint-cleanup",
                phase=phase,
                owner=OWNER_LOCAL_HELPER,
                role=ROLE_SECONDARY,
            )
            if cleanup_hint is not None:
                secondary_commands.append(cleanup_hint)
        commands = [hint for hint in (primary_hint, *secondary_commands) if hint is not None]
        return {
            "status": "ready",
            "primary": closeout_command,
            "primary_owner": OWNER_LOCAL_TRANSITION,
            "primary_label": "Primary local transition",
            "secondary": secondary_commands,
            "commands": commands,
        }

    if any(
        "verification" in blocker or "proof-redteam" in blocker or "proof-bearing" in blocker for blocker in blockers
    ):
        primary = f"gpd:verify-work {phase}"
        action = "verify-work"
    elif any("bounded segment" in blocker for blocker in blockers):
        primary = "gpd:resume-work"
        action = "resume-work"
    else:
        primary = f"gpd:execute-phase {phase}"
        action = "execute-phase"

    return {
        "status": "blocked",
        "primary": primary,
        "primary_owner": OWNER_RUNTIME,
        "primary_label": "Primary",
        "commands": [_hint(primary, action=action, phase=phase, owner=OWNER_RUNTIME, role=ROLE_PRIMARY)],
        "blockers": blockers,
    }


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


def _closed_next_up(
    *,
    phase: str,
    next_phase: str | None,
    milestone_complete: bool,
) -> tuple[dict[str, object], str | None, str | None, str | None]:
    if milestone_complete or next_phase is None:
        primary = "gpd:audit-milestone"
        action = "audit-milestone"
    else:
        primary = f"gpd:plan-phase {next_phase}"
        action = "plan-phase"

    next_up = {
        "status": "closed",
        "primary": primary,
        "primary_owner": OWNER_RUNTIME,
        "primary_label": "Primary",
        "commands": [_hint(primary, action=action, phase=phase, owner=OWNER_RUNTIME, role=ROLE_PRIMARY)],
    }
    return next_up, action, OWNER_RUNTIME, primary


def _decision_from_closeout(
    *,
    closeout: PhaseCloseoutReadiness,
    phase_closed: bool,
    next_phase: str | None,
    state_status: str | None,
) -> tuple[LifecycleDecisionKind, dict[str, object], str | None, str | None, str | None]:
    if phase_closed:
        milestone_complete = (state_status or "").lower() == "milestone complete" or next_phase is None
        next_up, action, owner, command = _closed_next_up(
            phase=closeout.phase,
            next_phase=next_phase,
            milestone_complete=milestone_complete,
        )
        decision: LifecycleDecisionKind = (
            "closed_milestone_complete" if milestone_complete else "closed_ready_next_phase"
        )
        return decision, next_up, action, owner, command

    if not closeout.all_plans_complete:
        return (
            "needs_execution",
            closeout.next_up,
            "execute-phase",
            OWNER_RUNTIME,
            f"gpd:execute-phase {closeout.phase}",
        )

    if any("verification" in blocker for blocker in closeout.blockers):
        return "needs_verification", closeout.next_up, "verify-work", OWNER_RUNTIME, f"gpd:verify-work {closeout.phase}"

    if closeout.ready:
        return (
            "ready_for_closeout",
            closeout.next_up,
            "phase-complete",
            OWNER_LOCAL_TRANSITION,
            closeout.closeout_command,
        )

    primary = closeout.next_up.get("primary") if isinstance(closeout.next_up, dict) else None
    owner = closeout.next_up.get("primary_owner") if isinstance(closeout.next_up, dict) else None
    primary_text = str(primary) if primary is not None else None
    owner_text = str(owner) if owner is not None else None
    action = None
    if primary_text == "gpd:resume-work":
        action = "resume-work"
    elif primary_text and primary_text.startswith("gpd:verify-work"):
        action = "verify-work"
    elif primary_text and primary_text.startswith("gpd:execute-phase"):
        action = "execute-phase"
    return "blocked_closeout", closeout.next_up, action, owner_text, primary_text


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
    closeout = PhaseCloseoutReadiness(
        phase=phase,
        ready=False,
        mutation_allowed=False,
        project_root=project_root.as_posix(),
        require_verification=require_verification,
        preserve_checkpoint_tags=True,
        blockers=blockers,
        next_up=next_up,
    )
    return PhaseLifecycleDecision(
        phase=phase,
        project_root=project_root.as_posix(),
        decision="blocked_closeout",
        primary_action="execute-phase",
        primary_owner=OWNER_RUNTIME,
        primary_command=f"gpd:execute-phase {phase}",
        next_up=next_up,
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
    closeout = PhaseCloseoutReadiness(
        phase=phase,
        ready=False,
        mutation_allowed=False,
        project_root=project_root.as_posix(),
        require_verification=require_verification,
        preserve_checkpoint_tags=True,
        blockers=blockers,
        next_up=next_up,
    )
    return PhaseLifecycleDecision(
        phase=phase,
        project_root=project_root.as_posix(),
        decision="blocked_closeout",
        primary_action="execute-phase",
        primary_owner=OWNER_RUNTIME,
        primary_command=f"gpd:execute-phase {phase}",
        next_up=next_up,
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
    )
    if phase_closed:
        next_up, _closed_action, _closed_owner, _closed_command = _closed_next_up(
            phase=phase_info.phase_number,
            next_phase=next_phase,
            milestone_complete=(state_status or "").lower() == "milestone complete" or next_phase is None,
        )

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
        next_up=next_up,
    )
    decision, decision_next_up, primary_action, primary_owner, primary_command = _decision_from_closeout(
        closeout=closeout,
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
        primary_action=primary_action,
        primary_owner=primary_owner,
        primary_command=primary_command,
        next_up=decision_next_up,
        closeout_readiness=closeout,
    )


__all__ = [
    "OWNER_LOCAL_HELPER",
    "OWNER_LOCAL_TRANSITION",
    "OWNER_RUNTIME",
    "PhaseCloseoutReadiness",
    "PhaseLifecycleDecision",
    "phase_lifecycle_decision",
]
