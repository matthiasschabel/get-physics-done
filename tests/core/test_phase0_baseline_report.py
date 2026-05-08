"""Focused tests for the sanitized Phase 0 baseline report helper."""

from __future__ import annotations

import io
import json
import textwrap
from pathlib import Path

import scripts.phase0_baseline_report as phase0_baseline
from gpd.adapters.runtime_catalog import list_runtime_names


def test_phase0_baseline_report_shape_uses_prompt_diagnostics_and_class_only_summaries(tmp_path: Path) -> None:
    repo_root = _write_minimal_prompt_repo(tmp_path)
    runtime_name = _runtime_name()

    report = phase0_baseline.build_baseline_report(repo_root, runtime_names=(runtime_name,))

    assert report["schema"] == "phase0.baseline_report.v1"
    assert report["schema_id"] == "phase0.baseline_report.v1"
    assert report["prompt_diagnostics_schema"] == "prompt_surface_diagnostics.v7"
    assert report["repo"] == {"head": "unavailable", "tree_status_class": "not_git"}
    assert report["prompt_totals"]["item_count"] == 3
    assert report["kind_totals"]["command"]["item_count"] == 1
    assert report["totals_by_kind"]["command"]["item_count"] == 1
    assert report["kind_totals"]["agent"]["item_count"] == 1
    assert report["kind_totals"]["workflow"]["item_count"] == 1
    assert set(report["runtime_projection_totals"]["command_only"]) == {runtime_name}
    assert report["runtime_projection_totals"]["command_only"][runtime_name]["item_count"] == 1
    assert report["runtime_projection_totals"]["command_plus_agent"][runtime_name]["item_count"] == 2
    assert set(report["stage_totals"]) >= {"workflow_count", "stage_count", "first_turn_char_count"}
    assert set(report["duplicate_invariant_counts"]) >= {
        "literal_group_count",
        "semantic_group_count",
        "semantic_occurrence_count",
    }
    assert report["exact_assertion_totals"]["schema_version"] == "exact_assertions.v1"
    assert report["exact_assertion_totals"]["exact_assertion_count"] >= 2
    assert report["repo_graph_scope_counts"]["`src/gpd/commands/*.md`"] == 1
    safety = report["provider_free_live_audit_safety"]
    assert report["provider_free_safety_summary"] == safety
    assert safety["class_only"] is True
    assert safety["dry_run_launch_performed"] is False
    assert safety["preflight_process_launch_allowed"] is False
    assert safety["sensitive_material_retained"] is False
    assert safety["process_detail_retained"] is False


def test_phase0_baseline_report_excludes_prompt_provider_process_and_home_material(tmp_path: Path) -> None:
    repo_root = _write_minimal_prompt_repo(tmp_path)
    runtime_name = _runtime_name()
    home_path = str(Path.home())
    sentinel_values = (
        "SENSITIVE_PROMPT_TEXT_SHOULD_NOT_APPEAR",
        "PROVIDER_OUTPUT_SHOULD_NOT_APPEAR",
        "STDOUT_SHOULD_NOT_APPEAR",
        "ARGV_SHOULD_NOT_APPEAR",
        home_path,
    )
    _append(
        repo_root / "src" / "gpd" / "commands" / "alpha.md",
        "\n".join(sentinel_values) + "\n",
    )

    report = phase0_baseline.build_baseline_report(repo_root, runtime_names=(runtime_name,))
    json_output = phase0_baseline.render_json(report)
    markdown_output = phase0_baseline.render_markdown(report)
    combined = json_output + markdown_output

    for sentinel in sentinel_values:
        if sentinel:
            assert sentinel not in combined
    assert "stdout" not in combined.casefold()
    assert "stderr" not in combined.casefold()
    assert "transcript" not in combined.casefold()
    assert "argv" not in combined.casefold()
    assert "auth" not in combined.casefold()
    assert home_path not in combined


def test_phase0_baseline_report_cli_emits_json_and_markdown(tmp_path: Path) -> None:
    repo_root = _write_minimal_prompt_repo(tmp_path)
    runtime_name = _runtime_name()

    json_stdout = io.StringIO()
    assert (
        phase0_baseline.main(
            ["--repo-root", str(repo_root), "--runtime", runtime_name, "--format", "json"],
            stdout=json_stdout,
        )
        == 0
    )
    payload = json.loads(json_stdout.getvalue())
    assert payload["schema"] == "phase0.baseline_report.v1"
    assert payload["runtime_projection_totals"]["command_plus_agent"][runtime_name]["item_count"] == 2

    markdown_stdout = io.StringIO()
    assert (
        phase0_baseline.main(
            ["--repo-root", str(repo_root), "--runtime", runtime_name, "--format", "markdown"],
            stdout=markdown_stdout,
        )
        == 0
    )
    markdown = markdown_stdout.getvalue()
    assert markdown.startswith("# Phase 0 Baseline Report\n")
    assert "## Runtime Projection Totals" in markdown
    assert f"| `{runtime_name}` |" in markdown


def _runtime_name() -> str:
    runtime_names = list_runtime_names()
    assert runtime_names
    return runtime_names[0]


def _write_minimal_prompt_repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    invariant = "Use only status names: completed | checkpoint | blocked | failed when returning gpd_return status."
    _write(
        repo_root / "src" / "gpd" / "commands" / "alpha.md",
        f"""
        ---
        name: gpd:alpha
        description: Alpha command
        ---
        {invariant}

        ```yaml
        gpd_return:
          status: completed
          summary: Done.
          files_written: []
          issues: []
          next_actions: []
        ```
        """,
    )
    _write(
        repo_root / "src" / "gpd" / "agents" / "beta.md",
        f"""
        ---
        name: beta
        description: Beta agent
        ---
        {invariant}
        """,
    )
    _write(
        repo_root / "src" / "gpd" / "specs" / "workflows" / "gamma.md",
        f"""
        # Gamma

        {invariant}
        """,
    )
    _write(
        repo_root / "tests" / "test_prompt_exactness.py",
        """
        def test_exact_prompt_assertions(prompt):
            assert "GPD/state.json" in prompt
            assert "Quick Start" not in prompt
        """,
    )
    _write(
        repo_root / "tests" / "repo_graph_contract.json",
        json.dumps(
            {
                "schema_version": 1,
                "excluded_graph_dirs": [],
                "scope_counts": {
                    "`src/gpd/commands/*.md`": 1,
                    "`src/gpd/agents/*.md`": 1,
                    "`src/gpd/specs/workflows/*.md`": 1,
                    "`src/gpd/specs/templates/**/*.md`": 0,
                    "`src/gpd/specs/references/**/*.md`": 0,
                    "`src/gpd/adapters/*.py`": 0,
                    "`src/gpd/hooks/*.py`": 0,
                    "`src/gpd/mcp/*.py`": 0,
                    "`src/gpd/mcp/integrations/*.py`": 0,
                    "`src/gpd/mcp/servers/*.py`": 0,
                    "`infra/gpd-*.json`": 0,
                },
            },
            indent=2,
        )
        + "\n",
    )
    return repo_root


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def _append(path: Path, content: str) -> None:
    path.write_text(path.read_text(encoding="utf-8") + content, encoding="utf-8")
