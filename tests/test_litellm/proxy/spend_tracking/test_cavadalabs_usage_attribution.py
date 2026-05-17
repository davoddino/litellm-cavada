from __future__ import annotations

import datetime
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.cavadalabs.chatbot_runtime_auth import (
    build_chatbot_runtime_user_api_key,
)
from litellm.proxy.cavadalabs.dispatcher_shared import CavadaLabsRuntimeContext
from litellm.proxy.cavadalabs.usage import (
    _build_cavadalabs_ledger_where,
    _utc_range_for_local_dates,
    get_cavadalabs_daily_activity,
)
from litellm.proxy.cavadalabs.usage_tracking import (
    inspect_cavadalabs_ledger_attribution_inputs,
    process_spend_logs_cavadalabs_ledger,
)
from litellm.proxy.litellm_pre_call_utils import LiteLLMProxyRequestSetup
from litellm.proxy.spend_tracking.spend_tracking_utils import get_logging_payload


UTC = datetime.timezone.utc


class _JsonLike:
    def __init__(self, data: dict):
        self.data = data


def _project_row(*, project_id: str = "project-1", company_id: str = "company-1"):
    return SimpleNamespace(
        project_id=project_id,
        company_id=company_id,
        litellm_team_id=f"team-{project_id}",
        name=f"Project {project_id}",
        status="production",
    )


def _company_row(*, company_id: str = "company-1"):
    return SimpleNamespace(
        company_id=company_id,
        litellm_organization_id=f"org-{company_id}",
        legal_name=f"Company {company_id}",
        status="active",
    )


def _ledger_row(
    *,
    request_id: str = "chatcmpl-visible",
    company_id: str = "company-1",
    project_id: str = "project-1",
    spend: float = 0.25,
):
    return SimpleNamespace(
        ledger_id=f"ledger-{request_id}",
        request_id=request_id,
        company_id=company_id,
        project_id=project_id,
        chatbot_id=None,
        web_token_id=None,
        session_id=None,
        api_key_hash="hashed-key",
        provider="openai",
        model="openai/gpt-4.1",
        node_id=None,
        gpu_id=None,
        loaded_model_id=None,
        model_load_request_id=None,
        prompt_tokens=11,
        completion_tokens=7,
        total_tokens=18,
        spend=spend,
        status="success",
        metadata={"call_type": "acompletion", "model_group": "gpt-4.1"},
        created_at=datetime.datetime(2026, 5, 16, 12, tzinfo=UTC),
    )


def _usage_db(*, project_company_id: str = "company-1", ledger_rows=None):
    ledger_rows = list(ledger_rows or [])
    return SimpleNamespace(
        cavadalabs_projecttable=SimpleNamespace(
            find_many=AsyncMock(
                return_value=[
                    _project_row(
                        project_id="project-1",
                        company_id=project_company_id,
                    )
                ]
            )
        ),
        cavadalabs_companytable=SimpleNamespace(
            find_many=AsyncMock(return_value=[_company_row()])
        ),
        cavadalabs_requestledgertable=SimpleNamespace(
            count=AsyncMock(return_value=len(ledger_rows)),
            find_many=AsyncMock(return_value=ledger_rows),
            create_many=AsyncMock(return_value=SimpleNamespace(count=1)),
            update_many=AsyncMock(return_value=SimpleNamespace(count=0)),
        ),
        litellm_verificationtoken=SimpleNamespace(
            find_many=AsyncMock(
                return_value=[
                    SimpleNamespace(
                        token="hashed-key",
                        key_alias="Support key",
                        team_id="team-project-1",
                    )
                ]
            )
        ),
        litellm_deletedverificationtoken=SimpleNamespace(
            find_many=AsyncMock(return_value=[])
        ),
    )


