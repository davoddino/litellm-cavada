from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from litellm._logging import verbose_proxy_logger
from litellm.proxy.cavadalabs.usage_query_filters import (
    metadata_scope_filters as _metadata_scope_filters,
)
from litellm.proxy.cavadalabs.usage_query_filters import (
    metadata_scope_pair_filters as _metadata_scope_pair_filters,
)
from litellm.proxy.cavadalabs.usage_serialization import (
    _extract_metadata_context,
    _metadata_dict,
    _metadata_sources,
    _row_value,
    _str_value,
)
from litellm.proxy.utils import PrismaClient

_USAGE_KEY_CONTEXT_PAGE_SIZE = 1000


@dataclass(frozen=True)
class _KeyContext:
    company_id: str
    project_id: str
    chatbot_id: Optional[str] = None


@dataclass(frozen=True)
class _KeyContextLookupResult:
    context_by_token: Dict[str, _KeyContext]
    legacy_tokens_missing_metadata: List[str]


@dataclass(frozen=True)
class _KeyContextRowResolution:
    token: str
    context: Optional[_KeyContext]
    legacy_token_missing_metadata: bool = False


def _set_payload_key_context(
    payload: Dict[str, Any],
    context: _KeyContext,
) -> Dict[str, Any]:
    metadata = _metadata_dict(payload.get("metadata"))
    metadata["cavadalabs_company_id"] = context.company_id
    metadata["cavadalabs_project_id"] = context.project_id
    metadata["cavadalabs_metadata_authenticated"] = True
    metadata["cavadalabs_metadata_source"] = "key_metadata"
    cavadalabs_metadata = _metadata_dict(metadata.get("cavadalabs"))
    cavadalabs_metadata["company_id"] = context.company_id
    cavadalabs_metadata["project_id"] = context.project_id
    if context.chatbot_id is not None:
        cavadalabs_metadata["chatbot_id"] = context.chatbot_id
    metadata["cavadalabs"] = cavadalabs_metadata
    spend_logs_metadata = _metadata_dict(metadata.get("spend_logs_metadata"))
    spend_logs_metadata["cavadalabs_company_id"] = context.company_id
    spend_logs_metadata["cavadalabs_project_id"] = context.project_id
    if context.chatbot_id is not None:
        metadata["cavadalabs_chatbot_id"] = context.chatbot_id
        spend_logs_metadata["cavadalabs_chatbot_id"] = context.chatbot_id
    metadata["spend_logs_metadata"] = spend_logs_metadata
    return {**payload, "metadata": metadata}


def _extract_metadata_chatbot_id(metadata: Any) -> Optional[str]:
    parsed_metadata = _metadata_dict(metadata)
    for source in _metadata_sources(parsed_metadata):
        chatbot_id = _str_value(
            source.get("cavadalabs_chatbot_id") or source.get("chatbot_id")
        )
        if chatbot_id is not None:
            return chatbot_id
    return None


def _resolve_verification_token_key_context(
    *,
    row: Any,
    allowed_companies: set[str],
    allowed_projects: set[str],
    project_company_by_id: Dict[str, str],
    project_by_litellm_team_id: Dict[str, _KeyContext],
    company_id_by_litellm_org_id: Dict[str, str],
) -> Optional[_KeyContextRowResolution]:
    token = _str_value(_row_value(row, "token"))
    if token is None:
        return None

    metadata_company_id, metadata_project_id = _extract_metadata_context(
        _row_value(row, "metadata")
    )
    company_id = metadata_company_id
    project_id = metadata_project_id
    team_id = _str_value(_row_value(row, "team_id"))
    team_context = (
        project_by_litellm_team_id.get(team_id) if team_id is not None else None
    )
    if project_id is None and team_context is not None:
        project_id = team_context.project_id
        company_id = company_id or team_context.company_id

    organization_id = _str_value(_row_value(row, "organization_id"))
    organization_company_id = (
        company_id_by_litellm_org_id.get(organization_id)
        if organization_id is not None
        else None
    )
    if project_id is None:
        return _KeyContextRowResolution(
            token=token,
            context=None,
            legacy_token_missing_metadata=(
                organization_company_id is not None
                and (
                    not allowed_companies
                    or organization_company_id in allowed_companies
                )
            ),
        )

    company_id = company_id or organization_company_id
    company_id = company_id or project_company_by_id.get(project_id)
    if company_id is None:
        return None
    if allowed_companies and company_id not in allowed_companies:
        return None
    if allowed_projects and project_id not in allowed_projects:
        return None
    expected_company_id = project_company_by_id.get(project_id)
    if expected_company_id is not None and expected_company_id != company_id:
        return None
    if (
        expected_company_id is not None
        and organization_company_id is not None
        and organization_company_id != expected_company_id
    ):
        return None

    return _KeyContextRowResolution(
        token=token,
        context=_KeyContext(
            company_id=company_id,
            project_id=project_id,
            chatbot_id=_extract_metadata_chatbot_id(_row_value(row, "metadata")),
        ),
        legacy_token_missing_metadata=(
            metadata_company_id is None or metadata_project_id is None
        ),
    )


