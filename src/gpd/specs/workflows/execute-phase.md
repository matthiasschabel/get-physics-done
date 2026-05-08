<purpose>
Execute phase plans through wave-based delegation with checkpointing and validation.
</purpose>

<core_principle>
Coordinate, do not perform plan work. The orchestrator discovers plans, groups waves, dispatches executors, handles checkpoints, collects returns, and validates physics.
</core_principle>

<required_reading>
Load the structured init-state payload first; reopen STATE.md only if a later staged refresh is missing, stale, or flagged by `state_load_source` / `state_integrity_issues`.
For agent selection strategy and verification failure routing, see `{GPD_INSTALL_DIR}/references/orchestration/meta-orchestration.md`.
For artifact class definitions and review priority rules, see `{GPD_INSTALL_DIR}/references/orchestration/artifact-surfacing.md`.
</required_reading>

<process>

<step name="normalize_arguments" priority="first">
Normalize phase and flags before any init call. The first non-flag positional token is the phase; flags may appear before or after it.

```bash
PHASE_ARG=""
EXECUTE_FLAGS=()
for token in $ARGUMENTS; do
  case "$token" in
    --*) EXECUTE_FLAGS+=("$token") ;;
    *) [ -z "$PHASE_ARG" ] && PHASE_ARG="$token" ;;
  esac
done
GAPS_ONLY=false
for flag in "${EXECUTE_FLAGS[@]}"; do
  [ "$flag" = "--gaps-only" ] && GAPS_ONLY=true
done

if [ -z "$PHASE_ARG" ]; then
  echo "ERROR: missing phase. Usage: execute-phase <phase-number> [--gaps-only]"
  exit 1
fi
```
</step>

<step name="initialize" priority="first">
Load the bootstrap stage first. Keep later wave and closeout context on demand.

```bash
load_execute_phase_stage() {
  local stage_name="$1"
  local init_payload=""
  local init_stderr=""
  local init_status=0

  if [ -n "$stage_name" ]; then
    init_stderr=$(mktemp)
    init_payload=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage "${stage_name}" 2>"$init_stderr")
    init_status=$?
    if [ "$init_status" -ne 0 ] || [ -z "$init_payload" ]; then
      echo "ERROR: staged gpd initialization failed for stage '${stage_name}' (exit ${init_status})."
      [ -n "$init_payload" ] && echo "stdout: ${init_payload}"
      [ -s "$init_stderr" ] && echo "stderr: $(cat "$init_stderr")"
      rm -f "$init_stderr"
      return 1
    fi
    rm -f "$init_stderr"

    printf '%s' "$init_payload"
    return 0
  fi

  gpd --raw init execute-phase "${PHASE_ARG}"
}

BOOTSTRAP_INIT=$(load_execute_phase_stage phase_bootstrap)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $BOOTSTRAP_INIT"
  exit 1
fi
```

Use `gpd --raw stage field-access execute-phase --stage phase_bootstrap --style instruction` to confirm the manifest-selected bootstrap fields. Read only those keys from `BOOTSTRAP_INIT`; `BOOTSTRAP_INIT.staged_loading.required_init_fields` is the runtime confirmation.

**If `phase_found` is false:** Error -- phase directory not found.
**If `plan_count` is 0:** Error -- no plans found in phase.
**If `state_exists` is false but `GPD/` exists:** Offer reconstruct or continue.

If `project_contract_load_info.status` starts with `blocked`, STOP and show the concrete `project_contract_load_info.errors` / `warnings` before execution. A contract that could not be loaded cleanly is not safe to execute from.

If `project_contract_validation.valid` is false, STOP and show the explicit `project_contract_validation.errors` before execution. Do not treat a visible-but-blocked contract as an approved execution contract.

**If `project_contract_gate.authoritative` is not true:** STOP and checkpoint with the user. Show `project_contract_gate`, `project_contract_load_info.errors`, `project_contract_load_info.warnings`, and `project_contract_validation.errors` if present. Do not plan, execute, verify, fingerprint, align, or pass `project_contract` to subagents until the gate is authoritative. End with `## > Next Up`: primary `gpd:sync-state` or `gpd:new-project` as appropriate, then `gpd:execute-phase ${PHASE_ARG}` after repair, plus `gpd:suggest-next`.

Run the executable lifecycle authority gate before branch handling, plan preflight, wave planning, contract fingerprinting, alignment summary, or any executor/verifier delegation:

```bash
LIFECYCLE_CONTRACT_GATE=$(gpd --raw validate lifecycle-contract-gate execute-phase "${PHASE_ARG}")
if [ $? -ne 0 ]; then
  echo "$LIFECYCLE_CONTRACT_GATE"
  exit 1
fi
```

Later staged refreshes surface `effective_reference_intake`, `active_reference_context`, and `reference_artifacts_content` for anchor-aware routing and wave planning. Stable knowledge docs may appear only through those shared reference surfaces as reviewed background; they do not become a separate authority tier. Do not assume bootstrap already loaded that broader reference context.
Before branch handling, scripts, computations, dispatches, subagents, writes, or claims, require that the selected `PLAN.md` passes `gpd validate plan-preflight <PLAN.md>` as part of `validate_selected_plans_before_execution`.

When `parallelization` is false, plans within a wave execute sequentially.

**Mode-aware behavior:**
- `autonomy` controls who gets interrupted at a wave boundary.
- `research_mode` only adjusts depth and optional tangents; it does not relax required gates.
- `research_mode=balanced` (default): Use the standard execution depth and keep the default contract, anchor, and review coverage unless the wave needs broader or narrower review.
- `review_cadence` controls bounded phase pauses.
- `execute-plan.md owns plan-local execution semantics; this workflow only owns phase-wide routing and wave risk.`
- Even in `yolo`, do NOT skip required correctness gates, first-result sanity checks, skeptical review stops, or anchor-gated fanout reviews. A clean pass may auto-continue only after the gate is explicitly cleared.
- `research_mode=adaptive`: Start with explore-style coverage, then narrow only after prior decisive `contract_results`, decisive `comparison_verdicts`, or an explicit approach lock show that the method family is stable. Do NOT narrow just because a wave advanced or one proxy passed.
- Model profile may change depth, task granularity, or prose volume, but it does not waive required gates.
- `review_cadence` is read here only to schedule phase pauses; detailed gate ownership remains in `execute-plan.md`.
- `workflow.verifier=false`, sparse cadence, yolo autonomy, or any manual "skip verification" request do NOT disable mandatory proof red-teaming for proof-bearing or `proof_obligation` work.
</step>

<step name="validate_selected_plans_before_execution" priority="first">
Validate the selected plans before any execution-side work. If this gate fails, do not run workspace scripts, numerical computations, task dispatches, subagents, artifact writes, branch creation, or result claims.
```bash
SELECTED_PLAN_FILES=()
for plan in "$phase_dir"/*-PLAN.md; do
  [ -e "$plan" ] || continue
  if [ "$GAPS_ONLY" = true ]; then
    GAP_CLOSURE=$(gpd frontmatter get "$plan" --field gap_closure 2>/dev/null || echo false)
    [ "$GAP_CLOSURE" = "true" ] || continue
  fi
  SELECTED_PLAN_FILES+=("$plan")
done
if [ ${#SELECTED_PLAN_FILES[@]} -eq 0 ]; then
  echo "ERROR: no executable PLAN.md files found for phase ${PHASE_ARG}. Revise or recreate the missing/invalid plan, then rerun execute-phase for ${PHASE_ARG}."
  exit 1
fi
PLAN_GATE_FAILED=false
for plan in "${SELECTED_PLAN_FILES[@]}"; do
  gpd validate plan-contract "$plan" || PLAN_GATE_FAILED=true
  if ! gpd verify plan "$plan"; then
    PLAN_GATE_FAILED=true
  fi
  PLAN_PREFLIGHT=$(gpd --raw validate plan-preflight "$plan") || {
    echo "ERROR: plan preflight failed for $(basename "$plan")"
    echo "$PLAN_PREFLIGHT"
    PLAN_GATE_FAILED=true
  }
  gpd verify references "$plan" || PLAN_GATE_FAILED=true
done
gpd phase validate-waves "$phase_number" || PLAN_GATE_FAILED=true
if [ "$PLAN_GATE_FAILED" = true ]; then
  echo "Plan validation/preflight failed before execution; no workspace scripts, numerical computations, task dispatches, subagents, artifact writes, or result claims were authorized."
  echo "Next: revise or recreate the invalid PLAN.md, then rerun execute-phase for ${PHASE_ARG}."
  exit 1
fi
```
`gpd:plan-phase {N}` is the supported public plan repair route. Invoke it with explicit instructions to revise or recreate the invalid `PLAN.md`, then rerun `gpd:execute-phase {N}`.
</step>
<step name="handle_branching">
Check `branching_strategy` from init:

**"none":** Skip, continue on current branch.

**"per-phase" or "per-milestone":** Use pre-computed `branch_name` from init:

```bash
git checkout -b "$BRANCH_NAME" 2>/dev/null || git checkout "$BRANCH_NAME"
```

All subsequent commits go to this branch. User handles merging.
</step>

<step name="classify_phase">
Classify the phase type to drive agent selection and context budget decisions. Scan the phase goal and plan objectives for indicator keywords.

Load `load_execute_phase_stage phase_classification`, then classify from the stage payload, the phase goal, and selected plan objectives.

Use `gpd --raw stage field-access execute-phase --stage phase_classification --style instruction` before reading `PHASE_CLASSIFICATION_INIT`; fields outside that helper-selected set are unavailable at this stage.

Classify semantically. A phase may have multiple classes: `derivation`, `numerical`, `literature`, `paper-writing`, `formalism`, `analysis`, and `validation`; use `mixed` only when none of those apply.

Log the classification: `"Phase ${phase_number} classified as: ${PHASE_CLASSES[*]}"`

**Use classification for:**
- Agent selection (see `agent-infrastructure.md` Meta-Orchestration Intelligence > Agent Selection by Phase Type)
- Context budget targets (see `agent-infrastructure.md` Meta-Orchestration Intelligence > Context Budget Allocation)
- Verifier check prioritization (derivation phases promote dimensional / limit / identity-critical checks; numerical phases promote `5.5` convergence and `5.14` statistics; validation phases run the full relevant registry)
- Computation-type-aware execution adaptation (see `adapt_to_computation_type` below)
</step>

<step name="adapt_to_computation_type">
Translate the phase classification into concrete execution parameters that drive wave-loop behavior. Set these variables before entering `execute_waves`:

Start from this default routing state: `CONVENTION_LOCK_REQUIRED=false`, no pre-execution specialists, `INTER_WAVE_CHECKS=[convention, dimensional]`, `EXECUTOR_CONTEXT_HINT=standard`, `WAVE_TIMEOUT_FACTOR=1.0`, `FORCE_SEQUENTIAL=false`, and no yolo restrictions.

**Per-class overrides:** Apply these cumulatively for multi-class phases. This table is the source of truth for convention locks, specialist routing, inter-wave checks, executor context hints, timeout factors, sequential forcing, and yolo restrictions.

| Class | Overrides |
|---|---|
| `derivation` | require convention lock, add identity scan, use `derivation-heavy`, increase timeout factor, disallow skipped verification in yolo |
| `numerical` | add convergence spot check, use `code-heavy`, route `gpd-experiment-designer` only when the phase or plan requires a standalone design handoff |
| `literature` | force sequential execution, use `reading-heavy`, keep convention-only inter-wave checks |
| `paper-writing` | route notation coordination when needed, add LaTeX compile smoke checks, use `prose-heavy` |
| `formalism` | require convention lock, route notation coordination when needed, add identity scan |
| `analysis` | add plausibility scan |
| `validation` | disallow skipped verification and skipped inter-wave checks in yolo, add identity, convergence, and plausibility scans |

