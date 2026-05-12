"""Shared helpers for sanitized persona summary policy tests."""

from __future__ import annotations

import re
import shlex
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from gpd.adapters.runtime_catalog import iter_runtime_descriptors

PHASE4_SCHEMA_VERSION = "phase4.persona-live-smoke-summary.v1"
PHASE7_SCHEMA_VERSION = "phase7.live-persona-canary-summary.v1"

CLASS_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
DEFAULT_RAW_KEY_FRAGMENTS = (
    "account",
    "argv",
    "auth",
    "command",
    "command_line",
    "content",
    "credential",
    "diff",
    "env",
    "hash",
    "home",
    "path",
    "prompt",
    "provider",
    "provider_output",
    "provider_reply",
    "raw",
    "raw_prompt",
    "reply",
    "secret",
    "session",
    "stderr",
    "stdout",
    "token",
    "transcript",
)
SAFE_PHASE4_TRIGGERS = frozenset({"operator_local_manual", "workflow_dispatch_summary_validation"})
SAFE_PHASE7_NIGHTLY_TRIGGERS = frozenset({"workflow_dispatch", "schedule"})

_SHELL_SEGMENT_SPLIT_RE = re.compile(r"(?:&&|\|\||[;|()])")
_SHELL_ASSIGNMENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*")


def _runtime_launch_command_names() -> frozenset[str]:
    names: set[str] = set()
    for descriptor in iter_runtime_descriptors():
        tokens = shlex.split(descriptor.launch_command)
        if tokens:
            names.add(Path(tokens[0]).name)
    return frozenset(names)


PROVIDER_LAUNCH_COMMANDS = _runtime_launch_command_names()


def _secret_env_name_pattern() -> re.Pattern[str]:
    prefixes = frozenset({"ANTHROPIC", "CLAUDE", "CODEX", "GEMINI", "GOOGLE", "OPENAI", "OPENCODE"}) | frozenset(
        command.upper().replace("-", "_") for command in PROVIDER_LAUNCH_COMMANDS
    )
    prefix_pattern = "|".join(sorted(re.escape(prefix) for prefix in prefixes))
    return re.compile(
        rf"(?<![A-Z0-9_])(?:{prefix_pattern})_"
        r"(?:API_KEY|AUTH_TOKEN|OAUTH_TOKEN|ACCESS_TOKEN|SECRET|TOKEN|CREDENTIALS|"
        r"CREDENTIALS_JSON|SERVICE_ACCOUNT)"
        r"(?![A-Z0-9_])"
    )


DEFAULT_RAW_VALUE_PATTERNS = MappingProxyType(
    {
        "absolute_path": re.compile(
            r"(?<![A-Za-z0-9_])(?:/(?:Users|home|private|tmp|var|etc|Volumes|opt|mnt|root|workspace)\b|"
            r"[A-Za-z]:\\Users\\|~[/\\])"
        ),
        "parent_traversal": re.compile(r"(?:^|[/\\])\.\.(?:[/\\]|$)"),
        "provider_secret_env_name": _secret_env_name_pattern(),
        "token_like": re.compile(
            r"(?:\bBearer\s+[A-Za-z0-9._-]{8,}|sk-[A-Za-z0-9]{12,}|"
            r"ghp_[A-Za-z0-9]{12,}|github_pat_[A-Za-z0-9_]{20,}|"
            r"xox[baprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{10,}|"
            r"ya29\.[0-9A-Za-z_-]{10,}|glpat-[A-Za-z0-9_-]{10,}|"
            r"hf_[A-Za-z0-9]{10,}|pk_(?:live|test)_[A-Za-z0-9]{10,}|"
            r"\b[A-Za-z0-9+/]{40,}={0,2}\b)",
            re.IGNORECASE,
        ),
        "hash": re.compile(r"\b(?:[A-Fa-f0-9]{32}|[A-Fa-f0-9]{40}|[A-Fa-f0-9]{64})\b"),
        "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        "account_identifier": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
        "raw_artifact_file": re.compile(
            r"\b(?:prompt(?:\.enveloped)?\.txt|command\.(?:json|txt)|env\.json|"
            r"stdout\.(?:jsonl|txt)|stderr\.txt|transcript\.md|raw[-_]transcript\.md|"
            r"provider[-_]output\.(?:txt|log)|provider[-_]reply\.txt|"
            r"provider_output\.txt|provider_reply\.txt)\b",
            re.IGNORECASE,
        ),
        "raw_stream_or_capture": re.compile(r"\b(?:stdout|stderr|argv|env)\b", re.IGNORECASE),
        "provider_prompt_or_reply": re.compile(
            r"\b(?:raw[_ -]?prompt|provider prompt|raw provider reply|provider reply|"
            r"provider[_-](?:prompt|reply|output)|final answer text|assistant replied|"
            r"prompt text|prompt:|transcript excerpt)\b",
            re.IGNORECASE,
        ),
    }
)


