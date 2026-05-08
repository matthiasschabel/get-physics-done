"""Prompt-budget assertions for `gpd-planner` bootstrap loading."""

from __future__ import annotations

from pathlib import Path

from tests.prompt_metrics_support import measure_prompt_surface

REPO_ROOT = Path(__file__).resolve().parents[2]
PLANNER_PATH = REPO_ROOT / "src" / "gpd" / "agents" / "gpd-planner.md"
SOURCE_ROOT = REPO_ROOT / "src" / "gpd"
PATH_PREFIX = "/runtime/"
PLANNING_REFERENCES_DIR = SOURCE_ROOT / "specs" / "references" / "planning"

OLD_DOMAIN_CATALOG_HEADINGS = (
    "QFT Perturbative Calculation",
    "Condensed Matter (Analytical)",
    "Condensed Matter (Numerical)",
    "General Relativity / Cosmology",
    "AMO / Quantum Optics",
    "Numerical PDE/ODE",
    "Effective Field Theory",
    "### Domain Selection",
    "### Cross-Domain Projects",
)

ON_DEMAND_PLANNING_GUIDES = {
    "qft-perturbative-calculation.md": "QFT Perturbative Calculation",
    "condensed-matter-analytical.md": "Condensed Matter (Analytical)",
    "condensed-matter-numerical.md": "Condensed Matter (Numerical)",
    "statistical-mechanics.md": "Statistical Mechanics Planning Guide",
    "gr-cosmology.md": "General Relativity / Cosmology",
    "amo-quantum-optics.md": "AMO / Quantum Optics",
    "numerical-pde-ode.md": "Numerical PDE/ODE",
    "effective-field-theory.md": "Effective Field Theory",
    "cross-domain-convention-bridge.md": "Cross-Domain Projects Planning Guide",
}


def _read_planner_prompt() -> str:
    return PLANNER_PATH.read_text(encoding="utf-8")


def _between(text: str, start: str, end: str) -> str:
    _, start_marker, tail = text.partition(start)
    assert start_marker, f"Missing marker: {start}"
    body, end_marker, _ = tail.partition(end)
    assert end_marker, f"Missing marker: {end}"
    return body


def test_planner_bootstrap_does_not_eagerly_load_execution_or_completion_only_materials() -> None:
    planner = _read_planner_prompt()
    role = _between(planner, "<role>", "</role>")

    assert "@{GPD_INSTALL_DIR}/templates/phase-prompt.md" in role
    assert "@{GPD_INSTALL_DIR}/templates/plan-contract-schema.md" not in role
    assert "@{GPD_INSTALL_DIR}/workflows/execute-plan.md" not in role
    assert "@{GPD_INSTALL_DIR}/templates/summary.md" not in role
    assert "@{GPD_INSTALL_DIR}/references/protocols/order-of-limits.md" not in role
    assert role.index("@{GPD_INSTALL_DIR}/templates/phase-prompt.md") < role.index(
        "before any `PLAN.md` emission."
    )
    assert "planner contract schema is carried there" in role


def test_expanded_planner_prompt_stays_under_budget() -> None:
    metrics = measure_prompt_surface(
        PLANNER_PATH,
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )

    assert metrics.raw_include_count <= 3
    assert metrics.expanded_char_count < 112_000
    assert metrics.expanded_line_count < 2_350


def test_planner_prompt_no_longer_carries_the_removed_high_level_boilerplate() -> None:
    planner = _read_planner_prompt()

    for removed_marker in (
        "Quality Degradation Curve",
        "Research Fast",
        "Specificity Examples",
    ):
        assert removed_marker not in planner


def test_domain_blueprint_catalog_is_on_demand_not_in_base_prompt() -> None:
    planner = _read_planner_prompt()

    assert "references/planning/domain-strategy-index.md" in planner
    assert "planning_guides" in planner

    for removed_heading in OLD_DOMAIN_CATALOG_HEADINGS:
        assert removed_heading not in planner


def test_on_demand_domain_planning_guides_are_reachable() -> None:
    index = (PLANNING_REFERENCES_DIR / "domain-strategy-index.md").read_text(encoding="utf-8")

    for guide_name, expected_heading in ON_DEMAND_PLANNING_GUIDES.items():
        guide_path = PLANNING_REFERENCES_DIR / guide_name
        assert guide_path.is_file(), guide_name
        assert f"references/planning/{guide_name}" in index
        assert expected_heading in guide_path.read_text(encoding="utf-8")


def test_planner_prompt_delegates_raw_plan_template_to_canonical_template() -> None:
    planner = _read_planner_prompt()

    assert "## PLAN.md Source Of Truth" in planner
    assert "Do not inline, paraphrase, or reconstruct a second raw PLAN template here." in planner
    assert "## PLAN.md Structure" not in planner
    assert "```markdown\n---\nphase: XX-name" not in planner
    assert "claim-polarization" not in planner
    assert "deliv-vac-pol" not in planner
    assert "<execution_context>Use the already-loaded `phase-prompt.md`" not in planner
    assert "Researcher Setup Frontmatter" not in planner
    assert "Tool Requirements Frontmatter" not in planner


def test_planner_delegates_checkpoint_examples_to_canonical_reference() -> None:
    planner = _read_planner_prompt()
    checkpoint_section = _between(planner, "<checkpoints>", "</checkpoints>")

    assert "references/orchestration/checkpoints.md" in checkpoint_section
    assert "references/orchestration/checkpoint-ux-convention.md" in checkpoint_section
    assert "Do not inline a second checkpoint template here." in checkpoint_section
    assert '<task type="checkpoint:human-verify"' not in checkpoint_section
    assert '<task type="checkpoint:decision"' not in checkpoint_section
    assert "Bad -- Checkpointing every derivation step" not in checkpoint_section
    assert "Good -- Single verification at logical boundary" not in checkpoint_section
