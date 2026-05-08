"""Shared budget ceilings for staged runtime projection adapter tests."""

from __future__ import annotations

STAGED_INIT_COMMAND_PROJECTION_BUDGETS = {
    "plan-phase": {
        "claude-code": 4_196,
        "codex": 6_597,
        "gemini": 7_095,
        "opencode": 6_612,
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
