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
    runtime_quickstart_block_id,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
MARKER_PREFIX = "gpd-public-surface"
_BLOCK_ID_PATTERN = r"[a-z0-9][a-z0-9-]*"
_START_MARKER_RE = re.compile(rf"<!-- {MARKER_PREFIX}:(?P<block_id>{_BLOCK_ID_PATTERN}):start -->")
_END_MARKER_RE = re.compile(rf"<!-- {MARKER_PREFIX}:(?P<block_id>{_BLOCK_ID_PATTERN}):end -->")


@dataclass(frozen=True, slots=True)
class GeneratedRegionDiff:
    path: Path | None
    block_id: str
    diff: str


@dataclass(frozen=True, slots=True)
class PublicSurfaceTarget:
    path: Path
    required_blocks: tuple[str, ...]
    allowed_duplicate_blocks: tuple[str, ...] = ()


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
    return tuple(target.path for target in default_target_contracts())


def default_target_contracts() -> tuple[PublicSurfaceTarget, ...]:
    runtime_doc_paths = tuple(
        PublicSurfaceTarget(
            Path("docs") / runtime_doc_filename(surface),
            (runtime_quickstart_block_id(surface),),
        )
        for surface in public_surface_context().runtime_surfaces
    )
    return (
        PublicSurfaceTarget(
            Path("README.md"),
            (
                "terminal-runtime-bridge",
                "beginner-startup-ladder",
                "recovery-note",
                "local-cli-bridge-summary",
                "supported-runtimes-table",
                "recovery-note",
                "local-cli-bridge-summary",
            ),
            allowed_duplicate_blocks=("recovery-note", "local-cli-bridge-summary"),
        ),
        PublicSurfaceTarget(
            Path("docs/README.md"),
            (
                "beginner-preflight",
                "beginner-caveats",
                "beginner-startup-ladder",
                "recovery-note",
                "terminal-runtime-bridge",
                "post-start-settings",
            ),
        ),
        PublicSurfaceTarget(
            Path("docs/macos.md"),
            (
                "runtime-doc-links",
                "os-install-matrix",
                "supported-runtimes-table",
                "os-next-steps-table",
                "recovery-note",
            ),
        ),
        PublicSurfaceTarget(
            Path("docs/linux.md"),
            (
                "runtime-doc-links",
                "os-install-matrix",
                "supported-runtimes-table",
                "os-next-steps-table",
                "recovery-note",
            ),
        ),
        PublicSurfaceTarget(
            Path("docs/windows.md"),
            (
                "runtime-doc-links",
                "os-install-matrix",
                "supported-runtimes-table",
                "os-next-steps-table",
                "recovery-note",
            ),
        ),
        *runtime_doc_paths,
        PublicSurfaceTarget(
            Path("src/gpd/specs/workflows/help.md"),
            ("local-cli-bridge-summary", "recovery-note"),
        ),
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
        orphan_end_match = _END_MARKER_RE.search(text, cursor)
        if start_match is None:
            if orphan_end_match is not None:
                block_id = orphan_end_match.group("block_id")
                label = f" in {path.as_posix()}" if path is not None else ""
                raise ValueError(f"Orphan end marker for public surface generated block {block_id!r}{label}")
            output_parts.append(text[cursor:])
            break
        if orphan_end_match is not None and orphan_end_match.start() < start_match.start():
            block_id = orphan_end_match.group("block_id")
            label = f" in {path.as_posix()}" if path is not None else ""
            raise ValueError(f"Orphan end marker for public surface generated block {block_id!r}{label}")

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


def check_generated_region_inventory(
    text: str,
    *,
    required_blocks: Sequence[str],
    allowed_duplicate_blocks: Sequence[str] = (),
    path: Path | None = None,
) -> tuple[GeneratedRegionDiff, ...]:
    """Check that a default target still carries its declared generated regions."""

    known_block_ids = _known_block_ids()
    required_counts: dict[str, int] = {}
    for block_id in required_blocks:
        if block_id not in known_block_ids:
            raise ValueError(f"Unknown required public surface block {block_id!r}")
        required_counts[block_id] = required_counts.get(block_id, 0) + 1

    actual_counts: dict[str, int] = {}
    for match in _START_MARKER_RE.finditer(text):
        block_id = match.group("block_id")
        actual_counts[block_id] = actual_counts.get(block_id, 0) + 1

    allowed_duplicates = set(allowed_duplicate_blocks)
    problems: list[str] = []
    for block_id, expected_count in required_counts.items():
        actual_count = actual_counts.get(block_id, 0)
        if actual_count < expected_count:
            problems.append(f"missing {expected_count - actual_count} expected marker(s) for {block_id!r}")
        if actual_count > expected_count:
            problems.append(f"found {actual_count} marker(s) for {block_id!r}, expected {expected_count}")

    for block_id, actual_count in sorted(actual_counts.items()):
        if block_id not in known_block_ids:
            continue
        if block_id not in required_counts:
            problems.append(f"unexpected marker for {block_id!r}")
        if actual_count > 1 and block_id not in allowed_duplicates:
            problems.append(f"duplicate marker for {block_id!r} is not allowed")

    if not problems:
        return ()

    label = path.as_posix() if path is not None else "<text>"
    return (
        GeneratedRegionDiff(
            path=path,
            block_id=", ".join(dict.fromkeys(required_blocks)),
            diff=f"{label}: public surface marker inventory mismatch:\n- " + "\n- ".join(problems) + "\n",
        ),
    )


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


def _default_target_contract_map(*, repo_root: Path) -> dict[Path, PublicSurfaceTarget]:
    return {(repo_root / target.path).resolve(): target for target in default_target_contracts()}


def check_generated_files(
    paths: Sequence[Path] | None = None,
    *,
    repo_root: Path = REPO_ROOT,
) -> tuple[GeneratedRegionDiff, ...]:
    diffs: list[GeneratedRegionDiff] = []
    target_contracts = _default_target_contract_map(repo_root=repo_root) if paths is None else {}
    for path in _resolve_paths(paths, repo_root=repo_root):
        content = path.read_text(encoding="utf-8")
        diffs.extend(check_generated_regions(content, path=path))
        target = target_contracts.get(path.resolve())
        if target is not None:
            diffs.extend(
                check_generated_region_inventory(
                    content,
                    required_blocks=target.required_blocks,
                    allowed_duplicate_blocks=target.allowed_duplicate_blocks,
                    path=path,
                )
            )
    return tuple(diffs)


def update_generated_files(
    paths: Sequence[Path] | None = None,
    *,
    repo_root: Path = REPO_ROOT,
) -> tuple[Path, ...]:
    updated_paths: list[Path] = []
    target_contracts = _default_target_contract_map(repo_root=repo_root) if paths is None else {}
    for path in _resolve_paths(paths, repo_root=repo_root):
        original = path.read_text(encoding="utf-8")
        updated = replace_generated_regions(original)
        target = target_contracts.get(path.resolve())
        if target is not None:
            diffs = check_generated_region_inventory(
                updated,
                required_blocks=target.required_blocks,
                allowed_duplicate_blocks=target.allowed_duplicate_blocks,
                path=path,
            )
            if diffs:
                raise ValueError(diffs[0].diff.strip())
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
