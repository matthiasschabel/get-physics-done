"""Tests for assertion taxonomy support helpers."""

from __future__ import annotations

import pytest

from tests.assertion_taxonomy_support import (
    AssertionKind,
    AssertionTaxonomyError,
    FragmentMode,
    assert_prompt_baseline_budget,
    assert_prompt_budget,
    assert_prompt_contracts,
    assert_prompt_metric_budget,
    forbidden_duplicate,
    fragment_count,
    machine_exact,
    marker_range,
    prompt_budget,
    public_exact,
    semantic_anchor,
)
from tests.prompt_metrics_support import PromptSurfaceMetrics

SAMPLE_TEXT = """# Surface
outside-only legacy phrase

## Machine Contract
BEGIN MACHINE
alpha token
beta token
gamma token
repeat warning
repeat warning
END MACHINE

## Public Contract
first public phrase
second public phrase
"""


def test_assertion_taxonomy_values_are_stable_contract() -> None:
    assert tuple(kind.value for kind in AssertionKind) == (
        "machine_exact",
        "public_exact",
        "semantic_anchor",
        "budget",
        "forbidden_duplicate",
    )
    assert tuple(mode.value for mode in FragmentMode) == ("all", "any", "ordered", "absent", "count")


def test_exact_assertion_constructors_require_owner_and_rationale() -> None:
    with pytest.raises(ValueError, match="Exact assertions require non-empty owner and rationale"):
        machine_exact("schema field", "gpd_return:", owner="", rationale="schema parser depends on it")

    assertion = public_exact(
        "public help wording",
        "first public phrase",
        owner="cli-help",
        rationale="documented public CLI output",
        section="## Public Contract",
    )

    assert assertion.kind is AssertionKind.PUBLIC_EXACT
    assert assertion.owner == "cli-help"
    assertion.check(SAMPLE_TEXT)


def test_fragment_modes_cover_all_any_ordered_absent_and_count_with_scopes() -> None:
    scoped_markers = marker_range("BEGIN MACHINE", "END MACHINE")

    semantic_anchor(
        "machine anchors",
        ("alpha token", "beta token"),
        mode=FragmentMode.ALL,
        section="## Machine Contract",
        markers=scoped_markers,
    ).check(SAMPLE_TEXT)
    semantic_anchor(
        "alternate public wording",
        ("missing public phrase", "second public phrase"),
        mode=FragmentMode.ANY,
        section="Public Contract",
    ).check(SAMPLE_TEXT)
    machine_exact(
        "ordered machine fields",
        ("alpha token", "beta token", "gamma token"),
        owner="state-schema",
        rationale="machine parser consumes this field order",
        mode=FragmentMode.ORDERED,
        section="Machine Contract",
        markers=("BEGIN MACHINE", "END MACHINE"),
    ).check(SAMPLE_TEXT)
    semantic_anchor(
        "marker scope excludes outside phrase",
        "outside-only legacy phrase",
        mode=FragmentMode.ABSENT,
        section="Machine Contract",
        markers=scoped_markers,
    ).check(SAMPLE_TEXT)
    fragment_count(
        "single gamma",
        "gamma token",
        expected_count=1,
        section="Machine Contract",
        markers=scoped_markers,
    ).check(SAMPLE_TEXT)


def test_assert_prompt_contracts_uses_fence_aware_section_scopes() -> None:
    text = """# Surface

```markdown
## Machine Contract
fenced-only phrase
```

## Machine Contract
real phrase
"""

    assert_prompt_contracts(
        text,
        semantic_anchor("real section", "real phrase", section="Machine Contract"),
        semantic_anchor(
            "fenced section excluded", "fenced-only phrase", mode=FragmentMode.ABSENT, section="## Machine Contract"
        ),
    )


def test_missing_fragment_failure_names_kind_label_context_and_fragment() -> None:
    assertion = semantic_anchor("required public anchor", "missing phrase", section="## Public Contract")

    with pytest.raises(AssertionTaxonomyError) as exc_info:
        assertion.check(SAMPLE_TEXT)

    message = str(exc_info.value)
    assert "kind=semantic_anchor" in message
    assert "label=required public anchor" in message
    assert "context=full text / section '## Public Contract'" in message
    assert "missing fragment='missing phrase'" in message


