from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace

import tests.ci_sharding as ci_sharding
from gpd.adapters.runtime_catalog import iter_runtime_descriptors
from tests.ci_sharding import assert_ci_workflow_pytest_shard_policy, assert_tests_readme_documents_ci_shard_policy
from tests.helpers.github_actions import (
    github_actions_workflow_paths,
    iter_workflow_steps,
    load_github_actions_workflow,
    load_repo_github_actions_workflow,
    workflow_job,
    workflow_job_steps,
    workflow_jobs,
    workflow_step_by_name,
    workflow_steps_using,
)
from tests.helpers.release import assert_run_step_uses_isolated_uv_build_env, assert_setup_uv_step_pins_expected_version

REPO_ROOT = Path(__file__).resolve().parent.parent


def _workflow_paths() -> list[Path]:
    return github_actions_workflow_paths(REPO_ROOT)


def _workflow_data() -> dict[str, object]:
    return load_repo_github_actions_workflow(REPO_ROOT, "test.yml")


_PR_CI_TRIGGER_NAMES = {"pull_request", "push", "workflow_run"}
_LIVE_PROVIDER_PR_CI_MARKERS = (
    "phase8-live-providers",
    "phase8_live_provider_matrix.py",
    "provider_set",
    "phase8-provider-smoke",
    "GEMINI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
)
_PHASE0_BASELINE_HELPER_MARKERS = (
    "scripts/phase0_baseline_report.py",
    "phase0_baseline_report.py",
    "phase0-baseline-report",
)
_DEFAULT_PROVIDER_FREE_WORKFLOWS = ("test.yml", "release.yml", "publish-release.yml")
_PROVIDER_SECRET_MARKERS = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "CLAUDE_API_KEY",
        "CODEX_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "OPENCODE_API_KEY",
    }
)
_PACKAGE_PUBLISH_TOKEN_MARKERS = frozenset(
    {
        "NODE_AUTH_TOKEN",
        "NPM_TOKEN",
        "PYPI_API_TOKEN",
        "PYPI_TOKEN",
        "TWINE_PASSWORD",
        "TWINE_USERNAME",
    }
)
_ALLOWED_WORKFLOW_SECRET_REFS = {
    "phase8-live-provider-matrix.yml": frozenset(),
    "publish-release.yml": frozenset({"GITHUB_TOKEN", "GPD_WEB_DISPATCH_TOKEN"}),
    "release.yml": frozenset({"GITHUB_TOKEN"}),
    "staging-rebuild.yml": frozenset({"GPD_WEB_DISPATCH_TOKEN"}),
    "test.yml": frozenset(),
}
_SECRET_REF_RE = re.compile(r"\${{\s*secrets\.([A-Za-z_][A-Za-z0-9_]*)\s*}}")
_RAW_PROVIDER_ARTIFACT_MARKERS = ("raw", "stdout", "stderr", "transcript")


def _workflow_run_scripts(workflow: dict[str, object]) -> str:
    return "\n".join(str(step.get("run", "")) for _, step in iter_workflow_steps(workflow))


def _workflow_string_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        strings: list[str] = []
        for key, item in value.items():
            if isinstance(key, str):
                strings.append(key)
            strings.extend(_workflow_string_values(item))
        return strings
    if isinstance(value, list):
        strings = []
        for item in value:
            strings.extend(_workflow_string_values(item))
        return strings
    return []


def _workflow_string_surface(workflow: dict[str, object]) -> str:
    return "\n".join(_workflow_string_values(workflow))


def _workflow_secret_refs(workflow: dict[str, object]) -> set[str]:
    return set(_SECRET_REF_RE.findall(_workflow_string_surface(workflow)))


def _provider_launch_command_re() -> re.Pattern[str]:
    provider_commands = {descriptor.launch_command for descriptor in iter_runtime_descriptors()}
    return re.compile(rf"(?m)(?<![-./\w])(?:{'|'.join(sorted(provider_commands))})(?:\s|$)")


