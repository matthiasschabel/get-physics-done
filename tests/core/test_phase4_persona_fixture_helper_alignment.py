"""Alignment checks between Phase 4 persona fixtures and shared replay helpers."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Protocol

import pytest

from tests.helpers.phase4_persona.replay import (
    PersonaRow,
    executable_phase4_matrix_rows,
    load_phase4_replay_rows,
    persona_row_from_matrix_row,
    registered_phase4_scenarios,
    score_phase4_row,
)


class _RowLike(Protocol):
    row_id: str
    surface: str
    scenario: str


def _row_id(row: _RowLike) -> str:
    return row.row_id


def _row_key(row: _RowLike) -> tuple[str, str, str]:
    return (row.row_id, row.surface, row.scenario)


def test_shared_replay_rows_are_canonical_fixture_adapters() -> None:
    matrix_rows = executable_phase4_matrix_rows()
    replay_rows = load_phase4_replay_rows()

    assert matrix_rows
    assert [_row_key(row) for row in replay_rows] == [_row_key(row) for row in matrix_rows]
    assert {row.scenario for row in replay_rows} == registered_phase4_scenarios()
    assert all(not row.row_id.startswith("P4-S-") for row in replay_rows)

    for matrix_row, replay_row in zip(matrix_rows, replay_rows, strict=True):
        assert replay_row == persona_row_from_matrix_row(matrix_row)
        assert replay_row.fixture_family == matrix_row.fixture_family
        assert replay_row.runtime_scope == matrix_row.runtime_scope


def test_executable_scorer_registry_is_fixture_backed() -> None:
    executable_fixture_scenarios = {row.scenario for row in executable_phase4_matrix_rows()}

    assert registered_phase4_scenarios() == executable_fixture_scenarios


@pytest.mark.parametrize("row", executable_phase4_matrix_rows(), ids=_row_id)
def test_canonical_matrix_rows_score_through_shared_replay(
    row: _RowLike, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outcome = score_phase4_row(row, tmp_path, monkeypatch)
    replay_row = persona_row_from_matrix_row(row)

    assert outcome.provider_launch_allowed is False
    assert outcome.finding_id == replay_row.expected_finding
    assert outcome.result_class == replay_row.expected_result_class
    assert replay_row.expected_finding in outcome.failure_classes
    if replay_row.expected_state_status_class is not None:
        assert outcome.state_status_class == replay_row.expected_state_status_class
    if replay_row.expected_next_action_class is not None:
        assert outcome.next_action_class == replay_row.expected_next_action_class


@pytest.mark.parametrize(
    "field",
    ("provider_launch_allowed", "network_allowed", "raw_artifacts_allowed"),
)
def test_shared_replay_rejects_provider_or_raw_artifact_rows(field: str, tmp_path: Path) -> None:
    row = replace(load_phase4_replay_rows()[0], **{field: True})

    with pytest.raises(AssertionError, match="provider-free"):
        score_phase4_row(row, tmp_path)


def test_replay_surface_filter_stays_aligned_with_canonical_matrix() -> None:
    for surface in ("execution", "completion"):
        matrix_rows = executable_phase4_matrix_rows(surface)
        replay_rows = load_phase4_replay_rows(surface)

        assert [_row_key(row) for row in replay_rows] == [_row_key(row) for row in matrix_rows]
        assert all(isinstance(row, PersonaRow) for row in replay_rows)
