"""Contract tests for the `claim_deliverable_alignment_check` precheck step.

Grep-on-spec-text assertions that pin the precheck step's presence, location,
gating, suppression, abort handling, and side-by-side render shape. These
tests mirror the style of `tests/core/test_execute_phase_ownership_boundaries.py`:
load `execute-phase.md` once, assert on substrings.
"""

from __future__ import annotations

from pathlib import Path

WORKFLOWS_DIR = Path(__file__).resolve().parents[2] / "src" / "gpd" / "specs" / "workflows"
EXECUTE_PHASE_STAGE_DIR = WORKFLOWS_DIR / "execute-phase"
EXECUTE_PHASE_STAGE_FILES = (
    "phase-bootstrap.md",
    "phase-classification.md",
    "wave-planning.md",
    "pre-execution-specialists.md",
    "wave-dispatch.md",
    "executor-dispatch.md",
    "proof-critic-dispatch.md",
    "wave-return-checkpoint.md",
    "wave-failure-menu.md",
    "checkpoint-resume.md",
    "aggregate-and-verify.md",
    "verification-handoff.md",
    "gap-reverification.md",
    "consistency-check.md",
    "closeout.md",
)
EXECUTE_PHASE = "\n\n".join(
    (EXECUTE_PHASE_STAGE_DIR / stage_file).read_text(encoding="utf-8")
    for stage_file in EXECUTE_PHASE_STAGE_FILES
)

_PRECHECK_OPEN_TAG = '<step name="claim_deliverable_alignment_check">'
_STEP_CLOSE_TAG = "</step>"


def _extract_precheck_body() -> str:
    """Slice the precheck step body (between its open tag and matching </step>).

    Returns an empty string if the step is absent, so individual tests produce
    meaningful failures rather than a module-load crash.
    """
    start = EXECUTE_PHASE.find(_PRECHECK_OPEN_TAG)
    if start == -1:
        return ""
    end = EXECUTE_PHASE.find(_STEP_CLOSE_TAG, start)
    if end == -1:
        return ""
    return EXECUTE_PHASE[start:end]


_PRECHECK_BODY = _extract_precheck_body()


def test_precheck_step_exists_and_lives_before_plan_discovery() -> None:
    assert _PRECHECK_OPEN_TAG in EXECUTE_PHASE, (
        "claim_deliverable_alignment_check step is missing from execute-phase.md"
    )

    proof_gate_tag = '<step name="detect_proof_obligation_work">'
    discover_tag = '<step name="discover_and_group_plans">'

    proof_gate_idx = EXECUTE_PHASE.index(proof_gate_tag)
    precheck_idx = EXECUTE_PHASE.index(_PRECHECK_OPEN_TAG)
    discover_idx = EXECUTE_PHASE.index(discover_tag)

    assert proof_gate_idx < precheck_idx < discover_idx, (
        "claim_deliverable_alignment_check must be positioned after "
        "detect_proof_obligation_work and before discover_and_group_plans "
        f"(got offsets proof_gate={proof_gate_idx}, precheck={precheck_idx}, "
        f"discover={discover_idx})"
    )


def test_precheck_fires_under_supervised() -> None:
    assert _PRECHECK_BODY, "precheck step body could not be extracted"
    assert "autonomy=supervised" in _PRECHECK_BODY, "precheck gating must mention autonomy=supervised"


def test_precheck_fires_under_dense_regardless_of_autonomy() -> None:
    assert _PRECHECK_BODY, "precheck step body could not be extracted"
    assert "review_cadence=dense" in _PRECHECK_BODY, "precheck gating must mention review_cadence=dense"


def test_precheck_skipped_under_yolo_adaptive_no_proof() -> None:
    assert _PRECHECK_BODY, "precheck step body could not be extracted"

    body_lower = _PRECHECK_BODY.lower()
    assert "yolo" in body_lower, "precheck skip clause must mention yolo"
    assert ("adaptive" in body_lower) or ("sparse" in body_lower), (
        "precheck skip clause must mention adaptive or sparse cadence"
    )
    assert "proof-bearing" in body_lower or "proof_bearing" in body_lower, (
        "precheck skip clause must mention a no-proof-bearing condition"
    )


def test_precheck_fires_on_proof_bearing_plans_regardless_of_autonomy() -> None:
    assert _PRECHECK_BODY, "precheck step body could not be extracted"

    body_lower = _PRECHECK_BODY.lower()
    assert (
        "detect_proof_obligation_work" in _PRECHECK_BODY
        or "proof-bearing" in body_lower
        or "proof_bearing" in body_lower
    ), "precheck gating must reference detect_proof_obligation_work or proof-bearing plans"


def test_precheck_proceed_does_not_reprompt_in_same_session() -> None:
    assert _PRECHECK_BODY, "precheck step body could not be extracted"

    body_lower = _PRECHECK_BODY.lower()
    mentions_confirmed = "confirmed_at" in _PRECHECK_BODY or "already confirmed" in body_lower
    mentions_hash = ("hash" in body_lower) or ("fingerprint" in body_lower)

    assert mentions_confirmed, "precheck must reference confirmed_at or 'already confirmed' to suppress re-prompts"
    assert mentions_hash, "precheck suppression must reference a hash or fingerprint check"


