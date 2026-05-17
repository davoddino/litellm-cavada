from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, Request

from litellm.proxy import proxy_server
from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.management_endpoints import (
    cavadalabs_company_endpoints,
    cavadalabs_project_endpoints,
)
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsCompanyResponse,
    CavadaLabsCompanyUpdateRequest,
    CavadaLabsProjectCreateRequest,
    CavadaLabsProjectResponse,
    CavadaLabsProjectUpdateRequest,
)


def _row(**kwargs):
    defaults = {
        "created_at": datetime(2026, 5, 17, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 5, 17, tzinfo=timezone.utc),
        "created_by": "actor-user",
        "updated_by": "actor-user",
    }
    return SimpleNamespace(**{**defaults, **kwargs})


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


def _company_response(**kwargs) -> CavadaLabsCompanyResponse:
    return CavadaLabsCompanyResponse.model_validate(_company(**kwargs).__dict__)


def _project_response(**kwargs) -> CavadaLabsProjectResponse:
    return CavadaLabsProjectResponse.model_validate(_project(**kwargs).__dict__)


def _company_member(role: str):
    return _row(
        membership_id="company-member-1",
        company_id="company-1",
        user_id="actor-user",
        role=role,
    )


def _project_member(role: str):
    return _row(
        membership_id="project-member-1",
        project_id="project-1",
        user_id="actor-user",
        role=role,
    )


def _auth(
    *,
    user_role: LitellmUserRoles = LitellmUserRoles.INTERNAL_USER,
    user_id: str = "actor-user",
) -> UserAPIKeyAuth:
    return UserAPIKeyAuth(user_id=user_id, user_role=user_role)


def _request(path: str) -> Request:
    return Request(scope={"type": "http", "path": path})


def _prisma(*, company_role: str | None = None, project_role: str | None = None):
    db = MagicMock()
    db.cavadalabs_companytable = MagicMock()
    db.cavadalabs_projecttable = MagicMock()
    db.cavadalabs_companymembertable = MagicMock()
    db.cavadalabs_projectmembertable = MagicMock()
    db.litellm_organizationmembership = MagicMock()
    db.litellm_teamtable = MagicMock()
    db.litellm_usertable = MagicMock()

    db.cavadalabs_companytable.find_unique = AsyncMock(return_value=_company())
    db.cavadalabs_projecttable.find_unique = AsyncMock(return_value=_project())
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[_project()])
    db.cavadalabs_companymembertable.find_unique = AsyncMock(
        return_value=_company_member(company_role) if company_role is not None else None
    )
    db.cavadalabs_companymembertable.find_many = AsyncMock(
        return_value=[_company_member(company_role)] if company_role is not None else []
    )
    db.cavadalabs_projectmembertable.find_unique = AsyncMock(
        return_value=_project_member(project_role) if project_role is not None else None
    )
    db.cavadalabs_projectmembertable.find_many = AsyncMock(
        return_value=[_project_member(project_role)] if project_role is not None else []
    )
    db.litellm_organizationmembership.find_unique = AsyncMock(return_value=None)
    db.litellm_organizationmembership.find_many = AsyncMock(return_value=[])
    db.litellm_teamtable.find_unique = AsyncMock(return_value=None)
    db.litellm_usertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(user_id="actor-user", teams=[])
    )
    return SimpleNamespace(db=db)


@pytest.mark.asyncio
async def test_should_mark_project_member_parent_company_as_not_company_usage_visible(
    monkeypatch,
):
    prisma = _prisma(project_role="project_admin")
    service = SimpleNamespace(list_companies=AsyncMock(return_value=[_company_response()]))
    monkeypatch.setattr(proxy_server, "prisma_client", prisma)
    monkeypatch.setattr(
        cavadalabs_company_endpoints, "dispatcher_service", lambda: service
    )

    response = await cavadalabs_company_endpoints.list_companies(
        http_request=_request("/cavadalabs/companies"),
        status_filter=None,
        take=100,
        skip=0,
        user_api_key_dict=_auth(),
    )

    assert response.count == 1
    assert response.companies[0].cavadalabs_access_role == "operator"
    assert response.companies[0].cavadalabs_can_manage is False
    assert response.companies[0].cavadalabs_can_view_usage is False
    service.list_companies.assert_awaited_once()
    assert service.list_companies.call_args.kwargs["company_ids"] == ["company-1"]


@pytest.mark.asyncio
async def test_should_allow_native_company_admin_to_update_company_without_organization_gate(
    monkeypatch,
):
    prisma = _prisma(company_role="company_admin")
    service = SimpleNamespace(
        update_company=AsyncMock(return_value=_company_response(legal_name="Updated"))
    )
    monkeypatch.setattr(proxy_server, "prisma_client", prisma)
    monkeypatch.setattr(
        cavadalabs_company_endpoints, "dispatcher_service", lambda: service
    )

    response = await cavadalabs_company_endpoints.update_company(
        company_id="company-1",
        data=CavadaLabsCompanyUpdateRequest(legal_name="Updated"),
        http_request=_request("/cavadalabs/companies/company-1"),
        user_api_key_dict=_auth(),
    )

    assert response.legal_name == "Updated"
    service.update_company.assert_awaited_once()
    prisma.db.litellm_organizationmembership.find_unique.assert_not_awaited()


