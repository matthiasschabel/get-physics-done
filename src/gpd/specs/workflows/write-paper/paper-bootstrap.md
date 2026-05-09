<purpose>
Own the first `write-paper` boundary: resolve the lane, manuscript subject,
project contract visibility, evidence inventory, citation-source readiness, and
paper-readiness blockers before any downstream drafting, bibliography, or referee
authority can load.
</purpose>

<stage_boundary>
This is the only first-stage authority. Do not read `workflows/write-paper.md`
or any downstream `workflows/write-paper/*.md` authority while this stage is
active.

This stage is read-only. It may inspect project/manuscript state, strict
preflight output, intake manifests, literature/citation-source sidecars,
summary artifacts, and proof-review status. It must not create a manuscript
scaffold, draft sections, spawn child agents, run the embedded review panel, or
write review/response artifacts.
</stage_boundary>

<bootstrap>
Run staged init before relying on workflow fields:

```bash
WRITE_PAPER_ARGUMENTS="${ARGUMENTS:-}"
if [ -n "$WRITE_PAPER_ARGUMENTS" ]; then
  PAPER_BOOTSTRAP_INIT=$(gpd --raw init write-paper --stage paper_bootstrap -- "$WRITE_PAPER_ARGUMENTS")
else
  PAPER_BOOTSTRAP_INIT=$(gpd --raw init write-paper --stage paper_bootstrap)
fi
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $PAPER_BOOTSTRAP_INIT"
  # STOP; surface the error.
fi
INIT="$PAPER_BOOTSTRAP_INIT"
PROJECT_ROOT=$(echo "$INIT" | gpd json get .project_root --default "")
if [ -n "$PROJECT_ROOT" ]; then
  cd "$PROJECT_ROOT" || {
    echo "ERROR: could not enter resolved project root: $PROJECT_ROOT"
    exit 1
  }
fi
```

Parse bootstrap JSON using the manifest-owned `paper_bootstrap.required_init_fields` in `write-paper-stage-manifest.json`; `gpd --raw stage field-access write-paper --stage paper_bootstrap --style instruction` is the helper-owned field inventory. Keep `project_contract_gate` visible before authoritative-use decisions; use `project_contract` as authoritative only when `project_contract_gate.authoritative` is true; do not duplicate the manifest's required-field list in prose.

When later steps need publication routing, use the derived manuscript review statuses from init, including `derived_manuscript_reference_status` and `derived_manuscript_proof_review_status`, before reconstructing that status from source ordering or prose. If `derived_manuscript_reference_status` is present, use it for the resolved manuscript root. Use `derived_manuscript_proof_review_status` as proof-review freshness for theorem-bearing results.

Mode settings:

```bash
AUTONOMY=$(echo "$INIT" | gpd json get .autonomy --default supervised)
RESEARCH_MODE=$(echo "$INIT" | gpd json get .research_mode --default balanced)
```

Mode effects in this stage stay compact:
- **Supervised autonomy:** pause only for real ambiguity, a blocking choice, or a user-controlled proceed-with-gaps decision.
- **Balanced autonomy:** continue through routine inventory/readiness checks when evidence is sufficient. Do not force a routine outline-approval pause in balanced mode.
- **YOLO autonomy:** continue unless a hard gate blocks.
</bootstrap>

<lane_normalization>
Normalize the launch into one of two lanes before validation:

- `project_backed` -- current GPD project, including a managed manuscript lane
  at `GPD/publication/{subject_slug}/manuscript`
- `external_authoring_intake` -- explicit `--intake path/to/write-paper-authoring-input.json`

The bounded external-authoring lane has one entrypoint only:

- do not overload a paper-title positional argument
- do not accept arbitrary folder discovery
- do not treat `${PAPER_DIR}/PAPER-CONFIG.json` as the intake contract
- fail closed unless the intake manifest supplies at least `schema_version`,
  `title`, `authors`, `target_journal`, optional explicit `subject_slug`,
  `central_claim`, `claims[]` with explicit evidence bindings, `source_notes[]`,
  optional `results[]`, optional `figures[]`, bibliography / citation-source
  input, and optional conventions / notation note

External-authoring invariant: accept one explicit intake manifest only; do not
infer widened `gpd:arxiv-submission` scope from this lane.

If a launch supplies a bare positional title/path that looks like external
authoring input but omits `--intake`, stop before writes with a typed blocker:
`checkpoint: manuscript_root_gate`, `command_execution_state: blocked_before_write`,
`files_written: []`, and `next_step` exactly
`gpd:write-paper --intake path/to/write-paper-authoring-input.json` unless the
user supplied an explicit valid intake manifest path. Do not synthesize an
intake path under the rejected positional file or folder.
</lane_normalization>

<central_preflight>
Run centralized command-context preflight for `write-paper` before continuing.
If it reports blockers, show them and stop.

If the normalized write-paper argument payload begins with `--`, pass it to
validators after an end-of-options marker so the validator CLI does not
reinterpret intake flags as validator options.

