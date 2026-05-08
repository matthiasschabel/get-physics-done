"""Read-only prompt-surface diagnostics for canonical GPD sources."""

from __future__ import annotations

import ast
import difflib
import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, cast

import yaml

from gpd.adapters.install_utils import (
    DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES,
    build_runtime_cli_bridge_command,
    expand_at_includes,
    parse_at_include_path,
    project_markdown_for_runtime,
    projection_target_dir_from_path_prefix,
    split_markdown_frontmatter,
)
from gpd.adapters.runtime_catalog import (
    get_runtime_descriptor,
    iter_runtime_descriptors,
    normalize_runtime_name,
)
from gpd.core.frontmatter import (
    UNSUPPORTED_FRONTMATTER_FIELDS,
    VERIFICATION_REPORT_STATUSES,
    FrontmatterParseError,
    extract_frontmatter,
    validate_frontmatter,
)
from gpd.core.return_contract import (
    ALLOWED_RETURN_EXTENSION_FIELDS,
    GpdReturnEnvelope,
    validate_gpd_return_markdown,
)
from gpd.core.workflow_staging import (
    WorkflowStage,
    WorkflowStageConditionalAuthority,
    WorkflowStageManifest,
    known_init_fields_for_workflow,
    load_workflow_stage_manifest_from_path,
)

PromptSurfaceKind = Literal["command", "agent", "workflow"]

PROMPT_SURFACE_REPORT_SCHEMA_VERSION = "prompt_surface_diagnostics.v7"
DEFAULT_PATH_PREFIX = "/runtime/"
DEFAULT_SURFACES: tuple[PromptSurfaceKind, ...] = ("command", "agent", "workflow")

_INCLUDED_MARKER_RE = re.compile(r"<!-- \[included: [^\]]+\] -->")
_UNRESOLVED_INCLUDE_RE = re.compile(r"<!-- @ include (?:not resolved|cycle detected|read error|depth limit reached):")
_FENCE_OPEN_RE = re.compile(r"^[ \t]*(?P<marker>`{3,}|~{3,})(?P<info>.*)$")
_SPAWN_CONTRACT_RE = re.compile(
    r"^[ \t]*<spawn_contract(?:_interactive)?>[ \t]*$",
    re.MULTILINE,
)
_SCHEMA_BLOCK_MARKERS = (
    "gpd_return:",
    '"gpd_return"',
    "'gpd_return'",
    "schema_version",
    "contract_results",
    "project_contract",
)
_SCHEMA_FENCE_LANGUAGES = frozenset({"yaml", "yml", "json", "toml"})
_MARKDOWN_FRONTMATTER_FENCE_LANGUAGES = frozenset({"markdown", "md", ""})
_VERIFICATION_FRONTMATTER_KEYS = frozenset(
    {
        "phase",
        "verified",
        "status",
        "score",
        "plan_contract_ref",
        "contract_results",
        "comparison_verdicts",
        "suggested_contract_checks",
    }
)
_VERIFICATION_FRONTMATTER_STRONG_KEYS = frozenset(
    {
        "plan_contract_ref",
        "contract_results",
        "comparison_verdicts",
        "suggested_contract_checks",
    }
)
_GPD_RETURN_EXAMPLE_RE = re.compile(r"(?m)(?:^|[\s{,\[\('\"`])['\"]?gpd_return['\"]?\s*:")
_HARD_GATE_LINE_RE = re.compile(
    r"\b(?:STOP|fail[- ]closed|do not proceed|must|required|never|forbidden|reject|cannot|blocked)\b",
    re.IGNORECASE,
)
_SHELL_PARSING_RE = re.compile(
    r"(?:\bgpd\s+--raw\b|\bjq\b|\bsed\b|\bawk\b|\bgrep\b|\bmktemp\b|\$\(|<<-?|"
    r"^\s*case\b|\bcase\s+.*\bin\b|\bprintf\b|\bcat\s+GPD\b)"
)
_BRIDGE_COMMAND_RE = re.compile(r"(?:gpd\.runtime_cli|\bgpd_cli\s+--raw\b|\bgpd\s+--raw\b)")
_RUNTIME_NOTE_RE = re.compile(
    r"(?:runtime note|runtime bridge|runtime-visible|shared runtime cli bridge|GPD runtime|"
    r"When shell steps call the GPD CLI)",
    re.IGNORECASE,
)
_DUPLICATE_VOCABULARY = (
    "gpd_return",
    "files_written",
    "artifact gate",
    "fail-closed",
    "fail closed",
    "STOP",
    "do not proceed",
    "must not",
    "never",
    "authoritative",
    "frontmatter",
    "schema",
    "validation",
    "checkpoint",
    "blocked",
    "route on",
    "presentation only",
)
_MACHINE_CONTRACT_RE = re.compile(
    r"(?:"
    r"\b[A-Za-z0-9_.{}$-]+/[A-Za-z0-9_./{}$-]+|"
    r"\b[A-Za-z0-9_.-]+\.(?:md|json|ya?ml|toml|tex|pdf|py)\b|"
    r"--[a-z0-9][a-z0-9-]*\b|"
    r"\$gpd-[a-z0-9-]+|"
    r"\bgpd(?:[: -][a-z0-9-]+|_return| --raw)\b|"
    r"\b(?:schema_version|frontmatter|gpd_return|contract_results|files_written|next_actions|project_contract)\b|"
    r"\b[A-Za-z_][A-Za-z0-9_]*(?:\[\])?(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[\])?)+\b|"
    r"@\{GPD_INSTALL_DIR\}|"
    r"<!--\s*@\s*include\b|"
    r"<[A-Za-z][A-Za-z0-9_-]*(?:\s+[^>\n]*)?>"
    r")",
    re.IGNORECASE,
)
_SCHEMA_KEY_LITERAL_RE = re.compile(
    r"^\s*(?:schema_version|gpd_return|status|summary|files_written|issues|next_actions|contract_results|"
    r"project_contract|claims|references|artifacts|path|kind|id|name|description|stage|round|source|target|"
    r"verified_at):(?:\s|$)",
    re.IGNORECASE,
)
_FIELD_PATH_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\[\])?(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[\])?)+\b")
_STRUCTURED_PROMPT_MARKER_RE = re.compile(
    r"^\s*(?:"
    r"<[A-Za-z][A-Za-z0-9_-]*(?:\s+[^>\n]*)?>|"
    r"</[A-Za-z][A-Za-z0-9_-]*>|"
    r"<!--\s*@\s*include\b.*-->"
    r")\s*$"
)
_PUBLIC_UX_LITERAL_RE = re.compile(
    r"(?:"
    r"^\s*#+\s*(?:Command Index|Choose this runtime if|Quick Start|Install|Uninstall|Warnings)\b|"
    r"^\s*(?:Command Index|Quick Start|Choose this runtime if|Available commands|Usage|Examples?)\s*$|"
    r"\[Y/n/e\]|"
    r"Start a fresh context window, then run|"
    r"Runtime readiness preflight|"
    r"No GPD project found|"
    r"Choose one:"
    r")",
    re.IGNORECASE,
)
_PUBLIC_UX_TEST_PATH_RE = re.compile(
    r"(?:^|/)tests/(?:core/)?(?:"
    r"test_cli(?:_commands)?|"
    r"test_.*(?:help|start|tour|onboarding|install|uninstall|diagnostics|checkpoint)"
    r")\.py$"
)
_SHORT_MACHINE_CONTRACT_LITERALS = frozenset(
    {
        "must_haves",
        "verification_inputs",
        "peer_review_stage",
        "execution_segment",
        "schema_version",
        "frontmatter",
        "gpd_return",
    }
)
_SHORT_PUBLIC_UX_LITERALS = frozenset({"Quick Start", "[Y/n/e]"})
_EXACT_ASSERTION_EXAMPLES_PER_CATEGORY = 5
_EXACT_ASSERTION_THRESHOLDS: dict[str, dict[str, int]] = {
    "brittle_prose_assertions": {"warn": 1100, "fail": 1150},
    "max_brittle_prose_assertions_per_file": {"warn": 50, "fail": 75},
    "max_brittle_prose_assertions_in_test_prompt_wiring": {"warn": 240, "fail": 260},
    "public_ux_exact_assertions": {"warn": 700, "fail": 750},
    "machine_contract_exact_assertions": {"warn": 6000, "fail": 6200},
    "exact_assertion_count": {"warn": 7700, "fail": 7900},
}
_TAXONOMY_HELPER_USAGE_SCHEMA_VERSION = "taxonomy_helper_usage.v1"
_TAXONOMY_HELPER_NAMES: tuple[str, ...] = (
    "assert_fragments",
    "assert_prompt_contracts",
    "forbidden_duplicate",
    "fragment_count",
    "machine_exact",
    "public_exact",
    "semantic_anchor",
)
_TAXONOMY_HELPER_ALIASES = {
    "_assert_prompt_contracts": "assert_prompt_contracts",
}

