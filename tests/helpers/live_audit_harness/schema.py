"""Provider-free scenario schema helpers for the Phase 7 live-audit harness."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Final, cast

from gpd.adapters.runtime_catalog import list_runtime_names

RUNTIMES: Final[tuple[str, ...]] = tuple(list_runtime_names())
SCHEMA_VERSION: Final[str] = "phase7.persona-scenario-set.v1"
REQUIRED_ARTIFACTS: Final[frozenset[str]] = frozenset(
    {
        "status.json",
        "stdout.jsonl",
        "normalized-events.jsonl",
        "final.md",
        "write-classification.json",
        "evidence-packet.json",
    }
)

_TOP_LEVEL_KEYS: Final[frozenset[str]] = frozenset(
    {
        "schema_version",
        "scenario_set_id",
        "personas",
        "scenario_rows",
    }
)
_PERSONA_KEYS: Final[frozenset[str]] = frozenset(
    {
        "persona_id",
        "persona_family",
        "public_label_class",
        "expertise_class",
        "gpd_familiarity_class",
        "expected_support_classes",
        "forbidden_assumption_classes",
    }
)
_EXPECTED_OUTCOME_KEYS: Final[frozenset[str]] = frozenset(
    {
        "outcome_id",
        "required_event_classes",
        "forbidden_event_classes",
        "required_final_response_classes",
        "forbidden_final_response_classes",
    }
)
_WRITE_POLICY_KEYS: Final[frozenset[str]] = frozenset(
    {
        "policy_id",
        "mode",
        "allowed_paths",
        "forbidden_paths",
    }
)
_ROW_KEYS: Final[frozenset[str]] = frozenset(
    {
        "row_id",
        "scenario_id",
        "runtime",
        "persona_id",
        "command_slug",
        "fixture_ref",
        "provider_launch_allowed",
        "expected_outcome",
        "write_policy",
        "required_artifacts",
    }
)
_WRITE_POLICY_MODES: Final[frozenset[str]] = frozenset(
    {
        "read_only",
        "repo_tmp_only",
        "controlled_relative_writes",
    }
)
_FORBIDDEN_RAW_FIELD_MARKERS: Final[frozenset[str]] = frozenset(
    {
        "authfile",
        "authpath",
        "authstate",
        "localpath",
        "privatepath",
        "provideroutput",
        "providerstderr",
        "providerstdout",
        "rawauth",
        "rawpath",
        "rawprompt",
        "rawprovideroutput",
        "rawtranscript",
    }
)


@dataclass(frozen=True, slots=True)
class Persona:
    persona_id: str
    persona_family: str
    public_label_class: str
    expertise_class: str
    gpd_familiarity_class: str
    expected_support_classes: tuple[str, ...]
    forbidden_assumption_classes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExpectedOutcome:
    outcome_id: str
    required_event_classes: tuple[str, ...]
    forbidden_event_classes: tuple[str, ...]
    required_final_response_classes: tuple[str, ...]
    forbidden_final_response_classes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WritePolicy:
    policy_id: str
    mode: str
    allowed_paths: tuple[str, ...]
    forbidden_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScenarioRow:
    row_id: str
    scenario_id: str
    runtime: str
    persona_id: str
    command_slug: str
    fixture_ref: str
    provider_launch_allowed: bool
    expected_outcome: ExpectedOutcome
    write_policy: WritePolicy
    required_artifacts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScenarioSet:
    schema_version: str
    scenario_set_id: str
    personas: tuple[Persona, ...]
    rows: tuple[ScenarioRow, ...]


def default_scenario_path(repo_root: Path) -> Path:
    """Return the tracked Phase 7 scenario fixture path for a repository root."""

    return repo_root / "tests" / "fixtures" / "live_audit" / "scenarios.json"


def load_scenario_set(path: Path) -> ScenarioSet:
    """Load and validate a scenario set from JSON."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    return validate_scenario_set(_as_mapping(payload, "scenario set payload"))


def validate_scenario_set(payload: Mapping[str, object]) -> ScenarioSet:
    """Validate a public, provider-free Phase 7 scenario set."""

    _reject_raw_fields(payload, "scenario_set")
    _require_keys(payload, _TOP_LEVEL_KEYS, _TOP_LEVEL_KEYS, "scenario_set")

    schema_version = _required_str(payload, "schema_version", "scenario_set")
    if schema_version != SCHEMA_VERSION:
        raise ValueError(f"scenario_set.schema_version must be exactly {SCHEMA_VERSION!r}")

    scenario_set_id = _required_str(payload, "scenario_set_id", "scenario_set")
    personas = _parse_personas(_required_sequence(payload, "personas", "scenario_set"))
    persona_ids = _ids_by_persona(personas)
    rows = _parse_rows(_required_sequence(payload, "scenario_rows", "scenario_set"), persona_ids)

    return ScenarioSet(
        schema_version=schema_version,
        scenario_set_id=scenario_set_id,
        personas=personas,
        rows=rows,
    )


