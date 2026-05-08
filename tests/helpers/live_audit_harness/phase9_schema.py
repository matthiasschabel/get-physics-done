"""Provider-free schema helpers for the Phase 9 behavior matrix contract."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Final, cast

from gpd.adapters.runtime_catalog import list_runtime_names

SCHEMA_ID: Final[str] = "phase9.behavior-matrix.v1"
RUNTIMES: Final[tuple[str, ...]] = tuple(list_runtime_names())
LAUNCH_POLICY: Final[str] = "fake"
REQUIRED_SIDECARS: Final[frozenset[str]] = frozenset(
    {
        "status.json",
        "stdout.jsonl",
        "normalized-events.jsonl",
        "final.md",
        "write-classification.json",
        "evidence-packet.json",
    }
)

ROW_ROLES: Final[frozenset[str]] = frozenset({"green", "bad_behavior_sentinel"})
EXPECTED_BEHAVIOR_RESULTS: Final[frozenset[str]] = frozenset({"green", "yellow", "red", "invalid_evidence"})
WRITE_POLICY_MODES: Final[frozenset[str]] = frozenset(
    {
        "read_only",
        "repo_tmp_only",
        "controlled_relative_writes",
    }
)

_TOP_LEVEL_KEYS: Final[frozenset[str]] = frozenset(
    {
        "schema",
        "matrix_id",
        "default_pytest_policy",
        "required_sidecars",
        "personas",
        "behavior_contracts",
        "sidecar_profiles",
        "rows",
    }
)
_DEFAULT_PYTEST_POLICY_KEYS: Final[frozenset[str]] = frozenset(
    {
        "launch_policy",
        "default_pytest",
        "provider_subprocess_allowed",
        "network_allowed",
        "required_pytest_markers",
    }
)
_PERSONA_KEYS: Final[frozenset[str]] = frozenset(
    {
        "persona_id",
        "persona_class",
        "support_classes",
        "forbidden_assumption_classes",
    }
)
_BEHAVIOR_CONTRACT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "behavior_contract_id",
        "scenario_family",
        "command_slug",
        "risk_class",
        "required_behavior_classes",
        "forbidden_behavior_classes",
        "hard_failure_classes",
        "allowed_yellow_classes",
        "expected_metric_bounds",
        "write_policy",
        "required_sidecars",
    }
)
_METRIC_BOUNDS_KEYS: Final[frozenset[str]] = frozenset(
    {
        "max_setup_turns",
        "max_recovery_turns",
        "max_duplicate_question_buckets",
        "max_false_success_claims",
        "max_unexpected_writes",
        "max_stop_violations",
        "prompt_budget_class",
        "schema_failure_class",
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
_SIDECAR_PROFILE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "sidecar_profile_id",
        "expected_behavior_result_class",
        "expected_finding_ids",
        "expected_schema_failure_classes",
        "observed_behavior_classes",
        "metric_classes",
    }
)
_ROW_KEYS: Final[frozenset[str]] = frozenset(
    {
        "row_id",
        "runtime",
        "persona_id",
        "scenario_id",
        "behavior_contract_id",
        "sidecar_profile_id",
        "row_role",
        "launch_policy",
        "default_pytest",
        "provider_subprocess_allowed",
        "network_allowed",
        "required_pytest_markers",
        "required_sidecars",
    }
)
_CLASS_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_.-]*$")
_ID_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Z0-9][A-Z0-9_-]*$")
_FORBIDDEN_RAW_FIELD_EXACT_MARKERS: Final[frozenset[str]] = frozenset(
    {
        "argv",
        "env",
        "stderr",
        "stdout",
        "transcript",
    }
)
_FORBIDDEN_RAW_FIELD_SUBSTRINGS: Final[frozenset[str]] = frozenset(
    {
        "accountemail",
        "accountidentifier",
        "accountid",
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
        "rawprovider",
        "rawtranscript",
        "realpath",
    }
)
_FORBIDDEN_RAW_STRING_MARKERS: Final[tuple[str, ...]] = (
    "/Users/",
    "\\Users\\",
    "~/",
    "<environment_context>",
    "BEGIN PRIVATE KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
)


@dataclass(frozen=True, slots=True)
class DefaultPytestPolicy:
    launch_policy: str
    default_pytest: bool
    provider_subprocess_allowed: bool
    network_allowed: bool
    required_pytest_markers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Persona:
    persona_id: str
    persona_class: str
    support_classes: tuple[str, ...]
    forbidden_assumption_classes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MetricBounds:
    max_setup_turns: int
    max_recovery_turns: int
    max_duplicate_question_buckets: int
    max_false_success_claims: int
    max_unexpected_writes: int
    max_stop_violations: int
    prompt_budget_class: str
    schema_failure_class: str


@dataclass(frozen=True, slots=True)
class WritePolicy:
    policy_id: str
    mode: str
    allowed_paths: tuple[str, ...]
    forbidden_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BehaviorContract:
    behavior_contract_id: str
    scenario_family: str
    command_slug: str
    risk_class: str
    required_behavior_classes: tuple[str, ...]
    forbidden_behavior_classes: tuple[str, ...]
    hard_failure_classes: tuple[str, ...]
    allowed_yellow_classes: tuple[str, ...]
    expected_metric_bounds: MetricBounds
    write_policy: WritePolicy
    required_sidecars: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SidecarProfile:
    sidecar_profile_id: str
    expected_behavior_result_class: str
    expected_finding_ids: tuple[str, ...]
    expected_schema_failure_classes: tuple[str, ...]
    observed_behavior_classes: tuple[str, ...]
    metric_classes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MatrixRow:
    row_id: str
    runtime: str
    persona_id: str
    scenario_id: str
    behavior_contract_id: str
    sidecar_profile_id: str
    row_role: str
    launch_policy: str
    default_pytest: bool
    provider_subprocess_allowed: bool
    network_allowed: bool
    required_pytest_markers: tuple[str, ...]
    required_sidecars: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Phase9BehaviorMatrix:
    schema: str
    matrix_id: str
    default_pytest_policy: DefaultPytestPolicy
    required_sidecars: tuple[str, ...]
    personas: tuple[Persona, ...]
    behavior_contracts: tuple[BehaviorContract, ...]
    sidecar_profiles: tuple[SidecarProfile, ...]
    rows: tuple[MatrixRow, ...]


def default_phase9_behavior_matrix_path(repo_root: Path) -> Path:
    """Return the tracked Phase 9 behavior matrix fixture path."""

    return repo_root / "tests" / "fixtures" / "live_audit" / "phase9" / "behavior_matrix.json"


def load_phase9_behavior_matrix(path: Path) -> Phase9BehaviorMatrix:
    """Load and validate a provider-free Phase 9 behavior matrix fixture."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    return validate_phase9_behavior_matrix(_as_mapping(payload, "phase9_behavior_matrix payload"))


