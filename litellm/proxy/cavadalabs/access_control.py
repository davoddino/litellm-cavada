from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional, Set

from fastapi import HTTPException, status

from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsCompanyResponse,
    CavadaLabsProjectResponse,
)


@dataclass(frozen=True)
class CavadaLabsAccessScope:
    company_ids: Optional[Set[str]]
    project_ids: Optional[Set[str]]


def is_cavadalabs_admin_view(user_api_key_dict: UserAPIKeyAuth) -> bool:
    return user_api_key_dict.user_role in {
        LitellmUserRoles.PROXY_ADMIN,
        LitellmUserRoles.PROXY_ADMIN.value,
        LitellmUserRoles.PROXY_ADMIN_VIEW_ONLY,
        LitellmUserRoles.PROXY_ADMIN_VIEW_ONLY.value,
    }


def is_cavadalabs_mutation_admin(user_api_key_dict: UserAPIKeyAuth) -> bool:
    return user_api_key_dict.user_role in {
        LitellmUserRoles.PROXY_ADMIN,
        LitellmUserRoles.PROXY_ADMIN.value,
    }


def _row_value(row: Any, field_name: str) -> Any:
    if isinstance(row, dict):
        return row.get(field_name)
    return getattr(row, field_name, None)


def _row_to_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    model_dump = getattr(row, "model_dump", None)
    if callable(model_dump):
        return dict(model_dump())
    return dict(getattr(row, "__dict__", {}))


def _member_has_role(member: Any, *, user_id: str, role: str) -> bool:
    return (
        _row_value(member, "user_id") == user_id and _row_value(member, "role") == role
    )


def _csv_values(value: Optional[str]) -> list[str]:
    if not isinstance(value, str):
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


async def _user_team_ids(db: Any, user_api_key_dict: UserAPIKeyAuth) -> Set[str]:
    team_ids: Set[str] = set()
    if user_api_key_dict.team_id:
        team_ids.add(user_api_key_dict.team_id)
    if user_api_key_dict.user_id is None:
        return team_ids
    user_row = await db.litellm_usertable.find_unique(
        where={"user_id": user_api_key_dict.user_id}
    )
    for team_id in _row_value(user_row, "teams") or []:
        if team_id:
            team_ids.add(team_id)
    return team_ids


async def _user_organization_ids(
    db: Any,
    user_api_key_dict: UserAPIKeyAuth,
    *,
    require_org_admin: bool,
) -> Set[str]:
    if user_api_key_dict.user_id is None:
        return set()
    memberships = await db.litellm_organizationmembership.find_many(
        where={"user_id": user_api_key_dict.user_id}
    )
    organization_ids: Set[str] = set()
    for membership in memberships:
        if require_org_admin and _row_value(membership, "user_role") != (
            LitellmUserRoles.ORG_ADMIN.value
        ):
            continue
        organization_id = _row_value(membership, "organization_id")
        if organization_id:
            organization_ids.add(organization_id)
    return organization_ids


async def _companies_for_organization_ids(
    db: Any,
    organization_ids: Iterable[str],
) -> Set[str]:
    organization_ids = [org_id for org_id in organization_ids if org_id]
    if not organization_ids:
        return set()
    rows = await db.cavadalabs_companytable.find_many(
        where={"litellm_organization_id": {"in": organization_ids}}
    )
    return {
        company_id
        for row in rows
        if (company_id := _row_value(row, "company_id")) is not None
    }


async def _projects_for_team_ids(db: Any, team_ids: Iterable[str]) -> Set[str]:
    team_ids = [team_id for team_id in team_ids if team_id]
    if not team_ids:
        return set()
    rows = await db.cavadalabs_projecttable.find_many(
        where={"litellm_team_id": {"in": team_ids}}
    )
    return {
        project_id
        for row in rows
        if (project_id := _row_value(row, "project_id")) is not None
    }


