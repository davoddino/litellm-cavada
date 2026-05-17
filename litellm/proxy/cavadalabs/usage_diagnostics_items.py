from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from litellm.proxy.cavadalabs.usage_backfill_scope import (
    _UsageRepairScope,
    _company_repair_scope,
    _count_attributable_spend_logs,
    _count_project_company_metadata_conflicts,
    _count_scope_breakdown,
    _project_repair_scope,
    _UsageDiagnosticBreakdown,
)
from litellm.proxy.cavadalabs.usage_diagnostics_rules import (
    _usage_diagnostics_action,
    _usage_diagnostics_message,
    _usage_diagnostics_status,
)
from litellm.proxy.cavadalabs.usage_serialization import (
    _build_cavadalabs_ledger_where,
    _row_value,
    _str_value,
)
from litellm.proxy.utils import PrismaClient
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsUsageDiagnosticsItem,
    CavadaLabsUsageDiagnosticsStatus,
    CavadaLabsUsageRepairDryRunStatus,
)

_LEDGER_STATS_FETCH_PAGE_SIZE = 1000
_CONFLICTING_PROJECT_COMPANY_MAPPING = (
    "SpendLogs metadata with CavadaLabs project_id uses a different "
    "CavadaLabs company_id"
)


@dataclass(frozen=True)
class _LedgerUsageStats:
    total_spend: float = 0.0
    min_created_at: Optional[datetime] = None
    max_created_at: Optional[datetime] = None