def validate_phase9_behavior_matrix(payload: Mapping[str, object]) -> Phase9BehaviorMatrix:
    """Validate a class-only Phase 9 fake behavior matrix."""

    _reject_raw_fields(payload, "phase9_behavior_matrix")
    _require_keys(payload, _TOP_LEVEL_KEYS, _TOP_LEVEL_KEYS, "phase9_behavior_matrix")

    schema = _required_str(payload, "schema", "phase9_behavior_matrix")
    if schema != SCHEMA_ID:
        raise ValueError(f"phase9_behavior_matrix.schema must be exactly {SCHEMA_ID!r}")

    required_sidecars = _required_str_tuple(payload, "required_sidecars", "phase9_behavior_matrix")
    _validate_required_sidecars(required_sidecars, "phase9_behavior_matrix.required_sidecars")
    default_pytest_policy = _parse_default_pytest_policy(
        _required_mapping(payload, "default_pytest_policy", "phase9_behavior_matrix"),
        "phase9_behavior_matrix.default_pytest_policy",
    )

    personas = _parse_personas(_required_sequence(payload, "personas", "phase9_behavior_matrix"))
    persona_ids = frozenset(persona.persona_id for persona in personas)
    behavior_contracts = _parse_behavior_contracts(
        _required_sequence(payload, "behavior_contracts", "phase9_behavior_matrix")
    )
    contract_by_id = {contract.behavior_contract_id: contract for contract in behavior_contracts}
    sidecar_profiles = _parse_sidecar_profiles(
        _required_sequence(payload, "sidecar_profiles", "phase9_behavior_matrix")
    )
    profile_by_id = {profile.sidecar_profile_id: profile for profile in sidecar_profiles}
    rows = _parse_rows(
        _required_sequence(payload, "rows", "phase9_behavior_matrix"),
        persona_ids=persona_ids,
        contract_by_id=contract_by_id,
        profile_by_id=profile_by_id,
        default_pytest_policy=default_pytest_policy,
    )
    _validate_fixture_usefulness(
        behavior_contracts=behavior_contracts,
        sidecar_profiles=sidecar_profiles,
        rows=rows,
    )

    return Phase9BehaviorMatrix(
        schema=schema,
        matrix_id=_required_str(payload, "matrix_id", "phase9_behavior_matrix"),
        default_pytest_policy=default_pytest_policy,
        required_sidecars=required_sidecars,
        personas=personas,
        behavior_contracts=behavior_contracts,
        sidecar_profiles=sidecar_profiles,
        rows=rows,
    )


