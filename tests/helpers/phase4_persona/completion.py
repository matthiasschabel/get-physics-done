"""Provider-free Phase 4 completion and verification replay helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from gpd.adapters import get_adapter
from gpd.adapters.runtime_catalog import iter_runtime_descriptors
from gpd.core.phase_closeout import PhaseCloseoutReadiness, phase_closeout_readiness
from gpd.core.proof_redteam import build_proof_redteam_skeleton
from gpd.core.state import (
    default_state_dict,
    generate_state_markdown,
    load_state_json_readonly,
    state_record_verification,
)
from gpd.core.suggest import suggest_next
from tests.runtime_install_helpers import seed_complete_runtime_install

SCHEMA_VERSION = "phase4.persona_completion_replay.v1"
PHASE = "02"
PHASE_NAME = "analysis"
PHASE_READY_STATUS = "Phase complete \u2014 ready for verification"
_NON_PASSING_VERIFICATION_STATUSES = ("gaps_found", "human_needed", "expert_needed")


class _MonkeyPatch(Protocol):
    def setenv(self, name: str, value: str) -> None: ...


@dataclass(frozen=True)
class CompletionReplayRow:
    """Class-only replay row for Phase 4 completion behavior."""

    row_id: str
    scenario: str
    expected_finding: str
    expected_result_class: str
    expected_ready: bool | None = None
    expected_state_status_class: str | None = None
    expected_next_action_class: str | None = None
    expect_no_mutation: bool = True
    schema_version: str = SCHEMA_VERSION
    surface: str = "completion"
    fixture_family: str = "completion_verification_replay"
    runtime_scope: str = "provider_free"
    provider_launch_allowed: bool = False
    network_allowed: bool = False
    raw_artifacts_allowed: bool = False
    source_owners: tuple[str, ...] = (
        "src/gpd/core/phase_closeout.py",
        "src/gpd/core/state.py",
        "src/gpd/core/suggest.py",
    )
    test_owners: tuple[str, ...] = (
        "tests/helpers/phase4_persona/completion.py",
        "tests/core/test_phase4_persona_completion_replay.py",
    )


@dataclass(frozen=True)
class CompletionReplayOutcome:
    """Class-only replay outcome; no provider output or raw transcripts."""

    finding_id: str
    result_class: str
    failure_classes: tuple[str, ...] = ()
    ready: bool | None = None
    mutated: bool = False
    read_only: bool = True
    mutation_allowed: bool | None = None
    state_status_class: str | None = None
    next_action_class: str | None = None
    commands: tuple[str, ...] = ()
    provider_launch_allowed: bool = False
    network_allowed: bool = False
    raw_artifacts_allowed: bool = False


_ROWS = (
    CompletionReplayRow(
        "P4-COMP-01",
        "missing_verification_blocks_required_closeout",
        "missing_verification_blocks_closeout",
        "blocked_closeout",
        expected_ready=False,
        expected_next_action_class="verify_work",
    ),
    CompletionReplayRow(
        "P4-COMP-02",
        "gaps_found_verification_blocks",
        "gaps_found_verification_blocks",
        "blocked_verification",
        expected_ready=False,
        expected_state_status_class="blocked",
        expected_next_action_class="verify_work",
        expect_no_mutation=False,
    ),
    CompletionReplayRow(
        "P4-COMP-03",
        "human_needed_verification_blocks",
        "human_needed_verification_blocks",
        "blocked_verification",
        expected_ready=False,
        expected_state_status_class="blocked",
        expected_next_action_class="verify_work",
        expect_no_mutation=False,
    ),
    CompletionReplayRow(
        "P4-COMP-04",
        "expert_needed_verification_blocks",
        "expert_needed_verification_blocks",
        "blocked_verification",
        expected_ready=False,
        expected_state_status_class="blocked",
        expected_next_action_class="verify_work",
        expect_no_mutation=False,
    ),
    CompletionReplayRow(
        "P4-COMP-05",
        "passed_verification_closeout_ready",
        "passed_verification_allows_readiness",
        "ready_closeout",
        expected_ready=True,
        expected_next_action_class="phase_complete",
    ),
    CompletionReplayRow(
        "P4-COMP-06",
        "bounded_segment_blocks_closeout",
        "bounded_segment_blocks_closeout",
        "blocked_closeout",
        expected_ready=False,
        expected_next_action_class="resume_work",
    ),
    CompletionReplayRow(
        "P4-COMP-07",
        "proof_bearing_without_passed_proof_redteam_blocks_closeout",
        "proof_redteam_not_passed_blocks_closeout",
        "blocked_closeout",
        expected_ready=False,
    ),
    CompletionReplayRow(
        "P4-COMP-08",
        "completed_phase_suggests_runtime_verify_work",
        "runtime_verify_work_suggestion",
        "ready_for_runtime_verification",
        expected_next_action_class="runtime_verify_work",
    ),
    CompletionReplayRow(
        "P4-COMP-09",
        "closeout_readiness_read_only_no_mutation",
        "closeout_readiness_read_only",
        "read_only_ready_closeout",
        expected_ready=True,
        expected_next_action_class="phase_complete",
    ),
)


def completion_replay_rows() -> tuple[CompletionReplayRow, ...]:
    """Return the provider-free Phase 4 completion replay matrix."""

    return _ROWS


def score_completion_replay_row(
    row: CompletionReplayRow,
    root: Path,
    monkeypatch: _MonkeyPatch | None = None,
) -> CompletionReplayOutcome:
    """Score one completion replay row against real lifecycle APIs."""

    if monkeypatch is not None:
        monkeypatch.setenv("GPD_DATA_DIR", str(root / ".gpd-data"))

    match row.scenario:
        case "missing_verification_blocks_required_closeout":
            return _score_missing_verification_blocks_required_closeout(root)
        case "gaps_found_verification_blocks":
            return _score_non_passing_verification_blocks(root, "gaps_found")
        case "human_needed_verification_blocks":
            return _score_non_passing_verification_blocks(root, "human_needed")
        case "expert_needed_verification_blocks":
            return _score_non_passing_verification_blocks(root, "expert_needed")
        case "passed_verification_closeout_ready":
            return _score_passed_verification_closeout_ready(root)
        case "bounded_segment_blocks_closeout":
            return _score_bounded_segment_blocks_closeout(root)
        case "proof_bearing_without_passed_proof_redteam_blocks_closeout":
            return _score_proof_bearing_without_passed_proof_redteam_blocks_closeout(root)
        case "completed_phase_suggests_runtime_verify_work":
            return _score_completed_phase_suggests_runtime_verify_work(root)
        case "closeout_readiness_read_only_no_mutation":
            return _score_closeout_readiness_read_only_no_mutation(root)
    raise AssertionError(f"unhandled completion replay scenario: {row.scenario}")


def _write_phase_project(
    root: Path,
    *,
    status: str = PHASE_READY_STATUS,
    verification_status: str | None = None,
    bounded_segment: bool = False,
    proof_bearing: bool = False,
    recovery: bool = False,
) -> Path:
    gpd_dir = root / "GPD"
    phase_dir = gpd_dir / "phases" / f"{PHASE}-{PHASE_NAME}"
    phase_dir.mkdir(parents=True)
    (gpd_dir / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
    (gpd_dir / "ROADMAP.md").write_text(
        "# Roadmap\n\n## Phase 1: Setup\n\n## Phase 2: Analysis\n\n## Phase 3: Synthesis\n",
        encoding="utf-8",
    )
    for index in range(1, 3):
        proof_flag = "proof_bearing: true\n" if proof_bearing and index == 1 else ""
        (phase_dir / f"{PHASE}-{index:02d}-PLAN.md").write_text(
            f"---\nwave: {index}\n{proof_flag}---\n\n# Plan {index}\n",
            encoding="utf-8",
        )
        (phase_dir / f"{PHASE}-{index:02d}-SUMMARY.md").write_text(
            f"# Summary {index}\n",
            encoding="utf-8",
        )
    if verification_status is not None:
        _write_verification_report(phase_dir, verification_status)
    if recovery:
        (phase_dir / "RECOVERY-02.md").write_text("# Recovery\n", encoding="utf-8")

    state = default_state_dict()
    state["position"]["current_phase"] = PHASE
    state["position"]["current_phase_name"] = "Analysis"
    state["position"]["current_plan"] = "2"
    state["position"]["total_plans_in_phase"] = 2
    state["position"]["total_phases"] = 3
    state["position"]["progress_percent"] = 66
    state["position"]["status"] = status
    if bounded_segment:
        state["continuation"]["bounded_segment"] = {
            "resume_file": f"GPD/phases/{PHASE}-{PHASE_NAME}/.continue-here.md",
            "phase": PHASE,
            "plan": "02",
            "segment_id": "seg-02-02",
            "segment_status": "paused",
            "waiting_for_review": True,
        }
        (phase_dir / ".continue-here.md").write_text("Resume bounded segment.\n", encoding="utf-8")

    (gpd_dir / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    (gpd_dir / "STATE.md").write_text(generate_state_markdown(state), encoding="utf-8")
    return phase_dir


def _write_verification_report(phase_dir: Path, status: str) -> None:
    score = "1/1 contract targets verified" if status == "passed" else "0/1 contract targets verified"
    verdict = "PASS" if status == "passed" else "FAIL"
    phase_dir.joinpath(f"{PHASE}-VERIFICATION.md").write_text(
        "---\n"
        f"phase: {PHASE}-{PHASE_NAME}\n"
        'verified: "2026-05-09T00:00:00Z"\n'
        f"status: {status}\n"
        f'score: "{score}"\n'
        "---\n\n"
        f"# Phase {PHASE} Verification\n\n"
        f"{verdict}: replay fixture status is {status}.\n",
        encoding="utf-8",
    )


def _snapshot_tree(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    snapshot: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            snapshot[path.relative_to(root).as_posix()] = path.read_bytes()
    return snapshot


def _read_position_status(root: Path) -> str | None:
    state = load_state_json_readonly(root)
    position = state.get("position") if isinstance(state, dict) else None
    if isinstance(position, dict):
        status = position.get("status")
        return str(status) if status is not None else None
    return None


def _status_class(status: str | None) -> str | None:
    if status is None:
        return None
    normalized = status.strip().lower()
    if normalized == "verified":
        return "verified"
    if normalized == "blocked":
        return "blocked"
    if normalized == PHASE_READY_STATUS.lower():
        return "phase_ready_for_verification"
    return normalized.replace(" ", "_").replace("-", "_")


def _next_action_class(command: str | None) -> str | None:
    if not command:
        return None
    command = command.strip()
    if command == "gpd:resume-work":
        return "resume_work"
    if command.startswith("gpd phase complete"):
        return "phase_complete"
    if command.startswith("gpd:execute-phase"):
        return "execute_phase"
    if "verify-work" in command and "gpd verify phase" not in command:
        if command.startswith(("gpd:", "$", "/")):
            return "runtime_verify_work" if not command.startswith("gpd:") else "verify_work"
        return "verify_work"
    if command.startswith("gpd verify phase"):
        return "structural_verify_phase"
    return "unknown"


def _closeout_failure_classes(result: PhaseCloseoutReadiness) -> tuple[str, ...]:
    classes: list[str] = []
    if result.ready:
        classes.append("closeout_ready")
    else:
        classes.append("closeout_blocked")
    if result.verification_routing_status == "missing":
        classes.append("missing_verification")
    elif result.verification_status in _NON_PASSING_VERIFICATION_STATUSES:
        classes.append(str(result.verification_status))
        classes.append("non_passing_verification")
    elif result.verification_status == "passed":
        classes.append("passed_verification")
    if result.active_bounded_segment:
        classes.append("active_bounded_segment")
    if result.proof_redteam_required and not result.proof_redteam_ready:
        classes.append("proof_redteam_not_passed")
    if result.read_only:
        classes.append("read_only")
    return tuple(dict.fromkeys(classes))


def _readiness_outcome(
    *,
    result: PhaseCloseoutReadiness,
    finding_id: str,
    result_class: str,
    mutated: bool,
) -> CompletionReplayOutcome:
    primary = result.next_up.get("primary")
    primary_command = str(primary) if primary is not None else None
    return CompletionReplayOutcome(
        finding_id=finding_id,
        result_class=result_class,
        failure_classes=_closeout_failure_classes(result),
        ready=result.ready,
        mutated=mutated or result.mutated,
        read_only=result.read_only,
        mutation_allowed=result.mutation_allowed,
        state_status_class=_status_class(_read_position_status(Path(result.project_root))),
        next_action_class=_next_action_class(primary_command),
        commands=(primary_command,) if primary_command else (),
    )


def _score_missing_verification_blocks_required_closeout(root: Path) -> CompletionReplayOutcome:
    _write_phase_project(root, verification_status=None)
    before = _snapshot_tree(root / "GPD")

    result = phase_closeout_readiness(root, PHASE, require_verification=True)

    return _readiness_outcome(
        result=result,
        finding_id="missing_verification_blocks_closeout",
        result_class="blocked_closeout",
        mutated=_snapshot_tree(root / "GPD") != before,
    )


def _score_non_passing_verification_blocks(root: Path, verification_status: str) -> CompletionReplayOutcome:
    _write_phase_project(root, verification_status=verification_status)
    before_record = _snapshot_tree(root / "GPD")

    record_result = state_record_verification(root, phase=PHASE)
    readiness = phase_closeout_readiness(root, PHASE, require_verification=True)
    state_status_class = _status_class(_read_position_status(root))
    primary = readiness.next_up.get("primary")
    primary_command = str(primary) if primary is not None else None

    return CompletionReplayOutcome(
        finding_id=f"{verification_status}_verification_blocks",
        result_class="blocked_verification",
        failure_classes=(
            verification_status,
            "non_passing_verification",
            "recorded_blocked" if record_result.recorded else "record_failed",
            *_closeout_failure_classes(readiness),
        ),
        ready=readiness.ready,
        mutated=_snapshot_tree(root / "GPD") != before_record,
        read_only=readiness.read_only,
        mutation_allowed=readiness.mutation_allowed,
        state_status_class=state_status_class,
        next_action_class=_next_action_class(primary_command),
        commands=(primary_command,) if primary_command else (),
    )


def _score_passed_verification_closeout_ready(root: Path) -> CompletionReplayOutcome:
    _write_phase_project(root, verification_status="passed")
    before = _snapshot_tree(root / "GPD")

    result = phase_closeout_readiness(root, PHASE, require_verification=True)

    return _readiness_outcome(
        result=result,
        finding_id="passed_verification_allows_readiness",
        result_class="ready_closeout",
        mutated=_snapshot_tree(root / "GPD") != before,
    )


def _score_bounded_segment_blocks_closeout(root: Path) -> CompletionReplayOutcome:
    _write_phase_project(root, verification_status="passed", bounded_segment=True)
    before = _snapshot_tree(root / "GPD")

    result = phase_closeout_readiness(root, PHASE, require_verification=True)

    return _readiness_outcome(
        result=result,
        finding_id="bounded_segment_blocks_closeout",
        result_class="blocked_closeout",
        mutated=_snapshot_tree(root / "GPD") != before,
    )


def _score_proof_bearing_without_passed_proof_redteam_blocks_closeout(root: Path) -> CompletionReplayOutcome:
    phase_dir = _write_phase_project(root, verification_status="passed", proof_bearing=True)
    skeleton = build_proof_redteam_skeleton(
        claim_id="claim-a",
        proof_artifact_paths=[f"GPD/phases/{PHASE}-{PHASE_NAME}/{PHASE}-01-PLAN.md"],
        status="gaps_found",
    )
    (phase_dir / f"{PHASE}-01-PROOF-REDTEAM.md").write_text(skeleton.markdown_draft, encoding="utf-8")
    before = _snapshot_tree(root / "GPD")

    result = phase_closeout_readiness(root, PHASE, require_verification=True)

    return _readiness_outcome(
        result=result,
        finding_id="proof_redteam_not_passed_blocks_closeout",
        result_class="blocked_closeout",
        mutated=_snapshot_tree(root / "GPD") != before,
    )


def _score_completed_phase_suggests_runtime_verify_work(root: Path) -> CompletionReplayOutcome:
    commands: list[str] = []
    failures: list[str] = []
    mutated = False

    for descriptor in iter_runtime_descriptors():
        runtime = descriptor.runtime_name
        runtime_root = root / runtime
        adapter = get_adapter(runtime)
        seed_complete_runtime_install(runtime_root / adapter.local_config_dir_name, runtime=runtime)
        _write_phase_project(runtime_root, verification_status=None)
        before = _snapshot_tree(runtime_root)

        result = suggest_next(runtime_root)
        verify = next((suggestion for suggestion in result.suggestions if suggestion.action == "verify-work"), None)
        expected_command = f"{adapter.format_command('verify-work')} {PHASE}"
        if verify is None:
            failures.append(f"{runtime}:missing_verify_work")
            continue
        commands.append(verify.command)
        if verify.command != expected_command:
            failures.append(f"{runtime}:unexpected_runtime_command")
        if "gpd verify phase" in verify.command:
            failures.append(f"{runtime}:structural_verify_phase")
        if "verify-work" not in verify.command:
            failures.append(f"{runtime}:missing_verify_work_token")
        mutated = mutated or _snapshot_tree(runtime_root) != before

    result_class = "ready_for_runtime_verification" if not failures else "blocked_runtime_verification"
    return CompletionReplayOutcome(
        finding_id="runtime_verify_work_suggestion",
        result_class=result_class,
        failure_classes=tuple(failures or ["runtime_verify_work", "no_structural_verify_phase", "read_only"]),
        mutated=mutated,
        next_action_class="runtime_verify_work" if not failures else "unknown",
        commands=tuple(commands),
    )


def _score_closeout_readiness_read_only_no_mutation(root: Path) -> CompletionReplayOutcome:
    _write_phase_project(root, verification_status="passed", recovery=True)
    (root / "GPD" / "CHECKPOINTS.md").write_text("# Checkpoint tags\n\npreserve-this\n", encoding="utf-8")
    before = _snapshot_tree(root / "GPD")

    result = phase_closeout_readiness(root, PHASE, require_verification=True)

    return _readiness_outcome(
        result=result,
        finding_id="closeout_readiness_read_only",
        result_class="read_only_ready_closeout",
        mutated=_snapshot_tree(root / "GPD") != before,
    )
