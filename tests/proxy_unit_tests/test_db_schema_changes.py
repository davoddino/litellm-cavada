import pytest
import subprocess
import re
from pathlib import Path
from typing import Dict, List, Set


def get_schema_from_branch(branch: str = "main") -> str:
    """Get schema from specified git branch"""
    result = subprocess.run(
        ["git", "show", f"{branch}:schema.prisma"], capture_output=True, text=True
    )
    return result.stdout


def parse_model_fields(schema: str) -> Dict[str, Dict[str, str]]:
    """Parse Prisma schema into dict of models and their fields"""
    models = {}
    current_model = None

    for line in schema.split("\n"):
        line = line.strip()

        # Find model definition
        if line.startswith("model "):
            current_model = line.split(" ")[1]
            models[current_model] = {}
            continue

        # Inside model definition
        if current_model and line and not line.startswith("}"):
            # Split field definition into name and type
            parts = line.split()
            if len(parts) >= 2:
                field_name = parts[0]
                field_type = " ".join(parts[1:])
                models[current_model][field_name] = field_type

        # End of model definition
        if line.startswith("}"):
            current_model = None

    return models


def check_breaking_changes(
    old_schema: Dict[str, Dict[str, str]], new_schema: Dict[str, Dict[str, str]]
) -> List[str]:
    """Check for breaking changes between schemas"""
    breaking_changes = []

    # Check each model in old schema
    for model_name, old_fields in old_schema.items():
        if model_name not in new_schema:
            breaking_changes.append(f"Breaking: Model {model_name} was removed")
            continue

        new_fields = new_schema[model_name]

        # Check each field in old model
        for field_name, old_type in old_fields.items():
            if field_name not in new_fields:
                breaking_changes.append(
                    f"Breaking: Field {model_name}.{field_name} was removed"
                )
                continue

            new_type = new_fields[field_name]

            # Check for type changes
            if old_type != new_type:
                # Check specific type changes that are breaking
                if "?" in old_type and "?" not in new_type:
                    breaking_changes.append(
                        f"Breaking: Field {model_name}.{field_name} changed from optional to required"
                    )
                if not old_type.startswith(new_type.split("?")[0]):
                    breaking_changes.append(
                        f"Breaking: Field {model_name}.{field_name} changed type from {old_type} to {new_type}"
                    )

    return breaking_changes


def test_aaaaaschema_compatibility():
    """Test if current schema has breaking changes compared to main"""
    import os

    print("Current directory:", os.getcwd())

    # Get schemas
    old_schema = get_schema_from_branch("main")
    with open("./schema.prisma", "r") as f:
        new_schema = f.read()

    # Parse schemas
    old_models = parse_model_fields(old_schema)
    new_models = parse_model_fields(new_schema)

    # Check for breaking changes
    breaking_changes = check_breaking_changes(old_models, new_models)

    # Fail if breaking changes found
    if breaking_changes:
        pytest.fail("\n".join(breaking_changes))

    # Print informational diff
    print("\nNon-breaking changes detected:")
    for model_name, new_fields in new_models.items():
        if model_name not in old_models:
            print(f"Added new model: {model_name}")
            continue

        for field_name, new_type in new_fields.items():
            if field_name not in old_models[model_name]:
                print(f"Added new field: {model_name}.{field_name}")


def test_project_usage_migration_backfill_uses_request_metadata_and_existing_projects():
    migration_sql = Path(
        "litellm-proxy-extras/litellm_proxy_extras/migrations/"
        "20260517120000_add_project_spend_usage/migration.sql"
    ).read_text()

    assert "user_api_key_project_id" in migration_sql
    assert '"LiteLLM_ProjectTable" p' in migration_sql
    assert (
        'p."project_id" = NULLIF("LiteLLM_SpendLogs"."metadata"->>\'user_api_key_project_id\', \'\')'
        in migration_sql
    )
    assert (
        'p."project_id" = NULLIF("LiteLLM_SpendLogs"."project_id", \'\')'
        in migration_sql
    )
    assert '"LiteLLM_VerificationToken"' not in migration_sql
    assert '"LiteLLM_DeletedVerificationToken"' not in migration_sql