def runtime_row_id_prefix(runtime: str) -> str:
    """Return the Phase 9 row id prefix for a catalog runtime name."""

    return f"P9-{runtime.upper()}-"


def _parse_default_pytest_policy(mapping: Mapping[str, object], context: str) -> DefaultPytestPolicy:
    _require_keys(mapping, _DEFAULT_PYTEST_POLICY_KEYS, _DEFAULT_PYTEST_POLICY_KEYS, context)

    launch_policy = _required_str(mapping, "launch_policy", context)
    if launch_policy != LAUNCH_POLICY:
        raise ValueError(f"{context}.launch_policy must be exactly {LAUNCH_POLICY!r}")

    default_pytest = _required_bool(mapping, "default_pytest", context)
    if not default_pytest:
        raise ValueError(f"{context}.default_pytest must be true")

    provider_subprocess_allowed = _required_bool(mapping, "provider_subprocess_allowed", context)
    if provider_subprocess_allowed:
        raise ValueError(f"{context}.provider_subprocess_allowed must be false")

    network_allowed = _required_bool(mapping, "network_allowed", context)
    if network_allowed:
        raise ValueError(f"{context}.network_allowed must be false")

    required_pytest_markers = _required_str_tuple(mapping, "required_pytest_markers", context)
    if required_pytest_markers:
        raise ValueError(f"{context}.required_pytest_markers must be empty")

    return DefaultPytestPolicy(
        launch_policy=launch_policy,
        default_pytest=default_pytest,
        provider_subprocess_allowed=provider_subprocess_allowed,
        network_allowed=network_allowed,
        required_pytest_markers=required_pytest_markers,
    )


def _parse_personas(items: Sequence[object]) -> tuple[Persona, ...]:
    personas: list[Persona] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(items):
        context = f"phase9_behavior_matrix.personas[{index}]"
        mapping = _as_mapping(item, context)
        _require_keys(mapping, _PERSONA_KEYS, _PERSONA_KEYS, context)
        persona_id = _required_id(mapping, "persona_id", context)
        if persona_id in seen_ids:
            raise ValueError(f"duplicate persona_id {persona_id!r}")
        seen_ids.add(persona_id)
        personas.append(
            Persona(
                persona_id=persona_id,
                persona_class=_required_class_token(mapping, "persona_class", context),
                support_classes=_required_class_tuple(mapping, "support_classes", context),
                forbidden_assumption_classes=_required_class_tuple(mapping, "forbidden_assumption_classes", context),
            )
        )
    return tuple(personas)


