from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.auth.user_api_key_auth import user_api_key_auth
from litellm.proxy.cavadalabs.access_control import (
    is_cavadalabs_admin_view,
    require_company_wide_access,
    require_project_access,
    visible_company_wide_ids_for_user,
    visible_project_ids_for_user,
)
from litellm.proxy.cavadalabs.compliance import CavadaLabsComplianceService
from litellm.proxy.management_helpers.utils import management_endpoint_wrapper
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsAISystemAssessmentCreateRequest,
    CavadaLabsAISystemAssessmentListResponse,
    CavadaLabsAISystemAssessmentResponse,
    CavadaLabsAISystemAssessmentUpdateRequest,
    CavadaLabsComplianceDocumentCreateRequest,
    CavadaLabsComplianceDocumentListResponse,
    CavadaLabsComplianceDocumentResponse,
    CavadaLabsComplianceDocumentUpdateRequest,
    CavadaLabsComplianceEvidenceCreateRequest,
    CavadaLabsComplianceEvidenceListResponse,
    CavadaLabsComplianceEvidenceResponse,
    CavadaLabsComplianceEvidenceUpdateRequest,
    CavadaLabsComplianceFramework,
    CavadaLabsComplianceStatus,
    CavadaLabsDataSubjectRequestCreateRequest,
    CavadaLabsDataSubjectRequestListResponse,
    CavadaLabsDataSubjectRequestResponse,
    CavadaLabsDataSubjectRequestStatus,
    CavadaLabsDataSubjectRequestType,
    CavadaLabsDataSubjectRequestUpdateRequest,
    CavadaLabsProcessingActivityCreateRequest,
    CavadaLabsProcessingActivityListResponse,
    CavadaLabsProcessingActivityResponse,
    CavadaLabsProcessingActivityUpdateRequest,
)

router = APIRouter(prefix="/cavadalabs", tags=["cavadalabs-compliance"])


def _prisma_client():
    from litellm.proxy import proxy_server

    if proxy_server.prisma_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Database is required for CavadaLabs compliance"},
        )
    return proxy_server.prisma_client


def _service() -> CavadaLabsComplianceService:
    return CavadaLabsComplianceService(_prisma_client())


async def _require_compliance_scope_access(
    *,
    company_id: str,
    project_id: Optional[str],
    user_api_key_dict: UserAPIKeyAuth,
    require_admin: bool,
) -> None:
    db = _prisma_client().db
    if project_id is not None:
        project = await require_project_access(
            db,
            project_id=project_id,
            user_api_key_dict=user_api_key_dict,
            require_admin=require_admin,
        )
        if project.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "project_id must belong to company_id"},
            )
        return
    await require_company_wide_access(
        db,
        company_id=company_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=require_admin,
    )


async def _resolve_compliance_list_filters(
    *,
    company_id: Optional[str],
    project_id: Optional[str],
    user_api_key_dict: UserAPIKeyAuth,
) -> tuple[Optional[str], Optional[list[str]], Optional[str], Optional[list[str]]]:
    db = _prisma_client().db
    if project_id is not None:
        project = await require_project_access(
            db,
            project_id=project_id,
            user_api_key_dict=user_api_key_dict,
            require_admin=False,
        )
        if company_id is not None and project.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "project_id must belong to company_id"},
            )
        return None, None, project_id, None

    if company_id is not None:
        try:
            await require_company_wide_access(
                db,
                company_id=company_id,
                user_api_key_dict=user_api_key_dict,
                require_admin=False,
            )
            return company_id, None, None, None
        except HTTPException as exc:
            if exc.status_code != status.HTTP_403_FORBIDDEN:
                raise
            visible_project_ids = await visible_project_ids_for_user(
                db,
                user_api_key_dict,
                company_id=company_id,
            )
            if not visible_project_ids:
                raise
            return None, None, None, sorted(visible_project_ids)

    if is_cavadalabs_admin_view(user_api_key_dict):
        return None, None, None, None

    visible_company_ids = await visible_company_wide_ids_for_user(
        db,
        user_api_key_dict,
    )
    visible_project_ids = await visible_project_ids_for_user(db, user_api_key_dict)
    return (
        None,
        sorted(visible_company_ids or set()),
        None,
        sorted(visible_project_ids or set()),
    )


def _target_project_id(current: object, data: object) -> Optional[str]:
    fields_set = getattr(data, "model_fields_set", set())
    if "project_id" in fields_set:
        return getattr(data, "project_id", None)
    return getattr(current, "project_id", None)


