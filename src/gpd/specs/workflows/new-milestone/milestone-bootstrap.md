<purpose>

Start a new research milestone cycle for an existing project. Uses staged init to load milestone context, gathers milestone goals from MILESTONE-CONTEXT.md or conversation, updates PROJECT.md and STATE.md, optionally runs a task-local parallel literature survey, defines scoped research objectives with REQ-IDs, and hands off to the roadmapper through a fresh typed continuation with freshness checks. Continuation equivalent of new-project.

</purpose>

<required_reading>

Read all files referenced by the invoking prompt's execution_context before starting.

</required_reading>

<process>

## 1. Bootstrap and Load Context

```bash
INIT=$(gpd --raw init new-milestone --stage milestone_bootstrap)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $INIT"
  exit 1
fi
```

Use `gpd --raw stage field-access new-milestone --stage milestone_bootstrap --style instruction` to confirm the manifest-selected bootstrap fields. Read only those keys from `INIT`; `INIT.staged_loading.required_init_fields` is the runtime confirmation.

**Mode-aware behavior:**
- `autonomy=supervised` (default): Pause for user confirmation after requirements gathering and before roadmap generation.
- `autonomy=balanced`: Execute the full pipeline automatically and pause only if milestone scope is ambiguous or requirements conflict with prior work.
- `autonomy=yolo`: Execute full pipeline, skip optional research step, auto-approve roadmap, but do NOT skip phase-level contract coverage and anchor visibility.
- `research_mode=explore`: Broader research survey for new milestone, consider alternative approaches, include speculative phases.
- `research_mode=exploit`: Focused research on direct extensions of prior milestone, lean phase structure.
- `research_mode=balanced` (default): Use the standard research depth for the milestone and keep the default anchor and contract coverage unless the milestone needs broader or narrower review.
- `research_mode=adaptive`: Reuse a focused path only when prior milestones already provide decisive evidence or an explicit approach lock. Otherwise refresh broader gap analysis before narrowing the new milestone.

Run centralized context preflight before continuing:

```bash
CONTEXT=$(gpd --raw validate command-context new-milestone "$ARGUMENTS")
if [ $? -ne 0 ]; then
  echo "$CONTEXT"
  exit 1
fi
```

`{GPD_INSTALL_DIR}/references/orchestration/contract-authority-gate.md`

Apply the shared contract authority gate: `project_contract` is authoritative milestone scope only when `project_contract_gate.authoritative` is true, with `project_contract_load_info` and `project_contract_validation` kept visible as gate inputs.

Treat init as staged:
- Use this bootstrap init for milestone identity and contract gate state only.
- Run a survey/objectives init before milestone scoping and treat that refresh as the source of truth for carry-forward reference intake, artifact snapshots, and prior-project file context.
- Run a fresh late-stage init immediately before roadmapping and treat that later init as the source of truth for the final handoff.

**If `roadmap_exists` is true:** Note — existing ROADMAP.md will be replaced by this milestone's roadmap.

Load project files:

- Read PROJECT.md (existing project, answered questions, decisions)
- Read MILESTONES.md (if exists — may not exist for first milestone)
- Read STATE.md (if `state_exists` — pending items, blockers)
- Check for MILESTONE-CONTEXT.md (from milestone discussion)
- Continue applying the contract authority gate while gathering goals, determining milestone version, and reviewing roadmap coverage.
- If `project_contract_gate.authoritative` is false, checkpoint with the user and repair the stored contract before using it for milestone scope.


<stage_handoff>
When bootstrap routing is complete, reload `survey_objectives` with:

```bash
SURVEY_INIT=$(gpd --raw init new-milestone --stage survey_objectives)
```

Then load only that stage's `staged_loading.eager_authorities` before gathering goals, reading scoped reference artifacts, running optional scouts, or drafting objectives.
</stage_handoff>

</process>
