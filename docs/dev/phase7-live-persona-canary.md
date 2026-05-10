# Phase 7 Live Persona Canary

This runbook is for the small Phase 7 live persona canary only. It defines the
operator contract for a manual run and the sanitized public summary that may be
shared afterward.

## Policy

- Manual live is opt-in. It is never started by pull request, push, release, or
  publish jobs.
- The operator approves the budget, provider account, row set, and local
  workspace before any provider CLI is launched.
- Raw artifacts stay ignored/operator-local under repo-local `tmp/` roots. This
  includes prompts, stdout/stderr, transcripts, argv/env captures, auth/account
  data, home paths, provider replies, command files, and raw diffs.
- Public output is a sanitized class-only summary. It may contain row ids,
  runtime/persona/workflow/result/write/next-step classes, aggregate counts,
  redaction status, and finding classes. It must not contain raw text, local
  paths, hashes, account identifiers, command lines, tokens, provider replies,
  or transcript excerpts.
- Release and publish jobs must not launch provider CLIs. If they need Phase 7
  evidence, they consume an already-produced sanitized summary by report id.
- Nightly is deferred until manual summaries converge. If a nightly canary is
  added later, it must use a dedicated workflow with `workflow_dispatch` and
  optionally `schedule` only, protected credentials, strict budgets, and
  sanitized summary artifacts only.

## Manual Sequence

1. Choose the minimal 10-12 row persona matrix. Run read-only tri-runtime rows
   first; enable one bounded write row only after read-only rows converge.
2. Create a fresh ignored local root such as
   `tmp/phase7-live-persona-YYYYMMDD/`. Keep runner workspaces, runtime homes,
   prompts, transcripts, stdout/stderr, argv/env, and sidecars inside ignored
   `tmp/` paths.
3. Confirm the source checkout is clean or intentionally frozen, the runtime
   homes are row-owned, and budget/auth sidecars record classes only for public
   reporting.
4. Run the live rows manually from the operator machine. Stop on unexpected
   mutation, budget exhaustion, provider auth uncertainty, or redaction failure.
5. Produce only the sanitized summary for review. Keep raw artifacts local unless
   a maintainer explicitly requests private debugging material.

## Public Summary Shape

The public summary uses `phase7.live-persona-canary-summary.v1` and class-only
fields:

- `execution_mode_class`: `manual_opt_in`
- `trigger_class`: `operator_local_manual`
- `raw_artifact_retention_class`: `operator_local_ignored_tmp`
- `public_artifact_class`: `sanitized_class_only_summary`
- `provider_launch_source_class`: `manual_operator`
- `release_publish_provider_launch_allowed`: `false`
- `nightly_status_class`: `deferred`
- `nightly_allowed_triggers`: `workflow_dispatch`, `schedule`

Rows may include `row_id`, runtime/persona/workflow classes, write/result/next
step classes, redaction status class, finding classes, and event class counts.
Do not include prompt text, final answer text, stdout/stderr, transcripts,
argv/env values, auth paths, account data, absolute paths, hashes, or provider
session identifiers.

Policy tests validate this shape through `tests.helpers.persona_summary`, which
also shares the class-only negative cases with the Phase 4 live-smoke summary
tests. The helper is test-only; scripts and product code must not import it.
