"""Shared support for context staged-init tests."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

from tests.helpers.cli import artifact_manifest_payload, write_managed_publication_manuscript
from tests.workflow_stage_test_support import assert_staged_payload_matches_manifest

_MISSING = object()

EMPTY_REFERENCE_INTAKE = {
    "must_read_refs": [],
    "must_include_prior_outputs": [],
    "user_asserted_anchors": [],
    "known_good_baselines": [],
    "context_gaps": [],
    "crucial_inputs": [],
}

REFERENCE_HEAVY_FIELDS = (
    "active_reference_context",
    "protocol_bundle_context",
    "reference_artifacts_content",
)


def fail_if_context_builder_runs(name: str):
    def fail(*args: object, **kwargs: object) -> dict[str, object]:
        pytest.fail(f"{name} should not run for this staged init")

    return fail


def record_reference_artifact_payload_calls(calls: list[bool]):
    def record(
        _cwd: Path,
        *,
        include_content: bool = True,
    ) -> dict[str, object]:
        calls.append(include_content)
        return {
            "literature_review_files": [],
            "literature_review_count": 0,
            "research_map_reference_files": ["GPD/research-map/REFERENCES.md"],
            "research_map_reference_count": 1,
            "knowledge_doc_files": [],
            "knowledge_doc_count": 0,
            "stable_knowledge_doc_files": [],
            "stable_knowledge_doc_count": 0,
            "knowledge_doc_status_counts": {},
            "reference_artifact_files": ["GPD/research-map/REFERENCES.md"],
            "reference_artifacts_content": "hydrated reference artifacts" if include_content else None,
        }

    return record


def assert_context_stage(
    payload: Mapping[str, object],
    manifest: object,
    workflow_id: str,
    stage_id: str,
) -> None:
    assert_staged_payload_matches_manifest(
        payload,
        manifest,
        workflow_id=workflow_id,
        stage_id=stage_id,
    )


def assert_no_state_lock_after(project_root: Path, action: Callable[[], object]) -> object:
    result = action()
    assert not (project_root / "GPD" / "state.json.lock").exists()
    return result


def assert_stage_omits_heavy_reference_context(
    payload: Mapping[str, object],
    *,
    extra_fields: tuple[str, ...] = (),
) -> None:
    for field in (*REFERENCE_HEAVY_FIELDS, *extra_fields):
        assert field not in payload


def assert_stage_uses_reference_handles_only(
    payload: Mapping[str, object],
    *,
    reference_files: list[str] | None = None,
) -> None:
    if reference_files is not None:
        assert payload["reference_artifact_files"] == reference_files
    assert_stage_omits_heavy_reference_context(
        payload,
        extra_fields=("active_reference_context", "protocol_bundle_context"),
    )


def assert_empty_reference_intake(payload: Mapping[str, object]) -> None:
    assert payload.get("contract_intake") is None
    assert payload["effective_reference_intake"] == EMPTY_REFERENCE_INTAKE


def assert_publication_subject_roots(
    payload: Mapping[str, object],
    *,
    slug: str | None = None,
    managed_root: str | None = None,
    expected: Mapping[str, object] | None = None,
    optional_expected: Mapping[str, object] | None = None,
) -> str:
    if slug is None:
        assert payload["publication_subject_slug"]
        slug = str(payload["publication_subject_slug"])
    else:
        assert payload["publication_subject_slug"] == slug

    if managed_root is None:
        managed_root = f"GPD/publication/{slug}"
    assert payload["managed_publication_root"] == managed_root

    for key, value in (expected or {}).items():
        assert payload[key] == value
    for key, value in (optional_expected or {}).items():
        if key in payload:
            assert payload[key] == value
    return managed_root


def assert_project_manuscript_publication_roots(
    payload: Mapping[str, object],
    *,
    bootstrap_root: str = "paper",
    artifact_base: object = _MISSING,
    manuscript_root: object = _MISSING,
    manuscript_entrypoint: object = _MISSING,
    artifact_manifest_path: object = _MISSING,
) -> str:
    slug = str(payload["publication_subject_slug"])
    managed_root = f"GPD/publication/{slug}"
    expected: dict[str, object] = {
        "publication_subject_status": "resolved",
        "publication_bootstrap_mode": "resume_existing_manuscript",
        "publication_bootstrap_root": bootstrap_root,
        "publication_lane_kind": "canonical_project_manuscript",
        "publication_lane_owner": "project_managed",
        "selected_publication_root": "GPD",
        "publication_intake_root": f"{managed_root}/intake",
        "managed_manuscript_root": f"{managed_root}/manuscript",
    }
    optional_values = {
        "publication_artifact_base": artifact_base,
        "manuscript_root": manuscript_root,
        "manuscript_entrypoint": manuscript_entrypoint,
        "artifact_manifest_path": artifact_manifest_path,
    }
    expected.update({key: value for key, value in optional_values.items() if value is not _MISSING})
    return assert_publication_subject_roots(payload, managed_root=managed_root, expected=expected)


def assert_managed_publication_roots(
    payload: Mapping[str, object],
    *,
    slug: str,
    status: str = "resolved",
    owner: str = "project_managed",
    staged_payload: bool = False,
    source: object = _MISSING,
    bootstrap_mode: object = _MISSING,
    bootstrap_root: object = _MISSING,
    artifact_base: object = _MISSING,
    manuscript_root: object = _MISSING,
    manuscript_entrypoint: object = _MISSING,
    selected_review_root: object = _MISSING,
) -> str:
    managed_root = f"GPD/publication/{slug}"
    expected: dict[str, object] = {
        "publication_lane_kind": "managed_publication_manuscript",
        "publication_lane_owner": owner,
        "selected_publication_root": managed_root,
    }
    if not staged_payload:
        expected["publication_subject_status"] = status
        expected["managed_manuscript_root"] = f"{managed_root}/manuscript"
        expected["publication_intake_root"] = f"{managed_root}/intake"
    optional_values = {
        "publication_subject_source": source,
        "publication_bootstrap_mode": bootstrap_mode,
        "publication_bootstrap_root": bootstrap_root,
        "publication_artifact_base": artifact_base,
        "manuscript_root": manuscript_root,
        "manuscript_entrypoint": manuscript_entrypoint,
        "selected_review_root": selected_review_root,
    }
    expected.update({key: value for key, value in optional_values.items() if value is not _MISSING})
    return assert_publication_subject_roots(payload, slug=slug, managed_root=managed_root, expected=expected)


def assert_external_artifact_publication_roots(
    payload: Mapping[str, object],
    *,
    managed_manuscript_root: object = _MISSING,
) -> str:
    slug = str(payload["publication_subject_slug"])
    managed_root = f"GPD/publication/{slug}"
    optional_expected = {"managed_manuscript_root": managed_manuscript_root}
    return assert_publication_subject_roots(
        payload,
        managed_root=managed_root,
        expected={
            "publication_lane_kind": "external_artifact",
            "publication_lane_owner": "external_artifact",
            "selected_publication_root": managed_root,
            "selected_review_root": f"{managed_root}/review",
        },
        optional_expected={key: value for key, value in optional_expected.items() if value is not _MISSING},
    )


def write_project_paper_manuscript(
    project_root: Path,
    *,
    paper_dir: str = "paper",
    stem: str = "main",
    body: str = "Draft manuscript.",
    title: str = "Curvature Flow Bounds",
) -> Path:
    manuscript_dir = project_root / paper_dir
    manuscript_dir.mkdir(parents=True, exist_ok=True)
    manuscript = manuscript_dir / f"{stem}.tex"
    manuscript.write_text(
        f"\\documentclass{{article}}\\begin{{document}}{body}\\end{{document}}\n",
        encoding="utf-8",
    )
    (manuscript_dir / "ARTIFACT-MANIFEST.json").write_text(
        json.dumps(
            artifact_manifest_payload(
                manuscript,
                title=title,
                journal="jhep",
                artifact_id="main-tex",
                produced_by="test",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return manuscript


def write_managed_context_manuscript(
    project_root: Path,
    *,
    subject_slug: str,
    stem: str = "main",
    body: str = "Draft manuscript.",
) -> Path:
    return write_managed_publication_manuscript(
        project_root,
        subject_slug=subject_slug,
        stem=stem,
        body=body,
        produced_by="tests.core.test_context",
    )
