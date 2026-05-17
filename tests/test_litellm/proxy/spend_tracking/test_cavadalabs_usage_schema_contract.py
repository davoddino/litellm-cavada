from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
ROOT_SCHEMA = REPO_ROOT / "schema.prisma"
PROXY_SCHEMA = REPO_ROOT / "litellm/proxy/schema.prisma"
EXTRAS_SCHEMA = REPO_ROOT / "litellm-proxy-extras/litellm_proxy_extras/schema.prisma"
MIGRATIONS_DIR = REPO_ROOT / "litellm-proxy-extras/litellm_proxy_extras/migrations"


def _migration_sql(name: str) -> str:
    return (MIGRATIONS_DIR / name / "migration.sql").read_text()


def test_should_keep_cavadalabs_usage_schema_in_sync_across_root_proxy_and_extras():
    root_schema = ROOT_SCHEMA.read_text()
    proxy_schema = PROXY_SCHEMA.read_text()
    extras_schema = EXTRAS_SCHEMA.read_text()

    assert root_schema == proxy_schema
    assert root_schema == extras_schema

    required_schema_fragments = (
        "model CavadaLabs_CompanyTable",
        "litellm_organization_id    String?  @unique",
        "model CavadaLabs_ProjectTable",
        "litellm_team_id            String?  @unique",
        "model CavadaLabs_CompanyMemberTable",
        "model CavadaLabs_ProjectMemberTable",
        "model CavadaLabs_RequestLedgerTable",
        "request_id                 String   @unique",
        "company_id                 String",
        "project_id                 String",
        "@@index([company_id, created_at])",
        "@@index([project_id, created_at])",
        "model LiteLLM_SpendLogs",
        "@@index([api_key, startTime])",
        "@@index([team_id, startTime])",
        "@@index([organization_id, startTime])",
    )
    for fragment in required_schema_fragments:
        assert fragment in root_schema


def test_should_define_cavadalabs_usage_migration_bundle_for_ledger_attribution():
    dispatcher_sql = _migration_sql("20260514120000_add_cavadalabs_dispatcher_tables")
    mapping_sql = _migration_sql(
        "20260515120000_add_cavadalabs_litellm_membership_mappings"
    )
    spend_log_indexes_sql = _migration_sql(
        "20260515122000_add_cavadalabs_usage_spend_log_indexes"
    )
    metadata_backfill_sql = _migration_sql(
        "20260515123000_backfill_cavadalabs_request_ledger_from_spend_logs"
    )
    key_metadata_backfill_sql = _migration_sql(
        "20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata"
    )
    metadata_key_hash_backfill_sql = _migration_sql(
        "20260515161000_backfill_cavadalabs_request_ledger_from_metadata_key_hash"
    )

    assert (
        'CREATE TABLE IF NOT EXISTS "CavadaLabs_RequestLedgerTable"' in dispatcher_sql
    )
    for column_name in (
        "company_id",
        "project_id",
        "api_key_hash",
        "provider",
        "model",
        "spend",
        "created_at",
    ):
        assert f'"{column_name}"' in dispatcher_sql
    assert (
        'CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_RequestLedgerTable_request_id_key"'
        in dispatcher_sql
    )
    assert '"CavadaLabs_RequestLedgerTable_company_id_created_at_idx"' in dispatcher_sql
    assert '"CavadaLabs_RequestLedgerTable_project_id_created_at_idx"' in dispatcher_sql

    assert 'ADD COLUMN IF NOT EXISTS "litellm_organization_id"' in mapping_sql
    assert 'ADD COLUMN IF NOT EXISTS "litellm_team_id"' in mapping_sql
    assert '"CavadaLabs_CompanyTable_litellm_organization_id_fkey"' in mapping_sql
    assert '"CavadaLabs_ProjectTable_litellm_team_id_fkey"' in mapping_sql

    for index_name in (
        "LiteLLM_SpendLogs_api_key_startTime_idx",
        "LiteLLM_SpendLogs_team_id_startTime_idx",
        "LiteLLM_SpendLogs_organization_id_startTime_idx",
        "LiteLLM_SpendLogs_metadata_gin_idx",
    ):
        assert index_name in spend_log_indexes_sql

    assert 'INSERT INTO "CavadaLabs_RequestLedgerTable"' in metadata_backfill_sql
    assert (
        'LEFT JOIN "CavadaLabs_ProjectTable" compatibility_project'
        in metadata_backfill_sql
    )
    assert (
        'LEFT JOIN "CavadaLabs_CompanyTable" compatibility_company'
        in metadata_backfill_sql
    )
    assert 'ON CONFLICT ("request_id") DO NOTHING' in metadata_backfill_sql

    assert 'FROM "LiteLLM_VerificationToken" k' in key_metadata_backfill_sql
    assert 'FROM "LiteLLM_DeletedVerificationToken" k' in key_metadata_backfill_sql
    assert "key_context" in key_metadata_backfill_sql
    assert 'ON CONFLICT ("request_id") DO NOTHING' in key_metadata_backfill_sql

    assert "metadata_api_key_hash" in metadata_key_hash_backfill_sql
    assert "user_api_key_hash" in metadata_key_hash_backfill_sql
    assert "spend_logs_metadata" in metadata_key_hash_backfill_sql
    assert 'INNER JOIN key_context k' in metadata_key_hash_backfill_sql
    assert 'ON k."token" = s.metadata_api_key_hash' in metadata_key_hash_backfill_sql
    assert 'ON CONFLICT ("request_id") DO NOTHING' in metadata_key_hash_backfill_sql