async def visible_company_ids_for_user(
    db: Any,
    user_api_key_dict: UserAPIKeyAuth,
) -> Optional[Set[str]]:
    if is_cavadalabs_admin_view(user_api_key_dict):
        return None
    organization_ids = await _user_organization_ids(
        db, user_api_key_dict, require_org_admin=False
    )
    company_ids = await _companies_for_organization_ids(db, organization_ids)
    team_ids = await _user_team_ids(db, user_api_key_dict)
    if team_ids:
        project_rows = await db.cavadalabs_projecttable.find_many(
            where={"litellm_team_id": {"in": list(team_ids)}}
        )
        for row in project_rows:
            company_id = _row_value(row, "company_id")
            if company_id:
                company_ids.add(company_id)
    return company_ids


async def visible_project_ids_for_user(
    db: Any,
    user_api_key_dict: UserAPIKeyAuth,
    *,
    company_id: Optional[str] = None,
) -> Optional[Set[str]]:
    if is_cavadalabs_admin_view(user_api_key_dict):
        return None

    project_ids: Set[str] = set()
    organization_ids = await _user_organization_ids(
        db, user_api_key_dict, require_org_admin=False
    )
    company_ids = await _companies_for_organization_ids(db, organization_ids)
    if company_id is not None:
        company_ids = {company_id} if company_id in company_ids else set()
    if company_ids:
        rows = await db.cavadalabs_projecttable.find_many(
            where={"company_id": {"in": list(company_ids)}}
        )
        project_ids.update(
            project_id
            for row in rows
            if (project_id := _row_value(row, "project_id")) is not None
        )

    team_ids = await _user_team_ids(db, user_api_key_dict)
    if team_ids:
        team_where: dict[str, Any] = {"litellm_team_id": {"in": list(team_ids)}}
        if company_id is not None:
            team_where["company_id"] = company_id
        rows = await db.cavadalabs_projecttable.find_many(where=team_where)
        project_ids.update(
            project_id
            for row in rows
            if (project_id := _row_value(row, "project_id")) is not None
        )
    return project_ids


async def require_company_access(
    db: Any,
    *,
    company_id: str,
    user_api_key_dict: UserAPIKeyAuth,
    require_admin: bool = False,
) -> CavadaLabsCompanyResponse:
    row = await db.cavadalabs_companytable.find_unique(where={"company_id": company_id})
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": f"Company '{company_id}' not found"},
        )
    company = CavadaLabsCompanyResponse.model_validate(_row_to_dict(row))
    if is_cavadalabs_mutation_admin(user_api_key_dict) or (
        is_cavadalabs_admin_view(user_api_key_dict) and not require_admin
    ):
        return company

    if company.litellm_organization_id and user_api_key_dict.user_id:
        membership = await db.litellm_organizationmembership.find_unique(
            where={
                "user_id_organization_id": {
                    "user_id": user_api_key_dict.user_id,
                    "organization_id": company.litellm_organization_id,
                }
            }
        )
        if membership is not None:
            if not require_admin or _row_value(membership, "user_role") == (
                LitellmUserRoles.ORG_ADMIN.value
            ):
                return company

    if not require_admin:
        visible_company_ids = await visible_company_ids_for_user(db, user_api_key_dict)
        if visible_company_ids is not None and company_id in visible_company_ids:
            return company

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"error": "You do not have access to this CavadaLabs company"},
    )


async def require_project_access(
    db: Any,
    *,
    project_id: str,
    user_api_key_dict: UserAPIKeyAuth,
    require_admin: bool = False,
) -> CavadaLabsProjectResponse:
    row = await db.cavadalabs_projecttable.find_unique(where={"project_id": project_id})
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": f"Project '{project_id}' not found"},
        )
    project = CavadaLabsProjectResponse.model_validate(_row_to_dict(row))
    if is_cavadalabs_mutation_admin(user_api_key_dict) or (
        is_cavadalabs_admin_view(user_api_key_dict) and not require_admin
    ):
        return project

    if project.litellm_team_id and user_api_key_dict.user_id:
        team_row = await db.litellm_teamtable.find_unique(
            where={"team_id": project.litellm_team_id}
        )
        members_with_roles = _row_value(team_row, "members_with_roles") or []
        if any(
            _member_has_role(
                member,
                user_id=user_api_key_dict.user_id,
                role="admin" if require_admin else _row_value(member, "role"),
            )
            for member in members_with_roles
        ):
            return project
        if not require_admin and project.litellm_team_id in (
            await _user_team_ids(db, user_api_key_dict)
        ):
            return project

    await require_company_access(
        db,
        company_id=project.company_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=require_admin,
    )
    return project


