import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from litellm.proxy._types import (
    GenerateKeyRequest,
    LitellmUserRoles,
    UpdateKeyRequest,
    UserAPIKeyAuth,
)
from litellm.proxy.cavadalabs.usage_tracking import (
    process_spend_logs_cavadalabs_ledger,
)
from litellm.proxy.management_endpoints.key_management_endpoints import (
    _apply_cavadalabs_key_context,
    _build_key_filter_conditions,
    _check_key_admin_access,
    _can_user_query_key_info,
    _common_key_generation_helper,
    _normalize_cavadalabs_generate_key_request,
    _resolve_cavadalabs_key_filter_compatibility_mappings,
    _should_default_key_list_to_caller_user,
    _validate_cavadalabs_key_context,
    _validate_cavadalabs_key_list_filter_access,
    _validate_update_key_data,
    can_modify_verification_token,
    prepare_key_update_data,
)


def _row(**kwargs):
    return SimpleNamespace(**kwargs)


def _project(**kwargs):
    return _row(
        project_id=kwargs.pop("project_id", "project-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        litellm_team_id=kwargs.pop("litellm_team_id", "team-project-1"),
        status=kwargs.pop("status", "production"),
        name=kwargs.pop("name", "Support"),
        allowed_models=kwargs.pop("allowed_models", ["gpt-4"]),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        created_by="admin-user",
        updated_by="admin-user",
        **kwargs,
    )


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
        status=kwargs.pop("status", "active"),
        monthly_budget=100.0,
        metadata={},
        retention_policy={},
        default_guardrail_policy=None,
        default_billing_settings={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        created_by="admin-user",
        updated_by="admin-user",
        **kwargs,
    )


def _chatbot(**kwargs):
    return _row(
        chatbot_id=kwargs.pop("chatbot_id", "chatbot-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        project_id=kwargs.pop("project_id", "project-1"),
        name=kwargs.pop("name", "Support chatbot"),
        status=kwargs.pop("status", "published"),
        **kwargs,
    )


def _prisma_client():
    prisma_client = MagicMock()
    prisma_client.db = MagicMock()
    prisma_client.db.cavadalabs_projecttable = MagicMock()
    prisma_client.db.cavadalabs_companytable = MagicMock()
    prisma_client.db.cavadalabs_chatbottable = MagicMock()
    prisma_client.db.litellm_teamtable = MagicMock()
    prisma_client.db.litellm_usertable = MagicMock()
    prisma_client.db.litellm_organizationmembership = MagicMock()
    prisma_client.db.cavadalabs_companymembertable = MagicMock()
    prisma_client.db.cavadalabs_projectmembertable = MagicMock()
    prisma_client.db.cavadalabs_projecttable.find_unique = AsyncMock(
        return_value=_project()
    )
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[])
    prisma_client.db.cavadalabs_companytable.find_unique = AsyncMock(
        return_value=_company()
    )
    prisma_client.db.cavadalabs_companytable.find_many = AsyncMock(return_value=[])
    prisma_client.db.cavadalabs_chatbottable.find_unique = AsyncMock(
        return_value=_chatbot()
    )
    prisma_client.db.litellm_teamtable.find_unique = AsyncMock(return_value=None)
    prisma_client.db.litellm_usertable.find_unique = AsyncMock(return_value=None)
    prisma_client.db.litellm_organizationmembership.find_unique = AsyncMock(
        return_value=None
    )
    prisma_client.db.litellm_organizationmembership.find_many = AsyncMock(
        return_value=[]
    )
    prisma_client.db.cavadalabs_companymembertable.find_unique = AsyncMock(
        return_value=None
    )
    prisma_client.db.cavadalabs_companymembertable.find_many = AsyncMock(
        return_value=[]
    )
    prisma_client.db.cavadalabs_projectmembertable.find_unique = AsyncMock(
        return_value=None
    )
    prisma_client.db.cavadalabs_projectmembertable.find_many = AsyncMock(
        return_value=[]
    )
    return prisma_client


def _proxy_admin() -> UserAPIKeyAuth:
    return UserAPIKeyAuth(
        user_id="proxy-admin",
        user_role=LitellmUserRoles.PROXY_ADMIN,
    )


def _internal_user(user_id: str = "user-1") -> UserAPIKeyAuth:
    return UserAPIKeyAuth(
        user_id=user_id,
        user_role=LitellmUserRoles.INTERNAL_USER,
    )


def _cavadalabs_key(**kwargs):
    metadata = kwargs.pop(
        "metadata",
        {
            "cavadalabs_company_id": "company-1",
            "cavadalabs_project_id": "project-1",
        },
    )
    return _row(
        token=kwargs.pop("token", "hashed-token"),
        key_alias=kwargs.pop("key_alias", "support-api"),
        user_id=kwargs.pop("user_id", "owner-user"),
        team_id=kwargs.pop("team_id", "team-project-1"),
        organization_id=kwargs.pop("organization_id", "org-company-1"),
        metadata=metadata,
        max_budget=kwargs.pop("max_budget", None),
        spend=kwargs.pop("spend", 0.0),
        **kwargs,
    )


def _project_admin_prisma_client():
    prisma_client = _prisma_client()
    prisma_client.db.litellm_teamtable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            team_id="team-project-1",
            members_with_roles=[{"user_id": "user-1", "role": "admin"}],
        )
    )
    return prisma_client


def test_key_filters_keep_user_scope_with_cavadalabs_company_filter():
    where = _build_key_filter_conditions(
        user_id="user-1",
        team_id=None,
        organization_id=None,
        key_alias=None,
        key_hash=None,
        exclude_team_id=None,
        admin_team_ids=None,
        cavadalabs_company_id="company-1",
        cavadalabs_project_id=None,
    )

    and_conditions = where["AND"]
    assert isinstance(and_conditions, list)
    base_scope = and_conditions[0]
    assert isinstance(base_scope, dict)
    assert base_scope["user_id"] == "user-1"

    cavadalabs_filter = json.dumps(and_conditions[1])
    assert "cavadalabs_company_id" in cavadalabs_filter
    assert "company-1" in cavadalabs_filter
    assert "spend_logs_metadata" in cavadalabs_filter


def test_key_filters_apply_company_and_project_as_global_scope():
    where = _build_key_filter_conditions(
        user_id="user-1",
        team_id=None,
        organization_id=None,
        key_alias=None,
        key_hash=None,
        exclude_team_id=None,
        admin_team_ids=None,
        cavadalabs_company_id="company-1",
        cavadalabs_project_id="project-1",
    )

    serialized_where = json.dumps(where)

    assert "user-1" in serialized_where
    assert "company-1" in serialized_where
    assert "project-1" in serialized_where
    assert "cavadalabs_company_id" in serialized_where
    assert "cavadalabs_project_id" in serialized_where


