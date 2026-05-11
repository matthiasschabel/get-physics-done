"""Dispatch-stage contracts for the split `execute-phase` wave flow."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EXECUTE_PHASE_STAGE_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows" / "execute-phase"


def _stage(name: str) -> str:
    return (EXECUTE_PHASE_STAGE_DIR / name).read_text(encoding="utf-8")


def test_wave_planning_keeps_phase_wide_gates_without_full_checkpoint_or_verification_includes() -> None:
    wave_planning = _stage("wave-planning.md")

    for anchor in (
        '<step name="detect_proof_obligation_work">',
        '<step name="claim_deliverable_alignment_check">',
        '<step name="discover_and_group_plans">',
        '<step name="resolve_execution_cadence">',
        '<step name="publish_wave_plan_for_dispatch">',
        "Intra-wave dependency validation",
        "Parallel file conflict detection",
        "When `review_cadence=dense`, treat every wave as risky",
        "FIRST_RESULT_GATE_REQUIRED=true",
        "PRE_FANOUT_REVIEW_REQUIRED=true",
    ):
        assert anchor in wave_planning

    assert "@{GPD_INSTALL_DIR}/references/verification/core/proof-redteam-workflow-gate.md" in wave_planning
    assert "@{GPD_INSTALL_DIR}/references/orchestration/checkpoints.md" not in wave_planning
    assert "@{GPD_INSTALL_DIR}/references/verification/core/verification-core.md" not in wave_planning
    assert "checkpoint_resume" in wave_planning
    assert "executor_dispatch" in wave_planning


def test_wave_dispatch_is_setup_router_without_executor_or_return_acceptance() -> None:
    wave_dispatch = _stage("wave-dispatch.md")

    refresh_idx = wave_dispatch.index('WAVE_DISPATCH_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage wave_dispatch)')
    convention_idx = wave_dispatch.index('<step name="lock_wave_conventions">')
    checkpoint_idx = wave_dispatch.index('<step name="create_wave_checkpoint_before_work">')
    route_idx = wave_dispatch.index('<step name="choose_wave_route">')

    assert refresh_idx < convention_idx < checkpoint_idx < route_idx
    assert "safe_to_execute_wave: true" in wave_dispatch
    assert "No scripts, numerical computation, executor dispatch" in wave_dispatch
    assert "WAVE_CHECKPOINT_RESULT=$(gpd --raw phase checkpoint create" in wave_dispatch

    for route in ("executor_dispatch", "proof_critic_dispatch", "wave_return_checkpoint", "wave_failure_menu"):
        assert route in wave_dispatch

    for forbidden in (
        "task(",
        'subagent_type="gpd-executor"',
        'subagent_type="gpd-check-proof"',
        "child_gate:",
        "apply-return-updates",
        "artifact-surfacing.md",
        '<step name="wave_failure_handling">',
    ):
        assert forbidden not in wave_dispatch


def test_executor_dispatch_constructs_executor_children_with_child_readable_execute_plan_path() -> None:
    executor_dispatch = _stage("executor-dispatch.md")

    assert 'EXECUTOR_DISPATCH_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage executor_dispatch)' in executor_dispatch
    assert "EXECUTOR_HANDOFF_STARTED_AT=" in executor_dispatch
    assert 'subagent_type="gpd-executor"' in executor_dispatch
    assert "`workflows/execute-plan.md` is a child-readable workflow path" in executor_dispatch
    assert "- Workflow: {GPD_INSTALL_DIR}/workflows/execute-plan.md" in executor_dispatch
    assert "@{GPD_INSTALL_DIR}/workflows/execute-plan.md" not in executor_dispatch

    for required in (
        "strict_wait",
        "never_interrupt_running_workers",
        "never_auto_close_child_agents",
        "<first_result_gate>{FIRST_RESULT_GATE_REQUIRED}</first_result_gate>",
        "<pre_fanout_review>{PRE_FANOUT_REVIEW_REQUIRED}</pre_fanout_review>",
        "<checkpoint_before_downstream>{CHECKPOINT_BEFORE_DOWNSTREAM}</checkpoint_before_downstream>",
        "review_cadence=dense",
        "autonomy=supervised",
    ):
        assert required in executor_dispatch

    for forbidden in (
        "child_gate:",
        "apply-return-updates",
        'subagent_type="gpd-check-proof"',
    ):
        assert forbidden not in executor_dispatch


def test_executor_dispatch_requires_prior_wave_checkpoint_before_task_construction() -> None:
    executor_dispatch = _stage("executor-dispatch.md")

    guard_idx = executor_dispatch.index('<step name="pre_fanout_guard">')
    task_idx = executor_dispatch.index('task(\n  subagent_type="gpd-executor"')

    assert guard_idx < task_idx
    assert "Require the `wave_dispatch` route record and a wave checkpoint tag" in executor_dispatch
    assert "STOP before work and route back to `wave_dispatch`" in executor_dispatch
    assert "do not create a checkpoint after computation" in executor_dispatch
    assert "gpd --raw phase checkpoint create" not in executor_dispatch
