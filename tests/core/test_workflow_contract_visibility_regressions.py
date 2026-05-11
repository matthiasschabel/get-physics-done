from __future__ import annotations

import re
from pathlib import Path

import pytest

from gpd.adapters.install_utils import expand_at_includes
from gpd.core.public_surface_contract import resume_authority_fields
from gpd.core.workflow_staging import load_workflow_stage_manifest
from tests.doc_surface_contracts import resume_authority_public_vocabulary_intro, resume_backend_only_fields
from tests.lifecycle_contract_test_support import assert_semantic_contract as _assert_semantic
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"
COMMANDS_DIR = REPO_ROOT / "src/gpd/commands"
ORCHESTRATION_REFS_DIR = REPO_ROOT / "src/gpd/specs/references/orchestration"
BLOCKED_LIFECYCLE_STOP_PROHIBITION = (
    "Do not plan, execute, verify, fingerprint, align, or pass `project_contract` to subagents"
)


def _workflow_text(name: str) -> str:
    return workflow_authority_text(WORKFLOWS_DIR, name)


def test_contract_authority_gate_reference_defines_shared_boundary() -> None:
    reference = (ORCHESTRATION_REFS_DIR / "contract-authority-gate.md").read_text(encoding="utf-8")

    assert "project_contract_gate.authoritative" in reference
    _assert_semantic(
        reference,
        "contract authority gate diagnostic-only lifecycle boundary",
        "diagnostic context",
        "not planning, execution, verification",
        "lifecycle preflight",
        "stop fail-closed",
        "do not infer approved scope",
        "local workflow still owns",
        "artifacts",
        "validators",
        "failure route",
    )
    assert "## Blocked Lifecycle Stop Phrase" in reference
    assert BLOCKED_LIFECYCLE_STOP_PROHIBITION in reference
    assert "references/orchestration/stage-stop-envelope.md" in reference
    _assert_semantic(
        reference,
        "contract authority gate owns repair rerun command",
        "owning workflow",
        "rerun command",
        "after repair",
    )


def _assert_contract_gate_stop_tuple(
    workflow: str,
    *,
    workflow_id: str,
    stage_id: str,
    after_repair: str,
    triggers: tuple[str, ...],
) -> None:
    stop_tuple = next(
        line
        for line in workflow.splitlines()
        if "contract_gate_stop:" in line and f"workflow={workflow_id}" in line
    )
    assert f"stage={stage_id}" in stop_tuple
    assert "status=blocked" in stop_tuple
    assert "checkpoint=contract_gate" in stop_tuple
    assert "primary=gpd:sync-state|gpd:new-project" in stop_tuple
    assert f"rerun={after_repair}" in stop_tuple
    assert "secondary=gpd:suggest-next" in stop_tuple
    for trigger in triggers:
        assert trigger in stop_tuple or trigger in workflow


def test_owned_contract_visibility_workflows_load_shared_authority_gate_once() -> None:
    include = "`{GPD_INSTALL_DIR}/references/orchestration/contract-authority-gate.md`"
    for workflow_name in (
        "audit-milestone.md",
        "new-milestone.md",
        "literature-review.md",
        "map-research.md",
        "compare-results.md",
        "compare-experiment.md",
    ):
        assert _workflow_text(workflow_name).count(include) == 1


