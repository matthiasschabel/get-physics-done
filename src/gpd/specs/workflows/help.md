<purpose>
Display the complete GPD command reference. Output ONLY the reference content. Do NOT add project-specific analysis, git status, next-step suggestions, or any commentary beyond the reference.
</purpose>

<reference>
# GPD Command Reference

**GPD** (Get Physics Done) creates hierarchical research plans optimized for solo agentic physics research with AI research agents.

## Startup Checklist

Use the shared onboarding surfaces in the README or installer output for the longer beginner-first startup order and prerequisites.

1. `gpd:help` - See the command reference first.
2. `gpd:start` - Let GPD choose the safest first step for the current folder.
3. `gpd:tour` - Get a read-only guided tour before you choose.
4. `gpd:new-project` or `gpd:map-research` - Begin the actual work path once you know the folder state.
5. `gpd:resume-work` - Continue later from the selected project's canonical state.
6. `gpd:settings` - Change autonomy, permissions, or runtime preferences after your first successful start or later.
7. `gpd:set-tier-models` - Directly pin concrete `tier-1`, `tier-2`, and `tier-3` model ids for the active runtime.

## Invocation Surfaces

This reference lists the canonical in-runtime command names for the installed runtime's public command surface.

- If you are new to terminals or runtime setup, start with the Beginner Onboarding Hub linked from the README and installer output.
- That shared onboarding surface keeps the OS guides, runtime guides, and startup checklist in one place.
- Use these names inside the installed agent/runtime command surface.
- Runtime label: Show `gpd:` as native labels; keep local CLI `gpd ...` unchanged.
- If a reference section shows canonical `gpd:` names, treat them as lookup labels unless you are copying a normal-terminal command exactly.
- Use `gpd --help` to inspect the executable local install/readiness/permissions/diagnostics surface directly.
- Use the generated local CLI summary below for the read-only runtime-owned approval/alignment snapshot, unattended readiness, and permissions sync commands. Use `supervised` unless you intentionally selected a different autonomy mode.
- Use `gpd doctor` to check the selected install target and runtime-local readiness signals; add `--live-executable-probes` when you also want cheap local executable probes such as `pdflatex --version`, `tectonic --version`, or `wolframscript -version`.
- If you need to validate whether a public runtime command can run in the current workspace, use `gpd validate command-context <name>`.
- That is the generic typed command-policy check for the public runtime surface. Today, `gpd validate review-contract <command>` and `gpd validate review-preflight <command> [subject] --strict` are specialized typed surfaces for commands that expose review/publication contracts.
- If a plan declares specialized `tool_requirements`, use `gpd validate plan-preflight <PLAN.md>` from your normal terminal before execution.

<!-- gpd-public-surface:local-cli-bridge-summary:start -->
Use `gpd --help` from your normal terminal for the broader local CLI surface: install/readiness checks, typed command validation, permissions, observability, diagnostics, recovery, cost, presets, and shared Wolfram integration.

- `gpd --help`
- `gpd doctor`
- `gpd validate unattended-readiness --runtime <runtime> --autonomy <mode>`
- `gpd permissions status --runtime <runtime> --autonomy <mode>`
- `gpd permissions sync --runtime <runtime> --autonomy <mode>`
- `gpd resume`
- `gpd resume --recent`
- `gpd observe execution`
- `gpd cost`
- `gpd presets list`
- `gpd validate plan-preflight <PLAN.md>`
- `gpd integrations status wolfram`
<!-- gpd-public-surface:local-cli-bridge-summary:end -->

<!-- gpd-public-surface:recovery-note:start -->
Recovery ladder: use `gpd resume` for the current-workspace read-only recovery snapshot. If that is the wrong workspace, use `gpd resume --recent` to find the workspace first, then continue inside that workspace with `resume-work`. After resuming, `suggest-next` is the fastest next command. Before stepping away mid-phase, run `pause-work` so that ladder has an explicit handoff to restore, projected from canonical continuation.
<!-- gpd-public-surface:recovery-note:end -->

<!-- gpd-help:quick-start:start -->
## Quick Start

If you only remember one order, use this: `help -> start -> tour -> new-project / map-research -> resume-work`.
In runtime terms, that means `gpd:help`, then `gpd:start`, then `gpd:tour`, then `gpd:new-project` or `gpd:map-research`, and later `gpd:resume-work` when you return.

Use the path that matches your current situation:

**New work**
1. `gpd:start` - Guided first-run router that chooses the safest first step for this folder
2. `gpd:tour` - Get a read-only overview before choosing
3. `gpd:new-project` - Create a full GPD project
4. `gpd:new-project --minimal` - Create a project through the shortest setup path

**Existing work**
1. `gpd:map-research` - Map an existing folder before turning it into a GPD project
2. `gpd:new-project` - Turn that mapped context into a full GPD project

**Returning work**
1. `gpd resume` - Reopen the current-workspace recovery snapshot from your normal terminal
2. `gpd resume --recent` - Find a different workspace first from your normal terminal
3. `gpd:resume-work` - Continue inside the reopened project's canonical state
4. `gpd:progress` - See the broader project snapshot
5. `gpd:suggest-next` - Get the fastest next action
6. `gpd observe execution` - Read-only progress / waiting state snapshot, conservative `possibly stalled` wording, and the next read-only checks from your normal terminal
7. `gpd cost` - Review recorded machine-local usage / cost from your normal terminal

**Post-startup settings**
1. `gpd:settings` - Change autonomy, permissions, and broader runtime preferences after your first successful start or later
2. `gpd:set-tier-models` - Pin concrete `tier-1`, `tier-2`, and `tier-3` model ids only

When a side investigation appears later, use `gpd:tangent` first. It is the chooser for stay / quick / defer / branch. Use `gpd:branch-hypothesis` only when that tangent needs its own git-backed branch.
<!-- gpd-help:quick-start:end -->
<!-- gpd-help:command-index:start -->
## Command Index

This is the compact grouped list of runtime commands. For normal-terminal install, readiness, and diagnostics commands, use `gpd --help`.

### Starter commands

- `gpd:help` - Show the quick start or command index
- `gpd:start` - Guided first-run router for the safest first path in the current folder
- `gpd:tour` - Show a read-only overview of the main commands
- `gpd:new-project` - Create a full GPD project
- `gpd:new-project --minimal` - Create a GPD project through the shortest setup path
- `gpd:map-research` - Map an existing research folder before planning
- `gpd:resume-work` - Resume the selected project's canonical state inside the runtime
- `gpd:progress` - Review project status and likely next steps
- `gpd:suggest-next` - Ask only for the next best action
- `gpd:explain [concept]` - Explain a concept, method, result, or paper
- `gpd:quick` - Run one small bounded task without the full phase workflow

### Planning and execution

- `gpd:discuss-phase <number>` - Capture phase context before planning
- `gpd:research-phase <number>` - Run a focused phase literature survey
- `gpd:list-phase-assumptions <number>` - Preview the planned phase approach
- `gpd:discover [phase or topic]` - Survey methods, literature, and tools before planning; `quick` is verification-only
- `gpd:show-phase <number>` - Inspect one phase's artifacts and status
- `gpd:route [--frozen=yes|no] [--change=extend|revise] [--layer=new|change]` - Route a scope change to the right milestone/phase workflow
- `gpd:plan-phase <number>` - Build a detailed execution plan for a phase
- `gpd:execute-phase <phase-number> [--gaps-only]` - Run all plans in a phase, or only gap-closure plans
- `gpd:autonomous [--from N]` - Run all remaining phases autonomously (discuss→plan→execute→verify each)
- `gpd:derive-equation` - Run a rigorous derivation workflow from project context or one explicit current-workspace target

### Roadmap and milestones

- `gpd:add-phase <description>` - Append a new phase to the roadmap
- `gpd:insert-phase <after> <description>` - Insert urgent work between phases
- `gpd:remove-phase <number>` - Remove a future phase and renumber later ones
- `gpd:revise-phase <number> "<reason>"` - Supersede a completed phase with a replacement
- `gpd:merge-phases <source> <target>` - Fold one phase's results into another
- `gpd:new-milestone <name>` - Start the next milestone
- `gpd:complete-milestone <version>` - Archive a completed milestone

