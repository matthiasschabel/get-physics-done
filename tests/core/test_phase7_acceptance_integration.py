"""Phase 7 acceptance integration stays tied to product gates, not a harness."""

from __future__ import annotations

import json
import re
from pathlib import Path

from gpd.adapters.runtime_catalog import iter_runtime_descriptors
from tests.helpers.phase4_persona.behavior_metrics import BEHAVIOR_METRIC_COUNT_KEYS
from tests.helpers.phase4_persona.matrix import load_phase4_rows

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE7_FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "phase7_live_persona_matrix.json"

_PHASE7_TRACKED_LOC_CAP = 2_000
_PHASE7_BEHAVIOR_EXPANSION_MAX = 12
_PHASE7_ROW_ID_RE = re.compile(r"^(?:LP[0-9]{2}|LP-JIT-[0-9]{2})(?:-[A-Z0-9]+)*$")
_PHASE7_CLASS_TOKEN_RE = re.compile(r"^[a-z][a-z0-9_]*$")

_PHASE7_REQUIRED_BASE_ROW_IDS = (
    "LP01-START-PROJECTLESS-READONLY",
    "LP02-RESUME-CONTEXT-LOSS",
    "LP03-STALE-VERIFY-ARTIFACT",
    "LP04-STOP-MID-EXECUTION",
    "LP05-NEW-PROJECT-MINIMAL-VAGUE",
    "LP06-MAP-RESEARCH-EXISTING",
    "LP07-WRITE-PAPER-GAPS",
    "LP08-CHILD-CHECKPOINT-RETURN",
    "LP09-WORKSPACE-WRITE-BOUNDARY",
    "LP10-RUNTIME-PERMISSION-BLOCK",
    "LP11-SET-PROFILE-REVIEW-CANARY",
    "LP12-GEMINI-POLICY-DENIAL",
)
_PHASE7_REQUIRED_BEHAVIOR_ROW_IDS = tuple(f"LP-JIT-{index:02d}" for index in range(1, 9))
_PHASE7_REQUIRED_BEHAVIOR_FIELDS = frozenset(
    {
        "persona_class",
        "prompt_variant_class",
        "workflow_class",
        "expected_smoothness_class",
        "expected_schema_wrestling_class",
        "expected_stop_integrity_class",
        "expected_physics_to_schema_ratio_class",
        "expected_next_up_specificity_class",
        "expected_mutation_guard_class",
        "expected_first_useful_action_class",
        "expected_artifact_handle_first_class",
        "behavior_metric_bounds",
        "phase4_behavior_ref",
    }
)
_PHASE7_BEHAVIOR_CLASS_FIELDS = frozenset(
    field for field in _PHASE7_REQUIRED_BEHAVIOR_FIELDS if field.endswith("_class")
) | {"persona_class", "prompt_variant_class", "workflow_class"}
_PHASE7_PLANNED_BEHAVIOR_COUNT_KEYS = frozenset(
    (
        *BEHAVIOR_METRIC_COUNT_KEYS,
        "physics_progress_count",
        "schema_surface_count",
        "conversation_turn_count",
        "raw_reload_leakage_count",
        "content_hydration_before_selection_count",
    )
)

_PHASE7_FORBIDDEN_RAW_ARTIFACT_NAMES = frozenset(
    {
        "argv.json",
        "command.json",
        "command.txt",
        "env.json",
        "prompt.enveloped.txt",
        "prompt.txt",
        "provider-output.txt",
        "provider-reply.txt",
        "provider_output.txt",
        "provider_reply.txt",
        "raw-transcript.md",
        "raw_transcript.md",
        "stderr.txt",
        "stdout.jsonl",
        "stdout.txt",
        "transcript.md",
    }
)

