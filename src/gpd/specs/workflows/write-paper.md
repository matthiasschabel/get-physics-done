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
The public command includes only `workflows/write-paper/paper-bootstrap.md`.
Each later stage must be reached by a staged reload:

```bash
gpd --raw init write-paper --stage {stage_id}
```

Load only the active stage's `staged_loading.eager_authorities`. The first stage
must not eagerly load downstream authoring, bibliography, referee, review-panel,
or response-routing authorities.
</stage_loading_rule>

<canonical_references>
The staged authorities reference these canonical contracts as needed:

- `references/publication/publication-bootstrap-preflight.md`
- `templates/paper/publication-manuscript-root-preflight.md`
- `references/publication/publication-pipeline-modes.md`
- `references/publication/publication-review-round-artifacts.md`
- `references/publication/publication-response-writer-handoff.md`
- `templates/paper/paper-config-schema.md`
- `templates/paper/artifact-manifest-schema.md`
- `templates/paper/bibliography-audit-schema.md`
- `templates/paper/figure-tracker.md`
- `templates/paper/reproducibility-manifest.md`
- `templates/paper/author-response.md`
- `templates/paper/review-ledger-schema.md`
- `templates/paper/referee-decision-schema.md`
</canonical_references>
