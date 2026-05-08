"""Phase 1 prompt-surface diagnostic budget contracts."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from gpd.adapters import iter_runtime_descriptors
from gpd.adapters.runtime_catalog import RuntimeDescriptor
from gpd.core.prompt_diagnostics import build_prompt_surface_report, report_to_dict

REPO_ROOT = Path(__file__).resolve().parents[2]

PROMPT_TOTAL_BUDGET = {"lines": 83_500, "chars": 3_825_000}
PROMPT_KIND_BUDGETS = {
    "command": {"lines": 34_900, "chars": 1_515_000},
    "agent": {"lines": 14_900, "chars": 778_000},
    "workflow": {"lines": 34_000, "chars": 1_526_000},
}
STAGE_FIRST_TURN_BUDGET = {"lines": 12_500, "chars": 635_000}
SHELL_PARSING_LINE_BUDGET = 920
PHASE5_NON_REFERENCE_SEMANTIC_DUPLICATE_BUDGETS = {
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


def _aggregate_budget_for_descriptor(descriptor: RuntimeDescriptor) -> dict[str, int]:
    if descriptor.native_include_support:
        return {"lines": 20_000, "chars": 1_035_000}
    if not descriptor.agent_prompt_uses_dollar_templates:
        return {"lines": 36_600, "chars": 1_775_000}
    if descriptor.public_command_surface_prefix.endswith(":"):
        return {"lines": 36_800, "chars": 1_810_000}
    return {"lines": 37_100, "chars": 1_778_000}


def _command_only_budget_for_descriptor(descriptor: RuntimeDescriptor) -> dict[str, int]:
    if descriptor.native_include_support:
        return {"lines": 7_500, "chars": 383_000}
    if not descriptor.agent_prompt_uses_dollar_templates:
        return {"lines": 21_000, "chars": 953_000}
    if descriptor.public_command_surface_prefix.endswith(":"):
        return {"lines": 21_200, "chars": 988_000}
    return {"lines": 21_500, "chars": 956_500}


def _runtime_projection_budgets(*, command_only: bool) -> dict[str, dict[str, int]]:
    budget_for_descriptor = _command_only_budget_for_descriptor if command_only else _aggregate_budget_for_descriptor
    return {descriptor.runtime_name: budget_for_descriptor(descriptor) for descriptor in iter_runtime_descriptors()}


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


def test_prompt_surface_aggregate_budgets_stay_under_phase1_ceilings() -> None:
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


def test_prompt_surface_safety_floors_remain_zero() -> None:
    payload = _prompt_surface_payload(("all",), (), False)
    totals = payload["totals"]
    assert isinstance(totals, dict)

    observed = {field: totals[field] for field in ZERO_SAFETY_TOTAL_FIELDS}
    assert observed == dict.fromkeys(ZERO_SAFETY_TOTAL_FIELDS, 0)

    stage_diagnostics = totals["stage_diagnostics"]
    assert isinstance(stage_diagnostics, dict)
    assert stage_diagnostics["must_not_eager_load_violation_count"] == 0


def test_phase3_shell_parsing_and_staged_first_turn_budgets_stay_under_ceilings() -> None:
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


def test_phase5_non_reference_semantic_duplicate_budgets_stay_under_caps() -> None:
    payload = _prompt_surface_payload(("all",), (), False)
    groups = payload["semantic_duplicate_invariants"]
    assert isinstance(groups, list)
    groups_by_category = {
        group["category"]: group
        for group in groups
        if isinstance(group, dict) and isinstance(group.get("category"), str)
    }

    missing_categories = sorted(set(PHASE5_NON_REFERENCE_SEMANTIC_DUPLICATE_BUDGETS) - set(groups_by_category))
    assert missing_categories == []

    for category, budget in PHASE5_NON_REFERENCE_SEMANTIC_DUPLICATE_BUDGETS.items():
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


def test_runtime_projection_aggregate_budgets_stay_under_phase1_ceilings() -> None:
    payload = _prompt_surface_payload(("all",), ("all",), True)
    totals = payload["totals"]
    assert isinstance(totals, dict)
    runtime_projection = totals["runtime_projection"]
    assert isinstance(runtime_projection, dict)
    runtime_budgets = _runtime_projection_budgets(command_only=False)

    unexpected_runtimes = sorted(set(runtime_projection) - set(runtime_budgets))
    missing_runtimes = sorted(set(runtime_budgets) - set(runtime_projection))
    assert unexpected_runtimes == []
    assert missing_runtimes == []

    for runtime_name, budget in runtime_budgets.items():
        runtime_metrics = runtime_projection[runtime_name]
        assert isinstance(runtime_metrics, dict)
        _assert_runtime_projection_budget(f"{runtime_name} command+agent", runtime_metrics, budget)


def test_runtime_projection_command_only_budgets_stay_under_phase1_ceilings() -> None:
    payload = _prompt_surface_payload(("command",), ("all",), True)
    totals = payload["totals"]
    assert isinstance(totals, dict)
    runtime_projection = totals["runtime_projection"]
    assert isinstance(runtime_projection, dict)
    runtime_budgets = _runtime_projection_budgets(command_only=True)

    unexpected_runtimes = sorted(set(runtime_projection) - set(runtime_budgets))
    missing_runtimes = sorted(set(runtime_budgets) - set(runtime_projection))
    assert unexpected_runtimes == []
    assert missing_runtimes == []

    for runtime_name, budget in runtime_budgets.items():
        runtime_metrics = runtime_projection[runtime_name]
        assert isinstance(runtime_metrics, dict)
        _assert_runtime_projection_budget(f"{runtime_name} command-only", runtime_metrics, budget)
