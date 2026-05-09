"""Validate sanitized Phase 4 persona live-smoke summaries."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from gpd.adapters.runtime_catalog import iter_runtime_descriptors

SCHEMA_VERSION = "phase4.persona-live-smoke-summary.v1"
SAFE_TRIGGERS = {"operator_local_manual", "workflow_dispatch_summary_validation"}

SAFE_LITERAL_KEYS = {
    "schema_version",
    "report_id",
    "row_id",
    "row_count",
    "finding_count",
    "ci_provider_launch_allowed",
    "manual_provider_launch_allowed",
}
SAFE_CONTAINER_KEYS = {
    "aggregate_class_counts",
    "event_class_counts",
    "finding_classes",
    "redaction_scan",
    "rows",
    "allowed_trigger_classes",
}
CLASS_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")


def _runtime_launch_command_names() -> frozenset[str]:
    names: set[str] = set()
    for descriptor in iter_runtime_descriptors():
        tokens = shlex.split(descriptor.launch_command)
        if tokens:
            names.add(Path(tokens[0]).name)
    return frozenset(names)


def _secret_env_name_pattern() -> re.Pattern[str]:
    prefixes = frozenset({"OPENAI", "ANTHROPIC", "GOOGLE"}) | frozenset(
        command.upper().replace("-", "_") for command in PROVIDER_LAUNCH_COMMANDS
    )
    prefix_pattern = "|".join(sorted(re.escape(prefix) for prefix in prefixes))
    return re.compile(
        rf"(?<![A-Z0-9_])(?:{prefix_pattern})_"
        r"(?:API_KEY|AUTH_TOKEN|OAUTH_TOKEN|ACCESS_TOKEN|SECRET|TOKEN|CREDENTIALS|"
        r"CREDENTIALS_JSON|SERVICE_ACCOUNT)"
        r"(?![A-Z0-9_])"
    )


PROVIDER_LAUNCH_COMMANDS = _runtime_launch_command_names()
RAW_VALUE_PATTERNS = {
    "absolute_path": re.compile(
        r"(?<![A-Za-z0-9_])(?:/(?:Users|home|private|tmp|var|etc|Volumes|opt|mnt|root|workspace)\b|"
        r"[A-Za-z]:\\Users\\|~[/\\])"
    ),
    "parent_traversal": re.compile(r"(?:^|/)\.\.(?:/|$)"),
    "provider_secret_env_name": _secret_env_name_pattern(),
    "token_like": re.compile(
        r"(?:\bBearer\s+[A-Za-z0-9._-]{8,}|sk-[A-Za-z0-9]{12,}|ghp_[A-Za-z0-9]{12,}|"
        r"github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|"
        r"AIza[0-9A-Za-z_-]{10,}|ya29\.[0-9A-Za-z_-]{10,}|glpat-[A-Za-z0-9_-]{10,}|"
        r"hf_[A-Za-z0-9]{10,}|pk_(?:live|test)_[A-Za-z0-9]{10,}|"
        r"\b[A-Za-z0-9+/]{40,}={0,2}\b)",
        re.IGNORECASE,
    ),
    "hash": re.compile(r"\b(?:[A-Fa-f0-9]{32}|[A-Fa-f0-9]{40}|[A-Fa-f0-9]{64})\b"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "account_identifier": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "raw_artifact_file": re.compile(
        r"\b(?:prompt|stdout|stderr|transcript|argv|env|provider[-_]reply|provider[-_]output|"
        r"command)\.(?:txt|md|json|jsonl|log)\b",
        re.IGNORECASE,
    ),
    "provider_prompt_or_reply": re.compile(
        r"\b(?:provider prompt|raw provider reply|provider reply|provider[_-](?:prompt|reply|output)|"
        r"final answer text|assistant replied|prompt text|prompt:|transcript excerpt)\b",
        re.IGNORECASE,
    ),
}
SHELL_SEGMENT_SPLIT_RE = re.compile(r"(?:&&|\|\||[;|()])")
SHELL_ASSIGNMENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*")


@dataclass(frozen=True)
class ValidationResult:
    findings: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.findings


def _path_label(path: tuple[str, ...]) -> str:
    return ".".join(path) if path else "$"


def _key_is_class_only_or_policy_safe(key: str) -> bool:
    if key in SAFE_LITERAL_KEYS or key in SAFE_CONTAINER_KEYS:
        return True
    if key.endswith(("_class", "_classes", "_count", "_counts")):
        return True
    return False


def _record_string_findings(value: str, path: tuple[str, ...], findings: list[str]) -> None:
    for finding_class, pattern in RAW_VALUE_PATTERNS.items():
        if pattern.search(value):
            findings.append(f"raw_value:{finding_class}:{_path_label(path)}")
    if _provider_launch_command_in_text(value) is not None:
        findings.append(f"raw_value:provider_command_line:{_path_label(path)}")
    if not CLASS_TOKEN_RE.fullmatch(value):
        findings.append(f"raw_value:non_class_token:{_path_label(path)}")


def _shell_tokens(segment: str) -> list[str]:
    try:
        return shlex.split(segment, comments=True)
    except ValueError:
        return []


def _provider_launch_command_in_tokens(tokens: Sequence[str]) -> str | None:
    remaining = list(tokens)
    while remaining and SHELL_ASSIGNMENT_RE.fullmatch(remaining[0]):
        remaining.pop(0)
    while remaining and remaining[0] in {"builtin", "command", "exec", "sudo", "time"}:
        remaining.pop(0)
    if remaining and remaining[0] == "env":
        remaining.pop(0)
        while remaining and (remaining[0].startswith("-") or SHELL_ASSIGNMENT_RE.fullmatch(remaining[0])):
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


def _provider_launch_command_in_text(value: str) -> str | None:
    for segment in SHELL_SEGMENT_SPLIT_RE.split(value):
        command = _provider_launch_command_in_tokens(_shell_tokens(segment.strip()))
        if command is not None:
            return command
    return None


def _validate_count_map(value: object, path: tuple[str, ...], findings: list[str]) -> None:
    if not isinstance(value, Mapping):
        findings.append(f"invalid_count_map:{_path_label(path)}")
        return
    for key, count in value.items():
        if not isinstance(key, str) or not CLASS_TOKEN_RE.fullmatch(key):
            findings.append(f"invalid_count_key:{_path_label(path)}")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            findings.append(f"invalid_count_value:{_path_label((*path, str(key)))}")


def _summary_policy_findings(value: object, path: tuple[str, ...] = ()) -> list[str]:
    findings: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                findings.append(f"non_string_key:{_path_label(path)}")
                continue
            child_path = (*path, key)
            if not _key_is_class_only_or_policy_safe(key):
                findings.append(f"forbidden_key:{_path_label(child_path)}")
            if key.endswith("_counts"):
                _validate_count_map(child, child_path, findings)
                continue
            findings.extend(_summary_policy_findings(child, child_path))
        return findings
    if isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_summary_policy_findings(child, (*path, str(index))))
        return findings
    if isinstance(value, str):
        _record_string_findings(value, path, findings)
        return findings
    if value is None or isinstance(value, bool | int):
        return findings
    findings.append(f"unsupported_value_type:{_path_label(path)}:{type(value).__name__}")
    return findings


def _required_policy_findings(summary: Mapping[str, object]) -> list[str]:
    findings: list[str] = []
    expected_values: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "execution_mode_class": "manual_opt_in",
        "trigger_class": "operator_local_manual",
        "raw_artifact_retention_class": "operator_local_ignored_tmp",
        "public_artifact_class": "sanitized_class_only_summary",
        "provider_launch_source_class": "manual_operator",
        "ci_provider_launch_allowed": False,
    }
    for key, expected in expected_values.items():
        if summary.get(key) != expected:
            findings.append(f"required_policy:{key}")

    rows = summary.get("rows")
    if not isinstance(rows, list):
        findings.append("required_policy:rows")
    elif summary.get("row_count") != len(rows):
        findings.append("required_policy:row_count")

    triggers = summary.get("allowed_trigger_classes")
    if triggers is not None:
        if not isinstance(triggers, list) or any(trigger not in SAFE_TRIGGERS for trigger in triggers):
            findings.append("required_policy:allowed_trigger_classes")

    redaction_scan = summary.get("redaction_scan")
    if isinstance(redaction_scan, Mapping) and redaction_scan.get("status_class") != "pass":
        findings.append("required_policy:redaction_scan.status_class")

    return findings


def validate_summary(summary: object) -> ValidationResult:
    if not isinstance(summary, Mapping):
        return ValidationResult(("summary_not_mapping",))
    findings = [*_required_policy_findings(summary), *_summary_policy_findings(summary)]
    return ValidationResult(tuple(dict.fromkeys(findings)))


def load_summary(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path, help="Path to a sanitized Phase 4 persona live-smoke summary JSON file")
    args = parser.parse_args(argv)

    try:
        summary = load_summary(args.summary)
    except OSError as exc:
        print(f"ERROR: could not read summary: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON summary: {exc}", file=sys.stderr)
        return 2

    result = validate_summary(summary)
    if result.valid:
        print("phase4 persona summary valid")
        return 0

    print("ERROR: phase4 persona summary is not sanitized/class-only", file=sys.stderr)
    for finding in result.findings:
        print(f"- {finding}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
