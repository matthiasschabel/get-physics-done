<purpose>
Own the first `respond-to-referees` boundary: resolve the manuscript subject, report-source policy, publication/review roots, review preflight, convention checks, and response-root binding before any report triage, response writing, manuscript editing, or finalization authority can load.
</purpose>

<stage_boundary>
This is the only first-stage authority for `gpd:respond-to-referees`. Do not read `workflows/respond-to-referees.md` or any downstream `workflows/respond-to-referees/*.md` authority while this stage is active.

This stage is read-only. It may inspect project/manuscript state, command context, review preflight output, selected publication/review roots, latest review/response artifact metadata, and conventions. It must not create response artifacts, edit the manuscript, spawn child agents, load response templates, or run final closeout.
</stage_boundary>

<core_principle>
Responding to referees is not adversarial -- it is collaborative improvement. Every referee comment, even an incorrect one, reveals something about how the paper communicates (or fails to communicate) its results. The goal is to produce a stronger paper, not to win an argument.

**Response principles:**

1. **Address every point.** Never ignore a comment, even if you disagree.
2. **Be specific.** "We have clarified the text" is insufficient. Quote the exact change.
3. **Be respectful.** Even when the referee is wrong, acknowledge their perspective.
4. **Separate response from changes.** The response letter explains; the manuscript shows.
5. **Track everything.** Every change, every new calculation, every decision.
</core_principle>

<process>

<step name="init">
**Initialize the response-round bootstrap context and locate paper:**

```bash
if [ -n "${ARGUMENTS:-}" ]; then
  INIT=$(gpd --raw init respond-to-referees --stage bootstrap -- "$ARGUMENTS")
else
  INIT=$(gpd --raw init respond-to-referees --stage bootstrap)
fi
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $INIT"
  # STOP; surface the error.
fi
PROJECT_ROOT=$(echo "$INIT" | gpd json get .project_root --default "")
if [ -n "$PROJECT_ROOT" ]; then
  cd "$PROJECT_ROOT" || { echo "ERROR: could not enter resolved project root: $PROJECT_ROOT"; exit 1; }
fi
```

Use `INIT.staged_loading.required_init_fields` as the bootstrap contract. Do not recreate the canonical field list here; the `respond-to-referees-stage-manifest.json` sidecar owns stage-local init fields, authorities, allowed tools, and writes.
Parse JSON for: `project_contract_gate`, manuscript routing, publication/review roots, latest review artifacts, latest response artifacts, autonomy, and research_mode.
For nested-cwd launches, use `project_root`, `selected_publication_root`, `selected_review_root`, and the resolved manuscript root from init/preflight as authority. `cd` to the selected project root before relative writes, or use absolute paths rooted there; do not infer response roots from launch cwd.

**Read mode settings:**

```bash
AUTONOMY=$(echo "$INIT" | gpd json get .autonomy --default supervised)
RESEARCH_MODE=$(echo "$INIT" | gpd json get .research_mode --default balanced)
```

**Mode-aware behavior:**
- `autonomy=supervised` (default): Pause after each referee point for user review of the proposed response.
- `autonomy=balanced`: Draft the full response and apply routine manuscript changes. Do not force a parse-confirmation pause; pause only if the referee report is ambiguous, the response needs claim-level changes, new calculations, or unresolved referee disagreements. Any spawned agent that needs user input follows the publication stage-recovery gate checkpoint semantics.
- `autonomy=yolo`: Draft response and apply manuscript changes without pausing.

**Normalize command intake into one manuscript subject plus one or more report sources before preflight:**

