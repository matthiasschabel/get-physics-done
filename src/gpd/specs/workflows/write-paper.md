<purpose>
Compatibility index for the staged `write-paper` workflow.
</purpose>

<stage_authorities>
The active authority is selected by `write-paper-stage-manifest.json`.
Do not load this index as a stage authority.

- `paper_bootstrap` -> `workflows/write-paper/paper-bootstrap.md`
  Bootstrap, lane normalization, manuscript/project preflight, evidence
  inventory, citation-source readiness, and fail-closed blockers. Read summary artifacts (`SUMMARY.md` and `*-SUMMARY.md`) from `GPD/phases/*/*SUMMARY.md` when milestone digests are insufficient.
- `outline_and_scaffold` -> `workflows/write-paper/outline-scaffold.md`
  Journal key selection, outline, `${PAPER_DIR}/PAPER-CONFIG.json`, and
  `gpd paper-build` scaffold generation.
- `figure_and_section_authoring` -> `workflows/write-paper/authoring.md`
  Figure tracker, figure preparation, section writer waves, and section child
  artifact gates.
- `consistency_and_references` -> `workflows/write-paper/consistency-references.md`
  Notation, placeholders, bibliography verification, bibliography audit refresh,
  and reproducibility manifest.
- `publication_review` -> `workflows/write-paper/publication-review-finalization.md`
  Project-backed staged peer-review handoff, external-authoring review routing,
  final review, and in-workflow revision/response artifacts. Response routing
  uses `templates/paper/author-response.md` and can classify `needs-calculation`.
</stage_authorities>

<stage_loading_rule>
The public command includes only `workflows/write-paper/paper-bootstrap.md`; later stage loading is manifest-owned, and each active payload supplies `staged_loading.field_access_instruction`.
Keep downstream authoring, bibliography, referee, review-panel, and response-routing authorities lazy until their matching stage.
</stage_loading_rule>

<canonical_references>
The staged authorities reference these canonical contracts as needed:

- `references/publication/publication-bootstrap-preflight.md`
- `templates/paper/publication-manuscript-root-preflight.md`
- `{GPD_INSTALL_DIR}/references/publication/publication-bootstrap-preflight.md`
- `{GPD_INSTALL_DIR}/references/publication/publication-pipeline-modes.md`
- `{GPD_INSTALL_DIR}/references/publication/publication-review-round-artifacts.md`
- `{GPD_INSTALL_DIR}/references/publication/publication-response-writer-handoff.md`
- `{GPD_INSTALL_DIR}/templates/paper/paper-config-schema.md`
- `{GPD_INSTALL_DIR}/templates/paper/artifact-manifest-schema.md`
- `{GPD_INSTALL_DIR}/templates/paper/bibliography-audit-schema.md`
- `{GPD_INSTALL_DIR}/templates/paper/figure-tracker.md`
- `{GPD_INSTALL_DIR}/templates/paper/reproducibility-manifest.md`
- `{GPD_INSTALL_DIR}/templates/paper/author-response.md`
- `{GPD_INSTALL_DIR}/templates/paper/review-ledger-schema.md`
- `{GPD_INSTALL_DIR}/templates/paper/referee-decision-schema.md`
</canonical_references>
