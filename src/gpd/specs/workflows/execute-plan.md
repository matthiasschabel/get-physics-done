<purpose>
Execute a research plan (`PLAN.md` or `*-PLAN.md`) -- carry out derivations, calculations, simulations, or analysis -- and create the matching outcome summary (`SUMMARY.md` or `*-SUMMARY.md`).
`execute-phase.md` owns wave-level routing and fanout; this workflow owns the selected plan's local execution semantics, bounded gates, and summary emission.
</purpose>

<required_reading>
Load the structured init-state payload first; reopen `STATE.md` only if the payload is missing, stale, or flagged by `state_load_source` / `state_integrity_issues`.
Read config.json for planning behavior settings.
Defer execution-reference, checkpoint, recovery, and summary-schema loads until the stage that actually consumes them. When those files are needed, read them with the file_read tool in the relevant stage rather than frontloading them here.
</required_reading>

<process>

<step name="tangent_control">
If execution produces a bounded stop for possible side work, return it in the
same execution payload as a new event family with `tangent_summary` and
`tangent_decision`. Use the existing `execution` payload shape. Do not
auto-branch or start side work from telemetry alone.
</step>

<step name="init_context" priority="first">
Load the bootstrap execution context using the staged init payload:

```bash
INIT=$(gpd --raw init execute-phase "${phase}" --stage phase_bootstrap)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $INIT"
  exit 1
fi
```

This workflow assumes `execute-phase.md` already selected the plan and wave. It does not re-decide wave routing or specialist selection.

Use manifest-backed field guidance instead of ad hoc extraction lists:

```bash
gpd --raw stage field-access execute-phase --stage phase_bootstrap --style instruction
```

Extract from init JSON: phase identity, selected-plan inventory (`plans`, `incomplete_plans`, counts, `phase_dir`), execution settings (`executor_model`, `verifier_model`, `autonomy`, `review_cadence`, unattended/checkpoint bounds), repo settings, and the surfaced contract fields (`project_contract`, `project_contract_gate`, `project_contract_validation`, `project_contract_load_info`). Treat `project_contract_gate.authoritative` as the machine authority flag.

If `GPD/` missing: error.
</step>

<step name="load_phase_classification_context">
Load the phase-classification payload only when you actually need it:

```bash
CONTRACT_INIT=$(gpd --raw init execute-phase "${phase}" --stage phase_classification)
if [ $? -ne 0 ]; then
  echo "ERROR: staged phase-classification init failed: $CONTRACT_INIT"
  exit 1
fi
```

Use `gpd --raw stage field-access execute-phase --stage phase_classification --style instruction`, then read only the manifest-selected contract, intake, convention, and state-integrity fields from this payload.

If `project_contract_load_info.status` starts with `blocked`, STOP and repair the stored contract before executing. Use the surfaced `project_contract_load_info.errors` / `warnings`; do not guess around them from prose-only context.

If `project_contract_validation.valid` is false, STOP and repair the contract before executing. A visible-but-blocked contract is still not an approved execution contract.

Treat `project_contract` as authoritative machine-readable scope only when `project_contract_gate.authoritative` is true. Do not execute from PLAN markdown alone if the contract or active-anchor ledger says a decisive reference, prior output, or forbidden proxy still constrains the work.

Treat `effective_reference_intake` as the structured carry-forward ledger for must-read refs, baselines, prior outputs, user anchors, and context gaps. Use `active_reference_context` to interpret that ledger quickly, not to replace it with prose-only reconstruction.
</step>

<step name="load_protocol_bundle_context">
Keep bundle asset reads out of bootstrap. If the plan later needs specialized execution guidance, the wave_planning stage will load the bundle payload and the bundle-listed core assets there instead of here.
</step>

<step name="verify_conventions">
Before execution, verify convention lock is consistent and non-empty:

```bash
CONV_CHECK=$(gpd --raw convention check)
if [ $? -ne 0 ]; then
  echo "WARNING: Convention verification failed — review before executing"
  echo "$CONV_CHECK"
fi
```

If the project has existing phases and the convention lock is empty, this is an error. Conventions must be established before execution proceeds.

**Load authoritative conventions** (canonical protocol from `agent-infrastructure.md`):

```bash
CONVENTIONS=$(gpd --raw convention list 2>/dev/null)
```

Single source of truth is the structured init-state convention payload (`convention_lock` / `derived_convention_lock`). Before using any equation from a prior phase or external source, verify conventions match the lock. See `shared-protocols.md` Convention Tracking Protocol for the 5-point checklist (metric, Fourier, normalization, coupling, renormalization scheme).
</step>

