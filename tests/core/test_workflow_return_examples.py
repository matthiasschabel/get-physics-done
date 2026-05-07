"""Focused validation for workflow-visible ``gpd_return`` examples."""

from __future__ import annotations

import re
from pathlib import Path

from gpd.core.return_contract import REQUIRED_RETURN_FIELDS, validate_gpd_return_markdown

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
FENCED_YAML_RE = re.compile(r"```ya?ml\s*\n(?P<body>[\s\S]*?)```", re.IGNORECASE)


def _workflow_gpd_return_blocks(path: Path) -> list[tuple[int, str]]:
    text = path.read_text(encoding="utf-8")
    blocks: list[tuple[int, str]] = []
    for match in FENCED_YAML_RE.finditer(text):
        body = match.group("body")
        if "gpd_return:" not in body:
            continue
        line_number = text[: match.start()].count("\n") + 1
        blocks.append((line_number, f"```yaml\n{body.rstrip()}\n```"))
    return blocks


def _validated_workflow_return_examples(path: Path, *, expected_count: int) -> list[dict[str, object]]:
    blocks = _workflow_gpd_return_blocks(path)
    assert len(blocks) == expected_count

    envelopes: list[dict[str, object]] = []
    failures: list[str] = []
    for line_number, block in blocks:
        result = validate_gpd_return_markdown(block)
        if not result.passed:
            failures.append(f"{path.name}:{line_number}: {'; '.join(result.errors)}")
            continue
        missing_fields = sorted(set(REQUIRED_RETURN_FIELDS) - set(result.fields))
        if missing_fields:
            failures.append(f"{path.name}:{line_number}: missing required field(s): {', '.join(missing_fields)}")
            continue
        envelopes.append(result.fields)

    assert failures == []
    return envelopes


def test_execute_plan_visible_return_examples_are_complete_valid_envelopes() -> None:
    envelopes = _validated_workflow_return_examples(WORKFLOWS_DIR / "execute-plan.md", expected_count=3)

    assert any("state_updates" in envelope and "contract_updates" in envelope for envelope in envelopes)
    assert any(
        envelope["status"] == "checkpoint" and "decisions" in envelope and "blockers" in envelope
        for envelope in envelopes
    )
    assert any(envelope["status"] == "completed" and "continuation_update" in envelope for envelope in envelopes)


def test_map_research_visible_return_example_is_a_complete_valid_envelope() -> None:
    [envelope] = _validated_workflow_return_examples(WORKFLOWS_DIR / "map-research.md", expected_count=1)

    assert envelope["status"] == "completed"
    assert envelope["files_written"] == ["GPD/research-map/FORMALISM.md", "GPD/research-map/REFERENCES.md"]
    assert envelope["focus"] == "theory"