def _logging_payload_from_key(
    user_api_key_dict: UserAPIKeyAuth,
    *,
    request_id: str,
    spend: float = 0.25,
) -> dict:
    request_data = {"metadata": {}}
    LiteLLMProxyRequestSetup.add_user_api_key_auth_to_request_metadata(
        data=request_data,
        user_api_key_dict=user_api_key_dict,
        _metadata_variable_name="metadata",
    )
    start_time = datetime.datetime(2026, 5, 16, 12, tzinfo=UTC)
    return get_logging_payload(
        kwargs={
            "litellm_params": {"metadata": request_data["metadata"]},
            "call_type": "acompletion",
            "model": "openai/gpt-4.1",
            "custom_llm_provider": "openai",
            "response_cost": spend,
        },
        response_obj={
            "id": request_id,
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 7,
                "total_tokens": 18,
            },
        },
        start_time=start_time,
        end_time=start_time + datetime.timedelta(milliseconds=125),
    )


def _chatbot_runtime_context() -> CavadaLabsRuntimeContext:
    return CavadaLabsRuntimeContext(
        company=SimpleNamespace(
            company_id="company-1",
            litellm_organization_id="org-company-1",
        ),
        project=SimpleNamespace(
            project_id="project-1",
            litellm_team_id="team-project-1",
        ),
        chatbot=SimpleNamespace(chatbot_id="chatbot-1"),
        web_token=SimpleNamespace(
            web_token_id="web-token-1",
            name="Browser token",
        ),
        primary_policy=SimpleNamespace(model_alias="openai/gpt-4.1"),
        fallback_policies=[],
    )


@pytest.mark.asyncio
async def test_should_attribute_server_key_request_to_cavadalabs_ledger():
    db = _usage_db()
    payload = _logging_payload_from_key(
        UserAPIKeyAuth(
            api_key="hashed-key",
            cavadalabs_company_id="company-1",
            cavadalabs_project_id="project-1",
        ),
        request_id="chatcmpl-server-key",
    )

    created = await process_spend_logs_cavadalabs_ledger(
        prisma_client=SimpleNamespace(db=db),
        logs_to_process=[payload],
    )

    assert created == 1
    ledger_row = db.cavadalabs_requestledgertable.create_many.call_args.kwargs["data"][
        0
    ]
    assert ledger_row["request_id"] == "chatcmpl-server-key"
    assert ledger_row["company_id"] == "company-1"
    assert ledger_row["project_id"] == "project-1"
    assert ledger_row["api_key_hash"] == "hashed-key"
    assert ledger_row["spend"] == 0.25


def test_should_diagnose_nested_serialized_spend_metadata_as_attributable():
    check = inspect_cavadalabs_ledger_attribution_inputs(
        {
            "request_id": "chatcmpl-nested-spend-metadata",
            "metadata": {
                "spend_logs_metadata": json.dumps(
                    {
                        "cavadalabs_company_id": "company-1",
                        "cavadalabs_project_id": "project-1",
                    }
                )
            },
            "model": "openai/gpt-4.1",
            "custom_llm_provider": "openai",
        }
    )

    assert check.can_attempt_attribution is True
    assert check.company_id == "company-1"
    assert check.project_id == "project-1"
    assert check.missing_inputs == ()


@pytest.mark.asyncio
async def test_should_attribute_serialized_nested_spend_metadata_to_ledger():
    db = _usage_db()

    created = await process_spend_logs_cavadalabs_ledger(
        prisma_client=SimpleNamespace(db=db),
        logs_to_process=[
            {
                "request_id": "chatcmpl-nested-spend-metadata",
                "metadata": {
                    "spend_logs_metadata": json.dumps(
                        {
                            "cavadalabs_company_id": "company-1",
                            "cavadalabs_project_id": "project-1",
                        }
                    )
                },
                "custom_llm_provider": "openai",
                "model": "openai/gpt-4.1",
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "spend": 0.05,
                "status": "success",
                "startTime": datetime.datetime(2026, 5, 16, 12, tzinfo=UTC),
            }
        ],
    )

    assert created == 1
    ledger_row = db.cavadalabs_requestledgertable.create_many.call_args.kwargs["data"][
        0
    ]
    assert ledger_row["company_id"] == "company-1"
    assert ledger_row["project_id"] == "project-1"
    assert ledger_row["spend"] == 0.05