@pytest.mark.parametrize(
    ("workflow_name", "surface_marker", "expected_token", "authoritative_marker", "stage_id"),
    [
        (
            "plan-phase.md",
            "gpd --raw stage field-access plan-phase --stage phase_bootstrap --style instruction",
            "project_contract_gate",
            "project_contract_gate.authoritative",
            "phase_bootstrap",
        ),
        (
            "execute-phase.md",
            "gpd --raw stage field-access execute-phase --stage phase_bootstrap --style instruction",
            "project_contract_gate",
            "non-authoritative `project_contract_gate`",
            "phase_bootstrap",
        ),
        ("execute-plan.md", "Extract from init JSON:", "project_contract_gate", "project_contract_gate.authoritative", None),
        ("compare-experiment.md", "Parse JSON for:", "project_contract_gate", "project_contract_gate.authoritative", None),
        ("compare-results.md", "Parse JSON for:", "project_contract_gate", "project_contract_gate.authoritative", None),
        (
            "new-project.md",
            "Parse only fields named by `staged_loading.required_init_fields`",
            "project_contract_gate",
            "project_contract_gate.authoritative",
            "scope_intake",
        ),
        ("progress.md", "Extract from init JSON:", "project_contract_gate", "project_contract_gate.authoritative", None),
        ("audit-milestone.md", "Extract from init JSON:", "project_contract_gate", "project_contract_gate.authoritative", None),
        (
            "resume-work.md",
            "- **Availability and contract authority:**",
            "project_contract_gate",
            "project_contract_gate.authoritative",
            None,
        ),
        ("write-paper.md", "Parse bootstrap JSON using", "project_contract_gate", "project_contract_gate.authoritative", None),
        (
            "respond-to-referees.md",
            "Use `INIT.staged_loading.required_init_fields` as the bootstrap contract",
            "project_contract_gate",
            "project_contract_gate.authoritative",
            "bootstrap",
        ),
        (
            "peer-review.md",
            "Parse only fields named by `staged_loading.required_init_fields`",
            "project_contract_gate",
            "project_contract_gate.authoritative",
            "bootstrap",
        ),
    ],
)
def test_contract_gate_is_visible_before_authoritative_use(
    workflow_name: str,
    surface_marker: str,
    expected_token: str,
    authoritative_marker: str,
    stage_id: str | None,
) -> None:
    workflow = _workflow_text(workflow_name)
    surface_line = next(line for line in workflow.splitlines() if surface_marker in line)

    if stage_id is None:
        assert expected_token in surface_line
    else:
        workflow_id = workflow_name.removesuffix(".md")
        assert expected_token in load_workflow_stage_manifest(workflow_id).stage(stage_id).required_init_fields
    assert workflow.index(surface_line) < workflow.index(authoritative_marker)


@pytest.mark.parametrize(
    ("workflow_id", "stage_id"),
    [
        ("quick", "task_bootstrap"),
        ("literature-review", "review_bootstrap"),
        ("new-milestone", "milestone_bootstrap"),
        ("map-research", "map_bootstrap"),
    ],
)
def test_manifest_owned_contract_gate_is_visible_before_authoritative_use(
    workflow_id: str,
    stage_id: str,
) -> None:
    workflow = _workflow_text(f"{workflow_id}.md")
    manifest = load_workflow_stage_manifest(workflow_id)
    helper_line = next(
        line
        for line in workflow.splitlines()
        if f"gpd --raw stage field-access {workflow_id} --stage {stage_id} --style instruction" in line
    )

    assert "project_contract_gate" in manifest.stage(stage_id).required_init_fields
    assert workflow.index(helper_line) < workflow.index("project_contract_gate.authoritative")


def test_literature_review_workflow_surfaces_contract_gate_before_deferred_reference_artifacts() -> None:
    workflow = _workflow_text("literature-review.md")
    manifest = load_workflow_stage_manifest("literature-review")
    surface_line = next(
        line
        for line in workflow.splitlines()
        if "gpd --raw stage field-access literature-review --stage review_bootstrap --style instruction" in line
    )

    assert "project_contract_gate" in manifest.stage("review_bootstrap").required_init_fields
    assert workflow.index(surface_line) < workflow.index("project_contract_gate.authoritative")
    assert workflow.index(surface_line) < workflow.index(
        "Do not use `reference_artifact_files` or `reference_artifacts_content` yet."
    )


