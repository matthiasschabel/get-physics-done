"""Focused tests for role-aware ``gpd_return`` skeleton rendering."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from gpd.core.commands import cmd_apply_return_updates
from gpd.core.return_contract import (
    ALLOWED_RETURN_EXTENSION_FIELDS,
    REQUIRED_RETURN_FIELDS,
    RETURN_ENVELOPE_STATUS_CONTRACTS,
    VALID_RETURN_STATUSES,
    GpdReturnEnvelope,
    validate_gpd_return_markdown,
)
from gpd.core.return_skeleton import (
    APPLICATOR_OWNED_METADATA_FIELDS,
    GPD_RETURN_ROLE_PROFILES,
    KNOWN_RETURN_FIELD_NAMES,
    RETURN_STATUS_ORDER,
    build_gpd_return_skeleton,
    render_gpd_return_markdown,
    render_gpd_return_yaml,
)
from gpd.core.state import default_state_dict, generate_state_markdown


def test_return_profiles_cover_phase3_roles() -> None:
    assert set(GPD_RETURN_ROLE_PROFILES) == {
        "executor",
        "planner",
        "checker",
        "verifier",
        "referee",
        "researcher",
    }
    assert set(RETURN_STATUS_ORDER) == VALID_RETURN_STATUSES


def test_return_profile_fields_are_allowed_by_return_contract() -> None:
    known_fields = set(GpdReturnEnvelope.model_fields) | set(ALLOWED_RETURN_EXTENSION_FIELDS)
    assert KNOWN_RETURN_FIELD_NAMES == known_fields

    for profile in GPD_RETURN_ROLE_PROFILES.values():
        assert profile.required_fields == REQUIRED_RETURN_FIELDS
        for status in VALID_RETURN_STATUSES:
            assert status in profile.role_fields_by_status
            assert set(profile.role_fields_by_status[status]) <= known_fields
            assert set(profile.default_render_fields_by_status[status]) <= known_fields


def test_return_profile_status_fields_obey_status_contract() -> None:
    status_restricted_fields = {
        field_name
        for contract in RETURN_ENVELOPE_STATUS_CONTRACTS.values()
        for field_name in contract.structured_fields
    }

    for profile in GPD_RETURN_ROLE_PROFILES.values():
        for status, fields in profile.role_fields_by_status.items():
            allowed_structured = set(RETURN_ENVELOPE_STATUS_CONTRACTS[status].structured_fields)
            disallowed = sorted(set(fields).intersection(status_restricted_fields) - allowed_structured)
            assert disallowed == []

    executor = GPD_RETURN_ROLE_PROFILES["executor"]
    assert "blockers" not in executor.role_fields_by_status["completed"]
    assert "blockers" in executor.role_fields_by_status["checkpoint"]


@pytest.mark.parametrize("role", sorted(GPD_RETURN_ROLE_PROFILES))
@pytest.mark.parametrize("status", RETURN_STATUS_ORDER)
def test_return_skeleton_validates_for_each_role_status(role: str, status: str) -> None:
    skeleton = build_gpd_return_skeleton(role=role, status=status)

    result = validate_gpd_return_markdown(skeleton.markdown)

    assert result.passed is True
    assert result.fields == skeleton.envelope
    assert result.fields["status"] == status
    for field_name in REQUIRED_RETURN_FIELDS:
        assert field_name in result.fields

    payload_text = json.dumps(skeleton.model_dump(mode="json"), sort_keys=True)
    for field_name in APPLICATOR_OWNED_METADATA_FIELDS:
        assert field_name not in payload_text


def test_return_skeleton_renders_yaml_markdown_and_json_payload() -> None:
    skeleton = build_gpd_return_skeleton(
        role="planner",
        status="completed",
        files_written=("GPD/roadmap.md",),
        issues=("needs verifier review",),
        next_actions=("gpd plan-phase 01",),
        phase="01",
    )

    assert yaml.safe_load(skeleton.yaml_payload) == {"gpd_return": skeleton.envelope}
    assert render_gpd_return_yaml(skeleton.envelope) == skeleton.yaml_payload
    assert render_gpd_return_markdown(skeleton.envelope) == skeleton.markdown
    assert json.loads(skeleton.model_dump_json())["envelope"] == skeleton.envelope
    assert skeleton.envelope["files_written"] == ["GPD/roadmap.md"]
    assert skeleton.envelope["phase"] == "01"


def test_checker_checkpoint_skeleton_contains_partial_approval_fields() -> None:
    skeleton = build_gpd_return_skeleton(role="checker", status="checkpoint")

    assert skeleton.envelope["approved_plans"] == []
    assert skeleton.envelope["blocked_plans"] == []
    assert skeleton.envelope["revision_round"] == 1
    assert "blockers" in skeleton.envelope


def test_verifier_skeleton_keeps_verification_status_distinct() -> None:
    skeleton = build_gpd_return_skeleton(role="verifier", status="completed")

    assert skeleton.envelope["status"] == "completed"
    assert skeleton.envelope["verification_status"] == "gaps_found"
    assert "verified" not in skeleton.envelope


def test_return_skeleton_rejects_unknown_role_status_and_fields() -> None:
    with pytest.raises(ValueError, match="unknown gpd_return role profile"):
        build_gpd_return_skeleton(role="observer", status="completed")

    with pytest.raises(ValueError, match="unknown gpd_return status"):
        build_gpd_return_skeleton(role="executor", status="done")

    with pytest.raises(ValueError, match="unknown gpd_return field"):
        build_gpd_return_skeleton(role="executor", status="completed", extra_fields={"file_written": []})


def test_return_skeleton_rejects_status_disallowed_extra_fields() -> None:
    with pytest.raises(ValueError, match="status 'blocked' does not allow gpd_return field 'state_updates'"):
        build_gpd_return_skeleton(
            role="executor",
            status="blocked",
            extra_fields={"state_updates": {"advance_plan": True}},
        )


def test_checkpoint_applicator_fields_require_explicit_resume_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="resume_file"):
        build_gpd_return_skeleton(role="executor", status="checkpoint", include_applicator_fields=True)

    with pytest.raises(ValueError, match="existing project file"):
        build_gpd_return_skeleton(
            role="executor",
            status="checkpoint",
            include_applicator_fields=True,
            resume_file="GPD/phases/01-test-phase/.continue-here.md",
            project_root=tmp_path,
        )

    resume_file = tmp_path / "GPD" / "phases" / "01-test-phase" / ".continue-here.md"
    resume_file.parent.mkdir(parents=True)
    resume_file.write_text("resume\n", encoding="utf-8")

    skeleton = build_gpd_return_skeleton(
        role="executor",
        status="checkpoint",
        include_applicator_fields=True,
        resume_file="GPD/phases/01-test-phase/.continue-here.md",
        project_root=tmp_path,
        phase="01",
        plan="01",
    )

    bounded_segment = skeleton.envelope["continuation_update"]["bounded_segment"]
    assert bounded_segment == {
        "resume_file": "GPD/phases/01-test-phase/.continue-here.md",
        "segment_status": "paused",
        "phase": "01",
        "plan": "01",
    }
    assert skeleton.applicator_ready is True
    assert "gpd apply-return-updates <return-file.md>" in skeleton.validation_commands


def test_checkpoint_applicator_skeleton_applies_with_existing_resume_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GPD_DATA_DIR", str(tmp_path / "gpd-data"))
    gpd_dir = tmp_path / "GPD"
    gpd_dir.mkdir()
    state = default_state_dict()
    (gpd_dir / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    (gpd_dir / "STATE.md").write_text(generate_state_markdown(state), encoding="utf-8")
    resume_file = gpd_dir / "phases" / "01-test-phase" / ".continue-here.md"
    resume_file.parent.mkdir(parents=True)
    resume_file.write_text("resume\n", encoding="utf-8")

    skeleton = build_gpd_return_skeleton(
        role="executor",
        status="checkpoint",
        include_applicator_fields=True,
        resume_file="GPD/phases/01-test-phase/.continue-here.md",
        project_root=tmp_path,
        phase="01",
        plan="01",
    )
    return_file = tmp_path / "return.md"
    return_file.write_text(skeleton.markdown, encoding="utf-8")

    result = cmd_apply_return_updates(tmp_path, return_file)

    assert result.passed is True
    assert result.applied_continuation_operations == ["set_bounded_segment"]
