<purpose>
Execute small, ad-hoc physics tasks with GPD guarantees while skipping optional agents. Quick mode routes through the canonical planner handoff, loads staged quick init at the task-bootstrap and default task-authoring boundaries, selects the separate `reference_context` stage only when a task actually needs project reference artifacts, tracks `GPD/quick/`, and records structured completion. Tasks: derivation, dimensional/OOM check, limit, DOI. Quick mode is NOT authorized to close theorem-style or `proof_obligation` work.
</purpose>

<required_reading>
Read all files referenced by the invoking prompt's execution_context before starting.
</required_reading>

<quick_authorities>
@{GPD_INSTALL_DIR}/references/quick/quick-mode-boundary.md
@{GPD_INSTALL_DIR}/references/quick/quick-durability-minimum.md
@{GPD_INSTALL_DIR}/references/quick/quick-reroute-rules.md
</quick_authorities>

<process>
**Step 1: Get task description**

Ask for the task description as a single freeform prompt. Do not use the shared structured-choice fallback here; there are no fixed option labels to preserve.

Ask ONE question inline (freeform, NOT ask_user):

```text
What quick task do you want to do? Examples:
  - Quick derivation of the equation of motion from the Lagrangian
  - Dimensional check on the cross-section formula in eq. (3.14)
  - Order-of-magnitude estimate for the tunneling rate
  - Verify the non-relativistic limiting case of the dispersion relation
  - Look up the DOI for a specific bibliography item
```

Store response as `$DESCRIPTION`.

If empty, re-prompt: "Please provide a task description."

---

**Step 2: Initialize**

```bash
TASK_BOOTSTRAP_INIT=$(gpd --raw init quick "$DESCRIPTION" --stage task_bootstrap)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $TASK_BOOTSTRAP_INIT"
  # STOP; surface the error.
fi
INIT="$TASK_BOOTSTRAP_INIT"
```

Use `gpd --raw stage field-access quick --stage task_bootstrap --style instruction` to confirm the manifest-selected bootstrap fields. Read only those keys from `TASK_BOOTSTRAP_INIT`; `TASK_BOOTSTRAP_INIT.staged_loading.required_init_fields` is the runtime confirmation.

The bootstrap and default `task_authoring` payloads intentionally do not include the staged reference-runtime payload. Before the planner handoff, reload either:

- `task_authoring` for the default small-task path.
- `reference_context` only when the quick-mode boundary rules say the task really needs active project references, reference artifacts, literature/research-map files, or a targeted source lookup.

Treat the selected staged init payload's `staged_loading` block as authoritative for the planner handoff shape rather than reconstructing a separate quick-specific prompt contract.

**Mode-aware behavior:**
- `autonomy=supervised` (default): Pause after the plan for user approval before execution.
- `autonomy=balanced`: Execute without pausing unless the quick task reveals a real decision point.
- `autonomy=yolo`: Execute and commit without pausing.

**If `project_exists` is false:** Error -- Quick mode requires an initialized project with `GPD/PROJECT.md`. Run `gpd:new-project` first.

**If `planning_exists` is false:** Error -- Quick mode requires the `GPD/` workspace directory. Run `gpd:new-project` first.

Quick tasks can run mid-phase and do NOT require ROADMAP.md. They still require an initialized project workspace with `GPD/PROJECT.md` and the `GPD/` directory.
Quick mode still inherits the approved `project_contract` only when `project_contract_gate.authoritative` is true. The default small-task path does not load the full active reference ledger; select `reference_context` only when the task needs that ledger. Do not bypass required anchors, baselines, or forbidden-proxy constraints just because the task is small.

**Reroute block:** Apply `quick-reroute-rules.md`. If the description or inherited contract indicates theorem-style, proof-bearing, publication-grade, referee-response, manuscript proof-review, or claim-adjudication work, STOP instead of using quick mode. A generic manuscript or task "claim" is not enough by itself, but a formal proof target or `proof_obligation` is enough. Do not bypass this by asking for a "quick sketch", "light proof", or "just the main idea". Route explicitly to:

- `gpd:plan-phase <phase>` when this belongs in planned phase work
- `gpd:derive-equation "<goal>"` when you need a derivation/proof draft
- `gpd:verify-work <phase>` only after a canonical proof-redteam artifact exists

---

**Step 3: Create task directory**

Use `task_dir` from init JSON (for example, `GPD/quick/NNN-slug/`):

```bash
QUICK_DIR="${task_dir}"
mkdir -p "$QUICK_DIR"
```

Report to user:

