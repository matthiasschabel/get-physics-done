# Stage Stop Envelope

Compact model-facing convention for deciding what a stop, checkpoint, blocked
return, failed return, or completion renders as the final `## > Next Up` block.
The envelope is not user-facing by itself; it is the typed source for the
rendered closeout.

```yaml
stage_stop:
  workflow: execute-phase
  stage: wave_dispatch
  status: checkpoint
  reason: first_result_review
  checkpoint: first_result
  user_decision_needed: true
  next_runtime_command: gpd:resume-work
  also_available:
    - gpd:execute-phase {phase_number}
    - gpd:suggest-next
```

## Field Rules

- `workflow`: public workflow id, such as `execute-phase`, `verify-work`, or
  `plan-phase`.
- `stage`: manifest stage id, such as `wave_dispatch`, `closeout`, or
  `gap_repair`.
- `status`: one of `checkpoint`, `blocked`, `completed`, or `failed`.
- `reason`: compact snake_case reason for `checkpoint`, `blocked`, and
  `failed` stops.
- `checkpoint`: compact checkpoint class, or `none`.
- `user_decision_needed`: boolean. True only when the next run depends on user
  input.
- `next_runtime_command`: exactly one public `gpd:` runtime command. Shell
  commands, `gpd --raw init`, and `gpd --raw stage field-access` stay out of
  this field.
- `also_available`: optional secondary public commands. These are alternatives,
  not competing primaries; keep raw staged reload mechanics out.

If no domain-specific route is clear, set `next_runtime_command` to
`gpd:suggest-next`.

## Owner Labels

Use owner labels when a stop surface also mentions local helper commands:

- `runtime`: public runtime commands rendered from `next_runtime_command` or
  `also_available`.
- `local_transition`: local state transitions such as
  `gpd phase complete N`. These can be the primary only for readiness-gated
  local transition surfaces, not for blocked/checkpoint runtime stops.
- `local_helper`: secondary local helper work such as helper-owned checkpoint
  cleanup. Keep these out of `next_runtime_command` and `also_available`.
- `local_finalizer`: secondary local finalizer commands that produce or apply a
  concrete artifact.
- `display_only`: explanatory paths or examples that are not commands to run.

Blocked, checkpoint, failed, and post-completion runtime stops keep
`next_runtime_command` as the primary runtime route. A ready local transition
may render `Primary local transition: ...`, but the next runtime command after
that transition must be rendered separately under `**After this completes:**`.

## Render Rule

Every user-facing stop renders from the envelope into this shape:

```markdown
## > Next Up

Primary: `gpd:suggest-next`

**Also available:**
- `gpd:suggest-next` -- confirm the next action

<sub>Start a fresh context window, then run the primary command above.</sub>
```

A rendered `## > Next Up` block contains exactly one `Primary:` line, and
that line contains a public `gpd:` command. Put secondary commands only
under `**Also available:**`, `**After this completes:**`, or another clearly
secondary label.

For readiness-gated local transitions, the one primary line may use the owner
label:

```markdown
## > Next Up

Primary local transition: `gpd phase complete N`

**After this completes:**
- `gpd:plan-phase N+1` -- continue with the next runtime workflow

**Secondary local helper:**
- `gpd --raw phase checkpoint cleanup --phase N --namespace phase --policy successful-closeout` -- remove helper-owned checkpoint tags after success
```

## Raw-Init Boundary

Raw staged reload mechanics belong only in runtime and agent-authority loading
instructions.

- Allowed: shell snippets and stage-loading instructions before closeout render
  logic, such as `gpd --raw init ... --stage ...`.
- Allowed: field inventory instructions such as
  `gpd --raw stage field-access ...`.
- Not user-facing: rendered `## > Next Up` blocks, checkpoint text intended as final
  user output, or closeout snippets that ask the user to run raw staged-init or
  field-access commands.

## Route Examples

| Stop class | `status` | `checkpoint` | `next_runtime_command` |
| --- | --- | --- | --- |
| Resumable checkpoint | `checkpoint` | `first_result` | `gpd:resume-work` |
| Blocked contract gate | `blocked` | `none` | `gpd:sync-state` |
| New project setup gate | `blocked` | `none` | `gpd:new-project` |
| Verification gaps | `blocked` | `verification_gap` | `gpd:plan-phase N --gaps` |
| Successful next phase with context | `completed` | `none` | `gpd:plan-phase N` |
| Successful next phase without context | `completed` | `none` | `gpd:discuss-phase N` |
| Milestone complete | `completed` | `none` | `gpd:complete-milestone` |
| Failed stop with no clear route | `failed` | `none` | `gpd:suggest-next` |
