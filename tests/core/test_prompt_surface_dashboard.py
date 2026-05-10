"""Renderer coverage for the prompt-surface dashboard."""

from __future__ import annotations

import importlib
import textwrap
from pathlib import Path

from gpd.adapters.runtime_catalog import iter_runtime_descriptors
from gpd.core.prompt_surface_dashboard import render_prompt_surface_dashboard
from tests.assertion_taxonomy_support import MatchMode, assert_prompt_contracts, machine_exact, semantic_anchor

DASHBOARD_SECTION_LABELS = (
    "Prompt totals",
    "Safety floors",
    "Stage loading totals",
    "Top stage eager loads",
    "Top prior-stage residue contributors",
    "Staged-init pressure by stage",
    "Top staged-init fields",
    "Exactness totals",
    "Top exact/brittle files",
    "Semantic duplicate non-reference counts",
    "Runtime projection totals",
    "Validation timing references",
)


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


def _write_dashboard_probe_project(root: Path) -> None:
    _write(
        root,
        "src/gpd/commands/probe.md",
        """
        ---
        name: gpd:probe
        description: Probe command
        ---
        @{GPD_INSTALL_DIR}/workflows/probe-router.md

        Route on gpd_return.status values completed, checkpoint, blocked, or failed.
        STOP before accepting stale runtime success as proof.

        ```yaml
        gpd_return:
          status: completed
          files_written: []
        ```
        """,
    )
    _write(
        root,
        "src/gpd/specs/workflows/probe-router.md",
        """
        ---
        name: probe-router
        ---
        Route on gpd_return.status values completed, checkpoint, blocked, or failed.
        """,
    )
    _write(
        root,
        "src/gpd/specs/workflows/probe-bootstrap.md",
        """
        ---
        name: probe-bootstrap
        ---
        Bootstrap body names project_contract, phase_context, and schema_bridge.
        """,
    )
    _write(
        root,
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
              "required_init_fields": ["workspace_root"],
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
              "required_init_fields": [
                "workspace_root",
                "phase_context",
                "project_contract",
                "schema_bridge"
              ],
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
    _write(
        root,
        "tests/test_prompt_contracts.py",
        """
        PROMPT = "gpd_return:\\nQuick Start\\nstable semantic anchor\\n"

        def test_prompt_contracts():
            assert "gpd_return:" in PROMPT
            assert "Quick Start" in PROMPT
            assert "stable semantic anchor" in PROMPT
        """,
    )


def _write_runtime_probe_project(root: Path) -> None:
    _write(
        root,
        "src/gpd/commands/probe.md",
        """
        ---
        name: gpd:probe
        description: Probe command
        ---
        Probe runtime body with @{GPD_INSTALL_DIR}/references/runtime.md.
        """,
    )
    _write(root, "src/gpd/specs/references/runtime.md", "Runtime reference body.\n")


def _report(root: Path, **kwargs):
    options = {
        "surfaces": ("command", "agent", "workflow"),
        "runtime_names": (),
        "include_tests": False,
        "include_runtime_projections": True,
    }
    options.update(kwargs)
    return _diagnostics().build_prompt_surface_report(root, **options)


def _section_text(output: str, section_label: str) -> str:
    folded_output = output.casefold()
    folded_section_label = section_label.casefold()
    start = folded_output.index(folded_section_label)
    tail = output[start + len(section_label) :]
    folded_tail = tail.casefold()
    next_starts = [
        folded_tail.index(label.casefold())
        for label in DASHBOARD_SECTION_LABELS
        if label.casefold() != folded_section_label and label.casefold() in folded_tail
    ]
    end = min(next_starts) if next_starts else len(tail)
    return tail[:end]


def test_dashboard_renders_required_phase0_sections(tmp_path: Path) -> None:
    _write_dashboard_probe_project(tmp_path)
    report = _report(tmp_path, include_tests=True, include_runtime_projections=False)

    payload = _diagnostics().report_to_dict(report, top=5)
    assert payload["semantic_duplicate_invariants"]
    dashboard = render_prompt_surface_dashboard(report, top=5)

    assert_prompt_contracts(
        dashboard,
        semantic_anchor(
            "dashboard sections",
            DASHBOARD_SECTION_LABELS,
            match=MatchMode.CASEFOLD_NORMALIZED,
        ),
        machine_exact(
            "dashboard field keys",
            (
                "command",
                "agent",
                "workflow",
                "item_count",
                "expanded_char_count",
                "hard_gate_line_count",
                "must_not_eager_load_violation_count",
                "prior_stage_residue_count",
                "field_name",
                "field_pressure_class",
                "files_scanned",
                "exact_assertion_count",
                "non_reference_file_count",
            ),
        ),
    )

    runtime_root = tmp_path / "runtime"
    _write_runtime_probe_project(runtime_root)
    runtime_name = _non_native_runtime_name()
    runtime_report = _report(
        runtime_root,
        surfaces=("command",),
        runtime_names=(runtime_name,),
        include_runtime_projections=True,
    )
    runtime_dashboard = render_prompt_surface_dashboard(runtime_report, top=5)
    assert_prompt_contracts(
        _section_text(runtime_dashboard, "Runtime projection totals"),
        machine_exact("runtime projection row", ("Runtime", "Projected chars", runtime_name)),
    )


def test_dashboard_labels_runtime_and_exactness_not_collected(tmp_path: Path) -> None:
    _write_dashboard_probe_project(tmp_path)
    report = _report(tmp_path, include_tests=False, include_runtime_projections=False)

    dashboard = render_prompt_surface_dashboard(report, top=5)

    assert "not collected" in _section_text(dashboard, "Runtime projection totals").casefold()
    assert "not collected" in _section_text(dashboard, "Exactness totals").casefold()


def test_dashboard_keeps_prior_stage_residue_distinct_from_eager_violations(tmp_path: Path) -> None:
    _write_dashboard_probe_project(tmp_path)
    report = _report(tmp_path, include_runtime_projections=False)

    payload = _diagnostics().report_to_dict(report, top=5)
    stage_totals = payload["totals"]["stage_diagnostics"]
    assert stage_totals["must_not_eager_load_violation_count"] == 0
    assert stage_totals["prior_stage_residue_count"] == 1

    dashboard = render_prompt_surface_dashboard(report, top=5)
    loading_section = _section_text(dashboard, "Stage loading totals")
    residue_section = _section_text(dashboard, "Top prior-stage residue contributors")

    assert_prompt_contracts(
        loading_section,
        machine_exact(
            "stage loading distinct totals",
            ("must_not_eager_load_violation_count", "prior_stage_residue_count"),
        ),
    )
    assert_prompt_contracts(
        residue_section,
        machine_exact(
            "prior-stage residue row",
            ("phase_bootstrap", "workflows/probe-router.md", "prior_stage_residue"),
        ),
    )
