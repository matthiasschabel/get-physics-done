# Phase 7 Live Persona Canary

Manual live is opt-in. It is never started by pull request, push, release, or publish jobs. The operator approves budget, provider account, row set, and local workspace before any provider CLI launch.

Raw artifacts stay ignored/operator-local under repo-local `tmp/`: prompts, stdout/stderr, transcripts, argv/env, auth/account data, home paths, provider replies, command files, and raw diffs. Keep runner workspaces, runtime homes, prompts, transcripts, stdout/stderr, argv/env, and sidecars inside ignored `tmp/` paths.

Public output is a sanitized class-only summary: row ids, runtime/persona/workflow/result/write/next-step classes, aggregate counts, redaction status, and finding classes. It must not include raw text, local paths, hashes, account identifiers, command lines, tokens, provider replies, or transcript excerpts.

Release and publish jobs must not launch provider CLIs. They may consume an already-produced sanitized summary by report id. Nightly is deferred; any later nightly canary must use a dedicated workflow with `workflow_dispatch` and optionally `schedule`, protected credentials, strict budgets, and sanitized summary artifacts only.

## Phase 6 Shadow-Live Scope

Phase 6 shadow-live rows reuse this policy. They may observe a manually approved provider run, but repo code stays provider-free: no pull request, push, release, publish, or test job launches a provider CLI, and this runbook defines no live provider runner. Public review material is class tokens and counts only; raw material stays inside ignored repo-local `tmp/`.

## Manual Sequence

1. Choose the minimal 10-12 row matrix; run read-only tri-runtime rows before any bounded write row.
2. Create `tmp/phase7-live-persona-YYYYMMDD/` and keep all raw material under it.
3. Confirm clean/frozen checkout, row-owned homes, and class-only budget/auth sidecars.
4. Run rows manually; stop on mutation, budget exhaustion, auth uncertainty, or redaction failure.
5. Produce only the sanitized summary; keep raw artifacts local unless requested for private debugging.

## Public Summary Shape

The public summary uses `phase7.live-persona-canary-summary.v1` with class-only
fields such as `execution_mode_class=manual_opt_in`,
`trigger_class=operator_local_manual`,
`raw_artifact_retention_class=operator_local_ignored_tmp`,
`public_artifact_class=sanitized_class_only_summary`,
`provider_launch_source_class=manual_operator`,
`ci_provider_launch_allowed=false`,
`release_publish_provider_launch_allowed=false`, `nightly_status_class=deferred`,
and `nightly_allowed_triggers` containing `workflow_dispatch` and `schedule`.

Rows may include ids and runtime/persona/workflow/write/result/next-step,
shadow-live, capture-policy, redaction, finding, and event-count classes. Do not
include prompt/final-answer/provider text, stdout/stderr, transcripts, argv/env
values, secrets, auth paths, account data, absolute paths, hashes, or provider
session identifiers.

Policy tests validate this shape through `tests.helpers.persona_summary`, shared
with Phase 4 live-smoke class-only negative cases. The helper is test-only;
scripts and product code must not import it.
