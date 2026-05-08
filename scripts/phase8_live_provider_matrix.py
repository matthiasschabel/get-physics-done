"""Provider-free Phase 8 live-provider matrix preflight."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final, TextIO

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parent.parent
    sys.path[:0] = [str(repo_root), str(repo_root / "src")]

from tests.helpers.live_audit_harness.live_capabilities import (
    DEFAULT_BUDGETS,
    DEFAULT_TIMEOUTS,
    PHASE8_LIVE_CAPABILITY_REGISTRY_SCHEMA,
    iter_live_capabilities,
    normalize_runtime_filter,
    render_live_capability_registry,
)

PHASE8_LIVE_PROVIDER_PREFLIGHT_SCHEMA: Final[str] = "phase8.live-provider-matrix-preflight.v1"
PROVIDER_SUBPROCESS_ALLOWED_BY_THIS_SCRIPT: Final[bool] = False

_LIVE_MATRIX_MODES: Final[frozenset[str]] = frozenset({"manual_live", "nightly_live"})
_MATRIX_MODES: Final[tuple[str, ...]] = ("dry_run", "manual_live", "nightly_live")
_SHA256_RE: Final[re.Pattern[str]] = re.compile(r"^[a-fA-F0-9]{64}$")


@dataclass(frozen=True, slots=True)
class PreflightConfig:
    matrix_mode: str = "dry_run"
    provider_set: tuple[str, ...] = ()
    budget_id: str | None = None
    row_set_sha256: str | None = None
    source_ref: str | None = None
    max_attempts: int = DEFAULT_BUDGETS.max_attempts
    max_mutating_rows: int = DEFAULT_BUDGETS.max_mutating_rows
    allow_live_launch: bool = False


def build_preflight_report(config: PreflightConfig | None = None) -> dict[str, object]:
    """Build class-only preflight JSON without launching providers."""

    config = config or PreflightConfig()
    provider_set = normalize_runtime_filter(config.provider_set) or ()
    runtime_filter = provider_set if provider_set else None
    capability_registry = render_live_capability_registry(runtime_filter)
    capabilities = iter_live_capabilities(runtime_filter)
    live_requested = config.matrix_mode in _LIVE_MATRIX_MODES
    refusal_reasons = _live_refusal_reasons(config, provider_set=provider_set)
    decision = _decision(live_requested=live_requested, refusal_reasons=refusal_reasons)

    return {
        "schema": PHASE8_LIVE_PROVIDER_PREFLIGHT_SCHEMA,
        "capability_registry_schema": PHASE8_LIVE_CAPABILITY_REGISTRY_SCHEMA,
        "class_only": True,
        "provider_subprocess_allowed_by_this_script": PROVIDER_SUBPROCESS_ALLOWED_BY_THIS_SCRIPT,
        "provider_launch_performed": False,
        "matrix_mode": config.matrix_mode,
        "live_launch_requested": live_requested,
        "live_launch_preconditions_satisfied": live_requested and not refusal_reasons,
        "decision": decision,
        "refusal_reasons": refusal_reasons,
        "provider_set": list(provider_set),
        "row_set_sha256": config.row_set_sha256 or "unset",
        "budget_id": config.budget_id or "unset",
        "source_ref": config.source_ref or "unset",
        "requested_budget": {
            "max_attempts": config.max_attempts,
            "max_mutating_rows": config.max_mutating_rows,
        },
        "timeout_defaults": asdict(DEFAULT_TIMEOUTS),
        "budget_defaults": asdict(DEFAULT_BUDGETS),
        "runtime_capabilities": capability_registry["runtime_capabilities"],
        "runtime_status_counts": capability_registry["status_counts"],
        "non_ready_runtimes": [
            {
                "runtime_id": capability.runtime_id,
                "live_runner_status": capability.live_runner_status,
                "deferred_reason": capability.deferred_reason,
            }
            for capability in capabilities
            if capability.live_runner_status != "ready"
        ],
        "raw_material_policy": {
            "auth_material_recorded": False,
            "account_identifiers_recorded": False,
            "provider_stdout_recorded": False,
            "provider_stderr_recorded": False,
            "prompt_text_recorded": False,
            "argv_or_env_recorded": False,
        },
        "next_allowed_action": _next_allowed_action(decision),
    }


def parse_args(argv: Sequence[str] | None = None) -> PreflightConfig:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--matrix-mode",
        choices=_MATRIX_MODES,
        default="dry_run",
        help="Preflight mode. dry_run is the provider-free default.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force the provider-free dry-run path even when another mode was supplied.",
    )
    parser.add_argument(
        "--provider-set",
        action="append",
        default=[],
        metavar="RUNTIME[,RUNTIME...]",
        help="Explicit runtime/provider set for manual or nightly live preflight.",
    )
    parser.add_argument("--budget-id", help="Explicit operator budget id required for live preflight.")
    parser.add_argument("--row-set-sha256", help="Expected Phase 8 row-set SHA-256 required for live preflight.")
    parser.add_argument("--source-ref", help="Source ref or commit label for the sanitized preflight report.")
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_BUDGETS.max_attempts)
    parser.add_argument("--max-mutating-rows", type=int, default=DEFAULT_BUDGETS.max_mutating_rows)
    parser.add_argument(
        "--allow-live-launch",
        action="store_true",
        help="Operator acknowledgement required before handing off to a live runner.",
    )
    args = parser.parse_args(argv)
    matrix_mode = "dry_run" if args.dry_run else args.matrix_mode
    return PreflightConfig(
        matrix_mode=matrix_mode,
        provider_set=tuple(args.provider_set),
        budget_id=args.budget_id,
        row_set_sha256=args.row_set_sha256,
        source_ref=args.source_ref,
        max_attempts=args.max_attempts,
        max_mutating_rows=args.max_mutating_rows,
        allow_live_launch=args.allow_live_launch,
    )


def main(argv: Sequence[str] | None = None, stdout: TextIO | None = None) -> int:
    report = build_preflight_report(parse_args(argv))
    output = stdout if stdout is not None else sys.stdout
    print(json.dumps(report, indent=2, sort_keys=True), file=output)
    return 2 if report["decision"] == "refused" else 0


def _live_refusal_reasons(config: PreflightConfig, *, provider_set: tuple[str, ...]) -> list[str]:
    if config.matrix_mode == "dry_run":
        return []
    if config.matrix_mode not in _LIVE_MATRIX_MODES:
        return [f"unsupported_matrix_mode:{config.matrix_mode}"]

    reasons: list[str] = []
    if not config.allow_live_launch:
        reasons.append("missing_allow_live_launch")
    if not _has_text(config.budget_id):
        reasons.append("missing_budget_id")
    if not _has_text(config.row_set_sha256):
        reasons.append("missing_row_set_sha256")
    elif _SHA256_RE.fullmatch(config.row_set_sha256 or "") is None:
        reasons.append("invalid_row_set_sha256")
    if not provider_set:
        reasons.append("missing_provider_set")
    if config.max_attempts < 1:
        reasons.append("invalid_max_attempts")
    if config.max_mutating_rows < 0:
        reasons.append("invalid_max_mutating_rows")

    if provider_set:
        non_ready = [
            capability.runtime_id
            for capability in iter_live_capabilities(provider_set)
            if capability.live_runner_status != "ready"
        ]
        reasons.extend(f"provider_not_live_ready:{runtime_id}" for runtime_id in non_ready)
    return reasons


def _decision(*, live_requested: bool, refusal_reasons: Sequence[str]) -> str:
    if not live_requested:
        return "dry_run"
    if refusal_reasons:
        return "refused"
    return "preflight_ready"


def _next_allowed_action(decision: str) -> str:
    if decision == "preflight_ready":
        return "hand_off_to_manual_or_nightly_live_runner"
    if decision == "refused":
        return "supply_explicit_live_flags_budget_hash_and_ready_provider_set"
    return "inspect_class_only_capability_registry"


def _has_text(value: str | None) -> bool:
    return isinstance(value, str) and bool(value.strip())


if __name__ == "__main__":
    raise SystemExit(main())
