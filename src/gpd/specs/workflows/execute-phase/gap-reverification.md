<purpose>
Close verifier-reported gaps with the smallest safe execution loop, then run a gap-only verifier gate before any closeout path.
</purpose>

<stage_boundary>
This stage owns verification gap closure, localized re-execution, debugger diagnosis for persistent gaps, the automated circuit breaker, and the gap-only re-verifier child_gate. It does not run the first verifier handoff, run the rapid consistency checker, or close the phase.
</stage_boundary>

<process>

<step name="load_gap_reverification_stage">
Refresh only this stage before reading gap-closure fields:

```bash
GAP_REVERIFY_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage gap_reverification)
if [ $? -ne 0 ] || [ -z "$GAP_REVERIFY_INIT" ]; then
  echo "ERROR: gap-reverification stage refresh failed: $GAP_REVERIFY_INIT"
  exit 1
fi
```

Use `gpd --raw stage field-access execute-phase --stage gap_reverification --style instruction` before reading `GAP_REVERIFY_INIT`.
</step>

<step name="classify_gap_closure_route">
Read the validated top-level verification status from `{phase_dir}/{phase_number}-VERIFICATION.md`. Count only top-level report status and structured gap ledgers; do not use unanchored text search over nested `status:` fields.

| Failure pattern | Route |
| --- | --- |
| One localized contract target or one failed plan | Re-execute only the affected plan with verifier context. |
| Multiple failures with the same notation/convention cause | Stop and route through `gpd:validate-conventions`. |
| Multiple unrelated physics failures | Stop for user decision before new planning. |
| Same gap persists after one closure cycle | Spawn debugger before any second attempt. |
| Two failed gap-closure cycles | Circuit breaker: stop, summarize attempts, and do not attempt a third cycle. |

Gap-only execution uses `gpd:execute-phase {PHASE_NUMBER} --gaps-only` after gap plans exist. Localized re-execution may spawn `gpd-executor` for a specific plan only when the verifier report identifies the failing plan and contract target precisely.
</step>

<step name="localized_reexecution">
For a single localized failure, spawn one executor with explicit verifier context:

```
task(
  subagent_type="gpd-executor",
  model="{executor_model}",
  readonly=false,
  prompt="First, read {GPD_AGENTS_DIR}/gpd-executor.md for your role and instructions.

Re-execute plan {FAILED_PLAN} only. Fix the verifier-reported gap: {FAILURE_DESCRIPTION}.

Read:
- {GPD_INSTALL_DIR}/workflows/execute-plan.md as the child-readable executor workflow path
- {phase_dir}/{FAILED_PLAN}-PLAN.md
- {phase_dir}/{FAILED_PLAN}-SUMMARY.md
- {phase_dir}/{phase_number}-VERIFICATION.md
- GPD/STATE.md

Return exactly one typed gpd_return envelope with status, files_written, and the updated summary/artifact paths. If user input is required, return status: checkpoint and stop.",
  description="Targeted gap re-execution for {FAILED_PLAN}"
)
```

Apply the normal executor child gate and SUMMARY applicator before re-verification. Missing, stale, malformed, or wrong-root artifacts keep the gap cycle open.
</step>

<step name="convention_repair_route">
Convention repair is intentionally out-of-line here. Systematic sign, notation, unit, or naming failures are not repaired inline here. Populate a stage_stop and route through the convention workflow:

```yaml
stage_stop:
  workflow: execute-phase
  stage: gap_reverification
  status: blocked
  reason: convention_repair_required
  checkpoint: verification_gap
  user_decision_needed: true
  next_runtime_command: "gpd:validate-conventions"
  also_available:
    - "gpd:execute-phase {PHASE_NUMBER} --gaps-only"
    - "gpd:verify-work {PHASE_NUMBER}"
    - "gpd:suggest-next"
```

Do not spawn `gpd-notation-coordinator` from `execute-phase`. The next step is `gpd:validate-conventions`; the fresh continuation handoff owns any notation-coordinator work. Use a fresh `gpd:execute-phase {PHASE_NUMBER}` continuation after that workflow reports a typed result, or re-enter `gpd:execute-phase {PHASE_NUMBER} --gaps-only`.
</step>

<step name="debugger_diagnosis">
For a persistent gap after one closure attempt, spawn `gpd-debugger` before any second gap attempt:

