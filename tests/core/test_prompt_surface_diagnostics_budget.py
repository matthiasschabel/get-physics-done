"""Prompt-surface diagnostic budget contracts."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from gpd.adapters import iter_runtime_descriptors
from gpd.adapters.runtime_catalog import RuntimeDescriptor
from gpd.core.prompt_diagnostics import build_prompt_surface_report, report_to_dict

REPO_ROOT = Path(__file__).resolve().parents[2]

PROMPT_TOTAL_BUDGET = {"lines": 51_500, "chars": 2_205_000}
PROMPT_KIND_BUDGETS = {
    "command": {"lines": 22_600, "chars": 900_000},
    "agent": {"lines": 9_300, "chars": 490_000},
    "workflow": {"lines": 19_600, "chars": 813_500},
}
STAGE_FIRST_TURN_BUDGET = {"lines": 3_500, "chars": 171_200}
# Phase 4 scaffolding guard. Keep first-turn active content flat while Phase 6
# ratchets the integrated agent aggregate separately.
STAGE_FIRST_TURN_ACTIVE_BUDGET = {"lines": 2_500, "chars": 141_300}
STAGE_SELECTED_INIT_FIELD_BUDGET = 2_937
STAGE_SELECTED_INIT_CONTENT_FIELD_BUDGET = 58
REFERENCE_ARTIFACTS_CONTENT_SELECTION_BUDGET = 15
STAGE_HIGH_PRESSURE_INIT_FIELD_BUDGET = 664
STAGE_LIKELY_BULKY_INIT_FIELD_BUDGET = 664
EXECUTE_PHASE_FIRST_TURN_CHAR_BUDGET = 6_707
EXECUTE_PHASE_SPLIT_STAGE_EAGER_CHAR_BUDGET = 16_000
PHASE3_TARGET_STAGE_EAGER_CHAR_BUDGETS = {
    ("execute-phase", "closeout"): 7_167,
    ("peer-review", "preflight"): 9_178,
    ("verify-work", "gap_repair"): 14_122,
    ("verify-work", "interactive_validation"): 7_956,
    ("sync-state", "reconcile_and_validate"): 3_836,
    ("sync-state", "conflict_analysis"): 2_634,
    ("sync-state", "single_source_recovery"): 1_763,
}
PHASE5_STAGE_EAGER_CHAR_BUDGETS = {
    ("write-paper", "publication_review"): 12_000,
    ("peer-review", "panel_stages"): 40_000,
}
PHASE5_AUTONOMOUS_STAGE_EAGER_CHAR_BUDGET = 5_500
EXECUTE_PHASE_SPLIT_FAMILY_STAGES = (
    "wave_dispatch",
    "executor_dispatch",
    "proof_critic_dispatch",
    "wave_return_checkpoint",
    "wave_failure_menu",
    "aggregate_and_verify",
    "verification_handoff",
    "gap_reverification",
    "consistency_check",
)
MUST_NOT_EAGER_LOAD_VIOLATION_BUDGET = 0
MUST_NOT_EAGER_LOAD_PRIOR_STAGE_RESIDUE_BUDGET = 8
ROOT_WORKFLOW_AUTHORITY_STAGE_BUDGET = 0
ROOT_AUTHORITY_FREE_WORKFLOWS = frozenset(
    {
        "arxiv-submission",
        "autonomous",
        "execute-phase",
        "literature-review",
        "map-research",
        "new-milestone",
        "new-project",
        "peer-review",
        "plan-phase",
        "quick",
        "research-phase",
        "respond-to-referees",
        "resume-work",
        "sync-state",
        "verify-work",
        "write-paper",
    }
)
SHELL_PARSING_LINE_BUDGET = 460
SHELL_MIGRATION_TARGET_WORKFLOWS = frozenset(
    {
        ("workflow", "execute-phase"),
        ("workflow", "plan-phase"),
        ("workflow", "new-project"),
        ("workflow", "write-paper"),
    }
)
TARGET_WORKFLOW_SHELL_FENCE_BUDGET = 2
TARGET_WORKFLOW_SHELL_PARSING_LINE_BUDGET = 3
NON_REFERENCE_SEMANTIC_DUPLICATE_BUDGETS = {
    "status_handling": 80,
    "files_written_freshness": 15,
    "stale_artifact_rejection": 25,
    "fresh_continuation": 24,
    "heading_prose_non_authority": 14,
    "no_synthesized_child_gpd_return": 2,
}
# Future Phase 4 ratchet targets. These are asserted as exposed diagnostics only
# until prompt cuts are integrated and measured in the current workspace.
PHASE4_NON_REFERENCE_SEMANTIC_DUPLICATE_TARGETS = {
    "status_handling": 80,
    "fresh_continuation": 24,
    "files_written_freshness": 15,
    "stale_artifact_rejection": 25,
    "heading_prose_non_authority": 14,
    "no_synthesized_child_gpd_return": 2,
}
ZERO_SAFETY_TOTAL_FIELDS = (
    "unresolved_include_count",
    "invalid_gpd_return_example_count",
    "invalid_frontmatter_example_count",
    "disallowed_return_field_mention_count",
    "forbidden_child_return_synthesis_mention_count",
)
FORBIDDEN_MIGRATED_PROMPT_SHELL_FRAGMENTS = {
    "plan-phase.md": (
        "printf '```yaml\\ngpd_return:\\n'",
        "printf '  status: completed\\n  files_written:\\n'",
        'PLAN_RETURN_MARKDOWN="$MAIN_CONTEXT_PLAN_RETURN"',
    ),
    "execute-phase.md": (
        'PROJECT_ROOT=$(pwd -P); while [ "$PROJECT_ROOT" != "/" ]',
        "MANIFEST_PATH=\"$MANIFEST_PATH\" python - <<'PY'",
    ),
    "new-project.md": ("cat > GPD/init-progress.json << CHECKPOINT",),
}


def _aggregate_budget_for_descriptor(descriptor: RuntimeDescriptor) -> dict[str, int]:
    if descriptor.native_include_support:
        return {"lines": 17_700, "chars": 930_000}
    if not descriptor.agent_prompt_uses_dollar_templates:
        return {"lines": 27_350, "chars": 1_345_000}
    if descriptor.public_command_surface_prefix.endswith(":"):
        return {"lines": 27_500, "chars": 1_375_000}
    return {"lines": 27_850, "chars": 1_350_000}


def _command_only_budget_for_descriptor(descriptor: RuntimeDescriptor) -> dict[str, int]:
    if descriptor.native_include_support:
        return {"lines": 7_400, "chars": 382_000}
    if not descriptor.agent_prompt_uses_dollar_templates:
        return {"lines": 16_300, "chars": 745_000}
    if descriptor.public_command_surface_prefix.endswith(":"):
        return {"lines": 16_400, "chars": 775_000}
    return {"lines": 16_650, "chars": 750_000}


def _runtime_projection_budgets(*, command_only: bool) -> dict[str, dict[str, int]]:
    budget_for_descriptor = _command_only_budget_for_descriptor if command_only else _aggregate_budget_for_descriptor
    return {descriptor.runtime_name: budget_for_descriptor(descriptor) for descriptor in iter_runtime_descriptors()}


def _runtime_descriptors_by_name() -> dict[str, RuntimeDescriptor]:
    return {descriptor.runtime_name: descriptor for descriptor in iter_runtime_descriptors()}


def _root_workflow_authority_stages() -> dict[str, tuple[str, ...]]:
    workflow_root = REPO_ROOT / "src/gpd/specs/workflows"
    result: dict[str, tuple[str, ...]] = {}
    for manifest_path in sorted(workflow_root.glob("*-stage-manifest.json")):
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        workflow_id = payload["workflow_id"]
        root_authority = f"workflows/{workflow_id}.md"
        stage_ids: list[str] = []
        for stage in payload.get("stages", []):
            if not isinstance(stage, dict):
                continue
            authorities = [*stage.get("mode_paths", []), *stage.get("loaded_authorities", [])]
            if root_authority in authorities:
                stage_ids.append(stage["id"])
        if stage_ids:
            result[workflow_id] = tuple(stage_ids)
    return result


@lru_cache
def _prompt_surface_payload(
    surfaces: tuple[str, ...],
    runtime_names: tuple[str, ...],
    include_runtime_projections: bool,
) -> dict[str, object]:
    report = build_prompt_surface_report(
        REPO_ROOT,
        surfaces=surfaces,
        runtime_names=runtime_names,
        include_tests=False,
        include_runtime_projections=include_runtime_projections,
    )
    return report_to_dict(report)


def _assert_expanded_budget(label: str, metrics: dict[str, object], budget: dict[str, int]) -> None:
    observed_lines = metrics["expanded_line_count"]
    observed_chars = metrics["expanded_char_count"]
    assert isinstance(observed_lines, int)
    assert isinstance(observed_chars, int)
    assert observed_lines <= budget["lines"], (
        f"{label} expanded line budget exceeded: observed={observed_lines} max={budget['lines']}"
    )
    assert observed_chars <= budget["chars"], (
        f"{label} expanded char budget exceeded: observed={observed_chars} max={budget['chars']}"
    )


def _assert_runtime_projection_budget(
    label: str,
    metrics: dict[str, object],
    budget: dict[str, int],
) -> None:
    observed_lines = metrics["line_count"]
    observed_chars = metrics["char_count"]
    assert isinstance(observed_lines, int)
    assert isinstance(observed_chars, int)
    assert observed_lines <= budget["lines"], (
        f"{label} projected line budget exceeded: observed={observed_lines} max={budget['lines']}"
    )
    assert observed_chars <= budget["chars"], (
        f"{label} projected char budget exceeded: observed={observed_chars} max={budget['chars']}"
    )


def _assert_non_native_projection_has_no_projected_includes(
    label: str,
    descriptor: RuntimeDescriptor,
    metrics: dict[str, object],
) -> None:
    include_count = metrics["include_count"]
    assert isinstance(include_count, int)
    if descriptor.native_include_support:
        return
    assert include_count == 0, f"{label} projected include count must stay zero"


def _stage_diagnostic_count(stage_diagnostics: dict[str, object], *field_names: str) -> int:
    for field_name in field_names:
        value = stage_diagnostics.get(field_name)
        if value is None:
            continue
        assert isinstance(value, int)
        return value
    raise AssertionError(f"stage diagnostics missing expected count field from {field_names}")


def _required_stage_diagnostic_count(stage_diagnostics: dict[str, object], field_name: str) -> int:
    value = stage_diagnostics[field_name]
    assert isinstance(value, int)
    return value


def _workflow_stage_diagnostics(payload: dict[str, object], workflow_id: str) -> dict[str, object]:
    workflows = payload["stage_diagnostics"]
    assert isinstance(workflows, list)
    for workflow in workflows:
        assert isinstance(workflow, dict)
        if workflow.get("workflow_id") == workflow_id:
            return workflow
    raise AssertionError(f"{workflow_id} staged diagnostics were not reported")


def _stage_diagnostics_by_id(workflow: dict[str, object]) -> dict[str, dict[str, object]]:
    stages = workflow["stages"]
    assert isinstance(stages, list)
    return {stage["stage_id"]: stage for stage in stages if isinstance(stage, dict)}


def _stage_init_field_rows(payload: dict[str, object]) -> list[dict[str, object]]:
    rows = payload["stage_init_field_diagnostics"]
    assert isinstance(rows, list)
    return [row for row in rows if isinstance(row, dict)]


def _semantic_duplicate_groups_by_category(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    groups = payload["semantic_duplicate_invariants"]
    assert isinstance(groups, list)
    return {
        group["category"]: group
        for group in groups
        if isinstance(group, dict) and isinstance(group.get("category"), str)
    }


def test_prompt_surface_aggregate_budgets_stay_under_ceilings() -> None:
    payload = _prompt_surface_payload(("all",), (), False)
    totals = payload["totals"]
    assert isinstance(totals, dict)

    _assert_expanded_budget("all prompts", totals, PROMPT_TOTAL_BUDGET)

    by_kind = totals["by_kind"]
    assert isinstance(by_kind, dict)
    for kind, budget in PROMPT_KIND_BUDGETS.items():
        kind_metrics = by_kind[kind]
        assert isinstance(kind_metrics, dict)
        _assert_expanded_budget(kind, kind_metrics, budget)


def test_prompt_surface_safety_floors_stay_within_current_budgets() -> None:
    payload = _prompt_surface_payload(("all",), (), False)
    totals = payload["totals"]
    assert isinstance(totals, dict)

    observed = {field: totals[field] for field in ZERO_SAFETY_TOTAL_FIELDS}
    assert observed == dict.fromkeys(ZERO_SAFETY_TOTAL_FIELDS, 0)

    stage_diagnostics = totals["stage_diagnostics"]
    assert isinstance(stage_diagnostics, dict)
    violation_count = _stage_diagnostic_count(stage_diagnostics, "must_not_eager_load_violation_count")
    assert violation_count <= MUST_NOT_EAGER_LOAD_VIOLATION_BUDGET
    actionable_violation_count = _required_stage_diagnostic_count(
        stage_diagnostics,
        "must_not_eager_load_actionable_violation_count",
    )
    assert actionable_violation_count <= MUST_NOT_EAGER_LOAD_VIOLATION_BUDGET
    prior_stage_residue_count = _required_stage_diagnostic_count(
        stage_diagnostics,
        "must_not_eager_load_prior_stage_residue_count",
    )
    assert prior_stage_residue_count <= MUST_NOT_EAGER_LOAD_PRIOR_STAGE_RESIDUE_BUDGET


def test_staged_init_field_pressure_totals_do_not_grow_from_phase6_baseline() -> None:
    payload = _prompt_surface_payload(("all",), (), False)
    totals = payload["totals"]
    assert isinstance(totals, dict)

    stage_diagnostics = totals["stage_diagnostics"]
    assert isinstance(stage_diagnostics, dict)
    budgets = {
        "selected_init_field_count": STAGE_SELECTED_INIT_FIELD_BUDGET,
        "selected_init_content_field_count": STAGE_SELECTED_INIT_CONTENT_FIELD_BUDGET,
        "high_pressure_init_field_count": STAGE_HIGH_PRESSURE_INIT_FIELD_BUDGET,
        "likely_bulky_init_field_count": STAGE_LIKELY_BULKY_INIT_FIELD_BUDGET,
    }

    observed = {field_name: _required_stage_diagnostic_count(stage_diagnostics, field_name) for field_name in budgets}
    for field_name, budget in budgets.items():
        assert observed[field_name] <= budget, (
            f"{field_name} budget exceeded: observed={observed[field_name]} max={budget}; "
            "move bulky staged-init payload fields to later stages or cheap handles"
        )


def test_reference_artifacts_content_selection_count_stays_under_phase3_baseline() -> None:
    payload = _prompt_surface_payload(("command",), (), False)

    rows = [row for row in _stage_init_field_rows(payload) if row["field_name"] == "reference_artifacts_content"]
    observed = len(rows)
    assert observed <= REFERENCE_ARTIFACTS_CONTENT_SELECTION_BUDGET, (
        "reference_artifacts_content staged-init selection budget exceeded: "
        f"observed={observed} max={REFERENCE_ARTIFACTS_CONTENT_SELECTION_BUDGET}; "
        "stages that only need artifact handles should select reference_artifact_files"
    )
    assert {row["selection_count"] for row in rows} == {observed}
    assert {row["field_kind_guess"] for row in rows} == {"content"}
    assert {row["field_pressure_class"] for row in rows} == {"likely_bulky"}
    assert {row["likely_bulky"] for row in rows} == {True}


def test_shell_parsing_and_staged_first_turn_budgets_stay_under_ceilings() -> None:
    payload = _prompt_surface_payload(("all",), (), False)
    totals = payload["totals"]
    shell_parsing_line_count = totals["shell_parsing_line_count"]
    assert isinstance(shell_parsing_line_count, int)
    assert shell_parsing_line_count <= SHELL_PARSING_LINE_BUDGET, (
        "prompt shell parsing budget exceeded: "
        f"observed={shell_parsing_line_count} max={SHELL_PARSING_LINE_BUDGET}; "
        "prefer manifest-backed staged field access over prompt-local shell parsers"
    )

    stage_diagnostics = totals["stage_diagnostics"]
    assert isinstance(stage_diagnostics, dict)
    first_turn_lines = stage_diagnostics["first_turn_line_count"]
    first_turn_chars = stage_diagnostics["first_turn_char_count"]
    first_turn_active_lines = stage_diagnostics["first_turn_active_line_count"]
    first_turn_active_chars = stage_diagnostics["first_turn_active_char_count"]
    assert isinstance(first_turn_lines, int)
    assert isinstance(first_turn_chars, int)
    assert isinstance(first_turn_active_lines, int)
    assert isinstance(first_turn_active_chars, int)
    assert first_turn_lines <= STAGE_FIRST_TURN_BUDGET["lines"], (
        "stage_diagnostics first-turn line budget exceeded: "
        f"observed={first_turn_lines} max={STAGE_FIRST_TURN_BUDGET['lines']}"
    )
    assert first_turn_chars <= STAGE_FIRST_TURN_BUDGET["chars"], (
        "stage_diagnostics first-turn char budget exceeded: "
        f"observed={first_turn_chars} max={STAGE_FIRST_TURN_BUDGET['chars']}"
    )
    assert first_turn_active_lines <= STAGE_FIRST_TURN_ACTIVE_BUDGET["lines"], (
        "stage_diagnostics first-turn active line budget exceeded: "
        f"observed={first_turn_active_lines} max={STAGE_FIRST_TURN_ACTIVE_BUDGET['lines']}"
    )
    assert first_turn_active_chars <= STAGE_FIRST_TURN_ACTIVE_BUDGET["chars"], (
        "stage_diagnostics first-turn active char budget exceeded: "
        f"observed={first_turn_active_chars} max={STAGE_FIRST_TURN_ACTIVE_BUDGET['chars']}"
    )


def test_execute_phase_split_stage_budgets_stay_under_phase4_caps() -> None:
    payload = _prompt_surface_payload(("command",), (), False)
    workflow = _workflow_stage_diagnostics(payload, "execute-phase")

    first_turn_chars = workflow["first_turn_char_count"]
    assert isinstance(first_turn_chars, int)
    assert first_turn_chars <= EXECUTE_PHASE_FIRST_TURN_CHAR_BUDGET, (
        "execute-phase first-turn char budget exceeded: "
        f"observed={first_turn_chars} max={EXECUTE_PHASE_FIRST_TURN_CHAR_BUDGET}"
    )

    violation_count = workflow["violation_count"]
    assert isinstance(violation_count, int)
    assert violation_count <= MUST_NOT_EAGER_LOAD_VIOLATION_BUDGET

    stages = workflow["stages"]
    assert isinstance(stages, list)
    stage_by_id = _stage_diagnostics_by_id(workflow)
    for stage_id in EXECUTE_PHASE_SPLIT_FAMILY_STAGES:
        stage = stage_by_id[stage_id]
        observed = stage["eager_char_count"]
        assert isinstance(observed, int)
        assert observed < EXECUTE_PHASE_SPLIT_STAGE_EAGER_CHAR_BUDGET, (
            f"{stage_id} eager char budget exceeded: "
            f"observed={observed} max<{EXECUTE_PHASE_SPLIT_STAGE_EAGER_CHAR_BUDGET}"
        )


def test_phase3_target_stage_eager_budgets_do_not_rebound_above_measured_baselines() -> None:
    payload = _prompt_surface_payload(("command",), (), False)

    workflow_ids = {workflow_id for workflow_id, _stage_id in PHASE3_TARGET_STAGE_EAGER_CHAR_BUDGETS}
    stage_by_workflow = {
        workflow_id: _stage_diagnostics_by_id(_workflow_stage_diagnostics(payload, workflow_id))
        for workflow_id in workflow_ids
    }
    for (workflow_id, stage_id), char_budget in PHASE3_TARGET_STAGE_EAGER_CHAR_BUDGETS.items():
        stage = stage_by_workflow[workflow_id][stage_id]
        observed = stage["eager_char_count"]
        assert isinstance(observed, int)
        assert observed <= char_budget, (
            f"{workflow_id}.{stage_id} eager char budget exceeded: "
            f"observed={observed} max={char_budget}; keep optional stage authorities conditional"
        )


def test_phase5_publication_stage_eager_budgets_stay_under_caps() -> None:
    payload = _prompt_surface_payload(("command",), (), False)

    for (workflow_id, stage_id), char_budget in PHASE5_STAGE_EAGER_CHAR_BUDGETS.items():
        workflow = _workflow_stage_diagnostics(payload, workflow_id)
        stage = _stage_diagnostics_by_id(workflow)[stage_id]
        observed = stage["eager_char_count"]
        assert isinstance(observed, int)
        assert observed < char_budget, (
            f"{workflow_id}.{stage_id} eager char budget exceeded: observed={observed} max<{char_budget}"
        )


def test_phase5_autonomous_stages_stay_under_eager_cap() -> None:
    payload = _prompt_surface_payload(("command",), (), False)
    workflow = _workflow_stage_diagnostics(payload, "autonomous")

    for stage_id, stage in _stage_diagnostics_by_id(workflow).items():
        observed = stage["eager_char_count"]
        assert isinstance(observed, int)
        assert observed < PHASE5_AUTONOMOUS_STAGE_EAGER_CHAR_BUDGET, (
            f"autonomous.{stage_id} eager char budget exceeded: "
            f"observed={observed} max<{PHASE5_AUTONOMOUS_STAGE_EAGER_CHAR_BUDGET}"
        )


def test_root_workflow_authority_frontload_stays_within_advisory_budget() -> None:
    root_authority_stages = _root_workflow_authority_stages()
    root_stage_count = sum(len(stage_ids) for stage_ids in root_authority_stages.values())

    assert root_stage_count <= ROOT_WORKFLOW_AUTHORITY_STAGE_BUDGET, (
        "staged workflow root-authority frontload budget exceeded: "
        f"observed={root_stage_count} max={ROOT_WORKFLOW_AUTHORITY_STAGE_BUDGET}; "
        f"root-loaded stages={root_authority_stages}"
    )

    for workflow_id in ROOT_AUTHORITY_FREE_WORKFLOWS:
        assert workflow_id not in root_authority_stages, (
            f"{workflow_id} is split into stage authority files and must not eagerly load "
            f"workflows/{workflow_id}.md as a stage authority"
        )


def test_target_workflow_shell_budgets_stay_under_caps() -> None:
    payload = _prompt_surface_payload(("workflow",), (), False)
    items = payload["items"]
    assert isinstance(items, list)

    target_items = [
        item
        for item in items
        if isinstance(item, dict) and (item.get("kind"), item.get("name")) in SHELL_MIGRATION_TARGET_WORKFLOWS
    ]
    assert len(target_items) == len(SHELL_MIGRATION_TARGET_WORKFLOWS)

    shell_fence_count = sum(item["shell_fence_count"] for item in target_items)
    shell_parsing_line_count = sum(item["shell_parsing_line_count"] for item in target_items)
    assert isinstance(shell_fence_count, int)
    assert isinstance(shell_parsing_line_count, int)
    assert shell_fence_count <= TARGET_WORKFLOW_SHELL_FENCE_BUDGET, (
        "target workflow shell fence budget exceeded: "
        f"observed={shell_fence_count} max={TARGET_WORKFLOW_SHELL_FENCE_BUDGET}"
    )
    assert shell_parsing_line_count <= TARGET_WORKFLOW_SHELL_PARSING_LINE_BUDGET, (
        "target workflow shell parsing budget exceeded: "
        f"observed={shell_parsing_line_count} max={TARGET_WORKFLOW_SHELL_PARSING_LINE_BUDGET}; "
        "keep orchestration logic in helper surfaces instead of prompt-local shell parsers"
    )


def test_migrated_workflows_do_not_reintroduce_old_shell_fragments() -> None:
    workflow_root = REPO_ROOT / "src/gpd/specs/workflows"

    for workflow_name, fragments in FORBIDDEN_MIGRATED_PROMPT_SHELL_FRAGMENTS.items():
        text = (workflow_root / workflow_name).read_text(encoding="utf-8")
        for fragment in fragments:
            assert fragment not in text, f"{workflow_name} reintroduced old prompt shell fragment: {fragment}"


def test_non_reference_semantic_duplicate_budgets_stay_under_caps() -> None:
    payload = _prompt_surface_payload(("all",), (), False)
    groups_by_category = _semantic_duplicate_groups_by_category(payload)

    missing_categories = sorted(set(NON_REFERENCE_SEMANTIC_DUPLICATE_BUDGETS) - set(groups_by_category))
    assert missing_categories == []

    for category, budget in NON_REFERENCE_SEMANTIC_DUPLICATE_BUDGETS.items():
        group = groups_by_category[category]
        observed = group["non_reference_occurrence_count"]
        occurrence_count = group["occurrence_count"]
        canonical_references = group["canonical_references"]
        assert isinstance(observed, int)
        assert isinstance(occurrence_count, int)
        assert isinstance(canonical_references, list)
        assert canonical_references
        assert observed <= occurrence_count
        assert observed <= budget, (
            f"{category} non-reference semantic duplicate budget exceeded: "
            f"observed={observed} max={budget}; move generic invariant prose to shared references"
        )


def test_phase4_duplicate_category_targets_are_exposed_for_future_ratchet() -> None:
    payload = _prompt_surface_payload(("all",), (), False)
    groups_by_category = _semantic_duplicate_groups_by_category(payload)

    assert set(PHASE4_NON_REFERENCE_SEMANTIC_DUPLICATE_TARGETS) <= set(NON_REFERENCE_SEMANTIC_DUPLICATE_BUDGETS)
    missing_categories = sorted(set(PHASE4_NON_REFERENCE_SEMANTIC_DUPLICATE_TARGETS) - set(groups_by_category))
    assert missing_categories == []

    for category, target in PHASE4_NON_REFERENCE_SEMANTIC_DUPLICATE_TARGETS.items():
        group = groups_by_category[category]
        observed = group["non_reference_occurrence_count"]
        occurrence_count = group["occurrence_count"]
        canonical_references = group["canonical_references"]
        assert isinstance(target, int)
        assert isinstance(observed, int)
        assert isinstance(occurrence_count, int)
        assert isinstance(canonical_references, list)
        assert canonical_references
        assert observed <= occurrence_count


def test_runtime_projection_aggregate_budgets_stay_under_ceilings() -> None:
    payload = _prompt_surface_payload(("all",), ("all",), True)
    totals = payload["totals"]
    assert isinstance(totals, dict)
    runtime_projection = totals["runtime_projection"]
    assert isinstance(runtime_projection, dict)
    runtime_budgets = _runtime_projection_budgets(command_only=False)
    runtime_descriptors = _runtime_descriptors_by_name()

    unexpected_runtimes = sorted(set(runtime_projection) - set(runtime_budgets))
    missing_runtimes = sorted(set(runtime_budgets) - set(runtime_projection))
    assert unexpected_runtimes == []
    assert missing_runtimes == []
    assert set(runtime_descriptors) == set(runtime_budgets)

    for runtime_name, budget in runtime_budgets.items():
        runtime_metrics = runtime_projection[runtime_name]
        assert isinstance(runtime_metrics, dict)
        label = f"{runtime_name} command+agent"
        _assert_runtime_projection_budget(label, runtime_metrics, budget)
        _assert_non_native_projection_has_no_projected_includes(
            label,
            runtime_descriptors[runtime_name],
            runtime_metrics,
        )


def test_runtime_projection_command_only_budgets_stay_under_ceilings() -> None:
    payload = _prompt_surface_payload(("command",), ("all",), True)
    totals = payload["totals"]
    assert isinstance(totals, dict)
    runtime_projection = totals["runtime_projection"]
    assert isinstance(runtime_projection, dict)
    runtime_budgets = _runtime_projection_budgets(command_only=True)
    runtime_descriptors = _runtime_descriptors_by_name()

    unexpected_runtimes = sorted(set(runtime_projection) - set(runtime_budgets))
    missing_runtimes = sorted(set(runtime_budgets) - set(runtime_projection))
    assert unexpected_runtimes == []
    assert missing_runtimes == []
    assert set(runtime_descriptors) == set(runtime_budgets)

    for runtime_name, budget in runtime_budgets.items():
        runtime_metrics = runtime_projection[runtime_name]
        assert isinstance(runtime_metrics, dict)
        label = f"{runtime_name} command-only"
        _assert_runtime_projection_budget(label, runtime_metrics, budget)
        _assert_non_native_projection_has_no_projected_includes(
            label,
            runtime_descriptors[runtime_name],
            runtime_metrics,
        )