```
Creating quick task ${next_num}: ${DESCRIPTION}
Directory: ${QUICK_DIR}
```

---

**Step 4: Spawn planner (quick mode)**

Choose the staged authoring payload before assembling the quick planner prompt:

- Default to `task_authoring` for local calculations, dimensional checks, unit conversions, one-file numerical spot-checks, formatting, and other self-contained small tasks.
- Use `reference_context` only for targeted source lookup or tasks whose answer depends on active project anchors, existing reference artifacts, literature/research-map files, or protocol/reference context.

Set `NEEDS_REFERENCE_CONTEXT` to `true` only for the second case; otherwise set it to `false`.

```bash
if [ "$NEEDS_REFERENCE_CONTEXT" = "true" ]; then
  TASK_AUTHORING_INIT=$(gpd --raw init quick "$DESCRIPTION" --stage reference_context)
else
  TASK_AUTHORING_INIT=$(gpd --raw init quick "$DESCRIPTION" --stage task_authoring)
fi
if [ $? -ne 0 ]; then
  echo "ERROR: gpd quick task-authoring init failed: $TASK_AUTHORING_INIT"
  # STOP; surface the error.
fi
INIT="$TASK_AUTHORING_INIT"
```

`NEEDS_REFERENCE_CONTEXT` must be false by default. Do not set it just because `project_contract_gate` exists; contract-gate fields are already present in the default small-task payload.

Use `gpd --raw stage field-access quick --stage task_authoring --style instruction`, or `gpd --raw stage field-access quick --stage reference_context --style instruction` when `NEEDS_REFERENCE_CONTEXT=true`. Read only staged-loading fields.

Spawn gpd-planner with the quick-mode context:

@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md

> Apply the canonical runtime delegation convention already loaded above.

```
task(
  prompt="First, read {GPD_AGENTS_DIR}/gpd-planner.md for your role and instructions.

<planning_context>

**Mode:** quick
**Directory:** ${QUICK_DIR}
**Description:** ${DESCRIPTION}

**Project State:**
Read the file at GPD/STATE.md

**Project Exists:** {project_exists}

**Project Contract:** {project_contract}
**Project Contract Gate:** {project_contract_gate}
**Project Contract Load Info:** {project_contract_load_info}
**Project Contract Validation:** {project_contract_validation}

**Default Reference Runtime:** not loaded for `task_authoring`.

If `TASK_AUTHORING_INIT.staged_loading.stage_id` is `reference_context`, append this selected reference payload:
**Contract Intake:** {contract_intake}
**Effective Reference Intake:** {effective_reference_intake}
**Active References:** {active_reference_context}
**Reference Artifacts:** {reference_artifacts_content}
<protocol_bundle_handoff>
<selected_protocol_bundle_ids>{selected_protocol_bundle_ids}</selected_protocol_bundle_ids>
<protocol_bundle_load_manifest>{protocol_bundle_load_manifest}</protocol_bundle_load_manifest>
<protocol_bundle_context>{protocol_bundle_context}</protocol_bundle_context>
<protocol_bundle_verifier_extensions>{protocol_bundle_verifier_extensions}</protocol_bundle_verifier_extensions>
</protocol_bundle_handoff>

</planning_context>

<constraints>
- Create a SINGLE plan with 1-3 focused tasks
- Quick tasks should be atomic and self-contained
- No literature review phase, no checker phase
- Use the `staged_loading` fields from `TASK_AUTHORING_INIT` as the source of truth for the handoff instead of inventing a separate quick-only contract
- If `staged_loading.stage_id` is `task_authoring`, do not invent reference-runtime, protocol, literature/research-map, proof-review, or publication context that is not present in `TASK_AUTHORING_INIT.staged_loading.required_init_fields`.
- If `project_contract_load_info.status` starts with `blocked` or `project_contract_validation.valid` is false, return `gpd_return.status: checkpoint` instead of drafting a plan from guessed scope.
- If the task is theorem-style or proof-bearing, return `gpd_return.status: checkpoint` and tell the user quick mode is blocked pending the full proof-redteam workflow.
- Proof-obligation command block: theorem-style, lemma/corollary/proposition, or explicit `proof_obligation` work must route to the full proof-redteam workflow.
- ProjectContract `claim_kind: claim` is not proof-bearing by itself. A generic manuscript or task "claim" is not enough by itself. Require theorem/proof/formal metadata before routing generic manuscript claims through proof-redteam.
- Target ~30% context usage (simple, focused)
</constraints>

<output>
Write plan to: ${QUICK_DIR}/${next_num}-PLAN.md
Return a structured `gpd_return` envelope. Local completed output is `${QUICK_DIR}/${next_num}-PLAN.md` named in `gpd_return.files_written`; use checkpoint when user input or a contract block prevents drafting.
</output>
",
  subagent_type="gpd-planner",
  model="{planner_model}",
  readonly=false,
  description="Quick plan: ${DESCRIPTION}"
)
```

