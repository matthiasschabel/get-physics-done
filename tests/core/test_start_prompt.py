from __future__ import annotations

import re
from pathlib import Path

from gpd.adapters.install_utils import expand_at_includes
from gpd.registry import get_command, list_commands
from tests.assertion_taxonomy_support import FragmentMode, semantic_anchor
from tests.doc_surface_contracts import assert_start_workflow_router_contract

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = REPO_ROOT / "src" / "gpd" / "commands"
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
SOURCE_ROOT = REPO_ROOT / "src" / "gpd"
PATH_PREFIX = "/runtime/"


def _normalized(content: str) -> str:
    return " ".join(content.split())


def _extract_step(workflow: str, step_name: str) -> str:
    start = workflow.index(f'<step name="{step_name}">')
    end = workflow.index("</step>", start)
    return workflow[start:end]


def _extract_between(content: str, start_marker: str, end_marker: str) -> str:
    start = content.index(start_marker) + len(start_marker)
    end = content.index(end_marker, start)
    return content[start:end]


def _displayed_choice_labels(workflow: str) -> set[str]:
    offer_step = _extract_step(workflow, "offer_relevant_choices")
    labels: set[str] = set()
    for line in offer_step.splitlines():
        match = re.match(r"\s*(?:\d+\.|-)\s+(.+?)\s+- use `", line)
        if match is not None:
            labels.add(match.group(1))
    return labels


def _routed_choice_labels(workflow: str) -> set[str]:
    route_step = _extract_step(workflow, "route_choice")
    labels: set[str] = set()
    for match in re.finditer(r"\*\*If the researcher chooses (?P<body>.*?):\*\*", route_step):
        labels.update(re.findall(r"`([^`]+)`", match.group("body")))
    return labels


def _route_for_option(workflow: str, option_id: str) -> str:
    route_step = _extract_step(workflow, "route_choice")
    start_marker = f"**If the researcher chooses option_id `{option_id}`"
    start = route_step.index(start_marker)
    next_route = re.search(r"\n\*\*If the researcher chooses option_id `", route_step[start + 1 :])
    if next_route is None:
        return route_step[start:]
    return route_step[start : start + 1 + next_route.start()]


def _numbered_choices(section: str) -> list[str]:
    return [line.strip() for line in section.splitlines() if re.match(r"\s*\d+\.\s+", line)]


def _assert_anchor(text: str, label: str, fragments: tuple[str, ...] | str) -> None:
    semantic_anchor(label, fragments).check(text)


def _assert_absent(text: str, label: str, fragments: tuple[str, ...] | str) -> None:
    semantic_anchor(label, fragments, mode=FragmentMode.ABSENT).check(text)


def _assert_same_message_choice_boundary(text: str) -> None:
    _assert_anchor(
        text,
        "same-message start choice boundary",
        (
            "same-message explicit choice",
            "chooser answer",
            "not downstream write approval",
            "downstream intake",
            "scope approval",
            "file creation",
            "git initialization",
            "state repair",
            "map creation",
            "mapper spawning",
            "progress writes",
        ),
    )


def _assert_reopen_recent_boundary(text: str) -> None:
    _assert_anchor(
        text,
        "reopen recent terminal/runtime boundary",
        (
            "gpd resume --recent",
            "recent-project picker",
            "advisory",
            "gpd:resume-work",
        ),
    )


def test_start_command_is_registered_and_projectless() -> None:
    assert "start" in list_commands()
    command = get_command("gpd:start")
    assert command.name == "gpd:start"
    assert command.context_mode == "projectless"


def test_start_command_references_workflow() -> None:
    raw_command_prompt = (COMMANDS_DIR / "start.md").read_text(encoding="utf-8")
    command_prompt = expand_at_includes(raw_command_prompt, SOURCE_ROOT, PATH_PREFIX)

    assert "@{GPD_INSTALL_DIR}/workflows/start.md" in raw_command_prompt
    assert "@{GPD_INSTALL_DIR}/references/onboarding/beginner-command-taxonomy.md" in raw_command_prompt
    assert "gpd resume" in command_prompt
    assert "gpd resume --recent" in command_prompt
    assert "gpd:resume-work" in command_prompt
    assert "gpd:suggest-next" in command_prompt
    _assert_anchor(raw_command_prompt, "start passes argument context through", ("Requested choice", "$ARGUMENTS"))
    _assert_reopen_recent_boundary(command_prompt)
    semantic_anchor(
        "start recovery ladder command ordering",
        (
            "`gpd resume`",
            "current-workspace recovery snapshot",
            "`gpd resume --recent`",
            "advisory recent-project picker",
            "`gpd:suggest-next`",
            "fastest post-resume next command",
        ),
        mode=FragmentMode.ORDERED,
    ).check(command_prompt)


def test_start_command_same_message_choice_is_not_downstream_write_approval() -> None:
    raw_command_prompt = (COMMANDS_DIR / "start.md").read_text(encoding="utf-8")
    prompt = _normalized(raw_command_prompt)

    _assert_same_message_choice_boundary(prompt)
    _assert_anchor(
        prompt, "same-message choice does not execute recommendations", "executing a recommended next action"
    )


