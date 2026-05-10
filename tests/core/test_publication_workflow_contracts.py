from __future__ import annotations

import re
from pathlib import Path

from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"
AGENTS_DIR = REPO_ROOT / "src/gpd/agents"
WRITE_PAPER_STAGE_DIR = WORKFLOWS_DIR / "write-paper"


def _read_write_paper_staged_authorities() -> str:
    stage_names = (
        "paper-bootstrap.md",
        "outline-scaffold.md",
        "authoring.md",
        "consistency-references.md",
        "publication-review-finalization.md",
    )
    return "\n\n".join((WRITE_PAPER_STAGE_DIR / name).read_text(encoding="utf-8") for name in stage_names)


def test_write_paper_balanced_mode_keeps_outline_as_working_draft_and_threads_mode_context() -> None:
    workflow = _read_write_paper_staged_authorities()
    bootstrap_parse_line = next(
        line for line in workflow.splitlines() if line.startswith("Parse bootstrap JSON using")
    )

    assert "paper_bootstrap.required_init_fields" in bootstrap_parse_line
    assert "do not duplicate the manifest's required-field list in prose" in bootstrap_parse_line
    assert "selected_publication_root" not in bootstrap_parse_line
    assert "selected_review_root" not in bootstrap_parse_line
    assert "Do not force a routine outline-approval pause in balanced mode." in workflow
    assert 'WRITE_PAPER_ARGUMENTS="${ARGUMENTS:-}"' in workflow
    assert 'gpd --raw init write-paper --stage paper_bootstrap -- "$WRITE_PAPER_ARGUMENTS"' in workflow
    for stage in (
        "outline_and_scaffold",
        "figure_and_section_authoring",
        "consistency_and_references",
        "publication_review",
    ):
        assert f'gpd --raw init write-paper --stage {stage} -- "${{WRITE_PAPER_ARGUMENTS:-}}"' in workflow
    assert "explicit `--intake path/to/write-paper-authoring-input.json`" in workflow
    assert "For `external_authoring_intake`, use the strict command preflight's managed subject handoff" in workflow
    assert (
        "If `autonomy=supervised`, present the outline for approval before proceeding. "
        "If `autonomy=balanced`, treat the outline as a working draft"
    ) in workflow
    assert "Present outline for approval before proceeding." not in workflow
    assert "<autonomy_mode>{AUTONOMY}</autonomy_mode>" in workflow
    assert "<research_mode>{RESEARCH_MODE}</research_mode>" in workflow
    assert workflow.count("<autonomy_mode>{AUTONOMY}</autonomy_mode>") >= 3
    assert workflow.count("<research_mode>{RESEARCH_MODE}</research_mode>") >= 3
    assert "Treat the emitted `.tex` file as the success artifact gate\nfor each section only after the tuple passes." in workflow
    assert 'id: "write_paper_bibliographer"' in workflow
    assert "Always list `${PAPER_DIR}/CITATION-AUDIT.md` and `GPD/references-status.json` in `gpd_return.files_written`; list `{ACTIVE_BIBLIOGRAPHY_PATH}` only when the bibliography file changed." in workflow
    assert "Confirm `${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json`" in workflow
    assert "exists after the refresh before proceeding to reproducibility or strict review." in workflow
    assert 'id: "write_paper_section_writer"' in workflow
    assert 'id: "write_paper_response_pair"' in workflow
    assert "${selected_publication_root}/AUTHOR-RESPONSE{round_suffix}.md" in workflow
    assert "Embedded `write-paper` review parity for the bounded external-authoring lane is deferred" in workflow
    assert "route the user to standalone `gpd:peer-review`" in workflow
    assert "do not recommend `gpd:arxiv-submission` directly from this lane." in workflow