### Validation and analysis

- `gpd:verify-work [phase]` - Run physics verification checks
- `gpd:debug [issue description]` - Start a persistent debug session
- `gpd:dimensional-analysis` - Check dimensional consistency for a project phase or one explicit current-workspace file
- `gpd:limiting-cases` - Check known limits for a project phase or one explicit current-workspace file
- `gpd:numerical-convergence` - Run convergence checks for a project phase or one explicit current-workspace artifact
- `gpd:compare-experiment` - Compare results against external data
- `gpd:compare-results` - Compare internal results or baselines and write the verdict under `GPD/comparisons/`
- `gpd:validate-conventions [phase]` - Check notation and convention consistency
- `gpd:regression-check [phase]` - Scan for regressions in recorded verification state
- `gpd:health` - Run project health checks
- `gpd:parameter-sweep [phase | computation anchor]` - Run a structured parameter sweep
- `gpd:sensitivity-analysis` - Rank which inputs matter most from project context or explicit current-workspace flags
- `gpd:error-propagation` - Track uncertainties through a calculation chain

### Knowledge authoring

- `gpd:digest-knowledge [topic|arXiv id|source file|knowledge path]` - Create or update a draft knowledge doc under `GPD/knowledge/` in the current workspace
- `gpd:review-knowledge [knowledge path|knowledge id]` - Review one canonical current-workspace knowledge doc and write its review artifact

### Writing and publication

- `gpd:literature-review [topic or research question]` - Create a structured literature review under `GPD/literature/` in the current workspace
- `gpd:write-paper [--intake path/to/write-paper-authoring-input.json]` - Draft a paper from current project results or one explicit external-authoring intake manifest into the resolved manuscript lane
- `gpd:peer-review [paper directory | manuscript path | explicit artifact path]` - Run the staged review workflow on the current project manuscript or one explicit artifact
- `gpd:respond-to-referees [--manuscript PATH --report PATH | report path | paste]` - Draft referee responses and revise the resolved manuscript root
- `gpd:arxiv-submission [manuscript root or .tex entrypoint]` - Package a built manuscript for arXiv from the resolved GPD-owned manuscript root or entrypoint
- `gpd:slides [topic, audience, or source path]` - Create presentation slides

### Tangents, memory, and exports

- `gpd:tangent [description]` - Chooser for stay / quick / defer / branch when a side investigation appears
- `gpd:branch-hypothesis <description>` - Explicit git-backed alternative path for a side investigation
- `gpd:compare-branches` - Compare results across hypothesis branches
- `gpd:pause-work` - Save a continuation handoff before stepping away
- `gpd:add-todo [description]` - Capture a task or idea
- `gpd:check-todos [area]` - Review pending todos and pick one
- `gpd:decisions [phase or keyword]` - Search the decision log
- `gpd:graph` - Visualize phase dependencies
- `gpd:export [--format html|latex|zip|all] [--commit]` - Export project artifacts; generated text exports are committed only with explicit `--commit`
- `gpd:export-logs [--format jsonl|json|markdown] [--session <id>] [--last N] [--command <label>] [--phase <phase>] [--category <name>] [--no-traces] [--output-dir <path>]` - Export observability logs
- `gpd:error-patterns [category]` - Review common project-specific errors
- `gpd:record-backtrack [--reverted-commit=<sha>] [--trigger=<text>] [--phase=<NN-slug>] [description]` - Capture a backtrack event (what went wrong, what got reverted)
- `gpd:record-insight [description]` - Save a project-specific lesson
- `gpd:audit-milestone [version]` - Audit milestone completion against goals
- `gpd:plan-milestone-gaps` - Turn audit gaps into new phases

### Configuration and maintenance

- `gpd:settings` - Guided autonomy, permissions, and runtime configuration after your first successful start or later
- `gpd:set-tier-models` - Directly pin concrete tier model ids
- `gpd:set-profile <profile>` - Switch the abstract model profile
- `gpd:compact-state` - Archive old `STATE.md` entries
- `gpd:sync-state` - Repair diverged `STATE.md` and `state.json`
- `gpd:undo` - Roll back the last GPD operation with a safety checkpoint
- `gpd:update` - Update GPD to the latest version
- `gpd:reapply-patches` - Reapply local modifications after updating
<!-- gpd-help:command-index:end -->
<!-- gpd-help:detailed-command-reference:start -->
## Detailed Command Reference

Use `gpd:help --command <name>` when you want the detailed notes for one runtime command at a time.

Core workflow: `gpd:new-project` -> `gpd:discuss-phase` -> `gpd:plan-phase` -> `gpd:execute-phase` -> `gpd:verify-work` -> repeat.

Project-aware technical-analysis lane: `gpd:derive-equation`, `gpd:dimensional-analysis`, `gpd:limiting-cases`, `gpd:numerical-convergence`, `gpd:sensitivity-analysis`, `GPD/analysis/`. `gpd:graph` and `gpd:error-propagation` are separate commands and are not part of this relaxed current-workspace lane.

### Starter commands

**`gpd:help [--all | --command <name>]`**
Show available GPD commands and usage guide

Usage examples:
Usage: `gpd:help [--all | --command <name>]`

Registry metadata:
- Canonical command: `gpd:help`
- Argument hint: `[--all | --command <name>]`
- Context mode: `global`

**`gpd:start [optional short goal]`**
Choose the right first GPD action for this folder and route into the real workflow

Usage examples:
Usage: `gpd:start [optional short goal]`

Registry metadata:
- Canonical command: `gpd:start`
- Argument hint: `[optional short goal]`
- Context mode: `projectless`

**`gpd:tour [optional short goal]`**
Show a guided beginner walkthrough of the core GPD commands without taking action

Usage examples:
Usage: `gpd:tour [optional short goal]`

Registry metadata:
- Canonical command: `gpd:tour`
- Argument hint: `[optional short goal]`
- Context mode: `projectless`

**`gpd:new-project`**
Initialize a new physics research project with deep context gathering and PROJECT.md

Usage examples:
Usage: `gpd:new-project`
Usage: `gpd:new-project --minimal`
Usage: `gpd:new-project --minimal @file.md`
Usage: `gpd:new-project --auto`

Documented variants:
- `gpd:new-project --minimal`

Notes:
- All modes build a scoping contract before downstream artifacts.
- Blocking gaps get one targeted repair prompt, and scope must be explicitly approved before requirements or roadmap generation.
- `--minimal @file.md` still repairs blocking gaps and asks for scoping approval.
- `--auto` follows the configured autonomy gates.
- `GPD/state.json.bak` and `GPD/state.json.lock` are local recovery/coordination files.

Registry metadata:
- Canonical command: `gpd:new-project`
- Argument hint: `[--auto] [--minimal [@file.md]]`
- Context mode: `projectless`
- Staged workflow: new-project with stages scope_intake, scope_approval, minimal_artifacts, workflow_preferences, project_artifacts, literature_survey, requirements_authoring, roadmap_authoring, conventions_handoff, completion.

**`gpd:map-research`**
Map existing research project — theoretical framework, computations, conventions, and open questions

Usage examples:
Usage: `gpd:map-research`

Registry metadata:
- Canonical command: `gpd:map-research`
- Argument hint: `[optional: specific area to map, e.g., 'hamiltonian' or 'numerics' or 'perturbation-theory']`
- Context mode: `projectless`
- Staged workflow: map-research with stages map_bootstrap, mapper_authoring.

**`gpd:resume-work`**
Resume research from previous session with full context restoration

Usage examples:
Usage: `gpd:resume-work`

Notes:
- `state.json.continuation` is the durable authority. Canonical continuation fields define the public resume vocabulary: `active_resume_kind`, `active_resume_origin`, `active_resume_pointer`, `active_bounded_segment`, `derived_execution_head`, `active_resume_result`, `continuity_handoff_file`, `recorded_continuity_handoff_file`, `missing_continuity_handoff_file`, `resume_candidates`.

