from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Union

from fastapi import HTTPException, status

from litellm.litellm_core_utils.safe_json_loads import safe_json_loads

_SUCCESS_STATUSES = {"success", "succeeded", "completed", "ok"}


def _normalize_entity_ids(
    entity_id: Optional[Union[str, List[str]]],
) -> Optional[Union[str, List[str]]]:
    if entity_id is None:
        return None
    if isinstance(entity_id, list):
        return [item.strip() for item in entity_id if item and item.strip()]
    cleaned = entity_id.strip()
    return cleaned or None


def _normalize_entity_ids_list(entity_id: Optional[Union[str, List[str]]]) -> List[str]:
    normalized = _normalize_entity_ids(entity_id)
    if normalized is None:
        return []
    if isinstance(normalized, list):
        return normalized
    return [normalized]


def _parse_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": f"{field_name} must use YYYY-MM-DD format"},
        ) from exc


def _utc_range_for_local_dates(
    start_date: str,
    end_date: str,
    timezone_offset_minutes: Optional[int],
) -> Dict[str, datetime]:
    offset = timezone_offset_minutes or 0
    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date")
    if end < start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "end_date must be on or after start_date"},
        )

    local_start = datetime.combine(start, time.min)
    local_end_exclusive = datetime.combine(end + timedelta(days=1), time.min)
    return {
        "gte": (local_start + timedelta(minutes=offset)).replace(tzinfo=timezone.utc),
        "lt": (local_end_exclusive + timedelta(minutes=offset)).replace(
            tzinfo=timezone.utc
        ),
    }


def _local_date_key(
    created_at: datetime,
    timezone_offset_minutes: Optional[int],
) -> str:
    normalized = created_at
    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=timezone.utc)
    normalized = normalized.astimezone(timezone.utc)
    local_dt = normalized - timedelta(minutes=timezone_offset_minutes or 0)
    return local_dt.date().isoformat()


def _metadata_dict(value: Any) -> Dict[str, Any]:
    data = getattr(value, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = safe_json_loads(value, default={})
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _metadata_sources(metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    sources = [metadata]
    for key in ("cavadalabs", "spend_logs_metadata"):
        value = metadata.get(key)
        if isinstance(value, dict):
            sources.append(value)
    return sources


def _extract_metadata_context(metadata: Any) -> tuple[Optional[str], Optional[str]]:
    parsed_metadata = _metadata_dict(metadata)
    company_id = None
    project_id = None
    for source in _metadata_sources(parsed_metadata):
        company_id = company_id or _str_value(
            source.get("cavadalabs_company_id") or source.get("company_id")
        )
        project_id = project_id or _str_value(
            source.get("cavadalabs_project_id") or source.get("project_id")
        )
    return company_id, project_id


def _row_value(row: Any, field_name: str) -> Any:
    if isinstance(row, dict):
        return row.get(field_name)
    return getattr(row, field_name, None)


def _str_value(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _unique_sorted(values: List[str]) -> List[str]:
    return sorted({value for value in values if value})


def _clean_optional_str(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _build_cavadalabs_ledger_where(
    *,
    entity_id_field: str,
    entity_id: Optional[Union[str, List[str]]],
    date_range: Dict[str, datetime],
    model: Optional[str],
    provider: Optional[str],
    status_filter: Optional[str],
    api_key: Optional[Union[str, List[str]]],
    min_spend: Optional[float],
    max_spend: Optional[float],
) -> Dict[str, Any]:
    if min_spend is not None and max_spend is not None and max_spend < min_spend:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "max_spend must be greater than or equal to min_spend"},
        )

    normalized_entity_id = _normalize_entity_ids(entity_id)
    where_conditions: Dict[str, Any] = {"created_at": date_range}

    if normalized_entity_id is not None:
        if isinstance(normalized_entity_id, list):
            where_conditions[entity_id_field] = {"in": normalized_entity_id}
        else:
            where_conditions[entity_id_field] = normalized_entity_id

    cleaned_model = _clean_optional_str(model)
    and_conditions: List[Dict[str, Any]] = []
    if cleaned_model is not None:
        and_conditions.append(
            {
                "OR": [
                    {"model": cleaned_model},
                    {
                        "metadata": {
                            "path": ["model_group"],
                            "equals": cleaned_model,
                        }
                    },
                ]
            }
        )

    cleaned_provider = _clean_optional_str(provider)
    if cleaned_provider is not None:
        where_conditions["provider"] = cleaned_provider

    cleaned_status = _clean_optional_str(status_filter)
    if cleaned_status is not None:
        where_conditions["status"] = cleaned_status

    if api_key:
        if isinstance(api_key, list):
            cleaned_keys = [item.strip() for item in api_key if item and item.strip()]
            where_conditions["api_key_hash"] = {"in": cleaned_keys}
        else:
            cleaned_key = _clean_optional_str(api_key)
            if cleaned_key is not None:
                where_conditions["api_key_hash"] = cleaned_key

    spend_filter: Dict[str, float] = {}
    if min_spend is not None:
        spend_filter["gte"] = min_spend
    if max_spend is not None:
        spend_filter["lte"] = max_spend
    if spend_filter:
        where_conditions["spend"] = spend_filter
    if and_conditions:
        where_conditions["AND"] = and_conditions

    return where_conditions


def _ledger_row_to_daily_record(
    row: Any,
    *,
    timezone_offset_minutes: Optional[int],
) -> SimpleNamespace:
    metadata = _metadata_dict(getattr(row, "metadata", None))
    status_value = str(getattr(row, "status", "") or "").lower()
    is_success = status_value in _SUCCESS_STATUSES
    endpoint = metadata.get("endpoint") or metadata.get("call_type")

    return SimpleNamespace(
        date=_local_date_key(
            getattr(row, "created_at"),
            timezone_offset_minutes=timezone_offset_minutes,
        ),
        api_key=getattr(row, "api_key_hash", None) or "unassigned",
        model=getattr(row, "model", None) or "unknown",
        model_group=metadata.get("model_group") or getattr(row, "model", None),
        custom_llm_provider=getattr(row, "provider", None) or "unknown",
        mcp_namespaced_tool_name=None,
        endpoint=endpoint,
        spend=float(getattr(row, "spend", 0.0) or 0.0),
        prompt_tokens=int(getattr(row, "prompt_tokens", 0) or 0),
        completion_tokens=int(getattr(row, "completion_tokens", 0) or 0),
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
        api_requests=1,
        successful_requests=1 if is_success else 0,
        failed_requests=0 if is_success else 1,
        company_id=getattr(row, "company_id", None),
        project_id=getattr(row, "project_id", None),
    )
