"""Compatibility exports for child gate tuple schema and renderers."""

from __future__ import annotations

from gpd.core.child_handoff import (
    ChildGateApplicator,
    ChildGateArtifact,
    ChildGateFreshness,
    ChildGateTuple,
    child_gate_tuple_from_payload,
    render_child_gate_inline_summary,
    render_child_gate_markdown,
)

__all__ = [
    "ChildGateApplicator",
    "ChildGateArtifact",
    "ChildGateFreshness",
    "ChildGateTuple",
    "child_gate_tuple_from_payload",
    "render_child_gate_inline_summary",
    "render_child_gate_markdown",
]
