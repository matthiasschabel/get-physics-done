"""Focused tests for child gate tuple schema and parsing."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from gpd.core.child_gate_snippets import render_child_gate_inline_summary, render_child_gate_markdown
from gpd.core.child_handoff import (
    ChildGateApplicator,
    ChildGateArtifact,
    ChildGateFreshness,
    ChildGateTuple,
    child_gate_tuple_from_payload,
    parse_child_gate_markdown,
)
from gpd.core.handoff_artifacts import HandoffFailureClass

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"


def _planner_gate() -> ChildGateTuple:
    return ChildGateTuple(
        id="planner_initial_plan",
        role="gpd-planner",
        required_status="completed",
        expected_artifacts=(
            ChildGateArtifact(
                path="${PHASE_DIR}/*-PLAN.md",
                kind="glob",
            ),
        ),
        allowed_roots=("${PHASE_DIR}",),
        freshness=ChildGateFreshness(
            marker="$PLANNER_HANDOFF_STARTED_AT",
            require_mtime_at_or_after_marker=True,
        ),
        validators=(
            "gpd validate handoff-artifacts - --expected-glob '${PHASE_DIR}/*-PLAN.md' --allowed-root '${PHASE_DIR}' --require-files-written --require-status completed --fresh-after \"$PLANNER_HANDOFF_STARTED_AT\"",
            "gpd validate plan-contract <each fresh plan>",
            "gpd validate plan-preflight <each fresh plan>",
        ),
        applicator=ChildGateApplicator(command="none", require_passed_true=False),
    )


def _gate_markdown(gate: ChildGateTuple) -> str:
    return render_child_gate_markdown(gate)


def _renderer_gate() -> ChildGateTuple:
    return ChildGateTuple(
        id="renderer_gate",
        role="gpd-planner",
        required_status="completed",
        expected_artifacts=(
            ChildGateArtifact(path="GPD/plan.md"),
            ChildGateArtifact(
                path="GPD/reports/*.md",
                kind="glob",
                required=False,
                must_be_named_in_files_written=False,
            ),
        ),
        allowed_roots=("GPD",),
        freshness=ChildGateFreshness(
            marker="$HANDOFF_STARTED_AT",
            require_mtime_at_or_after_marker=True,
        ),
        validators=("readable", "plan-contract"),
        applicator=ChildGateApplicator(
            command="gpd --raw apply-return-updates GPD/plan.md",
            require_passed_true=True,
        ),
        write_allowlist=("GPD/plan.md", "GPD/reports/*.md"),
        status_route={
            "checkpoint": "present_checkpoint",
            "blocked": "surface_blocker",
        },
    )


def test_child_gate_tuple_renders_compact_yaml_with_inferred_return_profile() -> None:
    rendered = _gate_markdown(_planner_gate())

    payload = yaml.safe_load(rendered.removeprefix("```yaml\n").removesuffix("```\n"))
    child_gate = payload["child_gate"]

    assert child_gate["id"] == "planner_initial_plan"
    assert child_gate["role"] == "gpd-planner"
    assert child_gate["return_profile"] == "planner"
    assert child_gate["required_status"] == "completed"
    assert child_gate["expected_artifacts"] == [
        {
            "path": "${PHASE_DIR}/*-PLAN.md",
            "kind": "glob",
            "required": True,
            "must_be_named_in_files_written": True,
        }
    ]
    assert child_gate["allowed_roots"] == ["${PHASE_DIR}"]
    assert child_gate["freshness"] == {
        "marker": "$PLANNER_HANDOFF_STARTED_AT",
        "require_mtime_at_or_after_marker": True,
        "preexisting_artifacts": "recovery_evidence_only",
    }
    assert child_gate["applicator"] == {"command": "none", "require_passed_true": False}
    assert list(child_gate["failure_route"]) == [failure_class.value for failure_class in HandoffFailureClass]


def test_render_child_gate_markdown_round_trips_full_tuple_payload() -> None:
    gate = _renderer_gate()

    rendered = render_child_gate_markdown(gate)
    payload = yaml.safe_load(rendered.removeprefix("```yaml\n").removesuffix("```\n"))

    assert payload == {"child_gate": gate.to_payload()}
    assert parse_child_gate_markdown(rendered) == gate
    assert render_child_gate_markdown(payload) == rendered
    for key in (
        "expected_artifacts",
        "allowed_roots",
        "freshness",
        "validators",
        "applicator",
        "write_allowlist",
        "status_route",
        "failure_route",
    ):
        assert key in payload["child_gate"]


def test_render_child_gate_inline_summary_names_gate_anchors() -> None:
    summary = render_child_gate_inline_summary(_renderer_gate())

    assert "child_gate=renderer_gate" in summary
    assert "role=gpd-planner" in summary
    assert "required_status=completed" in summary
    assert "artifacts=GPD/plan.md[kind=path, required=true, files_written=true]" in summary
    assert "GPD/reports/*.md[kind=glob, required=false, files_written=false]" in summary
    assert "allowed_roots=GPD" in summary
    assert (
        "freshness=marker=$HANDOFF_STARTED_AT, "
        "mtime_at_or_after_marker=true, preexisting_artifacts=recovery_evidence_only"
    ) in summary
    assert "validators=readable, plan-contract" in summary
    assert "applicator=gpd --raw apply-return-updates GPD/plan.md require_passed_true=true" in summary
    assert "write_allowlist=GPD/plan.md, GPD/reports/*.md" in summary
    assert "status_route=checkpoint->present_checkpoint, blocked->surface_blocker" in summary
    assert "failure_route=return_missing->retry_once" in summary


def test_child_gate_tuple_from_payload_accepts_wrapped_payload_and_failure_class_strings() -> None:
    gate = child_gate_tuple_from_payload(
        {
            "child_gate": {
                "id": "verifier_gate",
                "role": "gpd-verifier",
                "return_profile": "verifier",
                "required_status": "completed",
                "failure_route": {
                    "return_missing": "retry_once",
                    "validator_failed": "revision_loop",
                },
            }
        }
    )

    assert gate.return_profile == "verifier"
    assert gate.failure_route == {
        HandoffFailureClass.RETURN_MISSING: "retry_once",
        HandoffFailureClass.VALIDATOR_FAILED: "revision_loop",
    }


def test_child_gate_tuple_accepts_compact_prompt_tuple_shape() -> None:
    gate = child_gate_tuple_from_payload(
        {
            "child_gate": {
                "id": "paper_section",
                "role": "gpd-paper-writer",
                "return_profile": "paper_writer",
                "required_status": "completed",
                "expected_artifacts": ["${PAPER_DIR}/intro.tex"],
                "allowed_roots": ["${PAPER_DIR}"],
                "freshness_marker": "after $SECTION_HANDOFF_STARTED_AT",
                "validators": ["gpd validate handoff-artifacts ..."],
                "applicator": "none",
                "failure_route": "stage-recovery-gate -> retry writer | stop",
                "allowed_write_paths": ["${PAPER_DIR}/intro.tex"],
            }
        }
    )

    assert gate.return_profile == "executor"
    assert gate.expected_artifacts[0].path == "${PAPER_DIR}/intro.tex"
    assert gate.freshness is not None
    assert gate.freshness.marker == "$SECTION_HANDOFF_STARTED_AT"
    assert gate.applicator.command == "none"
    assert gate.write_allowlist == ("${PAPER_DIR}/intro.tex",)
    assert set(gate.failure_route) == set(HandoffFailureClass)


def test_parse_child_gate_markdown_accepts_raw_and_fenced_payloads() -> None:
    raw = """
