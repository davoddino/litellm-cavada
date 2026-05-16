from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


CAVADALABS_COMPANY_METADATA_KEY = "cavadalabs_company_id"
CAVADALABS_PROJECT_METADATA_KEY = "cavadalabs_project_id"
CAVADALABS_CHATBOT_METADATA_KEY = "cavadalabs_chatbot_id"
CAVADALABS_METADATA_ENVELOPE_KEY = "cavadalabs"
CAVADALABS_SPEND_LOGS_METADATA_KEY = "spend_logs_metadata"


@dataclass(frozen=True)
class CavadaLabsResolvedKeyContext:
    company_id: str
    project_id: str
    litellm_organization_id: str
    litellm_team_id: str


def _optional_str(value: Any) -> Optional[str]:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def _metadata_to_dict(raw_metadata: Any) -> Dict[str, Any]:
    if isinstance(raw_metadata, dict):
        return copy.deepcopy(raw_metadata)
    if isinstance(raw_metadata, str):
        try:
            parsed = json.loads(raw_metadata)
            return copy.deepcopy(parsed) if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _preserve_existing_spend_logs_metadata(
    submitted_metadata: Dict[str, Any],
    existing_metadata: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    updated_metadata = copy.deepcopy(submitted_metadata)
    if CAVADALABS_SPEND_LOGS_METADATA_KEY in updated_metadata:
        return updated_metadata
    if not isinstance(existing_metadata, dict):
        return updated_metadata
    existing_spend_logs_metadata = existing_metadata.get(
        CAVADALABS_SPEND_LOGS_METADATA_KEY
    )
    if isinstance(existing_spend_logs_metadata, dict):
        updated_metadata[CAVADALABS_SPEND_LOGS_METADATA_KEY] = copy.deepcopy(
            existing_spend_logs_metadata
        )
    return updated_metadata


def _extract_cavadalabs_key_context(
    metadata: Optional[Dict[str, Any]],
) -> Tuple[Optional[str], Optional[str]]:
    if not isinstance(metadata, dict):
        return None, None
    cavadalabs_metadata = metadata.get(CAVADALABS_METADATA_ENVELOPE_KEY)
    spend_logs_metadata = metadata.get(CAVADALABS_SPEND_LOGS_METADATA_KEY)
    company_id = _optional_str(metadata.get(CAVADALABS_COMPANY_METADATA_KEY))
    project_id = _optional_str(metadata.get(CAVADALABS_PROJECT_METADATA_KEY))
    if isinstance(cavadalabs_metadata, dict):
        company_id = company_id or _optional_str(cavadalabs_metadata.get("company_id"))
        project_id = project_id or _optional_str(cavadalabs_metadata.get("project_id"))
    if isinstance(spend_logs_metadata, dict):
        company_id = company_id or _optional_str(
            spend_logs_metadata.get(CAVADALABS_COMPANY_METADATA_KEY)
        )
        project_id = project_id or _optional_str(
            spend_logs_metadata.get(CAVADALABS_PROJECT_METADATA_KEY)
        )
    return company_id, project_id


def _extract_cavadalabs_chatbot_id(metadata: Optional[Dict[str, Any]]) -> Optional[str]:
    if not isinstance(metadata, dict):
        return None
    cavadalabs_metadata = metadata.get(CAVADALABS_METADATA_ENVELOPE_KEY)
    spend_logs_metadata = metadata.get(CAVADALABS_SPEND_LOGS_METADATA_KEY)
    chatbot_id = _optional_str(metadata.get(CAVADALABS_CHATBOT_METADATA_KEY))
    if isinstance(cavadalabs_metadata, dict):
        chatbot_id = chatbot_id or _optional_str(cavadalabs_metadata.get("chatbot_id"))
    if isinstance(spend_logs_metadata, dict):
        chatbot_id = (
            chatbot_id
            or _optional_str(spend_logs_metadata.get(CAVADALABS_CHATBOT_METADATA_KEY))
            or _optional_str(spend_logs_metadata.get("chatbot_id"))
        )
    return chatbot_id


def _set_cavadalabs_key_context_metadata(
    metadata: Dict[str, Any],
    company_id: str,
    project_id: str,
    chatbot_id: Optional[str] = None,
) -> Dict[str, Any]:
    updated_metadata = copy.deepcopy(metadata)
    resolved_chatbot_id = chatbot_id or _extract_cavadalabs_chatbot_id(updated_metadata)
    cavadalabs_metadata = updated_metadata.get(CAVADALABS_METADATA_ENVELOPE_KEY)
    if not isinstance(cavadalabs_metadata, dict):
        cavadalabs_metadata = {}
    cavadalabs_metadata["company_id"] = company_id
    cavadalabs_metadata["project_id"] = project_id
    if resolved_chatbot_id is not None:
        cavadalabs_metadata["chatbot_id"] = resolved_chatbot_id
    updated_metadata[CAVADALABS_COMPANY_METADATA_KEY] = company_id
    updated_metadata[CAVADALABS_PROJECT_METADATA_KEY] = project_id
    if resolved_chatbot_id is not None:
        updated_metadata[CAVADALABS_CHATBOT_METADATA_KEY] = resolved_chatbot_id
    updated_metadata[CAVADALABS_METADATA_ENVELOPE_KEY] = cavadalabs_metadata
    spend_logs_metadata = updated_metadata.get(CAVADALABS_SPEND_LOGS_METADATA_KEY)
    if not isinstance(spend_logs_metadata, dict):
        spend_logs_metadata = {}
    spend_logs_metadata[CAVADALABS_COMPANY_METADATA_KEY] = company_id
    spend_logs_metadata[CAVADALABS_PROJECT_METADATA_KEY] = project_id
    if resolved_chatbot_id is not None:
        spend_logs_metadata[CAVADALABS_CHATBOT_METADATA_KEY] = resolved_chatbot_id
    updated_metadata[CAVADALABS_SPEND_LOGS_METADATA_KEY] = spend_logs_metadata
    return updated_metadata


def _key_info_value(key_info: Any, field_name: str) -> Any:
    if isinstance(key_info, dict):
        return key_info.get(field_name)
    return getattr(key_info, field_name, None)
