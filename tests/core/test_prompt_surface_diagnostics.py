"""Focused coverage for the prompt surface diagnostics production API."""

from __future__ import annotations

import ast
import importlib
import textwrap
from pathlib import Path

from gpd import registry
from gpd.adapters.runtime_catalog import iter_runtime_descriptors

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPT_DIAGNOSTICS_PATH = REPO_ROOT / "src" / "gpd" / "core" / "prompt_diagnostics.py"
EXPECTED_REPORT_KEYS = {
    "schema_version",
    "repo_root",
    "totals",
    "items",
    "invalid_gpd_return_examples",
    "duplicate_invariants",
    "exact_prose_assertion_files",
    "warnings",
}
EXPECTED_ITEM_KEYS = {
    "kind",
    "name",
    "path",
    "raw_line_count",
    "raw_char_count",
    "raw_include_count",
    "expanded_line_count",
    "expanded_char_count",
    "expanded_include_count",
    "unresolved_include_count",
    "visible_schema_example_count",
    "invalid_gpd_return_example_count",
    "invalid_gpd_return_examples",
    "hard_gate_line_count",
    "hard_gate_density",
    "shell_fence_count",
    "shell_parsing_line_count",
    "rigidity_index",
    "runtime_projection",
}
EXPECTED_RUNTIME_PROJECTION_KEYS = {
    "runtime",
    "native_include_support",
    "line_count",
    "char_count",
    "include_count",
    "runtime_note_count",
    "runtime_note_chars",
    "shell_fence_count",
    "bridge_command_occurrences",
}
EXPECTED_DUPLICATE_GROUP_KEYS = {
    "phrase",
    "occurrence_count",
    "file_count",
    "severity",
    "locations",
}
EXPECTED_INVALID_RETURN_EXAMPLE_KEYS = {
    "path",
    "start_line",
    "end_line",
    "errors",
    "preview",
}


def _diagnostics():
    return importlib.import_module("gpd.core.prompt_diagnostics")


