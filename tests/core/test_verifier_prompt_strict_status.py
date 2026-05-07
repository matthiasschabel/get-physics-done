from pathlib import Path

AGENTS_DIR = Path(__file__).resolve().parents[2] / "src" / "gpd" / "agents"
STATUS_AUTHORITY = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "gpd"
    / "specs"
    / "references"
    / "verification"
    / "verification-status-authority.md"
)


def test_verifier_prompt_strict_pass_matches_verification_report_reference_rules() -> None:
    verifier_prompt = (AGENTS_DIR / "gpd-verifier.md").read_text(encoding="utf-8")
    status_authority = STATUS_AUTHORITY.read_text(encoding="utf-8")

    assert "{GPD_INSTALL_DIR}/references/verification/verification-status-authority.md" in verifier_prompt
    assert "`passed`: every decisive target is `VERIFIED`" in status_authority
    assert "required references are completed" in status_authority
    assert "every `must_surface` reference has all `required_actions` recorded in `completed_actions`" in status_authority
    assert "no unresolved decisive `suggested_contract_checks` remain" in status_authority
    assert "decisive comparison verdicts are acceptable" in status_authority
    assert "required references handled" not in verifier_prompt
