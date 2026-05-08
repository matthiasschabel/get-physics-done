from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts.phase11_live_comparison_artifacts import (
    PHASE11_LIVE_COMPARISON_REPORT,
    PHASE11_LIVE_COMPARISON_SUMMARY,
)
from scripts.phase11_live_comparison_artifacts import (
    main as phase11_comparison_main,
)
from tests.helpers.live_audit_harness.reporting import render_provider_attempt_report


def test_phase11_live_comparison_cli_writes_expected_artifacts(tmp_path: Path) -> None:
    manual_report = _provider_attempt_report(
        attempt_id="attempt-manual",
        batch_id="batch-manual",
        launch_policy="manual_live",
        row_id="row-manual",
        result_class="green",
    )
    nightly_report = _provider_attempt_report(
        attempt_id="attempt-nightly",
        batch_id="batch-nightly",
        launch_policy="nightly_live",
        row_id="row-nightly",
        result_class="yellow",
    )
    manual_path = _write_json(tmp_path / "manual-report.json", manual_report)
    nightly_path = _write_json(tmp_path / "nightly-report.json", nightly_report)
    out_dir = tmp_path / "phase11"

    exit_code = phase11_comparison_main(
        [
            "--manual-report",
            str(manual_path),
            "--nightly-report",
            str(nightly_path),
            "--out-dir",
            str(out_dir),
        ]
    )

    assert exit_code == 0
    assert {path.name for path in out_dir.iterdir()} == {
        PHASE11_LIVE_COMPARISON_REPORT,
        PHASE11_LIVE_COMPARISON_SUMMARY,
    }
    report_text = (out_dir / PHASE11_LIVE_COMPARISON_REPORT).read_text(encoding="utf-8")
    summary_text = (out_dir / PHASE11_LIVE_COMPARISON_SUMMARY).read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert "attempt-manual" in report_text
    assert "attempt-nightly" in report_text
    assert report["provider_free"] is True
    assert summary_text.startswith("# Phase 11")


def test_phase11_live_comparison_cli_fails_for_missing_report(tmp_path: Path, capsys) -> None:
    manual_path = _write_json(
        tmp_path / "manual-report.json",
        _provider_attempt_report(
            attempt_id="attempt-manual",
            batch_id="batch-manual",
            launch_policy="manual_live",
            row_id="row-manual",
            result_class="green",
        ),
    )
    out_dir = tmp_path / "phase11"

    exit_code = phase11_comparison_main(
        [
            "--manual-report",
            str(manual_path),
            "--nightly-report",
            str(tmp_path / "missing-nightly-report.json"),
            "--out-dir",
            str(out_dir),
        ]
    )

    assert exit_code == 1
    assert "nightly report does not exist" in capsys.readouterr().err
    assert not out_dir.exists()


def test_phase11_live_comparison_cli_fails_for_unsafe_report(tmp_path: Path, capsys) -> None:
    manual_report = _provider_attempt_report(
        attempt_id="attempt-manual",
        batch_id="batch-manual",
        launch_policy="manual_live",
        row_id="row-manual",
        result_class="green",
    )
    unsafe_nightly_report = copy.deepcopy(
        _provider_attempt_report(
            attempt_id="attempt-nightly",
            batch_id="batch-nightly",
            launch_policy="nightly_live",
            row_id="row-nightly",
            result_class="green",
        )
    )
    unsafe_nightly_report["rows"][0]["provider_output"] = {"stdout": "provider transcript"}
    manual_path = _write_json(tmp_path / "manual-report.json", manual_report)
    nightly_path = _write_json(tmp_path / "nightly-report.json", unsafe_nightly_report)
    out_dir = tmp_path / "phase11"

    exit_code = phase11_comparison_main(
        [
            "--manual-report",
            str(manual_path),
            "--nightly-report",
            str(nightly_path),
            "--out-dir",
            str(out_dir),
        ]
    )

    assert exit_code == 1
    assert "provider_output" in capsys.readouterr().err
    assert not out_dir.exists()


def _provider_attempt_report(
    *,
    attempt_id: str,
    batch_id: str,
    launch_policy: str,
    row_id: str,
    result_class: str,
) -> dict[str, object]:
    return render_provider_attempt_report(
        [
            {
                "row_id": row_id,
                "scenario_id": "HELP-BEGINNER",
                "persona_id": "P00_zero_coder",
                "provider_runtime": "codex",
                "provider_adapter": "codex",
                "launch_policy": launch_policy,
                "attempt_status": "completed",
                "result_class": result_class,
                "command_bucket": "start",
                "prompt_budget": {
                    "max_prompt_tokens": 500,
                    "prompt_tokens_estimate": 200,
                    "completion_tokens_estimate": 50,
                    "observed_total_tokens": 240,
                },
                "retention_refs": ["provider-attempt-json"],
            }
        ],
        attempt_id=attempt_id,
        batch_id=batch_id,
        scenario_set_id="phase8-smoke",
        row_set_sha256=f"{attempt_id}-row-set",
        budget_id=f"{attempt_id}-budget",
        repo_head="abc123",
        provider_set=["codex"],
        runtime_capabilities=[{"runtime": "codex", "live_runner_status": "ready"}],
        retention_manifest={
            "artifacts": [
                {
                    "artifact_id": "provider-attempt-json",
                    "artifact_ref": "provider-attempt.json",
                    "retention_class": "committed_redacted",
                    "material_class": "sanitized_report",
                    "safe_to_commit": True,
                }
            ]
        },
    )


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
