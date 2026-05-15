from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Union

from fastapi import HTTPException, status

from litellm._logging import verbose_proxy_logger
from litellm.litellm_core_utils.safe_json_loads import safe_json_loads
from litellm.proxy._types import CommonProxyErrors
from litellm.proxy.management_endpoints.common_daily_activity import (
    _aggregate_spend_records,
)
from litellm.proxy.utils import PrismaClient
from litellm.types.proxy.management_endpoints.common_daily_activity import (
    DailySpendMetadata,
    SpendAnalyticsPaginatedResponse,
)

_SUCCESS_STATUSES = {"success", "succeeded", "completed", "ok"}


def _normalize_entity_ids(
    entity_id: Optional[Union[str, List[str]]],
) -> Optional[Union[str, List[str]]]:
    if entity_id is None:
        return None
    if isinstance(entity_id, list):
        cleaned = [item.strip() for item in entity_id if item and item.strip()]
        return cleaned or None
    cleaned = entity_id.strip()
    return cleaned or None


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
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = safe_json_loads(value, default={})
        return parsed if isinstance(parsed, dict) else {}
    return {}


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


async def _company_metadata(
    prisma_client: PrismaClient,
    company_ids: List[str],
) -> Dict[str, Dict[str, Any]]:
    if not company_ids:
        return {}
    rows = await prisma_client.db.cavadalabs_companytable.find_many(
        where={"company_id": {"in": company_ids}},
    )
    return {
        row.company_id: {
            "id": row.company_id,
            "alias": row.legal_name,
            "legal_name": row.legal_name,
            "status": row.status,
        }
        for row in rows
    }


async def _project_metadata(
    prisma_client: PrismaClient,
    project_ids: List[str],
) -> Dict[str, Dict[str, Any]]:
    if not project_ids:
        return {}
    rows = await prisma_client.db.cavadalabs_projecttable.find_many(
        where={"project_id": {"in": project_ids}},
    )
    return {
        row.project_id: {
            "id": row.project_id,
            "alias": row.name,
            "name": row.name,
            "company_id": row.company_id,
            "status": row.status,
        }
        for row in rows
    }


async def get_cavadalabs_daily_activity(
    *,
    prisma_client: Optional[PrismaClient],
    entity_id_field: str,
    entity_id: Optional[Union[str, List[str]]],
    start_date: Optional[str],
    end_date: Optional[str],
    model: Optional[str],
    api_key: Optional[Union[str, List[str]]],
    page: int,
    page_size: int,
    timezone_offset_minutes: Optional[int],
) -> SpendAnalyticsPaginatedResponse:
    if prisma_client is None:
        raise HTTPException(
            status_code=500,
            detail={"error": CommonProxyErrors.db_not_connected_error.value},
        )
    if start_date is None or end_date is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Please provide start_date and end_date"},
        )

    try:
        normalized_entity_id = _normalize_entity_ids(entity_id)
        where_conditions: Dict[str, Any] = {
            "created_at": _utc_range_for_local_dates(
                start_date=start_date,
                end_date=end_date,
                timezone_offset_minutes=timezone_offset_minutes,
            )
        }

        if normalized_entity_id is not None:
            if isinstance(normalized_entity_id, list):
                where_conditions[entity_id_field] = {"in": normalized_entity_id}
            else:
                where_conditions[entity_id_field] = normalized_entity_id
        if model:
            where_conditions["model"] = model
        if api_key:
            if isinstance(api_key, list):
                where_conditions["api_key_hash"] = {"in": api_key}
            else:
                where_conditions["api_key_hash"] = api_key

        total_count = await prisma_client.db.cavadalabs_requestledgertable.count(
            where=where_conditions
        )
        ledger_rows = await prisma_client.db.cavadalabs_requestledgertable.find_many(
            where=where_conditions,
            order=[{"created_at": "desc"}],
            skip=(page - 1) * page_size,
            take=page_size,
        )
        daily_records = [
            _ledger_row_to_daily_record(
                row,
                timezone_offset_minutes=timezone_offset_minutes,
            )
            for row in ledger_rows
        ]

        entity_ids = sorted(
            {
                getattr(record, entity_id_field)
                for record in daily_records
                if getattr(record, entity_id_field, None)
            }
        )
        entity_metadata = (
            await _company_metadata(prisma_client, entity_ids)
            if entity_id_field == "company_id"
            else await _project_metadata(prisma_client, entity_ids)
        )
        aggregated = await _aggregate_spend_records(
            prisma_client=prisma_client,
            records=daily_records,
            entity_id_field=entity_id_field,
            entity_metadata_field=entity_metadata,
        )
        metadata_metrics = aggregated["totals"]

        return SpendAnalyticsPaginatedResponse(
            results=aggregated["results"],
            metadata=DailySpendMetadata(
                total_spend=metadata_metrics.spend,
                total_prompt_tokens=metadata_metrics.prompt_tokens,
                total_completion_tokens=metadata_metrics.completion_tokens,
                total_tokens=metadata_metrics.total_tokens,
                total_api_requests=metadata_metrics.api_requests,
                total_successful_requests=metadata_metrics.successful_requests,
                total_failed_requests=metadata_metrics.failed_requests,
                total_cache_read_input_tokens=metadata_metrics.cache_read_input_tokens,
                total_cache_creation_input_tokens=metadata_metrics.cache_creation_input_tokens,
                page=page,
                total_pages=-(-total_count // page_size),
                has_more=(page * page_size) < total_count,
            ),
        )
    except HTTPException:
        raise
    except Exception as exc:
        verbose_proxy_logger.exception(
            "Error fetching CavadaLabs daily activity: %s", str(exc)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": f"Failed to fetch CavadaLabs analytics: {str(exc)}"},
        ) from exc
