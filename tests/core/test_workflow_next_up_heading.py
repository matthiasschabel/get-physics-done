"""Prompt-visible Next Up heading invariants."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = REPO_ROOT / "src/gpd/commands"
AGENTS_DIR = REPO_ROOT / "src/gpd/agents"
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"
TEMPLATES_DIR = REPO_ROOT / "src/gpd/specs/templates"
REFERENCES_DIR = REPO_ROOT / "src/gpd/specs/references"


def _prompt_markdown_paths(*, include_references: bool = False) -> list[Path]:
    roots = [
        COMMANDS_DIR,
        AGENTS_DIR,
        WORKFLOWS_DIR,
        TEMPLATES_DIR,
    ]
    if include_references:
        roots.extend(
            [
                REFERENCES_DIR / "orchestration",
                REFERENCES_DIR / "ui",
            ]
        )
    return [path for root in roots for path in sorted(root.rglob("*.md"))]


def _next_up_blocks(path: Path) -> list[tuple[int, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    blocks: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        if line.strip() != "## > Next Up":
            continue

        in_fenced_block = sum(1 for previous in lines[:index] if previous.strip().startswith("```")) % 2 == 1
        block_lines = [line]
        for following in lines[index + 1 :]:
            stripped = following.strip()
            if in_fenced_block and stripped == "```":
                break
            if not in_fenced_block and stripped.startswith("## "):
                break
            block_lines.append(following)
        blocks.append((index + 1, "\n".join(block_lines)))
    return blocks


def test_prompt_markdown_uses_canonical_next_up_heading() -> None:
    offenders: list[str] = []

    for path in _prompt_markdown_paths():
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("##") and "Next Up" in stripped and stripped != "## > Next Up":
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line_number}:{line}")

    assert offenders == []


def test_prompt_markdown_avoids_bang_bang_headings() -> None:
    offenders: list[str] = []

    for path in _prompt_markdown_paths():
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if line.strip().startswith("## !!"):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line_number}:{line}")

    assert offenders == []


def test_next_up_blocks_do_not_expose_raw_stage_reload_commands() -> None:
    forbidden_fragments = (
        "gpd --raw init",
        "--raw init",
        "gpd --raw stage field-access",
        "--raw stage field-access",
    )
    offenders: list[str] = []

    for path in _prompt_markdown_paths(include_references=True):
        for line_number, block in _next_up_blocks(path):
            for fragment in forbidden_fragments:
                if fragment in block:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{line_number}:{fragment}")

    assert offenders == []


def test_next_up_blocks_use_runtime_verify_work_not_structural_verify_commands() -> None:
    forbidden_fragments = (
        "gpd verify phase",
        "gpd:verify-phase",
        "gpd-verify-work",
    )
    offenders: list[str] = []

    for path in _prompt_markdown_paths(include_references=True):
        for line_number, block in _next_up_blocks(path):
            for fragment in forbidden_fragments:
                if fragment in block:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{line_number}:{fragment}")

    assert offenders == []
