from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
AGENTS_DIR = REPO_ROOT / "src" / "gpd" / "agents"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_literature_review_workflow_routes_on_typed_status_and_artifact_gate() -> None:
    workflow = _read(WORKFLOWS_DIR / "literature-review.md")

    assert "Route on `gpd_return.status` and the artifact gate;" in workflow
    assert "presentation only" in workflow
    assert "Verify `GPD/literature/{slug}-REVIEW.md` exists on disk" in workflow
    assert "Verify `GPD/literature/{slug}-CITATION-SOURCES.json` exists on disk and remains aligned with the review's Full Reference List" in workflow
    assert (
        "Return `gpd_return.status: completed` only when the review, citation sidecar, and citation audit "
        "are named in `gpd_return.files_written` and present/readable on disk"
    ) in workflow
    assert "gpd_return.status: completed" in workflow
    assert "gpd_return.status: checkpoint" in workflow
    assert "fresh continuation run" in workflow


def test_literature_reviewer_shows_base_return_fields_and_one_shot_checkpointing() -> None:
    agent = _read(AGENTS_DIR / "gpd-literature-reviewer.md")

    assert "The markdown `## REVIEW COMPLETE` heading is presentation only." in agent
    assert "The `## CHECKPOINT REACHED` heading below is presentation only." in agent
    assert "When reaching a checkpoint, return a typed `gpd_return` checkpoint and stop." in agent
    assert "stop at the continuation boundary" in agent
    assert "Use `gpd_return.status: completed` for a finished review." in agent

    completed_block = agent.split("Use `gpd_return.status: completed` for a finished review.", 1)[1]
    status_idx = completed_block.index("  status: completed")
    files_idx = completed_block.index("  files_written: [GPD/literature/spectral-form-factor-REVIEW.md]")
    issues_idx = completed_block.index("  issues: []")
    next_actions_idx = completed_block.index('  next_actions: ["gpd:literature-review --synthesize"]')
    papers_idx = completed_block.index("  papers_reviewed: 12")

    assert status_idx < files_idx < issues_idx < next_actions_idx < papers_idx
