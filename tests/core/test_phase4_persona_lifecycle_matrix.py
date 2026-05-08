"""Provider-free Phase 4 persona lifecycle failure matrix."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from gpd.command_labels import runtime_public_command_prefixes
from gpd.core.child_return_application import ApplyChildReturnResult
from gpd.core.command_run_hints import build_command_run_hint
from gpd.core.commands import cmd_apply_return_updates
from gpd.core.handoff_artifacts import validate_handoff_artifacts_markdown
from gpd.core.phase_closeout import phase_closeout_readiness
from gpd.core.return_repair_classifier import classify_gpd_return_repair
from gpd.core.state import default_state_dict, generate_state_markdown, state_record_verification


@dataclass(frozen=True)
class PersonaMatrixRow:
    row_id: str
    scenario: str
    expected_finding: str
    provider_launch_allowed: bool = False
    expected_accepted: bool = False
    expect_no_mutation: bool = True
    expected_state_status: str | None = None
    expected_next_action: str | None = None


@dataclass(frozen=True)
class PersonaMatrixOutcome:
    finding_id: str
    accepted: bool
    mutated: bool = False
    provider_launch_allowed: bool = False
    failure_classes: tuple[str, ...] = ()
    state_status: str | None = None
    next_action: str | None = None


_MATRIX_ROWS = (
    PersonaMatrixRow("P4-F-01", "invalid_gpd_verify_work", "invalid_verify_command_surface"),
    PersonaMatrixRow("P4-F-02", "structural_verify_phase", "invalid_verify_command_surface"),
    PersonaMatrixRow("P4-F-03", "prose_success_no_return", "return_missing"),
    PersonaMatrixRow("P4-F-04", "multiple_returns", "return_malformed_blocking"),
    PersonaMatrixRow("P4-F-05", "unfenced_return", "unfenced_candidate"),
    PersonaMatrixRow("P4-F-06", "missing_files_written", "artifact_missing"),
    PersonaMatrixRow("P4-F-07", "stale_files_written", "artifact_stale"),
    PersonaMatrixRow("P4-F-08", "applicator_output_only", "applicator_output_only"),
    PersonaMatrixRow("P4-F-09", "checkpoint_missing_bounded_context", "checkpoint_missing_bounded_segment"),
    PersonaMatrixRow(
        "P4-F-10",
        "nonpassing_verification_called_complete",
        "nonpassing_verification_called_complete",
        expect_no_mutation=False,
        expected_state_status="Blocked",
    ),
    PersonaMatrixRow(
        "P4-F-11",
        "bounded_segment_bypass",
        "bounded_segment_bypass",
        expected_next_action="gpd:resume-work",
    ),
)


def _return_block(files_written: list[str], *, status: str = "completed", extra: str = "") -> str:
    if files_written:
        files_yaml = "  files_written:\n" + "".join(f"    - {json.dumps(path)}\n" for path in files_written)
    else:
        files_yaml = "  files_written: []\n"
    return (
        "```yaml\n"
        "gpd_return:\n"
        f"  status: {status}\n"
        f"{files_yaml}"
        "  issues: []\n"
        "  next_actions: []\n"
        f"{extra}"
        "```\n"
    )


def _write_phase_project(
    root: Path,
    *,
    status: str = "Ready to execute",
    verification_status: str | None = None,
    bounded_segment: bool = False,
) -> Path:
    gpd_dir = root / "GPD"
    phase_dir = gpd_dir / "phases" / "02-analysis"
    phase_dir.mkdir(parents=True)
    (gpd_dir / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
    (gpd_dir / "ROADMAP.md").write_text("# Roadmap\n\n## Phase 2: Analysis\n", encoding="utf-8")
    for index in range(1, 3):
        (phase_dir / f"02-{index:02d}-PLAN.md").write_text(f"# Plan {index}\n", encoding="utf-8")
        (phase_dir / f"02-{index:02d}-SUMMARY.md").write_text(f"# Summary {index}\n", encoding="utf-8")
    if verification_status is not None:
        (phase_dir / "02-VERIFICATION.md").write_text(
            "---\n"
            f"status: {verification_status}\n"
            "score: persona matrix\n"
            "---\n\n"
            "# Verification\n",
            encoding="utf-8",
        )

    state = default_state_dict()
    state["position"]["current_phase"] = "02"
    state["position"]["current_phase_name"] = "Analysis"
    state["position"]["current_plan"] = "2"
    state["position"]["total_plans_in_phase"] = 2
    state["position"]["total_phases"] = 2
    state["position"]["status"] = status
    if bounded_segment:
        state["continuation"]["bounded_segment"] = {
            "resume_file": "GPD/phases/02-analysis/.continue-here.md",
            "phase": "02",
            "plan": "02",
            "segment_id": "seg-02-02",
            "segment_status": "paused",
            "waiting_for_review": True,
        }
    (gpd_dir / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    (gpd_dir / "STATE.md").write_text(generate_state_markdown(state), encoding="utf-8")
    return phase_dir


def _public_runtime_verify_work(command: str) -> bool:
    command_token = command.strip().split(maxsplit=1)[0]
    return any(command_token == f"{prefix}verify-work" for prefix in runtime_public_command_prefixes())


def _score_command_surface(command: str) -> PersonaMatrixOutcome:
    hint = build_command_run_hint(command=command, source="phase4-persona-matrix", action="verify-work", phase="02")
    if hint is None or not _public_runtime_verify_work(command):
        return PersonaMatrixOutcome(
            finding_id="invalid_verify_command_surface",
            accepted=False,
            failure_classes=("invalid_verify_command_surface", str((hint or {}).get("kind", "no_hint"))),
        )
    return PersonaMatrixOutcome(finding_id="valid_verify_command_surface", accepted=True)


def _score_apply_return_failure(root: Path, content: str) -> PersonaMatrixOutcome:
    _write_phase_project(root)
    report = root / "GPD" / "phases" / "02-analysis" / "PERSONA-RETURN.md"
    report.write_text(content, encoding="utf-8")
    state_path = root / "GPD" / "state.json"
    state_before = state_path.read_text(encoding="utf-8")

    result = cmd_apply_return_updates(root, report)

    assert state_path.read_text(encoding="utf-8") == state_before
    return PersonaMatrixOutcome(
        finding_id=str(result.primary_failure_class),
        accepted=result.passed,
        mutated=result.mutated,
        failure_classes=tuple(str(failure_class) for failure_class in result.failure_classes),
    )


def _score_unfenced_return() -> PersonaMatrixOutcome:
    result = classify_gpd_return_repair(
        "gpd_return:\n"
        "  status: completed\n"
        "  files_written: []\n"
        "  issues: []\n"
        "  next_actions: []\n"
    )
    return PersonaMatrixOutcome(
        finding_id=result.primary_class,
        accepted=result.accepted_for_success,
        failure_classes=tuple(result.failure_classes),
    )


def _score_missing_files_written(root: Path) -> PersonaMatrixOutcome:
    artifact = root / "GPD" / "phases" / "02-analysis" / "02-02-SUMMARY.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("# Summary\n", encoding="utf-8")

    result = validate_handoff_artifacts_markdown(
        root,
        _return_block([]),
        expected_artifacts=["GPD/phases/02-analysis/02-02-SUMMARY.md"],
        allowed_roots=["GPD/phases/02-analysis"],
        required_suffixes=["-SUMMARY.md"],
        require_files_written=True,
    )

    assert {"files_written_empty", "expected_artifact_omitted"} <= {failure.code for failure in result.failures}
    return PersonaMatrixOutcome(
        finding_id=str(result.primary_failure_class),
        accepted=result.passed,
        mutated=result.mutated,
        failure_classes=tuple(str(failure_class) for failure_class in result.failure_classes),
    )


def _score_stale_files_written(root: Path) -> PersonaMatrixOutcome:
    artifact = root / "GPD" / "phases" / "02-analysis" / "02-02-SUMMARY.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("# Summary\n", encoding="utf-8")
    stale_time = datetime.now(tz=UTC) - timedelta(hours=2)
    os.utime(artifact, (stale_time.timestamp(), stale_time.timestamp()))

    result = validate_handoff_artifacts_markdown(
        root,
        _return_block(["GPD/phases/02-analysis/02-02-SUMMARY.md"]),
        allowed_roots=["GPD/phases/02-analysis"],
        required_suffixes=["-SUMMARY.md"],
        fresh_after=datetime.now(tz=UTC) - timedelta(minutes=1),
    )

    assert {failure.code for failure in result.failures} == {"artifact_stale"}
    return PersonaMatrixOutcome(
        finding_id=str(result.primary_failure_class),
        accepted=result.passed,
        mutated=result.mutated,
        failure_classes=tuple(str(failure_class) for failure_class in result.failure_classes),
    )


def _score_applicator_output_only() -> PersonaMatrixOutcome:
    applicator_payload = {
        "passed": True,
        "status": "completed",
        "mutated": True,
        "files_written": ["GPD/phases/02-analysis/02-02-SUMMARY.md"],
        "applied_state_operations": ["advance_plan:last_plan"],
    }
    parsed = ApplyChildReturnResult.model_validate(applicator_payload)
    return_check = classify_gpd_return_repair(json.dumps(applicator_payload))

    assert parsed.passed is True
    assert return_check.primary_class == "missing_block"
    return PersonaMatrixOutcome(
        finding_id="applicator_output_only",
        accepted=False,
        failure_classes=("applicator_output_only", return_check.primary_class),
    )


def _score_checkpoint_missing_bounded_context(root: Path) -> PersonaMatrixOutcome:
    _write_phase_project(root)
    report = root / "GPD" / "phases" / "02-analysis" / "CHECKPOINT.md"
    report.write_text(
        _return_block(
            ["GPD/state.json"],
            status="checkpoint",
            extra='  phase: "02"\n  plan: "02"\n',
        ),
        encoding="utf-8",
    )
    state_path = root / "GPD" / "state.json"
    state_before = state_path.read_text(encoding="utf-8")

    result = cmd_apply_return_updates(root, report)

    assert result.primary_failure_class == "applicator_failed"
    assert any("continuation_update.bounded_segment.resume_file" in error for error in result.errors)
    assert state_path.read_text(encoding="utf-8") == state_before
    return PersonaMatrixOutcome(
        finding_id="checkpoint_missing_bounded_segment",
        accepted=False,
        mutated=result.mutated,
        failure_classes=("checkpoint_missing_bounded_segment", *tuple(result.failure_classes)),
    )


def _score_nonpassing_verification_called_complete(root: Path) -> PersonaMatrixOutcome:
    _write_phase_project(
        root,
        status="Phase complete \u2014 ready for verification",
        verification_status="gaps_found",
    )

    record_result = state_record_verification(root, phase="02")
    closeout = phase_closeout_readiness(root, "02", require_verification=True)

    assert record_result.recorded is True
    assert closeout.ready is False
    assert closeout.verification_status == "gaps_found"
    return PersonaMatrixOutcome(
        finding_id="nonpassing_verification_called_complete",
        accepted=False,
        mutated=True,
        failure_classes=("nonpassing_verification_called_complete", "verification_not_passing"),
        state_status=record_result.status,
    )


def _score_bounded_segment_bypass(root: Path) -> PersonaMatrixOutcome:
    _write_phase_project(root, verification_status="passed", bounded_segment=True)
    before_state = (root / "GPD" / "state.json").read_text(encoding="utf-8")

    result = phase_closeout_readiness(root, "02", require_verification=True)

    assert result.ready is False
    assert result.active_bounded_segment is True
    assert (root / "GPD" / "state.json").read_text(encoding="utf-8") == before_state
    return PersonaMatrixOutcome(
        finding_id="bounded_segment_bypass",
        accepted=False,
        failure_classes=("bounded_segment_bypass",),
        next_action=str(result.next_up["primary"]),
    )


def _score_row(row: PersonaMatrixRow, root: Path) -> PersonaMatrixOutcome:
    match row.scenario:
        case "invalid_gpd_verify_work":
            return _score_command_surface("gpd-verify-work 02")
        case "structural_verify_phase":
            return _score_command_surface("gpd verify phase 02")
        case "prose_success_no_return":
            return _score_apply_return_failure(root, "# Result\n\nDone. Verified. Ready to continue.\n")
        case "multiple_returns":
            completed = _return_block(["GPD/phases/02-analysis/02-02-SUMMARY.md"])
            blocked = _return_block([], status="blocked", extra="  blockers:\n    - conflicting status\n")
            return _score_apply_return_failure(root, completed + "\n" + blocked)
        case "unfenced_return":
            return _score_unfenced_return()
        case "missing_files_written":
            return _score_missing_files_written(root)
        case "stale_files_written":
            return _score_stale_files_written(root)
        case "applicator_output_only":
            return _score_applicator_output_only()
        case "checkpoint_missing_bounded_context":
            return _score_checkpoint_missing_bounded_context(root)
        case "nonpassing_verification_called_complete":
            return _score_nonpassing_verification_called_complete(root)
        case "bounded_segment_bypass":
            return _score_bounded_segment_bypass(root)
    raise AssertionError(f"unhandled matrix scenario: {row.scenario}")


def test_phase4_persona_lifecycle_matrix_rows_are_provider_free_and_class_only() -> None:
    assert len(_MATRIX_ROWS) == 11
    assert all(row.provider_launch_allowed is False for row in _MATRIX_ROWS)
    assert {row.expected_finding for row in _MATRIX_ROWS} >= {
        "invalid_verify_command_surface",
        "return_missing",
        "artifact_stale",
        "checkpoint_missing_bounded_segment",
        "bounded_segment_bypass",
    }


@pytest.mark.parametrize("row", _MATRIX_ROWS, ids=lambda row: f"{row.row_id}-{row.scenario}")
def test_phase4_persona_lifecycle_matrix(row: PersonaMatrixRow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GPD_DATA_DIR", str(tmp_path / ".gpd-data"))

    outcome = _score_row(row, tmp_path)

    assert outcome.provider_launch_allowed is False
    assert outcome.finding_id == row.expected_finding
    assert row.expected_finding in outcome.failure_classes
    assert outcome.accepted is row.expected_accepted
    if row.expect_no_mutation:
        assert outcome.mutated is False
    if row.expected_state_status is not None:
        assert outcome.state_status == row.expected_state_status
    if row.expected_next_action is not None:
        assert outcome.next_action == row.expected_next_action
