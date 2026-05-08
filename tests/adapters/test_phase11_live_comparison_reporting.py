from __future__ import annotations

import copy
import importlib
import inspect
import json
from collections.abc import Callable, Mapping, Sequence

import pytest

from tests.helpers.live_audit_harness.reporting import render_provider_attempt_report

PHASE11_COMPARISON_SCHEMA = "phase11.live-comparison-report.v1"
PHASE11_COMPARISON_MODULE = "tests.helpers.live_audit_harness.phase11_comparison"


def test_phase11_live_comparison_accepts_clean_manual_and_nightly_reports() -> None:
    manual_report = _provider_attempt_report(
        "manual",
        rows=[
            _attempt_row(
                row_id="manual-gemini-verify",
                scenario_id="VERIFY-PROOF-GAP",
                persona_id="P40_physics_verification_researcher",
                provider_runtime="gemini",
                command_bucket="verify",
            ),
            _attempt_row(row_id="manual-codex-start"),
        ],
    )
    nightly_report = _provider_attempt_report(
        "nightly",
        rows=[
            _attempt_row(row_id="nightly-codex-start"),
            _attempt_row(
                row_id="nightly-gemini-verify",
                scenario_id="VERIFY-PROOF-GAP",
                persona_id="P40_physics_verification_researcher",
                provider_runtime="gemini",
                command_bucket="verify",
            ),
        ],
    )

    comparison = _render_comparison(manual_report, nightly_report)
    _validate_comparison(comparison)

    assert comparison["schema"] == PHASE11_COMPARISON_SCHEMA
    assert comparison["decision"] == "accept"
    assert comparison["provider_subprocess_allowed_in_default_pytest"] is False
    assert comparison["network_allowed_in_default_pytest"] is False
    assert comparison["manual_or_nightly_only"] is True
    assert set(comparison["source_collection_classes"]) == {"manual", "nightly"}
    assert {
        (source["collection_class"], source["artifact_ref"], source["report_schema"])
        for source in comparison["source_reports"]
    } == {
        ("manual", "manual-phase8-provider-attempt-report.json", "phase8.provider_attempt_report.v1"),
        ("nightly", "nightly-phase8-provider-attempt-report.json", "phase8.provider_attempt_report.v1"),
    }

    assert comparison["aggregates"]["row_count"] == 2
    assert comparison["aggregates"]["common_row_count"] == 2
    assert comparison["aggregates"]["missing_manual_row_count"] == 0
    assert comparison["aggregates"]["missing_nightly_row_count"] == 0
    assert comparison["aggregates"]["regressed_row_count"] == 0

    rows = comparison["rows"]
    row_keys = [row["row_key"] for row in rows]
    assert row_keys == sorted(row_keys)
    assert len(row_keys) == len(set(row_keys))
    assert [row["provider_runtime"] for row in rows] == ["codex", "gemini"]
    assert [row["manual_result_class"] for row in rows] == ["green", "green"]
    assert [row["nightly_result_class"] for row in rows] == ["green", "green"]
    assert all(row["delta_class"] == "unchanged" for row in rows)
    assert all(row["comparison_row_id"].startswith("phase11-live-comparison:") for row in rows)
    assert all("manual-" not in row["row_key"] and "nightly-" not in row["row_key"] for row in rows)

    comparison_again = _render_comparison(manual_report, nightly_report)
    assert comparison_again == comparison


def test_phase11_live_comparison_needs_repair_for_product_s1_regression() -> None:
    manual_report = _provider_attempt_report("manual", rows=[_attempt_row(row_id="manual-codex-start")])
    nightly_report = _provider_attempt_report(
        "nightly",
        rows=[
            _attempt_row(
                row_id="nightly-codex-start",
                result_class="red",
                findings=[
                    {
                        "finding_id": "product.regression.stale_state_trusted",
                        "finding_class": "product_behavior",
                        "severity": "S1",
                        "summary": "Nightly trusted stale state that manual did not trust.",
                    }
                ],
            )
        ],
    )

    comparison = _render_comparison(manual_report, nightly_report, comparison_id="phase11-product-regression")
    _validate_comparison(comparison)

    assert comparison["decision"] == "needs_repair"
    assert comparison["aggregates"]["regressed_row_count"] == 1
    assert comparison["aggregates"]["product_behavior_finding_count"] == 1
    assert comparison["aggregates"]["provider_environment_finding_count"] == 0

    row = comparison["rows"][0]
    assert row["row_key"]
    assert row["manual_result_class"] == "green"
    assert row["nightly_result_class"] == "red"
    assert row["delta_class"] == "regressed"
    assert "product.regression.stale_state_trusted" in row["finding_ids"]
    assert "result_class_regressed" in row["regression_flags"]
    assert "new_s0_s1_product_finding" in row["regression_flags"]
    assert _verdict_classes(comparison, verdict="fail") == {"product_behavior"}


