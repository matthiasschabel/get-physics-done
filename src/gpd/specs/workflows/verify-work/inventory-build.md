<purpose>
Orchestrate conversational verification through a thin session wrapper around `gpd-verifier`.

The verifier owns target construction, proof policy, checks, comparison verdicts, and canonical status. Scientific status ownership and routing vocabulary live in `{GPD_INSTALL_DIR}/references/verification/verification-status-authority.md`. This workflow owns preflight, routing, interaction, sync, diagnosis, and gap repair.
</purpose>
<philosophy>
**Do not duplicate verifier policy here.**

- Fail closed before delegation if the project, roadmap, contract, or proof readiness are not usable.
- Use `{GPD_INSTALL_DIR}/references/verification/verification-status-authority.md` for status ownership and vocabulary; this wrapper gates artifacts and routes, but does not decide the scientific verdict.
- Present verifier-produced evidence one check at a time and record only the session overlay in this workflow.
- Every spawned agent is a one-shot delegation: if it needs user input or new evidence arrives after return, start a fresh continuation; never send more input to closed child.
- File-producing handoffs must prove the expected artifact exists before success is accepted.
</philosophy>
<shared_contract_floor>
**Project Contract Gate:** {project_contract_gate}
**Project Contract Load Info:** {project_contract_load_info}
**Project Contract Validation:** {project_contract_validation}
**Contract Intake:** {contract_intake}
**Effective Reference Intake:** {effective_reference_intake}

Treat `project_contract` as authoritative only when `project_contract_gate.authoritative` is true. A visible-but-blocked contract must be repaired before it is used as authoritative verification scope; keep the same contract-critical floor at all times.
Treat `effective_reference_intake` as the structured source of carry-forward anchors; `active_reference_context` is the readable projection, not the source of truth.
Do NOT skip contract-critical anchors.
</shared_contract_floor>
@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md

<process>

<step name="load_anchor_context">
Load inventory-building before using anchor, protocol-bundle, state, or verifier-handoff fields:

```bash
INVENTORY_BUILD_INIT=$(gpd --raw init verify-work "${PHASE_ARG}" --stage inventory_build)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd inventory-build initialization failed: $INVENTORY_BUILD_INIT"
  # STOP; surface the error.
fi
```

Treat `inventory_build.required_init_fields` as source of truth for contract, reference, and protocol-bundle fields.

Use `active_reference_context` from init JSON as a mandatory input to verification.
Treat `effective_reference_intake` as the structured source of carry-forward anchors; `active_reference_context` is the readable projection, not the source of truth.

- If it names a benchmark, prior artifact, or must-read reference, verification must explicitly check it or report why it could not.
- Treat `reference_artifacts_content` as supporting evidence for what comparisons remain decisive. Stable knowledge docs that appear there are reviewed background synthesis: use them to clarify definitions, assumptions, and caveats only when they agree with stronger sources, and never as decisive evidence on their own.
- Background literature may be reduced by mode; anchor checks may not.
</step>

<step name="load_protocol_bundle_context">
Use `protocol_bundle_load_manifest` and `protocol_bundle_context` from init JSON as additive specialized guidance. If `selected_protocol_bundle_ids` is non-empty, use `protocol_bundle_verifier_extensions` from init JSON as the primary source for bundle checklist extensions; call `get_bundle_checklist(selected_protocol_bundle_ids)` only when extensions are missing or need consistency checking. Bundle guidance may add estimator checks, decisive artifact expectations, or domain-specific audits, but it does NOT replace the plan contract or reduce anchor obligations.
- If the phase has a PLAN `contract` and project-local anchors or prior-output paths matter, use this contract-check loop before finalizing the inventory:
  1. Call `suggest_contract_checks(contract, project_dir=...)`.
  2. Treat the returned items as the default contract-aware seed unless they are clearly inapplicable.
  3. For each returned check, start from `request_template`, satisfy `required_request_fields` and `schema_required_request_fields`, satisfy one full alternative from `schema_required_request_anyof_fields`, stay within `supported_binding_fields` for `request.binding`, and keep `project_dir` as the top-level absolute project root argument.
  4. Call `run_contract_check(request=..., project_dir=...)` so contract-aware checks are executed rather than only discovered.
</step>

<step name="delegate_verification">
## Delegate Verification

Spawn `gpd-verifier` once and let it own the physics policy. Use `subagent_type="gpd-verifier"`, model `{verifier_model}`, and scoped write. It owns contract-backed target extraction, evidence mapping, proof policy, computational checks, decisive comparisons, canonical status, suggested contract checks, and the gap ledger.

