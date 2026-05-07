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
    "runtime_top_prompts",
    "stage_diagnostics",
    "invalid_gpd_return_examples",
    "disallowed_return_field_mentions",
    "duplicate_invariants",
    "semantic_duplicate_invariants",
    "exact_assertion_diagnostics",
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
    "return_field_mention_count",
    "disallowed_return_field_mention_count",
    "disallowed_return_field_mentions",
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
    "expanded_line_count",
    "expanded_char_count",
    "line_count",
    "char_count",
    "line_delta",
    "char_delta",
    "char_delta_percent",
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
    "line_delta",
    "char_delta",
    "char_delta_percent",
    "include_count",
    "runtime_note_count",
    "runtime_note_chars",
    "shell_rewrite_count",
}
EXPECTED_DUPLICATE_GROUP_KEYS = {
    "phrase",
    "occurrence_count",
    "file_count",
    "severity",
    "locations",
}
EXPECTED_SEMANTIC_DUPLICATE_GROUP_KEYS = {
    "category",
    "label",
    "occurrence_count",
    "file_count",
    "non_reference_file_count",
    "severity",
    "canonical_references",
    "suggested_action",
    "examples",
}
EXPECTED_SEMANTIC_DUPLICATE_EXAMPLE_KEYS = {
    "path",
    "line",
    "category",
    "snippet",
    "matched_terms",
    "is_reference_or_template",
}
EXPECTED_INVALID_RETURN_EXAMPLE_KEYS = {
    "path",
    "start_line",
    "end_line",
    "errors",
    "preview",
}
EXPECTED_RETURN_FIELD_MENTION_KEYS = {
    "path",
    "line",
    "field",
    "mention_kind",
    "polarity",
    "allowed",
    "allowed_source",
    "severity",
    "snippet",
    "suggestion",
}
EXPECTED_STAGE_DIAGNOSTIC_KEYS = {
    "workflow_id",
    "command_name",
    "command_path",
    "manifest_path",
    "stage_count",
    "first_turn_line_count",
    "first_turn_char_count",
    "first_turn_raw_include_count",
    "runtime_projection",
    "stages",
    "violation_count",
    "warnings",
}
EXPECTED_STAGE_KEYS = {
    "workflow_id",
    "stage_id",
    "order",
    "eager_authorities",
    "eager_authority_metrics",
    "eager_line_count",
    "eager_char_count",
    "lazy_authorities",
    "lazy_authority_metrics",
    "lazy_line_count",
    "lazy_char_count",
    "must_not_eager_load_violations",
}
EXPECTED_AUTHORITY_KEYS = {
    "authority",
    "path",
    "raw_line_count",
    "raw_char_count",
    "raw_include_count",
    "expanded_line_count",
    "expanded_char_count",
    "transitive_include_authorities",
}
EXPECTED_VIOLATION_KEYS = {
    "workflow_id",
    "stage_id",
    "authority",
    "violation_source",
    "eager_via",
}
EXPECTED_EXACT_ASSERTION_TOTAL_KEYS = {
    "files_scanned",
    "exact_assertion_file_count",
    "exact_assertion_count",
    "machine_contract_exact_assertions",
    "public_ux_exact_assertions",
    "brittle_prose_assertions",
    "brittle_prose_file_count",
}
EXPECTED_EXACT_ASSERTION_FILE_KEYS = {
    "path",
    "exact_assertion_count",
    "machine_contract_exact_assertions",
    "public_ux_exact_assertions",
    "brittle_prose_assertions",
    "brittle_prose_density",
    "severity",
    "examples",
}
EXPECTED_EXACT_ASSERTION_EXAMPLE_KEYS = {
    "path",
    "line",
    "literal",
    "assertion_shape",
    "polarity",
    "category",
    "reason",
}


def _diagnostics():
    return importlib.import_module("gpd.core.prompt_diagnostics")


