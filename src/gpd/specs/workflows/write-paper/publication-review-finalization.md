<purpose>
Own publication review routing, final adjudication handoff, final manuscript
checks, and in-workflow revision/response artifacts.
</purpose>

<stage_boundary>
This stage may load publication-review, response, panel, reliability, review
ledger, referee-decision, and stage-recovery authorities. It must start only
after manuscript-root artifacts, fresh bibliography audit, reproducibility
manifest, and claim/proof blockers are clear.
</stage_boundary>

<init>
Load the staged publication-review payload before running embedded peer review or
evaluating review-round artifacts:

```bash
PUBLICATION_REVIEW_INIT=$(gpd --raw init write-paper --stage publication_review -- "${WRITE_PAPER_ARGUMENTS:-}")
if [ $? -ne 0 ]; then
  echo "ERROR: write-paper publication-review init failed: $PUBLICATION_REVIEW_INIT"
  # STOP; surface the error.
fi
INIT="$PUBLICATION_REVIEW_INIT"
```

Use `gpd --raw stage field-access write-paper --stage publication_review --style instruction`
to confirm the manifest-selected publication-review fields before reading
`PUBLICATION_REVIEW_INIT`.
</init>

<pre_submission_review>
Branch by write-paper lane before finalizing.

**Project-backed lane:** run the staged `gpd:peer-review` authorities for the
resolved `${PAPER_DIR}/{topic_specific_stem}.tex` target recorded in
`ARTIFACT-MANIFEST.json`. Load the publication round artifact, peer-review panel,
reliability, review-ledger, referee-decision, and stage-recovery authorities
listed in this stage manifest. Do not copy the full panel protocol into
write-paper; keep behavior aligned with the standalone peer-review workflow.

Load `{GPD_INSTALL_DIR}/references/publication/publication-review-round-artifacts.md`
before review-round routing and `{GPD_INSTALL_DIR}/references/publication/publication-response-writer-handoff.md`
before paired response authoring.

Use `gpd-referee` only as the final adjudicator through the peer-review final
adjudication authority. Keep `project_contract`, `project_contract_gate`,
`project_contract_load_info`, `project_contract_validation`, and
`active_reference_context` visible throughout staged review; the contract remains
authoritative only when `project_contract_gate.authoritative` is true.

For theorem-style or `proof_obligation` claims, this stage carries the mandatory
auxiliary proof-redteam gate from peer review. Missing or open proof-redteam
artifacts are fail-closed blockers even if the rest of the manuscript review
looks clean.

Read `${selected_review_root}/REFEREE-DECISION{round_suffix}.json` and
`${selected_review_root}/REVIEW-LEDGER{round_suffix}.json` first when they
exist, then read `${selected_publication_root}/REFEREE-REPORT{round_suffix}.md`
and assess the findings.

**External-authoring lane:** do **not** run the embedded staged panel here.
Embedded `write-paper` review parity for the bounded external-authoring lane is
deferred until the managed publication lineage is unified end to end.
Embedded `write-paper` review parity for the bounded external-authoring lane is deferred until the managed publication lineage is unified end to end.

Instead, verify the bounded manuscript-root handoff under `${PAPER_DIR}`:

- `${PAPER_DIR}/{topic_specific_stem}.tex`
- `${PAPER_DIR}/PAPER-CONFIG.json`
- `${PAPER_DIR}/ARTIFACT-MANIFEST.json`
- `${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json`
- `${PAPER_DIR}/reproducibility-manifest.json`
- `${PAPER_DIR}/FIGURE_TRACKER.md` when the manuscript uses tracked figures

If any required manuscript-root artifact is missing, stop and fix it now.
Otherwise, route the user to standalone `gpd:peer-review` against the resolved
manuscript root or entrypoint. Do not claim full pre-submission review parity
here, and do not recommend `gpd:arxiv-submission` directly from this lane.
</pre_submission_review>

<final_review>
Before declaring the draft complete, run only decisive checks unless the user
explicitly requested polish:

- artifact manifest
- bibliography audit
- reproducibility manifest
- target-bound review state
- abstract/story consistency
- introduction/conclusion contribution
- equations and figures
- page count and reference formatting

Paper quality scoring is advisory and artifact-driven through
`{GPD_INSTALL_DIR}/references/publication/paper-quality-scoring.md`. Use
`${PAPER_DIR}/ARTIFACT-MANIFEST.json`, `${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json`,
`${PAPER_DIR}/FIGURE_TRACKER.md`, `GPD/comparisons/*-COMPARISON.md`, and phase
summary/verification `contract_results` and `comparison_verdicts`. Treat paper-support artifacts as scaffolding, not as proof that a claim is established.
Missing decisive comparisons still block strong submission recommendations.
Recommend `gpd:arxiv-submission` only when project-backed staged review already
clears packaging.

Run paper-quality scoring from project artifacts when it is still decisive:

```bash
gpd validate paper-quality --from-project .
```

