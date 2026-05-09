<purpose>
Orchestrate parallel research-mapper agents to analyze a physics research project and produce structured documents under the project-rooted `GPD/research-map/`.

Each agent has fresh context, explores one focus area, and **writes documents directly**. The orchestrator verifies typed returns, disk files, and line counts, then writes a summary.

Output: `GPD/research-map/` under the resolved project root, with 7 structured documents covering theoretical content, computational methods, data artifacts, conventions, and open questions.
</purpose>

<philosophy>
**Why dedicated mapper agents:** Fresh context per domain, direct writes, minimal orchestrator context, parallel execution.

**Document quality:** Include enough detail to be useful reference material; prefer practical examples (key equations, code patterns, data formats) over arbitrary brevity.

**Document templates:** Mapper agents load `{GPD_INSTALL_DIR}/references/templates/research-mapper/`. Missing templates mean broken install; fall back to the agent's built-in structure, not runtime-specific path searches.

**Always include file paths:**
Always include actual paths in backticks: `src/hamiltonian.py`, `notebooks/convergence_test.ipynb`, `latex/topic_stem.tex`.

**Map all project artifacts:**
A physics project may contain derivations, code, data, notebooks, figures, configs/job scripts, and references.
  </philosophy>

<process>

Runtime label: Show `gpd:` as native labels; keep local CLI `gpd ...` unchanged.

<step name="init_context" priority="first">
Load research mapping context:

```bash
load_map_research_stage() {
  local stage_name="$1"
  local init_payload=""
  local target_cwd="${PROJECT_ROOT:-$PWD}"

  if [ -n "${ARGUMENTS:-}" ]; then
    init_payload=$(gpd --raw --cwd "$target_cwd" init map-research --stage "${stage_name}" -- "${ARGUMENTS:-}" 2>/dev/null)
  else
    init_payload=$(gpd --raw --cwd "$target_cwd" init map-research --stage "${stage_name}" 2>/dev/null)
  fi
  if [ $? -ne 0 ] || [ -z "$init_payload" ]; then
    echo "ERROR: staged gpd initialization failed for stage '${stage_name}': ${init_payload}"
    return 1
  fi

  printf '%s' "$init_payload"
  return 0
}

BOOTSTRAP_INIT=$(load_map_research_stage map_bootstrap)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $BOOTSTRAP_INIT"
  # STOP; surface the error.
fi

PROJECT_ROOT=$(echo "$BOOTSTRAP_INIT" | gpd json get .project_root --default "")
WORKSPACE_ROOT=$(echo "$BOOTSTRAP_INIT" | gpd json get .workspace_root --default "")
RESEARCH_MAP_DIR=$(echo "$BOOTSTRAP_INIT" | gpd json get .research_map_dir --default "GPD/research-map")
RESEARCH_MAP_DIR_ABS=$(echo "$BOOTSTRAP_INIT" | gpd json get .research_map_dir_absolute --default "")
if [ -z "$PROJECT_ROOT" ] || [ -z "$RESEARCH_MAP_DIR_ABS" ]; then
  echo "ERROR: map-research init did not return project_root and research_map_dir_absolute"
  # STOP; surface the error.
fi
```

Use `gpd --raw stage field-access map-research --stage map_bootstrap --style instruction` to confirm the manifest-selected bootstrap fields. Read only those keys from `BOOTSTRAP_INIT`; `BOOTSTRAP_INIT.staged_loading.required_init_fields` is the runtime confirmation.
`{GPD_INSTALL_DIR}/references/orchestration/contract-authority-gate.md`

All filesystem actions in this workflow must use `PROJECT_ROOT` / `RESEARCH_MAP_DIR_ABS` from the staged payload. Do not create, delete, archive, verify, or commit `GPD/research-map` relative to the shell launch directory; a nested launch cwd inside a project is valid and must still target the resolved project root.

**Read mode settings:**

```bash
RESEARCH_MODE=$(echo "$BOOTSTRAP_INIT" | gpd json get .research_mode --default balanced)
```