def _parse_personas(items: Sequence[object]) -> tuple[Persona, ...]:
    personas: list[Persona] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(items):
        context = f"scenario_set.personas[{index}]"
        mapping = _as_mapping(item, context)
        _require_keys(mapping, _PERSONA_KEYS, _PERSONA_KEYS, context)
        persona_id = _required_str(mapping, "persona_id", context)
        if persona_id in seen_ids:
            raise ValueError(f"duplicate persona_id {persona_id!r}")
        seen_ids.add(persona_id)
        personas.append(
            Persona(
                persona_id=persona_id,
                persona_family=_required_str(mapping, "persona_family", context),
                public_label_class=_required_str(mapping, "public_label_class", context),
                expertise_class=_required_str(mapping, "expertise_class", context),
                gpd_familiarity_class=_required_str(mapping, "gpd_familiarity_class", context),
                expected_support_classes=_required_str_tuple(mapping, "expected_support_classes", context),
                forbidden_assumption_classes=_required_str_tuple(mapping, "forbidden_assumption_classes", context),
            )
        )
    return tuple(personas)


def _parse_rows(items: Sequence[object], persona_ids: frozenset[str]) -> tuple[ScenarioRow, ...]:
    rows: list[ScenarioRow] = []
    seen_row_ids: set[str] = set()
    seen_scenario_ids: set[str] = set()
    for index, item in enumerate(items):
        context = f"scenario_set.scenario_rows[{index}]"
        mapping = _as_mapping(item, context)
        _require_keys(mapping, _ROW_KEYS, _ROW_KEYS, context)

        row_id = _required_str(mapping, "row_id", context)
        if row_id in seen_row_ids:
            raise ValueError(f"duplicate row_id {row_id!r}")
        seen_row_ids.add(row_id)

        scenario_id = _required_str(mapping, "scenario_id", context)
        if scenario_id in seen_scenario_ids:
            raise ValueError(f"duplicate scenario_id {scenario_id!r}")
        seen_scenario_ids.add(scenario_id)

        runtime = _required_str(mapping, "runtime", context)
        if runtime not in RUNTIMES:
            raise ValueError(f"{context}.runtime must be one of {RUNTIMES!r}")
        runtime_prefix = f"P7-{runtime.upper()}-"
        if not row_id.startswith(runtime_prefix):
            raise ValueError(f"{context}.row_id must start with {runtime_prefix!r}")

        persona_id = _required_str(mapping, "persona_id", context)
        if persona_id not in persona_ids:
            raise ValueError(f"{context}.persona_id {persona_id!r} does not reference a declared persona")

        provider_launch_allowed = _required_bool(mapping, "provider_launch_allowed", context)
        if provider_launch_allowed:
            raise ValueError(f"{context}.provider_launch_allowed must be false")

        required_artifacts = _required_str_tuple(mapping, "required_artifacts", context)
        _validate_required_artifacts(required_artifacts, context)

        rows.append(
            ScenarioRow(
                row_id=row_id,
                scenario_id=scenario_id,
                runtime=runtime,
                persona_id=persona_id,
                command_slug=_required_str(mapping, "command_slug", context),
                fixture_ref=_required_str(mapping, "fixture_ref", context),
                provider_launch_allowed=provider_launch_allowed,
                expected_outcome=_parse_expected_outcome(
                    _required_mapping(mapping, "expected_outcome", context),
                    f"{context}.expected_outcome",
                ),
                write_policy=_parse_write_policy(
                    _required_mapping(mapping, "write_policy", context),
                    f"{context}.write_policy",
                ),
                required_artifacts=required_artifacts,
            )
        )
    return tuple(rows)


def _parse_expected_outcome(mapping: Mapping[str, object], context: str) -> ExpectedOutcome:
    _require_keys(mapping, _EXPECTED_OUTCOME_KEYS, _EXPECTED_OUTCOME_KEYS, context)
    return ExpectedOutcome(
        outcome_id=_required_str(mapping, "outcome_id", context),
        required_event_classes=_required_str_tuple(mapping, "required_event_classes", context),
        forbidden_event_classes=_required_str_tuple(mapping, "forbidden_event_classes", context),
        required_final_response_classes=_required_str_tuple(mapping, "required_final_response_classes", context),
        forbidden_final_response_classes=_required_str_tuple(mapping, "forbidden_final_response_classes", context),
    )


