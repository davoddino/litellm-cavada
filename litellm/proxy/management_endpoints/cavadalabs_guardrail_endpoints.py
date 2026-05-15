from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.auth.user_api_key_auth import user_api_key_auth
from litellm.proxy.cavadalabs.guardrails import CavadaLabsGuardrailService
from litellm.proxy.management_helpers.utils import management_endpoint_wrapper
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsGuardrailDecision,
    CavadaLabsGuardrailDecisionLogListResponse,
    CavadaLabsGuardrailEnforcementMode,
    CavadaLabsGuardrailEvaluateRequest,
    CavadaLabsGuardrailEvaluationResult,
    CavadaLabsGuardrailPolicyCreateRequest,
    CavadaLabsGuardrailPolicyListResponse,
    CavadaLabsGuardrailPolicyResponse,
    CavadaLabsGuardrailPolicyStatus,
    CavadaLabsGuardrailPolicyUpdateRequest,
)

router = APIRouter(prefix="/cavadalabs", tags=["cavadalabs-guardrails"])


def _require_proxy_admin(user_api_key_dict: UserAPIKeyAuth) -> None:
    if user_api_key_dict.user_role != LitellmUserRoles.PROXY_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "CavadaLabs guardrail mutations require proxy_admin"},
        )


def _require_admin_view(user_api_key_dict: UserAPIKeyAuth) -> None:
    if user_api_key_dict.user_role not in {
        LitellmUserRoles.PROXY_ADMIN,
        LitellmUserRoles.PROXY_ADMIN_VIEW_ONLY,
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "CavadaLabs guardrail access requires admin view"},
        )


def _service() -> CavadaLabsGuardrailService:
    from litellm.proxy import proxy_server

    if proxy_server.prisma_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Database is required for CavadaLabs guardrails"},
        )
    return CavadaLabsGuardrailService(proxy_server.prisma_client)


@router.post(
    "/guardrail-policies",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsGuardrailPolicyResponse,
)
@management_endpoint_wrapper
async def create_guardrail_policy(
    data: CavadaLabsGuardrailPolicyCreateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsGuardrailPolicyResponse:
    _require_proxy_admin(user_api_key_dict)
    return await _service().create_policy(data, user_api_key_dict)


@router.get(
    "/guardrail-policies",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsGuardrailPolicyListResponse,
)
@management_endpoint_wrapper
async def list_guardrail_policies(
    http_request: Request,
    company_id: Optional[str] = None,
    project_id: Optional[str] = None,
    chatbot_id: Optional[str] = None,
    status_filter: Optional[CavadaLabsGuardrailPolicyStatus] = Query(
        default=None, alias="status"
    ),
    take: int = Query(default=100, ge=1, le=1000),
    skip: int = Query(default=0, ge=0),
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsGuardrailPolicyListResponse:
    _require_admin_view(user_api_key_dict)
    return await _service().list_policies(
        company_id=company_id,
        project_id=project_id,
        chatbot_id=chatbot_id,
        status_filter=status_filter,
        take=take,
        skip=skip,
    )


@router.get(
    "/guardrail-policies/{policy_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsGuardrailPolicyResponse,
)
@management_endpoint_wrapper
async def get_guardrail_policy(
    policy_id: str,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsGuardrailPolicyResponse:
    _require_admin_view(user_api_key_dict)
    return await _service().get_policy(policy_id)


@router.patch(
    "/guardrail-policies/{policy_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsGuardrailPolicyResponse,
)
@management_endpoint_wrapper
async def update_guardrail_policy(
    policy_id: str,
    data: CavadaLabsGuardrailPolicyUpdateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsGuardrailPolicyResponse:
    _require_proxy_admin(user_api_key_dict)
    return await _service().update_policy(policy_id, data, user_api_key_dict)


@router.post(
    "/guardrail-policies/{policy_id}/activate",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsGuardrailPolicyResponse,
)
@management_endpoint_wrapper
async def activate_guardrail_policy(
    policy_id: str,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsGuardrailPolicyResponse:
    _require_proxy_admin(user_api_key_dict)
    return await _service().update_policy(
        policy_id,
        CavadaLabsGuardrailPolicyUpdateRequest(
            status=CavadaLabsGuardrailPolicyStatus.ACTIVE,
            enforcement_mode=CavadaLabsGuardrailEnforcementMode.ENFORCE,
        ),
        user_api_key_dict,
    )


@router.post(
    "/guardrails/evaluate",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsGuardrailEvaluationResult,
)
@management_endpoint_wrapper
async def evaluate_guardrails(
    data: CavadaLabsGuardrailEvaluateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsGuardrailEvaluationResult:
    _require_admin_view(user_api_key_dict)
    return await _service().evaluate_text(data)


@router.get(
    "/guardrail-decisions",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsGuardrailDecisionLogListResponse,
)
@management_endpoint_wrapper
async def list_guardrail_decisions(
    http_request: Request,
    company_id: Optional[str] = None,
    project_id: Optional[str] = None,
    chatbot_id: Optional[str] = None,
    policy_id: Optional[str] = None,
    decision: Optional[CavadaLabsGuardrailDecision] = None,
    take: int = Query(default=100, ge=1, le=1000),
    skip: int = Query(default=0, ge=0),
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsGuardrailDecisionLogListResponse:
    _require_admin_view(user_api_key_dict)
    return await _service().list_decision_logs(
        company_id=company_id,
        project_id=project_id,
        chatbot_id=chatbot_id,
        policy_id=policy_id,
        decision=decision,
        take=take,
        skip=skip,
    )