async def resolve_cavadalabs_team_list_filters(
    db: Any,
    *,
    user_api_key_dict: UserAPIKeyAuth,
    cavadalabs_company_id: Optional[str],
    cavadalabs_project_id: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    organization_id: Optional[str] = None
    team_id: Optional[str] = None
    if cavadalabs_company_id is not None:
        company = await require_company_access(
            db,
            company_id=cavadalabs_company_id,
            user_api_key_dict=user_api_key_dict,
        )
        organization_id = company.litellm_organization_id
    if cavadalabs_project_id is not None:
        project = await require_project_access(
            db,
            project_id=cavadalabs_project_id,
            user_api_key_dict=user_api_key_dict,
        )
        team_id = project.litellm_team_id
    return organization_id, team_id


async def resolve_cavadalabs_user_list_filters(
    db: Any,
    *,
    user_api_key_dict: UserAPIKeyAuth,
    cavadalabs_company_ids: Optional[str],
    cavadalabs_project_ids: Optional[str],
) -> tuple[list[str], list[str]]:
    organization_ids: list[str] = []
    require_scoped_admin = not is_cavadalabs_admin_view(user_api_key_dict)
    for company_id in _csv_values(cavadalabs_company_ids):
        company = await require_company_access(
            db,
            company_id=company_id,
            user_api_key_dict=user_api_key_dict,
            require_admin=require_scoped_admin,
        )
        if company.litellm_organization_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": f"Company '{company_id}' is missing its LiteLLM compatibility organization"
                },
            )
        organization_ids.append(company.litellm_organization_id)

    team_ids: list[str] = []
    for project_id in _csv_values(cavadalabs_project_ids):
        project = await require_project_access(
            db,
            project_id=project_id,
            user_api_key_dict=user_api_key_dict,
            require_admin=require_scoped_admin,
        )
        if project.litellm_team_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": f"Project '{project_id}' is missing its LiteLLM compatibility team"
                },
            )
        team_ids.append(project.litellm_team_id)
    return organization_ids, team_ids


async def resolve_cavadalabs_company_usage_scope(
    db: Any,
    *,
    user_api_key_dict: UserAPIKeyAuth,
    requested_company_ids: Optional[str],
) -> Optional[list[str]]:
    requested_ids = _csv_values(requested_company_ids)
    if is_cavadalabs_admin_view(user_api_key_dict):
        return requested_ids or None

    visible_company_ids = await visible_company_ids_for_user(db, user_api_key_dict)
    allowed_ids = visible_company_ids or set()
    if requested_ids:
        unauthorized_ids = sorted(set(requested_ids) - allowed_ids)
        if unauthorized_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "You do not have access to one or more requested CavadaLabs companies",
                    "company_ids": unauthorized_ids,
                },
            )
        return requested_ids
    return sorted(allowed_ids)


async def resolve_cavadalabs_project_usage_scope(
    db: Any,
    *,
    user_api_key_dict: UserAPIKeyAuth,
    requested_project_ids: Optional[str],
) -> Optional[list[str]]:
    requested_ids = _csv_values(requested_project_ids)
    if is_cavadalabs_admin_view(user_api_key_dict):
        return requested_ids or None

    visible_project_ids = await visible_project_ids_for_user(db, user_api_key_dict)
    allowed_ids = visible_project_ids or set()
    if requested_ids:
        unauthorized_ids = sorted(set(requested_ids) - allowed_ids)
        if unauthorized_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "You do not have access to one or more requested CavadaLabs projects",
                    "project_ids": unauthorized_ids,
                },
            )
        return requested_ids
    return sorted(allowed_ids)
