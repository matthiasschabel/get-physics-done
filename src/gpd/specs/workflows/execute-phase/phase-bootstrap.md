<purpose>
Bootstrap phase lookup, contract gates, plan preflight, and branch setup.
</purpose>

<stage_boundary>
First-stage authority only: arguments, bootstrap init, lifecycle gates, plan preflight, and branch setup. Do not load downstream authorities here.
</stage_boundary>

<process>

<step name="normalize_arguments" priority="first">
Normalize phase and flags before any init call. The first non-flag positional token is the phase; flags may appear before or after it.

```bash
PHASE_ARG=""
EXECUTE_FLAGS=()
for token in $ARGUMENTS; do
  case "$token" in
    --*) EXECUTE_FLAGS+=("$token") ;;
    *) [ -z "$PHASE_ARG" ] && PHASE_ARG="$token" ;;
  esac
done
GAPS_ONLY=false
for flag in "${EXECUTE_FLAGS[@]}"; do
  [ "$flag" = "--gaps-only" ] && GAPS_ONLY=true
done

if [ -z "$PHASE_ARG" ]; then
  echo "ERROR: missing phase. Usage: execute-phase <phase-number> [--gaps-only]"
  exit 1
fi
```
</step>

<step name="initialize" priority="first">
Load only the bootstrap stage.

```bash
INIT_STDERR=$(mktemp)
BOOTSTRAP_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage phase_bootstrap 2>"$INIT_STDERR")
INIT_STATUS=$?
if [ "$INIT_STATUS" -ne 0 ] || [ -z "$BOOTSTRAP_INIT" ]; then
  echo "ERROR: gpd initialization failed: execute-phase bootstrap (exit ${INIT_STATUS})."
  [ -n "$BOOTSTRAP_INIT" ] && echo "stdout: $BOOTSTRAP_INIT"
  [ -s "$INIT_STDERR" ] && echo "stderr: $(cat "$INIT_STDERR")"
  rm -f "$INIT_STDERR"
  exit 1
fi
rm -f "$INIT_STDERR"
```

Use `gpd --raw stage field-access execute-phase --stage phase_bootstrap --style instruction` to confirm the manifest-selected bootstrap fields. Read only those keys from `BOOTSTRAP_INIT`; `BOOTSTRAP_INIT.staged_loading.required_init_fields` is the runtime confirmation.

**If `phase_found` is false:** Error -- phase directory not found.
**If `plan_count` is 0:** Error -- no plans found in phase.
**If `state_exists` is false but `GPD/` exists:** Offer reconstruct or continue.

If `project_contract_load_info.status` starts with `blocked`, STOP and show `project_contract_load_info.errors` / `warnings`. If `project_contract_validation.valid` is false, STOP and show `project_contract_validation.errors`. Never treat a visible-but-blocked contract as an approved execution contract.

**If `project_contract_gate.authoritative` is not true:** STOP and checkpoint with the user. Show `project_contract_gate`, `project_contract_load_info.errors`, `project_contract_load_info.warnings`, and `project_contract_validation.errors` if present. Do not plan, execute, verify, fingerprint, align, or pass `project_contract` to subagents until the gate is authoritative. End with `## > Next Up`: primary `gpd:sync-state` or `gpd:new-project` as appropriate, then `gpd:execute-phase ${PHASE_ARG}` after repair, plus `gpd:suggest-next`.

Run the executable lifecycle authority gate before branch handling, plan preflight, wave planning, contract fingerprinting, alignment rendering, or any later-stage delegation:

```bash
LIFECYCLE_CONTRACT_GATE=$(gpd --raw validate lifecycle-contract-gate execute-phase "${PHASE_ARG}")
if [ $? -ne 0 ]; then
  echo "$LIFECYCLE_CONTRACT_GATE"
  exit 1
fi
```

Later staged refreshes surface `effective_reference_intake`, `active_reference_context`, and `reference_artifacts_content` for anchor-aware routing and wave planning. Stable knowledge docs may appear only through those shared reference surfaces as reviewed background; they do not become a separate authority tier. Before branch handling, scripts, computations, dispatches, subagents, writes, or claims, require that the selected `PLAN.md` passes `gpd validate plan-preflight <PLAN.md>`.
</step>

<step name="validate_selected_plans_before_execution" priority="first">
Validate the selected plans before any execution-side work. If this gate fails, do not run workspace scripts, numerical computations, task dispatches, subagents, artifact writes, branch creation, or result claims.
```bash
SELECTED_PLAN_FILES=()
for plan in "$phase_dir"/*-PLAN.md; do
  [ -e "$plan" ] || continue
  if [ "$GAPS_ONLY" = true ]; then
    GAP_CLOSURE=$(gpd frontmatter get "$plan" --field gap_closure 2>/dev/null || echo false)
    [ "$GAP_CLOSURE" = "true" ] || continue
  fi
  SELECTED_PLAN_FILES+=("$plan")
done
if [ ${#SELECTED_PLAN_FILES[@]} -eq 0 ]; then
  echo "ERROR: no executable PLAN.md files found for phase ${PHASE_ARG}. Revise or recreate the missing/invalid plan, then rerun execute-phase for ${PHASE_ARG}."
  exit 1
fi
PLAN_GATE_FAILED=false
for plan in "${SELECTED_PLAN_FILES[@]}"; do
  gpd validate plan-contract "$plan" || PLAN_GATE_FAILED=true
  if ! gpd verify plan "$plan"; then
    PLAN_GATE_FAILED=true
  fi
  PLAN_PREFLIGHT=$(gpd --raw validate plan-preflight "$plan") || {
    echo "ERROR: plan preflight failed for $(basename "$plan")"
    echo "$PLAN_PREFLIGHT"
    PLAN_GATE_FAILED=true
  }
  gpd verify references "$plan" || PLAN_GATE_FAILED=true
done
gpd phase validate-waves "$phase_number" || PLAN_GATE_FAILED=true
if [ "$PLAN_GATE_FAILED" = true ]; then
  echo "Plan validation/preflight failed before execution; no workspace scripts, numerical computations, task dispatches, subagents, artifact writes, or result claims were authorized."
  echo "Next: revise or recreate the invalid PLAN.md, then rerun execute-phase for ${PHASE_ARG}."
  exit 1
fi
```
`gpd:plan-phase {N}` is the supported public plan repair route. Invoke it with explicit instructions to revise or recreate the invalid `PLAN.md`, then rerun `gpd:execute-phase {N}`.
</step>

<step name="handle_branching">
Check `branching_strategy` from init:

**"none":** Skip, continue on current branch.

**"per-phase" or "per-milestone":** Use pre-computed `branch_name` from init:

```bash
git checkout -b "$BRANCH_NAME" 2>/dev/null || git checkout "$BRANCH_NAME"
```

All subsequent commits go to this branch. User handles merging.
</step>

</process>
