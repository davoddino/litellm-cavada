from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request

from litellm.proxy import proxy_server
from litellm.proxy._types import (
    LiteLLM_TeamTable,
    LitellmUserRoles,
    Member,
    TeamMemberAddRequest,
    UserAPIKeyAuth,
)
from litellm.proxy.management_endpoints import team_endpoints


def _row(**data):
    row = SimpleNamespace(**data)
    row.model_dump = lambda exclude_none=True: (
        {key: value for key, value in data.items() if value is not None}
        if exclude_none
        else dict(data)
    )
    return row


def _company_row(**kwargs):
    return _row(
        company_id=kwargs.pop("company_id", "company-1"),
        legal_name=kwargs.pop("legal_name", "ACME"),
        billing_name=None,
        vat_tax_id=None,
        billing_address={},
        admin_emails=[],
        plan="production",
        status="active",
        monthly_budget=None,
        metadata={},
        retention_policy={},
        default_guardrail_policy=None,
        default_billing_settings={},
        litellm_organization_id=kwargs.pop("litellm_organization_id", "org-company-1"),
        created_at=datetime.now(timezone.utc),
        created_by="admin",
        updated_at=datetime.now(timezone.utc),
        updated_by="admin",
        **kwargs,
    )


def _project_row(**kwargs):
    return _row(
        project_id=kwargs.pop("project_id", "project-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        name=kwargs.pop("name", "Support"),
        status="production",
        allowed_models=[],
        allowed_rag_collections=[],
        default_chatbot_settings={},
        default_guardrail_policy=None,
        budget=None,
        retention_policy_override={},
        metadata={},
        litellm_team_id=kwargs.pop("litellm_team_id", "team-project-1"),
        created_at=datetime.now(timezone.utc),
        created_by="admin",
        updated_at=datetime.now(timezone.utc),
        updated_by="admin",
        **kwargs,
    )


class _TeamDelegate:
    async def find_unique(self, **_kwargs):
        return LiteLLM_TeamTable(
            team_id="team-project-1",
            team_alias="Compatibility Team",
            organization_id="org-company-1",
            members_with_roles=[],
        )


class _ProjectDelegate:
    async def find_unique(self, *, where):
        if where == {"litellm_team_id": "team-project-1"}:
            return _project_row()
        if where == {"project_id": "project-1"}:
            return _project_row()
        return None


class _CompanyDelegate:
    async def find_unique(self, *, where):
        if where == {"company_id": "company-1"}:
            return _company_row()
        return None


class _ProjectMemberDelegate:
    def __init__(self, role):
        self.role = role

    async def find_unique(self, *, where):
        user_id = where["project_id_user_id"]["user_id"]
        if user_id == "project-member":
            return SimpleNamespace(role=self.role)
        return None


class _EmptyFindUniqueDelegate:
    async def find_unique(self, **_kwargs):
        return None


class _EmptyFindManyDelegate:
    async def find_many(self, **_kwargs):
        return []


class _TeamInfoPrisma:
    def __init__(self, *, project_member_role):
        self.db = SimpleNamespace(
            litellm_teamtable=_TeamDelegate(),
            litellm_teammembership=_EmptyFindManyDelegate(),
            cavadalabs_projecttable=_ProjectDelegate(),
            cavadalabs_companytable=_CompanyDelegate(),
            cavadalabs_projectmembertable=_ProjectMemberDelegate(project_member_role),
            cavadalabs_companymembertable=_EmptyFindUniqueDelegate(),
            litellm_organizationmembership=_EmptyFindUniqueDelegate(),
            litellm_usertable=_EmptyFindUniqueDelegate(),
        )

    async def get_data(self, **_kwargs):
        return []


async def _not_legacy_org_admin(**_kwargs):
    return False


def _project_member_auth():
    return UserAPIKeyAuth(
        user_id="project-member",
        user_role=LitellmUserRoles.INTERNAL_USER.value,
    )


@pytest.mark.asyncio
async def test_team_info_allows_native_cavadalabs_project_viewer_without_legacy_team_membership(
    monkeypatch,
):
    prisma_client = _TeamInfoPrisma(project_member_role="viewer")
    monkeypatch.setattr(proxy_server, "prisma_client", prisma_client)
    monkeypatch.setattr(
        team_endpoints, "_is_user_org_admin_for_team", _not_legacy_org_admin
    )

    response = await team_endpoints.team_info(
        http_request=Request(scope={"type": "http", "path": "/team/info"}),
        team_id="team-project-1",
        user_api_key_dict=_project_member_auth(),
    )

    assert response["team_id"] == "team-project-1"
    assert response["team_info"].team_id == "team-project-1"
    assert response["keys"] == []
    assert response["team_memberships"] == []


@pytest.mark.asyncio
async def test_team_manage_allows_native_cavadalabs_project_admin_without_legacy_team_membership(
    monkeypatch,
):
    prisma_client = _TeamInfoPrisma(project_member_role="project_admin")
    monkeypatch.setattr(
        team_endpoints, "_is_user_org_admin_for_team", _not_legacy_org_admin
    )

    await team_endpoints._verify_team_access(
        team_obj=LiteLLM_TeamTable(
            team_id="team-project-1",
            organization_id="org-company-1",
            members_with_roles=[],
        ),
        user_api_key_dict=_project_member_auth(),
        db=prisma_client.db,
    )


@pytest.mark.asyncio
async def test_team_member_add_allows_native_cavadalabs_project_admin_without_legacy_team_membership(
    monkeypatch,
):
    prisma_client = _TeamInfoPrisma(project_member_role="project_admin")
    monkeypatch.setattr(
        team_endpoints, "_is_user_org_admin_for_team", _not_legacy_org_admin
    )

    await team_endpoints._validate_team_member_add_permissions(
        user_api_key_dict=_project_member_auth(),
        complete_team_data=LiteLLM_TeamTable(
            team_id="team-project-1",
            organization_id="org-company-1",
            members_with_roles=[],
        ),
        data=TeamMemberAddRequest(
            team_id="team-project-1",
            member=Member(user_id="new-user", role="user"),
        ),
        prisma_client=prisma_client,
    )


@pytest.mark.asyncio
async def test_team_manage_denies_native_cavadalabs_project_viewer(
    monkeypatch,
):
    prisma_client = _TeamInfoPrisma(project_member_role="viewer")
    monkeypatch.setattr(
        team_endpoints, "_is_user_org_admin_for_team", _not_legacy_org_admin
    )

    with pytest.raises(HTTPException) as exc_info:
        await team_endpoints._verify_team_access(
            team_obj=LiteLLM_TeamTable(
                team_id="team-project-1",
                organization_id="org-company-1",
                members_with_roles=[],
            ),
            user_api_key_dict=_project_member_auth(),
            db=prisma_client.db,
        )

    assert exc_info.value.status_code == 403
