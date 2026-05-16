from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal, Optional, Set

from fastapi import HTTPException, status

from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsCompanyResponse,
    CavadaLabsProjectResponse,
)

_COMPANY_ROLE_BY_LITELLM_ORG_ROLE = {
    LitellmUserRoles.ORG_ADMIN.value: "company_admin",
    LitellmUserRoles.INTERNAL_USER.value: "operator",
    LitellmUserRoles.INTERNAL_USER_VIEW_ONLY.value: "viewer",
}
_PROJECT_ROLE_BY_LITELLM_TEAM_ROLE = {
    "admin": "project_admin",
    "user": "operator",
    "viewer": "viewer",
}
_COMPANY_ADMIN_ROLES = {"company_admin"}
_COMPANY_VISIBLE_ROLES = {"company_admin", "operator", "viewer"}
_PROJECT_ADMIN_ROLES = {"project_admin"}
_PROJECT_VISIBLE_ROLES = {"project_admin", "operator", "viewer"}
_NATIVE_COMPANY_MEMBER_ROLES = _COMPANY_VISIBLE_ROLES
_NATIVE_PROJECT_MEMBER_ROLES = _PROJECT_VISIBLE_ROLES
_COMPANY_ROLE_PRIORITY = ("company_admin", "operator", "viewer")


@dataclass(frozen=True)
class CavadaLabsAccessScope:
    company_ids: Optional[Set[str]]
    project_ids: Optional[Set[str]]


@dataclass(frozen=True)
class CavadaLabsAccessInfo:
    role: Optional[str]
    can_view: bool
    can_manage: bool


@dataclass(frozen=True)
class CavadaLabsAuthorizedAccess:
    company: Optional[CavadaLabsCompanyResponse]
    project: Optional[CavadaLabsProjectResponse]
    access_info: CavadaLabsAccessInfo


@dataclass(frozen=True)
class _NativeMembershipScope:
    ids: Set[str]
    schema_missing: bool


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


def _company_role_from_organization_membership(membership: Any) -> Optional[str]:
    user_role = _row_value(membership, "user_role")
    if hasattr(user_role, "value"):
        user_role = user_role.value
    return _COMPANY_ROLE_BY_LITELLM_ORG_ROLE.get(user_role)


def _company_role_from_native_membership(membership: Any) -> Optional[str]:
    role = _row_value(membership, "role")
    if role in _NATIVE_COMPANY_MEMBER_ROLES:
        return role
    return None


def _project_role_from_team_member(member: Any) -> Optional[str]:
    role = _row_value(member, "role")
    return _PROJECT_ROLE_BY_LITELLM_TEAM_ROLE.get(role)


def _project_role_from_native_membership(membership: Any) -> Optional[str]:
    role = _row_value(membership, "role")
    if role in _NATIVE_PROJECT_MEMBER_ROLES:
        return role
    return None


def _parent_company_role_from_project_role(role: Optional[str]) -> Optional[str]:
    if role == "viewer":
        return "viewer"
    if role in {"project_admin", "operator"}:
        return "operator"
    return None


def _strongest_company_role(roles: Iterable[str]) -> Optional[str]:
    role_set = set(roles)
    for role in _COMPANY_ROLE_PRIORITY:
        if role in role_set:
            return role
    return None


def _company_role_allows(role: Optional[str], *, require_admin: bool) -> bool:
    if role is None:
        return False
    if require_admin:
        return role in _COMPANY_ADMIN_ROLES
    return role in _COMPANY_VISIBLE_ROLES


def _project_role_allows(role: Optional[str], *, require_admin: bool) -> bool:
    if role is None:
        return False
    if require_admin:
        return role in _PROJECT_ADMIN_ROLES
    return role in _PROJECT_VISIBLE_ROLES


def _company_access_info_for_role(role: Optional[str]) -> CavadaLabsAccessInfo:
    return CavadaLabsAccessInfo(
        role=role,
        can_view=role in _COMPANY_VISIBLE_ROLES,
        can_manage=role in _COMPANY_ADMIN_ROLES,
    )


def _project_access_info_for_role(role: Optional[str]) -> CavadaLabsAccessInfo:
    return CavadaLabsAccessInfo(
        role=role,
        can_view=role in _PROJECT_VISIBLE_ROLES or role in _COMPANY_VISIBLE_ROLES,
        can_manage=role in _PROJECT_ADMIN_ROLES or role in _COMPANY_ADMIN_ROLES,
    )


