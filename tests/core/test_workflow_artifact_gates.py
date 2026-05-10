"""Focused assertions for workflow artifact gate hardening."""

from __future__ import annotations

import re
from pathlib import Path

from gpd.core.child_handoff import ChildGateTuple, parse_child_gate_markdown
from tests.assertion_taxonomy_support import MatchMode, assert_prompt_contracts, semantic_anchor
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


def _assert_semantic(text: str, label: str, *fragments: str) -> None:
    assert_prompt_contracts(
        text,
        semantic_anchor(label, fragments, match=MatchMode.CASEFOLD_NORMALIZED, context=label),
    )


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
    _assert_semantic(
        plan_phase,
        "plan-phase orchestrator return handoff",
        "MAIN_CONTEXT_PLAN_RETURN",
        "fenced YAML",
    )


def test_execute_phase_wave_return_artifacts_surface_only_after_executor_gate() -> None:
    wave_return = _read("execute-phase/wave-return-checkpoint.md")
    gate = _child_gate(wave_return, "wave_executor_plan_result")

    assert gate.expected_artifacts[0].path == "${SUMMARY_FILE}"
    assert gate.allowed_roots == ("{phase_dir}",)
    assert gate.freshness is not None
    assert gate.freshness.marker == "$EXECUTOR_HANDOFF_STARTED_AT"
    assert any("--require-files-written" in validator for validator in gate.validators)
    assert any('--fresh-after "$EXECUTOR_HANDOFF_STARTED_AT"' in validator for validator in gate.validators)
    assert any(
        all(fragment in validator for fragment in ("proof-redteam artifact", "status: passed", "proof-bearing"))
        for validator in gate.validators
    )
    assert gate.applicator.command == "gpd --raw apply-return-updates ${SUMMARY_FILE}"
    assert gate.applicator.require_passed_true is True

    gate_idx = wave_return.index('id: "wave_executor_plan_result"')
    artifact_idx = wave_return.index("## Artifacts: Wave {N}")
    assert gate_idx < artifact_idx
    _assert_semantic(
        wave_return,
        "execute-phase artifact surfacing order",
        "artifacts only after",
        "executor gate",
        "applicator",
    )
    _assert_semantic(
        wave_return,
        "execute-phase artifact surfacing authority",
        "artifact-surfacing.md",
        "artifact class",
        "review priority",
    )
    _assert_semantic(
        wave_return,
        "execute-phase acceptance-test subject artifact",
        "contract deliverable",
        "subject",
        "acceptance test",
    )


def test_verify_work_rechecks_proof_redteam_artifact_after_repair() -> None:
    verify_work = _read("verify-work.md")
    gate = _child_gate(verify_work, "verify_work_proof_critic")

    assert gate.expected_artifacts[0].path == "${PHASE_DIR_ABS}/${phase_number}-PROOF-REDTEAM.md"
    assert gate.freshness is not None
    assert gate.freshness.marker == "$PROOF_HANDOFF_STARTED_AT"
    assert gate.status_route["blocked"] == "fresh proof continuation or fail closed"
    assert {
        "gpd proof-redteam finalize ... when producing passed audits",
        "gpd validate proof-redteam ${PHASE_DIR_ABS}/${phase_number}-PROOF-REDTEAM.md",
        "frontmatter status: passed before finalizing the gap ledger",
    }.issubset(set(gate.validators))
    _assert_semantic(
        verify_work,
        "verify-work proof artifact reopening",
        "${PHASE_DIR_ABS}/${phase_number}-PROOF-REDTEAM.md",
        "gpd proof-redteam finalize",
        "gpd validate proof-redteam",
    )
    _assert_semantic(verify_work, "verify-work fresh proof continuation", "fresh proof continuation")


def test_validate_conventions_requires_artifact_and_lock_before_success() -> None:
    validate_conventions = _read("validate-conventions.md")

    _assert_semantic(validate_conventions, "validate-conventions one-shot delegation", "one-shot handoff")
    assert "gpd_return.status: completed" in validate_conventions
    assert "gpd_return.files_written" in validate_conventions
    _assert_semantic(validate_conventions, "validate-conventions disk artifact gate", "expected artifact", "disk")
    _assert_semantic(
        validate_conventions,
        "validate-conventions convention artifact and lock",
        "GPD/CONVENTIONS.md",
        "gpd convention list",
        "accepting the update",
    )
    _assert_semantic(
        validate_conventions,
        "validate-conventions artifact and lock verification",
        "Convention artifact",
        "lock",
        "before success",
    )
    _assert_semantic(validate_conventions, "validate-conventions checkpoint return", "options", "checkpoint", "return")
