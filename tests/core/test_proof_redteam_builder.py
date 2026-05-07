from __future__ import annotations

from pathlib import Path

import pytest

from gpd.core.proof_redteam import build_proof_redteam_skeleton, validate_proof_redteam_artifact
from tests.manuscript_test_support import write_proof_review_package


def test_proof_redteam_skeleton_defaults_to_gap_status_without_passed_text() -> None:
    skeleton = build_proof_redteam_skeleton(
        claim_id="CLM-001",
        claim_text="For every r_0 > 0, the orbit intersects the target annulus.",
    )

    assert skeleton.target_status == "gaps_found"
    assert skeleton.frontmatter["status"] == "gaps_found"
    assert skeleton.frontmatter["reviewer"] == "gpd-check-proof"
    assert skeleton.frontmatter["claim_ids"] == ["CLM-001"]
    assert skeleton.frontmatter["proof_artifact_paths"] == ["TODO-proof-artifact-path"]
    assert skeleton.frontmatter["missing_parameter_symbols"] == ["TODO-check-named-parameters"]
    assert skeleton.frontmatter["scope_status"] == "unclear"
    assert skeleton.frontmatter["counterexample_status"] == "not_attempted"
    assert "# Proof Redteam" in skeleton.markdown_draft
    assert "## Proof Inventory" in skeleton.markdown_draft
    assert "## Coverage Ledger" in skeleton.markdown_draft
    assert "## Adversarial Probe" in skeleton.markdown_draft
    assert "## Verdict" in skeleton.markdown_draft
    assert "## Required Follow-Up" in skeleton.markdown_draft
    assert "passed" not in skeleton.markdown_draft


def test_proof_redteam_skeleton_supports_human_needed_without_certifying() -> None:
    skeleton = build_proof_redteam_skeleton(
        claim_id="CLM-002",
        status="human_needed",
        proof_artifact_paths=["paper/theorem.tex", "paper/theorem.tex"],
    )

    assert skeleton.target_status == "human_needed"
    assert skeleton.frontmatter["status"] == "human_needed"
    assert skeleton.frontmatter["proof_artifact_paths"] == ["paper/theorem.tex"]
    assert skeleton.frontmatter["coverage_gaps"] == ["Human judgment is required before this proof audit can close."]
    assert "status: human_needed" in skeleton.frontmatter_yaml
    assert "passed" not in skeleton.markdown_draft


def test_proof_redteam_skeleton_rejects_passed_status() -> None:
    with pytest.raises(ValueError, match="gaps_found.*human_needed"):
        build_proof_redteam_skeleton(claim_id="CLM-001", status="passed")


def test_proof_redteam_skeleton_requires_complete_manuscript_binding() -> None:
    with pytest.raises(ValueError, match="manuscript_path.*manuscript_sha256.*round_number"):
        build_proof_redteam_skeleton(
            claim_id="CLM-001",
            manuscript_path="paper/main.tex",
        )


def test_validate_proof_redteam_artifact_accepts_conservative_skeleton_with_real_proof_path(
    tmp_path: Path,
) -> None:
    proof_path = tmp_path / "paper" / "theorem.tex"
    proof_path.parent.mkdir(parents=True)
    proof_path.write_text("\\begin{theorem}Demo.\\end{theorem}\n", encoding="utf-8")
    skeleton = build_proof_redteam_skeleton(
        claim_id="CLM-001",
        claim_text="For every r_0 > 0, the orbit intersects the target annulus.",
        proof_artifact_paths=["paper/theorem.tex"],
    )
    artifact_path = tmp_path / "PROOF-REDTEAM.md"
    artifact_path.write_text(skeleton.markdown_draft, encoding="utf-8")

    result = validate_proof_redteam_artifact(
        artifact_path,
        project_root=tmp_path,
        expected_claim_ids=("CLM-001",),
        expected_proof_artifact_paths=("paper/theorem.tex",),
    )

    assert result.valid is True
    assert result.status == "gaps_found"
    assert result.errors == []


def test_validate_proof_redteam_artifact_surfaces_existing_parser_errors(tmp_path: Path) -> None:
    proof_path = tmp_path / "paper" / "theorem.tex"
    proof_path.parent.mkdir(parents=True)
    proof_path.write_text("\\begin{theorem}Demo.\\end{theorem}\n", encoding="utf-8")
    skeleton = build_proof_redteam_skeleton(
        claim_id="CLM-001",
        claim_text="For every r_0 > 0, the orbit intersects the target annulus.",
        proof_artifact_paths=["paper/theorem.tex"],
    )
    artifact_path = tmp_path / "PROOF-REDTEAM.md"
    artifact_path.write_text(skeleton.markdown_draft, encoding="utf-8")

    result = validate_proof_redteam_artifact(
        artifact_path,
        project_root=tmp_path,
        expected_claim_ids=("CLM-002",),
    )

    assert result.valid is False
    assert result.status is None
    assert result.errors == ["top-level frontmatter `claim_ids` does not match the theorem-bearing claims under review"]


def test_validate_proof_redteam_artifact_accepts_existing_passed_artifact(tmp_path: Path) -> None:
    package = write_proof_review_package(
        tmp_path,
        theorem_bearing=True,
        review_report=True,
        proof_redteam_status="passed",
    )
    artifact_path = tmp_path / "GPD" / "review" / "PROOF-REDTEAM.md"

    result = validate_proof_redteam_artifact(
        artifact_path,
        project_root=tmp_path,
        expected_claim_ids=("CLM-001",),
        expected_proof_artifact_paths=("paper/curvature_flow_bounds.tex",),
    )

    assert result.valid is True
    assert result.status == "passed"
    assert result.errors == []
    assert package.manuscript_path.exists()
