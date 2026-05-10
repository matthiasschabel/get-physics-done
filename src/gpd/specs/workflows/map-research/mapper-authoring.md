<purpose>
Own mapper prompt assembly, parallel research-map fanout, artifact verification, secret scanning, commit, and completion reporting for `gpd:map-research` after bootstrap has resolved project-rooted output paths.
</purpose>

<stage_boundary>
This authority starts only after `map_bootstrap` has routed existing maps and created or selected the project-rooted `GPD/research-map/` directory. Do not read `workflows/map-research.md`; it is only a staged-file index.
</stage_boundary>

<philosophy>
**Why dedicated mapper agents:** Fresh context per domain, direct writes, minimal orchestrator context, parallel execution.

**Document quality:** Include enough detail to be useful reference material; prefer practical examples (key equations, code patterns, data formats) over arbitrary brevity.

**Document templates:** Mapper agents load `{GPD_INSTALL_DIR}/references/templates/research-mapper/`. Missing templates mean broken install; fall back to the agent's built-in structure, not runtime-specific path searches.

**Always include file paths:**
Always include actual paths in backticks: `src/hamiltonian.py`, `notebooks/convergence_test.ipynb`, `latex/topic_stem.tex`.

**Map all project artifacts:**
A physics project may contain derivations, code, data, notebooks, figures, configs/job scripts, and references.
</philosophy>

<stage_prerequisites>
If this authority is entered fresh, define the staged reload helper before running `mapper_authoring` init:

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
```
</stage_prerequisites>

<process>
<step name="spawn_agents">
Spawn 4 parallel gpd-research-mapper agents.

Load the authoring slice only after existing-map routing and directory setup are complete:

```bash
MAPPER_AUTHORING_INIT=$(load_map_research_stage mapper_authoring)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $MAPPER_AUTHORING_INIT"
  exit 1