def test_key_filters_match_company_metadata_or_legacy_organization_mapping():
    where = _build_key_filter_conditions(
        user_id=None,
        team_id=None,
        organization_id=None,
        key_alias=None,
        key_hash=None,
        exclude_team_id=None,
        admin_team_ids=None,
        cavadalabs_company_id="company-1",
        cavadalabs_project_id=None,
        cavadalabs_company_compatibility_organization_id="org-company-1",
    )

    serialized_where = json.dumps(where)
    assert "cavadalabs_company_id" in serialized_where
    assert "company-1" in serialized_where
    assert "organization_id" in serialized_where
    assert "org-company-1" in serialized_where


def test_key_filters_match_project_metadata_or_legacy_team_mapping():
    where = _build_key_filter_conditions(
        user_id=None,
        team_id=None,
        organization_id=None,
        key_alias=None,
        key_hash=None,
        exclude_team_id=None,
        admin_team_ids=None,
        cavadalabs_company_id=None,
        cavadalabs_project_id="project-1",
        cavadalabs_project_compatibility_team_id="team-project-1",
    )

    serialized_where = json.dumps(where)
    assert "cavadalabs_project_id" in serialized_where
    assert "project-1" in serialized_where
    assert "team_id" in serialized_where
    assert "team-project-1" in serialized_where


@pytest.mark.asyncio
async def test_key_filter_mapping_resolves_company_project_internal_compatibility_ids():
    prisma_client = _prisma_client()

    organization_id, team_id = (
        await _resolve_cavadalabs_key_filter_compatibility_mappings(
            prisma_client=prisma_client,
            cavadalabs_company_id="company-1",
            cavadalabs_project_id="project-1",
        )
    )

    assert organization_id == "org-company-1"
    assert team_id == "team-project-1"
    prisma_client.db.cavadalabs_companytable.find_unique.assert_awaited_once_with(
        where={"company_id": "company-1"}
    )
    prisma_client.db.cavadalabs_projecttable.find_unique.assert_awaited_once_with(
        where={"project_id": "project-1"}
    )


@pytest.mark.asyncio
async def test_key_filter_mapping_reports_missing_schema_for_partial_cavadalabs_migration():
    prisma_client = _prisma_client()
    prisma_client.db.cavadalabs_projecttable.find_unique = AsyncMock(
        side_effect=Exception('column "litellm_team_id" does not exist')
    )

    with pytest.raises(HTTPException) as exc_info:
        await _resolve_cavadalabs_key_filter_compatibility_mappings(
            prisma_client=prisma_client,
            cavadalabs_company_id=None,
            cavadalabs_project_id="project-1",
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["schema_status"] == "missing_schema"
    assert exc_info.value.detail["missing_schema"] == ["cavadalabs_projecttable"]
    assert "prisma migrate deploy" in exc_info.value.detail["migration_command"]


def test_key_list_can_use_explicit_cavadalabs_scope_without_legacy_user_filter():
    assert (
        _should_default_key_list_to_caller_user(
            user_id=None,
            use_substring_matching=False,
            cavadalabs_company_id="company-1",
            cavadalabs_project_id=None,
        )
        is False
    )

    where = _build_key_filter_conditions(
        user_id=None,
        team_id=None,
        organization_id=None,
        key_alias=None,
        key_hash=None,
        exclude_team_id=None,
        admin_team_ids=None,
        cavadalabs_company_id="company-1",
        cavadalabs_project_id="project-1",
    )

    serialized_where = json.dumps(where)
    assert "company-1" in serialized_where
    assert "project-1" in serialized_where
    assert "user_id" not in serialized_where
    assert "organization_id" not in serialized_where


def test_key_list_without_cavadalabs_scope_keeps_legacy_user_default():
    assert (
        _should_default_key_list_to_caller_user(
            user_id=None,
            use_substring_matching=False,
            cavadalabs_company_id=None,
            cavadalabs_project_id=None,
        )
        is True
    )


@pytest.mark.asyncio
async def test_generate_key_request_normalizes_cavadalabs_context_to_metadata_and_internal_mapping():
    prisma_client = _project_admin_prisma_client()
    data = GenerateKeyRequest(
        models=["gpt-4"],
        project_id="legacy-litellm-project",
        cavadalabs_company_id="company-1",
        cavadalabs_project_id="project-1",
        metadata={"app": "support-api"},
    )

    context_was_requested = await _normalize_cavadalabs_generate_key_request(
        data=data,
        prisma_client=prisma_client,
        user_api_key_dict=_internal_user(),
    )

    assert context_was_requested is True
    assert data.organization_id == "org-company-1"
    assert data.team_id == "team-project-1"
    assert data.project_id is None
    assert data.cavadalabs_company_id == "company-1"
    assert data.cavadalabs_project_id == "project-1"
    assert data.metadata["cavadalabs_company_id"] == "company-1"
    assert data.metadata["cavadalabs_project_id"] == "project-1"
    assert data.metadata["cavadalabs"] == {
        "company_id": "company-1",
        "project_id": "project-1",
    }
    assert data.metadata["spend_logs_metadata"] == {
        "cavadalabs_company_id": "company-1",
        "cavadalabs_project_id": "project-1",
    }


@pytest.mark.asyncio
async def test_generate_key_request_preserves_chatbot_metadata_for_usage_attribution():
    prisma_client = _project_admin_prisma_client()
    data = GenerateKeyRequest(
        models=["gpt-4"],
        cavadalabs_company_id="company-1",
        cavadalabs_project_id="project-1",
        metadata={
            "app": "support-api",
            "cavadalabs_chatbot_id": "chatbot-1",
        },
    )

    context_was_requested = await _normalize_cavadalabs_generate_key_request(
        data=data,
        prisma_client=prisma_client,
        user_api_key_dict=_internal_user(),
    )

    assert context_was_requested is True
    assert data.organization_id == "org-company-1"
    assert data.team_id == "team-project-1"
    assert data.project_id is None
    assert data.metadata["app"] == "support-api"
    assert data.metadata["cavadalabs_company_id"] == "company-1"
    assert data.metadata["cavadalabs_project_id"] == "project-1"
    assert data.metadata["cavadalabs_chatbot_id"] == "chatbot-1"
    assert data.metadata["cavadalabs"] == {
        "company_id": "company-1",
        "project_id": "project-1",
        "chatbot_id": "chatbot-1",
    }
    assert data.metadata["spend_logs_metadata"] == {
        "cavadalabs_company_id": "company-1",
        "cavadalabs_project_id": "project-1",
        "cavadalabs_chatbot_id": "chatbot-1",
    }
    prisma_client.db.cavadalabs_chatbottable.find_unique.assert_awaited_once_with(
        where={"chatbot_id": "chatbot-1"}
    )


@pytest.mark.asyncio
async def test_generate_key_request_autoderives_single_native_project_admin_scope():
    prisma_client = _prisma_client()
    prisma_client.db.cavadalabs_projectmembertable.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                project_id="project-1",
                user_id="user-1",
                role="project_admin",
            )
        ]
    )
    prisma_client.db.cavadalabs_projectmembertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            project_id="project-1",
            user_id="user-1",
            role="project_admin",
        )
    )
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[_project()]
    )
    data = GenerateKeyRequest(
        models=["gpt-4"],
        metadata={"app": "support-api"},
    )

    context_was_requested = await _normalize_cavadalabs_generate_key_request(
        data=data,
        prisma_client=prisma_client,
        user_api_key_dict=_internal_user(),
    )

    assert context_was_requested is True
    assert data.organization_id == "org-company-1"
    assert data.team_id == "team-project-1"
    assert data.project_id is None
    assert data.cavadalabs_company_id == "company-1"
    assert data.cavadalabs_project_id == "project-1"
    assert data.metadata["app"] == "support-api"
    assert data.metadata["cavadalabs_company_id"] == "company-1"
    assert data.metadata["cavadalabs_project_id"] == "project-1"
    assert data.metadata["spend_logs_metadata"] == {
        "cavadalabs_company_id": "company-1",
        "cavadalabs_project_id": "project-1",
    }


