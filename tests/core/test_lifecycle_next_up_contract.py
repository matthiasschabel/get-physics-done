"""Canonical lifecycle next-up object contract tests."""

from __future__ import annotations

import json
from pathlib import Path

from gpd.core.phase_lifecycle import LifecycleNextUp, phase_lifecycle_decision
from gpd.core.state import default_state_dict


def _assert_legacy_aliases(next_up: LifecycleNextUp) -> dict[str, object]:
    payload = next_up.to_legacy_payload()
    assert next_up.as_legacy_next_up_dict() == payload
    assert next_up.to_compat_dict() == payload
    return payload


def _write_closed_phase_project(root: Path, *, next_phase_context: bool) -> None:
    gpd_dir = root / "GPD"
    phase_dir = gpd_dir / "phases" / "02-analysis"
    phase_dir.mkdir(parents=True)
    (gpd_dir / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
    (gpd_dir / "ROADMAP.md").write_text(
        "# Roadmap\n\n"
        "- [x] Phase 2: Analysis\n"
        "- [ ] Phase 3: Synthesis\n\n"
        "## Phase 2: Analysis\n\n"
        "## Phase 3: Synthesis\n",
        encoding="utf-8",
    )
    (phase_dir / "02-01-PLAN.md").write_text("# Plan\n", encoding="utf-8")
    (phase_dir / "02-01-SUMMARY.md").write_text("# Summary\n", encoding="utf-8")
    (phase_dir / "02-VERIFICATION.md").write_text("---\nstatus: passed\n---\n\n# Verification\n", encoding="utf-8")
    if next_phase_context:
        next_phase_dir = gpd_dir / "phases" / "03-synthesis"
        next_phase_dir.mkdir()
        (next_phase_dir / "03-CONTEXT.md").write_text("# Context\n", encoding="utf-8")
    state = default_state_dict()
    state["position"]["current_phase"] = "03"
    state["position"]["status"] = "Ready to plan"
    (gpd_dir / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def test_lifecycle_next_up_ready_local_transition_exposes_canonical_route_fields() -> None:
    cleanup = "gpd --raw phase checkpoint cleanup --phase 02 --namespace phase --policy successful-closeout"

    next_up = LifecycleNextUp.ready_local_transition(
        phase="02",
        closeout_command="gpd phase complete 02",
        cleanup_command=cleanup,
    )
    route = next_up.to_route_payload()

    assert next_up.status_class == "ready_for_local_closeout"
    assert route["transition_owner"] == "local_transition"
    assert route["current_blocking_gate"] == "none"
    assert route["local_transition_command"]["command"] == "gpd phase complete 02"
    assert route["local_transition_command"]["owner"] == "local_transition"
    assert route["primary_runtime_command"]["command"] == "gpd:suggest-next"
    assert route["after_local_runtime_command"] == route["primary_runtime_command"]
    assert route["secondary_local_commands"][0]["command"] == cleanup
    assert route["secondary_runtime_commands"] == []
    assert route["stage_stop_next_runtime_command"] == "gpd:suggest-next"
    assert route["stage_stop_also_available"] == []
    assert "Secondary local helper:" in route["rendered_markdown"]
    assert next_up.model_dump(mode="json")["primary"]["command"] == "gpd phase complete 02"
    assert next_up.model_dump(mode="json")["primary_runtime_command"]["command"] == "gpd:suggest-next"

    payload = _assert_legacy_aliases(next_up)
    assert payload["primary"] == "gpd phase complete 02"
    assert payload["stage_stop_next_runtime_command"] == "gpd:suggest-next"


def test_lifecycle_next_up_blocked_runtime_exposes_canonical_route_fields() -> None:
    next_up = LifecycleNextUp.blocked_runtime(
        phase="02",
        blockers=["canonical verification report missing"],
        action="verify-work",
    )
    route = next_up.to_route_payload()

    assert next_up.status_class == "needs_verification"
    assert route["transition_owner"] == "runtime"
    assert route["current_blocking_gate"] == "verification_missing"
    assert route["primary_runtime_command"]["action"] == "verify-work"
    assert route["primary_runtime_command"]["command"] == "gpd:verify-work 02"
    assert route["local_transition_command"] is None
    assert route["after_local_runtime_command"] is None
    assert route["secondary_runtime_commands"] == []
    assert route["secondary_local_commands"] == []
    assert route["stage_stop_next_runtime_command"] == "gpd:verify-work 02"

    payload = _assert_legacy_aliases(next_up)
    assert payload["primary"] == "gpd:verify-work 02"
    assert payload["rendered_markdown"] == "## > Next Up\nPrimary: `gpd:verify-work 02`"


def test_lifecycle_next_up_closed_runtime_routes_next_phase_from_context_class() -> None:
    missing_context = LifecycleNextUp.closed_runtime(
        phase="02",
        next_phase="03",
        status_class="closed_needs_milestone_audit",
        next_phase_context_class="missing_context",
    )
    planned = LifecycleNextUp.closed_runtime(
        phase="02",
        next_phase="03",
        status_class="closed_needs_milestone_audit",
        next_phase_context_class="planned",
    )

    missing_route = missing_context.to_route_payload()
    assert missing_context.status_class == "closed_ready_next_phase"
    assert missing_route["transition_owner"] == "runtime"
    assert missing_route["current_blocking_gate"] == "none"
    assert missing_route["next_phase_context_class"] == "missing_context"
    assert missing_route["primary_runtime_command"]["command"] == "gpd:discuss-phase 03"
    assert [command["command"] for command in missing_route["secondary_runtime_commands"]] == [
        "gpd:plan-phase 03",
        "gpd:suggest-next",
    ]
    assert missing_route["stage_stop_next_runtime_command"] == "gpd:discuss-phase 03"
    assert missing_route["stage_stop_also_available"] == ["gpd:plan-phase 03", "gpd:suggest-next"]

    planned_route = planned.to_route_payload()
    assert planned_route["next_phase_context_class"] == "planned"
    assert planned_route["primary_runtime_command"]["command"] == "gpd:plan-phase 03"
    assert [command["command"] for command in planned_route["secondary_runtime_commands"]] == [
        "gpd:discuss-phase 03",
        "gpd:suggest-next",
    ]

    payload = _assert_legacy_aliases(missing_context)
    assert payload["primary"] == "gpd:discuss-phase 03"
    assert payload["stage_stop_also_available"] == ["gpd:plan-phase 03", "gpd:suggest-next"]


def test_lifecycle_next_up_closed_runtime_models_phase4_milestone_order() -> None:
    audit = LifecycleNextUp.closed_runtime(
        phase="02",
        next_phase=None,
        status_class="closed_needs_milestone_audit",
    )
    archive = LifecycleNextUp.closed_runtime(
        phase="02",
        next_phase=None,
        status_class="closed_ready_for_milestone_archive",
        milestone_version="v1.0",
    )
    archived = LifecycleNextUp.closed_runtime(
        phase="02",
        next_phase=None,
        status_class="archived_ready_for_next_milestone",
    )

    assert audit.status_class == "closed_needs_milestone_audit"
    assert audit.primary.command == "gpd:audit-milestone"
    assert audit.to_route_payload()["primary_runtime_command"]["command"] == "gpd:audit-milestone"
    assert archive.status_class == "closed_ready_for_milestone_archive"
    assert archive.primary.command == "gpd:complete-milestone v1.0"
    assert archived.status_class == "archived_ready_for_next_milestone"
    assert archived.primary.command == "gpd:new-milestone"
    assert audit.to_route_payload()["secondary_runtime_commands"] == []
    assert "gpd phase complete" not in audit.rendered_markdown


def test_closed_phase_decision_routes_next_phase_from_context_presence(tmp_path: Path) -> None:
    missing_context_root = tmp_path / "missing"
    has_context_root = tmp_path / "context"
    _write_closed_phase_project(missing_context_root, next_phase_context=False)
    _write_closed_phase_project(has_context_root, next_phase_context=True)

    missing = phase_lifecycle_decision(missing_context_root, "02")
    has_context = phase_lifecycle_decision(has_context_root, "02")

    assert missing.lifecycle_next_up is not None
    missing_route = missing.lifecycle_next_up.to_route_payload()
    assert missing_route["next_phase_context_class"] == "missing_context"
    assert missing_route["primary_runtime_command"]["command"] == "gpd:discuss-phase 03"
    assert missing_route["stage_stop_also_available"] == ["gpd:plan-phase 03", "gpd:suggest-next"]
    assert missing.primary_command == "gpd:discuss-phase 03"

    assert has_context.lifecycle_next_up is not None
    context_route = has_context.lifecycle_next_up.to_route_payload()
    assert context_route["next_phase_context_class"] == "has_context"
    assert context_route["primary_runtime_command"]["command"] == "gpd:plan-phase 03"
    assert context_route["stage_stop_also_available"] == ["gpd:discuss-phase 03", "gpd:suggest-next"]
    assert has_context.primary_command == "gpd:plan-phase 03"
