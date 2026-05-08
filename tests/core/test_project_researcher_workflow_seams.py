"""Workflow seam assertions for the project-researcher vertical."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_new_project_project_researcher_scouts_route_on_typed_return_and_reject_stale_results() -> None:
    workflow = _read(WORKFLOWS_DIR / "new-project.md")

    assert workflow.count('subagent_type="gpd-project-researcher"') == 4
    assert 'id: "literature_scouts"' in workflow
    assert 'return_profile: "researcher"' in workflow
    assert 'freshness_marker: "after $SCOUT_HANDOFF_STARTED_AT per scout"' in workflow
    assert "--require-status completed --require-files-written" in workflow
    assert 'failure_route: "retry missing scout once | repair prompt once | stop this scout path' in workflow
    assert "Status route: `checkpoint` -> present checkpoint and spawn a fresh continuation" in workflow
    assert "Do not proceed with a partial literature survey" in workflow


def test_new_milestone_project_researcher_scouts_require_fresh_continuations_and_stale_file_rejection() -> None:
    workflow = _read(WORKFLOWS_DIR / "new-milestone.md")

    assert workflow.count("Common structure for all 4 scouts:") == 1
    assert 'id: "milestone_literature_scouts"' in workflow
    assert 'role: "gpd-project-researcher"' in workflow
    assert "GPD/literature/PRIOR-WORK.md" in workflow
    assert "GPD/literature/METHODS.md" in workflow
    assert "GPD/literature/COMPUTATIONAL.md" in workflow
    assert "GPD/literature/PITFALLS.md" in workflow
    assert 'failure_route: "retry missing scout once | repair prompt once | stop survey path' in workflow
    assert "Status route: `checkpoint`, `blocked`, or final `failed`" in workflow
    assert "before counting any scout as complete" in workflow
    assert "references/orchestration/continuation-boundary.md" in workflow
