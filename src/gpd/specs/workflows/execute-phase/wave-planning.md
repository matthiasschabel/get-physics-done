<purpose>
Plan wave execution, dependency posture, proof-bearing routing, claim alignment, and cadence/risk gates.
</purpose>

<stage_boundary>
This stage owns phase-wide wave planning. It classifies proof obligations, checks claim/deliverable alignment, groups plans into waves, and decides cadence/risk policy. It does not spawn executors, verifiers, proof critics, or child-return handlers.
</stage_boundary>

<process>

<stage_policy>
Later staged refreshes surface `effective_reference_intake`, `active_reference_context`, `reference_artifacts_content`, selected protocol bundles, and convention locks for anchor-aware routing. Stable knowledge docs may appear only through those shared reference surfaces as reviewed background; they do not become a separate authority tier.

`execute-plan.md owns plan-local execution semantics; this workflow only owns phase-wide routing and wave risk.` This stage may name downstream child-readable paths, but it does not eagerly need full `workflows/execute-plan.md`, `references/orchestration/checkpoints.md`, or `references/verification/core/verification-core.md`.

**Mode-aware behavior:**
- `autonomy` controls who gets interrupted at a wave boundary.
- `research_mode` adjusts depth and optional tangents; it never relaxes required gates.
- `review_cadence` controls bounded phase pauses.
- `research_mode=balanced` keeps standard contract, anchor, and review coverage unless the wave needs a narrower or broader review.
- `research_mode=adaptive` may narrow only after decisive prior `contract_results`, `comparison_verdicts`, or an explicit approach lock show that the method family is stable.
- `research_mode=exploit` suppresses optional tangents by default.
- `workflow.verifier=false`, sparse cadence, `autonomy=yolo`, or manual "skip verification" requests do not disable mandatory proof red-teaming for proof-bearing work.
</stage_policy>

<step name="detect_proof_obligation_work">
Classify whether any selected plan is proof-bearing before execution and before honoring verifier-disabled or sparse-review settings.

@{GPD_INSTALL_DIR}/references/verification/core/proof-redteam-workflow-gate.md

Mark a plan proof-bearing when it establishes a theorem, lemma, equivalence, bound, identity, no-go result, derivation validity claim, parameter coverage claim, or proof-backed acceptance test. For each proof-bearing plan, require a sibling `{plan_id}-PROOF-REDTEAM.md` artifact before wave success can be claimed.

Never treat a clean `SUMMARY.md`, correct algebra in a subset of cases, or "human will inspect later" as a substitute for the sibling proof-redteam artifact. Runtime delegation should use `gpd-check-proof` for that independent audit; executors may draft proof context but must not self-certify theorem-proof alignment.
</step>

<step name="refresh_wave_planning_context">
Refresh the wave-planning stage so the orchestrator does not keep late execution context pinned in bootstrap state:

```bash
WAVE_PLANNING_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage wave_planning)
if [ $? -ne 0 ]; then
  echo "ERROR: wave-planning stage refresh failed: $WAVE_PLANNING_INIT"
  exit 1
fi
```

Use `gpd --raw stage field-access execute-phase --stage wave_planning --style instruction` to confirm the manifest-selected wave-planning fields. Read only those keys from `WAVE_PLANNING_INIT`; `WAVE_PLANNING_INIT.staged_loading.required_init_fields` is the runtime confirmation.
</step>

<step name="claim_deliverable_alignment_check">
Gate execution on explicit confirmation that the machine-readable claim matches user intent for Phase {N}.

Read the persisted alignment status and current fingerprints before rendering anything:

```bash
ALIGNMENT_STATUS=$(gpd contract alignment-status 2>/dev/null || echo '{}')
CONTRACT_HASH=$(gpd contract fingerprint 2>/dev/null)
CONTEXT_HASH=$(gpd contract context-fingerprint 2>/dev/null)
CONFIRMED_AT=$(echo "$ALIGNMENT_STATUS" | gpd json get .confirmed_at --default null)
CONFIRMED_CONTRACT_HASH=$(echo "$ALIGNMENT_STATUS" | gpd json get .confirmed_contract_hash --default null)
CONFIRMED_CONTEXT_HASH=$(echo "$ALIGNMENT_STATUS" | gpd json get .confirmed_context_hash --default null)
```

