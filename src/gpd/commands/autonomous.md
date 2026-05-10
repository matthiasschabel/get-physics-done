---
name: gpd:autonomous
description: Run remaining phases through staged discuss→plan→execute→verify
argument-hint: "[--from N]"
context_mode: project-required
requires:
  files: ["GPD/ROADMAP.md", "GPD/STATE.md"]
allowed-tools:
  - file_read
  - shell
  - find_files
  - search_files
  - ask_user
  - task
---

<objective>
Run remaining phases through staged autonomous orchestration. Child commands own
state updates and phase artifacts.
</objective>

<execution_context>
@{GPD_INSTALL_DIR}/workflows/autonomous/initialize-discover.md
</execution_context>

<context>
`--from N` starts from phase N. Staged init resolves project context.
</context>

<process>
Follow the included first-stage authority until stop, block, checkpoint, or
milestone closeout.
</process>
