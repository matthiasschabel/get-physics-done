<purpose>
Own response artifact pair creation, response-template use, synchronized manuscript edits, paper-writer revision handoffs, bounded revision verification, bibliography freshness, and optional manuscript-local response-letter generation.
</purpose>

<stage_boundary>
Load this stage only after revision planning has classified referee points and routed any new-calculation work. This is the first stage allowed to load `templates/paper/author-response.md`, `templates/paper/referee-response.md`, and response-writing child handoff authority.

This stage may write the canonical response pair and manuscript revisions under the manifest write allowlist. It must not run final commit/closeout routing until the finalize stage loads.
</stage_boundary>

<process>

<step name="create_response_file">
Load the revision-planning stage before response authoring so comment classification and response artifacts use the same staged authority order:

```bash
if [ -n "${PREFLIGHT_ARGUMENTS:-}" ]; then
  REVISION_PLANNING_INIT=$(gpd --raw init respond-to-referees --stage revision_planning -- "$PREFLIGHT_ARGUMENTS")
elif [ -n "${ARGUMENTS:-}" ]; then
  REVISION_PLANNING_INIT=$(gpd --raw init respond-to-referees --stage revision_planning -- "$ARGUMENTS")
else
  REVISION_PLANNING_INIT=$(gpd --raw init respond-to-referees --stage revision_planning)
fi
if [ $? -ne 0 ]; then
  echo "ERROR: respond-to-referees revision-planning init failed: $REVISION_PLANNING_INIT"
  # STOP; surface the error.
fi
```

Load the response-authoring stage before writing response artifacts or applying manuscript edits:

```bash
if [ -n "${PREFLIGHT_ARGUMENTS:-}" ]; then
  RESPONSE_AUTHORING_INIT=$(gpd --raw init respond-to-referees --stage response_authoring -- "$PREFLIGHT_ARGUMENTS")
elif [ -n "${ARGUMENTS:-}" ]; then
  RESPONSE_AUTHORING_INIT=$(gpd --raw init respond-to-referees --stage response_authoring -- "$ARGUMENTS")
else
  RESPONSE_AUTHORING_INIT=$(gpd --raw init respond-to-referees --stage response_authoring)
fi
if [ $? -ne 0 ]; then
  echo "ERROR: respond-to-referees response-authoring init failed: $RESPONSE_AUTHORING_INIT"
  # STOP; surface the error.
fi
```

**Create the structured referee response document:**

Read the canonical templates at `{GPD_INSTALL_DIR}/templates/paper/author-response.md` and `{GPD_INSTALL_DIR}/templates/paper/referee-response.md` using the runtime's normal file-read mechanism. Use the publication response-writer handoff already loaded during initialization.

Create both response artifacts for the current round:

- `${RESPONSE_AUTHOR_PATH}` — structured internal tracker keyed by `REF-*` issues, change locations, staged review outcomes, and new-calculation status
- `${RESPONSE_REFEREE_PATH}` — journal-facing response letter built from the template

Those two GPD-owned response artifacts stay canonical even when the manuscript subject is explicit or external. Use `selected_publication_root` / `selected_review_root` for subject-owned roots. Do not write `AUTHOR-RESPONSE*` or `REFEREE_RESPONSE*` beside `${PAPER_DIR}` or beside the imported report source. Do not duplicate the pair into both the subject-owned root and the global project root in one run.

Populate `${RESPONSE_REFEREE_PATH}` with paper metadata, decision summaries, mirrored per-comment classification/status fields from the canonical response templates, blocking items from `REVIEW-LEDGER*.json` when available, and the progress tracking table. Leave response and changes-made fields empty until the later draft/revision step fills them.

Before writing `${RESPONSE_AUTHOR_PATH}`, load the canonical template at `{GPD_INSTALL_DIR}/templates/paper/author-response.md` and keep the internal tracker aligned with it.