**Fingerprint gate:** fail closed if either fingerprint command fails or resolves to an empty value before rendering the prompt or recording confirmation. Do not compare blank hashes, suppress the gate, or call `gpd contract record-alignment` on this path.

```bash
if [ -z "$CONTRACT_HASH" ] || [ -z "$CONTEXT_HASH" ]; then
  echo "ERROR: claim_deliverable_alignment_check could not resolve contract/context fingerprints."
  echo "Next Up: discuss, plan, then execute phase {N}"
  exit 1
fi
```

**Gating:** fires when `autonomy=supervised` OR `review_cadence=dense` OR any selected plan is proof-bearing per `detect_proof_obligation_work`. Skip only under `autonomy=yolo AND review_cadence in {adaptive, sparse} AND no proof-bearing plans`; log `claim_deliverable_alignment_check: skipped (autonomy=yolo, cadence=adaptive, no proof-bearing plans)` and continue to `discover_and_group_plans` without prompting.

**Suppression:** if `confirmed_at` is set AND the current `contract_fingerprint == confirmed_contract_hash` AND `context_guidance_fingerprint == confirmed_context_hash`, skip and log `claim_deliverable_alignment_check: skipped (already confirmed this session)`.

**Render:** when fired and not suppressed, render a one-screen `Claim ↔ Deliverable Alignment` table. Left column: CONTEXT.md + `ContractContextIntake`; right column: `gpd contract alignment-summary`. Cap each cell at 5 bullets.

```
| User intent (CONTEXT)               | Machine contract                    |
|-------------------------------------|-------------------------------------|
| Observables: ...                    | Claims: ...                         |
| Deliverables: ...                   | Deliverables: ...                   |
| Must-have references: ...           | Acceptance tests: ...               |
| Stop-or-rethink conditions: ...     |                                     |
```

**ask_user:** present exactly one question with 4 options. Enter selects `Y`.

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

Only an explicit `ask_user` answer of `Y: proceed` authorizes record-alignment. A command invocation, missing `ask_user` support, timeout, empty answer, or noninteractive run is not an alignment answer. Otherwise STOP before branch/checkpoint writes, scripts, numerical computations, dispatches, subagents, or artifacts.

On `Y: proceed` record alignment and continue:

```bash
gpd contract record-alignment --contract-hash "$CONTRACT_HASH" --context-hash "$CONTEXT_HASH"
```

On `n: abort`, exit cleanly, do not spawn any executor, and emit `Next Up: gpd:execute-phase {N}`. On `e` or `p`, hand off to `gpd:discuss-phase {N}` or `gpd:plan-phase {N}`, then re-enter once; if the same key is chosen again, defer to that workflow and stop looping.
</step>

<step name="discover_and_group_plans">
Load plan inventory with wave grouping from `gpd phase index {phase_number}`.

Parse JSON for: `phase`, `plans[]` (each with `id`, `wave`, `interactive`, `gap_closure`, `objective`, `files_modified`, `task_count`, `has_summary`), `waves` (map of wave number -> plan IDs), `incomplete`, `has_checkpoints`.

**Filtering:** skip plans where `has_summary: true`. If `$GAPS_ONLY` is true, also skip non-gap_closure plans. If all filtered: "No matching incomplete plans" -> exit.

**Intra-wave dependency validation:** verify that no plan's `depends_on` references another plan in the same wave. If any same-wave dependency exists, stop and report the plan IDs and wave number.

**Parallel file conflict detection:** for waves with two or more plans, compare the indexed `files_modified` sets. If two plans touch the same path, warn and offer to serialize those plans within the wave.

If `INTRA_WAVE_CONFLICT` is true: STOP, present the dependency issue, and do not proceed.
If `FILE_CONFLICT` is true: WARN, present the overlap, and offer to serialize the conflicting plans within the wave.

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

