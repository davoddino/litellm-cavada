from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.auth.user_api_key_auth import user_api_key_auth
from litellm.proxy.cavadalabs.chatbot_scope import (
    require_chatbot_project_access,
    require_web_token_project_access,
)
from litellm.proxy.management_endpoints.cavadalabs_dispatcher_utils import (
    dispatcher_service,
)
from litellm.proxy.management_helpers.utils import management_endpoint_wrapper
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsChatbotCreateRequest,
    CavadaLabsChatbotListResponse,
    CavadaLabsChatbotResponse,
    CavadaLabsChatbotStatus,
    CavadaLabsChatbotUpdateRequest,
    CavadaLabsWebTokenCreateRequest,
    CavadaLabsWebTokenCreateResponse,
    CavadaLabsWebTokenListResponse,
    CavadaLabsWebTokenResponse,
    CavadaLabsWebTokenStatus,
)

router = APIRouter(tags=["cavadalabs-chatbot-admin"])


def _get_prisma_db():
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Database not connected"},
        )
    return prisma_client.db


async def _require_web_token_create_access(
    data: CavadaLabsWebTokenCreateRequest,
    user_api_key_dict: UserAPIKeyAuth,
) -> None:
    from litellm.proxy.cavadalabs.access_control import require_project_access

    project = await require_project_access(
        _get_prisma_db(),
        project_id=data.project_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=True,
    )
    if project.company_id != data.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "project_id must belong to company_id"},
        )


async def _require_chatbot_create_access(
    data: CavadaLabsChatbotCreateRequest,
    user_api_key_dict: UserAPIKeyAuth,
) -> None:
    from litellm.proxy.cavadalabs.access_control import require_project_access

    project = await require_project_access(
        _get_prisma_db(),
        project_id=data.project_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=True,
    )
    if project.company_id != data.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "project_id must belong to company_id"},
        )


async def _require_chatbot_access(
    chatbot_id: str,
    user_api_key_dict: UserAPIKeyAuth,
    *,
    require_admin: bool,
) -> CavadaLabsChatbotResponse:
    return await require_chatbot_project_access(
        _get_prisma_db(),
        chatbot_id=chatbot_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=require_admin,
    )


async def _resolve_chatbot_list_scope(
    *,
    company_id: Optional[str],
    project_id: Optional[str],
    user_api_key_dict: UserAPIKeyAuth,
) -> tuple[Optional[str], Optional[list[str]], Optional[str], Optional[list[str]]]:
    from litellm.proxy.cavadalabs.access_control import (
        is_cavadalabs_admin_view,
        require_company_access,
        require_project_access,
        visible_company_ids_for_user,
        visible_project_ids_for_user,
    )

    db = _get_prisma_db()
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
        return company_id, None, project_id, None

    if company_id is not None:
        await require_company_access(
            db,
            company_id=company_id,
            user_api_key_dict=user_api_key_dict,
            require_admin=False,
        )
        if is_cavadalabs_admin_view(user_api_key_dict):
            return company_id, None, None, None
        visible_project_ids = await visible_project_ids_for_user(
            db,
            user_api_key_dict,
            company_id=company_id,
        )
        return company_id, None, None, sorted(visible_project_ids or set())

    if is_cavadalabs_admin_view(user_api_key_dict):
        return None, None, None, None

    visible_company_ids = await visible_company_ids_for_user(db, user_api_key_dict)
    visible_project_ids = await visible_project_ids_for_user(db, user_api_key_dict)
    return (
        None,
        sorted(visible_company_ids or set()),
        None,
        sorted(visible_project_ids or set()),
    )


async def _resolve_web_token_list_scope(
    *,
    company_id: Optional[str],
    project_id: Optional[str],
    user_api_key_dict: UserAPIKeyAuth,
) -> tuple[Optional[str], Optional[list[str]], Optional[str], Optional[list[str]]]:
    from litellm.proxy.cavadalabs.access_control import (
        is_cavadalabs_admin_view,
        require_company_access,
        require_project_access,
        visible_company_ids_for_user,
        visible_project_ids_for_user,
    )

    db = _get_prisma_db()
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
        return company_id, None, project_id, None

    if company_id is not None:
        await require_company_access(
            db,
            company_id=company_id,
            user_api_key_dict=user_api_key_dict,
            require_admin=False,
        )
        if is_cavadalabs_admin_view(user_api_key_dict):
            return company_id, None, None, None
        visible_project_ids = await visible_project_ids_for_user(
            db,
            user_api_key_dict,
            company_id=company_id,
        )
        return company_id, None, None, sorted(visible_project_ids or set())

    if is_cavadalabs_admin_view(user_api_key_dict):
        return None, None, None, None

    visible_company_ids = await visible_company_ids_for_user(db, user_api_key_dict)
    visible_project_ids = await visible_project_ids_for_user(db, user_api_key_dict)
    return (
        None,
        sorted(visible_company_ids or set()),
        None,
        sorted(visible_project_ids or set()),
    )


