"""Focused assertions for workflow artifact gate hardening."""

from __future__ import annotations

import re
from pathlib import Path

from gpd.core.child_handoff import ChildGateTuple, parse_child_gate_markdown
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"
_YAML_BLOCK_RE = re.compile(r"```ya?ml\n(?P<body>.*?)\n```", re.DOTALL)


def _read(name: str) -> str:
    if name.removesuffix(".md") in {"plan-phase", "verify-work"}:
        return workflow_authority_text(WORKFLOWS_DIR, name)
    return (WORKFLOWS_DIR / name).read_text(encoding="utf-8")


def _child_gate(text: str, gate_id: str) -> ChildGateTuple:
    for match in _YAML_BLOCK_RE.finditer(text):
        body = match.group("body")
        if "child_gate:" not in body:
            continue
        gate = parse_child_gate_markdown(f"```yaml\n{body}\n```")
        if gate.id == gate_id:
            return gate
    raise AssertionError(f"missing child_gate {gate_id}")


def test_plan_phase_requires_plan_artifacts_before_accepting_success() -> None:
    plan_phase = _read("plan-phase.md")
    gate = _child_gate(plan_phase, "planner_initial_plan")

    assert [(artifact.path, artifact.kind) for artifact in gate.expected_artifacts] == [
        ("${PHASE_DIR}/*-PLAN.md", "glob")
    ]
    assert gate.allowed_roots == ("${PHASE_DIR}",)
    assert gate.freshness is not None
    assert gate.freshness.marker == "$PLANNER_HANDOFF_STARTED_AT"
    assert any(
        "gpd validate handoff-artifacts - --expected-glob '${PHASE_DIR}/*-PLAN.md'" in validator
        for validator in gate.validators
    )
    assert "gpd validate plan-contract <each fresh plan>" in gate.validators
    assert "gpd validate plan-preflight <each fresh plan>" in gate.validators
    assert gate.applicator.command == "none"
    assert gate.status_route["checkpoint"] == "fresh planner continuation after user response"
    assert "The shared child artifact gate owns the no-synthetic-child-return rule" in plan_phase
    assert "complete orchestrator-owned fenced YAML `MAIN_CONTEXT_PLAN_RETURN`" in plan_phase


def test_execute_phase_wave_return_artifacts_surface_only_after_executor_gate() -> None:
    wave_return = _read("execute-phase/wave-return-checkpoint.md")
    gate = _child_gate(wave_return, "wave_executor_plan_result")

    assert gate.expected_artifacts[0].path == "${SUMMARY_FILE}"
    assert gate.allowed_roots == ("{phase_dir}",)
    assert gate.freshness is not None
    assert gate.freshness.marker == "$EXECUTOR_HANDOFF_STARTED_AT"
    assert any("--require-files-written" in validator for validator in gate.validators)
    assert any('--fresh-after "$EXECUTOR_HANDOFF_STARTED_AT"' in validator for validator in gate.validators)
    assert "proof-redteam artifact exists and reports status: passed when proof-bearing" in gate.validators
    assert gate.applicator.command == "gpd --raw apply-return-updates ${SUMMARY_FILE}"
    assert gate.applicator.require_passed_true is True

    gate_idx = wave_return.index('id: "wave_executor_plan_result"')
    artifact_idx = wave_return.index("## Artifacts: Wave {N}")
    assert gate_idx < artifact_idx
    assert "Surface artifacts only after the executor gate and applicator have passed." in wave_return
    assert "artifact-surfacing.md` for artifact class definitions and review priority rules." in wave_return
    assert "contract deliverable that is the `subject` of an acceptance test" in wave_return


def test_verify_work_rechecks_proof_redteam_artifact_after_repair() -> None:
    verify_work = _read("verify-work.md")

    assert "After the proof critic returns, re-open `${PHASE_DIR_ABS}/${phase_number}-PROOF-REDTEAM.md` from disk" in verify_work
    assert "confirm the artifact exists and is `passed` after a successful `gpd proof-redteam finalize ...`" in verify_work
    assert "start a fresh proof continuation" in verify_work


def test_validate_conventions_requires_artifact_and_lock_before_success() -> None:
    validate_conventions = _read("validate-conventions.md")

    assert "Runtime delegation rule: this is a one-shot handoff." in validate_conventions
    assert "gpd_return.status: completed" in validate_conventions
    assert "gpd_return.files_written" in validate_conventions
    assert "expected artifact exists on disk" in validate_conventions
    assert "Verify that `GPD/CONVENTIONS.md` exists and that `gpd convention list` reflects the resolved fields before accepting the update." in validate_conventions
    assert "Convention artifact and lock re-verified after notation resolution before success is accepted" in validate_conventions
    assert "Present options, checkpoint, and return." in validate_conventions
