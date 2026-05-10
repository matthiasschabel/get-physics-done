"""Focused assertions for coordinator-routing contracts."""

from __future__ import annotations

from pathlib import Path

from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
AGENTS_DIR = REPO_ROOT / "src" / "gpd" / "agents"


def _read(name: str) -> str:
    if name in {"new-project.md", "new-milestone.md"}:
        return workflow_authority_text(WORKFLOWS_DIR, name)
    return (WORKFLOWS_DIR / name).read_text(encoding="utf-8")


def test_debug_workflow_routes_on_typed_status_and_file_backed_diagnosis() -> None:
    workflow = _read("debug.md")

    assert "gpd_return.status: completed" in workflow
    assert "gpd_return.status: checkpoint" in workflow
    assert "gpd_return.status: blocked" in workflow
    assert "GPD/debug/{slug}.md" in workflow
    assert "session_status: diagnosed" in workflow
    assert "The debug session file at `GPD/debug/{slug}.md` keeps the debug-session `status` lifecycle" in workflow
    assert "does not use `session_status`" in workflow
    assert "session file" in workflow
    assert "Do not route on heading markers in the returned text" in workflow
    assert "spawn a fresh continuation run" in workflow
    assert "## ROOT CAUSE FOUND" not in workflow
    assert "## INVESTIGATION INCONCLUSIVE" not in workflow


def test_new_project_and_new_milestone_route_roadmaps_on_typed_status() -> None:
    new_project = _read("new-project.md")
    new_milestone = _read("new-milestone.md")

    for workflow in (new_project, new_milestone):
        assert "gpd_return.status: completed" in workflow
        assert "failure_route:" in workflow
        assert "`blocked`" in workflow
        assert "--require-status completed --require-files-written" in workflow
        assert "GPD/REQUIREMENTS.md" in workflow
        assert "child gate" in workflow

    assert 'id: "project_roadmapper"' in new_project
    assert '"GPD/ROADMAP.md"' in new_project
    assert '"GPD/STATE.md"' in new_project
    assert '"GPD/REQUIREMENTS.md"' in new_project
    assert 'return_profile: "roadmapper"' in new_project
    assert "shared_state_policy=direct for this legacy init handoff" in new_project
    assert "do not invent an alternate roadmap path" in new_project
    assert "Headings such as\n`## ROADMAP CREATED` or `## ROADMAP BLOCKED` are not authority" in new_project
    assert 'id: "milestone_roadmapper"' in new_milestone
    assert '"GPD/ROADMAP.md"' in new_milestone
    assert '"GPD/REQUIREMENTS.md"' in new_milestone
    assert 'return_profile: "roadmapper"' in new_milestone
    assert "shared_state_policy: return_only" in new_milestone
    assert "direct roadmapper edit to\n`GPD/STATE.md` is not success proof." in new_milestone
    assert "Project contract gate: {project_contract_gate}" in new_milestone
    assert "Project contract load info: {project_contract_load_info}" in new_milestone
    assert "Project contract validation: {project_contract_validation}" in new_milestone
    assert "request fresh continuation" in new_milestone
    assert "main workflow applies accepted state changes with gpd state patch / gpd state add-decision after the artifact gate" in new_milestone


def test_parameter_sweep_balanced_mode_is_not_unconditionally_paused() -> None:
    workflow = _read("parameter-sweep.md")

    assert "autonomy=supervised" in workflow
    assert "autonomy=balanced" in workflow
    assert "only then pause for user approval" in workflow
    assert "If `autonomy=supervised`, show this plan and ask for confirmation before generating plans." in workflow
    assert "Proceed? (y/n)" not in workflow


def test_audit_milestone_consumes_a_typed_consistency_checker_return_without_routing_convention_ownership() -> None:
    workflow = _read("audit-milestone.md")
    checker = (AGENTS_DIR / "gpd-consistency-checker.md").read_text(encoding="utf-8")

    assert workflow.count('subagent_type="gpd-consistency-checker"') == 1
    assert "gpd-notation-coordinator" not in workflow
    assert "Consistency checker's report (notation conflicts, parameter mismatches, broken reasoning chains) — or note \"skipped\" if agent failed" in workflow
    assert "If the consistency checker agent fails to spawn or returns an error:" in workflow
    assert "status: completed" in checker
    assert "files_written:\n    - GPD/phases/03-conventions/CONSISTENCY-CHECK.md" in checker
    assert "This is a one-shot handoff: inspect once, write once, return once." in checker
    assert "Human-readable headings in the report are presentation only; route on `gpd_return.status`." in checker