def _non_native_runtime_name() -> str:
    return next(descriptor.runtime_name for descriptor in iter_runtime_descriptors() if not descriptor.native_include_support)


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
    assert payload["runtime_top_prompts"] == {}
    assert payload["stage_diagnostics"] == []
    assert payload["items"][0]["invalid_gpd_return_examples"] == []
    assert payload["invalid_gpd_return_examples"] == []
    assert payload["items"][0]["disallowed_return_field_mentions"] == []
    assert payload["disallowed_return_field_mentions"] == []
    assert payload["semantic_duplicate_invariants"] == []
    exact_diagnostics = payload["exact_assertion_diagnostics"]
    assert isinstance(exact_diagnostics, dict)
    assert exact_diagnostics["schema_version"] == "exact_assertions.v1"
    assert set(exact_diagnostics["totals"]) == EXPECTED_EXACT_ASSERTION_TOTAL_KEYS
    assert exact_diagnostics["totals"]["exact_assertion_count"] == 0
    assert exact_diagnostics["files"] == []


def test_stage_diagnostics_measure_staged_commands_and_transitive_lazy_violations(tmp_path: Path) -> None:
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
    _write(
        tmp_path,
        "src/gpd/specs/templates/deferred.md",
        """
        Deferred authority body.
        """,
    )
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
                {
                  "when": "need_deferred",
                  "authorities": ["templates/deferred.md"]
                }
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

    diagnostics = _diagnostics()
    report = _report(tmp_path, surfaces=("command",), runtime_names=(runtime_name,))
    payload = diagnostics.report_to_dict(report)

    command_item = payload["items"][0]
    stage_diagnostic = payload["stage_diagnostics"][0]
    assert set(stage_diagnostic) == EXPECTED_STAGE_DIAGNOSTIC_KEYS
    assert stage_diagnostic["workflow_id"] == "probe"
    assert stage_diagnostic["command_name"] == "probe"
    assert stage_diagnostic["first_turn_char_count"] == command_item["expanded_char_count"]
    assert stage_diagnostic["first_turn_line_count"] == command_item["expanded_line_count"]
    assert len(stage_diagnostic["runtime_projection"]) == 1
    assert set(stage_diagnostic["runtime_projection"][0]) == EXPECTED_RUNTIME_PROJECTION_KEYS

    stage = stage_diagnostic["stages"][0]
    assert set(stage) == EXPECTED_STAGE_KEYS
    assert stage["stage_id"] == "bootstrap"
    assert stage["eager_authorities"] == ["workflows/probe.md"]
    assert stage["lazy_authorities"] == ["templates/deferred.md"]
    assert len(stage["eager_authority_metrics"]) == 1
    assert set(stage["eager_authority_metrics"][0]) == EXPECTED_AUTHORITY_KEYS
    assert set(stage["lazy_authority_metrics"][0]) == EXPECTED_AUTHORITY_KEYS
    assert "templates/deferred.md" in stage["eager_authority_metrics"][0]["transitive_include_authorities"]

    violations = stage["must_not_eager_load_violations"]
    assert all(set(violation) == EXPECTED_VIOLATION_KEYS for violation in violations)
    violation_sources = {violation["violation_source"] for violation in violations}
    assert "first_turn_transitive_include" in violation_sources
    assert "stage_eager_transitive_include" in violation_sources
    assert "conditional_eager_overlap" not in violation_sources
    first_turn_violation = next(
        violation for violation in violations if violation["violation_source"] == "first_turn_transitive_include"
    )
    assert "workflows/probe.md" in first_turn_violation["eager_via"]
    assert stage_diagnostic["violation_count"] == len(violations)


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


