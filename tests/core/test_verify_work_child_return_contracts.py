"""Focused assertions for verify-work child-return contracts."""

from __future__ import annotations

import re
from pathlib import Path

from gpd.core.child_handoff import ChildGateTuple, parse_child_gate_markdown
from gpd.core.context import (
    _build_proof_redteam_finalizer_bridge,
    _build_verification_report_finalizer_bridge,
    _build_verification_report_skeleton_bridge,
)
from tests.assertion_taxonomy_support import (
    MatchMode,
    assert_prompt_contracts,
    semantic_anchor,
    semantic_concept,
)
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "src/gpd/agents"
TEMPLATES_DIR = REPO_ROOT / "src/gpd/specs/templates"
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"
_YAML_BLOCK_RE = re.compile(r"```ya?ml\n(?P<body>.*?)\n```", re.DOTALL)


def _read(path: Path) -> str:
    if path.parent == WORKFLOWS_DIR and path.stem == "verify-work":
        return workflow_authority_text(WORKFLOWS_DIR, path.stem)
    return path.read_text(encoding="utf-8")


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


def _assert_absent(text: str, label: str, *fragments: str) -> None:
    assert_prompt_contracts(
        text,
        *semantic_concept(label, forbidden=fragments, match=MatchMode.CASEFOLD_NORMALIZED, context=label),
    )


def test_verify_work_inventory_bridge_exposes_writer_command_and_preview_command(tmp_path: Path) -> None:
    phase_info = {
        "directory": "GPD/phases/01-setup",
        "phase_number": "01",
        "plans": ["01-PLAN.md"],
    }

    bridge = _build_verification_report_skeleton_bridge(tmp_path, phase_info)

    assert bridge["skeleton_command"] == (
        f"gpd verification-report skeleton {(tmp_path / 'GPD/phases/01-setup/01-PLAN.md').as_posix()} --format markdown"
    )
    assert bridge["writer_command"] == (
        f"gpd verification-report skeleton {(tmp_path / 'GPD/phases/01-setup/01-PLAN.md').as_posix()} "
        f"--write --output {(tmp_path / 'GPD/phases/01-setup/01-VERIFICATION.md').as_posix()} --force "
        "--body-file BODY.md --validate contract"
    )
    assert bridge["supported_statuses"] == ["gaps_found"]
    assert bridge["gap_report_skeleton_command"] == bridge["skeleton_command"]
    assert bridge["gap_report_writer_command"] == bridge["writer_command"]
    assert "gap-report-only" in str(bridge["status_policy"])
    body_contract = bridge["body_contract"]
    assert "`BODY.md` is body-only Markdown" in str(body_contract)
    _assert_semantic(
        str(body_contract),
        "verify-work body evidence execution transcript contract",
        "fenced executed",
        "python",
        "bash",
        "output",
        "PASS",
        "FAIL",
        "INCONCLUSIVE",
    )
    _assert_semantic(
        str(body_contract), "verify-work body evidence rejects prose-only bullets", "prose bullets", "invalid"
    )
    assert "--raw" not in str(bridge["skeleton_command"])
    assert "run writer_command" in str(bridge["fallback_rule"])
    assert "body-only evidence" in str(bridge["fallback_rule"])
    assert "satisfies body_contract" in str(bridge["fallback_rule"])
    _assert_semantic(
        str(bridge["fallback_rule"]),
        "verify-work skeleton command is preview only",
        "skeleton_command",
        "preview context only",
    )
    assert "hand-author or reflow VERIFICATION.md frontmatter" in str(bridge["fallback_rule"])
    assert "use the generated frontmatter as the starting YAML" not in str(bridge["fallback_rule"])


