"""Provider-free Phase 7 live-like adapter tests."""

from __future__ import annotations

import inspect
import json
from dataclasses import fields
from pathlib import Path

from gpd.core.context import init_literature_review
from gpd.core.staged_init_assembly import (
    StagedInitAssemblyContext,
    StagedInitProvider,
    assemble_staged_init_payload,
)
from gpd.core.workflow_staging import (
    WORKFLOW_STAGE_MANIFEST_DIR,
    WORKFLOW_STAGE_MANIFEST_SUFFIX,
    WorkflowStage,
    WorkflowStageManifest,
    load_workflow_stage_manifest,
)
from tests.helpers import phase7_live_like
from tests.helpers.persona_trace import FakePersonaTrace, FakePersonaTurn
from tests.helpers.phase7_live_like import (
    PHASE7_LIVE_PERSONA_MATRIX_PATH,
    REQUIRED_JIT_ROW_IDS,
    REQUIRED_LP_JIT_ROW_IDS,
    REQUIRED_P6_JIT_ROW_IDS,
    REQUIRED_P7_NEXTUP_JIT_ROW_IDS,
    ROW_TIERS,
    Phase7LiveLikeRow,
    load_phase7_live_like_rows,
    score_phase7_live_like_row,
    score_phase7_live_like_rows,
)

REFERENCE_FILE_FIELD = "reference_artifact_files"
REFERENCE_CONTENT_FIELD = "reference_artifacts_content"


def test_phase7_live_like_loader_consumes_tracked_matrix() -> None:
    rows = load_phase7_live_like_rows()

    assert {row.row_id for row in rows} >= {"LP01-START-PROJECTLESS-READONLY", "LP12-GEMINI-POLICY-DENIAL"}
    assert {row.row_id for row in rows} >= REQUIRED_JIT_ROW_IDS
    assert {row.row_tier for row in rows} <= ROW_TIERS
    assert all(row.provider_launch_allowed is False for row in rows)
    assert all(row.network_allowed is False for row in rows)


def test_phase7_live_like_matrix_has_no_raw_transcripts_or_provider_launch_fields() -> None:
    payload = json.loads(PHASE7_LIVE_PERSONA_MATRIX_PATH.read_text(encoding="utf-8"))
    forbidden_keys = {
        "raw_prompt",
        "raw_reply",
        "raw_transcript",
        "provider_stdout",
        "provider_stderr",
        "provider_argv",
        "provider_env",
        "provider_path",
        "provider_account",
        "api_key",
        "token",
        "secret",
    }
    row_fields = {field.name for field in fields(Phase7LiveLikeRow)}

    assert forbidden_keys.isdisjoint(row_fields)
    for row in payload["rows"]:
        assert forbidden_keys.isdisjoint(row)
        assert row.get("provider_launch_allowed", False) is False
        assert row.get("network_allowed", False) is False
        assert row.get("raw_artifacts_allowed", False) is False


def test_phase7_live_like_scores_jit_canary_rows_with_hard_budgets() -> None:
    rows = load_phase7_live_like_rows()
    scores = score_phase7_live_like_rows(rows)
    scores_by_id = {score.row.row_id: score for score in scores}

    assert REQUIRED_JIT_ROW_IDS <= set(scores_by_id)
    assert all(score.row.row_tier == "jit_canary" for score in scores)
    assert all(score.passed for score in scores)
    assert all(score.hard_budget_failures == () for score in scores)
    assert all(score.behavior_score.metric_counts["unexpected_write_count"] == 0 for score in scores)
    assert all(score.phase7_metric_counts["raw_reload_leakage_count"] == 0 for score in scores)
    assert all(
        score.phase7_metric_counts["schema_surface_count"] <= score.phase7_metric_counts["physics_progress_count"] + 1
        for score in scores
    )
    assert REQUIRED_LP_JIT_ROW_IDS <= set(scores_by_id)
    assert REQUIRED_P6_JIT_ROW_IDS <= set(scores_by_id)
    assert REQUIRED_P7_NEXTUP_JIT_ROW_IDS <= set(scores_by_id)
    assert scores_by_id["LP-JIT-03"].behavior_score.metric_counts["stale_artifact_trust_count"] == 0
    assert scores_by_id["LP-JIT-04"].phase7_metric_classes["artifact_handle_first_class"] == "handle_first"
    assert scores_by_id["LP-JIT-06"].phase7_metric_classes["stop_integrity_class"] == "stopped_cleanly"
    assert scores_by_id["LP-JIT-07"].behavior_score.metric_counts["invalid_command_suggestion_count"] == 0
    assert scores_by_id["LP-JIT-08"].behavior_score.metric_counts["unsupported_completion_claim_count"] == 0
    assert scores_by_id["P6-EXEC-JIT-02"].behavior_score.metric_counts["stale_artifact_trust_count"] == 0
    assert scores_by_id["P6-EXEC-JIT-03"].phase7_metric_classes["stop_integrity_class"] == "stopped_cleanly"
    assert scores_by_id["P6-EXEC-JIT-04"].behavior_score.metric_counts["invalid_command_suggestion_count"] == 0
    assert scores_by_id["P6-COMP-JIT-01"].behavior_score.metric_counts["unsupported_completion_claim_count"] == 0
    assert scores_by_id["P6-RES-JIT-02"].phase7_metric_classes["artifact_handle_first_class"] == "handle_first"


