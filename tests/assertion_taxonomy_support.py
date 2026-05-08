"""Test-only assertion taxonomy helpers for prompt and surface contracts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from tests.markdown_test_support import (
    extract_markdown_section as extract_markdown_section_text,
)
from tests.markdown_test_support import (
    extract_marker_range as extract_marker_range_text,
)
from tests.prompt_metrics_support import PromptSurfaceMetrics, budget_from_baseline, measure_prompt_surface

__all__ = [
    "AssertionKind",
    "AssertionTaxonomyError",
    "FragmentAssertion",
    "FragmentMode",
    "MarkerScope",
    "PromptBudgetAssertion",
    "assert_fragments",
    "assert_prompt_budget",
    "assert_prompt_baseline_budget",
    "assert_prompt_contracts",
    "assert_prompt_metric_budget",
    "fragment_count",
    "machine_exact",
    "marker_range",
    "prompt_budget",
    "public_exact",
    "semantic_anchor",
    "forbidden_duplicate",
]


class AssertionKind(StrEnum):
    """Assertion classes used by test authors."""

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
    max_raw_includes: int | None = None
    runtime: str | None = None
    context: str | None = None

    kind: AssertionKind = field(default=AssertionKind.BUDGET, init=False)

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("Budget assertion label must be non-empty")
        if self.max_lines is None and self.max_chars is None and self.max_raw_includes is None:
            raise ValueError("Budget assertions require max_lines, max_chars, max_raw_includes, or a combination")
        if self.max_lines is not None and self.max_lines < 0:
            raise ValueError("max_lines must be non-negative")
        if self.max_chars is not None and self.max_chars < 0:
            raise ValueError("max_chars must be non-negative")
        if self.max_raw_includes is not None and self.max_raw_includes < 0:
            raise ValueError("max_raw_includes must be non-negative")

    def check(self) -> PromptSurfaceMetrics:
        """Measure and assert this budget, returning the measured metrics."""

        return assert_prompt_budget(
            self.path,
            label=self.label,
            src_root=self.src_root,
            path_prefix=self.path_prefix,
            max_lines=self.max_lines,
            max_chars=self.max_chars,
            max_raw_includes=self.max_raw_includes,
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
    max_raw_includes: int | None = None,
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
        max_raw_includes=max_raw_includes,
        runtime=runtime,
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


def assert_prompt_budget(
    path: Path,
    *,
    label: str,
    src_root: Path,
    path_prefix: str,
    max_lines: int | None = None,
    max_chars: int | None = None,
    max_raw_includes: int | None = None,
    runtime: str | None = None,
    context: str | None = None,
) -> PromptSurfaceMetrics:
    """Measure ``path`` with the existing prompt metric helper and assert a budget."""

    PromptBudgetAssertion(
        label=label,
        path=path,
        src_root=src_root,
        path_prefix=path_prefix,
        max_lines=max_lines,
        max_chars=max_chars,
        max_raw_includes=max_raw_includes,
        runtime=runtime,
        context=context,
    )
    metrics = measure_prompt_surface(path, src_root=src_root, path_prefix=path_prefix, runtime=runtime)
    return assert_prompt_metric_budget(
        metrics,
        label=label,
        max_lines=max_lines,
        max_chars=max_chars,
        max_raw_includes=max_raw_includes,
        context=context,
    )


def assert_prompt_metric_budget(
    metrics: PromptSurfaceMetrics,
    *,
    label: str,
    max_lines: int | None = None,
    max_chars: int | None = None,
    max_raw_includes: int | None = None,
    context: str | None = None,
) -> PromptSurfaceMetrics:
    """Assert a hard budget against pre-measured prompt metrics."""

    failures: list[str] = []
    _validate_budget_label(label)
    if max_lines is None and max_chars is None and max_raw_includes is None:
        raise ValueError("Budget assertions require max_lines, max_chars, max_raw_includes, or a combination")
    if max_lines is not None and max_lines < 0:
        raise ValueError("max_lines must be non-negative")
    if max_chars is not None and max_chars < 0:
        raise ValueError("max_chars must be non-negative")
    if max_raw_includes is not None and max_raw_includes < 0:
        raise ValueError("max_raw_includes must be non-negative")

    if max_lines is not None and metrics.expanded_line_count > max_lines:
        failures.append(f"line budget exceeded: observed={metrics.expanded_line_count} max={max_lines}")
    if max_chars is not None and metrics.expanded_char_count > max_chars:
        failures.append(f"char budget exceeded: observed={metrics.expanded_char_count} max={max_chars}")
    if max_raw_includes is not None and metrics.raw_include_count > max_raw_includes:
        failures.append(f"raw include budget exceeded: observed={metrics.raw_include_count} max={max_raw_includes}")
    if failures:
        _raise_budget_failure(label, metrics, failures, context=context)
    return metrics


def assert_prompt_baseline_budget(
    metrics: PromptSurfaceMetrics,
    *,
    label: str,
    baseline_lines: int,
    baseline_chars: int,
    min_line_margin: int,
    min_char_margin: int,
    max_raw_includes: int | None = None,
    context: str | None = None,
) -> PromptSurfaceMetrics:
    """Assert two-sided baseline ratchet budgets against measured prompt metrics."""

    _validate_budget_label(label)
    for field_name, value in (
        ("baseline_lines", baseline_lines),
        ("baseline_chars", baseline_chars),
        ("min_line_margin", min_line_margin),
        ("min_char_margin", min_char_margin),
    ):
        if value < 0:
            raise ValueError(f"{field_name} must be non-negative")
    if max_raw_includes is not None and max_raw_includes < 0:
        raise ValueError("max_raw_includes must be non-negative")

    max_lines = budget_from_baseline(baseline_lines, minimum_margin=min_line_margin)
    max_chars = budget_from_baseline(baseline_chars, minimum_margin=min_char_margin)
    max_baseline_lines = budget_from_baseline(metrics.expanded_line_count, minimum_margin=min_line_margin)
    max_baseline_chars = budget_from_baseline(metrics.expanded_char_count, minimum_margin=min_char_margin)

    failures: list[str] = []
    if metrics.expanded_line_count > max_lines:
        failures.append(f"line budget exceeded: observed={metrics.expanded_line_count} max={max_lines}")
    if metrics.expanded_char_count > max_chars:
        failures.append(f"char budget exceeded: observed={metrics.expanded_char_count} max={max_chars}")
    if baseline_lines > max_baseline_lines:
        failures.append(
            "line baseline stale: "
            f"observed={metrics.expanded_line_count} max_baseline={max_baseline_lines} baseline={baseline_lines}"
        )
    if baseline_chars > max_baseline_chars:
        failures.append(
            "char baseline stale: "
            f"observed={metrics.expanded_char_count} max_baseline={max_baseline_chars} baseline={baseline_chars}"
        )
    if max_raw_includes is not None and metrics.raw_include_count > max_raw_includes:
        failures.append(f"raw include budget exceeded: observed={metrics.raw_include_count} max={max_raw_includes}")
    if failures:
        _raise_budget_failure(label, metrics, failures, context=context)
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


def _validate_budget_label(label: str) -> None:
    if not label.strip():
        raise ValueError("Budget assertion label must be non-empty")


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


def _raise_budget_failure(
    label: str,
    metrics: PromptSurfaceMetrics,
    failures: Sequence[str],
    *,
    context: str | None = None,
) -> None:
    failure_context = context or metrics.source_path.as_posix()
    lines = [
        "Assertion taxonomy failure:",
        f"kind={AssertionKind.BUDGET.value}",
        f"label={label}",
        f"context={failure_context}",
        *failures,
    ]
    raise AssertionTaxonomyError("\n".join(lines))