Run strict publication preflight:

```bash
gpd validate review-preflight write-paper --strict -- "$WRITE_PAPER_ARGUMENTS"
```

If review preflight exits nonzero because of project-backed gaps or
external-authoring intake gaps, stop and surface the blocking issues before any
scaffold, writer, bibliographer, or referee prompt can load.

Apply the shared publication bootstrap preflight contract from
`{GPD_INSTALL_DIR}/references/publication/publication-bootstrap-preflight.md`
and the manuscript-root details from
`{GPD_INSTALL_DIR}/templates/paper/publication-manuscript-root-preflight.md`.
</central_preflight>

<manuscript_root_gate>
Use `publication_subject*`, `manuscript_*`, and `publication_bootstrap*` from init / strict preflight as the authoritative managed-manuscript bootstrap surface.

- If `publication_bootstrap_mode` is `resume_existing_manuscript`, bind
  `PAPER_DIR` to `publication_bootstrap_root`, keep `MANUSCRIPT_ENTRYPOINT` on
  `manuscript_entrypoint`, and treat `${PAPER_DIR}/ARTIFACT-MANIFEST.json`,
  `${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json`, and
  `${PAPER_DIR}/reproducibility-manifest.json` as manuscript-root artifacts for
  that exact resolved subject only. The resolved manuscript root may already be
  the managed project lane `GPD/publication/{subject_slug}/manuscript`; treat
  that as project-owned manuscript state rather than external-artifact mode.
- If `publication_bootstrap_mode` is `fresh_project_bootstrap`, bind
  `PAPER_DIR` to `publication_bootstrap_root` and allow the outline/scaffold
  stage to create a fresh manuscript scaffold there. Fresh bootstrap exception:
  `fresh_project_bootstrap` may proceed to outline/scaffold even when no
  manuscript entrypoint exists yet; authoring cannot load until Stage 2 has
  produced a concrete scaffold, entrypoint, or section-output plan.
- If `publication_bootstrap_mode` is `blocked`, stop and repair the ambiguous or
  inconsistent manuscript state before writing.

For `external_authoring_intake`, use the strict command preflight's managed subject handoff:
persist intake/provenance/bootstrap state under
`GPD/publication/{subject_slug}/intake/` and bind `PAPER_DIR` to the only
manuscript/build root at `GPD/publication/{subject_slug}/manuscript`. Do not
write manuscript files into `paper/`, `manuscript/`, or `draft/` for this lane.
`${PAPER_DIR}/PAPER-CONFIG.json` is a manuscript-root builder artifact, not the
external intake contract.

Current publication-lane split:

- manuscript scaffold files and manuscript-root builder artifacts stay in
  `${PAPER_DIR}/`
- `GPD/publication/{subject_slug}/intake/` is intake/provenance state only; it must not participate in manuscript-root discovery
- a resolved `${PAPER_DIR}` under `GPD/publication/{subject_slug}/manuscript` may be either the managed project lane or the bounded external-authoring lane
- GPD-authored staged review artifacts stay under `GPD/` / `GPD/review/`
- do not mine generic folders or widen into arbitrary external-manuscript discovery; the only non-project lane is explicit `--intake`
</manuscript_root_gate>

<evidence_inventory>
Use `protocol_bundle_context` from init JSON as additive specialized-publication guidance.

- If `selected_protocol_bundle_ids` is non-empty, keep the bundle's decisive
  artifact guidance, estimator caveats, and reference prompts visible while
  choosing main-text figures, appendices, and related-work framing.
- Use bundle guidance only to check whether the manuscript surfaces the right
  decisive comparisons, benchmark anchors, and estimator limitations.
- Do **not** let bundle guidance invent new claims, replace `project_contract`,
  or override `contract_results`, `comparison_verdicts`,
  `GPD/comparisons/*-COMPARISON.md`, `${PAPER_DIR}/FIGURE_TRACKER.md`, or
  `active_reference_context`.

For `external_authoring_intake`, skip milestone digest lookup. Use only the
intake manifest and `GPD/publication/{subject_slug}/intake/` provenance state:
`central_claim`, `claims[]` with explicit evidence bindings, `source_notes[]`,
optional `results[]`, optional `figures[]`, bibliography / citation-source
  input, and optional conventions / notation note. Do not scan
  `GPD/milestones/*`, `GPD/phases/*`, `GPD/state.json`, or arbitrary folders to
  fill missing evidence for this lane.

For the project-backed lane, prefer research digests generated during milestone
completion. Cross-check recursive digest discovery against `GPD/MILESTONES.md`;
if the index lists a digest but discovery returns nothing, report a consistency
issue rather than silently downgrading to raw-phase mode. When digest coverage is
  insufficient, use structured init fields first:
  `derived_convention_lock`, `derived_intermediate_results`, and
  `derived_approximations`; then Read summary artifacts (`SUMMARY.md` and `*-SUMMARY.md`, including `GPD/phases/*/*SUMMARY.md`) before raw phase files.

