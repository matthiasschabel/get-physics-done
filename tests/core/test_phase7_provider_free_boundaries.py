"""Phase 7 provider-free boundary guards.

These tests are intentionally static: they parse workflow YAML and Python ASTs
without launching runtime/provider CLIs, touching credentials, or using the
network.
"""

from __future__ import annotations

import ast
import re
import shlex
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

from gpd.adapters.runtime_catalog import iter_runtime_descriptors
from tests.helpers.github_actions import (
    github_actions_workflow_paths,
    iter_workflow_steps,
    load_github_actions_workflow,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _launch_executable(command: str) -> str:
    try:
        parts = shlex.split(command)
    except ValueError:
        parts = []
    return Path(parts[0] if parts else command.strip()).name


_PROVIDER_LAUNCH_COMMANDS = tuple(
    sorted({_launch_executable(descriptor.launch_command) for descriptor in iter_runtime_descriptors()})
)
_PROVIDER_LAUNCH_COMMAND_SET = frozenset(_PROVIDER_LAUNCH_COMMANDS)
_SHELL_SEGMENT_SPLIT_RE = re.compile(r"(?:&&|\|\||[;|()])")
_SHELL_ASSIGNMENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*")
_PROVIDER_SECRET_ENV_RE = re.compile(
    r"(?<![A-Z0-9_])"
    r"(?:OPENAI|ANTHROPIC|CLAUDE|GEMINI|GOOGLE|CODEX|OPENCODE)_"
    r"(?:API_KEY|AUTH_TOKEN|OAUTH_TOKEN|ACCESS_TOKEN|SECRET|TOKEN|CREDENTIALS|CREDENTIALS_JSON|SERVICE_ACCOUNT)"
    r"(?![A-Z0-9_])"
)
_SPAWN_API_NAMES = frozenset(
    {
        "asyncio.create_subprocess_exec",
        "asyncio.create_subprocess_shell",
        "os.execl",
        "os.execle",
        "os.execlp",
        "os.execlpe",
        "os.execv",
        "os.execve",
        "os.execvp",
        "os.execvpe",
        "subprocess.Popen",
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
        "subprocess.run",
    }
)
_PROVIDER_OR_NETWORK_IMPORT_ROOTS = frozenset(
    {"aiohttp", "anthropic", "google", "httpx", "openai", "requests", "socket", "urllib", "websocket"}
)
_SHADOW_LIVE_PERSONA_POLICY_PYTHON_PATHS = (
    REPO_ROOT / "tests" / "helpers" / "phase7_live_like.py",
    REPO_ROOT / "tests" / "helpers" / "persona_summary.py",
)
_SHADOW_LIVE_PERSONA_POLICY_DOC_PATHS = (REPO_ROOT / "docs" / "dev" / "phase7-live-persona-canary.md",)


def _workflow_string_values(value: object, *, path: str = "$") -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, Mapping):
        for key, item in value.items():
            key_path = f"{path}.{key}"
            if isinstance(key, str):
                yield key_path, key
            yield from _workflow_string_values(item, path=key_path)
    elif isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        for index, item in enumerate(value):
            yield from _workflow_string_values(item, path=f"{path}[{index}]")


def _shell_tokens(segment: str) -> list[str]:
    try:
        return shlex.split(segment, comments=True)
    except ValueError:
        return []


def _provider_command_in_tokens(tokens: Sequence[str]) -> str | None:
    remaining = list(tokens)
    while remaining and _SHELL_ASSIGNMENT_RE.fullmatch(remaining[0]):
        remaining.pop(0)

    while remaining and remaining[0] in {"builtin", "command", "exec", "sudo", "time"}:
        remaining.pop(0)
        while remaining and _SHELL_ASSIGNMENT_RE.fullmatch(remaining[0]):
            remaining.pop(0)

    if remaining and remaining[0] == "env":
        remaining.pop(0)
        while remaining and (remaining[0].startswith("-") or _SHELL_ASSIGNMENT_RE.fullmatch(remaining[0])):
            remaining.pop(0)

    if len(remaining) >= 3 and remaining[:2] in (["uv", "run"], ["poetry", "run"], ["pipx", "run"]):
        remaining = remaining[2:]

    if remaining and remaining[0] in {"npx", "pnpm", "yarn"}:
        remaining.pop(0)
        while remaining and remaining[0].startswith("-"):
            remaining.pop(0)

    if len(remaining) >= 2 and remaining[:2] == ["npm", "exec"]:
        remaining = remaining[2:]
        while remaining and remaining[0].startswith("-"):
            remaining.pop(0)

    if not remaining:
        return None
    command = Path(remaining[0]).name
    return command if command in _PROVIDER_LAUNCH_COMMAND_SET else None


