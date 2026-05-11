"""Typer-free command preflight routing helpers."""

from __future__ import annotations

import dataclasses
import hashlib
import re
from collections.abc import Mapping
from pathlib import Path

from gpd.core.command_subjects import (
    ResolvedCommandSubject,
    _command_output_policy,
    _command_review_contract,
    _command_review_mode,
    _resolved_subject_manuscript_entrypoint,
    _supported_manuscript_root_for_target,
)
from gpd.core.constants import PLANNING_DIR_NAME, PUBLICATION_DIR_NAME, PUBLICATION_MANUSCRIPT_DIR_NAME
from gpd.core.utils import normalize_ascii_slug


@dataclasses.dataclass(frozen=True)
class PublicationSubjectPreflightPolicy:
    """Publication preflight relaxations and scope overrides derived from the active subject."""

    active_scopes: frozenset[str] = frozenset()
    relaxed_checks: frozenset[str] = frozenset()
    optional_checks: frozenset[str] = frozenset()
    detail_overrides: Mapping[str, str] = dataclasses.field(default_factory=dict)
    required_outputs: tuple[str, ...] = ()
    required_evidence: tuple[str, ...] = ()
    blocking_conditions: tuple[str, ...] = ()

    def relaxes(self, check_name: str) -> bool:
        return check_name in self.relaxed_checks

    def makes_missing_optional(self, check_name: str) -> bool:
        return check_name in self.optional_checks

    def passes_when_missing(self, check_name: str) -> bool:
        return self.relaxes(check_name) or self.makes_missing_optional(check_name)

    def detail(self, check_name: str) -> str | None:
        return self.detail_overrides.get(check_name)

    def blocking(self, check_name: str, *, missing: bool = False, default: bool = True) -> bool:
        if self.relaxes(check_name):
            return False
        if missing and self.makes_missing_optional(check_name):
            return False
        return default

    def missing_detail(self, check_name: str, *, default: str) -> str:
        detail = self.detail(check_name)
        return detail if detail is not None else default


_EXTERNAL_ARTIFACT_OPTIONAL_DETAILS = {
    "project_state": "external artifact review: project state is optional and is not required to start review",
    "roadmap": "external artifact review: roadmap is optional",
    "conventions": "external artifact review: project conventions are optional",
    "research_artifacts": "external artifact review: phase summaries or milestone digests are optional",
    "verification_reports": "external artifact review: verification reports are optional",
    "artifact_manifest": "no ARTIFACT-MANIFEST.json found near the manuscript; external artifact review can proceed without it",
    "bibliography_audit": "no BIBLIOGRAPHY-AUDIT.json found near the manuscript; external artifact review can proceed without it",
    "bibliography_audit_clean": "bibliography audit cleanliness is optional for external artifact review",
    "reproducibility_manifest": (
        "no reproducibility manifest found near the manuscript; external artifact review can proceed without it"
    ),
    "reproducibility_ready": "reproducibility readiness is optional for external artifact review",
    "manuscript_proof_review": (
        "prior staged manuscript proof review is optional in external artifact mode; "
        "theorem-bearing claims will be audited in this review round if detected"
    ),
}
_WRITE_PAPER_EXTERNAL_AUTHORING_OPTIONAL_DETAILS = {
    "project_state": "external authoring intake: project state is optional because the intake manifest is authoritative",
    "roadmap": "external authoring intake: roadmap is optional because the intake manifest supplies the draft scope",
    "conventions": "external authoring intake: project conventions are optional before the manuscript exists",
    "research_artifacts": (
        "external authoring intake: milestone digests and phase summaries are optional because claims and evidence "
        "come from the intake manifest"
    ),
    "verification_reports": (
        "external authoring intake: project verification reports are optional because claim-to-evidence bindings come "
        "from the intake manifest"
    ),
    "artifact_manifest": (
        "no ARTIFACT-MANIFEST.json found yet; the external authoring lane emits it after manuscript scaffolding"
    ),
    "bibliography_audit": (
        "no BIBLIOGRAPHY-AUDIT.json found yet; the external authoring lane emits it after bibliography scaffolding"
    ),
    "bibliography_audit_clean": "bibliography audit cleanliness is optional before the first external-authoring draft",
    "reproducibility_manifest": (
        "no reproducibility manifest found yet; the external authoring lane emits it after manuscript scaffolding"
    ),
    "reproducibility_ready": "reproducibility readiness is optional before the first external-authoring draft",
    "manuscript_proof_review": (
        "prior staged manuscript proof review is optional before the first external-authoring draft; "
        "proof review begins after the manuscript is authored"
    ),
}


