"""Shared helpers for CLI tests."""

from __future__ import annotations

import re

from typer.testing import CliRunner

from gpd.core.resume_surface import RESUME_BACKEND_ONLY_FIELDS


class StableCliRunner(CliRunner):
    def invoke(self, *args, **kwargs):
        kwargs.setdefault("color", False)
        return super().invoke(*args, **kwargs)


_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def normalize_cli_output(text: str) -> str:
    return " ".join(_ANSI_ESCAPE_RE.sub("", text).split())


def assert_no_top_level_resume_aliases(payload: dict[str, object]) -> None:
    for key in RESUME_BACKEND_ONLY_FIELDS:
        assert key not in payload
