---
name: gpd:help
description: Show available GPD commands and usage guide
argument-hint: "[--all | --command <name>]"
context_mode: global
---


<objective>
Display GPD help by delegating to the renderer-backed local CLI help bridge, with the workflow-owned help surface as the marker fallback.

Return only reference content. Do not add project-specific analysis, git status,
next-step suggestions, or commentary beyond the requested reference extract.
</objective>

Shared wrapper rule for every extract below: the loaded workflow help file is the authority only when the local CLI bridge is unavailable. Use the bridge first, and use the workflow-owned reference fallback without rewriting, summarizing, or inventing alternate wording.

Bridge command rule: run the local CLI raw help bridge for the requested mode, parse the JSON, and return the referenced markdown or compact fields as human-readable help. The bridge is provider-free and renderer-backed.

- `@{GPD_INSTALL_DIR}/workflows/help.md` - Fallback marker source path. This inline path documents the workflow-owned help surface without eagerly inlining the detailed reference into this command prompt.

Use the workflow-owned stable markers as the extraction boundaries for fallback mode:

- `<!-- gpd-help:quick-start:start -->` / `<!-- gpd-help:quick-start:end -->`
- `<!-- gpd-help:command-index:start -->` / `<!-- gpd-help:command-index:end -->`
- `<!-- gpd-help:detailed-command-reference:start -->` / `<!-- gpd-help:detailed-command-reference:end -->`

Return marker contents only; never print the HTML marker comments themselves. Visible headings inside marker ranges are output labels only.

Runtime command-surface note: refer to the command that invoked this wrapper as "this help command"; do not print adapter-specific examples.

<process>

## Step 1: Parse Arguments

Check whether the user passed `--command <name>` or `--all`.

- If `$ARGUMENTS` contains `--command <name>`: display the **Single Command Detail Extract** (step 4).
- If `$ARGUMENTS` contains `--all` and does not contain `--command <name>`: display the **Compact Command Index** (step 3).
- If `$ARGUMENTS` is empty or contains neither `--all` nor `--command <name>`: display the **Quick Start Extract** (step 2) only.

## Step 2: Quick Start Extract (Default Output)

Preferred bridge path:

```bash
gpd --raw help
```

- Parse JSON field `quick_start.markdown`.
- Output ONLY that markdown.
- Append this one wrapper-owned line: `Run this help command with --all for the compact command index.`

Workflow-owned reference fallback:

- Extract from `<!-- gpd-help:quick-start:start -->` through `<!-- gpd-help:quick-start:end -->`.
- Exclude the marker comment lines themselves.
- Do not output adapter-specific examples.
- Append this one wrapper-owned line: `Run this help command with --all for the compact command index.`

Then STOP.

## Step 3: Compact Command Index (--all)

Preferred bridge path:

```bash
gpd --raw help --all
```

- Parse JSON fields `quick_start.markdown`, `command_index_markdown`, and `detailed_help_follow_up`.
- Output the quick-start markdown, then the command-index markdown.
- Replace the generic detailed-help follow-up with this one wrapper-owned line: `Run this help command with --command <name> for detailed help on one command.`

Workflow-owned reference fallback:

- Extract from `<!-- gpd-help:quick-start:start -->` through `<!-- gpd-help:command-index:end -->`.
- Exclude the marker comment lines themselves.
- Do not output adapter-specific examples.
- Append this one wrapper-owned line: `Run this help command with --command <name> for detailed help on one command.`

Then STOP.

## Step 4: Single Command Detail Extract (--command <name>)

- Parse the command name from `$ARGUMENTS` after `--command`.
- Accept either a bare command name such as `plan-phase`, a canonical runtime command such as `gpd:plan-phase`, or the current runtime's native command label.
- If the lookup includes inline flags or arguments such as `gpd:new-project --minimal` or `new-project --minimal`, parse the inline arguments separately and normalize the lookup to the base command block that documents those flags or arguments.

Preferred bridge path:

```bash
gpd --raw help --command <name>
```

- Pass through the normalized command name after `--command`.
- If the bridge returns `ok: false` with `error: "unknown_command"`, output this one line and STOP: `Unknown command. Run this help command with --all for the compact command index.`
- If the bridge returns `detail_markdown`, output that renderer-owned markdown without rewriting it.
- Otherwise render a compact detail block from `canonical_command`, `description`, `argument_hint`, `context_mode`, `project_reentry_capable`, `requires`, and `allowed_tools`.
- Include command-context preflight fields when present, including the read-only runtime-owned permission snapshot / runtime-owned permission alignment metadata projected from canonical command policy.

Workflow-owned reference fallback:

- Normalize the lookup to the matching canonical runtime command inside the workflow-owned detailed-command marker range (`<!-- gpd-help:detailed-command-reference:start -->` / `<!-- gpd-help:detailed-command-reference:end -->`), whose visible heading is `## Detailed Command Reference`.
- Output ONLY the smallest matching detailed command block.
- Include the nearest containing section heading (for example `### Phase Planning`) plus the matching command block.
- Include matching `Flags:`, `Usage:`, and `Result:` lines that belong to that command when present.
- Stop before the next command block begins.
- If no command matches after normalization, output this one line and STOP: `Unknown command. Run this help command with --all for the compact command index.`
</process>