def _publication_subject_slug_for_manuscript_entrypoint(
    project_root: Path,
    manuscript_entrypoint: Path,
) -> str:
    """Return the managed publication slug for one manuscript entrypoint."""

    manuscript_root = _supported_manuscript_root_for_target(project_root, manuscript_entrypoint)
    if manuscript_root is not None:
        try:
            relative_root = manuscript_root.resolve(strict=False).relative_to(project_root.resolve(strict=False))
        except ValueError:
            relative_root = None
        if (
            relative_root is not None
            and len(relative_root.parts) == 4
            and relative_root.parts[0] == PLANNING_DIR_NAME
            and relative_root.parts[1] == PUBLICATION_DIR_NAME
            and relative_root.parts[3] == PUBLICATION_MANUSCRIPT_DIR_NAME
        ):
            return relative_root.parts[2]

    resolved_root = project_root.resolve(strict=False)
    resolved_entrypoint = manuscript_entrypoint.resolve(strict=False)
    try:
        label = resolved_entrypoint.relative_to(resolved_root).as_posix()
    except ValueError:
        label = resolved_entrypoint.as_posix()
    slug_source = label[: -len(resolved_entrypoint.suffix)] if resolved_entrypoint.suffix else label
    slug = normalize_ascii_slug(slug_source.replace("/", "-")) or "manuscript"
    slug = slug[:48].rstrip("-") or "manuscript"
    digest = hashlib.sha256(label.encode("utf-8")).hexdigest()[:12]
    return f"{slug}-{digest}"


def _managed_publication_slug_for_target(project_root: Path, target: Path | None) -> str | None:
    """Return the existing managed publication slug for a target under GPD/publication."""

    if target is None:
        return None
    try:
        relative = target.resolve(strict=False).relative_to(project_root.resolve(strict=False))
    except ValueError:
        return None
    parts = relative.parts
    if (
        len(parts) >= 4
        and parts[0] == PLANNING_DIR_NAME
        and parts[1] == PUBLICATION_DIR_NAME
        and parts[3] == PUBLICATION_MANUSCRIPT_DIR_NAME
    ):
        return parts[2]
    return None


def _command_context_publication_roots(
    project_root: Path,
    command: object,
    resolved_subject: ResolvedCommandSubject | None,
) -> tuple[str | None, str | None]:
    """Return selected response roots exposed by command-context preflight."""

    if _command_review_mode(command) != "publication":
        return None, None
    if resolved_subject is not None and resolved_subject.ownership_mode == "external_authoring_intake":
        managed_slug = _managed_publication_slug_for_target(
            project_root,
            resolved_subject.target_root or resolved_subject.target_path,
        )
        if managed_slug is None:
            return None, None
        publication_root = f"{PLANNING_DIR_NAME}/{PUBLICATION_DIR_NAME}/{managed_slug}"
        return publication_root, f"{publication_root}/review"
    if resolved_subject is None or resolved_subject.subject_kind != "manuscript":
        return PLANNING_DIR_NAME, f"{PLANNING_DIR_NAME}/review"

    managed_slug = _managed_publication_slug_for_target(project_root, resolved_subject.target_path)
    if managed_slug is not None:
        publication_root = f"{PLANNING_DIR_NAME}/{PUBLICATION_DIR_NAME}/{managed_slug}"
    elif resolved_subject.ownership_mode == "external_artifact" and resolved_subject.target_path is not None:
        publication_root = (
            f"{PLANNING_DIR_NAME}/{PUBLICATION_DIR_NAME}/"
            f"{_publication_subject_slug_for_manuscript_entrypoint(project_root, resolved_subject.target_path)}"
        )
    else:
        publication_root = PLANNING_DIR_NAME
    return publication_root, f"{publication_root}/review"


