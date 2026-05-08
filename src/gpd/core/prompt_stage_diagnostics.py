"""Stage-aware prompt diagnostics for staged workflow manifests."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, Protocol, cast

from gpd.adapters.install_utils import (
    expand_at_includes,
    parse_at_include_path,
    split_markdown_frontmatter,
)
from gpd.core.workflow_staging import (
    WorkflowStage,
    WorkflowStageManifest,
    known_init_fields_for_workflow,
    load_workflow_stage_manifest_from_path,
)


class StagePromptSource(Protocol):
    kind: str
    name: str
    path: str
    absolute_path: Path
    repo_root: Path
    src_root: Path


class RuntimeProjectionLike(Protocol):
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


class StageCommandMetric(Protocol):
    kind: str
    name: str
    raw_include_count: int
    expanded_line_count: int
    expanded_char_count: int
    runtime_projection: tuple[RuntimeProjectionLike, ...]


@dataclass(frozen=True, slots=True)
class AuthorityPromptMetric:
    authority: str
    path: str
    raw_line_count: int
    raw_char_count: int
    raw_include_count: int
    expanded_line_count: int
    expanded_char_count: int
    transitive_include_authorities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MustNotEagerLoadViolation:
    workflow_id: str
    stage_id: str
    authority: str
    violation_source: Literal[
        "manifest_overlap",
        "first_turn_direct_include",
        "first_turn_transitive_include",
        "stage_eager_transitive_include",
    ]
    eager_via: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WorkflowStagePromptMetric:
    workflow_id: str
    stage_id: str
    order: int
    eager_authorities: tuple[str, ...]
    eager_authority_metrics: tuple[AuthorityPromptMetric, ...]
    eager_line_count: int
    eager_char_count: int
    lazy_authorities: tuple[str, ...]
    lazy_authority_metrics: tuple[AuthorityPromptMetric, ...]
    lazy_line_count: int
    lazy_char_count: int
    must_not_eager_load_violations: tuple[MustNotEagerLoadViolation, ...]


@dataclass(frozen=True, slots=True)
class StageAwareWorkflowPromptMetric:
    workflow_id: str
    command_name: str
    command_path: str
    manifest_path: str
    stage_count: int
    first_turn_line_count: int
    first_turn_char_count: int
    first_turn_raw_include_count: int
    runtime_projection: tuple[RuntimeProjectionLike, ...]
    stages: tuple[WorkflowStagePromptMetric, ...]
    violation_count: int
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _IncludeTrace:
    authorities: tuple[str, ...]
    chains_by_authority: Mapping[str, tuple[tuple[str, ...], ...]]


def build_stage_diagnostics(
    sources: Sequence[StagePromptSource],
    items: Sequence[StageCommandMetric],
    *,
    report_warnings: list[str],
    path_prefix: str,
) -> tuple[StageAwareWorkflowPromptMetric, ...]:
    items_by_command = {(item.kind, item.name): item for item in items if item.kind == "command"}
    diagnostics: list[StageAwareWorkflowPromptMetric] = []
    for source in sources:
        if source.kind != "command":
            continue
        command_item = items_by_command.get((source.kind, source.name))
        if command_item is None:
            continue
        manifest_path = _stage_manifest_path_for_command(source)
        if not manifest_path.is_file():
            continue
        warning_count = len(report_warnings)
        metric = _build_stage_diagnostic_for_command(
            source,
            command_item,
            manifest_path,
            report_warnings=report_warnings,
            path_prefix=path_prefix,
        )
        if metric is None:
            if len(report_warnings) == warning_count:
                report_warnings.append(
                    f"could not load stage diagnostics for {source.name}: "
                    f"{_relative_path(manifest_path, source.repo_root)}"
                )
            continue
        diagnostics.append(metric)
    return tuple(sorted(diagnostics, key=lambda metric: (metric.workflow_id, metric.command_name)))


def stage_diagnostics_totals(stage_diagnostics: Sequence[StageAwareWorkflowPromptMetric]) -> dict[str, int]:
    stages = [stage for workflow in stage_diagnostics for stage in workflow.stages]
    return {
        "workflow_count": len(stage_diagnostics),
        "stage_count": len(stages),
        "first_turn_char_count": sum(workflow.first_turn_char_count for workflow in stage_diagnostics),
        "first_turn_line_count": sum(workflow.first_turn_line_count for workflow in stage_diagnostics),
        "eager_char_count": sum(stage.eager_char_count for stage in stages),
        "eager_line_count": sum(stage.eager_line_count for stage in stages),
        "lazy_char_count": sum(stage.lazy_char_count for stage in stages),
        "lazy_line_count": sum(stage.lazy_line_count for stage in stages),
        "must_not_eager_load_violation_count": sum(len(stage.must_not_eager_load_violations) for stage in stages),
    }


def top_stage_diagnostics(
    stage_diagnostics: Sequence[StageAwareWorkflowPromptMetric],
    top: int | None,
) -> tuple[StageAwareWorkflowPromptMetric, ...]:
    limit = _top_limit(top)
    if limit is None:
        return tuple(stage_diagnostics)
    return tuple(
        sorted(
            stage_diagnostics,
            key=lambda metric: (
                -sum(stage.eager_char_count for stage in metric.stages),
                -sum(stage.lazy_char_count for stage in metric.stages),
                -metric.first_turn_char_count,
                -metric.violation_count,
                metric.workflow_id,
                metric.command_name,
            ),
        )[:limit]
    )


def stage_top_prompt_rows(
    stage_diagnostics: Sequence[StageAwareWorkflowPromptMetric],
    top: int | None,
) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for workflow in stage_diagnostics:
        for stage in workflow.stages:
            rows.append(
                {
                    "workflow_id": workflow.workflow_id,
                    "command_name": workflow.command_name,
                    "stage_id": stage.stage_id,
                    "first_turn_char_count": workflow.first_turn_char_count,
                    "first_turn_line_count": workflow.first_turn_line_count,
                    "eager_char_count": stage.eager_char_count,
                    "eager_line_count": stage.eager_line_count,
                    "lazy_char_count": stage.lazy_char_count,
                    "lazy_line_count": stage.lazy_line_count,
                    "violation_count": len(stage.must_not_eager_load_violations),
                }
            )
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            -cast(int, row["eager_char_count"]),
            -cast(int, row["lazy_char_count"]),
            -cast(int, row["violation_count"]),
            cast(str, row["workflow_id"]),
            cast(str, row["stage_id"]),
        ),
    )
    limit = _top_limit(top)
    return tuple(sorted_rows[:limit])


def stage_diagnostic_to_dict(metric: StageAwareWorkflowPromptMetric) -> dict[str, object]:
    return {
        "workflow_id": metric.workflow_id,
        "command_name": metric.command_name,
        "command_path": metric.command_path,
        "manifest_path": metric.manifest_path,
        "stage_count": metric.stage_count,
        "first_turn_line_count": metric.first_turn_line_count,
        "first_turn_char_count": metric.first_turn_char_count,
        "first_turn_raw_include_count": metric.first_turn_raw_include_count,
        "runtime_projection": [
            _runtime_projection_metric_to_dict(runtime_metric) for runtime_metric in metric.runtime_projection
        ],
        "stages": [_workflow_stage_metric_to_dict(stage) for stage in metric.stages],
        "violation_count": metric.violation_count,
        "warnings": list(metric.warnings),
    }


def _stage_manifest_path_for_command(source: StagePromptSource) -> Path:
    return source.src_root / "specs" / "workflows" / f"{source.name}-stage-manifest.json"


def _build_stage_diagnostic_for_command(
    source: StagePromptSource,
    command_item: StageCommandMetric,
    manifest_path: Path,
    *,
    report_warnings: list[str],
    path_prefix: str,
) -> StageAwareWorkflowPromptMetric | None:
    warnings: list[str] = []
    manifest = _load_stage_manifest_for_source(source, manifest_path, warnings)
    if manifest is None:
        report_warnings.extend(f"could not load stage diagnostics for {source.name}: {warning}" for warning in warnings)
        return None

    command_text = source.absolute_path.read_text(encoding="utf-8")
    first_turn_trace = _include_trace_from_text(
        command_text,
        source.src_root,
        active_authorities=frozenset(),
    )
    stages = tuple(
        _measure_workflow_stage(
            source=source,
            manifest=manifest,
            stage=stage,
            first_turn_trace=first_turn_trace,
            path_prefix=path_prefix,
        )
        for stage in sorted(manifest.stages, key=lambda candidate: candidate.order)
    )
    violation_count = sum(len(stage.must_not_eager_load_violations) for stage in stages)
    return StageAwareWorkflowPromptMetric(
        workflow_id=manifest.workflow_id,
        command_name=source.name,
        command_path=source.path,
        manifest_path=_relative_path(manifest_path, source.repo_root),
        stage_count=len(stages),
        first_turn_line_count=command_item.expanded_line_count,
        first_turn_char_count=command_item.expanded_char_count,
        first_turn_raw_include_count=command_item.raw_include_count,
        runtime_projection=command_item.runtime_projection,
        stages=stages,
        violation_count=violation_count,
        warnings=tuple(warnings),
    )


def _load_stage_manifest_for_source(
    source: StagePromptSource,
    manifest_path: Path,
    warnings: list[str],
) -> WorkflowStageManifest | None:
    try:
        return load_workflow_stage_manifest_from_path(
            manifest_path,
            expected_workflow_id=source.name,
            known_init_fields=known_init_fields_for_workflow(source.name),
            specs_root=source.src_root / "specs",
        )
    except ValueError as exc:
        warnings.append(str(exc))
        return None


def _measure_workflow_stage(
    *,
    source: StagePromptSource,
    manifest: WorkflowStageManifest,
    stage: WorkflowStage,
    first_turn_trace: _IncludeTrace,
    path_prefix: str,
) -> WorkflowStagePromptMetric:
    eager_authorities = stage.eager_authorities()
    lazy_authorities = stage.must_not_eager_load
    eager_metrics = tuple(_measure_authority(source, authority, path_prefix=path_prefix) for authority in eager_authorities)
    lazy_metrics = tuple(_measure_authority(source, authority, path_prefix=path_prefix) for authority in lazy_authorities)
    violations = _must_not_eager_load_violations(
        source=source,
        workflow_id=manifest.workflow_id,
        stage=stage,
        eager_authorities=eager_authorities,
        first_turn_trace=first_turn_trace,
    )
    return WorkflowStagePromptMetric(
        workflow_id=manifest.workflow_id,
        stage_id=stage.id,
        order=stage.order,
        eager_authorities=eager_authorities,
        eager_authority_metrics=eager_metrics,
        eager_line_count=sum(metric.expanded_line_count for metric in eager_metrics),
        eager_char_count=sum(metric.expanded_char_count for metric in eager_metrics),
        lazy_authorities=lazy_authorities,
        lazy_authority_metrics=lazy_metrics,
        lazy_line_count=sum(metric.expanded_line_count for metric in lazy_metrics),
        lazy_char_count=sum(metric.expanded_char_count for metric in lazy_metrics),
        must_not_eager_load_violations=violations,
    )


def _measure_authority(
    source: StagePromptSource,
    authority: str,
    *,
    path_prefix: str,
) -> AuthorityPromptMetric:
    path = _authority_path(source.src_root, authority)
    raw_text = path.read_text(encoding="utf-8")
    expanded_text = expand_at_includes(raw_text, source.src_root, path_prefix)
    include_trace = _include_trace_from_text(
        raw_text,
        source.src_root,
        active_authorities=frozenset({authority}),
    )
    return AuthorityPromptMetric(
        authority=authority,
        path=_relative_path(path, source.repo_root),
        raw_line_count=_line_count(raw_text),
        raw_char_count=len(raw_text),
        raw_include_count=_count_raw_includes(raw_text),
        expanded_line_count=_line_count(expanded_text),
        expanded_char_count=len(expanded_text),
        transitive_include_authorities=include_trace.authorities,
    )


def _must_not_eager_load_violations(
    *,
    source: StagePromptSource,
    workflow_id: str,
    stage: WorkflowStage,
    eager_authorities: tuple[str, ...],
    first_turn_trace: _IncludeTrace,
) -> tuple[MustNotEagerLoadViolation, ...]:
    lazy_authorities = set(stage.must_not_eager_load)
    eager_authority_set = set(eager_authorities)
    violations: list[MustNotEagerLoadViolation] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()

    def add(authority: str, violation_source: str, eager_via: tuple[str, ...]) -> None:
        key = (authority, violation_source, eager_via)
        if key in seen:
            return
        seen.add(key)
        violations.append(_must_not_violation(workflow_id, stage.id, authority, violation_source, eager_via=eager_via))

    for authority in sorted(lazy_authorities.intersection(eager_authority_set)):
        add(authority, "manifest_overlap", (authority,))

    for authority in sorted(lazy_authorities):
        for chain in first_turn_trace.chains_by_authority.get(authority, ()):
            if len(chain) == 1:
                add(authority, "first_turn_direct_include", chain)
            elif len(chain) > 1:
                add(authority, "first_turn_transitive_include", chain[:-1])

    for eager_authority in eager_authorities:
        eager_path = _authority_path(source.src_root, eager_authority)
        if not eager_path.is_file():
            continue
        trace = _include_trace_from_path(
            eager_path,
            source.src_root,
            authority=eager_authority,
        )
        for authority in sorted(lazy_authorities):
            for chain in trace.chains_by_authority.get(authority, ()):
                add(authority, "stage_eager_transitive_include", (eager_authority, *chain[:-1]))

    return tuple(violations)


def _must_not_violation(
    workflow_id: str,
    stage_id: str,
    authority: str,
    violation_source: Literal[
        "manifest_overlap",
        "first_turn_direct_include",
        "first_turn_transitive_include",
        "stage_eager_transitive_include",
    ]
    | str,
    *,
    eager_via: tuple[str, ...],
) -> MustNotEagerLoadViolation:
    return MustNotEagerLoadViolation(
        workflow_id=workflow_id,
        stage_id=stage_id,
        authority=authority,
        violation_source=cast(
            Literal[
                "manifest_overlap",
                "first_turn_direct_include",
                "first_turn_transitive_include",
                "stage_eager_transitive_include",
            ],
            violation_source,
        ),
        eager_via=eager_via,
    )


def _include_trace_from_path(path: Path, src_root: Path, *, authority: str) -> _IncludeTrace:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return _IncludeTrace(authorities=(), chains_by_authority={})
    return _include_trace_from_text(
        raw_text,
        src_root,
        active_authorities=frozenset({authority}),
    )


def _include_trace_from_text(
    text: str,
    src_root: Path,
    *,
    active_authorities: frozenset[str],
) -> _IncludeTrace:
    ordered: list[str] = []
    chains_by_authority: dict[str, list[tuple[str, ...]]] = defaultdict(list)

    def add_chain(authority: str, chain: tuple[str, ...]) -> None:
        if authority not in ordered:
            ordered.append(authority)
        if chain not in chains_by_authority[authority]:
            chains_by_authority[authority].append(chain)

    def visit(current_text: str, active: frozenset[str], prefix: tuple[str, ...]) -> None:
        for _line_number, line in _iter_unfenced_lines(_body_without_frontmatter(current_text)):
            include_path = parse_at_include_path(line.strip())
            authority = _authority_id_from_include_path(include_path)
            if authority is None:
                continue
            chain = (*prefix, authority)
            add_chain(authority, chain)
            if authority in active:
                continue
            authority_path = _authority_path(src_root, authority)
            if not authority_path.is_file():
                continue
            try:
                included_text = authority_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            visit(included_text, active | {authority}, chain)

    visit(text, active_authorities, ())
    return _IncludeTrace(
        authorities=tuple(ordered),
        chains_by_authority={authority: tuple(chains) for authority, chains in chains_by_authority.items()},
    )


def _authority_id_from_include_path(include_path: str | None) -> str | None:
    if include_path is None:
        return None
    for prefix in ("{GPD_INSTALL_DIR}/", "get-physics-done/"):
        if include_path.startswith(prefix):
            candidate = include_path[len(prefix) :]
            return _normalize_authority_id_or_none(candidate)
    return _normalize_authority_id_or_none(include_path)


def _normalize_authority_id_or_none(candidate: str) -> str | None:
    try:
        return _normalize_authority_id(candidate, label="include")
    except ValueError:
        return None


def _normalize_authority_id(raw: str, *, label: str) -> str:
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{label} must be a normalized relative POSIX path")
    normalized = path.as_posix()
    if normalized != raw:
        raise ValueError(f"{label} must be a normalized relative POSIX path")
    if path.suffix != ".md":
        raise ValueError(f"{label} must reference a markdown file")
    if not normalized.startswith(("workflows/", "references/", "templates/")):
        raise ValueError(f"{label} must reference workflows/, references/, or templates/")
    return normalized


def _authority_path(src_root: Path, authority: str) -> Path:
    return src_root / "specs" / authority


def _workflow_stage_metric_to_dict(metric: WorkflowStagePromptMetric) -> dict[str, object]:
    return {
        "workflow_id": metric.workflow_id,
        "stage_id": metric.stage_id,
        "order": metric.order,
        "eager_authorities": list(metric.eager_authorities),
        "eager_authority_metrics": [
            _authority_prompt_metric_to_dict(authority_metric) for authority_metric in metric.eager_authority_metrics
        ],
        "eager_line_count": metric.eager_line_count,
        "eager_char_count": metric.eager_char_count,
        "lazy_authorities": list(metric.lazy_authorities),
        "lazy_authority_metrics": [
            _authority_prompt_metric_to_dict(authority_metric) for authority_metric in metric.lazy_authority_metrics
        ],
        "lazy_line_count": metric.lazy_line_count,
        "lazy_char_count": metric.lazy_char_count,
        "must_not_eager_load_violations": [
            _must_not_eager_load_violation_to_dict(violation) for violation in metric.must_not_eager_load_violations
        ],
    }


def _authority_prompt_metric_to_dict(metric: AuthorityPromptMetric) -> dict[str, object]:
    return {
        "authority": metric.authority,
        "path": metric.path,
        "raw_line_count": metric.raw_line_count,
        "raw_char_count": metric.raw_char_count,
        "raw_include_count": metric.raw_include_count,
        "expanded_line_count": metric.expanded_line_count,
        "expanded_char_count": metric.expanded_char_count,
        "transitive_include_authorities": list(metric.transitive_include_authorities),
    }


def _must_not_eager_load_violation_to_dict(violation: MustNotEagerLoadViolation) -> dict[str, object]:
    return {
        "workflow_id": violation.workflow_id,
        "stage_id": violation.stage_id,
        "authority": violation.authority,
        "violation_source": violation.violation_source,
        "eager_via": list(violation.eager_via),
    }


def _runtime_projection_metric_to_dict(metric: RuntimeProjectionLike) -> dict[str, object]:
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


def _body_without_frontmatter(text: str) -> str:
    _preamble, _frontmatter, _separator, body = split_markdown_frontmatter(text)
    return body


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


def _markdown_fence_marker(stripped_line: str) -> str | None:
    if stripped_line.startswith("```"):
        return "```"
    if stripped_line.startswith("~~~"):
        return "~~~"
    return None


def _count_raw_includes(text: str) -> int:
    return sum(1 for _line_number, line in _iter_unfenced_lines(text) if parse_at_include_path(line.strip()))


def _line_count(text: str) -> int:
    return len(text.splitlines())


def _relative_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _top_limit(top: int | None) -> int | None:
    if top is None or top <= 0:
        return None
    return top
