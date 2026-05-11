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

The full generated command detail reference is installed at `{GPD_INSTALL_DIR}/references/help/detailed-command-reference.md`; the runtime bridge serves that detail one command at a time.

Current-workspace durable outputs can be created from a project context or outside a project only when the user supplies an explicit derivation target or explicit file path. Parameter and sensitivity helpers keep their explicit flags visible: `--param`, `--range`, `--target`, and `--params`.

**`gpd:new-project`**
Initialize a new physics research project with deep context gathering and PROJECT.md

- `gpd:new-project --minimal`
- `gpd:new-project --minimal @file.md`
- `gpd:new-project --auto`

Documented variants:
- `gpd:new-project --minimal`

Notes:
- All modes build a scoping contract before downstream artifacts.
- Blocking gaps get one targeted repair prompt, and scope must be explicitly approved before requirements or roadmap generation.
- `--minimal @file.md` still repairs blocking gaps and asks for scoping approval.
- `--auto` follows the configured autonomy gates.
- `GPD/state.json.bak` and `GPD/state.json.lock` are local recovery/coordination files.

**`gpd:map-research`**
Map existing research project — theoretical framework, computations, conventions, and open questions

**`gpd:resume-work`**
Resume research from previous session with full context restoration

Notes:
- `state.json.continuation` is the durable authority. Canonical continuation fields define the public resume vocabulary: `active_resume_kind`, `active_resume_origin`, `active_resume_pointer`, `active_bounded_segment`, `derived_execution_head`, `active_resume_result`, `continuity_handoff_file`, `recorded_continuity_handoff_file`, `missing_continuity_handoff_file`, `resume_candidates`.

**`gpd:pause-work`**
Create continuation handoff when pausing research mid-phase

**`gpd:progress [--brief | --full | --reconcile]`**
Check research progress, show context, and route to next action (execute or plan)

- `gpd:progress --full`
- `gpd:progress --brief`
- `gpd:progress --reconcile`

Notes:
- The local CLI `gpd progress` is a read-only renderer with `json|bar|table` output. Local CLI: `gpd progress json|bar|table`.

**`gpd:suggest-next`**
Suggest the most impactful next action based on current project state

**`gpd:explain [concept, result, method, notation, or paper]`**
Explain a physics concept rigorously in the context of the active project or a standalone question with an explicit topic

- `gpd:explain "Ward identity"`

**`gpd:discover [phase or topic] [--depth quick|medium|deep]`**
Run discovery phase to investigate methods, literature, and approaches before planning

- `gpd:discover --depth medium "finite-size scaling"`

Notes:
- Depth quick is verification-only and writes no file; medium and deep write discovery artifacts.
- Discovery artifacts feed planning or standalone analysis.

**`gpd:show-phase <phase-number>`**
Inspect a single phase's artifacts, status, and results

**`gpd:plan-phase [phase] [--research] [--skip-research] [--gaps] [--skip-verify] [--light] [--inline-discuss]`**
Create detailed execution plan for a phase (PLAN.md) with verification loop

Notes:
- `--skip-verify` may skip routine verification, but proof-bearing plans still require checker review or an equivalent main-context audit.

**`gpd:execute-phase <phase-number> [--gaps-only]`**
Execute all plans in a phase with wave-based parallelization

**`gpd:verify-work [phase] [--dimensional] [--limits] [--convergence] [--regression] [--all]`**
Verify research results through physics consistency checks

**`gpd:derive-equation [equation or topic to derive]`**
Perform a rigorous physics derivation with systematic verification at each step

- `gpd:derive-equation "effective mass from self-energy"`

Notes:
- Part of the project-aware technical-analysis lane for explicit current-workspace derivations.

**`gpd:dimensional-analysis [phase number or file path]`**
Systematic dimensional analysis audit on all equations in a derivation or phase

- `gpd:dimensional-analysis results/01-SUMMARY.md`

