from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, Request

from litellm.proxy import proxy_server
from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.management_endpoints import cavadalabs_project_endpoints
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsProjectMemberCreateRequest,
    CavadaLabsProjectMemberRole,
    CavadaLabsProjectMemberUpdateRequest,
)


def _row(**kwargs):
    defaults = {
        "created_at": datetime(2026, 5, 15, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 5, 15, tzinfo=timezone.utc),
        "created_by": "admin-user",
        "updated_by": "admin-user",
    }
    return SimpleNamespace(**{**defaults, **kwargs})


def _project(**kwargs):
    return _row(
        project_id=kwargs.pop("project_id", "project-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        name=kwargs.pop("name", "Support"),
        status=kwargs.pop("status", "production"),
        allowed_models=[],
        allowed_rag_collections=[],
        default_chatbot_settings={},
        default_guardrail_policy=None,
        budget=None,
        retention_policy_override={},
        metadata={},
        litellm_team_id=kwargs.pop("litellm_team_id", "team-project-1"),
        **kwargs,
    )


def _company(**kwargs):
    return _row(
        company_id=kwargs.pop("company_id", "company-1"),
        legal_name=kwargs.pop("legal_name", "ACME Spa"),
        billing_name=None,
        vat_tax_id=None,
        billing_address={},
        admin_emails=[],
        plan="production",
        status="active",
        monthly_budget=100.0,
        metadata={},
        retention_policy={},
        default_guardrail_policy=None,
        default_billing_settings={},
        litellm_organization_id=kwargs.pop("litellm_organization_id", "org-company-1"),
        **kwargs,
    )


def _project_member(user_id: str, role: str = "operator"):
    return _row(
        membership_id=f"membership-{user_id}",
        project_id="project-1",
        user_id=user_id,
        role=role,
    )


def _auth(user_id: str = "admin-user") -> UserAPIKeyAuth:
    return UserAPIKeyAuth(user_id=user_id, user_role=LitellmUserRoles.INTERNAL_USER)


def _request() -> Request:
    return Request(
        scope={"type": "http", "path": "/cavadalabs/projects/project-1/members"}
    )


def _prisma(project_access_role: str = "project_admin"):
    db = MagicMock()
    db.cavadalabs_projecttable = MagicMock()
    db.cavadalabs_companytable = MagicMock()
    db.cavadalabs_projectmembertable = MagicMock()
    db.cavadalabs_companymembertable = MagicMock()
    db.cavadalabs_auditlogtable = MagicMock()
    db.litellm_teamtable = MagicMock()
    db.litellm_usertable = MagicMock()
    db.litellm_teammembership = MagicMock()
    db.litellm_organizationmembership = MagicMock()

    db.cavadalabs_projecttable.find_unique = AsyncMock(return_value=_project())
    db.cavadalabs_companytable.find_unique = AsyncMock(return_value=_company())
    db.cavadalabs_companymembertable.find_unique = AsyncMock(return_value=None)
    db.litellm_organizationmembership.find_unique = AsyncMock(return_value=None)
    db.litellm_organizationmembership.find_many = AsyncMock(return_value=[])
    db.litellm_teamtable.find_unique = AsyncMock(
        return_value=SimpleNamespace(team_id="team-project-1", members_with_roles=[])
    )
    db.litellm_teamtable.update = AsyncMock()
    db.litellm_usertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            user_id="user-2", user_email="user2@example.com", teams=[]
        )
    )
    db.litellm_usertable.update = AsyncMock()
    db.litellm_teammembership.delete_many = AsyncMock()
    db.cavadalabs_auditlogtable.create = AsyncMock()
    db.cavadalabs_projectmembertable.find_unique = AsyncMock(
        return_value=_project_member("admin-user", project_access_role)
    )
    db.cavadalabs_projectmembertable.find_many = AsyncMock(
        return_value=[_project_member("user-2", "operator")]
    )
    db.cavadalabs_projectmembertable.upsert = AsyncMock(
        return_value=_project_member("user-2", "operator")
    )
    db.cavadalabs_projectmembertable.update = AsyncMock(
        return_value=_project_member("user-2", "viewer")
    )
    db.cavadalabs_projectmembertable.delete_many = AsyncMock(return_value=1)
    return SimpleNamespace(db=db)