<step name="identify_plan">
Use `plans`, `incomplete_plans`, and selected-plan metadata from the staged init payload. Find the first plan artifact without a matching summary artifact; do not rediscover it with `ls`, `grep`, or filename parsing unless the payload is missing.

Canonical standalone pairing is `PLAN.md` <-> `SUMMARY.md`; numbered plans pair by shared stem. Decimal phases are supported for numbered files (`01.1-hotfix/`). Preserve separate `phase` and `plan` values from staged metadata so metrics render as "Phase 05 P05-02", not a collapsed plan code.

<if mode="yolo">
Auto-approve: `>> Execute {phase}-{plan}-PLAN.md [Plan X of Y for Phase Z]` -> parse_segments.
</if>

<if mode="interactive" OR="custom with gates.execute_next_plan true">
Present plan identification, wait for confirmation.
</if>
</step>

<step name="run_plan_tool_preflight">
Before executing the selected plan, validate any machine-checkable specialized tool requirements declared in plan frontmatter:

```bash
PLAN_PREFLIGHT=$(gpd --raw validate plan-preflight "${PLAN_PATH}")
if [ $? -ne 0 ]; then
  echo "ERROR: plan specialized-tool preflight failed"
  echo "$PLAN_PREFLIGHT"
  exit 1
fi
```

If the preflight reports warnings only, keep them visible during execution. Use declared fallbacks automatically only for non-blocking preferred tools (`required: false`) when the fallback preserves the plan's scientific intent, and document the switch in `SUMMARY.md`. If a required specialized tool is unavailable, stop and revise the plan or environment before execution.
</step>

<step name="record_start_time">
```bash
PLAN_START_TIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
PLAN_START_EPOCH=$(date +%s)
```

Record workflow start in the local observability stream, then start the plan-local execution trace:

```bash
gpd observe event workflow execute-plan.start --phase "${phase}" --plan "${plan}" 2>/dev/null || true
```

Start execution trace for debugging:

```bash
gpd trace start "${phase}" "${plan}" 2>/dev/null || true
```

Keep the GitHub lifecycle reference deferred until the plan reaches its checkpoint / closeout handling, but remember that this plan will eventually need `{GPD_INSTALL_DIR}/references/execution/github-lifecycle.md` for branch and remote examples.
</step>

<step name="resolve_autonomy_mode">
Read autonomy mode from init JSON to control decision authority throughout execution:

```bash
AUTONOMY=$(echo "$INIT" | gpd json get .autonomy --default supervised)
```

**Checkpoint behavior by mode:**

| Mode | Task Checkpoints | Physics Decision Checkpoints | Verification Failure |
|------|-----------------|------------------------------|---------------------|
| **supervised** | After EVERY task plus every required first-result gate. Under `review_cadence=dense`, a wave with no deviations may collapse its per-task checkpoints into one "Approve tasks {N..M} as clean pass? `[Y/n/e]`" batch (see "Clean-wave batching under dense" for the full predicate) | Always | Always stop |
| **balanced** | Auto-flow between clean tasks, but required bounded gates still run | On physics choices, deviation rules 5-6, convention conflicts, or convergence failure after 3 attempts | Attempt one bounded fix, then stop if unresolved |
| **yolo** | No user prompt on clean passes, but required bounded gates still run | Attempt one alternative before escalating; never skip first-result, skeptical, or pre-fanout gates | Stop only on unrecoverable errors, failed sanity gates, or unresolved skeptical review |

**Invariant:** `autonomy` changes who is asked and when. It does NOT disable first-result sanity checks, bounded execution segments, contract/anchor gates, or physics hard stops. Clean-wave batching under dense collapses keystrokes, not gates — any deviation, failed verification, or triggered gate reverts the wave to per-task checkpoints for the remaining tasks.

Task checkpoints are task-level, not every internal algebra line. Model profile and research mode may change depth or task granularity, but they do NOT remove required first-result, skeptical, or pre-fanout gates.

</step>

<step name="resolve_execution_cadence">
Read cadence controls from init JSON. Use these to decide whether a plan can run unbounded or must be segmented even without authored checkpoints.

