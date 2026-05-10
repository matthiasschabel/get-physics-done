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
    "checkpoint_resume": "workflows/execute-phase/checkpoint-resume.md",
    "aggregate_and_verify": "workflows/execute-phase/aggregate-and-verify.md",
    "closeout": "workflows/execute-phase/closeout.md",
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
        "workflows/execute-phase/aggregate-and-verify.md",
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
    wave_dispatch = _stage_text("wave-dispatch.md")
    aggregate = _stage_text("aggregate-and-verify.md")
    closeout = _stage_text("closeout.md")

    assert "@{GPD_INSTALL_DIR}/references/verification/core/proof-redteam-workflow-gate.md" in wave_planning
    assert "@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md" in wave_dispatch
    assert "gpd-check-proof" in wave_dispatch
    assert "verification_report_skeleton_bridge" in aggregate
    assert "verification_report_finalizer_bridge" in aggregate
    assert "{GPD_INSTALL_DIR}/workflows/verify-phase.md" in aggregate
    assert "{GPD_INSTALL_DIR}/templates/recovery-plan.md" in aggregate
    assert "{GPD_INSTALL_DIR}/workflows/transition.md" in closeout


def test_execute_phase_owned_stop_examples_use_stage_stop_and_one_primary() -> None:
    checkpoint = _stage_text("checkpoint-resume.md")
    aggregate = _stage_text("aggregate-and-verify.md")
    closeout = _stage_text("closeout.md")

    assert "stage: checkpoint_resume" in checkpoint
    assert 'next_runtime_command: "gpd:resume-work"' in checkpoint
    assert "stage: aggregate_and_verify" in aggregate
    assert 'next_runtime_command: "gpd:plan-phase {X} --gaps"' in aggregate
    assert "stage_stop.next_runtime_command" in aggregate
    assert "stage: closeout" in closeout
    assert 'next_runtime_command: "gpd:complete-milestone"' in closeout

    for block in _next_up_blocks(checkpoint + "\n" + aggregate + "\n" + closeout):
        assert block.count("Primary:") == 1
        assert "gpd --raw init" not in block
        assert "field-access" not in block