Read `review_cadence`, `research_mode`, the unattended-minute limits, checkpoint thresholds, `strict_wait`, `never_interrupt_running_workers`, and `never_auto_close_child_agents` from the current staged payload/config. `strict_wait` disables unattended-minute cutoffs entirely; `never_interrupt_running_workers` is the narrower form of the same guarantee. In either case, set plan and wave unattended-minute limits to zero so workers run to natural completion. `never_auto_close_child_agents` means a spawned child remains open until it returns, checkpoints, or fails; no parent stage may synthesize closure.

**Core invariant:** `autonomy` decides who gets interrupted. `review_cadence` decides when the system must stop, inspect, or re-question. Even in `yolo`, required first-result and pre-fanout gates still run; the difference is that a clean pass can auto-continue.

These gates are task-level safety rails, not line-by-line interruptions. Even in `supervised`, checkpoint after each plan task or required gate, not after every algebraic micro-step.

For each wave, classify downstream fanout as risky when any of these holds:
- multiple plans and any later wave depends on it
- any plan has `task_count >= CHECKPOINT_AFTER_N_TASKS`, no authored checkpoints, or likely exceeds `MAX_UNATTENDED_MINUTES_PER_PLAN`
- derivation, formalism, numerical, or validation phase classes
- file conflicts, convention-lock requirements, or benchmark-critical anchors
- new estimator, baseline, or branch point whose downstream value depends on a decisive comparison still to be earned
- sparse evidence where the first material result only validates a proxy, internal consistency story, or supporting artifact while decisive anchors remain unresolved

When a wave is risky:
- set `FIRST_RESULT_GATE_REQUIRED=true`
- set `PRE_FANOUT_REVIEW_REQUIRED=true`
- set `SEGMENT_TASK_CAP=${CHECKPOINT_AFTER_N_TASKS}`
- force bounded continuation segments even when the authored plan has no checkpoints

**Dense cadence override:** when `review_cadence=dense`, treat every wave as risky regardless of the heuristic checks above, applying the risky-wave settings unconditionally: `FIRST_RESULT_GATE_REQUIRED=true` and `PRE_FANOUT_REVIEW_REQUIRED=true`. A clean pass may auto-continue once the gate fires, but the gate must fire.

When a wave is not risky, keep bounded execution available for long plans, wall-clock budgets, and context pressure, but allow short low-fanout plans to run without checkpoint-free micro-pauses.

**Skeptical re-questioning rule:** if the first material result is anchor-thin, stop before downstream fanout and record the weakest unchecked anchor, what still looks assumed, the quickest disconfirming observation, and which downstream plans would become wasted work if that evidence failed.

**Proposal-first tangent control:** unexpected but non-blocking alternatives are tangent proposals, not permission for silent side work. Classify each proposal at the existing review stop using exactly one of: `ignore`, `defer`, `branch_later`, `pursue_now`. `pursue_now` requires explicit user request or approved contract scope.

If a tangent should become an explicit side investigation, surface `gpd:tangent` as the follow-up command instead of silently branching inside execution.

Do NOT narrow bounded review scope just because a wave advanced or one proxy passed; keep the weakest unchecked anchor and decisive disconfirming check visible until the gate clears.
</step>

<step name="publish_wave_plan_for_dispatch">
Emit a compact wave-plan record for downstream stages. It must include each wave's plan IDs, sequential/parallel posture, risk flags, `FIRST_RESULT_GATE_REQUIRED`, `PRE_FANOUT_REVIEW_REQUIRED`, `SEGMENT_TASK_CAP`, proof-bearing plan IDs, file-conflict serialization decisions, and convention-lock assumptions.

This stage owns only the policy and route labels. Full checkpoint presentation belongs to `checkpoint_resume`; executor task semantics belong to `executor_dispatch` and child-readable `workflows/execute-plan.md`; proof-redteam execution belongs to proof critic dispatch/return stages; final verification belongs to aggregate/verification stages.
</step>

</process>
