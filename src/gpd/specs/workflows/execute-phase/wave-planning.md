<purpose>
Plan wave execution, dependency posture, proof-bearing routing, alignment, and cadence gates.
</purpose>

<stage_boundary>
This stage is the first place proof-obligation workflow authority may become visible. It prepares wave grouping and review/cadence policy, but it does not spawn executors or verifiers.
</stage_boundary>

<process>

<stage_policy>
Later staged refreshes surface `effective_reference_intake`, `active_reference_context`, and `reference_artifacts_content` for anchor-aware routing and wave planning. Stable knowledge docs may appear only through those shared reference surfaces as reviewed background; they do not become a separate authority tier.

When `parallelization` is false, plans within a wave execute sequentially.

**Mode-aware behavior:**
- `autonomy` controls who gets interrupted at a wave boundary.
- `research_mode` only adjusts depth and optional tangents; it does not relax required gates.
- `research_mode=balanced` (default): Use the standard execution depth and keep the default contract, anchor, and review coverage unless the wave needs broader or narrower review.
- `review_cadence` controls bounded phase pauses.
- `execute-plan.md owns plan-local execution semantics; this workflow only owns phase-wide routing and wave risk.`
- Even in `yolo`, do NOT skip required correctness gates, first-result sanity checks, skeptical review stops, or anchor-gated fanout reviews. A clean pass may auto-continue only after the gate is explicitly cleared.
- `research_mode=adaptive`: Start with explore-style coverage, then narrow only after prior decisive `contract_results`, decisive `comparison_verdicts`, or an explicit approach lock show that the method family is stable. Do NOT narrow just because a wave advanced or one proxy passed.
- Model profile may change depth, task granularity, or prose volume, but it does not waive required gates.
- `review_cadence` is read here only to schedule phase pauses; detailed gate ownership remains in `execute-plan.md`.
- `workflow.verifier=false`, sparse cadence, yolo autonomy, or any manual "skip verification" request do NOT disable mandatory proof red-teaming for proof-bearing or `proof_obligation` work.
</stage_policy>

<step name="detect_proof_obligation_work">
Classify whether any selected plan is proof-bearing before execution and before honoring verifier-disabled or sparse-review settings.

@{GPD_INSTALL_DIR}/references/verification/core/proof-redteam-workflow-gate.md

For each proof-bearing plan, require a sibling `{plan_id}-PROOF-REDTEAM.md` artifact that follows the shared gate above.

Never treat a clean `SUMMARY.md`, correct algebra in a subset of cases, or "human will inspect later" as a substitute for this artifact.
When runtime delegation is available, `gpd-check-proof` is the canonical owner of this sibling artifact. The executor may draft the proof and theorem inventory, but it must not self-certify theorem-proof alignment as its own independent redteam.
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

Read the persisted alignment status and the current contract/context fingerprints before rendering anything:

```bash
ALIGNMENT_STATUS=$(gpd contract alignment-status 2>/dev/null || echo '{}')
CONTRACT_HASH=$(gpd contract fingerprint 2>/dev/null)
CONTEXT_HASH=$(gpd contract context-fingerprint 2>/dev/null)
CONFIRMED_AT=$(echo "$ALIGNMENT_STATUS" | gpd json get .confirmed_at --default null)
CONFIRMED_CONTRACT_HASH=$(echo "$ALIGNMENT_STATUS" | gpd json get .confirmed_contract_hash --default null)
CONFIRMED_CONTEXT_HASH=$(echo "$ALIGNMENT_STATUS" | gpd json get .confirmed_context_hash --default null)
```

**Fingerprint gate:** Fail closed if either fingerprint command fails or resolves to an empty value before rendering the prompt or recording confirmation. Do not compare blank hashes, do not suppress the gate, and do not call `gpd contract record-alignment` on this path.

