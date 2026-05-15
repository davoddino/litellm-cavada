import base64
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.cavadalabs.billing import CavadaLabsBillingService
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsBillingReportGenerateRequest,
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


def _company_row(**kwargs):
    return _row(
        company_id=kwargs.pop("company_id", "company-1"),
        legal_name=kwargs.pop("legal_name", "ACME Spa"),
        billing_name=kwargs.pop("billing_name", "ACME Billing"),
        vat_tax_id=kwargs.pop("vat_tax_id", "IT123"),
        billing_address=kwargs.pop("billing_address", {"country": "IT"}),
        admin_emails=kwargs.pop("admin_emails", ["admin@acme.test"]),
        plan=kwargs.pop("plan", "production"),
        status=kwargs.pop("status", "active"),
        monthly_budget=kwargs.pop("monthly_budget", 500.0),
        metadata=kwargs.pop("metadata", {}),
        retention_policy=kwargs.pop("retention_policy", {}),
        default_guardrail_policy=kwargs.pop("default_guardrail_policy", None),
        default_billing_settings=kwargs.pop(
            "default_billing_settings", {"payment_terms": "30d"}
        ),
        **kwargs,
    )


def _ledger_row(**kwargs):
    return SimpleNamespace(
        ledger_id=kwargs.pop("ledger_id", "ledger-1"),
        request_id=kwargs.pop("request_id", "request-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        project_id=kwargs.pop("project_id", "project-1"),
        chatbot_id=kwargs.pop("chatbot_id", "chatbot-1"),
        web_token_id=kwargs.pop("web_token_id", "web-token-1"),
        session_id=kwargs.pop("session_id", "session-1"),
        api_key_hash=kwargs.pop("api_key_hash", None),
        provider=kwargs.pop("provider", "cavadalabs"),
        model=kwargs.pop("model", "cavadalabs/qwen3-32b"),
        node_id=kwargs.pop("node_id", "node-1"),
        gpu_id=kwargs.pop("gpu_id", "gpu-1"),
        loaded_model_id=kwargs.pop("loaded_model_id", "loaded-model-1"),
        model_load_request_id=kwargs.pop(
            "model_load_request_id", "model-load-request-1"
        ),
        prompt_tokens=kwargs.pop("prompt_tokens", 100),
        completion_tokens=kwargs.pop("completion_tokens", 50),
        total_tokens=kwargs.pop("total_tokens", 150),
        spend=kwargs.pop("spend", 0.15),
        status=kwargs.pop("status", "success"),
        metadata=kwargs.pop("metadata", {}),
        created_at=kwargs.pop(
            "created_at", datetime(2026, 5, 14, 12, tzinfo=timezone.utc)
        ),
        **kwargs,
    )


def _daily_report_row(**kwargs):
    return SimpleNamespace(
        report_id=kwargs.pop("report_id", "node-report-1"),
        node_id=kwargs.pop("node_id", "node-1"),
        report_date=kwargs.pop(
            "report_date", datetime(2026, 5, 14, tzinfo=timezone.utc)
        ),
        samples=kwargs.pop("samples", []),
        total_kwh=kwargs.pop("total_kwh", 10.0),
        total_model_runtime_seconds=kwargs.pop("total_model_runtime_seconds", 3600),
        total_loaded_model_seconds=kwargs.pop("total_loaded_model_seconds", 7200),
        total_requests=kwargs.pop("total_requests", 4),
        total_tokens=kwargs.pop("total_tokens", 600),
        node_cost_estimate=kwargs.pop("node_cost_estimate", 30.0),
        errors=kwargs.pop("errors", []),
        metadata=kwargs.pop("metadata", {}),
        created_at=kwargs.pop("created_at", datetime.now(timezone.utc)),
        updated_at=kwargs.pop("updated_at", datetime.now(timezone.utc)),
        **kwargs,
    )


def _billing_report_row(**kwargs):
    return SimpleNamespace(
        report_id=kwargs.pop("report_id", "billing-report-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        report_version=kwargs.pop("report_version", 1),
        period_start=kwargs.pop(
            "period_start", datetime(2026, 5, 1, tzinfo=timezone.utc)
        ),
        period_end=kwargs.pop("period_end", datetime(2026, 6, 1, tzinfo=timezone.utc)),
        currency=kwargs.pop("currency", "EUR"),
        status=kwargs.pop("status", "generated"),
        formats=kwargs.pop("formats", ["json", "csv", "xlsx", "pdf"]),
        total_requests=kwargs.pop("total_requests", 0),
        total_tokens=kwargs.pop("total_tokens", 0),
        total_spend=kwargs.pop("total_spend", 0.0),
        provider_cost=kwargs.pop("provider_cost", 0.0),
        cavadalabs_node_cost=kwargs.pop("cavadalabs_node_cost", 0.0),
        tax_rate=kwargs.pop("tax_rate", None),
        tax_amount=kwargs.pop("tax_amount", None),
        grand_total=kwargs.pop("grand_total", 0.0),
        checksum=kwargs.pop("checksum", "checksum"),
        inputs_snapshot=kwargs.pop("inputs_snapshot", {}),
        totals=kwargs.pop("totals", {}),
        breakdowns=kwargs.pop("breakdowns", {}),
        artifacts=kwargs.pop("artifacts", {}),
        metadata=kwargs.pop("metadata", {}),
        generated_at=kwargs.pop("generated_at", datetime.now(timezone.utc)),
        generated_by=kwargs.pop("generated_by", "admin-user"),
        created_at=kwargs.pop("created_at", datetime.now(timezone.utc)),
        updated_at=kwargs.pop("updated_at", datetime.now(timezone.utc)),
        **kwargs,
    )


def _service():
    prisma_client = MagicMock()
    prisma_client.db = MagicMock()
    prisma_client.db.cavadalabs_companytable = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable = MagicMock()
    prisma_client.db.cavadalabs_nodedailyreporttable = MagicMock()
    prisma_client.db.cavadalabs_billingreporttable = MagicMock()
    prisma_client.db.cavadalabs_auditlogtable = MagicMock()
    prisma_client.db.cavadalabs_auditlogtable.create = AsyncMock()
    return CavadaLabsBillingService(prisma_client), prisma_client


@pytest.mark.asyncio
async def test_should_generate_monthly_billing_report_with_artifacts_and_checksum():
    service, prisma_client = _service()
    company_rows = [
        _ledger_row(ledger_id="ledger-1", request_id="request-1", total_tokens=150),
        _ledger_row(
            ledger_id="ledger-2",
            request_id="request-2",
            model="openai/gpt-4.1",
            provider="openai",
            total_tokens=150,
        ),
    ]
    all_node_rows = [
        *company_rows,
        _ledger_row(
            ledger_id="ledger-other",
            request_id="request-other",
            company_id="company-2",
            total_tokens=300,
        ),
    ]
    prisma_client.db.cavadalabs_companytable.find_unique = AsyncMock(
        return_value=_company_row()
    )
    prisma_client.db.cavadalabs_requestledgertable.find_many = AsyncMock(
        side_effect=[company_rows, all_node_rows]
    )
    prisma_client.db.cavadalabs_nodedailyreporttable.find_many = AsyncMock(
        return_value=[_daily_report_row(node_cost_estimate=30.0)]
    )
    prisma_client.db.cavadalabs_billingreporttable.find_many = AsyncMock(
        return_value=[]
    )
    prisma_client.db.cavadalabs_billingreporttable.find_unique = AsyncMock(
        return_value=None
    )

    async def _create_report(*args, **kwargs):
        return _billing_report_row(**kwargs["data"])

    prisma_client.db.cavadalabs_billingreporttable.create = AsyncMock(
        side_effect=_create_report
    )

    response = await service.generate_monthly_report(
        CavadaLabsBillingReportGenerateRequest(
            company_id="company-1",
            year=2026,
            month=5,
            tax_rate=0.2,
        ),
        _admin(),
    )

    assert response.total_requests == 2
    assert response.total_tokens == 300
    assert response.provider_cost == pytest.approx(0.3)
    assert response.cavadalabs_node_cost == pytest.approx(15.0)
    assert response.tax_amount == pytest.approx(3.06)
    assert response.grand_total == pytest.approx(18.36)
    assert response.checksum
    assert response.inputs_snapshot["source_request_ids"] == ["request-1", "request-2"]
    assert response.breakdowns["node_cost_allocations"][0]["share"] == pytest.approx(
        0.5
    )
    assert "json" in response.artifacts
    assert "section,id,requests,tokens,spend,extra" in response.artifacts["csv"]
    assert base64.b64decode(response.artifacts["xlsx_base64"]).startswith(b"PK")
    assert base64.b64decode(response.artifacts["pdf_base64"]).startswith(b"%PDF")
    prisma_client.db.cavadalabs_auditlogtable.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_should_return_existing_report_when_checksum_matches():
    service, prisma_client = _service()
    existing_report = _billing_report_row(checksum="existing-checksum")
    prisma_client.db.cavadalabs_companytable.find_unique = AsyncMock(
        return_value=_company_row()
    )
    prisma_client.db.cavadalabs_requestledgertable.find_many = AsyncMock(
        side_effect=[[], []]
    )
    prisma_client.db.cavadalabs_nodedailyreporttable.find_many = AsyncMock(
        return_value=[]
    )
    prisma_client.db.cavadalabs_billingreporttable.find_many = AsyncMock(
        return_value=[]
    )
    prisma_client.db.cavadalabs_billingreporttable.find_unique = AsyncMock(
        return_value=existing_report
    )
    prisma_client.db.cavadalabs_billingreporttable.create = AsyncMock()

    response = await service.generate_monthly_report(
        CavadaLabsBillingReportGenerateRequest(
            company_id="company-1",
            year=2026,
            month=5,
            formats=["json"],
        ),
        _admin(),
    )

    assert response.report_id == "billing-report-1"
    prisma_client.db.cavadalabs_billingreporttable.create.assert_not_called()


@pytest.mark.asyncio
async def test_should_list_and_get_billing_reports():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_billingreporttable.find_many = AsyncMock(
        return_value=[_billing_report_row()]
    )
    prisma_client.db.cavadalabs_billingreporttable.find_unique = AsyncMock(
        return_value=_billing_report_row()
    )

    listed = await service.list_billing_reports(
        company_id="company-1",
        year=2026,
        month=5,
    )
    fetched = await service.get_billing_report("billing-report-1")

    assert listed.count == 1
    assert fetched.report_id == "billing-report-1"
    where = prisma_client.db.cavadalabs_billingreporttable.find_many.call_args.kwargs[
        "where"
    ]
    assert where["company_id"] == "company-1"
    assert where["period_start"] == datetime(2026, 5, 1, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_should_list_billing_reports_for_authorized_company_scope():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_billingreporttable.find_many = AsyncMock(
        return_value=[
            _billing_report_row(report_id="billing-report-1", company_id="company-1")
        ]
    )

    listed = await service.list_billing_reports(company_ids=["company-1"])

    assert listed.count == 1
    where = prisma_client.db.cavadalabs_billingreporttable.find_many.call_args.kwargs[
        "where"
    ]
    assert where["company_id"] == {"in": ["company-1"]}


@pytest.mark.asyncio
async def test_should_return_empty_billing_reports_for_empty_company_scope():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_billingreporttable.find_many = AsyncMock()

    listed = await service.list_billing_reports(company_ids=[])

    assert listed.count == 0
    assert listed.billing_reports == []
    prisma_client.db.cavadalabs_billingreporttable.find_many.assert_not_awaited()
