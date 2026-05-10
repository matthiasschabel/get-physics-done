<purpose>
Accept executor child returns, apply SUMMARY updates, surface wave artifacts, and route checkpoint/inter-wave gates.
</purpose>

<stage_boundary>
This stage owns executor child-return acceptance after dispatch. It accepts completed executor work only through the canonical SUMMARY applicator, routes checkpoint returns to `checkpoint_resume`, requires proof-redteam success for proof-bearing plans, surfaces accepted artifacts, and runs inter-wave gates. It does not spawn normal executors, dispatch proof critics, or render retry/skip/rollback/stop menus.
</stage_boundary>

<process>

<step name="refresh_wave_return_checkpoint_context">
Refresh only this stage before reading child-return fields:

```bash
WAVE_RETURN_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage wave_return_checkpoint)
if [ $? -ne 0 ] || [ -z "$WAVE_RETURN_INIT" ]; then
  echo "ERROR: wave-return checkpoint stage refresh failed: $WAVE_RETURN_INIT"
  exit 1
fi
```

Use `gpd --raw stage field-access execute-phase --stage wave_return_checkpoint --style instruction` before reading `WAVE_RETURN_INIT`.
</step>

<step name="accept_executor_returns">
Wait for all executor children in the current wave to return. Report progress as each child finishes:

```
[Phase {N}, Wave {W}] Plan {plan_id} complete ({completed}/{total} in wave)
  Result: {one-line summary from SUMMARY.md or failure reason}
```

Run the local child artifact gate before success. Git commits and files are recovery evidence only until this gate passes and the canonical applicator reports `passed: true`; git commits are partial evidence only.

```yaml
child_gate:
  id: "wave_executor_plan_result"
  role: "gpd-executor"
  return_profile: "executor"
  required_status: "completed"
  expected_artifacts:
    - path: "${SUMMARY_FILE}"
      kind: "path"
      required: true
      must_be_named_in_files_written: true
  allowed_roots:
    - "{phase_dir}"
  freshness:
    marker: "$EXECUTOR_HANDOFF_STARTED_AT"
    require_mtime_at_or_after_marker: true
    preexisting_artifacts: "recovery_evidence_only"
  validators:
    - "gpd validate handoff-artifacts - --expected '${SUMMARY_FILE}' --allowed-root '{phase_dir}' --required-suffix=-SUMMARY.md --require-status completed --require-files-written --fresh-after \"$EXECUTOR_HANDOFF_STARTED_AT\""
    - "SUMMARY key-files.created / key-files.modified required/final deliverables exist"
    - "no Self-Check: FAILED or Validation: FAILED marker"
    - "proof-redteam artifact exists and reports status: passed when proof-bearing"
  applicator:
    command: "gpd --raw apply-return-updates ${SUMMARY_FILE}"
    require_passed_true: true
  write_allowlist:
    - "${SUMMARY_FILE}"
    - "{phase_dir}/**"
  status_route:
    checkpoint: "checkpoint_resume"
    blocked: "wave_failure_menu"
    failed: "wave_failure_menu"
  failure_route:
    return_missing: "repair_prompt_once"
    return_malformed_repairable: "repair_prompt_once"
    return_malformed_blocking: "wave_failure_menu"
    artifact_missing: "retry_once_or_main_context_fallback"
    artifact_stale: "retry_once"
    artifact_path_repairable: "repair_path_once"
    artifact_root_blocked: "wave_failure_menu"
    validator_failed: "wave_failure_menu"
    applicator_failed: "fail_closed_with_mutation_report"
```

Completed executor returns are accepted only after all of the following are true:

- `gpd_return.status` is `completed`.
- `gpd_return.files_written` is non-empty and names `${SUMMARY_FILE}`.
- `${SUMMARY_FILE}` is inside `{phase_dir}`, has suffix `-SUMMARY.md`, and is fresh after `$EXECUTOR_HANDOFF_STARTED_AT`.
- Required or final deliverables named in `key-files.created` / `key-files.modified` exist on disk.
- `Self-Check: FAILED` and `Validation: FAILED` markers are absent.
- Proof-bearing plans have sibling `{plan_id}-PROOF-REDTEAM.md` from `proof_critic_dispatch` with `status: passed`.
- `gpd --raw apply-return-updates ${SUMMARY_FILE}` returns `passed: true`.

