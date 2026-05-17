import json
import re
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from prisma import Json

from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.cavadalabs.dispatcher import (
    CavadaLabsDispatcherService,
    CavadaLabsRuntimeContext,
    hash_web_token,
)
from litellm.proxy.cavadalabs.chatbot_endpoints import (
    _finalize_chatbot_result,
    _should_bypass_router,
)
from litellm.proxy.cavadalabs.usage_tracking import (
    process_spend_logs_cavadalabs_ledger,
)
from litellm.proxy.cavadalabs.usage import (
    backfill_cavadalabs_usage_ledger_from_spend_logs,
    get_cavadalabs_daily_activity,
    get_cavadalabs_usage_diagnostics,
    repair_cavadalabs_usage_scope,
)
from litellm.proxy.management_endpoints import (
    cavadalabs_chatbot_admin_endpoints as chatbot_admin_endpoints,
)
from litellm.proxy.litellm_pre_call_utils import LiteLLMProxyRequestSetup
from litellm.proxy.spend_tracking.spend_tracking_utils import get_logging_payload
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsChatbotCreateRequest,
    CavadaLabsChatCompletionRequest,
    CavadaLabsCompanyCreateRequest,
    CavadaLabsProjectCreateRequest,
    CavadaLabsProjectModelPolicyCreateRequest,
    CavadaLabsUsageDiagnosticsAction,
    CavadaLabsUsageDiagnosticsStatus,
    CavadaLabsWebTokenCreateRequest,
)


def _admin() -> UserAPIKeyAuth:
    return UserAPIKeyAuth(
        api_key="sk-test",
        user_id="admin-user",
        user_role=LitellmUserRoles.PROXY_ADMIN,
    )


def _row(**kwargs):
    defaults = {
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "created_by": "admin-user",
        "updated_by": "admin-user",
    }
    return SimpleNamespace(**{**defaults, **kwargs})


def _prisma_model_block(schema: str, model_name: str) -> str:
    match = re.search(rf"model\s+{re.escape(model_name)}\s+\{{(.*?)\n\}}", schema, re.S)
    assert match is not None, f"Prisma model {model_name} not found"
    return match.group(1)


def _prisma_field_line(model_block: str, field_name: str) -> str:
    match = re.search(rf"^\s*{re.escape(field_name)}\s+(.+)$", model_block, re.M)
    assert match is not None, f"Prisma field {field_name} not found"
    return match.group(0)


def _migration_insert_columns(sql: str, table_name: str) -> list[str]:
    match = re.search(
        rf'INSERT\s+INTO\s+"{re.escape(table_name)}"\s*\((.*?)\)\s*SELECT',
        sql,
        re.I | re.S,
    )
    assert match is not None, f"INSERT into {table_name} not found"
    return re.findall(r'"([^"]+)"', match.group(1))


def _company_row(**kwargs):
    return _row(
        company_id=kwargs.pop("company_id", "company-1"),
        litellm_organization_id=kwargs.pop("litellm_organization_id", None),
        legal_name=kwargs.pop("legal_name", "ACME Spa"),
        billing_name=kwargs.pop("billing_name", None),
        vat_tax_id=kwargs.pop("vat_tax_id", None),
        billing_address=kwargs.pop("billing_address", {}),
        admin_emails=kwargs.pop("admin_emails", ["admin@acme.test"]),
        plan=kwargs.pop("plan", "production"),
        status=kwargs.pop("status", "active"),
        monthly_budget=kwargs.pop("monthly_budget", 500.0),
        metadata=kwargs.pop("metadata", {}),
        retention_policy=kwargs.pop("retention_policy", {}),
        default_guardrail_policy=kwargs.pop("default_guardrail_policy", None),
        default_billing_settings=kwargs.pop("default_billing_settings", {}),
        **kwargs,
    )


def _project_row(**kwargs):
    return _row(
        project_id=kwargs.pop("project_id", "project-1"),
        litellm_team_id=kwargs.pop("litellm_team_id", None),
        company_id=kwargs.pop("company_id", "company-1"),
        name=kwargs.pop("name", "Support"),
        status=kwargs.pop("status", "production"),
        allowed_models=kwargs.pop("allowed_models", ["cavadalabs/qwen3-32b"]),
        allowed_rag_collections=kwargs.pop("allowed_rag_collections", []),
        default_chatbot_settings=kwargs.pop("default_chatbot_settings", {}),
        default_guardrail_policy=kwargs.pop("default_guardrail_policy", None),
        budget=kwargs.pop("budget", 250.0),
        retention_policy_override=kwargs.pop("retention_policy_override", {}),
        metadata=kwargs.pop("metadata", {}),
        **kwargs,
    )


