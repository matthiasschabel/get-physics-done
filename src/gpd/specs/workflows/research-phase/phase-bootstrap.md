<purpose>
Research mathematical methods, physical principles, and computational tools needed to approach a phase. Spawns gpd-phase-researcher with phase context.

Standalone, one-shot research command. For most workflows, use `gpd:plan-phase` which integrates research automatically.
</purpose>

<process>

## Step 0: Initialize Context

**Load phase context and resolve model:**

```bash
load_research_phase_stage() {
  local stage_name="$1"
  local phase_arg="$2"
  local init_payload=""

  init_payload=$(gpd --raw init research-phase "${phase_arg}" --stage "${stage_name}" 2>/dev/null)
  if [ $? -ne 0 ] || [ -z "$init_payload" ]; then
    echo "ERROR: staged gpd initialization failed for stage '${stage_name}': ${init_payload}"
    return 1
  fi

  printf '%s' "$init_payload"
  return 0
}

BOOTSTRAP_INIT=$(load_research_phase_stage phase_bootstrap "${PHASE}")
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $BOOTSTRAP_INIT"
  # STOP; surface the error.
fi
```

Extract from init JSON: `phase_dir`, `phase_number`, `phase_name`, `phase_found`, `autonomy`, `research_mode`, `project_contract`, `project_contract_gate`, `project_contract_load_info`, `project_contract_validation`.

```bash
RESEARCH_MODE=$(echo "$BOOTSTRAP_INIT" | gpd json get .research_mode --default balanced)
```

The init-derived `RESEARCH_MODE` is the single source of truth for depth; do not re-query config later in the workflow.

**If `phase_found` is false:** Error and exit.

**Mode-aware behavior:**
- `research_mode=explore`: Comprehensive research — survey all viable methods, include failed approaches from literature, 10+ papers.
- `research_mode=exploit`: Focused research — direct methods only, 3-5 key papers, skip speculative approaches.
- `research_mode=balanced` (default): Use the standard research depth for this workflow and keep the default contract and anchor coverage unless the topic calls for broader or narrower review.
- `research_mode=adaptive`: Start broad enough to compare viable method families, then narrow only after prior decisive evidence or an explicit approach lock shows the method family is stable.
- `autonomy=supervised`: Present the `RESEARCH.md` draft for user review before treating the handoff as complete.
- `autonomy=balanced`: Accept the researcher handoff automatically once `RESEARCH.md` exists and passes the artifact check, then present the research summary before returning control.
- `autonomy=yolo`: Accept the researcher handoff automatically once `RESEARCH.md` exists and passes the artifact check without any extra summary-review pause.

@{GPD_INSTALL_DIR}/references/orchestration/model-profile-resolution.md

```bash
RESEARCHER_MODEL=$(gpd resolve-model gpd-phase-researcher)
```

## Step 1: Validate Phase

```bash
PHASE_INFO=$(gpd --raw roadmap get-phase "${phase_number}")
```

If `found` is false: Error and exit. Extract `goal` and `section` from JSON.

## Step 2: Check Existing Research

```bash
ls "${phase_dir}/"*-RESEARCH.md 2>/dev/null
```

If exists: Offer update/view/skip options.

## Step 3: Gather Phase Context

```bash
# Phase section from roadmap (already loaded in PHASE_INFO)
echo "$PHASE_INFO" | gpd json get .section --default ""
cat GPD/REQUIREMENTS.md 2>/dev/null
cat "${phase_dir}/"*-CONTEXT.md 2>/dev/null
# Decisions from gpd state snapshot (structured JSON)
gpd --raw state snapshot | gpd json get .decisions --default "[]"
```
## Stage Handoff: Research Handoff

After phase validation, existing-research routing, and context gathering are complete, reload `research_handoff` before assembling the child prompt:

```bash
HANDOFF_INIT=$(load_research_phase_stage research_handoff "${phase_number}")
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $HANDOFF_INIT"
  exit 1
fi
```

Read only `HANDOFF_INIT.staged_loading.eager_authorities`, primarily `workflows/research-phase/research-handoff.md`, plus the listed references. Do not continue from bootstrap memory into the researcher handoff.

</process>
