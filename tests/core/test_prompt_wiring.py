"""Assertions for prompt/template wiring."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

import pytest

from gpd import registry
from gpd.adapters.install_utils import expand_at_includes
from gpd.adapters.runtime_catalog import iter_runtime_descriptors
from gpd.contracts import ResearchContract, VerificationEvidence
from gpd.core.frontmatter import validate_frontmatter
from gpd.core.workflow_staging import load_workflow_stage_manifest, validate_workflow_stage_manifest_payload
from gpd.registry import _parse_frontmatter, _parse_tools
from tests.assertion_taxonomy_support import (
    FragmentAssertion,
    FragmentMode,
    MatchMode,
    assert_prompt_contracts,
    forbidden_duplicate,
    fragment_count,
    machine_exact,
    public_exact,
    semantic_anchor,
    semantic_concept,
)
from tests.core.test_spawn_contracts import _find_single_task
from tests.doc_surface_contracts import (
    assert_cost_surface_discoverability,
    assert_execution_observability_surface_contract,
    assert_help_command_all_extract_contract,
    assert_help_command_quick_start_extract_contract,
    assert_help_command_single_command_extract_contract,
    assert_help_workflow_quick_start_taxonomy_contract,
    assert_help_workflow_runtime_reference_contract,
    assert_publication_lane_boundary_contract,
    assert_recovery_ladder_contract,
    assert_resume_authority_contract,
    assert_runtime_reset_rediscovery_contract,
)
from tests.workflow_authority_support import (
    STAGED_WORKFLOW_AUTHORITY_NAMES,
    expanded_workflow_authority_text,
    workflow_authority_text,
)


@pytest.fixture(autouse=True)
def _clean_registry_cache():
    """Ensure fresh registry cache for each test."""
    from gpd import registry

    registry.invalidate_cache()
    yield
    registry.invalidate_cache()


REPO_ROOT = Path(__file__).resolve().parents[2]
README_PATH = REPO_ROOT / "README.md"
TEMPLATES_DIR = REPO_ROOT / "src/gpd/specs/templates"
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"
COMMANDS_DIR = REPO_ROOT / "src/gpd/commands"
AGENTS_DIR = REPO_ROOT / "src/gpd/agents"
REFERENCES_DIR = REPO_ROOT / "src/gpd/specs/references"
CONTRACT_BASELINE_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "stage0"
CONTRACT_RESULT_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "stage4"
PUBLICATION_SHARED_PREFLIGHT_INCLUDE = "@{GPD_INSTALL_DIR}/templates/paper/publication-manuscript-root-preflight.md"
PUBLICATION_BOOTSTRAP_PREFLIGHT_INCLUDE = "@{GPD_INSTALL_DIR}/references/publication/publication-bootstrap-preflight.md"
PUBLICATION_RESPONSE_WRITER_HANDOFF_INCLUDE = (
    "{GPD_INSTALL_DIR}/references/publication/publication-response-writer-handoff.md"
)
PUBLICATION_ROUND_ARTIFACTS_INCLUDE = "{GPD_INSTALL_DIR}/references/publication/publication-review-round-artifacts.md"
PUBLICATION_ROUND_ARTIFACTS_PATH = "{GPD_INSTALL_DIR}/references/publication/publication-review-round-artifacts.md"
PUBLICATION_REVIEW_RELIABILITY_INCLUDE = "{GPD_INSTALL_DIR}/references/publication/peer-review-reliability.md"
PUBLICATION_REVIEW_RELIABILITY_INLINE = "{GPD_INSTALL_DIR}/references/publication/peer-review-reliability.md"


def _assert_contains_fragments(text: str, *fragments: str) -> None:
    missing = [fragment for fragment in fragments if fragment not in text]
    assert not missing, "Missing expected prompt fragments:\n" + "\n".join(missing)


def _assert_prompt_contracts(text: str, *assertions: FragmentAssertion) -> None:
    for assertion in assertions:
        assertion.check(text)


def _assert_machine_fragments(text: str, *fragments: str, context: str) -> None:
    _assert_prompt_contracts(text, machine_exact(context, fragments, context=context))


def _assert_public_fragments(text: str, *fragments: str, context: str) -> None:
    _assert_prompt_contracts(text, public_exact(context, fragments, context=context))


def _assert_semantic_fragments(text: str, *fragments: str, context: str) -> None:
    _assert_prompt_contracts(
        text, semantic_anchor(context, fragments, match=MatchMode.CASEFOLD_NORMALIZED, context=context)
    )


def _assert_semantic_concepts(
    text: str,
    concepts: dict[str, tuple[str, ...]],
    *,
    context: str,
) -> None:
    _assert_prompt_contracts(
        text,
        *(
            semantic_anchor(concept, fragments, match=MatchMode.CASEFOLD_NORMALIZED, context=context)
            for concept, fragments in concepts.items()
        ),
    )


def _assert_semantic_concept(
    text: str,
    label: str,
    *,
    required: str | tuple[str, ...] | None = None,
    forbidden: str | tuple[str, ...] | None = None,
    match: MatchMode | str = MatchMode.CASEFOLD_NORMALIZED,
    context: str,
) -> None:
    _assert_prompt_contracts(
        text,
        *semantic_concept(label, required=required, forbidden=forbidden, match=match, context=context),
    )


def _assert_init_placeholders_visible(text: str, fields: tuple[str, ...], *, context: str) -> None:
    _assert_machine_fragments(text, *(f"{{{field}}}" for field in fields), context=context)


def _assert_command_delegates_to_workflow(
    command_text: str,
    workflow_id: str,
    *,
    semantic_fragments: tuple[str, ...] = (),
    stale_fragments: tuple[str, ...] = (),
    context: str | None = None,
) -> None:
    context = context or f"{workflow_id} command workflow delegation"
    include_fragments = [
        f"@{{GPD_INSTALL_DIR}}/workflows/{workflow_id}.md",
        f"{{GPD_INSTALL_DIR}}/workflows/{workflow_id}.md",
    ]
    manifest_path = WORKFLOWS_DIR / f"{workflow_id}-stage-manifest.json"
    if manifest_path.is_file():
        manifest = load_workflow_stage_manifest(workflow_id)
        include_fragments.extend(
            f"@{{GPD_INSTALL_DIR}}/{path}" for stage in manifest.stages for path in stage.mode_paths
        )

    _assert_prompt_contracts(
        command_text,
        machine_exact(
            f"{workflow_id} workflow include", tuple(include_fragments), mode=FragmentMode.ANY, context=context
        ),
    )
    if semantic_fragments:
        _assert_semantic_fragments(command_text, *semantic_fragments, context=context)
    if stale_fragments:
        _assert_forbidden_fragments(command_text, *stale_fragments, context=context)


def _assert_forbidden_fragments(text: str, *fragments: str, context: str) -> None:
    _assert_prompt_contracts(
        text,
        *(
            forbidden_duplicate(f"{context} forbidden fragment {index}", fragment, max_count=0, context=context)
            for index, fragment in enumerate(fragments, start=1)
        ),
    )


def _assert_loaded_authorities(command_name: str, stage_id: str, *authorities: str) -> None:
    staged_loading = registry.get_command(command_name).staged_loading

    assert staged_loading is not None
    loaded = tuple(staged_loading.stage(stage_id).loaded_authorities)
    missing = [authority for authority in authorities if authority not in loaded]
    assert not missing, f"{command_name}:{stage_id} missing loaded authorities: {missing}"


def _workflow_authority_text(name: str) -> str:
    return workflow_authority_text(WORKFLOWS_DIR, name)


def _expanded_workflow_authority_text(name: str, *, runtime: str | None = None) -> str:
    return expanded_workflow_authority_text(
        WORKFLOWS_DIR,
        name,
        src_root=REPO_ROOT / "src/gpd",
        path_prefix="/runtime/",
        runtime=runtime,
    )


def _autonomous_authority_text() -> str:
    paths = [WORKFLOWS_DIR / "autonomous.md"]
    stage_dir = WORKFLOWS_DIR / "autonomous"
    if stage_dir.is_dir():
        paths.extend(sorted(stage_dir.glob("*.md")))
    return "\n\n".join(path.read_text(encoding="utf-8") for path in paths)


def _success_criteria_sections(text: str) -> str:
    sections = re.findall(r"<success_criteria>(.*?)</success_criteria>", text, flags=re.DOTALL)
    return "\n\n".join(sections) if sections else text


def _assert_help_usage_line(text: str, command_name: str, *argument_fragments: str) -> None:
    pattern = rf"(?:^|\n)(?:- )?(?:Usage: )?`gpd:{re.escape(command_name)}(?P<arguments>[^`]*)`"
    matches = tuple(re.finditer(pattern, text))

    assert matches, f"missing help usage line for gpd:{command_name}"
    argument_options = tuple(match.group("arguments").strip() for match in matches)
    explicit_options = tuple(arguments for arguments in argument_options if arguments)
    assert explicit_options, f"usage line for gpd:{command_name} must include explicit input"
    if argument_fragments:
        assert any(all(fragment in arguments for fragment in argument_fragments) for arguments in explicit_options), (
            f"usage line for gpd:{command_name} missing argument fragments: {argument_fragments}"
        )


def _assert_slides_public_label_local_preflight_guidance(text: str, *, shared_source: bool = False) -> None:
    _assert_contains_fragments(
        text,
        "validate command-context",
        "`slides`",
    )
    if shared_source:
        _assert_contains_fragments(
            text,
            "this shared workflow is `gpd:slides`",
            "active runtime's native command label",
            "bare registry slug `slides`",
        )
        assert "$gpd-slides" not in text
    else:
        assert "this shared workflow is `gpd:slides`" in text or (
            "public runtime label" in text and "$gpd-slides" in text
        )
    assert "bare" in text.lower()
    assert any(
        fragment in text
        for fragment in (
            "local command-context bridge argument",
            "shell/local bridge",
            "bare registry slug",
        )
    )


def _assert_workflow_calls_staged_init_for_manifest_stages(workflow_id: str, workflow_text: str) -> None:
    staged_loading = registry.get_command(workflow_id).staged_loading

    assert staged_loading is not None
    for stage_id in staged_loading.stage_ids():
        pattern = rf"gpd --raw init {re.escape(workflow_id)}[\s\S]{{0,120}}--stage {re.escape(stage_id)}"
        helper_call = f"load_{workflow_id.replace('-', '_')}_stage {stage_id}"
        assert re.search(pattern, workflow_text) or helper_call in workflow_text, (
            f"missing staged init call for {workflow_id}:{stage_id}"
        )


COMMAND_SPAWN_TOKENS = {
    "explain.md": ["gpd-explainer", "gpd-bibliographer"],
    "debug.md": ["gpd-debugger"],
    "plan-phase.md": ["gpd-planner"],
    "quick.md": ["gpd-planner", "gpd-executor"],
}

WORKFLOW_SPAWN_TOKENS = {
    "derive-equation.md": ["gpd-check-proof"],
    "explain.md": ["gpd-explainer", "gpd-bibliographer"],
    "plan-phase.md": ["gpd-phase-researcher", "gpd-planner", "gpd-plan-checker"],
    "execute-phase.md": [
        "gpd-executor",
        "gpd-check-proof",
        "gpd-debugger",
        "gpd-verifier",
        "gpd-consistency-checker",
        "gpd-notation-coordinator",
        "gpd-experiment-designer",
    ],
    "verify-work.md": ["gpd-check-proof", "gpd-verifier", "gpd-planner", "gpd-plan-checker"],
    "write-paper.md": ["gpd-paper-writer", "gpd-bibliographer", "gpd-referee"],
    "peer-review.md": [
        "gpd-review-reader",
        "gpd-review-literature",
        "gpd-review-math",
        "gpd-check-proof",
        "gpd-review-physics",
        "gpd-review-significance",
        "gpd-referee",
    ],
    "new-project.md": [
        "gpd-project-researcher",
        "gpd-research-synthesizer",
        "gpd-roadmapper",
        "gpd-notation-coordinator",
    ],
    "new-milestone.md": ["gpd-project-researcher", "gpd-research-synthesizer", "gpd-roadmapper"],
}

AGENT_REFERENCE_TOKENS = {
    "gpd-bibliographer.md": [
        "references/shared/shared-protocols.md",
        "references/orchestration/agent-infrastructure.md",
        "references/physics-subfields.md",
        "references/publication/publication-pipeline-modes.md",
        "references/publication/bibliography-advanced-search.md",
        "templates/notation-glossary.md",
        "references/publication/bibtex-standards.md",
    ],
    "gpd-explainer.md": [
        "references/shared/shared-protocols.md",
        "references/orchestration/agent-infrastructure.md",
        "references/physics-subfields.md",
        "templates/notation-glossary.md",
    ],
    "gpd-debugger.md": [
        "Spawned by the debug orchestrator workflow.",
        "Public production boundary: public writable production agent specialized for discrepancy investigation and bounded repair work.",
        "On demand only: shared protocols, verification core, physics subfields, agent infrastructure, and cross-project patterns.",
        "Keep work in `gpd-debugger` while the task is root-cause isolation, validation, or a bounded repair tied to that investigation.",
        'Do not update `session_status` to "diagnosed" in `GPD/debug/{slug}.md`; that field belongs to verification artifacts.',
        "goal: find_root_cause_only",
        "goal: find_and_correct",
    ],
    "gpd-executor.md": [
        "references/shared/shared-protocols.md",
        "references/orchestration/agent-infrastructure.md",
        "references/shared/cross-project-patterns.md",
        "references/tooling/tool-integration.md",
        "references/execution/executor-index.md",
        "references/execution/executor-subfield-guide.md",
        "references/execution/executor-deviation-rules.md",
        "references/execution/executor-verification-flows.md",
        "references/execution/executor-task-checkpoints.md",
        "references/execution/executor-completion.md",
        "references/execution/executor-worked-example.md",
        "references/methods/approximation-selection.md",
        "references/verification/errors/llm-physics-errors.md",
        "references/verification/core/code-testing-physics.md",
        "references/orchestration/checkpoints.md",
        "templates/state-machine.md",
        "templates/summary.md",
        "templates/contract-results-schema.md",
        "templates/calculation-log.md",
    ],
    "gpd-experiment-designer.md": [
        "references/shared/shared-protocols.md",
        "references/orchestration/agent-infrastructure.md",
        "references/examples/ising-experiment-design-example.md",
    ],
    "gpd-notation-coordinator.md": [
        "references/shared/shared-protocols.md",
        "references/orchestration/agent-infrastructure.md",
        "references/conventions/subfield-convention-defaults.md",
        "templates/conventions.md",
    ],
    "gpd-paper-writer.md": [
        "references/shared/shared-protocols.md",
        "references/orchestration/agent-infrastructure.md",
        "references/publication/publication-pipeline-modes.md",
        "references/publication/paper-writer-cookbook.md",
        "templates/notation-glossary.md",
        "templates/latex-preamble.md",
        "references/publication/figure-generation-templates.md",
    ],
    "gpd-review-reader.md": [
        "references/shared/shared-protocols.md",
        "references/orchestration/agent-infrastructure.md",
        "references/publication/peer-review-panel.md",
    ],
    "gpd-review-literature.md": [
        "references/shared/shared-protocols.md",
        "references/orchestration/agent-infrastructure.md",
        "references/publication/publication-pipeline-modes.md",
        "references/publication/peer-review-panel.md",
    ],
    "gpd-review-math.md": [
        "references/shared/shared-protocols.md",
        "references/physics-subfields.md",
        "references/verification/core/verification-core.md",
        "references/publication/peer-review-panel.md",
    ],
    "gpd-check-proof.md": [
        "references/shared/shared-protocols.md",
        "references/orchestration/agent-infrastructure.md",
        "references/physics-subfields.md",
        "references/verification/core/verification-core.md",
        "templates/proof-redteam-schema.md",
        "references/verification/core/proof-redteam-protocol.md",
        "references/publication/peer-review-panel.md",
    ],
    "gpd-review-physics.md": [
        "references/shared/shared-protocols.md",
        "references/physics-subfields.md",
        "references/verification/core/verification-core.md",
        "references/publication/peer-review-panel.md",
    ],
    "gpd-review-significance.md": [
        "references/shared/shared-protocols.md",
        "references/orchestration/agent-infrastructure.md",
        "references/publication/publication-pipeline-modes.md",
        "references/publication/peer-review-panel.md",
    ],
    "gpd-phase-researcher.md": [
        "references/shared/shared-protocols.md",
        "references/orchestration/agent-infrastructure.md",
        "references/physics-subfields.md",
    ],
    "gpd-plan-checker.md": [
        "references/shared/shared-protocols.md",
        "references/orchestration/agent-infrastructure.md",
        "references/physics-subfields.md",
        "references/verification/core/verification-core.md",
        "templates/plan-contract-schema.md",
    ],
    "gpd-planner.md": [
        "references/shared/shared-protocols.md",
        "references/orchestration/agent-infrastructure.md",
        "references/physics-subfields.md",
        "references/verification/core/verification-core.md",
        "templates/planner-subagent-prompt.md",
        "templates/phase-prompt.md",
        "templates/parameter-table.md",
        "references/planning/planner-conventions.md",
        "references/protocols/hypothesis-driven-research.md",
    ],
    "gpd-project-researcher.md": [
        "references/shared/shared-protocols.md",
        "references/orchestration/agent-infrastructure.md",
    ],
    "gpd-referee.md": [
        "references/shared/shared-protocols.md",
        "references/orchestration/agent-infrastructure.md",
        "references/physics-subfields.md",
        "references/verification/core/verification-core.md",
        "references/publication/publication-pipeline-modes.md",
        "references/publication/referee-review-playbook.md",
        "references/publication/peer-review-panel.md",
        "templates/paper/referee-report.tex",
    ],
    "gpd-research-synthesizer.md": [
        "references/shared/shared-protocols.md",
        "references/orchestration/agent-infrastructure.md",
        "templates/research-project/SUMMARY.md",
    ],
    "gpd-roadmapper.md": [
        "references/shared/shared-protocols.md",
        "references/orchestration/agent-infrastructure.md",
        "templates/roadmap.md",
        "templates/state.md",
    ],
    "gpd-research-mapper.md": [
        "references/shared/shared-protocols.md",
        "references/orchestration/agent-infrastructure.md",
        "references/physics-subfields.md",
        "references/templates/research-mapper/FORMALISM.md",
        "references/templates/research-mapper/REFERENCES.md",
        "references/templates/research-mapper/ARCHITECTURE.md",
        "references/templates/research-mapper/STRUCTURE.md",
        "references/templates/research-mapper/CONVENTIONS.md",
        "references/templates/research-mapper/VALIDATION.md",
        "references/templates/research-mapper/CONCERNS.md",
    ],
    "gpd-verifier.md": [
        "references/shared/shared-protocols.md",
        "references/physics-subfields.md",
        "references/verification/core/verification-core.md",
        "references/verification/meta/verification-hierarchy-mapping.md",
        "references/verification/core/computational-verification-templates.md",
    ],
}


def _assert_contains_tokens(path: Path, tokens: list[str]) -> None:
    if path.parent == WORKFLOWS_DIR and path.stem in STAGED_WORKFLOW_AUTHORITY_NAMES:
        content = _workflow_authority_text(path.stem)
    else:
        content = path.read_text(encoding="utf-8")
    missing = [token for token in tokens if token not in content]
    assert missing == [], f"{path.relative_to(REPO_ROOT)} missing {missing}"


def _expand_prompt_surface(path: Path) -> str:
    return expand_at_includes(
        path.read_text(encoding="utf-8"),
        REPO_ROOT / "src/gpd/specs",
        "/runtime/",
    )


def _extract_between(content: str, start_marker: str, end_marker: str) -> str:
    start = content.index(start_marker) + len(start_marker)
    end = content.index(end_marker, start)
    return content[start:end]


def _normalized_prompt_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _assert_prompt_concepts(
    text: str,
    concepts: dict[str, tuple[str, ...]],
    *,
    context: str,
) -> None:
    _assert_semantic_concepts(text, concepts, context=context)


def _assert_ordered_prompt_fragments(text: str, fragments: tuple[str, ...], *, context: str) -> None:
    normalized = _normalized_prompt_text(text)
    position = -1
    for fragment in fragments:
        next_position = normalized.find(_normalized_prompt_text(fragment), position + 1)
        assert next_position != -1, f"{context} missing ordered fragment after {position}: {fragment}"
        position = next_position


def _plan_with_contract_text() -> str:
    return (CONTRACT_BASELINE_FIXTURES / "plan_with_contract.md").read_text(encoding="utf-8")


def test_planner_templates_exist():
    planner_prompt = TEMPLATES_DIR / "planner-subagent-prompt.md"
    phase_prompt = TEMPLATES_DIR / "phase-prompt.md"

    assert planner_prompt.exists()
    assert phase_prompt.exists()
    planner_text = planner_prompt.read_text(encoding="utf-8")
    phase_text = phase_prompt.read_text(encoding="utf-8")
    _assert_machine_fragments(
        planner_text,
        "template_version: 1",
        "<planning_context>",
        context="planner template machine markers",
    )
    _assert_machine_fragments(
        phase_text,
        "template_version: 1",
        "contract:",
        "acceptance_tests:",
        "uncertainty_markers:",
        context="phase prompt schema markers",
    )


def test_referee_latex_template_exists() -> None:
    referee_template = TEMPLATES_DIR / "paper" / "referee-report.tex"
    assert referee_template.exists()
    content = referee_template.read_text(encoding="utf-8")
    assert "template_version: 1" in content
    assert "\\RecommendationBadge" in content


def test_shared_protocols_require_permission_before_dependency_installs() -> None:
    shared = (REFERENCES_DIR / "shared" / "shared-protocols.md").read_text(encoding="utf-8")
    checkpoints = (REFERENCES_DIR / "orchestration" / "checkpoints.md").read_text(encoding="utf-8")
    verifier_raw = (AGENTS_DIR / "gpd-verifier.md").read_text(encoding="utf-8")
    verifier = expand_at_includes(verifier_raw, REPO_ROOT / "src/gpd", "/runtime/")
    planner = (AGENTS_DIR / "gpd-planner.md").read_text(encoding="utf-8")
    planner_execution = (REFERENCES_DIR / "planning" / "planner-execution-procedure.md").read_text(encoding="utf-8")

    _assert_semantic_fragments(
        shared,
        "NEVER install dependencies silently",
        "Ask the user before any install attempt",
        "BasicTeX",
        context="shared protocols dependency install permission gate",
    )
    _assert_forbidden_fragments(
        checkpoints,
        "Never install TeX automatically.",
        "install silently",
        context="checkpoint dependency install stale wording",
    )
    _assert_forbidden_fragments(
        verifier_raw,
        "## Data Boundary",
        "## GPD CLI Commit Protocol",
        "@{GPD_INSTALL_DIR}/references/orchestration/agent-infrastructure.md",
        context="verifier raw prompt dependency install include boundary",
    )
    _assert_semantic_fragments(
        verifier_raw,
        "Ask the user before any install attempt",
        "permission-gated",
        context="verifier dependency install permission gate",
    )
    _assert_semantic_fragments(
        verifier.lower(),
        "ask the user before any install attempt",
        context="expanded verifier dependency install permission gate",
    )
    _assert_semantic_fragments(
        planner + planner_execution,
        "permission-gated",
        context="planner dependency install permission gate",
    )


def test_agent_infrastructure_requires_concrete_next_actions_and_continuation_block() -> None:
    infra = (REFERENCES_DIR / "orchestration" / "agent-infrastructure.md").read_text(encoding="utf-8")

    assert "Prefer copy-pasteable GPD commands" in infra
    assert "references/orchestration/continuation-format.md" in infra
    assert "## > Next Up" in infra


def test_paper_writer_uses_lightweight_path_mentions_for_metadata_only_reference_packs() -> None:
    writer_text = (AGENTS_DIR / "gpd-paper-writer.md").read_text(encoding="utf-8")

    for path in (
        "references/shared/shared-protocols.md",
        "references/orchestration/agent-infrastructure.md",
        "templates/notation-glossary.md",
        "templates/latex-preamble.md",
    ):
        lightweight = f"{{GPD_INSTALL_DIR}}/{path}"
        eager = f"@{{GPD_INSTALL_DIR}}/{path}"
        assert lightweight in writer_text
        assert eager not in writer_text


def test_paper_writer_keeps_cookbook_material_lazy_loaded() -> None:
    writer_text = (AGENTS_DIR / "gpd-paper-writer.md").read_text(encoding="utf-8")
    cookbook = (REFERENCES_DIR / "publication" / "paper-writer-cookbook.md").read_text(encoding="utf-8")

    assert "<writing_reference_packs>" in writer_text
    assert "<figure_design>" not in writer_text
    assert "<supplemental_material>" not in writer_text
    assert "Journal-Specific Figure Requirements" not in writer_text
    assert "Abstract And Section Shape" in cookbook
    assert "Equation And Figure Details" in cookbook
    assert "Supplemental Material Placement" in cookbook


def test_bibliographer_uses_lightweight_path_mentions_for_metadata_only_reference_packs() -> None:
    bibliographer_text = (AGENTS_DIR / "gpd-bibliographer.md").read_text(encoding="utf-8")

    for path in (
        "references/shared/shared-protocols.md",
        "references/physics-subfields.md",
        "templates/notation-glossary.md",
        "references/orchestration/agent-infrastructure.md",
        "references/publication/bibtex-standards.md",
        "references/publication/publication-pipeline-modes.md",
        "references/publication/bibliography-advanced-search.md",
    ):
        lightweight = f"{{GPD_INSTALL_DIR}}/{path}"
        eager = f"@{{GPD_INSTALL_DIR}}/{path}"
        assert lightweight in bibliographer_text
        assert eager not in bibliographer_text


def test_continuation_format_scopes_clear_to_resolved_runtime_followups() -> None:
    continuation = (REFERENCES_DIR / "orchestration" / "continuation-format.md").read_text(encoding="utf-8")

    assert_runtime_reset_rediscovery_contract(continuation)
    _assert_semantic_fragments(
        continuation,
        "presentation layer only",
        "Start a fresh context window",
        "next command",
        "project rediscovery",
        context="continuation format runtime followups",
    )
    _assert_forbidden_fragments(
        continuation,
        "/clear",
        context="continuation format stale clear recovery wording",
    )


def test_plan_phase_applies_planner_roadmap_updates_in_orchestrator() -> None:
    plan_phase = _workflow_authority_text("plan-phase")

    _assert_semantic_fragments(
        plan_phase,
        "gpd_return.roadmap_updates",
        "planner returns",
        "roadmap edits",
        "orchestrator applies",
        "GPD/ROADMAP.md",
        "fresh `*-PLAN.md` artifacts",
        context="plan-phase roadmap update orchestration",
    )


def test_plan_phase_uses_manifest_owned_staged_init_access() -> None:
    plan_phase = _workflow_authority_text("plan-phase")

    _assert_workflow_calls_staged_init_for_manifest_stages("plan-phase", plan_phase)
    _assert_forbidden_fragments(
        plan_phase,
        "bind_plan_phase_init",
        context="plan-phase staged init manifest access",
    )
    _assert_machine_fragments(
        plan_phase,
        "BOOTSTRAP_INIT.staged_loading.required_init_fields",
        "INIT.staged_loading.required_init_fields",
        "--alias ALIAS=field",
        'gpd --raw init plan-phase "$PHASE" --stage planner_authoring',
        'gpd --raw init plan-phase "$PHASE" --stage checker_revision',
        "# Parse only the planner_authoring fields listed in INIT.staged_loading.required_init_fields",
        "# Parse only the checker_revision fields listed in INIT.staged_loading.required_init_fields",
        context="plan-phase staged init manifest access",
    )


def test_executor_completion_examples_use_command_based_next_actions() -> None:
    completion = (REFERENCES_DIR / "execution" / "executor-completion.md").read_text(encoding="utf-8")

    assert '"gpd:execute-phase {phase}"' in completion
    assert '"gpd:show-phase {phase}"' in completion
    assert "gpd state validate" in completion
    assert "gpd:sync-state" in completion
    assert "file_edit tool" not in completion


def test_referee_workflow_mentions_optional_pdf_compile_and_missing_tex_prompt() -> None:
    referee = (AGENTS_DIR / "gpd-referee.md").read_text(encoding="utf-8")
    peer_review = _workflow_authority_text("peer-review")

    _assert_semantic_fragments(
        referee,
        "compile",
        "referee-report `.tex`",
        "matching `.pdf`",
        "Do NOT install TeX yourself",
        context="referee optional pdf compile guidance",
    )
    _assert_semantic_fragments(
        peer_review,
        "Continue now",
        "${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.md",
        "${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.tex",
        context="peer-review missing tex continuation",
    )
    _assert_semantic_fragments(
        peer_review,
        "authorize",
        "install TeX",
        context="peer-review optional pdf compile guidance",
    )


def test_executor_prompt_defaults_to_return_only_shared_state_updates() -> None:
    executor = (AGENTS_DIR / "gpd-executor.md").read_text(encoding="utf-8")
    executor_completion = (REFERENCES_DIR / "execution" / "executor-completion.md").read_text(encoding="utf-8")

    _assert_semantic_fragments(
        executor,
        "return shared-state updates to the orchestrator",
        "instead of writing `STATE.md` directly",
        context="executor return-only shared state updates",
    )
    assert (
        "Your job: Execute the research plan completely, checkpoint each step, create SUMMARY.md, update STATE.md."
        not in executor
    )
    _assert_machine_fragments(
        executor,
        "state_updates",
        "contract_updates",
        "decisions",
        "blockers",
        "continuation_update",
        context="executor return fields",
    )
    _assert_semantic_fragments(
        executor,
        "omit `recorded_at`",
        "`recorded_by`",
        "child returns",
        context="executor child return timestamp ownership",
    )
    assert 'recorded_at: "{timestamp}"' not in executor
    assert 'recorded_by: "gpd-executor"' not in executor
    _assert_machine_fragments(
        executor_completion,
        "state_updates:",
        "contract_updates:",
        "decisions:",
        "blockers:",
        "continuation_update:",
        context="executor completion return fields",
    )
    _assert_semantic_fragments(
        executor_completion,
        "omit `recorded_at`",
        "`recorded_by`",
        "child returns",
        context="executor completion child return timestamp ownership",
    )
    assert 'recorded_at: "{timestamp}"' not in executor_completion
    assert 'recorded_by: "gpd-executor"' not in executor_completion


def test_return_only_planner_and_executor_do_not_commit_shared_state_files_by_default() -> None:
    planner = (AGENTS_DIR / "gpd-planner.md").read_text(encoding="utf-8")
    planner_execution = (REFERENCES_DIR / "planning" / "planner-execution-procedure.md").read_text(encoding="utf-8")
    executor = (AGENTS_DIR / "gpd-executor.md").read_text(encoding="utf-8")

    planner_commit_blocks = re.findall(r"```bash\n(gpd commit[\s\S]*?)\n```", planner + "\n" + planner_execution)
    executor_commit_blocks = re.findall(r"```bash\n(gpd commit[\s\S]*?)\n```", executor)

    assert planner_commit_blocks
    assert executor_commit_blocks
    assert all("GPD/STATE.md" not in block and "GPD/ROADMAP.md" not in block for block in planner_commit_blocks)
    assert all("GPD/STATE.md" not in block for block in executor_commit_blocks)
    assert "Authority: use the frontmatter-derived Agent Requirements block" not in planner
    assert "shared_state_authority: return_only" in registry.get_agent("gpd-planner").system_prompt
    assert "roadmap_updates" in planner
    assert "Authority: use the frontmatter-derived Agent Requirements block" not in executor
    assert "shared_state_authority: return_only" in registry.get_agent("gpd-executor").system_prompt


def test_read_only_plan_checker_and_research_mapper_tool_policy_are_contract_aligned() -> None:
    checker = (AGENTS_DIR / "gpd-plan-checker.md").read_text(encoding="utf-8")
    mapper = (AGENTS_DIR / "gpd-research-mapper.md").read_text(encoding="utf-8")

    assert "Return changed paths in `gpd_return.files_written`" not in checker
    assert "files_written: []" in checker
    assert "artifact_write_authority: read_only" in checker
    assert "All tools declared in frontmatter are available to this agent." in mapper
    _assert_semantic_fragments(
        mapper,
        "Reserve `web_search`",
        "`web_fetch`",
        "`status` focus",
        context="research mapper status-only web tools",
    )
    _assert_forbidden_fragments(
        mapper,
        "`status`: the same tools plus `web_search` and `web_fetch`",
        context="research mapper status-only web tools",
    )


def test_referee_prompt_no_longer_claims_read_only_artifact_policy() -> None:
    referee = (AGENTS_DIR / "gpd-referee.md").read_text(encoding="utf-8")

    _assert_semantic_fragments(
        referee,
        "scoped review artifacts",
        "changed paths",
        "gpd_return.files_written",
        context="referee writable review artifact policy",
    )
    _assert_forbidden_fragments(
        referee,
        "No files modified (read-only agent)",
        context="referee writable review artifact policy",
    )


def test_prompt_sources_do_not_use_stale_agent_install_paths():
    files = [
        REPO_ROOT / "src/gpd/specs/references/orchestration/agent-delegation.md",
        REPO_ROOT / "src/gpd/specs/templates/continuation-prompt.md",
    ]

    for path in files:
        assert "{GPD_INSTALL_DIR}/agents/" not in path.read_text(encoding="utf-8"), path


def test_prompt_sources_use_real_pattern_library_description():
    verifier_files = [REPO_ROOT / "src/gpd/agents/gpd-verifier.md"]

    for path in verifier_files:
        content = path.read_text(encoding="utf-8")
        assert "{GPD_INSTALL_DIR}/learned-patterns/" not in content, path
        assert "GPD_PATTERNS_ROOT" in content, path

    learned_pattern_template = (TEMPLATES_DIR / "learned-pattern.md").read_text(encoding="utf-8")
    assert "learned-patterns/patterns-by-domain/" in learned_pattern_template


def test_workflow_task_prompts_do_not_embed_at_references() -> None:
    invalid: list[str] = []

    for path in sorted(WORKFLOWS_DIR.rglob("*.md")):
        content = path.read_text(encoding="utf-8")
        for match in re.finditer(r"task\([\s\S]*?\)", content):
            if "@{GPD_INSTALL_DIR}" in match.group(0):
                invalid.append(str(path.relative_to(REPO_ROOT)))
                break

    assert invalid == []


def test_commands_reference_same_stem_workflows() -> None:
    workflow_stems = {path.stem for path in WORKFLOWS_DIR.glob("*.md")}

    for command_path in sorted(COMMANDS_DIR.glob("*.md")):
        if command_path.stem not in workflow_stems:
            continue
        content = command_path.read_text(encoding="utf-8")
        expected_standalone = f"@{{GPD_INSTALL_DIR}}/workflows/{command_path.stem}.md"
        expected_inline = f"{{GPD_INSTALL_DIR}}/workflows/{command_path.stem}.md"
        if expected_standalone in content or expected_inline in content:
            continue
        manifest_path = WORKFLOWS_DIR / f"{command_path.stem}-stage-manifest.json"
        if manifest_path.is_file():
            manifest = validate_workflow_stage_manifest_payload(
                json.loads(manifest_path.read_text(encoding="utf-8")),
                expected_workflow_id=command_path.stem,
            )
            first_stage_include = f"@{{GPD_INSTALL_DIR}}/{manifest.stages[0].mode_paths[0]}"
            if first_stage_include in content:
                continue
        raise AssertionError(command_path)


def test_commands_are_workflow_backed_or_explicitly_exempt() -> None:
    workflow_stems = {path.stem for path in WORKFLOWS_DIR.glob("*.md")}
    command_stems = {path.stem for path in COMMANDS_DIR.glob("*.md")}

    exempt_commands = registry.LOCAL_CLI_BRIDGE_WORKFLOW_EXEMPT_COMMANDS
    assert command_stems - workflow_stems == exempt_commands

    for command_stem in sorted(exempt_commands):
        command_text = (COMMANDS_DIR / f"{command_stem}.md").read_text(encoding="utf-8")
        if command_stem == "health":
            assert "gpd --raw health" in command_text
            assert "@{GPD_INSTALL_DIR}/workflows/health.md" not in command_text
        elif command_stem == "suggest-next":
            assert "gpd --raw suggest" in command_text
            assert "Local CLI fallback: `gpd --raw suggest`" in command_text
            assert "@{GPD_INSTALL_DIR}/workflows/suggest-next.md" not in command_text


def test_commands_reference_expected_spawn_agents() -> None:
    for command_name, agent_tokens in COMMAND_SPAWN_TOKENS.items():
        _assert_contains_tokens(COMMANDS_DIR / command_name, agent_tokens)


def test_workflows_reference_expected_spawn_agents() -> None:
    for workflow_name, agent_tokens in WORKFLOW_SPAWN_TOKENS.items():
        _assert_contains_tokens(WORKFLOWS_DIR / workflow_name, agent_tokens)


def test_agents_reference_expected_shared_specs() -> None:
    for agent_name, reference_tokens in AGENT_REFERENCE_TOKENS.items():
        _assert_contains_tokens(AGENTS_DIR / agent_name, reference_tokens)


def test_consistency_checker_prompt_keeps_the_canonical_contract_and_stays_least_privileged() -> None:
    source = (AGENTS_DIR / "gpd-consistency-checker.md").read_text(encoding="utf-8")

    assert "one-shot handoff" in source
    assert "status: completed" in source
    assert "files_written:\n    - GPD/phases/03-conventions/CONSISTENCY-CHECK.md" in source
    assert "GPD/CONSISTENCY-CHECK.md" in source
    assert "@{GPD_INSTALL_DIR}" not in source
    assert "Authority: use the frontmatter-derived Agent Requirements block" not in source
    assert "shared_state_authority: return_only" in registry.get_agent("gpd-consistency-checker").system_prompt
    _assert_semantic_fragments(
        source,
        "Do not claim ownership",
        "code fixes",
        "commits",
        "convention-authoring",
        "pattern-library updates",
        context="consistency checker least-privileged scope",
    )
    _assert_forbidden_fragments(
        source,
        "Create it from the template",
        context="consistency checker stale template authoring",
    )
    assert "gpd pattern add" not in source
    assert "Step 0.5" not in source
    assert "CONVENTIONS.md does not exist" not in source


def test_review_commands_expose_typed_contracts() -> None:
    write_paper = registry.get_command("gpd:write-paper")
    peer_review = registry.get_command("peer-review")
    arxiv_submission = registry.get_command("arxiv-submission")
    verify_work = registry.get_command("verify-work")
    respond_to_referees = registry.get_command("respond-to-referees")

    assert write_paper.review_contract is not None
    assert write_paper.review_contract.review_mode == "publication"
    assert "${PAPER_DIR}/ARTIFACT-MANIFEST.json" in write_paper.review_contract.required_outputs
    assert "${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json" in write_paper.review_contract.required_outputs
    assert "${PAPER_DIR}/reproducibility-manifest.json" in write_paper.review_contract.required_outputs
    assert "GPD/review/REVIEW-LEDGER{round_suffix}.json" in write_paper.review_contract.required_outputs
    assert "GPD/review/REFEREE-DECISION{round_suffix}.json" in write_paper.review_contract.required_outputs
    assert "GPD/REFEREE-REPORT{round_suffix}.md" in write_paper.review_contract.required_outputs
    assert "GPD/REFEREE-REPORT{round_suffix}.tex" in write_paper.review_contract.required_outputs
    assert write_paper.review_contract.required_evidence == [
        "project-backed lane: research artifacts and verification reports",
        "external-authoring lane: explicit `--intake` manifest with claim-to-evidence bindings",
        "bibliography / citation-source input",
    ]
    assert "command_context" in write_paper.review_contract.preflight_checks
    assert "verification_reports" in write_paper.review_contract.preflight_checks
    assert "manuscript" in write_paper.review_contract.preflight_checks
    assert "artifact_manifest" in write_paper.review_contract.preflight_checks
    assert "bibliography_audit" in write_paper.review_contract.preflight_checks
    assert "bibliography_audit_clean" in write_paper.review_contract.preflight_checks
    assert "reproducibility_manifest" in write_paper.review_contract.preflight_checks
    assert "reproducibility_ready" in write_paper.review_contract.preflight_checks
    assert "manuscript_proof_review" in write_paper.review_contract.preflight_checks
    assert write_paper.review_contract.stage_artifacts == []
    assert [
        {
            "when": requirement.when,
            "required_outputs": list(requirement.required_outputs),
        }
        for requirement in write_paper.review_contract.conditional_requirements
    ] == [
        {
            "when": "theorem-bearing claims are present",
            "required_outputs": ["GPD/review/PROOF-REDTEAM{round_suffix}.md"],
        }
    ]

    assert peer_review.review_contract is not None
    assert peer_review.review_contract.review_mode == "publication"
    assert "${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.md" in peer_review.review_contract.required_outputs
    assert "${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.tex" in peer_review.review_contract.required_outputs
    assert "${REVIEW_ROOT}/CLAIMS{round_suffix}.json" in peer_review.review_contract.required_outputs
    assert "${REVIEW_ROOT}/STAGE-interestingness{round_suffix}.json" in peer_review.review_contract.required_outputs
    assert "${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json" in peer_review.review_contract.required_outputs
    assert peer_review.review_contract.required_evidence == ["existing manuscript or explicit external artifact target"]
    assert peer_review.review_contract.blocking_conditions == [
        "missing manuscript or explicit external artifact target",
        "degraded review integrity",
        "unsupported physical significance claims",
        "collapsed novelty or venue fit",
    ]
    assert peer_review.review_contract.preflight_checks == [
        "command_context",
        "manuscript",
        "manuscript_proof_review",
    ]
    assert peer_review.review_contract.stage_artifacts == [
        "${REVIEW_ROOT}/CLAIMS{round_suffix}.json",
        "${REVIEW_ROOT}/STAGE-reader{round_suffix}.json",
        "${REVIEW_ROOT}/STAGE-literature{round_suffix}.json",
        "${REVIEW_ROOT}/STAGE-math{round_suffix}.json",
        "${REVIEW_ROOT}/STAGE-physics{round_suffix}.json",
        "${REVIEW_ROOT}/STAGE-interestingness{round_suffix}.json",
        "${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json",
        "${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json",
    ]
    assert [
        {
            "when": requirement.when,
            "required_outputs": list(requirement.required_outputs),
            "required_evidence": list(requirement.required_evidence),
            "blocking_conditions": list(requirement.blocking_conditions),
            "preflight_checks": list(requirement.preflight_checks),
            "blocking_preflight_checks": list(requirement.blocking_preflight_checks),
            "stage_artifacts": list(requirement.stage_artifacts),
        }
        for requirement in peer_review.review_contract.conditional_requirements
    ] == [
        {
            "when": "project-backed manuscript review",
            "required_outputs": [],
            "required_evidence": [
                "phase summaries or milestone digest",
                "verification reports",
                "manuscript-root bibliography audit",
                "manuscript-root artifact manifest",
                "manuscript-root reproducibility manifest",
                "manuscript-root publication artifacts",
            ],
            "blocking_conditions": [
                "missing project state",
                "missing roadmap",
                "missing conventions",
                "no research artifacts",
            ],
            "preflight_checks": [
                "project_state",
                "roadmap",
                "conventions",
                "research_artifacts",
                "verification_reports",
                "artifact_manifest",
                "bibliography_audit",
                "bibliography_audit_clean",
                "reproducibility_manifest",
                "reproducibility_ready",
            ],
            "blocking_preflight_checks": [
                "project_state",
                "roadmap",
                "conventions",
                "research_artifacts",
                "verification_reports",
                "artifact_manifest",
                "bibliography_audit",
                "bibliography_audit_clean",
                "reproducibility_manifest",
                "reproducibility_ready",
            ],
            "stage_artifacts": [],
        },
        {
            "when": "theorem-bearing claims are present",
            "required_outputs": ["${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md"],
            "required_evidence": [],
            "blocking_conditions": [],
            "preflight_checks": [],
            "blocking_preflight_checks": [],
            "stage_artifacts": ["${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md"],
        },
    ]

    assert arxiv_submission.review_contract is not None
    assert arxiv_submission.review_contract.review_mode == "publication"
    assert "command_context" in arxiv_submission.review_contract.preflight_checks
    assert "artifact_manifest" in arxiv_submission.review_contract.preflight_checks
    assert "bibliography_audit" in arxiv_submission.review_contract.preflight_checks
    assert "bibliography_audit_clean" in arxiv_submission.review_contract.preflight_checks
    assert "publication_blockers" in arxiv_submission.review_contract.preflight_checks
    assert "manuscript_proof_review" in arxiv_submission.review_contract.preflight_checks
    assert [
        {
            "when": requirement.when,
            "required_outputs": list(requirement.required_outputs),
            "required_evidence": list(requirement.required_evidence),
            "blocking_conditions": list(requirement.blocking_conditions),
            "blocking_preflight_checks": list(requirement.blocking_preflight_checks),
            "stage_artifacts": list(requirement.stage_artifacts),
        }
        for requirement in arxiv_submission.review_contract.conditional_requirements
    ] == [
        {
            "when": "theorem-bearing manuscripts are present",
            "required_outputs": [],
            "required_evidence": ["cleared manuscript proof review for theorem-bearing manuscripts"],
            "blocking_conditions": ["missing or stale manuscript proof review for theorem-bearing manuscripts"],
            "blocking_preflight_checks": ["manuscript_proof_review"],
            "stage_artifacts": [],
        }
    ]

    assert verify_work.review_contract is not None
    assert verify_work.review_contract.required_state == "phase_executed"
    assert "command_context" in verify_work.review_contract.preflight_checks
    assert "phase_lookup" in verify_work.review_contract.preflight_checks
    assert "phase_artifacts" in verify_work.review_contract.preflight_checks
    assert "phase_summaries" in verify_work.review_contract.preflight_checks
    assert "phase_proof_review" in verify_work.review_contract.preflight_checks

    assert respond_to_referees.review_contract is not None
    assert "GPD/review/REFEREE_RESPONSE{round_suffix}.md" in respond_to_referees.review_contract.required_outputs
    assert "GPD/AUTHOR-RESPONSE{round_suffix}.md" in respond_to_referees.review_contract.required_outputs
    assert "command_context" in respond_to_referees.review_contract.preflight_checks
    assert respond_to_referees.review_contract.required_evidence == [
        "existing manuscript",
        "referee report source when provided as a path",
    ]
    assert "gpd:peer-review" in registry.list_review_commands()
    assert "gpd:write-paper" in registry.list_review_commands()
    assert "gpd:respond-to-referees" in registry.list_review_commands()
    assert "gpd:verify-work" in registry.list_review_commands()


def test_conditional_review_contract_requirements_do_not_hide_runtime_blockers() -> None:
    peer_review = registry.get_command("peer-review").review_contract
    arxiv_submission = registry.get_command("arxiv-submission").review_contract

    assert peer_review is not None
    assert arxiv_submission is not None
    for field_name in (
        "stage_ids",
        "final_decision_output",
        "requires_fresh_context_per_stage",
        "max_review_rounds",
    ):
        assert not hasattr(peer_review, field_name)
    assert peer_review.preflight_checks == [
        "command_context",
        "manuscript",
        "manuscript_proof_review",
    ]
    assert "manuscript_proof_review" in peer_review.preflight_checks
    assert peer_review.conditional_requirements == [
        registry.ReviewContractConditionalRequirement(
            when="project-backed manuscript review",
            required_evidence=[
                "phase summaries or milestone digest",
                "verification reports",
                "manuscript-root bibliography audit",
                "manuscript-root artifact manifest",
                "manuscript-root reproducibility manifest",
                "manuscript-root publication artifacts",
            ],
            blocking_conditions=[
                "missing project state",
                "missing roadmap",
                "missing conventions",
                "no research artifacts",
            ],
            preflight_checks=[
                "project_state",
                "roadmap",
                "conventions",
                "research_artifacts",
                "verification_reports",
                "artifact_manifest",
                "bibliography_audit",
                "bibliography_audit_clean",
                "reproducibility_manifest",
                "reproducibility_ready",
            ],
            blocking_preflight_checks=[
                "project_state",
                "roadmap",
                "conventions",
                "research_artifacts",
                "verification_reports",
                "artifact_manifest",
                "bibliography_audit",
                "bibliography_audit_clean",
                "reproducibility_manifest",
                "reproducibility_ready",
            ],
        ),
        registry.ReviewContractConditionalRequirement(
            when="theorem-bearing claims are present",
            required_outputs=["${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md"],
            stage_artifacts=["${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md"],
        ),
    ]
    assert arxiv_submission.conditional_requirements == [
        registry.ReviewContractConditionalRequirement(
            when="theorem-bearing manuscripts are present",
            required_evidence=["cleared manuscript proof review for theorem-bearing manuscripts"],
            blocking_conditions=["missing or stale manuscript proof review for theorem-bearing manuscripts"],
            blocking_preflight_checks=["manuscript_proof_review"],
        )
    ]
    assert "manuscript_proof_review" in arxiv_submission.preflight_checks


def test_representative_commands_expose_expected_context_modes() -> None:
    assert registry.get_command("help").context_mode == "global"
    assert registry.get_command("health").context_mode == "projectless"
    assert registry.get_command("start").context_mode == "projectless"
    start_description = registry.get_command("start").description
    assert "first" in start_description.lower()
    _assert_semantic_fragments(
        start_description,
        "route",
        "real workflow",
        context="start command projectless context description",
    )
    _assert_forbidden_fragments(
        start_description,
        "without taking action",
        context="start command projectless context description",
    )
    assert registry.get_command("tour").context_mode == "projectless"
    tour_description = registry.get_command("tour").description
    assert "guided beginner walkthrough" in tour_description
    assert "core GPD commands" in tour_description
    assert "without taking action" in tour_description
    _assert_forbidden_fragments(
        tour_description,
        "route into the real workflow",
        context="tour command projectless context description",
    )
    assert registry.get_command("compare-results").context_mode == "project-aware"
    assert registry.get_command("map-research").context_mode == "projectless"
    assert registry.get_command("slides").context_mode == "projectless"
    assert registry.get_command("discover").context_mode == "project-aware"
    assert registry.get_command("explain").context_mode == "project-aware"
    assert registry.get_command("parameter-sweep").context_mode == "project-aware"
    assert registry.get_command("suggest-next").context_mode == "projectless"
    assert registry.get_command("peer-review").context_mode == "project-aware"


def test_readme_command_context_taxonomy_surfaces_global_mode_and_project_aware_publication_entrypoints() -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    command_context = readme.split("### Command Context", 1)[1].split("The full in-runtime reference", 1)[0]

    assert "| `Global` |" in command_context
    assert "| `Projectless` |" in command_context
    assert "| `Project-aware` |" in command_context
    assert "| `Project-required` |" in command_context
    project_aware_line = next(line for line in command_context.splitlines() if line.startswith("| `Project-aware` |"))
    project_required_line = next(
        line for line in command_context.splitlines() if line.startswith("| `Project-required` |")
    )
    assert "explicit current-workspace inputs" in project_aware_line
    for command_name in (
        "compare-experiment",
        "compare-results",
        "discover",
        "digest-knowledge",
        "explain",
        "parameter-sweep",
        "review-knowledge",
        "literature-review",
        "peer-review",
        "write-paper --intake intake/write-paper-authoring-input.json",
    ):
        assert command_name in project_aware_line
    _assert_semantic_fragments(
        command_context,
        "Project-aware commands",
        "current workspace",
        "relaxed technical-analysis lane",
        context="README command context taxonomy",
    )
    for command_name in (
        "derive-equation",
        "dimensional-analysis",
        "limiting-cases",
        "numerical-convergence",
        "parameter-sweep",
        "sensitivity-analysis",
    ):
        assert command_name in command_context
    assert "GPD/analysis/" in command_context
    assert "GPD/sweeps/" in command_context
    _assert_semantic_fragments(
        command_context,
        "`graph`",
        "`error-propagation`",
        "not part of this relaxed current-workspace lane",
        context="README relaxed technical-analysis lane exclusions",
    )
    assert "gpd:peer-review" not in project_required_line
    assert "gpd:write-paper" not in project_required_line
    assert (
        "Passing a manuscript path to a project-required command such as `gpd:peer-review paper/` selects the manuscript target, but does not bypass project initialization."
        not in command_context
    )


def test_readme_and_help_workflow_surface_publication_lane_boundary_without_claiming_root_migration() -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    help_workflow = (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8")

    assert_publication_lane_boundary_contract(readme)
    assert_publication_lane_boundary_contract(help_workflow)


def test_slides_workflow_references_templates_and_existing_output_policy() -> None:
    workflow = (WORKFLOWS_DIR / "slides.md").read_text(encoding="utf-8")

    _assert_slides_public_label_local_preflight_guidance(workflow, shared_source=True)
    _assert_machine_fragments(
        workflow,
        "{GPD_INSTALL_DIR}/templates/slides/presentation-brief.md",
        "{GPD_INSTALL_DIR}/templates/slides/outline.md",
        "{GPD_INSTALL_DIR}/templates/slides/slides.md",
        "{GPD_INSTALL_DIR}/templates/slides/speaker-notes.md",
        "{GPD_INSTALL_DIR}/templates/slides/main.tex",
        "1. Refresh",
        "2. Update",
        "3. Skip",
        "main.nav",
        "main.snm",
        context="slides template and cleanup machine tokens",
    )
    assert "source-bound skeleton" in workflow
    assert "selected_publication_root" not in workflow
    assert "selected_review_root" not in workflow


def test_slides_prompt_covers_cleanup_non_git_and_thin_source_boundaries() -> None:
    workflow = (WORKFLOWS_DIR / "slides.md").read_text(encoding="utf-8")

    _assert_slides_public_label_local_preflight_guidance(workflow, shared_source=True)
    _assert_semantic_fragments(
        workflow,
        "workspace is not a git checkout",
        "runtime-native deletion",
        "source-bound skeleton",
        context="slides cleanup non-git and source boundaries",
    )
    _assert_machine_fragments(
        workflow,
        "main.nav",
        "main.snm",
        context="slides cleanup known aux files",
    )


def test_publication_workflows_surface_no_write_stop_contracts_from_committed_sources() -> None:
    peer_review = _workflow_authority_text("peer-review")
    arxiv = _workflow_authority_text("arxiv-submission")
    slides = (WORKFLOWS_DIR / "slides.md").read_text(encoding="utf-8")

    _assert_contains_fragments(
        peer_review,
        "STOP at `manuscript_required`",
        "`next_step: none`",
    )
    _assert_contains_fragments(
        arxiv,
        "`command_execution_state: blocked_before_write`",
        "`response_gate`",
        "`review_state: stale`",
        "`response_state: requires_fresh_review`",
    )
    _assert_contains_fragments(
        slides,
        "`checkpoint: none`",
        "`next_step: none`",
        "`review_state: not_required`",
    )


def test_export_workflow_keeps_outputs_under_exports_without_satisfying_publication_gates() -> None:
    workflow = (WORKFLOWS_DIR / "export.md").read_text(encoding="utf-8")

    _assert_semantic_fragments(
        workflow,
        "`exports/`",
        "only durable write root",
        "Do not write generated export files",
        "GPD/publication/",
        "GPD/review/",
        "must not satisfy",
        "publication",
        "peer-review",
        "arXiv-package",
        "slides gates",
        context="export workflow durable root boundary",
    )


def test_representative_prompts_use_centralized_command_context_preflight() -> None:
    expected = {
        COMMANDS_DIR / "compare-experiment.md": "gpd --raw validate command-context compare-experiment",
        COMMANDS_DIR / "compare-results.md": "gpd --raw validate command-context compare-results",
        COMMANDS_DIR / "derive-equation.md": "gpd --raw validate command-context derive-equation",
        COMMANDS_DIR / "dimensional-analysis.md": "gpd --raw validate command-context dimensional-analysis",
        COMMANDS_DIR / "explain.md": "gpd --raw validate command-context explain",
        COMMANDS_DIR / "limiting-cases.md": "gpd --raw validate command-context limiting-cases",
        COMMANDS_DIR / "literature-review.md": "gpd --raw validate command-context literature-review",
        COMMANDS_DIR / "numerical-convergence.md": "gpd --raw validate command-context numerical-convergence",
        COMMANDS_DIR / "parameter-sweep.md": "gpd --raw validate command-context parameter-sweep",
        COMMANDS_DIR / "sensitivity-analysis.md": "gpd --raw validate command-context sensitivity-analysis",
        WORKFLOWS_DIR / "peer-review.md": "gpd --raw validate command-context peer-review",
        WORKFLOWS_DIR / "progress.md": "gpd --raw validate command-context progress",
    }

    for path, token in expected.items():
        text = _workflow_authority_text(path.stem) if path.parent == WORKFLOWS_DIR else path.read_text(encoding="utf-8")
        assert token in text, path


def test_current_workspace_project_aware_workflows_disable_recent_project_reentry() -> None:
    compare_experiment = (WORKFLOWS_DIR / "compare-experiment.md").read_text(encoding="utf-8")
    compare_results = (WORKFLOWS_DIR / "compare-results.md").read_text(encoding="utf-8")
    digest_knowledge = (WORKFLOWS_DIR / "digest-knowledge.md").read_text(encoding="utf-8")
    explain = (WORKFLOWS_DIR / "explain.md").read_text(encoding="utf-8")
    review_knowledge = (WORKFLOWS_DIR / "review-knowledge.md").read_text(encoding="utf-8")

    assert "INIT=$(gpd --raw init progress --include state,protocols --no-project-reentry)" in compare_experiment
    assert "INIT=$(gpd --raw init progress --include state --no-project-reentry)" in compare_results
    assert "INIT=$(gpd --raw init progress --include state,config,references --no-project-reentry)" in digest_knowledge
    assert "INIT=$(gpd --raw init progress --include project,state,roadmap,config --no-project-reentry)" in explain
    assert "INIT=$(gpd --raw init progress --include state,config --no-project-reentry)" in review_knowledge


def test_compare_commands_expose_typed_policy_for_interactive_intake_and_gpd_outputs() -> None:
    compare_results = registry.get_command("compare-results")
    compare_experiment = registry.get_command("compare-experiment")

    for command, resolution_mode, explicit_input in (
        (
            compare_results,
            "explicit_or_interactive_internal_comparison",
            "comparison target, phase, artifact path, or source-a vs source-b",
        ),
        (
            compare_experiment,
            "explicit_or_interactive_theory_data_comparison",
            "prediction, dataset path, phase identifier, or comparison target",
        ),
    ):
        assert command.command_policy is not None
        assert command.command_policy.schema_version == 1
        assert command.command_policy.subject_policy is not None
        assert command.command_policy.subject_policy.subject_kind == "comparison"
        assert command.command_policy.subject_policy.resolution_mode == resolution_mode
        assert command.command_policy.subject_policy.explicit_input_kinds == [explicit_input]
        assert command.command_policy.subject_policy.allow_external_subjects is True
        assert command.command_policy.subject_policy.allow_interactive_without_subject is True
        assert command.command_policy.supporting_context_policy is not None
        assert command.command_policy.supporting_context_policy.project_context_mode == "project-aware"
        assert command.command_policy.supporting_context_policy.project_reentry_mode == "disallowed"
        assert command.command_policy.output_policy is not None
        assert command.command_policy.output_policy.output_mode == "managed"
        assert command.command_policy.output_policy.managed_root_kind == "gpd_managed_durable"
        assert command.command_policy.output_policy.default_output_subtree == "GPD/comparisons"


def test_list_review_commands_contains_all_expected_commands() -> None:
    """Assert list_review_commands covers gpd:peer-review, gpd:write-paper,
    gpd:respond-to-referees, and gpd:verify-work without duplication."""
    review_cmds = registry.list_review_commands()
    expected = {"gpd:peer-review", "gpd:write-paper", "gpd:respond-to-referees", "gpd:verify-work"}
    assert expected <= set(review_cmds), f"Missing review commands: {expected - set(review_cmds)}"


def test_parameter_sweep_command_uses_project_aware_gpd_sweeps_output_policy() -> None:
    command = registry.get_command("parameter-sweep")

    assert command.context_mode == "project-aware"
    assert command.command_policy is not None
    assert command.command_policy.schema_version == 1
    assert command.command_policy.supporting_context_policy is not None
    assert command.command_policy.supporting_context_policy.project_context_mode == "project-aware"
    assert command.command_policy.supporting_context_policy.project_reentry_mode == "disallowed"
    assert command.command_policy.output_policy is not None
    assert command.command_policy.output_policy.output_mode == "managed"
    assert command.command_policy.output_policy.managed_root_kind == "gpd_managed_durable"
    assert command.command_policy.output_policy.default_output_subtree == "GPD/sweeps"


def test_list_review_commands_no_duplicates() -> None:
    """Each review command should appear exactly once."""
    review_cmds = registry.list_review_commands()
    assert len(review_cmds) == len(set(review_cmds))


def test_respond_to_referees_references_staged_review_artifacts() -> None:
    command_text = (COMMANDS_DIR / "respond-to-referees.md").read_text(encoding="utf-8")
    workflow_text = _workflow_authority_text("respond-to-referees")
    writer_text = (AGENTS_DIR / "gpd-paper-writer.md").read_text(encoding="utf-8")

    _assert_public_fragments(
        command_text,
        'argument-hint: "[--manuscript PATH] (--report PATH [--report PATH...] | paste)"',
        context="respond command public report source hint",
    )
    _assert_machine_fragments(
        command_text,
        "@{GPD_INSTALL_DIR}/workflows/respond-to-referees/bootstrap.md",
        context="respond command first-stage include",
    )
    _assert_forbidden_fragments(
        command_text,
        "@{GPD_INSTALL_DIR}/references/publication/publication-review-wrapper-guidance.md",
        context="respond command wrapper guidance no longer frontloaded",
    )
    _assert_semantic_fragments(
        command_text,
        "Referee report source",
        "$ARGUMENTS",
        "file path",
        "paste",
        "subject-owned publication root",
        "GPD/publication/{subject_slug}",
        context="respond command staged review artifact source",
    )
    _assert_semantic_fragments(
        workflow_text,
        "literal `paste` sentinel",
        "REVIEW-LEDGER*.json",
        "REFEREE-DECISION*.json",
        context="respond workflow staged review artifacts",
    )
    _assert_machine_fragments(
        writer_text,
        "review_ledger_path",
        "referee_decision_path",
        "author_response_path",
        "referee_response_path",
        context="paper writer response path fields",
    )


def test_publication_review_round_detection_prompts_are_shell_safe_and_pair_response_artifacts() -> None:
    peer_review = _workflow_authority_text("peer-review")
    referee = (AGENTS_DIR / "gpd-referee.md").read_text(encoding="utf-8")
    respond = _workflow_authority_text("respond-to-referees")
    reliability = (REFERENCES_DIR / "publication" / "peer-review-reliability.md").read_text(encoding="utf-8")

    for content in (peer_review, referee):
        _assert_forbidden_fragments(
            content,
            "ls GPD/REFEREE-REPORT*.md 2>/dev/null",
            "ls GPD/AUTHOR-RESPONSE*.md 2>/dev/null",
            context="publication review round shell-safe detection",
        )

    _assert_forbidden_fragments(
        referee,
        "ls GPD/review/REFEREE_RESPONSE*.md 2>/dev/null",
        context="referee shell-safe response artifact detection",
    )
    _assert_forbidden_fragments(
        respond,
        "ls GPD/review/REFEREE_RESPONSE*.md 2>/dev/null",
        "ls GPD/review/REVIEW-LEDGER*.json 2>/dev/null",
        "ls GPD/review/REFEREE-DECISION*.json 2>/dev/null",
        context="respond shell-safe response artifact detection",
    )

    _assert_machine_fragments(
        peer_review,
        "${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.md",
        "${PUBLICATION_ROOT}/AUTHOR-RESPONSE{round_suffix}.md",
        "${REVIEW_ROOT}/REFEREE_RESPONSE{round_suffix}.md",
        context="peer-review round-suffixed response artifacts",
    )
    _assert_semantic_fragments(
        peer_review,
        "Repair the target-bound response artifacts",
        "Do not require a response package",
        context="peer-review response package fail-closed policy",
    )

    _assert_semantic_fragments(
        referee,
        "matching paired response package",
        "same round",
        context="referee paired response package detection",
    )
    assert re.search(
        r"If one response artifact is missing[\s\S]{0,140}stop fail-closed and report the incomplete response package",
        referee,
    )
    assert (
        "A completed review without that package stays valid for internal review, accept/no-change outcomes, "
        "and fresh clearance reruns" in reliability
    )
    assert (
        "`${selected_publication_root}/AUTHOR-RESPONSE{round_suffix}.md` plus "
        "`${selected_review_root}/REFEREE_RESPONSE{round_suffix}.md`" in reliability
    )

    assert re.search(r"\bfind\b[\s\S]{0,160}-name ['\"]REFEREE_RESPONSE\*\.md['\"]", respond)
    assert re.search(r"\bfind\b[\s\S]{0,160}-name ['\"]AUTHOR-RESPONSE\*\.md['\"]", respond)
    assert re.search(r"\bfind\b[\s\S]{0,160}-name ['\"]REVIEW-LEDGER\*\.json['\"]", respond)
    assert re.search(r"\bfind\b[\s\S]{0,160}-name ['\"]REFEREE-DECISION\*\.json['\"]", respond)


def test_review_workflows_keep_round_suffix_artifacts_visible_and_anchor_response_outputs() -> None:
    peer_review = (COMMANDS_DIR / "peer-review.md").read_text(encoding="utf-8")
    workflow = _workflow_authority_text("peer-review")
    respond = _workflow_authority_text("respond-to-referees")
    write_paper = _workflow_authority_text("write-paper")
    write_paper_expanded = expand_at_includes(write_paper, REPO_ROOT / "src" / "gpd", "/runtime/")
    panel = (REFERENCES_DIR / "publication" / "peer-review-panel.md").read_text(encoding="utf-8")

    _assert_machine_fragments(
        peer_review,
        "${REVIEW_ROOT}/CLAIMS{round_suffix}.json",
        "${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json",
        "${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json",
        context="peer-review round-suffixed review artifacts",
    )
    _assert_machine_fragments(
        workflow,
        "${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.md",
        context="peer-review publication report artifact",
    )
    _assert_machine_fragments(
        panel,
        "${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.tex",
        "`manuscript_path` must be non-empty",
        context="peer-review panel round-suffixed artifacts",
    )
    _assert_semantic_fragments(
        panel,
        "Stage 1",
        "CLAIMS{round_suffix}.json",
        "ClaimIndex",
        "closed schema",
        "JSON `round` field",
        "sibling `CLAIMS{round_suffix}.json`",
        context="peer-review panel claim index contract",
    )
    _assert_forbidden_fragments(
        panel,
        "Stage 1 `CLAIMS.json` must follow this compact `ClaimIndex` shape:",
        context="peer-review panel stale unsuffixed claim index contract",
    )

    _assert_semantic_fragments(
        respond,
        "resolved section file",
        "manuscript tree rooted at `${PAPER_DIR}`",
        "${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json",
        "manuscript-local response-letter companion",
        "${RESPONSE_REFEREE_PATH}",
        "${RESPONSE_AUTHOR_PATH}",
        "selected_publication_root",
        "selected_review_root",
        "Do not duplicate the pair",
        context="respond round-suffixed response outputs",
    )
    _assert_machine_fragments(
        respond,
        "templates/paper/author-response.md",
        "needs-calculation",
        context="respond response output templates",
    )

    _assert_machine_fragments(
        write_paper,
        PUBLICATION_ROUND_ARTIFACTS_INCLUDE,
        context="write-paper round-suffixed response outputs",
    )
    _assert_machine_fragments(
        write_paper_expanded,
        "REVIEW-LEDGER{round_suffix}.json",
        "REFEREE-DECISION{round_suffix}.json",
        "${selected_publication_root}/REFEREE-REPORT{round_suffix}.md",
        context="expanded write-paper round-suffixed response outputs",
    )


def test_publication_commands_accept_documented_manuscript_layouts() -> None:
    write_paper = (COMMANDS_DIR / "write-paper.md").read_text(encoding="utf-8")
    peer_review = (COMMANDS_DIR / "peer-review.md").read_text(encoding="utf-8")
    publication_modes = (REFERENCES_DIR / "publication" / "publication-pipeline-modes.md").read_text(encoding="utf-8")
    respond = (COMMANDS_DIR / "respond-to-referees.md").read_text(encoding="utf-8")
    arxiv = (COMMANDS_DIR / "arxiv-submission.md").read_text(encoding="utf-8")
    respond_command = registry.get_command("respond-to-referees")

    assert "context_mode: project-aware" in write_paper
    assert "--intake path/to/write-paper-authoring-input.json" in write_paper
    _assert_semantic_fragments(
        write_paper,
        "Project-backed manuscripts",
        "`GPD/publication/{subject_slug}/manuscript`",
        "review/response auxiliaries",
        "`GPD/`",
        context="write-paper documented manuscript layouts",
    )
    assert "`paper/`, `manuscript/`, and `draft/`" in peer_review
    assert "{GPD_INSTALL_DIR}/references/publication/publication-pipeline-modes.md" in peer_review
    assert "subject-owned publication root at `GPD/publication/{subject_slug}`" in publication_modes
    assert "current global `GPD/` / `GPD/review/` round-artifact layout" not in peer_review
    assert respond_command.argument_hint == "[--manuscript PATH] (--report PATH [--report PATH...] | paste)"
    assert respond_command.command_policy is not None
    assert respond_command.command_policy.subject_policy is not None
    assert respond_command.command_policy.subject_policy.explicit_input_kinds == [
        "manuscript_path",
        "referee_report_path",
        "paste_referee_report",
    ]
    assert respond_command.command_policy.subject_policy.supported_roots == ["paper", "manuscript", "draft"]
    assert "allow_external_subjects: true" in respond
    assert "requires:" not in respond
    _assert_semantic_fragments(
        respond,
        "bounded continuation path",
        "not a full relocation",
        "manuscript-local publication artifacts",
        context="respond bounded publication continuation",
    )
    assert 'files: ["paper/*.tex", "manuscript/*.tex", "draft/*.tex", "GPD/publication/*/manuscript/*.tex"]' in arxiv

    assert "conditional_requirements:" in peer_review
    assert "when: project-backed manuscript review" in peer_review
    _assert_semantic_fragments(
        peer_review,
        "existing manuscript",
        "explicit external artifact target",
        "theorem-bearing claims",
        context="peer-review conditional manuscript requirements",
    )
    assert "${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md" in peer_review
    assert "gpd-check-proof" in peer_review
    assert "conditional_requirements:" in arxiv
    _assert_semantic_fragments(
        arxiv,
        "theorem-bearing manuscripts",
        "cleared manuscript proof review",
        context="arxiv conditional theorem requirements",
    )
    assert "latest peer-review review ledger" in arxiv
    assert "latest peer-review referee decision" in arxiv
    _assert_semantic_fragments(
        arxiv,
        "missing latest staged peer-review decision evidence",
        "resolved manuscript root",
        "build",
        "reproducibility",
        "staged-review artifacts",
        "workflow gates",
        "wrapper thin",
        "workflow own validation",
        context="arxiv publication gate evidence",
    )
    assert 'find . -name "main.tex"' not in arxiv
    assert 'find . -name "*.tex"' not in write_paper
    assert "first-match" not in arxiv


def test_proof_contract_prompts_surface_explicit_theorem_fields_and_review_bindings() -> None:
    plan_schema = _expand_prompt_surface(TEMPLATES_DIR / "plan-contract-schema.md")
    proof_schema = (TEMPLATES_DIR / "proof-redteam-schema.md").read_text(encoding="utf-8")
    proof_protocol = (REFERENCES_DIR / "verification" / "core" / "proof-redteam-protocol.md").read_text(
        encoding="utf-8"
    )
    peer_review = _workflow_authority_text("peer-review")
    check_proof = (AGENTS_DIR / "gpd-check-proof.md").read_text(encoding="utf-8")

    _assert_machine_fragments(
        plan_schema,
        "claim_kind",
        "parameters[]",
        "hypotheses[]",
        "quantifiers[]",
        "conclusion_clauses[]",
        "proof_deliverables[]",
        "proof_hypothesis_coverage",
        "proof_parameter_coverage",
        "proof_quantifier_domain",
        "claim_to_proof_alignment",
        "lemma_dependency_closure",
        "counterexample_search",
        context="plan contract proof theorem fields",
    )
    _assert_forbidden_fragments(
        plan_schema,
        "schema lacks dedicated theorem fields",
        context="plan contract proof theorem fields",
    )

    _assert_semantic_fragments(
        peer_review,
        "`gpd-check-proof` task must carry",
        "active `manuscript_path`",
        "`manuscript_sha256`",
        "`round`",
        "theorem-bearing `claim_ids`",
        "`proof_artifact_paths`",
        context="peer-review proof task binding",
    )
    assert "copy exactly from `${REVIEW_ROOT}/CLAIMS{round_suffix}.json`" in peer_review
    _assert_semantic_fragments(
        peer_review,
        "theorem-binding frontmatter",
        "`claim_ids`",
        "non-empty",
        "`proof_artifact_paths`",
        context="peer-review theorem-binding frontmatter",
    )
    _assert_semantic_fragments(
        peer_review,
        "Stage 3 math artifact",
        "exactly one `proof_audits[]` entry",
        "reviewed theorem-bearing claim",
        context="peer-review proof audit binding",
    )
    assert "every `proof_audits[].claim_id` must also appear in `claims_reviewed`" in peer_review

    assert "{GPD_INSTALL_DIR}/templates/proof-redteam-schema.md" in check_proof
    assert "{GPD_INSTALL_DIR}/references/verification/core/proof-redteam-protocol.md" in check_proof
    assert "@{GPD_INSTALL_DIR}/references/publication/peer-review-panel.md" not in check_proof
    assert "proof_artifact_paths: [path, ...]" in proof_schema
    assert "manuscript_path" in proof_schema
    assert "manuscript_sha256" in proof_schema
    assert "round" in proof_schema
    _assert_semantic_fragments(
        proof_protocol,
        "proof audit",
        "one-shot run",
        context="proof redteam one-shot audit policy",
    )
    assert "`peer-review` owns manuscript binding" in proof_protocol


def test_peer_review_prompt_surfaces_generic_claim_kind_as_non_theorem_bearing_by_default() -> None:
    panel = (REFERENCES_DIR / "publication" / "peer-review-panel.md").read_text(encoding="utf-8")
    referee = (AGENTS_DIR / "gpd-referee.md").read_text(encoding="utf-8")
    stale_theorem_boundary = (
        "Treat theorem-bearing status from the full Stage 1 claim record, not only from non-empty "
        "`theorem_assumptions` / `theorem_parameters` arrays: theorem-style `claim_kind` values and theorem-like "
        "statement text still require proof audits even when extraction is incomplete."
    )

    _assert_semantic_concept(
        panel,
        "panel theorem-bearing claim-kind boundary",
        required=(
            "Treat theorem-bearing status from the full Stage 1 Paper `ClaimRecord`",
            "`ProjectContract` `ContractClaim` vocabulary",
            "`claim_kind: theorem | lemma | corollary | proposition`",
            "kind alone",
            "`claim_kind: claim | result | other`",
            "theorem metadata or theorem-like text",
            "proof obligation explicit",
            "The theorem-style `claim_kind` values are limited to `theorem`, `lemma`, `corollary`, and `proposition`.",
            "Do not treat `claim_kind: claim` as theorem-bearing by default.",
            "This Paper `ClaimRecord` rule is intentionally different from `ProjectContract.claims[]`",
        ),
        forbidden=stale_theorem_boundary,
        context="peer-review generic claim theorem-bearing boundary",
    )

    _assert_semantic_concept(
        referee,
        "referee theorem-bearing claim-kind boundary",
        required=(
            "only `claim_kind: theorem | lemma | corollary | proposition` is theorem-bearing by kind alone",
            "while non-theorem-style kinds such as `claim`, `result`, or `other` become theorem-bearing only when "
            "non-empty theorem metadata or theorem-like statement text makes the proof obligation explicit.",
            "Do not upclassify a non-theorem-style claim record, including a generic `claim_kind: claim`, into "
            "theorem-bearing status unless the Stage 1 claim record also carries theorem metadata or theorem-like "
            "statement text.",
        ),
        forbidden=stale_theorem_boundary,
        context="referee generic claim theorem-bearing boundary",
    )


def test_write_paper_and_arxiv_submission_keep_the_build_boundary_explicit() -> None:
    write_paper = _workflow_authority_text("write-paper")
    arxiv = _workflow_authority_text("arxiv-submission")

    assert 'gpd paper-build "${PAPER_DIR}/PAPER-CONFIG.json" --output-dir "${PAPER_DIR}"' in write_paper
    _assert_semantic_fragments(
        write_paper,
        "This emits `${PAPER_DIR}/{topic_specific_stem}.tex`",
        "manuscript-root",
        "artifact manifest",
        "`${PAPER_DIR}/ARTIFACT-MANIFEST.json`",
        context="write-paper paper-build boundary",
    )
    _assert_semantic_fragments(
        write_paper,
        "local compilation smoke checks are skipped",
        "`.tex` generation still proceeds",
        "`gpd paper-build`",
        "canonical manuscript scaffold contract",
        context="write-paper paper-build nonblocking compile",
    )
    assert 'gpd paper-build "${PAPER_DIR}/PAPER-CONFIG.json" --output-dir "${PAPER_DIR}"' in arxiv
    _assert_semantic_fragments(
        arxiv,
        "`pdflatex` is available",
        "local smoke check",
        "`pdflatex` is not available",
        "smoke check was skipped",
        "Do not package stale audit artifacts",
        context="arxiv paper-build compile and stale audit policy",
    )


def test_write_paper_source_distinguishes_overclaim_pressure_from_bounded_resume_narrowing() -> None:
    write_paper = _workflow_authority_text("write-paper")

    _assert_semantic_fragments(
        write_paper,
        "unsupported-strengthening pressure",
        "strengthen unsupported theorem, general-proof",
        "submission-readiness claims",
        "cite whatever is needed",
        "adversarial overclaim pressure",
        "explicitly asks to narrow, qualify, or repair the claim",
        "Reject before manuscript writes",
        "claim_state: overclaim_blocked",
        "command_execution_state: blocked_before_write",
        "checkpoint: claim_evidence_gate",
        "files_written: none",
        "Do not convert adversarial overclaim pressure into a safe-narrowing rewrite",
        "Ordinary bounded resume narrowing remains allowed",
        "evidence requires a narrower claim",
        "no-write `overclaim_blocked` rule",
        context="write-paper overclaim versus safe narrowing",
    )


def test_arxiv_submission_documents_conservative_response_freshness_policy() -> None:
    command = (COMMANDS_DIR / "arxiv-submission.md").read_text(encoding="utf-8")
    workflow = _workflow_authority_text("arxiv-submission")

    _assert_semantic_concept(
        command,
        "arxiv command response freshness gate",
        required=(
            "latest response-round freshness status",
            "same-round or newer response artifacts without newer staged peer-review clearance",
        ),
        context="arxiv response freshness gate",
    )
    _assert_semantic_concept(
        workflow,
        "arxiv workflow conservative response freshness gate",
        required=(
            "Current executable policy is conservative",
            "any same-round or newer `gpd:respond-to-referees` author/referee response artifact",
            "all-response freshness policy",
            "durable manuscript-change scope metadata",
        ),
        context="arxiv response freshness gate",
    )
    _assert_machine_fragments(
        workflow,
        "response_freshness",
        "latest_response_requires_fresh_review=true",
        "response_gate",
        "review_state: stale",
        "response_state: requires_fresh_review",
        "claim_state: not_applicable",
        "not `human_needed`",
        context="arxiv response freshness machine markers",
    )


def test_remove_phase_workflow_stages_checkpoint_shelf_updates() -> None:
    workflow = (WORKFLOWS_DIR / "remove-phase.md").read_text(encoding="utf-8")

    assert "checkpoint shelf artifacts" in workflow
    assert "GPD/CHECKPOINTS.md" in workflow
    assert "GPD/phase-checkpoints" in workflow


def test_new_project_surfaces_supervised_default_and_core_research_preset_preview() -> None:
    workflow_text = _workflow_authority_text("new-project")

    # The minimal-mode config.json template emits the supervised default explicitly.
    assert '"autonomy": "supervised"' in workflow_text
    assert '"review_cadence": "dense"' in workflow_text

    # The preset catalog is still present, with the core-research preset recommended.
    assert "Which starting workflow preset should GPD use for `GPD/config.json`?" in workflow_text
    assert '"Core research (Recommended)"' in workflow_text
    assert '"Theory"' in workflow_text
    assert '"Numerics"' in workflow_text
    assert '"Publication / manuscript"' in workflow_text
    assert '"Full research"' in workflow_text

    # The core-research preset aligns with the Phase-1 defaults
    # (autonomy=supervised, review_cadence=dense), so its preview surfaces
    # those values rather than weaker overrides.
    _assert_machine_fragments(
        workflow_text,
        '"autonomy": "supervised"',
        '"research_mode": "balanced"',
        '"parallelization": true',
        '"commit_docs": true',
        '"review_cadence": "dense"',
        context="new-project core-research preset machine preview",
    )
    _assert_semantic_fragments(
        workflow_text,
        "Config:",
        "Supervised autonomy",
        "Dense review cadence",
        "Balanced research mode",
        "Parallel",
        "All agents",
        "Review profile",
        context="new-project core-research preset preview",
    )

    assert "Recommended defaults use YOLO autonomy" not in workflow_text
    assert (
        "Config: YOLO autonomy | Balanced research mode | Parallel | All agents | Review profile" not in workflow_text
    )


def test_settings_and_new_project_surface_runtime_permission_sync_for_yolo() -> None:
    new_project = _workflow_authority_text("new-project")
    settings = (WORKFLOWS_DIR / "settings.md").read_text(encoding="utf-8")
    permissions_sync = re.compile(
        r"gpd --raw permissions sync\b"
        r"(?=[^\n]*--runtime \"\$SELECTED_RUNTIME\")"
        r"(?=[^\n]*--autonomy \"\$SELECTED_AUTONOMY\")"
    )

    assert permissions_sync.search(new_project)
    assert permissions_sync.search(settings)
    assert 'gpd --raw permissions sync --autonomy "$SELECTED_AUTONOMY"' not in new_project
    assert 'gpd --raw permissions sync --autonomy "$SELECTED_AUTONOMY"' not in settings
    _assert_machine_fragments(
        new_project,
        "SELECTED_RUNTIME",
        "runtime-owned permission settings",
        "base install",
        "tool readiness",
        "workflow readiness",
        "If `requires_relaunch` is `true`, show `next_step` verbatim",
        context="new-project runtime permission sync fields",
    )
    _assert_semantic_fragments(
        new_project,
        "sync runtime-owned permissions",
        "selected autonomy",
        context="new-project runtime permission sync",
    )
    _assert_machine_fragments(
        settings,
        "model_overrides.<SELECTED_RUNTIME>",
        "runtime-owned permission settings",
        "install health",
        "workflow/tool readiness",
        "| Runtime Permissions  | {aligned / changed / manual follow-up required} |",
        context="settings runtime permission sync fields",
    )
    _assert_semantic_fragments(
        settings,
        "syncs the runtime",
        "most autonomous permission mode",
        context="settings runtime permission sync",
    )


def test_new_project_requires_scoping_contract_across_setup_modes() -> None:
    workflow_text = _workflow_authority_text("new-project")
    command_text = (COMMANDS_DIR / "new-project.md").read_text(encoding="utf-8")

    _assert_contains_fragments(
        workflow_text,
        "scoping contract",
        "explicit approval",
        "decisive outputs",
        "anchors",
        "prior outputs",
        "stop conditions",
        "rethink triggers",
        "`context_intake`",
        "`approach_policy`",
        "`uncertainty_markers`",
    )
    _assert_contains_fragments(
        command_text,
        "scoping contract",
        "decisive outputs",
        "anchors",
        "one explicit scope approval",
        "scoping approval gate",
        "staged roadmap/conventions handoff",
    )


def _assert_parse_line_includes_tokens(parse_line: str, fields: tuple[str, ...]) -> None:
    for field in fields:
        assert f"`{field}`" in parse_line


def test_new_project_wiring_mentions_contract_persistence_and_contract_first_downstream_generation() -> None:
    workflow_text = _workflow_authority_text("new-project")
    scope_intake_text = (WORKFLOWS_DIR / "new-project" / "scope-intake.md").read_text(encoding="utf-8")
    command_text = (COMMANDS_DIR / "new-project.md").read_text(encoding="utf-8")
    manifest = validate_workflow_stage_manifest_payload(
        json.loads((WORKFLOWS_DIR / "new-project-stage-manifest.json").read_text(encoding="utf-8")),
        expected_workflow_id="new-project",
    )
    scope_intake = manifest.stage("scope_intake")

    assert "gpd state set-project-contract" in workflow_text
    assert "gpd --raw validate project-contract - --mode approved" in workflow_text
    assert "gpd state set-project-contract -" in workflow_text
    assert "/tmp/gpd-project-contract.json" not in workflow_text
    assert "temporary JSON file if needed" not in workflow_text
    assert "Parse JSON for:" not in scope_intake_text
    assert "staged_loading.required_init_fields" in workflow_text
    for field in (
        "commit_docs",
        "autonomy",
        "research_mode",
        "project_exists",
        "has_research_map",
        "planning_exists",
        "has_research_files",
        "research_file_samples",
        "has_project_manifest",
        "needs_research_map",
        "has_git",
        "project_contract",
        "project_contract_gate",
        "project_contract_load_info",
        "project_contract_validation",
    ):
        assert field in scope_intake.required_init_fields
    assert "SCOPE_APPROVAL_INIT=$(gpd --raw init new-project --stage scope_approval)" in workflow_text
    assert "MINIMAL_ARTIFACTS_INIT=$(gpd --raw init new-project --stage minimal_artifacts)" in workflow_text
    assert "WORKFLOW_PREFS_INIT=$(gpd --raw init new-project --stage workflow_preferences)" in workflow_text
    assert "POST_SCOPE_INIT=$(gpd --raw init new-project --stage post_scope)" not in workflow_text
    assert "roadmapper_model" in workflow_text
    _assert_contains_fragments(
        workflow_text,
        "project_contract_gate.authoritative",
        "approved scope",
        "contract coverage",
        "ROADMAP.md",
        "REQUIREMENTS.md",
    )
    _assert_contains_fragments(
        command_text,
        "scoping contract",
        "roadmap generation",
        "one explicit scope approval",
        "scoping approval gate",
    )


def test_new_project_defers_workflow_setup_until_after_scope_approval() -> None:
    workflow_text = _workflow_authority_text("new-project")
    workflow_preferences = (WORKFLOWS_DIR / "new-project" / "workflow-preferences.md").read_text(encoding="utf-8")
    project_artifacts = (WORKFLOWS_DIR / "new-project" / "project-artifacts.md").read_text(encoding="utf-8")
    command_text = (COMMANDS_DIR / "new-project.md").read_text(encoding="utf-8")

    _assert_contains_fragments(
        workflow_preferences,
        "GPD/config.json",
        "scope approval",
        "before downstream project artifacts",
    )
    assert "## 2.5 Early Workflow Setup" not in workflow_text
    assert "Describe your research project in one pass" in workflow_text
    _assert_contains_fragments(
        project_artifacts,
        "If `GPD/config.json` is missing",
        "workflow_preferences",
        "After `GPD/config.json` exists",
    )
    assert "If Step 2.5 already captured provisional setup preferences" not in workflow_text
    assert "start with physics questioning" in command_text
    assert "surface a preset choice before workflow preferences" in command_text
    assert "before the first project-artifact commit" in command_text


def test_new_project_command_avoids_stale_workflow_line_counts() -> None:
    command_text = (COMMANDS_DIR / "new-project.md").read_text(encoding="utf-8")

    assert "read the included stage authority" in command_text
    assert "step-by-step instructions" not in command_text
    assert "lines)" not in command_text


def test_questioning_guide_requires_anchors_and_disconfirming_questions() -> None:
    guide_text = (REFERENCES_DIR / "research" / "questioning.md").read_text(encoding="utf-8")
    how_to_question = _extract_between(guide_text, "<how_to_question>", "</how_to_question>")
    question_types = _extract_between(guide_text, "<question_types>", "</question_types>")
    context_checklist = _extract_between(guide_text, "<context_checklist>", "</context_checklist>")
    decision_gate = _extract_between(guide_text, "<decision_gate>", "</decision_gate>")

    _assert_prompt_concepts(
        how_to_question,
        {
            "early anchors": ("references", "prior outputs", "benchmarks", "smoking-gun signal"),
            "preserve user guidance": ("figure", "dataset", "paper", "stop condition", "recognizable"),
            "pressure-test framing": ("working hypothesis", "narrow", "overturn", "falsify"),
            "avoid fake decomposition": ("roadmap is still fuzzy", "open decomposition question", "fake phases"),
        },
        context="questioning guide how_to_question",
    )
    _assert_prompt_concepts(
        question_types,
        {
            "ground-truth anchors": ("Ground-truth anchors", "known result", "prior output", "trusted anchor"),
            "disconfirmation": ("Disconfirmation and failure", "wrong or incomplete", "should not count as success"),
        },
        context="questioning guide question_types",
    )
    _assert_prompt_concepts(
        context_checklist,
        {
            "background anchor checks": ("background checklist", "known result", "prior output", "misleading proxy"),
        },
        context="questioning guide context_checklist",
    )
    _assert_prompt_concepts(
        decision_gate,
        {
            "coarse scope can proceed": ("Lack of a full phase list", "first grounded investigation chunk"),
            "no mechanical turn count": ("Do not count turns mechanically", "materially sharpening"),
        },
        context="questioning guide decision_gate",
    )


def test_new_project_questioning_requires_smoking_gun_and_rejects_proxy_only_readiness() -> None:
    scope_intake = (WORKFLOWS_DIR / "new-project" / "scope-intake.md").read_text(encoding="utf-8")
    scope_approval = (WORKFLOWS_DIR / "new-project" / "scope-approval.md").read_text(encoding="utf-8")
    guide_text = (REFERENCES_DIR / "research" / "questioning.md").read_text(encoding="utf-8")
    guide_decision_gate = _extract_between(guide_text, "<decision_gate>", "</decision_gate>")
    guide_question_types = _extract_between(guide_text, "<question_types>", "</question_types>")

    _assert_prompt_concepts(
        scope_intake,
        {
            "decisive intake": ("output, claim, or deliverable", "anchor", "baseline", "rethink"),
            "single repair": ("missing", "blocks a coherent scoping contract", "one narrow repair question"),
        },
        context="new-project deep questioning",
    )
    _assert_prompt_concepts(
        scope_approval,
        {
            "user anchor preservation": ("concrete anchor", "reference", "prior-output constraint", "baseline"),
            "no invented grounding": ("Do not invent anchors", "references", "baselines", "prior outputs"),
        },
        context="new-project Step M1.5 contract",
    )
    _assert_prompt_concepts(
        guide_text,
        {
            "hard correctness anchor": ("hard correctness check", "smoking-gun signal", "generic limiting cases"),
        },
        context="questioning guide smoking-gun policy",
    )
    _assert_prompt_concepts(
        guide_question_types,
        {
            "smoking-gun question": ("smoking-gun observable", "scaling law", "curve", "benchmark"),
            "sanity check is not enough": ("limiting cases", "sanity checks", "missed the smoking-gun check"),
        },
        context="questioning guide success and anchors",
    )
    _assert_prompt_concepts(
        guide_decision_gate,
        {
            "proxy-only gate rejection": (
                "proxy checks",
                "sanity checks",
                "limiting cases",
                "no decisive smoking-gun observable",
            ),
            "missing-anchor note is insufficient": (
                "missing-anchor note",
                "concrete reference",
                "prior-output",
                "baseline grounding",
            ),
        },
        context="questioning guide decision gate",
    )


def test_project_and_context_templates_surface_contract_and_skeptical_review() -> None:
    project_text = (TEMPLATES_DIR / "project.md").read_text(encoding="utf-8")
    context_text = (TEMPLATES_DIR / "context.md").read_text(encoding="utf-8")
    requirements_text = (TEMPLATES_DIR / "requirements.md").read_text(encoding="utf-8")
    state_schema_text = _expand_prompt_surface(TEMPLATES_DIR / "state-json-schema.md")

    _assert_machine_fragments(
        project_text,
        "## Scoping Contract Summary",
        "### Contract Coverage",
        "### Active Anchor Registry",
        "### User Guidance To Preserve",
        "### Skeptical Review",
        context="project template contract sections",
    )
    _assert_machine_fragments(
        context_text,
        "## Contract Coverage",
        "## Active Anchor Registry",
        "## User Guidance To Preserve",
        "## Skeptical Review",
        context="context template contract sections",
    )
    _assert_machine_fragments(
        requirements_text, "## Contract Coverage", context="requirements template contract sections"
    )
    assert "disconfirming_observations" in state_schema_text


def test_discuss_and_assumption_workflows_surface_anchors_and_fast_falsifiers() -> None:
    discuss_text = (WORKFLOWS_DIR / "discuss-phase.md").read_text(encoding="utf-8")
    assumptions_text = (WORKFLOWS_DIR / "list-phase-assumptions.md").read_text(encoding="utf-8")

    _assert_semantic_fragments(
        discuss_text,
        "prior output",
        "benchmark",
        "reference",
        "look wrong or incomplete early",
        "## User Guidance To Preserve",
        "## Contract Coverage",
        "## Active Anchor Registry",
        "## Skeptical Review",
        context="discuss-phase anchor and falsifier intake",
    )
    _assert_public_fragments(
        assumptions_text,
        "User Guidance I Am Treating As Binding",
        "### Anchor Inputs",
        "**Fast falsifier:**",
        "**False progress:**",
        context="list-phase-assumptions anchor and falsifier sections",
    )


def test_discuss_and_plan_workflows_resolve_roadmap_only_phases() -> None:
    discuss_text = (WORKFLOWS_DIR / "discuss-phase.md").read_text(encoding="utf-8")
    plan_text = _workflow_authority_text("plan-phase")

    _assert_forbidden_fragments(
        discuss_text,
        "Phase [X] not found in roadmap.",
        context="discuss-phase stale roadmap phase failure",
    )
    _assert_machine_fragments(
        discuss_text,
        'ROADMAP_INFO=$(gpd --raw roadmap get-phase "${PHASE}")',
        'phase_slug=$(gpd slug "$phase_name")',
        context="discuss-phase roadmap-only phase resolution",
    )
    _assert_semantic_fragments(
        discuss_text,
        "check_existing",
        "roadmap-derived phase metadata",
        context="discuss-phase roadmap-only phase resolution",
    )
    _assert_machine_fragments(
        plan_text,
        'REQUESTED_PHASE="${PHASE}"',
        'PHASE=$(echo "$INIT" | gpd json get .phase_number --default "${REQUESTED_PHASE}")',
        context="plan-phase roadmap-only phase resolution",
    )
    _assert_semantic_fragments(
        plan_text,
        "roadmap phase helper",
        "phase_number",
        "phase_name",
        "goal",
        "PHASE_DIR",
        "PHASE_SLUG",
        "PADDED_PHASE",
        context="plan-phase roadmap-only phase resolution",
    )


def test_planning_and_phase_templates_surface_active_reference_context() -> None:
    planner_prompt = (TEMPLATES_DIR / "planner-subagent-prompt.md").read_text(encoding="utf-8")
    phase_prompt = (TEMPLATES_DIR / "phase-prompt.md").read_text(encoding="utf-8")
    workflow_text = _workflow_authority_text("plan-phase")

    _assert_semantic_fragments(
        planner_prompt,
        "approved `project_contract`",
        context="planner prompt active reference context",
    )
    _assert_init_placeholders_visible(
        planner_prompt,
        (
            "project_contract",
            "project_contract_gate",
            "project_contract_load_info",
            "project_contract_validation",
            "active_reference_context",
        ),
        context="planner prompt active reference placeholders",
    )
    assert "@path/to/reference-or-benchmark-anchor.md" in phase_prompt
    assert "Planning requires an approved scoping contract in `GPD/state.json`" in workflow_text
    assert "project_contract_gate" in workflow_text
    assert "project_contract_validation" in workflow_text
    assert "project_contract_load_info" in workflow_text
    _assert_semantic_fragments(
        workflow_text,
        "project_contract_gate.authoritative",
        "Use `contract_gate_stop`",
        "Planning requires an approved scoping contract in `GPD/state.json`",
        "**Anchor coverage:**",
        "Required references",
        context="plan-phase active reference context",
    )
    _assert_init_placeholders_visible(
        workflow_text,
        ("project_contract", "active_reference_context"),
        context="plan-phase active reference placeholders",
    )


def test_progress_workflow_surfaces_contract_load_and_validation_state() -> None:
    workflow_text = (WORKFLOWS_DIR / "progress.md").read_text(encoding="utf-8")
    command_text = (COMMANDS_DIR / "progress.md").read_text(encoding="utf-8")

    _assert_machine_fragments(
        workflow_text,
        "project_contract_validation",
        "project_contract_load_info",
        "knowledge_doc_count",
        "stable_knowledge_doc_count",
        "knowledge_doc_status_counts",
        "derived_knowledge_doc_count",
        "knowledge_doc_warnings",
        context="progress workflow contract and knowledge fields",
    )
    _assert_semantic_fragments(
        workflow_text,
        "structured load status",
        "warnings",
        "blockers",
        "contract",
        "authoritative",
        "`project_contract_gate.authoritative`",
        context="progress workflow contract load state",
    )
    status_scan = 'grep -l -E "^(status: (gaps_found|human_needed|expert_needed)|session_status: diagnosed)$"'
    assert status_scan in workflow_text
    assert status_scan not in command_text
    _assert_semantic_fragments(
        command_text,
        "included workflow",
        "Do not duplicate",
        "workflow logic",
        context="progress command thin wrapper",
    )
    assert "INIT=$(gpd --raw init progress --include state,roadmap,project,config,references)" not in command_text
    assert 'CONTEXT=$(gpd --raw validate command-context progress "$ARGUMENTS")' not in command_text
    assert "status: (gaps_found|diagnosed|human_needed|expert_needed)" not in workflow_text
    assert "status: (gaps_found|diagnosed|human_needed|expert_needed)" not in command_text
    _assert_machine_fragments(
        workflow_text,
        "`session_status: diagnosed`",
        "HEALTH.summary.warn > 0",
        "HEALTH.summary.fail > 0",
        "## Knowledge Status",
        "GPD/phases/[current-phase-dir]/*-VERIFICATION.md",
        context="progress workflow status and health fields",
    )
    assert "`session_status: diagnosed`" not in command_text
    assert "non-empty `issues` array" not in workflow_text
    assert "GPD/phases/[current-phase-dir]/*-VERIFICATION.md" not in command_text


def test_progress_workflow_uses_read_only_health_for_compaction_status() -> None:
    workflow_text = (WORKFLOWS_DIR / "progress.md").read_text(encoding="utf-8")

    assert "gpd --raw health" in workflow_text
    assert "HEALTH_JSON=$(gpd --raw health 2>/dev/null || true)" in workflow_text
    assert "HEALTH=$(gpd --raw health 2>/dev/null || true)" in workflow_text
    _assert_semantic_fragments(
        workflow_text,
        "exit 1",
        "parseable JSON",
        "raw health returned nonzero",
        context="progress workflow read-only health compaction status",
    )
    assert "`State Compaction` check" in workflow_text
    assert "Report only; do not run raw state compaction from `gpd:progress`." in workflow_text
    assert "`gpd:progress` did not modify it" in workflow_text
    assert "gpd --raw state compact" not in workflow_text


def test_planning_prompts_keep_contract_gate_in_light_mode_and_all_modes() -> None:
    planner_prompt = (TEMPLATES_DIR / "planner-subagent-prompt.md").read_text(encoding="utf-8")
    planner_agent = (AGENTS_DIR / "gpd-planner.md").read_text(encoding="utf-8")
    checker_agent = (AGENTS_DIR / "gpd-plan-checker.md").read_text(encoding="utf-8")
    workflow_text = _workflow_authority_text("plan-phase")

    assert "{GPD_INSTALL_DIR}/templates/plan-contract-schema.md" in planner_prompt
    assert (
        "Use `@{GPD_INSTALL_DIR}/templates/plan-contract-schema.md` as the canonical contract source." in planner_prompt
    )
    _assert_semantic_fragments(
        planner_prompt,
        "approach_policy",
        "execution policy only",
        "Light mode",
        "body verbosity",
        context="planner light mode contract gate",
    )
    _assert_semantic_fragments(
        planner_agent,
        "Profiles",
        "compress detail",
        "do NOT relax contract completeness",
        context="planner agent profile contract completeness",
    )
    _assert_semantic_fragments(
        workflow_text,
        "All modes",
        "contract completeness",
        "decisive outputs",
        "required anchors",
        "forbidden-proxy",
        "disconfirming paths",
        context="plan-phase all-mode contract completeness",
    )
    assert "gpd_return.status: completed" in planner_prompt
    _assert_semantic_fragments(
        planner_prompt,
        "## PLANNING COMPLETE",
        "## CHECKPOINT REACHED",
        "## PLANNING INCONCLUSIVE",
        "human-readable labels only",
        context="planner presentation headings are non-authority",
    )
    assert "gpd_return.status: completed" in workflow_text
    _assert_semantic_fragments(
        workflow_text,
        "Checker presentation headings",
        "non-authority",
        "structured status",
        "plan-list validators",
        context="plan-phase checker presentation headings are non-authority",
    )
    _assert_semantic_fragments(
        checker_agent,
        "Human review",
        "does not replace",
        "requirements",
        context="plan checker contract completeness",
    )


def test_stable_knowledge_remains_background_only_across_planning_verification_and_execution() -> None:
    planner_prompt = (TEMPLATES_DIR / "planner-subagent-prompt.md").read_text(encoding="utf-8")
    plan_phase = _workflow_authority_text("plan-phase")
    verify_workflow = _workflow_authority_text("verify-work")
    verify_phase = (WORKFLOWS_DIR / "verify-phase.md").read_text(encoding="utf-8")
    execute_plan = (WORKFLOWS_DIR / "execute-plan.md").read_text(encoding="utf-8")
    execute_phase = _workflow_authority_text("execute-phase")

    _assert_semantic_fragments(
        planner_prompt,
        "stable knowledge docs",
        "`active_reference_context`",
        "`reference_artifacts_content`",
        "reviewed background",
        "`knowledge_deps`",
        "advisory",
        "do not override",
        context="planner stable knowledge boundary",
    )
    _assert_semantic_fragments(
        plan_phase,
        "Stable knowledge docs",
        "advisory",
        "explicit `knowledge_deps`",
        "never override",
        "`convention_lock`",
        "`project_contract`",
        "direct evidence",
        context="plan-phase stable knowledge boundary",
    )
    _assert_semantic_fragments(
        verify_workflow,
        "Stable knowledge docs",
        "reviewed background synthesis",
        "stronger sources",
        "never as decisive evidence",
        context="verify-work stable knowledge boundary",
    )
    _assert_semantic_fragments(
        verify_phase,
        "Stable knowledge docs",
        "reviewed background synthesis",
        "check selection",
        "do not override",
        "decisive evidence",
        context="verify-phase stable knowledge boundary",
    )
    _assert_semantic_fragments(
        execute_plan,
        "Stable knowledge docs",
        "reviewed background",
        "do not override",
        "contract",
        "decisive evidence",
        context="execute-plan stable knowledge boundary",
    )
    _assert_semantic_fragments(
        execute_phase,
        "Stable knowledge docs",
        "shared reference surfaces",
        "reviewed background",
        "not become a separate authority tier",
        "do not override",
        "proof audits",
        "decisive evidence",
        context="execute-phase stable knowledge boundary",
    )


def test_plan_checker_requires_contract_gate_and_reference_artifacts() -> None:
    checker_agent = (AGENTS_DIR / "gpd-plan-checker.md").read_text(encoding="utf-8")
    workflow_text = _workflow_authority_text("plan-phase")

    assert "## Dimension 0: Contract Gate" in checker_agent
    assert "{GPD_INSTALL_DIR}/templates/plan-contract-schema.md" in checker_agent
    _assert_prompt_contracts(
        checker_agent,
        machine_exact(
            "plan checker continuation boundary reference",
            "{GPD_INSTALL_DIR}/references/orchestration/continuation-boundary.md",
        ),
        semantic_anchor(
            "plan checker checkpoint handoff stop",
            ("one-shot handoff", "user input", "typed checkpoint", "stop"),
            context="plan-checker contract gate",
        ),
    )
    _assert_machine_fragments(
        checker_agent,
        "contract_decisive_output",
        "contract_anchor_coverage",
        "proxy_only_success_path",
        context="plan checker contract dimensions",
    )
    _assert_init_placeholders_visible(
        workflow_text,
        (
            "project_contract_gate",
            "project_contract_load_info",
            "project_contract_validation",
            "contract_intake",
            "effective_reference_intake",
            "reference_artifacts_content",
        ),
        context="plan-phase contract gate placeholders",
    )
    _assert_semantic_fragments(
        workflow_text,
        "Decisive outputs",
        "decisive claims and deliverables",
        context="plan-phase decisive output checks",
    )
    _assert_semantic_fragments(
        workflow_text,
        "Acceptance tests",
        "executable or reviewable test",
        "Forbidden proxies",
        "Proxy-only success conditions",
        context="plan-phase decisive acceptance and proxy checks",
    )


def test_roadmap_template_and_workflows_surface_phase_contract_coverage() -> None:
    roadmap_template = (TEMPLATES_DIR / "roadmap.md").read_text(encoding="utf-8")
    state_template = (TEMPLATES_DIR / "state.md").read_text(encoding="utf-8")
    roadmapper_agent = (AGENTS_DIR / "gpd-roadmapper.md").read_text(encoding="utf-8")
    new_project = _workflow_authority_text("new-project")
    new_milestone = _workflow_authority_text("new-milestone")
    new_project_roadmapper = _find_single_task(WORKFLOWS_DIR / "new-project.md", "gpd-roadmapper").text

    _assert_public_fragments(
        roadmap_template,
        "## Contract Overview",
        "**Contract Coverage:**",
        context="roadmap template public contract headings",
    )
    _assert_semantic_concept(
        roadmap_template,
        "roadmap phase titles are objective driven",
        required="Phase titles should be objective-driven, not template-driven",
        forbidden=(
            "Standard physics research flow",
            "Literature Review",
            "Formalism Development",
            "Calculation / Simulation",
            "Validation & Cross-checks",
            "Paper Writing",
        ),
        match=MatchMode.EXACT,
        context="roadmap template objective-driven phases",
    )
    assert_prompt_contracts(
        roadmapper_agent,
        forbidden_duplicate(
            "roadmapper defers roadmap template body",
            "@{GPD_INSTALL_DIR}/templates/roadmap.md",
            max_count=0,
        ),
        forbidden_duplicate(
            "roadmapper defers state template body",
            "@{GPD_INSTALL_DIR}/templates/state.md",
            max_count=0,
        ),
        semantic_anchor(
            "roadmapper keeps late-loaded roadmap and state templates visible",
            (
                "{GPD_INSTALL_DIR}/templates/roadmap.md",
                "{GPD_INSTALL_DIR}/templates/state.md",
                "file_read",
            ),
        ),
    )
    _assert_machine_fragments(
        roadmapper_agent,
        "## Step 3: Load Research Context (if exists)",
        "Contract coverage",
        "Machine-Readable Return Envelope",
        "gpd_return:",
        "status: completed",
        "files_written:",
        "GPD/ROADMAP.md",
        "GPD/STATE.md",
        "GPD/REQUIREMENTS.md",
        "phases_created: 4",
        context="roadmapper return and coverage fields",
    )
    _assert_machine_fragments(
        new_project_roadmapper,
        "gpd_return.files_written",
        "GPD/REQUIREMENTS.md",
        context="new-project roadmapper artifact gate",
    )
    _assert_semantic_fragments(
        new_project_roadmapper,
        "do not rely on runtime completion text alone",
        context="new-project roadmapper artifact gate",
    )
    _assert_machine_fragments(
        new_milestone,
        "expected_artifacts:",
        'freshness_marker: "after $MILESTONE_ROADMAPPER_HANDOFF_STARTED_AT"',
        context="new-milestone roadmapper artifact gate",
    )
    _assert_public_fragments(state_template, "Intermediate Results", context="state template progress heading")
    _assert_semantic_concept(
        roadmapper_agent,
        "roadmapper stops with blocked return when contract is underspecified",
        required=(
            "approved project contract is missing",
            "decisive outputs / deliverables plus anchor guidance",
            "stop with a blocked return",
            "return skeleton/profile reference for status vocabulary",
        ),
        context="roadmapper blocked return status",
    )
    _assert_semantic_concept(
        roadmapper_agent,
        "roadmapper treats contract intake as binding user guidance",
        required=(
            "`context_intake.must_read_refs`",
            "`must_include_prior_outputs`",
            "`user_asserted_anchors`",
            "`known_good_baselines`",
            "`crucial_inputs`",
            "binding user guidance",
        ),
        context="roadmapper binding user guidance",
    )
    # new-project uses shallow mode by default — Phase 1 only carries full coverage.
    # new-milestone keeps full-detail roadmap for scoped continuations.
    _assert_semantic_fragments(
        new_project,
        "For Phase 1",
        "explicit contract coverage",
        "ROADMAP.md",
        "requirements or contract demand",
        "contract-critical identity",
        context="new-project roadmap contract coverage",
    )
    _assert_semantic_fragments(
        new_milestone,
        "For each phase",
        "explicit contract coverage",
        "ROADMAP.md",
        context="new-milestone roadmap coverage",
    )


def test_research_prompt_surfaces_use_canonical_literature_outputs() -> None:
    project_researcher = (AGENTS_DIR / "gpd-project-researcher.md").read_text(encoding="utf-8")
    research_synthesizer = (AGENTS_DIR / "gpd-research-synthesizer.md").read_text(encoding="utf-8")
    phase_researcher = (AGENTS_DIR / "gpd-phase-researcher.md").read_text(encoding="utf-8")
    roadmapper_agent = (AGENTS_DIR / "gpd-roadmapper.md").read_text(encoding="utf-8")

    for content in (project_researcher, research_synthesizer, phase_researcher, roadmapper_agent):
        assert "GPD/research/" not in content

    assert "GPD/literature/" in project_researcher
    assert "GPD/literature/SUMMARY.md" in research_synthesizer
    assert "GPD/literature/SUMMARY.md" in phase_researcher
    assert "literature/SUMMARY.md" in roadmapper_agent


def test_new_project_minimal_mode_and_planning_wiring_allow_coarse_scoped_decomposition() -> None:
    workflow_text = _workflow_authority_text("new-project")
    scope_intake = (WORKFLOWS_DIR / "new-project" / "scope-intake.md").read_text(encoding="utf-8")
    scope_approval = (WORKFLOWS_DIR / "new-project" / "scope-approval.md").read_text(encoding="utf-8")
    roadmap_authoring = (WORKFLOWS_DIR / "new-project" / "roadmap-authoring.md").read_text(encoding="utf-8")
    planner_prompt = (TEMPLATES_DIR / "planner-subagent-prompt.md").read_text(encoding="utf-8")
    roadmap_instructions = _extract_between(roadmap_authoring, "<instructions>", "</instructions>")

    assert "say the anchor is\nunknown" in scope_intake
    _assert_prompt_concepts(
        scope_approval,
        {
            "unknown anchor fields": (
                "anchor",
                "context_intake",
                "uncertainty_markers",
                "missing-anchor uncertainty",
            ),
            "no invented grounding": ("Do not invent anchors", "references", "baselines", "prior outputs"),
        },
        context="new-project approval contract",
    )
    _assert_prompt_concepts(
        workflow_text,
        {
            "missing anchor is carried": ("anchor is unknown", "explicit unknown-anchor gap"),
            "coarse stage gate": ("single phase", "coarse early roadmap", "smallest decomposition"),
        },
        context="new-project missing-anchor approval gate",
    )
    _assert_prompt_concepts(
        roadmap_instructions,
        {
            "smallest supported roadmap": ("smallest decomposition", "single phase", "coarse early roadmap"),
            "no invented phase families": ("Do NOT invent", "literature", "numerics", "paper phases"),
        },
        context="new-project roadmap instructions",
    )
    assert "## CHECKPOINT REACHED" in planner_prompt
    assert "missing or no longer sufficient to identify the right phase slice" in planner_prompt


def test_reference_workflows_require_anchor_registry_propagation() -> None:
    literature_workflow = _workflow_authority_text("literature-review")
    literature_command = (COMMANDS_DIR / "literature-review.md").read_text(encoding="utf-8")
    literature_agent = (AGENTS_DIR / "gpd-literature-reviewer.md").read_text(encoding="utf-8")
    bibliographer_agent = (AGENTS_DIR / "gpd-bibliographer.md").read_text(encoding="utf-8")
    compare_workflow = (WORKFLOWS_DIR / "compare-results.md").read_text(encoding="utf-8")
    map_workflow = _workflow_authority_text("map-research")
    map_command = (COMMANDS_DIR / "map-research.md").read_text(encoding="utf-8")
    mapper_agent = (AGENTS_DIR / "gpd-research-mapper.md").read_text(encoding="utf-8")

    literature_bootstrap_fields = (
        load_workflow_stage_manifest("literature-review").stage("review_bootstrap").required_init_fields
    )
    assert "project_contract_load_info" in literature_bootstrap_fields
    assert "project_contract_validation" in literature_bootstrap_fields
    _assert_prompt_concepts(
        literature_workflow,
        {
            "contract-gated anchor scope": (
                "contract-critical anchors",
                "project_contract_gate.authoritative",
                "authoritative",
            ),
            "defer heavy artifacts until scoped": (
                "frontload reference artifacts",
                "scope is fixed",
                "reference_artifact_files",
                "reference_artifacts_content",
            ),
        },
        context="literature-review workflow anchor propagation",
    )
    _assert_semantic_fragments(
        literature_workflow,
        "load_scoped_reference_artifacts",
        "include `bibtex_key`",
        "known and verified",
        context="literature-review scoped citation artifacts",
    )
    assert "reference_artifact_files" not in literature_bootstrap_fields
    assert "reference_artifacts_content" not in literature_bootstrap_fields
    _assert_command_delegates_to_workflow(
        literature_command,
        "literature-review",
        semantic_fragments=("staged workflow owns", "scope fixing", "artifact gating", "citation verification"),
        stale_fragments=(
            "First, read {GPD_AGENTS_DIR}/gpd-literature-reviewer.md for your role and instructions",
            "Write to: GPD/literature/{slug}-REVIEW.md",
        ),
    )
    assert "Active Anchor Registry" not in literature_command
    _assert_machine_fragments(
        literature_agent,
        "active_anchors",
        "GPD/literature/{slug}-CITATION-SOURCES.json",
        "gpd paper-build --citation-sources",
        "reference_id",
        context="literature reviewer citation sidecar fields",
    )
    _assert_semantic_fragments(
        literature_agent,
        "compatible with the `CitationSource` shape",
        "`bibtex_key` as an optional preferred key",
        "Keep `bibtex_key` stable",
        context="literature reviewer bibtex key stability",
    )
    _assert_prompt_concepts(
        bibliographer_agent,
        {
            "bibtex manuscript bridge": ("preferred `bibtex_key`", "manuscript bridge candidate"),
            "mode matrix reference": ("mode specification matrix", "publication-pipeline-modes.md"),
        },
        context="bibliographer anchor propagation",
    )
    _assert_machine_fragments(
        compare_workflow,
        "project_contract_load_info",
        "project_contract_validation",
        "active_reference_context",
        context="compare-results reference fields",
    )
    _assert_prompt_concepts(
        compare_workflow,
        {
            "comparison scope authority gate": (
                "contract authority gate",
                "project_contract",
                "comparison scope",
                "project_contract_gate.authoritative",
            ),
        },
        context="compare-results workflow anchor propagation",
    )
    _assert_machine_fragments(
        map_workflow,
        "active_reference_context",
        "effective_reference_intake",
        "project_contract_load_info",
        "project_contract_validation",
        "reference_artifacts_content",
        context="map-research reference fields",
    )
    _assert_prompt_concepts(
        map_workflow,
        {
            "map-research authority gate": ("authoritative", "project_contract_gate.authoritative"),
        },
        context="map-research workflow anchor propagation",
    )
    _assert_command_delegates_to_workflow(
        map_command,
        "map-research",
        semantic_fragments=("workflow", "staged init", "mapper fanout", "return routing"),
        stale_fragments=("project_contract_load_info", "reference_artifacts_content"),
    )
    assert "REFERENCES.md is an anchor registry" in mapper_agent


def test_literature_review_stage_manifest_keeps_citation_audit_write_visible() -> None:
    literature_workflow = _workflow_authority_text("literature-review")
    literature_staging = validate_workflow_stage_manifest_payload(
        json.loads((WORKFLOWS_DIR / "literature-review-stage-manifest.json").read_text(encoding="utf-8")),
        expected_workflow_id="literature-review",
    )

    assert literature_staging.stage_ids() == (
        "review_bootstrap",
        "scope_locked",
        "review_handoff",
        "completion_gate",
    )
    assert "GPD/literature/{slug}-CITATION-AUDIT.md" in literature_workflow
    assert "GPD/literature/slug-CITATION-AUDIT.md" in literature_staging.stage("review_handoff").writes_allowed


def test_file_producing_command_surfaces_use_canonical_spawn_contract() -> None:
    literature = (COMMANDS_DIR / "literature-review.md").read_text(encoding="utf-8")
    debug = (COMMANDS_DIR / "debug.md").read_text(encoding="utf-8")
    respond = (COMMANDS_DIR / "respond-to-referees.md").read_text(encoding="utf-8")

    for content, agent_name, file_token in ((debug, "gpd-debugger", "GPD/debug/{slug}.md"),):
        assert f"{{GPD_AGENTS_DIR}}/{agent_name}.md" in content
        assert "role and instructions" in content
        assert file_token in content
        assert "before continuing" in content
        assert f"@{file_token}" not in content
    assert "Fresh 200k context" not in content

    assert "gpd --raw validate command-context literature-review" in literature
    _assert_command_delegates_to_workflow(
        literature,
        "literature-review",
        semantic_fragments=("staged workflow", "artifact gating", "citation verification"),
        stale_fragments=(
            "First, read {GPD_AGENTS_DIR}/gpd-literature-reviewer.md for your role and instructions",
            "Write to: GPD/literature/{slug}-REVIEW.md",
        ),
    )

    assert "Fresh 200k context" not in respond


def test_research_phase_command_delegates_file_path_and_return_routing_to_the_workflow() -> None:
    command = (COMMANDS_DIR / "research-phase.md").read_text(encoding="utf-8")
    workflow = _workflow_authority_text("research-phase")

    _assert_command_delegates_to_workflow(
        command,
        "research-phase",
        semantic_fragments=("workflow-owned staged init", "typed-return routing", "artifact gating", "research_mode"),
        stale_fragments=(
            "gpd --raw init phase-op --include state,config",
            "gpd_return.status: completed",
            "gpd_return.files_written",
        ),
    )
    _assert_machine_fragments(
        workflow,
        'BOOTSTRAP_INIT=$(load_research_phase_stage phase_bootstrap "${PHASE}")',
        'HANDOFF_INIT=$(load_research_phase_stage research_handoff "${phase_number}")',
        'gpd --raw init research-phase "${phase_arg}" --stage "${stage_name}"',
        "Write to: {phase_dir}/{phase_number}-RESEARCH.md",
        "gpd_return.files_written",
        'RESEARCH_MODE=$(echo "$BOOTSTRAP_INIT" | gpd json get .research_mode --default balanced)',
        context="research-phase workflow staged routing",
    )


def test_revision_and_audit_workflows_verify_artifacts_before_trusting_success_text() -> None:
    respond = _workflow_authority_text("respond-to-referees")
    audit = (WORKFLOWS_DIR / "audit-milestone.md").read_text(encoding="utf-8")
    stage_gate = (REPO_ROOT / "src/gpd/specs/references/publication/stage-recovery-gate.md").read_text(encoding="utf-8")

    _assert_machine_fragments(
        respond,
        "templates/paper/author-response.md",
        "needs-calculation",
        "stage-recovery-gate.md",
        "`${RESPONSE_AUTHOR_PATH}`",
        "`${RESPONSE_REFEREE_PATH}`",
        context="respond artifact gate fields",
    )
    _assert_semantic_fragments(
        respond,
        "Evidence",
        "verify the promised artifacts",
        "before trusting the handoff text",
        context="respond artifact gate semantics",
    )
    _assert_semantic_fragments(
        stage_gate,
        "Do not accept stale preexisting files",
        "current-run completion",
        context="stage recovery gate freshness",
    )
    _assert_semantic_fragments(
        audit,
        "Verify the promised referee artifacts",
        "Confirm `GPD/v{milestone_version}-MILESTONE-REFEREE-REPORT.md`",
        "agent reported success",
        "artifact is missing",
        "peer review as failed",
        context="audit milestone artifact gate",
    )


def test_audit_milestone_surfaces_contract_gate_and_milestone_review_namespace() -> None:
    audit = (WORKFLOWS_DIR / "audit-milestone.md").read_text(encoding="utf-8")

    _assert_machine_fragments(
        audit,
        "project_contract_load_info",
        "project_contract_validation",
        "active_reference_context",
        context="audit milestone contract gate fields",
    )
    _assert_semantic_fragments(
        audit, "Apply the shared contract authority gate", context="audit milestone gate semantics"
    )
    assert (
        "project_contract` is approved milestone scope only when `project_contract_gate.authoritative` is true" in audit
    )
    assert (
        "skip mock peer review and note that the contract gate must be repaired before milestone publishability review"
        in audit
    )
    assert "GPD/v{milestone_version}-MILESTONE-REFEREE-REPORT.md" in audit
    assert "GPD/v{milestone_version}-MILESTONE-REFEREE-REPORT.tex" in audit
    assert "Project contract load info: {project_contract_load_info}" in audit
    assert "Project contract validation: {project_contract_validation}" in audit
    assert "Active references: {active_reference_context}" in audit


def test_audit_milestone_uses_canonical_phase_helpers_instead_of_raw_glob_discovery() -> None:
    audit = (WORKFLOWS_DIR / "audit-milestone.md").read_text(encoding="utf-8")

    assert "gpd phase list" in audit
    assert "gpd:show-phase <phase-number>" in audit
    assert "gpd show-phase <phase-number>" not in audit
    assert "`find_files` `GPD/phases/*/*-VERIFICATION.md` by hand" in audit
    assert "cat GPD/phases/01-*/*-VERIFICATION.md" not in audit
    assert "cat GPD/phases/02-*/*-VERIFICATION.md" not in audit


def test_discover_command_does_not_emit_phase_only_commit_placeholders_for_standalone_mode() -> None:
    discover = (COMMANDS_DIR / "discover.md").read_text(encoding="utf-8")

    _assert_contains_fragments(
        discover,
        "Produces RESEARCH.md",
        "Do not commit `RESEARCH.md` separately.",
        "phase-only commit messages or file paths",
    )
    assert 'gpd commit "discover(${phase_number})' not in discover
    assert "GPD/phases/${padded_phase}-${phase_slug}/RESEARCH.md" not in discover
    assert "DISCOVERY.md" not in discover


def test_workflows_use_raw_json_when_shell_snippets_pipe_cli_output_into_gpd_json_get() -> None:
    required_machine_fragments = (
        (
            _workflow_authority_text("research-phase"),
            (
                'PHASE_INFO=$(gpd --raw roadmap get-phase "${phase_number}")',
                'gpd --raw state snapshot | gpd json get .decisions --default "[]"',
                'BOOTSTRAP_INIT=$(load_research_phase_stage phase_bootstrap "${PHASE}")',
                'HANDOFF_INIT=$(load_research_phase_stage research_handoff "${phase_number}")',
                'RESEARCH_MODE=$(echo "$BOOTSTRAP_INIT" | gpd json get .research_mode --default balanced)',
            ),
            "research-phase raw json plumbing",
        ),
        (
            _workflow_authority_text("map-research"),
            (
                "BOOTSTRAP_INIT=$(load_map_research_stage map_bootstrap)",
                "MAPPER_AUTHORING_INIT=$(load_map_research_stage mapper_authoring)",
                'gpd --raw --cwd "$target_cwd" init map-research --stage "${stage_name}" -- "${ARGUMENTS:-}"',
                'RESEARCH_MODE=$(echo "$BOOTSTRAP_INIT" | gpd json get .research_mode --default balanced)',
                "Map focus: {map_focus}",
            ),
            "map-research raw json plumbing",
        ),
        (
            (WORKFLOWS_DIR / "progress.md").read_text(encoding="utf-8"),
            (
                "ROADMAP=$(gpd --raw roadmap analyze)",
                'gpd --raw summary-extract <path> --field one_liner | gpd json get .one_liner --default ""',
            ),
            "progress raw json plumbing",
        ),
        (
            _workflow_authority_text("execute-phase"),
            (
                "Load plan inventory with wave grouping from `gpd phase index {phase_number}`.",
                "`objective`",
                "summary-extract for one-liners",
            ),
            "execute-phase raw json plumbing",
        ),
        (
            (WORKFLOWS_DIR / "complete-milestone.md").read_text(encoding="utf-8"),
            (
                "ROADMAP=$(gpd --raw roadmap analyze)",
                'gpd --raw summary-extract "$summary" --field one_liner | gpd json get .one_liner --default ""',
            ),
            "complete-milestone raw json plumbing",
        ),
        (
            (WORKFLOWS_DIR / "show-phase.md").read_text(encoding="utf-8"),
            ('PHASE_INFO=$(gpd --raw roadmap get-phase "${phase_number}")', "ROADMAP=$(gpd --raw roadmap analyze)"),
            "show-phase raw json plumbing",
        ),
    )
    for text, fragments, context in required_machine_fragments:
        _assert_machine_fragments(text, *fragments, context=context)

    for filename in ("graph.md", "validate-conventions.md", "export.md"):
        _assert_machine_fragments(
            (WORKFLOWS_DIR / filename).read_text(encoding="utf-8"),
            "ROADMAP=$(gpd --raw roadmap analyze)",
            context=f"{filename} raw json plumbing",
        )

    _assert_machine_fragments(
        (WORKFLOWS_DIR / "plan-milestone-gaps.md").read_text(encoding="utf-8"),
        "PHASES=$(gpd --raw phase list)",
        context="plan-milestone-gaps raw json plumbing",
    )
    _assert_prompt_contracts(
        (WORKFLOWS_DIR / "transition.md").read_text(encoding="utf-8"),
        fragment_count(
            "transition workflow roadmap analyze call count",
            "ROADMAP=$(gpd --raw roadmap analyze)",
            expected_count=2,
            context="transition workflow roadmap helpers",
        ),
    )
    _assert_machine_fragments(
        (WORKFLOWS_DIR / "verify-phase.md").read_text(encoding="utf-8"),
        'gpd --raw roadmap get-phase "${phase_number}"',
        context="verify-phase raw json plumbing",
    )
    _assert_machine_fragments(
        _workflow_authority_text("verify-work"),
        'gpd --raw roadmap get-phase "${PHASE_ARG}"',
        context="verify-work raw json plumbing",
    )

    for text, fragments, context in (
        (
            _workflow_authority_text("research-phase"),
            ("gpd --raw config get research_mode",),
            "research-phase raw json stale config reads",
        ),
        (
            (COMMANDS_DIR / "research-phase.md").read_text(encoding="utf-8"),
            ('gpd --raw init phase-op --include state,config "${PHASE}"',),
            "research-phase command duplicated init",
        ),
        (
            _workflow_authority_text("map-research"),
            ("MAP_RESEARCH_FOCUS=", "MAP_FOCUS=", "MAP_FOCUS_PROVIDED=", "gpd --raw config get research_mode"),
            "map-research stale focus/config reads",
        ),
        (
            (COMMANDS_DIR / "map-research.md").read_text(encoding="utf-8"),
            ("gpd --raw init map-research",),
            "map-research command duplicated init",
        ),
        (
            (COMMANDS_DIR / "progress.md").read_text(encoding="utf-8"),
            ("ROADMAP=$(gpd --raw roadmap analyze)",),
            "progress command duplicated roadmap read",
        ),
    ):
        _assert_forbidden_fragments(text, *fragments, context=context)

    _assert_semantic_fragments(
        _workflow_authority_text("map-research"),
        "If `map_focus_provided` is true",
        context="map-research provided focus semantics",
    )
    _assert_semantic_fragments(
        (COMMANDS_DIR / "progress.md").read_text(encoding="utf-8"),
        "Follow the included workflow exactly",
        "Do not duplicate",
        context="progress command wrapper semantics",
    )


def test_workflow_and_command_docs_use_raw_output_for_machine_parsed_cli_json() -> None:
    offenders: list[str] = []
    shell_languages = {"bash", "sh", "shell", "zsh"}

    prompt_paths = [
        *sorted(WORKFLOWS_DIR.glob("*.md")),
        *sorted(COMMANDS_DIR.glob("*.md")),
        *sorted(AGENTS_DIR.glob("*.md")),
        *sorted(TEMPLATES_DIR.rglob("*.md")),
        *sorted(REFERENCES_DIR.rglob("*.md")),
    ]

    for path in prompt_paths:
        in_shell_fence = False
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith("```"):
                if in_shell_fence:
                    in_shell_fence = False
                else:
                    in_shell_fence = stripped[3:].strip().lower() in shell_languages
                continue

            if not in_shell_fence:
                continue

            if re.search(r"\bgpd init\b", line) and "gpd --raw init" not in line:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line_number}: {line.strip()}")
            if re.search(r"\bgpd summary-extract\b", line) and "gpd --raw summary-extract" not in line:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line_number}: {line.strip()}")
            if re.search(r"\bgpd state compact\b", line) and "gpd --raw state compact" not in line:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line_number}: {line.strip()}")

    assert not offenders, "Found machine-parsed CLI snippets missing --raw:\n" + "\n".join(offenders)


def test_planner_subagent_prompt_uses_raw_init_placeholder_source() -> None:
    planner_subagent_prompt = (TEMPLATES_DIR / "planner-subagent-prompt.md").read_text(encoding="utf-8")

    assert "| `{phase_number}` | `gpd --raw init plan-phase` |" in planner_subagent_prompt


def test_research_phase_uses_resolved_phase_dir_for_artifact_paths_and_context_lookups() -> None:
    research_workflow = _workflow_authority_text("research-phase")
    research_command = (COMMANDS_DIR / "research-phase.md").read_text(encoding="utf-8")

    assert "Write to: {phase_dir}/{phase_number}-RESEARCH.md" in research_workflow
    _assert_command_delegates_to_workflow(
        research_command,
        "research-phase",
        semantic_fragments=("workflow", "staged init", "return routing"),
        stale_fragments=(
            "Write to: {phase_dir}/{phase_number}-RESEARCH.md",
            "Research file path: {phase_dir}/{phase_number}-RESEARCH.md",
        ),
    )
    assert "GPD/phases/${PHASE}-{slug}/${PHASE}-RESEARCH.md" not in research_workflow
    assert "GPD/phases/${PHASE}-{slug}/${PHASE}-RESEARCH.md" not in research_command


def test_audit_milestone_command_does_not_preload_raw_verification_globs() -> None:
    audit_command = (COMMANDS_DIR / "audit-milestone.md").read_text(encoding="utf-8")

    assert "find_files: GPD/phases/*/*SUMMARY.md" in audit_command
    assert "gpd phase list" in audit_command
    assert "gpd:show-phase <phase-number>" in audit_command
    assert "gpd show-phase <phase-number>" not in audit_command
    assert "find_files: GPD/phases/*/*-VERIFICATION.md" not in audit_command


def test_sensitivity_analysis_workflow_uses_canonical_cli_commands() -> None:
    workflow = (WORKFLOWS_DIR / "sensitivity-analysis.md").read_text(encoding="utf-8")

    assert "gpd --raw init progress --include state,config" in workflow
    assert "gpd --raw init phase-op" in workflow
    assert "gpd uncertainty add" in workflow
    assert "gpd commit" in workflow
    assert "gpd CLI init progress" not in workflow
    assert "gpd CLI init phase-op" not in workflow
    assert "gpd CLI uncertainty add" not in workflow
    assert "gpd CLI commit" not in workflow


def test_phase_research_and_verification_surfaces_keep_anchor_checks_mandatory() -> None:
    phase_researcher = (AGENTS_DIR / "gpd-phase-researcher.md").read_text(encoding="utf-8")
    planner_agent = (AGENTS_DIR / "gpd-planner.md").read_text(encoding="utf-8")
    planner_execution = (REFERENCES_DIR / "planning" / "planner-execution-procedure.md").read_text(encoding="utf-8")
    planner_surface = planner_agent + "\n" + planner_execution
    verify_workflow = _workflow_authority_text("verify-work")
    verify_workflow_expanded = expand_at_includes(verify_workflow, REPO_ROOT / "src/gpd", "/runtime/")

    _assert_prompt_concepts(
        phase_researcher,
        {
            "active anchor section": ("## Active Anchor References",),
            "mandatory anchor inputs": ("contract-critical anchors", "mandatory inputs"),
        },
        context="phase researcher anchor checks",
    )
    assert "FORMALISM.md" in planner_execution
    _assert_prompt_concepts(
        planner_surface,
        {
            "derivation reference table row": ("derivation, analytical, symbolic", "CONVENTIONS.md", "FORMALISM.md"),
            "validation reference table row": ("validation, testing, benchmarks", "VALIDATION.md", "REFERENCES.md"),
        },
        context="planner anchor reference table",
    )
    _assert_prompt_concepts(
        verify_workflow,
        {
            "mandatory contract anchors": ("Do NOT skip", "contract-critical anchors"),
            "blocked contract repair": ("visible-but-blocked contract", "repaired", "authoritative verification scope"),
        },
        context="verify-work anchor checks",
    )
    assert "active_reference_context" in verify_workflow
    assert "project_contract_gate" in verify_workflow
    assert "project_contract_validation" in verify_workflow
    assert "project_contract_load_info" in verify_workflow
    assert "suggest_contract_checks(contract)" in verify_workflow
    _assert_prompt_contracts(
        verify_workflow,
        fragment_count(
            "verify-work raw project contract gate block count",
            "**Project Contract Gate:** {project_contract_gate}",
            expected_count=2,
            context="verify-work contract gate block",
        ),
    )
    _assert_semantic_fragments(
        verify_workflow_expanded,
        "**Project Contract Gate:** {project_contract_gate}",
        context="expanded verify-work contract gate block",
    )
    _assert_prompt_concepts(
        verify_workflow,
        {
            "structured anchor source": (
                "effective_reference_intake",
                "structured source",
                "carry-forward anchors",
                "active_reference_context",
                "readable projection",
                "source of truth",
            ),
        },
        context="verify-work effective reference intake",
    )


def test_phase_researcher_prompt_keeps_the_one_shot_handoff_and_return_contract_visible() -> None:
    phase_researcher = (AGENTS_DIR / "gpd-phase-researcher.md").read_text(encoding="utf-8")
    research_workflow = _workflow_authority_text("research-phase")
    research_command = (COMMANDS_DIR / "research-phase.md").read_text(encoding="utf-8")

    _assert_machine_fragments(
        phase_researcher,
        "## RESEARCH COMPLETE",
        "## RESEARCH BLOCKED",
        "gpd_return:",
        "status: completed",
        "GPD/phases/03-spectral-form-factor/03-RESEARCH.md",
        context="phase researcher return envelope",
    )
    _assert_machine_fragments(
        research_workflow,
        "references/orchestration/continuation-boundary.md",
        "expected_artifacts",
        "child-artifact-gate.md",
        "gpd_return.files_written",
        context="research workflow handoff artifact gate",
    )
    _assert_semantic_fragments(
        research_workflow,
        "fresh continuation handoff",
        context="research workflow continuation handoff",
    )
    _assert_command_delegates_to_workflow(
        research_command,
        "research-phase",
        semantic_fragments=("workflow", "staged init", "return routing"),
    )
    assert 'gpd --raw init research-phase "${phase_arg}" --stage "${stage_name}"' in research_workflow


def test_workflows_surface_structured_proof_review_statuses() -> None:
    verify_workflow = _workflow_authority_text("verify-work")
    verify_phase = (WORKFLOWS_DIR / "verify-phase.md").read_text(encoding="utf-8")
    write_paper = _workflow_authority_text("write-paper")
    peer_review = _workflow_authority_text("peer-review")
    respond_to_referees = _workflow_authority_text("respond-to-referees")
    arxiv_submission = _workflow_authority_text("arxiv-submission")

    _assert_machine_fragments(
        verify_workflow,
        "phase_proof_review_status",
        "proof-review freshness summary",
        context="verify-work proof review status",
    )
    for text, context in (
        (verify_phase, "verify-phase proof review status"),
        (write_paper, "write-paper proof review status"),
        (peer_review, "peer-review proof review status"),
        (respond_to_referees, "respond proof review status"),
        (arxiv_submission, "arxiv proof review status"),
    ):
        _assert_machine_fragments(text, "derived_manuscript_proof_review_status", context=context)
    _assert_semantic_fragments(
        verify_phase,
        "manuscript-local proof-bearing artifact",
        context="verify-phase proof review semantics",
    )
    _assert_semantic_fragments(
        write_paper,
        "proof-review freshness",
        "theorem-bearing results",
        context="write-paper proof review semantics",
    )
    _assert_semantic_fragments(peer_review, "theorem/proof freshness", context="peer-review proof review semantics")
    _assert_semantic_fragments(
        respond_to_referees,
        "proof-review freshness",
        "theorem-bearing revisions",
        context="respond proof review semantics",
    )
    _assert_semantic_fragments(
        arxiv_submission,
        "theorem-proof freshness",
        "resolved manuscript",
        context="arxiv proof review semantics",
    )


def test_verify_phase_and_gap_reverify_prompts_surface_contract_context_before_contract_checks() -> None:
    verify_phase = (WORKFLOWS_DIR / "verify-phase.md").read_text(encoding="utf-8")
    execute_phase = _workflow_authority_text("execute-phase")

    _assert_machine_fragments(
        verify_phase,
        "project_contract_gate",
        "contract_intake",
        "effective_reference_intake",
        "active_reference_context",
        "reference_artifacts_content",
        "protocol_bundle_context",
        context="verify-phase contract context fields",
    )
    assert verify_phase.index("project_contract_gate") < verify_phase.index("suggest_contract_checks(contract)")
    _assert_machine_fragments(
        execute_phase,
        "{GPD_INSTALL_DIR}/workflows/verify-phase.md",
        "{GPD_INSTALL_DIR}/templates/verification-report.md",
        "{GPD_INSTALL_DIR}/templates/contract-results-schema.md",
        "gpd --raw init phase-op {PHASE_NUMBER}",
        "active_reference_context",
        "protocol_bundle_context",
        context="execute-phase verify-phase wiring",
    )


def test_templates_and_workflows_surface_contract_results_and_verdict_ledgers() -> None:
    summary_template = (TEMPLATES_DIR / "summary.md").read_text(encoding="utf-8")

    assert "contract_results" in summary_template
    assert "comparison_verdicts" in summary_template
    assert "plan_contract_ref" in summary_template
    assert "subsystem (optional):" not in summary_template
    assert "tags (optional):" not in summary_template
    assert "plan_contract_ref (required" not in summary_template
    assert "contract_results (required" not in summary_template
    assert "comparison_verdicts (required" not in summary_template
    assert (
        "reload `{GPD_INSTALL_DIR}/templates/contract-results-schema.md` immediately before writing" in summary_template
    )
    assert "uncertainty_markers" in summary_template


def test_validator_backed_examples_use_concrete_machine_readable_values() -> None:
    assert '"stage_id": "reader | literature | math | physics | interestingness"' not in (
        REFERENCES_DIR / "publication" / "peer-review-panel.md"
    ).read_text(encoding="utf-8")
    assert (
        '"claim_type": "main_result | novelty | significance | physical_interpretation | generality | method"'
        not in (REFERENCES_DIR / "publication" / "peer-review-panel.md").read_text(encoding="utf-8")
    )
    assert "claim_kind: theorem | lemma | corollary | proposition | result | claim | other" not in (
        TEMPLATES_DIR / "plan-contract-schema.md"
    ).read_text(encoding="utf-8")
    assert "status: passed|partial|failed|blocked|not_attempted" not in (
        TEMPLATES_DIR / "contract-results-schema.md"
    ).read_text(encoding="utf-8")
    assert "status: passed | gaps_found | expert_needed | human_needed" not in (
        TEMPLATES_DIR / "verification-report.md"
    ).read_text(encoding="utf-8")


def test_convention_templates_are_state_lock_projections_not_authorities() -> None:
    conventions = (TEMPLATES_DIR / "conventions.md").read_text(encoding="utf-8")
    notation = (TEMPLATES_DIR / "notation-glossary.md").read_text(encoding="utf-8")
    mapper = (AGENTS_DIR / "gpd-research-mapper.md").read_text(encoding="utf-8")
    infra = (REFERENCES_DIR / "orchestration" / "agent-infrastructure.md").read_text(encoding="utf-8")

    assert "human-readable projection and audit surface" in conventions
    assert "**Authoritative lock:** `GPD/state.json` -> `convention_lock`" in conventions
    assert "not the source\n> of truth" in conventions
    assert "This glossary is not a second convention authority" in notation
    assert "`state.json.convention_lock` plus the `GPD/CONVENTIONS.md` / `GPD/NOTATION_GLOSSARY.md` projections" in (
        AGENTS_DIR / "gpd-paper-writer.md"
    ).read_text(encoding="utf-8")
    assert "state.json.convention_lock` through `gpd convention set`" in mapper
    assert "authoritative project-level convention lock" not in mapper
    assert "Direct-commit allowlist:" not in infra
    assert "Agents: project-researcher" not in infra
    assert "Agents that write or verify equations" in infra


def test_verification_report_top_level_status_excludes_partial_while_nested_contracts_keep_it() -> None:
    verification_template = (TEMPLATES_DIR / "verification-report.md").read_text(encoding="utf-8")

    assert "Top-level `status` is limited to `passed`, `gaps_found`, `expert_needed`, or `human_needed`" in (
        verification_template
    )
    assert "use `partial`, `gaps_found`" not in verification_template
    assert "Nested `contract_results` entries" in verification_template
    assert "including `partial` when a specific claim, deliverable, or acceptance test is only partly satisfied" in (
        verification_template
    )


def test_plan_tool_preflight_surfaces_across_planning_and_execution_prompts() -> None:
    phase_prompt = (TEMPLATES_DIR / "phase-prompt.md").read_text(encoding="utf-8")
    planner_agent = (AGENTS_DIR / "gpd-planner.md").read_text(encoding="utf-8")
    planner_prompt_template = (TEMPLATES_DIR / "planner-subagent-prompt.md").read_text(encoding="utf-8")
    plan_checker = (AGENTS_DIR / "gpd-plan-checker.md").read_text(encoding="utf-8")
    executor_agent = (AGENTS_DIR / "gpd-executor.md").read_text(encoding="utf-8")
    execute_plan = (WORKFLOWS_DIR / "execute-plan.md").read_text(encoding="utf-8")
    execute_phase = _workflow_authority_text("execute-phase")
    tooling_ref = (REFERENCES_DIR / "tooling" / "tool-integration.md").read_text(encoding="utf-8")
    summary_template = (TEMPLATES_DIR / "summary.md").read_text(encoding="utf-8")
    verification_template = (TEMPLATES_DIR / "verification-report.md").read_text(encoding="utf-8")
    research_verification = (TEMPLATES_DIR / "research-verification.md").read_text(encoding="utf-8")
    verify_workflow = _workflow_authority_text("verify-work")
    verify_phase = (WORKFLOWS_DIR / "verify-phase.md").read_text(encoding="utf-8")
    verifier_agent = (AGENTS_DIR / "gpd-verifier.md").read_text(encoding="utf-8")
    compare_workflow = (WORKFLOWS_DIR / "compare-experiment.md").read_text(encoding="utf-8")
    comparison_template = (TEMPLATES_DIR / "paper" / "experimental-comparison.md").read_text(encoding="utf-8")
    internal_comparison_template = (TEMPLATES_DIR / "paper" / "internal-comparison.md").read_text(encoding="utf-8")

    _assert_machine_fragments(
        phase_prompt,
        "# tool_requirements: # Optional machine-checkable specialized tools. Omit entirely if none.",
        '#     tool: "command"',
        '#     command: "pdflatex --version"',
        "`required` defaults to true when omitted",
        "Quick contract rules:",
        context="phase prompt tool requirements",
    )
    _assert_machine_fragments(
        planner_agent,
        "# tool_requirements: # Machine-checkable specialized tools (omit entirely if none)",
        "tool: command",
        "Use only the closed tool vocabulary the validator accepts",
        "| `tool_requirements` | No       | Machine-checkable specialized tool requirements |",
        context="planner agent tool requirements",
    )
    _assert_machine_fragments(plan_checker, "declare them in `tool_requirements`", context="plan checker tools")
    _assert_machine_fragments(
        executor_agent,
        "Run `gpd validate plan-preflight <PLAN.md path>` from the local CLI.",
        context="executor plan-preflight",
    )
    _assert_machine_fragments(
        execute_plan,
        'PLAN_PREFLIGHT=$(gpd --raw validate plan-preflight "${PLAN_PATH}")',
        context="execute-plan plan-preflight",
    )
    _assert_forbidden_fragments(
        execute_plan, "gpd validate plan-preflight <PLAN.md>", context="execute-plan stale preflight spelling"
    )
    _assert_semantic_fragments(
        phase_prompt,
        "fallback",
        "missing required tool",
        "non-blocking",
        context="phase-prompt tool fallback semantics",
    )
    _assert_machine_fragments(
        execute_phase,
        "require that the selected `PLAN.md` passes `gpd validate plan-preflight <PLAN.md>`",
        context="execute-phase plan-preflight",
    )
    _assert_semantic_fragments(
        planner_prompt_template,
        "`tool_requirements`",
        "`gpd validate plan-preflight <PLAN.md>`",
        "execution-ready",
        context="planner template plan-preflight",
    )
    plan_phase_manifest = validate_workflow_stage_manifest_payload(
        json.loads((REPO_ROOT / "src/gpd/specs/workflows/plan-phase-stage-manifest.json").read_text(encoding="utf-8")),
        expected_workflow_id="plan-phase",
    )
    assert plan_phase_manifest.stage_ids() == (
        "phase_bootstrap",
        "research_routing",
        "planner_authoring",
        "checker_revision",
    )
    assert plan_phase_manifest.stages[0].loaded_authorities == ("workflows/plan-phase/phase-bootstrap.md",)
    for stage in (plan_phase_manifest.stages[2], plan_phase_manifest.stages[3]):
        assert "templates/planner-subagent-prompt.md" in stage.loaded_authorities

    _assert_semantic_fragments(
        execute_phase,
        "`VERIFICATION.md`",
        "schema-owned ledgers",
        "`plan_contract_ref`",
        "`contract_results`",
        "`comparison_verdicts`",
        "`suggested_contract_checks`",
        "verifier-local aliases",
        context="execute-phase verification contract fields",
    )
    _assert_machine_fragments(
        tooling_ref, "declare it as `tool: wolfram` in `tool_requirements`", context="tool integration requirements"
    )
    _assert_forbidden_fragments(
        summary_template,
        "must_haves",
        "verification_inputs",
        "contract_evidence",
        "independently_confirmed",
        context="summary removed verification aliases",
    )
    _assert_semantic_fragments(
        summary_template,
        "`suggested_contract_checks`",
        "verification-only",
        "does not belong in summaries",
        context="summary contract fields",
    )
    _assert_semantic_fragments(
        verification_template,
        "contract_results",
        "machine-readable surface",
        "schema-owned ledgers",
        "verification-side `suggested_contract_checks`",
        context="verification report schema fields",
    )
    _assert_prompt_contracts(
        research_verification,
        machine_exact(
            "research verification report template path",
            "{GPD_INSTALL_DIR}/templates/verification-report.md",
        ),
        semantic_anchor(
            "research verification uses canonical frontmatter contract",
            ("canonical verification frontmatter contract",),
            context="research verification template",
        ),
    )
    _assert_machine_fragments(
        research_verification,
        "status: gaps_found",
        "# Allowed status values: passed|gaps_found|expert_needed|human_needed",
        "comparison_verdicts:",
        "subject_role: decisive",
        "comparison_kind: benchmark",
        "`comparison_kind`: benchmark|prior_work|experiment|cross_method|baseline|other",
        "suggested_contract_checks:",
        "uncertainty_markers:",
        context="research verification schema examples",
    )
    _assert_prompt_contracts(
        verify_workflow,
        fragment_count(
            "verify-work planner template authority count",
            "templates/planner-subagent-prompt.md",
            expected_count=2,
            context="verify-work planner wiring",
        ),
        fragment_count(
            "verify-work planner role instruction count",
            "First, read {GPD_AGENTS_DIR}/gpd-planner.md for your role and instructions.",
            expected_count=2,
            context="verify-work planner wiring",
        ),
    )
    _assert_machine_fragments(
        verify_workflow,
        "tool_requirements",
        "gap_closure",
        "Load the staged researcher-session scaffold and canonical schema pack at this stage.",
        "Keep the session overlay frontmatter compatible with the authoritative verification report.",
        context="verify-work planner and schema wiring",
    )
    _assert_forbidden_fragments(
        verify_workflow,
        "## CHECKPOINT REACHED",
        "The shared planner template owns the canonical planning policy and contract gate.",
        "The shared planner template owns the canonical planning and revision policy.",
        "status: gaps_found",
        "uncertainty_markers:",
        "Allowed body enum values:",
        "suggested_contract_checks:",
        "`suggested_contract_check`",
        "independently_confirmed",
        context="verify-work stale duplicated schema content",
    )
    _assert_machine_fragments(
        verify_phase,
        "Return status (`passed` | `gaps_found` | `expert_needed` | `human_needed`)",
        "gpd verification-report skeleton PLAN.md --write --output",
        "contract_results",
        "Verification targets must stay user-visible",
        "request_template",
        "required_request_fields",
        "supported_binding_fields",
        "run_contract_check(request=..., project_dir=...)",
        "copy the returned `check_key` into the frontmatter `check` field",
        "schema_required_request_fields",
        "schema_required_request_anyof_fields",
        "project_dir",
        context="verify-phase schema and helper wiring",
    )
    _assert_semantic_fragments(
        verify_phase,
        "helper owns frontmatter shape",
        "`plan_contract_ref`",
        "`contract_results`",
        "`comparison_verdicts`",
        "`suggested_contract_checks`",
        "validation",
        context="verify-phase verification helper",
    )
    _assert_forbidden_fragments(
        verify_phase,
        "frontmatter (phase/timestamp/status/score",
        "independently_confirmed",
        "`suggested_contract_check`",
        "must_haves",
        context="verify-phase removed schema aliases",
    )
    _assert_machine_fragments(
        verifier_agent,
        "Use the verification-report helper to serialize the gap ledger",
        "The body must still make every gap actionable",
        "Verification Status:** {passed | gaps_found | expert_needed | human_needed}",
        "schema_required_request_fields",
        "schema_required_request_anyof_fields",
        "project_dir",
        context="verifier schema helper wiring",
    )
    _assert_forbidden_fragments(
        verifier_agent,
        "Each gap has: `subject_kind`",
        "`suggested_contract_check`",
        context="verifier removed schema aliases",
    )
    _assert_machine_fragments(
        execute_plan,
        "`contract_results` is authoritative.",
        "project_contract_validation",
        "project_contract_load_info",
        "visible-but-blocked contract is still not an approved execution contract",
        context="execute-plan contract results wiring",
    )
    _assert_semantic_fragments(
        execute_plan,
        "Autonomy mode",
        "profile",
        "do NOT relax contract-result emission",
        "comparison_verdicts`",
        "decisive",
        "required or attempted",
        "emit `verdict: inconclusive`",
        "`verdict: tension`",
        "instead of omitting",
        context="execute-plan comparison verdicts",
    )
    _assert_prompt_contracts(
        execute_plan,
        machine_exact(
            "execute-plan contract results schema path",
            "{GPD_INSTALL_DIR}/templates/contract-results-schema.md",
        ),
        semantic_anchor(
            "execute-plan reapplies contract-results schema before frontmatter",
            ("Immediately before writing frontmatter", "re-open", "apply it literally"),
            context="execute-plan contract results",
        ),
    )
    _assert_machine_fragments(
        compare_workflow,
        "comparison_verdicts",
        "project_contract_load_info",
        "project_contract_validation",
        "selected_protocol_bundle_ids",
        "protocol_bundle_context",
        "active_reference_context",
        "subject_kind: claim",
        "subject_role: decisive",
        "comparison_kind: experiment",
        "verdict: pass",
        "omit `protocol_bundle_ids` and `bundle_expectations` entirely",
        context="compare-experiment contract wiring",
    )
    _assert_semantic_fragments(
        compare_workflow,
        "approved contract",
        "`project_contract_gate.authoritative`",
        "true",
        context="compare-experiment contract gate",
    )
    _assert_forbidden_fragments(
        compare_workflow,
        "protocol_bundle_ids (optional):",
        "bundle_expectations (optional):",
        "subject_kind: claim|deliverable|acceptance_test|reference",
        "comparison_kind: benchmark|prior_work|experiment|cross_method|baseline|other",
        "verdict: pass | tension | fail | inconclusive",
        context="compare-experiment removed comparison aliases",
    )
    for context, text, comparison_kind in (
        ("experimental comparison template", comparison_template, "experiment"),
        ("internal comparison template", internal_comparison_template, "cross_method"),
    ):
        _assert_machine_fragments(
            text,
            "`comparison_verdicts` is a closed schema",
            "subject_kind: claim",
            "subject_role: decisive",
            f"comparison_kind: {comparison_kind}",
            "verdict: pass",
            "omit `protocol_bundle_ids` and `bundle_expectations` entirely",
            context=context,
        )
        _assert_forbidden_fragments(
            text,
            "protocol_bundle_ids (optional):",
            "bundle_expectations (optional):",
            "subject_kind: claim|deliverable|acceptance_test|reference",
            "comparison_kind: benchmark|prior_work|experiment|cross_method|baseline|other",
            "verdict: pass | tension | fail | inconclusive",
            "verdict: pass|tension|fail|inconclusive",
            context=context,
        )
    _assert_semantic_fragments(
        executor_agent,
        "Profiles",
        "autonomy modes",
        "do NOT relax contract-result emission",
        context="executor contract results",
    )
    _assert_semantic_fragments(
        verifier_agent,
        "Use claim IDs",
        "deliverable IDs",
        "acceptance test IDs",
        "reference IDs",
        "forbidden proxy IDs",
        "directly from the `contract` block",
        context="verifier contract IDs",
    )


def test_execute_phase_workflow_surfaces_project_contract_validation_gate() -> None:
    execute_workflow = _workflow_authority_text("execute-phase")

    assert "project_contract_validation" in execute_workflow
    assert "project_contract_load_info" in execute_workflow
    _assert_machine_fragments(
        execute_workflow,
        "contract_gate_stop:",
        "ref=contract-authority-gate#blocked-lifecycle-stop-phrase",
        "primary=gpd:sync-state|gpd:new-project",
        "rerun=gpd:execute-phase ${PHASE_ARG}",
        context="execute-phase contract gate stop tuple",
    )

    # The claim<->deliverable alignment precheck is wired into execute-phase.md
    # and references the helpers/CLI provided by the contract alignment layer.
    alignment_step = _extract_between(
        execute_workflow,
        '<step name="claim_deliverable_alignment_check">',
        "</step>",
    )
    assert "gpd contract alignment-status" in alignment_step
    assert "gpd contract fingerprint" in alignment_step
    assert "gpd contract context-fingerprint" in alignment_step
    assert "gpd contract alignment-summary" in alignment_step
    assert (
        'gpd contract record-alignment --contract-hash "$CONTRACT_HASH" --context-hash "$CONTEXT_HASH"'
    ) in alignment_step
    assert "claim_deliverable_alignment_check: skipped (already confirmed this session)" in alignment_step


def test_execute_and_autonomous_gate_execution_before_plan_work() -> None:
    execute_phase = _workflow_authority_text("execute-phase")
    autonomous = _autonomous_authority_text()

    execute_gate = _extract_between(
        execute_phase,
        '<step name="validate_selected_plans_before_execution" priority="first">',
        "</step>",
    )
    _assert_prompt_concepts(
        execute_gate,
        {
            "blocks execution-side work before validation": (
                "workspace scripts",
                "numerical computations",
                "task dispatches",
                "subagents",
                "artifact writes",
            ),
            "plan repair route": ("gpd:plan-phase {N}", "supported public plan repair route"),
        },
        context="execute-phase selected-plan gate",
    )
    assert 'gpd validate plan-contract "$plan"' in execute_gate
    assert 'if ! gpd verify plan "$plan"; then' in execute_gate
    assert 'PLAN_PREFLIGHT=$(gpd --raw validate plan-preflight "$plan")' in execute_gate
    assert 'gpd verify references "$plan"' in execute_gate
    assert 'gpd phase validate-waves "$phase_number"' in execute_gate

    _assert_prompt_concepts(
        autonomous,
        {
            "lifecycle gate before execute-phase": (
                "lifecycle gate",
                "execute-phase",
            ),
            "stop before execution-side work": (
                "stop before",
                "workspace scripts",
                "numerical computations",
                "task dispatches",
                "subagents",
                "artifact writes",
            ),
            "repair goes through child commands": ("gpd:plan-phase ${PHASE_NUM}", "gpd:execute-phase ${PHASE_NUM}"),
        },
        context="autonomous execution-before-plan gate",
    )
    assert 'gpd --raw validate lifecycle-contract-gate execute-phase "${PHASE_NUM}"' in autonomous
    assert 'gpd --raw validate lifecycle-contract-gate plan-phase "${PHASE_NUM}"' in autonomous
    assert "gpd:plan-phase" in autonomous
    assert "gpd:execute-phase" in autonomous
    assert "--revise" not in execute_phase
    assert "--revise" not in autonomous


def test_execute_phase_and_execute_plan_use_staged_execution_bootstrap_instead_of_monolithic_init() -> None:
    execute_workflow = _workflow_authority_text("execute-phase")
    execute_plan = (WORKFLOWS_DIR / "execute-plan.md").read_text(encoding="utf-8")

    _assert_workflow_calls_staged_init_for_manifest_stages("execute-phase", execute_workflow)
    assert 'gpd --raw init execute-phase "${phase}" --include state,config' not in execute_plan
    assert 'gpd --raw init execute-phase "${phase}" --stage phase_bootstrap' in execute_plan
    assert 'gpd --raw init execute-phase "${phase}" --stage phase_classification' in execute_plan
    assert 'gpd --raw init execute-phase "${phase}" --stage wave_planning' in execute_plan
    assert 'gpd --raw init execute-phase "${phase}" --stage aggregate_and_verify' in execute_plan


def test_execute_phase_and_execute_plan_surface_required_reference_and_state_ownership_guidance() -> None:
    execute_command = (COMMANDS_DIR / "execute-phase.md").read_text(encoding="utf-8")
    execute_workflow = _workflow_authority_text("execute-phase")
    execute_plan = (WORKFLOWS_DIR / "execute-plan.md").read_text(encoding="utf-8")

    assert "{GPD_INSTALL_DIR}/references/orchestration/artifact-surfacing.md" in execute_workflow
    assert "{GPD_INSTALL_DIR}/references/execution/github-lifecycle.md" in execute_plan
    assert (
        "substitute the repository's actual default branch and remote names for `<default-branch>` and `<remote-name>`"
    ) in execute_plan
    assert "update state, resume" in execute_command
    assert (
        "The orchestrator applies them through `gpd apply-return-updates` after each agent completes."
        in execute_workflow
    )
    assert "STATE.md is updated after each wave completes" not in execute_command
    assert "By the time the wave-complete report is emitted" in execute_workflow
    assert "continuation_update" in execute_plan
    assert "session_update" not in execute_plan


def test_verification_prompts_keep_suggested_contract_check_bindings_schema_tight() -> None:
    verification_template = (TEMPLATES_DIR / "verification-report.md").read_text(encoding="utf-8")
    research_verification = (TEMPLATES_DIR / "research-verification.md").read_text(encoding="utf-8")
    verify_workflow = _workflow_authority_text("verify-work")
    verifier_agent = (AGENTS_DIR / "gpd-verifier.md").read_text(encoding="utf-8")

    assert 'suggested_subject_id: ""' not in verification_template
    assert 'suggested_subject_id: [contract id or ""]' not in research_verification
    assert 'suggested_subject_id: [contract id or ""]' not in verify_workflow
    assert "suggested_subject_id: acceptance-test-main" in research_verification
    assert "suggested_subject_id: reference-main" in research_verification
    assert "suggested_subject_id: acceptance-test-main" not in verify_workflow
    assert "suggested_subject_id: reference-main" not in verify_workflow
    assert "acceptance-test-main" in research_verification
    assert "suggested_contract_checks" in verification_template
    assert (
        "Reload `{GPD_INSTALL_DIR}/templates/contract-results-schema.md` immediately before writing"
        in verification_template
    )
    assert "proof-audit rules in the canonical schema" in verification_template
    assert "{GPD_INSTALL_DIR}/templates/verification-report.md" in verifier_agent
    assert "{GPD_INSTALL_DIR}/templates/contract-results-schema.md" in verifier_agent
    assert "@{GPD_INSTALL_DIR}/templates/verification-report.md" not in verifier_agent
    assert "@{GPD_INSTALL_DIR}/templates/contract-results-schema.md" not in verifier_agent
    assert "do not inline or recreate their full YAML" in verifier_agent
    assert "proof-audit linkage" in verifier_agent
    assert "verification-report helper to serialize the gap ledger" in verifier_agent
    assert "The body must still make every gap actionable" in verifier_agent
    assert "Each gap has: `subject_kind`" not in verifier_agent
    assert "Verification Status:** {passed | gaps_found | expert_needed | human_needed}" in verifier_agent


def test_lane5_prompt_examples_keep_schema_valid_contract_fields_visible() -> None:
    planner = (AGENTS_DIR / "gpd-planner.md").read_text(encoding="utf-8")
    plan_checker = (AGENTS_DIR / "gpd-plan-checker.md").read_text(encoding="utf-8")
    parameter_sweep = (WORKFLOWS_DIR / "parameter-sweep.md").read_text(encoding="utf-8")
    research_verification = (TEMPLATES_DIR / "research-verification.md").read_text(encoding="utf-8")
    verify_work = _workflow_authority_text("verify-work")
    verifier = (AGENTS_DIR / "gpd-verifier.md").read_text(encoding="utf-8")
    executor_example = (REFERENCES_DIR / "execution" / "executor-worked-example.md").read_text(encoding="utf-8")
    phase_prompt = _expand_prompt_surface(TEMPLATES_DIR / "phase-prompt.md")

    assert "context_intake:" in planner
    assert 'must_read_refs: ["ref-textbook"]' in planner
    assert 'references: ["ref-main"]' in phase_prompt
    assert "context_intake:" in plan_checker
    assert "why_it_matters:" in plan_checker
    assert "required_actions: [read, compare, cite]" in plan_checker
    assert 'procedure: "Compare the computed value against the benchmark anchor within tolerance."' in plan_checker
    assert "context_intake:" in parameter_sweep
    assert "must_read_refs: [ref-sweep-anchor]" in parameter_sweep
    assert "reference-main" in research_verification
    assert "acceptance-test-main" in research_verification
    assert "linked_ids: [deliverable-main, acceptance-test-main, reference-main]" in research_verification
    assert "evidence:\n        - verifier: gpd-verifier" in research_verification
    assert 'evidence_path: "GPD/phases/01-benchmark/01-VERIFICATION.md"' in research_verification
    assert "started:" in research_verification
    assert "updated:" in research_verification
    assert "test-benchmark" not in research_verification
    assert "reference-main" not in verify_work
    assert "acceptance-test-main" not in verify_work
    assert "test-benchmark" not in verify_work
    assert "{GPD_INSTALL_DIR}/templates/verification-report.md" in verifier
    assert "{GPD_INSTALL_DIR}/templates/contract-results-schema.md" in verifier
    assert "@{GPD_INSTALL_DIR}/templates/verification-report.md" not in verifier
    assert "@{GPD_INSTALL_DIR}/templates/contract-results-schema.md" not in verifier
    assert "reference-main" not in verifier
    assert "acceptance-test-main" not in verifier
    assert "test-benchmark" not in verifier
    assert "deliverables:" in executor_example
    assert "references:" in executor_example
    assert 'reference_id: "reference-qed-benchmark"' in executor_example
    assert "deliverable-self-energy-derivation" in executor_example


def test_verification_prompt_wiring_rejects_invalid_reference_and_proxy_scaffolds(tmp_path: Path) -> None:
    phase_dir = tmp_path / "GPD" / "phases" / "01-benchmark"
    phase_dir.mkdir(parents=True)
    (phase_dir / "01-01-PLAN.md").write_text(
        _plan_with_contract_text(),
        encoding="utf-8",
    )
    verification_path = phase_dir / "01-VERIFICATION.md"
    verification_path.write_text(
        (CONTRACT_RESULT_FIXTURES / "verification_with_contract_results.md")
        .read_text(encoding="utf-8")
        .replace(
            "  references:\n"
            "    ref-benchmark:\n"
            "      status: completed\n"
            "      completed_actions: [read, compare, cite]\n"
            "      missing_actions: []\n"
            "      summary: Benchmark anchor was surfaced.\n",
            "  references:\n"
            "    ref-benchmark:\n"
            "      completed_actions: [read, cite]\n"
            "      missing_actions: [compare]\n"
            "      summary: Benchmark anchor was surfaced.\n",
            1,
        )
        .replace(
            "  forbidden_proxies:\n    fp-benchmark:\n      status: rejected\n",
            "  forbidden_proxies:\n    fp-benchmark:\n      notes: Proxy scaffold left status unspecified.\n",
            1,
        ),
        encoding="utf-8",
    )

    result = validate_frontmatter(
        verification_path.read_text(encoding="utf-8"),
        "verification",
        source_path=verification_path,
    )

    assert result.valid is False
    assert any(
        "references.ref-benchmark.status must be explicit in contract-backed contract_results" in error
        for error in result.errors
    )
    assert any(
        "forbidden_proxies.fp-benchmark.status must be explicit in contract-backed contract_results" in error
        for error in result.errors
    )


def test_verification_prompt_wiring_requires_suggested_checks_for_compare_required_references(
    tmp_path: Path,
) -> None:
    phase_dir = tmp_path / "GPD" / "phases" / "01-benchmark"
    phase_dir.mkdir(parents=True)
    (phase_dir / "01-01-PLAN.md").write_text(
        _plan_with_contract_text(),
        encoding="utf-8",
    )
    verification_path = phase_dir / "01-VERIFICATION.md"
    verification_path.write_text(
        (CONTRACT_RESULT_FIXTURES / "verification_with_contract_results.md")
        .read_text(encoding="utf-8")
        .replace(
            "status: passed\nscore: 3/3 contract targets verified\n",
            "status: gaps_found\nscore: 2/3 contract targets verified\n",
            1,
        )
        .replace(
            "  references:\n"
            "    ref-benchmark:\n"
            "      status: completed\n"
            "      completed_actions: [read, compare, cite]\n"
            "      missing_actions: []\n"
            "      summary: Benchmark anchor was surfaced.\n",
            "  references:\n"
            "    ref-benchmark:\n"
            "      status: completed\n"
            "      completed_actions: [read, cite]\n"
            "      missing_actions: []\n"
            "      summary: Benchmark anchor was surfaced.\n",
            1,
        ),
        encoding="utf-8",
    )

    result = validate_frontmatter(
        verification_path.read_text(encoding="utf-8"),
        "verification",
        source_path=verification_path,
    )

    assert result.valid is False
    assert any(
        "suggested_contract_checks: required when decisive benchmark/cross-method checks remain missing, partial, or incomplete"
        in error
        for error in result.errors
    )


def test_verifier_entry_points_expose_contract_check_tools() -> None:
    verify_work_meta, _ = _parse_frontmatter((COMMANDS_DIR / "verify-work.md").read_text(encoding="utf-8"))
    verifier_meta, _ = _parse_frontmatter((AGENTS_DIR / "gpd-verifier.md").read_text(encoding="utf-8"))

    verify_work_tools = verify_work_meta.get("allowed-tools", [])
    verifier_tools = _parse_tools(verifier_meta.get("tools"))

    for tool_name in (
        "mcp__gpd_verification__get_bundle_checklist",
        "mcp__gpd_verification__suggest_contract_checks",
        "mcp__gpd_verification__run_contract_check",
    ):
        assert tool_name in verify_work_tools
        assert tool_name in verifier_tools


def test_manuscript_documentation_uses_current_manuscript_root_paths_only() -> None:
    explain = (WORKFLOWS_DIR / "explain.md").read_text(encoding="utf-8")
    manuscript_outline = (TEMPLATES_DIR / "paper" / "manuscript-outline.md").read_text(encoding="utf-8")
    execute_phase = _workflow_authority_text("execute-phase")
    figure_tracker = (TEMPLATES_DIR / "paper" / "figure-tracker.md").read_text(encoding="utf-8")

    assert "GPD/paper/" not in explain
    assert "GPD/paper/" not in manuscript_outline
    assert "paper/EXPERIMENTAL_COMPARISON.md" in execute_phase
    assert "${PAPER_DIR}/EXPERIMENTAL_COMPARISON.md" not in execute_phase
    assert "GPD/paper/EXPERIMENTAL_COMPARISON.md" not in execute_phase
    assert "fig-main.pdf" not in figure_tracker


def test_explain_surfaces_keep_workspace_rooted_outputs_and_honest_standalone_targeting() -> None:
    explain_command = (COMMANDS_DIR / "explain.md").read_text(encoding="utf-8")
    explain_workflow = (WORKFLOWS_DIR / "explain.md").read_text(encoding="utf-8")

    assert "standalone question with an explicit topic" in explain_command
    assert (
        "GPD-authored explanation artifacts stay under `GPD/explanations/` rooted at the current workspace."
        in explain_command
    )
    assert (
        "If `$ARGUMENTS` is empty in standalone mode, stop and ask the user to rerun with an explicit concept/topic"
        in explain_command
    )
    assert (
        "standalone explanations only when the standalone request already names an explicit target" in explain_workflow
    )
    assert "Do not promise that an empty standalone launch can be clarified later" in explain_workflow
    assert (
        "Keep all GPD-authored explanation artifacts rooted under `GPD/explanations/` in the current workspace."
        in explain_workflow
    )


def test_publication_workflows_describe_recursive_manuscript_tree_inputs() -> None:
    arxiv_submission = _workflow_authority_text("arxiv-submission")
    write_paper = _workflow_authority_text("write-paper")
    respond = _workflow_authority_text("respond-to-referees")

    assert "Keep `\\input{}` / `\\include{}` chains only if every source file is packaged" in arxiv_submission
    assert (
        "If the manuscript root is not already `paper/`, stage the package in a temporary submission tree"
        in arxiv_submission
    )
    assert "Manuscript tree: all `.tex` files under `${PAPER_DIR}` recursively" in write_paper
    assert "resolved section file within the manuscript tree rooted at `${PAPER_DIR}`" in respond


def test_review_and_verification_prompts_explicitly_surface_schema_sources_and_contract_context() -> None:
    peer_review = _workflow_authority_text("peer-review")
    peer_review_command = (COMMANDS_DIR / "peer-review.md").read_text(encoding="utf-8")
    verify_command = (COMMANDS_DIR / "verify-work.md").read_text(encoding="utf-8")
    verify_workflow = _workflow_authority_text("verify-work")
    write_paper = _workflow_authority_text("write-paper")
    write_paper_command = (COMMANDS_DIR / "write-paper.md").read_text(encoding="utf-8")
    respond_to_referees = _workflow_authority_text("respond-to-referees")
    sync_state = _workflow_authority_text("sync-state")
    review_reader = (AGENTS_DIR / "gpd-review-reader.md").read_text(encoding="utf-8")
    review_literature = (AGENTS_DIR / "gpd-review-literature.md").read_text(encoding="utf-8")
    review_math = (AGENTS_DIR / "gpd-review-math.md").read_text(encoding="utf-8")
    review_physics = (AGENTS_DIR / "gpd-review-physics.md").read_text(encoding="utf-8")
    review_significance = (AGENTS_DIR / "gpd-review-significance.md").read_text(encoding="utf-8")
    referee = (AGENTS_DIR / "gpd-referee.md").read_text(encoding="utf-8")
    verify_work_staging = registry.get_command("verify-work").staged_loading
    assert verify_work_staging is not None
    interactive_validation = next(stage for stage in verify_work_staging.stages if stage.id == "interactive_validation")
    inventory_build = next(stage for stage in verify_work_staging.stages if stage.id == "inventory_build")

    _assert_semantic_fragments(
        peer_review,
        "Reader-visible claims",
        "surfaced evidence",
        "first-class",
        "compact `REVIEW_CARRY_FORWARD`",
        "before spawning panel stages",
        "Do not repeat",
        "full contract/reference payloads",
        "every child prompt",
        context="peer-review carry-forward context",
    )
    _assert_machine_fragments(
        peer_review,
        "effective_reference_intake",
        "project_contract_validation",
        "project_contract_load_info",
        "Carry-forward packet: {REVIEW_CARRY_FORWARD}",
        "project_contract_gate.authoritative",
        context="peer-review contract context",
    )
    _assert_forbidden_fragments(
        peer_review,
        "reference artifacts content {reference_artifacts_content}",
        context="peer-review carry-forward payload",
    )
    _assert_prompt_contracts(
        peer_review,
        semantic_anchor(
            "peer-review treats project contract gate as authoritative only when approved",
            (
                "`project_contract_gate`",
                "authoritative",
                "`project_contract_gate.authoritative`",
                "diagnostics/context",
                "carry-forward evidence",
            ),
            context="peer-review project contract gate",
        ),
        forbidden_duplicate(
            "peer-review single contract gate authority note",
            "Treat `project_contract_gate` as authoritative.",
            context="peer-review project contract gate",
        ),
    )
    _assert_machine_fragments(
        respond_to_referees,
        "project_contract_gate",
        "project_contract_load_info",
        "project_contract_validation",
        "Treat the project contract as authoritative only when",
        "`project_contract_gate.authoritative` is true",
        context="respond-to-referees contract gate",
    )
    _assert_forbidden_fragments(
        peer_review_command,
        "templates/paper/review-ledger-schema.md",
        "templates/paper/referee-decision-schema.md",
        "references/publication/peer-review-panel.md",
        context="peer-review command wrapper schema bodies",
    )
    _assert_forbidden_fragments(
        verify_command,
        "templates/verification-report.md",
        "templates/contract-results-schema.md",
        "Severity Classification",
        "One check at a time, plain text responses, no interrogation.",
        "Physics verification is not binary:",
        "For deeper focused analysis",
        context="verify-work command wrapper schema bodies",
    )
    _assert_command_delegates_to_workflow(
        verify_command,
        "verify-work",
        semantic_fragments=(
            "staged workflow authorities own",
            "detailed check taxonomy",
            "bootstraps the canonical verification surface",
            "delegates the physics checks",
        ),
        context="verify-work command wrapper",
    )
    _assert_semantic_fragments(
        verify_workflow,
        "Load the staged researcher-session scaffold",
        "session overlay frontmatter",
        "compatible",
        "authoritative verification report",
        context="verify-work interactive validation stage",
    )
    interactive_conditionals = tuple(
        authority
        for conditional in interactive_validation.conditional_authorities
        for authority in conditional.authorities
    )
    assert {"templates/verification-report.md", "templates/contract-results-schema.md"} <= set(interactive_conditionals)
    assert "references/verification/meta/verification-independence.md" in inventory_build.loaded_authorities
    _assert_forbidden_fragments(
        write_paper_command,
        "templates/paper/review-ledger-schema.md",
        "templates/paper/referee-decision-schema.md",
        "references/publication/peer-review-panel.md",
        context="write-paper command wrapper schema bodies",
    )
    _assert_machine_fragments(
        write_paper,
        "Canonical schema for `${PAPER_DIR}/reproducibility-manifest.json`:",
        context="write-paper reproducibility schema",
    )
    _assert_machine_fragments(
        sync_state,
        "Canonical reconciliation contract:",
        "state-json-schema.md",
        "state.json is authoritative for structured fields",
        "optional_commit",
        'gpd --raw --cwd "$PROJECT_ROOT" state repair-sync',
        context="sync-state reconciliation",
    )
    _assert_semantic_fragments(
        sync_state,
        "workflow",
        "fail-closed",
        context="sync-state reconciliation",
    )
    _assert_semantic_fragments(
        sync_state,
        "Do not",
        "move or delete files",
        "prompt",
        context="sync-state reconciliation",
    )
    _assert_forbidden_fragments(
        sync_state,
        "gpd --raw state snapshot",
        "Proceed with reconciliation? (y/n)",
        "determine which source is more recent",
        context="sync-state stale reconciliation flow",
    )
    _assert_semantic_fragments(
        peer_review, "repair the blocked contract before retrying", context="peer-review blocked contract"
    )
    _assert_machine_fragments(
        review_reader,
        "${REVIEW_ROOT}/CLAIMS{round_suffix}.json",
        "${REVIEW_ROOT}/STAGE-reader{round_suffix}.json",
        context="review reader schema paths",
    )
    _assert_semantic_fragments(
        review_reader,
        "shared source of truth",
        "`ClaimIndex`",
        "`StageReviewReport`",
        "Stage 1",
        "${REVIEW_ROOT}/CLAIMS{round_suffix}.json",
        context="review reader schema visibility",
    )

    _assert_semantic_fragments(
        review_reader,
        "theorem kind",
        "explicit hypotheses",
        "free target parameters",
        "theorem-like claims",
        context="review reader claim structure",
    )
    _assert_semantic_fragments(
        review_reader,
        "`findings`",
        "overclaiming",
        "missing promised deliverables",
        "claim-structure blockers",
        context="review reader findings",
    )
    for label, text, output_path in (
        ("literature", review_literature, "${REVIEW_ROOT}/STAGE-literature{round_suffix}.json"),
        ("math", review_math, "${REVIEW_ROOT}/STAGE-math{round_suffix}.json"),
        ("physics", review_physics, "${REVIEW_ROOT}/STAGE-physics{round_suffix}.json"),
        ("significance", review_significance, "${REVIEW_ROOT}/STAGE-interestingness{round_suffix}.json"),
    ):
        _assert_machine_fragments(text, output_path, context=f"review {label} output path")
        _assert_semantic_fragments(
            text,
            "shared source of truth",
            "`StageReviewReport` contract",
            context=f"review {label} schema visibility",
        )
    _assert_semantic_fragments(
        review_literature,
        "`findings`",
        "claimed advance",
        "prior work",
        "novelty assessment",
        "`reject`",
        "`major_revision`",
        context="literature review findings",
    )
    _assert_semantic_fragments(
        review_math,
        "theorem-bearing Stage 1 claim",
        "exactly one `proof_audits[]` entry",
        "`claim_id`",
        "`claims_reviewed`",
        "Do not emit proof audits",
        "unreviewed claims",
        "do not repeat `claim_id` values",
        "theorem-to-proof audit",
        "what the proof actually uses",
        "silently specializes away",
        "coverage gaps",
        "`recommendation_ceiling`",
        "`major_revision`",
        "`reject`",
        "central theorem-proof gaps",
        context="math review recommendation ceiling",
    )
    _assert_semantic_fragments(
        review_physics,
        "`findings`",
        "physical assumptions",
        "regime of validity",
        "supported physical conclusions",
        "overstated connections",
        context="physics review findings",
    )
    _assert_semantic_fragments(
        review_physics,
        "`recommendation_ceiling`",
        "`major_revision`",
        "physical conclusions",
        "actual evidence",
        context="physics review recommendation ceiling",
    )
    _assert_semantic_fragments(
        review_significance,
        "`findings`",
        "why the result might matter",
        "venue fit",
        "claim proportionality",
        context="significance review findings",
    )
    _assert_semantic_fragments(
        review_significance,
        "`recommendation_ceiling`",
        "`reject`",
        "significance",
        "venue fit",
        "`major_revision`",
        "technically competent",
        "physically uninteresting",
        "overclaimed",
        context="significance review recommendation ceiling",
    )
    for text in (review_reader, review_literature, review_math, review_physics, review_significance):
        _assert_forbidden_fragments(
            text,
            "Required schema for",
            "closed schema; do not invent extra keys",
            context="review agent schema prose duplication",
        )
    _assert_machine_fragments(
        referee,
        "re-open `{GPD_INSTALL_DIR}/references/publication/peer-review-panel.md`",
        context="referee panel reopen",
    )


def test_peer_review_prompt_includes_concise_stage_map_for_users() -> None:
    peer_review_command = (COMMANDS_DIR / "peer-review.md").read_text(encoding="utf-8")
    peer_review_workflow = _workflow_authority_text("peer-review")

    _assert_prompt_concepts(
        peer_review_command,
        {
            "user-facing stage map": ("announcing the panel", "each stage", "concise sentence"),
        },
        context="peer-review command stage map",
    )
    _assert_prompt_concepts(
        peer_review_workflow,
        {
            "pre-spawn stage map": ("Before spawning", "reviewer", "concise stage map"),
        },
        context="peer-review workflow stage map",
    )
    stage_map = {
        "Stage 1": ("Stage 1", "claims"),
        "Stages 2-3": ("Stages 2-3", "prior work", "mathematical soundness", "parallel"),
        "Stage 4": ("Stage 4", "physical interpretation", "supported"),
        "Stage 5": ("Stage 5", "significance", "venue fit"),
        "Stage 6": ("Stage 6", "synthesizes", "final recommendation"),
    }
    _assert_prompt_concepts(peer_review_command, stage_map, context="peer-review command stage roles")
    _assert_prompt_concepts(peer_review_workflow, stage_map, context="peer-review workflow stage roles")
    _assert_ordered_prompt_fragments(
        peer_review_command,
        ("Stage 1", "Stages 2-3", "Stage 4", "Stage 5", "Stage 6"),
        context="peer-review command stage order",
    )
    _assert_ordered_prompt_fragments(
        peer_review_workflow,
        ("Stage 1", "Stages 2-3", "Stage 4", "Stage 5", "Stage 6"),
        context="peer-review workflow stage order",
    )


def test_peer_review_command_limits_default_manuscript_targets_to_canonical_roots() -> None:
    peer_review_command = (COMMANDS_DIR / "peer-review.md").read_text(encoding="utf-8")

    _assert_semantic_fragments(
        peer_review_command,
        "default in-project manuscript family",
        "`paper/`",
        "`manuscript/`",
        "`draft/`",
        "PAPER-CONFIG.json",
        "canonical current manuscript entrypoint rules",
        context="peer-review command manuscript roots",
    )

    _assert_semantic_fragments(
        peer_review_command,
        "Explicit external artifact intake",
        "`.tex`",
        "`.md`",
        "`.pdf`",
        "`.docx`",
        "`.xlsx`",
        "manifest/config-resolved",
        "Do not use ad hoc wildcard discovery",
        "specific artifact path",
        context="peer-review command manuscript roots",
    )
    _assert_forbidden_fragments(
        peer_review_command,
        "find paper manuscript draft",
        "find . -maxdepth 3",
        context="peer-review command manuscript roots",
    )


def test_peer_review_referee_surface_fail_closed_final_adjudication_contract() -> None:
    referee = (AGENTS_DIR / "gpd-referee.md").read_text(encoding="utf-8")
    peer_review = _workflow_authority_text("peer-review")
    panel = (REFERENCES_DIR / "publication" / "peer-review-panel.md").read_text(encoding="utf-8")
    reliability = (REFERENCES_DIR / "publication" / "peer-review-reliability.md").read_text(encoding="utf-8")

    _assert_prompt_concepts(
        peer_review,
        {
            "fail closed before recommendation": (
                "required staged-review artifact",
                "missing",
                "malformed",
                "wrong round suffix",
                "STOP",
                "final recommendation",
            ),
            "blank manuscript path fails validation": (
                "blank `manuscript_path`",
                "${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json",
                "${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json",
                "validation failures",
            ),
        },
        context="peer-review workflow fail-closed final adjudication",
    )
    _assert_semantic_fragments(
        referee,
        "Do not fall back",
        "standalone review",
        context="peer-review referee fail-closed final adjudication",
    )
    _assert_forbidden_fragments(
        referee,
        "fall back to direct standalone review",
        context="peer-review referee fail-closed final adjudication",
    )
    _assert_prompt_concepts(
        reliability,
        {
            "strict referee decision validation": (
                "gpd validate referee-decision",
                "--strict",
                "--ledger",
                "manuscript_path",
            ),
            "strict ledger validation": ("gpd validate review-ledger", "non-empty `manuscript_path`"),
            "blank manuscript path contract failure": ("blank `manuscript_path`", "contract failure"),
        },
        context="peer-review reliability final adjudication",
    )
    _assert_machine_fragments(
        reliability,
        "bibliography_audit_clean",
        "reproducibility_ready",
        context="peer-review reliability final adjudication fields",
    )
    _assert_prompt_concepts(
        panel,
        {
            "Stage 6 owns only adjudication output": ("Stage 6", "write only", "adjudication artifacts", "Output"),
            "upstream evidence is read-only": (
                "${REVIEW_ROOT}/CLAIMS{round_suffix}.json",
                "${REVIEW_ROOT}/STAGE-*.json",
                "${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md",
                "read-only upstream evidence",
            ),
            "fail closed routes upstream": (
                "missing",
                "malformed",
                "stale",
                "mutually inconsistent",
                "Stage 6",
                "fail closed",
                "earliest failing upstream stage",
            ),
            "consistency report is sidecar": (
                "${PUBLICATION_ROOT}/CONSISTENCY-REPORT.md",
                "diagnostic sidecar",
            ),
            "no upstream repair": ("Do not repair", "upstream stage artifacts", "final adjudication"),
        },
        context="peer-review panel Stage 6 boundary",
    )


def test_publication_prompts_surface_strict_semantic_manuscript_gates() -> None:
    arxiv = (COMMANDS_DIR / "arxiv-submission.md").read_text(encoding="utf-8")
    respond = (COMMANDS_DIR / "respond-to-referees.md").read_text(encoding="utf-8")
    peer_review_workflow = _workflow_authority_text("peer-review")
    peer_review_index = (WORKFLOWS_DIR / "peer-review.md").read_text(encoding="utf-8")
    write_paper_workflow = _workflow_authority_text("write-paper")
    respond_workflow = _workflow_authority_text("respond-to-referees")
    arxiv_workflow = _workflow_authority_text("arxiv-submission")
    shared_preflight = (TEMPLATES_DIR / "paper" / "publication-manuscript-root-preflight.md").read_text(
        encoding="utf-8"
    )

    _assert_forbidden_fragments(
        peer_review_index,
        PUBLICATION_SHARED_PREFLIGHT_INCLUDE,
        context="peer-review workflow publication preflight include",
    )
    _assert_machine_fragments(
        peer_review_workflow,
        "{GPD_INSTALL_DIR}/templates/paper/publication-manuscript-root-preflight.md",
        context="peer-review workflow publication preflight include",
    )
    _assert_loaded_authorities(
        "peer-review",
        "artifact_discovery",
        "references/publication/publication-review-round-artifacts.md",
    )
    _assert_machine_fragments(
        write_paper_workflow,
        "{GPD_INSTALL_DIR}/references/publication/publication-bootstrap-preflight.md",
        PUBLICATION_RESPONSE_WRITER_HANDOFF_INCLUDE,
        PUBLICATION_ROUND_ARTIFACTS_INCLUDE,
        context="write-paper workflow publication authorities",
    )
    for content in (respond, arxiv):
        _assert_forbidden_fragments(
            content,
            PUBLICATION_SHARED_PREFLIGHT_INCLUDE,
            PUBLICATION_BOOTSTRAP_PREFLIGHT_INCLUDE,
            PUBLICATION_RESPONSE_WRITER_HANDOFF_INCLUDE,
            PUBLICATION_ROUND_ARTIFACTS_INCLUDE,
            PUBLICATION_REVIEW_RELIABILITY_INCLUDE,
            "@{GPD_INSTALL_DIR}/references/shared/canonical-schema-discipline.md",
            "templates/paper/review-ledger-schema.md",
            "templates/paper/referee-decision-schema.md",
            context="thin publication command wrapper",
        )
    _assert_machine_fragments(
        respond_workflow,
        PUBLICATION_BOOTSTRAP_PREFLIGHT_INCLUDE,
        PUBLICATION_RESPONSE_WRITER_HANDOFF_INCLUDE,
        PUBLICATION_REVIEW_RELIABILITY_INLINE,
        context="respond workflow publication authorities",
    )
    _assert_forbidden_fragments(
        respond_workflow,
        PUBLICATION_ROUND_ARTIFACTS_INCLUDE,
        context="respond workflow publication authorities",
    )
    _assert_machine_fragments(
        arxiv_workflow,
        PUBLICATION_BOOTSTRAP_PREFLIGHT_INCLUDE,
        PUBLICATION_ROUND_ARTIFACTS_INCLUDE,
        context="arxiv workflow publication authorities",
    )
    _assert_forbidden_fragments(
        arxiv_workflow,
        PUBLICATION_RESPONSE_WRITER_HANDOFF_INCLUDE,
        PUBLICATION_REVIEW_RELIABILITY_INCLUDE,
        context="arxiv workflow publication authorities",
    )
    _assert_semantic_fragments(
        arxiv_workflow,
        "staged",
        "peer-review-reliability.md",
        "reference",
        context="arxiv staged reliability reference",
    )
    _assert_loaded_authorities(
        "arxiv-submission",
        "manuscript_preflight",
        "templates/paper/publication-manuscript-root-preflight.md",
    )
    _assert_loaded_authorities(
        "respond-to-referees",
        "bootstrap",
        "references/publication/publication-bootstrap-preflight.md",
    )
    _assert_semantic_fragments(
        shared_preflight,
        "strict preflight reads",
        "resolved manuscript directory",
        "ARTIFACT-MANIFEST.json",
        "BIBLIOGRAPHY-AUDIT.json",
        "reproducibility-manifest.json",
        "PAPER-CONFIG.json",
        "wildcard discovery",
        "first-match filename scans",
        context="publication manuscript preflight",
    )

    _assert_semantic_fragments(
        shared_preflight,
        "canonical manuscript family",
        "`paper/`",
        "`manuscript/`",
        "`draft/`",
        "explicit-artifact mode",
        "`.pdf`",
        "does not widen",
        "resolved `.tex` / `.md` entrypoint path",
        context="publication manuscript preflight",
    )

    _assert_semantic_fragments(
        shared_preflight,
        "nearby `ARTIFACT-MANIFEST.json`",
        "additive when present",
        "same explicit manuscript directory",
        "copied from another manuscript root",
        "gpd paper-build",
        "regenerates",
        context="publication manuscript preflight",
    )
    _assert_machine_fragments(
        shared_preflight,
        "bibliography_audit_clean",
        "reproducibility_ready",
        context="publication preflight review contract fields",
    )


def test_publication_command_contexts_surface_schema_docs_before_generation() -> None:
    write_paper = (COMMANDS_DIR / "write-paper.md").read_text(encoding="utf-8")
    peer_review = (COMMANDS_DIR / "peer-review.md").read_text(encoding="utf-8")
    arxiv = (COMMANDS_DIR / "arxiv-submission.md").read_text(encoding="utf-8")
    respond = (COMMANDS_DIR / "respond-to-referees.md").read_text(encoding="utf-8")
    write_paper_workflow = _workflow_authority_text("write-paper")
    peer_review_workflow = _workflow_authority_text("peer-review")
    peer_review_index = (WORKFLOWS_DIR / "peer-review.md").read_text(encoding="utf-8")
    respond_workflow = _workflow_authority_text("respond-to-referees")
    arxiv_workflow = _workflow_authority_text("arxiv-submission")
    peer_review_workflow_expanded = _expanded_workflow_authority_text("peer-review")
    shared_preflight_include = "@{GPD_INSTALL_DIR}/templates/paper/publication-manuscript-root-preflight.md"
    bootstrap_preflight_include = "@{GPD_INSTALL_DIR}/references/publication/publication-bootstrap-preflight.md"
    response_handoff_include = "{GPD_INSTALL_DIR}/references/publication/publication-response-writer-handoff.md"
    round_artifacts_include = "{GPD_INSTALL_DIR}/references/publication/publication-review-round-artifacts.md"

    for content in (write_paper, peer_review, arxiv, respond):
        _assert_forbidden_fragments(
            content,
            "templates/paper/paper-config-schema.md",
            "templates/paper/artifact-manifest-schema.md",
            "templates/paper/bibliography-audit-schema.md",
            "templates/paper/reproducibility-manifest.md",
            PUBLICATION_REVIEW_RELIABILITY_INCLUDE,
            shared_preflight_include,
            bootstrap_preflight_include,
            response_handoff_include,
            round_artifacts_include,
            context="thin publication command schema staging",
        )
    for content in (write_paper, peer_review):
        _assert_forbidden_fragments(
            content,
            "templates/paper/review-ledger-schema.md",
            "templates/paper/referee-decision-schema.md",
            "references/publication/peer-review-panel.md",
            "references/publication/peer-review-reliability.md",
            context="thin publication command review schema staging",
        )
    _assert_machine_fragments(
        write_paper_workflow,
        "templates/paper/paper-config-schema.md",
        "templates/paper/artifact-manifest-schema.md",
        "templates/paper/bibliography-audit-schema.md",
        "templates/paper/reproducibility-manifest.md",
        "{GPD_INSTALL_DIR}/references/publication/publication-bootstrap-preflight.md",
        response_handoff_include,
        round_artifacts_include,
        context="write-paper workflow staged schema docs",
    )
    _assert_loaded_authorities(
        "write-paper",
        "paper_bootstrap",
        "templates/paper/publication-manuscript-root-preflight.md",
    )
    _assert_forbidden_fragments(
        peer_review_index,
        PUBLICATION_SHARED_PREFLIGHT_INCLUDE,
        bootstrap_preflight_include,
        response_handoff_include,
        context="peer-review workflow staged schema docs",
    )
    _assert_machine_fragments(
        peer_review_workflow,
        "{GPD_INSTALL_DIR}/templates/paper/publication-manuscript-root-preflight.md",
        context="peer-review workflow staged schema docs",
    )
    _assert_loaded_authorities(
        "peer-review",
        "final_adjudication",
        "templates/paper/review-ledger-schema.md",
    )
    _assert_loaded_authorities(
        "peer-review",
        "final_adjudication",
        "templates/paper/referee-decision-schema.md",
    )
    _assert_loaded_authorities(
        "peer-review",
        "artifact_discovery",
        "references/publication/publication-review-round-artifacts.md",
    )
    _assert_machine_fragments(
        peer_review_workflow_expanded,
        "bibliography_audit_clean",
        "reproducibility_ready",
        context="peer-review expanded review contract fields",
    )
    _assert_machine_fragments(
        respond_workflow,
        "templates/paper/author-response.md",
        "templates/paper/referee-response.md",
        bootstrap_preflight_include,
        response_handoff_include,
        PUBLICATION_REVIEW_RELIABILITY_INLINE,
        context="respond workflow staged schema docs",
    )
    _assert_loaded_authorities(
        "respond-to-referees",
        "bootstrap",
        "references/publication/publication-bootstrap-preflight.md",
    )
    _assert_machine_fragments(
        arxiv_workflow,
        bootstrap_preflight_include,
        round_artifacts_include,
        context="arxiv workflow staged schema docs",
    )
    _assert_forbidden_fragments(
        arxiv_workflow,
        response_handoff_include,
        PUBLICATION_REVIEW_RELIABILITY_INCLUDE,
        context="arxiv workflow staged schema docs",
    )
    _assert_semantic_fragments(
        arxiv_workflow,
        "staged",
        "peer-review-reliability.md",
        "reference",
        context="arxiv workflow staged reliability note",
    )
    _assert_loaded_authorities(
        "arxiv-submission",
        "manuscript_preflight",
        "templates/paper/publication-manuscript-root-preflight.md",
    )
    _assert_loaded_authorities(
        "write-paper",
        "figure_and_section_authoring",
        "references/shared/canonical-schema-discipline.md",
    )
    for content in (respond, arxiv):
        _assert_forbidden_fragments(
            content,
            shared_preflight_include,
            bootstrap_preflight_include,
            response_handoff_include,
            round_artifacts_include,
            PUBLICATION_REVIEW_RELIABILITY_INCLUDE,
            context="publication command wrapper staged include absence",
        )


def test_staged_publication_and_quick_workflow_prompts_match_executable_init_paths() -> None:
    write_paper_workflow = _workflow_authority_text("write-paper")
    peer_review_workflow = _workflow_authority_text("peer-review")
    quick_workflow = _workflow_authority_text("quick")
    arxiv_workflow = _workflow_authority_text("arxiv-submission")
    arxiv_staging = registry.get_command("arxiv-submission").staged_loading

    _assert_workflow_calls_staged_init_for_manifest_stages("write-paper", write_paper_workflow)
    _assert_workflow_calls_staged_init_for_manifest_stages("peer-review", peer_review_workflow)
    _assert_workflow_calls_staged_init_for_manifest_stages("quick", quick_workflow)
    execute_phase_workflow = _workflow_authority_text("execute-phase")
    _assert_workflow_calls_staged_init_for_manifest_stages("execute-phase", execute_phase_workflow)
    _assert_workflow_calls_staged_init_for_manifest_stages("arxiv-submission", arxiv_workflow)

    assert arxiv_staging is not None
    assert arxiv_staging.stage_ids() == (
        "bootstrap",
        "manuscript_preflight",
        "review_gate",
        "package",
        "finalize",
    )
    assert "executable through `gpd --raw init arxiv-submission --stage <stage_id>`" in arxiv_workflow
    assert "metadata-only for the prompt path today" not in arxiv_workflow
    assert "no public staged init CLI command" not in arxiv_workflow
    assert "gpd --raw init arxiv-submission --stage bootstrap" in arxiv_workflow
    assert "gpd --raw validate command-context arxiv-submission" in arxiv_workflow
    assert "gpd --raw validate review-preflight arxiv-submission" in arxiv_workflow


def test_research_verification_body_scaffold_keeps_body_only_subject_labels_distinct() -> None:
    research_verification = (TEMPLATES_DIR / "research-verification.md").read_text(encoding="utf-8")

    assert "Allowed body enum values:" in research_verification
    assert "check_subject_kind: claim" in research_verification
    assert "check_subject_kind: claim" in research_verification
    assert "suggested_subject_kind" in research_verification
    assert 'gap_subject_kind: "claim"' in research_verification
    assert "Use `check_subject_kind` for body-only verification checkpoints" in research_verification
    assert "Use `gap_subject_kind` for the body scaffold" in research_verification
    assert (
        "Keep `check_subject_kind` and `gap_subject_kind` aligned with the canonical frontmatter-safe subject vocabulary"
        in research_verification
    )
    assert "use `forbidden_proxy_id` for explicit proxy-rejection gaps" in research_verification
    assert (
        "\nsubject_kind: [claim | deliverable | acceptance_test | reference | forbidden_proxy | suggested_contract_check]"
        not in research_verification
    )
    assert (
        "# Allowed check_subject_kind values: claim|deliverable|acceptance_test|reference" not in research_verification
    )
    assert "check_subject_kind: [claim | deliverable | acceptance_test | reference]" not in research_verification
    assert (
        "check_subject_kind: [claim | deliverable | acceptance_test | reference | forbidden_proxy | suggested_contract_check]"
        not in research_verification
    )
    assert 'gap_subject_kind: "claim | deliverable | acceptance_test | reference"' not in research_verification
    assert (
        'gap_subject_kind: "claim | deliverable | acceptance_test | reference | forbidden_proxy | suggested_contract_check"'
        not in research_verification
    )


def test_verify_work_workflow_uses_body_only_subject_kind_fields() -> None:
    verify_work = _workflow_authority_text("verify-work")

    _assert_machine_fragments(
        verify_work,
        "Load the staged researcher-session scaffold and canonical schema pack at this stage.",
        "Keep body-only session-overlay fields aligned with the staged researcher-session scaffold.",
        "Write to `${PHASE_DIR_ABS}/${phase_number}-VERIFICATION.md`",
        'gpd validate verification-contract "${PHASE_DIR_ABS}/${phase_number}-VERIFICATION.md"',
        'gpd commit "verify(${phase_number}): complete research validation - {passed} passed, {issues} issues" --files "${PHASE_DIR_ABS}/${phase_number}-VERIFICATION.md"',
        "Use `phase_dir_abs` for shell/file IO",
        "Read all PLAN.md files in `${PHASE_DIR_ABS}/` using the file_read tool.",
        context="verify-work body-only subject and path wiring",
    )
    _assert_semantic_fragments(
        verify_work,
        "Use `forbidden_proxy_id`",
        "explicit proxy-rejection checks",
        "instead of inventing extra body subject kinds",
        context="verify-work forbidden proxy subject boundary",
    )
    _assert_forbidden_fragments(
        verify_work,
        "check_subject_kind: `claim|deliverable|acceptance_test|reference`",
        "Allowed body enum values:",
        "check_subject_kind: claim",
        "`check_subject_kind`: claim|deliverable|acceptance_test|reference",
        'gap_subject_kind: "claim"',
        "# Allowed check_subject_kind values: claim|deliverable|acceptance_test|reference",
        "check_subject_kind: [claim | deliverable | acceptance_test | reference]",
        "{phase}",
        "GPD/phases/{phase_dir}",
        "${phase_dir}/",
        "{phase_dir}/",
        "\nsubject_kind: [claim | deliverable | acceptance_test | reference | forbidden_proxy | suggested_contract_check]",
        "check_subject_kind: `claim | deliverable | acceptance_test | reference | forbidden_proxy | suggested_contract_check`",
        "check_subject_kind: [claim | deliverable | acceptance_test | reference | forbidden_proxy | suggested_contract_check]",
        context="verify-work removed body subject aliases",
    )


def test_verify_work_active_sessions_use_canonical_verification_path_and_keep_status_separate() -> None:
    verify_work = _workflow_authority_text("verify-work")

    assert 'gpd frontmatter get "$file" --field session_status' not in verify_work
    assert "Read `active_verification_sessions` from `SESSION_ROUTER_INIT`." in verify_work
    assert "Active sessions are payload entries with `session_status` of `validating` or `diagnosed`." in verify_work
    assert "Route on each entry's canonical `status` / `routing_status`" in verify_work
    assert "never let `session_status` overwrite `status`" in verify_work
    assert "`session_status` if present, otherwise `status`" not in verify_work


def test_skill_surface_exposes_contract_references_for_paper_and_review_workflows() -> None:
    from gpd.mcp.servers.skills_server import get_skill

    write_paper = get_skill("gpd-write-paper")
    peer_review = get_skill("gpd-peer-review")
    arxiv_submission = get_skill("gpd-arxiv-submission")
    respond_to_referees = get_skill("gpd-respond-to-referees")
    write_paper_schema_documents = {Path(entry["path"]).name: entry for entry in write_paper["schema_documents"]}
    peer_review_contract_documents = {Path(entry["path"]).name: entry for entry in peer_review["contract_documents"]}
    arxiv_contract_documents = {Path(entry["path"]).name: entry for entry in arxiv_submission["contract_documents"]}
    respond_contract_documents = {
        Path(entry["path"]).name: entry for entry in respond_to_referees["contract_documents"]
    }
    write_paper_stage_authorities = {
        authority
        for stage in write_paper.get("staged_loading", {}).get("stages", [])
        for authority in stage.get("loaded_authorities", [])
    }
    peer_review_stage_authorities = {
        authority
        for stage in peer_review.get("staged_loading", {}).get("stages", [])
        for authority in (
            *stage.get("loaded_authorities", []),
            *(
                authority
                for conditional in stage.get("conditional_authorities", [])
                for authority in conditional.get("authorities", [])
            ),
        )
    }

    assert "error" not in write_paper
    assert "error" not in peer_review
    assert "error" not in arxiv_submission
    assert "error" not in respond_to_referees
    assert any(path.endswith("paper-config-schema.md") for path in write_paper_stage_authorities)
    assert any(path.endswith("artifact-manifest-schema.md") for path in write_paper_stage_authorities)
    assert any(path.endswith("bibliography-audit-schema.md") for path in write_paper_stage_authorities)
    assert any(path.endswith("publication-review-round-artifacts.md") for path in write_paper_stage_authorities)
    assert any(path.endswith("review-ledger-schema.md") for path in peer_review_stage_authorities)
    assert any(path.endswith("referee-decision-schema.md") for path in peer_review_stage_authorities)
    assert any(path.endswith("publication-review-round-artifacts.md") for path in peer_review_stage_authorities)
    assert any(path.endswith("peer-review-panel.md") for path in peer_review_stage_authorities)
    assert any(path.endswith("peer-review-reliability.md") for path in peer_review_stage_authorities)
    arxiv_stage_authorities = {
        authority
        for stage in arxiv_submission.get("staged_loading", {}).get("stages", [])
        for authority in stage.get("loaded_authorities", [])
    }
    assert any(path.endswith("publication-bootstrap-preflight.md") for path in arxiv_stage_authorities)
    assert any(path.endswith("publication-review-round-artifacts.md") for path in arxiv_stage_authorities)
    assert any(path.endswith("reproducibility-manifest.md") for path in write_paper_stage_authorities)
    assert not any(path.endswith("peer-review-panel.md") for path in write_paper_stage_authorities)
    assert write_paper_schema_documents == {}
    assert peer_review_contract_documents == {}
    assert arxiv_contract_documents == {}
    assert respond_contract_documents == {}
    assert "Treat `content` as the wrapper/context surface." in write_paper["loading_hint"]
    assert "See `referenced_files` for external markdown dependencies" in write_paper["loading_hint"]
    assert "Load `schema_documents` and `contract_documents` too when present" not in write_paper["loading_hint"]
    assert "transitive_schema_documents" not in write_paper["loading_hint"]
    assert "transitive_contract_documents" not in write_paper["loading_hint"]


def test_peer_review_workflow_and_generated_skill_surface_keep_lifecycle_cleanup_contract() -> None:
    from gpd.mcp.servers.skills_server import get_skill

    peer_review_workflow = _workflow_authority_text("peer-review")
    peer_review_skill_content = get_skill("gpd-peer-review")["content"]

    _assert_semantic_fragments(
        peer_review_workflow,
        "stage-recovery-gate.md",
        "spawned",
        "reviewer/proof-auditor/referee lifecycle",
        "stale-output rejection",
        "declared carry-forward inputs",
        "Apply the `peer_review_stage6_referee` tuple",
        context="peer-review lifecycle cleanup contract",
    )
    _assert_semantic_fragments(
        peer_review_skill_content,
        "staged_loading",
        "artifact_discovery",
        "final_adjudication",
        context="generated peer-review lifecycle cleanup contract",
    )


def test_peer_review_spawned_stage_prompts_keep_stage_identity_callsite_owned() -> None:
    peer_review = _workflow_authority_text("peer-review")

    assert '<step name="child_return_contract">' in peer_review or "<child_return_contract>" in peer_review
    _assert_semantic_fragments(
        peer_review,
        "Stage identity",
        "callsite-owned",
        "tuple `role`",
        "Fresh `gpd_return.files_written` evidence",
        "matching tuple gate",
        context="peer-review stage identity contract",
    )
    assert "peer_review_stage6_referee" in peer_review

    expected_stage_contracts = (
        "peer_review_stage1_reader",
        "stage_id=reader and stage_kind=reader",
        "peer_review_stage2_literature",
        "stage_id=literature and stage_kind=literature",
        "peer_review_stage3_math",
        "stage_id=math and stage_kind=math",
        "peer_review_proof_redteam",
        "${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md",
        "peer_review_stage4_physics",
        "stage_id=physics and stage_kind=physics",
        "peer_review_stage5_significance",
        "stage_id=interestingness and stage_kind=interestingness",
        "peer_review_stage6_referee",
        "gpd_return.files_written stays within Stage 6 write_allowlist",
    )
    _assert_contains_fragments(peer_review, *expected_stage_contracts)


def test_bibliographer_skill_surface_stays_direct_only() -> None:
    from gpd.mcp.servers.skills_server import get_skill

    bibliographer = get_skill("gpd-bibliographer")
    direct_reference_suffixes = {
        "references/shared/shared-protocols.md",
        "references/physics-subfields.md",
        "references/orchestration/agent-infrastructure.md",
        "templates/notation-glossary.md",
        "references/publication/bibtex-standards.md",
        "references/publication/publication-pipeline-modes.md",
        "references/publication/bibliography-advanced-search.md",
    }

    assert "error" not in bibliographer
    assert bibliographer["reference_count"] == len(direct_reference_suffixes)
    assert {entry["path"].split("}/", 1)[1] for entry in bibliographer["referenced_files"]} == direct_reference_suffixes


def test_review_and_execution_prompts_expand_required_schema_sources() -> None:
    src_root = REPO_ROOT / "src/gpd/specs"

    review_reader_raw = (AGENTS_DIR / "gpd-review-reader.md").read_text(encoding="utf-8")
    referee_raw = (AGENTS_DIR / "gpd-referee.md").read_text(encoding="utf-8")
    review_reader = expand_at_includes(
        (AGENTS_DIR / "gpd-review-reader.md").read_text(encoding="utf-8"),
        src_root,
        "/runtime/",
    )
    review_literature = expand_at_includes(
        (AGENTS_DIR / "gpd-review-literature.md").read_text(encoding="utf-8"),
        src_root,
        "/runtime/",
    )
    referee = expand_at_includes(
        (AGENTS_DIR / "gpd-referee.md").read_text(encoding="utf-8"),
        src_root,
        "/runtime/",
    )

    assert "{GPD_INSTALL_DIR}/references/publication/peer-review-panel.md" in review_reader_raw
    assert "{GPD_INSTALL_DIR}/references/publication/peer-review-panel.md" in referee_raw
    assert "{GPD_INSTALL_DIR}/templates/paper/review-ledger-schema.md" in referee_raw
    assert "{GPD_INSTALL_DIR}/templates/paper/referee-decision-schema.md" in referee_raw
    assert "Peer Review Panel Protocol" not in review_reader
    assert "{GPD_INSTALL_DIR}/references/publication/peer-review-panel.md" in review_literature
    assert "Peer Review Panel Protocol" not in review_literature
    assert "Review Ledger Schema" not in referee
    assert "Referee Decision Schema" not in referee


def test_verification_and_agent_reference_prompts_expand_or_stage_required_reference_bodies() -> None:
    verify_work = _expand_prompt_surface(WORKFLOWS_DIR / "verify-work.md")
    verify_phase = _expand_prompt_surface(WORKFLOWS_DIR / "verify-phase.md")
    phase_researcher = _expand_prompt_surface(AGENTS_DIR / "gpd-phase-researcher.md")
    planner = _expand_prompt_surface(AGENTS_DIR / "gpd-planner.md")
    verify_work_staging = registry.get_command("verify-work").staged_loading
    assert verify_work_staging is not None
    inventory_build = next(stage for stage in verify_work_staging.stages if stage.id == "inventory_build")
    interactive_validation = next(stage for stage in verify_work_staging.stages if stage.id == "interactive_validation")

    assert "Verification Independence" not in verify_work
    assert "# Contract Results Schema" not in verify_work
    assert "references/verification/meta/verification-independence.md" in inventory_build.loaded_authorities
    interactive_conditionals = tuple(
        authority
        for conditional in interactive_validation.conditional_authorities
        for authority in conditional.authorities
    )
    assert {"templates/contract-results-schema.md"} <= set(interactive_conditionals)
    assert "Verification Independence" not in verify_phase
    assert "# Contract Results Schema" not in verify_phase
    assert "Do not raw-include the verification reference library at workflow load." in verify_phase
    assert "{GPD_INSTALL_DIR}/references/verification/meta/verification-independence.md" in verify_phase
    assert "{GPD_INSTALL_DIR}/templates/contract-results-schema.md" in verify_phase
    assert "@{GPD_INSTALL_DIR}/references/verification/core/verification-core.md" not in verify_phase
    assert "@{GPD_INSTALL_DIR}/templates/contract-results-schema.md" not in verify_phase
    assert "- `@{GPD_INSTALL_DIR}/references/shared/shared-protocols.md`" in phase_researcher
    assert "# Shared Research Philosophy and Protocols" not in phase_researcher
    assert "# Agent Infrastructure Protocols" not in phase_researcher
    assert "Shared Protocols" in planner
    assert "{GPD_INSTALL_DIR}/references/orchestration/agent-infrastructure.md" in planner
    assert "@ include not resolved:" not in verify_work.lower()
    assert "@ include not resolved:" not in verify_phase.lower()
    assert "@ include not resolved:" not in phase_researcher.lower()
    assert "@ include not resolved:" not in planner.lower()
    assert (
        "The standalone `gpd:verify-work` workflow reuses the same verification criteria through `verify-work.md`; this file itself is executed by the execute-phase orchestrator."
        in verify_phase
    )
    assert 'VERIFICATION_FILE="${phase_dir}/${phase_number}-VERIFICATION.md"' in verify_phase
    assert "Return status (`passed` | `gaps_found` | `expert_needed` | `human_needed`)" in verify_phase


def test_verification_independence_reference_examples_keep_required_contract_fields_visible() -> None:
    reference = (REFERENCES_DIR / "verification" / "meta" / "verification-independence.md").read_text(encoding="utf-8")

    _assert_prompt_contracts(
        reference,
        fragment_count(
            "verification independence includes two contract examples",
            "contract:\n  schema_version: 1",
            expected_count=2,
            context="verification independence examples",
        ),
    )
    assert "context_intake:" in reference
    assert "forbidden_proxies:" in reference
    assert "uncertainty_markers:" in reference


def test_planner_and_summary_prompt_surfaces_expand_contract_schema_bodies() -> None:
    phase_prompt = _expand_prompt_surface(TEMPLATES_DIR / "phase-prompt.md")
    planner_prompt = _expand_prompt_surface(TEMPLATES_DIR / "planner-subagent-prompt.md")
    summary_template = _expand_prompt_surface(TEMPLATES_DIR / "summary.md")

    _assert_machine_fragments(
        phase_prompt,
        "# PLAN Contract Schema",
        "schema_version: 1",
        "in_scope:",
        "context_intake:",
        "Quick contract rules:",
        context="expanded phase prompt plan contract schema",
    )
    _assert_prompt_contracts(
        phase_prompt,
        fragment_count(
            "expanded phase prompt has one quick contract rules block",
            "Quick contract rules:",
            expected_count=1,
            context="expanded phase prompt contract schema",
        ),
    )
    for token in (
        "tool_requirements",
        "researcher_setup",
        "scope.in_scope",
        "claim_kind",
        "observables[].kind",
        "deliverables[].kind",
        "acceptance_tests[].kind",
        "references[].kind",
        "references[].role",
        "links[].relation",
        "must_surface",
        "required_actions[]",
        "applies_to[]",
        "carry_forward_to[]",
        "uncertainty_markers",
    ):
        assert token in phase_prompt
    _assert_machine_fragments(
        phase_prompt,
        'must_include_prior_outputs: ["GPD/phases/00-baseline/00-01-SUMMARY.md"]',
        'user_asserted_anchors: ["GPD/phases/00-baseline/00-01-SUMMARY.md#vacuum-polarization-normalization"]',
        "claims:",
        "observables: [obs-main]",
        "### `forbidden_proxies[]`",
        "### `links[]`",
        context="expanded phase prompt contract examples",
    )
    _assert_prompt_contracts(
        planner_prompt,
        fragment_count(
            "planner prompt standard planning template heading count",
            "## Standard Planning Template",
            expected_count=1,
            context="expanded planner prompt schema includes",
        ),
        fragment_count(
            "planner prompt revision template heading count",
            "## Revision Template",
            expected_count=1,
            context="expanded planner prompt schema includes",
        ),
        fragment_count(
            "planner prompt plan contract schema include count",
            "{GPD_INSTALL_DIR}/templates/plan-contract-schema.md",
            expected_count=1,
            context="expanded planner prompt schema includes",
        ),
    )
    for token in (
        "project_contract_gate.authoritative",
        "project_contract_load_info.status",
        "project_contract_validation.valid",
        "project_contract",
        "effective_reference_intake",
        "active_reference_context",
        "approach_policy",
        "scope.in_scope",
        "contract.context_intake",
        "claim_kind",
    ):
        assert token in planner_prompt
    _assert_machine_fragments(
        phase_prompt,
        "scope.unresolved_questions",
        context="expanded phase prompt unresolved question field",
    )
    _assert_semantic_concept(
        phase_prompt,
        "expanded phase prompt stable id rules",
        required=(
            "Every claim must declare a stable `id`.",
            "Do not reuse the same ID across `observables[]`, `claims[]`, `deliverables[]`, `acceptance_tests[]`, "
            "`references[]`, `forbidden_proxies[]`, or `links[]`",
        ),
        context="expanded phase prompt stable id rules",
    )
    _assert_machine_fragments(
        summary_template,
        "contract-results-schema.md",
        context="expanded summary template schema include",
    )
    _assert_semantic_concept(
        summary_template,
        "summary template defers contract rules to schema include",
        required="single detailed rule source",
        context="expanded summary template schema include",
    )


def test_sync_state_defers_state_schema_while_write_paper_expands_required_schema_bodies() -> None:
    sync_state = _expand_prompt_surface(COMMANDS_DIR / "sync-state.md")
    sync_state_workflow = _expanded_workflow_authority_text("sync-state")
    write_paper = _expanded_workflow_authority_text("write-paper")

    assert "state-json-schema.md" in sync_state
    assert "# state.json Schema" not in sync_state
    assert "Authoritative vs Derived" not in sync_state
    assert "`convention_lock`" not in sync_state
    assert "`convention_lock`" in sync_state_workflow
    assert "templates/paper/reproducibility-manifest.md" in write_paper
    assert "Reproducibility Manifest Template" not in write_paper
    assert "bibliographer search breadth" in write_paper
    assert "paper-writer style by mode" in write_paper
    _assert_semantic_fragments(
        write_paper,
        "bounded external-authoring lane",
        "accept one explicit",
        "intake manifest only",
        context="write-paper external authoring intake",
    )
    assert "GPD/publication/{subject_slug}/intake/" in write_paper
    assert '"execution_steps"' not in write_paper
    assert "random_seeds[].computation" not in write_paper
    assert "resource_requirements[].step" not in write_paper


def test_non_adapter_sources_do_not_hardcode_runtime_names() -> None:
    runtime_terms = {descriptor.runtime_name for descriptor in iter_runtime_descriptors()}
    runtime_terms.update(
        alias for descriptor in iter_runtime_descriptors() for alias in descriptor.selection_aliases if alias.strip()
    )
    runtime_name_re = re.compile(
        rf"\b(?:{'|'.join(re.escape(term) for term in sorted(runtime_terms, key=len, reverse=True))})\b",
        re.IGNORECASE,
    )
    offenders: list[str] = []

    for path in sorted((REPO_ROOT / "src" / "gpd").rglob("*")):
        if not path.is_file() or path.suffix not in {".py", ".md"}:
            continue
        if path.is_relative_to(REPO_ROOT / "src" / "gpd" / "adapters"):
            continue
        content = path.read_text(encoding="utf-8")
        if runtime_name_re.search(content):
            offenders.append(str(path.relative_to(REPO_ROOT)))

    assert offenders == []


def test_state_json_schema_surfaces_stdin_contract_persistence_and_model_normalization_rules() -> None:
    state_schema = _expand_prompt_surface(TEMPLATES_DIR / "state-json-schema.md")

    _assert_machine_fragments(
        state_schema,
        "printf '%s\\n' \"$PROJECT_CONTRACT_JSON\" | gpd --raw validate project-contract -",
        "printf '%s\\n' \"$PROJECT_CONTRACT_JSON\" | gpd state set-project-contract -",
        "temporary file",
        "`schema_version` must be the integer `1`.",
        '"required_actions": ["read", "compare", "cite", "avoid"]',
        "Blank-after-trim values are invalid",
        context="state schema project contract stdin persistence",
    )
    _assert_semantic_fragments(
        state_schema,
        "grounding fields",
        "concrete enough to re-find later",
        "missing `must_surface: true` reference",
        "warning",
        context="state schema project contract grounding",
    )


def test_phase_prompt_surfaces_validation_critical_plan_contract_rules() -> None:
    phase_prompt = (TEMPLATES_DIR / "phase-prompt.md").read_text(encoding="utf-8")

    assert "Quick contract rules:" in phase_prompt
    _assert_prompt_contracts(
        phase_prompt,
        fragment_count(
            "phase prompt has one quick contract rules block",
            "Quick contract rules:",
            expected_count=1,
            context="phase-prompt contract rules",
        ),
    )
    for token in (
        "tool_requirements",
        "researcher_setup",
        "type: execute",
        "gap_closure: true",
        "scope.in_scope",
        "claim_kind",
        "observables[].kind",
        "deliverables[].kind",
        "acceptance_tests[].kind",
        "references[].kind",
        "references[].role",
        "links[].relation",
        "must_surface",
        "required_actions[]",
        "applies_to[]",
        "carry_forward_to[]",
        "uncertainty_markers",
    ):
        assert token in phase_prompt


def test_review_ledger_schema_surfaces_enforced_id_formats() -> None:
    review_ledger_schema = (TEMPLATES_DIR / "paper" / "review-ledger-schema.md").read_text(encoding="utf-8")

    assert "`issue_id` must match `REF-[A-Za-z0-9][A-Za-z0-9_-]*`" in review_ledger_schema
    assert "Every `claim_ids[]` entry must match `CLM-[A-Za-z0-9][A-Za-z0-9_-]*`." in review_ledger_schema


def test_contract_models_match_prompted_schema_contracts() -> None:
    acceptance_test_fields = ResearchContract.model_fields["acceptance_tests"].annotation.__args__[0].model_fields
    reference_fields = ResearchContract.model_fields["references"].annotation.__args__[0].model_fields

    assert "automation" in acceptance_test_fields
    assert "aliases" in reference_fields
    assert "carry_forward_to" in reference_fields
    assert ResearchContract.model_fields["schema_version"].annotation == Literal[1]
    assert VerificationEvidence.model_config.get("extra") == "forbid"


def test_execution_surfaces_use_bounded_review_cadence_and_first_result_gates() -> None:
    execute_phase = _workflow_authority_text("execute-phase")
    execute_plan = (WORKFLOWS_DIR / "execute-plan.md").read_text(encoding="utf-8")
    resume_work = expand_at_includes(
        _workflow_authority_text("resume-work"),
        REPO_ROOT / "src/gpd",
        "/runtime/",
    )
    continuation = (TEMPLATES_DIR / "continuation-prompt.md").read_text(encoding="utf-8")
    checkpoints = (REFERENCES_DIR / "orchestration" / "checkpoints.md").read_text(encoding="utf-8")
    checkpoint_flow = (REFERENCES_DIR / "execution" / "execute-plan-checkpoints.md").read_text(encoding="utf-8")
    executor_agent = (AGENTS_DIR / "gpd-executor.md").read_text(encoding="utf-8")

    _assert_machine_fragments(
        execute_phase,
        "review_cadence",
        "FIRST_RESULT_GATE_REQUIRED",
        "probe_then_fanout",
        "bounded_execution",
        "pre_execution_specialists",
        'gpd --raw init execute-phase "${PHASE_ARG}" --stage pre_execution_specialists',
        context="execute-phase bounded review cadence",
    )
    _assert_prompt_contracts(
        execute_plan,
        semantic_anchor(
            "execute-plan honors dense-forced first-result gate",
            ("do not recompute", "treat `FIRST_RESULT_GATE_REQUIRED=true` as forced"),
            mode="any",
            context="execute-plan first-result gate",
        ),
    )
    _assert_semantic_fragments(
        execute_plan,
        "autonomy",
        "does NOT disable first-result sanity checks",
        "Required first-result sanity gate",
        "phase ordering",
        "prior momentum",
        "never waive",
        "required bounded stop",
        "`MAX_UNATTENDED_MINUTES_PER_PLAN`",
        context="execute-plan bounded review cadence",
    )
    _assert_semantic_fragments(
        execute_phase,
        "Do NOT narrow",
        "wave advanced",
        "one proxy passed",
        context="execute-phase bounded review scope",
    )
    _assert_forbidden_fragments(
        execute_phase,
        '# task(subagent_type="gpd-notation-coordinator"',
        '# task(subagent_type="gpd-experiment-designer"',
        "| `completed`    | -> update_roadmap (interactive verify-work equivalent)",
        "| `diagnosed`    | Gaps were debugged; review fixes, then -> update_roadmap",
        "| `validating`   | Verification in progress; wait or re-run verify-phase",
        context="execute-phase bounded review stale branches",
    )
    _assert_semantic_fragments(
        resume_work,
        "What decisive evidence is still owed before downstream work is trustworthy?",
        context="resume-work continuation vocabulary",
    )
    _assert_resume_canonical_note(resume_work)
    _assert_forbidden_fragments(
        resume_work,
        "public top-level resume vocabulary",
        "`resume_surface`",
        "gpd init resume",
        context="resume-work stale continuation vocabulary",
    )
    _assert_machine_fragments(executor_agent, "Pattern D: Auto-bounded", context="executor bounded pattern")
    _assert_machine_fragments(continuation, "execution_segment", context="continuation prompt bounded segment")
    _assert_machine_fragments(checkpoints, "Required Checkpoint Payload", context="checkpoint payload prompt")
    _assert_machine_fragments(checkpoint_flow, "rollback primitive", context="execute-plan checkpoint flow")
    _assert_semantic_fragments(
        execute_phase,
        "`session_status: validating|completed|diagnosed`",
        "conversational progress only",
        context="execute-phase verification status boundary",
    )
    _assert_machine_fragments(
        execute_phase,
        "If the prior report carries `session_status: diagnosed`",
        context="execute-phase session status boundary",
    )


def test_show_phase_workflow_distinguishes_verification_status_from_session_status() -> None:
    show_phase = (WORKFLOWS_DIR / "show-phase.md").read_text(encoding="utf-8")

    assert "`*-VERIFICATION.md`" in show_phase
    assert (
        "read frontmatter to extract canonical verification `status`, plus `session_status` when present" in show_phase
    )
    assert "Automated verification uses `passed`/`gaps_found`/`expert_needed`/`human_needed`" in show_phase
    assert "researcher-session progress uses `session_status: validating|completed|diagnosed`" in show_phase
    assert "Automated verification uses `passed`/`gaps_found`/`human_needed`" not in show_phase
    assert "interactive validation uses `validating`/`completed`/`diagnosed`" not in show_phase


def test_execute_phase_and_related_agents_surface_only_plan_scoped_verification_artifacts() -> None:
    execute_phase = _workflow_authority_text("execute-phase")
    planner_gap_policy = (REFERENCES_DIR / "planning" / "planner-gap-and-revision-policy.md").read_text(
        encoding="utf-8"
    )
    verifier = (AGENTS_DIR / "gpd-verifier.md").read_text(encoding="utf-8")
    audit_milestone = (WORKFLOWS_DIR / "audit-milestone.md").read_text(encoding="utf-8")

    assert "- Verification: {phase_dir}/{phase}-VERIFICATION.md" in execute_phase
    assert '"$phase_dir"/VERIFICATION.md "$phase_dir"/*-VERIFICATION.md' not in execute_phase
    assert 'ls "$phase_dir"/*-VERIFICATION.md 2>/dev/null' in planner_gap_policy
    assert 'find_files("$PHASE_DIR/*-VERIFICATION.md")' in verifier
    assert "`find_files` `GPD/phases/*/*-VERIFICATION.md` by hand" in audit_milestone
    assert "GPD/phases/01-*/VERIFICATION.md" not in audit_milestone


def test_debug_prompts_use_session_status_for_diagnosis_progress() -> None:
    debug_workflow = (WORKFLOWS_DIR / "debug.md").read_text(encoding="utf-8")
    debugger = (AGENTS_DIR / "gpd-debugger.md").read_text(encoding="utf-8")

    assert "set `session_status: diagnosed`" in debug_workflow
    assert 'Update status in frontmatter to "diagnosed"' not in debug_workflow
    assert 'update `session_status` to "diagnosed"' in debugger
    assert 'Update status to "diagnosed"' not in debugger


def test_debug_command_and_workflow_wire_directly_to_gpd_debugger() -> None:
    debug_command = (COMMANDS_DIR / "debug.md").read_text(encoding="utf-8")
    debug_workflow = (WORKFLOWS_DIR / "debug.md").read_text(encoding="utf-8")
    debugger = (AGENTS_DIR / "gpd-debugger.md").read_text(encoding="utf-8")

    assert "gpd-debugger" in debug_command
    assert "DEBUGGER_MODEL=$(gpd resolve-model gpd-debugger)" in debug_command
    _assert_command_delegates_to_workflow(
        debug_command,
        "debug",
        semantic_fragments=("workflow owns", "workspace bootstrap", "active-session handling", "symptom gathering"),
        stale_fragments=("Use ask_user for each.",),
    )
    assert "Interactive mode (direct user invocation): do not parse `VERIFICATION.md`." in debug_workflow
    assert "Interactive symptom fields:" in debug_workflow
    assert "offer: Fix now, Plan fix, Manual fix" in debug_workflow
    assert 'subagent_type="gpd-debugger"' in debug_workflow
    assert "First, read {GPD_AGENTS_DIR}/gpd-debugger.md" in debug_workflow
    assert "public writable production agent specialized for discrepancy investigation" in debugger


def test_resume_workflow_surfaces_contract_load_and_validation_state() -> None:
    raw_resume_work = _workflow_authority_text("resume-work")
    resume_work = expand_at_includes(raw_resume_work, REPO_ROOT / "src/gpd", "/runtime/")
    resume_vocabulary = (REFERENCES_DIR / "orchestration" / "resume-vocabulary.md").read_text(encoding="utf-8")

    assert "{GPD_INSTALL_DIR}/templates/state-json-schema.md" in raw_resume_work
    assert "@{GPD_INSTALL_DIR}/templates/state-json-schema.md" not in raw_resume_work
    _assert_machine_fragments(
        resume_work,
        "project_contract_validation",
        "project_contract_load_info",
        "workspace_state_exists",
        "workspace_roadmap_exists",
        "workspace_project_exists",
        "workspace_planning_exists",
        context="resume core workspace fields",
    )
    assert_resume_authority_contract(
        resume_vocabulary,
        allow_explicit_alias_examples=False,
        require_canonical_note=False,
    )
    _assert_semantic_fragments(
        resume_work,
        "canonical continuation",
        "recovery authority",
        context="resume-work continuation authority",
    )
    _assert_resume_canonical_note(resume_work)
    assert "public top-level resume vocabulary" not in resume_work
    _assert_machine_fragments(
        resume_work,
        "continuity_handoff_file",
        "recorded_continuity_handoff_file",
        "missing_continuity_handoff_file",
        "machine_change_detected",
        "machine_change_notice",
        "current_hostname",
        "current_platform",
        "session_hostname",
        "session_platform",
        context="resume continuity and machine fields",
    )
    _assert_semantic_fragments(
        resume_work,
        "workspace_*",
        "user-requested workspace",
        "recent-project list is advisory",
        "machine-local",
        "reloads",
        "canonical state",
        "`project_contract_gate.authoritative` is true",
        "visible gate inputs and diagnostics",
        "`project_contract_gate.authoritative` is false",
        "visible-but-blocked",
        context="resume workspace and contract authority",
    )
    _assert_semantic_fragments(
        resume_work,
        "Contract repair required",
        "blocked contract",
        "state-integrity issue",
        "before planning or execution",
        context="resume contract repair gate",
    )


def _assert_resume_canonical_note(text: str) -> None:
    _assert_semantic_fragments(
        text,
        "Canonical continuation fields",
        "public resume vocabulary",
        context="resume canonical public vocabulary",
    )


def test_resume_command_keeps_internal_resume_backend_details_out_of_public_prompt_surface() -> None:
    resume_command = expand_at_includes(
        (COMMANDS_DIR / "resume-work.md").read_text(encoding="utf-8"),
        REPO_ROOT / "src/gpd",
        "/runtime/",
    )

    _assert_resume_canonical_note(resume_command)
    assert "`resume_surface`" not in resume_command
    assert "gpd init resume" not in resume_command


def test_execution_observability_and_resume_workflow_surfaces_stay_conservative_about_stalls() -> None:
    help_command = (COMMANDS_DIR / "help.md").read_text(encoding="utf-8")
    help_workflow = expand_at_includes(
        (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8"),
        REPO_ROOT / "src/gpd",
        "/runtime/",
    )
    progress = (WORKFLOWS_DIR / "progress.md").read_text(encoding="utf-8")
    resume_work = expand_at_includes(
        _workflow_authority_text("resume-work"),
        REPO_ROOT / "src/gpd",
        "/runtime/",
    )

    _assert_command_delegates_to_workflow(
        help_command,
        "help",
        semantic_fragments=("GPD help", "delegating", "workflow-owned help surface"),
    )
    assert_execution_observability_surface_contract(help_workflow)
    assert_cost_surface_discoverability(help_workflow)
    _assert_semantic_fragments(
        help_command,
        "workflow-owned stable markers",
        "extraction boundaries",
        context="help command extraction boundary",
    )
    assert "When STATE.md appears out of sync with disk reality" in progress
    assert "advisory context only" in resume_work
    _assert_semantic_fragments(
        resume_work,
        "not a ranked bounded-segment resume candidate",
        'does not justify `active_resume_kind="bounded_segment"`',
        context="resume stall advisory boundary",
    )


def test_pause_resume_and_help_wiring_keep_runtime_handoff_and_local_snapshot_boundary() -> None:
    pause_work = (WORKFLOWS_DIR / "pause-work.md").read_text(encoding="utf-8")
    resume_work = expand_at_includes(
        _workflow_authority_text("resume-work"),
        REPO_ROOT / "src/gpd",
        "/runtime/",
    )
    help_workflow = expand_at_includes(
        (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8"),
        REPO_ROOT / "src/gpd",
        "/runtime/",
    )

    assert "gpd:resume-work" in resume_work
    assert "gpd resume" in resume_work
    assert "gpd resume --recent" in resume_work
    assert "gpd init resume" not in resume_work
    _assert_semantic_fragments(
        resume_work,
        "guided runtime path",
        "public local read-only summary",
        "cross-project discovery surface",
        "advisory and machine-local",
        "reloads",
        "canonical state",
        context="resume public local snapshot boundary",
    )
    _assert_resume_canonical_note(resume_work)
    assert "resume_candidates" in resume_work
    assert "`resume_surface`" not in resume_work
    _assert_resume_canonical_note(help_workflow)
    _assert_semantic_fragments(
        resume_work,
        "Do NOT invent additional candidates",
        "plan files without summaries",
        "auto-checkpoints",
        "ad hoc checkpoints",
        context="resume candidate source boundary",
    )
    assert "gpd:resume-work" in pause_work
    assert "gpd resume" in pause_work
    assert "gpd resume --recent" in pause_work
    _assert_semantic_fragments(
        pause_work,
        "canonical recorded handoff artifact",
        "current phase",
        context="pause-work canonical handoff artifact",
    )
    _assert_prompt_contracts(
        pause_work,
        semantic_anchor(
            "pause-work continuity wording",
            ("continuation handoff artifact", "session continuity"),
            mode=FragmentMode.ANY,
            match=MatchMode.CASEFOLD_NORMALIZED,
            context="pause-work continuity wording",
        ),
    )
    assert "session.resume_file" not in pause_work
    _assert_resume_canonical_note(help_workflow)
    assert_recovery_ladder_contract(
        help_workflow,
        resume_work_fragments=("gpd:resume-work",),
        suggest_next_fragments=("gpd:suggest-next",),
        pause_work_fragments=("gpd:pause-work",),
    )


def test_state_portability_reference_keeps_resume_public_vocabulary_note_compact() -> None:
    state_portability = expand_at_includes(
        (REFERENCES_DIR / "orchestration" / "state-portability.md").read_text(encoding="utf-8"),
        REPO_ROOT / "src/gpd",
        "/runtime/",
    )
    help_workflow = expand_at_includes(
        (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8"),
        REPO_ROOT / "src/gpd",
        "/runtime/",
    )

    _assert_resume_canonical_note(state_portability)
    assert "public top-level resume vocabulary" not in state_portability
    assert "gpd observe execution" in help_workflow
    assert "next read-only checks from your normal terminal" in help_workflow


def test_pause_resume_and_derivation_templates_preserve_result_id_continuity() -> None:
    pause_work = (WORKFLOWS_DIR / "pause-work.md").read_text(encoding="utf-8")
    resume_work = _workflow_authority_text("resume-work")
    continue_here = (TEMPLATES_DIR / "continue-here.md").read_text(encoding="utf-8")
    derivation_state = (TEMPLATES_DIR / "DERIVATION-STATE.md").read_text(encoding="utf-8")

    assert "Every intermediate result added to state.json (with result IDs)" in pause_work
    assert (
        "The `<persistent_state>` and `<intermediate_results>` sections in `.continue-here.md` are filled (documenting what was appended to DERIVATION-STATE.md)"
        in pause_work
    )
    assert 'gpd state record-session "${record_session_args[@]}"' in pause_work
    assert "Treat an explicit `--last-result-id` override as a manual repair path" in pause_work
    assert "If the active bounded-segment continuity already carries a canonical" in pause_work
    assert "last_result_id, omit --last-result-id and let the automatic continuity path" in pause_work
    assert "canonical `last_result_id`" in resume_work
    assert "preferred continuity anchor" in resume_work
    assert "Reference the result IDs added to state.json this session" in continue_here
    assert "Each entry links back to the state.json intermediate_results key" in continue_here
    assert "Result IDs should match those in state.json intermediate_results" in derivation_state
    assert "By resume-work workflow: applies pruning rules" not in derivation_state
    assert "resume-work reads it without mutation" in derivation_state


def test_state_compaction_lifecycle_docs_do_not_claim_progress_mutates_state() -> None:
    compact_state = (WORKFLOWS_DIR / "compact-state.md").read_text(encoding="utf-8")
    help_workflow = (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8")

    assert "Triggered automatically when progress.md detects" not in compact_state
    assert "Triggered automatically when STATE.md exceeds 1500 lines" not in help_workflow
    assert "Suggested by progress.md" in compact_state
    assert "Suggested by `gpd:progress`" in help_workflow


def test_protocol_bundle_context_surfaces_across_planning_execution_and_verification() -> None:
    planner_prompt = (TEMPLATES_DIR / "planner-subagent-prompt.md").read_text(encoding="utf-8")
    plan_phase = _workflow_authority_text("plan-phase")
    research_phase = _workflow_authority_text("research-phase")
    execute_phase = _workflow_authority_text("execute-phase")
    execute_plan = (WORKFLOWS_DIR / "execute-plan.md").read_text(encoding="utf-8")
    verify_phase = (WORKFLOWS_DIR / "verify-phase.md").read_text(encoding="utf-8")
    verify_work = _workflow_authority_text("verify-work")
    continuation = (TEMPLATES_DIR / "continuation-prompt.md").read_text(encoding="utf-8")
    planner_agent = (AGENTS_DIR / "gpd-planner.md").read_text(encoding="utf-8")
    checker_agent = (AGENTS_DIR / "gpd-plan-checker.md").read_text(encoding="utf-8")
    executor_agent = (AGENTS_DIR / "gpd-executor.md").read_text(encoding="utf-8")
    verifier_agent = (AGENTS_DIR / "gpd-verifier.md").read_text(encoding="utf-8")
    executor_guide = (REFERENCES_DIR / "execution" / "executor-subfield-guide.md").read_text(encoding="utf-8")

    bundle_fragments = (
        "<selected_protocol_bundle_ids>",
        "{selected_protocol_bundle_ids}",
        "<protocol_bundle_load_manifest>",
        "{protocol_bundle_load_manifest}",
        "<protocol_bundle_context>",
        "{protocol_bundle_context}",
        "<protocol_bundle_verifier_extensions>",
        "{protocol_bundle_verifier_extensions}",
    )
    for text in (planner_prompt, continuation):
        _assert_machine_fragments(text, *bundle_fragments, context="protocol bundle prompt placeholders")
    assert "<protocol_bundles>" not in continuation

    _assert_semantic_fragments(
        plan_phase,
        "Use the protocol bundle handoff as the primary specialized method/domain surface",
        context="plan-phase protocol bundle handoff semantics",
    )
    _assert_machine_fragments(
        plan_phase,
        "- `{selected_protocol_bundle_ids}` -> {selected_protocol_bundle_ids}",
        "- `{protocol_bundle_load_manifest}` -> {protocol_bundle_load_manifest}",
        "- `{protocol_bundle_verifier_extensions}` -> {protocol_bundle_verifier_extensions}",
        "<protocol_bundle_load_manifest>",
        context="plan-phase protocol bundle fields",
    )
    _assert_machine_fragments(
        research_phase,
        "selected_protocol_bundle_ids`, `protocol_bundle_load_manifest`, `protocol_bundle_context`, `protocol_bundle_verifier_extensions`",
        "<protocol_bundle_verifier_extensions>",
        context="research-phase protocol bundle fields",
    )
    _assert_semantic_fragments(
        research_phase,
        "selected_protocol_bundle_ids` is non-empty",
        "bundle context",
        "load manifest",
        context="research-phase protocol bundle semantics",
    )
    _assert_machine_fragments(
        execute_phase,
        "<selected_protocol_bundle_ids>{selected_protocol_bundle_ids}</selected_protocol_bundle_ids>",
        "<protocol_bundle_load_manifest>{protocol_bundle_load_manifest}</protocol_bundle_load_manifest>",
        "<protocol_bundle_verifier_extensions>{protocol_bundle_verifier_extensions}</protocol_bundle_verifier_extensions>",
        "`{protocol_bundle_verifier_extensions}`: From checkpoint_resume init JSON",
        context="execute-phase protocol bundle fields",
    )
    _assert_semantic_fragments(
        execute_phase,
        "protocol bundle verifier extensions",
        context="execute-phase protocol bundle semantics",
    )
    _assert_machine_fragments(
        execute_plan,
        "protocol_bundle_load_manifest",
        "protocol_bundle_verifier_extensions",
        context="execute-plan protocol bundle fields",
    )
    _assert_machine_fragments(
        verify_phase,
        "protocol_bundle_verifier_extensions",
        context="verify-phase protocol bundle fields",
    )
    _assert_machine_fragments(
        verify_work,
        "protocol_bundle_verifier_extensions",
        "<protocol_bundle_load_manifest>",
        context="verify-work protocol bundle fields",
    )
    _assert_semantic_fragments(
        verify_work,
        "primary source",
        "bundle checklist extensions",
        context="verify-work protocol bundle checklist source",
    )
    _assert_semantic_fragments(
        planner_agent, "selected protocol bundle context", context="planner protocol bundle context"
    )
    _assert_machine_fragments(checker_agent, "protocol_bundle_coverage", context="plan checker protocol bundle field")
    _assert_semantic_fragments(
        executor_agent,
        "additive routing hints",
        "first additive specialization pass",
        context="executor protocol bundle routing",
    )
    _assert_semantic_fragments(
        verifier_agent,
        "bundle checklist extensions",
        "prefer `protocol_bundle_verifier_extensions`",
        "`protocol_bundle_context` from init JSON",
        context="verifier protocol bundle checklist",
    )
    _assert_semantic_fragments(
        executor_guide,
        "fallback index",
        "manual cross-check",
        "not a default route",
        context="executor subfield guide protocol bundle fallback",
    )


def test_quick_reference_context_passes_protocol_bundle_fields_but_default_stays_free() -> None:
    quick = _workflow_authority_text("quick")

    planner_reference_branch = re.search(
        r"If `TASK_AUTHORING_INIT\.staged_loading\.stage_id` is `reference_context`, append this selected reference payload:(.*?)</planning_context>",
        quick,
        flags=re.DOTALL,
    )
    assert planner_reference_branch is not None
    _assert_machine_fragments(
        planner_reference_branch.group(1),
        "<selected_protocol_bundle_ids>",
        "{selected_protocol_bundle_ids}",
        "<protocol_bundle_load_manifest>",
        "{protocol_bundle_load_manifest}",
        "<protocol_bundle_context>",
        "{protocol_bundle_context}",
        "<protocol_bundle_verifier_extensions>",
        "{protocol_bundle_verifier_extensions}",
        context="quick planner reference protocol bundle placeholders",
    )

    executor_reference_branch = re.search(
        r"If the selected planner stage was `reference_context`, pass through the selected reference payload:(.*?)<constraints>",
        quick,
        flags=re.DOTALL,
    )
    assert executor_reference_branch is not None
    _assert_machine_fragments(
        executor_reference_branch.group(1),
        "<selected_protocol_bundle_ids>",
        "{selected_protocol_bundle_ids}",
        "<protocol_bundle_load_manifest>",
        "{protocol_bundle_load_manifest}",
        "<protocol_bundle_context>",
        "{protocol_bundle_context}",
        "<protocol_bundle_verifier_extensions>",
        "{protocol_bundle_verifier_extensions}",
        context="quick executor reference protocol bundle placeholders",
    )

    default_prefix = quick.split(
        "If `TASK_AUTHORING_INIT.staged_loading.stage_id` is `reference_context`, append this selected reference payload:",
        1,
    )[0]
    assert "**Default Reference Runtime:** not loaded for `task_authoring`." in default_prefix
    assert "{selected_protocol_bundle_ids}" not in default_prefix
    assert "{protocol_bundle_context}" not in default_prefix


def test_executor_bundle_fallback_stays_generic_when_no_bundle_fits() -> None:
    executor_agent = (AGENTS_DIR / "gpd-executor.md").read_text(encoding="utf-8")
    executor_guide = (REFERENCES_DIR / "execution" / "executor-subfield-guide.md").read_text(encoding="utf-8")

    _assert_semantic_fragments(
        executor_agent,
        "If no bundle is selected",
        "generic execution flow",
        "contract-backed anchors and checks",
        "instead of forcing the work into a topic bucket",
        "Do not stay trapped",
        "fallback subfield",
        context="executor generic fallback when no bundle fits",
    )
    _assert_semantic_fragments(
        executor_guide,
        "If no row cleanly fits",
        "generic execution guidance",
        "core verification expectations",
        "instead of guessing",
        context="executor guide generic fallback when no bundle fits",
    )


def test_runtime_parity_docs_use_canonical_model_resolution_and_generic_handoff_rules() -> None:
    model_resolution = (REFERENCES_DIR / "orchestration" / "model-profile-resolution.md").read_text(encoding="utf-8")
    agent_delegation = (REFERENCES_DIR / "orchestration" / "agent-delegation.md").read_text(encoding="utf-8")
    execute_phase = _workflow_authority_text("execute-phase")
    execute_plan = (WORKFLOWS_DIR / "execute-plan.md").read_text(encoding="utf-8")
    quick = _workflow_authority_text("quick")

    _assert_semantic_fragments(
        model_resolution,
        "Do not scrape",
        "`GPD/config.json`",
        "directly in workflows",
        context="model profile resolution",
    )
    _assert_machine_fragments(
        model_resolution,
        "gpd resolve-tier",
        "gpd resolve-model",
        context="model profile resolution commands",
    )
    _assert_semantic_fragments(
        agent_delegation,
        "Delegation Contract",
        "Return-envelope parity",
        context="agent delegation parity",
    )
    _assert_semantic_fragments(
        execute_plan,
        "control decision authority throughout execution",
        "Handoff verification",
        context="execute-plan handoff authority",
    )
    _assert_semantic_fragments(execute_phase, "Handoff verification", context="execute-phase handoff authority")
    _assert_semantic_fragments(
        execute_phase,
        "false failure",
        "delivered work",
        "child-listed",
        "artifacts",
        context="execute-phase false failure guard",
    )
    _assert_machine_fragments(
        quick,
        "First, read {GPD_AGENTS_DIR}/gpd-planner.md for your role and instructions.",
        context="quick planner delegation",
    )
    _assert_semantic_fragments(quick, "Handoff verification", context="quick handoff verification")
    _assert_semantic_fragments(
        quick,
        "staged quick init",
        "task-bootstrap",
        "default task-authoring",
        "`reference_context` stage",
        "actually needs project reference artifacts",
        context="quick staged loading",
    )
    _assert_machine_fragments(
        quick,
        'gpd --raw init quick "$DESCRIPTION" --stage task_bootstrap',
        'gpd --raw init quick "$DESCRIPTION" --stage task_authoring',
        'gpd --raw init quick "$DESCRIPTION" --stage reference_context',
        "project_contract_load_info.status",
        "project_contract_validation.valid",
        "project_contract_validation",
        "project_contract_load_info",
        context="quick staged init commands and fields",
    )
    _assert_semantic_fragments(
        quick,
        "Quick mode",
        "approved `project_contract`",
        "`project_contract_gate.authoritative`",
        "true",
        context="quick project contract gate",
    )

    _assert_semantic_fragments(
        quick,
        "default small-task path",
        "does not load",
        "full active reference ledger",
        context="quick reference context",
    )
    _assert_init_placeholders_visible(
        quick,
        (
            "project_contract_gate",
            "project_contract_load_info",
            "project_contract_validation",
            "contract_intake",
        ),
        context="quick contract gate placeholders",
    )
    assert "gpd validate plan-preflight" in quick
    assert "references/orchestration/continuation-boundary.md" in quick
    assert "classifyHandoffIfNeeded" not in execute_phase
    assert "classifyHandoffIfNeeded" not in execute_plan
    assert "classifyHandoffIfNeeded" not in quick
    assert "cat GPD/config.json" not in model_resolution
    assert "print(c.get('model_profile', 'review'))" not in execute_phase


def test_verify_work_gap_closure_delegation_surfaces_contract_gate_inputs() -> None:
    verify_work = _workflow_authority_text("verify-work")

    _assert_init_placeholders_visible(
        verify_work,
        (
            "project_contract_gate",
            "project_contract_load_info",
            "project_contract_validation",
            "contract_intake",
            "effective_reference_intake",
        ),
        context="verify-work contract gate placeholders",
    )
    assert "tool_requirements" in verify_work
    assert "machine-checkable hard requirements" in verify_work
    assert "The shared planner template owns the canonical planning policy and contract gate." not in verify_work


def test_decisive_comparisons_paper_quality_artifacts_and_profile_invariants_are_visible() -> None:
    compare_command = (COMMANDS_DIR / "compare-results.md").read_text(encoding="utf-8")
    compare_workflow = (WORKFLOWS_DIR / "compare-results.md").read_text(encoding="utf-8")
    internal_template = (TEMPLATES_DIR / "paper" / "internal-comparison.md").read_text(encoding="utf-8")
    figure_tracker = (TEMPLATES_DIR / "paper" / "figure-tracker.md").read_text(encoding="utf-8")
    write_paper = _workflow_authority_text("write-paper")
    new_project = _workflow_authority_text("new-project")
    execute_phase = _workflow_authority_text("execute-phase")
    scoring = (REFERENCES_DIR / "publication" / "paper-quality-scoring.md").read_text(encoding="utf-8")
    settings = (WORKFLOWS_DIR / "settings.md").read_text(encoding="utf-8")
    profiles = (REFERENCES_DIR / "orchestration" / "model-profiles.md").read_text(encoding="utf-8")
    artifact_surfacing = (REFERENCES_DIR / "orchestration" / "artifact-surfacing.md").read_text(encoding="utf-8")
    hypothesis_protocol = (REFERENCES_DIR / "protocols" / "hypothesis-driven-research.md").read_text(encoding="utf-8")
    quick_reference = (REFERENCES_DIR / "verification" / "core" / "verification-quick-reference.md").read_text(
        encoding="utf-8"
    )
    verifier_profiles = (REFERENCES_DIR / "verification" / "meta" / "verifier-profile-checks.md").read_text(
        encoding="utf-8"
    )
    planner = (AGENTS_DIR / "gpd-planner.md").read_text(encoding="utf-8")
    executor = (AGENTS_DIR / "gpd-executor.md").read_text(encoding="utf-8")
    verifier_agent = (AGENTS_DIR / "gpd-verifier.md").read_text(encoding="utf-8")

    _assert_semantic_fragments(compare_command, "emit decisive verdicts", context="compare-results command verdicts")
    _assert_machine_fragments(
        compare_workflow,
        "GPD/comparisons/[slug]-COMPARISON.md",
        context="compare-results workflow artifact path",
    )
    assert "GPD/analysis/comparison-{slug}.md" not in compare_workflow
    _assert_machine_fragments(internal_template, "comparison_verdicts", context="internal comparison verdict field")
    _assert_machine_fragments(
        figure_tracker,
        "figure_registry",
        "role: smoking_gun|benchmark|comparison|sanity_check|publication_polish|other",
        "`${PAPER_DIR}/FIGURE_TRACKER.md`",
        context="figure tracker schema fields",
    )
    _assert_semantic_fragments(
        figure_tracker, "canonical schema source of truth", context="figure tracker schema authority"
    )
    _assert_machine_fragments(
        write_paper,
        "validate paper-quality --from-project .",
        "`${PAPER_DIR}/FIGURE_TRACKER.md`",
        context="write-paper paper-quality figure tracker",
    )
    _assert_machine_fragments(
        new_project, '"review_cadence": "dense"', "Dense review cadence", context="dense review default"
    )
    _assert_semantic_fragments(
        execute_phase,
        "prior decisive `contract_results`",
        "decisive `comparison_verdicts`",
        "explicit approach lock",
        context="execute-phase decisive prior evidence",
    )
    _assert_machine_fragments(execute_phase, "paper/FIGURE_TRACKER.md", context="execute-phase figure tracker path")
    assert "GPD/paper/FIGURE_TRACKER.md" not in execute_phase
    _assert_machine_fragments(
        scoring, "figure_registry", "manuscript-root `FIGURE_TRACKER.md`", context="scoring figure fields"
    )
    _assert_machine_fragments(
        artifact_surfacing,
        "paper/<topic_stem>.tex",
        "paper/<topic_stem>.pdf",
        context="artifact surfacing paper outputs",
    )
    _assert_machine_fragments(
        hypothesis_protocol, "ARTIFACT-MANIFEST.json", "MANUSCRIPT_TEX", context="hypothesis protocol manifest fields"
    )
    assert "main.tex" not in hypothesis_protocol
    _assert_machine_fragments(settings, "Review (Recommended)", context="settings review profile")
    _assert_semantic_fragments(profiles, "all required contract-aware checks", context="model profile yolo gates")
    _assert_machine_fragments(
        quick_reference, "current registry: 5.1-5.19", context="verification quick reference registry"
    )
    _assert_semantic_fragments(
        verifier_profiles,
        "still run every contract-aware check required by the plan",
        context="verifier profile yolo contract-aware checks",
    )
    _assert_prompt_concepts(
        planner,
        {
            "yolo gates": ("first-result gates", "anchor checks", "pre-fanout gates"),
        },
        context="planner autonomy gates",
    )
    _assert_semantic_fragments(
        planner, "Do NOT change conventions mid-project", "explicit checkpoint", context="planner convention lock"
    )
    _assert_semantic_fragments(
        executor,
        "Required first-result, anchor, and pre-fanout gates",
        "yolo mode",
        context="executor yolo gates",
    )
    _assert_machine_fragments(verifier_agent, "suggested_contract_checks", context="verifier suggested contract checks")


def test_publication_workflows_refresh_bibliography_audit_after_bibliography_changes() -> None:
    write_paper = _workflow_authority_text("write-paper")
    respond = _workflow_authority_text("respond-to-referees")
    peer_review = _workflow_authority_text("peer-review")
    peer_review_index = (WORKFLOWS_DIR / "peer-review.md").read_text(encoding="utf-8")
    arxiv_submission = _workflow_authority_text("arxiv-submission")
    shared_preflight = (TEMPLATES_DIR / "paper" / "publication-manuscript-root-preflight.md").read_text(
        encoding="utf-8"
    )

    _assert_semantic_fragments(
        write_paper,
        "gpd paper-build",
        "${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json",
        "reference_id -> bibtex_key",
        "bibliography or citation set changes",
        "strict review",
        context="write-paper bibliography audit refresh",
    )
    _assert_semantic_fragments(
        respond,
        "refresh",
        "${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json",
        "response letter",
        "final review",
        context="respond bibliography audit refresh",
    )
    _assert_forbidden_fragments(
        peer_review_index,
        PUBLICATION_SHARED_PREFLIGHT_INCLUDE,
        context="peer-review shared preflight include form",
    )
    _assert_machine_fragments(
        peer_review,
        "{GPD_INSTALL_DIR}/templates/paper/publication-manuscript-root-preflight.md",
        "bibliography_audit_clean",
        "reproducibility_ready",
        context="peer-review bibliography audit strict fields",
    )
    _assert_loaded_authorities(
        "peer-review",
        "artifact_discovery",
        "references/publication/publication-review-round-artifacts.md",
    )
    _assert_semantic_fragments(
        peer_review,
        "review-ready",
        "merely present",
        context="peer-review bibliography audit strict fields",
    )
    _assert_semantic_fragments(
        shared_preflight,
        "gpd paper-build",
        "regenerates",
        "ARTIFACT-MANIFEST.json",
        "BIBLIOGRAPHY-AUDIT.json",
        context="publication preflight paper-build authority",
    )
    _assert_machine_fragments(
        write_paper,
        "{GPD_INSTALL_DIR}/references/publication/publication-bootstrap-preflight.md",
        PUBLICATION_RESPONSE_WRITER_HANDOFF_INCLUDE,
        context="write-paper bibliography workflow includes",
    )
    _assert_machine_fragments(
        respond,
        PUBLICATION_BOOTSTRAP_PREFLIGHT_INCLUDE,
        PUBLICATION_RESPONSE_WRITER_HANDOFF_INCLUDE,
        context="respond bibliography workflow includes",
    )
    _assert_machine_fragments(
        arxiv_submission,
        PUBLICATION_BOOTSTRAP_PREFLIGHT_INCLUDE,
        PUBLICATION_ROUND_ARTIFACTS_INCLUDE,
        context="arxiv bibliography workflow includes",
    )
    _assert_forbidden_fragments(
        arxiv_submission,
        PUBLICATION_RESPONSE_WRITER_HANDOFF_INCLUDE,
        context="arxiv bibliography workflow includes",
    )


def test_publication_workflows_keep_manuscript_local_reference_status_rooted_at_the_resolved_manuscript_directory() -> (
    None
):
    write_paper = _workflow_authority_text("write-paper")
    peer_review = _workflow_authority_text("peer-review")
    respond = _workflow_authority_text("respond-to-referees")
    arxiv_submission = _workflow_authority_text("arxiv-submission")

    _assert_machine_fragments(
        write_paper,
        "{GPD_INSTALL_DIR}/references/publication/publication-bootstrap-preflight.md",
        PUBLICATION_RESPONSE_WRITER_HANDOFF_INCLUDE,
        context="write-paper manuscript-local support includes",
    )
    _assert_semantic_fragments(
        peer_review,
        "After resolution",
        "manuscript-local support artifacts",
        "same explicit manuscript directory",
        "BIBLIOGRAPHY_AUDIT_PATH",
        "bibliography_audit_path",
        "${MANUSCRIPT_ROOT}/BIBLIOGRAPHY-AUDIT.json",
        context="peer-review manuscript-local support artifacts",
    )
    _assert_semantic_fragments(
        respond,
        "refresh",
        "${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json",
        "response letter",
        "final review",
        "bounded continuation path",
        context="respond manuscript-local support artifacts",
    )
    _assert_machine_fragments(
        respond,
        PUBLICATION_BOOTSTRAP_PREFLIGHT_INCLUDE,
        PUBLICATION_RESPONSE_WRITER_HANDOFF_INCLUDE,
        context="respond manuscript-local support includes",
    )
    _assert_machine_fragments(
        arxiv_submission,
        PUBLICATION_BOOTSTRAP_PREFLIGHT_INCLUDE,
        context="arxiv manuscript-local support includes",
    )
    _assert_semantic_fragments(
        arxiv_submission,
        "Strict preflight reads",
        "ARTIFACT-MANIFEST.json",
        "BIBLIOGRAPHY-AUDIT.json",
        "reproducibility-manifest.json",
        "same resolved manuscript root",
        "source of truth for packaging",
        context="arxiv manuscript-local support artifacts",
    )


def test_respond_to_referees_arxiv_handoff_uses_public_positional_arxiv_target() -> None:
    respond = _workflow_authority_text("respond-to-referees")
    help_workflow = (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8")
    arxiv_command = (COMMANDS_DIR / "arxiv-submission.md").read_text(encoding="utf-8")
    arxiv_workflow = _workflow_authority_text("arxiv-submission")
    arxiv_help_block = help_workflow.split(
        "**`gpd:arxiv-submission [manuscript root or .tex entrypoint]`**",
        1,
    )[1].split("**`gpd:explain", 1)[0]

    _assert_public_fragments(
        arxiv_command,
        'argument-hint: "[manuscript root or .tex entrypoint]"',
        "Paper target: $ARGUMENTS (optional manuscript root or `.tex` entrypoint",
        context="arxiv public positional manuscript target",
    )
    _assert_semantic_fragments(
        arxiv_workflow,
        "Resolve the manuscript target",
        "raw preflight",
        "$ARGUMENTS",
        context="arxiv public positional manuscript target",
    )
    _assert_public_fragments(
        arxiv_help_block,
        "`gpd:arxiv-submission paper/`",
        context="arxiv help positional manuscript target",
    )
    _assert_forbidden_fragments(
        arxiv_help_block,
        "--manuscript",
        context="arxiv help positional manuscript target",
    )

    _assert_public_fragments(
        respond,
        "`gpd:arxiv-submission <resolved-manuscript>`",
        "`gpd:arxiv-submission paper/curvature_flow_bounds.tex`",
        context="respond public arxiv positional handoff",
    )
    _assert_forbidden_fragments(
        respond,
        "`$gpd-arxiv-submission <resolved-manuscript>`",
        "`$gpd-arxiv-submission paper/curvature_flow_bounds.tex`",
        "`gpd:arxiv-submission --manuscript",
        "`$gpd-arxiv-submission --manuscript",
        context="respond public arxiv positional handoff",
    )


def test_adaptive_mode_and_review_cadence_docs_stay_aligned() -> None:
    research_phase = _workflow_authority_text("research-phase")
    verify_work = _workflow_authority_text("verify-work")
    plan_phase = _workflow_authority_text("plan-phase")
    new_project = _workflow_authority_text("new-project")
    new_milestone = _workflow_authority_text("new-milestone")
    set_profile = (WORKFLOWS_DIR / "set-profile.md").read_text(encoding="utf-8")
    settings = (WORKFLOWS_DIR / "settings.md").read_text(encoding="utf-8")
    planning_config = (REFERENCES_DIR / "planning" / "planning-config.md").read_text(encoding="utf-8")
    research_modes = (REFERENCES_DIR / "research" / "research-modes.md").read_text(encoding="utf-8")
    meta_orchestration = (REFERENCES_DIR / "orchestration" / "meta-orchestration.md").read_text(encoding="utf-8")

    expected_anchor = "prior decisive evidence or an explicit approach lock"

    for text in (research_phase, research_modes, meta_orchestration):
        _assert_semantic_fragments(
            text,
            expected_anchor,
            context="adaptive mode decisive evidence anchor",
        )
    _assert_semantic_concept(
        plan_phase,
        "plan-phase adaptive mode evidence gate",
        required=expected_anchor,
        forbidden=("phase 1-2", "phase 3+", "N≥3"),
        context="plan-phase adaptive mode stale thresholds",
    )
    _assert_semantic_fragments(
        new_project,
        "adaptive",
        "Research mode",
        "Review cadence",
        context="new-project adaptive mode gate",
    )
    _assert_semantic_fragments(
        new_milestone,
        "prior milestones",
        "decisive evidence",
        "explicit approach lock",
        "project_contract_validation",
        "project_contract_load_info",
        "project_contract_gate.authoritative",
        "checkpoint with the user",
        "repair the stored contract",
        context="new-milestone adaptive mode gate",
    )
    _assert_semantic_fragments(
        verify_work,
        "same contract-critical floor",
        context="verify-work review cadence floor",
    )
    _assert_machine_fragments(
        set_profile,
        "does NOT rewrite `execution.review_cadence`",
        context="set-profile review cadence field boundary",
    )
    _assert_forbidden_fragments(
        set_profile,
        "verify_between_waves",
        context="set-profile stale cadence field",
    )
    _assert_semantic_fragments(
        settings,
        "independent of `model_profile`",
        "`research_mode`",
        context="settings review cadence independence",
    )
    _assert_semantic_fragments(
        planning_config,
        "wall-clock",
        "task budgets",
        "bounded segments",
        "phase number",
        "wave number",
        "`model_profile`",
        "do not create or retire these gates",
        context="planning config review cadence invariants",
    )
    _assert_semantic_fragments(
        research_modes,
        "There is no separate `adaptive_transition` block",
        context="research-modes adaptive transition boundary",
    )
    _assert_semantic_fragments(
        meta_orchestration,
        "evidence-driven",
        "phase-count-driven",
        "Proxy-only",
        "sanity-only",
        context="meta-orchestration adaptive mode gate",
    )


def test_settings_command_keeps_wrapper_thin_and_delegates_manual_to_workflow() -> None:
    settings_command = (COMMANDS_DIR / "settings.md").read_text(encoding="utf-8")

    _assert_machine_fragments(
        settings_command,
        "@{GPD_INSTALL_DIR}/workflows/settings.md",
        context="settings command workflow include",
    )
    _assert_semantic_fragments(
        settings_command,
        "wrapper thin",
        "parallel settings flow",
        "preset",
        "model-posture",
        "tier-model",
        "budget",
        "permission-sync",
        "local CLI bridge",
        context="settings command wrapper boundary",
    )


def test_help_surfaces_distinguish_runtime_slash_commands_from_local_cli_subcommands() -> None:
    help_command = (COMMANDS_DIR / "help.md").read_text(encoding="utf-8")
    help_workflow = (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8")

    _assert_semantic_fragments(
        help_command,
        "GPD help",
        "delegating",
        "workflow-owned help surface",
        context="help command workflow delegation",
    )
    _assert_machine_fragments(
        help_command,
        "@{GPD_INSTALL_DIR}/workflows/help.md",
        "## Step 2: Quick Start Extract (Default Output)",
        "## Step 3: Compact Command Index (--all)",
        "## Step 4: Single Command Detail Extract (--command <name>)",
        context="help command extraction markers",
    )

    assert_help_workflow_runtime_reference_contract(help_workflow)
    _assert_machine_fragments(
        help_workflow,
        "gpd validate command-context <name>",
        context="help workflow command context validator",
    )


def test_help_command_keeps_static_quick_start_while_workflow_owns_full_reference() -> None:
    help_command = (COMMANDS_DIR / "help.md").read_text(encoding="utf-8")
    help_workflow = (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8")
    quick_start_reference = _extract_between(help_workflow, "## Quick Start", "## Command Index")

    _assert_machine_fragments(
        help_command,
        "@{GPD_INSTALL_DIR}/workflows/help.md",
        context="help command workflow include",
    )
    assert_help_command_quick_start_extract_contract(help_command)
    assert_help_command_all_extract_contract(help_command)
    assert_help_command_single_command_extract_contract(help_command)
    _assert_semantic_fragments(
        help_command,
        "Append",
        "wrapper-owned line",
        context="help command wrapper-owned quick-start line",
    )
    assert_help_workflow_runtime_reference_contract(help_workflow)
    _assert_public_fragments(
        help_workflow,
        "## Detailed Command Reference",
        context="help workflow command reference heading",
    )
    assert_help_workflow_quick_start_taxonomy_contract(quick_start_reference)


def test_help_workflow_uses_reachable_quick_start_for_resume_branch() -> None:
    help_workflow = (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8")
    quick_start = _extract_between(help_workflow, "## Quick Start", "## Command Index")
    returning_work = _extract_between(quick_start, "**Returning work**", "**Post-startup settings**")

    assert_runtime_reset_rediscovery_contract(
        help_workflow,
        extra_reset_fragments=("then run gpd resume in your normal terminal",),
        extra_reset_not_recovery_fragments=("then run gpd resume in your normal terminal",),
    )
    _assert_forbidden_fragments(
        help_workflow,
        "## Contextual Help (State-Aware Variant)",
        context="help workflow stale contextual help branch",
    )
    _assert_public_fragments(
        quick_start,
        "Returning work",
        "gpd:resume-work",
        context="help quick start returning work branch",
    )
    assert returning_work.index("gpd resume --recent") < returning_work.index("gpd:resume-work")
    _assert_public_fragments(
        returning_work,
        "gpd:progress",
        "gpd:suggest-next",
        context="help quick start returning work commands",
    )
    _assert_public_fragments(
        help_workflow,
        "gpd:tangent",
        context="help workflow tangent command",
    )


def test_help_and_execution_surfaces_wire_tangent_control_path() -> None:
    help_workflow = (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8")
    plan_phase = _workflow_authority_text("plan-phase")
    execute_phase = _workflow_authority_text("execute-phase")
    execute_plan = (WORKFLOWS_DIR / "execute-plan.md").read_text(encoding="utf-8")
    tangent_workflow = (WORKFLOWS_DIR / "tangent.md").read_text(encoding="utf-8")

    _assert_public_fragments(
        help_workflow,
        "gpd:tangent",
        context="help tangent command surface",
    )
    assert re.search(
        r"gpd:tangent[^\n]*?(?:tangent|side investigation|alternative direction|parallel)", help_workflow, re.I
    )
    _assert_public_fragments(
        plan_phase,
        "gpd:tangent",
        context="plan-phase tangent command surface",
    )
    assert re.search(r"gpd:tangent.*?(?:side|alternative|parallel|branch)", plan_phase, re.I | re.S)
    _assert_public_fragments(
        execute_phase,
        "gpd:tangent",
        context="execute-phase tangent command surface",
    )
    assert re.search(r"gpd:tangent.*?(?:branch|follow-up|alternative)", execute_phase, re.I | re.S)
    _assert_machine_fragments(
        execute_phase,
        "tangent_summary",
        "tangent_decision",
        context="execute-phase tangent return fields",
    )
    _assert_prompt_concepts(
        execute_phase,
        {
            "live execution tangent bridge": (
                "tangent proposal",
                "tangent_summary",
                "tangent_decision",
            ),
            "no executor-initiated side work": ("executor initiative",),
        },
        context="execute-phase tangent control",
    )
    _assert_machine_fragments(
        execute_plan,
        "tangent_summary",
        "tangent_decision",
        context="execute-plan tangent return fields",
    )
    _assert_prompt_concepts(
        execute_plan,
        {
            "bounded stop tangent payload": (
                "bounded stop",
                "same execution payload",
                "new event family",
                "tangent_summary",
                "tangent_decision",
            ),
            "telemetry cannot auto-branch": ("existing `execution` payload", "Do not auto-branch", "side work"),
        },
        context="execute-plan tangent control",
    )
    _assert_machine_fragments(
        tangent_workflow,
        "{GPD_INSTALL_DIR}/workflows/quick.md",
        "{GPD_INSTALL_DIR}/workflows/add-todo.md",
        "{GPD_INSTALL_DIR}/workflows/branch-hypothesis.md",
        context="tangent workflow command includes",
    )
    _assert_prompt_concepts(
        tangent_workflow,
        {
            "decision before selected command": (
                "$TANGENT_DECISION",
                "do not name",
                "gpd:quick",
                "gpd:add-todo",
                "gpd:branch-hypothesis",
                "gpd:execute-phase",
            ),
        },
        context="tangent workflow chooser",
    )
    _assert_prompt_concepts(
        (COMMANDS_DIR / "tangent.md").read_text(encoding="utf-8"),
        {
            "command stays at chooser until explicit outcome": (
                "exactly one tangent outcome",
                "do not present",
                "gpd:quick",
                "gpd:add-todo",
                "gpd:branch-hypothesis",
                "gpd:execute-phase",
                "gpd:tangent",
            ),
        },
        context="tangent command chooser",
    )


def test_planner_and_plan_phase_keep_no_silent_branching_and_exploit_tangent_suppression() -> None:
    planner = (REPO_ROOT / "src/gpd/agents/gpd-planner.md").read_text(encoding="utf-8")
    tangent_model = (REFERENCES_DIR / "planning" / "planner-tangent-decision-model.md").read_text(encoding="utf-8")
    plan_phase = _workflow_authority_text("plan-phase")

    for content in (planner + "\n" + tangent_model, plan_phase):
        _assert_semantic_fragments(
            content,
            "silently",
            "gpd:tangent",
            "gpd:branch-hypothesis",
            context="planner no silent tangent branching",
        )

    _assert_semantic_fragments(
        tangent_model,
        "Explore mode",
        "analysis and comparison",
        "not branch creation",
        context="planner tangent exploration boundary",
    )
    _assert_prompt_concepts(
        tangent_model,
        {
            "explicit tangent branch outcome": ("Hypothesis branches", "explicit tangent outcome"),
        },
        context="planner tangent branch policy",
    )
    _assert_prompt_concepts(
        planner + "\n" + tangent_model,
        {
            "optional tangent suppression": ("Exploit suppresses optional tangents", "current approach is blocked"),
        },
        context="planner optional tangent suppression",
    )
    _assert_semantic_fragments(
        plan_phase,
        "do not auto-create",
        "git-backed branches",
        "git.branching_strategy",
        "suppress optional tangents",
        "user explicitly requests",
        "gpd:branch-hypothesis",
        "exploit mode",
        context="plan-phase tangent suppression",
    )


def test_help_surfaces_describe_regression_check_as_metadata_scan_not_full_reverification() -> None:
    help_workflow = (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8")

    _assert_semantic_fragments(
        help_workflow,
        "SUMMARY",
        "frontmatter",
        "convention conflicts",
        "VERIFICATION",
        "canonical statuses",
        context="help regression check metadata scan",
    )
    _assert_forbidden_fragments(
        help_workflow,
        "re-runs dimensional analysis",
        "re-runs limiting cases",
        "re-runs numerical checks",
        context="help regression check avoids full reverification",
    )


def test_help_surfaces_use_projectless_examples_that_satisfy_command_context_predicates() -> None:
    help_workflow = (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8")

    _assert_help_usage_line(help_workflow, "derive-equation")
    _assert_help_usage_line(help_workflow, "discover", "--depth")
    _assert_help_usage_line(help_workflow, "dimensional-analysis", ".md")
    _assert_help_usage_line(help_workflow, "limiting-cases", ".md")
    _assert_help_usage_line(help_workflow, "numerical-convergence", ".csv")
    _assert_help_usage_line(help_workflow, "parameter-sweep", "--param", "--range")
    _assert_help_usage_line(help_workflow, "compare-experiment", ".csv")
    _assert_help_usage_line(help_workflow, "compare-results", ".md")
    _assert_help_usage_line(help_workflow, "explain")
    _assert_help_usage_line(help_workflow, "literature-review")
    _assert_help_usage_line(help_workflow, "digest-knowledge")
    _assert_help_usage_line(help_workflow, "review-knowledge", "GPD/knowledge/")
    _assert_help_usage_line(help_workflow, "sensitivity-analysis", "--target", "--params", "--method")


def test_help_surfaces_frame_relaxed_technical_analysis_lane_honestly() -> None:
    help_workflow = (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8")

    _assert_semantic_fragments(
        help_workflow,
        "Project-aware technical-analysis lane",
        "GPD/analysis/",
        "GPD/sweeps/",
        "gpd:graph",
        "gpd:error-propagation",
        "not part of this relaxed current-workspace lane",
        context="help relaxed technical-analysis lane",
    )

    _assert_semantic_fragments(
        help_workflow,
        "Current-workspace durable outputs",
        "outside a project",
        "explicit derivation target",
        "explicit file path",
        "--param",
        "--range",
        "--target",
        "--params",
        context="help relaxed technical-analysis lane",
    )


def test_expanded_artifact_intake_surfaces_use_cli_text_extraction_helper() -> None:
    peer_review_workflow = _workflow_authority_text("peer-review")
    help_workflow = (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8")
    digest_command = (COMMANDS_DIR / "digest-knowledge.md").read_text(encoding="utf-8")
    digest_workflow = (WORKFLOWS_DIR / "digest-knowledge.md").read_text(encoding="utf-8")
    referee = (AGENTS_DIR / "gpd-referee.md").read_text(encoding="utf-8")
    peer_review_help_block = help_workflow.split(
        "**`gpd:peer-review [paper directory | manuscript path | explicit artifact path]`**",
        1,
    )[1].split("**`gpd:respond-to-referees", 1)[0]

    _assert_semantic_fragments(
        peer_review_workflow,
        "`.tex`",
        "`.md`",
        "`.txt`",
        "`.pdf`",
        "`.docx`",
        "`.csv`",
        "`.tsv`",
        "`.xlsx`",
        "`.xlsm`",
        "manuscript directory path",
        context="peer-review artifact intake",
    )

    _assert_semantic_fragments(
        peer_review_workflow,
        "centralized target-aware init",
        "command-context preflight",
        "authoritative manuscript resolver",
        context="peer-review artifact intake",
    )

    _assert_semantic_fragments(
        peer_review_workflow,
        "project-backed manuscript review",
        "`paper/`",
        "`manuscript/`",
        "`draft/`",
        context="peer-review artifact intake",
    )
    _assert_semantic_fragments(
        peer_review_workflow,
        "gpd --raw init peer-review",
        "--stage bootstrap",
        context="peer-review artifact intake staged init",
    )
    _assert_semantic_fragments(
        peer_review_workflow,
        "points at one artifact path",
        "external-artifact intake surface",
        "must not widen",
        "default `paper/`, `manuscript/`, or `draft/` discovery rules",
        context="peer-review artifact intake",
    )
    _assert_machine_fragments(
        peer_review_workflow,
        'gpd validate artifact-text "$RESOLVED_MANUSCRIPT" --output ${REVIEW_ROOT}/MANUSCRIPT-TEXT.txt',
        context="peer-review artifact text validator",
    )
    _assert_forbidden_fragments(
        peer_review_workflow,
        "pdftotext",
        context="peer-review artifact text validator",
    )

    _assert_public_fragments(
        help_workflow,
        "- `gpd:peer-review [paper directory | manuscript path | explicit artifact path]`",
        context="peer-review help public command line",
    )
    _assert_semantic_fragments(
        help_workflow,
        "command-policy supported suffixes",
        "publication-artifact paths",
        context="peer-review help explicit artifact suffix policy",
    )
    _assert_forbidden_fragments(
        peer_review_help_block,
        "`.txt`, `.pdf`, `.docx`, `.csv`, `.tsv`, `.xlsx`, and `.xlsm`",
        "pdftotext",
        context="peer-review help explicit artifact suffix policy",
    )
    _assert_machine_fragments(
        peer_review_help_block,
        "gpd validate artifact-text <path> --output <txt-path>",
        context="peer-review help artifact text validator",
    )
    _assert_help_usage_line(peer_review_help_block, "peer-review", ".docx")
    assert "`gpd:peer-review data/observables.csv`" in peer_review_help_block
    _assert_semantic_fragments(
        help_workflow,
        "Example document source",
        "gpd:digest-knowledge",
        ".docx",
        "Example tabular source",
        ".csv",
        context="digest help explicit source examples",
    )

    _assert_semantic_fragments(
        digest_command,
        "explicit source-file intake",
        "`.md`",
        "`.txt`",
        "`.pdf`",
        "`.docx`",
        "`.csv`",
        "`.tsv`",
        "`.xlsx`",
        context="digest-knowledge source intake",
    )

    _assert_semantic_fragments(
        digest_command,
        "text extraction",
        "inside the workflow",
        "`gpd validate artifact-text <path> --output <txt-path>`",
        context="digest-knowledge source intake",
    )
    _assert_semantic_fragments(
        digest_workflow,
        "`source_path` suffixes",
        "`.md`",
        "`.txt`",
        "`.pdf`",
        "`.docx`",
        "`.csv`",
        "`.tsv`",
        "`.xlsx`",
        context="digest-knowledge workflow source intake",
    )
    _assert_semantic_fragments(
        digest_workflow,
        "read",
        "`.md`",
        "`.txt`",
        "`.csv`",
        "`.tsv`",
        "directly as source surfaces",
        context="digest workflow plain text source intake",
    )
    _assert_semantic_fragments(
        digest_workflow,
        "`.pdf`",
        "`.docx`",
        "`.xlsx`",
        "working text surface",
        "`gpd validate artifact-text <path> --output <txt-path>`",
        context="digest-knowledge workflow source intake",
    )

    _assert_semantic_fragments(
        digest_workflow,
        "source began",
        "`.pdf`",
        "`.docx`",
        "`.xlsx`",
        "preserve the original artifact path",
        "metadata",
        context="digest-knowledge workflow source intake",
    )

    _assert_semantic_fragments(
        referee,
        "standalone `.txt`, `.csv`, or `.tsv`",
        "extracted text surface",
        "`.pdf`, `.docx`, `.xlsx`, or `.xlsm`",
        "primary review surface",
        context="referee artifact intake",
    )


def test_peer_review_and_arxiv_use_subject_aware_publication_roots() -> None:
    peer_review = _workflow_authority_text("peer-review")
    arxiv_submission = _workflow_authority_text("arxiv-submission")

    for field in (
        "publication_subject_slug",
        "publication_lane_kind",
        "managed_publication_root",
        "selected_publication_root",
        "selected_review_root",
    ):
        _assert_machine_fragments(
            peer_review,
            field,
            context="peer-review subject-aware publication root fields",
        )
        _assert_machine_fragments(
            arxiv_submission,
            field,
            context="arxiv subject-aware publication root fields",
        )
    _assert_semantic_fragments(
        peer_review,
        "`REVIEW_ROOT`",
        "`selected_review_root`",
        "${REVIEW_ROOT}/STAGE-reader{round_suffix}.json",
        'gpd validate artifact-text "$RESOLVED_MANUSCRIPT" --output ${REVIEW_ROOT}/MANUSCRIPT-TEXT.txt',
        context="peer-review subject-aware review root",
    )
    _assert_forbidden_fragments(
        peer_review,
        "GPD/review/STAGE-reader{round_suffix}.json",
        context="peer-review subject-aware review root",
    )

    _assert_machine_fragments(
        arxiv_submission,
        "REVIEW_PREFLIGHT=$(gpd --raw validate review-preflight arxiv-submission",
        "BOOTSTRAP_INIT=$(gpd --raw init arxiv-submission --stage bootstrap)",
        'gpd --raw validate command-context arxiv-submission -- "${ARGUMENTS}"',
        'gpd --raw validate review-preflight arxiv-submission --strict -- "${ARGUMENTS}"',
        'PUBLICATION_ROOT="GPD/publication/${subject_slug}"',
        'PACKAGE_ROOT="${PUBLICATION_ROOT}/arxiv"',
        context="arxiv subject-aware publication root commands",
    )
    _assert_semantic_fragments(
        arxiv_submission,
        "Set `subject_slug`",
        "publication_subject_slug",
        context="arxiv subject-aware publication root commands",
    )
    _assert_forbidden_fragments(
        arxiv_submission,
        'gpd --raw init arxiv-submission --stage bootstrap -- "${ARGUMENTS}"',
        'PUBLICATION_ROOT="${selected_publication_root:-GPD/publication/${subject_slug}}"',
        "Derive a stable ASCII `subject_slug`",
        context="arxiv subject-aware publication root commands",
    )


def test_generated_peer_review_skill_surface_uses_artifact_text_helper_for_non_plaintext_intake() -> None:
    from gpd.mcp.servers.skills_server import get_skill

    peer_review_skill = get_skill("gpd-peer-review")
    peer_review_skill_content = peer_review_skill["content"]
    peer_review_workflow = _workflow_authority_text("peer-review")

    _assert_semantic_fragments(
        peer_review_skill_content,
        "artifact_discovery",
        "staged_loading",
        context="generated peer-review skill staged routing",
    )
    _assert_semantic_fragments(
        peer_review_workflow,
        "If none exists",
        "${REVIEW_ROOT}/",
        "gpd validate artifact-text",
        "$RESOLVED_MANUSCRIPT",
        "${REVIEW_ROOT}/MANUSCRIPT-TEXT.txt",
        "extracted file",
        "canonical",
        "`RESOLVED_MANUSCRIPT`",
        context="generated peer-review skill artifact text helper",
    )

    _assert_semantic_fragments(
        peer_review_workflow,
        "If extraction fails",
        "STOP",
        "`.txt`",
        "`.md`",
        "`.tex`",
        "`.csv`",
        "`.tsv`",
        "matching extracted `.txt` companion file",
        context="generated peer-review skill artifact text helper",
    )
    _assert_forbidden_fragments(
        peer_review_skill_content,
        "pdftotext",
        context="generated peer-review skill artifact text helper",
    )


def test_verification_and_publication_prompts_keep_decisive_contract_targets_reader_visible() -> None:
    verify_work = _workflow_authority_text("verify-work")
    write_paper = _workflow_authority_text("write-paper")
    peer_review = _workflow_authority_text("peer-review")
    respond = _workflow_authority_text("respond-to-referees")

    _assert_semantic_fragments(
        verify_work,
        "researcher",
        "phase promise",
        "parent claim",
        "acceptance test",
        "decisive comparison",
        context="verify-work decisive contract targets",
    )
    _assert_semantic_fragments(
        write_paper,
        "verification_status",
        "confidence",
        "not blockers",
        "decisive comparisons",
        "claims it actually makes",
        "pre_submission_review",
        "reproducibility manifest",
        context="write-paper decisive contract targets",
    )
    _assert_semantic_fragments(
        peer_review,
        "review-support artifacts",
        "scaffolding",
        context="peer-review decisive contract targets",
    )
    _assert_semantic_fragments(
        respond,
        "referee requests",
        "honest scope",
        "optional",
        "real support gap",
        context="respond decisive contract targets",
    )


def test_new_project_spawns_roadmapper_with_shallow_mode_in_standard_mode() -> None:
    new_project = _workflow_authority_text("new-project")
    assert "<shallow_mode>true</shallow_mode>" in new_project


def test_new_milestone_keeps_full_roadmap_detail_shallow_mode_false() -> None:
    new_milestone = _workflow_authority_text("new-milestone")
    assert "<shallow_mode>false</shallow_mode>" in new_milestone


def test_new_project_next_up_recommends_discuss_phase_1_primary() -> None:
    new_project = (WORKFLOWS_DIR / "new-project" / "completion.md").read_text(encoding="utf-8")
    # The standard-mode Next Up block is the final occurrence; the first is the --minimal path.
    next_up_block = new_project[new_project.rindex("## > Next Up") :]
    # discuss-phase 1 should appear before plan-phase 1 in that block.
    discuss_idx = next_up_block.index("`gpd:discuss-phase 1`")
    plan_idx = next_up_block.index("`gpd:plan-phase 1`")
    assert discuss_idx < plan_idx, "discuss-phase 1 must be the primary Next Up recommendation, not plan-phase"


def test_roadmapper_documents_shallow_mode_behavior() -> None:
    roadmapper = (AGENTS_DIR / "gpd-roadmapper.md").read_text(encoding="utf-8")
    assert "shallow_mode" in roadmapper
    assert "Phase 1" in roadmapper
    assert "stub" in roadmapper.lower()


def test_route_workflow_uses_physics_scope_examples_and_ordered_compound_contract() -> None:
    route_workflow = (WORKFLOWS_DIR / "route.md").read_text(encoding="utf-8")
    route_command = (COMMANDS_DIR / "route.md").read_text(encoding="utf-8")
    help_workflow = (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8")

    _assert_machine_fragments(
        route_workflow,
        "STATE=$(gpd --raw state get --include position,continuation)",
        "fail_closed_on_state_conflict",
        "state/roadmap phase mismatch or missing active phase directory -> `gpd:sync-state`",
        "convention-lock or `GPD/CONVENTIONS.md` mismatch -> `gpd:validate-conventions`",
        context="route workflow state and conflict contracts",
    )
    _assert_forbidden_fragments(
        route_workflow,
        "position,session,continuation",
        "TAM/revenue/impact analysis",
        context="route workflow stale command examples",
    )
    _assert_semantic_fragments(
        route_workflow,
        "parameter sweep",
        "derived model",
        "active milestone override",
        "generic health checks",
        "Exactly one recommendation",
        "compound",
        "ordered command sequence",
        context="route workflow physics and compound recommendation semantics",
    )

    _assert_public_fragments(
        route_command,
        'argument-hint: "[--frozen=yes|no] [--change=extend|revise] [--layer=new|change]"',
        context="route command public argument hint",
    )
    _assert_semantic_fragments(
        route_command,
        "included route workflow",
        "One recommendation",
        "compound recommendations",
        "required commands in order",
        context="route command workflow delegation",
    )
    _assert_public_fragments(
        help_workflow,
        "ordered compound sequence `gpd:complete-milestone` then `gpd:new-milestone`",
        context="help route compound recommendation example",
    )


def test_phase_lifecycle_workflows_fail_closed_on_dirty_state_and_stale_verification() -> None:
    plan_phase = _workflow_authority_text("plan-phase")
    autonomous = _autonomous_authority_text()

    _assert_semantic_fragments(
        plan_phase,
        "Dirty worktree safety gate",
        "project worktree",
        "dirty paths",
        "never stashes",
        "resets",
        "cleans",
        "overwrites",
        "fail_closed_on_state_conflict",
        "Canonical conflict-stop labels",
        "convention check",
        "route to convention validation",
        context="plan-phase lifecycle gate",
    )

    _assert_semantic_fragments(
        autonomous,
        "Missing, stale",
        "non-passing",
        "blocks lifecycle",
        "gpd:verify-work",
        "COMPLETE_PHASE",
        "missing plan authority",
        context="autonomous lifecycle verification gate",
    )
    _assert_machine_fragments(
        autonomous,
        "gpd --raw validate lifecycle-contract-gate plan-phase",
        context="autonomous lifecycle verification validator",
    )


def test_new_project_customize_settings_matches_supervised_dense_defaults() -> None:
    new_project = (WORKFLOWS_DIR / "new-project" / "workflow-preferences.md").read_text(encoding="utf-8")

    customize = _extract_between(new_project, "<customize_settings>", "</customize_settings>")

    _assert_semantic_concept(
        customize,
        "new-project customize choices keep supervised dense defaults",
        required=(
            "Autonomy: supervised / balanced / yolo",
            "Review cadence: dense / adaptive / sparse",
            "Planning commit docs: true / false",
        ),
        forbidden='Balanced (Recommended)", description: "Routine work is automatic',
        context="new-project customize round-one shape",
    )
    _assert_machine_fragments(
        new_project,
        '"autonomy": "supervised"',
        '"review_cadence": "dense"',
        '"commit_docs": true',
        context="new-project customize supervised dense defaults",
    )


def test_undo_backtrack_hook_collects_complete_backtrack_row_fields() -> None:
    undo_workflow = (WORKFLOWS_DIR / "undo.md").read_text(encoding="utf-8")
    record_workflow = (WORKFLOWS_DIR / "record-backtrack.md").read_text(encoding="utf-8")
    record_command = (COMMANDS_DIR / "record-backtrack.md").read_text(encoding="utf-8")

    assert "--phase=<NN-slug>" in record_command

    record_parse_step = _extract_between(
        record_workflow,
        '<step name="parse_prefill_args">',
        "</step>",
    )
    record_dedupe_step = _extract_between(
        record_workflow,
        '<step name="check_duplicates">',
        "</step>",
    )
    undo_backtrack_step = _extract_between(
        undo_workflow,
        '<step name="offer_record_backtrack">',
        "</step>",
    )

    assert "--phase=<NN-slug>" in record_parse_step
    assert "Dedupe by exact normalized matching of finalized" in record_dedupe_step
    assert "`phase` + `trigger` + `why_wrong`" in record_dedupe_step
    _assert_machine_fragments(
        undo_backtrack_step,
        "reverted_commit",
        "TARGET_HASH",
        "trigger",
        "TARGET_MSG",
        "phase",
        "INFERRED_PHASE_OR_NULL",
        "`stage`",
        "`produced`",
        "`why_wrong`",
        "`counter_action`",
        "`category`",
        "`confidence`",
        "`promote`",
        context="undo backtrack structured row fields",
    )
    _assert_semantic_fragments(
        undo_backtrack_step,
        "structured arguments",
        "not a shell-shaped string",
        "do not interpolate it into shell-shaped args",
        "remaining required row fields",
        context="undo backtrack shell-safe structured args",
    )
    assert "prompts the user only for `why_wrong`" not in undo_backtrack_step


def test_changed_continuation_surfaces_do_not_reintroduce_session_as_authority() -> None:
    checked_surfaces = {
        "execute-plan": (WORKFLOWS_DIR / "execute-plan.md").read_text(encoding="utf-8"),
        "resume-work": _workflow_authority_text("resume-work"),
        "checkpoints": (REFERENCES_DIR / "orchestration" / "checkpoints.md").read_text(encoding="utf-8"),
        "github-lifecycle": (REFERENCES_DIR / "execution" / "github-lifecycle.md").read_text(encoding="utf-8"),
        "state-machine": (TEMPLATES_DIR / "state-machine.md").read_text(encoding="utf-8"),
        "help": (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8"),
    }
    stale_phrases = (
        "`session` record are discovery surfaces",
        "`session` and STATE.md are projection surfaces",
        "`session` continuity mirror",
        "`session` fields should mirror",
        "session info reflect the latest work",
        "session fields, or the derived head",
        "canonical session handoff",
        "STATE.md (Session section)",
        "mirrored STATE.md session continuity entry",
    )

    for name, text in checked_surfaces.items():
        for phrase in stale_phrases:
            assert phrase not in text, f"{name} reintroduced stale session-authority wording: {phrase}"


def test_autonomous_success_criteria_stay_provider_neutral_and_current() -> None:
    autonomous = _autonomous_authority_text()
    success_criteria = _success_criteria_sections(autonomous)

    assert "current `gpd` surfaces" in success_criteria or "runtime-installed child commands" in success_criteria
    assert "canonical `GPD/` paths" in success_criteria or "GPD/CONVENTIONS.md" in autonomous
    assert "runtime/provider-neutral" in success_criteria

    for stale_fragment in ("gsd-tools.cjs", ".planning/", "provider-specific features"):
        assert stale_fragment not in success_criteria
    for provider_literal in ("Anthropic", "OpenAI"):
        assert provider_literal not in success_criteria
