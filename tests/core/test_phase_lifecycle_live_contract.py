"""End-to-end phase lifecycle contracts that mirror live agent handoffs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gpd.adapters import get_adapter
from gpd.adapters.runtime_catalog import iter_runtime_descriptors
from gpd.cli import app
from gpd.core.state import default_state_dict, generate_state_markdown
from gpd.core.suggest import suggest_next
from tests.runtime_install_helpers import seed_complete_runtime_install


class _StableCliRunner(CliRunner):
    def invoke(self, *args, **kwargs):
        kwargs.setdefault("color", False)
        return super().invoke(*args, **kwargs)


RUNNER = _StableCliRunner()
_RUNTIME_NAMES = tuple(descriptor.runtime_name for descriptor in iter_runtime_descriptors())


def _write_phase_project(
    root: Path,
    *,
    phase: str = "02",
    phase_name: str = "analysis",
    current_plan: int = 2,
    total_plans: int = 2,
    status: str = "Ready to execute",
    summaries: int = 2,
) -> Path:
    gpd_dir = root / "GPD"
    phase_dir = gpd_dir / "phases" / f"{phase}-{phase_name}"
    phase_dir.mkdir(parents=True)
    (gpd_dir / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
    (gpd_dir / "ROADMAP.md").write_text(
        "# Roadmap\n\n"
        "## Phase 1: Setup\n\n"
        "## Phase 2: Analysis\n\n"
        "## Phase 3: Synthesis\n",
        encoding="utf-8",
    )
    for index in range(1, total_plans + 1):
        (phase_dir / f"{phase}-{index:02d}-PLAN.md").write_text(
            f"# Phase {phase} Plan {index:02d}\n",
            encoding="utf-8",
        )
    for index in range(1, summaries + 1):
        (phase_dir / f"{phase}-{index:02d}-SUMMARY.md").write_text(
            f"# Phase {phase} Plan {index:02d} Summary\n",
            encoding="utf-8",
        )

    state = default_state_dict()
    state["position"]["current_phase"] = phase
    state["position"]["current_phase_name"] = phase_name.title()
    state["position"]["current_plan"] = str(current_plan)
    state["position"]["total_plans_in_phase"] = total_plans
    state["position"]["total_phases"] = 3
    state["position"]["progress_percent"] = 66
    state["position"]["status"] = status
    (gpd_dir / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    (gpd_dir / "STATE.md").write_text(generate_state_markdown(state), encoding="utf-8")
    return phase_dir


def _write_completed_return(summary_path: Path, *, phase: str = "02", plan: str = "02") -> None:
    summary_path.write_text(
        "# Completed Summary\n\n"
        "```yaml\n"
        "gpd_return:\n"
        "  status: completed\n"
        f"  files_written: [{summary_path.as_posix()}]\n"
        "  issues: []\n"
        f"  next_actions: [gpd:verify-work {phase}]\n"
        f"  phase: \"{phase}\"\n"
        f"  plan: \"{plan}\"\n"
        "  tasks_completed: 1\n"
        "  tasks_total: 1\n"
        "  duration_seconds: 12\n"
        "  state_updates:\n"
        "    advance_plan: true\n"
        "    update_progress: true\n"
        "    record_metric:\n"
        f"      phase: \"{phase}\"\n"
        f"      plan: \"{plan}\"\n"
        "      duration: \"12s\"\n"
        "      tasks: \"1\"\n"
        "      files: \"1\"\n"
        "```\n",
        encoding="utf-8",
    )


def _write_gap_verification(report_path: Path) -> None:
    report_path.write_text(
        "---\n"
        "phase: 02-analysis\n"
        'verified: "2026-05-07T00:00:00Z"\n'
        "status: gaps_found\n"
        'score: "0/1 contract targets verified"\n'
        "---\n\n"
        "# Phase 02 Verification\n\n"
        "```bash\n"
        "printf 'missing benchmark evidence\\n'\n"
        "```\n\n"
        "**Output:**\n\n"
        "```output\n"
        "missing benchmark evidence\n"
        "```\n\n"
        "FAIL: benchmark evidence is absent.\n",
        encoding="utf-8",
    )


def test_apply_return_updates_completes_last_plan_from_ready_to_execute_state(tmp_path: Path) -> None:
    """A final-plan child return should not require manual Ready -> Executing repair."""
    phase_dir = _write_phase_project(tmp_path, status="Ready to execute")
    summary = phase_dir / "02-02-SUMMARY.md"
    _write_completed_return(summary)

    result = RUNNER.invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "apply-return-updates",
            "GPD/phases/02-analysis/02-02-SUMMARY.md",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["passed"] is True
    assert "advance_plan:last_plan" in payload["applied_state_operations"]
    state = json.loads((tmp_path / "GPD" / "state.json").read_text(encoding="utf-8"))
    assert state["position"]["status"] == "Phase complete \u2014 ready for verification"


def test_apply_return_updates_rejects_report_without_gpd_return_without_mutating_state(tmp_path: Path) -> None:
    phase_dir = _write_phase_project(tmp_path, status="Ready to execute")
    report = phase_dir / "CONSISTENCY-CHECK.md"
    report.write_text("# Consistency Check\n\nNo issues found.\n", encoding="utf-8")
    before_state = (tmp_path / "GPD" / "state.json").read_text(encoding="utf-8")

    result = RUNNER.invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "apply-return-updates",
            "GPD/phases/02-analysis/CONSISTENCY-CHECK.md",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["passed"] is False
    assert payload["errors"] == ["No gpd_return YAML block found"]
    assert (tmp_path / "GPD" / "state.json").read_text(encoding="utf-8") == before_state


@pytest.mark.parametrize("initial_status", ["verifying", "Phase complete \u2014 ready for verification"])
def test_record_verification_maps_gap_report_to_blocked_and_keeps_state_surfaces_in_sync(
    tmp_path: Path,
    initial_status: str,
) -> None:
    phase_dir = _write_phase_project(tmp_path, status=initial_status)
    verification_report = phase_dir / "02-VERIFICATION.md"
    _write_gap_verification(verification_report)
    before_report = verification_report.read_text(encoding="utf-8")

    result = RUNNER.invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "state",
            "record-verification",
            "--phase",
            "02",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["recorded"] is True
    assert payload["status"] == "Blocked"
    assert payload["previous_status"] == initial_status
    assert verification_report.read_text(encoding="utf-8") == before_report

    state = json.loads((tmp_path / "GPD" / "state.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / "GPD" / "STATE.md").read_text(encoding="utf-8")
    assert state["position"]["status"] == "Blocked"
    assert state["position"]["status"] != "Verified"
    assert "**Status:** Blocked" in markdown

    validation = RUNNER.invoke(app, ["--raw", "--cwd", str(tmp_path), "state", "validate"])
    assert validation.exit_code == 0, validation.output
    validation_payload = json.loads(validation.output)
    assert validation_payload["valid"] is True
    assert validation_payload["integrity_status"] == "healthy"


@pytest.mark.parametrize("runtime", _RUNTIME_NAMES)
def test_completed_phase_suggests_active_runtime_verify_work_not_structural_verify_phase(
    tmp_path: Path,
    runtime: str,
) -> None:
    adapter = get_adapter(runtime)
    seed_complete_runtime_install(tmp_path / adapter.local_config_dir_name, runtime=runtime)
    _write_phase_project(tmp_path, status="Phase complete \u2014 ready for verification", summaries=2)

    result = suggest_next(tmp_path)

    verify = next((suggestion for suggestion in result.suggestions if suggestion.action == "verify-work"), None)
    assert verify is not None, (
        f"No 'verify-work' suggestion found for runtime={runtime!r}; "
        f"got: {[suggestion.action for suggestion in result.suggestions]}"
    )
    assert verify.command == f"{adapter.format_command('verify-work')} 02"
    assert "gpd verify phase" not in verify.command
