"""Read-only phase closeout readiness checks."""

from __future__ import annotations

from pathlib import Path

from gpd.core.phase_lifecycle import (
    OWNER_LOCAL_HELPER,
    OWNER_LOCAL_TRANSITION,
    OWNER_RUNTIME,
    ROLE_PRIMARY,
    ROLE_SECONDARY,
    PhaseCloseoutReadiness,
    phase_lifecycle_decision,
)


def phase_closeout_readiness(
    cwd: Path,
    phase: str,
    *,
    require_verification: bool = False,
) -> PhaseCloseoutReadiness:
    """Return a read-only closeout gate result; never mutate roadmap, state, or tags."""

    return phase_lifecycle_decision(
        cwd,
        phase,
        require_verification=require_verification,
    ).closeout_readiness


__all__ = [
    "OWNER_LOCAL_HELPER",
    "OWNER_LOCAL_TRANSITION",
    "OWNER_RUNTIME",
    "PhaseCloseoutReadiness",
    "ROLE_PRIMARY",
    "ROLE_SECONDARY",
    "phase_closeout_readiness",
]