def _admin_company_access_info(
    user_api_key_dict: UserAPIKeyAuth,
) -> Optional[CavadaLabsAccessInfo]:
    if is_cavadalabs_mutation_admin(user_api_key_dict):
        return _company_access_info_for_role("company_admin")
    if is_cavadalabs_admin_view(user_api_key_dict):
        return _company_access_info_for_role("viewer")
    return None


def _admin_project_access_info(
    user_api_key_dict: UserAPIKeyAuth,
) -> Optional[CavadaLabsAccessInfo]:
    if is_cavadalabs_mutation_admin(user_api_key_dict):
        return _project_access_info_for_role("project_admin")
    if is_cavadalabs_admin_view(user_api_key_dict):
        return _project_access_info_for_role("viewer")
    return None


def _csv_values(value: Optional[str]) -> list[str]:
    if not isinstance(value, str):
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _missing_schema_error(table_name: str, exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "error": (
                f"CavadaLabs access control schema is missing required table "
                f"delegate '{table_name}'. Run Prisma migrations before using "
                "Company/Project scoped access control."
            ),
            "schema_status": "missing_schema",
            "missing_schema": [table_name],
            "migration_command": "uv run prisma migrate deploy",
            "cause": str(exc),
        },
    )


async def _find_company_by_id(
    db: Any, company_id: str
) -> Optional[CavadaLabsCompanyResponse]:
    try:
        row = await db.cavadalabs_companytable.find_unique(
            where={"company_id": company_id}
        )
    except AttributeError as exc:
        raise _missing_schema_error("cavadalabs_companytable", exc) from exc
    if row is None:
        return None
    return CavadaLabsCompanyResponse.model_validate(_row_to_dict(row))


async def _find_project_by_id(
    db: Any, project_id: str
) -> Optional[CavadaLabsProjectResponse]:
    try:
        row = await db.cavadalabs_projecttable.find_unique(
            where={"project_id": project_id}
        )
    except AttributeError as exc:
        raise _missing_schema_error("cavadalabs_projecttable", exc) from exc
    if row is None:
        return None
    return CavadaLabsProjectResponse.model_validate(_row_to_dict(row))


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
        if not _company_role_allows(
            _company_role_from_organization_membership(membership),
            require_admin=require_org_admin,
        ):
            continue
        organization_id = _row_value(membership, "organization_id")
        if organization_id:
            organization_ids.add(organization_id)
    return organization_ids


async def _native_company_scope_for_user(
    db: Any,
    user_api_key_dict: UserAPIKeyAuth,
    *,
    require_admin: bool,
) -> _NativeMembershipScope:
    if user_api_key_dict.user_id is None:
        return _NativeMembershipScope(ids=set(), schema_missing=False)
    try:
        rows = await db.cavadalabs_companymembertable.find_many(
            where={"user_id": user_api_key_dict.user_id}
        )
    except AttributeError:
        return _NativeMembershipScope(ids=set(), schema_missing=True)
    except TypeError:
        return _NativeMembershipScope(ids=set(), schema_missing=False)

    company_ids: Set[str] = set()
    for row in rows:
        role = _company_role_from_native_membership(row)
        if not _company_role_allows(role, require_admin=require_admin):
            continue
        company_id = _row_value(row, "company_id")
        if company_id:
            company_ids.add(company_id)
    return _NativeMembershipScope(ids=company_ids, schema_missing=False)


async def _native_company_ids_for_user(
    db: Any,
    user_api_key_dict: UserAPIKeyAuth,
    *,
    require_admin: bool,
) -> Set[str]:
    return (
        await _native_company_scope_for_user(
            db,
            user_api_key_dict,
            require_admin=require_admin,
        )
    ).ids


