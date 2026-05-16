from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.cavadalabs.billing import CavadaLabsBillingService
from litellm.proxy.cavadalabs.usage import (
    get_cavadalabs_daily_activity,
    get_cavadalabs_usage_diagnostics,
)
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsBillingReportGenerateRequest,
    CavadaLabsUsageSchemaStatus,
)


def _admin() -> UserAPIKeyAuth:
    return UserAPIKeyAuth(
        api_key="sk-test",
        user_id="admin-user",
        user_role=LitellmUserRoles.PROXY_ADMIN,
    )


def _company_row(**kwargs):
    return SimpleNamespace(
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
        default_billing_settings=kwargs.pop("default_billing_settings", {}),
        litellm_organization_id=kwargs.pop("litellm_organization_id", "org-1"),
        created_at=kwargs.pop("created_at", datetime.now(timezone.utc)),
        updated_at=kwargs.pop("updated_at", datetime.now(timezone.utc)),
        created_by=kwargs.pop("created_by", "admin-user"),
        updated_by=kwargs.pop("updated_by", "admin-user"),
        **kwargs,
    )


def _prisma_client():
    prisma_client = MagicMock()
    prisma_client.db = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable = MagicMock()
    prisma_client.db.cavadalabs_requestledgertable.find_many = AsyncMock(
        return_value=[]
    )
    prisma_client.db.cavadalabs_requestledgertable.count = AsyncMock(return_value=0)
    prisma_client.db.cavadalabs_requestledgertable.create_many = AsyncMock()
    prisma_client.db.cavadalabs_companytable = MagicMock()
    prisma_client.db.cavadalabs_companytable.find_unique = AsyncMock(
        return_value=_company_row()
    )
    prisma_client.db.cavadalabs_companytable.find_many = AsyncMock(return_value=[])
    prisma_client.db.cavadalabs_projecttable = MagicMock()
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(return_value=[])
    prisma_client.db.cavadalabs_nodedailyreporttable = MagicMock()
    prisma_client.db.cavadalabs_nodedailyreporttable.find_many = AsyncMock(
        return_value=[]
    )
    prisma_client.db.cavadalabs_billingreporttable = MagicMock()
    prisma_client.db.cavadalabs_billingreporttable.create = AsyncMock()
    prisma_client.db.cavadalabs_billingreporttable.find_many = AsyncMock(
        return_value=[]
    )
    prisma_client.db.cavadalabs_billingreporttable.find_unique = AsyncMock(
        return_value=None
    )
    prisma_client.db.litellm_spendlogs = MagicMock()
    prisma_client.db.litellm_spendlogs.count = AsyncMock(return_value=0)
    prisma_client.db.litellm_spendlogs.find_many = AsyncMock(return_value=[])
    prisma_client.db.litellm_verificationtoken = MagicMock()
    prisma_client.db.litellm_verificationtoken.find_many = AsyncMock(return_value=[])
    prisma_client.db.litellm_deletedverificationtoken = MagicMock()
    prisma_client.db.litellm_deletedverificationtoken.find_many = AsyncMock(
        return_value=[]
    )
    return prisma_client


