import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from litellm.proxy import proxy_server
from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.cavadalabs.usage import (
    backfill_cavadalabs_usage_ledger_from_spend_logs,
    get_cavadalabs_daily_activity,
    get_cavadalabs_usage_diagnostics,
    repair_cavadalabs_usage_scope,
)
from litellm.proxy.cavadalabs.usage_query_filters import spend_log_repair_where
from litellm.proxy.cavadalabs.usage_tracking import (
    process_spend_logs_cavadalabs_ledger,
)
from litellm.proxy.management_endpoints import (
    cavadalabs_company_endpoints as company_endpoints,
)
from litellm.proxy.management_endpoints import (
    cavadalabs_project_endpoints as project_endpoints,
)
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsUsageDiagnosticsAction,
    CavadaLabsUsageDiagnosticsStatus,
    CavadaLabsUsageMigrationStatus,
    CavadaLabsUsageRepairRequest,
    CavadaLabsUsageRepairResponse,
    CavadaLabsUsageSchemaStatus,
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
        legal_name="ACME Spa",
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
        name="Support",
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


def _ledger(**kwargs):
    return _row(
        request_id=kwargs.pop("request_id", "request-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        project_id=kwargs.pop("project_id", "project-1"),
        api_key_hash=kwargs.pop("api_key_hash", "hashed-key"),
        provider=kwargs.pop("provider", "cavadalabs"),
        model=kwargs.pop("model", "cavadalabs/qwen3-32b"),
        prompt_tokens=kwargs.pop("prompt_tokens", 10),
        completion_tokens=kwargs.pop("completion_tokens", 5),
        total_tokens=kwargs.pop("total_tokens", 15),
        spend=kwargs.pop("spend", 0.15),
        status=kwargs.pop("status", "success"),
        metadata=kwargs.pop(
            "metadata", {"model_group": "cavadalabs/qwen3-32b", "call_type": "chat"}
        ),
        created_at=kwargs.pop(
            "created_at", datetime(2026, 5, 15, 12, tzinfo=timezone.utc)
        ),
        **kwargs,
    )


def _spend_log(**kwargs):
    return SimpleNamespace(
        request_id=kwargs.pop("request_id", "request-1"),
        call_type=kwargs.pop("call_type", "chat"),
        api_key=kwargs.pop("api_key", "hashed-key"),
        spend=kwargs.pop("spend", 0.15),
        total_tokens=kwargs.pop("total_tokens", 15),
        prompt_tokens=kwargs.pop("prompt_tokens", 10),
        completion_tokens=kwargs.pop("completion_tokens", 5),
        startTime=kwargs.pop(
            "startTime", datetime(2026, 5, 15, 12, tzinfo=timezone.utc)
        ),
        endTime=kwargs.pop(
            "endTime", datetime(2026, 5, 15, 12, 0, 2, tzinfo=timezone.utc)
        ),
        model=kwargs.pop("model", "cavadalabs/qwen3-32b"),
        model_group=kwargs.pop("model_group", "cavadalabs/qwen3-32b"),
        custom_llm_provider=kwargs.pop("custom_llm_provider", "cavadalabs"),
        metadata=kwargs.pop("metadata", {}),
        team_id=kwargs.pop("team_id", None),
        organization_id=kwargs.pop("organization_id", None),
        session_id=kwargs.pop("session_id", None),
        status=kwargs.pop("status", "success"),
        request_tags=kwargs.pop("request_tags", []),
        **kwargs,
    )


def _date_range():
    return {
        "gte": datetime(2026, 5, 1, tzinfo=timezone.utc),
        "lt": datetime(2026, 6, 1, tzinfo=timezone.utc),
    }


def _membership(role: LitellmUserRoles):
    return SimpleNamespace(
        user_id="user-1",
        organization_id="org-company-1",
        user_role=role.value,
    )


def _db():
    db = MagicMock()
    db.cavadalabs_companytable = MagicMock()
    db.cavadalabs_projecttable = MagicMock()
    db.litellm_organizationmembership = MagicMock()
    db.litellm_usertable = MagicMock()
    db.litellm_teamtable = MagicMock()
    db.cavadalabs_requestledgertable = MagicMock()
    db.litellm_spendlogs = MagicMock()
    db.litellm_verificationtoken = MagicMock()
    db.litellm_deletedverificationtoken = MagicMock()
    db.cavadalabs_companytable.find_unique = AsyncMock(return_value=_company())
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[])
    db.cavadalabs_projecttable.find_unique = AsyncMock(return_value=_project())
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[])
    db.cavadalabs_requestledgertable.count = AsyncMock(return_value=0)
    db.cavadalabs_requestledgertable.find_many = AsyncMock(return_value=[])
    db.cavadalabs_requestledgertable.update_many = AsyncMock(
        return_value=SimpleNamespace(count=0)
    )
    db.litellm_organizationmembership.find_unique = AsyncMock(return_value=None)
    db.litellm_organizationmembership.find_many = AsyncMock(return_value=[])
    db.litellm_spendlogs.count = AsyncMock(return_value=0)
    db.litellm_spendlogs.find_many = AsyncMock(return_value=[])
    db.litellm_usertable.find_unique = AsyncMock(return_value=None)
    db.litellm_teamtable.find_unique = AsyncMock(return_value=None)
    db.litellm_verificationtoken.find_many = AsyncMock(return_value=[])
    db.litellm_deletedverificationtoken.find_many = AsyncMock(return_value=[])
    return db


def _auth() -> UserAPIKeyAuth:
    return UserAPIKeyAuth(
        user_id="user-1",
        user_role=LitellmUserRoles.INTERNAL_USER,
    )


def _admin_auth() -> UserAPIKeyAuth:
    return UserAPIKeyAuth(
        user_id="admin-user",
        user_role=LitellmUserRoles.PROXY_ADMIN,
    )


def _request(
    company_ids=None,
    project_ids=None,
    model=None,
    provider=None,
    status=None,
    api_key=None,
    min_spend=None,
    max_spend=None,
    dry_run=False,
    batch_limit=None,
) -> CavadaLabsUsageRepairRequest:
    return CavadaLabsUsageRepairRequest(
        company_ids=company_ids or [],
        project_ids=project_ids or [],
        start_date="2026-05-01",
        end_date="2026-05-31",
        model=model,
        provider=provider,
        status=status,
        api_key=api_key,
        min_spend=min_spend,
        max_spend=max_spend,
        dry_run=dry_run,
        batch_limit=batch_limit,
    )


def _repair_response(entity_type: str, entity_ids: list[str]):
    return CavadaLabsUsageRepairResponse(
        entity_type=entity_type,
        entity_ids=entity_ids,
        attempted=True,
        repaired=True,
        scoped_spend_logs=1,
        processed_spend_logs=1,
        batches=1,
        diagnostics=[],
        migration_name="20260515161000_backfill_cavadalabs_request_ledger_from_metadata_key_hash",
        migration_command="uv run prisma migrate deploy",
        migration_names=[
            "20260515122000_add_cavadalabs_usage_spend_log_indexes",
            "20260515123000_backfill_cavadalabs_request_ledger_from_spend_logs",
            "20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata",
            "20260515161000_backfill_cavadalabs_request_ledger_from_metadata_key_hash",
        ],
    )


def _patch_prisma(monkeypatch, db):
    monkeypatch.setattr(proxy_server, "prisma_client", SimpleNamespace(db=db))


def _set_native_company_membership(
    db,
    role: str | None,
    *,
    company_id: str = "company-1",
    user_id: str = "user-1",
) -> None:
    membership = (
        SimpleNamespace(company_id=company_id, user_id=user_id, role=role)
        if role is not None
        else None
    )
    db.cavadalabs_companymembertable = MagicMock()
    db.cavadalabs_companymembertable.find_unique = AsyncMock(return_value=membership)
    db.cavadalabs_companymembertable.find_many = AsyncMock(
        return_value=[membership] if membership is not None else []
    )


def _set_native_project_membership(
    db,
    role: str | None,
    *,
    project_id: str = "project-1",
    user_id: str = "user-1",
) -> None:
    membership = (
        SimpleNamespace(project_id=project_id, user_id=user_id, role=role)
        if role is not None
        else None
    )
    db.cavadalabs_projectmembertable = MagicMock()
    db.cavadalabs_projectmembertable.find_unique = AsyncMock(return_value=membership)
    db.cavadalabs_projectmembertable.find_many = AsyncMock(
        return_value=[membership] if membership is not None else []
    )


def _assert_missing_usage_schema_detail(detail):
    assert detail["schema_status"] == CavadaLabsUsageSchemaStatus.MISSING_SCHEMA.value
    assert (
        detail["migration_status"]
        == CavadaLabsUsageMigrationStatus.SCHEMA_MISSING.value
    )
    assert (
        detail["recommended_action"]
        == CavadaLabsUsageDiagnosticsAction.RUN_MIGRATION_BACKFILL.value
    )
    assert detail["missing_schema"]
    assert detail["migration_command"]
    assert "prisma migrate deploy" in detail["migration_command"]
    assert (
        "20260515161000_backfill_cavadalabs_request_ledger_from_metadata_key_hash"
        in detail["migration_names"]
    )
    assert detail["migration_plan"]


def _find_and_or_condition(where, expected_member):
    for condition in where.get("AND", []):
        or_members = condition.get("OR") if isinstance(condition, dict) else None
        if isinstance(or_members, list) and expected_member in or_members:
            return condition
    raise AssertionError(f"Could not find OR condition containing {expected_member}")


def _find_spend_logs_find_many_call(db, expected_member, *, take=None):
    for call in db.litellm_spendlogs.find_many.call_args_list:
        kwargs = call.kwargs
        if take is not None and kwargs.get("take") != take:
            continue
        try:
            _find_and_or_condition(kwargs.get("where", {}), expected_member)
        except AssertionError:
            continue
        return kwargs
    raise AssertionError(
        f"Could not find SpendLogs find_many call containing {expected_member}"
    )


def _raw_spend_logs_backfill_fetch_calls(db):
    return [
        call.kwargs
        for call in db.litellm_spendlogs.find_many.call_args_list
        if "select" not in call.kwargs
    ]


def _paginated_ledger_find_many(ledger_rows):
    async def _find_many(**kwargs):
        if kwargs.get("take") == 1:
            return ledger_rows[:1]
        skip = kwargs.get("skip", 0)
        take = kwargs.get("take", len(ledger_rows))
        return ledger_rows[skip : skip + take]

    return AsyncMock(side_effect=_find_many)


def test_spend_log_repair_where_matches_api_key_hash_in_metadata_paths():
    where = spend_log_repair_where(
        date_range=_date_range(),
        filters=[{"team_id": "team-project-1"}],
        model=None,
        provider=None,
        api_key="hashed-key",
    )

    api_key_condition = _find_and_or_condition(
        where,
        {"api_key": {"in": ["hashed-key"]}},
    )
    assert {
        "metadata": {
            "path": ["user_api_key_hash"],
            "equals": json.dumps("hashed-key"),
        }
    } in api_key_condition["OR"]
    assert {
        "metadata": {
            "path": ["spend_logs_metadata", "api_key_hash"],
            "equals": json.dumps("hashed-key"),
        }
    } in api_key_condition["OR"]


