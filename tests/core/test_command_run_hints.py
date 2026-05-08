from __future__ import annotations

import pytest

from gpd.adapters.runtime_catalog import iter_runtime_descriptors
from gpd.command_labels import runtime_public_command_prefixes
from gpd.core.command_run_hints import (
    KIND_LOCAL_CLI_FINALIZER_COMMAND,
    KIND_LOCAL_CLI_VALIDATION_COMMAND,
    KIND_RUNTIME_COMMAND_LABEL,
    KIND_UNKNOWN_DISPLAY_ONLY,
    build_command_run_hint,
)
from gpd.core.public_surface_contract import local_cli_bridge_commands


def _runtime_command(slug: str, *args: str) -> str:
    prefix = runtime_public_command_prefixes()[0]
    suffix = f" {' '.join(args)}" if args else ""
    return f"{prefix}{slug}{suffix}"


def _local_cli_command_example(command: str) -> str:
    runtime_name = iter_runtime_descriptors()[0].runtime_name
    return (
        command.replace("<runtime>", runtime_name)
        .replace("<mode>", "review")
        .replace("<PLAN.md>", "GPD/PLAN.md")
    )


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


def test_structural_verify_phase_route_is_not_runtime_verify_work_hint() -> None:
    hint = build_command_run_hint(command="gpd verify phase 02", source="test", action="verify-work", phase="02")

    assert hint is not None
    assert hint["kind"] == KIND_UNKNOWN_DISPLAY_ONLY
    assert hint["execution"] == "not_executed"
    assert hint["requires_user_initiated_runtime_command"] is False
    assert "unrecognized_command_display_only" in hint["notes"]


def test_shell_metacharacters_are_not_classified_as_executable_runtime_labels() -> None:
    command = f"{_runtime_command('verify-work', '02')} && echo should-not-run"

    hint = build_command_run_hint(command=command, source="test", action="verify-work", phase="02")

    assert hint is not None
    assert hint["kind"] == KIND_UNKNOWN_DISPLAY_ONLY
    assert hint["execution"] == "not_executed"
    assert "shell_control_tokens_present" in hint["notes"]
    assert "display_only" in hint["notes"]


def test_contract_local_validation_commands_are_display_copy_safe() -> None:
    commands = tuple(
        _local_cli_command_example(command)
        for command in local_cli_bridge_commands()
        if command.startswith("gpd validate ")
    )
    assert commands

    for command in commands:
        hint = build_command_run_hint(command=command, source="test")

        assert hint is not None
        assert hint["kind"] == KIND_LOCAL_CLI_VALIDATION_COMMAND
        assert hint["execution"] == "not_executed"
        assert hint["requires_user_initiated_runtime_command"] is False
        assert hint["fresh_context_recommended"] is False
        assert "display_copy_safe" in hint["notes"]


def test_local_validation_family_commands_remain_display_copy_safe() -> None:
    hint = build_command_run_hint(
        command="gpd validate verification-contract GPD/verification.md",
        source="test",
    )

    assert hint is not None
    assert hint["kind"] == KIND_LOCAL_CLI_VALIDATION_COMMAND
    assert hint["execution"] == "not_executed"
    assert hint["requires_user_initiated_runtime_command"] is False
    assert hint["fresh_context_recommended"] is False
    assert "display_copy_safe" in hint["notes"]


def test_representative_local_finalizer_command_is_display_copy_safe() -> None:
    command = "gpd verification-report finalize --plan GPD/PLAN.md"

    hint = build_command_run_hint(command=command, source="test")

    assert hint is not None
    assert hint["kind"] == KIND_LOCAL_CLI_FINALIZER_COMMAND
    assert hint["execution"] == "not_executed"
    assert hint["requires_user_initiated_runtime_command"] is False
    assert hint["fresh_context_recommended"] is False
    assert "display_copy_safe" in hint["notes"]