```bash
REVIEW_CADENCE=$(echo "$INIT" | gpd json get .review_cadence --default dense)
MAX_UNATTENDED_MINUTES_PER_PLAN=$(echo "$INIT" | gpd json get .max_unattended_minutes_per_plan --default 15)
CHECKPOINT_AFTER_N_TASKS=$(echo "$INIT" | gpd json get .checkpoint_after_n_tasks --default 1)
CHECKPOINT_AFTER_FIRST_RESULT=$(echo "$INIT" | gpd json get .checkpoint_after_first_load_bearing_result --default true)
CHECKPOINT_BEFORE_DOWNSTREAM=$(echo "$INIT" | gpd json get .checkpoint_before_downstream_dependent_tasks --default true)
```

Resolve plan-local bounds using orchestrator tags first, then plan shape:

- if the orchestrator passed `<first_result_gate>true</first_result_gate>`, honor it
- if `review_cadence=dense`, treat `FIRST_RESULT_GATE_REQUIRED=true` as forced; do not recompute it from per-plan heuristics
- if the orchestrator passed `<segment_task_cap>N</segment_task_cap>`, honor it
- otherwise require bounded execution when the plan has no authored checkpoints and `task_count >= CHECKPOINT_AFTER_N_TASKS`
- also require bounded execution when the uninterrupted segment is likely to exceed `MAX_UNATTENDED_MINUTES_PER_PLAN`, even if the work feels smooth
- also require bounded execution when the plan establishes a new baseline, new estimator, new ansatz, or a first decisive-comparison path that many downstream tasks depend on
- phase ordering, prior momentum, or "we are already deep into execution" never waive a required bounded stop

Set:

- `FIRST_RESULT_GATE_REQUIRED=true|false`
- `SEGMENT_TASK_CAP=${CHECKPOINT_AFTER_N_TASKS}` unless overridden
- `BOUNDED_EXECUTION=true|false`
- `PRE_FANOUT_REVIEW_REQUIRED=${CHECKPOINT_BEFORE_DOWNSTREAM}` when downstream work would rely on a not-yet-decisive result

**Skeptical re-questioning rule:** if the first material result only validates a proxy, internal consistency check, or supporting artifact while the contract still owes a decisive comparison, benchmark anchor, or acceptance-test outcome, STOP and ask whether the framing still deserves belief before continuing.

Required gates are only considered passed when an explicit clear/override transition is recorded. "No obvious issue" prose is not enough to resume fanout.

Clear transitions are reason-scoped: clearing `first_result` must not silently clear `pre_fanout` or skeptical review state, and a `fanout unlock` never substitutes for the matching review clear.

</step>

<step name="create_checkpoint">
Before any plan execution, load `{GPD_INSTALL_DIR}/references/execution/execute-plan-checkpoints.md` and follow its rollback-tag protocol. Keep only the resulting `CHECKPOINT_TAG` in local execution state.
</step>

<step name="detect_previous_attempt">
Use `execute-plan-checkpoints.md` to detect prior task commits for this plan and offer resume-or-fresh-start. Load any prior `plan-commits.json` data into the task-commit ledger before executing.
</step>

<step name="parse_segments">
Read checkpoint declarations from the selected PLAN and merge virtual boundaries from the resolved cadence controls. Routing:

| Checkpoints | Pattern        | Execution                                                                                              |
| ----------- | -------------- | ------------------------------------------------------------------------------------------------------ |
| None        | A (non-interactive) | Single subagent: full plan + SUMMARY + commit                                                    |
| Verify-only | B (segmented)  | Segments between checkpoints. After none/human-verify -> SUBAGENT. After decision/human-action -> MAIN |
| Decision    | C (main)       | Execute entirely in main context                                                                       |
| Auto-bounded | D (virtual checkpoints) | Segment automatically at first-result, task-cap, context-pressure, or pre-fanout review boundaries |

**Pattern A:** spawn one `gpd-executor` for the selected plan, all tasks, SUMMARY, completion commit, and a structured return envelope. The child must load conventions, rerun plan preflight before substantive execution, follow `execute-plan-validation.md`, and receive `<autonomy_mode>{AUTONOMY}</autonomy_mode>`, `<review_cadence>{REVIEW_CADENCE}</review_cadence>`, and `<bounded_execution>false</bounded_execution>` only for genuinely low-risk short plans.

**Pattern A failure:** load `execute-plan-recovery.md` child handoff recovery. Commits or output files do not prove success without the gate. If the return envelope is missing or invalid, keep the child handoff incomplete and retry, use explicit Pattern C main-context fallback, or abort.