Registry metadata:
- Canonical command: `gpd:resume-work`
- Context mode: `project-required`
- Project reentry: supported
- Requires files: `GPD/ROADMAP.md`
- Staged workflow: resume-work with stages resume_bootstrap, state_restore, derivation_restore, resume_routing.

**`gpd:progress [--brief | --full | --reconcile]`**
Check research progress, show context, and route to next action (execute or plan)

Usage examples:
Usage: `gpd:progress [--brief | --full | --reconcile]`

Notes:
- Usage: `gpd:progress --full`
- Usage: `gpd:progress --brief`
- Usage: `gpd:progress --reconcile`
- The local CLI `gpd progress` is a read-only renderer with `json|bar|table` output. Local CLI: `gpd progress json|bar|table`.

Registry metadata:
- Canonical command: `gpd:progress`
- Argument hint: `[--brief | --full | --reconcile]`
- Context mode: `project-required`
- Project reentry: supported
- Requires files: `GPD/PROJECT.md`

**`gpd:suggest-next`**
Suggest the most impactful next action based on current project state

Usage examples:
Usage: `gpd:suggest-next`

Registry metadata:
- Canonical command: `gpd:suggest-next`
- Context mode: `projectless`

**`gpd:explain [concept, result, method, notation, or paper]`**
Explain a physics concept rigorously in the context of the active project or a standalone question with an explicit topic

Usage examples:
Usage: `gpd:explain [concept, result, method, notation, or paper]`

Registry metadata:
- Canonical command: `gpd:explain`
- Argument hint: `[concept, result, method, notation, or paper]`
- Context mode: `project-aware`
- Subject policy: subject=explanation_subject; resolution=explanation_input; explicit inputs=concept, result, method, notation, or paper
- Output policy: mode=managed; managed root=gpd_managed_durable; default subtree=GPD/explanations

**`gpd:quick`**
Execute a quick research task with GPD guarantees (atomic commits, state tracking) but skip optional agents

Usage examples:
Usage: `gpd:quick`

Registry metadata:
- Canonical command: `gpd:quick`
- Context mode: `project-required`
- Staged workflow: quick with stages task_bootstrap, task_authoring, reference_context.

### Planning and execution

**`gpd:discuss-phase <phase> [--auto|--compact]`**
Gather phase context through adaptive questioning before planning

Usage examples:
Usage: `gpd:discuss-phase <phase> [--auto|--compact]`

Registry metadata:
- Canonical command: `gpd:discuss-phase`
- Argument hint: `<phase> [--auto|--compact]`
- Context mode: `project-required`

**`gpd:research-phase <phase-number>`**
Research how to tackle a phase (standalone - usually use gpd:plan-phase instead)

Usage examples:
Usage: `gpd:research-phase <phase-number>`

Registry metadata:
- Canonical command: `gpd:research-phase`
- Argument hint: `<phase-number>`
- Context mode: `project-required`
- Subject policy: subject=phase; resolution=phase_number; explicit inputs=phase-number
- Staged workflow: research-phase with stages phase_bootstrap, research_handoff.

**`gpd:list-phase-assumptions <phase-number>`**
Surface the AI's assumptions about a phase approach before planning

Usage examples:
Usage: `gpd:list-phase-assumptions <phase-number>`

Registry metadata:
- Canonical command: `gpd:list-phase-assumptions`
- Argument hint: `<phase-number>`
- Context mode: `project-required`
- Subject policy: subject=phase; resolution=phase_number; explicit inputs=phase-number

**`gpd:discover [phase or topic] [--depth quick|medium|deep]`**
Run discovery phase to investigate methods, literature, and approaches before planning

Usage examples:
Usage: `gpd:discover [phase or topic] [--depth quick|medium|deep]`

Notes:
- Depth quick is verification-only and writes no file; medium and deep write discovery artifacts.
- Discovery artifacts feed planning or standalone analysis.

Registry metadata:
- Canonical command: `gpd:discover`
- Argument hint: `[phase or topic] [--depth quick|medium|deep]`
- Context mode: `project-aware`
- Subject policy: subject=discovery_subject; resolution=phase_or_topic; explicit inputs=phase number or standalone topic
- Output policy: mode=managed; managed root=gpd_managed_durable; default subtree=GPD/analysis

**`gpd:show-phase <phase-number>`**
Inspect a single phase's artifacts, status, and results

Usage examples:
Usage: `gpd:show-phase <phase-number>`

Registry metadata:
- Canonical command: `gpd:show-phase`
- Argument hint: `<phase-number>`
- Context mode: `project-required`
- Requires files: `GPD/ROADMAP.md`

**`gpd:route [--frozen=yes|no] [--change=extend|revise] [--layer=new|change]`**
Decide whether a scope change is a new phase, a revision, a new milestone, or a milestone completion

Usage examples:
Usage: `gpd:route [--frozen=yes|no] [--change=extend|revise] [--layer=new|change]`

Notes:
- The frozen scope-expansion path renders the ordered compound sequence `gpd:complete-milestone` then `gpd:new-milestone`.

Registry metadata:
- Canonical command: `gpd:route`
- Argument hint: `[--frozen=yes|no] [--change=extend|revise] [--layer=new|change]`
- Context mode: `project-required`

**`gpd:plan-phase [phase] [--research] [--skip-research] [--gaps] [--skip-verify] [--light] [--inline-discuss]`**
Create detailed execution plan for a phase (PLAN.md) with verification loop

Usage examples:
Usage: `gpd:plan-phase [phase] [--research] [--skip-research] [--gaps] [--skip-verify] [--light] [--inline-discuss]`

Notes:
- `--skip-verify` may skip routine verification, but proof-bearing plans still require checker review or an equivalent main-context audit.

Registry metadata:
- Canonical command: `gpd:plan-phase`
- Argument hint: `[phase] [--research] [--skip-research] [--gaps] [--skip-verify] [--light] [--inline-discuss]`
- Context mode: `project-required`
- Requires files: `GPD/ROADMAP.md`, `GPD/STATE.md`
- Staged workflow: plan-phase with stages phase_bootstrap, research_routing, planner_authoring, checker_revision.

**`gpd:execute-phase <phase-number> [--gaps-only]`**
Execute all plans in a phase with wave-based parallelization

Usage examples:
Usage: `gpd:execute-phase <phase-number> [--gaps-only]`

Registry metadata:
- Canonical command: `gpd:execute-phase`
- Argument hint: `<phase-number> [--gaps-only]`
- Context mode: `project-required`
- Requires files: `GPD/ROADMAP.md`
- Staged workflow: execute-phase with stages phase_bootstrap, phase_classification, wave_planning, pre_execution_specialists, wave_dispatch, executor_dispatch, proof_critic_dispatch, wave_return_checkpoint, wave_failure_menu, checkpoint_resume, aggregate_and_verify, verification_handoff, gap_reverification, consistency_check, closeout.

**`gpd:autonomous [--from N]`**
Run remaining phases through staged discuss→plan→execute→verify

Usage examples:
Usage: `gpd:autonomous [--from N]`

Registry metadata:
- Canonical command: `gpd:autonomous`
- Argument hint: `[--from N]`
- Context mode: `project-required`
- Requires files: `GPD/ROADMAP.md`, `GPD/STATE.md`
- Staged workflow: autonomous with stages initialize_discover, phase_route, discuss_delegate, plan_execute_child_cycle, verification_route, gap_route, convention_lifecycle_closeout, blocked_recovery.

**`gpd:derive-equation [equation or topic to derive]`**
Perform a rigorous physics derivation with systematic verification at each step

Usage examples:
Usage: `gpd:derive-equation [equation or topic to derive]`

Notes:
- Part of the project-aware technical-analysis lane for explicit current-workspace derivations.

Registry metadata:
- Canonical command: `gpd:derive-equation`
- Argument hint: `[equation or topic to derive]`
- Context mode: `project-aware`
- Subject policy: explicit inputs=equation or topic to derive
- Output policy: mode=managed; managed root=gpd_managed_durable; default subtree=GPD/analysis; stage artifacts=gpd_owned_outputs_only

### Roadmap and milestones

**`gpd:add-phase <description>`**
Add research phase to end of current milestone in roadmap