@pytest.mark.asyncio
async def test_generate_key_request_keeps_legacy_path_when_scope_is_ambiguous():
    prisma_client = _prisma_client()
    prisma_client.db.cavadalabs_projectmembertable.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                project_id="project-1",
                user_id="user-1",
                role="project_admin",
            ),
            SimpleNamespace(
                project_id="project-2",
                user_id="user-1",
                role="project_admin",
            ),
        ]
    )
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[
            _project(project_id="project-1"),
            _project(project_id="project-2", company_id="company-2"),
        ]
    )
    data = GenerateKeyRequest(models=["gpt-4"])

    context_was_requested = await _normalize_cavadalabs_generate_key_request(
        data=data,
        prisma_client=prisma_client,
        user_api_key_dict=_internal_user(),
    )

    assert context_was_requested is False
    assert data.organization_id is None
    assert data.team_id is None
    assert data.metadata == {}


@pytest.mark.asyncio
async def test_generate_key_request_rejects_chatbot_without_cavadalabs_context():
    prisma_client = _project_admin_prisma_client()
    data = GenerateKeyRequest(
        models=["gpt-4"],
        metadata={"cavadalabs_chatbot_id": "chatbot-1"},
    )

    with pytest.raises(HTTPException) as exc_info:
        await _normalize_cavadalabs_generate_key_request(
            data=data,
            prisma_client=prisma_client,
            user_api_key_dict=_internal_user(),
        )

    assert exc_info.value.status_code == 400
    assert "cavadalabs_project_id is required" in exc_info.value.detail["error"]


@pytest.mark.asyncio
async def test_generate_key_request_rejects_chatbot_from_other_project():
    prisma_client = _project_admin_prisma_client()
    prisma_client.db.cavadalabs_chatbottable.find_unique = AsyncMock(
        return_value=_chatbot(
            chatbot_id="chatbot-foreign",
            company_id="company-2",
            project_id="project-2",
        )
    )
    data = GenerateKeyRequest(
        models=["gpt-4"],
        cavadalabs_company_id="company-1",
        cavadalabs_project_id="project-1",
        metadata={"cavadalabs_chatbot_id": "chatbot-foreign"},
    )

    with pytest.raises(HTTPException) as exc_info:
        await _normalize_cavadalabs_generate_key_request(
            data=data,
            prisma_client=prisma_client,
            user_api_key_dict=_internal_user(),
        )

    assert exc_info.value.status_code == 400
    assert (
        exc_info.value.detail["error"]
        == "cavadalabs_chatbot_id must belong to the key Company and Project"
    )
    assert exc_info.value.detail["chatbot_id"] == "chatbot-foreign"
    assert exc_info.value.detail["company_id"] == "company-1"
    assert exc_info.value.detail["project_id"] == "project-1"


