"""Provider-free Phase 4 planning persona replay helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

from gpd.core.context import init_plan_phase
from gpd.core.errors import ValidationError
from gpd.core.state import default_state_dict, save_state_json, state_set_project_contract
from gpd.core.workflow_staging import load_workflow_stage_manifest
from tests.helpers.git import git_add, git_commit, init_test_git_repo, run_git, seed_test_git_repo
from tests.helpers.phase4_persona.matrix import (
    PHASE4_PERSONA_SCHEMA_VERSION,
    PersonaMatrixRow,
)
from tests.helpers.phase4_persona.matrix import (
    load_phase4_rows as load_phase4_matrix_rows,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
GPD_DIRNAME = "GPD"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "stage0"
PLAN_PHASE_COMMAND = REPO_ROOT / "src" / "gpd" / "commands" / "plan-phase.md"
PLAN_PHASE_STAGE_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows" / "plan-phase"
PLAN_CHECKER_PROMPT = REPO_ROOT / "src" / "gpd" / "agents" / "gpd-plan-checker.md"
PLANNER_TEMPLATE = REPO_ROOT / "src" / "gpd" / "specs" / "templates" / "planner-subagent-prompt.md"
PLANNING_SOURCE_OWNERS = (
    "src/gpd/core/context.py",
    "src/gpd/core/workflow_staging.py",
    "src/gpd/specs/workflows/plan-phase/phase-bootstrap.md",
)
PLANNING_TEST_OWNERS = (
    "tests/helpers/phase4_persona/planning.py",
    "tests/core/test_phase4_persona_planning_replay.py",
)


@dataclass(frozen=True)
class PlanningReplayRow:
    row_id: str
    scenario: str
    expected_finding: str
    expected_result_class: str
    schema_version: str = PHASE4_PERSONA_SCHEMA_VERSION
    surface: str = "planning"
    fixture_family: str = "planning_replay_class"
    runtime_scope: tuple[str, ...] = ("provider_free",)
    source_owners: tuple[str, ...] = PLANNING_SOURCE_OWNERS
    test_owners: tuple[str, ...] = PLANNING_TEST_OWNERS
    provider_launch_allowed: bool = False
    network_allowed: bool = False
    raw_artifacts_allowed: bool = False
    expected_mutated: bool = False
    behavior_contract_id: str | None = None
    persona_class: str = "planner"
    prompt_variant_class: str = "workflow_stage_replay"
    expected_smoothness_class: str = "smooth"
    expected_schema_wrestling_class: str = "none"
    expected_next_up_specificity_class: str = "none"
    expected_mutation_guard_class: str = "no_write"
    expected_metric_bounds: tuple[tuple[str, int], ...] = (
        ("schema_repair_loop_count", 0),
        ("unexpected_write_count", 0),
    )
    metadata_source: str = "compatibility_adapter"


@dataclass(frozen=True)
class PlanningReplayOutcome:
    finding_id: str
    result_class: str
    mutated: bool = False
    provider_launch_allowed: bool = False
    failure_classes: tuple[str, ...] = ()
    evidence_classes: tuple[str, ...] = ()


PLANNING_REPLAY_ROWS = (
    PlanningReplayRow(
        "P4-PLAN-01",
        "plan_phase_bootstrap_lazy_loading",
        "plan_phase_bootstrap_lazy_loading",
        "stage_lazy_loading_preserved",
    ),
    PlanningReplayRow(
        "P4-PLAN-02",
        "missing_phase_no_target_invention",
        "missing_phase_no_target_invention",
        "missing_phase_blocked",
    ),
    PlanningReplayRow(
        "P4-PLAN-03",
        "project_contract_authority_block",
        "project_contract_authority_block",
        "planning_authority_blocked",
    ),
    PlanningReplayRow(
        "P4-PLAN-04",
        "dirty_worktree_hard_stop",
        "dirty_worktree_hard_stop",
        "dirty_worktree_blocks_before_write_stage",
    ),
    PlanningReplayRow(
        "P4-PLAN-05",
        "proof_bearing_checker_audit_visibility",
        "proof_bearing_checker_audit_visibility",
        "proof_bearing_audit_required",
    ),
)


def load_planning_replay_rows() -> tuple[PlanningReplayRow, ...]:
    """Return the class-only provider-free planning replay rows."""

    canonical_rows = _canonical_rows_by_exact_contract()
    return tuple(_with_canonical_metadata(row, canonical_rows) for row in PLANNING_REPLAY_ROWS)


def _canonical_rows_by_exact_contract() -> dict[tuple[str, str, str, str], PersonaMatrixRow]:
    try:
        return {
            (row.row_id, row.scenario, row.expected_finding, row.expected_result_class): row
            for row in load_phase4_matrix_rows("planning")
        }
    except (FileNotFoundError, KeyError, TypeError, ValueError):
        return {}


def _with_canonical_metadata(
    row: PlanningReplayRow,
    canonical_rows: dict[tuple[str, str, str, str], PersonaMatrixRow],
) -> PlanningReplayRow:
    row = _with_behavior_contract_defaults(row)
    canonical = canonical_rows.get((row.row_id, row.scenario, row.expected_finding, row.expected_result_class))
    if canonical is None:
        return row

    return replace(
        row,
        schema_version=canonical.schema_version,
        fixture_family=canonical.fixture_family,
        runtime_scope=canonical.runtime_scope,
        source_owners=canonical.source_owners,
        test_owners=canonical.test_owners,
        provider_launch_allowed=canonical.provider_launch_allowed,
        network_allowed=canonical.network_allowed,
        raw_artifacts_allowed=canonical.raw_artifacts_allowed,
        behavior_contract_id=getattr(canonical, "behavior_contract_id", row.behavior_contract_id),
        persona_class=getattr(canonical, "persona_class", row.persona_class),
        prompt_variant_class=getattr(canonical, "prompt_variant_class", row.prompt_variant_class),
        expected_smoothness_class=getattr(
            canonical,
            "expected_smoothness_class",
            row.expected_smoothness_class,
        ),
        expected_schema_wrestling_class=getattr(
            canonical,
            "expected_schema_wrestling_class",
            row.expected_schema_wrestling_class,
        ),
        expected_next_up_specificity_class=getattr(
            canonical,
            "expected_next_up_specificity_class",
            row.expected_next_up_specificity_class,
        ),
        expected_mutation_guard_class=getattr(
            canonical,
            "expected_mutation_guard_class",
            row.expected_mutation_guard_class,
        ),
        expected_metric_bounds=_normalize_metric_bounds(
            getattr(canonical, "expected_metric_bounds", row.expected_metric_bounds)
        ),
        metadata_source="canonical_fixture",
    )


def _with_behavior_contract_defaults(row: PlanningReplayRow) -> PlanningReplayRow:
    expected_smoothness_class = "smooth"
    if row.scenario in {
        "missing_phase_no_target_invention",
        "project_contract_authority_block",
        "dirty_worktree_hard_stop",
    }:
        expected_smoothness_class = "acceptable"
    return replace(
        row,
        behavior_contract_id=row.behavior_contract_id or f"phase4.planning.{row.scenario}",
        expected_smoothness_class=expected_smoothness_class,
    )


def _normalize_metric_bounds(value: object) -> tuple[tuple[str, int], ...]:
    if isinstance(value, dict):
        return tuple(sorted((str(key), int(bound)) for key, bound in value.items()))
    if isinstance(value, (list, tuple)):
        normalized: list[tuple[str, int]] = []
        for item in value:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                normalized.append((str(item[0]), int(item[1])))
        if normalized:
            return tuple(normalized)
    return ()


def score_planning_replay_row(row: PlanningReplayRow, tmp_path: Path) -> PlanningReplayOutcome:
    match row.scenario:
        case "plan_phase_bootstrap_lazy_loading":
            return _score_bootstrap_lazy_loading(tmp_path)
        case "missing_phase_no_target_invention":
            return _score_missing_phase_no_target_invention(tmp_path)
        case "project_contract_authority_block":
            return _score_project_contract_authority_block(tmp_path)
        case "dirty_worktree_hard_stop":
            return _score_dirty_worktree_hard_stop(tmp_path)
        case "proof_bearing_checker_audit_visibility":
            return _score_proof_bearing_checker_audit_visibility()
    raise AssertionError(f"unhandled planning replay scenario: {row.scenario}")


def _read_stage(name: str) -> str:
    return (PLAN_PHASE_STAGE_DIR / name).read_text(encoding="utf-8")


def _write_base_project(root: Path, *, roadmap_body: str | None = None, valid_contract: bool = True) -> None:
    gpd_dir = root / GPD_DIRNAME
    phase_dir = gpd_dir / "phases" / "02-analysis"
    phase_dir.mkdir(parents=True, exist_ok=True)
    (gpd_dir / "PROJECT.md").write_text("# Test Project\n", encoding="utf-8")
    (gpd_dir / "REQUIREMENTS.md").write_text("# Requirements\n- Preserve benchmark anchors.\n", encoding="utf-8")
    (gpd_dir / "ROADMAP.md").write_text(
        roadmap_body
        if roadmap_body is not None
        else "# Roadmap\n\n## Phase 2: Analysis\n\n**Goal:** Compare the benchmark observable.\n",
        encoding="utf-8",
    )
    (gpd_dir / "STATE.md").write_text("# State\nCurrent phase: 02\n", encoding="utf-8")
    (phase_dir / "02-CONTEXT.md").write_text("# Context\nLocked scope.\n", encoding="utf-8")
    (phase_dir / "02-RESEARCH.md").write_text("# Research\nMethod comparison.\n", encoding="utf-8")

    state = default_state_dict()
    state["position"]["current_phase"] = "02"
    state["position"]["current_phase_name"] = "Analysis"
    if valid_contract:
        state["project_contract"] = _fixture_project_contract()
    (gpd_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")


def _fixture_project_contract() -> dict[str, object]:
    return json.loads((FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"))


def _write_approval_blocked_contract(root: Path) -> None:
    _write_base_project(root, valid_contract=False)
    contract = _fixture_project_contract()
    contract["claims"][0]["references"] = []
    contract["acceptance_tests"][0]["evidence_required"] = ["deliv-figure"]
    contract["references"][0]["role"] = "background"
    contract["references"][0]["must_surface"] = False
    contract["references"][0]["applies_to"] = []
    contract["references"][0]["required_actions"] = []
    contract["context_intake"] = {
        "must_read_refs": [],
        "must_include_prior_outputs": [],
        "user_asserted_anchors": [],
        "known_good_baselines": [],
        "context_gaps": ["Need a concrete must-surface anchor before approval."],
        "crucial_inputs": [],
    }

    save_state_json(root, default_state_dict())
    result = state_set_project_contract(root, contract)
    assert result.updated is True


def _score_bootstrap_lazy_loading(root: Path) -> PlanningReplayOutcome:
    _write_base_project(root)

    payload = init_plan_phase(root, "2", stage="phase_bootstrap")
    manifest = load_workflow_stage_manifest("plan-phase")
    bootstrap = manifest.stage("phase_bootstrap")
    command = PLAN_PHASE_COMMAND.read_text(encoding="utf-8")

    assert tuple(field for field in payload if field != "staged_loading") == bootstrap.required_init_fields
    assert payload["staged_loading"] == manifest.staged_loading_payload("phase_bootstrap")
    assert "workflows/plan-phase/phase-bootstrap.md" in payload["staged_loading"]["eager_authorities"]
    assert "workflows/plan-phase/planner-authoring.md" in payload["staged_loading"]["must_not_eager_load"]
    assert "workflows/plan-phase/checker-revision.md" in payload["staged_loading"]["must_not_eager_load"]
    assert "reference_artifacts_content" not in payload
    assert "state_content" not in payload
    assert "@{GPD_INSTALL_DIR}/workflows/plan-phase/phase-bootstrap.md" in command
    assert "@{GPD_INSTALL_DIR}/workflows/plan-phase.md" not in command

    return PlanningReplayOutcome(
        finding_id="plan_phase_bootstrap_lazy_loading",
        result_class="stage_lazy_loading_preserved",
        failure_classes=("plan_phase_bootstrap_lazy_loading", "late_authorities_deferred"),
        evidence_classes=("staged_init_payload", "manifest_must_not_eager_load", "thin_command_wrapper"),
    )


def _score_missing_phase_no_target_invention(root: Path) -> PlanningReplayOutcome:
    _write_base_project(root, roadmap_body="# Roadmap\n\nNo phase list yet.\n")

    try:
        init_plan_phase(root, None, stage="phase_bootstrap")
    except ValidationError as exc:
        assert "phase is required for init plan-phase" in str(exc)
    else:  # pragma: no cover - assertion message is clearer than an uncovered branch.
        raise AssertionError("missing phase unexpectedly produced a staged plan-phase payload")

    explicit_missing = init_plan_phase(root, "9", stage="phase_bootstrap")
    assert explicit_missing["phase_found"] is False
    assert explicit_missing["phase_dir"] is None
    assert explicit_missing["phase_name"] is None
    assert explicit_missing["phase_slug"] is None
    assert not (root / GPD_DIRNAME / "phases" / "09").exists()

    return PlanningReplayOutcome(
        finding_id="missing_phase_no_target_invention",
        result_class="missing_phase_blocked",
        failure_classes=("missing_phase_no_target_invention", "explicit_missing_phase_unresolved"),
        evidence_classes=("staged_init_validation_error", "no_phase_dir_created", "no_phase_metadata_invented"),
    )


def _score_project_contract_authority_block(root: Path) -> PlanningReplayOutcome:
    _write_approval_blocked_contract(root)

    payload = init_plan_phase(root, "2", stage="phase_bootstrap")
    gate = payload["project_contract_gate"]
    validation = payload["project_contract_validation"]
    bootstrap_text = _read_stage("phase-bootstrap.md")

    assert isinstance(gate, dict)
    assert isinstance(validation, dict)
    assert gate["visible"] is True
    assert gate["blocked"] is True
    assert gate["approval_blocked"] is True
    assert gate["authoritative"] is False
    assert validation["valid"] is False
    assert bootstrap_text.index("project_contract_validation.valid") < bootstrap_text.index(
        "LIFECYCLE_CONTRACT_GATE="
    )
    assert bootstrap_text.index("project_contract_gate.authoritative") < bootstrap_text.index(
        "LIFECYCLE_CONTRACT_GATE="
    )
    assert "Do not plan, execute, verify, fingerprint, align, or pass `project_contract` to subagents" in bootstrap_text

    return PlanningReplayOutcome(
        finding_id="project_contract_authority_block",
        result_class="planning_authority_blocked",
        failure_classes=("project_contract_authority_block", "non_authoritative_contract_blocks_planning"),
        evidence_classes=("approval_blocked_contract_gate", "bootstrap_stop_before_lifecycle_or_planning"),
    )


def _score_dirty_worktree_hard_stop(root: Path) -> PlanningReplayOutcome:
    init_test_git_repo(root)
    _write_base_project(root)
    git_add(root, GPD_DIRNAME)
    git_commit(root, "seed GPD project")
    seed_test_git_repo(root, relpath="README.md", content="seed\n", message="seed workspace")
    (root / "notes.md").write_text("user scratch\n", encoding="utf-8")

    status = run_git(root, "status", "--porcelain", "--untracked-files=all").stdout
    manifest = load_workflow_stage_manifest("plan-phase")
    bootstrap = manifest.stage("phase_bootstrap")
    planner_authoring = manifest.stage("planner_authoring")
    bootstrap_text = _read_stage("phase-bootstrap.md")

    assert status.strip()
    assert bootstrap.writes_allowed == ()
    assert "GPD/phases" in planner_authoring.writes_allowed
    assert "Dirty worktree safety gate" in bootstrap_text
    assert "git status --short" in bootstrap_text
    assert "gpd commit" in bootstrap_text
    assert "explicitly approved project-local cleanup path" in bootstrap_text
    assert "never stashes, resets, cleans, overwrites, or hides user work" in bootstrap_text
    assert bootstrap_text.index("Dirty worktree safety gate") < bootstrap_text.index(
        "If `project_contract_load_info.status`"
    )

    return PlanningReplayOutcome(
        finding_id="dirty_worktree_hard_stop",
        result_class="dirty_worktree_blocks_before_write_stage",
        failure_classes=("dirty_worktree_hard_stop", "no_stash_reset_clean_or_overwrite"),
        evidence_classes=("git_worktree_present", "dirty_status_nonempty", "bootstrap_no_writes"),
    )


def _score_proof_bearing_checker_audit_visibility() -> PlanningReplayOutcome:
    manifest = load_workflow_stage_manifest("plan-phase")
    bootstrap = _read_stage("phase-bootstrap.md")
    planner = _read_stage("planner-authoring.md")
    checker = _read_stage("checker-revision.md")
    planner_template = PLANNER_TEMPLATE.read_text(encoding="utf-8")
    checker_prompt = PLAN_CHECKER_PROMPT.read_text(encoding="utf-8")

    assert manifest.stage("checker_revision").loaded_authorities == (
        "workflows/plan-phase/checker-revision.md",
        "templates/planner-subagent-prompt.md",
    )
    assert "`--skip-verify` does NOT waive checker review" in bootstrap
    assert "any proof-bearing plan set still needs checker review or an equivalent main-context audit" in bootstrap
    assert "proof-bearing plans still need checker review or an equivalent main-context audit" in planner
    assert "Proof-obligation audit path" in checker
    assert "sibling `{plan_id}-PROOF-REDTEAM.md` review artifact" in checker
    assert "Anti-bypass language" in checker
    assert "If any plan is proof-bearing, do NOT waive this gate" in checker
    assert "Proof-bearing plans keep proof artifacts and sibling `*-PROOF-REDTEAM.md` audits explicit" in planner_template
    assert "Proof-bearing plans always require theorem text" in checker_prompt
    assert "proof audit path" in checker_prompt

    return PlanningReplayOutcome(
        finding_id="proof_bearing_checker_audit_visibility",
        result_class="proof_bearing_audit_required",
        failure_classes=("proof_bearing_checker_audit_visibility", "skip_verify_does_not_waive_proof_audit"),
        evidence_classes=("bootstrap_proof_gate", "planner_proof_gate", "checker_audit_gate"),
    )
