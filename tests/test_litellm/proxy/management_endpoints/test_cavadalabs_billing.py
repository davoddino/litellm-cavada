import base64
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from litellm.proxy import proxy_server
from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.cavadalabs.billing import CavadaLabsBillingService
from litellm.proxy.management_endpoints import (
    cavadalabs_billing_endpoints as billing_endpoints,
)
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsBillingReportGenerateRequest,
)


def _admin() -> UserAPIKeyAuth:
    return UserAPIKeyAuth(
        api_key="sk-test",
        user_id="admin-user",
        user_role=LitellmUserRoles.PROXY_ADMIN,
    )


def _internal_user() -> UserAPIKeyAuth:
    return UserAPIKeyAuth(
        api_key="sk-user",
        user_id="user-1",
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
    prisma_client.db.cavadalabs_companytable.find_many = AsyncMock(return_value=[])
    prisma_client.db.cavadalabs_projecttable = MagicMock()
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[])
    prisma_client.db.cavadalabs_requestledgertable = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable.create_many = AsyncMock()
    prisma_client.db.cavadalabs_nodedailyreporttable = MagicMock()
    prisma_client.db.cavadalabs_billingreporttable = MagicMock()
    prisma_client.db.cavadalabs_auditlogtable = MagicMock()
    prisma_client.db.cavadalabs_auditlogtable.create = AsyncMock()
    prisma_client.db.litellm_spendlogs = MagicMock()
    prisma_client.db.litellm_spendlogs.count = AsyncMock(return_value=0)
    prisma_client.db.litellm_spendlogs.find_many = AsyncMock(return_value=[])
    prisma_client.db.litellm_verificationtoken = MagicMock()
    prisma_client.db.litellm_verificationtoken.find_many = AsyncMock(return_value=[])
    prisma_client.db.litellm_deletedverificationtoken = MagicMock()
    prisma_client.db.litellm_deletedverificationtoken.find_many = AsyncMock(
        return_value=[]
    )
    return CavadaLabsBillingService(prisma_client), prisma_client


def _billing_endpoint_db(company_role="viewer", project_role=None):
    db = MagicMock()

    async def _find_company(*, where):
        company_id = where["company_id"]
        return _company_row(
            company_id=company_id,
            litellm_organization_id=f"org-{company_id}",
        )

    async def _find_company_member(*, where):
        key = where["company_id_user_id"]
        if (
            company_role is not None
            and key["company_id"] == "company-1"
            and key["user_id"] == "user-1"
        ):
            return SimpleNamespace(
                company_id="company-1",
                user_id="user-1",
                role=company_role,
            )
        return None

    async def _find_project_member(*, where):
        key = where["project_id_user_id"]
        if (
            project_role is not None
            and key["project_id"] == "project-1"
            and key["user_id"] == "user-1"
        ):
            return SimpleNamespace(
                project_id="project-1",
                user_id="user-1",
                role=project_role,
            )
        return None

    db.cavadalabs_companytable = MagicMock()
    db.cavadalabs_companytable.find_unique = AsyncMock(side_effect=_find_company)
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[])
    db.cavadalabs_projecttable = MagicMock()
    db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[])
    db.cavadalabs_projecttable.find_unique = AsyncMock(
        return_value=SimpleNamespace(project_id="project-1", company_id="company-1")
    )
    db.cavadalabs_companymembertable = MagicMock()
    db.cavadalabs_companymembertable.find_unique = AsyncMock(
        side_effect=_find_company_member
    )
    db.cavadalabs_companymembertable.find_many = AsyncMock(
        return_value=(
            [
                SimpleNamespace(
                    company_id="company-1",
                    user_id="user-1",
                    role=company_role,
                )
            ]
            if company_role is not None
            else []
        )
    )
    db.cavadalabs_projectmembertable = MagicMock()
    db.cavadalabs_projectmembertable.find_unique = AsyncMock(
        side_effect=_find_project_member
    )
    db.cavadalabs_projectmembertable.find_many = AsyncMock(
        return_value=(
            [
                SimpleNamespace(
                    project_id="project-1",
                    user_id="user-1",
                    role=project_role,
                )
            ]
            if project_role is not None
            else []
        )
    )
    db.litellm_organizationmembership = MagicMock()
    db.litellm_organizationmembership.find_unique = AsyncMock(return_value=None)
    db.litellm_organizationmembership.find_many = AsyncMock(return_value=[])
    db.litellm_usertable = MagicMock()
    db.litellm_usertable.find_unique = AsyncMock(return_value=None)
    db.litellm_teamtable = MagicMock()
    db.litellm_teamtable.find_unique = AsyncMock(return_value=None)
    db.cavadalabs_billingreporttable = MagicMock()
    db.cavadalabs_billingreporttable.find_many = AsyncMock(
        return_value=[
            _billing_report_row(report_id="billing-report-1", company_id="company-1")
        ]
    )
    db.cavadalabs_billingreporttable.find_unique = AsyncMock(
        return_value=_billing_report_row(
            report_id="billing-report-1",
            company_id="company-1",
        )
    )
    return db


