<purpose>
Compatibility index for the staged `quick` workflow.
</purpose>

<stage_authority_index>
The active authority is selected by `quick-stage-manifest.json`. Do not load this index as a stage authority.

- `task_bootstrap` -> `workflows/quick/task-bootstrap.md`
  Freeform quick-task intake, staged bootstrap init, project/workspace gates, reroute rules, and quick directory creation. The bootstrap authority asks: `Ask ONE question inline (freeform, NOT ask_user):`; there are no fixed option labels to preserve.
- `task_authoring` -> `workflows/quick/task-authoring.md`
  Default small-task planner handoff, plan artifact gate, executor handoff, child-return application, durable state update, and commit.
- `reference_context` -> `workflows/quick/task-authoring.md`
  Same authoring authority with the selected reference-runtime payload enabled only when the task needs active project anchors, reference artifacts, literature/research-map files, or targeted source lookup.
</stage_authority_index>

<stage_loading_rule>
The public command includes only `workflows/quick/task-bootstrap.md`. Later stages are reached with staged reloads:

```bash
gpd --raw init quick "$DESCRIPTION" --stage task_authoring
gpd --raw init quick "$DESCRIPTION" --stage reference_context
```

Load only the active stage's `staged_loading.eager_authorities`; never read `staged_loading.must_not_eager_load` or the root workflow index as active authority.
</stage_loading_rule>

<canonical_references>
- `references/quick/quick-mode-boundary.md`
- `references/quick/quick-durability-minimum.md`
- `references/quick/quick-reroute-rules.md`
- `references/orchestration/runtime-delegation-note.md`
- `references/orchestration/child-artifact-gate.md`
- `references/orchestration/continuation-boundary.md`
</canonical_references>