def test_respond_to_referees_balanced_mode_does_not_force_parse_confirmation() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "respond-to-referees")

    assert "research_mode" in workflow
    assert "RESEARCH_MODE=$(echo \"$INIT\" | gpd json get .research_mode --default balanced)" in workflow
    assert (
        "This workflow is project-aware: it may revise the active manuscript from the current GPD project or an explicit manuscript subject"
        in workflow
    )
    assert "Preferred explicit intake: `gpd:respond-to-referees --manuscript path/to/main.tex --report reviews/ref1.md --report reviews/ref2.md`" in workflow
    assert "Treat a bare positional path as a referee-report source only." in workflow
    assert (
        "Present the parsed structure. Ask for explicit user confirmation only in supervised mode or when the report source is ambiguous; "
        "balanced mode should treat the parse as working context"
    ) in workflow
    assert "Present the parsed structure for user confirmation:" not in workflow
    assert "<autonomy_mode>{AUTONOMY}</autonomy_mode>" in workflow
    assert "<research_mode>{RESEARCH_MODE}</research_mode>" in workflow
    assert "Treat `${RESPONSE_AUTHOR_PATH}` and `${RESPONSE_REFEREE_PATH}` as the response success gate." in workflow
    assert "Use `selected_publication_root` and `selected_review_root` from the target-aware preflight as the response roots." in workflow
    assert 'id: "respond_to_referees_revision_section"' in workflow
    assert "aggregate_child_gate:" in workflow
    assert "Confirm the refreshed JSON artifact exists before treating the round as complete." in workflow
    assert "If the manuscript subject is an explicit external artifact, keep auxiliary response outputs under the selected GPD roots" in workflow


def test_peer_review_stage_six_requires_report_artifacts_and_threads_mode_context() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "peer-review")

    assert "Parse only fields named by `staged_loading.required_init_fields`" in workflow
    assert "peer-review-stage-manifest.json" in workflow
    assert "RESEARCH_MODE=$(echo \"$BOOTSTRAP_INIT\" | gpd json get .research_mode --default balanced)" in workflow
    assert "<autonomy_mode>{AUTONOMY}</autonomy_mode>" in workflow
    assert "<research_mode>{RESEARCH_MODE}</research_mode>" in workflow
    assert "Treat the referee report files as required final-stage artifacts." in workflow
    assert re.search(
        r"confirm `\$\{PUBLICATION_ROOT\}/REFEREE-REPORT\{round_suffix\}\.md` and\s+`\$\{PUBLICATION_ROOT\}/REFEREE-REPORT\{round_suffix\}\.tex` exist before treating the final\s+recommendation as complete",
        workflow,
    )
    assert "${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.md" in workflow
    assert "${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.tex" in workflow
    assert "Stage-review validation alone is not proof-redteam clearance" in workflow
    assert re.search(
        r"same-round\s+`\$\{REVIEW_ROOT\}/PROOF-REDTEAM\{round_suffix\}\.md` clearance plus strict\s+referee-decision validation",
        workflow,
    )


def test_peer_review_panel_child_gates_are_tuple_shaped_and_stage_owned() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "peer-review")

    for gate_id in (
        "peer_review_stage1_reader",
        "peer_review_stage2_literature",
        "peer_review_stage3_math",
        "peer_review_proof_redteam",
        "peer_review_stage4_physics",
        "peer_review_stage5_significance",
        "peer_review_stage6_referee",
    ):
        assert f"{gate_id}" in workflow
    assert re.search(r"Stage identity is\s+callsite-owned", workflow)
    assert re.search(r"never trust a stage label inside\s+`gpd_return`", workflow)
    assert "gpd validate review-claim-index ${REVIEW_ROOT}/CLAIMS{round_suffix}.json" in workflow
    assert "gpd validate proof-redteam ${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md" in workflow
    assert "favorable_decisions_require_same_round_status_passed" in workflow


def test_paper_writer_prompt_supports_bounded_external_authoring_without_workspace_mining() -> None:
    agent = (AGENTS_DIR / "gpd-paper-writer.md").read_text(encoding="utf-8")

    assert "for bounded external authoring, an explicit intake-manifest handoff" in agent
    assert "When the orchestrator says this is `external_authoring_intake`" in agent
    assert "the only supported non-project intake is explicit `--intake path/to/write-paper-authoring-input.json`" in agent
    assert "Do not scan `GPD/phases/*`, `GPD/milestones/*`, `GPD/STATE.md`, or unrelated folders to fill gaps." in agent
    assert "missing evidence bindings are hard blocks" in agent


