from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.auth.user_api_key_auth import user_api_key_auth
from litellm.proxy.cavadalabs.access_control import (
    require_company_access,
    resolve_cavadalabs_company_usage_scope,
    visible_company_ids_for_user,
)
from litellm.proxy.cavadalabs.usage import get_cavadalabs_daily_activity
from litellm.proxy.management_endpoints.cavadalabs_dispatcher_utils import (
    dispatcher_service,
    require_proxy_admin,
)
from litellm.proxy.management_helpers.utils import management_endpoint_wrapper
from litellm.types.proxy.management_endpoints.common_daily_activity import (
    SpendAnalyticsPaginatedResponse,
)
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsCompanyCreateRequest,
    CavadaLabsCompanyListResponse,
    CavadaLabsCompanyResponse,
    CavadaLabsCompanyUpdateRequest,
    CavadaLabsStatus,
)

router = APIRouter(tags=["cavadalabs-companies"])


def _split_csv(value: Optional[str]) -> Optional[list[str]]:
    if value is None:
        return None
    values = [item.strip() for item in value.split(",") if item.strip()]
    return values or None


@router.post(
    "/companies",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsCompanyResponse,
)
@management_endpoint_wrapper
async def create_company(
    data: CavadaLabsCompanyCreateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsCompanyResponse:
    require_proxy_admin(user_api_key_dict)
    return await dispatcher_service().create_company(data, user_api_key_dict)


@router.get(
    "/companies",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsCompanyListResponse,
)
@management_endpoint_wrapper
async def list_companies(
    http_request: Request,
    status_filter: Optional[CavadaLabsStatus] = Query(default=None, alias="status"),
    take: int = Query(default=100, ge=1, le=1000),
    skip: int = Query(default=0, ge=0),
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsCompanyListResponse:
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Database is required for CavadaLabs dispatcher"},
        )
    visible_company_ids = await visible_company_ids_for_user(
        prisma_client.db,
        user_api_key_dict,
    )
    companies = await dispatcher_service().list_companies(
        status_filter=status_filter,
        company_ids=(
            list(visible_company_ids) if visible_company_ids is not None else None
        ),
        take=take,
        skip=skip,
    )
    return CavadaLabsCompanyListResponse(companies=companies, count=len(companies))


@router.get(
    "/companies/daily/activity",
    dependencies=[Depends(user_api_key_auth)],
    response_model=SpendAnalyticsPaginatedResponse,
)
@management_endpoint_wrapper
async def get_company_daily_activity(
    http_request: Request,
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    model: Optional[str] = Query(default=None),
    api_key: Optional[str] = Query(default=None),
    company_ids: Optional[str] = Query(default=None),
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
    entity_ids = await resolve_cavadalabs_company_usage_scope(
        prisma_client.db,
        user_api_key_dict=user_api_key_dict,
        requested_company_ids=company_ids,
    )
    return await get_cavadalabs_daily_activity(
        prisma_client=prisma_client,
        entity_id_field="company_id",
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
    "/companies/{company_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsCompanyResponse,
)
@management_endpoint_wrapper
async def get_company(
    company_id: str,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsCompanyResponse:
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Database is required for CavadaLabs dispatcher"},
        )
    await require_company_access(
        prisma_client.db,
        company_id=company_id,
        user_api_key_dict=user_api_key_dict,
    )
    return await dispatcher_service().get_company(company_id)


@router.patch(
    "/companies/{company_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsCompanyResponse,
)
@management_endpoint_wrapper
async def update_company(
    company_id: str,
    data: CavadaLabsCompanyUpdateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsCompanyResponse:
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Database is required for CavadaLabs dispatcher"},
        )
    await require_company_access(
        prisma_client.db,
        company_id=company_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=True,
    )
    return await dispatcher_service().update_company(
        company_id, data, user_api_key_dict
    )


@router.delete(
    "/companies/{company_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsCompanyResponse,
)
@management_endpoint_wrapper
async def archive_company(
    company_id: str,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsCompanyResponse:
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Database is required for CavadaLabs dispatcher"},
        )
    await require_company_access(
        prisma_client.db,
        company_id=company_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=True,
    )
    return await dispatcher_service().archive_company(company_id, user_api_key_dict)