- Preferred explicit intake: `gpd:respond-to-referees --manuscript path/to/main.tex --report reviews/ref1.md --report reviews/ref2.md`
- Accept the literal `paste` sentinel as an explicit report source.
- Accept the positional shorthand `gpd:respond-to-referees path/to/report.md` or `gpd:respond-to-referees paste` only when the manuscript subject resolves from the current GPD project.
- Treat a bare positional path as a referee-report source only. Do not reinterpret it as the manuscript subject for this workflow.
- Keep all GPD-authored auxiliary outputs under the preflight-selected GPD publication/review roots even when the manuscript subject itself is external, and keep manuscript edits on the resolved manuscript subject.
- Project-backed response rounds keep the current global `GPD/` / `GPD/review/` ownership. If centralized preflight resolves an explicit external publication subject with `selected_publication_root=GPD/publication/{subject_slug}` and `selected_review_root=GPD/publication/{subject_slug}/review`, keep the same round-artifact family inside those managed roots instead of writing sidecars beside `${PAPER_DIR}`.
- Set `PREFLIGHT_ARGUMENTS` to the validator-safe normalized intake string before shelling out. For the explicit `--manuscript ... --report ...` lane, keep the normalized manuscript/report payload in that single variable and do not explode it back into separate validator argv tokens.

Run centralized context preflight before continuing:

```bash
if [ -n "$PREFLIGHT_ARGUMENTS" ]; then
  CONTEXT=$(gpd --raw validate command-context respond-to-referees -- "$PREFLIGHT_ARGUMENTS")
else
  CONTEXT=$(gpd --raw validate command-context respond-to-referees "$ARGUMENTS")
fi
if [ $? -ne 0 ]; then
  echo "$CONTEXT"
  exit 1
fi
```

Run the centralized review preflight before continuing:

```bash
if [ -n "$PREFLIGHT_ARGUMENTS" ]; then
  REVIEW_PREFLIGHT=$(gpd validate review-preflight respond-to-referees --strict -- "$PREFLIGHT_ARGUMENTS")
elif [ -n "$ARGUMENTS" ]; then
  REVIEW_PREFLIGHT=$(gpd validate review-preflight respond-to-referees "$ARGUMENTS" --strict)
else
  REVIEW_PREFLIGHT=$(gpd validate review-preflight respond-to-referees --strict)
fi
if [ $? -ne 0 ]; then
  echo "$REVIEW_PREFLIGHT"
  exit 1
fi
```

When the normalized payload begins with `--`, the end-of-options marker is mandatory in both validator calls; otherwise the validator CLI will reinterpret `--manuscript` or `--report` as its own options instead of as subject text.
Use the literal `paste` sentinel when collecting inline report text. Do not pass the raw pasted referee report body as `$ARGUMENTS` to the strict preflight command.
Do not pass the raw pasted referee report body as `PREFLIGHT_ARGUMENTS` either; only the literal `paste` sentinel is validator-safe.

If review preflight exits nonzero because of missing project state, missing manuscript, missing referee report source when provided as a path, degraded review integrity, or missing required conventions, STOP and show the blocking issues before drafting responses.
In explicit external-manuscript mode, `project_state` and `conventions` are advisory only. The hard intake blockers remain the resolved manuscript subject, the report-source set, and review-integrity failures.
Apply the shared publication bootstrap preflight exactly:

@{GPD_INSTALL_DIR}/references/publication/publication-bootstrap-preflight.md

Treat the project contract as authoritative only when
`project_contract_gate.authoritative` is true. Bootstrap carries the gate and
load/validation status, not the full contract body; if the response needs
contract text, wait for the revision-planning or response-authoring stage that
selects the contract body.
If `derived_manuscript_reference_status` is present, use it as a quick manuscript-local summary of what is already cited, what is still pending, and what probably needs a bibliography refresh; keep `${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json` and the other manuscript-root publication artifacts authoritative for strict response and packaging decisions.
If `derived_manuscript_proof_review_status` is present, use it as the first-pass manuscript-local summary of proof-review freshness for theorem-bearing revisions; keep passed proof-redteam artifacts and the manuscript-root publication artifacts authoritative for strict response and packaging decisions.

**Locate paper directory:**

Bind `PAPER_DIR` to the manuscript root resolved either from explicit `--manuscript` intake or by the shared preflight and manuscript-root contract above, keep every manuscript-local path rooted there, and do not re-derive a second manuscript root later in this workflow. Set `MANUSCRIPT_BASENAME` from the resolved manuscript entrypoint for later rebuild and smoke-check steps.