def _parse_behavior_contracts(items: Sequence[object]) -> tuple[BehaviorContract, ...]:
    contracts: list[BehaviorContract] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(items):
        context = f"phase9_behavior_matrix.behavior_contracts[{index}]"
        mapping = _as_mapping(item, context)
        _require_keys(mapping, _BEHAVIOR_CONTRACT_KEYS, _BEHAVIOR_CONTRACT_KEYS, context)
        behavior_contract_id = _required_class_token(mapping, "behavior_contract_id", context)
        if behavior_contract_id in seen_ids:
            raise ValueError(f"duplicate behavior_contract_id {behavior_contract_id!r}")
        seen_ids.add(behavior_contract_id)
        required_sidecars = _required_str_tuple(mapping, "required_sidecars", context)
        _validate_required_sidecars(required_sidecars, f"{context}.required_sidecars")
        required_behavior_classes = _required_class_tuple(mapping, "required_behavior_classes", context)
        if not required_behavior_classes:
            raise ValueError(f"{context}.required_behavior_classes must not be empty")
        forbidden_behavior_classes = _required_class_tuple(mapping, "forbidden_behavior_classes", context)
        if not forbidden_behavior_classes:
            raise ValueError(f"{context}.forbidden_behavior_classes must not be empty")
        hard_failure_classes = _required_class_tuple(mapping, "hard_failure_classes", context)
        allowed_yellow_classes = _required_class_tuple(mapping, "allowed_yellow_classes", context)
        if set(hard_failure_classes).intersection(allowed_yellow_classes):
            raise ValueError(f"{context}.hard_failure_classes must not overlap allowed_yellow_classes")
        contracts.append(
            BehaviorContract(
                behavior_contract_id=behavior_contract_id,
                scenario_family=_required_class_token(mapping, "scenario_family", context),
                command_slug=_required_class_token(mapping, "command_slug", context),
                risk_class=_required_class_token(mapping, "risk_class", context),
                required_behavior_classes=required_behavior_classes,
                forbidden_behavior_classes=forbidden_behavior_classes,
                hard_failure_classes=hard_failure_classes,
                allowed_yellow_classes=allowed_yellow_classes,
                expected_metric_bounds=_parse_metric_bounds(
                    _required_mapping(mapping, "expected_metric_bounds", context),
                    f"{context}.expected_metric_bounds",
                ),
                write_policy=_parse_write_policy(
                    _required_mapping(mapping, "write_policy", context),
                    f"{context}.write_policy",
                ),
                required_sidecars=required_sidecars,
            )
        )
    return tuple(contracts)


def _parse_metric_bounds(mapping: Mapping[str, object], context: str) -> MetricBounds:
    _require_keys(mapping, _METRIC_BOUNDS_KEYS, _METRIC_BOUNDS_KEYS, context)
    return MetricBounds(
        max_setup_turns=_required_non_negative_int(mapping, "max_setup_turns", context),
        max_recovery_turns=_required_non_negative_int(mapping, "max_recovery_turns", context),
        max_duplicate_question_buckets=_required_non_negative_int(mapping, "max_duplicate_question_buckets", context),
        max_false_success_claims=_required_non_negative_int(mapping, "max_false_success_claims", context),
        max_unexpected_writes=_required_non_negative_int(mapping, "max_unexpected_writes", context),
        max_stop_violations=_required_non_negative_int(mapping, "max_stop_violations", context),
        prompt_budget_class=_required_class_token(mapping, "prompt_budget_class", context),
        schema_failure_class=_required_class_token(mapping, "schema_failure_class", context),
    )


def _parse_write_policy(mapping: Mapping[str, object], context: str) -> WritePolicy:
    _require_keys(mapping, _WRITE_POLICY_KEYS, _WRITE_POLICY_KEYS, context)
    mode = _required_class_token(mapping, "mode", context)
    if mode not in WRITE_POLICY_MODES:
        raise ValueError(f"{context}.mode must be one of {sorted(WRITE_POLICY_MODES)!r}")

    allowed_paths = _required_str_tuple(mapping, "allowed_paths", context)
    forbidden_paths = _required_str_tuple(mapping, "forbidden_paths", context)
    for path in (*allowed_paths, *forbidden_paths):
        _validate_relative_path(path, context)

    return WritePolicy(
        policy_id=_required_class_token(mapping, "policy_id", context),
        mode=mode,
        allowed_paths=allowed_paths,
        forbidden_paths=forbidden_paths,
    )