async def _native_project_scope_for_user(
    db: Any,
    user_api_key_dict: UserAPIKeyAuth,
    *,
    require_admin: bool,
) -> _NativeMembershipScope:
    if user_api_key_dict.user_id is None:
        return _NativeMembershipScope(ids=set(), schema_missing=False)
    try:
        rows = await db.cavadalabs_projectmembertable.find_many(
            where={"user_id": user_api_key_dict.user_id}
        )
    except AttributeError:
        return _NativeMembershipScope(ids=set(), schema_missing=True)
    except TypeError:
        return _NativeMembershipScope(ids=set(), schema_missing=False)

    project_ids: Set[str] = set()
    for row in rows:
        role = _project_role_from_native_membership(row)
        if not _project_role_allows(role, require_admin=require_admin):
            continue
        project_id = _row_value(row, "project_id")
        if project_id:
            project_ids.add(project_id)
    return _NativeMembershipScope(ids=project_ids, schema_missing=False)


async def _native_project_ids_for_user(
    db: Any,
    user_api_key_dict: UserAPIKeyAuth,
    *,
    require_admin: bool,
) -> Set[str]:
    return (
        await _native_project_scope_for_user(
            db,
            user_api_key_dict,
            require_admin=require_admin,
        )
    ).ids


async def _native_project_parent_company_access_info_for_user(
    db: Any,
    *,
    company_id: str,
    user_api_key_dict: UserAPIKeyAuth,
) -> tuple[CavadaLabsAccessInfo, bool]:
    if user_api_key_dict.user_id is None:
        return _company_access_info_for_role(None), False
    try:
        memberships = await db.cavadalabs_projectmembertable.find_many(
            where={"user_id": user_api_key_dict.user_id}
        )
    except AttributeError:
        return _company_access_info_for_role(None), True
    except TypeError:
        return _company_access_info_for_role(None), False

    parent_company_roles_by_project: dict[str, str] = {}
    for membership in memberships:
        parent_company_role = _parent_company_role_from_project_role(
            _project_role_from_native_membership(membership)
        )
        if parent_company_role is None:
            continue
        project_id = _row_value(membership, "project_id")
        if project_id:
            parent_company_roles_by_project[project_id] = parent_company_role
    if not parent_company_roles_by_project:
        return _company_access_info_for_role(None), False

    project_rows = await db.cavadalabs_projecttable.find_many(
        where={
            "project_id": {"in": list(parent_company_roles_by_project.keys())},
            "company_id": company_id,
        }
    )
    parent_company_roles = [
        parent_company_roles_by_project[project_id]
        for row in project_rows
        if _row_value(row, "company_id") == company_id
        and (project_id := _row_value(row, "project_id"))
        in parent_company_roles_by_project
    ]
    return (
        _company_access_info_for_role(_strongest_company_role(parent_company_roles)),
        False,
    )


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
    native_company_scope = await _native_company_scope_for_user(
        db, user_api_key_dict, require_admin=False
    )
    company_ids = set(native_company_scope.ids)
    native_project_scope = await _native_project_scope_for_user(
        db, user_api_key_dict, require_admin=False
    )
    if native_project_scope.ids:
        project_rows = await db.cavadalabs_projecttable.find_many(
            where={"project_id": {"in": list(native_project_scope.ids)}}
        )
        for row in project_rows:
            company_id = _row_value(row, "company_id")
            if company_id:
                company_ids.add(company_id)
    organization_ids = await _user_organization_ids(
        db, user_api_key_dict, require_org_admin=False
    )
    company_ids.update(await _companies_for_organization_ids(db, organization_ids))
    team_ids = await _user_team_ids(db, user_api_key_dict)
    if team_ids:
        project_rows = await db.cavadalabs_projecttable.find_many(
            where={"litellm_team_id": {"in": list(team_ids)}}
        )
        for row in project_rows:
            company_id = _row_value(row, "company_id")
            if company_id:
                company_ids.add(company_id)
    if not company_ids and native_company_scope.schema_missing:
        raise _missing_schema_error(
            "cavadalabs_companymembertable",
            AttributeError("missing CavadaLabs native company membership delegate"),
        )
    if not company_ids and native_project_scope.schema_missing:
        raise _missing_schema_error(
            "cavadalabs_projectmembertable",
            AttributeError("missing CavadaLabs native project membership delegate"),
        )
    return company_ids


