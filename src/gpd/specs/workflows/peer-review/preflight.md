<purpose>
Own peer-review prerequisite validation and manuscript-root readiness checks.
</purpose>

<stage_boundary>
Preflight validates that the selected target mode has enough evidence for review.
It does not launch panel agents, classify final recommendations, run proof-redteam
protocols, author referee decisions, or route author-response work.
</stage_boundary>

<load_specialized_review_context>
Read the staged payload from:

```bash
PREFLIGHT_INIT=$(gpd --raw init peer-review "$REVIEW_TARGET" --stage preflight)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd peer-review preflight init failed: $PREFLIGHT_INIT"
  # STOP; surface the error.
fi
```

Parse only fields named by `staged_loading.required_init_fields`. Use the manifest
field names for `review_target_mode`, `resolved_review_target`,
`selected_publication_root`, `selected_review_root`, `manuscript_root`,
`manuscript_entrypoint`, `artifact_manifest_path`, `bibliography_audit_path`,
`reproducibility_manifest_path`, and `publication_blockers`.

Apply the canonical manuscript-root publication preflight:

@{GPD_INSTALL_DIR}/templates/paper/publication-manuscript-root-preflight.md

Use the staged peer-review reliability reference only for preflight integrity checks:

@{GPD_INSTALL_DIR}/references/publication/peer-review-reliability.md
</load_specialized_review_context>

<preflight>
Run command context and strict review preflight before reading or writing review
artifacts:

```bash
CONTEXT=$(gpd --raw validate command-context peer-review "$REVIEW_TARGET")
if [ $? -ne 0 ]; then
  echo "$CONTEXT"
  # STOP; surface the command-context error.
fi

REVIEW_PREFLIGHT=$(gpd validate review-preflight peer-review "$REVIEW_TARGET" --strict)
if [ $? -ne 0 ]; then
  echo "$REVIEW_PREFLIGHT"
  # STOP; surface the strict review-preflight blockers.
fi
```

command-context preflight must run before strict review preflight.

Project-backed manuscript review is strict on project state, roadmap, conventions,
research artifacts, verification reports, artifact manifest, clean bibliography audit,
and reproducibility readiness. Fail closed for missing project state, missing roadmap,
missing conventions, no research artifacts, missing verification reports, missing
`ARTIFACT-MANIFEST.json`, failed or unverified `BIBLIOGRAPHY-AUDIT.json`, or missing
`reproducibility-manifest.json`.
Keep `bibliography_audit_clean` and `reproducibility_ready` visible as strict
review fields.
The manuscript-root bibliography audit must be review-ready, not merely present.

Standalone explicit-artifact review requires one accepted readable target. Treat
project and manuscript-root artifacts as optional supporting context unless the
selected target mode makes them authoritative.

Do not copy manuscript-local artifacts into `GPD/` to satisfy strict review gates.
Do not write a managed-subject review bundle to global `GPD/review`; use
`selected_review_root`.

Bundle guidance from `protocol_bundle_context` is additive only; it
cannot override visible evidence, the resolved manuscript, `project_contract`,
comparison/figure artifacts such as `GPD/comparisons/*-COMPARISON.md`, or
verification evidence. Include `${MANUSCRIPT_ROOT}/FIGURE_TRACKER.md` when
present. Reader-visible claims and surfaced evidence remain first-class review
inputs. review-support artifacts are scaffolding, not substitutes for
authoritative evidence.

Carry forward a compact `REVIEW_CARRY_FORWARD` packet containing the selected
target, roots, claim/evidence context, and blockers instead of reloading broad
bootstrap state before spawning panel stages.
Carry-forward packet: {REVIEW_CARRY_FORWARD}
Do not repeat broad bootstrap prose in panel-stage prompts.
Do not repeat full contract/reference payloads in every child prompt.
</preflight>

<handoff>
When preflight passes, reload before artifact discovery:

```bash
ARTIFACT_DISCOVERY_INIT=$(gpd --raw init peer-review "$REVIEW_TARGET" --stage artifact_discovery)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd peer-review artifact-discovery init failed: $ARTIFACT_DISCOVERY_INIT"
  # STOP; surface the error.
fi
```
</handoff>
