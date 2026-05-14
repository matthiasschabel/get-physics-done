"""Canonical lifecycle next-up object contract tests."""

from __future__ import annotations

from gpd.core.phase_lifecycle import LifecycleNextUp

_LEGACY_NEXT_UP_KEYS = {
    "status",
    "primary",
    "primary_owner",
    "primary_label",
    "commands",
    "primary_command",
    "after_this_completes",
    "secondary",
    "secondary_commands",
    "rendered_markdown",
    "stage_stop_next_runtime_command",
    "stage_stop_also_available",
}


def test_lifecycle_next_up_ready_local_transition_preserves_legacy_json_fields() -> None:
    cleanup = "gpd --raw phase checkpoint cleanup --phase 02 --namespace phase --policy successful-closeout"

    next_up = LifecycleNextUp.ready_local_transition(
        phase="02",
        closeout_command="gpd phase complete 02",
        cleanup_command=cleanup,
    )
    payload = next_up.as_legacy_next_up_dict()

    assert _LEGACY_NEXT_UP_KEYS <= set(payload)
    assert next_up.status_class == "ready_for_local_closeout"
    assert next_up.primary.command == "gpd phase complete 02"
    assert next_up.primary.owner == "local_transition"
    assert next_up.after_this_completes is not None
    assert next_up.after_this_completes.command == "gpd:suggest-next"
    assert payload["primary"] == "gpd phase complete 02"
    assert payload["primary_command"] == payload["primary_next_command"]
    assert payload["after_this_completes"] == payload["after_this_completes_next_command"]
    assert payload["secondary_commands"] == payload["secondary_next_commands"]
    assert payload["commands"][0]["owner"] == "local_transition"
    assert payload["commands"][0]["requires_user_initiated_runtime_command"] is False
    assert payload["secondary"][0]["owner"] == "local_helper"
    assert payload["secondary_commands"][0]["command"] == cleanup
    assert payload["stage_stop_next_runtime_command"] == "gpd:suggest-next"
    assert payload["stage_stop_also_available"] == []
    assert "Secondary local helper:" in payload["rendered_markdown"]
    assert next_up.model_dump(mode="json")["primary"]["command"] == "gpd phase complete 02"


def test_lifecycle_next_up_blocked_runtime_preserves_legacy_json_fields() -> None:
    next_up = LifecycleNextUp.blocked_runtime(
        phase="02",
        blockers=["canonical verification report missing"],
        action="verify-work",
    )
    payload = next_up.to_compat_dict()

    assert (_LEGACY_NEXT_UP_KEYS - {"after_this_completes"}) <= set(payload)
    assert "after_this_completes" not in payload
    assert next_up.status_class == "needs_verification"
    assert next_up.primary.action == "verify-work"
    assert payload["status"] == "blocked"
    assert payload["blockers"] == ["canonical verification report missing"]
    assert payload["primary"] == "gpd:verify-work 02"
    assert payload["primary_owner"] == "runtime"
    assert payload["commands"][0]["role"] == "primary"
    assert payload["secondary"] == []
    assert payload["secondary_commands"] == []
    assert payload["stage_stop_next_runtime_command"] == "gpd:verify-work 02"
    assert payload["rendered_markdown"] == "## > Next Up\nPrimary: `gpd:verify-work 02`"


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
    next_phase = LifecycleNextUp.closed_runtime(
        phase="02",
        next_phase="03",
        status_class="closed_needs_milestone_audit",
    )

    assert audit.status_class == "closed_needs_milestone_audit"
    assert audit.primary.command == "gpd:audit-milestone"
    assert archive.status_class == "closed_ready_for_milestone_archive"
    assert archive.primary.command == "gpd:complete-milestone v1.0"
    assert archived.status_class == "archived_ready_for_next_milestone"
    assert archived.primary.command == "gpd:new-milestone"
    assert next_phase.status_class == "closed_ready_next_phase"
    assert next_phase.primary.command == "gpd:plan-phase 03"
    assert "gpd phase complete" not in audit.rendered_markdown
