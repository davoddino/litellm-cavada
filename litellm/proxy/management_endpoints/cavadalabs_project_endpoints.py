from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.auth.user_api_key_auth import user_api_key_auth
from litellm.proxy.cavadalabs.access_control import (
    require_company_access,
    require_project_access,
    require_project_admin_access,
    resolve_cavadalabs_project_usage_scope,
    visible_project_ids_for_user,
    with_project_access_metadata,
)
from litellm.proxy.cavadalabs.usage import (
    get_cavadalabs_daily_activity,
    get_cavadalabs_usage_diagnostics,
    repair_cavadalabs_usage_scope,
)
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
    CavadaLabsProjectMemberCreateRequest,
    CavadaLabsProjectMemberDeleteResponse,
    CavadaLabsProjectMemberListResponse,
    CavadaLabsProjectMemberResponse,
    CavadaLabsProjectMemberUpdateRequest,
    CavadaLabsProjectResponse,
    CavadaLabsProjectStatus,
    CavadaLabsProjectUpdateRequest,
    CavadaLabsUsageDiagnosticsResponse,
    CavadaLabsUsageRepairRequest,
    CavadaLabsUsageRepairResponse,
)

router = APIRouter(tags=["cavadalabs-projects"])


def _split_csv(value: Optional[str]) -> Optional[list[str]]:
    if value is None:
        return None
    values = [item.strip() for item in value.split(",") if item.strip()]
    return values or None


def _normalize_id_list(values: Optional[list[str]]) -> list[str]:
    if values is None:
        return []
    return [item.strip() for item in values if isinstance(item, str) and item.strip()]


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
    projects = [
        await with_project_access_metadata(
            prisma_client.db,
            project=project,
            user_api_key_dict=user_api_key_dict,
        )
        for project in projects
    ]
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
    provider: Optional[str] = Query(default=None),
    status_filter: Annotated[Optional[str], Query(alias="status")] = None,
    api_key: Optional[str] = Query(default=None),
    min_spend: Annotated[Optional[float], Query(ge=0)] = None,
    max_spend: Annotated[Optional[float], Query(ge=0)] = None,
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
        provider=provider,
        status_filter=status_filter,
        api_key=api_key,
        min_spend=min_spend,
        max_spend=max_spend,
        page=page,
        page_size=page_size,
        timezone_offset_minutes=timezone,
    )


@router.get(
    "/projects/usage/diagnostics",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsUsageDiagnosticsResponse,
)
@management_endpoint_wrapper
async def get_project_usage_diagnostics(
    http_request: Request,
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    project_ids: Optional[str] = Query(default=None),
    model: Optional[str] = Query(default=None),
    provider: Optional[str] = Query(default=None),
    status_filter: Annotated[Optional[str], Query(alias="status")] = None,
    api_key: Optional[str] = Query(default=None),
    min_spend: Annotated[Optional[float], Query(ge=0)] = None,
    max_spend: Annotated[Optional[float], Query(ge=0)] = None,
    timezone: Optional[int] = Query(default=None),
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsUsageDiagnosticsResponse:
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Database is required for CavadaLabs dispatcher"},
        )
    if _split_csv(project_ids) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Select at least one Project for usage diagnostics"},
        )
    entity_ids = await resolve_cavadalabs_project_usage_scope(
        prisma_client.db,
        user_api_key_dict=user_api_key_dict,
        requested_project_ids=project_ids,
    )
    return await get_cavadalabs_usage_diagnostics(
        prisma_client=prisma_client,
        entity_type="project",
        entity_id=entity_ids,
        start_date=start_date,
        end_date=end_date,
        timezone_offset_minutes=timezone,
        model=model,
        provider=provider,
        api_key=api_key,
        status_filter=status_filter,
        min_spend=min_spend,
        max_spend=max_spend,
    )


@router.post(
    "/projects/usage/repair",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsUsageRepairResponse,
)
@management_endpoint_wrapper
async def repair_project_usage(
    data: CavadaLabsUsageRepairRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsUsageRepairResponse:
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Database is required for CavadaLabs dispatcher"},
        )
    project_ids = _normalize_id_list(data.project_ids)
    if not project_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Select at least one Project for usage repair"},
        )
    entity_ids = await resolve_cavadalabs_project_usage_scope(
        prisma_client.db,
        user_api_key_dict=user_api_key_dict,
        requested_project_ids=",".join(project_ids),
    )
    if not entity_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "You do not have access to any requested Projects"},
        )
    for project_id in entity_ids:
        await require_project_admin_access(
            prisma_client.db,
            project_id=project_id,
            user_api_key_dict=user_api_key_dict,
        )
    return await repair_cavadalabs_usage_scope(
        prisma_client=prisma_client,
        entity_type="project",
        entity_id=entity_ids,
        start_date=data.start_date,
        end_date=data.end_date,
        timezone_offset_minutes=data.timezone,
        model=data.model,
        provider=data.provider,
        api_key=data.api_key,
        status_filter=data.status,
        min_spend=data.min_spend,
        max_spend=data.max_spend,
        dry_run=data.dry_run,
        batch_limit=data.batch_limit,
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
    project = await dispatcher_service().get_project(project_id)
    return await with_project_access_metadata(
        prisma_client.db,
        project=project,
        user_api_key_dict=user_api_key_dict,
    )


@router.get(
    "/projects/{project_id}/members",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsProjectMemberListResponse,
)
@management_endpoint_wrapper
async def list_project_members(
    project_id: str,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsProjectMemberListResponse:
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
    return await dispatcher_service().list_project_members(project_id)


@router.post(
    "/projects/{project_id}/members",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsProjectMemberResponse,
)
@management_endpoint_wrapper
async def upsert_project_member(
    project_id: str,
    data: CavadaLabsProjectMemberCreateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsProjectMemberResponse:
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
    return await dispatcher_service().upsert_project_member(
        project_id, data, user_api_key_dict
    )


@router.patch(
    "/projects/{project_id}/members/{user_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsProjectMemberResponse,
)
@management_endpoint_wrapper
async def update_project_member(
    project_id: str,
    user_id: str,
    data: CavadaLabsProjectMemberUpdateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsProjectMemberResponse:
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
    return await dispatcher_service().update_project_member(
        project_id, user_id, data, user_api_key_dict
    )


@router.delete(
    "/projects/{project_id}/members/{user_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsProjectMemberDeleteResponse,
)
@management_endpoint_wrapper
async def delete_project_member(
    project_id: str,
    user_id: str,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsProjectMemberDeleteResponse:
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
    return await dispatcher_service().delete_project_member(
        project_id, user_id, user_api_key_dict
    )


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
