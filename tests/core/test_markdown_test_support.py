"""Tests for semantic markdown assertion helpers."""

from __future__ import annotations

import pytest

from tests.markdown_test_support import (
    assert_forbidden_fragments,
    assert_ordered_fragments,
    assert_required_fragments,
    extract_markdown_section,
    normalize_text,
    parse_frontmatter_mapping,
    parse_yaml_fences,
    require_mapping,
)


def test_normalize_text_collapses_incidental_whitespace() -> None:
    assert normalize_text(" alpha\n\n  beta\tgamma ") == "alpha beta gamma"


def test_extract_markdown_section_ignores_fenced_headings_and_stops_at_peer_heading() -> None:
    markdown = """# Prompt

```markdown
## Contract
inside fence
```

## Contract

Required claim.

### Nested

Nested detail.

## Next

Outside.
"""

    section = extract_markdown_section(markdown, "## Contract", context="prompt")

    assert "Required claim." in section
    assert "### Nested" in section
    assert "Nested detail." in section
    assert "## Next" not in section
    assert "inside fence" not in section


def test_extract_markdown_section_missing_heading_has_contextual_failure() -> None:
    with pytest.raises(AssertionError, match=r"missing markdown section in prompt: '## Missing'"):
        extract_markdown_section("# Prompt\n\nBody.\n", "## Missing", context="prompt")


def test_required_and_forbidden_fragments_accept_normalized_prose() -> None:
    section = "The contract\nmust include `plan_contract_ref` and\n`contract_results`."

    assert_required_fragments(
        section,
        (
            "contract must include",
            "`plan_contract_ref`",
            "`contract_results`",
        ),
        context="contract section",
    )
    assert_forbidden_fragments(section, ("must_haves", "verification_inputs"), context="contract section")


def test_required_fragments_failure_lists_missing_fragments() -> None:
    with pytest.raises(AssertionError) as excinfo:
        assert_required_fragments("alpha beta", ("alpha", "gamma"), context="sample")

    message = str(excinfo.value)
    assert "missing required fragments in sample" in message
    assert "- 'gamma'" in message
    assert "alpha" not in message


def test_forbidden_fragments_failure_lists_present_fragments() -> None:
    with pytest.raises(AssertionError) as excinfo:
        assert_forbidden_fragments("alpha stale_alias beta", ("stale_alias", "other"), context="sample")

    message = str(excinfo.value)
    assert "forbidden fragments present in sample" in message
    assert "- 'stale_alias'" in message
    assert "other" not in message


def test_ordered_fragments_accept_normalized_order() -> None:
    assert_ordered_fragments("first\n\nsecond   third", ("first second", "third"), context="sample")


def test_ordered_fragments_failure_distinguishes_out_of_order_fragment() -> None:
    with pytest.raises(AssertionError) as excinfo:
        assert_ordered_fragments("beta alpha", ("alpha", "beta"), context="sample")

    message = str(excinfo.value)
    assert "fragment appears out of order in sample" in message
    assert "'beta' appears before 'alpha'" in message


def test_parse_frontmatter_mapping_returns_strict_frontmatter_mapping() -> None:
    markdown = "---\nname: prompt\nfields:\n  - plan_contract_ref\n---\n\nBody.\n"

    frontmatter = parse_frontmatter_mapping(markdown, context="prompt")

    assert frontmatter == {"name": "prompt", "fields": ["plan_contract_ref"]}


def test_parse_frontmatter_mapping_failure_includes_context() -> None:
    markdown = "---\nname: first\nname: second\n---\n\nBody.\n"

    with pytest.raises(AssertionError) as excinfo:
        parse_frontmatter_mapping(markdown, context="prompt")

    message = str(excinfo.value)
    assert "invalid frontmatter in prompt" in message
    assert "duplicate key" in message


def test_parse_yaml_fences_filters_yaml_fences_and_preserves_line_metadata() -> None:
    markdown = """Intro.

```python
value = 1
```

```yaml
schema_version: 1
fields:
  - plan_contract_ref
```

~~~yml title
status: passed
~~~
"""

    fences = parse_yaml_fences(markdown, context="prompt")

    assert len(fences) == 2
    assert fences[0].info == "yaml"
    assert fences[0].start_line == 7
    assert fences[0].end_line == 11
    assert require_mapping(fences[0].data, context="first YAML fence")["fields"] == ["plan_contract_ref"]
    assert require_mapping(fences[1].data, context="second YAML fence")["status"] == "passed"


def test_parse_yaml_fences_failure_includes_context_and_fence_lines() -> None:
    markdown = """Before.

```yaml
name: first
name: second
```
"""

    with pytest.raises(AssertionError) as excinfo:
        parse_yaml_fences(markdown, context="prompt")

    message = str(excinfo.value)
    assert "invalid YAML fence in prompt at lines 3-6" in message
    assert "duplicate key" in message


def test_require_mapping_failure_names_non_mapping_type() -> None:
    with pytest.raises(AssertionError, match="expected mapping in yaml example, got list"):
        require_mapping([], context="yaml example")