def _parse_sidecar_profiles(items: Sequence[object]) -> tuple[SidecarProfile, ...]:
    profiles: list[SidecarProfile] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(items):
        context = f"phase9_behavior_matrix.sidecar_profiles[{index}]"
        mapping = _as_mapping(item, context)
        _require_keys(mapping, _SIDECAR_PROFILE_KEYS, _SIDECAR_PROFILE_KEYS, context)
        sidecar_profile_id = _required_class_token(mapping, "sidecar_profile_id", context)
        if sidecar_profile_id in seen_ids:
            raise ValueError(f"duplicate sidecar_profile_id {sidecar_profile_id!r}")
        seen_ids.add(sidecar_profile_id)
        expected_behavior_result_class = _required_class_token(mapping, "expected_behavior_result_class", context)
        if expected_behavior_result_class not in EXPECTED_BEHAVIOR_RESULTS:
            raise ValueError(
                f"{context}.expected_behavior_result_class must be one of {sorted(EXPECTED_BEHAVIOR_RESULTS)!r}"
            )
        expected_finding_ids = _required_class_tuple(mapping, "expected_finding_ids", context)
        expected_schema_failure_classes = _required_class_tuple(mapping, "expected_schema_failure_classes", context)
        observed_behavior_classes = _required_class_tuple(mapping, "observed_behavior_classes", context)
        metric_classes = _required_class_tuple(mapping, "metric_classes", context)
        profiles.append(
            SidecarProfile(
                sidecar_profile_id=sidecar_profile_id,
                expected_behavior_result_class=expected_behavior_result_class,
                expected_finding_ids=expected_finding_ids,
                expected_schema_failure_classes=expected_schema_failure_classes,
                observed_behavior_classes=observed_behavior_classes,
                metric_classes=metric_classes,
            )
        )
    return tuple(profiles)


def _parse_rows(
    items: Sequence[object],
    *,
    persona_ids: frozenset[str],
    contract_by_id: Mapping[str, BehaviorContract],
    profile_by_id: Mapping[str, SidecarProfile],
    default_pytest_policy: DefaultPytestPolicy,
) -> tuple[MatrixRow, ...]:
    rows: list[MatrixRow] = []
    seen_row_ids: set[str] = set()
    for index, item in enumerate(items):
        context = f"phase9_behavior_matrix.rows[{index}]"
        mapping = _as_mapping(item, context)
        _require_keys(mapping, _ROW_KEYS, _ROW_KEYS, context)

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

        persona_id = _required_id(mapping, "persona_id", context)
        if persona_id not in persona_ids:
            raise ValueError(f"{context}.persona_id {persona_id!r} does not reference a declared persona")

        scenario_id = _required_id(mapping, "scenario_id", context)
        behavior_contract_id = _required_class_token(mapping, "behavior_contract_id", context)
        try:
            contract = contract_by_id[behavior_contract_id]
        except KeyError as exc:
            raise ValueError(
                f"{context}.behavior_contract_id {behavior_contract_id!r} does not reference a declared contract"
            ) from exc

        sidecar_profile_id = _required_class_token(mapping, "sidecar_profile_id", context)
        try:
            profile = profile_by_id[sidecar_profile_id]
        except KeyError as exc:
            raise ValueError(
                f"{context}.sidecar_profile_id {sidecar_profile_id!r} does not reference a declared profile"
            ) from exc

        row_role = _required_class_token(mapping, "row_role", context)
        if row_role not in ROW_ROLES:
            raise ValueError(f"{context}.row_role must be one of {sorted(ROW_ROLES)!r}")

        launch_policy = _required_str(mapping, "launch_policy", context)
        default_pytest = _required_bool(mapping, "default_pytest", context)
        provider_subprocess_allowed = _required_bool(mapping, "provider_subprocess_allowed", context)
        network_allowed = _required_bool(mapping, "network_allowed", context)
        required_pytest_markers = _required_str_tuple(mapping, "required_pytest_markers", context)
        required_sidecars = _required_str_tuple(mapping, "required_sidecars", context)

        _validate_row_provider_free_contract(
            context=context,
            launch_policy=launch_policy,
            default_pytest=default_pytest,
            provider_subprocess_allowed=provider_subprocess_allowed,
            network_allowed=network_allowed,
            required_pytest_markers=required_pytest_markers,
            required_sidecars=required_sidecars,
            default_pytest_policy=default_pytest_policy,
        )
        _validate_row_profile_contract(context=context, row_role=row_role, contract=contract, profile=profile)

        rows.append(
            MatrixRow(
                row_id=row_id,
                runtime=runtime,
                persona_id=persona_id,
                scenario_id=scenario_id,
                behavior_contract_id=behavior_contract_id,
                sidecar_profile_id=sidecar_profile_id,
                row_role=row_role,
                launch_policy=launch_policy,
                default_pytest=default_pytest,
                provider_subprocess_allowed=provider_subprocess_allowed,
                network_allowed=network_allowed,
                required_pytest_markers=required_pytest_markers,
                required_sidecars=required_sidecars,
            )
        )
    return tuple(rows)


