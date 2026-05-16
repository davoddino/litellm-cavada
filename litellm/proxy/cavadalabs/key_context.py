from __future__ import annotations

from typing import Any, Dict, Optional

from litellm.proxy._types import GenerateKeyRequest, UserAPIKeyAuth
from litellm.proxy.cavadalabs.key_context_filters import (
    _cavadalabs_key_context_filter,
    _resolve_cavadalabs_key_filter_compatibility_mappings,
    _validate_cavadalabs_key_list_filter_access,
)
from litellm.proxy.cavadalabs.key_context_metadata import (
    CAVADALABS_CHATBOT_METADATA_KEY,
    CAVADALABS_COMPANY_METADATA_KEY,
    CAVADALABS_METADATA_ENVELOPE_KEY,
    CAVADALABS_PROJECT_METADATA_KEY,
    CAVADALABS_SPEND_LOGS_METADATA_KEY,
    CavadaLabsResolvedKeyContext,
    _extract_cavadalabs_chatbot_id,
    _extract_cavadalabs_key_context,
    _metadata_to_dict,
    _optional_str,
    _preserve_existing_spend_logs_metadata,
    _set_cavadalabs_key_context_metadata,
)
from litellm.proxy.cavadalabs.key_context_schema import (
    CAVADALABS_KEY_CONTEXT_MIGRATION_COMMAND,
)
from litellm.proxy.cavadalabs.key_context_resolution import (
    _can_access_existing_cavadalabs_key,
    _require_existing_cavadalabs_key_admin_access,
)
from litellm.proxy.cavadalabs.key_context_validation import (
    _is_proxy_admin_user,
    _raise_cavadalabs_key_context_conflict,
    _require_cavadalabs_key_context_access,
    _validate_cavadalabs_key_chatbot_context,
    _validate_cavadalabs_key_context,
)


__all__ = [
    "CAVADALABS_COMPANY_METADATA_KEY",
    "CAVADALABS_CHATBOT_METADATA_KEY",
    "CAVADALABS_KEY_CONTEXT_MIGRATION_COMMAND",
    "CAVADALABS_METADATA_ENVELOPE_KEY",
    "CAVADALABS_PROJECT_METADATA_KEY",
    "CAVADALABS_SPEND_LOGS_METADATA_KEY",
    "CavadaLabsResolvedKeyContext",
    "_apply_cavadalabs_key_context",
    "_cavadalabs_key_context_filter",
    "_can_access_existing_cavadalabs_key",
    "_is_proxy_admin_user",
    "_metadata_to_dict",
    "_normalize_cavadalabs_generate_key_request",
    "_optional_str",
    "_require_existing_cavadalabs_key_admin_access",
    "_resolve_cavadalabs_key_filter_compatibility_mappings",
    "_validate_cavadalabs_key_context",
    "_validate_cavadalabs_key_list_filter_access",
]


