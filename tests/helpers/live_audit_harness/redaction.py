"""Phase 8 provider-report redaction and retention safety validators."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from functools import lru_cache
from typing import Final, cast

from gpd.adapters.runtime_catalog import iter_runtime_descriptors

PROVIDER_REPORT_CONTEXT: Final[str] = "provider_report"

RETENTION_CLASSES: Final[frozenset[str]] = frozenset(
    {
        "committed_redacted",
        "operator_local_raw",
        "discard_after_summary",
        "never_record",
    }
)
SAFE_TO_COMMIT_RETENTION_CLASSES: Final[frozenset[str]] = frozenset({"committed_redacted"})
UNSAFE_RETENTION_CLASSES: Final[frozenset[str]] = RETENTION_CLASSES - SAFE_TO_COMMIT_RETENTION_CLASSES
RAW_PROVIDER_MATERIAL_CLASSES: Final[frozenset[str]] = frozenset(
    {
        "account_identifier",
        "argv_dump",
        "auth_material",
        "auth_path",
        "env_dump",
        "private_key",
        "prompt_in_argv",
        "provider_output",
        "provider_response",
        "provider_stderr",
        "provider_stdout",
        "provider_transcript",
        "raw_provider_material",
        "secret",
    }
)

_FORBIDDEN_RAW_FIELD_NAMES: Final[frozenset[str]] = frozenset(
    {
        "output",
        "provideroutput",
        "providerresponse",
        "providerstderr",
        "providerstdout",
        "rawoutput",
        "rawprovideroutput",
        "rawproviderresponse",
        "rawstderr",
        "rawstdout",
        "rawtranscript",
        "stderr",
        "stdout",
        "transcript",
    }
)
_FORBIDDEN_RAW_FIELD_MARKERS: Final[tuple[str, ...]] = (
    "outputtext",
    "provideroutput",
    "providerresponse",
    "providerstderr",
    "providerstdout",
    "rawoutput",
    "rawprovider",
    "rawstderr",
    "rawstdout",
    "rawtranscript",
    "stderrtext",
    "stdouttext",
    "transcripttext",
)
_FORBIDDEN_ARGV_ENV_NAMES: Final[frozenset[str]] = frozenset(
    {
        "args",
        "arguments",
        "argv",
        "commandargv",
        "commandlineargv",
        "env",
        "environ",
        "environment",
        "environmentvariables",
        "fullargv",
        "fullenv",
        "processargv",
        "processenv",
        "providerargv",
        "providerenv",
    }
)
_FORBIDDEN_ARGV_ENV_MARKERS: Final[tuple[str, ...]] = (
    "argvdump",
    "envdump",
    "environmentdump",
    "promptinargv",
)
_FORBIDDEN_AUTH_PATH_NAMES: Final[frozenset[str]] = frozenset(
    {
        "authfile",
        "authpath",
        "credentialfile",
        "credentialpath",
        "keyfile",
        "keypath",
        "secretfile",
        "secretpath",
        "tokenfile",
        "tokenpath",
    }
)
_FORBIDDEN_HEADER_NAMES: Final[frozenset[str]] = frozenset(
    {
        "authheader",
        "authorization",
        "authorizationheader",
        "headers",
        "httpheaders",
        "providerheaders",
    }
)
_AUTH_PROVIDER_CONTEXT_MARKERS: Final[tuple[str, ...]] = (
    "account",
    "auth",
    "credential",
    "keyring",
    "provider",
    "quota",
    "runtimecapability",
    "secret",
    "token",
)
_GENERIC_AUTH_PATH_VALUE_MARKERS: Final[tuple[str, ...]] = (
    ".aws/credentials",
    ".config/gcloud",
    ".netrc",
    "/auth.json",
    "/credentials.json",
)
_ARTIFACT_REF_KEYS: Final[frozenset[str]] = frozenset(
    {
        "artifactref",
        "artifactrefs",
        "evidenceref",
        "evidencerefs",
        "retentionref",
        "retentionrefs",
        "sidecarref",
        "sidecarrefs",
    }
)
_RETENTION_ENTRY_REF_KEYS: Final[tuple[str, ...]] = ("artifact_id", "artifact_ref", "artifact", "ref", "path")
_RETENTION_ENTRY_CLASS_KEYS: Final[tuple[str, ...]] = ("retention_class", "class")
_MATERIAL_CLASS_KEYS: Final[tuple[str, ...]] = ("material_class", "artifact_class", "content_class")

_PRIVATE_KEY_RE: Final[re.Pattern[str]] = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.DOTALL,
)
_AUTH_HEADER_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b(?:authorization|proxy-authorization)\s*:\s*(?:bearer|basic|token)\s+[A-Za-z0-9._~+/=-]{8,}"
)
_BEARER_RE: Final[re.Pattern[str]] = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}")
_JWT_RE: Final[re.Pattern[str]] = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
_KNOWN_TOKEN_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:"
    r"sk-ant-[A-Za-z0-9_-]{16,}|"
    r"sk-[A-Za-z0-9][A-Za-z0-9_-]{20,}|"
    r"AIza[0-9A-Za-z_-]{20,}|"
    r"gh[pousr]_[A-Za-z0-9_]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{20,}|"
    r"(?:AKIA|ASIA)[0-9A-Z]{16}"
    r")\b"
)
_SECRET_ASSIGNMENT_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|id[_-]?token|client[_-]?secret|"
    r"password|passwd|secret|session[_-]?token)\s*[:=]\s*['\"]?[A-Za-z0-9._~+/=-]{12,}"
)
_HOME_PATH_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:^|[\s'\"=:(])(?:/Users/[^/\s'\";:]+|/home/[^/\s'\";:]+|/root(?:/|[\s'\";:]|$)|"
    r"[A-Za-z]:\\Users\\[^\\\s'\";:]+)"
)
_EMAIL_RE: Final[re.Pattern[str]] = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)


def validate_provider_report_safety(report: Mapping[str, object], *, context: str = PROVIDER_REPORT_CONTEXT) -> None:
    """Raise ``ValueError`` when a Phase 8 provider report is unsafe to commit."""

    issues = collect_provider_report_safety_issues(report, context=context)
    if issues:
        raise ValueError("provider report redaction/retention validation failed: " + "; ".join(issues))


def collect_provider_report_safety_issues(
    report: Mapping[str, object], *, context: str = PROVIDER_REPORT_CONTEXT
) -> tuple[str, ...]:
    """Return deterministic redaction and retention issues for a provider report."""

    issues: list[str] = []
    _scan_redaction(report, context, (), issues)
    _validate_retention_manifest(report, context, issues)
    return tuple(issues)


def validate_provider_report_redaction(report: Mapping[str, object], *, context: str = PROVIDER_REPORT_CONTEXT) -> None:
    """Raise ``ValueError`` when a provider report contains raw or sensitive material."""

    issues: list[str] = []
    _scan_redaction(report, context, (), issues)
    if issues:
        raise ValueError("provider report redaction validation failed: " + "; ".join(issues))


def _scan_redaction(value: object, path: str, key_stack: tuple[str, ...], issues: list[str]) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                issues.append(f"{path} contains a non-string key")
                continue
            normalized_key = _normalize_key(key)
            child_path = f"{path}.{key}"
            _reject_key(normalized_key, child_path, issues)
            _scan_redaction(item, child_path, (*key_stack, normalized_key), issues)
    elif _is_sequence(value):
        for index, item in enumerate(value):
            _scan_redaction(item, f"{path}[{index}]", key_stack, issues)
    elif isinstance(value, str):
        _scan_string(value, path, key_stack, issues)


def _reject_key(normalized_key: str, path: str, issues: list[str]) -> None:
    if normalized_key in _FORBIDDEN_RAW_FIELD_NAMES or any(
        marker in normalized_key for marker in _FORBIDDEN_RAW_FIELD_MARKERS
    ):
        issues.append(f"{path} is a forbidden raw provider output/transcript field")
    if normalized_key in _FORBIDDEN_ARGV_ENV_NAMES or any(
        marker in normalized_key for marker in _FORBIDDEN_ARGV_ENV_MARKERS
    ):
        issues.append(f"{path} is a forbidden argv/env dump field")
    if normalized_key in _FORBIDDEN_AUTH_PATH_NAMES:
        issues.append(f"{path} is a forbidden auth path field")
    if normalized_key in _FORBIDDEN_HEADER_NAMES:
        issues.append(f"{path} is a forbidden auth header field")


def _scan_string(value: str, path: str, key_stack: tuple[str, ...], issues: list[str]) -> None:
    if _PRIVATE_KEY_RE.search(value):
        issues.append(f"{path} contains private-key material")
    if _AUTH_HEADER_RE.search(value) or _BEARER_RE.search(value):
        issues.append(f"{path} contains an authorization header or bearer token")
    if _KNOWN_TOKEN_RE.search(value) or _JWT_RE.search(value) or _SECRET_ASSIGNMENT_RE.search(value):
        issues.append(f"{path} contains a secret-looking token")
    if _HOME_PATH_RE.search(value) or value.startswith("~/"):
        issues.append(f"{path} contains a real home path")
    if _is_auth_provider_context(key_stack) and _EMAIL_RE.search(value):
        issues.append(f"{path} contains an account identifier in an auth/provider context")
    if _is_auth_provider_context(key_stack) and _contains_auth_path(value):
        issues.append(f"{path} contains an auth path")


def _validate_retention_manifest(report: Mapping[str, object], context: str, issues: list[str]) -> None:
    manifest = report.get("retention_manifest")
    if manifest is None:
        issues.append(f"{context}.retention_manifest is required")
        return

    entries = _retention_entries(manifest, f"{context}.retention_manifest", issues)
    manifest_refs: set[str] = set()
    for entry, entry_path in entries:
        artifact_ref = _entry_string(entry, _RETENTION_ENTRY_REF_KEYS)
        retention_class = _entry_string(entry, _RETENTION_ENTRY_CLASS_KEYS)
        material_classes = _entry_material_classes(entry)
        safe_to_commit = entry.get("safe_to_commit")

        if artifact_ref is None:
            issues.append(f"{entry_path} is missing artifact_ref")
        elif artifact_ref in manifest_refs:
            issues.append(f"{entry_path}.artifact_ref duplicates another retention manifest entry")
        else:
            manifest_refs.add(artifact_ref)

        if retention_class is None:
            issues.append(f"{entry_path} is missing retention_class")
        elif retention_class not in RETENTION_CLASSES:
            issues.append(f"{entry_path}.retention_class is not an allowed retention class")

        if not isinstance(safe_to_commit, bool):
            issues.append(f"{entry_path}.safe_to_commit must be a boolean")
        elif safe_to_commit and retention_class not in SAFE_TO_COMMIT_RETENTION_CLASSES:
            issues.append(f"{entry_path}.safe_to_commit is true for an unsafe retention class")

        if retention_class in UNSAFE_RETENTION_CLASSES and not _unsafe_entry_is_local_or_unretained(entry):
            issues.append(f"{entry_path} uses an unsafe retention class without local-only or not-retained status")

        if material_classes & RAW_PROVIDER_MATERIAL_CLASSES:
            if safe_to_commit is True:
                issues.append(f"{entry_path}.safe_to_commit is true for raw provider material")
            if retention_class in SAFE_TO_COMMIT_RETENTION_CLASSES:
                issues.append(f"{entry_path}.retention_class commits raw provider material")

    _validate_referenced_artifacts(report, context, manifest_refs, issues)


def _retention_entries(
    manifest: object, path: str, issues: list[str]
) -> tuple[tuple[Mapping[str, object], str], ...]:
    if isinstance(manifest, Mapping):
        entries_value = manifest.get("entries")
        if entries_value is not None:
            return _sequence_retention_entries(entries_value, f"{path}.entries", issues)
        artifacts_value = manifest.get("artifacts")
        if artifacts_value is not None:
            return _sequence_retention_entries(artifacts_value, f"{path}.artifacts", issues)
        entries: list[tuple[Mapping[str, object], str]] = []
        for key, value in manifest.items():
            key_path = f"{path}.{key}" if isinstance(key, str) else path
            if isinstance(value, str):
                entries.append(({"artifact_ref": str(key), "retention_class": value}, key_path))
            elif isinstance(value, Mapping):
                entry = dict(value)
                entry.setdefault("artifact_ref", str(key))
                entries.append((cast(Mapping[str, object], entry), key_path))
            else:
                issues.append(f"{key_path} must be an object or retention class string")
        return tuple(entries)
    return _sequence_retention_entries(manifest, path, issues)


def _sequence_retention_entries(
    entries_value: object, path: str, issues: list[str]
) -> tuple[tuple[Mapping[str, object], str], ...]:
    if not _is_sequence(entries_value):
        issues.append(f"{path} must be a list or object")
        return ()
    entries: list[tuple[Mapping[str, object], str]] = []
    for index, item in enumerate(entries_value):
        item_path = f"{path}[{index}]"
        if not isinstance(item, Mapping):
            issues.append(f"{item_path} must be an object")
            continue
        entries.append((cast(Mapping[str, object], item), item_path))
    return tuple(entries)


def _entry_string(entry: Mapping[str, object], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _entry_material_classes(entry: Mapping[str, object]) -> frozenset[str]:
    classes: set[str] = set()
    for key in _MATERIAL_CLASS_KEYS:
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            classes.add(value.strip())
        elif _is_sequence(value):
            classes.update(item.strip() for item in value if isinstance(item, str) and item.strip())
    return frozenset(classes)


def _unsafe_entry_is_local_or_unretained(entry: Mapping[str, object]) -> bool:
    if entry.get("local_only") is True:
        return True
    if entry.get("retained") is False or entry.get("recorded") is False:
        return True
    storage_scope = entry.get("storage_scope")
    if isinstance(storage_scope, str) and storage_scope in {"discarded", "none", "not_retained", "operator_local"}:
        return True
    return False


def _validate_referenced_artifacts(
    report: Mapping[str, object], context: str, manifest_refs: set[str], issues: list[str]
) -> None:
    referenced: list[tuple[str, str]] = []
    _collect_artifact_refs(report, context, (), referenced)
    for ref, path in referenced:
        if ref not in manifest_refs:
            issues.append(f"{path} has no retention manifest entry")


def _collect_artifact_refs(
    value: object, path: str, key_stack: tuple[str, ...], referenced: list[tuple[str, str]]
) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                continue
            normalized_key = _normalize_key(key)
            if normalized_key == "retentionmanifest":
                continue
            child_path = f"{path}.{key}"
            if normalized_key in _ARTIFACT_REF_KEYS:
                _append_artifact_refs(item, child_path, referenced)
            else:
                _collect_artifact_refs(item, child_path, (*key_stack, normalized_key), referenced)
    elif _is_sequence(value):
        for index, item in enumerate(value):
            _collect_artifact_refs(item, f"{path}[{index}]", key_stack, referenced)


def _append_artifact_refs(value: object, path: str, referenced: list[tuple[str, str]]) -> None:
    if isinstance(value, str) and value.strip():
        referenced.append((value.strip(), path))
    elif _is_sequence(value):
        for index, item in enumerate(value):
            _append_artifact_refs(item, f"{path}[{index}]", referenced)
    elif isinstance(value, Mapping):
        for key, item in value.items():
            item_path = f"{path}.{key}" if isinstance(key, str) else path
            _append_artifact_refs(item, item_path, referenced)


def _is_auth_provider_context(key_stack: tuple[str, ...]) -> bool:
    return any(any(marker in key for marker in _AUTH_PROVIDER_CONTEXT_MARKERS) for key in key_stack)


def _contains_auth_path(value: str) -> bool:
    normalized = value.replace("\\", "/").casefold()
    return any(marker in normalized for marker in _auth_path_value_markers())


@lru_cache(maxsize=1)
def _auth_path_value_markers() -> tuple[str, ...]:
    markers = set(_GENERIC_AUTH_PATH_VALUE_MARKERS)
    for descriptor in iter_runtime_descriptors():
        if descriptor.config_dir_name:
            config_dir = descriptor.config_dir_name.casefold()
            markers.add(config_dir)
            markers.add(f"{config_dir}/auth")
        if descriptor.global_config.home_subpath:
            markers.add(descriptor.global_config.home_subpath.replace("\\", "/").casefold())
    return tuple(sorted(markers, key=len, reverse=True))


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.casefold())


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


__all__ = [
    "PROVIDER_REPORT_CONTEXT",
    "RAW_PROVIDER_MATERIAL_CLASSES",
    "RETENTION_CLASSES",
    "SAFE_TO_COMMIT_RETENTION_CLASSES",
    "UNSAFE_RETENTION_CLASSES",
    "collect_provider_report_safety_issues",
    "validate_provider_report_redaction",
    "validate_provider_report_safety",
]