def test_all_github_workflows_parse_with_github_actions_shape() -> None:
    workflow_paths = _workflow_paths()

    assert {path.name for path in workflow_paths} == {
        "phase8-live-provider-matrix.yml",
        "publish-release.yml",
        "release.yml",
        "staging-rebuild.yml",
        "test.yml",
    }

    for path in workflow_paths:
        workflow = load_github_actions_workflow(path)

        assert isinstance(workflow.get("name"), str), f"{path} must define a workflow name"
        assert isinstance(workflow.get("on"), dict), f"{path} must define GitHub Actions triggers under `on`"
        assert isinstance(workflow.get("permissions"), dict), f"{path} must define explicit permissions"

        jobs = workflow_jobs(workflow)
        assert jobs, f"{path} must define at least one job"
        for job_id, job in jobs.items():
            assert isinstance(job_id, str) and job_id, f"{path} has an invalid job id"
            assert isinstance(job, dict), f"{path}:{job_id} must be a mapping"
            assert "runs-on" in job or "uses" in job, f"{path}:{job_id} must be a normal or reusable job"
            steps = job.get("steps")
            if steps is None:
                continue
            assert isinstance(steps, list) and steps, f"{path}:{job_id} steps must be a nonempty list"
            for index, step in enumerate(steps):
                assert isinstance(step, dict), f"{path}:{job_id} step {index} must be a mapping"
                assert "run" in step or "uses" in step, f"{path}:{job_id} step {index} needs `run` or `uses`"


def test_github_actions_loader_preserves_on_key_without_losing_boolean_inputs() -> None:
    workflow = load_repo_github_actions_workflow(REPO_ROOT, "release.yml")
    dry_run = workflow["on"]["workflow_dispatch"]["inputs"]["dry_run"]

    assert "on" in workflow
    assert True not in workflow
    assert dry_run["type"] == "boolean"
    assert dry_run["default"] is False


def test_phase8_live_provider_workflow_is_manual_or_nightly_and_sanitized_only() -> None:
    workflow = load_repo_github_actions_workflow(REPO_ROOT, "phase8-live-provider-matrix.yml")
    triggers = workflow["on"]

    assert set(triggers) == {"workflow_dispatch", "schedule"}
    assert "pull_request" not in triggers
    assert "push" not in triggers
    assert "workflow_run" not in triggers
    assert triggers["schedule"] == [{"cron": "17 8 * * *"}]

    dispatch_inputs = triggers["workflow_dispatch"]["inputs"]
    assert set(dispatch_inputs) == {
        "source_ref",
        "provider_set",
        "matrix_mode",
        "scenario_set_id",
        "row_set_hash",
        "budget_id",
        "max_attempts",
        "max_mutating_rows",
        "dry_run",
    }
    assert dispatch_inputs["provider_set"]["default"] == "metadata-only"
    assert dispatch_inputs["provider_set"]["type"] == "string"
    assert dispatch_inputs["matrix_mode"]["default"] == "smoke"
    assert dispatch_inputs["scenario_set_id"]["default"] == "phase8-smoke"
    assert dispatch_inputs["budget_id"]["default"] == "dry-run-only"
    assert dispatch_inputs["max_attempts"]["default"] == 1
    assert dispatch_inputs["max_mutating_rows"]["default"] == 0
    assert dispatch_inputs["dry_run"]["type"] == "boolean"
    assert dispatch_inputs["dry_run"]["default"] is True

    job = workflow_job(workflow, "phase8-live-provider-matrix")
    assert job["environment"] == {"name": "phase8-live-providers"}
    effective_permissions = job.get("permissions", workflow["permissions"])
    assert effective_permissions == {"contents": "read"}

    run_commands = "\n".join(str(step.get("run", "")) for _, step in iter_workflow_steps(workflow))
    assert "uv run pytest" not in run_commands
    assert " pytest" not in run_commands
    assert "GEMINI_API_KEY" not in run_commands
    assert "ANTHROPIC_API_KEY" not in run_commands
    assert "OPENAI_API_KEY" not in run_commands
    assert "Phase 8 live-provider launch is not wired in this skeleton" in run_commands

    upload_steps = workflow_steps_using(workflow, "actions/upload-artifact@v7")
    assert len(upload_steps) == 1
    upload_step = upload_steps[0][1]
    assert upload_step["with"]["name"] == "phase8-sanitized-provider-report"
    upload_path = upload_step["with"]["path"]
    assert "phase8-sanitized-report/phase8-provider-smoke-report.json" in upload_path
    assert "phase8-sanitized-report/phase8-provider-smoke-summary.md" in upload_path
    assert all(forbidden not in upload_path.lower() for forbidden in ("raw", "stdout", "stderr", "transcript"))