@pytest.mark.asyncio
async def test_should_make_server_key_request_visible_for_company_and_project_daily_activity():
    write_db = _usage_db()
    payload = _logging_payload_from_key(
        UserAPIKeyAuth(
            api_key="hashed-key",
            cavadalabs_company_id="company-1",
            cavadalabs_project_id="project-1",
        ),
        request_id="chatcmpl-visible-server-key",
    )

    created = await process_spend_logs_cavadalabs_ledger(
        prisma_client=SimpleNamespace(db=write_db),
        logs_to_process=[payload],
    )

    assert created == 1
    ledger_row = write_db.cavadalabs_requestledgertable.create_many.call_args.kwargs[
        "data"
    ][0]
    read_db = _usage_db(ledger_rows=[SimpleNamespace(**ledger_row)])

    company_response = await get_cavadalabs_daily_activity(
        prisma_client=SimpleNamespace(db=read_db),
        entity_id_field="company_id",
        entity_id=["company-1"],
        start_date="2026-05-16",
        end_date="2026-05-16",
        model=None,
        api_key=None,
        page=1,
        page_size=50,
        timezone_offset_minutes=0,
    )
    project_response = await get_cavadalabs_daily_activity(
        prisma_client=SimpleNamespace(db=read_db),
        entity_id_field="project_id",
        entity_id=["project-1"],
        start_date="2026-05-16",
        end_date="2026-05-16",
        model=None,
        api_key=None,
        page=1,
        page_size=50,
        timezone_offset_minutes=0,
    )

    assert company_response.metadata.total_spend == 0.25
    assert company_response.metadata.total_api_requests == 1
    assert project_response.metadata.total_spend == 0.25
    assert project_response.metadata.total_api_requests == 1
    assert (
        company_response.results[0].breakdown.entities["company-1"].metrics.spend
        == 0.25
    )
    assert (
        project_response.results[0].breakdown.entities["project-1"].metrics.spend
        == 0.25
    )


@pytest.mark.asyncio
async def test_should_attribute_chatbot_web_token_request_to_cavadalabs_ledger():
    db = _usage_db()
    user_api_key_dict = build_chatbot_runtime_user_api_key(
        context=_chatbot_runtime_context(),
        token="clwt-browser-token",
        payload=None,
    )
    payload = _logging_payload_from_key(
        user_api_key_dict,
        request_id="chatcmpl-chatbot-token",
        spend=0.31,
    )

    created = await process_spend_logs_cavadalabs_ledger(
        prisma_client=SimpleNamespace(db=db),
        logs_to_process=[payload],
    )

    assert created == 1
    ledger_row = db.cavadalabs_requestledgertable.create_many.call_args.kwargs["data"][
        0
    ]
    assert ledger_row["request_id"] == "chatcmpl-chatbot-token"
    assert ledger_row["company_id"] == "company-1"
    assert ledger_row["project_id"] == "project-1"
    assert ledger_row["chatbot_id"] == "chatbot-1"
    assert ledger_row["web_token_id"] == "web-token-1"
    assert ledger_row["spend"] == 0.31


@pytest.mark.asyncio
async def test_should_attribute_server_key_request_from_key_metadata_to_chatbot_ledger():
    db = _usage_db()
    db.litellm_verificationtoken.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                token="hashed-key",
                team_id="team-project-1",
                organization_id="org-company-1",
                metadata={
                    "cavadalabs_company_id": "company-1",
                    "cavadalabs_project_id": "project-1",
                    "cavadalabs_chatbot_id": "chatbot-1",
                    "spend_logs_metadata": {
                        "cavadalabs_company_id": "company-1",
                        "cavadalabs_project_id": "project-1",
                        "cavadalabs_chatbot_id": "chatbot-1",
                    },
                },
            )
        ]
    )

    created = await process_spend_logs_cavadalabs_ledger(
        prisma_client=SimpleNamespace(db=db),
        logs_to_process=[
            {
                "request_id": "chatcmpl-key-metadata-chatbot",
                "metadata": {"user_api_key_hash": "hashed-key"},
                "custom_llm_provider": "openai",
                "model": "openai/gpt-4.1",
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "spend": 0.05,
                "status": "success",
                "startTime": datetime.datetime(2026, 5, 16, 12, tzinfo=UTC),
            }
        ],
    )

    assert created == 1
    ledger_row = db.cavadalabs_requestledgertable.create_many.call_args.kwargs["data"][
        0
    ]
    assert ledger_row["company_id"] == "company-1"
    assert ledger_row["project_id"] == "project-1"
    assert ledger_row["chatbot_id"] == "chatbot-1"
    assert ledger_row["api_key_hash"] == "hashed-key"