Pass the project contract, proof freshness summary, active reference context, and protocol bundle handoff fields into the handoff so the verifier can build its own authoritative ledger.
Point the verifier at `{GPD_INSTALL_DIR}/references/verification/verification-status-authority.md` for scientific status ownership, target status vocabulary, top-level verification status, and runtime return-status distinction.
Use `protocol_bundle_verifier_extensions` as primary bundle checklist surface; `protocol_bundle_context` is readable projection. Use `suggest_contract_checks(contract)` for ambiguous decisive anchors or prior-output paths. Required decisive comparisons should stay legible enough that the researcher can recognize in the phase promise which `claim`, acceptance test, or reference is still unresolved. Do not mark the parent claim or acceptance test as passed until that decisive comparison is resolved.
Verifier presentation headings are non-authority; route through the verifier tuple plus `verification-status-authority.md`.

> Verifier checkpoints use `references/orchestration/continuation-boundary.md`; the wrapper starts a fresh continuation after the user responds.

Use `verification_report_finalizer_bridge` as the canonical report finalizer bridge for passed, `human_needed`, `expert_needed`, and typed non-gap outcomes. Gap-only conservative reports may use `verification_report_skeleton_bridge`; stronger statuses must run `gpd verification-report finalize` with a typed patch JSON plus body-only evidence and pass `gpd validate verification-contract` before the wrapper routes on the report.

Set `VERIFIER_HANDOFF_STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")` immediately before spawning.

Prompt: "First, read {GPD_AGENTS_DIR}/gpd-verifier.md for your role and instructions." Then verify Phase {phase_number}; use `Verification flags from the normalized parser: $VERIFY_FLAG_TEXT`; treat `--dimensional`, `--limits`, `--convergence`, and `--regression` as optional-breadth narrowing only.

Read with `file_read`: `${PHASE_DIR_ABS}/${phase_number}-VERIFICATION.md`, all PLAN/SUMMARY/`*-PROOF-REDTEAM.md` files in `${PHASE_DIR_ABS}/`, `${PROJECT_ROOT}/GPD/STATE.md`, and `${PROJECT_ROOT}/GPD/ROADMAP.md`.

Pass this context: Project contract: {project_contract}; Project contract gate: {project_contract_gate}; Project contract load info: {project_contract_load_info}; Project contract validation: {project_contract_validation}; Contract intake: {contract_intake}; Effective reference intake: {effective_reference_intake}; Active reference context: {active_reference_context}; Proof freshness summary: {phase_proof_review_status}.

<selected_protocol_bundle_ids>
{selected_protocol_bundle_ids}
</selected_protocol_bundle_ids>

<protocol_bundle_load_manifest>
{protocol_bundle_load_manifest}
</protocol_bundle_load_manifest>

<protocol_bundle_context>
{protocol_bundle_context}
</protocol_bundle_context>

<protocol_bundle_verifier_extensions>
{protocol_bundle_verifier_extensions}
</protocol_bundle_verifier_extensions>

Treat `project_contract` as authoritative only when `project_contract_gate.authoritative` is true. Use `protocol_bundle_verifier_extensions` as primary bundle-extension surface. Keep decisive comparison gaps legible at the claim / acceptance-test / reference level. If user input is required, return `gpd_return.status: checkpoint` and stop.
Schema finalization is bounded: validator pass returns; after the second validator failure total, including the initial failure and one repair rerun, return `gpd_return.status: blocked` with latest errors. Stop after two schema-only repair failures.

<spawn_contract>
write_scope:
  mode: scoped_write
  allowed_paths:
    - ${PHASE_DIR_ABS}/${phase_number}-VERIFICATION.md
expected_artifacts:
  - ${PHASE_DIR_ABS}/${phase_number}-VERIFICATION.md
shared_state_policy: return_only
</spawn_contract>

Verifier child artifact gate: apply `references/orchestration/child-artifact-gate.md`; scientific status routing applies `references/verification/verification-status-authority.md`; checkpoint handling applies `references/orchestration/continuation-boundary.md`.

