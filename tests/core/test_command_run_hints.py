from __future__ import annotations

import pytest

from gpd.command_labels import runtime_public_command_prefixes
from gpd.core.command_run_hints import (
    KIND_LOCAL_CLI_FINALIZER_COMMAND,
    KIND_LOCAL_CLI_VALIDATION_COMMAND,
    KIND_RUNTIME_COMMAND_LABEL,
    KIND_UNKNOWN_DISPLAY_ONLY,
    build_command_run_hint,
)


def _runtime_command(slug: str, *args: str) -> str:
    prefix = runtime_public_command_prefixes()[0]
    suffix = f" {' '.join(args)}" if args else ""
    return f"{prefix}{slug}{suffix}"


def test_runtime_command_label_gets_non_executing_run_hint() -> None:
    command = _runtime_command("verify-work", "02")

    hint = build_command_run_hint(command=command, source="test", action="verify-work", phase="02")

    assert hint is not None
    assert hint["schema_version"] == 1
    assert hint["source"] == "test"
    assert hint["kind"] == KIND_RUNTIME_COMMAND_LABEL
    assert hint["command"] == command
    assert hint["action"] == "verify-work"
    assert hint["phase"] == "02"
    assert hint["execution"] == "not_executed"
    assert hint["requires_user_initiated_runtime_command"] is True
    assert hint["fresh_context_recommended"] is True


@pytest.mark.parametrize("command", [None, "", "   "])
def test_empty_command_returns_no_hint(command: str | None) -> None:
    assert build_command_run_hint(command=command, source="test") is None


def test_unknown_command_is_display_only() -> None:
    hint = build_command_run_hint(command="python -m gpd.cli suggest", source="test", action="suggest")

    assert hint is not None
    assert hint["kind"] == KIND_UNKNOWN_DISPLAY_ONLY
    assert hint["execution"] == "not_executed"
    assert hint["requires_user_initiated_runtime_command"] is False
    assert hint["fresh_context_recommended"] is False
    assert "unrecognized_command_display_only" in hint["notes"]


def test_shell_metacharacters_are_not_classified_as_executable_runtime_labels() -> None:
    command = f"{_runtime_command('verify-work', '02')} && echo should-not-run"

    hint = build_command_run_hint(command=command, source="test", action="verify-work", phase="02")

    assert hint is not None
    assert hint["kind"] == KIND_UNKNOWN_DISPLAY_ONLY
    assert hint["execution"] == "not_executed"
    assert "shell_control_tokens_present" in hint["notes"]
    assert "display_only" in hint["notes"]


@pytest.mark.parametrize(
    ("command", "expected_kind"),
    [
        ("gpd validate verification-contract GPD/verification.md", KIND_LOCAL_CLI_VALIDATION_COMMAND),
        ("gpd verification-report finalize --plan GPD/PLAN.md", KIND_LOCAL_CLI_FINALIZER_COMMAND),
        ("gpd proof-redteam finalize --proof proof.md", KIND_LOCAL_CLI_FINALIZER_COMMAND),
        ("gpd apply-return-updates GPD/return.md", KIND_LOCAL_CLI_FINALIZER_COMMAND),
    ],
)
def test_known_local_validation_and_finalizer_commands_are_display_copy_safe(
    command: str,
    expected_kind: str,
) -> None:
    hint = build_command_run_hint(command=command, source="test")

    assert hint is not None
    assert hint["kind"] == expected_kind
    assert hint["execution"] == "not_executed"
    assert hint["requires_user_initiated_runtime_command"] is False
    assert hint["fresh_context_recommended"] is False
    assert "display_copy_safe" in hint["notes"]
