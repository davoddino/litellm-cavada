from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from litellm._logging import verbose_proxy_logger
from litellm.proxy.cavadalabs.usage_backfill_scope import (
    _company_repair_scope,
    _project_repair_scope,
)
from litellm.proxy.cavadalabs.usage_key_context import (
    _set_payload_key_context,
)
from litellm.proxy.cavadalabs.usage_query_filters import (
    spend_log_repair_where as _spend_log_repair_where,
)
from litellm.proxy.cavadalabs.usage_serialization import (
    _normalize_entity_ids_list,
    _str_value,
)
from litellm.proxy.utils import PrismaClient

_USAGE_LEDGER_REPAIR_BATCH_SIZE = 1000
_SPEND_LOG_PAYLOAD_FIELDS = (
    "request_id",
    "call_type",
    "api_key",
    "spend",
    "total_tokens",
    "prompt_tokens",
    "completion_tokens",
    "startTime",
    "endTime",
    "model",
    "model_group",
    "custom_llm_provider",
    "metadata",
    "team_id",
    "organization_id",
    "session_id",
    "status",
    "request_tags",
)


@dataclass(frozen=True)
class CavadaLabsUsageLedgerBackfillResult:
    attempted: bool
    repaired: bool
    dry_run: bool
    batch_limit: Optional[int]
    scoped_spend_logs: int
    processed_spend_logs: int
    batches: int
    message: str


def _spend_log_row_to_payload(row: Any) -> Dict[str, Any]:
    if isinstance(row, dict):
        source = row
    elif hasattr(row, "model_dump"):
        source = row.model_dump()
    elif hasattr(row, "dict"):
        source = row.dict()
    else:
        source = {
            field_name: getattr(row, field_name, None)
            for field_name in _SPEND_LOG_PAYLOAD_FIELDS
        }

    payload = {}
    for field_name in _SPEND_LOG_PAYLOAD_FIELDS:
        value = source.get(field_name)
        if value is not None:
            payload[field_name] = value
    return payload


async def backfill_cavadalabs_usage_ledger_from_spend_logs(
    *,
    prisma_client: PrismaClient,
    entity_id_field: str,
    entity_id: Optional[Union[str, List[str]]],
    date_range: Dict[str, datetime],
    model: Optional[str],
    provider: Optional[str],
    api_key: Optional[Union[str, List[str]]],
    dry_run: bool = False,
    batch_limit: Optional[int] = None,
) -> CavadaLabsUsageLedgerBackfillResult:
    entity_ids = _normalize_entity_ids_list(entity_id)
    if not entity_ids:
        return CavadaLabsUsageLedgerBackfillResult(
            attempted=False,
            repaired=False,
            dry_run=dry_run,
            batch_limit=batch_limit,
            scoped_spend_logs=0,
            processed_spend_logs=0,
            batches=0,
            message="No Company/Project scope was selected for usage backfill.",
        )

    if entity_id_field == "company_id":
        scope = await _company_repair_scope(
            prisma_client=prisma_client,
            entity_ids=entity_ids,
        )
    elif entity_id_field == "project_id":
        scope = await _project_repair_scope(
            prisma_client=prisma_client,
            entity_ids=entity_ids,
        )
    else:
        return CavadaLabsUsageLedgerBackfillResult(
            attempted=False,
            repaired=False,
            dry_run=dry_run,
            batch_limit=batch_limit,
            scoped_spend_logs=0,
            processed_spend_logs=0,
            batches=0,
            message="Unsupported CavadaLabs usage repair scope.",
        )

    filters = scope.filters
    if not filters:
        return CavadaLabsUsageLedgerBackfillResult(
            attempted=False,
            repaired=False,
            dry_run=dry_run,
            batch_limit=batch_limit,
            scoped_spend_logs=0,
            processed_spend_logs=0,
            batches=0,
            message=(
                "No attributable SpendLogs scope was resolved from Company/Project "
                "metadata or compatibility mappings."
            ),
        )

    from litellm.proxy.cavadalabs.usage_tracking import (
        process_spend_logs_cavadalabs_ledger,
    )

    repaired_any = False
    offset = 0
    processed_spend_logs = 0
    batches = 0
    where = _spend_log_repair_where(
        date_range=date_range,
        filters=filters,
        model=model,
        provider=provider,
        api_key=api_key,
    )
    try:
        scoped_spend_logs: Optional[int] = int(
            await prisma_client.db.litellm_spendlogs.count(where=where)
        )
    except Exception as exc:
        verbose_proxy_logger.warning(
            "CavadaLabs usage repair could not count scoped SpendLogs: %s",
            exc,
        )
        scoped_spend_logs = None

    if dry_run:
        return CavadaLabsUsageLedgerBackfillResult(
            attempted=True,
            repaired=False,
            dry_run=True,
            batch_limit=batch_limit,
            scoped_spend_logs=scoped_spend_logs or 0,
            processed_spend_logs=0,
            batches=0,
            message=(
                "Dry run completed. Apply scoped backfill to mirror attributable "
                "SpendLogs into CavadaLabs usage ledger."
            ),
        )

    max_rows_to_process = batch_limit
    while True:
        if (
            max_rows_to_process is not None
            and processed_spend_logs >= max_rows_to_process
        ):
            return CavadaLabsUsageLedgerBackfillResult(
                attempted=True,
                repaired=repaired_any,
                dry_run=False,
                batch_limit=batch_limit,
                scoped_spend_logs=(
                    scoped_spend_logs
                    if scoped_spend_logs is not None
                    else processed_spend_logs
                ),
                processed_spend_logs=processed_spend_logs,
                batches=batches,
                message=(
                    "Scoped backfill reached the requested batch limit."
                    if batch_limit is not None
                    else "Scoped backfill completed."
                ),
            )
        take = _USAGE_LEDGER_REPAIR_BATCH_SIZE
        if max_rows_to_process is not None:
            take = min(take, max_rows_to_process - processed_spend_logs)
        spend_log_rows = await prisma_client.db.litellm_spendlogs.find_many(
            where=where,
            order=[{"startTime": "asc"}],
            skip=offset,
            take=take,
        )
        if not spend_log_rows:
            return CavadaLabsUsageLedgerBackfillResult(
                attempted=True,
                repaired=repaired_any,
                dry_run=False,
                batch_limit=batch_limit,
                scoped_spend_logs=(
                    scoped_spend_logs
                    if scoped_spend_logs is not None
                    else processed_spend_logs
                ),
                processed_spend_logs=processed_spend_logs,
                batches=batches,
                message="Scoped backfill completed.",
            )

        payloads = []
        for row in spend_log_rows:
            payload = _spend_log_row_to_payload(row)
            api_key_hash = _str_value(payload.get("api_key"))
            if api_key_hash in scope.key_context_by_api_key:
                payload = _set_payload_key_context(
                    payload,
                    scope.key_context_by_api_key[api_key_hash],
                )
            payloads.append(payload)
        created_ledger_rows = await process_spend_logs_cavadalabs_ledger(
            prisma_client=prisma_client,
            logs_to_process=payloads,
        )
        repaired_any = repaired_any or created_ledger_rows > 0
        processed_spend_logs += len(spend_log_rows)
        batches += 1
        if len(spend_log_rows) < take:
            return CavadaLabsUsageLedgerBackfillResult(
                attempted=True,
                repaired=repaired_any,
                dry_run=False,
                batch_limit=batch_limit,
                scoped_spend_logs=(
                    scoped_spend_logs
                    if scoped_spend_logs is not None
                    else processed_spend_logs
                ),
                processed_spend_logs=processed_spend_logs,
                batches=batches,
                message="Scoped backfill completed.",
            )
        offset += len(spend_log_rows)


