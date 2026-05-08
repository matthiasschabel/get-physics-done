"""Runtime-projected prompt parity for contract-heavy command and agent surfaces."""

from __future__ import annotations

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
from gpd.core.model_visible_text import (
    agent_visibility_note,
    review_contract_visibility_note,
)
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
    True: (900, 60_000),
    False: (6_500, 430_000),
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
    "Route only on the canonical verification frontmatter and `gpd_return.status`",
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