def test_semantic_duplicate_invariants_group_paraphrased_categories(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/commands/alpha.md",
        """
        ---
        name: gpd:alpha
        description: Alpha
        ---
        When routing, read gpd_return.status; the valid runtime choices remain completed, checkpoint, blocked, and failed.
        A checkpoint handoff stops after asking the user and the orchestrator starts a fresh continuation instead of letting that same spawned run continue.
        Reject a phase artifact that already existed before this run; runtime completion text cannot prove success by itself.
        Treat the report as fresh only when the expected path appears in gpd_return.files_written and is readable on disk.
        Human-readable headings and success prose are presentation only; route on the structured status, not labels.
        Do not fabricate a child gpd_return when the checker omits its return envelope; retry the child instead.
        """,
    )
    _write(
        tmp_path,
        "src/gpd/specs/workflows/beta.md",
        """
        ---
        name: beta
        ---
        Consume the typed status from gpd_return.status and use only completed | checkpoint | blocked | failed.
        For checkpoint user input, present the checkpoint and spawn a fresh continuation rather than resuming in place.
        Preexisting files are stale evidence for this handoff; do not infer completion from files alone.
        The artifact gate passes only when gpd_return.files_written names the same path that now exists.
        Route on gpd_return.status, not headings or marker strings that merely look successful.
        Never paste a synthetic gpd_return for a verifier child; a malformed return envelope is incomplete.
        """,
    )

    report = _report(tmp_path, runtime_names=())
    groups_by_category = {group.category: group for group in report.semantic_duplicate_invariants}

    assert set(groups_by_category) == {
        "status_handling",
        "fresh_continuation",
        "stale_artifact_rejection",
        "files_written_freshness",
        "heading_prose_non_authority",
        "no_synthesized_child_gpd_return",
    }
    assert groups_by_category["no_synthesized_child_gpd_return"].severity == "high"
    assert all(group.occurrence_count >= 2 for group in groups_by_category.values())
    assert all(group.non_reference_file_count == 2 for group in groups_by_category.values())
    assert all(group.examples for group in groups_by_category.values())

    matching_exact_groups = [
        group
        for group in report.duplicate_invariants
        if "fresh continuation" in group.phrase or "files_written" in group.phrase
    ]
    assert matching_exact_groups == []


def test_semantic_duplicate_invariants_ignore_frontmatter_and_fenced_code(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/commands/fenced-only.md",
        """
        ---
        name: gpd:fenced-only
        description: gpd_return.status completed checkpoint blocked failed in metadata
        ---
        ```text
        Route on gpd_return.status and use completed | checkpoint | blocked | failed.
        Do not fabricate a child gpd_return from this fenced example.
        ```
        """,
    )

    report = _report(tmp_path, runtime_names=())

    assert report.semantic_duplicate_invariants == ()


def test_semantic_duplicate_invariants_avoid_common_false_positives(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/specs/workflows/false-positive-probe.md",
        """
        ---
        name: false-positive-probe
        ---
        Record verification_status: passed | gaps_found | expert_needed | human_needed for scientific review.
        The research synthesizer can synthesize literature summaries without touching any return envelope.
        A main-context fallback owns its own gpd_return and does not patch a child envelope.
        Numerical artifacts may appear in plots, but that does not describe handoff freshness.
        """,
    )

    report = _report(tmp_path, runtime_names=())

    assert report.semantic_duplicate_invariants == ()


def test_semantic_duplicate_invariants_reference_only_occurrences_are_info(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/specs/references/orchestration/child-artifact-gate.md",
        """
        The artifact gate passes only when gpd_return.files_written names the expected path and it exists on disk.
        """,
    )

    report = _report(tmp_path, runtime_names=())

    assert len(report.semantic_duplicate_invariants) == 1
    group = report.semantic_duplicate_invariants[0]
    assert group.category == "files_written_freshness"
    assert group.severity == "info"
    assert group.non_reference_file_count == 0
    assert group.examples[0].is_reference_or_template is True


