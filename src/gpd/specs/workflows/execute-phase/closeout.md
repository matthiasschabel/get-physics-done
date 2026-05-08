<purpose>
Close the phase only after execution, verification, and readiness gates have passed.
</purpose>

<stage_boundary>
This stage owns roadmap/state completion, transition handoff, checkpoint cleanup, and concrete next-command rendering.
</stage_boundary>

<process>

<step name="update_roadmap">
Mark phase complete in ROADMAP.md (date, status).

```bash
CLOSEOUT_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage closeout)
if [ $? -ne 0 ] || [ -z "$CLOSEOUT_INIT" ]; then
  echo "ERROR: closeout init failed: $CLOSEOUT_INIT"
  exit 1
fi
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
