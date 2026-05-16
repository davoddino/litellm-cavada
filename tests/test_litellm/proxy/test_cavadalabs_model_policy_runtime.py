from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, Request

import litellm.proxy.common_request_processing as common_request_processing
from litellm.proxy import proxy_server
from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.cavadalabs.model_policy_proxy import (
    apply_cavadalabs_project_model_fallback,
)
from litellm.proxy.cavadalabs.model_policy_resolution import (
    CavadaLabsModelPolicyCandidate,
    CavadaLabsModelPolicyResolutionError,
    resolve_project_model_priority,
)
from litellm.proxy.common_request_processing import (
    ProxyBaseLLMRequestProcessing,
    ProxyConfig,
)
from litellm.proxy.utils import ProxyLogging


def _policy(**kwargs) -> CavadaLabsModelPolicyCandidate:
    return CavadaLabsModelPolicyCandidate(
        policy_id=kwargs.pop("policy_id", "policy-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        project_id=kwargs.pop("project_id", "project-1"),
        model_alias=kwargs.pop("model_alias", "model-a"),
        provider=kwargs.pop("provider", "openai"),
        priority=kwargs.pop("priority", 1),
        enabled=kwargs.pop("enabled", True),
    )


def _policy_row(**kwargs):
    return SimpleNamespace(
        policy_id=kwargs.pop("policy_id", "policy-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        project_id=kwargs.pop("project_id", "project-1"),
        model_alias=kwargs.pop("model_alias", "model-a"),
        provider=kwargs.pop("provider", "openai"),
        priority=kwargs.pop("priority", 1),
        enabled=kwargs.pop("enabled", True),
    )


def _prisma_client(rows):
    db = MagicMock()
    db.cavadalabs_projectmodelpolicytable = MagicMock()
    db.cavadalabs_projectmodelpolicytable.find_many = AsyncMock(return_value=rows)
    return SimpleNamespace(db=db)


class _RouterStub:
    model_names = {"model-a", "model-b"}
    deployment_names = {"deployment-model"}

    def get_model_names(self, team_id=None):
        return ["model-b", "model-a"]

    def get_model_ids(self):
        return ["model-id-1"]


def test_should_resolve_first_available_policy_by_priority():
    result = resolve_project_model_priority(
        project_id="project-1",
        policies=[
            _policy(policy_id="policy-1", model_alias="missing-model", priority=1),
            _policy(policy_id="policy-2", model_alias="model-b", priority=2),
            _policy(policy_id="policy-3", model_alias="model-a", priority=3),
        ],
        available_model_names={"model-a", "model-b"},
    )

    assert result.model == "model-b"
    assert result.policy.policy_id == "policy-2"
    assert result.skipped_policies[0]["reason"] == "model_not_configured"


def test_should_return_clear_error_when_no_project_policy_is_available():
    with pytest.raises(CavadaLabsModelPolicyResolutionError) as exc_info:
        resolve_project_model_priority(
            project_id="project-1",
            policies=[
                _policy(policy_id="policy-1", model_alias="model-a", enabled=False),
                _policy(policy_id="policy-2", model_alias="model-b", priority=2),
            ],
            available_model_names={"model-c"},
        )

    detail = exc_info.value.to_detail()
    assert detail["code"] == "no_available_model"
    assert detail["project_id"] == "project-1"
    assert [item["reason"] for item in detail["skipped_policies"]] == [
        "disabled",
        "model_not_configured",
    ]


@pytest.mark.asyncio
async def test_should_apply_cavadalabs_project_model_fallback_from_key_context():
    data = {"messages": [{"role": "user", "content": "ciao"}], "model": None}
    user_api_key_dict = UserAPIKeyAuth(
        api_key="sk-test",
        user_id="user-1",
        cavadalabs_company_id="company-1",
        cavadalabs_project_id="project-1",
        team_id="team-1",
    )
    prisma_client = _prisma_client(
        [
            _policy_row(policy_id="policy-1", model_alias="missing-model", priority=1),
            _policy_row(policy_id="policy-2", model_alias="model-b", priority=2),
        ]
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
    prisma_client.db.cavadalabs_projectmodelpolicytable.find_many.assert_awaited_once_with(
        where={"project_id": "project-1", "enabled": True},
        order={"priority": "asc"},
    )


@pytest.mark.asyncio
async def test_should_report_missing_model_policy_schema_for_cavada_fallback():
    data = {"messages": [{"role": "user", "content": "ciao"}], "model": None}
    user_api_key_dict = UserAPIKeyAuth(
        api_key="sk-test",
        user_id="user-1",
        cavadalabs_project_id="project-1",
    )
    prisma_client = SimpleNamespace(db=SimpleNamespace())

    with pytest.raises(HTTPException) as exc_info:
        await apply_cavadalabs_project_model_fallback(
            data=data,
            route_type="acompletion",
            user_api_key_dict=user_api_key_dict,
            llm_router=_RouterStub(),
            prisma_client=prisma_client,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["schema_status"] == "missing_schema"
    assert (
        "CavadaLabs_ProjectModelPolicyTable" in exc_info.value.detail["missing_schema"]
    )
    assert "prisma migrate deploy" in exc_info.value.detail["migration_command"]


@pytest.mark.asyncio
async def test_should_resolve_missing_model_during_proxy_pre_call(monkeypatch):
    processor = ProxyBaseLLMRequestProcessing(
        data={"messages": [{"role": "user", "content": "ciao"}]}
    )
    request = MagicMock(spec=Request)
    request.headers = {}
    request.url = MagicMock()
    request.url.path = "/v1/chat/completions"
    prisma_client = _prisma_client(
        [_policy_row(policy_id="policy-1", model_alias="model-a", priority=1)]
    )
    monkeypatch.setattr(proxy_server, "prisma_client", prisma_client)

    async def mock_add_litellm_data_to_request(*args, **kwargs):
        return kwargs["data"]

    async def mock_pre_call_hook(user_api_key_dict, data, call_type):
        return data

    monkeypatch.setattr(
        common_request_processing,
        "add_litellm_data_to_request",
        mock_add_litellm_data_to_request,
    )
    proxy_logging_obj = MagicMock(spec=ProxyLogging)
    proxy_logging_obj.pre_call_hook = AsyncMock(side_effect=mock_pre_call_hook)
    proxy_config = MagicMock(spec=ProxyConfig)
    proxy_config._get_hierarchical_router_settings = AsyncMock(return_value=None)

    returned_data, _ = await processor.common_processing_pre_call_logic(
        request=request,
        general_settings={},
        user_api_key_dict=UserAPIKeyAuth(
            api_key="sk-test",
            user_id="user-1",
            cavadalabs_project_id="project-1",
            team_id="team-1",
        ),
        proxy_logging_obj=proxy_logging_obj,
        proxy_config=proxy_config,
        route_type="acompletion",
        llm_router=_RouterStub(),
    )

    assert returned_data["model"] == "model-a"
