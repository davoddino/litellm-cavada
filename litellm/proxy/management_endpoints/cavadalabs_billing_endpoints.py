from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.auth.user_api_key_auth import user_api_key_auth
from litellm.proxy.cavadalabs.billing import CavadaLabsBillingService
from litellm.proxy.management_helpers.utils import management_endpoint_wrapper
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsBillingReportGenerateRequest,
    CavadaLabsBillingReportListResponse,
    CavadaLabsBillingReportResponse,
)

router = APIRouter(prefix="/cavadalabs", tags=["cavadalabs-billing"])


def _require_proxy_admin(user_api_key_dict: UserAPIKeyAuth) -> None:
    if user_api_key_dict.user_role != LitellmUserRoles.PROXY_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "CavadaLabs billing mutations require proxy_admin"},
        )


def _require_admin_view(user_api_key_dict: UserAPIKeyAuth) -> None:
    if user_api_key_dict.user_role not in {
        LitellmUserRoles.PROXY_ADMIN,
        LitellmUserRoles.PROXY_ADMIN_VIEW_ONLY,
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "CavadaLabs billing access requires admin view"},
        )


def _service() -> CavadaLabsBillingService:
    from litellm.proxy import proxy_server

    if proxy_server.prisma_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Database is required for CavadaLabs billing"},
        )
    return CavadaLabsBillingService(proxy_server.prisma_client)


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
    _require_proxy_admin(user_api_key_dict)
    return await _service().generate_monthly_report(data, user_api_key_dict)


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
    _require_admin_view(user_api_key_dict)
    return await _service().list_billing_reports(
        company_id=company_id,
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
    _require_admin_view(user_api_key_dict)
    return await _service().get_billing_report(report_id)
