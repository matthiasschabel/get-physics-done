"""Shared budget ceilings for staged runtime projection adapter tests."""

from __future__ import annotations

from gpd.adapters.runtime_catalog import iter_runtime_descriptors

_RUNTIME_DESCRIPTORS = iter_runtime_descriptors()

RUNTIME_PROJECTION_TARGETS = tuple(descriptor.runtime_name for descriptor in _RUNTIME_DESCRIPTORS)
NON_NATIVE_RUNTIME_PROJECTION_TARGETS = tuple(
    descriptor.runtime_name for descriptor in _RUNTIME_DESCRIPTORS if not descriptor.native_include_support
)

STAGED_INIT_COMMAND_PROJECTION_BUDGETS = {
    "plan-phase": {
        "claude-code": 4_550,
        "codex": 6_900,
        "gemini": 7_400,
        "opencode": 6_900,
    },
    "execute-phase": {
        "claude-code": 3_426,
        "codex": 6_005,
        "gemini": 6_496,
        "opencode": 5_920,
    },
    "new-project": {
        "claude-code": 8_000,
        "codex": 9_800,
        "gemini": 10_300,
        "opencode": 9_700,
    },
    "write-paper": {
        "claude-code": 13_076,
        "codex": 12_251,
        "gemini": 12_692,
        "opencode": 15_578,
    },
}
STAGED_INIT_TARGET_COMMANDS = tuple(STAGED_INIT_COMMAND_PROJECTION_BUDGETS)
STAGED_PROJECTED_COMMAND_CHAR_BUDGET = 20_000

TARGET_AGENT_PROJECTION_BUDGETS = {
    "gpd-planner": {"lines": 600, "chars": 35_000},
    "gpd-research-synthesizer": {"lines": 520, "chars": 31_000},
    "gpd-roadmapper": {"lines": 800, "chars": 39_000},
}
TARGET_AGENT_COMBINED_NON_NATIVE_PROJECTION_CHAR_BUDGET = 110_000

SELECTED_AGENT_PROJECTION_BUDGETS = {
    "gpd-executor": {"lines": 760, "chars": 44_000},
    "gpd-experiment-designer": {"lines": 740, "chars": 42_000},
    "gpd-plan-checker": {"lines": 450, "chars": 25_500},
    **TARGET_AGENT_PROJECTION_BUDGETS,
    "gpd-project-researcher": {"lines": 380, "chars": 18_000},
    "gpd-research-mapper": {"lines": 460, "chars": 25_000},
    "gpd-verifier": {"lines": 440, "chars": 30_000},
}
SELECTED_AGENT_PROJECTION_TARGETS = tuple(SELECTED_AGENT_PROJECTION_BUDGETS)

NATIVE_AGENT_PROJECTION_BUDGETS = {
    "gpd-verifier": {"lines": 500, "chars": 35_000},
}
