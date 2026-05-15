from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.auth.user_api_key_auth import user_api_key_auth
from litellm.proxy.cavadalabs.access_control import (
    require_company_access,
    resolve_cavadalabs_company_usage_scope,
)
from litellm.proxy.cavadalabs.billing import CavadaLabsBillingService
from litellm.proxy.management_helpers.utils import management_endpoint_wrapper
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsBillingReportGenerateRequest,
    CavadaLabsBillingReportListResponse,
    CavadaLabsBillingReportResponse,
)

router = APIRouter(prefix="/cavadalabs", tags=["cavadalabs-billing"])


def _prisma_client():
    from litellm.proxy import proxy_server

    if proxy_server.prisma_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Database is required for CavadaLabs billing"},
        )
    return proxy_server.prisma_client


def _service() -> CavadaLabsBillingService:
    return CavadaLabsBillingService(_prisma_client())


@router.post(
    "/billing-reports",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsBillingReportResponse,
)
@management_endpoint_wrapper
async def generate_billing_report(
    data: CavadaLabsBillingReportGenerateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsBillingReportResponse:
    prisma_client = _prisma_client()
    await require_company_access(
        prisma_client.db,
        company_id=data.company_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=True,
    )
    return await CavadaLabsBillingService(prisma_client).generate_monthly_report(
        data, user_api_key_dict
    )


@router.get(
    "/billing-reports",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsBillingReportListResponse,
)
@management_endpoint_wrapper
async def list_billing_reports(
    http_request: Request,
    company_id: Optional[str] = None,
    year: Optional[int] = Query(default=None, ge=2000, le=2100),
    month: Optional[int] = Query(default=None, ge=1, le=12),
    take: int = Query(default=100, ge=1, le=1000),
    skip: int = Query(default=0, ge=0),
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsBillingReportListResponse:
    prisma_client = _prisma_client()
    company_ids = None
    if company_id is not None:
        await require_company_access(
            prisma_client.db,
            company_id=company_id,
            user_api_key_dict=user_api_key_dict,
        )
    else:
        company_ids = await resolve_cavadalabs_company_usage_scope(
            prisma_client.db,
            user_api_key_dict=user_api_key_dict,
            requested_company_ids=None,
        )
    return await CavadaLabsBillingService(prisma_client).list_billing_reports(
        company_id=company_id,
        company_ids=company_ids,
        year=year,
        month=month,
        take=take,
        skip=skip,
    )


@router.get(
    "/billing-reports/{report_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsBillingReportResponse,
)
@management_endpoint_wrapper
async def get_billing_report(
    report_id: str,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsBillingReportResponse:
    prisma_client = _prisma_client()
    report = await CavadaLabsBillingService(prisma_client).get_billing_report(report_id)
    await require_company_access(
        prisma_client.db,
        company_id=report.company_id,
        user_api_key_dict=user_api_key_dict,
    )
    return report