Child artifact gate: apply `references/orchestration/child-artifact-gate.md`; tuple: role=`gpd-planner`; expected=`${QUICK_DIR}/${next_num}-PLAN.md`; allowed_root=`${QUICK_DIR}`; validators=`gpd validate plan-preflight` when the plan declares `tool_requirements`; applicator=none before execution; failure=`retry planner | explicit main-context fallback with its own return | abort`.

**If the planner agent fails to spawn or returns an error:** Keep the handoff incomplete under the gate above. A plan file at `${QUICK_DIR}/${next_num}-PLAN.md` is recovery evidence only; require a valid planner `gpd_return` naming that plan, or run explicit main-context fallback with its own return. Offer: 1) Retry planner, 2) Create the plan in the main context, 3) Abort.

After planner returns:

1. Apply the planner gate tuple above: completed requires a fresh readable `${QUICK_DIR}/${next_num}-PLAN.md` named in `gpd_return.files_written`.
2. For checkpoint, present the checkpoint and continue only through a fresh continuation handoff under `references/orchestration/continuation-boundary.md`.
3. For blocked or failed, offer retry, main-context planning, or abort.
4. Extract plan count (typically 1 for quick tasks).
5. Report: "Plan created: ${QUICK_DIR}/${next_num}-PLAN.md"

If the plan file is missing, unreadable, stale, or absent from `gpd_return.files_written`, error: "Planner failed to create ${next_num}-PLAN.md"

If the plan declares specialized `tool_requirements`, run `gpd validate plan-preflight <PLAN.md>` before spawning the executor:

```bash
PLAN_TOOL_REQUIREMENTS=$(gpd frontmatter get "${QUICK_DIR}/${next_num}-PLAN.md" --field tool_requirements 2>/dev/null || true)
if [ -n "$PLAN_TOOL_REQUIREMENTS" ]; then
  PLAN_PREFLIGHT=$(gpd --raw validate plan-preflight "${QUICK_DIR}/${next_num}-PLAN.md")
  if [ $? -ne 0 ]; then
    echo "ERROR: plan-preflight failed: $PLAN_PREFLIGHT"
    # STOP; surface the error.
  fi
fi
```

---

**Step 5: Spawn executor**

Spawn gpd-executor with plan reference:
Apply the canonical runtime delegation convention already loaded above.

```
task(
  prompt="First, read {GPD_AGENTS_DIR}/gpd-executor.md for your role and instructions.

Execute quick task ${next_num}.

Plan: Read the file at ${QUICK_DIR}/${next_num}-PLAN.md
Project state: Read the file at GPD/STATE.md
Project contract: {project_contract}
Project contract gate: {project_contract_gate}
Project contract load info: {project_contract_load_info}
Project contract validation: {project_contract_validation}

Reference runtime: not loaded for default `task_authoring`.

If the selected planner stage was `reference_context`, pass through the selected reference payload:
Contract intake: {contract_intake}
Effective reference intake: {effective_reference_intake}
Active references: {active_reference_context}
Reference artifacts: {reference_artifacts_content}
<protocol_bundle_handoff>
<selected_protocol_bundle_ids>{selected_protocol_bundle_ids}</selected_protocol_bundle_ids>
<protocol_bundle_load_manifest>{protocol_bundle_load_manifest}</protocol_bundle_load_manifest>
<protocol_bundle_context>{protocol_bundle_context}</protocol_bundle_context>
<protocol_bundle_verifier_extensions>{protocol_bundle_verifier_extensions}</protocol_bundle_verifier_extensions>
</protocol_bundle_handoff>

<constraints>
- Execute all tasks in the plan
- Commit each task atomically
- Create summary at: ${QUICK_DIR}/${next_num}-SUMMARY.md
- Do NOT update ROADMAP.md (quick tasks are separate from planned phases)
- Do not invent reference artifacts or publication/proof-review context when the selected planner stage was the default `task_authoring`.
- If proof-bearing work slipped through planning, STOP and return the reroute instead of executing. Quick mode must not produce a proof result without the mandatory proof-redteam gate.
- Return a structured `gpd_return` envelope with `gpd_return.status` and `gpd_return.files_written`; local completed output is `${QUICK_DIR}/${next_num}-SUMMARY.md`.
</constraints>
",
  subagent_type="gpd-executor",
  model="{executor_model}",
  readonly=false,
  description="Execute: ${DESCRIPTION}"
)
```