@pytest.mark.asyncio
async def test_company_daily_activity_endpoint_reads_authoritative_cavadalabs_ledger(
    monkeypatch,
):
    db = _db()
    db.cavadalabs_requestledgertable.count = AsyncMock(return_value=1)
    db.cavadalabs_requestledgertable.find_many = AsyncMock(return_value=[_ledger()])
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[_company()])
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[_project()])
    db.litellm_spendlogs.count = AsyncMock(return_value=1)
    _patch_prisma(monkeypatch, db)

    response = await company_endpoints.get_company_daily_activity(
        http_request=MagicMock(),
        start_date="2026-05-15",
        end_date="2026-05-15",
        model="cavadalabs/qwen3-32b",
        provider="cavadalabs",
        status_filter="success",
        api_key="hashed-key",
        min_spend=0.1,
        max_spend=0.2,
        company_ids="company-1",
        page=1,
        page_size=100,
        timezone=0,
        user_api_key_dict=_admin_auth(),
    )

    where = db.cavadalabs_requestledgertable.count.call_args.kwargs["where"]
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
    assert where["spend"] == {"gte": 0.1, "lte": 0.2}
    assert response.metadata.total_spend == pytest.approx(0.15)


@pytest.mark.asyncio
async def test_company_daily_activity_aggregates_all_ledger_rows_before_day_pagination(
    monkeypatch,
):
    db = _db()
    latest_day_rows = [
        _ledger(
            request_id=f"request-latest-{idx}",
            prompt_tokens=2,
            completion_tokens=3,
            total_tokens=5,
            spend=0.01,
            created_at=datetime(2026, 5, 15, 12, idx % 60, tzinfo=timezone.utc),
        )
        for idx in range(120)
    ]
    previous_day_rows = [
        _ledger(
            request_id=f"request-previous-{idx}",
            prompt_tokens=1,
            completion_tokens=2,
            total_tokens=3,
            spend=0.02,
            created_at=datetime(2026, 5, 14, 12, idx % 60, tzinfo=timezone.utc),
        )
        for idx in range(30)
    ]
    ledger_rows = [*latest_day_rows, *previous_day_rows]
    db.cavadalabs_requestledgertable.count = AsyncMock(return_value=len(ledger_rows))
    db.cavadalabs_requestledgertable.find_many = _paginated_ledger_find_many(
        ledger_rows
    )
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[_company()])
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[_project()])
    _patch_prisma(monkeypatch, db)

    response = await company_endpoints.get_company_daily_activity(
        http_request=MagicMock(),
        start_date="2026-05-14",
        end_date="2026-05-15",
        model=None,
        provider=None,
        status_filter=None,
        api_key=None,
        min_spend=None,
        max_spend=None,
        company_ids="company-1",
        page=1,
        page_size=1,
        timezone=0,
        user_api_key_dict=_admin_auth(),
    )

    assert response.metadata.total_api_requests == 150
    assert response.metadata.total_prompt_tokens == 270
    assert response.metadata.total_completion_tokens == 420
    assert response.metadata.total_spend == pytest.approx(1.8)
    assert response.metadata.total_pages == 2
    assert response.metadata.has_more is True
    assert len(response.results) == 1
    assert response.results[0].date.isoformat() == "2026-05-15"
    assert response.results[0].metrics.api_requests == 120
    assert response.results[0].metrics.spend == pytest.approx(1.2)


@pytest.mark.asyncio
async def test_company_daily_activity_aggregates_multiple_ledger_pages_into_one_day(
    monkeypatch,
):
    db = _db()
    ledger_rows = [
        _ledger(
            request_id=f"request-page-{idx}",
            prompt_tokens=1,
            completion_tokens=2,
            total_tokens=3,
            spend=0.01,
            created_at=datetime(2026, 5, 15, 12, idx % 60, tzinfo=timezone.utc),
        )
        for idx in range(1205)
    ]
    db.cavadalabs_requestledgertable.count = AsyncMock(return_value=len(ledger_rows))
    db.cavadalabs_requestledgertable.find_many = _paginated_ledger_find_many(
        ledger_rows
    )
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[_company()])
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[_project()])
    _patch_prisma(monkeypatch, db)

    response = await company_endpoints.get_company_daily_activity(
        http_request=MagicMock(),
        start_date="2026-05-15",
        end_date="2026-05-15",
        model=None,
        provider=None,
        status_filter=None,
        api_key=None,
        min_spend=None,
        max_spend=None,
        company_ids="company-1",
        page=1,
        page_size=100,
        timezone=0,
        user_api_key_dict=_admin_auth(),
    )

    ledger_fetch_calls = [
        call.kwargs
        for call in db.cavadalabs_requestledgertable.find_many.call_args_list
        if call.kwargs.get("take") == 1000
    ]
    assert [call["skip"] for call in ledger_fetch_calls] == [0, 1000]
    assert response.metadata.total_api_requests == 1205
    assert response.metadata.total_prompt_tokens == 1205
    assert response.metadata.total_completion_tokens == 2410
    assert response.metadata.total_spend == pytest.approx(12.05)
    assert response.metadata.total_pages == 1
    assert response.metadata.has_more is False
    assert len(response.results) == 1
    assert response.results[0].date.isoformat() == "2026-05-15"
    assert response.results[0].metrics.api_requests == 1205
    assert response.results[0].metrics.spend == pytest.approx(12.05)


@pytest.mark.asyncio
async def test_project_daily_activity_aggregates_project_ledger_without_team_scope():
    db = _db()
    ledger_rows = [
        _ledger(
            request_id=f"project-request-{idx}",
            prompt_tokens=4,
            completion_tokens=6,
            total_tokens=10,
            spend=0.05,
            created_at=datetime(2026, 5, 15, 12, idx, tzinfo=timezone.utc),
        )
        for idx in range(10)
    ]
    db.cavadalabs_requestledgertable.count = AsyncMock(return_value=len(ledger_rows))
    db.cavadalabs_requestledgertable.find_many = _paginated_ledger_find_many(
        ledger_rows
    )
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[_project()])

    response = await get_cavadalabs_daily_activity(
        prisma_client=SimpleNamespace(db=db),
        entity_id_field="project_id",
        entity_id=["project-1"],
        start_date="2026-05-15",
        end_date="2026-05-15",
        model=None,
        provider=None,
        status_filter=None,
        api_key=None,
        min_spend=None,
        max_spend=None,
        page=1,
        page_size=100,
        timezone_offset_minutes=0,
    )

    where = db.cavadalabs_requestledgertable.count.call_args.kwargs["where"]
    assert where["project_id"] == {"in": ["project-1"]}
    assert "team_id" not in where
    assert "organization_id" not in where
    assert response.metadata.total_api_requests == 10
    assert response.metadata.total_prompt_tokens == 40
    assert response.metadata.total_completion_tokens == 60
    assert response.metadata.total_spend == pytest.approx(0.5)
    assert response.results[0].breakdown.entities["project-1"].metrics.spend == (
        pytest.approx(0.5)
    )


