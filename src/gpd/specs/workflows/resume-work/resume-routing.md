<purpose>
Detect incomplete work, present recovery status, select the next action, and update continuation only after a route is known.
</purpose>

<process>

<step name="check_incomplete_work">
Load resume-routing before deciding what work is incomplete or resumable:

```bash
RESUME_ROUTING_INIT=$(gpd --raw init resume --stage resume_routing)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd resume-routing initialization failed: $RESUME_ROUTING_INIT"
  # STOP; surface the error.
fi
```

Use `resume_routing.required_init_fields` as the routing payload.

Look for incomplete work that needs attention:

```bash
# Check for plans without summaries (incomplete execution)
for plan in GPD/phases/*/*-PLAN.md; do
  summary="${plan/PLAN/SUMMARY}"
  [ ! -f "$summary" ] && echo "Incomplete: $plan"
done 2>/dev/null

# Check for interrupted agents (use has_interrupted_agent and interrupted_agent_id from init)
if [ "$has_interrupted_agent" = "true" ]; then
  echo "Interrupted agent: $interrupted_agent_id"
fi
```

**Bounded execution segment detection:** If `active_resume_kind` is `bounded_segment`, `execution_resumable` is true, and `active_resume_pointer` is present, treat that bounded continuation as the primary resume target. The runtime ranks three recovery families into `resume_candidates`: a resumable live execution snapshot, a recorded handoff, and an interrupted-agent marker. If the live snapshot lacks a portable usable resume file, keep it visible only as advisory context. Do NOT invent additional candidates from plan files without summaries, auto-checkpoints, or other ad hoc checkpoints.

Reason-scoped clears still matter on resume: a `first_result` clear does not retire `pre_fanout` or skeptical fields, and a `fanout unlock` does not clear the review gate by itself.

When resuming from `first_result` or skeptical state, ask one concrete question first: "What decisive evidence is still owed before downstream work is trustworthy?" Do not resume fanout based only on proxy-looking success or "seems on track" prose.

**If PLAN without SUMMARY exists:**

- Execution was started but not completed
- Flag: "Found incomplete plan execution"

**If interrupted agent found and no newer bounded execution segment exists:**

- Subagent was spawned but session ended before completion
- Read agent-history.json for task details
- Flag: "Found interrupted agent"
  </step>

<step name="present_status">
Present complete research project status to user:

```
+================================================+
|  RESEARCH PROJECT STATUS                       |
+================================================+
|  Investigating:                                |
|  [one-liner from PROJECT.md "What This Is"]    |
|                                                |
|  Phase: [X] of [Y] - [Phase name]              |
|  Plan:  [A] of [B] - [Status]                  |
|  Progress: [||||||....] XX%                    |
|                                                |
|  Last activity: [date] - [what happened]       |
+================================================+

[If DERIVATION-STATE.md found:]
>> Persistent derivation history restored:
    - Equations: [X] across [N] sessions
    - Conventions: [Y] locked
    - Intermediate results: [Z] recorded
    - Approximations: [W] catalogued

[If `active_resume_kind` is `bounded_segment` and `active_bounded_segment` has a resume file:]
>> Research checkpoint detected:
    - Resume artifact: [resume_file]
    - Derivation state: [brief summary from the active execution snapshot]
    - Parameters in scope: [key parameter values]
    - Last result obtained: [most recent intermediate result]
    - Next planned step: [what was planned before pausing]

[If `continuity_handoff_file` exists and `execution_resumable` is false:]
>> Recorded handoff available:
    - Resume artifact: [continuity_handoff_file]
    - Status: recoverable recorded handoff; no resumable live execution snapshot is currently active
    - Note: this can coexist with an advisory live execution snapshot

[If `missing_continuity_handoff_file` exists:]
>> Recorded handoff artifact is missing:
    - Resume artifact: [missing_continuity_handoff_file]
    - Status: continuity metadata exists, but the recorded handoff file is missing from this workspace
    - Action: repair or recreate the handoff target before treating it as a resumable local target

[If `derived_execution_head` exists and `execution_resumable` is false:]
>> Live execution snapshot detected:
    - Status: advisory only; no bounded resume segment is currently active
    - [If `active_resume_pointer` is empty, non-project, or missing on disk:] the stored resume pointer is not portable or no longer resolves
    - Use: recover context about the last gate or paused task, but do not treat it as a resumable bounded segment

[If machine_change_detected is true:]
>> Machine change detected:
    - Last active on: [session_hostname] ([session_platform])
    - Current machine: [current_hostname] ([current_platform])
    - Action: rerun the installer if runtime-local config may be stale

[If `project_contract_gate.authoritative` is false:]
>> Contract repair required:
    - Load status: [project_contract_load_info.status]
    - Blocking detail: [first blocker or validation error]
    - Action: repair the contract/state integrity issue before planning or execution
    - Note: the structured contract stays visible for context, but it is not approved execution scope

[If `active_bounded_segment` is waiting on review:]
>> Live execution gate detected:
    - Gate: [checkpoint_reason]
    - First result ready: [yes/no]
    - Downstream fanout locked: [yes/no]
    - Review accepted but unlock still pending: [yes/no from pre_fanout_review_cleared && downstream_locked]
    - Skeptical re-questioning required: [yes/no]
    - Why the gate fired: [skeptical_requestioning_summary if present]
    - Weakest unchecked anchor: [if present]
    - Fastest disconfirming observation: [if present]

[If incomplete work found:]
>> Incomplete work detected:
    - [active execution gate or incomplete plan]

[If interrupted agent found:]
>> Interrupted agent detected:
    Agent ID: [id]
    Task: [task description from agent-history.json]
    Interrupted: [timestamp]

    Continue with: a fresh handoff built from the interrupted-agent record, or the canonical bounded segment if one has been recorded

[If pending todos exist:]
[N] pending todos -- gpd:check-todos to review

[If blockers exist:]
>> Carried concerns:
    - [blocker 1]
    - [blocker 2]

[If alignment is not checked:]
>> Brief alignment: [status] - [assessment]
```