def test_lp_jit_04_matrix_targets_real_literature_review_stage_pair() -> None:
    row = _raw_row_by_id("LP-JIT-04")
    bounds = row["behavior_metric_bounds"]

    assert row["fixture_family"] == "jit_reference_handle_first_class"
    assert row["workflow_class"] == "literature_review_handle_then_hydrate"
    assert {
        "src/gpd/core/context.py",
        "src/gpd/core/staged_init_assembly.py",
        "src/gpd/specs/workflows/literature-review-stage-manifest.json",
        "src/gpd/specs/workflows/literature-review/scope-locked.md",
        "src/gpd/specs/workflows/literature-review/review-handoff.md",
    } <= set(row["source_owners"])
    assert "tests/core/test_phase7_live_like.py" in row["test_owners"]

    for metric_key in (
        "invalid_command_suggestion_count",
        "schema_repair_loop_count",
        "duplicate_question_bucket_count",
        "post_stop_activity_count",
        "unexpected_write_count",
        "unsupported_completion_claim_count",
        "raw_reload_leakage_count",
        "content_hydration_before_selection_count",
    ):
        assert bounds[metric_key] == 0
    assert bounds["structured_authority_coverage"] == 1
    assert row["expected_artifact_handle_first_class"] == "handle_first"
    assert row["expected_first_useful_action_class"] == "handle_selection"
    assert row["expected_mutation_guard_class"] == "no_write"


def test_lp_jit_04_literature_review_stage_pair_defers_reference_content() -> None:
    manifest = load_workflow_stage_manifest("literature-review")
    scope_locked = manifest.stage("scope_locked")
    review_handoff = manifest.stage("review_handoff")

    assert REFERENCE_FILE_FIELD in scope_locked.required_init_fields
    assert REFERENCE_CONTENT_FIELD not in scope_locked.required_init_fields
    _assert_handles_before_content(review_handoff.required_init_fields)


def test_reference_content_stages_select_handles_before_content() -> None:
    for manifest_path in sorted(WORKFLOW_STAGE_MANIFEST_DIR.glob(f"*{WORKFLOW_STAGE_MANIFEST_SUFFIX}")):
        workflow_id = manifest_path.name.removesuffix(WORKFLOW_STAGE_MANIFEST_SUFFIX)
        manifest = _load_reference_order_manifest(workflow_id)
        for stage in manifest.stages:
            if REFERENCE_CONTENT_FIELD in stage.required_init_fields:
                _assert_handles_before_content(stage.required_init_fields, label=f"{workflow_id}.{stage.id}")