@pytest.mark.asyncio
async def test_company_daily_activity_reports_missing_schema_with_migration_command(
    monkeypatch,
):
    db = _db()
    db.cavadalabs_requestledgertable.find_many = AsyncMock(
        side_effect=Exception('relation "CavadaLabs_RequestLedgerTable" does not exist')
    )
    _patch_prisma(monkeypatch, db)

    with pytest.raises(HTTPException) as exc_info:
        await company_endpoints.get_company_daily_activity(
            http_request=MagicMock(),
            start_date="2026-05-15",
            end_date="2026-05-15",
            model=None,
            provider=None,
            status_filter=None,
            api_key=None,
            min_spend=None,
            max_spend=None,
            company_ids="company-1",
            page=1,
            page_size=100,
            timezone=0,
            user_api_key_dict=_admin_auth(),
        )

    assert exc_info.value.status_code == 503
    _assert_missing_usage_schema_detail(exc_info.value.detail)
    db.cavadalabs_requestledgertable.count.assert_not_awaited()
    db.litellm_spendlogs.find_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_project_daily_activity_reports_missing_schema_with_migration_command(
    monkeypatch,
):
    db = _db()
    db.cavadalabs_requestledgertable.find_many = AsyncMock(
        side_effect=Exception('column "project_id" does not exist')
    )
    _patch_prisma(monkeypatch, db)

    with pytest.raises(HTTPException) as exc_info:
        await project_endpoints.get_project_daily_activity(
            http_request=MagicMock(),
            start_date="2026-05-15",
            end_date="2026-05-15",
            model=None,
            provider=None,
            status_filter=None,
            api_key=None,
            min_spend=None,
            max_spend=None,
            project_ids="project-1",
            page=1,
            page_size=100,
            timezone=0,
            user_api_key_dict=_admin_auth(),
        )

    assert exc_info.value.status_code == 503
    _assert_missing_usage_schema_detail(exc_info.value.detail)
    db.cavadalabs_requestledgertable.count.assert_not_awaited()
    db.litellm_spendlogs.find_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_company_daily_activity_reports_missing_spendlogs_repair_schema(
    monkeypatch,
):
    db = _db()
    db.litellm_spendlogs.count = AsyncMock(
        side_effect=Exception('column "model_group" does not exist')
    )
    _patch_prisma(monkeypatch, db)

    with pytest.raises(HTTPException) as exc_info:
        await company_endpoints.get_company_daily_activity(
            http_request=MagicMock(),
            start_date="2026-05-15",
            end_date="2026-05-15",
            model=None,
            provider=None,
            status_filter=None,
            api_key=None,
            min_spend=None,
            max_spend=None,
            company_ids="company-1",
            page=1,
            page_size=100,
            timezone=0,
            user_api_key_dict=_admin_auth(),
        )

    assert exc_info.value.status_code == 503
    _assert_missing_usage_schema_detail(exc_info.value.detail)
    assert any(
        "LiteLLM_SpendLogs" in missing
        for missing in exc_info.value.detail["missing_schema"]
    )
    probe_where = db.litellm_spendlogs.count.call_args.kwargs["where"]
    assert probe_where["request_id"] == "__cavadalabs_schema_probe__"
    db.cavadalabs_requestledgertable.count.assert_awaited_once()
    db.litellm_spendlogs.find_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_company_daily_activity_reads_existing_ledger_when_key_backfill_schema_missing(
    monkeypatch,
):
    db = _db()
    db.litellm_deletedverificationtoken = None
    db.cavadalabs_requestledgertable.count = AsyncMock(return_value=1)
    db.cavadalabs_requestledgertable.find_many = AsyncMock(return_value=[_ledger()])
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[_company()])
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[_project()])
    _patch_prisma(monkeypatch, db)

    response = await company_endpoints.get_company_daily_activity(
        http_request=MagicMock(),
        start_date="2026-05-15",
        end_date="2026-05-15",
        model=None,
        provider=None,
        status_filter=None,
        api_key=None,
        min_spend=None,
        max_spend=None,
        company_ids="company-1",
        page=1,
        page_size=100,
        timezone=0,
        user_api_key_dict=_admin_auth(),
    )

    assert response.metadata.total_api_requests == 1
    assert response.metadata.total_spend == pytest.approx(0.15)
    db.cavadalabs_requestledgertable.find_many.assert_awaited()
    db.litellm_spendlogs.find_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_company_daily_activity_reads_existing_ledger_when_spendlogs_repair_schema_missing(
    monkeypatch,
):
    db = _db()
    db.litellm_spendlogs.count = AsyncMock(
        side_effect=Exception('column "model_group" does not exist')
    )
    db.cavadalabs_requestledgertable.count = AsyncMock(return_value=1)
    db.cavadalabs_requestledgertable.find_many = AsyncMock(return_value=[_ledger()])
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[_company()])
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[_project()])
    _patch_prisma(monkeypatch, db)

    response = await company_endpoints.get_company_daily_activity(
        http_request=MagicMock(),
        start_date="2026-05-15",
        end_date="2026-05-15",
        model=None,
        provider=None,
        status_filter=None,
        api_key=None,
        min_spend=None,
        max_spend=None,
        company_ids="company-1",
        page=1,
        page_size=100,
        timezone=0,
        user_api_key_dict=_admin_auth(),
    )

    assert response.metadata.total_api_requests == 1
    assert response.metadata.total_spend == pytest.approx(0.15)
    db.cavadalabs_requestledgertable.find_many.assert_awaited()
    db.litellm_spendlogs.find_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_project_daily_activity_reads_existing_ledger_when_key_backfill_schema_missing(
    monkeypatch,
):
    db = _db()
    db.litellm_deletedverificationtoken = None
    db.cavadalabs_requestledgertable.count = AsyncMock(return_value=1)
    db.cavadalabs_requestledgertable.find_many = AsyncMock(return_value=[_ledger()])
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[_company()])
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[_project()])
    _patch_prisma(monkeypatch, db)

    response = await project_endpoints.get_project_daily_activity(
        http_request=MagicMock(),
        start_date="2026-05-15",
        end_date="2026-05-15",
        model=None,
        provider=None,
        status_filter=None,
        api_key=None,
        min_spend=None,
        max_spend=None,
        project_ids="project-1",
        page=1,
        page_size=100,
        timezone=0,
        user_api_key_dict=_admin_auth(),
    )

    assert response.metadata.total_api_requests == 1
    assert response.metadata.total_spend == pytest.approx(0.15)
    where = db.cavadalabs_requestledgertable.count.call_args.kwargs["where"]
    assert where["project_id"] == {"in": ["project-1"]}
    db.cavadalabs_requestledgertable.find_many.assert_awaited()
    db.litellm_spendlogs.find_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_project_daily_activity_reads_existing_ledger_when_spendlogs_repair_schema_missing(
    monkeypatch,
):
    db = _db()
    db.litellm_spendlogs.count = AsyncMock(
        side_effect=Exception('column "model_group" does not exist')
    )
    db.cavadalabs_requestledgertable.count = AsyncMock(return_value=1)
    db.cavadalabs_requestledgertable.find_many = AsyncMock(return_value=[_ledger()])
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[_company()])
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[_project()])
    _patch_prisma(monkeypatch, db)

    response = await project_endpoints.get_project_daily_activity(
        http_request=MagicMock(),
        start_date="2026-05-15",
        end_date="2026-05-15",
        model=None,
        provider=None,
        status_filter=None,
        api_key=None,
        min_spend=None,
        max_spend=None,
        project_ids="project-1",
        page=1,
        page_size=100,
        timezone=0,
        user_api_key_dict=_admin_auth(),
    )

    assert response.metadata.total_api_requests == 1
    assert response.metadata.total_spend == pytest.approx(0.15)
    where = db.cavadalabs_requestledgertable.count.call_args.kwargs["where"]
    assert where["project_id"] == {"in": ["project-1"]}
    db.cavadalabs_requestledgertable.find_many.assert_awaited()
    db.litellm_spendlogs.find_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_company_daily_activity_empty_ledger_reports_missing_key_backfill_schema(
    monkeypatch,
):
    db = _db()
    db.litellm_deletedverificationtoken = None
    db.cavadalabs_requestledgertable.count = AsyncMock(return_value=0)
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[_company()])
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[_project()])
    _patch_prisma(monkeypatch, db)

    with pytest.raises(HTTPException) as exc_info:
        await company_endpoints.get_company_daily_activity(
            http_request=MagicMock(),
            start_date="2026-05-15",
            end_date="2026-05-15",
            model=None,
            provider=None,
            status_filter=None,
            api_key=None,
            min_spend=None,
            max_spend=None,
            company_ids="company-1",
            page=1,
            page_size=100,
            timezone=0,
            user_api_key_dict=_admin_auth(),
        )

    assert exc_info.value.status_code == 503
    detail = exc_info.value.detail
    assert detail["operation"] == "repair_empty_cavadalabs_daily_activity"
    _assert_missing_usage_schema_detail(detail)
    assert "LiteLLM_DeletedVerificationToken delegate" in detail["missing_schema"]
    db.litellm_spendlogs.find_many.assert_not_awaited()
    db.cavadalabs_requestledgertable.create_many.assert_not_called()


@pytest.mark.asyncio
async def test_project_daily_activity_empty_ledger_reports_missing_key_backfill_schema(
    monkeypatch,
):
    db = _db()
    db.litellm_deletedverificationtoken = None
    db.cavadalabs_requestledgertable.count = AsyncMock(return_value=0)
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[_company()])
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[_project()])
    _patch_prisma(monkeypatch, db)

    with pytest.raises(HTTPException) as exc_info:
        await project_endpoints.get_project_daily_activity(
            http_request=MagicMock(),
            start_date="2026-05-15",
            end_date="2026-05-15",
            model=None,
            provider=None,
            status_filter=None,
            api_key=None,
            min_spend=None,
            max_spend=None,
            project_ids="project-1",
            page=1,
            page_size=100,
            timezone=0,
            user_api_key_dict=_admin_auth(),
        )

    assert exc_info.value.status_code == 503
    detail = exc_info.value.detail
    assert detail["operation"] == "repair_empty_cavadalabs_daily_activity"
    _assert_missing_usage_schema_detail(detail)
    assert "LiteLLM_DeletedVerificationToken delegate" in detail["missing_schema"]
    db.litellm_spendlogs.find_many.assert_not_awaited()
    db.cavadalabs_requestledgertable.create_many.assert_not_called()


@pytest.mark.asyncio
async def test_company_daily_activity_reports_missing_schema_when_ledger_count_fails_after_probe(
    monkeypatch,
):
    db = _db()
    db.cavadalabs_requestledgertable.find_many = AsyncMock(return_value=[])
    db.cavadalabs_requestledgertable.count = AsyncMock(
        side_effect=Exception('column "company_id" does not exist')
    )
    _patch_prisma(monkeypatch, db)

    with pytest.raises(HTTPException) as exc_info:
        await company_endpoints.get_company_daily_activity(
            http_request=MagicMock(),
            start_date="2026-05-15",
            end_date="2026-05-15",
            model=None,
            provider=None,
            status_filter=None,
            api_key=None,
            min_spend=None,
            max_spend=None,
            company_ids="company-1",
            page=1,
            page_size=100,
            timezone=0,
            user_api_key_dict=_admin_auth(),
        )

    assert exc_info.value.status_code == 503
    _assert_missing_usage_schema_detail(exc_info.value.detail)
    assert any(
        "CavadaLabs usage read path" in missing
        for missing in exc_info.value.detail["missing_schema"]
    )
    db.litellm_spendlogs.find_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_project_daily_activity_endpoint_rejects_inaccessible_project_scope(
    monkeypatch,
):
    db = _db()
    _patch_prisma(monkeypatch, db)

    with pytest.raises(HTTPException) as exc_info:
        await project_endpoints.get_project_daily_activity(
            http_request=MagicMock(),
            start_date="2026-05-15",
            end_date="2026-05-15",
            model=None,
            provider=None,
            status_filter=None,
            api_key=None,
            min_spend=None,
            max_spend=None,
            project_ids="project-2",
            page=1,
            page_size=100,
            timezone=0,
            user_api_key_dict=_auth(),
        )

    assert exc_info.value.status_code == 403
    db.cavadalabs_requestledgertable.count.assert_not_awaited()


@pytest.mark.asyncio
async def test_company_daily_activity_repairs_spend_log_matching_model_group_filter(
    monkeypatch,
):
    db = _db()
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[_company()])
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[_project()])
    db.cavadalabs_requestledgertable.count = AsyncMock(side_effect=[0, 1])
    db.cavadalabs_requestledgertable.find_many = AsyncMock(
        return_value=[
            _ledger(
                request_id="req-model-group-history",
                model="openai/gpt-4.1",
                metadata={
                    "model_group": "cavadalabs/qwen3-32b",
                    "call_type": "chat",
                },
            )
        ]
    )
    db.litellm_spendlogs.find_many = AsyncMock(
        return_value=[
            _spend_log(
                request_id="req-model-group-history",
                api_key="hashed-key",
                model="openai/gpt-4.1",
                model_group="cavadalabs/qwen3-32b",
                custom_llm_provider="openai",
                team_id="team-project-1",
                metadata={},
            )
        ]
    )
    db.cavadalabs_requestledgertable.create_many = AsyncMock(
        return_value=SimpleNamespace(count=1)
    )
    _patch_prisma(monkeypatch, db)

    response = await company_endpoints.get_company_daily_activity(
        http_request=MagicMock(),
        start_date="2026-05-15",
        end_date="2026-05-15",
        model="cavadalabs/qwen3-32b",
        provider=None,
        status_filter=None,
        api_key=None,
        min_spend=None,
        max_spend=None,
        company_ids="company-1",
        page=1,
        page_size=100,
        timezone=0,
        user_api_key_dict=_admin_auth(),
    )

    ledger_where = db.cavadalabs_requestledgertable.count.call_args.kwargs["where"]
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
    } in ledger_where["AND"]
    spend_where = db.litellm_spendlogs.find_many.call_args.kwargs["where"]
    model_condition = _find_and_or_condition(
        spend_where, {"model": "cavadalabs/qwen3-32b"}
    )
    assert {"model_group": "cavadalabs/qwen3-32b"} in model_condition["OR"]
    assert {
        "metadata": {
            "path": ["spend_logs_metadata", "cavadalabs_model_alias"],
            "equals": "cavadalabs/qwen3-32b",
        }
    } in model_condition["OR"]
    ledger_row = db.cavadalabs_requestledgertable.create_many.call_args.kwargs["data"][
        0
    ]
    assert ledger_row["company_id"] == "company-1"
    assert ledger_row["project_id"] == "project-1"
    assert response.metadata.total_api_requests == 1
    assert response.metadata.total_spend == pytest.approx(0.15)


