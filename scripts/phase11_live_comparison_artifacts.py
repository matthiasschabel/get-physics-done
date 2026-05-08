"""Render provider-free Phase 11 live-comparison artifacts from sanitized Phase 8 reports."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Final

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parent.parent
    sys.path[:0] = [str(repo_root), str(repo_root / "src")]

from tests.helpers.live_audit_harness.redaction import validate_provider_report_safety
from tests.helpers.live_audit_harness.reporting import (
    PROVIDER_ATTEMPT_REPORT_SCHEMA,
    validate_provider_attempt_report,
)

PHASE11_LIVE_COMPARISON_REPORT: Final[str] = "phase11-live-comparison-report.json"
PHASE11_LIVE_COMPARISON_SUMMARY: Final[str] = "phase11-live-comparison-summary.md"
PHASE11_LIVE_COMPARISON_SCHEMA: Final[str] = "phase11.live-comparison-report.v1"
PROVIDER_SUBPROCESS_ALLOWED_BY_THIS_SCRIPT: Final[bool] = False

_REPORT_HELPER_NAMES: Final[tuple[str, ...]] = (
    "render_phase11_live_comparison_report",
    "render_phase11_comparison_report",
    "render_live_comparison_report",
)
_MARKDOWN_HELPER_NAMES: Final[tuple[str, ...]] = (
    "render_phase11_live_comparison_markdown",
    "render_phase11_comparison_markdown",
    "render_phase11_live_comparison_summary",
    "render_phase11_comparison_summary",
    "render_live_comparison_markdown",
)
_ARTIFACT_HELPER_NAMES: Final[tuple[str, ...]] = (
    "render_phase11_live_comparison_artifacts",
    "render_phase11_comparison_artifacts",
    "render_live_comparison_artifacts",
)
_HELPER_MODULE_NAMES: Final[tuple[str, ...]] = (
    "tests.helpers.live_audit_harness.phase11_comparison",
    "tests.helpers.live_audit_harness.phase11_live_comparison",
    "tests.helpers.live_audit_harness.reporting",
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manual-report", required=True, type=Path, help="Sanitized manual Phase 8 report JSON.")
    parser.add_argument("--nightly-report", required=True, type=Path, help="Sanitized nightly Phase 8 report JSON.")
    parser.add_argument("--out-dir", required=True, type=Path, help="Directory for the two Phase 11 artifacts.")
    args = parser.parse_args(argv)

    try:
        manual_report = _read_sanitized_phase8_report(args.manual_report, label="manual")
        nightly_report = _read_sanitized_phase8_report(args.nightly_report, label="nightly")
        report, markdown = render_comparison_artifacts(
            manual_report=manual_report,
            nightly_report=nightly_report,
        )
        _write_outputs(args.out_dir, report=report, markdown=markdown)
    except Exception as exc:
        print(f"Phase 11 live comparison failed: {exc}", file=sys.stderr)
        return 1

    return 0


def render_comparison_artifacts(
    *,
    manual_report: Mapping[str, object],
    nightly_report: Mapping[str, object],
) -> tuple[dict[str, object], str]:
    """Render Phase 11 JSON and Markdown without launching providers or reading local auth."""

    artifact_helper = _optional_helper(_ARTIFACT_HELPER_NAMES)
    if artifact_helper is not None:
        rendered = _call_pair_helper(
            artifact_helper,
            manual_report=manual_report,
            nightly_report=nightly_report,
        )
        return _normalize_artifact_helper_result(rendered)

    report_helper = _optional_helper(_REPORT_HELPER_NAMES)
    markdown_helper = _optional_helper(_MARKDOWN_HELPER_NAMES)
    if report_helper is not None and markdown_helper is not None:
        report = _call_pair_helper(
            report_helper,
            manual_report=manual_report,
            nightly_report=nightly_report,
        )
        if not isinstance(report, Mapping):
            raise ValueError("Phase 11 comparison report helper must return a mapping")
        markdown = markdown_helper(report)
        if not isinstance(markdown, str):
            raise ValueError("Phase 11 comparison markdown helper must return text")
        return dict(report), _ensure_trailing_newline(markdown)

    report = _fallback_comparison_report(manual_report=manual_report, nightly_report=nightly_report)
    return report, _fallback_comparison_markdown(report)


def _read_sanitized_phase8_report(path: Path, *, label: str) -> dict[str, object]:
    if not path.is_file():
        raise ValueError(f"{label} report does not exist: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"{label} report JSON must contain an object")
    if payload.get("schema") != PROVIDER_ATTEMPT_REPORT_SCHEMA:
        raise ValueError(f"{label} report schema must be exactly {PROVIDER_ATTEMPT_REPORT_SCHEMA!r}")

    validate_provider_report_safety(payload)
    validate_provider_attempt_report(payload)
    return dict(payload)


def _write_outputs(out_dir: Path, *, report: Mapping[str, object], markdown: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / PHASE11_LIVE_COMPARISON_REPORT).write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / PHASE11_LIVE_COMPARISON_SUMMARY).write_text(
        _ensure_trailing_newline(markdown),
        encoding="utf-8",
    )


def _optional_helper(names: Sequence[str]) -> Callable[..., object] | None:
    for module_name in _HELPER_MODULE_NAMES:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name != module_name:
                raise
            continue
        for name in names:
            helper = getattr(module, name, None)
            if callable(helper):
                return helper
    return None


def _call_pair_helper(
    helper: Callable[..., object],
    *,
    manual_report: Mapping[str, object],
    nightly_report: Mapping[str, object],
) -> object:
    try:
        return helper(manual_report=manual_report, nightly_report=nightly_report)
    except TypeError:
        return helper(manual_report, nightly_report)


def _normalize_artifact_helper_result(rendered: object) -> tuple[dict[str, object], str]:
    if not isinstance(rendered, Mapping):
        raise ValueError("Phase 11 comparison artifact helper must return a mapping")

    report = rendered.get("report") or rendered.get("json") or rendered.get("comparison_report")
    markdown = rendered.get("markdown") or rendered.get("summary") or rendered.get("summary_markdown")
    if not isinstance(report, Mapping):
        raise ValueError("Phase 11 comparison artifact helper result is missing report mapping")
    if not isinstance(markdown, str):
        raise ValueError("Phase 11 comparison artifact helper result is missing markdown text")
    return dict(report), _ensure_trailing_newline(markdown)


def _fallback_comparison_report(
    *,
    manual_report: Mapping[str, object],
    nightly_report: Mapping[str, object],
) -> dict[str, object]:
    manual = _source_report_summary(manual_report)
    nightly = _source_report_summary(nightly_report)
    manual_aggregates = _mapping(manual_report.get("aggregates"))
    nightly_aggregates = _mapping(nightly_report.get("aggregates"))
    manual_prompt = _mapping(manual_report.get("prompt_budget"))
    nightly_prompt = _mapping(nightly_report.get("prompt_budget"))

    return {
        "schema": PHASE11_LIVE_COMPARISON_SCHEMA,
        "provider_free": True,
        "provider_subprocess_allowed_by_this_script": PROVIDER_SUBPROCESS_ALLOWED_BY_THIS_SCRIPT,
        "inputs": {
            "manual": manual,
            "nightly": nightly,
        },
        "comparison": {
            "decision_pair": {
                "manual": manual["decision"],
                "nightly": nightly["decision"],
            },
            "provider_attempt_count_delta": _as_int(nightly["provider_attempt_count"])
            - _as_int(manual["provider_attempt_count"]),
            "row_count_delta": _as_int(nightly["row_count"]) - _as_int(manual["row_count"]),
            "finding_count_delta": _as_int(nightly["finding_count"]) - _as_int(manual["finding_count"]),
            "runtime_count_delta": _count_delta(
                _mapping(manual_aggregates.get("runtime_counts")),
                _mapping(nightly_aggregates.get("runtime_counts")),
            ),
            "result_class_count_delta": _count_delta(
                _mapping(manual_aggregates.get("result_class_counts")),
                _mapping(nightly_aggregates.get("result_class_counts")),
            ),
            "total_tokens_estimate_delta": _as_int(nightly_prompt.get("total_tokens_estimate"))
            - _as_int(manual_prompt.get("total_tokens_estimate")),
            "observed_total_tokens_delta": _as_int(nightly_prompt.get("observed_total_tokens"))
            - _as_int(manual_prompt.get("observed_total_tokens")),
        },
        "next_allowed_action": "inspect_phase11_live_comparison_summary",
    }


def _fallback_comparison_markdown(report: Mapping[str, object]) -> str:
    inputs = _mapping(report.get("inputs"))
    comparison = _mapping(report.get("comparison"))
    manual = _mapping(inputs.get("manual"))
    nightly = _mapping(inputs.get("nightly"))
    lines = [
        "# Phase 11 Live Comparison Summary",
        "",
        "## Source Reports",
        "",
        _markdown_table(
            ("Mode", "Attempt", "Batch", "Decision", "Provider attempts", "Rows", "Findings"),
            (
                _summary_row("manual", manual),
                _summary_row("nightly", nightly),
            ),
        ),
        "",
        "## Deltas",
        "",
        _markdown_table(
            ("Metric", "Nightly minus manual"),
            (
                ("Provider attempts", comparison.get("provider_attempt_count_delta", 0)),
                ("Rows", comparison.get("row_count_delta", 0)),
                ("Findings", comparison.get("finding_count_delta", 0)),
                ("Estimated tokens", comparison.get("total_tokens_estimate_delta", 0)),
                ("Observed tokens", comparison.get("observed_total_tokens_delta", 0)),
            ),
        ),
        "",
        "## Runtime Delta",
        "",
        _markdown_table(
            ("Runtime", "Nightly minus manual"),
            sorted(_mapping(comparison.get("runtime_count_delta")).items()),
        ),
        "",
        "## Result-Class Delta",
        "",
        _markdown_table(
            ("Result class", "Nightly minus manual"),
            sorted(_mapping(comparison.get("result_class_count_delta")).items()),
        ),
        "",
    ]
    return "\n".join(lines)


def _source_report_summary(report: Mapping[str, object]) -> dict[str, object]:
    return {
        "attempt_id": _as_string(report.get("attempt_id"), default="unknown"),
        "batch_id": _as_string(report.get("batch_id"), default="unknown"),
        "scenario_set_id": _as_string(report.get("scenario_set_id"), default="unknown"),
        "row_set_sha256": _as_string(report.get("row_set_sha256"), default="unknown"),
        "repo_head": _as_string(report.get("repo_head"), default="unknown"),
        "decision": _as_string(report.get("decision"), default="unknown"),
        "provider_set": _string_sequence(report.get("provider_set")),
        "provider_attempt_count": _as_int(report.get("provider_attempt_count")),
        "row_count": len(_mapping_sequence(report.get("rows"))),
        "finding_count": len(_mapping_sequence(report.get("findings"))),
    }


def _summary_row(label: str, summary: Mapping[str, object]) -> tuple[object, ...]:
    return (
        label,
        summary.get("attempt_id", "unknown"),
        summary.get("batch_id", "unknown"),
        summary.get("decision", "unknown"),
        summary.get("provider_attempt_count", 0),
        summary.get("row_count", 0),
        summary.get("finding_count", 0),
    )


def _count_delta(
    manual_counts: Mapping[str, object],
    nightly_counts: Mapping[str, object],
) -> dict[str, int]:
    keys = set(manual_counts) | set(nightly_counts)
    return {key: _as_int(nightly_counts.get(key)) - _as_int(manual_counts.get(key)) for key in sorted(keys)}


def _markdown_table(headers: Sequence[object], rows: Sequence[Sequence[object]]) -> str:
    header_cells = [str(header) for header in headers]
    lines = [
        "| " + " | ".join(header_cells) + " |",
        "| " + " | ".join("---" for _ in header_cells) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_markdown_cell(cell) for cell in row) + " |")
    return "\n".join(lines)


def _markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _mapping_sequence(value: object) -> tuple[Mapping[str, object], ...]:
    if isinstance(value, Sequence) and not isinstance(value, str):
        return tuple(item for item in value if isinstance(item, Mapping))
    return ()


def _string_sequence(value: object) -> list[str]:
    if isinstance(value, Sequence) and not isinstance(value, str):
        return [str(item) for item in value]
    return []


def _as_int(value: object) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    return 0


def _as_string(value: object, *, default: str = "") -> str:
    if isinstance(value, str) and value.strip():
        return value
    return default


def _ensure_trailing_newline(text: str) -> str:
    return text if text.endswith("\n") else f"{text}\n"


if __name__ == "__main__":
    raise SystemExit(main())
