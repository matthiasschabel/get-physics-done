"""Sync checks for generated help workflow marker bodies."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_workflow_help() -> str:
    return (_repo_root() / "src/gpd/specs/workflows/help.md").read_text(encoding="utf-8")


def _range(content: str, start_marker: str, end_marker: str) -> str:
    start = content.index(start_marker) + len(start_marker)
    end = content.index(end_marker, start)
    return content[start:end]


def _help_marker_range(content: str, marker_name: str) -> str:
    start_marker = f"<!-- gpd-help:{marker_name}:start -->"
    end_marker = f"<!-- gpd-help:{marker_name}:end -->"
    return _range(content, start_marker, end_marker)


def _normalized_block(text: str) -> str:
    return text.strip().replace("\r\n", "\n")


def _help_renderer() -> object:
    return pytest.importorskip(
        "gpd.core.help_renderer",
        reason="Worker B help renderer API has not landed in this checkout yet",
    )


def _rendered_markdown(result: object) -> str:
    if isinstance(result, str):
        return _normalized_block(result)
    markdown = getattr(result, "markdown", None)
    if isinstance(markdown, str):
        return _normalized_block(markdown)
    pytest.fail(f"expected renderer result to be markdown text, got {type(result)!r}")


def _call_with_supported_kwargs(function: object, /, **kwargs: object) -> object:
    signature = inspect.signature(function)
    supported_kwargs = {name: value for name, value in kwargs.items() if name in signature.parameters}
    return function(**supported_kwargs)


def _build_catalog(renderer: object) -> object:
    build_help_catalog = getattr(renderer, "build_help_catalog", None)
    if build_help_catalog is None:
        pytest.fail("gpd.core.help_renderer must expose build_help_catalog()")
    return build_help_catalog()


def _render_quick_start(renderer: object) -> str:
    render_quick_start = getattr(renderer, "render_quick_start", None)
    if render_quick_start is None:
        pytest.fail("gpd.core.help_renderer must expose render_quick_start()")
    return _rendered_markdown(_call_with_supported_kwargs(render_quick_start, public_prefix="gpd:"))


def _render_command_index(renderer: object) -> str:
    render_command_index = getattr(renderer, "render_command_index", None)
    if render_command_index is None:
        pytest.fail("gpd.core.help_renderer must expose render_command_index()")

    catalog = _build_catalog(renderer)
    signature = inspect.signature(render_command_index)
    parameters = signature.parameters
    if "catalog" in parameters:
        result = _call_with_supported_kwargs(
            render_command_index,
            catalog=catalog,
            public_prefix="gpd:",
            include_quick_start=False,
        )
    else:
        result = _call_with_supported_kwargs(
            render_command_index,
            public_prefix="gpd:",
            include_quick_start=False,
        )
    return _rendered_markdown(result)


def test_help_quick_start_marker_matches_renderer_output() -> None:
    renderer = _help_renderer()
    workflow_help = _read_workflow_help()

    checked_in_quick_start = _normalized_block(_help_marker_range(workflow_help, "quick-start"))
    assert checked_in_quick_start == _render_quick_start(renderer)


def test_help_command_index_marker_matches_renderer_output() -> None:
    renderer = _help_renderer()
    workflow_help = _read_workflow_help()

    checked_in_command_index = _normalized_block(_help_marker_range(workflow_help, "command-index"))
    assert checked_in_command_index == _render_command_index(renderer)