def _chatbot_row(**kwargs):
    return _row(
        chatbot_id=kwargs.pop("chatbot_id", "chatbot-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        project_id=kwargs.pop("project_id", "project-1"),
        name=kwargs.pop("name", "Support Widget"),
        status=kwargs.pop("status", "published"),
        system_prompt=kwargs.pop("system_prompt", "Answer from company docs."),
        prompt_version=kwargs.pop("prompt_version", 1),
        default_language=kwargs.pop("default_language", "it"),
        model_policy_id=kwargs.pop("model_policy_id", None),
        assigned_rag_collections=kwargs.pop("assigned_rag_collections", []),
        assigned_guardrail_policy=kwargs.pop("assigned_guardrail_policy", None),
        allowed_domains=kwargs.pop("allowed_domains", ["acme.test"]),
        widget_theme_config=kwargs.pop("widget_theme_config", {}),
        fallback_message=kwargs.pop("fallback_message", None),
        transcript_retention_policy=kwargs.pop("transcript_retention_policy", {}),
        metadata=kwargs.pop("metadata", {}),
        **kwargs,
    )


def _web_token_row(**kwargs):
    return _row(
        web_token_id=kwargs.pop("web_token_id", "web-token-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        project_id=kwargs.pop("project_id", "project-1"),
        chatbot_id=kwargs.pop("chatbot_id", "chatbot-1"),
        name=kwargs.pop("name", "widget"),
        token_prefix=kwargs.pop("token_prefix", "clwt-prefix"),
        status=kwargs.pop("status", "active"),
        allowed_domains=kwargs.pop("allowed_domains", ["acme.test"]),
        allowed_origins=kwargs.pop("allowed_origins", ["https://acme.test"]),
        route_allowlist=kwargs.pop(
            "route_allowlist", ["/cavadalabs/chatbots/messages"]
        ),
        ip_rpm_limit=kwargs.pop("ip_rpm_limit", 30),
        session_rpm_limit=kwargs.pop("session_rpm_limit", 10),
        session_budget=kwargs.pop("session_budget", 0.25),
        expires_at=kwargs.pop(
            "expires_at", datetime.now(timezone.utc) + timedelta(minutes=30)
        ),
        revoked_at=kwargs.pop("revoked_at", None),
        last_used_at=kwargs.pop("last_used_at", None),
        metadata=kwargs.pop("metadata", {}),
        **kwargs,
    )


def _model_policy_row(**kwargs):
    return _row(
        policy_id=kwargs.pop("policy_id", "policy-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        project_id=kwargs.pop("project_id", "project-1"),
        model_alias=kwargs.pop("model_alias", "cavadalabs/qwen3-32b"),
        provider=kwargs.pop("provider", "cavadalabs"),
        deployment_id=kwargs.pop("deployment_id", "deploy-1"),
        priority=kwargs.pop("priority", 10),
        enabled=kwargs.pop("enabled", True),
        fallback_enabled=kwargs.pop("fallback_enabled", True),
        require_json_output=kwargs.pop("require_json_output", False),
        force_json_output=kwargs.pop("force_json_output", False),
        json_schema=kwargs.pop("json_schema", None),
        strict_json=kwargs.pop("strict_json", False),
        repair_invalid_json=kwargs.pop("repair_invalid_json", False),
        retry_on_invalid_json=kwargs.pop("retry_on_invalid_json", False),
        require_no_think=kwargs.pop("require_no_think", True),
        no_think=kwargs.pop("no_think", False),
        reasoning_mode=kwargs.pop("reasoning_mode", None),
        hide_reasoning=kwargs.pop("hide_reasoning", False),
        strip_thinking_tags=kwargs.pop("strip_thinking_tags", False),
        prefer_loaded_model=kwargs.pop("prefer_loaded_model", True),
        max_cost_input=kwargs.pop("max_cost_input", None),
        max_cost_output=kwargs.pop("max_cost_output", None),
        required_capabilities=kwargs.pop("required_capabilities", ["tools"]),
        metadata=kwargs.pop("metadata", {}),
        **kwargs,
    )


def _node_row(**kwargs):
    return _row(
        node_id=kwargs.pop("node_id", "node-1"),
        display_name=kwargs.pop("display_name", "Inference Node"),
        hostname=kwargs.pop("hostname", "node-1.local"),
        location=kwargs.pop("location", "eu-west"),
        status=kwargs.pop("status", "online"),
        public_key=kwargs.pop("public_key", None),
        public_key_fingerprint=kwargs.pop("public_key_fingerprint", None),
        agent_version=kwargs.pop("agent_version", "1.0.0"),
        allowed_project_ids=kwargs.pop("allowed_project_ids", ["project-1"]),
        pools=kwargs.pop("pools", ["production"]),
        default_electricity_cost_per_kwh=kwargs.pop(
            "default_electricity_cost_per_kwh", None
        ),
        fixed_hourly_cost=kwargs.pop("fixed_hourly_cost", None),
        hardware_amortization_hourly_cost=kwargs.pop(
            "hardware_amortization_hourly_cost", None
        ),
        last_heartbeat_at=kwargs.pop("last_heartbeat_at", datetime.now(timezone.utc)),
        metadata=kwargs.pop("metadata", {}),
        **kwargs,
    )


def _gpu_row(**kwargs):
    return _row(
        gpu_id=kwargs.pop("gpu_id", "gpu-1"),
        node_id=kwargs.pop("node_id", "node-1"),
        vendor=kwargs.pop("vendor", "nvidia"),
        model=kwargs.pop("model", "A100"),
        uuid=kwargs.pop("uuid", "GPU-1"),
        vram_total_mb=kwargs.pop("vram_total_mb", 81920),
        status=kwargs.pop("status", "loaded"),
        loaded_model_ids=kwargs.pop("loaded_model_ids", ["deploy-1"]),
        metadata=kwargs.pop("metadata", {}),
        **kwargs,
    )


def _loaded_model_row(**kwargs):
    return _row(
        loaded_model_id=kwargs.pop("loaded_model_id", "deploy-1"),
        node_id=kwargs.pop("node_id", "node-1"),
        gpu_id=kwargs.pop("gpu_id", "gpu-1"),
        model_alias=kwargs.pop("model_alias", "cavadalabs/qwen3-32b"),
        provider=kwargs.pop("provider", "cavadalabs"),
        status=kwargs.pop("status", "loaded"),
        load_request_id=kwargs.pop("load_request_id", "model-load-request-1"),
        context_window=kwargs.pop("context_window", 32768),
        capabilities=kwargs.pop("capabilities", ["tools"]),
        loaded_at=kwargs.pop("loaded_at", datetime.now(timezone.utc)),
        unloaded_at=kwargs.pop("unloaded_at", None),
        last_used_at=kwargs.pop("last_used_at", None),
        metadata=kwargs.pop("metadata", {}),
        **kwargs,
    )


def _model_load_request_row(**kwargs):
    return _row(
        model_load_request_id=kwargs.pop(
            "model_load_request_id", "model-load-request-1"
        ),
        company_id=kwargs.pop("company_id", "company-1"),
        project_id=kwargs.pop("project_id", "project-1"),
        model_alias=kwargs.pop("model_alias", "cavadalabs/qwen3-32b"),
        provider=kwargs.pop("provider", "cavadalabs"),
        node_id=kwargs.pop("node_id", None),
        gpu_id=kwargs.pop("gpu_id", None),
        loaded_model_id=kwargs.pop("loaded_model_id", None),
        status=kwargs.pop("status", "queued"),
        priority=kwargs.pop("priority", 10),
        requested_by=kwargs.pop("requested_by", "cavadalabs-runtime"),
        requested_at=kwargs.pop("requested_at", datetime.now(timezone.utc)),
        expires_at=kwargs.pop("expires_at", None),
        last_error=kwargs.pop("last_error", None),
        metadata=kwargs.pop("metadata", {}),
        **kwargs,
    )


def _service():
    prisma_client = MagicMock()
    prisma_client.db = MagicMock()
    prisma_client.db.cavadalabs_companytable = MagicMock()
    prisma_client.db.cavadalabs_projecttable = MagicMock()
    prisma_client.db.cavadalabs_chatbottable = MagicMock()
    prisma_client.db.cavadalabs_webtokentable = MagicMock()
    prisma_client.db.cavadalabs_projectmodelpolicytable = MagicMock()
    prisma_client.db.cavadalabs_projectmembertable = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable = MagicMock()
    prisma_client.db.cavadalabs_loadedmodeltable = MagicMock()
    prisma_client.db.cavadalabs_modelloadrequesttable = MagicMock()
    prisma_client.db.cavadalabs_nodetable = MagicMock()
    prisma_client.db.cavadalabs_gputable = MagicMock()
    prisma_client.db.cavadalabs_gpulocktable = MagicMock()
    prisma_client.db.cavadalabs_auditlogtable = MagicMock()
    prisma_client.db.cavadalabs_auditlogtable.create = AsyncMock()
    prisma_client.db.cavadalabs_projectmembertable.upsert = AsyncMock()
    prisma_client.db.cavadalabs_companytable.find_unique = AsyncMock(return_value=None)
    prisma_client.db.cavadalabs_companytable.find_many = AsyncMock(return_value=[])
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[])
    prisma_client.db.cavadalabs_companytable.update = AsyncMock(
        return_value=_company_row(
            litellm_organization_id="cavadalabs-company-company-1"
        )
    )
    prisma_client.db.cavadalabs_projecttable.update = AsyncMock(
        return_value=_project_row(litellm_team_id="cavadalabs-project-project-1")
    )
    prisma_client.db.litellm_budgettable = MagicMock()
    prisma_client.db.litellm_organizationtable = MagicMock()
    prisma_client.db.litellm_teamtable = MagicMock()
    prisma_client.db.litellm_usertable = MagicMock()
    prisma_client.db.litellm_organizationmembership = MagicMock()
    prisma_client.db.litellm_budgettable.create = AsyncMock(
        return_value=SimpleNamespace(budget_id="budget-compat-1")
    )
    prisma_client.db.litellm_organizationtable.find_unique = AsyncMock(
        return_value=None
    )
    prisma_client.db.litellm_organizationtable.create = AsyncMock()
    prisma_client.db.litellm_organizationtable.update = AsyncMock()
    prisma_client.db.litellm_teamtable.find_unique = AsyncMock(return_value=None)
    prisma_client.db.litellm_teamtable.create = AsyncMock()
    prisma_client.db.litellm_teamtable.update = AsyncMock()
    prisma_client.db.litellm_usertable.find_first = AsyncMock(return_value=None)
    prisma_client.db.litellm_usertable.find_unique = AsyncMock(return_value=None)
    prisma_client.db.litellm_usertable.upsert = AsyncMock(
        side_effect=lambda **kwargs: SimpleNamespace(
            user_id=kwargs["data"]["create"]["user_id"],
            user_email=kwargs["data"]["create"].get("user_email"),
            team_id=None,
            sso_user_id=None,
            organization_id=None,
            object_permission_id=None,
            password=None,
            teams=kwargs["data"]["create"].get("teams", []),
            user_role=None,
            max_budget=None,
            spend=0.0,
            models=kwargs["data"]["create"].get("models", []),
            metadata={},
            max_parallel_requests=None,
            tpm_limit=None,
            rpm_limit=None,
            budget_duration=None,
            budget_reset_at=None,
            allowed_cache_controls=[],
            policies=[],
            model_spend={},
            model_max_budget={},
            created_at=None,
            updated_at=None,
        )
    )
    prisma_client.db.litellm_organizationmembership.upsert = AsyncMock()
    prisma_client.db.litellm_spendlogs = MagicMock()
    prisma_client.db.litellm_spendlogs.count = AsyncMock(return_value=0)
    prisma_client.db.litellm_spendlogs.find_many = AsyncMock(return_value=[])
    prisma_client.db.litellm_verificationtoken = MagicMock()
    prisma_client.db.litellm_verificationtoken.find_many = AsyncMock(return_value=[])
    prisma_client.db.litellm_deletedverificationtoken = MagicMock()
    prisma_client.db.litellm_deletedverificationtoken.find_many = AsyncMock(
        return_value=[]
    )
    return CavadaLabsDispatcherService(prisma_client), prisma_client


def test_should_bypass_router_only_for_resolved_cavadalabs_hosted_runtime():
    assert (
        _should_bypass_router(
            {
                "metadata": {
                    "cavadalabs": {
                        "runtime": {
                            "node_id": "node-1",
                            "loaded_model_id": "deploy-1",
                        }
                    }
                }
            }
        )
        is True
    )
    assert _should_bypass_router({"metadata": {"cavadalabs": {}}}) is False


async def _resolved_runtime_context(
    service: CavadaLabsDispatcherService,
    prisma_client,
    token: str = "clwt-test.secret",
) -> CavadaLabsRuntimeContext:
    prisma_client.db.cavadalabs_webtokentable.find_unique = AsyncMock(
        side_effect=[_web_token_row(), _web_token_row()]
    )
    prisma_client.db.cavadalabs_webtokentable.update = AsyncMock(
        return_value=_web_token_row()
    )
    prisma_client.db.cavadalabs_companytable.find_unique = AsyncMock(
        return_value=_company_row()
    )
    prisma_client.db.cavadalabs_projecttable.find_unique = AsyncMock(
        return_value=_project_row(
            allowed_models=["cavadalabs/qwen3-32b", "openai/gpt-4.1"]
        )
    )
    prisma_client.db.cavadalabs_chatbottable.find_unique = AsyncMock(
        return_value=_chatbot_row(assigned_guardrail_policy="safe-widget")
    )
    prisma_client.db.cavadalabs_projectmodelpolicytable.find_many = AsyncMock(
        return_value=[
            _model_policy_row(
                policy_id="policy-primary",
                model_alias="cavadalabs/qwen3-32b",
                provider="cavadalabs",
                priority=10,
                require_json_output=True,
                require_no_think=True,
            ),
            _model_policy_row(
                policy_id="policy-fallback",
                model_alias="openai/gpt-4.1",
                provider="openai",
                priority=20,
                require_no_think=False,
            ),
        ]
    )
    return await service.resolve_runtime_context(
        token=token,
        route="/cavadalabs/chatbots/messages",
        origin="https://acme.test",
    )


@pytest.mark.asyncio
async def test_should_create_company_and_write_cavadalabs_audit_log():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_companytable.create = AsyncMock(
        return_value=_company_row()
    )

    response = await service.create_company(
        CavadaLabsCompanyCreateRequest(
            legal_name=" ACME Spa ",
            admin_emails=["Admin@ACME.test", "admin@acme.test"],
            monthly_budget=500.0,
            plan="production",
        ),
        _admin(),
    )

    assert response.company_id == "company-1"
    assert response.litellm_organization_id == "cavadalabs-company-company-1"
    assert response.admin_emails == ["admin@acme.test"]
    create_data = prisma_client.db.cavadalabs_companytable.create.call_args.kwargs[
        "data"
    ]
    assert create_data["created_by"] == "admin-user"
    assert create_data["updated_by"] == "admin-user"
    assert isinstance(create_data["billing_address"], Json)
    assert create_data["billing_address"].data == {}
    organization_create_data = (
        prisma_client.db.litellm_organizationtable.create.call_args.kwargs["data"]
    )
    assert organization_create_data["organization_id"] == "cavadalabs-company-company-1"
    assert organization_create_data["organization_alias"] == "ACME Spa"
    prisma_client.db.cavadalabs_companytable.update.assert_awaited_once_with(
        where={"company_id": "company-1"},
        data={"litellm_organization_id": "cavadalabs-company-company-1"},
    )
    prisma_client.db.litellm_organizationmembership.upsert.assert_awaited_once()
    prisma_client.db.cavadalabs_auditlogtable.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_should_create_project_under_active_company():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_companytable.find_unique = AsyncMock(
        return_value=_company_row()
    )
    prisma_client.db.cavadalabs_projecttable.create = AsyncMock(
        return_value=_project_row()
    )

    response = await service.create_project(
        CavadaLabsProjectCreateRequest(
            company_id="company-1",
            name="Support",
            status="production",
            allowed_models=["cavadalabs/qwen3-32b", "cavadalabs/qwen3-32b"],
            budget=250.0,
        ),
        _admin(),
    )

    assert response.project_id == "project-1"
    assert response.litellm_team_id == "cavadalabs-project-project-1"
    assert response.allowed_models == ["cavadalabs/qwen3-32b"]
    create_data = prisma_client.db.cavadalabs_projecttable.create.call_args.kwargs[
        "data"
    ]
    assert create_data["company_id"] == "company-1"
    assert create_data["status"] == "production"
    team_create_data = prisma_client.db.litellm_teamtable.create.call_args.kwargs[
        "data"
    ]
    assert team_create_data["team_id"] == "cavadalabs-project-project-1"
    assert team_create_data["organization_id"] == "cavadalabs-company-company-1"
    assert team_create_data["models"] == ["cavadalabs/qwen3-32b"]
    prisma_client.db.cavadalabs_projecttable.update.assert_awaited_once_with(
        where={"project_id": "project-1"},
        data={"litellm_team_id": "cavadalabs-project-project-1"},
    )
    prisma_client.db.cavadalabs_projectmembertable.upsert.assert_awaited_once_with(
        where={
            "project_id_user_id": {
                "project_id": "project-1",
                "user_id": "admin-user",
            }
        },
        data={
            "create": {
                "project_id": "project-1",
                "user_id": "admin-user",
                "role": "project_admin",
                "created_by": "admin-user",
                "updated_by": "admin-user",
            },
            "update": {
                "role": "project_admin",
                "updated_by": "admin-user",
            },
        },
    )


@pytest.mark.asyncio
async def test_should_report_missing_native_project_membership_schema_on_project_create():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_companytable.find_unique = AsyncMock(
        return_value=_company_row()
    )
    prisma_client.db.cavadalabs_projecttable.create = AsyncMock(
        return_value=_project_row()
    )
    delattr(prisma_client.db, "cavadalabs_projectmembertable")

    with pytest.raises(HTTPException) as exc_info:
        await service.create_project(
            CavadaLabsProjectCreateRequest(
                company_id="company-1",
                name="Support",
                status="production",
                allowed_models=["cavadalabs/qwen3-32b"],
                budget=250.0,
            ),
            _admin(),
        )

    assert exc_info.value.status_code == 503
    assert "native project membership schema is missing" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_should_reject_chatbot_when_project_company_mismatch():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_projecttable.find_unique = AsyncMock(
        return_value=_project_row(company_id="other-company")
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.create_chatbot(
            CavadaLabsChatbotCreateRequest(
                company_id="company-1",
                project_id="project-1",
                name="Support Widget",
                status="published",
                system_prompt="Answer from company docs.",
            ),
            _admin(),
        )

    assert exc_info.value.status_code == 400
    assert "does not belong" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_should_create_browser_web_token_hash_only_and_return_secret_once():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_companytable.find_unique = AsyncMock(
        return_value=_company_row()
    )
    prisma_client.db.cavadalabs_projecttable.find_unique = AsyncMock(
        return_value=_project_row()
    )
    prisma_client.db.cavadalabs_chatbottable.find_unique = AsyncMock(
        return_value=_chatbot_row()
    )

    async def create_web_token(data):
        assert "token" not in data
        assert data["token_hash"] != data["token_prefix"]
        return _web_token_row(
            token_prefix=data["token_prefix"],
            allowed_domains=data["allowed_domains"],
            allowed_origins=data["allowed_origins"],
            expires_at=data["expires_at"],
        )

    prisma_client.db.cavadalabs_webtokentable.create = AsyncMock(
        side_effect=create_web_token
    )

    response = await service.create_web_token(
        CavadaLabsWebTokenCreateRequest(
            company_id="company-1",
            project_id="project-1",
            chatbot_id="chatbot-1",
            name="widget",
            allowed_origins=["https://acme.test"],
            expires_in_seconds=600,
        ),
        _admin(),
    )

    assert response.token.startswith("clwt-")
    assert response.web_token.token_prefix == response.token[:24]
    create_data = prisma_client.db.cavadalabs_webtokentable.create.call_args.kwargs[
        "data"
    ]
    assert create_data["token_hash"] == hash_web_token(response.token)
    assert "token_hash" not in response.web_token.model_dump()
    assert create_data["allowed_domains"] == ["acme.test"]
    token_metadata = create_data["metadata"].data
    assert token_metadata["cavadalabs_company_id"] == "company-1"
    assert token_metadata["cavadalabs_project_id"] == "project-1"
    assert token_metadata["cavadalabs_chatbot_id"] == "chatbot-1"
    assert token_metadata["cavadalabs_metadata_authenticated"] is True
    assert token_metadata["cavadalabs_metadata_source"] == "chatbot_runtime"
    assert token_metadata["cavadalabs"] == {
        "company_id": "company-1",
        "project_id": "project-1",
        "chatbot_id": "chatbot-1",
    }
    assert token_metadata["spend_logs_metadata"] == {
        "cavadalabs_company_id": "company-1",
        "cavadalabs_project_id": "project-1",
        "cavadalabs_chatbot_id": "chatbot-1",
    }


@pytest.mark.asyncio
async def test_should_list_web_tokens_with_visible_company_project_scope_filters():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_webtokentable.find_many = AsyncMock(
        return_value=[_web_token_row()]
    )

    web_tokens = await service.list_web_tokens(
        company_ids=["company-2", "company-1", "company-1"],
        project_ids=["project-1"],
    )

    assert len(web_tokens) == 1
    prisma_client.db.cavadalabs_webtokentable.find_many.assert_awaited_once()
    where = prisma_client.db.cavadalabs_webtokentable.find_many.call_args.kwargs[
        "where"
    ]
    assert where["company_id"] == {"in": ["company-1", "company-2"]}
    assert where["project_id"] == {"in": ["project-1"]}


@pytest.mark.asyncio
async def test_should_list_chatbots_with_visible_company_project_scope_filters():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_chatbottable.find_many = AsyncMock(
        return_value=[_chatbot_row()]
    )

    chatbots = await service.list_chatbots(
        company_ids=["company-2", "company-1"],
        project_ids=["project-1"],
    )

    assert len(chatbots) == 1
    prisma_client.db.cavadalabs_chatbottable.find_many.assert_awaited_once()
    where = prisma_client.db.cavadalabs_chatbottable.find_many.call_args.kwargs["where"]
    assert where["company_id"] == {"in": ["company-1", "company-2"]}
    assert where["project_id"] == {"in": ["project-1"]}


@pytest.mark.asyncio
async def test_should_not_query_chatbots_for_empty_visible_scope_filters():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_chatbottable.find_many = AsyncMock()

    chatbots = await service.list_chatbots(project_ids=[])

    assert chatbots == []
    prisma_client.db.cavadalabs_chatbottable.find_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_should_not_query_web_tokens_for_empty_visible_scope_filters():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_webtokentable.find_many = AsyncMock()

    web_tokens = await service.list_web_tokens(company_ids=[])

    assert web_tokens == []
    prisma_client.db.cavadalabs_webtokentable.find_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_should_resolve_chatbot_list_scope_from_project_membership(monkeypatch):
    _, prisma_client = _service()
    monkeypatch.setattr(
        chatbot_admin_endpoints,
        "_get_prisma_db",
        lambda: prisma_client.db,
    )
    prisma_client.db.litellm_organizationmembership.find_many = AsyncMock(
        return_value=[]
    )
    prisma_client.db.litellm_usertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(user_id="project-user", teams=["team-1"])
    )
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        side_effect=[[_project_row()], [_project_row()]]
    )

    resolved_scope = await chatbot_admin_endpoints._resolve_chatbot_list_scope(
        company_id=None,
        project_id=None,
        user_api_key_dict=UserAPIKeyAuth(
            user_id="project-user",
            user_role=LitellmUserRoles.INTERNAL_USER,
        ),
    )

    assert resolved_scope == (None, ["company-1"], None, ["project-1"])


@pytest.mark.asyncio
async def test_should_reject_chatbot_admin_mutation_for_project_operator(monkeypatch):
    service, prisma_client = _service()
    monkeypatch.setattr(
        chatbot_admin_endpoints,
        "_get_prisma_db",
        lambda: prisma_client.db,
    )
    monkeypatch.setattr(chatbot_admin_endpoints, "dispatcher_service", lambda: service)
    prisma_client.db.cavadalabs_chatbottable.find_unique = AsyncMock(
        return_value=_chatbot_row()
    )
    prisma_client.db.cavadalabs_projecttable.find_unique = AsyncMock(
        return_value=_project_row(litellm_team_id="team-1")
    )
    prisma_client.db.litellm_teamtable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            team_id="team-1",
            members_with_roles=[{"user_id": "operator-user", "role": "user"}],
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        await chatbot_admin_endpoints._require_chatbot_access(
            "chatbot-1",
            UserAPIKeyAuth(
                user_id="operator-user",
                user_role=LitellmUserRoles.INTERNAL_USER,
            ),
            require_admin=True,
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_should_allow_chatbot_admin_mutation_for_project_admin(monkeypatch):
    service, prisma_client = _service()
    monkeypatch.setattr(
        chatbot_admin_endpoints,
        "_get_prisma_db",
        lambda: prisma_client.db,
    )
    monkeypatch.setattr(chatbot_admin_endpoints, "dispatcher_service", lambda: service)
    prisma_client.db.cavadalabs_chatbottable.find_unique = AsyncMock(
        return_value=_chatbot_row()
    )
    prisma_client.db.cavadalabs_projecttable.find_unique = AsyncMock(
        return_value=_project_row(litellm_team_id="team-1")
    )
    prisma_client.db.litellm_teamtable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            team_id="team-1",
            members_with_roles=[{"user_id": "project-admin", "role": "admin"}],
        )
    )

    chatbot = await chatbot_admin_endpoints._require_chatbot_access(
        "chatbot-1",
        UserAPIKeyAuth(
            user_id="project-admin",
            user_role=LitellmUserRoles.INTERNAL_USER,
        ),
        require_admin=True,
    )

    assert chatbot.chatbot_id == "chatbot-1"


@pytest.mark.asyncio
async def test_should_resolve_web_token_list_scope_from_project_membership(monkeypatch):
    _, prisma_client = _service()
    monkeypatch.setattr(
        chatbot_admin_endpoints,
        "_get_prisma_db",
        lambda: prisma_client.db,
    )
    prisma_client.db.litellm_organizationmembership.find_many = AsyncMock(
        return_value=[]
    )
    prisma_client.db.litellm_usertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(user_id="project-user", teams=["team-1"])
    )
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        side_effect=[[_project_row()], [_project_row()]]
    )

    resolved_scope = await chatbot_admin_endpoints._resolve_web_token_list_scope(
        company_id=None,
        project_id=None,
        user_api_key_dict=UserAPIKeyAuth(
            user_id="project-user",
            user_role=LitellmUserRoles.INTERNAL_USER,
        ),
    )

    assert resolved_scope == (None, ["company-1"], None, ["project-1"])


@pytest.mark.asyncio
async def test_should_restrict_company_web_token_filter_to_visible_projects(
    monkeypatch,
):
    _, prisma_client = _service()
    monkeypatch.setattr(
        chatbot_admin_endpoints,
        "_get_prisma_db",
        lambda: prisma_client.db,
    )
    prisma_client.db.cavadalabs_companytable.find_unique = AsyncMock(
        return_value=_company_row()
    )
    prisma_client.db.litellm_organizationmembership.find_unique = AsyncMock(
        return_value=None
    )
    prisma_client.db.litellm_organizationmembership.find_many = AsyncMock(
        return_value=[]
    )
    prisma_client.db.litellm_usertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(user_id="project-user", teams=["team-1"])
    )
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        side_effect=[
            [_project_row(litellm_team_id="team-1")],
            [_project_row(litellm_team_id="team-1")],
        ]
    )

    resolved_scope = await chatbot_admin_endpoints._resolve_web_token_list_scope(
        company_id="company-1",
        project_id=None,
        user_api_key_dict=UserAPIKeyAuth(
            user_id="project-user",
            user_role=LitellmUserRoles.INTERNAL_USER,
        ),
    )

    assert resolved_scope == ("company-1", None, None, ["project-1"])


