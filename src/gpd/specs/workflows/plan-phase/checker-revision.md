<purpose>
Verify fresh plans, route structured checker results, revise only blocked plans,
and present final planning status after the active checker/revision event has
resolved.
</purpose>

<stage_boundary>
Final-stage authority is event-local. Start with `checker_handoff`; do not use
return routing until a `CHECKER_RETURN` or spawn error exists. Do not use
revision planner machinery until blocked plan IDs are reconciled. Do not show
max-iteration choices unless the revision limit is exhausted. Do not render the
final offer until a green, override, or skipped checker status has been selected.
</stage_boundary>

<process>

## 10. Event: checker_handoff

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
# Apply INIT.staged_loading.field_access_instruction before using this payload.
```

Read each fresh plan artifact into `PLANS_CONTENT` only after the planner gate
passes. Use runtime file-read tooling and the reconciled `FRESH_PLAN_FILES`
list; do not rescan the phase directory or include older plan files that were
not part of the fresh planner return.

Initial checker event exclusions: do not display revision planner prompts,
max-iteration choices, or the final planning offer during `checker_handoff`.
This event only prepares local checker context and spawns the one-shot checker.

Checker prompt:

```markdown
<verification_context>
**Phase:** {phase_number}
**Phase Goal:** {goal from ROADMAP}

**Plans to verify:** {plans_content}
Use `INIT.staged_loading.field_access_instruction` as the prompt inventory. Include the project contract/gate values, `contract_intake`,
`effective_reference_intake`, and selected reference path handles from that
staged payload; do not request rendered reference or artifact body fields.
<protocol_bundle_handoff>
<selected_protocol_bundle_ids>{selected_protocol_bundle_ids}</selected_protocol_bundle_ids>
<protocol_bundle_load_manifest>{protocol_bundle_load_manifest}</protocol_bundle_load_manifest>
<protocol_bundle_verifier_extensions>{protocol_bundle_verifier_extensions}</protocol_bundle_verifier_extensions>
</protocol_bundle_handoff>
Treat reference paths as handles, not preloaded bodies. Read a selected path only
when a checker finding depends on quoting or decisive comparison evidence;
reviewed knowledge docs never override `convention_lock`, `project_contract`,
the PLAN `contract`, or decisive evidence.
Check that any downstream-gateable reliance on a reviewed knowledge doc is
written as explicit `knowledge_deps`, not only implied by background context.

**Phase Context:**
IMPORTANT: Plans MUST honor user decisions. If context is needed, read
`${PHASE_DIR}/*-CONTEXT.md`; locked decisions must be implemented exactly,
discretion areas may be chosen by the plan, and deferred ideas remain out of
scope.
</verification_context>

<local_checker_criteria>
The checker agent owns the full verification dimensions and return structure.
This handoff adds only local plan-phase constraints:

- [ ] **Decisive outputs / acceptance tests:** Plans cover decisive claims and
      deliverables, with executable or reviewable tests, rather than proxy-only
      infrastructure.
- [ ] **Anchor and protocol coverage:** Required references, baselines, prior
      outputs, and protocol bundles are explicit where the plan depends on them.
- [ ] **Physics sanity:** Dimensional consistency, limiting cases,
      approximation validity, conservation/symmetry obligations, independent
      cross-checks, and expected scales are explicit where relevant.
- [ ] **Disconfirming path / forbidden proxies:** Risky plans name what would
      force a rethink and reject proxy-only success conditions.
- [ ] **Proof-obligation audit path:** Proof-bearing plans expose theorem
      targets, named parameters/hypotheses/quantifiers, and a sibling
      `{plan_id}-PROOF-REDTEAM.md` review artifact.
- [ ] **Anti-bypass language:** Plans do not rely on `--skip-verify`, sparse
      cadence, or later human inspection to waive proof red-teaming.
</local_checker_criteria>

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

Keep this local checker gate tuple with the handoff. Run this `child_gate` only
after `CHECKER_RETURN` exists; shared acceptance and continuation rules live in
`references/orchestration/child-artifact-gate.md` and
`references/orchestration/continuation-boundary.md`.

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

Non-completed checker returns use `status_route` in `checker_return_routing`.

Stop this event after the checker call. Continue to `checker_return_routing`
only when the runtime has a checker spawn error or a fenced `CHECKER_RETURN`.

## 11. Event: checker_return_routing

Checker presentation headings are non-authority. Route through a valid fenced
`gpd_return.status`, structured `approved_plans`, structured `blocked_plans`,
`issues`, and the `plan_checker_review` child gate tuple. Do not treat file
existence, logs, headings, or old artifacts as checker success.

