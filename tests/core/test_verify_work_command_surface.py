"""Focused assertions for the verify-work command wrapper surface."""

from __future__ import annotations

from pathlib import Path

from gpd.core.workflow_staging import load_workflow_stage_manifest
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMAND_PATH = REPO_ROOT / "src/gpd/commands/verify-work.md"
WORKFLOW_PATH = REPO_ROOT / "src/gpd/specs/workflows/verify-work.md"
WORKFLOW_STAGE_DIR = REPO_ROOT / "src/gpd/specs/workflows/verify-work"


def test_verify_work_command_wrapper_stays_thin_and_delegates_policy_to_workflow() -> None:
    text = COMMAND_PATH.read_text(encoding="utf-8")

    assert "@{GPD_INSTALL_DIR}/workflows/verify-work/session-router.md" in text
    assert "@{GPD_INSTALL_DIR}/workflows/verify-work.md" not in text
    assert (
        "The staged workflow authorities own the detailed check taxonomy; this wrapper only bootstraps the canonical verification surface and delegates the physics checks."
        in text
    )
    assert "Severity Classification" not in text
    assert "One check at a time, plain text responses, no interrogation." not in text
    assert "Physics verification is not binary:" not in text
    assert "For deeper focused analysis" not in text


def test_verify_work_workflow_loads_staged_init_payloads_on_demand() -> None:
    text = workflow_authority_text(WORKFLOW_PATH.parent, "verify-work")

    assert 'PHASE_ARG=""' in text
    assert "VERIFY_FLAGS=()" in text
    assert '*) [ -z "$PHASE_ARG" ] && PHASE_ARG="$token" ;;' in text
    assert text.index('PHASE_ARG=""') < text.index(
        'SESSION_ROUTER_INIT=$(gpd --raw init verify-work "${PHASE_ARG}" --stage session_router)'
    )
    assert 'SESSION_ROUTER_INIT=$(gpd --raw init verify-work "${PHASE_ARG}" --stage session_router)' in text
    assert 'PROJECT_ROOT=$(echo "$SESSION_ROUTER_INIT" | gpd json get .project_root)' in text
    assert 'PHASE_DIR_ABS=$(echo "$SESSION_ROUTER_INIT" | gpd json get .phase_dir_abs --default "")' in text
    assert "VERIFY_FLAG_TEXT=\"${VERIFY_FLAGS[*]}\"" in text
    assert "Verification flags from the normalized parser: $VERIFY_FLAG_TEXT" in text
    assert "Verification flags from the invoking wrapper: $ARGUMENTS" not in text
    assert 'PHASE_BOOTSTRAP_INIT=$(gpd --raw init verify-work "${PHASE_ARG}" --stage phase_bootstrap)' in text
    assert 'INVENTORY_BUILD_INIT=$(gpd --raw init verify-work "${PHASE_ARG}" --stage inventory_build)' in text
    assert (
        'INTERACTIVE_VALIDATION_INIT=$(gpd --raw init verify-work "${PHASE_ARG}" --stage interactive_validation)'
        in text
    )
    assert 'GAP_REPAIR_INIT=$(gpd --raw init verify-work "${PHASE_ARG}" --stage gap_repair)' in text
    assert 'INIT=$(gpd --raw init verify-work "${PHASE_ARG}")' not in text
    assert "Do not assume reference ledgers, protocol bundles, or report schemas are loaded here" in text
    assert "**If non-empty `${PHASE_ARG}` is not found:**" in text
    assert "Wait for user response; load phase-only stages only after `PHASE_ARG` is set." in text


def test_verify_work_root_is_stage_index_not_active_authority() -> None:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "Compatibility index for the staged `verify-work` workflow." in text
    assert "workflows/verify-work/session-router.md" in text
    assert "workflows/verify-work/gap-repair.md" in text
    assert "@{GPD_INSTALL_DIR}/references/verification/core/proof-redteam-workflow-gate.md" not in text
    assert "verification_report_skeleton_bridge" not in text
    assert "verify_work_gap_planner" not in text