Usage examples:
Usage: `gpd:add-phase <description>`

Registry metadata:
- Canonical command: `gpd:add-phase`
- Argument hint: `<description>`
- Context mode: `project-required`

**`gpd:insert-phase <after-phase> "<description>"`**
Insert urgent research work as decimal phase (e.g., 72.1) between existing phases

Usage examples:
Usage: `gpd:insert-phase <after-phase> "<description>"`

Registry metadata:
- Canonical command: `gpd:insert-phase`
- Argument hint: `<after-phase> "<description>"`
- Context mode: `project-required`

**`gpd:remove-phase <phase-number>`**
Remove a future research phase from roadmap and renumber subsequent phases

Usage examples:
Usage: `gpd:remove-phase <phase-number>`

Registry metadata:
- Canonical command: `gpd:remove-phase`
- Argument hint: `<phase-number>`
- Context mode: `project-required`

**`gpd:revise-phase <phase-number> <reason for revision>`**
Supersede a completed phase and create a replacement for iterative revision

Usage examples:
Usage: `gpd:revise-phase <phase-number> <reason for revision>`

Registry metadata:
- Canonical command: `gpd:revise-phase`
- Argument hint: `<phase-number> <reason for revision>`
- Context mode: `project-required`

**`gpd:merge-phases <source-phase> <target-phase>`**
Merge results from one phase into another

Usage examples:
Usage: `gpd:merge-phases <source-phase> <target-phase>`

Registry metadata:
- Canonical command: `gpd:merge-phases`
- Argument hint: `<source-phase> <target-phase>`
- Context mode: `project-required`

**`gpd:new-milestone [milestone name, e.g., 'v1.1 Finite-Temperature Extension']`**
Start a new research milestone cycle — staged init, requirements, and roadmap

Usage examples:
Usage: `gpd:new-milestone [milestone name, e.g., 'v1.1 Finite-Temperature Extension']`

Registry metadata:
- Canonical command: `gpd:new-milestone`
- Argument hint: `[milestone name, e.g., 'v1.1 Finite-Temperature Extension']`
- Context mode: `project-required`
- Staged workflow: new-milestone with stages milestone_bootstrap, survey_objectives, roadmap_authoring.

**`gpd:complete-milestone <version>`**
Archive completed research milestone and prepare for next phase of investigation

Usage examples:
Usage: `gpd:complete-milestone <version>`

Registry metadata:
- Canonical command: `gpd:complete-milestone`
- Argument hint: `<version>`
- Context mode: `project-required`
- Requires files: `GPD/ROADMAP.md`

### Validation and analysis

**`gpd:verify-work [phase] [--dimensional] [--limits] [--convergence] [--regression] [--all]`**
Verify research results through physics consistency checks

Usage examples:
Usage: `gpd:verify-work [phase] [--dimensional] [--limits] [--convergence] [--regression] [--all]`

Registry metadata:
- Canonical command: `gpd:verify-work`
- Argument hint: `[phase] [--dimensional] [--limits] [--convergence] [--regression] [--all]`
- Context mode: `project-required`
- Requires files: `GPD/ROADMAP.md`
- Review contract: review mode with 1 required output(s), 7 preflight check(s), and 4 blocking condition(s).
- Staged workflow: verify-work with stages session_router, phase_bootstrap, inventory_build, interactive_validation, gap_repair.

**`gpd:debug [issue description]`**
Systematic debugging of physics calculations with persistent state across context resets

Usage examples:
Usage: `gpd:debug [issue description]`

Registry metadata:
- Canonical command: `gpd:debug`
- Argument hint: `[issue description]`
- Context mode: `project-required`

**`gpd:dimensional-analysis [phase number or file path]`**
Systematic dimensional analysis audit on all equations in a derivation or phase

Usage examples:
Usage: `gpd:dimensional-analysis [phase number or file path]`
Usage: `gpd:dimensional-analysis results/01-SUMMARY.md`

Notes:
- Part of the project-aware technical-analysis lane; analysis artifacts belong under GPD/analysis/ when a standalone target is supplied.

Registry metadata:
- Canonical command: `gpd:dimensional-analysis`
- Argument hint: `[phase number or file path]`
- Context mode: `project-aware`
- Subject policy: explicit inputs=phase number or file path
- Output policy: mode=managed; managed root=gpd_managed_durable; default subtree=GPD/analysis

**`gpd:limiting-cases [phase number or file path]`**
Systematically identify and verify all relevant limiting cases for a result or phase

Usage examples:
Usage: `gpd:limiting-cases [phase number or file path]`
Usage: `gpd:limiting-cases results/01-SUMMARY.md`

Notes:
- Part of the project-aware technical-analysis lane for explicit current-workspace limit checks.

Registry metadata:
- Canonical command: `gpd:limiting-cases`
- Argument hint: `[phase number or file path]`
- Context mode: `project-aware`
- Subject policy: explicit inputs=phase number or file path
- Output policy: mode=managed; managed root=gpd_managed_durable; default subtree=GPD/analysis; stage artifacts=gpd_owned_outputs_only

**`gpd:numerical-convergence [phase number or file path]`**
Systematic convergence testing for numerical physics computations

Usage examples:
Usage: `gpd:numerical-convergence [phase number or file path]`
Usage: `gpd:numerical-convergence results/mesh-study.csv`

Notes:
- Part of the project-aware technical-analysis lane for explicit current-workspace convergence checks.

Registry metadata:
- Canonical command: `gpd:numerical-convergence`
- Argument hint: `[phase number or file path]`
- Context mode: `project-aware`
- Subject policy: explicit inputs=phase number or file path
- Output policy: mode=managed; managed root=gpd_managed_durable; default subtree=GPD/analysis; stage artifacts=gpd_owned_outputs_only

**`gpd:compare-experiment [prediction, dataset, phase, or comparison target]`**
Systematically compare theoretical predictions with experimental or observational data

Usage examples:
Usage: `gpd:compare-experiment [prediction, dataset, phase, or comparison target]`

Registry metadata:
- Canonical command: `gpd:compare-experiment`
- Argument hint: `[prediction, dataset, phase, or comparison target]`
- Context mode: `project-aware`
- Subject policy: subject=comparison; resolution=explicit_or_interactive_theory_data_comparison; explicit inputs=prediction, dataset path, phase identifier, or comparison target; external subjects allowed=true
- Output policy: mode=managed; managed root=gpd_managed_durable; default subtree=GPD/comparisons

**`gpd:compare-results [phase, artifact, or comparison target]`**
Compare internal results, baselines, or methods and emit decisive verdicts

Usage examples:
Usage: `gpd:compare-results [phase, artifact, or comparison target]`

Notes:
- Writes a decisive comparison artifact under GPD/comparisons/ for the current workspace.

Registry metadata:
- Canonical command: `gpd:compare-results`
- Argument hint: `[comparison target or source-a vs source-b]`
- Context mode: `project-aware`
- Subject policy: subject=comparison; resolution=explicit_or_interactive_internal_comparison; explicit inputs=comparison target, phase, artifact path, or source-a vs source-b; external subjects allowed=true
- Output policy: mode=managed; managed root=gpd_managed_durable; default subtree=GPD/comparisons

**`gpd:validate-conventions [phase number to limit scope, or empty for all]`**
Validate convention consistency across all phases

Usage examples:
Usage: `gpd:validate-conventions [phase number to limit scope, or empty for all]`

Registry metadata:
- Canonical command: `gpd:validate-conventions`
- Argument hint: `[phase number to limit scope, or empty for all]`
- Context mode: `project-required`

**`gpd:regression-check [phase] [--quick]`**
Scan completed phase summaries and verifications for convention conflicts and verification-state regressions

Usage examples:
Usage: `gpd:regression-check [phase] [--quick]`

Registry metadata:
- Canonical command: `gpd:regression-check`
- Argument hint: `[phase] [--quick]`
- Context mode: `project-required`

**`gpd:health [--fix]`**
Run project health checks and optionally auto-fix issues

Usage examples:
Usage: `gpd:health [--fix]`

Registry metadata:
- Canonical command: `gpd:health`
- Argument hint: `[--fix]`
- Context mode: `projectless`

