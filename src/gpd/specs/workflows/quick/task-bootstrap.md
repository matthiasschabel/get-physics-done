<purpose>
Execute small, ad-hoc physics tasks with GPD guarantees while skipping optional agents. Quick mode routes through the canonical planner handoff, loads staged quick init at the task-bootstrap and default task-authoring boundaries, selects the separate `reference_context` stage only when a task actually needs project reference artifacts, tracks `GPD/quick/`, and records structured completion. Tasks: derivation, dimensional/OOM check, limit, DOI. Quick mode is NOT authorized to close theorem-style or `proof_obligation` work.
</purpose>

<required_reading>
Read all files referenced by the invoking prompt's execution_context before starting.
</required_reading>

<quick_authorities>
@{GPD_INSTALL_DIR}/references/quick/quick-mode-boundary.md
@{GPD_INSTALL_DIR}/references/quick/quick-durability-minimum.md
@{GPD_INSTALL_DIR}/references/quick/quick-reroute-rules.md
</quick_authorities>

<process>
**Step 1: Get task description**

Ask for the task description as a single freeform prompt. Do not use the shared structured-choice fallback here; there are no fixed option labels to preserve.

Ask ONE question inline (freeform, NOT ask_user):

```text
What quick task do you want to do? Examples:
  - Quick derivation of the equation of motion from the Lagrangian
  - Dimensional check on the cross-section formula in eq. (3.14)
  - Order-of-magnitude estimate for the tunneling rate
  - Verify the non-relativistic limiting case of the dispersion relation
  - Look up the DOI for a specific bibliography item
```

Store response as `$DESCRIPTION`.

If empty, re-prompt: "Please provide a task description."

---

**Step 2: Initialize**

```bash
TASK_BOOTSTRAP_INIT=$(gpd --raw init quick "$DESCRIPTION" --stage task_bootstrap)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $TASK_BOOTSTRAP_INIT"
  # STOP; surface the error.
fi
INIT="$TASK_BOOTSTRAP_INIT"
```

Use `gpd --raw stage field-access quick --stage task_bootstrap --style instruction` to confirm the manifest-selected bootstrap fields. Read only those keys from `TASK_BOOTSTRAP_INIT`; `TASK_BOOTSTRAP_INIT.staged_loading.required_init_fields` is the runtime confirmation.

The bootstrap and default `task_authoring` payloads intentionally do not include the staged reference-runtime payload. Before the planner handoff, reload either:

- `task_authoring` for the default small-task path.
- `reference_context` only when the quick-mode boundary rules say the task really needs active project references, reference artifacts, literature/research-map files, or a targeted source lookup.

Treat the selected staged init payload's `staged_loading` block as authoritative for the planner handoff shape rather than reconstructing a separate quick-specific prompt contract.

**Mode-aware behavior:**
- `autonomy=supervised` (default): Pause after the plan for user approval before execution.
- `autonomy=balanced`: Execute without pausing unless the quick task reveals a real decision point.
- `autonomy=yolo`: Execute and commit without pausing.

**If `project_exists` is false:** Error -- Quick mode requires an initialized project with `GPD/PROJECT.md`. Run `gpd:new-project` first.

**If `planning_exists` is false:** Error -- Quick mode requires the `GPD/` workspace directory. Run `gpd:new-project` first.

Quick tasks can run mid-phase and do NOT require ROADMAP.md. They still require an initialized project workspace with `GPD/PROJECT.md` and the `GPD/` directory.
Quick mode still inherits the approved `project_contract` only when `project_contract_gate.authoritative` is true. The default small-task path does not load the full active reference ledger; select `reference_context` only when the task needs that ledger. Do not bypass required anchors, baselines, or forbidden-proxy constraints just because the task is small.

**Reroute block:** Apply `quick-reroute-rules.md`. If the description or inherited contract indicates theorem-style, proof-bearing, publication-grade, referee-response, manuscript proof-review, or claim-adjudication work, STOP instead of using quick mode. A generic manuscript or task "claim" is not enough by itself, but a formal proof target or `proof_obligation` is enough. Do not bypass this by asking for a "quick sketch", "light proof", or "just the main idea". Route explicitly to:

- `gpd:plan-phase <phase>` when this belongs in planned phase work
- `gpd:derive-equation "<goal>"` when you need a derivation/proof draft
- `gpd:verify-work <phase>` only after a canonical proof-redteam artifact exists

---

**Step 3: Create task directory**

Use `task_dir` from init JSON (for example, `GPD/quick/NNN-slug/`):

```bash
QUICK_DIR="${task_dir}"
mkdir -p "$QUICK_DIR"
```

Report to user:

```
Creating quick task ${next_num}: ${DESCRIPTION}
Directory: ${QUICK_DIR}
```

---

<stage_boundary>
This is the first-stage authority for `gpd:quick`. It owns task intake, bootstrap init, reroute gating, and quick directory creation only. Do not load `workflows/quick.md` or the downstream authoring authority while this stage is active.
</stage_boundary>

<stage_handoff>
After Step 3 creates `${QUICK_DIR}`, choose the next stage using the quick boundary rules:

- `task_authoring` for the default small-task path.
- `reference_context` only for targeted source lookup or tasks that need active project anchors, existing reference artifacts, literature/research-map files, or protocol/reference context.

Reload with `gpd --raw init quick "$DESCRIPTION" --stage task_authoring` or `gpd --raw init quick "$DESCRIPTION" --stage reference_context`, then follow `staged_loading.eager_authorities` for the active stage, primarily `workflows/quick/task-authoring.md`. Do not continue from bootstrap memory into planner or executor handoffs.
</stage_handoff>

</process>
