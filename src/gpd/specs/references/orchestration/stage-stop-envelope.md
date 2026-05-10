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
