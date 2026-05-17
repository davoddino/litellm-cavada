from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from litellm._logging import verbose_proxy_logger
from litellm.litellm_core_utils.safe_json_loads import safe_json_loads
from litellm.proxy.cavadalabs.prisma_json import serialize_prisma_json_fields
from litellm.proxy.cavadalabs.usage_schema_readiness import (
    looks_like_missing_schema_exception,
)
from litellm.proxy.utils import PrismaClient


_FIELD_ALIASES: Dict[str, Iterable[str]] = {
    "company_id": ("cavadalabs_company_id", "company_id"),
    "project_id": ("cavadalabs_project_id", "project_id"),
    "chatbot_id": ("cavadalabs_chatbot_id", "chatbot_id"),
    "web_token_id": ("cavadalabs_web_token_id", "web_token_id"),
    "session_id": ("cavadalabs_session_id", "session_id"),
    "node_id": ("cavadalabs_node_id", "node_id"),
    "gpu_id": ("cavadalabs_gpu_id", "gpu_id"),
    "loaded_model_id": ("cavadalabs_loaded_model_id", "loaded_model_id"),
    "model_load_request_id": (
        "cavadalabs_model_load_request_id",
        "model_load_request_id",
    ),
    "provider": ("cavadalabs_provider", "provider"),
    "model_alias": ("cavadalabs_model_alias", "model_alias"),
}

_API_KEY_HASH_METADATA_KEYS = ("user_api_key_hash", "user_api_key", "api_key_hash")
_AUTHENTICATED_METADATA_MARKER = "cavadalabs_metadata_authenticated"
_AUTHENTICATED_METADATA_SOURCE = "cavadalabs_metadata_source"


@dataclass(frozen=True)
class _ProjectMapping:
    project_id: str
    company_id: str


@dataclass(frozen=True)
class _KeyContextMapping:
    project_id: str
    company_id: str
    chatbot_id: Optional[str]


@dataclass(frozen=True)
class _KeyContextCandidate:
    token: str
    company_id: Optional[str]
    project_id: Optional[str]
    chatbot_id: Optional[str]
    team_id: Optional[str]
    organization_id: Optional[str]


@dataclass(frozen=True)
class CavadaLabsResolvedContext:
    company_id: str
    project_id: str
    source: str


@dataclass(frozen=True)
class CavadaLabsLedgerAttributionInputCheck:
    request_id: Optional[str]
    company_id: Optional[str]
    project_id: Optional[str]
    api_key_hash: Optional[str]
    team_id: Optional[str]
    organization_id: Optional[str]
    can_attempt_attribution: bool
    missing_inputs: tuple[str, ...]
    required_lookups: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class _CompatContextResolver:
    company_id_by_litellm_org_id: Dict[str, str]
    project_by_litellm_team_id: Dict[str, _ProjectMapping]
    project_by_project_id: Dict[str, _ProjectMapping]
    key_context_by_api_key_hash: Dict[str, _KeyContextMapping]
    project_lookup_available: bool = True
    project_lookup_schema_missing: bool = False