def test_start_workflow_routes_to_existing_entrypoints() -> None:
    workflow = (WORKFLOWS_DIR / "start.md").read_text(encoding="utf-8")

    assert_start_workflow_router_contract(workflow)
    assert "START_CONTEXT=$(gpd --raw init new-project)" in workflow
    assert "gpd --raw init new-project --stage scope_intake" not in workflow
    detect_step = _extract_step(workflow, "detect_workspace_state")
    explain_step = _extract_step(workflow, "explain_current_state")
    offer_step = _extract_step(workflow, "offer_relevant_choices")

    _assert_anchor(
        detect_step,
        "start classifier uses raw workspace-bound preflight",
        ("non-staged raw CLI classifier", "workspace-bound", "read-only classifier", "invoked folder itself"),
    )
    _assert_anchor(
        detect_step + explain_step,
        "research file samples are classifier-provided context",
        ("research_file_samples", "sorted", "bounded", "project-relative", "show those sample files"),
    )
    assert "read-only file search" not in workflow
    assert "HAS_GPD_PROJECT=false" not in workflow
    assert "RESEARCH_FILE_COUNT" not in workflow

    _assert_anchor(
        explain_step,
        "start explains folder states in official beginner terms",
        (
            "GPD project",
            "research map",
            "map-research",
            "inspect an existing folder",
            "new-project",
            "project scaffolding",
        ),
    )
    for heading in (
        "This folder already has saved GPD work (`GPD project`)",
        "This folder has partial/recoverable GPD state",
        "This folder already has GPD's folder summary (`research map`)",
        "This folder already has research files, but GPD is not set up here yet",
        "This folder looks new or mostly empty",
    ):
        assert heading in offer_step
    assert {
        "Resume this project (recommended)",
        "Review the project status first",
        "Map this folder first (recommended)",
        "Start a brand-new GPD project anyway",
        "Fast start (recommended)",
        "Full guided setup",
        "Turn this into a full GPD project (recommended)",
    } <= _displayed_choice_labels(workflow)
    _assert_anchor(
        offer_step,
        "start first chooser stays short and state-specific",
        ("safest next steps first", "broader options second", "Keep the numbered list short", "first chooser"),
    )
    _assert_same_message_choice_boundary(offer_step)
    _assert_anchor(
        offer_step,
        "same-message chooser visible reply instruction",
        ("Reply with the number or the option name.", "Do not treat surrounding goals"),
    )
    _assert_reopen_recent_boundary(workflow)
    guardrails = _extract_step(workflow, "guardrails")
    _assert_anchor(
        guardrails,
        "start guardrails preserve chooser boundary",
        (
            "chooser",
            "not a second implementation",
            "Do not silently create project files",
            "Do not silently switch",
            "prefer `map-research`",
            "official GPD terms",
        ),
    )

    _assert_absent(workflow, "quoted internal numbered-list rule leak", "- `Keep the numbered list short.")
    _assert_absent(
        workflow,
        "old internal structuring rule leak",
        "this is an internal structuring rule, not a line to show the researcher",
    )
    assert "Other useful options" not in workflow
    assert "other useful options" not in workflow

    assert "Read `{GPD_INSTALL_DIR}/workflows/new-project.md` with the file-read tool." not in workflow
    assert "Read `{GPD_INSTALL_DIR}/workflows/help.md` with the file-read tool." not in workflow
    assert "Read `{GPD_INSTALL_DIR}/workflows/tour.md` with the file-read tool." not in workflow
    _assert_anchor(
        offer_step,
        "partial state choices are filtered by recoverable fields",
        ("command-context preflight", "roadmap_exists=true", "state_exists=true", "next numbered choice"),
    )
    partial_state_choices = _extract_between(
        workflow,
        "**This folder has partial/recoverable GPD state**",
        "**This folder already has GPD's folder summary",
    )
    _assert_anchor(partial_state_choices, "partial state choices are renumbered after filtering", "contiguously")
    assert "1. Inspect recovery state" not in partial_state_choices
    assert "2. Reconcile state files" not in partial_state_choices
    _assert_anchor(
        offer_step, "partial state excludes progress route", ("Do not list", "gpd:progress", "partial state")
    )
    assert "Review visible progress - use `gpd:progress`" not in workflow


