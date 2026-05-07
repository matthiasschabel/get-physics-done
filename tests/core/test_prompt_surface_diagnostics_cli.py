"""CLI coverage for prompt-surface diagnostics."""

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

EXPECTED_RUNTIME_PROJECTION_KEYS = {
    "runtime",
    "native_include_support",
    "expanded_line_count",
    "expanded_char_count",
    "line_count",
    "char_count",
    "include_count",
    "runtime_note_count",
    "runtime_note_chars",
    "shell_fence_count",
    "shell_rewrite_count",
    "bridge_command_occurrences",
}
EXPECTED_RUNTIME_TOP_PROMPT_KEYS = {
    "runtime",
    "native_include_support",
    "kind",
    "name",
    "path",
    "projected_line_count",
    "projected_char_count",
    "expanded_line_count",
    "expanded_char_count",
    "include_count",
    "runtime_note_count",
    "runtime_note_chars",
    "shell_rewrite_count",
}


def _non_native_runtime_name() -> str:
    return next(descriptor.runtime_name for descriptor in iter_runtime_descriptors() if not descriptor.native_include_support)


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

    assert isinstance(payload["schema_version"], str)
    assert payload["schema_version"]
    assert isinstance(payload["repo_root"], str)
    assert isinstance(payload["totals"], dict)
    assert isinstance(payload["items"], list)
    assert 1 <= len(payload["items"]) <= 3
    assert payload["runtime_top_prompts"] == {}
    assert isinstance(payload["invalid_gpd_return_examples"], list)
    assert isinstance(payload["duplicate_invariants"], list)
    assert isinstance(payload["exact_prose_assertion_files"], list)
    assert isinstance(payload["warnings"], list)

    for item in payload["items"]:
        assert item["kind"] in {"command", "agent", "workflow"}
        assert item["name"]
        assert item["path"].endswith(".md")
        assert isinstance(item["raw_line_count"], int)
        assert isinstance(item["raw_char_count"], int)
        assert isinstance(item["raw_include_count"], int)
        assert isinstance(item["expanded_line_count"], int)
        assert isinstance(item["expanded_char_count"], int)
        assert isinstance(item["expanded_include_count"], int)
        assert isinstance(item["unresolved_include_count"], int)
        assert isinstance(item["visible_schema_example_count"], int)
        assert isinstance(item["invalid_gpd_return_example_count"], int)
        assert isinstance(item["invalid_gpd_return_examples"], list)
        assert isinstance(item["hard_gate_line_count"], int)
        assert isinstance(item["hard_gate_density"], int | float)
        assert isinstance(item["shell_fence_count"], int)
        assert isinstance(item["shell_parsing_line_count"], int)
        assert isinstance(item["rigidity_index"], int)
        assert item["runtime_projection"] == []

    for example in payload["invalid_gpd_return_examples"]:
        assert isinstance(example["path"], str)
        assert example["path"].endswith(".md")
        assert isinstance(example["start_line"], int)
        assert isinstance(example["end_line"], int)
        assert example["start_line"] <= example["end_line"]
        assert isinstance(example["errors"], list)
        assert all(isinstance(error, str) for error in example["errors"])
        assert isinstance(example["preview"], str)


def test_prompt_surface_diagnostics_raw_json_runtime_projection_shape() -> None:
    runtime_name = _non_native_runtime_name()
    result = runner.invoke(
        app,
        ["--raw", "diagnostics", "prompt-surface", "--top", "1", "--surface", "command", "--runtime", runtime_name],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)

    assert len(payload["items"]) == 1
    runtime_projection = payload["items"][0]["runtime_projection"]
    assert len(runtime_projection) == 1
    assert set(runtime_projection[0]) == EXPECTED_RUNTIME_PROJECTION_KEYS
    assert runtime_projection[0]["runtime"] == runtime_name
    assert isinstance(runtime_projection[0]["expanded_line_count"], int)
    assert isinstance(runtime_projection[0]["expanded_char_count"], int)
    assert isinstance(runtime_projection[0]["shell_rewrite_count"], int)

    runtime_top_prompts = payload["runtime_top_prompts"]
    assert set(runtime_top_prompts) == {runtime_name}
    assert len(runtime_top_prompts[runtime_name]) == 1
    assert set(runtime_top_prompts[runtime_name][0]) == EXPECTED_RUNTIME_TOP_PROMPT_KEYS
    assert runtime_top_prompts[runtime_name][0]["runtime"] == runtime_name
    assert isinstance(runtime_top_prompts[runtime_name][0]["projected_char_count"], int)
    assert isinstance(runtime_top_prompts[runtime_name][0]["expanded_char_count"], int)


def test_prompt_surface_diagnostics_markdown_smoke() -> None:
    result = runner.invoke(
        app,
        ["diagnostics", "prompt-surface", "--top", "2", "--no-runtime-projections", "--format", "markdown"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    normalized_output = result.output.lower()
    assert "prompt" in normalized_output
    assert "surface" in normalized_output
    assert "invalid `gpd_return` examples" in normalized_output
    assert ".md" in result.output


def test_prompt_surface_diagnostics_table_runtime_top_prompts_smoke() -> None:
    runtime_name = _non_native_runtime_name()
    result = runner.invoke(
        app,
        ["diagnostics", "prompt-surface", "--top", "1", "--surface", "command", "--runtime", runtime_name],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    assert "runtime top prompts" in result.output
    assert "projected_chars" in result.output
    assert "expanded_chars" in result.output
    assert "shell_rewrites" in result.output
    assert runtime_name in result.output


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
