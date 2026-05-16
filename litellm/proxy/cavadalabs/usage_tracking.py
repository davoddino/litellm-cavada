from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from litellm._logging import verbose_proxy_logger
from litellm.litellm_core_utils.safe_json_loads import safe_json_loads
from litellm.proxy.cavadalabs.prisma_json import serialize_prisma_json_fields
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
class _CompatContextResolver:
    company_id_by_litellm_org_id: Dict[str, str]
    project_by_litellm_team_id: Dict[str, _ProjectMapping]
    project_by_project_id: Dict[str, _ProjectMapping]
    key_context_by_api_key_hash: Dict[str, _KeyContextMapping]
    project_lookup_available: bool = True


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
        value = metadata.get(key)
        if isinstance(value, dict):
            sources.append(value)
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


def _resolve_cavadalabs_context(
    payload: Dict[str, Any],
    sources: List[Dict[str, Any]],
    compat_context: Optional[_CompatContextResolver],
) -> Optional[CavadaLabsResolvedContext]:
    company_id = _extract_metadata_value(sources, "company_id")
    project_id = _extract_metadata_value(sources, "project_id")
    project_company_id: Optional[str] = None
    org_company_id: Optional[str] = None
    source = "metadata" if company_id is not None or project_id is not None else None

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
            else:
                if compat_context.project_lookup_available:
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
            "CavadaLabs compatibility context lookup failed; unvalidated CavadaLabs usage attribution will be skipped: %s",
            exc,
        )
        compat_context = _CompatContextResolver(
            company_id_by_litellm_org_id={},
            project_by_litellm_team_id={},
            project_by_project_id={},
            key_context_by_api_key_hash={},
            project_lookup_available=False,
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

    if not ledger_rows:
        return 0

    try:
        result = await prisma_client.db.cavadalabs_requestledgertable.create_many(
            data=ledger_rows,
            skip_duplicates=True,
        )
        created_count = getattr(result, "count", None)
        if isinstance(created_count, int):
            return created_count
        if isinstance(result, dict) and isinstance(result.get("count"), int):
            return result["count"]
        return len(ledger_rows)
    except Exception as exc:
        verbose_proxy_logger.warning(
            "CavadaLabs request ledger tracking failed (non-fatal): %s", exc
        )
        return 0
