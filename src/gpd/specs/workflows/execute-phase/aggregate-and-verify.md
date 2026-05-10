<purpose>
Aggregate completed waves, validate artifacts, generate recovery/figure artifacts, and run verification/consistency gates.
</purpose>

<stage_boundary>
This stage owns summary aggregation, figure inventory, recovery reports, verifier routing, verification report bridges, gap re-verification, debugger routing for persistent gaps, and rapid consistency checking.
</stage_boundary>

<process>

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

```bash
AGGREGATE_VERIFY_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage aggregate_and_verify)
if [ $? -ne 0 ] || [ -z "$AGGREGATE_VERIFY_INIT" ]; then
  echo "ERROR: aggregate-and-verify stage refresh failed: $AGGREGATE_VERIFY_INIT"
  exit 1
fi
```

Use `gpd --raw stage field-access execute-phase --stage aggregate_and_verify --style instruction` before reading `AGGREGATE_VERIFY_INIT`; aggregation and verification fields remain manifest-owned.

`AGGREGATE_VERIFY_INIT` includes `verification_report_skeleton_bridge` and `verification_report_finalizer_bridge`. Keep both bridge payloads visible through the verification handoff. Gap-only conservative reports use the skeleton bridge writer command; passed, human-needed, expert-needed, and typed non-gap outcomes use the finalizer bridge writer command template with `PATCH.json` plus body-only `BODY.md`. Do not hand-author `VERIFICATION.md` YAML in this workflow.

Before reporting a false failure despite delivered work, re-open child-listed
artifacts and plan summaries; classify gaps as missing, stale, malformed, or
unsurfaced.

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
After all waves complete successfully, scan this phase's SUMMARY.md key-files
and durable figure roots for generated PDF/PNG/EPS/SVG/JPEG/TIFF figures. Stable
figure roots are `artifacts/phases/${phase_number}-${phase_slug}/`, `figures/`,
or `paper/figures/`, not `GPD/phases/**`. Generated figures and plots should live in stable workspace roots. Durable figure roots include `figures/`, or `paper/figures/`.

If figures exist, load `{GPD_INSTALL_DIR}/templates/paper/figure-tracker.md`,
append to existing `paper/FIGURE_TRACKER.md` or create it from the template, and
commit the tracker after pre-commit checking. Entries record source phase,
source/data files, status, and update date. If no figures exist, skip silently.

If the phase compared theory with experimental or observational data, create
`paper/EXPERIMENTAL_COMPARISON.md` from
`{GPD_INSTALL_DIR}/templates/paper/experimental-comparison.md`; otherwise skip.

</step>

<step name="recovery_report">
**After all waves complete (including any failures, skips, or rollbacks), generate a recovery report.**

This step runs unconditionally -- for fully successful phases it is a brief confirmation; for phases with failures it is the critical decision point.

Build recovery outcome lists from the phase index, current summary artifacts, and the orchestrator's maintained failed/skipped records. Track succeeded, failed, skipped, and rolled-back plan IDs with reasons; do not infer success from a previous summary alone when spot-checks failed.

If all plans passed, proceed to `verify_phase_goal`; the report is informational
only. If any failures or skips occurred:

Create a recovery section in the phase directory. For physics-specific root cause analysis, consult `{GPD_INSTALL_DIR}/templates/recovery-plan.md`:

```bash
RECOVERY_FILE="${phase_dir}/PHASE-RECOVERY.md"
```

Write `PHASE-RECOVERY.md` with frontmatter for phase, timestamp, succeeded,
failed, skipped, and checkpoint tags. Include failed/skipped plan summaries,
links to plan recovery files when present, and these recovery routes:
`gpd:execute-phase {X}`, `gpd:plan-phase {X} --gaps`, `gpd:discuss-phase {X}`,
or `gpd:plan-phase {X+1}` when remaining work is non-critical.

Commit the recovery document after pre-commit checking `${RECOVERY_FILE}` and `GPD/STATE.md`.

Offer next steps based on failure pattern: isolated failed plan -> re-execute;
same-wave multiple failures -> discuss-phase; dependency cascade -> fix root
plan first; complete phase failure -> re-plan.

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