@dataclass(frozen=True)
class PersonaSummaryPolicy:
    """Class-only public summary rules for one persona canary surface."""

    schema_version: str
    required_values: Mapping[str, object]
    safe_literal_keys: frozenset[str]
    safe_container_keys: frozenset[str]
    allowed_list_values: Mapping[str, frozenset[str]] = field(default_factory=dict)
    raw_key_fragments: tuple[str, ...] = DEFAULT_RAW_KEY_FRAGMENTS
    raw_value_patterns: Mapping[str, re.Pattern[str]] = field(default_factory=lambda: DEFAULT_RAW_VALUE_PATTERNS)


@dataclass(frozen=True)
class PersonaSummaryValidationResult:
    findings: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.findings


_COMMON_SAFE_LITERAL_KEYS = frozenset(
    {
        "finding_count",
        "report_id",
        "row_count",
        "row_id",
        "schema_version",
        "raw_artifact_retention_class",
        "provider_launch_source_class",
    }
)
_COMMON_SAFE_CONTAINER_KEYS = frozenset(
    {
        "aggregate_class_counts",
        "event_class_counts",
        "finding_classes",
        "redaction_scan",
        "rows",
    }
)
_PHASE4_SAFE_LITERAL_KEYS = _COMMON_SAFE_LITERAL_KEYS | frozenset(
    {
        "ci_provider_launch_allowed",
        "invalid_command_suggestion_count",
        "manual_provider_launch_allowed",
        "schema_repair_loop_count",
        "unexpected_write_count",
    }
)
_PHASE4_SAFE_CONTAINER_KEYS = _COMMON_SAFE_CONTAINER_KEYS | frozenset(
    {
        "allowed_trigger_classes",
        "behavior_class_counts",
        "behavior_metric_counts",
    }
)
_PHASE7_SAFE_LITERAL_KEYS = _COMMON_SAFE_LITERAL_KEYS | frozenset(
    {
        "content_hydration_before_selection_count",
        "conversation_turn_count",
        "invalid_command_suggestion_count",
        "release_publish_provider_launch_allowed",
        "manual_provider_launch_allowed",
        "physics_progress_count",
        "raw_reload_leakage_count",
        "schema_repair_loop_count",
        "schema_surface_count",
    }
)
_PHASE7_SAFE_CONTAINER_KEYS = _COMMON_SAFE_CONTAINER_KEYS | frozenset({"nightly_allowed_triggers"})


def phase4_live_smoke_policy() -> PersonaSummaryPolicy:
    return PersonaSummaryPolicy(
        schema_version=PHASE4_SCHEMA_VERSION,
        required_values={
            "execution_mode_class": "manual_opt_in",
            "trigger_class": "operator_local_manual",
            "raw_artifact_retention_class": "operator_local_ignored_tmp",
            "public_artifact_class": "sanitized_class_only_summary",
            "provider_launch_source_class": "manual_operator",
            "ci_provider_launch_allowed": False,
        },
        safe_literal_keys=_PHASE4_SAFE_LITERAL_KEYS,
        safe_container_keys=_PHASE4_SAFE_CONTAINER_KEYS,
        allowed_list_values={"allowed_trigger_classes": SAFE_PHASE4_TRIGGERS},
    )