```
task(
  subagent_type="gpd-debugger",
  model="{debugger_model}",
  readonly=false,
  prompt="First, read {GPD_AGENTS_DIR}/gpd-debugger.md for your role and instructions.

Use {GPD_INSTALL_DIR}/templates/debug-subagent-prompt.md as the one-shot debug contract. Populate it from the failed verification file, the gap-closure summary, and the original summary. Set goal: find_root_cause_only, symptoms_prefilled: true, and Create: GPD/debug/{FAILED_PLAN}.md.

Return exactly one typed gpd_return envelope with status: completed | checkpoint | blocked | failed, include files_written, and stop. Do not continue the investigation interactively inside the child.",
  description="Diagnose persistent verification gap"
)
```

If debugger output is missing, stale, malformed, blocked, or failed, stop. Do not run a second automated gap closure without a readable diagnosis.
</step>

<step name="circuit_breaker">
Maximum two verification-gap closure cycles. The second cycle is allowed only after debugger diagnosis for the persistent gap.

After two failed cycles, stop with a summary of:

- verifier report path
- first closure attempt and result
- debugger diagnosis path if present
- second closure attempt and result
- remaining gaps
- next routes: `gpd:discuss-phase {PHASE_NUMBER}`, `gpd:verify-work {PHASE_NUMBER}`, or manual intervention

Do not attempt a third automated cycle.
</step>

<step name="gap_only_reverification">
After gap-only execution or localized re-execution succeeds, automatically re-verify only the previously unresolved targets.

```bash
REVERIFY_HANDOFF_STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
```

```
task(
  subagent_type="gpd-verifier",
  model="{verifier_model}",
  readonly=false,
  prompt="First, read {GPD_AGENTS_DIR}/gpd-verifier.md for your role and instructions.

Re-verify Phase {PHASE_NUMBER} after gap closure.

Load before verdict:
- {GPD_INSTALL_DIR}/workflows/verify-phase.md as the child-readable verifier workflow path
- Verification: {phase_dir}/{phase}-VERIFICATION.md
- verification_report_skeleton_bridge from GAP_REVERIFY_INIT
- verification_report_finalizer_bridge from GAP_REVERIFY_INIT
- {GPD_INSTALL_DIR}/templates/verification-report.md only if a helper or validator reports a schema issue
- {GPD_INSTALL_DIR}/templates/contract-results-schema.md only if a helper or validator reports a schema issue

Focus on targets previously marked failed, partial, blocked, or unresolved. If the prior report carries session_status: diagnosed, start from that diagnosis. For proof-bearing work, re-check every required proof-redteam artifact and keep the phase blocked until each audit reports status: passed.

Update {phase_dir}/{phase_number}-VERIFICATION.md through the verification-report bridge helpers. Return exactly one typed gpd_return envelope with status, files_written, report path, and canonical verification_status: passed | gaps_found | expert_needed | human_needed.",
  description="Gap-only re-verification for Phase {PHASE_NUMBER}"
)
```

Run the local child_gate before accepting re-verification:

```yaml
child_gate:
  id: "gap_closure_reverification"
  role: "gpd-verifier"
  return_profile: "verifier"
  required_status: "completed"
  expected_artifacts:
    - "{phase_dir}/{phase_number}-VERIFICATION.md"
  allowed_roots:
    - "{phase_dir}"
  freshness_marker: "after $REVERIFY_HANDOFF_STARTED_AT"
  validators:
    - "gpd validate handoff-artifacts - --expected '{phase_dir}/{phase_number}-VERIFICATION.md' --allowed-root '{phase_dir}' --required-suffix=-VERIFICATION.md --require-status completed --require-files-written --fresh-after \"$REVERIFY_HANDOFF_STARTED_AT\""
    - "gpd validate verification-contract {phase_dir}/{phase_number}-VERIFICATION.md"
    - "verification-status-authority.md status rules"
    - "proof-redteam status: passed for proof-bearing work"
  applicator:
    command: "none; closeout/update_roadmap is allowed only after re-verifier and consistency gates pass"
    require_passed_true: false
  failure_route: "fail_closed -> gpd:verify-work {PHASE_NUMBER} | repair_prompt_once | retry_once_then_verify_work"
```

Route only on `gpd_return.status` and canonical verification_status:

- `completed` + `passed`: continue to `consistency_check`
- `completed` + non-passing verification_status: stop without auto-looping
- `checkpoint`: stop and route to `gpd:resume-work`
- `blocked` / `failed`: stop and route to `gpd:verify-work {PHASE_NUMBER}`
- malformed, missing files_written, stale report, or failed validators: fail closed and route to `gpd:verify-work {PHASE_NUMBER}`

Do not infer success from prose headings or untyped routing. Do not mark the phase complete on any non-passing or malformed path.
Every spawn error, malformed output, failed tuple, and non-passing verifier verdict keeps gap-closure state intact.
</step>

</process>
