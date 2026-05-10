<purpose>
Verify fresh plans, route structured checker results, revise blocked plans, and present final planning status.
</purpose>

<stage_boundary>
Final-stage authority: checker handoff, checker result reconciliation, partial approval, revision loop, final status, and next-step offer.
</stage_boundary>

<process>

## 10. Spawn gpd-plan-checker Agent

Display banner (include iteration count if in revision loop):

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 GPD > VERIFYING PLANS (attempt {iteration_count}/3)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

* Spawning plan checker...
```

Refresh the checker/revision payload before entering the checker loop:

```bash
INIT=$(gpd --raw init plan-phase "$PHASE" --stage checker_revision)
if [ $? -ne 0 ]; then
  echo "ERROR: staged plan-phase init failed: $INIT"
  exit 1
fi
# Confirm fields with: gpd --raw stage field-access plan-phase --stage checker_revision --style instruction
# Parse only the checker_revision fields listed in INIT.staged_loading.required_init_fields before use.
```

Read each fresh plan artifact into `PLANS_CONTENT` only after the planner gate passes. Use runtime file-read tooling and the reconciled `FRESH_PLAN_FILES` list; do not rescan the phase directory or include older plan files that were not part of the fresh return.

Checker prompt:

```markdown
<verification_context>
**Phase:** {phase_number}
**Phase Goal:** {goal from ROADMAP}

**Plans to verify:** {plans_content}
**Requirements:** {requirements_content}
**Project Contract:** {project_contract}
**Project Contract Gate:** {project_contract_gate}
**Project Contract Load Info:** {project_contract_load_info}
**Project Contract Validation:** {project_contract_validation}
**Contract Intake:** {contract_intake}
**Effective Reference Intake:** {effective_reference_intake}
**Active References:** {active_reference_context}
**Reference Artifacts:** {reference_artifacts_content}
<protocol_bundle_handoff>
<selected_protocol_bundle_ids>{selected_protocol_bundle_ids}</selected_protocol_bundle_ids>
<protocol_bundle_load_manifest>{protocol_bundle_load_manifest}</protocol_bundle_load_manifest>
<protocol_bundle_context>{protocol_bundle_context}</protocol_bundle_context>
<protocol_bundle_verifier_extensions>{protocol_bundle_verifier_extensions}</protocol_bundle_verifier_extensions>
</protocol_bundle_handoff>
Treat stable knowledge docs in `active_reference_context` and `reference_artifacts_content` as reviewed background synthesis. They may influence assumptions or method choice when consistent with stronger sources, but they do not override `convention_lock`, `project_contract`, the PLAN `contract`, or decisive evidence.
Check that any downstream-gateable reliance on a reviewed knowledge doc is written as explicit `knowledge_deps`, not only implied by background context.

**Phase Context:**
IMPORTANT: Plans MUST honor user decisions. Flag as issue if plans contradict.

- **Decisions** = LOCKED -- plans must implement exactly
- **Agent's Discretion** = Freedom areas -- plans can choose approach
- **Deferred Ideas** = Out of scope -- plans must NOT include

{context_content}
</verification_context>

<physics_verification_criteria>
In addition to structural checks, verify:

- [ ] **Dimensional consistency:** All equations are dimensionally correct
- [ ] **Limiting cases specified:** Plans identify which limits must be recovered and where checks occur
- [ ] **Approximation validity:** Each approximation has stated regime of validity and error estimates
- [ ] **Conservation laws:** Plans respect relevant conservation laws (energy, momentum, charge, unitarity, etc.)
- [ ] **Symmetry preservation:** Approximations and numerical methods preserve relevant symmetries
- [ ] **Independent cross-checks:** At least one independent verification method per major result
- [ ] **Order-of-magnitude sanity:** Expected scales are stated before detailed calculations
- [ ] **Anchor coverage:** Required references, baselines, and prior outputs are surfaced where the plan depends on them
- [ ] **Protocol-bundle coverage:** Selected protocol bundles are reflected in task structure, estimator guards, decisive artifacts, or verification paths
- [ ] **Contract completeness:** Each plan includes decisive claims, deliverables, acceptance tests, forbidden proxies, and uncertainty markers
- [ ] **Decisive outputs:** The plan set covers decisive claims and deliverables rather than only infrastructure or proxy work
- [ ] **Acceptance tests:** Every decisive claim or deliverable has at least one executable or reviewable test
- [ ] **Disconfirming path:** Risky plans name the observation or comparison that would force a rethink
- [ ] **Forbidden proxies:** Proxy-only success conditions are rejected explicitly
- [ ] **Proof-obligation audit path:** Proof-bearing plans expose theorem targets, named parameters/hypotheses/quantifiers, and a sibling `{plan_id}-PROOF-REDTEAM.md` review artifact
- [ ] **Anti-bypass language:** Plans do not rely on `--skip-verify`, sparse cadence, or later human inspection to waive proof red-teaming
</physics_verification_criteria>

