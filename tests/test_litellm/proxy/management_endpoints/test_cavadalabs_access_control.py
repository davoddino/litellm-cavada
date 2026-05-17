from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.cavadalabs.access_control import (
    authorize_cavadalabs_company_project_access,
    company_access_info_for_user,
    project_access_info_for_user,
    require_company_access,
    require_company_admin_access,
    require_project_access,
    require_project_admin_access,
    resolve_cavadalabs_company_usage_scope,
    resolve_cavadalabs_project_usage_scope,
    resolve_cavadalabs_team_list_filters,
    resolve_cavadalabs_user_list_filters,
    visible_company_ids_for_user,
    visible_project_ids_for_user,
    with_company_access_metadata,
    with_project_access_metadata,
)
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsCompanyResponse,
    CavadaLabsProjectResponse,
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


def _company_response(**kwargs) -> CavadaLabsCompanyResponse:
    return CavadaLabsCompanyResponse.model_validate(_company(**kwargs).__dict__)


def _project_response(**kwargs) -> CavadaLabsProjectResponse:
    return CavadaLabsProjectResponse.model_validate(_project(**kwargs).__dict__)


def test_cavadalabs_native_membership_migration_matches_schema_contract():
    repo_root = Path(__file__).parents[4]
    migration_path = (
        repo_root
        / "litellm-proxy-extras"
        / "litellm_proxy_extras"
        / "migrations"
        / "20260515150000_add_cavadalabs_native_memberships"
        / "migration.sql"
    )
    schema_path = repo_root / "litellm" / "proxy" / "schema.prisma"
    root_schema_path = repo_root / "schema.prisma"
    extras_schema_path = (
        repo_root / "litellm-proxy-extras" / "litellm_proxy_extras" / "schema.prisma"
    )
    sql = migration_path.read_text()
    schema = schema_path.read_text()
    root_schema = root_schema_path.read_text()
    extras_schema = extras_schema_path.read_text()

    for schema_text in (schema, root_schema, extras_schema):
        assert "model CavadaLabs_CompanyMemberTable" in schema_text
        assert "model CavadaLabs_ProjectMemberTable" in schema_text
        assert "@@unique([company_id, user_id])" in schema_text
        assert "@@unique([project_id, user_id])" in schema_text
        assert (
            "company_members            CavadaLabs_CompanyMemberTable[]" in schema_text
        )
        assert (
            "project_members            CavadaLabs_ProjectMemberTable[]" in schema_text
        )
        assert (
            "cavadalabs_company_memberships CavadaLabs_CompanyMemberTable[]"
            in schema_text
        )
        assert (
            "cavadalabs_project_memberships CavadaLabs_ProjectMemberTable[]"
            in schema_text
        )

    for table_name in [
        "CavadaLabs_CompanyMemberTable",
        "CavadaLabs_ProjectMemberTable",
    ]:
        assert f'CREATE TABLE IF NOT EXISTS "{table_name}"' in sql
        assert f'CONSTRAINT "{table_name}_pkey"' in sql

    for role in ["company_admin", "project_admin", "operator", "viewer"]:
        assert role in sql
    assert "CavadaLabs_CompanyMemberTable_role_check" in sql
    assert "CavadaLabs_ProjectMemberTable_role_check" in sql
    assert "ON DELETE CASCADE" in sql
    assert "LiteLLM_UserTable" in sql


def _db():
    db = MagicMock()
    db.cavadalabs_companytable = MagicMock()
    db.cavadalabs_projecttable = MagicMock()
    db.cavadalabs_companymembertable = MagicMock()
    db.cavadalabs_projectmembertable = MagicMock()
    db.litellm_organizationmembership = MagicMock()
    db.litellm_teamtable = MagicMock()
    db.litellm_usertable = MagicMock()
    db.cavadalabs_companytable.find_unique = AsyncMock(return_value=_company())
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[])
    db.cavadalabs_projecttable.find_unique = AsyncMock(return_value=_project())
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[_project()])
    db.cavadalabs_companymembertable.find_unique = AsyncMock(return_value=None)
    db.cavadalabs_companymembertable.find_many = AsyncMock(return_value=[])
    db.cavadalabs_projectmembertable.find_unique = AsyncMock(return_value=None)
    db.cavadalabs_projectmembertable.find_many = AsyncMock(return_value=[])
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


