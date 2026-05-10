<purpose>
Create the milestone roadmap through the roadmapper handoff and final artifact gate.
</purpose>

<process>

## 9. Create Roadmap

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 GPD >>> CREATING RESEARCH ROADMAP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

>>> Spawning roadmapper...
```

**Starting phase number:** Read MILESTONES.md for last phase number. Continue from there (v1.0 ended at phase 5 -> v1.1 starts at phase 6).

**Roadmap handoff staging:** run a fresh late-stage init immediately before the roadmapper handoff and treat it as the source of truth for roadmap assembly.

```bash
ROADMAPPER_INIT=$(gpd --raw init new-milestone --stage roadmap_authoring)
if [ $? -ne 0 ]; then
  echo "ERROR: roadmap init failed: $ROADMAPPER_INIT"
  exit 1
fi
```

Use `gpd --raw stage field-access new-milestone --stage roadmap_authoring --style instruction` to confirm the manifest-selected roadmapping fields. Read only those keys from `ROADMAPPER_INIT`; `ROADMAPPER_INIT.staged_loading.required_init_fields` is the runtime confirmation.

Use the bootstrap init for milestone identity and contract gating. Use this late-stage init for the final handoff and do not reuse earlier roadmapping inputs from the survey/objective loop.

Apply the canonical runtime delegation convention already loaded above.

```
task(prompt="First, read {GPD_AGENTS_DIR}/gpd-roadmapper.md for your role and instructions.

<files_to_read>
Read these files using the file_read tool before proceeding:
- GPD/PROJECT.md
- GPD/state.json
- GPD/config.json
- GPD/MILESTONES.md (if exists, skip if not found)
- GPD/REQUIREMENTS.md
- GPD/literature/SUMMARY.md (if exists, skip if not found)
- Files named in `effective_reference_intake.must_include_prior_outputs` when they exist
- Files named in `reference_artifact_files` when they exist and are relevant to anchor coverage
</files_to_read>

<milestone_context>
Current milestone: {current_milestone}
Milestone name: {current_milestone_name}
Project content: {project_content}
State content: {state_content}
Milestones content: {milestones_content}
Requirements content: {requirements_content}
Roadmap content: {roadmap_content}
Reference artifacts: {reference_artifacts_content}
</milestone_context>

<contract_context>
Project contract: {project_contract}
Project contract gate: {project_contract_gate}
Project contract validation: {project_contract_validation}
Project contract load info: {project_contract_load_info}
Contract intake: {contract_intake}
Active references: {active_reference_context}
Effective reference intake: {effective_reference_intake}
Reference artifacts: {reference_artifacts_content}
</contract_context>

<shallow_mode>false</shallow_mode>
<!-- Milestones keep the full-detail roadmap so scoped continuations inherit every phase's contract coverage and success criteria up front. -->

<continuation_context>
This is a fresh continuation handoff for the current milestone roadmap. Carry forward the approved objectives, requirement traceability, prior survey findings, and any unresolved context gaps. Edit the existing roadmap files in place and return the roadmapper `gpd_return` profile.
</continuation_context>

<instructions>
Create research roadmap for milestone v[X.Y]:
1. Start phase numbering from [N]
2. Derive phases from THIS MILESTONE's objectives, the approved project contract only when `project_contract_gate.authoritative` is true, and the effective reference intake
3. Map every objective to exactly one phase
4. For each phase, include explicit contract coverage in ROADMAP.md showing decisive contract items, anchor coverage, required prior outputs, and forbidden proxies advanced by that phase
5. Treat `must_read_refs`, `must_include_prior_outputs`, `user_asserted_anchors`, `known_good_baselines`, and `crucial_inputs` as binding milestone context, and surface unresolved `context_gaps`
6. Derive 2-5 success criteria per phase (concrete, verifiable results)
7. Validate 100% objective coverage and surface all contract-critical items touched by this milestone
8. Write files immediately (ROADMAP.md and REQUIREMENTS.md traceability). Do not write STATE.md directly; return any proposed state status, position, or decision-log update for the orchestrator to apply with `gpd state` commands after the artifact gate.
9. Return the roadmapper `gpd_return` profile; completed local artifacts are `GPD/ROADMAP.md` and `GPD/REQUIREMENTS.md`.
10. If blocked, checkpointed, or failed, return the typed status with concrete issues and next actions; the parent gate below owns retry, freshness, display, and commit routing.

</instructions>
", subagent_type="gpd-roadmapper", model="{roadmapper_model}", readonly=false, description="Create research roadmap")
```

Add this contract inside the spawned roadmapper prompt when adapting it:

```markdown
<spawn_contract>
write_scope:
  mode: scoped_write
  allowed_paths:
    - GPD/ROADMAP.md
    - GPD/REQUIREMENTS.md
expected_artifacts:
  - GPD/ROADMAP.md
  - GPD/REQUIREMENTS.md
shared_state_policy: return_only
</spawn_contract>
```

This roadmapper contract is task-local. Do not widen the write scope or reuse it outside this handoff. The roadmapper does not own shared state; apply any accepted STATE.md updates in the main workflow with `gpd state` commands only after the roadmap artifacts pass the freshness gate.

**Roadmapper child gate:**

```yaml
child_gate:
  id: "milestone_roadmapper"
  role: "gpd-roadmapper"
  return_profile: "roadmapper"
  required_status: "completed"
  expected_artifacts:
    - "GPD/ROADMAP.md"
    - "GPD/REQUIREMENTS.md"
  allowed_roots:
    - "GPD"
  freshness_marker: "after $MILESTONE_ROADMAPPER_HANDOFF_STARTED_AT"
  validators:
    - "gpd validate handoff-artifacts - --expected GPD/ROADMAP.md --expected GPD/REQUIREMENTS.md --allowed-root GPD --require-status completed --require-files-written --fresh-after \"$MILESTONE_ROADMAPPER_HANDOFF_STARTED_AT\""
    - "readable ROADMAP.md / REQUIREMENTS.md"
  applicator:
    command: "main workflow applies accepted state changes with gpd state patch / gpd state add-decision after the artifact gate"
    require_passed_true: false
  failure_route: "ask retry or stop | repair prompt once | stop roadmapper path | request fresh continuation | repair path once | fail closed | ..."
```

Route `checkpoint` -> fresh roadmapper continuation, `blocked` -> resolve then
fresh continuation, `failed` -> ask retry or stop; Next Up primary
`gpd:new-milestone [milestone name]`, also `gpd:suggest-next`. Only after the
artifact gate passes, apply accepted state changes in the main workflow with
`gpd state patch` / `gpd state add-decision`; a direct roadmapper edit to
`GPD/STATE.md` is not success proof.

**If `gpd_return.status: completed`:** Read ROADMAP.md only after the fresh file proof is satisfied, then present the roadmap inline:

```
## Proposed Research Roadmap

**[N] phases** | **[X] objectives mapped** | Contract coverage surfaced

| # | Phase | Goal | Objectives | Contract Coverage | Success Criteria |
|---|-------|------|------------|-------------------|------------------|
| [N] | [Name] | [Goal] | [REQ-IDs] | [claims / anchors] | [count] |

### Phase Details

**Phase [N]: [Name]**
Goal: [goal]
Objectives: [REQ-IDs]
Contract coverage: [decisive outputs, anchors, forbidden proxies]
Success criteria:
1. [criterion]
2. [criterion]
```

**Ask for approval** via ask_user:

- "Approve" — Commit and continue
- "Adjust phases" — Tell me what to change
- "Review full file" — Show raw ROADMAP.md

**If "Adjust":** Get notes, then respawn the roadmapper with a revision continuation handoff:

Apply the canonical runtime delegation convention already loaded above.

  ```
  task(prompt="First, read {GPD_AGENTS_DIR}/gpd-roadmapper.md for your role and instructions.

  <continuation>
  This is a continuation of the current roadmap handoff, not a fresh brainstorm.

  User feedback on roadmap:
  [user's notes]

  Current artifact snapshot:
  - GPD/ROADMAP.md
  - GPD/STATE.md
  - GPD/REQUIREMENTS.md

  Read the existing roadmap and requirements before editing.
  Edit files in place.
  Return a fresh typed `gpd_return` envelope with `status` and `files_written`.
  </continuation>

  <shallow_mode>false</shallow_mode>
  <!-- Milestones keep the full-detail roadmap so scoped continuations inherit every phase's contract coverage and success criteria up front. -->
  ", subagent_type="gpd-roadmapper", model="{roadmapper_model}", readonly=false, description="Revise roadmap")
  ```

  **If the revision roadmapper agent fails to spawn or returns an error:** Treat the revision as incomplete. Do not compare old file contents as proof of success. Ask whether to retry the same continuation once or stop. If retrying, use a fresh continuation handoff that includes the current roadmap, requirements, and user notes.

- Present revised roadmap
- Loop until user approves (**maximum 3 revision iterations** - after 3, commit the current version with user's notes recorded as open questions in ROADMAP.md, and note: "Roadmap committed after 3 revision rounds. Further adjustments via `gpd:add-phase` or `gpd:remove-phase`.")

**If "Review full file":** Display raw `cat GPD/ROADMAP.md`, then re-ask.

**Commit roadmap** (after approval or auto mode):

```bash
PRE_CHECK=$(gpd pre-commit-check --files GPD/ROADMAP.md GPD/STATE.md GPD/REQUIREMENTS.md 2>&1) || true
echo "$PRE_CHECK"

gpd commit "docs: create milestone v[X.Y] roadmap ([N] phases)" --files GPD/ROADMAP.md GPD/STATE.md GPD/REQUIREMENTS.md
```

## 10. Done

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 GPD >>> MILESTONE INITIALIZED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Milestone v[X.Y]: [Name]**

| Artifact       | Location                    |
|----------------|-----------------------------|
| Project        | `GPD/PROJECT.md`      |
| Literature     | `GPD/literature/`     |
| Objectives     | `GPD/REQUIREMENTS.md`   |
| Roadmap        | `GPD/ROADMAP.md`      |

**[N] phases** | **[X] objectives** | Ready to investigate

## > Next Up

**Phase [N]: [Phase Name]** — [Goal]

`gpd:discuss-phase [N]`

<sub>Start a fresh context window, then run `gpd:discuss-phase [N]`.</sub>

---

**Also available:**
- `gpd:plan-phase [N]` — skip discussion and plan directly
- `gpd:suggest-next` — confirm the next action
```
</process>

<success_criteria>

- [ ] PROJECT.md updated with Current Milestone section
- [ ] STATE.md reset for new milestone
- [ ] MILESTONE-CONTEXT.md consumed and deleted (if existed)
- [ ] Literature survey completed (if selected) — 4 parallel agents, milestone-aware
- [ ] Objectives gathered and scoped per category
- [ ] REQUIREMENTS.md created with REQ-IDs
- [ ] gpd-roadmapper spawned with staged continuation context
- [ ] Roadmap files written immediately (not draft)
- [ ] User feedback incorporated (if any)
- [ ] ROADMAP.md phases continue from previous milestone
- [ ] All commits made (if planning docs committed)
- [ ] User knows next step: `gpd:discuss-phase [N]`

**Atomic commits:** Each phase commits its artifacts immediately.
</success_criteria>
