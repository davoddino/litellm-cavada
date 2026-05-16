from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from litellm.proxy.cavadalabs.usage_key_context import (
    _KeyContext,
    _company_key_context_scope,
    _project_key_context_scope,
)
from litellm.proxy.cavadalabs.usage_query_filters import (
    metadata_scope_filters as _metadata_scope_filters,
)
from litellm.proxy.cavadalabs.usage_query_filters import (
    metadata_scope_pair_filters as _metadata_scope_pair_filters,
)
from litellm.proxy.cavadalabs.usage_query_filters import (
    spend_log_repair_where as _spend_log_repair_where,
)
from litellm.proxy.cavadalabs.usage_serialization import (
    _row_value,
    _str_value,
    _unique_sorted,
)
from litellm.proxy.utils import PrismaClient


@dataclass(frozen=True)
class _UsageRepairScope:
    filters: List[Dict[str, Any]]
    key_context_by_api_key: Dict[str, _KeyContext]
    metadata_filters: List[Dict[str, Any]]
    compatibility_filters: List[Dict[str, Any]]
    key_metadata_filters: List[Dict[str, Any]]


@dataclass(frozen=True)
class _SpendLogScopeFilterGroups:
    metadata_filters: List[Dict[str, Any]]
    compatibility_filters: List[Dict[str, Any]]

    @property
    def filters(self) -> List[Dict[str, Any]]:
        return [*self.metadata_filters, *self.compatibility_filters]


@dataclass(frozen=True)
class _UsageDiagnosticBreakdown:
    metadata_spend_logs: int = 0
    compatibility_spend_logs: int = 0
    key_metadata_spend_logs: int = 0
    unmapped_spend_logs: int = 0


def _api_key_scope_filter(api_key_hashes: List[str]) -> List[Dict[str, Any]]:
    if not api_key_hashes:
        return []
    return [{"api_key": {"in": api_key_hashes}}]


def _company_spend_log_scope_filter_groups(
    *,
    company_id: str,
    company: Any,
    project_ids: List[str],
    team_ids: List[str],
) -> _SpendLogScopeFilterGroups:
    metadata_filters = _metadata_scope_pair_filters(
        company_id=company_id,
        project_ids=project_ids,
    )
    compatibility_filters: List[Dict[str, Any]] = []
    litellm_organization_id = (
        _str_value(_row_value(company, "litellm_organization_id"))
        if company is not None
        else None
    )
    if litellm_organization_id is not None:
        for project_id in project_ids:
            for project_filter in _metadata_scope_filters("project_id", project_id):
                compatibility_filters.append(
                    {
                        "AND": [
                            {"organization_id": litellm_organization_id},
                            project_filter,
                        ]
                    }
                )

    if team_ids:
        compatibility_filters.append({"team_id": {"in": team_ids}})
    return _SpendLogScopeFilterGroups(
        metadata_filters=metadata_filters,
        compatibility_filters=compatibility_filters,
    )


def _project_spend_log_scope_filter_groups(
    *,
    project_id: str,
    project: Any,
) -> _SpendLogScopeFilterGroups:
    metadata_filters = _metadata_scope_filters("project_id", project_id)
    compatibility_filters: List[Dict[str, Any]] = []
    litellm_team_id = (
        _str_value(_row_value(project, "litellm_team_id"))
        if project is not None
        else None
    )
    if litellm_team_id is not None:
        compatibility_filters.append({"team_id": litellm_team_id})
    return _SpendLogScopeFilterGroups(
        metadata_filters=metadata_filters,
        compatibility_filters=compatibility_filters,
    )


async def _count_attributable_spend_logs(
    *,
    prisma_client: PrismaClient,
    date_range: Optional[Dict[str, datetime]],
    filters: List[Dict[str, Any]],
    model: Optional[str] = None,
    provider: Optional[str] = None,
    api_key: Optional[Union[str, List[str]]] = None,
) -> int:
    if not filters:
        return 0
    if not model and not provider and not api_key:
        where: Dict[str, Any] = {"OR": filters}
        if date_range is not None:
            where["startTime"] = date_range
    else:
        where = _spend_log_repair_where(
            date_range=date_range,
            filters=filters,
            model=model,
            provider=provider,
            api_key=api_key,
        )
    return int(await prisma_client.db.litellm_spendlogs.count(where=where))


