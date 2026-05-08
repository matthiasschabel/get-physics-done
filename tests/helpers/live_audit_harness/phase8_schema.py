"""Provider-free schema helpers for the Phase 8 live-provider matrix contract."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Final, cast

from gpd.adapters.runtime_catalog import list_runtime_names

SCHEMA_ID: Final[str] = "phase8.provider-persona-matrix.v1"
RUNTIMES: Final[tuple[str, ...]] = tuple(list_runtime_names())
LIVE_PROVIDER_MARKER: Final[str] = "live_provider"
LAUNCH_POLICIES: Final[frozenset[str]] = frozenset(
    {
        "fake",
        "manual_live",
        "nightly_live",
        "setup_refusal",
        "deferred",
    }
)
LIVE_LAUNCH_POLICIES: Final[frozenset[str]] = frozenset({"manual_live", "nightly_live"})
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
LIVE_ONLY_ARTIFACTS: Final[frozenset[str]] = frozenset(
    {
        "provider-attempt.json",
        "semantic-score.json",
        "redaction-report.json",
    }
)

_TOP_LEVEL_KEYS: Final[frozenset[str]] = frozenset(
    {
        "schema",
        "matrix_id",
        "default_pytest_policy",
        "personas",
        "scenario_templates",
        "rows",
    }
)
_DEFAULT_PYTEST_POLICY_KEYS: Final[frozenset[str]] = frozenset(
    {
        "live_rows_in_default_pytest",
        "provider_subprocess_allowed",
        "network_allowed",
        "required_live_marker",
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
_SCENARIO_TEMPLATE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "scenario_template_id",
        "scenario_family",
        "command_slug",
        "fixture_ref",
        "risk_class",
        "expected_outcome",
        "write_policy",
        "required_artifacts",
    }
)
_ROW_REQUIRED_KEYS: Final[frozenset[str]] = frozenset(
    {
        "row_id",
        "runtime",
        "persona_id",
        "scenario_template_id",
        "launch_policy",
        "default_pytest",
        "provider_subprocess_allowed",
        "network_allowed",
        "required_pytest_markers",
        "budget_policy",
        "live_artifacts",
    }
)
_ROW_ALLOWED_KEYS: Final[frozenset[str]] = _ROW_REQUIRED_KEYS | frozenset(
    {
        "setup_refusal_class",
        "deferred_reason_class",
    }
)
_BUDGET_POLICY_KEYS: Final[frozenset[str]] = frozenset(
    {
        "mode",
        "budget_id_class",
        "max_attempts",
        "max_mutating_rows",
    }
)
_WRITE_POLICY_MODES: Final[frozenset[str]] = frozenset(
    {
        "read_only",
        "repo_tmp_only",
        "controlled_relative_writes",
    }
)
_BUDGET_POLICY_MODES: Final[frozenset[str]] = frozenset({"none", "required_live_budget"})
_FORBIDDEN_RAW_FIELD_MARKERS: Final[frozenset[str]] = frozenset(
    {
        "accountemail",
        "accountidentifier",
        "accountid",
        "argv",
        "authfile",
        "authheader",
        "authpath",
        "authstate",
        "authorization",
        "envdump",
        "homepath",
        "localpath",
        "privatepath",
        "promptargv",
        "provideroutput",
        "providerstderr",
        "providerstdout",
        "rawauth",
        "rawenv",
        "rawpath",
        "rawprompt",
        "rawprovideroutput",
        "rawtranscript",
        "realpath",
        "stderr",
        "stdout",
        "transcript",
    }
)


@dataclass(frozen=True, slots=True)
class DefaultPytestPolicy:
    live_rows_in_default_pytest: bool
    provider_subprocess_allowed: bool
    network_allowed: bool
    required_live_marker: str


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
class ScenarioTemplate:
    scenario_template_id: str
    scenario_family: str
    command_slug: str
    fixture_ref: str
    risk_class: str
    expected_outcome: ExpectedOutcome
    write_policy: WritePolicy
    required_artifacts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BudgetPolicy:
    mode: str
    budget_id_class: str | None
    max_attempts: int | None
    max_mutating_rows: int | None


@dataclass(frozen=True, slots=True)
class MatrixRow:
    row_id: str
    runtime: str
    persona_id: str
    scenario_template_id: str
    launch_policy: str
    default_pytest: bool
    provider_subprocess_allowed: bool
    network_allowed: bool
    required_pytest_markers: tuple[str, ...]
    budget_policy: BudgetPolicy
    live_artifacts: tuple[str, ...]
    setup_refusal_class: str | None
    deferred_reason_class: str | None


@dataclass(frozen=True, slots=True)
class Phase8Matrix:
    schema: str
    matrix_id: str
    default_pytest_policy: DefaultPytestPolicy
    personas: tuple[Persona, ...]
    scenario_templates: tuple[ScenarioTemplate, ...]
    rows: tuple[MatrixRow, ...]


def default_phase8_matrix_path(repo_root: Path) -> Path:
    """Return the tracked Phase 8 provider-persona matrix fixture path."""

    return repo_root / "tests" / "fixtures" / "live_audit" / "phase8" / "provider_persona_matrix.json"


def load_phase8_matrix(path: Path) -> Phase8Matrix:
    """Load and validate a provider-free Phase 8 matrix fixture."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    return validate_phase8_matrix(_as_mapping(payload, "phase8_matrix payload"))


