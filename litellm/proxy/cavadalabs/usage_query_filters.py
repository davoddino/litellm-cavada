from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

_API_KEY_HASH_METADATA_KEYS = ("user_api_key_hash", "api_key_hash", "user_api_key")
_METADATA_PREFIXES = ((), ("cavadalabs",), ("spend_logs_metadata",))


def metadata_scope_filters(logical_field: str, value: str) -> List[Dict[str, Any]]:
    if logical_field == "company_id":
        aliases = ("cavadalabs_company_id", "company_id")
    elif logical_field == "project_id":
        aliases = ("cavadalabs_project_id", "project_id")
    elif logical_field == "provider":
        aliases = ("cavadalabs_provider", "provider")
    elif logical_field == "model_alias":
        aliases = ("cavadalabs_model_alias", "model_alias")
    else:
        aliases = (logical_field,)

    filters: List[Dict[str, Any]] = []
    for prefix in ((), ("cavadalabs",), ("spend_logs_metadata",)):
        for alias in aliases:
            filters.append(
                {
                    "metadata": {
                        "path": [*prefix, alias],
                        "equals": value,
                    }
                }
            )
    return filters


def _clean_filter_values(values: Union[str, List[str]]) -> List[str]:
    if isinstance(values, list):
        raw_values = values
    else:
        raw_values = [values]

    cleaned_values: List[str] = []
    seen_values: set[str] = set()
    for value in raw_values:
        if value is None:
            continue
        cleaned = value.strip() if isinstance(value, str) else str(value).strip()
        if not cleaned or cleaned in seen_values:
            continue
        cleaned_values.append(cleaned)
        seen_values.add(cleaned)
    return cleaned_values


def api_key_hash_scope_filters(
    api_key_hashes: Union[str, List[str]],
) -> List[Dict[str, Any]]:
    cleaned_hashes = _clean_filter_values(api_key_hashes)
    if not cleaned_hashes:
        return []

    filters: List[Dict[str, Any]] = [{"api_key": {"in": cleaned_hashes}}]
    for api_key_hash in cleaned_hashes:
        for prefix in _METADATA_PREFIXES:
            for metadata_key in _API_KEY_HASH_METADATA_KEYS:
                filters.append(
                    {
                        "metadata": {
                            "path": [*prefix, metadata_key],
                            "equals": api_key_hash,
                        }
                    }
                )
    return filters


def metadata_scope_pair_filters(
    *,
    company_id: str,
    project_ids: List[str],
) -> List[Dict[str, Any]]:
    filters: List[Dict[str, Any]] = []
    company_filters = metadata_scope_filters("company_id", company_id)
    for project_id in project_ids:
        project_filters = metadata_scope_filters("project_id", project_id)
        for company_filter in company_filters:
            for project_filter in project_filters:
                filters.append({"AND": [company_filter, project_filter]})
    return filters


def spend_log_repair_where(
    *,
    date_range: Optional[Dict[str, datetime]],
    filters: List[Dict[str, Any]],
    model: Optional[str],
    provider: Optional[str],
    api_key: Optional[Union[str, List[str]]],
    status_filter: Optional[str] = None,
    min_spend: Optional[float] = None,
    max_spend: Optional[float] = None,
) -> Dict[str, Any]:
    conditions: List[Dict[str, Any]] = [{"OR": filters}]
    if model:
        conditions.append(
            {
                "OR": [
                    {"model": model},
                    {"model_group": model},
                    *metadata_scope_filters("model_alias", model),
                ]
            }
        )
    if provider:
        conditions.append(
            {
                "OR": [
                    {"custom_llm_provider": provider},
                    *metadata_scope_filters("provider", provider),
                ]
            }
        )
    if api_key:
        api_key_filters = api_key_hash_scope_filters(api_key)
        if api_key_filters:
            conditions.append({"OR": api_key_filters})
    if status_filter:
        conditions.append({"status": status_filter})
    spend_filter: Dict[str, float] = {}
    if min_spend is not None:
        spend_filter["gte"] = min_spend
    if max_spend is not None:
        spend_filter["lte"] = max_spend
    if spend_filter:
        conditions.append({"spend": spend_filter})
    where: Dict[str, Any] = {"AND": conditions}
    if date_range is not None:
        where["startTime"] = date_range
    return where
