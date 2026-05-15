from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.auth.user_api_key_auth import user_api_key_auth
from litellm.proxy.management_endpoints.cavadalabs_dispatcher_utils import (
    dispatcher_service,
    require_admin_view,
    require_proxy_admin,
)
from litellm.proxy.management_helpers.utils import management_endpoint_wrapper
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsProjectCreateRequest,
    CavadaLabsProjectListResponse,
    CavadaLabsProjectResponse,
    CavadaLabsProjectStatus,
    CavadaLabsProjectUpdateRequest,
)

router = APIRouter(tags=["cavadalabs-projects"])


@router.post(
    "/projects",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsProjectResponse,
)
@management_endpoint_wrapper
async def create_project(
    data: CavadaLabsProjectCreateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsProjectResponse:
    require_proxy_admin(user_api_key_dict)
    return await dispatcher_service().create_project(data, user_api_key_dict)


@router.get(
    "/projects",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsProjectListResponse,
)
@management_endpoint_wrapper
async def list_projects(
    http_request: Request,
    company_id: Optional[str] = None,
    status_filter: Optional[CavadaLabsProjectStatus] = Query(
        default=None, alias="status"
    ),
    take: int = Query(default=100, ge=1, le=1000),
    skip: int = Query(default=0, ge=0),
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsProjectListResponse:
    require_admin_view(user_api_key_dict)
    projects = await dispatcher_service().list_projects(
        company_id=company_id,
        status_filter=status_filter,
        take=take,
        skip=skip,
    )
    return CavadaLabsProjectListResponse(projects=projects, count=len(projects))


@router.get(
    "/projects/{project_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsProjectResponse,
)
@management_endpoint_wrapper
async def get_project(
    project_id: str,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsProjectResponse:
    require_admin_view(user_api_key_dict)
    return await dispatcher_service().get_project(project_id)


@router.patch(
    "/projects/{project_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsProjectResponse,
)
@management_endpoint_wrapper
async def update_project(
    project_id: str,
    data: CavadaLabsProjectUpdateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsProjectResponse:
    require_proxy_admin(user_api_key_dict)
    return await dispatcher_service().update_project(
        project_id, data, user_api_key_dict
    )


@router.delete(
    "/projects/{project_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsProjectResponse,
)
@management_endpoint_wrapper
async def archive_project(
    project_id: str,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsProjectResponse:
    require_proxy_admin(user_api_key_dict)
    return await dispatcher_service().update_project(
        project_id,
        CavadaLabsProjectUpdateRequest(status=CavadaLabsProjectStatus.ARCHIVED),
        user_api_key_dict,
    )
