"""Prompt diagnostics coverage through the public production API."""

from __future__ import annotations

import importlib
import textwrap
from pathlib import Path

from gpd import registry
from gpd.adapters.runtime_catalog import iter_runtime_descriptors

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPT_DIAGNOSTICS_PATH = REPO_ROOT / "src" / "gpd" / "core" / "prompt_diagnostics.py"
PROMPT_MARKDOWN_SCAN_PATH = REPO_ROOT / "src" / "gpd" / "core" / "prompt_markdown_scan.py"
PROMPT_DIAGNOSTICS_TOTAL_LOC_CAP = 3_850
PROMPT_DIAGNOSTICS_SPLIT_FACADE_LOC_CAP = 3_200
PROMPT_DIAGNOSTICS_SUPPORT_MODULE_LOC_CAP = 1_200


def _diagnostics():
    return importlib.import_module("gpd.core.prompt_diagnostics")


def _non_native_runtime_name() -> str:
    return next(
        descriptor.runtime_name for descriptor in iter_runtime_descriptors() if not descriptor.native_include_support
    )


def _write(root: Path, relative_path: str, content: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    return path


def _report(repo_root: Path, **kwargs):
    options = {
        "surfaces": ("command", "agent", "workflow"),
        "runtime_names": (),
        "include_tests": False,
        "include_runtime_projections": True,
    }
    options.update(kwargs)
    return _diagnostics().build_prompt_surface_report(repo_root, **options)


def _relative_report_path(raw_path: str) -> str:
    path = Path(raw_path)
    if path.is_absolute():
        return path.relative_to(REPO_ROOT).as_posix()
    return path.as_posix()


def _stage_by_id(payload: dict[str, object], stage_id: str) -> dict[str, object]:
    diagnostics = payload["stage_diagnostics"]
    assert isinstance(diagnostics, list)
    assert len(diagnostics) == 1
    stages = diagnostics[0]["stages"]
    return next(stage for stage in stages if stage["stage_id"] == stage_id)


def _source_line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def test_report_includes_registered_command_agent_and_workflow_sources() -> None:
    report = _report(REPO_ROOT, runtime_names=())

    actual_paths_by_kind: dict[str, set[str]] = {}
    for item in report.items:
        actual_paths_by_kind.setdefault(item.kind, set()).add(_relative_report_path(item.path))

    expected_command_paths = {f"src/gpd/commands/{name}.md" for name in registry.list_commands()}
    expected_agent_paths = {f"src/gpd/agents/{name}.md" for name in registry.list_agents()}
    expected_workflow_paths = {
        path.relative_to(REPO_ROOT).as_posix()
        for path in sorted((REPO_ROOT / "src" / "gpd" / "specs" / "workflows").glob("*.md"))
    }

    assert expected_command_paths <= actual_paths_by_kind.get("command", set())
    assert expected_agent_paths <= actual_paths_by_kind.get("agent", set())
    assert expected_workflow_paths <= actual_paths_by_kind.get("workflow", set())


def test_report_to_dict_exposes_stable_public_shape(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/commands/probe.md",
        """
        ---
        name: gpd:probe
        description: Probe command
        ---
        Probe body.
        """,
    )

    report = _report(tmp_path, surfaces=("command",), runtime_names=())
    payload = _diagnostics().report_to_dict(report)

    assert payload["schema_version"] == report.schema_version
    assert isinstance(payload["totals"], dict)
    assert isinstance(payload["items"], list)
    assert len(payload["items"]) == 1
    assert payload["items"][0]["name"] == "probe"
    assert payload["items"][0]["runtime_projection"] == []
    assert payload["runtime_top_prompts"] == {}
    assert payload["stage_diagnostics"] == []
    assert payload["invalid_gpd_return_examples"] == []
    assert payload["invalid_frontmatter_examples"] == []
    assert payload["disallowed_return_field_mentions"] == []
    assert payload["forbidden_child_return_synthesis_mentions"] == []
    assert payload["exact_assertion_diagnostics"]["schema_version"] == "exact_assertions.v1"
    assert payload["exact_assertion_diagnostics"]["totals"]["exact_assertion_count"] == 0


def test_stage_diagnostics_detect_transitive_eager_loading_violations(tmp_path: Path) -> None:
    runtime_name = _non_native_runtime_name()
    _write(
        tmp_path,
        "src/gpd/commands/probe.md",
        """
        ---
        name: gpd:probe
        description: Probe command
        ---
        @{GPD_INSTALL_DIR}/workflows/probe.md
        """,
    )
    _write(
        tmp_path,
        "src/gpd/specs/workflows/probe.md",
        """
        ---
        name: probe
        ---
        Stage bootstrap body.
        @{GPD_INSTALL_DIR}/templates/deferred.md
        """,
    )
    _write(tmp_path, "src/gpd/specs/templates/deferred.md", "Deferred authority body.\n")
    _write(
        tmp_path,
        "src/gpd/specs/workflows/probe-stage-manifest.json",
        """
        {
          "schema_version": 1,
          "workflow_id": "probe",
          "stages": [
            {
              "id": "bootstrap",
              "order": 1,
              "purpose": "Load the probe bootstrap.",
              "mode_paths": ["workflows/probe.md"],
              "required_init_fields": [],
              "loaded_authorities": ["workflows/probe.md"],
              "conditional_authorities": [
                {"when": "need_deferred", "authorities": ["templates/deferred.md"]}
              ],
              "must_not_eager_load": ["templates/deferred.md"],
              "allowed_tools": [],
              "writes_allowed": [],
              "produced_state": [],
              "next_stages": [],
              "checkpoints": []
            }
          ]
        }
        """,
    )

    payload = _diagnostics().report_to_dict(
        _report(tmp_path, surfaces=("command",), runtime_names=(runtime_name,)),
    )

    stage = payload["stage_diagnostics"][0]["stages"][0]
    assert stage["eager_authorities"] == ["workflows/probe.md"]
    assert stage["lazy_authorities"] == ["templates/deferred.md"]
    assert "templates/deferred.md" in stage["eager_authority_metrics"][0]["transitive_include_authorities"]
    violation_sources = {violation["violation_source"] for violation in stage["must_not_eager_load_violations"]}
    assert {"first_turn_transitive_include", "stage_eager_transitive_include"} <= violation_sources
    assert payload["totals"]["stage_diagnostics"]["must_not_eager_load_violation_count"] == len(
        stage["must_not_eager_load_violations"]
    )
    assert payload["stage_diagnostics"][0]["runtime_projection"][0]["runtime"] == runtime_name


def test_stage_diagnostics_classifies_prior_stage_first_turn_residue_without_counting_violation(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "src/gpd/commands/probe.md",
        """
        ---
        name: gpd:probe
        description: Probe command
        ---
        @{GPD_INSTALL_DIR}/workflows/probe-router.md
        """,
    )
    _write(tmp_path, "src/gpd/specs/workflows/probe-router.md", "Router body.\n")
    _write(tmp_path, "src/gpd/specs/workflows/probe-bootstrap.md", "Bootstrap body.\n")
    _write(
        tmp_path,
        "src/gpd/specs/workflows/probe-stage-manifest.json",
        """
        {
          "schema_version": 1,
          "workflow_id": "probe",
          "stages": [
            {
              "id": "session_router",
              "order": 1,
              "purpose": "Route into the staged workflow.",
              "mode_paths": ["workflows/probe-router.md"],
              "required_init_fields": [],
              "loaded_authorities": ["workflows/probe-router.md"],
              "conditional_authorities": [],
              "must_not_eager_load": [],
              "allowed_tools": [],
              "writes_allowed": [],
              "produced_state": [],
              "next_stages": ["phase_bootstrap"],
              "checkpoints": []
            },
            {
              "id": "phase_bootstrap",
              "order": 2,
              "purpose": "Bootstrap the selected phase without reloading the router.",
              "mode_paths": ["workflows/probe-bootstrap.md"],
              "required_init_fields": [],
              "loaded_authorities": ["workflows/probe-bootstrap.md"],
              "conditional_authorities": [],
              "must_not_eager_load": ["workflows/probe-router.md"],
              "allowed_tools": [],
              "writes_allowed": [],
              "produced_state": [],
              "next_stages": [],
              "checkpoints": []
            }
          ]
        }
        """,
    )

    payload = _diagnostics().report_to_dict(_report(tmp_path, surfaces=("command",), runtime_names=()))

    bootstrap = _stage_by_id(payload, "phase_bootstrap")
    residue_metrics = bootstrap["prior_stage_residue_authority_metrics"]
    assert bootstrap["must_not_eager_load_violations"] == []
    assert [metric["authority"] for metric in residue_metrics] == ["workflows/probe-router.md"]
    assert residue_metrics[0]["violation_source"] == "prior_stage_residue"
    assert residue_metrics[0]["eager_via"] == ["workflows/probe-router.md"]
    assert payload["totals"]["stage_diagnostics"]["must_not_eager_load_violation_count"] == 0
    assert payload["totals"]["stage_diagnostics"]["prior_stage_residue_count"] == 1


def test_stage_diagnostics_exposes_conditional_authority_bucket_and_metrics(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/commands/probe.md",
        """
        ---
        name: gpd:probe
        description: Probe command
        ---
        @{GPD_INSTALL_DIR}/workflows/probe.md
        """,
    )
    _write(tmp_path, "src/gpd/specs/workflows/probe.md", "Probe body.\n")
    _write(tmp_path, "src/gpd/specs/references/deep-dive.md", "Deep dive authority.\n")
    _write(tmp_path, "src/gpd/specs/templates/deferred.md", "Deferred body.\n")
    _write(
        tmp_path,
        "src/gpd/specs/workflows/probe-stage-manifest.json",
        """
        {
          "schema_version": 1,
          "workflow_id": "probe",
          "stages": [
            {
              "id": "bootstrap",
              "order": 1,
              "purpose": "Load the probe bootstrap.",
              "mode_paths": ["workflows/probe.md"],
              "required_init_fields": [],
              "loaded_authorities": ["workflows/probe.md"],
              "conditional_authorities": [
                {"when": "need_deep_dive", "authorities": ["references/deep-dive.md"]}
              ],
              "must_not_eager_load": ["templates/deferred.md"],
              "allowed_tools": [],
              "writes_allowed": [],
              "produced_state": [],
              "next_stages": [],
              "checkpoints": []
            }
          ]
        }
        """,
    )

    payload = _diagnostics().report_to_dict(_report(tmp_path, surfaces=("command",), runtime_names=()))

    stage = _stage_by_id(payload, "bootstrap")
    assert stage["conditional_authorities"] == [
        {"when": "need_deep_dive", "authorities": ["references/deep-dive.md"]}
    ]
    assert [metric["authority"] for metric in stage["conditional_authority_metrics"]] == [
        "references/deep-dive.md"
    ]
    assert stage["conditional_char_count"] == stage["conditional_authority_metrics"][0]["expanded_char_count"]
    assert "references/deep-dive.md" not in stage["eager_authorities"]

    bucket_rows = stage["authority_bucket_metrics"]
    conditional_rows = [
        row
        for row in bucket_rows
        if row["bucket"] == "conditional" and row["authority"] == "references/deep-dive.md"
    ]
    assert conditional_rows
    assert {row["bucket"] for row in bucket_rows} >= {"first_turn_active", "stage_eager", "conditional", "lazy"}


def test_stage_init_field_pressure_rows_classify_likely_bulky_fields(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/commands/probe.md",
        """
        ---
        name: gpd:probe
        description: Probe command
        ---
        @{GPD_INSTALL_DIR}/workflows/probe.md
        """,
    )
    _write(tmp_path, "src/gpd/specs/workflows/probe.md", "Probe body.\n")
    _write(
        tmp_path,
        "src/gpd/specs/workflows/probe-stage-manifest.json",
        """
        {
          "schema_version": 1,
          "workflow_id": "probe",
          "stages": [
            {
              "id": "bootstrap",
              "order": 1,
              "purpose": "Load the probe bootstrap.",
              "mode_paths": ["workflows/probe.md"],
              "required_init_fields": [
                "workspace_root",
                "phase_context",
                "project_contract",
                "revision_report",
                "schema_bridge",
                "reference_artifacts",
                "state_content"
              ],
              "loaded_authorities": ["workflows/probe.md"],
              "conditional_authorities": [],
              "must_not_eager_load": [],
              "allowed_tools": [],
              "writes_allowed": [],
              "produced_state": [],
              "next_stages": [],
              "checkpoints": []
            }
          ]
        }
        """,
    )

    payload = _diagnostics().report_to_dict(_report(tmp_path, surfaces=("command",), runtime_names=()))

    rows = [
        row
        for row in payload["stage_init_field_diagnostics"]
        if row["workflow_id"] == "probe" and row["stage_id"] == "bootstrap"
    ]
    rows_by_field = {row["field_name"]: row for row in rows}
    likely_bulky_fields = {
        "phase_context",
        "project_contract",
        "revision_report",
        "schema_bridge",
        "reference_artifacts",
        "state_content",
    }
    assert set(rows_by_field) == likely_bulky_fields | {"workspace_root"}
    assert all(
        rows_by_field[field]["field_pressure_class"] == "likely_bulky" for field in likely_bulky_fields
    )
    assert rows_by_field["workspace_root"]["field_pressure_class"] == "ordinary"
    assert rows_by_field["project_contract"]["field_kind_guess"] == "contract"
    assert rows_by_field["schema_bridge"]["field_kind_guess"] == "schema_bridge"
    assert rows_by_field["state_content"]["field_kind_guess"] == "content"
    assert {row["selection_count"] for row in rows} == {1}
    assert {row["required_init_field_count"] for row in rows} == {7}
    assert {row["likely_bulky_field_count"] for row in rows} == {6}


def test_stage_diagnostics_uses_workflow_staging_group_validation_for_local_sources(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/commands/quick.md",
        """
        ---
        name: gpd:quick
        description: Quick command
        ---
        @{GPD_INSTALL_DIR}/workflows/quick.md
        """,
    )
    _write(tmp_path, "src/gpd/specs/workflows/quick.md", "Quick bootstrap body.\n")
    _write(
        tmp_path,
        "src/gpd/specs/workflows/quick-stage-manifest.json",
        """
        {
          "schema_version": 1,
          "workflow_id": "quick",
          "required_init_field_groups": {
            "reference_runtime": [
              "selected_protocol_bundle_ids",
              "protocol_bundle_count",
              "protocol_bundle_context",
              "not_a_quick_field"
            ]
          },
          "stages": [
            {
              "id": "bootstrap",
              "order": 1,
              "purpose": "Load local quick bootstrap.",
              "mode_paths": ["workflows/quick.md"],
              "required_init_field_groups": ["reference_runtime"],
              "required_init_fields": [],
              "loaded_authorities": ["workflows/quick.md"],
              "conditional_authorities": [],
              "must_not_eager_load": [],
              "allowed_tools": [],
              "writes_allowed": [],
              "produced_state": [],
              "next_stages": [],
              "checkpoints": []
            }
          ]
        }
        """,
    )

    payload = _diagnostics().report_to_dict(_report(tmp_path, surfaces=("command",), runtime_names=()))

    assert payload["stage_diagnostics"] == []
    assert any(
        "unknown field name" in warning and "not_a_quick_field" in warning for warning in payload["warnings"]
    )


def test_report_detects_invalid_schema_and_forbidden_child_return_synthesis(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/specs/workflows/probe.md",
        """
        ---
        name: probe
        ---
        The parent may synthesize the child gpd_return if the spawned agent forgets it.

        ```yaml
        gpd_return:
          status: completed
          files_written: []
          bogus_child_field: true
        ```

        ```markdown
        ---
        phase: "01"
        status: maybe
        contract_results: []
        ---
        ```
        """,
    )

    payload = _diagnostics().report_to_dict(_report(tmp_path, surfaces=("workflow",), runtime_names=()))

    assert payload["invalid_gpd_return_examples"]
    assert payload["invalid_frontmatter_examples"]
    assert payload["disallowed_return_field_mentions"]
    assert payload["forbidden_child_return_synthesis_mentions"]
    assert payload["items"][0]["visible_schema_example_count"] >= 2


def test_include_counting_ignores_fenced_code_and_runtime_projection_covers_runtimes(tmp_path: Path) -> None:
    runtime_name = _non_native_runtime_name()
    _write(
        tmp_path,
        "src/gpd/commands/probe.md",
        """
        ---
        name: gpd:probe
        description: Probe command
        ---
        @{GPD_INSTALL_DIR}/workflows/probe.md

        ```bash
        @{GPD_INSTALL_DIR}/workflows/ignored.md
        ```
        """,
    )
    _write(tmp_path, "src/gpd/specs/workflows/probe.md", "Included body.\n")
    _write(tmp_path, "src/gpd/specs/workflows/ignored.md", "Ignored body.\n")

    payload = _diagnostics().report_to_dict(
        _report(tmp_path, surfaces=("command",), runtime_names=(runtime_name,)),
    )

    item = payload["items"][0]
    assert item["raw_include_count"] == 1
    assert item["expanded_include_count"] == 1
    projection = item["runtime_projection"][0]
    assert projection["runtime"] == runtime_name
    assert projection["line_count"] >= 1
    assert projection["char_count"] >= projection["expanded_char_count"]
    assert payload["runtime_top_prompts"][runtime_name][0]["name"] == "probe"


def test_exact_assertion_diagnostics_and_taxonomy_usage_are_additive(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "tests/test_prompt_contracts.py",
        """
        from tests.assertion_taxonomy_support import (
            assert_fragments,
            assert_prompt_contracts,
            machine_exact,
            public_exact,
            semantic_anchor,
        )

        PROMPT = "Quick Start\\ngpd_return:\\nstable semantic anchor\\n"

        def test_prompt_contracts():
            assert "gpd_return:" in PROMPT
            assert "Quick Start" in PROMPT
            assert "the exact old sentence is gone forever" not in PROMPT
            assert_prompt_contracts(
                PROMPT,
                machine_exact("schema", "gpd_return:"),
                public_exact("help", "Quick Start"),
                semantic_anchor("meaning", "stable semantic anchor"),
            )
            assert_fragments(PROMPT, semantic_anchor("direct fragment", "stable semantic anchor"))
        """,
    )

    exactness = _diagnostics().report_to_dict(_report(tmp_path, include_tests=True))["exact_assertion_diagnostics"]
    usage = exactness["taxonomy_helper_usage"]

    assert exactness["totals"]["exact_assertion_count"] >= 2
    assert exactness["totals"]["public_ux_exact_assertions"] >= 1
    assert usage["totals"]["assert_prompt_contracts"] == 1
    assert usage["totals"]["machine_exact"] == 1
    assert usage["totals"]["public_exact"] == 1
    assert usage["totals"]["semantic_anchor"] == 2


def test_renderers_include_actionable_sections(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/commands/probe.md",
        """
        ---
        name: gpd:probe
        description: Probe command
        ---
        Probe body with gpd_return.status and a STOP gate.
        """,
    )

    diagnostics = _diagnostics()
    report = _report(tmp_path, surfaces=("command",), runtime_names=(_non_native_runtime_name(),))
    markdown = diagnostics.render_prompt_surface_markdown(report, top=1)
    table = diagnostics.render_prompt_surface_table(report, top=1)

    assert "Prompt Surface Diagnostics" in markdown
    assert "Runtime Projection Totals" in markdown
    assert "kind" in table
    assert "runtime top prompts" in table


def test_production_prompt_diagnostics_does_not_import_from_tests() -> None:
    source = PROMPT_DIAGNOSTICS_PATH.read_text(encoding="utf-8")

    assert "from tests" not in source
    assert "import tests" not in source


def test_prompt_diagnostics_modules_stay_small_enough_for_phase_6_split() -> None:
    module_paths = sorted(
        {
            PROMPT_MARKDOWN_SCAN_PATH,
            *PROMPT_DIAGNOSTICS_PATH.parent.glob("prompt_diagnostics*.py"),
            *PROMPT_DIAGNOSTICS_PATH.parent.glob("prompt_*_diagnostics.py"),
        }
    )
    loc_by_module = {path.name: _source_line_count(path) for path in module_paths}
    support_module_loc = {
        name: line_count for name, line_count in loc_by_module.items() if name != PROMPT_DIAGNOSTICS_PATH.name
    }

    assert PROMPT_DIAGNOSTICS_PATH.name in loc_by_module
    assert sum(loc_by_module.values()) <= PROMPT_DIAGNOSTICS_TOTAL_LOC_CAP, loc_by_module

    if support_module_loc:
        assert loc_by_module[PROMPT_DIAGNOSTICS_PATH.name] <= PROMPT_DIAGNOSTICS_SPLIT_FACADE_LOC_CAP, loc_by_module
        assert all(
            line_count <= PROMPT_DIAGNOSTICS_SUPPORT_MODULE_LOC_CAP
            for line_count in support_module_loc.values()
        ), support_module_loc


def test_prompt_diagnostics_does_not_define_local_stage_manifest_parser() -> None:
    source = PROMPT_DIAGNOSTICS_PATH.read_text(encoding="utf-8")

    assert "_load_local_source_stage_manifest" not in source
    assert "_manifest_string_list" not in source