@pytest.mark.asyncio
async def test_project_member_list_uses_native_project_access(monkeypatch):
    prisma = _prisma(project_access_role="viewer")
    monkeypatch.setattr(proxy_server, "prisma_client", prisma)

    response = await cavadalabs_project_endpoints.list_project_members(
        project_id="project-1",
        http_request=_request(),
        user_api_key_dict=_auth(),
    )

    assert response.project_id == "project-1"
    assert response.company_id == "company-1"
    assert response.members[0].user_id == "user-2"
    assert response.members[0].role == CavadaLabsProjectMemberRole.OPERATOR


@pytest.mark.asyncio
async def test_project_admin_can_add_native_project_member_without_org_admin(
    monkeypatch,
):
    prisma = _prisma(project_access_role="project_admin")
    monkeypatch.setattr(proxy_server, "prisma_client", prisma)

    response = await cavadalabs_project_endpoints.upsert_project_member(
        project_id="project-1",
        data=CavadaLabsProjectMemberCreateRequest(user_id="user-2", role="operator"),
        http_request=_request(),
        user_api_key_dict=_auth(),
    )

    assert response.user_id == "user-2"
    prisma.db.cavadalabs_projectmembertable.upsert.assert_awaited_once()
    upsert_call = prisma.db.cavadalabs_projectmembertable.upsert.await_args.kwargs
    assert upsert_call["where"]["project_id_user_id"] == {
        "project_id": "project-1",
        "user_id": "user-2",
    }
    assert upsert_call["data"]["create"]["role"] == "operator"
    prisma.db.litellm_teamtable.update.assert_awaited_once()
    team_update = prisma.db.litellm_teamtable.update.await_args.kwargs
    assert team_update["where"] == {"team_id": "team-project-1"}
    assert '"user_id": "user-2"' in team_update["data"]["members_with_roles"]


@pytest.mark.asyncio
async def test_project_viewer_cannot_mutate_project_members(monkeypatch):
    prisma = _prisma(project_access_role="viewer")
    monkeypatch.setattr(proxy_server, "prisma_client", prisma)

    with pytest.raises(HTTPException) as exc_info:
        await cavadalabs_project_endpoints.upsert_project_member(
            project_id="project-1",
            data=CavadaLabsProjectMemberCreateRequest(
                user_id="user-2", role="operator"
            ),
            http_request=_request(),
            user_api_key_dict=_auth(),
        )

    assert exc_info.value.status_code == 403
    prisma.db.cavadalabs_projectmembertable.upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_project_member_update_and_delete_update_native_and_compat_memberships(
    monkeypatch,
):
    prisma = _prisma(project_access_role="project_admin")
    prisma.db.cavadalabs_projectmembertable.find_unique = AsyncMock(
        side_effect=[
            _project_member("admin-user", "project_admin"),
            _project_member("user-2", "operator"),
            _project_member("admin-user", "project_admin"),
            _project_member("user-2", "viewer"),
        ]
    )
    monkeypatch.setattr(proxy_server, "prisma_client", prisma)

    updated = await cavadalabs_project_endpoints.update_project_member(
        project_id="project-1",
        user_id="user-2",
        data=CavadaLabsProjectMemberUpdateRequest(role="viewer"),
        http_request=_request(),
        user_api_key_dict=_auth(),
    )
    deleted = await cavadalabs_project_endpoints.delete_project_member(
        project_id="project-1",
        user_id="user-2",
        http_request=_request(),
        user_api_key_dict=_auth(),
    )

    assert updated.role == CavadaLabsProjectMemberRole.VIEWER
    assert deleted.deleted is True
    prisma.db.cavadalabs_projectmembertable.update.assert_awaited_once()
    prisma.db.cavadalabs_projectmembertable.delete_many.assert_awaited_once_with(
        where={"project_id": "project-1", "user_id": "user-2"}
    )
    assert prisma.db.litellm_teamtable.update.await_count == 2
    prisma.db.litellm_teammembership.delete_many.assert_awaited_once_with(
        where={"team_id": "team-project-1", "user_id": "user-2"}
    )