def test_should_keep_cavadalabs_usage_migrations_aligned_with_schema_contract():
    repo_root = Path(__file__).parents[4]
    migration_root = (
        repo_root / "litellm-proxy-extras" / "litellm_proxy_extras" / "migrations"
    )
    dispatcher_sql = (
        migration_root
        / "20260514120000_add_cavadalabs_dispatcher_tables"
        / "migration.sql"
    ).read_text()
    billing_sql = (
        migration_root
        / "20260514130000_add_cavadalabs_billing_reports"
        / "migration.sql"
    ).read_text()
    membership_mapping_sql = (
        migration_root
        / "20260515120000_add_cavadalabs_litellm_membership_mappings"
        / "migration.sql"
    ).read_text()
    spend_indexes_sql = (
        migration_root
        / "20260515122000_add_cavadalabs_usage_spend_log_indexes"
        / "migration.sql"
    ).read_text()
    spend_backfill_sql = (
        migration_root
        / "20260515123000_backfill_cavadalabs_request_ledger_from_spend_logs"
        / "migration.sql"
    ).read_text()
    key_backfill_sql = (
        migration_root
        / "20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata"
        / "migration.sql"
    ).read_text()
    native_membership_sql = (
        migration_root
        / "20260515150000_add_cavadalabs_native_memberships"
        / "migration.sql"
    ).read_text()
    schema_texts = [
        (repo_root / "schema.prisma").read_text(),
        (repo_root / "litellm" / "proxy" / "schema.prisma").read_text(),
        (
            repo_root
            / "litellm-proxy-extras"
            / "litellm_proxy_extras"
            / "schema.prisma"
        ).read_text(),
    ]

    for schema_text in schema_texts:
        assert "model CavadaLabs_RequestLedgerTable" in schema_text
        assert "request_id                 String   @unique" in schema_text
        assert 'metadata                   Json     @default("{}")' in schema_text
        assert "@@index([company_id, created_at])" in schema_text
        assert "@@index([project_id, created_at])" in schema_text
        assert "@@index([provider, model])" in schema_text
        assert "model CavadaLabs_BillingReportTable" in schema_text
        assert "checksum                   String   @unique" in schema_text
        assert (
            "@@unique([company_id, period_start, period_end, report_version])"
            in schema_text
        )
        assert "litellm_organization_id    String?  @unique" in schema_text
        assert "litellm_team_id            String?  @unique" in schema_text
        assert "model CavadaLabs_CompanyMemberTable" in schema_text
        assert "model CavadaLabs_ProjectMemberTable" in schema_text
        assert "@@index([api_key, startTime])" in schema_text
        assert "@@index([team_id, startTime])" in schema_text
        assert "@@index([organization_id, startTime])" in schema_text
        assert "@@index([model, startTime])" in schema_text
        assert "@@index([model_group, startTime])" in schema_text

    for fragment in [
        'CREATE TABLE IF NOT EXISTS "CavadaLabs_RequestLedgerTable"',
        '"request_id" TEXT NOT NULL',
        '"company_id" TEXT NOT NULL',
        '"project_id" TEXT NOT NULL',
        '"api_key_hash" TEXT',
        '"provider" TEXT NOT NULL',
        '"model" TEXT NOT NULL',
        '"metadata" JSONB NOT NULL DEFAULT',
        'CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_RequestLedgerTable_request_id_key"',
        'ON "CavadaLabs_RequestLedgerTable"("request_id")',
        'CREATE INDEX IF NOT EXISTS "CavadaLabs_RequestLedgerTable_company_id_created_at_idx"',
        'CREATE INDEX IF NOT EXISTS "CavadaLabs_RequestLedgerTable_project_id_created_at_idx"',
        'CREATE INDEX IF NOT EXISTS "CavadaLabs_RequestLedgerTable_provider_model_idx"',
    ]:
        assert fragment in dispatcher_sql

    for fragment in [
        'CREATE TABLE IF NOT EXISTS "CavadaLabs_BillingReportTable"',
        '"checksum" TEXT NOT NULL',
        'CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_BillingReportTable_checksum_key"',
        'CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_BillingReportTable_company_id_period_start_period_end_report_version_key"',
        'CREATE INDEX IF NOT EXISTS "CavadaLabs_BillingReportTable_company_id_period_start_period_end_idx"',
    ]:
        assert fragment in billing_sql

    for fragment in [
        'ADD COLUMN IF NOT EXISTS "litellm_organization_id" TEXT',
        'ADD COLUMN IF NOT EXISTS "litellm_team_id" TEXT',
        'CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_CompanyTable_litellm_organization_id_key"',
        'CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_ProjectTable_litellm_team_id_key"',
        'REFERENCES "LiteLLM_OrganizationTable"("organization_id")',
        'REFERENCES "LiteLLM_TeamTable"("team_id")',
    ]:
        assert fragment in membership_mapping_sql

    for fragment in [
        'CREATE INDEX IF NOT EXISTS "LiteLLM_SpendLogs_api_key_startTime_idx"',
        'CREATE INDEX IF NOT EXISTS "LiteLLM_SpendLogs_team_id_startTime_idx"',
        'CREATE INDEX IF NOT EXISTS "LiteLLM_SpendLogs_organization_id_startTime_idx"',
        'CREATE INDEX IF NOT EXISTS "LiteLLM_SpendLogs_model_startTime_idx"',
        'CREATE INDEX IF NOT EXISTS "LiteLLM_SpendLogs_model_group_startTime_idx"',
        'CREATE INDEX IF NOT EXISTS "LiteLLM_SpendLogs_metadata_gin_idx"',
    ]:
        assert fragment in spend_indexes_sql

    for sql in (spend_backfill_sql, key_backfill_sql):
        assert 'INSERT INTO "CavadaLabs_RequestLedgerTable"' in sql
        assert 'FROM "LiteLLM_SpendLogs"' in sql
        assert 'ON CONFLICT ("request_id") DO NOTHING' in sql
        assert "cavadalabs_company_id" in sql
        assert "cavadalabs_project_id" in sql
        assert '"litellm_team_id"' in sql
        assert '"litellm_organization_id"' in sql

    assert 'FROM "LiteLLM_VerificationToken"' in key_backfill_sql
    assert 'FROM "LiteLLM_DeletedVerificationToken"' in key_backfill_sql
    assert "key_chatbot_id" in key_backfill_sql
    assert "k.key_chatbot_id" in key_backfill_sql
    assert "cavadalabs_chatbot_id" in key_backfill_sql

    for fragment in [
        'CREATE TABLE IF NOT EXISTS "CavadaLabs_CompanyMemberTable"',
        'CREATE TABLE IF NOT EXISTS "CavadaLabs_ProjectMemberTable"',
        'CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_CompanyMemberTable_company_id_user_id_key"',
        'CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_ProjectMemberTable_project_id_user_id_key"',
        'CHECK ("role" IN (',
        'REFERENCES "LiteLLM_UserTable"("user_id")',
    ]:
        assert fragment in native_membership_sql


