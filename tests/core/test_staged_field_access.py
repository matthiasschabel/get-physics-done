from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from gpd.cli import app
from gpd.core.staged_field_access import build_staged_field_access
from gpd.core.workflow_staging import load_workflow_stage_manifest

runner = CliRunner()


def test_default_instruction_style_is_shell_free_and_manifest_backed() -> None:
    manifest = load_workflow_stage_manifest("plan-phase")
    stage = manifest.stage("planner_authoring")

    access = build_staged_field_access("plan-phase", stage_id="planner_authoring")
    payload = access.to_payload()

    assert payload["style"] == "instruction"
    assert payload["selected_fields"] == list(stage.required_init_fields)
    assert payload["aliases"] == []
    assert "shell_bindings" not in payload

    instruction_text = "\n".join(payload["instructions"])
    assert "gpd json get" not in instruction_text
    assert "$(" not in instruction_text
    assert "active_reference_context" in payload["selected_fields"]
    assert "staged_loading" not in payload["selected_fields"]


def test_json_style_exposes_exact_fields_and_requested_aliases() -> None:
    manifest = load_workflow_stage_manifest("plan-phase")
    stage = manifest.stage("planner_authoring")

    access = build_staged_field_access(
        "plan-phase",
        stage_id="planner_authoring",
        style="json",
        alias_specs=("PHASE=phase_number", "plan_count"),
    )
    payload = access.to_payload()

    assert payload["style"] == "json"
    assert payload["source"]["manifest_path"] == "workflows/plan-phase-stage-manifest.json"
    assert payload["selected_fields"] == list(stage.required_init_fields)
    assert payload["aliases"] == [
        {"alias": "PHASE", "field": "phase_number"},
        {"alias": "plan_count", "field": "plan_count"},
    ]
    assert "instructions" not in payload
    assert "shell_bindings" not in payload


def test_aliases_must_target_fields_selected_by_stage() -> None:
    with pytest.raises(ValueError, match="Field 'state_content' is not selected by plan-phase stage 'phase_bootstrap'"):
        build_staged_field_access(
            "plan-phase",
            stage_id="phase_bootstrap",
            style="json",
            alias_specs=("STATE=state_content",),
        )


def test_shell_style_binds_only_requested_aliases() -> None:
    access = build_staged_field_access(
        "plan-phase",
        stage_id="planner_authoring",
        style="shell",
        alias_specs=("PHASE=phase_number", "PHASE_DIR=phase_dir"),
    )
    payload = access.to_payload()

    assert payload["style"] == "shell"
    assert payload["aliases"] == [
        {"alias": "PHASE", "field": "phase_number"},
        {"alias": "PHASE_DIR", "field": "phase_dir"},
    ]
    assert payload["shell_bindings"] == [
        "PHASE=$(printf '%s\\n' \"${INIT}\" | gpd json get .phase_number --default \"\")",
        "PHASE_DIR=$(printf '%s\\n' \"${INIT}\" | gpd json get .phase_dir --default \"\")",
    ]
    assert all("researcher_model" not in line for line in payload["shell_bindings"])


def test_shell_style_without_aliases_binds_no_fields() -> None:
    access = build_staged_field_access("plan-phase", stage_id="planner_authoring", style="shell")
    payload = access.to_payload()

    assert payload["aliases"] == []
    assert payload["shell_bindings"] == []


def test_cli_raw_stage_field_access_json() -> None:
    result = runner.invoke(
        app,
        [
            "--raw",
            "stage",
            "field-access",
            "plan-phase",
            "--stage",
            "planner_authoring",
            "--style",
            "json",
            "--alias",
            "PHASE=phase_number",
        ],
        catch_exceptions=False,
        color=False,
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["workflow_id"] == "plan-phase"
    assert payload["stage_id"] == "planner_authoring"
    assert payload["style"] == "json"
    assert payload["aliases"] == [{"alias": "PHASE", "field": "phase_number"}]
    assert "phase_number" in payload["selected_fields"]


def test_cli_raw_stage_field_access_rejects_unselected_alias_field() -> None:
    result = runner.invoke(
        app,
        [
            "--raw",
            "stage",
            "field-access",
            "plan-phase",
            "--stage",
            "phase_bootstrap",
            "--style",
            "json",
            "--alias",
            "STATE=state_content",
        ],
        catch_exceptions=False,
        color=False,
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert "Field 'state_content' is not selected by plan-phase stage 'phase_bootstrap'" in payload["error"]
