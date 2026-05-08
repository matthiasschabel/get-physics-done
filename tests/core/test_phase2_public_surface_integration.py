"""Phase 2 public-surface renderer integration guardrails."""

from __future__ import annotations

import dataclasses
import importlib
import importlib.util
import inspect
import json
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import pytest
from typer.testing import CliRunner

from gpd import registry
from gpd.cli import app
from gpd.command_labels import parse_command_label

REPO_ROOT = Path(__file__).resolve().parents[2]
RENDER_PUBLIC_SURFACE_SCRIPT = REPO_ROOT / "scripts" / "render_public_surface.py"
HELP_WORKFLOW_PATH = REPO_ROOT / "src" / "gpd" / "specs" / "workflows" / "help.md"


class _StableCliRunner(CliRunner):
    def invoke(self, *args: object, **kwargs: object):
        kwargs.setdefault("color", False)
        return super().invoke(*args, **kwargs)


runner = _StableCliRunner()


def _range(content: str, start_marker: str, end_marker: str) -> str:
    start = content.index(start_marker) + len(start_marker)
    end = content.index(end_marker, start)
    return content[start:end]


def _help_marker_range(content: str, marker_name: str) -> str:
    return _range(
        content,
        f"<!-- gpd-help:{marker_name}:start -->",
        f"<!-- gpd-help:{marker_name}:end -->",
    )


def _phase2_module(module_name: str) -> object:
    if importlib.util.find_spec(module_name) is None:
        pytest.skip(f"{module_name} is not available yet")
    return importlib.import_module(module_name)


def _as_mapping(value: object, *, context: str) -> Mapping[str, object]:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        value = dataclasses.asdict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        value = to_dict()
    if isinstance(value, Mapping):
        return cast(Mapping[str, object], value)
    pytest.fail(f"{context} must be a mapping-like payload, got {type(value)!r}")


def _as_sequence(value: object, *, context: str) -> Sequence[object]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return value
    pytest.fail(f"{context} must be a sequence, got {type(value)!r}")


def _call_with_supported_kwargs(function: object, /, **kwargs: object) -> object:
    signature = inspect.signature(function)
    supported_kwargs = {name: value for name, value in kwargs.items() if name in signature.parameters}
    missing_required = [
        parameter.name
        for parameter in signature.parameters.values()
        if parameter.kind
        in {
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        }
        and parameter.default is inspect.Parameter.empty
        and parameter.name not in supported_kwargs
    ]
    if missing_required:
        function_name = getattr(function, "__name__", repr(function))
        pytest.fail(f"{function_name} requires unsupported parameter(s): {missing_required}")
    return function(**supported_kwargs)


def _rendered_markdown(result: object, *, context: str) -> str:
    if isinstance(result, str):
        return result.strip()
    markdown = getattr(result, "markdown", None)
    if isinstance(markdown, str):
        return markdown.strip()
    mapping = _as_mapping(result, context=context)
    markdown_value = mapping.get("markdown")
    if isinstance(markdown_value, str):
        return markdown_value.strip()
    pytest.fail(f"{context} must expose markdown text")


def _build_help_catalog(renderer: object) -> object:
    build_help_catalog = getattr(renderer, "build_help_catalog", None)
    if callable(build_help_catalog):
        return build_help_catalog()

    help_command_groups = getattr(renderer, "help_command_groups", None)
    if callable(help_command_groups):
        return {"command_groups": help_command_groups()}

    command_groups_payload = getattr(renderer, "command_groups_payload", None)
    if callable(command_groups_payload):
        return {"command_groups": command_groups_payload()}

    pytest.fail("gpd.core.help_renderer must expose renderer-owned command groups")


def _render_quick_start(renderer: object) -> str:
    render_quick_start = getattr(renderer, "render_quick_start", None) or getattr(
        renderer, "render_quick_start_markdown", None
    )
    if render_quick_start is None:
        pytest.fail("gpd.core.help_renderer must expose quick-start markdown rendering")
    return _rendered_markdown(
        _call_with_supported_kwargs(render_quick_start, public_prefix="gpd:"),
        context="render_quick_start()",
    )


def _render_command_index(renderer: object, catalog: object) -> str:
    render_command_index = getattr(renderer, "render_command_index", None) or getattr(
        renderer, "render_command_index_markdown", None
    )
    if render_command_index is None:
        pytest.fail("gpd.core.help_renderer must expose command-index markdown rendering")
    return _rendered_markdown(
        _call_with_supported_kwargs(
            render_command_index,
            catalog=catalog,
            public_prefix="gpd:",
            include_quick_start=False,
        ),
        context="render_command_index()",
    )


def _value_from_mapping(mapping: Mapping[str, object], names: tuple[str, ...], *, context: str) -> object:
    for name in names:
        if name in mapping:
            return mapping[name]
    pytest.fail(f"{context} must expose one of {names}")


def _catalog_groups(catalog: object) -> object:
    if dataclasses.is_dataclass(catalog) and not isinstance(catalog, type):
        catalog = dataclasses.asdict(catalog)
    if isinstance(catalog, Mapping):
        for field_name in ("command_groups", "groups", "help_groups"):
            if field_name in catalog:
                return catalog[field_name]
    for field_name in ("command_groups", "groups", "help_groups"):
        value = getattr(catalog, field_name, None)
        if value is not None:
            return value
    pytest.fail("build_help_catalog() must expose renderer-owned command groups")