@pytest.mark.asyncio
async def test_should_validate_web_token_origin_domain_route_and_mark_last_used():
    service, prisma_client = _service()
    token = "clwt-test.secret"
    prisma_client.db.cavadalabs_webtokentable.find_unique = AsyncMock(
        return_value=_web_token_row()
    )
    prisma_client.db.cavadalabs_webtokentable.update = AsyncMock(
        return_value=_web_token_row()
    )

    result = await service.validate_web_token(
        token=token,
        route="/cavadalabs/chatbots/messages",
        origin="https://acme.test",
    )

    assert result.active is True
    assert result.company_id == "company-1"
    prisma_client.db.cavadalabs_webtokentable.find_unique.assert_awaited_once_with(
        where={"token_hash": hash_web_token(token)}
    )
    update_data = prisma_client.db.cavadalabs_webtokentable.update.call_args.kwargs[
        "data"
    ]
    assert "last_used_at" in update_data


@pytest.mark.asyncio
async def test_should_reject_web_token_for_unallowed_route():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_webtokentable.find_unique = AsyncMock(
        return_value=_web_token_row()
    )
    prisma_client.db.cavadalabs_webtokentable.update = AsyncMock()

    result = await service.validate_web_token(
        token="clwt-test.secret",
        route="/v1/chat/completions",
        origin="https://acme.test",
    )

    assert result.active is False
    assert result.reason == "route_not_allowed"
    prisma_client.db.cavadalabs_webtokentable.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_should_resolve_runtime_context_for_valid_web_token_and_policy():
    service, prisma_client = _service()

    context = await _resolved_runtime_context(service, prisma_client)

    assert context.company.company_id == "company-1"
    assert context.project.project_id == "project-1"
    assert context.chatbot.chatbot_id == "chatbot-1"
    assert context.web_token.web_token_id == "web-token-1"
    assert context.primary_policy.policy_id == "policy-primary"
    assert [policy.policy_id for policy in context.fallback_policies] == [
        "policy-fallback"
    ]


@pytest.mark.asyncio
async def test_should_build_chatbot_completion_payload_with_cavadalabs_metadata():
    service, prisma_client = _service()
    context = await _resolved_runtime_context(service, prisma_client)

    payload = service.build_chat_completion_payload(
        request_data=CavadaLabsChatCompletionRequest(
            session_id="session-1",
            client_request_id="client-request-1",
            messages=[{"role": "user", "content": "Ciao"}],
            metadata={"widget_version": "1.0.0"},
        ),
        context=context,
        origin="https://acme.test",
        request_ip="203.0.113.10",
    )

    assert payload["model"] == "cavadalabs/qwen3-32b"
    assert payload["fallbacks"] == ["openai/gpt-4.1"]
    assert payload["messages"][0] == {
        "role": "system",
        "content": "Answer from company docs.",
    }
    assert payload["messages"][1] == {"role": "user", "content": "Ciao"}
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["reasoning_effort"] == "none"
    assert payload["guardrails"] == ["safe-widget"]
    assert payload["metadata"]["widget_version"] == "1.0.0"
    assert payload["metadata"]["cavadalabs_company_id"] == "company-1"
    assert payload["metadata"]["cavadalabs_project_id"] == "project-1"
    assert payload["metadata"]["cavadalabs_chatbot_id"] == "chatbot-1"
    assert payload["metadata"]["cavadalabs_web_token_id"] == "web-token-1"
    assert payload["metadata"]["cavadalabs_metadata_authenticated"] is True
    assert payload["metadata"]["cavadalabs_metadata_source"] == "chatbot_runtime"
    assert payload["metadata"]["cavadalabs"]["policy_id"] == "policy-primary"
    assert payload["metadata"]["cavadalabs"]["client_request_id"] == "client-request-1"


@pytest.mark.asyncio
async def test_should_translate_advanced_json_and_reasoning_policy_to_payload():
    service, prisma_client = _service()
    context = await _resolved_runtime_context(service, prisma_client)
    json_schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }
    context = replace(
        context,
        primary_policy=context.primary_policy.model_copy(
            update={
                "require_json_output": False,
                "force_json_output": True,
                "json_schema": json_schema,
                "strict_json": True,
                "repair_invalid_json": True,
                "retry_on_invalid_json": True,
                "require_no_think": False,
                "no_think": True,
                "hide_reasoning": True,
                "strip_thinking_tags": True,
                "metadata": {"json_schema_name": "support_answer"},
            }
        ),
    )

    payload = service.build_chat_completion_payload(
        request_data=CavadaLabsChatCompletionRequest(
            session_id="session-1",
            messages=[{"role": "user", "content": "Rispondi in JSON"}],
        ),
        context=context,
        origin="https://acme.test",
        request_ip="203.0.113.10",
    )

    assert payload["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "support_answer",
            "schema": json_schema,
            "strict": True,
        },
    }
    assert payload["reasoning_effort"] == "none"
    cavadalabs_metadata = payload["metadata"]["cavadalabs"]
    assert cavadalabs_metadata["force_json_output"] is True
    assert cavadalabs_metadata["json_schema"] == json_schema
    assert cavadalabs_metadata["repair_invalid_json"] is True
    assert cavadalabs_metadata["retry_on_invalid_json"] is True
    assert cavadalabs_metadata["hide_reasoning"] is True
    assert cavadalabs_metadata["strip_thinking_tags"] is True


def test_should_strip_reasoning_repair_json_and_validate_schema_on_chatbot_result():
    payload = {
        "metadata": {
            "cavadalabs": {
                "force_json_output": True,
                "repair_invalid_json": True,
                "hide_reasoning": True,
                "strip_thinking_tags": True,
                "json_schema": {
                    "type": "object",
                    "properties": {"answer": {"type": "string"}},
                    "required": ["answer"],
                    "additionalProperties": False,
                },
            }
        }
    }
    result = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": '<think>internal</think> Here is JSON: {"answer": "ok"}',
                    "reasoning_content": "hidden chain",
                }
            }
        ]
    }

    finalized = _finalize_chatbot_result(result, payload)

    message = finalized["choices"][0]["message"]
    assert message["content"] == '{"answer":"ok"}'
    assert "reasoning_content" not in message


@pytest.mark.asyncio
async def test_should_resolve_loaded_cavadalabs_model_for_chatbot_runtime_payload():
    service, prisma_client = _service()
    context = await _resolved_runtime_context(service, prisma_client)
    prisma_client.db.cavadalabs_loadedmodeltable.find_unique = AsyncMock(
        return_value=_loaded_model_row(
            metadata={
                "api_base": "http://node-1.local:8000/v1/",
                "api_key": "node-runtime-key",
                "served_model_name": "qwen3-32b",
                "request_timeout": 45,
            }
        )
    )
    prisma_client.db.cavadalabs_loadedmodeltable.find_many = AsyncMock(return_value=[])
    prisma_client.db.cavadalabs_loadedmodeltable.update = AsyncMock(
        return_value=_loaded_model_row()
    )
    prisma_client.db.cavadalabs_nodetable.find_unique = AsyncMock(
        return_value=_node_row()
    )
    prisma_client.db.cavadalabs_gputable.find_unique = AsyncMock(
        return_value=_gpu_row()
    )

    payload = await service.prepare_chat_completion_payload(
        request_data=CavadaLabsChatCompletionRequest(
            session_id="session-1",
            messages=[{"role": "user", "content": "Ciao"}],
        ),
        context=context,
        origin="https://acme.test",
        request_ip="203.0.113.10",
    )

    assert payload["model"] == "openai/qwen3-32b"
    assert payload["api_base"] == "http://node-1.local:8000/v1"
    assert payload["api_key"] == "node-runtime-key"
    assert payload["custom_llm_provider"] == "openai"
    assert payload["request_timeout"] == 45
    assert payload["metadata"]["cavadalabs_node_id"] == "node-1"
    assert payload["metadata"]["cavadalabs_gpu_id"] == "gpu-1"
    assert payload["metadata"]["cavadalabs_loaded_model_id"] == "deploy-1"
    assert (
        payload["metadata"]["cavadalabs_model_load_request_id"]
        == "model-load-request-1"
    )
    assert payload["metadata"]["cavadalabs"]["model_alias"] == "cavadalabs/qwen3-32b"
    assert payload["metadata"]["cavadalabs"]["runtime"] == {
        "node_id": "node-1",
        "gpu_id": "gpu-1",
        "loaded_model_id": "deploy-1",
        "model_load_request_id": "model-load-request-1",
        "route_model": "openai/qwen3-32b",
        "custom_llm_provider": "openai",
        "api_base": "http://node-1.local:8000/v1",
        "api_key_configured": True,
        "context_window": 32768,
        "capabilities": ["tools"],
    }
    prisma_client.db.cavadalabs_loadedmodeltable.update.assert_awaited_once()


@pytest.mark.asyncio
async def test_should_reject_cavadalabs_runtime_without_loaded_model_endpoint():
    service, prisma_client = _service()
    context = await _resolved_runtime_context(service, prisma_client)
    context = replace(context, fallback_policies=[])
    prisma_client.db.cavadalabs_loadedmodeltable.find_unique = AsyncMock(
        return_value=_loaded_model_row(metadata={})
    )
    prisma_client.db.cavadalabs_loadedmodeltable.find_many = AsyncMock(return_value=[])
    prisma_client.db.cavadalabs_loadedmodeltable.update = AsyncMock()
    prisma_client.db.cavadalabs_nodetable.find_unique = AsyncMock(
        return_value=_node_row()
    )
    prisma_client.db.cavadalabs_gputable.find_unique = AsyncMock(
        return_value=_gpu_row()
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.prepare_chat_completion_payload(
            request_data=CavadaLabsChatCompletionRequest(
                session_id="session-1",
                messages=[{"role": "user", "content": "Ciao"}],
            ),
            context=context,
            origin="https://acme.test",
            request_ip="203.0.113.10",
        )

    assert exc_info.value.status_code == 409
    assert "missing_runtime_endpoint" in str(exc_info.value.detail)
    prisma_client.db.cavadalabs_loadedmodeltable.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_should_enqueue_load_request_and_route_to_external_fallback_when_primary_is_loadable():
    service, prisma_client = _service()
    context = await _resolved_runtime_context(service, prisma_client)
    prisma_client.db.cavadalabs_loadedmodeltable.find_unique = AsyncMock(
        return_value=None
    )
    prisma_client.db.cavadalabs_loadedmodeltable.find_many = AsyncMock(return_value=[])
    prisma_client.db.cavadalabs_nodetable.find_many = AsyncMock(
        return_value=[_node_row()]
    )
    prisma_client.db.cavadalabs_gputable.find_many = AsyncMock(
        return_value=[_gpu_row(status="available", loaded_model_ids=[])]
    )
    prisma_client.db.cavadalabs_gpulocktable.find_many = AsyncMock(return_value=[])
    prisma_client.db.cavadalabs_modelloadrequesttable.find_first = AsyncMock(
        return_value=None
    )
    prisma_client.db.cavadalabs_modelloadrequesttable.create = AsyncMock(
        return_value=_model_load_request_row()
    )

    payload = await service.prepare_chat_completion_payload(
        request_data=CavadaLabsChatCompletionRequest(
            session_id="session-1",
            messages=[{"role": "user", "content": "Ciao"}],
        ),
        context=context,
        origin="https://acme.test",
        request_ip="203.0.113.10",
    )

    assert payload["model"] == "openai/gpt-4.1"
    assert "api_base" not in payload
    assert "fallbacks" not in payload
    routing = payload["metadata"]["cavadalabs"]["routing"]
    assert routing["selected_policy_id"] == "policy-fallback"
    assert routing["skipped_policies"] == [
        {
            "policy_id": "policy-primary",
            "model_alias": "cavadalabs/qwen3-32b",
            "provider": "cavadalabs",
            "reason_codes": ["no_loaded_runtime"],
        }
    ]
    assert routing["queued_model_load_requests"] == [
        {
            "policy_id": "policy-primary",
            "model_alias": "cavadalabs/qwen3-32b",
            "model_load_request_id": "model-load-request-1",
            "status": "queued",
        }
    ]
    create_data = (
        prisma_client.db.cavadalabs_modelloadrequesttable.create.call_args.kwargs[
            "data"
        ]
    )
    assert create_data["requested_by"] == "cavadalabs-runtime"
    assert create_data["metadata"].data["source"] == "chatbot_runtime"


@pytest.mark.asyncio
async def test_should_enqueue_load_request_and_return_retry_when_no_policy_is_routable():
    service, prisma_client = _service()
    context = await _resolved_runtime_context(service, prisma_client)
    context = replace(context, fallback_policies=[])
    prisma_client.db.cavadalabs_loadedmodeltable.find_unique = AsyncMock(
        return_value=None
    )
    prisma_client.db.cavadalabs_loadedmodeltable.find_many = AsyncMock(return_value=[])
    prisma_client.db.cavadalabs_nodetable.find_many = AsyncMock(
        return_value=[_node_row()]
    )
    prisma_client.db.cavadalabs_gputable.find_many = AsyncMock(
        return_value=[_gpu_row(status="available", loaded_model_ids=[])]
    )
    prisma_client.db.cavadalabs_gpulocktable.find_many = AsyncMock(return_value=[])
    prisma_client.db.cavadalabs_modelloadrequesttable.find_first = AsyncMock(
        return_value=None
    )
    prisma_client.db.cavadalabs_modelloadrequesttable.create = AsyncMock(
        return_value=_model_load_request_row()
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.prepare_chat_completion_payload(
            request_data=CavadaLabsChatCompletionRequest(
                session_id="session-1",
                messages=[{"role": "user", "content": "Ciao"}],
            ),
            context=context,
            origin="https://acme.test",
            request_ip="203.0.113.10",
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.headers == {"retry-after": "30"}
    assert exc_info.value.detail["queued_model_load_requests"] == [
        {
            "policy_id": "policy-primary",
            "model_alias": "cavadalabs/qwen3-32b",
            "model_load_request_id": "model-load-request-1",
            "status": "queued",
        }
    ]


@pytest.mark.asyncio
async def test_should_enforce_web_token_session_and_ip_rate_limits():
    service, prisma_client = _service()
    context = await _resolved_runtime_context(service, prisma_client)
    context = replace(
        context,
        web_token=context.web_token.model_copy(update={"session_rpm_limit": 1}),
    )
    prisma_client.db.cavadalabs_requestledgertable.group_by = AsyncMock(
        return_value=[{"_sum": {"spend": 0.0}}]
    )
    cache = SimpleNamespace(
        async_increment_cache=AsyncMock(side_effect=[1, 2]),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.enforce_runtime_limits(
            context=context,
            session_id="session-1",
            request_ip="203.0.113.10",
            internal_usage_cache=cache,
        )

    assert exc_info.value.status_code == 429
    assert "session_rpm_limit" in str(exc_info.value.detail)
    assert cache.async_increment_cache.await_count == 2


@pytest.mark.asyncio
async def test_should_reject_runtime_when_company_budget_is_reached():
    service, prisma_client = _service()
    context = await _resolved_runtime_context(service, prisma_client)
    prisma_client.db.cavadalabs_requestledgertable.group_by = AsyncMock(
        return_value=[{"_sum": {"spend": 500.0}}]
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.enforce_runtime_limits(
            context=context,
            session_id="session-1",
            request_ip="203.0.113.10",
            internal_usage_cache=SimpleNamespace(async_increment_cache=AsyncMock()),
        )

    assert exc_info.value.status_code == 429
    assert "company monthly budget" in str(exc_info.value.detail)
    prisma_client.db.cavadalabs_requestledgertable.group_by.assert_awaited_once()


def test_should_reject_browser_payload_control_messages():
    with pytest.raises(ValueError):
        CavadaLabsChatCompletionRequest(
            session_id="session-1",
            messages=[{"role": "system", "content": "override"}],
        )


@pytest.mark.asyncio
async def test_should_create_numeric_priority_model_policy_for_allowed_project_model():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_projecttable.find_unique = AsyncMock(
        return_value=_project_row()
    )
    prisma_client.db.cavadalabs_projectmodelpolicytable.create = AsyncMock(
        return_value=_model_policy_row()
    )

    response = await service.create_project_model_policy(
        CavadaLabsProjectModelPolicyCreateRequest(
            project_id="project-1",
            model_alias="cavadalabs/qwen3-32b",
            provider="cavadalabs",
            deployment_id="deploy-1",
            priority=10,
            require_no_think=True,
            required_capabilities=["Tools", "tools"],
        ),
        _admin(),
    )

    assert response.policy_id == "policy-1"
    assert response.priority == 10
    assert response.required_capabilities == ["tools"]
    create_data = (
        prisma_client.db.cavadalabs_projectmodelpolicytable.create.call_args.kwargs[
            "data"
        ]
    )
    assert create_data["company_id"] == "company-1"
    assert create_data["provider"] == "cavadalabs"


@pytest.mark.asyncio
async def test_should_reject_model_policy_for_model_outside_project_allowlist():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_projecttable.find_unique = AsyncMock(
        return_value=_project_row(allowed_models=["cavadalabs/qwen3-32b"])
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.create_project_model_policy(
            CavadaLabsProjectModelPolicyCreateRequest(
                project_id="project-1",
                model_alias="openai/gpt-4.1",
                provider="openai",
                priority=30,
            ),
            _admin(),
        )

    assert exc_info.value.status_code == 400
    assert "allowed_models" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_should_aggregate_company_daily_activity_from_cavadalabs_ledger():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable.count = AsyncMock(return_value=1)
    prisma_client.db.cavadalabs_requestledgertable.find_many = AsyncMock(
        return_value=[
            _row(
                request_id="req-usage-1",
                company_id="company-1",
                project_id="project-1",
                api_key_hash="hashed-key",
                provider="cavadalabs",
                model="cavadalabs/qwen3-32b",
                prompt_tokens=12,
                completion_tokens=8,
                total_tokens=20,
                spend=0.12,
                status="success",
                metadata={"model_group": "cavadalabs/qwen3-32b", "call_type": "chat"},
                created_at=datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc),
            )
        ]
    )
    prisma_client.db.cavadalabs_companytable.find_many = AsyncMock(
        return_value=[_company_row()]
    )
    prisma_client.db.litellm_verificationtoken = MagicMock()
    prisma_client.db.litellm_verificationtoken.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(token="hashed-key", key_alias="Widget key", team_id=None)
        ]
    )

    response = await get_cavadalabs_daily_activity(
        prisma_client=prisma_client,
        entity_id_field="company_id",
        entity_id=["company-1"],
        start_date="2026-05-15",
        end_date="2026-05-15",
        model=None,
        api_key=None,
        page=1,
        page_size=100,
        timezone_offset_minutes=0,
    )

    assert response.metadata.total_spend == 0.12
    assert response.metadata.total_api_requests == 1
    assert (
        response.results[0].breakdown.entities["company-1"].metadata["alias"]
        == "ACME Spa"
    )
    assert (
        response.results[0].breakdown.api_keys["hashed-key"].metadata.key_alias
        == "Widget key"
    )


@pytest.mark.asyncio
async def test_should_filter_company_daily_activity_on_authoritative_ledger_fields():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable.count = AsyncMock(return_value=1)
    prisma_client.db.cavadalabs_requestledgertable.find_many = AsyncMock(
        return_value=[
            _row(
                request_id="req-filtered-company",
                company_id="company-1",
                project_id="project-1",
                api_key_hash="hashed-key",
                provider="cavadalabs",
                model="cavadalabs/qwen3-32b",
                prompt_tokens=12,
                completion_tokens=8,
                total_tokens=20,
                spend=0.12,
                status="success",
                metadata={"model_group": "cavadalabs/qwen3-32b", "call_type": "chat"},
                created_at=datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc),
            )
        ]
    )
    prisma_client.db.cavadalabs_companytable.find_many = AsyncMock(
        return_value=[_company_row()]
    )
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[
            _project_row(
                project_id="project-1",
                company_id="company-1",
                litellm_team_id="team-1",
            )
        ]
    )
    prisma_client.db.litellm_spendlogs.count = AsyncMock(return_value=1)

    response = await get_cavadalabs_daily_activity(
        prisma_client=prisma_client,
        entity_id_field="company_id",
        entity_id=["company-1"],
        start_date="2026-05-15",
        end_date="2026-05-15",
        model="cavadalabs/qwen3-32b",
        provider="cavadalabs",
        status_filter="success",
        api_key="hashed-key",
        min_spend=0.10,
        max_spend=0.20,
        page=1,
        page_size=100,
        timezone_offset_minutes=0,
    )

    where = prisma_client.db.cavadalabs_requestledgertable.count.call_args.kwargs[
        "where"
    ]
    assert where["company_id"] == {"in": ["company-1"]}
    assert {
        "OR": [
            {"model": "cavadalabs/qwen3-32b"},
            {
                "metadata": {
                    "path": ["model_group"],
                    "equals": "cavadalabs/qwen3-32b",
                }
            },
        ]
    } in where["AND"]
    assert where["provider"] == "cavadalabs"
    assert where["status"] == "success"
    assert where["api_key_hash"] == "hashed-key"
    assert where["spend"] == {"gte": 0.10, "lte": 0.20}
    assert response.metadata.total_spend == pytest.approx(0.12)
    assert response.metadata.total_successful_requests == 1


@pytest.mark.asyncio
async def test_should_aggregate_project_daily_activity_from_cavadalabs_ledger():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable.count = AsyncMock(return_value=1)
    prisma_client.db.cavadalabs_requestledgertable.find_many = AsyncMock(
        return_value=[
            _row(
                request_id="req-project-usage",
                company_id="company-1",
                project_id="project-1",
                api_key_hash="hashed-key",
                provider="openai",
                model="openai/gpt-4.1",
                prompt_tokens=30,
                completion_tokens=20,
                total_tokens=50,
                spend=0.42,
                status="success",
                metadata={"model_group": "openai/gpt-4.1", "call_type": "chat"},
                created_at=datetime(2026, 5, 15, 14, 0, tzinfo=timezone.utc),
            )
        ]
    )
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[_project_row(project_id="project-1", name="Support")]
    )
    prisma_client.db.litellm_spendlogs.count = AsyncMock(return_value=1)

    response = await get_cavadalabs_daily_activity(
        prisma_client=prisma_client,
        entity_id_field="project_id",
        entity_id=["project-1"],
        start_date="2026-05-15",
        end_date="2026-05-15",
        model=None,
        provider="openai",
        status_filter="success",
        api_key=None,
        page=1,
        page_size=100,
        timezone_offset_minutes=0,
    )

    where = prisma_client.db.cavadalabs_requestledgertable.count.call_args.kwargs[
        "where"
    ]
    assert where["project_id"] == {"in": ["project-1"]}
    assert where["provider"] == "openai"
    assert where["status"] == "success"
    assert response.metadata.total_spend == pytest.approx(0.42)
    assert (
        response.results[0].breakdown.entities["project-1"].metadata["alias"]
        == "Support"
    )