def test_verify_work_stage_authorities_are_lazy_by_stage() -> None:
    session_router = (WORKFLOW_STAGE_DIR / "session-router.md").read_text(encoding="utf-8")
    phase_bootstrap = (WORKFLOW_STAGE_DIR / "phase-bootstrap.md").read_text(encoding="utf-8")
    inventory_build = (WORKFLOW_STAGE_DIR / "inventory-build.md").read_text(encoding="utf-8")
    interactive_validation = (WORKFLOW_STAGE_DIR / "interactive-validation.md").read_text(encoding="utf-8")
    gap_repair = (WORKFLOW_STAGE_DIR / "gap-repair.md").read_text(encoding="utf-8")

    assert "@{GPD_INSTALL_DIR}/references/verification/core/proof-redteam-workflow-gate.md" not in session_router
    assert "verification_report_skeleton_bridge" not in session_router
    assert "verification_report_finalizer_bridge" not in session_router
    assert "GAP_REPAIR_INIT" not in session_router
    assert "templates/planner-subagent-prompt.md" not in session_router
    assert "verify_work_gap_planner" not in session_router

    assert "@{GPD_INSTALL_DIR}/references/verification/core/proof-redteam-workflow-gate.md" in phase_bootstrap
    assert "Use `proof_redteam_finalizer_bridge` as the helper-owned passed-audit bridge." in phase_bootstrap
    assert "verification_report_skeleton_bridge" not in phase_bootstrap
    assert "verify_work_gap_planner" not in phase_bootstrap

    assert "verification_report_skeleton_bridge" in inventory_build
    assert "verification_report_finalizer_bridge" in inventory_build
    assert 'id: "verify_work_verifier_report"' in inventory_build
    assert "GAP_REPAIR_INIT" not in inventory_build
    assert "verify_work_gap_planner" not in inventory_build

    assert "GAP_REPAIR_INIT=$(gpd --raw init verify-work" in interactive_validation
    assert "verify_work_gap_planner" not in interactive_validation

    assert "templates/planner-subagent-prompt.md" in gap_repair
    assert 'id: "verify_work_gap_planner"' in gap_repair


def test_verify_work_manifest_eager_authorities_follow_stage_boundaries() -> None:
    manifest = load_workflow_stage_manifest("verify-work")

    session_router = manifest.stage("session_router")
    phase_bootstrap = manifest.stage("phase_bootstrap")
    inventory_build = manifest.stage("inventory_build")
    interactive_validation = manifest.stage("interactive_validation")
    gap_repair = manifest.stage("gap_repair")

    assert session_router.mode_paths == ("workflows/verify-work/session-router.md",)
    assert session_router.loaded_authorities == ("workflows/verify-work/session-router.md",)
    assert "references/verification/core/proof-redteam-workflow-gate.md" not in session_router.eager_authorities()
    assert "workflows/verify-work/inventory-build.md" not in session_router.eager_authorities()
    assert "workflows/verify-work/gap-repair.md" not in session_router.eager_authorities()
    assert "templates/verification-report.md" not in session_router.eager_authorities()

    assert phase_bootstrap.mode_paths == ("workflows/verify-work/phase-bootstrap.md",)
    assert "references/verification/core/proof-redteam-workflow-gate.md" in phase_bootstrap.eager_authorities()
    assert "templates/verification-report.md" not in phase_bootstrap.eager_authorities()
    assert "workflows/verify-work/gap-repair.md" not in phase_bootstrap.eager_authorities()

    assert inventory_build.mode_paths == ("workflows/verify-work/inventory-build.md",)
    assert "verification_report_skeleton_bridge" in inventory_build.required_init_fields
    assert "templates/verification-report.md" not in inventory_build.eager_authorities()
    assert "workflows/verify-work/gap-repair.md" not in inventory_build.eager_authorities()

    assert interactive_validation.mode_paths == ("workflows/verify-work/interactive-validation.md",)
    assert "templates/verification-report.md" in interactive_validation.eager_authorities()
    assert "workflows/verify-work/gap-repair.md" not in interactive_validation.eager_authorities()

    assert gap_repair.mode_paths == ("workflows/verify-work/gap-repair.md",)
    assert "templates/verification-report.md" in gap_repair.eager_authorities()
    assert "references/protocols/error-propagation-protocol.md" in gap_repair.eager_authorities()
