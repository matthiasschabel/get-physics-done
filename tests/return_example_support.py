"""Shared helpers for tests that inspect visible ``gpd_return`` examples."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from gpd.core.return_contract import REQUIRED_RETURN_FIELDS, validate_gpd_return_markdown

FENCED_YAML_RE = re.compile(
    r"^```ya?ml[^\n]*\n(?P<body>.*?)(?:\n^```[ \t]*$)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)


@dataclass(frozen=True)
class GpdReturnExample:
    """One fenced visible ``gpd_return`` example with source location."""

    source_name: str
    line_number: int
    body: str
    markdown: str


def extract_gpd_return_examples(
    path_or_text: Path | str,
    *,
    source_name: str | None = None,
    skip_child_gate_examples: bool = True,
) -> list[GpdReturnExample]:
    """Extract fenced YAML examples whose body contains ``gpd_return``."""

    if isinstance(path_or_text, Path):
        text = path_or_text.read_text(encoding="utf-8")
        name = source_name or path_or_text.as_posix()
    else:
        text = path_or_text
        name = source_name or "<text>"

    examples: list[GpdReturnExample] = []
    for match in FENCED_YAML_RE.finditer(text):
        body = match.group("body")
        if "gpd_return" not in body:
            continue
        if skip_child_gate_examples and ("child_gate:" in body or "child_gates:" in body):
            continue
        examples.append(
            GpdReturnExample(
                source_name=name,
                line_number=text.count("\n", 0, match.start()) + 1,
                body=body,
                markdown=f"```yaml\n{body.rstrip()}\n```",
            )
        )
    return examples


def validate_gpd_return_examples(
    examples: Iterable[GpdReturnExample],
    *,
    require_required_fields: bool = False,
) -> tuple[list[dict[str, object]], list[str]]:
    """Validate extracted examples and return parsed envelopes plus location errors."""

    envelopes: list[dict[str, object]] = []
    failures: list[str] = []
    for example in examples:
        result = validate_gpd_return_markdown(example.markdown)
        if not result.passed:
            failures.append(f"{example.source_name}:{example.line_number}: {'; '.join(result.errors)}")
            continue
        if require_required_fields:
            missing_fields = sorted(set(REQUIRED_RETURN_FIELDS) - set(result.fields))
            if missing_fields:
                failures.append(
                    f"{example.source_name}:{example.line_number}: missing required field(s): "
                    + ", ".join(missing_fields)
                )
                continue
        envelopes.append(result.fields)
    return envelopes, failures