Notes:
- Part of the project-aware technical-analysis lane; analysis artifacts belong under GPD/analysis/ when a standalone target is supplied.

**`gpd:limiting-cases [phase number or file path]`**
Systematically identify and verify all relevant limiting cases for a result or phase

- `gpd:limiting-cases results/01-SUMMARY.md`

Notes:
- Part of the project-aware technical-analysis lane for explicit current-workspace limit checks.

**`gpd:numerical-convergence [phase number or file path]`**
Systematic convergence testing for numerical physics computations

- `gpd:numerical-convergence results/mesh-study.csv`

Notes:
- Part of the project-aware technical-analysis lane for explicit current-workspace convergence checks.

**`gpd:parameter-sweep [phase | computation anchor] [--param name --range start:end:steps] [--adaptive] [--log]`**
Systematic parameter sweep with parallel execution and result aggregation

- `gpd:parameter-sweep --param beta --range 0.1:1.0`

**`gpd:compare-experiment [prediction, dataset, phase, or comparison target]`**
Systematically compare theoretical predictions with experimental or observational data

- `gpd:compare-experiment data/results.csv`

**`gpd:compare-results [phase, artifact, or comparison target]`**
Compare internal results, baselines, or methods and emit decisive verdicts

- `gpd:compare-results GPD/comparisons/baseline.md`

Notes:
- Writes a decisive comparison artifact under GPD/comparisons/ for the current workspace.

**`gpd:sensitivity-analysis [--target quantity] [--params p1,p2,...] [--method analytical|numerical]`**
Systematic sensitivity analysis -- which parameters matter most and how uncertainties propagate

- `gpd:sensitivity-analysis --target observable --params alpha,beta --method sobol`

Notes:
- Part of the project-aware technical-analysis lane for ranking influential inputs from project context or explicit current-workspace flags.

**`gpd:graph`**
Visualize dependency graph across phases and identify gaps

Notes:
- Complements the technical-analysis lane; use separate commands such as gpd:error-propagation for uncertainty flow.

**`gpd:error-propagation [--target quantity] [--phase-range start:end]`**
Track how uncertainties propagate through multi-step calculations across phases

**`gpd:digest-knowledge [topic|arXiv id|source file|knowledge path]`**
Create or update a draft knowledge document in the current workspace from a topic, source file, arXiv ID, or canonical knowledge path

- `gpd:digest-knowledge "renormalization group fixed points"`
- `gpd:digest-knowledge 2401.12345v2`
- `gpd:digest-knowledge hep-th/9901001`
- `gpd:digest-knowledge ./notes/rg-notes.md`
- `gpd:digest-knowledge ./sources/review.docx`
- `gpd:digest-knowledge ./data/observables.csv`
- `gpd:digest-knowledge GPD/knowledge/K-renormalization-group-fixed-points.md`

Notes:
- Creates a current-workspace knowledge document draft from a topic, paper, source file, or explicit knowledge path.
- Example document source: `gpd:digest-knowledge ./sources/review.docx`; example tabular source: `gpd:digest-knowledge ./data/observables.csv`.
- Knowledge lifecycle states are draft, in_review, stable, and superseded; use gpd:review-knowledge for approval.
- Stable knowledge enters shared runtime reference surfaces as reviewed background synthesis; it is a separate authority tier and does not override stronger evidence.
- Resolves one canonical `GPD/knowledge/{knowledge_id}.md` target in the current workspace and stops on ambiguity.
- Supports an arXiv identifier with accepted prefixes.

**`gpd:review-knowledge [knowledge path or knowledge id]`**
Review a current-workspace knowledge document for approval, changes, or promotion gating

- `gpd:review-knowledge GPD/knowledge/K-example.md`

Notes:
- Reviews a canonical current-workspace knowledge document using typed approval evidence.
- Approval can promote stable knowledge; stable and superseded states remain addressable and traceable by canonical path or knowledge id.
- Writes review artifacts under GPD/knowledge/reviews/.