**`gpd:parameter-sweep [phase | computation anchor] [--param name --range start:end:steps] [--adaptive] [--log]`**
Systematic parameter sweep with parallel execution and result aggregation

Usage examples:
Usage: `gpd:parameter-sweep [phase | computation anchor] [--param name --range start:end:steps] [--adaptive] [--log]`

Registry metadata:
- Canonical command: `gpd:parameter-sweep`
- Argument hint: `[phase | computation anchor] [--param name --range start:end:steps] [--adaptive] [--log]`
- Context mode: `project-aware`
- Subject policy: explicit inputs=computation anchor or file path, --param name, --range start:end:steps
- Output policy: mode=managed; managed root=gpd_managed_durable; default subtree=GPD/sweeps; stage artifacts=gpd_owned_outputs_only

**`gpd:sensitivity-analysis [--target quantity] [--params p1,p2,...] [--method analytical|numerical]`**
Systematic sensitivity analysis -- which parameters matter most and how uncertainties propagate

Usage examples:
Usage: `gpd:sensitivity-analysis [--target quantity] [--params p1,p2,...] [--method analytical|numerical]`

Notes:
- Part of the project-aware technical-analysis lane for ranking influential inputs from project context or explicit current-workspace flags.

Registry metadata:
- Canonical command: `gpd:sensitivity-analysis`
- Argument hint: `[--target quantity] [--params p1,p2,...] [--method analytical|numerical]`
- Context mode: `project-aware`
- Subject policy: explicit inputs=--target quantity, --params p1,p2,...
- Output policy: mode=managed; managed root=gpd_managed_durable; default subtree=GPD/analysis; stage artifacts=gpd_owned_outputs_only

**`gpd:error-propagation [--target quantity] [--phase-range start:end]`**
Track how uncertainties propagate through multi-step calculations across phases

Usage examples:
Usage: `gpd:error-propagation [--target quantity] [--phase-range start:end]`

Registry metadata:
- Canonical command: `gpd:error-propagation`
- Argument hint: `[--target quantity] [--phase-range start:end]`
- Context mode: `project-required`

### Knowledge authoring

**`gpd:digest-knowledge [topic|arXiv id|source file|knowledge path]`**
Create or update a draft knowledge document in the current workspace from a topic, source file, arXiv ID, or canonical knowledge path

Usage examples:
Usage: `gpd:digest-knowledge [topic|arXiv id|source file|knowledge path]`
Usage: `gpd:digest-knowledge "renormalization group fixed points"`
Usage: `gpd:digest-knowledge 2401.12345v2`
Usage: `gpd:digest-knowledge hep-th/9901001`
Usage: `gpd:digest-knowledge ./notes/rg-notes.md`
Usage: `gpd:digest-knowledge ./sources/review.docx`
Usage: `gpd:digest-knowledge ./data/observables.csv`
Usage: `gpd:digest-knowledge GPD/knowledge/K-renormalization-group-fixed-points.md`

Notes:
- Creates a current-workspace knowledge document draft from a topic, paper, source file, or explicit knowledge path.
- Example document source: `gpd:digest-knowledge ./sources/review.docx`; example tabular source: `gpd:digest-knowledge ./data/observables.csv`.
- Knowledge lifecycle states are draft, in_review, stable, and superseded; use gpd:review-knowledge for approval.
- Stable knowledge enters shared runtime reference surfaces as reviewed background synthesis; it is a separate authority tier and does not override stronger evidence.
- Resolves one canonical `GPD/knowledge/{knowledge_id}.md` target in the current workspace and stops on ambiguity.
- Supports an arXiv identifier with accepted prefixes.

Registry metadata:
- Canonical command: `gpd:digest-knowledge`
- Argument hint: `[topic | source file | arXiv ID | current-workspace GPD/knowledge/K-*.md]`
- Context mode: `project-aware`
- Subject policy: subject=knowledge_document; resolution=explicit_input_to_canonical_current_workspace_target; explicit inputs=knowledge_document_path, source_path, arxiv_id, topic; external subjects allowed=true
- Output policy: mode=managed; managed root=gpd_managed_durable; default subtree=GPD/knowledge; stage artifacts=gpd_owned_outputs_only

**`gpd:review-knowledge [knowledge path or knowledge id]`**
Review a current-workspace knowledge document for approval, changes, or promotion gating

Usage examples:
Usage: `gpd:review-knowledge [knowledge path or knowledge id]`

Notes:
- Reviews a canonical current-workspace knowledge document using typed approval evidence.
- Approval can promote stable knowledge; stable and superseded states remain addressable and traceable by canonical path or knowledge id.
- Writes review artifacts under GPD/knowledge/reviews/.

Registry metadata:
- Canonical command: `gpd:review-knowledge`
- Argument hint: `[current-workspace GPD/knowledge/{knowledge_id}.md | canonical K-* knowledge_id]`
- Context mode: `project-aware`
- Subject policy: subject=knowledge_document; resolution=explicit_current_workspace_canonical_target; explicit inputs=knowledge_document_path, knowledge_id; external subjects allowed=false
- Output policy: mode=managed; managed root=gpd_managed_durable; default subtree=GPD/knowledge; stage artifacts=gpd_owned_outputs_only
- Review contract: review mode with 2 required output(s), 4 preflight check(s), and 5 blocking condition(s).

### Writing and publication

**`gpd:literature-review [topic or research question]`**
Structured literature review for a physics research topic with citation network analysis and open question identification

Usage examples:
Usage: `gpd:literature-review [topic or research question]`

Notes:
- Runs on the current project or an explicit topic: a physics research topic or research question, and writes under GPD/literature/ in the current workspace.

Registry metadata:
- Canonical command: `gpd:literature-review`
- Argument hint: `[topic or research question]`
- Context mode: `project-aware`
- Subject policy: subject=literature_topic; resolution=literature_topic; explicit inputs=topic or research question
- Output policy: mode=managed; managed root=gpd_managed_durable; default subtree=GPD/literature
- Staged workflow: literature-review with stages review_bootstrap, scope_locked, review_handoff, completion_gate.

**`gpd:write-paper [--intake path/to/write-paper-authoring-input.json]`**
Structure and write a physics paper from project research results or a bounded external-authoring intake

Usage examples:
Usage: `gpd:write-paper [--intake path/to/write-paper-authoring-input.json]`
Usage: `gpd:write-paper`
Usage: `gpd:write-paper --intake intake/write-paper-authoring-input.json`

Notes:
- Uses a bounded external-authoring lane driven by an explicit intake manifest only.
- GPD-authored outputs live under `GPD/publication/{subject_slug}/...`; `GPD/publication/{subject_slug}/intake/` stores intake/provenance state only.
- It does not mine arbitrary folders, and embedded external staged-review parity is out of scope.
- Project-backed review/response/package outputs remain in the resolved GPD manuscript lane.

Registry metadata:
- Canonical command: `gpd:write-paper`
- Argument hint: `[--intake path/to/write-paper-authoring-input.json]`
- Context mode: `project-aware`
- Subject policy: subject=publication; resolution=project_manuscript_or_bootstrap; explicit inputs=authoring_intake_manifest; external subjects allowed=false; bootstrap allowed=true
- Output policy: mode=manuscript_local_plus_gpd_auxiliary; managed root=gpd_managed_durable; default subtree=GPD/publication/{subject_slug}/manuscript; stage artifacts=allowed
- Review contract: publication mode with 9 required output(s), 13 preflight check(s), and 7 blocking condition(s).
- Scope variants: explicit_intake_manifest.
- Staged workflow: write-paper with stages paper_bootstrap, outline_and_scaffold, figure_and_section_authoring, consistency_and_references, publication_review.

**`gpd:peer-review [paper directory | manuscript path | explicit artifact path]`**
Conduct a staged six-pass peer review of a manuscript and supporting research artifacts from the current GPD project or an explicit external artifact

Usage examples:
Usage: `gpd:peer-review [paper directory | manuscript path | explicit artifact path]`
Usage: `gpd:peer-review draft.docx`
Usage: `gpd:peer-review data/observables.csv`