<expected_output>

- ## VERIFICATION PASSED -- all checks pass
- ## ISSUES FOUND -- structured issue list
- ## PARTIAL APPROVAL -- some plans approved, others need revision (see partial_approval protocol in your agent instructions)
</expected_output>
```

```
CHECKER_HANDOFF_STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
CHECKER_RETURN=$(
task(
  prompt="First, read {GPD_AGENTS_DIR}/gpd-plan-checker.md for your role and instructions.\n\n" + checker_prompt + "\n\n<spawn_contract>\nwrite_scope:\n  mode: read_only\n  allowed_paths: []\nexpected_artifacts: []\nshared_state_policy: return_only\n</spawn_contract>",
  subagent_type="gpd-plan-checker",
  model="{checker_model}",
  readonly=false,
  description="Verify Phase {phase} plans"
)
)
```

Run this `child_gate`; shared gate and continuation rules live in `references/orchestration/child-artifact-gate.md` and `references/orchestration/continuation-boundary.md`.

```yaml
child_gate:
  id: "plan_checker_review"
  role: "gpd-plan-checker"
  return_profile: "checker"
  required_status: "completed"
  expected_artifacts: []
  allowed_roots: []
  validators:
    - "approved/blocked plan-ID reconciliation against FRESH_PLAN_FILES"
    - "files_written: []"
    - "blocked_plans empty for completed status"
  applicator: none
  failure_route: "fail_closed_or_manual_review | repair_prompt_once | revision_loop_or_fail_closed"
  status_route:
    checkpoint: "record partial approval then revision loop or fresh continuation"
    blocked: "revision loop or manual review"
    failed: "revision loop or manual review"
