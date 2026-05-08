"""Tests for the registry-backed help renderer."""

from __future__ import annotations

from pathlib import Path

import pytest

from gpd.core import help_renderer
from gpd.registry import list_commands


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _help_marker_section(marker_name: str) -> str:
    content = (_repo_root() / "src/gpd/specs/workflows/help.md").read_text(encoding="utf-8")
    start = f"<!-- gpd-help:{marker_name}:start -->"
    end = f"<!-- gpd-help:{marker_name}:end -->"
    _, start_separator, tail = content.partition(start)
    assert start_separator
    section, end_separator, _ = tail.partition(end)
    assert end_separator
    return section.strip()


def test_help_renderer_matches_checked_in_quick_start_and_command_index_markers() -> None:
    assert help_renderer.render_quick_start_markdown() == _help_marker_section("quick-start")
    assert help_renderer.render_command_index_markdown() == _help_marker_section("command-index")


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
    assert groups[0]["commands"][0] == {
        "command": "gpd:help",
        "description": "Show the quick start or command index",
    }
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
