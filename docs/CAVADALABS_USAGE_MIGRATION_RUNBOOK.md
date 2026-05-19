# CavadaLabs Usage Migration Runbook

## Purpose

Company and Project usage is read from `CavadaLabs_RequestLedgerTable`. New
requests populate that ledger from the CavadaLabs key context during the normal
LiteLLM spend-log queue processing. Older `LiteLLM_SpendLogs` rows may already
contain CavadaLabs metadata but will not be visible in Company/Project usage
until the ledger is backfilled or scoped repair runs.

## Symptom

- A virtual key has `cavadalabs_company_id` and `cavadalabs_project_id`.
- Spend exists in `LiteLLM_SpendLogs`.
- `/cavadalabs/*/daily/activity` or the CavadaLabs usage UI shows no usage for
the expected Company/Project.

## Automatic Attribution

For new requests, CavadaLabs usage attribution is not a manual repair step. The
standard LiteLLM spend-log writer calls the CavadaLabs request-ledger processor
for the same batch after `LiteLLM_SpendLogs` has been written. The runtime
resolver derives the canonical product context in this order:

- CavadaLabs Company/Project metadata already present on the spend log;
- `LiteLLM_VerificationToken.metadata` for the hashed `api_key`, including the
  key's `spend_logs_metadata`;
- `LiteLLM_DeletedVerificationToken.metadata` for historical spend whose
  virtual key was deleted after the request was logged;
- the active or deleted virtual key's internal `team_id` mapped through
  `CavadaLabs_ProjectTable.litellm_team_id`;
- the request or key internal `organization_id` mapped through
  `CavadaLabs_CompanyTable.litellm_organization_id`.

The resolver only writes a Cavada request ledger row when both Company and
Project resolve and the Project belongs to that Company. If key metadata and a
Project mapping conflict, the row is skipped instead of being attributed to the
wrong tenant. LiteLLM Organization/Team are compatibility inputs only; CavadaLabs
Company/Project are the product context stored in the ledger.

## Ledger-Native Read Path

Company and Project usage APIs read from `CavadaLabs_RequestLedgerTable` as the
authoritative source:

- `GET /cavadalabs/companies/daily/activity`
- `GET /cavadalabs/projects/daily/activity`
- monthly billing report generation

The daily activity endpoints filter the Cavada ledger by Company/Project,
`created_at`, `model`, `provider`, `status`, `api_key_hash`, and optional spend
range. They aggregate all matching request-ledger rows by day before paginating
the daily result rows, so high-volume Company/Project scopes are not truncated by
the request-row `page_size`. They do not expose LiteLLM Organization or Team as
product filters. If the selected ledger slice is empty or appears partial, the
endpoint may trigger a scoped repair from `LiteLLM_SpendLogs`, but that repair is
a recovery path for historical or previously unattributed data. New requests
should be visible from the ledger-native read path as soon as the standard
LiteLLM spend-log queue has processed the batch.

Reading ledger rows only requires the CavadaLabs request-ledger schema. The
active/deleted virtual-key delegates are required for diagnostics and scoped
repair from legacy SpendLogs, but missing key-backfill schema must not hide usage
that is already present in `CavadaLabs_RequestLedgerTable`.

## Offline Schema Contract

The CavadaLabs usage path depends on these schema and migration contracts. They
can be checked without a live database by comparing the three Prisma schemas
(`schema.prisma`, `litellm/proxy/schema.prisma`,
`litellm-proxy-extras/litellm_proxy_extras/schema.prisma`) and the SQL
migrations under `litellm-proxy-extras/litellm_proxy_extras/migrations`.

`CavadaLabs_RequestLedgerTable` is the product usage table. The runtime writer
uses these columns: `request_id`, `company_id`, `project_id`, `chatbot_id`,
`web_token_id`, `session_id`, `api_key_hash`, `provider`, `model`, `node_id`,
`gpu_id`, `loaded_model_id`, `model_load_request_id`, token counts, `spend`,
`status`, `metadata`, and `created_at`. The schema requires `company_id` and
`project_id`, makes `request_id` unique, and indexes:

- `company_id, created_at`
- `project_id, created_at`
- `chatbot_id, created_at`
- `web_token_id, created_at`
- `provider, model`
- `node_id, gpu_id`