Skip paper-quality scoring if `review_gate` is decisive or finalization budget is
at risk. Skipping does not weaken bibliography freshness or peer-review
requirements.
</final_review>

<paper_revision>
For a dedicated referee response workflow, use `gpd:respond-to-referees`. This
in-workflow revision loop applies only after project-backed embedded review. The
bounded external-authoring lane exits earlier and should resume through
standalone `gpd:peer-review` or `gpd:respond-to-referees` once review artifacts
exist.

When revising a paper in response to referee reports:

1. Parse each referee point into a structured item with category and affected
   manuscript section(s).
2. Spawn targeted section revision agents for manuscript changes; a point is not
   `fixed` until the corresponding section file changes have landed on disk.
3. Produce paired response artifacts after manuscript edits land.

```
task(
  subagent_type="gpd-paper-writer",
  model="{writer_model}",
  readonly=false,
  prompt="First, read {GPD_AGENTS_DIR}/gpd-paper-writer.md for your role and instructions.\n\nRead the canonical <author_response> protocol at {GPD_INSTALL_DIR}/templates/paper/author-response.md, the canonical referee response template at {GPD_INSTALL_DIR}/templates/paper/referee-response.md, and the shared publication response-writer handoff at {GPD_INSTALL_DIR}/references/publication/publication-response-writer-handoff.md. Produce both response artifacts at the concrete paths below.\n\n<autonomy_mode>{AUTONOMY}</autonomy_mode>\n<research_mode>{RESEARCH_MODE}</research_mode>\n" +
    "selected_publication_root: ${selected_publication_root}\n" +
    "selected_review_root: ${selected_review_root}\n" +
    "author_response_path: ${selected_publication_root}/AUTHOR-RESPONSE{round_suffix}.md\n" +
    "referee_response_path: ${selected_review_root}/REFEREE_RESPONSE{round_suffix}.md\n" +
    "Referee report: ${selected_publication_root}/REFEREE-REPORT{round_suffix}.md\n" +
    "Review ledger (if present): ${selected_review_root}/REVIEW-LEDGER{round_suffix}.json\n" +
    "Decision artifact (if present): ${selected_review_root}/REFEREE-DECISION{round_suffix}.json\n" +
    "Manuscript tree: all .tex files under ${PAPER_DIR} recursively, rooted at the manifest-resolved manuscript directory, after the section revision agents have landed their edits\n" +
    "Round: {N}\n\n" +
    "For each REF-xxx issue, classify as fixed/rebutted/acknowledged/needs-calculation only after the corresponding manuscript edits exist on disk.\n" +
    "Write to ${selected_publication_root}/AUTHOR-RESPONSE{round_suffix}.md and ${selected_review_root}/REFEREE_RESPONSE{round_suffix}.md",
  description="Author response: round {N}"
)
```

Response-pair child gate:

```yaml
child_gate:
  id: "write_paper_response_pair"
  role: "gpd-paper-writer"
  return_profile: "response_writer"
  required_status: "completed"
  expected_artifacts:
    - "${selected_publication_root}/AUTHOR-RESPONSE{round_suffix}.md"
    - "${selected_review_root}/REFEREE_RESPONSE{round_suffix}.md"
  allowed_roots:
    - "${selected_publication_root}"
    - "${selected_review_root}"
  freshness_marker: "after $RESPONSE_HANDOFF_STARTED_AT"
  validators:
    - "gpd validate handoff-artifacts for both response paths"
    - "publication-response-writer-handoff.md frontmatter, round, and manuscript binding"
  applicator: "none"
  failure_route: "retry agent | main-context response drafting | skip structured response and proceed to calculation tracking"
```

Apply `{GPD_INSTALL_DIR}/references/publication/stage-recovery-gate.md` through this tuple before treating the response pair as complete. Every paired response completion depends on `gpd_return.files_written` plus on-disk verification of both paths.

Track new calculations in `${PAPER_DIR}/REVISION_TASKS.md`. After targeted
revisions, rerun consistency/reference checks and then this publication-review
stage. Stop after three bounded iterations and surface remaining issues.
</paper_revision>

<success_criteria>
- [ ] Project-backed lane: staged peer-review round completed, including final
      adjudication and proof-redteam artifacts when required.
- [ ] External-authoring lane: manuscript-root artifacts exist under
      `GPD/publication/{subject_slug}/manuscript`, and the workflow routed to
      standalone `gpd:peer-review`.
- [ ] Major staged-review issues were addressed or explicitly acknowledged.
- [ ] The bounded external-authoring lane did not widen into generic folder
      mining or direct `gpd:arxiv-submission` claims.
</success_criteria>

<community_contribution>
After a finalized draft passes peer review, mention that public papers can be
added to the README.md "Papers Using GPD" list at
https://github.com/psi-oss/get-physics-done#papers-using-gpd with a short
problem/approach summary, workflow used, and optional key result or figure. This
prompt is informational only; do not block the paper workflow on it.
</community_contribution>