_PHASE7_SURFACE_GLOBS = (
    "tests/core/test_phase7*.py",
    "tests/fixtures/**/*phase7*",
    "tests/helpers/**/*phase7*",
    "tests/helpers/**/persona_matrix/*.py",
    "src/**/*phase7*",
    "scripts/**/*phase7*",
    "docs/**/*phase7*",
)
_PHASE7_SURFACE_TEXT_SUFFIXES = frozenset({".json", ".md", ".py", ".yaml", ".yml"})


_LIFECYCLE_ROW_SEMANTIC_TEST_OWNER_OPTIONS = {
    "LP03-STALE-VERIFY-ARTIFACT": frozenset(
        {
            "tests/core/test_handoff_artifacts.py",
            "tests/core/test_child_handoff.py",
            "tests/core/test_phase4_persona_lifecycle_matrix.py",
        }
    ),
    "LP08-CHILD-CHECKPOINT-RETURN": frozenset(
        {
            "tests/core/test_phase_lifecycle_live_contract.py",
            "tests/core/test_child_handoff.py",
            "tests/core/test_phase4_persona_lifecycle_matrix.py",
        }
    ),
}


def _phase7_fixture_rows() -> tuple[dict[str, object], ...]:
    payload = json.loads(PHASE7_FIXTURE_PATH.read_text(encoding="utf-8"))
    rows = payload["rows"]
    assert isinstance(rows, list)
    assert all(isinstance(row, dict) for row in rows)
    return tuple(rows)


def _phase7_surface_files() -> tuple[Path, ...]:
    files: set[Path] = set()
    for pattern in _PHASE7_SURFACE_GLOBS:
        files.update(
            path for path in REPO_ROOT.glob(pattern) if path.is_file() and path.suffix in _PHASE7_SURFACE_TEXT_SUFFIXES
        )
    return tuple(sorted(files))


def _phase7_row_key(row_id: str) -> str:
    if row_id.startswith("LP-JIT-"):
        return "-".join(row_id.split("-", 3)[:3])
    return row_id.split("-", 1)[0]


def _physical_line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _explicit_denylist_line_numbers(path: Path) -> set[int]:
    allowed_lines: set[int] = set()
    inside_denylist = False
    inside_raw_parametrize = False
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if re.match(r"^_?[A-Z0-9_]*(?:FORBIDDEN|DENYLIST|RAW_(?:ARTIFACT|VALUE)|PATTERNS)[A-Z0-9_]*\s*=", stripped):
            inside_denylist = True
        if inside_denylist:
            allowed_lines.add(line_number)
            if stripped in {")", "}", "})"}:
                inside_denylist = False
            continue

        if stripped.startswith("@pytest.mark.parametrize("):
            inside_raw_parametrize = False
        if "raw_" in stripped and "@pytest.mark.parametrize" not in stripped:
            inside_raw_parametrize = True
        if inside_raw_parametrize:
            allowed_lines.add(line_number)
            if stripped == ")":
                inside_raw_parametrize = False
    return allowed_lines


def test_phase7_fixture_rows_name_existing_source_and_test_owners() -> None:
    runtime_names = {descriptor.runtime_name for descriptor in iter_runtime_descriptors()}
    rows = _phase7_fixture_rows()
    row_ids = [str(row["row_id"]) for row in rows]
    base_row_ids = set(_PHASE7_REQUIRED_BASE_ROW_IDS)
    behavior_row_ids = {row_id for row_id in row_ids if row_id.startswith("LP-JIT-")}
    expansion_row_ids = set(row_ids) - base_row_ids

    assert row_ids[: len(_PHASE7_REQUIRED_BASE_ROW_IDS)] == list(_PHASE7_REQUIRED_BASE_ROW_IDS)
    assert set(_PHASE7_REQUIRED_BEHAVIOR_ROW_IDS) <= behavior_row_ids
    assert expansion_row_ids == behavior_row_ids
    assert len(behavior_row_ids) <= _PHASE7_BEHAVIOR_EXPANSION_MAX
    assert len(set(row_ids)) == len(row_ids)
    assert all(_PHASE7_ROW_ID_RE.match(row_id) for row_id in row_ids)
    assert len({_phase7_row_key(row_id) for row_id in row_ids}) == len(row_ids)

    for row in rows:
        source_owners = tuple(str(owner) for owner in row["source_owners"])
        test_owners = tuple(str(owner) for owner in row["test_owners"])
        runtime_scope = tuple(str(runtime) for runtime in row["runtime_scope"])

        assert row["fixture_family"]
        assert source_owners
        assert test_owners
        assert all(runtime == "all_supported" or runtime in runtime_names for runtime in runtime_scope)
        assert row.get("provider_launch_allowed") is False
        assert row.get("network_allowed") is False

        for owner in (*source_owners, *test_owners):
            owner_file = REPO_ROOT / owner
            assert owner_file.exists(), f"{row['row_id']} references missing owner {owner}"


