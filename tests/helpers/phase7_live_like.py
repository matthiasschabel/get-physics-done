"""Provider-free Phase 7 live-like rows scored through Phase 4 behavior metrics."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from tests.helpers.persona_trace import (
    FakePersonaTrace,
    FakePersonaTurn,
    artifact_handle_first_class,
    content_hydration_before_selection_count,
    conversation_turn_count,
    physics_progress_count,
    physics_to_schema_ratio_class,
    raw_reload_leakage_count,
    schema_surface_count,
    stop_integrity_class,
)
from tests.helpers.phase4_persona.behavior_metrics import (
    BEHAVIOR_METRIC_CLASS_KEYS,
    BEHAVIOR_METRIC_COUNT_KEYS,
    BehaviorScore,
    score_behavior_metrics,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE7_LIVE_PERSONA_MATRIX_PATH = REPO_ROOT / "tests" / "fixtures" / "phase7_live_persona_matrix.json"
ROW_TIERS = frozenset({"required_base", "jit_canary", "experimental"})
REQUIRED_BASE_ROW_PREFIXES = frozenset(f"LP{index:02d}" for index in range(1, 13))
REQUIRED_LP_JIT_ROW_IDS = frozenset(f"LP-JIT-{index:02d}" for index in range(1, 9))
REQUIRED_P6_JIT_ROW_IDS = frozenset(
    {
        "P6-PLAN-JIT-01",
        "P6-PLAN-JIT-02",
        "P6-PLAN-JIT-03",
        "P6-PLAN-JIT-04",
        "P6-EXEC-JIT-01",
        "P6-EXEC-JIT-02",
        "P6-EXEC-JIT-03",
        "P6-EXEC-JIT-04",
        "P6-COMP-JIT-01",
        "P6-COMP-JIT-02",
        "P6-COMP-JIT-03",
        "P6-COMP-JIT-04",
        "P6-RES-JIT-01",
        "P6-RES-JIT-02",
        "P6-RES-JIT-03",
        "P6-RES-JIT-04",
        "P6-RES-JIT-05",
    }
)
REQUIRED_P7_NEXTUP_JIT_ROW_IDS = frozenset(
    {
        "P7-NEXTUP-JIT-01",
        "P7-NEXTUP-JIT-02",
        "P7-NEXTUP-JIT-03",
        "P7-NEXTUP-JIT-04",
        "P7-NEXTUP-JIT-05",
    }
)
REQUIRED_JIT_ROW_IDS = REQUIRED_LP_JIT_ROW_IDS | REQUIRED_P6_JIT_ROW_IDS | REQUIRED_P7_NEXTUP_JIT_ROW_IDS
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
    row_tier: str = "required_base"
    provider_launch_allowed: bool = False
    network_allowed: bool = False
    raw_artifacts_allowed: bool = False
    persona_class: str = "phase7_live_like"
    workflow_class: str = "provider_free_canary"
    prompt_variant_class: str = "class_only"
    behavior_case: str = ""
    phase4_behavior_ref: str = ""
    behavior_metric_bounds: Mapping[str, object] = field(default_factory=dict)
    schema_version: str = "phase7.live_persona_matrix.v1"


@dataclass(frozen=True, slots=True)
class Phase7LiveLikeScore:
    row: Phase7LiveLikeRow
    trace: FakePersonaTrace
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
    read_only: bool | None = True
    mutated: bool = False
    mutation_allowed: bool = False
    state_status_class: str | None = "unchanged"
    commands: tuple[str, ...] = ()


# fmt: off
_BEHAVIOR_CASES = {
    "minimal_projectless_route": ("planning", "projectless_route", "projectless_route", "routed_no_write", "gpd_start", ("workflow_stage_manifest", "projectless_route")),
    "bounded_resume": ("user_steering", "bounded_resume", "bounded_segment_required", "bounded_segment_resume_required", "bounded_segment_resume", ("bounded_segment_required", "resume_surface")),
    "stale_artifact_rejection": ("execution", "stale_artifact", "artifact_stale", "blocked_no_mutation", "retry_fresh_artifact", ("artifact_stale",)),
    "handles_before_content": ("planning", "handle_first", "artifact_handle_selected", "routed_no_write", "select_artifact_handle", ("workflow_stage_manifest", "staged_field_access")),
    "publication_gap_block": ("completion", "publication_gap_block", "verification_non_passing", "blocked_no_mutation", "repair_verification_gaps", ("verification_non_passing", "publication_gap")),
    "clean_stop": ("user_steering", "clean_stop", "user_abort_stops_dispatch", "stopped_before_dispatch", "stop", ("user_abort_stops_dispatch", "executor_dispatch_blocked")),
    "verify_work_command_correction": ("execution", "verify_work_command_correction", "invalid_verify_command_surface", "blocked_no_mutation", "active_runtime_verify_work", ("invalid_verify_command_surface", "verify_work_correction")),
    "unsupported_completion_block": ("completion", "unsupported_completion_block", "verification_missing", "blocked_no_mutation", "run_verify_work", ("canonical_verification_missing", "closeout_blocked")),
    "p6_plan_schema_averse_phase_bootstrap": ("planning", "p6_plan_schema_averse_phase_bootstrap", "phase_bootstrap_jit", "routed_no_write", "concrete_command", ("workflow_stage_manifest", "phase_bootstrap")),
    "p6_plan_blocker_next_action": ("planning", "p6_plan_blocker_next_action", "blocker_next_action", "blocked_no_mutation", "concrete_command", ("phase_blocker", "no_plan_invention")),
    "p6_plan_proof_checker_deferred": ("planning", "p6_plan_proof_checker_deferred", "proof_checker_deferred_to_checker_stage", "routed_no_write", "concrete_command", ("proof_bearing_visibility", "checker_stage_only")),
    "p6_plan_context_recovery_handles": ("planning", "p6_plan_context_recovery_handles", "state_handles_first", "routed_no_write", "concrete_command", ("state_handles", "no_raw_reload")),
    "p6_exec_wave_planning_before_dispatch": ("execution", "p6_exec_wave_planning_before_dispatch", "wave_planning_before_dispatch", "accepted", "runtime_verify_work", ("wave_planning", "valid_return_required")),
    "p6_exec_stale_artifact_rejection": ("execution", "p6_exec_stale_artifact_rejection", "artifact_stale", "blocked_no_mutation", "retry_fresh_artifact", ("artifact_stale",)),
    "p6_exec_stop_after_first_result": ("user_steering", "p6_exec_stop_after_first_result", "user_abort_stops_dispatch", "stopped_before_dispatch", "bounded_segment_resume", ("user_abort_stops_dispatch", "bounded_segment_required")),
    "p6_exec_runtime_verify_work_correction": ("execution", "p6_exec_runtime_verify_work_correction", "invalid_verify_command_surface", "blocked_no_mutation", "active_runtime_verify_work", ("invalid_verify_command_surface", "verify_work_correction")),
    "p6_comp_missing_verification_blocks": ("completion", "p6_comp_missing_verification_blocks", "verification_missing", "blocked_no_mutation", "run_verify_work", ("canonical_verification_missing", "closeout_blocked")),
    "p6_comp_nonpassing_verification_blocks": ("completion", "p6_comp_nonpassing_verification_blocks", "verification_non_passing", "blocked_no_mutation", "run_verify_work", ("verification_non_passing", "closeout_blocked")),
    "p6_comp_proof_redteam_required": ("completion", "p6_comp_proof_redteam_required", "proof_redteam_not_passed", "blocked_no_mutation", "run_verify_work", ("proof_redteam_not_passed", "closeout_blocked")),
    "p6_comp_clean_closeout_smallest_step": ("completion", "p6_comp_clean_closeout_smallest_step", "closeout_readiness_read_only", "ready_closeout", "local_phase_complete", ("phase_closeout_readiness", "local_transition")),
    "p6_res_existing_work_mapper_bootstrap": ("planning", "p6_res_existing_work_mapper_bootstrap", "existing_work_routed_first", "routed_no_write", "concrete_command", ("map_bootstrap", "existing_work_handles")),
    "p6_res_reference_handle_first": ("planning", "p6_res_reference_handle_first", "artifact_handle_selected", "routed_no_write", "select_artifact_handle", ("reference_handles", "content_deferred")),
    "p6_res_phase_gap_closer": ("planning", "p6_res_phase_gap_closer", "phase_research_handoff_only", "routed_no_write", "concrete_command", ("research_phase_handoff", "single_research_artifact")),
    "p6_res_contract_blocked_diagnostic": ("planning", "p6_res_contract_blocked_diagnostic", "planning_authority_blocked", "blocked_no_mutation", "concrete_command", ("project_contract_blocked", "no_downstream_spawn")),
    "p6_res_publication_gap_handles": ("planning", "p6_res_publication_gap_handles", "publication_gap_handles_first", "routed_no_write", "concrete_command", ("publication_gap", "reference_handles")),
    "p7_nextup_wrong_verify_command_correction": ("execution", "p7_nextup_wrong_verify_command_correction", "invalid_verify_command_surface", "corrected_runtime_route", "runtime_verify_work", ("invalid_verify_command_surface", "verify_work_correction")),
    "p7_nextup_blocked_closeout_missing_verification": ("completion", "p7_nextup_blocked_closeout_missing_verification", "verification_missing", "blocked_no_mutation", "runtime_verify_work", ("canonical_verification_missing", "closeout_blocked")),
    "p7_nextup_blocked_closeout_nonpassing_verification": ("completion", "p7_nextup_blocked_closeout_nonpassing_verification", "verification_non_passing", "blocked_no_mutation", "runtime_verify_work", ("verification_non_passing", "closeout_blocked")),
    "p7_nextup_ready_closeout_local_transition": ("completion", "p7_nextup_ready_closeout_local_transition", "closeout_readiness_read_only", "ready_closeout", "local_phase_complete", ("phase_closeout_readiness", "local_transition")),
    "p7_nextup_public_render_no_raw_reload": ("completion", "p7_nextup_public_render_no_raw_reload", "public_next_up_no_raw_reload", "routed_no_write", "runtime_verify_work", ("no_raw_reload", "command_hint")),
}
# fmt: on

_P7_NEXTUP_CLASSES = {
    "p7_nextup_wrong_verify_command_correction": {
        "structural_verify_phase_class": "structural_verify_phase_display_only",
        "rendered_public_structural_verify_class": "no_structural_verify_phase",
        "primary_owner_class": "runtime",
        "primary_action_class": "verify_work",
        "stage_stop_runtime_class": "runtime",
    },
    "p7_nextup_blocked_closeout_missing_verification": {
        "rendered_public_structural_verify_class": "no_structural_verify_phase",
        "primary_owner_class": "runtime",
        "primary_action_class": "verify_work",
        "stage_stop_runtime_class": "runtime",
    },
    "p7_nextup_blocked_closeout_nonpassing_verification": {
        "rendered_public_structural_verify_class": "no_structural_verify_phase",
        "primary_owner_class": "runtime",
        "primary_action_class": "verify_work",
        "stage_stop_runtime_class": "runtime",
    },
    "p7_nextup_ready_closeout_local_transition": {
        "primary_owner_class": "local_transition",
        "primary_action_class": "phase_complete",
        "after_this_completes_owner_class": "runtime",
        "stage_stop_runtime_class": "runtime",
    },
    "p7_nextup_public_render_no_raw_reload": {
        "display_only_filter_class": "display_only_filtered",
        "rendered_public_structural_verify_class": "no_structural_verify_phase",
        "primary_owner_class": "runtime",
        "primary_action_class": "verify_work",
        "stage_stop_runtime_class": "runtime",
    },
}


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
        if row.row_tier not in ROW_TIERS:
            raise AssertionError(f"{row.row_id} has invalid row_tier {row.row_tier}")
        if row.provider_launch_allowed or row.network_allowed or row.raw_artifacts_allowed:
            raise AssertionError(f"{row.row_id} must stay provider-free and class-only")
        if validate_owners:
            for owner in (*row.source_owners, *row.test_owners):
                if not (repo_root / owner).exists():
                    raise AssertionError(f"{row.row_id} references missing owner {owner}")
    return rows


def build_phase7_live_like_trace(row: Phase7LiveLikeRow) -> FakePersonaTrace:
    return FakePersonaTrace(
        row_id=row.row_id,
        persona_class=row.persona_class,
        prompt_variant_class=row.prompt_variant_class,
        turns=_turns_for_case(_case_for_row(row)),
    )


def score_phase7_live_like_row(
    row: Phase7LiveLikeRow,
    *,
    trace_override: FakePersonaTrace | None = None,
    behavior_outcome_override: _BehaviorOutcome | None = None,
    source_text_override: str | None = None,
) -> Phase7LiveLikeScore:
    case = _case_for_row(row)
    trace = trace_override or build_phase7_live_like_trace(row)
    behavior_row, outcome = _phase4_inputs(row, case)
    if behavior_outcome_override is not None:
        outcome = behavior_outcome_override
    counts, classes = _trace_metrics(trace, case, rendered_text=source_text_override)
    classes.update(_P7_NEXTUP_CLASSES.get(case, {}))
    behavior_score = _score_behavior(
        behavior_row,
        outcome,
        trace,
        source_text=source_text_override,
    )
    failures = _hard_budget_failures(behavior_score, counts, classes, row, case)
    return Phase7LiveLikeScore(row, trace, behavior_score, counts, classes, failures)


def score_phase7_live_like_rows(rows: Sequence[Phase7LiveLikeRow]) -> tuple[Phase7LiveLikeScore, ...]:
    return tuple(score_phase7_live_like_row(row) for row in rows if row.row_tier == "jit_canary")


def _row_from_mapping(row: Mapping[str, object], schema_version: str) -> Phase7LiveLikeRow:
    return Phase7LiveLikeRow(
        row_id=str(row["row_id"]),
        fixture_family=str(row["fixture_family"]),
        runtime_scope=_str_tuple(row["runtime_scope"]),
        source_owners=_str_tuple(row["source_owners"]),
        test_owners=_str_tuple(row["test_owners"]),
        row_tier=str(row.get("row_tier") or _default_row_tier(str(row["row_id"]))),
        provider_launch_allowed=bool(row.get("provider_launch_allowed", False)),
        network_allowed=bool(row.get("network_allowed", False)),
        raw_artifacts_allowed=bool(row.get("raw_artifacts_allowed", False)),
        persona_class=str(row.get("persona_class", "phase7_live_like")),
        workflow_class=str(row.get("workflow_class", "provider_free_canary")),
        prompt_variant_class=str(row.get("prompt_variant_class", "class_only")),
        behavior_case=str(row.get("behavior_case") or row.get("phase7_live_like_case") or ""),
        phase4_behavior_ref=str(row.get("phase4_behavior_ref", "")),
        behavior_metric_bounds=dict(row.get("behavior_metric_bounds", {})),
        schema_version=schema_version,
    )


def _case_for_row(row: Phase7LiveLikeRow) -> str:
    if row.behavior_case:
        return row.behavior_case
    return _PREFIX_CASES["-".join(row.row_id.split("-", 3)[:3])]


def _default_row_tier(row_id: str) -> str:
    if row_id.startswith("LP-JIT-") or (row_id.startswith("P6-") and "-JIT-" in row_id):
        return "jit_canary"
    if row_id.split("-", 1)[0] in REQUIRED_BASE_ROW_PREFIXES:
        return "required_base"
    return "experimental"


def _phase4_inputs(row: Phase7LiveLikeRow, case: str) -> tuple[_BehaviorRow, _BehaviorOutcome]:
    surface, scenario, finding, result, next_action, failures = _BEHAVIOR_CASES[case]
    accepted = result == "accepted"
    ready = True if result == "ready_closeout" else (False if surface == "completion" else None)
    state_status_class = "accepted_no_write" if accepted else ("read_only" if ready else "unchanged")
    return (
        _BehaviorRow(row.row_id, surface, scenario, result, next_action),
        _BehaviorOutcome(
            finding,
            result,
            failures,
            failures,
            next_action,
            accepted=accepted,
            ready=ready,
            state_status_class=state_status_class,
        ),
    )


def _score_behavior(
    row: _BehaviorRow,
    outcome: _BehaviorOutcome,
    trace: FakePersonaTrace,
    *,
    source_text: str | None = None,
) -> BehaviorScore:
    try:
        return score_behavior_metrics(row, outcome, event=trace, source_text=source_text)
    except TypeError as exc:
        if "_duplicate_question_bucket_count" not in str(exc):
            raise

    counts = dict.fromkeys(BEHAVIOR_METRIC_COUNT_KEYS, 0)
    counts.update(
        {
            "structured_authority_coverage": 1,
            "physics_progress_count": physics_progress_count(trace),
            "schema_surface_count": schema_surface_count(trace),
            "conversation_turn_count": conversation_turn_count(trace),
            "raw_reload_leakage_count": raw_reload_leakage_count(trace),
            "content_hydration_before_selection_count": content_hydration_before_selection_count(trace),
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
            "stop_integrity_class": stop_integrity_class(trace),
            "physics_to_schema_ratio_class": physics_to_schema_ratio_class(trace),
            "artifact_handle_first_class": artifact_handle_first_class(trace),
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


def _turns_for_case(case: str) -> tuple[FakePersonaTurn, ...]:
    def turn(index: int, intent: str, action: str, physics: str, **classes: str) -> FakePersonaTurn:
        return FakePersonaTurn(
            turn_index=index,
            speaker_class="assistant",
            intent_class=intent,
            action_class=action,
            physics_progress_class=physics,
            **classes,
        )

    # fmt: off
    return {
        "minimal_projectless_route": (turn(0, "projectless_route", "concrete_command", "project_context"),),
        "bounded_resume": (turn(0, "bounded_resume", "bounded_resume", "bounded_context"),),
        "stale_artifact_rejection": (turn(0, "stale_artifact_rejection", "concrete_command", "artifact_status"),),
        "handles_before_content": (turn(0, "reference_choice", "select_reference", "reference_selection", artifact_handle_class="handle_selected"), turn(1, "reference_review", "concrete_command", "artifact_verified", content_hydration_class="content_loaded")),
        "publication_gap_block": (turn(0, "publication_gap_block", "concrete_command", "verification_gap", schema_surface_class="schema_summary"),),
        "clean_stop": (turn(0, "abort_acknowledged", "stop", "stop_acknowledged", stop_class="user_abort_stops_dispatch"),),
        "verify_work_command_correction": (turn(0, "verify_work_command_correction", "concrete_command", "verification_route"),),
        "unsupported_completion_block": (turn(0, "unsupported_completion_block", "concrete_command", "verification_gate", schema_surface_class="schema_summary"),),
        "p6_plan_schema_averse_phase_bootstrap": (turn(0, "phase_bootstrap", "concrete_command", "phase_bootstrap"),),
        "p6_plan_blocker_next_action": (turn(0, "blocker_next_action", "concrete_command", "blocker_diagnosed"),),
        "p6_plan_proof_checker_deferred": (turn(0, "proof_checker_visibility", "concrete_command", "proof_stage_routed"),),
        "p6_plan_context_recovery_handles": (turn(0, "state_handle_recovery", "concrete_command", "state_handles"),),
        "p6_exec_wave_planning_before_dispatch": (turn(0, "wave_planning", "runtime_verify_work", "wave_planned"),),
        "p6_exec_stale_artifact_rejection": (turn(0, "stale_artifact_rejection", "concrete_command", "artifact_status"),),
        "p6_exec_stop_after_first_result": (turn(0, "abort_acknowledged", "stop", "stop_acknowledged", stop_class="user_abort_stops_dispatch"),),
        "p6_exec_runtime_verify_work_correction": (turn(0, "verify_work_command_correction", "concrete_command", "verification_route"),),
        "p6_comp_missing_verification_blocks": (turn(0, "missing_verification_gate", "concrete_command", "verification_gate", schema_surface_class="schema_summary"),),
        "p6_comp_nonpassing_verification_blocks": (turn(0, "nonpassing_verification_gate", "concrete_command", "verification_gate", schema_surface_class="schema_summary"),),
        "p6_comp_proof_redteam_required": (turn(0, "proof_redteam_gate", "concrete_command", "verification_gate", schema_surface_class="schema_summary"),),
        "p6_comp_clean_closeout_smallest_step": (turn(0, "clean_closeout", "concrete_command", "closeout_ready"),),
        "p6_res_existing_work_mapper_bootstrap": (turn(0, "existing_work_mapping", "concrete_command", "existing_work_mapped"),),
        "p6_res_reference_handle_first": (turn(0, "reference_choice", "select_reference", "reference_selection", artifact_handle_class="handle_selected"), turn(1, "reference_review", "concrete_command", "artifact_verified", content_hydration_class="content_loaded")),
        "p6_res_phase_gap_closer": (turn(0, "research_handoff_choice", "select_reference", "reference_selection", artifact_handle_class="handle_selected"), turn(1, "research_gap_closure", "concrete_command", "research_handoff", content_hydration_class="content_loaded")),
        "p6_res_contract_blocked_diagnostic": (turn(0, "contract_blocked_diagnostic", "concrete_command", "contract_diagnostic"),),
        "p6_res_publication_gap_handles": (turn(0, "publication_gap_choice", "select_reference", "reference_selection", artifact_handle_class="handle_selected"), turn(1, "publication_gap_research", "concrete_command", "publication_gap", content_hydration_class="content_loaded")),
        "p7_nextup_wrong_verify_command_correction": (turn(0, "verify_work_command_correction", "runtime_verify_work", "verification_route"),),
        "p7_nextup_blocked_closeout_missing_verification": (turn(0, "missing_verification_gate", "runtime_verify_work", "verification_gate"),),
        "p7_nextup_blocked_closeout_nonpassing_verification": (turn(0, "nonpassing_verification_gate", "runtime_verify_work", "verification_gate"),),
        "p7_nextup_ready_closeout_local_transition": (turn(0, "clean_closeout", "concrete_command", "closeout_ready"),),
        "p7_nextup_public_render_no_raw_reload": (turn(0, "public_next_up_render", "runtime_verify_work", "verification_route"),),
    }[case]
    # fmt: on


def _trace_metrics(
    trace: FakePersonaTrace,
    case: str,
    *,
    rendered_text: str | None = None,
) -> tuple[dict[str, int], dict[str, str]]:
    physics = physics_progress_count(trace)
    schema = schema_surface_count(trace)
    shared_artifact_class = artifact_handle_first_class(trace)
    rendered_raw_reload_count = _rendered_raw_reload_leakage_count(rendered_text)
    counts = {
        "conversation_turn_count": conversation_turn_count(trace),
        "physics_progress_count": physics,
        "schema_surface_count": schema,
        "raw_reload_leakage_count": raw_reload_leakage_count(trace) + rendered_raw_reload_count,
        "content_hydration_before_selection_count": content_hydration_before_selection_count(trace),
    }
    classes = {
        "artifact_handle_first_class": _phase7_artifact_handle_first_class(shared_artifact_class),
        "stop_integrity_class": stop_integrity_class(trace),
        "physics_to_schema_ratio_class": "balanced" if schema <= physics + 1 else "schema_heavy",
        "rendered_public_raw_reload_class": "raw_reload_leaked" if rendered_raw_reload_count else "no_raw_reload",
        "rendered_public_structural_verify_class": _rendered_structural_verify_class(rendered_text),
    }
    if case == "clean_stop" and classes["stop_integrity_class"] == "not_applicable":
        classes["stop_integrity_class"] = "ambiguous_stop"
    return counts, classes


def _phase7_artifact_handle_first_class(shared_class: str) -> str:
    if shared_class == "handle_before_content":
        return "handle_first"
    if shared_class == "content_before_handle":
        return "content_first"
    if shared_class == "missing_handle":
        return "missing_handle"
    return "not_applicable"


def _rendered_raw_reload_leakage_count(rendered_text: str | None) -> int:
    if not rendered_text:
        return 0
    lowered = rendered_text.lower()
    count = 0
    if "gpd --raw init" in lowered or "--raw init" in lowered:
        count += 1
    if "gpd --raw stage field-access" in lowered or "--raw stage field-access" in lowered:
        count += 1
    return count


def _rendered_structural_verify_class(rendered_text: str | None) -> str:
    if not rendered_text:
        return "not_applicable"
    lowered = rendered_text.lower()
    if "gpd verify phase" in lowered or "gpd:verify-phase" in lowered:
        return "structural_verify_phase_leaked"
    return "no_structural_verify_phase"


def _hard_budget_failures(
    behavior_score: BehaviorScore,
    phase7_counts: Mapping[str, int],
    phase7_classes: Mapping[str, str],
    row: Phase7LiveLikeRow,
    case: str,
) -> tuple[str, ...]:
    failures = [key for key in _HARD_ZERO_BEHAVIOR_KEYS if behavior_score.metric_counts[key] != 0]
    failures.extend(key for key in _HARD_ZERO_PHASE7_KEYS if phase7_counts[key] != 0)
    failures.extend(_row_metric_bound_failures(row.behavior_metric_bounds, behavior_score, phase7_counts))
    handle_first_cases = {
        "handles_before_content",
        "p6_res_reference_handle_first",
        "p6_res_phase_gap_closer",
        "p6_res_publication_gap_handles",
    }
    clean_stop_cases = {"clean_stop", "p6_exec_stop_after_first_result"}
    if case in handle_first_cases and phase7_classes["artifact_handle_first_class"] != "handle_first":
        failures.append("artifact_handle_first_class")
    if case in clean_stop_cases and phase7_classes["stop_integrity_class"] != "stopped_cleanly":
        failures.append("stop_integrity_class")
    if phase7_classes["physics_to_schema_ratio_class"] == "schema_heavy":
        failures.append("physics_to_schema_ratio_class")
    return tuple(dict.fromkeys(failures))


def _row_metric_bound_failures(
    bounds: Mapping[str, object],
    behavior_score: BehaviorScore,
    phase7_counts: Mapping[str, int],
) -> tuple[str, ...]:
    failures: list[str] = []
    for metric_key, raw_bound in bounds.items():
        bound = _metric_bound(raw_bound)
        observed_counts: list[int] = []
        if metric_key in behavior_score.metric_counts:
            observed_counts.append(int(behavior_score.metric_counts[metric_key]))
        if metric_key in phase7_counts:
            observed_counts.append(int(phase7_counts[metric_key]))
        if not observed_counts:
            failures.append(metric_key)
            continue
        if any(not _metric_bound_allows(bound, observed) for observed in observed_counts):
            failures.append(metric_key)
    return tuple(failures)


def _metric_bound(raw_bound: object) -> dict[str, int | None]:
    if isinstance(raw_bound, Mapping):
        return {
            "exact": _optional_int(raw_bound.get("exact")),
            "min": _optional_int(raw_bound.get("min")),
            "max": _optional_int(raw_bound.get("max")),
        }
    count = int(raw_bound)
    if count == 0:
        return {"exact": 0, "min": None, "max": None}
    return {"exact": None, "min": count, "max": None}


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)


def _metric_bound_allows(bound: Mapping[str, int | None], observed: int) -> bool:
    exact = bound.get("exact")
    minimum = bound.get("min")
    maximum = bound.get("max")
    if exact is not None and observed != exact:
        return False
    if minimum is not None and observed < minimum:
        return False
    if maximum is not None and observed > maximum:
        return False
    return True


def _str_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)