Child artifact gate: apply `references/orchestration/child-artifact-gate.md`; tuple: role=`gpd-executor`; expected=`${QUICK_DIR}/${next_num}-SUMMARY.md`; allowed_root=`${QUICK_DIR}`; validators=readable summary; applicator=`gpd apply-return-updates "${QUICK_DIR}/${next_num}-SUMMARY.md"`; failure=`retry executor | explicit main-context fallback with its own return | abort`.

**If the executor agent fails to spawn or returns an error:** Check `git log --oneline -3` only for partial evidence. Commits or files do not prove success without the local child artifact gate above. Offer: 1) Retry executor, 2) Execute in explicit main-context fallback with its own return, 3) Abort.

After executor returns:

1. Verify summary exists at `${QUICK_DIR}/${next_num}-SUMMARY.md`
2. Extract commit hash from executor output
3. Report completion status

> **Handoff verification:** Apply the executor child artifact gate before success; git commits are partial evidence only.

If summary not found, error: "Executor failed to create ${next_num}-SUMMARY.md"

Note: For quick tasks producing multiple plans (rare), spawn executors in parallel waves per execute-phase patterns.

---

**Step 6: Apply child-return effects**

Treat the executor summary as the canonical child-return artifact. Before any direct quick-task state updates, validate and apply its durable subset through the shared command path:

```bash
APPLY_RETURN=$(gpd apply-return-updates "${QUICK_DIR}/${next_num}-SUMMARY.md")
if [ $? -ne 0 ]; then
  echo "ERROR: apply-return-updates failed: $APPLY_RETURN"
  # STOP — show the structured errors and do not proceed.
fi
```

Apply `references/orchestration/child-artifact-gate.md` and `references/orchestration/continuation-boundary.md`: completed means the summary gate and applicator passed; checkpoint means present the checkpoint and spawn a fresh continuation; blocked or failed means surface issues and retry or handle manually.

Only proceed to the quick-task completion record after `apply-return-updates` succeeds and the summary file still exists on disk.

**Step 7: Update project state**

Update project state with quick task completion record using gpd commands (ensures STATE.md + state.json stay in sync):

**7a. Record quick task completion as a decision:**

```bash
gpd state add-decision --phase "quick-${next_num}" --summary "Quick task ${next_num}: ${DESCRIPTION}" --rationale "Ad-hoc task completed outside planned phases"
```

**7b. Update last activity:**

```bash
gpd state update "Last Activity" "${date}"
```

Treat the durable record for a quick task as:

- the decision entry written above via `gpd state add-decision`
- the updated `Last Activity` field via `gpd state update`
- the artifacts in `${QUICK_DIR}` (`${next_num}-PLAN.md`, `${next_num}-SUMMARY.md`, and any committed outputs)

If you want a human-facing index, put it in `GPD/quick/README.md` or in the quick-task summary.

---

**Step 8: Final commit and completion**

Stage and commit quick task artifacts:

```bash
PRE_CHECK=$(gpd pre-commit-check --files ${QUICK_DIR}/${next_num}-PLAN.md ${QUICK_DIR}/${next_num}-SUMMARY.md GPD/STATE.md 2>&1) || true
echo "$PRE_CHECK"

gpd commit "docs(quick-${next_num}): ${DESCRIPTION}" --files ${QUICK_DIR}/${next_num}-PLAN.md ${QUICK_DIR}/${next_num}-SUMMARY.md GPD/STATE.md
```

Get final commit hash:

```bash
commit_hash=$(git rev-parse --short HEAD)
```

Display completion output:

```
---

GPD > QUICK TASK COMPLETE

Quick Task ${next_num}: ${DESCRIPTION}

Summary: ${QUICK_DIR}/${next_num}-SUMMARY.md
Commit: ${commit_hash}

---

Ready for next task: gpd:quick
```

</process>

<success_criteria>

- [ ] `GPD/` directory exists
- [ ] User provides task description
- [ ] Slug generated (lowercase, hyphens, max 40 chars)
- [ ] Next number calculated (001, 002, 003...)
- [ ] Directory created at `GPD/quick/NNN-slug/`
- [ ] `${next_num}-PLAN.md` created by planner
- [ ] `${next_num}-SUMMARY.md` created by executor
- [ ] Structured state updated via `gpd state` commands
- [ ] Artifacts committed
</success_criteria>