**Convention lock enforcement:**

If `CONVENTION_LOCK_REQUIRED=true`:

Run the convention lock gate and require a `locked` or `complete` result before execution. If it fails, halt with a concrete `gpd convention set` / `gpd:validate-conventions` repair route; derivation and formalism convention errors compound across every step.

**Hard gate:** when `CONVENTION_LOCK_REQUIRED=true` and conventions are not locked, execution MUST NOT proceed in any autonomy mode. Convention errors invalidate downstream results.

**Pre-execution specialist routing:**

The `pre_execution_specialists` stage consumes `PRE_EXECUTION_SPECIALISTS` and loads delegation guidance for real one-shot handoffs. This workflow chooses specialist types; it does not inline placeholder `task(...)` calls or wait for child confirmation in the same run.

**Force-sequential override:**

If `FORCE_SEQUENTIAL=true`, override `PARALLELIZATION` to false for this phase regardless of config setting. Log: `"Phase class (${PHASE_CLASSES[*]}) forces sequential execution within waves."`

**YOLO mode restrictions:**

If `autonomy=yolo` and `YOLO_RESTRICTIONS` is non-empty, restrict yolo behavior: `no_skip_verification` keeps verification mandatory; `no_skip_inter_wave` keeps inter-wave gates mandatory.

Log any restrictions: `"YOLO mode restricted for phase class (${PHASE_CLASSES[*]}): ${YOLO_RESTRICTIONS[*]}"`

**Context hint propagation:**

Include `EXECUTOR_CONTEXT_HINT` in the executor spawn prompt so subagents can self-regulate:

```
<context_hint>{EXECUTOR_CONTEXT_HINT}</context_hint>
```

Hint meanings: `standard` balances derivation/code/prose; `derivation-heavy`, `code-heavy`, `reading-heavy`, and `prose-heavy` reserve context for their named work type without changing required gates.
</step>

<step name="validate_phase">
From init JSON: `phase_dir`, `plan_count`, `incomplete_count`.

Report: "Found {plan_count} plans in {phase_dir} ({incomplete_count} incomplete)"
</step>

<step name="detect_proof_obligation_work">
Classify whether any selected plan is proof-bearing before execution and before honoring verifier-disabled or sparse-review settings.

@{GPD_INSTALL_DIR}/references/verification/core/proof-redteam-workflow-gate.md

For each proof-bearing plan, require a sibling `{plan_id}-PROOF-REDTEAM.md` artifact that follows the shared gate above.

Never treat a clean `SUMMARY.md`, correct algebra in a subset of cases, or "human will inspect later" as a substitute for this artifact.
When runtime delegation is available, `gpd-check-proof` is the canonical owner of this sibling artifact. The executor may draft the proof and theorem inventory, but it must not self-certify theorem-proof alignment as its own independent redteam.
</step>

<step name="refresh_wave_planning_context">
Refresh the wave-planning stage so the orchestrator does not keep late execution context pinned in bootstrap state:

```bash
WAVE_PLANNING_INIT=$(load_execute_phase_stage wave_planning)
if [ $? -ne 0 ]; then
  echo "ERROR: wave-planning stage refresh failed: $WAVE_PLANNING_INIT"
  exit 1
fi
```

Use `gpd --raw stage field-access execute-phase --stage wave_planning --style instruction` to confirm the manifest-selected wave-planning fields. Read only those keys from `WAVE_PLANNING_INIT`; `WAVE_PLANNING_INIT.staged_loading.required_init_fields` is the runtime confirmation.
</step>

<step name="claim_deliverable_alignment_check">
Gate execution on explicit confirmation that the machine-readable claim matches user intent for Phase {N}.

Read the persisted alignment status and the current contract/context fingerprints before rendering anything:

```bash
ALIGNMENT_STATUS=$(gpd contract alignment-status 2>/dev/null || echo '{}')
CONTRACT_HASH=$(gpd contract fingerprint 2>/dev/null)
CONTEXT_HASH=$(gpd contract context-fingerprint 2>/dev/null)
CONFIRMED_AT=$(echo "$ALIGNMENT_STATUS" | gpd json get .confirmed_at --default null)
CONFIRMED_CONTRACT_HASH=$(echo "$ALIGNMENT_STATUS" | gpd json get .confirmed_contract_hash --default null)
CONFIRMED_CONTEXT_HASH=$(echo "$ALIGNMENT_STATUS" | gpd json get .confirmed_context_hash --default null)
```

**Fingerprint gate:** Fail closed if either fingerprint command fails or resolves to an empty value before rendering the prompt or recording confirmation. Do not compare blank hashes, do not suppress the gate, and do not call `gpd contract record-alignment` on this path.

```bash
if [ -z "$CONTRACT_HASH" ] || [ -z "$CONTEXT_HASH" ]; then
  echo "ERROR: claim_deliverable_alignment_check could not resolve contract/context fingerprints."
  echo "Next Up: discuss, plan, then execute phase {N}"
  exit 1
fi
```

**Gating:** Fires when `autonomy=supervised` OR `review_cadence=dense` OR any selected plan is proof-bearing per `detect_proof_obligation_work`. Skip only under `autonomy=yolo AND review_cadence in {adaptive, sparse} AND no proof-bearing plans`; log `claim_deliverable_alignment_check: skipped (autonomy=yolo, cadence=adaptive, no proof-bearing plans)` and continue to `discover_and_group_plans` without prompting.

**Suppression:** If `confirmed_at` is set AND the current `contract_fingerprint == confirmed_contract_hash` AND `context_guidance_fingerprint == confirmed_context_hash`, skip and log `claim_deliverable_alignment_check: skipped (already confirmed this session)`. Use `gpd contract alignment-status` plus `CONTRACT_HASH`/`CONTEXT_HASH`.

**Render:** When fired and not suppressed, render a one-screen `Claim ↔ Deliverable Alignment` table. Left column: CONTEXT.md + `ContractContextIntake`; right column: `gpd contract alignment-summary`. Cap each cell at 5 bullets.

```
| User intent (CONTEXT)               | Machine contract                    |
|-------------------------------------|-------------------------------------|
| Observables: ...                    | Claims: ...                         |
| Deliverables: ...                   | Deliverables: ...                   |
| Must-have references: ...           | Acceptance tests: ...               |
| Stop-or-rethink conditions: ...     |                                     |
```

**ask_user:** Present exactly one question with 4 options. Enter selects `Y`.

```
ask_user([
  {
    question: "Does the machine contract above match your intent for Phase {N}? Press Enter to proceed, or pick an option to revise.",
    header: "Claim ↔ Deliverable Alignment",
    multiSelect: false,
    options: [
      { label: "Y: proceed (Recommended, Enter = Y)", description: "Record confirmed alignment and continue." },
      { label: "e: edit CONTEXT", description: "Revise intent with gpd:discuss-phase {N}, then re-enter once." },
      { label: "p: edit PLAN contract", description: "Revise the machine contract with gpd:plan-phase {N}, then re-enter once." },
      { label: "n: abort", description: "Stop cleanly. Next Up is gpd:execute-phase {N} after alignment is resolved." }
    ]
  }
])
```

**Interactive answer requirement:** Only an explicit `ask_user` answer of `Y: proceed` authorizes record-alignment. The command invocation, missing `ask_user` support, timeout, empty answer, or any noninteractive run is not an alignment answer. Otherwise STOP before `gpd contract record-alignment`, branch/checkpoint writes, scripts/numerical computations, dispatches/subagents, and artifacts. End: `Blocked: claim-deliverable alignment needs an explicit user answer. Next Up: rerun gpd:execute-phase {N} interactively.`
**On "Y: proceed" (or Enter from that `ask_user` prompt):** Record alignment and continue:
```bash
gpd contract record-alignment --contract-hash "$CONTRACT_HASH" --context-hash "$CONTEXT_HASH"
```

**On "n: abort":** Exit cleanly. Do NOT spawn any executor and do NOT proceed to `discover_and_group_plans`. Emit a final line `"Next Up: gpd:execute-phase {N}"` so the operator can resume after resolving alignment.

**On "e" / "p":** Hand off to `gpd:discuss-phase {N}` or `gpd:plan-phase {N}`, then re-enter once. If the same key is chosen again, defer to that workflow and stop looping.
</step>

<step name="discover_and_group_plans">
Load plan inventory with wave grouping from `gpd phase index {phase_number}`.

Parse JSON for: `phase`, `plans[]` (each with `id`, `wave`, `interactive`, `gap_closure`, `objective`, `files_modified`, `task_count`, `has_summary`), `waves` (map of wave number -> plan IDs), `incomplete`, `has_checkpoints`.

**Filtering:** Skip plans where `has_summary: true`. If `$GAPS_ONLY` is true, also skip non-gap_closure plans. If all filtered: "No matching incomplete plans" -> exit.

**Intra-wave dependency validation:** From the phase index, verify that no plan's `depends_on` references another plan in the same wave. If any same-wave dependency exists, stop and report the plan IDs and wave number.

**Parallel file conflict detection:** For waves with two or more plans, compare the indexed `files_modified` sets. If two plans touch the same path, warn and offer to serialize those plans within the wave.

If `INTRA_WAVE_CONFLICT` is true: STOP — present the dependency issue and do not proceed.
If `FILE_CONFLICT` is true: WARN — present the overlap and offer to serialize the conflicting plans within the wave.

Report:

```
## Execution Plan

**Phase {X}: {Name}** -- {total_plans} plans across {wave_count} waves

| Wave | Plans | What it builds |
|------|-------|----------------|
| 1 | 01-01, 01-02 | {from plan objectives, 3-8 words} |
| 2 | 01-03 | ... |
```

</step>

<step name="resolve_execution_cadence">
Translate cadence config plus wave risk into concrete execution boundaries before any executor is spawned.

Read `review_cadence`, `research_mode`, the unattended-minute limits, checkpoint thresholds, `strict_wait`, `never_interrupt_running_workers`, and `never_auto_close_child_agents` from the current staged payload/config. `strict_wait` disables unattended-minute cutoffs entirely; `never_interrupt_running_workers` is the narrower form of the same guarantee. In either case, set plan and wave unattended-minute limits to zero so workers run to natural completion.

**Core invariant:** `autonomy` decides who gets interrupted. `review_cadence` decides when the system must stop, inspect, or re-question. Even in `yolo`, required first-result and pre-fanout gates still run; the difference is that a clean pass can auto-continue.

These gates are task-level safety rails, not line-by-line interruptions. Even in `supervised`, checkpoint after each plan task or required gate, not after every algebraic micro-step.

For each wave, classify whether downstream fanout is risky:

- risky when a wave has multiple plans and any later wave depends on it
- risky when any plan has `task_count >= CHECKPOINT_AFTER_N_TASKS`, no authored checkpoints, or is likely to exceed `MAX_UNATTENDED_MINUTES_PER_PLAN`
- risky for `derivation`, `formalism`, `numerical`, or `validation` phase classes
- risky when file conflicts, convention-lock requirements, or benchmark-critical anchors are present
- risky when the wave creates a new estimator, baseline, or branch point whose downstream usefulness depends on a decisive comparison still to be earned
- never mark a wave "safe" merely because it happens later in the phase or follows an earlier partial pass

When a wave is risky:

