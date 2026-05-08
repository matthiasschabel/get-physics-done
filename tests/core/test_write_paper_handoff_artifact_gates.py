"""Assertions for write-paper handoff and artifact-gate semantics."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows" / "write-paper"
BOOTSTRAP = STAGE_DIR / "paper-bootstrap.md"
AUTHORING = STAGE_DIR / "authoring.md"
CONSISTENCY = STAGE_DIR / "consistency-references.md"
FINALIZATION = STAGE_DIR / "publication-review-finalization.md"


def test_write_paper_writer_completion_requires_typed_status_files_written_and_disk_artifact() -> None:
    source = AUTHORING.read_text(encoding="utf-8")

    assert "stage-recovery-gate.md" in source
    assert 'id: "write_paper_section_writer"' in source
    assert 'role: "gpd-paper-writer"' in source
    assert "${PAPER_DIR}/{section_path}.tex" in source
    assert "--require-status completed --require-files-written --fresh-after $SECTION_WRITER_HANDOFF_STARTED_AT" in source
    assert "Existing `.tex` files can make a resumed wave current, but they are not fresh child handoff success." in source
    assert "Treat the emitted `.tex` file as the success artifact gate for each section only after the tuple passes" in source


def test_write_paper_bibliography_completion_requires_typed_status_files_written_and_disk_artifacts() -> None:
    source = CONSISTENCY.read_text(encoding="utf-8")

    assert 'id: "write_paper_bibliographer"' in source
    assert "Return a typed `gpd_return` envelope for the `write_paper_bibliographer` child_gate." in source
    assert "Always list `${PAPER_DIR}/CITATION-AUDIT.md` and `GPD/references-status.json` in `gpd_return.files_written`; list `{ACTIVE_BIBLIOGRAPHY_PATH}` only when the bibliography file changed." in source
    assert "and `{ACTIVE_BIBLIOGRAPHY_PATH}` only if the bibliography file changed" not in source
    assert "Bibliography: `{ACTIVE_BIBLIOGRAPHY_PATH}` (the resolved active bibliography for this manuscript)" in source
    assert "${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json after paper-build refresh" in source
    assert "bibliography_audit_clean before strict review" in source
    assert "Older audit files are recovery evidence only." in source


def test_write_paper_response_artifact_completion_requires_typed_status_files_written_and_disk_artifacts() -> None:
    source = FINALIZATION.read_text(encoding="utf-8")

    assert "stage-recovery-gate.md" in source
    assert 'id: "write_paper_response_pair"' in source
    assert 'role: "gpd-paper-writer"' in source
    assert "${selected_publication_root}/AUTHOR-RESPONSE{round_suffix}.md" in source
    assert "${selected_review_root}/REFEREE_RESPONSE{round_suffix}.md" in source
    assert "publication-response-writer-handoff.md frontmatter, round, and manuscript binding" in source
    assert "Apply `{GPD_INSTALL_DIR}/references/publication/stage-recovery-gate.md` through this tuple before treating the response pair as complete." in source


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
