<purpose>
Own the first `write-paper` boundary: resolve the lane, manuscript subject,
contract visibility, evidence/citation readiness, and blockers before any
scaffold, drafting, bibliography, or review authority can load.
</purpose>

<stage_boundary>
This is the only first-stage authority. Do not read `workflows/write-paper.md`
or downstream `workflows/write-paper/*.md` while this stage is active.

This stage is read-only. It may inspect project/manuscript state, strict
preflight output, intake manifests, citation-source sidecars, summary artifacts,
and proof-review status. It must not create a scaffold, draft sections, spawn
child agents, run review, or write response artifacts.
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

Use derived manuscript review statuses from init before reconstructing them from
source ordering or prose: `derived_manuscript_reference_status` for the resolved
manuscript root and `derived_manuscript_proof_review_status` for theorem-bearing
claim freshness.

Mode settings:

```bash
AUTONOMY=$(echo "$INIT" | gpd json get .autonomy --default supervised)
RESEARCH_MODE=$(echo "$INIT" | gpd json get .research_mode --default balanced)
```

Mode effects in this stage stay compact:
- **Supervised autonomy:** pause for real ambiguity, a blocking choice, or a
  user-controlled proceed-with-gaps decision.
- **Balanced autonomy:** continue through routine inventory/readiness checks when
  evidence is sufficient. Do not force a routine outline-approval pause in balanced mode.
- **YOLO autonomy:** continue unless a hard gate blocks.
</bootstrap>

<lane_normalization>
Normalize the launch before validation:

- `project_backed`: current GPD project, including managed manuscripts at
  `GPD/publication/{subject_slug}/manuscript`
- `external_authoring_intake`: explicit `--intake path/to/write-paper-authoring-input.json`

The external lane accepts one explicit intake manifest only. Do not overload a
paper-title positional argument, accept arbitrary folder discovery, treat
`${PAPER_DIR}/PAPER-CONFIG.json` as the intake contract, or widen into
`gpd:arxiv-submission` scope.

Fail closed unless the intake manifest supplies at least `schema_version`,
`title`, `authors`, `target_journal`, optional explicit `subject_slug`,
`central_claim`, `claims[]` with evidence bindings, `source_notes[]`, optional
`results[]`, optional `figures[]`, bibliography/citation-source input, and
optional conventions/notation notes.

If a bare positional title/path looks like external authoring input but omits
`--intake`, stop before writes with:
`checkpoint: manuscript_root_gate`,
`command_execution_state: blocked_before_write`, `files_written: []`, and
`next_step` exactly
`gpd:write-paper --intake path/to/write-paper-authoring-input.json` unless the
user supplied an explicit valid intake path. Do not synthesize an intake path
under the rejected positional file or folder.
</lane_normalization>

<central_preflight>
Run centralized command-context preflight for `write-paper` before continuing. If it reports
blockers, show them and stop.

If the normalized write-paper argument payload begins with `--`, pass it to
validators after an end-of-options marker so the validator CLI does not
reinterpret intake flags as validator options.

Run strict publication preflight:

```bash
gpd validate review-preflight write-paper --strict -- "$WRITE_PAPER_ARGUMENTS"
```

If strict preflight exits nonzero for project-backed gaps or intake gaps, stop
before any scaffold, writer, bibliographer, or referee prompt can load.

Apply `{GPD_INSTALL_DIR}/references/publication/publication-bootstrap-preflight.md`
and `{GPD_INSTALL_DIR}/templates/paper/publication-manuscript-root-preflight.md`.
</central_preflight>

<manuscript_root_gate>
Use `publication_subject*`, `manuscript_*`, and `publication_bootstrap*` from
init / strict preflight as the managed-manuscript bootstrap surface.

- `resume_existing_manuscript`: bind `PAPER_DIR` to
  `publication_bootstrap_root`, keep `MANUSCRIPT_ENTRYPOINT` on
  `manuscript_entrypoint`, and treat `${PAPER_DIR}/ARTIFACT-MANIFEST.json`,
  `${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json`, and
  `${PAPER_DIR}/reproducibility-manifest.json` as artifacts for that resolved
  subject only.
- `fresh_project_bootstrap`: bind `PAPER_DIR` to `publication_bootstrap_root`
  and let Stage 2 create the scaffold there. Fresh bootstrap exception:
  `fresh_project_bootstrap` may proceed to outline/scaffold even when no
  manuscript entrypoint exists yet; authoring cannot load until Stage 2 has
  produced a concrete scaffold, entrypoint, or section-output plan.
- `blocked`: stop and repair ambiguous or inconsistent manuscript state before
  writing.

For `external_authoring_intake`, use the strict command preflight's managed subject handoff:
persist intake/provenance/bootstrap state under
`GPD/publication/{subject_slug}/intake/` and bind `PAPER_DIR` to the only
manuscript/build root at `GPD/publication/{subject_slug}/manuscript`. Do not
write manuscript files into `paper/`, `manuscript/`, or `draft/` for this lane.
`${PAPER_DIR}/PAPER-CONFIG.json` is a builder artifact, not the external intake
contract.