@pytest.mark.asyncio
async def test_should_reject_invalid_cavadalabs_usage_spend_range():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable.count = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await get_cavadalabs_daily_activity(
            prisma_client=prisma_client,
            entity_id_field="company_id",
            entity_id=["company-1"],
            start_date="2026-05-15",
            end_date="2026-05-15",
            model=None,
            api_key=None,
            min_spend=0.20,
            max_spend=0.10,
            page=1,
            page_size=100,
            timezone_offset_minutes=0,
        )

    assert exc_info.value.status_code == 400
    prisma_client.db.cavadalabs_requestledgertable.count.assert_not_awaited()


@pytest.mark.asyncio
async def test_should_make_cavadalabs_key_spend_visible_in_company_usage():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable.create_many = AsyncMock()
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[_project_row(project_id="project-1", company_id="company-1")]
    )

    request_metadata = {"metadata": {}}
    user_api_key_dict = UserAPIKeyAuth(
        api_key="hashed-key",
        key_alias="Cavada key",
        user_id="user-1",
        cavadalabs_company_id="company-1",
        cavadalabs_project_id="project-1",
    )
    LiteLLMProxyRequestSetup.add_user_api_key_auth_to_request_metadata(
        data=request_metadata,
        user_api_key_dict=user_api_key_dict,
        _metadata_variable_name="metadata",
    )

    start_time = datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)
    spend_log_payload = get_logging_payload(
        kwargs={
            "litellm_params": {"metadata": request_metadata["metadata"]},
            "call_type": "acompletion",
            "model": "openai/gpt-4.1",
            "custom_llm_provider": "openai",
            "response_cost": 0.21,
        },
        response_obj={
            "id": "req-key-visible",
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 7,
                "total_tokens": 18,
            },
        },
        start_time=start_time,
        end_time=start_time + timedelta(milliseconds=100),
    )

    await process_spend_logs_cavadalabs_ledger(
        prisma_client=prisma_client,
        logs_to_process=[spend_log_payload],
    )

    ledger_row = (
        prisma_client.db.cavadalabs_requestledgertable.create_many.call_args.kwargs[
            "data"
        ][0]
    )
    prisma_client.db.cavadalabs_requestledgertable.count = AsyncMock(return_value=1)
    prisma_client.db.cavadalabs_requestledgertable.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                **{
                    **ledger_row,
                    "metadata": ledger_row["metadata"].data,
                }
            )
        ]
    )
    prisma_client.db.cavadalabs_companytable.find_many = AsyncMock(
        return_value=[_company_row()]
    )
    prisma_client.db.litellm_verificationtoken = MagicMock()
    prisma_client.db.litellm_verificationtoken.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(token="hashed-key", key_alias="Cavada key", team_id=None)
        ]
    )

    response = await get_cavadalabs_daily_activity(
        prisma_client=prisma_client,
        entity_id_field="company_id",
        entity_id=["company-1"],
        start_date="2026-05-15",
        end_date="2026-05-15",
        model=None,
        api_key=None,
        page=1,
        page_size=100,
        timezone_offset_minutes=0,
    )

    assert response.metadata.total_spend == 0.21
    assert response.metadata.total_tokens == 18
    assert response.results[0].breakdown.entities["company-1"].metrics.spend == 0.21
    assert (
        response.results[0].breakdown.api_keys["hashed-key"].metadata.key_alias
        == "Cavada key"
    )


@pytest.mark.asyncio
async def test_should_repair_empty_company_usage_ledger_from_scoped_spend_logs():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable.create_many = AsyncMock()
    prisma_client.db.cavadalabs_requestledgertable.count = AsyncMock(side_effect=[0, 1])
    prisma_client.db.cavadalabs_requestledgertable.find_many = AsyncMock(
        return_value=[
            _row(
                request_id="req-repair-company",
                company_id="company-1",
                project_id="project-1",
                api_key_hash="hashed-key",
                provider="openai",
                model="openai/gpt-4.1",
                prompt_tokens=6,
                completion_tokens=4,
                total_tokens=10,
                spend=0.33,
                status="success",
                metadata={"model_group": "openai/gpt-4.1", "call_type": "chat"},
                created_at=datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc),
            )
        ]
    )
    prisma_client.db.cavadalabs_companytable.find_many = AsyncMock(
        return_value=[
            _company_row(
                company_id="company-1",
                litellm_organization_id="org-compat-1",
            )
        ]
    )
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[
            _project_row(
                company_id="company-1",
                project_id="project-1",
                litellm_team_id="team-compat-1",
            )
        ]
    )
    prisma_client.db.litellm_spendlogs = MagicMock()
    prisma_client.db.litellm_spendlogs.find_many = AsyncMock(
        side_effect=[
            [
                _row(
                    request_id="req-repair-company",
                    api_key="hashed-key",
                    spend=0.33,
                    prompt_tokens=6,
                    completion_tokens=4,
                    total_tokens=10,
                    startTime=datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc),
                    model="openai/gpt-4.1",
                    model_group="openai/gpt-4.1",
                    custom_llm_provider="openai",
                    team_id="team-compat-1",
                    organization_id="org-compat-1",
                    metadata={
                        "spend_logs_metadata": {
                            "cavadalabs_company_id": "company-1",
                            "cavadalabs_project_id": "project-1",
                        }
                    },
                    status="success",
                )
            ],
        ]
    )
    prisma_client.db.litellm_verificationtoken = MagicMock()
    prisma_client.db.litellm_verificationtoken.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(token="hashed-key", key_alias="Cavada key", team_id=None)
        ]
    )

    response = await get_cavadalabs_daily_activity(
        prisma_client=prisma_client,
        entity_id_field="company_id",
        entity_id=["company-1"],
        start_date="2026-05-15",
        end_date="2026-05-15",
        model=None,
        api_key=None,
        page=1,
        page_size=100,
        timezone_offset_minutes=0,
    )

    prisma_client.db.cavadalabs_requestledgertable.create_many.assert_awaited_once()
    ledger_row = (
        prisma_client.db.cavadalabs_requestledgertable.create_many.call_args.kwargs[
            "data"
        ][0]
    )
    assert ledger_row["request_id"] == "req-repair-company"
    assert ledger_row["company_id"] == "company-1"
    assert ledger_row["project_id"] == "project-1"
    spend_where = prisma_client.db.litellm_spendlogs.find_many.call_args.kwargs["where"]
    assert {"team_id": {"in": ["team-compat-1"]}} in spend_where["AND"][0]["OR"]
    assert response.metadata.total_spend == 0.33


@pytest.mark.asyncio
async def test_should_repair_partial_company_usage_ledger_from_scoped_spend_logs():
    _, prisma_client = _service()
    existing_row = _row(
        request_id="req-existing-company",
        company_id="company-1",
        project_id="project-1",
        api_key_hash="hashed-key",
        provider="openai",
        model="openai/gpt-4.1",
        prompt_tokens=5,
        completion_tokens=5,
        total_tokens=10,
        spend=0.10,
        status="success",
        metadata={"model_group": "openai/gpt-4.1", "call_type": "chat"},
        created_at=datetime(2026, 5, 15, 10, 0, tzinfo=timezone.utc),
    )
    repaired_row = _row(
        request_id="req-repaired-company",
        company_id="company-1",
        project_id="project-1",
        api_key_hash="hashed-key-2",
        provider="openai",
        model="openai/gpt-4.1",
        prompt_tokens=4,
        completion_tokens=6,
        total_tokens=10,
        spend=0.25,
        status="success",
        metadata={"model_group": "openai/gpt-4.1", "call_type": "chat"},
        created_at=datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc),
    )
    prisma_client.db.cavadalabs_requestledgertable = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable.create_many = AsyncMock()
    prisma_client.db.cavadalabs_requestledgertable.count = AsyncMock(side_effect=[1, 2])
    prisma_client.db.cavadalabs_requestledgertable.find_many = AsyncMock(
        return_value=[existing_row, repaired_row]
    )
    prisma_client.db.cavadalabs_companytable.find_many = AsyncMock(
        return_value=[
            _company_row(
                company_id="company-1",
                litellm_organization_id="org-compat-1",
            )
        ]
    )
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[
            _project_row(
                company_id="company-1",
                project_id="project-1",
                litellm_team_id="team-compat-1",
            )
        ]
    )
    prisma_client.db.litellm_spendlogs.count = AsyncMock(return_value=2)
    prisma_client.db.litellm_spendlogs.find_many = AsyncMock(
        return_value=[
            _row(
                request_id="req-repaired-company",
                api_key="hashed-key-2",
                spend=0.25,
                prompt_tokens=4,
                completion_tokens=6,
                total_tokens=10,
                startTime=datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc),
                model="openai/gpt-4.1",
                model_group="openai/gpt-4.1",
                custom_llm_provider="openai",
                team_id="team-compat-1",
                organization_id="org-compat-1",
                metadata={
                    "spend_logs_metadata": {
                        "cavadalabs_company_id": "company-1",
                        "cavadalabs_project_id": "project-1",
                    }
                },
                status="success",
            )
        ]
    )
    prisma_client.db.litellm_verificationtoken = MagicMock()
    prisma_client.db.litellm_verificationtoken.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(token="hashed-key", key_alias="Existing key", team_id=None),
            SimpleNamespace(
                token="hashed-key-2", key_alias="Repaired key", team_id=None
            ),
        ]
    )

    response = await get_cavadalabs_daily_activity(
        prisma_client=prisma_client,
        entity_id_field="company_id",
        entity_id=["company-1"],
        start_date="2026-05-15",
        end_date="2026-05-15",
        model=None,
        api_key=None,
        page=1,
        page_size=100,
        timezone_offset_minutes=0,
    )

    assert prisma_client.db.litellm_spendlogs.count.await_count == 2
    prisma_client.db.cavadalabs_requestledgertable.create_many.assert_awaited_once()
    ledger_row = (
        prisma_client.db.cavadalabs_requestledgertable.create_many.call_args.kwargs[
            "data"
        ][0]
    )
    assert ledger_row["request_id"] == "req-repaired-company"
    assert ledger_row["company_id"] == "company-1"
    assert ledger_row["project_id"] == "project-1"
    assert response.metadata.total_api_requests == 2
    assert response.metadata.total_spend == pytest.approx(0.35)


