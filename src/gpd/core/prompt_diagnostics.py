"""Read-only prompt-surface diagnostics for canonical GPD sources."""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from gpd.adapters.install_utils import (
    DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES,
    expand_at_includes,
    parse_at_include_path,
    project_markdown_for_runtime,
    split_markdown_frontmatter,
)
from gpd.adapters.runtime_catalog import (
    get_runtime_descriptor,
    iter_runtime_descriptors,
    normalize_runtime_name,
)
from gpd.core.return_contract import validate_gpd_return_markdown

PromptSurfaceKind = Literal["command", "agent", "workflow"]

PROMPT_SURFACE_REPORT_SCHEMA_VERSION = "prompt_surface_diagnostics.v2"
DEFAULT_PATH_PREFIX = "/runtime/"
DEFAULT_SURFACES: tuple[PromptSurfaceKind, ...] = ("command", "agent", "workflow")

_INCLUDED_MARKER_RE = re.compile(r"<!-- \[included: [^\]]+\] -->")
_UNRESOLVED_INCLUDE_RE = re.compile(r"<!-- @ include (?:not resolved|cycle detected|read error|depth limit reached):")
_FENCE_OPEN_RE = re.compile(r"^[ \t]*(?P<marker>`{3,}|~{3,})(?P<info>.*)$")
_SPAWN_CONTRACT_RE = re.compile(
    r"^[ \t]*<spawn_contract(?:_interactive)?>[ \t]*$",
    re.MULTILINE,
)
_SCHEMA_BLOCK_MARKERS = (
    "gpd_return:",
    '"gpd_return"',
    "'gpd_return'",
    "schema_version",
    "contract_results",
    "project_contract",
)
_SCHEMA_FENCE_LANGUAGES = frozenset({"yaml", "yml", "json", "toml"})
_GPD_RETURN_EXAMPLE_RE = re.compile(r"(?m)(?:^|[\s{,\[\('\"`])['\"]?gpd_return['\"]?\s*:")
_HARD_GATE_LINE_RE = re.compile(
    r"\b(?:STOP|fail[- ]closed|do not proceed|must|required|never|forbidden|reject|cannot|blocked)\b",
    re.IGNORECASE,
)
_SHELL_PARSING_RE = re.compile(
    r"(?:\bgpd\s+--raw\b|\bjq\b|\bsed\b|\bawk\b|\bgrep\b|\bmktemp\b|\$\(|<<-?|"
    r"^\s*case\b|\bcase\s+.*\bin\b|\bprintf\b|\bcat\s+GPD\b)"
)
_BRIDGE_COMMAND_RE = re.compile(r"(?:gpd\.runtime_cli|\bgpd_cli\s+--raw\b|\bgpd\s+--raw\b)")
_RUNTIME_NOTE_RE = re.compile(
    r"(?:runtime note|runtime bridge|runtime-visible|shared runtime cli bridge|GPD runtime|"
    r"When shell steps call the GPD CLI)",
    re.IGNORECASE,
)
_DUPLICATE_VOCABULARY = (
    "gpd_return",
    "files_written",
    "artifact gate",
    "fail-closed",
    "fail closed",
    "STOP",
    "do not proceed",
    "must not",
    "never",
    "authoritative",
    "frontmatter",
    "schema",
    "validation",
    "checkpoint",
    "blocked",
    "route on",
    "presentation only",
)
_MACHINE_CONTRACT_RE = re.compile(
    r"(?:"
    r"\b[A-Za-z0-9_.-]+/[A-Za-z0-9_./{}$-]+|"
    r"\b[A-Za-z0-9_.-]+\.md\b|"
    r"--[a-z0-9-]+|"
    r"\bgpd(?:[: -][a-z0-9-]+|_return| --raw)\b|"
    r"\bschema_version\b|"
    r"\bfrontmatter\b|"
    r"\b[A-Za-z_][A-Za-z0-9_]*:\b|"
    r"<[^>\s]+>"
    r")",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class PromptSource:
    """One canonical prompt source discovered under the repository source tree."""

    kind: PromptSurfaceKind
    name: str
    path: str
    absolute_path: Path
    repo_root: Path
    src_root: Path


@dataclass(frozen=True, slots=True)
class MarkdownFence:
    """One fenced code block with line metadata."""

    info: str
    body: str
    start_line: int
    end_line: int


@dataclass(frozen=True, slots=True)
class RuntimeProjectionMetric:
    runtime: str
    native_include_support: bool
    line_count: int
    char_count: int
    include_count: int
    runtime_note_count: int
    runtime_note_chars: int
    shell_fence_count: int
    bridge_command_occurrences: int


@dataclass(frozen=True, slots=True)
class InvalidGpdReturnExample:
    path: str
    start_line: int
    end_line: int
    errors: tuple[str, ...]
    preview: str


@dataclass(frozen=True, slots=True)
class PromptSurfaceItem:
    kind: PromptSurfaceKind
    name: str
    path: str
    raw_line_count: int
    raw_char_count: int
    raw_include_count: int
    expanded_line_count: int
    expanded_char_count: int
    expanded_include_count: int
    unresolved_include_count: int
    visible_schema_example_count: int
    invalid_gpd_return_example_count: int
    invalid_gpd_return_examples: tuple[InvalidGpdReturnExample, ...]
    hard_gate_line_count: int
    hard_gate_density: float
    shell_fence_count: int
    shell_parsing_line_count: int
    rigidity_index: int
    runtime_projection: tuple[RuntimeProjectionMetric, ...]


@dataclass(frozen=True, slots=True)
class DuplicateInvariantGroup:
    phrase: str
    occurrence_count: int
    file_count: int
    severity: Literal["info", "warn", "high"]
    locations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PromptSurfaceReport:
    schema_version: str
    repo_root: str
    totals: Mapping[str, object]
    items: tuple[PromptSurfaceItem, ...]
    invalid_gpd_return_examples: tuple[InvalidGpdReturnExample, ...]
    duplicate_invariants: tuple[DuplicateInvariantGroup, ...]
    exact_prose_assertion_files: tuple[Mapping[str, object], ...]
    warnings: tuple[str, ...]


__all__ = [
    "DEFAULT_SURFACES",
    "PROMPT_SURFACE_REPORT_SCHEMA_VERSION",
    "DuplicateInvariantGroup",
    "InvalidGpdReturnExample",
    "PromptSource",
    "PromptSurfaceItem",
    "PromptSurfaceReport",
    "RuntimeProjectionMetric",
    "build_prompt_surface_report",
    "iter_prompt_sources",
    "measure_prompt_file",
    "render_prompt_surface_markdown",
    "render_prompt_surface_table",
    "report_to_dict",
]


def iter_prompt_sources(
    repo_root: str | Path,
    surfaces: Iterable[str] | str = DEFAULT_SURFACES,
) -> tuple[PromptSource, ...]:
    """Return canonical command, agent, and workflow markdown sources."""

    root = Path(repo_root).expanduser().resolve()
    src_root = _source_root_for_repo(root)
    normalized_surfaces = _normalize_surfaces(surfaces)
    source_dirs: dict[PromptSurfaceKind, Path] = {
        "command": src_root / "commands",
        "agent": src_root / "agents",
        "workflow": src_root / "specs" / "workflows",
    }

    sources: list[PromptSource] = []
    for kind in normalized_surfaces:
        source_dir = source_dirs[kind]
        if not source_dir.is_dir():
            continue
        for path in sorted(source_dir.glob("*.md")):
            if path.is_symlink() or not path.is_file():
                continue
            sources.append(
                PromptSource(
                    kind=kind,
                    name=path.stem,
                    path=_relative_path(path, root),
                    absolute_path=path,
                    repo_root=root,
                    src_root=src_root,
                )
            )
    return tuple(sources)


def measure_prompt_file(
    source: PromptSource,
    runtime_names: Iterable[str] | str = (),
    include_runtime_projections: bool = True,
) -> PromptSurfaceItem:
    """Measure one prompt source without mutating repo or project state."""

    raw_text = source.absolute_path.read_text(encoding="utf-8")
    expanded_text = expand_at_includes(raw_text, source.src_root, DEFAULT_PATH_PREFIX)
    raw_include_count = _count_raw_includes(raw_text)
    visible_schema_example_count, invalid_return_examples = _inspect_visible_schema_examples(raw_text, source.path)
    invalid_return_count = len(invalid_return_examples)
    hard_gate_line_count, hard_gate_density = _hard_gate_metrics(raw_text)
    shell_fence_count = _count_shell_fences(raw_text)
    shell_parsing_line_count = _count_shell_parsing_lines(raw_text)
    unresolved_include_count = len(_UNRESOLVED_INCLUDE_RE.findall(expanded_text))

    runtime_projection: tuple[RuntimeProjectionMetric, ...] = ()
    if include_runtime_projections and source.kind in {"command", "agent"}:
        runtime_projection = tuple(
            _measure_runtime_projection(source, raw_text, runtime_name)
            for runtime_name in _normalize_runtime_names(runtime_names)
        )

    rigidity_index = (
        2 * visible_schema_example_count
        + 3 * invalid_return_count
        + hard_gate_line_count
        + 2 * shell_parsing_line_count
        + 5 * unresolved_include_count
    )

    return PromptSurfaceItem(
        kind=source.kind,
        name=source.name,
        path=source.path,
        raw_line_count=_line_count(raw_text),
        raw_char_count=len(raw_text),
        raw_include_count=raw_include_count,
        expanded_line_count=_line_count(expanded_text),
        expanded_char_count=len(expanded_text),
        expanded_include_count=len(_INCLUDED_MARKER_RE.findall(expanded_text)),
        unresolved_include_count=unresolved_include_count,
        visible_schema_example_count=visible_schema_example_count,
        invalid_gpd_return_example_count=invalid_return_count,
        invalid_gpd_return_examples=invalid_return_examples,
        hard_gate_line_count=hard_gate_line_count,
        hard_gate_density=hard_gate_density,
        shell_fence_count=shell_fence_count,
        shell_parsing_line_count=shell_parsing_line_count,
        rigidity_index=rigidity_index,
        runtime_projection=runtime_projection,
    )


def build_prompt_surface_report(
    repo_root: str | Path,
    surfaces: Iterable[str] | str = DEFAULT_SURFACES,
    runtime_names: Iterable[str] | str = (),
    include_tests: bool = False,
    top: int | None = None,
    include_runtime_projections: bool = True,
) -> PromptSurfaceReport:
    """Build the full prompt diagnostics report for canonical source files."""

    del top
    root = Path(repo_root).expanduser().resolve()
    warnings: list[str] = []
    sources = iter_prompt_sources(root, surfaces)
    if not sources:
        warnings.append("no prompt sources found for requested surfaces")

    items = tuple(
        measure_prompt_file(
            source,
            runtime_names=runtime_names,
            include_runtime_projections=include_runtime_projections,
        )
        for source in sources
    )
    duplicate_invariants = _duplicate_invariant_groups(root, include_tests=include_tests)
    exact_assertions = _scan_exact_prompt_assertions(root) if include_tests else ()
    invalid_return_examples = tuple(example for item in items for example in item.invalid_gpd_return_examples)

    return PromptSurfaceReport(
        schema_version=PROMPT_SURFACE_REPORT_SCHEMA_VERSION,
        repo_root=str(root),
        totals=_build_totals(items),
        items=items,
        invalid_gpd_return_examples=invalid_return_examples,
        duplicate_invariants=duplicate_invariants,
        exact_prose_assertion_files=exact_assertions,
        warnings=tuple(warnings),
    )


def report_to_dict(report: PromptSurfaceReport, top: int | None = None) -> dict[str, object]:
    """Convert a report into JSON-serializable primitives."""

    return {
        "schema_version": report.schema_version,
        "repo_root": report.repo_root,
        "totals": report.totals,
        "items": [_prompt_item_to_dict(item) for item in _top_items(report.items, top)],
        "invalid_gpd_return_examples": [
            _invalid_gpd_return_example_to_dict(example) for example in report.invalid_gpd_return_examples
        ],
        "duplicate_invariants": [
            {
                "phrase": group.phrase,
                "occurrence_count": group.occurrence_count,
                "file_count": group.file_count,
                "severity": group.severity,
                "locations": list(group.locations),
            }
            for group in report.duplicate_invariants
        ],
        "exact_prose_assertion_files": [dict(entry) for entry in report.exact_prose_assertion_files],
        "warnings": list(report.warnings),
    }


def render_prompt_surface_markdown(report: PromptSurfaceReport, top: int | None = None) -> str:
    """Render a human-readable markdown report."""

    top_items = _top_items(report.items, top)
    totals = report.totals
    lines = [
        "# Prompt Surface Diagnostics",
        "",
        f"- Schema version: `{report.schema_version}`",
        f"- Repo root: `{report.repo_root}`",
        f"- Prompt sources: {totals.get('item_count', 0)}",
        f"- Expanded chars: {totals.get('expanded_char_count', 0)}",
        f"- Invalid `gpd_return` examples: {len(report.invalid_gpd_return_examples)}",
        f"- Hard-gate lines: {totals.get('hard_gate_line_count', 0)}",
        f"- Shell parsing lines: {totals.get('shell_parsing_line_count', 0)}",
        "",
        "## Top Prompt Sources",
        "",
        "| Rank | Kind | Name | Expanded chars | Raw lines | Includes | Hard gates | Shell parse | Schemas | Invalid returns | Rigidity |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for index, item in enumerate(top_items, start=1):
        lines.append(
            f"| {index} | {item.kind} | `{item.name}` | {item.expanded_char_count} | {item.raw_line_count} | "
            f"{item.raw_include_count} | {item.hard_gate_line_count} | {item.shell_parsing_line_count} | "
            f"{item.visible_schema_example_count} | {item.invalid_gpd_return_example_count} | "
            f"{item.rigidity_index} |"
        )

    if report.invalid_gpd_return_examples:
        lines.extend(
            [
                "",
                "## Invalid `gpd_return` Examples",
                "",
                "| Path | Lines | Errors | Preview |",
                "|---|---:|---|---|",
            ]
        )
        for example in report.invalid_gpd_return_examples:
            lines.append(
                f"| `{example.path}` | {example.start_line}-{example.end_line} | "
                f"{_markdown_table_cell('; '.join(example.errors))} | "
                f"`{_markdown_table_cell(example.preview)}` |"
            )

    runtime_totals = cast(Mapping[str, Mapping[str, object]], totals.get("runtime_projection", {}))
    if runtime_totals:
        lines.extend(
            [
                "",
                "## Runtime Projection Totals",
                "",
                "| Runtime | Native includes | Items | Projected chars | Includes | Runtime notes | Bridge calls |",
                "|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for runtime, metric in sorted(runtime_totals.items()):
            lines.append(
                f"| `{runtime}` | {str(metric.get('native_include_support', False)).lower()} | "
                f"{metric.get('item_count', 0)} | {metric.get('char_count', 0)} | "
                f"{metric.get('include_count', 0)} | {metric.get('runtime_note_count', 0)} | "
                f"{metric.get('bridge_command_occurrences', 0)} |"
            )

    duplicate_groups = report.duplicate_invariants[: top or len(report.duplicate_invariants)]
    if duplicate_groups:
        lines.extend(
            [
                "",
                "## Duplicate Invariants",
                "",
                "| Severity | Occurrences | Files | Phrase |",
                "|---|---:|---:|---|",
            ]
        )
        for group in duplicate_groups:
            lines.append(f"| {group.severity} | {group.occurrence_count} | {group.file_count} | `{group.phrase}` |")

    if report.exact_prose_assertion_files:
        lines.extend(
            [
                "",
                "## Prompt-Test Exactness",
                "",
                "| File | Exact assertions | Prose contracts | Machine contracts |",
                "|---|---:|---:|---:|",
            ]
        )
        for entry in report.exact_prose_assertion_files[: top or len(report.exact_prose_assertion_files)]:
            lines.append(
                f"| `{entry.get('path', '')}` | {entry.get('exact_assertion_count', 0)} | "
                f"{entry.get('prose_contract_assertions', 0)} | "
                f"{entry.get('machine_contract_assertions', 0)} |"
            )

    if report.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in report.warnings)

    return "\n".join(lines) + "\n"


def render_prompt_surface_table(report: PromptSurfaceReport, top: int | None = None) -> str:
    """Render a compact fixed-width table for terminal output."""

    rows = [
        (
            item.kind,
            item.name,
            str(item.expanded_char_count),
            str(item.raw_include_count),
            str(item.visible_schema_example_count),
            str(item.invalid_gpd_return_example_count),
            str(item.hard_gate_line_count),
            str(item.shell_parsing_line_count),
            str(item.rigidity_index),
        )
        for item in _top_items(report.items, top)
    ]
    headers = (
        "kind",
        "name",
        "expanded_chars",
        "includes",
        "schemas",
        "invalid",
        "hard_gates",
        "shell_parse",
        "rigidity",
    )
    widths = [len(header) for header in headers]
    for row in rows:
        widths = [max(width, len(cell)) for width, cell in zip(widths, row, strict=True)]

    def render_row(row: Sequence[str]) -> str:
        return "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip()

    lines = [render_row(headers), render_row(tuple("-" * width for width in widths))]
    lines.extend(render_row(row) for row in rows)
    return "\n".join(lines) + "\n"


def _source_root_for_repo(repo_root: Path) -> Path:
    src_root = repo_root / "src" / "gpd"
    if src_root.is_dir():
        return src_root
    if (repo_root / "commands").is_dir() and (repo_root / "agents").is_dir():
        return repo_root
    return src_root


def _normalize_surfaces(surfaces: Iterable[str] | str) -> tuple[PromptSurfaceKind, ...]:
    if isinstance(surfaces, str):
        raw_values = (surfaces,)
    else:
        raw_values = tuple(surfaces)
    if not raw_values or any(value == "all" for value in raw_values):
        return DEFAULT_SURFACES

    normalized: list[PromptSurfaceKind] = []
    for value in raw_values:
        if value not in DEFAULT_SURFACES:
            allowed = ", ".join((*DEFAULT_SURFACES, "all"))
            raise ValueError(f"surface must be one of: {allowed}")
        kind = cast(PromptSurfaceKind, value)
        if kind not in normalized:
            normalized.append(kind)
    return tuple(normalized)


def _normalize_runtime_names(runtime_names: Iterable[str] | str) -> tuple[str, ...]:
    descriptors = iter_runtime_descriptors()
    all_names = tuple(descriptor.runtime_name for descriptor in descriptors)
    if isinstance(runtime_names, str):
        raw_values = (runtime_names,)
    else:
        raw_values = tuple(runtime_names)
    if not raw_values:
        return ()
    if any(value == "all" for value in raw_values):
        return all_names

    normalized: list[str] = []
    for value in raw_values:
        runtime_name = normalize_runtime_name(value)
        if runtime_name is None:
            supported = ", ".join(all_names)
            raise KeyError(f"Unknown runtime {value!r}. Supported: {supported}")
        if runtime_name not in normalized:
            normalized.append(runtime_name)
    return tuple(normalized)


def _relative_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _line_count(text: str) -> int:
    return len(text.splitlines())


def _body_without_frontmatter(text: str) -> str:
    body, _line_offset = _body_without_frontmatter_with_line_offset(text)
    return body


def _body_without_frontmatter_with_line_offset(text: str) -> tuple[str, int]:
    _preamble, _frontmatter, _separator, body = split_markdown_frontmatter(text)
    prefix = text[: len(text) - len(body)]
    return body, prefix.count("\n")


def _markdown_fence_marker(stripped_line: str) -> str | None:
    if stripped_line.startswith("```"):
        return "```"
    if stripped_line.startswith("~~~"):
        return "~~~"
    return None


def _iter_markdown_fences(text: str) -> tuple[MarkdownFence, ...]:
    fences: list[MarkdownFence] = []
    active_marker: str | None = None
    active_info = ""
    active_start_line = 0
    active_body: list[str] = []

    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        marker = _markdown_fence_marker(stripped)
        if marker is None:
            if active_marker is not None:
                active_body.append(line)
            continue

        if active_marker is None:
            active_marker = marker
            active_info = stripped[len(marker) :].strip()
            active_start_line = line_number
            active_body = []
            continue

        if marker == active_marker:
            fences.append(
                MarkdownFence(
                    info=active_info,
                    body="\n".join(active_body),
                    start_line=active_start_line,
                    end_line=line_number,
                )
            )
            active_marker = None
            active_info = ""
            active_start_line = 0
            active_body = []
            continue

        active_body.append(line)

    return tuple(fences)


def _iter_unfenced_lines(text: str) -> tuple[tuple[int, str], ...]:
    lines: list[tuple[int, str]] = []
    active_marker: str | None = None

    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        marker = _markdown_fence_marker(stripped)
        if marker is not None:
            if active_marker is None:
                active_marker = marker
            elif marker == active_marker:
                active_marker = None
            continue
        if active_marker is not None:
            continue
        lines.append((line_number, line))
    return tuple(lines)


def _count_raw_includes(text: str) -> int:
    return sum(1 for _line_number, line in _iter_unfenced_lines(text) if parse_at_include_path(line.strip()))


def _count_shell_fences(text: str) -> int:
    count = 0
    for fence in _iter_markdown_fences(_body_without_frontmatter(text)):
        language = fence.info.lower().split(None, 1)[0] if fence.info else ""
        if language in DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES:
            count += 1
    return count


def _inspect_visible_schema_examples(text: str, path: str) -> tuple[int, tuple[InvalidGpdReturnExample, ...]]:
    body, line_offset = _body_without_frontmatter_with_line_offset(text)
    visible_count = 0
    invalid_return_examples: list[InvalidGpdReturnExample] = []

    for fence in _iter_markdown_fences(body):
        language = fence.info.lower().split(None, 1)[0] if fence.info else ""
        is_schema_block = _is_visible_schema_fence(language, fence.body)
        if not is_schema_block:
            continue
        visible_count += 1
        if not _contains_visible_gpd_return_example(fence.body):
            continue
        validation = validate_gpd_return_markdown(f"```yaml\n{fence.body}\n```")
        if validation.passed:
            continue
        invalid_return_examples.append(
            InvalidGpdReturnExample(
                path=path,
                start_line=fence.start_line + line_offset,
                end_line=fence.end_line + line_offset,
                errors=tuple(validation.errors),
                preview=_preview_fence_body(fence.body),
            )
        )

    spawn_contract_count = len(_SPAWN_CONTRACT_RE.findall(body))
    visible_count += spawn_contract_count
    return visible_count, tuple(invalid_return_examples)


def _is_visible_schema_fence(language: str, body: str) -> bool:
    if language in _SCHEMA_FENCE_LANGUAGES:
        return True
    if language in DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES:
        return False
    return any(marker in body for marker in _SCHEMA_BLOCK_MARKERS)


def _contains_visible_gpd_return_example(body: str) -> bool:
    return bool(_GPD_RETURN_EXAMPLE_RE.search(body))


def _preview_fence_body(body: str, max_chars: int = 140) -> str:
    preview = " ".join(line.strip() for line in body.splitlines() if line.strip())
    if len(preview) <= max_chars:
        return preview
    return preview[: max_chars - 3].rstrip() + "..."


def _hard_gate_metrics(text: str) -> tuple[int, float]:
    body = _body_without_frontmatter(text)
    lines = [(line_number, line) for line_number, line in _iter_unfenced_lines(body) if line.strip()]
    hard_gate_count = sum(1 for _line_number, line in lines if _HARD_GATE_LINE_RE.search(line))
    density = hard_gate_count / len(lines) if lines else 0.0
    return hard_gate_count, round(density, 6)


def _count_shell_parsing_lines(text: str) -> int:
    body = _body_without_frontmatter(text)
    count = 0
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.fullmatch(r"`?/?gpd:?help`?", stripped):
            continue
        if _SHELL_PARSING_RE.search(stripped):
            count += 1
    return count


def _measure_runtime_projection(
    source: PromptSource,
    raw_text: str,
    runtime_name: str,
) -> RuntimeProjectionMetric:
    descriptor = get_runtime_descriptor(runtime_name)
    projected_text = project_markdown_for_runtime(
        raw_text,
        runtime=runtime_name,
        path_prefix=DEFAULT_PATH_PREFIX,
        surface_kind=source.kind,
        src_root=source.src_root,
        protect_agent_prompt_body=source.kind == "agent",
        command_name=source.name,
    )
    runtime_note_lines = [line for line in projected_text.splitlines() if _RUNTIME_NOTE_RE.search(line)]
    return RuntimeProjectionMetric(
        runtime=runtime_name,
        native_include_support=descriptor.native_include_support,
        line_count=_line_count(projected_text),
        char_count=len(projected_text),
        include_count=_count_raw_includes(projected_text),
        runtime_note_count=len(runtime_note_lines),
        runtime_note_chars=sum(len(line) for line in runtime_note_lines),
        shell_fence_count=_count_shell_fences(projected_text),
        bridge_command_occurrences=len(_BRIDGE_COMMAND_RE.findall(projected_text)),
    )


def _build_totals(items: Sequence[PromptSurfaceItem]) -> dict[str, object]:
    numeric_fields = (
        "raw_line_count",
        "raw_char_count",
        "raw_include_count",
        "expanded_line_count",
        "expanded_char_count",
        "expanded_include_count",
        "unresolved_include_count",
        "visible_schema_example_count",
        "invalid_gpd_return_example_count",
        "hard_gate_line_count",
        "shell_fence_count",
        "shell_parsing_line_count",
        "rigidity_index",
    )
    totals: dict[str, object] = {"item_count": len(items)}
    for field in numeric_fields:
        totals[field] = sum(cast(int, getattr(item, field)) for item in items)

    by_kind: dict[str, dict[str, int]] = {}
    for kind in DEFAULT_SURFACES:
        kind_items = [item for item in items if item.kind == kind]
        by_kind[kind] = {"item_count": len(kind_items)}
        for field in numeric_fields:
            by_kind[kind][field] = sum(cast(int, getattr(item, field)) for item in kind_items)
    totals["by_kind"] = by_kind
    totals["runtime_projection"] = _runtime_projection_totals(items)
    return totals


def _runtime_projection_totals(items: Sequence[PromptSurfaceItem]) -> dict[str, dict[str, object]]:
    totals: dict[str, dict[str, object]] = {}
    for item in items:
        for metric in item.runtime_projection:
            runtime_totals = totals.setdefault(
                metric.runtime,
                {
                    "native_include_support": metric.native_include_support,
                    "item_count": 0,
                    "line_count": 0,
                    "char_count": 0,
                    "include_count": 0,
                    "runtime_note_count": 0,
                    "runtime_note_chars": 0,
                    "shell_fence_count": 0,
                    "bridge_command_occurrences": 0,
                },
            )
            runtime_totals["item_count"] = cast(int, runtime_totals["item_count"]) + 1
            runtime_totals["line_count"] = cast(int, runtime_totals["line_count"]) + metric.line_count
            runtime_totals["char_count"] = cast(int, runtime_totals["char_count"]) + metric.char_count
            runtime_totals["include_count"] = cast(int, runtime_totals["include_count"]) + metric.include_count
            runtime_totals["runtime_note_count"] = (
                cast(int, runtime_totals["runtime_note_count"]) + metric.runtime_note_count
            )
            runtime_totals["runtime_note_chars"] = (
                cast(int, runtime_totals["runtime_note_chars"]) + metric.runtime_note_chars
            )
            runtime_totals["shell_fence_count"] = (
                cast(int, runtime_totals["shell_fence_count"]) + metric.shell_fence_count
            )
            runtime_totals["bridge_command_occurrences"] = (
                cast(int, runtime_totals["bridge_command_occurrences"]) + metric.bridge_command_occurrences
            )
    return totals


def _duplicate_scan_paths(repo_root: Path, *, include_tests: bool) -> tuple[Path, ...]:
    src_root = _source_root_for_repo(repo_root)
    roots = (
        src_root / "commands",
        src_root / "agents",
        src_root / "specs" / "workflows",
        src_root / "specs" / "references",
        src_root / "specs" / "templates",
    )
    paths: list[Path] = []
    for root in roots:
        if root.is_dir():
            paths.extend(path for path in sorted(root.rglob("*.md")) if path.is_file() and not path.is_symlink())
    if include_tests:
        tests_root = repo_root / "tests"
        if tests_root.is_dir():
            paths.extend(path for path in sorted(tests_root.rglob("*.py")) if path.is_file() and not path.is_symlink())
    return tuple(paths)


def _duplicate_invariant_groups(repo_root: Path, *, include_tests: bool) -> tuple[DuplicateInvariantGroup, ...]:
    occurrences: dict[str, list[str]] = defaultdict(list)
    files_by_phrase: dict[str, set[str]] = defaultdict(set)
    non_reference_files_by_phrase: dict[str, set[str]] = defaultdict(set)

    for path in _duplicate_scan_paths(repo_root, include_tests=include_tests):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        relative_path = _relative_path(path, repo_root)
        for line_number, line in _iter_unfenced_lines(_body_without_frontmatter(text)):
            phrase = _normalize_duplicate_line(line)
            if not _is_candidate_duplicate_phrase(phrase):
                continue
            location = f"{relative_path}:{line_number}"
            occurrences[phrase].append(location)
            files_by_phrase[phrase].add(relative_path)
            if not _is_reference_or_template_path(relative_path):
                non_reference_files_by_phrase[phrase].add(relative_path)

    groups: list[DuplicateInvariantGroup] = []
    for phrase, locations in occurrences.items():
        file_count = len(files_by_phrase[phrase])
        non_reference_file_count = len(non_reference_files_by_phrase[phrase])
        if len(locations) < 3 and non_reference_file_count < 2:
            continue
        groups.append(
            DuplicateInvariantGroup(
                phrase=phrase,
                occurrence_count=len(locations),
                file_count=file_count,
                severity=_duplicate_severity(phrase, non_reference_file_count),
                locations=tuple(locations[:30]),
            )
        )

    severity_order = {"high": 0, "warn": 1, "info": 2}
    return tuple(
        sorted(
            groups,
            key=lambda group: (
                severity_order[group.severity],
                -group.file_count,
                -group.occurrence_count,
                group.phrase,
            ),
        )
    )


def _normalize_duplicate_line(line: str) -> str:
    normalized = line.strip()
    normalized = re.sub(r"^\s*(?:[-*+]|\d+[.)]|#+|>)\s*", "", normalized)
    normalized = normalized.strip("`*_ ")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.casefold()


def _is_candidate_duplicate_phrase(phrase: str) -> bool:
    if not phrase:
        return False
    folded = phrase.replace("_", " ").replace("-", " ")
    if not any(
        candidate.casefold() in phrase or candidate.casefold().replace("-", " ") in folded
        for candidate in _DUPLICATE_VOCABULARY
    ):
        return False
    word_count = len(re.findall(r"[a-z0-9_'-]+", phrase))
    if word_count >= 9:
        return True
    return any(
        marker in phrase
        for marker in (
            "use only status names",
            "frontmatter aliases",
            "non-canonical frontmatter",
            "presentation only",
        )
    )


def _is_reference_or_template_path(relative_path: str) -> bool:
    return "/specs/references/" in f"/{relative_path}" or "/specs/templates/" in f"/{relative_path}"


def _duplicate_severity(phrase: str, non_reference_file_count: int) -> Literal["info", "warn", "high"]:
    if non_reference_file_count == 0:
        return "info"
    if non_reference_file_count >= 5 or ("child" in phrase and "return" in phrase and "authoritative" in phrase):
        return "high"
    if non_reference_file_count >= 2:
        return "warn"
    return "info"


def _scan_exact_prompt_assertions(repo_root: Path) -> tuple[Mapping[str, object], ...]:
    tests_root = repo_root / "tests"
    if not tests_root.is_dir():
        return ()

    entries: list[Mapping[str, object]] = []
    for path in sorted(tests_root.rglob("*.py")):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
        literals = _prompt_exact_literals(tree)
        if not literals:
            continue
        prose = [literal for literal in literals if _classify_exact_literal(literal) == "prose"]
        machine = [literal for literal in literals if _classify_exact_literal(literal) == "machine"]
        entries.append(
            {
                "path": _relative_path(path, repo_root),
                "exact_assertion_count": len(literals),
                "prose_contract_assertions": len(prose),
                "machine_contract_assertions": len(machine),
                "examples": tuple(literals[:5]),
            }
        )
    return tuple(
        sorted(
            entries,
            key=lambda entry: (
                -cast(int, entry["prose_contract_assertions"]),
                -cast(int, entry["exact_assertion_count"]),
                cast(str, entry["path"]),
            ),
        )
    )


def _prompt_exact_literals(tree: ast.AST) -> tuple[str, ...]:
    literals: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            literals.extend(_assert_exact_literals(node.test))
        elif isinstance(node, ast.Call):
            literals.extend(_method_exact_literals(node))
    return tuple(literal for literal in literals if _is_prompt_literal(literal))


def _assert_exact_literals(node: ast.AST) -> tuple[str, ...]:
    if not isinstance(node, ast.Compare):
        return ()
    literals: list[str] = []
    for op in node.ops:
        if isinstance(op, (ast.In, ast.NotIn)):
            literal = _string_constant(node.left)
            if literal is not None:
                literals.append(literal)
            for comparator in node.comparators:
                literal = _string_constant(comparator)
                if literal is not None:
                    literals.append(literal)
    return tuple(literals)


def _method_exact_literals(node: ast.Call) -> tuple[str, ...]:
    if not isinstance(node.func, ast.Attribute) or node.func.attr not in {"count", "index"}:
        return ()
    literals: list[str] = []
    for arg in node.args[:1]:
        literal = _string_constant(arg)
        if literal is not None:
            literals.append(literal)
    return tuple(literals)


def _string_constant(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_prompt_literal(literal: str) -> bool:
    stripped = literal.strip()
    if len(stripped) < 12:
        return False
    if "\n" in stripped:
        return True
    return bool(re.search(r"[A-Za-z]{3,}\s+[A-Za-z]{3,}", stripped) or _MACHINE_CONTRACT_RE.search(stripped))


def _classify_exact_literal(literal: str) -> Literal["machine", "prose"]:
    if _MACHINE_CONTRACT_RE.search(literal):
        return "machine"
    if len(literal.split()) >= 5:
        return "prose"
    return "machine"


def _top_items(items: Sequence[PromptSurfaceItem], top: int | None) -> tuple[PromptSurfaceItem, ...]:
    sorted_items = sorted(
        items,
        key=lambda item: (-item.expanded_char_count, -item.rigidity_index, item.kind, item.name),
    )
    if top is None or top <= 0:
        return tuple(sorted_items)
    return tuple(sorted_items[:top])


def _prompt_item_to_dict(item: PromptSurfaceItem) -> dict[str, object]:
    return {
        "kind": item.kind,
        "name": item.name,
        "path": item.path,
        "raw_line_count": item.raw_line_count,
        "raw_char_count": item.raw_char_count,
        "raw_include_count": item.raw_include_count,
        "expanded_line_count": item.expanded_line_count,
        "expanded_char_count": item.expanded_char_count,
        "expanded_include_count": item.expanded_include_count,
        "unresolved_include_count": item.unresolved_include_count,
        "visible_schema_example_count": item.visible_schema_example_count,
        "invalid_gpd_return_example_count": item.invalid_gpd_return_example_count,
        "invalid_gpd_return_examples": [
            _invalid_gpd_return_example_to_dict(example) for example in item.invalid_gpd_return_examples
        ],
        "hard_gate_line_count": item.hard_gate_line_count,
        "hard_gate_density": item.hard_gate_density,
        "shell_fence_count": item.shell_fence_count,
        "shell_parsing_line_count": item.shell_parsing_line_count,
        "rigidity_index": item.rigidity_index,
        "runtime_projection": [
            {
                "runtime": metric.runtime,
                "native_include_support": metric.native_include_support,
                "line_count": metric.line_count,
                "char_count": metric.char_count,
                "include_count": metric.include_count,
                "runtime_note_count": metric.runtime_note_count,
                "runtime_note_chars": metric.runtime_note_chars,
                "shell_fence_count": metric.shell_fence_count,
                "bridge_command_occurrences": metric.bridge_command_occurrences,
            }
            for metric in item.runtime_projection
        ],
    }


def _invalid_gpd_return_example_to_dict(example: InvalidGpdReturnExample) -> dict[str, object]:
    return {
        "path": example.path,
        "start_line": example.start_line,
        "end_line": example.end_line,
        "errors": list(example.errors),
        "preview": example.preview,
    }


def _markdown_table_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("`", "\\`").replace("\n", " ")
