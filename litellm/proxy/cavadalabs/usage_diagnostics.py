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
from litellm.proxy.cavadalabs.usage_diagnostics_readiness import (
    build_usage_readiness_checks,
)
from litellm.proxy.cavadalabs.usage_schema_readiness import (
    USAGE_BACKFILL_MIGRATION_COMMAND as _USAGE_BACKFILL_MIGRATION_COMMAND,
    USAGE_BACKFILL_MIGRATION_NAME as _USAGE_BACKFILL_MIGRATION_NAME,
    UsageSchemaState,
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


def _missing_schema_contains(missing_schema: List[str], *markers: str) -> bool:
    return any(
        all(marker in missing_item for marker in markers)
        for missing_item in missing_schema
    )


def _schema_availability_kwargs(schema_state: UsageSchemaState) -> dict:
    missing_schema = schema_state.missing_schema
    return {
        "ledger_table_available": not _missing_schema_contains(
            missing_schema,
            "CavadaLabs_RequestLedgerTable",
        ),
        "spend_logs_table_available": not _missing_schema_contains(
            missing_schema,
            "LiteLLM_SpendLogs",
        ),
        "key_context_available": not (
            _missing_schema_contains(missing_schema, "LiteLLM_VerificationToken")
            or _missing_schema_contains(
                missing_schema,
                "LiteLLM_DeletedVerificationToken",
            )
        ),
    }


def _operator_commands(
    *,
    entity_type: str,
) -> List[str]:
    entity_param = "company_ids" if entity_type == "company" else "project_ids"
    plural = "companies" if entity_type == "company" else "projects"
    entity_env = (
        "CAVADALABS_COMPANY_ID"
        if entity_type == "company"
        else "CAVADALABS_PROJECT_ID"
    )
    entity_shell_ref = f"${{{entity_env}}}"
    entity_column = "company_id" if entity_type == "company" else "project_id"
    ledger_filter = f"{entity_column} = :'entity_id'"
    repair_payload_command = (
        '"$(uv run python -c '
        f'\'import json, os; print(json.dumps({{"{entity_param}":'
        f'[os.environ["{entity_env}"]],'
        '"start_date":os.environ["CAVADALABS_START_DATE"],'
        '"end_date":os.environ["CAVADALABS_END_DATE"],'
        '"dry_run":True}))\')"'
    )
    return [
        (
            f"export {entity_env}='REPLACE_WITH_{entity_type.upper()}_ID' "
            "CAVADALABS_START_DATE='YYYY-MM-DD' "
            "CAVADALABS_END_DATE='YYYY-MM-DD'"
        ),
        (
            "DATABASE_URL='postgresql://USER:PASSWORD@HOST:PORT/DB' "
            "uv run prisma migrate status --schema "
            "litellm-proxy-extras/litellm_proxy_extras/schema.prisma"
        ),
        _USAGE_BACKFILL_MIGRATION_COMMAND,
        (
            f'psql "$DATABASE_URL" -v entity_id="{entity_shell_ref}" '
            '-v start_date="$CAVADALABS_START_DATE" '
            '-v end_date="$CAVADALABS_END_DATE" '
            '-c "select company_id, project_id, count(*) as ledger_rows, '
            "sum(spend) as total_spend, min(created_at) as first_seen, "
            'max(created_at) as last_seen from \\"CavadaLabs_RequestLedgerTable\\" '
            f"where {ledger_filter} and created_at >= :'start_date'::date "
            "and created_at < (:'end_date'::date + interval '1 day') "
            'group by company_id, project_id order by company_id, project_id;"'
        ),
        (
            "curl -sS -H 'Authorization: Bearer $LITELLM_API_KEY' "
            "-G "
            f'"$LITELLM_PROXY_URL/cavadalabs/{plural}/usage/diagnostics" '
            '--data-urlencode "start_date=$CAVADALABS_START_DATE" '
            '--data-urlencode "end_date=$CAVADALABS_END_DATE" '
            f'--data-urlencode "{entity_param}={entity_shell_ref}"'
        ),
        (
            "curl -sS -X POST -H 'Authorization: Bearer $LITELLM_API_KEY' "
            "-H 'Content-Type: application/json' "
            f'"$LITELLM_PROXY_URL/cavadalabs/{plural}/usage/repair" '
            f"-d {repair_payload_command}"
        ),
    ]


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
    status_filter: Optional[str] = None,
    min_spend: Optional[float] = None,
    max_spend: Optional[float] = None,
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
            operator_commands=[],
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
                **_schema_availability_kwargs(schema_state),
                migration_names=_usage_backfill_migration_names(),
                migration_plan=_usage_backfill_migration_steps(),
                operator_commands=_operator_commands(
                    entity_type=entity_type,
                ),
                readiness_checks=build_usage_readiness_checks(
                    schema_state=schema_state,
                    diagnostics=diagnostics,
                ),
            )

        if entity_type == "company":
            diagnostics = await _company_usage_diagnostics(
                prisma_client=prisma_client,
                entity_ids=entity_ids,
                date_range=date_range,
                model=model,
                provider=provider,
                api_key=api_key,
                status_filter=status_filter,
                min_spend=min_spend,
                max_spend=max_spend,
            )
        else:
            diagnostics = await _project_usage_diagnostics(
                prisma_client=prisma_client,
                entity_ids=entity_ids,
                date_range=date_range,
                model=model,
                provider=provider,
                api_key=api_key,
                status_filter=status_filter,
                min_spend=min_spend,
                max_spend=max_spend,
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
            **_schema_availability_kwargs(schema_state),
            migration_names=_usage_backfill_migration_names(),
            migration_plan=_usage_backfill_migration_steps(),
            operator_commands=_operator_commands(
                entity_type=entity_type,
            ),
            readiness_checks=build_usage_readiness_checks(
                schema_state=schema_state,
                diagnostics=diagnostics,
            ),
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
    status_filter: Optional[str] = None,
    min_spend: Optional[float] = None,
    max_spend: Optional[float] = None,
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
                readiness_checks=build_usage_readiness_checks(
                    schema_state=schema_state,
                    diagnostics=diagnostics,
                ),
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
            status_filter=status_filter,
            min_spend=min_spend,
            max_spend=max_spend,
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
                status_filter=status_filter,
                min_spend=min_spend,
                max_spend=max_spend,
            )
        else:
            diagnostics = await _project_usage_diagnostics(
                prisma_client=prisma_client,
                entity_ids=entity_ids,
                date_range=date_range,
                model=model,
                provider=provider,
                api_key=api_key,
                status_filter=status_filter,
                min_spend=min_spend,
                max_spend=max_spend,
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
            readiness_checks=build_usage_readiness_checks(
                schema_state=schema_state,
                diagnostics=diagnostics,
            ),
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