def test_handle_only_reference_stage_inventory_keeps_content_deferred() -> None:
    handle_only_stages = (
        ("quick", "reference_context"),
        ("literature-review", "scope_locked"),
        ("peer-review", "artifact_discovery"),
        ("peer-review", "panel_stages"),
        ("peer-review", "final_adjudication"),
        ("respond-to-referees", "revision_planning"),
        ("verify-work", "interactive_validation"),
        ("write-paper", "consistency_and_references"),
        ("write-paper", "publication_review"),
    )
    content_stages = (
        ("literature-review", "review_handoff"),
        ("respond-to-referees", "response_authoring"),
        ("write-paper", "figure_and_section_authoring"),
    )

    for workflow_id, stage_id in handle_only_stages:
        stage = _load_reference_order_manifest(workflow_id).stage(stage_id)

        assert REFERENCE_FILE_FIELD in stage.required_init_fields, f"{workflow_id}.{stage_id}"
        assert REFERENCE_CONTENT_FIELD not in stage.required_init_fields, f"{workflow_id}.{stage_id}"

    for workflow_id, stage_id in content_stages:
        stage = _load_reference_order_manifest(workflow_id).stage(stage_id)

        _assert_handles_before_content(stage.required_init_fields, label=f"{workflow_id}.{stage_id}")


def test_staged_init_payload_dispatch_is_lazy_for_handle_only_reference_stage(tmp_path: Path) -> None:
    manifest = _manifest(
        _stage("handle_only", (REFERENCE_FILE_FIELD,)),
        _stage("hydrate", (REFERENCE_FILE_FIELD, REFERENCE_CONTENT_FIELD), order=2),
    )
    calls: list[str] = []

    def build_handles(context: StagedInitAssemblyContext) -> dict[str, object]:
        calls.append(f"handles:{context.stage.id}")
        return {REFERENCE_FILE_FIELD: ["GPD/research-map/REFERENCES.md"]}

    def build_content(context: StagedInitAssemblyContext) -> dict[str, object]:
        if context.stage.id == "handle_only":
            raise AssertionError("reference content provider must not run for handle-only stages")
        calls.append(f"content:{context.stage.id}")
        return {REFERENCE_CONTENT_FIELD: "hydrated reference body"}

    providers = (
        StagedInitProvider("handles", frozenset({REFERENCE_FILE_FIELD}), build_handles),
        StagedInitProvider("content", frozenset({REFERENCE_CONTENT_FIELD}), build_content),
    )

    handle_payload = assemble_staged_init_payload(
        workflow_id="phase7-handle-first",
        stage_id="handle_only",
        cwd=tmp_path,
        base_payload={},
        manifest=manifest,
        providers=providers,
    )
    hydrate_payload = assemble_staged_init_payload(
        workflow_id="phase7-handle-first",
        stage_id="hydrate",
        cwd=tmp_path,
        base_payload={},
        manifest=manifest,
        providers=providers,
    )

    assert calls == ["handles:handle_only", "handles:hydrate", "content:hydrate"]
    assert tuple(handle_payload) == (REFERENCE_FILE_FIELD, "staged_loading")
    assert REFERENCE_CONTENT_FIELD not in handle_payload
    assert tuple(hydrate_payload) == (REFERENCE_FILE_FIELD, REFERENCE_CONTENT_FIELD, "staged_loading")
    assert hydrate_payload[REFERENCE_CONTENT_FIELD] == "hydrated reference body"


def test_literature_review_staged_payload_hydrates_only_after_scope_locked(tmp_path: Path) -> None:
    _setup_literature_review_reference_project(tmp_path)

    scope_locked = init_literature_review(tmp_path, "Curvature flow bounds", stage="scope_locked")
    review_handoff = init_literature_review(tmp_path, "Curvature flow bounds", stage="review_handoff")

    assert REFERENCE_FILE_FIELD in scope_locked
    assert scope_locked[REFERENCE_FILE_FIELD] == ["GPD/research-map/REFERENCES.md"]
    assert REFERENCE_CONTENT_FIELD not in scope_locked
    assert _active_payload_fields(scope_locked) == tuple(scope_locked["staged_loading"]["required_init_fields"])

    assert review_handoff[REFERENCE_FILE_FIELD] == ["GPD/research-map/REFERENCES.md"]
    assert isinstance(review_handoff[REFERENCE_CONTENT_FIELD], str)
    assert review_handoff[REFERENCE_CONTENT_FIELD]
    assert _active_payload_fields(review_handoff) == tuple(review_handoff["staged_loading"]["required_init_fields"])
    _assert_handles_before_content(tuple(review_handoff))


