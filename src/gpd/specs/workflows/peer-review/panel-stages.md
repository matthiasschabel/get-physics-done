<purpose>
Own Stage 1 claim extraction, Stages 2-5 specialist review, conditional same-round
proof-redteam review, and stage-artifact validation.
</purpose>

<stage_boundary>
Panel stages start only after bootstrap, preflight, and artifact discovery have
resolved the target and round state. Each stage runs in a fresh subagent context
and writes a compact artifact. Apply
`{GPD_INSTALL_DIR}/references/publication/stage-recovery-gate.md` for spawned
reviewer/proof-auditor/referee lifecycle, checkpoint continuation,
stale-output rejection, retry freshness, and sequential fallback cleanup. Each
downstream stage begins from persisted artifacts plus the declared
carry-forward inputs for that stage.

The stage manifest loads `references/publication/peer-review-panel.md` for the
machine contract and `references/publication/peer-review-panel-playbook.md` for
Stage 1-5 reviewer guidance.

Bundle guidance from `protocol_bundle_context` is additive only. Reader-visible
claims, surfaced evidence, `${MANUSCRIPT_ROOT}/FIGURE_TRACKER.md`,
`GPD/comparisons/*-COMPARISON.md`, and review-support artifacts are scaffolding
and remain first-class; do not let bundle guidance invent new claims.
</stage_boundary>

<announce_panel>
Load the staged panel payload before launching Stage 1 through Stage 5 and the
conditional proof audit:

```bash
PANEL_INIT=$(gpd --raw init peer-review "$REVIEW_TARGET" --stage panel_stages)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd peer-review panel init failed: $PANEL_INIT"
  # STOP; surface the error.
fi
```

Before spawning any reviewer, announce the review with this concise stage map:

`Launching the six-stage review panel: Stage 1 maps the paper's claims; Stages 2-3 check prior work and mathematical soundness in parallel; theorem-style claims also trigger the auxiliary gpd-check-proof audit; Stage 4 checks whether the physical interpretation is supported; Stage 5 judges significance and venue fit; Stage 6 synthesizes everything into the final recommendation.`
</announce_panel>

<child_return_contract>
Use these local stage tuples for the panel callsites. Stage identity is
callsite-owned: derive it from the tuple `role`, expected artifact paths, write
allowlist, canonical filenames, and validators; never trust a stage label inside
`gpd_return`. Fresh `gpd_return.files_written` evidence is accepted only through
the matching tuple gate.

```yaml
peer_review_stage1_reader:
  role: gpd-review-reader
  expected_artifacts: ["${REVIEW_ROOT}/CLAIMS{round_suffix}.json", "${REVIEW_ROOT}/STAGE-reader{round_suffix}.json"]
  validators:
    - "gpd validate review-claim-index ${REVIEW_ROOT}/CLAIMS{round_suffix}.json"
    - "gpd validate review-stage-report ${REVIEW_ROOT}/STAGE-reader{round_suffix}.json with stage_id=reader and stage_kind=reader"
  failure_route: retry_stage_once_then_stop

peer_review_stage2_literature:
  role: gpd-review-literature
  expected_artifacts: ["${REVIEW_ROOT}/STAGE-literature{round_suffix}.json"]
  validators: ["gpd validate review-stage-report ${REVIEW_ROOT}/STAGE-literature{round_suffix}.json with stage_id=literature and stage_kind=literature"]
  failure_route: retry_stage_once_then_stop

peer_review_stage3_math:
  role: gpd-review-math
  expected_artifacts: ["${REVIEW_ROOT}/STAGE-math{round_suffix}.json"]
  validators: ["gpd validate review-stage-report ${REVIEW_ROOT}/STAGE-math{round_suffix}.json with stage_id=math and stage_kind=math"]
  failure_route: retry_stage_once_then_stop

peer_review_proof_redteam:
  role: gpd-check-proof
  return_profile: proof_redteam
  expected_artifacts: ["${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md"]
  validators: ["gpd validate proof-redteam ${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md", "required frontmatter, sections, same-round theorem binding, and reviewer=gpd-check-proof"]
  failure_route: retry_proof_redteam_once_then_stop; favorable_decisions_require_same_round_status_passed

peer_review_stage4_physics:
  role: gpd-review-physics
  expected_artifacts: ["${REVIEW_ROOT}/STAGE-physics{round_suffix}.json"]
  validators: ["gpd validate review-stage-report ${REVIEW_ROOT}/STAGE-physics{round_suffix}.json with stage_id=physics and stage_kind=physics"]
  failure_route: retry_stage_once_then_stop

peer_review_stage5_significance:
  role: gpd-review-significance
  expected_artifacts: ["${REVIEW_ROOT}/STAGE-interestingness{round_suffix}.json"]
  validators: ["gpd validate review-stage-report ${REVIEW_ROOT}/STAGE-interestingness{round_suffix}.json with stage_id=interestingness and stage_kind=interestingness"]
  failure_route: retry_stage_once_then_stop
```
</child_return_contract>

