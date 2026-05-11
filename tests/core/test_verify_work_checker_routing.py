"""Focused assertions for the verify-work checker routing seam."""

from pathlib import Path

from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY_WORK = REPO_ROOT / "src" / "gpd" / "specs" / "workflows" / "verify-work.md"


def test_verify_work_routes_on_structured_checker_statuses() -> None:
    workflow = workflow_authority_text(VERIFY_WORK.parent, "verify-work")

    assert "route on `gpd_return.status` and the structured plan lists" in workflow
    assert "- `completed`: accept only after fresh on-disk plans still match planner `files_written`." in workflow
    assert (
        "- `checkpoint`: some plans are approved and others need revision; record `approved_plans` and `blocked_plans`"
        in workflow
    )
    assert "- `blocked`: nothing is approved; feed the checker issues and blocked plan IDs back into the revision loop without rewriting approved plans." in workflow
    assert "- `failed`: present the issues and offer retry or manual revision." in workflow


def test_verify_work_references_one_shot_checker_contract_in_the_gap_closure_loop() -> None:
    workflow = workflow_authority_text(VERIFY_WORK.parent, "verify-work")

    assert 'id: "verify_work_gap_plan_checker"' in workflow
    assert "shared gate and continuation rules live in `references/orchestration/child-artifact-gate.md`" in workflow
    assert "route from structured `approved_plans`, `blocked_plans`, and `issues`" in workflow
    assert "not on presentation text" in workflow