@pytest.mark.asyncio
async def test_should_repair_company_usage_from_cavadalabs_key_metadata():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable.create_many = AsyncMock()
    prisma_client.db.cavadalabs_requestledgertable.count = AsyncMock(side_effect=[0, 1])
    prisma_client.db.cavadalabs_requestledgertable.find_many = AsyncMock(
        return_value=[
            _row(
                request_id="req-key-context",
                company_id="company-1",
                project_id="project-1",
                api_key_hash="hashed-key",
                provider="openai",
                model="openai/gpt-4.1",
                prompt_tokens=8,
                completion_tokens=2,
                total_tokens=10,
                spend=0.18,
                status="success",
                metadata={"model_group": "openai/gpt-4.1", "call_type": "chat"},
                created_at=datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc),
            )
        ]
    )
    prisma_client.db.cavadalabs_companytable.find_many = AsyncMock(
        return_value=[_company_row(company_id="company-1")]
    )
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[
            _project_row(
                company_id="company-1",
                project_id="project-1",
                litellm_team_id=None,
            )
        ]
    )
    prisma_client.db.litellm_verificationtoken.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                token="hashed-key",
                key_alias="Cavada key",
                team_id=None,
                metadata={
                    "cavadalabs_company_id": "company-1",
                    "cavadalabs_project_id": "project-1",
                },
            )
        ]
    )
    prisma_client.db.litellm_spendlogs.find_many = AsyncMock(
        return_value=[
            _row(
                request_id="req-key-context",
                api_key="hashed-key",
                spend=0.18,
                prompt_tokens=8,
                completion_tokens=2,
                total_tokens=10,
                startTime=datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc),
                model="openai/gpt-4.1",
                model_group="openai/gpt-4.1",
                custom_llm_provider="openai",
                team_id=None,
                organization_id=None,
                metadata={},
                status="success",
            )
        ]
    )

    response = await get_cavadalabs_daily_activity(
        prisma_client=prisma_client,
        entity_id_field="company_id",
        entity_id=["company-1"],
        start_date="2026-05-15",
        end_date="2026-05-15",
        model=None,
        api_key=None,
        page=1,
        page_size=100,
        timezone_offset_minutes=0,
    )

    spend_where = prisma_client.db.litellm_spendlogs.find_many.call_args.kwargs["where"]
    assert {"api_key": {"in": ["hashed-key"]}} in spend_where["AND"][0]["OR"]
    prisma_client.db.cavadalabs_requestledgertable.create_many.assert_awaited_once()
    create_call = (
        prisma_client.db.cavadalabs_requestledgertable.create_many.call_args.kwargs
    )
    assert create_call["skip_duplicates"] is True
    ledger_row = create_call["data"][0]
    assert ledger_row["request_id"] == "req-key-context"
    assert ledger_row["company_id"] == "company-1"
    assert ledger_row["project_id"] == "project-1"
    assert response.metadata.total_spend == pytest.approx(0.18)


@pytest.mark.asyncio
async def test_should_keep_scoped_backfill_idempotent_when_ledger_rows_already_exist():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable.create_many = AsyncMock(
        return_value=SimpleNamespace(count=0)
    )
    prisma_client.db.cavadalabs_companytable.find_many = AsyncMock(
        return_value=[
            _company_row(
                company_id="company-1",
                litellm_organization_id="org-compat-1",
            )
        ]
    )
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[
            _project_row(
                company_id="company-1",
                project_id="project-1",
                litellm_team_id="team-compat-1",
            )
        ]
    )
    prisma_client.db.litellm_verificationtoken.find_many = AsyncMock(return_value=[])
    prisma_client.db.litellm_spendlogs.count = AsyncMock(return_value=1)
    prisma_client.db.litellm_spendlogs.find_many = AsyncMock(
        return_value=[
            _row(
                request_id="req-existing-ledger",
                api_key="hashed-key",
                spend=0.18,
                prompt_tokens=8,
                completion_tokens=2,
                total_tokens=10,
                startTime=datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc),
                model="openai/gpt-4.1",
                model_group="openai/gpt-4.1",
                custom_llm_provider="openai",
                team_id="team-compat-1",
                organization_id="org-compat-1",
                metadata={
                    "cavadalabs_company_id": "company-1",
                    "cavadalabs_project_id": "project-1",
                },
                status="success",
            )
        ]
    )

    result = await backfill_cavadalabs_usage_ledger_from_spend_logs(
        prisma_client=prisma_client,
        entity_id_field="company_id",
        entity_id=["company-1"],
        date_range={
            "gte": datetime(2026, 5, 15, tzinfo=timezone.utc),
            "lt": datetime(2026, 5, 16, tzinfo=timezone.utc),
        },
        model=None,
        provider=None,
        api_key=None,
    )

    assert result.attempted is True
    assert result.repaired is False
    assert result.scoped_spend_logs == 1
    assert result.processed_spend_logs == 1
    assert result.batches == 1
    create_call = prisma_client.db.cavadalabs_requestledgertable.create_many.call_args
    assert create_call.kwargs["skip_duplicates"] is True
    assert create_call.kwargs["data"][0]["request_id"] == "req-existing-ledger"


@pytest.mark.asyncio
async def test_should_repair_company_daily_activity_from_explicit_spend_metadata():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable.create_many = AsyncMock()
    prisma_client.db.cavadalabs_requestledgertable.count = AsyncMock(side_effect=[0, 1])
    prisma_client.db.cavadalabs_requestledgertable.find_many = AsyncMock(
        return_value=[
            _row(
                request_id="req-company-metadata",
                company_id="company-1",
                project_id="project-1",
                api_key_hash="hashed-key",
                provider="openai",
                model="openai/gpt-4.1",
                prompt_tokens=11,
                completion_tokens=5,
                total_tokens=16,
                spend=0.24,
                status="success",
                metadata={"model_group": "openai/gpt-4.1", "call_type": "chat"},
                created_at=datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc),
            )
        ]
    )
    prisma_client.db.cavadalabs_companytable.find_many = AsyncMock(
        return_value=[
            _company_row(
                company_id="company-1",
                litellm_organization_id=None,
            )
        ]
    )
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[
            _project_row(
                company_id="company-1",
                project_id="project-1",
                litellm_team_id=None,
            )
        ]
    )
    prisma_client.db.litellm_verificationtoken.find_many = AsyncMock(return_value=[])
    prisma_client.db.litellm_deletedverificationtoken = MagicMock()
    prisma_client.db.litellm_deletedverificationtoken.find_many = AsyncMock(
        return_value=[]
    )
    prisma_client.db.litellm_spendlogs.find_many = AsyncMock(
        return_value=[
            _row(
                request_id="req-company-metadata",
                api_key="hashed-key",
                spend=0.24,
                prompt_tokens=11,
                completion_tokens=5,
                total_tokens=16,
                startTime=datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc),
                model="openai/gpt-4.1",
                model_group="openai/gpt-4.1",
                custom_llm_provider="openai",
                team_id=None,
                organization_id=None,
                metadata={
                    "spend_logs_metadata": {
                        "cavadalabs_company_id": "company-1",
                        "cavadalabs_project_id": "project-1",
                    }
                },
                status="success",
            )
        ]
    )

    response = await get_cavadalabs_daily_activity(
        prisma_client=prisma_client,
        entity_id_field="company_id",
        entity_id=["company-1"],
        start_date="2026-05-15",
        end_date="2026-05-15",
        model=None,
        api_key=None,
        page=1,
        page_size=100,
        timezone_offset_minutes=0,
    )

    spend_where = prisma_client.db.litellm_spendlogs.find_many.call_args.kwargs["where"]
    assert {
        "AND": [
            {
                "metadata": {
                    "path": ["cavadalabs_company_id"],
                    "equals": "company-1",
                }
            },
            {
                "metadata": {
                    "path": ["cavadalabs_project_id"],
                    "equals": "project-1",
                }
            },
        ]
    } in spend_where["AND"][0]["OR"]
    assert {
        "AND": [
            {
                "metadata": {
                    "path": ["spend_logs_metadata", "cavadalabs_company_id"],
                    "equals": "company-1",
                }
            },
            {
                "metadata": {
                    "path": ["spend_logs_metadata", "cavadalabs_project_id"],
                    "equals": "project-1",
                }
            },
        ]
    } in spend_where["AND"][0]["OR"]
    prisma_client.db.cavadalabs_requestledgertable.create_many.assert_awaited_once()
    ledger_row = (
        prisma_client.db.cavadalabs_requestledgertable.create_many.call_args.kwargs[
            "data"
        ][0]
    )
    assert ledger_row["request_id"] == "req-company-metadata"
    assert ledger_row["company_id"] == "company-1"
    assert ledger_row["project_id"] == "project-1"
    assert response.metadata.total_api_requests == 1
    assert response.metadata.total_spend == pytest.approx(0.24)


@pytest.mark.asyncio
async def test_should_repair_company_daily_activity_from_deleted_key_metadata():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable.create_many = AsyncMock()
    prisma_client.db.cavadalabs_requestledgertable.count = AsyncMock(side_effect=[0, 1])
    prisma_client.db.cavadalabs_requestledgertable.find_many = AsyncMock(
        return_value=[
            _row(
                request_id="req-deleted-key-history",
                company_id="company-1",
                project_id="project-1",
                api_key_hash="deleted-key-hash",
                provider="openai",
                model="openai/gpt-4.1",
                prompt_tokens=9,
                completion_tokens=4,
                total_tokens=13,
                spend=0.19,
                status="success",
                metadata={"model_group": "openai/gpt-4.1", "call_type": "chat"},
                created_at=datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc),
            )
        ]
    )
    prisma_client.db.cavadalabs_companytable.find_many = AsyncMock(
        return_value=[_company_row(company_id="company-1")]
    )
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[_project_row(company_id="company-1", project_id="project-1")]
    )
    prisma_client.db.litellm_verificationtoken.find_many = AsyncMock(return_value=[])
    prisma_client.db.litellm_deletedverificationtoken.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                token="deleted-key-hash",
                team_id=None,
                organization_id=None,
                metadata={
                    "cavadalabs_company_id": "company-1",
                    "cavadalabs_project_id": "project-1",
                },
            )
        ]
    )
    prisma_client.db.litellm_spendlogs.find_many = AsyncMock(
        return_value=[
            _row(
                request_id="req-deleted-key-history",
                api_key="deleted-key-hash",
                spend=0.19,
                prompt_tokens=9,
                completion_tokens=4,
                total_tokens=13,
                startTime=datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc),
                model="openai/gpt-4.1",
                model_group="openai/gpt-4.1",
                custom_llm_provider="openai",
                team_id=None,
                organization_id=None,
                metadata={},
                status="success",
            )
        ]
    )

    response = await get_cavadalabs_daily_activity(
        prisma_client=prisma_client,
        entity_id_field="company_id",
        entity_id=["company-1"],
        start_date="2026-05-15",
        end_date="2026-05-15",
        model=None,
        api_key=None,
        page=1,
        page_size=100,
        timezone_offset_minutes=0,
    )

    spend_where = prisma_client.db.litellm_spendlogs.find_many.call_args.kwargs["where"]
    assert {"api_key": {"in": ["deleted-key-hash"]}} in spend_where["AND"][0]["OR"]
    prisma_client.db.cavadalabs_requestledgertable.create_many.assert_awaited_once()
    ledger_row = (
        prisma_client.db.cavadalabs_requestledgertable.create_many.call_args.kwargs[
            "data"
        ][0]
    )
    assert ledger_row["request_id"] == "req-deleted-key-history"
    assert ledger_row["company_id"] == "company-1"
    assert ledger_row["project_id"] == "project-1"
    assert response.metadata.total_api_requests == 1
    assert response.metadata.total_spend == pytest.approx(0.19)


@pytest.mark.asyncio
async def test_should_repair_company_daily_activity_from_deleted_key_team_mapping():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable.create_many = AsyncMock()
    prisma_client.db.cavadalabs_requestledgertable.count = AsyncMock(side_effect=[0, 1])
    prisma_client.db.cavadalabs_requestledgertable.find_many = AsyncMock(
        return_value=[
            _row(
                request_id="req-deleted-key-team",
                company_id="company-1",
                project_id="project-1",
                api_key_hash="deleted-key-hash",
                provider="openai",
                model="openai/gpt-4.1",
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                spend=0.23,
                status="success",
                metadata={"model_group": "openai/gpt-4.1", "call_type": "chat"},
                created_at=datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc),
            )
        ]
    )
    prisma_client.db.cavadalabs_companytable.find_many = AsyncMock(
        return_value=[_company_row(company_id="company-1")]
    )
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[
            _project_row(
                company_id="company-1",
                project_id="project-1",
                litellm_team_id="team-compat-1",
            )
        ]
    )
    prisma_client.db.litellm_verificationtoken.find_many = AsyncMock(return_value=[])
    prisma_client.db.litellm_deletedverificationtoken.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                token="deleted-key-hash",
                team_id="team-compat-1",
                organization_id=None,
                metadata={},
            )
        ]
    )
    prisma_client.db.litellm_spendlogs.find_many = AsyncMock(
        return_value=[
            _row(
                request_id="req-deleted-key-team",
                api_key="deleted-key-hash",
                spend=0.23,
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                startTime=datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc),
                model="openai/gpt-4.1",
                model_group="openai/gpt-4.1",
                custom_llm_provider="openai",
                metadata={},
                status="success",
            )
        ]
    )

    response = await get_cavadalabs_daily_activity(
        prisma_client=prisma_client,
        entity_id_field="company_id",
        entity_id=["company-1"],
        start_date="2026-05-15",
        end_date="2026-05-15",
        model=None,
        api_key=None,
        page=1,
        page_size=100,
        timezone_offset_minutes=0,
    )

    spend_where = prisma_client.db.litellm_spendlogs.find_many.call_args.kwargs["where"]
    assert {"api_key": {"in": ["deleted-key-hash"]}} in spend_where["AND"][0]["OR"]
    ledger_row = (
        prisma_client.db.cavadalabs_requestledgertable.create_many.call_args.kwargs[
            "data"
        ][0]
    )
    assert ledger_row["company_id"] == "company-1"
    assert ledger_row["project_id"] == "project-1"
    assert response.metadata.total_spend == pytest.approx(0.23)


@pytest.mark.asyncio
async def test_should_run_scoped_company_usage_repair_and_return_diagnostics():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable.create_many = AsyncMock()
    prisma_client.db.cavadalabs_requestledgertable.count = AsyncMock(return_value=1)
    prisma_client.db.cavadalabs_companytable.find_many = AsyncMock(
        return_value=[
            _company_row(
                company_id="company-1",
                litellm_organization_id=None,
            )
        ]
    )
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[
            _project_row(
                company_id="company-1",
                project_id="project-1",
                litellm_team_id=None,
            )
        ]
    )
    prisma_client.db.litellm_verificationtoken.find_many = AsyncMock(return_value=[])
    prisma_client.db.litellm_spendlogs.find_many = AsyncMock(
        return_value=[
            _row(
                request_id="req-company-repair-action",
                api_key="hashed-key",
                spend=0.28,
                prompt_tokens=12,
                completion_tokens=4,
                total_tokens=16,
                startTime=datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc),
                model="openai/gpt-4.1",
                model_group="openai/gpt-4.1",
                custom_llm_provider="openai",
                metadata={
                    "cavadalabs_company_id": "company-1",
                    "cavadalabs_project_id": "project-1",
                },
                status="success",
            )
        ]
    )
    prisma_client.db.litellm_spendlogs.count = AsyncMock(return_value=1)

    response = await repair_cavadalabs_usage_scope(
        prisma_client=prisma_client,
        entity_type="company",
        entity_id=["company-1"],
        start_date="2026-05-15",
        end_date="2026-05-15",
        timezone_offset_minutes=0,
    )

    assert response.attempted is True
    assert response.repaired is True
    assert response.scoped_spend_logs == 1
    assert response.processed_spend_logs == 1
    assert response.batches == 1
    assert response.diagnostics[0].status == CavadaLabsUsageDiagnosticsStatus.VISIBLE
    assert response.diagnostics[0].ledger_gap == 0
    create_call = (
        prisma_client.db.cavadalabs_requestledgertable.create_many.call_args.kwargs
    )
    assert create_call["skip_duplicates"] is True
    assert create_call["data"][0]["company_id"] == "company-1"
    assert create_call["data"][0]["project_id"] == "project-1"