def test_phase7_behavior_canary_rows_are_class_only_and_aligned_to_phase4_scorers() -> None:
    rows_by_id = {str(row["row_id"]): row for row in _phase7_fixture_rows()}
    phase4_rows = {row.row_id: row for row in load_phase4_rows()}

    for row_id in _PHASE7_REQUIRED_BEHAVIOR_ROW_IDS:
        row = rows_by_id[row_id]
        missing_fields = _PHASE7_REQUIRED_BEHAVIOR_FIELDS - set(row)
        assert not missing_fields, f"{row_id} is missing behavior fields: {sorted(missing_fields)}"
        assert str(row["fixture_family"]).endswith("_class")

        for field in _PHASE7_BEHAVIOR_CLASS_FIELDS:
            value = row[field]
            assert isinstance(value, str), f"{row_id}.{field} must be a string class token"
            assert _PHASE7_CLASS_TOKEN_RE.match(value), f"{row_id}.{field} is not class-only"

        assert row["expected_smoothness_class"] != "regressed"
        assert row["expected_schema_wrestling_class"] != "danger"
        assert row["provider_launch_allowed"] is False
        assert row["network_allowed"] is False

        metric_bounds = row["behavior_metric_bounds"]
        assert isinstance(metric_bounds, dict)
        assert metric_bounds
        assert set(metric_bounds) <= _PHASE7_PLANNED_BEHAVIOR_COUNT_KEYS
        assert all(type(bound) is int and bound >= 0 for bound in metric_bounds.values())

        phase4_ref = row["phase4_behavior_ref"]
        assert isinstance(phase4_ref, str)
        assert phase4_ref in phase4_rows
        assert phase4_rows[phase4_ref].scorer_name


def test_phase7_key_lifecycle_rows_have_a_semantic_test_owner() -> None:
    rows_by_id = {str(row["row_id"]): row for row in _phase7_fixture_rows()}

    for row_id, owner_options in _LIFECYCLE_ROW_SEMANTIC_TEST_OWNER_OPTIONS.items():
        assert row_id in rows_by_id
        test_owners = {str(owner) for owner in rows_by_id[row_id]["test_owners"]}
        assert test_owners & owner_options, f"{row_id} must name at least one semantic test owner"


def test_phase7_acceptance_surface_stays_under_loc_cap() -> None:
    phase7_files = _phase7_surface_files()
    phase7_loc = sum(_physical_line_count(path) for path in phase7_files)

    assert phase7_files
    assert phase7_loc <= _PHASE7_TRACKED_LOC_CAP


def test_phase7_files_contain_raw_artifact_names_only_in_explicit_denylist() -> None:
    offenders: list[str] = []

    for path in _phase7_surface_files():
        allowed_lines = _explicit_denylist_line_numbers(path)
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if line_number in allowed_lines:
                continue
            for forbidden_name in _PHASE7_FORBIDDEN_RAW_ARTIFACT_NAMES:
                if forbidden_name in line:
                    relpath = path.relative_to(REPO_ROOT)
                    offenders.append(f"{relpath}:{line_number}:{forbidden_name}")

    assert not offenders, offenders
