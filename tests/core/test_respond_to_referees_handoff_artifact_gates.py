"""Assertions for respond-to-referees handoff and artifact-gate semantics."""

from __future__ import annotations

from pathlib import Path

import yaml

from gpd.core.child_handoff import ChildGateTuple, child_gate_tuple_from_payload
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"


def _workflow() -> str:
    return workflow_authority_text(WORKFLOWS_DIR, "respond-to-referees")


def _yaml_blocks(source: str) -> list[dict]:
    blocks: list[dict] = []
    for block in source.split("```yaml")[1:]:
        yaml_text = block.split("```", 1)[0]
        payload = yaml.safe_load(yaml_text)
        if isinstance(payload, dict):
            blocks.append(payload)
    return blocks


def _child_gate(source: str, gate_id: str) -> ChildGateTuple:
    for payload in _yaml_blocks(source):
        child_gate = payload.get("child_gate")
        if isinstance(child_gate, dict) and child_gate.get("id") == gate_id:
            return child_gate_tuple_from_payload(payload)
    raise AssertionError(f"missing child gate {gate_id}")


def _aggregate_gate(source: str, gate_id: str) -> dict:
    for payload in _yaml_blocks(source):
        aggregate_gate = payload.get("aggregate_child_gate")
        if isinstance(aggregate_gate, dict) and aggregate_gate.get("id") == gate_id:
            return aggregate_gate
    raise AssertionError(f"missing aggregate child gate {gate_id}")


def _artifact_paths(gate: ChildGateTuple) -> tuple[str, ...]:
    return tuple(artifact.path for artifact in gate.expected_artifacts)


def test_respond_to_referees_group_b_completion_requires_fresh_child_files_written_and_rejects_stale_edits() -> None:
    source = _workflow()
    gate = _child_gate(source, "respond_to_referees_revision_section")

    assert (
        "Return through the `respond_to_referees_revision_section` child_gate so the revised section file plus `${RESPONSE_AUTHOR_PATH}` and `${RESPONSE_REFEREE_PATH}` are all named."
        in source
    )
    assert gate.role == "gpd-paper-writer"
    assert gate.required_status == "completed"
    assert _artifact_paths(gate) == (
        "${PAPER_DIR}/{resolved_section_file}",
        "${RESPONSE_AUTHOR_PATH}",
        "${RESPONSE_REFEREE_PATH}",
    )
    assert gate.allowed_roots == ("${PAPER_DIR}", "${selected_publication_root}", "${selected_review_root}")
    assert gate.freshness is not None
    assert gate.freshness.marker == "$REVISION_SECTION_HANDOFF_STARTED_AT"
    assert "gpd validate handoff-artifacts for revised section plus both response artifacts" in gate.validators
    assert "publication-response-writer-handoff.md frontmatter, round, and manuscript binding" in source
    assert "target section has expected revision markers or substantive edits" in source
    assert "Re-apply the `respond_to_referees_revision_section` tuple first." in source
    assert "stage-recovery-gate.md" in source
    assert "If the section file changed but the response trackers did not, or vice versa, treat that section as failed" in source


def test_respond_to_referees_response_letter_generation_stays_file_backed_and_fresh_return_based() -> None:
    source = _workflow()
    gate = _aggregate_gate(source, "respond_to_referees_response_pair_current")

    assert gate["required_child_gates"] == [
        "respond_to_referees_revision_section for every launched Group B section"
    ]
    assert gate["expected_artifacts"] == [
        "every required revised section under ${PAPER_DIR}",
        "${RESPONSE_AUTHOR_PATH}",
        "${RESPONSE_REFEREE_PATH}",
    ]
    assert "expected mirrored artifacts exist on disk" in gate["validators"]
    assert "response frontmatter binds to the active manuscript path and review round when the subject is explicit" in source
    assert "Those two GPD-owned response artifacts stay canonical even when the manuscript subject is explicit or external." in source
    assert "If the manuscript subject is an explicit external artifact, keep auxiliary response outputs under the selected GPD roots" in source