@pytest.mark.asyncio
async def test_should_repair_empty_project_usage_ledger_from_team_mapping():
    _, prisma_client = _service()
    project = _project_row(
        company_id="company-1",
        project_id="project-1",
        litellm_team_id="team-compat-1",
    )
    prisma_client.db.cavadalabs_requestledgertable = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable.create_many = AsyncMock()
    prisma_client.db.cavadalabs_requestledgertable.count = AsyncMock(side_effect=[0, 1])
    prisma_client.db.cavadalabs_requestledgertable.find_many = AsyncMock(
        return_value=[
            _row(
                request_id="req-repair-project",
                company_id="company-1",
                project_id="project-1",
                api_key_hash="hashed-key",
                provider="openai",
                model="openai/gpt-4.1",
                prompt_tokens=3,
                completion_tokens=2,
                total_tokens=5,
                spend=0.09,
                status="success",
                metadata={"model_group": "openai/gpt-4.1", "call_type": "chat"},
                created_at=datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc),
            )
        ]
    )
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[project]
    )
    prisma_client.db.litellm_spendlogs = MagicMock()
    prisma_client.db.litellm_spendlogs.find_many = AsyncMock(
        return_value=[
            _row(
                request_id="req-repair-project",
                api_key="hashed-key",
                spend=0.09,
                prompt_tokens=3,
                completion_tokens=2,
                total_tokens=5,
                startTime=datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc),
                model="openai/gpt-4.1",
                model_group="openai/gpt-4.1",
                custom_llm_provider="openai",
                team_id="team-compat-1",
                organization_id=None,
                metadata={},
                status="success",
            )
        ]
    )
    prisma_client.db.litellm_verificationtoken = MagicMock()
    prisma_client.db.litellm_verificationtoken.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(token="hashed-key", key_alias="Cavada key", team_id=None)
        ]
    )

    response = await get_cavadalabs_daily_activity(
        prisma_client=prisma_client,
        entity_id_field="project_id",
        entity_id=["project-1"],
        start_date="2026-05-15",
        end_date="2026-05-15",
        model=None,
        api_key=None,
        page=1,
        page_size=100,
        timezone_offset_minutes=0,
    )

    prisma_client.db.cavadalabs_requestledgertable.create_many.assert_awaited_once()
    ledger_row = (
        prisma_client.db.cavadalabs_requestledgertable.create_many.call_args.kwargs[
            "data"
        ][0]
    )
    assert ledger_row["request_id"] == "req-repair-project"
    assert ledger_row["company_id"] == "company-1"
    assert ledger_row["project_id"] == "project-1"
    spend_where = prisma_client.db.litellm_spendlogs.find_many.call_args.kwargs["where"]
    assert {"team_id": "team-compat-1"} in spend_where["AND"][0]["OR"]
    assert response.metadata.total_spend == 0.09


@pytest.mark.asyncio
async def test_should_repair_project_daily_activity_from_explicit_spend_metadata():
    _, prisma_client = _service()
    project = _project_row(
        company_id="company-1",
        project_id="project-1",
        litellm_team_id=None,
    )
    prisma_client.db.cavadalabs_requestledgertable = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable.create_many = AsyncMock()
    prisma_client.db.cavadalabs_requestledgertable.count = AsyncMock(side_effect=[0, 1])
    prisma_client.db.cavadalabs_requestledgertable.find_many = AsyncMock(
        return_value=[
            _row(
                request_id="req-project-metadata",
                company_id="company-1",
                project_id="project-1",
                api_key_hash="hashed-key",
                provider="openai",
                model="openai/gpt-4.1",
                prompt_tokens=6,
                completion_tokens=7,
                total_tokens=13,
                spend=0.17,
                status="success",
                metadata={"model_group": "openai/gpt-4.1", "call_type": "chat"},
                created_at=datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc),
            )
        ]
    )
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[project]
    )
    prisma_client.db.litellm_verificationtoken = MagicMock()
    prisma_client.db.litellm_verificationtoken.find_many = AsyncMock(return_value=[])
    prisma_client.db.litellm_deletedverificationtoken = MagicMock()
    prisma_client.db.litellm_deletedverificationtoken.find_many = AsyncMock(
        return_value=[]
    )
    prisma_client.db.litellm_spendlogs = MagicMock()
    prisma_client.db.litellm_spendlogs.find_many = AsyncMock(
        return_value=[
            _row(
                request_id="req-project-metadata",
                api_key="hashed-key",
                spend=0.17,
                prompt_tokens=6,
                completion_tokens=7,
                total_tokens=13,
                startTime=datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc),
                model="openai/gpt-4.1",
                model_group="openai/gpt-4.1",
                custom_llm_provider="openai",
                team_id=None,
                organization_id=None,
                metadata={
                    "cavadalabs_company_id": "company-1",
                    "cavadalabs_project_id": "project-1",
                },
                status="success",
            )
        ]
    )

    response = await get_cavadalabs_daily_activity(
        prisma_client=prisma_client,
        entity_id_field="project_id",
        entity_id=["project-1"],
        start_date="2026-05-15",
        end_date="2026-05-15",
        model=None,
        api_key=None,
        page=1,
        page_size=100,
        timezone_offset_minutes=0,
    )

    spend_where = prisma_client.db.litellm_spendlogs.find_many.call_args.kwargs["where"]
    assert {"metadata": {"path": ["cavadalabs_project_id"], "equals": "project-1"}} in (
        spend_where["AND"][0]["OR"]
    )
    assert {
        "metadata": {
            "path": ["spend_logs_metadata", "cavadalabs_project_id"],
            "equals": "project-1",
        }
    } in spend_where["AND"][0]["OR"]
    prisma_client.db.cavadalabs_requestledgertable.create_many.assert_awaited_once()
    ledger_row = (
        prisma_client.db.cavadalabs_requestledgertable.create_many.call_args.kwargs[
            "data"
        ][0]
    )
    assert ledger_row["request_id"] == "req-project-metadata"
    assert ledger_row["company_id"] == "company-1"
    assert ledger_row["project_id"] == "project-1"
    assert response.metadata.total_api_requests == 1
    assert response.metadata.total_spend == pytest.approx(0.17)


@pytest.mark.asyncio
async def test_should_repair_project_daily_activity_from_deleted_key_metadata():
    _, prisma_client = _service()
    project = _project_row(
        company_id="company-1",
        project_id="project-1",
        litellm_team_id=None,
    )
    prisma_client.db.cavadalabs_requestledgertable = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable.create_many = AsyncMock()
    prisma_client.db.cavadalabs_requestledgertable.count = AsyncMock(side_effect=[0, 1])
    prisma_client.db.cavadalabs_requestledgertable.find_many = AsyncMock(
        return_value=[
            _row(
                request_id="req-project-deleted-key",
                company_id="company-1",
                project_id="project-1",
                api_key_hash="deleted-key-hash",
                provider="openai",
                model="openai/gpt-4.1",
                prompt_tokens=7,
                completion_tokens=8,
                total_tokens=15,
                spend=0.21,
                status="success",
                metadata={"model_group": "openai/gpt-4.1", "call_type": "chat"},
                created_at=datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc),
            )
        ]
    )
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[project]
    )
    prisma_client.db.litellm_verificationtoken.find_many = AsyncMock(return_value=[])
    prisma_client.db.litellm_deletedverificationtoken.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                token="deleted-key-hash",
                team_id=None,
                organization_id=None,
                metadata={
                    "cavadalabs_company_id": "company-1",
                    "cavadalabs_project_id": "project-1",
                },
            )
        ]
    )
    prisma_client.db.litellm_spendlogs.find_many = AsyncMock(
        return_value=[
            _row(
                request_id="req-project-deleted-key",
                api_key="deleted-key-hash",
                spend=0.21,
                prompt_tokens=7,
                completion_tokens=8,
                total_tokens=15,
                startTime=datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc),
                model="openai/gpt-4.1",
                model_group="openai/gpt-4.1",
                custom_llm_provider="openai",
                team_id=None,
                organization_id=None,
                metadata={},
                status="success",
            )
        ]
    )

    response = await get_cavadalabs_daily_activity(
        prisma_client=prisma_client,
        entity_id_field="project_id",
        entity_id=["project-1"],
        start_date="2026-05-15",
        end_date="2026-05-15",
        model=None,
        api_key=None,
        page=1,
        page_size=100,
        timezone_offset_minutes=0,
    )

    spend_where = prisma_client.db.litellm_spendlogs.find_many.call_args.kwargs["where"]
    assert {"api_key": {"in": ["deleted-key-hash"]}} in spend_where["AND"][0]["OR"]
    prisma_client.db.cavadalabs_requestledgertable.create_many.assert_awaited_once()
    ledger_row = (
        prisma_client.db.cavadalabs_requestledgertable.create_many.call_args.kwargs[
            "data"
        ][0]
    )
    assert ledger_row["request_id"] == "req-project-deleted-key"
    assert ledger_row["company_id"] == "company-1"
    assert ledger_row["project_id"] == "project-1"
    assert response.metadata.total_api_requests == 1
    assert response.metadata.total_spend == pytest.approx(0.21)


@pytest.mark.asyncio
async def test_should_run_scoped_project_usage_repair_and_report_missing_mapping():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable.count = AsyncMock(return_value=0)
    prisma_client.db.cavadalabs_requestledgertable.create_many = AsyncMock()
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[])
    prisma_client.db.litellm_spendlogs.find_many = AsyncMock(return_value=[])
    prisma_client.db.litellm_spendlogs.count = AsyncMock(return_value=0)

    response = await repair_cavadalabs_usage_scope(
        prisma_client=prisma_client,
        entity_type="project",
        entity_id=["missing-project"],
        start_date="2026-05-15",
        end_date="2026-05-15",
        timezone_offset_minutes=0,
    )

    assert response.attempted is False
    assert response.repaired is False
    assert response.processed_spend_logs == 0
    assert (
        response.diagnostics[0].status
        == CavadaLabsUsageDiagnosticsStatus.MISSING_COMPATIBILITY_MAPPING
    )
    assert response.diagnostics[0].missing_mappings == ["CavadaLabs project row"]
    prisma_client.db.litellm_spendlogs.find_many.assert_not_awaited()
    prisma_client.db.cavadalabs_requestledgertable.create_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_should_not_repair_project_usage_without_resolvable_project():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable.count = AsyncMock(return_value=0)
    prisma_client.db.cavadalabs_requestledgertable.find_many = AsyncMock(
        return_value=[]
    )
    prisma_client.db.cavadalabs_requestledgertable.create_many = AsyncMock()
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[])
    prisma_client.db.litellm_spendlogs = MagicMock()
    prisma_client.db.litellm_spendlogs.find_many = AsyncMock(return_value=[])

    response = await get_cavadalabs_daily_activity(
        prisma_client=prisma_client,
        entity_id_field="project_id",
        entity_id=["missing-project"],
        start_date="2026-05-15",
        end_date="2026-05-15",
        model=None,
        api_key=None,
        page=1,
        page_size=100,
        timezone_offset_minutes=0,
    )

    prisma_client.db.litellm_spendlogs.find_many.assert_not_awaited()
    prisma_client.db.cavadalabs_requestledgertable.create_many.assert_not_awaited()
    assert response.metadata.total_spend == 0
    assert response.metadata.total_api_requests == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("entity_id_field", ["company_id", "project_id"])
async def test_should_keep_empty_cavadalabs_usage_scope_empty(entity_id_field):
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable.count = AsyncMock(return_value=0)
    prisma_client.db.cavadalabs_requestledgertable.find_many = AsyncMock(
        return_value=[]
    )
    prisma_client.db.litellm_spendlogs = MagicMock()
    prisma_client.db.litellm_spendlogs.find_many = AsyncMock(return_value=[])

    response = await get_cavadalabs_daily_activity(
        prisma_client=prisma_client,
        entity_id_field=entity_id_field,
        entity_id=[],
        start_date="2026-05-15",
        end_date="2026-05-15",
        model=None,
        api_key=None,
        page=1,
        page_size=100,
        timezone_offset_minutes=0,
    )

    where = prisma_client.db.cavadalabs_requestledgertable.count.call_args.kwargs[
        "where"
    ]
    assert where[entity_id_field] == {"in": []}
    prisma_client.db.litellm_spendlogs.find_many.assert_not_awaited()
    assert response.metadata.total_spend == 0
    assert response.metadata.total_api_requests == 0


@pytest.mark.asyncio
async def test_should_diagnose_company_usage_backfill_when_spend_logs_exist():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable.count = AsyncMock(return_value=0)
    prisma_client.db.cavadalabs_companytable.find_many = AsyncMock(
        return_value=[
            _company_row(
                company_id="company-1",
                litellm_organization_id="org-compat-1",
            )
        ]
    )
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[
            _project_row(
                company_id="company-1",
                project_id="project-1",
                litellm_team_id="team-compat-1",
            )
        ]
    )
    prisma_client.db.litellm_spendlogs = MagicMock()
    prisma_client.db.litellm_spendlogs.count = AsyncMock(return_value=2)

    response = await get_cavadalabs_usage_diagnostics(
        prisma_client=prisma_client,
        entity_type="company",
        entity_id=["company-1"],
        start_date="2026-05-15",
        end_date="2026-05-15",
        timezone_offset_minutes=0,
    )

    diagnostic = response.diagnostics[0]
    assert (
        diagnostic.status == CavadaLabsUsageDiagnosticsStatus.SCOPED_BACKFILL_AVAILABLE
    )
    assert (
        diagnostic.recommended_action
        == CavadaLabsUsageDiagnosticsAction.RUN_SCOPED_BACKFILL
    )
    assert diagnostic.scoped_backfill_available is True
    assert diagnostic.ledger_gap == 2
    assert diagnostic.ledger_rows == 0
    assert diagnostic.attributable_spend_logs == 2
    assert diagnostic.metadata_spend_logs == 2
    assert diagnostic.compatibility_spend_logs == 2
    assert diagnostic.key_metadata_spend_logs == 0
    assert diagnostic.unmapped_spend_logs == 0
    assert diagnostic.missing_ledger_rows == 2
    assert (
        response.migration_name
        == "20260515161000_backfill_cavadalabs_request_ledger_from_metadata_key_hash"
    )
    assert response.migration_names == [
        "20260514120000_add_cavadalabs_dispatcher_tables",
        "20260515120000_add_cavadalabs_litellm_membership_mappings",
        "20260515122000_add_cavadalabs_usage_spend_log_indexes",
        "20260515123000_backfill_cavadalabs_request_ledger_from_spend_logs",
        "20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata",
        "20260515161000_backfill_cavadalabs_request_ledger_from_metadata_key_hash",
    ]
    assert [step.name for step in response.migration_plan] == response.migration_names
    assert "metadata" in response.migration_plan[-1].purpose
    assert "migrate deploy" in response.migration_command

    spend_where = next(
        call.kwargs["where"]
        for call in prisma_client.db.litellm_spendlogs.count.call_args_list
        if {"team_id": {"in": ["team-compat-1"]}} in call.kwargs["where"].get("OR", [])
    )
    assert spend_where["startTime"]["gte"] == datetime(
        2026, 5, 15, 0, 0, tzinfo=timezone.utc
    )
    assert {"team_id": {"in": ["team-compat-1"]}} in spend_where["OR"]
    assert {
        "AND": [
            {
                "metadata": {
                    "path": ["cavadalabs_company_id"],
                    "equals": "company-1",
                }
            },
            {
                "metadata": {
                    "path": ["cavadalabs_project_id"],
                    "equals": "project-1",
                }
            },
        ]
    } in spend_where["OR"]
    assert {
        "AND": [
            {"organization_id": "org-compat-1"},
            {
                "metadata": {
                    "path": ["cavadalabs_project_id"],
                    "equals": "project-1",
                }
            },
        ]
    } in spend_where["OR"]


@pytest.mark.asyncio
async def test_should_diagnose_company_usage_with_unmapped_internal_org_spend_logs():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable.count = AsyncMock(return_value=0)
    prisma_client.db.cavadalabs_companytable.find_many = AsyncMock(
        return_value=[
            _company_row(
                company_id="company-1",
                litellm_organization_id="org-compat-1",
            )
        ]
    )
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[])
    prisma_client.db.litellm_verificationtoken.find_many = AsyncMock(return_value=[])
    prisma_client.db.litellm_deletedverificationtoken.find_many = AsyncMock(
        return_value=[]
    )
    prisma_client.db.litellm_spendlogs.count = AsyncMock(return_value=2)

    response = await get_cavadalabs_usage_diagnostics(
        prisma_client=prisma_client,
        entity_type="company",
        entity_id=["company-1"],
        start_date="2026-05-15",
        end_date="2026-05-15",
        timezone_offset_minutes=0,
    )

    diagnostic = response.diagnostics[0]
    assert (
        diagnostic.status
        == CavadaLabsUsageDiagnosticsStatus.MISSING_COMPATIBILITY_MAPPING
    )
    assert (
        diagnostic.recommended_action
        == CavadaLabsUsageDiagnosticsAction.FIX_COMPATIBILITY_MAPPING
    )
    assert diagnostic.attributable_spend_logs == 0
    assert diagnostic.metadata_spend_logs == 0
    assert diagnostic.compatibility_spend_logs == 0
    assert diagnostic.key_metadata_spend_logs == 0
    assert diagnostic.unmapped_spend_logs == 2
    assert diagnostic.missing_mappings == [
        "CavadaLabs key metadata or Project compatibility mapping"
    ]
    assert "Missing compatibility mapping" in diagnostic.message
    spend_where = prisma_client.db.litellm_spendlogs.count.call_args.kwargs["where"]
    assert spend_where["OR"] == [{"organization_id": "org-compat-1"}]


