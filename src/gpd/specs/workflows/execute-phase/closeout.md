<purpose>
Close the phase only after execution, verification, gap re-verification if needed, consistency checking, and read-only closeout readiness have all passed.
</purpose>

<stage_boundary>
This stage owns readiness-gated completion, helper checkpoint cleanup, and renderer-ready next-command selection. Code owns the `NextCommand` taxonomy and public next-up shape. This stage does not spawn verifiers, close gaps, run consistency checks, or decide scientific status.
</stage_boundary>

<process>

<step name="closeout_readiness_gate">
Refresh only this stage before reading closeout fields:

```bash
CLOSEOUT_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage closeout)
if [ $? -ne 0 ] || [ -z "$CLOSEOUT_INIT" ]; then
  echo "ERROR: closeout init failed: $CLOSEOUT_INIT"
  exit 1
fi
```

Use `gpd --raw stage field-access execute-phase --stage closeout --style instruction` before reading `CLOSEOUT_INIT`.

Before any roadmap/state transition, run the helper below and route from its JSON. Prerequisites are summarized here, but the helper is authority:

- canonical verification report exists and has status `passed`
- proof-bearing work has fresh passed proof-redteam artifacts
- `consistency_check` passed its child gate
- no bounded execution segment is active

Then run the read-only readiness helper:

```bash
CLOSEOUT_READINESS=$(gpd --raw phase closeout-readiness "${phase_number}" --require-verification)
if [ $? -ne 0 ]; then
  echo "$CLOSEOUT_READINESS"
  exit 1
fi
```

The readiness helper is read-only. On any blocker, stop and surface its next action. Do not repair blockers, update roadmap/state, or clean checkpoints from this stage.

`ready-to-execute` and `ready-for-verification` are not `ready-for-closeout`; the helper JSON is the transition authority. Branch before showing any mutation:

```bash
CLOSEOUT_READY=$(echo "$CLOSEOUT_READINESS" | gpd json get .ready --default false)
if [ "$CLOSEOUT_READY" != "true" ]; then
  echo "$CLOSEOUT_READINESS" | gpd next-up render --from-closeout-readiness
  exit 0
fi
```

Readiness next-action ownership:

- Blocked closeout keeps a public runtime primary, such as `gpd:verify-work ${phase_number}`, `gpd:resume-work`, or `gpd:execute-phase ${phase_number}`.
- Ready closeout labels `gpd phase complete "${phase_number}"` as `Primary local transition`, not a runtime workflow.
- Prompt-visible ready closeout names the read-only readiness helper before the safe mutation: `gpd --raw phase closeout-readiness {PHASE_NUMBER} --require-verification`, then `gpd phase complete {PHASE_NUMBER}`.
- `closeout_command_hint` is the local transition; `cleanup_command_hint` is only a secondary local helper.
- Checkpoint cleanup never appears in `stage_stop.next_runtime_command` or `stage_stop.also_available`.
</step>

<step name="ready_success_complete_phase">
Only after `CLOSEOUT_READINESS.ready == true`, show and run the safe local transition:

```bash
gpd phase complete "${phase_number}"
```

The completion helper owns the roadmap/state transition and rechecks lifecycle readiness before mutating. Treat it as a local transition command, not a public runtime workflow. Load broader transition policy references only after readiness is green and only if the helper reports a transition ambiguity that needs policy interpretation.
Do not read `workflows/transition.md`, `templates/state-machine.md`, or `references/orchestration/state-portability.md` during normal closeout. If readiness is green and `gpd phase complete` reports an ambiguous transition/state-machine result, load the `transition_helper_ambiguity` conditional authority pack before interpreting or repairing that result.
</step>

<step name="ready_success_cleanup_phase_checkpoints">
After successful phase completion, remove only helper-owned checkpoint tags:

```bash
gpd --raw phase checkpoint cleanup --phase "${phase_number}" --namespace phase --policy successful-closeout
```

If cleanup exits nonzero, print the helper JSON and stop. Preserve tags for blockers, recovery artifacts, failed/skipped/rolled-back plans, verification gaps, or preservation policy. Cleanup is secondary local helper work after the transition; do not render it as the primary next action.
</step>

<step name="offer_next">
Never end with only "ready to plan/continue" prose. After successful closeout, choose one matching variant, one primary `NextCommand`, populate `stage_stop.next_runtime_command`, and emit a `## > Next Up` block with exactly one `Primary:` line. Do not print raw staged-init or field-access commands.

Render the variants below from the refreshed closeout payload using the shared renderer shape (`Primary:`, `Primary local transition:`, `**After this completes:**`, and `Secondary ...` lines) without reading `references/ui/ui-brand.md` or `references/orchestration/continuous-execution.md` on the normal path. Load the `next_up_rendering_recovery` conditional authority pack only if the fixed `stage_stop` / `## > Next Up` variants cannot be rendered from the closeout payload.

If the next phase has no context, choose `gpd:discuss-phase {PHASE_NUMBER_PLUS_ONE}` / `gpd:discuss-phase {X+1}` and list `gpd:plan-phase {PHASE_NUMBER_PLUS_ONE}` / `gpd:plan-phase {X+1}` as the direct-plan alternative. If the next phase already has context, choose `gpd:plan-phase {PHASE_NUMBER_PLUS_ONE}`. Always list `gpd:suggest-next` as the recovery/confirmation command.

If the next phase has no context:

```yaml
stage_stop:
  workflow: execute-phase
  stage: closeout
  status: completed
  reason: next_phase_needs_context
  checkpoint: none
  user_decision_needed: false
  next_runtime_command: "gpd:discuss-phase {PHASE_NUMBER_PLUS_ONE}"
  also_available:
    - "gpd:plan-phase {PHASE_NUMBER_PLUS_ONE}"
    - "gpd:suggest-next"
```

## > Next Up

Primary: `gpd:discuss-phase {PHASE_NUMBER_PLUS_ONE}`
Secondary runtime: `gpd:plan-phase {PHASE_NUMBER_PLUS_ONE}`
Secondary runtime: `gpd:suggest-next`

If the next phase already has context:

```yaml
stage_stop:
  workflow: execute-phase
  stage: closeout
  status: completed
  reason: next_phase_context_ready
  checkpoint: none
  user_decision_needed: false
  next_runtime_command: "gpd:plan-phase {PHASE_NUMBER_PLUS_ONE}"
  also_available:
    - "gpd:discuss-phase {PHASE_NUMBER_PLUS_ONE}"
    - "gpd:suggest-next"
```

## > Next Up

Primary: `gpd:plan-phase {PHASE_NUMBER_PLUS_ONE}`
Secondary runtime: `gpd:discuss-phase {PHASE_NUMBER_PLUS_ONE}`
Secondary runtime: `gpd:suggest-next`

If the milestone is complete:

```yaml
stage_stop:
  workflow: execute-phase
  stage: closeout
  status: completed
  reason: milestone_complete
  checkpoint: none
  user_decision_needed: false
  next_runtime_command: "gpd:complete-milestone"
  also_available:
    - "gpd:suggest-next"
```

## > Next Up

Primary: `gpd:complete-milestone`
Secondary runtime: `gpd:suggest-next`
</step>

</process>
