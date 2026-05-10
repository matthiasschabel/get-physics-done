"""Assertions for write-paper handoff and artifact-gate semantics."""

from __future__ import annotations

from pathlib import Path

import yaml

from gpd.core.child_handoff import ChildGateTuple, child_gate_tuple_from_payload

REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows" / "write-paper"
BOOTSTRAP = STAGE_DIR / "paper-bootstrap.md"
AUTHORING = STAGE_DIR / "authoring.md"
CONSISTENCY = STAGE_DIR / "consistency-references.md"
FINALIZATION = STAGE_DIR / "publication-review-finalization.md"


def _child_gate(source: str, gate_id: str) -> ChildGateTuple:
    for block in source.split("```yaml")[1:]:
        yaml_text = block.split("```", 1)[0]
        payload = yaml.safe_load(yaml_text)
        if not isinstance(payload, dict):
            continue
        child_gate = payload.get("child_gate")
        if isinstance(child_gate, dict) and child_gate.get("id") == gate_id:
            return child_gate_tuple_from_payload(payload)
    raise AssertionError(f"missing child gate {gate_id}")


def _artifact_paths(gate: ChildGateTuple) -> tuple[str, ...]:
    return tuple(artifact.path for artifact in gate.expected_artifacts)


def test_write_paper_writer_completion_requires_typed_status_files_written_and_disk_artifact() -> None:
    source = AUTHORING.read_text(encoding="utf-8")
    normalized_source = " ".join(source.split())
    gate = _child_gate(source, "write_paper_section_writer")

    assert "stage-recovery-gate.md" in source
    assert gate.role == "gpd-paper-writer"
    assert gate.required_status == "completed"
    assert _artifact_paths(gate) == ("${PAPER_DIR}/{section_path}.tex",)
    assert gate.allowed_roots == ("${PAPER_DIR}",)
    assert gate.freshness is not None
    assert gate.freshness.marker == "$SECTION_WRITER_HANDOFF_STARTED_AT"
    assert any(
        "--require-status completed --require-files-written --fresh-after $SECTION_WRITER_HANDOFF_STARTED_AT"
        in validator
        for validator in gate.validators
    )
    assert (
        "Existing `.tex` files can make a resumed wave current, but they are not fresh child handoff success."
        in normalized_source
    )
    assert normalized_source.count("Existing `.tex` files can make a resumed wave current") == 1
    assert "section authoring is complete only after the emitted `.tex` path passes this" in source


def test_write_paper_bibliography_completion_requires_typed_status_files_written_and_disk_artifacts() -> None:
    source = CONSISTENCY.read_text(encoding="utf-8")
    gate = _child_gate(source, "write_paper_bibliographer")

    assert gate.role == "gpd-bibliographer"
    assert gate.required_status == "completed"
    assert _artifact_paths(gate) == (
        "${PAPER_DIR}/CITATION-AUDIT.md",
        "GPD/references-status.json",
        "{ACTIVE_BIBLIOGRAPHY_PATH} only when changed",
        "${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json after paper-build refresh",
    )
    assert gate.allowed_roots == ("${PAPER_DIR}", "GPD")
    assert gate.freshness is not None
    assert gate.freshness.marker == "$BIBLIO_HANDOFF_STARTED_AT"
    assert "bibliography_audit_clean before strict review" in gate.validators
    assert "Return a typed `gpd_return` envelope for the `write_paper_bibliographer` child_gate." in source
    assert "Always list `${PAPER_DIR}/CITATION-AUDIT.md` and `GPD/references-status.json` in `gpd_return.files_written`; list `{ACTIVE_BIBLIOGRAPHY_PATH}` only when the bibliography file changed." in source
    assert "and `{ACTIVE_BIBLIOGRAPHY_PATH}` only if the bibliography file changed" not in source
    assert "Bibliography: `{ACTIVE_BIBLIOGRAPHY_PATH}` (the resolved active bibliography for this manuscript)" in source
    assert "${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json after paper-build refresh" in source
    assert "bibliography_audit_clean before strict review" in source
    assert "Older audit files are recovery evidence only." in source


def test_write_paper_response_artifact_completion_requires_typed_status_files_written_and_disk_artifacts() -> None:
    source = FINALIZATION.read_text(encoding="utf-8")
    gate = _child_gate(source, "write_paper_response_pair")

    assert "stage-recovery-gate.md" in source
    assert gate.role == "gpd-paper-writer"
    assert gate.required_status == "completed"
    assert _artifact_paths(gate) == (
        "${selected_publication_root}/AUTHOR-RESPONSE{round_suffix}.md",
        "${selected_review_root}/REFEREE_RESPONSE{round_suffix}.md",
    )
    assert gate.allowed_roots == ("${selected_publication_root}", "${selected_review_root}")
    assert gate.freshness is not None
    assert gate.freshness.marker == "$RESPONSE_HANDOFF_STARTED_AT"
    assert "publication-response-writer-handoff.md frontmatter, round, and manuscript binding" in source
    assert "Response-pair completion requires this callsite tuple to pass for both paths." in source


def test_write_paper_bootstrap_contract_is_explicit_about_project_and_bounded_external_lanes() -> None:
    source = BOOTSTRAP.read_text(encoding="utf-8")

    assert "Use `publication_subject*`, `manuscript_*`, and `publication_bootstrap*` from init / strict preflight" in source
    assert "The resolved manuscript root may already be" in source
    assert "the managed project lane `GPD/publication/{subject_slug}/manuscript`" in source
    assert "For `external_authoring_intake`, use the strict command preflight's managed subject handoff" in source
    assert "`GPD/publication/{subject_slug}/intake/` is intake/provenance state only; it must not participate in manuscript-root discovery" in source
    assert "a resolved `${PAPER_DIR}` under `GPD/publication/{subject_slug}/manuscript` may be either the managed project lane or the bounded external-authoring lane" in source
    assert "do not mine generic folders or widen into arbitrary external-manuscript discovery; the only non-project lane is explicit `--intake`" in source
    assert "do not invent an external-manuscript `write-paper` flow or relax the project-required contract" not in source


def test_write_paper_external_lane_stops_at_manuscript_root_handoff_and_routes_to_peer_review() -> None:
    source = FINALIZATION.read_text(encoding="utf-8")

    assert "**External-authoring lane:** do **not** run the embedded staged panel here." in source
    assert "Embedded `write-paper` review parity for the bounded external-authoring lane is deferred" in source
    assert "`${PAPER_DIR}/PAPER-CONFIG.json`" in source
    assert "`${PAPER_DIR}/ARTIFACT-MANIFEST.json`" in source
    assert "`${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json`" in source
    assert "`${PAPER_DIR}/reproducibility-manifest.json`" in source
    assert "route the user to standalone `gpd:peer-review`" in source
    assert "do not recommend `gpd:arxiv-submission` directly from this lane" in source
