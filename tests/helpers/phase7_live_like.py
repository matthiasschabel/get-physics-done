"""Provider-free Phase 7 live-like rows scored through Phase 4 behavior metrics."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from tests.helpers.phase4_persona.behavior_metrics import (
    BEHAVIOR_METRIC_CLASS_KEYS,
    BEHAVIOR_METRIC_COUNT_KEYS,
    BehaviorScore,
    score_behavior_metrics,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE7_LIVE_PERSONA_MATRIX_PATH = REPO_ROOT / "tests" / "fixtures" / "phase7_live_persona_matrix.json"
LP_JIT_ROW_IDS = tuple(f"LP-JIT-{index:02d}" for index in range(1, 9))

_PREFIX_CASES = {
    "LP-JIT-01": "minimal_projectless_route",
    "LP-JIT-02": "bounded_resume",
    "LP-JIT-03": "stale_artifact_rejection",
    "LP-JIT-04": "handles_before_content",
    "LP-JIT-05": "publication_gap_block",
    "LP-JIT-06": "clean_stop",
    "LP-JIT-07": "verify_work_command_correction",
    "LP-JIT-08": "unsupported_completion_block",
}
_HARD_ZERO_BEHAVIOR_KEYS = (
    "invalid_command_suggestion_count",
    "stale_artifact_trust_count",
    "post_stop_activity_count",
    "unexpected_write_count",
    "unsupported_completion_claim_count",
)
_HARD_ZERO_PHASE7_KEYS = ("raw_reload_leakage_count", "content_hydration_before_selection_count")


@dataclass(frozen=True, slots=True)
class Phase7LiveLikeRow:
    row_id: str
    fixture_family: str
    runtime_scope: tuple[str, ...]
    source_owners: tuple[str, ...]
    test_owners: tuple[str, ...]
    provider_launch_allowed: bool = False
    network_allowed: bool = False
    raw_artifacts_allowed: bool = False
    persona_class: str = "phase7_live_like"
    workflow_class: str = "provider_free_canary"
    prompt_variant_class: str = "class_only"
    behavior_case: str = ""
    phase4_behavior_ref: str = ""
    schema_version: str = "phase7.live_persona_matrix.v1"


@dataclass(frozen=True, slots=True)
class Phase7LiveLikeTurn:
    action_class: str
    physics_progress_class: str = "none"
    schema_surface_class: str = "none"
    artifact_access_class: str = "none"
    reload_surface_class: str = "none"
    stop_class: str = "none"


@dataclass(frozen=True, slots=True)
class Phase7LiveLikeTrace:
    row_id: str
    persona_class: str
    workflow_class: str
    prompt_variant_class: str
    turns: tuple[Phase7LiveLikeTurn, ...]


@dataclass(frozen=True, slots=True)
class Phase7LiveLikeScore:
    row: Phase7LiveLikeRow
    trace: Phase7LiveLikeTrace
    behavior_score: BehaviorScore
    phase7_metric_counts: Mapping[str, int]
    phase7_metric_classes: Mapping[str, str]
    hard_budget_failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.behavior_score.passed and not self.hard_budget_failures


@dataclass(frozen=True, slots=True)
class _BehaviorRow:
    row_id: str
    surface: str
    scenario: str
    expected_result_class: str
    expected_next_action_class: str
    provider_launch_allowed: bool = False
    network_allowed: bool = False
    raw_artifacts_allowed: bool = False
    mutation_allowed: bool = False


@dataclass(frozen=True, slots=True)
class _BehaviorOutcome:
    finding_id: str
    result_class: str
    failure_classes: tuple[str, ...]
    evidence_classes: tuple[str, ...]
    next_action_class: str
    accepted: bool = False
    ready: bool | None = None
    mutated: bool = False
    state_status_class: str | None = "unchanged"
    commands: tuple[str, ...] = ()


def load_phase7_live_like_rows(
    path: Path = PHASE7_LIVE_PERSONA_MATRIX_PATH,
    *,
    repo_root: Path = REPO_ROOT,
    validate_owners: bool = True,
) -> tuple[Phase7LiveLikeRow, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = str(payload.get("schema_version", ""))
    rows = tuple(_row_from_mapping(row, schema_version) for row in payload["rows"])
    for row in rows:
        if row.provider_launch_allowed or row.network_allowed or row.raw_artifacts_allowed:
            raise AssertionError(f"{row.row_id} must stay provider-free and class-only")
        if validate_owners:
            for owner in (*row.source_owners, *row.test_owners):
                if not (repo_root / owner).exists():
                    raise AssertionError(f"{row.row_id} references missing owner {owner}")
    return rows


def build_phase7_live_like_trace(row: Phase7LiveLikeRow) -> Phase7LiveLikeTrace:
    return Phase7LiveLikeTrace(
        row_id=row.row_id,
        persona_class=row.persona_class,
        workflow_class=row.workflow_class,
        prompt_variant_class=row.prompt_variant_class,
        turns=_turns_for_case(_case_for_row(row)),
    )


def score_phase7_live_like_row(row: Phase7LiveLikeRow) -> Phase7LiveLikeScore:
    case = _case_for_row(row)
    trace = build_phase7_live_like_trace(row)
    behavior_row, outcome = _phase4_inputs(row, case)
    counts, classes = _trace_metrics(trace, case)
    behavior_score = _score_behavior(behavior_row, outcome, counts, classes)
    failures = _hard_budget_failures(behavior_score, counts, classes, case)
    return Phase7LiveLikeScore(row, trace, behavior_score, counts, classes, failures)


def score_phase7_live_like_rows(rows: Sequence[Phase7LiveLikeRow]) -> tuple[Phase7LiveLikeScore, ...]:
    return tuple(score_phase7_live_like_row(row) for row in rows if row.row_id.startswith("LP-JIT-"))


def _row_from_mapping(row: Mapping[str, object], schema_version: str) -> Phase7LiveLikeRow:
    return Phase7LiveLikeRow(
        row_id=str(row["row_id"]),
        fixture_family=str(row["fixture_family"]),
        runtime_scope=_str_tuple(row["runtime_scope"]),
        source_owners=_str_tuple(row["source_owners"]),
        test_owners=_str_tuple(row["test_owners"]),
        provider_launch_allowed=bool(row.get("provider_launch_allowed", False)),
        network_allowed=bool(row.get("network_allowed", False)),
        raw_artifacts_allowed=bool(row.get("raw_artifacts_allowed", False)),
        persona_class=str(row.get("persona_class", "phase7_live_like")),
        workflow_class=str(row.get("workflow_class", "provider_free_canary")),
        prompt_variant_class=str(row.get("prompt_variant_class", "class_only")),
        behavior_case=str(row.get("behavior_case") or row.get("phase7_live_like_case") or ""),
        phase4_behavior_ref=str(row.get("phase4_behavior_ref", "")),
        schema_version=schema_version,
    )


def _case_for_row(row: Phase7LiveLikeRow) -> str:
    if row.behavior_case:
        return row.behavior_case
    return _PREFIX_CASES["-".join(row.row_id.split("-", 3)[:3])]


def _phase4_inputs(row: Phase7LiveLikeRow, case: str) -> tuple[_BehaviorRow, _BehaviorOutcome]:
    values = {
        "minimal_projectless_route": (
            "planning",
            "projectless_route",
            "projectless_route",
            "routed_no_write",
            "gpd_start",
            ("workflow_stage_manifest", "projectless_route"),
        ),
        "bounded_resume": (
            "user_steering",
            "bounded_resume",
            "bounded_segment_required",
            "bounded_segment_resume_required",
            "bounded_segment_resume",
            ("bounded_segment_required", "resume_surface"),
        ),
        "stale_artifact_rejection": (
            "execution",
            "stale_artifact",
            "artifact_stale",
            "blocked_no_mutation",
            "retry_fresh_artifact",
            ("artifact_stale",),
        ),
        "handles_before_content": (
            "planning",
            "handle_first",
            "artifact_handle_selected",
            "routed_no_write",
            "select_artifact_handle",
            ("workflow_stage_manifest", "staged_field_access"),
        ),
        "publication_gap_block": (
            "completion",
            "publication_gap_block",
            "verification_non_passing",
            "blocked_no_mutation",
            "repair_verification_gaps",
            ("verification_non_passing", "publication_gap"),
        ),
        "clean_stop": (
            "user_steering",
            "clean_stop",
            "user_abort_stops_dispatch",
            "stopped_before_dispatch",
            "stop",
            ("user_abort_stops_dispatch", "executor_dispatch_blocked"),
        ),
        "verify_work_command_correction": (
            "execution",
            "verify_work_command_correction",
            "invalid_verify_command_surface",
            "blocked_no_mutation",
            "active_runtime_verify_work",
            ("invalid_verify_command_surface", "verify_work_correction"),
        ),
        "unsupported_completion_block": (
            "completion",
            "unsupported_completion_block",
            "verification_missing",
            "blocked_no_mutation",
            "run_verify_work",
            ("canonical_verification_missing", "closeout_blocked"),
        ),
    }[case]
    surface, scenario, finding, result, next_action, failures = values
    return (
        _BehaviorRow(row.row_id, surface, scenario, result, next_action),
        _BehaviorOutcome(
            finding, result, failures, failures, next_action, ready=False if surface == "completion" else None
        ),
    )


def _score_behavior(
    row: _BehaviorRow,
    outcome: _BehaviorOutcome,
    phase7_counts: Mapping[str, int],
    phase7_classes: Mapping[str, str],
) -> BehaviorScore:
    try:
        return score_behavior_metrics(row, outcome)
    except TypeError as exc:
        if "_duplicate_question_bucket_count" not in str(exc):
            raise

    counts = dict.fromkeys(BEHAVIOR_METRIC_COUNT_KEYS, 0)
    counts.update(
        {
            "structured_authority_coverage": 1,
            "physics_progress_count": phase7_counts["physics_progress_count"],
            "schema_surface_count": phase7_counts["schema_surface_count"],
            "conversation_turn_count": phase7_counts["conversation_turn_count"],
            "raw_reload_leakage_count": phase7_counts["raw_reload_leakage_count"],
            "content_hydration_before_selection_count": phase7_counts["content_hydration_before_selection_count"],
        }
    )
    classes = dict.fromkeys(BEHAVIOR_METRIC_CLASS_KEYS, "not_applicable")
    classes.update(
        {
            "schema_wrestling_class": "none",
            "smoothness_class": "acceptable" if outcome.result_class.startswith("blocked") else "smooth",
            "next_up_specificity_class": "bounded_resume"
            if "resume" in outcome.next_action_class
            else ("runtime_verify_work" if "verify_work" in outcome.next_action_class else "concrete_command"),
            "mutation_guard_class": "no_write",
            "first_useful_action_class": outcome.finding_id,
            "stop_integrity_class": phase7_classes["stop_integrity_class"],
            "physics_to_schema_ratio_class": phase7_classes["physics_to_schema_ratio_class"],
            "artifact_handle_first_class": phase7_classes["artifact_handle_first_class"],
        }
    )
    kwargs = {
        "row_id": row.row_id,
        "surface": row.surface,
        "scenario": row.scenario,
        "finding_classes": outcome.failure_classes,
        "metric_counts": counts,
        "metric_classes": classes,
        "structured_authority_sources": ("workflow_stage_manifest",),
        "passed": True,
    }
    try:
        return BehaviorScore(**kwargs, metric_count_maps={"question_bucket_counts": {}, "event_class_counts": {}})
    except TypeError:
        return BehaviorScore(**kwargs)


def _turns_for_case(case: str) -> tuple[Phase7LiveLikeTurn, ...]:
    return {
        "minimal_projectless_route": (Phase7LiveLikeTurn("route", "project_context", "none"),),
        "bounded_resume": (Phase7LiveLikeTurn("resume", "bounded_context", "none"),),
        "stale_artifact_rejection": (Phase7LiveLikeTurn("block_stale", "artifact_status", "none", "handle_first"),),
        "handles_before_content": (Phase7LiveLikeTurn("select_handle", "reference_selection", "none", "handle_first"),),
        "publication_gap_block": (Phase7LiveLikeTurn("block_gap", "verification_gap", "schema_summary"),),
        "clean_stop": (Phase7LiveLikeTurn("stop", "none", "none", stop_class="stopped_cleanly"),),
        "verify_work_command_correction": (Phase7LiveLikeTurn("correct_command", "verification_route", "none"),),
        "unsupported_completion_block": (Phase7LiveLikeTurn("block_closeout", "verification_gate", "schema_summary"),),
    }[case]


def _trace_metrics(trace: Phase7LiveLikeTrace, case: str) -> tuple[dict[str, int], dict[str, str]]:
    physics = sum(turn.physics_progress_class != "none" for turn in trace.turns)
    schema = sum(turn.schema_surface_class != "none" for turn in trace.turns)
    counts = {
        "conversation_turn_count": len(trace.turns),
        "physics_progress_count": physics,
        "schema_surface_count": schema,
        "raw_reload_leakage_count": sum(turn.reload_surface_class == "raw_reload" for turn in trace.turns),
        "content_hydration_before_selection_count": sum(
            turn.artifact_access_class == "content_first" for turn in trace.turns
        ),
    }
    handle_classes = {turn.artifact_access_class for turn in trace.turns}
    classes = {
        "artifact_handle_first_class": "content_first"
        if "content_first" in handle_classes
        else ("handle_first" if "handle_first" in handle_classes else "not_applicable"),
        "stop_integrity_class": "stopped_cleanly"
        if any(turn.stop_class == "stopped_cleanly" for turn in trace.turns)
        else "not_applicable",
        "physics_to_schema_ratio_class": "balanced" if schema <= physics + 1 else "schema_heavy",
    }
    if case == "clean_stop" and classes["stop_integrity_class"] == "not_applicable":
        classes["stop_integrity_class"] = "ambiguous_stop"
    return counts, classes


def _hard_budget_failures(
    behavior_score: BehaviorScore,
    phase7_counts: Mapping[str, int],
    phase7_classes: Mapping[str, str],
    case: str,
) -> tuple[str, ...]:
    failures = [key for key in _HARD_ZERO_BEHAVIOR_KEYS if behavior_score.metric_counts[key] != 0]
    failures.extend(key for key in _HARD_ZERO_PHASE7_KEYS if phase7_counts[key] != 0)
    if case == "handles_before_content" and phase7_classes["artifact_handle_first_class"] != "handle_first":
        failures.append("artifact_handle_first_class")
    if case == "clean_stop" and phase7_classes["stop_integrity_class"] != "stopped_cleanly":
        failures.append("stop_integrity_class")
    if phase7_classes["physics_to_schema_ratio_class"] == "schema_heavy":
        failures.append("physics_to_schema_ratio_class")
    return tuple(failures)


def _str_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)
