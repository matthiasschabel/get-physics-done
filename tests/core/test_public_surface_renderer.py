from __future__ import annotations

from pathlib import Path

import pytest

from gpd.core.public_surface_renderer import (
    public_surface_block_ids,
    public_surface_context,
    render_beginner_caveat_list,
    render_beginner_preflight_list,
    render_local_cli_bridge_summary,
    render_os_install_matrix,
    render_os_next_step_table,
    render_post_start_settings_note,
    render_public_surface_block,
    render_recovery_note,
    render_runtime_doc_links,
    render_runtime_quickstart_snippet,
    render_startup_ladder,
    render_supported_runtime_table,
    render_terminal_runtime_bridge_text,
    runtime_doc_filename,
    runtime_quickstart_block_id,
)
from scripts.render_public_surface import (
    check_generated_files,
    check_generated_regions,
    generated_region_markers,
    render_generated_region,
    replace_generated_regions,
    update_generated_files,
)


def _table_row(*cells: str) -> str:
    return "| " + " | ".join(cells) + " |"


def _runtime_doc_slug(display_name: str) -> str:
    return "-".join(display_name.casefold().split())


def test_basic_contract_renderers_emit_canonical_public_surface() -> None:
    context = public_surface_context()
    contract = context.contract

    assert render_startup_ladder(context) == contract.beginner_onboarding.render_startup_ladder()
    assert render_beginner_preflight_list(context).splitlines() == [
        f"- {item}" for item in contract.beginner_onboarding.preflight_requirements
    ]
    assert render_beginner_caveat_list(context).splitlines() == [
        f"- {item}" for item in contract.beginner_onboarding.caveats
    ]
    assert render_post_start_settings_note(context) == contract.post_start_settings.render_note()
    assert render_recovery_note(context) == contract.recovery_ladder.render_note(
        resume_work_phrase="`resume-work`",
        suggest_next_phrase="`suggest-next`",
        pause_work_phrase="`pause-work`",
    )


def test_terminal_and_local_cli_bridge_text_derive_from_runtime_and_contract_data() -> None:
    context = public_surface_context()

    terminal_bridge = render_terminal_runtime_bridge_text(context)
    for surface in context.runtime_surfaces:
        assert f"`{surface.launch_command}`" in terminal_bridge
        assert f"`{surface.help_command}`" in terminal_bridge
    assert context.contract.beginner_onboarding.render_startup_ladder() in terminal_bridge

    cli_summary = render_local_cli_bridge_summary(context)
    assert context.contract.local_cli_bridge.render_note() in cli_summary
    for command in context.contract.local_cli_bridge.commands:
        assert f"- `{command}`" in cli_summary


def test_supported_runtime_and_install_tables_follow_public_runtime_surfaces() -> None:
    context = public_surface_context()

    supported_table = render_supported_runtime_table(context)
    assert supported_table.splitlines()[0] == _table_row(
        "Runtime",
        "`npx` flag",
        "Help",
        "Start",
        "Tour",
        "New work",
        "Existing work",
        "Return later",
    )
    for surface in context.runtime_surfaces:
        assert (
            _table_row(
                surface.display_name,
                f"`{surface.install_flag}`",
                f"`{surface.help_command}`",
                f"`{surface.start_command}`",
                f"`{surface.tour_command}`",
                f"`{surface.new_project_minimal_command}`",
                f"`{surface.map_research_command}`",
                f"`{surface.resume_work_command}`",
            )
            in supported_table.splitlines()
        )

    install_table = render_os_install_matrix(context)
    assert install_table.splitlines()[0] == _table_row("Runtime", "Install command")
    for surface in context.runtime_surfaces:
        install_command = f"{context.bootstrap_command} {surface.install_flag} --local"
        assert _table_row(surface.display_name, f"`{install_command}`") in install_table.splitlines()


def test_os_next_step_table_collapses_matching_runtime_command_columns() -> None:
    context = public_surface_context()
    command_groups: list[tuple[list[str], tuple[str, ...]]] = []
    group_indexes: dict[tuple[str, ...], int] = {}
    for surface in context.runtime_surfaces:
        commands = (
            surface.start_command,
            surface.tour_command,
            surface.new_project_minimal_command,
            surface.map_research_command,
            context.contract.recovery_ladder.local_snapshot_command,
            surface.resume_work_command,
        )
        group_index = group_indexes.get(commands)
        if group_index is None:
            group_indexes[commands] = len(command_groups)
            command_groups.append(([surface.display_name], commands))
        else:
            command_groups[group_index][0].append(surface.display_name)

    expected_headers = ["What you want to do", *(" / ".join(names) for names, _commands in command_groups)]
    expected_rows = (
        ("Not sure which path fits this folder", 0),
        ("Want a guided overview", 1),
        ("Start a new project", 2),
        ("Map an existing folder", 3),
        ("Rediscover the workspace in your normal terminal", 4),
        ("Continue in the reopened runtime", 5),
    )

    table_lines = render_os_next_step_table(context).splitlines()
    assert table_lines[0] == _table_row(*expected_headers)
    for label, command_index in expected_rows:
        assert (
            _table_row(label, *(f"`{commands[command_index]}`" for _names, commands in command_groups)) in table_lines
        )


