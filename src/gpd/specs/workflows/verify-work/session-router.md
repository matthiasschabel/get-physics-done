<purpose>
Orchestrate conversational verification through a thin session wrapper around `gpd-verifier`.

The verifier owns target construction, proof policy, checks, comparison verdicts, and canonical status. Scientific status ownership and routing vocabulary live in `{GPD_INSTALL_DIR}/references/verification/verification-status-authority.md`. This workflow owns preflight, routing, interaction, sync, diagnosis, and gap repair.
</purpose>
<stage_scope>
Stage id: `session_router`. Owns argument normalization, active-session routing, review preflight, contract-gate checks, lifecycle gate checks, and canonical phase artifact discovery. Do not load proof-redteam, verifier handoff, report schema, or gap-repair authorities here.
</stage_scope>
<process>

<step name="check_type_selection">
## Check Type Selection

Normalize args before init: the first non-flag token is the optional phase; flags may appear anywhere.

```bash
PHASE_ARG=""
VERIFY_FLAGS=()
for token in $ARGUMENTS; do
  case "$token" in
    --*) VERIFY_FLAGS+=("$token") ;;
    *) [ -z "$PHASE_ARG" ] && PHASE_ARG="$token" ;;
  esac
done
VERIFY_FLAG_TEXT="${VERIFY_FLAGS[*]}"
[ -n "$VERIFY_FLAG_TEXT" ] || VERIFY_FLAG_TEXT="--all"
```

Targeted flags narrow the optional check mix only. `--all` or no flags delegates the full package; proof gates, ownership, and fail-closed routing do not change.
</step>

<step name="initialize" priority="first">
Load session-router first; load later stages where used.

```bash
SESSION_ROUTER_INIT=$(gpd --raw init verify-work "${PHASE_ARG}" --stage session_router)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $SESSION_ROUTER_INIT"
  # STOP; surface the error.
fi
```

Parse only `session_router.required_init_fields`.

```bash
export PROJECT_ROOT PHASE_DIR_ABS
PROJECT_ROOT=$(echo "$SESSION_ROUTER_INIT" | gpd json get .project_root)
PHASE_DIR_ABS=$(echo "$SESSION_ROUTER_INIT" | gpd json get .phase_dir_abs --default "")
```

Do not assume reference ledgers, protocol bundles, or report schemas are loaded here.

**If no phase was provided:**

Read `active_verification_sessions` from `SESSION_ROUTER_INIT`. This payload is produced by the canonical verification-status reader from structured frontmatter and is capped to the first five active sessions. Never shell-loop over `GPD/phases` or call `gpd frontmatter get` here.

Active sessions are payload entries with `session_status` of `validating` or `diagnosed`. Route on each entry's canonical `status` / `routing_status` and keep `session_status` conversational only; never let `session_status` overwrite `status`.

If active sessions exist, display:

```
## Active Verification Sessions

1. Phase N: validating; verification gaps_found; score 2/6

Reply with a number to resume, or provide a phase number.
```

Wait for user response; load phase-only stages only after `PHASE_ARG` is set. If none exist, stop with: `No active verification sessions. Provide a phase number (e.g., gpd:verify-work 4)`.

**If non-empty `${PHASE_ARG}` is not found:**

```
ERROR: Phase not found: ${PHASE_ARG}

Available phases:
$(gpd phase list)

Usage: gpd:verify-work <phase>
```

Exit.

Run the centralized review preflight before continuing:

```bash
if [ -n "${PHASE_ARG}" ]; then
  REVIEW_PREFLIGHT=$(gpd validate review-preflight verify-work "${PHASE_ARG}" --strict)
else
  REVIEW_PREFLIGHT=$(gpd validate review-preflight verify-work --strict)
fi
if [ $? -ne 0 ]; then
  echo "$REVIEW_PREFLIGHT"
  exit 1
fi
```

If review preflight exits nonzero, stop and show its blocking issues before any delegation.

If `project_contract_load_info.status` starts with `blocked`, stop and show the surfaced `project_contract_load_info.errors` / `warnings` before delegation.

If `project_contract_validation.valid` is false, stop and show `project_contract_validation.errors` before delegation.

**If `project_contract_gate.authoritative` is not true:** STOP and checkpoint. Show gate/load/validation errors. Do not plan, execute, verify, fingerprint, align, or pass `project_contract` to subagents until repaired. Render the blocked stop through `references/orchestration/stage-stop-envelope.md`: primary `gpd:sync-state` or `gpd:new-project`, then `gpd:verify-work ${PHASE_ARG}` after repair, plus `gpd:suggest-next`.

Run the executable lifecycle authority gate before proof repair, inventory building, contract checks, or verifier delegation:

```bash
LIFECYCLE_CONTRACT_GATE=$(gpd --raw validate lifecycle-contract-gate verify-work "${PHASE_ARG}")
if [ $? -ne 0 ]; then
  echo "$LIFECYCLE_CONTRACT_GATE"
  exit 1
fi
```

Use canonical artifact discovery helpers during bootstrap. `verification_report_status_payload` is the fail-closed status surface for the current phase; if it reports `missing`, `missing_status`, `unparseable`, or `unknown_status`, treat that as pending verification rather than a pass.

```bash
PHASE_INFO=$(gpd --raw roadmap get-phase "${phase_number}")
```

Use `phase_dir_abs` for shell/file IO; `phase_dir` stays the project-relative label. Read all PLAN.md files in `${PHASE_DIR_ABS}/` using the file_read tool.
</step>

<stage_transition>
After `PHASE_ARG` is set and session-router preflight succeeds, load the next active authority with:

```bash
PHASE_BOOTSTRAP_INIT=$(gpd --raw init verify-work "${PHASE_ARG}" --stage phase_bootstrap)
```

Do not load inventory, interactive-validation, gap-repair, verification-report schema, or planner/checker authorities in this stage.
</stage_transition>

</process>
