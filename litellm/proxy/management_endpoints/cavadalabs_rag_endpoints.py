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
from litellm.proxy.cavadalabs.chatbot_scope import require_chatbot_project_access
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


def _prisma_client():
    from litellm.proxy import proxy_server

    if proxy_server.prisma_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Database is required for CavadaLabs RAG"},
        )
    return proxy_server.prisma_client


def _service() -> CavadaLabsRAGService:
    return CavadaLabsRAGService(_prisma_client())


def _scope_value(scope: object) -> str:
    value = getattr(scope, "value", scope)
    return str(value)


async def _require_project_company_match(
    *,
    project_id: str,
    company_id: str,
    user_api_key_dict: UserAPIKeyAuth,
    require_admin: bool,
) -> None:
    project = await require_project_access(
        _prisma_client().db,
        project_id=project_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=require_admin,
    )
    if project.company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "project_id must belong to company_id"},
        )


async def _require_collection_scope_access(
    collection: CavadaLabsRAGCollectionResponse,
    user_api_key_dict: UserAPIKeyAuth,
    *,
    require_admin: bool,
) -> None:
    if collection.project_id is not None:
        await _require_project_company_match(
            project_id=collection.project_id,
            company_id=collection.company_id,
            user_api_key_dict=user_api_key_dict,
            require_admin=require_admin,
        )
        return
    await require_company_wide_access(
        _prisma_client().db,
        company_id=collection.company_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=require_admin,
    )


async def _require_document_scope_access(
    document: CavadaLabsRAGDocumentResponse,
    user_api_key_dict: UserAPIKeyAuth,
    *,
    require_admin: bool,
) -> None:
    if document.project_id is not None:
        await _require_project_company_match(
            project_id=document.project_id,
            company_id=document.company_id,
            user_api_key_dict=user_api_key_dict,
            require_admin=require_admin,
        )
        return
    await require_company_wide_access(
        _prisma_client().db,
        company_id=document.company_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=require_admin,
    )


async def _require_collection_create_access(
    data: CavadaLabsRAGCollectionCreateRequest,
    user_api_key_dict: UserAPIKeyAuth,
) -> None:
    if (
        data.project_id is not None
        or _scope_value(data.scope) == CavadaLabsRAGCollectionScope.PROJECT.value
    ):
        if data.project_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "project-scoped RAG collections require project_id"},
            )
        await _require_project_company_match(
            project_id=data.project_id,
            company_id=data.company_id,
            user_api_key_dict=user_api_key_dict,
            require_admin=True,
        )
        return
    await require_company_wide_access(
        _prisma_client().db,
        company_id=data.company_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=True,
    )


