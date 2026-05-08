"""Focused assertions for the execute-phase re-verification seam."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
EXECUTE_PHASE_STAGE_DIR = WORKFLOWS_DIR / "execute-phase"


def _read(name: str) -> str:
    return (WORKFLOWS_DIR / name).read_text(encoding="utf-8")


def _read_execute_phase_stage(name: str) -> str:
    return (EXECUTE_PHASE_STAGE_DIR / name).read_text(encoding="utf-8")


def test_execute_phase_reverification_routes_on_typed_status_not_legacy_verifier_text() -> None:
    workflow = _read_execute_phase_stage("aggregate-and-verify.md")

    assert "Automatically re-verify the phase to confirm gaps are closed:" in workflow
    assert "gpd_return.status: completed" in workflow
    assert "gpd_return.status: checkpoint" in workflow
    assert "gpd_return.status: blocked" in workflow
    assert "gpd_return.status: failed" in workflow
    assert "include `files_written`" in workflow
    assert "verification_status: passed | gaps_found | expert_needed | human_needed" in workflow
    assert "Verifier status route: passed verdict updates roadmap; non-passing verdict reports remaining gaps without auto-looping." in workflow
    assert "Return verification status: passed | gaps_found." not in workflow
    assert "bare `passed | gaps_found` text as the routing surface" in workflow
    assert "Do not infer success from prose headings or untyped routing." in workflow
    assert "Spawn/error, malformed output, failed tuple, or non-passing verifier verdict" in workflow


def test_execute_phase_reverification_requires_files_written_and_disk_artifact_gate() -> None:
    workflow = _read_execute_phase_stage("aggregate-and-verify.md")

    assert 'subagent_type="gpd-verifier"' in workflow
    assert "files_written" in workflow
    assert "VERIFICATION.md" in workflow
    assert "gpd validate handoff-artifacts - --expected '{phase_dir}/{phase}-VERIFICATION.md'" in workflow
    assert "--require-files-written" in workflow
    assert "failed tuple" in workflow


def test_execute_phase_reverification_keeps_fail_closed_on_spawn_errors_and_stale_reports() -> None:
    workflow = _read_execute_phase_stage("aggregate-and-verify.md")

    assert "Spawn/error, malformed output, failed tuple, or non-passing verifier verdict keeps gap-closure state intact" in workflow
    assert "do not mark the phase complete on those paths" in workflow
    assert "non-passing verdict reports remaining gaps without auto-looping" in workflow