@pytest.mark.parametrize(
    (
        "workflow_name",
        "workflow_id",
        "stage_id",
        "after_repair",
        "triggers",
        "gate_command",
        "first_forbidden_marker",
        "stop_line",
    ),
    [
        (
            "plan-phase.md",
            "plan-phase",
            "phase_bootstrap",
            "gpd:plan-phase {PHASE}",
            (
                "project_contract_load_info.status starts with blocked",
                "project_contract is empty or null",
                "project_contract_validation.valid is false",
                "project_contract_gate.authoritative is not true",
            ),
            "gpd --raw validate lifecycle-contract-gate plan-phase",
            "### Spawn gpd-phase-researcher",
            "project_contract_gate.authoritative is not true",
        ),
        (
            "execute-phase.md",
            "execute-phase",
            "phase_bootstrap",
            "gpd:execute-phase ${PHASE_ARG}",
            (
                "blocked contract load",
                "invalid contract validation",
                "non-authoritative `project_contract_gate`",
            ),
            "gpd --raw validate lifecycle-contract-gate execute-phase",
            '<step name="handle_branching">',
            "non-authoritative `project_contract_gate`",
        ),
        (
            "verify-work.md",
            "verify-work",
            "session_router",
            "gpd:verify-work ${PHASE_ARG}",
            (
                "contract load is blocked",
                "validation is invalid",
                "`project_contract_gate.authoritative` is not true",
            ),
            "gpd --raw validate lifecycle-contract-gate verify-work",
            "gpd-check-proof",
            "`project_contract_gate.authoritative` is not true",
        ),
    ],
)
def test_lifecycle_workflows_stop_on_non_authoritative_project_contract_gate(
    workflow_name: str,
    workflow_id: str,
    stage_id: str,
    after_repair: str,
    triggers: tuple[str, ...],
    gate_command: str,
    first_forbidden_marker: str,
    stop_line: str,
) -> None:
    workflow = _workflow_text(workflow_name)

    assert stop_line in workflow
    assert BLOCKED_LIFECYCLE_STOP_PROHIBITION not in workflow
    _assert_contract_gate_stop_tuple(
        workflow,
        workflow_id=workflow_id,
        stage_id=stage_id,
        after_repair=after_repair,
        triggers=triggers,
    )
    assert gate_command in workflow
    assert workflow.index(stop_line) < workflow.index(first_forbidden_marker)
    assert workflow.index(gate_command) < workflow.index(first_forbidden_marker)


def test_plan_phase_dirty_gate_stops_before_contract_and_authoring_surfaces() -> None:
    workflow = _workflow_text("plan-phase.md")

    assert "**Dirty worktree safety gate:**" in workflow
    assert "If it is dirty, halt before planning" in workflow
    assert "**If `project_contract_load_info.status` starts with `blocked`" in workflow
    assert 'INIT=$(gpd --raw init plan-phase "$PHASE" --stage planner_authoring)' in workflow

    dirty_gate = workflow.index("**Dirty worktree safety gate:**")
    dirty_stop = workflow.index("If it is dirty, halt before planning")
    contract_stop = workflow.index("**If `project_contract_load_info.status` starts with `blocked`")
    first_authoring_reload = workflow.index('INIT=$(gpd --raw init plan-phase "$PHASE" --stage planner_authoring)')

    _assert_semantic(
        workflow,
        "plan-phase dirty gate stops before hiding user work",
        "inspect only the project worktree",
        "show dirty paths",
        "git status --short",
        "gpd commit",
        "project-local cleanup path",
        "never stashes",
        "resets",
        "cleans",
        "overwrites",
        "hides user work",
    )
    assert dirty_gate < dirty_stop < contract_stop < first_authoring_reload


