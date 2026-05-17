from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Type, TypeVar

from fastapi import HTTPException, status
from pydantic import BaseModel

from litellm._logging import verbose_proxy_logger
from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.cavadalabs.dispatcher import (
    _actor_key_hash,
    _actor_user_id,
    _is_unique_violation,
)
from litellm.proxy.cavadalabs.prisma_json import (
    parse_prisma_json_fields,
    serialize_prisma_json_fields,
)
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsAISystemAssessmentCreateRequest,
    CavadaLabsAISystemAssessmentResponse,
    CavadaLabsAISystemAssessmentUpdateRequest,
    CavadaLabsChatbotResponse,
    CavadaLabsComplianceDocumentCreateRequest,
    CavadaLabsComplianceDocumentResponse,
    CavadaLabsComplianceDocumentUpdateRequest,
    CavadaLabsComplianceEvidenceCreateRequest,
    CavadaLabsComplianceEvidenceResponse,
    CavadaLabsComplianceEvidenceUpdateRequest,
    CavadaLabsComplianceFramework,
    CavadaLabsComplianceStatus,
    CavadaLabsDataSubjectRequestCreateRequest,
    CavadaLabsDataSubjectRequestResponse,
    CavadaLabsDataSubjectRequestStatus,
    CavadaLabsDataSubjectRequestType,
    CavadaLabsDataSubjectRequestUpdateRequest,
    CavadaLabsProcessingActivityCreateRequest,
    CavadaLabsProcessingActivityResponse,
    CavadaLabsProcessingActivityUpdateRequest,
    CavadaLabsProjectResponse,
    CavadaLabsRAGCollectionResponse,
)

ModelT = TypeVar("ModelT", bound=BaseModel)