@pytest.mark.asyncio
async def test_should_resolve_key_context_from_prisma_json_nested_spend_metadata():
    db = _usage_db()
    db.litellm_verificationtoken.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                token="hashed-key",
                team_id=None,
                organization_id=None,
                metadata=_JsonLike(
                    {
                        "spend_logs_metadata": json.dumps(
                            {
                                "cavadalabs_company_id": "company-1",
                                "cavadalabs_project_id": "project-1",
                                "cavadalabs_chatbot_id": "chatbot-1",
                            }
                        )
                    }
                ),
            )
        ]
    )

    created = await process_spend_logs_cavadalabs_ledger(
        prisma_client=SimpleNamespace(db=db),
        logs_to_process=[
            {
                "request_id": "chatcmpl-json-nested-key-context",
                "metadata": {"user_api_key_hash": "hashed-key"},
                "custom_llm_provider": "openai",
                "model": "openai/gpt-4.1",
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "spend": 0.05,
                "status": "success",
                "startTime": datetime.datetime(2026, 5, 16, 12, tzinfo=UTC),
            }
        ],
    )

    assert created == 1
    ledger_row = db.cavadalabs_requestledgertable.create_many.call_args.kwargs["data"][
        0
    ]
    assert ledger_row["company_id"] == "company-1"
    assert ledger_row["project_id"] == "project-1"
    assert ledger_row["chatbot_id"] == "chatbot-1"
    assert ledger_row["api_key_hash"] == "hashed-key"


@pytest.mark.asyncio
async def test_should_repair_existing_ledger_context_from_authoritative_key_metadata():
    db = _usage_db()
    db.cavadalabs_requestledgertable.create_many = AsyncMock(
        return_value=SimpleNamespace(count=0)
    )
    db.cavadalabs_requestledgertable.update_many = AsyncMock(
        return_value=SimpleNamespace(count=1)
    )
    db.litellm_verificationtoken.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                token="hashed-key",
                team_id="team-project-1",
                organization_id="org-company-1",
                metadata={
                    "cavadalabs_company_id": "company-1",
                    "cavadalabs_project_id": "project-1",
                    "cavadalabs_chatbot_id": "chatbot-1",
                },
            )
        ]
    )

    repaired = await process_spend_logs_cavadalabs_ledger(
        prisma_client=SimpleNamespace(db=db),
        logs_to_process=[
            {
                "request_id": "chatcmpl-repair-duplicate",
                "metadata": {"user_api_key_hash": "hashed-key"},
                "custom_llm_provider": "openai",
                "model": "openai/gpt-4.1",
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "spend": 0.05,
                "status": "success",
                "startTime": datetime.datetime(2026, 5, 16, 12, tzinfo=UTC),
            }
        ],
    )

    assert repaired == 1
    update_call = db.cavadalabs_requestledgertable.update_many.call_args.kwargs
    assert update_call["where"] == {
        "request_id": "chatcmpl-repair-duplicate",
        "OR": [
            {"company_id": {"not": "company-1"}},
            {"project_id": {"not": "project-1"}},
        ],
    }
    assert update_call["data"]["company_id"] == "company-1"
    assert update_call["data"]["project_id"] == "project-1"
    assert update_call["data"]["chatbot_id"] == "chatbot-1"
    assert update_call["data"]["api_key_hash"] == "hashed-key"
    assert "request_id" not in update_call["data"]
    metadata = getattr(update_call["data"]["metadata"], "data", {})
    assert metadata["cavadalabs"]["attribution_source"] == "key_metadata"


