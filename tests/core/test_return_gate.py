"""Focused tests for the shared return-gate facade."""

from __future__ import annotations

from gpd.core.return_contract import validate_gpd_return_markdown
from gpd.core.return_gate import (
    ReturnGateFailureClass,
    return_gate_from_repair_classification,
    return_gate_from_validation_result,
    validate_return_gate_markdown,
)
from gpd.core.return_repair_classifier import classify_gpd_return_repair


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


def _valid_checkpoint_return() -> str:
    return _wrap_return_block(
        "  status: checkpoint\n"
        "  files_written: []\n"
        "  issues: []\n"
        "  next_actions: [gpd resume-work]\n"
        "  duration_seconds: 1\n"
    )


def _scalar_list_drift_return() -> str:
    return _wrap_return_block(
        "  status: completed\n  files_written: GPD/phases/01-test/SUMMARY.md\n  issues: []\n  next_actions: []\n"
    )


def test_missing_and_malformed_returns_are_non_mutating() -> None:
    missing = validate_return_gate_markdown("# Summary\n\nNo machine-readable return here.\n")
    malformed = validate_return_gate_markdown(_scalar_list_drift_return())

    assert missing.passed is False
    assert missing.primary_failure_class == ReturnGateFailureClass.RETURN_MISSING
    assert missing.mutates is False
    assert missing.mutated is False
    assert missing.safe_to_apply is False

    assert malformed.passed is False
    assert malformed.primary_failure_class == ReturnGateFailureClass.RETURN_MALFORMED_REPAIRABLE
    assert malformed.failures[0].code == "scalar_list_drift"
    assert malformed.mutates is False
    assert malformed.mutated is False
    assert malformed.safe_to_apply is False


def test_completed_status_passes_return_gate() -> None:
    result = validate_return_gate_markdown(_valid_completed_return())

    assert result.passed is True
    assert result.accepted is True
    assert result.schema_valid is True
    assert result.status_accepted is True
    assert result.accepted_for_success is True
    assert result.safe_to_apply is True
    assert result.status == "completed"
    assert result.required_status == "completed"
    assert result.primary_failure_class is None
    assert result.failure_classes == []
    assert result.failures == []
    assert result.files_written == ["GPD/phases/01-test/SUMMARY.md"]
    assert result.mutates is False
    assert result.mutated is False


def test_required_status_mismatch_is_consistent_between_validation_and_repair_conversion() -> None:
    content = _valid_checkpoint_return()
    validation_gate = return_gate_from_validation_result(
        validate_gpd_return_markdown(content),
        required_status="completed",
    )
    repair_gate = return_gate_from_repair_classification(
        classify_gpd_return_repair(content, require_status="completed")
    )

    for result in (validation_gate, repair_gate):
        assert result.passed is False
        assert result.accepted is False
        assert result.schema_valid is True
        assert result.status_accepted is False
        assert result.status == "checkpoint"
        assert result.required_status == "completed"
        assert result.primary_failure_class == ReturnGateFailureClass.RETURN_MALFORMED_BLOCKING
        assert result.failure_classes == [ReturnGateFailureClass.RETURN_MALFORMED_BLOCKING]
        assert result.failures[0].code == "required_status_mismatch"
        assert result.failures[0].stage == "status"
        assert result.mutates is False
        assert result.mutated is False


def test_repair_conversion_preserves_existing_failure_classes() -> None:
    repair_result = classify_gpd_return_repair(_scalar_list_drift_return())
    gate_result = return_gate_from_repair_classification(repair_result)

    assert repair_result.failure_classes == ["scalar_list_drift"]
    assert gate_result.source_failure_classes == repair_result.failure_classes
    assert gate_result.primary_class == repair_result.primary_class
    assert gate_result.primary_classification == repair_result.primary_classification
    assert gate_result.failures[0].code == "scalar_list_drift"
    assert gate_result.failures[0].source_class == "scalar_list_drift"
    assert gate_result.primary_failure_class == ReturnGateFailureClass.RETURN_MALFORMED_REPAIRABLE
