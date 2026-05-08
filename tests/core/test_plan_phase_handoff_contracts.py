"""Focused plan-phase spawned handoff contract assertions."""

from __future__ import annotations

from tests.core.test_spawn_contracts import (
    WORKFLOWS_DIR,
    _assert_spawn_contract,
    _find_single_task,
    _task_blocks_by_agent,
)


def test_plan_phase_planner_and_checker_handoffs_carry_inline_spawn_contracts() -> None:
    path = WORKFLOWS_DIR / "plan-phase.md"
    workflow = path.read_text(encoding="utf-8")
    planner_tasks = _task_blocks_by_agent(path, "gpd-planner")
    assert len(planner_tasks) >= 2
    for task in planner_tasks:
        _assert_spawn_contract(
            task,
            ("{phase_dir}/*-PLAN.md",),
            expected_write_paths=("{phase_dir}/*-PLAN.md",),
        )
        assert "artifact_gate:" not in task.text

    assert "Planner child artifact gate: apply `references/orchestration/child-artifact-gate.md`" in workflow
    assert "Revision planner child artifact gate: apply `references/orchestration/child-artifact-gate.md`" in workflow
    assert 'id: "phase_researcher_context_refresh"' in workflow
    assert 'id: "planner_initial_plan"' in workflow
    assert 'id: "planner_revision"' in workflow
    assert "gpd validate plan-contract <each fresh plan>" in workflow
    assert "gpd validate plan-preflight <each fresh plan>" in workflow

    checker = _find_single_task(path, "gpd-plan-checker")
    _assert_spawn_contract(checker, ())
    assert "mode: read_only" in checker.text
    assert "artifact_gate:" not in checker.text
    assert "Checker child artifact gate: apply `references/orchestration/child-artifact-gate.md`" in workflow
    assert "files_written: []" in workflow
    assert "approved/blocked plan-ID reconciliation against FRESH_PLAN_FILES" in workflow
