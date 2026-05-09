<purpose>
Own the phase-research handoff, child artifact gate, typed return routing, and continuation handoff for `gpd:research-phase` after phase bootstrap has validated the selected phase.
</purpose>

<stage_boundary>
This authority starts only after `phase_bootstrap` has validated the phase, handled existing research, gathered phase context, and loaded the `research_handoff` staged payload. Do not read `workflows/research-phase.md`; it is only a staged-file index.
</stage_boundary>

<stage_prerequisites>
If this authority is entered fresh, define the staged reload helper before loading `research_handoff`:

```bash
load_research_phase_stage() {
  local stage_name="$1"
  local phase_arg="$2"
  local init_payload=""

  init_payload=$(gpd --raw init research-phase "${phase_arg}" --stage "${stage_name}" 2>/dev/null)
  if [ $? -ne 0 ] || [ -z "$init_payload" ]; then
    echo "ERROR: staged gpd initialization failed for stage '${stage_name}': ${init_payload}"
    return 1
  fi

  printf '%s' "$init_payload"
  return 0
}
```
</stage_prerequisites>

<process>
## Step 4: Spawn Researcher

Load the heavier handoff slice only after phase validation, existing-research routing, and context gathering are complete:

Apply `references/orchestration/continuation-boundary.md`; local checkpoint trigger=researcher needs user input.

```bash
HANDOFF_INIT=$(load_research_phase_stage research_handoff "${phase_number}")
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $HANDOFF_INIT"
  exit 1
fi
```

Use the staged refresh for `contract_intake`, `effective_reference_intake`, `active_reference_context`, `reference_artifact_files`, `reference_artifacts_content`, `selected_protocol_bundle_ids`, `protocol_bundle_load_manifest`, `protocol_bundle_context`, `protocol_bundle_verifier_extensions`, `state_content`, `config_content`, and `roadmap_content` before assembling the child handoff.

@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md

```
task(
  prompt="First, read {GPD_AGENTS_DIR}/gpd-phase-researcher.md for your role and instructions.

<objective>
Research mathematical methods, physical principles, and computational approaches for Phase {phase}: {name}
</objective>

Research depth: use the active workflow research_mode from init/config ({RESEARCH_MODE}).

<context>
Phase description: {description}
Requirements: {requirements}
Prior decisions: {decisions}
Phase context: {context_md}
</context>

<protocol_bundle_handoff>
<selected_protocol_bundle_ids>{selected_protocol_bundle_ids}</selected_protocol_bundle_ids>
<protocol_bundle_load_manifest>{protocol_bundle_load_manifest}</protocol_bundle_load_manifest>
<protocol_bundle_context>{protocol_bundle_context}</protocol_bundle_context>
<protocol_bundle_verifier_extensions>{protocol_bundle_verifier_extensions}</protocol_bundle_verifier_extensions>
</protocol_bundle_handoff>

When `selected_protocol_bundle_ids` is non-empty, use the bundle context, load manifest, anchor prompts, reference prompts, assets, decisive-artifact guidance, and verifier extensions as the primary specialized research surface. Use the broad physics research directives below only for uncovered areas or when no bundle is selected.

<physics_research_directives>
Cover only what is needed for this phase:
- mathematical framework: governing equations, symmetries, function spaces, boundary/initial data
- standard results: exact solutions, approximations, validity regimes, key references
- limiting cases: classical/non-relativistic/thermodynamic, weak/strong coupling, asymptotics
- computational methods: algorithms, packages, convergence/error scaling, performance constraints
- dimensional scales: physical scales, dimensionless parameters, regime placement
- pitfalls: instabilities, gauge/regularization/renormalization, notation conflicts, known errors
</physics_research_directives>

<output>
Write to: {phase_dir}/{phase_number}-RESEARCH.md
</output>",
  subagent_type="gpd-phase-researcher",
  model="{researcher_model}",
  readonly=false
)
```

Add this contract inside the spawned prompt when adapting it:

```markdown
<spawn_contract>
write_scope:
  mode: scoped_write
  allowed_paths:
    - "{phase_dir}/{phase_number}-RESEARCH.md"
expected_artifacts:
  - "{phase_dir}/{phase_number}-RESEARCH.md"
shared_state_policy: return_only
</spawn_contract>
```