async def _fetch_verification_token_key_contexts(
    *,
    prisma_client: PrismaClient,
    where: Dict[str, Any],
    allowed_company_ids: List[str],
    allowed_project_ids: List[str],
    project_company_by_id: Dict[str, str],
    project_by_litellm_team_id: Dict[str, _KeyContext],
    company_id_by_litellm_org_id: Dict[str, str],
) -> _KeyContextLookupResult:
    allowed_companies = set(allowed_company_ids)
    allowed_projects = set(allowed_project_ids)
    key_context_by_token: Dict[str, _KeyContext] = {}
    legacy_tokens_missing_metadata: set[str] = set()

    async def _load_rows_from_table(table_name: str) -> None:
        try:
            table = getattr(prisma_client.db, table_name)
        except AttributeError:
            verbose_proxy_logger.warning(
                "CavadaLabs usage repair skipped missing Prisma delegate %s",
                table_name,
            )
            return
        skip = 0
        while True:
            try:
                rows = await table.find_many(
                    where=where,
                    skip=skip,
                    take=_USAGE_KEY_CONTEXT_PAGE_SIZE,
                )
            except Exception as exc:
                verbose_proxy_logger.warning(
                    "CavadaLabs usage repair skipped key-context lookup on %s: %s",
                    table_name,
                    exc,
                )
                return
            if not rows:
                return
            for row in rows:
                resolution = _resolve_verification_token_key_context(
                    row=row,
                    allowed_companies=allowed_companies,
                    allowed_projects=allowed_projects,
                    project_company_by_id=project_company_by_id,
                    project_by_litellm_team_id=project_by_litellm_team_id,
                    company_id_by_litellm_org_id=company_id_by_litellm_org_id,
                )
                if resolution is None or resolution.token in key_context_by_token:
                    continue
                if resolution.context is not None:
                    key_context_by_token[resolution.token] = resolution.context
                if resolution.legacy_token_missing_metadata:
                    legacy_tokens_missing_metadata.add(resolution.token)
            if len(rows) < _USAGE_KEY_CONTEXT_PAGE_SIZE:
                return
            skip += len(rows)

    await _load_rows_from_table("litellm_verificationtoken")
    await _load_rows_from_table("litellm_deletedverificationtoken")
    return _KeyContextLookupResult(
        context_by_token=key_context_by_token,
        legacy_tokens_missing_metadata=sorted(legacy_tokens_missing_metadata),
    )


async def _company_key_context_scope(
    *,
    prisma_client: PrismaClient,
    company_id: str,
    project_ids: List[str],
    team_ids: List[str],
    litellm_organization_id: Optional[str],
    project_company_by_id: Dict[str, str],
    project_by_litellm_team_id: Dict[str, _KeyContext],
) -> _KeyContextLookupResult:
    if not project_ids:
        return _KeyContextLookupResult(
            context_by_token={}, legacy_tokens_missing_metadata=[]
        )
    key_filters = _metadata_scope_pair_filters(
        company_id=company_id,
        project_ids=project_ids,
    )
    for project_id in project_ids:
        key_filters.extend(_metadata_scope_filters("project_id", project_id))
    if team_ids:
        key_filters.append({"team_id": {"in": team_ids}})
    if litellm_organization_id is not None:
        key_filters.append({"organization_id": litellm_organization_id})
    if not key_filters:
        return _KeyContextLookupResult(
            context_by_token={}, legacy_tokens_missing_metadata=[]
        )
    company_id_by_litellm_org_id = (
        {litellm_organization_id: company_id}
        if litellm_organization_id is not None
        else {}
    )
    return await _fetch_verification_token_key_contexts(
        prisma_client=prisma_client,
        where={"OR": key_filters},
        allowed_company_ids=[company_id],
        allowed_project_ids=project_ids,
        project_company_by_id=project_company_by_id,
        project_by_litellm_team_id=project_by_litellm_team_id,
        company_id_by_litellm_org_id=company_id_by_litellm_org_id,
    )


async def _project_key_context_scope(
    *,
    prisma_client: PrismaClient,
    project_id: str,
    litellm_team_id: Optional[str],
    project_company_by_id: Dict[str, str],
    project_by_litellm_team_id: Dict[str, _KeyContext],
    company_id_by_litellm_org_id: Dict[str, str],
) -> _KeyContextLookupResult:
    key_filters = _metadata_scope_filters("project_id", project_id)
    if litellm_team_id is not None:
        key_filters.append({"team_id": litellm_team_id})
    return await _fetch_verification_token_key_contexts(
        prisma_client=prisma_client,
        where={"OR": key_filters},
        allowed_company_ids=[],
        allowed_project_ids=[project_id],
        project_company_by_id=project_company_by_id,
        project_by_litellm_team_id=project_by_litellm_team_id,
        company_id_by_litellm_org_id=company_id_by_litellm_org_id,
    )