**Pattern B:** Execute segment-by-segment. Non-interactive segments spawn a child for assigned tasks only (no SUMMARY/commit). Checkpoints remain in the main context. After all segments: aggregate, create SUMMARY, apply return updates, and commit.

**Pattern B/D failure:** load `execute-plan-recovery.md` child handoff recovery. Segment outputs and git commits are partial evidence only until the fresh artifact gate, typed return, and applicator pass succeed.

**Pattern C:** Execute in main using standard flow (step name="execute").

**Pattern D:** Execute via virtual checkpoints even if the authored plan contains no checkpoint tasks. Stop at the first material result, at `SEGMENT_TASK_CAP`, at context-pressure auto-pause, or before downstream fanout when anchors still need review. Use the same continuation flow as authored checkpoints.

Fresh context per subagent preserves peak quality. Main context stays lean.
</step>

<step name="init_agent_tracking">
```bash
if [ ! -f GPD/agent-history.json ]; then
  echo '{"version":"1.0","max_entries":50,"entries":[]}' > GPD/agent-history.json
fi
if [ -f GPD/current-agent-id.txt ]; then
  INTERRUPTED_ID=$(cat GPD/current-agent-id.txt)
  echo "Found interrupted agent: $INTERRUPTED_ID"
fi
```

If interrupted: ask user to resume (Task `resume` parameter) or start fresh.

**Tracking protocol:** On spawn: write agent_id to `current-agent-id.txt`, append to agent-history.json: `{"agent_id":"[id]","task_description":"[desc]","phase":"[phase]","plan":"[plan]","segment":[num|null],"timestamp":"[ISO]","status":"spawned","completion_timestamp":null}`. On completion: status -> "completed", set completion_timestamp, delete current-agent-id.txt. Prune: if entries > max_entries, remove oldest "completed" (never "spawned").

Run for Pattern A/B before spawning. Pattern C: skip.
</step>

<step name="segment_execution">
Pattern B/D only (authored or virtual checkpoints). Skip for A/C.

1. Build the segment map from authored checkpoint locations plus virtual boundaries from `FIRST_RESULT_GATE_REQUIRED`, `SEGMENT_TASK_CAP`, `MAX_UNATTENDED_MINUTES_PER_PLAN`, and context pressure.
2. Per segment:
   - Subagent route: spawn `gpd-executor` for assigned tasks only. Include task range, plan path, full-plan context requirement, `<autonomy_mode>{AUTONOMY}</autonomy_mode>`, `<review_cadence>{REVIEW_CADENCE}</review_cadence>`, `<segment_task_cap>{SEGMENT_TASK_CAP}</segment_task_cap>`, `<max_unattended_minutes_per_plan>{MAX_UNATTENDED_MINUTES_PER_PLAN}</max_unattended_minutes_per_plan>`, and `<first_result_gate>{FIRST_RESULT_GATE_REQUIRED}</first_result_gate>`. The child returns segment outputs, `contract_updates`, and any durable `continuation_update`; it does not create the final SUMMARY or completion commit.
   - Treat `execution_segment` as the runtime transport payload for pause/continue handoff only. Durable state is the canonical subset persisted as `continuation.bounded_segment` plus the matching execution-lineage event; markdown handoffs are discovery surfaces.
   - Main route: execute tasks using standard flow (step name="execute")
3. After ALL segments: aggregate files, deviations, decisions, and `contract_updates`; create SUMMARY.md; apply returned state updates through `gpd apply-return-updates`; run the final self-check from `executor-completion.md`; then make the completion commit.

> **Handoff verification:** Apply the Pattern B/D child artifact gate before success; git commits are partial evidence only.

</step>

<step name="load_prompt">
```bash
ls "${phase_dir}"/PLAN.md "${phase_dir}"/*-PLAN.md 2>/dev/null | sort
ls "${phase_dir}"/SUMMARY.md "${phase_dir}"/*-SUMMARY.md 2>/dev/null | sort
cat "${phase_dir}/${phase}-${plan}-PLAN.md"
```
This IS the execution instructions. Follow exactly. If plan references CONTEXT.md: honor user's research direction throughout.
</step>

<step name="previous_phase_check">
```bash
ls GPD/phases/*/*SUMMARY.md 2>/dev/null | sort -r | head -2 | tail -1
```
> **Platform note:** If `ask_user` is not available, present these options in plain text and wait for the user's freeform response.

If previous SUMMARY has unresolved "Issues Encountered" or "Next Phase Readiness" blockers: ask_user(header="Previous Issues", options: "Proceed anyway" | "Address first" | "Review previous").
</step>

