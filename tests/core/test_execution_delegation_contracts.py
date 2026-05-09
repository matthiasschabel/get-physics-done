from __future__ import annotations

from pathlib import Path

from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"
EXECUTION_REFERENCES_DIR = REPO_ROOT / "src/gpd/specs/references/execution"


def test_execute_plan_routes_checkpoints_through_orchestrator_owned_returns() -> None:
    execute_plan = (WORKFLOWS_DIR / "execute-plan.md").read_text(encoding="utf-8")
    checkpoints = (EXECUTION_REFERENCES_DIR / "execute-plan-checkpoints.md").read_text(encoding="utf-8")

    assert "wait for user" not in execute_plan
    assert "wait for approval" not in execute_plan
    assert "Emit the checkpoint return with the task result and all intermediate values" in execute_plan
    assert "return structured checkpoint state to the orchestrator" in execute_plan
    assert "Awaiting (what the orchestrator must resolve before continuation)" in checkpoints
    assert "the child never waits for user approval inside the same run" in checkpoints


def test_execute_plan_clean_wave_batching_uses_typed_verification_outcome() -> None:
    execute_plan = (WORKFLOWS_DIR / "execute-plan.md").read_text(encoding="utf-8")

    assert 'verification.status="passed"' in execute_plan
    assert "verification.issue_count=0" in execute_plan
    assert "Do not parse prose such as \"failure language\" to decide batching eligibility." in execute_plan
    assert "omits the typed verification outcome" in execute_plan
    assert "verification-complete` without failure language" not in execute_plan


def test_execute_phase_requires_on_disk_artifacts_before_accepting_success() -> None:
    execute_phase = workflow_authority_text(WORKFLOWS_DIR, "execute-phase")

    assert (
        "If the SUMMARY marks any `key-files.created` / `key-files.modified` paths as required or "
        "final-deliverable, verify those paths on disk before accepting success"
    ) in execute_phase
    assert "Verify first 2 files from `key-files.created` exist on disk" in execute_phase


def test_executor_handoff_recovery_treats_commits_as_partial_evidence_only() -> None:
    quick = workflow_authority_text(WORKFLOWS_DIR, "quick")
    execute_plan = (WORKFLOWS_DIR / "execute-plan.md").read_text(encoding="utf-8")
    execute_phase = workflow_authority_text(WORKFLOWS_DIR, "execute-phase")

    for source in (quick, execute_plan, execute_phase):
        assert "partial evidence" in source
        assert "valid" in source
        assert "gpd apply-return-updates" in source

    assert "Commits or files do not prove success" in quick
    assert "Commits or output files do not prove success" in execute_plan
    assert "Apply the local child artifact gate before success" in execute_phase
    assert "If the return envelope is missing or invalid, keep the child handoff incomplete" in execute_plan
    assert "git commits are partial evidence only" in quick
    assert "git commits are partial evidence only" in execute_plan
    assert "git commits are partial evidence only" in execute_phase


def test_execute_plan_recovery_records_commits_as_partial_evidence_until_return_gate_passes() -> None:
    recovery = (EXECUTION_REFERENCES_DIR / "execute-plan-recovery.md").read_text(encoding="utf-8")

    assert "commits after the checkpoint are partial evidence" in recovery
    assert "Classify completion only after expected artifacts exist" in recovery
    assert "required `gpd_return` envelope validates" in recovery
    assert "required `gpd apply-return-updates` pass has succeeded" in recovery
    assert "Partial Evidence (not yet success)" in recovery
    assert "require retry or explicit main-context fallback" in recovery


def test_execute_phase_fails_closed_on_reverification_and_notation_handoffs() -> None:
    execute_phase = workflow_authority_text(WORKFLOWS_DIR, "execute-phase")

    assert "keeps gap-closure state intact" in execute_phase
    assert "Convention repair is intentionally out-of-line here." in execute_phase
    assert "The next step is `gpd:validate-conventions`" in execute_phase
    assert "fresh `gpd:execute-phase {PHASE_NUMBER}` continuation after that workflow reports a typed result" in (
        execute_phase
    )
