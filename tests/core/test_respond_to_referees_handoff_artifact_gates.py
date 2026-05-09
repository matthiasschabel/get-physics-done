"""Assertions for respond-to-referees handoff and artifact-gate semantics."""

from __future__ import annotations

from pathlib import Path

from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"


def _workflow() -> str:
    return workflow_authority_text(WORKFLOWS_DIR, "respond-to-referees")


def test_respond_to_referees_group_b_completion_requires_fresh_child_files_written_and_rejects_stale_edits() -> None:
    source = _workflow()

    assert (
        "Return through the `respond_to_referees_revision_section` child_gate so the revised section file plus `${RESPONSE_AUTHOR_PATH}` and `${RESPONSE_REFEREE_PATH}` are all named."
        in source
    )
    assert 'id: "respond_to_referees_revision_section"' in source
    assert "${PAPER_DIR}/{resolved_section_file}" in source
    assert "publication-response-writer-handoff.md frontmatter, round, and manuscript binding" in source
    assert "target section has expected revision markers or substantive edits" in source
    assert "Re-apply the `respond_to_referees_revision_section` tuple first." in source
    assert "stage-recovery-gate.md" in source
    assert "If the section file changed but the response trackers did not, or vice versa, treat that section as failed" in source


def test_respond_to_referees_response_letter_generation_stays_file_backed_and_fresh_return_based() -> None:
    source = _workflow()

    assert "aggregate_child_gate:" in source
    assert "id: respond_to_referees_response_pair_current" in source
    assert "respond_to_referees_revision_section for every launched Group B section" in source
    assert "expected mirrored artifacts exist on disk" in source
    assert "response frontmatter binds to the active manuscript path and review round when the subject is explicit" in source
    assert "Those two GPD-owned response artifacts stay canonical even when the manuscript subject is explicit or external." in source
    assert "If the manuscript subject is an explicit external artifact, keep auxiliary response outputs under the selected GPD roots" in source
