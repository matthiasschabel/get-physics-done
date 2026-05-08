from __future__ import annotations

from pathlib import Path

from gpd.adapters.install_utils import expand_at_includes
from gpd.core.onboarding_surfaces import beginner_startup_ladder_text
from gpd.registry import get_command, list_commands
from tests.assertion_taxonomy_support import FragmentMode, forbidden_duplicate, fragment_count, semantic_anchor
from tests.doc_surface_contracts import assert_tour_command_surface_contract

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = REPO_ROOT / "src" / "gpd" / "commands"
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
SOURCE_ROOT = REPO_ROOT / "src" / "gpd"
PATH_PREFIX = "/runtime/"


def _extract_between(content: str, start_marker: str, end_marker: str) -> str:
    start = content.index(start_marker) + len(start_marker)
    end = content.index(end_marker, start)
    return content[start:end]


def _extract_step(workflow: str, step_name: str) -> str:
    start = workflow.index(f'<step name="{step_name}">')
    end = workflow.index("</step>", start)
    return workflow[start:end]


def _assert_anchor(text: str, label: str, fragments: tuple[str, ...] | str) -> None:
    semantic_anchor(label, fragments).check(text)


def _assert_absent(text: str, label: str, fragments: tuple[str, ...] | str) -> None:
    semantic_anchor(label, fragments, mode=FragmentMode.ABSENT).check(text)


def _tour_required_entries(workflow: str) -> set[str]:
    table_block = _extract_between(workflow, "Include these entries:", "Keep this table runtime-facing only.")
    return {line.strip()[3:-1] for line in table_block.splitlines() if line.strip().startswith("- `")}


def _assert_tour_read_only_boundary(text: str) -> None:
    _assert_anchor(
        text,
        "tour read-only boundary",
        (
            "read-only tour",
            "does not create files",
            "change project",
            "state",
            "route into another workflow",
        ),
    )


def test_tour_command_is_registered_and_projectless() -> None:
    assert "tour" in list_commands()
    command = get_command("gpd:tour")
    assert command.name == "gpd:tour"
    assert command.context_mode == "projectless"
    assert command.allowed_tools == ["file_read"]


def test_tour_command_references_workflow() -> None:
    raw_command_prompt = (COMMANDS_DIR / "tour.md").read_text(encoding="utf-8")
    command_prompt = expand_at_includes(raw_command_prompt, SOURCE_ROOT, PATH_PREFIX)

    assert "@{GPD_INSTALL_DIR}/workflows/tour.md" in raw_command_prompt
    assert "@{GPD_INSTALL_DIR}/references/onboarding/beginner-command-taxonomy.md" in raw_command_prompt
    assert "gpd:set-tier-models" in command_prompt
    assert "gpd:settings" in command_prompt
    assert "This is a read-only tour of the main GPD commands. It will not change your files." in command_prompt
    _assert_anchor(command_prompt, "tour uses runtime-native command labels", ("runtime-native command labels", "gpd:"))


def test_tour_workflow_introduces_a_safe_beginner_walkthrough() -> None:
    workflow = (WORKFLOWS_DIR / "tour.md").read_text(encoding="utf-8")
    expanded_workflow = expand_at_includes(workflow, SOURCE_ROOT, PATH_PREFIX)
    assert_tour_command_surface_contract(workflow)
    table_entries = _extract_between(workflow, "Include these entries:", "Keep this table runtime-facing only.")
    assert _tour_required_entries(workflow) == {
        "gpd:start",
        "gpd:new-project --minimal",
        "gpd:new-project",
        "gpd:map-research",
        "gpd:resume-work",
        "gpd:progress",
        "gpd:suggest-next",
        "gpd:explain <topic>",
        "gpd:quick",
        "gpd:set-tier-models",
        "gpd:settings",
        "gpd:help",
    }
    _assert_absent(table_entries, "normal terminal resume is absent from runtime table", "- `gpd resume`")
    _assert_anchor(
        workflow,
        "tour table stays runtime-facing",
        ("runtime-facing only", "gpd resume", "terminal/runtime distinction"),
    )
    _assert_tour_read_only_boundary(workflow)
    _assert_anchor(
        expanded_workflow,
        "tour startup ladder comes from public surface contract",
        (beginner_startup_ladder_text(), "folder state", "actual path"),
    )

    for public_label in (
        "Use a compact table with four columns:",
        "Use this when",
        "Do not use this when",
        "Example",
        "A few terms in plain English",
        '"If you are still unsure, run `gpd:start`."',
    ):
        assert public_label in workflow

    _assert_anchor(
        _extract_step(workflow, "show_broader_capabilities"),
        "tour surfaces later capability groups",
        (
            "gpd:plan-phase",
            "gpd:execute-phase",
            "gpd:verify-work",
            "gpd:peer-review",
            "gpd:respond-to-referees",
            "gpd:arxiv-submission",
            "gpd:branch-hypothesis",
            "gpd:set-profile",
            "settings/model commands from the startup table",
        ),
    )
    _assert_anchor(
        _extract_step(workflow, "distinguish_terminal_and_runtime"),
        "tour distinguishes normal terminal from runtime",
        (
            "gpd --help",
            "gpd doctor",
            "gpd resume",
            "gpd:resume-work",
            "gpd:settings",
            "gpd:set-tier-models",
            "gpd:tour",
            "does not run",
        ),
    )
    _assert_anchor(
        _extract_step(workflow, "highlight_common_mistakes"),
        "tour highlights common command boundaries",
        (
            "Use `gpd:start` when you are still deciding, not `gpd:new-project`",
            "Use `gpd:resume-work` only when the project already has GPD state",
            "Use `gpd:help` when you want the command reference, not a setup wizard",
        ),
    )
    _assert_anchor(
        _extract_step(workflow, "explain_advanced_terms"),
        "tour defines beginner terms without routing",
        ("GPD project", "research map", "phase", "read-only", "without making changes"),
    )

    fragment_count("tour set-tier-models exact mention count", "gpd:set-tier-models", expected_count=2).check(workflow)
    fragment_count("tour settings exact mention count", "gpd:settings", expected_count=2).check(workflow)
    forbidden_duplicate("tour set-tier-models bounded duplicates", "set-tier-models", max_count=3).check(workflow)
    forbidden_duplicate("tour settings bounded duplicates", "settings", max_count=5).check(workflow)
    fragment_count("tour tier-1 model tier appears once", "tier-1", expected_count=1).check(workflow)