def _float_value(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _datetime_value(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _update_min_datetime(
    current: Optional[datetime],
    candidate: Optional[datetime],
) -> Optional[datetime]:
    if candidate is None:
        return current
    if current is None or candidate < current:
        return candidate
    return current


def _update_max_datetime(
    current: Optional[datetime],
    candidate: Optional[datetime],
) -> Optional[datetime]:
    if candidate is None:
        return current
    if current is None or candidate > current:
        return candidate
    return current


async def _ledger_usage_stats(
    *,
    prisma_client: PrismaClient,
    where: Dict[str, Any],
    ledger_rows: int,
) -> _LedgerUsageStats:
    if ledger_rows <= 0:
        return _LedgerUsageStats()

    skip = 0
    total_spend = 0.0
    min_created_at: Optional[datetime] = None
    max_created_at: Optional[datetime] = None
    while True:
        rows = await prisma_client.db.cavadalabs_requestledgertable.find_many(
            where=where,
            order={"created_at": "asc"},
            skip=skip,
            take=_LEDGER_STATS_FETCH_PAGE_SIZE,
            select={"spend": True, "created_at": True},
        )
        if not rows:
            break
        for row in rows:
            total_spend += _float_value(_row_value(row, "spend"))
            created_at = _datetime_value(_row_value(row, "created_at"))
            min_created_at = _update_min_datetime(min_created_at, created_at)
            max_created_at = _update_max_datetime(max_created_at, created_at)
        if len(rows) < _LEDGER_STATS_FETCH_PAGE_SIZE:
            break
        skip += len(rows)
    return _LedgerUsageStats(
        total_spend=total_spend,
        min_created_at=min_created_at,
        max_created_at=max_created_at,
    )


async def _count_safe_attributable_spend_logs(
    *,
    prisma_client: PrismaClient,
    date_range: Optional[Dict[str, datetime]],
    filters: List[Dict[str, Any]],
    project_company_by_id: Dict[str, str],
    key_context_by_api_key: Dict[str, Any],
    model: Optional[str],
    provider: Optional[str],
    api_key: Optional[Union[str, List[str]]],
    status_filter: Optional[str],
    min_spend: Optional[float],
    max_spend: Optional[float],
) -> tuple[int, int]:
    attributable_spend_logs = await _count_attributable_spend_logs(
        prisma_client=prisma_client,
        date_range=date_range,
        filters=filters,
        model=model,
        provider=provider,
        api_key=api_key,
        status_filter=status_filter,
        min_spend=min_spend,
        max_spend=max_spend,
    )
    if attributable_spend_logs <= 0 or not project_company_by_id:
        return attributable_spend_logs, 0

    metadata_conflicts = await _count_project_company_metadata_conflicts(
        prisma_client=prisma_client,
        project_company_by_id=project_company_by_id,
        key_context_by_api_key=key_context_by_api_key,
        date_range=date_range,
        model=model,
        provider=provider,
        api_key=api_key,
        status_filter=status_filter,
        min_spend=min_spend,
        max_spend=max_spend,
    )
    return max(attributable_spend_logs - metadata_conflicts, 0), metadata_conflicts


def _breakdown_with_metadata_conflicts(
    breakdown: _UsageDiagnosticBreakdown,
    metadata_conflicts: int,
) -> _UsageDiagnosticBreakdown:
    if metadata_conflicts <= 0:
        return breakdown
    additional_unmapped = max(metadata_conflicts - breakdown.unmapped_spend_logs, 0)
    return replace(
        breakdown,
        metadata_spend_logs=max(breakdown.metadata_spend_logs - metadata_conflicts, 0),
        unmapped_spend_logs=breakdown.unmapped_spend_logs + additional_unmapped,
    )


def _append_metadata_conflict_mapping(
    missing_mappings: List[str],
    metadata_conflicts: int,
) -> None:
    if (
        metadata_conflicts > 0
        and _CONFLICTING_PROJECT_COMPANY_MAPPING not in missing_mappings
    ):
        missing_mappings.append(_CONFLICTING_PROJECT_COMPANY_MAPPING)


def _repair_dry_run_status(
    *,
    scope_filters: List[Dict[str, Any]],
    ledger_rows: int,
    attributable_spend_logs: int,
    ledger_gap: int,
    missing_mappings: List[str],
) -> CavadaLabsUsageRepairDryRunStatus:
    attempted = bool(scope_filters)
    would_repair = attributable_spend_logs > ledger_rows
    if not attempted:
        message = (
            "Scoped repair dry-run was not attempted because no Company/Project "
            "metadata or compatibility mapping resolved to SpendLogs."
        )
    elif would_repair:
        message = (
            "Scoped repair dry-run found attributable SpendLogs that are missing "
            "from the CavadaLabs request ledger."
        )
    elif missing_mappings:
        message = (
            "Scoped repair dry-run found missing Company/Project attribution "
            "inputs before a safe repair can run."
        )
    else:
        message = "Scoped repair dry-run found no missing ledger rows."

    return CavadaLabsUsageRepairDryRunStatus(
        attempted=attempted,
        available=attempted and would_repair,
        would_repair=would_repair,
        scoped_spend_logs=attributable_spend_logs,
        missing_ledger_rows=ledger_gap,
        message=message,
    )


async def _company_usage_diagnostics(
    *,
    prisma_client: PrismaClient,
    entity_ids: List[str],
    date_range: Dict[str, datetime],
    model: Optional[str] = None,
    provider: Optional[str] = None,
    api_key: Optional[Union[str, List[str]]] = None,
    status_filter: Optional[str] = None,
    min_spend: Optional[float] = None,
    max_spend: Optional[float] = None,
) -> List[CavadaLabsUsageDiagnosticsItem]:
    company_rows = await prisma_client.db.cavadalabs_companytable.find_many(
        where={"company_id": {"in": entity_ids}}
    )
    companies_by_id = {row.company_id: row for row in company_rows}
    project_rows = await prisma_client.db.cavadalabs_projecttable.find_many(
        where={"company_id": {"in": entity_ids}}
    )
    team_ids_by_company: Dict[str, List[str]] = {}
    project_ids_by_company: Dict[str, List[str]] = {}
    for row in project_rows:
        team_id = getattr(row, "litellm_team_id", None)
        company_id = getattr(row, "company_id", None)
        project_id = getattr(row, "project_id", None)
        if isinstance(project_id, str) and project_id.strip() and company_id:
            project_ids_by_company.setdefault(company_id, []).append(project_id)
        if isinstance(team_id, str) and team_id.strip() and company_id:
            team_ids_by_company.setdefault(company_id, []).append(team_id)

    diagnostics: List[CavadaLabsUsageDiagnosticsItem] = []
    for company_id in entity_ids:
        ledger_where = _build_cavadalabs_ledger_where(
            entity_id_field="company_id",
            entity_id=company_id,
            date_range=date_range,
            model=model,
            provider=provider,
            status_filter=status_filter,
            api_key=api_key,
            min_spend=min_spend,
            max_spend=max_spend,
        )
        ledger_rows = int(
            await prisma_client.db.cavadalabs_requestledgertable.count(
                where=ledger_where
            )
        )
        ledger_stats = await _ledger_usage_stats(
            prisma_client=prisma_client,
            where=ledger_where,
            ledger_rows=ledger_rows,
        )
        company_team_ids = sorted(set(team_ids_by_company.get(company_id, [])))
        company = companies_by_id.get(company_id)
        scope = await _company_repair_scope(
            prisma_client=prisma_client,
            entity_ids=[company_id],
        )
        filters = scope.filters
        missing_mappings: List[str] = []
        if company is None:
            missing_mappings.append("CavadaLabs company row")
        if (
            company is not None
            and not company_team_ids
            and not getattr(company, "litellm_organization_id", None)
            and not scope.key_context_by_api_key
        ):
            missing_mappings.append(
                "litellm_organization_id, project litellm_team_id, or CavadaLabs key metadata"
            )

        company_project_company_by_id = {
            project_id: company_id
            for project_id in sorted(set(project_ids_by_company.get(company_id, [])))
        }
        attributable_spend_logs, metadata_conflicts = (
            await _count_safe_attributable_spend_logs(
                prisma_client=prisma_client,
                date_range=date_range,
                filters=filters,
                project_company_by_id=company_project_company_by_id,
                key_context_by_api_key=scope.key_context_by_api_key,
                model=model,
                provider=provider,
                api_key=api_key,
                status_filter=status_filter,
                min_spend=min_spend,
                max_spend=max_spend,
            )
        )
        _append_metadata_conflict_mapping(missing_mappings, metadata_conflicts)
        attributable_count_args = dict(
            prisma_client=prisma_client,
            filters=filters,
            project_company_by_id=company_project_company_by_id,
            key_context_by_api_key=scope.key_context_by_api_key,
        )
        litellm_organization_id = (
            _str_value(_row_value(company, "litellm_organization_id"))
            if company is not None
            else None
        )
        breakdown = await _count_scope_breakdown(
            prisma_client=prisma_client,
            date_range=date_range,
            scope=scope,
            model=model,
            provider=provider,
            api_key=api_key,
            status_filter=status_filter,
            min_spend=min_spend,
            max_spend=max_spend,
            unmapped_candidate_filters=(
                [{"organization_id": litellm_organization_id}]
                if litellm_organization_id is not None
                else None
            ),
            attributable_spend_logs=attributable_spend_logs,
        )
        breakdown = _breakdown_with_metadata_conflicts(
            breakdown,
            metadata_conflicts,
        )
        unfiltered_attributable_spend_logs = 0
        all_time_attributable_spend_logs = 0
        filters_exclude_usage = False
        date_range_excludes_usage = False
        if attributable_spend_logs == 0 and (
            model
            or provider
            or api_key
            or status_filter
            or min_spend is not None
            or max_spend is not None
        ):
            unfiltered_attributable_spend_logs, _ = (
                await _count_safe_attributable_spend_logs(
                    **attributable_count_args,
                    date_range=date_range,
                    model=None,
                    provider=None,
                    api_key=None,
                    status_filter=None,
                    min_spend=None,
                    max_spend=None,
                )
            )
            filters_exclude_usage = unfiltered_attributable_spend_logs > 0
        if attributable_spend_logs == 0 and not filters_exclude_usage:
            all_time_attributable_spend_logs, _ = (
                await _count_safe_attributable_spend_logs(
                    **attributable_count_args,
                    date_range=None,
                    model=None,
                    provider=None,
                    api_key=None,
                    status_filter=None,
                    min_spend=None,
                    max_spend=None,
                )
            )
            date_range_excludes_usage = all_time_attributable_spend_logs > 0
        item_status = _usage_diagnostics_status(
            ledger_rows=ledger_rows,
            attributable_spend_logs=attributable_spend_logs,
            missing_mappings=missing_mappings,
            unmapped_spend_logs=breakdown.unmapped_spend_logs,
            filters_exclude_usage=filters_exclude_usage,
            date_range_excludes_usage=date_range_excludes_usage,
            legacy_key_spend_logs=breakdown.legacy_key_spend_logs,
        )
        if (
            item_status
            == CavadaLabsUsageDiagnosticsStatus.MISSING_COMPATIBILITY_MAPPING
            and (
                breakdown.unmapped_spend_logs > 0 or breakdown.legacy_key_spend_logs > 0
            )
            and not missing_mappings
        ):
            missing_mappings = [
                "CavadaLabs key metadata or Project compatibility mapping"
            ]
        ledger_gap = max(attributable_spend_logs - ledger_rows, 0)
        repair_dry_run = _repair_dry_run_status(
            scope_filters=filters,
            ledger_rows=ledger_rows,
            attributable_spend_logs=attributable_spend_logs,
            ledger_gap=ledger_gap,
            missing_mappings=missing_mappings,
        )
        diagnostics.append(
            CavadaLabsUsageDiagnosticsItem(
                entity_type="company",
                entity_id=company_id,
                status=item_status,
                ledger_rows=ledger_rows,
                ledger_total_spend=ledger_stats.total_spend,
                ledger_min_created_at=ledger_stats.min_created_at,
                ledger_max_created_at=ledger_stats.max_created_at,
                attributable_spend_logs=attributable_spend_logs,
                metadata_spend_logs=breakdown.metadata_spend_logs,
                compatibility_spend_logs=breakdown.compatibility_spend_logs,
                key_metadata_spend_logs=breakdown.key_metadata_spend_logs,
                legacy_keys_missing_metadata=(breakdown.legacy_keys_missing_metadata),
                legacy_key_spend_logs=breakdown.legacy_key_spend_logs,
                unmapped_spend_logs=breakdown.unmapped_spend_logs,
                unfiltered_attributable_spend_logs=(unfiltered_attributable_spend_logs),
                all_time_attributable_spend_logs=all_time_attributable_spend_logs,
                ledger_gap=ledger_gap,
                missing_ledger_rows=ledger_gap,
                recommended_action=_usage_diagnostics_action(item_status),
                scoped_backfill_available=(
                    item_status
                    == CavadaLabsUsageDiagnosticsStatus.SCOPED_BACKFILL_AVAILABLE
                ),
                filters_exclude_usage=filters_exclude_usage,
                date_range_excludes_usage=date_range_excludes_usage,
                missing_mappings=missing_mappings,
                repair_dry_run=repair_dry_run,
                message=_usage_diagnostics_message(
                    entity_type="company",
                    status=item_status,
                    missing_mappings=missing_mappings,
                    unmapped_spend_logs=breakdown.unmapped_spend_logs,
                    legacy_key_spend_logs=breakdown.legacy_key_spend_logs,
                    filters_exclude_usage=filters_exclude_usage,
                    date_range_excludes_usage=date_range_excludes_usage,
                ),
            )
        )
    return diagnostics


async def _project_usage_diagnostics(
    *,
    prisma_client: PrismaClient,
    entity_ids: List[str],
    date_range: Dict[str, datetime],
    model: Optional[str] = None,
    provider: Optional[str] = None,
    api_key: Optional[Union[str, List[str]]] = None,
    status_filter: Optional[str] = None,
    min_spend: Optional[float] = None,
    max_spend: Optional[float] = None,
) -> List[CavadaLabsUsageDiagnosticsItem]:
    project_rows = await prisma_client.db.cavadalabs_projecttable.find_many(
        where={"project_id": {"in": entity_ids}}
    )
    projects_by_id = {row.project_id: row for row in project_rows}

    diagnostics: List[CavadaLabsUsageDiagnosticsItem] = []
    for project_id in entity_ids:
        ledger_where = _build_cavadalabs_ledger_where(
            entity_id_field="project_id",
            entity_id=project_id,
            date_range=date_range,
            model=model,
            provider=provider,
            status_filter=status_filter,
            api_key=api_key,
            min_spend=min_spend,
            max_spend=max_spend,
        )
        ledger_rows = int(
            await prisma_client.db.cavadalabs_requestledgertable.count(
                where=ledger_where
            )
        )
        ledger_stats = await _ledger_usage_stats(
            prisma_client=prisma_client,
            where=ledger_where,
            ledger_rows=ledger_rows,
        )
        missing_mappings = []
        project = projects_by_id.get(project_id)
        if project is None:
            missing_mappings.append("CavadaLabs project row")
            filters = []
            scope = _UsageRepairScope(
                filters=[],
                key_context_by_api_key={},
                legacy_key_hashes_missing_metadata=[],
                metadata_filters=[],
                compatibility_filters=[],
                key_metadata_filters=[],
            )
            project_project_company_by_id: Dict[str, str] = {}
        else:
            scope = await _project_repair_scope(
                prisma_client=prisma_client,
                entity_ids=[project_id],
            )
            filters = scope.filters
            project_company_id = _str_value(_row_value(project, "company_id"))
            project_project_company_by_id = (
                {project_id: project_company_id}
                if project_company_id is not None
                else {}
            )
            litellm_team_id = getattr(project, "litellm_team_id", None)
            if (
                not isinstance(litellm_team_id, str) or not litellm_team_id.strip()
            ) and not scope.key_context_by_api_key:
                missing_mappings.append(
                    "project litellm_team_id or CavadaLabs key metadata"
                )

        attributable_spend_logs, metadata_conflicts = (
            await _count_safe_attributable_spend_logs(
                prisma_client=prisma_client,
                date_range=date_range,
                filters=filters,
                project_company_by_id=project_project_company_by_id,
                key_context_by_api_key=scope.key_context_by_api_key,
                model=model,
                provider=provider,
                api_key=api_key,
                status_filter=status_filter,
                min_spend=min_spend,
                max_spend=max_spend,
            )
        )
        _append_metadata_conflict_mapping(missing_mappings, metadata_conflicts)
        attributable_count_args = dict(
            prisma_client=prisma_client,
            filters=filters,
            project_company_by_id=project_project_company_by_id,
            key_context_by_api_key=scope.key_context_by_api_key,
        )
        litellm_team_id = (
            _str_value(_row_value(project, "litellm_team_id"))
            if project is not None
            else None
        )
        breakdown = await _count_scope_breakdown(
            prisma_client=prisma_client,
            date_range=date_range,
            scope=(
                scope
                if project is not None
                else _UsageRepairScope(
                    filters=[],
                    key_context_by_api_key={},
                    legacy_key_hashes_missing_metadata=[],
                    metadata_filters=[],
                    compatibility_filters=[],
                    key_metadata_filters=[],
                )
            ),
            model=model,
            provider=provider,
            api_key=api_key,
            status_filter=status_filter,
            min_spend=min_spend,
            max_spend=max_spend,
            unmapped_candidate_filters=(
                [{"team_id": litellm_team_id}] if litellm_team_id is not None else None
            ),
            attributable_spend_logs=attributable_spend_logs,
        )
        breakdown = _breakdown_with_metadata_conflicts(
            breakdown,
            metadata_conflicts,
        )
        unfiltered_attributable_spend_logs = 0
        all_time_attributable_spend_logs = 0
        filters_exclude_usage = False
        date_range_excludes_usage = False
        if attributable_spend_logs == 0 and (
            model
            or provider
            or api_key
            or status_filter
            or min_spend is not None
            or max_spend is not None
        ):
            unfiltered_attributable_spend_logs, _ = (
                await _count_safe_attributable_spend_logs(
                    **attributable_count_args,
                    date_range=date_range,
                    model=None,
                    provider=None,
                    api_key=None,
                    status_filter=None,
                    min_spend=None,
                    max_spend=None,
                )
            )
            filters_exclude_usage = unfiltered_attributable_spend_logs > 0
        if attributable_spend_logs == 0 and not filters_exclude_usage:
            all_time_attributable_spend_logs, _ = (
                await _count_safe_attributable_spend_logs(
                    **attributable_count_args,
                    date_range=None,
                    model=None,
                    provider=None,
                    api_key=None,
                    status_filter=None,
                    min_spend=None,
                    max_spend=None,
                )
            )
            date_range_excludes_usage = all_time_attributable_spend_logs > 0
        item_status = _usage_diagnostics_status(
            ledger_rows=ledger_rows,
            attributable_spend_logs=attributable_spend_logs,
            missing_mappings=missing_mappings,
            unmapped_spend_logs=breakdown.unmapped_spend_logs,
            filters_exclude_usage=filters_exclude_usage,
            date_range_excludes_usage=date_range_excludes_usage,
            legacy_key_spend_logs=breakdown.legacy_key_spend_logs,
        )
        if (
            item_status
            == CavadaLabsUsageDiagnosticsStatus.MISSING_COMPATIBILITY_MAPPING
            and (
                breakdown.unmapped_spend_logs > 0 or breakdown.legacy_key_spend_logs > 0
            )
            and not missing_mappings
        ):
            missing_mappings = [
                "CavadaLabs key metadata or Project compatibility mapping"
            ]
        ledger_gap = max(attributable_spend_logs - ledger_rows, 0)
        repair_dry_run = _repair_dry_run_status(
            scope_filters=filters,
            ledger_rows=ledger_rows,
            attributable_spend_logs=attributable_spend_logs,
            ledger_gap=ledger_gap,
            missing_mappings=missing_mappings,
        )
        diagnostics.append(
            CavadaLabsUsageDiagnosticsItem(
                entity_type="project",
                entity_id=project_id,
                status=item_status,
                ledger_rows=ledger_rows,
                ledger_total_spend=ledger_stats.total_spend,
                ledger_min_created_at=ledger_stats.min_created_at,
                ledger_max_created_at=ledger_stats.max_created_at,
                attributable_spend_logs=attributable_spend_logs,
                metadata_spend_logs=breakdown.metadata_spend_logs,
                compatibility_spend_logs=breakdown.compatibility_spend_logs,
                key_metadata_spend_logs=breakdown.key_metadata_spend_logs,
                legacy_keys_missing_metadata=(breakdown.legacy_keys_missing_metadata),
                legacy_key_spend_logs=breakdown.legacy_key_spend_logs,
                unmapped_spend_logs=breakdown.unmapped_spend_logs,
                unfiltered_attributable_spend_logs=(unfiltered_attributable_spend_logs),
                all_time_attributable_spend_logs=all_time_attributable_spend_logs,
                ledger_gap=ledger_gap,
                missing_ledger_rows=ledger_gap,
                recommended_action=_usage_diagnostics_action(item_status),
                scoped_backfill_available=(
                    item_status
                    == CavadaLabsUsageDiagnosticsStatus.SCOPED_BACKFILL_AVAILABLE
                ),
                filters_exclude_usage=filters_exclude_usage,
                date_range_excludes_usage=date_range_excludes_usage,
                missing_mappings=missing_mappings,
                repair_dry_run=repair_dry_run,
                message=_usage_diagnostics_message(
                    entity_type="project",
                    status=item_status,
                    missing_mappings=missing_mappings,
                    unmapped_spend_logs=breakdown.unmapped_spend_logs,
                    legacy_key_spend_logs=breakdown.legacy_key_spend_logs,
                    filters_exclude_usage=filters_exclude_usage,
                    date_range_excludes_usage=date_range_excludes_usage,
                ),
            )
        )
    return diagnostics
