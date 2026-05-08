"""Validate sanitized Phase 8 provider-attempt reports for release gates."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parent.parent
    sys.path[:0] = [str(repo_root), str(repo_root / "src")]

from tests.helpers.live_audit_harness.redaction import validate_provider_report_safety
from tests.helpers.live_audit_harness.reporting import (
    PROVIDER_ATTEMPT_REPORT_SCHEMA,
    validate_provider_attempt_report,
)

SANITIZED_INTAKE_SCHEMA: Final[str] = "phase8.live-provider-gate.sanitized-intake.v1"


def validate_report(
    report: Mapping[str, object],
    *,
    require_smoke: bool = False,
    expected_repo_head: str | None = None,
    max_provider_attempts: int | None = None,
    max_mutating_rows: int | None = None,
) -> None:
    """Validate a Phase 8 report and raise ``ValueError`` on release-gate failure."""

    validate_provider_report_safety(report)
    schema = report.get("schema")
    if schema == PROVIDER_ATTEMPT_REPORT_SCHEMA:
        validate_provider_attempt_report(report)
        _validate_provider_attempt_release_gate(
            report,
            require_smoke=require_smoke,
            expected_repo_head=expected_repo_head,
            max_provider_attempts=max_provider_attempts,
            max_mutating_rows=max_mutating_rows,
        )
        return

    if schema == SANITIZED_INTAKE_SCHEMA:
        _validate_sanitized_intake(report, require_smoke=require_smoke, expected_repo_head=expected_repo_head)
        return

    raise ValueError(
        f"unsupported Phase 8 report schema {schema!r}; expected {PROVIDER_ATTEMPT_REPORT_SCHEMA!r}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Sanitized Phase 8 JSON report to validate.")
    parser.add_argument("--require-smoke", action="store_true", help="Require an accepted provider-attempt report.")
    parser.add_argument("--expected-repo-head", help="Expected release commit SHA.")
    parser.add_argument("--max-provider-attempts", type=int)
    parser.add_argument("--max-mutating-rows", type=int)
    args = parser.parse_args(argv)

    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError("report JSON must contain an object")
        validate_report(
            payload,
            require_smoke=args.require_smoke,
            expected_repo_head=args.expected_repo_head,
            max_provider_attempts=args.max_provider_attempts,
            max_mutating_rows=args.max_mutating_rows,
        )
    except Exception as exc:
        print(f"Phase 8 provider report validation failed: {exc}", file=sys.stderr)
        return 1

    print("Phase 8 provider report validation passed")
    return 0


def _validate_provider_attempt_release_gate(
    report: Mapping[str, object],
    *,
    require_smoke: bool,
    expected_repo_head: str | None,
    max_provider_attempts: int | None,
    max_mutating_rows: int | None,
) -> None:
    if require_smoke and report.get("decision") != "accept":
        raise ValueError("required Phase 8 smoke report must have decision='accept'")

    if expected_repo_head and report.get("repo_head") != expected_repo_head:
        raise ValueError("Phase 8 smoke report repo_head does not match the expected release SHA")

    if max_provider_attempts is not None and _as_int(report.get("provider_attempt_count")) > max_provider_attempts:
        raise ValueError("Phase 8 smoke report exceeds max provider attempts")

    budget = report.get("budget_consumption")
    if isinstance(budget, Mapping):
        mutating_rows = _as_int(budget.get("mutating_rows"))
        if max_mutating_rows is not None and mutating_rows > max_mutating_rows:
            raise ValueError("Phase 8 smoke report exceeds max mutating rows")

    for key in ("product_findings", "harness_readiness_findings", "provider_environment_findings"):
        for finding in _mapping_items(report.get(key)):
            if str(finding.get("severity", "")).upper() in {"S0", "S1"}:
                raise ValueError(f"Phase 8 smoke report contains open {key} severity {finding.get('severity')}")


def _validate_sanitized_intake(
    report: Mapping[str, object],
    *,
    require_smoke: bool,
    expected_repo_head: str | None,
) -> None:
    if require_smoke:
        raise ValueError("sanitized intake is not an accepted Phase 8 provider-attempt smoke report")
    if expected_repo_head and report.get("repo_head") != expected_repo_head:
        raise ValueError("Phase 8 sanitized intake repo_head does not match the expected release SHA")
    if report.get("provider_launch_performed") is True:
        raise ValueError("sanitized intake reports a provider launch; expected provider-free gate metadata")
    if report.get("provider_material_retained") is True:
        raise ValueError("sanitized intake reports retained raw provider material")


def _mapping_items(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _as_int(value: object) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
