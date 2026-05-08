"""Phase 8 provider-free live capability and preflight tests."""

from __future__ import annotations

import inspect
import json
from io import StringIO

import scripts.phase8_live_provider_matrix as phase8_preflight
import tests.helpers.live_audit_harness.live_capabilities as live_capabilities
from gpd.adapters.runtime_catalog import get_runtime_descriptor, list_runtime_names
from scripts.phase8_live_provider_matrix import PreflightConfig, build_preflight_report
from tests.helpers.live_audit_harness.live_capabilities import (
    DEFAULT_BUDGETS,
    DEFAULT_TIMEOUTS,
    LIVE_RUNNER_STATUSES,
    iter_live_capabilities,
    live_capability_by_runtime,
    ready_runtime_ids,
    render_live_capability_registry,
)


def test_live_capability_registry_includes_every_catalog_runtime_with_catalog_fields() -> None:
    capabilities = iter_live_capabilities()

    assert [capability.runtime_id for capability in capabilities] == list_runtime_names()
    assert {capability.live_runner_status for capability in capabilities} <= LIVE_RUNNER_STATUSES
    for capability in capabilities:
        descriptor = get_runtime_descriptor(capability.runtime_id)
        assert capability.display_name == descriptor.display_name
        assert capability.command_prefix == descriptor.command_prefix
        assert capability.launch_command == descriptor.launch_command
        assert capability.timeout_defaults == DEFAULT_TIMEOUTS
        assert capability.budget_defaults == DEFAULT_BUDGETS
        assert capability.prompt_transport_class
        assert capability.auth_probe_class
        assert capability.event_stream_class


def test_opencode_live_capability_is_explicitly_deferred_metadata_only() -> None:
    opencode = live_capability_by_runtime("OpenCode")

    assert opencode.runtime_id == "opencode"
    assert opencode.display_name == "OpenCode"
    assert opencode.live_runner_status == "deferred"
    assert opencode.headless_command_shape_id == "opencode_headless_contract_deferred"
    assert opencode.prompt_transport_class == "metadata_only_prompt_transport_deferred"
    assert opencode.auth_probe_class == "metadata_only_auth_probe_deferred"
    assert opencode.event_stream_class == "metadata_only_event_stream_deferred"
    assert opencode.deferred_reason is not None
    assert "headless command/output/auth contract is deferred" in opencode.deferred_reason
    assert "opencode" not in ready_runtime_ids(("opencode",))


def test_render_live_capability_registry_is_class_only_and_provider_free() -> None:
    registry = render_live_capability_registry()
    serialized = json.dumps(registry, sort_keys=True)

    assert registry["schema"] == "phase8.live-capability-registry.v1"
    assert registry["class_only"] is True
    assert registry["provider_subprocess_allowed"] is False
    assert registry["timeout_defaults"] == {
        "provider_startup_seconds": 30,
        "row_timeout_seconds": 600,
        "idle_timeout_seconds": 120,
        "batch_timeout_seconds": 3600,
    }
    assert registry["budget_defaults"] == {
        "max_attempts": 1,
        "max_rows": 12,
        "max_mutating_rows": 0,
        "prompt_budget_tokens_per_row": 12000,
    }
    assert "/Users/" not in serialized
    assert "Authorization" not in serialized
    assert "raw_provider" not in serialized
    assert "raw_prompt" not in serialized


def test_phase8_preflight_default_dry_run_emits_class_only_registry_without_launching() -> None:
    report = build_preflight_report()

    assert report["schema"] == "phase8.live-provider-matrix-preflight.v1"
    assert report["class_only"] is True
    assert report["provider_subprocess_allowed_by_this_script"] is False
    assert report["provider_launch_performed"] is False
    assert report["matrix_mode"] == "dry_run"
    assert report["decision"] == "dry_run"
    assert report["live_launch_requested"] is False
    assert report["live_launch_preconditions_satisfied"] is False
    assert report["refusal_reasons"] == []
    assert [row["runtime_id"] for row in report["runtime_capabilities"]] == list_runtime_names()
    assert report["raw_material_policy"] == {
        "auth_material_recorded": False,
        "account_identifiers_recorded": False,
        "provider_stdout_recorded": False,
        "provider_stderr_recorded": False,
        "prompt_text_recorded": False,
        "argv_or_env_recorded": False,
    }


def test_phase8_preflight_refuses_live_mode_without_explicit_budget_hash_and_provider_set() -> None:
    report = build_preflight_report(PreflightConfig(matrix_mode="manual_live"))

    assert report["decision"] == "refused"
    assert report["live_launch_requested"] is True
    assert report["live_launch_preconditions_satisfied"] is False
    assert report["provider_subprocess_allowed_by_this_script"] is False
    assert report["provider_launch_performed"] is False
    assert report["refusal_reasons"] == [
        "missing_allow_live_launch",
        "missing_budget_id",
        "missing_row_set_sha256",
        "missing_provider_set",
    ]


def test_phase8_preflight_accepts_ready_provider_set_only_as_provider_free_handoff() -> None:
    report = build_preflight_report(
        PreflightConfig(
            matrix_mode="manual_live",
            provider_set=("codex,claude",),
            budget_id="phase8-budget-001",
            row_set_sha256="a" * 64,
            source_ref="abc1234",
            allow_live_launch=True,
        )
    )

    assert report["decision"] == "preflight_ready"
    assert report["live_launch_preconditions_satisfied"] is True
    assert report["provider_subprocess_allowed_by_this_script"] is False
    assert report["provider_launch_performed"] is False
    assert report["provider_set"] == ["codex", "claude-code"]
    assert report["non_ready_runtimes"] == []
    assert report["next_allowed_action"] == "hand_off_to_manual_or_nightly_live_runner"


def test_phase8_preflight_refuses_deferred_opencode_live_provider_set() -> None:
    report = build_preflight_report(
        PreflightConfig(
            matrix_mode="nightly_live",
            provider_set=("opencode",),
            budget_id="phase8-budget-001",
            row_set_sha256="b" * 64,
            allow_live_launch=True,
        )
    )

    assert report["decision"] == "refused"
    assert report["refusal_reasons"] == ["provider_not_live_ready:opencode"]
    assert report["non_ready_runtimes"] == [
        {
            "runtime_id": "opencode",
            "live_runner_status": "deferred",
            "deferred_reason": "OpenCode catalog metadata is tracked, but the headless command/output/auth contract is deferred.",
        }
    ]


def test_phase8_preflight_source_has_no_subprocess_import_path() -> None:
    helper_source = inspect.getsource(live_capabilities)
    script_source = inspect.getsource(phase8_preflight)

    assert "import subprocess" not in helper_source
    assert "from subprocess" not in helper_source
    assert not hasattr(live_capabilities, "subprocess")
    assert "import subprocess" not in script_source
    assert "from subprocess" not in script_source
    assert not hasattr(phase8_preflight, "subprocess")


def test_phase8_preflight_cli_prints_json_and_uses_dry_run_default() -> None:
    output = StringIO()

    exit_code = phase8_preflight.main([], stdout=output)
    report = json.loads(output.getvalue())

    assert exit_code == 0
    assert report["decision"] == "dry_run"
    assert report["provider_subprocess_allowed_by_this_script"] is False