fi
```

Use `gpd --raw stage field-access map-research --stage mapper_authoring --style instruction` to confirm the manifest-selected authoring fields. Read only those keys from `MAPPER_AUTHORING_INIT`; `MAPPER_AUTHORING_INIT.staged_loading.required_init_fields` is the runtime confirmation. Use that refresh for mapper prompts; do not reuse bootstrap state for authoring.

Use task tool with `subagent_type="gpd-research-mapper"`, `model="{mapper_model}"`, `readonly=false`, and `run_in_background=true` for parallel execution.
@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md

> Apply the canonical runtime delegation convention already loaded above.

**CRITICAL:** Use the dedicated `gpd-research-mapper` agent, NOT `Explore`. The mapper agent writes documents directly.

Each mapper prompt must carry the staged intake, active reference context, excerpts, contract load/validation status, and project contract. Keep compact inline authority instructions in the task prompt; prefer contract IDs only when `project_contract_gate.authoritative` is true.

Mapper write paths are project-rooted. Resolve every relative `GPD/research-map/...` path against `{project_root}` and write to the corresponding absolute target under `{research_map_dir_absolute}`. Never write under the runtime shell cwd unless it is the same directory as `{project_root}`.

**Agent 1: Theory Focus**

task(
  subagent_type="gpd-research-mapper",
  model="{mapper_model}",
  readonly=false,
  run_in_background=true,
  description="Map research project theoretical content",
  prompt="First, read {GPD_AGENTS_DIR}/gpd-research-mapper.md for your role and instructions.

Focus: theory. Bias toward {map_focus} when provided without dropping contract-critical anchors.
Analyze theoretical content and literature foundations.

Context: staged={effective_reference_intake}; refs={active_reference_context}; excerpts={reference_artifacts_content}; contract={project_contract}; gate/load/validation={project_contract_gate}/{project_contract_load_info}/{project_contract_validation}. Use IDs only when authoritative.

- FORMALISM.md - equations, symmetries, approximations, boundary conditions, conservation laws
- REFERENCES.md - papers, benchmarks, prior artifacts, carry-forward actions, open questions. Every row needs `Anchor ID` and `Source / Locator`; record exact contract IDs separately when known.
Write to: GPD/research-map/FORMALISM.md
Write to: GPD/research-map/REFERENCES.md
<spawn_contract>
write_scope:
  mode: scoped_write
  allowed_paths:
    - GPD/research-map/FORMALISM.md
    - GPD/research-map/REFERENCES.md
expected_artifacts:
  - GPD/research-map/FORMALISM.md
  - GPD/research-map/REFERENCES.md
shared_state_policy: return_only
</spawn_contract>

Return typed `gpd_return`; completed must satisfy the focus-specific file gate. Read LaTeX, notes, comments/docstrings, README, BibTeX, docs.
"
)

**Agent 2: Computation Focus**

task(
  subagent_type="gpd-research-mapper",
  model="{mapper_model}",
  readonly=false,
  run_in_background=true,
  description="Map research project computational methods",
  prompt="First, read {GPD_AGENTS_DIR}/gpd-research-mapper.md for your role and instructions.

Focus: computation. Bias toward {map_focus} when provided without dropping contract-critical anchors.
Analyze computational methods, solvers, and project structure.

Context: staged={effective_reference_intake}; refs={active_reference_context}; excerpts={reference_artifacts_content}; contract={project_contract}; gate/load/validation={project_contract_gate}/{project_contract_load_info}/{project_contract_validation}. Use IDs only when authoritative.

- ARCHITECTURE.md - computational pipeline, solver choices, libraries, data flow, performance bottlenecks
- STRUCTURE.md - directory layout, file roles, naming conventions, formats, dependencies, build/job scripts
Write to: GPD/research-map/ARCHITECTURE.md
Write to: GPD/research-map/STRUCTURE.md
<spawn_contract>
write_scope:
  mode: scoped_write
  allowed_paths:
    - GPD/research-map/ARCHITECTURE.md
    - GPD/research-map/STRUCTURE.md
expected_artifacts:
  - GPD/research-map/ARCHITECTURE.md
  - GPD/research-map/STRUCTURE.md
shared_state_policy: return_only
</spawn_contract>

Return typed `gpd_return`; completed must satisfy the focus-specific file gate. Read code, notebooks, Makefiles, configs, requirements/pyproject files.
"
)

**Agent 3: Methodology Focus**

task(
  subagent_type="gpd-research-mapper",
  model="{mapper_model}",
  readonly=false,
  run_in_background=true,
  description="Map research project conventions and validation",
  prompt="First, read {GPD_AGENTS_DIR}/gpd-research-mapper.md for your role and instructions.

Focus: methodology. Bias toward {map_focus} when provided without dropping contract-critical anchors.
Analyze notation conventions, unit systems, and validation practices.

Context: staged={effective_reference_intake}; refs={active_reference_context}; excerpts={reference_artifacts_content}; contract={project_contract}; gate/load/validation={project_contract_gate}/{project_contract_load_info}/{project_contract_validation}. Use IDs only when authoritative.

- CONVENTIONS.md - notation, signs, units, indices, coordinates, variable naming, coupling definitions
- VALIDATION.md - known limits, convergence, consistency checks, comparisons, tests, error analysis
Write to: GPD/research-map/CONVENTIONS.md
Write to: GPD/research-map/VALIDATION.md
<spawn_contract>
write_scope:
  mode: scoped_write
  allowed_paths:
    - GPD/research-map/CONVENTIONS.md
    - GPD/research-map/VALIDATION.md
expected_artifacts:
  - GPD/research-map/CONVENTIONS.md
  - GPD/research-map/VALIDATION.md
shared_state_policy: return_only
</spawn_contract>

Return typed `gpd_return`; completed must satisfy the focus-specific file gate. Read LaTeX preambles, code naming, tests, validation scripts, comparison notebooks.
"
)

**Agent 4: Status Focus**

task(
  subagent_type="gpd-research-mapper",
  model="{mapper_model}",
  readonly=false,
  run_in_background=true,
  description="Map research project concerns and open questions",
  prompt="First, read {GPD_AGENTS_DIR}/gpd-research-mapper.md for your role and instructions.

Focus: status. Bias toward {map_focus} when provided without dropping contract-critical anchors.
Analyze open questions, known issues, and concerns.

Context: staged={effective_reference_intake}; refs={active_reference_context}; excerpts={reference_artifacts_content}; contract={project_contract}; gate/load/validation={project_contract_gate}/{project_contract_load_info}/{project_contract_validation}. Use IDs only when authoritative.

- CONCERNS.md - known issues, theoretical gaps, TODOs, fragile code/calculations, missing validation, bottlenecks, stale branches
Write to: GPD/research-map/CONCERNS.md
<spawn_contract>
write_scope:
  mode: scoped_write
  allowed_paths:
    - GPD/research-map/CONCERNS.md
expected_artifacts:
  - GPD/research-map/CONCERNS.md
shared_state_policy: return_only
</spawn_contract>

Return typed `gpd_return`; completed must satisfy the focus-specific file gate. Search TODO/FIXME/HACK/XXX, issue trackers, commented-out code, notebooks with errors.
"
)

**If any mapper agent fails to spawn or returns an error:** Finish remaining agents, but missing expected documents block completion unless the user explicitly accepts a partial map; default to retrying missing mapper slices.

Continue to collect_confirmations.
</step>

<step name="collect_confirmations">
Wait for all 4 agents to complete.

Read each agent's output file for confirmation, then reconcile the typed return with on-disk artifacts.

**Expected confirmation format from each agent:**

```yaml
gpd_return:
  status: completed
  files_written:
    - "GPD/research-map/FORMALISM.md"
    - "GPD/research-map/REFERENCES.md"
  issues: []
  next_actions:
    - "Verify GPD/research-map/FORMALISM.md and GPD/research-map/REFERENCES.md exist on disk before accepting the handoff."
  focus: "theory"
