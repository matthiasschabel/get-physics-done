"""Prompt/schema visibility assertions for approved-mode project-contract grounding."""

from __future__ import annotations

from pathlib import Path

from gpd.adapters.install_utils import expand_at_includes
from tests.assertion_taxonomy_support import FragmentMode, forbidden_duplicate, machine_exact, semantic_anchor
from tests.markdown_test_support import extract_markdown_section

REPO_ROOT = Path(__file__).resolve().parents[2]
NEW_PROJECT = REPO_ROOT / "src" / "gpd" / "specs" / "workflows" / "new-project.md"
PROJECT_CONTRACT_SCHEMA = REPO_ROOT / "src" / "gpd" / "specs" / "templates" / "project-contract-schema.md"
STATE_SCHEMA = REPO_ROOT / "src" / "gpd" / "specs" / "templates" / "state-json-schema.md"
QUESTIONING = REPO_ROOT / "src" / "gpd" / "specs" / "references" / "research" / "questioning.md"
NEW_PROJECT_M15_SECTION = "#### M1.5. Synthesize And Approve The Scoping Contract"
NEW_PROJECT_STEP4_SECTION = "## 4. Synthesize The Approved Project Contract And Write PROJECT.md"
PROJECT_CONTRACT_OWNER = "project-contract visibility"


def _expanded(path: Path) -> str:
    return expand_at_includes(path.read_text(encoding="utf-8"), REPO_ROOT / "src/gpd/specs", "/runtime/")


def _assert_prompt_contracts(text: str, *assertions) -> None:
    for assertion in assertions:
        assertion.check(text)


def _extract_contract_rule_block_lines(text: str, start_marker: str) -> tuple[str, ...]:
    section = extract_markdown_section(
        text,
        NEW_PROJECT_M15_SECTION,
        context="new-project minimal contract approval section",
    )
    lines = section.splitlines()
    start = lines.index(start_marker)
    bullets: list[str] = []
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if stripped.startswith("- "):
            bullets.append(stripped)
            continue
        if bullets and stripped:
            break
    return tuple(bullets)