def _renderer_command_groups(renderer: object, catalog: object) -> object:
    for function_name in (
        "build_command_groups",
        "command_groups",
        "render_command_groups",
        "help_command_groups",
    ):
        function = getattr(renderer, function_name, None)
        if callable(function):
            return _call_with_supported_kwargs(function, catalog=catalog, public_prefix="gpd:")
    return _catalog_groups(catalog)


def _canonical_usage(raw_label: str) -> tuple[str, str, str]:
    label = raw_label.strip().strip("`")
    parts = parse_command_label(label)
    if not parts.slug:
        pytest.fail(f"invalid command label in renderer group: {raw_label!r}")
    inline_suffix = f" {parts.inline_args}" if parts.inline_args else ""
    return f"{parts.canonical_command}{inline_suffix}", parts.slug, parts.inline_args


def _normalize_command_entry(entry: object, *, context: str) -> dict[str, str]:
    if isinstance(entry, str):
        command, slug, inline_args = _canonical_usage(entry)
        return {"command": command, "slug": slug, "inline_args": inline_args, "description": ""}

    mapping = _as_mapping(entry, context=context)
    raw_label = _value_from_mapping(
        mapping,
        ("command", "label", "usage", "display", "command_label", "canonical_command", "name"),
        context=context,
    )
    command, slug, inline_args = _canonical_usage(str(raw_label))
    description = mapping.get("description") or mapping.get("summary") or mapping.get("help_summary") or ""
    return {
        "command": command,
        "slug": slug,
        "inline_args": inline_args,
        "description": str(description),
    }


def _normalize_command_groups(groups: object) -> list[dict[str, object]]:
    normalized_groups: list[dict[str, object]] = []
    for group_index, group in enumerate(_as_sequence(groups, context="command groups")):
        group_mapping = _as_mapping(group, context=f"command group {group_index}")
        name = str(
            _value_from_mapping(
                group_mapping,
                ("name", "title", "heading", "group"),
                context=f"command group {group_index}",
            )
        )
        entries = _value_from_mapping(
            group_mapping,
            ("commands", "entries", "items"),
            context=f"command group {name!r}",
        )
        commands = [
            _normalize_command_entry(entry, context=f"command group {name!r} entry {entry_index}")
            for entry_index, entry in enumerate(_as_sequence(entries, context=f"command group {name!r} entries"))
        ]
        normalized_groups.append({"name": name, "commands": commands})
    return normalized_groups


def _raw_help_payload(tmp_path: Path, *args: str) -> dict[str, object]:
    result = runner.invoke(
        app,
        ["--raw", "--cwd", str(tmp_path), "help", *args],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert isinstance(payload, dict)
    return cast(dict[str, object], payload)


def test_generated_public_surface_blocks_are_current() -> None:
    if not RENDER_PUBLIC_SURFACE_SCRIPT.exists():
        pytest.skip("scripts/render_public_surface.py is not available yet")

    result = subprocess.run(
        [sys.executable, str(RENDER_PUBLIC_SURFACE_SCRIPT), "--check"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_help_renderer_command_groups_cover_registry_inventory_once() -> None:
    renderer = _phase2_module("gpd.core.help_renderer")
    catalog = _build_help_catalog(renderer)
    groups = _normalize_command_groups(_renderer_command_groups(renderer, catalog))

    group_names = [str(group["name"]) for group in groups]
    assert group_names
    assert len(group_names) == len(set(group_names))
    assert all(group["commands"] for group in groups)

    entries = [command for group in groups for command in cast(Sequence[Mapping[str, str]], group["commands"])]
    assert all(entry["description"].strip() for entry in entries)

    registry_commands = set(registry.list_commands(name_format="slug"))
    grouped_slugs = [entry["slug"] for entry in entries]
    assert sorted(set(grouped_slugs) - registry_commands) == []
    assert sorted(registry_commands - set(grouped_slugs)) == []

    duplicate_slugs = sorted(slug for slug, count in Counter(grouped_slugs).items() if count > 1)
    assert duplicate_slugs == ["new-project"]
    new_project_usages = sorted(entry["command"] for entry in entries if entry["slug"] == "new-project")
    assert new_project_usages == ["gpd:new-project", "gpd:new-project --minimal"]


def test_help_workflow_public_blocks_match_help_renderer() -> None:
    renderer = _phase2_module("gpd.core.help_renderer")
    catalog = _build_help_catalog(renderer)
    workflow_help = HELP_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert _help_marker_range(workflow_help, "quick-start").strip() == _render_quick_start(renderer)
    assert _help_marker_range(workflow_help, "command-index").strip() == _render_command_index(renderer, catalog)


def test_raw_cli_help_all_payload_matches_help_renderer(tmp_path: Path) -> None:
    renderer = _phase2_module("gpd.core.help_renderer")
    catalog = _build_help_catalog(renderer)

    payload = _raw_help_payload(tmp_path, "--all")

    assert payload["quick_start"]["markdown"].strip() == _render_quick_start(renderer)
    assert payload["command_index_markdown"].strip() == _render_command_index(renderer, catalog)
    assert _normalize_command_groups(payload["command_groups"]) == _normalize_command_groups(
        _renderer_command_groups(renderer, catalog)
    )
