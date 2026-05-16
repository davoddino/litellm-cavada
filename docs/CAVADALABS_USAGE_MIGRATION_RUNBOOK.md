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
range. They do not expose LiteLLM Organization or Team as product filters. If the
selected ledger slice is empty or appears partial, the endpoint may trigger a
scoped repair from `LiteLLM_SpendLogs`, but that repair is a recovery path for
historical or previously unattributed data. New requests should be visible from
the ledger-native read path as soon as the standard LiteLLM spend-log queue has
processed the batch.

Reading ledger rows only requires the CavadaLabs request-ledger schema. The
active/deleted virtual-key delegates are required for diagnostics and scoped
repair from legacy SpendLogs, but missing key-backfill schema must not hide usage
that is already present in `CavadaLabs_RequestLedgerTable`.

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

- `migration_names`: the complete CavadaLabs usage migration bundle that should
  be present after `prisma migrate deploy`, including the SpendLogs repair
  indexes, metadata/compat ledger backfill, and key-metadata/deleted-key
  backfill.
- `migration_plan`: the same migrations with their operational purpose, so an
  operator can tell whether missing usage is likely caused by missing indexes,
  missing historical metadata backfill, or missing key-metadata backfill.
- `migration_name`: the latest migration in that bundle, retained for backward
  compatibility with older clients that expected a single string.

Confirm the migration is present:

```bash
DATABASE_URL='postgresql://USER:PASSWORD@HOST:PORT/DB' uv run prisma migrate status --schema litellm-proxy-extras/litellm_proxy_extras/schema.prisma
```

Confirm ledger rows exist for the affected scope:

```sql
SELECT COUNT(*)
FROM "CavadaLabs_RequestLedgerTable"
WHERE "company_id" = '<company_id>'
  AND "project_id" = '<project_id>';
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
