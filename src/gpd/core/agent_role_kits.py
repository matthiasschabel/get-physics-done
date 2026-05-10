"""Closed registry and renderer for shared agent role kits."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

AGENT_ROLE_KITS_FRONTMATTER_KEY = "role_kits"
AGENT_ROLE_KITS_HEADING = "Agent Role Kits"


@dataclass(frozen=True, slots=True)
class AgentRoleKit:
    """Model-visible shared lifecycle rules selected by agent frontmatter."""

    id: str
    label: str
    authority_paths: tuple[str, ...]
    rules: tuple[str, ...]
    applies_to: tuple[str, ...] = ()


_ROLE_KIT_DEFINITIONS: tuple[AgentRoleKit, ...] = (
    AgentRoleKit(
        id="status-routing",
        label="Status Routing",
        authority_paths=("{GPD_INSTALL_DIR}/references/orchestration/agent-infrastructure.md",),
        rules=(
            "Route lifecycle state from `gpd_return.status`; do not infer completion, checkpoint, or failure from headings or prose alone.",
            "Use the shared status vocabulary from the authority path while preserving this prompt's role-specific return fields.",
        ),
    ),
    AgentRoleKit(
        id="fresh-continuation",
        label="Fresh Continuation",
        authority_paths=("{GPD_INSTALL_DIR}/references/orchestration/continuation-boundary.md",),
        rules=(
            "A checkpoint is a one-shot handoff: return once, stop, and let the orchestrator decide presentation or continuation.",
            "On resumed or fresh continuation, re-read current state and artifacts before acting; do not rely on stale prior-run assumptions.",
        ),
    ),
    AgentRoleKit(
        id="files-written-freshness",
        label="Files-Written Freshness",
        authority_paths=("{GPD_INSTALL_DIR}/references/orchestration/agent-infrastructure.md",),
        rules=(
            "`files_written` names only files created or updated in the current run.",
            "Preexisting or stale files are evidence to inspect, not proof of current completion.",
        ),
    ),
    AgentRoleKit(
        id="child-artifact-gate",
        label="Child Artifact Gate",
        authority_paths=(
            "{GPD_INSTALL_DIR}/references/orchestration/child-artifact-gate.md",
            "{GPD_INSTALL_DIR}/references/orchestration/agent-delegation.md",
        ),
        rules=(
            "Accept child-agent completion only through required artifact gates, validator checks, or explicit fallback instructions.",
            "If a child return is incomplete, failed, or unverifiable, retry or continue in the main context according to the local workflow gate.",
        ),
    ),
    AgentRoleKit(
        id="no-child-return-synthesis",
        label="No Child Return Synthesis",
        authority_paths=(
            "{GPD_INSTALL_DIR}/references/orchestration/agent-delegation.md",
            "{GPD_INSTALL_DIR}/references/orchestration/child-artifact-gate.md",
        ),
        rules=(
            "Do not synthesize, patch, or paste a child agent's `gpd_return`.",
            "Use the child's actual returned artifact/status, retry the child, or invoke an explicit main-context fallback.",
        ),
    ),
    AgentRoleKit(
        id="context-pressure",
        label="Context Pressure",
        authority_paths=(
            "{GPD_INSTALL_DIR}/references/orchestration/agent-infrastructure.md",
            "{GPD_INSTALL_DIR}/references/orchestration/context-pressure-thresholds.md",
        ),
        rules=(
            "When context pressure is high, finish the smallest coherent artifact or checkpoint rather than broadening scope.",
            "Use local role thresholds for what counts as high pressure; report `context_pressure: high` only when the shared policy calls for it.",
        ),
    ),
    AgentRoleKit(
        id="read-only-return",
        label="Read-Only Return",
        authority_paths=("{GPD_INSTALL_DIR}/references/orchestration/agent-infrastructure.md",),
        rules=(
            "For read-only roles, keep `files_written: []` unless this prompt explicitly authorizes a diagnostic sidecar.",
            "Report findings through the return envelope instead of claiming file outputs.",
        ),
    ),
)

_ROLE_KITS: dict[str, AgentRoleKit] = {kit.id: kit for kit in _ROLE_KIT_DEFINITIONS}

if len(_ROLE_KITS) != len(_ROLE_KIT_DEFINITIONS):  # pragma: no cover - import-time invariant
    raise RuntimeError("Agent role kit ids must be unique")


def valid_agent_role_kit_ids() -> tuple[str, ...]:
    """Return the closed role-kit id vocabulary."""

    return tuple(_ROLE_KITS)


def get_agent_role_kit(role_kit_id: str) -> AgentRoleKit:
    """Return a role-kit definition by id."""

    return _ROLE_KITS[role_kit_id]


def parse_agent_role_kit_ids(raw: object, *, agent_name: str) -> tuple[str, ...]:
    """Parse and validate the optional ``role_kits`` agent frontmatter field."""

    if raw is None:
        return ()

    subject = f"{AGENT_ROLE_KITS_FRONTMATTER_KEY} for {agent_name}"
    values: list[str] = []

    if isinstance(raw, str):
        candidates: Sequence[object] = list(raw.split(","))
    elif isinstance(raw, list):
        candidates = raw
    else:
        raise ValueError(f"{subject} must be a string or list of strings")

    seen: set[str] = set()
    valid_ids = valid_agent_role_kit_ids()
    for item in candidates:
        if not isinstance(item, str):
            raise ValueError(f"{subject} must contain only strings")
        role_kit_id = item.strip()
        if not role_kit_id:
            raise ValueError(f"{subject} must not contain blank entries")
        if role_kit_id in seen:
            raise ValueError(f"{subject} must not contain duplicate id {role_kit_id!r}")
        if role_kit_id not in _ROLE_KITS:
            valid = ", ".join(valid_ids)
            raise ValueError(f"Unknown role_kit {role_kit_id!r} for {agent_name}; expected one of: {valid}")
        seen.add(role_kit_id)
        values.append(role_kit_id)

    return tuple(values)


def _resolve_role_kits(role_kit_ids: Sequence[str]) -> tuple[AgentRoleKit, ...]:
    raw: object = role_kit_ids if isinstance(role_kit_ids, str) else list(role_kit_ids)
    return tuple(
        get_agent_role_kit(role_kit_id) for role_kit_id in parse_agent_role_kit_ids(raw, agent_name="rendered agent")
    )


def role_kit_authority_paths(role_kit_ids: Sequence[str]) -> tuple[str, ...]:
    """Return selected role-kit authority paths, deduped in render order."""

    paths: list[str] = []
    seen: set[str] = set()
    for kit in _resolve_role_kits(role_kit_ids):
        for path in kit.authority_paths:
            if path not in seen:
                seen.add(path)
                paths.append(path)
    return tuple(paths)


def render_agent_role_kits_section(role_kit_ids: Sequence[str]) -> str:
    """Render the model-visible role-kit section for selected kit ids."""

    kits = _resolve_role_kits(role_kit_ids)
    if not kits:
        return ""

    lines = [
        f"## {AGENT_ROLE_KITS_HEADING}",
        "",
        "Generated from `role_kits` frontmatter. Apply these shared lifecycle rules; keep role-specific artifact paths, validators, and output fields from this prompt.",
    ]
    for kit in kits:
        lines.extend(("", f"### {kit.label} (`{kit.id}`)"))
        if kit.authority_paths:
            authority = ", ".join(f"`{path}`" for path in kit.authority_paths)
            lines.append(f"Authority: {authority}")
        lines.extend(f"- {rule}" for rule in kit.rules)
    return "\n".join(lines)