@pytest.mark.asyncio
async def test_generate_key_request_reports_missing_schema_for_partial_project_migration():
    prisma_client = _prisma_client()
    prisma_client.db.cavadalabs_projecttable.find_unique = AsyncMock(
        side_effect=Exception('column "litellm_team_id" does not exist')
    )
    data = GenerateKeyRequest(
        models=["gpt-4"],
        cavadalabs_company_id="company-1",
        cavadalabs_project_id="project-1",
    )

    with pytest.raises(HTTPException) as exc_info:
        await _normalize_cavadalabs_generate_key_request(
            data=data,
            prisma_client=prisma_client,
            user_api_key_dict=_proxy_admin(),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["schema_status"] == "missing_schema"
    assert exc_info.value.detail["missing_schema"] == ["cavadalabs_projecttable"]
    assert "prisma migrate deploy" in exc_info.value.detail["migration_command"]


@pytest.mark.asyncio
async def test_prepare_key_update_data_reports_missing_schema_for_partial_company_migration():
    prisma_client = _prisma_client()
    prisma_client.db.cavadalabs_companytable.find_unique = AsyncMock(
        side_effect=Exception('column "litellm_organization_id" does not exist')
    )

    with pytest.raises(HTTPException) as exc_info:
        await prepare_key_update_data(
            data=UpdateKeyRequest(
                key="hashed-token",
                cavadalabs_company_id="company-1",
                cavadalabs_project_id="project-1",
            ),
            existing_key_row=_cavadalabs_key(
                metadata={"app": "legacy"},
                team_id=None,
                organization_id=None,
            ),
            user_api_key_dict=_proxy_admin(),
            prisma_client=prisma_client,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["schema_status"] == "missing_schema"
    assert exc_info.value.detail["missing_schema"] == ["cavadalabs_companytable"]
    assert "prisma migrate deploy" in exc_info.value.detail["migration_command"]


@pytest.mark.asyncio
async def test_key_generation_persists_cavadalabs_metadata_for_runtime_attribution(
    monkeypatch,
):
    from litellm.proxy import proxy_server
    from litellm.proxy.management_endpoints import (
        key_management_endpoints as key_endpoints,
    )

    prisma_client = _prisma_client()
    captured_key_data = {}

    async def capture_insert_data(data, table_name, **kwargs):
        if table_name == "key":
            captured_key_data.update(data)
            return SimpleNamespace(
                token="hashed-key",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                litellm_budget_table=None,
            )
        return SimpleNamespace(models=[])

    prisma_client.insert_data = AsyncMock(side_effect=capture_insert_data)
    prisma_client.jsonify_object = MagicMock(side_effect=lambda value: value)

    monkeypatch.setattr(proxy_server, "prisma_client", prisma_client)
    monkeypatch.setattr(proxy_server, "premium_user", True)
    monkeypatch.setattr(proxy_server, "llm_router", None)
    monkeypatch.setattr(proxy_server, "user_api_key_cache", MagicMock())
    monkeypatch.setattr(proxy_server, "litellm_proxy_admin_name", "proxy-admin")
    monkeypatch.setattr(
        key_endpoints,
        "get_team_object",
        AsyncMock(return_value=SimpleNamespace(team_id="team-project-1")),
    )
    monkeypatch.setattr(
        key_endpoints,
        "get_org_object",
        AsyncMock(return_value=SimpleNamespace(organization_id="org-company-1")),
    )
    monkeypatch.setattr(
        key_endpoints, "_check_team_key_limits", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        key_endpoints, "_check_org_key_limits", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        key_endpoints, "get_ui_settings_cached", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        key_endpoints.KeyManagementEventHooks,
        "async_key_generated_hook",
        AsyncMock(return_value=None),
    )

    response = await _common_key_generation_helper(
        data=GenerateKeyRequest(
            models=["gpt-4"],
            key="sk-cavadalabs-test-key",
            cavadalabs_company_id="company-1",
            cavadalabs_project_id="project-1",
            metadata={"owner": "support", "cavadalabs_chatbot_id": "chatbot-1"},
        ),
        user_api_key_dict=_proxy_admin(),
        litellm_changed_by=None,
        team_table=None,
    )

    assert response.token == "hashed-key"
    assert captured_key_data["organization_id"] == "org-company-1"
    assert captured_key_data["team_id"] == "team-project-1"
    assert captured_key_data["project_id"] is None
    saved_metadata = json.loads(captured_key_data["metadata"])
    assert saved_metadata["cavadalabs_company_id"] == "company-1"
    assert saved_metadata["cavadalabs_project_id"] == "project-1"
    assert saved_metadata["cavadalabs_chatbot_id"] == "chatbot-1"
    assert saved_metadata["cavadalabs"] == {
        "company_id": "company-1",
        "project_id": "project-1",
        "chatbot_id": "chatbot-1",
    }
    assert saved_metadata["spend_logs_metadata"] == {
        "cavadalabs_company_id": "company-1",
        "cavadalabs_project_id": "project-1",
        "cavadalabs_chatbot_id": "chatbot-1",
    }

    ledger_db = SimpleNamespace(
        litellm_verificationtoken=SimpleNamespace(
            find_many=AsyncMock(
                return_value=[
                    SimpleNamespace(
                        token="hashed-key",
                        metadata=saved_metadata,
                        team_id="team-project-1",
                        organization_id="org-company-1",
                    )
                ]
            )
        ),
        litellm_deletedverificationtoken=SimpleNamespace(
            find_many=AsyncMock(return_value=[])
        ),
        cavadalabs_projecttable=SimpleNamespace(
            find_many=AsyncMock(
                return_value=[
                    SimpleNamespace(project_id="project-1", company_id="company-1")
                ]
            )
        ),
        cavadalabs_companytable=SimpleNamespace(find_many=AsyncMock(return_value=[])),
        cavadalabs_requestledgertable=SimpleNamespace(
            create_many=AsyncMock(return_value=SimpleNamespace(count=1))
        ),
    )

    created = await process_spend_logs_cavadalabs_ledger(
        prisma_client=SimpleNamespace(db=ledger_db),
        logs_to_process=[
            {
                "request_id": "req-generated-key",
                "metadata": json.dumps({"user_api_key_hash": "hashed-key"}),
                "custom_llm_provider": "openai",
                "model": "openai/gpt-4.1",
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "spend": 0.05,
                "status": "success",
                "startTime": datetime.now(timezone.utc),
            }
        ],
    )

    assert created == 1
    ledger_row = ledger_db.cavadalabs_requestledgertable.create_many.call_args.kwargs[
        "data"
    ][0]
    assert ledger_row["company_id"] == "company-1"
    assert ledger_row["project_id"] == "project-1"
    assert ledger_row["chatbot_id"] == "chatbot-1"
    assert ledger_row["api_key_hash"] == "hashed-key"


@pytest.mark.asyncio
async def test_cavadalabs_key_context_reports_missing_schema():
    prisma_client = SimpleNamespace(db=SimpleNamespace())

    with pytest.raises(HTTPException) as exc_info:
        await _apply_cavadalabs_key_context(
            data_json={
                "cavadalabs_company_id": "company-1",
                "cavadalabs_project_id": "project-1",
            },
            existing_metadata=None,
            prisma_client=prisma_client,
            user_api_key_dict=_proxy_admin(),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["schema_status"] == "missing_schema"
    assert exc_info.value.detail["missing_schema"] == ["cavadalabs_projecttable"]
    assert exc_info.value.detail["migration_command"] == "uv run prisma migrate deploy"


@pytest.mark.asyncio
async def test_service_account_generate_maps_cavadalabs_context_before_team_validation(
    monkeypatch,
):
    from litellm.proxy import proxy_server
    from litellm.proxy.management_endpoints import (
        key_management_endpoints as key_endpoints,
    )

    prisma_client = _prisma_client()
    prisma_client.db.litellm_teamtable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            team_id="team-project-1",
            members_with_roles=[],
        )
    )
    captured_data = {}

    async def capture_generation(data, **kwargs):
        captured_data["data"] = data
        return {
            "team_id": data.team_id,
            "organization_id": data.organization_id,
            "project_id": data.project_id,
            "metadata": data.metadata,
            "user_id": data.user_id,
        }

    monkeypatch.setattr(proxy_server, "prisma_client", prisma_client)
    monkeypatch.setattr(proxy_server, "user_api_key_cache", None)
    monkeypatch.setattr(proxy_server, "user_custom_key_generate", None)
    monkeypatch.setattr(
        key_endpoints,
        "check_org_admin_can_generate_keys",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        key_endpoints,
        "get_team_object",
        AsyncMock(return_value=SimpleNamespace(team_id="team-project-1")),
    )
    monkeypatch.setattr(
        key_endpoints,
        "_check_team_key_limits",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(key_endpoints, "key_generation_check", MagicMock())
    monkeypatch.setattr(
        key_endpoints,
        "_common_key_generation_helper",
        AsyncMock(side_effect=capture_generation),
    )

    response = await key_endpoints.generate_service_account_key_fn(
        data=GenerateKeyRequest(
            models=["gpt-4"],
            project_id="legacy-litellm-project",
            metadata={"service_account_id": "support-api"},
            cavadalabs_company_id="company-1",
            cavadalabs_project_id="project-1",
        ),
        user_api_key_dict=_proxy_admin(),
        litellm_changed_by=None,
    )

    assert response["team_id"] == "team-project-1"
    assert response["organization_id"] == "org-company-1"
    assert response["project_id"] is None
    assert response["user_id"] is None
    assert response["metadata"]["service_account_id"] == "support-api"
    assert response["metadata"]["cavadalabs_company_id"] == "company-1"
    assert response["metadata"]["cavadalabs_project_id"] == "project-1"
    prisma_client.db.litellm_teamtable.find_unique.assert_called_once_with(
        where={"team_id": "team-project-1"}
    )
    assert captured_data["data"].team_id == "team-project-1"


@pytest.mark.asyncio
async def test_service_account_generate_allows_native_project_admin_without_legacy_team_admin(
    monkeypatch,
):
    from litellm.proxy import proxy_server
    from litellm.proxy.management_endpoints import (
        key_management_endpoints as key_endpoints,
    )

    prisma_client = _prisma_client()
    prisma_client.db.cavadalabs_projectmembertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            project_id="project-1",
            user_id="user-1",
            role="project_admin",
        )
    )
    prisma_client.db.litellm_teamtable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            team_id="team-project-1",
            members_with_roles=[],
        )
    )
    captured_data = {}

    async def capture_generation(data, **kwargs):
        captured_data["data"] = data
        return {
            "team_id": data.team_id,
            "organization_id": data.organization_id,
            "project_id": data.project_id,
            "metadata": data.metadata,
            "user_id": data.user_id,
        }

    legacy_key_generation_check = MagicMock(
        side_effect=AssertionError("legacy team key generation check should not run")
    )

    monkeypatch.setattr(proxy_server, "prisma_client", prisma_client)
    monkeypatch.setattr(proxy_server, "user_api_key_cache", None)
    monkeypatch.setattr(proxy_server, "user_custom_key_generate", None)
    monkeypatch.setattr(
        key_endpoints,
        "get_team_object",
        AsyncMock(
            return_value=SimpleNamespace(
                team_id="team-project-1",
                members_with_roles=[],
            )
        ),
    )
    monkeypatch.setattr(
        key_endpoints,
        "_check_team_key_limits",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        key_endpoints,
        "key_generation_check",
        legacy_key_generation_check,
    )
    monkeypatch.setattr(
        key_endpoints,
        "_common_key_generation_helper",
        AsyncMock(side_effect=capture_generation),
    )

    response = await key_endpoints.generate_service_account_key_fn(
        data=GenerateKeyRequest(
            models=["gpt-4"],
            metadata={"service_account_id": "support-api"},
            cavadalabs_company_id="company-1",
            cavadalabs_project_id="project-1",
        ),
        user_api_key_dict=_internal_user(),
        litellm_changed_by=None,
    )

    assert response["team_id"] == "team-project-1"
    assert response["organization_id"] == "org-company-1"
    assert response["project_id"] is None
    assert response["user_id"] is None
    assert response["metadata"]["service_account_id"] == "support-api"
    assert response["metadata"]["cavadalabs_company_id"] == "company-1"
    assert response["metadata"]["cavadalabs_project_id"] == "project-1"
    legacy_key_generation_check.assert_not_called()
    assert captured_data["data"].team_id == "team-project-1"