def phase7_live_canary_policy() -> PersonaSummaryPolicy:
    return PersonaSummaryPolicy(
        schema_version=PHASE7_SCHEMA_VERSION,
        required_values={
            "execution_mode_class": "manual_opt_in",
            "trigger_class": "operator_local_manual",
            "raw_artifact_retention_class": "operator_local_ignored_tmp",
            "public_artifact_class": "sanitized_class_only_summary",
            "provider_launch_source_class": "manual_operator",
            "release_publish_provider_launch_allowed": False,
            "nightly_status_class": "deferred",
        },
        safe_literal_keys=_PHASE7_SAFE_LITERAL_KEYS,
        safe_container_keys=_PHASE7_SAFE_CONTAINER_KEYS,
        allowed_list_values={"nightly_allowed_triggers": SAFE_PHASE7_NIGHTLY_TRIGGERS},
    )


def _path_label(path: tuple[str, ...]) -> str:
    return ".".join(path) if path else "$"


def _shell_tokens(segment: str) -> list[str]:
    try:
        return shlex.split(segment, comments=True)
    except ValueError:
        return []


def _provider_launch_command_in_tokens(tokens: Sequence[str]) -> str | None:
    remaining = list(tokens)
    while remaining and _SHELL_ASSIGNMENT_RE.fullmatch(remaining[0]):
        remaining.pop(0)
    while remaining and remaining[0] in {"builtin", "command", "exec", "sudo", "time"}:
        remaining.pop(0)
    if remaining and remaining[0] == "env":
        remaining.pop(0)
        while remaining and (remaining[0].startswith("-") or _SHELL_ASSIGNMENT_RE.fullmatch(remaining[0])):
            remaining.pop(0)
    if len(remaining) >= 3 and remaining[:2] in (["uv", "run"], ["poetry", "run"], ["pipx", "run"]):
        remaining = remaining[2:]
    if remaining and remaining[0] in {"npx", "pnpm", "yarn"}:
        remaining.pop(0)
        while remaining and remaining[0].startswith("-"):
            remaining.pop(0)
    if len(remaining) >= 2 and remaining[:2] == ["npm", "exec"]:
        remaining = remaining[2:]
    if not remaining:
        return None
    command = Path(remaining[0]).name
    return command if command in PROVIDER_LAUNCH_COMMANDS else None


def provider_launch_command_in_text(value: str) -> str | None:
    for segment in _SHELL_SEGMENT_SPLIT_RE.split(value):
        command = _provider_launch_command_in_tokens(_shell_tokens(segment.strip()))
        if command is not None:
            return command
    return None


def _key_is_class_only_or_policy_safe(key: str, policy: PersonaSummaryPolicy) -> bool:
    if key in policy.safe_literal_keys or key in policy.safe_container_keys:
        return True
    if any(fragment in key.lower() for fragment in policy.raw_key_fragments):
        return False
    return key.endswith(("_class", "_classes", "_count", "_counts"))


def _record_string_findings(
    value: str,
    path: tuple[str, ...],
    findings: list[str],
    policy: PersonaSummaryPolicy,
) -> None:
    for finding_class, pattern in policy.raw_value_patterns.items():
        if pattern.search(value):
            findings.append(f"raw_value:{finding_class}:{_path_label(path)}")
    if provider_launch_command_in_text(value) is not None:
        findings.append(f"raw_value:provider_command_line:{_path_label(path)}")
    if not CLASS_TOKEN_RE.fullmatch(value):
        findings.append(f"raw_value:non_class_token:{_path_label(path)}")


def _validate_count_value(
    value: object,
    path: tuple[str, ...],
    findings: list[str],
    policy: PersonaSummaryPolicy,
) -> None:
    if isinstance(value, str):
        _record_string_findings(value, path, findings, policy)
    if type(value) is not int or value < 0:
        findings.append(f"invalid_count_value:{_path_label(path)}")


