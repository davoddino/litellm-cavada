from __future__ import annotations

from fastapi import HTTPException, status

from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.cavadalabs.dispatcher import CavadaLabsDispatcherService


def require_proxy_admin(user_api_key_dict: UserAPIKeyAuth) -> None:
    if user_api_key_dict.user_role != LitellmUserRoles.PROXY_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "CavadaLabs dispatcher mutations require proxy_admin"},
        )


def require_admin_view(user_api_key_dict: UserAPIKeyAuth) -> None:
    if user_api_key_dict.user_role not in {
        LitellmUserRoles.PROXY_ADMIN,
        LitellmUserRoles.PROXY_ADMIN_VIEW_ONLY,
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "CavadaLabs dispatcher access requires admin view"},
        )


def dispatcher_service() -> CavadaLabsDispatcherService:
    from litellm.proxy import proxy_server

    if proxy_server.prisma_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Database is required for CavadaLabs dispatcher"},
        )
    return CavadaLabsDispatcherService(proxy_server.prisma_client)
