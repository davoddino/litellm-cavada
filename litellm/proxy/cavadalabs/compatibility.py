from __future__ import annotations

from typing import Any, Dict, Optional

from litellm.proxy._types import LitellmUserRoles, Member, UserAPIKeyAuth
from litellm.proxy.cavadalabs.dispatcher_shared import _actor_user_id
from litellm.proxy.cavadalabs.prisma_json import serialize_prisma_json_fields
from litellm.proxy.management_helpers.team_member_permission_checks import (
    TeamMemberPermissionChecks,
)
from litellm.proxy.management_helpers.utils import get_new_internal_user_defaults
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsCompanyResponse,
    CavadaLabsProjectResponse,
)


CAVADALABS_COMPAT_METADATA_KEY = "cavadalabs"


def company_compat_organization_id(company_id: str) -> str:
    return f"cavadalabs-company-{company_id}"


def project_compat_team_id(project_id: str) -> str:
    return f"cavadalabs-project-{project_id}"


def _row_value(row: Any, field_name: str) -> Any:
    if isinstance(row, dict):
        return row.get(field_name)
    return getattr(row, field_name, None)


def _metadata_with_cavadalabs_context(
    metadata: Optional[Dict[str, Any]],
    *,
    company_id: str,
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    merged_metadata = dict(metadata or {})
    cavadalabs_metadata = dict(
        merged_metadata.get(CAVADALABS_COMPAT_METADATA_KEY) or {}
    )
    cavadalabs_metadata["company_id"] = company_id
    if project_id is not None:
        cavadalabs_metadata["project_id"] = project_id
    cavadalabs_metadata["compatibility_mapping"] = True
    merged_metadata[CAVADALABS_COMPAT_METADATA_KEY] = cavadalabs_metadata
    return merged_metadata


async def _create_compat_budget(
    db: Any,
    *,
    actor: str,
    max_budget: Optional[float],
) -> str:
    data: Dict[str, Any] = {
        "created_by": actor,
        "updated_by": actor,
    }
    if max_budget is not None:
        data["max_budget"] = max_budget
    row = await db.litellm_budgettable.create(data=data)
    return _row_value(row, "budget_id")


async def _sync_company_admin_email_memberships(
    db: Any,
    *,
    organization_id: str,
    admin_emails: list[str],
) -> None:
    for admin_email in admin_emails:
        existing_user = await db.litellm_usertable.find_first(
            where={"user_email": admin_email}
        )
        user_id = _row_value(existing_user, "user_id") if existing_user else admin_email
        await db.litellm_usertable.upsert(
            where={"user_id": user_id},
            data={
                "update": {"user_email": admin_email},
                "create": {
                    "user_id": user_id,
                    "user_email": admin_email,
                    "models": [],
                    "teams": [],
                },
            },
        )
        await db.litellm_organizationmembership.upsert(
            where={
                "user_id_organization_id": {
                    "user_id": user_id,
                    "organization_id": organization_id,
                }
            },
            data={
                "update": {"user_role": LitellmUserRoles.ORG_ADMIN.value},
                "create": {
                    "user_id": user_id,
                    "organization_id": organization_id,
                    "user_role": LitellmUserRoles.ORG_ADMIN.value,
                },
            },
        )


async def ensure_company_compat_organization(
    prisma_client: Any,
    *,
    company: CavadaLabsCompanyResponse,
    user_api_key_dict: UserAPIKeyAuth,
) -> str:
    db = prisma_client.db
    actor = _actor_user_id(user_api_key_dict)
    organization_id = company.litellm_organization_id or company_compat_organization_id(
        company.company_id
    )
    existing_organization = await db.litellm_organizationtable.find_unique(
        where={"organization_id": organization_id}
    )
    metadata = _metadata_with_cavadalabs_context(
        _row_value(existing_organization, "metadata") if existing_organization else {},
        company_id=company.company_id,
    )

    if existing_organization is None:
        budget_id = await _create_compat_budget(
            db,
            actor=actor,
            max_budget=company.monthly_budget,
        )
        await db.litellm_organizationtable.create(
            data=serialize_prisma_json_fields(
                {
                    "organization_id": organization_id,
                    "organization_alias": company.legal_name,
                    "budget_id": budget_id,
                    "metadata": metadata,
                    "models": [],
                    "created_by": actor,
                    "updated_by": actor,
                }
            )
        )
    else:
        await db.litellm_organizationtable.update(
            where={"organization_id": organization_id},
            data=serialize_prisma_json_fields(
                {
                    "organization_alias": company.legal_name,
                    "metadata": metadata,
                    "updated_by": actor,
                }
            ),
        )

    if company.litellm_organization_id != organization_id:
        await db.cavadalabs_companytable.update(
            where={"company_id": company.company_id},
            data={"litellm_organization_id": organization_id},
        )

    await _sync_company_admin_email_memberships(
        db,
        organization_id=organization_id,
        admin_emails=company.admin_emails,
    )
    return organization_id


def _team_member_payload(member: Member) -> Dict[str, Any]:
    return member.model_dump(exclude_none=True)


async def _ensure_creator_team_membership(
    prisma_client: Any,
    *,
    team_id: str,
    user_api_key_dict: UserAPIKeyAuth,
) -> None:
    if user_api_key_dict.user_id is None:
        return
    new_user_defaults = get_new_internal_user_defaults(
        user_id=user_api_key_dict.user_id
    )
    await prisma_client.db.litellm_usertable.upsert(
        where={"user_id": user_api_key_dict.user_id},
        data={
            "update": {"teams": {"push": [team_id]}},
            "create": {"teams": [team_id], **new_user_defaults},
        },
    )


async def ensure_project_compat_team(
    prisma_client: Any,
    *,
    company: CavadaLabsCompanyResponse,
    project: CavadaLabsProjectResponse,
    user_api_key_dict: UserAPIKeyAuth,
) -> str:
    db = prisma_client.db
    team_id = project.litellm_team_id or project_compat_team_id(project.project_id)
    existing_team = await db.litellm_teamtable.find_unique(where={"team_id": team_id})
    existing_members = _row_value(existing_team, "members_with_roles") or []
    creator_member = (
        Member(role="admin", user_id=user_api_key_dict.user_id)
        if user_api_key_dict.user_id is not None
        else None
    )
    members_with_roles = list(existing_members or [])
    should_sync_creator_membership = False
    if creator_member is not None and not any(
        _row_value(member, "user_id") == user_api_key_dict.user_id
        for member in members_with_roles
    ):
        members_with_roles.append(_team_member_payload(creator_member))
        should_sync_creator_membership = True

    metadata = _metadata_with_cavadalabs_context(
        _row_value(existing_team, "metadata") if existing_team else {},
        company_id=project.company_id,
        project_id=project.project_id,
    )
    team_data = serialize_prisma_json_fields(
        {
            "team_alias": project.name,
            "organization_id": company.litellm_organization_id,
            "models": project.allowed_models,
            "max_budget": project.budget,
            "blocked": project.status == "archived",
            "metadata": metadata,
            "members_with_roles": members_with_roles,
        },
        json_fields={"metadata", "members_with_roles"},
    )

    if existing_team is None:
        team_data["team_member_permissions"] = (
            TeamMemberPermissionChecks.default_team_member_permissions()
        )
        await db.litellm_teamtable.create(
            data={
                "team_id": team_id,
                "members": (
                    [user_api_key_dict.user_id]
                    if user_api_key_dict.user_id is not None
                    else []
                ),
                **team_data,
            }
        )
    else:
        await db.litellm_teamtable.update(
            where={"team_id": team_id},
            data=team_data,
        )

    if project.litellm_team_id != team_id:
        await db.cavadalabs_projecttable.update(
            where={"project_id": project.project_id},
            data={"litellm_team_id": team_id},
        )

    if should_sync_creator_membership:
        await _ensure_creator_team_membership(
            prisma_client,
            team_id=team_id,
            user_api_key_dict=user_api_key_dict,
        )
    return team_id
