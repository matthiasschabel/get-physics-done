"""Focused assertions for typed-return prompt cleanup."""

from __future__ import annotations

from pathlib import Path

from tests.core.test_spawn_contracts import _find_single_task

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"
ROADMAPPER = REPO_ROOT / "src/gpd/agents/gpd-roadmapper.md"
PLANNER = REPO_ROOT / "src/gpd/agents/gpd-planner.md"
PHASE_RESEARCHER = REPO_ROOT / "src/gpd/agents/gpd-phase-researcher.md"
EXECUTOR_COMPLETION = REPO_ROOT / "src/gpd/specs/references/execution/executor-completion.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _yaml_envelope(text: str) -> str:
    return text.split("```yaml\n", 1)[1].split("```", 1)[0]


def test_roadmapper_prompt_example_includes_complete_base_return_fields() -> None:
    roadmapper = _read(ROADMAPPER)
    envelope = _yaml_envelope(roadmapper)

    assert envelope.startswith("gpd_return:\n")
    assert "status: completed" in envelope
    assert "files_written:\n    - GPD/ROADMAP.md\n    - GPD/STATE.md\n    - GPD/REQUIREMENTS.md" in envelope
    assert "issues: []" in envelope
    assert "next_actions:\n    - \"gpd:plan-phase 01\"" in envelope
    assert "phases_created: 4" in envelope


def test_new_project_roadmapper_task_block_requires_requirements_freshness_and_named_files_written() -> None:
    roadmapper_task = _find_single_task(WORKFLOWS_DIR / "new-project.md", "gpd-roadmapper")

    assert "gpd_return.files_written" in roadmapper_task.text
    assert "GPD/REQUIREMENTS.md" in roadmapper_task.text
    assert "do not rely on runtime completion text alone." in roadmapper_task.text
    assert "Write files first, then return." in roadmapper_task.text


def test_planner_tangent_guidance_routes_on_typed_checkpoint_status() -> None:
    planner = _read(PLANNER)

    assert "return `gpd_return.status: checkpoint` with the four options above instead of silently branching." in planner
    assert (
        "create the recommended main-line plan only and set `gpd_return.status: checkpoint` when multiple live alternatives still matter."
        in planner
    )
    assert "return `## CHECKPOINT REACHED` with the four options above instead of silently branching." not in planner
    assert "return `## CHECKPOINT REACHED` when multiple live alternatives still matter." not in planner


def test_phase_researcher_machine_readable_return_is_typed_first() -> None:
    researcher = _read(PHASE_RESEARCHER)

    assert "gpd_return:" in researcher
    assert "status: completed" in researcher
    assert "files_written:\n    - GPD/phases/03-spectral-form-factor/03-RESEARCH.md" in researcher
    assert "issues: []" in researcher
    assert "next_actions:\n    - \"gpd:plan-phase 03-spectral-form-factor\"" in researcher
    assert "confidence: HIGH" in researcher
    assert "Mapping: RESEARCH COMPLETE → completed, RESEARCH BLOCKED → blocked" not in researcher
    assert "Headings above are presentation only; route on gpd_return.status." in researcher


def test_executor_completion_spawned_handoff_example_keeps_base_fields_and_extensions() -> None:
    completion = _read(EXECUTOR_COMPLETION)

    assert "status: completed" in completion
    assert '    - "GPD/phases/XX-name/{phase}-{plan}-SUMMARY.md"' in completion
    assert "issues:" in completion
    assert "next_actions:" in completion
    assert "state_updates:" in completion
    assert "advance_plan: true" in completion
    assert "update_progress: true" in completion
    assert "record_metric:" in completion
    assert "contract_updates:" in completion
    assert "decisions:" in completion
    assert "blockers:" in completion
    assert "continuation_update:" in completion
    assert "handoff:" in completion
    assert "bounded_segment:" in completion
    assert "omit `recorded_at` and `recorded_by` from child returns" in completion
    assert 'recorded_at: "{timestamp}"' not in completion
    assert 'recorded_by: "gpd-executor"' not in completion
    assert "state_updates: [...]" not in completion
    assert "continuation_update: {...}" not in completion
