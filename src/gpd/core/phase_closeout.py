"""Read-only phase closeout readiness checks."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from gpd.core.command_run_hints import build_command_run_hint
from gpd.core.constants import ProjectLayout
from gpd.core.phases import PhaseAmbiguityError, find_phase
from gpd.core.state import load_state_json_readonly
from gpd.core.utils import is_phase_complete, phase_normalize
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

    if any("verification" in blocker for blocker in blockers):
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


def phase_closeout_readiness(
    cwd: Path,
    phase: str,
    *,
    require_verification: bool = False,
) -> PhaseCloseoutReadiness:
    """Return a read-only closeout gate result; never mutate roadmap, state, or tags."""

    project_root = cwd.expanduser().resolve(strict=False)
    normalized_phase = phase_normalize(str(phase).strip())
    blockers: list[str] = []
    warnings: list[str] = []

    if not ProjectLayout(project_root).gpd.is_dir():
        blockers.append("phase closeout requires a visible GPD/ project root")
        ready = False
        next_up = _next_up_payload(
            phase=normalized_phase,
            ready=ready,
            closeout_command=None,
            cleanup_command=None,
            blockers=blockers,
        )
        return PhaseCloseoutReadiness(
            phase=normalized_phase,
            ready=ready,
            mutation_allowed=False,
            project_root=project_root.as_posix(),
            require_verification=require_verification,
            preserve_checkpoint_tags=True,
            blockers=blockers,
            next_up=next_up,
        )

    try:
        phase_info = find_phase(project_root, normalized_phase)
    except PhaseAmbiguityError as exc:
        phase_info = None
        blockers.append(str(exc))
    if phase_info is None:
        blockers.append(f"Phase {normalized_phase} not found")
        ready = False
        next_up = _next_up_payload(
            phase=normalized_phase,
            ready=ready,
            closeout_command=None,
            cleanup_command=None,
            blockers=blockers,
        )
        return PhaseCloseoutReadiness(
            phase=normalized_phase,
            ready=ready,
            mutation_allowed=False,
            project_root=project_root.as_posix(),
            require_verification=require_verification,
            preserve_checkpoint_tags=True,
            blockers=blockers,
            next_up=next_up,
        )

    phase_dir = project_root / phase_info.directory
    plan_count = len(phase_info.plans)
    summary_count = len(phase_info.summaries)
    all_plans_complete = plan_count > 0 and is_phase_complete(plan_count, summary_count)
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

    return PhaseCloseoutReadiness(
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


__all__ = [
    "PhaseCloseoutReadiness",
    "phase_closeout_readiness",
]