def _patch_proxy_prisma(monkeypatch, db):
    monkeypatch.setattr(proxy_server, "prisma_client", SimpleNamespace(db=db))


def _patch_generate_billing_service(monkeypatch):
    calls = []
    report = billing_endpoints.CavadaLabsBillingReportResponse.model_validate(
        _billing_report_row().__dict__
    )

    class _GenerateBillingService:
        def __init__(self, prisma_client):
            self.prisma_client = prisma_client

        async def generate_monthly_report(self, data, user_api_key_dict):
            calls.append((data, user_api_key_dict, self.prisma_client))
            return report

    monkeypatch.setattr(
        billing_endpoints,
        "CavadaLabsBillingService",
        _GenerateBillingService,
    )
    return calls, report


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
        side_effect=[[], company_rows, all_node_rows]
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
async def test_should_generate_billing_from_existing_ledger_when_key_backfill_schema_missing():
    service, prisma_client = _service()
    company_rows = [_ledger_row(request_id="request-existing", total_tokens=150)]
    prisma_client.db.litellm_deletedverificationtoken = None
    prisma_client.db.cavadalabs_companytable.find_unique = AsyncMock(
        return_value=_company_row()
    )
    prisma_client.db.cavadalabs_requestledgertable.find_many = AsyncMock(
        side_effect=[[], company_rows, company_rows]
    )
    prisma_client.db.cavadalabs_nodedailyreporttable.find_many = AsyncMock(
        return_value=[]
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
            formats=["json"],
        ),
        _admin(),
    )

    assert response.total_requests == 1
    assert response.total_tokens == 150
    assert response.total_spend == pytest.approx(0.15)
    prisma_client.db.cavadalabs_requestledgertable.create_many.assert_not_awaited()
    prisma_client.db.cavadalabs_billingreporttable.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_should_generate_billing_from_existing_ledger_when_spendlogs_repair_schema_missing():
    service, prisma_client = _service()
    company_rows = [_ledger_row(request_id="request-existing", total_tokens=150)]
    prisma_client.db.litellm_spendlogs.count = AsyncMock(
        side_effect=Exception('column "model_group" does not exist')
    )
    prisma_client.db.cavadalabs_companytable.find_unique = AsyncMock(
        return_value=_company_row()
    )
    prisma_client.db.cavadalabs_companytable.find_many = AsyncMock(
        return_value=[_company_row(litellm_organization_id="org-company-1")]
    )
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                project_id="project-1",
                company_id="company-1",
                litellm_team_id="team-project-1",
            )
        ]
    )
    prisma_client.db.cavadalabs_requestledgertable.find_many = AsyncMock(
        side_effect=[[], company_rows, company_rows]
    )
    prisma_client.db.cavadalabs_nodedailyreporttable.find_many = AsyncMock(
        return_value=[]
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
            formats=["json"],
        ),
        _admin(),
    )

    assert response.total_requests == 1
    assert response.total_tokens == 150
    assert response.total_spend == pytest.approx(0.15)
    prisma_client.db.cavadalabs_requestledgertable.create_many.assert_not_awaited()
    prisma_client.db.cavadalabs_billingreporttable.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_should_report_missing_usage_schema_for_billing_generation():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_companytable.find_unique = AsyncMock(
        return_value=_company_row()
    )
    prisma_client.db.cavadalabs_requestledgertable.find_many = AsyncMock(
        side_effect=Exception('relation "CavadaLabs_RequestLedgerTable" does not exist')
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.generate_monthly_report(
            CavadaLabsBillingReportGenerateRequest(
                company_id="company-1",
                year=2026,
                month=5,
                formats=["json"],
            ),
            _admin(),
        )

    assert exc_info.value.status_code == 503
    detail = exc_info.value.detail
    assert detail["operation"] == "generate_cavadalabs_billing_report"
    assert detail["schema_status"] == "missing_schema"
    assert detail["migration_status"] == "schema_missing"
    assert detail["recommended_action"] == "run_migration_backfill"
    assert "prisma migrate deploy" in detail["migration_command"]
    assert detail["missing_schema"]
    prisma_client.db.cavadalabs_billingreporttable.create.assert_not_called()


@pytest.mark.asyncio
async def test_should_repair_empty_billing_ledger_from_cavadalabs_spend_logs():
    service, prisma_client = _service()
    ledger_row = _ledger_row(
        ledger_id="ledger-repaired",
        request_id="request-repaired",
        spend=0.42,
        total_tokens=42,
        node_id=None,
        gpu_id=None,
        loaded_model_id=None,
        model_load_request_id=None,
    )
    prisma_client.db.cavadalabs_companytable.find_unique = AsyncMock(
        return_value=_company_row()
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
            _row(
                project_id="project-1",
                company_id="company-1",
                litellm_team_id="team-compat-1",
            )
        ]
    )
    prisma_client.db.cavadalabs_requestledgertable.find_many = AsyncMock(
        side_effect=[
            [],
            [],
            [ledger_row],
            [ledger_row],
        ]
    )
    prisma_client.db.litellm_spendlogs.find_many = AsyncMock(
        return_value=[
            _row(
                request_id="request-repaired",
                api_key="hashed-key",
                spend=0.42,
                prompt_tokens=21,
                completion_tokens=21,
                total_tokens=42,
                startTime=datetime(2026, 5, 14, 12, tzinfo=timezone.utc),
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
    prisma_client.db.cavadalabs_nodedailyreporttable.find_many = AsyncMock(
        return_value=[]
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
            formats=["json"],
        ),
        _admin(),
    )

    prisma_client.db.cavadalabs_requestledgertable.create_many.assert_awaited_once()
    create_call = (
        prisma_client.db.cavadalabs_requestledgertable.create_many.call_args.kwargs
    )
    assert create_call["skip_duplicates"] is True
    assert create_call["data"][0]["request_id"] == "request-repaired"
    assert create_call["data"][0]["company_id"] == "company-1"
    assert create_call["data"][0]["project_id"] == "project-1"
    assert response.total_requests == 1
    assert response.total_spend == pytest.approx(0.42)
    spend_where = prisma_client.db.litellm_spendlogs.find_many.call_args.kwargs["where"]
    assert {"team_id": {"in": ["team-compat-1"]}} in spend_where["AND"][0]["OR"]


@pytest.mark.asyncio
async def test_should_repair_partial_billing_ledger_from_cavadalabs_spend_logs():
    service, prisma_client = _service()
    existing_row = _ledger_row(
        ledger_id="ledger-existing",
        request_id="request-existing",
        spend=0.10,
        total_tokens=10,
        node_id=None,
        gpu_id=None,
        loaded_model_id=None,
        model_load_request_id=None,
    )
    repaired_row = _ledger_row(
        ledger_id="ledger-repaired",
        request_id="request-repaired",
        spend=0.42,
        total_tokens=42,
        node_id=None,
        gpu_id=None,
        loaded_model_id=None,
        model_load_request_id=None,
    )
    prisma_client.db.cavadalabs_companytable.find_unique = AsyncMock(
        return_value=_company_row()
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
            _row(
                project_id="project-1",
                company_id="company-1",
                litellm_team_id="team-compat-1",
            )
        ]
    )
    prisma_client.db.cavadalabs_requestledgertable.find_many = AsyncMock(
        side_effect=[
            [],
            [existing_row],
            [existing_row, repaired_row],
        ]
    )
    prisma_client.db.litellm_spendlogs.count = AsyncMock(return_value=2)
    prisma_client.db.litellm_spendlogs.find_many = AsyncMock(
        return_value=[
            _row(
                request_id="request-repaired",
                api_key="hashed-key",
                spend=0.42,
                prompt_tokens=21,
                completion_tokens=21,
                total_tokens=42,
                startTime=datetime(2026, 5, 14, 12, tzinfo=timezone.utc),
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
    prisma_client.db.cavadalabs_nodedailyreporttable.find_many = AsyncMock(
        return_value=[]
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
            formats=["json"],
        ),
        _admin(),
    )

    assert prisma_client.db.litellm_spendlogs.count.await_count >= 1
    count_where = prisma_client.db.litellm_spendlogs.count.await_args.kwargs["where"]
    assert {"team_id": {"in": ["team-compat-1"]}} in count_where["AND"][0]["OR"]
    prisma_client.db.cavadalabs_requestledgertable.create_many.assert_awaited_once()
    create_call = (
        prisma_client.db.cavadalabs_requestledgertable.create_many.call_args.kwargs
    )
    assert create_call["skip_duplicates"] is True
    assert create_call["data"][0]["request_id"] == "request-repaired"
    assert create_call["data"][0]["company_id"] == "company-1"
    assert create_call["data"][0]["project_id"] == "project-1"
    assert response.total_requests == 2
    assert response.total_spend == pytest.approx(0.52)


@pytest.mark.asyncio
async def test_should_return_existing_report_when_checksum_matches():
    service, prisma_client = _service()
    existing_report = _billing_report_row(checksum="existing-checksum")
    prisma_client.db.cavadalabs_companytable.find_unique = AsyncMock(
        return_value=_company_row()
    )
    prisma_client.db.cavadalabs_requestledgertable.find_many = AsyncMock(
        return_value=[]
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


@pytest.mark.asyncio
async def test_billing_list_endpoint_filters_to_native_cavadalabs_company_scope(
    monkeypatch,
):
    db = _billing_endpoint_db()
    _patch_proxy_prisma(monkeypatch, db)

    response = await billing_endpoints.list_billing_reports(
        http_request=MagicMock(),
        company_id=None,
        year=None,
        month=None,
        take=100,
        skip=0,
        user_api_key_dict=_internal_user(),
    )

    assert response.count == 1
    where = db.cavadalabs_billingreporttable.find_many.call_args.kwargs["where"]
    assert where["company_id"] == {"in": ["company-1"]}


@pytest.mark.asyncio
async def test_billing_list_endpoint_rejects_cross_company_scope(monkeypatch):
    db = _billing_endpoint_db()
    _patch_proxy_prisma(monkeypatch, db)

    with pytest.raises(HTTPException) as exc_info:
        await billing_endpoints.list_billing_reports(
            http_request=MagicMock(),
            company_id="company-2",
            year=None,
            month=None,
            take=100,
            skip=0,
            user_api_key_dict=_internal_user(),
        )

    assert exc_info.value.status_code == 403
    db.cavadalabs_billingreporttable.find_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_billing_list_endpoint_rejects_project_only_parent_company_scope(
    monkeypatch,
):
    db = _billing_endpoint_db(company_role=None, project_role="viewer")
    _patch_proxy_prisma(monkeypatch, db)

    with pytest.raises(HTTPException) as exc_info:
        await billing_endpoints.list_billing_reports(
            http_request=MagicMock(),
            company_id="company-1",
            year=None,
            month=None,
            take=100,
            skip=0,
            user_api_key_dict=_internal_user(),
        )

    assert exc_info.value.status_code == 403
    db.cavadalabs_billingreporttable.find_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_billing_list_endpoint_returns_empty_for_project_only_user_without_company_scope(
    monkeypatch,
):
    db = _billing_endpoint_db(company_role=None, project_role="project_admin")
    _patch_proxy_prisma(monkeypatch, db)

    response = await billing_endpoints.list_billing_reports(
        http_request=MagicMock(),
        company_id=None,
        year=None,
        month=None,
        take=100,
        skip=0,
        user_api_key_dict=_internal_user(),
    )

    assert response.count == 0
    assert response.billing_reports == []
    db.cavadalabs_billingreporttable.find_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_billing_generate_endpoint_allows_native_company_admin(monkeypatch):
    db = _billing_endpoint_db(company_role="company_admin")
    _patch_proxy_prisma(monkeypatch, db)
    calls, expected_report = _patch_generate_billing_service(monkeypatch)

    response = await billing_endpoints.generate_billing_report(
        data=CavadaLabsBillingReportGenerateRequest(
            company_id="company-1",
            year=2026,
            month=5,
            formats=["json"],
        ),
        http_request=MagicMock(),
        user_api_key_dict=_internal_user(),
    )

    assert response == expected_report
    assert len(calls) == 1
    assert calls[0][0].company_id == "company-1"
    assert calls[0][1].user_id == "user-1"


@pytest.mark.asyncio
async def test_billing_generate_endpoint_rejects_company_viewer(monkeypatch):
    db = _billing_endpoint_db()
    _patch_proxy_prisma(monkeypatch, db)
    calls, _ = _patch_generate_billing_service(monkeypatch)

    with pytest.raises(HTTPException) as exc_info:
        await billing_endpoints.generate_billing_report(
            data=CavadaLabsBillingReportGenerateRequest(
                company_id="company-1",
                year=2026,
                month=5,
                formats=["json"],
            ),
            http_request=MagicMock(),
            user_api_key_dict=_internal_user(),
        )

    assert exc_info.value.status_code == 403
    assert calls == []


@pytest.mark.asyncio
async def test_billing_generate_endpoint_rejects_native_project_admin(monkeypatch):
    db = _billing_endpoint_db(company_role=None, project_role="project_admin")
    _patch_proxy_prisma(monkeypatch, db)
    calls, _ = _patch_generate_billing_service(monkeypatch)

    with pytest.raises(HTTPException) as exc_info:
        await billing_endpoints.generate_billing_report(
            data=CavadaLabsBillingReportGenerateRequest(
                company_id="company-1",
                year=2026,
                month=5,
                formats=["json"],
            ),
            http_request=MagicMock(),
            user_api_key_dict=_internal_user(),
        )

    assert exc_info.value.status_code == 403
    assert calls == []


@pytest.mark.asyncio
async def test_billing_get_endpoint_allows_native_company_viewer(monkeypatch):
    db = _billing_endpoint_db(company_role="viewer")
    _patch_proxy_prisma(monkeypatch, db)

    response = await billing_endpoints.get_billing_report(
        report_id="billing-report-1",
        http_request=MagicMock(),
        user_api_key_dict=_internal_user(),
    )

    assert response.report_id == "billing-report-1"
    assert response.company_id == "company-1"


@pytest.mark.asyncio
async def test_billing_get_endpoint_rejects_native_project_admin(monkeypatch):
    db = _billing_endpoint_db(company_role=None, project_role="project_admin")
    _patch_proxy_prisma(monkeypatch, db)

    with pytest.raises(HTTPException) as exc_info:
        await billing_endpoints.get_billing_report(
            report_id="billing-report-1",
            http_request=MagicMock(),
            user_api_key_dict=_internal_user(),
        )

    assert exc_info.value.status_code == 403
