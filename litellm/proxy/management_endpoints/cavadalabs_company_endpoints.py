from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.auth.user_api_key_auth import user_api_key_auth
from litellm.proxy.cavadalabs.access_control import (
    require_company_access,
    require_company_admin_access,
    resolve_cavadalabs_company_usage_scope,
    visible_company_ids_for_user,
    with_company_access_metadata,
)
from litellm.proxy.cavadalabs.usage import (
    get_cavadalabs_daily_activity,
    get_cavadalabs_usage_diagnostics,
    repair_cavadalabs_usage_scope,
)
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
    CavadaLabsUsageDiagnosticsResponse,
    CavadaLabsUsageRepairRequest,
    CavadaLabsUsageRepairResponse,
)

router = APIRouter(tags=["cavadalabs-companies"])


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
    companies = [
        await with_company_access_metadata(
            prisma_client.db,
            company=company,
            user_api_key_dict=user_api_key_dict,
        )
        for company in companies
    ]
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
    provider: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    api_key: Optional[str] = Query(default=None),
    min_spend: Optional[float] = Query(default=None, ge=0),
    max_spend: Optional[float] = Query(default=None, ge=0),
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
    "/companies/usage/diagnostics",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsUsageDiagnosticsResponse,
)
@management_endpoint_wrapper
async def get_company_usage_diagnostics(
    http_request: Request,
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    company_ids: Optional[str] = Query(default=None),
    model: Optional[str] = Query(default=None),
    provider: Optional[str] = Query(default=None),
    api_key: Optional[str] = Query(default=None),
    timezone: Optional[int] = Query(default=None),
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsUsageDiagnosticsResponse:
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Database is required for CavadaLabs dispatcher"},
        )
    if _split_csv(company_ids) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Select at least one Company for usage diagnostics"},
        )
    entity_ids = await resolve_cavadalabs_company_usage_scope(
        prisma_client.db,
        user_api_key_dict=user_api_key_dict,
        requested_company_ids=company_ids,
    )
    return await get_cavadalabs_usage_diagnostics(
        prisma_client=prisma_client,
        entity_type="company",
        entity_id=entity_ids,
        start_date=start_date,
        end_date=end_date,
        timezone_offset_minutes=timezone,
        model=model,
        provider=provider,
        api_key=api_key,
    )


@router.post(
    "/companies/usage/repair",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsUsageRepairResponse,
)
@management_endpoint_wrapper
async def repair_company_usage(
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
    company_ids = _normalize_id_list(data.company_ids)
    if not company_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Select at least one Company for usage repair"},
        )
    entity_ids = await resolve_cavadalabs_company_usage_scope(
        prisma_client.db,
        user_api_key_dict=user_api_key_dict,
        requested_company_ids=",".join(company_ids),
    )
    if not entity_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "You do not have access to any requested Companies"},
        )
    for company_id in entity_ids:
        await require_company_admin_access(
            prisma_client.db,
            company_id=company_id,
            user_api_key_dict=user_api_key_dict,
        )
    return await repair_cavadalabs_usage_scope(
        prisma_client=prisma_client,
        entity_type="company",
        entity_id=entity_ids,
        start_date=data.start_date,
        end_date=data.end_date,
        timezone_offset_minutes=data.timezone,
        model=data.model,
        provider=data.provider,
        api_key=data.api_key,
        dry_run=data.dry_run,
        batch_limit=data.batch_limit,
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
    company = await dispatcher_service().get_company(company_id)
    return await with_company_access_metadata(
        prisma_client.db,
        company=company,
        user_api_key_dict=user_api_key_dict,
    )


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
