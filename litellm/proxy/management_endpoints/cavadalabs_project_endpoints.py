from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.auth.user_api_key_auth import user_api_key_auth
from litellm.proxy.cavadalabs.access_control import (
    require_company_access,
    require_project_access,
    resolve_cavadalabs_project_usage_scope,
    visible_project_ids_for_user,
)
from litellm.proxy.cavadalabs.usage import get_cavadalabs_daily_activity
from litellm.proxy.management_endpoints.cavadalabs_dispatcher_utils import (
    dispatcher_service,
)
from litellm.proxy.management_helpers.utils import management_endpoint_wrapper
from litellm.types.proxy.management_endpoints.common_daily_activity import (
    SpendAnalyticsPaginatedResponse,
)
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsProjectCreateRequest,
    CavadaLabsProjectListResponse,
    CavadaLabsProjectResponse,
    CavadaLabsProjectStatus,
    CavadaLabsProjectUpdateRequest,
)

router = APIRouter(tags=["cavadalabs-projects"])


def _split_csv(value: Optional[str]) -> Optional[list[str]]:
    if value is None:
        return None
    values = [item.strip() for item in value.split(",") if item.strip()]
    return values or None


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
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Database is required for CavadaLabs dispatcher"},
        )
    await require_company_access(
        prisma_client.db,
        company_id=data.company_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=True,
    )
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
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Database is required for CavadaLabs dispatcher"},
        )
    visible_project_ids = await visible_project_ids_for_user(
        prisma_client.db,
        user_api_key_dict,
        company_id=company_id,
    )
    projects = await dispatcher_service().list_projects(
        company_id=company_id,
        project_ids=(
            list(visible_project_ids) if visible_project_ids is not None else None
        ),
        status_filter=status_filter,
        take=take,
        skip=skip,
    )
    return CavadaLabsProjectListResponse(projects=projects, count=len(projects))


@router.get(
    "/projects/daily/activity",
    dependencies=[Depends(user_api_key_auth)],
    response_model=SpendAnalyticsPaginatedResponse,
)
@management_endpoint_wrapper
async def get_project_daily_activity(
    http_request: Request,
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    model: Optional[str] = Query(default=None),
    api_key: Optional[str] = Query(default=None),
    project_ids: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000),
    timezone: Optional[int] = Query(default=None),
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> SpendAnalyticsPaginatedResponse:
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Database is required for CavadaLabs dispatcher"},
        )
    entity_ids = await resolve_cavadalabs_project_usage_scope(
        prisma_client.db,
        user_api_key_dict=user_api_key_dict,
        requested_project_ids=project_ids,
    )
    return await get_cavadalabs_daily_activity(
        prisma_client=prisma_client,
        entity_id_field="project_id",
        entity_id=entity_ids,
        start_date=start_date,
        end_date=end_date,
        model=model,
        api_key=api_key,
        page=page,
        page_size=page_size,
        timezone_offset_minutes=timezone,
    )


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
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Database is required for CavadaLabs dispatcher"},
        )
    await require_project_access(
        prisma_client.db,
        project_id=project_id,
        user_api_key_dict=user_api_key_dict,
    )
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
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Database is required for CavadaLabs dispatcher"},
        )
    await require_project_access(
        prisma_client.db,
        project_id=project_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=True,
    )
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
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Database is required for CavadaLabs dispatcher"},
        )
    await require_project_access(
        prisma_client.db,
        project_id=project_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=True,
    )
    return await dispatcher_service().update_project(
        project_id,
        CavadaLabsProjectUpdateRequest(status=CavadaLabsProjectStatus.ARCHIVED),
        user_api_key_dict,
    )