def test_verify_work_finalizer_bridges_expose_helper_commands(tmp_path: Path) -> None:
    phase_info = {
        "directory": "GPD/phases/01-setup",
        "phase_number": "01",
        "plans": ["01-PLAN.md"],
    }

    verification_bridge = _build_verification_report_finalizer_bridge(tmp_path, phase_info)
    proof_bridge = _build_proof_redteam_finalizer_bridge(tmp_path, phase_info)

    assert verification_bridge["command_name"] == "gpd verification-report finalize"
    assert verification_bridge["writer_command_template"] == (
        f"gpd verification-report finalize {(tmp_path / 'GPD/phases/01-setup/01-PLAN.md').as_posix()} "
        f"--patch PATCH.json --body-file BODY.md --output "
        f"{(tmp_path / 'GPD/phases/01-setup/01-VERIFICATION.md').as_posix()} --validate contract --force"
    )
    assert verification_bridge["supported_statuses"] == [
        "passed",
        "gaps_found",
        "expert_needed",
        "human_needed",
    ]
    assert "typed verification outcome patch" in str(verification_bridge["patch_contract"])
    assert "Do not hand-author VERIFICATION.md YAML" in str(verification_bridge["status_policy"])

    assert proof_bridge["command_name"] == "gpd proof-redteam finalize"
    assert proof_bridge["supported_statuses"] == ["passed"]
    assert (
        proof_bridge["expected_proof_redteam_path"] == (tmp_path / "GPD/phases/01-setup/01-PROOF-REDTEAM.md").as_posix()
    )
    assert "gpd proof-redteam finalize" in str(proof_bridge["writer_command_template"])


def test_verify_work_verifier_handoff_stays_one_shot_and_routes_on_typed_status() -> None:
    workflow = _read(WORKFLOWS_DIR / "verify-work.md")

    assert "Spawn `gpd-verifier` once and let it own the physics policy." in workflow
    assert 'subagent_type="gpd-verifier"' in workflow
    assert "<spawn_contract>" in workflow
    assert 'id: "verify_work_verifier_report"' in workflow
    _assert_semantic(workflow, "verify-work verifier heading non-authority", "presentation headings", "non-authority")
    assert "Verifier checkpoints use `references/orchestration/continuation-boundary.md`" in workflow
    assert "Missing/unreadable/unnamed/invalid artifacts use the tuple failure route" in workflow
    _assert_semantic(
        workflow,
        "verify-work wrapper does not recompute canonical status",
        "do not recompute",
        "canonical verification status",
    )


def test_verify_work_verifier_sync_requires_artifact_gate_before_downstream_routing() -> None:
    workflow = _read(WORKFLOWS_DIR / "verify-work.md")
    gate = _child_gate(workflow, "verify_work_verifier_report")

    _assert_semantic(
        workflow,
        "verify-work verifier child gate before routing",
        "verify_work_verifier_report",
        "child_gate",
        "before downstream routing",
    )
    assert [artifact.path for artifact in gate.expected_artifacts] == [
        "${PHASE_DIR_ABS}/${phase_number}-VERIFICATION.md"
    ]
    assert gate.allowed_roots == ("${PHASE_DIR_ABS}",)
    assert gate.freshness is not None
    assert gate.freshness.marker == "$VERIFIER_HANDOFF_STARTED_AT"
    assert any("--require-status completed --require-files-written" in validator for validator in gate.validators)
    assert "gpd validate verification-contract ${PHASE_DIR_ABS}/${phase_number}-VERIFICATION.md" in gate.validators
    assert gate.applicator.command == "sync_verifier_output only after tuple passes"
    assert gate.status_route == {
        "checkpoint": "fresh verifier continuation after user response",
        "blocked": "non-green stop with validator errors",
        "failed": "non-green stop with validator errors",
    }
    assert 'gpd validate verification-contract "${PHASE_DIR_ABS}/${phase_number}-VERIFICATION.md"' in workflow
    assert (
        'Any verifier-written canonical `VERIFICATION.md`, including gap reports and `blocked`/`failed` handoffs, must pass `gpd validate verification-contract "${PHASE_DIR_ABS}/${phase_number}-VERIFICATION.md"` before this wrapper accepts it as canonical.'
        in workflow
    )
    assert "Missing/unreadable/unnamed/invalid artifacts use the tuple failure route" in workflow
    _assert_semantic(
        workflow,
        "verify-work verifier sync keeps status canonical",
        "do not recompute",
        "canonical verification status",
    )
    _assert_semantic(workflow, "verify-work preexisting reports non-authority", "preexisting reports", "not authority")
    assert (
        "If a canonical verification file already exists, preserve its authoritative frontmatter and append only the session-local overlay here."
        in workflow
    )
    assert "Write to `${PHASE_DIR_ABS}/${phase_number}-VERIFICATION.md`." in workflow
    assert (
        'Run `gpd validate verification-contract "${PHASE_DIR_ABS}/${phase_number}-VERIFICATION.md"` before committing it; invalid reports stop non-green and do not advance state.'
        in workflow
    )
    assert (
        workflow.count(
            "Changed verification files fail `gpd pre-commit-check` when this header is missing or mismatched against the active lock."
        )
        == 1
    )
    assert 'failure_route: "fail_closed -> gpd:verify-work ${phase_number}' in workflow
    _assert_semantic(
        workflow, "verify-work preexisting reports still non-authority", "preexisting reports", "not authority"
    )


