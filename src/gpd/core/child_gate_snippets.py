"""Compatibility exports for child gate tuple schema.

Prompt snippet rendering was removed; child-gate authority now lives in
``gpd.core.child_handoff`` beside the read-only validator.
"""

from __future__ import annotations

from gpd.core.child_handoff import (
    ChildGateApplicator,
    ChildGateArtifact,
    ChildGateFreshness,
    ChildGateTuple,
    child_gate_tuple_from_payload,
)

__all__ = [
    "ChildGateApplicator",
    "ChildGateArtifact",
    "ChildGateFreshness",
    "ChildGateTuple",
    "child_gate_tuple_from_payload",
]
