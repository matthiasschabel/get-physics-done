from __future__ import annotations

from pathlib import Path

from tests.assertion_taxonomy_support import assert_prompt_contracts, machine_exact, semantic_concept

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
AGENTS_DIR = REPO_ROOT / "src" / "gpd" / "agents"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_comparison_workflows_call_comparison_contract_validator() -> None:
    compare_experiment = _read(WORKFLOWS_DIR / "compare-experiment.md")
    compare_results = _read(WORKFLOWS_DIR / "compare-results.md")

    expected = 'gpd validate comparison-contract "${COMPARISON_OUTPUT_PATH}"'
    assert expected in compare_experiment
    assert expected in compare_results
    for workflow in (compare_experiment, compare_results):
        assert_prompt_contracts(
            workflow,
            *semantic_concept(
                "comparison workflow rejects incomplete comparison artifacts",
                required=("treat the comparison artifact as incomplete",),
            ),
        )


def test_verifier_artifact_levels_are_four_level_consistent() -> None:
    verifier = _read(AGENTS_DIR / "gpd-verifier.md")

    assert_prompt_contracts(
        verifier,
        machine_exact(
            "verifier four-level artifact headings",
            (
                "## Step 4: Verify Artifacts (Four Levels)",
                "### Level 1: Existence",
                "### Level 2: Substantive Content",
                "### Level 3: Content Validation",
                "### Level 4: Integration",
            ),
        ),
        *semantic_concept("verifier artifact pass semantics", required=("all artifacts pass levels 1-4",)),
    )


def test_verify_phase_keeps_independent_confirmed_tally_out_of_machine_fields() -> None:
    verify_phase = _read(WORKFLOWS_DIR / "verify-phase.md")

    assert_prompt_contracts(
        verify_phase,
        *semantic_concept(
            "verify phase keeps independent-confirmed tally narrative-only",
            required=("Keep any independent-confirmed tally in the report body or markdown return narrative only",),
        ),
    )
    assert "do not add it to verification frontmatter or `gpd_return`" in verify_phase
    assert "independently confirmed count (K/M)" not in verify_phase
