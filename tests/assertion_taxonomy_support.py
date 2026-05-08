"""Test-only assertion taxonomy helpers for prompt and surface contracts."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from tests.prompt_metrics_support import PromptSurfaceMetrics, measure_prompt_surface

__all__ = [
    "AssertionKind",
    "AssertionTaxonomyError",
    "FragmentAssertion",
    "FragmentMode",
    "MarkerScope",
    "PromptBudgetAssertion",
    "assert_fragments",
    "assert_prompt_budget",
    "fragment_count",
    "machine_exact",
    "marker_range",
    "prompt_budget",
    "public_exact",
    "semantic_anchor",
    "forbidden_duplicate",
]


class AssertionKind(StrEnum):
    """Phase 0 assertion classes used by test authors."""

    MACHINE_EXACT = "machine_exact"
    PUBLIC_EXACT = "public_exact"
    SEMANTIC_ANCHOR = "semantic_anchor"
    BUDGET = "budget"
    FORBIDDEN_DUPLICATE = "forbidden_duplicate"


class FragmentMode(StrEnum):
    """Fragment matching modes for text assertions."""

    ALL = "all"
    ANY = "any"
    ORDERED = "ordered"
    ABSENT = "absent"
    COUNT = "count"


class AssertionTaxonomyError(AssertionError):
    """Assertion failure with taxonomy metadata in the message."""


@dataclass(frozen=True, slots=True)
class MarkerScope:
    """A text region beginning at ``start`` and ending before ``end``."""

    start: str
    end: str | None = None

    def __post_init__(self) -> None:
        if not self.start:
            raise ValueError("Marker scope requires a non-empty start marker")
        if self.end == "":
            raise ValueError("Marker scope end marker must be non-empty when provided")


@dataclass(frozen=True, slots=True)
class FragmentAssertion:
    """One scoped text assertion with Phase 0 taxonomy metadata."""

    kind: AssertionKind
    label: str
    fragments: tuple[str, ...]
    mode: FragmentMode = FragmentMode.ALL
    owner: str | None = None
    rationale: str | None = None
    section: str | None = None
    markers: MarkerScope | None = None
    expected_count: int | None = None
    max_count: int | None = None
    context: str | None = None

    def __post_init__(self) -> None:
        kind = AssertionKind(self.kind)
        mode = FragmentMode(self.mode)
        fragments = tuple(self.fragments)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "fragments", fragments)

        if not self.label.strip():
            raise ValueError("Assertion label must be non-empty")
        if not fragments or any(fragment == "" for fragment in fragments):
            raise ValueError("Fragment assertions require at least one non-empty fragment")
        if kind in {AssertionKind.MACHINE_EXACT, AssertionKind.PUBLIC_EXACT} and (
            not _non_empty(self.owner) or not _non_empty(self.rationale)
        ):
            raise ValueError("Exact assertions require non-empty owner and rationale metadata")
        if mode is FragmentMode.COUNT:
            if (self.expected_count is None) == (self.max_count is None):
                raise ValueError("Count fragment assertions require exactly one of expected_count or max_count")
            if self.expected_count is not None and self.expected_count < 0:
                raise ValueError("expected_count must be non-negative")
            if self.max_count is not None and self.max_count < 0:
                raise ValueError("max_count must be non-negative")
        elif self.expected_count is not None or self.max_count is not None:
            raise ValueError("expected_count and max_count are only valid with FragmentMode.COUNT")
        if kind is AssertionKind.FORBIDDEN_DUPLICATE and mode is not FragmentMode.COUNT:
            raise ValueError("Forbidden-duplicate assertions use FragmentMode.COUNT")

    def check(self, text: str) -> None:
        """Assert this fragment contract against ``text``."""

        assert_fragments(text, self)


@dataclass(frozen=True, slots=True)
class PromptBudgetAssertion:
    """Prompt budget assertion backed by ``tests.prompt_metrics_support``."""

    label: str
    path: Path
    src_root: Path
    path_prefix: str
    max_lines: int | None = None
    max_chars: int | None = None
    runtime: str | None = None
    context: str | None = None

    kind: AssertionKind = field(default=AssertionKind.BUDGET, init=False)

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("Budget assertion label must be non-empty")
        if self.max_lines is None and self.max_chars is None:
            raise ValueError("Budget assertions require max_lines, max_chars, or both")
        if self.max_lines is not None and self.max_lines < 0:
            raise ValueError("max_lines must be non-negative")
        if self.max_chars is not None and self.max_chars < 0:
            raise ValueError("max_chars must be non-negative")

    def check(self) -> PromptSurfaceMetrics:
        """Measure and assert this budget, returning the measured metrics."""

        return assert_prompt_budget(
            self.path,
            label=self.label,
            src_root=self.src_root,
            path_prefix=self.path_prefix,
            max_lines=self.max_lines,
            max_chars=self.max_chars,
            runtime=self.runtime,
            context=self.context,
        )


FragmentInput = str | Sequence[str]
MarkerInput = MarkerScope | tuple[str, str | None] | tuple[str]


def marker_range(start: str, end: str | None = None) -> MarkerScope:
    """Return a marker range for scoped fragment checks."""

    return MarkerScope(start=start, end=end)


def machine_exact(
    label: str,
    fragments: FragmentInput,
    *,
    owner: str,
    rationale: str,
    mode: FragmentMode | str = FragmentMode.ALL,
    section: str | None = None,
    markers: MarkerInput | None = None,
    context: str | None = None,
) -> FragmentAssertion:
    """Build a machine-exact assertion with required ownership metadata."""

    return _fragment_assertion(
        AssertionKind.MACHINE_EXACT,
        label,
        fragments,
        mode=mode,
        owner=owner,
        rationale=rationale,
        section=section,
        markers=markers,
        context=context,
    )


def public_exact(
    label: str,
    fragments: FragmentInput,
    *,
    owner: str,
    rationale: str,
    mode: FragmentMode | str = FragmentMode.ALL,
    section: str | None = None,
    markers: MarkerInput | None = None,
    context: str | None = None,
) -> FragmentAssertion:
    """Build a public-exact assertion with required ownership metadata."""

    return _fragment_assertion(
        AssertionKind.PUBLIC_EXACT,
        label,
        fragments,
        mode=mode,
        owner=owner,
        rationale=rationale,
        section=section,
        markers=markers,
        context=context,
    )


def semantic_anchor(
    label: str,
    fragments: FragmentInput,
    *,
    mode: FragmentMode | str = FragmentMode.ALL,
    section: str | None = None,
    markers: MarkerInput | None = None,
    context: str | None = None,
) -> FragmentAssertion:
    """Build a semantic-anchor assertion for non-exact wording contracts."""

    return _fragment_assertion(
        AssertionKind.SEMANTIC_ANCHOR,
        label,
        fragments,
        mode=mode,
        section=section,
        markers=markers,
        context=context,
    )


def fragment_count(
    label: str,
    fragments: FragmentInput,
    *,
    expected_count: int,
    section: str | None = None,
    markers: MarkerInput | None = None,
    context: str | None = None,
) -> FragmentAssertion:
    """Build a semantic-anchor count assertion."""

    return _fragment_assertion(
        AssertionKind.SEMANTIC_ANCHOR,
        label,
        fragments,
        mode=FragmentMode.COUNT,
        expected_count=expected_count,
        section=section,
        markers=markers,
        context=context,
    )


def forbidden_duplicate(
    label: str,
    fragment: str,
    *,
    max_count: int = 1,
    section: str | None = None,
    markers: MarkerInput | None = None,
    context: str | None = None,
) -> FragmentAssertion:
    """Build an assertion that a fragment does not appear more than ``max_count`` times."""

    return _fragment_assertion(
        AssertionKind.FORBIDDEN_DUPLICATE,
        label,
        fragment,
        mode=FragmentMode.COUNT,
        max_count=max_count,
        section=section,
        markers=markers,
        context=context,
    )


def prompt_budget(
    label: str,
    path: Path,
    *,
    src_root: Path,
    path_prefix: str,
    max_lines: int | None = None,
    max_chars: int | None = None,
    runtime: str | None = None,
    context: str | None = None,
) -> PromptBudgetAssertion:
    """Build a prompt budget assertion without checking it yet."""

    return PromptBudgetAssertion(
        label=label,
        path=path,
        src_root=src_root,
        path_prefix=path_prefix,
        max_lines=max_lines,
        max_chars=max_chars,
        runtime=runtime,
        context=context,
    )


def assert_fragments(text: str, assertion: FragmentAssertion) -> None:
    """Assert a fragment assertion against text."""

    scoped_text, context = _scope_text(text, assertion)
    mode = assertion.mode

    if mode is FragmentMode.ALL:
        for fragment in assertion.fragments:
            if fragment not in scoped_text:
                _raise_failure(assertion, context, f"missing fragment={fragment!r}", f"mode={mode.value}")
        return

    if mode is FragmentMode.ANY:
        if not any(fragment in scoped_text for fragment in assertion.fragments):
            _raise_failure(
                assertion,
                context,
                "missing any fragment from group=" + repr(assertion.fragments),
                f"mode={mode.value}",
            )
        return

    if mode is FragmentMode.ORDERED:
        offset = 0
        previous_fragment = "<start>"
        for fragment in assertion.fragments:
            index = scoped_text.find(fragment, offset)
            if index == -1:
                _raise_failure(
                    assertion,
                    context,
                    f"missing fragment={fragment!r}",
                    f"after fragment={previous_fragment!r}",
                    f"mode={mode.value}",
                )
            offset = index + len(fragment)
            previous_fragment = fragment
        return

    if mode is FragmentMode.ABSENT:
        for fragment in assertion.fragments:
            count = scoped_text.count(fragment)
            if count:
                _raise_failure(
                    assertion,
                    context,
                    f"forbidden fragment={fragment!r}",
                    f"count={count}",
                    f"mode={mode.value}",
                )
        return

    if mode is FragmentMode.COUNT:
        for fragment in assertion.fragments:
            observed = scoped_text.count(fragment)
            if assertion.expected_count is not None and observed != assertion.expected_count:
                _raise_failure(
                    assertion,
                    context,
                    f"fragment={fragment!r}",
                    f"observed_count={observed}",
                    f"expected_count={assertion.expected_count}",
                    f"mode={mode.value}",
                )
            if assertion.max_count is not None and observed > assertion.max_count:
                fragment_label = (
                    "duplicate fragment" if assertion.kind is AssertionKind.FORBIDDEN_DUPLICATE else "fragment"
                )
                _raise_failure(
                    assertion,
                    context,
                    f"{fragment_label}={fragment!r}",
                    f"observed_count={observed}",
                    f"max_count={assertion.max_count}",
                    f"mode={mode.value}",
                )
        return

    raise AssertionError(f"Unhandled fragment mode: {mode.value}")


def assert_prompt_budget(
    path: Path,
    *,
    label: str,
    src_root: Path,
    path_prefix: str,
    max_lines: int | None = None,
    max_chars: int | None = None,
    runtime: str | None = None,
    context: str | None = None,
) -> PromptSurfaceMetrics:
    """Measure ``path`` with the existing prompt metric helper and assert a budget."""

    assertion = PromptBudgetAssertion(
        label=label,
        path=path,
        src_root=src_root,
        path_prefix=path_prefix,
        max_lines=max_lines,
        max_chars=max_chars,
        runtime=runtime,
        context=context,
    )
    metrics = measure_prompt_surface(path, src_root=src_root, path_prefix=path_prefix, runtime=runtime)
    failures: list[str] = []
    if max_lines is not None and metrics.expanded_line_count > max_lines:
        failures.append(f"line budget exceeded: observed={metrics.expanded_line_count} max={max_lines}")
    if max_chars is not None and metrics.expanded_char_count > max_chars:
        failures.append(f"char budget exceeded: observed={metrics.expanded_char_count} max={max_chars}")
    if failures:
        _raise_budget_failure(assertion, metrics, failures)
    return metrics


def _fragment_assertion(
    kind: AssertionKind,
    label: str,
    fragments: FragmentInput,
    *,
    mode: FragmentMode | str = FragmentMode.ALL,
    owner: str | None = None,
    rationale: str | None = None,
    section: str | None = None,
    markers: MarkerInput | None = None,
    expected_count: int | None = None,
    max_count: int | None = None,
    context: str | None = None,
) -> FragmentAssertion:
    return FragmentAssertion(
        kind=kind,
        label=label,
        fragments=_normalize_fragments(fragments),
        mode=FragmentMode(mode),
        owner=owner,
        rationale=rationale,
        section=section,
        markers=_coerce_marker_scope(markers),
        expected_count=expected_count,
        max_count=max_count,
        context=context,
    )


def _normalize_fragments(fragments: FragmentInput) -> tuple[str, ...]:
    if isinstance(fragments, str):
        return (fragments,)
    return tuple(fragments)


def _coerce_marker_scope(markers: MarkerInput | None) -> MarkerScope | None:
    if markers is None or isinstance(markers, MarkerScope):
        return markers
    if len(markers) not in {1, 2}:
        raise ValueError("Marker tuple scopes require one start marker or a start/end pair")
    if len(markers) == 1:
        return MarkerScope(start=markers[0])
    return MarkerScope(start=markers[0], end=markers[1])


def _non_empty(value: str | None) -> bool:
    return value is not None and bool(value.strip())


def _scope_text(text: str, assertion: FragmentAssertion) -> tuple[str, str]:
    scoped_text = text
    contexts = [assertion.context or "full text"]

    if assertion.section is not None:
        scoped_text = _extract_markdown_section(scoped_text, assertion.section, assertion)
        contexts.append(f"section {assertion.section!r}")

    if assertion.markers is not None:
        scoped_text = _extract_marker_range(scoped_text, assertion.markers, assertion, " / ".join(contexts))
        end_marker = assertion.markers.end if assertion.markers.end is not None else "<end>"
        contexts.append(f"markers {assertion.markers.start!r}..{end_marker!r}")

    return scoped_text, " / ".join(contexts)


_HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<title>.+?)\s*#*\s*$")


def _extract_markdown_section(text: str, section: str, assertion: FragmentAssertion) -> str:
    target = section.strip()
    lines = text.splitlines(keepends=True)
    start_index: int | None = None
    start_level: int | None = None

    for index, line in enumerate(lines):
        stripped = line.strip()
        match = _HEADING_RE.match(stripped)
        if stripped == target:
            start_index = index
            start_level = len(match.group("hashes")) if match else 6
            break
        if match and match.group("title").strip() == target:
            start_index = index
            start_level = len(match.group("hashes"))
            break

    if start_index is None or start_level is None:
        _raise_failure(assertion, "full text", f"missing section={section!r}")

    end_index = len(lines)
    for index in range(start_index + 1, len(lines)):
        match = _HEADING_RE.match(lines[index].strip())
        if match and len(match.group("hashes")) <= start_level:
            end_index = index
            break
    return "".join(lines[start_index:end_index])


def _extract_marker_range(
    text: str,
    markers: MarkerScope,
    assertion: FragmentAssertion,
    context: str,
) -> str:
    start_index = text.find(markers.start)
    if start_index == -1:
        _raise_failure(assertion, context, f"missing start marker={markers.start!r}")

    content_start = start_index + len(markers.start)
    if markers.end is None:
        return text[content_start:]

    end_index = text.find(markers.end, content_start)
    if end_index == -1:
        _raise_failure(assertion, context, f"missing end marker={markers.end!r}")
    return text[content_start:end_index]


def _raise_failure(assertion: FragmentAssertion, context: str, *details: str) -> None:
    lines = [
        "Assertion taxonomy failure:",
        f"kind={assertion.kind.value}",
        f"label={assertion.label}",
        f"context={context}",
        *details,
    ]
    if assertion.owner is not None:
        lines.append(f"owner={assertion.owner}")
    if assertion.rationale is not None:
        lines.append(f"rationale={assertion.rationale}")
    raise AssertionTaxonomyError("\n".join(lines))


def _raise_budget_failure(
    assertion: PromptBudgetAssertion,
    metrics: PromptSurfaceMetrics,
    failures: Sequence[str],
) -> None:
    context = assertion.context or metrics.source_path.as_posix()
    lines = [
        "Assertion taxonomy failure:",
        f"kind={assertion.kind.value}",
        f"label={assertion.label}",
        f"context={context}",
        *failures,
    ]
    raise AssertionTaxonomyError("\n".join(lines))