- set `FIRST_RESULT_GATE_REQUIRED=true`
- set `PRE_FANOUT_REVIEW_REQUIRED=true`
- set `SEGMENT_TASK_CAP=${CHECKPOINT_AFTER_N_TASKS}`
- force bounded continuation segments even when the authored plan has no checkpoints

**Dense cadence override:** when `review_cadence=dense`, treat every wave as risky regardless of the heuristic checks above, applying the "When a wave is risky" bullets unconditionally (in particular `FIRST_RESULT_GATE_REQUIRED=true` and `PRE_FANOUT_REVIEW_REQUIRED=true`). The "not risky" branch does not apply; a clean pass may auto-continue once the gate fires, but the gate must fire.

When a wave is not risky:

- keep bounded execution available for long plans, wall-clock budgets, and context pressure
- allow checkpoint-free plans to run normally when task count is small and fanout is low

**Skeptical re-questioning rule:** if the first material result only validates a proxy, internal consistency story, or supporting artifact while decisive anchors, benchmark references, or contract-backed acceptance tests remain unresolved, stop and explicitly re-question the framing before allowing downstream fanout. Record:

- weakest unchecked anchor
- what still looks assumed rather than verified
- the disconfirming observation that would most quickly break the current path
- which downstream plans would become wasted work if that decisive evidence failed

**Proposal-first tangent control:** if an unexpected but non-blocking alternative path appears during execution, do not silently pursue it. Treat it as a tangent proposal and classify it using exactly one of these four decisions at the existing review stop:

- `ignore` — not a real tangent; continue the approved mainline plan
- `defer` — record it briefly in the wave report / SUMMARY as future follow-up, then continue the mainline plan
- `branch_later` — recommend `gpd:tangent ...` or `gpd:branch-hypothesis ...` for explicit follow-up, but do not create new side work during this execution pass
- `pursue_now` — only when the user explicitly requested tangent exploration or the approved contract already includes that alternative path

This is proposal-first, not a new execution state machine. Tangent proposals ride on the existing first-result / skeptical / pre-fanout review stops.

When `RESEARCH_MODE=exploit`, suppress optional tangents by default: classify them as `ignore` or `defer` unless the prompt or the user explicitly asked for tangent exploration.
</step>

<step name="prepare_pre_execution_specialists">
Load the specialist-routing stage only when a pre-wave specialist is actually needed.

When `PRE_EXECUTION_SPECIALISTS` is non-empty, bind `PRE_EXECUTION_INIT=$(load_execute_phase_stage pre_execution_specialists)` and stop if the staged refresh fails.

Use `gpd --raw stage field-access execute-phase --stage pre_execution_specialists --style instruction` before reading `PRE_EXECUTION_INIT`; this stage is available only for explicit one-shot specialist handoff sites.

Use this stage only at explicit one-shot specialist handoff sites. Do not recreate placeholder `task(...)` examples here, do not wait in place for user approval inside a child run, and do not treat a named specialist route as complete unless its later artifact gate passes.
</step>

<step name="execute_waves">
Execute each wave in sequence. Within a wave: parallel if `PARALLELIZATION=true` AND `FORCE_SEQUENTIAL=false`, sequential otherwise. (Literature phases force sequential execution — see `adapt_to_computation_type`.)

Refresh the wave-dispatch stage immediately before spawning executors so plan execution sees only the late-loaded context it actually needs:

Bind `WAVE_DISPATCH_INIT=$(load_execute_phase_stage wave_dispatch)` immediately before spawning executors and stop if the staged refresh fails.

Use `gpd --raw stage field-access execute-phase --stage wave_dispatch --style instruction` to confirm the manifest-selected wave-dispatch fields. Read only those keys from `WAVE_DISPATCH_INIT`; `WAVE_DISPATCH_INIT.staged_loading.required_init_fields` is the runtime confirmation.

**For each wave:**

1. **Convention lock check (before parallel execution):**

   Before launching parallel plans, verify convention consistency:

   ```bash
   gpd convention check
   ```

   - If conventions are unlocked for any field that parallel plans will use, LOCK them first via `gpd convention set`
   - Do NOT proceed with parallel execution if convention conflicts exist

   **Pre-flight convention check for parallel waves:** Before spawning wave executors in parallel, verify all plans in the wave reference the same `convention_lock` values. For each plan in the wave, extract any convention references (metric signature, Fourier convention, unit system) and cross-compare. If any plan's conventions differ from the locked values, resolve the discrepancy before spawning. This prevents the most insidious class of parallel execution bugs: two agents computing with different sign conventions whose results are later combined.

2. **Create wave-level checkpoint** before any plan starts. This is the rollback authority gate for the wave. Finish it before scripts, numerical computation, dispatch, subagents, artifacts, or claims. Do not run computation and then checkpoint afterward.
   ```bash
   WAVE_CHECKPOINT_RESULT=$(gpd --raw phase checkpoint create --phase "${phase_number}" --wave "${WAVE_NUM}" --namespace phase)
   if [ $? -ne 0 ]; then
     echo "$WAVE_CHECKPOINT_RESULT"
     exit 1
   fi
   ```

   Store the `tag` field from the helper result for wave-level recovery. Route only on `safe_to_execute_wave: true`; if the helper refuses the project/git-root boundary, stop before spawning any work.

3. **Describe what's being done (BEFORE spawning):**

   Read each plan's `<objective>`. Extract what's being computed/derived and why.

   ```
   ---
   ## Wave {N}

   **{Plan ID}: {Plan Name}**
   {2-3 sentences: what this derives/computes/simulates, mathematical approach, why it matters for the overall research}

   Spawning {count} agent(s)...
   ---
   ```

   Example: describe what the plan computes or derives and why it matters; avoid generic "executing plan" narration.

   **If this wave is marked risky fanout:** run `probe_then_fanout` instead of blind full-wave scaleout.

   - First launch each risky plan only to its first-result gate or bounded segment boundary.
   - Collect sanity, decisive-evidence, and anchor status; classify unexpected non-blocking alternatives as tangent proposals, not permission for silent side exploration.
   - Resolve tangent proposals with `ignore | defer | branch_later | pursue_now`; unlock the remainder only when gates pass or remaining work is independent. If a gate fails or requires re-questioning, STOP before spawning downstream work.

