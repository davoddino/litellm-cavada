from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from litellm._logging import verbose_proxy_logger
from litellm.litellm_core_utils.safe_json_loads import safe_json_loads
from litellm.proxy.utils import PrismaClient


_FIELD_ALIASES: Dict[str, Iterable[str]] = {
    "company_id": ("cavadalabs_company_id", "company_id"),
    "project_id": ("cavadalabs_project_id", "project_id"),
    "chatbot_id": ("cavadalabs_chatbot_id", "chatbot_id"),
    "web_token_id": ("cavadalabs_web_token_id", "web_token_id"),
    "session_id": ("cavadalabs_session_id", "session_id"),
    "node_id": ("cavadalabs_node_id", "node_id"),
    "gpu_id": ("cavadalabs_gpu_id", "gpu_id"),
    "loaded_model_id": ("cavadalabs_loaded_model_id", "loaded_model_id"),
    "model_load_request_id": (
        "cavadalabs_model_load_request_id",
        "model_load_request_id",
    ),
    "provider": ("cavadalabs_provider", "provider"),
    "model_alias": ("cavadalabs_model_alias", "model_alias"),
}


def _metadata_dict(raw_metadata: Any) -> Dict[str, Any]:
    if isinstance(raw_metadata, dict):
        return raw_metadata
    if isinstance(raw_metadata, str):
        parsed = safe_json_loads(raw_metadata, default={})
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _metadata_sources(metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    sources: List[Dict[str, Any]] = []
    for key in ("cavadalabs", "spend_logs_metadata"):
        value = metadata.get(key)
        if isinstance(value, dict):
            sources.append(value)
    sources.append(metadata)
    return sources


def _extract_metadata_value(
    metadata_sources: List[Dict[str, Any]], logical_field: str
) -> Optional[str]:
    aliases = _FIELD_ALIASES[logical_field]
    for source in metadata_sources:
        for alias in aliases:
            value = source.get(alias)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _normalize_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        result = datetime.now(timezone.utc)
    if result.tzinfo is None:
        return result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _int_value(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def _float_value(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _build_cavadalabs_ledger_row(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    request_id = payload.get("request_id")
    if not isinstance(request_id, str) or not request_id.strip():
        return None

    metadata = _metadata_dict(payload.get("metadata"))
    sources = _metadata_sources(metadata)
    company_id = _extract_metadata_value(sources, "company_id")
    project_id = _extract_metadata_value(sources, "project_id")
    if company_id is None or project_id is None:
        return None

    provider = (
        _extract_metadata_value(sources, "provider")
        or payload.get("custom_llm_provider")
        or "unknown"
    )
    cavadalabs_model_alias = _extract_metadata_value(sources, "model_alias")
    if str(provider) == "cavadalabs" and cavadalabs_model_alias is not None:
        model = cavadalabs_model_alias
    else:
        model = payload.get("model") or payload.get("model_group") or "unknown"
    status = payload.get("status") or metadata.get("status") or "success"
    cavadalabs_metadata = {}
    for source in sources:
        if source is metadata:
            continue
        if "rag" in source and isinstance(source.get("rag"), dict):
            cavadalabs_metadata["rag"] = source["rag"]
        if "policy_id" in source:
            cavadalabs_metadata["policy_id"] = source.get("policy_id")
        if "guardrails" in source:
            cavadalabs_metadata["guardrails"] = source.get("guardrails")

    return {
        "request_id": request_id,
        "company_id": company_id,
        "project_id": project_id,
        "chatbot_id": _extract_metadata_value(sources, "chatbot_id"),
        "web_token_id": _extract_metadata_value(sources, "web_token_id"),
        "session_id": payload.get("session_id")
        or _extract_metadata_value(sources, "session_id"),
        "api_key_hash": payload.get("api_key"),
        "provider": str(provider),
        "model": str(model),
        "node_id": _extract_metadata_value(sources, "node_id"),
        "gpu_id": _extract_metadata_value(sources, "gpu_id"),
        "loaded_model_id": _extract_metadata_value(sources, "loaded_model_id"),
        "model_load_request_id": _extract_metadata_value(
            sources, "model_load_request_id"
        ),
        "prompt_tokens": _int_value(payload.get("prompt_tokens")),
        "completion_tokens": _int_value(payload.get("completion_tokens")),
        "total_tokens": _int_value(payload.get("total_tokens")),
        "spend": _float_value(payload.get("spend")),
        "status": str(status),
        "metadata": {
            "model_group": payload.get("model_group"),
            "call_type": payload.get("call_type"),
            "request_tags": payload.get("request_tags"),
            "cavadalabs": cavadalabs_metadata,
        },
        "created_at": _normalize_datetime(payload.get("startTime")),
    }


async def process_spend_logs_cavadalabs_ledger(
    prisma_client: PrismaClient,
    logs_to_process: List[Dict[str, Any]],
) -> None:
    """
    Mirror CavadaLabs-attributed LiteLLM spend logs into the Cavada request ledger.

    The processor is intentionally opt-in: rows are written only when the spend-log
    metadata contains explicit CavadaLabs company/project ids.
    """
    if not logs_to_process:
        return

    ledger_rows = []
    for payload in logs_to_process:
        try:
            row = _build_cavadalabs_ledger_row(payload)
        except (TypeError, ValueError) as exc:
            verbose_proxy_logger.warning(
                "CavadaLabs ledger skipped malformed spend log payload: %s", exc
            )
            continue
        if row is not None:
            ledger_rows.append(row)

    if not ledger_rows:
        return

    try:
        await prisma_client.db.cavadalabs_requestledgertable.create_many(
            data=ledger_rows,
            skip_duplicates=True,
        )
    except Exception as exc:
        verbose_proxy_logger.warning(
            "CavadaLabs request ledger tracking failed (non-fatal): %s", exc
        )
