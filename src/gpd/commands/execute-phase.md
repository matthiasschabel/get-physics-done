---
name: gpd:execute-phase
description: Execute all plans in a phase with wave-based parallelization
argument-hint: "<phase-number> [--gaps-only]"
context_mode: project-required
requires:
  files: ["GPD/ROADMAP.md"]
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
Run staged phase waves: select plans, dispatch work, verify, update state, resume.
</objective>

<execution_context>
@{GPD_INSTALL_DIR}/workflows/execute-phase/phase-bootstrap.md
</execution_context>

<arguments>
Phase: $ARGUMENTS

- `--gaps-only`: only gap-closure plans.
</arguments>

<process>
Read the included bootstrap authority first. Later rerun init and read only
`staged_loading.eager_authorities`; never read
`staged_loading.must_not_eager_load`.
</process>
