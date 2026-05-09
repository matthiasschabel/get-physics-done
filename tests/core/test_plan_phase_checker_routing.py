"""Routing assertions for the `plan-phase` checker seam."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAN_PHASE = REPO_ROOT / "src/gpd/specs/workflows/plan-phase.md"
PLAN_PHASE_STAGE_DIR = REPO_ROOT / "src/gpd/specs/workflows/plan-phase"


def _stage_text(name: str) -> str:
    return (PLAN_PHASE_STAGE_DIR / name).read_text(encoding="utf-8")


def _plan_phase_authority_text() -> str:
    return "\n\n".join(
        [
            PLAN_PHASE.read_text(encoding="utf-8"),
            _stage_text("phase-bootstrap.md"),
            _stage_text("research-routing.md"),
            _stage_text("planner-authoring.md"),
            _stage_text("checker-revision.md"),
        ]
    )


def test_plan_phase_separates_planner_checkpoint_handling_from_checker_revision() -> None:
    source = _stage_text("planner-authoring.md")

    assert "## 9b. Handle Planner Checkpoint" in source
    assert "spawn a fresh `gpd-planner` continuation handoff" in source
    assert "Do not route planner checkpoints into the checker revision loop." in source
    assert "Only after the planner returns `completed` should the workflow advance to checker review." in source
    assert "Present to user, get response, spawn continuation (step 12)" not in source


def test_plan_phase_routes_checker_statuses_through_structured_fields() -> None:
    source = _stage_text("checker-revision.md")

    assert "`gpd_return.status: completed`" in source
    assert "`gpd_return.status: checkpoint`" in source
    assert "`gpd_return.status: blocked`" in source
    assert "`gpd_return.status: failed`" in source
    assert "Record approved plans from the structured `approved_plans` list only." in source
    assert "Record blocked plans from the structured `blocked_plans` list only." in source
    assert "Approved Plans (ready for execution)" not in source
    assert 'Approved Plans" table' not in source
    assert "plan-ID reconciliation" in source


def test_plan_phase_fails_closed_on_plan_id_mismatch_before_accepting_checker_success() -> None:
    source = _stage_text("checker-revision.md")

    assert "`approved_plans` names only readable `*-PLAN.md` artifacts in `FRESH_PLAN_FILES`" in source
    assert "`blocked_plans` is empty" in source
    assert "every approved plan file still exists and matches the approved plan IDs" in source
    assert (
        "Reject the return if any listed plan ID does not map to a readable `*-PLAN.md` file in `FRESH_PLAN_FILES`."
        in source
    )
    assert "send the checker output back through the revision loop as a fail-closed mismatch" in source


def test_plan_phase_reloads_each_stage_and_validates_only_fresh_plan_files() -> None:
    source = _plan_phase_authority_text()

    assert "bind_plan_phase_init" not in source
    assert "staged_loading.required_init_fields" in source
    assert "staged field-access helper" in source
    assert "gpd --raw stage field-access plan-phase --stage <stage_id> --style instruction" in source
    assert "--alias ALIAS=field" in source
    assert "shell variables parsed from an older stage" in source
    assert 'BOOTSTRAP_INIT=$(gpd --raw init plan-phase "$PHASE" --stage phase_bootstrap)' in source
    assert 'gpd --raw init plan-phase "$PHASE" --stage research_routing' in source
    assert 'gpd --raw init plan-phase "$PHASE" --stage planner_authoring' in source
    assert 'gpd --raw init plan-phase "$PHASE" --stage checker_revision' in source
    assert source.count("INIT=$(gpd --raw init plan-phase") >= 3
    assert "PLANNER_RETURN=$(\ntask(" in source
    assert source.index("PLANNER_RETURN=$(") < source.index(
        "Before checker/final status, validate only fresh `FRESH_PLAN_FILES`"
    )
    assert "derive that list from the typed `PLANNER_RETURN`" in source
    assert "gpd return skeleton --role planner --status completed" in source
    assert "one `--file` entry per newly written plan" in source
    assert "Then run the planner child_gate tuple once" in source
    assert "printf '```yaml\\ngpd_return:\\n'" not in source
    assert "printf '  status: completed\\n  files_written:\\n'" not in source
    assert "printf '%s\\n' \"$PLAN_RETURN_MARKDOWN\"" not in source
    assert 'FRESH_PLAN_FILES="$FRESH_PLAN_FILES" python3 -c' not in source
    assert 'json.dumps({"gpd_return":{"files_written":os.getenv("FRESH_PLAN_FILES","").split()}})' not in source
    assert "gpd validate handoff-artifacts -" in source
    assert "allowed-root" in source
    assert "expected-glob" in source
    assert "--required-suffix=-PLAN.md" in source
    assert '[ -f "$plan_file" ] || continue' not in source
    assert "all files are readable `${PHASE_DIR}/*-PLAN.md` paths" in source
    assert "every file passes `gpd validate plan-contract`" in source
    assert "every file passes the structured plan preflight validator" in source
    assert "Read each fresh plan artifact into `PLANS_CONTENT` only after the planner gate passes" in source
    assert (
        "Before checker/final status, validate only fresh `FRESH_PLAN_FILES` from the planner or manual branch."
    ) in source


def test_plan_phase_does_not_synthesize_files_only_json_planner_return() -> None:
    source = _stage_text("planner-authoring.md")

    assert "The shared child artifact gate owns the no-synthetic-child-return rule" in source
    assert "complete orchestrator-owned fenced YAML `MAIN_CONTEXT_PLAN_RETURN`" in source
    assert "gpd return skeleton --role planner --status completed" in source
    assert "printf '```yaml\\ngpd_return:\\n'" not in source
    assert '{"gpd_return":{"files_written"' not in source
    assert "${PLANNER_RETURN:-$(" not in source


def test_plan_phase_manual_plan_fallback_cannot_skip_fresh_plan_validators() -> None:
    source = _plan_phase_authority_text()

    assert "Main-context plan or any manual bounded authoring branch" in source
    assert "set `FRESH_PLAN_FILES` to the newly created path(s)" in source
    assert "No full planner/checker loop is required for this fallback unless requested" in source
    assert "a failing gate means `status: blocked`, not `planned_ready`/`green`" in source
    assert "and no `gpd:execute-phase` route" in source
    assert "gpd validate plan-contract" in source
    assert "structured plan preflight validator" in source
    assert (
        "The `PHASE PLANNED` offer and `gpd:execute-phase` route require the fresh-plan validator gate above." in source
    )


def test_plan_phase_captures_state_sensitive_spawn_returns() -> None:
    source = _plan_phase_authority_text()

    assert "PLANNER_RETURN=$(\ntask(" in source
    assert "CHECKER_RETURN=$(\ntask(" in source
    assert source.count("PLANNER_RETURN=$(\ntask(") >= 2


def test_plan_phase_researcher_checkpoint_path_is_a_fresh_continuation_handoff() -> None:
    source = _stage_text("research-routing.md")

    assert "## 5.1 Handle Researcher Checkpoint" in source
    assert "Continue research as a fresh continuation handoff for Phase {phase_number}: {phase_name}" in source
    assert "<checkpoint_response>" in source
    assert 'description="Continue research Phase {phase_number}"' in source
    assert "{phase_dir}/{phase_number}-RESEARCH.md" in source
    assert "{phase_dir}/{phase}-RESEARCH.md" not in source
    assert (
            "After the continuation returns, rerun the same researcher `child_gate` before advancing."
        in source
    )


def test_plan_phase_wrapper_stays_routing_only() -> None:
    command = (REPO_ROOT / "src/gpd/commands/plan-phase.md").read_text(encoding="utf-8")

    assert "@{GPD_INSTALL_DIR}/workflows/plan-phase/phase-bootstrap.md" in command
    assert "@{GPD_INSTALL_DIR}/workflows/plan-phase.md" not in command
    assert (
        "Canonical contract schema and hard validation rules load later at the staged planner and checker handoffs"
        not in command
    )
    assert "For proof-bearing work, every proof-bearing plan must surface the theorem statement" not in command
