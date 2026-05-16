from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.cavadalabs.chatbot_references import (
    validate_chatbot_project_references,
)
from litellm.proxy.cavadalabs.chatbot_runtime_auth import (
    build_chatbot_runtime_user_api_key,
)
from litellm.proxy.cavadalabs.chatbot_scope import (
    require_chatbot_project_access,
    require_web_token_project_access,
)
from litellm.proxy.cavadalabs.dispatcher_shared import CavadaLabsRuntimeContext
from litellm.proxy.cavadalabs.model_policy_proxy import (
    apply_cavadalabs_project_model_fallback,
)
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsChatbotResponse,
    CavadaLabsCompanyResponse,
    CavadaLabsProjectModelPolicyResponse,
    CavadaLabsProjectResponse,
    CavadaLabsWebTokenResponse,
)


NOW = datetime(2026, 5, 16, tzinfo=timezone.utc)


class _UniqueDelegate:
    def __init__(self, lookup_field: str, rows_by_id: dict[str, object]):
        self.lookup_field = lookup_field
        self.rows_by_id = rows_by_id
        self.find_unique = AsyncMock(side_effect=self._find_unique)

    async def _find_unique(self, *, where):
        return self.rows_by_id.get(where.get(self.lookup_field))


def _row(**kwargs):
    return SimpleNamespace(**kwargs)


def _company_row(**kwargs):
    return _row(
        company_id=kwargs.pop("company_id", "company-1"),
        legal_name=kwargs.pop("legal_name", "Company 1"),
        billing_name=kwargs.pop("billing_name", None),
        vat_tax_id=kwargs.pop("vat_tax_id", None),
        billing_address=kwargs.pop("billing_address", {}),
        admin_emails=kwargs.pop("admin_emails", []),
        plan=kwargs.pop("plan", None),
        status=kwargs.pop("status", "active"),
        monthly_budget=kwargs.pop("monthly_budget", None),
        metadata=kwargs.pop("metadata", {}),
        retention_policy=kwargs.pop("retention_policy", {}),
        default_guardrail_policy=kwargs.pop("default_guardrail_policy", None),
        default_billing_settings=kwargs.pop("default_billing_settings", {}),
        litellm_organization_id=kwargs.pop("litellm_organization_id", "org-1"),
        created_at=kwargs.pop("created_at", NOW),
        created_by=kwargs.pop("created_by", "admin"),
        updated_at=kwargs.pop("updated_at", NOW),
        updated_by=kwargs.pop("updated_by", "admin"),
    )