Executor subagents MUST NOT write STATE.md directly. Executor subagents must not write `GPD/STATE.md` directly. The SUMMARY applicator is the only durable state-update path for accepted executor returns, and it runs exactly once per accepted SUMMARY. The orchestrator applies them through `gpd apply-return-updates` after each agent completes. The concrete helper call is `gpd --raw apply-return-updates ${SUMMARY_FILE}`.

If `gpd_return.status` is `checkpoint`, stop acceptance for that child and route to `checkpoint_resume`; do not run artifact validators or the applicator for the checkpoint route. Other non-completed statuses route to `wave_failure_menu`.
</step>

<step name="spot_check_and_report_wave">
Before reporting wave completion, spot-check the accepted SUMMARY artifacts:

- Verify first 2 files from `key-files.created` exist on disk when present.
- If the SUMMARY marks any `key-files.created` / `key-files.modified` paths as required or final-deliverable, verify those paths on disk before accepting success.
- Confirm at least one plan-scoped execution commit exists when the plan required commits.
- Re-open proof-redteam artifacts for proof-bearing plans and confirm `status: passed`.

If any spot-check fails, report the plan id, failing artifact path, and failed gate, then route to `wave_failure_menu`.

By the time the wave-complete report is emitted, executor returns have passed the child gate, SUMMARY updates have been applied, and surfaced artifacts have been spot-checked.

When the wave passes, emit:

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
</step>

<step name="surface_wave_artifacts">
Surface artifacts only after the executor gate and applicator have passed.

Use `{GPD_INSTALL_DIR}/references/orchestration/artifact-surfacing.md` for artifact class definitions and review priority rules.

Guard against false failure by checking delivered work against child-listed artifacts before declaring a missing-output error.

```
## Artifacts: Wave {N}

| Path | Class | Review |
|------|-------|--------|
| {relative_path} | {artifact_class} | {required | optional | final-deliverable} |

Required review: {count} artifact(s) -- inspect before Wave {N+1}
```

Mark an artifact `required` when it is a load-bearing derivation, a numerical result consumed by later waves, or a contract deliverable that is the `subject` of an acceptance test. Mark manuscript outputs, compiled PDFs, and peer review reports as `final-deliverable`; mark supporting plots, intermediate notebooks, and literature notes as `optional`.
</step>

<step name="checkpoint_and_inter_wave_gates">
Before unlocking downstream dependent waves, apply first-result/pre-fanout gates to the accepted wave result.

Live gate state must include:

```yaml
checkpoint_reason: pre_fanout
pre_fanout_review_pending: true
downstream_locked: true
last_result_label: "{label}"
last_artifact_path: "{path}"
proof_redteam_status: "{passed | not_required | missing | failed}"
skeptical_requestioning_required: "{true | false}"
skeptical_requestioning_summary: "{summary}"
weakest_unchecked_anchor: "{anchor}"
disconfirming_observation: "{observation}"
tangent_summary: "{summary}"
tangent_decision: "ignore | defer | branch_later | pursue_now"
```

Normalize fanout-lock-only events into this same live review stop. Gate clears are reason-scoped; for `pre_fanout`, `gate_clear` and `fanout_unlock` are separate transitions.

Run the inter-wave verification gate when `review_cadence=dense`, when adaptive cadence flags decisive evidence or dependent baselines, or when YOLO restrictions require it. Collect only SUMMARY files from the current wave plus their surfaced key files. Hard failures stop before the next wave. Proof-bearing waves always include proof-redteam status; missing or open proof audits keep downstream work locked.

Executors may return a tangent proposal with `tangent_summary` and `tangent_decision`, but executor initiative alone never starts side work; the parent routes any `gpd:tangent` branch as a follow-up, alternative, or explicit user-approved path.

Before spawning the next wave, display a one-sentence transition for `Completed`, `Enables`, and `Starting`, using accepted SUMMARY content and the next wave plan objectives.
</step>

</process>
