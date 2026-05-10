"""Assertions for fail-closed proof redteam workflow wiring."""

from __future__ import annotations

from pathlib import Path

from gpd.adapters.install_utils import expand_at_includes
from tests.lifecycle_contract_test_support import (
    assert_forbidden_lifecycle_prose as _assert_absent,
)
from tests.lifecycle_contract_test_support import (
    assert_semantic_contract as _assert_semantic,
)
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"
SPECS_DIR = REPO_ROOT / "src/gpd/specs"
PROOF_GATE_REF = "@{GPD_INSTALL_DIR}/references/verification/core/proof-redteam-workflow-gate.md"
PROOF_GATE_PATH = "{GPD_INSTALL_DIR}/references/verification/core/proof-redteam-workflow-gate.md"
REPEATED_PROOF_CHECKPOINT_LINES = (
    "If the runtime needs user input, return `status: checkpoint` instead of waiting inside this run.",
    "If the runtime needs user input, return `status: checkpoint` instead of waiting inside the spawned run.",
    "Return `status: checkpoint` if the runtime needs user input instead of waiting inside the spawned run.",
    "Return `status: checkpoint` instead of waiting for user input inside this run.",
)


def _read(name: str) -> str:
    return workflow_authority_text(WORKFLOWS_DIR, name)


def _expanded(name: str) -> str:
    return expand_at_includes(_read(name), SPECS_DIR, "/runtime/")


def _peer_review_stage_text(*names: str) -> str:
    stage_names = names or (
        "artifact-discovery.md",
        "panel-stages.md",
        "final-adjudication.md",
    )
    return "\n".join((WORKFLOWS_DIR / "peer-review" / name).read_text(encoding="utf-8") for name in stage_names)


def _expanded_peer_review_stage_text(*names: str) -> str:
    return expand_at_includes(_peer_review_stage_text(*names), SPECS_DIR, "/runtime/")


def test_plan_and_execute_phase_require_proof_redteam_gates() -> None:
    plan_phase = _read("plan-phase.md")
    execute_phase = _read("execute-phase.md")

    assert "## 1.5 Proof-Obligation Planning Gate" in plan_phase
    assert "`--skip-verify` does NOT waive checker review" in plan_phase
    assert "{plan_id}-PROOF-REDTEAM.md" in plan_phase

    assert '<step name="detect_proof_obligation_work">' in execute_phase
    assert PROOF_GATE_REF in execute_phase
    assert "workflow.verifier=false" in execute_phase
    assert "sibling `{plan_id}-PROOF-REDTEAM.md` artifact" in execute_phase
    assert "`gpd-check-proof` is the canonical owner" in execute_phase
    assert 'subagent_type="gpd-check-proof"' in execute_phase
    _assert_semantic(
        execute_phase,
        "execute-phase proof-bearing work still runs proof verification",
        "executed plan",
        "proof-bearing",
        "proof verification still runs",
    )


def test_verification_workflows_fail_closed_on_missing_proof_coverage() -> None:
    verify_phase_raw = _read("verify-phase.md")
    verify_work_raw = _read("verify-work.md")
    derive_equation_raw = _read("derive-equation.md")
    verify_phase = _expanded("verify-phase.md")
    verify_work = _expanded("verify-work.md")
    derive_equation = _expanded("derive-equation.md")

    assert PROOF_GATE_REF not in verify_phase_raw
    assert PROOF_GATE_PATH in verify_phase_raw
    assert PROOF_GATE_REF in verify_work_raw
    assert PROOF_GATE_REF in derive_equation_raw

    _assert_semantic(
        verify_phase,
        "verify-phase proof obligation gate requires theorem audit and adversarial case",
        "theorem-to-proof audit",
        "adversarial special-case",
    )
    assert '<step name="proof_obligation_gate">' in verify_phase
    _assert_semantic(
        verify_phase,
        "verify-phase missing proof coverage is blocking and repair is one-shot",
        "Missing artifact",
        "missing theorem inventory",
        "status != passed",
        "blocking gap",
        "spawn `gpd-check-proof` once",
    )
    _assert_absent(
        verify_phase,
        "verify-phase no inline user waiting for proof repair",
        "wait for user confirmation",
        "ask the user then continue",
        "pause here for approval",
    )

    _assert_semantic(
        verify_work,
        "verify-work proof flags cannot waive canonical artifact",
        "Targeted flags narrow",
        "optional check mix only",
        "canonical `*-PROOF-REDTEAM.md` artifact",
    )
    assert "CHECK_PROOF_MODEL=$(gpd resolve-model gpd-check-proof)" in verify_work
    assert 'task(\n  subagent_type="gpd-check-proof"' in verify_work
    _assert_semantic(verify_work, "verify-work proof floor remains mandatory", "additional mandatory floor applies")

    assert '<step name="proof_obligation_screen">' in derive_equation
    assert "DERIVATION-{slug}-PROOF-REDTEAM.md" in derive_equation
    assert "gpd-check-proof" in derive_equation
    assert "CHECK_PROOF_MODEL=$(gpd resolve-model gpd-check-proof)" in derive_equation
    assert 'task(\n  subagent_type="gpd-check-proof"' in derive_equation
    _assert_semantic(
        derive_equation,
        "derive-equation proof-bearing derivations fail closed",
        "Proof-bearing derivations",
        "fail closed",
    )


