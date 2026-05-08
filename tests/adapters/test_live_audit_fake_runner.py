"""Tests for the provider-free live-audit fake runner."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import tests.helpers.live_audit_harness.fake_runner as fake_runner
from tests.helpers.live_audit_harness.events import extract_transcript_features, load_jsonl_events
from tests.helpers.live_audit_harness.fake_runner import GuardedWorkspace, run_fake_scenario
from tests.helpers.live_audit_harness.scorer import RESULT_GREEN, score_behavior


def _repo_roots(tmp_path: Path) -> tuple[Path, Path]:
    repo_root = tmp_path / "repo"
    repo_tmp = repo_root / "tmp"
    repo_tmp.mkdir(parents=True)
    (repo_root / "src").mkdir()
    return repo_root, repo_tmp


def _guard(tmp_path: Path) -> tuple[GuardedWorkspace, Path, Path, Path]:
    repo_root, repo_tmp = _repo_roots(tmp_path)
    row_root = repo_tmp / "rows" / "ROW-1"
    row_root.mkdir(parents=True)
    return GuardedWorkspace(repo_root=repo_root, tmp_root=repo_tmp, row_root=row_root), repo_root, repo_tmp, row_root


def _assert_under(path: Path, root: Path) -> None:
    path.resolve().relative_to(root.resolve())


def test_run_fake_scenario_emits_provider_free_artifacts_under_repo_tmp(tmp_path: Path) -> None:
    repo_root, repo_tmp = _repo_roots(tmp_path)
    row = SimpleNamespace(
        row_id="HELP-BEGINNER",
        final_text="Use /gpd:start for the guided menu.",
        stdout_events=[{"type": "message", "role": "assistant", "content": "Use /gpd:start for the guided menu."}],
        normalized_events=[
            {"type": "assistant_final", "source": "fake_fixture", "text": "Use /gpd:start for the guided menu."}
        ],
        fake_writes=[{"path": "workspace/GPD/notes.md", "text": "fake note\n"}],
        attempted_writes=[{"path": "../escape.txt", "text": "must not be written\n"}],
    )

    result = run_fake_scenario(row, repo_root=repo_root, output_root=repo_tmp / "phase7")

    assert result.row_id == "HELP-BEGINNER"
    assert result.row_root == repo_tmp / "phase7" / "HELP-BEGINNER"
    for path in (
        result.status_path,
        result.final_path,
        result.normalized_events_path,
        result.write_classification_path,
        result.evidence_packet_path,
        result.row_root / "stdout.jsonl",
    ):
        assert path.is_file()
        _assert_under(path, repo_tmp)
        _assert_under(path, result.row_root)

    assert (result.row_root / "workspace" / "GPD" / "notes.md").read_text(encoding="utf-8") == "fake note\n"
    assert not (result.row_root.parent / "escape.txt").exists()

    status = json.loads(result.status_path.read_text(encoding="utf-8"))
    assert status["fake_provider"] is True
    assert status["provider_launched"] is False
    assert status["subprocess_invoked"] is False
    assert "command" not in status
    assert "argv" not in status

    evidence = json.loads(result.evidence_packet_path.read_text(encoding="utf-8"))
    assert evidence["provider_launched"] is False
    assert evidence["subprocess_invoked"] is False
    assert evidence["raw_provider_output_recorded"] is False
    assert evidence["provider_cli_argv_recorded"] is False
    assert evidence["artifacts"]["evidence_packet"]["exists"] is True
    assert Path(evidence["artifacts"]["evidence_packet"]["path"]) == result.evidence_packet_path

    classification = json.loads(result.write_classification_path.read_text(encoding="utf-8"))
    assert classification["provider_launched"] is False
    assert classification["subprocess_invoked"] is False
    assert classification["summary"]["all_materialized_under_tmp"] is True
    assert classification["summary"]["all_materialized_under_row_root"] is True
    assert classification["summary"]["refused"] == 1
    assert classification["refused_writes"][0]["classification"] == "path_traversal_refused"
    for write in classification["writes"]:
        _assert_under(Path(write["resolved_path"]), repo_tmp)
        _assert_under(Path(write["resolved_path"]), result.row_root)


def test_fake_runner_module_has_no_subprocess_import_path() -> None:
    source = inspect.getsource(fake_runner)

    assert "import subprocess" not in source
    assert "from subprocess" not in source
    assert not hasattr(fake_runner, "subprocess")


def test_guarded_workspace_refuses_path_traversal(tmp_path: Path) -> None:
    guard, _repo_root, _repo_tmp, row_root = _guard(tmp_path)

    with pytest.raises(ValueError, match="traversal"):
        guard.write_text("../escape.txt", "no\n")

    assert not (row_root.parent / "escape.txt").exists()


def test_run_fake_scenario_evidence_scores_against_required_artifacts(tmp_path: Path) -> None:
    repo_root, repo_tmp = _repo_roots(tmp_path)
    row = SimpleNamespace(
        row_id="PHASE-CLOSEOUT-GREEN",
        final_text="Ready for review. No provider was launched.",
        required_artifacts=(
            "status.json",
            "stdout.jsonl",
            "normalized-events.jsonl",
            "final.md",
            "write-classification.json",
            "evidence-packet.json",
        ),
    )

    result = run_fake_scenario(row, repo_root=repo_root, output_root=repo_tmp / "phase7")

    events = load_jsonl_events(result.normalized_events_path)
    features = extract_transcript_features(
        row.row_id,
        result.final_path.read_text(encoding="utf-8"),
        events,
    )
    score = score_behavior(
        row,
        features,
        json.loads(result.status_path.read_text(encoding="utf-8")),
        json.loads(result.write_classification_path.read_text(encoding="utf-8")),
        json.loads(result.evidence_packet_path.read_text(encoding="utf-8")),
    )

    assert score.result == RESULT_GREEN
    assert score.findings == ()


def test_guarded_workspace_refuses_absolute_escape(tmp_path: Path) -> None:
    guard, _repo_root, repo_tmp, _row_root = _guard(tmp_path)
    absolute_target = repo_tmp / "absolute.txt"

    with pytest.raises(ValueError, match="absolute"):
        guard.write_text(str(absolute_target), "no\n")

    assert not absolute_target.exists()


def test_guarded_workspace_refuses_symlink_escape(tmp_path: Path) -> None:
    guard, _repo_root, repo_tmp, row_root = _guard(tmp_path)
    outside_row = repo_tmp / "outside-row"
    outside_row.mkdir()
    link = row_root / "link"
    try:
        link.symlink_to(outside_row, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlinks unavailable in this environment: {exc}")

    with pytest.raises(ValueError, match="symlink"):
        guard.write_text("link/escape.txt", "no\n")

    assert not (outside_row / "escape.txt").exists()


def test_guarded_workspace_refuses_active_checkout_row_root(tmp_path: Path) -> None:
    repo_root, repo_tmp = _repo_roots(tmp_path)
    active_checkout_row = repo_root / "src" / "row"
    active_checkout_row.mkdir()

    with pytest.raises(ValueError, match="active checkout"):
        GuardedWorkspace(repo_root=repo_root, tmp_root=repo_tmp, row_root=active_checkout_row)


def test_run_fake_scenario_refuses_output_root_outside_repo_tmp(tmp_path: Path) -> None:
    repo_root, _repo_tmp = _repo_roots(tmp_path)
    row = SimpleNamespace(row_id="PLAN-DIRTY-GIT")

    with pytest.raises(ValueError, match="repo-local tmp"):
        run_fake_scenario(row, repo_root=repo_root, output_root=tmp_path / "external-output")
