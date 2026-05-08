<purpose>
Own Stage 6 final adjudication, referee report writing, review-ledger and
referee-decision validation, and upstream read-only enforcement.
</purpose>

<stage_boundary>
Stage 6 reads all prior stage artifacts and spot-checks the manuscript. It may write
only Stage 6-owned adjudication artifacts for this round. It must never modify or list
upstream staged-review artifacts in `gpd_return.files_written`.

@{GPD_INSTALL_DIR}/references/publication/publication-final-adjudication-boundary.md
@{GPD_INSTALL_DIR}/references/publication/stage-recovery-gate.md
@{GPD_INSTALL_DIR}/templates/paper/review-ledger-schema.md
@{GPD_INSTALL_DIR}/templates/paper/referee-decision-schema.md
</stage_boundary>

<final_adjudication>
Load the staged final-adjudication payload before spawning `gpd-referee`:

```bash
FINAL_ADJUDICATION_INIT=$(gpd --raw init peer-review "$REVIEW_TARGET" --stage final_adjudication)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd peer-review final-adjudication init failed: $FINAL_ADJUDICATION_INIT"
  # STOP; surface the error.
fi
```

Spawn `gpd-referee` as the final adjudicating referee for the staged peer-review
panel. It must read:

- selected manuscript path and manuscript hash
- `${REVIEW_ROOT}/CLAIMS{round_suffix}.json`
- `${REVIEW_ROOT}/STAGE-reader{round_suffix}.json`
- `${REVIEW_ROOT}/STAGE-literature{round_suffix}.json`
- `${REVIEW_ROOT}/STAGE-math{round_suffix}.json`
- `${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md` if proof-bearing review is active
- `${REVIEW_ROOT}/STAGE-physics{round_suffix}.json`
- `${REVIEW_ROOT}/STAGE-interestingness{round_suffix}.json`
- target-aware `latest_referee_report_md` and `latest_author_response` when present for revision rounds

Stage 6 writes:

- `${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.md`
- `${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.tex`
- `${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json`
- `${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json`
- `${PUBLICATION_ROOT}/CONSISTENCY-REPORT.md` when supported as a diagnostic sidecar

Stage 6 child gate:

```yaml
child_gate:
  id: "peer_review_stage6_referee"
  role: "gpd-referee"
  required_status: "completed"
  expected_artifacts:
    - "${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.md"
    - "${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.tex"
    - "${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json"
    - "${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json"
    - "${PUBLICATION_ROOT}/CONSISTENCY-REPORT.md when produced"
  validators:
    - "gpd validate review-ledger ${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json"
    - "gpd validate referee-decision ${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json --strict --ledger ${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json"
  failure_route: "stage-recovery-gate -> retry Stage 6-owned artifacts | fail back upstream"
```

Return through the `peer_review_stage6_referee` child_gate tuple. Do not trust the referee's success text until that typed return, the on-disk files, and the validators all agree.
</final_adjudication>

<adjudication_rules>
If any required staged-review artifact is missing, malformed, or uses the wrong
round suffix, STOP before final recommendation and hand the failure back to the
earliest failing upstream stage.

For proof-bearing claims, a missing, malformed, wrong-round, wrong-root, or non-passing same-round `${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md` artifact prevents any favorable recommendation. Recommendation floor: `major_revision` or `reject`.

Stage-review validation alone is not proof-redteam clearance: aligned `proof_audits[]` entries in `${REVIEW_ROOT}/STAGE-math{round_suffix}.json` are necessary review evidence, but they do not by themselves clear a favorable final decision without the same-round proof-redteam artifact and strict final-decision validation.

Write `${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json` and
`${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json`. Keep `manuscript_path` non-empty
and identical across ledger, decision, and staged-review artifacts for this round.
In `REFEREE-DECISION{round_suffix}.json`, set every strict policy field explicitly.
Its `stage_artifacts` list may contain only the five canonical `STAGE-reader`,
`STAGE-literature`, `STAGE-math`, `STAGE-physics`, and `STAGE-interestingness` JSON
files for this round. `CLAIMS{round_suffix}.json` is the separately validated claim
index, not a `stage_artifacts` entry.

Your writable scope is limited to Stage 6-owned adjudication artifacts for this round:
`${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.md`,
`${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.tex`,
`${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json`,
`${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json`, and
`${PUBLICATION_ROOT}/CONSISTENCY-REPORT.md` when applicable.

Do not modify `${REVIEW_ROOT}/CLAIMS{round_suffix}.json`, any `${REVIEW_ROOT}/STAGE-*.json`, or `${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md`.
If any of those upstream artifacts are missing, malformed, stale, or inconsistent,
return `gpd_return.status: blocked` and hand the failure back to the earliest failing
upstream stage instead of repairing it inside Stage 6.

gpd_return.files_written stays within Stage 6 write_allowlist; any upstream path is a failed handoff.
The Stage 6 tuple write allowlist is report `.md`/`.tex`, ledger, decision, and optional consistency report.
</adjudication_rules>

<stage_recovery_6>
Check that both `${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json` and
`${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json` exist and parse as valid JSON.
Treat the referee report files as required final-stage artifacts.
Also confirm `${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.md` and
`${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.tex` exist before treating the final
recommendation as complete.

Run the built-in validators:

```bash
gpd validate review-ledger ${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json
gpd validate referee-decision ${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json --strict --ledger ${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json
```

For proof-bearing reviews, this strict final-decision validator is the favorable-decision guardrail before trusting any final recommendation. Do not treat a passing
`gpd validate review-stage-report ${REVIEW_ROOT}/STAGE-math{round_suffix}.json`
result, even with aligned `proof_audits[]`, as a substitute for same-round
`${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md` clearance plus strict
referee-decision validation.

Apply the `peer_review_stage6_referee` tuple and publication stage-recovery gate
before classifying the outcome as recovery-eligible, upstream-blocked, or
complete. Classify the failure first. Only retry Stage 6 for Stage 6-owned artifact failures.
Do not retry Stage 6 as an upstream repair step. If errors point at
`CLAIMS{round_suffix}.json`, `STAGE-*.json`, or `PROOF-REDTEAM{round_suffix}.md`,
STOP fail-closed and rerun the earliest failing upstream stage.
If the eligible Stage 6 retry also fails, do not proceed to report summarization.

Upstream fail-back table:

- `CLAIMS{round_suffix}.json` or `STAGE-reader{round_suffix}.json` -> rerun Stage 1
- `STAGE-literature{round_suffix}.json` -> rerun Stage 2
- `STAGE-math{round_suffix}.json` or `PROOF-REDTEAM{round_suffix}.md` -> rerun Stage 3 and the proof-critique pass when applicable
- `STAGE-physics{round_suffix}.json` -> rerun Stage 4
- `STAGE-interestingness{round_suffix}.json` -> rerun Stage 5

Treat blank `manuscript_path` values in either `${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json`
or `${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json` as validation failures, not
as optional bookkeeping.
</stage_recovery_6>

<handoff>
When Stage 6 validates, reload before final summary and routing:

```bash
FINALIZE_INIT=$(gpd --raw init peer-review "$REVIEW_TARGET" --stage finalize)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd peer-review finalize init failed: $FINALIZE_INIT"
  # STOP; surface the error.
fi
```
</handoff>