def test_new_project_prompt_surfaces_the_canonical_contract_schema_for_project_contract_grounding() -> None:
    new_project_text = NEW_PROJECT.read_text(encoding="utf-8")
    parse_line = next(line for line in new_project_text.splitlines() if line.startswith("Parse JSON for:"))

    _assert_prompt_contracts(
        new_project_text,
        machine_exact(
            "canonical schema source remains visible",
            ("templates/project-contract-schema.md", "`project_contract`"),
            owner=PROJECT_CONTRACT_OWNER,
            rationale="new-project must author the object governed by the canonical schema path",
            section=NEW_PROJECT_M15_SECTION,
        ),
        semantic_anchor(
            "approval authors a literal project_contract object",
            (
                "literal JSON object",
                "`project_contract` subsection",
                "canonical source of truth",
                "approval-critical reminders",
            ),
            section=NEW_PROJECT_M15_SECTION,
        ),
        semantic_anchor(
            "approval preserves decisive user guidance",
            (
                "decisive outputs",
                "anchors",
                "prior outputs",
                "review/stop triggers",
                "generic placeholders",
            ),
            section=NEW_PROJECT_M15_SECTION,
        ),
        semantic_anchor(
            "raw approval gate contract follows canonical schema",
            (
                "raw contract as a literal JSON object",
                "not the surrounding `state.json` envelope",
                "`project_contract` object rules",
                "exact keys",
                "enum values",
                "list/object shapes",
                "ID-linkage rules",
                "proof-bearing claim requirements",
                "near-miss enum values",
                "scalar shortcuts",
                "fix them to the schema before approval",
            ),
            section=NEW_PROJECT_M15_SECTION,
        ),
        machine_exact(
            "contract shape and boolean keys stay exact",
            (
                "`context_intake`",
                "`approach_policy`",
                "`uncertainty_markers`",
                "`schema_version`",
                "`references[].must_surface`",
                "`true`",
                "`false`",
                "references[]",
            ),
            owner=PROJECT_CONTRACT_OWNER,
            rationale="schema keys and JSON boolean values are machine contracts",
            section=NEW_PROJECT_M15_SECTION,
        ),
        semantic_anchor(
            "approval-state diagnostics are preserved",
            (
                "`project_contract_load_info`",
                "`project_contract_validation`",
                "preserve that state",
                "approval gate",
                "visible-but-blocked contract",
            ),
            section=NEW_PROJECT_M15_SECTION,
        ),
        semantic_anchor(
            "stale inlined schema prose stays absent",
            (
                "the contract schema is closed: do not add invented top-level or nested keys",
                "list fields must stay lists even for single-item values",
                "blank or duplicate list entries are invalid after trimming whitespace",
            ),
            mode=FragmentMode.ABSENT,
        ),
    )
    assert "project_contract_load_info" in new_project_text
    assert "project_contract_validation" in new_project_text

    machine_exact(
        "scope-intake manifest fields parsed exactly",
        tuple(
            f"`{field}`"
            for field in (
                "commit_docs",
                "autonomy",
                "research_mode",
                "project_exists",
                "state_exists",
                "roadmap_exists",
                "recoverable_project_exists",
                "partial_project_exists",
                "project_recovery_status",
                "init_progress_status",
                "has_research_map",
                "planning_exists",
                "has_research_files",
                "research_file_samples",
                "has_project_manifest",
                "needs_research_map",
                "has_git",
                "platform",
                "project_contract",
                "project_contract_gate",
                "project_contract_load_info",
                "project_contract_validation",
            )
        ),
        owner=PROJECT_CONTRACT_OWNER,
        rationale="scope-intake manifest field names are parsed from init JSON",
        context="new-project Parse JSON line",
    ).check(parse_line)
    machine_exact(
        "scope-intake parse line omits late model selectors",
        ("`researcher_model`", "`synthesizer_model`"),
        owner=PROJECT_CONTRACT_OWNER,
        rationale="post-scope model selectors must not be parsed from scope-intake init JSON",
        mode=FragmentMode.ABSENT,
        context="new-project Parse JSON line",
    ).check(parse_line)
    for field in (
        "`researcher_model`",
        "`synthesizer_model`",
        "`roadmapper_model`",
    ):
        assert field in new_project_text
    machine_exact(
        "post-scope init command stays exact",
        "POST_SCOPE_INIT=$(gpd --raw init new-project --stage post_scope)",
        owner=PROJECT_CONTRACT_OWNER,
        rationale="late model selection uses this exact raw init command",
    ).check(new_project_text)
    semantic_anchor(
        "stale continuation wording stays absent",
        "preserve any init-surfaced `project_contract`, `project_contract_load_info`, and "
        "`project_contract_validation` state while deciding whether this is fresh work or a continuation",
        mode=FragmentMode.ABSENT,
    ).check(new_project_text)


def test_new_project_contract_rule_block_is_not_duplicated() -> None:
    new_project_text = NEW_PROJECT.read_text(encoding="utf-8")
    show_block = _extract_contract_rule_block_lines(
        new_project_text,
        "Before you show the approval gate, build the raw contract as a literal JSON object for the `project_contract` subsection of `templates/project-contract-schema.md`:",
    )

    _assert_prompt_contracts(
        new_project_text,
        forbidden_duplicate(
            "raw approval contract rule appears once",
            "Before you show the approval gate, build the raw contract as a literal JSON object",
        ),
        forbidden_duplicate(
            "pre-approval literal contract reminder appears once",
            "Before you ask for approval, keep the contract as a literal JSON object",
        ),
        semantic_anchor(
            "step 4 delegates to the M1.5 scoping-contract procedure",
            (
                "Use the scoping-contract procedure from Step M1.5",
                "same blocking fields",
                "preservation rules",
                "schema discipline",
                "approval options",
                "validation command",
                "`gpd state set-project-contract -`",
                "Do not define a second scoping-contract variant here.",
            ),
            section=NEW_PROJECT_STEP4_SECTION,
        ),
        machine_exact(
            "step 4 does not revive stale approval-card fields",
            ("`scope.question`", "`context_intake.must_read_refs`", 'header: "Scope"'),
            owner=PROJECT_CONTRACT_OWNER,
            rationale="stale schema/card fragments would create a second contract variant",
            mode=FragmentMode.ABSENT,
            section=NEW_PROJECT_STEP4_SECTION,
        ),
    )
    assert any("context_intake" in line and "uncertainty_markers" in line for line in show_block)
    assert any("schema_version" in line and "must_surface" in line for line in show_block)