<step name="load_wave_planning_context">
Load the wave-planning payload only when the plan is ready to move into segment execution:

```bash
SEGMENT_INIT=$(gpd --raw init execute-phase "${phase}" --stage wave_planning)
if [ $? -ne 0 ]; then
  echo "ERROR: staged wave-planning init failed: $SEGMENT_INIT"
  exit 1
fi
```

Use `gpd --raw stage field-access execute-phase --stage wave_planning --style instruction`, then read only the selected bundle manifest/context, verifier extensions, active references, state-integrity fields, conventions, intermediate results, approximations, and propagated uncertainties needed by this segment.

If `selected_protocol_bundle_ids` is non-empty, treat `protocol_bundle_load_manifest` and `protocol_bundle_context` as the plan-execution specialized-loading guide for this plan. Read any bundle-listed core assets now, not during bootstrap. Preserve `protocol_bundle_verifier_extensions` for verifier-ready outputs and downstream summary/verification checks.

Use `reference_artifacts_content` only here, when the segment actually needs to interpret prior outputs, baselines, or unresolved gaps. Stable knowledge docs may be present in that content as reviewed background, but they do not override the contract, conventions, or decisive evidence requirements.

Use `{GPD_INSTALL_DIR}/references/execution/executor-index.md` as the topic-to-reference map and load only the row needed for active segment work. High-risk exceptions stay explicit: `execute-plan-recovery.md`, `execute-plan-validation.md`, `execute-plan-checkpoints.md`, `{GPD_INSTALL_DIR}/references/orchestration/context-budget.md`, `{GPD_INSTALL_DIR}/references/orchestration/checkpoints.md`, `{GPD_INSTALL_DIR}/templates/summary.md`, and `{GPD_INSTALL_DIR}/templates/recovery-plan.md`.

When following GitHub lifecycle examples, substitute the repository's actual default branch and remote names for `<default-branch>` and `<remote-name>`; those placeholders are not literal branch or remote names.
</step>

<step name="execute">
Deviations are normal -- handle via deviation rules in `execute-plan-validation.md`.

1. Read @context files from prompt
2. Per task:
   - `type="auto"`: Execute derivation/calculation/simulation. Verify done criteria including dimensional checks. Commit using `executor-task-checkpoints.md`. Track hashes for SUMMARY.
     **Required first-result sanity gate:** At the earliest of first quantitative result, derived core equation, produced artifact, benchmark-style comparison, or two completed auto tasks, stop and ask whether this result is load-bearing, proxy-only, already sanity-checked, still missing decisive evidence, or vulnerable to a disconfirming observation. Load `execute-plan-checkpoints.md` for the full first-result, skeptical re-questioning, and pre-fanout payload protocol. Keep reason-scoped clears: `first_result`, `skeptical_requestioning`, and `pre_fanout` do not clear each other.

     **Supervised mode post-task checkpoint:** If `AUTONOMY="supervised"`, insert a `checkpoint:human-verify` after EVERY completed task. Emit the checkpoint return with the task result and all intermediate values; the orchestrator owns presentation and approval through the checkpoint protocol before any next task is accepted. Every such `checkpoint:human-verify` uses the `[Y/n/e]` idiom with a one-line summary (see `{GPD_INSTALL_DIR}/references/orchestration/checkpoint-ux-convention.md`).

     **Clean-wave batching under dense:** allowed only when supervised+dense, no deviations, every verification event has typed payload `verification.status="passed"` and `verification.issue_count=0`, no required gate is pending, and the return envelope has `status="completed"` with empty `issues`. Do not parse prose such as "failure language" to decide batching eligibility. If any task emits a deviation, fails verification, omits the typed verification outcome, or trips a required gate, revert to per-task checkpoints. See `execute-plan-checkpoints.md` for `[Y/n/e]` batch behavior.
   - `type="checkpoint:*"`: Route by autonomy mode:
     - **supervised:** STOP -> checkpoint protocol (see `execute-plan-checkpoints.md`) -> return structured checkpoint state to the orchestrator. The orchestrator presents the checkpoint and continues only through that protocol.
     - **balanced:** Stop for `checkpoint:decision`, `checkpoint:human-verify`, required first-result gates, any checkpoint tied to deviation rules 5-6 or unresolved convergence failure, and any case where decisive evidence is still missing but the next tasks would assume it. Log routine checkpoint markers and continue when no judgment is needed.
     - **yolo:** Do NOT skip required first-result, bounded-segment, skeptical, or pre-fanout checkpoints. Auto-continue only after the gate is explicitly cleared and the remaining work is genuinely independent of the unresolved decisive comparison. STOP on failed sanity, unresolved skeptical review, anchor-gate failure, or unrecoverable computation error.