Populate `${RESPONSE_AUTHOR_PATH}` with one section per `REF-*` issue, classification (`fixed`, `rebutted`, `acknowledged`, `needs-calculation`), exact manuscript change locations or planned follow-up work, `New calculations required` and `Source phase for new work` when needed, and any blocking / recommendation-floor context imported from `REVIEW-LEDGER*.json` or `REFEREE-DECISION*.json`. Use `**Evidence:**` blocks for rebuttals and `**Plan:**` blocks for acknowledged or `needs-calculation` responses when needed.

Commit the initial response file:

```bash
PRE_CHECK=$(gpd pre-commit-check --files "${RESPONSE_REFEREE_PATH}" "${RESPONSE_AUTHOR_PATH}" 2>&1) || true
echo "$PRE_CHECK"

gpd commit \
  "docs: create referee response structure" \
  --files "${RESPONSE_REFEREE_PATH}" "${RESPONSE_AUTHOR_PATH}"
```

Keep the two files synchronized for the rest of the workflow: draft issue-by-issue substance in `${RESPONSE_AUTHOR_PATH}`, and mirror the journal-facing prose into `${RESPONSE_REFEREE_PATH}`.

Treat `${RESPONSE_AUTHOR_PATH}` and `${RESPONSE_REFEREE_PATH}` as the response success gate. The shared response-artifact contract owns freshness, metadata binding, and fail-closed completion.

Successful response states:

| State | Requirements |
|---|---|
| `current` | same-round target-bound pair inspected, frontmatter binds to resolved manuscript/round, no material writes; report `command_execution_state: read_only_inspection`, artifacts, and `files_written: none` |
| `completed_this_run` | both canonical paths written/refreshed by this invocation or fresh child handoff and named in current-run `files_written` / `gpd_return.files_written`; stale drafts or one-sided files do not count |

</step>

<step name="draft_responses">
**Draft responses for all Group A and Group B items:**

Use full `reference_artifacts_content` only for comments whose response or
manuscript edit depends on reference-backed evidence. For routine wording,
formatting, or already-local manuscript changes, prefer the selected manuscript
files, latest review artifacts, and reference handles.

Resolve writer model:

```bash
WRITER_MODEL=$(gpd resolve-model gpd-paper-writer)
```

**For Group A (response-only) items:**

Draft each response in `${RESPONSE_AUTHOR_PATH}`, then mirror the polished journal-facing wording into `${RESPONSE_REFEREE_PATH}`. For each comment:

- Quote the referee's exact words
- Write the assessment (is the referee correct, partially correct, or mistaken?)
- Draft a respectful, specific response
- Note "No manuscript change needed" in the changes section
- Set status to "Response drafted"

**For Group B (manuscript revision) items:**

Group revision items by affected section to minimize agent spawns. For each affected section, spawn a paper-writer agent:
@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md

> Apply the canonical runtime delegation convention already loaded above.

```
task(
  prompt="First, read {GPD_AGENTS_DIR}/gpd-paper-writer.md for your role and instructions.\n\nRead the canonical <author_response> protocol at {GPD_INSTALL_DIR}/templates/paper/author-response.md, the canonical referee response template at {GPD_INSTALL_DIR}/templates/paper/referee-response.md, and the shared publication response-writer handoff at {GPD_INSTALL_DIR}/references/publication/publication-response-writer-handoff.md. You own both the manuscript edits and the response-tracker updates for this section. Make the manuscript changes first, then update the response trackers for the same comments. Return through the `respond_to_referees_revision_section` child_gate so the revised section file plus `${RESPONSE_AUTHOR_PATH}` and `${RESPONSE_REFEREE_PATH}` are all named.\n\n<autonomy_mode>{AUTONOMY}</autonomy_mode>\n<research_mode>{RESEARCH_MODE}</research_mode>\n" + revision_prompt,
  subagent_type="gpd-paper-writer",
  model="{writer_model}",
  readonly=false,
  description="Revise: {section_name}"
)
```

