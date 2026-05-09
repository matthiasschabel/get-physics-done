"""Provider-free Phase 4 user-steering replay helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

WAVE_PLANNING = Path("src/gpd/specs/workflows/execute-phase/wave-planning.md")
WAVE_DISPATCH = Path("src/gpd/specs/workflows/execute-phase/wave-dispatch.md")
RESUME_BOOTSTRAP = Path("src/gpd/specs/workflows/resume-work/resume-bootstrap.md")
RESUME_ROUTING = Path("src/gpd/specs/workflows/resume-work/resume-routing.md")
CLOSEOUT = Path("src/gpd/specs/workflows/execute-phase/closeout.md")


@dataclass(frozen=True)
class UserSteeringRow:
    row_id: str
    scenario: str
    source_files: tuple[Path, ...]
    expected_finding: str
    expected_result_class: str
    expected_next_action_class: str
    provider_launch_allowed: bool = False
    network_allowed: bool = False
    raw_artifacts_allowed: bool = False
    mutation_allowed: bool = False


@dataclass(frozen=True)
class UserSteeringReplayEvent:
    scenario: str
    user_answer_class: str = "not_applicable"
    gate_class: str = "not_applicable"
    autonomy_class: str = "not_applicable"
    tangent_decision_class: str = "not_applicable"
    active_resume_kind_class: str = "not_applicable"
    advisory_resume_class: str = "not_applicable"


@dataclass(frozen=True)
class UserSteeringOutcome:
    finding_id: str
    result_class: str
    next_action_class: str
    failure_classes: tuple[str, ...]
    provider_launch_allowed: bool = False
    network_allowed: bool = False
    raw_artifacts_allowed: bool = False
    mutated: bool = False


USER_STEERING_ROWS: tuple[UserSteeringRow, ...] = (
    UserSteeringRow(
        row_id="P4-USER-01",
        scenario="alignment_requires_explicit_ask_user_answer",
        source_files=(WAVE_PLANNING,),
        expected_finding="alignment_answer_required",
        expected_result_class="blocked_before_execution",
        expected_next_action_class="gpd:execute-phase",
    ),
    UserSteeringRow(
        row_id="P4-USER-02",
        scenario="user_abort_stops_before_dispatch",
        source_files=(WAVE_PLANNING,),
        expected_finding="user_abort_stops_dispatch",
        expected_result_class="stopped_before_dispatch",
        expected_next_action_class="gpd:execute-phase",
    ),
    UserSteeringRow(
        row_id="P4-USER-03",
        scenario="tangent_proposal_uses_existing_review_stop",
        source_files=(WAVE_PLANNING, WAVE_DISPATCH),
        expected_finding="tangent_proposal_not_silent_work",
        expected_result_class="classified_at_existing_review_stop",
        expected_next_action_class="review_stop",
    ),
    UserSteeringRow(
        row_id="P4-USER-04",
        scenario="first_result_or_pre_fanout_routes_bounded_resume",
        source_files=(WAVE_PLANNING, WAVE_DISPATCH, RESUME_BOOTSTRAP, RESUME_ROUTING),
        expected_finding="pre_fanout_lock_routes_resume",
        expected_result_class="bounded_segment_resume_required",
        expected_next_action_class="gpd:resume-work",
    ),
    UserSteeringRow(
        row_id="P4-USER-05",
        scenario="supervised_closeout_requires_concrete_next_up",
        source_files=(CLOSEOUT,),
        expected_finding="supervised_closeout_requires_next_up",
        expected_result_class="paused_with_concrete_next_up",
        expected_next_action_class="concrete_next_command",
    ),
    UserSteeringRow(
        row_id="P4-USER-06",
        scenario="resume_prefers_canonical_bounded_segment",
        source_files=(RESUME_BOOTSTRAP, RESUME_ROUTING),
        expected_finding="canonical_bounded_segment_wins",
        expected_result_class="canonical_bounded_segment_preferred",
        expected_next_action_class="bounded_segment_resume",
    ),
)


def user_steering_rows() -> tuple[UserSteeringRow, ...]:
    return USER_STEERING_ROWS


def source_text(path: Path) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def source_bundle(row: UserSteeringRow) -> str:
    return "\n".join(source_text(path) for path in row.source_files)


def replay_event_for_row(row: UserSteeringRow) -> UserSteeringReplayEvent:
    match row.scenario:
        case "alignment_requires_explicit_ask_user_answer":
            return UserSteeringReplayEvent(
                scenario=row.scenario,
                user_answer_class="missing",
                gate_class="claim_deliverable_alignment",
                autonomy_class="supervised",
            )
        case "user_abort_stops_before_dispatch":
            return UserSteeringReplayEvent(
                scenario=row.scenario,
                user_answer_class="abort",
                gate_class="claim_deliverable_alignment",
                autonomy_class="supervised",
            )
        case "tangent_proposal_uses_existing_review_stop":
            return UserSteeringReplayEvent(
                scenario=row.scenario,
                gate_class="pre_fanout_review",
                tangent_decision_class="branch_later",
                autonomy_class="balanced",
            )
        case "first_result_or_pre_fanout_routes_bounded_resume":
            return UserSteeringReplayEvent(
                scenario=row.scenario,
                gate_class="pre_fanout_review_pending",
                active_resume_kind_class="bounded_segment",
            )
        case "supervised_closeout_requires_concrete_next_up":
            return UserSteeringReplayEvent(
                scenario=row.scenario,
                autonomy_class="supervised",
                gate_class="closeout_offer_next",
            )
        case "resume_prefers_canonical_bounded_segment":
            return UserSteeringReplayEvent(
                scenario=row.scenario,
                active_resume_kind_class="bounded_segment",
                advisory_resume_class="live_snapshot_and_recorded_handoff",
            )
    raise AssertionError(f"unhandled user-steering scenario: {row.scenario}")


def _assert_fragments(text: str, fragments: tuple[str, ...]) -> None:
    missing = [fragment for fragment in fragments if fragment not in text]
    assert missing == []


def _score_alignment_requires_answer(row: UserSteeringRow, event: UserSteeringReplayEvent) -> UserSteeringOutcome:
    assert event.user_answer_class == "missing"
    text = source_bundle(row)
    _assert_fragments(
        text,
        (
            "**ask_user:** Present exactly one question with 4 options.",
            "**Interactive answer requirement:** Only an explicit `ask_user` answer of `Y: proceed`",
            "Otherwise STOP before `gpd contract record-alignment`, branch/checkpoint writes, scripts/numerical computations, dispatches/subagents, and artifacts.",
            "Blocked: claim-deliverable alignment needs an explicit user answer.",
            "Next Up: rerun gpd:execute-phase {N} interactively.",
        ),
    )
    return UserSteeringOutcome(
        finding_id="alignment_answer_required",
        result_class="blocked_before_execution",
        next_action_class="gpd:execute-phase",
        failure_classes=("alignment_answer_required", "ask_user_answer_missing", "dispatch_not_authorized"),
    )


def _score_user_abort(row: UserSteeringRow, event: UserSteeringReplayEvent) -> UserSteeringOutcome:
    assert event.user_answer_class == "abort"
    text = source_bundle(row)
    _assert_fragments(
        text,
        (
            '**On "n: abort":** Exit cleanly.',
            "Do NOT spawn any executor and do NOT proceed to `discover_and_group_plans`.",
            'Emit a final line `"Next Up: gpd:execute-phase {N}"`',
        ),
    )
    return UserSteeringOutcome(
        finding_id="user_abort_stops_dispatch",
        result_class="stopped_before_dispatch",
        next_action_class="gpd:execute-phase",
        failure_classes=("user_abort_stops_dispatch", "executor_dispatch_blocked"),
    )


def _score_tangent_proposal(row: UserSteeringRow, event: UserSteeringReplayEvent) -> UserSteeringOutcome:
    assert event.tangent_decision_class == "branch_later"
    text = source_bundle(row)
    _assert_fragments(
        text,
        (
            "**Proposal-first tangent control:**",
            "do not silently pursue it",
            "Treat it as a tangent proposal and classify it using exactly one of these four decisions",
            "`branch_later`",
            "Tangent proposals ride on the existing first-result / skeptical / pre-fanout review stops.",
            "Do not create side branches or subagents from executor initiative",
        ),
    )
    return UserSteeringOutcome(
        finding_id="tangent_proposal_not_silent_work",
        result_class="classified_at_existing_review_stop",
        next_action_class="review_stop",
        failure_classes=("tangent_proposal_not_silent_work", "review_stop_required"),
    )


def _score_bounded_resume(row: UserSteeringRow, event: UserSteeringReplayEvent) -> UserSteeringOutcome:
    assert event.gate_class == "pre_fanout_review_pending"
    assert event.active_resume_kind_class == "bounded_segment"
    text = source_bundle(row)
    _assert_fragments(
        text,
        (
            "set `FIRST_RESULT_GATE_REQUIRED=true`",
            "set `PRE_FANOUT_REVIEW_REQUIRED=true`",
            "force bounded continuation segments",
            "Live gate state must include `checkpoint_reason: pre_fanout`",
            "`pre_fanout_review_pending: true`",
            "`downstream_locked: true`",
            "If `active_resume_kind` is `bounded_segment`, `execution_resumable` is true",
            "treat that bounded continuation as the primary resume target",
        ),
    )
    return UserSteeringOutcome(
        finding_id="pre_fanout_lock_routes_resume",
        result_class="bounded_segment_resume_required",
        next_action_class="gpd:resume-work",
        failure_classes=("pre_fanout_lock_routes_resume", "bounded_segment_required"),
    )


def _score_supervised_closeout(row: UserSteeringRow, event: UserSteeringReplayEvent) -> UserSteeringOutcome:
    assert event.autonomy_class == "supervised"
    text = source_bundle(row)
    _assert_fragments(
        text,
        (
            "If supervised, or if a checkpoint requires review, pause with a clear status message",
            "exact next command to continue",
            'Never end with only "ready to plan/continue" prose.',
            "## > Next Up",
            "Primary: `{chosen primary command}`",
            "`gpd:suggest-next` -- confirm the next action",
        ),
    )
    return UserSteeringOutcome(
        finding_id="supervised_closeout_requires_next_up",
        result_class="paused_with_concrete_next_up",
        next_action_class="concrete_next_command",
        failure_classes=("supervised_closeout_requires_next_up", "next_up_required"),
    )


def _score_canonical_resume(row: UserSteeringRow, event: UserSteeringReplayEvent) -> UserSteeringOutcome:
    assert event.active_resume_kind_class == "bounded_segment"
    assert event.advisory_resume_class == "live_snapshot_and_recorded_handoff"
    text = source_bundle(row)
    _assert_fragments(
        text,
        (
            "If `active_resume_kind=\"bounded_segment\"` and `active_bounded_segment` exists",
            "treat that as the primary bounded resume target",
            "does not define a second resume system",
            "Do NOT invent additional candidates from plan files without summaries, auto-checkpoints, or other ad hoc checkpoints.",
            "Primary: Continue the bounded execution segment",
            "Treat the live snapshot as advisory continuity context only",
        ),
    )
    return UserSteeringOutcome(
        finding_id="canonical_bounded_segment_wins",
        result_class="canonical_bounded_segment_preferred",
        next_action_class="bounded_segment_resume",
        failure_classes=("canonical_bounded_segment_wins", "advisory_resume_not_primary"),
    )


def score_user_steering_row(row: UserSteeringRow, event: UserSteeringReplayEvent | None = None) -> UserSteeringOutcome:
    event = event or replay_event_for_row(row)
    match row.scenario:
        case "alignment_requires_explicit_ask_user_answer":
            return _score_alignment_requires_answer(row, event)
        case "user_abort_stops_before_dispatch":
            return _score_user_abort(row, event)
        case "tangent_proposal_uses_existing_review_stop":
            return _score_tangent_proposal(row, event)
        case "first_result_or_pre_fanout_routes_bounded_resume":
            return _score_bounded_resume(row, event)
        case "supervised_closeout_requires_concrete_next_up":
            return _score_supervised_closeout(row, event)
        case "resume_prefers_canonical_bounded_segment":
            return _score_canonical_resume(row, event)
    raise AssertionError(f"unhandled user-steering scenario: {row.scenario}")