</step>

<step name="determine_next_action">
Based on project state, determine the most logical next action:

**If partial/recoverable state or `project_contract_gate.repair_required` needs repair:**
-> Stop before planning, mutation, execution, reconstruction, or continuation update; writes none; next `gpd:sync-state`
-> Choices exactly: `gpd:sync-state`, `gpd:health`, `gpd:resume-work` after repair; exclude `gpd:progress` and `gpd:new-project`
-> This gate overrides quick-resume auto-execution; show only repair choices.

**If `project_contract_gate.authoritative` is false:**
-> Primary: Repair the blocked contract or state-integrity issue before planning or execution
-> Option: Inspect the blocked contract context and supporting diagnostics without resuming downstream work

**If `active_resume_kind="bounded_segment"` and `active_bounded_segment` exists:**
-> Primary: Continue the bounded execution segment using its current cursor, checkpoint cause, downstream-lock state, and resume preconditions
-> If `checkpoint_reason=first_result`, `checkpoint_reason=pre_fanout`, or skeptical re-questioning is required: treat the next action as a review/replan decision whenever decisive evidence is still missing, not a routine execution resume
-> Do not resume downstream fanout until the gate has an explicit clear/override outcome and, for `pre_fanout`, the matching fanout-unlock transition
-> Option: Review another ranked resume candidate from `resume_candidates`

**If `derived_execution_head` exists and `execution_resumable` is false:**
-> Primary: Treat the live snapshot as advisory continuity context only and prefer a valid recorded handoff or repair action
-> Option: Inspect the live gate state without claiming the bounded segment is directly resumable

**If interrupted agent exists:**
-> Primary: Recreate the interrupted work as a fresh handoff, or continue the canonical bounded segment when one exists
-> Option: Start fresh (abandon agent work)

**If `continuity_handoff_file` exists and `execution_resumable` is false and no interrupted agent exists:**
-> Primary: Continue from the recorded handoff in the current workspace
-> Option: Inspect any advisory live execution context without claiming a bounded segment is active

**If `missing_continuity_handoff_file` exists and no interrupted agent exists:**
-> Primary: Repair or recreate the recorded handoff artifact before treating it as a resumable local target
-> Option: Inspect advisory live execution context or other recorded recovery state without claiming a bounded segment is active

**If incomplete plan (PLAN without SUMMARY) and no higher-priority blocker is active:**
-> Primary: Complete the incomplete plan
-> Option: Abandon and move on

**If phase in progress, all plans complete:**
-> Primary: Transition to next phase
-> Option: Review completed work

**If phase ready to plan:**
-> Check if CONTEXT.md exists for this phase:

- If CONTEXT.md missing:
  -> Primary: Discuss phase vision (how user imagines the physics working out)
  -> Secondary: Plan directly (skip context gathering)
- If CONTEXT.md exists:
  -> Primary: Plan the phase
  -> Option: Review roadmap

**If phase ready to execute:**
-> Primary: Execute next plan
-> Option: Review the plan first
</step>

<step name="offer_options">
Present contextual options based on project state:

**If partial/recoverable state or `project_contract_gate.repair_required` needs repair:** keep writes none and show only `gpd:sync-state`, `gpd:health`, `gpd:resume-work` after repair.

```
What would you like to do?

[Primary action based on state - e.g.:]
1. Resume interrupted agent [if interrupted agent found]
   OR
1. Execute phase (gpd:execute-phase {phase})
   OR
1. Discuss Phase 3 context (gpd:discuss-phase 3) [if CONTEXT.md missing]
   OR
1. Plan Phase 3 (gpd:plan-phase 3) [if CONTEXT.md exists or discuss option declined]

[Secondary options:]
2. Review current phase status
3. Check pending todos ([N] pending)
4. Review brief alignment
5. Something else
```

**Note:** When offering phase planning, check for CONTEXT.md existence first:

```bash
ls GPD/phases/${current_phase_slug}/*-CONTEXT.md 2>/dev/null
```

If missing, suggest discuss-phase before plan. If exists, offer plan directly.

Wait for user selection.
</step>

<step name="route_to_workflow">
Based on user selection, route to appropriate workflow:

- **Execute plan** -> Show the exact next command after clearing:

  ```
  ---

  ## > Next Up

  **{phase}-{plan}: [Plan Name]** -- [objective from PLAN.md]

  `gpd:execute-phase {phase}`

  <sub>Start a fresh context window, then run `gpd:execute-phase {phase}`</sub>

  ---
  ```

- **Plan phase** -> Show the exact next command after clearing:

  ```
  ---

  ## > Next Up

  **Phase [N]: [Name]** -- [Goal from ROADMAP.md]

  `gpd:plan-phase [phase-number]`

  <sub>Start a fresh context window, then run `gpd:plan-phase [phase-number]`</sub>

  ---

  **Also available:**
  - `gpd:discuss-phase [N]` -- gather context first
  - `gpd:research-phase [N]` -- investigate unknowns

  ---
  ```

- **Transition** -> `{GPD_INSTALL_DIR}/workflows/transition.md`
- **Check todos** -> Read GPD/todos/pending/, present summary
- **Review alignment** -> Read PROJECT.md, compare to current state
- **Something else** -> Ask what they need
  </step>

<step name="update_continuation">
Refresh canonical continuation only after the selected route, phase, and handoff file are known. Do not write a generic resume marker just because this workflow was opened.

Template only - do not run as-is:

```text
gpd state record-session \
  --stopped-at "<actual selected route and phase>" \
  --resume-file "<actual project-relative handoff path>"

gpd state record-session \
  --stopped-at "<actual selected route; pointer intentionally cleared>" \
  --resume-file none
```

Use the second form only when the selected route intentionally clears the pointer. Never copy placeholder phase numbers, prose, or file paths into state.
STATE.md should render the authoritative continuation update.
</step>

</process>

<reconstruction>
If STATE.md is missing but other artifacts exist and `planning_exists` is true:

"STATE.md missing. Reconstructing from artifacts..."

1. Read PROJECT.md -> Extract "What This Is" and Core Research Question
2. Read ROADMAP.md -> Determine phases, find current position
3. Scan \*-SUMMARY.md files -> Extract decisions, concerns
4. Count pending todos in GPD/todos/pending/
5. Check current execution snapshot -> Session continuity

Reconstruct and write STATE.md, then proceed normally.

If `planning_exists` is false:
- If recoverable state exists, repair recoverable state first, then run reconstruction.
- If state is not recoverable, skip reconstruction and route to `gpd:new-project`.

This handles cases where:

- Project predates STATE.md introduction
- File was accidentally deleted
- Cloning repo without full GPD/ state
  </reconstruction>

<quick_resume>
If user says "continue" or "go":

- If `project_root_auto_selected` is true or `project_root_source="recent_project"`, quick resume is disabled; show the project path, require explicit confirmation or reopened folder, and do not continue automatically.
- If partial/recoverable state or `project_contract_gate.repair_required` needs repair, quick resume must not auto-execute; show only repair choices.
- Load state silently
- Determine primary action
- Execute immediately without presenting options

"Continuing from [state]... [action]"
</quick_resume>

<success_criteria>
Resume is complete when:

- [ ] STATE.md loaded or reconstructed
- [ ] DERIVATION-STATE.md read, cap-checked, cross-referenced with state.json, and summarized when present
- [ ] Gaps, incomplete work, and restored research context surfaced
- [ ] Clear status and contextual next actions presented
- [ ] User knows where the project stands
- [ ] Session continuity updated
</success_criteria>