def _proxy_admin() -> UserAPIKeyAuth:
    return UserAPIKeyAuth(
        user_id="proxy-admin",
        user_role=LitellmUserRoles.PROXY_ADMIN,
    )


@pytest.mark.asyncio
async def test_authorize_company_project_access_allows_proxy_admin_and_validates_scope():
    db = _db()

    access = await authorize_cavadalabs_company_project_access(
        db,
        user_api_key_dict=_proxy_admin(),
        company_id="company-1",
        project_id="project-1",
        action="manage",
    )

    assert access.company is not None
    assert access.company.company_id == "company-1"
    assert access.project is not None
    assert access.project.project_id == "project-1"
    assert access.access_info.can_manage is True


@pytest.mark.asyncio
async def test_authorize_company_project_access_allows_native_company_admin():
    db = _db()
    db.cavadalabs_companymembertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            company_id="company-1",
            user_id="user-1",
            role="company_admin",
        )
    )

    access = await authorize_cavadalabs_company_project_access(
        db,
        user_api_key_dict=_internal_user(),
        company_id="company-1",
        project_id="project-1",
        action="manage",
    )

    assert access.project is not None
    assert access.access_info.role == "company_admin"
    assert access.access_info.can_manage is True


@pytest.mark.asyncio
async def test_authorize_company_project_access_allows_native_project_admin():
    db = _db()
    db.cavadalabs_projectmembertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            project_id="project-1",
            user_id="user-1",
            role="project_admin",
        )
    )

    access = await authorize_cavadalabs_company_project_access(
        db,
        user_api_key_dict=_internal_user(),
        company_id="company-1",
        project_id="project-1",
        action="manage",
    )

    assert access.project is not None
    assert access.access_info.role == "project_admin"
    assert access.access_info.can_manage is True


@pytest.mark.asyncio
async def test_authorize_company_project_access_limits_native_operator_to_view():
    db = _db()
    db.cavadalabs_projectmembertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            project_id="project-1",
            user_id="user-1",
            role="operator",
        )
    )

    access = await authorize_cavadalabs_company_project_access(
        db,
        user_api_key_dict=_internal_user(),
        company_id="company-1",
        project_id="project-1",
        action="view",
    )

    assert access.access_info.role == "operator"
    assert access.access_info.can_view is True
    assert access.access_info.can_manage is False

    with pytest.raises(HTTPException) as exc_info:
        await authorize_cavadalabs_company_project_access(
            db,
            user_api_key_dict=_internal_user(),
            company_id="company-1",
            project_id="project-1",
            action="manage",
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_authorize_company_project_access_rejects_unknown_native_role():
    db = _db()
    db.cavadalabs_projectmembertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            project_id="project-1",
            user_id="user-1",
            role="owner",
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        await authorize_cavadalabs_company_project_access(
            db,
            user_api_key_dict=_internal_user(),
            company_id="company-1",
            project_id="project-1",
            action="view",
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_authorize_company_project_access_allows_company_admin_to_manage_project():
    db = _db()
    db.litellm_organizationmembership.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            user_id="user-1",
            organization_id="org-company-1",
            user_role=LitellmUserRoles.ORG_ADMIN.value,
        )
    )

    access = await authorize_cavadalabs_company_project_access(
        db,
        user_api_key_dict=_internal_user(),
        company_id="company-1",
        project_id="project-1",
        action="manage",
    )

    assert access.project is not None
    assert access.project.project_id == "project-1"
    assert access.access_info.role == "company_admin"
    assert access.access_info.can_manage is True


@pytest.mark.asyncio
async def test_authorize_company_project_access_allows_project_admin_to_manage_project():
    db = _db()
    db.litellm_teamtable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            team_id="team-project-1",
            members_with_roles=[{"user_id": "user-1", "role": "admin"}],
        )
    )

    access = await authorize_cavadalabs_company_project_access(
        db,
        user_api_key_dict=_internal_user(),
        company_id="company-1",
        project_id="project-1",
        action="manage",
    )

    assert access.project is not None
    assert access.access_info.role == "project_admin"
    assert access.access_info.can_manage is True