def test_project_contract_schema_slice_keeps_contract_critical_rules_visible() -> None:
    contract_schema_text = _expanded(PROJECT_CONTRACT_SCHEMA)

    _assert_prompt_contracts(
        contract_schema_text,
        semantic_anchor(
            "schema slice is project-contract-only",
            (
                "Canonical schema",
                "`project_contract` object",
                "`GPD/state.json`",
                "model-facing contract setup",
                "only the `project_contract` shape and rules",
            ),
            section="# Project Contract Schema",
        ),
        semantic_anchor(
            "object sections stay objects",
            (
                "`context_intake`",
                "`approach_policy`",
                "`uncertainty_markers`",
                "JSON objects",
                "not collapse them to strings or lists",
            ),
            section="## Contract Rules",
        ),
        machine_exact(
            "project-contract schema machine fields stay exact",
            ("`schema_version` must be the integer `1`.", "`must_surface` is a boolean scalar.", "`true`", "`false`"),
            owner=PROJECT_CONTRACT_OWNER,
            rationale="schema version and must_surface boolean literals are validator-facing",
            section="## Contract Rules",
        ),
    )


def test_state_schema_surfaces_the_exact_approved_mode_grounding_rule() -> None:
    state_schema_text = _expanded(STATE_SCHEMA)

    _assert_prompt_contracts(
        state_schema_text,
        semantic_anchor(
            "approved mode requires concrete grounding",
            (
                "approved project contract requires",
                "concrete anchor/reference/prior-output/baseline",
                "explicit missing-anchor notes preserve uncertainty",
                "do not satisfy approval on their own",
            ),
        ),
        semantic_anchor(
            "prior outputs require concrete project-root resolution",
            (
                "`must_include_prior_outputs[]`",
                "explicit project-artifact paths or filenames",
                "current project root",
                "`project_root` is unavailable",
                "non-grounding",
                "concrete root",
            ),
            section="### Shared Grounding And Linkage Rules",
        ),
        machine_exact(
            "approved-mode example and validator command stay exact",
            (
                '"must_include_prior_outputs": ["GPD/phases/00-baseline/00-01-SUMMARY.md"]',
                "gpd --raw validate project-contract - --mode approved",
            ),
            owner=PROJECT_CONTRACT_OWNER,
            rationale="examples and CLI command are executable/user-facing contracts",
        ),
        machine_exact(
            "wildcard prior-output examples stay absent",
            ("`GPD/phases/.../*-SUMMARY.md` or `paper/main.tex`", "`GPD/phases/.../SUMMARY.md`"),
            owner=PROJECT_CONTRACT_OWNER,
            rationale="wildcards would make non-concrete paths appear valid",
            mode=FragmentMode.ABSENT,
        ),
        semantic_anchor(
            "anchor text alone is insufficient",
            (
                "`user_asserted_anchors[]`",
                "`known_good_baselines[]`",
                "concrete, re-findable handle",
                "Multi-word prose alone does not count.",
            ),
        ),
        semantic_anchor(
            "stale multi-word grounding heuristic stays absent",
            "should use at least three words and name a concrete benchmark",
            mode=FragmentMode.ABSENT,
        ),
        machine_exact(
            "project-contract object shape and boolean rules stay exact",
            (
                "`context_intake`",
                "`approach_policy`",
                "`uncertainty_markers`",
                "`schema_version` must be the integer `1`.",
                "`must_surface` is a boolean scalar.",
                "`true`",
                "`false`",
                "`context_intake` must not be empty.",
            ),
            owner=PROJECT_CONTRACT_OWNER,
            rationale="schema keys, integer schema version, and JSON boolean literals are validator-facing",
        ),
        machine_exact(
            "proof-bearing claim schema fields stay exact",
            (
                '"claim_kind"',
                '"observables[]"',
                '"deliverables[]"',
                '"acceptance_tests[]"',
                '"references[]"',
                '"parameters[]"',
                '"hypotheses[]"',
                '"quantifiers[]"',
                '"conclusion_clauses[]"',
                '"proof_deliverables[]"',
                "claims[].proof_deliverables[]",
                "`claims[].parameters[]`",
                "`claims[].hypotheses[]`",
                "`claims[].conclusion_clauses[]`",
                "`claims[].acceptance_tests[]`",
            ),
            owner=PROJECT_CONTRACT_OWNER,
            rationale="proof-bearing claim field names and array paths are machine schema contracts",
        ),
        semantic_anchor(
            "project contract claim kind does not inherit peer-review ClaimRecord meaning",
            (
                "`ProjectContract`",
                "`project_contract.claims[]`",
                "`ContractClaim`",
                "`claim_kind` is `theorem`, `lemma`, `corollary`, `proposition`, or `claim`",
                "Do not import the staged peer-review Paper `ClaimRecord` meaning",
            ),
        ),
        semantic_anchor(
            "theorem-like proof obligations remain visible",
            (
                "the statement is theorem-like",
                "`prove/show that`",
                "`for all` / `exists`",
                "any proof field is already populated",
                "`proof_obligation` target",
                "quantifiers",
                "explicit quantifier or domain obligation",
                "proof-specific test kind",
            ),
        ),
        semantic_anchor(
            "placeholder grounding is rejected",
            (
                "already exists inside the current project root",
                "Placeholder or `TBD` text does not count",
                "do not satisfy approved-mode grounding on their own",
            ),
        ),
    )


