"""Focused tests for read-only ``gpd_return`` repair classification."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gpd.core.return_repair_classifier import classify_gpd_return_repair
from gpd.core.state import default_state_dict, generate_state_markdown


def _wrap_return_block(yaml_body: str) -> str:
    return f"# Child output\n\n```yaml\ngpd_return:\n{yaml_body}```\n"


def _valid_completed_return() -> str:
    return _wrap_return_block(
        "  status: completed\n"
        "  files_written: [GPD/phases/01-test/SUMMARY.md]\n"
        "  issues: []\n"
        "  next_actions: []\n"
        "  duration_seconds: 1\n"
    )


def test_classifies_valid_completed_return_as_accepted_without_mutation() -> None:
    result = classify_gpd_return_repair(_valid_completed_return())

    assert result.valid is True
    assert result.accepted_for_success is True
    assert result.primary_class == "valid"
    assert result.primary_failure_class == "valid"
    assert result.failure_classes == []
    assert result.recovery_route == "accept"
    assert result.status == "completed"
    assert result.original_errors == []
    assert result.original_warnings == []
    assert result.mutated is False
    assert result.mutates is False
    assert result.may_patch_child_return is False


def test_classifies_plain_prose_without_candidate_as_missing_block() -> None:
    result = classify_gpd_return_repair("# Summary\n\nNo machine-readable return here.\n")

    assert result.primary_class == "missing_block"
    assert result.recovery_route == "retry_child"
    assert result.original_errors == ["No gpd_return YAML block found"]


@pytest.mark.parametrize(
    "content",
    [
        ("gpd_return:\n  status: completed\n  files_written: []\n  issues: []\n  next_actions: []\n"),
        ("status: completed\nfiles_written: []\nissues: []\nnext_actions: []\n"),
        json.dumps(
            {
                "gpd_return": {
                    "status": "completed",
                    "files_written": [],
                    "issues": [],
                    "next_actions": [],
                }
            }
        ),
    ],
)
def test_classifies_unfenced_raw_yaml_or_json_candidate(content: str) -> None:
    result = classify_gpd_return_repair(content)

    assert result.primary_class == "unfenced_candidate"
    assert result.repair_hint.startswith("Retry with the candidate return wrapped")


def test_classifies_wrong_language_fenced_json_candidate() -> None:
    result = classify_gpd_return_repair(
        '```json\n{"gpd_return": {"status": "completed", "files_written": [], "issues": [], "next_actions": []}}\n```'
    )

    assert result.primary_class == "wrong_fence_language"
    assert result.recovery_route == "retry_child"


def test_classifies_yaml_parse_error_inside_canonical_block() -> None:
    result = classify_gpd_return_repair("```yaml\ngpd_return:\n  status: [completed\n```\n")

    assert result.primary_class == "yaml_parse_error"
    assert any("YAML parse error" in error for error in result.original_errors)


@pytest.mark.parametrize(
    "content",
    [
        "```yaml\nstatus: completed\nfiles_written: []\nissues: []\nnext_actions: []\n```\n",
        "```yaml\ngpd_return:\n  - status: completed\n```\n",
    ],
)
def test_classifies_top_level_shape_errors(content: str) -> None:
    result = classify_gpd_return_repair(content)

    assert result.primary_class == "top_level_shape_error"


def test_classifies_missing_required_fields() -> None:
    result = classify_gpd_return_repair(_wrap_return_block("  status: completed\n"))

    assert result.primary_class == "missing_required_fields"
    assert set(result.original_errors) >= {
        "Missing required field: files_written",
        "Missing required field: issues",
        "Missing required field: next_actions",
    }


@pytest.mark.parametrize("status", ["COMPLETED", "done"])
def test_classifies_invalid_and_uppercase_status(status: str) -> None:
    result = classify_gpd_return_repair(
        _wrap_return_block(f"  status: {status}\n  files_written: []\n  issues: []\n  next_actions: []\n")
    )

    assert result.primary_class == "invalid_status"


def test_classifies_scalar_list_drift() -> None:
    result = classify_gpd_return_repair(
        _wrap_return_block(
            "  status: completed\n  files_written: GPD/phases/01-test/SUMMARY.md\n  issues: []\n  next_actions: []\n"
        )
    )

    assert result.primary_class == "scalar_list_drift"
    assert "list" in result.original_errors[0]


def test_classifies_unknown_typo_field() -> None:
    result = classify_gpd_return_repair(
        _wrap_return_block(
            "  status: completed\n"
            "  file_written: [GPD/phases/01-test/SUMMARY.md]\n"
            "  files_written: [GPD/phases/01-test/SUMMARY.md]\n"
            "  issues: []\n"
            "  next_actions: []\n"
        )
    )

    assert result.primary_class == "unknown_field"
    assert "file_written" in result.original_errors[0]


def test_classifies_status_forbidden_fields_as_blocking() -> None:
    result = classify_gpd_return_repair(
        _wrap_return_block(
            "  status: blocked\n"
            "  files_written: []\n"
            "  issues: [waiting]\n"
            "  next_actions: []\n"
            "  state_updates:\n"
            "    advance_plan: true\n"
        )
    )

    assert result.primary_class == "status_field_forbidden"
    assert result.recovery_route == "block_and_surface_errors"


def test_classifies_transport_payload_inside_continuation_update() -> None:
    result = classify_gpd_return_repair(
        _wrap_return_block(
            "  status: checkpoint\n"
            "  files_written: []\n"
            "  issues: []\n"
            "  next_actions: []\n"
            "  continuation_update:\n"
            "    execution_segment:\n"
            "      current_cursor: 3\n"
        )
    )

    assert result.primary_class == "transport_payload_in_return"
    assert result.recovery_route == "block_and_surface_errors"


def test_classifies_applicator_owned_metadata_inside_child_return() -> None:
    result = classify_gpd_return_repair(
        _wrap_return_block(
            "  status: checkpoint\n"
            "  files_written: []\n"
            "  issues: []\n"
            "  next_actions: []\n"
            "  continuation_update:\n"
            "    bounded_segment:\n"
            "      resume_file: GPD/phases/01-test/.continue-here.md\n"
            "      segment_status: paused\n"
            "      updated_at: 2026-05-08T12:00:00Z\n"
            "      recorded_by: execute-plan\n"
        )
    )

    assert result.primary_class == "applicator_owned_metadata"
    assert result.recovery_route == "block_and_surface_errors"


def test_classifies_continuation_schema_error() -> None:
    result = classify_gpd_return_repair(
        _wrap_return_block(
            "  status: checkpoint\n"
            "  files_written: []\n"
            "  issues: []\n"
            "  next_actions: []\n"
            "  continuation_update: checkpoint\n"
        )
    )

    assert result.primary_class == "continuation_schema_error"
    assert result.recovery_route == "block_and_surface_errors"


def test_classifies_valid_non_completed_return_without_treating_it_as_malformed() -> None:
    result = classify_gpd_return_repair(
        _wrap_return_block(
            "  status: checkpoint\n  files_written: []\n  issues: []\n  next_actions: [gpd resume-work]\n"
        )
    )

    assert result.valid is True
    assert result.accepted_for_success is False
    assert result.primary_class == "valid_non_completed"
    assert result.recovery_route == "route_by_status"
    assert result.status == "checkpoint"
    assert result.original_errors == []


def test_can_accept_non_completed_status_when_required() -> None:
    result = classify_gpd_return_repair(
        _wrap_return_block(
            "  status: checkpoint\n  files_written: []\n  issues: []\n  next_actions: [gpd resume-work]\n"
        ),
        require_status="checkpoint",
    )

    assert result.primary_class == "valid"
    assert result.accepted_for_success is True


def test_classifies_multiple_canonical_blocks_as_ambiguous() -> None:
    result = classify_gpd_return_repair(_valid_completed_return() + "\n" + _valid_completed_return())

    assert result.primary_class == "ambiguous_multiple_returns"
    assert result.valid is False
    assert result.accepted_for_success is False


def test_classifier_does_not_write_state_files(tmp_path: Path) -> None:
    gpd_dir = tmp_path / "GPD"
    gpd_dir.mkdir()
    state_path = gpd_dir / "state.json"
    state_md_path = gpd_dir / "STATE.md"
    state = default_state_dict()
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    state_md_path.write_text(generate_state_markdown(state), encoding="utf-8")
    before_json = state_path.read_text(encoding="utf-8")
    before_md = state_md_path.read_text(encoding="utf-8")

    result = classify_gpd_return_repair(_valid_completed_return())

    assert result.mutated is False
    assert result.mutates is False
    assert state_path.read_text(encoding="utf-8") == before_json
    assert state_md_path.read_text(encoding="utf-8") == before_md


def test_invalid_required_status_is_rejected_before_classification() -> None:
    with pytest.raises(ValueError, match="required status"):
        classify_gpd_return_repair(_valid_completed_return(), require_status="done")
