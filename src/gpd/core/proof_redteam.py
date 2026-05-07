"""Public proof-redteam validation wrappers and conservative skeleton builders."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from gpd.contracts import PROOF_AUDIT_REVIEWER
from gpd.core.proof_review import _read_proof_redteam_status

__all__ = [
    "PROOF_REDTEAM_BODY_CONTRACT",
    "ProofRedteamSkeleton",
    "ProofRedteamSkeletonStatus",
    "ProofRedteamValidationResult",
    "build_proof_redteam_skeleton",
    "render_proof_redteam_frontmatter_yaml",
    "render_proof_redteam_markdown",
    "validate_proof_redteam_artifact",
]

ProofRedteamSkeletonStatus = Literal["gaps_found", "human_needed"]

PROOF_REDTEAM_BODY_CONTRACT = (
    "Proof-redteam skeletons are non-certifying drafts: replace every TODO row with exact proof locations, "
    "structured gaps, and an adversarial probe before treating the claim as established."
)

_SUPPORTED_SKELETON_STATUSES = frozenset({"gaps_found", "human_needed"})
_PLACEHOLDER_PROOF_ARTIFACT_PATH = "TODO-proof-artifact-path"


class ProofRedteamValidationResult(BaseModel):
    """Structured result for proof-redteam artifact validation."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    path: str
    valid: bool
    status: str | None = None
    errors: list[str] = Field(default_factory=list)