<stage_1_claim_extraction>
Stage 1 reads the whole manuscript once and writes:

- `${REVIEW_ROOT}/CLAIMS{round_suffix}.json`
- `${REVIEW_ROOT}/STAGE-reader{round_suffix}.json`

Spawn `gpd-review-reader` with the selected manuscript path, manuscript hash,
target journal when known, round number, round suffix, `PUBLICATION_ROOT`, and
`REVIEW_ROOT`. The reader must preserve exact `manuscript_path`,
`manuscript_sha256`, claim ids, theorem-like claim kind, theorem assumptions, and
theorem parameters.

Validate before proceeding:

```bash
gpd validate review-claim-index ${REVIEW_ROOT}/CLAIMS{round_suffix}.json
gpd validate review-stage-report ${REVIEW_ROOT}/STAGE-reader{round_suffix}.json
```

If Stage 1 fails, apply the publication stage-recovery gate and retry once from
the same persisted inputs with a `StageReviewReport` / `ClaimIndex` schema
reminder. If validation still fails, STOP; do not proceed to Stages 2-6.
</stage_1_claim_extraction>

<stage_2_3_and_proof_redteam>
Stage 2 literature reads the manuscript, claims, reader stage, bibliography audit,
bib files, comparisons, figure tracker, and targeted web search when
novelty/positioning is uncertain. It writes
`${REVIEW_ROOT}/STAGE-literature{round_suffix}.json`.

Stage 3 math reads the manuscript, claims, reader stage, summaries, verification,
artifact manifest, reproducibility manifest, and proof artifact when present. It
writes `${REVIEW_ROOT}/STAGE-math{round_suffix}.json`.
Stage 3 math artifact must contain exactly one `proof_audits[]` entry for each
reviewed theorem-bearing claim.
every `proof_audits[].claim_id` must also appear in `claims_reviewed`.

If theorem-bearing claims are present, `gpd-check-proof` may be running in parallel
and will produce `${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md`; do not wait on that
artifact to begin the math review, and do not duplicate the proof audit yourself.

The stage manifest loads the proof-redteam workflow gate, protocol, and schema
authorities. Use those loaded authorities for same-round theorem binding,
frontmatter requirements, status handling, and artifact validation.

Conditional proof-critique prompt when theorem-bearing claims are present:

```text
First, read {GPD_AGENTS_DIR}/gpd-check-proof.md for your role and instructions.
Then read {GPD_INSTALL_DIR}/templates/proof-redteam-schema.md and {GPD_INSTALL_DIR}/references/verification/core/proof-redteam-protocol.md before writing any proof audit artifact.

Operate in adversarial proof-critique mode with a fresh context.
Follow the proof-redteam protocol's one-shot return semantics.
Write to: `${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md`
```

The proof-redteam artifact must bind to:

- `manuscript_path`: copy exactly from `${REVIEW_ROOT}/CLAIMS{round_suffix}.json`
- `manuscript_sha256`: copy exactly from `${REVIEW_ROOT}/CLAIMS{round_suffix}.json`
- `round`: the active review round
- `claim_ids`: copy exactly the theorem-bearing Stage 1 `claim_id` values under review
- `proof_artifact_paths`: copy exactly the theorem-bearing proof artifact paths under review, plus the manuscript entrypoint if it is not already listed

The `gpd-check-proof` task must carry the active `manuscript_path`,
`manuscript_sha256`, `round`, theorem-bearing `claim_ids`, and
`proof_artifact_paths` copied from `${REVIEW_ROOT}/CLAIMS{round_suffix}.json`.
Require theorem-binding frontmatter (`claim_ids` and non-empty
`proof_artifact_paths`) before accepting the proof-redteam artifact.

Use the proof-redteam references for adversarial proof critique. Locally require
full theorem/proof inventory coverage; narrower special-case proofs report
`status: gaps_found`.

If the runtime supports parallel subagent execution, run Stage 2, Stage 3, and the
conditional proof-critique pass in parallel when theorem-bearing claims are present.
Otherwise run Stage 2 first, then Stage 3, then the conditional proof-critique pass.
Treat Stage 2, Stage 3, and the conditional proof-critique pass as one barriered
review wave under the publication stage-recovery gate.

Validate after the wave:

```bash
gpd validate review-stage-report ${REVIEW_ROOT}/STAGE-literature{round_suffix}.json
gpd validate review-stage-report ${REVIEW_ROOT}/STAGE-math{round_suffix}.json
```

If proof-bearing review is active, also require
`${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md` with reviewer `gpd-check-proof`,
same-round theorem binding, non-empty `claim_ids`, non-empty
`proof_artifact_paths`, and the canonical proof-redteam sections. Missing,
malformed, wrong-round, wrong-root, `status: gaps_found`, or
`status: human_needed` artifacts block favorable recommendation; retry
`gpd-check-proof` once, then STOP if still invalid.
If the proof-redteam artifact is missing, malformed, or stale, retry `gpd-check-proof` once with the same inputs.
If the retry also fails, STOP the pipeline and report that proof review could not be completed.

Before Stage 4 can spawn, the branch barrier must pass: every launched child has a
typed return, every persisted artifact above exists and validates, and downstream work
restarts only from those artifacts plus the declared carry-forward inputs.
If literature, math, or the conditional proof-critique stage fails, STOP before
Stage 4; retry only the failed tuple once under the stage-recovery gate.
</stage_2_3_and_proof_redteam>

<stage_4_physics>
Stage 4 checks physical soundness after the mathematical pass. It reads the manuscript,
reader, math, literature, proof-redteam artifact if active, summaries, verifications,
comparisons, and figure tracker. It writes
`${REVIEW_ROOT}/STAGE-physics{round_suffix}.json`.

Validate before proceeding:

```bash
gpd validate review-stage-report ${REVIEW_ROOT}/STAGE-physics{round_suffix}.json
```

Apply the publication stage-recovery gate. Retry Stage 4 once from the same
persisted inputs; if validation still fails, STOP and do not proceed to Stage 5.
After `${REVIEW_ROOT}/STAGE-physics{round_suffix}.json` validates, Stage 5 starts
from persisted stage artifacts and declared carry-forward inputs only.
</stage_4_physics>

<stage_5_significance>
Stage 5 judges interestingness and venue fit after the technical stages. It reads the
manuscript, reader, literature, physics, proof-redteam artifact if active, and target
journal. It writes `${REVIEW_ROOT}/STAGE-interestingness{round_suffix}.json`.

Validate before Stage 6:

```bash
gpd validate review-stage-report ${REVIEW_ROOT}/STAGE-interestingness{round_suffix}.json
```

After `${REVIEW_ROOT}/STAGE-interestingness{round_suffix}.json` validates, Stage 6
must begin from the persisted stage artifacts and declared carry-forward inputs only.
</stage_5_significance>

<handoff>
Reload before final adjudication:

```bash
FINAL_ADJUDICATION_INIT=$(gpd --raw init peer-review "$REVIEW_TARGET" --stage final_adjudication)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd peer-review final-adjudication init failed: $FINAL_ADJUDICATION_INIT"
  # STOP; surface the error.
fi
```
</handoff>