@pytest.mark.asyncio
async def test_should_reject_native_company_viewer_from_company_update(monkeypatch):
    prisma = _prisma(company_role="viewer")
    service = SimpleNamespace(update_company=AsyncMock())
    monkeypatch.setattr(proxy_server, "prisma_client", prisma)
    monkeypatch.setattr(
        cavadalabs_company_endpoints, "dispatcher_service", lambda: service
    )

    with pytest.raises(HTTPException) as exc_info:
        await cavadalabs_company_endpoints.update_company(
            company_id="company-1",
            data=CavadaLabsCompanyUpdateRequest(legal_name="Denied"),
            http_request=_request("/cavadalabs/companies/company-1"),
            user_api_key_dict=_auth(),
        )

    assert exc_info.value.status_code == 403
    service.update_company.assert_not_awaited()
    prisma.db.litellm_organizationmembership.find_unique.assert_not_awaited()


@pytest.mark.asyncio
async def test_should_allow_native_company_admin_to_create_project_without_org_admin(
    monkeypatch,
):
    prisma = _prisma(company_role="company_admin")
    service = SimpleNamespace(
        create_project=AsyncMock(return_value=_project_response(name="New Project"))
    )
    monkeypatch.setattr(proxy_server, "prisma_client", prisma)
    monkeypatch.setattr(
        cavadalabs_project_endpoints, "dispatcher_service", lambda: service
    )

    response = await cavadalabs_project_endpoints.create_project(
        data=CavadaLabsProjectCreateRequest(
            company_id="company-1", name="New Project"
        ),
        http_request=_request("/cavadalabs/projects"),
        user_api_key_dict=_auth(),
    )

    assert response.name == "New Project"
    service.create_project.assert_awaited_once()
    prisma.db.litellm_organizationmembership.find_unique.assert_not_awaited()


@pytest.mark.asyncio
async def test_should_allow_native_project_admin_to_update_project_without_team_gate(
    monkeypatch,
):
    prisma = _prisma(project_role="project_admin")
    service = SimpleNamespace(
        update_project=AsyncMock(return_value=_project_response(name="Updated Project"))
    )
    monkeypatch.setattr(proxy_server, "prisma_client", prisma)
    monkeypatch.setattr(
        cavadalabs_project_endpoints, "dispatcher_service", lambda: service
    )

    response = await cavadalabs_project_endpoints.update_project(
        project_id="project-1",
        data=CavadaLabsProjectUpdateRequest(name="Updated Project"),
        http_request=_request("/cavadalabs/projects/project-1"),
        user_api_key_dict=_auth(),
    )

    assert response.name == "Updated Project"
    service.update_project.assert_awaited_once()
    prisma.db.litellm_teamtable.find_unique.assert_not_awaited()


@pytest.mark.asyncio
async def test_should_reject_native_project_viewer_from_project_update(monkeypatch):
    prisma = _prisma(project_role="viewer")
    service = SimpleNamespace(update_project=AsyncMock())
    monkeypatch.setattr(proxy_server, "prisma_client", prisma)
    monkeypatch.setattr(
        cavadalabs_project_endpoints, "dispatcher_service", lambda: service
    )

    with pytest.raises(HTTPException) as exc_info:
        await cavadalabs_project_endpoints.update_project(
            project_id="project-1",
            data=CavadaLabsProjectUpdateRequest(name="Denied"),
            http_request=_request("/cavadalabs/projects/project-1"),
            user_api_key_dict=_auth(),
        )

    assert exc_info.value.status_code == 403
    service.update_project.assert_not_awaited()
    prisma.db.litellm_teamtable.find_unique.assert_not_awaited()


@pytest.mark.asyncio
async def test_should_keep_proxy_admin_override_for_project_update(monkeypatch):
    prisma = _prisma()
    service = SimpleNamespace(
        update_project=AsyncMock(return_value=_project_response(name="Admin Update"))
    )
    monkeypatch.setattr(proxy_server, "prisma_client", prisma)
    monkeypatch.setattr(
        cavadalabs_project_endpoints, "dispatcher_service", lambda: service
    )

    response = await cavadalabs_project_endpoints.update_project(
        project_id="project-1",
        data=CavadaLabsProjectUpdateRequest(name="Admin Update"),
        http_request=_request("/cavadalabs/projects/project-1"),
        user_api_key_dict=_auth(user_role=LitellmUserRoles.PROXY_ADMIN),
    )

    assert response.name == "Admin Update"
    service.update_project.assert_awaited_once()
    prisma.db.cavadalabs_projectmembertable.find_unique.assert_not_awaited()
