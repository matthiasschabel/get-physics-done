<purpose>
Create executable PLAN.md files for a phase. Default flow: Research if needed -> Plan -> Verify -> Done, using researcher, planner, and checker agents with a max-3 revision loop.
</purpose>

<stage_boundary>
First-stage authority only: phase lookup, contract-gate validation, lifecycle gate, dirty-worktree safety, early conflict stops, and bootstrap routing. Do not load downstream authorities here.
</stage_boundary>

<process>

## 1. Initialize

Bootstrap with only the phase metadata and contract gate:

```bash
BOOTSTRAP_INIT=$(gpd --raw init plan-phase "$PHASE" --stage phase_bootstrap)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $BOOTSTRAP_INIT"
  exit 1
fi
```

Use `gpd --raw stage field-access plan-phase --stage phase_bootstrap --style instruction` to confirm the manifest-selected bootstrap fields. The staged field-access helper is the source of truth for which fields are available; use `gpd --raw stage field-access plan-phase --stage <stage_id> --style instruction` after later reloads. Parse only the fields named by `BOOTSTRAP_INIT.staged_loading.required_init_fields`; this stage-selected payload includes `project_contract_gate` before any authoritative contract use.

**Mode-aware behavior:**
- `autonomy=supervised` (default): Present draft plans for user review before approval or execution; do not weaken the contract gate.
- `autonomy=balanced`: Pause only if the checker raises issues or planning choices need user judgment.
- `autonomy=yolo`: Write the plan and proceed.
- `research_mode=explore`: Always run research step even if research exists. Expand research and comparison coverage, but do not auto-create git-backed branches or branch-like plans just because alternatives appear.
- `research_mode=exploit`: Reuse existing research only when it already covers the exact method family, anchors, and decisive evidence path for this phase. Otherwise run targeted research and suppress optional tangents entirely unless the user explicitly requests them. Do not volunteer `gpd:branch-hypothesis` as the default response in exploit mode.
- `research_mode=balanced` (default): Use the standard research depth for the phase and keep the default contract-checking and comparison coverage unless the phase needs broader or narrower review.
- `research_mode=adaptive`: Start broad until prior decisive evidence or an explicit approach lock justifies narrowing. Do not infer “safe to narrow” from phase number alone.
- Tangent policy: when multiple viable approaches or optional side questions appear, do NOT silently branch or widen the plan. Use the canonical tangent decision model below instead of assuming extra plans or branches. `git.branching_strategy` does not override this rule.
- All modes still require contract completeness, decisive outputs, required anchors, forbidden-proxy handling, and disconfirming paths before execution starts.

**Staged init access rule:** after every `gpd --raw init plan-phase ... --stage <stage_id>` reload, follow `references/orchestration/agent-module-loading.md`: read only the current `INIT.staged_loading.required_init_fields`, derive stage-local values from that payload, and request explicit `--alias ALIAS=field` bindings for shell snippets that need aliases. Do not reuse shell variables parsed from an older stage.

```bash
REQUESTED_PHASE="${PHASE}"
INIT="${BOOTSTRAP_INIT}"
# For the scalar binding below, request the helper-owned shape with:
# gpd --raw stage field-access plan-phase --stage phase_bootstrap --style shell --payload-var INIT --alias PHASE=phase_number
PHASE=$(echo "$INIT" | gpd json get .phase_number --default "${REQUESTED_PHASE}")
```

**Dirty worktree safety gate:** before phase directory creation, handoffs, fingerprints, alignment, or write-capable reloads, inspect only the project worktree:

If the project worktree is dirty, halt before planning. Show the dirty paths and offer `git status --short`, `gpd commit`, or an explicitly approved project-local cleanup path. `plan-phase` never stashes, resets, cleans, overwrites, or hides user work.

**If `planning_exists` is false:** Error -- run `gpd:new-project` first.

