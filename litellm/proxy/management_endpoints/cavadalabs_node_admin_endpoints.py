from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.auth.user_api_key_auth import user_api_key_auth
from litellm.proxy.cavadalabs.nodes import CavadaLabsNodeService
from litellm.proxy.management_helpers.utils import management_endpoint_wrapper
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsGPULockCreateRequest,
    CavadaLabsGPULockListResponse,
    CavadaLabsGPULockResponse,
    CavadaLabsGPULockStatus,
    CavadaLabsGPUListResponse,
    CavadaLabsGPUStatus,
    CavadaLabsModelLoadRequestCreateRequest,
    CavadaLabsModelLoadRequestListResponse,
    CavadaLabsModelLoadRequestResponse,
    CavadaLabsModelLoadRequestUpdateRequest,
    CavadaLabsModelRuntimeStatus,
    CavadaLabsNodeCreateRequest,
    CavadaLabsNodeEnrollmentCreateRequest,
    CavadaLabsNodeEnrollmentCreateResponse,
    CavadaLabsNodeListResponse,
    CavadaLabsNodeResponse,
    CavadaLabsNodeStatus,
    CavadaLabsNodeUpdateRequest,
    CavadaLabsSchedulerRunRequest,
    CavadaLabsSchedulerRunResponse,
)

router = APIRouter(prefix="/cavadalabs", tags=["cavadalabs-node-admin"])


def _require_proxy_admin(user_api_key_dict: UserAPIKeyAuth) -> None:
    if user_api_key_dict.user_role != LitellmUserRoles.PROXY_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "CavadaLabs node admin mutations require proxy_admin"},
        )


def _require_admin_view(user_api_key_dict: UserAPIKeyAuth) -> None:
    if user_api_key_dict.user_role not in {
        LitellmUserRoles.PROXY_ADMIN,
        LitellmUserRoles.PROXY_ADMIN_VIEW_ONLY,
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "CavadaLabs node admin access requires admin view"},
        )


def _service() -> CavadaLabsNodeService:
    from litellm.proxy import proxy_server

    if proxy_server.prisma_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Database is required for CavadaLabs node admin"},
        )
    return CavadaLabsNodeService(proxy_server.prisma_client)


