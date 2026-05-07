"""Structural Gemini shell projection regressions."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from gpd.adapters.gemini import _gemini_policy_command_prefixes
from gpd.adapters.install_utils import (
    DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES,
    build_runtime_cli_bridge_command,
    project_markdown_for_runtime,
)
from tests.prompt_metrics_support import MarkdownFence, iter_markdown_fences

REPO_ROOT = Path(__file__).resolve().parents[2]
GPD_ROOT = REPO_ROOT / "src/gpd"
COMMANDS_DIR = GPD_ROOT / "commands"

FORBIDDEN_GEMINI_SHELL_FRAGMENTS = (
    "PROJECT_CONTRACT_JSON",
    "printf '%s\\n'",
    "mktemp",
    "<<",
)
LEADING_ASSIGNMENT_RE = re.compile(r"^[A-Z][A-Z0-9_]*=")


def _bridge_for_projection(target_dir: Path) -> str:
    return build_runtime_cli_bridge_command(
        "gemini",
        target_dir=target_dir,
        config_dir_name=".gemini",
        is_global=False,
    )


def _project_gemini_command(command_name: str, target_dir: Path) -> str:
    return project_markdown_for_runtime(
        (COMMANDS_DIR / f"{command_name}.md").read_text(encoding="utf-8"),
        runtime="gemini",
        path_prefix="./.gemini/",
        surface_kind="command",
        install_scope="--local",
        src_root=GPD_ROOT,
        workflow_target_dir=target_dir,
        command_name=command_name,
    )


def _project_contract_schema_probe(target_dir: Path) -> str:
    source = (
        "---\n"
        "name: gpd:contract-schema-probe\n"
        "description: Contract schema projection probe\n"
        "allowed-tools:\n"
        "  - shell\n"
        "---\n"
        "@{GPD_INSTALL_DIR}/templates/project-contract-schema.md\n"
    )
    return project_markdown_for_runtime(
        source,
        runtime="gemini",
        path_prefix="./.gemini/",
        surface_kind="command",
        install_scope="--local",
        src_root=GPD_ROOT,
        workflow_target_dir=target_dir,
        command_name="contract-schema-probe",
    )


def _new_project_contract_section(projected: str) -> str:
    start_marker = "After approval, validate the contract before persisting it:"
    end_marker = "#### M2. Create PROJECT.md"
    start = projected.index(start_marker)
    end = projected.index(end_marker, start)
    return projected[start:end]


def _shell_fences(text: str) -> tuple[MarkdownFence, ...]:
    return tuple(
        fence
        for fence in iter_markdown_fences(text)
        if fence.info.lower() in DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES
    )


def _runnable_shell_lines(fence: MarkdownFence) -> tuple[str, ...]:
    return tuple(
        stripped
        for line in fence.body.splitlines()
        if (stripped := line.strip()) and not stripped.startswith("#")
    )


def _first_runnable_shell_command(fence: MarkdownFence) -> str | None:
    lines = _runnable_shell_lines(fence)
    return lines[0] if lines else None


def _assert_gemini_shell_fences_are_policy_runnable(text: str, *, bridge: str, label: str) -> None:
    fences = _shell_fences(text)
    assert fences, f"{label} should expose at least one Gemini shell fence"
    allowed_prefixes = _gemini_policy_command_prefixes(bridge)
    offenders = []

    for fence in fences:
        command = _first_runnable_shell_command(fence)
        if command is None:
            offenders.append(f"lines {fence.start_line}-{fence.end_line}: no runnable command")
        elif not command.startswith(allowed_prefixes):
            offenders.append(f"lines {fence.start_line}-{fence.end_line}: {command}")

    assert offenders == []


def _assert_no_unsafe_gemini_shell_shape(text: str, *, label: str) -> None:
    offenders = []
    for fence in _shell_fences(text):
        for fragment in FORBIDDEN_GEMINI_SHELL_FRAGMENTS:
            if fragment in fence.body:
                offenders.append(f"lines {fence.start_line}-{fence.end_line}: contains {fragment!r}")
        for line in _runnable_shell_lines(fence):
            if LEADING_ASSIGNMENT_RE.match(line):
                offenders.append(f"lines {fence.start_line}-{fence.end_line}: leading assignment {line!r}")

    assert offenders == [], f"{label} has unsafe Gemini shell projection: {offenders}"


@pytest.mark.parametrize(
    ("label", "projected_text"),
    (
        pytest.param(
            "health command",
            lambda target_dir: _project_gemini_command("health", target_dir),
            id="health",
        ),
        pytest.param(
            "new-project contract section",
            lambda target_dir: _new_project_contract_section(_project_gemini_command("new-project", target_dir)),
            id="new-project-contract",
        ),
        pytest.param(
            "contract schema include",
            _project_contract_schema_probe,
            id="contract-schema",
        ),
    ),
)
def test_gemini_projected_shell_fences_use_policy_prefixes_and_safe_shapes(
    label: str,
    projected_text,
    tmp_path: Path,
) -> None:
    target_dir = tmp_path / ".gemini"
    bridge = _bridge_for_projection(target_dir)
    projected = projected_text(target_dir)

    _assert_gemini_shell_fences_are_policy_runnable(projected, bridge=bridge, label=label)
    _assert_no_unsafe_gemini_shell_shape(projected, label=label)
