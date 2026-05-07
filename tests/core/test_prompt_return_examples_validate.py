"""Regression coverage for visible ``gpd_return`` YAML examples."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from gpd.core.return_contract import validate_gpd_return_markdown

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPT_EXAMPLE_ROOTS = (
    REPO_ROOT / "src" / "gpd" / "agents",
    REPO_ROOT / "src" / "gpd" / "specs" / "workflows",
)
REFERENCE_EXAMPLE_PATHS = (
    REPO_ROOT / "src" / "gpd" / "specs" / "references" / "execution" / "executor-completion.md",
    REPO_ROOT / "src" / "gpd" / "specs" / "references" / "orchestration" / "agent-infrastructure.md",
)
AGENTS_DIR = REPO_ROOT / "src" / "gpd" / "agents"
YAML_FENCE_RE = re.compile(r"^```ya?ml[^\n]*\n(?P<body>.*?)(?:\n^```[ \t]*$)", re.MULTILINE | re.DOTALL)


def _candidate_markdown_files() -> Iterable[Path]:
    for root in PROMPT_EXAMPLE_ROOTS:
        yield from sorted(root.rglob("*.md"))
    yield from REFERENCE_EXAMPLE_PATHS


def test_visible_gpd_return_yaml_examples_match_return_contract() -> None:
    failures: list[str] = []
    checked_examples = 0

    for path in _candidate_markdown_files():
        text = path.read_text(encoding="utf-8")
        for match in YAML_FENCE_RE.finditer(text):
            body = match.group("body")
            if "gpd_return" not in body:
                continue
            checked_examples += 1
            result = validate_gpd_return_markdown(f"```yaml\n{body.rstrip()}\n```")
            if result.passed:
                continue

            relative_path = path.relative_to(REPO_ROOT).as_posix()
            line_number = text.count("\n", 0, match.start()) + 1
            errors = "; ".join(result.errors)
            failures.append(f"{relative_path}:{line_number}: {errors}")

    assert checked_examples > 0
    assert not failures, "Invalid gpd_return YAML examples:\n" + "\n".join(failures)


def test_agent_return_examples_use_canonical_status_profile_reference() -> None:
    infra = (REFERENCE_EXAMPLE_PATHS[1]).read_text(encoding="utf-8")
    assert "Status vocabulary and base fields are canonical here." in infra
    assert "return skeleton/profile source" in infra

    offenders = []
    for path in sorted(AGENTS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if "Use only status names:" in text:
            offenders.append(path.relative_to(REPO_ROOT).as_posix())

    assert offenders == []