def test_exact_assertion_diagnostics_split_machine_public_ux_and_brittle_prose(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/commands/probe.md",
        """
        ---
        name: gpd:probe
        description: Probe
        ---
        Probe body.
        """,
    )
    _write(
        tmp_path,
        "tests/core/test_prompt_contracts.py",
        '''
        def test_machine_contracts(prompt):
            assert "gpd --raw init new-project --stage post_scope" in prompt
            assert "templates/project-contract-schema.md" in prompt
            assert "project_contract.claims[]" in prompt
            assert "must_haves" not in prompt
            assert '<step name="load_gap_repair_stage">' in prompt
            assert "schema_version: 1" in prompt
            assert "--mode approved" in prompt
        ''',
    )
    _write(
        tmp_path,
        "tests/core/test_cli.py",
        '''
        def test_public_ux(output):
            assert "## Command Index" in output
            assert "Quick Start" in output
            assert "## Choose this runtime if" in output
            assert "[Y/n/e]" in output
            assert "Start a fresh context window, then run `{next command}`." in output
        ''',
    )
    _write(
        tmp_path,
        "tests/core/test_prompt_prose.py",
        '''
        def test_brittle_prompt_prose(prompt):
            assert "The planner returns proposed roadmap edits for the next execution segment." in prompt
            prompt.count("Do not approve a scoping contract that strips decisive outputs from the project brief.")
            prompt.index("The worker should preserve the surrounding prose when updating this workflow section.")
        ''',
    )

    diagnostics = _diagnostics()
    report = diagnostics.build_prompt_surface_report(
        tmp_path,
        surfaces=("command",),
        runtime_names=(),
        include_tests=True,
        include_runtime_projections=False,
    )
    payload = diagnostics.report_to_dict(report)
    exact = payload["exact_assertion_diagnostics"]
    totals = exact["totals"]

    assert set(totals) == EXPECTED_EXACT_ASSERTION_TOTAL_KEYS
    assert totals["files_scanned"] == 3
    assert totals["exact_assertion_count"] == 15
    assert totals["machine_contract_exact_assertions"] == 7
    assert totals["public_ux_exact_assertions"] == 5
    assert totals["brittle_prose_assertions"] == 3
    assert totals["brittle_prose_file_count"] == 1

    files_by_path = {entry["path"]: entry for entry in exact["files"]}
    assert set(files_by_path) == {
        "tests/core/test_cli.py",
        "tests/core/test_prompt_contracts.py",
        "tests/core/test_prompt_prose.py",
    }
    for entry in files_by_path.values():
        assert set(entry) == EXPECTED_EXACT_ASSERTION_FILE_KEYS

    prose_entry = files_by_path["tests/core/test_prompt_prose.py"]
    assert prose_entry["brittle_prose_assertions"] == 3
    assert prose_entry["machine_contract_exact_assertions"] == 0
    assert prose_entry["public_ux_exact_assertions"] == 0
    assert prose_entry["brittle_prose_density"] == 1.0
    assert prose_entry["severity"] == "info"
    brittle_examples = prose_entry["examples"]["brittle_prose"]
    assert {example["assertion_shape"] for example in brittle_examples} == {
        "assert_contains",
        "count",
        "index",
    }
    assert all(set(example) == EXPECTED_EXACT_ASSERTION_EXAMPLE_KEYS for example in brittle_examples)
    assert all(example["category"] == "brittle_prose" for example in brittle_examples)

    machine_examples = files_by_path["tests/core/test_prompt_contracts.py"]["examples"]["machine_contract"]
    assert {example["reason"] for example in machine_examples} >= {
        "gpd_command_or_flag",
        "path_or_artifact",
        "schema_or_field_path",
    }
    assert any(example["polarity"] == "forbidden" for example in machine_examples)

    public_entry = files_by_path["tests/core/test_cli.py"]
    assert public_entry["public_ux_exact_assertions"] == 5
    assert public_entry["examples"]["public_ux"][0]["reason"] == "public_ux_copy"

    compatibility = {entry["path"]: entry for entry in payload["exact_prose_assertion_files"]}
    assert compatibility["tests/core/test_prompt_contracts.py"]["machine_contract_assertions"] == 7
    assert compatibility["tests/core/test_cli.py"]["prose_contract_assertions"] == 5
    assert compatibility["tests/core/test_prompt_prose.py"]["brittle_prose_assertions"] == 3

    markdown = diagnostics.render_prompt_surface_markdown(report, top=3)
    table = diagnostics.render_prompt_surface_table(report, top=3)
    assert "## Prompt-Test Exactness" in markdown
    assert "Thresholds: brittle prose warn" in markdown
    assert "| File | Exact | Machine | Public UX | Brittle prose | Brittle % | Severity |" in markdown
    assert "prompt-test exactness" in table
    assert "public_ux" in table
    assert "brittle_pct" in table


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