4. **Spawn executor agents:**

   Pass paths only -- executors read files themselves with fresh context.
   This keeps orchestrator context lean; use `references/orchestration/context-budget.md` for numeric budget targets.

   Canonical runtime delegation convention for every `task()` block in this workflow:
   @{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md
   The shared note owns runtime-neutral task construction and handoff gates. Later handoff blocks reference it instead of restating those rules.

   ```
   EXECUTOR_HANDOFF_STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
   task(
     subagent_type="gpd-executor",
     model="{executor_model}",
     readonly=false,
     prompt="First, read {GPD_AGENTS_DIR}/gpd-executor.md for your role and instructions.

       <objective>
       Execute plan {plan_number} of phase {phase_number}-{phase_name}.
       Commit each task atomically. Create SUMMARY.md.
       Return state updates (position, decisions, metrics) in your response -- do NOT write STATE.md directly.
       </objective>

       <context_hint>{EXECUTOR_CONTEXT_HINT}</context_hint>
       <phase_class>{PHASE_CLASSES}</phase_class>
       <research_mode>{RESEARCH_MODE}</research_mode>
       <selected_protocol_bundle_ids>{selected_protocol_bundle_ids}</selected_protocol_bundle_ids>
       <protocol_bundle_load_manifest>{protocol_bundle_load_manifest}</protocol_bundle_load_manifest>
       <protocol_bundle_context>{protocol_bundle_context}</protocol_bundle_context>
       <protocol_bundle_verifier_extensions>{protocol_bundle_verifier_extensions}</protocol_bundle_verifier_extensions>
       <review_cadence>{REVIEW_CADENCE}</review_cadence>
       <max_unattended_minutes_per_plan>{MAX_UNATTENDED_MINUTES_PER_PLAN}</max_unattended_minutes_per_plan>
       <max_unattended_minutes_per_wave>{MAX_UNATTENDED_MINUTES_PER_WAVE}</max_unattended_minutes_per_wave>
       <segment_task_cap>{SEGMENT_TASK_CAP}</segment_task_cap>
       <first_result_gate>{FIRST_RESULT_GATE_REQUIRED}</first_result_gate>
       <checkpoint_before_downstream>{CHECKPOINT_BEFORE_DOWNSTREAM}</checkpoint_before_downstream>
       <bounded_execution>{true}</bounded_execution>
       <proof_redteam_gate>
       If this plan is proof-bearing, leave the proof artifact, theorem inventory, and enough context for `gpd-check-proof`.
       Do NOT self-certify the sibling `{plan_id}-PROOF-REDTEAM.md` artifact when a fresh `gpd-check-proof` subagent is available.
       If any named parameter, hypothesis, or quantifier is missing, surface the gap and do NOT claim the theorem is established. Do not bypass this gate because the algebra looks clean, one limit works, or verification is disabled elsewhere.
       </proof_redteam_gate>
       <tangent_control>
       Proposal-first: classify unexpected non-blocking alternatives as `ignore`, `defer`, `branch_later`, or `pursue_now`; do not silently pursue optional tangents.
       `pursue_now` requires explicit user request or approved scope. If `research_mode=exploit`, suppress optional tangents unless requested.
       </tangent_control>

       <files_to_read>
       Read these files at execution start using the file_read tool:
       - Workflow: {GPD_INSTALL_DIR}/workflows/execute-plan.md
       - Summary template: {GPD_INSTALL_DIR}/templates/summary.md
       - Checkpoints ref: {GPD_INSTALL_DIR}/references/orchestration/checkpoints.md
       - Validation ref: {GPD_INSTALL_DIR}/references/verification/core/verification-core.md (+ domain-specific verification file)
       - Plan: {phase_dir}/{plan_file}
       - State: GPD/STATE.md
       - Config: GPD/config.json (if exists)
       </files_to_read>

	       <success_criteria>
	       - [ ] Tasks executed rigorously and committed individually
	       - [ ] Dimensional consistency and specified limiting cases checked
	       - [ ] Proof-bearing plans leave context for `gpd-check-proof` and receive `{plan_id}-PROOF-REDTEAM.md` with `status: passed` before completion is claimed
	       - [ ] SUMMARY.md created in plan directory
	       - [ ] State updates returned (NOT written to STATE.md directly)
	     </success_criteria>
     "
   )
   ```

5a. **For proof-bearing plans, spawn the independent proof critic before accepting the result.**

   Resolve the proof-critic model once per wave when any selected plan is proof-bearing:

   ```bash
   CHECK_PROOF_MODEL=$(gpd resolve-model gpd-check-proof)
   ```

   After a proof-bearing executor has written its proof artifact(s) and `SUMMARY.md`, but before the wave-level spot-check accepts the plan, spawn `gpd-check-proof` in a fresh context:

   > Apply the canonical runtime delegation convention above.

   ```
   PROOF_HANDOFF_STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
   task(
     subagent_type="gpd-check-proof",
     model="{check_proof_model}",
     readonly=false,
     prompt="First, read {GPD_AGENTS_DIR}/gpd-check-proof.md for your role and instructions.
Then read {GPD_INSTALL_DIR}/templates/proof-redteam-schema.md and {GPD_INSTALL_DIR}/references/verification/core/proof-redteam-protocol.md before writing any proof audit artifact.

       Operate in proof-redteam mode with a fresh context and follow the proof-redteam protocol's one-shot return semantics.

       Write to: {phase_dir}/{plan_id}-PROOF-REDTEAM.md

       Files to read: {phase_dir}/{plan_file}; {phase_dir}/{plan_id}-SUMMARY.md; proof/derivation artifacts; supporting verification or summary artifacts referenced by the plan.

       Reconstruct the theorem inventory explicitly before judging the proof.
       Fail closed on missing parameter coverage, missing hypotheses, narrowed quantifiers, or special-case proofs sold as general claims.",
     description="Proof redteam for phase {phase_number} plan {plan_id}"
   )
   ```

   Proof critic child artifact gate: apply `references/orchestration/child-artifact-gate.md`; checkpoint handling applies `references/orchestration/continuation-boundary.md`.

   ```yaml
   child_gate:
     id: "proof_critic_wave_audit"
     role: "gpd-check-proof"
     return_profile: "proof_redteam"
     required_status: "completed"
     expected_artifacts:
       - "{phase_dir}/{plan_id}-PROOF-REDTEAM.md"
     allowed_roots:
       - "{phase_dir}"
     freshness_marker: "after $PROOF_HANDOFF_STARTED_AT"
     validators:
       - "gpd validate proof-redteam {phase_dir}/{plan_id}-PROOF-REDTEAM.md"
       - "frontmatter status: passed before executor wave success"
     applicator: none
     failure_route: "wave_failure_handling | repair_prompt_once | retry_once_then_wave_failure_handling"
```

   Gate failure routes the plan to `wave_failure_handling`; executor self-review is not a substitute.

5. **Wait for all agents in wave to complete.**

   **Progress feedback during wave execution:** As each plan completes (or fails), immediately report to the user:

   ```
   [Phase {N}, Wave {W}] Plan {plan_id} complete ({completed}/{total} in wave)
     Result: {one-line summary from SUMMARY.md or failure reason}
   ```

   This ensures the user sees progress even when waves have multiple parallel plans. Do not wait for the entire wave to finish before showing any output.

   Wave child artifact gate: apply `references/orchestration/child-artifact-gate.md`; checkpoint handling applies `references/orchestration/continuation-boundary.md`.

   ```yaml
   child_gate:
     id: "wave_executor_plan_result"
     role: "gpd-executor"
     return_profile: "executor"
     required_status: "completed"
     expected_artifacts:
       - "${SUMMARY_FILE}"
     allowed_roots:
       - "{phase_dir}"
     freshness_marker: "after $EXECUTOR_HANDOFF_STARTED_AT"
     validators:
       - "gpd validate handoff-artifacts - --expected '${SUMMARY_FILE}' --allowed-root '{phase_dir}' --required-suffix=-SUMMARY.md --require-status completed --require-files-written --fresh-after \"$EXECUTOR_HANDOFF_STARTED_AT\""
       - "SUMMARY key-files.created / key-files.modified required/final deliverables exist"
       - "no Self-Check: FAILED or Validation: FAILED marker"
       - "proof-redteam artifact exists and reports status: passed when proof-bearing"
     applicator:
       command: "gpd --raw apply-return-updates ${SUMMARY_FILE}"
       require_passed_true: true
     failure_route: "wave_failure_handling | repair_prompt_once | retry_new_wave | repair_path_once | fail_closed_with_mutation_report"
```

   Status route: `checkpoint` uses checkpoint handling; other incomplete routes choose retry, main-context execution, or user-approved skip outside the child gate.

   **If any executor agent fails to spawn or returns an error:** use the tuple failure route. Git commits/files are recovery evidence only until the wave gate passes.

6. **Report completion -- spot-check claims first:**

   For each SUMMARY.md:

   - Verify first 2 files from `key-files.created` exist on disk
   - If the SUMMARY marks any `key-files.created` / `key-files.modified` paths as required or final-deliverable, verify those paths on disk before accepting success
	   - Check `git log --oneline --grep="{phase}-{plan}"` returns >=1 commit
	   - Check for `## Self-Check: FAILED` marker
	   - Check for `## Validation: FAILED` marker (physics-specific)
	   - For proof-bearing plans, verify the sibling `{plan_id}-PROOF-REDTEAM.md` artifact exists and has `status: passed`
	   - Validate and apply the gpd_return envelope through the canonical child-return applicator. Require the applicator result to report `passed: true`; otherwise stop with the summary path and applicator errors.

	   If ANY spot-check fails, including a missing or non-passing proof-redteam artifact for proof-bearing work, or if `apply-return-updates` does not report `passed: true`: report which plan failed, route to `wave_failure_handling` -- do NOT silently continue.

   **IMPORTANT: Executor subagents MUST NOT write STATE.md directly.** Return state updates (position, decisions, metrics) in the structured return envelope. The orchestrator applies them through `gpd apply-return-updates` after each agent completes. This prevents parallel write conflicts where multiple agents overwrite each other's STATE.md changes and keeps durable child-return ownership in one place.

   By the time the wave-complete report is emitted, the canonical applicator has already persisted every successful plan from that wave. Do not duplicate that state mutation here.

   If pass:

   ```
   ---
   ## Wave {N} Complete

   **{Plan ID}: {Plan Name}**
   {What was derived/computed -- from SUMMARY.md}
   {Notable deviations or unexpected results, if any}
   {Limiting cases verified: list}

   {If more waves: what this enables for next wave}
   ---
   ```

   - Bad: "Wave 2 complete. Proceeding to Wave 3."
   - Good: "Spin-chain spectrum computed -- Bethe ansatz solution yields N-magnon energies with correct Heisenberg limit. Finite-size scaling exponents match CFT prediction (nu = 1.00 +/- 0.02). Transport coefficient calculation (Wave 3) can now use these eigenstates."

7. **Artifact summary** -- surface key artifacts produced in the completed wave.

   After verifying wave completion, collect the artifacts from each plan's SUMMARY.md (`key-files.created`, `key-files.modified`) and emit a compact summary with review priorities. See `references/orchestration/artifact-surfacing.md` for artifact class definitions and review priority rules.

   ```
   ## Artifacts: Wave {N}

   | Path | Class | Review |
   |------|-------|--------|
   | {relative_path} | {artifact_class} | {required | optional | final-deliverable} |
   ...

   Required review: {count} artifact(s) -- inspect before Wave {N+1}
   ```

   **Classification rules:**
   - Assign artifact class from file extension and path (see artifact-surfacing.md section 1)
   - Mark as `required` if the artifact is a load-bearing derivation, a numerical result consumed by later waves, or a contract deliverable that is the `subject` of an acceptance test
   - Mark as `final-deliverable` for completed manuscript outputs, compiled PDFs, and peer review reports
   - Mark as `optional` for supporting plots, intermediate notebooks, and literature notes

   **If any artifacts are marked `required`:** Include their paths in the wave completion report so the researcher can prioritize review. Do not block execution for optional artifacts.

8. **Handle failures** -- see `wave_failure_handling` below.

9. **Execute checkpoint plans between waves** -- see `<checkpoint_handling>`.

   Before unlocking downstream dependent waves, confirm that risky-wave plans passed the first meaningful review point:

	   - the first load-bearing result exists
	   - the result is tied to a contract-relevant output, not only a proxy
	   - one quick sanity/benchmark/convention check passed
	   - if the plan is proof-bearing, `{plan_id}-PROOF-REDTEAM.md` exists and reports `status: passed`
	   - decisive anchors still missing were explicitly named and re-questioned if necessary
	   - if the contract owed a decisive comparison, either that comparison now has a pass verdict or the downstream work was explicitly scoped so it does not rely on that unresolved claim
	   - if `review_cadence=dense` and the just-completed first wave emitted no `result/produce` or `result/log` event at all, STOP and require explicit user confirmation before advancing — a dense wave that produced no result event is indistinguishable from a silent failure and the first-result gate never had anything to trip on

   If this gate fails: STOP — do not let wrong early assumptions scale out.

   **Machine-state requirement for risky fanout gates:** when this review point pauses execution, record it as live execution state, not only prose. Emit an execution gate event with:

	   - `checkpoint_reason: pre_fanout`
	   - `pre_fanout_review_pending: true`
	   - `downstream_locked: true`
	   - `last_result_label` or `last_artifact_path` for the first load-bearing output being reviewed
	   - `proof_redteam_required: true` and `proof_redteam_status` when the reviewed output is proof-bearing
	   - `skeptical_requestioning_required: true` when the first result still looks proxy-only, anchor-thin, or otherwise short of the decisive evidence the contract still owes
   - `skeptical_requestioning_summary`, `weakest_unchecked_anchor`, and `disconfirming_observation` whenever skeptical re-questioning is required
   - optional `tangent_summary` and `tangent_decision` when the same bounded stop surfaced an unexpected but non-blocking alternative path that still needs explicit handling

   If the runtime or agent only emits a fanout-lock event, normalize it into the same live review stop: treat the lock as `checkpoint_reason=pre_fanout`, mark `waiting_for_review=true`, and keep downstream locked until the review is explicitly cleared.

   Gate clears are reason-scoped: clearing `first_result` must not erase `pre_fanout` or skeptical review flags, and skeptical re-questioning should be cleared explicitly when it is resolved.

   For `pre_fanout`, the matching gate-clear and `fanout unlock` are separate transitions: the clear records the review outcome, the unlock releases downstream work. Keep the segment live on status, notify, and resume surfaces until both have been observed. Do not silently continue on "looks fine" prose alone.

   **Tangent proposals at the same stop:** if the first result suggests an unexpected but non-blocking alternative path, keep it inside the same review conversation rather than spawning extra work. Resolve it with one of:

   - `ignore` — continue mainline execution unchanged
   - `defer` — note it in outputs as future work and continue
   - `branch_later` — recommend an explicit `gpd:tangent ...` or `gpd:branch-hypothesis ...` follow-up after the bounded stop
   - `pursue_now` — only if the user explicitly asked for tangent exploration or the approved contract already covers it

   **Machine-state bridge for tangent proposals:** when a tangent proposal is relevant at this stop, keep it inside the same live execution payload instead of inventing a new tangent state machine. Emit:

   - `tangent_summary` — one short description of the alternative path
   - `tangent_decision` — one of `ignore | defer | branch_later | pursue_now` once classified

   Do not create a new branch, child plan, or side subagent from executor initiative alone. In `research_mode=exploit`, treat optional tangent proposals as suppressed unless explicit request overrides that default.

10. **Inter-wave verification gate (if more waves remain):**

   Before spawning the next wave, run lightweight verification on the just-completed wave's outputs. This catches errors cheaply before they propagate to downstream waves.

   **Determine if gate is enabled from init/context fields only:**

   - if `review_cadence == dense`: enable inter-wave verification
   - if `review_cadence == adaptive`: enable it when the completed wave established or challenged a decisive evidence path, introduced a new baseline/estimator that later waves depend on, or left any skeptical or pre-fanout state unresolved
   - if `review_cadence == sparse`: skip the routine gate unless the just-completed wave triggered a failed sanity check, anchor gap, or pre-fanout dependency warning

	   **If enabled:**

   First, collect the SUMMARY.md files produced by the just-completed wave from the phase index plan IDs. Only include summaries whose matching plan ran in the current wave.

   Run lightweight checks on the wave's SUMMARY.md outputs:

   a. **Convention consistency** — verify convention lock hasn't drifted:

   Run the convention check and warn if any required convention lock is incomplete.

   b. **Dimensional spot-check** — scan the wave's SUMMARY.md files for key results and verify dimensional consistency:

   For each SUMMARY.md produced in the just-completed wave, extract key equations (from `key_results` or `equations` frontmatter fields) and verify that:
   - Both sides of each equation have the same dimensions
   - Function arguments are dimensionless
   - No bare dimensionful quantities appear where dimensionless ones are expected

   This is a lightweight scan (~2-5k tokens), not a full dimensional analysis. It checks the SUMMARY outputs, not the derivation internals.

   c. **Unverified identity scan** — check for IDENTITY_CLAIM tags without verification:

   Inspect the current wave summaries and their surfaced durable artifact paths for `IDENTITY_SOURCE: training_data` claims that lack an `IDENTITY_VERIFIED` marker.

   Prefer paths surfaced through SUMMARY `key-files` or contract deliverables. Do not assume durable artifacts live beside the SUMMARY in `GPD/phases/**`.

   If unverified identities are found: flag as WARNING. These identities may be correct but have not been numerically tested — downstream waves building on them carry unquantified risk.

   d. **Computation-type-specific checks** (driven by `INTER_WAVE_CHECKS` from `adapt_to_computation_type`):

   **If `convergence_spot_check` in INTER_WAVE_CHECKS** (numerical phases):

   Scan the wave's SUMMARY.md files for convergence-related metrics. Look for keywords: `convergence`, `error`, `residual`, `tolerance`, `iterations`, `grid_size`. Flag if:
   - A convergence metric worsened compared to the previous wave's output
   - A residual exceeds 1e-3 without explicit justification
   - An iteration count hit a hard limit (suggests non-convergence)

   Extract convergence, residual, error, tolerance, iteration, and grid-size metrics from current wave summaries and flag worsening or unexplained high residuals.

   **If `plausibility_scan` in INTER_WAVE_CHECKS** (analysis/validation phases):

   Scan the wave's SUMMARY.md outputs for physically implausible values:
   - NaN or Inf in results
   - Negative values where positivity is expected (energies of bound states, probabilities, cross-sections)
   - Order-of-magnitude jumps (>10x) between related quantities in successive waves

   Inspect current wave summaries for NaN/Inf markers, divergent behavior, sign violations for positive quantities, and order-of-magnitude jumps.

   **If `latex_compile` in INTER_WAVE_CHECKS** (paper-writing phases):

   If `pdflatex` is available, compile the paper after each wave to catch LaTeX errors early:

   If a manuscript root has already been resolved for this workflow, bind it as `MANUSCRIPT_ROOT` before compiling from that root. Otherwise, resolve it locally from `paper/`, `manuscript/`, or `draft/` before checking for the manifest.

   If a compiler is available and the manuscript manifest exists, resolve the manifest-recorded TeX entrypoint with a structured JSON read, compile from the manuscript root, and surface the first LaTeX error lines as warnings.

   Flag any LaTeX errors as WARNING — they should be fixed before the next wave adds more content.

	   For proof-bearing waves, treat the proof-redteam artifact as part of this inter-wave gate even when the cadence would otherwise skip routine checks. Missing or open proof audits keep downstream work locked.

	   **If any check fails:**

   ```
   ---
   ## Inter-wave verification gate

   **Convention check:** {PASS | WARNING: {details}}
   **Dimensional check:** {PASS | WARNING: {details}}
   **Identity check:** {PASS | WARNING: {N} unverified training_data identities}
   **Convergence check:** {PASS | WARNING: {details} | SKIPPED (not numerical phase)}
   **Plausibility check:** {PASS | WARNING: {details} | SKIPPED (not analysis/validation phase)}
   **LaTeX compile:** {PASS | WARNING: {N} errors | SKIPPED (not paper-writing phase)}

   Options:
   1. Continue to next wave (accept warnings)
   2. Fix issues before continuing
   3. Stop execution and investigate
   ---
   ```

   Present options and wait for user response (or auto-continue in YOLO mode if both are warnings, not errors — unless `YOLO_RESTRICTIONS` includes `no_skip_inter_wave`, in which case always present).

   **If disabled:** Skip verification gate, proceed directly to step 11. Exception: if `YOLO_RESTRICTIONS` includes `no_skip_inter_wave`, the gate runs even when disabled by config.

   **Cost:** ~2-5k tokens per inter-wave gate. For a 4-wave phase with deep-theory profile, this is ~10-15k tokens overhead — negligible compared to the cost of a sign error propagating through 3 subsequent waves.

11. **Inter-wave transition display:**

   Before spawning the next wave, display a physics-meaningful progress update that connects what was just computed to what comes next:

   ```
   ---
   Wave {N} -> Wave {N+1} transition

   Completed: {brief physics summary of wave N results -- e.g., "Exact diagonalization of 2D Hubbard model for N=4,8,12 sites"}
   Enables: {what wave N+1 will use from these results -- e.g., "Finite-size scaling analysis using the energy spectra from Wave 1"}
   Starting: {brief description of wave N+1 plans -- e.g., "Extracting critical exponents via data collapse (plans 03, 04)"}
   ---
   ```

   Extract the "Completed" summary from the wave N completion report (step 6 above). Extract "Enables" and "Starting" from the wave N+1 plan objectives. Keep each line to one sentence.

12. **Proceed to next wave.**
   </step>

<step name="wave_failure_handling">
When a plan within a wave fails (spot-check failure, agent crash, or plan-level failure reported by execute-plan):

**1. Identify the failure and its downstream impact:**

Use the phase index dependency graph to list later-wave plans and identify every later plan that depends on `FAILED_PLAN_ID`. Keep the dependency analysis scoped to waves after the failed wave.

**2. Report failure with dependency analysis:**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 GPD > WAVE {N} FAILURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Failed plan:** {PLAN_ID} -- {plan name}
**Reason:** {failure description from spot-check or agent report}

### Wave {N} Status
| Plan | Status |
| ---- | ------ |
| {plan-A} | Passed |
| {plan-B} | FAILED |
| {plan-C} | Passed |

### Downstream Impact
Plans that depend on {FAILED_PLAN_ID} (will be auto-skipped):
{list of dependent plans with their wave numbers, or "None -- no downstream dependencies"}

──────────────────────────────────────────────────────
Options:
  1. "Rollback failed plan only" (preferred) -- revert only the commits from the failed plan
     using the TASK_COMMITS record. Keep all successful plans in this wave.
  2. "Continue" -- skip failed plan + dependents, execute remaining waves
  3. "Rollback wave" -- revert all wave {N} work to wave checkpoint
  4. "Stop" -- halt phase execution, preserve all completed work
──────────────────────────────────────────────────────
```

**3. Handle user choice:**

**Continue:**

- Mark the failed plan as skipped in the wave tracker
- Auto-skip all plans in `DEPENDENT_PLANS` in subsequent waves with message:

  ```
  Skipping {PLAN_ID}: depends on failed plan {FAILED_PLAN_ID}
  ```

- Track skipped plans in `SKIPPED_PLANS` array with reasons for the recovery report
- Proceed to next wave, filtering out dependent plans

**Rollback wave:**

- Revert to the wave checkpoint, then commit the rollback with phase, wave, failed plan, failure reason, and checkpoint tag in the message.

- Ask: "Retry wave {N}?" or "Stop execution?"
- If retry: re-enter the wave execution loop for wave N
- If stop: proceed to recovery report

**Stop:**

- Preserve all committed work
- Proceed directly to recovery report

**4. Auto-skip dependent plans during subsequent waves:**

When processing plans in waves N+1, N+2, etc., check each plan against the `SKIPPED_PLANS` list:

For each later wave plan, compare its indexed dependencies against `SKIPPED_PLANS`. If any dependency was skipped or failed, skip the current plan, record `depends_on_{dep_id}`, and continue with the next eligible plan.

> **Handoff verification:** Apply the local child artifact gate before success; git commits are partial evidence only.
</step>

<step name="checkpoint_handling">
Plans with `interactive: true` require user interaction.

```bash
CHECKPOINT_RESUME_INIT=$(load_execute_phase_stage checkpoint_resume) || { echo "ERROR: checkpoint_resume init failed"; exit 1; }
```

Use `gpd --raw stage field-access execute-phase --stage checkpoint_resume --style instruction` before reading `CHECKPOINT_RESUME_INIT`; do not reuse wave-dispatch fields here.

**Flow:**

1. Spawn agent for checkpoint plan
2. Agent runs until checkpoint task or validation gate -> returns structured state
3. Agent return includes completed tasks, current blocker, awaited item, and bounded execution segment; first-result/pre-fanout pauses add gate flags, skeptical re-questioning fields, and `downstream_locked`.
4. **Present to user:**

   ```
   ## Checkpoint: [Type]

   **Plan:** 03-03 Perturbation Expansion
   **Progress:** 2/3 tasks complete

   [Checkpoint Details from agent return]
   [Awaiting section from agent return]

   ## > Next Up

   `gpd:resume-work`

   Also available: `gpd:execute-phase {PHASE_NUMBER}` or `gpd:suggest-next`
   ```

5. User responds: "approved"/"done" | issue description | decision selection
6. **Spawn continuation agent (NOT resume)** using `{GPD_INSTALL_DIR}/templates/continuation-prompt.md` template:
   - `{completed_tasks_table}`: From checkpoint return
   - `{resume_task_number}` + `{resume_task_name}`: Current task
   - `{user_response}`: What user provided
   - `{resume_instructions}`: Based on checkpoint type (see template for type-specific instructions)
   - `{execution_segment}`: The returned bounded-segment state, including checkpoint cause, current cursor, resume preconditions, downstream-lock status, and any skeptical re-questioning fields that must survive into the continuation
   - `{selected_protocol_bundle_ids}`: From checkpoint_resume init JSON
   - `{protocol_bundle_load_manifest}`: From checkpoint_resume init JSON when present
   - `{protocol_bundle_context}`: From checkpoint_resume init JSON
   - `{protocol_bundle_verifier_extensions}`: From checkpoint_resume init JSON
7. Continuation agent verifies previous commits, continues from resume point
8. Repeat until plan completes or user stops

**Why fresh agent, not resume:** Resume relies on internal serialization that breaks with parallel tool calls. Fresh agents with explicit state are more reliable.

**Checkpoints in parallel waves:** Agent pauses and returns while other parallel agents may complete. Present checkpoint, spawn continuation, wait for all before next wave.
</step>

<step name="context_budget_check">
**Before aggregating results, estimate context consumption:**

Count the SUMMARY files that will be read and estimate their impact on orchestrator context using the summary-aggregation heuristic in `references/orchestration/context-budget.md`.

Estimate `SUMMARY_COUNT`, `ESTIMATED_TOKENS`, and `BUDGET_PERCENT` from the phase summaries using the context-budget heuristic.

If `BUDGET_PERCENT` exceeds 15%: warn before proceeding:

```
WARNING: Reading ${SUMMARY_COUNT} SUMMARY files will consume ~${BUDGET_PERCENT}% of orchestrator context.
Consider using summary-extract for one-liners only instead of full SUMMARY reads.
```

If >15%, use `summary-extract` for one-liners instead of reading full SUMMARY files:

If the budget warning fires, use `gpd summary-extract --field one_liner` for each summary instead of loading full summary bodies.
</step>

<step name="aggregate_results">
After all waves:

Load `load_execute_phase_stage aggregate_and_verify` and stop if the staged refresh fails.

Use `gpd --raw stage field-access execute-phase --stage aggregate_and_verify --style instruction` before reading `AGGREGATE_VERIFY_INIT`; aggregation and verification fields remain manifest-owned.

`AGGREGATE_VERIFY_INIT` includes `verification_report_skeleton_bridge` and `verification_report_finalizer_bridge`. Keep both bridge payloads visible through the verification handoff. Gap-only conservative reports use the skeleton bridge writer command; passed, human-needed, expert-needed, and typed non-gap outcomes use the finalizer bridge writer command template with `PATCH.json` plus body-only `BODY.md`. Do not hand-author `VERIFICATION.md` YAML in this workflow.

```markdown
## Phase {X}: {Name} Execution Complete

**Waves:** {N} | **Plans:** {M}/{total} complete

| Wave | Plans            | Status   |
| ---- | ---------------- | -------- |
| 1    | plan-01, plan-02 | Complete |
| CP   | plan-03          | Verified |
| 2    | plan-04          | Complete |

### Plan Details

1. **03-01**: [one-liner from SUMMARY.md]
2. **03-02**: [one-liner from SUMMARY.md]

### Validation Summary

[Aggregate limiting case checks, dimensional consistency results, cross-checks]

### Issues Encountered

[Aggregate from SUMMARYs, or "None"]
```

</step>

<step name="generate_figure_tracker">
**After all waves complete successfully, inventory generated figures/plots into FIGURE_TRACKER.md:**

Scan all SUMMARY.md files from this phase for figure-related artifacts:

Inspect summary `key-files.created` entries and durable figure roots for generated PDF, PNG, EPS, SVG, JPEG, or TIFF artifacts whose names indicate figures, plots, spectra, convergence, or diagrams.

Generated figures and plots should live in stable workspace roots such as `artifacts/phases/${phase_number}-${phase_slug}/`, `figures/`, or `paper/figures/`, not under `GPD/phases/**`.

**If any figures found:**

Read the figure tracker template from `{GPD_INSTALL_DIR}/templates/paper/figure-tracker.md` using the runtime's normal file-read mechanism.

**If `paper/FIGURE_TRACKER.md` already exists:** Append new figures to the existing registry. Do not overwrite existing entries.

**If it does not exist:** Create it from the template:

Ensure `paper/` exists before writing the tracker.

Write `paper/FIGURE_TRACKER.md` with:

- One entry per discovered figure/plot
- `Source phase` set to the current phase number
- `Source file` set to the script or notebook that generated it (from SUMMARY key-files)
- `Data file(s)` set to any associated data files (from SUMMARY key-files)
- `Status` set to "Data ready" or "Draft" based on file inspection
- `Last updated` set to today's date

Commit:

Run pre-commit checking for `paper/FIGURE_TRACKER.md`, then commit it with a phase-scoped figure-tracker message.

**If no figures found:** Skip silently (not all phases produce visual outputs).

**Experimental comparison artifact:** If any plan in this phase compared theoretical predictions with experimental or observational data (PHENO-type objectives, or plans whose SUMMARY mentions "experimental comparison", "pull", "chi-squared", or "theory vs data"), create `paper/EXPERIMENTAL_COMPARISON.md` using `{GPD_INSTALL_DIR}/templates/paper/experimental-comparison.md`. Populate with comparison tables, pull values, and discrepancy classifications from the plan SUMMARYs. Skip if no experimental comparison was performed.

</step>

<step name="recovery_report">
**After all waves complete (including any failures, skips, or rollbacks), generate a recovery report.**

This step runs unconditionally -- for fully successful phases it is a brief confirmation; for phases with failures it is the critical decision point.

**1. Collect execution outcomes:**

Build recovery outcome lists from the phase index, current summary artifacts, and the orchestrator's maintained failed/skipped records. Track succeeded, failed, skipped, and rolled-back plan IDs with reasons; do not infer success from a previous summary alone when spot-checks failed.

**2. Present recovery report:**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 GPD > PHASE {X} EXECUTION REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### Results

| Plan | Status | Detail |
| ---- | ------ | ------ |
| {id} | Passed | {one-liner from SUMMARY} |
| {id} | FAILED | {failure reason} |
| {id} | Skipped | Depends on failed {dep_id} |

**Summary:** {succeeded_count} passed, {failed_count} failed, {skipped_count} skipped
```

**3. If ALL plans passed:** Proceed to `verify_phase_goal` as normal. Report is informational only.

**4. If ANY failures or skips occurred:**

Create a recovery section in the phase directory. For physics-specific root cause analysis, consult `{GPD_INSTALL_DIR}/templates/recovery-plan.md`:

```bash
RECOVERY_FILE="${phase_dir}/PHASE-RECOVERY.md"
```

Write `PHASE-RECOVERY.md`:

```markdown
---
phase: { PHASE_NUMBER }
phase_name: { PHASE_NAME }
created: { ISO timestamp }
plans_succeeded: [{ list }]
plans_failed: [{ list }]
plans_skipped: [{ list }]
checkpoint_tags: [{ list of all remaining gpd-checkpoint tags for this phase }]
---

# Phase {X} Recovery

## Execution Summary

{succeeded_count}/{total_count} plans completed successfully.

## Failed Plans

### {PLAN_ID}: {plan name}

- **Failed at:** Task {N} -- {task name}
- **Reason:** {detailed failure reason}
- **Checkpoint:** {checkpoint tag, if preserved}
- **Recovery:** See RECOVERY-{PLAN}.md (created by execute-plan)

## Skipped Plans

### {PLAN_ID}: {plan name}

- **Skipped because:** Depends on failed plan {dep_id}
- **Would have computed:** {objective from PLAN.md}

## Recovery Options

1. Fix failing plans and re-execute: `gpd:execute-phase {X}` (auto-detects partial completion)
2. Re-plan failed tasks: `gpd:plan-phase {X} --gaps` (creates new plans for unfinished work)
3. Revise phase goal: `gpd:discuss-phase {X}` (rethink approach based on what failed)
4. Continue to next phase: `gpd:plan-phase {X+1}` (if remaining work is non-critical)
```

Commit the recovery document after pre-commit checking `${RECOVERY_FILE}` and `GPD/STATE.md`.

**5. Offer actionable next steps based on failure pattern:**

```
──────────────────────────────────────────────────────
## Next Steps

{If single plan failed, rest passed:}
  The failure is isolated. Fix and re-execute:
  `gpd:execute-phase {X}` -- will resume from the failed plan

{If multiple plans failed in same wave:}
  Multiple failures in Wave {N} suggest a systemic issue.
  Review the phase approach before retrying:
  `gpd:discuss-phase {X}` -- reassess methodology

{If failures cascaded through dependencies:}
  The root failure in {ROOT_PLAN} cascaded to {N} dependent plans.
  Fix the root cause first:
  Review: ${phase_dir}/RECOVERY-{ROOT_PLAN}.md

{If all plans failed:}
  Complete phase failure. The phase goal or approach may need revision:
  `gpd:plan-phase {X}` -- re-plan from scratch
──────────────────────────────────────────────────────
```

</step>

<step name="verify_phase_goal">
**If `verifier_enabled` is false** (from init JSON config / `workflow.verifier` in config.json): Skip only the generic post-execution verifier for non-proof phases. If any executed plan is proof-bearing, proof verification still runs and missing/open `*-PROOF-REDTEAM.md` artifacts keep the phase fail-closed. Log the distinction explicitly instead of treating verifier-disabled config as a blanket bypass.

Verify phase achieved its GOAL, not just completed tasks.

**Phase-class-aware verification:** Pass the phase classification from `classify_phase` so the verifier prioritizes checks: derivation -> dimensional/numerical spot/limit/identity checks; numerical -> convergence, statistical validation, spot checks, decisive benchmarks; formalism -> dimensional, limiting, Ward/sum-rule, literature checks; validation -> full relevant universal registry plus contract-aware checks; analysis -> order-of-magnitude, plausibility, literature, and fit/estimator checks.

Include in the verifier spawn prompt: `<phase_class>{PHASE_CLASSES}</phase_class>` so the verifier can adjust its check prioritization.

Spawn `gpd-verifier` in a fresh context; the child reads `{GPD_INSTALL_DIR}/workflows/verify-phase.md`.

> Apply the canonical runtime delegation convention above.

```
VERIFIER_HANDOFF_STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
task(
  subagent_type="gpd-verifier",
  model="{verifier_model}",
  readonly=false,
  prompt="First, read {GPD_AGENTS_DIR}/gpd-verifier.md for your role and instructions.

Verify Phase {PHASE_NUMBER} against its phase goal and plan contracts.

<phase_class>{PHASE_CLASSES}</phase_class>

<selected_protocol_bundle_ids>{selected_protocol_bundle_ids}</selected_protocol_bundle_ids>
<protocol_bundle_load_manifest>{protocol_bundle_load_manifest}</protocol_bundle_load_manifest>
<protocol_bundle_context>{protocol_bundle_context}</protocol_bundle_context>
<protocol_bundle_verifier_extensions>{protocol_bundle_verifier_extensions}</protocol_bundle_verifier_extensions>

Load before verdict:
- {GPD_INSTALL_DIR}/workflows/verify-phase.md
- verification_report_skeleton_bridge from AGGREGATE_VERIFY_INIT
- verification_report_finalizer_bridge from AGGREGATE_VERIFY_INIT
- {GPD_INSTALL_DIR}/templates/verification-report.md only if a helper or validator reports a schema issue
- {GPD_INSTALL_DIR}/templates/contract-results-schema.md only if a helper or validator reports a schema issue

<files_to_read>
- Phase plans and summaries: {phase_dir}
- Roadmap: GPD/ROADMAP.md
- State: GPD/STATE.md and GPD/state.json
</files_to_read>

Run `gpd --raw init phase-op {PHASE_NUMBER}` and keep the project contract, reference/protocol context, protocol bundle verifier extensions, and `phase_proof_review_status` visible. Stable knowledge docs surfaced there are background only.

Write to: {phase_dir}/{phase_number}-VERIFICATION.md through the verification-report skeleton/finalizer bridge. Do not hand-author or reflow the verification frontmatter YAML.

<spawn_contract>
write_scope:
  mode: scoped_write
  allowed_paths:
    - "{phase_dir}/{phase_number}-VERIFICATION.md"
expected_artifacts:
  - "{phase_dir}/{phase_number}-VERIFICATION.md"
shared_state_policy: return_only
</spawn_contract>

Return one typed `gpd_return` envelope with `status`, the written report path, and canonical `verification_status` (`passed | gaps_found | expert_needed | human_needed`). The report is acceptable only after the bridge writer/finalizer reports validation success and `gpd validate verification-contract {phase_dir}/{phase_number}-VERIFICATION.md` passes.",
  description="Verify Phase {PHASE_NUMBER} goal"
)
```

Post-execution verifier child artifact gate: apply `references/orchestration/child-artifact-gate.md`; scientific status routing applies `references/verification/verification-status-authority.md`; checkpoint handling applies `references/orchestration/continuation-boundary.md`.

```yaml
child_gate:
  id: "post_execution_verifier"
  role: "gpd-verifier"
  return_profile: "verifier"
  required_status: "completed"
  expected_artifacts:
    - "{phase_dir}/{phase_number}-VERIFICATION.md"
  allowed_roots:
    - "{phase_dir}"
  freshness_marker: "after $VERIFIER_HANDOFF_STARTED_AT"
  validators:
    - "gpd validate handoff-artifacts - --expected '{phase_dir}/{phase_number}-VERIFICATION.md' --allowed-root '{phase_dir}' --required-suffix=-VERIFICATION.md --require-status completed --require-files-written --fresh-after \"$VERIFIER_HANDOFF_STARTED_AT\""
    - "gpd validate verification-contract {phase_dir}/{phase_number}-VERIFICATION.md"
    - "verification-status-authority.md status rules"
    - "proof-redteam status: passed for proof-bearing work"
  applicator:
    command: "phase closeout/update_roadmap only after verifier gate and status route"
    require_passed_true: false
  failure_route: "route_to_gpd_verify_work | repair_prompt_once | retry_once_then_gpd_verify_work | repair_path_once | fail_closed"
```

Verifier status route: gaps found -> `gpd:plan-phase {phase} --gaps`; human/expert-needed -> present or escalate review.

Read status after the verifier tuple passes: use `gpd_return.status` plus the validated frontmatter; do not route on headings or marker strings.

| Status         | Action                                                      |
| -------------- | ----------------------------------------------------------- |
| `passed`       | -> update_roadmap                                           |
| `human_needed`  | Present items for human review, get approval or feedback    |
| `expert_needed` | Domain expert review required; present items, escalate      |
| `gaps_found`    | Present gap summary, offer `gpd:plan-phase {phase} --gaps` |

If the same report also carries `session_status: validating|completed|diagnosed`, treat that as conversational progress only. It does not replace the canonical verification `status` read above. A diagnosed verification session will normally still report `status: gaps_found` until the fixes are re-verified.

**If human_needed:**

```
## Phase {X}: {Name} -- Human Verification Required

All automated checks passed. {N} items need human review:

{From VERIFICATION.md human_verification section}

"approved" -> continue | Report issues -> gap closure
```

**If gaps_found:**

```
## Phase {X}: {Name} -- Gaps Found

**Score:** {N}/{M} contract targets verified
**Report:** {phase_dir}/{phase}-VERIFICATION.md

### What's Missing
{Gap summaries from VERIFICATION.md}

### Physics Issues
{Any dimensional inconsistencies, failed limiting cases, or conservation law violations}

---
## > Next Up

`gpd:plan-phase {X} --gaps`

<sub>Start a fresh context window</sub>

Also: `cat {phase_dir}/{phase}-VERIFICATION.md` -- full report
Also: `gpd:verify-work {X}` -- manual review first
```

Gap closure cycle: `gpd:plan-phase {X} --gaps` reads VERIFICATION.md -> creates gap plans with `gap_closure: true` -> user runs `gpd:execute-phase {X} --gaps-only` -> automatic re-verification (below).

**Smart failure recovery (replaces blunt circuit breaker):**

Before triggering gap closure, classify the failure to select the minimum-cost recovery strategy. See `agent-infrastructure.md` Meta-Orchestration Intelligence > Feedback Loop Intelligence for the full classification table.

```bash
# Count only top-level verification outcomes. Nested contract-results and gap
# ledgers also have `status:` fields, so unanchored grep would overcount them.
FAILED_COUNT=$(rg -c '^status: (gaps_found|expert_needed|human_needed)$' "${phase_dir}"/*-VERIFICATION.md 2>/dev/null | awk -F: '{sum += $2} END {print sum+0}')
TOTAL_COUNT=$(rg -c '^status: (passed|gaps_found|expert_needed|human_needed)$' "${phase_dir}"/*-VERIFICATION.md 2>/dev/null | awk -F: '{sum += $2} END {print sum+0}')
```

| Failure Pattern | Recovery | Cost |
|---|---|---|
| 1 contract target failed, rest passed | Re-execute the specific failing plan only | 1 subagent |
| Multiple failures, same error type (e.g., all sign errors) | Stop and route through `gpd:validate-conventions`; repair happens in a fresh continuation before re-execution | validate + follow-up |
| Multiple failures, different error types | Escalate to user -- approach may be fundamentally wrong | 0 (user decides) |
| Same gap persists after 1 gap-closure | Spawn debugger to identify root cause before 2nd attempt | 1-2 subagents |

**For localized failures (1 contract target):** Skip full gap-closure planning. Instead, directly re-execute the single plan that produced the failed result with explicit error context:

> Apply the canonical runtime delegation convention above.

```
task(
  subagent_type="gpd-executor",
  model="{executor_model}",
  readonly=false,
  prompt="First, read {GPD_AGENTS_DIR}/gpd-executor.md for your role and instructions.

  Re-execute plan {FAILED_PLAN} with focus on fixing: {FAILURE_DESCRIPTION}.
  The verifier found: {VERIFICATION_DETAIL}.
  Read the original SUMMARY.md for what was attempted. Fix the specific error.

  <context_hint>{EXECUTOR_CONTEXT_HINT}</context_hint>
  <phase_class>{PHASE_CLASSES}</phase_class>
  <selected_protocol_bundle_ids>{selected_protocol_bundle_ids}</selected_protocol_bundle_ids>
  <protocol_bundle_load_manifest>{protocol_bundle_load_manifest}</protocol_bundle_load_manifest>
  <protocol_bundle_context>{protocol_bundle_context}</protocol_bundle_context>
  <protocol_bundle_verifier_extensions>{protocol_bundle_verifier_extensions}</protocol_bundle_verifier_extensions>

  <files_to_read>
  - Workflow: {GPD_INSTALL_DIR}/workflows/execute-plan.md
  - Plan: {phase_dir}/{FAILED_PLAN}-PLAN.md
  - Previous SUMMARY: {phase_dir}/{FAILED_PLAN}-SUMMARY.md
  - State: GPD/STATE.md
  </files_to_read>",
  description="Targeted re-execution of {FAILED_PLAN}"
)
```

**For systematic failures:** Do not route notation repair inline from this workflow. Stop and point the user to `gpd:validate-conventions`; if convention repair is needed, that workflow and the fresh continuation handoff own the `gpd-notation-coordinator` spawn and typed return routing. After conventions are validated, re-enter `gpd:execute-phase {X}` or `gpd:execute-phase {X} --gaps-only` as appropriate.

**For persistent failures (same gap after 1 cycle):** Spawn debugger BEFORE the second gap-closure attempt:

```bash
DEBUGGER_MODEL=$(gpd resolve-model gpd-debugger)
```

> Apply the canonical runtime delegation convention above.

```
task(
  subagent_type="gpd-debugger",
  model="{debugger_model}",
  readonly=false,
  prompt="First, read {GPD_AGENTS_DIR}/gpd-debugger.md for your role and instructions.

  Use {GPD_INSTALL_DIR}/templates/debug-subagent-prompt.md as the explicit one-shot debug contract. Populate it from the failed verification file, the gap-closure summary, and the original summary; set `goal: find_root_cause_only`, `symptoms_prefilled: true`, and `Create: GPD/debug/{FAILED_PLAN}.md`.

  Return exactly one typed `gpd_return` envelope with `status: completed | checkpoint | blocked | failed`, include the session file, and stop. Do not route on heading markers or continue the investigation interactively inside the child.",
  description="Diagnose persistent verification failure"
)
```

**Circuit breaker (hard stop): Maximum 2 verification-gap closure cycles.** After 2 failed verification cycles (with debugger diagnosis on the second), STOP the loop. Present a diagnostic summary to the user:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 GPD > CIRCUIT BREAKER: VERIFICATION LOOP HALTED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Phase {X} has failed verification twice after gap closure attempts.

### Attempt 1
- Gaps found: {list from first VERIFICATION.md}
- Gap closure plans: {list of plans created}
- Re-verification result: {what still failed}

### Attempt 2
- Remaining gaps: {list from second VERIFICATION.md}
- Gap closure plans: {list of plans created}
- Re-verification result: {what still failed}

### Root Cause Hypothesis
{System's best hypothesis for why gap closure is not resolving the issue}

### Suggested Actions
1. `gpd:debug` — Systematic investigation of the persistent failure
2. `gpd:discuss-phase {X}` — Reassess the approach with fresh perspective
3. Manual intervention — The issue may require researcher insight

Do NOT attempt a third automated cycle.
```

**After gap closure execution completes (`$GAPS_ONLY` is true):**

Automatically re-verify the phase to confirm gaps are closed:

```bash
VERIFIER_MODEL=$(gpd resolve-model gpd-verifier)
```

> Apply the canonical runtime delegation convention above.

```
REVERIFY_HANDOFF_STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
task(
  subagent_type="gpd-verifier",
  model="{verifier_model}",
  readonly=false,
 prompt="First, read {GPD_AGENTS_DIR}/gpd-verifier.md for your role and instructions.

Reload these canonical verifier surfaces before updating any verdicts:
- {GPD_INSTALL_DIR}/workflows/verify-phase.md
- {GPD_INSTALL_DIR}/templates/verification-report.md
- {GPD_INSTALL_DIR}/templates/contract-results-schema.md

Treat `VERIFICATION.md` as contract-backed only through the schema-owned ledgers `plan_contract_ref`, `contract_results`, `comparison_verdicts`, and `suggested_contract_checks`; do not expect verifier-local aliases or ad hoc machine-readable artifact fields.

Re-verify Phase {PHASE_NUMBER} after gap closure.

<phase_class>{PHASE_CLASSES}</phase_class>

	<files_to_read>
	Read these files using the file_read tool:
	- Verification: {phase_dir}/{phase}-VERIFICATION.md
	- All SUMMARY.md files in {phase_dir}/
	- All `*-PROOF-REDTEAM.md` files in {phase_dir}/
	- State: GPD/STATE.md
	- Roadmap: GPD/ROADMAP.md
	</files_to_read>

	Rebuild the structured phase context with `gpd --raw init phase-op {PHASE_NUMBER}` and keep `project_contract`, `project_contract_gate`, `contract_intake`, `effective_reference_intake`, `active_reference_context`, `reference_artifacts_content`, `selected_protocol_bundle_ids`, `protocol_bundle_load_manifest`, `protocol_bundle_context`, `protocol_bundle_verifier_extensions`, and `phase_proof_review_status` visible while re-checking the remaining gaps. Treat any stable knowledge docs surfaced in those fields as reviewed background only: they may inform interpretation, but they do not override the contract, proof audits, or decisive evidence.

	Focus on the gaps that were previously marked failed, partial, blocked, or otherwise unresolved in the previous verification. If the prior report carries `session_status: diagnosed`, use the recorded root causes and missing actions as the starting point for re-verification. For proof-bearing work, re-check every required `*-PROOF-REDTEAM.md` artifact and keep the phase blocked until those audits report `status: passed`.
	Check whether the gap closure plans have resolved each issue.
	Update VERIFICATION.md with new status for each gap.
	Return exactly one typed `gpd_return` envelope with `status: completed | checkpoint | blocked | failed`, include `files_written`, and write `{phase_dir}/{phase}-VERIFICATION.md` before returning. Use the verifier's canonical `verification_status: passed | gaps_found | expert_needed | human_needed` inside the structured return or the written report; do not return bare `passed | gaps_found` text as the routing surface.",
  description="Re-verify Phase {PHASE_NUMBER} after gap closure"
)
```

Gap re-verifier child artifact gate: apply `references/orchestration/child-artifact-gate.md`; scientific status routing applies `references/verification/verification-status-authority.md`; checkpoint handling applies `references/orchestration/continuation-boundary.md`.

```yaml
child_gate:
  id: "gap_closure_reverification"
  role: "gpd-verifier"
  return_profile: "verifier"
  required_status: "completed"
  expected_artifacts:
    - "{phase_dir}/{phase}-VERIFICATION.md"
  allowed_roots:
    - "{phase_dir}"
  freshness_marker: "after $REVERIFY_HANDOFF_STARTED_AT"
  validators:
    - "gpd validate handoff-artifacts - --expected '{phase_dir}/{phase}-VERIFICATION.md' --allowed-root '{phase_dir}' --required-suffix=-VERIFICATION.md --require-status completed --require-files-written --fresh-after \"$REVERIFY_HANDOFF_STARTED_AT\""
    - "gpd validate verification-contract {phase_dir}/{phase}-VERIFICATION.md"
    - "verification-status-authority.md status rules"
    - "proof-redteam status: passed for proof-bearing work"
  applicator:
    command: "mark phase complete/update_roadmap only after verifier gate and passed verdict"
    require_passed_true: false
  failure_route: "blocked -> gpd:verify-work {PHASE_NUMBER} | repair_prompt_once | retry_once_then_verify_work"
```

Verifier status route: passed verdict updates roadmap; non-passing verdict reports remaining gaps without auto-looping.

Spawn/error, malformed output, failed tuple, or non-passing verifier verdict keeps gap-closure state intact and routes to `gpd:verify-work {PHASE_NUMBER}` or the listed gap commands; do not mark the phase complete on those paths.

</step>

<step name="rapid_consistency_check">
Run a rapid cross-phase consistency check to catch convention violations and sign errors before they propagate to future phases.

Resolve consistency checker model:

```bash
CONSISTENCY_MODEL=$(gpd resolve-model gpd-consistency-checker)
```

Spawn the consistency checker in rapid mode:

> Apply the canonical runtime delegation convention above.

CONSISTENCY_HANDOFF_STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
CONSISTENCY_RETURN=$(
task(prompt="First, read {GPD_AGENTS_DIR}/gpd-consistency-checker.md for your role and instructions.

<mode>rapid</mode>
<phase>{PHASE_NUMBER}</phase>

<spawn_contract>
write_scope:
  mode: scoped_write
  allowed_paths:
    - "{phase_dir}/CONSISTENCY-CHECK.md"
expected_artifacts:
  - "{phase_dir}/CONSISTENCY-CHECK.md"
shared_state_policy: return_only
</spawn_contract>

Check phase {PHASE_NUMBER} results against the full conventions ledger and all accumulated project state.
Use the structured init-state payload (`convention_lock` / `derived_convention_lock`) and SUMMARY.md frontmatter convention fields first.
Use `gpd convention list` and `file_read: GPD/STATE.md, GPD/state.json` only if the payload is missing or inconsistent.
file_read: All SUMMARY.md files from phase {PHASE_NUMBER}

Return exactly one typed `gpd_return` envelope, include `files_written`, and write `{phase_dir}/CONSISTENCY-CHECK.md`. Append the same typed YAML `gpd_return` block to `{phase_dir}/CONSISTENCY-CHECK.md` before returning so the canonical artifact gate can validate the durable handoff from the artifact itself.
", subagent_type="gpd-consistency-checker", model="{consistency_model}", readonly=false, description="Rapid consistency check")
)

**Consistency checker child artifact gate:** apply `references/orchestration/child-artifact-gate.md`; checkpoint handling applies `references/orchestration/continuation-boundary.md`.

```yaml
child_gate:
  id: "rapid_consistency_check"
  role: "gpd-consistency-checker"
  return_profile: "consistency_checker"
  required_status: "completed"
  expected_artifacts:
    - "{phase_dir}/CONSISTENCY-CHECK.md"
  allowed_roots:
    - "{phase_dir}"
  freshness_marker: "after $CONSISTENCY_HANDOFF_STARTED_AT"
  validators:
    - "gpd validate handoff-artifacts - --expected {phase_dir}/CONSISTENCY-CHECK.md --allowed-root {phase_dir} --required-suffix=CONSISTENCY-CHECK.md --require-status completed --require-files-written --fresh-after \"$CONSISTENCY_HANDOFF_STARTED_AT\""
    - "readable artifact check"
  applicator: none
  failure_route: "blocked -> gpd:validate-conventions | repair_prompt_once | retry_fresh_execute_continuation | retry_once"
```

```bash
CONSISTENCY_REPORT="${phase_dir}/CONSISTENCY-CHECK.md"
if [ ! -r "$CONSISTENCY_REPORT" ]; then
  echo "ERROR: consistency-check artifact missing: $CONSISTENCY_REPORT"
  exit 1
fi
printf '%s\n' "$CONSISTENCY_RETURN" | gpd validate handoff-artifacts - \
  --expected "$CONSISTENCY_REPORT" \
  --allowed-root "${phase_dir}" \
  --required-suffix=CONSISTENCY-CHECK.md \
  --require-files-written \
  --require-status completed \
  --fresh-after "$CONSISTENCY_HANDOFF_STARTED_AT" || exit 1
```

**If the consistency checker agent fails to spawn or returns an error:** Treat the consistency check as blocked. Do not proceed as if the phase was checked. End with `## > Next Up`: primary `gpd:validate-conventions`, plus `gpd:resume-work`, `gpd:execute-phase {PHASE_NUMBER}`, and `gpd:suggest-next`.

**Handle the checker response through `gpd_return.status`:**
- `gpd_return.status: completed`: accept only if the consistency checker gate passes. Surface any `issues` as warnings, then continue.
- `gpd_return.status: checkpoint`: stop, surface the checkpoint payload from the checker, and end with `## > Next Up`: primary `gpd:resume-work`, plus `gpd:validate-conventions` and `gpd:suggest-next`. Do not wait in place for user input inside this run.
- `gpd_return.status: blocked` / `gpd_return.status: failed`: stop execution, surface the returned issues, and end with `## > Next Up`: primary `gpd:validate-conventions`, plus `gpd:resume-work` and `gpd:suggest-next`. If the user wants convention repair, route through `gpd:validate-conventions`; the fresh continuation handoff owns any notation-coordinator work.

**If the checker output is malformed or omits `gpd_return.status`:** Treat it as blocked. Do not infer success from prose headings or untyped routing. Do not hand-author or paste a synthetic `gpd_return` into an already-returned report in the orchestrator; retry or repair the checker handoff so the child owns the typed envelope.

Convention repair is intentionally out-of-line here. Do not spawn `gpd-notation-coordinator` from `execute-phase`, do not route on checker-local prose markers, and do not accept a stale convention document as proof of repair. The next step is `gpd:validate-conventions`, followed by `gpd:resume-work` or a fresh `gpd:execute-phase {PHASE_NUMBER}` continuation after that workflow reports a typed result and the convention lock is valid.

**If "Force continue":** Log the forced override to DECISIONS.md:

```bash
gpd state add-decision \
  --phase "${phase_number}" \
  --summary "Forced past consistency check (--force-inconsistent)" \
  --rationale "${USER_RATIONALE}"
```

**If `gpd_return.status: completed`:** Continue to phase completion.
</step>

<step name="orchestrator_self_check">

Before marking complete, verify VERIFICATION.md lists attack vectors, limiting cases, and literature cross-references. If no issues appeared, run one targeted check on the most load-bearing result.

</step>

<step name="update_roadmap">
Mark phase complete in ROADMAP.md (date, status).

```bash
CLOSEOUT_INIT=$(load_execute_phase_stage closeout) || { echo "ERROR: closeout init failed"; exit 1; }
CLOSEOUT_READINESS=$(gpd --raw phase closeout-readiness "${phase_number}" --require-verification)
if [ $? -ne 0 ]; then
  echo "$CLOSEOUT_READINESS"
  exit 1
fi
gpd phase complete "${phase_number}"
```

Use `gpd --raw stage field-access execute-phase --stage closeout --style instruction` before reading `CLOSEOUT_INIT`; closeout fields remain scoped to the manifest-selected payload.

Follow `{GPD_INSTALL_DIR}/workflows/transition.md` for PROJECT.md, DECISIONS.md, and parallel phase detection. Pre-check and commit `GPD/ROADMAP.md`, `GPD/STATE.md`, the phase verification artifacts, and `GPD/REQUIREMENTS.md` with a phase-completion message.

</step>

<step name="cleanup_phase_checkpoints">
**After successful phase completion (all plans passed + verification passed):**

Ask the helper to remove only helper-owned checkpoint tags for this phase. The helper preserves tags when closeout readiness reports blockers, recovery artifacts, or a preservation policy.

Run `gpd --raw phase checkpoint cleanup --phase "${phase_number}" --namespace phase --policy successful-closeout`. If it exits nonzero, print the helper JSON and stop; otherwise surface the helper JSON in the closeout notes.

**If there were ANY failures during the phase** (even if subsequently resolved via re-execution), keep all checkpoint tags. They provide audit trail and enable future rollback if issues surface later.

**Decision logic:**

| Condition                               | Action                                             |
| --------------------------------------- | -------------------------------------------------- |
| All plans passed + verification passed  | Delete all `gpd-checkpoint-phase-{X}-*` tags       |
| Any plans failed (even if kept partial) | Keep all checkpoint tags                           |
| Verification found gaps                 | Keep all checkpoint tags                           |
| Phase marked complete after gap closure | Delete checkpoint tags from successful re-run only |

</step>

<step name="offer_next">

<continuation_routing>
After phase completion, check the project's autonomy mode. If yolo or balanced with no pending checkpoint, auto-route to the next phase. If supervised, or if a checkpoint requires review, pause with a clear status message showing: current phase completed, why execution paused, exact next command to continue, and key artifacts to review. See `{GPD_INSTALL_DIR}/references/orchestration/continuous-execution.md` for the standard checkpoint protocol.
</continuation_routing>

Never end with only "ready to plan/continue" prose. After a successful closeout, choose exactly one matching variant and emit a `Next Up` block with concrete commands; do not print conditional "if context is missing/exists" labels in the final answer.

- If the next phase has no `*-CONTEXT.md`, make `gpd:discuss-phase {X+1}` the primary command and show `gpd:plan-phase {X+1}` as the direct-plan alternative.
- If the next phase already has context, make `gpd:plan-phase {X+1}` the primary command.
- Always include `gpd:suggest-next` as the shortest recovery/confirmation command when the user only wants the next action.

**If more phases:**

```
## > Next Up

**Phase {X+1}: {Name}** -- {Goal}

Primary: `{chosen primary command}`

**Also available:**
- `{secondary command}` -- when relevant
- `gpd:suggest-next` -- confirm the next action

<sub>Start a fresh context window, then run the primary command above.</sub>
```

**If milestone complete:**

```
MILESTONE COMPLETE!

All {N} phases executed.

`gpd:complete-milestone`

**Also available:** `gpd:suggest-next`

<sub>Start a fresh context window, then run `gpd:complete-milestone`.</sub>
```

</step>

</process>

<context_efficiency>
Orchestrator stays lean per `references/orchestration/context-budget.md`; subagents get fresh contexts. No polling (Task blocks). No context bleed.
</context_efficiency>

<failure_handling>

- **False failure report despite delivered work:** Use the `wave_executor_plan_result` child_gate failure route; files and commits stay recovery evidence until that tuple passes.
- **Agent fails mid-plan:** Missing SUMMARY.md -> report, route to wave_failure_handling for user decision
- **Dependency chain breaks:** Wave N plan fails -> identify Wave N+1 dependents via `depends_on` frontmatter -> auto-skip with clear message -> user chooses at wave level
- **All agents in wave fail:** Systemic issue -> stop, report for investigation, offer wave-level rollback
- **Checkpoint unresolvable:** "Skip this plan?" or "Abort phase execution?" -> record partial progress in STATE.md
- **Physics validation failure:** Dimensional inconsistency or conservation law violation detected -> STOP, do not proceed to next wave, report for investigation
  </failure_handling>

<resumption>
Re-run `gpd:execute-phase {phase}` -> discover_plans finds completed SUMMARYs -> skips them -> resumes from first incomplete plan -> continues wave execution.

STATE.md tracks: last completed plan, current wave, pending checkpoints.

**Partial completion detection:** execute-plan's `detect_previous_attempt` step checks git log for task-level commits. Plans with partial commits offer resume-from-task-N. Plans with RECOVERY-{PLAN}.md files surface recovery options.
</resumption>
