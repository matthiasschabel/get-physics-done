"""Stage-authority assertions for the staged `execute-phase` workflow."""

from __future__ import annotations

import re
from pathlib import Path

from gpd.core.workflow_staging import load_workflow_stage_manifest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMAND_PATH = REPO_ROOT / "src" / "gpd" / "commands" / "execute-phase.md"
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
EXECUTE_PHASE_STAGE_DIR = WORKFLOWS_DIR / "execute-phase"

STAGE_AUTHORITY_BY_ID = {
    "phase_bootstrap": "workflows/execute-phase/phase-bootstrap.md",
    "phase_classification": "workflows/execute-phase/phase-classification.md",
    "wave_planning": "workflows/execute-phase/wave-planning.md",
    "pre_execution_specialists": "workflows/execute-phase/pre-execution-specialists.md",
    "wave_dispatch": "workflows/execute-phase/wave-dispatch.md",
    "executor_dispatch": "workflows/execute-phase/executor-dispatch.md",
    "proof_critic_dispatch": "workflows/execute-phase/proof-critic-dispatch.md",
    "wave_return_checkpoint": "workflows/execute-phase/wave-return-checkpoint.md",
    "wave_failure_menu": "workflows/execute-phase/wave-failure-menu.md",
    "checkpoint_resume": "workflows/execute-phase/checkpoint-resume.md",
    "aggregate_and_verify": "workflows/execute-phase/aggregate-and-verify.md",
    "verification_handoff": "workflows/execute-phase/verification-handoff.md",
    "gap_reverification": "workflows/execute-phase/gap-reverification.md",
    "consistency_check": "workflows/execute-phase/consistency-check.md",
    "closeout": "workflows/execute-phase/closeout.md",
}

TARGET_STAGE_EDGES = {
    "phase_bootstrap": ("phase_classification",),
    "phase_classification": ("wave_planning",),
    "wave_planning": ("pre_execution_specialists",),
    "pre_execution_specialists": ("wave_dispatch",),
    "wave_dispatch": ("executor_dispatch",),
    "executor_dispatch": ("proof_critic_dispatch",),
    "proof_critic_dispatch": ("wave_return_checkpoint",),
    "wave_return_checkpoint": ("wave_failure_menu",),
    "wave_failure_menu": ("checkpoint_resume",),
    "checkpoint_resume": ("aggregate_and_verify",),
    "aggregate_and_verify": ("verification_handoff",),
    "verification_handoff": ("gap_reverification",),
    "gap_reverification": ("consistency_check",),
    "consistency_check": ("closeout",),
    "closeout": (),
}

HEAVY_AUTHORITIES = {
    "workflows/execute-plan.md",
    "workflows/verify-phase.md",
    "workflows/transition.md",
    "references/orchestration/checkpoints.md",
    "references/orchestration/agent-infrastructure.md",
    "references/orchestration/continuous-execution.md",
    "references/verification/core/verification-core.md",
    "references/execution/github-lifecycle.md",
    "references/ui/ui-brand.md",
    "templates/recovery-plan.md",
    "templates/state-machine.md",
    "templates/paper/figure-tracker.md",
    "templates/paper/experimental-comparison.md",
}

WAVE_FAMILY_STAGES = {
    "wave_dispatch",
    "executor_dispatch",
    "proof_critic_dispatch",
    "wave_return_checkpoint",
    "wave_failure_menu",
}

VERIFICATION_FAMILY_STAGES = {
    "aggregate_and_verify",
    "verification_handoff",
    "gap_reverification",
    "consistency_check",
}


def _stage_text(stage_file: str) -> str:
    return (EXECUTE_PHASE_STAGE_DIR / stage_file).read_text(encoding="utf-8")


def _next_up_blocks(text: str) -> list[str]:
    return re.findall(r"## > Next Up\n(?P<body>.*?)(?:\n```|\Z)", text, flags=re.DOTALL)


def test_execute_phase_manifest_uses_stage_authorities_without_root_eager_loads() -> None:
    manifest = load_workflow_stage_manifest("execute-phase")

    assert manifest.stage_ids() == tuple(STAGE_AUTHORITY_BY_ID)
    for stage_id, authority in STAGE_AUTHORITY_BY_ID.items():
        stage = manifest.stage(stage_id)
        assert stage.mode_paths == (authority,)
        assert stage.loaded_authorities[0] == authority
        assert "workflows/execute-phase.md" not in stage.mode_paths
        assert "workflows/execute-phase.md" not in stage.loaded_authorities
        assert (WORKFLOWS_DIR / authority.removeprefix("workflows/")).is_file()