async def _count_scope_breakdown(
    *,
    prisma_client: PrismaClient,
    date_range: Optional[Dict[str, datetime]],
    scope: _UsageRepairScope,
    model: Optional[str],
    provider: Optional[str],
    api_key: Optional[Union[str, List[str]]],
    unmapped_candidate_filters: Optional[List[Dict[str, Any]]] = None,
    attributable_spend_logs: int,
) -> _UsageDiagnosticBreakdown:
    metadata_spend_logs = await _count_attributable_spend_logs(
        prisma_client=prisma_client,
        date_range=date_range,
        filters=scope.metadata_filters,
        model=model,
        provider=provider,
        api_key=api_key,
    )
    compatibility_spend_logs = await _count_attributable_spend_logs(
        prisma_client=prisma_client,
        date_range=date_range,
        filters=scope.compatibility_filters,
        model=model,
        provider=provider,
        api_key=api_key,
    )
    key_metadata_spend_logs = await _count_attributable_spend_logs(
        prisma_client=prisma_client,
        date_range=date_range,
        filters=scope.key_metadata_filters,
        model=model,
        provider=provider,
        api_key=api_key,
    )
    unmapped_candidate_spend_logs = 0
    if unmapped_candidate_filters:
        unmapped_candidate_spend_logs = await _count_attributable_spend_logs(
            prisma_client=prisma_client,
            date_range=date_range,
            filters=unmapped_candidate_filters,
            model=model,
            provider=provider,
            api_key=api_key,
        )
    return _UsageDiagnosticBreakdown(
        metadata_spend_logs=metadata_spend_logs,
        compatibility_spend_logs=compatibility_spend_logs,
        key_metadata_spend_logs=key_metadata_spend_logs,
        unmapped_spend_logs=max(
            unmapped_candidate_spend_logs - attributable_spend_logs,
            0,
        ),
    )


async def _company_repair_filters(
    *,
    prisma_client: PrismaClient,
    entity_ids: List[str],
) -> List[Dict[str, Any]]:
    return (
        await _company_repair_scope(
            prisma_client=prisma_client,
            entity_ids=entity_ids,
        )
    ).filters


async def _company_repair_scope(
    *,
    prisma_client: PrismaClient,
    entity_ids: List[str],
) -> _UsageRepairScope:
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
        company_id = _str_value(_row_value(row, "company_id"))
        project_id = _str_value(_row_value(row, "project_id"))
        team_id = _str_value(_row_value(row, "litellm_team_id"))
        if company_id is None:
            continue
        if project_id is not None:
            project_ids_by_company.setdefault(company_id, []).append(project_id)
        if team_id is not None:
            team_ids_by_company.setdefault(company_id, []).append(team_id)

    filters: List[Dict[str, Any]] = []
    metadata_filters: List[Dict[str, Any]] = []
    compatibility_filters: List[Dict[str, Any]] = []
    key_context_by_api_key: Dict[str, _KeyContext] = {}
    project_company_by_id = {
        project_id: company_id
        for company_id, project_ids in project_ids_by_company.items()
        for project_id in project_ids
    }
    project_by_litellm_team_id: Dict[str, _KeyContext] = {}
    for row in project_rows:
        team_id = _str_value(_row_value(row, "litellm_team_id"))
        project_id = _str_value(_row_value(row, "project_id"))
        company_id = _str_value(_row_value(row, "company_id"))
        if team_id is not None and project_id is not None and company_id is not None:
            project_by_litellm_team_id[team_id] = _KeyContext(
                company_id=company_id,
                project_id=project_id,
            )
    for company_id in entity_ids:
        company_project_ids = _unique_sorted(project_ids_by_company.get(company_id, []))
        company = companies_by_id.get(company_id)
        filter_groups = _company_spend_log_scope_filter_groups(
            company_id=company_id,
            company=company,
            project_ids=company_project_ids,
            team_ids=_unique_sorted(team_ids_by_company.get(company_id, [])),
        )
        filters.extend(filter_groups.filters)
        metadata_filters.extend(filter_groups.metadata_filters)
        compatibility_filters.extend(filter_groups.compatibility_filters)
        company_key_context = await _company_key_context_scope(
            prisma_client=prisma_client,
            company_id=company_id,
            project_ids=company_project_ids,
            team_ids=_unique_sorted(team_ids_by_company.get(company_id, [])),
            litellm_organization_id=(
                _str_value(_row_value(company, "litellm_organization_id"))
                if company is not None
                else None
            ),
            project_company_by_id=project_company_by_id,
            project_by_litellm_team_id=project_by_litellm_team_id,
        )
        key_context_by_api_key.update(company_key_context)
    key_metadata_filters = _api_key_scope_filter(sorted(key_context_by_api_key))
    filters.extend(key_metadata_filters)
    return _UsageRepairScope(
        filters=filters,
        key_context_by_api_key=key_context_by_api_key,
        metadata_filters=metadata_filters,
        compatibility_filters=compatibility_filters,
        key_metadata_filters=key_metadata_filters,
    )


