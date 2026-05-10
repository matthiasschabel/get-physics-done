"""Workflow seam assertions for the research-synthesizer vertical."""

from __future__ import annotations

from pathlib import Path

from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_new_project_synthesizer_seam_routes_on_typed_returns_and_rejects_stale_summary_files() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "new-project")

    assert "After all 4 scout artifacts pass the gate, spawn synthesizer to create SUMMARY.md:" in workflow
    assert "<research_files>" in workflow
    assert "- GPD/PROJECT.md" in workflow
    assert "- GPD/config.json" in workflow
    assert "- GPD/literature/SUMMARY.md (if re-synthesizing an existing survey)" in workflow
    assert "Synthesizer child gate:" in workflow
    assert "return_profile: \"synthesizer\"" in workflow
    assert "gpd validate handoff-artifacts - --expected GPD/literature/SUMMARY.md" in workflow
    assert "Route\n`checkpoint` -> fresh continuation" in workflow
    assert "`blocked` -> surface blocker and stop synth\npath until resolved" in workflow
    assert "`failed` -> retry once then stop" in workflow
    assert "surface the blocker rather than creating a fallback summary in the main context" in workflow


def test_new_milestone_synthesizer_seam_keeps_child_contract_visible_and_task_local() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "new-milestone")

    assert "Route `checkpoint`, `blocked`, or final `failed` through\n`references/orchestration/child-artifact-gate.md`" in workflow
    assert "After all 4 complete and required artifacts are present, spawn synthesizer:" in workflow
    assert "task(prompt=\"First, read {GPD_AGENTS_DIR}/gpd-research-synthesizer.md for your role and instructions." in workflow
    assert "<files_to_read>" in workflow
    assert "- GPD/literature/PRIOR-WORK.md" in workflow
    assert "- GPD/literature/METHODS.md" in workflow
    assert "- GPD/literature/COMPUTATIONAL.md" in workflow
    assert "- GPD/literature/PITFALLS.md" in workflow
    assert "Write to: GPD/literature/SUMMARY.md" in workflow
    assert "Use template: {GPD_INSTALL_DIR}/templates/research-project/SUMMARY.md" in workflow
    assert "<spawn_contract>" in workflow
    assert "allowed_paths:" in workflow
    assert "    - GPD/literature/SUMMARY.md" in workflow
    assert "shared_state_policy: return_only" in workflow
    assert "This synthesizer contract is task-local. Do not reuse survey write scopes or widen the summary handoff." in workflow
    assert "Synthesizer child gate:" in workflow
    assert "gpd validate handoff-artifacts - --expected GPD/literature/SUMMARY.md" in workflow
    assert "Do not display or commit `SUMMARY.md`, create it in the\nmain context" in workflow