Revision-section child gate:

```yaml
child_gate:
  id: "respond_to_referees_revision_section"
  role: "gpd-paper-writer"
  return_profile: "response_writer"
  required_status: "completed"
  expected_artifacts:
    - "${PAPER_DIR}/{resolved_section_file}"
    - "${RESPONSE_AUTHOR_PATH}"
    - "${RESPONSE_REFEREE_PATH}"
  allowed_roots:
    - "${PAPER_DIR}"
    - "${selected_publication_root}"
    - "${selected_review_root}"
  freshness_marker: "after $REVISION_SECTION_HANDOFF_STARTED_AT"
  validators:
    - "gpd validate handoff-artifacts for revised section plus both response artifacts"
    - "publication-response-writer-handoff.md frontmatter, round, and manuscript binding"
    - "target section has expected revision markers or substantive edits"
    - "affected comment block updated in both response artifacts"
  applicator: "none"
  failure_route: "continue other sections, then retry failed sections | main-context targeted revision | skip failed sections; checkpoint -> stage-recovery gate and fresh continuation"
```

Each revision agent receives:

- The specific referee comments affecting this section (with full quotes)
- The current section text (read from the resolved section file within the manuscript tree rooted at `${PAPER_DIR}`, allowing nested subdirectories)
- The planned response strategy for each comment
- Explicit ownership of both the manuscript edits and the response-tracker updates for this section; the paper-writer must not treat the handoff as complete until both are written
- Relevant `GPD/comparisons/*-COMPARISON.md` files and `FIGURE_TRACKER.md` entries for decisive claims mentioned in the section
- `protocol_bundle_context` and `selected_protocol_bundle_ids` as additive specialized guidance only; they help preserve benchmark anchors, decisive artifacts, and estimator caveats during revision, but do not create new claims or replace the review ledger
- Instruction to make minimal, targeted changes (do NOT rewrite the section)
- Instruction to mark changed text with `% REVISED: Referee X, Comment Y` LaTeX comments for tracking

**If a revision agent fails to spawn or returns an error:** Apply the `respond_to_referees_revision_section` tuple and `{GPD_INSTALL_DIR}/references/publication/stage-recovery-gate.md` for that section. Continue with other sections, then report failed sections and offer: 1) Retry failed sections, 2) Apply revisions manually in the main context, 3) Skip failed sections and proceed.

After each agent returns, verify the promised artifacts before trusting the handoff text:
- Re-apply the `respond_to_referees_revision_section` tuple first.
- Re-read the targeted resolved section file under `${PAPER_DIR}` and confirm the expected revision markers or substantive edits landed.
- Re-open `${RESPONSE_AUTHOR_PATH}` and `${RESPONSE_REFEREE_PATH}` and confirm the affected comment block now contains the updated assessment / changes-made text.
- If the section file changed but the response trackers did not, or vice versa, treat that section as failed and route it through the retry/manual options above instead of silently proceeding.

Only after those checks pass, update both `${RESPONSE_AUTHOR_PATH}` and `${RESPONSE_REFEREE_PATH}`:
- Fill in "Changes made" with specific locations (section, page, equation)
- Set status to "Response drafted"

</step>

<step name="revision_loop">
**Bounded revision verification (max 3 iterations):**

After all Group B revisions are applied, verify the revised manuscript compiles and is internally consistent:

```bash
cd "${PAPER_DIR}"
pdflatex -interaction=nonstopmode "${MANUSCRIPT_BASENAME}" 2>&1 | tail -20
bibtex "${MANUSCRIPT_BASENAME%.*}" 2>&1 | tail -10
pdflatex -interaction=nonstopmode "${MANUSCRIPT_BASENAME}" 2>&1 | tail -5
```

**If compilation errors:** Fix and retry (does not count as iteration).

**Consistency check (counts as iteration):**