@pytest.mark.parametrize(
    ("manual_report", "nightly_report", "missing_collection"),
    [
        (None, "nightly", "manual"),
        ("manual", None, "nightly"),
    ],
)
def test_phase11_live_comparison_blocks_when_manual_or_nightly_report_is_missing(
    manual_report: str | None,
    nightly_report: str | None,
    missing_collection: str,
) -> None:
    manual = (
        _provider_attempt_report("manual", rows=[_attempt_row(row_id="manual-codex-start")])
        if manual_report == "manual"
        else None
    )
    nightly = (
        _provider_attempt_report("nightly", rows=[_attempt_row(row_id="nightly-codex-start")])
        if nightly_report == "nightly"
        else None
    )

    comparison = _render_comparison(manual, nightly, comparison_id=f"phase11-missing-{missing_collection}")
    _validate_comparison(comparison)

    assert comparison["decision"] == "blocked"
    assert comparison["aggregates"][f"missing_{missing_collection}_report_count"] == 1
    assert any(
        verdict.get("verdict") == "blocked" and verdict.get("collection_class") == missing_collection
        for verdict in comparison["comparison_verdicts"]
    )


def test_phase11_live_comparison_keeps_provider_environment_findings_out_of_product_behavior() -> None:
    manual_report = _provider_attempt_report("manual", rows=[_attempt_row(row_id="manual-codex-start")])
    nightly_report = _provider_attempt_report(
        "nightly",
        rows=[
            _attempt_row(
                row_id="nightly-codex-start",
                findings=[
                    {
                        "finding_id": "provider_environment.cli_missing",
                        "finding_class": "provider_environment",
                        "severity": "S1",
                        "summary": "Provider CLI was unavailable in the nightly environment.",
                    }
                ],
            )
        ],
    )

    comparison = _render_comparison(manual_report, nightly_report, comparison_id="phase11-provider-env")
    _validate_comparison(comparison)

    assert comparison["aggregates"]["product_behavior_finding_count"] == 0
    assert comparison["aggregates"]["provider_environment_finding_count"] == 1
    assert comparison["product_behavior_findings"] == []
    assert [finding["finding_id"] for finding in comparison["provider_environment_findings"]] == [
        "provider_environment.cli_missing"
    ]
    assert "product_behavior" not in _verdict_classes(comparison, verdict="fail")
    assert "provider_environment" in _verdict_classes(comparison, verdict="blocked")

    row = comparison["rows"][0]
    assert row["manual_result_class"] == "green"
    assert row["nightly_result_class"] == "green"
    assert row["provider_environment_finding_ids"] == ["provider_environment.cli_missing"]
    assert row["product_finding_ids"] == []


def test_phase11_live_comparison_markdown_has_expected_sections_and_no_raw_material() -> None:
    manual_report = _provider_attempt_report("manual", rows=[_attempt_row(row_id="manual-codex-start")])
    nightly_report = _provider_attempt_report("nightly", rows=[_attempt_row(row_id="nightly-codex-start")])
    comparison = _render_comparison(manual_report, nightly_report, comparison_id="phase11-markdown")

    markdown = _render_markdown(comparison)

    assert markdown.startswith("# Phase 11 Live Comparison Report\n")
    for section in (
        "## Source Reports",
        "## Aggregate Deltas",
        "## Comparison Verdicts",
        "## Provider Environment Findings",
        "## Product Behavior Findings",
        "## Rows",
        "## Retention Manifest",
    ):
        assert section in markdown
    assert "phase11-markdown" in markdown
    assert "manual-phase8-provider-attempt-report.json" in markdown
    assert "nightly-phase8-provider-attempt-report.json" in markdown
    assert not _contains_key(comparison, "provider_output")
    assert not _contains_key(comparison, "raw_transcript")
    assert not _contains_key(comparison, "env")
    assert not _contains_key(comparison, "argv")
    assert not _contains_key(comparison, "account_identifier")
    serialized = json.dumps({"json": comparison, "markdown": markdown}, sort_keys=True)
    assert "provider transcript" not in serialized
    assert "researcher@example.com" not in serialized