Notes:
- Explicit artifact intake follows command-policy supported suffixes for publication-artifact paths.
- Use `gpd validate artifact-text <path> --output <txt-path>` when explicit artifact text extraction is needed.
- Project-backed mode uses the resolved manuscript entrypoint before staged review.

Registry metadata:
- Canonical command: `gpd:peer-review`
- Argument hint: `[paper directory or manuscript/artifact path]`
- Context mode: `project-aware`
- Requires files: `paper/*.tex`, `paper/*.md`, `manuscript/*.tex`, `manuscript/*.md`, and 2 more
- Subject policy: subject=publication; resolution=explicit_or_project_manuscript; explicit inputs=manuscript_root, manuscript_path, publication_artifact_path; external subjects allowed=true; bootstrap allowed=false
- Output policy: mode=managed; managed root=gpd_managed_durable; default subtree=GPD
- Review contract: publication mode with 10 required output(s), 3 preflight check(s), and 4 blocking condition(s).
- Scope variants: explicit_artifact.
- Staged workflow: peer-review with stages bootstrap, preflight, artifact_discovery, panel_stages, final_adjudication, finalize.

**`gpd:respond-to-referees [--manuscript PATH --report PATH | report path | paste]`**
Structure a point-by-point response to referee reports for an explicit manuscript target or the current GPD manuscript

Usage examples:
Usage: `gpd:respond-to-referees [--manuscript PATH --report PATH | report path | paste]`
Usage: `gpd:respond-to-referees --manuscript paper/main.tex --report reports/referee-report.md`
Usage: `gpd:respond-to-referees reports/referee-report.md`
Usage: `gpd:respond-to-referees paste`

Notes:
- Uses a bounded external-authoring lane when an explicit intake manifest or subject is allowed by command policy.
- Project-backed review/response/package outputs stay under the resolved manuscript root; this is not a full publication-root migration.

Registry metadata:
- Canonical command: `gpd:respond-to-referees`
- Argument hint: `[--manuscript PATH] (--report PATH [--report PATH...] | paste)`
- Context mode: `project-aware`
- Subject policy: subject=publication; resolution=explicit_or_project_manuscript; explicit inputs=manuscript_path, referee_report_path, paste_referee_report; external subjects allowed=true
- Output policy: mode=managed; managed root=gpd_managed_durable; default subtree=GPD
- Review contract: publication mode with 2 required output(s), 5 preflight check(s), and 5 blocking condition(s).
- Scope variants: managed_publication_subject, explicit_external_manuscript.
- Staged workflow: respond-to-referees with stages bootstrap, report_triage, revision_planning, response_authoring, finalize.

**`gpd:arxiv-submission [manuscript root or .tex entrypoint]`**
Prepare a GPD-owned manuscript for arXiv submission with validation and packaging

Usage examples:
Usage: `gpd:arxiv-submission [manuscript root or .tex entrypoint]`
Usage: `gpd:arxiv-submission paper/`

Notes:
- Packages the GPD-owned manuscript root or a supported .tex entrypoint; it does not package arbitrary external material.

Registry metadata:
- Canonical command: `gpd:arxiv-submission`
- Argument hint: `[manuscript root or .tex entrypoint]`
- Context mode: `project-aware`
- Requires files: `paper/*.tex`, `manuscript/*.tex`, `draft/*.tex`, `GPD/publication/*/manuscript/*.tex`
- Subject policy: subject=publication; resolution=explicit_or_project_manuscript; explicit inputs=manuscript_path, manuscript_root; external subjects allowed=false; bootstrap allowed=false
- Output policy: mode=managed; managed root=gpd_managed_durable; default subtree=GPD/publication/{subject_slug}/arxiv; stage artifacts=gpd_owned_outputs_only
- Review contract: publication mode with 1 required output(s), 17 preflight check(s), and 13 blocking condition(s).
- Staged workflow: arxiv-submission with stages bootstrap, manuscript_preflight, review_gate, package, finalize.

**`gpd:slides [topic, talk title, audience, or source path]`**
Create presentation slides from a GPD project or the current folder

Usage examples:
Usage: `gpd:slides [topic, talk title, audience, or source path]`

Registry metadata:
- Canonical command: `gpd:slides`
- Argument hint: `[topic, talk title, audience, or source path]`
- Context mode: `projectless`

### Tangents, memory, and exports

**`gpd:tangent [optional description]`**
Choose how to handle a possible side investigation without silently widening scope

Usage examples:
Usage: `gpd:tangent [optional description]`

Registry metadata:
- Canonical command: `gpd:tangent`
- Argument hint: `[optional description]`
- Context mode: `project-required`

**`gpd:branch-hypothesis <description>`**
Create a hypothesis branch for parallel investigation of an alternative approach

Usage examples:
Usage: `gpd:branch-hypothesis <description>`

Registry metadata:
- Canonical command: `gpd:branch-hypothesis`
- Argument hint: `<description>`
- Context mode: `project-required`
- Requires files: `GPD/ROADMAP.md`, `GPD/STATE.md`

**`gpd:compare-branches`**
Compare results across hypothesis branches side-by-side

Usage examples:
Usage: `gpd:compare-branches`

Registry metadata:
- Canonical command: `gpd:compare-branches`
- Context mode: `project-required`

**`gpd:pause-work`**
Create continuation handoff when pausing research mid-phase

Usage examples:
Usage: `gpd:pause-work`

Registry metadata:
- Canonical command: `gpd:pause-work`
- Context mode: `project-required`

**`gpd:add-todo [optional description]`**
Capture idea or task as todo from current research conversation context

Usage examples:
Usage: `gpd:add-todo [optional description]`

Registry metadata:
- Canonical command: `gpd:add-todo`
- Argument hint: `[optional description]`
- Context mode: `projectless`

**`gpd:check-todos [area filter]`**
List pending research todos and select one to work on

Usage examples:
Usage: `gpd:check-todos [area filter]`

Registry metadata:
- Canonical command: `gpd:check-todos`
- Argument hint: `[area filter]`
- Context mode: `projectless`

**`gpd:decisions [phase number or keyword]`**
Display and search the cumulative decision log

Usage examples:
Usage: `gpd:decisions [phase number or keyword]`

Registry metadata:
- Canonical command: `gpd:decisions`
- Argument hint: `[phase number or keyword]`
- Context mode: `project-required`
- Requires files: `GPD/STATE.md`

**`gpd:graph`**
Visualize dependency graph across phases and identify gaps

Usage examples:
Usage: `gpd:graph`

Notes:
- Complements the technical-analysis lane; use separate commands such as gpd:error-propagation for uncertainty flow.

Registry metadata:
- Canonical command: `gpd:graph`
- Context mode: `project-required`

**`gpd:export [--format html|latex|zip|all] [--commit]`**
Export research results to HTML, LaTeX, or ZIP package

Usage examples:
Usage: `gpd:export [--format html|latex|zip|all] [--commit]`
Usage: `gpd:export --format latex --commit`

Notes:
- For generated text exports, outputs are committed only with explicit `--commit`.
- gpd observe execution, gpd observe sessions, gpd observe show, and gpd trace show inspect only; gpd observe event, gpd observe export, and gpd trace start|log|stop write observability.

Registry metadata:
- Canonical command: `gpd:export`
- Argument hint: `[--format html|latex|zip|all] [--commit]`
- Context mode: `project-required`

**`gpd:export-logs [--format jsonl|json|markdown] [--session <id>] [--last N] [--command <label>] [--phase <phase>] [--category <name>] [--no-traces] [--output-dir <path>]`**
Export session logs and traces to files for external review or archival

Usage examples:
Usage: `gpd:export-logs [--format jsonl|json|markdown] [--session <id>] [--last N] [--command <label>] [--phase <phase>] [--category <name>] [--no-traces] [--output-dir <path>]`
Usage: `gpd:export-logs --command execute-phase --phase 3 --category workflow`

Notes:
- Exports observability logs with passthrough filters such as --command <label>, --phase <phase>, and --category <name>.
- Empty result payloads report empty_export: true.