def _validate_count_map(
    value: object,
    path: tuple[str, ...],
    findings: list[str],
    policy: PersonaSummaryPolicy,
) -> None:
    if not isinstance(value, Mapping):
        findings.append(f"invalid_count_map:{_path_label(path)}")
        return
    for key, count in value.items():
        key_path = (*path, str(key))
        if not isinstance(key, str):
            findings.append(f"invalid_count_key:{_path_label(path)}")
        elif not CLASS_TOKEN_RE.fullmatch(key):
            findings.append(f"invalid_count_key:{_path_label(key_path)}")
        elif key not in policy.safe_literal_keys and any(
            fragment in key.lower() for fragment in policy.raw_key_fragments
        ):
            findings.append(f"raw_value:count_key:{_path_label(key_path)}")
        elif key not in policy.safe_literal_keys and any(
            pattern.search(key) for pattern in policy.raw_value_patterns.values()
        ):
            findings.append(f"raw_value:count_key:{_path_label(key_path)}")
        _validate_count_value(count, key_path, findings, policy)


def _summary_policy_findings(
    value: object,
    policy: PersonaSummaryPolicy,
    path: tuple[str, ...] = (),
) -> list[str]:
    findings: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                findings.append(f"non_string_key:{_path_label(path)}")
                continue
            child_path = (*path, key)
            if not _key_is_class_only_or_policy_safe(key, policy):
                findings.append(f"forbidden_key:{_path_label(child_path)}")
            if key.endswith("_counts"):
                _validate_count_map(child, child_path, findings, policy)
                continue
            if key.endswith("_count"):
                _validate_count_value(child, child_path, findings, policy)
                continue
            findings.extend(_summary_policy_findings(child, policy, child_path))
        return findings
    if isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_summary_policy_findings(child, policy, (*path, str(index))))
        return findings
    if isinstance(value, str):
        _record_string_findings(value, path, findings, policy)
        return findings
    if value is None or isinstance(value, bool | int):
        return findings
    findings.append(f"unsupported_value_type:{_path_label(path)}:{type(value).__name__}")
    return findings


def _required_policy_findings(summary: Mapping[str, object], policy: PersonaSummaryPolicy) -> list[str]:
    findings: list[str] = []
    if summary.get("schema_version") != policy.schema_version:
        findings.append("required_policy:schema_version")
    for key, expected in policy.required_values.items():
        if summary.get(key) != expected:
            findings.append(f"required_policy:{key}")

    rows = summary.get("rows")
    if not isinstance(rows, list):
        findings.append("required_policy:rows")
    elif summary.get("row_count") != len(rows):
        findings.append("required_policy:row_count")

    for key, allowed_values in policy.allowed_list_values.items():
        value = summary.get(key)
        if not isinstance(value, list) or any(item not in allowed_values for item in value):
            findings.append(f"required_policy:{key}")

    redaction_scan = summary.get("redaction_scan")
    if not isinstance(redaction_scan, Mapping):
        findings.append("required_policy:redaction_scan")
    elif redaction_scan.get("status_class") != "pass":
        findings.append("required_policy:redaction_scan.status_class")

    return findings


def validate_persona_summary(summary: object, policy: PersonaSummaryPolicy) -> PersonaSummaryValidationResult:
    if not isinstance(summary, Mapping):
        return PersonaSummaryValidationResult(("summary_not_mapping",))
    findings = [*_required_policy_findings(summary, policy), *_summary_policy_findings(summary, policy)]
    return PersonaSummaryValidationResult(tuple(dict.fromkeys(findings)))


def assert_persona_summary_valid(summary: object, policy: PersonaSummaryPolicy) -> None:
    result = validate_persona_summary(summary, policy)
    if not result.valid:
        raise AssertionError("persona summary is not sanitized/class-only:\n" + "\n".join(result.findings))


