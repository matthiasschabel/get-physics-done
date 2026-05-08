<purpose>
Dispatch wave executors, handle proof critics, enforce child artifact gates, and route wave failures.
</purpose>

<stage_boundary>
This stage is the first execute-plan/runtime-delegation authority. It owns task handoffs, wave checkpoints, child-return acceptance, proof critic dispatch, inter-wave gates, and wave-level failure handling.
</stage_boundary>

<process>

<step name="execute_waves">
Execute each wave in sequence. Within a wave: parallel if `PARALLELIZATION=true` AND `FORCE_SEQUENTIAL=false`, sequential otherwise. (Literature phases force sequential execution — see `adapt_to_computation_type`.)

Refresh the wave-dispatch stage immediately before spawning executors so plan execution sees only the late-loaded context it actually needs:

```bash
WAVE_DISPATCH_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage wave_dispatch)
if [ $? -ne 0 ] || [ -z "$WAVE_DISPATCH_INIT" ]; then
  echo "ERROR: wave-dispatch stage refresh failed: $WAVE_DISPATCH_INIT"
  exit 1
fi
```

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

   After verifying wave completion, collect the artifacts from each plan's SUMMARY.md (`key-files.created`, `key-files.modified`) and emit a compact summary with review priorities. See `{GPD_INSTALL_DIR}/references/orchestration/artifact-surfacing.md` for artifact class definitions and review priority rules.

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

</process>
