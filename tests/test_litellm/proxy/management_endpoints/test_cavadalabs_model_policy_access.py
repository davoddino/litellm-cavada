from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from litellm.proxy import proxy_server
from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.management_endpoints import (
    cavadalabs_model_policy_endpoints as model_policy_endpoints,
)
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsModelPolicyEndpointType,
    CavadaLabsProjectModelPolicyCreateRequest,
    CavadaLabsProjectModelPolicyUpdateRequest,
)


def _internal_user(user_id: str = "user-1") -> UserAPIKeyAuth:
    return UserAPIKeyAuth(
        api_key="sk-test",
        user_id=user_id,
        user_role=LitellmUserRoles.INTERNAL_USER,
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
        litellm_organization_id=kwargs.pop("litellm_organization_id", "org-1"),
        **kwargs,
    )


def _project(**kwargs):
    return _row(
        project_id=kwargs.pop("project_id", "project-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        name=kwargs.pop("name", "Support"),
        status=kwargs.pop("status", "production"),
        allowed_models=kwargs.pop("allowed_models", []),
        allowed_rag_collections=[],
        default_chatbot_settings={},
        default_guardrail_policy=None,
        budget=None,
        retention_policy_override={},
        metadata={},
        litellm_team_id=kwargs.pop("litellm_team_id", "team-1"),
        **kwargs,
    )


def _policy(**kwargs):
    return _row(
        policy_id=kwargs.pop("policy_id", "policy-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        project_id=kwargs.pop("project_id", "project-1"),
        endpoint_type=kwargs.pop("endpoint_type", "chat_completion"),
        model_bucket=kwargs.pop("model_bucket", "default"),
        model_alias=kwargs.pop("model_alias", "openai/gpt-4.1"),
        provider=kwargs.pop("provider", "openai"),
        deployment_id=kwargs.pop("deployment_id", None),
        priority=kwargs.pop("priority", 1),
        enabled=kwargs.pop("enabled", True),
        fallback_enabled=kwargs.pop("fallback_enabled", True),
        require_json_output=kwargs.pop("require_json_output", False),
        force_json_output=kwargs.pop("force_json_output", False),
        json_schema=kwargs.pop("json_schema", None),
        strict_json=kwargs.pop("strict_json", False),
        repair_invalid_json=kwargs.pop("repair_invalid_json", False),
        retry_on_invalid_json=kwargs.pop("retry_on_invalid_json", False),
        require_no_think=kwargs.pop("require_no_think", False),
        no_think=kwargs.pop("no_think", False),
        reasoning_mode=kwargs.pop("reasoning_mode", None),
        hide_reasoning=kwargs.pop("hide_reasoning", False),
        strip_thinking_tags=kwargs.pop("strip_thinking_tags", False),
        prefer_loaded_model=kwargs.pop("prefer_loaded_model", True),
        max_cost_input=kwargs.pop("max_cost_input", None),
        max_cost_output=kwargs.pop("max_cost_output", None),
        required_capabilities=kwargs.pop("required_capabilities", []),
        metadata=kwargs.pop("metadata", {}),
        **kwargs,
    )


def _db(
    *,
    company_member_role: str | None = None,
    project_member_role: str | None = None,
    allowed_project_id: str = "project-1",
):
    db = MagicMock()

    async def _find_company(*, where):
        return _company(company_id=where["company_id"])

    async def _find_project(*, where):
        project_id = where["project_id"]
        return _project(
            project_id=project_id,
            company_id="company-1" if project_id == "project-1" else "company-2",
        )

    async def _find_company_member(*, where):
        key = where["company_id_user_id"]
        if company_member_role and key["company_id"] == "company-1":
            return SimpleNamespace(
                company_id="company-1",
                user_id=key["user_id"],
                role=company_member_role,
            )
        return None

    async def _find_project_member(*, where):
        key = where["project_id_user_id"]
        if project_member_role and key["project_id"] == allowed_project_id:
            return SimpleNamespace(
                project_id=allowed_project_id,
                user_id=key["user_id"],
                role=project_member_role,
            )
        return None

    db.cavadalabs_companytable = MagicMock()
    db.cavadalabs_companytable.find_unique = AsyncMock(side_effect=_find_company)
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[])
    db.cavadalabs_projecttable = MagicMock()
    db.cavadalabs_projecttable.find_unique = AsyncMock(side_effect=_find_project)
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[])
    db.cavadalabs_companymembertable = MagicMock()
    db.cavadalabs_companymembertable.find_unique = AsyncMock(
        side_effect=_find_company_member
    )
    db.cavadalabs_companymembertable.find_many = AsyncMock(return_value=[])
    db.cavadalabs_projectmembertable = MagicMock()
    db.cavadalabs_projectmembertable.find_unique = AsyncMock(
        side_effect=_find_project_member
    )
    db.cavadalabs_projectmembertable.find_many = AsyncMock(return_value=[])
    db.litellm_organizationmembership = MagicMock()
    db.litellm_organizationmembership.find_unique = AsyncMock(return_value=None)
    db.litellm_organizationmembership.find_many = AsyncMock(return_value=[])
    db.litellm_teamtable = MagicMock()
    db.litellm_teamtable.find_unique = AsyncMock(return_value=None)
    db.litellm_usertable = MagicMock()
    db.litellm_usertable.find_unique = AsyncMock(return_value=None)
    db.cavadalabs_projectmodelpolicytable = MagicMock()
    db.cavadalabs_projectmodelpolicytable.find_unique = AsyncMock(
        return_value=_policy()
    )
    db.cavadalabs_projectmodelpolicytable.find_many = AsyncMock(
        return_value=[_policy()]
    )
    db.cavadalabs_projectmodelpolicytable.create = AsyncMock(
        return_value=_policy(policy_id="policy-created")
    )
    db.cavadalabs_projectmodelpolicytable.update = AsyncMock(
        return_value=_policy(policy_id="policy-1", model_alias="openai/gpt-4.1-mini")
    )
    db.cavadalabs_auditlogtable = MagicMock()
    db.cavadalabs_auditlogtable.create = AsyncMock()
    return db