_DOCUMENT_JSON_FIELDS = {
    "generated_from",
    "metadata",
}
_EVIDENCE_JSON_FIELDS = {
    "content",
    "metadata",
}
_PROCESSING_ACTIVITY_JSON_FIELDS = {
    "metadata",
}
_DSR_JSON_FIELDS = {
    "result",
    "scope",
    "metadata",
}
_ASSESSMENT_JSON_FIELDS = {
    "prohibited_practice_review",
    "human_oversight",
    "model_provider_metadata",
    "evaluation_evidence",
    "metadata",
}
_AUDIT_JSON_FIELDS = {
    "before_value",
    "after_value",
}
_JSON_FIELDS_BY_RESPONSE = {
    CavadaLabsComplianceDocumentResponse: _DOCUMENT_JSON_FIELDS,
    CavadaLabsComplianceEvidenceResponse: _EVIDENCE_JSON_FIELDS,
    CavadaLabsProcessingActivityResponse: _PROCESSING_ACTIVITY_JSON_FIELDS,
    CavadaLabsDataSubjectRequestResponse: _DSR_JSON_FIELDS,
    CavadaLabsAISystemAssessmentResponse: _ASSESSMENT_JSON_FIELDS,
}
_TERMINAL_DSR_STATUSES = {
    CavadaLabsDataSubjectRequestStatus.COMPLETED.value,
    CavadaLabsDataSubjectRequestStatus.REJECTED.value,
    CavadaLabsDataSubjectRequestStatus.CANCELLED.value,
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

    return parse_prisma_json_fields(
        data,
        json_fields=_JSON_FIELDS_BY_RESPONSE.get(response_model),
    )


def _parse_response(row: Any, response_model: Type[ModelT]) -> ModelT:
    return response_model.model_validate(_row_to_dict(row, response_model))


def _clean_scope_ids(values: Optional[Sequence[str]]) -> Optional[List[str]]:
    if values is None:
        return None
    return [value for value in dict.fromkeys(values) if value]


def _apply_company_project_scope_filters(
    where: Dict[str, Any],
    *,
    company_id: Optional[str],
    company_ids: Optional[Sequence[str]],
    project_id: Optional[str],
    project_ids: Optional[Sequence[str]],
) -> bool:
    if company_id is not None:
        where["company_id"] = company_id
    elif company_ids is not None:
        cleaned_company_ids = _clean_scope_ids(company_ids) or []
        if project_id is None and project_ids is None and not cleaned_company_ids:
            return False
        if cleaned_company_ids:
            where["company_id"] = {"in": cleaned_company_ids}

    if project_id is not None:
        where["project_id"] = project_id
    elif project_ids is not None:
        cleaned_project_ids = _clean_scope_ids(project_ids) or []
        if company_id is None and company_ids is None and not cleaned_project_ids:
            return False
        if cleaned_project_ids:
            project_filter: Dict[str, Any] = {"project_id": {"in": cleaned_project_ids}}
            if "company_id" in where:
                company_filter = {"company_id": where.pop("company_id")}
                where["OR"] = [company_filter, project_filter]
            else:
                where.update(project_filter)

    return True


def _checksum(payload: Dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class CavadaLabsComplianceService:
    def __init__(self, prisma_client: Any):
        self.prisma_client = prisma_client

    @property
    def db(self) -> Any:
        return self.prisma_client.db

    async def create_document(
        self,
        data: CavadaLabsComplianceDocumentCreateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsComplianceDocumentResponse:
        create_data = data.model_dump(mode="python")
        scope = await self._validated_scope(
            company_id=data.company_id,
            project_id=data.project_id,
            chatbot_id=data.chatbot_id,
            collection_id=data.collection_id,
        )
        create_data.update(scope)
        self._normalize_document_lifecycle(create_data)
        create_data["checksum"] = self._document_checksum(create_data)
        create_data["created_by"] = _actor_user_id(user_api_key_dict)
        create_data["updated_by"] = _actor_user_id(user_api_key_dict)
        create_data = serialize_prisma_json_fields(
            create_data,
            json_fields=_DOCUMENT_JSON_FIELDS,
        )
        try:
            row = await self.db.cavadalabs_compliancedocumenttable.create(
                data=create_data
            )
        except Exception as exc:
            if _is_unique_violation(exc):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": "Compliance document version already exists"},
                )
            raise
        response = _parse_response(row, CavadaLabsComplianceDocumentResponse)
        await self._audit(
            user_api_key_dict=user_api_key_dict,
            action="created",
            resource_type="compliance_document",
            resource_id=response.document_id,
            company_id=response.company_id,
            project_id=response.project_id,
            before_value=None,
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def get_document(
        self, document_id: str
    ) -> CavadaLabsComplianceDocumentResponse:
        row = await self.db.cavadalabs_compliancedocumenttable.find_unique(
            where={"document_id": document_id}
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"Compliance document '{document_id}' not found"},
            )
        return _parse_response(row, CavadaLabsComplianceDocumentResponse)

    async def list_documents(
        self,
        company_id: Optional[str] = None,
        company_ids: Optional[Sequence[str]] = None,
        project_id: Optional[str] = None,
        project_ids: Optional[Sequence[str]] = None,
        framework: Optional[CavadaLabsComplianceFramework] = None,
        document_type: Optional[str] = None,
        status_filter: Optional[CavadaLabsComplianceStatus] = None,
        take: int = 100,
        skip: int = 0,
    ) -> List[CavadaLabsComplianceDocumentResponse]:
        where = self._base_where(
            company_id=company_id,
            company_ids=company_ids,
            project_id=project_id,
            project_ids=project_ids,
            status_filter=status_filter,
        )
        if where is None:
            return []
        if framework is not None:
            where["framework"] = framework.value
        if document_type is not None:
            where["document_type"] = document_type.strip().lower()
        rows = await self.db.cavadalabs_compliancedocumenttable.find_many(
            where=where or None,
            take=take,
            skip=skip,
            order={"updated_at": "desc"},
        )
        return [
            _parse_response(row, CavadaLabsComplianceDocumentResponse) for row in rows
        ]

    async def update_document(
        self,
        document_id: str,
        data: CavadaLabsComplianceDocumentUpdateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsComplianceDocumentResponse:
        before = await self.get_document(document_id)
        update_data = data.model_dump(mode="python", exclude_unset=True)
        if not update_data:
            return before
        merged = {**before.model_dump(mode="python"), **update_data}
        scope = await self._validated_scope(
            company_id=before.company_id,
            project_id=merged.get("project_id"),
            chatbot_id=merged.get("chatbot_id"),
            collection_id=merged.get("collection_id"),
        )
        update_data.update(scope)
        self._normalize_document_lifecycle(merged)
        for key in ("published_at", "approved_at"):
            if key not in update_data and key in merged:
                update_data[key] = merged[key]
        update_data["checksum"] = self._document_checksum(merged)
        update_data["updated_by"] = _actor_user_id(user_api_key_dict)
        update_data = serialize_prisma_json_fields(
            update_data,
            json_fields=_DOCUMENT_JSON_FIELDS,
        )
        try:
            row = await self.db.cavadalabs_compliancedocumenttable.update(
                where={"document_id": document_id},
                data=update_data,
            )
        except Exception as exc:
            if _is_unique_violation(exc):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": "Compliance document version already exists"},
                )
            raise
        response = _parse_response(row, CavadaLabsComplianceDocumentResponse)
        await self._audit_update(
            user_api_key_dict=user_api_key_dict,
            resource_type="compliance_document",
            resource_id=response.document_id,
            company_id=response.company_id,
            project_id=response.project_id,
            before_value=before.model_dump(mode="json"),
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def create_evidence(
        self,
        data: CavadaLabsComplianceEvidenceCreateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsComplianceEvidenceResponse:
        create_data = data.model_dump(mode="python")
        scope = await self._validated_scope(
            company_id=data.company_id,
            project_id=data.project_id,
            chatbot_id=data.chatbot_id,
            collection_id=data.collection_id,
        )
        create_data.update(scope)
        create_data["captured_at"] = create_data.get("captured_at") or _now_utc()
        create_data["checksum"] = self._evidence_checksum(create_data)
        create_data["created_by"] = _actor_user_id(user_api_key_dict)
        create_data["updated_by"] = _actor_user_id(user_api_key_dict)
        create_data = serialize_prisma_json_fields(
            create_data,
            json_fields=_EVIDENCE_JSON_FIELDS,
        )
        row = await self.db.cavadalabs_complianceevidencetable.create(data=create_data)
        response = _parse_response(row, CavadaLabsComplianceEvidenceResponse)
        await self._audit(
            user_api_key_dict=user_api_key_dict,
            action="created",
            resource_type="compliance_evidence",
            resource_id=response.evidence_id,
            company_id=response.company_id,
            project_id=response.project_id,
            before_value=None,
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def list_evidence(
        self,
        company_id: Optional[str] = None,
        company_ids: Optional[Sequence[str]] = None,
        project_id: Optional[str] = None,
        project_ids: Optional[Sequence[str]] = None,
        framework: Optional[CavadaLabsComplianceFramework] = None,
        evidence_type: Optional[str] = None,
        status_filter: Optional[CavadaLabsComplianceStatus] = None,
        take: int = 100,
        skip: int = 0,
    ) -> List[CavadaLabsComplianceEvidenceResponse]:
        where = self._base_where(
            company_id=company_id,
            company_ids=company_ids,
            project_id=project_id,
            project_ids=project_ids,
            status_filter=status_filter,
        )
        if where is None:
            return []
        if framework is not None:
            where["framework"] = framework.value
        if evidence_type is not None:
            where["evidence_type"] = evidence_type.strip().lower()
        rows = await self.db.cavadalabs_complianceevidencetable.find_many(
            where=where or None,
            take=take,
            skip=skip,
            order={"captured_at": "desc"},
        )
        return [
            _parse_response(row, CavadaLabsComplianceEvidenceResponse) for row in rows
        ]

    async def get_evidence(
        self, evidence_id: str
    ) -> CavadaLabsComplianceEvidenceResponse:
        row = await self.db.cavadalabs_complianceevidencetable.find_unique(
            where={"evidence_id": evidence_id}
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"Compliance evidence '{evidence_id}' not found"},
            )
        return _parse_response(row, CavadaLabsComplianceEvidenceResponse)

    async def update_evidence(
        self,
        evidence_id: str,
        data: CavadaLabsComplianceEvidenceUpdateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsComplianceEvidenceResponse:
        before = await self.get_evidence(evidence_id)
        update_data = data.model_dump(mode="python", exclude_unset=True)
        if not update_data:
            return before
        merged = {**before.model_dump(mode="python"), **update_data}
        scope = await self._validated_scope(
            company_id=before.company_id,
            project_id=merged.get("project_id"),
            chatbot_id=merged.get("chatbot_id"),
            collection_id=merged.get("collection_id"),
        )
        update_data.update(scope)
        update_data["captured_at"] = merged.get("captured_at") or _now_utc()
        merged["captured_at"] = update_data["captured_at"]
        update_data["checksum"] = self._evidence_checksum(merged)
        update_data["updated_by"] = _actor_user_id(user_api_key_dict)
        update_data = serialize_prisma_json_fields(
            update_data,
            json_fields=_EVIDENCE_JSON_FIELDS,
        )
        row = await self.db.cavadalabs_complianceevidencetable.update(
            where={"evidence_id": evidence_id},
            data=update_data,
        )
        response = _parse_response(row, CavadaLabsComplianceEvidenceResponse)
        await self._audit_update(
            user_api_key_dict=user_api_key_dict,
            resource_type="compliance_evidence",
            resource_id=response.evidence_id,
            company_id=response.company_id,
            project_id=response.project_id,
            before_value=before.model_dump(mode="json"),
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def create_processing_activity(
        self,
        data: CavadaLabsProcessingActivityCreateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsProcessingActivityResponse:
        create_data = data.model_dump(mode="python")
        await self._validated_company_project_scope(
            company_id=data.company_id,
            project_id=data.project_id,
        )
        create_data["created_by"] = _actor_user_id(user_api_key_dict)
        create_data["updated_by"] = _actor_user_id(user_api_key_dict)
        create_data = serialize_prisma_json_fields(
            create_data,
            json_fields=_PROCESSING_ACTIVITY_JSON_FIELDS,
        )
        try:
            row = await self.db.cavadalabs_processingactivitytable.create(
                data=create_data
            )
        except Exception as exc:
            if _is_unique_violation(exc):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": "Processing activity already exists"},
                )
            raise
        response = _parse_response(row, CavadaLabsProcessingActivityResponse)
        await self._audit(
            user_api_key_dict=user_api_key_dict,
            action="created",
            resource_type="processing_activity",
            resource_id=response.activity_id,
            company_id=response.company_id,
            project_id=response.project_id,
            before_value=None,
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def list_processing_activities(
        self,
        company_id: Optional[str] = None,
        company_ids: Optional[Sequence[str]] = None,
        project_id: Optional[str] = None,
        project_ids: Optional[Sequence[str]] = None,
        status_filter: Optional[CavadaLabsComplianceStatus] = None,
        take: int = 100,
        skip: int = 0,
    ) -> List[CavadaLabsProcessingActivityResponse]:
        where = self._base_where(
            company_id=company_id,
            company_ids=company_ids,
            project_id=project_id,
            project_ids=project_ids,
            status_filter=status_filter,
        )
        if where is None:
            return []
        rows = await self.db.cavadalabs_processingactivitytable.find_many(
            where=where or None,
            take=take,
            skip=skip,
            order={"updated_at": "desc"},
        )
        return [
            _parse_response(row, CavadaLabsProcessingActivityResponse) for row in rows
        ]

    async def get_processing_activity(
        self, activity_id: str
    ) -> CavadaLabsProcessingActivityResponse:
        row = await self.db.cavadalabs_processingactivitytable.find_unique(
            where={"activity_id": activity_id}
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"Processing activity '{activity_id}' not found"},
            )
        return _parse_response(row, CavadaLabsProcessingActivityResponse)

    async def update_processing_activity(
        self,
        activity_id: str,
        data: CavadaLabsProcessingActivityUpdateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsProcessingActivityResponse:
        before = await self.get_processing_activity(activity_id)
        update_data = data.model_dump(mode="python", exclude_unset=True)
        if not update_data:
            return before
        merged = {**before.model_dump(mode="python"), **update_data}
        await self._validated_company_project_scope(
            company_id=before.company_id,
            project_id=merged.get("project_id"),
        )
        update_data["updated_by"] = _actor_user_id(user_api_key_dict)
        update_data = serialize_prisma_json_fields(
            update_data,
            json_fields=_PROCESSING_ACTIVITY_JSON_FIELDS,
        )
        try:
            row = await self.db.cavadalabs_processingactivitytable.update(
                where={"activity_id": activity_id},
                data=update_data,
            )
        except Exception as exc:
            if _is_unique_violation(exc):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": "Processing activity already exists"},
                )
            raise
        response = _parse_response(row, CavadaLabsProcessingActivityResponse)
        await self._audit_update(
            user_api_key_dict=user_api_key_dict,
            resource_type="processing_activity",
            resource_id=response.activity_id,
            company_id=response.company_id,
            project_id=response.project_id,
            before_value=before.model_dump(mode="json"),
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def create_data_subject_request(
        self,
        data: CavadaLabsDataSubjectRequestCreateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsDataSubjectRequestResponse:
        create_data = data.model_dump(mode="python")
        await self._validated_company_project_scope(
            company_id=data.company_id,
            project_id=data.project_id,
        )
        self._normalize_dsr_lifecycle(create_data)
        create_data["created_by"] = _actor_user_id(user_api_key_dict)
        create_data["updated_by"] = _actor_user_id(user_api_key_dict)
        create_data = serialize_prisma_json_fields(
            create_data,
            json_fields=_DSR_JSON_FIELDS,
        )
        row = await self.db.cavadalabs_datasubjectrequesttable.create(data=create_data)
        response = _parse_response(row, CavadaLabsDataSubjectRequestResponse)
        await self._audit(
            user_api_key_dict=user_api_key_dict,
            action="created",
            resource_type="data_subject_request",
            resource_id=response.dsr_id,
            company_id=response.company_id,
            project_id=response.project_id,
            before_value=None,
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def get_data_subject_request(
        self, dsr_id: str
    ) -> CavadaLabsDataSubjectRequestResponse:
        row = await self.db.cavadalabs_datasubjectrequesttable.find_unique(
            where={"dsr_id": dsr_id}
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"Data subject request '{dsr_id}' not found"},
            )
        return _parse_response(row, CavadaLabsDataSubjectRequestResponse)

    async def list_data_subject_requests(
        self,
        company_id: Optional[str] = None,
        company_ids: Optional[Sequence[str]] = None,
        project_id: Optional[str] = None,
        project_ids: Optional[Sequence[str]] = None,
        request_type: Optional[CavadaLabsDataSubjectRequestType] = None,
        status_filter: Optional[CavadaLabsDataSubjectRequestStatus] = None,
        requester_email: Optional[str] = None,
        take: int = 100,
        skip: int = 0,
    ) -> List[CavadaLabsDataSubjectRequestResponse]:
        where: Dict[str, Any] = {}
        if not _apply_company_project_scope_filters(
            where,
            company_id=company_id,
            company_ids=company_ids,
            project_id=project_id,
            project_ids=project_ids,
        ):
            return []
        if request_type is not None:
            where["request_type"] = request_type.value
        if status_filter is not None:
            where["status"] = status_filter.value
        if requester_email is not None:
            where["requester_email"] = requester_email.strip().lower()
        rows = await self.db.cavadalabs_datasubjectrequesttable.find_many(
            where=where or None,
            take=take,
            skip=skip,
            order={"due_at": "asc"},
        )
        return [
            _parse_response(row, CavadaLabsDataSubjectRequestResponse) for row in rows
        ]

    async def update_data_subject_request(
        self,
        dsr_id: str,
        data: CavadaLabsDataSubjectRequestUpdateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsDataSubjectRequestResponse:
        before = await self.get_data_subject_request(dsr_id)
        update_data = data.model_dump(mode="python", exclude_unset=True)
        if not update_data:
            return before
        merged = {**before.model_dump(mode="python"), **update_data}
        await self._validated_company_project_scope(
            company_id=before.company_id,
            project_id=merged.get("project_id"),
        )
        self._normalize_dsr_lifecycle(merged)
        for key in ("received_at", "due_at", "completed_at"):
            if key not in update_data and key in merged:
                update_data[key] = merged[key]
        update_data["updated_by"] = _actor_user_id(user_api_key_dict)
        update_data = serialize_prisma_json_fields(
            update_data,
            json_fields=_DSR_JSON_FIELDS,
        )
        row = await self.db.cavadalabs_datasubjectrequesttable.update(
            where={"dsr_id": dsr_id},
            data=update_data,
        )
        response = _parse_response(row, CavadaLabsDataSubjectRequestResponse)
        await self._audit_update(
            user_api_key_dict=user_api_key_dict,
            resource_type="data_subject_request",
            resource_id=response.dsr_id,
            company_id=response.company_id,
            project_id=response.project_id,
            before_value=before.model_dump(mode="json"),
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def create_ai_system_assessment(
        self,
        data: CavadaLabsAISystemAssessmentCreateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsAISystemAssessmentResponse:
        create_data = data.model_dump(mode="python")
        scope = await self._validated_scope(
            company_id=data.company_id,
            project_id=data.project_id,
            chatbot_id=data.chatbot_id,
            collection_id=None,
        )
        create_data["project_id"] = scope["project_id"]
        create_data["chatbot_id"] = scope["chatbot_id"]
        self._normalize_ai_assessment_lifecycle(create_data)
        create_data["created_by"] = _actor_user_id(user_api_key_dict)
        create_data["updated_by"] = _actor_user_id(user_api_key_dict)
        create_data = serialize_prisma_json_fields(
            create_data,
            json_fields=_ASSESSMENT_JSON_FIELDS,
        )
        try:
            row = await self.db.cavadalabs_aisystemassessmenttable.create(
                data=create_data
            )
        except Exception as exc:
            if _is_unique_violation(exc):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": "AI system assessment version already exists"},
                )
            raise
        response = _parse_response(row, CavadaLabsAISystemAssessmentResponse)
        await self._audit(
            user_api_key_dict=user_api_key_dict,
            action="created",
            resource_type="ai_system_assessment",
            resource_id=response.assessment_id,
            company_id=response.company_id,
            project_id=response.project_id,
            before_value=None,
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def list_ai_system_assessments(
        self,
        company_id: Optional[str] = None,
        company_ids: Optional[Sequence[str]] = None,
        project_id: Optional[str] = None,
        project_ids: Optional[Sequence[str]] = None,
        chatbot_id: Optional[str] = None,
        status_filter: Optional[CavadaLabsComplianceStatus] = None,
        take: int = 100,
        skip: int = 0,
    ) -> List[CavadaLabsAISystemAssessmentResponse]:
        where = self._base_where(
            company_id=company_id,
            company_ids=company_ids,
            project_id=project_id,
            project_ids=project_ids,
            status_filter=status_filter,
        )
        if where is None:
            return []
        if chatbot_id is not None:
            where["chatbot_id"] = chatbot_id
        rows = await self.db.cavadalabs_aisystemassessmenttable.find_many(
            where=where or None,
            take=take,
            skip=skip,
            order={"updated_at": "desc"},
        )
        return [
            _parse_response(row, CavadaLabsAISystemAssessmentResponse) for row in rows
        ]

    async def get_ai_system_assessment(
        self, assessment_id: str
    ) -> CavadaLabsAISystemAssessmentResponse:
        row = await self.db.cavadalabs_aisystemassessmenttable.find_unique(
            where={"assessment_id": assessment_id}
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"AI system assessment '{assessment_id}' not found"},
            )
        return _parse_response(row, CavadaLabsAISystemAssessmentResponse)

    async def update_ai_system_assessment(
        self,
        assessment_id: str,
        data: CavadaLabsAISystemAssessmentUpdateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsAISystemAssessmentResponse:
        before = await self.get_ai_system_assessment(assessment_id)
        update_data = data.model_dump(mode="python", exclude_unset=True)
        if not update_data:
            return before
        merged = {**before.model_dump(mode="python"), **update_data}
        scope = await self._validated_scope(
            company_id=before.company_id,
            project_id=merged.get("project_id"),
            chatbot_id=merged.get("chatbot_id"),
            collection_id=None,
        )
        update_data["project_id"] = scope["project_id"]
        update_data["chatbot_id"] = scope["chatbot_id"]
        self._normalize_ai_assessment_lifecycle(merged)
        if "approved_at" not in update_data:
            update_data["approved_at"] = merged.get("approved_at")
        update_data["updated_by"] = _actor_user_id(user_api_key_dict)
        update_data = serialize_prisma_json_fields(
            update_data,
            json_fields=_ASSESSMENT_JSON_FIELDS,
        )
        try:
            row = await self.db.cavadalabs_aisystemassessmenttable.update(
                where={"assessment_id": assessment_id},
                data=update_data,
            )
        except Exception as exc:
            if _is_unique_violation(exc):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": "AI system assessment version already exists"},
                )
            raise
        response = _parse_response(row, CavadaLabsAISystemAssessmentResponse)
        await self._audit_update(
            user_api_key_dict=user_api_key_dict,
            resource_type="ai_system_assessment",
            resource_id=response.assessment_id,
            company_id=response.company_id,
            project_id=response.project_id,
            before_value=before.model_dump(mode="json"),
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def _validated_company_project_scope(
        self,
        company_id: str,
        project_id: Optional[str],
    ) -> None:
        await self._require_company(company_id)
        if project_id is not None:
            await self._require_project(project_id, company_id=company_id)

    async def _validated_scope(
        self,
        company_id: str,
        project_id: Optional[str],
        chatbot_id: Optional[str],
        collection_id: Optional[str],
    ) -> Dict[str, Optional[str]]:
        await self._require_company(company_id)
        resolved_project_id = project_id
        resolved_chatbot_id = chatbot_id
        resolved_collection_id = collection_id

        if resolved_project_id is not None:
            await self._require_project(resolved_project_id, company_id=company_id)
        if resolved_chatbot_id is not None:
            chatbot = await self._require_chatbot(
                resolved_chatbot_id,
                company_id=company_id,
                project_id=resolved_project_id,
            )
            resolved_project_id = chatbot.project_id
        if resolved_collection_id is not None:
            collection = await self._require_collection(
                resolved_collection_id,
                company_id=company_id,
                project_id=resolved_project_id,
            )
            if collection.project_id is not None:
                resolved_project_id = collection.project_id
        return {
            "company_id": company_id,
            "project_id": resolved_project_id,
            "chatbot_id": resolved_chatbot_id,
            "collection_id": resolved_collection_id,
        }

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
        self,
        project_id: str,
        company_id: str,
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
        if project.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "Project does not belong to the requested company"},
            )
        return project

    async def _require_chatbot(
        self,
        chatbot_id: str,
        company_id: str,
        project_id: Optional[str],
    ) -> CavadaLabsChatbotResponse:
        row = await self.db.cavadalabs_chatbottable.find_unique(
            where={"chatbot_id": chatbot_id}
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"Chatbot '{chatbot_id}' not found"},
            )
        chatbot = _parse_response(row, CavadaLabsChatbotResponse)
        if chatbot.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "Chatbot does not belong to the requested company"},
            )
        if project_id is not None and chatbot.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "Chatbot does not belong to the requested project"},
            )
        return chatbot

    async def _require_collection(
        self,
        collection_id: str,
        company_id: str,
        project_id: Optional[str],
    ) -> CavadaLabsRAGCollectionResponse:
        row = await self.db.cavadalabs_ragcollectiontable.find_unique(
            where={"collection_id": collection_id}
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"RAG collection '{collection_id}' not found"},
            )
        collection = _parse_response(row, CavadaLabsRAGCollectionResponse)
        if collection.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "RAG collection does not belong to the requested company"
                },
            )
        if (
            project_id is not None
            and collection.project_id is not None
            and collection.project_id != project_id
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "RAG collection does not belong to the requested project"
                },
            )
        return collection

    def _base_where(
        self,
        company_id: Optional[str],
        company_ids: Optional[Sequence[str]],
        project_id: Optional[str],
        project_ids: Optional[Sequence[str]],
        status_filter: Optional[CavadaLabsComplianceStatus],
    ) -> Optional[Dict[str, Any]]:
        where: Dict[str, Any] = {}
        if not _apply_company_project_scope_filters(
            where,
            company_id=company_id,
            company_ids=company_ids,
            project_id=project_id,
            project_ids=project_ids,
        ):
            return None
        if status_filter is not None:
            where["status"] = status_filter.value
        return where

    def _normalize_document_lifecycle(self, data: Dict[str, Any]) -> None:
        if data.get("status") == CavadaLabsComplianceStatus.PUBLISHED.value:
            data["published_at"] = data.get("published_at") or _now_utc()
        if data.get("approved_by") and data.get("approved_at") is None:
            data["approved_at"] = _now_utc()

    def _normalize_dsr_lifecycle(self, data: Dict[str, Any]) -> None:
        data["received_at"] = data.get("received_at") or _now_utc()
        data["due_at"] = data.get("due_at") or (
            data["received_at"] + timedelta(days=30)
        )
        if data.get("status") in _TERMINAL_DSR_STATUSES:
            data["completed_at"] = data.get("completed_at") or _now_utc()

    def _normalize_ai_assessment_lifecycle(self, data: Dict[str, Any]) -> None:
        if data.get("approved_by") and data.get("approved_at") is None:
            data["approved_at"] = _now_utc()

    def _document_checksum(self, data: Dict[str, Any]) -> str:
        return _checksum(
            {
                "company_id": data.get("company_id"),
                "project_id": data.get("project_id"),
                "chatbot_id": data.get("chatbot_id"),
                "collection_id": data.get("collection_id"),
                "framework": data.get("framework"),
                "document_type": data.get("document_type"),
                "version": data.get("version"),
                "locale": data.get("locale"),
                "content": data.get("content"),
                "content_format": data.get("content_format"),
                "generated_from": data.get("generated_from"),
            }
        )

    def _evidence_checksum(self, data: Dict[str, Any]) -> str:
        return _checksum(
            {
                "company_id": data.get("company_id"),
                "project_id": data.get("project_id"),
                "chatbot_id": data.get("chatbot_id"),
                "collection_id": data.get("collection_id"),
                "framework": data.get("framework"),
                "evidence_type": data.get("evidence_type"),
                "source_type": data.get("source_type"),
                "source_id": data.get("source_id"),
                "content": data.get("content"),
                "captured_at": data.get("captured_at"),
            }
        )

    async def _audit_update(
        self,
        user_api_key_dict: UserAPIKeyAuth,
        resource_type: str,
        resource_id: str,
        company_id: Optional[str],
        project_id: Optional[str],
        before_value: Dict[str, Any],
        after_value: Dict[str, Any],
    ) -> None:
        await self._audit(
            user_api_key_dict=user_api_key_dict,
            action="updated",
            resource_type=resource_type,
            resource_id=resource_id,
            company_id=company_id,
            project_id=project_id,
            before_value=before_value,
            after_value=after_value,
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
                    },
                    json_fields=_AUDIT_JSON_FIELDS,
                )
            )
        except Exception:
            verbose_proxy_logger.exception(
                "Failed to write CavadaLabs compliance audit log"
            )
