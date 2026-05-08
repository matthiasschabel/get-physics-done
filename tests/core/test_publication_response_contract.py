from __future__ import annotations

import re
from pathlib import Path

from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCES_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "references" / "publication"
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
AGENTS_DIR = REPO_ROOT / "src" / "gpd" / "agents"


def _workflow_authority(name: str) -> str:
    return workflow_authority_text(WORKFLOWS_DIR, name)


def test_publication_bootstrap_preflight_defines_the_shared_publication_gate() -> None:
    source = (REFERENCES_DIR / "publication-bootstrap-preflight.md").read_text(encoding="utf-8")

    assert "Canonical workflow-facing bootstrap and preflight reference for publication tasks." in source
    assert "publication-manuscript-root-preflight.md" in source
    assert "publication-review-round-artifacts.md" in source
    assert "publication-response-artifacts.md" in source
    assert "publication-artifact-gates.md" not in source


def test_publication_response_writer_handoff_defines_one_shot_child_returns() -> None:
    source = (REFERENCES_DIR / "publication-response-writer-handoff.md").read_text(encoding="utf-8")
    recovery = (REFERENCES_DIR / "stage-recovery-gate.md").read_text(encoding="utf-8")

    assert "Canonical workflow-facing handoff and completion reference for spawned response-writing work." in source
    assert "stage-recovery-gate.md" in source
    assert "Apply the publication stage-recovery gate for one-shot writer lifecycle" in source
    assert "Treat every spawned publication child as one-shot." in recovery
    assert "For `checkpoint`, stop that child and resume only by spawning a fresh continuation" in recovery
    assert (
        "`status: completed` is provisional until the expected response files exist on disk and are named in fresh typed `gpd_return.files_written`."
        in source
    )
    assert "status: checkpoint" in source
    assert "gpd_return.files_written" in source
    assert "${selected_publication_root}/AUTHOR-RESPONSE{round_suffix}.md" in source
    assert "${selected_review_root}/REFEREE_RESPONSE{round_suffix}.md" in source
    assert "default project subjects resolve those to `GPD/AUTHOR-RESPONSE{round_suffix}.md`" in source
    assert "Do not treat prose-only status messages as proof of completion." in source
    assert "stale same-round files without a binding do not complete the handoff" in source
    assert "Do not accept stale preexisting files as proof of current-run completion." in recovery
    assert "publication-artifact-gates.md" not in source


def test_publication_review_wrapper_guidance_points_to_the_new_shared_refs() -> None:
    source = (REFERENCES_DIR / "publication-review-wrapper-guidance.md").read_text(encoding="utf-8")

    assert "publication-bootstrap-preflight.md" in source
    assert "publication-response-writer-handoff.md" in source
    assert "publication-artifact-gates.md" not in source


def test_publication_review_round_artifacts_define_canonical_round_family() -> None:
    source = (REFERENCES_DIR / "publication-review-round-artifacts.md").read_text(encoding="utf-8")

    assert "Canonical round-suffix and sibling-artifact contract for publication review rounds." in source
    assert "Round 1 uses `round_suffix=\"\"`." in source
    assert "Round `N` for `N >= 2` uses `round_suffix=\"-R{N}\"`." in source
    assert "${selected_publication_root}/REFEREE-REPORT{round_suffix}.md" in source
    assert "${selected_review_root}/REVIEW-LEDGER{round_suffix}.json" in source
    assert "${selected_review_root}/REFEREE-DECISION{round_suffix}.json" in source
    assert "${selected_publication_root}/AUTHOR-RESPONSE{round_suffix}.md" in source
    assert "${selected_review_root}/REFEREE_RESPONSE{round_suffix}.md" in source
    assert "${selected_review_root}/PROOF-REDTEAM{round_suffix}.md" in source
    assert "default project-backed canonical layout" in source
    assert "subject-owned publication root `GPD/publication/{subject_slug}`" in source
    assert "does not by itself promise a full relocation" in source
    assert "review-round-artifact-contract.md" not in source
    assert "publication-artifact-gates.md" not in source


