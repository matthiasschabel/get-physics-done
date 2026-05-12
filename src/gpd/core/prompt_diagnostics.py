"""Read-only prompt-surface diagnostics for canonical GPD sources."""

from __future__ import annotations

import difflib
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import yaml

from gpd.adapters.install_utils import (
    DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES,
    build_runtime_cli_bridge_command,
    expand_at_includes,
    project_markdown_for_runtime,
    projection_target_dir_from_path_prefix,
)
from gpd.adapters.runtime_catalog import (
    get_runtime_descriptor,
    iter_runtime_descriptors,
    normalize_runtime_name,
)
from gpd.core import prompt_markdown_scan as _prompt_markdown_scan
from gpd.core.frontmatter import (
    UNSUPPORTED_FRONTMATTER_FIELDS,
    VERIFICATION_REPORT_STATUSES,
    FrontmatterParseError,
    extract_frontmatter,
    validate_frontmatter,
)
from gpd.core.prompt_exactness_diagnostics import (
    EXACT_ASSERTION_THRESHOLDS as _EXACT_ASSERTION_THRESHOLDS,
)
from gpd.core.prompt_exactness_diagnostics import (
    bounded_exact_assertion_diagnostics as _bounded_exact_assertion_diagnostics,
)
from gpd.core.prompt_exactness_diagnostics import (
    empty_exact_assertion_diagnostics as _empty_exact_assertion_diagnostics,
)
from gpd.core.prompt_exactness_diagnostics import (
    exact_assertion_file_rows as _exact_assertion_file_rows,
)
from gpd.core.prompt_exactness_diagnostics import (
    exact_prose_assertion_files_from_diagnostics as _exact_prose_assertion_files_from_diagnostics,
)
from gpd.core.prompt_exactness_diagnostics import (
    scan_exact_assertion_diagnostics as _scan_exact_assertion_diagnostics,
)
from gpd.core.prompt_semantic_duplicate_diagnostics import (
    SemanticDuplicateGroup,
    SemanticDuplicateOccurrence,
)
from gpd.core.prompt_semantic_duplicate_diagnostics import (
    scan_semantic_duplicate_invariant_groups as _scan_semantic_duplicate_invariant_groups,
)
from gpd.core.prompt_semantic_duplicate_diagnostics import (
    semantic_example_limit as _semantic_example_limit,
)
from gpd.core.prompt_semantic_duplicate_diagnostics import (
    status_handling_terms as _semantic_status_handling_terms,
)
from gpd.core.prompt_stage_diagnostics import (
    AuthorityPromptMetric,
    MustNotEagerLoadViolation,
    StageAwareWorkflowPromptMetric,
    WorkflowStagePromptMetric,
)
from gpd.core.prompt_stage_diagnostics import (
    build_stage_diagnostics as _build_stage_diagnostics,
)
from gpd.core.prompt_stage_diagnostics import (
    stage_authority_top_rows as _stage_authority_top_rows,
)
from gpd.core.prompt_stage_diagnostics import (
    stage_diagnostic_to_dict as _stage_diagnostic_to_dict,
)
from gpd.core.prompt_stage_diagnostics import (
    stage_diagnostics_totals as _stage_diagnostics_totals,
)
from gpd.core.prompt_stage_diagnostics import (
    stage_init_field_top_rows as _stage_init_field_top_rows,
)
from gpd.core.prompt_stage_diagnostics import (
    stage_top_prompt_rows as _stage_top_prompt_rows,
)
from gpd.core.prompt_stage_diagnostics import (
    top_stage_diagnostics as _top_stage_diagnostics,
)
from gpd.core.return_contract import (
    KNOWN_RETURN_FIELD_NAMES,
    return_field_allowed_source,
    validate_gpd_return_markdown,
)

MarkdownFence = _prompt_markdown_scan.MarkdownFence
_body_without_frontmatter = _prompt_markdown_scan.body_without_frontmatter
_body_without_frontmatter_with_line_offset = _prompt_markdown_scan.body_without_frontmatter_with_line_offset
_count_raw_includes = _prompt_markdown_scan.count_raw_includes
_iter_markdown_fences = _prompt_markdown_scan.iter_markdown_fences
_iter_unfenced_lines = _prompt_markdown_scan.iter_unfenced_lines
_line_count = _prompt_markdown_scan.line_count
_relative_path = _prompt_markdown_scan.relative_path
_top_limit = _prompt_markdown_scan.top_limit

PromptSurfaceKind = Literal["command", "agent", "workflow"]