3. Run `<verification>` checks including physics validation (see `execute-plan-validation.md`). Emit typed `verification-complete` telemetry; `passed` is valid only when all required checks passed with zero issues.
4. Confirm `<success_criteria>` met
5. Document deviations in Summary

**Context awareness (after each task):**

Context is finite. After each task, consult `{GPD_INSTALL_DIR}/references/orchestration/context-budget.md`: consider a checkpoint around 60% with heavy work remaining, force a bounded pause around 75% for supervised/balanced modes, and stop before quality degrades. If pausing mid-plan, commit current work, create `.continue-here.md`, persist the matching `execution_segment` as `continuation.bounded_segment`, and record the same pause in execution lineage. The markdown handoff file and STATE.md Session Continuity rendering are discovery surfaces; `continuation.bounded_segment` is the bounded authority.

Also stop when either bound is hit, even if context looks healthy:

- uninterrupted wall-clock time since the current segment started reaches `MAX_UNATTENDED_MINUTES_PER_PLAN`
- completed tasks since the last bounded checkpoint reach `SEGMENT_TASK_CAP`

These are bounded-segment stops, not optional hints. They keep long runs reviewable before a wrong early assumption fans out.
</step>

<task_commit>

## Task Commit Protocol

After each task (verification passed, done criteria met), load `{GPD_INSTALL_DIR}/references/execution/executor-task-checkpoints.md` and commit immediately through `gpd commit --files`.

Root-level invariants:

- choose exact task files; never use broad staging such as `git add .` or `git add -A`
- use a plan-scoped subject: `{type}({phase}-{plan}): {description}`
- let `gpd commit` run its blocking pre-commit validation; fix and retry on failure
- record the resulting hash in `TASK_COMMITS` for SUMMARY and crash recovery
- use per-segment `plan-commits-seg-${SEGMENT_NUM}.json` ledgers for Pattern B, then merge them into `plan-commits.json` after all segments complete

On resume (in `detect_previous_attempt`), read the ledger to reconstruct `TASK_COMMITS` and identify already committed tasks.

</task_commit>

<step name="checkpoint_protocol">
See `execute-plan-checkpoints.md` for the full checkpoint protocol (display format, types, resume signals) and `{GPD_INSTALL_DIR}/references/orchestration/checkpoints.md` for general checkpoint details. Spawned children return checkpoint state to the orchestrator; the orchestrator applies the protocol and owns the next-run handoff.
</step>

<step name="verification_failure_gate">
See `execute-plan-validation.md` for physics-specific verification failure handling (dimensional mismatch, limiting case failure, conservation violation).

Autonomy changes retry cadence, not correctness: supervised stops immediately; balanced may attempt one local verifiable fix before stopping; yolo may attempt one alternative approach before stopping. If verification still fails, record the issue in SUMMARY and return failure/checkpoint details to the orchestrator.
</step>

<step name="record_completion_time">
```bash
PLAN_END_TIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
PLAN_END_EPOCH=$(date +%s)

DURATION_SEC=$(( PLAN_END_EPOCH - PLAN_START_EPOCH ))
DURATION_MIN=$(( DURATION_SEC / 60 ))

if [[ $DURATION_MIN -ge 60 ]]; then
HRS=$(( DURATION_MIN / 60 ))
  MIN=$(( DURATION_MIN % 60 ))
DURATION="${HRS}h ${MIN}m"
else
  DURATION="${DURATION_MIN} min"
fi
```
</step>

<step name="create_summary">
Load the aggregate-and-verify payload only when the plan is ready to write `SUMMARY.md`:

```bash
SUMMARY_INIT=$(gpd --raw init execute-phase "${phase}" --stage aggregate_and_verify)
if [ $? -ne 0 ]; then
  echo "ERROR: staged aggregate-and-verify init failed: $SUMMARY_INIT"
  exit 1
fi
```

Use `gpd --raw stage field-access execute-phase --stage aggregate_and_verify --style instruction`, then read only summary inventory, selected bundle obligations, live execution/gate state, resume state, contract fields, active reference intake, and state-integrity fields needed for finalization.