def test_precheck_fails_closed_when_fingerprints_are_missing() -> None:
    assert _PRECHECK_BODY, "precheck step body could not be extracted"

    assert "fail closed if either fingerprint command fails or resolves to an empty value" in _PRECHECK_BODY
    assert 'if [ -z "$CONTRACT_HASH" ] || [ -z "$CONTEXT_HASH" ]; then' in _PRECHECK_BODY
    assert "call `gpd contract record-alignment` on this path" in _PRECHECK_BODY
    assert "STOP before writes, scripts, computations, dispatches, subagents, or artifacts" in _PRECHECK_BODY


def test_precheck_requires_explicit_interactive_answer_before_recording_alignment() -> None:
    assert _PRECHECK_BODY, "precheck step body could not be extracted"

    assert "Only explicit `Y: proceed` authorizes record-alignment." in _PRECHECK_BODY
    assert "Missing `ask_user`, timeout, empty answer, or noninteractive run is not confirmation" in _PRECHECK_BODY
    assert "STOP before writes, scripts, computations, dispatches, subagents, or artifacts" in _PRECHECK_BODY
    assert "On `Y: proceed` record alignment and continue" in _PRECHECK_BODY

    block_idx = _PRECHECK_BODY.index("Only explicit `Y: proceed`")
    record_idx = _PRECHECK_BODY.index(
        'gpd contract record-alignment --contract-hash "$CONTRACT_HASH" --context-hash "$CONTEXT_HASH"'
    )
    assert block_idx < record_idx


def test_wave_checkpoint_authority_is_established_before_execution_work() -> None:
    checkpoint_idx = EXECUTE_PHASE.index("This is the rollback authority gate for the wave.")
    describe_idx = EXECUTE_PHASE.index("Read each selected plan's `<objective>`")
    spawn_idx = EXECUTE_PHASE.index("Choose exactly one immediate route after the checkpoint")

    assert checkpoint_idx < describe_idx < spawn_idx
    assert "No scripts, numerical computation, executor dispatch, proof critic dispatch, artifact writes" in EXECUTE_PHASE
    assert "Do not run computation and then checkpoint afterward." in EXECUTE_PHASE
    assert 'gpd --raw phase checkpoint create --phase "${phase_number}" --wave "${WAVE_NUM}"' in EXECUTE_PHASE
    assert "safe_to_execute_wave: true" in EXECUTE_PHASE
    assert "PROJECT_ROOT=$(pwd -P)" not in EXECUTE_PHASE
    assert "GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || true)" not in EXECUTE_PHASE


def test_execute_phase_closeout_uses_readiness_and_checkpoint_helpers() -> None:
    assert 'gpd --raw phase closeout-readiness "${phase_number}" --require-verification' in EXECUTE_PHASE
    assert 'gpd phase complete "${phase_number}"' in EXECUTE_PHASE
    assert 'gpd --raw phase checkpoint cleanup --phase "${phase_number}" --namespace phase' in EXECUTE_PHASE
    assert 'git tag -l "gpd-checkpoint-phase-${phase_number}-*"' not in EXECUTE_PHASE
    assert 'git tag -d "${TAG}"' not in EXECUTE_PHASE


def test_precheck_abort_does_not_spawn_workers() -> None:
    assert _PRECHECK_BODY, "precheck step body could not be extracted"

    body_lower = _PRECHECK_BODY.lower()
    # Locate the abort / "On n" branch. Accept several wording variants.
    has_abort_marker = "on n" in body_lower or "abort" in body_lower or "on `n`" in body_lower
    assert has_abort_marker, "precheck must describe an abort / 'On n' branch"

    # The abort branch must clearly instruct not to spawn executors or to
    # exit cleanly. Keep the match case-insensitive and loose.
    abort_guards = (
        "do not spawn",
        "don't spawn",
        "no not spawn",
        "not spawn",
        "exit",
        "stop",
        "halt",
    )
    assert any(marker in body_lower for marker in abort_guards), (
        "precheck abort branch must forbid spawning executors or direct an exit"
    )


def test_precheck_renders_claim_deliverable_side_by_side() -> None:
    assert _PRECHECK_BODY, "precheck step body could not be extracted"

    body_lower = _PRECHECK_BODY.lower()

    mentions_summary = (
        "claim_deliverable_alignment_summary" in _PRECHECK_BODY
        or "claim ↔ deliverable" in body_lower
        or "claim <-> deliverable" in body_lower
        or "alignment-summary" in body_lower
        or "alignment summary" in body_lower
    )
    assert mentions_summary, (
        "precheck must reference claim_deliverable_alignment_summary or a "
        "'Claim ↔ Deliverable' / 'alignment-summary' header"
    )

    intent_tokens = ("observables", "deliverables", "references", "stop", "rethink")
    present = sum(1 for token in intent_tokens if token in body_lower)
    # Treat stop/rethink as one slot: if either is present, count that slot once.
    stop_rethink_present = ("stop" in body_lower) or ("rethink" in body_lower)
    explicit_slots = sum(1 for token in ("observables", "deliverables", "references") if token in body_lower) + (
        1 if stop_rethink_present else 0
    )

    assert explicit_slots >= 3, (
        "precheck render must mention at least 3 of the 4 user-intent fields "
        f"(observables, deliverables, references, stop/rethink); found {present} tokens "
        f"across the four slots"
    )