def test_should_not_ship_empty_cavadalabs_usage_migration_directories():
    repo_root = Path(__file__).parents[4]
    migration_root = (
        repo_root / "litellm-proxy-extras" / "litellm_proxy_extras" / "migrations"
    )

    cavadalabs_usage_migrations = [
        migration_dir
        for migration_dir in migration_root.iterdir()
        if migration_dir.is_dir() and "cavadalabs" in migration_dir.name
    ]

    assert cavadalabs_usage_migrations
    for migration_dir in cavadalabs_usage_migrations:
        assert (
            migration_dir / "migration.sql"
        ).is_file(), f"{migration_dir.name} is missing migration.sql"


@pytest.mark.asyncio
async def test_should_raise_missing_request_ledger_schema_before_empty_daily_usage():
    prisma_client = _prisma_client()
    prisma_client.db.cavadalabs_requestledgertable.find_many = AsyncMock(
        side_effect=Exception('column "metadata" does not exist')
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_cavadalabs_daily_activity(
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

    assert exc_info.value.status_code == 503
    detail = exc_info.value.detail
    assert detail["operation"] == "read_cavadalabs_daily_activity"
    assert detail["schema_status"] == "missing_schema"
    assert any(
        "CavadaLabs_RequestLedgerTable" in item and "metadata" in item
        for item in detail["missing_schema"]
    )
    assert (
        detail["migration_name"]
        == "20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata"
    )
    assert (
        "20260514120000_add_cavadalabs_dispatcher_tables" in detail["migration_names"]
    )
    assert (
        "20260515120000_add_cavadalabs_litellm_membership_mappings"
        in detail["migration_names"]
    )
    assert (
        "20260515122000_add_cavadalabs_usage_spend_log_indexes"
        in detail["migration_names"]
    )
    assert (
        "20260515123000_backfill_cavadalabs_request_ledger_from_spend_logs"
        in detail["migration_names"]
    )
    assert (
        "20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata"
        in detail["migration_names"]
    )
    migration_plan_names = [step["name"] for step in detail["migration_plan"]]
    assert "20260514120000_add_cavadalabs_dispatcher_tables" in migration_plan_names
    assert (
        "20260515120000_add_cavadalabs_litellm_membership_mappings"
        in migration_plan_names
    )
    assert "prisma migrate deploy" in detail["migration_command"]
    prisma_client.db.cavadalabs_requestledgertable.count.assert_not_awaited()


@pytest.mark.asyncio
async def test_should_report_missing_project_mapping_schema_in_usage_diagnostics():
    prisma_client = _prisma_client()
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        side_effect=Exception('column "litellm_team_id" does not exist')
    )

    response = await get_cavadalabs_usage_diagnostics(
        prisma_client=prisma_client,
        entity_type="project",
        entity_id=["project-1"],
        start_date="2026-05-15",
        end_date="2026-05-15",
        timezone_offset_minutes=0,
    )

    assert response.schema_status == CavadaLabsUsageSchemaStatus.MISSING_SCHEMA
    assert response.migration_status == "schema_missing"
    assert response.diagnostics[0].entity_id == "project-1"
    assert response.diagnostics[0].missing_schema
    assert any(
        "CavadaLabs_ProjectTable" in item and "litellm_team_id" in item
        for item in response.missing_schema
    )
    assert "prisma migrate deploy" in response.migration_command
    prisma_client.db.cavadalabs_requestledgertable.create_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_should_raise_missing_company_mapping_schema_before_empty_daily_usage():
    prisma_client = _prisma_client()
    prisma_client.db.cavadalabs_companytable.find_many = AsyncMock(
        side_effect=Exception('column "litellm_organization_id" does not exist')
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_cavadalabs_daily_activity(
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

    assert exc_info.value.status_code == 503
    detail = exc_info.value.detail
    assert detail["operation"] == "read_cavadalabs_daily_activity"
    assert detail["schema_status"] == "missing_schema"
    assert any(
        "CavadaLabs_CompanyTable" in item and "litellm_organization_id" in item
        for item in detail["missing_schema"]
    )
    assert "prisma migrate deploy" in detail["migration_command"]
    prisma_client.db.cavadalabs_requestledgertable.count.assert_not_awaited()


@pytest.mark.asyncio
async def test_should_raise_missing_project_mapping_schema_for_billing_generation():
    prisma_client = _prisma_client()
    prisma_client.db.cavadalabs_projecttable.find_many = AsyncMock(
        side_effect=Exception('column "litellm_team_id" does not exist')
    )
    service = CavadaLabsBillingService(prisma_client)

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
    assert any(
        "CavadaLabs_ProjectTable" in item and "litellm_team_id" in item
        for item in detail["missing_schema"]
    )
    assert "prisma migrate deploy" in detail["migration_command"]
    prisma_client.db.cavadalabs_billingreporttable.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_should_raise_missing_key_backfill_schema_before_empty_billing_report():
    prisma_client = _prisma_client()
    prisma_client.db.litellm_deletedverificationtoken = None
    service = CavadaLabsBillingService(prisma_client)

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
    assert detail["operation"] == "repair_empty_cavadalabs_billing_report"
    assert detail["schema_status"] == "missing_schema"
    assert "LiteLLM_DeletedVerificationToken delegate" in detail["missing_schema"]
    assert "prisma migrate deploy" in detail["migration_command"]
    prisma_client.db.cavadalabs_billingreporttable.create.assert_not_awaited()
