from __future__ import annotations

from pathlib import Path

from tests.prompt_metrics_support import count_unfenced_heading

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "src" / "gpd" / "agents"
REFERENCES_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "references"


def _read_agent(name: str) -> str:
    return (AGENTS_DIR / name).read_text(encoding="utf-8")


def test_referee_routes_on_status_and_shows_base_return_fields_first() -> None:
    source = _read_agent("gpd-referee.md")

    assert (
        "The markdown headings `## REVIEW COMPLETE`, `## REVIEW INCOMPLETE`, and `## CHECKPOINT REACHED` are human-readable labels only."
        in source
    )
    assert "Route on `gpd_return.status` and the written review artifacts, not on heading text." in source
    assert count_unfenced_heading(source, "## REVIEW COMPLETE") == 0
    assert count_unfenced_heading(source, "## REVIEW INCOMPLETE") == 0
    assert count_unfenced_heading(source, "## CHECKPOINT REACHED") == 0

    status_idx = source.index("  status: completed")
    files_idx = source.index("  files_written:")
    recommendation_idx = source.index('  recommendation: "minor_revision"')

    assert status_idx < files_idx < recommendation_idx


def test_project_researcher_uses_presentation_only_heading_mapping_and_base_fields_first() -> None:
    source = _read_agent("gpd-project-researcher.md")

    assert "gpd_return:" in source
    assert "status: completed" in source
    assert "files_written:\n    - GPD/literature/SUMMARY.md" in source
    assert "confidence: HIGH" in source
    assert "Mapping: RESEARCH COMPLETE → completed, RESEARCH BLOCKED → blocked" not in source
    assert "Route on `gpd_return.status` per the status-routing role kit." in source

    next_actions_idx = source.index("  next_actions:")
    confidence_idx = source.index("  confidence: HIGH")

    assert next_actions_idx < confidence_idx


def test_plan_checker_uses_typed_status_and_drops_nested_return_payload_examples() -> None:
    source = _read_agent("gpd-plan-checker.md")
    return_protocol = (REFERENCES_DIR / "verification" / "plan-checker" / "checker-return-protocol.md").read_text(
        encoding="utf-8"
    )

    assert (
        "The label examples in `checker-return-protocol.md` are UI only; use `gpd_return.status` for the machine decision."
        in source
    )
    assert "the machine decision comes from `gpd_return.status`" in source
    assert "Headings above are presentation only. Route on `gpd_return.status`" in return_protocol
    assert "`gpd_return.status: completed`" in source
    assert "`gpd_return.status: checkpoint`" in source
    assert "`gpd_return.status: failed`" in source
    assert "`gpd_return.status: blocked`" in source
    assert count_unfenced_heading(source, "## VERIFICATION PASSED") == 0
    assert count_unfenced_heading(source, "## ISSUES FOUND") == 0

    status_idx = source.index("  status: completed")
    files_idx = source.index("  files_written: []")
    approved_idx = source.index("  approved_plans:")

    assert status_idx < files_idx < approved_idx
    assert "contract_gate_summary:" not in source
    assert "issues_found:" not in source
    assert "escalation: null | {pattern, options}" not in source
    assert "# Mapping: all_approved" not in source