def _validate_row_provider_free_contract(
    *,
    context: str,
    launch_policy: str,
    default_pytest: bool,
    provider_subprocess_allowed: bool,
    network_allowed: bool,
    required_pytest_markers: tuple[str, ...],
    required_sidecars: tuple[str, ...],
    default_pytest_policy: DefaultPytestPolicy,
) -> None:
    if launch_policy != default_pytest_policy.launch_policy:
        raise ValueError(f"{context}.launch_policy must be exactly {LAUNCH_POLICY!r}")
    if default_pytest != default_pytest_policy.default_pytest:
        raise ValueError(f"{context}.default_pytest must be true")
    if provider_subprocess_allowed != default_pytest_policy.provider_subprocess_allowed:
        raise ValueError(f"{context}.provider_subprocess_allowed must be false")
    if network_allowed != default_pytest_policy.network_allowed:
        raise ValueError(f"{context}.network_allowed must be false")
    if required_pytest_markers != default_pytest_policy.required_pytest_markers:
        raise ValueError(f"{context}.required_pytest_markers must be empty")
    _validate_required_sidecars(required_sidecars, f"{context}.required_sidecars")


def _validate_row_profile_contract(
    *,
    context: str,
    row_role: str,
    contract: BehaviorContract,
    profile: SidecarProfile,
) -> None:
    observed_classes = set(profile.observed_behavior_classes)
    required_classes = set(contract.required_behavior_classes)
    forbidden_classes = set(contract.forbidden_behavior_classes)
    expected_failures = set(profile.expected_finding_ids).union(profile.expected_schema_failure_classes)

    if row_role == "green":
        if profile.expected_behavior_result_class != "green":
            raise ValueError(f"{context}.row_role green requires a green sidecar profile")
        missing_required = sorted(required_classes.difference(observed_classes))
        if missing_required:
            raise ValueError(f"{context}.sidecar_profile_id missing required behavior classes: {missing_required!r}")
        observed_forbidden = sorted(forbidden_classes.intersection(observed_classes))
        if observed_forbidden:
            raise ValueError(f"{context}.sidecar_profile_id observes forbidden classes: {observed_forbidden!r}")
        if expected_failures:
            raise ValueError(f"{context}.sidecar_profile_id green profiles must not expect failures")
    else:
        if profile.expected_behavior_result_class == "green":
            raise ValueError(f"{context}.row_role bad_behavior_sentinel requires a non-green sidecar profile")
        if not expected_failures:
            raise ValueError(f"{context}.row_role bad_behavior_sentinel requires expected findings or schema failures")


def _validate_fixture_usefulness(
    *,
    behavior_contracts: tuple[BehaviorContract, ...],
    sidecar_profiles: tuple[SidecarProfile, ...],
    rows: tuple[MatrixRow, ...],
) -> None:
    if not rows:
        raise ValueError("phase9_behavior_matrix.rows must not be empty")
    if not any(row.row_role == "green" for row in rows):
        raise ValueError("phase9_behavior_matrix.rows must include green rows")
    if not any(row.row_role == "bad_behavior_sentinel" for row in rows):
        raise ValueError("phase9_behavior_matrix.rows must include bad behavior sentinels")

    referenced_contracts = {row.behavior_contract_id for row in rows}
    unreferenced_contracts = sorted(
        contract.behavior_contract_id
        for contract in behavior_contracts
        if contract.behavior_contract_id not in referenced_contracts
    )
    if unreferenced_contracts:
        raise ValueError(f"unreferenced behavior_contract_id values: {unreferenced_contracts!r}")

    referenced_profiles = {row.sidecar_profile_id for row in rows}
    unreferenced_profiles = sorted(
        profile.sidecar_profile_id
        for profile in sidecar_profiles
        if profile.sidecar_profile_id not in referenced_profiles
    )
    if unreferenced_profiles:
        raise ValueError(f"unreferenced sidecar_profile_id values: {unreferenced_profiles!r}")


