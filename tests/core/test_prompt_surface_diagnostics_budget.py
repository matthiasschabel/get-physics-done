"""Prompt-surface diagnostic budget contracts."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from gpd.adapters import iter_runtime_descriptors
from gpd.adapters.runtime_catalog import RuntimeDescriptor
from gpd.core.prompt_diagnostics import build_prompt_surface_report, report_to_dict

REPO_ROOT = Path(__file__).resolve().parents[2]

PROMPT_TOTAL_BUDGET = {"lines": 61_000, "chars": 2_650_000}
PROMPT_KIND_BUDGETS = {
    "command": {"lines": 27_000, "chars": 1_100_000},
    "agent": {"lines": 10_800, "chars": 575_000},
    "workflow": {"lines": 24_500, "chars": 1_000_000},
}
STAGE_FIRST_TURN_BUDGET = {"lines": 3_800, "chars": 185_000}
MUST_NOT_EAGER_LOAD_VIOLATION_BUDGET = 1
ROOT_WORKFLOW_AUTHORITY_STAGE_BUDGET = 1
ROOT_AUTHORITY_FREE_WORKFLOWS = frozenset(
    {
        "arxiv-submission",
        "execute-phase",
        "literature-review",
        "map-research",
        "new-milestone",
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
SHELL_PARSING_LINE_BUDGET = 700
SHELL_MIGRATION_TARGET_WORKFLOWS = frozenset(
    {
        ("workflow", "execute-phase"),
        ("workflow", "plan-phase"),
        ("workflow", "new-project"),
        ("workflow", "write-paper"),
    }
)
TARGET_WORKFLOW_SHELL_FENCE_BUDGET = 25
TARGET_WORKFLOW_SHELL_PARSING_LINE_BUDGET = 45
NON_REFERENCE_SEMANTIC_DUPLICATE_BUDGETS = {
    "status_handling": 110,
    "files_written_freshness": 26,
    "stale_artifact_rejection": 30,
    "fresh_continuation": 38,
    "heading_prose_non_authority": 20,
    "no_synthesized_child_gpd_return": 3,
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
        "PLAN_RETURN_MARKDOWN=\"$MAIN_CONTEXT_PLAN_RETURN\"",
    ),
    "execute-phase.md": (
        'PROJECT_ROOT=$(pwd -P); while [ "$PROJECT_ROOT" != "/" ]',
        "MANIFEST_PATH=\"$MANIFEST_PATH\" python - <<'PY'",
    ),
    "new-project.md": ("cat > GPD/init-progress.json << CHECKPOINT",),
}


def _aggregate_budget_for_descriptor(descriptor: RuntimeDescriptor) -> dict[str, int]:
    if descriptor.native_include_support:
        return {"lines": 18_500, "chars": 950_000}
    if not descriptor.agent_prompt_uses_dollar_templates:
        return {"lines": 28_500, "chars": 1_385_000}
    if descriptor.public_command_surface_prefix.endswith(":"):
        return {"lines": 28_700, "chars": 1_420_000}
    return {"lines": 29_000, "chars": 1_390_000}


def _command_only_budget_for_descriptor(descriptor: RuntimeDescriptor) -> dict[str, int]:
    if descriptor.native_include_support:
        return {"lines": 7_500, "chars": 383_000}
    if not descriptor.agent_prompt_uses_dollar_templates:
        return {"lines": 16_500, "chars": 745_000}
    if descriptor.public_command_surface_prefix.endswith(":"):
        return {"lines": 16_800, "chars": 780_000}
    return {"lines": 16_700, "chars": 750_000}


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
    violation_count = stage_diagnostics["must_not_eager_load_violation_count"]
    assert isinstance(violation_count, int)
    assert violation_count <= MUST_NOT_EAGER_LOAD_VIOLATION_BUDGET


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
    assert isinstance(first_turn_lines, int)
    assert isinstance(first_turn_chars, int)
    assert first_turn_lines <= STAGE_FIRST_TURN_BUDGET["lines"], (
        "stage_diagnostics first-turn line budget exceeded: "
        f"observed={first_turn_lines} max={STAGE_FIRST_TURN_BUDGET['lines']}"
    )
    assert first_turn_chars <= STAGE_FIRST_TURN_BUDGET["chars"], (
        "stage_diagnostics first-turn char budget exceeded: "
        f"observed={first_turn_chars} max={STAGE_FIRST_TURN_BUDGET['chars']}"
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
    groups = payload["semantic_duplicate_invariants"]
    assert isinstance(groups, list)
    groups_by_category = {
        group["category"]: group
        for group in groups
        if isinstance(group, dict) and isinstance(group.get("category"), str)
    }

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
