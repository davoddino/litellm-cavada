from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.auth.user_api_key_auth import user_api_key_auth
from litellm.proxy.cavadalabs.rag import CavadaLabsRAGService
from litellm.proxy.management_helpers.utils import management_endpoint_wrapper
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsChatbotRAGAssignmentCreateRequest,
    CavadaLabsChatbotRAGAssignmentListResponse,
    CavadaLabsChatbotRAGAssignmentResponse,
    CavadaLabsChatbotRAGAssignmentUpdateRequest,
    CavadaLabsRAGAssignmentStatus,
    CavadaLabsRAGCollectionCreateRequest,
    CavadaLabsRAGCollectionListResponse,
    CavadaLabsRAGCollectionResponse,
    CavadaLabsRAGCollectionScope,
    CavadaLabsRAGCollectionStatus,
    CavadaLabsRAGCollectionUpdateRequest,
    CavadaLabsRAGDocumentCreateRequest,
    CavadaLabsRAGDocumentListResponse,
    CavadaLabsRAGDocumentResponse,
    CavadaLabsRAGDocumentStatus,
    CavadaLabsRAGDocumentUpdateRequest,
)

router = APIRouter(prefix="/cavadalabs", tags=["cavadalabs-rag"])


def _require_proxy_admin(user_api_key_dict: UserAPIKeyAuth) -> None:
    if user_api_key_dict.user_role != LitellmUserRoles.PROXY_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "CavadaLabs RAG mutations require proxy_admin"},
        )


def _require_admin_view(user_api_key_dict: UserAPIKeyAuth) -> None:
    if user_api_key_dict.user_role not in {
        LitellmUserRoles.PROXY_ADMIN,
        LitellmUserRoles.PROXY_ADMIN_VIEW_ONLY,
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "CavadaLabs RAG access requires admin view"},
        )


def _service() -> CavadaLabsRAGService:
    from litellm.proxy import proxy_server

    if proxy_server.prisma_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Database is required for CavadaLabs RAG"},
        )
    return CavadaLabsRAGService(proxy_server.prisma_client)