PROMPT_SURFACE_REPORT_SCHEMA_VERSION = "prompt_surface_diagnostics.v8"
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
_MARKDOWN_FRONTMATTER_FENCE_LANGUAGES = frozenset({"markdown", "md", ""})
_VERIFICATION_FRONTMATTER_KEYS = frozenset(
    {
        "phase",
        "verified",
        "status",
        "score",
        "plan_contract_ref",
        "contract_results",
        "comparison_verdicts",
        "suggested_contract_checks",
    }
)
_VERIFICATION_FRONTMATTER_STRONG_KEYS = frozenset(
    {
        "plan_contract_ref",
        "contract_results",
        "comparison_verdicts",
        "suggested_contract_checks",
    }
)
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
_GPD_RETURN_FIELD_REFERENCE_RE = re.compile(r"(?<![A-Za-z0-9_])\.?gpd_return\.([A-Za-z_][A-Za-z0-9_]*)")
_RETURN_FIELD_DECLARATION_RE = re.compile(
    r"\b(?:extended fields?|role-specific field|agent-specific extended field|role fields such as)\b",
    re.IGNORECASE,
)
_ROLE_FIELD_DECLARATION_RE = re.compile(
    r"\b(?:role-specific field|agent-specific extended field|role fields such as)\b",
    re.IGNORECASE,
)
_BACKTICK_IDENTIFIER_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")
_IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
_RETURN_FIELD_NEGATION_RE = re.compile(
    r"\b(?:do not|don't|never|forbidden|must not|not part of|omit|without)\b",
    re.IGNORECASE,
)
_YAML_KEY_RE = re.compile(r"^(?P<indent>\s*)(?P<key>['\"]?[A-Za-z_][A-Za-z0-9_]*['\"]?)\s*:")
_FIELD_DECLARATION_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "come",
        "comes",
        "extended",
        "field",
        "fields",
        "from",
        "include",
        "is",
        "must",
        "or",
        "role",
        "such",
        "the",
        "these",
        "this",
        "top",
        "with",
    }
)
_CHILD_RETURN_SYNTHESIS_CLAUSE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|;\s*")
_CHILD_RETURN_SYNTHESIS_ACTION_RE = re.compile(
    r"\b(?P<action>"
    r"synthesi[sz]e|synthesi[sz]ed|synthesi[sz]ing|"
    r"fabricate|fabricated|fabricating|"
    r"patch|patched|patching|"
    r"paste|pasted|pasting|"
    r"hand-author|hand-authored|hand-authoring|hand author|hand authored|hand authoring"
    r")\b",
    re.IGNORECASE,
)
_CHILD_RETURN_SYNTHESIS_CONTEXT_RE = re.compile(
    r"\b(?:child|planner|checker|verifier|agent|subagent)\b.{0,140}"
    r"\b(?:gpd_return|return envelope)\b|"
    r"\b(?:gpd_return|return envelope)\b.{0,140}"
    r"\b(?:child|planner|checker|verifier|agent|subagent)\b",
    re.IGNORECASE,
)
_CHILD_RETURN_SYNTHESIS_NEGATION_RE = re.compile(
    r"\b(?:do not|don't|never|must not|should not|cannot|can't|forbidden|not allowed|without|instead of)\b",
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
class RuntimeProjectionMetric:
    runtime: str
    native_include_support: bool
    expanded_line_count: int
    expanded_char_count: int
    line_count: int
    char_count: int
    line_delta: int
    char_delta: int
    char_delta_percent: float
    include_count: int
    runtime_note_count: int
    runtime_note_chars: int
    shell_fence_count: int
    shell_rewrite_count: int
    bridge_command_occurrences: int


@dataclass(frozen=True, slots=True)
class InvalidGpdReturnExample:
    path: str
    start_line: int
    end_line: int
    errors: tuple[str, ...]
    preview: str


@dataclass(frozen=True, slots=True)
class InvalidFrontmatterExample:
    path: str
    start_line: int
    end_line: int
    schema_name: Literal["verification"]
    fields: tuple[str, ...]
    errors: tuple[str, ...]
    preview: str


@dataclass(frozen=True, slots=True)
class PromptReturnFieldMention:
    path: str
    line: int
    field: str
    mention_kind: Literal[
        "direct_reference",
        "extended_field_list",
        "role_field_statement",
        "yaml_example_key",
    ]
    polarity: Literal["positive", "negative"]
    allowed: bool
    allowed_source: Literal["base", "extension", "unknown"]
    severity: Literal["info", "warn", "error"]
    snippet: str
    suggestion: str | None = None


@dataclass(frozen=True, slots=True)
class ForbiddenChildReturnSynthesisMention:
    path: str
    line: int
    action: str
    polarity: Literal["positive"]
    severity: Literal["error"]
    snippet: str


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
    invalid_frontmatter_example_count: int
    invalid_frontmatter_examples: tuple[InvalidFrontmatterExample, ...]
    return_field_mention_count: int
    disallowed_return_field_mention_count: int
    disallowed_return_field_mentions: tuple[PromptReturnFieldMention, ...]
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
    stage_diagnostics: tuple[StageAwareWorkflowPromptMetric, ...]
    invalid_gpd_return_examples: tuple[InvalidGpdReturnExample, ...]
    invalid_frontmatter_examples: tuple[InvalidFrontmatterExample, ...]
    return_field_mentions: tuple[PromptReturnFieldMention, ...]
    disallowed_return_field_mentions: tuple[PromptReturnFieldMention, ...]
    forbidden_child_return_synthesis_mentions: tuple[ForbiddenChildReturnSynthesisMention, ...]
    duplicate_invariants: tuple[DuplicateInvariantGroup, ...]
    semantic_duplicate_invariants: tuple[SemanticDuplicateGroup, ...]
    exact_assertion_diagnostics: Mapping[str, object]
    exact_prose_assertion_files: tuple[Mapping[str, object], ...]
    warnings: tuple[str, ...]


__all__ = [
    "DEFAULT_SURFACES",
    "PROMPT_SURFACE_REPORT_SCHEMA_VERSION",
    "AuthorityPromptMetric",
    "DuplicateInvariantGroup",
    "ForbiddenChildReturnSynthesisMention",
    "InvalidFrontmatterExample",
    "InvalidGpdReturnExample",
    "MustNotEagerLoadViolation",
    "PromptSource",
    "PromptReturnFieldMention",
    "PromptSurfaceItem",
    "PromptSurfaceReport",
    "RuntimeProjectionMetric",
    "SemanticDuplicateGroup",
    "SemanticDuplicateOccurrence",
    "StageAwareWorkflowPromptMetric",
    "WorkflowStagePromptMetric",
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
    (
        visible_schema_example_count,
        invalid_return_examples,
        invalid_frontmatter_examples,
    ) = _inspect_visible_schema_examples(raw_text, source.path)
    invalid_return_count = len(invalid_return_examples)
    invalid_frontmatter_count = len(invalid_frontmatter_examples)
    return_field_mentions = _scan_return_field_mentions(raw_text, source.path)
    disallowed_return_field_mentions = _disallowed_return_field_mentions(return_field_mentions)
    hard_gate_line_count, hard_gate_density = _hard_gate_metrics(raw_text)
    shell_fence_count = _count_shell_fences(raw_text)
    shell_parsing_line_count = _count_shell_parsing_lines(raw_text)
    unresolved_include_count = len(_UNRESOLVED_INCLUDE_RE.findall(expanded_text))

    runtime_projection: tuple[RuntimeProjectionMetric, ...] = ()
    if include_runtime_projections and source.kind in {"command", "agent"}:
        runtime_projection = tuple(
            _measure_runtime_projection(source, raw_text, expanded_text, runtime_name)
            for runtime_name in _normalize_runtime_names(runtime_names)
        )

    rigidity_index = (
        2 * visible_schema_example_count
        + 3 * invalid_return_count
        + 3 * invalid_frontmatter_count
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
        invalid_frontmatter_example_count=invalid_frontmatter_count,
        invalid_frontmatter_examples=invalid_frontmatter_examples,
        return_field_mention_count=len(return_field_mentions),
        disallowed_return_field_mention_count=len(disallowed_return_field_mentions),
        disallowed_return_field_mentions=disallowed_return_field_mentions,
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
    duplicate_invariants: tuple[DuplicateInvariantGroup, ...] = ()
    semantic_duplicate_invariants = _semantic_duplicate_invariant_groups(root, include_tests=include_tests)
    exact_assertion_diagnostics = (
        _scan_exact_assertion_diagnostics(root) if include_tests else _empty_exact_assertion_diagnostics()
    )
    exact_assertions = _exact_prose_assertion_files_from_diagnostics(exact_assertion_diagnostics)
    invalid_return_examples = tuple(example for item in items for example in item.invalid_gpd_return_examples)
    invalid_frontmatter_examples = tuple(example for item in items for example in item.invalid_frontmatter_examples)
    return_field_mentions = _scan_return_field_mentions_for_repo(root, include_tests=include_tests)
    disallowed_return_field_mentions = _disallowed_return_field_mentions(return_field_mentions)
    forbidden_child_return_synthesis_mentions = _scan_forbidden_child_return_synthesis_mentions(sources)
    stage_diagnostics = _build_stage_diagnostics(
        sources,
        items,
        report_warnings=warnings,
        path_prefix=DEFAULT_PATH_PREFIX,
    )

    return PromptSurfaceReport(
        schema_version=PROMPT_SURFACE_REPORT_SCHEMA_VERSION,
        repo_root=str(root),
        totals=_build_totals(
            items,
            stage_diagnostics=stage_diagnostics,
            return_field_mentions=return_field_mentions,
            forbidden_child_return_synthesis_mentions=forbidden_child_return_synthesis_mentions,
        ),
        items=items,
        stage_diagnostics=stage_diagnostics,
        invalid_gpd_return_examples=invalid_return_examples,
        invalid_frontmatter_examples=invalid_frontmatter_examples,
        return_field_mentions=return_field_mentions,
        disallowed_return_field_mentions=disallowed_return_field_mentions,
        forbidden_child_return_synthesis_mentions=forbidden_child_return_synthesis_mentions,
        duplicate_invariants=duplicate_invariants,
        semantic_duplicate_invariants=semantic_duplicate_invariants,
        exact_assertion_diagnostics=exact_assertion_diagnostics,
        exact_prose_assertion_files=exact_assertions,
        warnings=tuple(warnings),
    )


def report_to_dict(report: PromptSurfaceReport, top: int | None = None) -> dict[str, object]:
    """Convert a report into JSON-serializable primitives."""

    limit = _top_limit(top)
    stage_authority_rows = _stage_authority_top_prompt_rows(report.stage_diagnostics, top)
    stage_init_field_rows = _stage_init_field_pressure_rows(report.stage_diagnostics, top)
    return {
        "schema_version": report.schema_version,
        "repo_root": report.repo_root,
        "totals": report.totals,
        "items": [_prompt_item_to_dict(item) for item in _top_items(report.items, top)],
        "runtime_top_prompts": _runtime_top_prompts_to_dict(report.items, top),
        "stage_diagnostics": [
            _stage_diagnostic_to_dict(metric) for metric in _top_stage_diagnostics(report.stage_diagnostics, top)
        ],
        "stage_authority_top_prompts": list(stage_authority_rows),
        "stage_authority_top": list(stage_authority_rows),
        "stage_init_field_diagnostics": list(stage_init_field_rows),
        "stage_field_payload_pressure": list(stage_init_field_rows),
        "invalid_gpd_return_examples": [
            _invalid_gpd_return_example_to_dict(example) for example in report.invalid_gpd_return_examples
        ],
        "invalid_frontmatter_examples": [
            _invalid_frontmatter_example_to_dict(example) for example in report.invalid_frontmatter_examples
        ],
        "disallowed_return_field_mentions": [
            _return_field_mention_to_dict(mention) for mention in report.disallowed_return_field_mentions
        ],
        "forbidden_child_return_synthesis_mentions": [
            _forbidden_child_return_synthesis_mention_to_dict(mention)
            for mention in report.forbidden_child_return_synthesis_mentions
        ],
        "duplicate_invariants": [
            {
                "phrase": group.phrase,
                "occurrence_count": group.occurrence_count,
                "file_count": group.file_count,
                "severity": group.severity,
                "locations": list(group.locations),
            }
            for group in report.duplicate_invariants[:limit]
        ],
        "semantic_duplicate_invariants": [
            {
                "category": group.category,
                "label": group.label,
                "occurrence_count": group.occurrence_count,
                "file_count": group.file_count,
                "non_reference_occurrence_count": group.non_reference_occurrence_count,
                "non_reference_file_count": group.non_reference_file_count,
                "severity": group.severity,
                "canonical_references": list(group.canonical_references),
                "suggested_action": group.suggested_action,
                "examples": [
                    {
                        "path": example.path,
                        "line": example.line,
                        "category": example.category,
                        "snippet": example.snippet,
                        "matched_terms": list(example.matched_terms),
                        "is_reference_or_template": example.is_reference_or_template,
                    }
                    for example in group.examples[: _semantic_example_limit(top)]
                ],
            }
            for group in report.semantic_duplicate_invariants[:limit]
        ],
        "exact_assertion_diagnostics": _bounded_exact_assertion_diagnostics(report.exact_assertion_diagnostics, top),
        "exact_prose_assertion_files": [dict(entry) for entry in report.exact_prose_assertion_files[:limit]],
        "warnings": list(report.warnings),
    }


def _stage_authority_top_prompt_rows(
    stage_diagnostics: Sequence[StageAwareWorkflowPromptMetric],
    top: int | None,
) -> tuple[dict[str, object], ...]:
    return tuple(dict(row) for row in _stage_authority_top_rows(stage_diagnostics, top))


def _stage_init_field_pressure_rows(
    stage_diagnostics: Sequence[StageAwareWorkflowPromptMetric],
    top: int | None,
) -> tuple[dict[str, object], ...]:
    return tuple(dict(row) for row in _stage_init_field_top_rows(stage_diagnostics, top))


def _row_int(row: Mapping[str, object], *keys: str) -> int:
    for key in keys:
        value = row.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return 0


def _row_text(row: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None:
            return str(value)
    return ""


def _fixed_table_lines(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
) -> list[str]:
    widths = [len(header) for header in headers]
    for row in rows:
        widths = [max(width, len(cell)) for width, cell in zip(widths, row, strict=True)]

    def render_row(row: Sequence[str]) -> str:
        return "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip()

    return [render_row(headers), render_row(tuple("-" * width for width in widths)), *(render_row(row) for row in rows)]


def _fixed_table_section_lines(
    title: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
) -> list[str]:
    if not rows:
        return []
    return ["", title, *_fixed_table_lines(headers, rows)]


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
        f"- Invalid verification frontmatter examples: {len(report.invalid_frontmatter_examples)}",
        f"- Disallowed `gpd_return` field mentions: {len(report.disallowed_return_field_mentions)}",
        f"- Forbidden child `gpd_return` synthesis instructions: "
        f"{len(report.forbidden_child_return_synthesis_mentions)}",
        f"- Hard-gate lines: {totals.get('hard_gate_line_count', 0)}",
        f"- Shell parsing lines: {totals.get('shell_parsing_line_count', 0)}",
        "",
        "## Top Prompt Sources",
        "",
        "| Rank | Kind | Name | Expanded chars | Raw lines | Includes | Hard gates | Shell parse | Schemas | Invalid returns | Invalid frontmatter | Bad fields | Rigidity |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for index, item in enumerate(top_items, start=1):
        lines.append(
            f"| {index} | {item.kind} | `{item.name}` | {item.expanded_char_count} | {item.raw_line_count} | "
            f"{item.raw_include_count} | {item.hard_gate_line_count} | {item.shell_parsing_line_count} | "
            f"{item.visible_schema_example_count} | {item.invalid_gpd_return_example_count} | "
            f"{item.invalid_frontmatter_example_count} | "
            f"{item.disallowed_return_field_mention_count} | "
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

    if report.invalid_frontmatter_examples:
        lines.extend(
            [
                "",
                "## Invalid Verification Frontmatter Examples",
                "",
                "| Path | Lines | Schema | Fields | Errors | Preview |",
                "|---|---:|---|---|---|---|",
            ]
        )
        for example in report.invalid_frontmatter_examples:
            lines.append(
                f"| `{example.path}` | {example.start_line}-{example.end_line} | `{example.schema_name}` | "
                f"{_markdown_table_cell(', '.join(example.fields))} | "
                f"{_markdown_table_cell('; '.join(example.errors))} | "
                f"`{_markdown_table_cell(example.preview)}` |"
            )

    if report.disallowed_return_field_mentions:
        lines.extend(
            [
                "",
                "## Disallowed `gpd_return` Field Mentions",
                "",
                "| Path | Line | Field | Kind | Suggestion | Snippet |",
                "|---|---:|---|---|---|---|",
            ]
        )
        for mention in report.disallowed_return_field_mentions:
            suggestion = mention.suggestion or ""
            lines.append(
                f"| `{mention.path}` | {mention.line} | `{mention.field}` | {mention.mention_kind} | "
                f"{_markdown_table_cell(suggestion)} | `{_markdown_table_cell(mention.snippet)}` |"
            )

    if report.forbidden_child_return_synthesis_mentions:
        lines.extend(
            [
                "",
                "## Forbidden Child `gpd_return` Synthesis Instructions",
                "",
                "| Path | Line | Action | Snippet |",
                "|---|---:|---|---|",
            ]
        )
        for mention in report.forbidden_child_return_synthesis_mentions:
            lines.append(
                f"| `{mention.path}` | {mention.line} | `{mention.action}` | "
                f"`{_markdown_table_cell(mention.snippet)}` |"
            )

    runtime_totals = cast(Mapping[str, Mapping[str, object]], totals.get("runtime_projection", {}))
    if runtime_totals:
        lines.extend(
            [
                "",
                "## Runtime Projection Totals",
                "",
                "| Runtime | Native includes | Items | Projected chars | Char delta | Includes | Runtime notes | Bridge calls |",
                "|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for runtime, metric in sorted(runtime_totals.items()):
            lines.append(
                f"| `{runtime}` | {str(metric.get('native_include_support', False)).lower()} | "
                f"{metric.get('item_count', 0)} | {metric.get('char_count', 0)} | "
                f"{metric.get('char_delta', 0)} | "
                f"{metric.get('include_count', 0)} | {metric.get('runtime_note_count', 0)} | "
                f"{metric.get('bridge_command_occurrences', 0)} |"
            )

    runtime_top_prompts = _runtime_top_prompt_rows(report.items, top)
    if runtime_top_prompts:
        lines.extend(
            [
                "",
                "## Runtime Top Prompts",
                "",
                "| Runtime | Rank | Native includes | Kind | Name | Projected chars | Expanded chars | Char delta | Line delta | Includes | Runtime notes | Shell fences | Shell rewrites | Bridge calls |",
                "|---|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        ranks_by_runtime: dict[str, int] = defaultdict(int)
        for row in runtime_top_prompts:
            runtime = str(row["runtime"])
            ranks_by_runtime[runtime] += 1
            lines.append(
                f"| `{runtime}` | {ranks_by_runtime[runtime]} | "
                f"{str(row['native_include_support']).lower()} | {row['kind']} | `{row['name']}` | "
                f"{row['projected_char_count']} | {row['expanded_char_count']} | "
                f"{row['char_delta']} | {row['line_delta']} | {row['include_count']} | "
                f"{row['runtime_note_count']} | {row['shell_fence_count']} | "
                f"{row['shell_rewrite_count']} | {row['bridge_command_occurrences']} |"
            )

    stage_top_prompts = _stage_top_prompt_rows(report.stage_diagnostics, top)
    if stage_top_prompts:
        lines.extend(
            [
                "",
                "## Stage-Aware Staged Loading",
                "",
                "| Workflow | Stage | First-turn chars | Eager chars | Lazy chars | Violations |",
                "|---|---|---:|---:|---:|---:|",
            ]
        )
        for row in stage_top_prompts:
            lines.append(
                f"| `{row['workflow_id']}` | `{row['stage_id']}` | {row['first_turn_char_count']} | "
                f"{row['eager_char_count']} | {row['lazy_char_count']} | {row['violation_count']} |"
            )

    stage_authority_rows = _stage_authority_top_prompt_rows(report.stage_diagnostics, top)
    if stage_authority_rows:
        lines.extend(
            [
                "",
                "## Stage Authority Hotspots",
                "",
                "| Workflow | Stage | Bucket | Authority | Expanded chars | Lines | Includes | Transitive includes |",
                "|---|---|---|---|---:|---:|---:|---:|",
            ]
        )
        for row in stage_authority_rows:
            lines.append(
                f"| `{_row_text(row, 'workflow_id')}` | `{_row_text(row, 'stage_id')}` | "
                f"{_row_text(row, 'bucket')} | `{_row_text(row, 'authority')}` | "
                f"{_row_int(row, 'expanded_char_count')} | {_row_int(row, 'expanded_line_count')} | "
                f"{_row_int(row, 'raw_include_count')} | "
                f"{_row_int(row, 'transitive_include_count')} |"
            )

    stage_init_field_rows = _stage_init_field_pressure_rows(report.stage_diagnostics, top)
    if stage_init_field_rows:
        lines.extend(
            [
                "",
                "## Staged-Init Field Pressure",
                "",
                "| Workflow | Stage | Required fields | Likely bulky | Field | Kind | Pressure | Selections |",
                "|---|---|---:|---:|---|---|---|---:|",
            ]
        )
        for row in stage_init_field_rows:
            lines.append(
                f"| `{_row_text(row, 'workflow_id')}` | `{_row_text(row, 'stage_id')}` | "
                f"{_row_int(row, 'required_init_field_count')} | "
                f"{_row_int(row, 'likely_bulky_field_count')} | `{_row_text(row, 'field_name')}` | "
                f"{_row_text(row, 'field_kind_guess')} | {_row_text(row, 'field_pressure_class')} | "
                f"{_row_int(row, 'selection_count')} |"
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

    semantic_groups = report.semantic_duplicate_invariants[: top or len(report.semantic_duplicate_invariants)]
    if semantic_groups:
        lines.extend(
            [
                "",
                "## Semantic Duplicate Invariants",
                "",
                "| Severity | Category | Occurrences | Non-ref occurrences | Files | Non-ref files | Canonical refs | Suggested action |",
                "|---|---|---:|---:|---:|---:|---|---|",
            ]
        )
        for group in semantic_groups:
            refs = ", ".join(Path(reference).name for reference in group.canonical_references)
            lines.append(
                f"| {group.severity} | `{group.category}` | {group.occurrence_count} | "
                f"{group.non_reference_occurrence_count} | {group.file_count} | {group.non_reference_file_count} | "
                f"{_markdown_table_cell(refs)} | "
                f"{_markdown_table_cell(group.suggested_action)} |"
            )
        example_limit = _semantic_example_limit(top)
        for group in semantic_groups:
            examples = group.examples[:example_limit]
            if not examples:
                continue
            lines.extend(["", f"### `{group.category}` Examples", ""])
            for example in examples:
                lines.append(f"- `{example.path}:{example.line}` - {_markdown_table_cell(example.snippet)}")

    exact_files = _exact_assertion_file_rows(report.exact_assertion_diagnostics, top)
    if exact_files:
        brittle_threshold = _EXACT_ASSERTION_THRESHOLDS["brittle_prose_assertions"]
        lines.extend(
            [
                "",
                "## Prompt-Test Exactness",
                "",
                f"Thresholds: brittle prose warn > {brittle_threshold['warn']}, fail > {brittle_threshold['fail']}.",
                "",
                "| File | Exact | Machine | Public UX | Brittle prose | Brittle % | Severity |",
                "|---|---:|---:|---:|---:|---:|---|",
            ]
        )
        for entry in exact_files:
            brittle_density = 100 * cast(float, entry.get("brittle_prose_density", 0.0))
            lines.append(
                f"| `{entry.get('path', '')}` | {entry.get('exact_assertion_count', 0)} | "
                f"{entry.get('machine_contract_exact_assertions', 0)} | "
                f"{entry.get('public_ux_exact_assertions', 0)} | "
                f"{entry.get('brittle_prose_assertions', 0)} | "
                f"{brittle_density:.1f}% | {entry.get('severity', 'info')} |"
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
            str(item.invalid_frontmatter_example_count),
            str(item.disallowed_return_field_mention_count),
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
        "bad_frontmatter",
        "bad_fields",
        "hard_gates",
        "shell_parse",
        "rigidity",
    )
    lines = _fixed_table_lines(headers, rows)
    runtime_rows = [
        (
            str(row["runtime"]),
            str(row["kind"]),
            str(row["name"]),
            str(row["projected_char_count"]),
            str(row["expanded_char_count"]),
            str(row["char_delta"]),
            str(row["line_delta"]),
            str(row["include_count"]),
            str(row["runtime_note_count"]),
            str(row["shell_fence_count"]),
            str(row["shell_rewrite_count"]),
            str(row["bridge_command_occurrences"]),
        )
        for row in _runtime_top_prompt_rows(report.items, top)
    ]
    runtime_headers = (
        "runtime",
        "kind",
        "name",
        "projected_chars",
        "expanded_chars",
        "char_delta",
        "line_delta",
        "includes",
        "runtime_notes",
        "shell_fences",
        "shell_rewrites",
        "bridge_calls",
    )
    lines.extend(_fixed_table_section_lines("runtime top prompts", runtime_headers, runtime_rows))
    stage_rows = [
        (
            str(row["workflow_id"]),
            str(row["stage_id"]),
            str(row["first_turn_char_count"]),
            str(row["eager_char_count"]),
            str(row["lazy_char_count"]),
            str(row["violation_count"]),
        )
        for row in _stage_top_prompt_rows(report.stage_diagnostics, top)
    ]
    stage_headers = (
        "workflow",
        "stage",
        "first_turn_chars",
        "eager_chars",
        "lazy_chars",
        "violations",
    )
    lines.extend(_fixed_table_section_lines("stage top prompts", stage_headers, stage_rows))
    authority_rows = [
        (
            _row_text(row, "workflow_id"),
            _row_text(row, "stage_id"),
            _row_text(row, "bucket"),
            _row_text(row, "authority"),
            str(_row_int(row, "expanded_char_count")),
            str(_row_int(row, "raw_include_count")),
            str(_row_int(row, "transitive_include_count")),
        )
        for row in _stage_authority_top_prompt_rows(report.stage_diagnostics, top)
    ]
    lines.extend(
        _fixed_table_section_lines(
            "stage authority hotspots",
            ("workflow", "stage", "bucket", "authority", "expanded_chars", "includes", "transitive_includes"),
            authority_rows,
        )
    )
    init_field_rows = [
        (
            _row_text(row, "workflow_id"),
            _row_text(row, "stage_id"),
            str(_row_int(row, "required_init_field_count")),
            str(_row_int(row, "likely_bulky_field_count")),
            _row_text(row, "field_name"),
            _row_text(row, "field_kind_guess"),
            _row_text(row, "field_pressure_class"),
            str(_row_int(row, "selection_count")),
        )
        for row in _stage_init_field_pressure_rows(report.stage_diagnostics, top)
    ]
    lines.extend(
        _fixed_table_section_lines(
            "staged-init field pressure",
            (
                "workflow",
                "stage",
                "required_fields",
                "likely_bulky",
                "field_name",
                "field_kind",
                "pressure",
                "selections",
            ),
            init_field_rows,
        )
    )
    exact_rows = [
        (
            str(row.get("path", "")),
            str(row.get("exact_assertion_count", 0)),
            str(row.get("machine_contract_exact_assertions", 0)),
            str(row.get("public_ux_exact_assertions", 0)),
            str(row.get("brittle_prose_assertions", 0)),
            f"{100 * cast(float, row.get('brittle_prose_density', 0.0)):.1f}",
            str(row.get("severity", "info")),
        )
        for row in _exact_assertion_file_rows(report.exact_assertion_diagnostics, top)
    ]
    exact_headers = ("file", "exact", "machine", "public_ux", "brittle", "brittle_pct", "severity")
    lines.extend(_fixed_table_section_lines("prompt-test exactness", exact_headers, exact_rows))
    outside_top_disallowed = _disallowed_return_field_mentions_outside_top_rows(report, top)
    if outside_top_disallowed:
        lines.extend(("", f"disallowed return field mentions outside top prompt rows: {outside_top_disallowed}"))
    if report.forbidden_child_return_synthesis_mentions:
        lines.extend(
            (
                "",
                "forbidden child return synthesis instructions: "
                f"{len(report.forbidden_child_return_synthesis_mentions)}",
            )
        )
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


def _percent_delta(delta: int, baseline: int) -> float:
    if baseline <= 0:
        return 0.0
    return round(100 * delta / baseline, 6)


def _count_shell_fences(text: str) -> int:
    count = 0
    for fence in _iter_markdown_fences(_body_without_frontmatter(text)):
        language = fence.info.lower().split(None, 1)[0] if fence.info else ""
        if language in DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES:
            count += 1
    return count


def _inspect_visible_schema_examples(
    text: str,
    path: str,
) -> tuple[int, tuple[InvalidGpdReturnExample, ...], tuple[InvalidFrontmatterExample, ...]]:
    body, line_offset = _body_without_frontmatter_with_line_offset(text)
    visible_count = 0
    invalid_return_examples: list[InvalidGpdReturnExample] = []
    invalid_frontmatter_examples: list[InvalidFrontmatterExample] = []

    for fence in _iter_markdown_fences(body):
        language = fence.info.lower().split(None, 1)[0] if fence.info else ""
        invalid_frontmatter = _inspect_verification_frontmatter_example(
            fence,
            path=path,
            line_offset=line_offset,
            language=language,
        )
        is_schema_block = _is_visible_schema_fence(language, fence.body)
        if not is_schema_block and invalid_frontmatter is None:
            continue
        visible_count += 1
        if invalid_frontmatter is not None:
            invalid_frontmatter_examples.append(invalid_frontmatter)
        if invalid_frontmatter is not None or not _contains_visible_gpd_return_example(fence.body):
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
    return visible_count, tuple(invalid_return_examples), tuple(invalid_frontmatter_examples)


def _inspect_verification_frontmatter_example(
    fence: MarkdownFence,
    *,
    path: str,
    line_offset: int,
    language: str,
) -> InvalidFrontmatterExample | None:
    candidate = _verification_frontmatter_candidate_from_fence(fence, language=language)
    if candidate is None:
        return None
    candidate_text, meta = candidate
    fields = _invalid_verification_frontmatter_fields(meta)
    if not fields:
        return None
    errors = _verification_frontmatter_lint_errors(candidate_text, fields)
    if not errors:
        return None
    return InvalidFrontmatterExample(
        path=path,
        start_line=fence.start_line + line_offset,
        end_line=fence.end_line + line_offset,
        schema_name="verification",
        fields=fields,
        errors=errors,
        preview=_preview_fence_body(fence.body),
    )


def _verification_frontmatter_candidate_from_fence(
    fence: MarkdownFence,
    *,
    language: str,
) -> tuple[str, Mapping[str, object]] | None:
    if language in DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES:
        return None
    if language in _MARKDOWN_FRONTMATTER_FENCE_LANGUAGES:
        candidate_text = fence.body.lstrip()
        if not _starts_with_markdown_frontmatter(candidate_text):
            return None
        try:
            meta, _body = extract_frontmatter(candidate_text)
        except FrontmatterParseError:
            return None
        if not _looks_like_verification_frontmatter(meta):
            return None
        return candidate_text, meta
    if language not in {"yaml", "yml"}:
        return None
    try:
        parsed = yaml.safe_load(fence.body)
    except yaml.YAMLError:
        return None
    if not isinstance(parsed, Mapping):
        return None
    meta = {key: value for key, value in parsed.items() if isinstance(key, str)}
    if not _looks_like_verification_frontmatter(meta):
        return None
    return f"---\n{fence.body.rstrip()}\n---\n", meta


def _starts_with_markdown_frontmatter(text: str) -> bool:
    return text.startswith("---\n") or text.startswith("---\r\n")


def _looks_like_verification_frontmatter(meta: Mapping[str, object]) -> bool:
    keys = frozenset(key for key in meta if isinstance(key, str))
    if not keys:
        return False
    unsupported_keys = keys & frozenset(UNSUPPORTED_FRONTMATTER_FIELDS["verification"])
    verification_key_count = len(keys & _VERIFICATION_FRONTMATTER_KEYS)
    if keys & _VERIFICATION_FRONTMATTER_STRONG_KEYS:
        return True
    if "phase" in keys and keys & {"verified", "status", "score", "plan_contract_ref"}:
        return True
    if verification_key_count >= 2:
        return True
    return bool(unsupported_keys and keys & {"phase", "status", "verified", "score"})


def _invalid_verification_frontmatter_fields(meta: Mapping[str, object]) -> tuple[str, ...]:
    unsupported = frozenset(UNSUPPORTED_FRONTMATTER_FIELDS["verification"])
    fields = [field for field in sorted(unsupported) if field in meta]
    if "status" in meta:
        raw_status = meta.get("status")
        if not isinstance(raw_status, str) or raw_status.strip() not in VERIFICATION_REPORT_STATUSES:
            fields.append("status")
    return tuple(dict.fromkeys(fields))


def _verification_frontmatter_lint_errors(candidate_text: str, fields: Sequence[str]) -> tuple[str, ...]:
    field_set = frozenset(fields)
    try:
        validation = validate_frontmatter(candidate_text, "verification")
    except FrontmatterParseError:
        return ()
    return tuple(error for error in validation.errors if _verification_frontmatter_lint_error_field(error) in field_set)


def _verification_frontmatter_lint_error_field(error: str) -> str | None:
    field, separator, _detail = error.partition(":")
    if not separator:
        return None
    return field.strip()


def _scan_return_field_mentions_for_repo(
    repo_root: Path,
    *,
    include_tests: bool,
) -> tuple[PromptReturnFieldMention, ...]:
    mentions: list[PromptReturnFieldMention] = []
    for path in _duplicate_scan_paths(repo_root, include_tests=include_tests):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        mentions.extend(_scan_return_field_mentions(text, _relative_path(path, repo_root)))
    return tuple(
        sorted(
            mentions,
            key=lambda mention: (
                mention.path,
                mention.line,
                mention.field,
                mention.mention_kind,
            ),
        )
    )


def _scan_return_field_mentions(text: str, path: str) -> tuple[PromptReturnFieldMention, ...]:
    body, line_offset = _body_without_frontmatter_with_line_offset(text)
    mentions: list[PromptReturnFieldMention] = []
    mentions.extend(_scan_direct_return_field_references(body, path, line_offset=line_offset))
    mentions.extend(_scan_return_field_declarations(body, path, line_offset=line_offset))
    mentions.extend(_scan_yaml_return_field_keys(body, path, line_offset=line_offset))
    return tuple(_dedupe_return_field_mentions(mentions))


def _scan_forbidden_child_return_synthesis_mentions(
    sources: Sequence[PromptSource],
) -> tuple[ForbiddenChildReturnSynthesisMention, ...]:
    mentions: list[ForbiddenChildReturnSynthesisMention] = []
    for source in sources:
        if source.kind != "workflow":
            continue
        try:
            text = source.absolute_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        body, line_offset = _body_without_frontmatter_with_line_offset(text)
        for line_number, line in _iter_unfenced_lines(body):
            for clause in _child_return_synthesis_clauses(line):
                action = _forbidden_child_return_synthesis_action(clause)
                if action is None:
                    continue
                mentions.append(
                    ForbiddenChildReturnSynthesisMention(
                        path=source.path,
                        line=line_number + line_offset,
                        action=action,
                        polarity="positive",
                        severity="error",
                        snippet=_prompt_line_snippet(clause),
                    )
                )
    return tuple(
        sorted(
            mentions,
            key=lambda mention: (
                mention.path,
                mention.line,
                mention.action,
                mention.snippet,
            ),
        )
    )


def _child_return_synthesis_clauses(line: str) -> tuple[str, ...]:
    normalized = re.sub(r"^\s*(?:[-*+]|\d+[.)]|#+|>)\s*", "", line).strip()
    normalized = normalized.strip("`*_ ")
    normalized = re.sub(r"\s+", " ", normalized)
    if not normalized:
        return ()
    return tuple(
        part.strip(" -") for part in _CHILD_RETURN_SYNTHESIS_CLAUSE_SPLIT_RE.split(normalized) if part.strip(" -")
    ) or (normalized,)


def _forbidden_child_return_synthesis_action(clause: str) -> str | None:
    action_match = _CHILD_RETURN_SYNTHESIS_ACTION_RE.search(clause)
    if action_match is None:
        return None
    if not _CHILD_RETURN_SYNTHESIS_CONTEXT_RE.search(clause):
        return None
    if _CHILD_RETURN_SYNTHESIS_NEGATION_RE.search(clause):
        return None
    if _is_main_context_fallback_return_clause(clause):
        return None
    return action_match.group("action").casefold().replace(" ", "-")


def _is_main_context_fallback_return_clause(clause: str) -> bool:
    folded = clause.casefold()
    if "fallback" not in folded:
        return False
    has_main_context = "main-context" in folded or "main context" in folded
    has_own_return = ("own" in folded or "owns" in folded) and (
        "gpd_return" in folded or "return envelope" in folded or "own return" in folded
    )
    return has_main_context and has_own_return


def _scan_direct_return_field_references(
    body: str,
    path: str,
    *,
    line_offset: int,
) -> tuple[PromptReturnFieldMention, ...]:
    mentions: list[PromptReturnFieldMention] = []
    for line_number, line in enumerate(body.splitlines(), start=1):
        for match in _GPD_RETURN_FIELD_REFERENCE_RE.finditer(line):
            mentions.append(
                _build_return_field_mention(
                    path=path,
                    line=line_number + line_offset,
                    field=match.group(1),
                    mention_kind="direct_reference",
                    snippet=line,
                )
            )
    return tuple(mentions)


def _scan_return_field_declarations(
    body: str,
    path: str,
    *,
    line_offset: int,
) -> tuple[PromptReturnFieldMention, ...]:
    mentions: list[PromptReturnFieldMention] = []
    for line_number, line in _iter_unfenced_lines(body):
        declaration_match = _RETURN_FIELD_DECLARATION_RE.search(line)
        if declaration_match is None:
            continue
        mention_kind: Literal["extended_field_list", "role_field_statement"] = (
            "role_field_statement" if _ROLE_FIELD_DECLARATION_RE.search(line) else "extended_field_list"
        )
        for field in _declared_return_fields(line, declaration_match):
            mentions.append(
                _build_return_field_mention(
                    path=path,
                    line=line_number + line_offset,
                    field=field,
                    mention_kind=mention_kind,
                    snippet=line,
                )
            )
    return tuple(mentions)


def _declared_return_fields(line: str, declaration_match: re.Match[str]) -> tuple[str, ...]:
    field_span = line[declaration_match.end() :]
    backticked = tuple(_BACKTICK_IDENTIFIER_RE.findall(field_span))
    if backticked:
        return tuple(field for field in backticked if field != "gpd_return")

    declaration_text = declaration_match.group(0).casefold()
    has_explicit_list_intro = (
        ":" in field_span or "such as" in declaration_text or re.search(r"\bsuch as\b", field_span, re.IGNORECASE)
    )
    if not has_explicit_list_intro:
        return ()

    such_as_match = re.search(r"\bsuch as\b", field_span, re.IGNORECASE)
    if such_as_match is not None:
        field_span = field_span[such_as_match.end() :]
    colon_index = field_span.find(":")
    if colon_index >= 0:
        field_span = field_span[colon_index + 1 :]
    if "." in field_span:
        field_span = field_span.split(".", 1)[0]
    fields = []
    for field in _IDENTIFIER_RE.findall(field_span):
        if field.casefold() in _FIELD_DECLARATION_STOP_WORDS:
            continue
        fields.append(field)
    return tuple(fields)


def _scan_yaml_return_field_keys(
    body: str,
    path: str,
    *,
    line_offset: int,
) -> tuple[PromptReturnFieldMention, ...]:
    mentions: list[PromptReturnFieldMention] = []
    for fence in _iter_markdown_fences(body):
        language = fence.info.lower().split(None, 1)[0] if fence.info else ""
        if language not in {"yaml", "yml"}:
            continue
        if not _contains_visible_gpd_return_example(fence.body):
            continue
        try:
            parsed = yaml.safe_load(fence.body)
        except yaml.YAMLError:
            continue
        if not isinstance(parsed, Mapping):
            continue
        raw_envelope = parsed.get("gpd_return")
        if not isinstance(raw_envelope, Mapping):
            continue
        for raw_field in raw_envelope:
            if not isinstance(raw_field, str):
                continue
            mentions.append(
                _build_return_field_mention(
                    path=path,
                    line=_yaml_return_field_line(fence.body, raw_field, fence.start_line + line_offset),
                    field=raw_field,
                    mention_kind="yaml_example_key",
                    snippet=f"{raw_field}:",
                )
            )
    return tuple(mentions)


def _yaml_return_field_line(body: str, field: str, fence_start_line: int) -> int:
    in_gpd_return = False
    gpd_return_indent = -1
    child_indent: int | None = None
    for offset, line in enumerate(body.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _YAML_KEY_RE.match(line)
        if match is None:
            continue
        indent = len(match.group("indent").replace("\t", "    "))
        key = match.group("key").strip("'\"")
        if not in_gpd_return:
            if key == "gpd_return":
                in_gpd_return = True
                gpd_return_indent = indent
            continue
        if indent <= gpd_return_indent:
            break
        if child_indent is None:
            child_indent = indent
        if indent == child_indent and key == field:
            return fence_start_line + offset
    return fence_start_line


def _dedupe_return_field_mentions(
    mentions: Sequence[PromptReturnFieldMention],
) -> tuple[PromptReturnFieldMention, ...]:
    seen: set[tuple[str, int, str, str, str]] = set()
    deduped: list[PromptReturnFieldMention] = []
    for mention in mentions:
        key = (
            mention.path,
            mention.line,
            mention.field,
            mention.mention_kind,
            mention.polarity,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(mention)
    return tuple(deduped)


def _build_return_field_mention(
    *,
    path: str,
    line: int,
    field: str,
    mention_kind: Literal[
        "direct_reference",
        "extended_field_list",
        "role_field_statement",
        "yaml_example_key",
    ],
    snippet: str,
) -> PromptReturnFieldMention:
    allowed_source = return_field_allowed_source(field)
    allowed = allowed_source != "unknown"
    polarity: Literal["positive", "negative"] = "negative" if _RETURN_FIELD_NEGATION_RE.search(snippet) else "positive"
    severity: Literal["info", "warn", "error"] = "info"
    if not allowed and polarity == "positive":
        severity = "error"
    return PromptReturnFieldMention(
        path=path,
        line=line,
        field=field,
        mention_kind=mention_kind,
        polarity=polarity,
        allowed=allowed,
        allowed_source=allowed_source,
        severity=severity,
        snippet=_prompt_line_snippet(snippet),
        suggestion=_return_field_suggestion(field) if not allowed else None,
    )


def _return_field_suggestion(field: str) -> str | None:
    matches = difflib.get_close_matches(field, sorted(KNOWN_RETURN_FIELD_NAMES), n=1)
    return matches[0] if matches else None


def _prompt_line_snippet(line: str, max_chars: int = 180) -> str:
    snippet = re.sub(r"\s+", " ", line.strip())
    if len(snippet) <= max_chars:
        return snippet
    return snippet[: max_chars - 3].rstrip() + "..."


def _disallowed_return_field_mentions(
    mentions: Sequence[PromptReturnFieldMention],
) -> tuple[PromptReturnFieldMention, ...]:
    return tuple(mention for mention in mentions if mention.severity == "error")


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
    expanded_text: str,
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
    bridge_command = _projection_bridge_command(runtime_name) if source.kind == "command" else None
    runtime_note_lines = [line for line in projected_text.splitlines() if _RUNTIME_NOTE_RE.search(line)]
    expanded_line_count = _line_count(expanded_text)
    expanded_char_count = len(expanded_text)
    projected_line_count = _line_count(projected_text)
    projected_char_count = len(projected_text)
    line_delta = projected_line_count - expanded_line_count
    char_delta = projected_char_count - expanded_char_count
    return RuntimeProjectionMetric(
        runtime=runtime_name,
        native_include_support=descriptor.native_include_support,
        expanded_line_count=expanded_line_count,
        expanded_char_count=expanded_char_count,
        line_count=projected_line_count,
        char_count=projected_char_count,
        line_delta=line_delta,
        char_delta=char_delta,
        char_delta_percent=_percent_delta(char_delta, expanded_char_count),
        include_count=_count_raw_includes(projected_text),
        runtime_note_count=len(runtime_note_lines),
        runtime_note_chars=sum(len(line) for line in runtime_note_lines),
        shell_fence_count=_count_shell_fences(projected_text),
        shell_rewrite_count=_count_shell_fences_containing(projected_text, bridge_command),
        bridge_command_occurrences=len(_BRIDGE_COMMAND_RE.findall(projected_text)),
    )


def _projection_bridge_command(runtime_name: str) -> str:
    descriptor = get_runtime_descriptor(runtime_name)
    target_dir = projection_target_dir_from_path_prefix(
        DEFAULT_PATH_PREFIX,
        config_dir_name=descriptor.config_dir_name,
    )
    return build_runtime_cli_bridge_command(
        runtime_name,
        target_dir=target_dir,
        config_dir_name=descriptor.config_dir_name,
        is_global=False,
    )


def _count_shell_fences_containing(text: str, needle: str | None) -> int:
    if not needle:
        return 0

    count = 0
    for fence in _iter_markdown_fences(_body_without_frontmatter(text)):
        language = fence.info.lower().split(None, 1)[0] if fence.info else ""
        if language in DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES and needle in fence.body:
            count += 1
    return count


def _build_totals(
    items: Sequence[PromptSurfaceItem],
    *,
    stage_diagnostics: Sequence[StageAwareWorkflowPromptMetric] = (),
    return_field_mentions: Sequence[PromptReturnFieldMention] = (),
    forbidden_child_return_synthesis_mentions: Sequence[ForbiddenChildReturnSynthesisMention] = (),
) -> dict[str, object]:
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
        "invalid_frontmatter_example_count",
        "return_field_mention_count",
        "disallowed_return_field_mention_count",
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
    if return_field_mentions:
        disallowed_mentions = _disallowed_return_field_mentions(return_field_mentions)
        totals["return_field_mention_count"] = len(return_field_mentions)
        totals["disallowed_return_field_mention_count"] = len(disallowed_mentions)
        totals["negative_return_field_mention_count"] = sum(
            1 for mention in return_field_mentions if mention.polarity == "negative"
        )
        totals["allowed_return_field_mention_count"] = sum(1 for mention in return_field_mentions if mention.allowed)
    else:
        totals["negative_return_field_mention_count"] = 0
        totals["allowed_return_field_mention_count"] = 0
    totals["forbidden_child_return_synthesis_mention_count"] = len(forbidden_child_return_synthesis_mentions)
    totals["by_kind"] = by_kind
    totals["runtime_projection"] = _runtime_projection_totals(items)
    totals["stage_diagnostics"] = _stage_diagnostics_totals(stage_diagnostics)
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
                    "expanded_line_count": 0,
                    "expanded_char_count": 0,
                    "line_count": 0,
                    "char_count": 0,
                    "line_delta": 0,
                    "char_delta": 0,
                    "char_delta_percent": 0.0,
                    "include_count": 0,
                    "runtime_note_count": 0,
                    "runtime_note_chars": 0,
                    "shell_fence_count": 0,
                    "shell_rewrite_count": 0,
                    "bridge_command_occurrences": 0,
                },
            )
            runtime_totals["item_count"] = cast(int, runtime_totals["item_count"]) + 1
            runtime_totals["expanded_line_count"] = (
                cast(int, runtime_totals["expanded_line_count"]) + metric.expanded_line_count
            )
            runtime_totals["expanded_char_count"] = (
                cast(int, runtime_totals["expanded_char_count"]) + metric.expanded_char_count
            )
            runtime_totals["line_count"] = cast(int, runtime_totals["line_count"]) + metric.line_count
            runtime_totals["char_count"] = cast(int, runtime_totals["char_count"]) + metric.char_count
            runtime_totals["line_delta"] = cast(int, runtime_totals["line_delta"]) + metric.line_delta
            runtime_totals["char_delta"] = cast(int, runtime_totals["char_delta"]) + metric.char_delta
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
            runtime_totals["shell_rewrite_count"] = (
                cast(int, runtime_totals["shell_rewrite_count"]) + metric.shell_rewrite_count
            )
            runtime_totals["bridge_command_occurrences"] = (
                cast(int, runtime_totals["bridge_command_occurrences"]) + metric.bridge_command_occurrences
            )
    for runtime_totals in totals.values():
        runtime_totals["char_delta_percent"] = _percent_delta(
            cast(int, runtime_totals["char_delta"]),
            cast(int, runtime_totals["expanded_char_count"]),
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


def _semantic_duplicate_invariant_groups(
    repo_root: Path,
    *,
    include_tests: bool,
) -> tuple[SemanticDuplicateGroup, ...]:
    return _scan_semantic_duplicate_invariant_groups(
        _duplicate_scan_paths(repo_root, include_tests=include_tests),
        repo_root=repo_root,
    )


def _status_handling_terms(clause: str) -> tuple[str, ...]:
    return _semantic_status_handling_terms(clause)


def _top_items(items: Sequence[PromptSurfaceItem], top: int | None) -> tuple[PromptSurfaceItem, ...]:
    sorted_items = sorted(
        items,
        key=lambda item: (-item.expanded_char_count, -item.rigidity_index, item.kind, item.name),
    )
    if top is None or top <= 0:
        return tuple(sorted_items)
    return tuple(sorted_items[:top])


def _disallowed_return_field_mentions_outside_top_rows(report: PromptSurfaceReport, top: int | None) -> int:
    top_paths = {item.path for item in _top_items(report.items, top)}
    return sum(1 for mention in report.disallowed_return_field_mentions if mention.path not in top_paths)


def _runtime_top_prompt_rows(
    items: Sequence[PromptSurfaceItem],
    top: int | None,
) -> tuple[dict[str, object], ...]:
    rows_by_runtime: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in items:
        for metric in item.runtime_projection:
            rows_by_runtime[metric.runtime].append(
                {
                    "runtime": metric.runtime,
                    "native_include_support": metric.native_include_support,
                    "kind": item.kind,
                    "name": item.name,
                    "path": item.path,
                    "projected_line_count": metric.line_count,
                    "projected_char_count": metric.char_count,
                    "expanded_line_count": metric.expanded_line_count,
                    "expanded_char_count": metric.expanded_char_count,
                    "line_delta": metric.line_delta,
                    "char_delta": metric.char_delta,
                    "char_delta_percent": metric.char_delta_percent,
                    "include_count": metric.include_count,
                    "runtime_note_count": metric.runtime_note_count,
                    "runtime_note_chars": metric.runtime_note_chars,
                    "shell_fence_count": metric.shell_fence_count,
                    "shell_rewrite_count": metric.shell_rewrite_count,
                    "bridge_command_occurrences": metric.bridge_command_occurrences,
                }
            )

    limit = top if top is not None and top > 0 else None
    rows: list[dict[str, object]] = []
    for runtime in sorted(rows_by_runtime):
        runtime_rows = sorted(
            rows_by_runtime[runtime],
            key=lambda row: (
                -cast(int, row["projected_char_count"]),
                -cast(int, row["expanded_char_count"]),
                cast(str, row["kind"]),
                cast(str, row["name"]),
                cast(str, row["path"]),
            ),
        )
        rows.extend(runtime_rows[:limit])
    return tuple(rows)


def _runtime_top_prompts_to_dict(
    items: Sequence[PromptSurfaceItem],
    top: int | None,
) -> dict[str, list[dict[str, object]]]:
    rows_by_runtime: dict[str, list[dict[str, object]]] = {}
    for row in _runtime_top_prompt_rows(items, top):
        rows_by_runtime.setdefault(cast(str, row["runtime"]), []).append(dict(row))
    return rows_by_runtime


def _runtime_projection_metric_to_dict(metric: RuntimeProjectionMetric) -> dict[str, object]:
    return {
        "runtime": metric.runtime,
        "native_include_support": metric.native_include_support,
        "expanded_line_count": metric.expanded_line_count,
        "expanded_char_count": metric.expanded_char_count,
        "line_count": metric.line_count,
        "char_count": metric.char_count,
        "line_delta": metric.line_delta,
        "char_delta": metric.char_delta,
        "char_delta_percent": metric.char_delta_percent,
        "include_count": metric.include_count,
        "runtime_note_count": metric.runtime_note_count,
        "runtime_note_chars": metric.runtime_note_chars,
        "shell_fence_count": metric.shell_fence_count,
        "shell_rewrite_count": metric.shell_rewrite_count,
        "bridge_command_occurrences": metric.bridge_command_occurrences,
    }


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
        "invalid_frontmatter_example_count": item.invalid_frontmatter_example_count,
        "invalid_frontmatter_examples": [
            _invalid_frontmatter_example_to_dict(example) for example in item.invalid_frontmatter_examples
        ],
        "return_field_mention_count": item.return_field_mention_count,
        "disallowed_return_field_mention_count": item.disallowed_return_field_mention_count,
        "disallowed_return_field_mentions": [
            _return_field_mention_to_dict(mention) for mention in item.disallowed_return_field_mentions
        ],
        "hard_gate_line_count": item.hard_gate_line_count,
        "hard_gate_density": item.hard_gate_density,
        "shell_fence_count": item.shell_fence_count,
        "shell_parsing_line_count": item.shell_parsing_line_count,
        "rigidity_index": item.rigidity_index,
        "runtime_projection": [_runtime_projection_metric_to_dict(metric) for metric in item.runtime_projection],
    }


def _invalid_gpd_return_example_to_dict(example: InvalidGpdReturnExample) -> dict[str, object]:
    return {
        "path": example.path,
        "start_line": example.start_line,
        "end_line": example.end_line,
        "errors": list(example.errors),
        "preview": example.preview,
    }


def _invalid_frontmatter_example_to_dict(example: InvalidFrontmatterExample) -> dict[str, object]:
    return {
        "path": example.path,
        "start_line": example.start_line,
        "end_line": example.end_line,
        "schema_name": example.schema_name,
        "fields": list(example.fields),
        "errors": list(example.errors),
        "preview": example.preview,
    }


def _return_field_mention_to_dict(mention: PromptReturnFieldMention) -> dict[str, object]:
    return {
        "path": mention.path,
        "line": mention.line,
        "field": mention.field,
        "mention_kind": mention.mention_kind,
        "polarity": mention.polarity,
        "allowed": mention.allowed,
        "allowed_source": mention.allowed_source,
        "severity": mention.severity,
        "snippet": mention.snippet,
        "suggestion": mention.suggestion,
    }


def _forbidden_child_return_synthesis_mention_to_dict(
    mention: ForbiddenChildReturnSynthesisMention,
) -> dict[str, object]:
    return {
        "path": mention.path,
        "line": mention.line,
        "action": mention.action,
        "polarity": mention.polarity,
        "severity": mention.severity,
        "snippet": mention.snippet,
    }


def _markdown_table_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("`", "\\`").replace("\n", " ")
