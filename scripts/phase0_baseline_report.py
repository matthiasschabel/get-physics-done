"""Build a sanitized Phase 0 baseline summary from production diagnostics."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import TextIO, cast

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parent.parent
    sys.path[:0] = [str(repo_root), str(repo_root / "src")]

from gpd.adapters.runtime_catalog import list_runtime_names
from gpd.core.prompt_diagnostics import (
    DEFAULT_SURFACES,
    PromptSurfaceItem,
    PromptSurfaceReport,
    build_prompt_surface_report,
)
from scripts.phase8_live_provider_matrix import PreflightConfig, build_preflight_report
from scripts.repo_graph_contract import GRAPH_SCOPE_LABELS
from tests.helpers.live_audit_harness.phase8_schema import default_phase8_matrix_path, load_phase8_matrix

PHASE0_BASELINE_REPORT_SCHEMA = "phase0.baseline_report.v1"
REPO_ROOT = Path(__file__).resolve().parent.parent

_RUNTIME_TOTAL_FIELDS = (
    "expanded_line_count",
    "expanded_char_count",
    "line_count",
    "char_count",
    "line_delta",
    "char_delta",
    "include_count",
    "runtime_note_count",
    "runtime_note_chars",
    "shell_fence_count",
    "shell_rewrite_count",
    "bridge_command_occurrences",
)


def build_baseline_report(
    repo_root: str | Path = REPO_ROOT,
    *,
    runtime_names: Sequence[str] | None = None,
) -> dict[str, object]:
    """Return a JSON-ready Phase 0 baseline report without raw prompt or provider material."""

    root = Path(repo_root).expanduser().resolve()
    selected_runtimes = tuple(runtime_names) if runtime_names is not None else tuple(list_runtime_names())
    prompt_report = build_prompt_surface_report(
        root,
        surfaces=DEFAULT_SURFACES,
        runtime_names=selected_runtimes,
        include_tests=True,
        include_runtime_projections=True,
    )

    kind_totals = _kind_totals(prompt_report)
    provider_safety = _provider_free_live_audit_safety(root)
    return {
        "schema": PHASE0_BASELINE_REPORT_SCHEMA,
        "schema_id": PHASE0_BASELINE_REPORT_SCHEMA,
        "prompt_diagnostics_schema": prompt_report.schema_version,
        "repo": _repo_summary(root),
        "prompt_totals": _prompt_totals(prompt_report),
        "kind_totals": kind_totals,
        "totals_by_kind": kind_totals,
        "runtime_projection_totals": {
            "command_only": _runtime_projection_totals(prompt_report.items, kinds=("command",)),
            "command_plus_agent": _runtime_projection_totals(prompt_report.items, kinds=("command", "agent")),
        },
        "stage_totals": _stage_totals(prompt_report),
        "duplicate_invariant_counts": _duplicate_invariant_counts(prompt_report),
        "exact_assertion_totals": _exact_assertion_totals(prompt_report),
        "repo_graph_scope_counts": _repo_graph_scope_counts(root),
        "provider_free_live_audit_safety": provider_safety,
        "provider_free_safety_summary": provider_safety,
        "warning_count": len(prompt_report.warnings),
    }


def render_json(report: Mapping[str, object]) -> str:
    """Render the baseline report as stable JSON."""

    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def render_markdown(report: Mapping[str, object]) -> str:
    """Render a compact Markdown summary from a sanitized baseline report."""

    repo = _as_mapping(report.get("repo"))
    lines = [
        "# Phase 0 Baseline Report",
        "",
        f"- Schema: `{report.get('schema', '')}`",
        f"- Prompt diagnostics schema: `{report.get('prompt_diagnostics_schema', '')}`",
        f"- Repo head: `{repo.get('head', 'unavailable')}`",
        f"- Tree status class: `{repo.get('tree_status_class', 'unavailable')}`",
        "",
        "## Prompt Totals",
        "",
        *_metric_table(_as_mapping(report.get("prompt_totals"))),
        "",
        "## Kind Totals",
        "",
        *_nested_metric_table(_as_mapping(report.get("kind_totals")), label_header="Kind"),
        "",
        "## Runtime Projection Totals",
        "",
        "### Command Only",
        "",
        *_nested_metric_table(
            _as_mapping(_as_mapping(report.get("runtime_projection_totals")).get("command_only")),
            label_header="Runtime",
        ),
        "",
        "### Command Plus Agent",
        "",
        *_nested_metric_table(
            _as_mapping(_as_mapping(report.get("runtime_projection_totals")).get("command_plus_agent")),
            label_header="Runtime",
        ),
        "",
        "## Stage Totals",
        "",
        *_metric_table(_as_mapping(report.get("stage_totals"))),
        "",
        "## Duplicate Invariants",
        "",
        *_metric_table(_as_mapping(report.get("duplicate_invariant_counts"))),
        "",
        "## Exact Assertions",
        "",
        *_metric_table(_as_mapping(report.get("exact_assertion_totals"))),
        "",
        "## Repo Graph Scope Counts",
        "",
        *_metric_table(_as_mapping(report.get("repo_graph_scope_counts"))),
        "",
        "## Provider-Free Live-Audit Safety",
        "",
        *_metric_table(_flatten_for_markdown(_as_mapping(report.get("provider_free_live_audit_safety")))),
    ]
    return "\n".join(lines).rstrip() + "\n"


def main(argv: Sequence[str] | None = None, stdout: TextIO | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument(
        "--runtime",
        action="append",
        default=[],
        metavar="RUNTIME[,RUNTIME...]",
        help="Runtime projection set. Defaults to all catalog runtimes.",
    )
    args = parser.parse_args(argv)

    runtime_names = _parse_runtime_args(args.runtime)
    report = build_baseline_report(args.repo_root, runtime_names=runtime_names)
    output = render_markdown(report) if args.format == "markdown" else render_json(report)
    stream = stdout if stdout is not None else sys.stdout
    stream.write(output)
    return 0


def _repo_summary(repo_root: Path) -> dict[str, str]:
    head = _git_output(repo_root, ("rev-parse", "--verify", "HEAD"))
    if head is None:
        return {"head": "unavailable", "tree_status_class": "not_git"}

    status = _git_output(repo_root, ("status", "--porcelain=v1", "--untracked-files=normal"))
    status_class = "unavailable" if status is None else ("dirty" if status else "clean")
    return {"head": head, "tree_status_class": status_class}


def _git_output(repo_root: Path, args: Sequence[str]) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, OSError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _prompt_totals(report: PromptSurfaceReport) -> dict[str, int]:
    return {
        key: value
        for key, value in sorted(report.totals.items())
        if isinstance(value, int) and key not in {"runtime_projection", "stage_diagnostics", "by_kind"}
    }


def _kind_totals(report: PromptSurfaceReport) -> dict[str, dict[str, int]]:
    by_kind = _as_mapping(report.totals.get("by_kind"))
    totals: dict[str, dict[str, int]] = {}
    for kind in DEFAULT_SURFACES:
        totals[kind] = {
            key: value for key, value in sorted(_as_mapping(by_kind.get(kind)).items()) if isinstance(value, int)
        }
    return totals


def _runtime_projection_totals(
    items: Sequence[PromptSurfaceItem],
    *,
    kinds: Iterable[str],
) -> dict[str, dict[str, object]]:
    selected_kinds = frozenset(kinds)
    totals: dict[str, dict[str, object]] = {}
    for item in items:
        if item.kind not in selected_kinds:
            continue
        for metric in item.runtime_projection:
            runtime_totals = totals.setdefault(
                metric.runtime,
                {
                    "native_include_support": metric.native_include_support,
                    "item_count": 0,
                    **dict.fromkeys(_RUNTIME_TOTAL_FIELDS, 0),
                    "char_delta_percent": 0.0,
                },
            )
            runtime_totals["item_count"] = cast(int, runtime_totals["item_count"]) + 1
            for field in _RUNTIME_TOTAL_FIELDS:
                runtime_totals[field] = cast(int, runtime_totals[field]) + cast(int, getattr(metric, field))

    for runtime_totals in totals.values():
        runtime_totals["char_delta_percent"] = _percent_delta(
            cast(int, runtime_totals["char_delta"]),
            cast(int, runtime_totals["expanded_char_count"]),
        )
    return dict(sorted(totals.items()))


def _stage_totals(report: PromptSurfaceReport) -> dict[str, int]:
    return {
        key: value
        for key, value in sorted(_as_mapping(report.totals.get("stage_diagnostics")).items())
        if isinstance(value, int)
    }


def _duplicate_invariant_counts(report: PromptSurfaceReport) -> dict[str, object]:
    literal_severities = Counter(group.severity for group in report.duplicate_invariants)
    semantic_severities = Counter(group.severity for group in report.semantic_duplicate_invariants)
    return {
        "literal_group_count": len(report.duplicate_invariants),
        "literal_occurrence_count": sum(group.occurrence_count for group in report.duplicate_invariants),
        "literal_file_count_sum": sum(group.file_count for group in report.duplicate_invariants),
        "literal_severity_counts": dict(sorted(literal_severities.items())),
        "semantic_group_count": len(report.semantic_duplicate_invariants),
        "semantic_occurrence_count": sum(group.occurrence_count for group in report.semantic_duplicate_invariants),
        "semantic_file_count_sum": sum(group.file_count for group in report.semantic_duplicate_invariants),
        "semantic_non_reference_file_count_sum": sum(
            group.non_reference_file_count for group in report.semantic_duplicate_invariants
        ),
        "semantic_severity_counts": dict(sorted(semantic_severities.items())),
    }


def _exact_assertion_totals(report: PromptSurfaceReport) -> dict[str, object]:
    diagnostics = report.exact_assertion_diagnostics
    totals = _as_mapping(diagnostics.get("totals"))
    return {
        "schema_version": str(diagnostics.get("schema_version", "unknown")),
        **{key: value for key, value in sorted(totals.items()) if isinstance(value, int)},
    }


def _repo_graph_scope_counts(repo_root: Path) -> dict[str, int]:
    contract_path = repo_root / "tests" / "repo_graph_contract.json"
    if not contract_path.is_file():
        return {}
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    scope_counts = _as_mapping(_as_mapping(contract).get("scope_counts"))
    return {label: value for label in GRAPH_SCOPE_LABELS if isinstance((value := scope_counts.get(label)), int)}


def _provider_free_live_audit_safety(repo_root: Path) -> dict[str, object]:
    preflight = build_preflight_report(PreflightConfig(matrix_mode="dry_run"))
    matrix_path = default_phase8_matrix_path(repo_root)
    matrix_summary: dict[str, object] = {"available": False}
    if matrix_path.is_file():
        matrix = load_phase8_matrix(matrix_path)
        launch_policy_counts = Counter(row.launch_policy for row in matrix.rows)
        default_pytest_rows = [row for row in matrix.rows if row.default_pytest]
        live_rows = [row for row in matrix.rows if row.launch_policy in {"manual_live", "nightly_live"}]
        matrix_summary = {
            "available": True,
            "schema": matrix.schema,
            "row_count": len(matrix.rows),
            "launch_policy_counts": dict(sorted(launch_policy_counts.items())),
            "default_pytest_row_count": len(default_pytest_rows),
            "live_row_count": len(live_rows),
            "default_pytest_process_launch_allowed": matrix.default_pytest_policy.provider_subprocess_allowed,
            "default_pytest_network_allowed": matrix.default_pytest_policy.network_allowed,
            "live_rows_in_default_pytest": matrix.default_pytest_policy.live_rows_in_default_pytest,
            "default_pytest_rows_are_provider_free": all(
                not row.provider_subprocess_allowed and not row.network_allowed for row in default_pytest_rows
            ),
        }

    return {
        "class_only": bool(preflight.get("class_only")),
        "dry_run_decision": str(preflight.get("decision", "unknown")),
        "dry_run_launch_performed": bool(preflight.get("provider_launch_performed")),
        "preflight_process_launch_allowed": bool(preflight.get("provider_subprocess_allowed_by_this_script")),
        "runtime_status_counts": {
            key: value
            for key, value in sorted(_as_mapping(preflight.get("runtime_status_counts")).items())
            if isinstance(value, int)
        },
        "sensitive_material_retained": False,
        "process_detail_retained": False,
        "phase8_matrix": matrix_summary,
    }


def _parse_runtime_args(values: Sequence[str]) -> tuple[str, ...] | None:
    if not values or any(value == "all" for value in values):
        return None
    runtimes: list[str] = []
    for value in values:
        runtimes.extend(runtime.strip() for runtime in value.split(",") if runtime.strip())
    return tuple(runtimes)


def _metric_table(metrics: Mapping[str, object]) -> list[str]:
    lines = ["| Metric | Value |", "|---|---:|"]
    for key, value in sorted(metrics.items()):
        if isinstance(value, Mapping):
            continue
        lines.append(f"| `{key}` | {_markdown_value(value)} |")
    return lines


def _nested_metric_table(metrics: Mapping[str, object], *, label_header: str) -> list[str]:
    numeric_keys = sorted(
        {
            key
            for row in metrics.values()
            if isinstance(row, Mapping)
            for key, value in row.items()
            if isinstance(value, int | float | bool)
        }
    )
    if not numeric_keys:
        return [f"| {label_header} |", "|---|"]
    lines = [
        f"| {label_header} | {' | '.join(f'`{key}`' for key in numeric_keys)} |",
        f"|---|{'|'.join('---:' for _key in numeric_keys)}|",
    ]
    for label, row in sorted(metrics.items()):
        row_mapping = _as_mapping(row)
        values = " | ".join(_markdown_value(row_mapping.get(key, "")) for key in numeric_keys)
        lines.append(f"| `{label}` | {values} |")
    return lines


def _flatten_for_markdown(metrics: Mapping[str, object], prefix: str = "") -> dict[str, object]:
    flattened: dict[str, object] = {}
    for key, value in sorted(metrics.items()):
        flattened_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, Mapping):
            flattened.update(_flatten_for_markdown(value, flattened_key))
        elif isinstance(value, int | float | bool | str):
            flattened[flattened_key] = value
    return flattened


def _markdown_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    return f"`{str(value)}`"


def _percent_delta(delta: int, baseline: int) -> float:
    if baseline <= 0:
        return 0.0
    return round(100 * delta / baseline, 6)


def _as_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


if __name__ == "__main__":
    raise SystemExit(main())