@pytest.mark.asyncio
async def test_authorize_company_project_access_allows_operator_view_but_not_manage():
    db = _db()
    db.litellm_teamtable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            team_id="team-project-1",
            members_with_roles=[{"user_id": "user-1", "role": "user"}],
        )
    )

    access = await authorize_cavadalabs_company_project_access(
        db,
        user_api_key_dict=_internal_user(),
        company_id="company-1",
        project_id="project-1",
        action="view",
    )

    assert access.access_info.role == "operator"
    assert access.access_info.can_view is True
    assert access.access_info.can_manage is False

    with pytest.raises(HTTPException) as exc_info:
        await authorize_cavadalabs_company_project_access(
            db,
            user_api_key_dict=_internal_user(),
            company_id="company-1",
            project_id="project-1",
            action="manage",
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_authorize_company_project_access_rejects_cross_company_project_scope():
    db = _db()

    with pytest.raises(HTTPException) as exc_info:
        await authorize_cavadalabs_company_project_access(
            db,
            user_api_key_dict=_proxy_admin(),
            company_id="company-2",
            project_id="project-1",
            action="view",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["company_id"] == "company-2"
    assert exc_info.value.detail["project_id"] == "project-1"


@pytest.mark.asyncio
async def test_authorize_company_project_access_reports_missing_schema():
    db = SimpleNamespace()

    with pytest.raises(HTTPException) as exc_info:
        await authorize_cavadalabs_company_project_access(
            db,
            user_api_key_dict=_proxy_admin(),
            company_id=None,
            project_id="project-1",
            action="view",
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["schema_status"] == "missing_schema"
    assert "cavadalabs_projecttable" in exc_info.value.detail["missing_schema"]
    assert "prisma migrate deploy" in exc_info.value.detail["migration_command"]


@pytest.mark.asyncio
async def test_authorize_company_project_access_reports_missing_native_membership_schema():
    db = SimpleNamespace(
        cavadalabs_projecttable=SimpleNamespace(
            find_unique=AsyncMock(return_value=_project())
        ),
        cavadalabs_companytable=SimpleNamespace(
            find_unique=AsyncMock(return_value=_company()),
            find_many=AsyncMock(return_value=[]),
        ),
        cavadalabs_companymembertable=SimpleNamespace(
            find_unique=AsyncMock(return_value=None),
            find_many=AsyncMock(return_value=[]),
        ),
        litellm_teamtable=SimpleNamespace(find_unique=AsyncMock(return_value=None)),
        litellm_usertable=SimpleNamespace(find_unique=AsyncMock(return_value=None)),
        litellm_organizationmembership=SimpleNamespace(
            find_unique=AsyncMock(return_value=None),
            find_many=AsyncMock(return_value=[]),
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        await authorize_cavadalabs_company_project_access(
            db,
            user_api_key_dict=_internal_user(),
            company_id="company-1",
            project_id="project-1",
            action="view",
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["schema_status"] == "missing_schema"
    assert "cavadalabs_projectmembertable" in exc_info.value.detail["missing_schema"]
    assert "prisma migrate deploy" in exc_info.value.detail["migration_command"]


@pytest.mark.asyncio
async def test_visible_scopes_include_native_company_and_project_memberships():
    db = _db()
    db.cavadalabs_companymembertable.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                company_id="company-1",
                user_id="user-1",
                role="viewer",
            )
        ]
    )
    db.cavadalabs_projectmembertable.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                project_id="project-1",
                user_id="user-1",
                role="viewer",
            )
        ]
    )
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[_project()])

    assert await visible_company_ids_for_user(db, _internal_user()) == {"company-1"}
    assert await visible_project_ids_for_user(db, _internal_user()) == {"project-1"}


@pytest.mark.asyncio
async def test_visible_company_scope_includes_parent_company_for_native_project_member():
    db = _db()
    db.cavadalabs_companymembertable.find_many = AsyncMock(return_value=[])
    db.cavadalabs_projectmembertable.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                project_id="project-1",
                user_id="user-1",
                role="project_admin",
            )
        ]
    )
    db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[
            _project(project_id="project-1", company_id="company-1"),
        ]
    )

    assert await visible_company_ids_for_user(db, _internal_user()) == {"company-1"}