@pytest.mark.asyncio
async def test_generate_key_request_rejects_operator_cavadalabs_mutation():
    prisma_client = _prisma_client()
    prisma_client.db.litellm_teamtable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            team_id="team-project-1",
            members_with_roles=[{"user_id": "user-1", "role": "user"}],
        )
    )
    data = GenerateKeyRequest(
        models=["gpt-4"],
        cavadalabs_company_id="company-1",
        cavadalabs_project_id="project-1",
    )

    with pytest.raises(HTTPException) as exc_info:
        await _normalize_cavadalabs_generate_key_request(
            data=data,
            prisma_client=prisma_client,
            user_api_key_dict=_internal_user(),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_generate_key_request_allows_native_project_admin_without_legacy_team_admin():
    prisma_client = _prisma_client()
    prisma_client.db.cavadalabs_projectmembertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            project_id="project-1",
            user_id="user-1",
            role="project_admin",
        )
    )
    data = GenerateKeyRequest(
        models=["gpt-4"],
        cavadalabs_company_id="company-1",
        cavadalabs_project_id="project-1",
    )

    context_was_requested = await _normalize_cavadalabs_generate_key_request(
        data=data,
        prisma_client=prisma_client,
        user_api_key_dict=_internal_user(),
    )

    assert context_was_requested is True
    assert data.organization_id == "org-company-1"
    assert data.team_id == "team-project-1"
    assert data.metadata["cavadalabs_company_id"] == "company-1"
    assert data.metadata["cavadalabs_project_id"] == "project-1"
    prisma_client.db.litellm_teamtable.find_unique.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_key_request_allows_native_company_admin_for_project_key():
    prisma_client = _prisma_client()
    prisma_client.db.cavadalabs_companymembertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            company_id="company-1",
            user_id="user-1",
            role="company_admin",
        )
    )
    data = GenerateKeyRequest(
        models=["gpt-4"],
        cavadalabs_company_id="company-1",
        cavadalabs_project_id="project-1",
    )

    await _normalize_cavadalabs_generate_key_request(
        data=data,
        prisma_client=prisma_client,
        user_api_key_dict=_internal_user(),
    )

    assert data.organization_id == "org-company-1"
    assert data.team_id == "team-project-1"
    assert data.metadata["spend_logs_metadata"] == {
        "cavadalabs_company_id": "company-1",
        "cavadalabs_project_id": "project-1",
    }


@pytest.mark.asyncio
async def test_cavadalabs_key_context_rejects_conflicting_internal_team():
    prisma_client = _project_admin_prisma_client()

    with pytest.raises(HTTPException) as exc_info:
        await _apply_cavadalabs_key_context(
            data_json={
                "cavadalabs_company_id": "company-1",
                "cavadalabs_project_id": "project-1",
                "team_id": "team-conflict",
            },
            existing_metadata=None,
            prisma_client=prisma_client,
            user_api_key_dict=_internal_user(),
        )

    assert exc_info.value.status_code == 400
    assert "team_id conflicts" in exc_info.value.detail["error"]


@pytest.mark.asyncio
async def test_cavadalabs_key_context_discards_litellm_project_id():
    prisma_client = _project_admin_prisma_client()

    data_json = await _apply_cavadalabs_key_context(
        data_json={
            "cavadalabs_company_id": "company-1",
            "cavadalabs_project_id": "project-1",
            "project_id": "legacy-litellm-project",
        },
        existing_metadata=None,
        prisma_client=prisma_client,
        user_api_key_dict=_internal_user(),
    )

    assert "project_id" not in data_json
    assert data_json["organization_id"] == "org-company-1"
    assert data_json["team_id"] == "team-project-1"
    assert data_json["metadata"]["cavadalabs_project_id"] == "project-1"


@pytest.mark.asyncio
async def test_prepare_key_update_data_preserves_cavadalabs_context_for_usage_attribution():
    prisma_client = _project_admin_prisma_client()
    existing_key = SimpleNamespace(
        token="hashed-token",
        team_id="team-project-1",
        organization_id="org-company-1",
        metadata={
            "app": "support-api",
            "cavadalabs_company_id": "company-1",
            "cavadalabs_project_id": "project-1",
        },
    )
    update = UpdateKeyRequest(key="hashed-token", metadata={"app": "updated"})

    update_data = await prepare_key_update_data(
        data=update,
        existing_key_row=existing_key,
        user_api_key_dict=_internal_user(),
        prisma_client=prisma_client,
    )

    metadata = update_data["metadata"]
    assert metadata["app"] == "updated"
    assert metadata["cavadalabs_company_id"] == "company-1"
    assert metadata["cavadalabs_project_id"] == "project-1"
    assert metadata["cavadalabs"] == {
        "company_id": "company-1",
        "project_id": "project-1",
    }
    assert metadata["spend_logs_metadata"] == {
        "cavadalabs_company_id": "company-1",
        "cavadalabs_project_id": "project-1",
    }


