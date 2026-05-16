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


def _set_payload_key_context(
    payload: Dict[str, Any],
    context: _KeyContext,
) -> Dict[str, Any]:
    metadata = _metadata_dict(payload.get("metadata"))
    metadata["cavadalabs_company_id"] = context.company_id
    metadata["cavadalabs_project_id"] = context.project_id
    cavadalabs_metadata = metadata.get("cavadalabs")
    if not isinstance(cavadalabs_metadata, dict):
        cavadalabs_metadata = {}
    cavadalabs_metadata["company_id"] = context.company_id
    cavadalabs_metadata["project_id"] = context.project_id
    if context.chatbot_id is not None:
        cavadalabs_metadata["chatbot_id"] = context.chatbot_id
    metadata["cavadalabs"] = cavadalabs_metadata
    spend_logs_metadata = metadata.get("spend_logs_metadata")
    if not isinstance(spend_logs_metadata, dict):
        spend_logs_metadata = {}
    spend_logs_metadata["cavadalabs_company_id"] = context.company_id
    spend_logs_metadata["cavadalabs_project_id"] = context.project_id
    if context.chatbot_id is not None:
        metadata["cavadalabs_chatbot_id"] = context.chatbot_id
        spend_logs_metadata["cavadalabs_chatbot_id"] = context.chatbot_id
    metadata["spend_logs_metadata"] = spend_logs_metadata
    return {**payload, "metadata": metadata}


def _extract_metadata_chatbot_id(metadata: Any) -> Optional[str]:
    parsed_metadata = _metadata_dict(metadata)
    for source_key in (None, "cavadalabs", "spend_logs_metadata"):
        source = parsed_metadata
        if source_key is not None:
            nested = parsed_metadata.get(source_key)
            source = nested if isinstance(nested, dict) else {}
        chatbot_id = _str_value(
            source.get("cavadalabs_chatbot_id") or source.get("chatbot_id")
        )
        if chatbot_id is not None:
            return chatbot_id
    return None


async def _fetch_verification_token_key_contexts(
    *,
    prisma_client: PrismaClient,
    where: Dict[str, Any],
    allowed_company_ids: List[str],
    allowed_project_ids: List[str],
    project_company_by_id: Dict[str, str],
    project_by_litellm_team_id: Dict[str, _KeyContext],
    company_id_by_litellm_org_id: Dict[str, str],
) -> Dict[str, _KeyContext]:
    allowed_companies = set(allowed_company_ids)
    allowed_projects = set(allowed_project_ids)
    key_context_by_token: Dict[str, _KeyContext] = {}

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
                token = _str_value(_row_value(row, "token"))
                if token is None or token in key_context_by_token:
                    continue
                company_id, project_id = _extract_metadata_context(
                    _row_value(row, "metadata")
                )
                chatbot_id = _extract_metadata_chatbot_id(_row_value(row, "metadata"))
                team_id = _str_value(_row_value(row, "team_id"))
                team_context = (
                    project_by_litellm_team_id.get(team_id)
                    if team_id is not None
                    else None
                )
                if project_id is None and team_context is not None:
                    project_id = team_context.project_id
                    company_id = company_id or team_context.company_id
                if project_id is None:
                    continue
                organization_id = _str_value(_row_value(row, "organization_id"))
                organization_company_id = (
                    company_id_by_litellm_org_id.get(organization_id)
                    if organization_id is not None
                    else None
                )
                company_id = company_id or organization_company_id
                company_id = company_id or project_company_by_id.get(project_id)
                if company_id is None:
                    continue
                if allowed_companies and company_id not in allowed_companies:
                    continue
                if allowed_projects and project_id not in allowed_projects:
                    continue
                expected_company_id = project_company_by_id.get(project_id)
                if (
                    expected_company_id is not None
                    and expected_company_id != company_id
                ):
                    continue
                if (
                    expected_company_id is not None
                    and organization_company_id is not None
                    and organization_company_id != expected_company_id
                ):
                    continue
                key_context_by_token[token] = _KeyContext(
                    company_id=company_id,
                    project_id=project_id,
                    chatbot_id=chatbot_id,
                )
            if len(rows) < _USAGE_KEY_CONTEXT_PAGE_SIZE:
                return
            skip += len(rows)

    await _load_rows_from_table("litellm_verificationtoken")
    await _load_rows_from_table("litellm_deletedverificationtoken")
    return key_context_by_token


async def _company_key_context_scope(
    *,
    prisma_client: PrismaClient,
    company_id: str,
    project_ids: List[str],
    team_ids: List[str],
    litellm_organization_id: Optional[str],
    project_company_by_id: Dict[str, str],
    project_by_litellm_team_id: Dict[str, _KeyContext],
) -> Dict[str, _KeyContext]:
    if not project_ids:
        return {}
    key_filters = _metadata_scope_pair_filters(
        company_id=company_id,
        project_ids=project_ids,
    )
    for project_id in project_ids:
        key_filters.extend(_metadata_scope_filters("project_id", project_id))
    if team_ids:
        key_filters.append({"team_id": {"in": team_ids}})
    if not key_filters:
        return {}
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
) -> Dict[str, _KeyContext]:
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