def _validate_required_sidecars(sidecars: tuple[str, ...], context: str) -> None:
    if len(set(sidecars)) != len(sidecars):
        raise ValueError(f"{context} must not contain duplicates")
    missing = sorted(REQUIRED_SIDECARS.difference(sidecars))
    extra = sorted(set(sidecars).difference(REQUIRED_SIDECARS))
    if missing or extra:
        raise ValueError(f"{context} must be exactly the six required sidecars; missing={missing!r} extra={extra!r}")


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


def _required_id(mapping: Mapping[str, object], key: str, context: str) -> str:
    value = _required_str(mapping, key, context)
    if not _ID_TOKEN_RE.fullmatch(value):
        raise ValueError(f"{context}.{key} must be an uppercase class id")
    return value


def _required_class_token(mapping: Mapping[str, object], key: str, context: str) -> str:
    value = _required_str(mapping, key, context)
    if not _CLASS_TOKEN_RE.fullmatch(value):
        raise ValueError(f"{context}.{key} must be a class token")
    return value


def _required_bool(mapping: Mapping[str, object], key: str, context: str) -> bool:
    value = _required(mapping, key, context)
    if type(value) is not bool:
        raise ValueError(f"{context}.{key} must be a boolean")
    return value


def _required_non_negative_int(mapping: Mapping[str, object], key: str, context: str) -> int:
    value = _required(mapping, key, context)
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


def _required_class_tuple(mapping: Mapping[str, object], key: str, context: str) -> tuple[str, ...]:
    strings = _required_str_tuple(mapping, key, context)
    if len(set(strings)) != len(strings):
        raise ValueError(f"{context}.{key} must not contain duplicates")
    for index, item in enumerate(strings):
        if not _CLASS_TOKEN_RE.fullmatch(item):
            raise ValueError(f"{context}.{key}[{index}] must be a class token")
    return strings


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
            if normalized_key in _FORBIDDEN_RAW_FIELD_EXACT_MARKERS or any(
                marker in normalized_key for marker in _FORBIDDEN_RAW_FIELD_SUBSTRINGS
            ):
                raise ValueError(f"{context}.{key} is a forbidden raw auth/env/path/provider-output field")
            _reject_raw_fields(item, f"{context}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, str):
        for index, item in enumerate(value):
            _reject_raw_fields(item, f"{context}[{index}]")
    elif isinstance(value, str):
        _reject_raw_string(value, context)


def _reject_raw_string(value: str, context: str) -> None:
    if any(marker in value for marker in _FORBIDDEN_RAW_STRING_MARKERS):
        raise ValueError(f"{context} contains forbidden raw auth/env/path/provider-output content")
    if re.search(r"\bsk-[A-Za-z0-9_-]{8,}", value):
        raise ValueError(f"{context} contains forbidden raw auth/env/path/provider-output content")


__all__ = [
    "BehaviorContract",
    "DefaultPytestPolicy",
    "EXPECTED_BEHAVIOR_RESULTS",
    "LAUNCH_POLICY",
    "MatrixRow",
    "MetricBounds",
    "Persona",
    "Phase9BehaviorMatrix",
    "REQUIRED_SIDECARS",
    "ROW_ROLES",
    "RUNTIMES",
    "SCHEMA_ID",
    "SidecarProfile",
    "WRITE_POLICY_MODES",
    "WritePolicy",
    "default_phase9_behavior_matrix_path",
    "load_phase9_behavior_matrix",
    "runtime_row_id_prefix",
    "validate_phase9_behavior_matrix",
]
