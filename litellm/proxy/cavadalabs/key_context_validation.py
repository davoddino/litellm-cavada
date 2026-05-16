from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import HTTPException, status

from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.cavadalabs.key_context_metadata import (
    CavadaLabsResolvedKeyContext,
    _optional_str,
)
from litellm.proxy.cavadalabs.key_context_schema import (
    _raise_if_cavadalabs_key_context_schema_exception,
)


def _is_proxy_admin_user(user_api_key_dict: UserAPIKeyAuth) -> bool:
    return user_api_key_dict.user_role in {
        LitellmUserRoles.PROXY_ADMIN,
        LitellmUserRoles.PROXY_ADMIN.value,
    }


async def _require_cavadalabs_key_context_access(
    prisma_client: Any,
    resolved_context: CavadaLabsResolvedKeyContext,
    user_api_key_dict: UserAPIKeyAuth,
) -> None:
    from litellm.proxy.cavadalabs.access_control import (
        authorize_cavadalabs_company_project_access,
    )

    await authorize_cavadalabs_company_project_access(
        prisma_client.db,
        company_id=resolved_context.company_id,
        project_id=resolved_context.project_id,
        user_api_key_dict=user_api_key_dict,
        action="manage",
    )


async def _validate_cavadalabs_key_context(
    prisma_client: Any,
    company_id: Optional[str],
    project_id: Optional[str],
) -> CavadaLabsResolvedKeyContext:
    if project_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "cavadalabs_project_id is required when assigning a CavadaLabs key context"
            },
        )

    try:
        project = await prisma_client.db.cavadalabs_projecttable.find_unique(
            where={"project_id": project_id}
        )
    except Exception as exc:
        _raise_if_cavadalabs_key_context_schema_exception(
            "cavadalabs_projecttable", exc
        )
        raise
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": f"CavadaLabs project not found: {project_id}"},
        )

    resolved_company_id = company_id or getattr(project, "company_id", None)
    if resolved_company_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "CavadaLabs project is missing its company_id"},
        )

    if getattr(project, "company_id", None) != resolved_company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "cavadalabs_project_id must belong to cavadalabs_company_id"
            },
        )

    if getattr(project, "status", None) == "archived":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": f"CavadaLabs project is archived: {project_id}"},
        )
    litellm_team_id = _optional_str(getattr(project, "litellm_team_id", None))
    if litellm_team_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": f"CavadaLabs project is missing its internal compatibility mapping: {project_id}"
            },
        )

    try:
        company = await prisma_client.db.cavadalabs_companytable.find_unique(
            where={"company_id": resolved_company_id}
        )
    except Exception as exc:
        _raise_if_cavadalabs_key_context_schema_exception(
            "cavadalabs_companytable", exc
        )
        raise
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": f"CavadaLabs company not found: {resolved_company_id}"},
        )
    if getattr(company, "status", None) != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": f"CavadaLabs company is not active: {resolved_company_id}"
            },
        )
    litellm_organization_id = _optional_str(
        getattr(company, "litellm_organization_id", None)
    )
    if litellm_organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": f"CavadaLabs company is missing its internal compatibility mapping: {resolved_company_id}"
            },
        )

    return CavadaLabsResolvedKeyContext(
        company_id=resolved_company_id,
        project_id=project_id,
        litellm_organization_id=litellm_organization_id,
        litellm_team_id=litellm_team_id,
    )


async def _validate_cavadalabs_key_chatbot_context(
    prisma_client: Any,
    resolved_context: CavadaLabsResolvedKeyContext,
    chatbot_id: Optional[str],
) -> None:
    if chatbot_id is None:
        return

    try:
        chatbot = await prisma_client.db.cavadalabs_chatbottable.find_unique(
            where={"chatbot_id": chatbot_id}
        )
    except Exception as exc:
        _raise_if_cavadalabs_key_context_schema_exception(
            "cavadalabs_chatbottable", exc
        )
        raise
    if chatbot is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": f"CavadaLabs chatbot not found: {chatbot_id}"},
        )
    if (
        getattr(chatbot, "company_id", None) != resolved_context.company_id
        or getattr(chatbot, "project_id", None) != resolved_context.project_id
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "cavadalabs_chatbot_id must belong to the key Company and Project",
                "chatbot_id": chatbot_id,
                "company_id": resolved_context.company_id,
                "project_id": resolved_context.project_id,
            },
        )


def _raise_cavadalabs_key_context_conflict(
    field_name: Literal["organization_id", "team_id"],
    incoming_value: Optional[str],
    mapped_value: str,
    *,
    field_was_submitted: bool = False,
) -> None:
    if not field_was_submitted and incoming_value is None:
        return
    if incoming_value == mapped_value:
        return
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "error": (
                f"{field_name} conflicts with the CavadaLabs company/project "
                f"compatibility mapping. Expected {mapped_value}, received {incoming_value}."
            )
        },
    )
