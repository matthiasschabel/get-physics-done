<trigger>
Use this workflow when:
- Starting a new session on an existing research project
- User says "continue", "what's next", "where were we", "resume"
- Any planning operation when GPD/ already exists
- User returns after time away from project
</trigger>

<purpose>
Restore selected project context so "Where were we?" has an immediate answer.

@{GPD_INSTALL_DIR}/references/orchestration/resume-vocabulary.md
</purpose>

<required_reading>
Bootstrap loads only immediate resume vocabulary. Later staged payloads name
`{GPD_INSTALL_DIR}/references/orchestration/continuation-format.md`,
`{GPD_INSTALL_DIR}/references/orchestration/state-portability.md`, and
`{GPD_INSTALL_DIR}/templates/state-json-schema.md`; read them when entering those stages.
</required_reading>

<process>

Runtime label: Show `gpd:` as native labels; keep local CLI `gpd ...` unchanged.

<step name="initialize">
Load resume bootstrap. `gpd:resume-work` is the guided runtime path; `gpd resume` is the public local read-only summary; `gpd resume --recent` is the cross-project discovery surface; `gpd --raw resume` is raw local JSON:

```bash
INIT=$(gpd --raw init resume --stage resume_bootstrap)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $INIT"
  # STOP; surface the error.
fi
```

Parse JSON semantically:

- **Requested workspace availability:** `workspace_state_exists`, `workspace_roadmap_exists`, `workspace_project_exists`, `workspace_planning_exists`
- **Selected project availability:** `state_exists`, `state_json_backup_exists`, `roadmap_exists`, `project_exists`, `planning_exists`
- **Availability and contract authority:** `project_contract_gate` and peers are loaded by `STATE_RESTORE_INIT` before use
- **Canonical continuation and recovery authority:** `resume_surface_schema_version`, `active_resume_kind`, `active_resume_origin`, `active_resume_pointer`, `active_bounded_segment`, `derived_execution_head`, `active_resume_result`, `continuity_handoff_file`, `recorded_continuity_handoff_file`, `missing_continuity_handoff_file`, `has_continuity_handoff`, `resume_candidates`, `execution_resumable`, `execution_paused_at`, `execution_review_pending`, `execution_pre_fanout_review_pending`, `execution_skeptical_requestioning_required`, `execution_downstream_locked`, `has_interrupted_agent`, `interrupted_agent_id`
- **Machine advisory state:** `machine_change_detected`, `machine_change_notice`, `current_hostname`, `current_platform`, `session_hostname`, `session_platform`

@{GPD_INSTALL_DIR}/references/orchestration/resume-vocabulary.md

The recent-project list is advisory and machine-local; once you choose a workspace, `gpd:resume-work` reloads that project's canonical state.

**If `project_reentry_requires_selection` is true or `project_reentry_mode="ambiguous-recent-projects"`:** Stop before new-project routing or reconstruction. Show the recent-project count; tell the user to run `gpd resume --recent`, open the chosen workspace, and rerun `gpd:resume-work`.

**If `project_root_auto_selected` is true or `project_root_source="recent_project"`:** Runtime started outside the selected project. Do not quick-resume or act from the unrelated workspace. On bare "continue" or "go", stop. Show `project_root`; require explicit confirmation or a reopened project folder.

When present, use `active_resume_result` as hydrated result context. Use its `id` as anchor, but summarize structured fields rather than only the raw identifier.

`workspace_state_exists` / `state_exists` mean usable state from `GPD/state.json` or `GPD/STATE.md`; `GPD/state.json.bak` is only crash-recovery support. A stray unreadable path is not recoverable state.
Use `workspace_*` to judge the user-requested workspace before auto-selection; use the selected-project fields after re-entry resolution.

Resolver authority order: `GPD/state.json` / `continuation`, then `GPD/state.json.bak`, then `GPD/STATE.md`; `.continue-here.md` and live snapshots are context, not sole authority.

**If `planning_exists` is false and no recent-project selection is required:** If recoverable state exists, repair first. Otherwise route to gpd:new-project and do not attempt STATE.md reconstruction.
**If `state_exists` is false but `roadmap_exists` or `project_exists` is true:** Offer to reconstruct STATE.md from the existing project artifacts.

If `active_resume_kind="bounded_segment"` and `active_bounded_segment` exists, treat that as the primary bounded resume target. The derived execution head may still project the bounded segment when canonical continuation is missing or incomplete, but it does not define a second resume system.

`active_resume_kind` is narrower than the overall recovery status. A recorded handoff, a missing recorded handoff artifact, or advisory live execution can still exist when `active_resume_kind` is `None`; those status cues surface through `continuity_handoff_file` and `missing_continuity_handoff_file`, while `gpd --raw resume` keeps the top-level public fields canonical.

Surface `active_resume_result` beside the primary target. If a candidate has hydrated `last_result`, prefer it over `last_result_id`-only notes while preserving the ID as rerun anchor.

If `derived_execution_head` exists but `execution_resumable` is false, treat that live snapshot as advisory context only. If `active_resume_pointer` is empty, non-project, or missing on disk, call that out explicitly; in all such cases it is not a ranked bounded-segment resume candidate and does not justify `active_resume_kind="bounded_segment"`.

If `active_bounded_segment.pre_fanout_review_pending` is true, the gate is still live even when a resume file exists. If `active_bounded_segment.pre_fanout_review_cleared` is true, the review outcome was recorded but the separate fanout unlock is still missing.

If `active_bounded_segment.first_result_gate_pending` is true, do not treat later routine work or a resume artifact as proof that the first-result gate passed. Resume must still verify whether decisive evidence was actually produced or explicitly waived.
</step>

</process>
