<purpose>
Compatibility index for the staged `new-project` workflow.
</purpose>

@{GPD_INSTALL_DIR}/references/shared/interactive-choice-fallback.md

<runtime_labels>
Runtime label: Show `gpd:` as native labels; keep local CLI `gpd ...` unchanged.
</runtime_labels>

<stage_authorities>
The active authority is selected by `new-project-stage-manifest.json`.
Do not load this index as a stage authority.

- `scope_intake` -> `workflows/new-project/scope-intake.md`
  Startup routing, existing-work/recovery checks, and the first scoping intake boundary.
- `scope_approval` -> `workflows/new-project/scope-approval.md`
  Scoping contract authoring, explicit approval, validation, and approval-state persistence.
- `minimal_artifacts` -> `workflows/new-project/minimal-artifacts.md`
  Minimal-mode core artifact generation after approved scope persistence.
- `workflow_preferences` -> `workflows/new-project/workflow-preferences.md`
  Full/auto-mode workflow preference selection before project artifact authoring.
- `project_artifacts` -> `workflows/new-project/project-artifacts.md`
  Full/auto-mode project context artifact authoring.
- `literature_survey` -> `workflows/new-project/literature-survey.md`
  Literature survey selection, scout/synthesis handoff, or explicit skip before requirements.
- `requirements_authoring` -> `workflows/new-project/requirements-authoring.md`
  Requirements artifact authoring from the approved scope and available context.
- `roadmap_authoring` -> `workflows/new-project/roadmap-authoring.md`
  Roadmap handoff and roadmap/state artifact updates after requirements.
- `conventions_handoff` -> `workflows/new-project/conventions-handoff.md`
  Notation and convention handoff after roadmap completion.
- `completion` -> `workflows/new-project/completion.md`
  Final cleanup and next-step display.
</stage_authorities>

<stage_loading_rule>
The public command includes only `workflows/new-project/scope-intake.md`.
Each later stage must be reached by a staged reload:

```bash
gpd --raw init new-project --stage {stage_id}
```

Load only the active stage's `staged_loading.eager_authorities`. This index is
only a compatibility map and must not be used as executable workflow authority.
</stage_loading_rule>

<routing_summary>
`scope_approval` routes to `minimal_artifacts` for `--minimal` and to
`workflow_preferences` for full or `--auto` mode. The full/auto route then
continues through project artifacts, literature survey, requirements, roadmap,
conventions, and completion. The minimal route goes directly from
`minimal_artifacts` to `completion`.
</routing_summary>