def _project_row(**kwargs):
    return _row(
        project_id=kwargs.pop("project_id", "project-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        name=kwargs.pop("name", "Project 1"),
        status=kwargs.pop("status", "dev"),
        allowed_models=kwargs.pop("allowed_models", []),
        allowed_rag_collections=kwargs.pop("allowed_rag_collections", []),
        default_chatbot_settings=kwargs.pop("default_chatbot_settings", {}),
        default_guardrail_policy=kwargs.pop("default_guardrail_policy", None),
        budget=kwargs.pop("budget", None),
        retention_policy_override=kwargs.pop("retention_policy_override", {}),
        metadata=kwargs.pop("metadata", {}),
        litellm_team_id=kwargs.pop("litellm_team_id", "team-1"),
        created_at=kwargs.pop("created_at", NOW),
        created_by=kwargs.pop("created_by", "admin"),
        updated_at=kwargs.pop("updated_at", NOW),
        updated_by=kwargs.pop("updated_by", "admin"),
    )


def _chatbot_row(**kwargs):
    return _row(
        chatbot_id=kwargs.pop("chatbot_id", "chatbot-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        project_id=kwargs.pop("project_id", "project-1"),
        name=kwargs.pop("name", "Support bot"),
        status=kwargs.pop("status", "published"),
        system_prompt=kwargs.pop("system_prompt", "Answer."),
        prompt_version=kwargs.pop("prompt_version", 1),
        default_language=kwargs.pop("default_language", "it"),
        model_policy_id=kwargs.pop("model_policy_id", "policy-1"),
        assigned_rag_collections=kwargs.pop("assigned_rag_collections", []),
        assigned_guardrail_policy=kwargs.pop("assigned_guardrail_policy", None),
        allowed_domains=kwargs.pop("allowed_domains", []),
        widget_theme_config=kwargs.pop("widget_theme_config", {}),
        fallback_message=kwargs.pop("fallback_message", None),
        transcript_retention_policy=kwargs.pop("transcript_retention_policy", {}),
        metadata=kwargs.pop("metadata", {}),
        created_at=kwargs.pop("created_at", NOW),
        created_by=kwargs.pop("created_by", "admin"),
        updated_at=kwargs.pop("updated_at", NOW),
        updated_by=kwargs.pop("updated_by", "admin"),
    )


def _web_token_row(**kwargs):
    return _row(
        web_token_id=kwargs.pop("web_token_id", "web-token-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        project_id=kwargs.pop("project_id", "project-1"),
        chatbot_id=kwargs.pop("chatbot_id", "chatbot-1"),
        name=kwargs.pop("name", "Browser token"),
        token_prefix=kwargs.pop("token_prefix", "clwt-prefix"),
        status=kwargs.pop("status", "active"),
        allowed_domains=kwargs.pop("allowed_domains", []),
        allowed_origins=kwargs.pop("allowed_origins", []),
        route_allowlist=kwargs.pop(
            "route_allowlist", ["/cavadalabs/chatbots/messages"]
        ),
        ip_rpm_limit=kwargs.pop("ip_rpm_limit", None),
        session_rpm_limit=kwargs.pop("session_rpm_limit", None),
        session_budget=kwargs.pop("session_budget", None),
        expires_at=kwargs.pop("expires_at", NOW + timedelta(hours=1)),
        revoked_at=kwargs.pop("revoked_at", None),
        last_used_at=kwargs.pop("last_used_at", None),
        metadata=kwargs.pop("metadata", {}),
        created_at=kwargs.pop("created_at", NOW),
        created_by=kwargs.pop("created_by", "admin"),
        updated_at=kwargs.pop("updated_at", NOW),
        updated_by=kwargs.pop("updated_by", "admin"),
    )


def _policy_row(**kwargs):
    return _row(
        policy_id=kwargs.pop("policy_id", "policy-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        project_id=kwargs.pop("project_id", "project-1"),
        model_alias=kwargs.pop("model_alias", "model-a"),
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
        created_at=kwargs.pop("created_at", NOW),
        created_by=kwargs.pop("created_by", "admin"),
        updated_at=kwargs.pop("updated_at", NOW),
        updated_by=kwargs.pop("updated_by", "admin"),
    )


def _rag_collection_row(**kwargs):
    return _row(
        collection_id=kwargs.pop("collection_id", "rag-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        project_id=kwargs.pop("project_id", "project-1"),
        name=kwargs.pop("name", "Knowledge"),
        description=kwargs.pop("description", None),
        scope=kwargs.pop("scope", "project"),
        status=kwargs.pop("status", "active"),
        source_type=kwargs.pop("source_type", None),
        vector_store_provider=kwargs.pop("vector_store_provider", None),
        vector_store_id=kwargs.pop("vector_store_id", None),
        embedding_model=kwargs.pop("embedding_model", None),
        chunking_strategy=kwargs.pop("chunking_strategy", {}),
        access_policy=kwargs.pop("access_policy", {}),
        retention_policy=kwargs.pop("retention_policy", {}),
        metadata=kwargs.pop("metadata", {}),
        created_at=kwargs.pop("created_at", NOW),
        created_by=kwargs.pop("created_by", "admin"),
        updated_at=kwargs.pop("updated_at", NOW),
        updated_by=kwargs.pop("updated_by", "admin"),
    )


def _guardrail_policy_row(**kwargs):
    return _row(
        policy_id=kwargs.pop("policy_id", "guardrail-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        project_id=kwargs.pop("project_id", "project-1"),
        chatbot_id=kwargs.pop("chatbot_id", None),
        name=kwargs.pop("name", "Safety"),
        version=kwargs.pop("version", 1),
        scope=kwargs.pop("scope", "project"),
        status=kwargs.pop("status", "active"),
        enforcement_mode=kwargs.pop("enforcement_mode", "enforce"),
        description=kwargs.pop("description", None),
        categories=kwargs.pop("categories", []),
        rules=kwargs.pop("rules", {}),
        blocked_patterns=kwargs.pop("blocked_patterns", []),
        redaction_patterns=kwargs.pop("redaction_patterns", {}),
        pii_detection_enabled=kwargs.pop("pii_detection_enabled", True),
        prompt_injection_detection_enabled=kwargs.pop(
            "prompt_injection_detection_enabled", True
        ),
        log_raw_content=kwargs.pop("log_raw_content", False),
        metadata=kwargs.pop("metadata", {}),
        created_at=kwargs.pop("created_at", NOW),
        created_by=kwargs.pop("created_by", "admin"),
        updated_at=kwargs.pop("updated_at", NOW),
        updated_by=kwargs.pop("updated_by", "admin"),
    )


def _db(**overrides):
    project_members = overrides.pop("project_members", {})
    company_members = overrides.pop("company_members", {})
    db = SimpleNamespace(
        cavadalabs_chatbottable=_UniqueDelegate(
            "chatbot_id", {"chatbot-1": _chatbot_row()}
        ),
        cavadalabs_webtokentable=_UniqueDelegate(
            "web_token_id", {"web-token-1": _web_token_row()}
        ),
        cavadalabs_projecttable=_UniqueDelegate(
            "project_id", {"project-1": _project_row()}
        ),
        cavadalabs_companytable=_UniqueDelegate(
            "company_id", {"company-1": _company_row()}
        ),
        cavadalabs_projectmembertable=SimpleNamespace(
            find_unique=AsyncMock(
                side_effect=lambda *, where: project_members.get(
                    (
                        where["project_id_user_id"]["project_id"],
                        where["project_id_user_id"]["user_id"],
                    )
                )
            ),
            find_many=AsyncMock(return_value=[]),
        ),
        cavadalabs_companymembertable=SimpleNamespace(
            find_unique=AsyncMock(
                side_effect=lambda *, where: company_members.get(
                    (
                        where["company_id_user_id"]["company_id"],
                        where["company_id_user_id"]["user_id"],
                    )
                )
            ),
            find_many=AsyncMock(return_value=[]),
        ),
        litellm_teamtable=SimpleNamespace(find_unique=AsyncMock(return_value=None)),
        litellm_usertable=SimpleNamespace(find_unique=AsyncMock(return_value=None)),
        litellm_organizationmembership=SimpleNamespace(
            find_unique=AsyncMock(return_value=None),
            find_many=AsyncMock(return_value=[]),
        ),
    )
    for name, value in overrides.items():
        setattr(db, name, value)
    return db


def _project_member(role: str):
    return _row(project_id="project-1", user_id="user-1", role=role)


def _internal_user() -> UserAPIKeyAuth:
    return UserAPIKeyAuth(
        api_key="sk-user",
        user_id="user-1",
        user_role=LitellmUserRoles.INTERNAL_USER,
    )


@pytest.mark.asyncio
async def test_should_allow_project_admin_to_manage_chatbot_scope():
    db = _db(
        project_members={("project-1", "user-1"): _project_member("project_admin")}
    )

    chatbot = await require_chatbot_project_access(
        db,
        chatbot_id="chatbot-1",
        user_api_key_dict=_internal_user(),
        require_admin=True,
    )

    assert chatbot.chatbot_id == "chatbot-1"
    assert chatbot.company_id == "company-1"
    db.cavadalabs_projectmembertable.find_unique.assert_awaited_once()


@pytest.mark.asyncio
async def test_should_deny_project_viewer_from_admin_chatbot_scope():
    db = _db(project_members={("project-1", "user-1"): _project_member("viewer")})

    with pytest.raises(HTTPException) as exc_info:
        await require_chatbot_project_access(
            db,
            chatbot_id="chatbot-1",
            user_api_key_dict=_internal_user(),
            require_admin=True,
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_should_validate_web_token_project_scope_consistency():
    db = _db(
        cavadalabs_webtokentable=_UniqueDelegate(
            "web_token_id",
            {
                "web-token-1": _web_token_row(
                    web_token_id="web-token-1",
                    company_id="company-2",
                    project_id="project-1",
                )
            },
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        await require_web_token_project_access(
            db,
            web_token_id="web-token-1",
            user_api_key_dict=UserAPIKeyAuth(
                api_key="sk-admin", user_role=LitellmUserRoles.PROXY_ADMIN
            ),
            require_admin=True,
        )

    assert exc_info.value.status_code == 409
    assert "Project does not belong" in exc_info.value.detail["error"]


@pytest.mark.asyncio
async def test_should_report_missing_chatbot_scope_schema():
    with pytest.raises(HTTPException) as exc_info:
        await require_chatbot_project_access(
            SimpleNamespace(),
            chatbot_id="chatbot-1",
            user_api_key_dict=_internal_user(),
            require_admin=False,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["schema_status"] == "missing_schema"
    assert exc_info.value.detail["missing_schema"] == ["CavadaLabs_ChatbotTable"]
    assert "prisma migrate deploy" in exc_info.value.detail["migration_command"]


@pytest.mark.asyncio
async def test_should_validate_chatbot_project_references():
    db = _db(
        cavadalabs_projectmodelpolicytable=_UniqueDelegate(
            "policy_id", {"policy-1": _policy_row()}
        ),
        cavadalabs_ragcollectiontable=_UniqueDelegate(
            "collection_id",
            {
                "rag-company": _rag_collection_row(
                    collection_id="rag-company",
                    project_id=None,
                    scope="company",
                ),
                "rag-project": _rag_collection_row(collection_id="rag-project"),
            },
        ),
        cavadalabs_guardrailpolicytable=_UniqueDelegate(
            "policy_id", {"guardrail-1": _guardrail_policy_row()}
        ),
    )

    await validate_chatbot_project_references(
        db,
        company_id="company-1",
        project_id="project-1",
        chatbot_id="chatbot-1",
        model_policy_id="policy-1",
        assigned_rag_collection_ids=["rag-company", "rag-project"],
        assigned_guardrail_policy="guardrail-1",
    )

    db.cavadalabs_projectmodelpolicytable.find_unique.assert_awaited_once()
    assert db.cavadalabs_ragcollectiontable.find_unique.await_count == 2
    db.cavadalabs_guardrailpolicytable.find_unique.assert_awaited_once()


@pytest.mark.asyncio
async def test_should_reject_cross_project_rag_reference():
    db = _db(
        cavadalabs_ragcollectiontable=_UniqueDelegate(
            "collection_id",
            {
                "rag-2": _rag_collection_row(
                    collection_id="rag-2", project_id="project-2"
                )
            },
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        await validate_chatbot_project_references(
            db,
            company_id="company-1",
            project_id="project-1",
            assigned_rag_collection_ids=["rag-2"],
        )

    assert exc_info.value.status_code == 400
    assert "RAG collection does not belong" in exc_info.value.detail["error"]


@pytest.mark.asyncio
async def test_should_report_missing_schema_for_chatbot_references():
    with pytest.raises(HTTPException) as exc_info:
        await validate_chatbot_project_references(
            SimpleNamespace(),
            company_id="company-1",
            project_id="project-1",
            assigned_rag_collection_ids=["rag-1"],
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["schema_status"] == "missing_schema"
    assert exc_info.value.detail["missing_schema"] == ["CavadaLabs_RAGCollectionTable"]
    assert "prisma migrate deploy" in exc_info.value.detail["migration_command"]


class _RouterStub:
    def get_model_names(self, team_id=None):
        return ["model-b", "model-a"]

    def get_model_ids(self):
        return []


@pytest.mark.asyncio
async def test_should_build_lab_key_context_for_company_project_fallback():
    context = CavadaLabsRuntimeContext(
        company=CavadaLabsCompanyResponse.model_validate(_company_row().__dict__),
        project=CavadaLabsProjectResponse.model_validate(_project_row().__dict__),
        chatbot=CavadaLabsChatbotResponse.model_validate(_chatbot_row().__dict__),
        web_token=CavadaLabsWebTokenResponse.model_validate(_web_token_row().__dict__),
        primary_policy=CavadaLabsProjectModelPolicyResponse.model_validate(
            _policy_row(policy_id="policy-1", model_alias="model-a").__dict__
        ),
        fallback_policies=[
            CavadaLabsProjectModelPolicyResponse.model_validate(
                _policy_row(policy_id="policy-2", model_alias="model-b").__dict__
            )
        ],
    )
    user_api_key_dict = build_chatbot_runtime_user_api_key(
        context=context,
        token="clwt-token",
        payload={"fallbacks": ["model-c"]},
    )

    assert user_api_key_dict.cavadalabs_company_id == "company-1"
    assert user_api_key_dict.cavadalabs_project_id == "project-1"
    assert user_api_key_dict.team_id == "team-1"
    assert user_api_key_dict.org_id == "org-1"
    assert user_api_key_dict.metadata["cavadalabs_chatbot_id"] == "chatbot-1"
    assert user_api_key_dict.metadata["cavadalabs_web_token_id"] == "web-token-1"
    assert user_api_key_dict.metadata["cavadalabs"] == {
        "company_id": "company-1",
        "project_id": "project-1",
        "chatbot_id": "chatbot-1",
        "web_token_id": "web-token-1",
    }
    assert user_api_key_dict.metadata["spend_logs_metadata"] == {
        "cavadalabs_company_id": "company-1",
        "cavadalabs_project_id": "project-1",
        "cavadalabs_chatbot_id": "chatbot-1",
        "cavadalabs_web_token_id": "web-token-1",
    }
    assert user_api_key_dict.models == ["model-a", "model-b", "model-c"]

    data = {"messages": [{"role": "user", "content": "ciao"}]}
    prisma_client = SimpleNamespace(
        db=SimpleNamespace(
            cavadalabs_projectmodelpolicytable=SimpleNamespace(
                find_many=AsyncMock(
                    return_value=[
                        _policy_row(
                            policy_id="policy-runtime",
                            model_alias="model-b",
                            priority=1,
                        )
                    ]
                )
            )
        )
    )

    resolved_model = await apply_cavadalabs_project_model_fallback(
        data=data,
        route_type="acompletion",
        user_api_key_dict=user_api_key_dict,
        llm_router=_RouterStub(),
        prisma_client=prisma_client,
    )

    assert resolved_model == "model-b"
    assert data["model"] == "model-b"
