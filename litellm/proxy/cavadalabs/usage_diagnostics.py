from __future__ import annotations

from typing import List, Optional, Union

from fastapi import HTTPException, status

from litellm._logging import verbose_proxy_logger
from litellm.proxy._types import CommonProxyErrors
from litellm.proxy.cavadalabs.usage_backfill import (
    backfill_cavadalabs_usage_ledger_from_spend_logs,
)
from litellm.proxy.cavadalabs.usage_diagnostics_items import (
    _company_usage_diagnostics,
    _project_usage_diagnostics,
)
from litellm.proxy.cavadalabs.usage_schema_readiness import (
    USAGE_BACKFILL_MIGRATION_COMMAND as _USAGE_BACKFILL_MIGRATION_COMMAND,
    USAGE_BACKFILL_MIGRATION_NAME as _USAGE_BACKFILL_MIGRATION_NAME,
    diagnostics_migration_status as _diagnostics_migration_status,
    probe_usage_schema as _probe_usage_schema,
    schema_missing_diagnostics as _schema_missing_diagnostics,
    usage_backfill_migration_names as _usage_backfill_migration_names,
    usage_backfill_migration_steps as _usage_backfill_migration_steps,
)
from litellm.proxy.cavadalabs.usage_serialization import (
    _normalize_entity_ids_list,
    _utc_range_for_local_dates,
)
from litellm.proxy.utils import PrismaClient
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsUsageDiagnosticsResponse,
    CavadaLabsUsageMigrationStatus,
    CavadaLabsUsageRepairResponse,
    CavadaLabsUsageSchemaStatus,
)


async def get_cavadalabs_usage_diagnostics(
    *,
    prisma_client: Optional[PrismaClient],
    entity_type: str,
    entity_id: Optional[Union[str, List[str]]],
    start_date: Optional[str],
    end_date: Optional[str],
    timezone_offset_minutes: Optional[int],
    model: Optional[str] = None,
    provider: Optional[str] = None,
    api_key: Optional[Union[str, List[str]]] = None,
) -> CavadaLabsUsageDiagnosticsResponse:
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
    if entity_type not in {"company", "project"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "entity_type must be company or project"},
        )

    entity_ids = _normalize_entity_ids_list(entity_id)
    if not entity_ids:
        return CavadaLabsUsageDiagnosticsResponse(
            diagnostics=[],
            migration_name=_USAGE_BACKFILL_MIGRATION_NAME,
            migration_command=_USAGE_BACKFILL_MIGRATION_COMMAND,
            schema_status=CavadaLabsUsageSchemaStatus.READY,
            migration_status=CavadaLabsUsageMigrationStatus.READY,
            missing_schema=[],
            migration_names=_usage_backfill_migration_names(),
            migration_plan=_usage_backfill_migration_steps(),
        )

    try:
        date_range = _utc_range_for_local_dates(
            start_date=start_date,
            end_date=end_date,
            timezone_offset_minutes=timezone_offset_minutes,
        )
        schema_state = await _probe_usage_schema(
            prisma_client,
            include_key_context=True,
        )
        if schema_state.schema_status == CavadaLabsUsageSchemaStatus.MISSING_SCHEMA:
            diagnostics = _schema_missing_diagnostics(
                entity_type=entity_type,
                entity_ids=entity_ids,
                missing_schema=schema_state.missing_schema,
            )
            return CavadaLabsUsageDiagnosticsResponse(
                diagnostics=diagnostics,
                migration_name=_USAGE_BACKFILL_MIGRATION_NAME,
                migration_command=_USAGE_BACKFILL_MIGRATION_COMMAND,
                schema_status=schema_state.schema_status,
                migration_status=schema_state.migration_status,
                missing_schema=schema_state.missing_schema,
                migration_names=_usage_backfill_migration_names(),
                migration_plan=_usage_backfill_migration_steps(),
            )

        if entity_type == "company":
            diagnostics = await _company_usage_diagnostics(
                prisma_client=prisma_client,
                entity_ids=entity_ids,
                date_range=date_range,
                model=model,
                provider=provider,
                api_key=api_key,
            )
        else:
            diagnostics = await _project_usage_diagnostics(
                prisma_client=prisma_client,
                entity_ids=entity_ids,
                date_range=date_range,
                model=model,
                provider=provider,
                api_key=api_key,
            )

        return CavadaLabsUsageDiagnosticsResponse(
            diagnostics=diagnostics,
            migration_name=_USAGE_BACKFILL_MIGRATION_NAME,
            migration_command=_USAGE_BACKFILL_MIGRATION_COMMAND,
            schema_status=schema_state.schema_status,
            migration_status=_diagnostics_migration_status(
                schema_state=schema_state,
                diagnostics=diagnostics,
            ),
            missing_schema=schema_state.missing_schema,
            migration_names=_usage_backfill_migration_names(),
            migration_plan=_usage_backfill_migration_steps(),
        )
    except HTTPException:
        raise
    except Exception as exc:
        verbose_proxy_logger.exception(
            "Error fetching CavadaLabs usage diagnostics: %s", str(exc)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": f"Failed to fetch CavadaLabs usage diagnostics: {str(exc)}"
            },
        ) from exc


