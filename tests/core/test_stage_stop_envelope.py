"""Semantic checks for the stage-stop Next Up contract."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE_STOP_PATH = REPO_ROOT / "src/gpd/specs/references/orchestration/stage-stop-envelope.md"
CLOSEOUT_PATH = REPO_ROOT / "src/gpd/specs/workflows/execute-phase/closeout.md"
STAGE_STOP_OWNED_PATHS = (STAGE_STOP_PATH, CLOSEOUT_PATH)

PRIMARY_COMMAND_RE = re.compile(r"(?m)^Primary(?P<label> local transition)?: `(?P<command>[^`]+)`$")
PUBLIC_RUNTIME_COMMAND_RE = re.compile(r"^gpd:[^\s`]+(?:\s+.*)?$")
LOCAL_TRANSITION_COMMAND_RE = re.compile(r"^gpd phase complete\b")


def _fenced_blocks(text: str, language: str) -> list[str]:
    pattern = re.compile(rf"```{language}\n(?P<body>.*?)\n```", re.DOTALL)
    return [match.group("body") for match in pattern.finditer(text)]


def _stage_stop_blocks(path: Path) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    for block in _fenced_blocks(path.read_text(encoding="utf-8"), "yaml"):
        payload = yaml.safe_load(block)
        if isinstance(payload, dict) and isinstance(payload.get("stage_stop"), dict):
            blocks.append(payload["stage_stop"])
    return blocks


def _next_up_blocks(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    blocks: list[str] = []
    for index, line in enumerate(lines):
        if line.strip() != "## > Next Up":
            continue

        in_fenced_block = sum(1 for previous in lines[:index] if previous.strip().startswith("```")) % 2 == 1
        block_lines = [line]
        for following in lines[index + 1 :]:
            stripped = following.strip()
            if in_fenced_block and stripped == "```":
                break
            if not in_fenced_block and stripped.startswith("## "):
                break
            block_lines.append(following)
        blocks.append("\n".join(block_lines))
    return blocks


def _assert_public_runtime_command(command: object) -> None:
    assert isinstance(command, str)
    assert PUBLIC_RUNTIME_COMMAND_RE.match(command), command


def _assert_primary_line_shape(block: str) -> None:
    matches = list(PRIMARY_COMMAND_RE.finditer(block))
    assert len(matches) == 1, block
    label = matches[0].group("label")
    command = matches[0].group("command")
    if label == " local transition":
        assert LOCAL_TRANSITION_COMMAND_RE.match(command), command
        assert "**After this completes:**" in block
        return
    _assert_public_runtime_command(command)


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
        "owner labels",
        "local_transition",
        "local_helper",
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


def test_stage_stop_reference_next_up_blocks_have_one_owned_primary() -> None:
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
        _assert_primary_line_shape(block)
        assert all(fragment not in block for fragment in forbidden_fragments)


def test_stage_stop_owned_yaml_blocks_use_public_runtime_secondaries() -> None:
    blocks_by_path = {path: _stage_stop_blocks(path) for path in STAGE_STOP_OWNED_PATHS}
    assert all(blocks_by_path.values())

    for path, blocks in blocks_by_path.items():
        for stage_stop in blocks:
            assert stage_stop["status"] in {"checkpoint", "blocked", "completed", "failed"}
            assert "checkpoint" in stage_stop
            _assert_public_runtime_command(stage_stop["next_runtime_command"])
            also_available = stage_stop.get("also_available", [])
            assert isinstance(also_available, list), path
            for command in also_available:
                _assert_public_runtime_command(command)


def test_stage_stop_owned_next_up_blocks_have_one_primary_without_raw_reload() -> None:
    forbidden_fragments = (
        "gpd --raw init",
        "--raw init",
        "gpd --raw stage field-access",
        "--raw stage field-access",
    )

    for path in STAGE_STOP_OWNED_PATHS:
        blocks = _next_up_blocks(path)
        assert blocks, path
        for block in blocks:
            _assert_primary_line_shape(block)
            assert all(fragment not in block for fragment in forbidden_fragments), path
