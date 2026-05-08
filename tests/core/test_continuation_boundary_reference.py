"""Assertions for the shared continuation-boundary reference."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE = REPO_ROOT / "src/gpd/specs/references/orchestration/continuation-boundary.md"
OWNED_SURFACES = [
    REPO_ROOT / "src/gpd/specs/templates/continuation-prompt.md",
    REPO_ROOT / "src/gpd/specs/references/execution/execute-plan-checkpoints.md",
    REPO_ROOT / "src/gpd/agents/gpd-roadmapper.md",
    REPO_ROOT / "src/gpd/agents/gpd-notation-coordinator.md",
    REPO_ROOT / "src/gpd/agents/gpd-literature-reviewer.md",
    REPO_ROOT / "src/gpd/agents/gpd-paper-writer.md",
    REPO_ROOT / "src/gpd/agents/gpd-debugger.md",
    REPO_ROOT / "src/gpd/agents/gpd-project-researcher.md",
    REPO_ROOT / "src/gpd/agents/gpd-plan-checker.md",
    REPO_ROOT / "src/gpd/agents/gpd-consistency-checker.md",
]


def test_continuation_boundary_reference_defines_the_one_shot_contract() -> None:
    content = REFERENCE.read_text(encoding="utf-8")

    assert "A spawned `task()` run is one-shot." in content
    assert "returns a typed `gpd_return.status: checkpoint` envelope and stops" in content
    assert "must not wait for the user" in content
    assert "start a fresh continuation handoff" in content
    assert "use `files_written: []` when the checkpoint intentionally defers writes" in content
    assert "Include durable bounded-segment resume details only when the child prompt explicitly owns" in content
    assert "return child-owned `checkpoint_intent`" in content
    assert "`checkpoint_intent` is not durable authority until the parent/applicator supplies parent-owned resume context" in content
    assert "verify them on disk" in content


def test_owned_continuation_surfaces_reference_the_boundary_without_eager_include() -> None:
    token = "references/orchestration/continuation-boundary.md"
    eager_include = f"@{{GPD_INSTALL_DIR}}/{token}"

    for path in OWNED_SURFACES:
        content = path.read_text(encoding="utf-8")
        assert token in content, path.relative_to(REPO_ROOT)
        assert eager_include not in content, path.relative_to(REPO_ROOT)
