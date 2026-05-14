"""Exact prompt-assertion budget contracts."""

from __future__ import annotations

import textwrap
from functools import lru_cache
from pathlib import Path

from gpd.core.prompt_diagnostics import build_prompt_surface_report, report_to_dict
from gpd.core.prompt_exactness_diagnostics import scan_exact_assertion_diagnostics

REPO_ROOT = Path(__file__).resolve().parents[2]

EXACTNESS_TOTAL_BUDGETS = {
    "brittle_prose_assertions": 720,
    "exact_assertion_count": 5_460,
}
HIGH_SEVERITY_BASELINES: dict[str, dict[str, int]] = {}


@lru_cache
def _exactness_payload() -> dict[str, object]:
    report = build_prompt_surface_report(
        REPO_ROOT,
        runtime_names=(),
        include_tests=True,
        include_runtime_projections=False,
    )
    payload = report_to_dict(report)
    exactness = payload["exact_assertion_diagnostics"]
    assert isinstance(exactness, dict)
    return exactness


def _exactness_files_by_path() -> dict[str, dict[str, object]]:
    exactness = _exactness_payload()
    rows = exactness["files"]
    assert isinstance(rows, list)
    return {str(row["path"]): row for row in rows if isinstance(row, dict)}


def test_taxonomy_helper_usage_tracks_semantic_concept_without_hiding_raw_exactness(tmp_path: Path) -> None:
    test_file = tmp_path / "tests" / "test_prompt_contracts.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        textwrap.dedent(
            """
            from tests.assertion_taxonomy_support import (
                assert_prompt_contracts,
                machine_exact,
                public_exact,
                semantic_anchor,
                semantic_concept,
            )

            PROMPT = "Quick Start\\ngpd_return.status\\nstable semantic anchor\\n"

            def test_prompt_contracts():
                assert "gpd_return.status" in PROMPT
                assert "Quick Start" in PROMPT
                assert_prompt_contracts(
                    PROMPT,
                    machine_exact("schema", "gpd_return.status"),
                    public_exact("help", "Quick Start"),
                    semantic_anchor("meaning", "stable semantic anchor"),
                    *semantic_concept(
                        "meaning concept",
                        required=("stable semantic anchor",),
                        forbidden=("the exact old sentence is gone forever",),
                    ),
                )
            """
        ).lstrip(),
        encoding="utf-8",
    )

    exactness = scan_exact_assertion_diagnostics(tmp_path)
    totals = exactness["totals"]
    usage = exactness["taxonomy_helper_usage"]
    assert isinstance(totals, dict)
    assert isinstance(usage, dict)
    usage_totals = usage["totals"]
    assert isinstance(usage_totals, dict)

    assert totals["exact_assertion_count"] == 2
    assert totals["machine_contract_exact_assertions"] == 1
    assert totals["public_ux_exact_assertions"] == 1
    assert totals["brittle_prose_assertions"] == 0
    assert usage_totals["assert_prompt_contracts"] == 1
    assert usage_totals["machine_exact"] == 1
    assert usage_totals["public_exact"] == 1
    assert usage_totals["semantic_anchor"] == 1
    assert usage_totals["semantic_concept"] == 1


def test_exactness_totals_do_not_grow_past_baseline() -> None:
    exactness = _exactness_payload()
    totals = exactness["totals"]
    assert isinstance(totals, dict)

    for field, budget in EXACTNESS_TOTAL_BUDGETS.items():
        observed = totals[field]
        assert isinstance(observed, int)
        assert observed <= budget, f"{field} budget exceeded: observed={observed} max={budget}"


def test_exactness_has_no_new_high_severity_files() -> None:
    rows_by_path = _exactness_files_by_path()
    high_paths = {path for path, row in rows_by_path.items() if row["severity"] == "high"}
    unexpected_high_paths = sorted(high_paths - set(HIGH_SEVERITY_BASELINES))

    assert unexpected_high_paths == []


def test_existing_high_severity_files_do_not_gain_exact_or_brittle_assertions() -> None:
    rows_by_path = _exactness_files_by_path()

    for path, baseline in HIGH_SEVERITY_BASELINES.items():
        row = rows_by_path.get(path)
        if row is None:
            continue
        exact_count = row["exact_assertion_count"]
        brittle_count = row["brittle_prose_assertions"]
        assert isinstance(exact_count, int)
        assert isinstance(brittle_count, int)
        assert exact_count <= baseline["exact"], (
            f"{path} exact assertion budget exceeded: observed={exact_count} max={baseline['exact']}"
        )
        assert brittle_count <= baseline["brittle"], (
            f"{path} brittle prose budget exceeded: observed={brittle_count} max={baseline['brittle']}"
        )