Registry metadata:
- Canonical command: `gpd:export-logs`
- Argument hint: `[--format jsonl|json|markdown] [--session <id>] [--last N] [--command <label>] [--phase <phase>] [--category <name>] [--no-traces] [--output-dir <path>]`
- Context mode: `project-required`

**`gpd:error-patterns [category]`**
View accumulated physics error patterns for this project

Usage examples:
Usage: `gpd:error-patterns [category]`
Usage: `gpd:error-patterns sign-error`

Notes:
- Pattern-library categories include sign-error, factor-error, convention-pitfall, convergence-issue, approximation-failure, numerical-instability, conceptual-error, and dimensional-error.

Registry metadata:
- Canonical command: `gpd:error-patterns`
- Argument hint: `[category]`
- Context mode: `project-required`

**`gpd:record-backtrack [--reverted-commit=<sha>] [--trigger=<text>] [--phase=<NN-slug>] [description]`**
Record a backtrack event (what went wrong, what got reverted) to the backtracks ledger

Usage examples:
Usage: `gpd:record-backtrack [--reverted-commit=<sha>] [--trigger=<text>] [--phase=<NN-slug>] [description]`

Registry metadata:
- Canonical command: `gpd:record-backtrack`
- Argument hint: `[--reverted-commit=<sha>] [--trigger=<text>] [--phase=<NN-slug>] [description]`
- Context mode: `project-required`

**`gpd:record-insight [optional description]`**
Record a project-specific learning or pattern to the insights ledger

Usage examples:
Usage: `gpd:record-insight [optional description]`

Registry metadata:
- Canonical command: `gpd:record-insight`
- Argument hint: `[optional description]`
- Context mode: `project-required`

**`gpd:audit-milestone [version]`**
Audit research milestone completion against original research goals

Usage examples:
Usage: `gpd:audit-milestone [version]`

Registry metadata:
- Canonical command: `gpd:audit-milestone`
- Argument hint: `[version]`
- Context mode: `project-required`
- Requires files: `GPD/ROADMAP.md`, `GPD/STATE.md`

**`gpd:plan-milestone-gaps`**
Create phases to close all gaps identified by research milestone audit

Usage examples:
Usage: `gpd:plan-milestone-gaps`

Registry metadata:
- Canonical command: `gpd:plan-milestone-gaps`
- Context mode: `project-required`
- Requires files: `GPD/v*-MILESTONE-AUDIT.md`

### Configuration and maintenance

**`gpd:settings`**
Configure autonomy, unattended execution budgets, runtime permission sync, workflow preset bundles, model-cost posture, runtime-specific tier model overrides, review cadence, and git preferences

Usage examples:
Usage: `gpd:settings`

Notes:
- Autonomy vocabulary: Supervised, Max quality, Balanced, Budget-aware, runtime defaults, YOLO.
- Configuration keys include `execution.review_cadence`, `planning.commit_docs`, `git.branching_strategy`, and statuses such as `needs-calculation`; model tiers are `tier-1`, `tier-2`, and `tier-3`.
- Use `gpd observe execution` and `gpd cost` from the normal terminal for read-only status and usage review.

Registry metadata:
- Canonical command: `gpd:settings`
- Context mode: `projectless`

**`gpd:set-tier-models`**
Configure concrete tier-1/tier-2/tier-3 model IDs for the active runtime

Usage examples:
Usage: `gpd:set-tier-models`

Registry metadata:
- Canonical command: `gpd:set-tier-models`
- Context mode: `projectless`

**`gpd:set-profile <profile>`**
Switch research profile for GPD agents (deep-theory/numerical/exploratory/review/paper-writing)

Usage examples:
Usage: `gpd:set-profile <profile>`

Registry metadata:
- Canonical command: `gpd:set-profile`
- Argument hint: `<profile>`
- Context mode: `projectless`

**`gpd:compact-state [--force]`**
Archive historical entries from STATE.md to keep it under the 150-line target

Usage examples:
Usage: `gpd:compact-state [--force]`

Notes:
- Suggested by `gpd:progress` when STATE.md grows large.

Registry metadata:
- Canonical command: `gpd:compact-state`
- Argument hint: `[--force]`
- Context mode: `project-required`

**`gpd:sync-state`**
Reconcile diverged STATE.md and state.json after manual edits or corruption

Usage examples:
Usage: `gpd:sync-state`

Registry metadata:
- Canonical command: `gpd:sync-state`
- Context mode: `project-required`
- Project reentry: supported
- Staged workflow: sync-state with stages sync_bootstrap, single_source_recovery, conflict_analysis, reconcile_and_validate.

**`gpd:undo`**
Rollback last GPD operation with safety checkpoint

Usage examples:
Usage: `gpd:undo`

Registry metadata:
- Canonical command: `gpd:undo`
- Context mode: `project-required`

**`gpd:update`**
Update GPD to latest version with changelog display

Usage examples:
Usage: `gpd:update`

Notes:
- Runs the public bootstrap update command for the active runtime.
- Preserves local modifications via patch backups.

Registry metadata:
- Canonical command: `gpd:update`
- Context mode: `global`

**`gpd:reapply-patches`**
Reapply local modifications after a GPD update

Usage examples:
Usage: `gpd:reapply-patches`

Registry metadata:
- Canonical command: `gpd:reapply-patches`
- Context mode: `projectless`
<!-- gpd-help:detailed-command-reference:end -->

### Research Publishing

Publication lane boundary: `gpd:write-paper` supports current-project manuscripts plus one bounded external-authoring lane driven by an explicit intake manifest only. In that lane, GPD-authored outputs live under `GPD/publication/{subject_slug}/...`; `GPD/publication/{subject_slug}/manuscript` is the only manuscript/build root, and `GPD/publication/{subject_slug}/intake/` keeps intake/provenance state only. It does not mine arbitrary folders or infer claim/evidence bindings from loose notes. `gpd:peer-review` can review the current project manuscript or one explicit subject allowed by its command policy; it remains the standalone follow-on command when the bounded external-authoring lane needs review. Project-backed review/response/package outputs stay on the `GPD/` and `GPD/review/` paths. `gpd:respond-to-referees` stays tied to the resolved manuscript root; `gpd:arxiv-submission` packages only a GPD-owned manuscript root or `.tex` entrypoint and does not package arbitrary external manuscript directories. This is not a full publication-root migration.

### Optional Local CLI Add-Ons

- `gpd doctor --runtime <runtime> --local` / `gpd doctor --runtime <runtime> --global` - Check the local or global runtime target from your normal terminal before using paper/manuscript workflow presets. Add `--live-executable-probes` if you also want cheap local executable probes such as `pdflatex --version`, `tectonic --version`, or `wolframscript -version`.
- Paper/manuscript workflows: inspect paper-toolchain readiness with `gpd doctor` before you plan to use that preset. Missing preset tooling degrades that preset; it does not block the base GPD install.
- `paper-build` remains the build contract, and `paper-build` and `arxiv-submission` require the `LaTeX Toolchain`; `arxiv-submission` requires the built manuscript.
- Wolfram integration status is separate from plan readiness and does not replace `gpd validate plan-preflight <PLAN.md>`.
- **Workflow presets**: use `gpd presets list`, `gpd presets show <preset>`, and `gpd presets apply <preset>` from your normal terminal.
- Missing preset tooling can degrade `write-paper`; it does not block the base GPD install.
- Workflow presets are bundles over the existing config keys only; use `gpd presets list`, `gpd presets show <preset>`, and `gpd presets apply <preset>` from your normal terminal; they do not add a separate persisted preset block. Workflow preset tooling is layered on top of the base install and does not change runtime permission alignment.
- Shared Wolfram capability controls stay on the local CLI: `gpd integrations enable wolfram` and `gpd integrations disable wolfram`.

### Generated Detail Compatibility Notes

Regression checks scan recorded `SUMMARY` frontmatter, convention conflicts, `VERIFICATION` artifacts, and canonical statuses; they do not rerun full verification workflows.

Project-aware technical-analysis lane: `gpd:derive-equation`, `gpd:dimensional-analysis`, `gpd:limiting-cases`, `gpd:numerical-convergence`, `gpd:sensitivity-analysis`, `GPD/analysis/`, `gpd:graph`, and `gpd:error-propagation` are separate commands. Parameter-sweep artifacts under `GPD/sweeps/` are not part of this relaxed current-workspace lane.

