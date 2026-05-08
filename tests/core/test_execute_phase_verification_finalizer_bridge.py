"""Execute-phase verification finalizer bridge wiring tests."""

from __future__ import annotations

from pathlib import Path

from gpd.core.context import init_execute_phase
from gpd.core.workflow_staging import load_workflow_stage_manifest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"
EXECUTE_PHASE_STAGE_DIR = WORKFLOWS_DIR / "execute-phase"


def _write_phase(root: Path) -> None:
    phase_dir = root / "GPD" / "phases" / "01-demo"
    phase_dir.mkdir(parents=True)
    (phase_dir / "01-PLAN.md").write_text(
        "---\nwave: 1\ndepends_on: []\nfiles_modified: []\n---\n\n## Task 1\n",
        encoding="utf-8",
    )


def test_execute_phase_aggregate_stage_contains_verification_report_bridges(tmp_path: Path) -> None:
    _write_phase(tmp_path)

    payload = init_execute_phase(tmp_path, "1", stage="aggregate_and_verify")

    assert "verification_report_skeleton_bridge" in payload
    assert "verification_report_finalizer_bridge" in payload
    assert payload["verification_report_skeleton_bridge"]["command_name"] == "gpd verification-report skeleton"
    assert payload["verification_report_finalizer_bridge"]["command_name"] == "gpd verification-report finalize"
    assert payload["verification_report_finalizer_bridge"]["expected_verification_path"].endswith(
        "GPD/phases/01-demo/01-VERIFICATION.md"
    )


def test_execute_phase_manifest_scopes_bridges_to_aggregate_stage() -> None:
    manifest = load_workflow_stage_manifest("execute-phase")

    assert "verification_report_skeleton_bridge" in manifest.stage("aggregate_and_verify").required_init_fields
    assert "verification_report_finalizer_bridge" in manifest.stage("aggregate_and_verify").required_init_fields
    assert "verification_report_skeleton_bridge" not in manifest.stage("phase_bootstrap").required_init_fields
    assert "verification_report_finalizer_bridge" not in manifest.stage("phase_bootstrap").required_init_fields


def test_execute_phase_workflow_routes_report_construction_through_finalizer_bridge() -> None:
    workflow = (EXECUTE_PHASE_STAGE_DIR / "aggregate-and-verify.md").read_text(encoding="utf-8")

    assert "verification_report_finalizer_bridge" in workflow
    assert "verification_report_skeleton_bridge" in workflow
    assert "Do not hand-author `VERIFICATION.md` YAML in this workflow." in workflow
    assert "verification-report skeleton/finalizer bridge" in workflow
    assert workflow.index("verification_report_finalizer_bridge") < workflow.index("Verifier status route")