@pytest.mark.asyncio
async def test_company_access_allows_native_project_member_to_view_parent_company_only():
    db = _db()
    db.cavadalabs_projectmembertable.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                project_id="project-1",
                user_id="user-1",
                role="project_admin",
            )
        ]
    )
    db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[
            _project(project_id="project-1", company_id="company-1"),
        ]
    )

    company = await require_company_access(
        db,
        company_id="company-1",
        user_api_key_dict=_internal_user(),
        require_admin=False,
    )
    access_info = await company_access_info_for_user(
        db,
        company=_company_response(),
        user_api_key_dict=_internal_user(),
    )

    assert company.company_id == "company-1"
    assert access_info.role == "operator"
    assert access_info.can_view is True
    assert access_info.can_manage is False
    company_with_metadata = await with_company_access_metadata(
        db,
        company=_company_response(),
        user_api_key_dict=_internal_user(),
    )
    assert company_with_metadata.cavadalabs_access_role == "operator"
    assert company_with_metadata.cavadalabs_can_view_usage is False

    with pytest.raises(HTTPException) as exc_info:
        await require_company_access(
            db,
            company_id="company-1",
            user_api_key_dict=_internal_user(),
            require_admin=True,
        )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_company_access_denies_native_project_member_for_other_company():
    db = _db()
    db.cavadalabs_projectmembertable.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                project_id="project-2",
                user_id="user-1",
                role="project_admin",
            )
        ]
    )
    db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[
            _project(project_id="project-2", company_id="company-2"),
        ]
    )

    with pytest.raises(HTTPException) as exc_info:
        await require_company_access(
            db,
            company_id="company-1",
            user_api_key_dict=_internal_user(),
            require_admin=False,
        )

    assert exc_info.value.status_code == 403


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
async def test_company_admin_helper_allows_company_admin_product_role():
    db = _db()
    db.litellm_organizationmembership.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            user_id="user-1",
            organization_id="org-company-1",
            user_role=LitellmUserRoles.ORG_ADMIN.value,
        )
    )

    company = await require_company_admin_access(
        db,
        company_id="company-1",
        user_api_key_dict=_internal_user(),
    )

    assert company.company_id == "company-1"


@pytest.mark.asyncio
async def test_company_admin_helper_rejects_company_viewer_product_role():
    db = _db()
    db.litellm_organizationmembership.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            user_id="user-1",
            organization_id="org-company-1",
            user_role=LitellmUserRoles.INTERNAL_USER_VIEW_ONLY.value,
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        await require_company_admin_access(
            db,
            company_id="company-1",
            user_api_key_dict=_internal_user(),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_company_access_allows_company_operator_for_read_operation():
    db = _db()
    db.litellm_organizationmembership.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            user_id="user-1",
            organization_id="org-company-1",
            user_role=LitellmUserRoles.INTERNAL_USER.value,
        )
    )

    company = await require_company_access(
        db,
        company_id="company-1",
        user_api_key_dict=_internal_user(),
        require_admin=False,
    )

    assert company.company_id == "company-1"


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
async def test_project_admin_helper_allows_project_admin_product_role():
    db = _db()
    db.litellm_teamtable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            team_id="team-project-1",
            members_with_roles=[{"user_id": "user-1", "role": "admin"}],
        )
    )

    project = await require_project_admin_access(
        db,
        project_id="project-1",
        user_api_key_dict=_internal_user(),
    )

    assert project.project_id == "project-1"


@pytest.mark.asyncio
async def test_project_admin_helper_allows_company_admin_for_company_project():
    db = _db()
    db.litellm_organizationmembership.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            user_id="user-1",
            organization_id="org-company-1",
            user_role=LitellmUserRoles.ORG_ADMIN.value,
        )
    )

    project = await require_project_admin_access(
        db,
        project_id="project-1",
        user_api_key_dict=_internal_user(),
    )

    assert project.project_id == "project-1"


