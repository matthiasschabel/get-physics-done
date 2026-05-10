"""Assertions for `execute-phase` ownership boundaries."""

from __future__ import annotations

import re
from pathlib import Path

from gpd.core.config import GPDProjectConfig

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
EXECUTE_PHASE_STAGE_DIR = WORKFLOWS_DIR / "execute-phase"


def _execute_phase_stage(name: str) -> str:
    return (EXECUTE_PHASE_STAGE_DIR / name).read_text(encoding="utf-8")


def _execute_phase_combined() -> str:
    stage_files = (
        "phase-bootstrap.md",
        "phase-classification.md",
        "wave-planning.md",
        "pre-execution-specialists.md",
        "wave-dispatch.md",
        "executor-dispatch.md",
        "checkpoint-resume.md",
        "aggregate-and-verify.md",
        "closeout.md",
    )
    return "\n\n".join(_execute_phase_stage(stage_file) for stage_file in stage_files)


def test_execute_phase_has_no_commented_pre_execution_specialist_task_spawns() -> None:
    workflow_text = _execute_phase_combined()

    commented_task_lines = re.findall(
        r"(?m)^\s*#\s*task\(subagent_type=\"gpd-(notation-coordinator|experiment-designer)\"",
        workflow_text,
    )

    assert commented_task_lines == []


def test_execute_phase_routes_wave_risk_without_acceptance_side_effects() -> None:
    workflow_text = _execute_phase_stage("wave-dispatch.md")

    assert "probe_then_fanout" in workflow_text
    assert "fanout" in workflow_text.lower()
    assert "executor_dispatch" in workflow_text
    assert "wave_return_checkpoint" in workflow_text
    assert "proof_critic_dispatch" in workflow_text
    assert "child_gate:" not in workflow_text
    assert "apply-return-updates" not in workflow_text
    assert "artifact-surfacing.md" not in workflow_text


def test_executor_dispatch_owns_executor_fanout_but_not_child_acceptance() -> None:
    dispatch = _execute_phase_stage("wave-dispatch.md")
    executor = _execute_phase_stage("executor-dispatch.md")

    assert 'subagent_type="gpd-executor"' not in dispatch
    assert 'subagent_type="gpd-executor"' in executor
    assert "child-readable workflow path" in executor
    assert "- Workflow: {GPD_INSTALL_DIR}/workflows/execute-plan.md" in executor
    assert "@{GPD_INSTALL_DIR}/workflows/execute-plan.md" not in executor
    assert "child_gate:" not in executor
    assert "apply-return-updates" not in executor
    assert "wave_return_checkpoint" in executor
    assert "proof_critic_dispatch" in executor


def test_execute_phase_explicitly_defers_plan_local_semantics_to_execute_plan() -> None:
    workflow_text = _execute_phase_stage("wave-planning.md")
    executor_dispatch = _execute_phase_stage("executor-dispatch.md")
    execute_plan_text = (WORKFLOWS_DIR / "execute-plan.md").read_text(encoding="utf-8")

    assert "execute-plan.md owns plan-local execution semantics" in workflow_text
    assert "`workflows/execute-plan.md` is a child-readable workflow path" in executor_dispatch
    assert "autonomy` changes who is asked and when" in execute_plan_text
    assert "first-result" in execute_plan_text
    assert "pre-fanout" in execute_plan_text


def test_execute_workflow_fallback_defaults_match_project_config_defaults() -> None:
    execute_phase = _execute_phase_stage("wave-planning.md") + "\n" + _execute_phase_stage("executor-dispatch.md")
    execute_plan = (WORKFLOWS_DIR / "execute-plan.md").read_text(encoding="utf-8")
    defaults = GPDProjectConfig()

    assert f".max_unattended_minutes_per_plan --default {defaults.max_unattended_minutes_per_plan})" in execute_plan
    assert f".checkpoint_after_n_tasks --default {defaults.checkpoint_after_n_tasks})" in execute_plan
    assert "Read `review_cadence`, `research_mode`, the unattended-minute limits" in execute_phase
    assert "<max_unattended_minutes_per_plan>{MAX_UNATTENDED_MINUTES_PER_PLAN}</max_unattended_minutes_per_plan>" in execute_phase
    assert "<max_unattended_minutes_per_wave>{MAX_UNATTENDED_MINUTES_PER_WAVE}</max_unattended_minutes_per_wave>" in execute_phase


def test_autonomous_prompt_uses_supported_transition_and_discuss_contracts() -> None:
    autonomous = (WORKFLOWS_DIR / "autonomous.md").read_text(encoding="utf-8")

    assert "workflow.skip_discuss" not in autonomous
    assert "--no-transition" not in autonomous
    assert "execute-phase` owns its normal phase transition / closeout path" in autonomous
    assert "`gpd:execute-phase` with `{phase: PHASE_NUM}`" in autonomous


def test_autonomous_uses_child_delegation_not_local_grep_status_readers() -> None:
    autonomous = (WORKFLOWS_DIR / "autonomous.md").read_text(encoding="utf-8")

    forbidden_fragments = (
        'VERIFY_STATUS=$(grep',
        'AUDIT_STATUS=$(grep',
        'grep "^status:"',
        'grep -iE "^status:"',
        "Read the human_verification section from VERIFICATION.md",
        "Read gap summary from VERIFICATION.md",
    )
    for fragment in forbidden_fragments:
        assert fragment not in autonomous
    assert "Autonomous mode is an orchestrator, not a Markdown status parser." in autonomous
    assert "`gpd:verify-work` with `{phase: PHASE_NUM}`" in autonomous
    assert "verification_report_status" in autonomous


def test_autonomous_stops_at_bounded_checkpoint_before_verification_routing() -> None:
    autonomous = (WORKFLOWS_DIR / "autonomous.md").read_text(encoding="utf-8")

    bounded_idx = autonomous.index("**Bounded checkpoint stop override:**")
    verification_idx = autonomous.index("**3e. Post-Execution Verification Routing**")

    assert bounded_idx < verification_idx
    assert "bounded to one authorized segment/checkpoint" in autonomous
    assert "Do not run redundant read-only probing" in autonomous
    assert "do not invoke `gpd:verify-work`" in autonomous
    assert "then return from autonomous mode" in autonomous