@router.post(
    "/rag-collections",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsRAGCollectionResponse,
)
@management_endpoint_wrapper
async def create_rag_collection(
    data: CavadaLabsRAGCollectionCreateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsRAGCollectionResponse:
    _require_proxy_admin(user_api_key_dict)
    return await _service().create_collection(data, user_api_key_dict)


@router.get(
    "/rag-collections",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsRAGCollectionListResponse,
)
@management_endpoint_wrapper
async def list_rag_collections(
    http_request: Request,
    company_id: Optional[str] = None,
    project_id: Optional[str] = None,
    status_filter: Optional[CavadaLabsRAGCollectionStatus] = Query(
        default=None, alias="status"
    ),
    scope_filter: Optional[CavadaLabsRAGCollectionScope] = Query(
        default=None, alias="scope"
    ),
    take: int = Query(default=100, ge=1, le=1000),
    skip: int = Query(default=0, ge=0),
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsRAGCollectionListResponse:
    _require_admin_view(user_api_key_dict)
    rag_collections = await _service().list_collections(
        company_id=company_id,
        project_id=project_id,
        status_filter=status_filter,
        scope_filter=scope_filter,
        take=take,
        skip=skip,
    )
    return CavadaLabsRAGCollectionListResponse(
        rag_collections=rag_collections,
        count=len(rag_collections),
    )


@router.get(
    "/rag-collections/{collection_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsRAGCollectionResponse,
)
@management_endpoint_wrapper
async def get_rag_collection(
    collection_id: str,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsRAGCollectionResponse:
    _require_admin_view(user_api_key_dict)
    return await _service().get_collection(collection_id)


@router.patch(
    "/rag-collections/{collection_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsRAGCollectionResponse,
)
@management_endpoint_wrapper
async def update_rag_collection(
    collection_id: str,
    data: CavadaLabsRAGCollectionUpdateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsRAGCollectionResponse:
    _require_proxy_admin(user_api_key_dict)
    return await _service().update_collection(
        collection_id,
        data,
        user_api_key_dict,
    )


@router.delete(
    "/rag-collections/{collection_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsRAGCollectionResponse,
)
@management_endpoint_wrapper
async def archive_rag_collection(
    collection_id: str,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsRAGCollectionResponse:
    _require_proxy_admin(user_api_key_dict)
    return await _service().archive_collection(collection_id, user_api_key_dict)


@router.post(
    "/rag-documents",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsRAGDocumentResponse,
)
@management_endpoint_wrapper
async def create_rag_document(
    data: CavadaLabsRAGDocumentCreateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsRAGDocumentResponse:
    _require_proxy_admin(user_api_key_dict)
    return await _service().create_document(data, user_api_key_dict)


@router.get(
    "/rag-documents",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsRAGDocumentListResponse,
)
@management_endpoint_wrapper
async def list_rag_documents(
    http_request: Request,
    collection_id: Optional[str] = None,
    company_id: Optional[str] = None,
    project_id: Optional[str] = None,
    status_filter: Optional[CavadaLabsRAGDocumentStatus] = Query(
        default=None, alias="status"
    ),
    take: int = Query(default=100, ge=1, le=1000),
    skip: int = Query(default=0, ge=0),
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsRAGDocumentListResponse:
    _require_admin_view(user_api_key_dict)
    rag_documents = await _service().list_documents(
        collection_id=collection_id,
        company_id=company_id,
        project_id=project_id,
        status_filter=status_filter,
        take=take,
        skip=skip,
    )
    return CavadaLabsRAGDocumentListResponse(
        rag_documents=rag_documents,
        count=len(rag_documents),
    )


@router.patch(
    "/rag-documents/{document_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsRAGDocumentResponse,
)
@management_endpoint_wrapper
async def update_rag_document(
    document_id: str,
    data: CavadaLabsRAGDocumentUpdateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsRAGDocumentResponse:
    _require_proxy_admin(user_api_key_dict)
    return await _service().update_document(
        document_id,
        data,
        user_api_key_dict,
    )


@router.post(
    "/rag-assignments",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsChatbotRAGAssignmentResponse,
)
@management_endpoint_wrapper
async def create_rag_assignment(
    data: CavadaLabsChatbotRAGAssignmentCreateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsChatbotRAGAssignmentResponse:
    _require_proxy_admin(user_api_key_dict)
    return await _service().create_assignment(data, user_api_key_dict)


@router.get(
    "/rag-assignments",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsChatbotRAGAssignmentListResponse,
)
@management_endpoint_wrapper
async def list_rag_assignments(
    http_request: Request,
    company_id: Optional[str] = None,
    project_id: Optional[str] = None,
    chatbot_id: Optional[str] = None,
    collection_id: Optional[str] = None,
    status_filter: Optional[CavadaLabsRAGAssignmentStatus] = Query(
        default=None, alias="status"
    ),
    take: int = Query(default=100, ge=1, le=1000),
    skip: int = Query(default=0, ge=0),
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsChatbotRAGAssignmentListResponse:
    _require_admin_view(user_api_key_dict)
    rag_assignments = await _service().list_assignments(
        company_id=company_id,
        project_id=project_id,
        chatbot_id=chatbot_id,
        collection_id=collection_id,
        status_filter=status_filter,
        take=take,
        skip=skip,
    )
    return CavadaLabsChatbotRAGAssignmentListResponse(
        rag_assignments=rag_assignments,
        count=len(rag_assignments),
    )


@router.patch(
    "/rag-assignments/{assignment_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsChatbotRAGAssignmentResponse,
)
@management_endpoint_wrapper
async def update_rag_assignment(
    assignment_id: str,
    data: CavadaLabsChatbotRAGAssignmentUpdateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsChatbotRAGAssignmentResponse:
    _require_proxy_admin(user_api_key_dict)
    return await _service().update_assignment(
        assignment_id,
        data,
        user_api_key_dict,
    )


@router.delete(
    "/rag-assignments/{assignment_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsChatbotRAGAssignmentResponse,
)
@management_endpoint_wrapper
async def disable_rag_assignment(
    assignment_id: str,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsChatbotRAGAssignmentResponse:
    _require_proxy_admin(user_api_key_dict)
    return await _service().disable_assignment(assignment_id, user_api_key_dict)