def test_forbidden_duplicate_failure_names_duplicate_fragment() -> None:
    assertion = forbidden_duplicate(
        "no duplicate machine warning",
        "repeat warning",
        section="Machine Contract",
        markers=marker_range("BEGIN MACHINE", "END MACHINE"),
    )

    with pytest.raises(AssertionTaxonomyError) as exc_info:
        assertion.check(SAMPLE_TEXT)

    message = str(exc_info.value)
    assert "kind=forbidden_duplicate" in message
    assert "label=no duplicate machine warning" in message
    assert "duplicate fragment='repeat warning'" in message
    assert "observed_count=2" in message
    assert "max_count=1" in message


def test_prompt_budget_helper_wraps_existing_measurement(tmp_path) -> None:
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("first line\nsecond line\n", encoding="utf-8")

    metrics = prompt_budget(
        "tiny prompt",
        prompt_path,
        src_root=tmp_path,
        path_prefix="/runtime/",
        max_lines=2,
        max_chars=32,
    ).check()

    assert metrics.expanded_line_count == 2
    assert metrics.expanded_char_count == len("first line\nsecond line\n")

    with pytest.raises(AssertionTaxonomyError) as exc_info:
        assert_prompt_budget(
            prompt_path,
            label="tiny prompt hard cap",
            src_root=tmp_path,
            path_prefix="/runtime/",
            max_lines=1,
            max_chars=8,
        )

    message = str(exc_info.value)
    assert "kind=budget" in message
    assert "label=tiny prompt hard cap" in message
    assert "line budget exceeded: observed=2 max=1" in message
    assert "char budget exceeded: observed=23 max=8" in message


def test_prompt_metric_budget_checks_premeasured_metrics(tmp_path) -> None:
    metrics = PromptSurfaceMetrics(
        source_path=tmp_path / "prompt.md",
        raw_include_count=2,
        expanded_line_count=10,
        expanded_char_count=100,
    )

    assert (
        assert_prompt_metric_budget(
            metrics,
            label="premeasured prompt",
            max_lines=10,
            max_chars=100,
            max_raw_includes=2,
        )
        is metrics
    )

    with pytest.raises(AssertionTaxonomyError) as exc_info:
        assert_prompt_metric_budget(
            metrics,
            label="premeasured prompt hard cap",
            max_lines=9,
            max_chars=99,
            max_raw_includes=1,
            context="aggregate prompt budget",
        )

    message = str(exc_info.value)
    assert "kind=budget" in message
    assert "label=premeasured prompt hard cap" in message
    assert "context=aggregate prompt budget" in message
    assert "line budget exceeded: observed=10 max=9" in message
    assert "char budget exceeded: observed=100 max=99" in message
    assert "raw include budget exceeded: observed=2 max=1" in message


def test_prompt_baseline_budget_preserves_two_sided_ratchet(tmp_path) -> None:
    metrics = PromptSurfaceMetrics(
        source_path=tmp_path / "prompt.md",
        raw_include_count=1,
        expanded_line_count=100,
        expanded_char_count=1_000,
    )

    assert (
        assert_prompt_baseline_budget(
            metrics,
            label="baseline prompt",
            baseline_lines=100,
            baseline_chars=1_000,
            min_line_margin=5,
            min_char_margin=50,
            max_raw_includes=1,
        )
        is metrics
    )

    with pytest.raises(AssertionTaxonomyError) as exc_info:
        assert_prompt_baseline_budget(
            metrics,
            label="stale baseline prompt",
            baseline_lines=120,
            baseline_chars=1_200,
            min_line_margin=5,
            min_char_margin=50,
            max_raw_includes=0,
        )

    message = str(exc_info.value)
    assert "kind=budget" in message
    assert "label=stale baseline prompt" in message
    assert "line baseline stale: observed=100" in message
    assert "char baseline stale: observed=1000" in message
    assert "raw include budget exceeded: observed=1 max=0" in message
