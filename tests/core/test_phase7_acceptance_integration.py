"""Phase 7 acceptance integration stays tied to product gates, not a harness."""

from __future__ import annotations

import json
import re
from pathlib import Path

from gpd.adapters.runtime_catalog import iter_runtime_descriptors

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE7_FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "phase7_live_persona_matrix.json"

_PHASE7_TRACKED_LOC_CAP = 2_000

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


_LIFECYCLE_ROW_REQUIRED_TEST_OWNERS = {
    "LP03-STALE-VERIFY-ARTIFACT": {
        "tests/core/test_phase4_persona_lifecycle_matrix.py",
        "tests/core/test_phase_lifecycle_live_contract.py",
    },
    "LP08-CHILD-CHECKPOINT-RETURN": {
        "tests/core/test_phase4_persona_lifecycle_matrix.py",
        "tests/core/test_phase_lifecycle_live_contract.py",
    },
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
        files.update(path for path in REPO_ROOT.glob(pattern) if path.is_file())
    return tuple(sorted(files))


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

    assert len(rows) == 12
    assert len(set(row_ids)) == len(row_ids)
    assert {row_id[:4] for row_id in row_ids} == {f"LP{index:02d}" for index in range(1, 13)}

    for row in rows:
        source_owners = tuple(str(owner) for owner in row["source_owners"])
        test_owners = tuple(str(owner) for owner in row["test_owners"])
        runtime_scope = tuple(str(runtime) for runtime in row["runtime_scope"])

        assert row["fixture_family"]
        assert source_owners
        assert test_owners
        assert all(runtime == "all_supported" or runtime in runtime_names for runtime in runtime_scope)

        for owner in (*source_owners, *test_owners):
            owner_file = REPO_ROOT / owner
            assert owner_file.exists(), f"{row['row_id']} references missing owner {owner}"


def test_phase7_key_lifecycle_rows_are_anchored_to_existing_phase4_gates() -> None:
    rows_by_id = {str(row["row_id"]): row for row in _phase7_fixture_rows()}

    for row_id, required_owners in _LIFECYCLE_ROW_REQUIRED_TEST_OWNERS.items():
        assert row_id in rows_by_id
        test_owners = {str(owner) for owner in rows_by_id[row_id]["test_owners"]}
        assert required_owners <= test_owners


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