**If no paper found:**

```
No paper directory found. Searched the canonical manuscript roots `paper/`, `manuscript/`, and `draft/` via the manuscript resolver

Run gpd:write-paper first to generate a manuscript from research results.
```

Exit.

Treat every resolved manuscript file path as rooted under `${PAPER_DIR}`, including nested section files such as `${PAPER_DIR}/{section}.tex` and any optional manuscript-local response-letter companion such as `${PAPER_DIR}/response-letter.tex` when the journal requires one.

**Convention verification** — referee responses must use the same conventions as the paper:

```bash
CONV_CHECK=$(gpd --raw convention check 2>/dev/null)
if [ $? -ne 0 ]; then
  echo "WARNING: Convention verification failed — resolve before drafting referee responses"
  echo "$CONV_CHECK"
fi
```

If the check fails, resolve convention mismatches before proceeding. New calculations or derivations in the response must use the same conventions as the published manuscript.

**Select canonical response roots and check for existing referee response files:**

Use `selected_publication_root` and `selected_review_root` from the target-aware preflight as the response roots. Bind the concrete response paths once. Default project subjects resolve to `GPD/AUTHOR-RESPONSE{round_suffix}.md` and `GPD/review/REFEREE_RESPONSE{round_suffix}.md`; explicit external or managed publication subjects resolve to subject-owned roots.

```bash
RESPONSE_PUBLICATION_ROOT=$(echo "$CONTEXT" | gpd json get .selected_publication_root --default GPD)
RESPONSE_REVIEW_ROOT=$(echo "$CONTEXT" | gpd json get .selected_review_root --default "")
if [ -z "$RESPONSE_REVIEW_ROOT" ]; then
  RESPONSE_REVIEW_ROOT="${RESPONSE_PUBLICATION_ROOT}/review"
fi
RESPONSE_AUTHOR_PATH="${RESPONSE_PUBLICATION_ROOT}/AUTHOR-RESPONSE{round_suffix}.md"
RESPONSE_REFEREE_PATH="${RESPONSE_REVIEW_ROOT}/REFEREE_RESPONSE{round_suffix}.md"
if [ -d "${RESPONSE_REVIEW_ROOT}" ]; then
  find "${RESPONSE_REVIEW_ROOT}" -maxdepth 1 -type f -name 'REFEREE_RESPONSE*.md' -print
fi
if [ -d "${RESPONSE_PUBLICATION_ROOT}" ]; then
  find "${RESPONSE_PUBLICATION_ROOT}" -maxdepth 1 -type f -name 'AUTHOR-RESPONSE*.md' -print
fi
```

Load listings only as continuation context; do not infer `round_suffix` from them. The shared handoff below remains authoritative for latest-round detection and sibling-artifact pairing.

**Check for staged peer-review decision artifacts:**

```bash
if [ -d "${RESPONSE_REVIEW_ROOT}" ]; then
  find "${RESPONSE_REVIEW_ROOT}" -maxdepth 1 -type f -name 'REVIEW-LEDGER*.json' -print
  find "${RESPONSE_REVIEW_ROOT}" -maxdepth 1 -type f -name 'REFEREE-DECISION*.json' -print
fi
```

If matching round-specific files exist, load them as structured context, but keep the shared handoff below as the canonical source for active-round selection and paired response-artifact discovery.
Use the staged report-triage references below for `round_suffix`, sibling-artifact discovery, and the canonical response-artifact pair for the active round. `${RESPONSE_PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.md` remains the canonical issue-ID source, and `REVIEW-LEDGER*.json` / `REFEREE-DECISION*.json` still identify blocking issues, unsupported-claim findings, recommendation floors, and the referee's stated rationale. Keep `project_contract`, `project_contract_gate`, `project_contract_load_info`, `project_contract_validation`, and `active_reference_context` visible together only in the later revision-planning/response-authoring stages that select those fields; treat the contract as approved scope only when `project_contract_gate.authoritative` is true.
</step>

</process>
