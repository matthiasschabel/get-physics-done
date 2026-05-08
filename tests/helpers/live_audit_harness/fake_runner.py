"""Provider-free fake runner for live-audit harness tests."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path

_MISSING = object()
_NO_DEFAULT = object()
_HARNESS_ARTIFACT_NAMES = {
    "evidence-packet.json",
    "final.md",
    "normalized-events.jsonl",
    "status.json",
    "stdout.jsonl",
    "write-classification.json",
}


@dataclass(frozen=True, slots=True)
class FakeRunResult:
    row_id: str
    row_root: Path
    status_path: Path
    final_path: Path
    normalized_events_path: Path
    write_classification_path: Path
    evidence_packet_path: Path


@dataclass(slots=True)
class GuardedWorkspace:
    repo_root: Path
    tmp_root: Path
    row_root: Path
    write_records: list[dict[str, object]] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        raw_tmp_root = self.tmp_root
        raw_row_root = self.row_root

        self.repo_root = self.repo_root.resolve(strict=False)
        self.tmp_root = self.tmp_root.resolve(strict=False)
        self.row_root = self.row_root.resolve(strict=False)

        repo_tmp_root = (self.repo_root / "tmp").resolve(strict=False)
        if not _is_relative_to(self.tmp_root, repo_tmp_root):
            raise ValueError("tmp_root must be under the repo-local tmp directory")
        if not _is_relative_to(self.row_root, self.tmp_root):
            raise ValueError("row_root must be under tmp_root; active checkout writes are refused")
        if self.row_root == self.tmp_root:
            raise ValueError("row_root must be a row-specific child of tmp_root")
        if _path_is_or_contains_symlink(raw_tmp_root, stop_at=self.repo_root):
            raise ValueError("tmp_root must not contain symlink path components")
        if _path_is_or_contains_symlink(raw_row_root, stop_at=self.tmp_root):
            raise ValueError("row_root must not contain symlink path components")

    def resolve_allowed(self, relative_path: str, *, allow_harness_artifact: bool = False) -> Path:
        candidate = Path(relative_path)
        if candidate.is_absolute():
            raise ValueError("absolute paths are refused by the fake runner")
        parts = candidate.parts
        if not parts or parts == (".",):
            raise ValueError("empty relative paths are refused by the fake runner")
        if any(part == ".." for part in parts):
            raise ValueError("path traversal is refused by the fake runner")
        if any(part == "~" or part.startswith("~/") for part in parts):
            raise ValueError("home-directory writes are refused by the fake runner")
        if not allow_harness_artifact and _is_reserved_harness_artifact_path(candidate):
            raise ValueError("reserved harness sidecar writes are refused by the fake runner")

        target = self.row_root.joinpath(*parts)
        self._refuse_symlink_components(target)
        resolved_target = target.resolve(strict=False)
        if not _is_relative_to(resolved_target, self.row_root):
            raise ValueError("path resolves outside the row root")
        if not _is_relative_to(resolved_target, self.tmp_root):
            raise ValueError("path resolves outside the repo-local tmp root")
        if _is_relative_to(resolved_target, self.repo_root) and not _is_relative_to(resolved_target, self.tmp_root):
            raise ValueError("active checkout writes are refused")
        return target

    def write_text(self, relative_path: str, text: str, *, allow_harness_artifact: bool = False) -> Path:
        target = self.resolve_allowed(relative_path, allow_harness_artifact=allow_harness_artifact)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

        resolved_target = target.resolve(strict=True)
        if not _is_relative_to(resolved_target, self.row_root):
            raise ValueError("written path escaped the row root")
        if not _is_relative_to(resolved_target, self.tmp_root):
            raise ValueError("written path escaped the repo-local tmp root")

        self.write_records.append(
            {
                "relative_path": relative_path,
                "resolved_path": str(resolved_target),
                "classification": _classify_materialized_write(relative_path),
                "materialized": True,
                "under_tmp_root": True,
                "under_row_root": True,
            }
        )
        return target

    def _refuse_symlink_components(self, target: Path) -> None:
        relative_parts = target.relative_to(self.row_root).parts
        current = self.row_root
        for part in relative_parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("symlink path components are refused by the fake runner")
            if not current.exists():
                break


def run_fake_scenario(row: object, repo_root: Path, output_root: Path) -> FakeRunResult:
    row_id = _row_id(row)
    repo_root = repo_root.resolve(strict=False)
    output_root = output_root.resolve(strict=False)
    repo_tmp_root = (repo_root / "tmp").resolve(strict=False)
    if not _is_relative_to(output_root, repo_tmp_root):
        raise ValueError("output_root must be under the repo-local tmp directory")

    row_root = output_root / row_id
    row_root.mkdir(parents=True, exist_ok=True)
    workspace = GuardedWorkspace(repo_root=repo_root, tmp_root=repo_tmp_root, row_root=row_root)

    final_text = _final_text(row, row_id)
    stdout_events = _stdout_events(row, final_text)
    normalized_events = _normalized_events(row, final_text)

    stdout_path = workspace.write_text("stdout.jsonl", _jsonl(stdout_events), allow_harness_artifact=True)
    normalized_events_path = workspace.write_text(
        "normalized-events.jsonl", _jsonl(normalized_events), allow_harness_artifact=True
    )
    final_path = workspace.write_text("final.md", final_text, allow_harness_artifact=True)

    for relative_path, text in _materialized_writes(row):
        workspace.write_text(relative_path, text)

    refused_writes = _refused_write_attempts(row, workspace)
    status_payload = {
        "schema_version": "phase7.fake-runner-status.v1",
        "row_id": row_id,
        "status": str(_row_attr(row, "status", "passed")),
        "fake_provider": True,
        "provider_launched": False,
        "subprocess_invoked": False,
        "artifacts": {
            "stdout": stdout_path.name,
            "normalized_events": normalized_events_path.name,
            "final": final_path.name,
            "write_classification": "write-classification.json",
            "evidence_packet": "evidence-packet.json",
        },
    }
    status_path = workspace.write_text("status.json", _json(status_payload), allow_harness_artifact=True)

    classification_payload = _write_classification(row_id, workspace.write_records, refused_writes)
    write_classification_path = workspace.write_text(
        "write-classification.json", _json(classification_payload), allow_harness_artifact=True
    )

    evidence_payload = _evidence_packet(
        row_id=row_id,
        row_root=row_root,
        status_path=status_path,
        stdout_path=stdout_path,
        normalized_events_path=normalized_events_path,
        final_path=final_path,
        write_classification_path=write_classification_path,
        evidence_packet_path=row_root / "evidence-packet.json",
    )
    evidence_payload = _merge_evidence_overrides(evidence_payload, _evidence_overrides(row))
    evidence_packet_path = workspace.write_text(
        "evidence-packet.json", _json(evidence_payload), allow_harness_artifact=True
    )

    return FakeRunResult(
        row_id=row_id,
        row_root=row_root,
        status_path=status_path,
        final_path=final_path,
        normalized_events_path=normalized_events_path,
        write_classification_path=write_classification_path,
        evidence_packet_path=evidence_packet_path,
    )


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _path_is_or_contains_symlink(path: Path, *, stop_at: Path) -> bool:
    stop_at = stop_at.resolve(strict=False)
    path = path if path.is_absolute() else stop_at / path
    try:
        relative_parts = path.relative_to(stop_at).parts
    except ValueError:
        return path.is_symlink()

    current = stop_at
    for part in relative_parts:
        current = current / part
        if current.is_symlink():
            return True
        if not current.exists():
            break
    return False


def _is_reserved_harness_artifact_path(path: Path) -> bool:
    return len(path.parts) == 1 and path.parts[0] in _HARNESS_ARTIFACT_NAMES


def _row_attr(row: object, name: str, default: object = _NO_DEFAULT) -> object:
    if isinstance(row, Mapping) and name in row:
        return row[name]
    if hasattr(row, name):
        return getattr(row, name)
    if default is _NO_DEFAULT:
        raise AttributeError(name)
    return default


def _row_id(row: object) -> str:
    row_id = _row_attr(row, "row_id")
    if not isinstance(row_id, str) or not row_id:
        raise ValueError("row_id must be a non-empty string")
    row_id_path = Path(row_id)
    if row_id_path.is_absolute() or row_id_path.parts != (row_id,) or row_id in {".", ".."}:
        raise ValueError("row_id must be a single safe path segment")
    return row_id


def _final_text(row: object, row_id: str) -> str:
    value = _row_attr(row, "final_text", _MISSING)
    if value is _MISSING:
        value = _row_attr(row, "final_message", _MISSING)
    if isinstance(value, Mapping):
        value = value.get("text", _MISSING)
    if value is _MISSING or value is None:
        text = f"Fake runner completed {row_id}.\n"
    else:
        text = str(value)
    return text if text.endswith("\n") else f"{text}\n"


def _stdout_events(row: object, final_text: str) -> list[object]:
    default = [{"type": "message", "role": "assistant", "content": final_text.strip()}]
    value = _row_attr(row, "stdout_events", _MISSING)
    if value is _MISSING:
        value = _row_attr(row, "transcript", _MISSING)
    return _coerce_events(value, default)


def _normalized_events(row: object, final_text: str) -> list[object]:
    default = [{"type": "assistant_final", "source": "fake_runner", "text": final_text.strip()}]
    value = _row_attr(row, "normalized_events", _MISSING)
    return _coerce_events(value, default)


def _coerce_events(value: object, default: list[object]) -> list[object]:
    if value is _MISSING or value is None:
        return default
    if isinstance(value, Mapping):
        return [_json_ready(value)]
    if isinstance(value, str) or not isinstance(value, Sequence):
        return [_json_ready(value)]

    events: list[object] = []
    for entry in value:
        if isinstance(entry, Mapping) and entry.get("stream") in {"stdout", "stdout_jsonl", "stdout_json"}:
            events.append(_json_ready(entry.get("payload", {})))
        else:
            events.append(_json_ready(entry))
    return events


def _materialized_writes(row: object) -> list[tuple[str, str]]:
    writes: list[tuple[str, str]] = []
    for attr_name in ("fake_writes", "artifact_writes", "writes"):
        value = _row_attr(row, attr_name, _MISSING)
        if value is _MISSING or value is None:
            continue
        writes.extend(_coerce_write_items(value))
    return writes


def _coerce_write_items(value: object) -> list[tuple[str, str]]:
    if isinstance(value, Mapping):
        values: Sequence[object] = (value,)
    elif isinstance(value, Sequence) and not isinstance(value, str):
        values = value
    else:
        raise TypeError("write declarations must be mappings or sequences")

    writes: list[tuple[str, str]] = []
    for item in values:
        if isinstance(item, Mapping):
            path = item.get("relative_path", item.get("path"))
            text = item.get("text", item.get("content", ""))
        elif isinstance(item, Sequence) and not isinstance(item, str) and len(item) == 2:
            path = item[0]
            text = item[1]
        else:
            raise TypeError("write declarations must include a path and text")
        if not isinstance(path, str) or not path:
            raise ValueError("write path must be a non-empty relative string")
        writes.append((path, str(text)))
    return writes


def _refused_write_attempts(row: object, workspace: GuardedWorkspace) -> list[dict[str, object]]:
    value = _row_attr(row, "attempted_writes", _MISSING)
    if value is _MISSING or value is None:
        return []

    attempts = _coerce_write_items(value)
    refused: list[dict[str, object]] = []
    for relative_path, _text in attempts:
        try:
            workspace.resolve_allowed(relative_path)
        except ValueError as exc:
            refused.append(
                {
                    "relative_path": relative_path,
                    "classification": _classify_refusal(str(exc)),
                    "materialized": False,
                    "refused": True,
                    "reason": str(exc),
                }
            )
        else:
            raise ValueError(f"attempted write was not refused: {relative_path}")
    return refused


def _classify_materialized_write(relative_path: str) -> str:
    if relative_path in _HARNESS_ARTIFACT_NAMES:
        return "harness_log"
    if relative_path.startswith(("workspace/", "artifacts/")):
        return "expected_product_artifact"
    return "harness_temp"


def _classify_refusal(reason: str) -> str:
    if "reserved harness sidecar" in reason:
        return "reserved_harness_sidecar_refused"
    if "symlink" in reason:
        return "symlink_escape"
    if "absolute" in reason:
        return "absolute_escape_refused"
    if "traversal" in reason:
        return "path_traversal_refused"
    if "home" in reason:
        return "real_home_escape_refused"
    if "active checkout" in reason:
        return "source_checkout_escape_refused"
    return "manifest_error"


def _write_classification(
    row_id: str,
    materialized_writes: list[dict[str, object]],
    refused_writes: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": "phase7.fake-runner-write-classification.v1",
        "row_id": row_id,
        "provider_launched": False,
        "subprocess_invoked": False,
        "summary": {
            "materialized": len(materialized_writes),
            "refused": len(refused_writes),
            "forbidden_materialized": 0,
            "all_materialized_under_tmp": all(write.get("under_tmp_root") is True for write in materialized_writes),
            "all_materialized_under_row_root": all(
                write.get("under_row_root") is True for write in materialized_writes
            ),
        },
        "writes": materialized_writes,
        "refused_writes": refused_writes,
    }


def _evidence_packet(
    *,
    row_id: str,
    row_root: Path,
    status_path: Path,
    stdout_path: Path,
    normalized_events_path: Path,
    final_path: Path,
    write_classification_path: Path,
    evidence_packet_path: Path,
) -> dict[str, object]:
    artifacts = {
        "status": status_path,
        "stdout": stdout_path,
        "normalized_events": normalized_events_path,
        "final": final_path,
        "write_classification": write_classification_path,
        "evidence_packet": evidence_packet_path,
    }
    return {
        "schema_version": "phase7.fake-runner-evidence-packet.v1",
        "row_id": row_id,
        "row_root": str(row_root),
        "provider_launched": False,
        "subprocess_invoked": False,
        "artifacts": {
            name: {"path": str(path), "exists": True if name == "evidence_packet" else path.is_file()}
            for name, path in artifacts.items()
        },
        "raw_provider_output_recorded": False,
        "provider_cli_argv_recorded": False,
    }


def _evidence_overrides(row: object) -> Mapping[str, object]:
    value = _row_attr(row, "evidence_packet_overrides", _MISSING)
    if value is _MISSING:
        value = _row_attr(row, "evidence_packet", _MISSING)
    if value is _MISSING or value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError("evidence packet overrides must be a mapping")
    return value


def _merge_evidence_overrides(
    base: Mapping[str, object],
    overrides: Mapping[str, object],
) -> dict[str, object]:
    merged = dict(base)
    for key, value in overrides.items():
        existing = merged.get(str(key))
        if isinstance(existing, Mapping) and isinstance(value, Mapping):
            merged[str(key)] = _merge_evidence_overrides(existing, value)
        else:
            merged[str(key)] = _json_ready(value)
    return merged


def _json(payload: Mapping[str, object]) -> str:
    return json.dumps(_json_ready(payload), indent=2, sort_keys=True) + "\n"


def _jsonl(events: Sequence[object]) -> str:
    return "".join(json.dumps(_json_ready(event), sort_keys=True) + "\n" for event in events)


def _json_ready(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return _json_ready(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str):
        return [_json_ready(item) for item in value]
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return str(value)


__all__ = ["FakeRunResult", "GuardedWorkspace", "run_fake_scenario"]