def _project_relative_path(project_root: Path, target: Path | None) -> str | None:
    """Return *target* relative to *project_root* when possible."""

    if target is None:
        return None
    try:
        return target.resolve(strict=False).relative_to(project_root.resolve(strict=False)).as_posix()
    except ValueError:
        return target.resolve(strict=False).as_posix()


def _review_preflight_publication_routing(
    *,
    project_root: Path,
    command: object,
    resolved_subject: ResolvedCommandSubject | None,
    manuscript: Path | None,
    context_preflight: object,
) -> dict[str, str | None]:
    """Return publication routing fields emitted by raw review-preflight."""

    selected_publication_root = getattr(context_preflight, "selected_publication_root", None)
    selected_review_root = getattr(context_preflight, "selected_review_root", None)
    manuscript_root = (
        _supported_manuscript_root_for_target(project_root, manuscript) if manuscript is not None else None
    )
    if manuscript is not None and manuscript_root is None:
        manuscript_root = manuscript.parent

    publication_subject_slug = None
    publication_lane_kind = None
    managed_publication_root = None
    if (
        resolved_subject is not None
        and resolved_subject.ownership_mode == "external_authoring_intake"
        and _command_review_mode(command) == "publication"
    ):
        managed_slug = _managed_publication_slug_for_target(
            project_root,
            resolved_subject.target_root or resolved_subject.target_path,
        )
        if managed_slug is not None:
            publication_subject_slug = managed_slug
            publication_lane_kind = "managed_publication_manuscript"
            managed_publication_root = f"{PLANNING_DIR_NAME}/{PUBLICATION_DIR_NAME}/{publication_subject_slug}"
            manuscript_root = resolved_subject.target_root
    if manuscript is not None and _command_review_mode(command) == "publication":
        managed_slug = _managed_publication_slug_for_target(project_root, manuscript)
        publication_subject_slug = managed_slug or _publication_subject_slug_for_manuscript_entrypoint(
            project_root,
            manuscript,
        )
        managed_publication_root = f"{PLANNING_DIR_NAME}/{PUBLICATION_DIR_NAME}/{publication_subject_slug}"
        if managed_slug is not None:
            publication_lane_kind = "managed_publication_manuscript"
        elif (
            resolved_subject is not None
            and resolved_subject.ownership_mode == "external_artifact"
            and resolved_subject.explicit_input
        ):
            publication_lane_kind = "external_artifact"
        else:
            publication_lane_kind = "canonical_project_manuscript"

    return {
        "publication_subject_slug": publication_subject_slug,
        "publication_lane_kind": publication_lane_kind,
        "managed_publication_root": managed_publication_root,
        "selected_publication_root": selected_publication_root,
        "selected_review_root": selected_review_root,
        "manuscript_root": _project_relative_path(project_root, manuscript_root),
        "manuscript_entrypoint": _project_relative_path(project_root, manuscript),
    }


def _resolved_subject_uses_managed_publication_root(resolved_subject: ResolvedCommandSubject | None) -> bool:
    return (
        resolved_subject is not None
        and resolved_subject.subject_kind == "manuscript"
        and _managed_publication_slug_for_target(resolved_subject.context_root, resolved_subject.target_path)
        is not None
    )


def _command_managed_output_bindings(
    *,
    project_root: Path,
    resolved_subject: ResolvedCommandSubject | None,
) -> dict[str, str]:
    """Return dynamic managed-output subtree bindings for the active subject."""

    if resolved_subject is not None and resolved_subject.ownership_mode == "external_authoring_intake":
        managed_slug = _managed_publication_slug_for_target(
            project_root,
            resolved_subject.target_root or resolved_subject.target_path,
        )
        return {"subject_slug": managed_slug} if managed_slug is not None else {}
    manuscript_entrypoint = _resolved_subject_manuscript_entrypoint(resolved_subject)
    if manuscript_entrypoint is None:
        return {}
    return {"subject_slug": _publication_subject_slug_for_manuscript_entrypoint(project_root, manuscript_entrypoint)}


