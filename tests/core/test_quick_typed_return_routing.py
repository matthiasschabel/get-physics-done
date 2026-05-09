"""Focused assertions for quick workflow typed return routing."""

from __future__ import annotations

from pathlib import Path

from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"


def test_quick_workflow_routes_on_typed_gpd_return_and_applies_child_returns() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "quick")

    assert "gpd_return.status" in workflow
    assert "checkpoint" in workflow
    assert "completed means the summary gate and applicator passed" in workflow
    assert "blocked or failed means surface issues" in workflow
    assert "gpd_return.files_written" in workflow
    assert "loads staged quick init" in workflow
    assert "staged_loading" in workflow
    assert "reference_context" in workflow
    assert "default small-task path" in workflow
    assert "gpd --raw init quick \"$DESCRIPTION\" --stage reference_context" in workflow
    assert "workflows/quick/task-bootstrap.md" in workflow
    assert "workflows/quick/task-authoring.md" in workflow
    assert "tool_requirements" in workflow
    assert "gpd validate plan-preflight" in workflow
    assert "gpd apply-return-updates" in workflow
    assert "gpd state add-decision" in workflow
    assert "gpd state update" in workflow
    assert "gpd commit" in workflow
    assert "references/orchestration/child-artifact-gate.md" in workflow
    assert "references/orchestration/continuation-boundary.md" in workflow
    assert "role=`gpd-planner`" in workflow
    assert "expected=`${QUICK_DIR}/${next_num}-PLAN.md`" in workflow
    assert "role=`gpd-executor`" in workflow
    assert "expected=`${QUICK_DIR}/${next_num}-SUMMARY.md`" in workflow
    assert "recovery evidence only" in workflow
    assert "explicit main-context fallback with its own return" in workflow
