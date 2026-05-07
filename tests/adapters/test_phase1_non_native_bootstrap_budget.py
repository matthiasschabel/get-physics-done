"""Phase 1 acceptance budgets for non-native runtime bootstrap projections."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from gpd.core import prompt_diagnostics
from gpd.core.prompt_diagnostics import PromptSurfaceItem, PromptSurfaceReport, RuntimeProjectionMetric

REPO_ROOT = Path(__file__).resolve().parents[2]

NATIVE_RUNTIME = "claude-code"
NON_NATIVE_RUNTIMES = ("gemini", "codex", "opencode")
RUNTIME_NAMES = (NATIVE_RUNTIME, *NON_NATIVE_RUNTIMES)

PHASE0_PROJECTED_BASELINE_CHARS = {
    "gemini": 2_905_523,
    "codex": 2_874_832,
    "opencode": 2_837_588,
}
MAX_PROJECTED_TOTAL_RATIO_PERCENT = 70
MAX_NON_NATIVE_COMMAND_CHARS = 60_000
MAX_EXECUTE_PHASE_FIRST_TURN_CHARS = 20_000
MAX_HELP_DEFAULT_CHARS = 10_000


@pytest.fixture(scope="module")
def phase1_report() -> PromptSurfaceReport:
    return prompt_diagnostics.build_prompt_surface_report(
        REPO_ROOT,
        surfaces=("command", "agent"),
        runtime_names=RUNTIME_NAMES,
        include_tests=False,
        include_runtime_projections=True,
    )


def _item(report: PromptSurfaceReport, kind: str, name: str) -> PromptSurfaceItem:
    for item in report.items:
        if item.kind == kind and item.name == name:
            return item
    available = sorted(f"{item.kind}/{item.name}" for item in report.items)
    raise AssertionError(f"missing prompt surface item {kind}/{name}; available={available}")


def _metric(item: PromptSurfaceItem, runtime: str) -> RuntimeProjectionMetric:
    for metric in item.runtime_projection:
        if metric.runtime == runtime:
            return metric
    available = sorted(metric.runtime for metric in item.runtime_projection)
    raise AssertionError(f"missing runtime projection for {item.kind}/{item.name} {runtime}; available={available}")


def _runtime_projection_totals(report: PromptSurfaceReport) -> Mapping[str, object]:
    payload = prompt_diagnostics.report_to_dict(report)
    totals = payload["totals"]
    assert isinstance(totals, Mapping)
    runtime_totals = totals["runtime_projection"]
    assert isinstance(runtime_totals, Mapping)
    return runtime_totals


def test_non_native_command_agent_totals_drop_at_least_30_percent_from_phase0(
    phase1_report: PromptSurfaceReport,
) -> None:
    runtime_totals = _runtime_projection_totals(phase1_report)

    failures: list[str] = []
    for runtime, baseline in PHASE0_PROJECTED_BASELINE_CHARS.items():
        runtime_row = runtime_totals[runtime]
        assert isinstance(runtime_row, Mapping)
        char_count = runtime_row["char_count"]
        assert isinstance(char_count, int)
        ceiling = baseline * MAX_PROJECTED_TOTAL_RATIO_PERCENT // 100
        if char_count > ceiling:
            failures.append(f"{runtime}: {char_count:,} chars > {ceiling:,} ceiling from {baseline:,} baseline")

    assert not failures, "\n".join(failures)


def test_every_non_native_command_projection_stays_under_60k(
    phase1_report: PromptSurfaceReport,
) -> None:
    failures: list[str] = []
    for item in phase1_report.items:
        if item.kind != "command":
            continue
        for runtime in NON_NATIVE_RUNTIMES:
            metric = _metric(item, runtime)
            if metric.char_count >= MAX_NON_NATIVE_COMMAND_CHARS:
                failures.append(f"{runtime} {item.name}: {metric.char_count:,} chars")

    assert not failures, "\n".join(failures)


@pytest.mark.parametrize(
    ("command_name", "max_chars"),
    (
        ("execute-phase", MAX_EXECUTE_PHASE_FIRST_TURN_CHARS),
        ("help", MAX_HELP_DEFAULT_CHARS),
    ),
)
def test_key_non_native_command_bootstrap_payloads_are_compact(
    phase1_report: PromptSurfaceReport,
    command_name: str,
    max_chars: int,
) -> None:
    item = _item(phase1_report, "command", command_name)

    failures: list[str] = []
    for runtime in NON_NATIVE_RUNTIMES:
        metric = _metric(item, runtime)
        if metric.include_count != 0:
            failures.append(f"{runtime} {command_name}: {metric.include_count} projected include lines")
        if metric.char_count >= max_chars:
            failures.append(f"{runtime} {command_name}: {metric.char_count:,} chars >= {max_chars:,}")

    assert not failures, "\n".join(failures)


def test_prompt_surface_report_has_zero_unresolved_includes(
    phase1_report: PromptSurfaceReport,
) -> None:
    payload = prompt_diagnostics.report_to_dict(phase1_report)
    totals = payload["totals"]
    assert isinstance(totals, Mapping)
    assert totals["unresolved_include_count"] == 0

    failures = [
        f"{item.kind}/{item.name}: {item.unresolved_include_count}"
        for item in phase1_report.items
        if item.unresolved_include_count
    ]
    assert not failures, "\n".join(failures)


def test_non_native_command_and_agent_projections_have_no_raw_include_lines(
    phase1_report: PromptSurfaceReport,
) -> None:
    failures: list[str] = []
    for item in phase1_report.items:
        for runtime in NON_NATIVE_RUNTIMES:
            metric = _metric(item, runtime)
            if metric.include_count != 0:
                failures.append(f"{runtime} {item.kind}/{item.name}: {metric.include_count} projected include lines")

    assert not failures, "\n".join(failures)


def test_claude_staged_commands_preserve_native_include_lines(
    phase1_report: PromptSurfaceReport,
) -> None:
    staged_command_names = tuple(metric.command_name for metric in phase1_report.stage_diagnostics)
    assert staged_command_names, "expected production stage diagnostics for staged commands"

    failures: list[str] = []
    for command_name in staged_command_names:
        item = _item(phase1_report, "command", command_name)
        metric = _metric(item, NATIVE_RUNTIME)
        if not metric.native_include_support:
            failures.append(f"{command_name}: Claude metric did not report native include support")
        if item.raw_include_count <= 0:
            failures.append(f"{command_name}: source command has no native include lines to preserve")
        if metric.include_count != item.raw_include_count:
            failures.append(
                f"{command_name}: Claude projected includes {metric.include_count} != raw {item.raw_include_count}"
            )

    assert not failures, "\n".join(failures)
