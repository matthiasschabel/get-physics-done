"""Static guards for provider-free Phase 11 live-audit comparison files."""

from __future__ import annotations

import ast
import json
import os
import re
from collections.abc import Iterable, Mapping
from pathlib import Path

from gpd.adapters.runtime_catalog import iter_runtime_descriptors
from tests.ci_sharding import CI_CATEGORY_SHARD_COUNTS, category_for_test_relpath
from tests.helpers.github_actions import load_github_actions_workflow

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_ROOT = REPO_ROOT / "tests"
PHASE11_FIXTURE_ROOT = TESTS_ROOT / "fixtures" / "live_audit" / "phase11"
WORKFLOW_ROOT = REPO_ROOT / ".github" / "workflows"

PHASE11_ALLOWED_PATH_PATTERNS = (
    re.compile(r"^tests/adapters/test_phase11_[^/]+\.py$"),
    re.compile(r"^tests/fixtures/live_audit/phase11/"),
    re.compile(r"^tests/helpers/live_audit_harness/phase11[^/]*\.py$"),
    re.compile(r"^scripts/phase11_live_comparison_artifacts\.py$"),
)
PHASE11_ALLOWED_CI_CATEGORIES = {"adapters"}
WORKFLOW_ALLOWED_TRIGGERS = {"schedule", "workflow_dispatch"}
REPO_WALK_EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "tmp",
}
PROVIDER_MARKER_NAMES = {
    "fake_provider",
    "live_audit",
    "live_provider",
    "provider_live",
    "requires_live_provider",
    "requires_provider",
}
PROVIDER_SECRET_ENV_NAMES = frozenset(
    f"{provider}_API_KEY"
    for provider in (
        "ANTHROPIC",
        "CLAUDE",
        "CODEX",
        "GEMINI",
        "GOOGLE",
        "OPENAI",
        "OPENCODE",
    )
)
PROVIDER_SECRET_ENV_RE = re.compile(rf"\b(?:{'|'.join(sorted(PROVIDER_SECRET_ENV_NAMES))})\b")
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
NETWORK_IMPORT_PREFIXES = (
    "aiohttp",
    "grpc",
    "http.client",
    "httpx",
    "requests",
    "socket",
    "urllib.request",
    "urllib3",
    "websocket",
    "websockets",
)
RAW_FIELD_EXACT_KEYS = frozenset(
    {
        "apikey",
        "argv",
        "env",
        "environment",
        "homepath",
        "privatepath",
        "secret",
        "secrets",
        "stderr",
        "stdout",
        "token",
        "tokens",
        "transcript",
    }
)
RAW_FIELD_MARKERS = frozenset(
    {
        "accountemail",
        "accountidentifier",
        "accountid",
        "authfile",
        "authheader",
        "authpath",
        "authstate",
        "authorization",
        "credential",
        "envdump",
        "environmentdump",
        "homepath",
        "localpath",
        "password",
        "privatepath",
        "promptargv",
        "provideroutput",
        "providerstderr",
        "providerstdout",
        "rawauth",
        "rawenv",
        "rawpath",
        "rawprompt",
        "rawprovider",
        "rawtranscript",
        "realpath",
        "secret",
    }
)
SECRET_OR_PATH_PATTERNS = {
    "anthropic_api_key": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "bearer_token": re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    "google_api_key": re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    "linux_home": re.compile(r"(?<![A-Za-z0-9_/-])/home/[A-Za-z0-9._-]+"),
    "mac_home": re.compile(r"(?<![A-Za-z0-9_/-])/Users/[A-Za-z0-9._-]+"),
    "openai_api_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "private_key": re.compile(r"-----BEGIN (?:OPENSSH|RSA|EC|DSA|PRIVATE) KEY-----"),
    "secret_assignment": re.compile(r"(?i)\b(?:api[_-]?key|password|secret|token)\b[\"'\s:=]+[A-Za-z0-9._~+/=-]{16,}"),
    "tilde_home": re.compile(r"(?<![A-Za-z0-9_/-])~/[A-Za-z0-9._-]+"),
    "windows_home": re.compile(r"(?i)\b[A-Z]:\\Users\\[A-Za-z0-9._-]+"),
}
RAW_WORKFLOW_MARKERS = (
    "provider_output",
    "provider_stderr",
    "provider_stdout",
    "raw_provider",
    "raw_transcript",
)
MAX_PHASE11_FIXTURE_FILE_BYTES = 64 * 1024
MAX_PHASE11_FIXTURE_TREE_BYTES = 256 * 1024


def _repo_files() -> tuple[Path, ...]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = sorted(name for name in dirnames if name not in REPO_WALK_EXCLUDED_DIRS)
        root = Path(dirpath)
        files.extend(root / filename for filename in sorted(filenames))
    return tuple(files)