```yaml
child_gate:
  id: "verify_work_verifier_report"
  role: "gpd-verifier"
  return_profile: "verifier"
  required_status: "completed"
  expected_artifacts:
    - "${PHASE_DIR_ABS}/${phase_number}-VERIFICATION.md"
  allowed_roots:
    - "${PHASE_DIR_ABS}"
  freshness_marker: "after $VERIFIER_HANDOFF_STARTED_AT"
  validators:
    - "gpd validate handoff-artifacts - --expected '${PHASE_DIR_ABS}/${phase_number}-VERIFICATION.md' --allowed-root '${PHASE_DIR_ABS}' --required-suffix=-VERIFICATION.md --require-status completed --require-files-written --fresh-after \"$VERIFIER_HANDOFF_STARTED_AT\""
    - "gpd validate verification-contract ${PHASE_DIR_ABS}/${phase_number}-VERIFICATION.md"
    - "verification-status-authority.md status rules"
    - "required proof-redteam artifacts report status: passed"
  applicator:
    command: "sync_verifier_output only after tuple passes"
    require_passed_true: false
  failure_route: "fail_closed -> gpd:verify-work ${phase_number} | repair_prompt_once | fresh_verifier_continuation_or_non_green_stop | non_green_stop_with_validator_errors"
```

If runtime delegation is unavailable, fallback verifier execution is still `gpd-verifier` execution. Before writing contract-backed `${PHASE_DIR_ABS}/${phase_number}-VERIFICATION.md`: read `verification_report_skeleton_bridge` and `verification_report_finalizer_bridge`; write body-only evidence to a Markdown file that satisfies bridge `body_contract` (body-only Markdown with one fenced executed `python`/`bash` block, adjacent `**Output:**` plus fenced `output`, and a following `PASS`/`FAIL`/`INCONCLUSIVE` verdict). For conservative gap reports, replace `BODY.md` in the skeleton bridge `writer_command` with that file and run it. For passed, `human_needed`, `expert_needed`, or typed non-gap outcomes, write the finalizer bridge patch JSON, replace `PATCH.json` and `BODY.md` in its `writer_command_template`, and run `gpd verification-report finalize`. The helper serializes YAML and validates before canonical acceptance. Use `skeleton_command` only as read-only preview context; do not hand-author or reflow frontmatter, and keep command transcripts, hashes, oracle details, prose-only evidence, and `gpd_return` out of YAML. Read the runtime-projected `{GPD_AGENTS_DIR}/gpd-verifier.md` and helper/schema authority references for verifier policy, not for wrapper-side schema recreation. Then apply `sync_verifier_output`; on validation failure, emit the blocked/final response and stop. Do not wrapper-repair the canonical report.
</step>

<step name="sync_verifier_output">
Read the verifier-produced verification file or report path.

Apply the `verify_work_verifier_report` child_gate before downstream routing. Route only on canonical verification frontmatter plus `gpd_return.status`; headings, marker strings, runtime success, and preexisting reports are not authority.
- Any verifier-written canonical `VERIFICATION.md`, including gap reports and `blocked`/`failed` handoffs, must pass `gpd validate verification-contract "${PHASE_DIR_ABS}/${phase_number}-VERIFICATION.md"` before this wrapper accepts it as canonical.
- Missing/unreadable/unnamed/invalid artifacts use the tuple failure route; never present them as accepted or passed.
- Fallback executions that reach this step after failed report validation stop here: emit the blocked/final response with latest validator errors. Do not list the invalid `VERIFICATION.md` as an authoritative artifact, do not route to gaps unless a schema-valid gap report exists, do not enter `gap_repair` or `complete_session`, and do not patch the canonical verification report from this wrapper.
- Do not patch canonical verification frontmatter in this wrapper. Surface bounded-loop validator errors fail-closed with `## > Next Up`: `gpd:verify-work ${phase_number}`, `gpd:resume-work`, `gpd:suggest-next`.
- If a canonical verification file already exists, preserve its authoritative frontmatter and append only the session-local overlay here.
- Do not recompute canonical verification status in this workflow.

Load the staged researcher-session scaffold and canonical schema pack at this stage.

```bash
INTERACTIVE_VALIDATION_INIT=$(gpd --raw init verify-work "${PHASE_ARG}" --stage interactive_validation)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd interactive-validation initialization failed: $INTERACTIVE_VALIDATION_INIT"
  # STOP; surface the error.
fi
```

Use `interactive_validation.required_init_fields` before writing the session overlay.
Keep the session overlay frontmatter compatible with the authoritative verification report.
Write to `${PHASE_DIR_ABS}/${phase_number}-VERIFICATION.md`.
Changed verification files fail `gpd pre-commit-check` when this header is missing or mismatched against the active lock.
</step>

</process>
