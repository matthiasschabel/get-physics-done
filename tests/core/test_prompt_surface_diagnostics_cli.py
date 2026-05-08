"""CLI smoke coverage for prompt-surface diagnostics."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from gpd.adapters.runtime_catalog import iter_runtime_descriptors
from gpd.cli import app


class _StableCliRunner(CliRunner):
    def invoke(self, *args, **kwargs):
        kwargs.setdefault("color", False)
        return super().invoke(*args, **kwargs)


runner = _StableCliRunner()


def _non_native_runtime_name() -> str:
    return next(
        descriptor.runtime_name for descriptor in iter_runtime_descriptors() if not descriptor.native_include_support
    )


def _tree_snapshot(root: Path) -> tuple[tuple[str, bool, bytes], ...]:
    return tuple(
        sorted(
            (
                path.relative_to(root).as_posix(),
                path.is_dir(),
                b"" if path.is_dir() else path.read_bytes(),
            )
            for path in root.rglob("*")
        )
    )


def test_prompt_surface_diagnostics_raw_json_shape() -> None:
    result = runner.invoke(
        app,
        ["--raw", "diagnostics", "prompt-surface", "--top", "3", "--no-runtime-projections"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)

    assert payload["schema_version"]
    assert isinstance(payload["totals"], dict)
    assert 1 <= len(payload["items"]) <= 3
    assert payload["runtime_top_prompts"] == {}
    assert payload["stage_diagnostics"]
    assert payload["items"][0]["runtime_projection"] == []
    assert isinstance(payload["invalid_gpd_return_examples"], list)
    assert isinstance(payload["invalid_frontmatter_examples"], list)
    assert isinstance(payload["disallowed_return_field_mentions"], list)
    assert isinstance(payload["semantic_duplicate_invariants"], list)


def test_prompt_surface_diagnostics_include_tests_exactness_summary() -> None:
    result = runner.invoke(
        app,
        [
            "--raw",
            "diagnostics",
            "prompt-surface",
            "--include-tests",
            "--top",
            "1",
            "--no-runtime-projections",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    exactness = json.loads(result.output)["exact_assertion_diagnostics"]
    assert exactness["schema_version"] == "exact_assertions.v1"
    assert exactness["totals"]["files_scanned"] > 0
    assert exactness["totals"]["exact_assertion_count"] > 0
    assert exactness["taxonomy_helper_usage"]["schema_version"] == "taxonomy_helper_usage.v1"
    assert exactness["taxonomy_helper_usage"]["totals"]["taxonomy_helper_call_count"] > 0


def test_prompt_surface_diagnostics_runtime_projection_and_renderers() -> None:
    runtime_name = _non_native_runtime_name()
    raw_result = runner.invoke(
        app,
        ["--raw", "diagnostics", "prompt-surface", "--top", "1", "--surface", "command", "--runtime", runtime_name],
        catch_exceptions=False,
    )
    markdown_result = runner.invoke(
        app,
        ["diagnostics", "prompt-surface", "--top", "1", "--no-runtime-projections", "--format", "markdown"],
        catch_exceptions=False,
    )
    table_result = runner.invoke(
        app,
        ["diagnostics", "prompt-surface", "--top", "1", "--surface", "command", "--runtime", runtime_name],
        catch_exceptions=False,
    )

    assert raw_result.exit_code == 0, raw_result.output
    payload = json.loads(raw_result.output)
    projection = payload["items"][0]["runtime_projection"][0]
    assert projection["runtime"] == runtime_name
    assert isinstance(projection["expanded_char_count"], int)
    assert isinstance(projection["shell_rewrite_count"], int)
    assert payload["runtime_top_prompts"][runtime_name][0]["runtime"] == runtime_name

    assert markdown_result.exit_code == 0, markdown_result.output
    assert "Prompt Surface Diagnostics" in markdown_result.output
    assert ".md" in markdown_result.output

    assert table_result.exit_code == 0, table_result.output
    assert "runtime top prompts" in table_result.output
    assert "projected_chars" in table_result.output
    assert runtime_name in table_result.output


def test_prompt_surface_diagnostics_is_read_only_outside_project(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.txt").write_text("scratch notes, not a GPD project\n", encoding="utf-8")
    before = _tree_snapshot(workspace)

    monkeypatch.chdir(workspace)
    result = runner.invoke(
        app,
        [
            "--cwd",
            str(workspace),
            "--raw",
            "diagnostics",
            "prompt-surface",
            "--top",
            "3",
            "--no-runtime-projections",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    json.loads(result.output)
    assert _tree_snapshot(workspace) == before