ExactAssertionCategory = Literal["machine_contract", "public_ux", "brittle_prose"]
ExactAssertionPolarity = Literal["required", "forbidden", "counted", "indexed"]
ExactAssertionShape = Literal["assert_contains", "assert_not_contains", "count", "index"]
ExactAssertionSeverity = Literal["info", "warn", "high"]
_GPD_RETURN_FIELD_REFERENCE_RE = re.compile(r"(?<![A-Za-z0-9_])\.?gpd_return\.([A-Za-z_][A-Za-z0-9_]*)")
_RETURN_FIELD_DECLARATION_RE = re.compile(
    r"\b(?:extended fields?|role-specific field|agent-specific extended field|role fields such as)\b",
    re.IGNORECASE,
)
_ROLE_FIELD_DECLARATION_RE = re.compile(
    r"\b(?:role-specific field|agent-specific extended field|role fields such as)\b",
    re.IGNORECASE,
)
_BACKTICK_IDENTIFIER_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")
_IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
_RETURN_FIELD_NEGATION_RE = re.compile(
    r"\b(?:do not|don't|never|forbidden|must not|not part of|omit|without)\b",
    re.IGNORECASE,
)
_YAML_KEY_RE = re.compile(r"^(?P<indent>\s*)(?P<key>['\"]?[A-Za-z_][A-Za-z0-9_]*['\"]?)\s*:")
_FIELD_DECLARATION_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "come",
        "comes",
        "extended",
        "field",
        "fields",
        "from",
        "include",
        "is",
        "must",
        "or",
        "role",
        "such",
        "the",
        "these",
        "this",
        "top",
        "with",
    }
)
_SEMANTIC_EXAMPLE_LIMIT = 10
_SEMANTIC_STATUS_VOCAB_RE = re.compile(
    r"\bcompleted\b.*\bcheckpoint\b.*\bblocked\b.*\bfailed\b|"
    r"\bcompleted\s*\|\s*checkpoint\s*\|\s*blocked\s*\|\s*failed\b",
    re.IGNORECASE,
)
_SEMANTIC_ROUTE_STATUS_RE = re.compile(
    r"\b(route|accept|handle|read|consume)\b.{0,100}\b(gpd_return\.status|typed status|structured status)\b",
    re.IGNORECASE,
)
_SEMANTIC_FRESH_CONTINUATION_RE = re.compile(
    r"\b(fresh continuation|one-shot handoff|same spawned run|resume(?:d)? in place|resume-in-place)\b",
    re.IGNORECASE,
)
_SEMANTIC_CHECKPOINT_SPAWN_RE = re.compile(
    r"\bcheckpoint\b.{0,140}\b(present|collect|response|user input|ask(?:ing)? the user)\b"
    r".{0,140}\b(spawn|start|fresh continuation)\b",
    re.IGNORECASE,
)
_SEMANTIC_NO_WAIT_RE = re.compile(
    r"\bdo not\b.{0,100}\b(wait|keep .*alive|resume .*in place|let .*continue)\b",
    re.IGNORECASE,
)
_SEMANTIC_STALE_ARTIFACT_RE = re.compile(
    r"\b(stale|preexisting|already existed|existing .* before this run)\b",
    re.IGNORECASE,
)
_SEMANTIC_RUNTIME_NOT_PROOF_RE = re.compile(
    r"\b(do not trust|do not infer|not enough|recovery evidence only|cannot prove)\b.{0,140}"
    r"\b(runtime|handoff status|completion text|files? alone|preexisting files?)\b",
    re.IGNORECASE,
)
_SEMANTIC_FILES_WRITTEN_RE = re.compile(r"\bgpd_return\.files_written\b|\bfiles_written\b", re.IGNORECASE)
_SEMANTIC_FILE_GATE_RE = re.compile(
    r"\b(named|names|appears|listed|list|same path|fresh|exists|readable|present|allowed|allowlist|"
    r"actually written|expected artifacts?|artifact gate)\b",
    re.IGNORECASE,
)
_SEMANTIC_PRESENTATION_ONLY_RE = re.compile(
    r"\b(headings?|human-readable|marker strings?|prose|success text|labels?)\b.{0,140}"
    r"\b(presentation only|not enough|do not satisfy|do not route|route on|authority|authoritative)\b",
    re.IGNORECASE,
)
_SEMANTIC_ROUTE_NOT_PROSE_RE = re.compile(
    r"\broute\b.{0,100}\b(gpd_return\.status|frontmatter|artifact gate|structured status)\b.{0,140}"
    r"\bnot\b.{0,100}\b(headings?|marker strings?|prose|runtime text|labels?)\b",
    re.IGNORECASE,
)
_SEMANTIC_NO_SYNTH_CHILD_RETURN_RE = re.compile(
    r"\b(do not|never)\b.{0,100}"
    r"\b(synthesize|synthesized|synthetic|fabricate|patch|paste|hand-author)\b.{0,140}"
    r"\b(child|planner|checker|verifier|agent|gpd_return|return envelope)\b",
    re.IGNORECASE,
)
_SEMANTIC_MISSING_CHILD_RETURN_RE = re.compile(
    r"\b(child|planner|checker|verifier|agent)\b.{0,120}"
    r"\b(missing|invalid|malformed)\b.{0,120}\b(gpd_return|return envelope)\b.{0,120}"
    r"\b(retry|fallback|incomplete)\b",
    re.IGNORECASE,
)
_SEMANTIC_CLAUSE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_CHILD_RETURN_SYNTHESIS_CLAUSE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|;\s*")
_CHILD_RETURN_SYNTHESIS_ACTION_RE = re.compile(
    r"\b(?P<action>"
    r"synthesi[sz]e|synthesi[sz]ed|synthesi[sz]ing|"
    r"fabricate|fabricated|fabricating|"
    r"patch|patched|patching|"
    r"paste|pasted|pasting|"
    r"hand-author|hand-authored|hand-authoring|hand author|hand authored|hand authoring"
    r")\b",
    re.IGNORECASE,
)
_CHILD_RETURN_SYNTHESIS_CONTEXT_RE = re.compile(
    r"\b(?:child|planner|checker|verifier|agent|subagent)\b.{0,140}"
    r"\b(?:gpd_return|return envelope)\b|"
    r"\b(?:gpd_return|return envelope)\b.{0,140}"
    r"\b(?:child|planner|checker|verifier|agent|subagent)\b",
    re.IGNORECASE,
)
_CHILD_RETURN_SYNTHESIS_NEGATION_RE = re.compile(
    r"\b(?:do not|don't|never|must not|should not|cannot|can't|forbidden|not allowed|without|instead of)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class _SemanticDuplicateCategory:
    category: str
    label: str
    canonical_references: tuple[str, ...]
    suggested_action: str


_SEMANTIC_DUPLICATE_CATEGORIES: tuple[_SemanticDuplicateCategory, ...] = (
    _SemanticDuplicateCategory(
        category="status_handling",
        label="Runtime status routing and vocabulary",
        canonical_references=(
            "src/gpd/specs/references/orchestration/agent-infrastructure.md",
            "src/gpd/specs/references/verification/verification-status-authority.md",
        ),
        suggested_action=(
            "Keep local routing decisions, but reference the shared runtime status authority for generic vocabulary."
        ),
    ),
    _SemanticDuplicateCategory(
        category="fresh_continuation",
        label="Checkpoint stop and fresh continuation ownership",
        canonical_references=(
            "src/gpd/specs/references/orchestration/agent-delegation.md",
            "src/gpd/specs/references/orchestration/continuation-boundary.md",
        ),
        suggested_action=(
            "Keep callsite-specific checkpoint prompts, but reference continuation-boundary.md for generic restart rules."
        ),
    ),
    _SemanticDuplicateCategory(
        category="stale_artifact_rejection",
        label="Reject stale artifact and runtime-success evidence",
        canonical_references=(
            "src/gpd/specs/references/orchestration/child-artifact-gate.md",
            "src/gpd/specs/references/orchestration/continuation-boundary.md",
            "src/gpd/specs/references/publication/stage-recovery-gate.md",
        ),
        suggested_action=(
            "Keep local expected artifact names, but move generic stale-output rejection to the shared artifact gate."
        ),
    ),
    _SemanticDuplicateCategory(
        category="files_written_freshness",
        label="Fresh artifact proof via gpd_return.files_written",
        canonical_references=(
            "src/gpd/specs/references/orchestration/child-artifact-gate.md",
            "src/gpd/specs/references/orchestration/continuation-boundary.md",
        ),
        suggested_action=(
            "Keep callsite-specific expected artifacts, but replace generic freshness prose with child-artifact-gate.md."
        ),
    ),
    _SemanticDuplicateCategory(
        category="heading_prose_non_authority",
        label="Headings and prose are presentation, not routing authority",
        canonical_references=(
            "src/gpd/specs/references/orchestration/child-artifact-gate.md",
            "src/gpd/specs/references/verification/verification-status-authority.md",
            "src/gpd/specs/references/verification/core/verification-child-return-contract.md",
        ),
        suggested_action=("Keep user-facing labels where useful, but route on structured status and artifact gates."),
    ),
    _SemanticDuplicateCategory(
        category="no_synthesized_child_gpd_return",
        label="Do not synthesize child gpd_return envelopes",
        canonical_references=(
            "src/gpd/specs/references/orchestration/agent-delegation.md",
            "src/gpd/specs/references/orchestration/child-artifact-gate.md",
        ),
        suggested_action=(
            "Keep main-context fallback returns distinct from child returns; retry or fail closed on malformed child envelopes."
        ),
    ),
)
_SEMANTIC_DUPLICATE_CATEGORY_BY_ID = {category.category: category for category in _SEMANTIC_DUPLICATE_CATEGORIES}


@dataclass(frozen=True, slots=True)
class ExactPromptAssertion:
    literal: str
    line: int
    assertion_shape: ExactAssertionShape
    polarity: ExactAssertionPolarity


@dataclass(frozen=True, slots=True)
class PromptSource:
    """One canonical prompt source discovered under the repository source tree."""

    kind: PromptSurfaceKind
    name: str
    path: str
    absolute_path: Path
    repo_root: Path
    src_root: Path


@dataclass(frozen=True, slots=True)
class MarkdownFence:
    """One fenced code block with line metadata."""

    info: str
    body: str
    start_line: int
    end_line: int


@dataclass(frozen=True, slots=True)
class RuntimeProjectionMetric:
    runtime: str
    native_include_support: bool
    expanded_line_count: int
    expanded_char_count: int
    line_count: int
    char_count: int
    line_delta: int
    char_delta: int
    char_delta_percent: float
    include_count: int
    runtime_note_count: int
    runtime_note_chars: int
    shell_fence_count: int
    shell_rewrite_count: int
    bridge_command_occurrences: int


@dataclass(frozen=True, slots=True)
class InvalidGpdReturnExample:
    path: str
    start_line: int
    end_line: int
    errors: tuple[str, ...]
    preview: str


@dataclass(frozen=True, slots=True)
class InvalidFrontmatterExample:
    path: str
    start_line: int
    end_line: int
    schema_name: Literal["verification"]
    fields: tuple[str, ...]
    errors: tuple[str, ...]
    preview: str


@dataclass(frozen=True, slots=True)
class PromptReturnFieldMention:
    path: str
    line: int
    field: str
    mention_kind: Literal[
        "direct_reference",
        "extended_field_list",
        "role_field_statement",
        "yaml_example_key",
    ]
    polarity: Literal["positive", "negative"]
    allowed: bool
    allowed_source: Literal["base", "extension", "unknown"]
    severity: Literal["info", "warn", "error"]
    snippet: str
    suggestion: str | None = None


@dataclass(frozen=True, slots=True)
class ForbiddenChildReturnSynthesisMention:
    path: str
    line: int
    action: str
    polarity: Literal["positive"]
    severity: Literal["error"]
    snippet: str


@dataclass(frozen=True, slots=True)
class PromptSurfaceItem:
    kind: PromptSurfaceKind
    name: str
    path: str
    raw_line_count: int
    raw_char_count: int
    raw_include_count: int
    expanded_line_count: int
    expanded_char_count: int
    expanded_include_count: int
    unresolved_include_count: int
    visible_schema_example_count: int
    invalid_gpd_return_example_count: int
    invalid_gpd_return_examples: tuple[InvalidGpdReturnExample, ...]
    invalid_frontmatter_example_count: int
    invalid_frontmatter_examples: tuple[InvalidFrontmatterExample, ...]
    return_field_mention_count: int
    disallowed_return_field_mention_count: int
    disallowed_return_field_mentions: tuple[PromptReturnFieldMention, ...]
    hard_gate_line_count: int
    hard_gate_density: float
    shell_fence_count: int
    shell_parsing_line_count: int
    rigidity_index: int
    runtime_projection: tuple[RuntimeProjectionMetric, ...]


@dataclass(frozen=True, slots=True)
class DuplicateInvariantGroup:
    phrase: str
    occurrence_count: int
    file_count: int
    severity: Literal["info", "warn", "high"]
    locations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SemanticDuplicateOccurrence:
    path: str
    line: int
    category: str
    snippet: str
    matched_terms: tuple[str, ...]
    is_reference_or_template: bool


@dataclass(frozen=True, slots=True)
class SemanticDuplicateGroup:
    category: str
    label: str
    occurrence_count: int
    file_count: int
    non_reference_occurrence_count: int
    non_reference_file_count: int
    severity: Literal["info", "warn", "high"]
    canonical_references: tuple[str, ...]
    examples: tuple[SemanticDuplicateOccurrence, ...]
    suggested_action: str


@dataclass(frozen=True, slots=True)
class AuthorityPromptMetric:
    authority: str
    path: str
    raw_line_count: int
    raw_char_count: int
    raw_include_count: int
    expanded_line_count: int
    expanded_char_count: int
    transitive_include_authorities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MustNotEagerLoadViolation:
    workflow_id: str
    stage_id: str
    authority: str
    violation_source: Literal[
        "manifest_overlap",
        "first_turn_direct_include",
        "first_turn_transitive_include",
        "stage_eager_transitive_include",
        "conditional_eager_overlap",
    ]
    eager_via: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WorkflowStagePromptMetric:
    workflow_id: str
    stage_id: str
    order: int
    eager_authorities: tuple[str, ...]
    eager_authority_metrics: tuple[AuthorityPromptMetric, ...]
    eager_line_count: int
    eager_char_count: int
    lazy_authorities: tuple[str, ...]
    lazy_authority_metrics: tuple[AuthorityPromptMetric, ...]
    lazy_line_count: int
    lazy_char_count: int
    must_not_eager_load_violations: tuple[MustNotEagerLoadViolation, ...]


@dataclass(frozen=True, slots=True)
class StageAwareWorkflowPromptMetric:
    workflow_id: str
    command_name: str
    command_path: str
    manifest_path: str
    stage_count: int
    first_turn_line_count: int
    first_turn_char_count: int
    first_turn_raw_include_count: int
    runtime_projection: tuple[RuntimeProjectionMetric, ...]
    stages: tuple[WorkflowStagePromptMetric, ...]
    violation_count: int
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _IncludeTrace:
    authorities: tuple[str, ...]
    chains_by_authority: Mapping[str, tuple[tuple[str, ...], ...]]


@dataclass(frozen=True, slots=True)
class PromptSurfaceReport:
    schema_version: str
    repo_root: str
    totals: Mapping[str, object]
    items: tuple[PromptSurfaceItem, ...]
    stage_diagnostics: tuple[StageAwareWorkflowPromptMetric, ...]
    invalid_gpd_return_examples: tuple[InvalidGpdReturnExample, ...]
    invalid_frontmatter_examples: tuple[InvalidFrontmatterExample, ...]
    return_field_mentions: tuple[PromptReturnFieldMention, ...]
    disallowed_return_field_mentions: tuple[PromptReturnFieldMention, ...]
    forbidden_child_return_synthesis_mentions: tuple[ForbiddenChildReturnSynthesisMention, ...]
    duplicate_invariants: tuple[DuplicateInvariantGroup, ...]
    semantic_duplicate_invariants: tuple[SemanticDuplicateGroup, ...]
    exact_assertion_diagnostics: Mapping[str, object]
    exact_prose_assertion_files: tuple[Mapping[str, object], ...]
    warnings: tuple[str, ...]


__all__ = [
    "DEFAULT_SURFACES",
    "PROMPT_SURFACE_REPORT_SCHEMA_VERSION",
    "AuthorityPromptMetric",
    "DuplicateInvariantGroup",
    "ForbiddenChildReturnSynthesisMention",
    "InvalidFrontmatterExample",
    "InvalidGpdReturnExample",
    "MustNotEagerLoadViolation",
    "PromptSource",
    "PromptReturnFieldMention",
    "PromptSurfaceItem",
    "PromptSurfaceReport",
    "RuntimeProjectionMetric",
    "SemanticDuplicateGroup",
    "SemanticDuplicateOccurrence",
    "StageAwareWorkflowPromptMetric",
    "WorkflowStagePromptMetric",
    "build_prompt_surface_report",
    "iter_prompt_sources",
    "measure_prompt_file",
    "render_prompt_surface_markdown",
    "render_prompt_surface_table",
    "report_to_dict",
]


def iter_prompt_sources(
    repo_root: str | Path,
    surfaces: Iterable[str] | str = DEFAULT_SURFACES,
) -> tuple[PromptSource, ...]:
    """Return canonical command, agent, and workflow markdown sources."""

    root = Path(repo_root).expanduser().resolve()
    src_root = _source_root_for_repo(root)
    normalized_surfaces = _normalize_surfaces(surfaces)
    source_dirs: dict[PromptSurfaceKind, Path] = {
        "command": src_root / "commands",
        "agent": src_root / "agents",
        "workflow": src_root / "specs" / "workflows",
    }

    sources: list[PromptSource] = []
    for kind in normalized_surfaces:
        source_dir = source_dirs[kind]
        if not source_dir.is_dir():
            continue
        for path in sorted(source_dir.glob("*.md")):
            if path.is_symlink() or not path.is_file():
                continue
            sources.append(
                PromptSource(
                    kind=kind,
                    name=path.stem,
                    path=_relative_path(path, root),
                    absolute_path=path,
                    repo_root=root,
                    src_root=src_root,
                )
            )
    return tuple(sources)


def measure_prompt_file(
    source: PromptSource,
    runtime_names: Iterable[str] | str = (),
    include_runtime_projections: bool = True,
) -> PromptSurfaceItem:
    """Measure one prompt source without mutating repo or project state."""

    raw_text = source.absolute_path.read_text(encoding="utf-8")
    expanded_text = expand_at_includes(raw_text, source.src_root, DEFAULT_PATH_PREFIX)
    raw_include_count = _count_raw_includes(raw_text)
    (
        visible_schema_example_count,
        invalid_return_examples,
        invalid_frontmatter_examples,
    ) = _inspect_visible_schema_examples(raw_text, source.path)
    invalid_return_count = len(invalid_return_examples)
    invalid_frontmatter_count = len(invalid_frontmatter_examples)
    return_field_mentions = _scan_return_field_mentions(raw_text, source.path)
    disallowed_return_field_mentions = _disallowed_return_field_mentions(return_field_mentions)
    hard_gate_line_count, hard_gate_density = _hard_gate_metrics(raw_text)
    shell_fence_count = _count_shell_fences(raw_text)
    shell_parsing_line_count = _count_shell_parsing_lines(raw_text)
    unresolved_include_count = len(_UNRESOLVED_INCLUDE_RE.findall(expanded_text))

    runtime_projection: tuple[RuntimeProjectionMetric, ...] = ()
    if include_runtime_projections and source.kind in {"command", "agent"}:
        runtime_projection = tuple(
            _measure_runtime_projection(source, raw_text, expanded_text, runtime_name)
            for runtime_name in _normalize_runtime_names(runtime_names)
        )

    rigidity_index = (
        2 * visible_schema_example_count
        + 3 * invalid_return_count
        + 3 * invalid_frontmatter_count
        + hard_gate_line_count
        + 2 * shell_parsing_line_count
        + 5 * unresolved_include_count
    )

    return PromptSurfaceItem(
        kind=source.kind,
        name=source.name,
        path=source.path,
        raw_line_count=_line_count(raw_text),
        raw_char_count=len(raw_text),
        raw_include_count=raw_include_count,
        expanded_line_count=_line_count(expanded_text),
        expanded_char_count=len(expanded_text),
        expanded_include_count=len(_INCLUDED_MARKER_RE.findall(expanded_text)),
        unresolved_include_count=unresolved_include_count,
        visible_schema_example_count=visible_schema_example_count,
        invalid_gpd_return_example_count=invalid_return_count,
        invalid_gpd_return_examples=invalid_return_examples,
        invalid_frontmatter_example_count=invalid_frontmatter_count,
        invalid_frontmatter_examples=invalid_frontmatter_examples,
        return_field_mention_count=len(return_field_mentions),
        disallowed_return_field_mention_count=len(disallowed_return_field_mentions),
        disallowed_return_field_mentions=disallowed_return_field_mentions,
        hard_gate_line_count=hard_gate_line_count,
        hard_gate_density=hard_gate_density,
        shell_fence_count=shell_fence_count,
        shell_parsing_line_count=shell_parsing_line_count,
        rigidity_index=rigidity_index,
        runtime_projection=runtime_projection,
    )


def build_prompt_surface_report(
    repo_root: str | Path,
    surfaces: Iterable[str] | str = DEFAULT_SURFACES,
    runtime_names: Iterable[str] | str = (),
    include_tests: bool = False,
    top: int | None = None,
    include_runtime_projections: bool = True,
) -> PromptSurfaceReport:
    """Build the full prompt diagnostics report for canonical source files."""

    del top
    root = Path(repo_root).expanduser().resolve()
    warnings: list[str] = []
    sources = iter_prompt_sources(root, surfaces)
    if not sources:
        warnings.append("no prompt sources found for requested surfaces")

    items = tuple(
        measure_prompt_file(
            source,
            runtime_names=runtime_names,
            include_runtime_projections=include_runtime_projections,
        )
        for source in sources
    )
    duplicate_invariants = _duplicate_invariant_groups(root, include_tests=include_tests)
    semantic_duplicate_invariants = _semantic_duplicate_invariant_groups(root, include_tests=include_tests)
    exact_assertion_diagnostics = (
        _scan_exact_assertion_diagnostics(root) if include_tests else _empty_exact_assertion_diagnostics()
    )
    exact_assertions = _exact_prose_assertion_files_from_diagnostics(exact_assertion_diagnostics)
    invalid_return_examples = tuple(example for item in items for example in item.invalid_gpd_return_examples)
    invalid_frontmatter_examples = tuple(example for item in items for example in item.invalid_frontmatter_examples)
    return_field_mentions = _scan_return_field_mentions_for_repo(root, include_tests=include_tests)
    disallowed_return_field_mentions = _disallowed_return_field_mentions(return_field_mentions)
    forbidden_child_return_synthesis_mentions = _scan_forbidden_child_return_synthesis_mentions(sources)
    stage_diagnostics = _build_stage_diagnostics(sources, items, report_warnings=warnings)

    return PromptSurfaceReport(
        schema_version=PROMPT_SURFACE_REPORT_SCHEMA_VERSION,
        repo_root=str(root),
        totals=_build_totals(
            items,
            stage_diagnostics=stage_diagnostics,
            return_field_mentions=return_field_mentions,
            forbidden_child_return_synthesis_mentions=forbidden_child_return_synthesis_mentions,
        ),
        items=items,
        stage_diagnostics=stage_diagnostics,
        invalid_gpd_return_examples=invalid_return_examples,
        invalid_frontmatter_examples=invalid_frontmatter_examples,
        return_field_mentions=return_field_mentions,
        disallowed_return_field_mentions=disallowed_return_field_mentions,
        forbidden_child_return_synthesis_mentions=forbidden_child_return_synthesis_mentions,
        duplicate_invariants=duplicate_invariants,
        semantic_duplicate_invariants=semantic_duplicate_invariants,
        exact_assertion_diagnostics=exact_assertion_diagnostics,
        exact_prose_assertion_files=exact_assertions,
        warnings=tuple(warnings),
    )


def report_to_dict(report: PromptSurfaceReport, top: int | None = None) -> dict[str, object]:
    """Convert a report into JSON-serializable primitives."""

    return {
        "schema_version": report.schema_version,
        "repo_root": report.repo_root,
        "totals": report.totals,
        "items": [_prompt_item_to_dict(item) for item in _top_items(report.items, top)],
        "runtime_top_prompts": _runtime_top_prompts_to_dict(report.items, top),
        "stage_diagnostics": [_stage_diagnostic_to_dict(metric) for metric in report.stage_diagnostics],
        "invalid_gpd_return_examples": [
            _invalid_gpd_return_example_to_dict(example) for example in report.invalid_gpd_return_examples
        ],
        "invalid_frontmatter_examples": [
            _invalid_frontmatter_example_to_dict(example) for example in report.invalid_frontmatter_examples
        ],
        "disallowed_return_field_mentions": [
            _return_field_mention_to_dict(mention) for mention in report.disallowed_return_field_mentions
        ],
        "forbidden_child_return_synthesis_mentions": [
            _forbidden_child_return_synthesis_mention_to_dict(mention)
            for mention in report.forbidden_child_return_synthesis_mentions
        ],
        "duplicate_invariants": [
            {
                "phrase": group.phrase,
                "occurrence_count": group.occurrence_count,
                "file_count": group.file_count,
                "severity": group.severity,
                "locations": list(group.locations),
            }
            for group in report.duplicate_invariants
        ],
        "semantic_duplicate_invariants": [
            {
                "category": group.category,
                "label": group.label,
                "occurrence_count": group.occurrence_count,
                "file_count": group.file_count,
                "non_reference_occurrence_count": group.non_reference_occurrence_count,
                "non_reference_file_count": group.non_reference_file_count,
                "severity": group.severity,
                "canonical_references": list(group.canonical_references),
                "suggested_action": group.suggested_action,
                "examples": [
                    {
                        "path": example.path,
                        "line": example.line,
                        "category": example.category,
                        "snippet": example.snippet,
                        "matched_terms": list(example.matched_terms),
                        "is_reference_or_template": example.is_reference_or_template,
                    }
                    for example in group.examples[: _semantic_example_limit(top)]
                ],
            }
            for group in report.semantic_duplicate_invariants
        ],
        "exact_assertion_diagnostics": report.exact_assertion_diagnostics,
        "exact_prose_assertion_files": [dict(entry) for entry in report.exact_prose_assertion_files],
        "warnings": list(report.warnings),
    }


def render_prompt_surface_markdown(report: PromptSurfaceReport, top: int | None = None) -> str:
    """Render a human-readable markdown report."""

    top_items = _top_items(report.items, top)
    totals = report.totals
    lines = [
        "# Prompt Surface Diagnostics",
        "",
        f"- Schema version: `{report.schema_version}`",
        f"- Repo root: `{report.repo_root}`",
        f"- Prompt sources: {totals.get('item_count', 0)}",
        f"- Expanded chars: {totals.get('expanded_char_count', 0)}",
        f"- Invalid `gpd_return` examples: {len(report.invalid_gpd_return_examples)}",
        f"- Invalid verification frontmatter examples: {len(report.invalid_frontmatter_examples)}",
        f"- Disallowed `gpd_return` field mentions: {len(report.disallowed_return_field_mentions)}",
        f"- Forbidden child `gpd_return` synthesis instructions: "
        f"{len(report.forbidden_child_return_synthesis_mentions)}",
        f"- Hard-gate lines: {totals.get('hard_gate_line_count', 0)}",
        f"- Shell parsing lines: {totals.get('shell_parsing_line_count', 0)}",
        "",
        "## Top Prompt Sources",
        "",
        "| Rank | Kind | Name | Expanded chars | Raw lines | Includes | Hard gates | Shell parse | Schemas | Invalid returns | Invalid frontmatter | Bad fields | Rigidity |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for index, item in enumerate(top_items, start=1):
        lines.append(
            f"| {index} | {item.kind} | `{item.name}` | {item.expanded_char_count} | {item.raw_line_count} | "
            f"{item.raw_include_count} | {item.hard_gate_line_count} | {item.shell_parsing_line_count} | "
            f"{item.visible_schema_example_count} | {item.invalid_gpd_return_example_count} | "
            f"{item.invalid_frontmatter_example_count} | "
            f"{item.disallowed_return_field_mention_count} | "
            f"{item.rigidity_index} |"
        )

    if report.invalid_gpd_return_examples:
        lines.extend(
            [
                "",
                "## Invalid `gpd_return` Examples",
                "",
                "| Path | Lines | Errors | Preview |",
                "|---|---:|---|---|",
            ]
        )
        for example in report.invalid_gpd_return_examples:
            lines.append(
                f"| `{example.path}` | {example.start_line}-{example.end_line} | "
                f"{_markdown_table_cell('; '.join(example.errors))} | "
                f"`{_markdown_table_cell(example.preview)}` |"
            )

    if report.invalid_frontmatter_examples:
        lines.extend(
            [
                "",
                "## Invalid Verification Frontmatter Examples",
                "",
                "| Path | Lines | Schema | Fields | Errors | Preview |",
                "|---|---:|---|---|---|---|",
            ]
        )
        for example in report.invalid_frontmatter_examples:
            lines.append(
                f"| `{example.path}` | {example.start_line}-{example.end_line} | `{example.schema_name}` | "
                f"{_markdown_table_cell(', '.join(example.fields))} | "
                f"{_markdown_table_cell('; '.join(example.errors))} | "
                f"`{_markdown_table_cell(example.preview)}` |"
            )

    if report.disallowed_return_field_mentions:
        lines.extend(
            [
                "",
                "## Disallowed `gpd_return` Field Mentions",
                "",
                "| Path | Line | Field | Kind | Suggestion | Snippet |",
                "|---|---:|---|---|---|---|",
            ]
        )
        for mention in report.disallowed_return_field_mentions:
            suggestion = mention.suggestion or ""
            lines.append(
                f"| `{mention.path}` | {mention.line} | `{mention.field}` | {mention.mention_kind} | "
                f"{_markdown_table_cell(suggestion)} | `{_markdown_table_cell(mention.snippet)}` |"
            )

    if report.forbidden_child_return_synthesis_mentions:
        lines.extend(
            [
                "",
                "## Forbidden Child `gpd_return` Synthesis Instructions",
                "",
                "| Path | Line | Action | Snippet |",
                "|---|---:|---|---|",
            ]
        )
        for mention in report.forbidden_child_return_synthesis_mentions:
            lines.append(
                f"| `{mention.path}` | {mention.line} | `{mention.action}` | "
                f"`{_markdown_table_cell(mention.snippet)}` |"
            )

    runtime_totals = cast(Mapping[str, Mapping[str, object]], totals.get("runtime_projection", {}))
    if runtime_totals:
        lines.extend(
            [
                "",
                "## Runtime Projection Totals",
                "",
                "| Runtime | Native includes | Items | Projected chars | Char delta | Includes | Runtime notes | Bridge calls |",
                "|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for runtime, metric in sorted(runtime_totals.items()):
            lines.append(
                f"| `{runtime}` | {str(metric.get('native_include_support', False)).lower()} | "
                f"{metric.get('item_count', 0)} | {metric.get('char_count', 0)} | "
                f"{metric.get('char_delta', 0)} | "
                f"{metric.get('include_count', 0)} | {metric.get('runtime_note_count', 0)} | "
                f"{metric.get('bridge_command_occurrences', 0)} |"
            )

    runtime_top_prompts = _runtime_top_prompt_rows(report.items, top)
    if runtime_top_prompts:
        lines.extend(
            [
                "",
                "## Runtime Top Prompts",
                "",
                "| Runtime | Rank | Native includes | Kind | Name | Projected chars | Expanded chars | Char delta | Line delta | Includes | Runtime notes | Shell rewrites |",
                "|---|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        ranks_by_runtime: dict[str, int] = defaultdict(int)
        for row in runtime_top_prompts:
            runtime = str(row["runtime"])
            ranks_by_runtime[runtime] += 1
            lines.append(
                f"| `{runtime}` | {ranks_by_runtime[runtime]} | "
                f"{str(row['native_include_support']).lower()} | {row['kind']} | `{row['name']}` | "
                f"{row['projected_char_count']} | {row['expanded_char_count']} | "
                f"{row['char_delta']} | {row['line_delta']} | {row['include_count']} | "
                f"{row['runtime_note_count']} | {row['shell_rewrite_count']} |"
            )

    stage_top_prompts = _stage_top_prompt_rows(report.stage_diagnostics, top)
    if stage_top_prompts:
        lines.extend(
            [
                "",
                "## Stage-Aware Staged Loading",
                "",
                "| Workflow | Stage | First-turn chars | Eager chars | Lazy chars | Violations |",
                "|---|---|---:|---:|---:|---:|",
            ]
        )
        for row in stage_top_prompts:
            lines.append(
                f"| `{row['workflow_id']}` | `{row['stage_id']}` | {row['first_turn_char_count']} | "
                f"{row['eager_char_count']} | {row['lazy_char_count']} | {row['violation_count']} |"
            )

    duplicate_groups = report.duplicate_invariants[: top or len(report.duplicate_invariants)]
    if duplicate_groups:
        lines.extend(
            [
                "",
                "## Duplicate Invariants",
                "",
                "| Severity | Occurrences | Files | Phrase |",
                "|---|---:|---:|---|",
            ]
        )
        for group in duplicate_groups:
            lines.append(f"| {group.severity} | {group.occurrence_count} | {group.file_count} | `{group.phrase}` |")

    semantic_groups = report.semantic_duplicate_invariants[: top or len(report.semantic_duplicate_invariants)]
    if semantic_groups:
        lines.extend(
            [
                "",
                "## Semantic Duplicate Invariants",
                "",
                "| Severity | Category | Occurrences | Non-ref occurrences | Files | Non-ref files | Canonical refs | Suggested action |",
                "|---|---|---:|---:|---:|---:|---|---|",
            ]
        )
        for group in semantic_groups:
            refs = ", ".join(Path(reference).name for reference in group.canonical_references)
            lines.append(
                f"| {group.severity} | `{group.category}` | {group.occurrence_count} | "
                f"{group.non_reference_occurrence_count} | {group.file_count} | {group.non_reference_file_count} | "
                f"{_markdown_table_cell(refs)} | "
                f"{_markdown_table_cell(group.suggested_action)} |"
            )
        example_limit = _semantic_example_limit(top)
        for group in semantic_groups:
            examples = group.examples[:example_limit]
            if not examples:
                continue
            lines.extend(["", f"### `{group.category}` Examples", ""])
            for example in examples:
                lines.append(f"- `{example.path}:{example.line}` - {_markdown_table_cell(example.snippet)}")

    exact_files = _exact_assertion_file_rows(report.exact_assertion_diagnostics, top)
    if exact_files:
        brittle_threshold = _EXACT_ASSERTION_THRESHOLDS["brittle_prose_assertions"]
        lines.extend(
            [
                "",
                "## Prompt-Test Exactness",
                "",
                f"Thresholds: brittle prose warn > {brittle_threshold['warn']}, fail > {brittle_threshold['fail']}.",
                "",
                "| File | Exact | Machine | Public UX | Brittle prose | Brittle % | Severity |",
                "|---|---:|---:|---:|---:|---:|---|",
            ]
        )
        for entry in exact_files:
            brittle_density = 100 * cast(float, entry.get("brittle_prose_density", 0.0))
            lines.append(
                f"| `{entry.get('path', '')}` | {entry.get('exact_assertion_count', 0)} | "
                f"{entry.get('machine_contract_exact_assertions', 0)} | "
                f"{entry.get('public_ux_exact_assertions', 0)} | "
                f"{entry.get('brittle_prose_assertions', 0)} | "
                f"{brittle_density:.1f}% | {entry.get('severity', 'info')} |"
            )

    if report.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in report.warnings)

    return "\n".join(lines) + "\n"


def render_prompt_surface_table(report: PromptSurfaceReport, top: int | None = None) -> str:
    """Render a compact fixed-width table for terminal output."""

    rows = [
        (
            item.kind,
            item.name,
            str(item.expanded_char_count),
            str(item.raw_include_count),
            str(item.visible_schema_example_count),
            str(item.invalid_gpd_return_example_count),
            str(item.invalid_frontmatter_example_count),
            str(item.disallowed_return_field_mention_count),
            str(item.hard_gate_line_count),
            str(item.shell_parsing_line_count),
            str(item.rigidity_index),
        )
        for item in _top_items(report.items, top)
    ]
    headers = (
        "kind",
        "name",
        "expanded_chars",
        "includes",
        "schemas",
        "invalid",
        "bad_frontmatter",
        "bad_fields",
        "hard_gates",
        "shell_parse",
        "rigidity",
    )
    widths = [len(header) for header in headers]
    for row in rows:
        widths = [max(width, len(cell)) for width, cell in zip(widths, row, strict=True)]

    def render_row(row: Sequence[str]) -> str:
        return "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip()

    lines = [render_row(headers), render_row(tuple("-" * width for width in widths))]
    lines.extend(render_row(row) for row in rows)
    runtime_rows = [
        (
            str(row["runtime"]),
            str(row["kind"]),
            str(row["name"]),
            str(row["projected_char_count"]),
            str(row["expanded_char_count"]),
            str(row["char_delta"]),
            str(row["line_delta"]),
            str(row["include_count"]),
            str(row["runtime_note_count"]),
            str(row["shell_rewrite_count"]),
        )
        for row in _runtime_top_prompt_rows(report.items, top)
    ]
    if runtime_rows:
        runtime_headers = (
            "runtime",
            "kind",
            "name",
            "projected_chars",
            "expanded_chars",
            "char_delta",
            "line_delta",
            "includes",
            "runtime_notes",
            "shell_rewrites",
        )
        runtime_widths = [len(header) for header in runtime_headers]
        for row in runtime_rows:
            runtime_widths = [max(width, len(cell)) for width, cell in zip(runtime_widths, row, strict=True)]

        def render_runtime_row(row: Sequence[str]) -> str:
            return "  ".join(cell.ljust(width) for cell, width in zip(row, runtime_widths, strict=True)).rstrip()

        lines.extend(
            (
                "",
                "runtime top prompts",
                render_runtime_row(runtime_headers),
                render_runtime_row(tuple("-" * width for width in runtime_widths)),
            )
        )
        lines.extend(render_runtime_row(row) for row in runtime_rows)
    stage_rows = [
        (
            str(row["workflow_id"]),
            str(row["stage_id"]),
            str(row["first_turn_char_count"]),
            str(row["eager_char_count"]),
            str(row["lazy_char_count"]),
            str(row["violation_count"]),
        )
        for row in _stage_top_prompt_rows(report.stage_diagnostics, top)
    ]
    if stage_rows:
        stage_headers = (
            "workflow",
            "stage",
            "first_turn_chars",
            "eager_chars",
            "lazy_chars",
            "violations",
        )
        stage_widths = [len(header) for header in stage_headers]
        for row in stage_rows:
            stage_widths = [max(width, len(cell)) for width, cell in zip(stage_widths, row, strict=True)]

        def render_stage_row(row: Sequence[str]) -> str:
            return "  ".join(cell.ljust(width) for cell, width in zip(row, stage_widths, strict=True)).rstrip()

        lines.extend(
            (
                "",
                "stage top prompts",
                render_stage_row(stage_headers),
                render_stage_row(tuple("-" * width for width in stage_widths)),
            )
        )
        lines.extend(render_stage_row(row) for row in stage_rows)
    exact_rows = [
        (
            str(row.get("path", "")),
            str(row.get("exact_assertion_count", 0)),
            str(row.get("machine_contract_exact_assertions", 0)),
            str(row.get("public_ux_exact_assertions", 0)),
            str(row.get("brittle_prose_assertions", 0)),
            f"{100 * cast(float, row.get('brittle_prose_density', 0.0)):.1f}",
            str(row.get("severity", "info")),
        )
        for row in _exact_assertion_file_rows(report.exact_assertion_diagnostics, top)
    ]
    if exact_rows:
        exact_headers = ("file", "exact", "machine", "public_ux", "brittle", "brittle_pct", "severity")
        exact_widths = [len(header) for header in exact_headers]
        for row in exact_rows:
            exact_widths = [max(width, len(cell)) for width, cell in zip(exact_widths, row, strict=True)]

        def render_exact_row(row: Sequence[str]) -> str:
            return "  ".join(cell.ljust(width) for cell, width in zip(row, exact_widths, strict=True)).rstrip()

        lines.extend(
            (
                "",
                "prompt-test exactness",
                render_exact_row(exact_headers),
                render_exact_row(tuple("-" * width for width in exact_widths)),
            )
        )
        lines.extend(render_exact_row(row) for row in exact_rows)
    outside_top_disallowed = _disallowed_return_field_mentions_outside_top_rows(report, top)
    if outside_top_disallowed:
        lines.extend(("", f"disallowed return field mentions outside top prompt rows: {outside_top_disallowed}"))
    if report.forbidden_child_return_synthesis_mentions:
        lines.extend(
            (
                "",
                "forbidden child return synthesis instructions: "
                f"{len(report.forbidden_child_return_synthesis_mentions)}",
            )
        )
    return "\n".join(lines) + "\n"


def _source_root_for_repo(repo_root: Path) -> Path:
    src_root = repo_root / "src" / "gpd"
    if src_root.is_dir():
        return src_root
    if (repo_root / "commands").is_dir() and (repo_root / "agents").is_dir():
        return repo_root
    return src_root


def _normalize_surfaces(surfaces: Iterable[str] | str) -> tuple[PromptSurfaceKind, ...]:
    if isinstance(surfaces, str):
        raw_values = (surfaces,)
    else:
        raw_values = tuple(surfaces)
    if not raw_values or any(value == "all" for value in raw_values):
        return DEFAULT_SURFACES

    normalized: list[PromptSurfaceKind] = []
    for value in raw_values:
        if value not in DEFAULT_SURFACES:
            allowed = ", ".join((*DEFAULT_SURFACES, "all"))
            raise ValueError(f"surface must be one of: {allowed}")
        kind = cast(PromptSurfaceKind, value)
        if kind not in normalized:
            normalized.append(kind)
    return tuple(normalized)


def _normalize_runtime_names(runtime_names: Iterable[str] | str) -> tuple[str, ...]:
    descriptors = iter_runtime_descriptors()
    all_names = tuple(descriptor.runtime_name for descriptor in descriptors)
    if isinstance(runtime_names, str):
        raw_values = (runtime_names,)
    else:
        raw_values = tuple(runtime_names)
    if not raw_values:
        return ()
    if any(value == "all" for value in raw_values):
        return all_names

    normalized: list[str] = []
    for value in raw_values:
        runtime_name = normalize_runtime_name(value)
        if runtime_name is None:
            supported = ", ".join(all_names)
            raise KeyError(f"Unknown runtime {value!r}. Supported: {supported}")
        if runtime_name not in normalized:
            normalized.append(runtime_name)
    return tuple(normalized)


def _relative_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _line_count(text: str) -> int:
    return len(text.splitlines())


def _percent_delta(delta: int, baseline: int) -> float:
    if baseline <= 0:
        return 0.0
    return round(100 * delta / baseline, 6)


def _body_without_frontmatter(text: str) -> str:
    body, _line_offset = _body_without_frontmatter_with_line_offset(text)
    return body


def _body_without_frontmatter_with_line_offset(text: str) -> tuple[str, int]:
    _preamble, _frontmatter, _separator, body = split_markdown_frontmatter(text)
    prefix = text[: len(text) - len(body)]
    return body, prefix.count("\n")


def _markdown_fence_marker(stripped_line: str) -> str | None:
    if stripped_line.startswith("```"):
        return "```"
    if stripped_line.startswith("~~~"):
        return "~~~"
    return None


def _iter_markdown_fences(text: str) -> tuple[MarkdownFence, ...]:
    fences: list[MarkdownFence] = []
    active_marker: str | None = None
    active_info = ""
    active_start_line = 0
    active_body: list[str] = []

    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        marker = _markdown_fence_marker(stripped)
        if marker is None:
            if active_marker is not None:
                active_body.append(line)
            continue

        if active_marker is None:
            active_marker = marker
            active_info = stripped[len(marker) :].strip()
            active_start_line = line_number
            active_body = []
            continue

        if marker == active_marker:
            fences.append(
                MarkdownFence(
                    info=active_info,
                    body="\n".join(active_body),
                    start_line=active_start_line,
                    end_line=line_number,
                )
            )
            active_marker = None
            active_info = ""
            active_start_line = 0
            active_body = []
            continue

        active_body.append(line)

    return tuple(fences)


def _iter_unfenced_lines(text: str) -> tuple[tuple[int, str], ...]:
    lines: list[tuple[int, str]] = []
    active_marker: str | None = None

    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        marker = _markdown_fence_marker(stripped)
        if marker is not None:
            if active_marker is None:
                active_marker = marker
            elif marker == active_marker:
                active_marker = None
            continue
        if active_marker is not None:
            continue
        lines.append((line_number, line))
    return tuple(lines)


def _count_raw_includes(text: str) -> int:
    return sum(1 for _line_number, line in _iter_unfenced_lines(text) if parse_at_include_path(line.strip()))


def _count_shell_fences(text: str) -> int:
    count = 0
    for fence in _iter_markdown_fences(_body_without_frontmatter(text)):
        language = fence.info.lower().split(None, 1)[0] if fence.info else ""
        if language in DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES:
            count += 1
    return count


def _inspect_visible_schema_examples(
    text: str,
    path: str,
) -> tuple[int, tuple[InvalidGpdReturnExample, ...], tuple[InvalidFrontmatterExample, ...]]:
    body, line_offset = _body_without_frontmatter_with_line_offset(text)
    visible_count = 0
    invalid_return_examples: list[InvalidGpdReturnExample] = []
    invalid_frontmatter_examples: list[InvalidFrontmatterExample] = []

    for fence in _iter_markdown_fences(body):
        language = fence.info.lower().split(None, 1)[0] if fence.info else ""
        invalid_frontmatter = _inspect_verification_frontmatter_example(
            fence,
            path=path,
            line_offset=line_offset,
            language=language,
        )
        is_schema_block = _is_visible_schema_fence(language, fence.body)
        if not is_schema_block and invalid_frontmatter is None:
            continue
        visible_count += 1
        if invalid_frontmatter is not None:
            invalid_frontmatter_examples.append(invalid_frontmatter)
        if invalid_frontmatter is not None or not _contains_visible_gpd_return_example(fence.body):
            continue
        validation = validate_gpd_return_markdown(f"```yaml\n{fence.body}\n```")
        if validation.passed:
            continue
        invalid_return_examples.append(
            InvalidGpdReturnExample(
                path=path,
                start_line=fence.start_line + line_offset,
                end_line=fence.end_line + line_offset,
                errors=tuple(validation.errors),
                preview=_preview_fence_body(fence.body),
            )
        )

    spawn_contract_count = len(_SPAWN_CONTRACT_RE.findall(body))
    visible_count += spawn_contract_count
    return visible_count, tuple(invalid_return_examples), tuple(invalid_frontmatter_examples)


def _inspect_verification_frontmatter_example(
    fence: MarkdownFence,
    *,
    path: str,
    line_offset: int,
    language: str,
) -> InvalidFrontmatterExample | None:
    candidate = _verification_frontmatter_candidate_from_fence(fence, language=language)
    if candidate is None:
        return None
    candidate_text, meta = candidate
    fields = _invalid_verification_frontmatter_fields(meta)
    if not fields:
        return None
    errors = _verification_frontmatter_lint_errors(candidate_text, fields)
    if not errors:
        return None
    return InvalidFrontmatterExample(
        path=path,
        start_line=fence.start_line + line_offset,
        end_line=fence.end_line + line_offset,
        schema_name="verification",
        fields=fields,
        errors=errors,
        preview=_preview_fence_body(fence.body),
    )


def _verification_frontmatter_candidate_from_fence(
    fence: MarkdownFence,
    *,
    language: str,
) -> tuple[str, Mapping[str, object]] | None:
    if language in DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES:
        return None
    if language in _MARKDOWN_FRONTMATTER_FENCE_LANGUAGES:
        candidate_text = fence.body.lstrip()
        if not _starts_with_markdown_frontmatter(candidate_text):
            return None
        try:
            meta, _body = extract_frontmatter(candidate_text)
        except FrontmatterParseError:
            return None
        if not _looks_like_verification_frontmatter(meta):
            return None
        return candidate_text, meta
    if language not in {"yaml", "yml"}:
        return None
    try:
        parsed = yaml.safe_load(fence.body)
    except yaml.YAMLError:
        return None
    if not isinstance(parsed, Mapping):
        return None
    meta = {key: value for key, value in parsed.items() if isinstance(key, str)}
    if not _looks_like_verification_frontmatter(meta):
        return None
    return f"---\n{fence.body.rstrip()}\n---\n", meta


def _starts_with_markdown_frontmatter(text: str) -> bool:
    return text.startswith("---\n") or text.startswith("---\r\n")


def _looks_like_verification_frontmatter(meta: Mapping[str, object]) -> bool:
    keys = frozenset(key for key in meta if isinstance(key, str))
    if not keys:
        return False
    unsupported_keys = keys & frozenset(UNSUPPORTED_FRONTMATTER_FIELDS["verification"])
    verification_key_count = len(keys & _VERIFICATION_FRONTMATTER_KEYS)
    if keys & _VERIFICATION_FRONTMATTER_STRONG_KEYS:
        return True
    if "phase" in keys and keys & {"verified", "status", "score", "plan_contract_ref"}:
        return True
    if verification_key_count >= 2:
        return True
    return bool(unsupported_keys and keys & {"phase", "status", "verified", "score"})


def _invalid_verification_frontmatter_fields(meta: Mapping[str, object]) -> tuple[str, ...]:
    unsupported = frozenset(UNSUPPORTED_FRONTMATTER_FIELDS["verification"])
    fields = [field for field in sorted(unsupported) if field in meta]
    if "status" in meta:
        raw_status = meta.get("status")
        if not isinstance(raw_status, str) or raw_status.strip() not in VERIFICATION_REPORT_STATUSES:
            fields.append("status")
    return tuple(dict.fromkeys(fields))


def _verification_frontmatter_lint_errors(candidate_text: str, fields: Sequence[str]) -> tuple[str, ...]:
    field_set = frozenset(fields)
    try:
        validation = validate_frontmatter(candidate_text, "verification")
    except FrontmatterParseError:
        return ()
    return tuple(error for error in validation.errors if _verification_frontmatter_lint_error_field(error) in field_set)


def _verification_frontmatter_lint_error_field(error: str) -> str | None:
    field, separator, _detail = error.partition(":")
    if not separator:
        return None
    return field.strip()


def _scan_return_field_mentions_for_repo(
    repo_root: Path,
    *,
    include_tests: bool,
) -> tuple[PromptReturnFieldMention, ...]:
    mentions: list[PromptReturnFieldMention] = []
    for path in _duplicate_scan_paths(repo_root, include_tests=include_tests):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        mentions.extend(_scan_return_field_mentions(text, _relative_path(path, repo_root)))
    return tuple(
        sorted(
            mentions,
            key=lambda mention: (
                mention.path,
                mention.line,
                mention.field,
                mention.mention_kind,
            ),
        )
    )


def _scan_return_field_mentions(text: str, path: str) -> tuple[PromptReturnFieldMention, ...]:
    body, line_offset = _body_without_frontmatter_with_line_offset(text)
    mentions: list[PromptReturnFieldMention] = []
    mentions.extend(_scan_direct_return_field_references(body, path, line_offset=line_offset))
    mentions.extend(_scan_return_field_declarations(body, path, line_offset=line_offset))
    mentions.extend(_scan_yaml_return_field_keys(body, path, line_offset=line_offset))
    return tuple(_dedupe_return_field_mentions(mentions))


def _scan_forbidden_child_return_synthesis_mentions(
    sources: Sequence[PromptSource],
) -> tuple[ForbiddenChildReturnSynthesisMention, ...]:
    mentions: list[ForbiddenChildReturnSynthesisMention] = []
    for source in sources:
        if source.kind != "workflow":
            continue
        try:
            text = source.absolute_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        body, line_offset = _body_without_frontmatter_with_line_offset(text)
        for line_number, line in _iter_unfenced_lines(body):
            for clause in _child_return_synthesis_clauses(line):
                action = _forbidden_child_return_synthesis_action(clause)
                if action is None:
                    continue
                mentions.append(
                    ForbiddenChildReturnSynthesisMention(
                        path=source.path,
                        line=line_number + line_offset,
                        action=action,
                        polarity="positive",
                        severity="error",
                        snippet=_prompt_line_snippet(clause),
                    )
                )
    return tuple(
        sorted(
            mentions,
            key=lambda mention: (
                mention.path,
                mention.line,
                mention.action,
                mention.snippet,
            ),
        )
    )


def _child_return_synthesis_clauses(line: str) -> tuple[str, ...]:
    normalized = re.sub(r"^\s*(?:[-*+]|\d+[.)]|#+|>)\s*", "", line).strip()
    normalized = normalized.strip("`*_ ")
    normalized = re.sub(r"\s+", " ", normalized)
    if not normalized:
        return ()
    return tuple(
        part.strip(" -") for part in _CHILD_RETURN_SYNTHESIS_CLAUSE_SPLIT_RE.split(normalized) if part.strip(" -")
    ) or (normalized,)


def _forbidden_child_return_synthesis_action(clause: str) -> str | None:
    action_match = _CHILD_RETURN_SYNTHESIS_ACTION_RE.search(clause)
    if action_match is None:
        return None
    if not _CHILD_RETURN_SYNTHESIS_CONTEXT_RE.search(clause):
        return None
    if _CHILD_RETURN_SYNTHESIS_NEGATION_RE.search(clause):
        return None
    if _is_main_context_fallback_return_clause(clause):
        return None
    return action_match.group("action").casefold().replace(" ", "-")


def _is_main_context_fallback_return_clause(clause: str) -> bool:
    folded = clause.casefold()
    if "fallback" not in folded:
        return False
    has_main_context = "main-context" in folded or "main context" in folded
    has_own_return = ("own" in folded or "owns" in folded) and (
        "gpd_return" in folded or "return envelope" in folded or "own return" in folded
    )
    return has_main_context and has_own_return


def _scan_direct_return_field_references(
    body: str,
    path: str,
    *,
    line_offset: int,
) -> tuple[PromptReturnFieldMention, ...]:
    mentions: list[PromptReturnFieldMention] = []
    for line_number, line in enumerate(body.splitlines(), start=1):
        for match in _GPD_RETURN_FIELD_REFERENCE_RE.finditer(line):
            mentions.append(
                _build_return_field_mention(
                    path=path,
                    line=line_number + line_offset,
                    field=match.group(1),
                    mention_kind="direct_reference",
                    snippet=line,
                )
            )
    return tuple(mentions)


def _scan_return_field_declarations(
    body: str,
    path: str,
    *,
    line_offset: int,
) -> tuple[PromptReturnFieldMention, ...]:
    mentions: list[PromptReturnFieldMention] = []
    for line_number, line in _iter_unfenced_lines(body):
        declaration_match = _RETURN_FIELD_DECLARATION_RE.search(line)
        if declaration_match is None:
            continue
        mention_kind: Literal["extended_field_list", "role_field_statement"] = (
            "role_field_statement" if _ROLE_FIELD_DECLARATION_RE.search(line) else "extended_field_list"
        )
        for field in _declared_return_fields(line, declaration_match):
            mentions.append(
                _build_return_field_mention(
                    path=path,
                    line=line_number + line_offset,
                    field=field,
                    mention_kind=mention_kind,
                    snippet=line,
                )
            )
    return tuple(mentions)


def _declared_return_fields(line: str, declaration_match: re.Match[str]) -> tuple[str, ...]:
    field_span = line[declaration_match.end() :]
    backticked = tuple(_BACKTICK_IDENTIFIER_RE.findall(field_span))
    if backticked:
        return tuple(field for field in backticked if field != "gpd_return")

    declaration_text = declaration_match.group(0).casefold()
    has_explicit_list_intro = (
        ":" in field_span or "such as" in declaration_text or re.search(r"\bsuch as\b", field_span, re.IGNORECASE)
    )
    if not has_explicit_list_intro:
        return ()

    such_as_match = re.search(r"\bsuch as\b", field_span, re.IGNORECASE)
    if such_as_match is not None:
        field_span = field_span[such_as_match.end() :]
    colon_index = field_span.find(":")
    if colon_index >= 0:
        field_span = field_span[colon_index + 1 :]
    if "." in field_span:
        field_span = field_span.split(".", 1)[0]
    fields = []
    for field in _IDENTIFIER_RE.findall(field_span):
        if field.casefold() in _FIELD_DECLARATION_STOP_WORDS:
            continue
        fields.append(field)
    return tuple(fields)


def _scan_yaml_return_field_keys(
    body: str,
    path: str,
    *,
    line_offset: int,
) -> tuple[PromptReturnFieldMention, ...]:
    mentions: list[PromptReturnFieldMention] = []
    for fence in _iter_markdown_fences(body):
        language = fence.info.lower().split(None, 1)[0] if fence.info else ""
        if language not in {"yaml", "yml"}:
            continue
        if not _contains_visible_gpd_return_example(fence.body):
            continue
        try:
            parsed = yaml.safe_load(fence.body)
        except yaml.YAMLError:
            continue
        if not isinstance(parsed, Mapping):
            continue
        raw_envelope = parsed.get("gpd_return")
        if not isinstance(raw_envelope, Mapping):
            continue
        for raw_field in raw_envelope:
            if not isinstance(raw_field, str):
                continue
            mentions.append(
                _build_return_field_mention(
                    path=path,
                    line=_yaml_return_field_line(fence.body, raw_field, fence.start_line + line_offset),
                    field=raw_field,
                    mention_kind="yaml_example_key",
                    snippet=f"{raw_field}:",
                )
            )
    return tuple(mentions)


def _yaml_return_field_line(body: str, field: str, fence_start_line: int) -> int:
    in_gpd_return = False
    gpd_return_indent = -1
    child_indent: int | None = None
    for offset, line in enumerate(body.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _YAML_KEY_RE.match(line)
        if match is None:
            continue
        indent = len(match.group("indent").replace("\t", "    "))
        key = match.group("key").strip("'\"")
        if not in_gpd_return:
            if key == "gpd_return":
                in_gpd_return = True
                gpd_return_indent = indent
            continue
        if indent <= gpd_return_indent:
            break
        if child_indent is None:
            child_indent = indent
        if indent == child_indent and key == field:
            return fence_start_line + offset
    return fence_start_line


def _dedupe_return_field_mentions(
    mentions: Sequence[PromptReturnFieldMention],
) -> tuple[PromptReturnFieldMention, ...]:
    seen: set[tuple[str, int, str, str, str]] = set()
    deduped: list[PromptReturnFieldMention] = []
    for mention in mentions:
        key = (
            mention.path,
            mention.line,
            mention.field,
            mention.mention_kind,
            mention.polarity,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(mention)
    return tuple(deduped)


def _build_return_field_mention(
    *,
    path: str,
    line: int,
    field: str,
    mention_kind: Literal[
        "direct_reference",
        "extended_field_list",
        "role_field_statement",
        "yaml_example_key",
    ],
    snippet: str,
) -> PromptReturnFieldMention:
    allowed_source = _return_field_allowed_source(field)
    allowed = allowed_source != "unknown"
    polarity: Literal["positive", "negative"] = "negative" if _RETURN_FIELD_NEGATION_RE.search(snippet) else "positive"
    severity: Literal["info", "warn", "error"] = "info"
    if not allowed and polarity == "positive":
        severity = "error"
    return PromptReturnFieldMention(
        path=path,
        line=line,
        field=field,
        mention_kind=mention_kind,
        polarity=polarity,
        allowed=allowed,
        allowed_source=allowed_source,
        severity=severity,
        snippet=_prompt_line_snippet(snippet),
        suggestion=_return_field_suggestion(field) if not allowed else None,
    )


def _allowed_return_fields() -> frozenset[str]:
    return frozenset(GpdReturnEnvelope.model_fields) | frozenset(ALLOWED_RETURN_EXTENSION_FIELDS)


def _return_field_allowed_source(field: str) -> Literal["base", "extension", "unknown"]:
    if field in GpdReturnEnvelope.model_fields:
        return "base"
    if field in ALLOWED_RETURN_EXTENSION_FIELDS:
        return "extension"
    return "unknown"


def _return_field_suggestion(field: str) -> str | None:
    matches = difflib.get_close_matches(field, sorted(_allowed_return_fields()), n=1)
    return matches[0] if matches else None


def _prompt_line_snippet(line: str, max_chars: int = 180) -> str:
    snippet = re.sub(r"\s+", " ", line.strip())
    if len(snippet) <= max_chars:
        return snippet
    return snippet[: max_chars - 3].rstrip() + "..."


def _disallowed_return_field_mentions(
    mentions: Sequence[PromptReturnFieldMention],
) -> tuple[PromptReturnFieldMention, ...]:
    return tuple(mention for mention in mentions if mention.severity == "error")


def _is_visible_schema_fence(language: str, body: str) -> bool:
    if language in _SCHEMA_FENCE_LANGUAGES:
        return True
    if language in DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES:
        return False
    return any(marker in body for marker in _SCHEMA_BLOCK_MARKERS)


def _contains_visible_gpd_return_example(body: str) -> bool:
    return bool(_GPD_RETURN_EXAMPLE_RE.search(body))


def _preview_fence_body(body: str, max_chars: int = 140) -> str:
    preview = " ".join(line.strip() for line in body.splitlines() if line.strip())
    if len(preview) <= max_chars:
        return preview
    return preview[: max_chars - 3].rstrip() + "..."


def _hard_gate_metrics(text: str) -> tuple[int, float]:
    body = _body_without_frontmatter(text)
    lines = [(line_number, line) for line_number, line in _iter_unfenced_lines(body) if line.strip()]
    hard_gate_count = sum(1 for _line_number, line in lines if _HARD_GATE_LINE_RE.search(line))
    density = hard_gate_count / len(lines) if lines else 0.0
    return hard_gate_count, round(density, 6)


def _count_shell_parsing_lines(text: str) -> int:
    body = _body_without_frontmatter(text)
    count = 0
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.fullmatch(r"`?/?gpd:?help`?", stripped):
            continue
        if _SHELL_PARSING_RE.search(stripped):
            count += 1
    return count


def _measure_runtime_projection(
    source: PromptSource,
    raw_text: str,
    expanded_text: str,
    runtime_name: str,
) -> RuntimeProjectionMetric:
    descriptor = get_runtime_descriptor(runtime_name)
    projected_text = project_markdown_for_runtime(
        raw_text,
        runtime=runtime_name,
        path_prefix=DEFAULT_PATH_PREFIX,
        surface_kind=source.kind,
        src_root=source.src_root,
        protect_agent_prompt_body=source.kind == "agent",
        command_name=source.name,
    )
    bridge_command = _projection_bridge_command(runtime_name) if source.kind == "command" else None
    runtime_note_lines = [line for line in projected_text.splitlines() if _RUNTIME_NOTE_RE.search(line)]
    expanded_line_count = _line_count(expanded_text)
    expanded_char_count = len(expanded_text)
    projected_line_count = _line_count(projected_text)
    projected_char_count = len(projected_text)
    line_delta = projected_line_count - expanded_line_count
    char_delta = projected_char_count - expanded_char_count
    return RuntimeProjectionMetric(
        runtime=runtime_name,
        native_include_support=descriptor.native_include_support,
        expanded_line_count=expanded_line_count,
        expanded_char_count=expanded_char_count,
        line_count=projected_line_count,
        char_count=projected_char_count,
        line_delta=line_delta,
        char_delta=char_delta,
        char_delta_percent=_percent_delta(char_delta, expanded_char_count),
        include_count=_count_raw_includes(projected_text),
        runtime_note_count=len(runtime_note_lines),
        runtime_note_chars=sum(len(line) for line in runtime_note_lines),
        shell_fence_count=_count_shell_fences(projected_text),
        shell_rewrite_count=_count_shell_fences_containing(projected_text, bridge_command),
        bridge_command_occurrences=len(_BRIDGE_COMMAND_RE.findall(projected_text)),
    )


def _projection_bridge_command(runtime_name: str) -> str:
    descriptor = get_runtime_descriptor(runtime_name)
    target_dir = projection_target_dir_from_path_prefix(
        DEFAULT_PATH_PREFIX,
        config_dir_name=descriptor.config_dir_name,
    )
    return build_runtime_cli_bridge_command(
        runtime_name,
        target_dir=target_dir,
        config_dir_name=descriptor.config_dir_name,
        is_global=False,
    )


def _count_shell_fences_containing(text: str, needle: str | None) -> int:
    if not needle:
        return 0

    count = 0
    for fence in _iter_markdown_fences(_body_without_frontmatter(text)):
        language = fence.info.lower().split(None, 1)[0] if fence.info else ""
        if language in DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES and needle in fence.body:
            count += 1
    return count


def _build_stage_diagnostics(
    sources: Sequence[PromptSource],
    items: Sequence[PromptSurfaceItem],
    *,
    report_warnings: list[str],
) -> tuple[StageAwareWorkflowPromptMetric, ...]:
    items_by_command = {(item.kind, item.name): item for item in items if item.kind == "command"}
    diagnostics: list[StageAwareWorkflowPromptMetric] = []
    for source in sources:
        if source.kind != "command":
            continue
        command_item = items_by_command.get((source.kind, source.name))
        if command_item is None:
            continue
        manifest_path = _stage_manifest_path_for_command(source)
        if not manifest_path.is_file():
            continue
        metric = _build_stage_diagnostic_for_command(source, command_item, manifest_path)
        if metric is None:
            report_warnings.append(
                f"could not load stage diagnostics for {source.name}: {_relative_path(manifest_path, source.repo_root)}"
            )
            continue
        diagnostics.append(metric)
    return tuple(sorted(diagnostics, key=lambda metric: (metric.workflow_id, metric.command_name)))


def _stage_manifest_path_for_command(source: PromptSource) -> Path:
    return source.src_root / "specs" / "workflows" / f"{source.name}-stage-manifest.json"


def _build_stage_diagnostic_for_command(
    source: PromptSource,
    command_item: PromptSurfaceItem,
    manifest_path: Path,
) -> StageAwareWorkflowPromptMetric | None:
    warnings: list[str] = []
    manifest = _load_stage_manifest_for_source(source, manifest_path, warnings)
    if manifest is None:
        return None

    command_text = source.absolute_path.read_text(encoding="utf-8")
    first_turn_trace = _include_trace_from_text(
        command_text,
        source.src_root,
        source.repo_root,
        active_authorities=frozenset(),
    )
    stages = tuple(
        _measure_workflow_stage(
            source=source,
            manifest=manifest,
            stage=stage,
            first_turn_trace=first_turn_trace,
        )
        for stage in sorted(manifest.stages, key=lambda candidate: candidate.order)
    )
    violation_count = sum(len(stage.must_not_eager_load_violations) for stage in stages)
    return StageAwareWorkflowPromptMetric(
        workflow_id=manifest.workflow_id,
        command_name=source.name,
        command_path=source.path,
        manifest_path=_relative_path(manifest_path, source.repo_root),
        stage_count=len(stages),
        first_turn_line_count=command_item.expanded_line_count,
        first_turn_char_count=command_item.expanded_char_count,
        first_turn_raw_include_count=command_item.raw_include_count,
        runtime_projection=command_item.runtime_projection,
        stages=stages,
        violation_count=violation_count,
        warnings=tuple(warnings),
    )


def _load_stage_manifest_for_source(
    source: PromptSource,
    manifest_path: Path,
    warnings: list[str],
) -> WorkflowStageManifest | None:
    try:
        return load_workflow_stage_manifest_from_path(
            manifest_path,
            expected_workflow_id=source.name,
            known_init_fields=known_init_fields_for_workflow(source.name),
        )
    except ValueError as exc:
        if _is_package_source_root(source.src_root):
            warnings.append(str(exc))
            return None
        try:
            return _load_local_source_stage_manifest(manifest_path, source)
        except (OSError, ValueError, json.JSONDecodeError) as fallback_exc:
            warnings.append(f"{exc}; fallback parser failed: {fallback_exc}")
            return None


def _is_package_source_root(src_root: Path) -> bool:
    try:
        return src_root.resolve() == Path(__file__).resolve().parents[1]
    except OSError:
        return False


def _load_local_source_stage_manifest(manifest_path: Path, source: PromptSource) -> WorkflowStageManifest:
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("workflow stage manifest must be a JSON object")
    if raw.get("schema_version") != 1:
        raise ValueError("workflow stage manifest schema_version must be 1")
    workflow_id = _manifest_string(raw.get("workflow_id"), label="workflow_id")
    if workflow_id != source.name:
        raise ValueError(f"workflow stage manifest workflow_id must be {source.name!r}, got {workflow_id!r}")
    stages_raw = raw.get("stages")
    if not isinstance(stages_raw, list) or not stages_raw:
        raise ValueError("stages must be a non-empty list")

    stages = tuple(
        _load_local_source_stage(stage_raw, index=index, source=source) for index, stage_raw in enumerate(stages_raw)
    )
    stage_orders = [stage.order for stage in stages]
    if stage_orders != list(range(1, len(stages) + 1)):
        raise ValueError("stage order values must start at 1 and increase by 1")
    stage_ids = [stage.id for stage in stages]
    if len(stage_ids) != len(set(stage_ids)):
        raise ValueError("stage ids must be unique")
    return WorkflowStageManifest(
        schema_version=1,
        workflow_id=workflow_id,
        stages=stages,
        prompt_usage=_manifest_string(raw.get("prompt_usage", "staged_init"), label="prompt_usage"),
    )


def _load_local_source_stage(raw: object, *, index: int, source: PromptSource) -> WorkflowStage:
    if not isinstance(raw, dict):
        raise ValueError(f"stages[{index}] must be a JSON object")
    mode_paths = tuple(
        _normalize_local_authority_id(value, source=source, label=f"stages[{index}].mode_paths")
        for value in _manifest_string_list(raw.get("mode_paths"), label=f"stages[{index}].mode_paths")
    )
    loaded_authorities = tuple(
        _normalize_local_authority_id(value, source=source, label=f"stages[{index}].loaded_authorities")
        for value in _manifest_string_list(
            raw.get("loaded_authorities", []),
            label=f"stages[{index}].loaded_authorities",
        )
    )
    conditional_authorities = tuple(
        _load_local_conditional_authority(entry, index=index, conditional_index=conditional_index, source=source)
        for conditional_index, entry in enumerate(
            _manifest_list(raw.get("conditional_authorities", []), label=f"stages[{index}].conditional_authorities")
        )
    )
    must_not_eager_load = tuple(
        _normalize_local_authority_id(value, source=source, label=f"stages[{index}].must_not_eager_load")
        for value in _manifest_string_list(
            raw.get("must_not_eager_load", []),
            label=f"stages[{index}].must_not_eager_load",
        )
    )
    return WorkflowStage(
        id=_manifest_string(raw.get("id"), label=f"stages[{index}].id"),
        order=_manifest_int(raw.get("order"), label=f"stages[{index}].order"),
        purpose=_manifest_string(raw.get("purpose"), label=f"stages[{index}].purpose"),
        mode_paths=mode_paths,
        required_init_fields=tuple(
            _manifest_string_list(
                raw.get("required_init_fields", []),
                label=f"stages[{index}].required_init_fields",
            )
        ),
        loaded_authorities=loaded_authorities,
        conditional_authorities=conditional_authorities,
        must_not_eager_load=must_not_eager_load,
        allowed_tools=tuple(
            _manifest_string_list(raw.get("allowed_tools", []), label=f"stages[{index}].allowed_tools")
        ),
        writes_allowed=tuple(
            _manifest_string_list(raw.get("writes_allowed", []), label=f"stages[{index}].writes_allowed")
        ),
        produced_state=tuple(
            _manifest_string_list(raw.get("produced_state", []), label=f"stages[{index}].produced_state")
        ),
        next_stages=tuple(_manifest_string_list(raw.get("next_stages", []), label=f"stages[{index}].next_stages")),
        checkpoints=tuple(_manifest_string_list(raw.get("checkpoints", []), label=f"stages[{index}].checkpoints")),
    )


def _load_local_conditional_authority(
    raw: object,
    *,
    index: int,
    conditional_index: int,
    source: PromptSource,
) -> WorkflowStageConditionalAuthority:
    if not isinstance(raw, dict):
        raise ValueError(f"stages[{index}].conditional_authorities[{conditional_index}] must be an object")
    return WorkflowStageConditionalAuthority(
        when=_manifest_string(
            raw.get("when"),
            label=f"stages[{index}].conditional_authorities[{conditional_index}].when",
        ),
        authorities=tuple(
            _normalize_local_authority_id(
                value,
                source=source,
                label=f"stages[{index}].conditional_authorities[{conditional_index}].authorities",
            )
            for value in _manifest_string_list(
                raw.get("authorities", []),
                label=f"stages[{index}].conditional_authorities[{conditional_index}].authorities",
            )
        ),
    )


def _manifest_string(raw: object, *, label: str) -> str:
    if not isinstance(raw, str) or not raw:
        raise ValueError(f"{label} must be a non-empty string")
    return raw


def _manifest_int(raw: object, *, label: str) -> int:
    if not isinstance(raw, int):
        raise ValueError(f"{label} must be an integer")
    return raw


def _manifest_list(raw: object, *, label: str) -> tuple[object, ...]:
    if not isinstance(raw, list):
        raise ValueError(f"{label} must be a list")
    return tuple(raw)


def _manifest_string_list(raw: object, *, label: str) -> tuple[str, ...]:
    values = _manifest_list(raw, label=label)
    for value in values:
        if not isinstance(value, str):
            raise ValueError(f"{label} must contain only strings")
    return cast(tuple[str, ...], values)


def _normalize_local_authority_id(raw: str, *, source: PromptSource, label: str) -> str:
    authority = _normalize_authority_id(raw, label=label)
    path = _authority_path(source.src_root, authority)
    if not path.is_file():
        raise ValueError(f"{label} must reference an existing markdown file: {authority}")
    return authority


def _measure_workflow_stage(
    *,
    source: PromptSource,
    manifest: WorkflowStageManifest,
    stage: WorkflowStage,
    first_turn_trace: _IncludeTrace,
) -> WorkflowStagePromptMetric:
    eager_authorities = stage.eager_authorities()
    lazy_authorities = stage.must_not_eager_load
    eager_metrics = tuple(_measure_authority(source, authority) for authority in eager_authorities)
    lazy_metrics = tuple(_measure_authority(source, authority) for authority in lazy_authorities)
    violations = _must_not_eager_load_violations(
        source=source,
        workflow_id=manifest.workflow_id,
        stage=stage,
        eager_authorities=eager_authorities,
        first_turn_trace=first_turn_trace,
    )
    return WorkflowStagePromptMetric(
        workflow_id=manifest.workflow_id,
        stage_id=stage.id,
        order=stage.order,
        eager_authorities=eager_authorities,
        eager_authority_metrics=eager_metrics,
        eager_line_count=sum(metric.expanded_line_count for metric in eager_metrics),
        eager_char_count=sum(metric.expanded_char_count for metric in eager_metrics),
        lazy_authorities=lazy_authorities,
        lazy_authority_metrics=lazy_metrics,
        lazy_line_count=sum(metric.expanded_line_count for metric in lazy_metrics),
        lazy_char_count=sum(metric.expanded_char_count for metric in lazy_metrics),
        must_not_eager_load_violations=violations,
    )


def _measure_authority(source: PromptSource, authority: str) -> AuthorityPromptMetric:
    path = _authority_path(source.src_root, authority)
    raw_text = path.read_text(encoding="utf-8")
    expanded_text = expand_at_includes(raw_text, source.src_root, DEFAULT_PATH_PREFIX)
    include_trace = _include_trace_from_text(
        raw_text,
        source.src_root,
        source.repo_root,
        active_authorities=frozenset({authority}),
    )
    return AuthorityPromptMetric(
        authority=authority,
        path=_relative_path(path, source.repo_root),
        raw_line_count=_line_count(raw_text),
        raw_char_count=len(raw_text),
        raw_include_count=_count_raw_includes(raw_text),
        expanded_line_count=_line_count(expanded_text),
        expanded_char_count=len(expanded_text),
        transitive_include_authorities=include_trace.authorities,
    )


def _must_not_eager_load_violations(
    *,
    source: PromptSource,
    workflow_id: str,
    stage: WorkflowStage,
    eager_authorities: tuple[str, ...],
    first_turn_trace: _IncludeTrace,
) -> tuple[MustNotEagerLoadViolation, ...]:
    lazy_authorities = set(stage.must_not_eager_load)
    eager_authority_set = set(eager_authorities)
    violations: list[MustNotEagerLoadViolation] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()

    def add(authority: str, violation_source: str, eager_via: tuple[str, ...]) -> None:
        key = (authority, violation_source, eager_via)
        if key in seen:
            return
        seen.add(key)
        violations.append(_must_not_violation(workflow_id, stage.id, authority, violation_source, eager_via=eager_via))

    for authority in sorted(lazy_authorities.intersection(eager_authority_set)):
        add(authority, "manifest_overlap", (authority,))

    for authority in sorted(lazy_authorities):
        for chain in first_turn_trace.chains_by_authority.get(authority, ()):
            if len(chain) == 1:
                add(authority, "first_turn_direct_include", chain)
            elif len(chain) > 1:
                add(authority, "first_turn_transitive_include", chain[:-1])

    for eager_authority in eager_authorities:
        eager_path = _authority_path(source.src_root, eager_authority)
        if not eager_path.is_file():
            continue
        trace = _include_trace_from_path(
            eager_path,
            source.src_root,
            source.repo_root,
            authority=eager_authority,
        )
        for authority in sorted(lazy_authorities):
            for chain in trace.chains_by_authority.get(authority, ()):
                add(authority, "stage_eager_transitive_include", (eager_authority, *chain[:-1]))

    return tuple(violations)


def _must_not_violation(
    workflow_id: str,
    stage_id: str,
    authority: str,
    violation_source: Literal[
        "manifest_overlap",
        "first_turn_direct_include",
        "first_turn_transitive_include",
        "stage_eager_transitive_include",
        "conditional_eager_overlap",
    ]
    | str,
    *,
    eager_via: tuple[str, ...],
) -> MustNotEagerLoadViolation:
    return MustNotEagerLoadViolation(
        workflow_id=workflow_id,
        stage_id=stage_id,
        authority=authority,
        violation_source=cast(
            Literal[
                "manifest_overlap",
                "first_turn_direct_include",
                "first_turn_transitive_include",
                "stage_eager_transitive_include",
                "conditional_eager_overlap",
            ],
            violation_source,
        ),
        eager_via=eager_via,
    )


def _include_trace_from_path(path: Path, src_root: Path, repo_root: Path, *, authority: str) -> _IncludeTrace:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return _IncludeTrace(authorities=(), chains_by_authority={})
    return _include_trace_from_text(
        raw_text,
        src_root,
        repo_root,
        active_authorities=frozenset({authority}),
    )


def _include_trace_from_text(
    text: str,
    src_root: Path,
    repo_root: Path,
    *,
    active_authorities: frozenset[str],
) -> _IncludeTrace:
    del repo_root
    ordered: list[str] = []
    chains_by_authority: dict[str, list[tuple[str, ...]]] = defaultdict(list)

    def add_chain(authority: str, chain: tuple[str, ...]) -> None:
        if authority not in ordered:
            ordered.append(authority)
        if chain not in chains_by_authority[authority]:
            chains_by_authority[authority].append(chain)

    def visit(current_text: str, active: frozenset[str], prefix: tuple[str, ...]) -> None:
        for _line_number, line in _iter_unfenced_lines(_body_without_frontmatter(current_text)):
            include_path = parse_at_include_path(line.strip())
            authority = _authority_id_from_include_path(include_path)
            if authority is None:
                continue
            chain = (*prefix, authority)
            add_chain(authority, chain)
            if authority in active:
                continue
            authority_path = _authority_path(src_root, authority)
            if not authority_path.is_file():
                continue
            try:
                included_text = authority_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            visit(included_text, active | {authority}, chain)

    visit(text, active_authorities, ())
    return _IncludeTrace(
        authorities=tuple(ordered),
        chains_by_authority={authority: tuple(chains) for authority, chains in chains_by_authority.items()},
    )


def _authority_id_from_include_path(include_path: str | None) -> str | None:
    if include_path is None:
        return None
    for prefix in ("{GPD_INSTALL_DIR}/", "get-physics-done/"):
        if include_path.startswith(prefix):
            candidate = include_path[len(prefix) :]
            return _normalize_authority_id_or_none(candidate)
    return _normalize_authority_id_or_none(include_path)


def _normalize_authority_id_or_none(candidate: str) -> str | None:
    try:
        return _normalize_authority_id(candidate, label="include")
    except ValueError:
        return None


def _normalize_authority_id(raw: str, *, label: str) -> str:
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{label} must be a normalized relative POSIX path")
    normalized = path.as_posix()
    if normalized != raw:
        raise ValueError(f"{label} must be a normalized relative POSIX path")
    if path.suffix != ".md":
        raise ValueError(f"{label} must reference a markdown file")
    if not normalized.startswith(("workflows/", "references/", "templates/")):
        raise ValueError(f"{label} must reference workflows/, references/, or templates/")
    return normalized


def _authority_path(src_root: Path, authority: str) -> Path:
    return src_root / "specs" / authority


def _stage_diagnostics_totals(stage_diagnostics: Sequence[StageAwareWorkflowPromptMetric]) -> dict[str, int]:
    stages = [stage for workflow in stage_diagnostics for stage in workflow.stages]
    return {
        "workflow_count": len(stage_diagnostics),
        "stage_count": len(stages),
        "first_turn_char_count": sum(workflow.first_turn_char_count for workflow in stage_diagnostics),
        "first_turn_line_count": sum(workflow.first_turn_line_count for workflow in stage_diagnostics),
        "eager_char_count": sum(stage.eager_char_count for stage in stages),
        "eager_line_count": sum(stage.eager_line_count for stage in stages),
        "lazy_char_count": sum(stage.lazy_char_count for stage in stages),
        "lazy_line_count": sum(stage.lazy_line_count for stage in stages),
        "must_not_eager_load_violation_count": sum(len(stage.must_not_eager_load_violations) for stage in stages),
    }


def _build_totals(
    items: Sequence[PromptSurfaceItem],
    *,
    stage_diagnostics: Sequence[StageAwareWorkflowPromptMetric] = (),
    return_field_mentions: Sequence[PromptReturnFieldMention] = (),
    forbidden_child_return_synthesis_mentions: Sequence[ForbiddenChildReturnSynthesisMention] = (),
) -> dict[str, object]:
    numeric_fields = (
        "raw_line_count",
        "raw_char_count",
        "raw_include_count",
        "expanded_line_count",
        "expanded_char_count",
        "expanded_include_count",
        "unresolved_include_count",
        "visible_schema_example_count",
        "invalid_gpd_return_example_count",
        "invalid_frontmatter_example_count",
        "return_field_mention_count",
        "disallowed_return_field_mention_count",
        "hard_gate_line_count",
        "shell_fence_count",
        "shell_parsing_line_count",
        "rigidity_index",
    )
    totals: dict[str, object] = {"item_count": len(items)}
    for field in numeric_fields:
        totals[field] = sum(cast(int, getattr(item, field)) for item in items)

    by_kind: dict[str, dict[str, int]] = {}
    for kind in DEFAULT_SURFACES:
        kind_items = [item for item in items if item.kind == kind]
        by_kind[kind] = {"item_count": len(kind_items)}
        for field in numeric_fields:
            by_kind[kind][field] = sum(cast(int, getattr(item, field)) for item in kind_items)
    if return_field_mentions:
        disallowed_mentions = _disallowed_return_field_mentions(return_field_mentions)
        totals["return_field_mention_count"] = len(return_field_mentions)
        totals["disallowed_return_field_mention_count"] = len(disallowed_mentions)
        totals["negative_return_field_mention_count"] = sum(
            1 for mention in return_field_mentions if mention.polarity == "negative"
        )
        totals["allowed_return_field_mention_count"] = sum(1 for mention in return_field_mentions if mention.allowed)
    else:
        totals["negative_return_field_mention_count"] = 0
        totals["allowed_return_field_mention_count"] = 0
    totals["forbidden_child_return_synthesis_mention_count"] = len(forbidden_child_return_synthesis_mentions)
    totals["by_kind"] = by_kind
    totals["runtime_projection"] = _runtime_projection_totals(items)
    totals["stage_diagnostics"] = _stage_diagnostics_totals(stage_diagnostics)
    return totals


def _runtime_projection_totals(items: Sequence[PromptSurfaceItem]) -> dict[str, dict[str, object]]:
    totals: dict[str, dict[str, object]] = {}
    for item in items:
        for metric in item.runtime_projection:
            runtime_totals = totals.setdefault(
                metric.runtime,
                {
                    "native_include_support": metric.native_include_support,
                    "item_count": 0,
                    "expanded_line_count": 0,
                    "expanded_char_count": 0,
                    "line_count": 0,
                    "char_count": 0,
                    "line_delta": 0,
                    "char_delta": 0,
                    "char_delta_percent": 0.0,
                    "include_count": 0,
                    "runtime_note_count": 0,
                    "runtime_note_chars": 0,
                    "shell_fence_count": 0,
                    "shell_rewrite_count": 0,
                    "bridge_command_occurrences": 0,
                },
            )
            runtime_totals["item_count"] = cast(int, runtime_totals["item_count"]) + 1
            runtime_totals["expanded_line_count"] = (
                cast(int, runtime_totals["expanded_line_count"]) + metric.expanded_line_count
            )
            runtime_totals["expanded_char_count"] = (
                cast(int, runtime_totals["expanded_char_count"]) + metric.expanded_char_count
            )
            runtime_totals["line_count"] = cast(int, runtime_totals["line_count"]) + metric.line_count
            runtime_totals["char_count"] = cast(int, runtime_totals["char_count"]) + metric.char_count
            runtime_totals["line_delta"] = cast(int, runtime_totals["line_delta"]) + metric.line_delta
            runtime_totals["char_delta"] = cast(int, runtime_totals["char_delta"]) + metric.char_delta
            runtime_totals["include_count"] = cast(int, runtime_totals["include_count"]) + metric.include_count
            runtime_totals["runtime_note_count"] = (
                cast(int, runtime_totals["runtime_note_count"]) + metric.runtime_note_count
            )
            runtime_totals["runtime_note_chars"] = (
                cast(int, runtime_totals["runtime_note_chars"]) + metric.runtime_note_chars
            )
            runtime_totals["shell_fence_count"] = (
                cast(int, runtime_totals["shell_fence_count"]) + metric.shell_fence_count
            )
            runtime_totals["shell_rewrite_count"] = (
                cast(int, runtime_totals["shell_rewrite_count"]) + metric.shell_rewrite_count
            )
            runtime_totals["bridge_command_occurrences"] = (
                cast(int, runtime_totals["bridge_command_occurrences"]) + metric.bridge_command_occurrences
            )
    for runtime_totals in totals.values():
        runtime_totals["char_delta_percent"] = _percent_delta(
            cast(int, runtime_totals["char_delta"]),
            cast(int, runtime_totals["expanded_char_count"]),
        )
    return totals


def _duplicate_scan_paths(repo_root: Path, *, include_tests: bool) -> tuple[Path, ...]:
    src_root = _source_root_for_repo(repo_root)
    roots = (
        src_root / "commands",
        src_root / "agents",
        src_root / "specs" / "workflows",
        src_root / "specs" / "references",
        src_root / "specs" / "templates",
    )
    paths: list[Path] = []
    for root in roots:
        if root.is_dir():
            paths.extend(path for path in sorted(root.rglob("*.md")) if path.is_file() and not path.is_symlink())
    if include_tests:
        tests_root = repo_root / "tests"
        if tests_root.is_dir():
            paths.extend(path for path in sorted(tests_root.rglob("*.py")) if path.is_file() and not path.is_symlink())
    return tuple(paths)


def _duplicate_invariant_groups(repo_root: Path, *, include_tests: bool) -> tuple[DuplicateInvariantGroup, ...]:
    occurrences: dict[str, list[str]] = defaultdict(list)
    files_by_phrase: dict[str, set[str]] = defaultdict(set)
    non_reference_files_by_phrase: dict[str, set[str]] = defaultdict(set)

    for path in _duplicate_scan_paths(repo_root, include_tests=include_tests):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        relative_path = _relative_path(path, repo_root)
        for line_number, line in _iter_unfenced_lines(_body_without_frontmatter(text)):
            phrase = _normalize_duplicate_line(line)
            if not _is_candidate_duplicate_phrase(phrase):
                continue
            location = f"{relative_path}:{line_number}"
            occurrences[phrase].append(location)
            files_by_phrase[phrase].add(relative_path)
            if not _is_reference_or_template_path(relative_path):
                non_reference_files_by_phrase[phrase].add(relative_path)

    groups: list[DuplicateInvariantGroup] = []
    for phrase, locations in occurrences.items():
        file_count = len(files_by_phrase[phrase])
        non_reference_file_count = len(non_reference_files_by_phrase[phrase])
        if len(locations) < 3 and non_reference_file_count < 2:
            continue
        groups.append(
            DuplicateInvariantGroup(
                phrase=phrase,
                occurrence_count=len(locations),
                file_count=file_count,
                severity=_duplicate_severity(phrase, non_reference_file_count),
                locations=tuple(locations[:30]),
            )
        )

    severity_order = {"high": 0, "warn": 1, "info": 2}
    return tuple(
        sorted(
            groups,
            key=lambda group: (
                severity_order[group.severity],
                -group.file_count,
                -group.occurrence_count,
                group.phrase,
            ),
        )
    )


def _normalize_duplicate_line(line: str) -> str:
    normalized = line.strip()
    normalized = re.sub(r"^\s*(?:[-*+]|\d+[.)]|#+|>)\s*", "", normalized)
    normalized = normalized.strip("`*_ ")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.casefold()


def _is_candidate_duplicate_phrase(phrase: str) -> bool:
    if not phrase:
        return False
    folded = phrase.replace("_", " ").replace("-", " ")
    if not any(
        candidate.casefold() in phrase or candidate.casefold().replace("-", " ") in folded
        for candidate in _DUPLICATE_VOCABULARY
    ):
        return False
    word_count = len(re.findall(r"[a-z0-9_'-]+", phrase))
    if word_count >= 9:
        return True
    return any(
        marker in phrase
        for marker in (
            "use only status names",
            "frontmatter aliases",
            "non-canonical frontmatter",
            "presentation only",
        )
    )


def _is_reference_or_template_path(relative_path: str) -> bool:
    return "/specs/references/" in f"/{relative_path}" or "/specs/templates/" in f"/{relative_path}"


def _duplicate_severity(phrase: str, non_reference_file_count: int) -> Literal["info", "warn", "high"]:
    if non_reference_file_count == 0:
        return "info"
    if non_reference_file_count >= 5 or ("child" in phrase and "return" in phrase and "authoritative" in phrase):
        return "high"
    if non_reference_file_count >= 2:
        return "warn"
    return "info"


def _semantic_duplicate_invariant_groups(
    repo_root: Path,
    *,
    include_tests: bool,
) -> tuple[SemanticDuplicateGroup, ...]:
    occurrences_by_category: dict[str, list[SemanticDuplicateOccurrence]] = defaultdict(list)
    files_by_category: dict[str, set[str]] = defaultdict(set)
    non_reference_files_by_category: dict[str, set[str]] = defaultdict(set)

    for path in _duplicate_scan_paths(repo_root, include_tests=include_tests):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        relative_path = _relative_path(path, repo_root)
        is_reference_or_template = _is_reference_or_template_path(relative_path)
        body, line_offset = _body_without_frontmatter_with_line_offset(text)
        for line_number, line in _iter_unfenced_lines(body):
            for clause in _semantic_logical_clauses(line):
                for category, matched_terms in _semantic_category_matches(clause):
                    occurrence = SemanticDuplicateOccurrence(
                        path=relative_path,
                        line=line_number + line_offset,
                        category=category,
                        snippet=_semantic_snippet(clause),
                        matched_terms=matched_terms,
                        is_reference_or_template=is_reference_or_template,
                    )
                    occurrences_by_category[category].append(occurrence)
                    files_by_category[category].add(relative_path)
                    if not is_reference_or_template:
                        non_reference_files_by_category[category].add(relative_path)

    category_order = {category.category: index for index, category in enumerate(_SEMANTIC_DUPLICATE_CATEGORIES)}
    severity_order = {"high": 0, "warn": 1, "info": 2}
    groups: list[SemanticDuplicateGroup] = []
    for category_id, occurrences in occurrences_by_category.items():
        category = _SEMANTIC_DUPLICATE_CATEGORY_BY_ID[category_id]
        file_count = len(files_by_category[category_id])
        non_reference_occurrence_count = sum(1 for occurrence in occurrences if not occurrence.is_reference_or_template)
        non_reference_file_count = len(non_reference_files_by_category[category_id])
        sorted_examples = tuple(
            sorted(
                occurrences,
                key=lambda occurrence: (
                    occurrence.is_reference_or_template,
                    occurrence.path,
                    occurrence.line,
                    occurrence.snippet,
                ),
            )[:_SEMANTIC_EXAMPLE_LIMIT]
        )
        groups.append(
            SemanticDuplicateGroup(
                category=category.category,
                label=category.label,
                occurrence_count=len(occurrences),
                file_count=file_count,
                non_reference_occurrence_count=non_reference_occurrence_count,
                non_reference_file_count=non_reference_file_count,
                severity=_semantic_duplicate_severity(category.category, non_reference_file_count),
                canonical_references=category.canonical_references,
                examples=sorted_examples,
                suggested_action=category.suggested_action,
            )
        )

    return tuple(
        sorted(
            groups,
            key=lambda group: (
                severity_order[group.severity],
                -group.non_reference_file_count,
                -group.occurrence_count,
                category_order[group.category],
            ),
        )
    )


def _semantic_logical_clauses(line: str) -> tuple[str, ...]:
    normalized = re.sub(r"^\s*(?:[-*+]|\d+[.)]|#+|>)\s*", "", line).strip()
    normalized = normalized.strip("`*_ ")
    normalized = re.sub(r"\s+", " ", normalized)
    if not normalized:
        return ()
    clauses = tuple(part.strip(" -") for part in _SEMANTIC_CLAUSE_SPLIT_RE.split(normalized) if part.strip(" -"))
    return clauses or (normalized,)


def _semantic_category_matches(clause: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    matches: list[tuple[str, tuple[str, ...]]] = []
    for category, terms in (
        ("status_handling", _status_handling_terms(clause)),
        ("fresh_continuation", _fresh_continuation_terms(clause)),
        ("stale_artifact_rejection", _stale_artifact_terms(clause)),
        ("files_written_freshness", _files_written_freshness_terms(clause)),
        ("heading_prose_non_authority", _heading_prose_non_authority_terms(clause)),
        ("no_synthesized_child_gpd_return", _no_synthesized_child_return_terms(clause)),
    ):
        if terms:
            matches.append((category, terms))
    return tuple(matches)


def _status_handling_terms(clause: str) -> tuple[str, ...]:
    folded = clause.casefold()
    has_gpd_status = "gpd_return.status" in folded
    has_runtime_vocab = bool(_SEMANTIC_STATUS_VOCAB_RE.search(clause))
    has_route_status = bool(_SEMANTIC_ROUTE_STATUS_RE.search(clause))
    if not (has_gpd_status or has_runtime_vocab or has_route_status):
        return ()
    if "verification_status" in folded and not has_gpd_status and not has_runtime_vocab:
        return ()
    terms: list[str] = []
    if has_gpd_status:
        terms.append("gpd_return.status")
    if has_runtime_vocab:
        terms.append("completed | checkpoint | blocked | failed")
    if has_route_status:
        terms.append("route on status")
    return tuple(terms)


def _fresh_continuation_terms(clause: str) -> tuple[str, ...]:
    folded = clause.casefold()
    has_checkpoint = "checkpoint" in folded
    has_fresh = bool(_SEMANTIC_FRESH_CONTINUATION_RE.search(clause))
    has_spawn = bool(_SEMANTIC_CHECKPOINT_SPAWN_RE.search(clause))
    has_no_wait = bool(_SEMANTIC_NO_WAIT_RE.search(clause))
    orchestrator_starts_fresh = has_fresh and "orchestrator" in folded and "start" in folded
    if not (
        (has_checkpoint and (has_fresh or has_spawn or has_no_wait))
        or "one-shot handoff" in folded
        or orchestrator_starts_fresh
    ):
        return ()
    terms: list[str] = []
    if has_checkpoint:
        terms.append("checkpoint")
    if "fresh continuation" in folded:
        terms.append("fresh continuation")
    if "one-shot handoff" in folded:
        terms.append("one-shot handoff")
    if has_spawn or orchestrator_starts_fresh:
        terms.append("spawn continuation")
    if has_no_wait or "resume in place" in folded or "resuming in place" in folded:
        terms.append("not resumed in place")
    return tuple(terms)


def _stale_artifact_terms(clause: str) -> tuple[str, ...]:
    has_stale_word = bool(_SEMANTIC_STALE_ARTIFACT_RE.search(clause))
    has_runtime_not_proof = bool(_SEMANTIC_RUNTIME_NOT_PROOF_RE.search(clause))
    has_artifact_context = bool(
        re.search(r"\b(artifact|file|handoff|runtime|completion|success|evidence|output|report)\b", clause, re.I)
    )
    if not ((has_stale_word and has_artifact_context) or has_runtime_not_proof):
        return ()
    terms: list[str] = []
    folded = clause.casefold()
    for term in ("stale", "preexisting", "already existed", "before this run", "runtime", "files alone"):
        if term in folded:
            terms.append(term)
    if has_runtime_not_proof and "runtime" not in terms:
        terms.append("runtime not proof")
    return tuple(terms or ("stale artifact",))


def _files_written_freshness_terms(clause: str) -> tuple[str, ...]:
    if not (_SEMANTIC_FILES_WRITTEN_RE.search(clause) and _SEMANTIC_FILE_GATE_RE.search(clause)):
        return ()
    folded = clause.casefold()
    terms = ["files_written"]
    for term in (
        "fresh",
        "same path",
        "exists",
        "readable",
        "present",
        "allowed",
        "allowlist",
        "expected artifact",
        "artifact gate",
        "actually written",
        "named",
        "names",
        "appears",
    ):
        if term in folded:
            terms.append(term)
    return tuple(dict.fromkeys(terms))


def _heading_prose_non_authority_terms(clause: str) -> tuple[str, ...]:
    has_presentation = bool(_SEMANTIC_PRESENTATION_ONLY_RE.search(clause))
    has_route_not_prose = bool(_SEMANTIC_ROUTE_NOT_PROSE_RE.search(clause))
    if not (has_presentation or has_route_not_prose):
        return ()
    folded = clause.casefold()
    terms: list[str] = []
    for term in ("heading", "headings", "human-readable", "marker strings", "prose", "success text", "labels"):
        if term in folded:
            terms.append(term)
    if "presentation only" in folded:
        terms.append("presentation only")
    if has_route_not_prose:
        terms.append("route on structured status")
    return tuple(dict.fromkeys(terms or ["presentation only"]))


def _no_synthesized_child_return_terms(clause: str) -> tuple[str, ...]:
    has_synthetic_return = bool(_SEMANTIC_NO_SYNTH_CHILD_RETURN_RE.search(clause))
    has_missing_child_return = bool(_SEMANTIC_MISSING_CHILD_RETURN_RE.search(clause))
    if not (has_synthetic_return or has_missing_child_return):
        return ()
    folded = clause.casefold()
    terms: list[str] = []
    for term in (
        "synthesize",
        "synthesized",
        "synthetic",
        "fabricate",
        "patch",
        "paste",
        "hand-author",
        "child",
        "gpd_return",
        "return envelope",
        "retry",
        "incomplete",
    ):
        if term in folded:
            terms.append(term)
    return tuple(dict.fromkeys(terms or ["synthetic child gpd_return"]))


def _semantic_duplicate_severity(
    category: str,
    non_reference_file_count: int,
) -> Literal["info", "warn", "high"]:
    if non_reference_file_count == 0:
        return "info"
    if category == "no_synthesized_child_gpd_return" and non_reference_file_count >= 2:
        return "high"
    if non_reference_file_count >= 5:
        return "high"
    if non_reference_file_count >= 2:
        return "warn"
    return "info"


def _semantic_snippet(clause: str, max_chars: int = 220) -> str:
    normalized = re.sub(r"\s+", " ", clause).strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


def _semantic_example_limit(top: int | None) -> int:
    if top is None or top <= 0:
        return _SEMANTIC_EXAMPLE_LIMIT
    return min(top, _SEMANTIC_EXAMPLE_LIMIT)


def _scan_exact_prompt_assertions(repo_root: Path) -> tuple[Mapping[str, object], ...]:
    return _exact_prose_assertion_files_from_diagnostics(_scan_exact_assertion_diagnostics(repo_root))


def _scan_exact_assertion_diagnostics(repo_root: Path) -> dict[str, object]:
    tests_root = repo_root / "tests"
    if not tests_root.is_dir():
        return _empty_exact_assertion_diagnostics()

    file_rows: list[dict[str, object]] = []
    taxonomy_usage_rows: list[dict[str, object]] = []
    files_scanned = 0
    for path in sorted(tests_root.rglob("*.py")):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
        files_scanned += 1
        relative_path = _relative_path(path, repo_root)
        taxonomy_usage = _taxonomy_helper_usage_for_tree(tree, path=relative_path)
        if taxonomy_usage:
            taxonomy_usage_rows.append(taxonomy_usage)
        assertions = _prompt_exact_assertions(tree)
        if not assertions:
            continue
        classified = [_exact_assertion_to_dict(assertion, path=relative_path) for assertion in assertions]
        machine = [entry for entry in classified if entry["category"] == "machine_contract"]
        public_ux = [entry for entry in classified if entry["category"] == "public_ux"]
        brittle = [entry for entry in classified if entry["category"] == "brittle_prose"]
        exact_count = len(classified)
        brittle_density = len(brittle) / exact_count if exact_count else 0.0
        file_rows.append(
            {
                "path": relative_path,
                "exact_assertion_count": exact_count,
                "machine_contract_exact_assertions": len(machine),
                "public_ux_exact_assertions": len(public_ux),
                "brittle_prose_assertions": len(brittle),
                "brittle_prose_density": round(brittle_density, 6),
                "severity": _exact_assertion_file_severity(len(brittle), brittle_density),
                "examples": {
                    "machine_contract": machine[:_EXACT_ASSERTION_EXAMPLES_PER_CATEGORY],
                    "public_ux": public_ux[:_EXACT_ASSERTION_EXAMPLES_PER_CATEGORY],
                    "brittle_prose": brittle[:_EXACT_ASSERTION_EXAMPLES_PER_CATEGORY],
                },
            }
        )

    file_rows = sorted(
        file_rows,
        key=lambda entry: (
            -cast(int, entry["brittle_prose_assertions"]),
            -cast(float, entry["brittle_prose_density"]),
            -cast(int, entry["exact_assertion_count"]),
            cast(str, entry["path"]),
        ),
    )
    totals = _exact_assertion_totals(files_scanned, file_rows)
    return {
        "schema_version": "exact_assertions.v1",
        "totals": totals,
        "thresholds": _EXACT_ASSERTION_THRESHOLDS,
        "files": file_rows,
        "taxonomy_helper_usage": _taxonomy_helper_usage_diagnostics(files_scanned, taxonomy_usage_rows),
    }


def _empty_exact_assertion_diagnostics() -> dict[str, object]:
    return {
        "schema_version": "exact_assertions.v1",
        "totals": {
            "files_scanned": 0,
            "exact_assertion_file_count": 0,
            "exact_assertion_count": 0,
            "machine_contract_exact_assertions": 0,
            "public_ux_exact_assertions": 0,
            "brittle_prose_assertions": 0,
            "brittle_prose_file_count": 0,
        },
        "thresholds": _EXACT_ASSERTION_THRESHOLDS,
        "files": [],
        "taxonomy_helper_usage": _taxonomy_helper_usage_diagnostics(0, ()),
    }


def _exact_assertion_totals(files_scanned: int, file_rows: Sequence[Mapping[str, object]]) -> dict[str, int]:
    return {
        "files_scanned": files_scanned,
        "exact_assertion_file_count": len(file_rows),
        "exact_assertion_count": sum(cast(int, row["exact_assertion_count"]) for row in file_rows),
        "machine_contract_exact_assertions": sum(
            cast(int, row["machine_contract_exact_assertions"]) for row in file_rows
        ),
        "public_ux_exact_assertions": sum(cast(int, row["public_ux_exact_assertions"]) for row in file_rows),
        "brittle_prose_assertions": sum(cast(int, row["brittle_prose_assertions"]) for row in file_rows),
        "brittle_prose_file_count": sum(1 for row in file_rows if cast(int, row["brittle_prose_assertions"]) > 0),
    }


def _taxonomy_helper_usage_for_tree(tree: ast.AST, *, path: str) -> dict[str, object] | None:
    helper_counts: dict[str, int] = dict.fromkeys(_TAXONOMY_HELPER_NAMES, 0)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        helper_name = _taxonomy_helper_name(node.func)
        if helper_name is None:
            continue
        helper_counts[helper_name] += 1

    used_helpers = {helper_name: count for helper_name, count in helper_counts.items() if count}
    if not used_helpers:
        return None
    return {
        "path": path,
        "helper_call_count": sum(used_helpers.values()),
        "helpers": used_helpers,
    }


def _taxonomy_helper_name(node: ast.AST) -> str | None:
    raw_name: str | None = None
    if isinstance(node, ast.Name):
        raw_name = node.id
    elif isinstance(node, ast.Attribute):
        raw_name = node.attr
    if raw_name is None:
        return None
    helper_name = _TAXONOMY_HELPER_ALIASES.get(raw_name, raw_name)
    if helper_name not in _TAXONOMY_HELPER_NAMES:
        return None
    return helper_name


def _taxonomy_helper_usage_diagnostics(
    files_scanned: int,
    file_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    sorted_rows = tuple(
        sorted(
            file_rows,
            key=lambda row: (
                -cast(int, row["helper_call_count"]),
                cast(str, row["path"]),
            ),
        )
    )
    totals: dict[str, int] = {
        "files_scanned": files_scanned,
        "taxonomy_helper_file_count": len(sorted_rows),
        "taxonomy_helper_call_count": sum(cast(int, row["helper_call_count"]) for row in sorted_rows),
    }
    for helper_name in _TAXONOMY_HELPER_NAMES:
        totals[helper_name] = sum(
            cast(int, cast(Mapping[str, object], row.get("helpers", {})).get(helper_name, 0)) for row in sorted_rows
        )
    return {
        "schema_version": _TAXONOMY_HELPER_USAGE_SCHEMA_VERSION,
        "totals": totals,
        "files": [dict(row) for row in sorted_rows],
    }


def _exact_prose_assertion_files_from_diagnostics(
    diagnostics: Mapping[str, object],
) -> tuple[Mapping[str, object], ...]:
    entries: list[Mapping[str, object]] = []
    for row in _exact_assertion_file_rows(diagnostics, None):
        examples = cast(Mapping[str, object], row.get("examples", {}))
        sample_literals: list[str] = []
        for category in ("brittle_prose", "public_ux", "machine_contract"):
            category_examples = cast(Sequence[Mapping[str, object]], examples.get(category, ()))
            sample_literals.extend(str(example.get("literal", "")) for example in category_examples)
        entries.append(
            {
                "path": row.get("path", ""),
                "exact_assertion_count": row.get("exact_assertion_count", 0),
                "prose_contract_assertions": cast(int, row.get("public_ux_exact_assertions", 0))
                + cast(int, row.get("brittle_prose_assertions", 0)),
                "machine_contract_assertions": row.get("machine_contract_exact_assertions", 0),
                "public_ux_exact_assertions": row.get("public_ux_exact_assertions", 0),
                "brittle_prose_assertions": row.get("brittle_prose_assertions", 0),
                "examples": tuple(sample_literals[:5]),
            }
        )
    return tuple(
        sorted(
            entries,
            key=lambda entry: (
                -cast(int, entry["prose_contract_assertions"]),
                -cast(int, entry["exact_assertion_count"]),
                cast(str, entry["path"]),
            ),
        )
    )


def _exact_assertion_file_rows(
    diagnostics: Mapping[str, object],
    top: int | None,
) -> tuple[Mapping[str, object], ...]:
    files = tuple(cast(Sequence[Mapping[str, object]], diagnostics.get("files", ())))
    if top is None or top <= 0:
        return files
    return files[:top]


def _exact_assertion_to_dict(assertion: ExactPromptAssertion, *, path: str) -> dict[str, object]:
    category, reason = _classify_exact_assertion(
        assertion.literal,
        path=path,
        polarity=assertion.polarity,
    )
    return {
        "path": path,
        "line": assertion.line,
        "literal": assertion.literal,
        "assertion_shape": assertion.assertion_shape,
        "polarity": assertion.polarity,
        "category": category,
        "reason": reason,
    }


def _exact_assertion_file_severity(
    brittle_prose_assertions: int,
    brittle_prose_density: float,
) -> ExactAssertionSeverity:
    if brittle_prose_assertions >= 50 or (brittle_prose_assertions >= 20 and brittle_prose_density >= 0.45):
        return "high"
    if brittle_prose_assertions >= 20 or (brittle_prose_assertions >= 10 and brittle_prose_density >= 0.30):
        return "warn"
    return "info"


def _prompt_exact_literals(tree: ast.AST) -> tuple[str, ...]:
    return tuple(assertion.literal for assertion in _prompt_exact_assertions(tree))


def _prompt_exact_assertions(tree: ast.AST) -> tuple[ExactPromptAssertion, ...]:
    assertions: list[ExactPromptAssertion] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            assertions.extend(_assert_exact_assertions(node.test))
        elif isinstance(node, ast.Call):
            assertions.extend(_method_exact_assertions(node))
    return tuple(assertion for assertion in assertions if _is_prompt_literal(assertion.literal))


def _assert_exact_literals(node: ast.AST) -> tuple[str, ...]:
    return tuple(assertion.literal for assertion in _assert_exact_assertions(node))


def _assert_exact_assertions(node: ast.AST) -> tuple[ExactPromptAssertion, ...]:
    if not isinstance(node, ast.Compare):
        return ()
    assertions: list[ExactPromptAssertion] = []
    for op in node.ops:
        if isinstance(op, (ast.In, ast.NotIn)):
            shape: ExactAssertionShape = "assert_not_contains" if isinstance(op, ast.NotIn) else "assert_contains"
            polarity: ExactAssertionPolarity = "forbidden" if isinstance(op, ast.NotIn) else "required"
            literal = _string_constant(node.left)
            if literal is not None:
                assertions.append(
                    ExactPromptAssertion(
                        literal=literal,
                        line=getattr(node, "lineno", 0),
                        assertion_shape=shape,
                        polarity=polarity,
                    )
                )
            for comparator in node.comparators:
                literal = _string_constant(comparator)
                if literal is not None:
                    assertions.append(
                        ExactPromptAssertion(
                            literal=literal,
                            line=getattr(node, "lineno", 0),
                            assertion_shape=shape,
                            polarity=polarity,
                        )
                    )
    return tuple(assertions)


def _method_exact_literals(node: ast.Call) -> tuple[str, ...]:
    return tuple(assertion.literal for assertion in _method_exact_assertions(node))


def _method_exact_assertions(node: ast.Call) -> tuple[ExactPromptAssertion, ...]:
    if not isinstance(node.func, ast.Attribute) or node.func.attr not in {"count", "index"}:
        return ()
    shape = cast(ExactAssertionShape, node.func.attr)
    polarity: ExactAssertionPolarity = "counted" if node.func.attr == "count" else "indexed"
    assertions: list[ExactPromptAssertion] = []
    for arg in node.args[:1]:
        literal = _string_constant(arg)
        if literal is not None:
            assertions.append(
                ExactPromptAssertion(
                    literal=literal,
                    line=getattr(node, "lineno", 0),
                    assertion_shape=shape,
                    polarity=polarity,
                )
            )
    return tuple(assertions)


def _string_constant(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_prompt_literal(literal: str) -> bool:
    stripped = literal.strip()
    if len(stripped) < 12:
        return stripped in _SHORT_MACHINE_CONTRACT_LITERALS or stripped in _SHORT_PUBLIC_UX_LITERALS
    if "\n" in stripped:
        return True
    return bool(
        re.search(r"[A-Za-z]{3,}\s+[A-Za-z]{3,}", stripped)
        or _MACHINE_CONTRACT_RE.search(stripped)
        or _SCHEMA_KEY_LITERAL_RE.search(stripped)
        or _PUBLIC_UX_LITERAL_RE.search(stripped)
    )


def _classify_exact_literal(literal: str) -> Literal["machine", "prose"]:
    category, _reason = _classify_exact_assertion(literal, path="", polarity="required")
    if category == "machine_contract":
        return "machine"
    return "prose"


def _classify_exact_assertion(
    literal: str,
    *,
    path: str,
    polarity: ExactAssertionPolarity,
) -> tuple[ExactAssertionCategory, str]:
    machine_reason = _machine_contract_exact_reason(literal, polarity=polarity)
    if machine_reason:
        return "machine_contract", machine_reason

    public_reason = _public_ux_exact_reason(literal, path=path)
    if public_reason:
        return "public_ux", public_reason

    if _english_word_count(literal) >= 5:
        return "brittle_prose", "long_internal_prompt_prose"
    return "machine_contract", "short_prompt_literal"


def _machine_contract_exact_reason(literal: str, *, polarity: ExactAssertionPolarity) -> str | None:
    stripped = literal.strip()
    if stripped in _SHORT_PUBLIC_UX_LITERALS:
        return None
    if stripped in _SHORT_MACHINE_CONTRACT_LITERALS:
        return "machine_regression_token"
    if _STRUCTURED_PROMPT_MARKER_RE.search(stripped):
        return "structured_prompt_marker"
    if re.search(r"\bgpd\s+--raw\b|\bgpd:[a-z0-9-]+\b|\$gpd-[a-z0-9-]+\b|--[a-z0-9][a-z0-9-]*\b", stripped):
        return "gpd_command_or_flag"
    if re.search(r"\b[A-Za-z0-9_.{}$-]+/[A-Za-z0-9_./{}$-]+", stripped) or re.search(
        r"\b[A-Za-z0-9_.-]+\.(?:md|json|ya?ml|toml|tex|pdf|py)\b",
        stripped,
        re.IGNORECASE,
    ):
        return "path_or_artifact"
    if _FIELD_PATH_RE.search(stripped) or _SCHEMA_KEY_LITERAL_RE.search(stripped):
        return "schema_or_field_path"
    if _MACHINE_CONTRACT_RE.search(stripped):
        return "machine_token"
    if polarity == "forbidden" and any(token in stripped for token in _SHORT_MACHINE_CONTRACT_LITERALS):
        return "forbidden_stale_alias"
    return None


def _public_ux_exact_reason(literal: str, *, path: str) -> str | None:
    stripped = literal.strip()
    if stripped in _SHORT_PUBLIC_UX_LITERALS or _PUBLIC_UX_LITERAL_RE.search(stripped):
        return "public_ux_copy"
    if _PUBLIC_UX_TEST_PATH_RE.search(path) and _english_word_count(stripped) >= 2:
        return "public_ux_surface"
    return None


def _english_word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z][A-Za-z'-]*", text))


def _top_items(items: Sequence[PromptSurfaceItem], top: int | None) -> tuple[PromptSurfaceItem, ...]:
    sorted_items = sorted(
        items,
        key=lambda item: (-item.expanded_char_count, -item.rigidity_index, item.kind, item.name),
    )
    if top is None or top <= 0:
        return tuple(sorted_items)
    return tuple(sorted_items[:top])


def _disallowed_return_field_mentions_outside_top_rows(report: PromptSurfaceReport, top: int | None) -> int:
    top_paths = {item.path for item in _top_items(report.items, top)}
    return sum(1 for mention in report.disallowed_return_field_mentions if mention.path not in top_paths)


def _runtime_top_prompt_rows(
    items: Sequence[PromptSurfaceItem],
    top: int | None,
) -> tuple[dict[str, object], ...]:
    rows_by_runtime: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in items:
        for metric in item.runtime_projection:
            rows_by_runtime[metric.runtime].append(
                {
                    "runtime": metric.runtime,
                    "native_include_support": metric.native_include_support,
                    "kind": item.kind,
                    "name": item.name,
                    "path": item.path,
                    "projected_line_count": metric.line_count,
                    "projected_char_count": metric.char_count,
                    "expanded_line_count": metric.expanded_line_count,
                    "expanded_char_count": metric.expanded_char_count,
                    "line_delta": metric.line_delta,
                    "char_delta": metric.char_delta,
                    "char_delta_percent": metric.char_delta_percent,
                    "include_count": metric.include_count,
                    "runtime_note_count": metric.runtime_note_count,
                    "runtime_note_chars": metric.runtime_note_chars,
                    "shell_rewrite_count": metric.shell_rewrite_count,
                }
            )

    limit = top if top is not None and top > 0 else None
    rows: list[dict[str, object]] = []
    for runtime in sorted(rows_by_runtime):
        runtime_rows = sorted(
            rows_by_runtime[runtime],
            key=lambda row: (
                -cast(int, row["projected_char_count"]),
                -cast(int, row["expanded_char_count"]),
                cast(str, row["kind"]),
                cast(str, row["name"]),
                cast(str, row["path"]),
            ),
        )
        rows.extend(runtime_rows[:limit])
    return tuple(rows)


def _runtime_top_prompts_to_dict(
    items: Sequence[PromptSurfaceItem],
    top: int | None,
) -> dict[str, list[dict[str, object]]]:
    rows_by_runtime: dict[str, list[dict[str, object]]] = {}
    for row in _runtime_top_prompt_rows(items, top):
        rows_by_runtime.setdefault(cast(str, row["runtime"]), []).append(dict(row))
    return rows_by_runtime


def _stage_top_prompt_rows(
    stage_diagnostics: Sequence[StageAwareWorkflowPromptMetric],
    top: int | None,
) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for workflow in stage_diagnostics:
        for stage in workflow.stages:
            rows.append(
                {
                    "workflow_id": workflow.workflow_id,
                    "command_name": workflow.command_name,
                    "stage_id": stage.stage_id,
                    "first_turn_char_count": workflow.first_turn_char_count,
                    "first_turn_line_count": workflow.first_turn_line_count,
                    "eager_char_count": stage.eager_char_count,
                    "eager_line_count": stage.eager_line_count,
                    "lazy_char_count": stage.lazy_char_count,
                    "lazy_line_count": stage.lazy_line_count,
                    "violation_count": len(stage.must_not_eager_load_violations),
                }
            )
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            -cast(int, row["eager_char_count"]),
            -cast(int, row["lazy_char_count"]),
            -cast(int, row["violation_count"]),
            cast(str, row["workflow_id"]),
            cast(str, row["stage_id"]),
        ),
    )
    limit = top if top is not None and top > 0 else None
    return tuple(sorted_rows[:limit])


def _stage_diagnostic_to_dict(metric: StageAwareWorkflowPromptMetric) -> dict[str, object]:
    return {
        "workflow_id": metric.workflow_id,
        "command_name": metric.command_name,
        "command_path": metric.command_path,
        "manifest_path": metric.manifest_path,
        "stage_count": metric.stage_count,
        "first_turn_line_count": metric.first_turn_line_count,
        "first_turn_char_count": metric.first_turn_char_count,
        "first_turn_raw_include_count": metric.first_turn_raw_include_count,
        "runtime_projection": [
            _runtime_projection_metric_to_dict(runtime_metric) for runtime_metric in metric.runtime_projection
        ],
        "stages": [_workflow_stage_metric_to_dict(stage) for stage in metric.stages],
        "violation_count": metric.violation_count,
        "warnings": list(metric.warnings),
    }


def _workflow_stage_metric_to_dict(metric: WorkflowStagePromptMetric) -> dict[str, object]:
    return {
        "workflow_id": metric.workflow_id,
        "stage_id": metric.stage_id,
        "order": metric.order,
        "eager_authorities": list(metric.eager_authorities),
        "eager_authority_metrics": [
            _authority_prompt_metric_to_dict(authority_metric) for authority_metric in metric.eager_authority_metrics
        ],
        "eager_line_count": metric.eager_line_count,
        "eager_char_count": metric.eager_char_count,
        "lazy_authorities": list(metric.lazy_authorities),
        "lazy_authority_metrics": [
            _authority_prompt_metric_to_dict(authority_metric) for authority_metric in metric.lazy_authority_metrics
        ],
        "lazy_line_count": metric.lazy_line_count,
        "lazy_char_count": metric.lazy_char_count,
        "must_not_eager_load_violations": [
            _must_not_eager_load_violation_to_dict(violation) for violation in metric.must_not_eager_load_violations
        ],
    }


def _authority_prompt_metric_to_dict(metric: AuthorityPromptMetric) -> dict[str, object]:
    return {
        "authority": metric.authority,
        "path": metric.path,
        "raw_line_count": metric.raw_line_count,
        "raw_char_count": metric.raw_char_count,
        "raw_include_count": metric.raw_include_count,
        "expanded_line_count": metric.expanded_line_count,
        "expanded_char_count": metric.expanded_char_count,
        "transitive_include_authorities": list(metric.transitive_include_authorities),
    }


def _must_not_eager_load_violation_to_dict(violation: MustNotEagerLoadViolation) -> dict[str, object]:
    return {
        "workflow_id": violation.workflow_id,
        "stage_id": violation.stage_id,
        "authority": violation.authority,
        "violation_source": violation.violation_source,
        "eager_via": list(violation.eager_via),
    }


def _runtime_projection_metric_to_dict(metric: RuntimeProjectionMetric) -> dict[str, object]:
    return {
        "runtime": metric.runtime,
        "native_include_support": metric.native_include_support,
        "expanded_line_count": metric.expanded_line_count,
        "expanded_char_count": metric.expanded_char_count,
        "line_count": metric.line_count,
        "char_count": metric.char_count,
        "line_delta": metric.line_delta,
        "char_delta": metric.char_delta,
        "char_delta_percent": metric.char_delta_percent,
        "include_count": metric.include_count,
        "runtime_note_count": metric.runtime_note_count,
        "runtime_note_chars": metric.runtime_note_chars,
        "shell_fence_count": metric.shell_fence_count,
        "shell_rewrite_count": metric.shell_rewrite_count,
        "bridge_command_occurrences": metric.bridge_command_occurrences,
    }


def _prompt_item_to_dict(item: PromptSurfaceItem) -> dict[str, object]:
    return {
        "kind": item.kind,
        "name": item.name,
        "path": item.path,
        "raw_line_count": item.raw_line_count,
        "raw_char_count": item.raw_char_count,
        "raw_include_count": item.raw_include_count,
        "expanded_line_count": item.expanded_line_count,
        "expanded_char_count": item.expanded_char_count,
        "expanded_include_count": item.expanded_include_count,
        "unresolved_include_count": item.unresolved_include_count,
        "visible_schema_example_count": item.visible_schema_example_count,
        "invalid_gpd_return_example_count": item.invalid_gpd_return_example_count,
        "invalid_gpd_return_examples": [
            _invalid_gpd_return_example_to_dict(example) for example in item.invalid_gpd_return_examples
        ],
        "invalid_frontmatter_example_count": item.invalid_frontmatter_example_count,
        "invalid_frontmatter_examples": [
            _invalid_frontmatter_example_to_dict(example) for example in item.invalid_frontmatter_examples
        ],
        "return_field_mention_count": item.return_field_mention_count,
        "disallowed_return_field_mention_count": item.disallowed_return_field_mention_count,
        "disallowed_return_field_mentions": [
            _return_field_mention_to_dict(mention) for mention in item.disallowed_return_field_mentions
        ],
        "hard_gate_line_count": item.hard_gate_line_count,
        "hard_gate_density": item.hard_gate_density,
        "shell_fence_count": item.shell_fence_count,
        "shell_parsing_line_count": item.shell_parsing_line_count,
        "rigidity_index": item.rigidity_index,
        "runtime_projection": [
            {
                "runtime": metric.runtime,
                "native_include_support": metric.native_include_support,
                "expanded_line_count": metric.expanded_line_count,
                "expanded_char_count": metric.expanded_char_count,
                "line_count": metric.line_count,
                "char_count": metric.char_count,
                "line_delta": metric.line_delta,
                "char_delta": metric.char_delta,
                "char_delta_percent": metric.char_delta_percent,
                "include_count": metric.include_count,
                "runtime_note_count": metric.runtime_note_count,
                "runtime_note_chars": metric.runtime_note_chars,
                "shell_fence_count": metric.shell_fence_count,
                "shell_rewrite_count": metric.shell_rewrite_count,
                "bridge_command_occurrences": metric.bridge_command_occurrences,
            }
            for metric in item.runtime_projection
        ],
    }


def _invalid_gpd_return_example_to_dict(example: InvalidGpdReturnExample) -> dict[str, object]:
    return {
        "path": example.path,
        "start_line": example.start_line,
        "end_line": example.end_line,
        "errors": list(example.errors),
        "preview": example.preview,
    }


def _invalid_frontmatter_example_to_dict(example: InvalidFrontmatterExample) -> dict[str, object]:
    return {
        "path": example.path,
        "start_line": example.start_line,
        "end_line": example.end_line,
        "schema_name": example.schema_name,
        "fields": list(example.fields),
        "errors": list(example.errors),
        "preview": example.preview,
    }


def _return_field_mention_to_dict(mention: PromptReturnFieldMention) -> dict[str, object]:
    return {
        "path": mention.path,
        "line": mention.line,
        "field": mention.field,
        "mention_kind": mention.mention_kind,
        "polarity": mention.polarity,
        "allowed": mention.allowed,
        "allowed_source": mention.allowed_source,
        "severity": mention.severity,
        "snippet": mention.snippet,
        "suggestion": mention.suggestion,
    }


def _forbidden_child_return_synthesis_mention_to_dict(
    mention: ForbiddenChildReturnSynthesisMention,
) -> dict[str, object]:
    return {
        "path": mention.path,
        "line": mention.line,
        "action": mention.action,
        "polarity": mention.polarity,
        "severity": mention.severity,
        "snippet": mention.snippet,
    }


def _markdown_table_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("`", "\\`").replace("\n", " ")
