from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Union


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
        if isinstance(api_key, list):
            cleaned_keys = [item for item in api_key if item]
            conditions.append({"api_key": {"in": cleaned_keys}})
        else:
            conditions.append({"api_key": api_key})
    where: Dict[str, Any] = {"AND": conditions}
    if date_range is not None:
        where["startTime"] = date_range
    return where
