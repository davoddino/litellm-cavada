from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.cavadalabs.access_control import require_project_access
from litellm.proxy.cavadalabs.chatbot_schema import get_required_response
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsChatbotResponse,
    CavadaLabsWebTokenResponse,
)


async def get_chatbot_for_scope(db: Any, chatbot_id: str) -> CavadaLabsChatbotResponse:
    return await get_required_response(
        db,
        delegate_name="cavadalabs_chatbottable",
        where={"chatbot_id": chatbot_id},
        response_model=CavadaLabsChatbotResponse,
        resource_name="Chatbot",
        resource_id=chatbot_id,
    )


async def get_web_token_for_scope(
    db: Any, web_token_id: str
) -> CavadaLabsWebTokenResponse:
    return await get_required_response(
        db,
        delegate_name="cavadalabs_webtokentable",
        where={"web_token_id": web_token_id},
        response_model=CavadaLabsWebTokenResponse,
        resource_name="Web token",
        resource_id=web_token_id,
    )


async def require_chatbot_project_access(
    db: Any,
    *,
    chatbot_id: str,
    user_api_key_dict: UserAPIKeyAuth,
    require_admin: bool,
) -> CavadaLabsChatbotResponse:
    chatbot = await get_chatbot_for_scope(db, chatbot_id)
    project = await require_project_access(
        db,
        project_id=chatbot.project_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=require_admin,
    )
    if project.company_id != chatbot.company_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Chatbot Project does not belong to its Company"},
        )
    return chatbot


async def require_web_token_project_access(
    db: Any,
    *,
    web_token_id: str,
    user_api_key_dict: UserAPIKeyAuth,
    require_admin: bool,
) -> CavadaLabsWebTokenResponse:
    web_token = await get_web_token_for_scope(db, web_token_id)
    project = await require_project_access(
        db,
        project_id=web_token.project_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=require_admin,
    )
    if project.company_id != web_token.company_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Web token Project does not belong to its Company"},
        )
    return web_token
