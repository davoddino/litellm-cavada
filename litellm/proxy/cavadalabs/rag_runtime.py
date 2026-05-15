from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple, TypeVar

from fastapi import HTTPException, status
from pydantic import BaseModel

from litellm._logging import verbose_proxy_logger
from litellm.proxy.cavadalabs.dispatcher import CavadaLabsRuntimeContext
from litellm.proxy.cavadalabs.rag import _parse_response
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsChatCompletionRequest,
    CavadaLabsChatbotRAGAssignmentResponse,
    CavadaLabsRAGAssignmentStatus,
    CavadaLabsRAGCollectionResponse,
    CavadaLabsRAGCollectionStatus,
)

ModelT = TypeVar("ModelT", bound=BaseModel)

_DEFAULT_MAX_CONTEXT_CHARS = 12000
_DEFAULT_MAX_CHARS_PER_RESULT = 2000
_DEFAULT_TOP_K = 5


class CavadaLabsVectorStoreSearchClient(Protocol):
    async def search(
        self,
        *,
        vector_store_id: str,
        query: str,
        custom_llm_provider: Optional[str],
        filters: Optional[Dict[str, Any]],
        max_num_results: int,
        ranking_options: Optional[Dict[str, Any]],
        rewrite_query: Optional[bool],
        timeout: Optional[float],
    ) -> Dict[str, Any]:
        pass


@dataclass(frozen=True)
class CavadaLabsRAGSource:
    collection_id: str
    vector_store_id: str
    document_id: Optional[str]
    file_id: Optional[str]
    filename: Optional[str]
    score: Optional[float]
    text: str
    attributes: Dict[str, Any]


@dataclass(frozen=True)
class CavadaLabsRAGContext:
    query: str
    context_text: str
    sources: List[CavadaLabsRAGSource]
    collection_ids: List[str]
    skipped_collection_ids: List[str]

    @property
    def has_context(self) -> bool:
        return bool(self.context_text.strip())

    def metadata(self) -> Dict[str, Any]:
        document_ids = _unique_strings([source.document_id for source in self.sources])
        file_ids = _unique_strings([source.file_id for source in self.sources])
        return {
            "query": self.query,
            "collection_ids": self.collection_ids,
            "document_ids": document_ids,
            "file_ids": file_ids,
            "result_count": len(self.sources),
            "skipped_collection_ids": self.skipped_collection_ids,
            "sources": [
                {
                    "collection_id": source.collection_id,
                    "vector_store_id": source.vector_store_id,
                    "document_id": source.document_id,
                    "file_id": source.file_id,
                    "filename": source.filename,
                    "score": source.score,
                }
                for source in self.sources
            ],
        }