async def visible_company_wide_ids_for_user(
    db: Any,
    user_api_key_dict: UserAPIKeyAuth,
) -> Optional[Set[str]]:
    """Return companies whose full company-level data the caller may read.

    Project membership is intentionally excluded here. A project member can read
    that project, but a company-only usage/key scope covers sibling projects too.
    """
    if is_cavadalabs_admin_view(user_api_key_dict):
        return None
    native_company_scope = await _native_company_scope_for_user(
        db, user_api_key_dict, require_admin=False
    )
    company_ids = set(native_company_scope.ids)
    organization_ids = await _user_organization_ids(
        db, user_api_key_dict, require_org_admin=False
    )
    company_ids.update(await _companies_for_organization_ids(db, organization_ids))
    if not company_ids and native_company_scope.schema_missing:
        raise _missing_schema_error(
            "cavadalabs_companymembertable",
            AttributeError("missing CavadaLabs native company membership delegate"),
        )
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
    native_company_scope = await _native_company_scope_for_user(
        db, user_api_key_dict, require_admin=False
    )
    native_company_ids = set(native_company_scope.ids)
    if company_id is not None:
        native_company_ids = {company_id} if company_id in native_company_ids else set()
    if native_company_ids:
        rows = await db.cavadalabs_projecttable.find_many(
            where={"company_id": {"in": list(native_company_ids)}}
        )
        project_ids.update(
            project_id
            for row in rows
            if (project_id := _row_value(row, "project_id")) is not None
        )

    native_project_scope = await _native_project_scope_for_user(
        db, user_api_key_dict, require_admin=False
    )
    native_project_ids = set(native_project_scope.ids)
    if native_project_ids:
        project_where: dict[str, Any] = {"project_id": {"in": list(native_project_ids)}}
        if company_id is not None:
            project_where["company_id"] = company_id
        rows = await db.cavadalabs_projecttable.find_many(where=project_where)
        project_ids.update(
            project_id
            for row in rows
            if (project_id := _row_value(row, "project_id")) is not None
        )

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
    if not project_ids and native_project_scope.schema_missing:
        raise _missing_schema_error(
            "cavadalabs_projectmembertable",
            AttributeError("missing CavadaLabs native project membership delegate"),
        )
    if not project_ids and native_company_scope.schema_missing:
        raise _missing_schema_error(
            "cavadalabs_companymembertable",
            AttributeError("missing CavadaLabs native company membership delegate"),
        )
    return project_ids


async def _native_company_access_info_for_user(
    db: Any,
    *,
    company_id: str,
    user_api_key_dict: UserAPIKeyAuth,
) -> tuple[CavadaLabsAccessInfo, bool]:
    if user_api_key_dict.user_id is None:
        return _company_access_info_for_role(None), False
    try:
        membership = await db.cavadalabs_companymembertable.find_unique(
            where={
                "company_id_user_id": {
                    "company_id": company_id,
                    "user_id": user_api_key_dict.user_id,
                }
            }
        )
    except AttributeError:
        return _company_access_info_for_role(None), True
    except TypeError:
        return _company_access_info_for_role(None), False
    return (
        _company_access_info_for_role(_company_role_from_native_membership(membership)),
        False,
    )


async def _native_project_access_info_for_user(
    db: Any,
    *,
    project_id: str,
    user_api_key_dict: UserAPIKeyAuth,
) -> tuple[CavadaLabsAccessInfo, bool]:
    if user_api_key_dict.user_id is None:
        return _project_access_info_for_role(None), False
    try:
        membership = await db.cavadalabs_projectmembertable.find_unique(
            where={
                "project_id_user_id": {
                    "project_id": project_id,
                    "user_id": user_api_key_dict.user_id,
                }
            }
        )
    except AttributeError:
        return _project_access_info_for_role(None), True
    except TypeError:
        return _project_access_info_for_role(None), False
    return (
        _project_access_info_for_role(_project_role_from_native_membership(membership)),
        False,
    )


