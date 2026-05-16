from __future__ import annotations

from typing import Any, Dict, Optional

from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.cavadalabs.dispatcher_shared import (
    CavadaLabsRuntimeContext,
    hash_web_token,
)
from litellm.proxy.cavadalabs.chatbot_token_metadata import (
    build_chatbot_token_metadata,
)

CHATBOT_MESSAGES_ROUTE = "/cavadalabs/chatbots/messages"


def build_chatbot_runtime_user_api_key(
    *,
    context: CavadaLabsRuntimeContext,
    token: str,
    payload: Optional[Dict[str, Any]] = None,
) -> UserAPIKeyAuth:
    allowed_models = _allowed_runtime_models(context=context, payload=payload)
    metadata = build_chatbot_token_metadata(
        getattr(context.web_token, "metadata", None),
        company_id=context.company.company_id,
        project_id=context.project.project_id,
        chatbot_id=context.chatbot.chatbot_id,
        web_token_id=context.web_token.web_token_id,
    )
    return UserAPIKeyAuth(
        api_key=f"cavadalabs-web-token-{context.web_token.web_token_id}",
        token=hash_web_token(token),
        key_alias=context.web_token.name,
        models=allowed_models,
        user_id=f"cavadalabs-company-{context.company.company_id}",
        team_id=context.project.litellm_team_id,
        org_id=context.company.litellm_organization_id,
        project_id=context.project.project_id,
        request_route=CHATBOT_MESSAGES_ROUTE,
        cavadalabs_company_id=context.company.company_id,
        cavadalabs_project_id=context.project.project_id,
        metadata=metadata,
    )


def _allowed_runtime_models(
    *,
    context: CavadaLabsRuntimeContext,
    payload: Optional[Dict[str, Any]],
) -> list[str]:
    allowed_models = [
        context.primary_policy.model_alias,
        *[
            policy.model_alias
            for policy in context.fallback_policies
            if policy.fallback_enabled
        ],
    ]
    if payload is None:
        return _unique_strings(allowed_models)

    requested_model = payload.get("model")
    if isinstance(requested_model, str):
        allowed_models.append(requested_model)

    fallbacks = payload.get("fallbacks")
    if isinstance(fallbacks, list):
        allowed_models.extend(
            fallback_model
            for fallback_model in fallbacks
            if isinstance(fallback_model, str)
        )
    return _unique_strings(allowed_models)


def _unique_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result