async def _apply_cavadalabs_key_context(
    data_json: Dict[str, Any],
    existing_metadata: Optional[Dict[str, Any]],
    prisma_client: Any,
    user_api_key_dict: UserAPIKeyAuth,
    existing_team_id: Optional[str] = None,
    existing_organization_id: Optional[str] = None,
    existing_cavadalabs_company_id: Optional[str] = None,
    existing_cavadalabs_project_id: Optional[str] = None,
) -> Dict[str, Any]:
    requested_company_id = _optional_str(
        data_json.pop(CAVADALABS_COMPANY_METADATA_KEY, None)
    )
    requested_project_id = _optional_str(
        data_json.pop(CAVADALABS_PROJECT_METADATA_KEY, None)
    )
    metadata_company_id, metadata_project_id = _extract_cavadalabs_key_context(
        existing_metadata
    )
    existing_company_id = (
        _optional_str(existing_cavadalabs_company_id) or metadata_company_id
    )
    existing_project_id = (
        _optional_str(existing_cavadalabs_project_id) or metadata_project_id
    )
    existing_chatbot_id = _extract_cavadalabs_chatbot_id(existing_metadata)
    metadata_was_submitted = "metadata" in data_json
    submitted_metadata = _metadata_to_dict(data_json.get("metadata"))
    if metadata_was_submitted:
        submitted_metadata = _preserve_existing_spend_logs_metadata(
            submitted_metadata=submitted_metadata,
            existing_metadata=existing_metadata,
        )
    metadata_company_id, metadata_project_id = _extract_cavadalabs_key_context(
        submitted_metadata
    )
    submitted_chatbot_id = _extract_cavadalabs_chatbot_id(submitted_metadata)
    chatbot_id = submitted_chatbot_id or existing_chatbot_id

    requested_company_id = requested_company_id or metadata_company_id
    requested_project_id = requested_project_id or metadata_project_id
    context_was_requested = (
        requested_company_id is not None
        or requested_project_id is not None
        or submitted_chatbot_id is not None
    )

    if not context_was_requested:
        if existing_company_id and existing_project_id:
            data_json.pop("project_id", None)
            resolved_context = await _validate_cavadalabs_key_context(
                prisma_client=prisma_client,
                company_id=existing_company_id,
                project_id=existing_project_id,
            )
            await _require_cavadalabs_key_context_access(
                prisma_client=prisma_client,
                resolved_context=resolved_context,
                user_api_key_dict=user_api_key_dict,
            )
            await _validate_cavadalabs_key_chatbot_context(
                prisma_client=prisma_client,
                resolved_context=resolved_context,
                chatbot_id=chatbot_id,
            )
            _raise_cavadalabs_key_context_conflict(
                field_name="organization_id",
                incoming_value=_optional_str(data_json.get("organization_id")),
                mapped_value=resolved_context.litellm_organization_id,
                field_was_submitted="organization_id" in data_json,
            )
            _raise_cavadalabs_key_context_conflict(
                field_name="team_id",
                incoming_value=_optional_str(data_json.get("team_id")),
                mapped_value=resolved_context.litellm_team_id,
                field_was_submitted="team_id" in data_json,
            )
            if existing_organization_id != resolved_context.litellm_organization_id:
                data_json["organization_id"] = resolved_context.litellm_organization_id
            if existing_team_id != resolved_context.litellm_team_id:
                data_json["team_id"] = resolved_context.litellm_team_id
            if metadata_was_submitted:
                data_json["metadata"] = _set_cavadalabs_key_context_metadata(
                    metadata=submitted_metadata,
                    company_id=existing_company_id,
                    project_id=existing_project_id,
                    chatbot_id=chatbot_id,
                )
        return data_json

    data_json.pop("project_id", None)
    company_id = requested_company_id or existing_company_id
    project_id = requested_project_id or existing_project_id
    resolved_context = await _validate_cavadalabs_key_context(
        prisma_client=prisma_client,
        company_id=company_id,
        project_id=project_id,
    )
    await _require_cavadalabs_key_context_access(
        prisma_client=prisma_client,
        resolved_context=resolved_context,
        user_api_key_dict=user_api_key_dict,
    )
    await _validate_cavadalabs_key_chatbot_context(
        prisma_client=prisma_client,
        resolved_context=resolved_context,
        chatbot_id=chatbot_id,
    )
    incoming_organization_id = _optional_str(data_json.get("organization_id"))
    incoming_team_id = _optional_str(data_json.get("team_id"))
    context_changes_existing = (
        existing_company_id is not None
        and existing_project_id is not None
        and (
            resolved_context.company_id != existing_company_id
            or resolved_context.project_id != existing_project_id
        )
    )
    _raise_cavadalabs_key_context_conflict(
        field_name="organization_id",
        incoming_value=incoming_organization_id
        or (None if context_changes_existing else existing_organization_id),
        mapped_value=resolved_context.litellm_organization_id,
        field_was_submitted="organization_id" in data_json,
    )
    _raise_cavadalabs_key_context_conflict(
        field_name="team_id",
        incoming_value=incoming_team_id
        or (None if context_changes_existing else existing_team_id),
        mapped_value=resolved_context.litellm_team_id,
        field_was_submitted="team_id" in data_json,
    )

    metadata = submitted_metadata
    if not metadata and existing_metadata is not None:
        metadata = _metadata_to_dict(existing_metadata)
    data_json["metadata"] = _set_cavadalabs_key_context_metadata(
        metadata=metadata,
        company_id=resolved_context.company_id,
        project_id=resolved_context.project_id,
        chatbot_id=chatbot_id,
    )
    data_json["organization_id"] = resolved_context.litellm_organization_id
    data_json["team_id"] = resolved_context.litellm_team_id
    return data_json


async def _normalize_cavadalabs_generate_key_request(
    data: GenerateKeyRequest,
    prisma_client: Any,
    user_api_key_dict: UserAPIKeyAuth,
) -> bool:
    data_json = data.model_dump(exclude_unset=True, exclude_none=True)
    original_company_id = _optional_str(data_json.get(CAVADALABS_COMPANY_METADATA_KEY))
    original_project_id = _optional_str(data_json.get(CAVADALABS_PROJECT_METADATA_KEY))
    metadata_company_id, metadata_project_id = _extract_cavadalabs_key_context(
        _metadata_to_dict(data_json.get("metadata"))
    )
    metadata_chatbot_id = _extract_cavadalabs_chatbot_id(
        _metadata_to_dict(data_json.get("metadata"))
    )
    context_was_requested = (
        original_company_id is not None
        or original_project_id is not None
        or metadata_company_id is not None
        or metadata_project_id is not None
        or metadata_chatbot_id is not None
    )
    if not context_was_requested:
        return False

    normalized_data = await _apply_cavadalabs_key_context(
        data_json=data_json,
        existing_metadata=None,
        prisma_client=prisma_client,
        user_api_key_dict=user_api_key_dict,
    )
    data.metadata = normalized_data.get("metadata")
    data.organization_id = normalized_data.get("organization_id")
    data.team_id = normalized_data.get("team_id")
    data.project_id = None
    resolved_company_id, resolved_project_id = _extract_cavadalabs_key_context(
        data.metadata
    )
    data.cavadalabs_company_id = resolved_company_id
    data.cavadalabs_project_id = resolved_project_id
    fields_set = getattr(data, "model_fields_set", None)
    if fields_set is not None:
        fields_set.update(
            {
                "metadata",
                "organization_id",
                "team_id",
                CAVADALABS_COMPANY_METADATA_KEY,
                CAVADALABS_PROJECT_METADATA_KEY,
            }
        )
        fields_set.discard("project_id")
    return True