Keep `selected_protocol_bundle_ids`, `protocol_bundle_load_manifest`, `protocol_bundle_context`, and `protocol_bundle_verifier_extensions` visible through summary authoring when the selected bundle added decisive artifact or verifier-extension obligations.

Load `{GPD_INSTALL_DIR}/references/execution/executor-completion.md` and `{GPD_INSTALL_DIR}/templates/summary.md`, then create `${phase}-${plan}-SUMMARY.md` at `${phase_dir}/`.

Note: DERIVATION-STATE.md is updated by `gpd:pause-work` as the pause handoff record. On natural completion, key equations and results are captured in SUMMARY.md.

If the selected plan artifact is the standalone `PLAN.md`, write the canonical standalone summary as `SUMMARY.md`. Where this workflow shows numbered examples like `${phase}-${plan}-SUMMARY.md`, substitute the standalone `SUMMARY.md` filename instead.

**Contract-backed plans:** if the PLAN frontmatter includes `contract`, SUMMARY frontmatter must also include:
- `plan_contract_ref`
- `contract_results` keyed by claim IDs, deliverable IDs, acceptance test IDs, reference IDs, and forbidden proxy IDs
- `comparison_verdicts` for decisive internal/external comparisons that were required or attempted; if the comparison is still open, emit `verdict: inconclusive` or `verdict: tension` instead of omitting the entry

Immediately before writing frontmatter, re-open `{GPD_INSTALL_DIR}/templates/contract-results-schema.md` and apply it literally. Do not rely on memory or on paraphrased summary rules.

`contract_results` is authoritative. Do not reintroduce ad hoc summary-side success criteria that are absent from the PLAN contract.
Before treating the summary as complete, run `gpd validate summary-contract ${phase_dir}/${phase}-${plan}-SUMMARY.md` and fix any contract-linkage or verdict-ledger errors.

Follow `executor-completion.md` for substantive title, key results, uncertainty budget, limiting cases, validation events, open questions, final self-check, typed return, and completion commit. Next status is either "Ready for {next-plan}" or "Phase complete, ready for transition".

Autonomy mode (`supervised` / `balanced` / `yolo`) and profile may change cadence or verbosity, but they do NOT relax contract-result emission.
</step>

<step name="update_current_position">
Use `executor-completion.md` as the authority for completion-state effects. **Do NOT write STATE.md directly.** Return state updates in the `gpd_return` envelope so the orchestrator (`execute-phase.md`) can apply them sequentially via `gpd apply-return-updates`.

Minimal completion envelope shape:

```yaml
gpd_return:
  status: completed
  files_written:
    - "GPD/phases/${phase_dir_name}/${phase}-${plan}-SUMMARY.md"
  issues: []
  next_actions: []
  state_updates:
    advance_plan: true
    update_progress: true
    record_metric:
      phase: "${phase}"
      plan: "${plan}"
  contract_updates:
    plan_contract_ref: "GPD/phases/${phase_dir_name}/${phase}-${plan}-PLAN.md#/contract"
    contract_results:
      claim:example:
        status: satisfied
        evidence: "GPD/phases/${phase_dir_name}/${phase}-${plan}-SUMMARY.md#key-results"
    comparison_verdicts:
      - subject_id: "acceptance-test:example"
        verdict: inconclusive
        evidence: "GPD/phases/${phase_dir_name}/${phase}-${plan}-SUMMARY.md#validation-events"
    contract_completion_status: partial
```

**Exception:** If executing in Pattern C (main context, no subagent), apply state updates directly by invoking the same canonical applicator on the summary file:

```bash
gpd apply-return-updates "${SUMMARY_FILE}"
```

</step>

<step name="extract_decisions_and_issues">
From SUMMARY, include decisions and blockers in the `gpd_return` envelope. The orchestrator applies them through `gpd apply-return-updates`:

```yaml
gpd_return:
  status: checkpoint
  files_written:
    - "GPD/phases/${phase_dir_name}/${phase}-${plan}-SUMMARY.md"
  issues:
    - "Blocker"
  next_actions:
    - "Resolve before downstream execution."
  decisions:
    - phase: "${phase}"
      summary: "${DECISION_TEXT}"
  blockers:
    - text: "Blocker"
```

**Exception:** Pattern C applies directly through the same applicator:

```bash
gpd apply-return-updates "${SUMMARY_FILE}"
```

</step>

<step name="update_continuation">
Include continuation cleanup in the `gpd_return` envelope so `gpd apply-return-updates` can retire the completed bounded segment and persist the canonical handoff:

