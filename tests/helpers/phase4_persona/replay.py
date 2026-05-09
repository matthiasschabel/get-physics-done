"""Provider-free replay API for Phase 4 persona lifecycle rows."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Protocol

from tests.helpers.phase4_persona.scorers import SCORERS, PersonaOutcome

SCHEMA_VERSION = "phase4.persona_lifecycle_matrix.v1"


@dataclass(frozen=True, slots=True)
class PersonaRow:
    """Class-only replay row with no provider transcript or raw artifact payload."""

    row_id: str
    surface: str
    scenario: str
    expected_finding: str
    expected_result_class: str
    provider_launch_allowed: bool = False
    network_allowed: bool = False
    raw_artifacts_allowed: bool = False
    mutation_allowed: bool = False
    expected_state_status_class: str | None = None
    expected_next_action_class: str | None = None
    fixture_family: str = "phase4_persona_replay"
    runtime_scope: tuple[str, ...] = ("provider_free",)
    schema_version: str = SCHEMA_VERSION


class _MonkeyPatchLike(Protocol):
    def setenv(self, name: str, value: str) -> None: ...


_SEED_ROWS: tuple[PersonaRow, ...] = (
    PersonaRow(
        row_id="P4-S-01",
        surface="completion",
        scenario="invalid_verify_command_surface",
        expected_finding="invalid_verify_command_surface",
        expected_result_class="blocked_no_mutation",
        expected_state_status_class="unchanged",
        expected_next_action_class="active_runtime_verify_work",
    ),
    PersonaRow(
        row_id="P4-S-02",
        surface="execution",
        scenario="prose_success_no_return",
        expected_finding="return_missing",
        expected_result_class="blocked_no_mutation",
        expected_state_status_class="unchanged",
        expected_next_action_class="retry_child_return",
    ),
    PersonaRow(
        row_id="P4-S-03",
        surface="execution",
        scenario="stale_files_written",
        expected_finding="artifact_stale",
        expected_result_class="blocked_no_mutation",
        expected_state_status_class="unchanged",
        expected_next_action_class="retry_fresh_artifact",
    ),
    PersonaRow(
        row_id="P4-S-04",
        surface="execution",
        scenario="checkpoint_missing_bounded_context",
        expected_finding="checkpoint_missing_bounded_segment",
        expected_result_class="blocked_no_mutation",
        expected_state_status_class="unchanged",
        expected_next_action_class="create_bounded_resume_context",
    ),
    PersonaRow(
        row_id="P4-S-05",
        surface="completion",
        scenario="bounded_segment_bypass",
        expected_finding="closeout_authority_blocks_premature_completion",
        expected_result_class="blocked_no_mutation",
        expected_state_status_class="unchanged",
        expected_next_action_class="gpd_resume_work",
    ),
)


def _validate_rows(rows: tuple[PersonaRow, ...]) -> None:
    row_ids = [row.row_id for row in rows]
    if len(row_ids) != len(set(row_ids)):
        raise AssertionError("Phase 4 persona replay row ids must be unique")
    for row in rows:
        if row.schema_version != SCHEMA_VERSION:
            raise AssertionError(f"{row.row_id} has unsupported schema version {row.schema_version!r}")
        if row.provider_launch_allowed or row.network_allowed or row.raw_artifacts_allowed:
            raise AssertionError(f"{row.row_id} must stay provider-free and class-only")
        if row.scenario not in SCORERS:
            raise AssertionError(f"{row.row_id} has no registered scorer for scenario {row.scenario!r}")


def load_phase4_rows(surface: str | None = None) -> tuple[PersonaRow, ...]:
    """Return provider-free replay rows, optionally filtered by behavior surface."""

    rows = _SEED_ROWS if surface is None else tuple(row for row in _SEED_ROWS if row.surface == surface)
    _validate_rows(rows)
    return rows


def persona_row_from_mapping(data: Mapping[str, object]) -> PersonaRow:
    """Coerce a future class-only fixture mapping into the current row model."""

    raw_runtime_scope = data.get("runtime_scope", ("provider_free",))
    if isinstance(raw_runtime_scope, str):
        runtime_scope = (raw_runtime_scope,)
    elif isinstance(raw_runtime_scope, (list, tuple, set)):
        runtime_scope = tuple(str(item) for item in raw_runtime_scope)
    else:
        runtime_scope = (str(raw_runtime_scope),)

    return PersonaRow(
        row_id=str(data["row_id"]),
        surface=str(data["surface"]),
        scenario=str(data["scenario"]),
        expected_finding=str(data["expected_finding"]),
        expected_result_class=str(data["expected_result_class"]),
        provider_launch_allowed=bool(data.get("provider_launch_allowed", False)),
        network_allowed=bool(data.get("network_allowed", False)),
        raw_artifacts_allowed=bool(data.get("raw_artifacts_allowed", False)),
        mutation_allowed=bool(data.get("mutation_allowed", False)),
        expected_state_status_class=(
            None if data.get("expected_state_status_class") is None else str(data["expected_state_status_class"])
        ),
        expected_next_action_class=(
            None if data.get("expected_next_action_class") is None else str(data["expected_next_action_class"])
        ),
        fixture_family=str(data.get("fixture_family", "phase4_persona_replay")),
        runtime_scope=runtime_scope,
        schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
    )


def _coerce_row(row: PersonaRow | Mapping[str, object] | object) -> PersonaRow:
    if isinstance(row, PersonaRow):
        return row
    if isinstance(row, Mapping):
        return persona_row_from_mapping(row)
    if is_dataclass(row):
        return persona_row_from_mapping(asdict(row))
    return persona_row_from_mapping(
        {
            "row_id": _required_attr(row, "row_id"),
            "surface": _required_attr(row, "surface"),
            "scenario": _required_attr(row, "scenario"),
            "expected_finding": _required_attr(row, "expected_finding"),
            "expected_result_class": _required_attr(row, "expected_result_class"),
            "provider_launch_allowed": _optional_attr(row, "provider_launch_allowed", False),
            "network_allowed": _optional_attr(row, "network_allowed", False),
            "raw_artifacts_allowed": _optional_attr(row, "raw_artifacts_allowed", False),
            "mutation_allowed": _optional_attr(row, "mutation_allowed", False),
            "expected_state_status_class": _optional_attr(row, "expected_state_status_class", None),
            "expected_next_action_class": _optional_attr(row, "expected_next_action_class", None),
            "fixture_family": _optional_attr(row, "fixture_family", "phase4_persona_replay"),
            "runtime_scope": _optional_attr(row, "runtime_scope", ("provider_free",)),
            "schema_version": _optional_attr(row, "schema_version", SCHEMA_VERSION),
        }
    )


def _required_attr(row: object, name: str) -> object:
    return getattr(row, name)


def _optional_attr(row: object, name: str, default: object) -> object:
    return getattr(row, name, default)


def score_phase4_row(
    row: PersonaRow | Mapping[str, object] | object,
    tmp_path: Path,
    monkeypatch: _MonkeyPatchLike | None = None,
) -> PersonaOutcome:
    """Replay one row through core lifecycle APIs without launching providers."""

    replay_row = _coerce_row(row)
    _validate_rows((replay_row,))
    if monkeypatch is not None:
        monkeypatch.setenv("GPD_DATA_DIR", str(tmp_path / ".gpd-data"))
    return SCORERS[replay_row.scenario](tmp_path)


__all__ = [
    "PersonaOutcome",
    "PersonaRow",
    "SCHEMA_VERSION",
    "load_phase4_rows",
    "persona_row_from_mapping",
    "score_phase4_row",
]