async def company_access_info_for_user(
    db: Any,
    *,
    company: CavadaLabsCompanyResponse,
    user_api_key_dict: UserAPIKeyAuth,
) -> CavadaLabsAccessInfo:
    admin_info = _admin_company_access_info(user_api_key_dict)
    if admin_info is not None:
        return admin_info

    native_access_info, native_schema_missing = (
        await _native_company_access_info_for_user(
            db,
            company_id=company.company_id,
            user_api_key_dict=user_api_key_dict,
        )
    )
    if native_access_info.can_view:
        return native_access_info

    native_project_parent_company_info, native_project_schema_missing = (
        await _native_project_parent_company_access_info_for_user(
            db,
            company_id=company.company_id,
            user_api_key_dict=user_api_key_dict,
        )
    )
    if native_project_parent_company_info.can_view:
        return native_project_parent_company_info

    if company.litellm_organization_id and user_api_key_dict.user_id:
        membership = await db.litellm_organizationmembership.find_unique(
            where={
                "user_id_organization_id": {
                    "user_id": user_api_key_dict.user_id,
                    "organization_id": company.litellm_organization_id,
                }
            }
        )
        role = _company_role_from_organization_membership(membership)
        access_info = _company_access_info_for_role(role)
        if access_info.can_view:
            return access_info

    visible_company_ids = await visible_company_ids_for_user(db, user_api_key_dict)
    if visible_company_ids is not None and company.company_id in visible_company_ids:
        return _company_access_info_for_role("operator")
    if native_schema_missing:
        raise _missing_schema_error(
            "cavadalabs_companymembertable",
            AttributeError("missing CavadaLabs native company membership delegate"),
        )
    if native_project_schema_missing:
        raise _missing_schema_error(
            "cavadalabs_projectmembertable",
            AttributeError("missing CavadaLabs native project membership delegate"),
        )
    return _company_access_info_for_role(None)


async def company_wide_access_info_for_user(
    db: Any,
    *,
    company: CavadaLabsCompanyResponse,
    user_api_key_dict: UserAPIKeyAuth,
) -> CavadaLabsAccessInfo:
    """Company access for full company-scoped data surfaces.

    This does not use project-derived parent-company access. It is used by
    company-level usage/key filters where widening a project member to the
    parent company would expose sibling project data.
    """
    admin_info = _admin_company_access_info(user_api_key_dict)
    if admin_info is not None:
        return admin_info

    native_access_info, native_schema_missing = (
        await _native_company_access_info_for_user(
            db,
            company_id=company.company_id,
            user_api_key_dict=user_api_key_dict,
        )
    )
    if native_access_info.can_view:
        return native_access_info

    if company.litellm_organization_id and user_api_key_dict.user_id:
        membership = await db.litellm_organizationmembership.find_unique(
            where={
                "user_id_organization_id": {
                    "user_id": user_api_key_dict.user_id,
                    "organization_id": company.litellm_organization_id,
                }
            }
        )
        access_info = _company_access_info_for_role(
            _company_role_from_organization_membership(membership)
        )
        if access_info.can_view:
            return access_info

    if native_schema_missing:
        raise _missing_schema_error(
            "cavadalabs_companymembertable",
            AttributeError("missing CavadaLabs native company membership delegate"),
        )
    return _company_access_info_for_role(None)


async def project_access_info_for_user(
    db: Any,
    *,
    project: CavadaLabsProjectResponse,
    user_api_key_dict: UserAPIKeyAuth,
) -> CavadaLabsAccessInfo:
    admin_info = _admin_project_access_info(user_api_key_dict)
    if admin_info is not None:
        return admin_info

    native_project_info, native_project_schema_missing = (
        await _native_project_access_info_for_user(
            db,
            project_id=project.project_id,
            user_api_key_dict=user_api_key_dict,
        )
    )
    if native_project_info.can_view:
        return native_project_info

    native_company_schema_missing = False
    company = await _find_company_by_id(db, project.company_id)
    if company is not None:
        native_company_info, native_company_schema_missing = (
            await _native_company_access_info_for_user(
                db,
                company_id=company.company_id,
                user_api_key_dict=user_api_key_dict,
            )
        )
        if native_company_info.can_view:
            return _project_access_info_for_role(native_company_info.role)

    if project.litellm_team_id and user_api_key_dict.user_id:
        team_row = await db.litellm_teamtable.find_unique(
            where={"team_id": project.litellm_team_id}
        )
        members_with_roles = _row_value(team_row, "members_with_roles") or []
        for member in members_with_roles:
            if _row_value(member, "user_id") != user_api_key_dict.user_id:
                continue
            role = _project_role_from_team_member(member)
            access_info = _project_access_info_for_role(role)
            if access_info.can_view:
                return access_info

        if project.litellm_team_id in (await _user_team_ids(db, user_api_key_dict)):
            return _project_access_info_for_role("operator")

    if company is not None:
        company_access_info = await company_access_info_for_user(
            db,
            company=company,
            user_api_key_dict=user_api_key_dict,
        )
        if company_access_info.can_view:
            return _project_access_info_for_role(company_access_info.role)

    if native_project_schema_missing:
        raise _missing_schema_error(
            "cavadalabs_projectmembertable",
            AttributeError("missing CavadaLabs native project membership delegate"),
        )
    if native_company_schema_missing:
        raise _missing_schema_error(
            "cavadalabs_companymembertable",
            AttributeError("missing CavadaLabs native company membership delegate"),
        )
    return _project_access_info_for_role(None)