def test_execute_phase_manifest_uses_phase4_stage_topology() -> None:
    manifest = load_workflow_stage_manifest("execute-phase")

    assert manifest.stage_ids() == tuple(TARGET_STAGE_EDGES)
    for stage_id, next_stages in TARGET_STAGE_EDGES.items():
        assert manifest.stage(stage_id).next_stages == next_stages


def test_execute_phase_heavy_authorities_are_conditional_or_lazy_not_unconditional() -> None:
    manifest = load_workflow_stage_manifest("execute-phase")

    for stage in manifest.stages:
        assert not HEAVY_AUTHORITIES.intersection(stage.loaded_authorities), stage.id

    executor_dispatch = manifest.stage("executor_dispatch")
    verification_handoff = manifest.stage("verification_handoff")
    aggregate = manifest.stage("aggregate_and_verify")
    closeout = manifest.stage("closeout")

    conditional_by_stage = {
        stage.id: {authority for conditional in stage.conditional_authorities for authority in conditional.authorities}
        for stage in manifest.stages
    }

    assert "workflows/execute-plan.md" in conditional_by_stage["executor_dispatch"]
    assert "workflows/verify-phase.md" in conditional_by_stage["verification_handoff"]
    assert "references/verification/core/verification-core.md" in conditional_by_stage["verification_handoff"]
    assert "templates/paper/figure-tracker.md" in conditional_by_stage["aggregate_and_verify"]
    assert "templates/paper/experimental-comparison.md" in conditional_by_stage["aggregate_and_verify"]
    assert "templates/recovery-plan.md" in conditional_by_stage["aggregate_and_verify"]
    assert "references/execution/github-lifecycle.md" in conditional_by_stage["closeout"]
    assert closeout.loaded_authorities == ("workflows/execute-phase/closeout.md",)
    for authority in (
        "workflows/transition.md",
        "templates/state-machine.md",
        "references/orchestration/state-portability.md",
        "references/ui/ui-brand.md",
        "references/orchestration/continuous-execution.md",
    ):
        assert authority in conditional_by_stage["closeout"]

    assert "workflows/execute-plan.md" in executor_dispatch.must_not_eager_load
    assert "workflows/verify-phase.md" in verification_handoff.must_not_eager_load
    assert "references/verification/core/verification-core.md" in verification_handoff.must_not_eager_load
    assert "templates/recovery-plan.md" in aggregate.must_not_eager_load
    assert "references/execution/github-lifecycle.md" in closeout.must_not_eager_load
    assert "references/execution/git-integration.md" in closeout.must_not_eager_load
    for authority in (
        "workflows/transition.md",
        "templates/state-machine.md",
        "references/orchestration/state-portability.md",
        "references/ui/ui-brand.md",
        "references/orchestration/continuous-execution.md",
    ):
        assert authority in closeout.must_not_eager_load


def test_execute_phase_split_stage_write_scopes_are_narrow() -> None:
    manifest = load_workflow_stage_manifest("execute-phase")

    for stage_id in ("phase_bootstrap", "phase_classification", "wave_planning", "pre_execution_specialists"):
        assert manifest.stage(stage_id).writes_allowed == ()
    for stage_id in (*WAVE_FAMILY_STAGES, "checkpoint_resume", "aggregate_and_verify", "consistency_check"):
        assert manifest.stage(stage_id).writes_allowed == ("GPD/phases",)
    for stage_id in ("verification_handoff", "gap_reverification"):
        assert manifest.stage(stage_id).writes_allowed == ("GPD/phases", "GPD/STATE.md")
    assert manifest.stage("closeout").writes_allowed == ("GPD/ROADMAP.md", "GPD/STATE.md", "GPD/phases")


def test_execute_phase_early_reference_content_boundaries_are_explicit() -> None:
    manifest = load_workflow_stage_manifest("execute-phase")
    phase_classification = manifest.stage("phase_classification")
    wave_planning = manifest.stage("wave_planning")
    closeout = manifest.stage("closeout")

    assert "reference_artifacts_content" not in phase_classification.required_init_fields
    assert "protocol_bundle_context" not in phase_classification.required_init_fields
    assert "active_reference_context" in phase_classification.required_init_fields

    assert "reference_artifact_files" in wave_planning.required_init_fields
    assert "reference_artifacts_content" in wave_planning.required_init_fields
    assert "protocol_bundle_context" in wave_planning.required_init_fields

    assert "active_reference_context" not in closeout.required_init_fields
    assert "reference_artifact_files" not in closeout.required_init_fields
    assert "reference_artifacts_content" not in closeout.required_init_fields
    assert "current_execution" in closeout.required_init_fields