Post-execution verifier child artifact gate: run the local `child_gate` below. Shared acceptance semantics live in `references/orchestration/child-artifact-gate.md`; scientific status routing lives in `references/verification/verification-status-authority.md`; checkpoint transport lives in `references/orchestration/continuation-boundary.md`. This callsite owns the verification report bridge, validators, closeout applicator boundary, and failure route.

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

**If gaps_found:** populate the stop envelope, then render the canonical block.

```yaml
stage_stop:
  workflow: execute-phase
  stage: aggregate_and_verify
  status: blocked
  reason: verification_gaps_found
  checkpoint: verification_gap
  user_decision_needed: true
  next_runtime_command: "gpd:plan-phase {X} --gaps"
  also_available:
    - "cat {phase_dir}/{phase}-VERIFICATION.md"
    - "gpd:verify-work {X}"
    - "gpd:suggest-next"
```

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

Primary: `gpd:plan-phase {X} --gaps`

**Also available:**
- `cat {phase_dir}/{phase}-VERIFICATION.md` -- full report
- `gpd:verify-work {X}` -- manual review first
- `gpd:suggest-next` -- confirm the next action

<sub>Start a fresh context window, then run the primary command above.</sub>
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

**Circuit breaker (hard stop): Maximum 2 verification-gap closure cycles.** After
2 failed verification cycles (with debugger diagnosis on the second), STOP the
loop. Summarize both attempts, remaining gaps, root-cause hypothesis, and next
routes (`gpd:debug`, `gpd:discuss-phase {X}`, or manual intervention). Do NOT
attempt a third automated cycle.

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

Gap re-verifier child artifact gate: run the local `child_gate` below. Shared acceptance semantics live in `references/orchestration/child-artifact-gate.md`; scientific status routing lives in `references/verification/verification-status-authority.md`; checkpoint transport lives in `references/orchestration/continuation-boundary.md`. This callsite owns the re-verification report validator, closeout boundary, and failure route.

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

**Consistency checker child artifact gate:** run the local `child_gate` below. Shared acceptance semantics live in `references/orchestration/child-artifact-gate.md`; checkpoint transport lives in `references/orchestration/continuation-boundary.md`. This callsite owns the consistency artifact, validator, no-op applicator, and failure route.

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

For every consistency-check stop, populate `stage_stop` before rendering. Do not print raw staged-init or field-access commands in `## > Next Up`; those remain runtime mechanics.

| Stop | `stage_stop.status` | `reason` | `checkpoint` | `next_runtime_command` | `also_available` |
|---|---|---|---|---|---|
| checker spawn/error | `blocked` | `consistency_checker_unavailable` | `consistency_check` | `gpd:validate-conventions` | `gpd:resume-work`; `gpd:execute-phase {PHASE_NUMBER}`; `gpd:suggest-next` |
| checker checkpoint | `checkpoint` | `consistency_checker_checkpoint` | `consistency_check` | `gpd:resume-work` | `gpd:validate-conventions`; `gpd:suggest-next` |
| checker blocked | `blocked` | `consistency_checker_blocked` | `consistency_check` | `gpd:validate-conventions` | `gpd:resume-work`; `gpd:suggest-next` |
| checker failed | `failed` | `consistency_checker_failed` | `consistency_check` | `gpd:validate-conventions` | `gpd:resume-work`; `gpd:suggest-next` |

Render all three routes with this shape:

```
## > Next Up

Primary: `{stage_stop.next_runtime_command}`

**Also available:**
- `{secondary command}` -- route-specific recovery
- `gpd:suggest-next` -- confirm the next action

<sub>Start a fresh context window, then run the primary command above.</sub>
```

**If the consistency checker agent fails to spawn or returns an error:** Treat the consistency check as blocked. Do not proceed as if the phase was checked. Use the `checker spawn/error` route above.

**Handle the checker response through `gpd_return.status`:**
- `gpd_return.status: completed`: accept only if the consistency checker gate passes. Surface any `issues` as warnings, then continue.
- `gpd_return.status: checkpoint`: stop, surface the checkpoint payload from the checker, and use the `checker checkpoint` route above. Do not wait in place for user input inside this run.
- `gpd_return.status: blocked` / `gpd_return.status: failed`: stop execution, surface the returned issues, and use the matching `checker blocked` or `checker failed` route above. If the user wants convention repair, route through `gpd:validate-conventions`; the fresh continuation handoff owns any notation-coordinator work.

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

</process>
