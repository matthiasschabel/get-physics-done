"""Focused assertions for the execute-phase re-verification seam."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from gpd.core.handoff_artifacts import validate_handoff_artifacts_markdown
from tests.assertion_taxonomy_support import MatchMode, assert_prompt_contracts, machine_exact, semantic_anchor
from tests.return_skeleton_support import render_gpd_return_block

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
EXECUTE_PHASE_STAGE_DIR = WORKFLOWS_DIR / "execute-phase"


def _read(name: str) -> str:
    return (WORKFLOWS_DIR / name).read_text(encoding="utf-8")


def _read_execute_phase_stage(name: str) -> str:
    return (EXECUTE_PHASE_STAGE_DIR / name).read_text(encoding="utf-8")


def test_execute_phase_reverification_routes_on_typed_status_not_legacy_verifier_text() -> None:
    workflow = _read_execute_phase_stage("gap-reverification.md")

    assert "automatically re-verify only the previously unresolved targets" in workflow
    assert "`completed` + `passed`: continue to `consistency_check`" in workflow
    assert "`checkpoint`: stop and route to `gpd:resume-work`" in workflow
    assert "`blocked` / `failed`: stop and route to `gpd:verify-work {PHASE_NUMBER}`" in workflow
    assert "include files_written" in workflow
    assert "verification_status: passed | gaps_found | expert_needed | human_needed" in workflow
    assert "Return verification status: passed | gaps_found." not in workflow
    assert "Do not infer success from prose headings or untyped routing." in workflow
    assert "Do not mark the phase complete on any non-passing or malformed path." in workflow


def test_execute_phase_reverification_requires_files_written_and_disk_artifact_gate() -> None:
    workflow = _read_execute_phase_stage("gap-reverification.md")

    assert 'subagent_type="gpd-verifier"' in workflow
    assert "files_written" in workflow
    assert "VERIFICATION.md" in workflow
    assert "gpd validate handoff-artifacts - --expected '{phase_dir}/{phase_number}-VERIFICATION.md'" in workflow
    assert "--require-files-written" in workflow
    assert 'id: "gap_closure_reverification"' in workflow


def test_execute_phase_reverification_keeps_fail_closed_on_spawn_errors_and_stale_reports() -> None:
    workflow = _read_execute_phase_stage("gap-reverification.md")

    assert "malformed, missing files_written, stale report, or failed validators: fail closed" in workflow
    assert "stop without auto-looping" in workflow
    assert "Do not mark the phase complete on any non-passing or malformed path." in workflow


def test_execute_phase_gap_reverification_has_debugger_and_circuit_breaker() -> None:
    workflow = _read_execute_phase_stage("gap-reverification.md")

    assert "Spawn debugger before any second attempt." in workflow
    assert 'subagent_type="gpd-debugger"' in workflow
    assert "Maximum two verification-gap closure cycles." in workflow
    assert "Do not attempt a third automated cycle." in workflow
    assert "gpd:validate-conventions" in workflow


def test_execute_phase_consistency_check_uses_typed_return_and_file_gate() -> None:
    workflow = _read_execute_phase_stage("consistency-check.md")

    assert_prompt_contracts(
        workflow,
        machine_exact(
            "consistency check child gate machine anchors",
            (
                "gpd-consistency-checker.md",
                "<spawn_contract>",
                "expected_artifacts:",
                "{phase_dir}/CONSISTENCY-CHECK.md",
                "Return exactly one typed gpd_return envelope, include files_written",
                'id: "rapid_consistency_check"',
                "--require-files-written",
                "--fresh-after",
                "CONSISTENCY_HANDOFF_STARTED_AT",
            ),
        ),
        semantic_anchor(
            "runtime return canonical for consistency report",
            (
                "keep that envelope in the child response",
                "runtime return is canonical",
                "Do not embed or duplicate gpd_return inside the report artifact",
            ),
            match=MatchMode.CASEFOLD_NORMALIZED,
        ),
    )
    assert "Append the same typed YAML gpd_return block to the artifact before returning" not in workflow


def test_execute_phase_consistency_check_fails_closed_on_malformed_output() -> None:
    workflow = _read_execute_phase_stage("consistency-check.md")

    assert "omits `gpd_return.status`" in workflow
    assert "omits `files_written`" in workflow
    assert "returns malformed output, treat the consistency check as blocked" in workflow
    assert "Do not infer success from prose headings or untyped routing." in workflow
    assert "Do not hand-author or paste a synthetic `gpd_return`" in workflow
    assert "gpd:validate-conventions" in workflow


def test_execute_phase_consistency_report_without_embedded_return_validates_via_runtime_return(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "GPD" / "phases" / "03-conventions" / "CONSISTENCY-CHECK.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("# Consistency Check\n\nNo embedded return block.\n", encoding="utf-8")

    runtime_return = render_gpd_return_block(
        ["GPD/phases/03-conventions/CONSISTENCY-CHECK.md"],
        extra_fields={"phase_checked": "03-conventions", "checks_performed": 3, "issues_found": 0},
    )

    result = validate_handoff_artifacts_markdown(
        tmp_path,
        runtime_return,
        expected_artifacts=["GPD/phases/03-conventions/CONSISTENCY-CHECK.md"],
        allowed_roots=["GPD/phases/03-conventions"],
        required_suffixes=["CONSISTENCY-CHECK.md"],
        require_files_written=True,
        require_status="completed",
        fresh_after=datetime.now(tz=UTC) - timedelta(minutes=1),
    )

    assert result.passed is True
    assert result.mutated is False
    assert result.mutates is False
    assert result.status == "completed"
    assert result.files_written == ["GPD/phases/03-conventions/CONSISTENCY-CHECK.md"]
    assert result.checked_files == ["GPD/phases/03-conventions/CONSISTENCY-CHECK.md"]
    assert "gpd_return:" not in report_path.read_text(encoding="utf-8")


def test_execute_phase_consistency_stops_render_from_stage_stop_routes() -> None:
    workflow = _read_execute_phase_stage("consistency-check.md")

    assert "For every consistency-check stop, populate `stage_stop` before rendering." in workflow
    assert "| checker spawn/error | `blocked` | `consistency_checker_unavailable`" in workflow
    assert "| checker checkpoint | `checkpoint` | `consistency_checker_checkpoint`" in workflow
    assert "| checker blocked | `blocked` | `consistency_checker_blocked`" in workflow
    assert "| checker failed | `failed` | `consistency_checker_failed`" in workflow
    assert "| malformed output | `blocked` | `consistency_checker_malformed_output`" in workflow
    assert "Primary: `{stage_stop.next_runtime_command}`" in workflow
