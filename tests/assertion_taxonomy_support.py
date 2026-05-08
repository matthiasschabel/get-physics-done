"""Test-only assertion taxonomy helpers for prompt and surface contracts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from tests.markdown_test_support import (
    extract_markdown_section as extract_markdown_section_text,
)
from tests.markdown_test_support import (
    extract_marker_range as extract_marker_range_text,
)

__all__ = [
    "AssertionKind",
    "AssertionTaxonomyError",
    "FragmentAssertion",
    "FragmentMode",
    "MarkerScope",
    "assert_fragments",
    "assert_prompt_contracts",
    "fragment_count",
    "machine_exact",
    "marker_range",
    "public_exact",
    "semantic_anchor",
    "forbidden_duplicate",
]


class AssertionKind(StrEnum):
    """Assertion classes used by test authors."""

    MACHINE_EXACT = "machine_exact"
    PUBLIC_EXACT = "public_exact"
    SEMANTIC_ANCHOR = "semantic_anchor"
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
    """One scoped text assertion with taxonomy metadata."""

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


FragmentInput = str | Sequence[str]
MarkerInput = MarkerScope | tuple[str, str | None] | tuple[str]


def marker_range(start: str, end: str | None = None) -> MarkerScope:
    """Return a marker range for scoped fragment checks."""

    return MarkerScope(start=start, end=end)


def machine_exact(
    label: str,
    fragments: FragmentInput,
    *,
    owner: str | None = None,
    rationale: str | None = None,
    mode: FragmentMode | str = FragmentMode.ALL,
    section: str | None = None,
    markers: MarkerInput | None = None,
    context: str | None = None,
) -> FragmentAssertion:
    """Build a machine-exact assertion."""

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
    owner: str | None = None,
    rationale: str | None = None,
    mode: FragmentMode | str = FragmentMode.ALL,
    section: str | None = None,
    markers: MarkerInput | None = None,
    context: str | None = None,
) -> FragmentAssertion:
    """Build a public-exact assertion."""

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


def assert_prompt_contracts(text: str, *assertions: FragmentAssertion) -> None:
    """Assert prompt fragment contracts against text."""

    for assertion in assertions:
        if not isinstance(assertion, FragmentAssertion):
            raise TypeError(f"assert_prompt_contracts expected FragmentAssertion, got {type(assertion).__name__}")
        assertion.check(text)


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


def _extract_markdown_section(text: str, section: str, assertion: FragmentAssertion) -> str:
    context = assertion.context or "full text"
    try:
        return extract_markdown_section_text(text, section, context=context, include_heading=True)
    except AssertionError as exc:
        _raise_failure(assertion, context, f"section scope failed: {exc}")


def _extract_marker_range(
    text: str,
    markers: MarkerScope,
    assertion: FragmentAssertion,
    context: str,
) -> str:
    try:
        return extract_marker_range_text(text, markers.start, markers.end, context=context)
    except AssertionError as exc:
        _raise_failure(assertion, context, f"marker scope failed: {exc}")


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