def _patch_prisma(monkeypatch, db) -> None:
    monkeypatch.setattr(proxy_server, "prisma_client", SimpleNamespace(db=db))


def _create_request() -> CavadaLabsProjectModelPolicyCreateRequest:
    return CavadaLabsProjectModelPolicyCreateRequest(
        project_id="project-1",
        endpoint_type="chat_completion",
        model_bucket="medium",
        model_alias="openai/gpt-4.1",
        provider="openai",
        priority=1,
    )


@pytest.mark.asyncio
async def test_should_allow_project_admin_to_create_model_policy(monkeypatch):
    db = _db(project_member_role="project_admin")
    _patch_prisma(monkeypatch, db)

    response = await model_policy_endpoints.create_model_policy(
        data=_create_request(),
        http_request=MagicMock(),
        user_api_key_dict=_internal_user(),
    )

    assert response.policy_id == "policy-created"
    db.cavadalabs_projectmodelpolicytable.create.assert_awaited_once()
    create_data = db.cavadalabs_projectmodelpolicytable.create.await_args.kwargs["data"]
    assert create_data["endpoint_type"] == "chat_completion"
    assert create_data["model_bucket"] == "medium"


@pytest.mark.asyncio
async def test_should_allow_company_admin_to_update_project_model_policy(monkeypatch):
    db = _db(company_member_role="company_admin")
    _patch_prisma(monkeypatch, db)

    response = await model_policy_endpoints.update_model_policy(
        policy_id="policy-1",
        data=CavadaLabsProjectModelPolicyUpdateRequest(
            model_alias="openai/gpt-4.1-mini"
        ),
        http_request=MagicMock(),
        user_api_key_dict=_internal_user(),
    )

    assert response.model_alias == "openai/gpt-4.1-mini"
    db.cavadalabs_projectmodelpolicytable.update.assert_awaited_once()


@pytest.mark.asyncio
async def test_should_allow_project_viewer_to_list_but_not_create_model_policy(
    monkeypatch,
):
    db = _db(project_member_role="viewer")
    _patch_prisma(monkeypatch, db)

    listed = await model_policy_endpoints.list_model_policies(
        http_request=MagicMock(),
        project_id="project-1",
        enabled=True,
        endpoint_type=CavadaLabsModelPolicyEndpointType.CHAT_COMPLETION,
        model_bucket="medium",
        user_api_key_dict=_internal_user(),
    )

    assert listed.count == 1
    db.cavadalabs_projectmodelpolicytable.find_many.assert_awaited_once()
    find_args = db.cavadalabs_projectmodelpolicytable.find_many.await_args.kwargs
    assert find_args["where"]["endpoint_type"] == "chat_completion"
    assert find_args["where"]["model_bucket"] == "medium"

    with pytest.raises(HTTPException) as exc_info:
        await model_policy_endpoints.create_model_policy(
            data=_create_request(),
            http_request=MagicMock(),
            user_api_key_dict=_internal_user(),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_should_reject_cross_project_model_policy_list(monkeypatch):
    db = _db(project_member_role="project_admin", allowed_project_id="project-1")
    _patch_prisma(monkeypatch, db)

    with pytest.raises(HTTPException) as exc_info:
        await model_policy_endpoints.list_model_policies(
            http_request=MagicMock(),
            project_id="project-2",
            enabled=None,
            user_api_key_dict=_internal_user(),
        )

    assert exc_info.value.status_code == 403
    db.cavadalabs_projectmodelpolicytable.find_many.assert_not_awaited()