def test_lp_jit_04_uses_shared_handle_before_content_detector() -> None:
    row = _row_by_id("LP-JIT-04")
    score = score_phase7_live_like_row(row)

    assert score.passed
    assert score.hard_budget_failures == ()
    assert score.phase7_metric_counts["raw_reload_leakage_count"] == 0
    assert score.phase7_metric_counts["content_hydration_before_selection_count"] == 0
    assert score.phase7_metric_counts["conversation_turn_count"] == 2
    assert score.behavior_score.metric_counts["raw_reload_leakage_count"] == 0
    assert score.behavior_score.metric_counts["content_hydration_before_selection_count"] == 0
    assert score.behavior_score.metric_classes["artifact_handle_first_class"] == "handle_before_content"
    assert score.phase7_metric_classes["artifact_handle_first_class"] == "handle_first"


def test_p6_research_handle_row_rejects_content_before_handle_regression() -> None:
    row = _row_by_id("P6-RES-JIT-02")
    trace = FakePersonaTrace(
        row_id="P6_RES_JIT_02_BAD_CONTENT_FIRST",
        persona_class=row.persona_class,
        prompt_variant_class=row.prompt_variant_class,
        turns=(
            FakePersonaTurn(
                turn_index=0,
                speaker_class="assistant",
                intent_class="reference_review",
                action_class="concrete_command",
                physics_progress_class="artifact_verified",
                content_hydration_class="content_loaded",
            ),
            FakePersonaTurn(
                turn_index=1,
                speaker_class="assistant",
                intent_class="reference_choice",
                action_class="select_reference",
                artifact_handle_class="handle_selected",
            ),
        ),
    )
    score = score_phase7_live_like_row(row, trace_override=trace)

    assert not score.passed
    assert score.behavior_score.metric_counts["content_hydration_before_selection_count"] == 1
    assert score.behavior_score.metric_classes["artifact_handle_first_class"] == "content_before_handle"
    assert "content_hydration_before_selection_count" in score.hard_budget_failures


def test_handle_first_source_text_rejects_body_fields_before_selection() -> None:
    row = _row_by_id("P6-RES-JIT-02")
    source = (
        "Reference artifacts: {reference_artifacts_content}\n"
        "<protocol_bundle_context>{protocol_bundle_context}</protocol_bundle_context>\n"
        "Rendered active references: {active_reference_context}"
    )
    score = score_phase7_live_like_row(row, source_text_override=source)
    assert not score.passed
    assert score.phase7_metric_counts["content_hydration_before_selection_count"] > 0
    assert "content_hydration_before_selection_count" in score.hard_budget_failures


def test_p6_exec_stop_rejects_post_stop_activity() -> None:
    row = _row_by_id("P6-EXEC-JIT-03")
    trace = FakePersonaTrace(
        row_id="P6_EXEC_JIT_03_BAD_POST_STOP",
        persona_class=row.persona_class,
        prompt_variant_class=row.prompt_variant_class,
        turns=(
            FakePersonaTurn(
                turn_index=0,
                speaker_class="assistant",
                intent_class="abort_acknowledged",
                action_class="stop",
                stop_class="user_abort_stops_dispatch",
            ),
            FakePersonaTurn(
                turn_index=1,
                speaker_class="assistant",
                intent_class="kept_dispatching",
                action_class="runtime_command",
                physics_progress_class="wave_dispatched",
            ),
        ),
    )
    score = score_phase7_live_like_row(row, trace_override=trace)

    assert not score.passed
    assert score.behavior_score.metric_counts["post_stop_activity_count"] == 1
    assert score.phase7_metric_classes["stop_integrity_class"] == "post_stop_activity"
    assert "post_stop_activity_count" in score.hard_budget_failures