Contract-stop closeout: render blocked stops through `references/orchestration/stage-stop-envelope.md` with `workflow: plan-phase`, `stage: phase_bootstrap`, `status: blocked`, and `checkpoint: contract_gate`. Use one public primary command: `gpd:sync-state` for load/validation/gate repair, `gpd:new-project` for a missing setup contract; after repair, continue with `gpd:plan-phase {PHASE}` and keep `gpd:suggest-next` secondary.

**If `project_contract_load_info.status` starts with `blocked`:** STOP and checkpoint with the user. Show the specific `project_contract_load_info.errors` / `warnings`; do not silently continue from `ROADMAP.md` or `REQUIREMENTS.md` alone when the stored contract could not even be loaded cleanly. Use the contract-stop closeout.

**If `project_contract` is empty or null:** STOP and checkpoint with the user. Planning requires an approved scoping contract in `GPD/state.json`; do not infer phase scope from `ROADMAP.md` or `REQUIREMENTS.md` alone. Use the contract-stop closeout, choosing `gpd:new-project` as primary unless state exists but drifted.

**If `project_contract_validation.valid` is false:** STOP and checkpoint with the user. Quote the `project_contract_validation.errors` explicitly and repair the contract before planning; a visible-but-blocked contract is not an approved planning contract. Use the contract-stop closeout.

**If `project_contract_gate.authoritative` is not true:** STOP and checkpoint with the user. Treat `project_contract` as authoritative only when `project_contract_gate.authoritative` is true. Show `project_contract_gate`, load errors/warnings, and validation errors. Do not plan, execute, verify, fingerprint, align, or pass `project_contract` to subagents until the gate is authoritative. Use the contract-stop closeout.
Run the executable lifecycle authority gate before any research, planning, checker, fingerprint, or alignment step:

```bash
LIFECYCLE_CONTRACT_GATE=$(gpd --raw validate lifecycle-contract-gate plan-phase "${PHASE}")
if [ $? -ne 0 ]; then
  echo "$LIFECYCLE_CONTRACT_GATE"
  exit 1
fi
```

<step name="fail_closed_on_state_conflict" priority="first">
Before resolving a missing phase, creating `PHASE_DIR`, spawning agents, or writing plans, compare `state_content`, `roadmap_content`, `requirements_content`, phase directories, and conventions. If they disagree about phase/scope, STOP: no new plan, roadmap rewrite, execution, or generic health check. Repair route:

- state/roadmap phase mismatch or missing active phase directory -> `gpd:sync-state`
- convention-lock or `GPD/CONVENTIONS.md` mismatch -> `gpd:validate-conventions`

Canonical conflict-stop labels: `status: blocked`, `phase_state: contract_conflict`, `plan_authority: blocked`, `execution_state: not_started`, `checkpoint: convention_conflict`, artifacts+writes `none`, `gpd:sync-state`/`gpd:validate-conventions`
</step>

## 1.5 Proof-Obligation Planning Gate

The planner template owns the detailed theorem and proof-redteam policy. The workflow only needs to keep proof-bearing work fail-closed: `--skip-verify` does NOT waive checker review, checker-disabled config does not waive proof review, and any proof-bearing plan set still needs checker review or an equivalent main-context audit before planning is considered complete. Proof-bearing work includes theorem-style claims, `claim`, lemma, corollary, proposition, proof, prove, existence, and uniqueness tasks.

## 2. Parse and Normalize Arguments

Extract from $ARGUMENTS: phase number (integer or decimal like `2.1`), flags (`--research`, `--skip-research`, `--gaps`, `--skip-verify`, `--light`, `--inline-discuss`).

### `--inline-discuss` Flag (Combined Discuss + Plan)

When `--inline-discuss` is present, combine discuss-phase and plan-phase for straightforward phases.

**Before step 5 (Handle Research), insert a quick gray-area probe:**

1. Read the phase goal/description from ROADMAP.md and ask 2-3 planning-critical gray-area questions:
   - "What formalism/method do you envision for this phase?" (if multiple valid approaches exist)
   - "Are there any constraints or conventions from prior phases that should carry through?" (if phase has dependencies)
   - "What precision level is acceptable?" (for numerical/computational phases)
