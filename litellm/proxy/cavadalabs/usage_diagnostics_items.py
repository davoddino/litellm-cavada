from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Union

from litellm.proxy.cavadalabs.usage_backfill_scope import (
    _UsageRepairScope,
    _company_repair_scope,
    _count_attributable_spend_logs,
    _count_scope_breakdown,
    _project_repair_scope,
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
)


async def _company_usage_diagnostics(
    *,
    prisma_client: PrismaClient,
    entity_ids: List[str],
    date_range: Dict[str, datetime],
    model: Optional[str] = None,
    provider: Optional[str] = None,
    api_key: Optional[Union[str, List[str]]] = None,
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
        ledger_rows = int(
            await prisma_client.db.cavadalabs_requestledgertable.count(
                where=_build_cavadalabs_ledger_where(
                    entity_id_field="company_id",
                    entity_id=company_id,
                    date_range=date_range,
                    model=model,
                    provider=provider,
                    status_filter=None,
                    api_key=api_key,
                    min_spend=None,
                    max_spend=None,
                )
            )
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

        attributable_spend_logs = await _count_attributable_spend_logs(
            prisma_client=prisma_client,
            date_range=date_range,
            filters=filters,
            model=model,
            provider=provider,
            api_key=api_key,
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
            unmapped_candidate_filters=(
                [{"organization_id": litellm_organization_id}]
                if litellm_organization_id is not None
                else None
            ),
            attributable_spend_logs=attributable_spend_logs,
        )
        unfiltered_attributable_spend_logs = 0
        all_time_attributable_spend_logs = 0
        filters_exclude_usage = False
        date_range_excludes_usage = False
        if attributable_spend_logs == 0 and (model or provider or api_key):
            unfiltered_attributable_spend_logs = await _count_attributable_spend_logs(
                prisma_client=prisma_client,
                date_range=date_range,
                filters=filters,
            )
            filters_exclude_usage = unfiltered_attributable_spend_logs > 0
        if attributable_spend_logs == 0 and not filters_exclude_usage:
            all_time_attributable_spend_logs = await _count_attributable_spend_logs(
                prisma_client=prisma_client,
                date_range=None,
                filters=filters,
            )
            date_range_excludes_usage = all_time_attributable_spend_logs > 0
        item_status = _usage_diagnostics_status(
            ledger_rows=ledger_rows,
            attributable_spend_logs=attributable_spend_logs,
            missing_mappings=missing_mappings,
            unmapped_spend_logs=breakdown.unmapped_spend_logs,
            filters_exclude_usage=filters_exclude_usage,
            date_range_excludes_usage=date_range_excludes_usage,
        )
        if (
            item_status
            == CavadaLabsUsageDiagnosticsStatus.MISSING_COMPATIBILITY_MAPPING
            and breakdown.unmapped_spend_logs > 0
            and not missing_mappings
        ):
            missing_mappings = [
                "CavadaLabs key metadata or Project compatibility mapping"
            ]
        ledger_gap = max(attributable_spend_logs - ledger_rows, 0)
        diagnostics.append(
            CavadaLabsUsageDiagnosticsItem(
                entity_type="company",
                entity_id=company_id,
                status=item_status,
                ledger_rows=ledger_rows,
                attributable_spend_logs=attributable_spend_logs,
                metadata_spend_logs=breakdown.metadata_spend_logs,
                compatibility_spend_logs=breakdown.compatibility_spend_logs,
                key_metadata_spend_logs=breakdown.key_metadata_spend_logs,
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
                message=_usage_diagnostics_message(
                    entity_type="company",
                    status=item_status,
                    missing_mappings=missing_mappings,
                    unmapped_spend_logs=breakdown.unmapped_spend_logs,
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
) -> List[CavadaLabsUsageDiagnosticsItem]:
    project_rows = await prisma_client.db.cavadalabs_projecttable.find_many(
        where={"project_id": {"in": entity_ids}}
    )
    projects_by_id = {row.project_id: row for row in project_rows}

    diagnostics: List[CavadaLabsUsageDiagnosticsItem] = []
    for project_id in entity_ids:
        ledger_rows = int(
            await prisma_client.db.cavadalabs_requestledgertable.count(
                where=_build_cavadalabs_ledger_where(
                    entity_id_field="project_id",
                    entity_id=project_id,
                    date_range=date_range,
                    model=model,
                    provider=provider,
                    status_filter=None,
                    api_key=api_key,
                    min_spend=None,
                    max_spend=None,
                )
            )
        )
        missing_mappings = []
        project = projects_by_id.get(project_id)
        if project is None:
            missing_mappings.append("CavadaLabs project row")
            filters = []
        else:
            scope = await _project_repair_scope(
                prisma_client=prisma_client,
                entity_ids=[project_id],
            )
            filters = scope.filters
            litellm_team_id = getattr(project, "litellm_team_id", None)
            if (
                not isinstance(litellm_team_id, str) or not litellm_team_id.strip()
            ) and not scope.key_context_by_api_key:
                missing_mappings.append(
                    "project litellm_team_id or CavadaLabs key metadata"
                )

        attributable_spend_logs = await _count_attributable_spend_logs(
            prisma_client=prisma_client,
            date_range=date_range,
            filters=filters,
            model=model,
            provider=provider,
            api_key=api_key,
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
                    metadata_filters=[],
                    compatibility_filters=[],
                    key_metadata_filters=[],
                )
            ),
            model=model,
            provider=provider,
            api_key=api_key,
            unmapped_candidate_filters=(
                [{"team_id": litellm_team_id}] if litellm_team_id is not None else None
            ),
            attributable_spend_logs=attributable_spend_logs,
        )
        unfiltered_attributable_spend_logs = 0
        all_time_attributable_spend_logs = 0
        filters_exclude_usage = False
        date_range_excludes_usage = False
        if attributable_spend_logs == 0 and (model or provider or api_key):
            unfiltered_attributable_spend_logs = await _count_attributable_spend_logs(
                prisma_client=prisma_client,
                date_range=date_range,
                filters=filters,
            )
            filters_exclude_usage = unfiltered_attributable_spend_logs > 0
        if attributable_spend_logs == 0 and not filters_exclude_usage:
            all_time_attributable_spend_logs = await _count_attributable_spend_logs(
                prisma_client=prisma_client,
                date_range=None,
                filters=filters,
            )
            date_range_excludes_usage = all_time_attributable_spend_logs > 0
        item_status = _usage_diagnostics_status(
            ledger_rows=ledger_rows,
            attributable_spend_logs=attributable_spend_logs,
            missing_mappings=missing_mappings,
            unmapped_spend_logs=breakdown.unmapped_spend_logs,
            filters_exclude_usage=filters_exclude_usage,
            date_range_excludes_usage=date_range_excludes_usage,
        )
        if (
            item_status
            == CavadaLabsUsageDiagnosticsStatus.MISSING_COMPATIBILITY_MAPPING
            and breakdown.unmapped_spend_logs > 0
            and not missing_mappings
        ):
            missing_mappings = [
                "CavadaLabs key metadata or Project compatibility mapping"
            ]
        ledger_gap = max(attributable_spend_logs - ledger_rows, 0)
        diagnostics.append(
            CavadaLabsUsageDiagnosticsItem(
                entity_type="project",
                entity_id=project_id,
                status=item_status,
                ledger_rows=ledger_rows,
                attributable_spend_logs=attributable_spend_logs,
                metadata_spend_logs=breakdown.metadata_spend_logs,
                compatibility_spend_logs=breakdown.compatibility_spend_logs,
                key_metadata_spend_logs=breakdown.key_metadata_spend_logs,
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
                message=_usage_diagnostics_message(
                    entity_type="project",
                    status=item_status,
                    missing_mappings=missing_mappings,
                    unmapped_spend_logs=breakdown.unmapped_spend_logs,
                    filters_exclude_usage=filters_exclude_usage,
                    date_range_excludes_usage=date_range_excludes_usage,
                ),
            )
        )
    return diagnostics
