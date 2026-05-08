"""Phase 0 runtime projection baseline guardrails."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from gpd.adapters.runtime_catalog import RuntimeDescriptor, iter_runtime_descriptors
from gpd.core import prompt_diagnostics
from gpd.core.prompt_diagnostics import PromptSurfaceReport
from tests.helpers.live_audit_harness.live_capabilities import (
    live_capability_by_runtime,
    ready_runtime_ids,
    render_live_capability_registry,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

RUNTIME_TOTAL_NUMERIC_KEYS = frozenset(
    {
        "item_count",
        "expanded_line_count",
        "expanded_char_count",
        "line_count",
        "char_count",
        "line_delta",
        "char_delta",
        "char_delta_percent",
        "include_count",
        "runtime_note_count",
        "runtime_note_chars",
        "shell_fence_count",
        "shell_rewrite_count",
        "bridge_command_occurrences",
    }
)
RUNTIME_TOTAL_ALLOWED_KEYS = RUNTIME_TOTAL_NUMERIC_KEYS | {"native_include_support"}
RUNTIME_TOTAL_COUNT_KEYS = RUNTIME_TOTAL_NUMERIC_KEYS - {"line_delta", "char_delta", "char_delta_percent"}


@pytest.fixture(scope="module")
def runtime_descriptors() -> tuple[RuntimeDescriptor, ...]:
    return tuple(iter_runtime_descriptors())


@pytest.fixture(scope="module")
def runtime_names(runtime_descriptors: tuple[RuntimeDescriptor, ...]) -> tuple[str, ...]:
    return tuple(descriptor.runtime_name for descriptor in runtime_descriptors)


@pytest.fixture(scope="module")
def command_projection_report(runtime_names: tuple[str, ...]) -> PromptSurfaceReport:
    return prompt_diagnostics.build_prompt_surface_report(
        REPO_ROOT,
        surfaces=("command",),
        runtime_names=runtime_names,
        include_tests=False,
        include_runtime_projections=True,
    )


@pytest.fixture(scope="module")
def command_agent_projection_report(runtime_names: tuple[str, ...]) -> PromptSurfaceReport:
    return prompt_diagnostics.build_prompt_surface_report(
        REPO_ROOT,
        surfaces=("command", "agent"),
        runtime_names=runtime_names,
        include_tests=False,
        include_runtime_projections=True,
    )


def _payload(report: PromptSurfaceReport) -> Mapping[str, object]:
    return prompt_diagnostics.report_to_dict(report, top=1)


def _runtime_totals(report: PromptSurfaceReport) -> Mapping[str, Mapping[str, object]]:
    payload = _payload(report)
    totals = payload["totals"]
    assert isinstance(totals, Mapping)
    runtime_totals = totals["runtime_projection"]
    assert isinstance(runtime_totals, Mapping)

    rows: dict[str, Mapping[str, object]] = {}
    for runtime, row in runtime_totals.items():
        assert isinstance(runtime, str)
        assert isinstance(row, Mapping)
        rows[runtime] = row
    return rows


def _kind_item_count(report: PromptSurfaceReport, kind: str) -> int:
    totals = report.totals
    by_kind = totals["by_kind"]
    assert isinstance(by_kind, Mapping)
    kind_totals = by_kind[kind]
    assert isinstance(kind_totals, Mapping)
    item_count = kind_totals["item_count"]
    assert isinstance(item_count, int)
    return item_count


def test_prompt_diagnostics_exposes_command_only_and_command_agent_projection_totals_separately(
    command_projection_report: PromptSurfaceReport,
    command_agent_projection_report: PromptSurfaceReport,
    runtime_names: tuple[str, ...],
) -> None:
    command_totals = _runtime_totals(command_projection_report)
    command_agent_totals = _runtime_totals(command_agent_projection_report)
    expected_command_count = _kind_item_count(command_projection_report, "command")
    expected_agent_count = _kind_item_count(command_agent_projection_report, "agent")

    assert expected_command_count > 0
    assert expected_agent_count > 0
    assert set(command_totals) == set(runtime_names)
    assert set(command_agent_totals) == set(runtime_names)

    for runtime in runtime_names:
        command_row = command_totals[runtime]
        command_agent_row = command_agent_totals[runtime]

        assert command_row["item_count"] == expected_command_count
        assert command_agent_row["item_count"] == expected_command_count + expected_agent_count
        assert isinstance(command_row["char_count"], int)
        assert isinstance(command_agent_row["char_count"], int)
        assert command_agent_row["char_count"] > command_row["char_count"]


def test_runtime_projection_rows_derive_from_runtime_catalog_names(
    command_agent_projection_report: PromptSurfaceReport,
    runtime_descriptors: tuple[RuntimeDescriptor, ...],
) -> None:
    runtime_names = tuple(descriptor.runtime_name for descriptor in runtime_descriptors)
    runtime_name_set = set(runtime_names)
    payload = _payload(command_agent_projection_report)
    runtime_totals = _runtime_totals(command_agent_projection_report)

    assert tuple(runtime_totals) == runtime_names

    top_prompts = payload["runtime_top_prompts"]
    assert isinstance(top_prompts, Mapping)
    assert set(top_prompts) == runtime_name_set

    for item in command_agent_projection_report.items:
        assert {metric.runtime for metric in item.runtime_projection} == runtime_name_set

    for runtime, rows in top_prompts.items():
        assert runtime in runtime_name_set
        assert isinstance(rows, list)
        assert rows
        for row in rows:
            assert isinstance(row, Mapping)
            assert row["runtime"] == runtime


def test_non_native_runtime_projection_totals_are_class_only_numeric_metrics(
    command_agent_projection_report: PromptSurfaceReport,
    runtime_descriptors: tuple[RuntimeDescriptor, ...],
) -> None:
    runtime_totals = _runtime_totals(command_agent_projection_report)
    non_native_runtimes = tuple(
        descriptor.runtime_name for descriptor in runtime_descriptors if not descriptor.native_include_support
    )

    assert non_native_runtimes
    for runtime in non_native_runtimes:
        row = runtime_totals[runtime]
        serialized_row = json.dumps(row, sort_keys=True)

        assert set(row) == RUNTIME_TOTAL_ALLOWED_KEYS
        assert row["native_include_support"] is False
        assert "raw_prompt" not in serialized_row
        assert "raw_provider" not in serialized_row
        assert "Authorization" not in serialized_row
        assert "provider_stdout" not in serialized_row
        assert "provider_stderr" not in serialized_row

        for key in RUNTIME_TOTAL_NUMERIC_KEYS:
            value = row[key]
            assert type(value) in {int, float}, f"{runtime}.{key} should be numeric, got {value!r}"
        for key in RUNTIME_TOTAL_COUNT_KEYS:
            assert row[key] >= 0, f"{runtime}.{key} should be non-negative"


def test_opencode_is_prompt_projection_visible_but_not_live_ready(
    command_agent_projection_report: PromptSurfaceReport,
) -> None:
    runtime_totals = _runtime_totals(command_agent_projection_report)
    registry = render_live_capability_registry(("opencode",))
    opencode_capability = live_capability_by_runtime("OpenCode")

    assert "opencode" in runtime_totals
    assert runtime_totals["opencode"]["item_count"] == len(command_agent_projection_report.items)
    assert registry["class_only"] is True
    assert registry["provider_subprocess_allowed"] is False
    assert opencode_capability.runtime_id == "opencode"
    assert opencode_capability.live_runner_status == "deferred"
    assert opencode_capability.deferred_reason is not None
    assert "headless command/output/auth contract is deferred" in opencode_capability.deferred_reason
    assert "opencode" not in ready_runtime_ids(("opencode",))
