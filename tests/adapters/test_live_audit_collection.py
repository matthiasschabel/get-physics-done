from __future__ import annotations

import ast
import importlib
import json
import re
import subprocess
from collections.abc import Iterable
from pathlib import Path

from tests.ci_sharding import CI_CATEGORY_SHARD_COUNTS, category_for_test_relpath

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_ROOT = REPO_ROOT / "tests"
HELPER_PACKAGE = "tests.helpers.live_audit_harness"
HELPER_ROOT = TESTS_ROOT / "helpers" / "live_audit_harness"
FIXTURE_ROOT = TESTS_ROOT / "fixtures" / "live_audit"
SCENARIO_FIXTURE = FIXTURE_ROOT / "scenarios.json"

LIVE_AUDIT_ALLOWED_PREFIXES = (
    "adapters/test_live_audit_",
    "fixtures/live_audit/",
    "helpers/live_audit_harness/",
)
LIVE_AUDIT_ALLOWED_CI_CATEGORIES = {"adapters"}
FORBIDDEN_TMP_LIVE_AUDIT_DIRS = tuple(
    (Path("tmp") / ignored_dir).as_posix() for ignored_dir in ("live-audit", "live-audit-v2", "live-audit-v3")
)
FORBIDDEN_TMP_LIVE_AUDIT_MODULES = ("tmp.live_audit", "tmp.live_audit_v2", "tmp.live_audit_v3")
PROVIDER_MARKER_NAMES = {
    "fake_provider",
    "live_audit",
    "live_provider",
    "provider_live",
    "requires_live_provider",
    "requires_provider",
}
OBVIOUS_SECRET_PATTERNS = {
    "anthropic_api_key": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "bearer_token": re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    "google_api_key": re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    "openai_api_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "private_key": re.compile(r"-----BEGIN (?:OPENSSH|RSA|EC|DSA|PRIVATE) KEY-----"),
    "secret_assignment": re.compile(r"(?i)\b(?:api[_-]?key|password|secret|token)\b[\"'\s:=]+[A-Za-z0-9._~+/=-]{16,}"),
    "slack_token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
}
REAL_HOME_PATH_PATTERNS = {
    "linux_home": re.compile(r"(?<![A-Za-z0-9_/-])/home/[A-Za-z0-9._-]+"),
    "mac_home": re.compile(r"(?<![A-Za-z0-9_/-])/Users/[A-Za-z0-9._-]+"),
    "tilde_home": re.compile(r"(?<![A-Za-z0-9_/-])~/[A-Za-z0-9._-]+"),
    "windows_home": re.compile(r"(?i)\b[A-Z]:\\Users\\[A-Za-z0-9._-]+"),
}


def _git_ls_files(*pathspecs: str) -> tuple[str, ...]:
    result = subprocess.run(
        ["git", "ls-files", "--", *pathspecs],
        check=True,
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        text=True,
    )
    return tuple(line for line in result.stdout.splitlines() if line)


def _tracked_test_python_files() -> tuple[Path, ...]:
    return tuple(REPO_ROOT / relpath for relpath in _git_ls_files("tests") if relpath.endswith(".py"))


def _live_audit_files_under_tests() -> tuple[str, ...]:
    relpaths: list[str] = []
    for path in TESTS_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        relpath = path.relative_to(TESTS_ROOT).as_posix()
        if "live_audit" in relpath or "live-audit" in relpath:
            relpaths.append(relpath)
    return tuple(sorted(relpaths))


def _python_test_relpaths(relpaths: Iterable[str]) -> tuple[str, ...]:
    return tuple(relpath for relpath in relpaths if relpath.endswith(".py") and Path(relpath).name.startswith("test_"))


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


