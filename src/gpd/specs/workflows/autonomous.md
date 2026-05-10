<purpose>
Compatibility index for the staged `autonomous` workflow.
</purpose>

<stage_authorities>
The active authority is selected by `autonomous-stage-manifest.json`.
Do not load this index as a stage authority.

- `initialize_discover` -> `workflows/autonomous/initialize-discover.md`
  Parse launch arguments, load milestone and roadmap state, validate project
  inputs, and choose the first eligible phase.
- `phase_route` -> `workflows/autonomous/phase-route.md`
  Select the current phase, display progress, detect paper-writing phases, and
  route to the runtime-installed `gpd:write-paper` child command when needed.
- `discuss_delegate` -> `workflows/autonomous/discuss-delegate.md`
  Check phase context state and delegate missing context to the
  runtime-installed `gpd:discuss-phase` child command.
- `plan_execute_child_cycle` -> `workflows/autonomous/plan-execute-child-cycle.md`
  Run lifecycle gates, call the runtime-installed `gpd:plan-phase` child command,
  validate plan readiness, call the runtime-installed `gpd:execute-phase` child command,
  and honor checkpoint stops.
- `verification_route` -> `workflows/autonomous/verification-route.md`
  Call the runtime-installed `gpd:verify-work` child command and route on
  `verification_report_status` / child return state.
- `gap_route` -> `workflows/autonomous/gap-route.md`
  Make one gap-closure attempt through child planning/execution, then verify
  again.
- `convention_lifecycle_closeout` -> `workflows/autonomous/convention-lifecycle-closeout.md`
  Run convention checks, loop to the next phase by reloading staged init, then
  call the runtime-installed `gpd:audit-milestone` child command and the
  runtime-installed `gpd:complete-milestone` child command when ready.
- `blocked_recovery` -> `workflows/autonomous/blocked-recovery.md`
  Shared retry, skip, or stop recovery menu.
</stage_authorities>

<stage_loading_rule>
The public command includes only `workflows/autonomous/initialize-discover.md`.
Each later stage must be reached by a staged reload:

```bash
gpd --raw init autonomous --stage {stage_id}
```

Load only the active stage's `staged_loading.eager_authorities`. The first stage
must not eagerly load downstream phase routing, child-cycle, verification, gap,
closeout, or blocked-recovery authorities.
</stage_loading_rule>

<orchestration_contract>
Autonomous mode is an orchestrator, not a Markdown status parser. It invokes
child commands and routes on child returns / staged init payloads instead of
local `grep` readers.

Use the child commands with explicit phase arguments:

- `gpd:discuss-phase ${PHASE_NUM}`
- `gpd:plan-phase ${PHASE_NUM}`
- `gpd:execute-phase` with `{phase: PHASE_NUM}`
- `gpd:verify-work` with `{phase: PHASE_NUM}`

Before invoking execute-phase, run gate checks and stop before workspace
scripts, numerical computations, task dispatches, subagents, or artifact writes
when the plan authority is missing or stale:

```bash
gpd --raw validate lifecycle-contract-gate plan-phase "${PHASE_NUM}"
gpd --raw validate lifecycle-contract-gate execute-phase "${PHASE_NUM}"
gpd validate plan-contract
gpd --raw validate plan-preflight
```

Repair missing plan authority through discuss then plan; do not invent a local
repair path. `execute-phase` owns its normal phase transition / closeout path.

Stale/missing/non-passing verification blocks audit/paper routing. A phase is
not eligible for `COMPLETE_PHASE` closeout until verification passes and missing
plan authority has been resolved through the public child commands.

**Bounded checkpoint stop override:** if `gpd:execute-phase` returns a state
bounded to one authorized segment/checkpoint, surface the checkpoint, do not run
redundant read-only probing, do not invoke `gpd:verify-work`, and then return
from autonomous mode.

**3e. Post-Execution Verification Routing** is reached only after execute-phase
does not return a bounded checkpoint stop.
</orchestration_contract>

<success_criteria>
- All phase routing uses current `gpd` surfaces.
- All artifact references use canonical `GPD/` paths.
- The staged workflow remains runtime/provider-neutral.
</success_criteria>