def test_execute_phase_command_bootstraps_only_first_stage_authority() -> None:
    command = COMMAND_PATH.read_text(encoding="utf-8")

    assert "@{GPD_INSTALL_DIR}/workflows/execute-phase/phase-bootstrap.md" in command
    assert "@{GPD_INSTALL_DIR}/workflows/execute-phase.md" not in command
    assert "staged_loading.eager_authorities" in command
    assert "staged_loading.must_not_eager_load" in command


def test_execute_phase_bootstrap_defers_late_authorities() -> None:
    manifest = load_workflow_stage_manifest("execute-phase")
    bootstrap = manifest.stage("phase_bootstrap")
    bootstrap_text = _stage_text("phase-bootstrap.md")

    deferred = set(bootstrap.must_not_eager_load)
    for authority in (
        "workflows/execute-phase.md",
        "workflows/execute-phase/wave-planning.md",
        "workflows/execute-phase/wave-dispatch.md",
        "workflows/execute-phase/executor-dispatch.md",
        "workflows/execute-phase/proof-critic-dispatch.md",
        "workflows/execute-phase/wave-return-checkpoint.md",
        "workflows/execute-phase/wave-failure-menu.md",
        "workflows/execute-phase/aggregate-and-verify.md",
        "workflows/execute-phase/verification-handoff.md",
        "workflows/execute-phase/gap-reverification.md",
        "workflows/execute-phase/consistency-check.md",
        "workflows/execute-phase/closeout.md",
        "references/verification/core/proof-redteam-workflow-gate.md",
        "references/orchestration/runtime-delegation-note.md",
        "templates/summary.md",
        "templates/calculation-log.md",
        "templates/recovery-plan.md",
        "workflows/verify-phase.md",
        "workflows/transition.md",
    ):
        assert authority in deferred

    forbidden_bootstrap_fragments = (
        "@{GPD_INSTALL_DIR}/references/verification/core/proof-redteam-workflow-gate.md",
        "@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md",
        "{plan_id}-PROOF-REDTEAM.md",
        "gpd-check-proof",
        "verification_report_finalizer_bridge",
        "{GPD_INSTALL_DIR}/workflows/verify-phase.md",
        "{GPD_INSTALL_DIR}/workflows/transition.md",
        "{GPD_INSTALL_DIR}/templates/recovery-plan.md",
    )
    for fragment in forbidden_bootstrap_fragments:
        assert fragment not in bootstrap_text


def test_execute_phase_late_authorities_live_in_owning_stages() -> None:
    wave_planning = _stage_text("wave-planning.md")
    executor_dispatch = _stage_text("executor-dispatch.md")
    proof_critic_dispatch = _stage_text("proof-critic-dispatch.md")
    aggregate = _stage_text("aggregate-and-verify.md")
    verification_handoff = _stage_text("verification-handoff.md")
    gap_reverification = _stage_text("gap-reverification.md")
    closeout = _stage_text("closeout.md")

    assert "@{GPD_INSTALL_DIR}/references/verification/core/proof-redteam-workflow-gate.md" in wave_planning
    assert "@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md" in executor_dispatch
    assert "{GPD_INSTALL_DIR}/workflows/execute-plan.md" in executor_dispatch
    assert "gpd-check-proof" in proof_critic_dispatch
    assert "verification_report_skeleton_bridge" in verification_handoff
    assert "verification_report_finalizer_bridge" in verification_handoff
    assert "{GPD_INSTALL_DIR}/workflows/verify-phase.md" in verification_handoff
    assert "{GPD_INSTALL_DIR}/workflows/verify-phase.md" in gap_reverification
    assert "{GPD_INSTALL_DIR}/templates/recovery-plan.md" in aggregate
    assert "gpd:complete-milestone" in closeout


def test_execute_phase_owned_stop_examples_use_stage_stop_and_one_primary() -> None:
    checkpoint = _stage_text("checkpoint-resume.md")
    verification_handoff = _stage_text("verification-handoff.md")
    gap_reverification = _stage_text("gap-reverification.md")
    consistency_check = _stage_text("consistency-check.md")
    closeout = _stage_text("closeout.md")

    assert "stage: checkpoint_resume" in checkpoint
    assert 'next_runtime_command: "gpd:resume-work"' in checkpoint
    assert "stage: verification_handoff" in verification_handoff
    assert 'next_runtime_command: "gpd:plan-phase {PHASE_NUMBER} --gaps"' in verification_handoff
    assert "stage: gap_reverification" in gap_reverification
    assert "stage_stop.next_runtime_command" in consistency_check
    assert "stage: closeout" in closeout
    assert 'next_runtime_command: "gpd:complete-milestone"' in closeout

    for block in _next_up_blocks(checkpoint + "\n" + verification_handoff + "\n" + consistency_check + "\n" + closeout):
        assert block.count("Primary:") == 1
        assert "gpd --raw init" not in block
        assert "field-access" not in block