class LiteLLMVectorStoreSearchClient:
    async def search(
        self,
        *,
        vector_store_id: str,
        query: str,
        custom_llm_provider: Optional[str],
        filters: Optional[Dict[str, Any]],
        max_num_results: int,
        ranking_options: Optional[Dict[str, Any]],
        rewrite_query: Optional[bool],
        timeout: Optional[float],
    ) -> Dict[str, Any]:
        from litellm.vector_stores.main import search

        response = await asyncio.to_thread(
            search,
            vector_store_id=vector_store_id,
            query=query,
            filters=filters,
            max_num_results=max_num_results,
            ranking_options=ranking_options,
            rewrite_query=rewrite_query,
            timeout=timeout,
            custom_llm_provider=custom_llm_provider,
        )
        if isinstance(response, dict):
            return response
        model_dump = getattr(response, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump()
            if isinstance(dumped, dict):
                return dumped
        return dict(response)


class CavadaLabsRAGRuntimeService:
    def __init__(
        self,
        prisma_client: Any,
        search_client: Optional[CavadaLabsVectorStoreSearchClient] = None,
    ):
        self.prisma_client = prisma_client
        self.search_client = search_client or LiteLLMVectorStoreSearchClient()

    @property
    def db(self) -> Any:
        return self.prisma_client.db

    async def retrieve_context(
        self,
        *,
        context: CavadaLabsRuntimeContext,
        request_data: CavadaLabsChatCompletionRequest,
    ) -> CavadaLabsRAGContext:
        query = _extract_query(request_data.messages)
        if not query:
            return CavadaLabsRAGContext(
                query="",
                context_text="",
                sources=[],
                collection_ids=[],
                skipped_collection_ids=[],
            )

        assignments = await self._list_active_assignments(
            chatbot_id=context.chatbot.chatbot_id
        )
        if not assignments and not context.chatbot.assigned_rag_collections:
            return CavadaLabsRAGContext(
                query=query,
                context_text="",
                sources=[],
                collection_ids=[],
                skipped_collection_ids=[],
            )

        assignment_pairs = await self._resolve_assignment_collections(
            context=context,
            assignments=assignments,
        )
        if not assignment_pairs:
            return CavadaLabsRAGContext(
                query=query,
                context_text="",
                sources=[],
                collection_ids=[],
                skipped_collection_ids=[],
            )

        sources: List[CavadaLabsRAGSource] = []
        collection_ids: List[str] = []
        skipped_collection_ids: List[str] = []
        remaining_chars = _max_context_chars(assignment_pairs)

        for assignment, collection in assignment_pairs:
            collection_ids.append(collection.collection_id)
            if remaining_chars <= 0:
                skipped_collection_ids.append(collection.collection_id)
                continue

            config = assignment.retrieval_config
            try:
                collection_sources = await self._search_collection(
                    assignment=assignment,
                    collection=collection,
                    query=query,
                    remaining_chars=remaining_chars,
                )
            except Exception as exc:
                if _fail_open(config):
                    verbose_proxy_logger.warning(
                        "CavadaLabs RAG retrieval skipped collection %s: %s",
                        collection.collection_id,
                        exc,
                    )
                    skipped_collection_ids.append(collection.collection_id)
                    continue
                if isinstance(exc, HTTPException):
                    raise
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={
                        "error": "CavadaLabs RAG retrieval failed",
                        "collection_id": collection.collection_id,
                    },
                ) from exc

            for source in collection_sources:
                if remaining_chars <= 0:
                    break
                trimmed = source.text[:remaining_chars]
                if not trimmed:
                    continue
                sources.append(
                    CavadaLabsRAGSource(
                        collection_id=source.collection_id,
                        vector_store_id=source.vector_store_id,
                        document_id=source.document_id,
                        file_id=source.file_id,
                        filename=source.filename,
                        score=source.score,
                        text=trimmed,
                        attributes=source.attributes,
                    )
                )
                remaining_chars -= len(trimmed)

        context_text = _format_context_sources(sources)
        return CavadaLabsRAGContext(
            query=query,
            context_text=context_text,
            sources=sources,
            collection_ids=_unique_strings(collection_ids),
            skipped_collection_ids=_unique_strings(skipped_collection_ids),
        )

    async def _list_active_assignments(
        self, chatbot_id: str
    ) -> List[CavadaLabsChatbotRAGAssignmentResponse]:
        rows = await self.db.cavadalabs_chatbotragassignmenttable.find_many(
            where={
                "chatbot_id": chatbot_id,
                "status": CavadaLabsRAGAssignmentStatus.ACTIVE.value,
            },
            order={"priority": "asc"},
        )
        return [
            _parse_response(row, CavadaLabsChatbotRAGAssignmentResponse) for row in rows
        ]

    async def _resolve_assignment_collections(
        self,
        *,
        context: CavadaLabsRuntimeContext,
        assignments: Sequence[CavadaLabsChatbotRAGAssignmentResponse],
    ) -> List[
        Tuple[CavadaLabsChatbotRAGAssignmentResponse, CavadaLabsRAGCollectionResponse]
    ]:
        pairs: List[
            Tuple[
                CavadaLabsChatbotRAGAssignmentResponse,
                CavadaLabsRAGCollectionResponse,
            ]
        ] = []
        for assignment in assignments:
            if assignment.company_id != context.company.company_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": "RAG assignment company mismatch"},
                )
            if assignment.project_id != context.project.project_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": "RAG assignment project mismatch"},
                )
            row = await self.db.cavadalabs_ragcollectiontable.find_unique(
                where={"collection_id": assignment.collection_id}
            )
            if row is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": "RAG assignment references a missing collection",
                        "collection_id": assignment.collection_id,
                    },
                )
            collection = _parse_response(row, CavadaLabsRAGCollectionResponse)
            if collection.status != CavadaLabsRAGCollectionStatus.ACTIVE.value:
                continue
            if collection.company_id != context.company.company_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": "RAG collection company mismatch"},
                )
            if (
                collection.project_id is not None
                and collection.project_id != context.project.project_id
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": "RAG collection project mismatch"},
                )
            pairs.append((assignment, collection))
        return pairs

    async def _search_collection(
        self,
        *,
        assignment: CavadaLabsChatbotRAGAssignmentResponse,
        collection: CavadaLabsRAGCollectionResponse,
        query: str,
        remaining_chars: int,
    ) -> List[CavadaLabsRAGSource]:
        if not collection.vector_store_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "Active RAG collection has no vector_store_id",
                    "collection_id": collection.collection_id,
                },
            )
        if not collection.vector_store_provider:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "Active RAG collection has no vector_store_provider",
                    "collection_id": collection.collection_id,
                },
            )

        config = assignment.retrieval_config
        max_results = _int_config(config, "max_num_results", "top_k") or _DEFAULT_TOP_K
        max_results = max(1, min(max_results, 50))
        max_chars_per_result = (
            _int_config(config, "max_chars_per_result") or _DEFAULT_MAX_CHARS_PER_RESULT
        )
        max_chars_per_result = max(256, min(max_chars_per_result, remaining_chars))

        response = await self.search_client.search(
            vector_store_id=collection.vector_store_id,
            query=query,
            custom_llm_provider=collection.vector_store_provider,
            filters=_dict_config(config, "filters"),
            max_num_results=max_results,
            ranking_options=_dict_config(config, "ranking_options"),
            rewrite_query=_bool_config(config, "rewrite_query"),
            timeout=_float_config(config, "timeout"),
        )
        return _normalize_search_response(
            response=response,
            collection=collection,
            max_chars_per_result=max_chars_per_result,
        )