@pytest.mark.asyncio
async def test_project_admin_helper_rejects_operator_product_role():
    db = _db()
    db.litellm_teamtable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            team_id="team-project-1",
            members_with_roles=[{"user_id": "user-1", "role": "user"}],
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        await require_project_admin_access(
            db,
            project_id="project-1",
            user_api_key_dict=_internal_user(),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_project_admin_helper_rejects_cross_company_scope():
    db = _db()
    db.cavadalabs_projecttable.find_unique = AsyncMock(
        return_value=_project(
            company_id="company-2",
            litellm_team_id="team-project-2",
            project_id="project-2",
        )
    )
    db.cavadalabs_companytable.find_unique = AsyncMock(
        return_value=_company(
            company_id="company-2",
            litellm_organization_id="org-company-2",
        )
    )
    db.litellm_organizationmembership.find_unique = AsyncMock(return_value=None)
    db.litellm_teamtable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            team_id="team-project-2",
            members_with_roles=[],
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        await require_project_admin_access(
            db,
            project_id="project-2",
            user_api_key_dict=_internal_user(),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_project_access_allows_project_operator_for_read_operation():
    db = _db()
    db.litellm_teamtable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            team_id="team-project-1",
            members_with_roles=[{"user_id": "user-1", "role": "user"}],
        )
    )

    project = await require_project_access(
        db,
        project_id="project-1",
        user_api_key_dict=_internal_user(),
        require_admin=False,
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
async def test_user_list_filter_allows_native_company_viewer_without_compat_scope():
    db = _db()
    db.cavadalabs_companytable.find_unique = AsyncMock(
        return_value=_company(litellm_organization_id=None)
    )
    db.cavadalabs_companymembertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            company_id="company-1",
            user_id="user-1",
            role="viewer",
        )
    )

    organization_ids, team_ids = await resolve_cavadalabs_user_list_filters(
        db,
        user_api_key_dict=_internal_user(),
        cavadalabs_company_ids="company-1",
        cavadalabs_project_ids=None,
    )

    assert organization_ids == []
    assert team_ids == []


@pytest.mark.asyncio
async def test_user_list_filter_allows_native_project_viewer_without_compat_scope():
    db = _db()
    db.cavadalabs_projecttable.find_unique = AsyncMock(
        return_value=_project(litellm_team_id=None)
    )
    db.cavadalabs_projectmembertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            project_id="project-1",
            user_id="user-1",
            role="viewer",
        )
    )

    organization_ids, team_ids = await resolve_cavadalabs_user_list_filters(
        db,
        user_api_key_dict=_internal_user(),
        cavadalabs_company_ids=None,
        cavadalabs_project_ids="project-1",
    )

    assert organization_ids == []
    assert team_ids == []


@pytest.mark.asyncio
async def test_user_list_filter_denies_cross_company_scope():
    db = _db()
    db.cavadalabs_companytable.find_unique = AsyncMock(
        return_value=_company(company_id="company-2", litellm_organization_id=None)
    )

    with pytest.raises(HTTPException) as exc:
        await resolve_cavadalabs_user_list_filters(
            db,
            user_api_key_dict=_internal_user(),
            cavadalabs_company_ids="company-2",
            cavadalabs_project_ids=None,
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_user_list_filter_denies_cross_project_scope():
    db = _db()
    db.cavadalabs_projecttable.find_unique = AsyncMock(
        return_value=_project(project_id="project-2", litellm_team_id=None)
    )

    with pytest.raises(HTTPException) as exc:
        await resolve_cavadalabs_user_list_filters(
            db,
            user_api_key_dict=_internal_user(),
            cavadalabs_company_ids=None,
            cavadalabs_project_ids="project-2",
        )

    assert exc.value.status_code == 403


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
async def test_team_list_filter_rejects_company_without_compat_organization():
    db = _db()
    db.cavadalabs_companytable.find_unique = AsyncMock(
        return_value=_company(litellm_organization_id=None)
    )
    auth = UserAPIKeyAuth(
        user_id="admin-user",
        user_role=LitellmUserRoles.PROXY_ADMIN_VIEW_ONLY,
    )

    with pytest.raises(HTTPException) as exc_info:
        await resolve_cavadalabs_team_list_filters(
            db,
            user_api_key_dict=auth,
            cavadalabs_company_id="company-1",
            cavadalabs_project_id=None,
        )

    assert exc_info.value.status_code == 409
    assert "compatibility organization" in exc_info.value.detail["error"]


@pytest.mark.asyncio
async def test_team_list_filter_rejects_project_without_compat_team():
    db = _db()
    db.cavadalabs_projecttable.find_unique = AsyncMock(
        return_value=_project(litellm_team_id=None)
    )
    auth = UserAPIKeyAuth(
        user_id="admin-user",
        user_role=LitellmUserRoles.PROXY_ADMIN_VIEW_ONLY,
    )

    with pytest.raises(HTTPException) as exc_info:
        await resolve_cavadalabs_team_list_filters(
            db,
            user_api_key_dict=auth,
            cavadalabs_company_id=None,
            cavadalabs_project_id="project-1",
        )

    assert exc_info.value.status_code == 409
    assert "compatibility team" in exc_info.value.detail["error"]


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
async def test_company_usage_scope_returns_empty_scope_without_access():
    db = _db()

    company_ids = await resolve_cavadalabs_company_usage_scope(
        db,
        user_api_key_dict=_internal_user(),
        requested_company_ids=None,
    )

    assert company_ids == []


@pytest.mark.asyncio
async def test_company_usage_scope_does_not_promote_project_member_to_company_scope():
    db = _db()
    db.cavadalabs_projectmembertable.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(project_id="project-1", user_id="user-1", role="viewer")
        ]
    )
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[_project()])

    company_ids = await resolve_cavadalabs_company_usage_scope(
        db,
        user_api_key_dict=_internal_user(),
        requested_company_ids=None,
    )

    assert company_ids == []


