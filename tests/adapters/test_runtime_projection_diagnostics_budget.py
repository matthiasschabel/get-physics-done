"""Guardrails for non-native runtime projection diagnostics."""

from __future__ import annotations

from pathlib import Path

from gpd.core import prompt_diagnostics
from tests.adapters.projection_budget_support import (
    NON_NATIVE_RUNTIME_PROJECTION_TARGETS,
    SELECTED_AGENT_PROJECTION_BUDGETS,
    STAGED_INIT_COMMAND_PROJECTION_BUDGETS,
    STAGED_PROJECTED_COMMAND_CHAR_BUDGET,
    TARGET_AGENT_COMBINED_NON_NATIVE_PROJECTION_CHAR_BUDGET,
    TARGET_AGENT_PROJECTION_BUDGETS,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
NON_NATIVE_RUNTIMES = ("codex", "gemini", "opencode")
NORMALIZED_RUNTIME_BRIDGE_MARKER = "<runtime-bridge>"
KNOWN_PROJECTION_HOTSPOTS = {
    "execute-phase",
    "gpd-executor",
    "gpd-planner",
    "gpd-roadmapper",
    "new-project",
    "write-paper",
}


def _non_negative_int(row: dict[str, object], key: str) -> int:
    value = row.get(key)
    assert isinstance(value, int), f"{key} should be an int in {row!r}"
    assert value >= 0, f"{key} should be non-negative in {row!r}"
    return value


def _normalized_runtime_projection_char_count(metric: prompt_diagnostics.RuntimeProjectionMetric) -> int:
    bridge_occurrences = metric.bridge_command_occurrences
    if bridge_occurrences == 0:
        return metric.char_count
    bridge_command = prompt_diagnostics._projection_bridge_command(metric.runtime)
    return metric.char_count - (len(bridge_command) - len(NORMALIZED_RUNTIME_BRIDGE_MARKER)) * bridge_occurrences


def test_report_to_dict_exposes_non_native_runtime_top_prompt_hotspots() -> None:
    report = prompt_diagnostics.build_prompt_surface_report(
        REPO_ROOT,
        surfaces=("command", "agent"),
        runtime_names=NON_NATIVE_RUNTIMES,
        include_tests=False,
        include_runtime_projections=True,
    )

    payload = prompt_diagnostics.report_to_dict(report)

    assert "runtime_top_prompts" in payload
    runtime_top_prompts = payload["runtime_top_prompts"]
    assert isinstance(runtime_top_prompts, dict)
    assert set(NON_NATIVE_RUNTIMES) <= set(runtime_top_prompts)

    hotspot_names: set[str] = set()
    saw_shell_rewrite_pressure = False
    for runtime in NON_NATIVE_RUNTIMES:
        rows = runtime_top_prompts[runtime]
        assert isinstance(rows, list)
        assert rows, f"{runtime} should expose at least one runtime top prompt row"

        projected_char_counts: list[int] = []
        for row in rows:
            assert isinstance(row, dict)
            assert row["runtime"] == runtime
            assert row["native_include_support"] is False
            assert row["kind"] in {"command", "agent"}
            assert isinstance(row["name"], str)
            assert row["name"]
            assert isinstance(row["path"], str)
            assert row["path"].endswith(".md")

            projected_char_counts.append(_non_negative_int(row, "projected_char_count"))
            _non_negative_int(row, "projected_line_count")
            _non_negative_int(row, "expanded_char_count")
            _non_negative_int(row, "expanded_line_count")
            _non_negative_int(row, "include_count")
            _non_negative_int(row, "runtime_note_count")
            shell_rewrite_count = _non_negative_int(row, "shell_rewrite_count")

            saw_shell_rewrite_pressure = saw_shell_rewrite_pressure or shell_rewrite_count > 0
            if row["name"] in KNOWN_PROJECTION_HOTSPOTS:
                hotspot_names.add(row["name"])

        assert projected_char_counts == sorted(projected_char_counts, reverse=True)

    assert hotspot_names, "runtime_top_prompts should surface at least one known prompt-size hotspot"
    assert saw_shell_rewrite_pressure, "runtime_top_prompts should expose nonzero shell rewrite pressure"


def test_target_command_runtime_projection_diagnostics_stay_under_baseline_budgets() -> None:
    runtime_names = ("claude-code", *NON_NATIVE_RUNTIMES)
    report = prompt_diagnostics.build_prompt_surface_report(
        REPO_ROOT,
        surfaces=("command",),
        runtime_names=runtime_names,
        include_tests=False,
        include_runtime_projections=True,
    )

    items_by_name = {item.name: item for item in report.items if item.kind == "command"}
    missing = sorted(set(STAGED_INIT_COMMAND_PROJECTION_BUDGETS) - set(items_by_name))
    assert missing == []

    for command_name, budget_by_runtime in STAGED_INIT_COMMAND_PROJECTION_BUDGETS.items():
        item = items_by_name[command_name]
        metrics_by_runtime = {metric.runtime: metric for metric in item.runtime_projection}
        assert set(runtime_names) <= set(metrics_by_runtime)

        for runtime, budget in budget_by_runtime.items():
            metric = metrics_by_runtime[runtime]
            assert _normalized_runtime_projection_char_count(metric) <= budget
            assert metric.char_count <= STAGED_PROJECTED_COMMAND_CHAR_BUDGET
            if runtime in NON_NATIVE_RUNTIMES:
                assert metric.bridge_command_occurrences > 0
                assert metric.shell_rewrite_count > 0


def test_selected_agent_runtime_projection_diagnostics_stay_under_baseline_budgets() -> None:
    report = prompt_diagnostics.build_prompt_surface_report(
        REPO_ROOT,
        surfaces=("agent",),
        runtime_names=NON_NATIVE_RUNTIME_PROJECTION_TARGETS,
        include_tests=False,
        include_runtime_projections=True,
    )

    items_by_name = {item.name: item for item in report.items if item.kind == "agent"}
    missing = sorted(set(SELECTED_AGENT_PROJECTION_BUDGETS) - set(items_by_name))
    assert missing == []

    target_agent_max_chars: dict[str, int] = {}
    for agent_name, budget in SELECTED_AGENT_PROJECTION_BUDGETS.items():
        item = items_by_name[agent_name]
        metrics_by_runtime = {metric.runtime: metric for metric in item.runtime_projection}
        assert set(NON_NATIVE_RUNTIME_PROJECTION_TARGETS) <= set(metrics_by_runtime)

        max_chars = 0
        for runtime in NON_NATIVE_RUNTIME_PROJECTION_TARGETS:
            metric = metrics_by_runtime[runtime]
            assert metric.native_include_support is False
            assert metric.line_count <= budget["lines"]
            assert metric.char_count <= budget["chars"]
            assert metric.runtime_note_count == 0
            max_chars = max(max_chars, metric.char_count)

        if agent_name in TARGET_AGENT_PROJECTION_BUDGETS:
            target_agent_max_chars[agent_name] = max_chars

    assert (
        sum(target_agent_max_chars.values())
        <= TARGET_AGENT_COMBINED_NON_NATIVE_PROJECTION_CHAR_BUDGET
    )
