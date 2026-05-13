"""Reference hydration guardrails for real staged-init payloads."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from gpd.core import context as context_module
from gpd.core.context import (
    init_execute_phase,
    init_literature_review,
    init_peer_review,
    init_respond_to_referees,
    init_verify_work,
    init_write_paper,
)
from gpd.core.state import default_state_dict
from gpd.core.workflow_staging import load_workflow_stage_manifest
from tests import context_stage_test_support as stage_ctx

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "stage0"
REFERENCE_BODY_SENTINEL = "SENTINEL_REFERENCE_BODY_SHOULD_NOT_APPEAR"


def _setup_project(project_root: Path) -> None:
    gpd_dir = project_root / "GPD"
    gpd_dir.mkdir(parents=True, exist_ok=True)
    (gpd_dir / "phases").mkdir(exist_ok=True)
    (gpd_dir / "PROJECT.md").write_text("# Test Project\n\nReference hydration checks.\n", encoding="utf-8")
    (gpd_dir / "ROADMAP.md").write_text("# Roadmap\n\n## Phase 2: Analysis\n", encoding="utf-8")
    (gpd_dir / "REQUIREMENTS.md").write_text("# Requirements\n\n- Preserve reference handles.\n", encoding="utf-8")
    (gpd_dir / "STATE.md").write_text("# State\n\nCurrent phase: 02\n", encoding="utf-8")

    state = default_state_dict()
    state["project_contract"] = json.loads((FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"))
    state["convention_lock"] = {
        "metric_signature": "(-,+,+,+)",
        "fourier_convention": "physics",
        "natural_units": "SI",
    }
    state["intermediate_results"] = [
        {
            "id": "R-01",
            "equation": "E = mc^2",
            "description": "Rest energy",
            "phase": "02",
            "depends_on": [],
            "verified": True,
        }
    ]
    state["approximations"] = [
        {
            "name": "weak coupling",
            "validity_range": "g << 1",
            "controlling_param": "g",
            "current_value": "0.1",
            "status": "valid",
        }
    ]
    (gpd_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")


def _create_phase(project_root: Path) -> None:
    phase_dir = project_root / "GPD" / "phases" / "02-analysis"
    phase_dir.mkdir(parents=True, exist_ok=True)
    (phase_dir / "02-PLAN.md").write_text("objective: compare benchmark observable\n", encoding="utf-8")
    (phase_dir / "02-SUMMARY.md").write_text("# Summary\nExisting result.\n", encoding="utf-8")


def _write_reference_artifacts(project_root: Path) -> set[Path]:
    literature_dir = project_root / "GPD" / "literature"
    literature_dir.mkdir(parents=True, exist_ok=True)
    sentinel_review = literature_dir / "sentinel-REVIEW.md"
    sentinel_review.write_text(
        "# Sentinel Review\n\n"
        "This file should remain handle-only before explicit reference body selection.\n\n"
        f"{REFERENCE_BODY_SENTINEL}\n",
        encoding="utf-8",
    )

    research_map_dir = project_root / "GPD" / "research-map"
    research_map_dir.mkdir(parents=True, exist_ok=True)
    (research_map_dir / "REFERENCES.md").write_text(
        "# Active Reference Registry\n\n"
        "## Benchmarks and Comparison Targets\n\n"
        "- Benchmark reference\n"
        "  - Kind: paper\n"
        "  - Role: benchmark\n"
        "  - Why it matters: Keeps the staged payload non-empty.\n",
        encoding="utf-8",
    )
    return {sentinel_review.resolve(strict=False)}


def _write_response_intake(project_root: Path) -> str:
    reports_dir = project_root / "reviews"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "referee-1.md").write_text("# Referee 1\n\nClarify the benchmark comparison.\n", encoding="utf-8")
    return "reviews/referee-1.md"


def _install_hydration_guards(
    monkeypatch: pytest.MonkeyPatch,
    *,
    forbidden_body_paths: set[Path],
    reference_payload_calls: list[bool],
) -> None:
    original_artifact_payload = context_module._reference_artifact_payload
    original_safe_read_file_truncated = context_module._safe_read_file_truncated

    def record_artifact_payload(
        cwd: Path,
        *,
        include_content: bool = True,
    ) -> dict[str, object]:
        reference_payload_calls.append(include_content)
        return original_artifact_payload(cwd, include_content=include_content)

    def fail_on_reference_body_read(path: Path, *args: object, **kwargs: object) -> str:
        resolved_path = Path(path).resolve(strict=False)
        if resolved_path in forbidden_body_paths:
            pytest.fail(f"reference body should not be read for handle-only staged init: {path}")
        return original_safe_read_file_truncated(path, *args, **kwargs)

    monkeypatch.setattr(context_module, "_reference_artifact_payload", record_artifact_payload)
    monkeypatch.setattr(context_module, "_safe_read_file_truncated", fail_on_reference_body_read)
    monkeypatch.setattr(
        context_module,
        "_render_active_reference_context",
        stage_ctx.fail_if_context_builder_runs("_render_active_reference_context"),
    )
    monkeypatch.setattr(
        context_module,
        "render_protocol_bundle_context",
        stage_ctx.fail_if_context_builder_runs("render_protocol_bundle_context"),
    )


def _assert_handle_only_payload(
    payload: dict[str, object],
    *,
    workflow_id: str,
    stage_id: str,
) -> None:
    manifest = load_workflow_stage_manifest(workflow_id)
    stage_ctx.assert_context_stage(payload, manifest, workflow_id, stage_id)
    assert "reference_artifact_files" in payload
    assert payload["reference_artifact_files"]
    assert "reference_artifacts_content" not in payload
    assert "active_reference_context" not in payload
    assert "protocol_bundle_context" not in payload
    assert REFERENCE_BODY_SENTINEL not in json.dumps(payload, sort_keys=True, default=str)


@pytest.mark.parametrize(
    ("workflow_id", "stage_id", "prepare", "build_payload"),
    (
        (
            "execute-phase",
            "verification_handoff",
            lambda project_root: _create_phase(project_root),
            lambda project_root: init_execute_phase(project_root, "2", stage="verification_handoff"),
        ),
        (
            "peer-review",
            "panel_stages",
            lambda project_root: stage_ctx.write_project_paper_manuscript(project_root),
            lambda project_root: init_peer_review(project_root, stage="panel_stages"),
        ),
        (
            "respond-to-referees",
            "revision_planning",
            lambda project_root: (
                stage_ctx.write_project_paper_manuscript(project_root),
                _write_response_intake(project_root),
            ),
            lambda project_root: init_respond_to_referees(
                project_root,
                subject="reviews/referee-1.md",
                stage="revision_planning",
            ),
        ),
        (
            "verify-work",
            "interactive_validation",
            lambda project_root: _create_phase(project_root),
            lambda project_root: init_verify_work(project_root, "2", stage="interactive_validation"),
        ),
        (
            "write-paper",
            "outline_and_scaffold",
            lambda project_root: None,
            lambda project_root: init_write_paper(project_root, stage="outline_and_scaffold"),
        ),
        (
            "write-paper",
            "figure_and_section_authoring",
            lambda project_root: None,
            lambda project_root: init_write_paper(project_root, stage="figure_and_section_authoring"),
        ),
        (
            "literature-review",
            "scope_locked",
            lambda project_root: None,
            lambda project_root: init_literature_review(
                project_root,
                topic="Curvature flow bounds",
                stage="scope_locked",
            ),
        ),
    ),
)
def test_handle_only_reference_staged_payloads_do_not_hydrate_bodies_or_rendered_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    workflow_id: str,
    stage_id: str,
    prepare: Callable[[Path], object],
    build_payload: Callable[[Path], dict[str, object]],
) -> None:
    _setup_project(tmp_path)
    prepare(tmp_path)
    forbidden_body_paths = _write_reference_artifacts(tmp_path)
    reference_payload_calls: list[bool] = []
    _install_hydration_guards(
        monkeypatch,
        forbidden_body_paths=forbidden_body_paths,
        reference_payload_calls=reference_payload_calls,
    )

    payload = build_payload(tmp_path)

    _assert_handle_only_payload(payload, workflow_id=workflow_id, stage_id=stage_id)
    assert reference_payload_calls == [False]
