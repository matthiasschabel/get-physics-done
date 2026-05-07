"""CLI coverage for prompt-surface diagnostics."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from gpd.cli import app


class _StableCliRunner(CliRunner):
    def invoke(self, *args, **kwargs):
        kwargs.setdefault("color", False)
        return super().invoke(*args, **kwargs)


runner = _StableCliRunner()


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
        assert isinstance(item["hard_gate_line_count"], int)
        assert isinstance(item["hard_gate_density"], int | float)
        assert isinstance(item["shell_fence_count"], int)
        assert isinstance(item["shell_parsing_line_count"], int)
        assert isinstance(item["rigidity_index"], int)
        assert item["runtime_projection"] == []


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
    assert ".md" in result.output


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