The current RequestLedger schema does not define Prisma relation fields or SQL
foreign keys to Company/Project. Runtime and backfill code validate that the
resolved Project belongs to the resolved Company before writing; conflicting
Company/Project mappings are skipped rather than attached to the wrong tenant.
Do not add ledger FKs casually: evaluate historical ledger retention and hard
delete semantics first.

`CavadaLabs_CompanyTable` and `CavadaLabs_ProjectTable` are the product tenant
tables. Their compatibility fields are internal only:

- Company: `litellm_organization_id String? @unique`
- Project: `litellm_team_id String? @unique`

The compatibility migration adds those columns, unique indexes, and FKs to
LiteLLM Organization/Team with `ON DELETE SET NULL`. Product usage reads still
filter by CavadaLabs `company_id` and `project_id`.

Native membership is stored in:

- `CavadaLabs_CompanyMemberTable`: unique `(company_id, user_id)`, indexes
  `(company_id, role)` and `(user_id, role)`, FK cascade to Company and user.
- `CavadaLabs_ProjectMemberTable`: unique `(project_id, user_id)`, indexes
  `(project_id, role)` and `(user_id, role)`, FK cascade to Project and user.

The scoped repair and diagnostics path also depends on SpendLogs indexes:

- `LiteLLM_SpendLogs_api_key_startTime_idx`
- `LiteLLM_SpendLogs_team_id_startTime_idx`
- `LiteLLM_SpendLogs_organization_id_startTime_idx`
- `LiteLLM_SpendLogs_model_startTime_idx`
- `LiteLLM_SpendLogs_model_group_startTime_idx`
- `LiteLLM_SpendLogs_metadata_gin_idx`

No CavadaLabs usage endpoint should expose Organization or Team as product
filters. They are only compatibility inputs used to resolve old LiteLLM spend
rows or keys into Company/Project.

Company/Project filters over `LiteLLM_SpendLogs.metadata` and virtual-key
metadata use the existing JSON/JSONB columns plus
`LiteLLM_SpendLogs_metadata_gin_idx`. No additional migration is required for
the runtime filter fix that makes selected Company/Project keys and usage
visible: Prisma JSON-path string comparisons must pass JSON string literals
(`"company_id"` / `"project_id"`) at the query boundary, while the database
schema and indexes above remain unchanged.

Monthly billing generation uses the same usage-schema preflight. If the
`CavadaLabs_RequestLedgerTable` delegate or required Company/Project usage
columns are missing, billing generation returns a structured 503 with
`schema_status=missing_schema`, `migration_status=schema_missing`,
`recommended_action=run_migration_backfill`, and the `prisma migrate deploy`
command instead of producing an empty or partial report. If ledger rows already
exist for the billing month, billing can generate from those rows even if the
key-backfill delegates still need migration before historical repair.

## Scoped automatic repair

When a selected Company or Project daily usage request finds missing ledger rows
or a partially populated ledger, the API attempts a scoped repair from
`LiteLLM_SpendLogs` before returning the response. Monthly CavadaLabs billing
generation uses the same scoped repair when the selected Company's ledger is
empty or incomplete for the requested billing period, so a report is not
generated from a partial ledger if attributable LiteLLM spend can be resolved
first. The repair uses the same authoritative context rules as the migrations:

- explicit CavadaLabs Company/Project metadata on the spend log;
- CavadaLabs Company/Project metadata on `LiteLLM_VerificationToken` when the
  spend row only carries the hashed `api_key`;
- CavadaLabs Company/Project metadata on `LiteLLM_DeletedVerificationToken`
  when historical spend references a key that has since been deleted;
- active or deleted key `team_id` ->
  `CavadaLabs_ProjectTable.litellm_team_id` when the spend row itself lost the
  team field;
- internal `team_id` -> `CavadaLabs_ProjectTable.litellm_team_id`;
- internal `organization_id` -> `CavadaLabs_CompanyTable.litellm_organization_id`.