def _command_managed_output_policy(
    command: object,
    *,
    project_root: Path | None = None,
    resolved_subject: ResolvedCommandSubject | None = None,
):
    """Return a storage-path managed-output policy derived from command metadata."""

    from gpd.core.storage_paths import (
        ManagedOutputClass,
        ManagedOutputMatchMode,
        ManagedOutputPolicy,
        ManagedOutputRootKind,
        StageArtifactPolicy,
    )

    output_policy = _command_output_policy(command)
    if output_policy is None:
        return None

    managed_root_raw = str(getattr(output_policy, "managed_root_kind", "") or "").strip().casefold()
    if not managed_root_raw:
        return None
    if managed_root_raw in {"gpd", "gpd_managed_durable", "gpd_internal_other"}:
        managed_root_kind = ManagedOutputRootKind.GPD
        output_class = ManagedOutputClass.GPD_MANAGED_DURABLE
    elif managed_root_raw in {"project", "user_export_durable", "project_local_other"}:
        managed_root_kind = ManagedOutputRootKind.PROJECT
        output_class = ManagedOutputClass.USER_EXPORT_DURABLE
    else:
        return None

    subtree = str(getattr(output_policy, "default_output_subtree", "") or "").strip()
    if not subtree:
        return None
    subtree = subtree.replace("\\", "/")
    if managed_root_kind == ManagedOutputRootKind.GPD:
        if subtree == PLANNING_DIR_NAME:
            subtree = ""
        elif subtree.startswith(f"{PLANNING_DIR_NAME}/"):
            subtree = subtree[len(PLANNING_DIR_NAME) + 1 :]
    elif managed_root_kind == ManagedOutputRootKind.PROJECT and subtree.startswith("./"):
        subtree = subtree[2:]
    subtree_components = tuple(component for component in subtree.split("/") if component and component != ".")

    stage_policy_raw = str(getattr(output_policy, "stage_artifact_policy", "") or "").strip().casefold()
    stage_artifact_policy = (
        StageArtifactPolicy.ALLOWED
        if stage_policy_raw in {"allowed", "gpd_owned_outputs_only"}
        else StageArtifactPolicy.DISALLOWED
    )

    output_mode = str(getattr(output_policy, "output_mode", "") or "").strip().casefold()
    match_mode = ManagedOutputMatchMode.EXACT if output_mode == "exact" else ManagedOutputMatchMode.SUBTREE

    try:
        policy = ManagedOutputPolicy(
            output_class=output_class,
            managed_root_kind=managed_root_kind,
            default_output_subtree=subtree_components,
            match_mode=match_mode,
            stage_artifact_policy=stage_artifact_policy,
        )
    except ValueError:
        return None

    if not any(re.search(r"\{[A-Za-z_][A-Za-z0-9_]*\}", component) for component in policy.default_output_subtree):
        return policy
    if project_root is None:
        return None
    try:
        return policy.bind_output_subtree_placeholders(
            _command_managed_output_bindings(project_root=project_root, resolved_subject=resolved_subject)
        )
    except ValueError:
        return None


def _command_managed_output_root(
    command: object,
    *,
    project_root: Path,
    resolved_subject: ResolvedCommandSubject | None = None,
) -> Path | None:
    """Return the effective managed output root for one command, when typed policy declares it."""

    from gpd.core.storage_paths import ProjectStorageLayout

    policy = _command_managed_output_policy(
        command,
        project_root=project_root,
        resolved_subject=resolved_subject,
    )
    if policy is None:
        return None
    return ProjectStorageLayout(project_root).managed_output_path(policy)


def _command_managed_output_context_root(
    *,
    workspace_root: Path,
    context_root: Path,
    project_exists: bool,
) -> Path:
    """Choose the root that owns managed outputs for one command-context preflight."""

    return context_root if project_exists else workspace_root


