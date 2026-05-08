"""Static guards for Phase 8 provider-free default collection."""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path

import tests.helpers.live_audit_harness as live_audit_harness
from gpd.adapters.runtime_catalog import iter_runtime_descriptors

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_ROOT = REPO_ROOT / "tests" / "helpers" / "live_audit_harness"
PHASE8_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "live_audit" / "phase8"
TEST_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "test.yml"

PROVIDER_SECRET_ENV_NAMES = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "CLAUDE_API_KEY",
        "CODEX_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "OPENCODE_API_KEY",
    }
)
PROVIDER_SECRET_ENV_RE = re.compile(rf"\b(?:{'|'.join(sorted(PROVIDER_SECRET_ENV_NAMES))})\b")
RAW_FIELD_EXACT_KEYS = frozenset({"argv", "env", "stderr", "stdout", "transcript"})
RAW_FIELD_MARKERS = frozenset(
    {
        "authheader",
        "authstate",
        "envdump",
        "environmentdump",
        "provideroutput",
        "providerstderr",
        "providerstdout",
        "rawauth",
        "rawpath",
        "rawprompt",
        "rawprovider",
        "rawtranscript",
    }
)
SECRET_OR_PATH_PATTERNS = {
    "anthropic_api_key": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "bearer_token": re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    "google_api_key": re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    "mac_home": re.compile(r"(?<![A-Za-z0-9_/-])/Users/[A-Za-z0-9._-]+"),
    "openai_api_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "private_key": re.compile(r"-----BEGIN (?:OPENSSH|RSA|EC|DSA|PRIVATE) KEY-----"),
    "secret_assignment": re.compile(r"(?i)\b(?:api[_-]?key|password|secret|token)\b[\"'\s:=]+[A-Za-z0-9._~+/=-]{16,}"),
    "tilde_home": re.compile(r"(?<![A-Za-z0-9_/-])~/[A-Za-z0-9._-]+"),
    "windows_home": re.compile(r"(?i)\b[A-Z]:\\Users\\[A-Za-z0-9._-]+"),
}
PROVIDER_LAUNCH_APIS = {
    ("asyncio", "create_subprocess_exec"),
    ("asyncio", "create_subprocess_shell"),
    ("os", "popen"),
    ("os", "spawnl"),
    ("os", "spawnle"),
    ("os", "spawnlp"),
    ("os", "spawnlpe"),
    ("os", "spawnv"),
    ("os", "spawnve"),
    ("os", "spawnvp"),
    ("os", "spawnvpe"),
    ("os", "system"),
    ("pexpect", "spawn"),
    ("subprocess", "call"),
    ("subprocess", "check_call"),
    ("subprocess", "check_output"),
    ("subprocess", "Popen"),
    ("subprocess", "run"),
}


def _python_files(root: Path) -> tuple[Path, ...]:
    return tuple(sorted(path for path in root.glob("*.py") if path.is_file()))


def _fixture_files(root: Path) -> tuple[Path, ...]:
    if not root.exists():
        return ()
    return tuple(sorted(path for path in root.rglob("*") if path.is_file()))


def _string_literals(tree: ast.AST) -> Iterable[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value


def _call_name(node: ast.Call) -> tuple[str, str] | None:
    func = node.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return func.value.id, func.attr
    if isinstance(func, ast.Name):
        return "", func.id
    return None


def _reads_environment(node: ast.AST) -> bool:
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
        return isinstance(node.value.value, ast.Name) and node.value.value.id == "os" and node.value.attr == "environ"
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        owner = node.func.value
        if isinstance(owner, ast.Name) and owner.id == "os" and node.func.attr == "getenv":
            return True
        if (
            isinstance(owner, ast.Attribute)
            and isinstance(owner.value, ast.Name)
            and owner.value.id == "os"
            and owner.attr == "environ"
            and node.func.attr == "get"
        ):
            return True
    return False


def _workflow_run_script_text(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    scripts: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        match = re.match(r"^(?P<indent>\s*)run:\s*(?P<value>.*)$", line)
        if match is None:
            index += 1
            continue
        value = match.group("value").strip()
        if value and value[0] not in {"|", ">"}:
            scripts.append(value)
            index += 1
            continue
        run_indent = len(match.group("indent"))
        block: list[str] = []
        index += 1
        while index < len(lines):
            next_line = lines[index]
            if next_line.strip() and len(next_line) - len(next_line.lstrip()) <= run_indent:
                break
            block.append(next_line)
            index += 1
        scripts.append("\n".join(block))
    return "\n".join(scripts)


def _phase8_fixture_records(path: Path) -> Iterable[object]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        yield json.loads(text)
    elif path.suffix == ".jsonl":
        for line in text.splitlines():
            if line.strip():
                yield json.loads(line)
    else:
        yield text


def _raw_key_hits(value: object, *, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized_key = re.sub(r"[^a-z0-9]+", "", str(key).casefold())
            if normalized_key in RAW_FIELD_EXACT_KEYS or any(marker in normalized_key for marker in RAW_FIELD_MARKERS):
                hits.append(f"{path}.{key}")
            hits.extend(_raw_key_hits(child, path=f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(_raw_key_hits(child, path=f"{path}[{index}]"))
    return hits


def test_phase8_default_harness_does_not_launch_providers_or_read_provider_secrets() -> None:
    assert live_audit_harness.PROVIDER_SUBPROCESS_ALLOWED is False

    offenders: list[str] = []
    for path in _python_files(HARNESS_ROOT):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relpath = path.relative_to(REPO_ROOT).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _call_name(node) in PROVIDER_LAUNCH_APIS:
                offenders.append(f"{relpath}: provider launch API {_call_name(node)}")
            if _reads_environment(node):
                offenders.append(f"{relpath}: environment lookup")
        if PROVIDER_SECRET_ENV_RE.search("\n".join(_string_literals(tree))):
            offenders.append(f"{relpath}: provider secret env literal")

    assert offenders == []


def test_default_test_workflow_remains_provider_free() -> None:
    workflow_text = TEST_WORKFLOW.read_text(encoding="utf-8")
    run_scripts = _workflow_run_script_text(TEST_WORKFLOW)
    provider_commands = {descriptor.launch_command for descriptor in iter_runtime_descriptors()}
    provider_command_re = re.compile(rf"(?m)(?<![-./\w])(?:{'|'.join(sorted(provider_commands))})(?:\s|$)")

    assert "live_provider" not in workflow_text
    assert "requires_live_provider" not in workflow_text
    assert PROVIDER_SECRET_ENV_RE.search(workflow_text) is None
    assert provider_command_re.search(run_scripts) is None


def test_phase8_fixture_files_are_secret_path_and_raw_field_clean() -> None:
    offenders: list[str] = []
    for path in _fixture_files(PHASE8_FIXTURE_ROOT):
        relpath = path.relative_to(REPO_ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        for name, pattern in SECRET_OR_PATH_PATTERNS.items():
            if pattern.search(text):
                offenders.append(f"{relpath}: {name}")
        for record in _phase8_fixture_records(path):
            offenders.extend(f"{relpath}: raw field {hit}" for hit in _raw_key_hits(record))

    assert offenders == []
