"""Registry-backed rendering helpers for the public GPD help surface."""

from __future__ import annotations

import dataclasses
import textwrap
from functools import lru_cache
from typing import TypeAlias

from gpd.command_labels import canonical_command_label, parse_command_label
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


def _format_ladder_step_as_runtime_commands(step: str) -> str:
    commands = _runtime_command_for_ladder_step(step)
    if not commands:
        raise ValueError("beginner startup ladder steps must contain at least one command")
    return " or ".join(f"`{command}`" for command in commands)


def _runtime_ladder_sentence(ladder: tuple[str, ...]) -> str:
    command_fragments = tuple(_format_ladder_step_as_runtime_commands(step) for step in ladder)
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


def command_detail_payload(command_name: str, *, minimal: bool = False) -> dict[str, object]:
    """Return compact registry metadata for one command lookup."""

    command = get_command(canonical_command_label(command_name))
    detail = HelpCommandDetail(
        canonical_command=command.name,
        slug=parse_command_label(command.name).slug,
        description=command.description,
        argument_hint=command.argument_hint,
        context_mode=command.context_mode,
        project_reentry_capable=command.project_reentry_capable,
        allowed_tools=[] if minimal else command.allowed_tools,
        requires={} if minimal else command.requires,
    )
    return detail.as_payload()


def render_quick_start_markdown() -> str:
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
    return textwrap.dedent(
        f"""\
        ## Quick Start

        If you only remember one order, use this: {beginner_startup_ladder_text()}.
        {_runtime_ladder_sentence(startup_ladder)}

        Use the path that matches your current situation:

        **New work**
        1. `{start_command}` - Guided first-run router that chooses the safest first step for this folder
        2. `{tour_command}` - Get a read-only overview before choosing
        3. `{new_project_command}` - Create a full GPD project
        4. `gpd:new-project --minimal` - Create a project through the shortest setup path

        **Existing work**
        1. `{map_research_command}` - Map an existing folder before turning it into a GPD project
        2. `{new_project_command}` - Turn that mapped context into a full GPD project

        **Returning work**
        1. `{local_resume}` - Reopen the current-workspace recovery snapshot from your normal terminal
        2. `{local_resume_recent}` - Find a different workspace first from your normal terminal
        3. `{resume_work_command}` - Continue inside the reopened project's canonical state
        4. `gpd:progress` - See the broader project snapshot
        5. `gpd:suggest-next` - Get the fastest next action
        6. `{local_observe_execution}` - Read-only progress / waiting state snapshot, conservative `possibly stalled` wording, and the next read-only checks from your normal terminal
        7. `{local_cost}` - Review recorded machine-local usage / cost from your normal terminal

        **Post-startup settings**
        1. `gpd:settings` - Change autonomy, permissions, and broader runtime preferences after your first successful start or later
        2. `gpd:set-tier-models` - Pin concrete `tier-1`, `tier-2`, and `tier-3` model ids only

        When a side investigation appears later, use `gpd:tangent` first. It is the chooser for stay / quick / defer / branch. Use `gpd:branch-hypothesis` only when that tangent needs its own git-backed branch.
        """
    ).strip()


def render_command_index_markdown() -> str:
    """Render the compact grouped command index from renderer-owned help metadata."""

    lines = [
        "## Command Index",
        "",
        "This is the compact grouped list of runtime commands. For normal-terminal install, readiness, and diagnostics commands, use `gpd --help`.",
    ]
    for group in help_command_groups():
        lines.extend(("", f"### {group.name}", ""))
        lines.extend(f"- `{entry.command}` - {entry.description}" for entry in group.commands)
    return "\n".join(lines)


def render_quick_start() -> str:
    """Render the default public quick-start help section."""

    return render_quick_start_markdown()


def render_command_index() -> str:
    """Render the compact grouped command index."""

    return render_command_index_markdown()


__all__ = [
    "DETAILED_HELP_FOLLOW_UP",
    "HelpCommandDetail",
    "HelpCommandEntry",
    "HelpCommandGroup",
    "build_help_catalog",
    "command_detail_payload",
    "command_groups_payload",
    "command_index_payload",
    "help_command_groups",
    "render_command_index",
    "render_command_index_markdown",
    "render_quick_start",
    "render_quick_start_markdown",
]