def test_verify_work_fallback_failed_validation_stops_at_sync_gate() -> None:
    workflow = _read(WORKFLOWS_DIR / "verify-work.md")

    fallback_fragments = (
        "fallback verifier execution is still `gpd-verifier` execution",
        "verification_report_skeleton_bridge",
        "verification_report_finalizer_bridge",
        "write body-only evidence",
        "satisfies bridge `body_contract`",
        "one fenced executed `python`/`bash` block",
        "adjacent `**Output:**` plus fenced `output`",
        "following `PASS`/`FAIL`/`INCONCLUSIVE` verdict",
        "replace `BODY.md` in the skeleton bridge `writer_command`",
        "The helper serializes YAML and validates before canonical acceptance.",
        "write the finalizer bridge patch JSON",
        "run `gpd verification-report finalize`",
        "Use `skeleton_command` only as read-only preview context",
        "do not hand-author or reflow frontmatter",
        "keep command transcripts, hashes, oracle details, prose-only evidence, and `gpd_return` out of YAML",
        "Read the runtime-projected `{GPD_AGENTS_DIR}/gpd-verifier.md` and helper/schema authority references for verifier policy",
        "not for wrapper-side schema recreation",
        "Do not wrapper-repair the canonical report.",
    )
    sync_stop = (
        "- Fallback executions that reach this step after failed report validation stop here: emit the blocked/final response with latest validator errors. "
        "Do not list the invalid `VERIFICATION.md` as an authoritative artifact, do not route to gaps unless a schema-valid gap report exists, do not enter `gap_repair` or `complete_session`, "
        "and do not patch the canonical verification report from this wrapper."
    )
    stage_stop_line = (
        "- Do not patch canonical verification frontmatter in this wrapper. Surface bounded-loop validator errors fail-closed through `references/orchestration/stage-stop-envelope.md`: "
        "primary `gpd:verify-work ${phase_number}`, secondary `gpd:resume-work` and `gpd:suggest-next`."
    )

    for fragment in fallback_fragments:
        assert fragment in workflow
    assert sync_stop in workflow
    assert stage_stop_line in workflow
    assert (
        "Schema finalization is bounded: validator pass returns; after the second validator failure total, including the initial failure and one repair rerun, return `gpd_return.status: blocked` with latest errors."
        in workflow
    )

    assert workflow.index("verification_report_skeleton_bridge") < workflow.index('<step name="sync_verifier_output">')
    assert workflow.index("replace `BODY.md` in the skeleton bridge `writer_command`") < workflow.index(
        '<step name="sync_verifier_output">'
    )
    assert workflow.index(sync_stop) < workflow.index(
        'INTERACTIVE_VALIDATION_INIT=$(gpd --raw init verify-work "${PHASE_ARG}" --stage interactive_validation)'
    )
    assert workflow.index(sync_stop) < workflow.index('<step name="load_gap_repair_stage">')
    assert workflow.index(sync_stop) < workflow.index('<step name="complete_session">')