def test_publication_final_adjudication_boundary_preserves_stage_six_guards() -> None:
    source = (REFERENCES_DIR / "publication-final-adjudication-boundary.md").read_text(encoding="utf-8")
    referee = (AGENTS_DIR / "gpd-referee.md").read_text(encoding="utf-8")

    assert "Compact Stage 6 reference for the final `gpd-referee` adjudication pass." in source
    assert "the workflow callsite and referee prompt must still keep the local write allowlist" in source
    assert "selected_publication_root" in source
    assert "selected_review_root" in source
    assert "round_suffix" in source
    assert "${selected_publication_root}/REFEREE-REPORT{round_suffix}.md" in source
    assert "${selected_publication_root}/REFEREE-REPORT{round_suffix}.tex" in source
    assert "${selected_review_root}/REVIEW-LEDGER{round_suffix}.json" in source
    assert "${selected_review_root}/REFEREE-DECISION{round_suffix}.json" in source
    assert "${selected_publication_root}/CONSISTENCY-REPORT.md" in source
    assert "${selected_review_root}/CLAIMS{round_suffix}.json" in source
    assert "any `${selected_review_root}/STAGE-*.json`" in source
    assert "${selected_review_root}/PROOF-REDTEAM{round_suffix}.md" in source
    assert "gpd validate review-ledger ${selected_review_root}/REVIEW-LEDGER{round_suffix}.json" in source
    assert (
        "gpd validate referee-decision ${selected_review_root}/REFEREE-DECISION{round_suffix}.json --strict "
        "--ledger ${selected_review_root}/REVIEW-LEDGER{round_suffix}.json"
    ) in source
    assert "Stage-review validation alone is not proof-redteam clearance." in source
    assert "publication-final-adjudication-boundary.md" in referee
    assert "During the staged peer-review workflow, Stage 6 is read-only" in referee
    assert "Stage 6 writable allowlist" in referee


def test_publication_response_artifacts_define_paired_completion_gate() -> None:
    source = (REFERENCES_DIR / "publication-response-artifacts.md").read_text(encoding="utf-8")

    assert "Canonical paired response-artifact and one-shot child-return contract for referee-response work." in source
    assert "stage-recovery-gate.md" in source
    assert "spawned writer lifecycle, checkpoint continuation, and stale-output rejection" in source
    assert (
        "A reported `status: completed` is provisional until the response pair exists on disk and those same fresh paths appear in typed `gpd_return.files_written`."
        in source
    )
    assert "${selected_publication_root}/AUTHOR-RESPONSE{round_suffix}.md" in source
    assert "${selected_review_root}/REFEREE_RESPONSE{round_suffix}.md" in source
    assert "Treat the two files as one success gate" in source
    assert "do not mark the round complete when only one of them is current" in source
    assert "Successful response-round completion requires both" in source
    assert "status: checkpoint" in source
    assert "gpd_return.files_written" in source
    assert "stale-output handling comes from the stage-recovery gate" in source
    assert "Project-backed response rounds resolve `selected_publication_root=GPD`" in source
    assert "same paired response artifacts bind under the subject-owned" in source
    assert "response_to: REFEREE-REPORT{round_suffix}.md" in source
    assert "manuscript_path: path/to/active-manuscript.tex" in source
    assert "missing or mismatched response frontmatter as incomplete" in source
    assert "does not imply a full relocation" in source
    assert "response-artifact-contract.md" not in source
    assert "publication-artifact-gates.md" not in source


def test_response_templates_include_explicit_subject_binding_frontmatter() -> None:
    templates_dir = REPO_ROOT / "src/gpd/specs/templates/paper"

    for template_name in ("author-response.md", "referee-response.md"):
        source = (templates_dir / template_name).read_text(encoding="utf-8")
        assert "response_to: REFEREE-REPORT{round_suffix}.md" in source
        assert "round: {N}" in source
        assert "manuscript_path: {path/to/active-manuscript.tex}" in source
        assert "review_ledger: ${selected_review_root}/REVIEW-LEDGER{round_suffix}.json" in source
        assert "referee_decision: ${selected_review_root}/REFEREE-DECISION{round_suffix}.json" in source


