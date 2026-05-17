from __future__ import annotations

from typing import Any, Dict, Optional


def _record(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def build_chatbot_token_metadata(
    metadata: Optional[Dict[str, Any]],
    *,
    company_id: str,
    project_id: str,
    chatbot_id: str,
    web_token_id: Optional[str] = None,
) -> Dict[str, Any]:
    next_metadata = _record(metadata)
    cavadalabs = _record(next_metadata.get("cavadalabs"))
    spend_logs_metadata = _record(next_metadata.get("spend_logs_metadata"))

    top_level = {
        "cavadalabs_company_id": company_id,
        "cavadalabs_project_id": project_id,
        "cavadalabs_chatbot_id": chatbot_id,
    }
    if web_token_id:
        top_level["cavadalabs_web_token_id"] = web_token_id

    next_metadata.update(top_level)
    next_metadata["cavadalabs_metadata_authenticated"] = True
    next_metadata["cavadalabs_metadata_source"] = "chatbot_runtime"
    next_metadata["cavadalabs"] = {
        **cavadalabs,
        "company_id": company_id,
        "project_id": project_id,
        "chatbot_id": chatbot_id,
        **({"web_token_id": web_token_id} if web_token_id else {}),
    }
    next_metadata["spend_logs_metadata"] = {
        **spend_logs_metadata,
        **top_level,
    }
    return next_metadata
