"""Refresh or check generated GPD help workflow marker regions."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parent.parent
    sys.path[:0] = [str(repo_root), str(repo_root / "src")]

from gpd.core.help_renderer import (
    render_command_index_markdown,
    render_detailed_command_reference_markdown,
    render_quick_start_markdown,
)
from scripts.generated_region_support import (
    GeneratedRegionDiff,
    GeneratedRegionSpec,
    marker_pair,
    render_region,
    replace_regions,
    unified_diff_text,
    write_stale_check_result,
)

HelpSurfaceDiff = GeneratedRegionDiff

REPO_ROOT = Path(__file__).resolve().parent.parent
HELP_WORKFLOW_PATH = Path("src/gpd/specs/workflows/help.md")
MARKER_PREFIX = "gpd-help"


_HELP_BLOCK_RENDERERS: dict[str, Callable[[], str]] = {
    "quick-start": render_quick_start_markdown,
    "command-index": render_command_index_markdown,
    "detailed-command-reference": render_detailed_command_reference_markdown,
}


def help_surface_block_ids() -> tuple[str, ...]:
    return tuple(_HELP_BLOCK_RENDERERS)


_HELP_REGION_SPEC = GeneratedRegionSpec(
    marker_prefix=MARKER_PREFIX,
    known_block_ids=help_surface_block_ids,
    block_label="help surface block",
)


def help_surface_markers(block_id: str) -> tuple[str, str]:
    if block_id not in _HELP_BLOCK_RENDERERS:
        raise ValueError(f"Unknown help surface block {block_id!r}")
    return marker_pair(_HELP_REGION_SPEC, block_id)


def render_help_surface_region(block_id: str) -> str:
    if block_id not in _HELP_BLOCK_RENDERERS:
        raise ValueError(f"Unknown help surface block {block_id!r}")
    return render_region(_HELP_REGION_SPEC, block_id, _HELP_BLOCK_RENDERERS[block_id]())


def _replace_help_surface_regions_in_text(text: str, *, path: Path | None = None) -> tuple[str, tuple[str, ...]]:
    return replace_regions(
        text,
        spec=_HELP_REGION_SPEC,
        render_body=lambda block_id: _HELP_BLOCK_RENDERERS[block_id](),
        path=path,
    )


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
            diff=unified_diff_text(updated, text, path=path, block_id="help-surface-regions"),
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
            return write_stale_check_result(
                diffs,
                heading="Help surface generated regions are stale.",
                regenerate_command="uv run python scripts/render_help_surface.py",
            )
        return 0

    if update_help_surface_file(args.path):
        print(args.path.relative_to(REPO_ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