@pytest.mark.asyncio
async def test_should_not_create_cross_project_ledger_from_conflicting_metadata():
    db = _usage_db(project_company_id="company-2")

    created = await process_spend_logs_cavadalabs_ledger(
        prisma_client=SimpleNamespace(db=db),
        logs_to_process=[
            {
                "request_id": "req-conflicting-company-project",
                "metadata": {
                    "cavadalabs_company_id": "company-1",
                    "cavadalabs_project_id": "project-1",
                    "cavadalabs_metadata_authenticated": True,
                },
                "spend": 0.42,
                "total_tokens": 42,
                "prompt_tokens": 20,
                "completion_tokens": 22,
                "startTime": datetime.datetime(2026, 5, 16, 12, tzinfo=UTC),
                "model": "openai/gpt-4.1",
                "custom_llm_provider": "openai",
                "status": "success",
            }
        ],
    )

    assert created == 0
    db.cavadalabs_requestledgertable.create_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_should_not_create_ledger_when_project_mapping_schema_is_unavailable():
    db = _usage_db()
    db.cavadalabs_projecttable.find_many = AsyncMock(
        side_effect=Exception('relation "CavadaLabs_ProjectTable" does not exist')
    )

    created = await process_spend_logs_cavadalabs_ledger(
        prisma_client=SimpleNamespace(db=db),
        logs_to_process=[
            {
                "request_id": "req-project-schema-missing",
                "api_key": "hashed-key",
                "metadata": {
                    "cavadalabs_company_id": "company-1",
                    "cavadalabs_project_id": "project-1",
                },
                "spend": 0.42,
                "total_tokens": 42,
                "prompt_tokens": 20,
                "completion_tokens": 22,
                "startTime": datetime.datetime(2026, 5, 16, 12, tzinfo=UTC),
                "model": "openai/gpt-4.1",
                "custom_llm_provider": "openai",
                "status": "success",
            }
        ],
    )

    assert created == 0
    db.cavadalabs_requestledgertable.create_many.assert_not_awaited()


def test_should_build_company_project_ledger_filters_without_organization_scope():
    where = _build_cavadalabs_ledger_where(
        entity_id_field="project_id",
        entity_id=["project-1"],
        date_range=_utc_range_for_local_dates("2026-05-16", "2026-05-16", 0),
        model="openai/gpt-4.1",
        provider="openai",
        status_filter="success",
        api_key="hashed-key",
        min_spend=None,
        max_spend=None,
    )

    assert where["project_id"] == {"in": ["project-1"]}
    assert where["provider"] == "openai"
    assert where["api_key_hash"] == "hashed-key"
    assert "organization_id" not in where
    assert "team_id" not in where


@pytest.mark.parametrize(
    ("entity_id_field", "entity_id"),
    [("company_id", "company-1"), ("project_id", "project-1")],
)
@pytest.mark.asyncio
async def test_should_read_company_project_daily_activity_from_cavadalabs_ledger(
    entity_id_field: str,
    entity_id: str,
):
    db = _usage_db(ledger_rows=[_ledger_row()])

    response = await get_cavadalabs_daily_activity(
        prisma_client=SimpleNamespace(db=db),
        entity_id_field=entity_id_field,
        entity_id=[entity_id],
        start_date="2026-05-16",
        end_date="2026-05-16",
        model=None,
        api_key=None,
        page=1,
        page_size=50,
        timezone_offset_minutes=0,
    )

    assert response.metadata.total_spend == 0.25
    assert response.metadata.total_tokens == 18
    assert response.metadata.total_successful_requests == 1
    assert response.results[0].breakdown.entities[entity_id].metrics.spend == 0.25

    ledger_where = db.cavadalabs_requestledgertable.find_many.call_args_list[-1].kwargs[
        "where"
    ]
    assert ledger_where[entity_id_field] == {"in": [entity_id]}
    assert "organization_id" not in ledger_where
    assert "team_id" not in ledger_where


@pytest.mark.asyncio
async def test_should_return_migration_command_when_usage_schema_delegate_is_missing():
    with pytest.raises(HTTPException) as exc_info:
        await get_cavadalabs_daily_activity(
            prisma_client=SimpleNamespace(db=SimpleNamespace()),
            entity_id_field="company_id",
            entity_id=["company-1"],
            start_date="2026-05-16",
            end_date="2026-05-16",
            model=None,
            api_key=None,
            page=1,
            page_size=50,
            timezone_offset_minutes=0,
        )

    assert exc_info.value.status_code == 503
    detail = exc_info.value.detail
    assert detail["schema_status"] == "missing_schema"
    assert detail["missing_schema"]
    assert "prisma migrate deploy" in detail["migration_command"]
