"""Phase 0 cross-surface integration guardrails."""

from __future__ import annotations

import re
from pathlib import Path
from typing import cast

import pytest

from gpd import registry
from gpd.core.prompt_diagnostics import PromptSurfaceReport, build_prompt_surface_report, report_to_dict
from gpd.core.return_contract import validate_gpd_return_markdown
from gpd.core.workflow_staging import (
    WORKFLOW_STAGE_MANIFEST_DIR,
    WORKFLOW_STAGE_MANIFEST_SUFFIX,
    load_workflow_stage_manifest,
)
from scripts.repo_graph_contract import load_contract
from scripts.sync_repo_graph_contract import check_generated_artifacts

REPO_ROOT = Path(__file__).resolve().parents[2]
SPECS_DIR = REPO_ROOT / "src" / "gpd" / "specs"
YAML_FENCE_RE = re.compile(r"^```ya?ml[^\n]*\n(?P<body>.*?)(?:\n^```[ \t]*$)", re.MULTILINE | re.DOTALL)


@pytest.fixture(scope="module")
def phase0_prompt_report() -> PromptSurfaceReport:
    return build_prompt_surface_report(
        REPO_ROOT,
        surfaces=("command", "agent", "workflow"),
        runtime_names=(),
        include_tests=False,
        include_runtime_projections=False,
    )


def _prompt_item_path(raw_path: object) -> Path:
    path = Path(str(raw_path))
    return path if path.is_absolute() else REPO_ROOT / path


def _scope_count(label: str) -> int:
    contract = load_contract()
    scope_counts = contract["scope_counts"]
    assert isinstance(scope_counts, dict)
    value = scope_counts[label]
    assert isinstance(value, int)
    return value


def test_phase0_prompt_diagnostics_and_visible_return_examples_agree(
    phase0_prompt_report: PromptSurfaceReport,
) -> None:
    payload = report_to_dict(phase0_prompt_report)
    items = cast(list[dict[str, object]], payload["items"])
    invalid_examples = cast(list[dict[str, object]], payload["invalid_gpd_return_examples"])
    checked_examples = 0
    failures: list[str] = []

    for item in items:
        path = _prompt_item_path(item["path"])
        text = path.read_text(encoding="utf-8")
        for match in YAML_FENCE_RE.finditer(text):
            body = match.group("body")
            if "gpd_return" not in body:
                continue
            checked_examples += 1
            result = validate_gpd_return_markdown(f"```yaml\n{body.rstrip()}\n```")
            if result.passed:
                continue
            line_number = text.count("\n", 0, match.start()) + 1
            failures.append(f"{path.relative_to(REPO_ROOT).as_posix()}:{line_number}: {'; '.join(result.errors)}")

    totals = phase0_prompt_report.totals
    assert checked_examples > 0
    assert int(totals["visible_schema_example_count"]) >= checked_examples
    assert invalid_examples == []
    assert int(totals["invalid_gpd_return_example_count"]) == 0
    assert all(item["invalid_gpd_return_example_count"] == 0 for item in items)
    assert not failures, "Invalid visible gpd_return examples:\n" + "\n".join(failures)


def test_phase0_prompt_return_field_mentions_match_contract_allowlist(
    phase0_prompt_report: PromptSurfaceReport,
) -> None:
    assert phase0_prompt_report.disallowed_return_field_mentions == ()
    assert int(phase0_prompt_report.totals["disallowed_return_field_mention_count"]) == 0


def test_phase0_parent_workflows_do_not_instruct_child_return_synthesis(
    phase0_prompt_report: PromptSurfaceReport,
) -> None:
    assert phase0_prompt_report.forbidden_child_return_synthesis_mentions == ()
    assert int(phase0_prompt_report.totals["forbidden_child_return_synthesis_mention_count"]) == 0


def test_phase0_stage_manifests_preserve_eager_loading_boundaries() -> None:
    manifest_paths = sorted(WORKFLOW_STAGE_MANIFEST_DIR.glob(f"*{WORKFLOW_STAGE_MANIFEST_SUFFIX}"))

    assert manifest_paths
    for manifest_path in manifest_paths:
        workflow_id = manifest_path.name.removesuffix(WORKFLOW_STAGE_MANIFEST_SUFFIX)
        manifest = load_workflow_stage_manifest(workflow_id)
        workflow_path = WORKFLOW_STAGE_MANIFEST_DIR / f"{workflow_id}.md"

        assert workflow_path.is_file()
        assert manifest.workflow_id == workflow_id
        assert manifest.stage_ids() == tuple(stage.id for stage in manifest.stages)
        assert [stage.order for stage in manifest.stages] == list(range(1, len(manifest.stages) + 1))

        for stage in manifest.stages:
            payload = manifest.staged_loading_payload(stage.id)
            eager_authorities = tuple(cast(list[str], payload["eager_authorities"]))
            must_not_eager_load = tuple(cast(list[str], payload["must_not_eager_load"]))

            assert payload["workflow_id"] == workflow_id
            assert payload["stage_id"] == stage.id
            assert payload["required_init_fields"] == list(stage.required_init_fields)
            assert payload["mode_paths"] == list(stage.mode_paths)
            assert payload["loaded_authorities"] == list(stage.loaded_authorities)
            assert eager_authorities == stage.eager_authorities()
            assert set(stage.mode_paths).issubset(eager_authorities)
            assert set(stage.loaded_authorities).issubset(eager_authorities)
            assert set(eager_authorities).isdisjoint(must_not_eager_load)

            all_declared_authorities = (
                *stage.eager_authorities(),
                *stage.must_not_eager_load,
                *(authority for entry in stage.conditional_authorities for authority in entry.authorities),
            )
            assert all((SPECS_DIR / authority).is_file() for authority in all_declared_authorities)


def test_phase0_prompt_diagnostics_match_registry_workflow_and_graph_inventory(
    phase0_prompt_report: PromptSurfaceReport,
) -> None:
    registry.invalidate_cache()
    payload = report_to_dict(phase0_prompt_report)
    items = cast(list[dict[str, object]], payload["items"])
    names_by_kind = {
        kind: {str(item["name"]) for item in items if item["kind"] == kind}
        for kind in ("command", "agent", "workflow")
    }
    workflow_markdown = {
        path.stem for path in sorted(WORKFLOW_STAGE_MANIFEST_DIR.glob("*.md")) if path.is_file()
    }
    staged_workflows = {
        path.name.removesuffix(WORKFLOW_STAGE_MANIFEST_SUFFIX)
        for path in sorted(WORKFLOW_STAGE_MANIFEST_DIR.glob(f"*{WORKFLOW_STAGE_MANIFEST_SUFFIX}"))
    }

    assert names_by_kind["command"] == set(registry.list_commands())
    assert names_by_kind["agent"] == set(registry.list_agents())
    assert names_by_kind["workflow"] == workflow_markdown
    assert staged_workflows <= workflow_markdown
    assert int(phase0_prompt_report.totals["item_count"]) == sum(len(names) for names in names_by_kind.values())
    assert _scope_count("`src/gpd/commands/*.md`") == len(names_by_kind["command"])
    assert _scope_count("`src/gpd/agents/*.md`") == len(names_by_kind["agent"])
    assert _scope_count("`src/gpd/specs/workflows/*.md`") == len(names_by_kind["workflow"])


def test_phase0_repo_graph_generated_artifacts_are_current() -> None:
    diffs = check_generated_artifacts()

    assert not diffs, "\n".join(diffs)
