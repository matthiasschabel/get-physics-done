<purpose>
Orchestrate conversational verification through a thin session wrapper around `gpd-verifier`.

The verifier owns target construction, proof policy, checks, comparison verdicts, and canonical status. Scientific status ownership and routing vocabulary live in `{GPD_INSTALL_DIR}/references/verification/verification-status-authority.md`. This workflow owns preflight, routing, interaction, sync, diagnosis, and gap repair.
</purpose>
<philosophy>
**Do not duplicate verifier policy here.**

- Fail closed before delegation if the project, roadmap, contract, or proof readiness are not usable.
- Use `{GPD_INSTALL_DIR}/references/verification/verification-status-authority.md` for status ownership and vocabulary; this wrapper gates artifacts and routes, but does not decide the scientific verdict.
- Present verifier-produced evidence one check at a time and record only the session overlay in this workflow.
- Every spawned agent is a one-shot delegation: if it needs user input or new evidence arrives after return, start a fresh continuation; never send more input to closed child.
- File-producing handoffs must prove the expected artifact exists before success is accepted.
</philosophy>
<shared_contract_floor>
**Project Contract Gate:** {project_contract_gate}
**Project Contract Load Info:** {project_contract_load_info}
**Project Contract Validation:** {project_contract_validation}
**Contract Intake:** {contract_intake}
**Effective Reference Intake:** {effective_reference_intake}

Treat `project_contract` as authoritative only when `project_contract_gate.authoritative` is true. A visible-but-blocked contract must be repaired before it is used as authoritative verification scope; keep the same contract-critical floor at all times.
Treat `effective_reference_intake` as the structured source of carry-forward anchors; `active_reference_context` is the readable projection, not the source of truth.
Do NOT skip contract-critical anchors.
</shared_contract_floor>
@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md

<process>

<step name="plan_gap_closure">
**Auto-plan fixes from diagnosed gaps**

Display:

```
====================================================
 GPD > PLANNING FIXES
====================================================

* Spawning planner for gap closure...
```

Spawn `gpd-planner` in `--gaps` mode as a fresh one-shot delegation from the staged gap-repair payload.
First, read {GPD_AGENTS_DIR}/gpd-planner.md for your role and instructions.
Use `templates/planner-subagent-prompt.md` to build the gap_closure planner handoff from the staged payload. Keep `tool_requirements`, the checker feedback, and other machine-checkable hard requirements explicit.
Bind the template's protocol fields from the gap-repair payload: `{selected_protocol_bundle_ids}`, `{protocol_bundle_load_manifest}`, `{protocol_bundle_context}`, and `{protocol_bundle_verifier_extensions}`. Do not collapse verifier extensions into the rendered context block.

> Apply the canonical runtime delegation convention above; planner status, freshness, continuation, and failure routing use the tuple below.

Set `GAP_PLANNER_HANDOFF_STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")` immediately before spawning.

Gap planner child artifact gate: apply `references/orchestration/child-artifact-gate.md`; checkpoint handling applies `references/orchestration/continuation-boundary.md`.

```yaml
child_gate:
  id: "verify_work_gap_planner"
  role: "gpd-planner"
  return_profile: "planner"
  required_status: "completed"
  expected_artifacts:
    - path: "${PHASE_DIR_ABS}/*-PLAN.md"
      kind: "glob"
  allowed_roots:
    - "${PHASE_DIR_ABS}"
  freshness_marker: "after $GAP_PLANNER_HANDOFF_STARTED_AT"
  validators:
    - "gpd validate handoff-artifacts - --expected-glob '${PHASE_DIR_ABS}/*-PLAN.md' --allowed-root '${PHASE_DIR_ABS}' --required-suffix=-PLAN.md --require-files-written --require-status completed --fresh-after \"$GAP_PLANNER_HANDOFF_STARTED_AT\""
    - "gpd validate plan-contract <each fresh gap plan>"
    - "gpd validate plan-preflight <each fresh gap plan>"
  applicator: none
  failure_route: "fail_closed -> gpd:plan-phase ${phase_number} --gaps | repair_prompt_once | fresh_gap_planner_continuation"
```

If the planner fails to spawn or returns an error, keep the session fail-closed and offer retry or manual plan creation. Do not fall through to gap verification on the basis of preexisting `PLAN.md` files alone. End with the same `gpd:plan-phase ${phase_number} --gaps` Next Up route.
</step>

<step name="verify_gap_plans">
**Verify fix plans with checker**

Display:

```
====================================================
 GPD > VERIFYING FIX PLANS
====================================================

* Spawning plan checker...
```

Spawn `gpd-plan-checker` as a fresh one-shot delegation.

> Apply the canonical runtime delegation convention above; checker status and continuation routing use the tuple below.

Set `GAP_CHECKER_HANDOFF_STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")` immediately before spawning.

Gap plan-checker child artifact gate: apply `references/orchestration/child-artifact-gate.md`; checkpoint handling applies `references/orchestration/continuation-boundary.md`.

```yaml
child_gate:
  id: "verify_work_gap_plan_checker"
  role: "gpd-plan-checker"
  return_profile: "checker"
  required_status: "completed"
  expected_artifacts: []
  allowed_roots: []
  validators:
    - "fresh planner PLAN.md artifacts remain readable and named in planner files_written"
    - "approved_plans and blocked_plans reconcile to fresh gap plans"
    - "files_written: []"
  applicator: none
  failure_route: "manual_review_or_fail_closed | repair_prompt_once | fail_closed | revision_loop_or_fail_closed"
```