@pytest.mark.asyncio
async def test_company_usage_scope_rejects_company_filter_for_project_only_member():
    db = _db()
    db.cavadalabs_projectmembertable.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(project_id="project-1", user_id="user-1", role="viewer")
        ]
    )
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[_project()])

    with pytest.raises(HTTPException) as exc_info:
        await resolve_cavadalabs_company_usage_scope(
            db,
            user_api_key_dict=_internal_user(),
            requested_company_ids="company-1",
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_company_usage_scope_reports_missing_native_membership_schema_without_legacy_scope():
    db = SimpleNamespace(
        litellm_organizationmembership=SimpleNamespace(
            find_many=AsyncMock(return_value=[])
        ),
        litellm_usertable=SimpleNamespace(find_unique=AsyncMock(return_value=None)),
    )

    with pytest.raises(HTTPException) as exc_info:
        await resolve_cavadalabs_company_usage_scope(
            db,
            user_api_key_dict=_internal_user(),
            requested_company_ids=None,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["schema_status"] == "missing_schema"
    assert "cavadalabs_companymembertable" in exc_info.value.detail["missing_schema"]
    assert "prisma migrate deploy" in exc_info.value.detail["migration_command"]


@pytest.mark.asyncio
async def test_company_usage_scope_preserves_legacy_org_fallback_when_native_schema_missing():
    db = SimpleNamespace(
        litellm_organizationmembership=SimpleNamespace(
            find_many=AsyncMock(
                return_value=[
                    SimpleNamespace(
                        user_id="user-1",
                        organization_id="org-company-1",
                        user_role=LitellmUserRoles.INTERNAL_USER.value,
                    )
                ]
            )
        ),
        cavadalabs_companytable=SimpleNamespace(
            find_many=AsyncMock(return_value=[_company()])
        ),
        litellm_usertable=SimpleNamespace(find_unique=AsyncMock(return_value=None)),
    )

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


@pytest.mark.asyncio
async def test_project_usage_scope_returns_empty_scope_without_access():
    db = _db()

    project_ids = await resolve_cavadalabs_project_usage_scope(
        db,
        user_api_key_dict=_internal_user(),
        requested_project_ids=None,
    )

    assert project_ids == []


@pytest.mark.asyncio
async def test_project_usage_scope_reports_missing_native_membership_schema_without_legacy_scope():
    db = SimpleNamespace(
        litellm_organizationmembership=SimpleNamespace(
            find_many=AsyncMock(return_value=[])
        ),
        litellm_usertable=SimpleNamespace(find_unique=AsyncMock(return_value=None)),
    )

    with pytest.raises(HTTPException) as exc_info:
        await resolve_cavadalabs_project_usage_scope(
            db,
            user_api_key_dict=_internal_user(),
            requested_project_ids=None,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["schema_status"] == "missing_schema"
    assert "cavadalabs_projectmembertable" in exc_info.value.detail["missing_schema"]
    assert "prisma migrate deploy" in exc_info.value.detail["migration_command"]


@pytest.mark.asyncio
async def test_project_usage_scope_preserves_legacy_team_fallback_when_native_schema_missing():
    db = SimpleNamespace(
        litellm_organizationmembership=SimpleNamespace(
            find_many=AsyncMock(return_value=[])
        ),
        litellm_usertable=SimpleNamespace(
            find_unique=AsyncMock(
                return_value=SimpleNamespace(user_id="user-1", teams=["team-project-1"])
            )
        ),
        cavadalabs_projecttable=SimpleNamespace(
            find_many=AsyncMock(return_value=[_project()])
        ),
    )

    project_ids = await resolve_cavadalabs_project_usage_scope(
        db,
        user_api_key_dict=_internal_user(),
        requested_project_ids=None,
    )

    assert project_ids == ["project-1"]


@pytest.mark.asyncio
async def test_company_access_metadata_marks_global_admin_as_company_admin():
    db = _db()
    auth = UserAPIKeyAuth(
        user_id="proxy-admin",
        user_role=LitellmUserRoles.PROXY_ADMIN,
    )

    company = await with_company_access_metadata(
        db,
        company=_company_response(),
        user_api_key_dict=auth,
    )

    assert company.cavadalabs_access_role == "company_admin"
    assert company.cavadalabs_can_manage is True
    assert company.cavadalabs_can_view_usage is True


@pytest.mark.asyncio
async def test_company_access_metadata_marks_admin_viewer_read_only():
    db = _db()
    auth = UserAPIKeyAuth(
        user_id="proxy-viewer",
        user_role=LitellmUserRoles.PROXY_ADMIN_VIEW_ONLY,
    )

    access_info = await company_access_info_for_user(
        db,
        company=_company_response(),
        user_api_key_dict=auth,
    )

    assert access_info.role == "viewer"
    assert access_info.can_view is True
    assert access_info.can_manage is False


@pytest.mark.asyncio
async def test_company_access_metadata_maps_company_admin_and_operator_roles():
    db = _db()
    db.litellm_organizationmembership.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            user_id="user-1",
            organization_id="org-company-1",
            user_role=LitellmUserRoles.ORG_ADMIN.value,
        )
    )

    admin_company = await with_company_access_metadata(
        db,
        company=_company_response(),
        user_api_key_dict=_internal_user(),
    )

    db.litellm_organizationmembership.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            user_id="user-1",
            organization_id="org-company-1",
            user_role=LitellmUserRoles.INTERNAL_USER.value,
        )
    )
    operator_company = await with_company_access_metadata(
        db,
        company=_company_response(),
        user_api_key_dict=_internal_user(),
    )

    assert admin_company.cavadalabs_access_role == "company_admin"
    assert admin_company.cavadalabs_can_manage is True
    assert admin_company.cavadalabs_can_view_usage is True
    assert operator_company.cavadalabs_access_role == "operator"
    assert operator_company.cavadalabs_can_manage is False
    assert operator_company.cavadalabs_can_view_usage is True