**If the plan-checker agent fails to spawn or returns an error:** Proceed
without plan verification only for non-proof-bearing plan sets. Plans are still
executable, but note that verification was skipped and recommend manual review
before execution. If any plan is proof-bearing, do NOT waive this gate: run an
equivalent main-context proof-plan audit against the checker criteria above or
STOP and report that proof-obligation planning could not be cleared safely.

**Plan-ID reconciliation is required before accepting any checker route:**

1. Build the candidate ID set only from structured `approved_plans` and `blocked_plans`; headings and tables are display-only.
2. Every candidate ID must map to exactly one readable `*-PLAN.md` artifact in
   `FRESH_PLAN_FILES`.
3. Reject overlaps between approved and blocked IDs.
4. Reject any listed ID that is missing, ambiguous, unreadable, or outside the
   fresh returned plan set.
5. Reject any checker `files_written` value other than `[]`.
6. Preserve approved IDs only after these checks pass.

- **`gpd_return.status: completed`:** Treat as a full pass only after plan-ID
  reconciliation succeeds. Before accepting the success state, verify:

  1. `approved_plans` names only readable `*-PLAN.md` artifacts in `FRESH_PLAN_FILES`
  2. `blocked_plans` is empty
  3. every approved plan file still exists and matches the approved plan IDs
  4. the approved set covers every fresh plan file that must proceed to execution
  5. the checker's `files_written` value does not claim unrelated artifacts

  If any check fails, reject the success state and send the checker output to
  `blocked_plan_revision_branch` as a fail-closed mismatch. If reconciliation
  passes, display:

  ```
  Plan passed checker (attempt {iteration_count}/3)
  ```

- **`gpd_return.status: checkpoint`:** Record approved plans from the structured
  `approved_plans` list only and blocked plans from the structured
  `blocked_plans` list only. Reject the return if any listed plan ID does not
  map to a readable `*-PLAN.md` file in `FRESH_PLAN_FILES`. Display:

     ```
     Partial approval (attempt {iteration_count}/3): {N_approved} plans approved, {N_blocked} need revision
     ```

  Send ONLY the blocked plans from the fresh returned plan set to
  `blocked_plan_revision_branch`. Pass `{structured_issues_from_checker}`. Do
  NOT re-check already-approved plans unless their inputs change during
  revision, and do not treat preexisting blocked-plan files as revised unless
  `planner_revision` passes. Approved plans from partial approval are final only
  after the plan-ID reconciliation checks pass.

- **`gpd_return.status: blocked`:** The checker found a blocker that prevents
  accepting the current plan set as-is. If `approved_plans` is empty, treat this
  as a full rejection and set `BLOCKED_PLANS` to every current fresh plan ID. If
  `approved_plans` is non-empty, preserve the approved subset only after
  plan-ID reconciliation passes, then send the blocked subset to
  `blocked_plan_revision_branch` with the structured issues.

- **`gpd_return.status: failed`:** Display iteration-aware status, show issues,
  and set `BLOCKED_PLANS` to the reconciled blocked IDs if present, otherwise to
  every current fresh plan ID:

  ```
  Checker found {N} issues (attempt {iteration_count}/3). Revising plan...
  ```

After this event, either route to `planning_final_offer` with a green, skipped,
or override status, or route to `blocked_plan_revision_branch` with reconciled
`BLOCKED_PLANS` and `{structured_issues_from_checker}`.

## 12. Event: blocked_plan_revision_branch

Enter this branch only after `checker_return_routing` has isolated blocked plan
IDs or a fail-closed mismatch. Revision planner machinery is branch-local here;
do not build a revision prompt until the blocked subset and the user's
exhaustion choice, if needed, are known.
The branch invariant is that blocked plan IDs are reconciled before planner
machinery appears.

Before any revision handoff:

1. Build revision `PLANS_CONTENT` from the reconciled fresh plan set.
2. For partial approval, include only the readable plan files whose IDs are
   listed in `BLOCKED_PLANS`.
3. For a full rejection, include every readable file in `FRESH_PLAN_FILES`.
4. Do not rescan the phase directory or accept an ambiguous ID match.
5. Confirm that every `plan_id` in `BLOCKED_PLANS` maps to exactly one readable
   `*-PLAN.md` file in `FRESH_PLAN_FILES`. If any blocked ID is missing or
   ambiguous, stop and report the reconciliation failure rather than inventing a
   fallback mapping.

Maximum iterations: 3. Track `iteration_count` (starts at 1 after initial plan
+ check).

**If iteration_count >= 3:**

Display: `Max iterations reached. {N} issues remain:` + issue list.

