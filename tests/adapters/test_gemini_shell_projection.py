"""Structural Gemini shell projection regressions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pytest

from gpd.adapters.gemini import _gemini_policy_command_prefixes
from gpd.adapters.install_utils import project_markdown_for_runtime
from tests.adapters.projection_test_utils import (
    first_runnable_shell_command,
    runnable_shell_lines,
    runtime_bridge_command,
    shell_fences,
)
from tests.prompt_metrics_support import MarkdownFence

REPO_ROOT = Path(__file__).resolve().parents[2]
GPD_ROOT = REPO_ROOT / "src/gpd"
COMMANDS_DIR = GPD_ROOT / "commands"

FORBIDDEN_GEMINI_SHELL_FRAGMENTS = (
    "PROJECT_CONTRACT_JSON",
    "printf '%s\\n'",
    "mktemp",
    "<<",
    "if [ $? -ne 0 ]",
)
TARGET_STAGED_COMMAND_INIT_BY_NAME = {
    "plan-phase": '--raw init plan-phase "$ARGUMENTS" --stage phase_bootstrap',
    "execute-phase": '--raw init execute-phase "$ARGUMENTS" --stage phase_bootstrap',
    "new-project": "--raw init new-project --stage scope_intake",
    "write-paper": '--raw init write-paper --stage paper_bootstrap -- "$ARGUMENTS"',
}
LEADING_ASSIGNMENT_RE = re.compile(r"^[A-Z][A-Z0-9_]*=")
SHELL_CONTROL_PREFIXES = ("case ", "elif ", "else", "fi", "for ", "if ", "then", "while ")
TERMINAL_EXAMPLE_PREFIXES = (
    "./",
    "cat ",
    "cd ",
    "cp ",
    "curl ",
    "echo ",
    "find ",
    "git ",
    "gpd ",
    "grep ",
    "ls ",
    "mkdir ",
    "python ",
    "python3 ",
    "rm ",
    "sed ",
    "uv ",
)

GeminiShellClassification = Literal["runnable-bridge", "policy-static", "terminal-example", "pseudocode", "non-runnable"]


@dataclass(frozen=True, slots=True)
class GeminiShellPolicyOffender:
    label: str
    line_span: str
    classification: GeminiShellClassification
    detail: str

    def render(self) -> str:
        return f"{self.label}:{self.line_span} {self.classification}: {self.detail}"


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


def _project_new_project_workflow_probe(target_dir: Path) -> str:
    source = (
        "---\n"
        "name: gpd:new-project-workflow-probe\n"
        "description: New project workflow projection probe\n"
        "allowed-tools:\n"
        "  - shell\n"
        "---\n"
        "@{GPD_INSTALL_DIR}/workflows/new-project.md\n"
    )
    return project_markdown_for_runtime(
        source,
        runtime="gemini",
        path_prefix="./.gemini/",
        surface_kind="command",
        install_scope="--local",
        src_root=GPD_ROOT,
        workflow_target_dir=target_dir,
        command_name="new-project-workflow-probe",
    )


def _new_project_contract_section(projected: str) -> str:
    start_marker = "After approval, validate the contract before persisting it:"
    end_marker = "#### M2. Create PROJECT.md"
    start = projected.index(start_marker)
    end = projected.index(end_marker, start)
    return projected[start:end]


def _classify_rendered_gemini_shell_fence(
    fence: MarkdownFence,
    *,
    bridge: str,
    allowed_prefixes: tuple[str, ...],
) -> GeminiShellClassification:
    command = first_runnable_shell_command(fence)
    if command is None:
        return "non-runnable"
    if command.startswith(bridge):
        return "runnable-bridge"
    static_prefixes = tuple(prefix for prefix in allowed_prefixes if prefix != bridge)
    if command.startswith(static_prefixes):
        return "policy-static"
    if _looks_like_shell_pseudocode(fence.body, command):
        return "pseudocode"
    return "terminal-example"


def _looks_like_shell_pseudocode(body: str, command: str) -> bool:
    stripped = command.strip()
    if LEADING_ASSIGNMENT_RE.match(stripped):
        return True
    if stripped.startswith(SHELL_CONTROL_PREFIXES):
        return True
    if "$(" in body or "<<" in body:
        return True
    if "$ARGUMENTS" in body or "${" in body:
        return True
    if "<" in body and ">" in body and "```" not in body:
        return True
    return False


def _gemini_shell_policy_offenders(
    text: str,
    *,
    bridge: str,
    label: str,
) -> tuple[GeminiShellPolicyOffender, ...]:
    allowed_prefixes = _gemini_policy_command_prefixes(bridge)
    offenders: list[GeminiShellPolicyOffender] = []

    for fence in shell_fences(text):
        line_span = f"{fence.start_line}-{fence.end_line}"
        command = first_runnable_shell_command(fence)
        classification = _classify_rendered_gemini_shell_fence(
            fence,
            bridge=bridge,
            allowed_prefixes=allowed_prefixes,
        )

        if classification not in {"runnable-bridge", "policy-static"}:
            detail = command or "no runnable command"
            if command and command.startswith(TERMINAL_EXAMPLE_PREFIXES):
                detail = f"terminal command rendered as executable shell: {command}"
            offenders.append(GeminiShellPolicyOffender(label, line_span, classification, detail))
        elif command is None or not command.startswith(allowed_prefixes):
            offenders.append(
                GeminiShellPolicyOffender(
                    label,
                    line_span,
                    classification,
                    command or "no runnable command",
                )
            )

        for fragment in FORBIDDEN_GEMINI_SHELL_FRAGMENTS:
            if fragment in fence.body:
                offenders.append(
                    GeminiShellPolicyOffender(label, line_span, "pseudocode", f"unsafe fragment {fragment!r}")
                )
        for line in runnable_shell_lines(fence):
            if LEADING_ASSIGNMENT_RE.match(line):
                offenders.append(GeminiShellPolicyOffender(label, line_span, "pseudocode", f"leading assignment {line!r}"))

    return tuple(offenders)


def _format_gemini_shell_policy_offenders(offenders: tuple[GeminiShellPolicyOffender, ...]) -> str:
    if not offenders:
        return ""
    return "Rendered Gemini shell-policy offenders:\n" + "\n".join(offender.render() for offender in offenders)


def _assert_gemini_shell_fences_are_policy_runnable(text: str, *, bridge: str, label: str) -> None:
    fences = shell_fences(text)
    assert fences, f"{label} should expose at least one Gemini shell fence"
    allowed_prefixes = _gemini_policy_command_prefixes(bridge)
    offenders = []

    for fence in fences:
        command = first_runnable_shell_command(fence)
        if command is None:
            offenders.append(f"lines {fence.start_line}-{fence.end_line}: no runnable command")
        elif not command.startswith(allowed_prefixes):
            offenders.append(f"lines {fence.start_line}-{fence.end_line}: {command}")

    assert offenders == []


def _assert_no_unsafe_gemini_shell_shape(text: str, *, label: str) -> None:
    offenders = []
    for fence in shell_fences(text):
        for fragment in FORBIDDEN_GEMINI_SHELL_FRAGMENTS:
            if fragment in fence.body:
                offenders.append(f"lines {fence.start_line}-{fence.end_line}: contains {fragment!r}")
        for line in runnable_shell_lines(fence):
            if LEADING_ASSIGNMENT_RE.match(line):
                offenders.append(f"lines {fence.start_line}-{fence.end_line}: leading assignment {line!r}")

    assert offenders == [], f"{label} has unsafe Gemini shell projection: {offenders}"


@pytest.mark.parametrize("command_name", tuple(TARGET_STAGED_COMMAND_INIT_BY_NAME))
def test_gemini_target_staged_command_projection_is_single_safe_bridge_bootstrap(
    command_name: str,
    tmp_path: Path,
) -> None:
    target_dir = tmp_path / ".gemini"
    bridge = runtime_bridge_command("gemini", target_dir)
    projected = _project_gemini_command(command_name, target_dir)
    expected_command = f"{bridge} {TARGET_STAGED_COMMAND_INIT_BY_NAME[command_name]}"

    _assert_gemini_shell_fences_are_policy_runnable(projected, bridge=bridge, label=command_name)
    _assert_no_unsafe_gemini_shell_shape(projected, label=command_name)
    assert tuple(
        command
        for fence in shell_fences(projected)
        if (command := first_runnable_shell_command(fence))
    ) == (expected_command,)


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
            lambda target_dir: _new_project_contract_section(_project_new_project_workflow_probe(target_dir)),
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
    bridge = runtime_bridge_command("gemini", target_dir)
    projected = projected_text(target_dir)

    _assert_gemini_shell_fences_are_policy_runnable(projected, bridge=bridge, label=label)
    _assert_no_unsafe_gemini_shell_shape(projected, label=label)


def test_gemini_expanded_command_corpus_has_zero_rendered_shell_policy_offenders(tmp_path: Path) -> None:
    target_dir = tmp_path / ".gemini"
    bridge = runtime_bridge_command("gemini", target_dir)
    offenders: list[GeminiShellPolicyOffender] = []
    shell_fence_count = 0

    command_paths = sorted(COMMANDS_DIR.glob("*.md"))
    assert command_paths, "Gemini command corpus should contain real command markdown files"

    for command_path in command_paths:
        projected = project_markdown_for_runtime(
            command_path.read_text(encoding="utf-8"),
            runtime="gemini",
            path_prefix="./.gemini/",
            surface_kind="command",
            install_scope="--local",
            src_root=GPD_ROOT,
            workflow_target_dir=target_dir,
            command_name=command_path.stem,
        )
        assert "{GPD_INSTALL_DIR}" not in projected
        assert "{GPD_AGENTS_DIR}" not in projected
        shell_fence_count += len(shell_fences(projected))
        offenders.extend(
            _gemini_shell_policy_offenders(
                projected,
                bridge=bridge,
                label=f"commands/{command_path.name}",
            )
        )

    assert len(command_paths) >= 50
    assert shell_fence_count > 0
    assert tuple(offenders) == (), _format_gemini_shell_policy_offenders(tuple(offenders))