@pytest.mark.asyncio
async def test_company_daily_activity_repairs_spend_log_matching_cavada_metadata_filters(
    monkeypatch,
):
    db = _db()
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[_company()])
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[_project()])
    db.cavadalabs_requestledgertable.count = AsyncMock(side_effect=[0, 1])
    db.cavadalabs_requestledgertable.find_many = AsyncMock(
        return_value=[
            _ledger(
                request_id="req-cavada-metadata-filters",
                provider="cavadalabs",
                model="cavadalabs/qwen3-32b",
            )
        ]
    )
    db.litellm_spendlogs.find_many = AsyncMock(
        return_value=[
            _spend_log(
                request_id="req-cavada-metadata-filters",
                api_key="hashed-key",
                model="openai/gpt-4.1",
                model_group="legacy-group",
                custom_llm_provider="openai",
                metadata={
                    "spend_logs_metadata": {
                        "cavadalabs_company_id": "company-1",
                        "cavadalabs_project_id": "project-1",
                        "cavadalabs_provider": "cavadalabs",
                        "cavadalabs_model_alias": "cavadalabs/qwen3-32b",
                    }
                },
            )
        ]
    )
    db.cavadalabs_requestledgertable.create_many = AsyncMock(
        return_value=SimpleNamespace(count=1)
    )
    _patch_prisma(monkeypatch, db)

    response = await company_endpoints.get_company_daily_activity(
        http_request=MagicMock(),
        start_date="2026-05-15",
        end_date="2026-05-15",
        model="cavadalabs/qwen3-32b",
        provider="cavadalabs",
        status_filter=None,
        api_key=None,
        min_spend=None,
        max_spend=None,
        company_ids="company-1",
        page=1,
        page_size=100,
        timezone=0,
        user_api_key_dict=_admin_auth(),
    )

    spend_where = db.litellm_spendlogs.find_many.call_args.kwargs["where"]
    model_condition = _find_and_or_condition(
        spend_where, {"model": "cavadalabs/qwen3-32b"}
    )
    assert {
        "metadata": {
            "path": ["spend_logs_metadata", "cavadalabs_model_alias"],
            "equals": "cavadalabs/qwen3-32b",
        }
    } in model_condition["OR"]
    provider_condition = _find_and_or_condition(
        spend_where, {"custom_llm_provider": "cavadalabs"}
    )
    assert {
        "metadata": {
            "path": ["spend_logs_metadata", "cavadalabs_provider"],
            "equals": "cavadalabs",
        }
    } in provider_condition["OR"]
    ledger_row = db.cavadalabs_requestledgertable.create_many.call_args.kwargs["data"][
        0
    ]
    assert ledger_row["provider"] == "cavadalabs"
    assert ledger_row["model"] == "cavadalabs/qwen3-32b"
    assert ledger_row["company_id"] == "company-1"
    assert ledger_row["project_id"] == "project-1"
    assert response.metadata.total_api_requests == 1
    assert response.metadata.total_spend == pytest.approx(0.15)


@pytest.mark.asyncio
async def test_usage_diagnostics_reports_missing_ledger_schema_without_500():
    db = _db()
    db.cavadalabs_requestledgertable.find_many = AsyncMock(
        side_effect=Exception('column "company_id" does not exist')
    )

    response = await get_cavadalabs_usage_diagnostics(
        prisma_client=SimpleNamespace(db=db),
        entity_type="company",
        entity_id=["company-1"],
        start_date="2026-05-01",
        end_date="2026-05-31",
        timezone_offset_minutes=0,
    )

    assert response.schema_status == CavadaLabsUsageSchemaStatus.MISSING_SCHEMA
    assert response.migration_status == CavadaLabsUsageMigrationStatus.SCHEMA_MISSING
    assert response.missing_schema
    assert response.migration_command
    assert (
        response.diagnostics[0].status
        == CavadaLabsUsageDiagnosticsStatus.BACKFILL_REQUIRED
    )
    assert (
        response.diagnostics[0].recommended_action
        == CavadaLabsUsageDiagnosticsAction.RUN_MIGRATION_BACKFILL
    )
    assert "migration" in response.diagnostics[0].message.lower()


@pytest.mark.asyncio
async def test_usage_diagnostics_reports_missing_key_metadata_schema_before_empty_usage():
    db = _db()
    db.litellm_deletedverificationtoken = None

    response = await get_cavadalabs_usage_diagnostics(
        prisma_client=SimpleNamespace(db=db),
        entity_type="company",
        entity_id=["company-1"],
        start_date="2026-05-01",
        end_date="2026-05-31",
        timezone_offset_minutes=0,
    )

    assert response.schema_status == CavadaLabsUsageSchemaStatus.MISSING_SCHEMA
    assert response.migration_status == CavadaLabsUsageMigrationStatus.SCHEMA_MISSING
    assert "LiteLLM_DeletedVerificationToken delegate" in response.missing_schema
    assert "prisma migrate deploy" in response.migration_command
    assert (
        response.diagnostics[0].recommended_action
        == CavadaLabsUsageDiagnosticsAction.RUN_MIGRATION_BACKFILL
    )
    probe_where = db.litellm_spendlogs.count.call_args.kwargs["where"]
    assert probe_where["request_id"] == "__cavadalabs_schema_probe__"


@pytest.mark.asyncio
async def test_usage_diagnostics_reports_partial_key_context_schema_as_migration_missing():
    db = _db()
    db.litellm_verificationtoken.find_many = AsyncMock(
        side_effect=Exception('Unknown argument "organization_id"')
    )

    response = await get_cavadalabs_usage_diagnostics(
        prisma_client=SimpleNamespace(db=db),
        entity_type="project",
        entity_id=["project-1"],
        start_date="2026-05-01",
        end_date="2026-05-31",
        timezone_offset_minutes=0,
    )

    assert response.schema_status == CavadaLabsUsageSchemaStatus.MISSING_SCHEMA
    assert response.migration_status == CavadaLabsUsageMigrationStatus.SCHEMA_MISSING
    assert any(
        "LiteLLM_VerificationToken" in missing for missing in response.missing_schema
    )
    assert "prisma migrate deploy" in response.migration_command
    assert (
        response.diagnostics[0].recommended_action
        == CavadaLabsUsageDiagnosticsAction.RUN_MIGRATION_BACKFILL
    )
    db.litellm_spendlogs.find_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_usage_diagnostics_distinguishes_restrictive_filters_from_missing_usage():
    db = _db()
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[_company()])
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[_project()])
    db.cavadalabs_requestledgertable.count = AsyncMock(return_value=0)

    async def _count_spend_logs(*, where):
        if "model-that-does-not-match" in str(where):
            return 0
        return 2

    db.litellm_spendlogs.count = AsyncMock(side_effect=_count_spend_logs)

    response = await get_cavadalabs_usage_diagnostics(
        prisma_client=SimpleNamespace(db=db),
        entity_type="company",
        entity_id=["company-1"],
        start_date="2026-05-01",
        end_date="2026-05-31",
        timezone_offset_minutes=0,
        model="model-that-does-not-match",
        provider="provider-that-does-not-match",
        api_key="key-that-does-not-match",
    )

    item = response.diagnostics[0]
    assert response.schema_status == CavadaLabsUsageSchemaStatus.READY
    assert response.migration_status == CavadaLabsUsageMigrationStatus.READY
    assert item.status == CavadaLabsUsageDiagnosticsStatus.FILTERS_EXCLUDE_USAGE
    assert item.recommended_action == CavadaLabsUsageDiagnosticsAction.NONE
    assert item.attributable_spend_logs == 0
    assert item.unfiltered_attributable_spend_logs == 2
    assert item.filters_exclude_usage is True
    assert item.scoped_backfill_available is False


@pytest.mark.asyncio
async def test_usage_diagnostics_applies_status_and_spend_filters_to_filter_exclusion():
    db = _db()
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[_company()])
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[_project()])
    db.cavadalabs_requestledgertable.count = AsyncMock(return_value=0)

    async def _count_spend_logs(*, where):
        if where.get("request_id") == "__cavadalabs_schema_probe__":
            return 0
        conditions = where.get("AND", [])
        if {"status": "error"} in conditions or {"spend": {"gte": 10.0}} in conditions:
            return 0
        return 2

    db.litellm_spendlogs.count = AsyncMock(side_effect=_count_spend_logs)

    response = await get_cavadalabs_usage_diagnostics(
        prisma_client=SimpleNamespace(db=db),
        entity_type="company",
        entity_id=["company-1"],
        start_date="2026-05-01",
        end_date="2026-05-31",
        timezone_offset_minutes=0,
        status_filter="error",
        min_spend=10.0,
    )

    item = response.diagnostics[0]
    assert item.status == CavadaLabsUsageDiagnosticsStatus.FILTERS_EXCLUDE_USAGE
    assert item.recommended_action == CavadaLabsUsageDiagnosticsAction.NONE
    assert item.attributable_spend_logs == 0
    assert item.unfiltered_attributable_spend_logs == 2
    assert item.filters_exclude_usage is True
    ledger_where = db.cavadalabs_requestledgertable.count.call_args.kwargs["where"]
    assert ledger_where["status"] == "error"
    assert ledger_where["spend"] == {"gte": 10.0}
    filtered_spend_where = db.litellm_spendlogs.count.call_args_list[1].kwargs[
        "where"
    ]
    assert {"status": "error"} in filtered_spend_where["AND"]
    assert {"spend": {"gte": 10.0}} in filtered_spend_where["AND"]


@pytest.mark.asyncio
async def test_usage_diagnostics_reports_genuine_zero_when_no_ledger_or_legacy_spend():
    db = _db()
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[_company()])
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[_project()])
    db.cavadalabs_requestledgertable.count = AsyncMock(return_value=0)
    db.litellm_spendlogs.count = AsyncMock(return_value=0)

    response = await get_cavadalabs_usage_diagnostics(
        prisma_client=SimpleNamespace(db=db),
        entity_type="company",
        entity_id=["company-1"],
        start_date="2026-05-01",
        end_date="2026-05-31",
        timezone_offset_minutes=0,
    )

    item = response.diagnostics[0]
    assert response.schema_status == CavadaLabsUsageSchemaStatus.READY
    assert response.migration_status == CavadaLabsUsageMigrationStatus.READY
    assert item.status == CavadaLabsUsageDiagnosticsStatus.NO_ATTRIBUTABLE_SPEND
    assert item.recommended_action == CavadaLabsUsageDiagnosticsAction.NONE
    assert item.ledger_rows == 0
    assert item.attributable_spend_logs == 0
    assert item.unmapped_spend_logs == 0
    assert item.missing_mappings == []
    assert item.scoped_backfill_available is False
    assert "No CavadaLabs-attributable spend exists" in item.message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("entity_type", "entity_id", "project_row"),
    [
        ("company", "company-1", _project(litellm_team_id=None)),
        ("project", "project-1", _project(litellm_team_id=None)),
    ],
)
async def test_usage_diagnostics_reports_scoped_backfill_from_virtual_key_metadata(
    entity_type,
    entity_id,
    project_row,
):
    db = _db()
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[_company()])
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[project_row])
    db.cavadalabs_requestledgertable.count = AsyncMock(return_value=0)
    db.litellm_verificationtoken.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                token="key-with-cavada-metadata",
                team_id=None,
                organization_id=None,
                metadata={
                    "cavadalabs_company_id": "company-1",
                    "cavadalabs_project_id": "project-1",
                    "spend_logs_metadata": {
                        "cavadalabs_company_id": "company-1",
                        "cavadalabs_project_id": "project-1",
                    },
                },
            )
        ]
    )

    async def _count_spend_logs(*, where):
        if where.get("request_id") == "__cavadalabs_schema_probe__":
            return 0
        if "key-with-cavada-metadata" in str(where):
            return 2
        return 0

    db.litellm_spendlogs.count = AsyncMock(side_effect=_count_spend_logs)

    response = await get_cavadalabs_usage_diagnostics(
        prisma_client=SimpleNamespace(db=db),
        entity_type=entity_type,
        entity_id=[entity_id],
        start_date="2026-05-01",
        end_date="2026-05-31",
        timezone_offset_minutes=0,
    )

    item = response.diagnostics[0]
    assert response.schema_status == CavadaLabsUsageSchemaStatus.READY
    assert response.migration_status == CavadaLabsUsageMigrationStatus.BACKFILL_PENDING
    assert item.entity_type == entity_type
    assert item.entity_id == entity_id
    assert item.status == CavadaLabsUsageDiagnosticsStatus.SCOPED_BACKFILL_AVAILABLE
    assert (
        item.recommended_action == CavadaLabsUsageDiagnosticsAction.RUN_SCOPED_BACKFILL
    )
    assert item.ledger_rows == 0
    assert item.attributable_spend_logs == 2
    assert item.key_metadata_spend_logs == 2
    assert item.ledger_gap == 2
    assert item.scoped_backfill_available is True


