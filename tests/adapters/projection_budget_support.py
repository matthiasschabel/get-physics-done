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
        "codex": 5_987,
        "gemini": 6_478,
        "opencode": 5_902,
    },
    "new-project": {
        "claude-code": 9_740,
        "codex": 11_588,
        "gemini": 12_080,
        "opencode": 11_453,
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
    "gpd-planner": {"lines": 650, "chars": 37_000},
    "gpd-research-synthesizer": {"lines": 1_050, "chars": 53_000},
    "gpd-roadmapper": {"lines": 1_030, "chars": 45_000},
}
TARGET_AGENT_COMBINED_NON_NATIVE_PROJECTION_CHAR_BUDGET = 135_000

SELECTED_AGENT_PROJECTION_BUDGETS = {
    "gpd-executor": {"lines": 840, "chars": 53_000},
    "gpd-experiment-designer": {"lines": 870, "chars": 49_000},
    "gpd-plan-checker": {"lines": 450, "chars": 25_500},
    **TARGET_AGENT_PROJECTION_BUDGETS,
    "gpd-project-researcher": {"lines": 1_060, "chars": 65_000},
    "gpd-research-mapper": {"lines": 800, "chars": 40_000},
    "gpd-verifier": {"lines": 440, "chars": 30_000},
}
SELECTED_AGENT_PROJECTION_TARGETS = tuple(SELECTED_AGENT_PROJECTION_BUDGETS)

NATIVE_AGENT_PROJECTION_BUDGETS = {
    "gpd-verifier": {"lines": 500, "chars": 35_000},
}
