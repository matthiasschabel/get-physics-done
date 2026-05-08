"""Provider-free Phase 8 live capability registry helpers."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Final, Literal

from gpd.adapters.runtime_catalog import RuntimeDescriptor, iter_runtime_descriptors, normalize_runtime_name

PHASE8_LIVE_CAPABILITY_REGISTRY_SCHEMA: Final[str] = "phase8.live-capability-registry.v1"
PROVIDER_SUBPROCESS_ALLOWED_BY_REGISTRY: Final[bool] = False

LiveRunnerStatus = Literal["ready", "metadata_only", "deferred"]

LIVE_RUNNER_STATUSES: Final[frozenset[str]] = frozenset({"ready", "metadata_only", "deferred"})

_READY_RUNTIME_CLASSES: Final[Mapping[str, Mapping[str, str]]] = {
    "claude-code": {
        "headless_command_shape_id": "claude_code_print_stdin_prompt",
        "prompt_transport_class": "stdin_text_prompt",
        "auth_probe_class": "cli_session_metadata_only",
        "event_stream_class": "jsonl_or_text_completion_summary",
    },
    "gemini": {
        "headless_command_shape_id": "gemini_prompt_stdin",
        "prompt_transport_class": "stdin_text_prompt",
        "auth_probe_class": "cli_auth_profile_metadata_only",
        "event_stream_class": "jsonl_or_text_completion_summary",
    },
    "codex": {
        "headless_command_shape_id": "codex_exec_stdin_prompt",
        "prompt_transport_class": "stdin_text_prompt",
        "auth_probe_class": "cli_session_metadata_only",
        "event_stream_class": "jsonl_event_stream_summary",
    },
}

_DEFERRED_RUNTIME_CLASSES: Final[Mapping[str, Mapping[str, str]]] = {
    "opencode": {
        "headless_command_shape_id": "opencode_headless_contract_deferred",
        "prompt_transport_class": "metadata_only_prompt_transport_deferred",
        "auth_probe_class": "metadata_only_auth_probe_deferred",
        "event_stream_class": "metadata_only_event_stream_deferred",
        "deferred_reason": "OpenCode catalog metadata is tracked, but the headless command/output/auth contract is deferred.",
    }
}


@dataclass(frozen=True, slots=True)
class TimeoutDefaults:
    provider_startup_seconds: int = 30
    row_timeout_seconds: int = 600
    idle_timeout_seconds: int = 120
    batch_timeout_seconds: int = 3600


@dataclass(frozen=True, slots=True)
class BudgetDefaults:
    max_attempts: int = 1
    max_rows: int = 12
    max_mutating_rows: int = 0
    prompt_budget_tokens_per_row: int = 12000


@dataclass(frozen=True, slots=True)
class RuntimeLiveCapability:
    runtime_id: str
    display_name: str
    command_prefix: str
    launch_command: str
    live_runner_status: LiveRunnerStatus
    headless_command_shape_id: str
    prompt_transport_class: str
    auth_probe_class: str
    event_stream_class: str
    timeout_defaults: TimeoutDefaults
    budget_defaults: BudgetDefaults
    deferred_reason: str | None = None

    def to_json(self) -> dict[str, object]:
        return asdict(self)


DEFAULT_TIMEOUTS: Final[TimeoutDefaults] = TimeoutDefaults()
DEFAULT_BUDGETS: Final[BudgetDefaults] = BudgetDefaults()


def iter_live_capabilities(runtime_filter: Sequence[str] | None = None) -> tuple[RuntimeLiveCapability, ...]:
    """Return catalog-backed Phase 8 live capability records."""

    selected = normalize_runtime_filter(runtime_filter)
    records: list[RuntimeLiveCapability] = []
    for descriptor in iter_runtime_descriptors():
        if selected is not None and descriptor.runtime_name not in selected:
            continue
        records.append(_capability_from_descriptor(descriptor))
    return tuple(records)


def live_capability_by_runtime(runtime: str) -> RuntimeLiveCapability:
    """Return the capability record for a runtime id, alias, display name, or launch command."""

    normalized = normalize_runtime_name(runtime)
    if normalized is None:
        raise ValueError(f"unsupported runtime: {runtime!r}")
    for capability in iter_live_capabilities((normalized,)):
        return capability
    raise ValueError(f"unsupported runtime: {runtime!r}")


def render_live_capability_registry(runtime_filter: Sequence[str] | None = None) -> dict[str, object]:
    """Render a deterministic class-only registry document."""

    capabilities = iter_live_capabilities(runtime_filter)
    status_counts = Counter(capability.live_runner_status for capability in capabilities)
    return {
        "schema": PHASE8_LIVE_CAPABILITY_REGISTRY_SCHEMA,
        "class_only": True,
        "provider_subprocess_allowed": PROVIDER_SUBPROCESS_ALLOWED_BY_REGISTRY,
        "timeout_defaults": asdict(DEFAULT_TIMEOUTS),
        "budget_defaults": asdict(DEFAULT_BUDGETS),
        "status_counts": dict(sorted(status_counts.items())),
        "runtime_capabilities": [capability.to_json() for capability in capabilities],
    }


def ready_runtime_ids(runtime_filter: Sequence[str] | None = None) -> tuple[str, ...]:
    """Return runtimes that have a tracked ready live runner contract."""

    return tuple(
        capability.runtime_id
        for capability in iter_live_capabilities(runtime_filter)
        if capability.live_runner_status == "ready"
    )


def normalize_runtime_filter(runtime_filter: Sequence[str] | None) -> tuple[str, ...] | None:
    """Normalize a runtime filter while preserving first-seen order."""

    if runtime_filter is None:
        return None
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_runtime in _flatten_runtime_filter(runtime_filter):
        runtime = normalize_runtime_name(raw_runtime)
        if runtime is None:
            raise ValueError(f"unsupported runtime: {raw_runtime!r}")
        if runtime in seen:
            continue
        seen.add(runtime)
        normalized.append(runtime)
    return tuple(normalized)


def _capability_from_descriptor(descriptor: RuntimeDescriptor) -> RuntimeLiveCapability:
    if descriptor.runtime_name in _READY_RUNTIME_CLASSES:
        metadata = _READY_RUNTIME_CLASSES[descriptor.runtime_name]
        status: LiveRunnerStatus = "ready"
        deferred_reason = None
    elif descriptor.runtime_name in _DEFERRED_RUNTIME_CLASSES:
        metadata = _DEFERRED_RUNTIME_CLASSES[descriptor.runtime_name]
        status = "deferred"
        deferred_reason = metadata["deferred_reason"]
    else:
        metadata = {
            "headless_command_shape_id": "catalog_metadata_only",
            "prompt_transport_class": "metadata_only_prompt_transport",
            "auth_probe_class": "metadata_only_auth_probe",
            "event_stream_class": "metadata_only_event_stream",
        }
        status = "metadata_only"
        deferred_reason = "Runtime is catalog-visible but does not yet have a tracked Phase 8 live contract."

    return RuntimeLiveCapability(
        runtime_id=descriptor.runtime_name,
        display_name=descriptor.display_name,
        command_prefix=descriptor.command_prefix,
        launch_command=descriptor.launch_command,
        live_runner_status=status,
        headless_command_shape_id=metadata["headless_command_shape_id"],
        prompt_transport_class=metadata["prompt_transport_class"],
        auth_probe_class=metadata["auth_probe_class"],
        event_stream_class=metadata["event_stream_class"],
        timeout_defaults=DEFAULT_TIMEOUTS,
        budget_defaults=DEFAULT_BUDGETS,
        deferred_reason=deferred_reason,
    )


def _flatten_runtime_filter(runtime_filter: Sequence[str]) -> Iterable[str]:
    for item in runtime_filter:
        for runtime in item.split(","):
            normalized = runtime.strip()
            if normalized:
                yield normalized


__all__ = [
    "DEFAULT_BUDGETS",
    "DEFAULT_TIMEOUTS",
    "LIVE_RUNNER_STATUSES",
    "PHASE8_LIVE_CAPABILITY_REGISTRY_SCHEMA",
    "PROVIDER_SUBPROCESS_ALLOWED_BY_REGISTRY",
    "BudgetDefaults",
    "LiveRunnerStatus",
    "RuntimeLiveCapability",
    "TimeoutDefaults",
    "iter_live_capabilities",
    "live_capability_by_runtime",
    "normalize_runtime_filter",
    "ready_runtime_ids",
    "render_live_capability_registry",
]