def test_disallowed_direct_gpd_return_field_mentions_are_reported(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/commands/direct-return-field-probe.md",
        """
        ---
        name: gpd:direct-return-field-probe
        description: Direct return field probe
        ---
        Route on gpd_return.file_written after the handoff.
        """,
    )

    report = _report(tmp_path, surfaces=("command",), runtime_names=())
    item = report.items[0]
    mention = report.disallowed_return_field_mentions[0]

    assert item.return_field_mention_count == 1
    assert item.disallowed_return_field_mention_count == 1
    assert item.disallowed_return_field_mentions == report.disallowed_return_field_mentions
    assert mention.path == "src/gpd/commands/direct-return-field-probe.md"
    assert mention.field == "file_written"
    assert mention.mention_kind == "direct_reference"
    assert mention.polarity == "positive"
    assert mention.allowed is False
    assert mention.allowed_source == "unknown"
    assert mention.severity == "error"
    assert mention.suggestion == "files_written"


def test_disallowed_extended_field_list_mentions_are_reported(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/agents/extended-return-field-probe.md",
        """
        ---
        name: extended-return-field-probe
        description: Extended return field probe
        ---
        Return extended fields: `verification_status`, `mystery_metric`.
        """,
    )

    report = _report(tmp_path, surfaces=("agent",), runtime_names=())

    assert report.totals["return_field_mention_count"] == 2
    assert report.totals["allowed_return_field_mention_count"] == 1
    assert len(report.disallowed_return_field_mentions) == 1
    mention = report.disallowed_return_field_mentions[0]
    assert mention.field == "mystery_metric"
    assert mention.mention_kind == "extended_field_list"


def test_disallowed_yaml_example_key_reports_field_specific_diagnostic(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/specs/workflows/yaml-return-field-probe.md",
        """
        ---
        name: yaml-return-field-probe
        ---
        ```yaml
        gpd_return:
          status: completed
          file_written:
            - GPD/output.md
          issues: []
          next_actions: []
        ```
        """,
    )

    report = _report(tmp_path, surfaces=("workflow",), runtime_names=())
    item = report.items[0]
    mention = report.disallowed_return_field_mentions[0]

    assert item.invalid_gpd_return_example_count == 1
    assert report.invalid_gpd_return_examples
    assert item.disallowed_return_field_mention_count == 1
    assert mention.field == "file_written"
    assert mention.mention_kind == "yaml_example_key"
    assert mention.suggestion == "files_written"


def test_negative_disallowed_return_field_guardrail_does_not_fail_diagnostic(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/specs/workflows/negative-return-field-probe.md",
        """
        ---
        name: negative-return-field-probe
        ---
        Do not use gpd_return.execution_segment; use continuation_update.bounded_segment instead.
        """,
    )

    report = _report(tmp_path, surfaces=("workflow",), runtime_names=())

    assert report.disallowed_return_field_mentions == ()
    assert report.totals["disallowed_return_field_mention_count"] == 0
    assert report.totals["negative_return_field_mention_count"] == 1
    mention = report.return_field_mentions[0]
    assert mention.field == "execution_segment"
    assert mention.polarity == "negative"
    assert mention.severity == "info"


