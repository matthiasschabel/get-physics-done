"""Semantic checks for the stage-stop Next Up contract."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE_STOP_PATH = REPO_ROOT / "src/gpd/specs/references/orchestration/stage-stop-envelope.md"

PRIMARY_COMMAND_RE = re.compile(r"(?m)^Primary: `(?P<command>gpd:[^`]+)`$")


def _fenced_blocks(text: str, language: str) -> list[str]:
    pattern = re.compile(rf"```{language}\n(?P<body>.*?)\n```", re.DOTALL)
    return [match.group("body") for match in pattern.finditer(text)]


def test_stage_stop_envelope_reference_defines_contract() -> None:
    assert STAGE_STOP_PATH.exists()
    text = STAGE_STOP_PATH.read_text(encoding="utf-8")
    lowered = text.lower()

    required_fragments = [
        "stage_stop:",
        "next_runtime_command",
        "exactly one public `gpd:` runtime command",
        "gpd:suggest-next",
        "raw-init boundary",
        "gpd --raw init",
        "gpd --raw stage field-access",
    ]
    missing = [fragment for fragment in required_fragments if fragment.lower() not in lowered]
    assert missing == []


def test_stage_stop_yaml_example_uses_accepted_status_and_public_commands() -> None:
    text = STAGE_STOP_PATH.read_text(encoding="utf-8")
    yaml_blocks = _fenced_blocks(text, "yaml")
    assert yaml_blocks

    payload = yaml.safe_load(yaml_blocks[0])
    assert set(payload) == {"stage_stop"}

    stage_stop = payload["stage_stop"]
    assert stage_stop["status"] in {"checkpoint", "blocked", "completed", "failed"}
    assert stage_stop["next_runtime_command"].startswith("gpd:")
    assert all(command.startswith("gpd:") for command in stage_stop["also_available"])


def test_stage_stop_reference_next_up_blocks_have_one_public_primary() -> None:
    text = STAGE_STOP_PATH.read_text(encoding="utf-8")
    markdown_blocks = [block for block in _fenced_blocks(text, "markdown") if "## > Next Up" in block]
    assert markdown_blocks

    forbidden_fragments = (
        "gpd --raw init",
        "--raw init",
        "gpd --raw stage field-access",
        "--raw stage field-access",
    )
    for block in markdown_blocks:
        primary_commands = PRIMARY_COMMAND_RE.findall(block)
        assert primary_commands == ["gpd:suggest-next"]
        assert all(fragment not in block for fragment in forbidden_fragments)