@pytest.mark.parametrize(
    ("field_name", "inject"),
    [
        ("provider_output", lambda report: report["rows"][0].__setitem__("provider_output", {"stdout": "x"})),
        ("raw_transcript", lambda report: report["rows"][0].__setitem__("raw_transcript", "x")),
        ("env", lambda report: report["rows"][0].__setitem__("env", {"HOME": "/Users/sergio/private"})),
        ("argv", lambda report: report["rows"][0].__setitem__("argv", ["provider-cli", "subcommand", "prompt"])),
        (
            "account_identifier",
            lambda report: report["auth_profile"].__setitem__("account_identifier", "researcher@example.com"),
        ),
    ],
)
def test_phase11_live_comparison_rejects_raw_provider_and_account_fields(
    field_name: str,
    inject: Callable[[dict[str, object]], None],
) -> None:
    manual_report = _provider_attempt_report("manual", rows=[_attempt_row(row_id="manual-codex-start")])
    nightly_report = _provider_attempt_report("nightly", rows=[_attempt_row(row_id="nightly-codex-start")])
    poisoned_manual = copy.deepcopy(manual_report)
    inject(poisoned_manual)

    with pytest.raises(ValueError, match=field_name):
        _render_comparison(poisoned_manual, nightly_report, comparison_id=f"phase11-raw-{field_name}")