```bash
if [ -z "$CONTRACT_HASH" ] || [ -z "$CONTEXT_HASH" ]; then
  echo "ERROR: claim_deliverable_alignment_check could not resolve contract/context fingerprints."
  echo "Next Up: discuss, plan, then execute phase {N}"
  exit 1
fi
```

**Gating:** Fires when `autonomy=supervised` OR `review_cadence=dense` OR any selected plan is proof-bearing per `detect_proof_obligation_work`. Skip only under `autonomy=yolo AND review_cadence in {adaptive, sparse} AND no proof-bearing plans`; log `claim_deliverable_alignment_check: skipped (autonomy=yolo, cadence=adaptive, no proof-bearing plans)` and continue to `discover_and_group_plans` without prompting.

**Suppression:** If `confirmed_at` is set AND the current `contract_fingerprint == confirmed_contract_hash` AND `context_guidance_fingerprint == confirmed_context_hash`, skip and log `claim_deliverable_alignment_check: skipped (already confirmed this session)`. Use `gpd contract alignment-status` plus `CONTRACT_HASH`/`CONTEXT_HASH`.

**Render:** When fired and not suppressed, render a one-screen `Claim ↔ Deliverable Alignment` table. Left column: CONTEXT.md + `ContractContextIntake`; right column: `gpd contract alignment-summary`. Cap each cell at 5 bullets.

```
| User intent (CONTEXT)               | Machine contract                    |
|-------------------------------------|-------------------------------------|
| Observables: ...                    | Claims: ...                         |
| Deliverables: ...                   | Deliverables: ...                   |
| Must-have references: ...           | Acceptance tests: ...               |
| Stop-or-rethink conditions: ...     |                                     |
```

**ask_user:** Present exactly one question with 4 options. Enter selects `Y`.

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

**Interactive answer requirement:** Only an explicit `ask_user` answer of `Y: proceed` authorizes record-alignment. The command invocation, missing `ask_user` support, timeout, empty answer, or any noninteractive run is not an alignment answer. Otherwise STOP before `gpd contract record-alignment`, branch/checkpoint writes, scripts/numerical computations, dispatches/subagents, and artifacts. End: `Blocked: claim-deliverable alignment needs an explicit user answer. Next Up: rerun gpd:execute-phase {N} interactively.`
**On "Y: proceed" (or Enter from that `ask_user` prompt):** Record alignment and continue:
```bash
gpd contract record-alignment --contract-hash "$CONTRACT_HASH" --context-hash "$CONTEXT_HASH"
```

**On "n: abort":** Exit cleanly. Do NOT spawn any executor and do NOT proceed to `discover_and_group_plans`. Emit a final line `"Next Up: gpd:execute-phase {N}"` so the operator can resume after resolving alignment.

**On "e" / "p":** Hand off to `gpd:discuss-phase {N}` or `gpd:plan-phase {N}`, then re-enter once. If the same key is chosen again, defer to that workflow and stop looping.
</step>

<step name="discover_and_group_plans">
Load plan inventory with wave grouping from `gpd phase index {phase_number}`.

Parse JSON for: `phase`, `plans[]` (each with `id`, `wave`, `interactive`, `gap_closure`, `objective`, `files_modified`, `task_count`, `has_summary`), `waves` (map of wave number -> plan IDs), `incomplete`, `has_checkpoints`.

**Filtering:** Skip plans where `has_summary: true`. If `$GAPS_ONLY` is true, also skip non-gap_closure plans. If all filtered: "No matching incomplete plans" -> exit.

**Intra-wave dependency validation:** From the phase index, verify that no plan's `depends_on` references another plan in the same wave. If any same-wave dependency exists, stop and report the plan IDs and wave number.

**Parallel file conflict detection:** For waves with two or more plans, compare the indexed `files_modified` sets. If two plans touch the same path, warn and offer to serialize those plans within the wave.