async def _project_repair_filters(
    *,
    prisma_client: PrismaClient,
    entity_ids: List[str],
) -> List[Dict[str, Any]]:
    return (
        await _project_repair_scope(
            prisma_client=prisma_client,
            entity_ids=entity_ids,
        )
    ).filters


async def _project_repair_scope(
    *,
    prisma_client: PrismaClient,
    entity_ids: List[str],
) -> _UsageRepairScope:
    project_rows = await prisma_client.db.cavadalabs_projecttable.find_many(
        where={"project_id": {"in": entity_ids}}
    )
    projects_by_id = {row.project_id: row for row in project_rows}
    project_company_by_id = {
        project_id: company_id
        for project_id, project in projects_by_id.items()
        if (company_id := _str_value(_row_value(project, "company_id"))) is not None
    }
    project_by_litellm_team_id: Dict[str, _KeyContext] = {}
    for project_id, project in projects_by_id.items():
        team_id = _str_value(_row_value(project, "litellm_team_id"))
        company_id = _str_value(_row_value(project, "company_id"))
        if team_id is not None and company_id is not None:
            project_by_litellm_team_id[team_id] = _KeyContext(
                company_id=company_id,
                project_id=project_id,
            )
    company_id_by_litellm_org_id: Dict[str, str] = {}
    company_ids = _unique_sorted(list(project_company_by_id.values()))
    if company_ids:
        company_rows = await prisma_client.db.cavadalabs_companytable.find_many(
            where={"company_id": {"in": company_ids}}
        )
        for row in company_rows:
            organization_id = _str_value(_row_value(row, "litellm_organization_id"))
            company_id = _str_value(_row_value(row, "company_id"))
            if organization_id is not None and company_id is not None:
                company_id_by_litellm_org_id[organization_id] = company_id
    filters: List[Dict[str, Any]] = []
    metadata_filters: List[Dict[str, Any]] = []
    compatibility_filters: List[Dict[str, Any]] = []
    key_context_by_api_key: Dict[str, _KeyContext] = {}
    for project_id in entity_ids:
        project = projects_by_id.get(project_id)
        if project is None:
            continue
        filter_groups = _project_spend_log_scope_filter_groups(
            project_id=project_id,
            project=project,
        )
        filters.extend(filter_groups.filters)
        metadata_filters.extend(filter_groups.metadata_filters)
        compatibility_filters.extend(filter_groups.compatibility_filters)
        project_key_context = await _project_key_context_scope(
            prisma_client=prisma_client,
            project_id=project_id,
            litellm_team_id=_str_value(_row_value(project, "litellm_team_id")),
            project_company_by_id=project_company_by_id,
            project_by_litellm_team_id=project_by_litellm_team_id,
            company_id_by_litellm_org_id=company_id_by_litellm_org_id,
        )
        key_context_by_api_key.update(project_key_context)
    key_metadata_filters = _api_key_scope_filter(sorted(key_context_by_api_key))
    filters.extend(key_metadata_filters)
    return _UsageRepairScope(
        filters=filters,
        key_context_by_api_key=key_context_by_api_key,
        metadata_filters=metadata_filters,
        compatibility_filters=compatibility_filters,
        key_metadata_filters=key_metadata_filters,
    )