def _attempt_row(
    *,
    row_id: str,
    scenario_id: str = "HELP-BEGINNER",
    persona_id: str = "P00_zero_coder",
    provider_runtime: str = "codex",
    command_bucket: str = "start",
    result_class: str = "green",
    findings: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    return {
        "row_id": row_id,
        "scenario_id": scenario_id,
        "scenario_template_id": f"T-{scenario_id.casefold()}",
        "persona_id": persona_id,
        "provider_runtime": provider_runtime,
        "provider_adapter": provider_runtime,
        "attempt_status": "completed",
        "result_class": result_class,
        "command_bucket": command_bucket,
        "command_surface": f"$gpd-{command_bucket}",
        "prompt_budget": {
            "max_prompt_tokens": 2000,
            "prompt_tokens_estimate": 700,
            "completion_tokens_estimate": 120,
            "observed_total_tokens": 780,
        },
        "findings": list(findings),
        "sidecar_statuses": {"provider-attempt.json": "present"},
        "write_status": "not_written",
        "retention_refs": ["provider-attempt-json"],
    }


def _provider_attempt_report(collection_class: str, *, rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    assert collection_class in {"manual", "nightly"}
    launch_policy = f"{collection_class}_live"
    report = render_provider_attempt_report(
        [{**row, "launch_policy": launch_policy} for row in rows],
        attempt_id=f"attempt-phase11-{collection_class}",
        batch_id=f"batch-phase11-{collection_class}",
        scenario_set_id="phase11-live-comparison-smoke",
        row_set_sha256=f"row-set-phase11-{collection_class}",
        budget_id=f"budget-phase11-{collection_class}",
        repo_head="abc123",
        provider_set=["codex", "gemini"],
        runtime_capabilities=[
            {"runtime": "codex", "live_runner_status": "ready"},
            {"runtime": "gemini", "live_runner_status": "ready"},
        ],
        retention_manifest={
            "artifacts": [
                {
                    "artifact_id": "provider-attempt-json",
                    "artifact_ref": f"{collection_class}-provider-attempt.json",
                    "retention_class": "committed_redacted",
                    "material_class": "sanitized_report",
                    "safe_to_commit": True,
                }
            ]
        },
    )
    assert report["schema"] == "phase8.provider_attempt_report.v1"
    return report


def _render_comparison(
    manual_report: Mapping[str, object] | None,
    nightly_report: Mapping[str, object] | None,
    *,
    comparison_id: str = "phase11-manual-nightly",
) -> dict[str, object]:
    module = _comparison_module()
    renderer = _require_callable(
        module,
        "render_live_comparison_report",
        "render_phase11_live_comparison_report",
        "render_live_provider_comparison_report",
    )
    common = {
        "comparison_id": comparison_id,
        "repo_head": "abc123",
        "manual_artifact_ref": "manual-phase8-provider-attempt-report.json",
        "nightly_artifact_ref": "nightly-phase8-provider-attempt-report.json",
    }
    source_records = []
    plain_reports = []
    if manual_report is not None:
        source_records.append(
            {
                "collection_class": "manual",
                "artifact_ref": common["manual_artifact_ref"],
                "report": manual_report,
            }
        )
        plain_reports.append(manual_report)
    if nightly_report is not None:
        source_records.append(
            {
                "collection_class": "nightly",
                "artifact_ref": common["nightly_artifact_ref"],
                "report": nightly_report,
            }
        )
        plain_reports.append(nightly_report)

    candidates = [
        ((), {"manual_report": manual_report, "nightly_report": nightly_report, **common}),
        ((), {"manual": manual_report, "nightly": nightly_report, **common}),
        ((), {"source_reports": source_records, **common}),
        ((), {"reports": source_records, **common}),
        ((), {"source_reports": plain_reports, **common}),
        ((), {"reports": plain_reports, **common}),
        ((manual_report, nightly_report), common),
        ((source_records,), common),
        ((plain_reports,), common),
    ]
    return _call_first_supported(renderer, candidates)


def _render_markdown(report: Mapping[str, object]) -> str:
    module = _comparison_module()
    renderer = _require_callable(
        module,
        "render_live_comparison_markdown",
        "render_phase11_live_comparison_markdown",
        "render_live_provider_comparison_markdown",
    )
    return str(_call_first_supported(renderer, [((report,), {}), ((), {"report": report})]))


def _validate_comparison(report: Mapping[str, object]) -> None:
    module = _comparison_module()
    validator = _optional_callable(
        module,
        "validate_live_comparison_report",
        "validate_phase11_live_comparison_report",
        "validate_live_provider_comparison_report",
    )
    if validator is not None:
        _call_first_supported(validator, [((report,), {}), ((), {"report": report})])


def _comparison_module():
    try:
        return importlib.import_module(PHASE11_COMPARISON_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name == PHASE11_COMPARISON_MODULE:
            pytest.fail(f"Worker A helper module is missing: {PHASE11_COMPARISON_MODULE}")
        raise


def _require_callable(module: object, *names: str) -> Callable[..., object]:
    helper = _optional_callable(module, *names)
    if helper is None:
        pytest.fail(f"{PHASE11_COMPARISON_MODULE} is missing one of: {', '.join(names)}")
    return helper


def _optional_callable(module: object, *names: str) -> Callable[..., object] | None:
    for name in names:
        value = getattr(module, name, None)
        if callable(value):
            return value
    return None


def _call_first_supported(
    function: Callable[..., object],
    candidates: Sequence[tuple[tuple[object, ...], Mapping[str, object]]],
) -> object:
    errors: list[str] = []
    signature = inspect.signature(function)
    for args, kwargs in candidates:
        filtered_kwargs = _supported_kwargs(signature, kwargs)
        try:
            result = function(*args, **filtered_kwargs)
        except TypeError as exc:
            errors.append(str(exc))
            continue
        return result
    pytest.fail(f"Could not call {function.__name__} with supported Phase 11 comparison inputs: {errors}")


def _supported_kwargs(signature: inspect.Signature, kwargs: Mapping[str, object]) -> dict[str, object]:
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()):
        return dict(kwargs)
    return {key: value for key, value in kwargs.items() if key in signature.parameters}


def _verdict_classes(report: Mapping[str, object], *, verdict: str) -> set[str]:
    classes = set()
    for item in report.get("comparison_verdicts", []):
        if isinstance(item, Mapping) and item.get("verdict") == verdict:
            classes.add(str(item.get("finding_class") or item.get("verdict_class") or item.get("class")))
    return classes


def _contains_key(value: object, key: str) -> bool:
    if isinstance(value, Mapping):
        return key in value or any(_contains_key(child, key) for child in value.values())
    if isinstance(value, list):
        return any(_contains_key(child, key) for child in value)
    return False
