"""Test-only semantic markdown assertion helpers."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import yaml

from gpd.core.frontmatter import FrontmatterParseError, extract_frontmatter
from gpd.core.strict_yaml import load_strict_yaml
from tests.prompt_metrics_support import iter_markdown_fences

__all__ = [
    "ParsedYamlFence",
    "assert_forbidden_fragments",
    "assert_ordered_fragments",
    "assert_required_fragments",
    "extract_markdown_section",
    "normalize_text",
    "parse_frontmatter_mapping",
    "parse_yaml_fences",
    "require_mapping",
]

_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_YAML_FENCE_LANGUAGES = {"yaml", "yml"}


@dataclass(frozen=True, slots=True)
class ParsedYamlFence:
    """A parsed YAML code fence with source line metadata."""

    info: str
    data: object
    start_line: int
    end_line: int


def normalize_text(text: str) -> str:
    """Return text with incidental whitespace collapsed."""

    return " ".join(text.split())


def _coerce_fragments(fragments: Iterable[str] | str) -> tuple[str, ...]:
    if isinstance(fragments, str):
        fragments = (fragments,)
    coerced = tuple(fragments)
    if any(fragment == "" for fragment in coerced):
        raise ValueError("fragments must be non-empty")
    return coerced


def _normalize_fragment(fragment: str, *, normalize: bool) -> str:
    return normalize_text(fragment) if normalize else fragment


def _format_fragment_list(fragments: Iterable[str]) -> str:
    return "\n".join(f"- {fragment!r}" for fragment in fragments)


def assert_required_fragments(
    text: str,
    fragments: Iterable[str] | str,
    *,
    context: str = "markdown",
    normalize: bool = True,
) -> None:
    """Assert that every fragment appears in the text."""

    required = _coerce_fragments(fragments)
    haystack = normalize_text(text) if normalize else text
    missing = [fragment for fragment in required if _normalize_fragment(fragment, normalize=normalize) not in haystack]
    if missing:
        raise AssertionError(f"missing required fragments in {context}:\n{_format_fragment_list(missing)}")


def assert_forbidden_fragments(
    text: str,
    fragments: Iterable[str] | str,
    *,
    context: str = "markdown",
    normalize: bool = True,
) -> None:
    """Assert that no forbidden fragment appears in the text."""

    forbidden = _coerce_fragments(fragments)
    haystack = normalize_text(text) if normalize else text
    present = [fragment for fragment in forbidden if _normalize_fragment(fragment, normalize=normalize) in haystack]
    if present:
        raise AssertionError(f"forbidden fragments present in {context}:\n{_format_fragment_list(present)}")


def assert_ordered_fragments(
    text: str,
    fragments: Iterable[str] | str,
    *,
    context: str = "markdown",
    normalize: bool = True,
) -> None:
    """Assert that fragments appear in the given order."""

    ordered = _coerce_fragments(fragments)
    haystack = normalize_text(text) if normalize else text
    cursor = 0
    previous_fragment: str | None = None
    for fragment in ordered:
        needle = _normalize_fragment(fragment, normalize=normalize)
        index = haystack.find(needle, cursor)
        if index >= 0:
            cursor = index + len(needle)
            previous_fragment = fragment
            continue

        earlier_index = haystack.find(needle)
        if earlier_index >= 0:
            raise AssertionError(
                f"fragment appears out of order in {context}: {fragment!r} appears before {previous_fragment!r}"
            )
        if previous_fragment is None:
            raise AssertionError(f"missing ordered fragment in {context}: {fragment!r}")
        raise AssertionError(f"missing ordered fragment in {context}: {fragment!r} after {previous_fragment!r}")


def _heading_level(line: str) -> int | None:
    match = _HEADING_RE.match(line.strip())
    if match is None:
        return None
    return len(match.group(1))


def _fenced_line_numbers(text: str) -> set[int]:
    fenced_lines: set[int] = set()
    for fence in iter_markdown_fences(text):
        fenced_lines.update(range(fence.start_line, fence.end_line + 1))
    return fenced_lines


def extract_markdown_section(text: str, heading: str, *, context: str = "markdown") -> str:
    """Return the body under an exact ATX heading, ignoring headings inside fences."""

    target_heading = heading.strip()
    target_level = _heading_level(target_heading)
    if target_level is None:
        raise ValueError(f"heading must be an ATX markdown heading, got {heading!r}")

    lines = text.splitlines()
    fenced_lines = _fenced_line_numbers(text)
    start_index: int | None = None
    for index, line in enumerate(lines):
        line_number = index + 1
        if line_number in fenced_lines:
            continue
        if line.strip() == target_heading:
            start_index = index + 1
            break

    if start_index is None:
        raise AssertionError(f"missing markdown section in {context}: {target_heading!r}")

    end_index = len(lines)
    for index in range(start_index, len(lines)):
        line_number = index + 1
        if line_number in fenced_lines:
            continue
        heading_level = _heading_level(lines[index])
        if heading_level is not None and heading_level <= target_level:
            end_index = index
            break

    return "\n".join(lines[start_index:end_index]).strip("\n")


def parse_frontmatter_mapping(text: str, *, context: str = "markdown") -> dict[str, object]:
    """Parse the top-level frontmatter mapping from markdown text."""

    try:
        frontmatter, _body = extract_frontmatter(text)
    except FrontmatterParseError as exc:
        raise AssertionError(f"invalid frontmatter in {context}: {exc}") from exc
    return dict(frontmatter)


def _fence_language(info: str) -> str:
    return info.strip().split(maxsplit=1)[0].lower() if info.strip() else ""


def parse_yaml_fences(
    text: str,
    *,
    info: str | None = None,
    context: str = "markdown",
) -> tuple[ParsedYamlFence, ...]:
    """Parse YAML code fences, preserving each fence's source line metadata."""

    parsed: list[ParsedYamlFence] = []
    requested_language = info.lower() if info is not None else None
    for fence in iter_markdown_fences(text):
        language = _fence_language(fence.info)
        if requested_language is None:
            if language not in _YAML_FENCE_LANGUAGES:
                continue
        elif fence.info.strip() != info and language != requested_language:
            continue

        try:
            data = load_strict_yaml(fence.body)
        except yaml.YAMLError as exc:
            raise AssertionError(
                f"invalid YAML fence in {context} at lines {fence.start_line}-{fence.end_line}: {exc}"
            ) from exc
        parsed.append(
            ParsedYamlFence(
                info=fence.info,
                data=data,
                start_line=fence.start_line,
                end_line=fence.end_line,
            )
        )
    return tuple(parsed)


def require_mapping(value: object, *, context: str) -> Mapping[object, object]:
    """Return a parsed YAML value as a mapping, or fail with context."""

    if not isinstance(value, Mapping):
        raise AssertionError(f"expected mapping in {context}, got {type(value).__name__}")
    return value
