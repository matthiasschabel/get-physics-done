"""Prompt diagnostics coverage through the public production API."""

from __future__ import annotations

import importlib
import textwrap
from pathlib import Path

from gpd import registry
from gpd.adapters.runtime_catalog import iter_runtime_descriptors

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPT_DIAGNOSTICS_PATH = REPO_ROOT / "src" / "gpd" / "core" / "prompt_diagnostics.py"


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
    assert payload["stage_diagnostics"][0]["runtime_projection"][0]["runtime"] == runtime_name


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