def test_new_project_and_questioning_gate_do_not_treat_missing_anchor_notes_as_approval_ready_grounding() -> None:
    new_project_text = NEW_PROJECT.read_text(encoding="utf-8")
    questioning_text = QUESTIONING.read_text(encoding="utf-8")

    _assert_prompt_contracts(
        new_project_text,
        semantic_anchor(
            "new-project approval waits for real grounding",
            (
                "At least one concrete anchor, reference, prior-output constraint, or baseline",
                "decisive anchor is still unknown",
                "keep that blocker explicit",
                "Missing-anchor notes preserve uncertainty",
                "do not satisfy approval on their own",
                "Do not offer approval",
                "must ground approval or be carried forward",
            ),
            section=NEW_PROJECT_M15_SECTION,
        ),
        machine_exact(
            "approved-mode validation command remains visible",
            "gpd --raw validate project-contract - --mode approved",
            owner=PROJECT_CONTRACT_OWNER,
            rationale="scope approval must call the approved-mode validator exactly",
            section=NEW_PROJECT_M15_SECTION,
        ),
    )
    _assert_prompt_contracts(
        questioning_text,
        machine_exact(
            "questioning gate preserves schema shape warnings",
            (
                "do not invent extra keys or collapse list fields into scalars",
                "Array fields stay arrays, even for singletons",
            ),
            owner=PROJECT_CONTRACT_OWNER,
            rationale="questioning gate must not suggest invalid contract shape shortcuts",
        ),
        semantic_anchor(
            "questioning gate missing-anchor notes are not approval grounding",
            (
                "blank or duplicate list items",
                "at least one concrete anchor, reference, prior output, or baseline",
                "decisive anchor is still unknown",
                "explicit missing-anchor note",
                "do not replace the requirement",
            ),
        ),
    )