The repair only runs for an explicitly selected Company or Project scope. Billing
repair is scoped to the report Company and month. It does not scan or attach
global legacy spend without a resolvable Company and Project. Scoped repair is
idempotent because the ledger write uses the unique `request_id` with duplicate
skipping. If duplicate rows are skipped, the repair response can report
`attempted=true` with `repaired=false`, which means the operation was safe but no
new ledger rows were inserted for that scope. The runtime repair path validates
the Project's owning Company before writing, matching the migration behavior:
explicit Company/Project metadata that conflicts with the `CavadaLabs_Project`
row is skipped instead of being attached to the wrong tenant. The migrations
below are still the recommended full historical backfill path because they cover
all attributable historical rows in one operational step.

## Migration

The metadata/compat backfill migration is:

```text
litellm-proxy-extras/litellm_proxy_extras/migrations/20260515123000_backfill_cavadalabs_request_ledger_from_spend_logs/migration.sql
```

The key-metadata backfill migration is:

```text
litellm-proxy-extras/litellm_proxy_extras/migrations/20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata/migration.sql
```

The metadata key-hash backfill migration is:

```text
litellm-proxy-extras/litellm_proxy_extras/migrations/20260515161000_backfill_cavadalabs_request_ledger_from_metadata_key_hash/migration.sql
```

The spend-log index migration used by scoped repair and diagnostics is:

```text
litellm-proxy-extras/litellm_proxy_extras/migrations/20260515122000_add_cavadalabs_usage_spend_log_indexes/migration.sql
```

It copies legacy spend rows into `CavadaLabs_RequestLedgerTable` when both
Company and Project can be resolved to existing CavadaLabs rows from metadata or
from the internal LiteLLM compatibility mapping:

- `LiteLLM_SpendLogs.api_key` -> `LiteLLM_VerificationToken.token`, then
  CavadaLabs metadata on the key
- `LiteLLM_SpendLogs.api_key` -> `LiteLLM_DeletedVerificationToken.token`, then
  CavadaLabs metadata preserved in the deleted-key audit row
- `LiteLLM_SpendLogs.metadata.user_api_key_hash`,
  `metadata.api_key_hash`, or the same keys under `spend_logs_metadata` /
  `cavadalabs` -> active/deleted key metadata
- `LiteLLM_SpendLogs.api_key` -> active/deleted key `team_id`, then
  `CavadaLabs_ProjectTable.litellm_team_id`
- `LiteLLM_SpendLogs.team_id` -> `CavadaLabs_ProjectTable.litellm_team_id`
- `LiteLLM_SpendLogs.organization_id` -> `CavadaLabs_CompanyTable.litellm_organization_id`

Rows without a resolvable Project and Company are left out intentionally so an
unscoped legacy row never becomes visible under the wrong tenant. Rows with a
conflicting Company/Project compatibility mapping are also skipped. The
migration is idempotent because `request_id` is unique on the ledger and
duplicate rows use `ON CONFLICT ("request_id") DO NOTHING`.
Rows with empty or null metadata can still be backfilled when their
`team_id` maps to a CavadaLabs Project.
Rows with explicit Project metadata that does not match an existing
`CavadaLabs_ProjectTable` row are skipped; the Project is the authoritative
tenant boundary for CavadaLabs usage.

## Apply

Run from the repository root with the production `DATABASE_URL`:

```bash
DATABASE_URL='postgresql://USER:PASSWORD@HOST:PORT/DB' uv run prisma migrate deploy --schema litellm-proxy-extras/litellm_proxy_extras/schema.prisma
```

Use a project-compatible `uv` version for the command. If `uv run` exits before
Prisma with a version mismatch, update `uv` to the version required by the
repository or run the command from the deployment image that already has the
matching toolchain.

The LiteLLM proxy startup also runs Prisma migrations in normal deployments, but
the command above is the explicit operational path when usage needs to be
checked before restart.

Prisma does not rerun migrations that are already recorded as applied. If the
historical backfill migrations ran before a Company/Project mapping or key
metadata was fixed, use the diagnostics and selected daily activity/billing
endpoints below to trigger the scoped repair for the affected Company or Project
date range.

## Scoped Repair API

When diagnostics return `recommended_action=run_scoped_backfill`, an admin can
repair the affected Company or Project date range without running a global
historical migration. The repair endpoint uses the same scoped filters as daily
activity and billing, writes idempotently with duplicate skipping, and never
attaches spend that cannot be resolved to both a CavadaLabs Company and Project.

