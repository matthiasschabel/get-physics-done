"""Manifest-backed staged-init field access metadata."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from gpd.core.staged_context_fields import (
    STAGED_BODY_FIELDS,
    STAGED_REFERENCE_HANDLE_STATUS_FIELDS,
    STAGED_REFERENCE_RENDERED_CONTEXT_FIELDS,
)
from gpd.core.workflow_staging import (
    WORKFLOW_STAGE_MANIFEST_DIR,
    load_workflow_stage_manifest,
    resolve_workflow_stage_manifest_path,
)

FIELD_ACCESS_STYLES = frozenset({"instruction", "json", "shell"})
_SHELL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_JSON_FIELD_PATH_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_BODY_FIELD_SUFFIX = "_content"
_HANDLE_STATUS_SUFFIXES = (
    "_count",
    "_counts",
    "_file",
    "_files",
    "_ids",
    "_load_info",
    "_manifest",
    "_status",
    "_statuses",
    "_summary",
    "_warnings",
)


@dataclass(frozen=True, slots=True)
class StagedFieldAlias:
    """Explicit alias for a selected staged-init field."""

    alias: str
    field: str

    def to_payload(self) -> dict[str, str]:
        return {"alias": self.alias, "field": self.field}


@dataclass(frozen=True, slots=True)
class StagedFieldAccess:
    """Field-access metadata for one workflow stage."""

    workflow_id: str
    stage_id: str
    style: str
    selected_fields: tuple[str, ...]
    aliases: tuple[StagedFieldAlias, ...]
    stage_order: int
    stage_purpose: str
    manifest_path: str
    instructions: tuple[str, ...] = ()
    shell_bindings: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "workflow_id": self.workflow_id,
            "stage_id": self.stage_id,
            "style": self.style,
            "read_only": True,
            "source": {
                "type": "workflow_stage_manifest",
                "manifest_path": self.manifest_path,
            },
            "stage": {
                "order": self.stage_order,
                "purpose": self.stage_purpose,
            },
            "selected_fields": list(self.selected_fields),
            "aliases": [alias.to_payload() for alias in self.aliases],
        }
        if self.instructions:
            payload["instructions"] = list(self.instructions)
        if self.style == "shell" or self.shell_bindings:
            payload["shell_bindings"] = list(self.shell_bindings)
        return payload


def parse_field_alias_specs(alias_specs: Iterable[str] | None) -> tuple[StagedFieldAlias, ...]:
    """Parse repeatable alias specs of the form ``ALIAS=field`` or ``field``."""

    aliases: list[StagedFieldAlias] = []
    seen_aliases: set[str] = set()
    for raw_spec in alias_specs or ():
        spec = str(raw_spec).strip()
        if not spec:
            raise ValueError("field-access alias specs must not be blank")
        if "=" in spec:
            raw_alias, raw_field = spec.split("=", 1)
            alias = raw_alias.strip()
            field = raw_field.strip()
        else:
            alias = spec
            field = spec
        if not alias or not field:
            raise ValueError(f"Invalid field-access alias spec {raw_spec!r}; expected ALIAS=field")
        if not _SHELL_IDENTIFIER_RE.fullmatch(alias):
            raise ValueError(f"Invalid field-access alias {alias!r}; aliases must be shell identifier names")
        if alias in seen_aliases:
            raise ValueError(f"Duplicate field-access alias {alias!r}")
        seen_aliases.add(alias)
        aliases.append(StagedFieldAlias(alias=alias, field=field))
    return tuple(aliases)


def build_staged_field_access(
    workflow_id: str,
    *,
    stage_id: str,
    style: str = "instruction",
    alias_specs: Iterable[str] | None = None,
    payload_variable: str = "INIT",
) -> StagedFieldAccess:
    """Build field-access metadata from the workflow stage manifest."""

    normalized_style = style.strip().casefold()
    if normalized_style not in FIELD_ACCESS_STYLES:
        raise ValueError(
            f"Unknown field-access style {style!r}; expected one of: {', '.join(sorted(FIELD_ACCESS_STYLES))}"
        )
    if not stage_id or not stage_id.strip():
        raise ValueError("field-access requires --stage")
    if normalized_style == "shell" and not _SHELL_IDENTIFIER_RE.fullmatch(payload_variable):
        raise ValueError(
            f"Invalid field-access payload variable {payload_variable!r}; payload variable must be a shell identifier"
        )

    manifest = load_workflow_stage_manifest(workflow_id)
    try:
        stage = manifest.stage(stage_id.strip())
    except KeyError as exc:
        raise ValueError(
            f"Unknown {manifest.workflow_id} stage {stage_id!r}. Available stages: {', '.join(manifest.stage_ids())}"
        ) from exc

    selected_fields = stage.required_init_fields
    selected_field_set = set(selected_fields)
    aliases = parse_field_alias_specs(alias_specs)
    _validate_aliases_for_selected_fields(
        aliases, selected_field_set, workflow_id=manifest.workflow_id, stage_id=stage.id
    )

    manifest_path = resolve_workflow_stage_manifest_path(manifest.workflow_id)
    try:
        relative_manifest_path = manifest_path.relative_to(WORKFLOW_STAGE_MANIFEST_DIR.parent).as_posix()
    except ValueError:
        relative_manifest_path = manifest_path.as_posix()

    return StagedFieldAccess(
        workflow_id=manifest.workflow_id,
        stage_id=stage.id,
        style=normalized_style,
        selected_fields=selected_fields,
        aliases=aliases,
        stage_order=stage.order,
        stage_purpose=stage.purpose,
        manifest_path=relative_manifest_path,
        instructions=_instruction_lines(manifest.workflow_id, stage.id, selected_fields)
        if normalized_style == "instruction"
        else (),
        shell_bindings=_shell_binding_lines(aliases, payload_variable=payload_variable)
        if normalized_style == "shell"
        else (),
    )


def _validate_aliases_for_selected_fields(
    aliases: tuple[StagedFieldAlias, ...],
    selected_fields: set[str],
    *,
    workflow_id: str,
    stage_id: str,
) -> None:
    for alias in aliases:
        if alias.field not in selected_fields:
            raise ValueError(
                f"Field {alias.field!r} is not selected by {workflow_id} stage {stage_id!r}; "
                f"selected fields: {', '.join(sorted(selected_fields))}"
            )


def _instruction_lines(workflow_id: str, stage_id: str, selected_fields: tuple[str, ...]) -> tuple[str, ...]:
    field_list = ", ".join(selected_fields)
    body_fields = _selected_body_fields(selected_fields)
    handle_status_fields = _selected_handle_status_fields(selected_fields)
    rendered_context_fields = _selected_rendered_context_fields(selected_fields)
    lines = [
        (
            "Active-stage field access is manifest-owned: run "
            f"`gpd --raw stage field-access {workflow_id} --stage {stage_id} --style instruction`, "
            "then read only keys listed in `<INIT>.staged_loading.required_init_fields`."
        ),
        f"{workflow_id} stage {stage_id} selects exactly these staged-init fields: {field_list}.",
        "Treat unlisted init fields as unavailable for this stage.",
    ]
    if body_fields:
        lines.append(
            "Body fields are opt-in: selected body fields are target-scoped "
            f"({', '.join(body_fields)}) may be read only after choosing the concrete section, issue, "
            "artifact, gap, handoff, or reference target; use handles/status fields first."
        )
    elif handle_status_fields:
        lines.append(
            "Body fields are opt-in: selected handle/status fields are handles only; "
            "no staged body fields are selected for this stage."
        )
    else:
        lines.append("Body fields are opt-in: no staged body fields are selected for this stage.")
    if rendered_context_fields:
        lines.append(
            "Rendered context fields selected for this stage "
            f"({', '.join(rendered_context_fields)}) do not make unselected body fields available."
        )
    return tuple(lines)


def _selected_body_fields(selected_fields: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        field for field in selected_fields if field in STAGED_BODY_FIELDS or field.endswith(_BODY_FIELD_SUFFIX)
    )


def _selected_handle_status_fields(selected_fields: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        field
        for field in selected_fields
        if field in STAGED_REFERENCE_HANDLE_STATUS_FIELDS or field.endswith(_HANDLE_STATUS_SUFFIXES)
    )


def _selected_rendered_context_fields(selected_fields: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(field for field in selected_fields if field in STAGED_REFERENCE_RENDERED_CONTEXT_FIELDS)


def _shell_binding_lines(aliases: tuple[StagedFieldAlias, ...], *, payload_variable: str) -> tuple[str, ...]:
    lines: list[str] = []
    for alias in aliases:
        if not _JSON_FIELD_PATH_RE.fullmatch(alias.field):
            raise ValueError(f"Field {alias.field!r} cannot be emitted as a shell JSON path")
        lines.append(
            f'{alias.alias}=$(printf \'%s\\n\' "${{{payload_variable}}}" | gpd json get .{alias.field} --default "")'
        )
    return tuple(lines)


__all__ = [
    "FIELD_ACCESS_STYLES",
    "StagedFieldAccess",
    "StagedFieldAlias",
    "build_staged_field_access",
    "parse_field_alias_specs",
]