def _normalize_review_scope_selector(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def _resolved_subject_scope_selectors(resolved_subject: ResolvedCommandSubject | None) -> frozenset[str]:
    if resolved_subject is None:
        return frozenset()

    selectors: set[str] = set()
    ownership_mode = _normalize_review_scope_selector(resolved_subject.ownership_mode)
    if ownership_mode:
        selectors.add(ownership_mode)
    status = _normalize_review_scope_selector(resolved_subject.status)
    if status:
        selectors.add(status)
    if resolved_subject.explicit_input:
        selectors.add("explicit_input")
        if resolved_subject.subject_kind == "manuscript":
            selectors.add("explicit_manuscript")
    if resolved_subject.ancestor_walked_up:
        selectors.add("ancestor_project")
    if resolved_subject.ownership_mode in {"project_backed", "project_reentry_selected"}:
        selectors.add("project_backed")
    if _resolved_subject_uses_managed_publication_root(resolved_subject):
        selectors.add("managed_publication_subject")
    if resolved_subject.ownership_mode == "external_artifact":
        selectors.update(
            {
                "explicit_artifact",
                "explicit_external_manuscript",
                "explicit_external_subject",
                "external_artifact",
            }
        )
    if resolved_subject.ownership_mode == "external_authoring_intake":
        selectors.update(
            {
                "external_authoring_intake",
                "explicit_intake_manifest",
                "authoring_intake",
            }
        )
    if resolved_subject.status == "interactive":
        selectors.update({"interactive", "interactive_standalone"})
    return frozenset(selectors)


def _active_review_contract_scope_variants(
    contract: object,
    *,
    resolved_subject: ResolvedCommandSubject | None,
) -> list[object]:
    active_selectors = _resolved_subject_scope_selectors(resolved_subject)
    active_variants: list[object] = []
    for variant in list(getattr(contract, "scope_variants", []) or []):
        scope = _normalize_review_scope_selector(str(getattr(variant, "scope", "") or ""))
        if scope and scope in active_selectors:
            active_variants.append(variant)
    return active_variants


def _effective_review_contract_scope_overrides(
    contract: object,
    *,
    active_scope_variants: list[object],
) -> tuple[list[str], list[str], list[str]]:
    required_outputs = list(getattr(contract, "required_outputs", []) or [])
    required_evidence = list(getattr(contract, "required_evidence", []) or [])
    blocking_conditions = list(getattr(contract, "blocking_conditions", []) or [])
    for variant in active_scope_variants:
        outputs_override = list(getattr(variant, "required_outputs_override", []) or [])
        if outputs_override:
            required_outputs = outputs_override
        evidence_override = list(getattr(variant, "required_evidence_override", []) or [])
        if evidence_override:
            required_evidence = evidence_override
        blocking_override = list(getattr(variant, "blocking_conditions_override", []) or [])
        if blocking_override:
            blocking_conditions = blocking_override
    return required_outputs, required_evidence, blocking_conditions


def _publication_subject_preflight_policy(
    command: object,
    *,
    resolved_subject: ResolvedCommandSubject | None,
) -> PublicationSubjectPreflightPolicy:
    """Return publication preflight relaxations derived from the shared subject envelope."""

    contract = _command_review_contract(command)
    if _command_review_mode(command) != "publication":
        return PublicationSubjectPreflightPolicy()

    active_scopes = _resolved_subject_scope_selectors(resolved_subject)
    active_scope_variants = _active_review_contract_scope_variants(
        contract,
        resolved_subject=resolved_subject,
    )
    relaxed_checks: set[str] = set()
    optional_checks: set[str] = set()
    detail_overrides: dict[str, str] = {}
    for variant in active_scope_variants:
        relaxed_checks.update(list(getattr(variant, "relaxed_preflight_checks", []) or []))
        optional_checks.update(list(getattr(variant, "optional_preflight_checks", []) or []))

    if active_scopes.intersection({"external_authoring_intake", "explicit_intake_manifest", "authoring_intake"}):
        for check_name, detail in _WRITE_PAPER_EXTERNAL_AUTHORING_OPTIONAL_DETAILS.items():
            if check_name in relaxed_checks or check_name in optional_checks:
                detail_overrides.setdefault(check_name, detail)

    if active_scopes.intersection({"explicit_artifact", "external_artifact"}):
        for check_name, detail in _EXTERNAL_ARTIFACT_OPTIONAL_DETAILS.items():
            if check_name in relaxed_checks or check_name in optional_checks:
                detail_overrides.setdefault(check_name, detail)

    required_outputs, required_evidence, blocking_conditions = _effective_review_contract_scope_overrides(
        contract,
        active_scope_variants=active_scope_variants,
    )
    return PublicationSubjectPreflightPolicy(
        active_scopes=active_scopes,
        relaxed_checks=frozenset(relaxed_checks),
        optional_checks=frozenset(optional_checks),
        detail_overrides=detail_overrides,
        required_outputs=tuple(required_outputs),
        required_evidence=tuple(required_evidence),
        blocking_conditions=tuple(blocking_conditions),
    )