@router.post(
    "/nodes",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsNodeResponse,
)
@management_endpoint_wrapper
async def create_node(
    data: CavadaLabsNodeCreateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsNodeResponse:
    _require_proxy_admin(user_api_key_dict)
    return await _service().create_node(data, user_api_key_dict)


@router.get(
    "/nodes",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsNodeListResponse,
)
@management_endpoint_wrapper
async def list_nodes(
    http_request: Request,
    status_filter: Optional[CavadaLabsNodeStatus] = Query(default=None, alias="status"),
    location: Optional[str] = None,
    take: int = Query(default=100, ge=1, le=1000),
    skip: int = Query(default=0, ge=0),
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsNodeListResponse:
    _require_admin_view(user_api_key_dict)
    return await _service().list_nodes(
        status_filter=status_filter,
        location=location,
        take=take,
        skip=skip,
    )


@router.get(
    "/nodes/{node_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsNodeResponse,
)
@management_endpoint_wrapper
async def get_node(
    node_id: str,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsNodeResponse:
    _require_admin_view(user_api_key_dict)
    return await _service().get_node(node_id)


@router.patch(
    "/nodes/{node_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsNodeResponse,
)
@management_endpoint_wrapper
async def update_node(
    node_id: str,
    data: CavadaLabsNodeUpdateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsNodeResponse:
    _require_proxy_admin(user_api_key_dict)
    return await _service().update_node(node_id, data, user_api_key_dict)


@router.delete(
    "/nodes/{node_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsNodeResponse,
)
@management_endpoint_wrapper
async def disable_node(
    node_id: str,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsNodeResponse:
    _require_proxy_admin(user_api_key_dict)
    return await _service().disable_node(node_id, user_api_key_dict)


@router.post(
    "/nodes/{node_id}/enrollment-secrets",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsNodeEnrollmentCreateResponse,
)
@management_endpoint_wrapper
async def create_node_enrollment_secret(
    node_id: str,
    data: CavadaLabsNodeEnrollmentCreateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsNodeEnrollmentCreateResponse:
    _require_proxy_admin(user_api_key_dict)
    return await _service().create_enrollment_secret(node_id, data, user_api_key_dict)


@router.get(
    "/nodes/{node_id}/gpus",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsGPUListResponse,
)
@management_endpoint_wrapper
async def list_node_gpus(
    node_id: str,
    http_request: Request,
    status_filter: Optional[CavadaLabsGPUStatus] = Query(default=None, alias="status"),
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsGPUListResponse:
    _require_admin_view(user_api_key_dict)
    return await _service().list_gpus(
        node_id=node_id,
        status_filter=status_filter,
    )


@router.post(
    "/model-load-requests",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsModelLoadRequestResponse,
)
@management_endpoint_wrapper
async def create_model_load_request(
    data: CavadaLabsModelLoadRequestCreateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsModelLoadRequestResponse:
    _require_proxy_admin(user_api_key_dict)
    return await _service().create_model_load_request(data, user_api_key_dict)


@router.get(
    "/model-load-requests",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsModelLoadRequestListResponse,
)
@management_endpoint_wrapper
async def list_model_load_requests(
    http_request: Request,
    project_id: Optional[str] = None,
    node_id: Optional[str] = None,
    status_filter: Optional[CavadaLabsModelRuntimeStatus] = Query(
        default=None, alias="status"
    ),
    take: int = Query(default=100, ge=1, le=1000),
    skip: int = Query(default=0, ge=0),
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsModelLoadRequestListResponse:
    _require_admin_view(user_api_key_dict)
    return await _service().list_model_load_requests(
        project_id=project_id,
        node_id=node_id,
        status_filter=status_filter,
        take=take,
        skip=skip,
    )


@router.patch(
    "/model-load-requests/{model_load_request_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsModelLoadRequestResponse,
)
@management_endpoint_wrapper
async def update_model_load_request(
    model_load_request_id: str,
    data: CavadaLabsModelLoadRequestUpdateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsModelLoadRequestResponse:
    _require_proxy_admin(user_api_key_dict)
    return await _service().update_model_load_request(
        model_load_request_id,
        data,
        user_api_key_dict,
    )


@router.post(
    "/model-load-requests/schedule",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsSchedulerRunResponse,
)
@management_endpoint_wrapper
async def schedule_model_load_requests(
    data: CavadaLabsSchedulerRunRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsSchedulerRunResponse:
    _require_proxy_admin(user_api_key_dict)
    return await _service().schedule_model_load_requests(
        data,
        user_api_key_dict,
    )


@router.post(
    "/gpu-locks",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsGPULockResponse,
)
@management_endpoint_wrapper
async def create_gpu_lock(
    data: CavadaLabsGPULockCreateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsGPULockResponse:
    _require_proxy_admin(user_api_key_dict)
    return await _service().create_gpu_lock(data, user_api_key_dict)


@router.get(
    "/gpu-locks",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsGPULockListResponse,
)
@management_endpoint_wrapper
async def list_gpu_locks(
    http_request: Request,
    project_id: Optional[str] = None,
    node_id: Optional[str] = None,
    status_filter: Optional[CavadaLabsGPULockStatus] = Query(
        default=None, alias="status"
    ),
    take: int = Query(default=100, ge=1, le=1000),
    skip: int = Query(default=0, ge=0),
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsGPULockListResponse:
    _require_admin_view(user_api_key_dict)
    return await _service().list_gpu_locks(
        project_id=project_id,
        node_id=node_id,
        status_filter=status_filter,
        take=take,
        skip=skip,
    )


@router.post(
    "/gpu-locks/{lock_id}/release",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsGPULockResponse,
)
@management_endpoint_wrapper
async def release_gpu_lock(
    lock_id: str,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsGPULockResponse:
    _require_proxy_admin(user_api_key_dict)
    return await _service().release_gpu_lock(lock_id, user_api_key_dict)
