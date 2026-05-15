from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.auth.user_api_key_auth import user_api_key_auth
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


def _require_proxy_admin(user_api_key_dict: UserAPIKeyAuth) -> None:
    if user_api_key_dict.user_role != LitellmUserRoles.PROXY_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "CavadaLabs compliance mutations require proxy_admin"},
        )


def _require_admin_view(user_api_key_dict: UserAPIKeyAuth) -> None:
    if user_api_key_dict.user_role not in {
        LitellmUserRoles.PROXY_ADMIN,
        LitellmUserRoles.PROXY_ADMIN_VIEW_ONLY,
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "CavadaLabs compliance access requires admin view"},
        )


def _service() -> CavadaLabsComplianceService:
    from litellm.proxy import proxy_server

    if proxy_server.prisma_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Database is required for CavadaLabs compliance"},
        )
    return CavadaLabsComplianceService(proxy_server.prisma_client)


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
    _require_proxy_admin(user_api_key_dict)
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
    _require_admin_view(user_api_key_dict)
    documents = await _service().list_documents(
        company_id=company_id,
        project_id=project_id,
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
    _require_admin_view(user_api_key_dict)
    return await _service().get_document(document_id)


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
    _require_proxy_admin(user_api_key_dict)
    return await _service().update_document(document_id, data, user_api_key_dict)


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
    _require_proxy_admin(user_api_key_dict)
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
    _require_admin_view(user_api_key_dict)
    evidence = await _service().list_evidence(
        company_id=company_id,
        project_id=project_id,
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
    _require_admin_view(user_api_key_dict)
    return await _service().get_evidence(evidence_id)


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
    _require_proxy_admin(user_api_key_dict)
    return await _service().update_evidence(evidence_id, data, user_api_key_dict)


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
    _require_proxy_admin(user_api_key_dict)
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
    _require_admin_view(user_api_key_dict)
    activities = await _service().list_processing_activities(
        company_id=company_id,
        project_id=project_id,
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
    _require_admin_view(user_api_key_dict)
    return await _service().get_processing_activity(activity_id)


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
    _require_proxy_admin(user_api_key_dict)
    return await _service().update_processing_activity(
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
    _require_proxy_admin(user_api_key_dict)
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
    _require_admin_view(user_api_key_dict)
    requests = await _service().list_data_subject_requests(
        company_id=company_id,
        project_id=project_id,
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
    _require_admin_view(user_api_key_dict)
    return await _service().get_data_subject_request(dsr_id)


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
    _require_proxy_admin(user_api_key_dict)
    return await _service().update_data_subject_request(
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
    _require_proxy_admin(user_api_key_dict)
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
    _require_admin_view(user_api_key_dict)
    assessments = await _service().list_ai_system_assessments(
        company_id=company_id,
        project_id=project_id,
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
    _require_admin_view(user_api_key_dict)
    return await _service().get_ai_system_assessment(assessment_id)


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
    _require_proxy_admin(user_api_key_dict)
    return await _service().update_ai_system_assessment(
        assessment_id,
        data,
        user_api_key_dict,
    )