def _metadata_dict(raw_metadata: Any) -> Dict[str, Any]:
    data = getattr(raw_metadata, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(raw_metadata, dict):
        return raw_metadata
    if isinstance(raw_metadata, str):
        parsed = safe_json_loads(raw_metadata, default={})
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _metadata_sources(metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    # Top-level spend-log metadata is server-authenticated key context. Keep it
    # ahead of request-supplied spend_logs_metadata so clients cannot spoof
    # CavadaLabs billing attribution for a virtual key.
    sources: List[Dict[str, Any]] = [metadata]
    for key in ("cavadalabs", "spend_logs_metadata"):
        nested_metadata = _metadata_dict(metadata.get(key))
        if nested_metadata:
            sources.append(nested_metadata)
    return sources


def _extract_metadata_value(
    metadata_sources: List[Dict[str, Any]], logical_field: str
) -> Optional[str]:
    aliases = _FIELD_ALIASES[logical_field]
    for source in metadata_sources:
        for alias in aliases:
            value = source.get(alias)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _normalize_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        result = datetime.now(timezone.utc)
    if result.tzinfo is None:
        return result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _int_value(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def _float_value(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _str_value(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _row_value(row: Any, field_name: str) -> Any:
    if isinstance(row, dict):
        return row.get(field_name)
    return getattr(row, field_name, None)


def _has_top_level_cavadalabs_context(metadata: Dict[str, Any]) -> bool:
    company_id = _str_value(
        metadata.get("cavadalabs_company_id") or metadata.get("company_id")
    )
    project_id = _str_value(
        metadata.get("cavadalabs_project_id") or metadata.get("project_id")
    )
    return company_id is not None and project_id is not None


def _has_authenticated_direct_cavadalabs_context(metadata: Dict[str, Any]) -> bool:
    marker = metadata.get(_AUTHENTICATED_METADATA_MARKER)
    return marker is True and _has_top_level_cavadalabs_context(metadata)


def _authenticated_direct_context_source(metadata: Dict[str, Any]) -> Optional[str]:
    if not _has_authenticated_direct_cavadalabs_context(metadata):
        return None
    return _str_value(metadata.get(_AUTHENTICATED_METADATA_SOURCE))


def _can_use_direct_context_without_project_lookup(
    *,
    compat_context: _CompatContextResolver,
    direct_metadata: Dict[str, Any],
) -> bool:
    return (
        not compat_context.project_lookup_available
        and not compat_context.project_lookup_schema_missing
        and _has_authenticated_direct_cavadalabs_context(direct_metadata)
    )


def _log_unresolved_project_context(
    *,
    payload: Dict[str, Any],
    company_id: Optional[str],
    project_id: str,
    project_lookup_available: bool,
) -> None:
    if project_lookup_available:
        verbose_proxy_logger.warning(
            "CavadaLabs ledger skipped spend log with unresolved Project context: request_id=%s company_id=%s project_id=%s",
            payload.get("request_id"),
            company_id,
            project_id,
        )
    else:
        verbose_proxy_logger.warning(
            "CavadaLabs ledger skipped spend log because Project context could not be validated: request_id=%s company_id=%s project_id=%s",
            payload.get("request_id"),
            company_id,
            project_id,
        )


def _api_key_hash_value(value: Any) -> Optional[str]:
    api_key_hash = _str_value(value)
    if api_key_hash is None:
        return None
    # Never persist or look up a raw key from client-supplied metadata. The
    # spend-log payload top-level api_key is already normalized by LiteLLM.
    if api_key_hash.startswith("sk-"):
        return None
    return api_key_hash


def _api_key_hash_from_payload(
    payload: Dict[str, Any],
    sources: List[Dict[str, Any]],
) -> Optional[str]:
    for field_name in ("api_key", "user_api_key_hash", "api_key_hash"):
        api_key_hash = _api_key_hash_value(payload.get(field_name))
        if api_key_hash is not None:
            return api_key_hash
    for source in sources:
        for field_name in _API_KEY_HASH_METADATA_KEYS:
            api_key_hash = _api_key_hash_value(source.get(field_name))
            if api_key_hash is not None:
                return api_key_hash
    return None


def inspect_cavadalabs_ledger_attribution_inputs(
    payload: Dict[str, Any],
) -> CavadaLabsLedgerAttributionInputCheck:
    """
    Explain whether a LiteLLM SpendLogs payload has enough CavadaLabs context.

    This is intentionally no-DB: it tells operators if the runtime payload is
    missing the Company/Project attribution inputs before any Prisma lookup.
    Database-backed validation still happens in process_spend_logs_cavadalabs_ledger.
    """

    request_id = _str_value(payload.get("request_id"))
    metadata = _metadata_dict(payload.get("metadata"))
    sources = _metadata_sources(metadata)
    company_id = _extract_metadata_value(sources, "company_id")
    project_id = _extract_metadata_value(sources, "project_id")
    api_key_hash = _api_key_hash_from_payload(payload=payload, sources=sources)
    team_id = _str_value(payload.get("team_id"))
    organization_id = _str_value(payload.get("organization_id"))

    missing_inputs: List[str] = []
    if request_id is None:
        missing_inputs.append("request_id")

    has_company_path = any(
        value is not None
        for value in (company_id, project_id, api_key_hash, team_id, organization_id)
    )
    has_project_path = any(
        value is not None for value in (project_id, api_key_hash, team_id)
    )
    if not has_company_path:
        missing_inputs.append(
            "Company context: cavadalabs_company_id, virtual-key metadata, "
            "Project mapping, or LiteLLM organization mapping"
        )
    if not has_project_path:
        missing_inputs.append(
            "Project context: cavadalabs_project_id, virtual-key metadata, "
            "or LiteLLM team mapping"
        )

    required_lookups: List[str] = []
    if api_key_hash is not None and (company_id is None or project_id is None):
        required_lookups.append("virtual-key CavadaLabs metadata lookup")
    if project_id is not None:
        required_lookups.append("CavadaLabs Project validation")
    if team_id is not None and project_id is None:
        required_lookups.append("Project litellm_team_id compatibility mapping")
    if organization_id is not None and company_id is None:
        required_lookups.append("Company litellm_organization_id compatibility mapping")

    can_attempt_attribution = not missing_inputs
    if missing_inputs:
        message = (
            "CavadaLabs usage cannot be attributed to the request ledger without "
            + "; ".join(missing_inputs)
            + "."
        )
    elif required_lookups:
        message = (
            "CavadaLabs usage has enough runtime context; DB lookup must resolve "
            + "; ".join(required_lookups)
            + "."
        )
    else:
        message = "CavadaLabs usage has direct Company/Project runtime context."

    return CavadaLabsLedgerAttributionInputCheck(
        request_id=request_id,
        company_id=company_id,
        project_id=project_id,
        api_key_hash=api_key_hash,
        team_id=team_id,
        organization_id=organization_id,
        can_attempt_attribution=can_attempt_attribution,
        missing_inputs=tuple(missing_inputs),
        required_lookups=tuple(dict.fromkeys(required_lookups)),
        message=message,
    )


def _resolve_cavadalabs_context(
    payload: Dict[str, Any],
    sources: List[Dict[str, Any]],
    compat_context: Optional[_CompatContextResolver],
) -> Optional[CavadaLabsResolvedContext]:
    company_id = _extract_metadata_value(sources, "company_id")
    project_id = _extract_metadata_value(sources, "project_id")
    direct_metadata = sources[0] if sources else {}
    project_company_id: Optional[str] = None
    org_company_id: Optional[str] = None
    source = _authenticated_direct_context_source(direct_metadata) or (
        "metadata" if company_id is not None or project_id is not None else None
    )

    if compat_context is not None:
        api_key_hash = _api_key_hash_from_payload(payload=payload, sources=sources)
        key_mapping = (
            compat_context.key_context_by_api_key_hash.get(api_key_hash)
            if api_key_hash is not None
            else None
        )
        if key_mapping is not None:
            if company_id is not None and company_id != key_mapping.company_id:
                verbose_proxy_logger.warning(
                    "CavadaLabs ledger using virtual-key Company context over conflicting spend-log metadata: request_id=%s metadata_company_id=%s key_company_id=%s",
                    payload.get("request_id"),
                    company_id,
                    key_mapping.company_id,
                )
            if project_id is not None and project_id != key_mapping.project_id:
                verbose_proxy_logger.warning(
                    "CavadaLabs ledger using virtual-key Project context over conflicting spend-log metadata: request_id=%s metadata_project_id=%s key_project_id=%s",
                    payload.get("request_id"),
                    project_id,
                    key_mapping.project_id,
                )
            company_id = key_mapping.company_id
            project_id = key_mapping.project_id
            project_company_id = key_mapping.company_id
            source = "key_metadata"

        if key_mapping is None and project_id is not None:
            project_mapping = compat_context.project_by_project_id.get(project_id)
            if project_mapping is not None:
                project_company_id = project_mapping.company_id
                company_id = company_id or project_mapping.company_id
            elif _can_use_direct_context_without_project_lookup(
                compat_context=compat_context,
                direct_metadata=direct_metadata,
            ):
                source = source or "authenticated_metadata"
            else:
                _log_unresolved_project_context(
                    payload=payload,
                    company_id=company_id,
                    project_id=project_id,
                    project_lookup_available=compat_context.project_lookup_available,
                )
                return None

        if key_mapping is None and project_id is None:
            team_id = _str_value(payload.get("team_id"))
            if team_id is not None:
                project_mapping = compat_context.project_by_litellm_team_id.get(team_id)
                if project_mapping is not None:
                    project_id = project_mapping.project_id
                    project_company_id = project_mapping.company_id
                    company_id = company_id or project_mapping.company_id
                    source = source or "team_mapping"

        org_id = _str_value(payload.get("organization_id"))
        if org_id is not None:
            org_company_id = compat_context.company_id_by_litellm_org_id.get(org_id)
            company_id = company_id or org_company_id
            if org_company_id is not None:
                source = source or "organization_mapping"

    if company_id is None or project_id is None:
        return None

    if project_company_id is not None and company_id != project_company_id:
        verbose_proxy_logger.warning(
            "CavadaLabs ledger skipped spend log with conflicting project/company context: request_id=%s company_id=%s project_company_id=%s project_id=%s",
            payload.get("request_id"),
            company_id,
            project_company_id,
            project_id,
        )
        return None

    if (
        org_company_id is not None
        and project_company_id is not None
        and org_company_id != project_company_id
    ):
        verbose_proxy_logger.warning(
            "CavadaLabs ledger skipped spend log with conflicting LiteLLM organization/team mapping: request_id=%s organization_company_id=%s project_company_id=%s",
            payload.get("request_id"),
            org_company_id,
            project_company_id,
        )
        return None

    return CavadaLabsResolvedContext(
        company_id=company_id,
        project_id=project_id,
        source=source or "metadata",
    )


def _collect_context_lookup_ids(
    logs_to_process: List[Dict[str, Any]],
) -> tuple[set[str], set[str], set[str], set[str]]:
    team_ids: set[str] = set()
    org_ids: set[str] = set()
    project_ids: set[str] = set()
    api_key_hashes: set[str] = set()

    for payload in logs_to_process:
        metadata = _metadata_dict(payload.get("metadata"))
        sources = _metadata_sources(metadata)
        company_id = _extract_metadata_value(sources, "company_id")
        project_id = _extract_metadata_value(sources, "project_id")
        chatbot_id = _extract_metadata_value(sources, "chatbot_id")
        api_key_hash = _api_key_hash_from_payload(payload=payload, sources=sources)
        if api_key_hash is not None and (
            company_id is None
            or project_id is None
            or chatbot_id is None
            or not _has_top_level_cavadalabs_context(metadata)
        ):
            api_key_hashes.add(api_key_hash)
        if company_id is None:
            org_id = _str_value(payload.get("organization_id"))
            if org_id is not None:
                org_ids.add(org_id)
        if project_id is None or company_id is None:
            team_id = _str_value(payload.get("team_id"))
            if team_id is not None:
                team_ids.add(team_id)
        if project_id is not None:
            project_ids.add(project_id)

    return team_ids, org_ids, project_ids, api_key_hashes


async def _fetch_key_context_candidates(
    prisma_client: PrismaClient,
    api_key_hashes: set[str],
) -> Dict[str, _KeyContextCandidate]:
    if not api_key_hashes:
        return {}
    candidates: Dict[str, _KeyContextCandidate] = {}

    async def _load_rows_from_table(table_name: str, tokens: set[str]) -> None:
        if not tokens:
            return
        try:
            table = getattr(prisma_client.db, table_name)
            rows = await table.find_many(where={"token": {"in": sorted(tokens)}})
        except AttributeError:
            verbose_proxy_logger.warning(
                "CavadaLabs usage attribution skipped missing Prisma delegate %s",
                table_name,
            )
            return
        except Exception as exc:
            verbose_proxy_logger.warning(
                "CavadaLabs usage attribution skipped key-context lookup on %s: %s",
                table_name,
                exc,
            )
            return
        for row in rows:
            token = _str_value(_row_value(row, "token"))
            if token is None or token in candidates:
                continue
            metadata = _metadata_dict(_row_value(row, "metadata"))
            sources = _metadata_sources(metadata)
            candidates[token] = _KeyContextCandidate(
                token=token,
                company_id=_extract_metadata_value(sources, "company_id"),
                project_id=_extract_metadata_value(sources, "project_id"),
                chatbot_id=_extract_metadata_value(sources, "chatbot_id"),
                team_id=_str_value(_row_value(row, "team_id")),
                organization_id=_str_value(_row_value(row, "organization_id")),
            )

    await _load_rows_from_table(
        "litellm_verificationtoken",
        api_key_hashes,
    )
    missing_api_key_hashes = api_key_hashes.difference(candidates.keys())
    await _load_rows_from_table(
        "litellm_deletedverificationtoken",
        missing_api_key_hashes,
    )
    return candidates


def _build_key_context_by_api_key_hash(
    key_context_candidates: Dict[str, _KeyContextCandidate],
    project_by_litellm_team_id: Dict[str, _ProjectMapping],
    project_by_project_id: Dict[str, _ProjectMapping],
    company_id_by_litellm_org_id: Dict[str, str],
) -> Dict[str, _KeyContextMapping]:
    key_context_by_api_key_hash: Dict[str, _KeyContextMapping] = {}
    for candidate in key_context_candidates.values():
        project_mapping: Optional[_ProjectMapping] = None
        if candidate.project_id is not None:
            project_mapping = project_by_project_id.get(candidate.project_id)
        if project_mapping is None and candidate.team_id is not None:
            project_mapping = project_by_litellm_team_id.get(candidate.team_id)
        if project_mapping is None:
            continue

        company_id = candidate.company_id or project_mapping.company_id
        if company_id is None and candidate.organization_id is not None:
            company_id = company_id_by_litellm_org_id.get(candidate.organization_id)
        if company_id != project_mapping.company_id:
            verbose_proxy_logger.warning(
                "CavadaLabs ledger skipped virtual key with conflicting Company/Project context: api_key_hash=%s key_company_id=%s project_company_id=%s project_id=%s",
                candidate.token,
                company_id,
                project_mapping.company_id,
                project_mapping.project_id,
            )
            continue

        org_company_id = (
            company_id_by_litellm_org_id.get(candidate.organization_id)
            if candidate.organization_id is not None
            else None
        )
        if org_company_id is not None and org_company_id != project_mapping.company_id:
            verbose_proxy_logger.warning(
                "CavadaLabs ledger skipped virtual key with conflicting LiteLLM organization mapping: api_key_hash=%s organization_company_id=%s project_company_id=%s",
                candidate.token,
                org_company_id,
                project_mapping.company_id,
            )
            continue

        key_context_by_api_key_hash[candidate.token] = _KeyContextMapping(
            project_id=project_mapping.project_id,
            company_id=project_mapping.company_id,
            chatbot_id=candidate.chatbot_id,
        )
    return key_context_by_api_key_hash


async def _build_compat_context_resolver(
    prisma_client: PrismaClient,
    logs_to_process: List[Dict[str, Any]],
) -> _CompatContextResolver:
    team_ids, org_ids, project_ids, api_key_hashes = _collect_context_lookup_ids(
        logs_to_process
    )
    key_context_candidates = await _fetch_key_context_candidates(
        prisma_client=prisma_client,
        api_key_hashes=api_key_hashes,
    )
    for candidate in key_context_candidates.values():
        if candidate.project_id is not None:
            project_ids.add(candidate.project_id)
        if candidate.project_id is None and candidate.team_id is not None:
            team_ids.add(candidate.team_id)
        if candidate.company_id is None and candidate.organization_id is not None:
            org_ids.add(candidate.organization_id)

    project_by_litellm_team_id: Dict[str, _ProjectMapping] = {}
    project_by_project_id: Dict[str, _ProjectMapping] = {}
    company_id_by_litellm_org_id: Dict[str, str] = {}

    if team_ids:
        project_rows = await prisma_client.db.cavadalabs_projecttable.find_many(
            where={"litellm_team_id": {"in": sorted(team_ids)}}
        )
        for row in project_rows:
            team_id = _str_value(_row_value(row, "litellm_team_id"))
            project_id = _str_value(_row_value(row, "project_id"))
            company_id = _str_value(_row_value(row, "company_id"))
            if (
                team_id is not None
                and project_id is not None
                and company_id is not None
            ):
                mapping = _ProjectMapping(project_id=project_id, company_id=company_id)
                project_by_litellm_team_id[team_id] = mapping
                project_by_project_id[project_id] = mapping

    missing_project_ids = sorted(
        project_id
        for project_id in project_ids
        if project_id not in project_by_project_id
    )
    if missing_project_ids:
        project_rows = await prisma_client.db.cavadalabs_projecttable.find_many(
            where={"project_id": {"in": missing_project_ids}}
        )
        for row in project_rows:
            project_id = _str_value(_row_value(row, "project_id"))
            company_id = _str_value(_row_value(row, "company_id"))
            if project_id is not None and company_id is not None:
                project_by_project_id[project_id] = _ProjectMapping(
                    project_id=project_id,
                    company_id=company_id,
                )

    if org_ids:
        company_rows = await prisma_client.db.cavadalabs_companytable.find_many(
            where={"litellm_organization_id": {"in": sorted(org_ids)}}
        )
        for row in company_rows:
            org_id = _str_value(_row_value(row, "litellm_organization_id"))
            company_id = _str_value(_row_value(row, "company_id"))
            if org_id is not None and company_id is not None:
                company_id_by_litellm_org_id[org_id] = company_id

    key_context_by_api_key_hash = _build_key_context_by_api_key_hash(
        key_context_candidates=key_context_candidates,
        project_by_litellm_team_id=project_by_litellm_team_id,
        project_by_project_id=project_by_project_id,
        company_id_by_litellm_org_id=company_id_by_litellm_org_id,
    )

    return _CompatContextResolver(
        company_id_by_litellm_org_id=company_id_by_litellm_org_id,
        project_by_litellm_team_id=project_by_litellm_team_id,
        project_by_project_id=project_by_project_id,
        key_context_by_api_key_hash=key_context_by_api_key_hash,
    )


def _build_cavadalabs_ledger_row(
    payload: Dict[str, Any],
    compat_context: Optional[_CompatContextResolver] = None,
) -> Optional[Dict[str, Any]]:
    request_id = payload.get("request_id")
    if not isinstance(request_id, str) or not request_id.strip():
        return None

    metadata = _metadata_dict(payload.get("metadata"))
    sources = _metadata_sources(metadata)
    resolved_context = _resolve_cavadalabs_context(
        payload=payload,
        sources=sources,
        compat_context=compat_context,
    )
    if resolved_context is None:
        return None
    company_id = resolved_context.company_id
    project_id = resolved_context.project_id
    api_key_hash = _api_key_hash_from_payload(payload=payload, sources=sources)
    key_context_mapping = (
        compat_context.key_context_by_api_key_hash.get(api_key_hash)
        if compat_context is not None and api_key_hash is not None
        else None
    )

    provider = (
        _extract_metadata_value(sources, "provider")
        or payload.get("custom_llm_provider")
        or "unknown"
    )
    cavadalabs_model_alias = _extract_metadata_value(sources, "model_alias")
    if str(provider) == "cavadalabs" and cavadalabs_model_alias is not None:
        model = cavadalabs_model_alias
    else:
        model = payload.get("model") or payload.get("model_group") or "unknown"
    status = payload.get("status") or metadata.get("status") or "success"
    cavadalabs_metadata = {}
    for source in sources:
        if source is metadata:
            continue
        if "rag" in source and isinstance(source.get("rag"), dict):
            cavadalabs_metadata["rag"] = source["rag"]
        if "policy_id" in source:
            cavadalabs_metadata["policy_id"] = source.get("policy_id")
        if "guardrails" in source:
            cavadalabs_metadata["guardrails"] = source.get("guardrails")
    cavadalabs_metadata["attribution_source"] = resolved_context.source

    return {
        "request_id": request_id,
        "company_id": company_id,
        "project_id": project_id,
        "chatbot_id": _extract_metadata_value(sources, "chatbot_id")
        or (
            key_context_mapping.chatbot_id if key_context_mapping is not None else None
        ),
        "web_token_id": _extract_metadata_value(sources, "web_token_id"),
        "session_id": payload.get("session_id")
        or _extract_metadata_value(sources, "session_id"),
        "api_key_hash": api_key_hash,
        "provider": str(provider),
        "model": str(model),
        "node_id": _extract_metadata_value(sources, "node_id"),
        "gpu_id": _extract_metadata_value(sources, "gpu_id"),
        "loaded_model_id": _extract_metadata_value(sources, "loaded_model_id"),
        "model_load_request_id": _extract_metadata_value(
            sources, "model_load_request_id"
        ),
        "prompt_tokens": _int_value(payload.get("prompt_tokens")),
        "completion_tokens": _int_value(payload.get("completion_tokens")),
        "total_tokens": _int_value(payload.get("total_tokens")),
        "spend": _float_value(payload.get("spend")),
        "status": str(status),
        "metadata": {
            "model_group": payload.get("model_group"),
            "call_type": payload.get("call_type"),
            "request_tags": payload.get("request_tags"),
            "cavadalabs": cavadalabs_metadata,
        },
        "created_at": _normalize_datetime(payload.get("startTime")),
    }


def _batch_result_count(result: Any) -> Optional[int]:
    created_count = getattr(result, "count", None)
    if isinstance(created_count, int):
        return created_count
    if isinstance(result, dict) and isinstance(result.get("count"), int):
        return result["count"]
    return None


def _ledger_update_data(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in row.items()
        if key not in {"ledger_id", "request_id"}
    }


async def _repair_existing_cavadalabs_ledger_rows(
    prisma_client: PrismaClient,
    ledger_rows: List[Dict[str, Any]],
) -> int:
    ledger_table = prisma_client.db.cavadalabs_requestledgertable
    update_many = getattr(ledger_table, "update_many", None)
    if not callable(update_many):
        verbose_proxy_logger.warning(
            "CavadaLabs request ledger repair skipped missing update_many delegate"
        )
        return 0

    repaired_count = 0
    for row in ledger_rows:
        request_id = row.get("request_id")
        company_id = row.get("company_id")
        project_id = row.get("project_id")
        if not isinstance(request_id, str) or not request_id.strip():
            continue
        if not isinstance(company_id, str) or not isinstance(project_id, str):
            continue
        try:
            result = await update_many(
                where={
                    "request_id": request_id,
                    "OR": [
                        {"company_id": {"not": company_id}},
                        {"project_id": {"not": project_id}},
                    ],
                },
                data=_ledger_update_data(row),
            )
        except Exception as exc:
            verbose_proxy_logger.warning(
                "CavadaLabs request ledger duplicate repair skipped request_id=%s: %s",
                request_id,
                exc,
            )
            continue
        updated_count = _batch_result_count(result)
        repaired_count += updated_count or 0
    return repaired_count


async def process_spend_logs_cavadalabs_ledger(
    prisma_client: PrismaClient,
    logs_to_process: List[Dict[str, Any]],
) -> int:
    """
    Mirror CavadaLabs-attributed LiteLLM spend logs into the Cavada request ledger.

    Explicit CavadaLabs key metadata is authoritative. When older LiteLLM rows
    lack those fields, the processor falls back to CavadaLabs' internal
    Company-to-Organization and Project-to-Team compatibility mappings.
    """
    if not logs_to_process:
        return 0

    try:
        compat_context = await _build_compat_context_resolver(
            prisma_client=prisma_client,
            logs_to_process=logs_to_process,
        )
    except Exception as exc:
        verbose_proxy_logger.warning(
            "CavadaLabs compatibility context lookup failed; only authenticated direct CavadaLabs metadata will be attributed: %s",
            exc,
        )
        compat_context = _CompatContextResolver(
            company_id_by_litellm_org_id={},
            project_by_litellm_team_id={},
            project_by_project_id={},
            key_context_by_api_key_hash={},
            project_lookup_available=False,
            project_lookup_schema_missing=looks_like_missing_schema_exception(exc),
        )

    ledger_rows = []
    for payload in logs_to_process:
        try:
            row = _build_cavadalabs_ledger_row(
                payload=payload,
                compat_context=compat_context,
            )
        except (TypeError, ValueError) as exc:
            verbose_proxy_logger.warning(
                "CavadaLabs ledger skipped malformed spend log payload: %s", exc
            )
            continue
        if row is not None:
            ledger_rows.append(serialize_prisma_json_fields(row))
        else:
            attribution_check = inspect_cavadalabs_ledger_attribution_inputs(payload)
            if attribution_check.missing_inputs:
                verbose_proxy_logger.debug(
                    "CavadaLabs ledger skipped spend log input check: request_id=%s missing_inputs=%s",
                    attribution_check.request_id,
                    list(attribution_check.missing_inputs),
                )

    if not ledger_rows:
        return 0

    try:
        result = await prisma_client.db.cavadalabs_requestledgertable.create_many(
            data=ledger_rows,
            skip_duplicates=True,
        )
        created_count = _batch_result_count(result)
        if isinstance(created_count, int):
            if created_count < len(ledger_rows):
                repaired_count = await _repair_existing_cavadalabs_ledger_rows(
                    prisma_client=prisma_client,
                    ledger_rows=ledger_rows,
                )
                return created_count + repaired_count
            return created_count
        return len(ledger_rows)
    except Exception as exc:
        verbose_proxy_logger.warning(
            "CavadaLabs request ledger tracking failed (non-fatal): %s", exc
        )
        return 0