@pytest.mark.asyncio
async def test_usage_diagnostics_reports_legacy_keys_missing_cavadalabs_metadata():
    db = _db()
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[_company()])
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[_project()])
    db.cavadalabs_requestledgertable.count = AsyncMock(return_value=0)
    db.litellm_verificationtoken.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                token="legacy-team-key",
                team_id="team-project-1",
                organization_id="org-company-1",
                metadata={"owner": "support"},
            )
        ]
    )

    async def _count_spend_logs(*, where):
        if where.get("request_id") == "__cavadalabs_schema_probe__":
            return 0
        if "legacy-team-key" in str(where):
            return 3
        return 0

    db.litellm_spendlogs.count = AsyncMock(side_effect=_count_spend_logs)

    response = await get_cavadalabs_usage_diagnostics(
        prisma_client=SimpleNamespace(db=db),
        entity_type="company",
        entity_id=["company-1"],
        start_date="2026-05-01",
        end_date="2026-05-31",
        timezone_offset_minutes=0,
    )

    item = response.diagnostics[0]
    assert item.status == CavadaLabsUsageDiagnosticsStatus.SCOPED_BACKFILL_AVAILABLE
    assert item.attributable_spend_logs == 3
    assert item.key_metadata_spend_logs == 3
    assert item.legacy_keys_missing_metadata == 1
    assert item.legacy_key_spend_logs == 3
    assert item.ledger_gap == 3


@pytest.mark.asyncio
async def test_usage_diagnostics_reports_unattributable_legacy_company_key_without_project_metadata():
    db = _db()
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[_company()])
    db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[_project(litellm_team_id=None)]
    )
    db.cavadalabs_requestledgertable.count = AsyncMock(return_value=0)
    db.litellm_verificationtoken.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                token="legacy-org-key",
                team_id=None,
                organization_id="org-company-1",
                metadata={"owner": "support"},
            )
        ]
    )

    async def _count_spend_logs(*, where):
        if where.get("request_id") == "__cavadalabs_schema_probe__":
            return 0
        if "legacy-org-key" in str(where):
            return 4
        return 0

    db.litellm_spendlogs.count = AsyncMock(side_effect=_count_spend_logs)

    response = await get_cavadalabs_usage_diagnostics(
        prisma_client=SimpleNamespace(db=db),
        entity_type="company",
        entity_id=["company-1"],
        start_date="2026-05-01",
        end_date="2026-05-31",
        timezone_offset_minutes=0,
    )

    item = response.diagnostics[0]
    assert item.status == CavadaLabsUsageDiagnosticsStatus.MISSING_COMPATIBILITY_MAPPING
    assert (
        item.recommended_action
        == CavadaLabsUsageDiagnosticsAction.FIX_COMPATIBILITY_MAPPING
    )
    assert item.attributable_spend_logs == 0
    assert item.legacy_keys_missing_metadata == 1
    assert item.legacy_key_spend_logs == 4
    assert item.missing_mappings == [
        "CavadaLabs key metadata or Project compatibility mapping"
    ]


@pytest.mark.asyncio
async def test_usage_diagnostics_reports_unrepairable_legacy_spend_missing_links():
    db = _db()
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[_company()])
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[])
    db.cavadalabs_requestledgertable.count = AsyncMock(return_value=0)

    async def _count_spend_logs(*, where):
        if where.get("OR") == [{"organization_id": "org-company-1"}]:
            return 2
        return 0

    db.litellm_spendlogs.count = AsyncMock(side_effect=_count_spend_logs)

    response = await get_cavadalabs_usage_diagnostics(
        prisma_client=SimpleNamespace(db=db),
        entity_type="company",
        entity_id=["company-1"],
        start_date="2026-05-01",
        end_date="2026-05-31",
        timezone_offset_minutes=0,
    )

    item = response.diagnostics[0]
    assert response.schema_status == CavadaLabsUsageSchemaStatus.READY
    assert response.migration_status == CavadaLabsUsageMigrationStatus.READY
    assert item.status == CavadaLabsUsageDiagnosticsStatus.MISSING_COMPATIBILITY_MAPPING
    assert (
        item.recommended_action
        == CavadaLabsUsageDiagnosticsAction.FIX_COMPATIBILITY_MAPPING
    )
    assert item.attributable_spend_logs == 0
    assert item.unmapped_spend_logs == 2
    assert item.scoped_backfill_available is False
    assert item.missing_mappings == [
        "CavadaLabs key metadata or Project compatibility mapping"
    ]
    assert "Missing compatibility mapping" in item.message


@pytest.mark.asyncio
async def test_usage_repair_reports_missing_key_metadata_schema_without_backfill():
    db = _db()
    db.litellm_verificationtoken = None

    response = await repair_cavadalabs_usage_scope(
        prisma_client=SimpleNamespace(db=db),
        entity_type="project",
        entity_id=["project-1"],
        start_date="2026-05-01",
        end_date="2026-05-31",
        timezone_offset_minutes=0,
        dry_run=True,
    )

    assert response.attempted is False
    assert response.repaired is False
    assert response.schema_status == CavadaLabsUsageSchemaStatus.MISSING_SCHEMA
    assert response.migration_status == CavadaLabsUsageMigrationStatus.SCHEMA_MISSING
    assert "LiteLLM_VerificationToken delegate" in response.missing_schema
    assert "migration" in response.message.lower()
    db.litellm_spendlogs.find_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_usage_repair_dry_run_counts_without_writing_ledger():
    db = _db()
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[_company()])
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[_project()])
    db.cavadalabs_requestledgertable.create_many = AsyncMock()
    db.litellm_spendlogs.count = AsyncMock(return_value=2)

    response = await repair_cavadalabs_usage_scope(
        prisma_client=SimpleNamespace(db=db),
        entity_type="company",
        entity_id=["company-1"],
        start_date="2026-05-01",
        end_date="2026-05-31",
        timezone_offset_minutes=0,
        model="cavadalabs/qwen3-32b",
        provider="cavadalabs",
        api_key="hashed-key",
        dry_run=True,
        batch_limit=10,
    )

    assert response.dry_run is True
    assert response.attempted is True
    assert response.repaired is False
    assert response.scoped_spend_logs == 2
    assert response.processed_spend_logs == 0
    assert response.batch_limit == 10
    assert "Dry run completed" in response.message
    assert _raw_spend_logs_backfill_fetch_calls(db) == []
    db.cavadalabs_requestledgertable.create_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_usage_repair_apply_backfills_limited_batch_then_daily_activity_reads_ledger(
    monkeypatch,
):
    db = _db()
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[_company()])
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[_project()])
    db.litellm_spendlogs.count = AsyncMock(return_value=2)
    db.litellm_spendlogs.find_many = AsyncMock(
        return_value=[
            _spend_log(
                request_id="req-company-backfill",
                api_key="hashed-key",
                model="cavadalabs/qwen3-32b",
                custom_llm_provider="cavadalabs",
                team_id="team-project-1",
            )
        ]
    )
    db.cavadalabs_requestledgertable.create_many = AsyncMock(
        return_value=SimpleNamespace(count=1)
    )
    db.cavadalabs_requestledgertable.count = AsyncMock(return_value=0)

    repair = await repair_cavadalabs_usage_scope(
        prisma_client=SimpleNamespace(db=db),
        entity_type="company",
        entity_id=["company-1"],
        start_date="2026-05-01",
        end_date="2026-05-31",
        timezone_offset_minutes=0,
        model="cavadalabs/qwen3-32b",
        provider="cavadalabs",
        api_key="hashed-key",
        dry_run=False,
        batch_limit=1,
    )

    assert repair.dry_run is False
    assert repair.repaired is True
    assert repair.scoped_spend_logs == 2
    assert repair.processed_spend_logs == 1
    assert repair.batch_limit == 1
    assert "batch limit" in repair.message
    find_kwargs = _find_spend_logs_find_many_call(
        db,
        {"custom_llm_provider": "cavadalabs"},
        take=1,
    )
    provider_condition = _find_and_or_condition(
        find_kwargs["where"], {"custom_llm_provider": "cavadalabs"}
    )
    assert {
        "metadata": {
            "path": ["spend_logs_metadata", "cavadalabs_provider"],
            "equals": "cavadalabs",
        }
    } in provider_condition["OR"]
    ledger_row = db.cavadalabs_requestledgertable.create_many.call_args.kwargs["data"][
        0
    ]
    assert ledger_row["company_id"] == "company-1"
    assert ledger_row["project_id"] == "project-1"

    db.cavadalabs_requestledgertable.count = AsyncMock(return_value=1)
    db.cavadalabs_requestledgertable.find_many = AsyncMock(
        return_value=[
            _ledger(
                request_id="req-company-backfill",
                provider="cavadalabs",
                model="cavadalabs/qwen3-32b",
            )
        ]
    )
    _patch_prisma(monkeypatch, db)

    activity = await company_endpoints.get_company_daily_activity(
        http_request=MagicMock(),
        start_date="2026-05-15",
        end_date="2026-05-15",
        model="cavadalabs/qwen3-32b",
        provider="cavadalabs",
        status_filter=None,
        api_key="hashed-key",
        min_spend=None,
        max_spend=None,
        company_ids="company-1",
        page=1,
        page_size=100,
        timezone=0,
        user_api_key_dict=_admin_auth(),
    )

    assert activity.metadata.total_api_requests == 1
    assert activity.metadata.total_spend == pytest.approx(0.15)


