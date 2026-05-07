"""Focused assertions for quick workflow typed return routing."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
QUICK_WORKFLOW = REPO_ROOT / "src" / "gpd" / "specs" / "workflows" / "quick.md"


def test_quick_workflow_routes_on_typed_gpd_return_and_applies_child_returns() -> None:
    workflow = QUICK_WORKFLOW.read_text(encoding="utf-8")

    assert "gpd_return.status" in workflow
    assert "checkpoint" in workflow
    assert "completed means the summary gate and applicator passed" in workflow
    assert "blocked or failed means surface issues" in workflow
    assert "gpd_return.files_written" in workflow
    assert "loads staged quick init" in workflow
    assert "staged_loading" in workflow
    assert "tool_requirements" in workflow
    assert "gpd validate plan-preflight" in workflow
    assert "gpd apply-return-updates" in workflow
    assert "references/orchestration/child-artifact-gate.md" in workflow
    assert "references/orchestration/continuation-boundary.md" in workflow
    assert "role=`gpd-planner`" in workflow
    assert "expected=`${QUICK_DIR}/${next_num}-PLAN.md`" in workflow
    assert "role=`gpd-executor`" in workflow
    assert "expected=`${QUICK_DIR}/${next_num}-SUMMARY.md`" in workflow
    assert "recovery evidence only" in workflow
    assert "explicit main-context fallback with its own return" in workflow