@pytest.mark.asyncio
async def test_project_access_metadata_maps_project_admin_operator_and_parent_company_admin():
    db = _db()
    db.litellm_teamtable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            team_id="team-project-1",
            members_with_roles=[{"user_id": "user-1", "role": "admin"}],
        )
    )

    admin_project = await with_project_access_metadata(
        db,
        project=_project_response(),
        user_api_key_dict=_internal_user(),
    )

    db.litellm_teamtable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            team_id="team-project-1",
            members_with_roles=[{"user_id": "user-1", "role": "user"}],
        )
    )
    operator_project = await with_project_access_metadata(
        db,
        project=_project_response(),
        user_api_key_dict=_internal_user(),
    )

    db.litellm_teamtable.find_unique = AsyncMock(return_value=None)
    db.litellm_usertable.find_unique = AsyncMock(return_value=None)
    db.cavadalabs_companytable.find_unique = AsyncMock(return_value=_company())
    db.litellm_organizationmembership.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            user_id="user-1",
            organization_id="org-company-1",
            user_role=LitellmUserRoles.ORG_ADMIN.value,
        )
    )
    company_admin_project = await with_project_access_metadata(
        db,
        project=_project_response(),
        user_api_key_dict=_internal_user(),
    )

    assert admin_project.cavadalabs_access_role == "project_admin"
    assert admin_project.cavadalabs_can_manage is True
    assert admin_project.cavadalabs_can_view_usage is True
    assert operator_project.cavadalabs_access_role == "operator"
    assert operator_project.cavadalabs_can_manage is False
    assert operator_project.cavadalabs_can_view_usage is True
    assert company_admin_project.cavadalabs_access_role == "company_admin"
    assert company_admin_project.cavadalabs_can_manage is True
    assert company_admin_project.cavadalabs_can_view_usage is True


@pytest.mark.asyncio
async def test_project_access_metadata_denies_non_member_without_global_fallback():
    db = _db()

    access_info = await project_access_info_for_user(
        db,
        project=_project_response(),
        user_api_key_dict=_internal_user(),
    )

    assert access_info.role is None
    assert access_info.can_view is False
    assert access_info.can_manage is False