Repair a Company scope:

```bash
curl -sS \
  -X POST \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  "$LITELLM_BASE_URL/cavadalabs/companies/usage/repair" \
  -d '{
    "company_ids": ["<company_id>"],
    "start_date": "2026-05-01",
    "end_date": "2026-05-31"
  }'
```

Repair a Project scope:

```bash
curl -sS \
  -X POST \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  "$LITELLM_BASE_URL/cavadalabs/projects/usage/repair" \
  -d '{
    "project_ids": ["<project_id>"],
    "start_date": "2026-05-01",
    "end_date": "2026-05-31"
  }'
```

The response includes `attempted`, `repaired`, `processed_spend_logs`,
`batches`, and fresh diagnostics for the repaired scope. Non-admin users cannot
run repair; they can only see usage within their Company/Project visibility.

## Verify

The API can distinguish an empty or partial CavadaLabs ledger from attributable
`LiteLLM_SpendLogs` that still need scoped backfill:

```bash
curl -sS \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  "$LITELLM_BASE_URL/cavadalabs/companies/usage/diagnostics?company_ids=<company_id>&start_date=2026-05-01&end_date=2026-05-31"
```

```bash
curl -sS \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  "$LITELLM_BASE_URL/cavadalabs/projects/usage/diagnostics?project_ids=<project_id>&start_date=2026-05-01&end_date=2026-05-31"
```

Diagnostic statuses:

- `visible`: matching rows already exist in `CavadaLabs_RequestLedgerTable`.
- `scoped_backfill_available`: attributable spend exists in `LiteLLM_SpendLogs`,
  but the CavadaLabs ledger is empty or partial for the selected scope/date
  range. The selected daily activity or monthly billing call will attempt a
  scoped repair automatically; run the migrations for full historical coverage.
- `missing_compatibility_mapping`: legacy spend cannot be mapped through the
  internal LiteLLM Team/Organization compatibility fields or CavadaLabs key
  metadata.
- `no_attributable_spend`: no Company/Project-attributable spend exists for the
  selected scope/date range.

## UI Behavior

The CavadaLabs usage panel intentionally does not treat every empty table as
`no data`.

- If ledger rows exist for the selected Company/Project/date range, the panel
  shows spend, requests, tokens, and errors from the CavadaLabs ledger.
- If the usage schema or generated Prisma delegate is missing, the panel shows
  `CavadaLabs usage schema is not ready`, lists the missing schema items, and
  displays the `prisma migrate deploy` command. Scoped repair is not offered
  until the schema is present.
- Diagnostics and scoped repair also preflight the active and deleted virtual
  key delegates used for Company/Project key-metadata attribution. If either
  delegate is missing because the migration/client is stale, the product reports
  `schema_status=missing_schema` instead of treating historical usage as empty.
- If diagnostics return `scoped_backfill_available`, the panel shows
  `usage can be repaired`, displays the attributable SpendLogs count and ledger
  gap, and offers Preview/Run scoped backfill for the selected Company/Project
  and filters.
- If diagnostics return `no_attributable_spend`, the panel shows a real no-data
  state: no ledger rows, SpendLogs metadata, key metadata, or internal
  compatibility mapping matched the selected Company/Project scope.
- If a user is unauthorized or the Project/Company scope is invalid, the panel
  shows the structured backend error instead of replacing it with an empty
  usage table.

Diagnostic items also include:

- `ledger_gap`: how many attributable `SpendLogs` rows are not represented in
  the CavadaLabs ledger for that scope/date range.
- `recommended_action`: `run_scoped_backfill`, `fix_compatibility_mapping`, or
  `none`.
- `scoped_backfill_available`: boolean shortcut for operational checks.

The diagnostics and repair responses also include:

- `readiness_checks`: structured admin checks for the schema, ledger rows,
  SpendLogs attribution, scoped repair state, and restrictive filters/date
  ranges. Each check includes a stable `code`, `status`, `message`,
  `recommended_action`, and scoped details.
- `migration_names`: the complete CavadaLabs usage migration bundle that should
  be present after `prisma migrate deploy`, including the SpendLogs repair
  indexes, metadata/compat ledger backfill, and key-metadata/deleted-key
  backfill, including legacy SpendLogs whose key hash is present only in
  metadata.
