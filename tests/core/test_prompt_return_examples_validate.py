"""Regression coverage for visible ``gpd_return`` YAML examples."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from tests.return_example_support import extract_gpd_return_examples, validate_gpd_return_examples

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


def _candidate_markdown_files() -> Iterable[Path]:
    for root in PROMPT_EXAMPLE_ROOTS:
        yield from sorted(root.rglob("*.md"))
    yield from REFERENCE_EXAMPLE_PATHS


def test_visible_gpd_return_yaml_examples_match_return_contract() -> None:
    failures: list[str] = []
    checked_examples = 0

    for path in _candidate_markdown_files():
        relative_path = path.relative_to(REPO_ROOT).as_posix()
        examples = extract_gpd_return_examples(path, source_name=relative_path)
        checked_examples += len(examples)
        _, path_failures = validate_gpd_return_examples(examples)
        failures.extend(path_failures)

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
