"""Read-only phase lifecycle decision helper tests."""

from __future__ import annotations

import json
from pathlib import Path

from gpd.core.phase_closeout import phase_closeout_readiness
from gpd.core.phase_lifecycle import phase_lifecycle_decision
from gpd.core.state import default_state_dict

_FORBIDDEN_NEXT_UP_RELOAD_FRAGMENTS = (
    "gpd --raw init",
    "--raw init",
    "gpd --raw stage field-access",
    "--raw stage field-access",
)


def _write_phase_project(
    root: Path,
    *,
    summaries: tuple[str, ...] = ("02-01-SUMMARY.md", "02-02-SUMMARY.md"),
    verification_status: str | None = "passed",
    proof_bearing: bool = False,
    recovery: bool = False,
    bounded_segment: bool = False,
    state_current_phase: str | None = "02",
    state_status: str | None = "Verified",
    roadmap_closed: bool = False,
) -> Path:
    gpd_dir = root / "GPD"
    phase_dir = gpd_dir / "phases" / "02-analysis"
    phase_dir.mkdir(parents=True)
    (gpd_dir / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
    marker = "x" if roadmap_closed else " "
    (gpd_dir / "ROADMAP.md").write_text(
        "# Roadmap\n\n"
        f"- [{marker}] Phase 2: Analysis\n"
        "- [ ] Phase 3: Synthesis\n\n"
        "## Phase 2: Analysis\n\n"
        "## Phase 3: Synthesis\n",
        encoding="utf-8",
    )
    for index in range(1, 3):
        proof_flag = "proof_bearing: true\n" if proof_bearing and index == 1 else ""
        (phase_dir / f"02-{index:02d}-PLAN.md").write_text(
            f"---\nwave: {index}\n{proof_flag}---\n\n# Plan {index}\n",
            encoding="utf-8",
        )
    for summary_name in summaries:
        (phase_dir / summary_name).write_text(f"# {summary_name}\n", encoding="utf-8")
    if verification_status is not None:
        (phase_dir / "02-VERIFICATION.md").write_text(
            f"---\nstatus: {verification_status}\nscore: lifecycle test\n---\n\n# Verification\n",
            encoding="utf-8",
        )
    if recovery:
        (phase_dir / "RECOVERY-02.md").write_text("# Recovery\n", encoding="utf-8")

    state = default_state_dict()
    state["position"]["current_phase"] = state_current_phase
    state["position"]["current_phase_name"] = "Analysis" if state_current_phase == "02" else "Synthesis"
    state["position"]["current_plan"] = "02" if state_current_phase == "02" else None
    state["position"]["total_plans_in_phase"] = 2 if state_current_phase == "02" else None
    state["position"]["status"] = state_status
    if bounded_segment:
        state["continuation"]["bounded_segment"] = {
            "resume_file": "GPD/phases/02-analysis/.continue-here.md",
            "phase": "02",
            "plan": "02",
            "segment_id": "seg-02-02",
            "segment_status": "paused",
        }
    (gpd_dir / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return phase_dir


def test_lifecycle_decision_ready_closeout_matches_closeout_readiness_and_stays_read_only(tmp_path: Path) -> None:
    _write_phase_project(tmp_path)
    before_roadmap = (tmp_path / "GPD" / "ROADMAP.md").read_text(encoding="utf-8")
    before_state = (tmp_path / "GPD" / "state.json").read_text(encoding="utf-8")

    decision = phase_lifecycle_decision(tmp_path, "2")
    closeout = phase_closeout_readiness(tmp_path, "02", require_verification=True)

    assert decision.decision == "ready_for_closeout"
    assert decision.primary_command == "gpd phase complete 02"
    assert decision.primary_owner == "local_transition"
    assert decision.closeout_readiness == closeout
    assert decision.next_up == closeout.next_up
    assert decision.lifecycle_class == "ready_for_local_closeout"
    assert decision.lifecycle_next_up is not None
    assert closeout.lifecycle_next_up is not None
    assert decision.lifecycle_next_up.primary.command == decision.primary_command
    assert decision.lifecycle_next_up.primary.owner == decision.primary_owner
    assert decision.next_up == decision.lifecycle_next_up.as_legacy_next_up_dict()
    assert closeout.next_up == closeout.lifecycle_next_up.as_legacy_next_up_dict()
    assert decision.next_up["commands"][0]["owner"] == "local_transition"
    assert decision.next_up["commands"][0]["requires_user_initiated_runtime_command"] is False
    assert decision.next_up["primary_command"]["owner"] == "local_transition"
    assert decision.next_up["primary_command"]["command"] == "gpd phase complete 02"
    assert decision.next_up["after_this_completes"]["owner"] == "runtime"
    assert decision.next_up["after_this_completes"]["command"] == "gpd:suggest-next"
    assert decision.next_up["stage_stop_next_runtime_command"] == "gpd:suggest-next"
    assert decision.next_up["stage_stop_also_available"] == []
    assert decision.next_up["rendered_markdown"].startswith("## > Next Up\nPrimary local transition:")
    assert "**After this completes:** `gpd:suggest-next`" in decision.next_up["rendered_markdown"]
    assert all(
        fragment not in decision.next_up["rendered_markdown"] for fragment in _FORBIDDEN_NEXT_UP_RELOAD_FRAGMENTS
    )
    assert (tmp_path / "GPD" / "ROADMAP.md").read_text(encoding="utf-8") == before_roadmap
    assert (tmp_path / "GPD" / "state.json").read_text(encoding="utf-8") == before_state


def test_lifecycle_decision_counts_only_matching_summaries(tmp_path: Path) -> None:
    _write_phase_project(tmp_path, summaries=("02-01-SUMMARY.md", "02-99-SUMMARY.md"))

    decision = phase_lifecycle_decision(tmp_path, "02")

    assert decision.decision == "needs_execution"
    assert decision.summary_count == 1
    assert decision.closeout_readiness.summary_count == 1
    assert decision.closeout_readiness.all_plans_complete is False
    assert "02-02-PLAN.md" in decision.closeout_readiness.incomplete_plans
    assert any("phase summaries incomplete: 1/2" in blocker for blocker in decision.closeout_blockers)
    assert decision.primary_command == "gpd:execute-phase 02"
    assert decision.lifecycle_class == "needs_execution"
    assert decision.lifecycle_next_up is not None
    assert decision.lifecycle_next_up.primary.action == "execute-phase"
    assert decision.next_up["primary"] == "gpd:execute-phase 02"
    assert decision.next_up["primary_command"]["action"] == "execute-phase"
    assert decision.next_up["primary_command"]["owner"] == "runtime"
    assert decision.next_up["stage_stop_next_runtime_command"] == "gpd:execute-phase 02"
    assert decision.next_up["rendered_markdown"] == "## > Next Up\nPrimary: `gpd:execute-phase 02`"


def test_lifecycle_decision_missing_verification_routes_to_runtime_verify_work(tmp_path: Path) -> None:
    _write_phase_project(tmp_path, verification_status=None, state_status="Phase complete - ready for verification")

    decision = phase_lifecycle_decision(tmp_path, "02")

    assert decision.decision == "needs_verification"
    assert decision.verification_routing_status == "missing"
    assert decision.primary_command == "gpd:verify-work 02"
    assert decision.primary_owner == "runtime"
    assert decision.lifecycle_class == "needs_verification"
    assert decision.lifecycle_next_up is not None
    assert decision.lifecycle_next_up.primary.action == "verify-work"
    assert decision.next_up["primary"] == "gpd:verify-work 02"
    assert decision.next_up["commands"][0]["owner"] == "runtime"
    assert decision.next_up["primary_command"]["action"] == "verify-work"
    assert decision.next_up["primary_command"]["owner"] == "runtime"
    assert decision.next_up["stage_stop_next_runtime_command"] == "gpd:verify-work 02"
    assert decision.next_up["rendered_markdown"] == "## > Next Up\nPrimary: `gpd:verify-work 02`"


def test_lifecycle_decision_proof_redteam_blocker_uses_runtime_verify_work(tmp_path: Path) -> None:
    _write_phase_project(tmp_path, proof_bearing=True)

    decision = phase_lifecycle_decision(tmp_path, "02")

    assert decision.decision == "blocked_closeout"
    assert decision.lifecycle_class == "needs_verification"
    assert decision.closeout_readiness.proof_redteam_required is True
    assert decision.closeout_readiness.proof_redteam_ready is False
    assert "proof-bearing work requires a passed proof-redteam artifact" in decision.closeout_blockers
    assert decision.next_up["primary"] == "gpd:verify-work 02"
    assert decision.next_up["primary_command"]["action"] == "verify-work"
    assert decision.next_up["stage_stop_next_runtime_command"] == "gpd:verify-work 02"


def test_lifecycle_decision_active_bounded_segment_blocks_with_resume_next_up(tmp_path: Path) -> None:
    _write_phase_project(tmp_path, bounded_segment=True, verification_status=None)

    decision = phase_lifecycle_decision(tmp_path, "02")

    assert decision.decision == "blocked_closeout"
    assert decision.lifecycle_class == "blocked_closeout"
    assert decision.closeout_readiness.active_bounded_segment is True
    assert any("active bounded segment" in blocker for blocker in decision.closeout_blockers)
    assert decision.primary_command == "gpd:resume-work"
    assert decision.primary_owner == "runtime"
    assert decision.next_up["commands"][0]["role"] == "primary"
    assert decision.next_up["primary_command"]["action"] == "resume-work"
    assert decision.next_up["stage_stop_next_runtime_command"] == "gpd:resume-work"
    assert decision.next_up["rendered_markdown"] == "## > Next Up\nPrimary: `gpd:resume-work`"


def test_lifecycle_decision_preserves_recovery_artifacts_and_suppresses_cleanup(tmp_path: Path) -> None:
    _write_phase_project(tmp_path, recovery=True)

    decision = phase_lifecycle_decision(tmp_path, "02")

    assert decision.decision == "ready_for_closeout"
    assert decision.closeout_readiness.preserve_checkpoint_tags is True
    assert decision.closeout_readiness.cleanup_command is None
    assert decision.closeout_readiness.recovery_artifacts == ["GPD/phases/02-analysis/RECOVERY-02.md"]
    assert decision.next_up["secondary"] == []


def test_lifecycle_decision_closed_phase_advances_to_next_phase_action(tmp_path: Path) -> None:
    _write_phase_project(
        tmp_path,
        state_current_phase="03",
        state_status="Ready to plan",
        roadmap_closed=True,
    )

    decision = phase_lifecycle_decision(tmp_path, "02")

    assert decision.decision == "closed_ready_next_phase"
    assert decision.lifecycle_class == "closed_ready_next_phase"
    assert decision.phase_closed is True
    assert decision.roadmap_complete is True
    assert decision.next_phase == "03"
    assert decision.closeout_ready is False
    assert decision.primary_command == "gpd:plan-phase 03"
    assert decision.primary_owner == "runtime"
    assert decision.lifecycle_next_up is not None
    assert decision.lifecycle_next_up.primary.command == "gpd:plan-phase 03"
    assert decision.closeout_readiness.next_up["primary"] == "gpd:plan-phase 03"
    assert decision.next_up["primary_command"]["action"] == "plan-phase"
    assert decision.next_up["primary_command"]["owner"] == "runtime"
    assert decision.next_up["stage_stop_next_runtime_command"] == "gpd:plan-phase 03"
    assert "gpd phase complete 02" not in decision.next_up["rendered_markdown"]


def test_lifecycle_decision_closed_milestone_routes_runtime_audit_not_stale_transition(tmp_path: Path) -> None:
    _write_phase_project(
        tmp_path,
        state_current_phase=None,
        state_status="milestone complete",
        roadmap_closed=True,
    )

    decision = phase_lifecycle_decision(tmp_path, "02")

    assert decision.decision == "closed_milestone_complete"
    assert decision.lifecycle_class == "closed_needs_milestone_audit"
    assert decision.phase_closed is True
    assert decision.primary_command == "gpd:audit-milestone"
    assert decision.primary_owner == "runtime"
    assert decision.next_up["primary_command"]["owner"] == "runtime"
    assert decision.next_up["stage_stop_next_runtime_command"] == "gpd:audit-milestone"
    assert decision.next_up["rendered_markdown"] == "## > Next Up\nPrimary: `gpd:audit-milestone`"
    assert "gpd phase complete 02" not in decision.next_up["rendered_markdown"]


def test_lifecycle_decision_closed_milestone_routes_archive_only_after_passed_audit(tmp_path: Path) -> None:
    _write_phase_project(
        tmp_path,
        state_current_phase=None,
        state_status="milestone complete",
        roadmap_closed=True,
    )
    (tmp_path / "GPD" / "v1.0-MILESTONE-AUDIT.md").write_text(
        "---\nstatus: passed\n---\n\n# Audit\n",
        encoding="utf-8",
    )

    decision = phase_lifecycle_decision(tmp_path, "02")

    assert decision.decision == "closed_milestone_complete"
    assert decision.lifecycle_class == "closed_ready_for_milestone_archive"
    assert decision.phase_closed is True
    assert decision.primary_action == "complete-milestone"
    assert decision.primary_command == "gpd:complete-milestone v1.0"
    assert decision.primary_owner == "runtime"
    assert decision.next_up["stage_stop_next_runtime_command"] == "gpd:complete-milestone v1.0"
    assert decision.next_up["rendered_markdown"] == "## > Next Up\nPrimary: `gpd:complete-milestone v1.0`"
    assert "gpd:audit-milestone" not in decision.next_up["rendered_markdown"]