def test_nested_continuation_fields_are_not_treated_as_top_level_return_fields(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/specs/workflows/nested-continuation-probe.md",
        """
        ---
        name: nested-continuation-probe
        ---
        Persist continuation_update.bounded_segment.resume_file when the checkpoint is durable.
        """,
    )

    report = _report(tmp_path, surfaces=("workflow",), runtime_names=())

    assert report.return_field_mentions == ()
    assert report.disallowed_return_field_mentions == ()


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
    _write(tmp_path, "src/gpd/specs/templates/runtime-shared.md", "Shared runtime include.\n" * 80)

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
        assert metric.expanded_line_count == item.expanded_line_count
        assert metric.expanded_char_count == item.expanded_char_count
        assert metric.line_count > 0
        assert metric.char_count > 0
        assert metric.shell_rewrite_count == 0

    native_include_runtimes = tuple(
        descriptor.runtime_name for descriptor in descriptors if descriptor.native_include_support
    )
    non_native_include_runtimes = tuple(
        descriptor.runtime_name for descriptor in descriptors if not descriptor.native_include_support
    )

    assert native_include_runtimes
    assert non_native_include_runtimes
    assert all(projections_by_runtime[runtime].native_include_support is True for runtime in native_include_runtimes)
    assert all(projections_by_runtime[runtime].native_include_support is False for runtime in non_native_include_runtimes)
    assert all(projections_by_runtime[runtime].include_count == 1 for runtime in native_include_runtimes)
    assert all(projections_by_runtime[runtime].include_count == 0 for runtime in non_native_include_runtimes)


def test_runtime_projection_shell_rewrite_count_uses_projected_shell_fences_only(tmp_path: Path) -> None:
    runtime_name = _non_native_runtime_name()
    _write(
        tmp_path,
        "src/gpd/commands/shell-rewrite-probe.md",
        """
        ---
        name: gpd:shell-rewrite-probe
        description: Shell rewrite probe
        ---
        The runtime note may mention the bridge, but prose must not count as a shell rewrite.

        ```bash
        gpd hidden-probe
        gpd hidden-probe --json
        ```
        """,
    )
    _write(
        tmp_path,
        "src/gpd/commands/no-shell-rewrite-probe.md",
        """
        ---
        name: gpd:no-shell-rewrite-probe
        description: No shell rewrite probe
        ---
        This command has no runnable shell fence.
        """,
    )

    shell_item = _measure(
        tmp_path,
        "command",
        "shell-rewrite-probe",
        runtime_names=(runtime_name,),
        include_runtime_projections=True,
    )
    no_shell_item = _measure(
        tmp_path,
        "command",
        "no-shell-rewrite-probe",
        runtime_names=(runtime_name,),
        include_runtime_projections=True,
    )

    shell_metric = shell_item.runtime_projection[0]
    no_shell_metric = no_shell_item.runtime_projection[0]

    assert shell_metric.shell_fence_count == 1
    assert shell_metric.shell_rewrite_count == 1
    assert shell_metric.bridge_command_occurrences > shell_metric.shell_rewrite_count
    assert no_shell_metric.shell_fence_count == 0
    assert no_shell_metric.shell_rewrite_count == 0
    assert no_shell_metric.bridge_command_occurrences > 0


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
    runtime_top_prompts = payload["runtime_top_prompts"]
    assert isinstance(runtime_top_prompts, dict)
    assert set(runtime_top_prompts) == {runtime_name}
    runtime_rows = runtime_top_prompts[runtime_name]
    assert isinstance(runtime_rows, list)
    assert len(runtime_rows) == 3
    assert set(runtime_rows[0]) == EXPECTED_RUNTIME_TOP_PROMPT_KEYS
    assert runtime_rows[0]["runtime"] == runtime_name
    assert runtime_rows[0]["projected_char_count"] >= runtime_rows[-1]["projected_char_count"]
    assert payload["duplicate_invariants"]
    assert set(payload["duplicate_invariants"][0]) == EXPECTED_DUPLICATE_GROUP_KEYS
    assert payload["semantic_duplicate_invariants"]
    semantic_group = payload["semantic_duplicate_invariants"][0]
    assert set(semantic_group) == EXPECTED_SEMANTIC_DUPLICATE_GROUP_KEYS
    assert set(semantic_group["examples"][0]) == EXPECTED_SEMANTIC_DUPLICATE_EXAMPLE_KEYS


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


