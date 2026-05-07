"""Phase 2 runtime-note budget and adapter-boundary coverage."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

import pytest

from gpd.adapters.install_utils import project_markdown_for_runtime
from gpd.adapters.runtime_catalog import iter_runtime_descriptors

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src/gpd"
COMMANDS_DIR = SRC_ROOT / "commands"
PHASE2_RUNTIME_NOTE_BLOCK_CHAR_BUDGET = 5_000

RUNTIMES = tuple(descriptor.runtime_name for descriptor in iter_runtime_descriptors())
RUNTIME_NOTE_TAGS_BY_RUNTIME: Mapping[str, tuple[str, ...]] = {
    "codex": ("codex_runtime_notes", "codex_questioning"),
    "gemini": ("gemini_runtime_notes", "gemini_shell_runtime_notes"),
}
ALL_RUNTIME_NOTE_TAGS = tuple(
    dict.fromkeys(tag for tags in RUNTIME_NOTE_TAGS_BY_RUNTIME.values() for tag in tags)
)
SHARED_RUNTIME_NOTE_REFERENCE_MARKERS = (
    "references/tooling/runtime-command-snippets.md",
    "references/tooling/codex-runtime-bridge.md",
    "references/tooling/gemini-shell-policy.md",
    "gpd-auto-edit.toml",
)
SHARED_ADAPTER_INFRASTRUCTURE_FILES = (
    SRC_ROOT / "adapters/base.py",
    SRC_ROOT / "adapters/install_utils.py",
    SRC_ROOT / "adapters/tool_names.py",
)
CANONICAL_RUNTIME_PROMPT_DIRS = (
    SRC_ROOT / "commands",
    SRC_ROOT / "agents",
    SRC_ROOT / "specs/workflows",
)


@pytest.fixture(scope="module")
def projected_command_prompts() -> dict[str, dict[str, str]]:
    """Return runtime-visible command projections for the Phase 2 note checks."""
    projected: dict[str, dict[str, str]] = {runtime: {} for runtime in RUNTIMES}
    for command_path in sorted(COMMANDS_DIR.glob("*.md")):
        raw = command_path.read_text(encoding="utf-8")
        for runtime in RUNTIMES:
            projected[runtime][command_path.stem] = project_markdown_for_runtime(
                raw,
                runtime=runtime,
                path_prefix="/runtime/",
                surface_kind="command",
                src_root=SRC_ROOT,
                command_name=command_path.stem,
            )
    return projected


def _tag_block_re(tag: str) -> re.Pattern[str]:
    return re.compile(rf"<{re.escape(tag)}(?:\s[^>]*)?>.*?</{re.escape(tag)}>", re.DOTALL)


def _runtime_note_blocks(text: str, tag: str) -> tuple[str, ...]:
    return tuple(match.group(0) for match in _tag_block_re(tag).finditer(text))


def _has_shared_runtime_note_reference(block: str) -> bool:
    return any(marker in block for marker in SHARED_RUNTIME_NOTE_REFERENCE_MARKERS)


def test_runtime_note_full_blocks_are_budgeted_or_shared_reference_backed(
    projected_command_prompts: Mapping[str, Mapping[str, str]],
) -> None:
    failures: list[str] = []

    for runtime, tags in RUNTIME_NOTE_TAGS_BY_RUNTIME.items():
        runtime_prompts = projected_command_prompts[runtime]
        for tag in tags:
            blocks = tuple(
                block
                for prompt in runtime_prompts.values()
                for block in _runtime_note_blocks(prompt, tag)
            )
            if not blocks:
                continue

            full_block_chars = sum(len(block) for block in blocks)
            if full_block_chars <= PHASE2_RUNTIME_NOTE_BLOCK_CHAR_BUDGET:
                continue

            unbacked_count = sum(1 for block in blocks if not _has_shared_runtime_note_reference(block))
            if unbacked_count:
                failures.append(
                    f"{runtime} {tag}: {full_block_chars:,} full block chars across {len(blocks)} blocks "
                    f"without shared snippet references in {unbacked_count} blocks"
                )

    assert not failures, "\n".join(failures)


def test_runtime_note_tags_stay_runtime_owned_in_command_projections(
    projected_command_prompts: Mapping[str, Mapping[str, str]],
) -> None:
    failures: list[str] = []

    for runtime, command_prompts in projected_command_prompts.items():
        allowed_tags = set(RUNTIME_NOTE_TAGS_BY_RUNTIME.get(runtime, ()))
        for command_name, prompt in command_prompts.items():
            present_tags = {
                tag
                for tag in ALL_RUNTIME_NOTE_TAGS
                if f"<{tag}" in prompt or f"</{tag}>" in prompt
            }
            foreign_tags = sorted(present_tags - allowed_tags)
            if foreign_tags:
                failures.append(f"{runtime} {command_name}: unexpected runtime note tags {foreign_tags}")

    assert not failures, "\n".join(failures)


def test_adapter_runtime_note_tags_do_not_leak_into_shared_adapter_infrastructure() -> None:
    failures: list[str] = []

    for path in SHARED_ADAPTER_INFRASTRUCTURE_FILES:
        text = path.read_text(encoding="utf-8")
        leaked_tags = sorted(tag for tag in ALL_RUNTIME_NOTE_TAGS if f"<{tag}" in text or f"</{tag}>" in text)
        if leaked_tags:
            failures.append(f"{path.relative_to(REPO_ROOT)}: adapter-owned note tags {leaked_tags}")

    assert not failures, "\n".join(failures)


def test_canonical_runtime_prompt_sources_do_not_carry_adapter_note_tags() -> None:
    failures: list[str] = []

    for root in CANONICAL_RUNTIME_PROMPT_DIRS:
        for path in sorted(root.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            leaked_tags = sorted(tag for tag in ALL_RUNTIME_NOTE_TAGS if f"<{tag}" in text or f"</{tag}>" in text)
            if leaked_tags:
                failures.append(f"{path.relative_to(REPO_ROOT)}: adapter-owned note tags {leaked_tags}")

    assert not failures, "\n".join(failures)
