"""Prompt budget assertions for the `execute-phase` startup surface."""

from __future__ import annotations

from pathlib import Path

from tests.prompt_metrics_support import measure_prompt_surface

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = REPO_ROOT / "src" / "gpd" / "commands"
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
EXECUTE_PHASE_STAGE_DIR = WORKFLOWS_DIR / "execute-phase"
SOURCE_ROOT = REPO_ROOT / "src" / "gpd"
PATH_PREFIX = "/runtime/"
EXECUTE_PHASE_STAGE_FILES = (
    "phase-bootstrap.md",
    "phase-classification.md",
    "wave-planning.md",
    "pre-execution-specialists.md",
    "wave-dispatch.md",
    "checkpoint-resume.md",
    "aggregate-and-verify.md",
    "closeout.md",
)


def _stage_text(stage_file: str) -> str:
    return (EXECUTE_PHASE_STAGE_DIR / stage_file).read_text(encoding="utf-8")


def _combined_stage_text() -> str:
    return "\n\n".join(_stage_text(stage_file) for stage_file in EXECUTE_PHASE_STAGE_FILES)


def test_execute_phase_command_stays_thin_and_only_eagerly_loads_bootstrap_authority() -> None:
    command_path = COMMANDS_DIR / "execute-phase.md"
    command_text = command_path.read_text(encoding="utf-8")
    metrics = measure_prompt_surface(
        command_path,
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )

    assert metrics.raw_include_count == 1
    assert "@{GPD_INSTALL_DIR}/workflows/execute-phase/phase-bootstrap.md" in command_text
    assert "@{GPD_INSTALL_DIR}/workflows/execute-phase.md" not in command_text
    assert metrics.expanded_char_count <= 28_000
    assert "<arguments>" in command_text
    assert "<inline_guidance>" not in command_text
    assert "@{GPD_INSTALL_DIR}/references/ui/ui-brand.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/templates/summary.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/templates/contract-results-schema.md" not in command_text
    assert "Read the included bootstrap authority first." in command_text
    assert "staged_loading.eager_authorities" in command_text


def test_execute_phase_workflow_refreshes_stage_context_in_order() -> None:
    workflow_text = _combined_stage_text()

    assert 'PHASE_ARG=""' in workflow_text
    assert "EXECUTE_FLAGS=()" in workflow_text
    assert "GAPS_ONLY=false" in workflow_text
    assert '[ "$flag" = "--gaps-only" ] && GAPS_ONLY=true' in workflow_text
    assert '*) [ -z "$PHASE_ARG" ] && PHASE_ARG="$token" ;;' in workflow_text
    bootstrap_load = 'BOOTSTRAP_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage phase_bootstrap'
    wave_planning_load = 'WAVE_PLANNING_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage wave_planning)'
    pre_execution_load = (
        'PRE_EXECUTION_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage pre_execution_specialists)'
    )
    wave_dispatch_load = 'WAVE_DISPATCH_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage wave_dispatch)'
    assert workflow_text.index("<step name=\"normalize_arguments\"") < workflow_text.index(bootstrap_load)
    assert bootstrap_load in workflow_text
    assert wave_planning_load in workflow_text
    assert pre_execution_load in workflow_text
    assert wave_dispatch_load in workflow_text
    assert workflow_text.index(bootstrap_load) < workflow_text.index(wave_planning_load)
    assert workflow_text.index(wave_planning_load) < workflow_text.index(pre_execution_load)
    assert workflow_text.index(pre_execution_load) < workflow_text.index(wave_dispatch_load)
    assert 'gpd --raw init execute-phase "${PHASE_ARG}" --include state,config' not in workflow_text
    assert 'gpd --raw init execute-phase "${PHASE_ARG}" --stage "${stage_name}" 2>/dev/null' not in workflow_text
    assert 'echo "stderr: $(cat "$INIT_STDERR")"' in workflow_text
    assert "`gap_closure`" in next(
        line for line in workflow_text.splitlines() if line.startswith("Parse JSON for: `phase`, `plans[]`")
    )
    assert "If `$GAPS_ONLY` is true, also skip non-gap_closure plans." in workflow_text
    assert "**After gap closure execution completes (`$GAPS_ONLY` is true):**" in workflow_text
    assert "execute-plan.md owns plan-local execution semantics" in workflow_text
    assert "# task(subagent_type=\"gpd-notation-coordinator\"" not in workflow_text
    assert "# task(subagent_type=\"gpd-experiment-designer\"" not in workflow_text


def test_execute_phase_single_sources_runtime_delegation_boilerplate() -> None:
    workflow_text = _combined_stage_text()

    assert workflow_text.count("@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md") == 1
    assert "Canonical runtime delegation convention for every `task()` block in this workflow:" in workflow_text
    assert "Spawn a subagent for the task below. Adapt the `task()` call to your runtime's agent spawning mechanism." not in workflow_text
    assert "owns runtime-neutral task construction and handoff gates" in workflow_text
    assert workflow_text.count("Apply the canonical runtime delegation convention above.") == 6