```

Non-completed: use `status_route`.

## 11. Handle Checker Return

**If the plan-checker agent fails to spawn or returns an error:** Proceed without plan verification. Plans are still executable. Note that verification was skipped and recommend the user review the plans manually before executing. If any plan is proof-bearing, do NOT waive this gate: run an equivalent main-context proof-plan audit against the checker criteria above or STOP and report that proof-obligation planning could not be cleared safely.

Checker presentation headings are non-authority; route through the checker tuple's structured status and plan-list validators.

- **`gpd_return.status: completed`:** Treat as a full pass only after plan-ID reconciliation succeeds. Before accepting the success state, verify:

  1. `approved_plans` names only readable `*-PLAN.md` artifacts in `FRESH_PLAN_FILES`
  2. `blocked_plans` is empty
  3. every approved plan file still exists and matches the approved plan IDs
  4. the checker's `files_written` value does not claim unrelated artifacts

  If any of those checks fail, reject the success state and send the checker output back through the revision loop as a fail-closed mismatch.

  Display iteration-aware confirmation and proceed to step 13 only after reconciliation passes:

  ```
  Plan passed checker (attempt {iteration_count}/3)
  ```

- **`gpd_return.status: checkpoint`:** Some plans passed, others need revision. Split the work:

  1. Record approved plans from the structured `approved_plans` list only.
  2. Record blocked plans from the structured `blocked_plans` list only.
  3. Reject the return if any listed plan ID does not map to a readable `*-PLAN.md` file in `FRESH_PLAN_FILES`.
  4. Display status:

     ```
     Partial approval (attempt {iteration_count}/3): {N_approved} plans approved, {N_blocked} need revision
     ```

  5. Send ONLY the blocked plans from the fresh returned plan set to the revision loop (step 12). Pass the checker's blocker details as `{structured_issues_from_checker}`. Do NOT re-check already-approved plans unless their inputs change during revision, and do not treat preexisting blocked-plan files as revised unless `planner_revision` passes.
  6. After revision + re-check cycle, if the re-check returns `gpd_return.status: completed` for the revised plans, merge approved sets and proceed to step 13. If it returns `gpd_return.status: checkpoint` again, repeat. If `gpd_return.status: failed`, enter standard revision loop for remaining plans.
  7. Approved plans from partial approval are final only after the plan-ID reconciliation checks pass.

- **`gpd_return.status: blocked`:** The checker found a blocker that prevents accepting the current plan set as-is. If `approved_plans` is empty, treat this as a full rejection and send all plans to the revision loop. If `approved_plans` is non-empty, preserve the approved subset only after plan-ID reconciliation passes, then send the blocked subset to the revision loop with the structured issues.

- **`gpd_return.status: failed`:** Display iteration-aware status, show issues, check iteration count, proceed to step 12:

  ```
  Checker found {N} issues (attempt {iteration_count}/3). Revising plan...
  ```

## 12. Revision Loop (Max 3 Iterations)

Maximum iterations: 3. After 3 rejections by the plan-checker:
1. Present the best plan to the user with the checker's remaining objections
2. Ask: "The plan-checker has rejected this plan 3 times. Would you like to: (a) proceed anyway, (b) modify the plan manually, or (c) abandon this phase?"
3. Do NOT loop indefinitely

Track `iteration_count` (starts at 1 after initial plan + check).

**If iteration_count < 3:**

Display: `Checker found issues, revising plan (attempt {N}/3)...`

  Build revision `PLANS_CONTENT` from the reconciled fresh plan set. For partial approval, include only the readable plan files whose IDs are listed in `BLOCKED_PLANS`; for a full rejection, include every readable file in `FRESH_PLAN_FILES`. Do not rescan the phase directory or accept an ambiguous ID match.

Before spawning the revision planner, confirm that every `plan_id` in `BLOCKED_PLANS` maps to exactly one readable `*-PLAN.md` file in `FRESH_PLAN_FILES`. If any blocked ID is missing or ambiguous, stop and report the reconciliation failure rather than inventing a fallback mapping.

Revision prompt:

Use `templates/planner-subagent-prompt.md` here as the stage-local planner template and render its `## Revision Template` section.

```markdown
Render the template's `## Revision Template` into `revision_prompt` with these bindings:

- `{phase_number}` -> {phase_number}
- `{plans_content}` -> {plans_content}
- `{structured_issues_from_checker}` -> {structured_issues_from_checker}
- `{state_content}` -> {state_content}
- `{project_contract}` -> {project_contract}
- `{project_contract_gate}` -> {project_contract_gate}
- `{project_contract_load_info}` -> {project_contract_load_info}
- `{project_contract_validation}` -> {project_contract_validation}
- `{contract_intake}` -> {contract_intake}
- `{effective_reference_intake}` -> {effective_reference_intake}
- `{selected_protocol_bundle_ids}` -> {selected_protocol_bundle_ids}
- `{protocol_bundle_load_manifest}` -> {protocol_bundle_load_manifest}
- `{protocol_bundle_context}` -> {protocol_bundle_context}
- `{protocol_bundle_verifier_extensions}` -> {protocol_bundle_verifier_extensions}
- `{active_reference_context}` -> {active_reference_context}
- `{reference_artifacts_content}` -> {reference_artifacts_content}
- `{context_content}` -> {context_content}
If the revised fix plan still needs specialized tooling or other machine-checkable hard requirements, keep them in PLAN frontmatter `tool_requirements`.
Treat `effective_reference_intake` as the structured source of carry-forward anchors; `active_reference_context` is the readable projection, not the source of truth.