- `migration_plan`: the same migrations with their operational purpose, so an
  operator can tell whether missing usage is likely caused by missing indexes,
  missing historical metadata backfill, missing key-metadata backfill, or
  metadata-only key-hash backfill.
- `migration_name`: the latest migration in that bundle, retained for backward
  compatibility with older clients that expected a single string.

Confirm the migration is present:

```bash
DATABASE_URL='postgresql://USER:PASSWORD@HOST:PORT/DB' uv run prisma migrate status --schema litellm-proxy-extras/litellm_proxy_extras/schema.prisma
```

Deploy any missing migrations:

```bash
DATABASE_URL='postgresql://USER:PASSWORD@HOST:PORT/DB' uv run prisma migrate deploy --schema litellm-proxy-extras/litellm_proxy_extras/schema.prisma
```

Confirm the CavadaLabs usage migration bundle in Prisma's migration ledger:

```sql
SELECT migration_name, finished_at, rolled_back_at
FROM "_prisma_migrations"
WHERE migration_name IN (
  '20260514120000_add_cavadalabs_dispatcher_tables',
  '20260515120000_add_cavadalabs_litellm_membership_mappings',
  '20260515122000_add_cavadalabs_usage_spend_log_indexes',
  '20260515123000_backfill_cavadalabs_request_ledger_from_spend_logs',
  '20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata',
  '20260515150000_add_cavadalabs_native_memberships',
  '20260515161000_backfill_cavadalabs_request_ledger_from_metadata_key_hash'
)
ORDER BY migration_name;
```

Confirm the critical runtime tables, columns, indexes, and FKs exist:

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
    'CavadaLabs_CompanyTable',
    'CavadaLabs_ProjectTable',
    'CavadaLabs_RequestLedgerTable',
    'CavadaLabs_CompanyMemberTable',
    'CavadaLabs_ProjectMemberTable',
    'LiteLLM_SpendLogs',
    'LiteLLM_VerificationToken',
    'LiteLLM_DeletedVerificationToken'
  )
ORDER BY table_name;
```

```sql
SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND (
    table_name = 'CavadaLabs_RequestLedgerTable'
    OR (table_name = 'CavadaLabs_CompanyTable' AND column_name = 'litellm_organization_id')
    OR (table_name = 'CavadaLabs_ProjectTable' AND column_name = 'litellm_team_id')
    OR table_name IN ('CavadaLabs_CompanyMemberTable', 'CavadaLabs_ProjectMemberTable')
  )
ORDER BY table_name, ordinal_position;
```

```sql
SELECT tablename, indexname
FROM pg_indexes
WHERE schemaname = 'public'
  AND indexname IN (
    'CavadaLabs_RequestLedgerTable_request_id_key',
    'CavadaLabs_RequestLedgerTable_company_id_created_at_idx',
    'CavadaLabs_RequestLedgerTable_project_id_created_at_idx',
    'CavadaLabs_RequestLedgerTable_provider_model_idx',
    'CavadaLabs_CompanyTable_litellm_organization_id_key',
    'CavadaLabs_ProjectTable_litellm_team_id_key',
    'CavadaLabs_CompanyMemberTable_company_id_user_id_key',
    'CavadaLabs_ProjectMemberTable_project_id_user_id_key',
    'LiteLLM_SpendLogs_api_key_startTime_idx',
    'LiteLLM_SpendLogs_team_id_startTime_idx',
    'LiteLLM_SpendLogs_organization_id_startTime_idx',
    'LiteLLM_SpendLogs_metadata_gin_idx'
  )
