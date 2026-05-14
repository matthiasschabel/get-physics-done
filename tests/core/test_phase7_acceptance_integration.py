"""Phase 7 acceptance integration stays tied to product gates, not a harness."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

from tests.helpers.phase4_persona.matrix import load_phase4_rows
from tests.helpers.phase7_live_like import (
    REQUIRED_JIT_ROW_IDS,
    assert_phase7_matrix_payload_valid,
    load_phase7_live_like_rows,
    load_phase7_live_persona_payload,
    phase7_behavior_row_ids,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

_PHASE7_TRACKED_LOC_CAP = 3_400

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

_PHASE6_INTEGRATION_PLAN_PERSONA_ROWS = dict(
    zip(
        "start_existing_project_progress_no_reconcile schema_averse_planner blocked_or_changed_plan_planner proof_checker_deferral execute_interruption verification_pressure ready_closeout runtime_confused_command runtime_rendered_labels reference_overload resume_missing_handoff_visible write_paper_section_first respond_referee_issue_first".split(),
        "P6-START-JIT-01 P6-PLAN-JIT-01 P6-PLAN-JIT-02 P6-PLAN-JIT-03 P6-EXEC-JIT-03 P6-COMP-JIT-01 P6-COMP-JIT-04 P7-ERG-JIT-02 P7-NEXTUP-JIT-05 P7-ERG-JIT-03 P6-RES-JIT-06 P8-WF-JIT-07 P8-WF-JIT-08".split(),
        strict=True,
    )
)
_PHASE6_WORKFLOW_PERSONA_ROWS = {
    "help": "LP13-HELP-REFERENCE-ONLY",
    "start": "LP14-START-CHOOSER-ROUTE",
    "new_project": "P7-ERG-JIT-01",
    "map_research": "P6-RES-JIT-01",
    "plan_phase": "P6-PLAN-JIT-01",
    "execute_phase": "P6-EXEC-JIT-01",
    "verify_work": "P7-ERG-JIT-02",
    "peer_review": "LP15-PEER-REVIEW-MODE",
    "resume_work": "LP-JIT-02",
    "resume_missing_handoff": "P6-RES-JIT-06",
    "write_paper": "P8-WF-JIT-07",
    "respond_to_referees": "P8-WF-JIT-08",
}
_PHASE6_HARD_ZERO_BOUND_KEYS = frozenset(
    {
        "invalid_command_suggestion_count",
        "schema_repair_loop_count",
        "duplicate_question_bucket_count",
        "question_before_action_count",
        "post_stop_activity_count",
        "unexpected_write_count",
        "unsupported_completion_claim_count",
        "raw_reload_leakage_count",
        "content_hydration_before_selection_count",
    }
)
_PHASE6_EXTRA_HARD_ZERO_BOUND_KEYS = {
    "start_existing_project_progress_no_reconcile": frozenset({"progress_reconcile_write_count"}),
    "resume_missing_handoff_visible": frozenset({"project_lost_claim_count"}),
    "resume_missing_handoff": frozenset({"project_lost_claim_count"}),
    "runtime_rendered_labels": frozenset({"wrong_runtime_prefix_count", "missing_runtime_command_label_count"}),
}


def _phase7_surface_files() -> tuple[Path, ...]:
    files: set[Path] = set()
    for pattern in _PHASE7_SURFACE_GLOBS:
        files.update(
            path for path in REPO_ROOT.glob(pattern) if path.is_file() and path.suffix in _PHASE7_SURFACE_TEXT_SUFFIXES
        )
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


def test_phase7_fixture_schema_source_and_test_owners_are_canonical() -> None:
    payload = load_phase7_live_persona_payload()

    assert_phase7_matrix_payload_valid(payload)
    assert REQUIRED_JIT_ROW_IDS <= phase7_behavior_row_ids(payload)


def test_phase7_key_lifecycle_rows_have_a_semantic_test_owner() -> None:
    rows_by_id = {row.row_id: row for row in load_phase7_live_like_rows()}

    for row_id, owner_options in _LIFECYCLE_ROW_SEMANTIC_TEST_OWNER_OPTIONS.items():
        assert row_id in rows_by_id
        test_owners = set(rows_by_id[row_id].test_owners)
        assert test_owners & owner_options, f"{row_id} must name at least one semantic test owner"


def test_phase6_integration_plan_persona_families_are_mapped_to_matrix_rows() -> None:
    _assert_phase6_persona_rows_cover(_PHASE6_INTEGRATION_PLAN_PERSONA_ROWS)


def test_phase6_workflow_persona_surfaces_are_mapped_to_matrix_rows() -> None:
    _assert_phase6_persona_rows_cover(_PHASE6_WORKFLOW_PERSONA_ROWS)


def _assert_phase6_persona_rows_cover(mapping: Mapping[str, str]) -> None:
    rows_by_id = {row.row_id: row for row in load_phase7_live_like_rows()}
    behavior_row_ids = {row.row_id for row in rows_by_id.values() if row.row_tier == "jit_canary"}
    phase4_rows = {row.row_id for row in load_phase4_rows()}

    assert len(set(mapping.values())) == len(mapping)
    for family, row_id in mapping.items():
        row = rows_by_id[row_id]
        assert row_id in behavior_row_ids, family
        assert row.provider_launch_allowed is False, family
        assert row.network_allowed is False, family
        assert row.raw_artifacts_allowed is False, family

        required_bounds = _PHASE6_HARD_ZERO_BOUND_KEYS | _PHASE6_EXTRA_HARD_ZERO_BOUND_KEYS.get(family, frozenset())
        assert required_bounds <= set(row.behavior_metric_bounds), family
        assert row.phase4_behavior_ref in phase4_rows, family


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