def test_plan_phase_missing_contract_gate_blocks_scope_substitution_and_authoring() -> None:
    workflow = _workflow_text("plan-phase.md")

    assert "**If `project_contract` is empty or null:**" in workflow
    assert "**If `project_contract_gate.authoritative` is not true:**" in workflow
    assert "LIFECYCLE_CONTRACT_GATE=$(gpd --raw validate lifecycle-contract-gate plan-phase" in workflow
    assert 'INIT=$(gpd --raw init plan-phase "$PHASE" --stage planner_authoring)' in workflow

    missing_contract_stop = workflow.index("**If `project_contract` is empty or null:**")
    authoritative_gate_stop = workflow.index("**If `project_contract_gate.authoritative` is not true:**")
    lifecycle_gate = workflow.index("LIFECYCLE_CONTRACT_GATE=$(gpd --raw validate lifecycle-contract-gate plan-phase")
    first_authoring_reload = workflow.index('INIT=$(gpd --raw init plan-phase "$PHASE" --stage planner_authoring)')

    _assert_semantic(
        workflow,
        "plan-phase missing contract cannot infer scope from roadmap",
        "approved scoping contract",
        "GPD/state.json",
        "do not infer phase scope",
        "ROADMAP.md",
        "REQUIREMENTS.md",
    )
    _assert_contract_gate_stop_tuple(
        workflow,
        workflow_id="plan-phase",
        stage_id="phase_bootstrap",
        after_repair="gpd:plan-phase {PHASE}",
        triggers=(
            "project_contract_load_info.status starts with blocked",
            "project_contract is empty or null",
            "project_contract_validation.valid is false",
            "project_contract_gate.authoritative is not true",
        ),
    )
    assert BLOCKED_LIFECYCLE_STOP_PROHIBITION not in workflow
    assert missing_contract_stop < authoritative_gate_stop < lifecycle_gate < first_authoring_reload


def test_write_paper_surfaces_manuscript_reference_status_before_using_it() -> None:
    workflow = _workflow_text("write-paper.md")
    surface_line = next(line for line in workflow.splitlines() if line.startswith("Parse bootstrap JSON using"))
    status_line = next(line for line in workflow.splitlines() if "Use derived manuscript review statuses from init" in line)

    assert "do not duplicate the manifest's required-field list in prose" in surface_line
    assert "selected_publication_root" not in surface_line
    assert workflow.index(surface_line) < workflow.index(status_line)
    assert workflow.index(status_line) < workflow.index("source ordering or prose")
    assert "`derived_manuscript_reference_status` for the resolved" in workflow


def test_execute_phase_latex_compile_guidance_uses_resolved_manuscript_root() -> None:
    workflow = _workflow_text("execute-phase.md")

    assert "paper/ARTIFACT-MANIFEST.json" not in workflow
    assert "cd paper" not in workflow
    assert "MANUSCRIPT_ROOT" in workflow
    assert "manifest-recorded TeX entrypoint" in workflow
    assert "latex_compile" in workflow


def test_peer_review_reliability_reference_matches_peer_review_workflow_invocation() -> None:
    workflow = _workflow_text("peer-review.md")
    reliability = (REPO_ROOT / "src/gpd/specs/references/publication/peer-review-reliability.md").read_text(
        encoding="utf-8"
    )

    expected = 'gpd validate review-preflight peer-review "$REVIEW_TARGET" --strict'

    assert expected in workflow
    assert expected in reliability
    assert "gpd validate review-preflight peer-review --strict" not in reliability


def test_reapply_patches_keeps_manifest_regeneration_contract_honest() -> None:
    workflow = _workflow_text("reapply-patches.md")

    assert "do not invent a manual manifest-regeneration step" in workflow
    assert "The managed file manifest is rebuilt by the next `gpd:update`" in workflow
    assert "regenerate the file manifest" not in workflow


def test_help_update_describes_bootstrap_update_surface_not_repo_pull() -> None:
    workflow = _workflow_text("help.md")

    assert "Runs the public bootstrap update command for the active runtime" in workflow
    assert "Preserves local modifications via patch backups" in workflow
    assert "Pulls latest GPD files from the repository" not in workflow


