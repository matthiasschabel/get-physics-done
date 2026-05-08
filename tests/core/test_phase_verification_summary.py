"""Focused tests for the phase verification summary helper."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from gpd.cli import app
from gpd.core.phase_verification_summary import build_phase_verification_summary

RUNNER = CliRunner()


def _phase_dir(root: Path) -> Path:
    phase_dir = root / "GPD" / "phases" / "01-demo"
    phase_dir.mkdir(parents=True, exist_ok=True)
    return phase_dir


def _write_plan(phase_dir: Path, name: str, *, wave: int = 1, body: str = "Do work.") -> None:
    phase_dir.joinpath(name).write_text(
        "---\n"
        f"wave: {wave}\n"
        "depends_on: []\n"
        "files_modified: []\n"
        "---\n\n"
        "## Task 1\n"
        f"{body}\n",
        encoding="utf-8",
    )


def _write_summary(phase_dir: Path, name: str, *, plan: str, body: str = "# Summary\n") -> None:
    phase_dir.joinpath(name).write_text(
        "---\n"
        'phase: "01"\n'
        f'plan: "{plan}"\n'
        "depth: standard\n"
        "provides: []\n"
        'completed: "2026-05-08"\n'
        f"one-liner: Completed {plan}\n"
        "---\n\n"
        f"{body}\n",
        encoding="utf-8",
    )


def test_wave_summary_lists_exact_wave_plans(tmp_path: Path) -> None:
    phase_dir = _phase_dir(tmp_path)
    _write_plan(phase_dir, "a-PLAN.md", wave=1)
    _write_plan(phase_dir, "b-PLAN.md", wave=2)
    _write_summary(phase_dir, "a-SUMMARY.md", plan="a")
    _write_summary(phase_dir, "b-SUMMARY.md", plan="b")

    result = build_phase_verification_summary(tmp_path, "1", wave=1)

    assert result.structural_valid is True
    assert result.scope == "wave"
    assert result.wave == 1
    assert result.plan_ids == ["a"]
    assert [summary.plan_id for summary in result.summaries] == ["a"]
    assert result.summary_count == 1
    assert result.routing == "pass"


def test_missing_summary_blocks_routing(tmp_path: Path) -> None:
    phase_dir = _phase_dir(tmp_path)
    _write_plan(phase_dir, "a-PLAN.md", wave=1)

    result = build_phase_verification_summary(tmp_path, "01", wave=1)

    assert result.routing == "blocked"
    assert result.missing_summary_files == ["GPD/phases/01-demo/a-SUMMARY.md"]
    assert any("Missing summary for plan a" in blocker for blocker in result.blockers)


def test_malformed_summary_frontmatter_blocks_with_path(tmp_path: Path) -> None:
    phase_dir = _phase_dir(tmp_path)
    _write_plan(phase_dir, "a-PLAN.md", wave=1)
    (phase_dir / "a-SUMMARY.md").write_text("---\nphase: [\n---\nBody\n", encoding="utf-8")

    result = build_phase_verification_summary(tmp_path, "01", wave=1)

    assert result.routing == "blocked"
    assert result.summary_validation_failures[0]["path"] == "GPD/phases/01-demo/a-SUMMARY.md"
    assert "a-SUMMARY.md" in result.blockers[0]


def test_nested_status_fields_do_not_override_top_level_verification_status(tmp_path: Path) -> None:
    phase_dir = _phase_dir(tmp_path)
    _write_plan(phase_dir, "a-PLAN.md", wave=1)
    _write_summary(phase_dir, "a-SUMMARY.md", plan="a")
    (phase_dir / "01-VERIFICATION.md").write_text(
        "---\n"
        'phase: "01"\n'
        'verified: "2026-05-08T00:00:00Z"\n'
        "status: passed\n"
        'score: "1/1"\n'
        "---\n\n"
        "contract_results:\n"
        "  claims:\n"
        "    c1:\n"
        "      status: gaps_found\n",
        encoding="utf-8",
    )

    result = build_phase_verification_summary(tmp_path, "1", all_waves=True)

    assert result.verification_report_status is not None
    assert result.verification_report_status["status"] == "passed"
    assert result.verification_report_status["routing_status"] == "passed"
    assert result.checks["verification_report"] == "pass"
    assert result.routing == "pass"


def test_proof_bearing_plan_without_passed_redteam_blocks(tmp_path: Path) -> None:
    phase_dir = _phase_dir(tmp_path)
    _write_plan(phase_dir, "a-PLAN.md", wave=1, body="proof_obligation: prove the theorem.")
    _write_summary(phase_dir, "a-SUMMARY.md", plan="a")

    missing = build_phase_verification_summary(tmp_path, "01", wave=1)

    assert missing.routing == "blocked"
    assert missing.proof_redteam.required is True
    assert missing.proof_redteam.missing == ["GPD/phases/01-demo/a-PROOF-REDTEAM.md"]

    (phase_dir / "a-PROOF-REDTEAM.md").write_text(
        "---\nstatus: gaps_found\n---\n\n# Proof audit\n",
        encoding="utf-8",
    )

    open_result = build_phase_verification_summary(tmp_path, "01", wave=1)

    assert open_result.routing == "blocked"
    assert open_result.proof_redteam.open == ["GPD/phases/01-demo/a-PROOF-REDTEAM.md"]


def test_optional_warning_categories_do_not_turn_into_passed_claims(tmp_path: Path) -> None:
    phase_dir = _phase_dir(tmp_path)
    _write_plan(phase_dir, "a-PLAN.md", wave=1)
    _write_summary(
        phase_dir,
        "a-SUMMARY.md",
        plan="a",
        body="# Summary\n\nIDENTITY_SOURCE: training_data\n",
    )

    result = build_phase_verification_summary(tmp_path, "01", wave=1)

    assert result.checks["identity"] == "warning"
    assert result.routing == "warning"
    assert result.recommended_next_action.startswith("Review warnings")


def test_phase_verification_summary_cli_emits_raw_json(tmp_path: Path) -> None:
    phase_dir = _phase_dir(tmp_path)
    _write_plan(phase_dir, "a-PLAN.md", wave=1)
    _write_summary(phase_dir, "a-SUMMARY.md", plan="a")

    result = RUNNER.invoke(
        app,
        ["--raw", "--cwd", str(tmp_path), "phase", "verification-summary", "01", "--wave", "1"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["phase"] == "01"
    assert payload["scope"] == "wave"
    assert payload["plan_ids"] == ["a"]
    assert payload["routing"] == "pass"
