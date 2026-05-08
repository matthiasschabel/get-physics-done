"""Phase 9 sidecar bundle validation tests."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.helpers.live_audit_harness.fake_runner import run_fake_scenario
from tests.helpers.live_audit_harness.sidecar_schema import (
    REQUIRED_SIDECARS,
    SIDECAR_BUNDLE_SCHEMA,
    SidecarSchemaError,
    collect_sidecar_schema_failures,
    validate_sidecar_bundle,
)


def _repo_roots(tmp_path: Path) -> tuple[Path, Path]:
    repo_root = tmp_path / "repo"
    repo_tmp = repo_root / "tmp"
    repo_tmp.mkdir(parents=True)
    return repo_root, repo_tmp


def _row(**overrides: object) -> SimpleNamespace:
    payload: dict[str, object] = {
        "row_id": "P9-SIDECAR-GREEN-001",
        "launch_policy": "fake",
        "default_pytest": True,
        "provider_subprocess_allowed": False,
        "network_allowed": False,
        "required_pytest_markers": (),
        "required_artifacts": REQUIRED_SIDECARS,
        "final_text": "Class-only fake row completed. No provider was launched.",
        "normalized_events": (
            {"type": "turn_started", "metadata": {"turn_class": "setup"}},
            {"type": "assistant_final", "source": "fake_fixture", "text": "Class-only fake row completed."},
        ),
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def _run_row(tmp_path: Path, **overrides: object):
    repo_root, repo_tmp = _repo_roots(tmp_path)
    row = _row(**overrides)
    result = run_fake_scenario(row, repo_root=repo_root, output_root=repo_tmp / "phase9")
    return row, result


def _rewrite_json(path: Path, update: dict[str, object]) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    payload.update(update)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_validate_sidecar_bundle_accepts_fake_runner_green_row(tmp_path: Path) -> None:
    row, result = _run_row(tmp_path)

    bundle = validate_sidecar_bundle(result.row_root, row)

    assert bundle.schema == SIDECAR_BUNDLE_SCHEMA
    assert bundle.row_id == row.row_id
    assert bundle.provider_free is True
    assert bundle.schema_failures == ()
    assert set(bundle.required_artifacts) == set(REQUIRED_SIDECARS)
    assert bundle.sidecar_statuses == dict.fromkeys(REQUIRED_SIDECARS, "present")
    assert bundle.status["provider_launched"] is False
    assert bundle.write_classification["subprocess_invoked"] is False
    assert bundle.evidence_packet["raw_provider_output_recorded"] is False


def test_validate_sidecar_bundle_rejects_missing_required_sidecar(tmp_path: Path) -> None:
    row, result = _run_row(tmp_path)
    result.normalized_events_path.unlink()

    with pytest.raises(SidecarSchemaError, match="missing_required_sidecar") as exc_info:
        validate_sidecar_bundle(result.row_root, row)

    failures = exc_info.value.failures
    assert any(
        failure.sidecar == "normalized-events.jsonl" and failure.failure_class == "missing_required_sidecar"
        for failure in failures
    )


def test_validate_sidecar_bundle_rejects_row_id_mismatch(tmp_path: Path) -> None:
    row, result = _run_row(tmp_path)
    _rewrite_json(result.status_path, {"row_id": "P9-OTHER-ROW"})

    with pytest.raises(SidecarSchemaError, match="row_id_mismatch"):
        validate_sidecar_bundle(result.row_root, row)


def test_validate_sidecar_bundle_rejects_malformed_jsonl_record(tmp_path: Path) -> None:
    row, result = _run_row(tmp_path)
    result.normalized_events_path.write_text('{"type": "assistant_final"}\nnot-json\n', encoding="utf-8")

    with pytest.raises(SidecarSchemaError, match="malformed_jsonl"):
        validate_sidecar_bundle(result.row_root, row)


@pytest.mark.parametrize("field_name", ["provider_output", "raw_transcript", "argv", "env", "auth_path", "home_path"])
def test_validate_sidecar_bundle_rejects_raw_provider_auth_or_env_fields(
    tmp_path: Path,
    field_name: str,
) -> None:
    row, result = _run_row(tmp_path)
    _rewrite_json(result.evidence_packet_path, {field_name: "raw material must not be accepted"})

    with pytest.raises(SidecarSchemaError, match="raw_field_forbidden"):
        validate_sidecar_bundle(result.row_root, row)


def test_validate_sidecar_bundle_rejects_provider_free_flag_violation(tmp_path: Path) -> None:
    row, result = _run_row(tmp_path)
    _rewrite_json(result.status_path, {"provider_launched": True})

    with pytest.raises(SidecarSchemaError, match="provider_free_violation"):
        validate_sidecar_bundle(result.row_root, row)


def test_validate_sidecar_bundle_rejects_artifact_path_outside_row_root(tmp_path: Path) -> None:
    row, result = _run_row(tmp_path)
    evidence = json.loads(result.evidence_packet_path.read_text(encoding="utf-8"))
    assert isinstance(evidence, dict)
    evidence["artifacts"]["final"]["path"] = str(result.row_root.parent / "final.md")
    result.evidence_packet_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    failures = collect_sidecar_schema_failures(result.row_root, row)

    assert any(failure.failure_class == "row_root_escape" for failure in failures)


def test_fake_runner_refuses_row_declared_reserved_sidecar_write(tmp_path: Path) -> None:
    repo_root, repo_tmp = _repo_roots(tmp_path)
    row = _row(fake_writes=({"path": "final.md", "text": "overwrite\n"},))

    with pytest.raises(ValueError, match="reserved harness sidecar"):
        run_fake_scenario(row, repo_root=repo_root, output_root=repo_tmp / "phase9")

    final_path = repo_tmp / "phase9" / row.row_id / "final.md"
    assert final_path.read_text(encoding="utf-8") != "overwrite\n"