class ProofRedteamSkeleton(BaseModel):
    """Typed payload for copy-safe proof-redteam skeletons."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    frontmatter: dict[str, object]
    frontmatter_yaml: str
    markdown_draft: str
    body_stub: str
    body_contract: str
    authoring_rules: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    claim_id: str
    claim_text: str | None = None
    target_status: ProofRedteamSkeletonStatus = "gaps_found"


def validate_proof_redteam_artifact(
    path: str | Path,
    *,
    project_root: str | Path,
    expected_manuscript_path: str | None = None,
    expected_manuscript_sha256: str | None = None,
    expected_round: int | None = None,
    expected_claim_ids: Iterable[str] = (),
    expected_proof_artifact_paths: Iterable[str] = (),
) -> ProofRedteamValidationResult:
    """Validate a proof-redteam artifact through the existing strict proof-review parser."""

    artifact_path = Path(path)
    status, error = _read_proof_redteam_status(
        artifact_path,
        project_root=Path(project_root),
        expected_manuscript_path=expected_manuscript_path,
        expected_manuscript_sha256=expected_manuscript_sha256,
        expected_round=expected_round,
        expected_claim_ids=tuple(expected_claim_ids),
        expected_proof_artifact_paths=tuple(expected_proof_artifact_paths),
    )
    if error is not None:
        return ProofRedteamValidationResult(
            path=artifact_path.as_posix(),
            valid=False,
            errors=[error],
        )
    return ProofRedteamValidationResult(
        path=artifact_path.as_posix(),
        valid=True,
        status=status,
    )


def build_proof_redteam_skeleton(
    *,
    claim_id: str,
    claim_text: str | None = None,
    status: ProofRedteamSkeletonStatus = "gaps_found",
    proof_artifact_paths: Iterable[str] = (),
    manuscript_path: str | None = None,
    manuscript_sha256: str | None = None,
    round_number: int | None = None,
) -> ProofRedteamSkeleton:
    """Return a non-certifying proof-redteam artifact skeleton.

    The builder owns schema-shaped frontmatter and required section headings,
    but it never judges proof validity. It emits only open skeleton states.
    """

    if status not in _SUPPORTED_SKELETON_STATUSES:
        raise ValueError("proof-redteam skeleton supports only status='gaps_found' or status='human_needed'")
    normalized_claim_id = claim_id.strip()
    if not normalized_claim_id:
        raise ValueError("proof-redteam skeleton requires a non-empty claim_id")
    normalized_claim_text = _normalize_optional_text(claim_text)
    normalized_proof_paths = _normalize_proof_artifact_paths(proof_artifact_paths)
    manuscript_fields = _normalize_manuscript_fields(
        manuscript_path=manuscript_path,
        manuscript_sha256=manuscript_sha256,
        round_number=round_number,
    )
    frontmatter = _build_proof_redteam_frontmatter(
        claim_id=normalized_claim_id,
        status=status,
        proof_artifact_paths=normalized_proof_paths,
        manuscript_fields=manuscript_fields,
    )
    body_stub = _body_stub(
        claim_id=normalized_claim_id,
        claim_text=normalized_claim_text,
        proof_artifact_path=normalized_proof_paths[0],
        status=status,
    )
    frontmatter_yaml = render_proof_redteam_frontmatter_yaml(frontmatter)
    authoring_rules = _authoring_rules()
    warnings = _warnings()
    return ProofRedteamSkeleton(
        frontmatter=frontmatter,
        frontmatter_yaml=frontmatter_yaml,
        markdown_draft=render_proof_redteam_markdown(
            frontmatter_yaml,
            body_stub,
            authoring_rules=authoring_rules,
            warnings=warnings,
        ),
        body_stub=body_stub,
        body_contract=PROOF_REDTEAM_BODY_CONTRACT,
        authoring_rules=authoring_rules,
        warnings=warnings,
        claim_id=normalized_claim_id,
        claim_text=normalized_claim_text,
        target_status=status,
    )


def render_proof_redteam_frontmatter_yaml(frontmatter: dict[str, object]) -> str:
    """Return proof-redteam YAML frontmatter with delimiters."""

    yaml_str = yaml.dump(
        frontmatter,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=999999,
    ).rstrip()
    return f"---\n{yaml_str}\n---\n"


def render_proof_redteam_markdown(
    frontmatter_yaml: str,
    body_stub: str,
    *,
    authoring_rules: Iterable[str] = (),
    warnings: Iterable[str] = (),
) -> str:
    """Return a copy-safe Markdown proof-redteam draft."""

    sections = [body_stub.rstrip()]
    warning_section = _markdown_list_section("Generated Warnings", warnings)
    if warning_section:
        sections.append(warning_section)
    rules_section = _markdown_list_section("Generated Frontmatter Rules", authoring_rules)
    if rules_section:
        sections.append(rules_section)
    rendered_body = "\n\n".join(section for section in sections if section)
    return f"{frontmatter_yaml.rstrip()}\n\n{rendered_body}\n"


def _build_proof_redteam_frontmatter(
    *,
    claim_id: str,
    status: ProofRedteamSkeletonStatus,
    proof_artifact_paths: tuple[str, ...],
    manuscript_fields: dict[str, object],
) -> dict[str, object]:
    structured_defaults = _structured_defaults(status)
    return {
        "status": status,
        "reviewer": PROOF_AUDIT_REVIEWER,
        "claim_ids": [claim_id],
        "proof_artifact_paths": list(proof_artifact_paths),
        **manuscript_fields,
        **structured_defaults,
    }


def _structured_defaults(status: ProofRedteamSkeletonStatus) -> dict[str, object]:
    if status == "human_needed":
        coverage_gap = "Human judgment is required before this proof audit can close."
    else:
        coverage_gap = "Builder skeleton: proof obligations have not been audited."
    return {
        "missing_parameter_symbols": ["TODO-check-named-parameters"],
        "missing_hypothesis_ids": ["TODO-check-hypotheses"],
        "coverage_gaps": [coverage_gap],
        "scope_status": "unclear",
        "quantifier_status": "unclear",
        "counterexample_status": "not_attempted",
    }


def _body_stub(
    *,
    claim_id: str,
    claim_text: str | None,
    proof_artifact_path: str,
    status: ProofRedteamSkeletonStatus,
) -> str:
    proof_location = f"{proof_artifact_path}:TODO"
    claim_line = claim_text or f"TODO exact statement for {claim_id}"
    return (
        "# Proof Redteam\n\n"
        "## Proof Inventory\n\n"
        f"- Exact claim / theorem text: {claim_line}\n"
        "- Claim / theorem target: TODO identify the theorem target under audit.\n"
        "- Named parameters:\n"
        "  - TODO list each named parameter or state that none appear.\n"
        "- Hypotheses:\n"
        "  - TODO list each hypothesis or state that none appear.\n"
        "- Quantifier / domain obligations:\n"
        "  - TODO list every quantifier and domain obligation.\n"
        "- Conclusion clauses:\n"
        "  - TODO list each conclusion clause that the proof must establish.\n\n"
        "## Coverage Ledger\n\n"
        "### Named-Parameter Coverage\n\n"
        "| Parameter | Role / Domain | Proof Location | Status | Notes |\n"
        "| --- | --- | --- | --- | --- |\n"
        f"| TODO | TODO | {proof_location} | open | Builder skeleton; audit needed. |\n\n"
        "### Hypothesis Coverage\n\n"
        "| Hypothesis | Proof Location | Status | Notes |\n"
        "| --- | --- | --- | --- |\n"
        f"| TODO | {proof_location} | open | Builder skeleton; audit needed. |\n\n"
        "### Quantifier / Domain Coverage\n\n"
        "| Obligation | Proof Location | Status | Notes |\n"
        "| --- | --- | --- | --- |\n"
        f"| TODO | {proof_location} | open | Builder skeleton; audit needed. |\n\n"
        "### Conclusion-Clause Coverage\n\n"
        "| Clause | Proof Location | Status | Notes |\n"
        "| --- | --- | --- | --- |\n"
        f"| TODO | {proof_location} | open | Builder skeleton; audit needed. |\n\n"
        "## Adversarial Probe\n\n"
        "- Probe type: TODO counterexample attempt, boundary case, dropped-parameter test, or narrower-case challenge.\n"
        "- Result: TODO record the adversarial result before closure.\n\n"
        "## Verdict\n\n"
        "- Scope status: `unclear`\n"
        "- Quantifier status: `unclear`\n"
        "- Counterexample status: `not_attempted`\n"
        "- Blocking gaps:\n"
        f"  - Current skeleton status is `{status}`; replace TODO coverage before closure.\n\n"
        "## Required Follow-Up\n\n"
        "- Replace every TODO with exact proof locations, structured gaps, and required repair work.\n"
    )


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_proof_artifact_paths(values: Iterable[str]) -> tuple[str, ...]:
    normalized = _dedupe(value.strip() for value in values if value.strip())
    return tuple(normalized) if normalized else (_PLACEHOLDER_PROOF_ARTIFACT_PATH,)


def _normalize_manuscript_fields(
    *,
    manuscript_path: str | None,
    manuscript_sha256: str | None,
    round_number: int | None,
) -> dict[str, object]:
    provided = (
        manuscript_path is not None,
        manuscript_sha256 is not None,
        round_number is not None,
    )
    if any(provided) and not all(provided):
        raise ValueError(
            "manuscript-scoped proof-redteam skeletons require manuscript_path, manuscript_sha256, and round_number"
        )
    if not any(provided):
        return {}
    normalized_manuscript_path = manuscript_path.strip() if manuscript_path is not None else ""
    normalized_manuscript_sha256 = manuscript_sha256.strip().lower() if manuscript_sha256 is not None else ""
    if not normalized_manuscript_path:
        raise ValueError("manuscript_path must not be blank")
    if len(normalized_manuscript_sha256) != 64 or any(
        char not in "0123456789abcdef" for char in normalized_manuscript_sha256
    ):
        raise ValueError("manuscript_sha256 must be a lowercase 64-hex digest")
    if round_number is None or round_number < 1:
        raise ValueError("round_number must be a positive integer")
    return {
        "manuscript_path": normalized_manuscript_path,
        "manuscript_sha256": normalized_manuscript_sha256,
        "round": round_number,
    }


def _authoring_rules() -> list[str]:
    return [
        "Keep the generated status as gaps_found or human_needed until a separate proof critic supplies a complete audit.",
        "Keep reviewer as gpd-check-proof for proof-redteam artifacts.",
        "Replace TODO rows with exact proof locations and structured coverage findings.",
        "Keep structured frontmatter fields synchronized with the verdict section.",
    ]


def _warnings() -> list[str]:
    return [
        "Generated frontmatter is schema-owned; regenerate it from typed inputs instead of hand-authoring YAML.",
        "This skeleton does not decide proof validity.",
        "Validate the completed artifact before any workflow relies on it.",
    ]


def _markdown_list_section(title: str, items: Iterable[str]) -> str:
    entries = [item.strip() for item in items if item.strip()]
    if not entries:
        return ""
    return f"## {title}\n\n" + "\n".join(f"- {entry}" for entry in entries)


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
