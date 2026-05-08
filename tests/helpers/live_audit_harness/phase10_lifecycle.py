"""Thin loader aliases for the Phase 10 lifecycle persona matrix."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from tests.helpers.live_audit_harness.phase9_schema import (
    Phase9BehaviorMatrix,
    load_phase9_behavior_matrix,
)

PHASE10_LIFECYCLE_MATRIX_ID: Final[str] = "phase10-lifecycle-persona-behavior-matrix-v1"
EXPECTED_PHASE10_SCENARIO_IDS: Final[tuple[str, ...]] = (
    "LIFE-PLAN-HAPPY",
    "LIFE-PLAN-STEERED",
    "LIFE-EXEC-FINAL-PLAN",
    "LIFE-EXEC-MALFORMED-RETURN",
    "LIFE-VERIFY-COMPLETE",
    "LIFE-VERIFY-GAPS",
    "LIFE-INTERRUPTED-AGENT",
    "LIFE-RECOVERABLE-DRIFT",
)


def default_phase10_lifecycle_matrix_path(repo_root: Path) -> Path:
    """Return the tracked Phase 10 lifecycle persona matrix fixture path."""

    return repo_root / "tests" / "fixtures" / "live_audit" / "phase10" / "lifecycle_persona_matrix.json"


def load_phase10_lifecycle_matrix(path: Path) -> Phase9BehaviorMatrix:
    """Load the Phase 10 lifecycle matrix through the Phase 9 provider-free schema."""

    matrix = load_phase9_behavior_matrix(path)
    if matrix.matrix_id != PHASE10_LIFECYCLE_MATRIX_ID:
        raise ValueError(f"phase10 lifecycle matrix_id must be {PHASE10_LIFECYCLE_MATRIX_ID!r}")

    scenario_ids = tuple(row.scenario_id for row in matrix.rows)
    expected = set(EXPECTED_PHASE10_SCENARIO_IDS)
    observed = set(scenario_ids)
    if observed != expected or len(scenario_ids) != len(EXPECTED_PHASE10_SCENARIO_IDS):
        missing = sorted(expected.difference(observed))
        extra = sorted(observed.difference(expected))
        duplicates = sorted(scenario_id for scenario_id in observed if scenario_ids.count(scenario_id) > 1)
        raise ValueError(
            "phase10 lifecycle matrix must cover each expected LIFE scenario exactly once; "
            f"missing={missing!r} extra={extra!r} duplicates={duplicates!r}"
        )

    return matrix


__all__ = [
    "EXPECTED_PHASE10_SCENARIO_IDS",
    "PHASE10_LIFECYCLE_MATRIX_ID",
    "default_phase10_lifecycle_matrix_path",
    "load_phase10_lifecycle_matrix",
]