def test_p6_runtime_verify_correction_rejects_structural_verify_phase_command() -> None:
    row = _row_by_id("P6-EXEC-JIT-04")
    bad_outcome = phase7_live_like._BehaviorOutcome(
        finding_id="runtime_verify_work_suggestion",
        result_class="ready_for_runtime_verification",
        failure_classes=(),
        evidence_classes=("verify_work_correction",),
        next_action_class="runtime_verify_work",
        ready=False,
        state_status_class="read_only",
        commands=("gpd verify phase 02",),
    )
    score = score_phase7_live_like_row(row, behavior_outcome_override=bad_outcome)

    assert not score.passed
    assert score.behavior_score.metric_counts["invalid_command_suggestion_count"] == 1
    assert "invalid_command_suggestion_count" in score.hard_budget_failures


def test_p6_completion_pressure_rejects_unsupported_closeout_claim() -> None:
    row = _row_by_id("P6-COMP-JIT-01")
    bad_outcome = phase7_live_like._BehaviorOutcome(
        finding_id="unsupported_completion_claim",
        result_class="ready_closeout",
        failure_classes=("unsupported_completion_claim", "canonical_verification_missing"),
        evidence_classes=("closeout_blocked",),
        next_action_class="run_verify_work",
        accepted=True,
        ready=True,
        state_status_class="read_only",
    )
    score = score_phase7_live_like_row(row, behavior_outcome_override=bad_outcome)

    assert not score.passed
    assert score.behavior_score.metric_counts["unsupported_completion_claim_count"] == 1
    assert "unsupported_completion_claim_count" in score.hard_budget_failures


def test_p7_nextup_rows_score_live_like_classes_without_transcripts() -> None:
    scores = {row_id: score_phase7_live_like_row(_row_by_id(row_id)) for row_id in REQUIRED_P7_NEXTUP_JIT_ROW_IDS}

    assert all(score.passed for score in scores.values())
    assert all(score.hard_budget_failures == () for score in scores.values())

    for row_id in ("P7-NEXTUP-JIT-01", "P7-NEXTUP-JIT-02", "P7-NEXTUP-JIT-03", "P7-NEXTUP-JIT-05"):
        score = scores[row_id]
        assert score.behavior_score.metric_classes["next_up_specificity_class"] == "runtime_verify_work"
        assert score.phase7_metric_classes["primary_owner_class"] == "runtime"
        assert score.phase7_metric_classes["stage_stop_runtime_class"] == "runtime"
        assert score.phase7_metric_classes["rendered_public_raw_reload_class"] == "no_raw_reload"
        assert score.phase7_metric_classes["rendered_public_structural_verify_class"] == "no_structural_verify_phase"

    ready = scores["P7-NEXTUP-JIT-04"]
    assert ready.behavior_score.metric_classes["next_up_specificity_class"] == "concrete_command"
    assert ready.phase7_metric_classes["primary_owner_class"] == "local_transition"
    assert ready.phase7_metric_classes["after_this_completes_owner_class"] == "runtime"
    assert ready.phase7_metric_classes["stage_stop_runtime_class"] == "runtime"

    wrong_verify = scores["P7-NEXTUP-JIT-01"]
    assert wrong_verify.phase7_metric_classes["structural_verify_phase_class"] == "structural_verify_phase_display_only"
    assert wrong_verify.behavior_score.metric_counts["invalid_command_suggestion_count"] == 0

    renderer = scores["P7-NEXTUP-JIT-05"]
    assert renderer.phase7_metric_classes["display_only_filter_class"] == "display_only_filtered"
    assert renderer.phase7_metric_counts["raw_reload_leakage_count"] == 0


def test_p7_nextup_row_local_bounds_accept_object_forms() -> None:
    row = _raw_row_by_id("P7-NEXTUP-JIT-04")
    bounds = row["behavior_metric_bounds"]

    assert bounds["invalid_command_suggestion_count"] == {"exact": 0}
    assert bounds["structured_authority_coverage"] == {"min": 1}
    assert bounds["conversation_turn_count"] == {"max": 1}

    score = score_phase7_live_like_row(_row_by_id("P7-NEXTUP-JIT-04"))

    assert score.passed
    assert score.hard_budget_failures == ()