def test_new_milestone_roadmapper_prompt_surfaces_contract_gate_inputs() -> None:
    workflow = _workflow_text("new-milestone.md")
    contract_context = workflow[workflow.index("<contract_context>") : workflow.index("</contract_context>")]

    assert "Project contract gate: {project_contract_gate}" in contract_context
    assert "Project contract validation: {project_contract_validation}" in contract_context
    assert "Project contract load info: {project_contract_load_info}" in contract_context
    assert "Contract intake: {contract_intake}" in contract_context
    assert "Effective reference intake: {effective_reference_intake}" in contract_context
    assert "Reference artifact file handles: {reference_artifact_files}" in contract_context
    assert "Files named in `effective_reference_intake.must_include_prior_outputs`" in workflow
    assert workflow.index("Project contract gate: {project_contract_gate}") < workflow.index(
        "approved project contract"
    )
    assert "`project_contract_gate.authoritative` is true" in workflow
    assert "shared_state_policy: return_only" in workflow
    assert "expected_artifacts:" in workflow


def test_help_resume_surface_stays_user_facing() -> None:
    workflow = expand_at_includes(_workflow_text("help.md"), REPO_ROOT / "src/gpd", "/runtime/").lower()

    assert "canonical continuation fields define the public resume vocabulary" in workflow
    assert "`resume_surface`" not in workflow
    assert "session.resume_file" not in workflow
    assert "shared resume-surface resolver owns canonical candidate kind/origin semantics" not in workflow


def test_resume_work_keeps_public_resume_vocabulary_canonical() -> None:
    resume_work_command = expand_at_includes(
        (COMMANDS_DIR / "resume-work.md").read_text(encoding="utf-8"),
        REPO_ROOT / "src/gpd",
        "/runtime/",
    )
    resume_work_workflow = expand_at_includes(_workflow_text("resume-work.md"), REPO_ROOT / "src/gpd", "/runtime/")

    assert resume_authority_public_vocabulary_intro() in resume_work_command
    assert resume_authority_public_vocabulary_intro() in resume_work_workflow
    assert "`resume_surface`" not in resume_work_command
    assert "`resume_surface`" not in resume_work_workflow
    assert "handoff_resume_file" not in resume_work_command
    assert "handoff_resume_file" not in resume_work_workflow
    assert resume_authority_fields() == (
        "active_resume_kind",
        "active_resume_origin",
        "active_resume_pointer",
        "active_bounded_segment",
        "derived_execution_head",
        "active_resume_result",
        "continuity_handoff_file",
        "recorded_continuity_handoff_file",
        "missing_continuity_handoff_file",
        "resume_candidates",
    )
    assert not any(alias in resume_authority_fields() for alias in resume_backend_only_fields())


def test_sync_state_keeps_state_json_authority_before_markdown_repair() -> None:
    raw_sync_state_command = (COMMANDS_DIR / "sync-state.md").read_text(encoding="utf-8")
    raw_sync_state_workflow = _workflow_text("sync-state.md")
    sync_state_command = expand_at_includes(
        raw_sync_state_command,
        REPO_ROOT / "src/gpd",
        "/runtime/",
    )
    sync_state_workflow = expand_at_includes(raw_sync_state_workflow, REPO_ROOT / "src/gpd", "/runtime/")

    assert "@{GPD_INSTALL_DIR}/workflows/sync-state/sync-bootstrap.md" in raw_sync_state_command
    assert "@{GPD_INSTALL_DIR}/templates/state-json-schema.md" not in raw_sync_state_command
    assert "{GPD_INSTALL_DIR}/templates/state-json-schema.md" in raw_sync_state_workflow
    assert "@{GPD_INSTALL_DIR}/templates/state-json-schema.md" not in raw_sync_state_workflow
    assert "`state.json` is authoritative" in raw_sync_state_workflow
    assert "`STATE.md` is the projection" in raw_sync_state_workflow

    for content in (sync_state_command, sync_state_workflow):
        assert "state-json-schema.md" in content
        assert "# state.json Schema" not in content

    assert re.search(r"`STATE\.md` is the projection and only becomes a recovery\s+source", sync_state_command)
    assert "backend repair command owns" in sync_state_workflow
    assert "Use `state.json` for structured fields and regenerate `STATE.md` from it unless `state.json` is unreadable." in sync_state_workflow

    assert "do not invent a field-by-field merge" not in sync_state_command
    assert "do not invent a field-by-field merge" in sync_state_workflow