Ask only now: "The plan-checker has rejected this plan 3 times. Would you like
to: (a) proceed anyway, (b) modify the plan manually, or (c) abandon this
phase?"

- Force proceed: route to `planning_final_offer` with checker status `override`
  and include the remaining objections.
- Modify manually / provide guidance and retry: collect the user's guidance,
  keep the reconciled `BLOCKED_PLANS`, and then continue to
  `revision_planner_handoff`.
- Abandon: stop with the current checker objections and no execute-phase offer.

Do NOT loop indefinitely.

**If iteration_count < 3:** Display
`Checker found issues, revising plan (attempt {N}/3)...` and continue directly
to `revision_planner_handoff`.

## 12a. Event: revision_planner_handoff

Use this event only from `blocked_plan_revision_branch` after blocked plan IDs
are reconciled and any required user choice has selected retry/manual-guided
revision.

Revision prompt:

Load the `revision_template_rendering` conditional authority pack first. Use
`templates/planner-subagent-prompt.md` here as the stage-local planner template
and render its `## Revision Template` section.

```markdown
Render the template's `## Revision Template` into `revision_prompt` with fresh
blocked-plan content, checker issues, and these staged bindings. Do not add
unselected body fields.

- `{phase_number}` -> {phase_number}
- `{plans_content}` -> {plans_content}
- `{structured_issues_from_checker}` -> {structured_issues_from_checker}
- `{project_contract}` -> {project_contract}
- `{project_contract_gate}` -> {project_contract_gate}
- `{project_contract_load_info}` -> {project_contract_load_info}
- `{project_contract_validation}` -> {project_contract_validation}
- `{contract_intake}` -> {contract_intake}
- `{effective_reference_intake}` -> {effective_reference_intake}
- `{selected_protocol_bundle_ids}` -> {selected_protocol_bundle_ids}
- `{protocol_bundle_load_manifest}` -> {protocol_bundle_load_manifest}
- `{protocol_bundle_verifier_extensions}` -> {protocol_bundle_verifier_extensions}
- `{reference_artifact_files}` -> {reference_artifact_files}
- `{literature_review_files}` -> {literature_review_files}
- `{research_map_reference_files}` -> {research_map_reference_files}
If the revised fix plan still needs specialized tooling or other
machine-checkable hard requirements, keep them in PLAN frontmatter
`tool_requirements`.
Treat `effective_reference_intake` as the structured source of carry-forward
anchors; read reference paths by handle only for targeted checker fixes.

Keep the revision prompt scoped to targeted checker fixes. Do not restate
template-owned revision policy here.
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

Run this `child_gate`; shared gate and continuation rules live in
`references/orchestration/child-artifact-gate.md` and
`references/orchestration/continuation-boundary.md`.

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

**If the revision planner agent fails to spawn or returns an error:** Do not
proceed to re-check just because revised `PLAN.md` files exist on disk. Treat
them as incomplete until `planner_revision` passes. If no accepted revision
return is available, keep the loop fail-closed and offer: 1) Retry revision
planner, 2) Apply revisions manually in the main context using checker
feedback, 3) Force proceed with current plans despite checker issues.

After planner returns, update `FRESH_PLAN_FILES` only from the accepted
`planner_revision` return, increment `iteration_count`, and return to
`checker_handoff`. If revising from PARTIAL APPROVAL, only pass the revised
plans, not already-approved plans, to the checker.

## 13. Event: planning_final_offer

Route here only after `checker_return_routing` has selected one of these final
checker states:

- `green`: checker completed, plan-ID reconciliation passed, blocked set empty
- `override`: max iterations exhausted and the user chose to proceed anyway
- `skipped`: checker was unavailable for a non-proof-bearing plan set and the
  user-visible status records the skip

Do not render the final offer from initial checker handoff state, from a pending
checkpoint, from unreconciled blocked IDs, or from a failed revision planner.

**Structured final status convention:** For clean bounded non-autonomous planning
that creates or updates the expected `*-PLAN.md` artifact, has `checkpoint: none`,
and has no stale verification, proof-audit, dirty-git,
contract, preflight, convention, or checker gate, report `status: green`.
Execution remaining as the next command is not by itself a yellow condition. The
`PHASE PLANNED` offer and `gpd:execute-phase` route require the fresh-plan
validator gate above and one of the final checker states listed in this event.

Route to `<offer_next>`.

</process>

<offer_next>
Output a compact `GPD > PHASE {X} PLANNED` offer directly, not as a code block.
Include phase name, plan/wave count, research status, final checker status, and
`## > Next Up` with primary `gpd:execute-phase {X}`. Also list plan review and
`gpd:plan-phase {X} --research` as secondary options.

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