@pytest.mark.asyncio
async def test_update_key_validation_allows_native_project_admin_without_legacy_team_admin(
    monkeypatch,
):
    from litellm.proxy.management_endpoints import (
        key_management_endpoints as key_endpoints,
    )

    prisma_client = _prisma_client()
    prisma_client.db.cavadalabs_projectmembertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            project_id="project-1",
            user_id="user-1",
            role="project_admin",
        )
    )
    legacy_team_permission_check = AsyncMock(
        side_effect=AssertionError("legacy team permission check should not run")
    )
    monkeypatch.setattr(
        key_endpoints.TeamMemberPermissionChecks,
        "can_team_member_execute_key_management_endpoint",
        legacy_team_permission_check,
    )
    monkeypatch.setattr(
        key_endpoints,
        "get_team_object",
        AsyncMock(return_value=None),
    )

    await _validate_update_key_data(
        data=UpdateKeyRequest(key="hashed-token", metadata={"app": "updated"}),
        existing_key_row=_cavadalabs_key(user_id="owner-user"),
        user_api_key_dict=_internal_user(),
        llm_router=None,
        premium_user=True,
        prisma_client=prisma_client,
        user_api_key_cache=MagicMock(),
    )

    legacy_team_permission_check.assert_not_awaited()


@pytest.mark.asyncio
async def test_prepare_key_update_data_preserves_existing_chatbot_metadata_for_usage_attribution():
    prisma_client = _project_admin_prisma_client()
    existing_key = SimpleNamespace(
        token="hashed-token",
        team_id="team-project-1",
        organization_id="org-company-1",
        metadata={
            "app": "support-api",
            "cavadalabs_company_id": "company-1",
            "cavadalabs_project_id": "project-1",
            "cavadalabs_chatbot_id": "chatbot-1",
            "spend_logs_metadata": {"legacy": "kept"},
        },
    )

    update_data = await prepare_key_update_data(
        data=UpdateKeyRequest(key="hashed-token", metadata={"app": "updated"}),
        existing_key_row=existing_key,
        user_api_key_dict=_internal_user(),
        prisma_client=prisma_client,
    )

    metadata = update_data["metadata"]
    assert metadata["app"] == "updated"
    assert metadata["cavadalabs_company_id"] == "company-1"
    assert metadata["cavadalabs_project_id"] == "project-1"
    assert metadata["cavadalabs_chatbot_id"] == "chatbot-1"
    assert metadata["cavadalabs"] == {
        "company_id": "company-1",
        "project_id": "project-1",
        "chatbot_id": "chatbot-1",
    }
    assert metadata["spend_logs_metadata"] == {
        "legacy": "kept",
        "cavadalabs_company_id": "company-1",
        "cavadalabs_project_id": "project-1",
        "cavadalabs_chatbot_id": "chatbot-1",
    }
    prisma_client.db.cavadalabs_chatbottable.find_unique.assert_awaited_once_with(
        where={"chatbot_id": "chatbot-1"}
    )


@pytest.mark.asyncio
async def test_prepare_key_update_data_repairs_top_level_cavadalabs_context_metadata():
    prisma_client = _project_admin_prisma_client()
    existing_key = _cavadalabs_key(
        metadata={"app": "legacy"},
        cavadalabs_company_id="company-1",
        cavadalabs_project_id="project-1",
        team_id=None,
        organization_id=None,
    )

    update_data = await prepare_key_update_data(
        data=UpdateKeyRequest(key="hashed-token", metadata={"app": "updated"}),
        existing_key_row=existing_key,
        user_api_key_dict=_internal_user(),
        prisma_client=prisma_client,
    )

    assert update_data["organization_id"] == "org-company-1"
    assert update_data["team_id"] == "team-project-1"
    metadata = update_data["metadata"]
    assert metadata["app"] == "updated"
    assert metadata["cavadalabs_company_id"] == "company-1"
    assert metadata["cavadalabs_project_id"] == "project-1"
    assert metadata["spend_logs_metadata"] == {
        "cavadalabs_company_id": "company-1",
        "cavadalabs_project_id": "project-1",
    }


@pytest.mark.asyncio
async def test_prepare_key_update_data_rejects_internal_team_remap_for_cavadalabs_key():
    prisma_client = _project_admin_prisma_client()

    with pytest.raises(HTTPException) as exc_info:
        await prepare_key_update_data(
            data=UpdateKeyRequest(key="hashed-token", team_id="team-other"),
            existing_key_row=_cavadalabs_key(user_id="owner-user"),
            user_api_key_dict=_internal_user(),
            prisma_client=prisma_client,
        )

    assert exc_info.value.status_code == 400
    assert "team_id conflicts" in exc_info.value.detail["error"]


@pytest.mark.asyncio
async def test_prepare_key_update_data_repairs_internal_mapping_for_existing_cavadalabs_key():
    prisma_client = _project_admin_prisma_client()

    update_data = await prepare_key_update_data(
        data=UpdateKeyRequest(key="hashed-token", metadata={"app": "updated"}),
        existing_key_row=_cavadalabs_key(
            user_id="owner-user",
            team_id=None,
            organization_id=None,
        ),
        user_api_key_dict=_internal_user(),
        prisma_client=prisma_client,
    )

    assert update_data["organization_id"] == "org-company-1"
    assert update_data["team_id"] == "team-project-1"
    assert update_data["metadata"]["cavadalabs_company_id"] == "company-1"
    assert update_data["metadata"]["cavadalabs_project_id"] == "project-1"


@pytest.mark.asyncio
async def test_prepare_key_update_data_assigns_cavadalabs_context_to_legacy_mapped_key():
    prisma_client = _project_admin_prisma_client()

    update_data = await prepare_key_update_data(
        data=UpdateKeyRequest(
            key="hashed-token",
            metadata={"app": "updated"},
            project_id="legacy-litellm-project",
            cavadalabs_company_id="company-1",
            cavadalabs_project_id="project-1",
        ),
        existing_key_row=_cavadalabs_key(
            user_id="owner-user",
            metadata={"app": "legacy"},
            team_id="team-project-1",
            organization_id="org-company-1",
        ),
        user_api_key_dict=_internal_user(),
        prisma_client=prisma_client,
    )

    assert "project_id" not in update_data
    assert update_data["organization_id"] == "org-company-1"
    assert update_data["team_id"] == "team-project-1"
    metadata = update_data["metadata"]
    assert metadata["app"] == "updated"
    assert metadata["cavadalabs_company_id"] == "company-1"
    assert metadata["cavadalabs_project_id"] == "project-1"
    assert metadata["cavadalabs"] == {
        "company_id": "company-1",
        "project_id": "project-1",
    }
    assert metadata["spend_logs_metadata"] == {
        "cavadalabs_company_id": "company-1",
        "cavadalabs_project_id": "project-1",
    }