async def _require_web_token_revoke_access(
    web_token_id: str,
    user_api_key_dict: UserAPIKeyAuth,
) -> None:
    await require_web_token_project_access(
        _get_prisma_db(),
        web_token_id=web_token_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=True,
    )


@router.post(
    "/chatbots",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsChatbotResponse,
)
@management_endpoint_wrapper
async def create_chatbot(
    data: CavadaLabsChatbotCreateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsChatbotResponse:
    await _require_chatbot_create_access(data, user_api_key_dict)
    return await dispatcher_service().create_chatbot(data, user_api_key_dict)


@router.get(
    "/chatbots",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsChatbotListResponse,
)
@management_endpoint_wrapper
async def list_chatbots(
    http_request: Request,
    company_id: Optional[str] = None,
    project_id: Optional[str] = None,
    status_filter: Optional[CavadaLabsChatbotStatus] = Query(
        default=None, alias="status"
    ),
    take: int = Query(default=100, ge=1, le=1000),
    skip: int = Query(default=0, ge=0),
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsChatbotListResponse:
    (
        resolved_company_id,
        resolved_company_ids,
        resolved_project_id,
        resolved_project_ids,
    ) = await _resolve_chatbot_list_scope(
        company_id=company_id,
        project_id=project_id,
        user_api_key_dict=user_api_key_dict,
    )
    chatbots = await dispatcher_service().list_chatbots(
        company_id=resolved_company_id,
        company_ids=resolved_company_ids,
        project_id=resolved_project_id,
        project_ids=resolved_project_ids,
        status_filter=status_filter,
        take=take,
        skip=skip,
    )
    return CavadaLabsChatbotListResponse(chatbots=chatbots, count=len(chatbots))


@router.get(
    "/chatbots/{chatbot_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsChatbotResponse,
)
@management_endpoint_wrapper
async def get_chatbot(
    chatbot_id: str,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsChatbotResponse:
    return await _require_chatbot_access(
        chatbot_id,
        user_api_key_dict,
        require_admin=False,
    )


@router.patch(
    "/chatbots/{chatbot_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsChatbotResponse,
)
@management_endpoint_wrapper
async def update_chatbot(
    chatbot_id: str,
    data: CavadaLabsChatbotUpdateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsChatbotResponse:
    await _require_chatbot_access(
        chatbot_id,
        user_api_key_dict,
        require_admin=True,
    )
    return await dispatcher_service().update_chatbot(
        chatbot_id, data, user_api_key_dict
    )


@router.delete(
    "/chatbots/{chatbot_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsChatbotResponse,
)
@management_endpoint_wrapper
async def disable_chatbot(
    chatbot_id: str,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsChatbotResponse:
    await _require_chatbot_access(
        chatbot_id,
        user_api_key_dict,
        require_admin=True,
    )
    return await dispatcher_service().update_chatbot(
        chatbot_id,
        CavadaLabsChatbotUpdateRequest(status=CavadaLabsChatbotStatus.DISABLED),
        user_api_key_dict,
    )


@router.post(
    "/web-tokens",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsWebTokenCreateResponse,
)
@management_endpoint_wrapper
async def create_web_token(
    data: CavadaLabsWebTokenCreateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsWebTokenCreateResponse:
    await _require_web_token_create_access(data, user_api_key_dict)
    return await dispatcher_service().create_web_token(data, user_api_key_dict)


@router.get(
    "/web-tokens",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsWebTokenListResponse,
)
@management_endpoint_wrapper
async def list_web_tokens(
    http_request: Request,
    company_id: Optional[str] = None,
    project_id: Optional[str] = None,
    chatbot_id: Optional[str] = None,
    status_filter: Optional[CavadaLabsWebTokenStatus] = Query(
        default=None, alias="status"
    ),
    take: int = Query(default=100, ge=1, le=1000),
    skip: int = Query(default=0, ge=0),
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsWebTokenListResponse:
    (
        resolved_company_id,
        resolved_company_ids,
        resolved_project_id,
        resolved_project_ids,
    ) = await _resolve_web_token_list_scope(
        company_id=company_id,
        project_id=project_id,
        user_api_key_dict=user_api_key_dict,
    )
    web_tokens = await dispatcher_service().list_web_tokens(
        company_id=resolved_company_id,
        company_ids=resolved_company_ids,
        project_id=resolved_project_id,
        project_ids=resolved_project_ids,
        chatbot_id=chatbot_id,
        status_filter=status_filter,
        take=take,
        skip=skip,
    )
    return CavadaLabsWebTokenListResponse(web_tokens=web_tokens, count=len(web_tokens))


@router.post(
    "/web-tokens/{web_token_id}/revoke",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsWebTokenResponse,
)
@management_endpoint_wrapper
async def revoke_web_token(
    web_token_id: str,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsWebTokenResponse:
    await _require_web_token_revoke_access(web_token_id, user_api_key_dict)
    return await dispatcher_service().revoke_web_token(web_token_id, user_api_key_dict)
