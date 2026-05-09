"""Provider-free replay tests for Phase 4 user-steering behavior."""

from __future__ import annotations

import re
from dataclasses import fields
from pathlib import Path

import pytest

from tests.helpers.phase4_persona.user_steering import (
    REPO_ROOT,
    UserSteeringOutcome,
    UserSteeringRow,
    replay_event_for_row,
    score_user_steering_row,
    user_steering_rows,
)

CLASS_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")


def _assert_class_only(value: object) -> None:
    if isinstance(value, str):
        assert CLASS_TOKEN_RE.fullmatch(value), value
        assert "/" not in value
        assert "\\" not in value
        assert " " not in value
    elif isinstance(value, tuple):
        for item in value:
            _assert_class_only(item)
    elif isinstance(value, bool):
        return
    else:
        raise AssertionError(f"unexpected non-class value type: {type(value).__name__}")


def _assert_outcome_class_only(outcome: UserSteeringOutcome) -> None:
    for field in fields(outcome):
        _assert_class_only(getattr(outcome, field.name))


def test_phase4_user_steering_rows_are_provider_free_and_owned() -> None:
    rows = user_steering_rows()

    assert [row.row_id for row in rows] == [
        "P4-USER-01",
        "P4-USER-02",
        "P4-USER-03",
        "P4-USER-04",
        "P4-USER-05",
        "P4-USER-06",
    ]
    assert all(row.provider_launch_allowed is False for row in rows)
    assert all(row.network_allowed is False for row in rows)
    assert all(row.raw_artifacts_allowed is False for row in rows)
    assert all(row.mutation_allowed is False for row in rows)

    source_files = {source_file for row in rows for source_file in row.source_files}
    assert source_files == {
        Path("src/gpd/specs/workflows/execute-phase/wave-planning.md"),
        Path("src/gpd/specs/workflows/execute-phase/wave-dispatch.md"),
        Path("src/gpd/specs/workflows/resume-work/resume-bootstrap.md"),
        Path("src/gpd/specs/workflows/resume-work/resume-routing.md"),
        Path("src/gpd/specs/workflows/execute-phase/closeout.md"),
    }
    assert all((REPO_ROOT / source_file).is_file() for source_file in source_files)


@pytest.mark.parametrize("row", user_steering_rows(), ids=lambda row: f"{row.row_id}-{row.scenario}")
def test_phase4_user_steering_replay_scores_expected_class(row: UserSteeringRow) -> None:
    event = replay_event_for_row(row)

    outcome = score_user_steering_row(row, event)

    assert outcome.provider_launch_allowed is False
    assert outcome.network_allowed is False
    assert outcome.raw_artifacts_allowed is False
    assert outcome.mutated is False
    assert outcome.finding_id == row.expected_finding
    assert outcome.result_class == row.expected_result_class
    assert outcome.next_action_class == row.expected_next_action_class
    assert row.expected_finding in outcome.failure_classes
    _assert_outcome_class_only(outcome)


def test_phase4_user_steering_replay_events_are_class_only() -> None:
    for row in user_steering_rows():
        event = replay_event_for_row(row)
        for field in fields(event):
            _assert_class_only(getattr(event, field.name))