def validate_phase8_matrix(payload: Mapping[str, object]) -> Phase8Matrix:
    """Validate a class-only Phase 8 provider-persona matrix."""

    _reject_raw_fields(payload, "phase8_matrix")
    _require_keys(payload, _TOP_LEVEL_KEYS, _TOP_LEVEL_KEYS, "phase8_matrix")

    schema = _required_str(payload, "schema", "phase8_matrix")
    if schema != SCHEMA_ID:
        raise ValueError(f"phase8_matrix.schema must be exactly {SCHEMA_ID!r}")

    default_pytest_policy = _parse_default_pytest_policy(
        _required_mapping(payload, "default_pytest_policy", "phase8_matrix"),
        "phase8_matrix.default_pytest_policy",
    )
    personas = _parse_personas(_required_sequence(payload, "personas", "phase8_matrix"))
    persona_ids = frozenset(persona.persona_id for persona in personas)
    scenario_templates = _parse_scenario_templates(_required_sequence(payload, "scenario_templates", "phase8_matrix"))
    scenario_template_ids = frozenset(template.scenario_template_id for template in scenario_templates)
    rows = _parse_rows(
        _required_sequence(payload, "rows", "phase8_matrix"),
        persona_ids=persona_ids,
        scenario_template_ids=scenario_template_ids,
        default_pytest_policy=default_pytest_policy,
    )

    return Phase8Matrix(
        schema=schema,
        matrix_id=_required_str(payload, "matrix_id", "phase8_matrix"),
        default_pytest_policy=default_pytest_policy,
        personas=personas,
        scenario_templates=scenario_templates,
        rows=rows,
    )


def runtime_row_id_prefix(runtime: str) -> str:
    """Return the Phase 8 row id prefix for a catalog runtime name."""

    return f"P8-{runtime.upper()}-"


def _parse_default_pytest_policy(mapping: Mapping[str, object], context: str) -> DefaultPytestPolicy:
    _require_keys(mapping, _DEFAULT_PYTEST_POLICY_KEYS, _DEFAULT_PYTEST_POLICY_KEYS, context)

    live_rows_in_default_pytest = _required_bool(mapping, "live_rows_in_default_pytest", context)
    if live_rows_in_default_pytest:
        raise ValueError(f"{context}.live_rows_in_default_pytest must be false")

    provider_subprocess_allowed = _required_bool(mapping, "provider_subprocess_allowed", context)
    if provider_subprocess_allowed:
        raise ValueError(f"{context}.provider_subprocess_allowed must be false")

    network_allowed = _required_bool(mapping, "network_allowed", context)
    if network_allowed:
        raise ValueError(f"{context}.network_allowed must be false")

    required_live_marker = _required_str(mapping, "required_live_marker", context)
    if required_live_marker != LIVE_PROVIDER_MARKER:
        raise ValueError(f"{context}.required_live_marker must be exactly {LIVE_PROVIDER_MARKER!r}")

    return DefaultPytestPolicy(
        live_rows_in_default_pytest=live_rows_in_default_pytest,
        provider_subprocess_allowed=provider_subprocess_allowed,
        network_allowed=network_allowed,
        required_live_marker=required_live_marker,
    )