@pytest.mark.asyncio
async def test_should_diagnose_company_usage_backfill_from_deleted_key_metadata():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable.count = AsyncMock(return_value=0)
    prisma_client.db.cavadalabs_companytable.find_many = AsyncMock(
        return_value=[_company_row(company_id="company-1")]
    )
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[_project_row(company_id="company-1", project_id="project-1")]
    )
    prisma_client.db.litellm_verificationtoken.find_many = AsyncMock(return_value=[])
    prisma_client.db.litellm_deletedverificationtoken.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                token="deleted-key-hash",
                team_id=None,
                organization_id=None,
                metadata={
                    "cavadalabs_company_id": "company-1",
                    "cavadalabs_project_id": "project-1",
                },
            )
        ]
    )
    prisma_client.db.litellm_spendlogs.count = AsyncMock(return_value=1)

    response = await get_cavadalabs_usage_diagnostics(
        prisma_client=prisma_client,
        entity_type="company",
        entity_id=["company-1"],
        start_date="2026-05-15",
        end_date="2026-05-15",
        timezone_offset_minutes=0,
    )

    diagnostic = response.diagnostics[0]
    assert (
        diagnostic.status == CavadaLabsUsageDiagnosticsStatus.SCOPED_BACKFILL_AVAILABLE
    )
    assert (
        diagnostic.recommended_action
        == CavadaLabsUsageDiagnosticsAction.RUN_SCOPED_BACKFILL
    )
    assert diagnostic.scoped_backfill_available is True
    assert diagnostic.ledger_gap == 1
    assert diagnostic.attributable_spend_logs == 1
    assert (
        response.migration_name
        == "20260515161000_backfill_cavadalabs_request_ledger_from_metadata_key_hash"
    )
    assert (
        "20260515161000_backfill_cavadalabs_request_ledger_from_metadata_key_hash"
        in response.migration_names
    )
    spend_where = prisma_client.db.litellm_spendlogs.count.call_args.kwargs["where"]
    assert {"api_key": {"in": ["deleted-key-hash"]}} in spend_where["OR"]


@pytest.mark.asyncio
async def test_should_diagnose_partial_company_usage_backfill_when_spend_logs_exceed_ledger():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable.count = AsyncMock(return_value=1)
    prisma_client.db.cavadalabs_companytable.find_many = AsyncMock(
        return_value=[
            _company_row(
                company_id="company-1",
                litellm_organization_id="org-compat-1",
            )
        ]
    )
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[
            _project_row(
                company_id="company-1",
                project_id="project-1",
                litellm_team_id="team-compat-1",
            )
        ]
    )
    prisma_client.db.litellm_spendlogs.count = AsyncMock(return_value=2)

    response = await get_cavadalabs_usage_diagnostics(
        prisma_client=prisma_client,
        entity_type="company",
        entity_id=["company-1"],
        start_date="2026-05-15",
        end_date="2026-05-15",
        timezone_offset_minutes=0,
    )

    diagnostic = response.diagnostics[0]
    assert (
        diagnostic.status == CavadaLabsUsageDiagnosticsStatus.SCOPED_BACKFILL_AVAILABLE
    )
    assert (
        diagnostic.recommended_action
        == CavadaLabsUsageDiagnosticsAction.RUN_SCOPED_BACKFILL
    )
    assert diagnostic.scoped_backfill_available is True
    assert diagnostic.ledger_gap == 1
    assert diagnostic.ledger_rows == 1
    assert diagnostic.attributable_spend_logs == 2


@pytest.mark.asyncio
async def test_should_diagnose_project_usage_missing_mapping_without_global_fallback():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable.count = AsyncMock(return_value=0)
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[_project_row(project_id="project-1", litellm_team_id=None)]
    )
    prisma_client.db.litellm_spendlogs = MagicMock()
    prisma_client.db.litellm_spendlogs.count = AsyncMock(return_value=0)

    response = await get_cavadalabs_usage_diagnostics(
        prisma_client=prisma_client,
        entity_type="project",
        entity_id=["project-1"],
        start_date="2026-05-15",
        end_date="2026-05-15",
        timezone_offset_minutes=0,
    )

    diagnostic = response.diagnostics[0]
    assert (
        diagnostic.status
        == CavadaLabsUsageDiagnosticsStatus.MISSING_COMPATIBILITY_MAPPING
    )
    assert diagnostic.missing_mappings == [
        "project litellm_team_id or CavadaLabs key metadata"
    ]
    spend_where = prisma_client.db.litellm_spendlogs.count.call_args.kwargs["where"]
    assert spend_where["OR"] == [
        {
            "metadata": {
                "path": ["cavadalabs_project_id"],
                "equals": "project-1",
            }
        },
        {"metadata": {"path": ["project_id"], "equals": "project-1"}},
        {
            "metadata": {
                "path": ["cavadalabs", "cavadalabs_project_id"],
                "equals": "project-1",
            }
        },
        {
            "metadata": {
                "path": ["cavadalabs", "project_id"],
                "equals": "project-1",
            }
        },
        {
            "metadata": {
                "path": ["spend_logs_metadata", "cavadalabs_project_id"],
                "equals": "project-1",
            }
        },
        {
            "metadata": {
                "path": ["spend_logs_metadata", "project_id"],
                "equals": "project-1",
            }
        },
    ]


@pytest.mark.asyncio
async def test_should_diagnose_project_usage_from_key_metadata_without_team_mapping():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable.count = AsyncMock(return_value=0)
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[
            _project_row(
                project_id="project-1",
                company_id="company-1",
                litellm_team_id=None,
            )
        ]
    )
    prisma_client.db.litellm_verificationtoken.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                token="hashed-key",
                metadata={
                    "cavadalabs_company_id": "company-1",
                    "cavadalabs_project_id": "project-1",
                },
            )
        ]
    )
    prisma_client.db.litellm_spendlogs.count = AsyncMock(return_value=1)

    response = await get_cavadalabs_usage_diagnostics(
        prisma_client=prisma_client,
        entity_type="project",
        entity_id=["project-1"],
        start_date="2026-05-15",
        end_date="2026-05-15",
        timezone_offset_minutes=0,
    )

    diagnostic = response.diagnostics[0]
    assert (
        diagnostic.status == CavadaLabsUsageDiagnosticsStatus.SCOPED_BACKFILL_AVAILABLE
    )
    assert (
        diagnostic.recommended_action
        == CavadaLabsUsageDiagnosticsAction.RUN_SCOPED_BACKFILL
    )
    assert diagnostic.scoped_backfill_available is True
    assert diagnostic.missing_mappings == []
    assert diagnostic.ledger_gap == 1
    spend_where = prisma_client.db.litellm_spendlogs.count.call_args.kwargs["where"]
    assert {"api_key": {"in": ["hashed-key"]}} in spend_where["OR"]


@pytest.mark.asyncio
async def test_should_diagnose_missing_project_without_spend_log_fallback():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable.count = AsyncMock(return_value=0)
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[])
    prisma_client.db.litellm_spendlogs = MagicMock()
    prisma_client.db.litellm_spendlogs.count = AsyncMock(return_value=0)

    response = await get_cavadalabs_usage_diagnostics(
        prisma_client=prisma_client,
        entity_type="project",
        entity_id=["missing-project"],
        start_date="2026-05-15",
        end_date="2026-05-15",
        timezone_offset_minutes=0,
    )

    diagnostic = response.diagnostics[0]
    assert (
        diagnostic.status
        == CavadaLabsUsageDiagnosticsStatus.MISSING_COMPATIBILITY_MAPPING
    )
    assert diagnostic.missing_mappings == ["CavadaLabs project row"]
    assert diagnostic.attributable_spend_logs == 0
    assert prisma_client.db.litellm_spendlogs.count.await_count == 1
    spend_count_where = prisma_client.db.litellm_spendlogs.count.call_args.kwargs[
        "where"
    ]
    assert spend_count_where["request_id"] == "__cavadalabs_schema_probe__"


def test_cavadalabs_ledger_backfill_migration_matches_schema_contract():
    repo_root = Path(__file__).parents[4]
    migration_path = (
        repo_root
        / "litellm-proxy-extras"
        / "litellm_proxy_extras"
        / "migrations"
        / "20260515123000_backfill_cavadalabs_request_ledger_from_spend_logs"
        / "migration.sql"
    )
    schema_path = repo_root / "litellm" / "proxy" / "schema.prisma"
    sql = migration_path.read_text()
    schema = schema_path.read_text()

    ledger_model = _prisma_model_block(schema, "CavadaLabs_RequestLedgerTable")
    spend_log_model = _prisma_model_block(schema, "LiteLLM_SpendLogs")
    company_model = _prisma_model_block(schema, "CavadaLabs_CompanyTable")
    project_model = _prisma_model_block(schema, "CavadaLabs_ProjectTable")

    request_id_line = _prisma_field_line(ledger_model, "request_id")
    assert "@unique" in request_id_line
    assert 'ON CONFLICT ("request_id") DO NOTHING' in sql

    metadata_line = _prisma_field_line(spend_log_model, "metadata")
    assert re.search(r"\bJson\?", metadata_line)
    assert "CREATE OR REPLACE FUNCTION _cavadalabs_safe_jsonb_object" in sql
    assert "EXCEPTION WHEN others THEN" in sql
    assert "DROP FUNCTION IF EXISTS _cavadalabs_safe_jsonb_object(jsonb)" in sql
    assert "jsonb_typeof" in sql
    assert 'FROM "LiteLLM_SpendLogs"' in sql
    assert 'WHERE s."metadata" IS NOT NULL' not in sql

    for source_field in [
        "request_id",
        "api_key",
        "metadata",
        "model",
        "model_group",
        "custom_llm_provider",
        "request_tags",
        "session_id",
        "team_id",
        "organization_id",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "spend",
        "status",
        "startTime",
    ]:
        _prisma_field_line(spend_log_model, source_field)

    expected_insert_columns = [
        "ledger_id",
        "request_id",
        "company_id",
        "project_id",
        "chatbot_id",
        "web_token_id",
        "session_id",
        "api_key_hash",
        "provider",
        "model",
        "node_id",
        "gpu_id",
        "loaded_model_id",
        "model_load_request_id",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "spend",
        "status",
        "metadata",
        "created_at",
    ]
    assert (
        _migration_insert_columns(sql, "CavadaLabs_RequestLedgerTable")
        == expected_insert_columns
    )
    for ledger_field in expected_insert_columns:
        _prisma_field_line(ledger_model, ledger_field)

    assert "c.company_id IS NOT NULL" in sql
    assert "c.project_id IS NOT NULL" in sql
    assert "cavadalabs_company_id" in sql
    assert "cavadalabs_project_id" in sql
    assert "spend_logs_metadata" in sql
    assert "CavadaLabs_ProjectTable" in sql
    assert "CavadaLabs_CompanyTable" in sql
    assert "litellm_team_id" in sql
    assert "litellm_organization_id" in sql
    assert "c.project_company_id IS NOT NULL" in sql
    assert "c.company_id = c.project_company_id" in sql
    assert "organization_company_id = c.project_company_id" in sql
    _prisma_field_line(company_model, "litellm_organization_id")
    _prisma_field_line(project_model, "litellm_team_id")


def test_cavadalabs_key_metadata_backfill_migration_matches_schema_contract():
    repo_root = Path(__file__).parents[4]
    migration_path = (
        repo_root
        / "litellm-proxy-extras"
        / "litellm_proxy_extras"
        / "migrations"
        / "20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata"
        / "migration.sql"
    )
    schema_path = repo_root / "litellm" / "proxy" / "schema.prisma"
    sql = migration_path.read_text()
    schema = schema_path.read_text()

    ledger_model = _prisma_model_block(schema, "CavadaLabs_RequestLedgerTable")
    spend_log_model = _prisma_model_block(schema, "LiteLLM_SpendLogs")
    verification_token_model = _prisma_model_block(schema, "LiteLLM_VerificationToken")
    deleted_token_model = _prisma_model_block(
        schema, "LiteLLM_DeletedVerificationToken"
    )
    company_model = _prisma_model_block(schema, "CavadaLabs_CompanyTable")
    project_model = _prisma_model_block(schema, "CavadaLabs_ProjectTable")

    assert 'FROM "LiteLLM_VerificationToken"' in sql
    assert 'FROM "LiteLLM_DeletedVerificationToken"' in sql
    assert "DISTINCT ON" in sql
    assert "source_priority" in sql
    assert 'ON k."token" = NULLIF(s."api_key", \'\')' in sql
    assert "key_company_id" in sql
    assert "key_project_id" in sql
    assert "key_team_id" in sql
    assert "key_organization_id" in sql
    assert "key_project" in sql
    assert "key_compat_project" in sql
    assert "key_compat_company" in sql
    assert "key_organization_company_id = c.project_company_id" in sql
    assert "c.company_id = c.project_company_id" in sql
    assert 'ON CONFLICT ("request_id") DO NOTHING' in sql
    assert "CREATE OR REPLACE FUNCTION _cavadalabs_safe_jsonb_object" in sql
    assert "DROP FUNCTION IF EXISTS _cavadalabs_safe_jsonb_object(jsonb)" in sql

    for source_field in ["request_id", "api_key", "metadata", "startTime"]:
        _prisma_field_line(spend_log_model, source_field)
    for key_field in ["token", "metadata", "team_id", "organization_id"]:
        _prisma_field_line(verification_token_model, key_field)
        _prisma_field_line(deleted_token_model, key_field)
    _prisma_field_line(company_model, "litellm_organization_id")
    for project_field in ["project_id", "company_id", "litellm_team_id"]:
        _prisma_field_line(project_model, project_field)
    for ledger_field in _migration_insert_columns(sql, "CavadaLabs_RequestLedgerTable"):
        _prisma_field_line(ledger_model, ledger_field)


def test_cavadalabs_metadata_key_hash_backfill_migration_matches_schema_contract():
    repo_root = Path(__file__).parents[4]
    migration_path = (
        repo_root
        / "litellm-proxy-extras"
        / "litellm_proxy_extras"
        / "migrations"
        / "20260515161000_backfill_cavadalabs_request_ledger_from_metadata_key_hash"
        / "migration.sql"
    )
    schema_path = repo_root / "litellm" / "proxy" / "schema.prisma"
    sql = migration_path.read_text()
    schema = schema_path.read_text()

    ledger_model = _prisma_model_block(schema, "CavadaLabs_RequestLedgerTable")
    spend_log_model = _prisma_model_block(schema, "LiteLLM_SpendLogs")
    verification_token_model = _prisma_model_block(schema, "LiteLLM_VerificationToken")
    deleted_token_model = _prisma_model_block(
        schema, "LiteLLM_DeletedVerificationToken"
    )
    project_model = _prisma_model_block(schema, "CavadaLabs_ProjectTable")

    assert "metadata_api_key_hash" in sql
    assert "user_api_key_hash" in sql
    assert "api_key_hash" in sql
    assert "spend_logs_metadata" in sql
    assert 'INNER JOIN key_context k' in sql
    assert 'ON k."token" = s.metadata_api_key_hash' in sql
    assert "candidate.value NOT LIKE 'sk-%'" in sql
    assert "c.company_id = c.project_company_id" in sql
    assert 'ON CONFLICT ("request_id") DO NOTHING' in sql

    for source_field in ["request_id", "metadata", "startTime"]:
        _prisma_field_line(spend_log_model, source_field)
    for key_field in ["token", "metadata", "team_id", "organization_id"]:
        _prisma_field_line(verification_token_model, key_field)
        _prisma_field_line(deleted_token_model, key_field)
    for project_field in ["project_id", "company_id", "litellm_team_id"]:
        _prisma_field_line(project_model, project_field)
    for ledger_field in _migration_insert_columns(sql, "CavadaLabs_RequestLedgerTable"):
        _prisma_field_line(ledger_model, ledger_field)


