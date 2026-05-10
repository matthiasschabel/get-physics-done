"""Shared helpers for checked-in generated artifacts and marker regions."""

from __future__ import annotations

import difflib
import re
import sys
from collections import Counter
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class GeneratedRegionDiff:
    path: Path | None
    block_id: str
    diff: str


@dataclass(frozen=True, slots=True)
class GeneratedRegionSpec:
    marker_prefix: str
    known_block_ids: Callable[[], Collection[str]]
    block_label: str
    block_id_pattern: str = r"[a-z0-9][a-z0-9-]*"
    invalid_block_id_message: str = "Generated block ids must be kebab-case: {block_id!r}"


def marker_pair(spec: GeneratedRegionSpec, block_id: str) -> tuple[str, str]:
    if re.fullmatch(spec.block_id_pattern, block_id) is None:
        raise ValueError(spec.invalid_block_id_message.format(block_id=block_id))
    return f"<!-- {spec.marker_prefix}:{block_id}:start -->", f"<!-- {spec.marker_prefix}:{block_id}:end -->"


def render_region(spec: GeneratedRegionSpec, block_id: str, body: str) -> str:
    start_marker, end_marker = marker_pair(spec, block_id)
    return f"{start_marker}\n{body.rstrip()}\n{end_marker}"


def replace_regions(
    text: str,
    *,
    spec: GeneratedRegionSpec,
    render_body: Callable[[str], str],
    path: Path | None = None,
) -> tuple[str, tuple[str, ...]]:
    start_marker_re, end_marker_re = _marker_regexes(spec)
    known_block_ids = frozenset(spec.known_block_ids())
    output_parts: list[str] = []
    replaced_block_ids: list[str] = []
    path_label = f" in {path.as_posix()}" if path is not None else ""
    cursor = 0

    while True:
        start_match = start_marker_re.search(text, cursor)
        orphan_end_match = end_marker_re.search(text, cursor)
        if orphan_end_match is not None and (start_match is None or orphan_end_match.start() < start_match.start()):
            block_id = orphan_end_match.group("block_id")
            raise ValueError(f"Orphan end marker for {spec.block_label} {block_id!r}{path_label}")
        if start_match is None:
            output_parts.append(text[cursor:])
            break

        block_id = start_match.group("block_id")
        if block_id not in known_block_ids:
            raise ValueError(f"Unknown {spec.block_label} {block_id!r}{path_label}")

        _start_marker, end_marker = marker_pair(spec, block_id)
        end_index = text.find(end_marker, start_match.end())
        if end_index < 0:
            raise ValueError(f"Missing end marker for {spec.block_label} {block_id!r}{path_label}")

        next_start = start_marker_re.search(text, start_match.end())
        if next_start is not None and next_start.start() < end_index:
            raise ValueError(f"Nested {spec.block_label} before {block_id!r} ends{path_label}")

        output_parts.append(text[cursor : start_match.start()])
        output_parts.append(render_region(spec, block_id, render_body(block_id)))
        cursor = end_index + len(end_marker)
        replaced_block_ids.append(block_id)

    return "".join(output_parts), tuple(replaced_block_ids)


def marker_start_counts(text: str, *, spec: GeneratedRegionSpec) -> dict[str, int]:
    start_marker_re, _end_marker_re = _marker_regexes(spec)
    return dict(Counter(match.group("block_id") for match in start_marker_re.finditer(text)))


def unified_diff_text(expected: str, actual: str, *, path: Path | None, block_id: str) -> str:
    label = path.as_posix() if path is not None else "<text>"
    return "".join(
        difflib.unified_diff(
            actual.splitlines(keepends=True),
            expected.splitlines(keepends=True),
            fromfile=f"{label}:{block_id} (current)",
            tofile=f"{label}:{block_id} (expected)",
        )
    )


def write_stale_check_result(diffs: Sequence[GeneratedRegionDiff], *, heading: str, regenerate_command: str) -> int:
    if not diffs:
        return 0
    sys.stderr.write(f"{heading} Run `{regenerate_command}` and commit the result.\n\n")
    sys.stderr.write("\n".join(diff.diff for diff in diffs))
    return 1


def _marker_regexes(spec: GeneratedRegionSpec) -> tuple[re.Pattern[str], re.Pattern[str]]:
    escaped_prefix = re.escape(spec.marker_prefix)
    return (
        re.compile(rf"<!-- {escaped_prefix}:(?P<block_id>{spec.block_id_pattern}):start -->"),
        re.compile(rf"<!-- {escaped_prefix}:(?P<block_id>{spec.block_id_pattern}):end -->"),
    )