**Mode-aware behavior:**
- `explore`: broad alternatives, speculative connections, open questions.
- `exploit`: primary formalism, established results, direct computational needs.
- `research_mode=balanced` (default): standard depth and default anchor/contract coverage unless the question needs otherwise.
- `adaptive`: start primary, expand if cross-domain connections appear.
- Never drop contract-critical anchors, prior baselines, or user-mandated references.
- `RESEARCH_MODE` is sourced from the init payload. Do not re-query config later in this workflow.
- Preserve stable anchor identity: every durable `REFERENCES.md` anchor needs reusable `Anchor ID` and concrete `Source / Locator`.
- Keep carry-forward scope separate from contract subject linkage: `Carry Forward To` names workflow stages; exact claim/deliverable IDs go in `Contract Subject IDs`.
- Contract gate: `project_contract` is authoritative only when `project_contract_gate.authoritative` is true; otherwise keep gate/load/validation visible.
- If `map_focus_provided` is true, keep `map_focus` visible and bias each slice without losing contract-critical coverage. Map focus: {map_focus}
Each mapper agent is a one-shot file-producing handoff. Route on `gpd_return.status`, then verify `gpd_return.files_written` against the expected artifacts before accepting the run.
</step>

<step name="check_existing">
Check if the project-rooted research-map directory already exists using `has_maps` and `research_map_dir_exists` from init context.

If `research_map_dir_exists` is true:

```bash
ls -la "$RESEARCH_MAP_DIR_ABS/"
```

**If exists:**

```
GPD/research-map/ already exists at:
{research_map_dir_absolute}

Existing documents:
[List files found]

What's next?
- option_id: refresh_archive - archive existing map beside it, create a new empty map, remap.
- option_id: update_selected - keep existing files and update selected documents.
- option_id: skip_existing - use existing research map as-is.
```

Wait for user response and route by exact `option_id`, not option number or label.

If `refresh_archive`: archive first, then continue to create_structure:

```bash
RESEARCH_MAP_ARCHIVE_DIR="${RESEARCH_MAP_DIR_ABS}.archive-$(date +%Y%m%d-%H%M%S)"
if [ -e "$RESEARCH_MAP_ARCHIVE_DIR" ]; then
  RESEARCH_MAP_ARCHIVE_DIR="${RESEARCH_MAP_ARCHIVE_DIR}-$$"
fi
mv "$RESEARCH_MAP_DIR_ABS" "$RESEARCH_MAP_ARCHIVE_DIR"
mkdir -p "$RESEARCH_MAP_DIR_ABS"
echo "Archived previous research map at: $RESEARCH_MAP_ARCHIVE_DIR"
```

If `update_selected`: ask for explicit document IDs from this fixed set only: `FORMALISM.md`, `REFERENCES.md`, `ARCHITECTURE.md`, `STRUCTURE.md`, `CONVENTIONS.md`, `VALIDATION.md`, `CONCERNS.md`. Continue only after the user selects at least one valid document ID. Record the selected list as `UPDATE_SELECTED_DOCS`.

For `update_selected`, run selected-document mode:

- Spawn only mapper slices that own at least one selected document.
- Intersect every selected mapper's `allowed_paths`, `expected_artifacts`, and accepted `gpd_return.files_written` with `UPDATE_SELECTED_DOCS`.
- Keep unselected map documents byte-for-byte unchanged; do not rewrite, reformat, or verify them as outputs for this run.
- Completion verifies only the selected documents plus the unchanged status of unselected documents. If any unselected file changes, fail closed and report the unexpected write.

If `skip_existing`: Exit workflow

**If doesn't exist:**
Continue to create_structure.
</step>

<step name="create_structure">
Create the project-rooted research-map directory:

```bash
mkdir -p "$RESEARCH_MAP_DIR_ABS"
```

**Expected output files:**

- FORMALISM.md (from theory mapper)
- REFERENCES.md (from theory mapper)
- ARCHITECTURE.md (from computation mapper)
- STRUCTURE.md (from computation mapper)
- CONVENTIONS.md (from methodology mapper)
- VALIDATION.md (from methodology mapper)
- CONCERNS.md (from status mapper)

Continue to spawn_agents.
</step>
<step name="handoff_to_mapper_authoring">
When existing-map routing and directory setup are complete, reload `mapper_authoring` and read only that stage's eager authorities before spawning mapper agents.

```bash
MAPPER_AUTHORING_INIT=$(load_map_research_stage mapper_authoring)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $MAPPER_AUTHORING_INIT"
  exit 1
fi
```

Use `gpd --raw stage field-access map-research --stage mapper_authoring --style instruction` to confirm the manifest-selected authoring fields. Then follow `workflows/map-research/mapper-authoring.md`; do not continue from bootstrap memory into mapper fanout.
</step>

</process>