@pytest.mark.asyncio
async def test_prepare_key_update_data_autoderives_single_native_project_admin_scope_for_legacy_key():
    prisma_client = _prisma_client()
    prisma_client.db.cavadalabs_projectmembertable.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                project_id="project-1",
                user_id="user-1",
                role="project_admin",
            )
        ]
    )
    prisma_client.db.cavadalabs_projectmembertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            project_id="project-1",
            user_id="user-1",
            role="project_admin",
        )
    )
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[_project()]
    )

    update_data = await prepare_key_update_data(
        data=UpdateKeyRequest(key="hashed-token", metadata={"app": "updated"}),
        existing_key_row=_cavadalabs_key(
            user_id="owner-user",
            metadata={"app": "legacy"},
            team_id=None,
            organization_id=None,
        ),
        user_api_key_dict=_internal_user(),
        prisma_client=prisma_client,
    )

    assert update_data["organization_id"] == "org-company-1"
    assert update_data["team_id"] == "team-project-1"
    metadata = update_data["metadata"]
    assert metadata["app"] == "updated"
    assert metadata["cavadalabs_company_id"] == "company-1"
    assert metadata["cavadalabs_project_id"] == "project-1"
    assert metadata["spend_logs_metadata"] == {
        "cavadalabs_company_id": "company-1",
        "cavadalabs_project_id": "project-1",
    }


@pytest.mark.asyncio
async def test_cavadalabs_key_update_strips_legacy_litellm_project_id():
    prisma_client = _project_admin_prisma_client()

    data_json = await _apply_cavadalabs_key_context(
        data_json={"metadata": {"app": "updated"}, "project_id": "legacy-project"},
        existing_metadata={
            "cavadalabs_company_id": "company-1",
            "cavadalabs_project_id": "project-1",
        },
        prisma_client=prisma_client,
        user_api_key_dict=_internal_user(),
        existing_team_id="team-project-1",
        existing_organization_id="org-company-1",
    )

    assert "project_id" not in data_json
    assert data_json["metadata"]["app"] == "updated"
    assert data_json["metadata"]["cavadalabs_company_id"] == "company-1"
    assert data_json["metadata"]["cavadalabs_project_id"] == "project-1"


@pytest.mark.asyncio
async def test_prepare_key_update_data_rejects_operator_for_cavadalabs_key():
    prisma_client = _prisma_client()
    prisma_client.db.litellm_teamtable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            team_id="team-project-1",
            members_with_roles=[{"user_id": "user-1", "role": "user"}],
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        await prepare_key_update_data(
            data=UpdateKeyRequest(key="hashed-token", metadata={"app": "updated"}),
            existing_key_row=_cavadalabs_key(user_id="user-1"),
            user_api_key_dict=_internal_user(),
            prisma_client=prisma_client,
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_cavadalabs_key_delete_requires_project_admin_even_for_owner():
    prisma_client = _prisma_client()
    prisma_client.db.litellm_teamtable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            team_id="team-project-1",
            members_with_roles=[{"user_id": "user-1", "role": "user"}],
        )
    )

    can_modify = await can_modify_verification_token(
        key_info=_cavadalabs_key(user_id="user-1"),
        user_api_key_cache=MagicMock(),
        user_api_key_dict=_internal_user(),
        prisma_client=prisma_client,
    )

    assert can_modify is False


@pytest.mark.asyncio
async def test_cavadalabs_key_delete_allows_project_admin():
    can_modify = await can_modify_verification_token(
        key_info=_cavadalabs_key(user_id="owner-user"),
        user_api_key_cache=MagicMock(),
        user_api_key_dict=_internal_user(),
        prisma_client=_project_admin_prisma_client(),
    )

    assert can_modify is True


@pytest.mark.asyncio
async def test_cavadalabs_key_admin_access_allows_native_project_admin_without_legacy_team_admin():
    prisma_client = _prisma_client()
    prisma_client.db.cavadalabs_projectmembertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            project_id="project-1",
            user_id="user-1",
            role="project_admin",
        )
    )
    prisma_client.db.litellm_verificationtoken = MagicMock()
    prisma_client.db.litellm_verificationtoken.find_unique = AsyncMock(
        return_value=_cavadalabs_key(user_id="owner-user")
    )
    prisma_client.db.litellm_teamtable.find_unique = AsyncMock(
        side_effect=AssertionError("legacy team admin check should not run")
    )

    await _check_key_admin_access(
        user_api_key_dict=_internal_user(),
        hashed_token="hashed-token",
        prisma_client=prisma_client,
        user_api_key_cache=MagicMock(),
        route="/key/block",
    )

    prisma_client.db.litellm_teamtable.find_unique.assert_not_awaited()


@pytest.mark.asyncio
async def test_cavadalabs_key_admin_access_rejects_native_viewer_before_legacy_team_admin():
    prisma_client = _prisma_client()
    prisma_client.db.cavadalabs_projectmembertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            project_id="project-1",
            user_id="user-1",
            role="viewer",
        )
    )
    prisma_client.db.litellm_verificationtoken = MagicMock()
    prisma_client.db.litellm_verificationtoken.find_unique = AsyncMock(
        return_value=_cavadalabs_key(user_id="owner-user")
    )
    prisma_client.db.litellm_teamtable.find_unique = AsyncMock(
        side_effect=AssertionError("legacy team admin check should not run")
    )

    with pytest.raises(HTTPException) as exc_info:
        await _check_key_admin_access(
            user_api_key_dict=_internal_user(),
            hashed_token="hashed-token",
            prisma_client=prisma_client,
            user_api_key_cache=MagicMock(),
            route="/key/block",
        )

    assert exc_info.value.status_code == 403
    assert "Only CavadaLabs company/project admins" in exc_info.value.detail["error"]
    prisma_client.db.litellm_teamtable.find_unique.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_personal_key_delete_owner_path_is_unchanged():
    can_modify = await can_modify_verification_token(
        key_info=_cavadalabs_key(
            user_id="user-1",
            team_id=None,
            organization_id=None,
            metadata={"app": "legacy"},
        ),
        user_api_key_cache=MagicMock(),
        user_api_key_dict=_internal_user(),
        prisma_client=_prisma_client(),
    )

    assert can_modify is True


@pytest.mark.asyncio
async def test_cavadalabs_key_delete_requires_admin_for_top_level_context_even_for_owner():
    can_modify = await can_modify_verification_token(
        key_info=_cavadalabs_key(
            user_id="user-1",
            metadata={"app": "legacy"},
            cavadalabs_company_id="company-1",
            cavadalabs_project_id="project-1",
        ),
        user_api_key_cache=MagicMock(),
        user_api_key_dict=_internal_user(),
        prisma_client=_prisma_client(),
    )

    assert can_modify is False


