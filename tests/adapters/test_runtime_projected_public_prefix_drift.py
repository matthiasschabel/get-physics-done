"""Regression tests for descriptor-owned public command prefixes in projections."""

from __future__ import annotations

from dataclasses import replace

import gpd.adapters.base as base_module
import gpd.adapters.claude_code as claude_module
import gpd.adapters.codex as codex_module
import gpd.adapters.gemini as gemini_module
import gpd.adapters.opencode as opencode_module
from gpd.adapters.runtime_catalog import get_runtime_descriptor


def _descriptor_with_public_prefix(runtime: str, public_prefix: str):
    return replace(get_runtime_descriptor(runtime), public_command_surface_prefix=public_prefix)


def test_codex_projection_uses_descriptor_public_prefix_for_command_references(monkeypatch) -> None:
    descriptor = _descriptor_with_public_prefix("codex", "$public-")
    monkeypatch.setattr(codex_module, "get_runtime_descriptor", lambda runtime: descriptor)

    projected = codex_module.CodexAdapter().project_markdown_surface(
        """---
description: Prefix drift probe
---
Treat `gpd:` as the canonical command family.
Use gpd:help and /gpd:settings when discussing runtime commands.
""",
        surface_kind="command",
        path_prefix="",
        command_name="prefix-drift-probe",
        bridge_command="python -m gpd",
    )

    assert "`$public-`" in projected
    assert "$public-help" in projected
    assert "$public-settings" in projected
    assert "$gpd-help" not in projected
    assert "$gpd-settings" not in projected
    assert "$gpd-..." not in projected


def test_gemini_projection_uses_descriptor_public_prefix_for_runtime_note(monkeypatch) -> None:
    descriptor = _descriptor_with_public_prefix("gemini", "/public:")
    monkeypatch.setattr(gemini_module, "get_runtime_descriptor", lambda runtime: descriptor)
    monkeypatch.setattr(base_module, "get_runtime_descriptor", lambda runtime: descriptor)

    projected = gemini_module.GeminiAdapter().project_markdown_surface(
        """---
description: Prefix drift probe
---
Body.
""",
        surface_kind="command",
        path_prefix="",
        command_name="prefix-drift-probe",
        bridge_command="python -m gpd",
    )

    assert "/public:..." in projected
    assert "/gpd:..." not in projected


def test_gemini_projection_uses_descriptor_public_prefix_for_command_references(monkeypatch) -> None:
    descriptor = _descriptor_with_public_prefix("gemini", "/public:")
    monkeypatch.setattr(gemini_module, "get_runtime_descriptor", lambda runtime: descriptor)
    monkeypatch.setattr(base_module, "get_runtime_descriptor", lambda runtime: descriptor)

    projected = gemini_module.GeminiAdapter().project_markdown_surface(
        """---
description: Prefix drift probe
---
Treat `gpd:` as the canonical command family.
Use gpd:help and /gpd:settings when discussing runtime commands.
Do not rewrite gpd:not-a-command or /tmp/gpd:help.
""",
        surface_kind="command",
        path_prefix="",
        command_name="prefix-drift-probe",
        bridge_command="python -m gpd",
    )

    assert "`/public:`" in projected
    assert "/public:help" in projected
    assert "/public:settings" in projected
    assert "Use gpd:help" not in projected
    assert "/gpd:settings" not in projected
    assert "gpd:not-a-command" in projected
    assert "/tmp/gpd:help" in projected


def test_claude_projection_uses_descriptor_public_prefix_for_command_references(monkeypatch) -> None:
    descriptor = _descriptor_with_public_prefix("claude-code", "/public:")
    monkeypatch.setattr(base_module, "get_runtime_descriptor", lambda runtime: descriptor)

    projected = claude_module.ClaudeCodeAdapter().project_markdown_surface(
        """---
description: Prefix drift probe
---
Treat `gpd:` as the canonical command family.
Use gpd:help and /gpd:settings when discussing runtime commands.
Do not rewrite gpd:not-a-command or /tmp/gpd:help.
""",
        surface_kind="command",
        path_prefix="",
        command_name="prefix-drift-probe",
        bridge_command="python -m gpd",
    )

    assert "`/public:`" in projected
    assert "/public:help" in projected
    assert "/public:settings" in projected
    assert "Use gpd:help" not in projected
    assert "/gpd:settings" not in projected
    assert "gpd:not-a-command" in projected
    assert "/tmp/gpd:help" in projected


def test_opencode_projection_uses_descriptor_public_prefix_for_command_references(monkeypatch) -> None:
    descriptor = _descriptor_with_public_prefix("opencode", "/public-")
    monkeypatch.setattr(opencode_module, "get_runtime_descriptor", lambda runtime: descriptor)
    monkeypatch.setattr(base_module, "get_runtime_descriptor", lambda runtime: descriptor)

    projected = opencode_module.OpenCodeAdapter().project_markdown_surface(
        """---
description: Prefix drift probe
---
Treat `gpd:` as the canonical command family.
Use gpd:help and /gpd:settings when discussing runtime commands.
""",
        surface_kind="command",
        path_prefix="",
        command_name="prefix-drift-probe",
        bridge_command="python -m gpd",
    )

    assert "`/public-`" in projected
    assert "/public-help" in projected
    assert "/public-settings" in projected
    assert "gpd-help" not in projected
    assert "/gpd-settings" not in projected
