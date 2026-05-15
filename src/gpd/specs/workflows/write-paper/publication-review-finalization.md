<purpose>
Own publication review routing, final adjudication handoff, final manuscript
checks, and in-workflow revision/response artifacts.
</purpose>

<stage_boundary>
This stage is a compact routing/finalization surface. It eagerly loads only the
publication-review stage instructions and review-round artifact contract.
Response authoring, recovery, paper-quality scoring, and reliability diagnostics
are conditional branches. Peer-review panel execution, review-ledger schemas,
referee-decision schemas, and proof-redteam details stay inside staged
`gpd:peer-review` authorities and must not be inlined here.

Start only after manuscript-root artifacts, fresh bibliography audit,
reproducibility manifest, and claim/proof blockers are clear.
</stage_boundary>

<init>
Load the staged publication-review payload before routing peer review or
evaluating review-round artifacts:

```bash
PUBLICATION_REVIEW_INIT=$(gpd --raw init write-paper --stage publication_review -- "${WRITE_PAPER_ARGUMENTS:-}")
if [ $? -ne 0 ]; then
  echo "ERROR: write-paper publication-review init failed: $PUBLICATION_REVIEW_INIT"
  # STOP; surface the error.
fi
INIT="$PUBLICATION_REVIEW_INIT"
```

Apply `PUBLICATION_REVIEW_INIT.staged_loading.field_access_instruction` before reading `PUBLICATION_REVIEW_INIT`.
</init>

<pre_submission_review>
Branch by write-paper lane before finalizing.

**Project-backed lane:** route to staged `gpd:peer-review` for the resolved
`${PAPER_DIR}/{topic_specific_stem}.tex` target recorded in
`ARTIFACT-MANIFEST.json`. Use the peer-review stage manifest for panel
execution, final adjudication, review-ledger/referee-decision schemas, and any
proof-redteam gate. Do not inline those authorities here.
Load `proactive_critique_loop` when budget allows; log run/skip/failure.

This write-paper stage may read review-round artifacts after peer review returns.
Load the conditional `response_pair_authoring` authorities only when paired
response artifacts are actually being drafted.

Use `gpd-referee` only through the peer-review final-adjudication authority. Keep
the project-contract gate fields, reference handles/statuses, citation-source
context, and protocol load manifests visible. Read a specific reference or
protocol source file only when a concrete review finding, response issue, or
routing decision depends on its body.

Read `${selected_review_root}/REFEREE-DECISION{round_suffix}.json` and
`${selected_review_root}/REVIEW-LEDGER{round_suffix}.json` first when they
exist, then read `${selected_publication_root}/REFEREE-REPORT{round_suffix}.md`
and assess the findings.

**External-authoring lane:** do **not** run the embedded staged panel here.
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

Paper quality scoring is advisory and artifact-driven. Load the
`advisory_paper_quality_scoring` authority only when the score is still
decisive. Use
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
3. Load `response_pair_authoring` authorities only after manuscript edits land,
   then produce paired response artifacts through `gpd-paper-writer`.

Pass `<autonomy_mode>{AUTONOMY}</autonomy_mode>`,
`<research_mode>{RESEARCH_MODE}</research_mode>`, selected roots, round,
referee report, optional ledger/decision paths, manifest-resolved manuscript
tree, and the concrete author/referee response paths. For each `REF-xxx` issue,
classify it only after the corresponding manuscript edits exist on disk.

Response-pair completion is delegated to
`publication-response-writer-handoff.md` plus `stage-recovery-gate.md` under the
`response_pair_authoring` condition. Keep the callsite identifier
`id: "write_paper_response_pair"` when applying that delegated gate, with
`${selected_publication_root}/AUTHOR-RESPONSE{round_suffix}.md` and
`${selected_review_root}/REFEREE_RESPONSE{round_suffix}.md` as the expected
outputs. Both response paths must pass handoff artifact validation, round
binding, manuscript binding, allowed-root checks, and freshness checks before
this stage treats the response pair as complete.

Response-pair child gate:

```yaml
child_gate:
  id: "write_paper_response_pair"
  role: "gpd-paper-writer"
  return_profile: "paper_writer"
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
  failure_route: "stage-recovery-gate -> retry response writer | stop incomplete"
```

Response-pair completion requires this callsite tuple to pass for both paths.

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
