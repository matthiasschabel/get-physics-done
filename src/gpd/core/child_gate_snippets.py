"""Compatibility exports for child gate tuple schema and renderers."""

from __future__ import annotations

from gpd.core.child_handoff import (
    AggregateChildGateTuple,
    ChildGateApplicator,
    ChildGateArtifact,
    ChildGateFreshness,
    ChildGateTuple,
    aggregate_child_gate_tuple_from_payload,
    child_gate_tuple_from_payload,
    parse_aggregate_child_gate_markdown,
    render_child_gate_inline_summary,
    render_child_gate_markdown,
)

__all__ = [
    "AggregateChildGateTuple",
    "ChildGateApplicator",
    "ChildGateArtifact",
    "ChildGateFreshness",
    "ChildGateTuple",
    "aggregate_child_gate_tuple_from_payload",
    "child_gate_tuple_from_payload",
    "parse_aggregate_child_gate_markdown",
    "render_child_gate_inline_summary",
    "render_child_gate_markdown",
]