async def with_company_access_metadata(
    db: Any,
    *,
    company: CavadaLabsCompanyResponse,
    user_api_key_dict: UserAPIKeyAuth,
) -> CavadaLabsCompanyResponse:
    access_info = await company_access_info_for_user(
        db,
        company=company,
        user_api_key_dict=user_api_key_dict,
    )
    return company.model_copy(
        update={
            "cavadalabs_access_role": access_info.role,
            "cavadalabs_can_manage": access_info.can_manage,
        }
    )


async def with_project_access_metadata(
    db: Any,
    *,
    project: CavadaLabsProjectResponse,
    user_api_key_dict: UserAPIKeyAuth,
) -> CavadaLabsProjectResponse:
    access_info = await project_access_info_for_user(
        db,
        project=project,
        user_api_key_dict=user_api_key_dict,
    )
    return project.model_copy(
        update={
            "cavadalabs_access_role": access_info.role,
            "cavadalabs_can_manage": access_info.can_manage,
        }
    )


async def require_company_access(
    db: Any,
    *,
    company_id: str,
    user_api_key_dict: UserAPIKeyAuth,
    require_admin: bool = False,
) -> CavadaLabsCompanyResponse:
    access = await authorize_cavadalabs_company_project_access(
        db,
        company_id=company_id,
        project_id=None,
        user_api_key_dict=user_api_key_dict,
        action="manage" if require_admin else "view",
    )
    if access.company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": f"Company '{company_id}' not found"},
        )
    return access.company


async def require_company_wide_access(
    db: Any,
    *,
    company_id: str,
    user_api_key_dict: UserAPIKeyAuth,
    require_admin: bool = False,
) -> CavadaLabsCompanyResponse:
    company = await _find_company_by_id(db, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": f"Company '{company_id}' not found"},
        )
    access_info = await company_wide_access_info_for_user(
        db,
        company=company,
        user_api_key_dict=user_api_key_dict,
    )
    if _company_role_allows(access_info.role, require_admin=require_admin):
        return company
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error": "You do not have full-scope access to this CavadaLabs company"
        },
    )


async def require_project_access(
    db: Any,
    *,
    project_id: str,
    user_api_key_dict: UserAPIKeyAuth,
    require_admin: bool = False,
) -> CavadaLabsProjectResponse:
    access = await authorize_cavadalabs_company_project_access(
        db,
        company_id=None,
        project_id=project_id,
        user_api_key_dict=user_api_key_dict,
        action="manage" if require_admin else "view",
    )
    if access.project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": f"Project '{project_id}' not found"},
        )
    return access.project


async def authorize_cavadalabs_company_project_access(
    db: Any,
    *,
    user_api_key_dict: UserAPIKeyAuth,
    company_id: Optional[str],
    project_id: Optional[str],
    action: Literal["view", "manage"] = "view",
) -> CavadaLabsAuthorizedAccess:
    if company_id is None and project_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "A CavadaLabs company_id or project_id is required"},
        )

    requires_admin = action == "manage"
    company: Optional[CavadaLabsCompanyResponse] = None
    project: Optional[CavadaLabsProjectResponse] = None

    if project_id is not None:
        project = await _find_project_by_id(db, project_id)
        if project is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"Project '{project_id}' not found"},
            )
        if company_id is not None and project.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "project_id must belong to company_id",
                    "company_id": company_id,
                    "project_id": project_id,
                },
            )
        company_id = project.company_id
        access_info = await project_access_info_for_user(
            db,
            project=project,
            user_api_key_dict=user_api_key_dict,
        )
        if (requires_admin and access_info.can_manage) or (
            not requires_admin and access_info.can_view
        ):
            if company_id is not None:
                company = await _find_company_by_id(db, company_id)
            return CavadaLabsAuthorizedAccess(
                company=company,
                project=project,
                access_info=access_info,
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "You do not have access to this CavadaLabs project"},
        )

    assert company_id is not None
    company = await _find_company_by_id(db, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": f"Company '{company_id}' not found"},
        )
    access_info = await company_access_info_for_user(
        db,
        company=company,
        user_api_key_dict=user_api_key_dict,
    )
    if (requires_admin and access_info.can_manage) or (
        not requires_admin and access_info.can_view
    ):
        return CavadaLabsAuthorizedAccess(
            company=company,
            project=None,
            access_info=access_info,
        )

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"error": "You do not have access to this CavadaLabs company"},
    )