If `INTRA_WAVE_CONFLICT` is true: STOP — present the dependency issue and do not proceed.
If `FILE_CONFLICT` is true: WARN — present the overlap and offer to serialize the conflicting plans within the wave.

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

Read `review_cadence`, `research_mode`, the unattended-minute limits, checkpoint thresholds, `strict_wait`, `never_interrupt_running_workers`, and `never_auto_close_child_agents` from the current staged payload/config. `strict_wait` disables unattended-minute cutoffs entirely; `never_interrupt_running_workers` is the narrower form of the same guarantee. In either case, set plan and wave unattended-minute limits to zero so workers run to natural completion.

**Core invariant:** `autonomy` decides who gets interrupted. `review_cadence` decides when the system must stop, inspect, or re-question. Even in `yolo`, required first-result and pre-fanout gates still run; the difference is that a clean pass can auto-continue.

These gates are task-level safety rails, not line-by-line interruptions. Even in `supervised`, checkpoint after each plan task or required gate, not after every algebraic micro-step.

For each wave, classify whether downstream fanout is risky:

- risky when a wave has multiple plans and any later wave depends on it
- risky when any plan has `task_count >= CHECKPOINT_AFTER_N_TASKS`, no authored checkpoints, or is likely to exceed `MAX_UNATTENDED_MINUTES_PER_PLAN`
- risky for `derivation`, `formalism`, `numerical`, or `validation` phase classes
- risky when file conflicts, convention-lock requirements, or benchmark-critical anchors are present
- risky when the wave creates a new estimator, baseline, or branch point whose downstream usefulness depends on a decisive comparison still to be earned
- never mark a wave "safe" merely because it happens later in the phase or follows an earlier partial pass

When a wave is risky:

- set `FIRST_RESULT_GATE_REQUIRED=true`
- set `PRE_FANOUT_REVIEW_REQUIRED=true`
- set `SEGMENT_TASK_CAP=${CHECKPOINT_AFTER_N_TASKS}`
- force bounded continuation segments even when the authored plan has no checkpoints

**Dense cadence override:** when `review_cadence=dense`, treat every wave as risky regardless of the heuristic checks above, applying the "When a wave is risky" bullets unconditionally (in particular `FIRST_RESULT_GATE_REQUIRED=true` and `PRE_FANOUT_REVIEW_REQUIRED=true`). The "not risky" branch does not apply; a clean pass may auto-continue once the gate fires, but the gate must fire.

When a wave is not risky:

- keep bounded execution available for long plans, wall-clock budgets, and context pressure
- allow checkpoint-free plans to run normally when task count is small and fanout is low

**Skeptical re-questioning rule:** if the first material result only validates a proxy, internal consistency story, or supporting artifact while decisive anchors, benchmark references, or contract-backed acceptance tests remain unresolved, stop and explicitly re-question the framing before allowing downstream fanout. Record:

- weakest unchecked anchor
- what still looks assumed rather than verified
- the disconfirming observation that would most quickly break the current path
- which downstream plans would become wasted work if that decisive evidence failed

**Proposal-first tangent control:** if an unexpected but non-blocking alternative path appears during execution, do not silently pursue it. Treat it as a tangent proposal and classify it using exactly one of these four decisions at the existing review stop:

- `ignore` — not a real tangent; continue the approved mainline plan
- `defer` — record it briefly in the wave report / SUMMARY as future follow-up, then continue the mainline plan
- `branch_later` — recommend `gpd:tangent ...` or `gpd:branch-hypothesis ...` for explicit follow-up, but do not create new side work during this execution pass
- `pursue_now` — only when the user explicitly requested tangent exploration or the approved contract already includes that alternative path

This is proposal-first, not a new execution state machine. Tangent proposals ride on the existing first-result / skeptical / pre-fanout review stops.

When `RESEARCH_MODE=exploit`, suppress optional tangents by default: classify them as `ignore` or `defer` unless the prompt or the user explicitly asked for tangent exploration.
</step>

</process>
