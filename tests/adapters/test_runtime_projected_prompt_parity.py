"""Runtime-projected prompt parity for contract-heavy command and agent surfaces."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

import gpd.adapters.gemini as gemini_module
from gpd.adapters import get_adapter
from gpd.adapters.install_utils import (
    DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES,
    build_runtime_cli_bridge_command,
    expand_at_includes,
    project_markdown_for_runtime,
)
from gpd.adapters.runtime_catalog import get_runtime_descriptor, iter_runtime_descriptors
from gpd.core.context import init_execute_phase, init_plan_phase, init_quick, init_verify_work
from gpd.core.model_visible_text import (
    agent_visibility_note,
    review_contract_visibility_note,
)
from gpd.core.workflow_staging import load_workflow_stage_manifest_from_path
from gpd.registry import _frontmatter_parts, _load_frontmatter_mapping, _parse_spawn_contracts
from tests.adapters.projection_test_utils import StagedCommandProjectionCase, iter_staged_command_projection_cases
from tests.prompt_metrics_support import iter_markdown_fences, runtime_command_visibility_note

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = REPO_ROOT / "src/gpd/commands"
AGENTS_DIR = REPO_ROOT / "src/gpd/agents"
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"
TEMPLATES_DIR = REPO_ROOT / "src/gpd/specs/templates"

RUNTIMES = tuple(descriptor.runtime_name for descriptor in iter_runtime_descriptors())
VERIFIER_BUDGET_BY_NATIVE_INCLUDE_SUPPORT = {
    True: (500, 35_000),
    False: (500, 35_000),
}
VERIFIER_SCHEMA_INCLUDE_SUFFIXES = (
    "templates/verification-report.md",
    "templates/contract-results-schema.md",
    "references/shared/canonical-schema-discipline.md",
)
VERIFIER_SCHEMA_AUTHORITY_MARKERS = (
    ("templates/verification-report.md", "# Verification Report Template"),
    ("templates/contract-results-schema.md", "# Contract Results Schema"),
    ("references/shared/canonical-schema-discipline.md", "# Canonical Schema Discipline"),
)
VERIFY_WORK_CONCISE_GUIDANCE_FRAGMENTS = (
    "Every spawned agent is a one-shot delegation",
    "File-producing handoffs must prove the expected artifact exists before success is accepted.",
    "For proof-bearing work, require a canonical `*-PROOF-REDTEAM.md` artifact; if missing/stale/malformed/not `passed`, spawn `gpd-check-proof` once",
    "Route only on canonical verification frontmatter plus `gpd_return.status`",
    "Do not recompute canonical verification status in this workflow.",
    "verification_report_skeleton_bridge",
    "writer_command",
    "write body-only evidence",
    "satisfies bridge `body_contract`",
    "one fenced executed `python`/`bash` block",
    "adjacent `**Output:**` plus fenced `output`",
    "following `PASS`/`FAIL`/`INCONCLUSIVE` verdict",
    "do not hand-author or reflow frontmatter",
)
VERIFY_WORK_FORBIDDEN_SOURCE_COMMAND_PREFIXES = (
    "$gpd-verify-work",
    "/gpd:verify-work",
    "/gpd-verify-work",
    "gpd-verify-work",
)
STAGED_SHIM_SENTINELS = ("<gpd_staged_bootstrap_shim", "## Compact Staged Command Shim")
HELP_BRIDGE_SHIM_SENTINELS = ("<gpd_help_bridge_shim", "CLI-owned compact help surface")
UNRESOLVED_INCLUDE_MARKERS = (
    "@ include not resolved:",
    "@ include cycle detected:",
    "@ include read error:",
    "@ include depth limit reached:",
)
STAGED_SHIM_CONTRACT_FRAGMENTS = (
    "staged_loading",
    "workflow_id",
    "stage_id",
    "order",
    "required_init_fields",
    "mode_paths",
    "loaded_authorities",
    "eager_authorities",
    "conditional_authorities",
    "must_not_eager_load",
    "next_stages",
    "allowed_tools",
    "writes_allowed",
    "produced_state",
    "checkpoints",
)
STAGED_PROJECTED_COMMAND_CHAR_BUDGET = 20_000


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _command_names() -> tuple[str, ...]:
    return tuple(path.stem for path in sorted(COMMANDS_DIR.glob("*.md")))


def _command_frontmatter(command_name: str) -> dict[str, object]:
    frontmatter, _body = _frontmatter_parts(_read(COMMANDS_DIR / f"{command_name}.md"))
    assert frontmatter is not None, f"{command_name} is missing command frontmatter"
    return _load_frontmatter_mapping(frontmatter, error_prefix=f"Malformed frontmatter for {command_name}")


def _contract_bearing_command_surfaces() -> dict[str, tuple[str, ...]]:
    surfaces: dict[str, tuple[str, ...]] = {}
    for command_name in _command_names():
        meta = _command_frontmatter(command_name)
        fragments = []
        review_contract = meta.get("review-contract")
        if isinstance(review_contract, dict):
            fragments.append(review_contract_visibility_note())
            if "required_state" in review_contract:
                fragments.append("required_state:")
        if meta.get("agent") or "review-contract" in meta or "allowed-tools" in meta or "requires" in meta:
            surfaces[command_name] = tuple(fragments)
    return surfaces


def _runtime_expected_fragments(fragments: tuple[str, ...], *, runtime: str) -> tuple[str, ...]:
    if runtime == "codex":
        return tuple(fragment.replace("`gpd:suggest-next`", "`$gpd-suggest-next`") for fragment in fragments)
    if runtime == "opencode":
        # OpenCode adapter rewrites bare `gpd:X` to `gpd-X` in body text;
        # translate expected fragments accordingly.
        import re as _re

        def _rewrite(text: str) -> str:
            return _re.sub(r"(?<![A-Za-z0-9_./:$-])gpd:([a-z][a-z0-9-]*)\b", r"gpd-\1", text)

        return tuple(_rewrite(fragment) for fragment in fragments)
    return fragments


def _spawn_contract_commands() -> tuple[str, ...]:
    return tuple(
        command_name
        for command_name in _command_names()
        if "<spawn_contract>" in _read(COMMANDS_DIR / f"{command_name}.md")
    )


COMMAND_SURFACES = _contract_bearing_command_surfaces()
SPAWN_CONTRACT_COMMANDS = _spawn_contract_commands()
STAGED_COMMAND_PROJECTION_CASES = iter_staged_command_projection_cases(
    commands_dir=COMMANDS_DIR,
    workflows_dir=WORKFLOWS_DIR,
)
PLAN_AGENT_SURFACES = {
    "gpd-planner": (
        agent_visibility_note(),
        "tool_requirements",
        "must_surface",
        "`wolfram` and `command`",
    ),
}
RESULT_AGENT_SURFACES = {
    "gpd-verifier": (
        agent_visibility_note(),
        "templates/contract-results-schema.md",
        "writer_command",
        "skeleton_command",
        "verification_report_skeleton_bridge",
        "gpd frontmatter validate",
        "gpd validate verification-contract",
    ),
    "gpd-executor": (
        agent_visibility_note(),
        "templates/contract-results-schema.md",
        "templates/summary.md",
        "plan_contract_ref",
        "contract_results",
        "comparison_verdicts",
    ),
}
PEER_REVIEW_PUBLICATION_LANE_FRAGMENTS = (
    "Use centralized preflight's selected publication/review roots for GPD-authored review artifacts.",
    "Keep the manuscript and manuscript-local publication manifests rooted at the resolved manuscript directory.",
)
PROTOCOL_BUNDLE_JIT_FIELDS = (
    "selected_protocol_bundle_ids",
    "protocol_bundle_count",
    "protocol_bundle_context",
    "protocol_bundle_verifier_extensions",
)
PROTOCOL_BUNDLE_JIT_COMMANDS = (
    "execute-phase",
    "literature-review",
    "map-research",
    "plan-phase",
    "quick",
    "research-phase",
    "respond-to-referees",
    "verify-work",
    "write-paper",
)
PROTOCOL_BUNDLE_INLINE_CATALOG_MARKERS = (
    "Statistical Mechanics Simulation",
    "Numerical Relativity",
    "{GPD_INSTALL_DIR}/references/protocols/monte-carlo.md",
    "{GPD_INSTALL_DIR}/references/protocols/numerical-relativity.md",
    "Estimator policies:",
    "Decisive artifacts:",
)


def _staged_command_has_protocol_bundle_fields(command_name: str) -> bool:
    if command_name not in PROTOCOL_BUNDLE_JIT_COMMANDS:
        return False
    manifest = load_workflow_stage_manifest_from_path(
        WORKFLOWS_DIR / f"{command_name}-stage-manifest.json",
        expected_workflow_id=command_name,
    )
    return any(
        any(field in stage.required_init_fields for field in PROTOCOL_BUNDLE_JIT_FIELDS) for stage in manifest.stages
    )


def _write_bundle_projection_project(cwd: Path, *, selected: bool) -> None:
    from gpd.core.state import default_state_dict

    gpd_dir = cwd / "GPD"
    phase_dir = gpd_dir / "phases" / "01-setup"
    phase_dir.mkdir(parents=True, exist_ok=True)
    (phase_dir / "01-PLAN.md").write_text("# Plan\n", encoding="utf-8")
    (phase_dir / "01-CONTEXT.md").write_text("# Context\n", encoding="utf-8")
    (gpd_dir / "config.json").write_text("{}", encoding="utf-8")
    (gpd_dir / "STATE.md").write_text("# State\n", encoding="utf-8")
    (gpd_dir / "REQUIREMENTS.md").write_text("# Requirements\n", encoding="utf-8")
    (gpd_dir / "ROADMAP.md").write_text("## Milestone\n\n### Phase 1: Setup\n", encoding="utf-8")
    (gpd_dir / "PROJECT.md").write_text(
        (
            "# Test Project\n\n"
            "## What This Is\n\n"
            "Monte Carlo study of a statistical mechanics lattice model near criticality.\n\n"
            "## Research Context\n\n"
            "### Theoretical Framework\n\n"
            "Statistical mechanics\n\n"
            "### Known Results\n\n"
            "Binder cumulants, thermalization windows, and finite-size scaling should be benchmarked.\n"
        )
        if selected
        else (
            "# Test Project\n\n"
            "## What This Is\n\n"
            "Quantum-gravity saddle bookkeeping with Page-curve comparisons and entropy arguments.\n"
        ),
        encoding="utf-8",
    )

    state = default_state_dict()
    state["project_contract"] = _stat_mech_contract_payload() if selected else _generic_benchmark_contract_payload()
    state["convention_lock"] = {
        "metric_signature": "(-,+,+,+)",
        "fourier_convention": "physics",
        "natural_units": "SI",
    }
    state["intermediate_results"] = [
        {
            "id": "R-01",
            "equation": "E = mc^2",
            "description": "Rest energy",
            "phase": "01",
            "depends_on": [],
            "verified": True,
        }
    ]
    state["approximations"] = [
        {
            "name": "weak coupling",
            "validity_range": "g << 1",
            "controlling_param": "g",
            "current_value": "0.1",
            "status": "valid",
        }
    ]
    state["propagated_uncertainties"] = [
        {
            "quantity": "m_eff",
            "value": "1.2",
            "uncertainty": "0.1",
            "phase": "01",
            "method": "bootstrap",
        }
    ]
    (gpd_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")


def _stat_mech_contract_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "scope": {
            "question": "What finite-size scaling collapse and benchmark comparison does the simulation recover?",
            "in_scope": ["Recover the decisive finite-size scaling benchmark for the simulation regime"],
        },
        "claims": [
            {
                "id": "claim-critical",
                "statement": "Recover benchmark finite-size scaling behavior",
                "deliverables": ["deliv-data", "deliv-figure"],
                "acceptance_tests": ["test-benchmark"],
                "references": ["ref-benchmark"],
            }
        ],
        "deliverables": [
            {
                "id": "deliv-data",
                "kind": "dataset",
                "path": "results/measurements.csv",
                "description": "Raw Monte Carlo measurements with metadata",
            },
            {
                "id": "deliv-figure",
                "kind": "figure",
                "path": "figures/collapse.png",
                "description": "Finite-size scaling collapse figure",
            },
        ],
        "acceptance_tests": [
            {
                "id": "test-benchmark",
                "subject": "claim-critical",
                "kind": "benchmark",
                "procedure": "Compare Binder cumulants and finite-size scaling against literature benchmarks",
                "pass_condition": "Benchmark agreement is within uncertainty",
            }
        ],
        "references": [
            {
                "id": "ref-benchmark",
                "kind": "paper",
                "locator": "Benchmark Monte Carlo paper",
                "role": "benchmark",
                "why_it_matters": "Decisive comparison for the simulation regime",
                "applies_to": ["claim-critical"],
                "must_surface": True,
                "required_actions": ["read", "compare", "cite"],
            }
        ],
        "context_intake": {
            "must_read_refs": ["ref-benchmark"],
        },
        "forbidden_proxies": [
            {
                "id": "fp-proxy",
                "subject": "claim-critical",
                "proxy": "Qualitative agreement without scaling analysis",
                "reason": "Would not validate the decisive benchmarked observable",
            }
        ],
        "uncertainty_markers": {
            "weakest_anchors": ["Autocorrelation estimate near the critical point"],
            "disconfirming_observations": ["Finite-size crossings drift away from the benchmark window"],
        },
    }


def _generic_benchmark_contract_payload() -> dict[str, object]:
    payload = _stat_mech_contract_payload()
    payload["scope"] = {
        "question": "Does the output match a generic benchmark?",
        "in_scope": ["Compare against the generic benchmark"],
    }
    payload["claims"] = [
        {
            "id": "claim-critical",
            "statement": "Recover a generic benchmark value",
            "deliverables": ["deliv-data", "deliv-figure"],
            "acceptance_tests": ["test-benchmark"],
            "references": ["ref-benchmark"],
        }
    ]
    payload["deliverables"] = [
        {
            "id": "deliv-data",
            "kind": "dataset",
            "path": "results/generic-measurements.csv",
            "description": "Generic benchmark measurements with metadata",
        },
        {
            "id": "deliv-figure",
            "kind": "figure",
            "path": "figures/generic-benchmark.png",
            "description": "Generic benchmark comparison figure",
        },
    ]
    payload["acceptance_tests"] = [
        {
            "id": "test-benchmark",
            "subject": "claim-critical",
            "kind": "benchmark",
            "procedure": "Compare against a benchmark reference",
            "pass_condition": "Benchmark agreement is within uncertainty",
        }
    ]
    payload["references"] = [
        {
            "id": "ref-benchmark",
            "kind": "paper",
            "locator": "Generic benchmark paper",
            "role": "benchmark",
            "why_it_matters": "Comparison target",
            "applies_to": ["claim-critical"],
            "must_surface": True,
            "required_actions": ["read", "compare"],
        }
    ]
    payload["forbidden_proxies"] = [
        {
            "id": "fp-proxy",
            "subject": "claim-critical",
            "proxy": "Qualitative trend agreement without the generic benchmark comparison",
            "reason": "Would not validate the decisive benchmarked observable",
        }
    ]
    payload["uncertainty_markers"] = {
        "weakest_anchors": ["Generic benchmark tolerance"],
        "disconfirming_observations": ["Benchmark agreement disappears under direct comparison"],
    }
    return payload


def _project_markdown(path: Path, runtime: str, *, is_agent: bool) -> str:
    return project_markdown_for_runtime(
        _read(path),
        runtime=runtime,
        path_prefix="/runtime/",
        surface_kind="agent" if is_agent else "command",
        src_root=REPO_ROOT / "src/gpd",
        protect_agent_prompt_body=is_agent,
        command_name=path.stem,
    )


def _project_installed_shared_markdown(path: Path, runtime: str) -> str:
    return get_adapter(runtime).translate_shared_markdown(_read(path), "/runtime/", install_scope="--local")


def _bridge_for_projection(runtime: str, target_dir: Path) -> str:
    descriptor = get_runtime_descriptor(runtime)
    return build_runtime_cli_bridge_command(
        runtime,
        target_dir=target_dir,
        config_dir_name=descriptor.config_dir_name,
        is_global=False,
    )


def _project_fixture_command(content: str, runtime: str, target_dir: Path) -> str:
    descriptor = get_runtime_descriptor(runtime)
    return project_markdown_for_runtime(
        content,
        runtime=runtime,
        path_prefix=f"./{descriptor.config_dir_name}/",
        surface_kind="command",
        install_scope="--local",
        workflow_target_dir=target_dir,
        command_name="projection-probe",
    )


def _shell_fence_bodies(text: str) -> tuple[str, ...]:
    return tuple(
        fence.body
        for fence in iter_markdown_fences(text)
        if fence.info.lower() in DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES
    )


def _raw_include_count(text: str, include_suffix: str) -> int:
    return sum(
        1 for line in text.splitlines() if line.strip().startswith("@") and line.strip().endswith(include_suffix)
    )


def _has_compact_non_native_shim(text: str) -> bool:
    return _has_staged_shim_sentinel(text) or _has_help_bridge_shim_sentinel(text)


def _has_staged_shim_sentinel(text: str) -> bool:
    return any(sentinel in text for sentinel in STAGED_SHIM_SENTINELS)


def _has_help_bridge_shim_sentinel(text: str) -> bool:
    return any(sentinel in text for sentinel in HELP_BRIDGE_SHIM_SENTINELS)


def _assert_no_unresolved_include_markers(text: str, *, label: str) -> None:
    lowered = text.lower()
    offenders = [marker for marker in UNRESOLVED_INCLUDE_MARKERS if marker in lowered]
    assert offenders == [], f"{label} contains unresolved include marker(s): {', '.join(offenders)}"


def _workflow_authority_for_shimmed_projection(command_name: str, projected: str, runtime: str) -> str:
    if _has_compact_non_native_shim(projected):
        return projected + "\n" + _project_installed_shared_markdown(WORKFLOWS_DIR / f"{command_name}.md", runtime)
    return projected


def _first_shell_command(body: str) -> str | None:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return None


def _first_shell_commands(text: str) -> tuple[str, ...]:
    return tuple(command for body in _shell_fence_bodies(text) if (command := _first_shell_command(body)))


def _assert_runtime_note_block_count(text: str, tag: str, expected_count: int) -> None:
    assert text.count(f"<{tag}>") == expected_count
    assert text.count(f"</{tag}>") == expected_count


def _single_runtime_note_block(text: str, tag: str) -> str:
    _assert_runtime_note_block_count(text, tag, 1)
    start_marker = f"<{tag}>"
    end_marker = f"</{tag}>"
    start = text.index(start_marker) + len(start_marker)
    end = text.index(end_marker, start)
    return text[start:end].strip()


def _has_line_with_terms(text: str, *terms: str) -> bool:
    folded_terms = tuple(term.casefold() for term in terms)
    return any(all(term in line.casefold() for term in folded_terms) for line in text.splitlines())


def _assert_codex_compact_runtime_note(text: str, bridge: str) -> None:
    block = _single_runtime_note_block(text, "codex_runtime_notes")
    assert "runtime-command-snippets.md#runtime-shell-bridge" in block
    assert bridge in block
    assert _has_line_with_terms(block, "bridge")
    assert "Codex shell compatibility:" not in block
    assert "When shell steps call the GPD CLI" not in block


def _assert_codex_inline_freeform_questioning(text: str) -> None:
    block = _single_runtime_note_block(text, "codex_questioning")
    assert "runtime-command-snippets.md#runtime-questioning" in block
    assert _has_line_with_terms(block, "ask", "once")
    assert "ask_user" not in text.casefold()
    assert _has_line_with_terms(text, "ask", "inline", "freeform")
    assert (
        _has_line_with_terms(text, "one", "inline", "freeform")
        or _has_line_with_terms(text, "single", "inline", "freeform")
        or _has_line_with_terms(text, "exactly", "inline", "freeform")
    )


def _assert_fragments_visible(text: str, fragments: tuple[str, ...], *, label: str) -> None:
    missing = sorted(fragment for fragment in fragments if fragment not in text)
    assert not missing, f"{label} is missing contract-bearing fragments: {', '.join(missing)}"


def _extract_spawn_contracts(text: str) -> list[dict[str, object]]:
    return list(_parse_spawn_contracts(text, owner_name="runtime-projected"))


@pytest.mark.parametrize(
    "case",
    STAGED_COMMAND_PROJECTION_CASES,
    ids=lambda case: case.command_name,
)
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_runtime_projected_staged_commands_use_native_include_or_compact_stage_shim(
    case: StagedCommandProjectionCase,
    runtime: str,
) -> None:
    command_name = case.command_name
    projected = _project_markdown(COMMANDS_DIR / f"{command_name}.md", runtime, is_agent=False)
    descriptor = get_runtime_descriptor(runtime)

    _assert_no_unresolved_include_markers(projected, label=f"{runtime} {command_name}")
    assert get_adapter(runtime).format_command(command_name) in projected

    if descriptor.native_include_support:
        for include_path in case.native_include_paths:
            assert _raw_include_count(projected, include_path) == 1
        assert _raw_include_count(projected, f"workflows/{command_name}-stage-manifest.json") == 0
        assert f"<!-- [included: {command_name}.md] -->" not in projected
        assert not _has_staged_shim_sentinel(projected)
        return

    workflow_source = _read(WORKFLOWS_DIR / f"{command_name}.md")
    expanded_workflow = expand_at_includes(
        workflow_source,
        REPO_ROOT / "src/gpd",
        "/runtime/",
        runtime=runtime,
    )
    init_lines = tuple(line.strip() for line in projected.splitlines() if f"--raw init {command_name}" in line)

    assert _raw_include_count(projected, f"workflows/{command_name}.md") == 0
    assert f"<!-- [included: {command_name}.md] -->" not in projected
    assert _has_staged_shim_sentinel(projected)
    assert not _has_help_bridge_shim_sentinel(projected)
    assert any(f"--stage {case.first_stage_id}" in line for line in init_lines)
    assert f'first_stage="{case.first_stage_id}"' in projected
    for fragment in (*STAGED_SHIM_CONTRACT_FRAGMENTS, *case.staged_loading_keys):
        assert fragment in projected
    assert len(projected) <= STAGED_PROJECTED_COMMAND_CHAR_BUDGET
    assert len(projected) <= len(expanded_workflow) * 0.85


@pytest.mark.parametrize(
    "case",
    STAGED_COMMAND_PROJECTION_CASES,
    ids=lambda case: case.command_name,
)
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_runtime_projected_staged_commands_keep_protocol_bundle_jit_visible_without_catalog_inline(
    case: StagedCommandProjectionCase,
    runtime: str,
) -> None:
    projected = _project_markdown(COMMANDS_DIR / f"{case.command_name}.md", runtime, is_agent=False)
    descriptor = get_runtime_descriptor(runtime)
    has_bundle_fields = _staged_command_has_protocol_bundle_fields(case.command_name)

    if not has_bundle_fields:
        assert "<protocol_bundle_jit>" not in projected
        return

    for marker in PROTOCOL_BUNDLE_INLINE_CATALOG_MARKERS:
        assert marker not in projected

    if descriptor.native_include_support:
        assert _raw_include_count(projected, f"workflows/{case.command_name}.md") == 1
        assert "<protocol_bundle_jit>" not in projected
        return

    assert "<protocol_bundle_jit>" in projected
    assert "use those init payload fields as the selected-bundle loading map" in projected
    assert "load only selected asset paths named by `protocol_bundle_context`" in projected
    assert "do not inline protocol bundle catalogs during bootstrap" in projected
    for field in PROTOCOL_BUNDLE_JIT_FIELDS:
        assert field in projected


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_runtime_projected_help_uses_native_include_or_compact_help_bridge_shim(runtime: str) -> None:
    projected = _project_markdown(COMMANDS_DIR / "help.md", runtime, is_agent=False)
    descriptor = get_runtime_descriptor(runtime)

    _assert_no_unresolved_include_markers(projected, label=f"{runtime} help")
    assert get_adapter(runtime).format_command("help") in projected

    if descriptor.native_include_support:
        assert _raw_include_count(projected, "workflows/help.md") == 1
        assert "<!-- [included: help.md] -->" not in projected
        assert not _has_help_bridge_shim_sentinel(projected)
        return

    assert _raw_include_count(projected, "workflows/help.md") == 0
    assert "<!-- [included: help.md] -->" not in projected
    assert _has_help_bridge_shim_sentinel(projected)
    assert not _has_staged_shim_sentinel(projected)
    assert "<current-help-command>" not in projected
    assert "--raw help" in projected
    assert "--raw help --all" in projected
    assert "--raw help --command <name>" in projected
    assert len(projected) < 10_000


@pytest.mark.parametrize("selected", (True, False), ids=("selected", "absent"))
def test_staged_protocol_bundle_payloads_preserve_selected_vs_absent_context(
    tmp_path: Path,
    selected: bool,
) -> None:
    _write_bundle_projection_project(tmp_path, selected=selected)
    payloads = (
        init_plan_phase(tmp_path, "1", stage="planner_authoring"),
        init_execute_phase(tmp_path, "1", stage="wave_planning"),
        init_verify_work(tmp_path, "1", stage="inventory_build"),
        init_quick(tmp_path, "Benchmark lookup", stage="reference_context"),
    )

    for payload in payloads:
        assert "selected_protocol_bundles" not in payload
        assert "protocol_bundle_asset_paths" not in payload
        if selected:
            assert payload["selected_protocol_bundle_ids"] == ["stat-mech-simulation"]
            assert payload["protocol_bundle_count"] == 1
            assert "Statistical Mechanics Simulation" in payload["protocol_bundle_context"]
            assert "{GPD_INSTALL_DIR}/references/protocols/monte-carlo.md" in payload["protocol_bundle_context"]
            assert "Estimator policies:" in payload["protocol_bundle_context"]
            assert "Decisive artifacts:" in payload["protocol_bundle_context"]
            assert "Numerical Relativity" not in payload["protocol_bundle_context"]
            assert (
                "{GPD_INSTALL_DIR}/references/protocols/numerical-relativity.md"
                not in payload["protocol_bundle_context"]
            )
            assert any(
                extension["bundle_id"] == "stat-mech-simulation"
                for extension in payload["protocol_bundle_verifier_extensions"]
            )
        else:
            assert payload["selected_protocol_bundle_ids"] == []
            assert payload["protocol_bundle_count"] == 0
            assert payload["protocol_bundle_verifier_extensions"] == []
            assert "None selected from project metadata" in payload["protocol_bundle_context"]
            assert "Fall back to shared protocols and on-demand routing." in payload["protocol_bundle_context"]
            for marker in PROTOCOL_BUNDLE_INLINE_CATALOG_MARKERS:
                assert marker not in payload["protocol_bundle_context"]


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize(("command_name", "expected_fragments"), tuple(COMMAND_SURFACES.items()))
def test_runtime_projected_commands_keep_model_visible_contract_wrappers(
    command_name: str, expected_fragments: tuple[str, ...], runtime: str
) -> None:
    projected = _project_markdown(COMMANDS_DIR / f"{command_name}.md", runtime, is_agent=False)

    assert projected.count("## Command Requirements") == 1
    assert runtime_command_visibility_note(runtime) in projected
    for fragment in _runtime_expected_fragments(expected_fragments, runtime=runtime):
        assert fragment in projected, f"{runtime} {command_name} missing {fragment!r}"


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_runtime_projected_peer_review_keeps_publication_lane_boundary_visible(runtime: str) -> None:
    projected = _project_markdown(COMMANDS_DIR / "peer-review.md", runtime, is_agent=False)
    visible_text = _workflow_authority_for_shimmed_projection("peer-review", projected, runtime)

    _assert_fragments_visible(
        visible_text,
        PEER_REVIEW_PUBLICATION_LANE_FRAGMENTS,
        label=f"{runtime} peer-review",
    )


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize(("agent_name", "expected_fragments"), tuple(PLAN_AGENT_SURFACES.items()))
def test_runtime_projected_planner_agent_keeps_plan_contract_guidance_visible(
    agent_name: str,
    expected_fragments: tuple[str, ...],
    runtime: str,
) -> None:
    projected = _project_markdown(AGENTS_DIR / f"{agent_name}.md", runtime, is_agent=True)

    _assert_fragments_visible(projected, expected_fragments, label=f"{runtime} {agent_name}")


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize(("agent_name", "expected_fragments"), tuple(RESULT_AGENT_SURFACES.items()))
def test_runtime_projected_agents_keep_contract_results_guidance_visible(
    agent_name: str,
    expected_fragments: tuple[str, ...],
    runtime: str,
) -> None:
    projected = _project_markdown(AGENTS_DIR / f"{agent_name}.md", runtime, is_agent=True)
    descriptor = get_runtime_descriptor(runtime)

    _assert_fragments_visible(projected, expected_fragments, label=f"{runtime} {agent_name}")
    if agent_name == "gpd-executor":
        validator_text = (
            _project_installed_shared_markdown(TEMPLATES_DIR / "contract-results-schema.md", runtime)
            if descriptor.native_include_support
            else projected
        )
        assert "gpd validate summary-contract" in validator_text


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_runtime_projected_verifier_surface_keeps_one_wrapper_and_stays_within_budget(runtime: str) -> None:
    projected = _project_markdown(AGENTS_DIR / "gpd-verifier.md", runtime, is_agent=True)
    descriptor = get_runtime_descriptor(runtime)
    line_budget, char_budget = VERIFIER_BUDGET_BY_NATIVE_INCLUDE_SUPPORT[descriptor.native_include_support]

    assert projected.count("## Agent Requirements") == 1
    assert projected.index("## Agent Requirements") < projected.index("## Bootstrap Discipline")
    for include_suffix, expanded_heading in VERIFIER_SCHEMA_AUTHORITY_MARKERS:
        assert include_suffix in projected or expanded_heading in projected
    assert len(projected.splitlines()) <= line_budget
    assert len(projected) <= char_budget


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_runtime_projected_verify_work_surface_keeps_concise_guidance_visible(runtime: str) -> None:
    projected = _project_markdown(COMMANDS_DIR / "verify-work.md", runtime, is_agent=False)
    descriptor = get_runtime_descriptor(runtime)
    visible_text = (
        _project_installed_shared_markdown(WORKFLOWS_DIR / "verify-work.md", runtime)
        if descriptor.native_include_support or _has_compact_non_native_shim(projected)
        else projected
    )

    if descriptor.native_include_support:
        assert _raw_include_count(projected, "workflows/verify-work.md") == 1
    _assert_fragments_visible(
        visible_text,
        VERIFY_WORK_CONCISE_GUIDANCE_FRAGMENTS,
        label=f"{runtime} verify-work",
    )


def test_verify_work_sources_keep_canonical_command_labels_before_projection() -> None:
    source_text = "\n".join(
        _read(path)
        for path in (
            COMMANDS_DIR / "verify-work.md",
            WORKFLOWS_DIR / "verify-work.md",
            AGENTS_DIR / "gpd-verifier.md",
        )
    )

    for forbidden in VERIFY_WORK_FORBIDDEN_SOURCE_COMMAND_PREFIXES:
        assert forbidden not in source_text


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("command_name", SPAWN_CONTRACT_COMMANDS)
def test_runtime_projected_spawn_contract_blocks_match_canonical_command_content(
    command_name: str,
    runtime: str,
) -> None:
    projected = _project_markdown(COMMANDS_DIR / f"{command_name}.md", runtime, is_agent=False)
    descriptor = get_runtime_descriptor(runtime)
    projected_contracts = _extract_spawn_contracts(projected)
    source_text = _read(COMMANDS_DIR / f"{command_name}.md")
    expanded_contracts = _extract_spawn_contracts(
        expand_at_includes(
            source_text,
            REPO_ROOT / "src/gpd",
            "/runtime/",
            runtime=runtime,
        )
    )
    source_contracts = _extract_spawn_contracts(source_text)

    if descriptor.native_include_support:
        assert projected_contracts == source_contracts
        if not source_contracts and expanded_contracts:
            assert "@/runtime/get-physics-done/workflows/" in projected
        return

    if _has_staged_shim_sentinel(projected):
        assert projected_contracts == source_contracts
        assert "staged_loading" in projected
        return

    assert projected_contracts == expanded_contracts


def test_codex_projected_command_surface_matches_install_runtime_rewrites(tmp_path: Path) -> None:
    target_dir = tmp_path / ".codex"
    bridge = _bridge_for_projection("codex", target_dir)
    source = (
        "---\n"
        "name: gpd:projection-probe\n"
        "description: Projection probe\n"
        "allowed-tools:\n"
        "  - shell\n"
        "---\n"
        "Ask ONE question inline (freeform, NOT ask_user):\n"
        "\n"
        "```bash\n"
        "gpd --raw init progress --include state,config\n"
        "```\n"
    )

    projected = _project_fixture_command(source, "codex", target_dir)

    _assert_codex_compact_runtime_note(projected, bridge)
    _assert_codex_inline_freeform_questioning(projected)
    assert f"{bridge} --raw init progress --include state,config" in projected


def test_gemini_projected_command_surface_matches_install_runtime_rewrites(tmp_path: Path) -> None:
    target_dir = tmp_path / ".gemini"
    bridge = _bridge_for_projection("gemini", target_dir)
    source = (
        "---\n"
        "name: gpd:projection-probe\n"
        "description: Projection probe\n"
        "allowed-tools:\n"
        "  - shell\n"
        "---\n"
        "```bash\n"
        "gpd config ensure-section\n"
        "INIT=$(gpd --raw init progress --include state,config)\n"
        "if [ $? -ne 0 ]; then\n"
        '  echo "ERROR: gpd initialization failed: $INIT"\n'
        '  echo "$INIT"\n'
        "  # STOP \u2014 display the error to the user and do not proceed.\n"
        "fi\n"
        "```\n"
    )

    projected = _project_fixture_command(source, "gemini", target_dir)

    _assert_runtime_note_block_count(projected, "gemini_runtime_notes", 1)
    _assert_runtime_note_block_count(projected, "gemini_shell_runtime_notes", 1)
    shell_text = "\n".join(_shell_fence_bodies(projected))
    assert _first_shell_commands(projected) == (
        f"{bridge} config ensure-section",
        f'{bridge} config set model_profile "$PROFILE"',
    )
    assert f"{bridge} --raw init progress --include state,config" not in shell_text
    assert "INIT=$(gpd --raw init progress --include state,config)" not in projected
    assert 'echo "$INIT"' not in projected


def test_gemini_projected_shell_allowlist_matches_policy_prefixes(tmp_path: Path) -> None:
    target_dir = tmp_path / ".gemini"
    bridge = _bridge_for_projection("gemini", target_dir)
    source = (
        "---\n"
        "name: gpd:projection-probe\n"
        "description: Projection probe\n"
        "allowed-tools:\n"
        "  - shell\n"
        "---\n"
        "Runnable contract persistence must be file-backed in Gemini:\n"
        "\n"
        "```bash\n"
        "printf '%s\\n' \"$PROJECT_CONTRACT_JSON\" | gpd --raw validate project-contract - --mode approved\n"
        "```\n"
        "\n"
        "```bash\n"
        "git init\n"
        "```\n"
        "\n"
        "```bash\n"
        "mkdir -p GPD\n"
        "```\n"
        "\n"
        "Non-runnable contract-variable shorthand, for explanation only:\n"
        "\n"
        "```text\n"
        "PROJECT_CONTRACT_JSON={...}\n"
        "printf '%s\\n' \"$PROJECT_CONTRACT_JSON\"\n"
        "```\n"
    )

    projected = _project_fixture_command(source, "gemini", target_dir)
    policy_prefixes = tuple(tomllib.loads(gemini_module._render_gemini_policy_toml(bridge))["rule"][0]["commandPrefix"])

    assert policy_prefixes == gemini_module._gemini_policy_command_prefixes(bridge)
    for prefix in policy_prefixes:
        assert f"  - `{prefix}`" in projected
    assert all("PROJECT_CONTRACT_JSON" not in prefix for prefix in policy_prefixes)
    assert all(not prefix.startswith("printf") for prefix in policy_prefixes)

    shell_bodies = _shell_fence_bodies(projected)
    assert shell_bodies
    first_commands = _first_shell_commands(projected)
    assert first_commands == (
        f"{bridge} --raw validate project-contract GPD/.approved-project-contract.json --mode approved",
        "git init",
        "mkdir -p GPD",
    )
    assert all(command.startswith(policy_prefixes) for command in first_commands)
    assert "PROJECT_CONTRACT_JSON" not in "\n".join(shell_bodies)
    assert "printf '%s\\n'" not in "\n".join(shell_bodies)
    assert "```text\nPROJECT_CONTRACT_JSON={...}" in projected


def test_gemini_real_command_shell_fences_start_with_policy_prefixes(tmp_path: Path) -> None:
    target_dir = tmp_path / ".gemini"
    bridge = _bridge_for_projection("gemini", target_dir)
    policy_prefixes = gemini_module._gemini_policy_command_prefixes(bridge)
    offenders: list[str] = []

    for command_name in _command_names():
        projected = project_markdown_for_runtime(
            _read(COMMANDS_DIR / f"{command_name}.md"),
            runtime="gemini",
            path_prefix="./.gemini/",
            surface_kind="command",
            install_scope="--local",
            workflow_target_dir=target_dir,
            command_name=command_name,
        )
        for body in _shell_fence_bodies(projected):
            first_command = _first_shell_command(body)
            if first_command and not first_command.startswith(policy_prefixes):
                offenders.append(f"{command_name}: {first_command}")

    assert offenders == []


@pytest.mark.parametrize("runtime", ("claude-code", "opencode"))
def test_projected_command_surfaces_rewrite_fenced_cli_invocations_to_runtime_bridge(
    runtime: str,
    tmp_path: Path,
) -> None:
    descriptor = get_runtime_descriptor(runtime)
    target_dir = tmp_path / descriptor.config_dir_name
    bridge = _bridge_for_projection(runtime, target_dir)
    source = (
        "---\n"
        "name: gpd:projection-probe\n"
        "description: Projection probe\n"
        "allowed-tools:\n"
        "  - shell\n"
        "---\n"
        "Inline `gpd --raw init progress` stays prose.\n"
        "\n"
        "```bash\n"
        "gpd --raw init progress --include state,config\n"
        "```\n"
    )

    projected = _project_fixture_command(source, runtime, target_dir)

    assert f"{bridge} --raw init progress --include state,config" in projected
    assert "Inline `gpd --raw init progress` stays prose." in projected


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_projected_command_surfaces_rewrite_tilde_fenced_cli_invocations_to_runtime_bridge(
    runtime: str,
    tmp_path: Path,
) -> None:
    descriptor = get_runtime_descriptor(runtime)
    target_dir = tmp_path / descriptor.config_dir_name
    bridge = _bridge_for_projection(runtime, target_dir)
    source = (
        "---\n"
        "name: gpd:projection-probe\n"
        "description: Projection probe\n"
        "allowed-tools:\n"
        "  - shell\n"
        "---\n"
        "Inline `gpd status` stays prose.\n"
        "\n"
        "~~~bash\n"
        "gpd --raw init progress --include state,config\n"
        "~~~\n"
    )

    projected = _project_fixture_command(source, runtime, target_dir)

    assert f"{bridge} --raw init progress --include state,config" in projected
    assert "Inline `gpd status` stays prose." in projected
