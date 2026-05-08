"""Read-only phase verification summary helper."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gpd.core.commands import cmd_summary_extract
from gpd.core.constants import (
    PLAN_SUFFIX,
    STANDALONE_PLAN,
    STANDALONE_SUMMARY,
    SUMMARY_SUFFIX,
    VERIFICATION_SUFFIX,
)
from gpd.core.frontmatter import FrontmatterParseError, extract_frontmatter
from gpd.core.phases import find_phase, phase_plan_index
from gpd.core.utils import phase_artifact_display_name, phase_artifact_id, phase_normalize
from gpd.core.verification_status import read_verification_status, verification_path_for_phase

__all__ = [
    "ArtifactExistenceStatus",
    "PhaseVerificationSummary",
    "PlanSummaryStatus",
    "ProofRedteamStatus",
    "build_phase_verification_summary",
]

CheckStatus = Literal["pass", "warning", "blocked", "skipped"]
RoutingStatus = Literal["pass", "warning", "blocked"]

_PROOF_BEARING_TEXT_RE = re.compile(
    r"\b(proof[_ -]?obligation|proof-bearing|theorem|lemma|corollary|proposition|prove|proof)\b",
    re.IGNORECASE,
)
_PROOF_BEARING_KINDS = frozenset({"theorem", "lemma", "corollary", "proposition", "proof_obligation"})
_WARNING_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "convention": (
        re.compile(r"\b(convention|unit|sign)\b.*\b(mismatch|inconsistent|uncertain|unchecked)\b", re.IGNORECASE),
    ),
    "identity": (
        re.compile(r"IDENTITY_SOURCE:\s*training_data", re.IGNORECASE),
        re.compile(r"\bidentity\b.*\b(unverified|unchecked|training_data|placeholder)\b", re.IGNORECASE),
    ),
    "convergence": (
        re.compile(r"\bconvergence\b.*\b(unverified|unchecked|failed|missing|inconclusive)\b", re.IGNORECASE),
    ),
    "plausibility": (
        re.compile(r"\bplausib(?:le|ility)\b.*\b(unverified|unchecked|failed|missing|inconclusive)\b", re.IGNORECASE),
    ),
    "latex_compile": (
        re.compile(r"\b(?:latex|pdflatex|compile)\b.*\b(failed|not run|missing|unchecked)\b", re.IGNORECASE),
    ),
}


class ArtifactExistenceStatus(BaseModel):
    """Existence status for a summary-declared artifact path."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    path: str
    exists: bool
    source_summary: str
    skipped_reason: str | None = None