@pytest.mark.asyncio
async def test_project_usage_diagnostics_repair_then_daily_activity_reads_ledger(
    monkeypatch,
):
    db = _db()
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[_company()])
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[_project()])
    db.cavadalabs_requestledgertable.count = AsyncMock(return_value=0)
    db.litellm_spendlogs.count = AsyncMock(return_value=1)

    diagnostics = await get_cavadalabs_usage_diagnostics(
        prisma_client=SimpleNamespace(db=db),
        entity_type="project",
        entity_id=["project-1"],
        start_date="2026-05-01",
        end_date="2026-05-31",
        timezone_offset_minutes=0,
        model=None,
        provider=None,
        api_key=None,
    )

    item = diagnostics.diagnostics[0]
    assert item.status == CavadaLabsUsageDiagnosticsStatus.SCOPED_BACKFILL_AVAILABLE
    assert (
        item.recommended_action == CavadaLabsUsageDiagnosticsAction.RUN_SCOPED_BACKFILL
    )
    assert item.scoped_backfill_available is True
    assert item.ledger_gap == 1
    assert item.attributable_spend_logs == 1

    db.litellm_spendlogs.find_many = AsyncMock(
        return_value=[
            _spend_log(
                request_id="req-project-backfill",
                api_key="hashed-key",
                model="cavadalabs/qwen3-32b",
                custom_llm_provider="cavadalabs",
                team_id="team-project-1",
            )
        ]
    )
    db.cavadalabs_requestledgertable.create_many = AsyncMock(
        return_value=SimpleNamespace(count=1)
    )
    db.cavadalabs_requestledgertable.count = AsyncMock(return_value=1)

    repair = await repair_cavadalabs_usage_scope(
        prisma_client=SimpleNamespace(db=db),
        entity_type="project",
        entity_id=["project-1"],
        start_date="2026-05-01",
        end_date="2026-05-31",
        timezone_offset_minutes=0,
        model=None,
        provider=None,
        api_key=None,
        dry_run=False,
        batch_limit=None,
    )

    assert repair.attempted is True
    assert repair.repaired is True
    assert repair.scoped_spend_logs == 1
    assert repair.processed_spend_logs == 1
    assert repair.diagnostics[0].status == CavadaLabsUsageDiagnosticsStatus.VISIBLE
    ledger_row = db.cavadalabs_requestledgertable.create_many.call_args.kwargs["data"][
        0
    ]
    assert ledger_row["request_id"] == "req-project-backfill"
    assert ledger_row["company_id"] == "company-1"
    assert ledger_row["project_id"] == "project-1"

    db.cavadalabs_requestledgertable.find_many = AsyncMock(
        return_value=[
            _ledger(
                request_id="req-project-backfill",
                company_id="company-1",
                project_id="project-1",
                provider="cavadalabs",
                model="cavadalabs/qwen3-32b",
            )
        ]
    )
    _patch_prisma(monkeypatch, db)

    activity = await project_endpoints.get_project_daily_activity(
        http_request=MagicMock(),
        start_date="2026-05-15",
        end_date="2026-05-15",
        model=None,
        provider=None,
        status_filter=None,
        api_key=None,
        min_spend=None,
        max_spend=None,
        project_ids="project-1",
        page=1,
        page_size=100,
        timezone=0,
        user_api_key_dict=_admin_auth(),
    )

    assert activity.metadata.total_api_requests == 1
    assert activity.metadata.total_spend == pytest.approx(0.15)
    assert activity.results[0].breakdown.entities["project-1"].metrics.spend == 0.15


@pytest.mark.asyncio
async def test_usage_repair_backfills_chatbot_id_from_virtual_key_metadata():
    db = _db()
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[_company()])
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[_project()])
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
    db.litellm_spendlogs.count = AsyncMock(return_value=1)
    db.litellm_spendlogs.find_many = AsyncMock(
        return_value=[
            _spend_log(
                request_id="req-chatbot-key-backfill",
                api_key="hashed-key",
                metadata={},
            )
        ]
    )
    db.cavadalabs_requestledgertable.create_many = AsyncMock(
        return_value=SimpleNamespace(count=1)
    )

    repair = await repair_cavadalabs_usage_scope(
        prisma_client=SimpleNamespace(db=db),
        entity_type="company",
        entity_id=["company-1"],
        start_date="2026-05-01",
        end_date="2026-05-31",
        timezone_offset_minutes=0,
        model=None,
        provider=None,
        api_key=None,
        dry_run=False,
        batch_limit=None,
    )

    assert repair.repaired is True
    ledger_row = db.cavadalabs_requestledgertable.create_many.call_args.kwargs["data"][
        0
    ]
    assert ledger_row["company_id"] == "company-1"
    assert ledger_row["project_id"] == "project-1"
    assert ledger_row["chatbot_id"] == "chatbot-1"


@pytest.mark.asyncio
async def test_usage_repair_backfills_spend_log_matching_key_hash_in_metadata_only():
    db = _db()
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[_company()])
    db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[_project(litellm_team_id=None)]
    )
    db.litellm_verificationtoken.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                token="hashed-key",
                team_id=None,
                organization_id=None,
                metadata={
                    "cavadalabs_company_id": "company-1",
                    "cavadalabs_project_id": "project-1",
                    "cavadalabs_chatbot_id": "chatbot-1",
                },
            )
        ]
    )
    db.litellm_spendlogs.count = AsyncMock(return_value=1)
    db.litellm_spendlogs.find_many = AsyncMock(
        return_value=[
            _spend_log(
                request_id="req-metadata-key-hash-backfill",
                api_key=None,
                team_id=None,
                organization_id=None,
                metadata={
                    "spend_logs_metadata": {
                        "user_api_key_hash": "hashed-key",
                    }
                },
            )
        ]
    )
    db.cavadalabs_requestledgertable.create_many = AsyncMock(
        return_value=SimpleNamespace(count=1)
    )

    repair = await repair_cavadalabs_usage_scope(
        prisma_client=SimpleNamespace(db=db),
        entity_type="company",
        entity_id=["company-1"],
        start_date="2026-05-01",
        end_date="2026-05-31",
        timezone_offset_minutes=0,
        model=None,
        provider=None,
        api_key=None,
        dry_run=False,
        batch_limit=None,
    )

    assert repair.repaired is True
    find_kwargs = _find_spend_logs_find_many_call(
        db,
        {"api_key": {"in": ["hashed-key"]}},
    )
    spend_where = find_kwargs["where"]
    key_hash_condition = _find_and_or_condition(
        spend_where,
        {"api_key": {"in": ["hashed-key"]}},
    )
    assert {
        "metadata": {
            "path": ["spend_logs_metadata", "user_api_key_hash"],
            "equals": json.dumps("hashed-key"),
        }
    } in key_hash_condition["OR"]
    ledger_row = db.cavadalabs_requestledgertable.create_many.call_args.kwargs["data"][
        0
    ]
    assert ledger_row["request_id"] == "req-metadata-key-hash-backfill"
    assert ledger_row["company_id"] == "company-1"
    assert ledger_row["project_id"] == "project-1"
    assert ledger_row["chatbot_id"] == "chatbot-1"
    assert ledger_row["api_key_hash"] == "hashed-key"
    metadata = getattr(ledger_row["metadata"], "data", {})
    assert metadata["cavadalabs"]["attribution_source"] == "key_metadata"


@pytest.mark.asyncio
async def test_usage_repair_updates_existing_ledger_row_for_authoritative_company_project():
    db = _db()
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[_company()])
    db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[_project(litellm_team_id=None)]
    )
    db.litellm_verificationtoken.find_many = AsyncMock(
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
    db.litellm_spendlogs.count = AsyncMock(return_value=1)
    db.litellm_spendlogs.find_many = AsyncMock(
        return_value=[
            _spend_log(
                request_id="req-existing-ledger-wrong-scope",
                api_key=None,
                team_id=None,
                organization_id=None,
                metadata={
                    "spend_logs_metadata": {
                        "api_key_hash": "hashed-key",
                    }
                },
            )
        ]
    )
    db.cavadalabs_requestledgertable.create_many = AsyncMock(
        return_value=SimpleNamespace(count=0)
    )
    db.cavadalabs_requestledgertable.update_many = AsyncMock(
        return_value=SimpleNamespace(count=1)
    )

    repair = await repair_cavadalabs_usage_scope(
        prisma_client=SimpleNamespace(db=db),
        entity_type="project",
        entity_id=["project-1"],
        start_date="2026-05-01",
        end_date="2026-05-31",
        timezone_offset_minutes=0,
        model=None,
        provider=None,
        api_key=None,
        dry_run=False,
        batch_limit=None,
    )

    assert repair.repaired is True
    assert repair.processed_spend_logs == 1
    update_call = db.cavadalabs_requestledgertable.update_many.call_args.kwargs
    assert update_call["where"] == {
        "request_id": "req-existing-ledger-wrong-scope",
        "OR": [
            {"company_id": {"not": "company-1"}},
            {"project_id": {"not": "project-1"}},
        ],
    }
    assert update_call["data"]["company_id"] == "company-1"
    assert update_call["data"]["project_id"] == "project-1"
    assert "request_id" not in update_call["data"]


@pytest.mark.asyncio
async def test_company_daily_activity_endpoint_allows_native_company_viewer(
    monkeypatch,
):
    db = _db()
    db.cavadalabs_companytable.find_unique = AsyncMock(return_value=_company())
    db.cavadalabs_companymembertable = MagicMock()
    db.cavadalabs_companymembertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            company_id="company-1",
            user_id="user-1",
            role="viewer",
        )
    )
    _patch_prisma(monkeypatch, db)
    daily_activity = AsyncMock(return_value=SimpleNamespace(results=[], metadata=None))
    monkeypatch.setattr(
        company_endpoints,
        "get_cavadalabs_daily_activity",
        daily_activity,
    )

    response = await company_endpoints.get_company_daily_activity(
        http_request=MagicMock(),
        start_date="2026-05-01",
        end_date="2026-05-31",
        model=None,
        provider=None,
        status_filter=None,
        api_key=None,
        min_spend=None,
        max_spend=None,
        company_ids="company-1",
        page=1,
        page_size=100,
        timezone=0,
        user_api_key_dict=_auth(),
    )

    assert response.results == []
    daily_activity.assert_awaited_once()
    assert daily_activity.call_args.kwargs["entity_id_field"] == "company_id"
    assert daily_activity.call_args.kwargs["entity_id"] == ["company-1"]
    db.litellm_organizationmembership.find_unique.assert_not_awaited()


@pytest.mark.asyncio
async def test_company_daily_activity_endpoint_rejects_project_only_member_scope(
    monkeypatch,
):
    db = _db()
    db.cavadalabs_companytable.find_unique = AsyncMock(return_value=_company())
    db.cavadalabs_companymembertable = MagicMock()
    db.cavadalabs_companymembertable.find_unique = AsyncMock(return_value=None)
    db.cavadalabs_projectmembertable = MagicMock()
    db.cavadalabs_projectmembertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            project_id="project-1",
            user_id="user-1",
            role="viewer",
        )
    )
    _patch_prisma(monkeypatch, db)
    daily_activity = AsyncMock(return_value=SimpleNamespace(results=[], metadata=None))
    monkeypatch.setattr(
        company_endpoints,
        "get_cavadalabs_daily_activity",
        daily_activity,
    )

    with pytest.raises(HTTPException) as exc_info:
        await company_endpoints.get_company_daily_activity(
            http_request=MagicMock(),
            start_date="2026-05-01",
            end_date="2026-05-31",
            model=None,
            provider=None,
            status_filter=None,
            api_key=None,
            min_spend=None,
            max_spend=None,
            company_ids="company-1",
            page=1,
            page_size=100,
            timezone=0,
            user_api_key_dict=_auth(),
        )

    assert exc_info.value.status_code == 403
    daily_activity.assert_not_awaited()


@pytest.mark.asyncio
async def test_project_daily_activity_endpoint_allows_native_project_viewer(
    monkeypatch,
):
    db = _db()
    db.cavadalabs_projecttable.find_unique = AsyncMock(return_value=_project())
    db.cavadalabs_projectmembertable = MagicMock()
    db.cavadalabs_projectmembertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            project_id="project-1",
            user_id="user-1",
            role="viewer",
        )
    )
    _patch_prisma(monkeypatch, db)
    daily_activity = AsyncMock(return_value=SimpleNamespace(results=[], metadata=None))
    monkeypatch.setattr(
        project_endpoints,
        "get_cavadalabs_daily_activity",
        daily_activity,
    )

    response = await project_endpoints.get_project_daily_activity(
        http_request=MagicMock(),
        start_date="2026-05-01",
        end_date="2026-05-31",
        model=None,
        provider=None,
        status_filter=None,
        api_key=None,
        min_spend=None,
        max_spend=None,
        project_ids="project-1",
        page=1,
        page_size=100,
        timezone=0,
        user_api_key_dict=_auth(),
    )

    assert response.results == []
    daily_activity.assert_awaited_once()
    assert daily_activity.call_args.kwargs["entity_id_field"] == "project_id"
    assert daily_activity.call_args.kwargs["entity_id"] == ["project-1"]
    db.litellm_teamtable.find_unique.assert_not_awaited()