async def repair_cavadalabs_usage_scope(
    *,
    prisma_client: Optional[PrismaClient],
    entity_type: str,
    entity_id: Optional[Union[str, List[str]]],
    start_date: Optional[str],
    end_date: Optional[str],
    timezone_offset_minutes: Optional[int],
    model: Optional[str] = None,
    provider: Optional[str] = None,
    api_key: Optional[Union[str, List[str]]] = None,
    dry_run: bool = False,
    batch_limit: Optional[int] = None,
) -> CavadaLabsUsageRepairResponse:
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
    if entity_type not in {"company", "project"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "entity_type must be company or project"},
        )

    entity_ids = _normalize_entity_ids_list(entity_id)
    if not entity_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Select at least one Company or Project for scoped usage repair"
            },
        )

    try:
        date_range = _utc_range_for_local_dates(
            start_date=start_date,
            end_date=end_date,
            timezone_offset_minutes=timezone_offset_minutes,
        )
        schema_state = await _probe_usage_schema(
            prisma_client,
            include_key_context=True,
        )
        if schema_state.schema_status == CavadaLabsUsageSchemaStatus.MISSING_SCHEMA:
            diagnostics = _schema_missing_diagnostics(
                entity_type=entity_type,
                entity_ids=entity_ids,
                missing_schema=schema_state.missing_schema,
            )
            return CavadaLabsUsageRepairResponse(
                entity_type=entity_type,
                entity_ids=entity_ids,
                attempted=False,
                repaired=False,
                dry_run=dry_run,
                batch_limit=batch_limit,
                scoped_spend_logs=0,
                processed_spend_logs=0,
                batches=0,
                message=(
                    "CavadaLabs usage schema is missing. Run the migration "
                    "command before scoped backfill."
                ),
                diagnostics=diagnostics,
                migration_name=_USAGE_BACKFILL_MIGRATION_NAME,
                migration_command=_USAGE_BACKFILL_MIGRATION_COMMAND,
                schema_status=schema_state.schema_status,
                migration_status=schema_state.migration_status,
                missing_schema=schema_state.missing_schema,
                migration_names=_usage_backfill_migration_names(),
                migration_plan=_usage_backfill_migration_steps(),
            )

        entity_id_field = "company_id" if entity_type == "company" else "project_id"
        result = await backfill_cavadalabs_usage_ledger_from_spend_logs(
            prisma_client=prisma_client,
            entity_id_field=entity_id_field,
            entity_id=entity_ids,
            date_range=date_range,
            model=model,
            provider=provider,
            api_key=api_key,
            dry_run=dry_run,
            batch_limit=batch_limit,
        )
        if entity_type == "company":
            diagnostics = await _company_usage_diagnostics(
                prisma_client=prisma_client,
                entity_ids=entity_ids,
                date_range=date_range,
                model=model,
                provider=provider,
                api_key=api_key,
            )
        else:
            diagnostics = await _project_usage_diagnostics(
                prisma_client=prisma_client,
                entity_ids=entity_ids,
                date_range=date_range,
                model=model,
                provider=provider,
                api_key=api_key,
            )
        return CavadaLabsUsageRepairResponse(
            entity_type=entity_type,
            entity_ids=entity_ids,
            attempted=result.attempted,
            repaired=result.repaired,
            dry_run=result.dry_run,
            batch_limit=result.batch_limit,
            scoped_spend_logs=result.scoped_spend_logs,
            processed_spend_logs=result.processed_spend_logs,
            batches=result.batches,
            message=result.message,
            diagnostics=diagnostics,
            migration_name=_USAGE_BACKFILL_MIGRATION_NAME,
            migration_command=_USAGE_BACKFILL_MIGRATION_COMMAND,
            schema_status=schema_state.schema_status,
            migration_status=_diagnostics_migration_status(
                schema_state=schema_state,
                diagnostics=diagnostics,
            ),
            missing_schema=schema_state.missing_schema,
            migration_names=_usage_backfill_migration_names(),
            migration_plan=_usage_backfill_migration_steps(),
        )
    except HTTPException:
        raise
    except Exception as exc:
        verbose_proxy_logger.exception(
            "Error repairing CavadaLabs usage scope: %s", str(exc)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": f"Failed to repair CavadaLabs usage: {str(exc)}"},
        ) from exc
