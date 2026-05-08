"""Test-only structural helpers for runtime projection assertions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from gpd.adapters.install_utils import DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES
from gpd.core.workflow_staging import load_workflow_stage_manifest_from_path
from tests.prompt_metrics_support import MarkdownFence, iter_markdown_fences

__all__ = [
    "ProjectedSection",
    "ProjectedText",
    "StagedCommandProjectionCase",
    "first_runnable_shell_command",
    "iter_staged_command_projection_cases",
    "normalize_projected_text",
]

_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)(?:[ \t]+#+[ \t]*)?$")


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
        return tuple(
            fence
            for fence in iter_markdown_fences(self.text)
            if fence.info.lower() in DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES
        )

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