def test_cavadalabs_company_project_runtime_fields_have_migration_coverage():
    schema_paths = [
        Path("schema.prisma"),
        Path("litellm/proxy/schema.prisma"),
        Path("litellm-proxy-extras/litellm_proxy_extras/schema.prisma"),
    ]
    schemas = [path.read_text() for path in schema_paths]
    assert schemas[0] == schemas[1] == schemas[2]

    schema = schemas[0]
    for fragment in [
        "model LiteLLM_OrganizationTable",
        "model LiteLLM_OrganizationMembership",
        "model LiteLLM_ProjectTable",
        "project_id String?",
        "organization_id     String?",
        "project_id          String?",
        "@@index([organization_id])",
        "@@index([project_id])",
        "@@index([organization_id, startTime])",
        "@@index([project_id, startTime])",
        "@@index([api_key, startTime])",
        "model LiteLLM_DailyOrganizationSpend",
        "model LiteLLM_DailyProjectSpend",
        "project_id          String",
        "@@unique([project_id, date, api_key, model, custom_llm_provider, mcp_namespaced_tool_name, endpoint])",
        "@@index([project_id, date])",
        "@@index([api_key])",
    ]:
        assert fragment in schema

    migrations_dir = Path("litellm-proxy-extras/litellm_proxy_extras/migrations")

    def migration_sql(name: str) -> str:
        return (migrations_dir / name / "migration.sql").read_text()

    baseline = migration_sql("20250326162113_baseline")
    assert 'CREATE TABLE IF NOT EXISTS "LiteLLM_OrganizationTable"' in baseline
    assert 'CREATE TABLE IF NOT EXISTS "LiteLLM_TeamTable"' in baseline
    assert 'CREATE TABLE IF NOT EXISTS "LiteLLM_OrganizationMembership"' in baseline
    assert '"organization_id" TEXT' in baseline

    project = migration_sql("20251113000000_add_project_table")
    assert 'CREATE TABLE IF NOT EXISTS "LiteLLM_ProjectTable"' in project
    assert (
        'ALTER TABLE "LiteLLM_VerificationToken" ADD COLUMN IF NOT EXISTS "project_id" TEXT;'
        in project
    )

    spend_org = migration_sql("20251122125322_Add organization_id to spend logs")
    assert (
        'ALTER TABLE "LiteLLM_SpendLogs" ADD COLUMN IF NOT EXISTS "organization_id" TEXT;'
        in spend_org
    )

    daily_org = migration_sql("20251114180624_Add_org_usage_table")
    assert 'CREATE TABLE IF NOT EXISTS "LiteLLM_DailyOrganizationSpend"' in daily_org
    assert '"organization_id" TEXT' in daily_org
    assert '"api_key" TEXT NOT NULL' in daily_org
    assert "LiteLLM_DailyOrganizationSpend_api_key_idx" in daily_org

    daily_endpoint = migration_sql("20260106155622_add_endpoint_to_daily_activity_tables")
    assert (
        'ALTER TABLE "LiteLLM_DailyOrganizationSpend" ADD COLUMN IF NOT EXISTS "endpoint" TEXT;'
        in daily_endpoint
    )
    assert (
        'ON "LiteLLM_DailyOrganizationSpend"("organization_id", "date", "api_key", "model", "custom_llm_provider", "mcp_namespaced_tool_name", "endpoint")'
        in daily_endpoint
    )

    team_company_index = migration_sql("20260318140652_add_index_to_team_table")
    assert "LiteLLM_TeamTable_organization_id_idx" in team_company_index

    project_usage = migration_sql("20260517120000_add_project_spend_usage")
    assert 'ADD COLUMN IF NOT EXISTS "project_id" TEXT' in project_usage
    assert "LiteLLM_SpendLogs_project_id_startTime_idx" in project_usage
    assert 'CREATE TABLE IF NOT EXISTS "LiteLLM_DailyProjectSpend"' in project_usage
    assert '"project_id" TEXT NOT NULL' in project_usage
    assert "LiteLLM_DailyProjectSpend_project_id_date_idx" in project_usage
    assert "LiteLLM_DailyProjectSpend_api_key_idx" in project_usage
    assert (
        'ON "LiteLLM_DailyProjectSpend"("project_id", "date", "api_key", "model", "custom_llm_provider", "mcp_namespaced_tool_name", "endpoint")'
        in project_usage
    )

    company_spend_index = migration_sql("20260517143000_add_company_spend_logs_index")
    assert "LiteLLM_SpendLogs_organization_id_startTime_idx" in company_spend_index

    key_indexes = migration_sql("20260517160000_add_key_company_project_indexes")
    assert "LiteLLM_VerificationToken_organization_id_idx" in key_indexes
    assert "LiteLLM_VerificationToken_project_id_idx" in key_indexes
    assert "LiteLLM_DeletedVerificationToken_project_id_idx" in key_indexes

    spend_api_key_index = migration_sql(
        "20260518170000_add_spend_logs_api_key_starttime_index"
    )
    assert "LiteLLM_SpendLogs_api_key_startTime_idx" in spend_api_key_index
    assert 'ON "LiteLLM_SpendLogs"("api_key", "startTime")' in spend_api_key_index
