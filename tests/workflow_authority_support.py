"""Helpers for tests that need staged workflow authority text."""

from __future__ import annotations

import json
from pathlib import Path

from gpd.adapters.install_utils import expand_at_includes

STAGED_WORKFLOW_AUTHORITY_NAMES = {"execute-phase", "peer-review", "write-paper"}


def workflow_authority_text(workflows_dir: Path, name: str) -> str:
    """Return root workflow text plus split stage authorities when present."""

    workflow_name = name.removesuffix(".md")
    root = workflows_dir / f"{workflow_name}.md"
    parts = [root.read_text(encoding="utf-8")]
    stage_dir = workflows_dir / workflow_name
    if workflow_name in STAGED_WORKFLOW_AUTHORITY_NAMES and stage_dir.is_dir():
        stage_paths = _ordered_stage_authority_paths(workflows_dir, workflow_name)
        parts.extend(path.read_text(encoding="utf-8") for path in stage_paths)
    return "\n\n".join(parts)


def _ordered_stage_authority_paths(workflows_dir: Path, workflow_name: str) -> tuple[Path, ...]:
    """Return staged workflow authority files in manifest order."""

    manifest_path = workflows_dir / f"{workflow_name}-stage-manifest.json"
    seen: set[Path] = set()
    ordered: list[Path] = []

    if manifest_path.exists():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        stages = payload.get("stages", [])
        if isinstance(stages, list):
            for stage in stages:
                if not isinstance(stage, dict):
                    continue
                for key in ("mode_paths", "loaded_authorities"):
                    values = stage.get(key, [])
                    if not isinstance(values, list):
                        continue
                    for value in values:
                        if not isinstance(value, str):
                            continue
                        if not value.startswith(f"workflows/{workflow_name}/") or not value.endswith(".md"):
                            continue
                        path = workflows_dir.parent / value
                        if path.exists() and path not in seen:
                            seen.add(path)
                            ordered.append(path)

    if ordered:
        return tuple(ordered)
    return tuple(sorted((workflows_dir / workflow_name).glob("*.md")))


def expanded_workflow_authority_text(
    workflows_dir: Path,
    name: str,
    *,
    src_root: Path,
    path_prefix: str,
    runtime: str | None = None,
) -> str:
    """Expand includes across a workflow's root plus staged authority files."""

    return expand_at_includes(
        workflow_authority_text(workflows_dir, name),
        src_root,
        path_prefix,
        runtime=runtime,
    )
