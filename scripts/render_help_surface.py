"""Refresh or check generated GPD help workflow marker regions."""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parent.parent
    sys.path[:0] = [str(repo_root), str(repo_root / "src")]

from gpd.core.help_renderer import (
    render_command_index_markdown,
    render_detailed_command_reference_markdown,
    render_quick_start_markdown,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
HELP_WORKFLOW_PATH = Path("src/gpd/specs/workflows/help.md")
MARKER_PREFIX = "gpd-help"
_BLOCK_ID_PATTERN = r"[a-z0-9][a-z0-9-]*"
_START_MARKER_RE = re.compile(rf"<!-- {MARKER_PREFIX}:(?P<block_id>{_BLOCK_ID_PATTERN}):start -->")
_END_MARKER_RE = re.compile(rf"<!-- {MARKER_PREFIX}:(?P<block_id>{_BLOCK_ID_PATTERN}):end -->")


@dataclass(frozen=True, slots=True)
class HelpSurfaceDiff:
    path: Path | None
    block_id: str
    diff: str


_HELP_BLOCK_RENDERERS: dict[str, Callable[[], str]] = {
    "quick-start": render_quick_start_markdown,
    "command-index": render_command_index_markdown,
    "detailed-command-reference": render_detailed_command_reference_markdown,
}


def help_surface_block_ids() -> tuple[str, ...]:
    return tuple(_HELP_BLOCK_RENDERERS)


def help_surface_markers(block_id: str) -> tuple[str, str]:
    if block_id not in _HELP_BLOCK_RENDERERS:
        raise ValueError(f"Unknown help surface block {block_id!r}")
    return (
        f"<!-- {MARKER_PREFIX}:{block_id}:start -->",
        f"<!-- {MARKER_PREFIX}:{block_id}:end -->",
    )


def render_help_surface_region(block_id: str) -> str:
    start_marker, end_marker = help_surface_markers(block_id)
    body = _HELP_BLOCK_RENDERERS[block_id]().rstrip() + "\n"
    return f"{start_marker}\n{body}{end_marker}"


def _diff(expected: str, actual: str, *, path: Path | None, block_id: str) -> str:
    label = path.as_posix() if path is not None else "<text>"
    return "".join(
        difflib.unified_diff(
            actual.splitlines(keepends=True),
            expected.splitlines(keepends=True),
            fromfile=f"{label}:{block_id} (current)",
            tofile=f"{label}:{block_id} (expected)",
        )
    )


def _replace_help_surface_regions_in_text(text: str, *, path: Path | None = None) -> tuple[str, tuple[str, ...]]:
    output_parts: list[str] = []
    replaced_block_ids: list[str] = []
    cursor = 0

    while True:
        start_match = _START_MARKER_RE.search(text, cursor)
        orphan_end_match = _END_MARKER_RE.search(text, cursor)
        if start_match is None:
            if orphan_end_match is not None:
                block_id = orphan_end_match.group("block_id")
                label = f" in {path.as_posix()}" if path is not None else ""
                raise ValueError(f"Orphan end marker for help surface block {block_id!r}{label}")
            output_parts.append(text[cursor:])
            break
        if orphan_end_match is not None and orphan_end_match.start() < start_match.start():
            block_id = orphan_end_match.group("block_id")
            label = f" in {path.as_posix()}" if path is not None else ""
            raise ValueError(f"Orphan end marker for help surface block {block_id!r}{label}")

        block_id = start_match.group("block_id")
        if block_id not in _HELP_BLOCK_RENDERERS:
            label = f" in {path.as_posix()}" if path is not None else ""
            raise ValueError(f"Unknown help surface block {block_id!r}{label}")

        _start_marker, end_marker = help_surface_markers(block_id)
        end_index = text.find(end_marker, start_match.end())
        if end_index < 0:
            label = f" in {path.as_posix()}" if path is not None else ""
            raise ValueError(f"Missing end marker for help surface block {block_id!r}{label}")

        next_start = _START_MARKER_RE.search(text, start_match.end())
        if next_start is not None and next_start.start() < end_index:
            label = f" in {path.as_posix()}" if path is not None else ""
            raise ValueError(f"Nested help surface block before {block_id!r} ends{label}")

        output_parts.append(text[cursor : start_match.start()])
        output_parts.append(render_help_surface_region(block_id))
        cursor = end_index + len(end_marker)
        replaced_block_ids.append(block_id)

    return "".join(output_parts), tuple(replaced_block_ids)


def replace_help_surface_text(text: str) -> str:
    updated, _block_ids = _replace_help_surface_regions_in_text(text)
    return updated


def check_help_surface_text(text: str, *, path: Path | None = None) -> tuple[HelpSurfaceDiff, ...]:
    updated, block_ids = _replace_help_surface_regions_in_text(text, path=path)
    missing_blocks = tuple(block_id for block_id in _HELP_BLOCK_RENDERERS if block_id not in block_ids)
    if missing_blocks:
        label = path.as_posix() if path is not None else "<text>"
        return (
            HelpSurfaceDiff(
                path=path,
                block_id=", ".join(missing_blocks),
                diff=(
                    f"{label}: missing expected help surface marker(s): "
                    + ", ".join(repr(block_id) for block_id in missing_blocks)
                    + "\n"
                ),
            ),
        )
    if updated == text:
        return ()
    return (
        HelpSurfaceDiff(
            path=path,
            block_id=", ".join(dict.fromkeys(block_ids)),
            diff=_diff(updated, text, path=path, block_id="help-surface-regions"),
        ),
    )


def check_help_surface_file(
    path: Path = REPO_ROOT / HELP_WORKFLOW_PATH,
) -> tuple[HelpSurfaceDiff, ...]:
    return check_help_surface_text(path.read_text(encoding="utf-8"), path=path)


def update_help_surface_file(
    path: Path = REPO_ROOT / HELP_WORKFLOW_PATH,
) -> bool:
    original = path.read_text(encoding="utf-8")
    updated = replace_help_surface_text(original)
    if updated == original:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=REPO_ROOT / HELP_WORKFLOW_PATH,
        help="help workflow file to check or update",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify generated help marker regions without modifying the file",
    )
    parser.add_argument(
        "--list-blocks",
        action="store_true",
        help="print supported help generated block ids",
    )
    args = parser.parse_args(argv)

    if args.list_blocks:
        for block_id in help_surface_block_ids():
            print(block_id)
        return 0

    if args.check:
        diffs = check_help_surface_file(args.path)
        if diffs:
            sys.stderr.write(
                "Help surface generated regions are stale. "
                "Run `uv run python scripts/render_help_surface.py` and commit the result.\n\n"
            )
            sys.stderr.write("\n".join(diff.diff for diff in diffs))
            return 1
        return 0

    if update_help_surface_file(args.path):
        print(args.path.relative_to(REPO_ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
