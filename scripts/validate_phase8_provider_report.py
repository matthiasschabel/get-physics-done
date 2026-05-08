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
        _validate_provider_attempt_budget_shape(
            report,
            max_provider_attempts=max_provider_attempts,
            max_mutating_rows=max_mutating_rows,
        )
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

    raise ValueError(f"unsupported Phase 8 report schema {schema!r}; expected {PROVIDER_ATTEMPT_REPORT_SCHEMA!r}")


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
        raise ValueError(f"required Phase 8 smoke report must have decision='accept'; got {report.get('decision')!r}")

    if expected_repo_head and report.get("repo_head") != expected_repo_head:
        raise ValueError(
            "Phase 8 smoke report repo_head "
            f"{report.get('repo_head')!r} does not match expected release SHA {expected_repo_head!r}"
        )

    if max_provider_attempts is not None:
        provider_attempt_count = _required_int(
            report.get("provider_attempt_count"),
            "provider_attempt_count",
            flag="--max-provider-attempts",
        )
        if provider_attempt_count > max_provider_attempts:
            raise ValueError(
                "Phase 8 smoke report provider_attempt_count "
                f"{provider_attempt_count} exceeds --max-provider-attempts {max_provider_attempts}"
            )

    if max_mutating_rows is not None:
        budget = _required_mapping(
            report.get("budget_consumption"),
            "budget_consumption",
            flag="--max-mutating-rows",
        )
        mutating_rows = _required_int(
            budget.get("mutating_rows"),
            "budget_consumption.mutating_rows",
            flag="--max-mutating-rows",
        )
        if mutating_rows > max_mutating_rows:
            raise ValueError(
                "Phase 8 smoke report budget_consumption.mutating_rows "
                f"{mutating_rows} exceeds --max-mutating-rows {max_mutating_rows}"
            )

    for key in ("product_findings", "harness_readiness_findings", "provider_environment_findings"):
        for finding in _mapping_items(report.get(key)):
            severity = str(finding.get("severity", "")).upper()
            if severity in {"S0", "S1"}:
                finding_id = finding.get("finding_id", "unknown")
                raise ValueError(
                    "Phase 8 smoke report contains blocking S0/S1 finding in "
                    f"{key}: severity {severity}, finding_id {finding_id!r}"
                )


def _validate_provider_attempt_budget_shape(
    report: Mapping[str, object],
    *,
    max_provider_attempts: int | None,
    max_mutating_rows: int | None,
) -> None:
    if max_provider_attempts is not None:
        _required_int(
            report.get("provider_attempt_count"),
            "provider_attempt_count",
            flag="--max-provider-attempts",
        )

    if max_mutating_rows is not None:
        budget = _required_mapping(
            report.get("budget_consumption"),
            "budget_consumption",
            flag="--max-mutating-rows",
        )
        _required_int(
            budget.get("mutating_rows"),
            "budget_consumption.mutating_rows",
            flag="--max-mutating-rows",
        )


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


def _required_mapping(value: object, field: str, *, flag: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be present as a JSON object when {flag} is set")
    return value


def _required_int(value: object, field: str, *, flag: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be present as an integer when {flag} is set")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