Current-workspace durable outputs can be created from a project context or outside a project only when the user supplies an explicit derivation target or explicit file path. Parameter and sensitivity helpers keep their explicit flags visible: `--param`, `--range`, `--target`, and `--params`.

Usage: `gpd:dimensional-analysis notes/dimension-check.md`
Usage: `gpd:limiting-cases notes/limit-check.md`
Usage: `gpd:numerical-convergence data/convergence.csv`
Usage: `gpd:parameter-sweep --param beta --range 0.1:1.0`
Usage: `gpd:compare-experiment data/results.csv`
Usage: `gpd:compare-results GPD/comparisons/baseline.md`
Usage: `gpd:review-knowledge GPD/knowledge/K-example.md`
Usage: `gpd:sensitivity-analysis --target observable --params alpha,beta --method sobol`

## Files & Structure

The literature survey lives under `GPD/literature/`, and reviewed knowledge docs live under `GPD/knowledge/` with review artifacts in `GPD/knowledge/reviews/`.

```
GPD/
|-- PROJECT.md            # Research question, framework, parameters
|-- REQUIREMENTS.md       # Scoped research requirements with REQ-IDs
|-- ROADMAP.md            # Current phase breakdown
|-- STATE.md              # Project memory & context
|-- MILESTONES.md         # Milestone history
|-- config.json           # Workflow mode & gates
|-- literature/           # Literature survey results and citation artifacts
|   |-- PRIOR-WORK.md     # Established results in the field
|   |-- METHODS.md        # Standard methods and tools
|   |-- COMPUTATIONAL.md  # Computational approaches and tools
|   |-- PITFALLS.md       # Known pitfalls and open problems
|   +-- SUMMARY.md        # Synthesized survey
|-- knowledge/            # Knowledge docs and typed review artifacts
|   |-- K-*.md            # Draft, in_review, stable, or superseded knowledge docs
|   +-- reviews/          # Deterministic review artifacts
|-- research-map/         # Theory map (existing research projects)
|   |-- FORMALISM.md      # Mathematical framework and key equations
|   |-- REFERENCES.md     # Key papers and their relationships
|   |-- ARCHITECTURE.md   # Computation flow and methodology
|   |-- STRUCTURE.md      # Project layout, key files
|   |-- CONVENTIONS.md    # Notation standards, unit systems
|   |-- VALIDATION.md     # Known results for benchmarking
|   +-- CONCERNS.md       # Open questions, known issues
|-- todos/                # Captured ideas and research tasks
|   |-- pending/          # Todos waiting to be worked on
|   +-- done/             # Completed todos
|-- debug/                # Active debug sessions
|   +-- resolved/         # Archived resolved issues
|-- quick/                # Ad-hoc task plans and summaries
|-- milestones/           # Archived milestone data
+-- phases/
    |-- 01-analytical-setup/
    |   |-- 01-01-PLAN.md
    |   |-- 01-01-SUMMARY.md
    |   +-- 01-VERIFICATION.md
    +-- 02-numerical-validation/
        |-- 02-01-PLAN.md
        +-- 02-01-SUMMARY.md
```

## Workflow Modes

GPD keeps you in the loop. Use Supervised for frequent checkpoints, Balanced for fewer routine pauses after you trust the workflow, and YOLO only after runtime permissions are ready.

Set during `gpd:new-project` or changed later with `gpd:settings`:

**Supervised (Recommended)**

- You carry the veto; GPD carries the task
- Checkpoints at every physics-bearing decision so you can redirect early
- Default mode; matches the advisor/graduate-student cadence
- Best for new projects, high-stakes work, or any research where you want to see each step

**Balanced**

- Handles routine work automatically
- Pauses on physics decisions, ambiguities, blockers, or scope changes
- Lighter checkpoint cadence for users who have built intuition for GPD's boundary
- Good for unattended runs once you trust GPD's boundary on your specific research

**YOLO**

- Fastest and least interactive
- Auto-approves checkpoints and keeps going unless a hard stop fires
- Best when you want maximum speed and minimal interruptions
- Use only after `gpd:settings` reports runtime permissions are synchronized and no relaunch is still required

Change anytime with `gpd:settings`. If it says a relaunch is required, the new autonomy level is not unattended-ready yet.

## Planning Configuration

Configure how planning artifacts are managed in `GPD/config.json`:

**`planning.commit_docs`** (default: `true`)

- `true`: Planning artifacts committed to git (standard workflow)
- `false`: Planning artifacts kept local-only, not committed

When `planning.commit_docs: false`:

- Add `GPD/` to your `.gitignore`
- Useful for collaborative projects, shared repos, or keeping planning private
- All planning files still work normally, just not tracked in git

When `planning.commit_docs: true`:

- Keep `GPD/` tracked
- Add `GPD/state.json.bak` and `GPD/state.json.lock` to `.gitignore` so local recovery/coordination files do not linger as untracked noise

Example config:

```json
{
  "execution": {
    "review_cadence": "dense"
  },
  "planning": {
    "commit_docs": false
  }
}
```

## Common Workflows

**Starting a new research project:**

```text
gpd:new-project        # Unified flow: questioning -> survey -> discuss -> objectives -> roadmap
# Start a fresh context window, then run:
gpd:discuss-phase 1    # Gather context and clarify approach
# Start a fresh context window, then run:
gpd:plan-phase 1       # Create plans for first phase
# Start a fresh context window, then run:
gpd:execute-phase 1    # Execute all plans in phase
```

**Fast project bootstrap (skip deep questioning):**

```text
gpd:new-project --minimal              # One structured intake plus scope approval
gpd:new-project --minimal @plan.md     # Parse a plan file, then repair/approve scope
```

**Leaving and returning after a break:**

```text
gpd:pause-work        # Before leaving mid-phase, capture a continuation handoff artifact
# Start a fresh context window, then run gpd resume in your normal terminal for the current workspace
gpd resume             # Current-workspace read-only recovery snapshot from your normal terminal
gpd resume --recent    # Find the workspace first in your normal terminal when you need to reopen a different one
gpd:resume-work       # Continue in-runtime from the reopened project's canonical state after reopening that workspace
gpd:suggest-next      # Fastest post-resume next command when you only need the next action
gpd:progress --brief  # Short orientation snapshot if you need more context
```

**Normal terminal, read-only recovery snapshot:**

```text
gpd resume
```

**Normal terminal, read-only machine-local usage / cost summary:**

```text
gpd cost
```

Read-only machine-local usage / cost summary from recorded local telemetry, optional USD budget guardrails, and the current profile tier mix; advisory only, not live budget enforcement or provider billing truth. If telemetry is missing, the USD view stays partial or estimated rather than exact.

**Adding urgent mid-milestone work:**

```text
gpd:insert-phase 5 "Fix sign error in renormalization group equation"
gpd:plan-phase 5.1
gpd:execute-phase 5.1
```

**Completing a milestone:**

```text
gpd:complete-milestone v2.0
# Start a fresh context window, then run:
gpd:new-milestone  # Start next milestone (questioning -> survey -> objectives -> roadmap)
```

**Capturing ideas during work:**

```text
gpd:add-todo                                      # Capture from conversation context
gpd:add-todo Check finite-size scaling exponent    # Capture with explicit description
gpd:check-todos                                    # Review and work on todos
gpd:check-todos numerical                          # Filter by area
```

## Getting Help

- Read `GPD/PROJECT.md` for research question and framework
- Read `GPD/STATE.md` for current context and key results
- Check `GPD/ROADMAP.md` for phase status
- Run `gpd:progress` to check where you are
- Run `gpd:start` when you need the safest route for this folder
- Run `gpd:suggest-next` when you only need the next action
  </reference>

<success_criteria>
- [ ] Available commands listed with descriptions
- [ ] Common workflows shown with examples
- [ ] Quick reference table presented
- [ ] Static reference stays project-independent; current-state routing is delegated to `gpd:start`, `gpd:progress`, or `gpd:suggest-next`
</success_criteria>