```yaml
gpd_return:
  status: completed
  files_written:
    - "GPD/phases/${phase_dir_name}/${phase}-${plan}-SUMMARY.md"
  issues: []
  next_actions: []
  continuation_update:
    handoff:
      stopped_at: "Completed ${phase}-${plan}-PLAN.md"
    bounded_segment: null
```

`gpd apply-return-updates` records handoff timestamp/provenance; do not include `recorded_at` or `recorded_by` in child returns.

**Exception:** Pattern C applies directly through the same applicator:

```bash
gpd apply-return-updates "${SUMMARY_FILE}"
```

This continuation update is the authoritative completion cleanup boundary; STATE.md reflects it after persistence but is not an independent authority.

Keep STATE.md under 150 lines.
</step>

<step name="issues_review_gate">
If SUMMARY "Issues Encountered" != "None", route by autonomy mode:

- **supervised:** Present ALL issues with full details. Wait for user acknowledgment before proceeding.
- **balanced:** Present issues. Wait for acknowledgment only if any issue is physics-critical (dimensional error, limiting case failure, conservation violation) or changes interpretation. Log-only for minor issues.
- **yolo:** Log and continue immediately. Issues visible only in SUMMARY.md.
</step>

<step name="update_roadmap">
More plans -> update plan count, keep "In progress". Last plan -> mark phase "Complete", add date.
</step>

<step name="git_commit_metadata">
Task work already committed per-task. By this step the main context has already applied any returned state updates. Follow `executor-completion.md` for the final completion commit.

If you run an explicit `gpd pre-commit-check`, treat it as early visibility only. `gpd commit` re-runs the same validation on the commit paths and remains the blocking gate, so fix any reported issues before retrying when the commit is rejected.

```bash
gpd commit "docs(${phase}-${plan}): complete ${PLAN_NAME} plan" --files "${phase_dir}/${phase}-${plan}-SUMMARY.md" GPD/STATE.md GPD/ROADMAP.md
```

</step>

<step name="stop_trace">
Record workflow completion in the local observability stream, then stop the plan-local trace:

```bash
gpd observe event workflow execute-plan.complete --phase "${phase}" --plan "${plan}" 2>/dev/null || true
```

Stop execution trace (captures event summary):

```bash
gpd trace stop 2>/dev/null || true
```
</step>

<step name="cleanup_checkpoint">
After successful plan completion, remove the rollback tag using the cleanup rule in `execute-plan-checkpoints.md`. Retain it on failure for recovery.
</step>

<step name="offer_next">
Use staged `plans` and `summaries` from the aggregate/finalization payload rather than shelling out to count files.

| Condition                                  | Route                 | Action                                                                                                                                                  |
| ------------------------------------------ | --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| summaries < plans                          | **A: More plans**     | Find next PLAN without SUMMARY. **balanced/yolo:** auto-continue to next plan when no blockers remain. **supervised:** show next plan + completion summary, then end with `## > Next Up`: primary `gpd:execute-phase {phase}`, plus `gpd:suggest-next`. STOP here. |
| summaries = plans, current < highest phase | **B: Phase done**     | Show completion, suggest `gpd:plan-phase {Z+1}` + `gpd:verify-work {Z}` + `gpd:discuss-phase {Z+1}`                                                  |
| summaries = plans, current = highest phase | **C: Milestone done** | Show banner, suggest `gpd:complete-milestone` + `gpd:verify-work` + `gpd:add-phase`                                                                  |

All routes: start a fresh context window first.
</step>

</process>

<failure_recovery>
When plan execution fails, see `execute-plan-recovery.md` for the full recovery protocol including rollback, partial work preservation, and RECOVERY.md creation. For physics-specific failure diagnosis (sign errors, convergence failures, numerical instability, dimensional mismatches), use the template at `{GPD_INSTALL_DIR}/templates/recovery-plan.md`.
</failure_recovery>

<success_criteria>

- All tasks from PLAN.md completed
- All verifications pass (including physics validation gates)
- Dimensional consistency verified for all quantitative results
- Limiting cases checked where specified
- SUMMARY.md created with substantive content including key results
- Contract-backed plans emit contract_results and comparison_verdicts when applicable
- Shared state updated through `gpd_return` / `gpd apply-return-updates` (position, decisions, issues, Session Continuity rendering)
- ROADMAP.md updated
- Validation events documented
- Checkpoint tag cleaned up on success (retained on failure)
</success_criteria>
