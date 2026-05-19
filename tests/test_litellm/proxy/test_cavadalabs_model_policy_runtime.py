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
        key_id=kwargs.pop("key_id", None),
        model_alias=kwargs.pop("model_alias", "model-a"),
        provider=kwargs.pop("provider", "openai"),
        priority=kwargs.pop("priority", 1),
        enabled=kwargs.pop("enabled", True),
        endpoint_type=kwargs.pop("endpoint_type", "chat_completion"),
        model_bucket=kwargs.pop("model_bucket", "default"),
        fallback_enabled=kwargs.pop("fallback_enabled", True),
    )


def _policy_row(**kwargs):
    return SimpleNamespace(
        policy_id=kwargs.pop("policy_id", "policy-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        project_id=kwargs.pop("project_id", "project-1"),
        key_id=kwargs.pop("key_id", None),
        endpoint_type=kwargs.pop("endpoint_type", "chat_completion"),
        model_bucket=kwargs.pop("model_bucket", "default"),
        model_alias=kwargs.pop("model_alias", "model-a"),
        provider=kwargs.pop("provider", "openai"),
        priority=kwargs.pop("priority", 1),
        enabled=kwargs.pop("enabled", True),
        fallback_enabled=kwargs.pop("fallback_enabled", True),
    )


def _prisma_client(rows, *, key_rows=None):
    async def _find_many(*, where, order):
        if where.get("key_id") is not None:
            return key_rows or []
        return rows

    db = MagicMock()
    db.cavadalabs_projectmodelpolicytable = MagicMock()
    db.cavadalabs_projectmodelpolicytable.find_many = AsyncMock(side_effect=_find_many)
    return SimpleNamespace(db=db)


class _RouterStub:
    model_names = {"model-a", "model-b"}
    deployment_names = {"deployment-model"}

    def get_model_names(self, team_id=None):
        return ["model-b", "model-a"]

    def get_model_ids(self):
        return ["model-id-1"]


class _HealthAwareRouterStub(_RouterStub):
    enable_health_check_routing = True

    def __init__(self, unhealthy_deployment_ids: set[str]):
        self.health_state_cache = SimpleNamespace(
            async_get_unhealthy_deployment_ids=AsyncMock(
                return_value=unhealthy_deployment_ids
            )
        )

    def get_model_list(self, team_id=None):
        return [
            {
                "model_name": "model-a",
                "litellm_params": {"model": "openai/model-a"},
                "model_info": {"id": "deployment-a"},
            },
            {
                "model_name": "model-b",
                "litellm_params": {"model": "openai/model-b"},
                "model_info": {"id": "deployment-b"},
            },
        ]


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
    assert result.fallback_models == ("model-a",)
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
async def test_should_apply_default_cavadalabs_project_model_fallback_from_key_context():
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
            _policy_row(policy_id="policy-3", model_alias="model-a", priority=3),
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
    assert data["fallbacks"] == ["model-a"]
    assert data["metadata"]["cavadalabs_model_bucket"] == "default"
    find_calls = (
        prisma_client.db.cavadalabs_projectmodelpolicytable.find_many.await_args_list
    )
    assert find_calls[0].kwargs["where"]["key_id"] is not None
    assert find_calls[1].kwargs == {
        "where": {
            "project_id": "project-1",
            "endpoint_type": "chat_completion",
            "model_bucket": "default",
            "enabled": True,
            "key_id": None,
        },
        "order": {"priority": "asc"},
    }


@pytest.mark.asyncio
async def test_should_apply_named_model_bucket_from_key_context():
    data = {"messages": [{"role": "user", "content": "ciao"}], "model": "medium"}
    user_api_key_dict = UserAPIKeyAuth(
        api_key="sk-test",
        user_id="user-1",
        cavadalabs_company_id="company-1",
        cavadalabs_project_id="project-1",
        team_id="team-1",
    )
    prisma_client = _prisma_client(
        [
            _policy_row(
                policy_id="policy-1",
                model_alias="model-a",
                priority=1,
                model_bucket="medium",
            ),
            _policy_row(
                policy_id="policy-2",
                model_alias="model-b",
                priority=2,
                model_bucket="medium",
            ),
        ]
    )

    resolved_model = await apply_cavadalabs_project_model_fallback(
        data=data,
        route_type="acompletion",
        user_api_key_dict=user_api_key_dict,
        llm_router=_RouterStub(),
        prisma_client=prisma_client,
    )

    assert resolved_model == "model-a"
    assert data["model"] == "model-a"
    assert data["fallbacks"] == ["model-b"]
    assert data["metadata"]["cavadalabs"]["routing"]["model_bucket"] == "medium"
    find_calls = (
        prisma_client.db.cavadalabs_projectmodelpolicytable.find_many.await_args_list
    )
    assert find_calls[0].kwargs["where"]["key_id"] is not None
    assert find_calls[1].kwargs == {
        "where": {
            "project_id": "project-1",
            "endpoint_type": "chat_completion",
            "model_bucket": "medium",
            "enabled": True,
            "key_id": None,
        },
        "order": {"priority": "asc"},
    }


@pytest.mark.asyncio
async def test_should_skip_health_check_unhealthy_primary_policy():
    data = {"messages": [{"role": "user", "content": "ciao"}], "model": "medium"}
    user_api_key_dict = UserAPIKeyAuth(
        api_key="sk-test",
        user_id="user-1",
        cavadalabs_project_id="project-1",
    )
    prisma_client = _prisma_client(
        [
            _policy_row(
                policy_id="policy-1",
                model_alias="model-a",
                priority=1,
                model_bucket="medium",
            ),
            _policy_row(
                policy_id="policy-2",
                model_alias="model-b",
                priority=2,
                model_bucket="medium",
            ),
        ]
    )
    router = _HealthAwareRouterStub(unhealthy_deployment_ids={"deployment-a"})

    resolved_model = await apply_cavadalabs_project_model_fallback(
        data=data,
        route_type="acompletion",
        user_api_key_dict=user_api_key_dict,
        llm_router=router,
        prisma_client=prisma_client,
    )

    assert resolved_model == "model-b"
    assert data["model"] == "model-b"
    assert "fallbacks" not in data
    assert data["metadata"]["cavadalabs"]["routing"]["selected_policy_id"] == "policy-2"
    router.health_state_cache.async_get_unhealthy_deployment_ids.assert_awaited_once()


@pytest.mark.asyncio
async def test_should_prefer_key_scoped_model_bucket_over_project_default():
    data = {"messages": [{"role": "user", "content": "ciao"}], "model": "medium"}
    user_api_key_dict = UserAPIKeyAuth(
        api_key="sk-test",
        user_id="user-1",
        cavadalabs_project_id="project-1",
    )
    prisma_client = _prisma_client(
        [
            _policy_row(
                policy_id="project-policy",
                model_alias="model-a",
                priority=1,
                model_bucket="medium",
            )
        ],
        key_rows=[
            _policy_row(
                policy_id="key-policy",
                key_id="sk-test",
                model_alias="model-b",
                priority=1,
                model_bucket="medium",
            )
        ],
    )

    resolved_model = await apply_cavadalabs_project_model_fallback(
        data=data,
        route_type="acompletion",
        user_api_key_dict=user_api_key_dict,
        llm_router=_RouterStub(),
        prisma_client=prisma_client,
    )

    assert resolved_model == "model-b"
    assert data["metadata"]["cavadalabs"]["routing"]["key_id"] is not None
    find_calls = (
        prisma_client.db.cavadalabs_projectmodelpolicytable.find_many.await_args_list
    )
    assert len(find_calls) == 1
    assert find_calls[0].kwargs["where"]["key_id"] is not None


@pytest.mark.asyncio
async def test_should_fall_back_to_project_model_bucket_when_key_has_no_policy():
    data = {"messages": [{"role": "user", "content": "ciao"}], "model": "advanced"}
    user_api_key_dict = UserAPIKeyAuth(
        api_key="sk-test",
        user_id="user-1",
        cavadalabs_project_id="project-1",
    )
    prisma_client = _prisma_client(
        [
            _policy_row(
                policy_id="project-policy",
                model_alias="model-a",
                priority=1,
                model_bucket="advanced",
            )
        ],
        key_rows=[],
    )

    resolved_model = await apply_cavadalabs_project_model_fallback(
        data=data,
        route_type="acompletion",
        user_api_key_dict=user_api_key_dict,
        llm_router=_RouterStub(),
        prisma_client=prisma_client,
    )

    assert resolved_model == "model-a"
    assert (
        data["metadata"]["cavadalabs"]["routing"]["selected_policy_id"]
        == "project-policy"
    )
    assert data["metadata"]["cavadalabs"]["routing"]["key_id"] is None


@pytest.mark.asyncio
async def test_should_apply_bucket_routing_for_embedding_endpoint():
    data = {"input": "ciao", "model": "small"}
    user_api_key_dict = UserAPIKeyAuth(
        api_key="sk-test",
        user_id="user-1",
        cavadalabs_project_id="project-1",
    )
    prisma_client = _prisma_client(
        [
            _policy_row(
                policy_id="embedding-policy",
                endpoint_type="embedding",
                model_bucket="small",
                model_alias="model-a",
            )
        ],
        key_rows=[],
    )

    resolved_model = await apply_cavadalabs_project_model_fallback(
        data=data,
        route_type="aembedding",
        user_api_key_dict=user_api_key_dict,
        llm_router=_RouterStub(),
        prisma_client=prisma_client,
    )

    assert resolved_model == "model-a"
    assert data["model"] == "model-a"
    assert data["metadata"]["cavadalabs"]["routing"]["endpoint_type"] == "embedding"
    find_calls = (
        prisma_client.db.cavadalabs_projectmodelpolicytable.find_many.await_args_list
    )
    assert find_calls[1].kwargs["where"]["endpoint_type"] == "embedding"
    assert find_calls[1].kwargs["where"]["model_bucket"] == "small"


@pytest.mark.asyncio
async def test_should_leave_real_model_when_no_matching_bucket_exists():
    data = {"messages": [{"role": "user", "content": "ciao"}], "model": "model-a"}
    user_api_key_dict = UserAPIKeyAuth(
        api_key="sk-test",
        user_id="user-1",
        cavadalabs_project_id="project-1",
    )
    prisma_client = _prisma_client([])

    resolved_model = await apply_cavadalabs_project_model_fallback(
        data=data,
        route_type="acompletion",
        user_api_key_dict=user_api_key_dict,
        llm_router=_RouterStub(),
        prisma_client=prisma_client,
    )

    assert resolved_model is None
    assert data == {
        "messages": [{"role": "user", "content": "ciao"}],
        "model": "model-a",
    }


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
