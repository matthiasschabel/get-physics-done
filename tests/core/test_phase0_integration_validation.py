"""Phase 0 cross-surface integration guardrails."""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, is_dataclass
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
REAL_HOME_PATH_RE = re.compile(r"(?:/Users/[^/\s]+/|/home/[^/\s]+/|[A-Za-z]:\\Users\\[^\\\s]+\\)")

EXPECTED_PHASE0_ASSERTION_KIND_VALUES = {
    "machine_exact",
    "public_exact",
    "semantic_anchor",
    "budget",
    "forbidden_duplicate",
}
PHASE0_BASELINE_REPORT_BUILDERS = (
    "build_phase0_baseline_report",
    "build_baseline_report",
    "generate_phase0_baseline_report",
    "build_report",
)
PHASE0_BASELINE_REQUIRED_PATHS: Mapping[str, tuple[tuple[str, ...], ...]] = {
    "schema id": (("schema_id",), ("schema_version",)),
    "repo head": (("repo_head",), ("repo", "head")),
    "tree status class": (("tree_status_class",), ("repo", "tree_status_class")),
    "prompt totals": (("prompt_totals",), ("prompt_surface", "totals")),
    "totals by kind": (("totals_by_kind",), ("prompt_totals_by_kind",), ("prompt_surface", "totals_by_kind")),
    "runtime command-only projection totals": (
        ("runtime_projection_totals", "command_only"),
        ("runtime_projections", "command_only"),
    ),
    "runtime command+agent projection totals": (
        ("runtime_projection_totals", "command_and_agent"),
        ("runtime_projection_totals", "command_plus_agent"),
        ("runtime_projections", "command_and_agent"),
    ),
    "stage totals": (("stage_totals",), ("stage_diagnostics", "totals")),
    "duplicate invariant counts": (
        ("duplicate_invariant_counts",),
        ("duplicate_invariants", "counts"),
    ),
    "exact assertion totals": (("exact_assertion_totals",), ("exact_assertions", "totals")),
    "repo graph scope counts": (("repo_graph_scope_counts",), ("repo_graph", "scope_counts")),
    "provider-free safety summary": (
        ("provider_free_safety_summary",),
        ("live_audit_safety_summary",),
        ("provider_safety_summary",),
    ),
}
FORBIDDEN_PHASE0_BASELINE_FIELD_NAMES = {
    "account_email",
    "account_id",
    "account_identifier",
    "auth_material",
    "authorization_header",
    "argv",
    "env",
    "environment",
    "expanded_prompt_text",
    "full_transcript",
    "home_path",
    "process_env",
    "prompt_text",
    "provider_output_text",
    "provider_stderr",
    "provider_stdout",
    "raw_prompt",
    "raw_prompt_text",
    "raw_provider_output",
    "real_home_path",
    "stderr",
    "stdout",
    "transcript",
}


@pytest.fixture(scope="module")
def phase0_prompt_report() -> PromptSurfaceReport:
    return build_prompt_surface_report(
        REPO_ROOT,
        surfaces=("command", "agent", "workflow"),
        runtime_names=(),
        include_tests=False,
        include_runtime_projections=False,
    )


@pytest.fixture(scope="module")
def optional_phase0_baseline_payload() -> Mapping[str, object]:
    module = _optional_import("scripts.phase0_baseline_report")
    for builder_name in PHASE0_BASELINE_REPORT_BUILDERS:
        builder = getattr(module, builder_name, None)
        if callable(builder):
            return _as_mapping(_call_phase0_baseline_builder(builder), context=builder_name)
    pytest.skip("scripts.phase0_baseline_report has no importable baseline report builder yet")


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


def _optional_import(module_name: str) -> object:
    if importlib.util.find_spec(module_name) is None:
        pytest.skip(f"{module_name} is not available yet")
    return importlib.import_module(module_name)


def _call_phase0_baseline_builder(builder: Callable[..., object]) -> object:
    args: list[object] = []
    kwargs: dict[str, object] = {}
    signature = inspect.signature(builder)

    for parameter in signature.parameters.values():
        if parameter.kind in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}:
            continue
        if parameter.name not in {"repo_root", "root", "project_root"}:
            if parameter.default is inspect.Parameter.empty:
                pytest.skip(
                    f"{builder.__name__} requires unsupported parameter {parameter.name!r}"
                )
            continue
        if parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
            args.append(REPO_ROOT)
        else:
            kwargs[parameter.name] = REPO_ROOT

    return builder(*args, **kwargs)


def _as_mapping(payload: object, *, context: str) -> Mapping[str, object]:
    if isinstance(payload, Mapping):
        return payload
    if isinstance(payload, str):
        decoded = json.loads(payload)
        assert isinstance(decoded, Mapping), f"{context} JSON output must be an object"
        return cast(Mapping[str, object], decoded)
    to_dict = getattr(payload, "to_dict", None)
    if callable(to_dict):
        return _as_mapping(to_dict(), context=f"{context}.to_dict()")
    if is_dataclass(payload) and not isinstance(payload, type):
        return cast(Mapping[str, object], asdict(payload))
    pytest.skip(f"{context} did not return a dict-like baseline payload")


def _has_path(payload: Mapping[str, object], path: Sequence[str]) -> bool:
    current: object = payload
    for part in path:
        if not isinstance(current, Mapping) or part not in current:
            return False
        current = current[part]
    return True


def _normalized_field_name(name: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name).lower())


def _walk_payload(payload: object, path: tuple[str, ...] = ()) -> tuple[tuple[tuple[str, ...], object], ...]:
    entries: list[tuple[tuple[str, ...], object]] = [(path, payload)]
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            entries.extend(_walk_payload(value, (*path, str(key))))
    elif isinstance(payload, list | tuple):
        for index, value in enumerate(payload):
            entries.extend(_walk_payload(value, (*path, f"[{index}]")))
    return tuple(entries)


def test_phase0_assertion_taxonomy_exposes_expected_kind_values() -> None:
    module = _optional_import("tests.assertion_taxonomy_support")
    assertion_kind = getattr(module, "AssertionKind", None)
    if assertion_kind is None:
        pytest.skip("tests.assertion_taxonomy_support.AssertionKind is not available yet")

    values = {str(member.value) for member in assertion_kind}

    assert values == EXPECTED_PHASE0_ASSERTION_KIND_VALUES


def test_phase0_baseline_report_exposes_required_summary_keys(
    optional_phase0_baseline_payload: Mapping[str, object],
) -> None:
    missing = [
        label
        for label, accepted_paths in PHASE0_BASELINE_REQUIRED_PATHS.items()
        if not any(_has_path(optional_phase0_baseline_payload, path) for path in accepted_paths)
    ]

    assert missing == []


def test_phase0_baseline_report_excludes_raw_fields(
    optional_phase0_baseline_payload: Mapping[str, object],
) -> None:
    forbidden_field_names = {_normalized_field_name(name) for name in FORBIDDEN_PHASE0_BASELINE_FIELD_NAMES}
    forbidden_paths = [
        ".".join(path)
        for path, _value in _walk_payload(optional_phase0_baseline_payload)
        if path and _normalized_field_name(path[-1]) in forbidden_field_names
    ]
    home_path_values = [
        ".".join(path)
        for path, value in _walk_payload(optional_phase0_baseline_payload)
        if isinstance(value, str) and REAL_HOME_PATH_RE.search(value)
    ]

    assert forbidden_paths == []
    assert home_path_values == []


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