1. Verify notation consistency in revised sections
2. Check that new equations are numbered and referenced correctly
3. Verify new citations exist in .bib file — for any NEW citations added during revision, verify metadata accuracy (author, year, journal) via `gpd pattern search` or web search. Referee-suggested references are usually real but may have wrong metadata.
4. Check cross-references to new or renumbered equations/figures
5. Resolve any `MISSING:` citation markers left by the paper-writer (see write-paper workflow for the resolution protocol)
6. Re-check any decisive `comparison_verdicts` or benchmark anchors touched by the revision. If protocol bundles are selected, use them only as an additive reminder of which decisive comparisons or estimator caveats must remain visible after revision.
7. If the revision touched bibliography files or citation commands, refresh `${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json` before generating the response letter or proceeding to final review. Use `gpd paper-build` as the refresh path, and use `derived_manuscript_reference_status` as the quick read on what likely changed; the manuscript-root bibliography audit remains authoritative for the round. Stale bibliography audits are not acceptable in a referee-response round. Confirm the refreshed JSON artifact exists before treating the round as complete.
8. If a spawned paper-writer returns `status: checkpoint`, apply the publication stage-recovery gate: stop after recording the checkpoint, present it to the user, and continue only from persisted artifacts after the user responds.

**If inconsistencies found and iteration < 3:**

Spawn targeted paper-writer agents to fix specific inconsistencies. Increment iteration count.

**If iteration >= 3:**

```
Revision loop reached maximum iterations (3).

Remaining issues ({N}):
{list of unresolved inconsistencies}

Options:
1. Proceed anyway (note issues in response letter)
2. Manually fix the remaining issues
```

</step>

<step name="generate_response_letter">
**Finalize the canonical response artifacts and generate an optional manuscript-local response letter companion:**

Before response-pair completion, read `${RESPONSE_AUTHOR_PATH}` and
`${RESPONSE_REFEREE_PATH}` (all comments should have status "Response drafted"
or "Final") and run the aggregate below. The already-loaded shared
publication response-writer handoff owns pair freshness and binding.

```yaml
aggregate_child_gate:
  id: respond_to_referees_response_pair_current
  required_child_gates:
    - respond_to_referees_revision_section for every launched Group B section
  expected_artifacts:
    - every required revised section under ${PAPER_DIR}
    - ${RESPONSE_AUTHOR_PATH}
    - ${RESPONSE_REFEREE_PATH}
  validators:
    - expected mirrored artifacts exist on disk
    - response frontmatter binds to the active manuscript path and review round when the subject is explicit
    - every launched section tuple passed with current section and response artifacts
  failure_route: retry failed sections | main-context targeted revision | leave response pair incomplete
```

Those two Markdown artifacts under the selected GPD publication/review roots are the canonical required outputs for this workflow. `${PAPER_DIR}/response-letter.tex` or `${PAPER_DIR}/response-letter.md` is optional and should be generated only when the journal or user asked for a manuscript-local submission companion. If the manuscript subject is an explicit external artifact, keep auxiliary response outputs under the selected GPD roots and do not write sidecars beside that external manuscript unless the main integration later exposes a subject-local export hook.
If centralized preflight resolved a subject-owned publication root at `GPD/publication/{subject_slug}` for that explicit external subject, apply the same rule there: keep the canonical response pair under `selected_publication_root` / `selected_review_root`, not beside the manuscript, and do not infer a full publication-tree relocation from this bounded continuation path.

**If any Group C items are still pending:** Warn the user before generating:

```
{N} new calculations are still pending. The response letter will note these as
"work in progress." Complete them with gpd:execute-phase before resubmission.
```

If a project-backed manuscript needs a manuscript-local response-letter companion, write `${PAPER_DIR}/response-letter.tex` or `.md` with: editor thanks, per-referee/per-comment quote, response, concrete changes, summary of major/minor changes, and signature.

</step>

</process>