_PHASE4_LIVE_SMOKE_SUMMARY: dict[str, object] = {
    "schema_version": PHASE4_SCHEMA_VERSION,
    "report_id": "phase4-persona-live-smoke-summary-fixture",
    "execution_mode_class": "manual_opt_in",
    "trigger_class": "operator_local_manual",
    "raw_artifact_retention_class": "operator_local_ignored_tmp",
    "public_artifact_class": "sanitized_class_only_summary",
    "provider_launch_source_class": "manual_operator",
    "ci_provider_launch_allowed": False,
    "allowed_trigger_classes": ["operator_local_manual"],
    "row_count": 2,
    "aggregate_class_counts": {"blocked_before_execution": 1, "stopped_before_dispatch": 1},
    "behavior_class_counts": {"smooth": 1, "acceptable": 1},
    "behavior_metric_counts": {
        "invalid_command_suggestion_count": 0,
        "schema_repair_loop_count": 0,
        "unexpected_write_count": 0,
    },
    "redaction_scan": {
        "status_class": "pass",
        "finding_count": 0,
        "finding_classes": [],
    },
    "rows": [
        {
            "row_id": "P4-USER-01",
            "runtime_class": "codex_runtime",
            "persona_class": "user_steering",
            "workflow_class": "execute_phase",
            "gate_class": "claim_deliverable_alignment",
            "result_class": "blocked_before_execution",
            "next_action_class": "gpd:execute-phase",
            "write_class": "no_write",
            "smoothness_class": "smooth",
            "schema_wrestling_class": "none",
            "next_up_specificity_class": "concrete_command",
            "mutation_guard_class": "no_write",
            "invalid_command_suggestion_count": 0,
            "redaction_status_class": "pass",
            "finding_classes": ["alignment_answer_required"],
            "event_class_counts": {"ask_user_missing": 1, "dispatch_blocked": 1},
        },
        {
            "row_id": "P4-USER-02",
            "runtime_class": "claude_runtime",
            "persona_class": "user_steering",
            "workflow_class": "execute_phase",
            "gate_class": "alignment_abort",
            "result_class": "stopped_before_dispatch",
            "next_action_class": "gpd:execute-phase",
            "write_class": "no_write",
            "smoothness_class": "acceptable",
            "schema_wrestling_class": "none",
            "next_up_specificity_class": "bounded_resume",
            "mutation_guard_class": "no_write",
            "invalid_command_suggestion_count": 0,
            "redaction_status_class": "pass",
            "finding_classes": ["user_abort_stops_dispatch"],
            "event_class_counts": {"abort_selected": 1, "dispatch_blocked": 1},
        },
    ],
}

_PHASE7_LIVE_CANARY_SUMMARY: dict[str, object] = {
    "schema_version": PHASE7_SCHEMA_VERSION,
    "report_id": "phase7-manual-canary-summary-fixture",
    "execution_mode_class": "manual_opt_in",
    "trigger_class": "operator_local_manual",
    "raw_artifact_retention_class": "operator_local_ignored_tmp",
    "public_artifact_class": "sanitized_class_only_summary",
    "provider_launch_source_class": "manual_operator",
    "release_publish_provider_launch_allowed": False,
    "nightly_status_class": "deferred",
    "nightly_allowed_triggers": ["workflow_dispatch", "schedule"],
    "row_count": 1,
    "aggregate_class_counts": {"blocked": 1, "no_write": 1},
    "redaction_scan": {
        "status_class": "pass",
        "finding_count": 0,
        "finding_classes": [],
    },
    "rows": [
        {
            "row_id": "LP-RO-RUNTIME",
            "runtime_class": "runtime_catalog_member",
            "persona_class": "zero_coder_recovery",
            "workflow_class": "read_only_setup_recovery",
            "launch_policy_class": "manual_opt_in",
            "write_class": "no_write",
            "result_class": "blocked",
            "next_step_class": "operator_review",
            "artifact_retention_class": "operator_local_ignored_tmp",
            "redaction_status_class": "pass",
            "finding_classes": ["provider_auth_unknown"],
            "event_class_counts": {"setup_refusal": 1, "redaction_pass": 1},
        }
    ],
}


def make_phase4_live_smoke_summary() -> dict[str, object]:
    return deepcopy(_PHASE4_LIVE_SMOKE_SUMMARY)


def make_phase7_live_canary_summary() -> dict[str, object]:
    return deepcopy(_PHASE7_LIVE_CANARY_SUMMARY)
