"""Read-only closeout readiness checks for phase lifecycle helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gpd.cli import app
from gpd.core.phase_closeout import phase_closeout_readiness
from gpd.core.proof_redteam import build_proof_redteam_skeleton
from gpd.core.state import default_state_dict


class _StableCliRunner(CliRunner):
    def invoke(self, *args, **kwargs):
        kwargs.setdefault("color", False)
        return super().invoke(*args, **kwargs)


RUNNER = _StableCliRunner()
REPO_ROOT = Path(__file__).resolve().parents[2]
EXECUTE_PHASE_STAGE_DIR = REPO_ROOT / "src/gpd/specs/workflows/execute-phase"
_FORBIDDEN_NEXT_UP_RELOAD_FRAGMENTS = (
    "gpd --raw init",
    "--raw init",
    "gpd --raw stage field-access",
    "--raw stage field-access",
)


def _write_phase_project(
    root: Path,
    *,
    summaries: int = 2,
    verification_status: str | None = "passed",
    malformed_verification: bool = False,
    proof_bearing: bool = False,
    recovery: bool = False,
) -> Path:
    gpd_dir = root / "GPD"
    phase_dir = gpd_dir / "phases" / "02-analysis"
    phase_dir.mkdir(parents=True)
    (gpd_dir / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
    (gpd_dir / "ROADMAP.md").write_text("# Roadmap\n\n## Phase 2: Analysis\n", encoding="utf-8")
    for index in range(1, 3):
        proof_flag = "proof_bearing: true\n" if proof_bearing and index == 1 else ""
        (phase_dir / f"02-{index:02d}-PLAN.md").write_text(
            f"---\nwave: {index}\n{proof_flag}---\n\n# Plan {index}\n",
            encoding="utf-8",
        )
    for index in range(1, summaries + 1):
        (phase_dir / f"02-{index:02d}-SUMMARY.md").write_text(f"# Summary {index}\n", encoding="utf-8")
    if malformed_verification:
        (phase_dir / "02-VERIFICATION.md").write_text("---\nstatus: [\n---\n\n# Bad\n", encoding="utf-8")
    elif verification_status is not None:
        (phase_dir / "02-VERIFICATION.md").write_text(
            f"---\nstatus: {verification_status}\nscore: closeout test\n---\n\n# Verification\n",
            encoding="utf-8",
        )
    if recovery:
        (phase_dir / "RECOVERY-02.md").write_text("# Recovery\n", encoding="utf-8")
    return phase_dir


def _write_state(root: Path, *, bounded_segment: bool = False) -> None:
    state = default_state_dict()
    if bounded_segment:
        state["continuation"]["bounded_segment"] = {
            "resume_file": "GPD/phases/02-analysis/.continue-here.md",
            "phase": "02",
            "plan": "01",
            "segment_id": "seg-02-01",
            "segment_status": "paused",
            "waiting_for_review": True,
        }
    (root / "GPD" / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def test_closeout_readiness_all_summaries_and_passed_verification_is_ready(tmp_path: Path) -> None:
    _write_phase_project(tmp_path)
    _write_state(tmp_path)
    before_roadmap = (tmp_path / "GPD" / "ROADMAP.md").read_text(encoding="utf-8")
    before_state = (tmp_path / "GPD" / "state.json").read_text(encoding="utf-8")

    result = phase_closeout_readiness(tmp_path, "2", require_verification=True)

    assert result.ready is True
    assert result.mutation_allowed is True
    assert result.read_only is True
    assert result.mutated is False
    assert result.plan_count == 2
    assert result.summary_count == 2
    assert result.verification_status == "passed"
    assert result.closeout_command == "gpd phase complete 02"
    assert (
        result.cleanup_command
        == "gpd --raw phase checkpoint cleanup --phase 02 --namespace phase --policy successful-closeout"
    )
    assert result.next_up["status"] == "ready"
    assert result.next_up["primary"] == "gpd phase complete 02"
    assert result.next_up["primary_owner"] == "local_transition"
    commands = result.next_up["commands"]
    assert isinstance(commands, list)
    assert commands[0]["command"] == "gpd phase complete 02"
    assert commands[0]["owner"] == "local_transition"
    assert commands[0]["role"] == "primary"
    assert commands[0]["requires_user_initiated_runtime_command"] is False
    assert result.next_up["primary_command"]["owner"] == "local_transition"
    assert result.next_up["primary_command"]["command"] == "gpd phase complete 02"
    assert result.next_up["after_this_completes"]["owner"] == "runtime"
    assert result.next_up["after_this_completes"]["command"] == "gpd:suggest-next"
    assert result.next_up["stage_stop_next_runtime_command"] == "gpd:suggest-next"
    assert result.next_up["stage_stop_also_available"] == []
    secondary = result.next_up["secondary"]
    assert isinstance(secondary, list)
    assert secondary[0]["command"] == result.cleanup_command
    assert secondary[0]["owner"] == "local_helper"
    assert secondary[0]["role"] == "secondary"
    secondary_commands = result.next_up["secondary_commands"]
    assert isinstance(secondary_commands, list)
    assert secondary_commands[0]["command"] == result.cleanup_command
    assert secondary_commands[0]["owner"] == "local_helper"
    rendered = result.next_up["rendered_markdown"]
    assert rendered.startswith("## > Next Up\nPrimary local transition:")
    assert "**After this completes:** `gpd:suggest-next`" in rendered
    assert "Secondary local helper:" in rendered
    assert all(fragment not in rendered for fragment in _FORBIDDEN_NEXT_UP_RELOAD_FRAGMENTS)
    assert result.closeout_command_hint is not None
    assert result.closeout_command_hint["owner"] == "local_transition"
    assert result.cleanup_command_hint is not None
    assert result.cleanup_command_hint["owner"] == "local_helper"
    assert (tmp_path / "GPD" / "ROADMAP.md").read_text(encoding="utf-8") == before_roadmap
    assert (tmp_path / "GPD" / "state.json").read_text(encoding="utf-8") == before_state


def test_closeout_readiness_missing_summary_blocks_closeout(tmp_path: Path) -> None:
    _write_phase_project(tmp_path, summaries=1)

    result = phase_closeout_readiness(tmp_path, "02", require_verification=True)

    assert result.ready is False
    assert result.mutation_allowed is False
    assert result.all_plans_complete is False
    assert "02-02-PLAN.md" in result.incomplete_plans
    assert any("summaries incomplete" in blocker for blocker in result.blockers)
    assert result.next_up["primary"] == "gpd:execute-phase 02"
    assert result.next_up["primary_command"]["action"] == "execute-phase"
    assert result.next_up["primary_command"]["owner"] == "runtime"
    assert result.next_up["stage_stop_next_runtime_command"] == "gpd:execute-phase 02"


def test_closeout_readiness_missing_verification_blocks_required_closeout(tmp_path: Path) -> None:
    _write_phase_project(tmp_path, verification_status=None)
    (tmp_path / "GPD" / "CHECKPOINTS.md").write_text("# Generated checkpoint shelf\n", encoding="utf-8")

    result = phase_closeout_readiness(tmp_path, "02", require_verification=True)

    assert result.ready is False
    assert result.verification_routing_status == "missing"
    assert "canonical verification report missing" in result.blockers
    assert result.next_up["primary"] == "gpd:verify-work 02"
    assert result.next_up["primary_owner"] == "runtime"
    commands = result.next_up["commands"]
    assert isinstance(commands, list)
    assert commands[0]["owner"] == "runtime"
    assert commands[0]["role"] == "primary"
    assert result.next_up["primary_command"]["action"] == "verify-work"
    assert result.next_up["primary_command"]["owner"] == "runtime"
    assert result.next_up["stage_stop_next_runtime_command"] == "gpd:verify-work 02"
    assert result.next_up["rendered_markdown"] == "## > Next Up\nPrimary: `gpd:verify-work 02`"


@pytest.mark.parametrize("status", ["gaps_found", "human_needed", "expert_needed"])
def test_closeout_readiness_non_passing_verification_blocks_required_closeout(
    tmp_path: Path,
    status: str,
) -> None:
    _write_phase_project(tmp_path, verification_status=status)

    result = phase_closeout_readiness(tmp_path, "02", require_verification=True)

    assert result.ready is False
    assert result.verification_status == status
    assert any("must have top-level frontmatter status 'passed'" in blocker for blocker in result.blockers)
    assert result.next_up["primary"] == "gpd:verify-work 02"
    assert result.next_up["primary_command"]["action"] == "verify-work"
    assert result.next_up["primary_command"]["owner"] == "runtime"
    assert result.next_up["stage_stop_next_runtime_command"] == "gpd:verify-work 02"


def test_closeout_readiness_malformed_verification_blocks_closeout(tmp_path: Path) -> None:
    _write_phase_project(tmp_path, malformed_verification=True)

    result = phase_closeout_readiness(tmp_path, "02", require_verification=True)

    assert result.ready is False
    assert result.verification_routing_status == "unparseable"
    assert any("canonical verification report blocked" in blocker for blocker in result.blockers)


def test_closeout_readiness_uses_top_level_verification_frontmatter_only(tmp_path: Path) -> None:
    phase_dir = _write_phase_project(tmp_path)
    (phase_dir / "02-VERIFICATION.md").write_text(
        "---\n"
        "status: passed\n"
        "score: closeout test\n"
        "---\n\n"
        "contract_results:\n"
        "  claims:\n"
        "    claim-a:\n"
        "      status: gaps_found\n",
        encoding="utf-8",
    )

    result = phase_closeout_readiness(tmp_path, "02", require_verification=True)

    assert result.ready is True
    assert result.verification_status == "passed"
    assert result.verification_routing_status == "passed"
    assert not any("canonical verification report" in blocker for blocker in result.blockers)


def test_closeout_readiness_active_bounded_segment_blocks_closeout(tmp_path: Path) -> None:
    _write_phase_project(tmp_path)
    _write_state(tmp_path, bounded_segment=True)

    result = phase_closeout_readiness(tmp_path, "02", require_verification=True)

    assert result.ready is False
    assert result.active_bounded_segment is True
    assert any("active bounded segment" in blocker for blocker in result.blockers)
    assert result.next_up["primary"] == "gpd:resume-work"
    assert result.next_up["primary_owner"] == "runtime"
    assert result.next_up["primary_command"]["action"] == "resume-work"
    assert result.next_up["primary_command"]["owner"] == "runtime"
    assert result.next_up["stage_stop_next_runtime_command"] == "gpd:resume-work"


def test_closeout_readiness_preserves_checkpoint_tags_when_recovery_artifacts_exist(tmp_path: Path) -> None:
    _write_phase_project(tmp_path, recovery=True)

    result = phase_closeout_readiness(tmp_path, "02", require_verification=True)

    assert result.ready is True
    assert result.preserve_checkpoint_tags is True
    assert result.cleanup_command is None
    assert result.next_up["primary_owner"] == "local_transition"
    assert result.next_up["secondary"] == []
    assert result.next_up["secondary_commands"] == []
    assert result.next_up["after_this_completes"]["command"] == "gpd:suggest-next"
    assert result.recovery_artifacts == ["GPD/phases/02-analysis/RECOVERY-02.md"]


def test_closeout_readiness_blocks_proof_bearing_work_without_passed_proof_redteam(tmp_path: Path) -> None:
    _write_phase_project(tmp_path, proof_bearing=True)

    result = phase_closeout_readiness(tmp_path, "02", require_verification=True)

    assert result.ready is False
    assert result.proof_redteam_required is True
    assert result.proof_redteam_ready is False
    assert "proof-bearing work requires a passed proof-redteam artifact" in result.blockers
    assert result.next_up["primary"] == "gpd:verify-work 02"
    assert result.next_up["primary_command"]["action"] == "verify-work"
    assert result.next_up["stage_stop_next_runtime_command"] == "gpd:verify-work 02"


def test_closeout_readiness_blocks_non_passed_proof_redteam_artifact(tmp_path: Path) -> None:
    phase_dir = _write_phase_project(tmp_path, proof_bearing=True)
    skeleton = build_proof_redteam_skeleton(
        claim_id="claim-a",
        proof_artifact_paths=["GPD/phases/02-analysis/02-01-PLAN.md"],
        status="gaps_found",
    )
    (phase_dir / "02-01-PROOF-REDTEAM.md").write_text(skeleton.markdown_draft, encoding="utf-8")

    result = phase_closeout_readiness(tmp_path, "02", require_verification=True)

    assert result.ready is False
    assert result.proof_redteam_required is True
    assert result.proof_redteam_ready is False
    assert result.proof_redteam_artifacts == ["GPD/phases/02-analysis/02-01-PROOF-REDTEAM.md"]
    assert any("reports status 'gaps_found'; expected 'passed'" in blocker for blocker in result.blockers)


def test_phase_closeout_readiness_cli_emits_json_and_nonzero_when_blocked(tmp_path: Path) -> None:
    _write_phase_project(tmp_path, verification_status=None)

    result = RUNNER.invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "phase",
            "closeout-readiness",
            "02",
            "--require-verification",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["ready"] is False
    assert payload["read_only"] is True
    assert payload["mutated"] is False


def test_phase_help_lists_closeout_readiness_not_removed_verification_summary() -> None:
    result = RUNNER.invoke(app, ["phase", "--help"])

    assert result.exit_code == 0
    assert "closeout-readiness" in result.output
    assert "verification-summary" not in result.output


def test_execute_phase_closeout_spec_is_readiness_transition_only() -> None:
    workflow = (EXECUTE_PHASE_STAGE_DIR / "closeout.md").read_text(encoding="utf-8")
    manifest = json.loads((EXECUTE_PHASE_STAGE_DIR.parent / "execute-phase-stage-manifest.json").read_text())
    closeout_stage = next(stage for stage in manifest["stages"] if stage["id"] == "closeout")
    conditional_authorities = {
        authority for condition in closeout_stage["conditional_authorities"] for authority in condition["authorities"]
    }

    assert "does not spawn verifiers, close gaps, run consistency checks, or decide scientific status" in workflow
    assert (
        "`verification_handoff` or `gap_reverification` produced a validated canonical verification report" in workflow
    )
    assert "`consistency_check` completed through its child_gate" in workflow
    assert "gpd --raw phase closeout-readiness" in workflow
    assert "--require-verification" in workflow
    assert 'gpd phase complete "${phase_number}"' in workflow
    assert workflow.index("gpd --raw phase closeout-readiness") < workflow.index('gpd phase complete "${phase_number}"')
    assert "Do not repair blockers, update roadmap/state, or clean checkpoints from this stage." in workflow
    assert closeout_stage["loaded_authorities"] == ["workflows/execute-phase/closeout.md"]
    assert {"workflows/transition.md", "templates/state-machine.md"} <= conditional_authorities