def test_p7_nextup_verify_correction_rejects_structural_verify_phase_command() -> None:
    row = _row_by_id("P7-NEXTUP-JIT-01")
    bad_outcome = phase7_live_like._BehaviorOutcome(
        finding_id="runtime_verify_work_suggestion",
        result_class="ready_for_runtime_verification",
        failure_classes=(),
        evidence_classes=("verify_work_correction",),
        next_action_class="runtime_verify_work",
        ready=False,
        state_status_class="read_only",
        commands=("gpd verify phase 02",),
    )
    score = score_phase7_live_like_row(row, behavior_outcome_override=bad_outcome)

    assert not score.passed
    assert score.behavior_score.metric_counts["invalid_command_suggestion_count"] == 1
    assert "invalid_command_suggestion_count" in score.hard_budget_failures


def test_p7_public_render_row_rejects_raw_reload_source_text() -> None:
    row = _row_by_id("P7-NEXTUP-JIT-05")
    score = score_phase7_live_like_row(
        row,
        source_text_override=(
            "## > Next Up\n"
            "Primary: `gpd --raw init new-project`\n"
            "Secondary: `gpd --raw stage field-access --stage closeout --field next_up`"
        ),
    )

    assert not score.passed
    assert score.behavior_score.metric_counts["raw_reload_leakage_count"] == 2
    assert score.phase7_metric_counts["raw_reload_leakage_count"] == 2
    assert "raw_reload_leakage_count" in score.hard_budget_failures


def test_phase7_live_like_helper_has_no_execution_or_network_surface() -> None:
    source = inspect.getsource(phase7_live_like)

    for forbidden in ("subprocess", "create_subprocess", "os.environ", "socket", "urllib", "requests"):
        assert forbidden not in source


def _row_by_id(row_id: str) -> Phase7LiveLikeRow:
    rows = load_phase7_live_like_rows()
    return next(row for row in rows if row.row_id == row_id)


def _raw_row_by_id(row_id: str) -> dict[str, object]:
    payload = json.loads(PHASE7_LIVE_PERSONA_MATRIX_PATH.read_text(encoding="utf-8"))
    return next(row for row in payload["rows"] if row["row_id"] == row_id)


def _load_reference_order_manifest(workflow_id: str) -> WorkflowStageManifest:
    return load_workflow_stage_manifest(workflow_id)


def _assert_handles_before_content(required_fields: tuple[str, ...], *, label: str = "") -> None:
    assert REFERENCE_FILE_FIELD in required_fields, label
    assert REFERENCE_CONTENT_FIELD in required_fields, label
    assert required_fields.index(REFERENCE_FILE_FIELD) < required_fields.index(REFERENCE_CONTENT_FIELD), label


def _stage(stage_id: str, required_fields: tuple[str, ...], *, order: int = 1) -> WorkflowStage:
    return WorkflowStage(
        id=stage_id,
        order=order,
        purpose=f"{stage_id} purpose",
        mode_paths=(),
        required_init_fields=required_fields,
        loaded_authorities=(),
        conditional_authorities=(),
        must_not_eager_load=(),
        allowed_tools=(),
        writes_allowed=(),
        produced_state=(),
        next_stages=(),
        checkpoints=(),
        init_spec_id=None,
    )


def _manifest(*stages: WorkflowStage) -> WorkflowStageManifest:
    return WorkflowStageManifest(schema_version=1, workflow_id="phase7-handle-first", stages=stages)


def _setup_literature_review_reference_project(cwd: Path) -> None:
    gpd_dir = cwd / "GPD"
    research_map_dir = gpd_dir / "research-map"
    research_map_dir.mkdir(parents=True, exist_ok=True)
    (gpd_dir / "config.json").write_text("{}", encoding="utf-8")
    (gpd_dir / "state.json").write_text("{}", encoding="utf-8")
    (gpd_dir / "STATE.md").write_text("# State\n", encoding="utf-8")
    (gpd_dir / "PROJECT.md").write_text("# Project\n\nCurvature flow bounds.\n", encoding="utf-8")
    (gpd_dir / "ROADMAP.md").write_text("## Milestone\n\n### Phase 1: Test\n", encoding="utf-8")
    (research_map_dir / "REFERENCES.md").write_text("# References\n\n- Hamilton 1982.\n", encoding="utf-8")


def _active_payload_fields(payload: dict[str, object]) -> tuple[str, ...]:
    return tuple(key for key in payload if key != "staged_loading")
