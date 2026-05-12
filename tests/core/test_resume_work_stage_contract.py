"""Assertions for the staged `resume-work` contract."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gpd.cli import app
from gpd.core.workflow_staging import (
    known_init_fields_for_workflow,
    load_workflow_stage_manifest,
    validate_workflow_stage_manifest_payload,
)
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
RUNNER = CliRunner()


def _workflow_step(text: str, step_name: str) -> str:
    start = text.index(f'<step name="{step_name}">')
    end = text.index("</step>", start)
    return text[start:end]


def _workflow_block(text: str, block_name: str) -> str:
    start = text.index(f"<{block_name}>")
    end = text.index(f"</{block_name}>", start)
    return text[start:end]


def _command_is_explicitly_excluded(text: str, command: str) -> bool:
    for match in re.finditer(re.escape(command), text):
        window = text[max(0, match.start() - 160) : match.end() + 160].lower()
        if re.search(
            r"\b(do not|don't|must not|mustn't|forbid|forbidden|exclude|excluded|never|"
            r"not\s+(?:to|be|allowed|permitted|use|run|call|invoke|include|route|delegate|spawn|write|read|"
            r"trust|continue|advance|proceed))\b",
            window,
        ):
            return True
    return False


def test_resume_work_stage_manifest_loads_and_preserves_stage_order() -> None:
    manifest = load_workflow_stage_manifest("resume-work")

    assert manifest.workflow_id == "resume-work"
    assert manifest.stage_ids() == ("resume_bootstrap", "state_restore", "derivation_restore", "resume_routing")

    bootstrap = manifest.get_stage("resume_bootstrap")
    state_restore = manifest.get_stage("state_restore")
    derivation_restore = manifest.get_stage("derivation_restore")
    resume_routing = manifest.get_stage("resume_routing")

    assert bootstrap.loaded_authorities == (
        "workflows/resume-work/resume-bootstrap.md",
        "references/orchestration/resume-vocabulary.md",
    )
    assert "templates/state-json-schema.md" in bootstrap.must_not_eager_load
    assert "reference_artifacts_content" not in bootstrap.required_init_fields
    assert "project_contract_gate" not in bootstrap.required_init_fields
    assert "state_json_backup_exists" in bootstrap.required_init_fields

    assert state_restore.loaded_authorities == (
        "workflows/resume-work/state-restore.md",
        "references/orchestration/state-portability.md",
    )
    assert "project_contract_gate" in state_restore.required_init_fields
    assert "state_content" in state_restore.required_init_fields
    assert "project_content" in state_restore.required_init_fields
    assert "reference_artifacts_content" not in state_restore.required_init_fields

    assert derivation_restore.loaded_authorities == (
        "workflows/resume-work/derivation-restore.md",
        "references/orchestration/continuation-format.md",
    )
    assert derivation_restore.required_init_fields[:2] == (
        "derived_convention_lock",
        "derived_convention_lock_count",
    )
    assert "derived_intermediate_results" in derivation_restore.required_init_fields
    assert "derived_approximations" in derivation_restore.required_init_fields
    assert "derivation_state_content" in derivation_restore.required_init_fields
    assert "continuity_handoff_content" in derivation_restore.required_init_fields
    assert derivation_restore.required_init_fields.index(
        "derived_approximation_count"
    ) < derivation_restore.required_init_fields.index("derivation_state_content")
    assert derivation_restore.writes_allowed == ()
    assert "file_write" not in derivation_restore.allowed_tools

    assert "project_contract_gate" in resume_routing.required_init_fields
    assert "roadmap_content" in resume_routing.required_init_fields
    assert "continuity_handoff_content" in resume_routing.required_init_fields

    known_fields = known_init_fields_for_workflow("resume-work")
    assert known_fields is not None
    assert "state_json_backup_exists" in known_fields


def test_resume_work_stage_manifest_rejects_invalid_field_drift() -> None:
    payload = json.loads((WORKFLOWS_DIR / "resume-work-stage-manifest.json").read_text(encoding="utf-8"))
    payload["stages"][0]["required_init_fields"] = ["bogus_field"]

    with pytest.raises(ValueError, match="unknown field name"):
        validate_workflow_stage_manifest_payload(payload, expected_workflow_id="resume-work")


def test_resume_work_workflow_uses_public_init_resume_for_staged_payloads() -> None:
    text = workflow_authority_text(WORKFLOWS_DIR, "resume-work")

    assert "INIT=$(gpd --raw init resume --stage resume_bootstrap)" in text
    assert "STATE_RESTORE_INIT=$(gpd --raw init resume --stage state_restore)" in text
    assert "DERIVATION_RESTORE_INIT=$(gpd --raw init resume --stage derivation_restore)" in text
    assert "RESUME_ROUTING_INIT=$(gpd --raw init resume --stage resume_routing)" in text
    assert "gpd --raw init resume-work" not in text
    assert "@{GPD_INSTALL_DIR}/references/orchestration/continuation-format.md" not in text
    assert "@{GPD_INSTALL_DIR}/references/orchestration/state-portability.md" not in text
    assert "@{GPD_INSTALL_DIR}/templates/state-json-schema.md" not in text


def test_resume_work_derivation_restore_does_not_rewrite_derivation_state() -> None:
    text = workflow_authority_text(WORKFLOWS_DIR, "resume-work")
    section = _workflow_step(text, "restore_persistent_state")

    assert "Do not prune, rewrite, replace, or otherwise modify `GPD/DERIVATION-STATE.md`" in section
    assert "This is a report-only check." in section
    assert "Read and summarize the file as-is" in section
    assert "TMP_FILE" not in section
    assert "Pruning oldest" not in section
    assert "Pruned file" not in section
    forbidden_write_patterns = (
        r">\s*GPD/DERIVATION-STATE\.md",
        r">>\s*GPD/DERIVATION-STATE\.md",
        r">\s*\"\$TMP_FILE\"",
        r"\bcp\b[^\n]*GPD/DERIVATION-STATE\.md",
        r"\bmv\b[^\n]*GPD/DERIVATION-STATE\.md",
        r"\bsed\s+-i\b[^\n]*GPD/DERIVATION-STATE\.md",
    )
    for pattern in forbidden_write_patterns:
        assert re.search(pattern, section) is None


def test_resume_work_transition_reference_uses_installed_workflow_path() -> None:
    text = workflow_authority_text(WORKFLOWS_DIR, "resume-work")

    assert "- **Transition** -> `{GPD_INSTALL_DIR}/workflows/transition.md`" in text
    assert "- **Transition** -> ./transition.md" not in text


def test_resume_work_quick_resume_refuses_auto_selected_recent_projects() -> None:
    text = workflow_authority_text(WORKFLOWS_DIR, "resume-work")
    initialize = _workflow_step(text, "initialize")
    quick_resume = _workflow_block(text, "quick_resume")

    ambiguity_gate = "**If `project_reentry_requires_selection` is true"
    auto_recent_gate = "**If `project_root_auto_selected` is true"
    new_project_gate = "**If `planning_exists` is false and no recent-project selection is required:**"

    assert ambiguity_gate in initialize
    assert auto_recent_gate in initialize
    assert new_project_gate in initialize
    assert initialize.index(ambiguity_gate) < initialize.index(new_project_gate)
    assert initialize.index(auto_recent_gate) < initialize.index(new_project_gate)
    assert "quick resume is disabled" in quick_resume
    assert "do not continue automatically" in quick_resume
    assert "project_contract_gate.repair_required" in quick_resume
    assert "quick resume must not auto-execute" in quick_resume


def test_resume_work_partial_recoverable_repair_menu_blocks_downstream_actions() -> None:
    text = workflow_authority_text(WORKFLOWS_DIR, "resume-work")
    branch = _workflow_step(text, "determine_next_action")

    for command in ("gpd:sync-state", "gpd:health", "gpd:resume-work"):
        assert command in branch

    assert "**If partial/recoverable state or `project_contract_gate.repair_required` needs repair:**" in branch
    assert re.search(r"(?i)\bnext\b[^\n.]{0,80}gpd:sync-state", branch)

    normalized = branch.lower()
    assert "stop before" in normalized
    assert "planning" in normalized
    assert "execution" in normalized
    assert re.search(r"\bmutat(e|es|ing|ion|ions)\b", normalized)
    assert "overrides quick-resume auto-execution" in normalized

    assert _command_is_explicitly_excluded(branch, "gpd:progress")
    assert _command_is_explicitly_excluded(branch, "gpd:new-project")


def test_resume_routing_status_presentation_uses_three_lanes() -> None:
    text = workflow_authority_text(WORKFLOWS_DIR, "resume-work")
    section = _workflow_step(text, "present_status")

    assert "exactly three visible lanes" in section
    for lane in ("Selected project", "Primary resume target", "Blocker / next command"):
        assert lane in section

    assert '`active_resume_kind="bounded_segment"`' in section
    assert "outranks" in section
    assert "advisory `derived_execution_head`" in section
    assert "`missing_continuity_handoff_file` is a repair blocker" in section
    assert "disables quick resume" in section
    assert "separate candidate" in section
    assert "recovery ladder" in section


def test_resume_routing_next_up_examples_have_one_primary() -> None:
    text = workflow_authority_text(WORKFLOWS_DIR, "resume-work")
    blocks = re.findall(r"## > Next Up(?P<body>.*?)(?=\n\s*---\n\s*```|\Z)", text, flags=re.S)

    assert blocks
    for block in blocks:
        assert len(re.findall(r"^\s*Primary\s+\w+:", block, flags=re.M)) == 1
        assert "Primary runtime:" in block
        assert "`gpd:execute-phase" in block or "`gpd:plan-phase" in block


def test_init_resume_invokes_resume_context(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str | None] = []

    def fake_init_resume(cwd: Path, *, stage: str | None = None) -> dict[str, object]:
        calls.append(stage)
        return {"stage": stage}

    monkeypatch.setattr("gpd.core.context.init_resume", fake_init_resume)

    result = RUNNER.invoke(app, ["--raw", "init", "resume", "--stage", "resume_bootstrap"])

    assert result.exit_code == 0
    assert calls == ["resume_bootstrap"]
    assert json.loads(result.output)["stage"] == "resume_bootstrap"


def test_init_resume_work_alias_delegates_to_resume() -> None:
    expected = RUNNER.invoke(app, ["--raw", "init", "resume", "--stage", "resume_bootstrap"])
    result = RUNNER.invoke(app, ["--raw", "init", "resume-work", "--stage", "resume_bootstrap"])

    assert expected.exit_code == 0
    assert result.exit_code == 0
    assert json.loads(result.output) == json.loads(expected.output)
