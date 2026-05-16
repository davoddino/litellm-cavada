from __future__ import annotations

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
    _aggregate_spend_records,
)
from litellm.proxy.utils import PrismaClient
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsUsageSchemaStatus,
)
from litellm.types.proxy.management_endpoints.common_daily_activity import (
    DailySpendMetadata,
    SpendAnalyticsPaginatedResponse,
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

        total_count = await prisma_client.db.cavadalabs_requestledgertable.count(
            where=where_conditions
        )
        if total_count == 0:
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
            )
            if repaired:
                total_count = (
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
                current_ledger_count=total_count,
                model=model,
                provider=provider,
                api_key=api_key,
            )
            if repaired:
                total_count = (
                    await prisma_client.db.cavadalabs_requestledgertable.count(
                        where=where_conditions
                    )
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