def test_verify_work_gap_plan_checker_routes_on_canonical_gpd_return_status() -> None:
    workflow = _read(WORKFLOWS_DIR / "verify-work.md")
    checker = _read(AGENTS_DIR / "gpd-plan-checker.md")
    gate = _child_gate(workflow, "verify_work_gap_plan_checker")

    assert 'gpd --raw init verify-work "${PHASE_ARG}" --stage gap_repair' in workflow
    _assert_semantic(
        workflow,
        "verify-work gap repair staged payload routing",
        "staged payload",
        "source of truth",
        "planner",
        "checker routing",
    )
    assert (
        "If the checker returns a structured `gpd_return`, route on `gpd_return.status` and the structured plan lists, not on presentation text:"
        in workflow
    )
    assert (
        "- `completed`: treat the fresh fix plans as verified only after the on-disk files still match the planner's `files_written` set."
        in workflow
    )
    _assert_semantic(
        workflow,
        "verify-work gap checker checkpoint route",
        "checkpoint",
        "approved_plans",
        "blocked_plans",
        "revision loop",
        "checkpoint stop route",
    )
    _assert_semantic(
        workflow,
        "verify-work gap checker blocked route",
        "blocked",
        "nothing is approved",
        "blocked plan IDs",
        "without rewriting approved plans",
    )
    _assert_semantic(
        workflow,
        "verify-work gap checker failed route",
        "failed",
        "retry",
        "manual revision",
        "failed stop route",
    )
    _assert_semantic(
        workflow,
        "verify-work gap checker structured fields authority",
        "structured fields",
        "human-readable approval table",
        "source of truth",
    )
    assert gate.status_route == {
        "checkpoint": "record approved/blocked plans for gap revision",
        "blocked": "gpd:plan-phase ${phase_number} --gaps",
        "failed": "retry or manual revision",
    }

    assert "The label examples in `checker-return-protocol.md` are UI only" in checker
    assert "the machine decision comes from `gpd_return.status`, approved/blocked plan lists, and `issues`" in checker
    assert "approved_plans:" in checker
    assert '    - "04-01"' in checker
    assert "blocked_plans: []" in checker


def test_verify_work_gap_plan_success_reconciles_files_written_and_disk_artifacts() -> None:
    workflow = _read(WORKFLOWS_DIR / "verify-work.md")
    planner_prompt = _read(TEMPLATES_DIR / "planner-subagent-prompt.md")
    gate = _child_gate(workflow, "verify_work_gap_planner")

    assert (
        "Use `templates/planner-subagent-prompt.md` to build the gap_closure planner handoff from the staged payload."
        in workflow
    )
    assert [(artifact.path, artifact.kind) for artifact in gate.expected_artifacts] == [
        ("${PHASE_DIR_ABS}/*-PLAN.md", "glob")
    ]
    assert gate.allowed_roots == ("${PHASE_DIR_ABS}",)
    assert gate.freshness is not None
    assert gate.freshness.marker == "$GAP_PLANNER_HANDOFF_STARTED_AT"
    assert "gpd validate plan-contract <each fresh gap plan>" in gate.validators
    assert (
        "If the planner fails to spawn or returns an error, keep the session fail-closed and offer retry or manual plan creation. Do not fall through to gap verification on the basis of preexisting `PLAN.md` files alone."
        in workflow
    )
    assert gate.status_route == {
        "checkpoint": "fresh gap-planner continuation after user response",
        "blocked": "gpd:plan-phase ${phase_number} --gaps",
        "failed": "retry gap planner or gpd:plan-phase ${phase_number} --gaps",
    }
    assert 'id: "verify_work_gap_plan_checker"' in workflow
    assert "fresh planner PLAN.md artifacts remain readable and named in planner files_written" in workflow
    _assert_semantic(
        workflow,
        "verify-work gap checker spawn failure policy",
        "checker fails to spawn",
        "without plan verification",
        "not verified",
    )
    _assert_semantic(
        workflow,
        "verify-work approved plans are not rewritten",
        "do not rewrite approved plans",
        "revision round",
    )
    assert "Do not fall through to gap verification on the basis of preexisting `PLAN.md` files alone." in workflow

    assert "Planner runs must return a structured `gpd_return` envelope." in planner_prompt
    assert "Do not route on them; route on `gpd_return.status` and the artifact gate below." in planner_prompt
    assert (
        "- `gpd_return.status: completed` means the planner wrote the expected PLAN.md artifacts and they passed the on-disk artifact check."
        in planner_prompt
    )
    assert (
        "Always verify `gpd_return.files_written` against the expected plan artifacts before accepting completion."
        in planner_prompt
    )