async def _require_current_and_target_scope_access(
    *,
    current: object,
    data: object,
    user_api_key_dict: UserAPIKeyAuth,
) -> None:
    company_id = getattr(current, "company_id")
    current_project_id = getattr(current, "project_id", None)
    await _require_compliance_scope_access(
        company_id=company_id,
        project_id=current_project_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=True,
    )
    target_project_id = _target_project_id(current, data)
    if target_project_id != current_project_id:
        await _require_compliance_scope_access(
            company_id=company_id,
            project_id=target_project_id,
            user_api_key_dict=user_api_key_dict,
            require_admin=True,
        )


@router.post(
    "/compliance-documents",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsComplianceDocumentResponse,
)
@management_endpoint_wrapper
async def create_compliance_document(
    data: CavadaLabsComplianceDocumentCreateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsComplianceDocumentResponse:
    await _require_compliance_scope_access(
        company_id=data.company_id,
        project_id=data.project_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=True,
    )
    return await _service().create_document(data, user_api_key_dict)


@router.get(
    "/compliance-documents",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsComplianceDocumentListResponse,
)
@management_endpoint_wrapper
async def list_compliance_documents(
    http_request: Request,
    company_id: Optional[str] = None,
    project_id: Optional[str] = None,
    framework: Optional[CavadaLabsComplianceFramework] = None,
    document_type: Optional[str] = None,
    status_filter: Optional[CavadaLabsComplianceStatus] = Query(
        default=None, alias="status"
    ),
    take: int = Query(default=100, ge=1, le=1000),
    skip: int = Query(default=0, ge=0),
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsComplianceDocumentListResponse:
    scoped_company_id, scoped_company_ids, scoped_project_id, scoped_project_ids = (
        await _resolve_compliance_list_filters(
            company_id=company_id,
            project_id=project_id,
            user_api_key_dict=user_api_key_dict,
        )
    )
    documents = await _service().list_documents(
        company_id=scoped_company_id,
        company_ids=scoped_company_ids,
        project_id=scoped_project_id,
        project_ids=scoped_project_ids,
        framework=framework,
        document_type=document_type,
        status_filter=status_filter,
        take=take,
        skip=skip,
    )
    return CavadaLabsComplianceDocumentListResponse(
        compliance_documents=documents,
        count=len(documents),
    )


@router.get(
    "/compliance-documents/{document_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsComplianceDocumentResponse,
)
@management_endpoint_wrapper
async def get_compliance_document(
    document_id: str,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsComplianceDocumentResponse:
    document = await _service().get_document(document_id)
    await _require_compliance_scope_access(
        company_id=document.company_id,
        project_id=document.project_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=False,
    )
    return document


@router.patch(
    "/compliance-documents/{document_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsComplianceDocumentResponse,
)
@management_endpoint_wrapper
async def update_compliance_document(
    document_id: str,
    data: CavadaLabsComplianceDocumentUpdateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsComplianceDocumentResponse:
    service = _service()
    current = await service.get_document(document_id)
    await _require_current_and_target_scope_access(
        current=current,
        data=data,
        user_api_key_dict=user_api_key_dict,
    )
    return await service.update_document(document_id, data, user_api_key_dict)


@router.post(
    "/compliance-evidence",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsComplianceEvidenceResponse,
)
@management_endpoint_wrapper
async def create_compliance_evidence(
    data: CavadaLabsComplianceEvidenceCreateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsComplianceEvidenceResponse:
    await _require_compliance_scope_access(
        company_id=data.company_id,
        project_id=data.project_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=True,
    )
    return await _service().create_evidence(data, user_api_key_dict)


@router.get(
    "/compliance-evidence",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsComplianceEvidenceListResponse,
)
@management_endpoint_wrapper
async def list_compliance_evidence(
    http_request: Request,
    company_id: Optional[str] = None,
    project_id: Optional[str] = None,
    framework: Optional[CavadaLabsComplianceFramework] = None,
    evidence_type: Optional[str] = None,
    status_filter: Optional[CavadaLabsComplianceStatus] = Query(
        default=None, alias="status"
    ),
    take: int = Query(default=100, ge=1, le=1000),
    skip: int = Query(default=0, ge=0),
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsComplianceEvidenceListResponse:
    scoped_company_id, scoped_company_ids, scoped_project_id, scoped_project_ids = (
        await _resolve_compliance_list_filters(
            company_id=company_id,
            project_id=project_id,
            user_api_key_dict=user_api_key_dict,
        )
    )
    evidence = await _service().list_evidence(
        company_id=scoped_company_id,
        company_ids=scoped_company_ids,
        project_id=scoped_project_id,
        project_ids=scoped_project_ids,
        framework=framework,
        evidence_type=evidence_type,
        status_filter=status_filter,
        take=take,
        skip=skip,
    )
    return CavadaLabsComplianceEvidenceListResponse(
        compliance_evidence=evidence,
        count=len(evidence),
    )


@router.get(
    "/compliance-evidence/{evidence_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsComplianceEvidenceResponse,
)
@management_endpoint_wrapper
async def get_compliance_evidence(
    evidence_id: str,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsComplianceEvidenceResponse:
    evidence = await _service().get_evidence(evidence_id)
    await _require_compliance_scope_access(
        company_id=evidence.company_id,
        project_id=evidence.project_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=False,
    )
    return evidence


@router.patch(
    "/compliance-evidence/{evidence_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsComplianceEvidenceResponse,
)
@management_endpoint_wrapper
async def update_compliance_evidence(
    evidence_id: str,
    data: CavadaLabsComplianceEvidenceUpdateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsComplianceEvidenceResponse:
    service = _service()
    current = await service.get_evidence(evidence_id)
    await _require_current_and_target_scope_access(
        current=current,
        data=data,
        user_api_key_dict=user_api_key_dict,
    )
    return await service.update_evidence(evidence_id, data, user_api_key_dict)


@router.post(
    "/processing-activities",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsProcessingActivityResponse,
)
@management_endpoint_wrapper
async def create_processing_activity(
    data: CavadaLabsProcessingActivityCreateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsProcessingActivityResponse:
    await _require_compliance_scope_access(
        company_id=data.company_id,
        project_id=data.project_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=True,
    )
    return await _service().create_processing_activity(data, user_api_key_dict)


@router.get(
    "/processing-activities",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsProcessingActivityListResponse,
)
@management_endpoint_wrapper
async def list_processing_activities(
    http_request: Request,
    company_id: Optional[str] = None,
    project_id: Optional[str] = None,
    status_filter: Optional[CavadaLabsComplianceStatus] = Query(
        default=None, alias="status"
    ),
    take: int = Query(default=100, ge=1, le=1000),
    skip: int = Query(default=0, ge=0),
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsProcessingActivityListResponse:
    scoped_company_id, scoped_company_ids, scoped_project_id, scoped_project_ids = (
        await _resolve_compliance_list_filters(
            company_id=company_id,
            project_id=project_id,
            user_api_key_dict=user_api_key_dict,
        )
    )
    activities = await _service().list_processing_activities(
        company_id=scoped_company_id,
        company_ids=scoped_company_ids,
        project_id=scoped_project_id,
        project_ids=scoped_project_ids,
        status_filter=status_filter,
        take=take,
        skip=skip,
    )
    return CavadaLabsProcessingActivityListResponse(
        processing_activities=activities,
        count=len(activities),
    )


@router.get(
    "/processing-activities/{activity_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsProcessingActivityResponse,
)
@management_endpoint_wrapper
async def get_processing_activity(
    activity_id: str,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsProcessingActivityResponse:
    activity = await _service().get_processing_activity(activity_id)
    await _require_compliance_scope_access(
        company_id=activity.company_id,
        project_id=activity.project_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=False,
    )
    return activity


@router.patch(
    "/processing-activities/{activity_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsProcessingActivityResponse,
)
@management_endpoint_wrapper
async def update_processing_activity(
    activity_id: str,
    data: CavadaLabsProcessingActivityUpdateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsProcessingActivityResponse:
    service = _service()
    current = await service.get_processing_activity(activity_id)
    await _require_current_and_target_scope_access(
        current=current,
        data=data,
        user_api_key_dict=user_api_key_dict,
    )
    return await service.update_processing_activity(
        activity_id,
        data,
        user_api_key_dict,
    )


@router.post(
    "/data-subject-requests",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsDataSubjectRequestResponse,
)
@management_endpoint_wrapper
async def create_data_subject_request(
    data: CavadaLabsDataSubjectRequestCreateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsDataSubjectRequestResponse:
    await _require_compliance_scope_access(
        company_id=data.company_id,
        project_id=data.project_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=True,
    )
    return await _service().create_data_subject_request(data, user_api_key_dict)


@router.get(
    "/data-subject-requests",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsDataSubjectRequestListResponse,
)
@management_endpoint_wrapper
async def list_data_subject_requests(
    http_request: Request,
    company_id: Optional[str] = None,
    project_id: Optional[str] = None,
    request_type: Optional[CavadaLabsDataSubjectRequestType] = None,
    status_filter: Optional[CavadaLabsDataSubjectRequestStatus] = Query(
        default=None, alias="status"
    ),
    requester_email: Optional[str] = None,
    take: int = Query(default=100, ge=1, le=1000),
    skip: int = Query(default=0, ge=0),
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsDataSubjectRequestListResponse:
    scoped_company_id, scoped_company_ids, scoped_project_id, scoped_project_ids = (
        await _resolve_compliance_list_filters(
            company_id=company_id,
            project_id=project_id,
            user_api_key_dict=user_api_key_dict,
        )
    )
    requests = await _service().list_data_subject_requests(
        company_id=scoped_company_id,
        company_ids=scoped_company_ids,
        project_id=scoped_project_id,
        project_ids=scoped_project_ids,
        request_type=request_type,
        status_filter=status_filter,
        requester_email=requester_email,
        take=take,
        skip=skip,
    )
    return CavadaLabsDataSubjectRequestListResponse(
        data_subject_requests=requests,
        count=len(requests),
    )


@router.get(
    "/data-subject-requests/{dsr_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsDataSubjectRequestResponse,
)
@management_endpoint_wrapper
async def get_data_subject_request(
    dsr_id: str,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsDataSubjectRequestResponse:
    request = await _service().get_data_subject_request(dsr_id)
    await _require_compliance_scope_access(
        company_id=request.company_id,
        project_id=request.project_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=False,
    )
    return request


@router.patch(
    "/data-subject-requests/{dsr_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsDataSubjectRequestResponse,
)
@management_endpoint_wrapper
async def update_data_subject_request(
    dsr_id: str,
    data: CavadaLabsDataSubjectRequestUpdateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsDataSubjectRequestResponse:
    service = _service()
    current = await service.get_data_subject_request(dsr_id)
    await _require_current_and_target_scope_access(
        current=current,
        data=data,
        user_api_key_dict=user_api_key_dict,
    )
    return await service.update_data_subject_request(
        dsr_id,
        data,
        user_api_key_dict,
    )


@router.post(
    "/ai-system-assessments",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsAISystemAssessmentResponse,
)
@management_endpoint_wrapper
async def create_ai_system_assessment(
    data: CavadaLabsAISystemAssessmentCreateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsAISystemAssessmentResponse:
    await _require_compliance_scope_access(
        company_id=data.company_id,
        project_id=data.project_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=True,
    )
    return await _service().create_ai_system_assessment(data, user_api_key_dict)


@router.get(
    "/ai-system-assessments",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsAISystemAssessmentListResponse,
)
@management_endpoint_wrapper
async def list_ai_system_assessments(
    http_request: Request,
    company_id: Optional[str] = None,
    project_id: Optional[str] = None,
    chatbot_id: Optional[str] = None,
    status_filter: Optional[CavadaLabsComplianceStatus] = Query(
        default=None, alias="status"
    ),
    take: int = Query(default=100, ge=1, le=1000),
    skip: int = Query(default=0, ge=0),
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsAISystemAssessmentListResponse:
    scoped_company_id, scoped_company_ids, scoped_project_id, scoped_project_ids = (
        await _resolve_compliance_list_filters(
            company_id=company_id,
            project_id=project_id,
            user_api_key_dict=user_api_key_dict,
        )
    )
    assessments = await _service().list_ai_system_assessments(
        company_id=scoped_company_id,
        company_ids=scoped_company_ids,
        project_id=scoped_project_id,
        project_ids=scoped_project_ids,
        chatbot_id=chatbot_id,
        status_filter=status_filter,
        take=take,
        skip=skip,
    )
    return CavadaLabsAISystemAssessmentListResponse(
        ai_system_assessments=assessments,
        count=len(assessments),
    )


@router.get(
    "/ai-system-assessments/{assessment_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsAISystemAssessmentResponse,
)
@management_endpoint_wrapper
async def get_ai_system_assessment(
    assessment_id: str,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsAISystemAssessmentResponse:
    assessment = await _service().get_ai_system_assessment(assessment_id)
    await _require_compliance_scope_access(
        company_id=assessment.company_id,
        project_id=assessment.project_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=False,
    )
    return assessment


@router.patch(
    "/ai-system-assessments/{assessment_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsAISystemAssessmentResponse,
)
@management_endpoint_wrapper
async def update_ai_system_assessment(
    assessment_id: str,
    data: CavadaLabsAISystemAssessmentUpdateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsAISystemAssessmentResponse:
    service = _service()
    current = await service.get_ai_system_assessment(assessment_id)
    await _require_current_and_target_scope_access(
        current=current,
        data=data,
        user_api_key_dict=user_api_key_dict,
    )
    return await service.update_ai_system_assessment(
        assessment_id,
        data,
        user_api_key_dict,
    )
