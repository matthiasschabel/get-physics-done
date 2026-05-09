<purpose>
Compatibility index for the staged `literature-review` workflow.
</purpose>

<stage_authorities>
The active authority is selected by `literature-review-stage-manifest.json`.
Do not load this index as a stage authority.

- `review_bootstrap` -> `workflows/literature-review/review-bootstrap.md`
  Topic intake, project-aware preflight, contract-gate visibility, scope confirmation, and deferred reference-artifact policy.
- `scope_locked` -> `workflows/literature-review/scope-locked.md`
  Scoped reference artifact loading, literature-reviewer handoff, review and citation-sidecar artifact gate, and checkpoint routing.
- `review_handoff` -> `workflows/literature-review/review-handoff.md`
  Bibliographer handoff, citation audit, citation repair, and fresh audit gate.
- `completion_gate` -> `workflows/literature-review/completion-gate.md`
  Final review, sidecar, and citation-audit existence/freshness gate before returning status.
</stage_authorities>

<stage_loading_rule>
The public command includes only `workflows/literature-review/review-bootstrap.md`.
Each later stage must be reached by a staged reload:

```bash
gpd --raw init literature-review "$ARGUMENTS" --stage {stage_id}
```

Load only the active stage's `staged_loading.eager_authorities`. The first stage must not eagerly load scoped reference artifacts, child handoffs, runtime delegation, citation audit, or completion-gate authority.
</stage_loading_rule>