```

**What you receive:** Typed return + file paths and line counts. NOT document contents.

If an agent reports `gpd_return.status: completed`, accept it only through the focus-specific artifact gate.

Continue to verify_output.
</step>

<step name="verify_output">
Verify all documents created successfully:

```bash
ls -la "$RESEARCH_MAP_DIR_ABS/"
wc -l "$RESEARCH_MAP_DIR_ABS"/*.md
```

**Verification checklist:**

- All 7 documents exist
- No empty documents (each should have >20 lines)

If any documents are missing or empty, stop before secret scan and commit unless the user explicitly chooses partial mode. Say `Research project mapping is partial, not complete.`, list missing docs/focus, ask `retry` or `accept partial map`, and make `gpd:map-research [missing focus]` the primary `## > Next Up`.

`retry` reruns missing focus areas. `accept partial map` sets `MAP_STATUS=partial`. Never call partial output complete or make `gpd:new-project` the primary next step. If all documents exist and are non-empty, set `MAP_STATUS=complete`.

After complete verification or explicit partial-map acceptance, continue to scan_for_secrets.
</step>

<step name="scan_for_secrets">
**CRITICAL SECURITY CHECK:** Scan output files for accidentally leaked secrets before committing.

Run secret pattern detection:

```bash
grep -E '(sk-[[:alnum:]]{20,}|sk_(live|test)_|gh[pousr]_[[:alnum:]]{20,}|glpat-|AKIA[[:alnum:]]{16}|xox[baprs]-|BEGIN .*PRIVATE KEY|eyJ[[:alnum:]_-]+\.eyJ)' "$RESEARCH_MAP_DIR_ABS"/*.md 2>/dev/null && SECRETS_FOUND=true || SECRETS_FOUND=false
```

**If SECRETS_FOUND=true:**

```
>> SECURITY ALERT: Potential secrets detected in research map documents!

Found patterns that look like API keys or tokens in:
[show grep output]

This would expose credentials if committed.

**Action required:**
1. Review the flagged content above
2. If these are real secrets, they must be removed before committing
3. Consider adding sensitive files to your runtime's restricted-access list

Pausing before commit. Reply "safe to proceed" if the flagged content is not actually sensitive, or edit the files first.
```

Wait for user confirmation before continuing to commit_research_map.

**If SECRETS_FOUND=false:**

Continue to commit_research_map.
</step>

<step name="commit_research_map">
Commit the research map:

```bash
PRE_CHECK=$(gpd --cwd "$PROJECT_ROOT" pre-commit-check --files "$RESEARCH_MAP_DIR" 2>&1) || true
echo "$PRE_CHECK"

gpd --cwd "$PROJECT_ROOT" commit "docs: map existing research project" --files "$RESEARCH_MAP_DIR"
```

Continue to offer_next.
</step>

<step name="offer_next">
Present completion summary and next steps.

**Get line counts:**

```bash
wc -l "$RESEARCH_MAP_DIR_ABS"/*.md
```

**If `MAP_STATUS=partial`, output `Research project mapping partial.`, list missing documents, and end with `## > Next Up` primary `gpd:map-research [missing focus]`. Do not print `Research project mapping complete.` or make `gpd:new-project` primary. End workflow after the partial summary.

**If `MAP_STATUS=complete`, use this output format:**

```
Research project mapping complete.

Created GPD/research-map/:
- FORMALISM.md ([N] lines) - Theoretical framework, key equations, symmetries
- REFERENCES.md ([N] lines) - Literature foundations, cited papers, experimental data
- ARCHITECTURE.md ([N] lines) - Computational pipeline, solvers, algorithms
- STRUCTURE.md ([N] lines) - Directory layout, file organization, data formats
- CONVENTIONS.md ([N] lines) - Notation, units, sign conventions
- VALIDATION.md ([N] lines) - Benchmarks, consistency checks, test coverage
- CONCERNS.md ([N] lines) - Known issues, theoretical gaps, open questions


---

## > Next Up

**Initialize project** -- use research map context for planning

`gpd:new-project`

<sub>Start a fresh context window</sub>

---

**Also available:**
- Re-run mapping: `gpd:map-research`
- Review specific file: `cat GPD/research-map/FORMALISM.md`
- Edit any document before proceeding

---
```

End workflow.
</step>

</process>

<success_criteria>

- Project-rooted `GPD/research-map/` directory created
- 4 parallel gpd-research-mapper agents spawned with run_in_background=true
- Agents write documents directly (orchestrator doesn't receive document contents)
- Read agent output files to collect confirmations
- All 7 research map documents exist covering theory, computation, methodology, and status
- Clear completion summary with line counts
- User offered clear next steps in GPD style
  </success_criteria>