def test_proof_redteam_handoffs_delegate_checkpoint_semantics_to_shared_contracts() -> None:
    workflow_names = ("derive-equation.md", "execute-phase.md", "verify-phase.md", "verify-work.md")

    combined = "\n".join((*(_read(name) for name in workflow_names), _peer_review_stage_text("panel-stages.md")))

    _assert_absent(
        combined,
        "proof-redteam handoffs use shared checkpoint semantics",
        *REPEATED_PROOF_CHECKPOINT_LINES,
    )

    assert combined.count("proof-redteam protocol's one-shot return semantics") == 3
    assert combined.count("typed proof-redteam handoff contract") == 2
    assert "shared verification child-return contract" in combined


def test_quick_publication_and_settings_surfaces_block_proof_bypass() -> None:
    quick = _read("quick.md")
    write_paper = _read("write-paper.md")
    peer_review = _expanded_peer_review_stage_text()
    peer_review_raw = _peer_review_stage_text()
    settings = _read("settings.md")

    _assert_semantic(
        quick,
        "quick blocks proof obligation bypass",
        "Quick mode",
        "NOT authorized",
        "theorem-style",
        "proof_obligation",
        "blocked pending the full proof-redteam workflow",
    )

    assert "proof-obligation coverage" in write_paper
    assert "GPD/review/PROOF-REDTEAM{round_suffix}.md" in write_paper
    _assert_semantic(
        write_paper,
        "write-paper cannot smooth beyond proof-redteam scope",
        "must not strengthen",
        "generalize",
        "rhetorically smooth",
        "theorem-style claims",
        "passed proof-redteam scope",
    )

    assert "<proof_bearing_routing>" in peer_review
    assert PROOF_GATE_PATH not in peer_review_raw
    assert "references/verification/core/proof-redteam-workflow-gate.md" in (
        WORKFLOWS_DIR / "peer-review-stage-manifest.json"
    ).read_text(encoding="utf-8")
    assert "${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md" in peer_review
    assert "gpd-check-proof" in peer_review
    assert "may be running in parallel" in peer_review
    assert "do not wait on that" in peer_review
    assert "artifact to begin the math review" in peer_review
    assert "expect a sibling `GPD/review/PROOF-REDTEAM{round_suffix}.md` artifact" not in peer_review
    assert "Recommendation floor: `major_revision` or `reject`." in peer_review

    assert "this does NOT disable mandatory proof red-teaming" in settings
    assert "Sparse cadence does not waive proof red-teaming" in settings


def test_peer_review_final_decision_guardrail_requires_same_round_proof_redteam() -> None:
    peer_review = _expanded_peer_review_stage_text("panel-stages.md", "final-adjudication.md")
    reliability = (SPECS_DIR / "references/publication/peer-review-reliability.md").read_text(encoding="utf-8")

    assert (
        "wrong-round, wrong-root, or non-passing same-round `${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md` "
        "artifact prevents any favorable recommendation" in peer_review
    )
    assert "Stage-review validation alone is not proof-redteam clearance" in peer_review
    assert "aligned `proof_audits[]` entries in `${REVIEW_ROOT}/STAGE-math{round_suffix}.json`" in peer_review
    assert (
        "do not by themselves clear a favorable final decision without the same-round proof-redteam artifact"
        in peer_review
    )
    assert (
        "gpd validate referee-decision ${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json --strict "
        "--ledger ${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json" in peer_review
    )
    assert "this strict final-decision validator is the favorable-decision guardrail" in peer_review

    assert "same selected review root as the round artifacts" in reliability
    assert "stage-review validation alone does not clear same-round proof-redteam policy" in reliability


def test_proof_obligation_detection_distinguishes_generic_manuscript_claims() -> None:
    proof_gate = (SPECS_DIR / "references/verification/core/proof-redteam-workflow-gate.md").read_text(encoding="utf-8")
    quick = _read("quick.md")
    peer_review = _expanded_peer_review_stage_text("artifact-discovery.md")

    assert (
        "ProjectContract` vocabulary such as `claim_kind: theorem | lemma | corollary | proposition | claim`"
        in proof_gate
    )
    assert "A generic manuscript claim" in proof_gate
    assert "the bare word `claim` is not proof-bearing by itself" in proof_gate
    assert (
        "Require theorem/proof/formal metadata before routing generic manuscript claims through proof-redteam."
        in proof_gate
    )

    assert "ProjectContract `claim_kind: claim`" in quick
    assert 'A generic manuscript or task "claim" is not enough by itself.' in quick
    assert "Paper `ClaimRecord.claim_kind: claim`" in peer_review
