from __future__ import annotations

from pathlib import Path

from gpd.core.workflow_staging import (
    WORKFLOW_STAGE_MANIFEST_DIR,
    WORKFLOW_STAGE_MANIFEST_SUFFIX,
    load_workflow_stage_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_PATH = (
    REPO_ROOT / "src" / "gpd" / "specs" / "references" / "orchestration" / "agent-module-loading.md"
)

ALLOWED_MODULE_INIT_FIELDS = {
    "selected_module_ids",
    "module_load_manifest",
    "module_policy_summary",
}
DISALLOWED_MODULE_BODY_KEYS = {
    "module_body",
    "module_bodies",
    "module_content",
    "module_contents",
    "module_markdown",
    "module_text",
    "module_payload",
    "module_payloads",
    "rendered_module_body",
    "rendered_module_content",
}


def _assert_staged_metadata_is_body_free(value: object, *, path: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            assert key_text not in DISALLOWED_MODULE_BODY_KEYS, path
            assert not (
                key_text.startswith("module_")
                and any(fragment in key_text for fragment in ("body", "content", "markdown", "text"))
            ), path
            _assert_staged_metadata_is_body_free(child, path=f"{path}.{key_text}")
        return

    if isinstance(value, list):
        for index, child in enumerate(value):
            _assert_staged_metadata_is_body_free(child, path=f"{path}[{index}]")
        return

    if isinstance(value, str):
        assert "\n" not in value, path


def test_agent_module_loading_reference_defines_stage_first_metadata_only_contract() -> None:
    text = REFERENCE_PATH.read_text(encoding="utf-8")
    normalized_text = " ".join(text.split())

    required_fragments = (
        "Stage first.",
        "`payload.staged_loading`",
        "`staged_loading.must_not_eager_load`",
        "`module_load_manifest`",
        "must not include module bodies",
        "`protocol_bundle_load_manifest`",
        "Selected protocol bundles are additive module sources",
        "Autonomy controls checkpoint and interruption pressure.",
    )

    for fragment in required_fragments:
        assert fragment in normalized_text


def test_stage_manifests_do_not_request_module_body_init_fields() -> None:
    offenders: dict[str, list[str]] = {}

    for manifest_path in sorted(WORKFLOW_STAGE_MANIFEST_DIR.glob(f"*{WORKFLOW_STAGE_MANIFEST_SUFFIX}")):
        workflow_id = manifest_path.name.removesuffix(WORKFLOW_STAGE_MANIFEST_SUFFIX)
        manifest = load_workflow_stage_manifest(workflow_id)
        for stage in manifest.stages:
            module_fields = [
                field
                for field in stage.required_init_fields
                if field.startswith("module_") or field.startswith("selected_module")
            ]
            unexpected_fields = sorted(set(module_fields) - ALLOWED_MODULE_INIT_FIELDS)
            if "module_policy_summary" in module_fields and "module_load_manifest" not in module_fields:
                unexpected_fields.append("module_policy_summary_without_module_load_manifest")
            if unexpected_fields:
                offenders[f"{workflow_id}:{stage.id}"] = unexpected_fields

    assert offenders == {}


def test_staged_loading_payloads_remain_metadata_only_and_module_body_free() -> None:
    for manifest_path in sorted(WORKFLOW_STAGE_MANIFEST_DIR.glob(f"*{WORKFLOW_STAGE_MANIFEST_SUFFIX}")):
        workflow_id = manifest_path.name.removesuffix(WORKFLOW_STAGE_MANIFEST_SUFFIX)
        manifest = load_workflow_stage_manifest(workflow_id)
        for stage_id in manifest.stage_ids():
            payload = manifest.staged_loading_payload(stage_id)
            _assert_staged_metadata_is_body_free(payload, path=f"{workflow_id}:{stage_id}")