Catalog evidence by section candidate:
- derivations, numerical outputs, figures, and source data
- literature context from intake-manifest citation input,
  `GPD/literature/*-REVIEW.md`, or phase `RESEARCH.md`
- verification artifacts and limiting-case checks
- internal comparisons and decisive evidence from
  `GPD/comparisons/*-COMPARISON.md`, intake claim/evidence bindings,
  `${PAPER_DIR}/FIGURE_TRACKER.md`, and protocol bundle context
</evidence_inventory>

<paper_readiness_audit>
Before committing to an outline, audit publication readiness.

For `external_authoring_intake`:

1. Every intended manuscript claim must appear in `claims[]` with an explicit
   evidence binding.
2. Every cited `source_notes[]`, optional `results[]`, or optional `figures[]`
   item must be referenced by that claim/evidence ledger.
3. Bibliography / citation-source input must exist before citation planning
   begins.
4. Optional conventions / notation notes are the only conventions input unless
   later manuscript-root artifacts supersede them.
5. Proof-style claims still require passed proof-review support when the intake
   says a theorem-style claim is being made.
6. Do not enumerate project phases, milestones, or loose workspace files to
   repair missing evidence.

For the project-backed lane, audit:

- summary-artifact completeness and contract-backed `contract_results`
- decisive `comparison_verdicts` evidence for central claims
- convention consistency, using `derived_convention_lock` first
- numerical value stability and stated uncertainty
- figure readiness from durable roots: `artifacts/phases`, `figures`,
  `${PAPER_DIR}/figures`, and `${PAPER_DIR}/FIGURE_TRACKER.md`
- citation readiness from `references/references.bib`,
  `${PAPER_DIR}/references.bib`, `GPD/literature/*-CITATION-SOURCES.json`,
  and literature-review artifacts with concrete prior-work entries
- proof-obligation coverage through passed `*-PROOF-REDTEAM.md` or
  manuscript-round `GPD/review/PROOF-REDTEAM{round_suffix}.md`
- the manuscript claims it actually makes, not stronger claims inferred from
  desired venue or publication pressure

Missing generic `verification_status` / `confidence` tags alone are not blockers.
Treat them as calibration warnings unless contract-backed outcome evidence or a
decisive comparison needed by a manuscript claim is missing.

Citation readiness is a hard gate for authoring in Phase 3: no bibliography
file, no literature review with concrete prior-work entries, and no
citation-source sidecar means `checkpoint: bibliography_gate`, not a warning.
The authoring stage cannot load until the run has an active bibliography path or
required citation-source input for the intended claims.
</paper_readiness_audit>

<typed_blockers>
Return blockers in this shape before any downstream write prompt can load:

```yaml
gpd_return:
  status: blocked
  files_written: []
  issues:
    - "<specific missing or invalid input>"
  next_actions:
    - "<single concrete command or repair>"
  blockers:
    - kind: manuscript_root_gate | bibliography_gate | claim_evidence_gate | review_gate
      checkpoint: manuscript_root_gate | bibliography_gate | claim_evidence_gate | review_gate
      detail: "<specific missing or invalid input>"
      next_step: "<single concrete command or repair>"
```

Block before outline/scaffold when:
- `publication_bootstrap_mode == "blocked"`
- the launch attempted unsupported external intake
- project contract state is visible but not authoritative for a project-backed
  authoring decision
- unsupported-strengthening pressure asks to strengthen unsupported theorem, general-proof,
  citation, or submission-readiness claims, "cite whatever is needed", or
  otherwise overclaim beyond evidence. Reject before manuscript writes with
  `claim_state: overclaim_blocked`, `checkpoint: claim_evidence_gate`,
  `files_written: none`, and `command_execution_state: blocked_before_write`.
  Do not convert adversarial overclaim pressure into a safe-narrowing rewrite
  unless the user explicitly asks to narrow, qualify, or repair the claim
  against evidence; otherwise use the no-write `overclaim_blocked` rule.
  Ordinary bounded resume narrowing remains allowed when evidence requires a narrower claim.

Block before authoring when:
- `resume_existing_manuscript` is selected but `manuscript_entrypoint` is missing
- a later stage is entered with no scaffold/entrypoint from the prior stage
- no active bibliography path or citation-source input exists
- any central claim lacks explicit evidence binding
- `checkpoint: claim_evidence_gate`

Block before publication review when:
- `${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json` is missing or stale
- `${PAPER_DIR}/reproducibility-manifest.json` is missing or not review-ready
- theorem-style claims lack same-scope passed proof-review support
</typed_blockers>

<handoff>
When manuscript/project preflight, evidence inventory, citation readiness, and
claim/evidence gates are non-blocking, reload:

```bash
OUTLINE_INIT=$(gpd --raw init write-paper --stage outline_and_scaffold -- "${WRITE_PAPER_ARGUMENTS:-}")
```

Load the next stage authority from `staged_loading.eager_authorities`; do not
carry this bootstrap authority as the active instruction surface.
</handoff>
