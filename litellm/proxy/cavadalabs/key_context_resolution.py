from __future__ import annotations

from typing import Any, Optional, Tuple

from fastapi import HTTPException, status

from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.cavadalabs.key_context_metadata import (
    CAVADALABS_COMPANY_METADATA_KEY,
    CAVADALABS_PROJECT_METADATA_KEY,
    _extract_cavadalabs_key_context,
    _key_info_value,
    _metadata_to_dict,
    _optional_str,
)
from litellm.proxy.cavadalabs.key_context_schema import (
    _raise_if_cavadalabs_key_context_schema_exception,
)


def _extract_existing_cavadalabs_key_context(
    key_info: Any,
) -> Tuple[Optional[str], Optional[str]]:
    metadata_company_id, metadata_project_id = _extract_cavadalabs_key_context(
        _metadata_to_dict(_key_info_value(key_info, "metadata"))
    )
    top_level_company_id = _optional_str(
        _key_info_value(key_info, CAVADALABS_COMPANY_METADATA_KEY)
    )
    top_level_project_id = _optional_str(
        _key_info_value(key_info, CAVADALABS_PROJECT_METADATA_KEY)
    )
    return (
        top_level_company_id or metadata_company_id,
        top_level_project_id or metadata_project_id,
    )


async def _find_cavadalabs_project_by_litellm_team_id(
    prisma_client: Any,
    team_id: str,
) -> Optional[Any]:
    try:
        return await prisma_client.db.cavadalabs_projecttable.find_unique(
            where={"litellm_team_id": team_id}
        )
    except Exception as exc:
        _raise_if_cavadalabs_key_context_schema_exception(
            "cavadalabs_projecttable.litellm_team_id", exc
        )
        raise


async def _find_cavadalabs_company_by_litellm_organization_id(
    prisma_client: Any,
    organization_id: str,
) -> Optional[Any]:
    try:
        return await prisma_client.db.cavadalabs_companytable.find_unique(
            where={"litellm_organization_id": organization_id}
        )
    except Exception as exc:
        _raise_if_cavadalabs_key_context_schema_exception(
            "cavadalabs_companytable.litellm_organization_id", exc
        )
        raise


async def _resolve_existing_cavadalabs_key_context(
    prisma_client: Any,
    key_info: Any,
) -> Optional[Tuple[Optional[str], Optional[str]]]:
    company_id, project_id = _extract_existing_cavadalabs_key_context(key_info)
    team_id = _optional_str(_key_info_value(key_info, "team_id"))
    organization_id = _optional_str(_key_info_value(key_info, "organization_id"))

    if team_id is not None:
        project = await _find_cavadalabs_project_by_litellm_team_id(
            prisma_client=prisma_client,
            team_id=team_id,
        )
        if project is not None:
            mapped_project_id = _optional_str(getattr(project, "project_id", None))
            mapped_company_id = _optional_str(getattr(project, "company_id", None))
            if (
                project_id is not None
                and mapped_project_id is not None
                and project_id != mapped_project_id
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error": (
                            "CavadaLabs key metadata project does not match its "
                            "internal compatibility team mapping."
                        )
                    },
                )
            if (
                company_id is not None
                and mapped_company_id is not None
                and company_id != mapped_company_id
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error": (
                            "CavadaLabs key metadata company does not match its "
                            "internal compatibility project mapping."
                        )
                    },
                )
            project_id = project_id or mapped_project_id
            company_id = company_id or mapped_company_id

    if organization_id is not None:
        company = await _find_cavadalabs_company_by_litellm_organization_id(
            prisma_client=prisma_client,
            organization_id=organization_id,
        )
        if company is not None:
            mapped_company_id = _optional_str(getattr(company, "company_id", None))
            if (
                company_id is not None
                and mapped_company_id is not None
                and company_id != mapped_company_id
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error": (
                            "CavadaLabs key company context does not match its "
                            "internal compatibility organization mapping."
                        )
                    },
                )
            company_id = company_id or mapped_company_id

    if company_id is None and project_id is None:
        return None
    return company_id, project_id


async def _can_access_existing_cavadalabs_key(
    prisma_client: Any,
    key_info: Any,
    user_api_key_dict: UserAPIKeyAuth,
    *,
    require_admin: bool,
) -> Optional[bool]:
    resolved_context = await _resolve_existing_cavadalabs_key_context(
        prisma_client=prisma_client,
        key_info=key_info,
    )
    if resolved_context is None:
        return None
    company_id, project_id = resolved_context

    from litellm.proxy.cavadalabs.access_control import (
        authorize_cavadalabs_company_project_access,
    )

    try:
        await authorize_cavadalabs_company_project_access(
            prisma_client.db,
            company_id=company_id,
            project_id=project_id,
            user_api_key_dict=user_api_key_dict,
            action="manage" if require_admin else "view",
        )
        return True
    except HTTPException as exc:
        detail = getattr(exc, "detail", None)
        if (
            exc.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            and isinstance(detail, dict)
            and detail.get("schema_status") == "missing_schema"
        ):
            raise
        return False


async def _require_existing_cavadalabs_key_admin_access(
    prisma_client: Any,
    key_info: Any,
    user_api_key_dict: UserAPIKeyAuth,
    *,
    route: str,
) -> Optional[bool]:
    can_access = await _can_access_existing_cavadalabs_key(
        prisma_client=prisma_client,
        key_info=key_info,
        user_api_key_dict=user_api_key_dict,
        require_admin=True,
    )
    if can_access is None:
        return None
    if can_access is True:
        return True
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error": (
                f"Only CavadaLabs company/project admins can call {route} "
                "for this Company/Project-scoped key."
            )
        },
    )