2. If those questions reveal viable alternatives or side questions, use the canonical tangent decision model below instead of assuming extra plans or branches.
3. Record the answers and any explicit tangent decision in lightweight CONTEXT.md, then proceed to step 5.

This is not the full discuss-phase flow; use `gpd:discuss-phase` separately for complex phases.

**If no phase number:** Use the `phase_number` returned by bootstrap; `gpd --raw init plan-phase --stage phase_bootstrap` auto-detects the first roadmap phase whose disk status is `empty`, `no_directory`, `discussed`, or `researched`. If bootstrap cannot infer one, stop and ask for an explicit phase.

**If `phase_found` is false:** Validate that the phase exists in ROADMAP.md. If valid, resolve `PHASE_NAME`, `PHASE_SLUG`, `PADDED_PHASE`, and `PHASE_DIR` from the roadmap before continuing. If invalid, stop with `Error: Phase {PHASE} not found in ROADMAP.md.`

Use these resolved values for all later references to `PHASE_DIR`, `PHASE_SLUG`, and `PADDED_PHASE`.

**Existing artifacts from init:** `has_research`, `has_plans`, `plan_count`.

## 3. Validate Phase

Use the roadmap phase helper to refresh phase metadata. **If `found` is false:** Error with available phases. **If `found` is true:** Extract `phase_number`, `phase_name`, `goal` from the structured result.

## 4. Load CONTEXT.md and Hypothesis Context

Use `context_content` from init JSON (already loaded via `--include context`).

**CRITICAL:** Use `context_content` from INIT -- pass to researcher, planner, checker, and revision agents.

If `context_content` is not null, display: `Using phase context from: ${PHASE_DIR}/*-CONTEXT.md`

### Hypothesis-Aware Planning

Check the structured active-hypothesis state. If one exists, bind `HYPOTHESIS_SLUG`, read `GPD/hypotheses/{HYPOTHESIS_SLUG}/HYPOTHESIS.md`, and store its contents as `HYPOTHESIS_CONTENT`.

**If an active hypothesis exists:**

1. Extract the branch slug, read HYPOTHESIS.md using the shell snippet above, and display `Active hypothesis detected: hypothesis/${HYPOTHESIS_SLUG}`.
2. Treat the hypothesis description, motivation, expected outcome, and success criteria as a **primary constraint** for researcher, planner, checker, and revision prompts:

```markdown
<hypothesis_constraint>
This phase is being planned on a HYPOTHESIS BRANCH. The plan must serve
the hypothesis investigation, not the default approach.

{HYPOTHESIS_CONTENT}

**Planning constraint:** Every plan task must either:
- Directly test or advance the hypothesis, OR
- Provide infrastructure required by hypothesis-specific tasks

Do NOT plan tasks that follow the parent branch approach. The parent branch
already explores that path.
</hypothesis_constraint>
```

3. Append this `<hypothesis_constraint>` block to the prompts for the researcher, planner, checker, and revision agents.

## 4.5. Convention Verification

**Verify conventions before planning** — plans that depend on conventions from prior phases must use the correct ones:

Run the convention check before planning. If it fails, stop with the check output and route to convention validation; convention mismatches compound into every planned task.

If the check fails, stop before spawning the researcher or planner. Convention mismatches in the plan propagate into every task during execution.

## 4.6. Tangent Control During Planning

Required 4-way tangent decision model:

- Branch as alternative hypothesis -> route through `gpd:tangent` or `gpd:branch-hypothesis`
- Run a bounded side investigation now -> route through `gpd:quick`
- Capture and defer -> route through `gpd:add-todo`
- Stay on the main line -> create plans only for the selected primary approach

The planner template owns the detailed tangent decision model. The workflow only needs to surface an explicit checkpoint when the planner reports multiple viable approaches; do NOT silently branch, widen scope, or create detached side plans here.

Next, reload `gpd --raw init plan-phase "$PHASE" --stage research_routing` and read only that stage's `staged_loading.eager_authorities`.

</process>
