from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from fastapi import HTTPException, status

from litellm._logging import verbose_proxy_logger
from litellm.proxy._types import CommonProxyErrors
from litellm.proxy.cavadalabs.usage_backfill import (
    _repair_empty_usage_ledger_from_spend_logs,
    repair_incomplete_cavadalabs_usage_ledger_from_spend_logs,
)
from litellm.proxy.cavadalabs.usage_schema_readiness import (
    ensure_cavadalabs_usage_repair_schema_ready,
    looks_like_missing_schema_exception as _looks_like_missing_schema_exception,
    missing_usage_schema_state as _missing_usage_schema_state,
    probe_usage_schema as _probe_usage_schema,
    raise_missing_usage_schema_http_exception as _raise_missing_usage_schema_http_exception,
)
from litellm.proxy.cavadalabs.usage_serialization import (
    _build_cavadalabs_ledger_where,
    _ledger_row_to_daily_record,
    _normalize_entity_ids,
    _utc_range_for_local_dates,
)
from litellm.proxy.management_endpoints.common_daily_activity import (
    get_api_key_metadata,
    update_breakdown_metrics,
    update_metrics,
)
from litellm.proxy.utils import PrismaClient
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsUsageSchemaStatus,
)
from litellm.types.proxy.management_endpoints.common_daily_activity import (
    BreakdownMetrics,
    DailySpendMetadata,
    DailySpendData,
    SpendAnalyticsPaginatedResponse,
    SpendMetrics,
)

_REQUEST_LEDGER_FETCH_PAGE_SIZE = 1000


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


def _daily_bucket(
    grouped_data: Dict[str, Dict[str, Any]],
    date_str: str,
) -> Dict[str, Any]:
    if date_str not in grouped_data:
        grouped_data[date_str] = {
            "metrics": SpendMetrics(),
            "breakdown": BreakdownMetrics(),
        }
    return grouped_data[date_str]


def _daily_results_from_grouped(
    grouped_data: Dict[str, Dict[str, Any]]
) -> List[DailySpendData]:
    results = [
        DailySpendData(
            date=datetime.strptime(date_str, "%Y-%m-%d").date(),
            metrics=data["metrics"],
            breakdown=data["breakdown"],
        )
        for date_str, data in grouped_data.items()
    ]
    results.sort(key=lambda result: result.date, reverse=True)
    return results


async def _ensure_entity_metadata(
    *,
    prisma_client: PrismaClient,
    entity_id_field: str,
    entity_metadata: Dict[str, Dict[str, Any]],
    records: List[Any],
) -> None:
    missing_entity_ids = sorted(
        {
            entity_id
            for record in records
            if (entity_id := getattr(record, entity_id_field, None))
            and entity_id not in entity_metadata
        }
    )
    if not missing_entity_ids:
        return
    fetched_metadata = (
        await _company_metadata(prisma_client, missing_entity_ids)
        if entity_id_field == "company_id"
        else await _project_metadata(prisma_client, missing_entity_ids)
    )
    entity_metadata.update(fetched_metadata)


async def _ensure_api_key_metadata(
    *,
    prisma_client: PrismaClient,
    api_key_metadata: Dict[str, Dict[str, Any]],
    records: List[Any],
) -> None:
    missing_api_keys = {
        api_key
        for record in records
        if (api_key := getattr(record, "api_key", None))
        and api_key != "unassigned"
        and api_key not in api_key_metadata
    }
    if not missing_api_keys:
        return
    api_key_metadata.update(
        await get_api_key_metadata(prisma_client, missing_api_keys)
    )


def _add_daily_record_to_grouped(
    *,
    grouped_data: Dict[str, Dict[str, Any]],
    total_metrics: SpendMetrics,
    record: Any,
    api_key_metadata: Dict[str, Dict[str, Any]],
    entity_id_field: str,
    entity_metadata: Dict[str, Dict[str, Any]],
) -> None:
    bucket = _daily_bucket(grouped_data, record.date)
    bucket["metrics"] = update_metrics(bucket["metrics"], record)
    bucket["breakdown"] = update_breakdown_metrics(
        bucket["breakdown"],
        record,
        {},
        {},
        api_key_metadata,
        entity_id_field=entity_id_field,
        entity_metadata_field=entity_metadata,
    )
    update_metrics(total_metrics, record)


