---
name: gpd:autonomous
description: Run all remaining phases autonomously — discuss→plan→execute→verify per phase
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
Execute remaining milestone phases through the staged autonomous orchestrator:
discover -> discuss -> plan -> execute -> verify -> closeout. Child commands
own roadmap/state updates and phase artifacts.
</objective>

<execution_context>
@{GPD_INSTALL_DIR}/workflows/autonomous/initialize-discover.md
</execution_context>

<context>
Optional flag: `--from N` starts from phase N. Project context and routing state
come from staged init; do not preload extra context.
</context>

<process>
Read the included first-stage authority, then follow its staged loading rule
until the workflow stops, blocks, checkpoints, or closes the milestone.
</process>