def test_referee_revision_mode_requires_a_paired_response_package() -> None:
    referee = (AGENTS_DIR / "gpd-referee.md").read_text(encoding="utf-8")

    assert "paired response package" in referee
    assert "${selected_publication_root}/AUTHOR-RESPONSE.md" in referee
    assert "${selected_publication_root}/AUTHOR-RESPONSE-R{N}.md" in referee
    assert "${selected_review_root}/REFEREE_RESPONSE.md" in referee
    assert "${selected_review_root}/REFEREE_RESPONSE-R{N}.md" in referee
    assert "Do not infer revision state by scanning global `GPD/` filenames." in referee
    assert "suffixes disagree" in referee
    assert "incomplete response package" in referee


def test_paper_writer_and_referee_load_the_canonical_publication_response_contracts() -> None:
    paper_writer = (AGENTS_DIR / "gpd-paper-writer.md").read_text(encoding="utf-8")
    referee = (AGENTS_DIR / "gpd-referee.md").read_text(encoding="utf-8")
    write_paper = _workflow_authority("write-paper")
    respond = (WORKFLOWS_DIR / "respond-to-referees.md").read_text(encoding="utf-8")

    for source in (paper_writer, referee):
        assert "publication-artifact-gates.md" not in source
        assert "response-artifact-contract.md" not in source
        assert "review-round-artifact-contract.md" not in source

    assert "publication-response-writer-handoff.md" in paper_writer
    assert "publication-response-artifacts.md" not in paper_writer
    assert "publication-review-round-artifacts.md" not in paper_writer
    assert "publication-response-artifacts.md" in referee
    assert "publication-review-round-artifacts.md" in referee
    assert "fixed" in paper_writer and "on disk" in paper_writer
    assert "fixed" in referee and "on disk" in referee
    assert "gpd_return.files_written" in write_paper
    assert "gpd validate handoff-artifacts for both response paths" in write_paper
    assert "publication-response-writer-handoff.md frontmatter, round, and manuscript binding" in write_paper
    assert "publication-bootstrap-preflight.md" in write_paper
    assert "publication-response-writer-handoff.md" in write_paper
    assert "publication-bootstrap-preflight.md" in respond
    assert "publication-response-writer-handoff.md" in respond
    assert "selected_publication_root` / `selected_review_root" in respond
    assert "publication-response-artifacts.md" not in write_paper
    assert "publication-response-artifacts.md" not in respond
    assert "fresh child handoff and named in current-run `files_written` / `gpd_return.files_written`" in respond
    assert "gpd validate handoff-artifacts for revised section plus both response artifacts" in respond


def test_peer_review_stage_six_requires_fresh_referee_return_and_artifacts() -> None:
    workflow = _workflow_authority("peer-review")

    assert "child_gate tuple" in workflow
    assert "peer_review_stage6_referee" in workflow
    assert re.search(r"required_status:\s+[\"']?completed", workflow)
    assert "stage-recovery-gate.md" in workflow
    assert "checkpoint continuation" in workflow
    assert "gpd_return.files_written stays within Stage 6 write_allowlist" in workflow


def test_peer_review_parallel_wave_stops_terminal_children_before_stage_4() -> None:
    workflow = _workflow_authority("peer-review")

    assert "If the runtime supports parallel subagent execution" in workflow
    assert "conditional proof-critique pass in parallel when theorem-bearing claims are present" in workflow
    assert re.search(r"If literature, math, or the conditional proof-critique stage fails[\s\S]{0,80}STOP", workflow)
    assert "Treat Stage 2, Stage 3, and the conditional proof-critique pass as one barriered" in workflow
    assert "retry only the failed tuple once under the stage-recovery gate" in workflow
    assert "Before Stage 4 can spawn, the branch barrier must pass" in workflow
    assert re.search(
        r"If the proof-redteam artifact is missing, malformed,[\s\S]{0,90}retry `gpd-check-proof` once with the same inputs",
        workflow,
    )
    assert re.search(r"If the retry also fails, STOP the pipeline[\s\S]{0,80}proof review could not\s+be completed", workflow)