@pytest.mark.asyncio
async def test_project_daily_activity_endpoint_rejects_cross_scope_project(
    monkeypatch,
):
    db = _db()
    db.cavadalabs_projecttable.find_unique = AsyncMock(
        return_value=_project(
            project_id="project-2",
            company_id="company-2",
            litellm_team_id="team-project-2",
        )
    )
    db.cavadalabs_companytable.find_unique = AsyncMock(
        return_value=_company(
            company_id="company-2",
            litellm_organization_id="org-company-2",
        )
    )
    db.cavadalabs_projectmembertable = MagicMock()
    db.cavadalabs_projectmembertable.find_unique = AsyncMock(return_value=None)
    db.cavadalabs_companymembertable = MagicMock()
    db.cavadalabs_companymembertable.find_unique = AsyncMock(return_value=None)
    db.litellm_teamtable.find_unique = AsyncMock(return_value=None)
    _patch_prisma(monkeypatch, db)
    daily_activity = AsyncMock()
    monkeypatch.setattr(
        project_endpoints,
        "get_cavadalabs_daily_activity",
        daily_activity,
    )

    with pytest.raises(HTTPException) as exc_info:
        await project_endpoints.get_project_daily_activity(
            http_request=MagicMock(),
            start_date="2026-05-01",
            end_date="2026-05-31",
            model=None,
            provider=None,
            status_filter=None,
            api_key=None,
            min_spend=None,
            max_spend=None,
            project_ids="project-2",
            page=1,
            page_size=100,
            timezone=0,
            user_api_key_dict=_auth(),
        )

    assert exc_info.value.status_code == 403
    daily_activity.assert_not_awaited()


@pytest.mark.asyncio
async def test_project_usage_diagnostics_endpoint_reports_valid_scope_missing_mapping(
    monkeypatch,
):
    db = _db()
    db.cavadalabs_projecttable.find_unique = AsyncMock(
        return_value=_project(litellm_team_id=None)
    )
    db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[_project(litellm_team_id=None)]
    )
    db.cavadalabs_projectmembertable = MagicMock()
    db.cavadalabs_projectmembertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            project_id="project-1",
            user_id="user-1",
            role="viewer",
        )
    )
    db.cavadalabs_companymembertable = MagicMock()
    db.cavadalabs_companymembertable.find_unique = AsyncMock(return_value=None)
    _patch_prisma(monkeypatch, db)

    response = await project_endpoints.get_project_usage_diagnostics(
        http_request=MagicMock(),
        start_date="2026-05-01",
        end_date="2026-05-31",
        project_ids="project-1",
        model=None,
        provider=None,
        api_key=None,
        timezone=0,
        user_api_key_dict=_auth(),
    )

    item = response.diagnostics[0]
    assert item.entity_type == "project"
    assert item.entity_id == "project-1"
    assert item.status == CavadaLabsUsageDiagnosticsStatus.MISSING_COMPATIBILITY_MAPPING
    assert (
        item.recommended_action
        == CavadaLabsUsageDiagnosticsAction.FIX_COMPATIBILITY_MAPPING
    )
    assert item.ledger_rows == 0
    assert item.attributable_spend_logs == 0
    assert item.scoped_backfill_available is False
    assert item.missing_mappings == [
        "project litellm_team_id or CavadaLabs key metadata"
    ]
    db.litellm_spendlogs.find_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_company_usage_diagnostics_endpoint_allows_native_company_viewer(
    monkeypatch,
):
    db = _db()
    _set_native_company_membership(db, "viewer")
    _patch_prisma(monkeypatch, db)
    diagnostics = AsyncMock(return_value=SimpleNamespace(diagnostics=[]))
    monkeypatch.setattr(
        company_endpoints,
        "get_cavadalabs_usage_diagnostics",
        diagnostics,
    )

    response = await company_endpoints.get_company_usage_diagnostics(
        http_request=MagicMock(),
        start_date="2026-05-01",
        end_date="2026-05-31",
        company_ids="company-1",
        model=None,
        provider=None,
        api_key=None,
        timezone=0,
        user_api_key_dict=_auth(),
    )

    assert response.diagnostics == []
    diagnostics.assert_awaited_once()
    assert diagnostics.call_args.kwargs["entity_type"] == "company"
    assert diagnostics.call_args.kwargs["entity_id"] == ["company-1"]
    db.litellm_organizationmembership.find_unique.assert_not_awaited()


@pytest.mark.asyncio
async def test_company_repair_endpoint_allows_company_admin(monkeypatch):
    db = _db()
    db.litellm_organizationmembership.find_many = AsyncMock(
        return_value=[_membership(LitellmUserRoles.ORG_ADMIN)]
    )
    db.litellm_organizationmembership.find_unique = AsyncMock(
        return_value=_membership(LitellmUserRoles.ORG_ADMIN)
    )
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[_company()])
    _patch_prisma(monkeypatch, db)
    repair = AsyncMock(return_value=_repair_response("company", ["company-1"]))
    monkeypatch.setattr(company_endpoints, "repair_cavadalabs_usage_scope", repair)

    response = await company_endpoints.repair_company_usage(
        data=_request(
            company_ids=["company-1"],
            model="cavadalabs/qwen3-32b",
            provider="cavadalabs",
            status="success",
            api_key="hashed-key",
            min_spend=0.1,
            max_spend=1.0,
            dry_run=True,
            batch_limit=25,
        ),
        http_request=MagicMock(),
        user_api_key_dict=_auth(),
    )

    assert response.repaired is True
    repair.assert_awaited_once()
    assert repair.call_args.kwargs["entity_type"] == "company"
    assert repair.call_args.kwargs["entity_id"] == ["company-1"]
    assert repair.call_args.kwargs["model"] == "cavadalabs/qwen3-32b"
    assert repair.call_args.kwargs["provider"] == "cavadalabs"
    assert repair.call_args.kwargs["status_filter"] == "success"
    assert repair.call_args.kwargs["api_key"] == "hashed-key"
    assert repair.call_args.kwargs["min_spend"] == 0.1
    assert repair.call_args.kwargs["max_spend"] == 1.0
    assert repair.call_args.kwargs["dry_run"] is True
    assert repair.call_args.kwargs["batch_limit"] == 25


@pytest.mark.asyncio
async def test_company_repair_endpoint_allows_native_company_admin(monkeypatch):
    db = _db()
    _set_native_company_membership(db, "company_admin")
    _patch_prisma(monkeypatch, db)
    repair = AsyncMock(return_value=_repair_response("company", ["company-1"]))
    monkeypatch.setattr(company_endpoints, "repair_cavadalabs_usage_scope", repair)

    response = await company_endpoints.repair_company_usage(
        data=_request(company_ids=["company-1"]),
        http_request=MagicMock(),
        user_api_key_dict=_auth(),
    )

    assert response.repaired is True
    repair.assert_awaited_once()
    assert repair.call_args.kwargs["entity_type"] == "company"
    assert repair.call_args.kwargs["entity_id"] == ["company-1"]
    db.litellm_organizationmembership.find_unique.assert_not_awaited()


@pytest.mark.asyncio
async def test_company_repair_endpoint_rejects_company_viewer(monkeypatch):
    db = _db()
    db.litellm_organizationmembership.find_many = AsyncMock(
        return_value=[_membership(LitellmUserRoles.INTERNAL_USER_VIEW_ONLY)]
    )
    db.litellm_organizationmembership.find_unique = AsyncMock(
        return_value=_membership(LitellmUserRoles.INTERNAL_USER_VIEW_ONLY)
    )
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[_company()])
    _patch_prisma(monkeypatch, db)
    repair = AsyncMock()
    monkeypatch.setattr(company_endpoints, "repair_cavadalabs_usage_scope", repair)

    with pytest.raises(HTTPException) as exc_info:
        await company_endpoints.repair_company_usage(
            data=_request(company_ids=["company-1"]),
            http_request=MagicMock(),
            user_api_key_dict=_auth(),
        )

    assert exc_info.value.status_code == 403
    repair.assert_not_awaited()


@pytest.mark.asyncio
async def test_company_repair_endpoint_rejects_native_company_viewer(monkeypatch):
    db = _db()
    _set_native_company_membership(db, "viewer")
    _patch_prisma(monkeypatch, db)
    repair = AsyncMock()
    monkeypatch.setattr(company_endpoints, "repair_cavadalabs_usage_scope", repair)

    with pytest.raises(HTTPException) as exc_info:
        await company_endpoints.repair_company_usage(
            data=_request(company_ids=["company-1"]),
            http_request=MagicMock(),
            user_api_key_dict=_auth(),
        )

    assert exc_info.value.status_code == 403
    repair.assert_not_awaited()


@pytest.mark.asyncio
async def test_company_repair_endpoint_rejects_native_project_admin_scope(
    monkeypatch,
):
    db = _db()
    _set_native_company_membership(db, None)
    _set_native_project_membership(db, "project_admin")
    _patch_prisma(monkeypatch, db)
    repair = AsyncMock()
    monkeypatch.setattr(company_endpoints, "repair_cavadalabs_usage_scope", repair)

    with pytest.raises(HTTPException) as exc_info:
        await company_endpoints.repair_company_usage(
            data=_request(company_ids=["company-1"]),
            http_request=MagicMock(),
            user_api_key_dict=_auth(),
        )

    assert exc_info.value.status_code == 403
    repair.assert_not_awaited()


@pytest.mark.asyncio
async def test_company_repair_endpoint_rejects_inaccessible_scope(monkeypatch):
    db = _db()
    _patch_prisma(monkeypatch, db)
    repair = AsyncMock()
    monkeypatch.setattr(company_endpoints, "repair_cavadalabs_usage_scope", repair)

    with pytest.raises(HTTPException) as exc_info:
        await company_endpoints.repair_company_usage(
            data=_request(company_ids=["company-2"]),
            http_request=MagicMock(),
            user_api_key_dict=_auth(),
        )

    assert exc_info.value.status_code == 403
    repair.assert_not_awaited()


@pytest.mark.asyncio
async def test_project_repair_endpoint_allows_project_admin(monkeypatch):
    db = _db()
    db.litellm_usertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(user_id="user-1", teams=["team-project-1"])
    )
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[_project()])
    db.litellm_teamtable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            team_id="team-project-1",
            members_with_roles=[{"user_id": "user-1", "role": "admin"}],
        )
    )
    _patch_prisma(monkeypatch, db)
    repair = AsyncMock(return_value=_repair_response("project", ["project-1"]))
    monkeypatch.setattr(project_endpoints, "repair_cavadalabs_usage_scope", repair)

    response = await project_endpoints.repair_project_usage(
        data=_request(project_ids=["project-1"]),
        http_request=MagicMock(),
        user_api_key_dict=_auth(),
    )

    assert response.repaired is True
    repair.assert_awaited_once()
    assert repair.call_args.kwargs["entity_type"] == "project"
    assert repair.call_args.kwargs["entity_id"] == ["project-1"]


