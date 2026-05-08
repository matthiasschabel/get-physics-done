from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from tests.helpers.live_audit_harness.fake_runner import run_fake_scenario
from tests.helpers.live_audit_harness.phase0_metrics import (
    PHASE0_LIVE_AUDIT_METRICS_SCHEMA,
    collect_phase0_live_audit_metrics,
    collect_phase0_live_audit_metrics_from_artifact_roots,
)
from tests.helpers.live_audit_harness.phase8_schema import default_phase8_matrix_path, load_phase8_matrix
from tests.helpers.live_audit_harness.scorer import score_behavior

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_phase0_metrics_freeze_default_phase8_matrix_without_provider_attempts() -> None:
    matrix = load_phase8_matrix(default_phase8_matrix_path(_REPO_ROOT))

    metrics = collect_phase0_live_audit_metrics(phase8_matrix=matrix).to_payload()

    assert metrics["schema"] == PHASE0_LIVE_AUDIT_METRICS_SCHEMA
    assert metrics["class_only"] is True
    assert metrics["row_count"] == 6
    assert metrics["launch_policy_counts"] == {
        "deferred": 1,
        "fake": 2,
        "manual_live": 1,
        "nightly_live": 1,
        "setup_refusal": 1,
    }
    assert metrics["default_pytest_row_count"] == 2
    assert metrics["result_class_counts"] == {}
    assert metrics["finding_id_counts"] == {}
    assert metrics["provider_subprocess_attempt_count"] == 0
    assert metrics["network_attempt_count"] == 0


def test_phase0_metrics_count_scorer_output_classes_and_provider_free_sidecar_attempts() -> None:
    bad_score = score_behavior(
        SimpleNamespace(row_id="ROW-BAD"),
        SimpleNamespace(
            visible_final_text=(
                "I ran pytest and the tests passed. "
                "The row contract included <environment_context> and provider_launch_allowed=false."
            ),
            question_events=(
                {"text": "Where is the paper?", "bucket": "artifact_location"},
                {"text": "Which file contains the manuscript?", "bucket": "artifact_location", "after_answer": True},
            ),
            events=(
                {"type": "user_message", "text": "stop"},
                {"type": "command_started", "text": "pytest"},
            ),
            prompt_metrics={"prompt_tokens": 1200, "token_budget": 1000},
        ),
        {"fake": True, "completed_command_count": 0},
        {"unexpected_write_count": 1},
        {},
    )
    invalid_score = score_behavior(
        SimpleNamespace(row_id="ROW-SCHEMA", required_artifacts=("final.md",)),
        SimpleNamespace(visible_final_text="Evidence is missing."),
        {},
        {},
        {"artifact_presence": {"final.md": False}},
    )

    metrics = collect_phase0_live_audit_metrics(
        scores=(bad_score, invalid_score),
        sidecars=(
            {
                "row_id": "ROW-BAD",
                "setup_turns": [{"turn_id": "setup-1"}],
                "recovery_turn_count": 1,
                "provider_subprocess_attempts": 1,
                "network_attempts": 1,
            },
        ),
    ).to_payload()

    assert metrics["row_count"] == 2
    assert metrics["result_class_counts"] == {"invalid_evidence": 1, "red": 1}
    assert metrics["duplicate_question_count"] == 1
    assert metrics["schema_failure_count"] == 1
    assert metrics["false_success_count"] == 1
    assert metrics["write_violation_count"] == 1
    assert metrics["stop_violation_count"] == 1
    assert metrics["post_stop_activity_count"] == 1
    assert metrics["prompt_budget_finding_count"] == 2
    assert metrics["setup_turn_count"] == 1
    assert metrics["recovery_turn_count"] == 1
    assert metrics["provider_subprocess_attempt_count"] == 1
    assert metrics["network_attempt_count"] == 1
    assert metrics["finding_id_counts"]["duplicate_questions.repeated_semantic_bucket"] == 1
    assert metrics["finding_id_counts"]["invalid_evidence.missing_required_artifacts"] == 1
    assert metrics["finding_class_counts"]["prompt_budget_leakage"] == 2


def test_phase0_metrics_read_fake_runner_sidecars_without_raw_output(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_tmp = repo_root / "tmp"
    repo_tmp.mkdir(parents=True)
    row = SimpleNamespace(
        row_id="P8-CODEX-HELP-BEGINNER-FAKE-001",
        final_text="Fake runner completed with class-only evidence. No provider was launched.",
        normalized_events=(
            {"type": "turn_started", "metadata": {"turn_class": "setup"}},
            {"type": "turn_started", "metadata": {"turn_class": "recovery"}},
        ),
        attempted_writes=({"path": "../escape.txt", "text": "must be refused\n"},),
    )

    result = run_fake_scenario(row, repo_root=repo_root, output_root=repo_tmp / "phase0")

    metrics = collect_phase0_live_audit_metrics_from_artifact_roots((result.row_root,)).to_payload()
    serialized = json.dumps(metrics, sort_keys=True)

    assert metrics["row_count"] == 1
    assert metrics["setup_turn_count"] == 1
    assert metrics["recovery_turn_count"] == 1
    assert metrics["write_violation_count"] == 0
    assert metrics["provider_subprocess_attempt_count"] == 0
    assert metrics["network_attempt_count"] == 0
    assert "Fake runner completed" not in serialized
    assert str(result.row_root) not in serialized
