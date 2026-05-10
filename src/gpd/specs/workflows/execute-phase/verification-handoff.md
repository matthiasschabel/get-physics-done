<purpose>
Route post-execution verification through a fresh verifier child, the verification report bridge helpers, and canonical verification status.
</purpose>

<stage_boundary>
This stage owns verifier spawn, verification_report_skeleton_bridge / verification_report_finalizer_bridge handoff, verification report validation, the verifier child_gate, and canonical verification_status routing. It does not aggregate summaries, close gaps, run the consistency checker, or close the phase.
</stage_boundary>

<handoff_verification>
Handoff verification stays child-owned: the verifier writes `VERIFICATION.md`, the parent validates the artifact and routes on canonical status.
</handoff_verification>

<verification_contract_fields>
`VERIFICATION.md` owns schema-owned ledgers: `plan_contract_ref`, `contract_results`, `comparison_verdicts`, and verifier-side `suggested_contract_checks`. Do not accept verifier-local aliases for these fields.
</verification_contract_fields>

<reference_context_boundary>
Stable knowledge docs surfaced through shared reference surfaces are reviewed background. They do not override the project contract, proof audits, or decisive evidence, and they do not become a separate authority tier.
</reference_context_boundary>

<process>

<step name="load_verification_handoff_stage">
Refresh only this stage before reading verification handoff fields:

```bash
VERIFICATION_HANDOFF_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage verification_handoff)
if [ $? -ne 0 ] || [ -z "$VERIFICATION_HANDOFF_INIT" ]; then
  echo "ERROR: verification-handoff stage refresh failed: $VERIFICATION_HANDOFF_INIT"
  exit 1
fi
```

Use `gpd --raw stage field-access execute-phase --stage verification_handoff --style instruction` before reading `VERIFICATION_HANDOFF_INIT`. Required bridge and context fields are manifest-owned by this stage.

`VERIFICATION_HANDOFF_INIT` must carry:

- `verification_report_skeleton_bridge`
- `verification_report_finalizer_bridge`
- `reference_artifact_files` and any reference/protocol context passed to the verifier
- `protocol_bundle_verifier_extensions`
- proof-review status when available

Keep `{GPD_INSTALL_DIR}/workflows/verify-phase.md` as a child-readable path in the verifier prompt. The parent stage must not eagerly load or restate the full verifier workflow, `verification-core.md`, or schema templates unless a helper or validator error specifically requires them.
</step>

<step name="verifier_eligibility">
If `verifier_enabled` is false, skip only the generic post-execution verifier for non-proof phases. Proof-bearing work still requires fresh proof-redteam artifacts with `status: passed`; missing, stale, malformed, or non-passing proof-redteam artifacts keep verification fail-closed.

Do not treat a disabled generic verifier as permission to close the phase. Closeout still requires the structured readiness gate and any proof/consistency gates that apply.
</step>

<step name="spawn_verifier">
Verify phase goal achievement, not task completion. Pass phase classification, protocol bundle context, active reference context, and proof-review status as context, but let the child verifier own target construction and physics checks.

Set the freshness marker immediately before spawning:

```bash
VERIFIER_HANDOFF_STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
```

Spawn one fresh verifier:

```
task(
  subagent_type="gpd-verifier",
  model="{verifier_model}",
  readonly=false,
  prompt="First, read {GPD_AGENTS_DIR}/gpd-verifier.md for your role and instructions.

Verify Phase {PHASE_NUMBER} against its phase goal and plan contracts.

Load before verdict:
- {GPD_INSTALL_DIR}/workflows/verify-phase.md
- verification_report_skeleton_bridge from VERIFICATION_HANDOFF_INIT
- verification_report_finalizer_bridge from VERIFICATION_HANDOFF_INIT
- {GPD_INSTALL_DIR}/templates/verification-report.md only if a helper or validator reports a schema issue
- {GPD_INSTALL_DIR}/templates/contract-results-schema.md only if a helper or validator reports a schema issue

Use the skeleton bridge writer only for conservative gap reports. Use the finalizer bridge writer command template with PATCH.json plus body-only BODY.md for passed, human_needed, expert_needed, and typed non-gap outcomes. Do not hand-author or reflow VERIFICATION.md frontmatter YAML.

<phase_class>{PHASE_CLASSES}</phase_class>
<selected_protocol_bundle_ids>{selected_protocol_bundle_ids}</selected_protocol_bundle_ids>
<protocol_bundle_load_manifest>{protocol_bundle_load_manifest}</protocol_bundle_load_manifest>
<protocol_bundle_context>{protocol_bundle_context}</protocol_bundle_context>
<protocol_bundle_verifier_extensions>{protocol_bundle_verifier_extensions}</protocol_bundle_verifier_extensions>

<files_to_read>
- Phase plans and summaries: {phase_dir}
- Roadmap: GPD/ROADMAP.md
- State: GPD/STATE.md and GPD/state.json
</files_to_read>

<spawn_contract>
write_scope:
  mode: scoped_write
  allowed_paths:
    - "{phase_dir}/{phase_number}-VERIFICATION.md"
expected_artifacts:
  - "{phase_dir}/{phase_number}-VERIFICATION.md"
shared_state_policy: return_only
</spawn_contract>

Run `gpd --raw init phase-op {PHASE_NUMBER}` and keep project contract, reference/protocol context, protocol bundle verifier extensions, and phase_proof_review_status visible. Stable knowledge docs surfaced there are background only.

Write to {phase_dir}/{phase_number}-VERIFICATION.md through the verification-report skeleton/finalizer bridge. Return one typed `gpd_return` envelope with status, files_written, the report path, and canonical verification_status: passed | gaps_found | expert_needed | human_needed.",
  description="Verify Phase {PHASE_NUMBER} goal"
)
```
</step>

<step name="verifier_child_gate">
Run the local child_gate before accepting the verifier result. Generic acceptance semantics live in `references/orchestration/child-artifact-gate.md`; scientific status routing lives in `references/verification/verification-status-authority.md`; checkpoint transport lives in `references/orchestration/continuation-boundary.md`.

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
    command: "none; closeout/update_roadmap is allowed only after verifier and consistency gates pass"
    require_passed_true: false
  failure_route: "fail_closed -> gpd:verify-work {PHASE_NUMBER} | repair_prompt_once | retry_once_then_gpd_verify_work"
```

Spawn errors, missing `files_written`, stale reports, failed validators, malformed returns, or proof-redteam blockers all fail closed. Verifier return authorship and report frontmatter stay child/helper-owned; this parent stage may not mark the phase complete.
</step>

<step name="canonical_status_route">
Read status only after the child_gate passes. Route on `gpd_return.status` plus the validated top-level report frontmatter `status` / `verification_status`. Do not route on headings, marker strings, conversational `session_status`, or prose like "all checks passed".

`session_status: validating|completed|diagnosed` is conversational progress only. If the prior report carries `session_status: diagnosed`, use it as context but continue to route from canonical verification status.

| Canonical verification status | Route |
| --- | --- |
| `passed` | Continue to `consistency_check`; do not close the phase yet. |
| `gaps_found` | Continue to `gap_reverification` or stop with the gap route below. |
| `human_needed` | Stop for human review; do not update roadmap/state. |
| `expert_needed` | Stop for expert review; do not update roadmap/state. |

For `gaps_found`, populate a stage_stop before rendering:

```yaml
stage_stop:
  workflow: execute-phase
  stage: verification_handoff
  status: blocked
  reason: verification_gaps_found
  checkpoint: verification_gap
  user_decision_needed: true
  next_runtime_command: "gpd:plan-phase {PHASE_NUMBER} --gaps"
  also_available:
    - "cat {phase_dir}/{phase_number}-VERIFICATION.md"
    - "gpd:verify-work {PHASE_NUMBER}"
    - "gpd:suggest-next"
```

## > Next Up

Primary: `gpd:plan-phase {PHASE_NUMBER} --gaps`

**Also available:**
- `cat {phase_dir}/{phase_number}-VERIFICATION.md` -- inspect the canonical report
- `gpd:verify-work {PHASE_NUMBER}` -- rerun or continue verification
- `gpd:suggest-next` -- confirm the next action

<sub>Start a fresh context window, then run the primary command above.</sub>
</step>

</process>
