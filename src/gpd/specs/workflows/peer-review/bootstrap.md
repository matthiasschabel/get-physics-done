<purpose>
Own the first staged `peer-review` boundary: target-aware intake, manuscript routing,
contract-gate visibility, and handoff to strict review preflight.
</purpose>

<stage_boundary>
This is the only bootstrap authority for `gpd:peer-review`.
Do not read `workflows/peer-review.md` or downstream stage authorities while this
stage is active. Do not load panel prompts, reliability rules, proof-redteam
protocols, review-ledger or referee-decision schemas, final-adjudication rules, or
response-routing details in bootstrap.

Bootstrap is read-only. It resolves which target is being reviewed and which selected
publication/review roots later stages must use.
</stage_boundary>

<bootstrap_init>
Run staged init before any review decision:

```bash
BOOTSTRAP_INIT=$(gpd --raw init peer-review "$ARGUMENTS" --stage bootstrap)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd peer-review bootstrap init failed: $BOOTSTRAP_INIT"
  # STOP; surface the error.
fi
```

Parse only `staged_loading.required_init_fields`; keep `project_contract_gate`,
`project_contract_load_info`, and `project_contract_validation` visible. Use
`gpd --raw stage field-access peer-review --stage bootstrap --style instruction`
only if the runtime needs key guidance.

AUTONOMY=$(echo "$BOOTSTRAP_INIT" | gpd json get .autonomy --default balanced)
RESEARCH_MODE=$(echo "$BOOTSTRAP_INIT" | gpd json get .research_mode --default balanced)
Pass `<autonomy_mode>{AUTONOMY}</autonomy_mode>` and
`<research_mode>{RESEARCH_MODE}</research_mode>` to reviewers.

Keep `project_contract_gate` visible. If `project_contract_gate.authoritative`
is false, use `contract_intake` and `effective_reference_intake` only as
diagnostics/context carry-forward evidence. Do not hydrate full reference or
active-reference bodies in bootstrap.
If contract loading is blocked, repair the blocked contract before retrying.
</bootstrap_init>

<target_routing>
Review target: `$ARGUMENTS` can be empty, a paper directory, a manuscript path, or an
explicit external artifact path.

Explicit external artifact intake points at one artifact path, uses only the
external-artifact intake surface, and must not widen into default `paper/`,
`manuscript/`, or `draft/` discovery rules.

Peer review supports two intake modes:

- `project-backed manuscript review`: strict publication-pipeline review of the
  current GPD project manuscript under `paper/`, `manuscript/`, `draft/`, or a centralized
  `GPD/publication/{subject_slug}/manuscript` lane.
- `standalone explicit-artifact review`: path-driven review of one explicit manuscript artifact or other accepted target. Nearby project/manuscript-root
  artifacts are additive context unless the selected mode makes them authoritative.

If no argument is provided, first ask whether to review an explicit artifact or the
current GPD project's active manuscript when available.

Use centralized target-aware init and the authoritative manuscript resolver to resolve the active manuscript entrypoint from the explicit
argument when provided, otherwise from the manuscript-root `ARTIFACT-MANIFEST.json`,
then `PAPER-CONFIG.json`, then the canonical current manuscript entrypoint rules for
supported roots. Do not use ad hoc wildcard discovery.

If no manuscript or explicit target can be resolved, STOP at `manuscript_required` with `command_execution_state: blocked_before_write`,
`files_written: []`, and `next_step: none`.
</target_routing>

<root_binding>
Use centralized preflight's selected publication/review roots for GPD-authored review
artifacts. Never write managed-subject review artifacts to the global `GPD/review`
fallback.

Keep `publication_subject_slug`, `publication_lane_kind`,
`managed_publication_root`, `selected_publication_root`, and
`selected_review_root` visible for every later review-stage payload.
Set `REVIEW_ROOT` = `selected_review_root`.

If centralized preflight exposes a subject-owned publication root for a managed or
explicit external publication subject, keep the round-artifact family bound there and
do not infer a full publication-tree relocation from that one continuation path.

The default in-project manuscript family is limited to `paper/`, `manuscript`, and
`draft`. A resolved project-managed manuscript lane at
`GPD/publication/{subject_slug}/manuscript` is also a current-project manuscript
subject; staged review outputs go to selected review root
`GPD/publication/{subject_slug}/review`, not beside the manuscript and not under the
default global `GPD/review` path.
</root_binding>

<stage_map>
Before spawning any reviewer, the panel stage gives the user a concise stage map.
Preserve these stage ids:

1. `bootstrap` resolves target mode, root bindings, contract-gate visibility, and
   prior-round snapshot state.
2. `preflight` validates mode-aware prerequisites and manuscript-root readiness.
3. `artifact_discovery` loads manuscript artifacts, target-aware round state, and
   proof-bearing routing state without launching panel agents.
4. `panel_stages` runs claim extraction, specialist review, stage validation, and the
   conditional proof critic.
5. `final_adjudication` runs the Stage 6 referee over persisted upstream artifacts.
6. `finalize` summarizes the completed review and routes the next action.
</stage_map>

<handoff>
When bootstrap target routing is resolved, reload before strict checks:

```bash
PREFLIGHT_INIT=$(gpd --raw init peer-review "$REVIEW_TARGET" --stage preflight)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd peer-review preflight init failed: $PREFLIGHT_INIT"
  # STOP; surface the error.
fi
```

Do not continue from bootstrap memory into preflight. Later stages must start from
their staged init payloads and persisted artifacts.
</handoff>
