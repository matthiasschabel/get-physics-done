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
<stage_scope>
Stage id: `interactive_validation`. Owns researcher-facing check presentation, response capture, diagnosis, and the explicit transition into gap repair. Do not load planner/checker gap-repair authority until the user chooses auto-plan fixes.
</stage_scope>
@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md

<process>

<step name="present_check">
**Present current check to the researcher with verifier evidence:**

Read the verifier-supplied current check from the verification file or report state.

Display compactly:

```
### Research Validation Check {number}: {name}

{expected}

**Independent computation:** {computation description and result}

Confirm this matches your result, or describe what differs.
```

The wrapper should present verifier-produced evidence exactly once per check. It should not derive a new physics criterion here.

Keep body-only session-overlay fields aligned with the staged researcher-session scaffold. Use `forbidden_proxy_id` for explicit proxy-rejection checks instead of inventing extra body subject kinds.

Wait for researcher response (plain text).
</step>

<step name="process_response">
**Process researcher response and update the session overlay**

- Empty response, `yes`, `y`, `ok`, `pass`, `next`, `confirmed`, `correct` -> pass
- `skip`, `cannot check`, `n/a`, `not applicable` -> skipped
- Anything else -> issue

Infer severity from the response text:

- `wrong`, `error`, `diverges`, `unphysical`, `violates` -> blocker
- `disagrees`, `inconsistent`, `does not match`, `off by`, `missing` -> major
- `approximate`, `close but`, `small discrepancy`, `minor` -> minor
- `label`, `formatting`, `axis`, `legend`, `cosmetic` -> cosmetic
- default -> major

Update the session overlay only. The canonical verifier verdict remains verifier-owned.
</step>

<step name="resume_from_file">
**Resume validation from file:**

Read the active verification file. Find the first verifier-supplied check with `result: pending`.

Announce:

```
Resuming: Phase {phase_number} Research Validation
Progress: {passed + issues + skipped}/{total}
Issues found so far: {issues count}

Continuing from Check {N}...
```

Update the current check display and continue to `present_check`.
</step>

<step name="researcher_custom_checks">
**After the verifier-supplied checks are complete, invite researcher-supplied checks:**

```
All {N} verifier checks complete ({passed} passed, {issues} issues, {skipped} skipped).

Are there any additional physics checks you'd like to verify?
Examples: "check Ward identity", "verify sum rule", "test at strong coupling"
(Type "done" to skip)
```

If the researcher provides custom checks, spawn a fresh verifier continuation rather than extending the old run. Keep the one-shot delegation rule in force.

If the researcher says `done`, `no`, `skip`, or leaves it empty, proceed to issue routing.
</step>

<step name="diagnose_issues">
**Diagnose root causes before planning fixes**

**Severity gate:** only spawn parallel diagnosis agents for major+ issues. Minor and cosmetic issues are reported directly without investigation overhead.

**Major+ issues**

- Collect the major+ issues into an investigation list.
- Spawn parallel diagnosis agents once per issue.
- Pass the pre-check evidence and researcher response into each agent.
- Each spawned agent is a one-shot handoff and must checkpoint instead of waiting for user interaction.
- Collect root causes and update the verification overlay with the diagnosis result.

**Minor/cosmetic issues**

- Present them directly.
- Do not trigger investigation agents.
</step>

<step name="diagnosis_review">
## Diagnosis Review

Present the diagnosis results to the user and ask how to proceed:

- Auto-plan fixes
- Investigate manually
- Acknowledge limitation; verification status remains non-passed

Acknowledgement is routing only, not verification evidence. It cannot upgrade non-passed verifier/frontmatter/proof/check status to `passed`; preserve verifier-owned status and route to gap planning or follow-up.
</step>

<step name="load_gap_repair_stage">
## Load Gap Repair Stage

When the user chooses auto-plan fixes, reload `verify-work` through the explicit gap-repair stage:

```bash
GAP_REPAIR_INIT=$(gpd --raw init verify-work "${PHASE_ARG}" --stage gap_repair)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd gap-repair initialization failed: $GAP_REPAIR_INIT"
  # STOP; surface the error.
fi
```

Treat the staged payload as the source of truth for planner and checker routing.

If the staged init is blocked, stale, or missing required fields, stop and surface the blocking issues instead of falling back to unstaged plan repair.
</step>

</process>