def test_default_ci_workflow_has_no_live_provider_credentials_or_phase8_launch_path() -> None:
    workflow = _workflow_data()
    workflow_text = (REPO_ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")

    assert "phase8-live-provider-matrix" not in workflow_text
    assert "phase8-live-providers" not in workflow_text
    for secret_name in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        assert secret_name not in workflow_text

    run_commands = _workflow_run_scripts(workflow)
    assert "provider_set" not in run_commands
    assert "phase8-provider-smoke" not in run_commands


def test_default_ci_and_release_workflows_do_not_launch_provider_clis() -> None:
    provider_command_re = _provider_launch_command_re()

    offenders: list[str] = []
    for workflow_name in _DEFAULT_PROVIDER_FREE_WORKFLOWS:
        workflow = load_repo_github_actions_workflow(REPO_ROOT, workflow_name)
        run_scripts = _workflow_run_scripts(workflow)
        for marker in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
            if marker in run_scripts:
                offenders.append(f"{workflow_name}: provider secret {marker}")
        match = provider_command_re.search(run_scripts)
        if match is not None:
            offenders.append(f"{workflow_name}: provider launch command {match.group(0).strip()!r}")

    assert offenders == []


def test_workflow_secret_references_are_explicitly_allowlisted() -> None:
    offenders: list[str] = []

    for path in _workflow_paths():
        workflow = load_github_actions_workflow(path)
        secret_refs = _workflow_secret_refs(workflow)
        allowed_refs = set(_ALLOWED_WORKFLOW_SECRET_REFS[path.name])
        unexpected_refs = secret_refs - allowed_refs
        missing_refs = allowed_refs - secret_refs

        if unexpected_refs:
            offenders.append(f"{path.name}: unexpected secrets {sorted(unexpected_refs)}")
        if missing_refs:
            offenders.append(f"{path.name}: missing expected secrets {sorted(missing_refs)}")
        forbidden_refs = secret_refs & (_PROVIDER_SECRET_MARKERS | _PACKAGE_PUBLISH_TOKEN_MARKERS)
        if forbidden_refs:
            offenders.append(f"{path.name}: forbidden provider/package token refs {sorted(forbidden_refs)}")

    assert offenders == []


def test_release_and_publish_workflows_do_not_reference_provider_secrets_or_launch_provider_clis() -> None:
    provider_command_re = _provider_launch_command_re()
    offenders: list[str] = []

    for workflow_name in ("release.yml", "publish-release.yml"):
        workflow = load_repo_github_actions_workflow(REPO_ROOT, workflow_name)
        string_surface = _workflow_string_surface(workflow)
        run_scripts = _workflow_run_scripts(workflow)

        for marker in sorted(_PROVIDER_SECRET_MARKERS | _PACKAGE_PUBLISH_TOKEN_MARKERS):
            if marker in string_surface:
                offenders.append(f"{workflow_name}: forbidden secret/token marker {marker}")

        match = provider_command_re.search(run_scripts)
        if match is not None:
            offenders.append(f"{workflow_name}: provider launch command {match.group(0).strip()!r}")

        for launch_path in ("scripts/phase8_live_provider_matrix.py", "phase8_live_provider_matrix.py"):
            if launch_path in run_scripts:
                offenders.append(f"{workflow_name}: Phase 8 launch path {launch_path}")

        if "phase8-live-providers" in string_surface:
            offenders.append(f"{workflow_name}: references live-provider environment")

    assert offenders == []


def test_publish_release_phase8_smoke_gate_consumes_sanitized_artifact_only() -> None:
    workflow = load_repo_github_actions_workflow(REPO_ROOT, "publish-release.yml")
    validate_step = workflow_step_by_name(
        workflow,
        "build-release",
        "Validate sanitized Phase 8 smoke report if required",
    )

    assert validate_step["env"] == {
        "GH_TOKEN": "${{ github.token }}",
        "RELEASE_SHA": "${{ steps.release_sha.outputs.sha }}",
        "REQUIRE_PHASE8_SMOKE": "${{ inputs.require_phase8_smoke }}",
        "PHASE8_SMOKE_RUN_ID": "${{ inputs.phase8_smoke_run_id }}",
        "PHASE8_SMOKE_ARTIFACT_NAME": "${{ inputs.phase8_smoke_artifact_name }}",
        "PHASE8_SMOKE_MAX_PROVIDER_ATTEMPTS": "${{ inputs.phase8_smoke_max_provider_attempts }}",
        "PHASE8_SMOKE_MAX_MUTATING_ROWS": "${{ inputs.phase8_smoke_max_mutating_rows }}",
    }

    run_command = validate_step["run"]
    assert 'REPORT_DIR="$(mktemp -d)"' in run_command
    assert 'gh run download "$PHASE8_SMOKE_RUN_ID"' in run_command
    assert '--name "$PHASE8_SMOKE_ARTIFACT_NAME"' in run_command
    assert '--dir "$REPORT_DIR"' in run_command
    assert "find \"$REPORT_DIR\" -type f -name 'phase8-provider-smoke-report.json' | sort" in run_command
    assert "-name '*.json'" not in run_command
    assert "Downloaded Phase 8 smoke artifact did not contain phase8-provider-smoke-report.json." in run_command
    assert (
        "Downloaded Phase 8 smoke artifact contained multiple phase8-provider-smoke-report.json files." in run_command
    )
    assert "uv run python scripts/validate_phase8_provider_report.py \\" in run_command
    assert '--input "$REPORT_PATH"' in run_command
    assert "--require-smoke" in run_command
    assert '--expected-repo-head "$RELEASE_SHA"' in run_command
    assert '--max-provider-attempts "$PHASE8_SMOKE_MAX_PROVIDER_ATTEMPTS"' in run_command
    assert '--max-mutating-rows "$PHASE8_SMOKE_MAX_MUTATING_ROWS"' in run_command
    assert "scripts/phase8_live_provider_matrix.py" not in run_command
    assert _provider_launch_command_re().search(run_command) is None
    assert all(marker not in run_command.lower() for marker in _RAW_PROVIDER_ARTIFACT_MARKERS)

    build_steps = workflow_job_steps(workflow, "build-release")
    step_names = [str(step.get("name", "")) for step in build_steps]
    assert step_names.index("Validate sanitized Phase 8 smoke report if required") < step_names.index(
        "Run release validation suite"
    )
    assert step_names.index("Validate sanitized Phase 8 smoke report if required") < step_names.index(
        "Build Python distributions"
    )


def test_publish_pypi_job_publishes_downloaded_distribution_artifacts_only() -> None:
    workflow = load_repo_github_actions_workflow(REPO_ROOT, "publish-release.yml")
    publish_job = workflow_job(workflow, "publish-pypi")

    assert publish_job["needs"] == "build-release"
    assert publish_job["environment"] == {
        "name": "PyPI",
        "url": "https://pypi.org/p/get-physics-done",
    }
    assert publish_job["permissions"] == {"contents": "read", "id-token": "write"}

    download_step = workflow_step_by_name(workflow, "publish-pypi", "Download Python distributions")
    assert download_step["uses"] == "actions/download-artifact@v8"
    assert download_step["with"] == {"name": "python-dists", "path": "dist"}

    publish_step = workflow_step_by_name(workflow, "publish-pypi", "Publish package distributions to PyPI")
    assert publish_step["uses"] == "pypa/gh-action-pypi-publish@release/v1"
    assert publish_step["with"] == {"packages-dir": "dist", "skip-existing": True}

    publish_run_scripts = "\n".join(str(step.get("run", "")) for step in workflow_job_steps(workflow, "publish-pypi"))
    for forbidden in ("uv build", "npm publish", "npm pack", "twine upload"):
        assert forbidden not in publish_run_scripts
    for marker in sorted(_PROVIDER_SECRET_MARKERS | _PACKAGE_PUBLISH_TOKEN_MARKERS):
        assert marker not in _workflow_string_surface(publish_job)
    assert _provider_launch_command_re().search(publish_run_scripts) is None


def test_pr_triggered_workflows_do_not_define_live_provider_or_phase0_provider_lanes() -> None:
    offenders: list[str] = []
    phase0_provider_offenders: list[str] = []

    for path in _workflow_paths():
        workflow = load_github_actions_workflow(path)
        triggers = set(workflow["on"])
        if not triggers & _PR_CI_TRIGGER_NAMES:
            continue

        workflow_text = path.read_text(encoding="utf-8")
        for marker in _LIVE_PROVIDER_PR_CI_MARKERS:
            if marker in workflow_text:
                offenders.append(f"{path.name}: {marker}")

        if any(marker in workflow_text for marker in _PHASE0_BASELINE_HELPER_MARKERS):
            for marker in _LIVE_PROVIDER_PR_CI_MARKERS:
                if marker in workflow_text:
                    phase0_provider_offenders.append(f"{path.name}: {marker}")

    assert offenders == []
    assert phase0_provider_offenders == []


def test_ci_workflow_runs_human_author_check_on_pull_requests_and_main_pushes() -> None:
    workflow = _workflow_data()
    triggers = workflow["on"]
    human_author_job = workflow_job(workflow, "human-authors")

    assert triggers["pull_request"]["branches"] == ["main"]
    assert triggers["push"]["branches"] == ["main"]
    assert human_author_job["if"] == "github.event_name == 'pull_request' || github.event_name == 'push'"

    checkout_step = workflow_step_by_name(workflow, "human-authors", "Check out repository")
    assert checkout_step["uses"] == "actions/checkout@v6"
    assert checkout_step["with"]["fetch-depth"] == 0

    pr_step = workflow_step_by_name(workflow, "human-authors", "Check PR commit attribution uses human authors")
    assert pr_step["if"] == "github.event_name == 'pull_request'"
    assert pr_step["run"].strip() == 'bash scripts/check-human-authors.sh --range "origin/${{ github.base_ref }}..HEAD"'

    push_step = workflow_step_by_name(workflow, "human-authors", "Check pushed commit attribution uses human authors")
    assert push_step["if"] == "github.event_name == 'push'"
    assert push_step["env"] == {
        "BEFORE_SHA": "${{ github.event.before }}",
        "HEAD_SHA": "${{ github.sha }}",
    }
    assert 'range="${BEFORE_SHA}..${HEAD_SHA}"' in push_step["run"]
    assert 'bash scripts/check-human-authors.sh --range "$range"' in push_step["run"]


def test_ci_workflow_runs_category_named_runtime_informed_pytest_shards_with_default_parallelism_and_ci_worksteal() -> (
    None
):
    workflow = _workflow_data()
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert_ci_workflow_pytest_shard_policy(workflow, pyproject_text=pyproject)


def test_ci_collection_cache_is_repo_and_category_scoped(tmp_path, monkeypatch) -> None:
    calls: list[tuple[tuple[str, ...], Path]] = []

    def _fake_checked_in_test_relpaths(
        *, repo_root: Path | None = None, category: str | None = None
    ) -> tuple[str, ...]:
        if category == "core":
            return ("core/test_sample.py",)
        return ("test_sample.py",)

    def _fake_run(args: list[str], **kwargs: object) -> SimpleNamespace:
        cwd = kwargs["cwd"]
        assert isinstance(cwd, Path)
        calls.append((tuple(args), cwd))
        if "tests/core/test_sample.py" in args:
            stdout = "tests/core/test_sample.py::test_core\n"
        else:
            stdout = "tests/test_sample.py::test_root\n"
        return SimpleNamespace(stdout=stdout)

    monkeypatch.setattr(ci_sharding, "checked_in_test_relpaths", _fake_checked_in_test_relpaths)
    monkeypatch.setattr(ci_sharding.subprocess, "run", _fake_run)
    ci_sharding._collected_test_inventory_items.cache_clear()
    try:
        first_root = ci_sharding.collected_test_inventory(repo_root=tmp_path, category="root")
        second_root = ci_sharding.collected_test_inventory(repo_root=tmp_path, category="root")
        core = ci_sharding.collected_test_inventory(repo_root=tmp_path, category="core")
        other_root = ci_sharding.collected_test_inventory(repo_root=tmp_path / "other", category="root")
    finally:
        ci_sharding._collected_test_inventory_items.cache_clear()

    assert first_root == second_root == {"test_sample.py": ("tests/test_sample.py::test_root",)}
    assert core == {"core/test_sample.py": ("tests/core/test_sample.py::test_core",)}
    assert other_root == first_root
    assert calls == [
        (
            (
                sys.executable,
                "-m",
                "pytest",
                "-p",
                "no:cacheprovider",
                "tests/test_sample.py",
                "--collect-only",
                "-q",
                "-n",
                "0",
            ),
            tmp_path.resolve(),
        ),
        (
            (
                sys.executable,
                "-m",
                "pytest",
                "-p",
                "no:cacheprovider",
                "tests/core/test_sample.py",
                "--collect-only",
                "-q",
                "-n",
                "0",
            ),
            tmp_path.resolve(),
        ),
        (
            (
                sys.executable,
                "-m",
                "pytest",
                "-p",
                "no:cacheprovider",
                "tests/test_sample.py",
                "--collect-only",
                "-q",
                "-n",
                "0",
            ),
            (tmp_path / "other").resolve(),
        ),
    ]


def test_ci_represents_documented_default_full_suite_without_duplicate_full_suite_lane() -> None:
    workflow = _workflow_data()
    run_pytest_shard = workflow_step_by_name(workflow, "pytest", "Run pytest shard")
    env = run_pytest_shard["env"]
    run_command = run_pytest_shard["run"]

    assert env["GPD_DEFAULT_FULL_SUITE_COMMAND"] == "uv run pytest tests/ -q"
    assert int(env["GPD_FULL_SUITE_SHARD_BUDGET_SECONDS"]) <= 180
    assert 'timeout "${GPD_FULL_SUITE_SHARD_BUDGET_SECONDS}s" uv run pytest -q' in run_command
    assert "${PYTEST_TARGETS[@]}" in run_command

    direct_default_suite_pattern = re.compile(r"(?m)^\s*(?:timeout\s+[^\n]+\s+)?uv run pytest tests/ -q\b")
    assert direct_default_suite_pattern.search("uv run pytest tests/ -q")
    assert direct_default_suite_pattern.search("timeout 180s uv run pytest tests/ -q --durations=20")

    direct_default_suite_steps = [
        f"{job_id}:{step.get('name', '<unnamed>')}"
        for job_id, step in iter_workflow_steps(workflow)
        if direct_default_suite_pattern.search(step.get("run", ""))
    ]

    assert direct_default_suite_steps == []


def test_ci_workflow_runs_lightweight_python_compatibility_matrix() -> None:
    workflow = _workflow_data()
    compat_job = workflow_job(workflow, "python-compatibility")

    assert compat_job["name"] == "python compatibility (${{ matrix.python-version }})"
    assert compat_job["runs-on"] == "ubuntu-latest"
    assert compat_job["strategy"]["fail-fast"] is False
    assert compat_job["strategy"]["matrix"]["python-version"] == ["3.12", "3.13"]
    checkout_step = workflow_step_by_name(workflow, "python-compatibility", "Check out repository")
    python_step = workflow_step_by_name(workflow, "python-compatibility", "Set up Python")
    node_step = workflow_step_by_name(workflow, "python-compatibility", "Set up Node.js")
    uv_step = workflow_step_by_name(workflow, "python-compatibility", "Set up uv")
    install_step = workflow_step_by_name(workflow, "python-compatibility", "Install dependencies")
    build_step = workflow_step_by_name(workflow, "python-compatibility", "Build wheel")
    assert checkout_step["uses"] == "actions/checkout@v6"
    assert python_step["uses"] == "actions/setup-python@v6"
    assert python_step["with"]["python-version"] == "${{ matrix.python-version }}"
    assert node_step["uses"] == "actions/setup-node@v6"
    assert node_step["with"]["node-version"] == "20"
    assert_setup_uv_step_pins_expected_version(uv_step, context="test.yml python-compatibility Set up uv")
    assert install_step["run"] == "uv sync --dev --frozen"

    import_smoke = workflow_step_by_name(workflow, "python-compatibility", "Run import stability contracts")["run"]
    assert "uv run pytest -n 0 -q tests/test_import_stability_contracts.py" in import_smoke

    console_smoke = workflow_step_by_name(workflow, "python-compatibility", "Smoke console script")["run"]
    assert "uv run gpd --version" in console_smoke
    assert "uv run gpd --help > /tmp/gpd-help.txt" in console_smoke
    assert "test -s /tmp/gpd-help.txt" in console_smoke

    targeted_tests = workflow_step_by_name(
        workflow, "python-compatibility", "Run installer and runtime compatibility tests"
    )["run"]
    assert "tests/test_runtime_catalog_bootstrap_contract.py" in targeted_tests
    assert "tests/test_runtime_install_smoke.py" in targeted_tests
    assert "tests/test_install_lifecycle.py::test_markdown_command_runtime_lifecycle_round_trip" in targeted_tests
    assert "test_bootstrap_prefers_versioned_python_when_generic_alias_is_newer" in targeted_tests
    assert "test_bootstrap_recreates_managed_env_when_selected_minor_changes" in targeted_tests
    assert "uv run pytest -q tests/" not in targeted_tests
    assert_run_step_uses_isolated_uv_build_env(build_step, context="test.yml python-compatibility Build wheel")
    assert "uv build --wheel --out-dir dist/compat-${{ matrix.python-version }}" in build_step["run"]


def test_ci_workflow_uses_current_action_versions() -> None:
    workflow = _workflow_data()
    action_uses = [step["uses"] for _, step in iter_workflow_steps(workflow) if "uses" in step]

    assert "actions/checkout@v6" in action_uses
    assert "actions/setup-node@v6" in action_uses
    assert "actions/checkout@v5" not in action_uses
    assert "actions/setup-node@v5" not in action_uses


def test_github_workflows_pin_setup_uv_tool_version() -> None:
    setup_uv_step_count = 0
    for path in _workflow_paths():
        workflow = load_github_actions_workflow(path)
        setup_uv_steps = workflow_steps_using(workflow, "astral-sh/setup-uv@v7")
        setup_uv_step_count += len(setup_uv_steps)

        for _, step in setup_uv_steps:
            assert_setup_uv_step_pins_expected_version(step, context=path.name)

    assert setup_uv_step_count > 0


def test_ci_workflow_installs_dev_dependencies_from_frozen_lockfile() -> None:
    workflow = _workflow_data()
    jobs = workflow_jobs(workflow)
    install_commands_by_job: dict[str, list[str]] = {}

    for job_id in jobs:
        for step in workflow_job_steps(workflow, str(job_id)):
            if step.get("name") == "Install dependencies":
                install_commands_by_job.setdefault(str(job_id), []).append(step["run"])

    assert {"ruff", "python-compatibility", "pytest"} <= set(install_commands_by_job)
    for job_id, install_commands in install_commands_by_job.items():
        assert install_commands, f"{job_id} must have at least one matching install step"
        for install_command in install_commands:
            assert install_command == "uv sync --dev --frozen", f"{job_id} install must use the frozen lockfile"


def test_tests_readme_documents_default_full_suite_and_category_named_runtime_informed_ci_shards() -> None:
    tests_readme = (REPO_ROOT / "tests" / "README.md").read_text(encoding="utf-8")

    assert_tests_readme_documents_ci_shard_policy(tests_readme)