async def _resolve_rag_list_filters(
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
    await _require_collection_create_access(data, user_api_key_dict)
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
    scoped_company_id, scoped_company_ids, scoped_project_id, scoped_project_ids = (
        await _resolve_rag_list_filters(
            company_id=company_id,
            project_id=project_id,
            user_api_key_dict=user_api_key_dict,
        )
    )
    rag_collections = await _service().list_collections(
        company_id=scoped_company_id,
        company_ids=scoped_company_ids,
        project_id=scoped_project_id,
        project_ids=scoped_project_ids,
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
    collection = await _service().get_collection(collection_id)
    await _require_collection_scope_access(
        collection,
        user_api_key_dict,
        require_admin=False,
    )
    return collection


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
    service = _service()
    collection = await service.get_collection(collection_id)
    await _require_collection_scope_access(
        collection,
        user_api_key_dict,
        require_admin=True,
    )
    next_scope = data.scope if "scope" in data.model_fields_set else collection.scope
    next_project_id = (
        data.project_id
        if "project_id" in data.model_fields_set
        else collection.project_id
    )
    if _scope_value(next_scope) == CavadaLabsRAGCollectionScope.PROJECT.value:
        if next_project_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "project-scoped RAG collections require project_id"},
            )
        await _require_project_company_match(
            project_id=next_project_id,
            company_id=collection.company_id,
            user_api_key_dict=user_api_key_dict,
            require_admin=True,
        )
    else:
        if next_project_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "company-scoped RAG collections must not set project_id"
                },
            )
        await require_company_wide_access(
            _prisma_client().db,
            company_id=collection.company_id,
            user_api_key_dict=user_api_key_dict,
            require_admin=True,
        )
    return await service.update_collection(
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
    service = _service()
    collection = await service.get_collection(collection_id)
    await _require_collection_scope_access(
        collection,
        user_api_key_dict,
        require_admin=True,
    )
    return await service.archive_collection(collection_id, user_api_key_dict)


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
    service = _service()
    collection = await service.get_collection(data.collection_id)
    await _require_collection_scope_access(
        collection,
        user_api_key_dict,
        require_admin=True,
    )
    return await service.create_document(data, user_api_key_dict)


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
    service = _service()
    scoped_company_id = company_id
    scoped_company_ids = None
    scoped_project_id = project_id
    scoped_project_ids = None
    if collection_id is not None:
        collection = await service.get_collection(collection_id)
        await _require_collection_scope_access(
            collection,
            user_api_key_dict,
            require_admin=False,
        )
        if company_id is not None and collection.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "collection_id must belong to company_id"},
            )
        if project_id is not None and collection.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "collection_id must belong to project_id"},
            )
    else:
        scoped_company_id, scoped_company_ids, scoped_project_id, scoped_project_ids = (
            await _resolve_rag_list_filters(
                company_id=company_id,
                project_id=project_id,
                user_api_key_dict=user_api_key_dict,
            )
        )
    rag_documents = await _service().list_documents(
        collection_id=collection_id,
        company_id=scoped_company_id,
        company_ids=scoped_company_ids,
        project_id=scoped_project_id,
        project_ids=scoped_project_ids,
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
    service = _service()
    document = await service.get_document(document_id)
    await _require_document_scope_access(
        document,
        user_api_key_dict,
        require_admin=True,
    )
    return await service.update_document(
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
    service = _service()
    collection = await service.get_collection(data.collection_id)
    await _require_collection_scope_access(
        collection,
        user_api_key_dict,
        require_admin=False,
    )
    await require_chatbot_project_access(
        _prisma_client().db,
        chatbot_id=data.chatbot_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=True,
    )
    return await service.create_assignment(data, user_api_key_dict)


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
    service = _service()
    scoped_company_id = company_id
    scoped_company_ids = None
    scoped_project_id = project_id
    scoped_project_ids = None
    if chatbot_id is not None:
        chatbot = await require_chatbot_project_access(
            _prisma_client().db,
            chatbot_id=chatbot_id,
            user_api_key_dict=user_api_key_dict,
            require_admin=False,
        )
        if company_id is not None and chatbot.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "chatbot_id must belong to company_id"},
            )
        if project_id is not None and chatbot.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "chatbot_id must belong to project_id"},
            )
    elif collection_id is not None and company_id is None and project_id is None:
        collection = await service.get_collection(collection_id)
        await _require_collection_scope_access(
            collection,
            user_api_key_dict,
            require_admin=False,
        )
        if collection.project_id is not None:
            scoped_company_id = None
            scoped_project_id = collection.project_id
        else:
            scoped_company_id = collection.company_id
            scoped_project_id = None
    else:
        scoped_company_id, scoped_company_ids, scoped_project_id, scoped_project_ids = (
            await _resolve_rag_list_filters(
                company_id=company_id,
                project_id=project_id,
                user_api_key_dict=user_api_key_dict,
            )
        )
    rag_assignments = await _service().list_assignments(
        company_id=scoped_company_id,
        company_ids=scoped_company_ids,
        project_id=scoped_project_id,
        project_ids=scoped_project_ids,
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
    service = _service()
    assignment = await service.get_assignment(assignment_id)
    await _require_project_company_match(
        project_id=assignment.project_id,
        company_id=assignment.company_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=True,
    )
    return await service.update_assignment(
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
    service = _service()
    assignment = await service.get_assignment(assignment_id)
    await _require_project_company_match(
        project_id=assignment.project_id,
        company_id=assignment.company_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=True,
    )
    return await service.disable_assignment(assignment_id, user_api_key_dict)
