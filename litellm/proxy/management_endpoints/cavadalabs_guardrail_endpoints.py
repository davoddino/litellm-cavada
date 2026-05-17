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


def _prisma_client():
    from litellm.proxy import proxy_server

    if proxy_server.prisma_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Database is required for CavadaLabs guardrails"},
        )
    return proxy_server.prisma_client


def _service() -> CavadaLabsGuardrailService:
    return CavadaLabsGuardrailService(_prisma_client())


async def _require_chatbot_company_project_match(
    *,
    chatbot_id: str,
    company_id: str,
    project_id: Optional[str],
    user_api_key_dict: UserAPIKeyAuth,
    require_admin: bool,
) -> None:
    chatbot = await require_chatbot_project_access(
        _prisma_client().db,
        chatbot_id=chatbot_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=require_admin,
    )
    if chatbot.company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "chatbot_id must belong to company_id"},
        )
    if project_id is not None and chatbot.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "chatbot_id must belong to project_id"},
        )


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


async def _require_guardrail_context_access(
    *,
    company_id: str,
    project_id: Optional[str],
    chatbot_id: Optional[str],
    user_api_key_dict: UserAPIKeyAuth,
    require_admin: bool,
) -> None:
    if chatbot_id is not None:
        await _require_chatbot_company_project_match(
            chatbot_id=chatbot_id,
            company_id=company_id,
            project_id=project_id,
            user_api_key_dict=user_api_key_dict,
            require_admin=require_admin,
        )
        return
    if project_id is not None:
        await _require_project_company_match(
            project_id=project_id,
            company_id=company_id,
            user_api_key_dict=user_api_key_dict,
            require_admin=require_admin,
        )
        return
    await require_company_wide_access(
        _prisma_client().db,
        company_id=company_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=require_admin,
    )


async def _require_policy_access(
    policy: CavadaLabsGuardrailPolicyResponse,
    user_api_key_dict: UserAPIKeyAuth,
    *,
    require_admin: bool,
) -> None:
    await _require_guardrail_context_access(
        company_id=policy.company_id,
        project_id=policy.project_id,
        chatbot_id=policy.chatbot_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=require_admin,
    )


async def _resolve_guardrail_list_filters(
    *,
    company_id: Optional[str],
    project_id: Optional[str],
    chatbot_id: Optional[str],
    user_api_key_dict: UserAPIKeyAuth,
) -> tuple[Optional[str], Optional[list[str]], Optional[str], Optional[list[str]]]:
    db = _prisma_client().db
    if chatbot_id is not None:
        chatbot = await require_chatbot_project_access(
            db,
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
        return None, None, chatbot.project_id, None

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
    await _require_guardrail_context_access(
        company_id=data.company_id,
        project_id=data.project_id,
        chatbot_id=data.chatbot_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=True,
    )
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
    scoped_company_id, scoped_company_ids, scoped_project_id, scoped_project_ids = (
        await _resolve_guardrail_list_filters(
            company_id=company_id,
            project_id=project_id,
            chatbot_id=chatbot_id,
            user_api_key_dict=user_api_key_dict,
        )
    )
    return await _service().list_policies(
        company_id=scoped_company_id,
        company_ids=scoped_company_ids,
        project_id=scoped_project_id,
        project_ids=scoped_project_ids,
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
    policy = await _service().get_policy(policy_id)
    await _require_policy_access(
        policy,
        user_api_key_dict,
        require_admin=False,
    )
    return policy


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
    service = _service()
    policy = await service.get_policy(policy_id)
    await _require_policy_access(
        policy,
        user_api_key_dict,
        require_admin=True,
    )
    return await service.update_policy(policy_id, data, user_api_key_dict)


@router.delete(
    "/guardrail-policies/{policy_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsGuardrailPolicyResponse,
)
@management_endpoint_wrapper
async def archive_guardrail_policy(
    policy_id: str,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsGuardrailPolicyResponse:
    service = _service()
    policy = await service.get_policy(policy_id)
    await _require_policy_access(
        policy,
        user_api_key_dict,
        require_admin=True,
    )
    return await service.update_policy(
        policy_id,
        CavadaLabsGuardrailPolicyUpdateRequest(
            status=CavadaLabsGuardrailPolicyStatus.ARCHIVED
        ),
        user_api_key_dict,
    )


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
    service = _service()
    policy = await service.get_policy(policy_id)
    await _require_policy_access(
        policy,
        user_api_key_dict,
        require_admin=True,
    )
    return await service.update_policy(
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
    await _require_guardrail_context_access(
        company_id=data.company_id,
        project_id=data.project_id,
        chatbot_id=data.chatbot_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=False,
    )
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
    service = _service()
    scoped_company_id = company_id
    scoped_company_ids = None
    scoped_project_id = project_id
    scoped_project_ids = None
    if policy_id is not None:
        policy = await service.get_policy(policy_id)
        await _require_policy_access(
            policy,
            user_api_key_dict,
            require_admin=False,
        )
        if company_id is not None and policy.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "policy_id must belong to company_id"},
            )
        if project_id is not None:
            await _require_project_company_match(
                project_id=project_id,
                company_id=policy.company_id,
                user_api_key_dict=user_api_key_dict,
                require_admin=False,
            )
            if policy.project_id is not None and policy.project_id != project_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"error": "policy_id must belong to project_id"},
                )
        if chatbot_id is not None:
            await _require_chatbot_company_project_match(
                chatbot_id=chatbot_id,
                company_id=policy.company_id,
                project_id=project_id or policy.project_id,
                user_api_key_dict=user_api_key_dict,
                require_admin=False,
            )
            if policy.chatbot_id is not None and policy.chatbot_id != chatbot_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"error": "policy_id must belong to chatbot_id"},
                )
        scoped_company_id = policy.company_id
        scoped_project_id = project_id or policy.project_id
    else:
        scoped_company_id, scoped_company_ids, scoped_project_id, scoped_project_ids = (
            await _resolve_guardrail_list_filters(
                company_id=company_id,
                project_id=project_id,
                chatbot_id=chatbot_id,
                user_api_key_dict=user_api_key_dict,
            )
        )
    return await _service().list_decision_logs(
        company_id=scoped_company_id,
        company_ids=scoped_company_ids,
        project_id=scoped_project_id,
        project_ids=scoped_project_ids,
        chatbot_id=chatbot_id,
        policy_id=policy_id,
        decision=decision,
        take=take,
        skip=skip,
    )