def _workflow_provider_launches(script: str) -> Iterator[tuple[int, str, str]]:
    for line_no, line in enumerate(script.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for segment in _SHELL_SEGMENT_SPLIT_RE.split(stripped):
            segment = segment.strip()
            if not segment:
                continue
            for prefix in ("if ", "while ", "until "):
                if segment.startswith(prefix):
                    segment = segment[len(prefix) :].strip()
                    break
            provider_command = _provider_command_in_tokens(_shell_tokens(segment))
            if provider_command is not None:
                yield line_no, provider_command, segment


def test_github_workflows_do_not_launch_catalog_provider_clis() -> None:
    failures: list[str] = []
    workflow_paths = github_actions_workflow_paths(REPO_ROOT)

    for path in workflow_paths:
        workflow = load_github_actions_workflow(path)
        for job_id, step in iter_workflow_steps(workflow):
            step_name = step.get("name", "<unnamed>")
            uses = step.get("uses")
            if isinstance(uses, str):
                action_owner = uses.split("/", 1)[0]
                if Path(action_owner).name in _PROVIDER_LAUNCH_COMMAND_SET:
                    failures.append(f"{path.relative_to(REPO_ROOT)}:{job_id}:{step_name}: uses {uses!r}")

            run_script = step.get("run")
            if not isinstance(run_script, str):
                continue
            for line_no, provider_command, segment in _workflow_provider_launches(run_script):
                failures.append(
                    f"{path.relative_to(REPO_ROOT)}:{job_id}:{step_name}: line {line_no} "
                    f"runs provider CLI {provider_command!r}: {segment}"
                )

    assert failures == [], (
        "GitHub PR/release workflows must not execute provider runtime launch commands "
        f"from the runtime catalog ({', '.join(_PROVIDER_LAUNCH_COMMANDS)}):\n" + "\n".join(failures)
    )


def test_github_workflows_do_not_reference_provider_secret_env_names() -> None:
    failures: list[str] = []

    for path in github_actions_workflow_paths(REPO_ROOT):
        relative = path.relative_to(REPO_ROOT)
        raw_text = path.read_text(encoding="utf-8")
        for match in _PROVIDER_SECRET_ENV_RE.finditer(raw_text):
            line_no = raw_text.count("\n", 0, match.start()) + 1
            failures.append(f"{relative}:{line_no}: raw workflow text references {match.group(0)}")

        workflow = load_github_actions_workflow(path)
        for workflow_path, value in _workflow_string_values(workflow):
            match = _PROVIDER_SECRET_ENV_RE.search(value)
            if match:
                failures.append(f"{relative}:{workflow_path}: parsed workflow value references {match.group(0)}")

    assert failures == [], (
        "GitHub PR/release workflows should not receive live provider secret env names; "
        "Phase 7 live credentials belong only in opt-in manual/nightly surfaces:\n" + "\n".join(failures)
    )


def _python_source_paths() -> list[Path]:
    roots = (REPO_ROOT / "src", REPO_ROOT / "scripts")
    return sorted(path for root in roots for path in root.rglob("*.py"))


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_name = alias.name.split(".", 1)[0]
                if root_name in {"asyncio", "os", "subprocess"}:
                    aliases[alias.asname or root_name] = root_name
        elif isinstance(node, ast.ImportFrom) and node.module in {"asyncio", "os", "subprocess"}:
            for alias in node.names:
                canonical = f"{node.module}.{alias.name}"
                if canonical in _SPAWN_API_NAMES:
                    aliases[alias.asname or alias.name] = canonical
    return aliases


def _imported_module_roots(tree: ast.AST) -> Iterator[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".", 1)[0]
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module.split(".", 1)[0]


def _call_name(func: ast.expr, aliases: Mapping[str, str]) -> str | None:
    if isinstance(func, ast.Name):
        return aliases.get(func.id)
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        root = aliases.get(func.value.id, func.value.id)
        return f"{root}.{func.attr}"
    return None


def _literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _literal_string_sequence(node: ast.AST) -> list[str] | None:
    if not isinstance(node, ast.List | ast.Tuple):
        return None
    values: list[str] = []
    for item in node.elts:
        literal = _literal_string(item)
        if literal is None:
            return None
        values.append(literal)
    return values


def _provider_command_in_shell_string(command: str) -> str | None:
    for segment in _SHELL_SEGMENT_SPLIT_RE.split(command):
        provider_command = _provider_command_in_tokens(_shell_tokens(segment.strip()))
        if provider_command is not None:
            return provider_command
    return None


def test_shadow_live_persona_policy_surfaces_do_not_define_provider_runners() -> None:
    failures: list[str] = []

    for path in _SHADOW_LIVE_PERSONA_POLICY_PYTHON_PATHS:
        relative = path.relative_to(REPO_ROOT)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for root in sorted(set(_imported_module_roots(tree)) & _PROVIDER_OR_NETWORK_IMPORT_ROOTS):
            failures.append(f"{relative}: imports provider/network module {root!r}")

        aliases = _import_aliases(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            call_name = _call_name(node.func, aliases)
            if call_name in _SPAWN_API_NAMES:
                failures.append(f"{relative}:{node.lineno}: uses process-spawn API {call_name}")

    for path in _SHADOW_LIVE_PERSONA_POLICY_DOC_PATHS:
        relative = path.relative_to(REPO_ROOT)
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            provider_command = _provider_command_in_shell_string(line)
            if provider_command is not None:
                failures.append(f"{relative}:{line_no}: documents provider launch command {provider_command!r}")

    assert failures == [], (
        "Phase 6 shadow-live persona policy surfaces must stay manual-only and must not define "
        "a provider runner, provider SDK/network import, process spawn, or provider command line:\n"
        + "\n".join(failures)
    )


def _spawn_call_provider_command(call: ast.Call, call_name: str) -> str | None:
    if not call.args:
        return None

    if call_name == "asyncio.create_subprocess_exec":
        first_arg = _literal_string(call.args[0])
        return _provider_command_in_tokens([first_arg]) if first_arg is not None else None

    if call_name == "asyncio.create_subprocess_shell":
        shell_command = _literal_string(call.args[0])
        return _provider_command_in_shell_string(shell_command) if shell_command is not None else None

    if call_name.startswith("os.exec"):
        executable = _literal_string(call.args[0])
        return _provider_command_in_tokens([executable]) if executable is not None else None

    argv = _literal_string_sequence(call.args[0])
    if argv is not None:
        return _provider_command_in_tokens(argv)

    shell_command = _literal_string(call.args[0])
    if shell_command is not None:
        return _provider_command_in_shell_string(shell_command)

    return None


def test_python_source_does_not_directly_spawn_provider_runtime_launch_commands() -> None:
    """Provider launch labels may appear as metadata, but not as process-spawn targets.

    The known non-executing cases are catalog/bootstrap metadata and Gemini's
    generated yolo wrapper string, which writes an opt-in launcher for a human to
    run later. This guard is therefore scoped to direct spawn APIs instead of
    banning catalog launch labels from source text.
    """
    failures: list[str] = []

    for path in _python_source_paths():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        aliases = _import_aliases(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            call_name = _call_name(node.func, aliases)
            if call_name not in _SPAWN_API_NAMES:
                continue
            provider_command = _spawn_call_provider_command(node, call_name)
            if provider_command is not None:
                failures.append(
                    f"{path.relative_to(REPO_ROOT)}:{node.lineno}: {call_name} launches {provider_command!r}"
                )

    assert failures == [], (
        "Python source must not directly launch provider CLIs via subprocess/Popen/create_subprocess/os.exec. "
        "Route GPD commands through the runtime bridge and keep provider launches opt-in/manual:\n"
        + "\n".join(failures)
    )