Child artifact gate: apply `references/orchestration/child-artifact-gate.md`; tuple: role=`gpd-phase-researcher`; expected=`{phase_dir}/{phase_number}-RESEARCH.md`; allowed_root=`{phase_dir}`; validators=readable research artifact; applicator=none; failure=`retry research | skip to plan-phase | abort/discuss`.

## Step 5: Handle Return

**If the researcher agent fails to spawn or returns an error:** Report the failure. End with `## > Next Up`: primary `gpd:research-phase {phase_number}` to retry, plus `gpd:plan-phase {phase_number}` to skip research and plan directly, and `gpd:suggest-next`. Do not silently continue without research output.

- **Artifact gate:** Accept completed only after the gate tuple passes for `RESEARCH.md`. If the artifact is missing, unreadable, or absent from `gpd_return.files_written`, end with `## > Next Up`: primary `gpd:research-phase {phase_number}` to retry, plus `gpd:plan-phase {phase_number}` and `gpd:suggest-next`.
- `gpd_return.status: completed` -- Display summary and end with `## > Next Up`: primary `gpd:plan-phase {phase_number}`, plus `gpd:research-phase {phase_number}` to dig deeper, `gpd:show-phase {phase_number}` to review, and `gpd:suggest-next`.
- `gpd_return.status: checkpoint` -- Present the checkpoint and continue only through a fresh continuation handoff under `references/orchestration/continuation-boundary.md`. End with `## > Next Up`: primary `gpd:resume-work`, plus `gpd:research-phase {phase_number}` and `gpd:suggest-next`.
- `gpd_return.status: blocked` or `failed` -- Show attempts and end with `## > Next Up`: primary `gpd:discuss-phase {phase_number}` to add context, plus `gpd:research-phase {phase_number}` and `gpd:suggest-next`.

## Step 6: Spawn Continuation Researcher

```markdown
<objective>
Continue research as a fresh continuation handoff for Phase {phase_number}: {phase_name}
</objective>

<prior_state>
Research file path: {phase_dir}/{phase_number}-RESEARCH.md
Read that file before continuing so you inherit the prior research state instead of relying on inline prompt state.
</prior_state>

<checkpoint_response>
**Type:** {checkpoint_type}
**Response:** {user_response}
</checkpoint_response>

<protocol_bundle_handoff>
<selected_protocol_bundle_ids>{selected_protocol_bundle_ids}</selected_protocol_bundle_ids>
<protocol_bundle_load_manifest>{protocol_bundle_load_manifest}</protocol_bundle_load_manifest>
<protocol_bundle_context>{protocol_bundle_context}</protocol_bundle_context>
<protocol_bundle_verifier_extensions>{protocol_bundle_verifier_extensions}</protocol_bundle_verifier_extensions>
</protocol_bundle_handoff>

<spawn_contract>
write_scope:
  mode: scoped_write
  allowed_paths:
    - "{phase_dir}/{phase_number}-RESEARCH.md"
expected_artifacts:
  - "{phase_dir}/{phase_number}-RESEARCH.md"
shared_state_policy: return_only
</spawn_contract>
```

```bash
task(
  prompt="First, read {GPD_AGENTS_DIR}/gpd-phase-researcher.md for your role and instructions.\n\n" + continuation_prompt,
  subagent_type="gpd-phase-researcher",
  model="{researcher_model}",
  readonly=false,
  description="Continue research Phase {phase}"
)
```

</process>

<success_criteria>
- [ ] Phase argument validated and phase info loaded
- [ ] Existing research checked (update/skip offered if present)
- [ ] Phase context gathered (roadmap section, requirements, prior decisions)
- [ ] gpd-phase-researcher spawned with physics research directives
- [ ] RESEARCH.md written to phase directory and named in `gpd_return.files_written`
- [ ] Research return handled via typed `gpd_return.status` and artifact gating
- [ ] Research covers: mathematical framework, known solutions, limiting cases, computational methods, dimensional analysis, potential pitfalls
- [ ] Return handled (complete/checkpoint/inconclusive)
- [ ] Next action offered (plan phase, dig deeper, review)
</success_criteria>
