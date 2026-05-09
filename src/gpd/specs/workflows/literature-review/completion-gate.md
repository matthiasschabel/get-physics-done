<purpose>
Verify review completion and sidecar freshness before presenting results.
</purpose>

<process>

<step name="return_results">
Return to orchestrator through the typed child-return contract. Route on `gpd_return.status` and the artifact gate; the `## REVIEW COMPLETE` and `## CHECKPOINT REACHED` headings are presentation only.

```bash
COMPLETION_GATE_INIT=$(load_literature_review_stage completion_gate "${topic:-$ARGUMENTS}")
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $COMPLETION_GATE_INIT"
  exit 1
fi
```

Use `gpd --raw stage field-access literature-review --stage completion_gate --style instruction` to confirm the manifest-selected completion fields. Read only those keys from `COMPLETION_GATE_INIT`; `COMPLETION_GATE_INIT.staged_loading.required_init_fields` is the runtime confirmation before presenting results.

On completion:

- Verify `GPD/literature/{slug}-REVIEW.md` exists on disk
- Verify `GPD/literature/{slug}-CITATION-SOURCES.json` exists on disk and remains aligned with the review's Full Reference List
- Verify `GPD/literature/{slug}-CITATION-AUDIT.md` is fresh for the current review and sidecar
- Return `gpd_return.status: completed` only when the review, citation sidecar, and citation audit are named in `gpd_return.files_written` and present/readable on disk
- Include `papers_reviewed`, `field_assessment`, and citation verification details as needed
- If any required artifact is missing, malformed, or stale, return `gpd_return.status: blocked` or `failed` instead of `completed`

On checkpoint:

- Return `gpd_return.status: checkpoint`
- Include the decision question, context, options, and partial progress
- Record the user's answer as `checkpoint_response` for the fresh continuation handoff.
- Do not trust the runtime handoff status by itself.
- Stop and let the orchestrator present the checkpoint to the user, then spawn a fresh continuation run after the response

If the review is incomplete or blocked, use `gpd_return.status: blocked` or `failed` and list the missing artifact or unresolved scope issue explicitly.

</step>

</process>

<success_criteria>

- [ ] Source hierarchy followed (textbooks -> reviews -> papers -> arXiv -> web)
- [ ] Foundational works identified with key contributions
- [ ] Methods cataloged with regimes, limitations, and key references
- [ ] Results tabulated with uncertainties and conventions
- [ ] Citation network traced showing intellectual development
- [ ] Controversies and disagreements documented
- [ ] Open questions identified with feasibility assessment
- [ ] Current frontier mapped (recent results, active groups, emerging methods)
- [ ] Conventions cataloged across references
- [ ] LITERATURE-REVIEW.md created with all sections
- [ ] Recommended reading path provided
- [ ] Citations verified via gpd-bibliographer (no hallucinated references)

</success_criteria>
