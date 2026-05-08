"""Refresh or check generated public onboarding surface regions."""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parent.parent
    sys.path[:0] = [str(repo_root), str(repo_root / "src")]

from gpd.core.public_surface_renderer import (
    public_surface_block_ids,
    public_surface_context,
    render_public_surface_block,
    runtime_doc_filename,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
MARKER_PREFIX = "gpd-public-surface"
_DEFAULT_STATIC_TARGET_PATHS = (
    Path("README.md"),
    Path("docs/README.md"),
    Path("docs/macos.md"),
    Path("docs/linux.md"),
    Path("docs/windows.md"),
    Path("src/gpd/specs/workflows/help.md"),
)

_BLOCK_ID_PATTERN = r"[a-z0-9][a-z0-9-]*"
_START_MARKER_RE = re.compile(rf"<!-- {MARKER_PREFIX}:(?P<block_id>{_BLOCK_ID_PATTERN}):start -->")


@dataclass(frozen=True, slots=True)
class GeneratedRegionDiff:
    path: Path | None
    block_id: str
    diff: str


def generated_region_markers(block_id: str) -> tuple[str, str]:
    if re.fullmatch(_BLOCK_ID_PATTERN, block_id) is None:
        raise ValueError(f"Generated public surface block ids must be kebab-case: {block_id!r}")
    return (
        f"<!-- {MARKER_PREFIX}:{block_id}:start -->",
        f"<!-- {MARKER_PREFIX}:{block_id}:end -->",
    )


def render_generated_region(block_id: str, body: str) -> str:
    start_marker, end_marker = generated_region_markers(block_id)
    normalized_body = body.rstrip() + "\n"
    return f"{start_marker}\n{normalized_body}{end_marker}"


def _known_block_ids() -> frozenset[str]:
    return frozenset(public_surface_block_ids())


def default_target_paths() -> tuple[Path, ...]:
    runtime_doc_paths = tuple(
        Path("docs") / runtime_doc_filename(surface)
        for surface in public_surface_context().runtime_surfaces
    )
    return (
        *_DEFAULT_STATIC_TARGET_PATHS[:-1],
        *runtime_doc_paths,
        _DEFAULT_STATIC_TARGET_PATHS[-1],
    )


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


def _replace_generated_regions_in_text(text: str, *, path: Path | None = None) -> tuple[str, tuple[str, ...]]:
    known_block_ids = _known_block_ids()
    output_parts: list[str] = []
    replaced_block_ids: list[str] = []
    cursor = 0

    while True:
        start_match = _START_MARKER_RE.search(text, cursor)
        if start_match is None:
            output_parts.append(text[cursor:])
            break

        block_id = start_match.group("block_id")
        if block_id not in known_block_ids:
            label = f" in {path.as_posix()}" if path is not None else ""
            raise ValueError(f"Unknown public surface generated block {block_id!r}{label}")

        start_marker, end_marker = generated_region_markers(block_id)
        end_index = text.find(end_marker, start_match.end())
        if end_index < 0:
            label = f" in {path.as_posix()}" if path is not None else ""
            raise ValueError(f"Missing end marker for public surface generated block {block_id!r}{label}")

        next_start = _START_MARKER_RE.search(text, start_match.end())
        if next_start is not None and next_start.start() < end_index:
            label = f" in {path.as_posix()}" if path is not None else ""
            raise ValueError(f"Nested public surface generated block before {block_id!r} ends{label}")

        output_parts.append(text[cursor : start_match.start()])
        output_parts.append(render_generated_region(block_id, render_public_surface_block(block_id)))
        cursor = end_index + len(end_marker)
        replaced_block_ids.append(block_id)

    return "".join(output_parts), tuple(replaced_block_ids)


def replace_generated_regions(text: str) -> str:
    updated, _block_ids = _replace_generated_regions_in_text(text)
    return updated


def check_generated_regions(text: str, *, path: Path | None = None) -> tuple[GeneratedRegionDiff, ...]:
    updated, block_ids = _replace_generated_regions_in_text(text, path=path)
    if updated == text:
        return ()
    return (
        GeneratedRegionDiff(
            path=path,
            block_id=", ".join(dict.fromkeys(block_ids)),
            diff=_diff(updated, text, path=path, block_id="generated-regions"),
        ),
    )


def _resolve_paths(paths: Sequence[Path] | None, *, repo_root: Path) -> tuple[Path, ...]:
    selected_paths = tuple(paths) if paths else default_target_paths()
    return tuple(path if path.is_absolute() else repo_root / path for path in selected_paths)


def check_generated_files(
    paths: Sequence[Path] | None = None,
    *,
    repo_root: Path = REPO_ROOT,
) -> tuple[GeneratedRegionDiff, ...]:
    diffs: list[GeneratedRegionDiff] = []
    for path in _resolve_paths(paths, repo_root=repo_root):
        diffs.extend(check_generated_regions(path.read_text(encoding="utf-8"), path=path))
    return tuple(diffs)


def update_generated_files(
    paths: Sequence[Path] | None = None,
    *,
    repo_root: Path = REPO_ROOT,
) -> tuple[Path, ...]:
    updated_paths: list[Path] = []
    for path in _resolve_paths(paths, repo_root=repo_root):
        original = path.read_text(encoding="utf-8")
        updated = replace_generated_regions(original)
        if updated == original:
            continue
        path.write_text(updated, encoding="utf-8")
        updated_paths.append(path)
    return tuple(updated_paths)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, help="specific files to check or update")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify generated public surface regions without modifying files",
    )
    parser.add_argument(
        "--list-blocks",
        action="store_true",
        help="print supported public surface generated block ids",
    )
    args = parser.parse_args(argv)

    if args.list_blocks:
        for block_id in public_surface_block_ids():
            print(block_id)
        return 0

    if args.check:
        diffs = check_generated_files(args.paths)
        if diffs:
            sys.stderr.write(
                "Public surface generated regions are stale. "
                "Run `uv run python scripts/render_public_surface.py` and commit the result.\n\n"
            )
            sys.stderr.write("\n".join(diff.diff for diff in diffs))
            return 1
        return 0

    updated_paths = update_generated_files(args.paths)
    for path in updated_paths:
        print(path.relative_to(REPO_ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
