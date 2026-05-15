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
    require_proxy_admin(user_api_key_dict)
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
    require_admin_view(user_api_key_dict)
    chatbots = await dispatcher_service().list_chatbots(
        company_id=company_id,
        project_id=project_id,
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
    require_admin_view(user_api_key_dict)
    return await dispatcher_service().get_chatbot(chatbot_id)


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
    require_proxy_admin(user_api_key_dict)
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
    require_proxy_admin(user_api_key_dict)
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
    require_proxy_admin(user_api_key_dict)
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
    require_admin_view(user_api_key_dict)
    web_tokens = await dispatcher_service().list_web_tokens(
        company_id=company_id,
        project_id=project_id,
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
    require_proxy_admin(user_api_key_dict)
    return await dispatcher_service().revoke_web_token(web_token_id, user_api_key_dict)
