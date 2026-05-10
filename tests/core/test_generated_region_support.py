from __future__ import annotations

from pathlib import Path

import pytest

from scripts.generated_region_support import (
    GeneratedRegionDiff,
    GeneratedRegionSpec,
    marker_pair,
    marker_start_counts,
    render_region,
    replace_regions,
    unified_diff_text,
    write_stale_check_result,
)


def _region_spec() -> GeneratedRegionSpec:
    return GeneratedRegionSpec(
        marker_prefix="gpd-test",
        known_block_ids=lambda: ("alpha", "beta"),
        block_label="test generated block",
    )


def test_marker_pair_and_render_region_normalize_generated_body() -> None:
    spec = _region_spec()

    assert marker_pair(spec, "alpha") == (
        "<!-- gpd-test:alpha:start -->",
        "<!-- gpd-test:alpha:end -->",
    )
    assert render_region(spec, "alpha", "body\n\n") == (
        "<!-- gpd-test:alpha:start -->\nbody\n<!-- gpd-test:alpha:end -->"
    )


def test_marker_prefix_separator_supports_existing_fixed_marker_shape() -> None:
    spec = GeneratedRegionSpec(
        marker_prefix="repo-graph",
        known_block_ids=lambda: ("scope",),
        block_label="repo graph block",
        marker_prefix_separator="-",
    )
    stale = "<!-- repo-graph-scope:start -->\nstale\n<!-- repo-graph-scope:end -->"

    updated, block_ids = replace_regions(stale, spec=spec, render_body=lambda block_id: f"{block_id} body")

    assert marker_pair(spec, "scope") == (
        "<!-- repo-graph-scope:start -->",
        "<!-- repo-graph-scope:end -->",
    )
    assert block_ids == ("scope",)
    assert updated == "<!-- repo-graph-scope:start -->\nscope body\n<!-- repo-graph-scope:end -->"


def test_replace_regions_preserves_order_and_reports_replaced_block_ids() -> None:
    spec = _region_spec()
    text = "before\n" + render_region(spec, "alpha", "old") + "\n" + render_region(spec, "beta", "old") + "\nafter\n"

    updated, block_ids = replace_regions(
        text,
        spec=spec,
        render_body=lambda block_id: f"{block_id} body",
    )

    assert block_ids == ("alpha", "beta")
    assert updated == (
        "before\n"
        "<!-- gpd-test:alpha:start -->\nalpha body\n<!-- gpd-test:alpha:end -->\n"
        "<!-- gpd-test:beta:start -->\nbeta body\n<!-- gpd-test:beta:end -->\n"
        "after\n"
    )
    assert marker_start_counts(updated, spec=spec) == {"alpha": 1, "beta": 1}


def test_replace_regions_fails_closed_for_malformed_marker_ranges() -> None:
    spec = _region_spec()
    alpha_start, alpha_end = marker_pair(spec, "alpha")
    beta_start, beta_end = marker_pair(spec, "beta")

    with pytest.raises(ValueError, match="Unknown test generated block 'gamma' in target.md"):
        replace_regions(
            "<!-- gpd-test:gamma:start -->\nbody\n<!-- gpd-test:gamma:end -->",
            spec=spec,
            render_body=lambda block_id: block_id,
            path=Path("target.md"),
        )
    with pytest.raises(ValueError, match="Missing end marker for test generated block 'alpha'"):
        replace_regions(f"{alpha_start}\nbody\n", spec=spec, render_body=lambda block_id: block_id)
    with pytest.raises(ValueError, match="Nested test generated block before 'alpha' ends"):
        replace_regions(
            f"{alpha_start}\n{beta_start}\nbody\n{beta_end}\n{alpha_end}\n",
            spec=spec,
            render_body=lambda block_id: block_id,
        )
    with pytest.raises(ValueError, match="Orphan end marker for test generated block 'alpha'"):
        replace_regions(f"before\n{alpha_end}\nafter\n", spec=spec, render_body=lambda block_id: block_id)


def test_diff_and_stale_check_helpers_match_renderer_cli_shape(capsys: pytest.CaptureFixture[str]) -> None:
    diff_text = unified_diff_text("new\n", "old\n", path=Path("target.md"), block_id="alpha")
    diff = GeneratedRegionDiff(path=Path("target.md"), block_id="alpha", diff=diff_text)

    assert "--- target.md:alpha (current)" in diff_text
    assert "+++ target.md:alpha (expected)" in diff_text
    assert write_stale_check_result((diff,), heading="Generated regions are stale.", regenerate_command="render") == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("Generated regions are stale. Run `render` and commit the result.\n\n")
    assert "--- target.md:alpha (current)" in captured.err