id: planner_initial_plan
role: gpd-planner
required_status: completed
"""
    fenced = f"```yaml\nchild_gate:\n  {raw.strip().replace(chr(10), chr(10) + '  ')}\n```\n"

    assert parse_child_gate_markdown(raw).return_profile == "planner"
    assert parse_child_gate_markdown(fenced).return_profile == "planner"


def test_child_gate_tuple_rejects_unknown_profile_status_route_and_invalid_freshness() -> None:
    with pytest.raises(ValueError, match="unknown gpd_return role profile"):
        ChildGateTuple(id="bad", role="gpd-unknown", required_status="completed")

    with pytest.raises(ValueError, match="unknown gpd_return status"):
        ChildGateTuple(id="bad", role="gpd-planner", required_status="done")

    with pytest.raises(ValueError, match="unknown gpd_return status"):
        ChildGateTuple(id="bad", role="gpd-planner", status_route={"waiting": "pause"})

    with pytest.raises(ValueError, match="unknown handoff failure class"):
        ChildGateTuple(
            id="bad",
            role="gpd-planner",
            failure_route={"not_a_failure": "retry"},
        )

    with pytest.raises(ValueError, match="freshness marker is required"):
        ChildGateFreshness(require_mtime_at_or_after_marker=True)


def test_workflow_child_gate_yaml_blocks_parse_as_child_gate_tuples() -> None:
    parsed = 0
    errors: list[str] = []

    for path in sorted(WORKFLOWS_DIR.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        offset = 0
        for block in text.split("```yaml")[1:]:
            start = text.index("```yaml" + block, offset)
            offset = start + 1
            yaml_text = block.split("```", 1)[0]
            if "child_gate" not in yaml_text:
                continue
            parsed += 1
            try:
                payload = yaml.safe_load(yaml_text)
                if isinstance(payload, dict) and "child_gate" in payload:
                    child_gate_tuple_from_payload(payload)
                if isinstance(payload, dict) and isinstance(payload.get("child_gates"), list):
                    for gate_payload in payload["child_gates"]:
                        child_gate_tuple_from_payload(gate_payload)
            except Exception as exc:  # pragma: no cover - assertion reports exact prompt location
                line = text[:start].count("\n") + 1
                errors.append(f"{path.relative_to(REPO_ROOT)}:{line}: {exc}")

    assert errors == []
    assert parsed >= 20