def test_runtime_doc_links_and_quickstart_snippets_are_runtime_derived() -> None:
    context = public_surface_context()
    doc_links = render_runtime_doc_links(context)

    for surface in context.runtime_surfaces:
        assert runtime_doc_filename(surface) == f"{_runtime_doc_slug(surface.display_name)}.md"
        assert f"- [{surface.display_name} quickstart](./{runtime_doc_filename(surface)})" in doc_links

        snippet = render_runtime_quickstart_snippet(surface.runtime_name, context)
        assert f"{context.bootstrap_command} {surface.install_flag} --local" in snippet
        assert "```bash\n" in snippet
        assert f"\n{surface.launch_command}\n```" in snippet
        for command in (
            surface.help_command,
            surface.start_command,
            surface.tour_command,
            surface.new_project_minimal_command,
            surface.map_research_command,
            surface.resume_work_command,
            surface.settings_command,
            context.contract.recovery_ladder.local_snapshot_command,
            context.contract.recovery_ladder.cross_workspace_command,
        ):
            assert command in snippet
        assert context.contract.post_start_settings.default_sentence in snippet


def test_public_surface_block_registry_includes_runtime_quickstarts() -> None:
    context = public_surface_context()
    block_ids = public_surface_block_ids(context)

    for block_id in (
        "beginner-startup-ladder",
        "beginner-preflight",
        "beginner-caveats",
        "terminal-runtime-bridge",
        "local-cli-bridge-summary",
        "post-start-settings",
        "recovery-note",
        "supported-runtimes-table",
        "os-install-matrix",
        "os-next-steps-table",
        "runtime-doc-links",
    ):
        assert block_id in block_ids
        assert render_public_surface_block(block_id, context)

    for surface in context.runtime_surfaces:
        block_id = runtime_quickstart_block_id(surface)
        assert block_id in block_ids
        assert render_public_surface_block(block_id, context) == render_runtime_quickstart_snippet(
            surface.runtime_name,
            context,
        )

    with pytest.raises(KeyError, match="Unknown public surface block"):
        render_public_surface_block("unknown-block", context)


def test_generated_region_helpers_check_and_replace_stale_regions() -> None:
    block_id = "beginner-startup-ladder"
    text = "before\n" + render_generated_region(block_id, "stale body") + "\nafter\n"

    diffs = check_generated_regions(text)
    assert len(diffs) == 1
    assert diffs[0].block_id == block_id
    assert "stale body" in diffs[0].diff

    updated = replace_generated_regions(text)
    assert "stale body" not in updated
    assert render_public_surface_block(block_id) in updated
    assert updated.startswith("before\n")
    assert updated.endswith("\nafter\n")
    assert check_generated_regions(updated) == ()


def test_generated_file_helpers_update_explicit_paths(tmp_path: Path) -> None:
    block_id = "beginner-preflight"
    target = tmp_path / "surface.md"
    target.write_text(render_generated_region(block_id, "old") + "\n", encoding="utf-8")

    diffs = check_generated_files((target,), repo_root=tmp_path)
    assert len(diffs) == 1
    assert diffs[0].path == target

    assert update_generated_files((target,), repo_root=tmp_path) == (target,)
    assert check_generated_files((target,), repo_root=tmp_path) == ()
    assert render_public_surface_block(block_id) in target.read_text(encoding="utf-8")
    assert update_generated_files((target,), repo_root=tmp_path) == ()


def test_generated_region_helpers_fail_closed_for_bad_markers() -> None:
    start_marker, _end_marker = generated_region_markers("unknown-block")
    with pytest.raises(ValueError, match="Unknown public surface generated block"):
        replace_generated_regions(f"{start_marker}\nbody\n<!-- gpd-public-surface:unknown-block:end -->")

    known_start, known_end = generated_region_markers("beginner-caveats")
    with pytest.raises(ValueError, match="Missing end marker"):
        replace_generated_regions(f"{known_start}\nbody\n")

    nested_start, nested_end = generated_region_markers("beginner-preflight")
    with pytest.raises(ValueError, match="Nested public surface generated block"):
        replace_generated_regions(f"{known_start}\n{nested_start}\nbody\n{nested_end}\n{known_end}\n")