@pytest.mark.asyncio
async def test_cavadalabs_key_info_denies_user_outside_company_project_scope():
    can_query = await _can_user_query_key_info(
        user_api_key_dict=_internal_user(),
        key="hashed-token",
        key_info=_cavadalabs_key(user_id="user-1"),
        prisma_client=_prisma_client(),
    )

    assert can_query is False


@pytest.mark.asyncio
async def test_cavadalabs_key_info_denies_top_level_context_outside_scope_even_for_owner():
    can_query = await _can_user_query_key_info(
        user_api_key_dict=_internal_user(),
        key="hashed-token",
        key_info=_cavadalabs_key(
            user_id="user-1",
            metadata={"app": "legacy"},
            cavadalabs_company_id="company-1",
            cavadalabs_project_id="project-1",
        ),
        prisma_client=_prisma_client(),
    )

    assert can_query is False


@pytest.mark.asyncio
async def test_cavadalabs_key_info_allows_project_viewer_scope():
    prisma_client = _prisma_client()
    prisma_client.db.litellm_teamtable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            team_id="team-project-1",
            members_with_roles=[{"user_id": "user-1", "role": "viewer"}],
        )
    )

    can_query = await _can_user_query_key_info(
        user_api_key_dict=_internal_user(),
        key="hashed-token",
        key_info=_cavadalabs_key(user_id="other-user"),
        prisma_client=prisma_client,
    )

    assert can_query is True


@pytest.mark.asyncio
async def test_cavadalabs_key_info_allows_native_project_viewer_from_legacy_team_mapping():
    prisma_client = _prisma_client()

    async def find_project(where):
        if where == {"litellm_team_id": "team-project-1"}:
            return _project()
        if where == {"project_id": "project-1"}:
            return _project()
        return None

    prisma_client.db.cavadalabs_projecttable.find_unique = AsyncMock(
        side_effect=find_project
    )
    prisma_client.db.cavadalabs_projectmembertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            project_id="project-1",
            user_id="user-1",
            role="viewer",
        )
    )
    prisma_client.db.litellm_teamtable.find_unique = AsyncMock(
        side_effect=AssertionError("legacy team info access should not run")
    )

    can_query = await _can_user_query_key_info(
        user_api_key_dict=_internal_user(),
        key="hashed-token",
        key_info=_cavadalabs_key(
            user_id="other-user",
            metadata={"app": "legacy"},
            team_id="team-project-1",
            organization_id=None,
        ),
        prisma_client=prisma_client,
    )

    assert can_query is True
    prisma_client.db.litellm_teamtable.find_unique.assert_not_awaited()


@pytest.mark.asyncio
async def test_cavadalabs_key_info_reports_missing_schema_for_legacy_team_mapping():
    prisma_client = _prisma_client()
    prisma_client.db.cavadalabs_projecttable.find_unique = AsyncMock(
        side_effect=Exception('column "litellm_team_id" does not exist')
    )

    with pytest.raises(HTTPException) as exc_info:
        await _can_user_query_key_info(
            user_api_key_dict=_internal_user(),
            key="hashed-token",
            key_info=_cavadalabs_key(
                user_id="other-user",
                metadata={"app": "legacy"},
                team_id="team-project-1",
                organization_id=None,
            ),
            prisma_client=prisma_client,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["schema_status"] == "missing_schema"
    assert exc_info.value.detail["missing_schema"] == [
        "cavadalabs_projecttable.litellm_team_id"
    ]
    assert "prisma migrate deploy" in exc_info.value.detail["migration_command"]


@pytest.mark.asyncio
async def test_cavadalabs_key_list_filter_authorizes_visible_project_scope():
    prisma_client = _prisma_client()
    prisma_client.db.litellm_teamtable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            team_id="team-project-1",
            members_with_roles=[{"user_id": "user-1", "role": "user"}],
        )
    )

    await _validate_cavadalabs_key_list_filter_access(
        prisma_client=prisma_client,
        user_api_key_dict=_internal_user(),
        cavadalabs_company_id="company-1",
        cavadalabs_project_id="project-1",
    )


@pytest.mark.asyncio
async def test_cavadalabs_key_list_filter_allows_native_company_viewer_scope():
    prisma_client = _prisma_client()
    prisma_client.db.cavadalabs_companymembertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            company_id="company-1",
            user_id="user-1",
            role="viewer",
        )
    )

    await _validate_cavadalabs_key_list_filter_access(
        prisma_client=prisma_client,
        user_api_key_dict=_internal_user(),
        cavadalabs_company_id="company-1",
        cavadalabs_project_id=None,
    )


@pytest.mark.asyncio
async def test_cavadalabs_key_list_filter_allows_native_project_viewer_scope():
    prisma_client = _prisma_client()
    prisma_client.db.cavadalabs_projectmembertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            project_id="project-1",
            user_id="user-1",
            role="viewer",
        )
    )

    await _validate_cavadalabs_key_list_filter_access(
        prisma_client=prisma_client,
        user_api_key_dict=_internal_user(),
        cavadalabs_company_id="company-1",
        cavadalabs_project_id="project-1",
    )


@pytest.mark.asyncio
async def test_cavadalabs_key_list_company_filter_rejects_project_only_member_scope():
    prisma_client = _prisma_client()
    prisma_client.db.cavadalabs_projectmembertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            project_id="project-1",
            user_id="user-1",
            role="viewer",
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        await _validate_cavadalabs_key_list_filter_access(
            prisma_client=prisma_client,
            user_api_key_dict=_internal_user(),
            cavadalabs_company_id="company-1",
            cavadalabs_project_id=None,
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_cavadalabs_key_list_filter_rejects_non_member_scope():
    prisma_client = _prisma_client()

    with pytest.raises(HTTPException) as exc_info:
        await _validate_cavadalabs_key_list_filter_access(
            prisma_client=prisma_client,
            user_api_key_dict=_internal_user(),
            cavadalabs_company_id="company-1",
            cavadalabs_project_id="project-1",
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_cavadalabs_key_list_filter_rejects_company_project_mismatch():
    prisma_client = _prisma_client()

    with pytest.raises(HTTPException) as exc_info:
        await _validate_cavadalabs_key_list_filter_access(
            prisma_client=prisma_client,
            user_api_key_dict=_proxy_admin(),
            cavadalabs_company_id="company-2",
            cavadalabs_project_id="project-1",
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_cavadalabs_key_context_rejects_company_project_mismatch():
    prisma_client = _prisma_client()

    with pytest.raises(HTTPException) as exc_info:
        await _validate_cavadalabs_key_context(
            prisma_client=prisma_client,
            company_id="company-2",
            project_id="project-1",
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_proxy_admin_can_assign_cavadalabs_key_context():
    prisma_client = _prisma_client()

    data_json = await _apply_cavadalabs_key_context(
        data_json={
            "cavadalabs_company_id": "company-1",
            "cavadalabs_project_id": "project-1",
        },
        existing_metadata=None,
        prisma_client=prisma_client,
        user_api_key_dict=_proxy_admin(),
    )

    assert data_json["organization_id"] == "org-company-1"
    assert data_json["team_id"] == "team-project-1"