def _relpath(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _phase11_repo_files() -> tuple[Path, ...]:
    return tuple(path for path in _repo_files() if "phase11" in _relpath(path).casefold())


def _phase11_python_files() -> tuple[Path, ...]:
    return tuple(path for path in _phase11_repo_files() if path.suffix == ".py")


def _phase11_fixture_files() -> tuple[Path, ...]:
    if not PHASE11_FIXTURE_ROOT.exists():
        return ()
    return tuple(sorted(path for path in PHASE11_FIXTURE_ROOT.rglob("*") if path.is_file()))


def _python_test_relpath(path: Path) -> str | None:
    if path.suffix != ".py" or not path.name.startswith("test_"):
        return None
    try:
        return path.relative_to(TESTS_ROOT).as_posix()
    except ValueError:
        return None


def _string_literals(tree: ast.AST) -> Iterable[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value


def _imported_module_names(tree: ast.AST) -> Iterable[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            yield node.module


def _pytest_mark_names(tree: ast.AST) -> Iterable[str]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        mark_node = node.value
        if not isinstance(mark_node, ast.Attribute) or mark_node.attr != "mark":
            continue
        if isinstance(mark_node.value, ast.Name) and mark_node.value.id == "pytest":
            yield node.attr


def _import_aliases(tree: ast.AST) -> tuple[dict[str, str], dict[str, tuple[str, str]]]:
    modules: dict[str, str] = {}
    callables: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_name = alias.name.split(".", 1)[0]
                if any(module == root_name for module, _ in PROVIDER_LAUNCH_APIS):
                    modules[alias.asname or root_name] = root_name
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            module_name = node.module.split(".", 1)[0]
            for alias in node.names:
                if (module_name, alias.name) in PROVIDER_LAUNCH_APIS:
                    callables[alias.asname or alias.name] = (module_name, alias.name)
                if module_name == "os" and alias.name in {"environ", "getenv"}:
                    callables[alias.asname or alias.name] = (module_name, alias.name)
    return modules, callables


def _call_name(
    node: ast.Call, module_aliases: Mapping[str, str], callable_aliases: Mapping[str, tuple[str, str]]
) -> tuple[str, str] | None:
    func = node.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return module_aliases.get(func.value.id, func.value.id), func.attr
    if isinstance(func, ast.Name):
        return callable_aliases.get(func.id, ("", func.id))
    return None


def _reads_environment(node: ast.AST, callable_aliases: Mapping[str, tuple[str, str]]) -> bool:
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        if node.value.id == "os" and node.attr == "environ":
            return True
    if isinstance(node, ast.Name) and callable_aliases.get(node.id) == ("os", "environ"):
        return True
    if isinstance(node, ast.Call):
        call = _call_name(node, {}, callable_aliases)
        if call in {("os", "getenv"), ("os", "environ")}:
            return True
        if isinstance(node.func, ast.Attribute):
            owner = node.func.value
            if isinstance(owner, ast.Name) and callable_aliases.get(owner.id) == ("os", "environ"):
                return True
            if (
                isinstance(owner, ast.Attribute)
                and isinstance(owner.value, ast.Name)
                and owner.value.id == "os"
                and owner.attr == "environ"
                and node.func.attr in {"get", "setdefault"}
            ):
                return True
    return False


def _provider_launch_command_re() -> re.Pattern[str]:
    provider_commands = {re.escape(descriptor.launch_command) for descriptor in iter_runtime_descriptors()}
    launch_arguments = (
        "--approval-mode",
        "--model",
        "--prompt",
        "--sandbox",
        "--yolo",
        "-p",
        "chat",
        "exec",
        "run",
    )
    return re.compile(
        rf"(?m)(?<![-./\w])(?:{'|'.join(sorted(provider_commands))})\s+"
        rf"(?:{'|'.join(re.escape(argument) for argument in launch_arguments)})(?:\s|$)"
    )


def _json_records(path: Path) -> Iterable[object]:
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


def _provider_marker_value_hits(value: object, *, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, str):
        if value in PROVIDER_MARKER_NAMES:
            hits.append(path)
    elif isinstance(value, Mapping):
        for key, child in value.items():
            hits.extend(_provider_marker_value_hits(child, path=f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(_provider_marker_value_hits(child, path=f"{path}[{index}]"))
    return hits


def _workflow_trigger_names(workflow: Mapping[str, object]) -> set[str]:
    triggers = workflow["on"]
    if isinstance(triggers, str):
        return {triggers}
    if isinstance(triggers, list):
        return {str(trigger) for trigger in triggers}
    assert isinstance(triggers, Mapping)
    return {str(trigger) for trigger in triggers}


def _workflow_is_sanitized_only(text: str) -> bool:
    normalized = text.casefold()
    return (
        "sanitized" in normalized
        and not PROVIDER_SECRET_ENV_RE.search(text)
        and not any(marker in normalized for marker in RAW_WORKFLOW_MARKERS)
        and _provider_launch_command_re().search(text) is None
    )


def test_phase11_files_stay_inside_adapter_helper_fixture_and_script_boundaries() -> None:
    offenders = [
        _relpath(path)
        for path in _phase11_repo_files()
        if not any(pattern.match(_relpath(path)) for pattern in PHASE11_ALLOWED_PATH_PATTERNS)
    ]
    test_categories = {
        category_for_test_relpath(test_relpath)
        for path in _phase11_repo_files()
        if (test_relpath := _python_test_relpath(path)) is not None
    }

    assert offenders == []
    assert test_categories == PHASE11_ALLOWED_CI_CATEGORIES
    assert PHASE11_ALLOWED_CI_CATEGORIES <= set(CI_CATEGORY_SHARD_COUNTS)


def test_phase11_python_static_contract_stays_provider_free_in_default_pytest() -> None:
    provider_launch_command_re = _provider_launch_command_re()
    offenders: list[str] = []

    for path in _phase11_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relpath = _relpath(path)
        module_aliases, callable_aliases = _import_aliases(tree)
        provider_markers = PROVIDER_MARKER_NAMES & set(_pytest_mark_names(tree))
        if provider_markers:
            offenders.append(f"{relpath}: provider pytest marker(s) {', '.join(sorted(provider_markers))}")
        if any(_reads_environment(node, callable_aliases) for node in ast.walk(tree)):
            offenders.append(f"{relpath}: environment lookup")
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and _call_name(node, module_aliases, callable_aliases) in PROVIDER_LAUNCH_APIS
            ):
                offenders.append(f"{relpath}: provider launch API {_call_name(node, module_aliases, callable_aliases)}")
        imported_modules = set(_imported_module_names(tree))
        blocked_network_imports = sorted(
            module
            for module in imported_modules
            if any(module == prefix or module.startswith(f"{prefix}.") for prefix in NETWORK_IMPORT_PREFIXES)
        )
        if blocked_network_imports:
            offenders.append(f"{relpath}: network import(s) {', '.join(blocked_network_imports)}")
        literal_text = "\n".join(_string_literals(tree))
        match = provider_launch_command_re.search(literal_text)
        if match is not None:
            offenders.append(f"{relpath}: provider CLI launch string {match.group(0).strip()!r}")

    assert offenders == []


def test_phase11_github_actions_lanes_are_manual_or_scheduled_sanitized_only() -> None:
    offenders: list[str] = []
    for path in sorted({*WORKFLOW_ROOT.glob("*.yml"), *WORKFLOW_ROOT.glob("*.yaml")}):
        text = path.read_text(encoding="utf-8")
        if "phase11" not in f"{path.name}\n{text}".casefold():
            continue

        relpath = _relpath(path)
        trigger_names = _workflow_trigger_names(load_github_actions_workflow(path))
        unexpected_triggers = trigger_names - WORKFLOW_ALLOWED_TRIGGERS
        if unexpected_triggers:
            offenders.append(f"{relpath}: phase11 workflow trigger(s) {', '.join(sorted(unexpected_triggers))}")
        if not (trigger_names & WORKFLOW_ALLOWED_TRIGGERS):
            offenders.append(f"{relpath}: phase11 workflow lacks manual or scheduled trigger")
        if not _workflow_is_sanitized_only(text):
            offenders.append(f"{relpath}: phase11 workflow is not sanitized-only")

    assert offenders == []


def test_phase11_fixtures_stay_compact_class_only_and_provider_free() -> None:
    offenders: list[str] = []
    total_bytes = 0

    for path in _phase11_fixture_files():
        relpath = _relpath(path)
        size_bytes = path.stat().st_size
        total_bytes += size_bytes
        if size_bytes > MAX_PHASE11_FIXTURE_FILE_BYTES:
            offenders.append(f"{relpath}: {size_bytes} bytes exceeds {MAX_PHASE11_FIXTURE_FILE_BYTES}")

        text = path.read_text(encoding="utf-8")
        for name, pattern in SECRET_OR_PATH_PATTERNS.items():
            if pattern.search(text):
                offenders.append(f"{relpath}: {name}")
        if PROVIDER_SECRET_ENV_RE.search(text):
            offenders.append(f"{relpath}: provider secret env literal")
        if re.search(r'"(?:provider_subprocess_allowed|network_allowed)"\s*:\s*true', text):
            offenders.append(f"{relpath}: default-pytest provider/network escape hatch")

        for record in _json_records(path):
            offenders.extend(f"{relpath}: raw field {hit}" for hit in _raw_key_hits(record))
            offenders.extend(
                f"{relpath}: provider pytest marker value {hit}" for hit in _provider_marker_value_hits(record)
            )

    if total_bytes > MAX_PHASE11_FIXTURE_TREE_BYTES:
        offenders.append(f"phase11 fixture tree: {total_bytes} bytes exceeds {MAX_PHASE11_FIXTURE_TREE_BYTES}")

    assert offenders == []
