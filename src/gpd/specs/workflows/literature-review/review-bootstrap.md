<purpose>
Conduct a systematic literature review for a physics research topic. Map the intellectual landscape: foundational works, methodological approaches, key results, controversies, and open questions. Produce LITERATURE-REVIEW.md consumed by planning and paper-writing workflows.

Also emit `GPD/literature/{slug}-CITATION-SOURCES.json` with strict `CitationSource` objects keyed by stable `reference_id` values. Include `bibtex_key` only when already known and verified; audit-only verification fields belong in `GPD/literature/{slug}-CITATION-AUDIT.md`.

Called from gpd:literature-review command.

This workflow owns staged init, scope fixing, deferred reference-artifact loading, and artifact gates. Do not frontload reference artifacts before scope is fixed.

Keep all durable review artifacts rooted under `GPD/literature/` in the current workspace. In project-backed mode, that is the resolved project root's `GPD/literature/`; in standalone mode, it is `./GPD/literature/` in the invoking workspace.
</purpose>

<core_principle>
A physics literature review is not a bibliography. It maps who computed what, with which methods and assumptions, what results agree or conflict, what is open, and where new work can contribute.
</core_principle>

<source_hierarchy>
**MANDATORY: Authoritative sources BEFORE general search**

1. **Textbooks and monographs** -- standard results, methods, conventions, and field context.
2. **Review articles** -- field overviews and method surveys.
3. **Seminal papers** -- original derivations; read the papers, not just citations.
4. **Recent arXiv preprints** -- relevant new results.
5. **Conference proceedings** -- recent community direction.
6. **web_search** -- last resort for discussions, code, or benchmarks.

</source_hierarchy>

<process>

<step name="load_context" priority="first">
**Load project context (if available):**

```bash
load_literature_review_stage() {
  local stage_name="$1"
  shift
  local init_payload=""

  init_payload=$(gpd --raw init literature-review "$@" --stage "$stage_name" 2>/dev/null)
  if [ $? -ne 0 ] || [ -z "$init_payload" ]; then
    echo "ERROR: staged gpd initialization failed for stage '${stage_name}': ${init_payload}"
    return 1
  fi

  printf '%s' "$init_payload"
  return 0
}

BOOTSTRAP_INIT=$(load_literature_review_stage review_bootstrap "$ARGUMENTS")
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $BOOTSTRAP_INIT"
  # STOP; surface the error.
fi
```

Use `gpd --raw stage field-access literature-review --stage review_bootstrap --style instruction` to confirm manifest-selected bootstrap fields. Read only keys in `BOOTSTRAP_INIT.staged_loading.required_init_fields`.
`{GPD_INSTALL_DIR}/references/orchestration/contract-authority-gate.md`

- If `topic` is empty, do not invent or auto-derive it from project state, active references, or deferred artifacts.
- In project-backed mode, ask one focused question to lock the topic before broadening the search or loading scoped reference artifacts.
- In standalone mode, stop; centralized preflight should already have required explicit topic input.

Do not use `reference_artifact_files` or `reference_artifacts_content` yet. Keep them deferred until scope is fixed so reference artifacts cannot broaden the topic before the user has chosen it.

**Read mode settings:**

```bash
AUTONOMY=$(gpd --raw config get autonomy 2>/dev/null | gpd json get .value --default supervised 2>/dev/null || echo "supervised")
RESEARCH_MODE=$(gpd --raw config get research_mode 2>/dev/null | gpd json get .value --default balanced 2>/dev/null || echo "balanced")
```

**Mode-aware behavior:**
- `research_mode=explore`: Comprehensive review; include tangential fields, citation network, and open questions.
- `research_mode=exploit`: Focused review; direct relevance only, key results and methods.
- `research_mode=balanced` (default): Use the standard review depth for this workflow and keep the default anchor and contract coverage unless the topic needs broader or narrower review.
- `research_mode=adaptive`: Start medium-depth and expand if the citation network reveals critical gaps.
- `autonomy=supervised` (default): Pause after each review round for user feedback on scope and direction.
- `autonomy=balanced`: Complete the full review pipeline automatically. Pause only if the literature reveals scope ambiguity, contradictory evidence, or a change in recommendation.
- `autonomy=yolo`: Complete the review pipeline without pausing, but do NOT drop contract-critical anchors or user-mandated references.

- **If `state_exists` is true:** Extract `convention_lock` for notation context (helps identify which conventions are used in papers being reviewed). Extract active research topic, phase context, and any contract-critical references from `active_reference_context`.
- **If `state_exists` is false** (standalone usage): Proceed — the user will specify the topic directly.
- Treat `effective_reference_intake` as the carry-forward ledger for anchors, prior outputs, baselines, user-mandated context, and unresolved gaps. Re-surface those items even if the broader search expands.
- Apply the shared contract authority gate: treat `project_contract` as authoritative only when `project_contract_gate.authoritative` is true; in review context, otherwise keep it visible as diagnostics and do not promote it to approved review truth.

Project context helps focus the review on conventions and methods relevant to the current research.
</step>

<step name="scope_review">
Establish scope from command context:

The review topic must already be explicit or newly clarified; project existence alone does not satisfy subject selection.

- **Topic and focus**: specific physics question or subfield
- **Depth**: quick | standard | comprehensive
- **Time range**: all time | last N years | since a specific result
- **Purpose**: background | method selection | gap identification | manuscript prep
- List seed anchors from `project_contract`, `contract_intake`, `effective_reference_intake`, and `active_reference_context` before broadening search.

Define explicit include/exclude boundaries:

- Include: specific phenomena, methods, energy ranges, dimensions
- Exclude: tangential fields, historical reviews (unless depth=comprehensive)
- Track contract-critical anchors in a compact registry with a `| Must Surface |` column.
- Set `Must Surface` to `yes` for required anchors, with roles like `benchmark`, `definition`, `method`, or `must_consider`.
  </step>

</process>