async def require_company_admin_access(
    db: Any,
    *,
    company_id: str,
    user_api_key_dict: UserAPIKeyAuth,
) -> CavadaLabsCompanyResponse:
    return await require_company_access(
        db,
        company_id=company_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=True,
    )


async def require_project_admin_access(
    db: Any,
    *,
    project_id: str,
    user_api_key_dict: UserAPIKeyAuth,
) -> CavadaLabsProjectResponse:
    return await require_project_access(
        db,
        project_id=project_id,
        user_api_key_dict=user_api_key_dict,
        require_admin=True,
    )


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
        if organization_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": f"Company '{cavadalabs_company_id}' is missing its LiteLLM compatibility organization"
                },
            )
    if cavadalabs_project_id is not None:
        project = await require_project_access(
            db,
            project_id=cavadalabs_project_id,
            user_api_key_dict=user_api_key_dict,
        )
        team_id = project.litellm_team_id
        if team_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": f"Project '{cavadalabs_project_id}' is missing its LiteLLM compatibility team"
                },
            )
    return organization_id, team_id


async def resolve_cavadalabs_user_list_filters(
    db: Any,
    *,
    user_api_key_dict: UserAPIKeyAuth,
    cavadalabs_company_ids: Optional[str],
    cavadalabs_project_ids: Optional[str],
) -> tuple[list[str], list[str]]:
    organization_ids: list[str] = []
    for company_id in _csv_values(cavadalabs_company_ids):
        company = await require_company_access(
            db,
            company_id=company_id,
            user_api_key_dict=user_api_key_dict,
            require_admin=False,
        )
        if company.litellm_organization_id is not None:
            organization_ids.append(company.litellm_organization_id)

    team_ids: list[str] = []
    for project_id in _csv_values(cavadalabs_project_ids):
        project = await require_project_access(
            db,
            project_id=project_id,
            user_api_key_dict=user_api_key_dict,
            require_admin=False,
        )
        if project.litellm_team_id is not None:
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
        for company_id in requested_ids:
            await authorize_cavadalabs_company_project_access(
                db,
                company_id=company_id,
                project_id=None,
                user_api_key_dict=user_api_key_dict,
                action="view",
            )
        return requested_ids or None

    if requested_ids:
        for company_id in requested_ids:
            await require_company_wide_access(
                db,
                company_id=company_id,
                user_api_key_dict=user_api_key_dict,
            )
        return requested_ids

    visible_company_ids = await visible_company_wide_ids_for_user(db, user_api_key_dict)
    allowed_ids = visible_company_ids or set()
    return sorted(allowed_ids)


async def resolve_cavadalabs_project_usage_scope(
    db: Any,
    *,
    user_api_key_dict: UserAPIKeyAuth,
    requested_project_ids: Optional[str],
) -> Optional[list[str]]:
    requested_ids = _csv_values(requested_project_ids)
    if is_cavadalabs_admin_view(user_api_key_dict):
        for project_id in requested_ids:
            await authorize_cavadalabs_company_project_access(
                db,
                company_id=None,
                project_id=project_id,
                user_api_key_dict=user_api_key_dict,
                action="view",
            )
        return requested_ids or None

    if requested_ids:
        for project_id in requested_ids:
            await authorize_cavadalabs_company_project_access(
                db,
                company_id=None,
                project_id=project_id,
                user_api_key_dict=user_api_key_dict,
                action="view",
            )
        return requested_ids

    visible_project_ids = await visible_project_ids_for_user(db, user_api_key_dict)
    allowed_ids = visible_project_ids or set()
    return sorted(allowed_ids)