def test_verify_work_proof_check_handoff_uses_structured_freshness_and_fail_closed_artifact_gates() -> None:
    workflow = _read(WORKFLOWS_DIR / "verify-work.md")
    gate = _child_gate(workflow, "verify_work_proof_critic")

    _assert_semantic(
        workflow,
        "verify-work proof-review freshness summary",
        "phase_proof_review_status",
        "proof-review freshness summary",
    )
    _assert_semantic(
        workflow,
        "verify-work proof redteam finalizer bridge",
        "proof_redteam_finalizer_bridge",
        "helper-owned",
        "passed-audit bridge",
    )
    assert "Use `gpd proof-redteam skeleton` for non-passing helper-owned proof-redteam frontmatter" in workflow
    assert "gpd proof-redteam finalize" in workflow
    assert "before `gpd validate proof-redteam`" in workflow
    assert "`staged_loading.checkpoints` is not a proof classifier" in workflow
    assert "ignore `phase_proof_review_status.state=not_reviewed|fresh` alone" in workflow
    _assert_semantic(
        workflow,
        "verify-work proof-bearing classification source",
        "proof-bearing",
        "research artifacts",
    )
    assert "exclude installed runtime/config/skills trees" in workflow
    assert 'id: "verify_work_proof_critic"' in workflow
    _assert_semantic(
        workflow,
        "verify-work proof handoff uses runtime delegation tuple",
        "runtime delegation convention",
        "proof handoff",
        "tuple",
    )
    assert [artifact.path for artifact in gate.expected_artifacts] == [
        "${PHASE_DIR_ABS}/${phase_number}-PROOF-REDTEAM.md"
    ]
    assert gate.allowed_roots == ("${PHASE_DIR_ABS}",)
    assert gate.freshness is not None
    assert gate.freshness.marker == "$PROOF_HANDOFF_STARTED_AT"
    assert gate.status_route == {
        "checkpoint": "fresh proof continuation after user response",
        "blocked": "fresh proof continuation or fail closed",
        "failed": "fresh proof continuation or fail closed",
    }
    _assert_absent(
        workflow,
        "verify-work stale inline checkpoint wording",
        "Return `status: checkpoint` instead of waiting for user input inside this run.",
    )
    _assert_semantic(
        workflow,
        "verify-work proof return text alone is insufficient",
        "never trust the return text alone",
        "missing",
        "stale",
        "malformed",
        "not passed",
        "fail-closed",
        "fresh proof continuation",
    )
    assert (
        "After the proof critic returns, re-open `${PHASE_DIR_ABS}/${phase_number}-PROOF-REDTEAM.md` from disk and confirm the artifact exists and is `passed` after a successful `gpd proof-redteam finalize ...` and `gpd validate proof-redteam` run before finalizing the gap ledger."
        in workflow
    )
    assert (
        "If `gpd-check-proof` still cannot produce a passed audit, keep the verification status fail-closed."
        in workflow
    )
    _assert_semantic(
        workflow,
        "verify-work file-producing handoff proves expected artifact",
        "file-producing handoffs",
        "expected artifact",
        "success",
    )
    _assert_semantic(workflow, "verify-work closed child is one-shot", "never send more input", "closed child")


def test_verify_work_acknowledgement_is_routing_only_not_status_upgrade() -> None:
    workflow = _read(WORKFLOWS_DIR / "verify-work.md")

    assert "Accept as-is" not in workflow
    _assert_semantic(
        workflow,
        "verify-work acknowledgement keeps verification non-passed",
        "acknowledge limitation",
        "verification status remains non-passed",
    )
    _assert_semantic(
        workflow,
        "verify-work acknowledgement is routing only",
        "acknowledgement",
        "routing only",
        "not verification evidence",
    )
    assert "cannot upgrade non-passed verifier/frontmatter/proof/check status to `passed`" in workflow
    assert "preserve verifier-owned status" in workflow
    _assert_semantic(workflow, "verify-work acknowledgement route", "gap planning", "follow-up")


def test_verify_work_record_verification_state_closeout_is_sequential() -> None:
    workflow = _read(WORKFLOWS_DIR / "verify-work.md")

    assert 'gpd --raw state record-verification --phase "${phase_number}"' in workflow
    _assert_semantic(
        workflow,
        "verify-work record-verification canonical reader",
        "record-verification",
        "canonical verification-status reader",
        "passed",
        "Verified",
        "canonical non-passed",
        "Blocked",
        "fails closed",
        "without changing state",
    )
    assert "Do not pass `--status` here or for acknowledgement" in workflow
    assert "legacy/admin overrides require no verifier frontmatter" in workflow
    _assert_semantic(workflow, "verify-work limitations cannot pass", "limitations", "passes")
    assert "--status passed|failed" not in workflow
    assert "Barrier: wait before state get/validate/repair" in workflow
    _assert_semantic(
        workflow,
        "verify-work state mutation validation is sequential",
        "never parallelize",
        "state mutation",
        "validation",
    )