def _has_provider_env_lookup(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
            if isinstance(node.value.value, ast.Name) and node.value.value.id == "os" and node.value.attr == "environ":
                return True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr not in {"getenv", "setdefault", "get"}:
                continue
            owner = node.func.value
            if isinstance(owner, ast.Name) and owner.id == "os":
                return True
            if isinstance(owner, ast.Attribute) and owner.attr == "environ":
                if isinstance(owner.value, ast.Name) and owner.value.id == "os":
                    return True
    return False


def test_live_audit_helper_package_is_importable_and_layout_exists() -> None:
    module = importlib.import_module(HELPER_PACKAGE)

    assert HELPER_ROOT.is_dir()
    assert (HELPER_ROOT / "__init__.py").is_file()
    assert module.HARNESS_CONTRACT_ID == "phase7-live-audit-harness"
    assert module.PROVIDER_SUBPROCESS_ALLOWED is False


def test_tracked_tests_do_not_import_ignored_live_audit_tmp_harnesses() -> None:
    offenders: list[str] = []
    for path in _tracked_test_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relpath = path.relative_to(REPO_ROOT).as_posix()
        if any(module.startswith(FORBIDDEN_TMP_LIVE_AUDIT_MODULES) for module in _imported_module_names(tree)):
            offenders.append(relpath)
            continue
        for literal in _string_literals(tree):
            normalized_literal = literal.replace("\\", "/")
            if any(forbidden_dir in normalized_literal for forbidden_dir in FORBIDDEN_TMP_LIVE_AUDIT_DIRS):
                offenders.append(relpath)
                break

    assert offenders == []


def test_live_audit_paths_stay_inside_existing_pytest_ci_categories() -> None:
    relpaths = _live_audit_files_under_tests()
    misplaced = [
        relpath
        for relpath in relpaths
        if not any(relpath.startswith(allowed_prefix) for allowed_prefix in LIVE_AUDIT_ALLOWED_PREFIXES)
    ]
    test_categories = {category_for_test_relpath(relpath) for relpath in _python_test_relpaths(relpaths)}

    assert misplaced == []
    assert test_categories <= LIVE_AUDIT_ALLOWED_CI_CATEGORIES
    assert LIVE_AUDIT_ALLOWED_CI_CATEGORIES <= set(CI_CATEGORY_SHARD_COUNTS)


def test_live_audit_default_pytest_collection_needs_no_provider_markers_or_env_gates() -> None:
    offenders: list[str] = []
    for relpath in _live_audit_files_under_tests():
        if not relpath.endswith(".py"):
            continue
        path = TESTS_ROOT / relpath
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        provider_markers = PROVIDER_MARKER_NAMES & set(_pytest_mark_names(tree))
        if provider_markers or _has_provider_env_lookup(tree):
            offenders.append(relpath)

    assert offenders == []


def test_live_audit_fixture_tree_has_no_obvious_secrets_or_real_home_paths() -> None:
    assert FIXTURE_ROOT.is_dir()

    offenders: list[str] = []
    for path in sorted(item for item in FIXTURE_ROOT.rglob("*") if item.is_file()):
        content = path.read_text(encoding="utf-8")
        hits = [
            name
            for name, pattern in {**OBVIOUS_SECRET_PATTERNS, **REAL_HOME_PATH_PATTERNS}.items()
            if pattern.search(content)
        ]
        if hits:
            relpath = path.relative_to(REPO_ROOT).as_posix()
            offenders.append(f"{relpath}: {', '.join(sorted(hits))}")

    assert offenders == []


def test_live_audit_scenario_fixtures_exist() -> None:
    assert SCENARIO_FIXTURE.is_file()

    payload = json.loads(SCENARIO_FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    assert isinstance(payload.get("scenario_set_id"), str)
    rows = payload.get("scenario_rows")
    assert isinstance(rows, list) and rows
    assert all(isinstance(row, dict) for row in rows)
    assert all(isinstance(row.get("row_id"), str) and row["row_id"] for row in rows)
    assert all(isinstance(row.get("scenario_id"), str) and row["scenario_id"] for row in rows)
    assert all(row.get("provider_launch_allowed") is False for row in rows)
