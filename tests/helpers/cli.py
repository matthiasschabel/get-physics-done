"""Shared helpers for CLI tests."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence

from click.testing import Result
from typer.testing import CliRunner

from gpd.core.resume_surface import RESUME_BACKEND_ONLY_FIELDS


class StableCliRunner(CliRunner):
    def invoke(self, *args, **kwargs):
        kwargs.setdefault("color", False)
        return super().invoke(*args, **kwargs)


_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def normalize_cli_output(text: str) -> str:
    return " ".join(_ANSI_ESCAPE_RE.sub("", text).split())


def _safe_stderr(result: Result) -> str:
    try:
        return result.stderr
    except ValueError:
        return ""


def _result_failure_message(result: Result, expected_exit: int) -> str:
    details = [
        f"expected exit code {expected_exit}, got {result.exit_code}",
        f"stdout:\n{result.output}",
    ]
    stderr = _safe_stderr(result)
    if stderr:
        details.append(f"stderr:\n{stderr}")
    if result.exception is not None:
        details.append(f"exception: {result.exception!r}")
    return "\n\n".join(details)


def assert_result_exit(result: Result, expected_exit: int = 0) -> None:
    assert result.exit_code == expected_exit, _result_failure_message(result, expected_exit)


def invoke_cli(
    runner: CliRunner,
    app: object,
    args: Sequence[str],
    *,
    expect_exit: int | None = 0,
    **kwargs: object,
) -> Result:
    result = runner.invoke(app, list(args), **kwargs)
    if expect_exit is not None:
        assert_result_exit(result, expect_exit)
    return result


def json_output_from_result(result: Result, *, expect_exit: int = 0) -> object:
    assert_result_exit(result, expect_exit)
    return json.loads(result.output)


def invoke_json(
    runner: CliRunner,
    app: object,
    args: Sequence[str],
    *,
    expect_exit: int = 0,
    **kwargs: object,
) -> object:
    return json_output_from_result(invoke_cli(runner, app, args, expect_exit=None, **kwargs), expect_exit=expect_exit)


def invoke_help_text(
    runner: CliRunner,
    app: object,
    args: Sequence[str],
    *,
    expect_exit: int = 0,
    **kwargs: object,
) -> str:
    result = invoke_cli(runner, app, [*args, "--help"], expect_exit=expect_exit, **kwargs)
    return normalize_cli_output(result.output)


def assert_no_top_level_resume_aliases(payload: dict[str, object]) -> None:
    for key in RESUME_BACKEND_ONLY_FIELDS:
        assert key not in payload
