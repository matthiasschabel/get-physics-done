<purpose>
Own paper scope, journal/builder selection, detailed outline, and manuscript
scaffold generation.
</purpose>

<stage_boundary>
This stage may write the managed manuscript scaffold and intake/provenance roots
already allowed by the stage manifest. It does not draft sections, verify
bibliography, run peer review, or spawn downstream child agents.
</stage_boundary>

<init>
Load the staged outline/scaffold payload before using outline-time publication
scaffolding fields or paper schema authorities:

```bash
OUTLINE_INIT=$(gpd --raw init write-paper --stage outline_and_scaffold -- "${WRITE_PAPER_ARGUMENTS:-}")
if [ $? -ne 0 ]; then
  echo "ERROR: write-paper outline/scaffold init failed: $OUTLINE_INIT"
  # STOP; surface the error.
fi
INIT="$OUTLINE_INIT"
```

Use `gpd --raw stage field-access write-paper --stage outline_and_scaffold --style instruction`
to confirm the manifest-selected outline/scaffold fields before reading
`OUTLINE_INIT`.

Apply `{GPD_INSTALL_DIR}/references/publication/publication-pipeline-modes.md`
from this staged payload before outline-level mode decisions, including
bibliographer search breadth, referee strictness, and paper-writer style by mode.
</init>

<journal_formats>
The manuscript builder and emitted `${PAPER_DIR}/ARTIFACT-MANIFEST.json`
currently support only these `PAPER-CONFIG.json` journal keys:

- `prl`
- `apj`
- `mnras`
- `nature`
- `jhep`
- `jfm`

These are the only valid `journal` values in `PAPER-CONFIG.json` and
`${PAPER_DIR}/ARTIFACT-MANIFEST.json`.

Manual `PaperQualityInput` JSON can use additional scoring-only profiles such as
`prd`, `prb`, `prc`, or `nature_physics`, but those are not supported
`PAPER-CONFIG.json` builder keys yet. Unsupported values fall back to the
`generic` scoring profile rather than being inferred.
</journal_formats>

<scope>
From the validated bootstrap/evidence state, determine:

- target journal and formatting requirements
- paper type: new result, new method, comparison, or review
- the one key result or honestly narrowed claim
- target audience
- available evidence and decisive comparison artifacts

Every section must support, contextualize, or explain the key result. If the key
result cannot be stated in one sentence, narrow the paper before scaffolding.
</scope>

<create_outline>
Generate a detailed outline tailored to the journal format.

For each section include:

- purpose in the narrative
- key content, with 3-7 concrete points
- equations to include by source artifact
- figures or tables by source artifact
- citations or citation-source IDs
- length estimate
- dependencies and evidence/proof obligations

The outline must satisfy:

1. A reader of only the Introduction understands what was done and why.
2. A reader of only the Results gets the key finding with evidence.
3. A reader of Abstract + Conclusions gets the full story in miniature.
4. The Discussion interprets the result rather than repeating it.

If `autonomy=supervised`, present the outline for approval before proceeding. If `autonomy=balanced`, treat the outline as a working draft and continue automatically unless it exposes a genuine ambiguity, missing evidence path, or scope-changing decision that needs user judgment. If `autonomy=yolo`, continue automatically after the artifact checks.
</create_outline>

<generate_files>
Create or repair the manuscript directory under the manifest-resolved
`${PAPER_DIR}`:

```text
${PAPER_DIR}/
+-- {topic_specific_stem}.tex
+-- abstract.tex
+-- introduction.tex
+-- model.tex or setup.tex
+-- methods.tex or derivation.tex
+-- results.tex
+-- discussion.tex
+-- conclusions.tex
+-- appendix_A.tex
+-- references.bib
+-- figures/
+-- Makefile
```

Prefer the canonical builder whenever a machine-readable paper spec is available:

```bash
mkdir -p "${PAPER_DIR}"
gpd paper-build "${PAPER_DIR}/PAPER-CONFIG.json" --output-dir "${PAPER_DIR}"
```

This emits `${PAPER_DIR}/{topic_specific_stem}.tex`, writes the manuscript-root
artifact manifest at `${PAPER_DIR}/ARTIFACT-MANIFEST.json`, and defines
manuscript build truth; local compiler runs are smoke checks. For
`fresh_project_bootstrap` or explicit
builder-regeneration, create `${PAPER_DIR}/PAPER-CONFIG.json` from
`{GPD_INSTALL_DIR}/templates/paper/paper-config-schema.md` if absent, set a short
underscore `output_filename`, and run `gpd paper-build` before drafting.

For `resume_existing_manuscript`, do not probe the builder with throwaway `/tmp`
configs or create optional `${PAPER_DIR}/PAPER-CONFIG.json` when an accepted
entrypoint exists. Read the schema only for real builder repair; if unclear or
audits cannot refresh, stop at `checkpoint: command_failed` or
`checkpoint: bibliography_gate`.

When authoring `${PAPER_DIR}/PAPER-CONFIG.json`:

- use the exact top-level fields from
  `{GPD_INSTALL_DIR}/templates/paper/paper-config-schema.md`
- keep `authors`, `sections`, `figures`, and `appendix_sections` as JSON arrays
- keep custom funding/collaborator text in `acknowledgments`; `gpd paper-build`
  appends this sentence automatically if missing: `This research made use of Get
  Physics Done (GPD), developed by Physical Superintelligence PBC (PSI).`
- keep `journal` to a supported builder key
- do not reuse `${PAPER_DIR}/PAPER-CONFIG.json` as the external-authoring intake
  contract

Canonical schema for `${PAPER_DIR}/ARTIFACT-MANIFEST.json`:
`{GPD_INSTALL_DIR}/templates/paper/artifact-manifest-schema.md`.

Keep this split explicit:

- `${PAPER_DIR}` is the manuscript-local scaffold root for the current subject
- `GPD/publication/{subject_slug}/intake/` stores intake/provenance only
- builder-owned manuscript artifacts remain beside that manuscript root
- GPD-owned review and response auxiliaries remain under `GPD/` / `GPD/review/`

After `gpd paper-build` runs, treat the `.tex` artifact recorded in
`${PAPER_DIR}/ARTIFACT-MANIFEST.json` as the canonical manuscript entrypoint and
refer to its basename as `MANUSCRIPT_BASENAME` in later smoke checks.
</generate_files>

<compiler_probe>
Detect `pdflatex` on PATH for later smoke checks. If unavailable, warn that
local compilation smoke checks are skipped; `.tex` generation still proceeds and
`gpd paper-build` remains the canonical manuscript scaffold contract. Do not
install TeX automatically.
</compiler_probe>

<handoff>
Before handing off to authoring, confirm:

- `${PAPER_DIR}` exists under the manifest-resolved publication root
- a concrete manuscript entrypoint, scaffold plan, or section-output plan exists
- `${PAPER_DIR}/ARTIFACT-MANIFEST.json` exists when the builder ran
- active bibliography path or citation-source input is known
- no open evidence blocker remains for central claims

Then reload:

```bash
AUTHORING_INIT=$(gpd --raw init write-paper --stage figure_and_section_authoring -- "${WRITE_PAPER_ARGUMENTS:-}")
```
</handoff>