Keep the revision prompt scoped to targeted checker fixes. Do not restate template-owned revision policy here.
```

```
PLANNER_HANDOFF_STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
PLANNER_RETURN=$(
task(
  prompt="First, read {GPD_AGENTS_DIR}/gpd-planner.md for your role and instructions.\n\n" + revision_prompt + "\n\n<spawn_contract>\nwrite_scope:\n  mode: scoped_write\n  allowed_paths:\n    - \"{phase_dir}/*-PLAN.md\"\nexpected_artifacts:\n  - \"revised readable {phase_dir}/*-PLAN.md named in gpd_return.files_written\"\nshared_state_policy: return_only\n</spawn_contract>",
  subagent_type="gpd-planner",
  model="{planner_model}",
  readonly=false,
  description="Revise Phase {phase} plans"
)
)
```

Run this `child_gate`; shared gate and continuation rules live in `references/orchestration/child-artifact-gate.md` and `references/orchestration/continuation-boundary.md`.

```yaml
child_gate:
  id: "planner_revision"
  role: "gpd-planner"
  return_profile: "planner"
  required_status: "completed"
  expected_artifacts:
    - path: "${PHASE_DIR}/*-PLAN.md"
      kind: "glob"
  allowed_roots:
    - "${PHASE_DIR}"
  freshness_marker: "after $PLANNER_HANDOFF_STARTED_AT"
  validators:
    - "gpd validate handoff-artifacts - --expected-glob '${PHASE_DIR}/*-PLAN.md' --allowed-root '${PHASE_DIR}' --required-suffix=-PLAN.md --require-files-written --require-status completed --fresh-after \"$PLANNER_HANDOFF_STARTED_AT\""
    - "gpd validate plan-contract <each fresh plan>"
    - "gpd validate plan-preflight <each fresh plan>"
  applicator: none
  failure_route: "retry_revision_planner_or_manual_revision_or_force_decision | repair_prompt_once | fail_closed | retry_once | repair_path_once | recheck_or_manual_decision"
  status_route:
    checkpoint: "fresh revision-planner continuation after user response"
    blocked: "retry, manual revision, or force decision"
    failed: "retry, manual revision, or force decision"
```

Non-completed: use `status_route`.

**If the revision planner agent fails to spawn or returns an error:** Do not proceed to re-check just because revised `PLAN.md` files exist on disk. Treat them as incomplete until `planner_revision` passes. If no accepted revision return is available, keep the loop fail-closed and offer: 1) Retry revision planner, 2) Apply revisions manually in the main context using checker feedback, 3) Force proceed with current plans despite checker issues.

After planner returns -> spawn checker again (step 10), increment iteration_count. If revising from PARTIAL APPROVAL, only pass the revised plans (not already-approved plans) to the checker.

**If iteration_count >= 3:**

Display: `Max iterations reached. {N} issues remain:` + issue list

Offer: 1) Force proceed, 2) Provide guidance and retry, 3) Abandon

## 13. Present Final Status

Route to `<offer_next>`.

**Structured final status convention:** For clean bounded non-autonomous planning that creates or updates the expected `*-PLAN.md` artifact, has `checkpoint: none`, and has no stale verification, proof-audit, dirty-git, contract, preflight, convention, or checker gate, report `status: green`. Execution remaining as the next command is not by itself a yellow condition. The `PHASE PLANNED` offer and `gpd:execute-phase` route require the fresh-plan validator gate above.

</process>

<offer_next>
Output this markdown directly (not as a code block):

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 GPD > PHASE {X} PLANNED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Phase {X}: {Name}** -- {N} plan(s) in {M} wave(s)

| Wave | Plans  | What it builds |
| ---- | ------ | -------------- |
| 1    | 01, 02 | [objectives]   |
| 2    | 03     | [objective]    |

Research: {Completed | Used existing | Skipped}
Verification: {Passed | Partial (N approved, M revised) | Passed with override | Skipped}

---

## > Next Up

**Execute Phase {X}** -- run all {N} plans

gpd:execute-phase {X}

<sub>Start a fresh context window</sub>

---

**Also available:**

- read `GPD/phases/{phase-dir}/*-PLAN.md` -- review plans
- gpd:plan-phase {X} --research -- re-research first

---

</offer_next>

<success_criteria>

- [ ] GPD/ directory, roadmap phase, and phase directory validated
- [ ] CONTEXT.md loaded early (step 4) and passed to ALL agents
- [ ] Research completed or explicitly skipped; numerical phases carry convergence, uncertainty, benchmark, and forbidden-proxy obligations directly in PLAN, or explicitly route to a required standalone experiment design
- [ ] Existing plans checked; planner and checker spawned with required context
- [ ] Plans created and any CHECKPOINT handled
- [ ] Verification passed OR user override OR max iterations with user decision
- [ ] Plans include dimensional, limiting-case, and approximation-validity checks
- [ ] User sees status between agent spawns
- [ ] User knows next steps
</success_criteria>