def test_resume_workflow_routes_recent_project_ambiguity_before_new_projects_and_state_reconstruction() -> None:
    workflow = _workflow_text("resume-work.md")

    ambiguity_line = (
        '**If `project_reentry_requires_selection` is true or `project_reentry_mode="ambiguous-recent-projects"`:**'
    )
    auto_recent_line = '**If `project_root_auto_selected` is true or `project_root_source="recent_project"`:**'
    new_project_line = "**If `planning_exists` is false and no recent-project selection is required:** If recoverable state exists, repair first. Otherwise route to gpd:new-project and do not attempt STATE.md reconstruction."
    reconstruction_line = "If STATE.md is missing but other artifacts exist and `planning_exists` is true:"

    assert ambiguity_line in workflow
    assert auto_recent_line in workflow
    assert new_project_line in workflow
    assert reconstruction_line in workflow
    assert workflow.index(ambiguity_line) < workflow.index(new_project_line)
    assert workflow.index(auto_recent_line) < workflow.index(new_project_line)
    assert workflow.index(new_project_line) < workflow.index(reconstruction_line)


def test_resume_workflow_prioritizes_blocked_contract_repair_before_resume_targets_and_incomplete_plan() -> None:
    workflow = _workflow_text("resume-work.md")

    blocked_contract_line = "**If `project_contract_gate.authoritative` is false:**"
    bounded_segment_line = '**If `active_resume_kind="bounded_segment"` and `active_bounded_segment` exists:**'
    incomplete_plan_line = "**If incomplete plan (PLAN without SUMMARY) and no higher-priority blocker is active:**"

    assert blocked_contract_line in workflow
    assert bounded_segment_line in workflow
    assert incomplete_plan_line in workflow
    assert workflow.index(blocked_contract_line) < workflow.index(bounded_segment_line)
    assert workflow.index(blocked_contract_line) < workflow.index(incomplete_plan_line)


def test_arxiv_submission_does_not_instruct_unsupported_explicit_submission_root() -> None:
    workflow = _workflow_text("arxiv-submission.md")

    assert "submission/topic_stem.tex" not in workflow
    root_policy = workflow[workflow.index("Resolve manuscript target from raw preflight") :]
    for supported_root in (
        "`paper/`",
        "`manuscript/`",
        "`draft/`",
        "`GPD/publication/<subject_slug>/manuscript/`",
    ):
        assert supported_root in root_policy
    assert "Do not accept arbitrary external directories" in root_policy
    assert "Do not fall back to `find` or arbitrary wildcard matching" in root_policy


def test_paper_quality_scoring_reference_tracks_per_journal_gate_and_generic_fallback() -> None:
    scoring = (REPO_ROOT / "src/gpd/specs/references/publication/paper-quality-scoring.md").read_text(encoding="utf-8")

    assert "minimum_submission_score" in scoring
    assert "score ≥ 80" not in scoring
    assert "`mnras` and `jfm` currently use the generic weighting profile" in scoring


def test_write_paper_and_scoring_docs_distinguish_builder_supported_vs_manual_only_journals() -> None:
    workflow = _workflow_text("write-paper.md")
    scoring = (REPO_ROOT / "src/gpd/specs/references/publication/paper-quality-scoring.md").read_text(encoding="utf-8")

    assert "These are the only valid `journal` values" in workflow
    assert "`PAPER-CONFIG.json`" in workflow
    assert "`${PAPER_DIR}/ARTIFACT-MANIFEST.json`" in workflow
    assert "artifact-driven `--from-project` path" in scoring
    assert "Manual JSON is also the only supported path today for scoring-only profiles" in scoring
    assert "`prd`, `prb`, `prc`, and `nature_physics`" in scoring


def test_settings_publication_manuscript_preset_surfaces_real_latex_readiness_gates() -> None:
    settings = _workflow_text("settings.md")

    assert "only affects local smoke checks" not in settings
    assert "can degrade or block `paper-build` / `arxiv-submission`" in settings