def test_peer_review_workflow_retires_finished_handoffs_and_clears_transient_state() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "peer-review")

    assert "{GPD_INSTALL_DIR}/references/publication/stage-recovery-gate.md" in workflow
    assert re.search(r"spawned\s+reviewer/proof-auditor/referee lifecycle", workflow)
    assert re.search(r"checkpoint continuation,[\s\S]{0,80}sequential fallback cleanup", workflow)
    assert (
        re.search(r"Each\s+downstream stage begins from persisted artifacts plus the declared\s+carry-forward inputs for that stage", workflow)
    )


def test_peer_review_workflow_requires_barriers_and_cleanup_before_downstream_stage_spawns() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "peer-review")

    assert re.search(
        r"Treat Stage 2, Stage 3, and the conditional proof-critique pass as one barriered\s+review wave under the publication stage-recovery gate",
        workflow,
    )
    assert (
        re.search(
            r"Before Stage 4 can spawn, the branch barrier must pass: every launched child has a\s+typed return, every persisted artifact above exists and validates, and downstream work\s+restarts only from those artifacts plus the declared carry-forward inputs",
            workflow,
        )
    )
    assert re.search(
        r"After `\$\{REVIEW_ROOT\}/STAGE-physics\{round_suffix\}\.json` validates, Stage 5\s+(?:must )?starts?\s+from persisted stage artifacts and declared carry-forward inputs only",
        workflow,
    )
    assert re.search(
        r"After `\$\{REVIEW_ROOT\}/STAGE-interestingness\{round_suffix\}\.json` validates, Stage 6\s+must begin from the persisted stage artifacts and declared carry-forward inputs only",
        workflow,
    )
    assert re.search(
        r"Apply the `peer_review_stage6_referee` tuple and publication stage-recovery gate\s+before classifying the outcome as recovery-eligible, upstream-blocked, or\s+complete",
        workflow,
    )


def test_peer_review_stage_six_limits_writes_to_stage_six_owned_artifacts() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "peer-review")

    assert "Your writable scope is limited to Stage 6-owned adjudication artifacts for this round:" in workflow
    assert "${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json" in workflow
    assert "${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json" in workflow
    assert "${PUBLICATION_ROOT}/CONSISTENCY-REPORT.md" in workflow
    assert "Do not modify `${REVIEW_ROOT}/CLAIMS{round_suffix}.json`, any `${REVIEW_ROOT}/STAGE-*.json`, or `${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md`." in workflow
    assert "any upstream path is a failed handoff" in workflow
    assert "peer_review_stage6_referee" in workflow
    assert "gpd_return.files_written stays within Stage 6 write_allowlist" in workflow
    assert "The Stage 6 tuple write allowlist is report `.md`/`.tex`, ledger, decision, and optional consistency report." in workflow
    assert "any upstream path is a failed handoff" in workflow


def test_peer_review_stage_six_fails_back_to_earliest_upstream_stage_on_inconsistent_inputs() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "peer-review")

    assert re.search(
        r"return `gpd_return.status: blocked` and hand the failure back to the earliest failing\s+upstream stage",
        workflow,
    )
    assert "Do not retry Stage 6 as an upstream repair step." in workflow
    assert "Upstream fail-back table:" in workflow
    assert "`CLAIMS{round_suffix}.json` or `STAGE-reader{round_suffix}.json` -> rerun Stage 1" in workflow
    assert "`STAGE-math{round_suffix}.json` or `PROOF-REDTEAM{round_suffix}.md` -> rerun Stage 3" in workflow
    assert "`STAGE-interestingness{round_suffix}.json` -> rerun Stage 5" in workflow
    assert "earliest failing upstream stage" in workflow
