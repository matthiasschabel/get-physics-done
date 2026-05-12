"""Registry-backed rendering helpers for the public GPD help surface."""

from __future__ import annotations

import dataclasses
import textwrap
from functools import lru_cache
from typing import TypeAlias

from gpd.command_labels import canonical_command_label, parse_command_label, rewrite_runtime_command_surfaces_to_public
from gpd.core.public_surface_contract import (
    beginner_startup_ladder,
    beginner_startup_ladder_text,
    local_cli_cost_command,
    local_cli_observe_execution_command,
    local_cli_resume_command,
    local_cli_resume_recent_command,
)
from gpd.registry import get_command, list_commands

CommandGroupPayload: TypeAlias = dict[str, object]
CommandEntryPayload: TypeAlias = dict[str, str]

DETAILED_HELP_FOLLOW_UP = "Use `gpd:help --command <name>` when you want detailed notes for one runtime command."


@dataclasses.dataclass(frozen=True, slots=True)
class HelpCommandEntry:
    """One compact command-index row."""

    command: str
    description: str
    registry_command: str
    documented_variant: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class HelpCommandGroup:
    """One compact command-index group."""

    name: str
    commands: tuple[HelpCommandEntry, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class HelpCommandDetail:
    """Compact registry metadata used by machine-readable help consumers."""

    canonical_command: str
    slug: str
    description: str
    argument_hint: str
    context_mode: str
    project_reentry_capable: bool
    signature: str
    group: str
    documented_variants: list[str]
    allowed_tools: list[str]
    requires: dict[str, object]

    def as_payload(self) -> dict[str, object]:
        return dataclasses.asdict(self)


_CommandEntrySpec = tuple[str, str] | tuple[str, str, str]
_CommandGroupSpec = tuple[str, tuple[_CommandEntrySpec, ...]]

_COMMAND_GROUP_SPECS: tuple[_CommandGroupSpec, ...] = (
    (
        "Starter commands",
        (
            ("gpd:help", "Show the quick start or command index"),
            ("gpd:start", "Guided first-run router for the safest first path in the current folder"),
            ("gpd:tour", "Show a read-only overview of the main commands"),
            ("gpd:new-project", "Create a full GPD project"),
            (
                "gpd:new-project --minimal",
                "Create a GPD project through the shortest setup path",
                "gpd:new-project",
            ),
            ("gpd:map-research", "Map an existing research folder before planning"),
            ("gpd:resume-work", "Resume the selected project's canonical state inside the runtime"),
            ("gpd:progress", "Review project status and likely next steps"),
            ("gpd:suggest-next", "Ask only for the next best action"),
            ("gpd:explain [concept]", "Explain a concept, method, result, or paper"),
            ("gpd:quick", "Run one small bounded task without the full phase workflow"),
        ),
    ),
    (
        "Planning and execution",
        (
            ("gpd:discuss-phase <number>", "Capture phase context before planning"),
            ("gpd:research-phase <number>", "Run a focused phase literature survey"),
            ("gpd:list-phase-assumptions <number>", "Preview the planned phase approach"),
            (
                "gpd:discover [phase or topic]",
                "Survey methods, literature, and tools before planning; `quick` is verification-only",
            ),
            ("gpd:show-phase <number>", "Inspect one phase's artifacts and status"),
            (
                "gpd:route [--frozen=yes|no] [--change=extend|revise] [--layer=new|change]",
                "Route a scope change to the right milestone/phase workflow",
            ),
            ("gpd:plan-phase <number>", "Build a detailed execution plan for a phase"),
            ("gpd:execute-phase <phase-number> [--gaps-only]", "Run all plans in a phase, or only gap-closure plans"),
            (
                "gpd:autonomous [--from N]",
                "Run all remaining phases autonomously (discuss→plan→execute→verify each)",
            ),
            (
                "gpd:derive-equation",
                "Run a rigorous derivation workflow from project context or one explicit current-workspace target",
            ),
        ),
    ),
    (
        "Roadmap and milestones",
        (
            ("gpd:add-phase <description>", "Append a new phase to the roadmap"),
            ("gpd:insert-phase <after> <description>", "Insert urgent work between phases"),
            ("gpd:remove-phase <number>", "Remove a future phase and renumber later ones"),
            ('gpd:revise-phase <number> "<reason>"', "Supersede a completed phase with a replacement"),
            ("gpd:merge-phases <source> <target>", "Fold one phase's results into another"),
            ("gpd:new-milestone <name>", "Start the next milestone"),
            ("gpd:complete-milestone <version>", "Archive a completed milestone"),
        ),
    ),
    (
        "Validation and analysis",
        (
            ("gpd:verify-work [phase]", "Run physics verification checks"),
            ("gpd:debug [issue description]", "Start a persistent debug session"),
            (
                "gpd:dimensional-analysis",
                "Check dimensional consistency for a project phase or one explicit current-workspace file",
            ),
            ("gpd:limiting-cases", "Check known limits for a project phase or one explicit current-workspace file"),
            (
                "gpd:numerical-convergence",
                "Run convergence checks for a project phase or one explicit current-workspace artifact",
            ),
            ("gpd:compare-experiment", "Compare results against external data"),
            (
                "gpd:compare-results",
                "Compare internal results or baselines and write the verdict under `GPD/comparisons/`",
            ),
            ("gpd:validate-conventions [phase]", "Check notation and convention consistency"),
            ("gpd:regression-check [phase]", "Scan for regressions in recorded verification state"),
            ("gpd:health", "Run project health checks"),
            ("gpd:parameter-sweep [phase | computation anchor]", "Run a structured parameter sweep"),
            (
                "gpd:sensitivity-analysis",
                "Rank which inputs matter most from project context or explicit current-workspace flags",
            ),
            ("gpd:error-propagation", "Track uncertainties through a calculation chain"),
        ),
    ),
    (
        "Knowledge authoring",
        (
            (
                "gpd:digest-knowledge [topic|arXiv id|source file|knowledge path]",
                "Create or update a draft knowledge doc under `GPD/knowledge/` in the current workspace",
            ),
            (
                "gpd:review-knowledge [knowledge path|knowledge id]",
                "Review one canonical current-workspace knowledge doc and write its review artifact",
            ),
        ),
    ),
    (
        "Writing and publication",
        (
            (
                "gpd:literature-review [topic or research question]",
                "Create a structured literature review under `GPD/literature/` in the current workspace",
            ),
            (
                "gpd:write-paper [--intake path/to/write-paper-authoring-input.json]",
                "Draft a paper from current project results or one explicit external-authoring intake manifest into the resolved manuscript lane",
            ),
            (
                "gpd:peer-review [paper directory | manuscript path | explicit artifact path]",
                "Run the staged review workflow on the current project manuscript or one explicit artifact",
            ),
            (
                "gpd:respond-to-referees [--manuscript PATH --report PATH | report path | paste]",
                "Draft referee responses and revise the resolved manuscript root",
            ),
            (
                "gpd:arxiv-submission [manuscript root or .tex entrypoint]",
                "Package a built manuscript for arXiv from the resolved GPD-owned manuscript root or entrypoint",
            ),
            ("gpd:slides [topic, audience, or source path]", "Create presentation slides"),
        ),
    ),
    (
        "Tangents, memory, and exports",
        (
            (
                "gpd:tangent [description]",
                "Chooser for stay / quick / defer / branch when a side investigation appears",
            ),
            ("gpd:branch-hypothesis <description>", "Explicit git-backed alternative path for a side investigation"),
            ("gpd:compare-branches", "Compare results across hypothesis branches"),
            ("gpd:pause-work", "Save a continuation handoff before stepping away"),
            ("gpd:add-todo [description]", "Capture a task or idea"),
            ("gpd:check-todos [area]", "Review pending todos and pick one"),
            ("gpd:decisions [phase or keyword]", "Search the decision log"),
            ("gpd:graph", "Visualize phase dependencies"),
            (
                "gpd:export [--format html|latex|zip|all] [--commit]",
                "Export project artifacts; generated text exports are committed only with explicit `--commit`",
            ),
            (
                "gpd:export-logs [--format jsonl|json|markdown] [--session <id>] [--last N] "
                "[--command <label>] [--phase <phase>] [--category <name>] [--no-traces] [--output-dir <path>]",
                "Export observability logs",
            ),
            ("gpd:error-patterns [category]", "Review common project-specific errors"),
            (
                "gpd:record-backtrack [--reverted-commit=<sha>] [--trigger=<text>] [--phase=<NN-slug>] [description]",
                "Capture a backtrack event (what went wrong, what got reverted)",
            ),
            ("gpd:record-insight [description]", "Save a project-specific lesson"),
            ("gpd:audit-milestone [version]", "Audit milestone completion against goals"),
            ("gpd:plan-milestone-gaps", "Turn audit gaps into new phases"),
        ),
    ),
    (
        "Configuration and maintenance",
        (
            (
                "gpd:settings",
                "Guided autonomy, permissions, and runtime configuration after your first successful start or later",
            ),
            ("gpd:set-tier-models", "Directly pin concrete tier model ids"),
            ("gpd:set-profile <profile>", "Switch the abstract model profile"),
            ("gpd:compact-state", "Archive old `STATE.md` entries"),
            ("gpd:sync-state", "Repair diverged `STATE.md` and `state.json`"),
            ("gpd:undo", "Roll back the last GPD operation with a safety checkpoint"),
            ("gpd:update", "Update GPD to the latest version"),
            ("gpd:reapply-patches", "Reapply local modifications after updating"),
        ),
    ),
)

_ADDITIONAL_QUICK_START_RUNTIME_COMMANDS = (
    "gpd:progress",
    "gpd:suggest-next",
    "gpd:settings",
    "gpd:set-tier-models",
    "gpd:tangent",
    "gpd:branch-hypothesis",
)

_COMMAND_DETAIL_SIGNATURE_OVERRIDES: dict[str, str] = {
    "gpd:compare-results": "gpd:compare-results [phase, artifact, or comparison target]",
    "gpd:discover": "gpd:discover [phase or topic] [--depth quick|medium|deep]",
    "gpd:digest-knowledge": "gpd:digest-knowledge [topic|arXiv id|source file|knowledge path]",
    "gpd:map-research": "gpd:map-research",
    "gpd:new-project": "gpd:new-project",
    "gpd:peer-review": "gpd:peer-review [paper directory | manuscript path | explicit artifact path]",
    "gpd:respond-to-referees": "gpd:respond-to-referees [--manuscript PATH --report PATH | report path | paste]",
    "gpd:review-knowledge": "gpd:review-knowledge [knowledge path or knowledge id]",
}

_COMMAND_DETAIL_USAGE_EXAMPLES: dict[str, tuple[str, ...]] = {
    "gpd:arxiv-submission": ("gpd:arxiv-submission paper/",),
    "gpd:compare-experiment": ("gpd:compare-experiment data/results.csv",),
    "gpd:compare-results": ("gpd:compare-results GPD/comparisons/baseline.md",),
    "gpd:derive-equation": ('gpd:derive-equation "effective mass from self-energy"',),
    "gpd:digest-knowledge": (
        'gpd:digest-knowledge "renormalization group fixed points"',
        "gpd:digest-knowledge 2401.12345v2",
        "gpd:digest-knowledge hep-th/9901001",
        "gpd:digest-knowledge ./notes/rg-notes.md",
        "gpd:digest-knowledge ./sources/review.docx",
        "gpd:digest-knowledge ./data/observables.csv",
        "gpd:digest-knowledge GPD/knowledge/K-renormalization-group-fixed-points.md",
    ),
    "gpd:dimensional-analysis": ("gpd:dimensional-analysis results/01-SUMMARY.md",),
    "gpd:discover": ('gpd:discover --depth medium "finite-size scaling"',),
    "gpd:error-patterns": ("gpd:error-patterns sign-error",),
    "gpd:export": ("gpd:export --format latex --commit",),
    "gpd:export-logs": ("gpd:export-logs --command execute-phase --phase 3 --category workflow",),
    "gpd:explain": ('gpd:explain "Ward identity"',),
    "gpd:limiting-cases": ("gpd:limiting-cases results/01-SUMMARY.md",),
    "gpd:literature-review": ('gpd:literature-review "holographic superconductors"',),
    "gpd:new-project": (
        "gpd:new-project --minimal",
        "gpd:new-project --minimal @file.md",
        "gpd:new-project --auto",
    ),
    "gpd:numerical-convergence": ("gpd:numerical-convergence results/mesh-study.csv",),
    "gpd:parameter-sweep": ("gpd:parameter-sweep --param beta --range 0.1:1.0",),
    "gpd:peer-review": (
        "gpd:peer-review draft.docx",
        "gpd:peer-review data/observables.csv",
    ),
    "gpd:progress": (
        "gpd:progress --full",
        "gpd:progress --brief",
        "gpd:progress --reconcile",
    ),
    "gpd:respond-to-referees": (
        "gpd:respond-to-referees --manuscript paper/main.tex --report reports/referee-report.md",
        "gpd:respond-to-referees reports/referee-report.md",
        "gpd:respond-to-referees paste",
    ),
    "gpd:review-knowledge": ("gpd:review-knowledge GPD/knowledge/K-example.md",),
    "gpd:sensitivity-analysis": ("gpd:sensitivity-analysis --target observable --params alpha,beta --method sobol",),
    "gpd:write-paper": (
        "gpd:write-paper",
        "gpd:write-paper --intake intake/write-paper-authoring-input.json",
    ),
}

_COMMAND_DETAIL_NOTES: dict[str, tuple[str, ...]] = {
    "gpd:arxiv-submission": (
        "Packages the GPD-owned manuscript root or a supported .tex entrypoint; it does not package arbitrary external material.",
    ),
    "gpd:compact-state": ("Suggested by `gpd:progress` when STATE.md grows large.",),
    "gpd:compare-results": ("Writes a decisive comparison artifact under GPD/comparisons/ for the current workspace.",),
    "gpd:derive-equation": (
        "Part of the project-aware technical-analysis lane for explicit current-workspace derivations.",
    ),
    "gpd:dimensional-analysis": (
        "Part of the project-aware technical-analysis lane; analysis artifacts belong under GPD/analysis/ when a standalone target is supplied.",
    ),
    "gpd:discover": (
        "Depth quick is verification-only and writes no file; medium and deep write discovery artifacts.",
        "Discovery artifacts feed planning or standalone analysis.",
    ),
    "gpd:digest-knowledge": (
        "Creates a current-workspace knowledge document draft from a topic, paper, source file, or explicit knowledge path.",
        "Example document source: `gpd:digest-knowledge ./sources/review.docx`; example tabular source: `gpd:digest-knowledge ./data/observables.csv`.",
        "Knowledge lifecycle states are draft, in_review, stable, and superseded; use gpd:review-knowledge for approval.",
        "Stable knowledge enters shared runtime reference surfaces as reviewed background synthesis; it is a separate authority tier and does not override stronger evidence.",
        "Resolves one canonical `GPD/knowledge/{knowledge_id}.md` target in the current workspace and stops on ambiguity.",
        "Supports an arXiv identifier with accepted prefixes.",
    ),
    "gpd:error-patterns": (
        "Pattern-library categories include sign-error, factor-error, convention-pitfall, convergence-issue, approximation-failure, numerical-instability, conceptual-error, and dimensional-error.",
    ),
    "gpd:export": (
        "For generated text exports, outputs are committed only with explicit `--commit`.",
        "gpd observe execution, gpd observe sessions, gpd observe show, and gpd trace show inspect only; gpd observe event, gpd observe export, and gpd trace start|log|stop write observability.",
    ),
    "gpd:export-logs": (
        "Exports observability logs with passthrough filters such as --command <label>, --phase <phase>, and --category <name>.",
        "Empty result payloads report empty_export: true.",
    ),
    "gpd:graph": (
        "Complements the technical-analysis lane; use separate commands such as gpd:error-propagation for uncertainty flow.",
    ),
    "gpd:limiting-cases": (
        "Part of the project-aware technical-analysis lane for explicit current-workspace limit checks.",
    ),
    "gpd:literature-review": (
        "Runs on the current project or an explicit topic: a physics research topic or research question, and writes under GPD/literature/ in the current workspace.",
    ),
    "gpd:new-project": (
        "All modes build a scoping contract before downstream artifacts.",
        "Blocking gaps get one targeted repair prompt, and scope must be explicitly approved before requirements or roadmap generation.",
        "`--minimal @file.md` still repairs blocking gaps and asks for scoping approval.",
        "`--auto` follows the configured autonomy gates.",
        "`GPD/state.json.bak` and `GPD/state.json.lock` are local recovery/coordination files.",
    ),
    "gpd:numerical-convergence": (
        "Part of the project-aware technical-analysis lane for explicit current-workspace convergence checks.",
    ),
    "gpd:peer-review": (
        "Explicit artifact intake follows command-policy supported suffixes for publication-artifact paths.",
        "Use `gpd validate artifact-text <path> --output <txt-path>` when explicit artifact text extraction is needed.",
        "Project-backed mode uses the resolved manuscript entrypoint before staged review.",
    ),
    "gpd:plan-phase": (
        "`--skip-verify` may skip routine verification, but proof-bearing plans still require checker review or an equivalent main-context audit.",
    ),
    "gpd:progress": (
        "The local CLI `gpd progress` is a read-only renderer with `json|bar|table` output. Local CLI: `gpd progress json|bar|table`.",
    ),
    "gpd:resume-work": (
        "`state.json.continuation` is the durable authority. Canonical continuation fields define the public resume vocabulary: `active_resume_kind`, `active_resume_origin`, `active_resume_pointer`, `active_bounded_segment`, `derived_execution_head`, `active_resume_result`, `continuity_handoff_file`, `recorded_continuity_handoff_file`, `missing_continuity_handoff_file`, `resume_candidates`.",
    ),
    "gpd:respond-to-referees": (
        "Uses a bounded external-authoring lane when an explicit intake manifest or subject is allowed by command policy.",
        "Project-backed review/response/package outputs stay under the resolved manuscript root; this is not a full publication-root migration.",
    ),
    "gpd:route": (
        "The frozen scope-expansion path renders the ordered compound sequence `gpd:complete-milestone` then `gpd:new-milestone`.",
    ),
    "gpd:review-knowledge": (
        "Reviews a canonical current-workspace knowledge document using typed approval evidence.",
        "Approval can promote stable knowledge; stable and superseded states remain addressable and traceable by canonical path or knowledge id.",
        "Writes review artifacts under GPD/knowledge/reviews/.",
    ),
    "gpd:sensitivity-analysis": (
        "Part of the project-aware technical-analysis lane for ranking influential inputs from project context or explicit current-workspace flags.",
    ),
    "gpd:settings": (
        "Autonomy vocabulary: Supervised, Max quality, Balanced, Budget-aware, runtime defaults, YOLO.",
        "Configuration keys include `execution.review_cadence`, `planning.commit_docs`, `git.branching_strategy`, and statuses such as `needs-calculation`; model tiers are `tier-1`, `tier-2`, and `tier-3`.",
        "Use `gpd observe execution` and `gpd cost` from the normal terminal for read-only status and usage review.",
    ),
    "gpd:update": (
        "Runs the public bootstrap update command for the active runtime.",
        "Preserves local modifications via patch backups.",
    ),
    "gpd:write-paper": (
        "Uses a bounded external-authoring lane driven by an explicit intake manifest only.",
        "GPD-authored outputs live under `GPD/publication/{subject_slug}/...`; `GPD/publication/{subject_slug}/intake/` stores intake/provenance state only.",
        "It does not mine arbitrary folders, and embedded external staged-review parity is out of scope.",
        "Project-backed review/response/package outputs remain in the resolved GPD manuscript lane.",
    ),
}

_ROOT_DETAILED_REFERENCE_COMMANDS: tuple[str, ...] = (
    "gpd:new-project",
    "gpd:map-research",
    "gpd:resume-work",
    "gpd:pause-work",
    "gpd:progress",
    "gpd:suggest-next",
    "gpd:explain",
    "gpd:discover",
    "gpd:show-phase",
    "gpd:plan-phase",
    "gpd:execute-phase",
    "gpd:verify-work",
    "gpd:derive-equation",
    "gpd:dimensional-analysis",
    "gpd:limiting-cases",
    "gpd:numerical-convergence",
    "gpd:parameter-sweep",
    "gpd:compare-experiment",
    "gpd:compare-results",
    "gpd:sensitivity-analysis",
    "gpd:graph",
    "gpd:error-propagation",
    "gpd:digest-knowledge",
    "gpd:review-knowledge",
    "gpd:literature-review",
    "gpd:write-paper",
    "gpd:peer-review",
    "gpd:respond-to-referees",
    "gpd:arxiv-submission",
    "gpd:settings",
    "gpd:route",
    "gpd:record-backtrack",
    "gpd:compact-state",
    "gpd:update",
)


def _runtime_command_for_ladder_step(step: str) -> tuple[str, ...]:
    return tuple(f"gpd:{part.strip()}" for part in step.split("/") if part.strip())


def _startup_ladder_runtime_command_map(ladder: tuple[str, ...]) -> dict[str, str]:
    commands: dict[str, str] = {}
    for step in ladder:
        for command in _runtime_command_for_ladder_step(step):
            commands[parse_command_label(command).slug] = command
    return commands


def _required_ladder_command(commands: dict[str, str], slug: str) -> str:
    try:
        return commands[slug]
    except KeyError as exc:
        raise ValueError(f"beginner startup ladder must include {slug!r}") from exc


def _format_ladder_step_as_runtime_commands(step: str, *, public_prefix: str = "gpd:") -> str:
    commands = _runtime_command_for_ladder_step(step)
    if not commands:
        raise ValueError("beginner startup ladder steps must contain at least one command")
    return " or ".join(f"`{_apply_public_prefix(command, public_prefix=public_prefix)}`" for command in commands)


def _runtime_ladder_sentence(ladder: tuple[str, ...], *, public_prefix: str = "gpd:") -> str:
    command_fragments = tuple(
        _format_ladder_step_as_runtime_commands(step, public_prefix=public_prefix) for step in ladder
    )
    if len(command_fragments) < 2:
        raise ValueError("beginner startup ladder must contain at least two steps")
    return (
        "In runtime terms, that means "
        + ", then ".join(command_fragments[:-1])
        + f", and later {command_fragments[-1]} when you return."
    )


def _quick_start_runtime_commands() -> tuple[str, ...]:
    ladder_commands = tuple(
        command for step in beginner_startup_ladder() for command in _runtime_command_for_ladder_step(step)
    )
    return (*ladder_commands, *_ADDITIONAL_QUICK_START_RUNTIME_COMMANDS)


def _entry_registry_command(spec: _CommandEntrySpec) -> str:
    command = spec[0]
    if len(spec) == 3:
        return spec[2]
    return canonical_command_label(command)


def _entry_from_spec(spec: _CommandEntrySpec) -> HelpCommandEntry:
    registry_command = _entry_registry_command(spec)
    get_command(registry_command)
    return HelpCommandEntry(
        command=spec[0],
        description=spec[1],
        registry_command=registry_command,
        documented_variant=len(spec) == 3,
    )


def _base_command_entries_by_label() -> dict[str, tuple[str, HelpCommandEntry]]:
    entries: dict[str, tuple[str, HelpCommandEntry]] = {}
    for group in help_command_groups():
        for entry in group.commands:
            if entry.documented_variant:
                continue
            entries[entry.registry_command] = (group.name, entry)
    return entries


def _documented_variants_for(registry_command: str) -> tuple[str, ...]:
    return tuple(
        entry.command
        for group in help_command_groups()
        for entry in group.commands
        if entry.documented_variant and entry.registry_command == registry_command
    )


def _display_signature_for_command(registry_command: str) -> str:
    if registry_command in _COMMAND_DETAIL_SIGNATURE_OVERRIDES:
        return _COMMAND_DETAIL_SIGNATURE_OVERRIDES[registry_command]
    command = get_command(registry_command)
    if command.argument_hint:
        return f"{command.name} {command.argument_hint}"
    entries = _base_command_entries_by_label()
    entry = entries.get(registry_command, (None, None))[1]
    return entry.command if entry is not None else command.name


def _usage_examples_for(registry_command: str) -> tuple[str, ...]:
    examples = _COMMAND_DETAIL_USAGE_EXAMPLES.get(registry_command, ())
    seen: set[str] = set()
    deduped: list[str] = []
    for example in examples:
        if example in seen:
            continue
        seen.add(example)
        deduped.append(example)
    return tuple(deduped)


def _format_sequence(values: list[str] | tuple[str, ...], *, limit: int = 4) -> str:
    cleaned = [value for value in values if value]
    if not cleaned:
        return ""
    shown = cleaned[:limit]
    suffix = "" if len(cleaned) <= limit else f", and {len(cleaned) - limit} more"
    return ", ".join(f"`{value}`" for value in shown) + suffix


def _requires_summary(requires: dict[str, object]) -> tuple[str, ...]:
    lines: list[str] = []
    for key in sorted(requires):
        value = requires[key]
        if isinstance(value, list):
            rendered = _format_sequence([str(item) for item in value])
            if rendered:
                lines.append(f"{key}: {rendered}")
            continue
        if isinstance(value, tuple):
            rendered = _format_sequence(tuple(str(item) for item in value))
            if rendered:
                lines.append(f"{key}: {rendered}")
            continue
        if value not in (None, "", [], {}):
            lines.append(f"{key}: `{value}`")
    return tuple(lines)


def _command_policy_summary(command_name: str) -> tuple[str, ...]:
    command = get_command(command_name)
    policy = command.command_policy
    if policy is None:
        return ()

    lines: list[str] = []
    subject = policy.subject_policy
    if subject is not None and (
        subject.subject_kind
        or subject.resolution_mode
        or subject.explicit_input_kinds
        or subject.allow_external_subjects is not None
        or subject.bootstrap_allowed is not None
    ):
        parts: list[str] = []
        if subject.subject_kind:
            parts.append(f"subject={subject.subject_kind}")
        if subject.resolution_mode:
            parts.append(f"resolution={subject.resolution_mode}")
        if subject.explicit_input_kinds:
            parts.append("explicit inputs=" + ", ".join(subject.explicit_input_kinds))
        if subject.allow_external_subjects is not None:
            parts.append(f"external subjects allowed={str(subject.allow_external_subjects).lower()}")
        if subject.bootstrap_allowed is not None:
            parts.append(f"bootstrap allowed={str(subject.bootstrap_allowed).lower()}")
        lines.append("Subject policy: " + "; ".join(parts))

    output = policy.output_policy
    if output is not None and (
        output.output_mode or output.managed_root_kind or output.default_output_subtree or output.stage_artifact_policy
    ):
        parts = []
        if output.output_mode:
            parts.append(f"mode={output.output_mode}")
        if output.managed_root_kind:
            parts.append(f"managed root={output.managed_root_kind}")
        if output.default_output_subtree:
            parts.append(f"default subtree={output.default_output_subtree}")
        if output.stage_artifact_policy:
            parts.append(f"stage artifacts={output.stage_artifact_policy}")
        lines.append("Output policy: " + "; ".join(parts))
    return tuple(lines)


def _review_contract_summary(command_name: str) -> tuple[str, ...]:
    command = get_command(command_name)
    contract = command.review_contract
    if contract is None:
        return ()
    lines = [
        (
            f"Review contract: {contract.review_mode} mode with "
            f"{len(contract.required_outputs)} required output(s), "
            f"{len(contract.preflight_checks)} preflight check(s), and "
            f"{len(contract.blocking_conditions)} blocking condition(s)."
        )
    ]
    if contract.scope_variants:
        scopes = ", ".join(variant.scope for variant in contract.scope_variants)
        lines.append(f"Scope variants: {scopes}.")
    return tuple(lines)


def _staged_workflow_summary(command_name: str) -> tuple[str, ...]:
    command = get_command(command_name)
    manifest = command.staged_loading
    if manifest is None:
        return ()
    return (f"Staged workflow: `{manifest.workflow_id}`.",)


@lru_cache(maxsize=1)
def help_command_groups() -> tuple[HelpCommandGroup, ...]:
    """Return compact help groups, validating every base command against the registry."""

    groups = tuple(
        HelpCommandGroup(
            name=group_name,
            commands=tuple(_entry_from_spec(entry_spec) for entry_spec in entry_specs),
        )
        for group_name, entry_specs in _COMMAND_GROUP_SPECS
    )
    registry_commands = set(list_commands(name_format="label"))
    grouped_registry_commands = {
        entry.registry_command for group in groups for entry in group.commands if not entry.documented_variant
    }
    missing = sorted(registry_commands - grouped_registry_commands)
    extra = sorted(grouped_registry_commands - registry_commands)
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing registry commands: {', '.join(missing)}")
        if extra:
            details.append(f"unknown grouped commands: {', '.join(extra)}")
        raise ValueError("; ".join(details))
    return groups


def command_groups_payload() -> list[CommandGroupPayload]:
    """Return raw-help-compatible grouped command metadata."""

    return [
        {
            "name": group.name,
            "commands": [
                {
                    "command": entry.command,
                    "description": entry.description,
                }
                for entry in group.commands
            ],
        }
        for group in help_command_groups()
    ]


def build_help_catalog() -> dict[str, object]:
    """Return renderer-owned help metadata for sync tests and integrations."""

    return {"command_groups": help_command_groups()}


def command_index_payload() -> list[dict[str, str]]:
    """Return compact registry command metadata in stable registry order."""

    return [
        {
            "command": command.name,
            "slug": parse_command_label(command.name).slug,
            "description": command.description,
        }
        for slug in list_commands(name_format="slug")
        for command in (get_command(slug),)
    ]


def command_detail_payload(
    command_name: str,
    *,
    minimal: bool = False,
    include_markdown: bool = False,
) -> dict[str, object]:
    """Return compact registry metadata for one command lookup."""

    command = get_command(canonical_command_label(command_name))
    group_name, _entry = _base_command_entries_by_label()[command.name]
    detail = HelpCommandDetail(
        canonical_command=command.name,
        slug=parse_command_label(command.name).slug,
        description=command.description,
        argument_hint=command.argument_hint,
        context_mode=command.context_mode,
        project_reentry_capable=command.project_reentry_capable,
        signature=_display_signature_for_command(command.name),
        group=group_name,
        documented_variants=list(_documented_variants_for(command.name)),
        allowed_tools=[] if minimal else command.allowed_tools,
        requires={} if minimal else command.requires,
    )
    payload = detail.as_payload()
    if include_markdown:
        payload["detail_markdown"] = render_command_detail_markdown(command.name, include_group_heading=True)
    return payload


def _render_command_detail_block(
    registry_command: str,
    *,
    include_group_heading: bool,
    public_prefix: str,
    include_metadata: bool = True,
) -> str:
    command = get_command(registry_command)
    group_name, _entry = _base_command_entries_by_label()[command.name]
    signature = _apply_public_prefix(_display_signature_for_command(command.name), public_prefix=public_prefix)
    lines: list[str] = []
    if include_group_heading:
        lines.extend((f"### {group_name}", ""))

    lines.extend(
        (
            f"**`{signature}`**",
            command.description.strip(),
        )
    )
    examples = _usage_examples_for(command.name)
    if examples:
        lines.append("")
        lines.extend(f"- `{_apply_public_prefix(example, public_prefix=public_prefix)}`" for example in examples)

    variants = tuple(
        _apply_public_prefix(variant, public_prefix=public_prefix) for variant in _documented_variants_for(command.name)
    )
    if variants:
        lines.extend(("", "Documented variants:"))
        lines.extend(f"- `{variant}`" for variant in variants)

    notes = _COMMAND_DETAIL_NOTES.get(command.name, ())
    if notes:
        lines.extend(("", "Notes:"))
        lines.extend(f"- {note}" for note in notes)

    if include_metadata:
        metadata_lines: list[str] = []
        for require_line in _requires_summary(command.requires):
            metadata_lines.append(f"- Requires {require_line}")
        for policy_line in _command_policy_summary(command.name):
            metadata_lines.append(f"- {policy_line}")
        for review_line in _review_contract_summary(command.name):
            metadata_lines.append(f"- {review_line}")
        for staged_line in _staged_workflow_summary(command.name):
            metadata_lines.append(f"- {staged_line}")
        if metadata_lines:
            lines.extend(("", *metadata_lines))
    return "\n".join(lines).strip()


def _render_root_command_detail_block(
    registry_command: str,
    *,
    public_prefix: str,
) -> str:
    """Render a terse root-help command detail without metadata expansion."""

    command = get_command(registry_command)
    signature = _apply_public_prefix(_display_signature_for_command(command.name), public_prefix=public_prefix)
    lines = [f"**`{signature}`**", command.description.strip()]

    examples = tuple(
        _apply_public_prefix(example, public_prefix=public_prefix) for example in _usage_examples_for(command.name)
    )
    if examples:
        lines.append("Usage: " + "; ".join(f"`{example}`" for example in examples))

    notes = _COMMAND_DETAIL_NOTES.get(command.name, ())
    if notes:
        lines.append("Notes: " + " ".join(notes))

    return "\n".join(lines).strip()


def _apply_public_prefix(text: str, *, public_prefix: str) -> str:
    if public_prefix == "gpd:":
        return text
    return rewrite_runtime_command_surfaces_to_public(text, public_prefix=public_prefix)


def format_help_all_command(*, public_prefix: str = "gpd:") -> str:
    """Render the runtime-public command for the compact help index."""

    return _apply_public_prefix("gpd:help --all", public_prefix=public_prefix)


def format_detailed_help_follow_up(*, public_prefix: str = "gpd:") -> str:
    """Render the runtime-public detailed-help follow-up sentence."""

    return _apply_public_prefix(DETAILED_HELP_FOLLOW_UP, public_prefix=public_prefix)


def render_command_detail_markdown(
    command_name: str,
    *,
    public_prefix: str = "gpd:",
    include_group_heading: bool = True,
) -> str:
    """Render one detailed command block from registry and renderer help metadata."""

    command = get_command(canonical_command_label(command_name))
    return _render_command_detail_block(
        command.name,
        include_group_heading=include_group_heading,
        public_prefix=public_prefix,
    )


def _detailed_reference_intro_lines(*, public_prefix: str) -> list[str]:
    return [
        "## Detailed Command Reference",
        "",
        _apply_public_prefix(
            "Use `gpd:help --command <name>` when you want the detailed notes for one runtime command at a time.",
            public_prefix=public_prefix,
        ),
        "",
        _apply_public_prefix(
            "Core workflow: `gpd:new-project` -> `gpd:discuss-phase` -> `gpd:plan-phase` -> `gpd:execute-phase` -> `gpd:verify-work` -> repeat.",
            public_prefix=public_prefix,
        ),
        "",
        _apply_public_prefix(
            (
                "Project-aware technical-analysis lane: `gpd:derive-equation`, `gpd:dimensional-analysis`, "
                "`gpd:limiting-cases`, `gpd:numerical-convergence`, `gpd:sensitivity-analysis`, "
                "`GPD/analysis/`, and `GPD/sweeps/`. "
                "`gpd:graph` and `gpd:error-propagation` are separate commands and are not part of this relaxed "
                "current-workspace lane."
            ),
            public_prefix=public_prefix,
        ),
    ]


def render_root_detailed_command_reference_markdown(*, public_prefix: str = "gpd:") -> str:
    """Render the compact root fallback for detailed help."""

    lines = _detailed_reference_intro_lines(public_prefix=public_prefix)
    lines.extend(
        (
            "",
            (
                "The full generated command detail reference is installed at "
                "`{GPD_INSTALL_DIR}/references/help/detailed-command-reference.md`; the runtime bridge serves "
                "that detail one command at a time."
            ),
            "",
            _apply_public_prefix(
                (
                    "Current-workspace durable outputs can be created from a project context or outside a project "
                    "only when the user supplies an explicit derivation target or explicit file path. Parameter "
                    "and sensitivity helpers keep their explicit flags visible: `--param`, `--range`, `--target`, "
                    "and `--params`."
                ),
                public_prefix=public_prefix,
            ),
        )
    )
    for command_name in _ROOT_DETAILED_REFERENCE_COMMANDS:
        lines.extend(
            (
                "",
                _render_root_command_detail_block(
                    command_name,
                    public_prefix=public_prefix,
                ),
            )
        )
    return "\n".join(lines).strip()


def render_detailed_command_reference_markdown(*, public_prefix: str = "gpd:") -> str:
    """Render the detailed command reference from registry and renderer help metadata."""

    lines = _detailed_reference_intro_lines(public_prefix=public_prefix)
    emitted: set[str] = set()
    for group in help_command_groups():
        lines.extend(("", f"### {group.name}"))
        for entry in group.commands:
            if entry.documented_variant or entry.registry_command in emitted:
                continue
            emitted.add(entry.registry_command)
            lines.extend(
                (
                    "",
                    _render_command_detail_block(
                        entry.registry_command,
                        include_group_heading=False,
                        public_prefix=public_prefix,
                    ),
                )
            )
    return "\n".join(lines).strip()


def render_quick_start_markdown(*, public_prefix: str = "gpd:") -> str:
    """Render the default public quick-start help section."""

    for command in _quick_start_runtime_commands():
        get_command(command)
    startup_ladder = beginner_startup_ladder()
    local_resume = local_cli_resume_command()
    local_resume_recent = local_cli_resume_recent_command()
    local_observe_execution = local_cli_observe_execution_command()
    local_cost = local_cli_cost_command()
    ladder_commands = _startup_ladder_runtime_command_map(startup_ladder)
    start_command = _required_ladder_command(ladder_commands, "start")
    tour_command = _required_ladder_command(ladder_commands, "tour")
    new_project_command = _required_ladder_command(ladder_commands, "new-project")
    map_research_command = _required_ladder_command(ladder_commands, "map-research")
    resume_work_command = _required_ladder_command(ladder_commands, "resume-work")
    start_command = _apply_public_prefix(start_command, public_prefix=public_prefix)
    tour_command = _apply_public_prefix(tour_command, public_prefix=public_prefix)
    new_project_command = _apply_public_prefix(new_project_command, public_prefix=public_prefix)
    map_research_command = _apply_public_prefix(map_research_command, public_prefix=public_prefix)
    resume_work_command = _apply_public_prefix(resume_work_command, public_prefix=public_prefix)
    return textwrap.dedent(
        f"""\
        ## Quick Start

        If you only remember one order, use this: {beginner_startup_ladder_text()}.
        {_runtime_ladder_sentence(startup_ladder, public_prefix=public_prefix)}

        Use the path that matches your current situation:

        **New work**
        1. `{start_command}` - Guided first-run router that chooses the safest first step for this folder
        2. `{tour_command}` - Get a read-only overview before choosing
        3. `{new_project_command}` - Create a full GPD project
        4. `{_apply_public_prefix("gpd:new-project --minimal", public_prefix=public_prefix)}` - Create a project through the shortest setup path

        **Existing work**
        1. `{map_research_command}` - Map an existing folder before turning it into a GPD project
        2. `{new_project_command}` - Turn that mapped context into a full GPD project

        **Returning work**
        1. `{local_resume}` - Reopen the current-workspace recovery snapshot from your normal terminal
        2. `{local_resume_recent}` - Find a different workspace first from your normal terminal
        3. `{resume_work_command}` - Continue inside the reopened project's canonical state
        4. `{_apply_public_prefix("gpd:progress", public_prefix=public_prefix)}` - See the broader project snapshot
        5. `{_apply_public_prefix("gpd:suggest-next", public_prefix=public_prefix)}` - Get the fastest next action
        6. `{local_observe_execution}` - Read-only progress / waiting state snapshot, conservative `possibly stalled` wording, and the next read-only checks from your normal terminal
        7. `{local_cost}` - Review recorded local telemetry usage / cost from your normal terminal

        **Post-startup settings**
        1. `{_apply_public_prefix("gpd:settings", public_prefix=public_prefix)}` - Change autonomy, permissions, and broader runtime preferences after your first successful start or later
        2. `{_apply_public_prefix("gpd:set-tier-models", public_prefix=public_prefix)}` - Pin concrete `tier-1`, `tier-2`, and `tier-3` model ids only

        When a side investigation appears later, use `{_apply_public_prefix("gpd:tangent", public_prefix=public_prefix)}` first. It is the chooser for stay / quick / defer / branch. Use `{_apply_public_prefix("gpd:branch-hypothesis", public_prefix=public_prefix)}` only when that tangent needs its own git-backed branch.
        """
    ).strip()


def render_command_index_markdown(*, public_prefix: str = "gpd:") -> str:
    """Render the compact grouped command index from renderer-owned help metadata."""

    lines = [
        "## Command Index",
        "",
        "This is the compact grouped list of runtime commands. For normal-terminal install, readiness, and diagnostics commands, use `gpd --help`.",
    ]
    for group in help_command_groups():
        lines.extend(("", f"### {group.name}", ""))
        lines.extend(
            f"- `{_apply_public_prefix(entry.command, public_prefix=public_prefix)}` - {entry.description}"
            for entry in group.commands
        )
    return "\n".join(lines)


def render_quick_start(*, public_prefix: str = "gpd:") -> str:
    """Render the default public quick-start help section."""

    return render_quick_start_markdown(public_prefix=public_prefix)


def render_command_index(*, public_prefix: str = "gpd:") -> str:
    """Render the compact grouped command index."""

    return render_command_index_markdown(public_prefix=public_prefix)


__all__ = [
    "DETAILED_HELP_FOLLOW_UP",
    "HelpCommandDetail",
    "HelpCommandEntry",
    "HelpCommandGroup",
    "build_help_catalog",
    "command_detail_payload",
    "command_groups_payload",
    "command_index_payload",
    "format_detailed_help_follow_up",
    "format_help_all_command",
    "help_command_groups",
    "render_command_index",
    "render_command_index_markdown",
    "render_command_detail_markdown",
    "render_detailed_command_reference_markdown",
    "render_root_detailed_command_reference_markdown",
    "render_quick_start",
    "render_quick_start_markdown",
]
