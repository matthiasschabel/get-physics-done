---
name: gpd:quick
description: Execute a quick research task with GPD guarantees (atomic commits, state tracking) but skip optional agents
context_mode: project-required
allowed-tools:
  - file_read
  - file_write
  - file_edit
  - find_files
  - search_files
  - shell
  - task
  - ask_user
---


<objective>
Execute small, ad-hoc research tasks in an initialized GPD project while
preserving atomic commits and durable state tracking. The workflow owns the
staged quick planner handoff, executor routing, completion record, and
complexity promotion boundary. It spawns `gpd-planner` and `gpd-executor`
only from the active stage authority.

Records completion through structured `gpd state` commands and quick-task
summary files, not a custom STATE.md table.
</objective>

<execution_context>
@{GPD_INSTALL_DIR}/workflows/quick/task-bootstrap.md
</execution_context>

<context>
@GPD/STATE.md
</context>

<process>
Follow the included first-stage quick authority exactly. After each staged reload, follow only `staged_loading.eager_authorities` for the active stage and do not read `staged_loading.must_not_eager_load` or the root workflow index.
Preserve workflow gates by following the active stage authority: validation,
task description, staged planner loading, planning, execution, preflight, state
updates, commits, and quick-to-full promotion.
</process>
