"""Test-only structural helpers for runtime projection assertions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from gpd.adapters.install_utils import (
    COMPACT_HELP_BRIDGE_SHIM_SENTINEL,
    COMPACT_STAGED_COMMAND_SHIM_SENTINEL,
    COMPACT_WORKFLOW_COMMAND_SHIM_SENTINEL,
    DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES,
    build_runtime_cli_bridge_command,
)
from gpd.adapters.runtime_catalog import get_runtime_descriptor
from gpd.core import prompt_diagnostics
from gpd.core.workflow_staging import load_workflow_stage_manifest_from_path
from tests.prompt_metrics_support import MarkdownFence, iter_markdown_fences

__all__ = [
    "HELP_BRIDGE_SHIM_SENTINELS",
    "NORMALIZED_RUNTIME_BRIDGE_MARKER",
    "PROTOCOL_BUNDLE_INLINE_CATALOG_MARKERS",
    "PROTOCOL_BUNDLE_JIT_COMMANDS",
    "PROTOCOL_BUNDLE_JIT_FIELDS",
    "ProjectedSection",
    "ProjectedText",
    "RUNTIME_BRIDGE_COMMAND_RE",
    "RUNTIME_NOTE_TAGS",
    "STAGED_SHIM_CONTRACT_FRAGMENTS",
    "STAGED_SHIM_SENTINELS",
    "StagedCommandProjectionCase",
    "UNRESOLVED_INCLUDE_MARKERS",
    "WORKFLOW_REFERENCE_SHIM_SENTINELS",
    "assert_compact_staged_command_shim",
    "assert_no_unresolved_include_markers",
    "assert_protocol_bundle_jit_shape",
    "assert_runtime_note_tag_count",
    "assert_runtime_note_tags_not_repeated",
    "first_runnable_shell_command",
    "first_runnable_shell_commands",
    "has_compact_non_native_shim",
    "has_help_bridge_shim_sentinel",
    "has_staged_shim_sentinel",
    "has_workflow_reference_shim_sentinel",
    "iter_staged_command_projection_cases",
    "normalize_projected_text",
    "normalized_runtime_bridge_text",
    "normalized_runtime_projection_char_count",
    "raw_include_count",
    "runnable_shell_lines",
    "runtime_bridge_command",
    "shell_fence_bodies",
    "shell_fences",
    "staged_command_has_protocol_bundle_fields",
    "single_runtime_note_block",
    "tag_count",
]

_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)(?:[ \t]+#+[ \t]*)?$")
RUNTIME_BRIDGE_COMMAND_RE = re.compile(
    r"(?:[^ \n`]+)\s+-m gpd\.runtime_cli\s+--runtime\s+[a-z-]+"
    r"\s+--config-dir\s+[^ \n`]+(?:\s+--install-scope\s+local)?"
)
NORMALIZED_RUNTIME_BRIDGE_MARKER = "<runtime-bridge>"
STAGED_SHIM_SENTINELS = (COMPACT_STAGED_COMMAND_SHIM_SENTINEL, "## Compact Staged Command Shim")
HELP_BRIDGE_SHIM_SENTINELS = (COMPACT_HELP_BRIDGE_SHIM_SENTINEL, "CLI-owned compact help surface")
WORKFLOW_REFERENCE_SHIM_SENTINELS = (COMPACT_WORKFLOW_COMMAND_SHIM_SENTINEL,)
UNRESOLVED_INCLUDE_MARKERS = (
    "@ include not resolved:",
    "@ include cycle detected:",
    "@ include read error:",
    "@ include depth limit reached:",
)
RUNTIME_NOTE_TAGS = (
    "codex_runtime_notes",
    "codex_questioning",
    "gemini_runtime_notes",
    "gemini_shell_runtime_notes",
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


@dataclass(frozen=True, slots=True)
class ProjectedSection:
    """One markdown section from a projected runtime prompt."""

    heading: str
    level: int
    body: str
    start_line: int
    end_line: int

    @property
    def text(self) -> str:
        heading_line = f"{'#' * self.level} {self.heading}"
        return f"{heading_line}\n{self.body}" if self.body else heading_line


@dataclass(frozen=True, slots=True)
class StagedCommandProjectionCase:
    """One checked-in staged command/workflow manifest pair."""

    command_name: str
    first_stage_id: str
    native_include_paths: tuple[str, ...]
    staged_loading_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Heading:
    heading: str
    level: int
    line_number: int


@dataclass(frozen=True, slots=True)
class ProjectedText:
    """Normalized view of a projected runtime prompt."""

    text: str

    def sections(self, heading: str | None = None, *, level: int | None = None) -> tuple[ProjectedSection, ...]:
        sections = _sections(self.text)
        if heading is not None:
            sections = tuple(section for section in sections if section.heading == heading)
        if level is not None:
            sections = tuple(section for section in sections if section.level == level)
        return sections

    def section(self, heading: str, *, level: int | None = None) -> ProjectedSection:
        sections = self.sections(heading, level=level)
        assert len(sections) == 1, f"Expected exactly one projected section {heading!r}; found {len(sections)}"
        return sections[0]

    def shell_fences(self) -> tuple[MarkdownFence, ...]:
        return shell_fences(self.text)

    def first_runnable_shell_commands(self) -> tuple[str, ...]:
        return tuple(command for fence in self.shell_fences() if (command := first_runnable_shell_command(fence)))


def normalize_projected_text(text: str) -> ProjectedText:
    return ProjectedText(text=text)


def iter_staged_command_projection_cases(
    *,
    commands_dir: Path,
    workflows_dir: Path,
) -> tuple[StagedCommandProjectionCase, ...]:
    """Return projection cases discovered from checked-in stage manifests."""

    cases: list[StagedCommandProjectionCase] = []
    for manifest_path in sorted(workflows_dir.glob("*-stage-manifest.json")):
        command_name = manifest_path.name.removesuffix("-stage-manifest.json")
        command_path = commands_dir / f"{command_name}.md"
        assert command_path.is_file(), f"{manifest_path.name} has no command surface at {command_path}"

        manifest = load_workflow_stage_manifest_from_path(
            manifest_path,
            expected_workflow_id=command_name,
        )
        if manifest.prompt_usage != "staged_init":
            continue
        assert manifest.stages, f"{manifest_path.name} has no stages"
        first_stage = manifest.stages[0]
        cases.append(
            StagedCommandProjectionCase(
                command_name=command_name,
                first_stage_id=first_stage.id,
                native_include_paths=tuple(first_stage.mode_paths),
                staged_loading_keys=tuple(manifest.staged_loading_payload(first_stage.id)),
            )
        )

    return tuple(cases)


def first_runnable_shell_command(fence_or_body: MarkdownFence | str) -> str | None:
    body = fence_or_body.body if isinstance(fence_or_body, MarkdownFence) else fence_or_body
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return None


def runtime_bridge_command(
    runtime: str,
    target_dir: Path,
    *,
    is_global: bool = False,
    explicit_target: bool = False,
) -> str:
    descriptor = get_runtime_descriptor(runtime)
    return build_runtime_cli_bridge_command(
        runtime,
        target_dir=target_dir,
        config_dir_name=descriptor.config_dir_name,
        is_global=is_global,
        explicit_target=explicit_target,
    )


def normalized_runtime_bridge_text(text: str) -> str:
    return RUNTIME_BRIDGE_COMMAND_RE.sub(NORMALIZED_RUNTIME_BRIDGE_MARKER, text)


def normalized_runtime_projection_char_count(metric: prompt_diagnostics.RuntimeProjectionMetric) -> int:
    bridge_occurrences = metric.bridge_command_occurrences
    if bridge_occurrences == 0:
        return metric.char_count
    bridge_command = prompt_diagnostics._projection_bridge_command(metric.runtime)
    return metric.char_count - (len(bridge_command) - len(NORMALIZED_RUNTIME_BRIDGE_MARKER)) * bridge_occurrences


def raw_include_count(text: str, include_suffix: str) -> int:
    return sum(
        1 for line in text.splitlines() if line.strip().startswith("@") and line.strip().endswith(include_suffix)
    )


def shell_fences(text: str) -> tuple[MarkdownFence, ...]:
    fences: list[MarkdownFence] = []
    for fence in iter_markdown_fences(text):
        info = fence.info.strip()
        language = info.split(None, 1)[0].lower() if info else ""
        if language in DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES:
            fences.append(fence)
    return tuple(fences)


def shell_fence_bodies(text: str) -> tuple[str, ...]:
    return tuple(fence.body for fence in shell_fences(text))


def runnable_shell_lines(fence: MarkdownFence) -> tuple[str, ...]:
    return tuple(
        stripped for line in fence.body.splitlines() if (stripped := line.strip()) and not stripped.startswith("#")
    )


def first_runnable_shell_commands(text: str) -> tuple[str, ...]:
    return tuple(command for fence in shell_fences(text) if (command := first_runnable_shell_command(fence)))


def has_staged_shim_sentinel(text: str) -> bool:
    return any(sentinel in text for sentinel in STAGED_SHIM_SENTINELS)


def has_help_bridge_shim_sentinel(text: str) -> bool:
    return any(sentinel in text for sentinel in HELP_BRIDGE_SHIM_SENTINELS)


def has_workflow_reference_shim_sentinel(text: str) -> bool:
    return any(sentinel in text for sentinel in WORKFLOW_REFERENCE_SHIM_SENTINELS)


def has_compact_non_native_shim(text: str) -> bool:
    return (
        has_staged_shim_sentinel(text)
        or has_help_bridge_shim_sentinel(text)
        or has_workflow_reference_shim_sentinel(text)
    )


def assert_no_unresolved_include_markers(text: str, *, label: str) -> None:
    lowered = text.lower()
    offenders = [marker for marker in UNRESOLVED_INCLUDE_MARKERS if marker in lowered]
    assert offenders == [], f"{label} contains unresolved include marker(s): {', '.join(offenders)}"


def tag_count(text: str, tag: str) -> tuple[int, int]:
    return text.count(f"<{tag}>"), text.count(f"</{tag}>")


def assert_runtime_note_tags_not_repeated(text: str, *, label: str, tags: tuple[str, ...] = RUNTIME_NOTE_TAGS) -> None:
    for tag in tags:
        opens, closes = tag_count(text, tag)
        assert opens == closes, f"{label} has unbalanced {tag}: {opens}/{closes}"
        assert opens <= 1, f"{label} repeats {tag}: {opens}"


def assert_runtime_note_tag_count(text: str, tag: str, expected_count: int, *, label: str | None = None) -> None:
    opens, closes = tag_count(text, tag)
    detail = f" for {label}" if label else ""
    assert opens == expected_count, f"Expected {expected_count} <{tag}> block(s){detail}; found {opens}"
    assert closes == expected_count, f"Expected {expected_count} </{tag}> block(s){detail}; found {closes}"


def single_runtime_note_block(text: str, tag: str, *, label: str | None = None) -> str:
    assert_runtime_note_tag_count(text, tag, 1, label=label)
    match = re.search(rf"<{re.escape(tag)}>\n(?P<body>.*?)</{re.escape(tag)}>", text, flags=re.DOTALL)
    assert match is not None, f"{label or tag} should have one <{tag}> block"
    return match.group("body").strip()


def assert_compact_staged_command_shim(
    text: str,
    *,
    command_name: str,
    first_stage: str,
    staged_loading_keys: tuple[str, ...] = (),
    command_label: str | None = None,
) -> None:
    assert COMPACT_STAGED_COMMAND_SHIM_SENTINEL in text
    expected_command_label = command_label or f"gpd:{command_name}"
    assert f'command="{expected_command_label}"' in text
    assert f'first_stage="{first_stage}"' in text
    assert f"<!-- [included: {command_name}.md] -->" not in text
    assert f"@{{GPD_INSTALL_DIR}}/workflows/{command_name}.md" not in text
    assert f"--raw init {command_name}" in text
    assert f"--stage {first_stage}" in text
    for fragment in (*STAGED_SHIM_CONTRACT_FRAGMENTS, *staged_loading_keys):
        assert fragment in text


def assert_protocol_bundle_jit_shape(
    text: str,
    *,
    case: StagedCommandProjectionCase,
    runtime: str,
    has_bundle_fields: bool,
) -> None:
    descriptor = get_runtime_descriptor(runtime)
    if not has_bundle_fields:
        assert "<protocol_bundle_jit>" not in text
        return

    for marker in PROTOCOL_BUNDLE_INLINE_CATALOG_MARKERS:
        assert marker not in text

    if descriptor.native_include_support:
        for include_path in case.native_include_paths:
            assert raw_include_count(text, include_path) == 1
        assert "<protocol_bundle_jit>" not in text
        return

    assert has_staged_shim_sentinel(text)
    assert "<protocol_bundle_jit>" in text
    assert "use those init payload fields as the selected-bundle loading map" in text
    assert "load only selected asset paths named by `protocol_bundle_context`" in text
    assert "do not inline protocol bundle catalogs during bootstrap" in text
    for field in PROTOCOL_BUNDLE_JIT_FIELDS:
        assert field in text


def staged_command_has_protocol_bundle_fields(
    workflows_dir: Path,
    command_name: str,
    *,
    jit_commands: tuple[str, ...] = PROTOCOL_BUNDLE_JIT_COMMANDS,
) -> bool:
    if command_name not in jit_commands:
        return False
    manifest = load_workflow_stage_manifest_from_path(
        workflows_dir / f"{command_name}-stage-manifest.json",
        expected_workflow_id=command_name,
    )
    return any(
        any(field in stage.required_init_fields for field in PROTOCOL_BUNDLE_JIT_FIELDS) for stage in manifest.stages
    )


def _sections(text: str) -> tuple[ProjectedSection, ...]:
    lines = text.splitlines()
    headings = _headings_outside_fences(lines)
    sections: list[ProjectedSection] = []

    for index, heading in enumerate(headings):
        end_line = len(lines)
        for later_heading in headings[index + 1 :]:
            if later_heading.level <= heading.level:
                end_line = later_heading.line_number - 1
                break

        body_lines = lines[heading.line_number : end_line]
        sections.append(
            ProjectedSection(
                heading=heading.heading,
                level=heading.level,
                body="\n".join(body_lines),
                start_line=heading.line_number,
                end_line=end_line,
            )
        )

    return tuple(sections)


def _headings_outside_fences(lines: list[str]) -> tuple[_Heading, ...]:
    headings: list[_Heading] = []
    active_fence_marker: str | None = None

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        fence_marker = _fence_marker(stripped)
        if fence_marker is not None:
            if active_fence_marker is None:
                active_fence_marker = fence_marker
            elif fence_marker == active_fence_marker:
                active_fence_marker = None
            continue

        if active_fence_marker is not None:
            continue

        match = _HEADING_RE.match(stripped)
        if match is not None:
            marker, heading = match.groups()
            headings.append(_Heading(heading=heading.strip(), level=len(marker), line_number=line_number))

    return tuple(headings)


def _fence_marker(stripped_line: str) -> str | None:
    if stripped_line.startswith("```"):
        return "```"
    if stripped_line.startswith("~~~"):
        return "~~~"
    return None