**`gpd:literature-review [topic or research question]`**
Structured literature review for a physics research topic with citation network analysis and open question identification

- `gpd:literature-review "holographic superconductors"`

Notes:
- Runs on the current project or an explicit topic: a physics research topic or research question, and writes under GPD/literature/ in the current workspace.

**`gpd:write-paper [--intake path/to/write-paper-authoring-input.json]`**
Structure and write a physics paper from project research results or a bounded external-authoring intake

- `gpd:write-paper`
- `gpd:write-paper --intake intake/write-paper-authoring-input.json`

Notes:
- Uses a bounded external-authoring lane driven by an explicit intake manifest only.
- GPD-authored outputs live under `GPD/publication/{subject_slug}/...`; `GPD/publication/{subject_slug}/intake/` stores intake/provenance state only.
- It does not mine arbitrary folders, and embedded external staged-review parity is out of scope.
- Project-backed review/response/package outputs remain in the resolved GPD manuscript lane.

**`gpd:peer-review [paper directory | manuscript path | explicit artifact path]`**
Conduct a staged six-pass peer review of a manuscript and supporting research artifacts from the current GPD project or an explicit external artifact

- `gpd:peer-review draft.docx`
- `gpd:peer-review data/observables.csv`

Notes:
- Explicit artifact intake follows command-policy supported suffixes for publication-artifact paths.
- Use `gpd validate artifact-text <path> --output <txt-path>` when explicit artifact text extraction is needed.
- Project-backed mode uses the resolved manuscript entrypoint before staged review.

**`gpd:respond-to-referees [--manuscript PATH --report PATH | report path | paste]`**
Structure a point-by-point response to referee reports for an explicit manuscript target or the current GPD manuscript

- `gpd:respond-to-referees --manuscript paper/main.tex --report reports/referee-report.md`
- `gpd:respond-to-referees reports/referee-report.md`
- `gpd:respond-to-referees paste`

Notes:
- Uses a bounded external-authoring lane when an explicit intake manifest or subject is allowed by command policy.
- Project-backed review/response/package outputs stay under the resolved manuscript root; this is not a full publication-root migration.

**`gpd:arxiv-submission [manuscript root or .tex entrypoint]`**
Prepare a GPD-owned manuscript for arXiv submission with validation and packaging

- `gpd:arxiv-submission paper/`

Notes:
- Packages the GPD-owned manuscript root or a supported .tex entrypoint; it does not package arbitrary external material.

**`gpd:settings`**
Configure autonomy, unattended execution budgets, runtime permission sync, workflow preset bundles, model-cost posture, runtime-specific tier model overrides, review cadence, and git preferences

Notes:
- Autonomy vocabulary: Supervised, Max quality, Balanced, Budget-aware, runtime defaults, YOLO.
- Configuration keys include `execution.review_cadence`, `planning.commit_docs`, `git.branching_strategy`, and statuses such as `needs-calculation`; model tiers are `tier-1`, `tier-2`, and `tier-3`.
- Use `gpd observe execution` and `gpd cost` from the normal terminal for read-only status and usage review.

**`gpd:route [--frozen=yes|no] [--change=extend|revise] [--layer=new|change]`**
Decide whether a scope change is a new phase, a revision, a new milestone, or a milestone completion

Notes:
- The frozen scope-expansion path renders the ordered compound sequence `gpd:complete-milestone` then `gpd:new-milestone`.

**`gpd:record-backtrack [--reverted-commit=<sha>] [--trigger=<text>] [--phase=<NN-slug>] [description]`**
Record a backtrack event (what went wrong, what got reverted) to the backtracks ledger

**`gpd:compact-state [--force]`**
Archive historical entries from STATE.md to keep it under the 150-line target

Notes:
- Suggested by `gpd:progress` when STATE.md grows large.

**`gpd:update`**
Update GPD to latest version with changelog display

Notes:
- Runs the public bootstrap update command for the active runtime.
- Preserves local modifications via patch backups.
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