def _extract_query(messages: Sequence[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for message in reversed(messages):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content")
        extracted = _extract_content_text(content)
        if extracted:
            parts.append(extracted)
            break
    return "\n".join(parts).strip()


def _extract_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("text"), str):
                parts.append(item["text"].strip())
            elif isinstance(item.get("content"), str):
                parts.append(item["content"].strip())
        return "\n".join(part for part in parts if part).strip()
    return ""


def _normalize_search_response(
    *,
    response: Dict[str, Any],
    collection: CavadaLabsRAGCollectionResponse,
    max_chars_per_result: int,
) -> List[CavadaLabsRAGSource]:
    data = response.get("data")
    if not isinstance(data, list):
        return []

    sources: List[CavadaLabsRAGSource] = []
    for result in data:
        if not isinstance(result, dict):
            continue
        text = _result_text(result)
        if not text:
            continue
        attributes = result.get("attributes")
        if not isinstance(attributes, dict):
            attributes = {}
        sources.append(
            CavadaLabsRAGSource(
                collection_id=collection.collection_id,
                vector_store_id=collection.vector_store_id or "",
                document_id=_string_or_none(
                    attributes.get("document_id")
                    or attributes.get("cavadalabs_document_id")
                ),
                file_id=_string_or_none(result.get("file_id")),
                filename=_string_or_none(result.get("filename")),
                score=_float_or_none(result.get("score")),
                text=text[:max_chars_per_result],
                attributes=attributes,
            )
        )
    return sources


def _result_text(result: Dict[str, Any]) -> str:
    content = result.get("content")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"].strip())
        return "\n".join(part for part in parts if part).strip()
    if isinstance(content, str):
        return content.strip()
    text = result.get("text")
    return text.strip() if isinstance(text, str) else ""


def _format_context_sources(sources: Sequence[CavadaLabsRAGSource]) -> str:
    sections = []
    for index, source in enumerate(sources, start=1):
        label = source.filename or source.file_id or source.document_id or "source"
        sections.append(
            "\n".join(
                [
                    f"[{index}] collection={source.collection_id} source={label}",
                    source.text.strip(),
                ]
            )
        )
    return "\n\n".join(sections)


def _max_context_chars(
    pairs: Sequence[
        Tuple[CavadaLabsChatbotRAGAssignmentResponse, CavadaLabsRAGCollectionResponse]
    ],
) -> int:
    limits = [
        _int_config(assignment.retrieval_config, "max_context_chars")
        for assignment, _ in pairs
    ]
    configured = [limit for limit in limits if limit is not None and limit > 0]
    if configured:
        return min(configured)
    return _DEFAULT_MAX_CONTEXT_CHARS


def _fail_open(config: Dict[str, Any]) -> bool:
    return config.get("fail_open") is True


def _dict_config(config: Dict[str, Any], key: str) -> Optional[Dict[str, Any]]:
    value = config.get(key)
    return value if isinstance(value, dict) else None


def _bool_config(config: Dict[str, Any], key: str) -> Optional[bool]:
    value = config.get(key)
    return value if isinstance(value, bool) else None


def _int_config(config: Dict[str, Any], *keys: str) -> Optional[int]:
    for key in keys:
        value = config.get(key)
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, str) and value.isdigit():
            parsed = int(value)
            if parsed > 0:
                return parsed
    return None


def _float_config(config: Dict[str, Any], key: str) -> Optional[float]:
    value = config.get(key)
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    if isinstance(value, str):
        try:
            parsed = float(value)
        except ValueError:
            return None
        return parsed if parsed > 0 else None
    return None


def _float_or_none(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _string_or_none(value: Any) -> Optional[str]:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _unique_strings(values: Sequence[Optional[str]]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        if value is None or value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result