def _write(root: Path, relative_path: str, content: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    return path


def _report(
    repo_root: Path,
    *,
    surfaces: tuple[str, ...] = ("command", "agent", "workflow"),
    runtime_names: tuple[str, ...] = (),
):
    diagnostics = _diagnostics()
    return diagnostics.build_prompt_surface_report(
        repo_root,
        surfaces=surfaces,
        runtime_names=runtime_names,
        include_tests=False,
        top=10_000,
    )


def _source(repo_root: Path, kind: str, name: str):
    diagnostics = _diagnostics()
    sources = tuple(diagnostics.iter_prompt_sources(repo_root, surfaces=(kind,)))
    for source in sources:
        source_path = Path(source.path)
        if source.name == name or source_path.stem == name:
            return source
    available = sorted(source.name for source in sources)
    raise AssertionError(f"missing {kind} source {name!r}; available={available}")


def _measure(
    repo_root: Path,
    kind: str,
    name: str,
    *,
    runtime_names: tuple[str, ...] = (),
    include_runtime_projections: bool = False,
):
    diagnostics = _diagnostics()
    return diagnostics.measure_prompt_file(
        _source(repo_root, kind, name),
        runtime_names=runtime_names,
        include_runtime_projections=include_runtime_projections,
    )


def _relative_report_path(raw_path: str) -> str:
    path = Path(raw_path)
    if path.is_absolute():
        return path.relative_to(REPO_ROOT).as_posix()
    return path.as_posix()


def test_report_includes_every_command_agent_and_workflow_source() -> None:
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


def test_report_to_dict_has_stable_schema_version_and_json_shape(tmp_path: Path) -> None:
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
    diagnostics = _diagnostics()
    report = _report(tmp_path, surfaces=("command",), runtime_names=())

    payload = diagnostics.report_to_dict(report)

    assert set(payload) == EXPECTED_REPORT_KEYS
    assert payload["schema_version"] == report.schema_version
    assert isinstance(payload["schema_version"], str)
    assert payload["schema_version"]
    assert isinstance(payload["items"], list)
    assert len(payload["items"]) == 1
    assert set(payload["items"][0]) == EXPECTED_ITEM_KEYS
    assert payload["items"][0]["runtime_projection"] == []
    assert payload["items"][0]["invalid_gpd_return_examples"] == []
    assert payload["invalid_gpd_return_examples"] == []


def test_include_counting_ignores_fenced_code_and_uses_installer_expansion(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/commands/include-probe.md",
        """
        ---
        name: gpd:include-probe
        description: Include probe
        ---
        @{GPD_INSTALL_DIR}/templates/shared.md

        ```text
        @{GPD_INSTALL_DIR}/templates/not-a-real-include.md
        ```
        """,
    )
    _write(
        tmp_path,
        "src/gpd/specs/templates/shared.md",
        """
        ---
        description: Included frontmatter should be stripped.
        ---
        Included body line.
        """,
    )

    item = _measure(tmp_path, "command", "include-probe")

    assert item.raw_include_count == 1
    assert item.expanded_include_count == 1
    assert item.unresolved_include_count == 0
    assert item.expanded_char_count > item.raw_char_count


def test_visible_schema_example_count_excludes_yaml_frontmatter(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/commands/schema-probe.md",
        """
        ---
        name: gpd:schema-probe
        description: Schema probe
        schema_version: 1
        ---
        The frontmatter schema_version above is metadata, not a visible schema example.

        ```yaml
        schema_version: 1
        contract_results: []
        ```
        """,
    )

    item = _measure(tmp_path, "command", "schema-probe")

    assert item.visible_schema_example_count == 1


def test_duplicate_invariant_grouping_normalizes_whitespace_and_case(tmp_path: Path) -> None:
    invariant = "Use only status names: completed | checkpoint | blocked | failed when returning gpd_return status."
    _write(
        tmp_path,
        "src/gpd/commands/alpha.md",
        f"""
        ---
        name: gpd:alpha
        description: Alpha
        ---
        {invariant}
        """,
    )
    _write(
        tmp_path,
        "src/gpd/commands/beta.md",
        """
        ---
        name: gpd:beta
        description: Beta
        ---
        use   only status names: completed | checkpoint | blocked | failed when returning gpd_return status.
        """,
    )
    _write(
        tmp_path,
        "src/gpd/specs/workflows/gamma.md",
        """
        ---
        name: gamma
        ---
        USE ONLY STATUS NAMES: COMPLETED | CHECKPOINT | BLOCKED | FAILED WHEN RETURNING GPD_RETURN STATUS.
        """,
    )

    report = _report(tmp_path, runtime_names=())
    matching_groups = [
        group for group in report.duplicate_invariants if "use only status names" in group.phrase.lower()
    ]

    assert len(matching_groups) == 1
    group = matching_groups[0]
    assert group.occurrence_count == 3
    assert group.file_count == 3
    assert group.severity == "warn"
    assert len(group.locations) == 3


def test_invalid_partial_gpd_return_examples_are_reported(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/agents/gpd-return-probe.md",
        """
        ---
        name: gpd-return-probe
        description: Return probe
        tools: []
        ---
        ```yaml
        gpd_return:
          status: completed
          summary: This partial example omits the required files_written list.
        ```
        """,
    )

    item = _measure(tmp_path, "agent", "gpd-return-probe")

    assert item.visible_schema_example_count == 1
    assert item.invalid_gpd_return_example_count == 1
    assert len(item.invalid_gpd_return_examples) == 1
    example = item.invalid_gpd_return_examples[0]
    assert example.path == "src/gpd/agents/gpd-return-probe.md"
    assert example.start_line == 6
    assert example.end_line == 10
    assert "Missing required field: files_written" in example.errors
    assert "Missing required field: issues" in example.errors
    assert "Missing required field: next_actions" in example.errors
    assert example.preview.startswith("gpd_return: status: completed")


def test_invalid_json_gpd_return_examples_are_reported_as_invalid(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/specs/workflows/json-return-probe.md",
        """
        ---
        name: json-return-probe
        ---
        ```json
        {"gpd_return":{"files_written":["GPD/plan.md"]}}
        ```
        """,
    )

    item = _measure(tmp_path, "workflow", "json-return-probe")

    assert item.visible_schema_example_count == 1
    assert item.invalid_gpd_return_example_count == 1
    example = item.invalid_gpd_return_examples[0]
    assert example.start_line == 4
    assert example.end_line == 6
    assert example.errors == ("No gpd_return YAML block found",)
    assert '"gpd_return"' in example.preview


def test_shell_blocks_that_construct_returns_are_not_schema_examples(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/specs/workflows/shell-return-probe.md",
        """
        ---
        name: shell-return-probe
        ---
        ```bash
        printf '```yaml\\n'
        printf 'gpd_return:\\n'
        printf '  status: completed\\n'
        printf '  files_written: []\\n'
        printf '  issues: []\\n'
        printf '  next_actions: []\\n'
        printf '```\\n'
        ```
        """,
    )

    item = _measure(tmp_path, "workflow", "shell-return-probe")

    assert item.visible_schema_example_count == 0
    assert item.invalid_gpd_return_example_count == 0
    assert item.invalid_gpd_return_examples == ()


def test_runtime_projections_cover_every_runtime_descriptor(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/commands/runtime-probe.md",
        """
        ---
        name: gpd:runtime-probe
        description: Runtime probe
        ---
        @{GPD_INSTALL_DIR}/templates/runtime-shared.md
        """,
    )
    _write(tmp_path, "src/gpd/specs/templates/runtime-shared.md", "Shared runtime include.\n")

    descriptors = tuple(iter_runtime_descriptors())
    runtime_names = tuple(descriptor.runtime_name for descriptor in descriptors)
    item = _measure(
        tmp_path,
        "command",
        "runtime-probe",
        runtime_names=runtime_names,
        include_runtime_projections=True,
    )

    projections_by_runtime = {metric.runtime: metric for metric in item.runtime_projection}

    assert set(projections_by_runtime) == set(runtime_names)
    for descriptor in descriptors:
        metric = projections_by_runtime[descriptor.runtime_name]
        assert metric.native_include_support is descriptor.native_include_support
        assert metric.line_count > 0
        assert metric.char_count > 0

    native_include_runtimes = tuple(descriptor.runtime_name for descriptor in descriptors if descriptor.native_include_support)
    non_native_include_runtimes = tuple(
        descriptor.runtime_name for descriptor in descriptors if not descriptor.native_include_support
    )

    assert native_include_runtimes
    assert non_native_include_runtimes
    assert all(projections_by_runtime[runtime].native_include_support is True for runtime in native_include_runtimes)
    assert all(projections_by_runtime[runtime].native_include_support is False for runtime in non_native_include_runtimes)


def test_report_to_dict_serializes_runtime_and_duplicate_group_shapes(tmp_path: Path) -> None:
    invariant = "Use only status names: completed | checkpoint | blocked | failed when returning gpd_return status."
    for name in ("one", "two", "three"):
        _write(
            tmp_path,
            f"src/gpd/commands/{name}.md",
            f"""
            ---
            name: gpd:{name}
            description: {name}
            ---
            {invariant}
            """,
        )

    diagnostics = _diagnostics()
    runtime_name = next(descriptor.runtime_name for descriptor in iter_runtime_descriptors())
    report = _report(tmp_path, surfaces=("command",), runtime_names=(runtime_name,))
    payload = diagnostics.report_to_dict(report)

    assert set(payload["items"][0]["runtime_projection"][0]) == EXPECTED_RUNTIME_PROJECTION_KEYS
    assert payload["items"][0]["runtime_projection"][0]["runtime"] == runtime_name
    assert payload["duplicate_invariants"]
    assert set(payload["duplicate_invariants"][0]) == EXPECTED_DUPLICATE_GROUP_KEYS


def test_report_to_dict_serializes_invalid_gpd_return_example_shape(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/agents/return-shape-probe.md",
        """
        ---
        name: return-shape-probe
        description: Return shape probe
        ---
        ```yaml
        gpd_return:
          status: completed
        ```
        """,
    )

    diagnostics = _diagnostics()
    report = _report(tmp_path, surfaces=("agent",), runtime_names=())
    payload = diagnostics.report_to_dict(report)
    item_example = payload["items"][0]["invalid_gpd_return_examples"][0]
    report_example = payload["invalid_gpd_return_examples"][0]

    assert item_example == report_example
    assert set(report_example) == EXPECTED_INVALID_RETURN_EXAMPLE_KEYS
    assert report_example["path"] == "src/gpd/agents/return-shape-probe.md"
    assert report_example["start_line"] == 5
    assert report_example["end_line"] == 8
    assert report_example["errors"]
    assert report_example["preview"].startswith("gpd_return:")


def test_markdown_render_lists_invalid_gpd_return_examples(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/agents/return-markdown-probe.md",
        """
        ---
        name: return-markdown-probe
        description: Return markdown probe
        ---
        ```yaml
        gpd_return:
          status: completed
        ```
        """,
    )

    diagnostics = _diagnostics()
    report = _report(tmp_path, surfaces=("agent",), runtime_names=())
    markdown = diagnostics.render_prompt_surface_markdown(report)

    assert "## Invalid `gpd_return` Examples" in markdown
    assert "`src/gpd/agents/return-markdown-probe.md`" in markdown
    assert "5-8" in markdown
    assert "Missing required field: files_written" in markdown


def test_production_prompt_diagnostics_does_not_import_from_tests() -> None:
    assert PROMPT_DIAGNOSTICS_PATH.exists()
    tree = ast.parse(PROMPT_DIAGNOSTICS_PATH.read_text(encoding="utf-8"))

    forbidden_imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            forbidden_imports.extend(
                alias.name for alias in node.names if alias.name == "tests" or alias.name.startswith("tests.")
            )
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "tests" or node.module.startswith("tests."):
                forbidden_imports.append(node.module)

    assert forbidden_imports == []