class PlanSummaryStatus(BaseModel):
    """Structured status for one plan's expected summary artifact."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    plan_id: str
    plan_file: str
    wave: int
    expected_summary: str
    summary_path: str
    exists: bool
    valid: bool
    one_liner: str | None = None
    key_files: list[str] = Field(default_factory=list)
    decisions: list[object] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ProofRedteamStatus(BaseModel):
    """Proof-redteam status summary for selected proof-bearing plans."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    required: bool
    status: CheckStatus
    required_plan_ids: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    open: list[str] = Field(default_factory=list)
    passed: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class PhaseVerificationSummary(BaseModel):
    """Conservative helper-owned summary for phase/wave verification routing."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    phase: str
    phase_dir: str | None = None
    scope: Literal["wave", "all_waves"]
    wave: int | None = None
    structural_valid: bool = True
    plan_ids: list[str] = Field(default_factory=list)
    plan_count: int = 0
    summary_count: int = 0
    missing_summary_files: list[str] = Field(default_factory=list)
    summary_validation_failures: list[dict[str, object]] = Field(default_factory=list)
    summaries: list[PlanSummaryStatus] = Field(default_factory=list)
    required_artifacts: list[ArtifactExistenceStatus] = Field(default_factory=list)
    proof_redteam: ProofRedteamStatus = Field(
        default_factory=lambda: ProofRedteamStatus(required=False, status="skipped")
    )
    verification_report_status: dict[str, object] | None = None
    checks: dict[str, CheckStatus] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    routing: RoutingStatus = "blocked"
    recommended_next_action: str = "Fix blockers before continuing."


def build_phase_verification_summary(
    cwd: Path,
    phase: str,
    *,
    wave: int | str | None = None,
    all_waves: bool = False,
) -> PhaseVerificationSummary:
    """Return a read-only phase/wave verification summary.

    The helper owns file discovery, summary parsing, proof-redteam status
    aggregation, and canonical verification frontmatter reading. It does not
    certify scientific correctness.
    """

    normalized = phase_normalize(str(phase))
    wave_number, wave_error = _normalize_wave(wave)
    scope: Literal["wave", "all_waves"] = "wave" if wave_number is not None else "all_waves"
    if all_waves and wave_number is not None:
        return _structural_error(
            phase=normalized,
            scope="wave",
            wave=wave_number,
            error="Use either --wave or --all-waves, not both.",
        )

    phase_info = find_phase(cwd, normalized)
    if phase_info is None:
        return _structural_error(
            phase=normalized,
            scope=scope,
            wave=wave_number,
            error=f"Phase {normalized} not found.",
        )
    phase_dir = cwd / phase_info.directory
    index = phase_plan_index(cwd, normalized)
    if not index.validation.valid:
        return _structural_error(
            phase=index.phase,
            phase_dir=phase_info.directory,
            scope=scope,
            wave=wave_number,
            error="Phase plan index is invalid.",
            extra_blockers=list(index.validation.errors),
        )
    if wave_error is not None:
        return _structural_error(
            phase=index.phase,
            phase_dir=phase_info.directory,
            scope=scope,
            wave=None,
            error=wave_error,
        )

    selected_plans = [entry for entry in index.plans if wave_number is None or entry.wave == wave_number]
    if wave_number is not None and not selected_plans:
        return _structural_error(
            phase=index.phase,
            phase_dir=phase_info.directory,
            scope="wave",
            wave=wave_number,
            error=f"Wave {wave_number} has no plans in phase {index.phase}.",
        )

    plan_files_by_id, summary_files_by_id = _artifact_maps(phase_info.plans, phase_info.summaries)
    summaries: list[PlanSummaryStatus] = []
    blockers: list[str] = []
    warnings: list[str] = []
    summary_validation_failures: list[dict[str, object]] = []
    required_artifacts: list[ArtifactExistenceStatus] = []
    summary_texts: list[str] = []

    for plan in selected_plans:
        plan_file, raw_plan_id = plan_files_by_id.get(plan.id, (f"{plan.id}{PLAN_SUFFIX}", plan.id))
        expected_summary = _expected_summary_name(raw_plan_id)
        actual_summary = summary_files_by_id.get(plan.id, expected_summary)
        summary_relpath = f"{phase_info.directory}/{actual_summary}"
        summary_path = cwd / summary_relpath
        if not summary_path.exists():
            blockers.append(f"Missing summary for plan {plan.id}: {summary_relpath}")
            summaries.append(
                PlanSummaryStatus(
                    plan_id=plan.id,
                    plan_file=plan_file,
                    wave=plan.wave,
                    expected_summary=expected_summary,
                    summary_path=summary_relpath,
                    exists=False,
                    valid=False,
                    errors=["summary file missing"],
                )
            )
            continue

        extracted: dict[str, object] | None = None
        errors: list[str] = []
        try:
            result = cmd_summary_extract(
                cwd,
                summary_relpath,
                fields=[
                    "one_liner",
                    "key_files",
                    "key_files_created",
                    "key_files_modified",
                    "decisions",
                    "key_results",
                    "equations",
                ],
            )
            extracted = result if isinstance(result, dict) else result.model_dump()
        except Exception as exc:  # noqa: BLE001 - helper should fail closed on parser-specific errors.
            errors.append(str(exc))
            summary_validation_failures.append({"path": summary_relpath, "errors": list(errors)})
            blockers.append(f"Invalid summary for plan {plan.id}: {summary_relpath}")

        content = _read_text_or_empty(summary_path)
        if content:
            summary_texts.append(content)

        key_files = _string_list_from_extract(extracted, "key_files")
        for artifact_path in key_files:
            artifact_status = _artifact_status(cwd, artifact_path, source_summary=summary_relpath)
            required_artifacts.append(artifact_status)
            if not artifact_status.exists and artifact_status.skipped_reason is None:
                warnings.append(f"Summary artifact path is missing: {artifact_path}")

        summaries.append(
            PlanSummaryStatus(
                plan_id=plan.id,
                plan_file=plan_file,
                wave=plan.wave,
                expected_summary=expected_summary,
                summary_path=summary_relpath,
                exists=True,
                valid=not errors,
                one_liner=_string_or_none(extracted.get("one_liner") if extracted else None),
                key_files=key_files,
                decisions=_list_from_extract(extracted, "decisions"),
                errors=errors,
            )
        )

    proof_redteam = _proof_redteam_status(cwd, phase_dir, selected_plans, plan_files_by_id)
    blockers.extend(proof_redteam.errors)
    blockers.extend(f"Missing proof-redteam artifact: {path}" for path in proof_redteam.missing)
    blockers.extend(f"Open proof-redteam artifact: {path}" for path in proof_redteam.open)

    verification_payload = _verification_status_payload(cwd, normalized)
    if verification_payload is not None and verification_payload.get("exists") is True:
        routing_status = verification_payload.get("routing_status")
        if routing_status in {"unreadable", "unparseable", "missing_status", "unknown_status"}:
            blockers.append(f"Canonical verification report is not routable: {routing_status}")

    checks = _warning_checks(summary_texts)
    warnings.extend(_warnings_from_checks(checks))
    checks["summaries"] = "blocked" if any(not summary.valid for summary in summaries) else "pass"
    checks["proof_redteam"] = proof_redteam.status
    if verification_payload is None or verification_payload.get("exists") is False:
        checks["verification_report"] = "skipped"
    elif verification_payload.get("routing_status") == "passed":
        checks["verification_report"] = "pass"
    elif verification_payload.get("routing_status") in {"gaps_found", "expert_needed", "human_needed"}:
        checks["verification_report"] = "warning"
    else:
        checks["verification_report"] = "blocked"

    routing = _routing(blockers, warnings)
    return PhaseVerificationSummary(
        phase=index.phase,
        phase_dir=phase_info.directory,
        scope=scope,
        wave=wave_number,
        structural_valid=True,
        plan_ids=[plan.id for plan in selected_plans],
        plan_count=len(selected_plans),
        summary_count=sum(1 for summary in summaries if summary.exists and summary.valid),
        missing_summary_files=[summary.summary_path for summary in summaries if not summary.exists],
        summary_validation_failures=summary_validation_failures,
        summaries=summaries,
        required_artifacts=required_artifacts,
        proof_redteam=proof_redteam,
        verification_report_status=verification_payload,
        checks=checks,
        warnings=_dedupe(warnings),
        blockers=_dedupe(blockers),
        routing=routing,
        recommended_next_action=_recommended_next_action(routing, wave=wave_number, phase=index.phase),
    )


def _normalize_wave(wave: int | str | None) -> tuple[int | None, str | None]:
    if wave is None:
        return None, None
    try:
        wave_number = int(str(wave))
    except ValueError:
        return None, f"Wave must be an integer, got {wave!r}."
    if wave_number < 1:
        return None, f"Wave must be >= 1, got {wave_number}."
    return wave_number, None


def _structural_error(
    *,
    phase: str,
    scope: Literal["wave", "all_waves"],
    wave: int | None,
    error: str,
    phase_dir: str | None = None,
    extra_blockers: Iterable[str] = (),
) -> PhaseVerificationSummary:
    blockers = [error, *list(extra_blockers)]
    return PhaseVerificationSummary(
        phase=phase,
        phase_dir=phase_dir,
        scope=scope,
        wave=wave,
        structural_valid=False,
        blockers=blockers,
        checks={
            "summaries": "blocked",
            "proof_redteam": "skipped",
            "verification_report": "skipped",
            "convention": "skipped",
            "identity": "skipped",
            "convergence": "skipped",
            "plausibility": "skipped",
            "latex_compile": "skipped",
        },
        routing="blocked",
        recommended_next_action="Fix the structural phase input before continuing.",
    )


def _artifact_maps(
    plan_files: Iterable[str],
    summary_files: Iterable[str],
) -> tuple[dict[str, tuple[str, str]], dict[str, str]]:
    plans: dict[str, tuple[str, str]] = {}
    for plan_file in plan_files:
        raw_id = phase_artifact_id(plan_file, PLAN_SUFFIX, STANDALONE_PLAN)
        display_id = phase_artifact_display_name(raw_id, STANDALONE_PLAN)
        plans[display_id] = (plan_file, raw_id)

    summaries: dict[str, str] = {}
    for summary_file in summary_files:
        raw_id = phase_artifact_id(summary_file, SUMMARY_SUFFIX, STANDALONE_SUMMARY)
        display_id = phase_artifact_display_name(raw_id, STANDALONE_PLAN)
        summaries[display_id] = summary_file
    return plans, summaries


def _expected_summary_name(raw_plan_id: str) -> str:
    if not raw_plan_id:
        return STANDALONE_SUMMARY
    return f"{raw_plan_id}{SUMMARY_SUFFIX}"


def _read_text_or_empty(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _list_from_extract(extracted: dict[str, object] | None, key: str) -> list[object]:
    if extracted is None:
        return []
    value = extracted.get(key)
    return value if isinstance(value, list) else []


def _string_list_from_extract(extracted: dict[str, object] | None, key: str) -> list[str]:
    return [str(item) for item in _list_from_extract(extracted, key) if str(item).strip()]


def _artifact_status(cwd: Path, path_text: str, *, source_summary: str) -> ArtifactExistenceStatus:
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", path_text):
        return ArtifactExistenceStatus(
            path=path_text,
            exists=False,
            source_summary=source_summary,
            skipped_reason="external URI",
        )
    path = Path(path_text)
    candidate = path if path.is_absolute() else cwd / path
    return ArtifactExistenceStatus(
        path=path_text,
        exists=candidate.exists(),
        source_summary=source_summary,
    )


def _proof_redteam_status(
    cwd: Path,
    phase_dir: Path,
    plans: Iterable[object],
    plan_files_by_id: dict[str, tuple[str, str]],
) -> ProofRedteamStatus:
    required_plan_ids: list[str] = []
    missing: list[str] = []
    open_artifacts: list[str] = []
    passed: list[str] = []
    errors: list[str] = []

    for plan in plans:
        plan_id = str(getattr(plan, "id", ""))
        plan_file, raw_plan_id = plan_files_by_id.get(plan_id, (f"{plan_id}{PLAN_SUFFIX}", plan_id))
        plan_path = phase_dir / plan_file
        content = _read_text_or_empty(plan_path)
        if not _plan_is_proof_bearing(content):
            continue
        required_plan_ids.append(plan_id)
        redteam_name = f"{raw_plan_id}-PROOF-REDTEAM.md" if raw_plan_id else "PROOF-REDTEAM.md"
        redteam_path = phase_dir / redteam_name
        redteam_relpath = redteam_path.relative_to(cwd).as_posix() if redteam_path.is_relative_to(cwd) else redteam_path.as_posix()
        if not redteam_path.exists():
            missing.append(redteam_relpath)
            continue
        try:
            meta, _body = extract_frontmatter(redteam_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, FrontmatterParseError) as exc:
            errors.append(f"{redteam_relpath}: {exc}")
            continue
        status = _string_or_none(meta.get("status"))
        if status == "passed":
            passed.append(redteam_relpath)
        else:
            open_artifacts.append(redteam_relpath)

    if missing or open_artifacts or errors:
        status: CheckStatus = "blocked"
    elif required_plan_ids:
        status = "pass"
    else:
        status = "skipped"
    return ProofRedteamStatus(
        required=bool(required_plan_ids),
        status=status,
        required_plan_ids=required_plan_ids,
        missing=missing,
        open=open_artifacts,
        passed=passed,
        errors=errors,
    )


def _plan_is_proof_bearing(content: str) -> bool:
    if not content:
        return False
    try:
        meta, body = extract_frontmatter(content)
    except FrontmatterParseError:
        return bool(_PROOF_BEARING_TEXT_RE.search(content))
    for key in ("proof_obligation", "proof_bearing", "proof-bearing"):
        value = meta.get(key)
        if value is True:
            return True
        if isinstance(value, str) and value.strip().lower() in {"true", "yes", "required"}:
            return True
    for key in ("claim_kind", "kind", "type"):
        value = meta.get(key)
        if isinstance(value, str) and value.strip().lower() in _PROOF_BEARING_KINDS:
            return True
    return bool(_PROOF_BEARING_TEXT_RE.search(body))


def _verification_status_payload(cwd: Path, phase: str) -> dict[str, object] | None:
    path = verification_path_for_phase(cwd, phase)
    if path is None:
        expected = _expected_verification_path(cwd, phase)
        return {
            "path": expected.as_posix() if expected is not None else None,
            "exists": False,
            "readable": False,
            "parseable": False,
            "status": None,
            "session_status": None,
            "score": None,
            "source": None,
            "errors": ["verification report missing"],
            "routing_status": "missing",
        }
    return read_verification_status(path).model_dump()


def _expected_verification_path(cwd: Path, phase: str) -> Path | None:
    phase_info = find_phase(cwd, phase)
    if phase_info is None:
        return None
    return cwd / phase_info.directory / f"{phase_info.phase_number}{VERIFICATION_SUFFIX}"


def _warning_checks(summary_texts: Iterable[str]) -> dict[str, CheckStatus]:
    joined = "\n\n".join(summary_texts)
    checks: dict[str, CheckStatus] = {}
    for name, patterns in _WARNING_PATTERNS.items():
        if not joined:
            checks[name] = "skipped"
        elif any(pattern.search(joined) for pattern in patterns):
            checks[name] = "warning"
        else:
            checks[name] = "pass"
    return checks


def _warnings_from_checks(checks: dict[str, CheckStatus]) -> list[str]:
    return [f"{name} check reported warning." for name, status in checks.items() if status == "warning"]


def _routing(blockers: Iterable[str], warnings: Iterable[str]) -> RoutingStatus:
    if any(blockers):
        return "blocked"
    if any(warnings):
        return "warning"
    return "pass"


def _recommended_next_action(routing: RoutingStatus, *, wave: int | None, phase: str) -> str:
    if routing == "blocked":
        return "Fix listed blockers before continuing execution."
    if routing == "warning":
        return "Review warnings before continuing; do not treat warnings as scientific verification."
    if wave is not None:
        return f"Wave {wave} structured evidence is present; continue phase {phase} only after reviewing warnings."
    return f"All selected phase {phase} structured summaries are present; proceed to verifier/finalizer gates."


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