def test_start_workflow_existing_research_unmapped_first_chooser_is_only_three_choices() -> None:
    workflow = (WORKFLOWS_DIR / "start.md").read_text(encoding="utf-8")
    existing_research_choices = _extract_between(
        workflow,
        "**This folder already has research files, but GPD is not set up here yet**",
        "**This folder looks new or mostly empty**",
    )

    assert _numbered_choices(existing_research_choices) == [
        "1. Map this folder first (recommended) - use `gpd:map-research`.",
        "2. Take a guided tour first - use `gpd:tour`.",
        "3. Start a brand-new GPD project anyway - use `gpd:new-project --minimal`.",
    ]
    assert re.findall(r"`(gpd:[^`]+)`", existing_research_choices) == [
        "gpd:map-research",
        "gpd:tour",
        "gpd:new-project --minimal",
    ]
    assert not re.search(r"(?m)^\s*-\s+.+\s+- use `gpd:", existing_research_choices)
    assert "Other useful options" not in existing_research_choices
    assert "capabilities menu" not in existing_research_choices
    assert "help menu" not in existing_research_choices
    assert "gpd:help" not in existing_research_choices
    assert "gpd:quick" not in existing_research_choices
    assert "gpd:explain" not in existing_research_choices
    assert "gpd:suggest-next" not in existing_research_choices


def test_start_workflow_displayed_choice_labels_route_verbatim() -> None:
    workflow = (WORKFLOWS_DIR / "start.md").read_text(encoding="utf-8")

    displayed_labels = _displayed_choice_labels(workflow)
    routed_labels = _routed_choice_labels(workflow)

    assert displayed_labels
    assert displayed_labels <= routed_labels
    assert "Do one small bounded task" not in displayed_labels
    assert "Do one small bounded task" not in routed_labels
    assert "tour" in routed_labels


def test_start_workflow_same_message_choice_is_only_chooser_authority() -> None:
    workflow = (WORKFLOWS_DIR / "start.md").read_text(encoding="utf-8")
    offer_step = _normalized(_extract_step(workflow, "offer_relevant_choices"))

    _assert_same_message_choice_boundary(offer_step)
    _assert_anchor(
        offer_step,
        "same-message choice does not execute next action",
        "permission to execute a recommended next action",
    )


def test_start_workflow_route_choice_has_general_downstream_write_gate_boundary() -> None:
    workflow = (WORKFLOWS_DIR / "start.md").read_text(encoding="utf-8")
    route_step = _normalized(_extract_step(workflow, "route_choice"))

    _assert_anchor(
        route_step,
        "start route choice has downstream write gate",
        (
            "start-menu choice authorizes only the route into that command",
            "state the route boundary visibly",
            "first downstream write-capable gate",
            "separate explicit approval",
        ),
    )


def test_start_workflow_new_project_routes_stop_before_project_writes() -> None:
    workflow = (WORKFLOWS_DIR / "start.md").read_text(encoding="utf-8")

    for option_id, command in (
        ("new_project_minimal", "gpd:new-project --minimal"),
        ("new_project_full", "gpd:new-project"),
    ):
        route = _route_for_option(workflow, option_id)
        assert (
            f"I will route to `{command}` now and stop at its first downstream intake or scope-approval gate" in route
        )
        assert "no project, git, state, or progress files are approved by this start choice" in route
        assert f"Route boundary for `{option_id}`" in route
        assert "do not create `GPD/`" in route
        assert "initialize git" in route
        assert "write state" in route
        assert "write progress files" in route
        assert "explicit downstream intake/scope approval after this start route" in route


def test_start_workflow_map_route_stops_before_research_map_writes() -> None:
    workflow = (WORKFLOWS_DIR / "start.md").read_text(encoding="utf-8")
    route = _route_for_option(workflow, "map_research")

    assert "I will route to `gpd:map-research` now and stop at its first map-research decision/write gate" in route
    assert "no research-map files, mapper agents, archives, or summaries are approved by this start choice" in route
    assert "Route boundary for `map_research`" in route
    assert "stop before creating, archiving, or updating `GPD/research-map/`" in route
    assert "before spawning mapper agents" in route
    assert "before writing summaries" in route
    assert "explicit durable-write confirmation after the route handoff" in route


def test_start_workflow_sync_route_stops_before_state_repair_writes() -> None:
    workflow = (WORKFLOWS_DIR / "start.md").read_text(encoding="utf-8")
    route = _route_for_option(workflow, "sync_state")

    assert "I will route to `gpd:sync-state` now and stop after its recovery diagnosis/instruction gate" in route
    assert "no state repair or state rewrite is approved by this start choice" in route
    assert "do not continue through the sync-state shell repair workflow from `gpd:start`" in route
    assert "Route boundary for `sync_state`" in route
    assert "do not run `gpd state repair-sync`" in route
    assert "promote backups" in route
    assert "rewrite `GPD/STATE.md`" in route
    assert "rewrite `GPD/state.json`" in route
    assert "separate exact sync/repair confirmation inside `gpd:sync-state`" in route


def test_start_workflow_progress_route_is_default_report_only() -> None:
    workflow = (WORKFLOWS_DIR / "start.md").read_text(encoding="utf-8")
    route = _route_for_option(workflow, "progress")

    assert "I will route to `gpd:progress` now in default/report mode only" in route
    assert "no reconcile, state write, compaction, or next-action execution is approved by this start choice" in route
    assert "Route boundary for `progress`" in route
    assert "use default/report mode only" in route
    assert "Do not switch to `--reconcile`" in route
    assert "execute the recommended next action" in route
    assert "compact state" in route
    assert "write progress/state files" in route
