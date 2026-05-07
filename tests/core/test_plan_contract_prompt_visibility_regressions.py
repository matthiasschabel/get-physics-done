from __future__ import annotations

import re
from pathlib import Path

from gpd.adapters.install_utils import expand_at_includes
from gpd.core.strict_yaml import load_strict_yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "src/gpd/agents"
TEMPLATES_DIR = REPO_ROOT / "src/gpd/specs/templates"


def _read_template(name: str) -> str:
    return (TEMPLATES_DIR / name).read_text(encoding="utf-8")


def _expanded_template(name: str) -> str:
    return expand_at_includes(_read_template(name), REPO_ROOT / "src/gpd/specs", "/runtime/")


def _section(text: str, heading: str) -> str:
    match = re.search(rf"^(?P<level>#+)\s+{re.escape(heading)}\s*$", text, flags=re.MULTILINE)
    assert match is not None, f"missing markdown heading: {heading}"

    heading_level = len(match.group("level"))
    next_heading = re.search(rf"^#{{1,{heading_level}}}\s+", text[match.end() :], flags=re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(text)
    return text[match.end() : end]


def _tagged_section(text: str, tag: str) -> str:
    start = f"<{tag}>"
    end = f"</{tag}>"
    assert start in text, f"missing start tag: {start}"
    assert end in text, f"missing end tag: {end}"
    return text.split(start, 1)[1].split(end, 1)[0]


def _contains_all(text: str, tokens: tuple[str, ...]) -> None:
    missing = [token for token in tokens if token not in text]
    assert not missing, f"missing expected tokens: {missing}"


def _fenced_blocks(text: str, language: str) -> list[str]:
    fence_pattern = re.compile(r"```(?P<language>[^\n]*)\n(?P<body>.*?)\n```", flags=re.DOTALL)
    return [
        match.group("body")
        for match in fence_pattern.finditer(text)
        if match.group("language").strip().split()[:1] == [language]
    ]


def _single_yaml_fence(text: str) -> object:
    blocks = _fenced_blocks(text, "yaml")
    assert len(blocks) == 1
    return load_strict_yaml(blocks[0])


def _as_mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value


def _as_list(value: object) -> list[object]:
    assert isinstance(value, list)
    return value


def _first_mapping(value: object) -> dict[str, object]:
    items = _as_list(value)
    assert len(items) == 1
    return _as_mapping(items[0])


def test_plan_contract_schema_surfaces_defaultable_semantic_fields_and_hard_constraints() -> None:
    plan_schema = _expanded_template("plan-contract-schema.md")

    schema_version_example = _as_mapping(_single_yaml_fence(_section(plan_schema, "`schema_version`")))
    scope_example = _as_mapping(_as_mapping(_single_yaml_fence(_section(plan_schema, "`scope`")))["scope"])
    context_intake_example = _as_mapping(
        _as_mapping(_single_yaml_fence(_section(plan_schema, "`context_intake`")))["context_intake"]
    )
    approach_policy_example = _as_mapping(
        _as_mapping(_single_yaml_fence(_section(plan_schema, "`approach_policy`")))["approach_policy"]
    )
    observables_example = _first_mapping(_single_yaml_fence(_section(plan_schema, "`observables[]`")))
    references_example = _first_mapping(_single_yaml_fence(_section(plan_schema, "`references[]`")))
    links_example = _first_mapping(_single_yaml_fence(_section(plan_schema, "`links[]`")))
    required_shape = _section(plan_schema, "Required Shape")
    context_intake_rules = _section(plan_schema, "`context_intake`")
    approach_policy_rules = _section(plan_schema, "`approach_policy`")
    references_rules = _section(plan_schema, "`references[]`")
    links_rules = _section(plan_schema, "`links[]`")
    alignment_rules = _section(plan_schema, "Contract Alignment Rules")

    assert "observables[].kind" in plan_schema
    assert "deliverables[].kind" in plan_schema
    assert "acceptance_tests[].kind" in plan_schema
    assert "references[].kind" in plan_schema
    assert "references[].role" in plan_schema
    assert "links[].relation" in plan_schema
    assert "their default is `other`" in plan_schema

    assert schema_version_example == {"schema_version": 1}
    assert scope_example["in_scope"] == ["Recover the benchmark curve within tolerance"]
    assert isinstance(scope_example["in_scope"], list)
    assert context_intake_example["must_read_refs"] == ["ref-main"]
    assert context_intake_example["must_include_prior_outputs"] == ["GPD/phases/00-baseline/00-01-SUMMARY.md"]
    assert isinstance(context_intake_example["must_include_prior_outputs"], list)
    assert isinstance(approach_policy_example["formulations"], list)
    assert observables_example["kind"] == "scalar"
    assert references_example["kind"] == "paper"
    assert references_example["role"] == "benchmark"
    assert references_example["must_surface"] is True
    assert references_example["required_actions"] == ["read", "compare", "cite", "avoid"]
    assert links_example["relation"] == "supports"

    _contains_all(
        required_shape,
        (
            "`schema_version`",
            "integer `1`",
            "`scope`",
            "`context_intake`",
            "`approach_policy`",
            "`uncertainty_markers`",
            "YAML object",
            "not strings or lists",
            "hard grounding/anchor requirement",
        ),
    )
    _contains_all(
        context_intake_rules,
        (
            "`contract.context_intake`",
            "required",
            "non-empty object",
            "not a string or list",
            "Use concrete anchors",
            "`must_read_refs[]`",
            "`must_include_prior_outputs[]`",
            "`user_asserted_anchors[]`",
            "`known_good_baselines[]`",
        ),
    )
    _contains_all(
        approach_policy_rules,
        (
            "`approach_policy`",
            "YAML object",
            "not a string or list",
            "does not count as grounding",
            "`context_intake`",
            "preserved scoping inputs",
            "`references[]`",
        ),
    )
    _contains_all(
        references_rules,
        (
            "`kind`",
            "`role`",
            "`must_surface`",
            "boolean scalar",
            "`true`",
            "`false`",
            "synonyms",
            "`required_actions`",
            "`applies_to[]`",
            "concrete enough to re-find later",
        ),
    )
    assert "Proof-bearing claims must use an explicit non-`other` `claim_kind`" in plan_schema
    _contains_all(
        links_rules,
        (
            "`source`",
            "`target`",
            "declared observable",
            "claim",
            "deliverable",
            "acceptance-test",
            "reference",
            "forbidden-proxy",
            "link IDs",
        ),
    )
    _contains_all(
        alignment_rules,
        (
            "`references[]`",
            "`context_intake`",
            "preserved scoping inputs",
            "`must_surface: true`",
            "concrete grounding",
            "warning",
            "not a blocker",
        ),
    )
    assert (
        "For non-scoping plans, `claims[]`, `deliverables[]`, `acceptance_tests[]`, and `forbidden_proxies[]` are all required."
        in plan_schema
    )


def test_planner_prompt_surfaces_default_salvage_and_specific_semantics() -> None:
    planner_prompt = _read_template("planner-subagent-prompt.md")

    assert planner_prompt.count("## Standard Planning Template") == 1
    assert planner_prompt.count("## Revision Template") == 1
    assert planner_prompt.count("@{GPD_INSTALL_DIR}/templates/plan-contract-schema.md") == 1
    assert "**Project Contract Gate:** {project_contract_gate}" in planner_prompt
    assert "**Project Contract Load Info:** {project_contract_load_info}" in planner_prompt
    assert "**Project Contract Validation:** {project_contract_validation}" in planner_prompt
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
    assert "Do not silently branch or widen scope." in planner_prompt
    assert "`tool_requirements` pass `gpd validate plan-preflight <PLAN.md>`" in planner_prompt
    assert "Proof-bearing plans keep proof artifacts and sibling `*-PROOF-REDTEAM.md` audits explicit" in planner_prompt
    assert "The contract still exposes defaultable semantic fields" not in planner_prompt
    assert "Stale proof review gate" not in planner_prompt


def test_planner_and_checker_examples_surface_concrete_contract_anchors() -> None:
    planner_prompt = (REPO_ROOT / "src/gpd/agents/gpd-planner.md").read_text(encoding="utf-8")
    checker_prompt = (REPO_ROOT / "src/gpd/agents/gpd-plan-checker.md").read_text(encoding="utf-8")
    checker_contract_gate = _section(checker_prompt, "Dimension 0: Contract Gate")

    assert 'in_scope: ["Recover the benchmark curve within tolerance"]' in planner_prompt
    assert "claim_kind: theorem" in planner_prompt
    assert 'parameters -> symbol "q"' in planner_prompt
    assert "hypotheses -> hyp-gauge" in planner_prompt
    assert "conclusion_clauses -> concl-transverse" in planner_prompt
    assert "GPD/phases/01-vacuum-polarization/01-01-SUMMARY.md" in planner_prompt
    assert "GPD/phases/00-baseline/00-01-SUMMARY.md#gauge-and-tensor-convention" in planner_prompt
    assert "schema_version: 1" in checker_prompt
    assert 'in_scope: ["Recover the benchmark value within tolerance"]' in checker_prompt
    assert "claim_kind: theorem" in checker_prompt
    assert "parameters:" in checker_prompt
    assert "- symbol: k" in checker_prompt
    assert 'domain_or_type: "dimensionless"' in checker_prompt
    assert "aliases: [kappa]" in checker_prompt
    assert "required_in_proof: true" in checker_prompt
    assert "hypotheses:" in checker_prompt
    assert "- id: hyp-normalization" in checker_prompt
    assert 'text: "Reference normalization and tolerance convention match Ref-01"' in checker_prompt
    assert "symbols: [k]" in checker_prompt
    assert "category: assumption" in checker_prompt
    assert "conclusion_clauses:" in checker_prompt
    assert "- id: concl-benchmark" in checker_prompt
    assert 'text: "Benchmark agreement stays within tolerance at every approved sample"' in checker_prompt
    assert "proof_deliverables: [deliv-proof-main]" in checker_prompt
    assert "parameters: [k]" not in checker_prompt
    assert 'hypotheses: ["Reference normalization and tolerance convention match Ref-01"]' not in checker_prompt
    assert (
        'conclusion_clauses: ["Benchmark agreement stays within tolerance at every approved sample"]'
        not in checker_prompt
    )
    _contains_all(
        checker_contract_gate,
        (
            "stable knowledge docs",
            "shared reference context",
            "reviewed background syntheses",
            "do not override",
            "`convention_lock`",
            "`project_contract`",
            "PLAN `contract`",
            "`contract_results`",
            "`comparison_verdicts`",
            "proof-review artifacts",
            "direct benchmark/result evidence",
        ),
    )
    assert "GPD/phases/00-baseline/00-01-SUMMARY.md" in checker_prompt
    assert "GPD/phases/00-baseline/00-01-SUMMARY.md#gauge-unit-and-notation-conventions" in checker_prompt


def test_plan_checker_prompt_surfaces_direct_schema_visibility_and_read_only_authority() -> None:
    checker_prompt = (AGENTS_DIR / "gpd-plan-checker.md").read_text(encoding="utf-8")

    assert checker_prompt.count("@{GPD_INSTALL_DIR}/templates/plan-contract-schema.md") >= 2
    assert "{GPD_INSTALL_DIR}/references/shared/shared-protocols.md" in checker_prompt
    assert "@{GPD_INSTALL_DIR}/references/shared/shared-protocols.md" not in checker_prompt
    assert "Apply `{GPD_INSTALL_DIR}/references/orchestration/continuation-boundary.md` for one-shot handoff semantics." in checker_prompt
    assert "If user input is needed, return the typed checkpoint and stop." in checker_prompt
    assert "artifact_write_authority: read_only" in checker_prompt
    assert "file_write" not in checker_prompt
    assert "approved_plans:" in checker_prompt
    assert '    - "04-01"' in checker_prompt
    assert "blocked_plans: []" in checker_prompt
    assert "GPD/phases/00-baseline/00-01-SUMMARY.md" in checker_prompt
    assert "GPD/phases/00-baseline/00-01-SUMMARY.md#gauge-unit-and-notation-conventions" in checker_prompt
    assert "GPD/phases/00-baseline/00-01-SUMMARY.md#gauge-and-tensor-convention" in checker_prompt
    assert "GPD/phases/01-vacuum-polarization/01-01-SUMMARY.md" in checker_prompt


def test_phase_prompt_surfaces_default_salvage_and_hard_plan_requirements() -> None:
    phase_prompt = _read_template("phase-prompt.md")

    assert phase_prompt.count("Quick contract rules:") == 1
    assert phase_prompt.count("@{GPD_INSTALL_DIR}/templates/plan-contract-schema.md") == 1
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


def test_contract_schema_docs_make_lowercase_closed_vocab_rule_model_visible() -> None:
    plan_schema = _expanded_template("plan-contract-schema.md")
    project_schema = _expanded_template("project-contract-schema.md")
    state_schema = _expanded_template("state-json-schema.md")

    expected = "Case drift such as `Theorem`, `Benchmark`, or `Read` fails strict validation."

    assert expected in plan_schema
    assert expected in project_schema
    assert expected in state_schema


def test_planner_prompt_stays_compact_while_preserving_canonical_contract_wiring() -> None:
    planner_prompt = (REPO_ROOT / "src/gpd/agents/gpd-planner.md").read_text(encoding="utf-8")
    planner_role = planner_prompt.partition("</role>")[0]

    assert 'parameters -> symbol "q"' in planner_prompt
    assert "hypotheses -> hyp-gauge" in planner_prompt
    assert "conclusion_clauses -> concl-transverse" in planner_prompt
    assert 'parameters: ["q"]' not in planner_prompt
    assert 'hypotheses: ["Gauge-fixing and regularization conventions match the approved anchor"]' not in planner_prompt
    assert 'conclusion_clauses: ["q_mu Pi^{mu nu} = 0"]' not in planner_prompt
    assert "15-20%" not in planner_prompt
    assert "Context %" not in planner_prompt
    assert "No plan-checker" not in planner_prompt
    assert "The system starts broad and narrows automatically." not in planner_prompt
    assert "approach_validated: true" not in planner_prompt
    assert planner_prompt.count("| **YOLO** |") == 1
    assert "<worked_examples>" not in planner_prompt
    assert "<goal_backward>" not in planner_prompt
    assert "Worked Examples: Complete PLAN.md Files" not in planner_prompt
    assert "Goal-Backward Methodology for Physics" not in planner_prompt
    assert "tool_requirements[].id" in planner_prompt
    assert "must be unique within the list" in planner_prompt
    assert 'in_scope: ["Recover the benchmark curve within tolerance"]' in planner_prompt
    assert "claim_kind: theorem" in planner_prompt
    assert 'proof_deliverables: ["deliv-proof-vac-pol"]' in planner_prompt
    assert "GPD/phases/00-baseline/00-01-SUMMARY.md#gauge-and-tensor-convention" in planner_prompt
    assert "GPD/phases/01-vacuum-polarization/01-01-SUMMARY.md" in planner_prompt
    assert "@{GPD_INSTALL_DIR}/workflows/execute-plan.md" not in planner_role
    assert "@{GPD_INSTALL_DIR}/templates/summary.md" not in planner_role
    assert "@{GPD_INSTALL_DIR}/references/protocols/order-of-limits.md" not in planner_role


def test_proof_obligation_planning_surfaces_require_claim_audit_and_stale_review_gate() -> None:
    plan_schema = _read_template("plan-contract-schema.md")
    planner_prompt = _read_template("planner-subagent-prompt.md")
    phase_prompt = _read_template("phase-prompt.md")
    observables_rules = _section(plan_schema, "`observables[]`")
    planner_contract_rules = _tagged_section(planner_prompt, "contract_visibility_requirements")
    phase_quick_rules = phase_prompt.split("Quick contract rules:", 1)[1].split("---", 1)[0]

    assert "kind: scalar|curve|map|classification|proof_obligation|other" in plan_schema
    _contains_all(
        observables_rules,
        (
            "`kind`",
            "proof_obligation",
            "`definition`",
            "theorem/result",
            "hypotheses",
            "parameter regime",
            "body prose",
        ),
    )

    _contains_all(
        planner_contract_rules,
        (
            "proof-bearing work",
            "explicit non-`other` `claim_kind`",
            "auditable hypotheses",
            "quantified variables",
            "named parameters",
        ),
    )
    assert "**Proof claim audit:**" not in planner_prompt
    assert "**Stale proof review gate:**" not in planner_prompt

    _contains_all(
        phase_quick_rules,
        (
            "proof-bearing work",
            "explicit non-`other` `claim_kind`",
            "hypotheses",
            "parameters",
            "conclusions auditable",
            "`observables[].kind: proof_obligation`",
            "theorem or claim",
            "parameter regime",
            "proof audit",
            "stale",
            "`status: passed`",
        ),
    )


def test_planner_gap_closure_example_keeps_execute_type_and_required_contract_block() -> None:
    planner_prompt = (REPO_ROOT / "src/gpd/agents/gpd-planner.md").read_text(encoding="utf-8")
    gap_closure_mode = _tagged_section(planner_prompt, "gap_closure_mode")
    gap_closure_example = _as_mapping(_single_yaml_fence(gap_closure_mode))
    contract = _as_mapping(gap_closure_example["contract"])
    scope = _as_mapping(contract["scope"])
    context_intake = _as_mapping(contract["context_intake"])
    claims = _as_list(contract["claims"])
    deliverables = _as_list(contract["deliverables"])
    acceptance_tests = _as_list(contract["acceptance_tests"])
    forbidden_proxies = _as_list(contract["forbidden_proxies"])
    uncertainty_markers = _as_mapping(contract["uncertainty_markers"])

    _contains_all(
        gap_closure_mode,
        (
            "`type: execute`",
            "`gap_closure: true`",
            "verification",
            "repair marker",
            "PLAN.md",
            "failed verification",
            "new passing check",
        ),
    )
    assert "type: gap_closure" not in gap_closure_mode
    assert gap_closure_example["gap_closure"] is True
    assert set(contract) == {
        "schema_version",
        "scope",
        "context_intake",
        "claims",
        "deliverables",
        "acceptance_tests",
        "forbidden_proxies",
        "uncertainty_markers",
    }
    assert contract["schema_version"] == 1
    assert isinstance(scope["question"], str)
    assert scope["in_scope"] == ["Repair the failed verification for the published benchmark comparison"]
    assert context_intake["must_include_prior_outputs"] == ["GPD/phases/XX-name/XX-NN-SUMMARY.md"]
    assert isinstance(context_intake["must_include_prior_outputs"], list)
    assert isinstance(context_intake["crucial_inputs"], list)

    assert len(claims) == 1
    claim = _as_mapping(claims[0])
    assert claim["claim_kind"] == "other"
    assert claim["deliverables"] == ["deliv-gap-fix"]
    assert claim["acceptance_tests"] == ["test-gap-fix"]

    assert len(deliverables) == 1
    deliverable = _as_mapping(deliverables[0])
    assert deliverable["kind"] == "report"
    assert deliverable["path"] == "GPD/phases/XX-name/XX-NN-SUMMARY.md"

    assert len(acceptance_tests) == 1
    acceptance_test = _as_mapping(acceptance_tests[0])
    assert acceptance_test["subject"] == "claim-gap-fix"
    assert acceptance_test["kind"] == "other"
    assert acceptance_test["evidence_required"] == ["deliv-gap-fix"]

    assert len(forbidden_proxies) == 1
    forbidden_proxy = _as_mapping(forbidden_proxies[0])
    assert forbidden_proxy["subject"] == "claim-gap-fix"
    assert isinstance(uncertainty_markers["weakest_anchors"], list)
    assert isinstance(uncertainty_markers["disconfirming_observations"], list)