def test_report_to_dict_serializes_disallowed_return_field_mention_shape(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/commands/return-field-shape-probe.md",
        """
        ---
        name: gpd:return-field-shape-probe
        description: Return field shape probe
        ---
        Route on gpd_return.file_written after the handoff.
        """,
    )

    diagnostics = _diagnostics()
    report = _report(tmp_path, surfaces=("command",), runtime_names=())
    payload = diagnostics.report_to_dict(report)
    item_mention = payload["items"][0]["disallowed_return_field_mentions"][0]
    report_mention = payload["disallowed_return_field_mentions"][0]

    assert item_mention == report_mention
    assert set(report_mention) == EXPECTED_RETURN_FIELD_MENTION_KEYS
    assert report_mention["path"] == "src/gpd/commands/return-field-shape-probe.md"
    assert report_mention["field"] == "file_written"
    assert report_mention["mention_kind"] == "direct_reference"
    assert report_mention["severity"] == "error"
    assert report_mention["suggestion"] == "files_written"


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


def test_markdown_render_lists_disallowed_return_field_mentions(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/commands/return-field-markdown-probe.md",
        """
        ---
        name: gpd:return-field-markdown-probe
        description: Return field markdown probe
        ---
        Route on gpd_return.file_written after the handoff.
        """,
    )

    diagnostics = _diagnostics()
    report = _report(tmp_path, surfaces=("command",), runtime_names=())
    markdown = diagnostics.render_prompt_surface_markdown(report)
    table = diagnostics.render_prompt_surface_table(report)

    assert "Disallowed `gpd_return` field mentions: 1" in markdown
    assert "## Disallowed `gpd_return` Field Mentions" in markdown
    assert "`file_written`" in markdown
    assert "files_written" in markdown
    assert "bad_fields" in table
    assert "return-field-markdown-probe" in table


def test_markdown_render_lists_semantic_duplicate_invariants(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/gpd/commands/semantic-render-a.md",
        """
        ---
        name: gpd:semantic-render-a
        description: Semantic render A
        ---
        Treat output as fresh only when gpd_return.files_written lists the expected artifact and it is readable.
        """,
    )
    _write(
        tmp_path,
        "src/gpd/specs/workflows/semantic-render-b.md",
        """
        ---
        name: semantic-render-b
        ---
        The artifact gate passes when gpd_return.files_written names the same path that exists now.
        """,
    )

    diagnostics = _diagnostics()
    report = _report(tmp_path, runtime_names=())
    markdown = diagnostics.render_prompt_surface_markdown(report, top=1)

    assert "## Semantic Duplicate Invariants" in markdown
    assert "`files_written_freshness`" in markdown
    assert "### `files_written_freshness` Examples" in markdown
    assert "`src/gpd/commands/semantic-render-a.md:" in markdown


def test_runtime_top_prompts_render_in_markdown_and_table(tmp_path: Path) -> None:
    runtime_name = _non_native_runtime_name()
    _write(
        tmp_path,
        "src/gpd/commands/runtime-render-probe.md",
        """
        ---
        name: gpd:runtime-render-probe
        description: Runtime render probe
        ---
        ```bash
        gpd hidden-probe
        ```
        """,
    )

    diagnostics = _diagnostics()
    report = _report(tmp_path, surfaces=("command",), runtime_names=(runtime_name,))
    markdown = diagnostics.render_prompt_surface_markdown(report, top=1)
    table = diagnostics.render_prompt_surface_table(report, top=1)

    assert "## Runtime Top Prompts" in markdown
    assert "Shell rewrites" in markdown
    assert f"| `{runtime_name}` | 1 |" in markdown
    assert "`runtime-render-probe`" in markdown
    assert "runtime top prompts" in table
    assert "projected_chars" in table
    assert "shell_rewrites" in table
    assert "runtime-render-probe" in table


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