def _parse_write_policy(mapping: Mapping[str, object], context: str) -> WritePolicy:
    _require_keys(mapping, _WRITE_POLICY_KEYS, _WRITE_POLICY_KEYS, context)
    mode = _required_str(mapping, "mode", context)
    if mode not in _WRITE_POLICY_MODES:
        raise ValueError(f"{context}.mode must be one of {sorted(_WRITE_POLICY_MODES)!r}")

    allowed_paths = _required_str_tuple(mapping, "allowed_paths", context)
    forbidden_paths = _required_str_tuple(mapping, "forbidden_paths", context)
    for path in (*allowed_paths, *forbidden_paths):
        _validate_relative_path(path, context)

    return WritePolicy(
        policy_id=_required_str(mapping, "policy_id", context),
        mode=mode,
        allowed_paths=allowed_paths,
        forbidden_paths=forbidden_paths,
    )


def _ids_by_persona(personas: tuple[Persona, ...]) -> frozenset[str]:
    return frozenset(persona.persona_id for persona in personas)


def _validate_required_artifacts(artifacts: tuple[str, ...], context: str) -> None:
    if len(set(artifacts)) != len(artifacts):
        raise ValueError(f"{context}.required_artifacts must not contain duplicates")
    missing = sorted(REQUIRED_ARTIFACTS.difference(artifacts))
    if missing:
        raise ValueError(f"{context}.required_artifacts missing required artifacts: {missing!r}")


def _validate_relative_path(path: str, context: str) -> None:
    if not path or path in {".", "./"}:
        raise ValueError(f"{context} write policy paths must be non-empty relative paths")
    if path.startswith("~") or "\\" in path:
        raise ValueError(f"{context} write policy path {path!r} must be repo-relative")
    posix_path = PurePosixPath(path)
    windows_path = PureWindowsPath(path)
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise ValueError(f"{context} write policy path {path!r} must be relative")
    if ".." in posix_path.parts:
        raise ValueError(f"{context} write policy path {path!r} must not traverse upward")


def _require_keys(
    mapping: Mapping[str, object],
    required: frozenset[str],
    allowed: frozenset[str],
    context: str,
) -> None:
    keys = set(mapping)
    missing = sorted(required.difference(keys))
    if missing:
        raise ValueError(f"{context} missing required keys: {missing!r}")
    unknown = sorted(keys.difference(allowed))
    if unknown:
        raise ValueError(f"{context} has unknown keys: {unknown!r}")


def _required(mapping: Mapping[str, object], key: str, context: str) -> object:
    try:
        return mapping[key]
    except KeyError as exc:
        raise ValueError(f"{context} missing required key {key!r}") from exc


def _required_str(mapping: Mapping[str, object], key: str, context: str) -> str:
    value = _required(mapping, key, context)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context}.{key} must be a non-empty string")
    return value


def _required_bool(mapping: Mapping[str, object], key: str, context: str) -> bool:
    value = _required(mapping, key, context)
    if type(value) is not bool:
        raise ValueError(f"{context}.{key} must be a boolean")
    return value


def _required_sequence(mapping: Mapping[str, object], key: str, context: str) -> Sequence[object]:
    value = _required(mapping, key, context)
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError(f"{context}.{key} must be a list")
    return value


def _required_str_tuple(mapping: Mapping[str, object], key: str, context: str) -> tuple[str, ...]:
    value = _required_sequence(mapping, key, context)
    strings: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item:
            raise ValueError(f"{context}.{key}[{index}] must be a non-empty string")
        strings.append(item)
    return tuple(strings)


def _required_mapping(mapping: Mapping[str, object], key: str, context: str) -> Mapping[str, object]:
    return _as_mapping(_required(mapping, key, context), f"{context}.{key}")


def _as_mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{context} must be an object")
    for key in value:
        if not isinstance(key, str):
            raise ValueError(f"{context} keys must be strings")
    return cast(Mapping[str, object], value)


def _reject_raw_fields(value: object, context: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{context} keys must be strings")
            normalized_key = re.sub(r"[^a-z0-9]", "", key.lower())
            if any(marker in normalized_key for marker in _FORBIDDEN_RAW_FIELD_MARKERS):
                raise ValueError(f"{context}.{key} is a forbidden raw auth/path/provider-output field")
            _reject_raw_fields(item, f"{context}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, str):
        for index, item in enumerate(value):
            _reject_raw_fields(item, f"{context}[{index}]")


__all__ = [
    "ExpectedOutcome",
    "Persona",
    "RUNTIMES",
    "ScenarioRow",
    "ScenarioSet",
    "WritePolicy",
    "default_scenario_path",
    "load_scenario_set",
    "validate_scenario_set",
]
