"""Tests for the registry-backed help renderer."""

from __future__ import annotations

import re

import pytest

from gpd.core import help_renderer
from gpd.core.public_surface_contract import (
    beginner_startup_ladder,
    beginner_startup_ladder_text,
    local_cli_cost_command,
    local_cli_observe_execution_command,
    local_cli_resume_command,
    local_cli_resume_recent_command,
)
from gpd.registry import list_commands

_COMMAND_ROW_RE = re.compile(r"^- `([^`]+)` - (.+)$", re.MULTILINE)
_NUMBERED_COMMAND_ROW_RE = re.compile(r"^\d+\. `([^`]+)` - (.+)$", re.MULTILINE)


def _command_rows(markdown: str) -> dict[str, str]:
    rows = _COMMAND_ROW_RE.findall(markdown)
    assert len(rows) == len({command for command, _description in rows})
    return dict(rows)


def _numbered_command_rows(markdown: str) -> list[tuple[str, str]]:
    return _NUMBERED_COMMAND_ROW_RE.findall(markdown)


def _assert_in_order(text: str, fragments: tuple[str, ...]) -> None:
    positions = [text.index(fragment) for fragment in fragments]
    assert positions == sorted(positions)


def _runtime_ladder_commands() -> tuple[str, ...]:
    return tuple(
        f"gpd:{part.strip()}"
        for step in beginner_startup_ladder()
        for part in step.split("/")
        if part.strip()
    )


def test_help_renderer_renders_quick_start_structure_without_freezing_marker_body() -> None:
    quick_start = help_renderer.render_quick_start_markdown()

    assert quick_start.startswith("## Quick Start")
    assert beginner_startup_ladder_text() in quick_start
    for section_heading in ("**New work**", "**Existing work**", "**Returning work**", "**Post-startup settings**"):
        assert section_heading in quick_start

    _assert_in_order(
        quick_start,
        tuple(f"`{command}`" for command in _runtime_ladder_commands()),
    )

    rows = _numbered_command_rows(quick_start)
    commands = {command for command, _description in rows}
    expected_rows = set(_runtime_ladder_commands()[1:])
    expected_rows.update(
        {
            "gpd:new-project --minimal",
            "gpd:progress",
            "gpd:suggest-next",
            "gpd:settings",
            "gpd:set-tier-models",
            local_cli_resume_command(),
            local_cli_resume_recent_command(),
            local_cli_observe_execution_command(),
            local_cli_cost_command(),
        }
    )
    assert expected_rows <= commands
    assert all(description.strip() for _command, description in rows)


def test_help_renderer_renders_command_index_from_registry_backed_groups() -> None:
    command_index = help_renderer.render_command_index_markdown()

    assert command_index.startswith("## Command Index")
    rows = _command_rows(command_index)
    expected_commands = {entry.command for group in help_renderer.help_command_groups() for entry in group.commands}
    assert set(rows) == expected_commands
    assert all(description.strip() for description in rows.values())

    for group in help_renderer.help_command_groups():
        assert f"### {group.name}" in command_index
        fragments = (f"### {group.name}",) + tuple(f"`{entry.command}`" for entry in group.commands)
        _assert_in_order(command_index, fragments)


def test_help_command_groups_cover_registry_without_treating_minimal_variant_as_command() -> None:
    groups = help_renderer.help_command_groups()

    grouped_registry_commands = {
        entry.registry_command for group in groups for entry in group.commands if not entry.documented_variant
    }
    assert grouped_registry_commands == set(list_commands(name_format="label"))

    documented_variants = [entry for group in groups for entry in group.commands if entry.documented_variant]
    assert [(entry.command, entry.registry_command) for entry in documented_variants] == [
        ("gpd:new-project --minimal", "gpd:new-project")
    ]
    assert "gpd:new-project --minimal" not in set(list_commands(name_format="label"))


def test_command_groups_payload_preserves_raw_help_shape() -> None:
    groups = help_renderer.command_groups_payload()

    assert groups[0]["name"] == "Starter commands"
    first_command = groups[0]["commands"][0]
    assert first_command["command"] == "gpd:help"
    assert set(first_command) == {"command", "description"}
    assert isinstance(first_command["description"], str)
    description = first_command["description"].casefold()
    for fragment in ("quick start", "command index"):
        assert fragment in description
    starter_commands = {entry["command"] for entry in groups[0]["commands"]}
    assert "gpd:new-project --minimal" in starter_commands


def test_command_detail_payload_uses_registry_and_normalizes_documented_variants() -> None:
    detail = help_renderer.command_detail_payload("gpd:new-project --minimal", minimal=True)

    assert detail["canonical_command"] == "gpd:new-project"
    assert detail["slug"] == "new-project"
    assert detail["context_mode"] == "projectless"
    assert detail["allowed_tools"] == []
    assert detail["requires"] == {}


def test_command_detail_payload_fails_closed_for_unknown_commands() -> None:
    with pytest.raises(KeyError):
        help_renderer.command_detail_payload("does-not-exist")