ORDER BY tablename, indexname;
```

```sql
SELECT conrelid::regclass AS table_name, conname, confrelid::regclass AS references_table
FROM pg_constraint
WHERE conname IN (
  'CavadaLabs_ProjectTable_company_id_fkey',
  'CavadaLabs_CompanyTable_litellm_organization_id_fkey',
  'CavadaLabs_ProjectTable_litellm_team_id_fkey',
  'CavadaLabs_CompanyMemberTable_company_id_fkey',
  'CavadaLabs_CompanyMemberTable_user_id_fkey',
  'CavadaLabs_ProjectMemberTable_project_id_fkey',
  'CavadaLabs_ProjectMemberTable_user_id_fkey'
)
ORDER BY table_name::text, conname;
```

## Live Smoke Test

Use this when a specific Company/Project still shows empty usage after a deploy.
Replace the placeholders with the affected production values; do not reset or
drop data.

1. Confirm migrations are applied:

```bash
DATABASE_URL='postgresql://USER:PASSWORD@HOST:PORT/DB' uv run prisma migrate status --schema litellm-proxy-extras/litellm_proxy_extras/schema.prisma
```

2. Confirm the Cavada key context is present on the virtual key:

```sql
SELECT token, team_id, organization_id,
       metadata ->> 'cavadalabs_company_id' AS company_id,
       metadata ->> 'cavadalabs_project_id' AS project_id,
       metadata -> 'spend_logs_metadata' AS spend_logs_metadata
FROM "LiteLLM_VerificationToken"
WHERE token = '<hashed_api_key>';
```

3. Generate one real request through LiteLLM using the affected key:

```bash
curl -sS "$LITELLM_BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $CAVADALABS_SERVER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "<allowed-model-alias>",
    "messages": [{"role": "user", "content": "CavadaLabs usage smoke test"}],
    "max_tokens": 8
  }'
```

4. Wait for the LiteLLM spend-log queue to flush, then verify the ledger:

```sql
SELECT request_id, company_id, project_id, api_key_hash, provider, model,
       spend, total_tokens, status, created_at
FROM "CavadaLabs_RequestLedgerTable"
WHERE company_id = '<company_id>'
  AND project_id = '<project_id>'
ORDER BY created_at DESC
LIMIT 10;
```

5. Verify the product API reads the same Company/Project scope:

```bash
curl -sS \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  "$LITELLM_BASE_URL/cavadalabs/companies/daily/activity?company_ids=<company_id>&start_date=2026-05-01&end_date=2026-05-31&page=1&page_size=30"
```

```bash
curl -sS \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  "$LITELLM_BASE_URL/cavadalabs/projects/daily/activity?project_ids=<project_id>&start_date=2026-05-01&end_date=2026-05-31&page=1&page_size=30"
```

Confirm ledger rows exist for the affected scope:

```sql
SELECT COUNT(*) AS ledger_rows,
       COALESCE(SUM("spend"), 0) AS ledger_spend,
       COALESCE(SUM("total_tokens"), 0) AS ledger_tokens,
       MIN("created_at") AS first_seen,
       MAX("created_at") AS last_seen
FROM "CavadaLabs_RequestLedgerTable"
WHERE "company_id" = '<company_id>'
  AND "project_id" = '<project_id>'
  AND "created_at" >= TIMESTAMPTZ '2026-05-01 00:00:00+00'
  AND "created_at" <  TIMESTAMPTZ '2026-06-01 00:00:00+00';
```

If this returns `0`, check whether the source spend rows contain the required
metadata:

```sql
SELECT "request_id", "metadata"
FROM "LiteLLM_SpendLogs"
WHERE "metadata"::text LIKE '%cavadalabs_company_id%'
   OR "metadata"::text LIKE '%cavadalabs_project_id%'
ORDER BY "startTime" DESC
LIMIT 20;
```

Find spend rows that are attributable through CavadaLabs key metadata but have
not reached the request ledger:

```sql
WITH raw_key_context AS (
  SELECT token, metadata, 0 AS source_priority FROM "LiteLLM_VerificationToken"
  UNION ALL
  SELECT token, metadata, 1 AS source_priority FROM "LiteLLM_DeletedVerificationToken"
),
key_context AS (
  SELECT DISTINCT ON (token)
         token,
         COALESCE(
           metadata ->> 'cavadalabs_company_id',
           metadata -> 'cavadalabs' ->> 'company_id',
           metadata -> 'spend_logs_metadata' ->> 'cavadalabs_company_id'
         ) AS company_id,
         COALESCE(
           metadata ->> 'cavadalabs_project_id',
           metadata -> 'cavadalabs' ->> 'project_id',
           metadata -> 'spend_logs_metadata' ->> 'cavadalabs_project_id'
         ) AS project_id
  FROM raw_key_context
  WHERE token IS NOT NULL AND token <> ''
  ORDER BY token, source_priority
),
spend_logs_with_key AS (
  SELECT s.*,
         COALESCE(
           NULLIF(s."api_key", ''),
           NULLIF(s."metadata" ->> 'user_api_key_hash', ''),
           NULLIF(s."metadata" ->> 'api_key_hash', ''),
           NULLIF(s."metadata" -> 'cavadalabs' ->> 'user_api_key_hash', ''),
           NULLIF(s."metadata" -> 'cavadalabs' ->> 'api_key_hash', ''),
           NULLIF(s."metadata" -> 'spend_logs_metadata' ->> 'user_api_key_hash', ''),
           NULLIF(s."metadata" -> 'spend_logs_metadata' ->> 'api_key_hash', '')
         ) AS spend_api_key_hash
  FROM "LiteLLM_SpendLogs" s
)
SELECT s."request_id", s."startTime", s.spend_api_key_hash,
       s."api_key", s."team_id", s."organization_id",
       k.company_id, k.project_id, l."request_id" AS ledger_request_id
