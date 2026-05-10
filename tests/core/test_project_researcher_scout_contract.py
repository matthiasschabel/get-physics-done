"""Assertions for the new-project scout contract."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
AGENTS_DIR = REPO_ROOT / "src" / "gpd" / "agents"


def _read_workflow(name: str) -> str:
    return (WORKFLOWS_DIR / name).read_text(encoding="utf-8")


def _read_agent(name: str) -> str:
    return (AGENTS_DIR / name).read_text(encoding="utf-8")


def test_project_researcher_uses_staged_mode_and_one_shot_checkpoint_language() -> None:
    source = _read_agent("gpd-project-researcher.md")

    assert "one-shot handoff and fresh-continuation semantics" in source
    assert "return the typed checkpoint and stop" in source
    assert "{GPD_INSTALL_DIR}/references/orchestration/continuation-boundary.md" in source
    assert "Do not wait inside the same spawned run." not in source
    assert "Do not query config or reread init JSON inside this agent." in source
    assert "Write only the assigned `write_scope.allowed_paths`" in source
    assert "Execute all 4 parallel research threads independently" not in source


def test_new_project_scout_returns_route_on_typed_status_and_files_written() -> None:
    workflow = _read_workflow("new-project.md")

    assert "Use the staged `research_mode` from `POST_SCOPE_INIT` for all scout handoffs." in workflow
    assert "Scout child gate:" in workflow
    assert 'id: "literature_scouts"' in workflow
    assert 'role: "gpd-project-researcher"' in workflow
    assert "GPD/literature/PRIOR-WORK.md" in workflow
    assert "GPD/literature/METHODS.md" in workflow
    assert "GPD/literature/COMPUTATIONAL.md" in workflow
    assert "GPD/literature/PITFALLS.md" in workflow
    assert "gpd validate handoff-artifacts - --expected GPD/literature/{FILE}" in workflow
    assert 'freshness_marker: "after $SCOUT_HANDOFF_STARTED_AT per scout"' in workflow
    assert "--require-status completed --require-files-written" in workflow
    assert "`checkpoint` -> fresh\ncontinuation" in workflow
    assert "references/orchestration/child-artifact-gate.md" in workflow


def test_new_project_synthesizer_return_stays_typed_and_file_backed() -> None:
    workflow = _read_workflow("new-project.md")

    assert "Synthesizer child gate:" in workflow
    assert 'id: "literature_synthesizer"' in workflow
    assert 'role: "gpd-research-synthesizer"' in workflow
    assert 'return_profile: "synthesizer"' in workflow
    assert "GPD/literature/SUMMARY.md" in workflow
    assert "gpd validate handoff-artifacts - --expected GPD/literature/SUMMARY.md" in workflow
    assert 'failure_route: "retry once | repair prompt once | stop synth path' in workflow
    assert "rather than creating a fallback summary in the main context" in workflow
