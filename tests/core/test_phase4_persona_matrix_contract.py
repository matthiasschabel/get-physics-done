"""Contract checks for the provider-free Phase 4 persona row matrix."""

from __future__ import annotations

import re

from tests.helpers.phase4_persona.matrix import (
    PHASE4_PERSONA_SCHEMA_VERSION,
    REPO_ROOT,
    SCENARIO_SCORER_REGISTRY,
    SURFACE_SCENARIOS,
    SURFACES,
    fixture_path_for_surface,
    load_phase4_rows,
)

_ROW_ID_RE = re.compile(r"^P4-(PLAN|EXEC|COMP|USER)-[0-9]{2}$")
_SCORER_NAME_RE = re.compile(r"^score_[a-z0-9_]+$")
_FORBIDDEN_RAW_ARTIFACT_NAMES = frozenset(
    {
        "argv.json",
        "command.json",
        "command.txt",
        "env.json",
        "prompt.enveloped.txt",
        "prompt.txt",
        "provider-output.txt",
        "provider-reply.txt",
        "provider_output.txt",
        "provider_reply.txt",
        "raw-transcript.md",
        "raw_transcript.md",
        "stderr.txt",
        "stdout.jsonl",
        "stdout.txt",
        "transcript.md",
    }
)
_RAW_FIELD_NAMES = frozenset(
    {
        "argv",
        "command",
        "env",
        "prompt",
        "provider_output",
        "provider_reply",
        "raw_artifact",
        "raw_output",
        "raw_transcript",
        "stderr",
        "stdout",
        "transcript",
    }
)


def test_phase4_persona_fixture_files_load_for_every_surface() -> None:
    rows = load_phase4_rows()

    assert {row.surface for row in rows} == set(SURFACES)
    assert {fixture_path_for_surface(surface).name for surface in SURFACES} == {
        "planning_rows.json",
        "execution_rows.json",
        "completion_rows.json",
        "user_steering_rows.json",
    }


def test_phase4_persona_row_ids_are_unique_and_well_formed() -> None:
    rows = load_phase4_rows()
    row_ids = [row.row_id for row in rows]

    assert len(row_ids) == len(set(row_ids))
    assert all(_ROW_ID_RE.match(row_id) for row_id in row_ids)


def test_phase4_persona_rows_name_existing_owner_files() -> None:
    for row in load_phase4_rows():
        for owner in (*row.source_owners, *row.test_owners):
            owner_file = REPO_ROOT / owner
            assert owner_file.is_file(), f"{row.row_id} references missing owner {owner}"


def test_phase4_persona_rows_are_provider_free_and_class_only() -> None:
    for row in load_phase4_rows():
        assert row.schema_version == PHASE4_PERSONA_SCHEMA_VERSION
        assert row.provider_launch_allowed is False
        assert row.network_allowed is False
        assert row.raw_artifacts_allowed is False

        row_values = vars(row)
        assert _RAW_FIELD_NAMES.isdisjoint(row_values)
        assert all(isinstance(value, (str, bool, tuple, type(None))) for value in row_values.values())
        assert row.fixture_family.endswith("_class")
        assert "transcript" not in row.fixture_family


def test_phase4_persona_rows_use_valid_surface_scenario_pairs() -> None:
    for row in load_phase4_rows():
        assert row.surface in SURFACES
        assert row.scenario in SURFACE_SCENARIOS[row.surface]


def test_phase4_persona_scenarios_have_registered_scorer_names() -> None:
    registered_scenarios = set(SCENARIO_SCORER_REGISTRY)
    fixture_scenarios = {row.scenario for row in load_phase4_rows()}

    assert fixture_scenarios <= registered_scenarios
    for row in load_phase4_rows():
        scorer_name = row.scorer_name
        assert scorer_name is not None
        assert _SCORER_NAME_RE.match(scorer_name)


def test_phase4_persona_fixture_text_has_no_raw_artifact_names() -> None:
    offenders: list[str] = []
    for surface in SURFACES:
        fixture_path = fixture_path_for_surface(surface)
        for line_number, line in enumerate(fixture_path.read_text(encoding="utf-8").splitlines(), start=1):
            for forbidden_name in _FORBIDDEN_RAW_ARTIFACT_NAMES:
                if forbidden_name in line:
                    relpath = fixture_path.relative_to(REPO_ROOT)
                    offenders.append(f"{relpath}:{line_number}:{forbidden_name}")

    assert not offenders, offenders