Status route: `checkpoint` records approved/blocked plans for gap revision; `blocked` routes to `gpd:plan-phase ${phase_number} --gaps`; `failed` routes to retry or manual revision.

If the checker fails to spawn or returns an error, proceed without plan verification but note that the plans were not verified.

If the checker returns a structured `gpd_return`, route on `gpd_return.status` and the structured plan lists, not on presentation text:

- `completed`: treat the fresh fix plans as verified only after the on-disk files still match the planner's `files_written` set.
- `checkpoint`: some plans are approved and others need revision; record `approved_plans` and `blocked_plans`, then send only the blocked plans back through the revision loop. If stopping for user input, end with `## > Next Up`: primary `gpd:resume-work`, plus `gpd:plan-phase ${phase_number} --gaps` and `gpd:suggest-next`.
- `blocked`: nothing is approved; feed the checker issues and blocked plan IDs back into the revision loop without rewriting approved plans. If stopping, use the same Next Up route.
- `failed`: present the issues and offer retry or manual revision. End with `## > Next Up`: primary `gpd:plan-phase ${phase_number} --gaps`, plus `gpd:resume-work` and `gpd:suggest-next`.
</step>

<step name="revision_loop">
**Iterate planner <-> checker until plans pass, up to 3 rounds**

If the checker reports issues, send a fresh planner continuation from the staged gap-repair payload with the checker feedback. After the planner returns, run the checker again. Each agent turn is one-shot; do not keep either agent alive across user interaction.
When the checker returns `checkpoint` or `blocked`, use the structured `approved_plans`, `blocked_plans`, and `issues` fields to decide which plans to revise. Use the structured fields, not the human-readable approval table, as the source of truth. Do not rewrite approved plans during the revision round.
First, read {GPD_AGENTS_DIR}/gpd-planner.md for your role and instructions.
Use `templates/planner-subagent-prompt.md` again for checker-driven gap_closure revisions.
Again bind `{selected_protocol_bundle_ids}`, `{protocol_bundle_load_manifest}`, `{protocol_bundle_context}`, and `{protocol_bundle_verifier_extensions}` from the staged gap-repair payload so revision planners keep verifier-extension obligations visible.

If iteration count reaches 3, stop and offer the user:

1. Force proceed
2. Provide guidance and retry
3. Abandon and exit

End that stop with `## > Next Up`: primary `gpd:plan-phase ${phase_number} --gaps`, plus `gpd:execute-phase ${phase_number} --gaps-only`, `gpd:verify-work ${phase_number}`, and `gpd:suggest-next`.
</step>

<step name="complete_session">
**Complete validation and commit**

Update the verification file overlay:

- `verified`: now
- `updated`: now
- `session_status`: `completed`

Clear the current check display to indicate completion.

Run `gpd validate verification-contract "${PHASE_DIR_ABS}/${phase_number}-VERIFICATION.md"` before committing it; invalid reports stop non-green and do not advance state.

```bash
gpd commit "verify(${phase_number}): complete research validation - {passed} passed, {issues} issues" --files "${PHASE_DIR_ABS}/${phase_number}-VERIFICATION.md"
```

**Atomically advance shared state** so `gpd:progress` / `gpd:show-phase` reflect the verifier outcome without a manual `gpd:sync-state`:

```bash
gpd --raw state record-verification --phase "${phase_number}"
```

`record-verification` uses the canonical verification-status reader (`passed` -> `Verified`; canonical non-passed -> `Blocked`; missing, unparseable, or unknown status fails closed without changing state).
Do not pass `--status` here or for acknowledgement; legacy/admin overrides require no verifier frontmatter and cannot turn limitations into passes. Barrier: wait before state get/validate/repair; never parallelize state mutation with validation.

Present the summary of passed, issue, and skipped checks. Do not relax verifier fail-closed results.

End with `## > Next Up`:

- If verification passed and more phases remain: primary `gpd:discuss-phase ${next_phase}` when context is missing, otherwise `gpd:plan-phase ${next_phase}`
- If verification passed and the milestone is complete: primary `gpd:complete-milestone`
- If gaps remain: primary `gpd:plan-phase ${phase_number} --gaps`; after gap plans exist, `gpd:execute-phase ${phase_number} --gaps-only`; confirm with `gpd:verify-work ${phase_number}`
- Always include `gpd:suggest-next` as the recovery/confirmation command
- Include `<sub>Start a fresh context window, then run the primary command above.</sub>`
</step>

</process>

<update_rules>
Write only when needed:

1. issue found
2. session complete
3. every 5 passed checks as a safety net

Keep the current check display, summary, and session overlay in sync with the verifier output. The canonical verifier report content remains owned by `gpd-verifier`.
</update_rules>

<success_criteria>

- [ ] `verify-work` stays thin and does not duplicate verifier policy
- [ ] Preflight, review gating, session routing, diagnosis, and gap repair remain in the workflow
- [ ] `gpd-verifier` owns canonical target extraction, evidence mapping, proof policy, checks, and status
- [ ] Spawned agents use one-shot delegation with checkpoint-and-restart semantics after user input
- [ ] File-producing handoffs verify expected artifacts on disk before success is accepted
- [ ] The verification overlay is written only after authoritative verifier output is available
- [ ] Researcher responses are processed as pass / issue / skip
- [ ] Final session closeout validates and commits the verification file without recomputing verifier policy

</success_criteria>
