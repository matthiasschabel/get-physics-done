<purpose>
Own completed-review summarization, optional PDF note, and next-action routing.
</purpose>

<stage_boundary>
Finalize is read-only. It reads completed target-bound review artifacts and tells the
user what to do next. It does not mutate manuscript files, rewrite upstream stage
artifacts, author response packages, or change the final recommendation.
</stage_boundary>

<optional_pdf_compile>
If TeX is missing, do not block review: Continue now with
`${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.md` and
`${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.tex` only. If a polished PDF is
required, ask the user to choose whether to authorize TeX installation now or compile
the `.tex` later in an environment that already has TeX.
If a polished PDF is required, ask whether to install TeX now or compile later.
</optional_pdf_compile>

<summarize_report>
Load the staged finalize payload before summarizing the report and routing the next
action:

```bash
if [ -n "${ARGUMENTS:-}" ]; then FINALIZE_INIT=$(gpd --raw init peer-review --stage finalize -- "$ARGUMENTS"); else FINALIZE_INIT=$(gpd --raw init peer-review --stage finalize); fi
if [ $? -ne 0 ]; then echo "ERROR: gpd peer-review finalize init failed: $FINALIZE_INIT"; fi
INIT="$FINALIZE_INIT"
```

Apply `FINALIZE_INIT.staged_loading.field_access_instruction` before reading it.

```bash
REVIEW_TARGET=$(echo "$INIT" | gpd json get .review_target_input --default "")
PUBLICATION_ROOT=$(echo "$INIT" | gpd json get .selected_publication_root --default GPD)
REVIEW_ROOT=$(echo "$INIT" | gpd json get .selected_review_root --default "")
REVIEW_ROOT="${REVIEW_ROOT:-${PUBLICATION_ROOT}/review}"
```

Read the target-bound referee report for the active round:

- `${PUBLICATION_ROOT}/REFEREE-REPORT.md`
- `${PUBLICATION_ROOT}/REFEREE-REPORT-R2.md`
- `${PUBLICATION_ROOT}/REFEREE-REPORT-R3.md`

Summarize with:

```markdown
## Peer Review Summary

- Recommendation:
- Main blocking issues:
- Proof-redteam status when applicable:
- Stage artifacts:
- Next action:
```
</summarize_report>

<route_next_action>
A completed staged review of a rejected manuscript is still a completed review run.

- `accept` routes toward `gpd:arxiv-submission`.
- `minor_revision` routes to targeted edits or `gpd:respond-to-referees`.
- `major_revision` routes to `gpd:respond-to-referees` with blocking findings.
- `reject` presents highest-severity issues and avoids automatic project authoring for
  standalone explicit-artifact review unless rewriting was explicitly requested.

If the report finds unverified bibliography sources, do not present `BIBLIOGRAPHY-AUDIT.json` with no failed or unverified sources as verified. If the report
finds overclaiming, classify the manuscript claim state as overclaim-blocked rather than evidence-bound; do not turn a terminal `reject` recommendation into an automatic project-authoring command.

Response packages are atomic pairs:

- `${selected_publication_root}/AUTHOR-RESPONSE{round_suffix}.md`
- `${selected_review_root}/REFEREE_RESPONSE{round_suffix}.md`

Same-round or newer response artifacts require a newer staged peer review before
submission packaging.
</route_next_action>