def test_peer_review_later_stages_restart_from_fresh_context_and_written_artifacts() -> None:
    workflow = _workflow_authority("peer-review")

    assert "Stage 4 checks physical soundness" in workflow
    assert "Stage 5 judges interestingness and venue fit" in workflow
    assert "${REVIEW_ROOT}/STAGE-math{round_suffix}.json" in workflow
    assert "${REVIEW_ROOT}/STAGE-literature{round_suffix}.json" in workflow
    assert "${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md` if proof-bearing review is active" in workflow
    assert "${REVIEW_ROOT}/STAGE-physics{round_suffix}.json" in workflow
    assert "Validate before proceeding:" in workflow
    assert re.search(r"do not\s+proceed to Stage 5", workflow)
    assert "Validate before Stage 6:" in workflow


def test_referee_stage_six_files_written_must_be_fresh_current_run_outputs() -> None:
    referee = (AGENTS_DIR / "gpd-referee.md").read_text(encoding="utf-8")

    assert "Preexisting files are stale unless the same paths appear in fresh `gpd_return.files_written` from this run." in referee
    assert "For all statuses, `files_written` must list only files actually written in this run from the Stage 6 allowlist." in referee
    assert (
        "For `blocked` returns caused by upstream staged-review artifact failures, keep `files_written` empty "
        "unless you wrote only `${selected_publication_root}/CONSISTENCY-REPORT.md`."
    ) in referee


def test_referee_stage_six_write_allowlist_stops_before_upstream_repairs() -> None:
    referee = (AGENTS_DIR / "gpd-referee.md").read_text(encoding="utf-8")

    assert "Stage 6 writable allowlist" in referee
    assert "${selected_publication_root}/REFEREE-REPORT{round_suffix}.md" in referee
    assert "${selected_publication_root}/REFEREE-REPORT{round_suffix}.tex" in referee
    assert "${selected_review_root}/REVIEW-LEDGER{round_suffix}.json" in referee
    assert "${selected_review_root}/REFEREE-DECISION{round_suffix}.json" in referee
    assert "${selected_publication_root}/CONSISTENCY-REPORT.md" in referee
    assert "never rewrite `${selected_review_root}/CLAIMS{round_suffix}.json`" in referee
    assert "any `${selected_review_root}/STAGE-*.json`" in referee
    assert "`${selected_review_root}/PROOF-REDTEAM{round_suffix}.md`" in referee
    assert (
        "If an upstream staged-review artifact is missing, malformed, stale, suffix-inconsistent, "
        "manuscript-inconsistent, or mutually inconsistent, return `gpd_return.status: blocked`"
    ) in referee


def test_stage_six_handoff_closure_and_retry_freshness_remain_explicit() -> None:
    workflow = _workflow_authority("peer-review")
    referee = (AGENTS_DIR / "gpd-referee.md").read_text(encoding="utf-8")

    assert "Do not trust the referee's success text until that typed return, the on-disk files, and the validators all agree." in workflow
    assert "gpd_return.files_written stays within Stage 6 write_allowlist" in workflow
    assert "Only retry Stage 6 for Stage 6-owned artifact failures" in workflow
    assert "Do not retry Stage 6 as an upstream repair step." in workflow
    assert "If the eligible Stage 6 retry also fails" in workflow
    assert "do not proceed to report summarization" in workflow
    assert "Checkpoint ownership is orchestrator-side: when you stop, the orchestrator presents the issue and owns the fresh continuation handoff." in referee
    assert (
        "`gpd_return.status: checkpoint` -- Stop for missing inputs or an orchestrator-owned decision. Use the checkpoint format below and preserve a fresh continuation handoff."
        in referee
    )
    assert (
        "`gpd_return.status: completed` -- Final review finished. Write the full report plus any decision/ledger artifacts produced in this run, and treat completion as valid only when the fresh `gpd_return.files_written` names only Stage 6-owned artifacts from this run and they exist on disk."
        in referee
    )