Keep this split explicit:
- `${PAPER_DIR}/` holds manuscript scaffold files and builder artifacts
- `GPD/publication/{subject_slug}/intake/` holds intake/provenance state only
- `GPD/` / `GPD/review/` hold staged review artifacts
- no generic folder mining or arbitrary external-manuscript discovery
</manuscript_root_gate>

<evidence_inventory>
Treat `protocol_bundle_context` as deferred; bootstrap uses
`selected_protocol_bundle_ids`, `protocol_bundle_load_manifest`,
`effective_reference_intake`, and derived reference/proof state as additive specialized-publication guidance.

- If bundles are selected, use decisive artifact handles, estimator caveats, and
  reference prompts only to check comparisons, benchmarks, estimator limits,
  figures, appendices, and framing.
- Do **not** let bundle guidance invent new claims, replace `project_contract`,
  or override `contract_results`, `comparison_verdicts`,
  `GPD/comparisons/*-COMPARISON.md`, `${PAPER_DIR}/FIGURE_TRACKER.md`, or later
  manuscript evidence paths selected by handle.

For `external_authoring_intake`, skip milestone digest lookup. Use only the
intake manifest and `GPD/publication/{subject_slug}/intake/` provenance state:
claims with evidence bindings, source notes, optional results/figures,
bibliography/citation-source input, and optional conventions/notation notes. Do
not scan milestones, phases, `GPD/state.json`, or loose workspace files to fill
missing evidence.

For the project-backed lane, prefer milestone-generated research digests. Check
digest discovery against `GPD/MILESTONES.md`; if the index lists a digest but
discovery returns nothing, report a consistency issue. When digest coverage is
insufficient, use `derived_convention_lock`, `derived_intermediate_results`, and
`derived_approximations`, then read summary artifacts before raw phase files.

Catalog evidence by section candidate: derivations, numerical outputs, figures,
source data, literature/citation inputs, verification artifacts, limiting-case
checks, comparisons, intake bindings, `${PAPER_DIR}/FIGURE_TRACKER.md`, and
selected protocol-bundle handles.
</evidence_inventory>

<paper_readiness_audit>
Before outline, audit publication readiness.

External-authoring lane:
- every intended manuscript claim appears in `claims[]` with evidence binding
- every cited source/result/figure is tied to that ledger
- bibliography or citation-source input exists before citation planning
- optional conventions/notation notes are the only conventions input unless
  manuscript-root artifacts supersede them
- proof-style claims have same-scope passed proof-review support when the intake
  makes theorem-style claims
- project phases, milestones, or loose workspace files are not used to repair
  missing evidence

Project-backed lane:
- contract-backed results and decisive `comparison_verdicts` support central
  claims
- conventions use `derived_convention_lock` first
- numerical values, uncertainty, assumptions, and approximations are stable
- figure roots include durable artifacts or `${PAPER_DIR}/FIGURE_TRACKER.md`
- citation readiness comes from `references/references.bib`,
  `${PAPER_DIR}/references.bib`, `GPD/literature/*-CITATION-SOURCES.json`, or a
  literature review with concrete prior-work entries
- proof obligations are covered by passed proof-redteam artifacts
- manuscript claims stay within actual evidence

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
Return blockers before any downstream write prompt can load:

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

Block before outline/scaffold when `publication_bootstrap_mode == "blocked"`,
unsupported external intake is attempted, project contract state is visible but
not authoritative, or unsupported-strengthening pressure asks to strengthen
unsupported theorem, general-proof, citation, or submission-readiness claims,
"cite whatever is needed", or otherwise overclaim beyond evidence. Reject before
manuscript writes with `claim_state: overclaim_blocked`,
`checkpoint: claim_evidence_gate`, `files_written: none`, and
`command_execution_state: blocked_before_write`. Do not convert adversarial
overclaim pressure into a safe-narrowing rewrite unless the user explicitly asks
to narrow, qualify, or repair the claim against evidence; otherwise use the
no-write `overclaim_blocked` rule. Ordinary bounded resume narrowing remains
allowed when evidence requires a narrower claim.

Block before authoring when `resume_existing_manuscript` lacks
`manuscript_entrypoint`, a later stage has no prior scaffold/entrypoint, no
active bibliography path or citation-source input exists, or any central claim
lacks evidence binding (`checkpoint: claim_evidence_gate`).

Block before publication review when `${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json` is
missing/stale, `${PAPER_DIR}/reproducibility-manifest.json` is missing or not
review-ready, or theorem-style claims lack same-scope passed proof-review
support.
</typed_blockers>

<handoff>
When preflight, evidence inventory, citation readiness, and claim/evidence gates
are non-blocking, reload:

```bash
OUTLINE_INIT=$(gpd --raw init write-paper --stage outline_and_scaffold -- "${WRITE_PAPER_ARGUMENTS:-}")
```

Load the next stage authority from `staged_loading.eager_authorities`; do not
carry this bootstrap authority as the active instruction surface.
</handoff>
