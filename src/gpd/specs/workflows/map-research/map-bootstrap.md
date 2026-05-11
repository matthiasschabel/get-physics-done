<purpose>
Bootstrap `gpd:map-research`: resolve the project-rooted
`GPD/research-map/`, route existing maps, and reload `mapper_authoring` before
any mapper fanout. Mapper agents write the 7 map documents directly.
</purpose>

<philosophy>
Mapper authoring handles document quality, templates, file-path discipline, and
artifact coverage. Bootstrap only routes and prepares the project-rooted output
directory.
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

Use `gpd --raw stage field-access map-research --stage map_bootstrap --style instruction` to confirm the manifest-selected bootstrap fields. Read only those keys from `BOOTSTRAP_INIT`; `BOOTSTRAP_INIT.staged_loading.required_init_fields` is the runtime confirmation, including `project_contract_gate`.
`{GPD_INSTALL_DIR}/references/orchestration/contract-authority-gate.md`

All filesystem actions in this workflow must use `PROJECT_ROOT` / `RESEARCH_MAP_DIR_ABS` from the staged payload. Do not create, delete, archive, verify, or commit `GPD/research-map` relative to the shell launch directory; a nested launch cwd inside a project is valid and must still target the resolved project root.

**Read mode settings:**

```bash
RESEARCH_MODE=$(echo "$BOOTSTRAP_INIT" | gpd json get .research_mode --default balanced)
```

`RESEARCH_MODE` is the single source of truth for mapping depth. Preserve
contract-critical anchors, prior baselines, and user-mandated references.
Contract gate: `project_contract` is authoritative only when
`project_contract_gate.authoritative` is true; otherwise keep gate/load/validation
visible. If `map_focus_provided` is true, keep `map_focus` visible and bias each
slice without losing contract-critical coverage. Map focus: {map_focus}
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

For `update_selected`, run selected-document mode: Spawn only mapper slices that own at least one selected document, intersect each selected mapper's `allowed_paths`, `expected_artifacts`, and accepted `gpd_return.files_written` with `UPDATE_SELECTED_DOCS`, and Keep unselected map documents byte-for-byte unchanged. Completion verifies selected documents plus unchanged unselected documents. If any unselected file changes, fail closed and report the unexpected write.

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