FROM spend_logs_with_key s
JOIN key_context k ON k.token = s.spend_api_key_hash
LEFT JOIN "CavadaLabs_RequestLedgerTable" l ON l."request_id" = s."request_id"
WHERE k.company_id = '<company_id>'
  AND k.project_id = '<project_id>'
  AND s."startTime" >= TIMESTAMPTZ '2026-05-01 00:00:00+00'
  AND s."startTime" <  TIMESTAMPTZ '2026-06-01 00:00:00+00'
  AND l."request_id" IS NULL
ORDER BY s."startTime" DESC
LIMIT 50;
```

Find spend rows that are attributable only through internal compatibility
mapping:

```sql
SELECT s."request_id", s."startTime", s."team_id", s."organization_id",
       p."project_id", p."company_id", c."litellm_organization_id",
       l."request_id" AS ledger_request_id
FROM "LiteLLM_SpendLogs" s
JOIN "CavadaLabs_ProjectTable" p
  ON p."litellm_team_id" = NULLIF(s."team_id", '')
LEFT JOIN "CavadaLabs_CompanyTable" c
  ON c."company_id" = p."company_id"
LEFT JOIN "CavadaLabs_RequestLedgerTable" l
  ON l."request_id" = s."request_id"
WHERE p."company_id" = '<company_id>'
  AND p."project_id" = '<project_id>'
  AND s."startTime" >= TIMESTAMPTZ '2026-05-01 00:00:00+00'
  AND s."startTime" <  TIMESTAMPTZ '2026-06-01 00:00:00+00'
ORDER BY s."startTime" DESC
LIMIT 50;
```

Find likely unattributable spend rows for the same date window:

```sql
SELECT s."request_id", s."startTime", s."api_key", s."team_id", s."organization_id",
       s."metadata"
FROM "LiteLLM_SpendLogs" s
LEFT JOIN "CavadaLabs_RequestLedgerTable" l
  ON l."request_id" = s."request_id"
LEFT JOIN "CavadaLabs_ProjectTable" p
  ON p."litellm_team_id" = NULLIF(s."team_id", '')
WHERE s."startTime" >= TIMESTAMPTZ '2026-05-01 00:00:00+00'
  AND s."startTime" <  TIMESTAMPTZ '2026-06-01 00:00:00+00'
  AND l."request_id" IS NULL
  AND p."project_id" IS NULL
  AND COALESCE(s."metadata"::text, '') NOT LIKE '%cavadalabs_project_id%'
ORDER BY s."startTime" DESC
LIMIT 50;
```

Rows without CavadaLabs metadata and without a LiteLLM Team mapped to a
CavadaLabs Project are legacy-unattributed spend. They remain visible through
standard LiteLLM usage surfaces, but not through CavadaLabs Company/Project usage
because there is no authoritative Project context to attach.

If diagnostics or scoped repair are slow on a large historical
`LiteLLM_SpendLogs` table, confirm that
`20260515122000_add_cavadalabs_usage_spend_log_indexes` has been applied.
Scoped repair depends on `api_key`, `team_id`, `organization_id`, model, date and
metadata-path filters. The index migration makes that operational path safe
without changing tenant attribution semantics.