@pytest.mark.asyncio
async def test_project_repair_endpoint_allows_native_project_admin(monkeypatch):
    db = _db()
    _set_native_project_membership(db, "project_admin")
    db.cavadalabs_companymembertable = MagicMock()
    db.cavadalabs_companymembertable.find_unique = AsyncMock(return_value=None)
    _patch_prisma(monkeypatch, db)
    repair = AsyncMock(return_value=_repair_response("project", ["project-1"]))
    monkeypatch.setattr(project_endpoints, "repair_cavadalabs_usage_scope", repair)

    response = await project_endpoints.repair_project_usage(
        data=_request(project_ids=["project-1"]),
        http_request=MagicMock(),
        user_api_key_dict=_auth(),
    )

    assert response.repaired is True
    repair.assert_awaited_once()
    assert repair.call_args.kwargs["entity_type"] == "project"
    assert repair.call_args.kwargs["entity_id"] == ["project-1"]
    db.litellm_teamtable.find_unique.assert_not_awaited()


@pytest.mark.asyncio
async def test_project_repair_endpoint_rejects_project_operator(monkeypatch):
    db = _db()
    db.litellm_usertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(user_id="user-1", teams=["team-project-1"])
    )
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[_project()])
    db.litellm_teamtable.find_unique = AsyncMock(
        return_value=SimpleNamespace(
            team_id="team-project-1",
            members_with_roles=[{"user_id": "user-1", "role": "user"}],
        )
    )
    _patch_prisma(monkeypatch, db)
    repair = AsyncMock()
    monkeypatch.setattr(project_endpoints, "repair_cavadalabs_usage_scope", repair)

    with pytest.raises(HTTPException) as exc_info:
        await project_endpoints.repair_project_usage(
            data=_request(project_ids=["project-1"]),
            http_request=MagicMock(),
            user_api_key_dict=_auth(),
        )

    assert exc_info.value.status_code == 403
    repair.assert_not_awaited()


@pytest.mark.asyncio
async def test_project_repair_endpoint_rejects_native_project_viewer(monkeypatch):
    db = _db()
    _set_native_project_membership(db, "viewer")
    db.cavadalabs_companymembertable = MagicMock()
    db.cavadalabs_companymembertable.find_unique = AsyncMock(return_value=None)
    _patch_prisma(monkeypatch, db)
    repair = AsyncMock()
    monkeypatch.setattr(project_endpoints, "repair_cavadalabs_usage_scope", repair)

    with pytest.raises(HTTPException) as exc_info:
        await project_endpoints.repair_project_usage(
            data=_request(project_ids=["project-1"]),
            http_request=MagicMock(),
            user_api_key_dict=_auth(),
        )

    assert exc_info.value.status_code == 403
    repair.assert_not_awaited()


@pytest.mark.asyncio
async def test_project_repair_endpoint_rejects_inaccessible_scope(monkeypatch):
    db = _db()
    _patch_prisma(monkeypatch, db)
    repair = AsyncMock()
    monkeypatch.setattr(project_endpoints, "repair_cavadalabs_usage_scope", repair)

    with pytest.raises(HTTPException) as exc_info:
        await project_endpoints.repair_project_usage(
            data=_request(project_ids=["project-2"]),
            http_request=MagicMock(),
            user_api_key_dict=_auth(),
        )

    assert exc_info.value.status_code == 403
    repair.assert_not_awaited()


@pytest.mark.asyncio
async def test_repair_endpoints_reject_global_scope(monkeypatch):
    db = _db()
    _patch_prisma(monkeypatch, db)
    company_repair = AsyncMock()
    project_repair = AsyncMock()
    monkeypatch.setattr(
        company_endpoints, "repair_cavadalabs_usage_scope", company_repair
    )
    monkeypatch.setattr(
        project_endpoints, "repair_cavadalabs_usage_scope", project_repair
    )

    with pytest.raises(HTTPException) as company_exc:
        await company_endpoints.repair_company_usage(
            data=_request(company_ids=[]),
            http_request=MagicMock(),
            user_api_key_dict=_auth(),
        )
    with pytest.raises(HTTPException) as project_exc:
        await project_endpoints.repair_project_usage(
            data=_request(project_ids=[]),
            http_request=MagicMock(),
            user_api_key_dict=_auth(),
        )

    assert company_exc.value.status_code == 400
    assert project_exc.value.status_code == 400
    company_repair.assert_not_awaited()
    project_repair.assert_not_awaited()


def test_usage_repair_request_requires_date_range():
    with pytest.raises(ValidationError):
        CavadaLabsUsageRepairRequest(
            company_ids=["company-1"],
            end_date="2026-05-31",
        )
    with pytest.raises(ValidationError):
        CavadaLabsUsageRepairRequest(
            company_ids=["company-1"],
            start_date="",
            end_date="2026-05-31",
        )


@pytest.mark.asyncio
async def test_company_usage_backfill_uses_active_key_metadata_when_deleted_key_delegate_missing():
    db = SimpleNamespace(
        cavadalabs_companytable=SimpleNamespace(
            find_many=AsyncMock(return_value=[_company()])
        ),
        cavadalabs_projecttable=SimpleNamespace(
            find_many=AsyncMock(return_value=[_project()])
        ),
        litellm_verificationtoken=SimpleNamespace(
            find_many=AsyncMock(
                return_value=[
                    SimpleNamespace(
                        token="active-key-hash",
                        metadata={
                            "cavadalabs_company_id": "company-1",
                            "cavadalabs_project_id": "project-1",
                        },
                        team_id=None,
                        organization_id=None,
                    )
                ]
            )
        ),
        litellm_spendlogs=SimpleNamespace(
            find_many=AsyncMock(
                return_value=[
                    _spend_log(
                        request_id="req-active-key-history",
                        api_key="active-key-hash",
                        metadata={},
                    )
                ]
            )
        ),
        cavadalabs_requestledgertable=SimpleNamespace(
            create_many=AsyncMock(return_value=SimpleNamespace(count=1))
        ),
    )

    result = await backfill_cavadalabs_usage_ledger_from_spend_logs(
        prisma_client=SimpleNamespace(db=db),
        entity_id_field="company_id",
        entity_id="company-1",
        date_range=_date_range(),
        model=None,
        provider=None,
        api_key=None,
    )

    assert result.repaired is True
    spend_where = db.litellm_spendlogs.find_many.call_args.kwargs["where"]
    assert {"api_key": {"in": ["active-key-hash"]}} in spend_where["AND"][0]["OR"]
    ledger_row = db.cavadalabs_requestledgertable.create_many.call_args.kwargs["data"][
        0
    ]
    assert ledger_row["request_id"] == "req-active-key-history"
    assert ledger_row["company_id"] == "company-1"
    assert ledger_row["project_id"] == "project-1"


@pytest.mark.asyncio
async def test_runtime_usage_attribution_keeps_team_mapping_when_deleted_key_delegate_missing():
    db = SimpleNamespace(
        litellm_verificationtoken=SimpleNamespace(find_many=AsyncMock(return_value=[])),
        cavadalabs_projecttable=SimpleNamespace(
            find_many=AsyncMock(return_value=[_project()])
        ),
        cavadalabs_companytable=SimpleNamespace(find_many=AsyncMock(return_value=[])),
        cavadalabs_requestledgertable=SimpleNamespace(
            create_many=AsyncMock(return_value=SimpleNamespace(count=1))
        ),
    )

    created = await process_spend_logs_cavadalabs_ledger(
        prisma_client=SimpleNamespace(db=db),
        logs_to_process=[
            {
                "request_id": "req-team-mapped-runtime",
                "api_key": "unknown-key-hash",
                "team_id": "team-project-1",
                "metadata": {},
                "spend": 0.22,
                "total_tokens": 22,
                "prompt_tokens": 12,
                "completion_tokens": 10,
                "startTime": datetime(2026, 5, 15, 12, tzinfo=timezone.utc),
                "model": "openai/gpt-4.1",
                "custom_llm_provider": "openai",
                "status": "success",
            }
        ],
    )

    assert created == 1
    ledger_row = db.cavadalabs_requestledgertable.create_many.call_args.kwargs["data"][
        0
    ]
    assert ledger_row["request_id"] == "req-team-mapped-runtime"
    assert ledger_row["company_id"] == "company-1"
    assert ledger_row["project_id"] == "project-1"


@pytest.mark.asyncio
async def test_runtime_key_metadata_writes_ledger_visible_to_company_daily_activity():
    db = _db()
    db.litellm_verificationtoken.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                token="hashed-key",
                metadata={
                    "cavadalabs_company_id": "company-1",
                    "cavadalabs_project_id": "project-1",
                },
                team_id=None,
                organization_id=None,
                key_alias="Cavada live key",
            )
        ]
    )
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[_project()])
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[_company()])
    db.cavadalabs_requestledgertable.create_many = AsyncMock(
        return_value=SimpleNamespace(count=1)
    )

    created = await process_spend_logs_cavadalabs_ledger(
        prisma_client=SimpleNamespace(db=db),
        logs_to_process=[
            {
                "request_id": "req-live-key-metadata",
                "api_key": "hashed-key",
                "metadata": {},
                "spend": 0.27,
                "total_tokens": 27,
                "prompt_tokens": 17,
                "completion_tokens": 10,
                "startTime": datetime(2026, 5, 15, 12, tzinfo=timezone.utc),
                "model": "openai/gpt-4.1",
                "custom_llm_provider": "openai",
                "status": "success",
            }
        ],
    )

    assert created == 1
    ledger_row = db.cavadalabs_requestledgertable.create_many.call_args.kwargs["data"][
        0
    ]
    assert ledger_row["company_id"] == "company-1"
    assert ledger_row["project_id"] == "project-1"
    assert ledger_row["api_key_hash"] == "hashed-key"

    db.cavadalabs_requestledgertable.count = AsyncMock(return_value=1)
    db.cavadalabs_requestledgertable.find_many = AsyncMock(
        return_value=[SimpleNamespace(**ledger_row)]
    )

    response = await get_cavadalabs_daily_activity(
        prisma_client=SimpleNamespace(db=db),
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

    assert response.metadata.total_api_requests == 1
    assert response.metadata.total_spend == pytest.approx(0.27)
    assert response.metadata.total_tokens == 27
    assert response.results[0].breakdown.entities["company-1"].metrics.spend == 0.27
    db.litellm_spendlogs.find_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_runtime_attribution_skips_unresolved_explicit_project_metadata():
    db = _db()
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[])
    db.cavadalabs_requestledgertable.create_many = AsyncMock()

    created = await process_spend_logs_cavadalabs_ledger(
        prisma_client=SimpleNamespace(db=db),
        logs_to_process=[
            {
                "request_id": "req-unresolved-project",
                "api_key": "hashed-key",
                "metadata": {
                    "cavadalabs_company_id": "company-1",
                    "cavadalabs_project_id": "missing-project",
                },
                "spend": 0.27,
                "total_tokens": 27,
                "prompt_tokens": 17,
                "completion_tokens": 10,
                "startTime": datetime(2026, 5, 15, 12, tzinfo=timezone.utc),
                "model": "openai/gpt-4.1",
                "custom_llm_provider": "openai",
                "status": "success",
            }
        ],
    )

    assert created == 0
    db.cavadalabs_projecttable.find_many.assert_awaited_once_with(
        where={"project_id": {"in": ["missing-project"]}}
    )
    db.cavadalabs_requestledgertable.create_many.assert_not_awaited()
