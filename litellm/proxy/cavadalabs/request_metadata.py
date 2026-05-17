from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Mapping, Optional

_CAVADALABS_REQUEST_METADATA_ALIASES: Mapping[str, tuple[str, ...]] = {
    "cavadalabs_company_id": ("cavadalabs_company_id", "company_id"),
    "cavadalabs_project_id": ("cavadalabs_project_id", "project_id"),
    "cavadalabs_chatbot_id": ("cavadalabs_chatbot_id", "chatbot_id"),
    "cavadalabs_web_token_id": ("cavadalabs_web_token_id", "web_token_id"),
    "cavadalabs_session_id": ("cavadalabs_session_id", "session_id"),
    "cavadalabs_node_id": ("cavadalabs_node_id", "node_id"),
    "cavadalabs_gpu_id": ("cavadalabs_gpu_id", "gpu_id"),
    "cavadalabs_loaded_model_id": (
        "cavadalabs_loaded_model_id",
        "loaded_model_id",
    ),
    "cavadalabs_model_load_request_id": (
        "cavadalabs_model_load_request_id",
        "model_load_request_id",
    ),
    "cavadalabs_provider": ("cavadalabs_provider", "provider"),
    "cavadalabs_model_alias": ("cavadalabs_model_alias", "model_alias"),
}
_AUTHENTICATED_METADATA_MARKER = "cavadalabs_metadata_authenticated"
_AUTHENTICATED_METADATA_SOURCE = "cavadalabs_metadata_source"


def merge_cavadalabs_key_metadata_into_request_metadata(
    *,
    request_metadata: Dict[str, Any],
    key_metadata: Any,
) -> None:
    """Copy authenticated CavadaLabs key metadata into request metadata.

    The LiteLLM spend payload only sees request metadata. CavadaLabs web-token
    and chatbot identifiers live on the authenticated key metadata, so they
    must be mirrored here before logging. Authenticated key metadata is
    authoritative for CavadaLabs fields; client-supplied metadata must not be
    able to move usage to another Company/Project.
    """

    applied_context = False
    for canonical_key, aliases in _CAVADALABS_REQUEST_METADATA_ALIASES.items():
        value = _first_metadata_value(key_metadata, aliases)
        if value is not None:
            applied_context = True
            request_metadata[canonical_key] = value
            _merge_authenticated_spend_logs_metadata(
                request_metadata=request_metadata,
                canonical_key=canonical_key,
                value=value,
            )
    if applied_context:
        request_metadata[_AUTHENTICATED_METADATA_MARKER] = True
        request_metadata[_AUTHENTICATED_METADATA_SOURCE] = "key_metadata"


def _merge_authenticated_spend_logs_metadata(
    *,
    request_metadata: Dict[str, Any],
    canonical_key: str,
    value: str,
) -> None:
    existing_spend_metadata = request_metadata.get("spend_logs_metadata")
    spend_logs_metadata = _metadata_dict(existing_spend_metadata)
    spend_logs_metadata[canonical_key] = value
    request_metadata["spend_logs_metadata"] = spend_logs_metadata


def _first_metadata_value(metadata: Any, aliases: Iterable[str]) -> Optional[str]:
    for source in _metadata_sources(metadata):
        for alias in aliases:
            value = _non_empty_str(source.get(alias))
            if value is not None:
                return value
    return None


def _metadata_sources(metadata: Any) -> list[Dict[str, Any]]:
    metadata_dict = _metadata_dict(metadata)
    sources = [metadata_dict]
    for nested_key in ("cavadalabs", "spend_logs_metadata"):
        nested = _metadata_dict(metadata_dict.get(nested_key))
        if nested:
            sources.append(nested)
    return sources


def _metadata_dict(value: Any) -> Dict[str, Any]:
    data = getattr(value, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _non_empty_str(value: Any) -> Optional[str]:
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned:
            return cleaned
    return None
