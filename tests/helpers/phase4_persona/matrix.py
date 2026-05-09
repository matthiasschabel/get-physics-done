"""Loader and contract constants for the provider-free Phase 4 persona matrix."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

PHASE4_PERSONA_SCHEMA_VERSION = "phase4.persona_lifecycle_matrix.v1"

SURFACES = ("planning", "execution", "completion", "user_steering")

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "phase4_persona"

SURFACE_FIXTURE_FILENAMES = {
    "planning": "planning_rows.json",
    "execution": "execution_rows.json",
    "completion": "completion_rows.json",
    "user_steering": "user_steering_rows.json",
}

SURFACE_SCENARIOS = {
    "planning": frozenset(
        {
            "planning_contract_gate_blocks_without_authority",
            "planner_checkpoint_not_checker_success",
            "proof_bearing_plan_requires_checker",
        }
    ),
    "execution": frozenset(
        {
            "invalid_verify_command_surface",
            "prose_success_no_return",
            "stale_files_written",
            "checkpoint_missing_bounded_context",
            "intermediate_plan_cannot_complete_phase",
        }
    ),
    "completion": frozenset(
        {
            "missing_verification_blocks_closeout",
            "non_passing_verification_records_blocked",
            "active_bounded_segment_routes_resume_work",
            "passed_verification_closeout_readiness_read_only",
        }
    ),
    "user_steering": frozenset(
        {
            "execution_alignment_requires_ask_user_answer",
            "user_abort_stops_without_dispatch",
            "tangent_proposal_routes_to_review_stop",
            "resume_work_prefers_canonical_bounded_segment",
        }
    ),
}

SCENARIO_SCORER_REGISTRY = {
    "planning_contract_gate_blocks_without_authority": "score_planning_contract_gate",
    "planner_checkpoint_not_checker_success": "score_planner_checkpoint_routing",
    "proof_bearing_plan_requires_checker": "score_proof_bearing_plan_checker_gate",
    "invalid_verify_command_surface": "score_invalid_verify_command_surface",
    "prose_success_no_return": "score_prose_success_no_return",
    "stale_files_written": "score_stale_files_written",
    "checkpoint_missing_bounded_context": "score_checkpoint_missing_bounded_context",
    "intermediate_plan_cannot_complete_phase": "score_intermediate_plan_phase_completion_gate",
    "missing_verification_blocks_closeout": "score_missing_verification_closeout_gate",
    "non_passing_verification_records_blocked": "score_non_passing_verification_status",
    "active_bounded_segment_routes_resume_work": "score_active_bounded_segment_resume_route",
    "passed_verification_closeout_readiness_read_only": "score_passed_verification_read_only_closeout",
    "execution_alignment_requires_ask_user_answer": "score_execution_alignment_gate",
    "user_abort_stops_without_dispatch": "score_user_abort_dispatch_gate",
    "tangent_proposal_routes_to_review_stop": "score_tangent_review_stop",
    "resume_work_prefers_canonical_bounded_segment": "score_resume_work_bounded_segment_preference",
}


@dataclass(frozen=True)
class PersonaMatrixRow:
    schema_version: str
    row_id: str
    surface: str
    scenario: str
    fixture_family: str
    runtime_scope: tuple[str, ...]
    source_owners: tuple[str, ...]
    test_owners: tuple[str, ...]
    expected_finding: str
    expected_result_class: str
    provider_launch_allowed: bool
    network_allowed: bool
    raw_artifacts_allowed: bool
    expected_state_status_class: str | None = None
    expected_next_action_class: str | None = None
    mutation_allowed: bool | None = None

    @property
    def scorer_name(self) -> str | None:
        return SCENARIO_SCORER_REGISTRY.get(self.scenario)


def fixture_path_for_surface(surface: str) -> Path:
    if surface not in SURFACE_FIXTURE_FILENAMES:
        valid = ", ".join(SURFACES)
        raise ValueError(f"unknown Phase 4 persona surface {surface!r}; expected one of: {valid}")
    return FIXTURE_DIR / SURFACE_FIXTURE_FILENAMES[surface]


def load_phase4_rows(surface: str | None = None) -> tuple[PersonaMatrixRow, ...]:
    surfaces = (surface,) if surface is not None else SURFACES
    rows: list[PersonaMatrixRow] = []
    for selected_surface in surfaces:
        fixture_path = fixture_path_for_surface(selected_surface)
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        fixture_surface = _required_str(payload, "surface")
        if fixture_surface != selected_surface:
            raise ValueError(f"{fixture_path} declares surface {fixture_surface!r}, expected {selected_surface!r}")
        for raw_row in _required_list(payload, "rows"):
            if not isinstance(raw_row, dict):
                raise TypeError(f"{fixture_path} contains a non-object row: {raw_row!r}")
            row = _row_from_mapping(raw_row)
            if row.surface != selected_surface:
                raise ValueError(f"{fixture_path} row {row.row_id} declares surface {row.surface!r}")
            rows.append(row)
    return tuple(rows)


def _row_from_mapping(row: dict[str, object]) -> PersonaMatrixRow:
    return PersonaMatrixRow(
        schema_version=_required_str(row, "schema_version"),
        row_id=_required_str(row, "row_id"),
        surface=_required_str(row, "surface"),
        scenario=_required_str(row, "scenario"),
        fixture_family=_required_str(row, "fixture_family"),
        runtime_scope=_required_str_tuple(row, "runtime_scope"),
        source_owners=_required_str_tuple(row, "source_owners"),
        test_owners=_required_str_tuple(row, "test_owners"),
        expected_finding=_required_str(row, "expected_finding"),
        expected_result_class=_required_str(row, "expected_result_class"),
        provider_launch_allowed=_required_bool(row, "provider_launch_allowed"),
        network_allowed=_required_bool(row, "network_allowed"),
        raw_artifacts_allowed=_required_bool(row, "raw_artifacts_allowed"),
        expected_state_status_class=_optional_str(row, "expected_state_status_class"),
        expected_next_action_class=_optional_str(row, "expected_next_action_class"),
        mutation_allowed=_optional_bool(row, "mutation_allowed"),
    )


def _required_str(mapping: dict[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise TypeError(f"{key} must be a non-empty string")
    return value


def _optional_str(mapping: dict[str, object], key: str) -> str | None:
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise TypeError(f"{key} must be a non-empty string when set")
    return value


def _required_bool(mapping: dict[str, object], key: str) -> bool:
    value = mapping.get(key)
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be a boolean")
    return value


def _optional_bool(mapping: dict[str, object], key: str) -> bool | None:
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be a boolean when set")
    return value


def _required_list(mapping: dict[str, object], key: str) -> list[object]:
    value = mapping.get(key)
    if not isinstance(value, list):
        raise TypeError(f"{key} must be a list")
    return value


def _required_str_tuple(mapping: dict[str, object], key: str) -> tuple[str, ...]:
    value = _required_list(mapping, key)
    if not value or not all(isinstance(item, str) and item for item in value):
        raise TypeError(f"{key} must be a non-empty list of strings")
    return tuple(value)
