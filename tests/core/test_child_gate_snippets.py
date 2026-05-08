"""Focused tests for compact child gate snippet rendering."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from gpd.core.child_gate_snippets import (
    CHILD_GATE_SNIPPET_IDS,
    ChildGateApplicator,
    ChildGateArtifact,
    ChildGateFreshness,
    ChildGateTuple,
    child_gate_snippet_ids,
    child_gate_tuple_from_payload,
    render_child_gate_prompt_block,
    render_child_gate_snippet,
    render_child_gate_snippets,
    render_child_gate_tuple,
)
from gpd.core.handoff_artifacts import HandoffFailureClass
from gpd.core.return_skeleton import GPD_RETURN_ROLE_PROFILES

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


def test_child_gate_tuple_renders_compact_yaml_with_inferred_return_profile() -> None:
    rendered = render_child_gate_tuple(_planner_gate())

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
                "write_allowlist": ["${PAPER_DIR}/intro.tex"],
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


def test_child_gate_tuple_rejects_unknown_profile_status_and_invalid_freshness() -> None:
    with pytest.raises(ValueError, match="unknown gpd_return role profile"):
        ChildGateTuple(id="bad", role="gpd-unknown", required_status="completed")

    with pytest.raises(ValueError, match="unknown gpd_return status"):
        ChildGateTuple(id="bad", role="gpd-planner", required_status="done")

    with pytest.raises(ValueError, match="freshness marker is required"):
        ChildGateFreshness(require_mtime_at_or_after_marker=True)


def test_return_profile_snippet_sources_profile_fields_from_return_skeleton() -> None:
    rendered = render_child_gate_snippet("return_profile", role="gpd-planner", status="completed")

    assert "`gpd return skeleton --role planner --status completed`" in rendered
    assert "`return_contract.py` validates" in rendered
    for field_name in GPD_RETURN_ROLE_PROFILES["planner"].role_fields_by_status["completed"]:
        if field_name in {"phase", "plans_created", "waves"}:
            assert f"`{field_name}`" in rendered


def test_static_snippets_render_short_authority_pointers_and_failure_classes() -> None:
    assert child_gate_snippet_ids() == CHILD_GATE_SNIPPET_IDS

    snippets = {snippet_id: render_child_gate_snippet(snippet_id) for snippet_id in CHILD_GATE_SNIPPET_IDS}

    assert "gpd return skeleton --role <role> --status <status>" in snippets["return_profile"]
    assert "references/orchestration/child-artifact-gate.md" in snippets["child_artifact_gate"]
    assert "references/orchestration/continuation-boundary.md" in snippets["continuation_boundary"]
    assert "references/verification/verification-status-authority.md" in snippets["verification_status_authority"]
    assert "verification report frontmatter `status`" in snippets["verification_status_authority"]
    assert "Prose is not authority" in snippets["prose_is_not_authority"]

    for failure_class in HandoffFailureClass:
        assert f"`{failure_class.value}`" in snippets["child_artifact_gate"]

    assert all(len(snippet.splitlines()) <= 2 for snippet in snippets.values())


def test_render_child_gate_snippets_and_prompt_block_are_deterministic() -> None:
    gate = _planner_gate()

    rendered = render_child_gate_snippets(("child_artifact_gate", "prose_is_not_authority"))
    prompt_block = render_child_gate_prompt_block(gate)

    assert rendered == render_child_gate_snippets(("child_artifact_gate", "prose_is_not_authority"))
    assert prompt_block == render_child_gate_prompt_block(gate)
    assert "Child artifact gate:" in prompt_block
    assert "Continuation boundary:" in prompt_block
    assert "Prose is not authority:" in prompt_block
    assert "child_gate:" in prompt_block
    assert "planner_initial_plan" in prompt_block


def test_unknown_snippet_id_fails_closed() -> None:
    with pytest.raises(ValueError, match="unknown child gate snippet id"):
        render_child_gate_snippet("artifact_gate")


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
