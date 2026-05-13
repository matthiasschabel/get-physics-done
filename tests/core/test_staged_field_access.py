from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gpd.cli import app
from gpd.core.context import init_execute_phase, init_new_project, init_plan_phase, init_write_paper
from gpd.core.staged_field_access import build_staged_field_access
from gpd.core.state import default_state_dict
from gpd.core.workflow_staging import (
    WORKFLOW_STAGE_MANIFEST_DIR,
    WORKFLOW_STAGE_MANIFEST_SUFFIX,
    load_workflow_stage_manifest,
)
from tests.workflow_authority_support import workflow_authority_text

runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "stage0"


def _manifest_workflow_ids() -> tuple[str, ...]:
    return tuple(
        sorted(
            path.name.removesuffix(WORKFLOW_STAGE_MANIFEST_SUFFIX)
            for path in WORKFLOW_STAGE_MANIFEST_DIR.glob(f"*{WORKFLOW_STAGE_MANIFEST_SUFFIX}")
        )
    )


FIELD_ACCESS_WORKFLOWS = _manifest_workflow_ids()
PAYLOAD_WORKFLOWS = (
    "plan-phase",
    "execute-phase",
    "new-project",
    "write-paper",
)
STAGED_PROMPT_HYGIENE_WORKFLOWS = ("new-milestone", "quick", "map-research", "literature-review")
EXPECTED_FIELD_ACCESS_STAGE_MENTIONS = {
    "plan-phase": ("phase_bootstrap", "research_routing", "planner_authoring", "checker_revision"),
    "execute-phase": (
        "phase_bootstrap",
        "phase_classification",
        "wave_planning",
        "pre_execution_specialists",
        "wave_dispatch",
        "checkpoint_resume",
        "aggregate_and_verify",
        "closeout",
    ),
    "new-project": (
        "minimal_artifacts",
        "project_artifacts",
        "literature_survey",
        "requirements_authoring",
        "roadmap_authoring",
        "conventions_handoff",
        "completion",
    ),
    "write-paper": (
        "paper_bootstrap",
        "outline_and_scaffold",
        "figure_and_section_authoring",
        "consistency_and_references",
        "publication_review",
    ),
    "new-milestone": ("milestone_bootstrap", "survey_objectives", "roadmap_authoring"),
    "quick": ("task_bootstrap", "task_authoring", "reference_context"),
    "map-research": ("map_bootstrap", "mapper_authoring"),
    "literature-review": ("review_bootstrap", "scope_locked", "review_handoff", "completion_gate"),
}
STAGED_FIELD_INVENTORY_PATTERNS = (
    re.compile(r"\bParse JSON for\s*:?\s*`", re.IGNORECASE),
    re.compile(r"\bExtract from init JSON\s*:?\s*`", re.IGNORECASE),
    re.compile(r"\bExtract from the staged refresh\s*:?\s*`", re.IGNORECASE),
    re.compile(r"\bParse the staged refresh for\s*`", re.IGNORECASE),
    re.compile(r"\bParse the completion refresh for\s*`", re.IGNORECASE),
)


