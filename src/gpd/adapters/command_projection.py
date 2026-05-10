"""Shared mechanics for runtime command projection.

Runtime adapters own their command containers, labels, policy text, and note
wording.  This module only centralizes repeated projection mechanics that are
runtime-agnostic.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from gpd.adapters.install_utils import (
    DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES,
    render_markdown_frontmatter,
    rewrite_gpd_cli_invocations_to_runtime_bridge,
    split_markdown_frontmatter,
)
from gpd.adapters.shell_fence_projection import (
    DEFAULT_DIRECT_COMMAND_PREFIXES,
    DEFAULT_TERMINAL_EXAMPLE_PREFIXES,
    ShellFenceProjection,
    classify_shell_fence_body,
)


def rewrite_projection_shell_bridge(content: str, bridge_command: str) -> str:
    """Rewrite fenced shell command-position ``gpd`` calls to ``bridge_command``."""
    return rewrite_gpd_cli_invocations_to_runtime_bridge(
        content,
        bridge_command,
        shell_fence_languages=DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES,
    )


def classify_projection_shell_fence(
    body: str,
    *,
    direct_command_prefixes: Sequence[str] = DEFAULT_DIRECT_COMMAND_PREFIXES,
    terminal_example_prefixes: Sequence[str] = DEFAULT_TERMINAL_EXAMPLE_PREFIXES,
) -> ShellFenceProjection:
    """Classify a shell fence body for runtime-neutral projection decisions."""
    return classify_shell_fence_body(
        body,
        direct_command_prefixes=direct_command_prefixes,
        terminal_example_prefixes=terminal_example_prefixes,
    )


def strip_projection_note_blocks(content: str, strip_patterns: Sequence[re.Pattern[str]]) -> str:
    """Remove previously injected runtime note blocks using adapter-owned patterns."""
    stripped = content
    for pattern in strip_patterns:
        stripped = pattern.sub("", stripped)
    return stripped


def prepend_projection_note(
    content: str,
    note: str,
    *,
    strip_patterns: Sequence[re.Pattern[str]],
) -> str:
    """Prepend ``note`` after markdown frontmatter while replacing older notes.

    The supplied note and strip patterns stay adapter-owned so runtime-specific
    labels, shell policy, and wording do not leak into shared code.  ``note``
    should include any desired trailing blank line.
    """
    preamble, frontmatter, separator, body = split_markdown_frontmatter(content)
    if not frontmatter:
        return note + strip_projection_note_blocks(content, strip_patterns)

    body = strip_projection_note_blocks(body, strip_patterns)
    return render_markdown_frontmatter(preamble, frontmatter, separator, note + body)