def test_cavadalabs_spend_log_repair_indexes_match_usage_filters():
    repo_root = Path(__file__).parents[4]
    migration_path = (
        repo_root
        / "litellm-proxy-extras"
        / "litellm_proxy_extras"
        / "migrations"
        / "20260515122000_add_cavadalabs_usage_spend_log_indexes"
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
        spend_log_model = _prisma_model_block(schema_text, "LiteLLM_SpendLogs")
        for field_name in [
            "api_key",
            "team_id",
            "organization_id",
            "model",
            "model_group",
            "startTime",
            "metadata",
        ]:
            _prisma_field_line(spend_log_model, field_name)
        for index_line in [
            "@@index([api_key, startTime])",
            "@@index([team_id, startTime])",
            "@@index([organization_id, startTime])",
            "@@index([model, startTime])",
            "@@index([model_group, startTime])",
        ]:
            assert index_line in spend_log_model

    for index_name in [
        "LiteLLM_SpendLogs_api_key_startTime_idx",
        "LiteLLM_SpendLogs_team_id_startTime_idx",
        "LiteLLM_SpendLogs_organization_id_startTime_idx",
        "LiteLLM_SpendLogs_model_startTime_idx",
        "LiteLLM_SpendLogs_model_group_startTime_idx",
        "LiteLLM_SpendLogs_metadata_gin_idx",
    ]:
        assert f'CREATE INDEX IF NOT EXISTS "{index_name}"' in sql
    assert 'USING GIN ("metadata")' in sql


@pytest.mark.asyncio
async def test_should_mirror_cavadalabs_spend_log_to_request_ledger():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable.create_many = AsyncMock()
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                project_id="project-1",
                company_id="company-1",
                litellm_team_id=None,
            )
        ]
    )
    start_time = datetime.now(timezone.utc)

    await process_spend_logs_cavadalabs_ledger(
        prisma_client=prisma_client,
        logs_to_process=[
            {
                "request_id": "req-1",
                "metadata": json.dumps(
                    {
                        "spend_logs_metadata": {
                            "cavadalabs_company_id": "company-1",
                            "cavadalabs_project_id": "project-1",
                            "cavadalabs_chatbot_id": "chatbot-1",
                            "cavadalabs_web_token_id": "web-token-1",
                            "cavadalabs_node_id": "node-1",
                            "cavadalabs_gpu_id": "gpu-1",
                            "cavadalabs_model_alias": "cavadalabs/qwen3-32b",
                            "cavadalabs_provider": "cavadalabs",
                            "policy_id": "policy-1",
                            "guardrails": ["safe-widget"],
                            "rag": {
                                "collection_ids": ["collection-1"],
                                "document_ids": ["document-1"],
                                "result_count": 1,
                            },
                        }
                    }
                ),
                "api_key": "hashed-key",
                "custom_llm_provider": "openai",
                "model": "openai/qwen3-32b",
                "session_id": "session-1",
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "spend": 0.05,
                "status": "success",
                "startTime": start_time,
            }
        ],
    )

    prisma_client.db.cavadalabs_requestledgertable.create_many.assert_awaited_once()
    create_call = (
        prisma_client.db.cavadalabs_requestledgertable.create_many.call_args.kwargs
    )
    assert create_call["skip_duplicates"] is True
    ledger_row = create_call["data"][0]
    assert ledger_row["company_id"] == "company-1"
    assert ledger_row["project_id"] == "project-1"
    assert ledger_row["chatbot_id"] == "chatbot-1"
    assert ledger_row["web_token_id"] == "web-token-1"
    assert ledger_row["session_id"] == "session-1"
    assert ledger_row["node_id"] == "node-1"
    assert ledger_row["gpu_id"] == "gpu-1"
    assert ledger_row["provider"] == "cavadalabs"
    assert ledger_row["model"] == "cavadalabs/qwen3-32b"
    assert ledger_row["total_tokens"] == 15
    assert isinstance(ledger_row["metadata"], Json)
    ledger_metadata = ledger_row["metadata"].data
    assert ledger_metadata["cavadalabs"]["policy_id"] == "policy-1"
    assert ledger_metadata["cavadalabs"]["guardrails"] == ["safe-widget"]
    assert ledger_metadata["cavadalabs"]["rag"]["collection_ids"] == ["collection-1"]


@pytest.mark.asyncio
async def test_should_use_authoritative_key_context_for_cavadalabs_ledger():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable.create_many = AsyncMock()
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[
            _project_row(
                project_id="project-authoritative",
                company_id="company-authoritative",
            )
        ]
    )

    await process_spend_logs_cavadalabs_ledger(
        prisma_client=prisma_client,
        logs_to_process=[
            {
                "request_id": "req-authoritative",
                "metadata": json.dumps(
                    {
                        "cavadalabs_company_id": "company-authoritative",
                        "cavadalabs_project_id": "project-authoritative",
                        "spend_logs_metadata": {
                            "cavadalabs_company_id": "company-spoofed",
                            "cavadalabs_project_id": "project-spoofed",
                        },
                    }
                ),
                "api_key": "hashed-key",
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

    create_call = (
        prisma_client.db.cavadalabs_requestledgertable.create_many.call_args.kwargs
    )
    ledger_row = create_call["data"][0]
    assert ledger_row["company_id"] == "company-authoritative"
    assert ledger_row["project_id"] == "project-authoritative"


@pytest.mark.asyncio
async def test_should_resolve_runtime_cavadalabs_ledger_from_key_metadata():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable.create_many = AsyncMock()
    prisma_client.db.litellm_verificationtoken.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                token="hashed-key",
                team_id=None,
                organization_id=None,
                metadata={
                    "cavadalabs_company_id": "company-1",
                    "cavadalabs_project_id": "project-1",
                },
            )
        ]
    )
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[_project_row(project_id="project-1", company_id="company-1")]
    )

    await process_spend_logs_cavadalabs_ledger(
        prisma_client=prisma_client,
        logs_to_process=[
            {
                "request_id": "req-key-metadata-runtime",
                "metadata": json.dumps({}),
                "api_key": "hashed-key",
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

    prisma_client.db.litellm_verificationtoken.find_many.assert_awaited_once_with(
        where={"token": {"in": ["hashed-key"]}}
    )
    prisma_client.db.cavadalabs_requestledgertable.create_many.assert_awaited_once()
    ledger_row = (
        prisma_client.db.cavadalabs_requestledgertable.create_many.call_args.kwargs[
            "data"
        ][0]
    )
    assert ledger_row["request_id"] == "req-key-metadata-runtime"
    assert ledger_row["company_id"] == "company-1"
    assert ledger_row["project_id"] == "project-1"


@pytest.mark.asyncio
async def test_should_resolve_runtime_cavadalabs_ledger_from_deleted_key_metadata():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable.create_many = AsyncMock()
    prisma_client.db.litellm_verificationtoken.find_many = AsyncMock(return_value=[])
    prisma_client.db.litellm_deletedverificationtoken.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                token="deleted-key-hash",
                team_id=None,
                organization_id=None,
                metadata={
                    "cavadalabs_company_id": "company-1",
                    "cavadalabs_project_id": "project-1",
                },
            )
        ]
    )
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[_project_row(project_id="project-1", company_id="company-1")]
    )

    await process_spend_logs_cavadalabs_ledger(
        prisma_client=prisma_client,
        logs_to_process=[
            {
                "request_id": "req-deleted-key-runtime",
                "metadata": json.dumps({}),
                "api_key": "deleted-key-hash",
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

    prisma_client.db.litellm_verificationtoken.find_many.assert_awaited_once_with(
        where={"token": {"in": ["deleted-key-hash"]}}
    )
    prisma_client.db.litellm_deletedverificationtoken.find_many.assert_awaited_once_with(
        where={"token": {"in": ["deleted-key-hash"]}}
    )
    prisma_client.db.cavadalabs_requestledgertable.create_many.assert_awaited_once()
    ledger_row = (
        prisma_client.db.cavadalabs_requestledgertable.create_many.call_args.kwargs[
            "data"
        ][0]
    )
    assert ledger_row["request_id"] == "req-deleted-key-runtime"
    assert ledger_row["company_id"] == "company-1"
    assert ledger_row["project_id"] == "project-1"


@pytest.mark.asyncio
async def test_should_resolve_runtime_cavadalabs_ledger_from_deleted_key_team_mapping():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable.create_many = AsyncMock()
    prisma_client.db.litellm_verificationtoken.find_many = AsyncMock(return_value=[])
    prisma_client.db.litellm_deletedverificationtoken.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                token="deleted-key-hash",
                team_id="team-compat",
                organization_id="org-compat",
                metadata={},
            )
        ]
    )
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[
            _project_row(
                project_id="project-compat",
                company_id="company-compat",
                litellm_team_id="team-compat",
            )
        ]
    )
    prisma_client.db.cavadalabs_companytable.find_many = AsyncMock(
        return_value=[
            _company_row(
                company_id="company-compat",
                litellm_organization_id="org-compat",
            )
        ]
    )

    await process_spend_logs_cavadalabs_ledger(
        prisma_client=prisma_client,
        logs_to_process=[
            {
                "request_id": "req-deleted-key-team-runtime",
                "metadata": json.dumps({}),
                "api_key": "deleted-key-hash",
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

    prisma_client.db.cavadalabs_requestledgertable.create_many.assert_awaited_once()
    ledger_row = (
        prisma_client.db.cavadalabs_requestledgertable.create_many.call_args.kwargs[
            "data"
        ][0]
    )
    assert ledger_row["request_id"] == "req-deleted-key-team-runtime"
    assert ledger_row["company_id"] == "company-compat"
    assert ledger_row["project_id"] == "project-compat"


@pytest.mark.asyncio
async def test_should_resolve_runtime_cavadalabs_ledger_from_key_team_mapping():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable.create_many = AsyncMock()
    prisma_client.db.litellm_verificationtoken.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                token="hashed-key",
                team_id="team-compat",
                organization_id="org-compat",
                metadata={},
            )
        ]
    )
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[
            _project_row(
                project_id="project-compat",
                company_id="company-compat",
                litellm_team_id="team-compat",
            )
        ]
    )
    prisma_client.db.cavadalabs_companytable.find_many = AsyncMock(
        return_value=[
            _company_row(
                company_id="company-compat",
                litellm_organization_id="org-compat",
            )
        ]
    )

    await process_spend_logs_cavadalabs_ledger(
        prisma_client=prisma_client,
        logs_to_process=[
            {
                "request_id": "req-key-team-runtime",
                "metadata": json.dumps({}),
                "api_key": "hashed-key",
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

    prisma_client.db.cavadalabs_requestledgertable.create_many.assert_awaited_once()
    ledger_row = (
        prisma_client.db.cavadalabs_requestledgertable.create_many.call_args.kwargs[
            "data"
        ][0]
    )
    assert ledger_row["request_id"] == "req-key-team-runtime"
    assert ledger_row["company_id"] == "company-compat"
    assert ledger_row["project_id"] == "project-compat"


@pytest.mark.asyncio
async def test_should_skip_runtime_cavadalabs_ledger_on_conflicting_key_mapping():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable.create_many = AsyncMock()
    prisma_client.db.litellm_verificationtoken.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                token="hashed-key",
                team_id=None,
                organization_id=None,
                metadata={
                    "cavadalabs_company_id": "company-key",
                    "cavadalabs_project_id": "project-key",
                },
            )
        ]
    )
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[_project_row(project_id="project-key", company_id="company-row")]
    )

    await process_spend_logs_cavadalabs_ledger(
        prisma_client=prisma_client,
        logs_to_process=[
            {
                "request_id": "req-key-conflict",
                "metadata": json.dumps({}),
                "api_key": "hashed-key",
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

    prisma_client.db.cavadalabs_requestledgertable.create_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_should_skip_runtime_cavadalabs_ledger_on_conflicting_explicit_company_project_metadata():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable.create_many = AsyncMock()
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[_project_row(project_id="project-1", company_id="company-2")]
    )

    await process_spend_logs_cavadalabs_ledger(
        prisma_client=prisma_client,
        logs_to_process=[
            {
                "request_id": "req-explicit-conflict",
                "metadata": json.dumps(
                    {
                        "cavadalabs_company_id": "company-1",
                        "cavadalabs_project_id": "project-1",
                    }
                ),
                "api_key": "hashed-key",
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

    prisma_client.db.cavadalabs_projecttable.find_many.assert_awaited_once_with(
        where={"project_id": {"in": ["project-1"]}}
    )
    prisma_client.db.cavadalabs_requestledgertable.create_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_should_resolve_cavadalabs_ledger_from_litellm_team_mapping():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable.create_many = AsyncMock()
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[
            _project_row(
                project_id="project-compat",
                company_id="company-compat",
                litellm_team_id="team-compat",
            )
        ]
    )

    await process_spend_logs_cavadalabs_ledger(
        prisma_client=prisma_client,
        logs_to_process=[
            {
                "request_id": "req-compat",
                "metadata": json.dumps({"user_api_key_project_id": "litellm-project"}),
                "team_id": "team-compat",
                "api_key": "hashed-key",
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

    prisma_client.db.cavadalabs_requestledgertable.create_many.assert_awaited_once()
    ledger_row = (
        prisma_client.db.cavadalabs_requestledgertable.create_many.call_args.kwargs[
            "data"
        ][0]
    )
    assert ledger_row["company_id"] == "company-compat"
    assert ledger_row["project_id"] == "project-compat"


@pytest.mark.asyncio
async def test_should_skip_cavadalabs_ledger_on_conflicting_compat_mapping():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable.create_many = AsyncMock()
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[
            _project_row(
                project_id="project-compat",
                company_id="company-project",
                litellm_team_id="team-compat",
            )
        ]
    )
    prisma_client.db.cavadalabs_companytable.find_many = AsyncMock(
        return_value=[
            _company_row(
                company_id="company-org",
                litellm_organization_id="org-compat",
            )
        ]
    )

    await process_spend_logs_cavadalabs_ledger(
        prisma_client=prisma_client,
        logs_to_process=[
            {
                "request_id": "req-conflict",
                "metadata": json.dumps({}),
                "team_id": "team-compat",
                "organization_id": "org-compat",
                "api_key": "hashed-key",
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

    prisma_client.db.cavadalabs_requestledgertable.create_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_should_process_explicit_cavadalabs_ledger_when_compat_lookup_fails():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable.create_many = AsyncMock()
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        side_effect=RuntimeError("project lookup unavailable")
    )

    await process_spend_logs_cavadalabs_ledger(
        prisma_client=prisma_client,
        logs_to_process=[
            {
                "request_id": "req-needs-compat",
                "metadata": json.dumps({}),
                "team_id": "team-compat",
                "api_key": "hashed-key",
                "custom_llm_provider": "openai",
                "model": "openai/gpt-4.1",
                "startTime": datetime.now(timezone.utc),
            },
            {
                "request_id": "req-explicit",
                "metadata": json.dumps(
                    {
                        "cavadalabs_company_id": "company-explicit",
                        "cavadalabs_project_id": "project-explicit",
                        "cavadalabs_metadata_authenticated": True,
                    }
                ),
                "api_key": "hashed-key",
                "custom_llm_provider": "openai",
                "model": "openai/gpt-4.1",
                "startTime": datetime.now(timezone.utc),
            },
        ],
    )

    prisma_client.db.cavadalabs_requestledgertable.create_many.assert_awaited_once()
    ledger_rows = (
        prisma_client.db.cavadalabs_requestledgertable.create_many.call_args.kwargs[
            "data"
        ]
    )
    assert len(ledger_rows) == 1
    assert ledger_rows[0]["request_id"] == "req-explicit"
    assert ledger_rows[0]["company_id"] == "company-explicit"
    assert ledger_rows[0]["project_id"] == "project-explicit"


@pytest.mark.asyncio
async def test_should_skip_ledger_rows_without_resolvable_cavadalabs_context():
    _, prisma_client = _service()
    prisma_client.db.cavadalabs_requestledgertable = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable.create_many = AsyncMock()

    await process_spend_logs_cavadalabs_ledger(
        prisma_client=prisma_client,
        logs_to_process=[
            {
                "request_id": "req-1",
                "metadata": json.dumps({"user_api_key_project_id": "litellm-project"}),
                "model": "openai/gpt-4.1",
                "startTime": datetime.now(timezone.utc),
            }
        ],
    )

    prisma_client.db.cavadalabs_requestledgertable.create_many.assert_not_awaited()