def _setup_manifest_owned_payload_project(project_root: Path) -> None:
    gpd_dir = project_root / "GPD"
    phase_dir = gpd_dir / "phases" / "02-analysis"
    phase_dir.mkdir(parents=True)

    (gpd_dir / "PROJECT.md").write_text("# Test Project\n\nPaper target.\n", encoding="utf-8")
    (gpd_dir / "ROADMAP.md").write_text(
        "# Roadmap\n\n## Phase 2: Analysis\n\n**Goal:** Compare the benchmark observable.\n",
        encoding="utf-8",
    )
    (gpd_dir / "REQUIREMENTS.md").write_text("# Requirements\n- Preserve benchmark anchors.\n", encoding="utf-8")
    (gpd_dir / "STATE.md").write_text("# State\nCurrent phase: 02\n", encoding="utf-8")

    (phase_dir / "02-PLAN.md").write_text("objective: compare benchmark observable\n", encoding="utf-8")
    (phase_dir / "02-SUMMARY.md").write_text("# Summary\nExisting result.\n", encoding="utf-8")
    (phase_dir / "02-CONTEXT.md").write_text("# Context\nLocked scope.\n", encoding="utf-8")
    (phase_dir / "02-RESEARCH.md").write_text("# Research\nMethod comparison.\n", encoding="utf-8")
    (phase_dir / "02-EXPERIMENT-DESIGN.md").write_text("# Experiment Design\nGrid scan.\n", encoding="utf-8")
    (phase_dir / "02-VERIFICATION.md").write_text("# Verification\nGap notes.\n", encoding="utf-8")
    (phase_dir / "02-VALIDATION.md").write_text("# Validation\nChecks.\n", encoding="utf-8")

    state = default_state_dict()
    state["project_contract"] = json.loads((FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"))
    state["position"]["current_phase"] = "02"
    state["current_execution"] = {
        "session_id": "sess-stage-parity",
        "phase": "02",
        "plan": "01",
        "segment_status": "waiting_review",
        "resume_file": "GPD/phases/02-analysis/.continue-here.md",
        "pre_fanout_review_pending": True,
    }
    (gpd_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")


def _staged_init_payload(workflow_id: str, project_root: Path, stage_id: str) -> dict[str, object]:
    builders: dict[str, Callable[[Path, str], dict[str, object]]] = {
        "plan-phase": lambda root, stage: init_plan_phase(root, "2", stage=stage),
        "execute-phase": lambda root, stage: init_execute_phase(root, "2", stage=stage),
        "new-project": lambda root, stage: init_new_project(root, stage=stage),
        "write-paper": lambda root, stage: init_write_paper(root, stage=stage),
    }
    return builders[workflow_id](project_root, stage_id)


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


@pytest.mark.parametrize("workflow_id", FIELD_ACCESS_WORKFLOWS)
def test_instruction_style_matches_manifest_for_all_staged_workflow_stages(workflow_id: str) -> None:
    manifest = load_workflow_stage_manifest(workflow_id)

    for stage_id in manifest.stage_ids():
        stage = manifest.stage(stage_id)
        access = build_staged_field_access(workflow_id, stage_id=stage_id)
        payload = access.to_payload()

        assert payload["workflow_id"] == workflow_id
        assert payload["stage_id"] == stage_id
        assert payload["style"] == "instruction"
        assert payload["selected_fields"] == list(stage.required_init_fields)
        assert payload["aliases"] == []
        assert "shell_bindings" not in payload
        assert payload["selected_fields"] == manifest.staged_loading_payload(stage_id)["required_init_fields"]


@pytest.mark.parametrize("workflow_id", PAYLOAD_WORKFLOWS)
def test_staged_payload_fields_remain_manifest_owned(tmp_path: Path, workflow_id: str) -> None:
    _setup_manifest_owned_payload_project(tmp_path)
    manifest = load_workflow_stage_manifest(workflow_id)

    for stage_id in manifest.stage_ids():
        stage = manifest.stage(stage_id)
        payload = _staged_init_payload(workflow_id, tmp_path, stage_id)
        access_payload = build_staged_field_access(workflow_id, stage_id=stage_id).to_payload()

        assert tuple(field for field in payload if field != "staged_loading") == stage.required_init_fields
        assert set(payload) == set(stage.required_init_fields) | {"staged_loading"}
        assert payload["staged_loading"] == manifest.staged_loading_payload(stage_id)
        assert access_payload["selected_fields"] == list(stage.required_init_fields)


def test_target_workflow_prompts_use_field_access_helper_for_staged_reloads() -> None:
    for workflow_id, stage_ids in EXPECTED_FIELD_ACCESS_STAGE_MENTIONS.items():
        source = workflow_authority_text(WORKFLOWS_DIR, workflow_id)

        assert f"gpd --raw stage field-access {workflow_id}" in source
        for stage_id in stage_ids:
            assert f"gpd --raw stage field-access {workflow_id} --stage {stage_id} --style instruction" in source


@pytest.mark.parametrize("workflow_id", STAGED_PROMPT_HYGIENE_WORKFLOWS)
def test_staged_workflow_prompts_do_not_reintroduce_hand_written_field_inventories(workflow_id: str) -> None:
    source = workflow_authority_text(WORKFLOWS_DIR, workflow_id)

    for pattern in STAGED_FIELD_INVENTORY_PATTERNS:
        assert pattern.search(source) is None


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
        'PHASE=$(printf \'%s\\n\' "${INIT}" | gpd json get .phase_number --default "")',
        'PHASE_DIR=$(printf \'%s\\n\' "${INIT}" | gpd json get .phase_dir --default "")',
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
