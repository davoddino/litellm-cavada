from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Type, TypeVar

from fastapi import HTTPException, status
from pydantic import BaseModel

from litellm._logging import verbose_proxy_logger
from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.cavadalabs.dispatcher import (
    _actor_key_hash,
    _actor_user_id,
    _is_unique_violation,
)
from litellm.proxy.cavadalabs.prisma_json import serialize_prisma_json_fields
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsChatbotRAGAssignmentCreateRequest,
    CavadaLabsChatbotRAGAssignmentResponse,
    CavadaLabsChatbotRAGAssignmentUpdateRequest,
    CavadaLabsChatbotResponse,
    CavadaLabsProjectResponse,
    CavadaLabsRAGAssignmentStatus,
    CavadaLabsRAGCollectionCreateRequest,
    CavadaLabsRAGCollectionResponse,
    CavadaLabsRAGCollectionScope,
    CavadaLabsRAGCollectionStatus,
    CavadaLabsRAGCollectionUpdateRequest,
    CavadaLabsRAGDocumentCreateRequest,
    CavadaLabsRAGDocumentResponse,
    CavadaLabsRAGDocumentStatus,
    CavadaLabsRAGDocumentUpdateRequest,
)

ModelT = TypeVar("ModelT", bound=BaseModel)

_JSON_FIELDS = {
    "access_policy",
    "chunking_strategy",
    "metadata",
    "retrieval_config",
    "retention_policy",
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _row_to_dict(row: Any, response_model: Type[ModelT]) -> Dict[str, Any]:
    if isinstance(row, dict):
        data = dict(row)
    else:
        model_dump = getattr(row, "model_dump", None)
        data = {}
        if callable(model_dump):
            try:
                dumped = model_dump()
                if isinstance(dumped, dict):
                    data = dumped
            except Exception:
                data = {}
        if not data:
            for field_name in response_model.model_fields.keys():
                if field_name in getattr(row, "__dict__", {}):
                    data[field_name] = getattr(row, field_name)

    for key in _JSON_FIELDS:
        value = data.get(key)
        if isinstance(value, str):
            try:
                data[key] = json.loads(value)
            except json.JSONDecodeError:
                data[key] = {}
    return data


def _parse_response(row: Any, response_model: Type[ModelT]) -> ModelT:
    return response_model.model_validate(_row_to_dict(row, response_model))


class CavadaLabsRAGService:
    def __init__(self, prisma_client: Any):
        self.prisma_client = prisma_client

    @property
    def db(self) -> Any:
        return self.prisma_client.db

    async def create_collection(
        self,
        data: CavadaLabsRAGCollectionCreateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsRAGCollectionResponse:
        await self._require_company(data.company_id)
        if data.project_id is not None:
            await self._require_project(data.project_id, company_id=data.company_id)

        create_data = serialize_prisma_json_fields(
            {
                **data.model_dump(mode="python"),
                "created_by": _actor_user_id(user_api_key_dict),
                "updated_by": _actor_user_id(user_api_key_dict),
            }
        )
        try:
            row = await self.db.cavadalabs_ragcollectiontable.create(data=create_data)
        except Exception as exc:
            if _is_unique_violation(exc):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": "RAG collection already exists for this company"},
                )
            raise

        response = _parse_response(row, CavadaLabsRAGCollectionResponse)
        await self._audit(
            user_api_key_dict=user_api_key_dict,
            action="created",
            resource_type="rag_collection",
            resource_id=response.collection_id,
            company_id=response.company_id,
            project_id=response.project_id,
            before_value=None,
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def get_collection(
        self, collection_id: str
    ) -> CavadaLabsRAGCollectionResponse:
        row = await self.db.cavadalabs_ragcollectiontable.find_unique(
            where={"collection_id": collection_id}
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"RAG collection '{collection_id}' not found"},
            )
        return _parse_response(row, CavadaLabsRAGCollectionResponse)

    async def list_collections(
        self,
        company_id: Optional[str] = None,
        project_id: Optional[str] = None,
        status_filter: Optional[CavadaLabsRAGCollectionStatus] = None,
        scope_filter: Optional[CavadaLabsRAGCollectionScope] = None,
        take: int = 100,
        skip: int = 0,
    ) -> List[CavadaLabsRAGCollectionResponse]:
        where: Dict[str, Any] = {}
        if company_id is not None:
            where["company_id"] = company_id
        if project_id is not None:
            where["project_id"] = project_id
        if status_filter is not None:
            where["status"] = status_filter.value
        if scope_filter is not None:
            where["scope"] = scope_filter.value
        rows = await self.db.cavadalabs_ragcollectiontable.find_many(
            where=where or None,
            take=take,
            skip=skip,
            order={"created_at": "desc"},
        )
        return [_parse_response(row, CavadaLabsRAGCollectionResponse) for row in rows]

    async def update_collection(
        self,
        collection_id: str,
        data: CavadaLabsRAGCollectionUpdateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsRAGCollectionResponse:
        before = await self.get_collection(collection_id)
        update_data = data.model_dump(mode="python", exclude_unset=True)
        if not update_data:
            return before

        next_scope = update_data.get("scope", before.scope)
        next_project_id = update_data.get("project_id", before.project_id)
        if (
            next_scope == CavadaLabsRAGCollectionScope.PROJECT.value
            and not next_project_id
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "project-scoped RAG collections require project_id"},
            )
        if (
            next_scope == CavadaLabsRAGCollectionScope.COMPANY.value
            and next_project_id is not None
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "company-scoped RAG collections must not set project_id"
                },
            )
        if next_project_id is not None:
            await self._require_project(next_project_id, company_id=before.company_id)

        update_data["updated_by"] = _actor_user_id(user_api_key_dict)
        update_data = serialize_prisma_json_fields(update_data)
        try:
            row = await self.db.cavadalabs_ragcollectiontable.update(
                where={"collection_id": collection_id},
                data=update_data,
            )
        except Exception as exc:
            if _is_unique_violation(exc):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": "RAG collection already exists for this company"},
                )
            raise
        response = _parse_response(row, CavadaLabsRAGCollectionResponse)
        await self._audit(
            user_api_key_dict=user_api_key_dict,
            action="updated",
            resource_type="rag_collection",
            resource_id=response.collection_id,
            company_id=response.company_id,
            project_id=response.project_id,
            before_value=before.model_dump(mode="json"),
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def archive_collection(
        self,
        collection_id: str,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsRAGCollectionResponse:
        return await self.update_collection(
            collection_id,
            CavadaLabsRAGCollectionUpdateRequest(
                status=CavadaLabsRAGCollectionStatus.ARCHIVED
            ),
            user_api_key_dict,
        )

    async def create_document(
        self,
        data: CavadaLabsRAGDocumentCreateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsRAGDocumentResponse:
        collection = await self.get_collection(data.collection_id)
        if collection.status == CavadaLabsRAGCollectionStatus.ARCHIVED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "Cannot add documents to archived RAG collection"},
            )

        create_data = serialize_prisma_json_fields(
            {
                **data.model_dump(mode="python"),
                "company_id": collection.company_id,
                "project_id": collection.project_id,
                "created_by": _actor_user_id(user_api_key_dict),
                "updated_by": _actor_user_id(user_api_key_dict),
            }
        )
        if (
            create_data.get("status") == CavadaLabsRAGDocumentStatus.INDEXED.value
            and create_data.get("last_indexed_at") is None
        ):
            create_data["last_indexed_at"] = _now_utc()

        row = await self.db.cavadalabs_ragdocumenttable.create(data=create_data)
        response = _parse_response(row, CavadaLabsRAGDocumentResponse)
        await self._audit(
            user_api_key_dict=user_api_key_dict,
            action="created",
            resource_type="rag_document",
            resource_id=response.document_id,
            company_id=response.company_id,
            project_id=response.project_id,
            before_value=None,
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def get_document(self, document_id: str) -> CavadaLabsRAGDocumentResponse:
        row = await self.db.cavadalabs_ragdocumenttable.find_unique(
            where={"document_id": document_id}
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"RAG document '{document_id}' not found"},
            )
        return _parse_response(row, CavadaLabsRAGDocumentResponse)

    async def list_documents(
        self,
        collection_id: Optional[str] = None,
        company_id: Optional[str] = None,
        project_id: Optional[str] = None,
        status_filter: Optional[CavadaLabsRAGDocumentStatus] = None,
        take: int = 100,
        skip: int = 0,
    ) -> List[CavadaLabsRAGDocumentResponse]:
        where: Dict[str, Any] = {}
        if collection_id is not None:
            where["collection_id"] = collection_id
        if company_id is not None:
            where["company_id"] = company_id
        if project_id is not None:
            where["project_id"] = project_id
        if status_filter is not None:
            where["status"] = status_filter.value
        rows = await self.db.cavadalabs_ragdocumenttable.find_many(
            where=where or None,
            take=take,
            skip=skip,
            order={"created_at": "desc"},
        )
        return [_parse_response(row, CavadaLabsRAGDocumentResponse) for row in rows]

    async def update_document(
        self,
        document_id: str,
        data: CavadaLabsRAGDocumentUpdateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsRAGDocumentResponse:
        before = await self.get_document(document_id)
        update_data = data.model_dump(mode="python", exclude_unset=True)
        if not update_data:
            return before

        next_status = update_data.get("status", before.status)
        next_failure_reason = update_data.get("failure_reason", before.failure_reason)
        if (
            next_status == CavadaLabsRAGDocumentStatus.FAILED.value
            and not next_failure_reason
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "failed RAG documents require failure_reason"},
            )
        if (
            next_status == CavadaLabsRAGDocumentStatus.INDEXED.value
            and update_data.get("last_indexed_at") is None
            and before.last_indexed_at is None
        ):
            update_data["last_indexed_at"] = _now_utc()

        update_data["updated_by"] = _actor_user_id(user_api_key_dict)
        update_data = serialize_prisma_json_fields(update_data)
        row = await self.db.cavadalabs_ragdocumenttable.update(
            where={"document_id": document_id},
            data=update_data,
        )
        response = _parse_response(row, CavadaLabsRAGDocumentResponse)
        await self._audit(
            user_api_key_dict=user_api_key_dict,
            action="updated",
            resource_type="rag_document",
            resource_id=response.document_id,
            company_id=response.company_id,
            project_id=response.project_id,
            before_value=before.model_dump(mode="json"),
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def create_assignment(
        self,
        data: CavadaLabsChatbotRAGAssignmentCreateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsChatbotRAGAssignmentResponse:
        collection = await self.get_collection(data.collection_id)
        if collection.status == CavadaLabsRAGCollectionStatus.ARCHIVED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "Archived RAG collections cannot be assigned"},
            )
        chatbot = await self._require_chatbot(data.chatbot_id)
        self._validate_chatbot_collection_match(chatbot, collection)

        create_data = serialize_prisma_json_fields(
            {
                **data.model_dump(mode="python"),
                "company_id": chatbot.company_id,
                "project_id": chatbot.project_id,
                "created_by": _actor_user_id(user_api_key_dict),
                "updated_by": _actor_user_id(user_api_key_dict),
            }
        )
        try:
            row = await self.db.cavadalabs_chatbotragassignmenttable.create(
                data=create_data
            )
        except Exception as exc:
            if _is_unique_violation(exc):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": "RAG collection is already assigned to this chatbot"
                    },
                )
            raise

        response = _parse_response(row, CavadaLabsChatbotRAGAssignmentResponse)
        if response.status == CavadaLabsRAGAssignmentStatus.ACTIVE.value:
            await self._add_collection_to_chatbot_and_project(
                chatbot_id=response.chatbot_id,
                project_id=response.project_id,
                collection_id=response.collection_id,
                user_api_key_dict=user_api_key_dict,
            )
        await self._audit(
            user_api_key_dict=user_api_key_dict,
            action="created",
            resource_type="chatbot_rag_assignment",
            resource_id=response.assignment_id,
            company_id=response.company_id,
            project_id=response.project_id,
            before_value=None,
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def list_assignments(
        self,
        company_id: Optional[str] = None,
        project_id: Optional[str] = None,
        chatbot_id: Optional[str] = None,
        collection_id: Optional[str] = None,
        status_filter: Optional[CavadaLabsRAGAssignmentStatus] = None,
        take: int = 100,
        skip: int = 0,
    ) -> List[CavadaLabsChatbotRAGAssignmentResponse]:
        where: Dict[str, Any] = {}
        if company_id is not None:
            where["company_id"] = company_id
        if project_id is not None:
            where["project_id"] = project_id
        if chatbot_id is not None:
            where["chatbot_id"] = chatbot_id
        if collection_id is not None:
            where["collection_id"] = collection_id
        if status_filter is not None:
            where["status"] = status_filter.value
        rows = await self.db.cavadalabs_chatbotragassignmenttable.find_many(
            where=where or None,
            take=take,
            skip=skip,
            order={"priority": "asc"},
        )
        return [
            _parse_response(row, CavadaLabsChatbotRAGAssignmentResponse) for row in rows
        ]

    async def get_assignment(
        self, assignment_id: str
    ) -> CavadaLabsChatbotRAGAssignmentResponse:
        row = await self.db.cavadalabs_chatbotragassignmenttable.find_unique(
            where={"assignment_id": assignment_id}
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"RAG assignment '{assignment_id}' not found"},
            )
        return _parse_response(row, CavadaLabsChatbotRAGAssignmentResponse)

    async def update_assignment(
        self,
        assignment_id: str,
        data: CavadaLabsChatbotRAGAssignmentUpdateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsChatbotRAGAssignmentResponse:
        before = await self.get_assignment(assignment_id)
        update_data = data.model_dump(mode="python", exclude_unset=True)
        if not update_data:
            return before

        update_data["updated_by"] = _actor_user_id(user_api_key_dict)
        update_data = serialize_prisma_json_fields(update_data)
        row = await self.db.cavadalabs_chatbotragassignmenttable.update(
            where={"assignment_id": assignment_id},
            data=update_data,
        )
        response = _parse_response(row, CavadaLabsChatbotRAGAssignmentResponse)
        if response.status == CavadaLabsRAGAssignmentStatus.ACTIVE.value:
            await self._add_collection_to_chatbot_and_project(
                chatbot_id=response.chatbot_id,
                project_id=response.project_id,
                collection_id=response.collection_id,
                user_api_key_dict=user_api_key_dict,
            )
        elif response.status == CavadaLabsRAGAssignmentStatus.DISABLED.value:
            await self._remove_collection_from_chatbot(
                chatbot_id=response.chatbot_id,
                collection_id=response.collection_id,
                user_api_key_dict=user_api_key_dict,
            )
        await self._audit(
            user_api_key_dict=user_api_key_dict,
            action="updated",
            resource_type="chatbot_rag_assignment",
            resource_id=response.assignment_id,
            company_id=response.company_id,
            project_id=response.project_id,
            before_value=before.model_dump(mode="json"),
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def disable_assignment(
        self,
        assignment_id: str,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsChatbotRAGAssignmentResponse:
        return await self.update_assignment(
            assignment_id,
            CavadaLabsChatbotRAGAssignmentUpdateRequest(
                status=CavadaLabsRAGAssignmentStatus.DISABLED
            ),
            user_api_key_dict,
        )

    async def _require_company(self, company_id: str) -> None:
        row = await self.db.cavadalabs_companytable.find_unique(
            where={"company_id": company_id}
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"Company '{company_id}' not found"},
            )

    async def _require_project(
        self, project_id: str, company_id: Optional[str] = None
    ) -> CavadaLabsProjectResponse:
        row = await self.db.cavadalabs_projecttable.find_unique(
            where={"project_id": project_id}
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"Project '{project_id}' not found"},
            )
        project = _parse_response(row, CavadaLabsProjectResponse)
        if company_id is not None and project.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "Project does not belong to the requested company"},
            )
        return project

    async def _require_chatbot(self, chatbot_id: str) -> CavadaLabsChatbotResponse:
        row = await self.db.cavadalabs_chatbottable.find_unique(
            where={"chatbot_id": chatbot_id}
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"Chatbot '{chatbot_id}' not found"},
            )
        return _parse_response(row, CavadaLabsChatbotResponse)

    def _validate_chatbot_collection_match(
        self,
        chatbot: CavadaLabsChatbotResponse,
        collection: CavadaLabsRAGCollectionResponse,
    ) -> None:
        if chatbot.company_id != collection.company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "RAG collection and chatbot belong to different companies"
                },
            )
        if (
            collection.scope == CavadaLabsRAGCollectionScope.PROJECT.value
            and collection.project_id != chatbot.project_id
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "Project-scoped RAG collection cannot be assigned to this chatbot"
                },
            )

    async def _add_collection_to_chatbot_and_project(
        self,
        chatbot_id: str,
        project_id: str,
        collection_id: str,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> None:
        await self._update_string_array_field(
            model=self.db.cavadalabs_chatbottable,
            where={"chatbot_id": chatbot_id},
            field_name="assigned_rag_collections",
            value=collection_id,
            add=True,
            user_api_key_dict=user_api_key_dict,
        )
        await self._update_string_array_field(
            model=self.db.cavadalabs_projecttable,
            where={"project_id": project_id},
            field_name="allowed_rag_collections",
            value=collection_id,
            add=True,
            user_api_key_dict=user_api_key_dict,
        )

    async def _remove_collection_from_chatbot(
        self,
        chatbot_id: str,
        collection_id: str,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> None:
        await self._update_string_array_field(
            model=self.db.cavadalabs_chatbottable,
            where={"chatbot_id": chatbot_id},
            field_name="assigned_rag_collections",
            value=collection_id,
            add=False,
            user_api_key_dict=user_api_key_dict,
        )

    async def _update_string_array_field(
        self,
        model: Any,
        where: Dict[str, str],
        field_name: str,
        value: str,
        add: bool,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> None:
        row = await model.find_unique(where=where)
        if row is None:
            return
        current = list(getattr(row, field_name, []) or [])
        if add and value not in current:
            current.append(value)
        elif not add:
            current = [item for item in current if item != value]
        else:
            return
        await model.update(
            where=where,
            data={
                field_name: current,
                "updated_by": _actor_user_id(user_api_key_dict),
            },
        )

    async def _audit(
        self,
        user_api_key_dict: UserAPIKeyAuth,
        action: str,
        resource_type: str,
        resource_id: str,
        company_id: Optional[str],
        project_id: Optional[str],
        before_value: Optional[Dict[str, Any]],
        after_value: Optional[Dict[str, Any]],
    ) -> None:
        try:
            await self.db.cavadalabs_auditlogtable.create(
                data=serialize_prisma_json_fields(
                    {
                    "actor_user_id": _actor_user_id(user_api_key_dict),
                    "actor_api_key_hash": _actor_key_hash(user_api_key_dict),
                    "action": action,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "company_id": company_id,
                    "project_id": project_id,
                    "before_value": before_value,
                    "after_value": after_value,
                    }
                )
            )
        except Exception:
            verbose_proxy_logger.exception("Failed to write CavadaLabs RAG audit log")