async def _aggregate_ledger_rows_by_day(
    *,
    prisma_client: PrismaClient,
    where_conditions: Dict[str, Any],
    entity_id_field: str,
    timezone_offset_minutes: Optional[int],
) -> Dict[str, Any]:
    grouped_data: Dict[str, Dict[str, Any]] = {}
    total_metrics = SpendMetrics()
    api_key_metadata: Dict[str, Dict[str, Any]] = {}
    entity_metadata: Dict[str, Dict[str, Any]] = {}
    skip = 0
    while True:
        page = await prisma_client.db.cavadalabs_requestledgertable.find_many(
            where=where_conditions,
            order=[{"created_at": "desc"}],
            skip=skip,
            take=_REQUEST_LEDGER_FETCH_PAGE_SIZE,
        )
        if not page:
            break
        daily_records = [
            _ledger_row_to_daily_record(
                row,
                timezone_offset_minutes=timezone_offset_minutes,
            )
            for row in page
        ]
        await _ensure_entity_metadata(
            prisma_client=prisma_client,
            entity_id_field=entity_id_field,
            entity_metadata=entity_metadata,
            records=daily_records,
        )
        await _ensure_api_key_metadata(
            prisma_client=prisma_client,
            api_key_metadata=api_key_metadata,
            records=daily_records,
        )
        for record in daily_records:
            _add_daily_record_to_grouped(
                grouped_data=grouped_data,
                total_metrics=total_metrics,
                record=record,
                api_key_metadata=api_key_metadata,
                entity_id_field=entity_id_field,
                entity_metadata=entity_metadata,
            )
        if len(page) < _REQUEST_LEDGER_FETCH_PAGE_SIZE:
            break
        skip += len(page)
    return {
        "results": _daily_results_from_grouped(grouped_data),
        "totals": total_metrics,
    }


def _paginate_daily_results(
    results: List[DailySpendData],
    *,
    page: int,
    page_size: int,
) -> List[DailySpendData]:
    start = (page - 1) * page_size
    return results[start : start + page_size]


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
    provider: Optional[str] = None,
    status_filter: Optional[str] = None,
    min_spend: Optional[float] = None,
    max_spend: Optional[float] = None,
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
        date_range = _utc_range_for_local_dates(
            start_date=start_date,
            end_date=end_date,
            timezone_offset_minutes=timezone_offset_minutes,
        )
        schema_state = await _probe_usage_schema(
            prisma_client,
            include_key_context=False,
            include_spend_logs=False,
        )
        if schema_state.schema_status == CavadaLabsUsageSchemaStatus.MISSING_SCHEMA:
            _raise_missing_usage_schema_http_exception(
                schema_state=schema_state,
                operation="read_cavadalabs_daily_activity",
            )
        where_conditions = _build_cavadalabs_ledger_where(
            entity_id_field=entity_id_field,
            entity_id=normalized_entity_id,
            date_range=date_range,
            model=model,
            provider=provider,
            status_filter=status_filter,
            api_key=api_key,
            min_spend=min_spend,
            max_spend=max_spend,
        )

        ledger_row_count = await prisma_client.db.cavadalabs_requestledgertable.count(
            where=where_conditions
        )
        if ledger_row_count == 0:
            await ensure_cavadalabs_usage_repair_schema_ready(
                prisma_client=prisma_client,
                operation="repair_empty_cavadalabs_daily_activity",
            )
            repaired = await _repair_empty_usage_ledger_from_spend_logs(
                prisma_client=prisma_client,
                entity_id_field=entity_id_field,
                entity_id=normalized_entity_id,
                date_range=date_range,
                model=model,
                provider=provider,
                api_key=api_key,
                status_filter=status_filter,
                min_spend=min_spend,
                max_spend=max_spend,
            )
            if repaired:
                ledger_row_count = (
                    await prisma_client.db.cavadalabs_requestledgertable.count(
                        where=where_conditions
                    )
                )
        else:
            repaired = await repair_incomplete_cavadalabs_usage_ledger_from_spend_logs(
                prisma_client=prisma_client,
                entity_id_field=entity_id_field,
                entity_id=normalized_entity_id,
                date_range=date_range,
                current_ledger_count=ledger_row_count,
                model=model,
                provider=provider,
                api_key=api_key,
                status_filter=status_filter,
                min_spend=min_spend,
                max_spend=max_spend,
            )
            if repaired:
                ledger_row_count = (
                    await prisma_client.db.cavadalabs_requestledgertable.count(
                        where=where_conditions
                    )
                )
        aggregated = await _aggregate_ledger_rows_by_day(
            prisma_client=prisma_client,
            where_conditions=where_conditions,
            entity_id_field=entity_id_field,
            timezone_offset_minutes=timezone_offset_minutes,
        )
        metadata_metrics = aggregated["totals"]
        total_daily_rows = len(aggregated["results"])
        paginated_results = _paginate_daily_results(
            aggregated["results"],
            page=page,
            page_size=page_size,
        )

        return SpendAnalyticsPaginatedResponse(
            results=paginated_results,
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
                total_pages=-(-total_daily_rows // page_size),
                has_more=(page * page_size) < total_daily_rows,
            ),
        )
    except HTTPException:
        raise
    except Exception as exc:
        if _looks_like_missing_schema_exception(exc):
            _raise_missing_usage_schema_http_exception(
                schema_state=_missing_usage_schema_state(
                    [f"CavadaLabs usage read path: {exc}"]
                ),
                operation="read_cavadalabs_daily_activity",
            )
        verbose_proxy_logger.exception(
            "Error fetching CavadaLabs daily activity: %s", str(exc)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": f"Failed to fetch CavadaLabs analytics: {str(exc)}"},
        ) from exc