def _parse_personas(items: Sequence[object]) -> tuple[Persona, ...]:
    personas: list[Persona] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(items):
        context = f"phase8_matrix.personas[{index}]"
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


def _parse_scenario_templates(items: Sequence[object]) -> tuple[ScenarioTemplate, ...]:
    scenario_templates: list[ScenarioTemplate] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(items):
        context = f"phase8_matrix.scenario_templates[{index}]"
        mapping = _as_mapping(item, context)
        _require_keys(mapping, _SCENARIO_TEMPLATE_KEYS, _SCENARIO_TEMPLATE_KEYS, context)
        scenario_template_id = _required_str(mapping, "scenario_template_id", context)
        if scenario_template_id in seen_ids:
            raise ValueError(f"duplicate scenario_template_id {scenario_template_id!r}")
        seen_ids.add(scenario_template_id)
        required_artifacts = _required_str_tuple(mapping, "required_artifacts", context)
        _validate_required_artifacts(required_artifacts, context)
        scenario_templates.append(
            ScenarioTemplate(
                scenario_template_id=scenario_template_id,
                scenario_family=_required_str(mapping, "scenario_family", context),
                command_slug=_required_str(mapping, "command_slug", context),
                fixture_ref=_required_str(mapping, "fixture_ref", context),
                risk_class=_required_str(mapping, "risk_class", context),
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
    return tuple(scenario_templates)


def _parse_rows(
    items: Sequence[object],
    *,
    persona_ids: frozenset[str],
    scenario_template_ids: frozenset[str],
    default_pytest_policy: DefaultPytestPolicy,
) -> tuple[MatrixRow, ...]:
    rows: list[MatrixRow] = []
    seen_row_ids: set[str] = set()
    for index, item in enumerate(items):
        context = f"phase8_matrix.rows[{index}]"
        mapping = _as_mapping(item, context)
        _require_keys(mapping, _ROW_REQUIRED_KEYS, _ROW_ALLOWED_KEYS, context)

        row_id = _required_str(mapping, "row_id", context)
        if row_id in seen_row_ids:
            raise ValueError(f"duplicate row_id {row_id!r}")
        seen_row_ids.add(row_id)

        runtime = _required_str(mapping, "runtime", context)
        if runtime not in RUNTIMES:
            raise ValueError(f"{context}.runtime must be one of {RUNTIMES!r}")
        runtime_prefix = runtime_row_id_prefix(runtime)
        if not row_id.startswith(runtime_prefix):
            raise ValueError(f"{context}.row_id must start with {runtime_prefix!r}")

        persona_id = _required_str(mapping, "persona_id", context)
        if persona_id not in persona_ids:
            raise ValueError(f"{context}.persona_id {persona_id!r} does not reference a declared persona")

        scenario_template_id = _required_str(mapping, "scenario_template_id", context)
        if scenario_template_id not in scenario_template_ids:
            raise ValueError(
                f"{context}.scenario_template_id {scenario_template_id!r} does not reference a declared template"
            )

        launch_policy = _required_str(mapping, "launch_policy", context)
        if launch_policy not in LAUNCH_POLICIES:
            raise ValueError(f"{context}.launch_policy must be one of {sorted(LAUNCH_POLICIES)!r}")

        default_pytest = _required_bool(mapping, "default_pytest", context)
        provider_subprocess_allowed = _required_bool(mapping, "provider_subprocess_allowed", context)
        network_allowed = _required_bool(mapping, "network_allowed", context)
        required_pytest_markers = _required_str_tuple(mapping, "required_pytest_markers", context)
        budget_policy = _parse_budget_policy(
            _required_mapping(mapping, "budget_policy", context), f"{context}.budget_policy"
        )
        live_artifacts = _required_str_tuple(mapping, "live_artifacts", context)
        setup_refusal_class = _optional_str(mapping, "setup_refusal_class", context)
        deferred_reason_class = _optional_str(mapping, "deferred_reason_class", context)

        _validate_launch_policy_contract(
            context=context,
            launch_policy=launch_policy,
            default_pytest=default_pytest,
            provider_subprocess_allowed=provider_subprocess_allowed,
            network_allowed=network_allowed,
            required_pytest_markers=required_pytest_markers,
            budget_policy=budget_policy,
            live_artifacts=live_artifacts,
            setup_refusal_class=setup_refusal_class,
            deferred_reason_class=deferred_reason_class,
            default_pytest_policy=default_pytest_policy,
        )

        rows.append(
            MatrixRow(
                row_id=row_id,
                runtime=runtime,
                persona_id=persona_id,
                scenario_template_id=scenario_template_id,
                launch_policy=launch_policy,
                default_pytest=default_pytest,
                provider_subprocess_allowed=provider_subprocess_allowed,
                network_allowed=network_allowed,
                required_pytest_markers=required_pytest_markers,
                budget_policy=budget_policy,
                live_artifacts=live_artifacts,
                setup_refusal_class=setup_refusal_class,
                deferred_reason_class=deferred_reason_class,
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


def _parse_budget_policy(mapping: Mapping[str, object], context: str) -> BudgetPolicy:
    _require_keys(mapping, frozenset({"mode"}), _BUDGET_POLICY_KEYS, context)
    mode = _required_str(mapping, "mode", context)
    if mode not in _BUDGET_POLICY_MODES:
        raise ValueError(f"{context}.mode must be one of {sorted(_BUDGET_POLICY_MODES)!r}")

    budget_id_class = _optional_str(mapping, "budget_id_class", context)
    max_attempts = _optional_positive_int(mapping, "max_attempts", context)
    max_mutating_rows = _optional_non_negative_int(mapping, "max_mutating_rows", context)
    if mode == "none":
        extras = sorted(set(mapping) - {"mode"})
        if extras:
            raise ValueError(f"{context} must only contain mode when mode is 'none': {extras!r}")
    else:
        if budget_id_class is None:
            raise ValueError(f"{context}.budget_id_class is required when mode is 'required_live_budget'")
        if max_attempts is None:
            raise ValueError(f"{context}.max_attempts is required when mode is 'required_live_budget'")
        if max_mutating_rows is None:
            raise ValueError(f"{context}.max_mutating_rows is required when mode is 'required_live_budget'")

    return BudgetPolicy(
        mode=mode,
        budget_id_class=budget_id_class,
        max_attempts=max_attempts,
        max_mutating_rows=max_mutating_rows,
    )


def _validate_launch_policy_contract(
    *,
    context: str,
    launch_policy: str,
    default_pytest: bool,
    provider_subprocess_allowed: bool,
    network_allowed: bool,
    required_pytest_markers: tuple[str, ...],
    budget_policy: BudgetPolicy,
    live_artifacts: tuple[str, ...],
    setup_refusal_class: str | None,
    deferred_reason_class: str | None,
    default_pytest_policy: DefaultPytestPolicy,
) -> None:
    if len(set(required_pytest_markers)) != len(required_pytest_markers):
        raise ValueError(f"{context}.required_pytest_markers must not contain duplicates")
    if len(set(live_artifacts)) != len(live_artifacts):
        raise ValueError(f"{context}.live_artifacts must not contain duplicates")

    if launch_policy == "fake":
        if not default_pytest:
            raise ValueError(f"{context}.default_pytest must be true for fake rows")
        if provider_subprocess_allowed:
            raise ValueError(f"{context}.provider_subprocess_allowed must be false for fake rows")
        if network_allowed:
            raise ValueError(f"{context}.network_allowed must be false for fake rows")
        if required_pytest_markers:
            raise ValueError(f"{context}.required_pytest_markers must be empty for fake rows")
        if budget_policy.mode != "none":
            raise ValueError(f"{context}.budget_policy.mode must be 'none' for fake rows")
        if live_artifacts:
            raise ValueError(f"{context}.live_artifacts must be empty for fake rows")
    elif launch_policy in LIVE_LAUNCH_POLICIES:
        if default_pytest or default_pytest_policy.live_rows_in_default_pytest:
            raise ValueError(f"{context}.default_pytest must be false for live rows")
        if not provider_subprocess_allowed:
            raise ValueError(f"{context}.provider_subprocess_allowed must be true for live rows")
        if not network_allowed:
            raise ValueError(f"{context}.network_allowed must be true for live rows")
        if default_pytest_policy.required_live_marker not in required_pytest_markers:
            raise ValueError(f"{context}.required_pytest_markers must include {LIVE_PROVIDER_MARKER!r} for live rows")
        if budget_policy.mode != "required_live_budget":
            raise ValueError(f"{context}.budget_policy.mode must be 'required_live_budget' for live rows")
        _validate_live_artifacts(live_artifacts, context)
    else:
        if default_pytest:
            raise ValueError(f"{context}.default_pytest must be false for {launch_policy} rows")
        if provider_subprocess_allowed:
            raise ValueError(f"{context}.provider_subprocess_allowed must be false for {launch_policy} rows")
        if network_allowed:
            raise ValueError(f"{context}.network_allowed must be false for {launch_policy} rows")
        if LIVE_PROVIDER_MARKER in required_pytest_markers:
            raise ValueError(f"{context}.required_pytest_markers must not include {LIVE_PROVIDER_MARKER!r}")
        if budget_policy.mode != "none":
            raise ValueError(f"{context}.budget_policy.mode must be 'none' for {launch_policy} rows")
        if live_artifacts:
            raise ValueError(f"{context}.live_artifacts must be empty for {launch_policy} rows")

    if launch_policy == "setup_refusal" and setup_refusal_class is None:
        raise ValueError(f"{context}.setup_refusal_class is required for setup_refusal rows")
    if launch_policy != "setup_refusal" and setup_refusal_class is not None:
        raise ValueError(f"{context}.setup_refusal_class is only allowed for setup_refusal rows")
    if launch_policy == "deferred" and deferred_reason_class is None:
        raise ValueError(f"{context}.deferred_reason_class is required for deferred rows")
    if launch_policy != "deferred" and deferred_reason_class is not None:
        raise ValueError(f"{context}.deferred_reason_class is only allowed for deferred rows")


def _validate_required_artifacts(artifacts: tuple[str, ...], context: str) -> None:
    if len(set(artifacts)) != len(artifacts):
        raise ValueError(f"{context}.required_artifacts must not contain duplicates")
    missing = sorted(REQUIRED_ARTIFACTS.difference(artifacts))
    if missing:
        raise ValueError(f"{context}.required_artifacts missing required artifacts: {missing!r}")


def _validate_live_artifacts(artifacts: tuple[str, ...], context: str) -> None:
    missing = sorted(LIVE_ONLY_ARTIFACTS.difference(artifacts))
    if missing:
        raise ValueError(f"{context}.live_artifacts missing required artifacts: {missing!r}")


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
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{context}.{key} must be a non-empty string")
    return value


def _optional_str(mapping: Mapping[str, object], key: str, context: str) -> str | None:
    if key not in mapping:
        return None
    value = mapping[key]
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{context}.{key} must be a non-empty string")
    return value


def _required_bool(mapping: Mapping[str, object], key: str, context: str) -> bool:
    value = _required(mapping, key, context)
    if type(value) is not bool:
        raise ValueError(f"{context}.{key} must be a boolean")
    return value


def _optional_positive_int(mapping: Mapping[str, object], key: str, context: str) -> int | None:
    if key not in mapping:
        return None
    value = mapping[key]
    if type(value) is not int or value <= 0:
        raise ValueError(f"{context}.{key} must be a positive integer")
    return value


def _optional_non_negative_int(mapping: Mapping[str, object], key: str, context: str) -> int | None:
    if key not in mapping:
        return None
    value = mapping[key]
    if type(value) is not int or value < 0:
        raise ValueError(f"{context}.{key} must be a non-negative integer")
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
        if not isinstance(item, str) or not item or item != item.strip():
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
    "BudgetPolicy",
    "DefaultPytestPolicy",
    "ExpectedOutcome",
    "LAUNCH_POLICIES",
    "LIVE_LAUNCH_POLICIES",
    "LIVE_ONLY_ARTIFACTS",
    "LIVE_PROVIDER_MARKER",
    "MatrixRow",
    "Persona",
    "Phase8Matrix",
    "REQUIRED_ARTIFACTS",
    "RUNTIMES",
    "SCHEMA_ID",
    "ScenarioTemplate",
    "WritePolicy",
    "default_phase8_matrix_path",
    "load_phase8_matrix",
    "runtime_row_id_prefix",
    "validate_phase8_matrix",
]
