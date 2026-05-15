from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.cavadalabs.access_control import (
    require_company_access,
    require_project_access,
    resolve_cavadalabs_company_usage_scope,
    resolve_cavadalabs_project_usage_scope,
    resolve_cavadalabs_team_list_filters,
    resolve_cavadalabs_user_list_filters,
    visible_company_ids_for_user,
    visible_project_ids_for_user,
)


def _row(**kwargs):
    defaults = {
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "created_by": "admin-user",
        "updated_by": "admin-user",
    }
    return SimpleNamespace(**{**defaults, **kwargs})


def _company(**kwargs):
    return _row(
        company_id=kwargs.pop("company_id", "company-1"),
        litellm_organization_id=kwargs.pop("litellm_organization_id", "org-company-1"),
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
        **kwargs,
    )


def _project(**kwargs):
    return _row(
        project_id=kwargs.pop("project_id", "project-1"),
        litellm_team_id=kwargs.pop("litellm_team_id", "team-project-1"),
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
        **kwargs,
    )


def _db():
    db = MagicMock()
    db.cavadalabs_companytable = MagicMock()
    db.cavadalabs_projecttable = MagicMock()
    db.litellm_organizationmembership = MagicMock()
    db.litellm_teamtable = MagicMock()
    db.litellm_usertable = MagicMock()
    db.cavadalabs_companytable.find_unique = AsyncMock(return_value=_company())
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[])
    db.cavadalabs_projecttable.find_unique = AsyncMock(return_value=_project())
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[])
    db.litellm_organizationmembership.find_unique = AsyncMock(return_value=None)
    db.litellm_organizationmembership.find_many = AsyncMock(return_value=[])
    db.litellm_teamtable.find_unique = AsyncMock(return_value=None)
    db.litellm_usertable.find_unique = AsyncMock(return_value=None)
    return db


def _internal_user(user_id: str = "user-1") -> UserAPIKeyAuth:
    return UserAPIKeyAuth(
        user_id=user_id,
        user_role=LitellmUserRoles.INTERNAL_USER,
    )


@pytest.mark.asyncio
async def test_company_access_allows_company_org_admin():
    db = _db()
    db.litellm_organizationmembership.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            user_id="user-1",
            organization_id="org-company-1",
            user_role=LitellmUserRoles.ORG_ADMIN.value,
        )
    )

    company = await require_company_access(
        db,
        company_id="company-1",
        user_api_key_dict=_internal_user(),
        require_admin=True,
    )

    assert company.company_id == "company-1"


@pytest.mark.asyncio
async def test_company_access_rejects_regular_member_for_admin_operation():
    db = _db()
    db.litellm_organizationmembership.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            user_id="user-1",
            organization_id="org-company-1",
            user_role=LitellmUserRoles.INTERNAL_USER.value,
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        await require_company_access(
            db,
            company_id="company-1",
            user_api_key_dict=_internal_user(),
            require_admin=True,
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_project_access_allows_project_team_admin():
    db = _db()
    db.litellm_teamtable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            team_id="team-project-1",
            members_with_roles=[{"user_id": "user-1", "role": "admin"}],
        )
    )

    project = await require_project_access(
        db,
        project_id="project-1",
        user_api_key_dict=_internal_user(),
        require_admin=True,
    )

    assert project.project_id == "project-1"


@pytest.mark.asyncio
async def test_visible_scopes_include_org_memberships_and_project_team_memberships():
    db = _db()
    db.litellm_organizationmembership.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                user_id="user-1",
                organization_id="org-company-1",
                user_role=LitellmUserRoles.INTERNAL_USER.value,
            )
        ]
    )
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[_company()])
    db.litellm_usertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(user_id="user-1", teams=["team-project-2"])
    )
    db.cavadalabs_projecttable.find_many = AsyncMock(
        side_effect=[
            [_project(project_id="project-2", company_id="company-2")],
            [_project(project_id="project-1")],
            [_project(project_id="project-2", company_id="company-2")],
        ]
    )

    company_ids = await visible_company_ids_for_user(db, _internal_user())
    project_ids = await visible_project_ids_for_user(db, _internal_user())

    assert company_ids == {"company-1", "company-2"}
    assert project_ids == {"project-1", "project-2"}


@pytest.mark.asyncio
async def test_user_list_filter_resolves_company_and_project_to_internal_scope():
    db = _db()
    db.cavadalabs_companytable.find_unique = AsyncMock(return_value=_company())
    db.cavadalabs_projecttable.find_unique = AsyncMock(return_value=_project())
    db.litellm_organizationmembership.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            user_id="user-1",
            organization_id="org-company-1",
            user_role=LitellmUserRoles.ORG_ADMIN.value,
        )
    )
    db.litellm_teamtable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            team_id="team-project-1",
            members_with_roles=[{"user_id": "user-1", "role": "admin"}],
        )
    )

    organization_ids, team_ids = await resolve_cavadalabs_user_list_filters(
        db,
        user_api_key_dict=_internal_user(),
        cavadalabs_company_ids="company-1",
        cavadalabs_project_ids="project-1",
    )

    assert organization_ids == ["org-company-1"]
    assert team_ids == ["team-project-1"]


@pytest.mark.asyncio
async def test_team_list_filter_resolves_company_project_context():
    db = _db()
    db.cavadalabs_companytable.find_unique = AsyncMock(return_value=_company())
    db.cavadalabs_projecttable.find_unique = AsyncMock(return_value=_project())
    auth = UserAPIKeyAuth(
        user_id="admin-user",
        user_role=LitellmUserRoles.PROXY_ADMIN_VIEW_ONLY,
    )

    organization_id, team_id = await resolve_cavadalabs_team_list_filters(
        db,
        user_api_key_dict=auth,
        cavadalabs_company_id="company-1",
        cavadalabs_project_id="project-1",
    )

    assert organization_id == "org-company-1"
    assert team_id == "team-project-1"


@pytest.mark.asyncio
async def test_company_usage_scope_limits_internal_user_to_visible_companies():
    db = _db()
    db.litellm_organizationmembership.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                user_id="user-1",
                organization_id="org-company-1",
                user_role=LitellmUserRoles.INTERNAL_USER.value,
            )
        ]
    )
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[_company()])

    company_ids = await resolve_cavadalabs_company_usage_scope(
        db,
        user_api_key_dict=_internal_user(),
        requested_company_ids=None,
    )

    assert company_ids == ["company-1"]


@pytest.mark.asyncio
async def test_company_usage_scope_rejects_requested_company_outside_scope():
    db = _db()
    db.litellm_organizationmembership.find_many = AsyncMock(return_value=[])
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[])

    with pytest.raises(HTTPException) as exc_info:
        await resolve_cavadalabs_company_usage_scope(
            db,
            user_api_key_dict=_internal_user(),
            requested_company_ids="company-2",
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_project_usage_scope_limits_internal_user_to_visible_projects():
    db = _db()
    db.litellm_organizationmembership.find_many = AsyncMock(return_value=[])
    db.litellm_usertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(user_id="user-1", teams=["team-project-1"])
    )
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[_project()])

    project_ids = await resolve_cavadalabs_project_usage_scope(
        db,
        user_api_key_dict=_internal_user(),
        requested_project_ids=None,
    )

    assert project_ids == ["project-1"]