async def _repair_empty_usage_ledger_from_spend_logs(
    *,
    prisma_client: PrismaClient,
    entity_id_field: str,
    entity_id: Optional[Union[str, List[str]]],
    date_range: Dict[str, datetime],
    model: Optional[str],
    provider: Optional[str],
    api_key: Optional[Union[str, List[str]]],
) -> bool:
    result = await backfill_cavadalabs_usage_ledger_from_spend_logs(
        prisma_client=prisma_client,
        entity_id_field=entity_id_field,
        entity_id=entity_id,
        date_range=date_range,
        model=model,
        provider=provider,
        api_key=api_key,
    )
    return result.repaired


async def _count_scoped_attributable_spend_logs(
    *,
    prisma_client: PrismaClient,
    entity_id_field: str,
    entity_id: Optional[Union[str, List[str]]],
    date_range: Dict[str, datetime],
    model: Optional[str],
    provider: Optional[str],
    api_key: Optional[Union[str, List[str]]],
) -> Optional[int]:
    entity_ids = _normalize_entity_ids_list(entity_id)
    if not entity_ids:
        return None

    if entity_id_field == "company_id":
        scope = await _company_repair_scope(
            prisma_client=prisma_client,
            entity_ids=entity_ids,
        )
    elif entity_id_field == "project_id":
        scope = await _project_repair_scope(
            prisma_client=prisma_client,
            entity_ids=entity_ids,
        )
    else:
        return None

    filters = scope.filters
    if not filters:
        return 0

    try:
        return int(
            await prisma_client.db.litellm_spendlogs.count(
                where=_spend_log_repair_where(
                    date_range=date_range,
                    filters=filters,
                    model=model,
                    provider=provider,
                    api_key=api_key,
                )
            )
        )
    except Exception as exc:
        verbose_proxy_logger.warning(
            "CavadaLabs usage repair skipped scoped SpendLogs count: %s",
            exc,
        )
        return None


async def repair_cavadalabs_usage_ledger_from_spend_logs(
    *,
    prisma_client: PrismaClient,
    entity_id_field: str,
    entity_id: Optional[Union[str, List[str]]],
    date_range: Dict[str, datetime],
    model: Optional[str] = None,
    provider: Optional[str] = None,
    api_key: Optional[Union[str, List[str]]] = None,
) -> bool:
    return await _repair_empty_usage_ledger_from_spend_logs(
        prisma_client=prisma_client,
        entity_id_field=entity_id_field,
        entity_id=entity_id,
        date_range=date_range,
        model=model,
        provider=provider,
        api_key=api_key,
    )


async def repair_incomplete_cavadalabs_usage_ledger_from_spend_logs(
    *,
    prisma_client: PrismaClient,
    entity_id_field: str,
    entity_id: Optional[Union[str, List[str]]],
    date_range: Dict[str, datetime],
    current_ledger_count: int,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    api_key: Optional[Union[str, List[str]]] = None,
) -> bool:
    attributable_spend_logs = await _count_scoped_attributable_spend_logs(
        prisma_client=prisma_client,
        entity_id_field=entity_id_field,
        entity_id=entity_id,
        date_range=date_range,
        model=model,
        provider=provider,
        api_key=api_key,
    )
    if (
        attributable_spend_logs is None
        or attributable_spend_logs <= current_ledger_count
    ):
        return False

    return await _repair_empty_usage_ledger_from_spend_logs(
        prisma_client=prisma_client,
        entity_id_field=entity_id_field,
        entity_id=entity_id,
        date_range=date_range,
        model=model,
        provider=provider,
        api_key=api_key,
    )
