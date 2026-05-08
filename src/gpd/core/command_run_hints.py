"""Read-only run-hint metadata for already-produced command strings."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from gpd.command_labels import parse_command_label
from gpd.core.public_surface_contract import local_cli_bridge_commands

COMMAND_RUN_HINT_SCHEMA_VERSION = 1
COMMAND_RUN_HINT_EXECUTION = "not_executed"

KIND_RUNTIME_COMMAND_LABEL = "runtime_command_label"
KIND_LOCAL_CLI_VALIDATION_COMMAND = "local_cli_validation_command"
KIND_LOCAL_CLI_FINALIZER_COMMAND = "local_cli_finalizer_command"
KIND_UNKNOWN_DISPLAY_ONLY = "unknown_display_only"

_SHELL_CONTROL_TOKENS = ("\n", "\r", ";", "|", "&", "<", ">", "`", "$(")


@dataclass(frozen=True, slots=True)
class CommandRunHint:
    """Compact metadata for rendering a command suggestion without executing it."""

    source: str
    kind: str
    command: str
    action: str | None = None
    phase: str | None = None
    requires_user_initiated_runtime_command: bool = False
    fresh_context_recommended: bool = False
    notes: tuple[str, ...] = ()
    schema_version: int = COMMAND_RUN_HINT_SCHEMA_VERSION
    execution: str = COMMAND_RUN_HINT_EXECUTION

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-stable run-hint payload."""

        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "kind": self.kind,
            "command": self.command,
            "action": self.action,
            "phase": self.phase,
            "execution": self.execution,
            "requires_user_initiated_runtime_command": self.requires_user_initiated_runtime_command,
            "fresh_context_recommended": self.fresh_context_recommended,
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class _LocalCliRunHintRule:
    kind: str
    command_roots: tuple[str, ...]
    notes: tuple[str, ...] = ("display_copy_safe", "not_executed")


@lru_cache(maxsize=1)
def _registered_command_slugs() -> frozenset[str]:
    try:
        from gpd.registry import list_commands
    except ModuleNotFoundError as exc:
        if exc.name != "gpd.registry":
            raise
        return frozenset()
    return frozenset(str(slug) for slug in list_commands(name_format="slug"))


def _unique_ordered(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _local_validation_command_root(command: str) -> str | None:
    parts = command.split()
    if len(parts) >= 2 and parts[0] == "gpd" and parts[1] == "validate":
        return " ".join(parts[:2])
    return None


@lru_cache(maxsize=1)
def _contract_local_validation_command_roots() -> tuple[str, ...]:
    roots = tuple(
        root
        for command in local_cli_bridge_commands()
        if (root := _local_validation_command_root(command)) is not None
    )
    return _unique_ordered(roots)


@lru_cache(maxsize=1)
def _local_cli_run_hint_rules() -> tuple[_LocalCliRunHintRule, ...]:
    return (
        _LocalCliRunHintRule(
            kind=KIND_LOCAL_CLI_VALIDATION_COMMAND,
            command_roots=_contract_local_validation_command_roots(),
        ),
        _LocalCliRunHintRule(
            kind=KIND_LOCAL_CLI_FINALIZER_COMMAND,
            command_roots=(
                "gpd verification-report",
                "gpd proof-redteam",
                "gpd apply-return-updates",
            ),
        ),
    )


def _contains_shell_control_tokens(command: str) -> bool:
    return any(token in command for token in _SHELL_CONTROL_TOKENS)


def _is_registered_runtime_label(command: str) -> bool:
    parts = parse_command_label(command)
    if not parts.prefix or not parts.slug:
        return False

    registered_slugs = _registered_command_slugs()
    return not registered_slugs or parts.slug in registered_slugs


def _starts_with_command_prefix(command: str, prefixes: tuple[str, ...]) -> bool:
    for prefix in prefixes:
        if command == prefix or command.startswith(f"{prefix} "):
            return True
    return False


def _unknown_hint(
    *,
    command: str,
    source: str,
    action: str | None,
    phase: str | None,
    notes: tuple[str, ...],
) -> dict[str, object]:
    return CommandRunHint(
        source=source,
        kind=KIND_UNKNOWN_DISPLAY_ONLY,
        command=command,
        action=action,
        phase=phase,
        notes=notes,
    ).as_dict()


def build_command_run_hint(
    *,
    command: str | None,
    source: str,
    action: str | None = None,
    phase: str | None = None,
) -> dict[str, object] | None:
    """Return read-only run metadata for an existing command string.

    This helper never shells out, never dispatches through the runtime bridge,
    and never interprets shell syntax for execution.
    """

    normalized_command = command.strip() if isinstance(command, str) else ""
    if not normalized_command:
        return None

    if _contains_shell_control_tokens(normalized_command):
        return _unknown_hint(
            command=normalized_command,
            source=source,
            action=action,
            phase=phase,
            notes=("shell_control_tokens_present", "display_only"),
        )

    if _is_registered_runtime_label(normalized_command):
        parsed = parse_command_label(normalized_command)
        return CommandRunHint(
            source=source,
            kind=KIND_RUNTIME_COMMAND_LABEL,
            command=normalized_command,
            action=action or parsed.slug,
            phase=phase,
            requires_user_initiated_runtime_command=True,
            fresh_context_recommended=True,
            notes=("user_initiated_runtime_command_required",),
        ).as_dict()

    for rule in _local_cli_run_hint_rules():
        if _starts_with_command_prefix(normalized_command, rule.command_roots):
            return CommandRunHint(
                source=source,
                kind=rule.kind,
                command=normalized_command,
                action=action,
                phase=phase,
                notes=rule.notes,
            ).as_dict()

    return _unknown_hint(
        command=normalized_command,
        source=source,
        action=action,
        phase=phase,
        notes=("unrecognized_command_display_only",),
    )


__all__ = [
    "COMMAND_RUN_HINT_EXECUTION",
    "COMMAND_RUN_HINT_SCHEMA_VERSION",
    "KIND_LOCAL_CLI_FINALIZER_COMMAND",
    "KIND_LOCAL_CLI_VALIDATION_COMMAND",
    "KIND_RUNTIME_COMMAND_LABEL",
    "KIND_UNKNOWN_DISPLAY_ONLY",
    "CommandRunHint",
    "build_command_run_hint",
]
