# CavadaLabs Operations

This file is the current operator runbook for CavadaLabs work on this branch.
Update commands in place as the implementation changes. Do not append a command history.

## Current State

- Branch reset baseline: `origin/litellm_internal_staging`.
- Current local branch: `cavadalabs_integration_of_new_features`.
- Current local upstream: `origin/litellm_internal_staging`.
- The old remote branch `origin/cavadalabs_integration_of_new_features` still exists remotely unless explicitly force-updated later.
- CavadaLabs feasibility/spec input: `DISPATCHER_FEASIBILITY.md` reviewed.
- Active implementation slice: Companies and Projects are the canonical tenant concepts in Users, Teams, Virtual Keys, Usage/Billing, and tenant management. Tenant management is product-facing as Companies; LiteLLM Organization routes/fields remain compatibility internals.
- Approved behavior: Product UI and new request filters use `company_id`/`company_ids` and `project_id`/`project_ids`. Existing LiteLLM `organization_id` fields, tables, routes, and helper names remain only as compatibility internals. Provider-specific organization parameters, such as OpenAI organization IDs, remain unchanged.
- Product Organization removal slice: Server API Key create/edit/detail/table surfaces must show Company and Project as tenant concepts. `organization_id` and `org_id` may appear only as compatibility fallback fields inside code paths that read existing LiteLLM records.
- Virtual Keys Company/Project slice: `/key/generate`, `/key/update`, `/key/list`, and key detail responses use `company_id`/`company_name` plus `project_id`/`project_name` as product contract fields. Key create/edit/list UI renders Company and Project, submits `company_id`/`project_id`, and keeps `organization_id` only as a validated legacy alias or DB compatibility field.
- Product Organization removal slice: Users and Teams create/edit/detail/list surfaces must show Company and Project as tenant concepts. Team create/list UI sends `company_id` and `project_id` filters; `organization_id` may remain inside LiteLLM compatibility fields and helper names only.
- Users/CreateUser Company/Project slice: user create, edit, detail, and list surfaces use `company_ids` and `project_ids` in product payloads/filters. Project selectors are filtered by selected Company and stale Project selections are pruned client-side before submit; backend remains authoritative for cross-Company Project validation. `/user/list` keeps `organization_ids` as a hidden legacy alias while documenting `company_ids` as the product filter.
- User management CreateUser Company/Project integration result: create-user UI renders Company and Project only, submits `company_ids`/`project_ids`, and never submits product tenant `organization_id` aliases. Backend create/update request models accept product `company_id` and `project_id` convenience aliases, map them to existing LiteLLM compatibility fields, and reject conflicting legacy `organization_id` input.
- User management edit Company/Project integration result: edit-user UI initializes and submits `company_ids`/`project_ids`, strips legacy Organization tenant aliases before submit, and renders Company/Project labels. Backend update accepts `company_id`/`project_id` aliases, rejects conflicting `organization_id`, and strips product/legacy tenant aliases before user-row persistence while updating membership tables through existing helpers.
- Users list/detail Company/Project surface result: Users list filters, table columns, and user detail membership cards render Company/Project tenant concepts. The list filter sends `company_ids`/`project_ids` through existing networking, and detail display falls back from names to product IDs when names are unavailable; `organization_id` remains only the LiteLLM membership compatibility column.
- Product Companies management slice: Dashboard route/nav/list/detail/create/edit use `/companies` and `/company/*` endpoints with `company_id`/`company_name`. Existing `/organization/*` endpoints remain compatibility routes hidden from product OpenAPI schema; persistence remains LiteLLM `LiteLLM_OrganizationTable`.
- RBAC behavior: Project members may list/read project-scoped Users, Teams, and Server API Keys where the route allows it. Create/update/write paths require proxy admin, Company admin, Project admin, or an explicit existing route permission such as `/key/generate` or `/key/update`.
- Usage/Billing visibility behavior: Company Usage uses `/company/daily/activity`; Project Usage uses `/project/daily/activity` with optional `company_id`/`company_ids` scoping. Company admins can view Project usage for Projects whose backing team belongs to their Company. Project/team members remain scoped by their backing team permissions and API-key ownership rules.
- Current Usage/Billing Company/Project visibility end-to-end result: no additional runtime source or schema change is required. Runtime spend logging already materializes Company on `LiteLLM_SpendLogs.organization_id` as the internal compatibility column and Project on `LiteLLM_SpendLogs.project_id`; daily aggregation writes `LiteLLM_DailyOrganizationSpend` and required `LiteLLM_DailyProjectSpend.project_id`; the Usage/Logs UI sends product `company_id`/`company_ids` and `project_id`/`project_ids`. Project Usage filters use Company option labels from `company_name` and values from `company_id`, with `organization_id` only as an internal fallback for legacy Company rows. Request-log networking normalizes hidden legacy `organization_id`/`org_id` filter aliases to product `company_id` only when they agree, and rejects conflicts before submit. The compatibility `EntityUsage` entity type `organization` calls the Company daily activity API so rendered Company usage does not depend on `/organization/daily/activity`. Contract tests cover a virtual-key-attributed spend row through `/spend/logs/ui`, `/company/daily/activity`, and `/project/daily/activity`; raw `/spend/logs/ui` SQL filters; Project daily activity Company filters; and UI filter payloads so regressions do not silently return unscoped data. `/project/daily/activity` accepts hidden LiteLLM `organization_id`/`organization_ids` compatibility aliases only when they match the product Company filters.
- Current Usage/Logs authorization hardening result: `/spend/logs/ui` and `/spend/logs/v2` verify requested Project ownership against the requested Company for non-proxy admins before dropping user-level scoping. Company daily activity is scoped through existing Company read membership rows (`org_admin`, `internal_user`, `internal_user_viewer`) with proxy admin override; Project daily activity remains scoped through Project backing teams plus Company admin memberships.
- Teams Company/Project completion result: Team create/update/list/detail runtime already uses Company as the product alias for the existing LiteLLM team `organization_id` and derives Project visibility from existing `LiteLLM_ProjectTable.team_id`. Current verification covers backend response enrichment plus Team detail UI Company/Projects rendering.
- Company/Project access-control hardening result: Project create/update/info/list now authorizes Company admins through `LiteLLM_OrganizationMembership.user_role = org_admin` for the Project backing team's Company. Project daily usage/spend, Users, Teams, and Server API Keys already had Company/Project-aware authorization in this branch; this slice closes the Project management visibility/write gap used by Project selectors and detail pages.
- Product-facing Organization surface cleanup result: Company management API docs/errors use Company wording. Existing `organization_id` fields, hidden `/organization/*` routes, LiteLLM Organization tables, helper names, and provider-specific organization parameters remain compatibility/internal only.
- Runtime UI Organization surface cleanup result: audited Companies, Virtual Keys, key create/edit, Users, Teams, Projects, Usage, and Billing runtime components for rendered `Organization`/`Organizations` tenant copy. Those surfaces expose Company/Project wording; the remaining rendered model-provider parameter is explicitly labeled `Provider Organization ID`.
- Current Virtual Keys/API keys Company+Project surface result: persisted key tenant fields already exist as `LiteLLM_VerificationToken.organization_id` and `LiteLLM_VerificationToken.project_id`. Product requests and UI filters use `company_id` and `project_id`; the create-key and edit-key UIs strip legacy Organization tenant aliases before submit, the list/table hook and Python key client map any legacy `organization_id`/`organizationID` option to a `company_id` query parameter, and key create/update/list/detail responses expose `company_id`/`company_name` plus `project_id`/`project_name` where available. `/key/list` exposes `company_id` and `project_id` in OpenAPI while keeping `organization_id` hidden as a validated compatibility alias. `organization_id` remains only the LiteLLM internal Company column and legacy API alias.
- Current Virtual Keys canonical Company/Project delete result: key delete/regenerate authorization now treats Company admin membership and Project backing-team admin/explicit `/key/delete` permission as product write authority for Company/Project-scoped keys. The dashboard delete client sends only key identifiers to `/key/delete`; tenant enforcement remains server-side and does not expose `organization_id` in product payloads.
- Current Virtual Keys product integration cleanup result: key create/edit/table/detail runtime UI has no product-facing Organization tenant selector, column, or label. Backend key request/response schemas keep `organization_id` only as an internal/deprecated compatibility alias for `company_id`; product clients should use `company_id` and `project_id`.
- Current Server API Keys end-to-end Company/Project canonicalization result: key create/edit/list/detail product contracts expose Company/Project fields. `organization_id` and `org_id` are internal/deprecated compatibility aliases for the existing LiteLLM Company storage column and must not be sent by dashboard product flows.
- Current Virtual Keys create/edit Company+Project result: key create/edit forms render Company and Project tenant controls and submit `company_id`/`project_id`. The existing dashboard networking layer now sanitizes `/key/generate`, `/key/service-account/generate`, and `/key/update` payloads so legacy `organization_id`, `org_id`, `organization_ids`, and `organizations` are not sent from product key flows; scalar legacy aliases are mapped to `company_id` only when they agree.
- Current Virtual Keys table Project filter result: the Virtual Keys table uses the existing Project list contract for Project filter options, not only Projects present on the current key page. The table still sends `project_id` and `company_id` filters to `/key/list`, so an operator can drill into a Company/Project even when the matching key is outside the first paginated result set.
- Current Virtual Keys product UI cleanup result: the team-scoped Virtual Keys table now also renders Project context and exposes a Project filter. It derives Project filter options from existing key list response fields (`project_id`, `project_name`, `project_alias`) and sends `projectID` through the existing `/key/list` client contract; Company display remains product-facing while `organization_id` is only the LiteLLM compatibility fallback.
- Current Usage/Logs UI Company/Project result: Usage and request-log filters render Company/Project tenant concepts. The existing Company dropdown component still uses the LiteLLM Organization data shape internally, but product display/search prefers `company_name` and `company_id`; `organization_id` is only the compatibility value used to call existing Company-backed endpoints.
- Current frontend visible usage proof result: dashboard request logs send `/spend/logs/ui` filters as `company_id` and `project_id`; Company Usage calls `/company/daily/activity` with `company_ids`; Project Usage calls `/project/daily/activity` with `project_ids` and optional `company_ids`. Changing the Project Usage Company filter remounts the Project usage panel and drops stale Project selections before the next daily activity fetch.
- Current Usage/Billing Company+Project correctness result: `/spend/logs/ui`, `/spend/logs/v2`, and session log responses accept product `company_id`/`project_id` filters, reject conflicting `organization_id` aliases, authorize Company/Project scope server-side, and enrich returned rows with `company_name`/`project_name` from existing Company/Project tables when available. Request-log UI columns and details display those names with ID fallback.
- Current Company/Project usage visibility result: product OpenAPI surfaces for `/spend/logs/v2` and `/company/daily/activity` expose Company/Project query fields and hide LiteLLM Organization compatibility aliases. The dashboard Usage view uses Company and Project selectors/labels; export options map any legacy `organization` entity type to Company wording.
- Current Usage/Logs real DB/runtime visibility result: no code or schema change is required for this slice. Runtime requests with a Company/Project-scoped server API key persist Company on `LiteLLM_SpendLogs.organization_id` and Project on `LiteLLM_SpendLogs.project_id`; daily usage reads `LiteLLM_DailyOrganizationSpend.organization_id` and required `LiteLLM_DailyProjectSpend.project_id`. Operators should diagnose missing selected Company/Project usage by verifying the migrations and validation queries below before changing runtime code.
- Current Teams UI Company/Project result: Teams list, filters, create, edit, and detail surfaces render Company/Project tenant concepts. Team filters and create/edit forms submit product `company_id`/`project_id` values and prefer `company_name`/`company_id` from the Company hook; the UI may still hold `organization_id` in internal state because LiteLLM team rows persist Company on `LiteLLM_TeamTable.organization_id`.
- Current Teams management Company/Project result: dashboard team list filters send `company_id` and `project_id`; team create/update networking accepts legacy `organization_id`/`org_id` only as compatibility aliases, rejects conflicts, and submits `company_id` without Organization tenant fields. Team create/update request schemas expose `company_id` as the product field and mark `organization_id` internal/deprecated. Project context in Team surfaces remains read-only and derived from existing Project backing teams rather than written through Team create/update.
- Current Users and Teams Company/Project management contract result: no runtime or schema change is required for this slice. User create/edit/list already uses product `company_ids`/`project_ids`, maps Companies to `LiteLLM_OrganizationMembership`, maps Projects to backing team membership through `LiteLLM_ProjectTable.team_id`, and rejects conflicting legacy Organization aliases. Team create/edit/list/detail already uses product `company_id`/`project_id`, stores Company on the existing `LiteLLM_TeamTable.organization_id` compatibility column, derives Project context from `LiteLLM_ProjectTable.team_id`, and hides `organization_id` from product OpenAPI list filters.
- Current remaining product-facing Organization cleanup result: Deleted Teams is a Teams product surface and now renders the tenant column as Company, preferring `company_name`/`company_id` and using `organization_id` only as the internal LiteLLM compatibility fallback for legacy rows.
- Current Projects product-surface result: Projects are shown and edited as Company-scoped CavadaLabs Projects. `/project/list` accepts product `company_id`/`company_ids` filters, create/update accepts product `company_id` and validates it against the selected Project backing team, and dashboard list/detail/create/edit surfaces show Company context while `team_id` remains the internal LiteLLM backing link.
- Current Company/Project RBAC membership result: Project write authorization resolves Project admin from the backing team's `members_with_roles` admin role, keeps the legacy `admins` fallback, and resolves Company admin through `LiteLLM_OrganizationMembership.user_role = org_admin`. A Project member without the admin role cannot create/update Projects through the Project management write path.
- Current runtime request attribution result: virtual key auth accepts product `company_id` and maps it to the internal `org_id` compatibility field used by spend tracking. Runtime auth also derives Company from a key's backing team `organization_id` when the key itself has no Company, and derives Project from `LiteLLM_ProjectTable.team_id` only when exactly one Project owns that team. Runtime request metadata for chat, completion, embeddings, queued chat, browser/agent keys using the same auth object, and failure spend logs writes `user_api_key_org_id` from Company and `user_api_key_project_id`/`user_api_key_project_alias` from Project. Spend logging persists those as `LiteLLM_SpendLogs.organization_id` plus `LiteLLM_SpendLogs.project_id`; daily Company and Project aggregation receive the same values.
- Current end-to-end Company/Project usage visibility contract result: a virtual-key-attributed request is visible through `/spend/logs/ui`, `/company/daily/activity`, and `/project/daily/activity` when filtered by product `company_id`, `project_id`, and the key hash. The regression uses existing endpoint code and daily spend helpers; no frontend contract or DB shape change is introduced.
- Current Company/Project usage authorization contract result: non-global users must pass existing Company read membership, Company admin, or Project backing-team permission checks before product usage endpoints remove user-level scoping. `/spend/logs/ui` is covered for allowed Company/Project scope, denied outside Company, denied Project outside requested Company, and denied Project without route permission. `/company/daily/activity` is covered for Company admin/member/viewer allow, cross-Company deny, and proxy admin override through `company_id`; `/project/daily/activity` is covered for Project backing-team member scope, Company admin access to Projects in their Company, and denial when the requested Project is outside that Company scope.
- Current Usage/Billing Company+Project visibility correction result: `/spend/logs/ui` and `/spend/logs/v2` treat `project_id` as the primary authorization scope when both product `company_id` and `project_id` filters are present. A Project member with the existing `/spend/logs` route permission can view rows for that Project when the requested Company matches the Project backing team's Company; Company-only filters still require Company admin.
- Current user create/edit Company/Project assignment result: create and edit user forms render Company/Project tenant fields, prefer product `company_name`/`company_id` display values from the existing Company hook, submit `company_ids`/`project_ids`, and strip legacy `organization_id`/`organization_ids`/`organizations` aliases before networking. The Users table Company filter also emits product `company_id` and clears stale Project filters. Backend request models continue to accept `company_id` and `project_id` aliases while rejecting conflicting legacy aliases.
- Current Users management Company/Project membership result: dashboard `/user/new` and `/user/update` networking normalizes product scalar aliases into `company_ids` and `project_ids`, rejects conflicting legacy Organization aliases before sending the request, and strips `organization_id`, `organization_ids`, `organizations`, `company_id`, and `project_id` from product payloads. Backend membership writes continue to map Companies to `LiteLLM_OrganizationMembership` and Projects to existing Project backing team membership.
- Current Users API Organization residue cleanup result: `/user/new`, `/user/update`, and `/user/list` product schemas expose Company/Project fields. `organization_id`, `organization_ids`, and `organizations` remain accepted only as internal/deprecated LiteLLM compatibility aliases with conflict validation against product Company fields.
- Current Users management Company/Project product cleanup result: no runtime source change is required. The audited create/edit/list/detail paths already render and submit Company/Project fields; `/v2/user/info` detail responses expose `company_ids`, `company_names`, `project_ids`, and `project_names` and do not expose Organization aliases in the response schema. This slice adds regression coverage for the detail contract so product user surfaces cannot silently regress to Organization wording or omit Company/Project context.
- Current Safety/Guardrails key-context result: `/v2/guardrails/list` accepts product `company_id` and `project_id` filters and scopes team-owned guardrails through existing Project backing teams plus Company admin membership. Server API Key create/edit guardrail selection passes the selected Company/Project context to that existing list endpoint; global guardrails remain visible, and guardrails owned by unrelated teams are filtered out. Scoped dashboard requests do not fall back to the legacy unscoped `/guardrails/list` endpoint if the v2 Company/Project request is denied or fails.
- Current Safety/Guardrails Compliance Company/Project contract result: guardrail submissions now use Company/Project as the product tenant contract. `/guardrails/register` accepts `company_id` and `project_id`, validates that the Project belongs to the Company, derives the existing LiteLLM backing `team_id`, persists nullable `LiteLLM_GuardrailsTable.project_id`, and returns Company/Project fields. `/guardrails/submissions` filters by `company_id` and `project_id`, keeps `organization_id` hidden as a compatibility alias, and enriches returned rows with Company/Project names where available. The dashboard Guardrails submissions tab renders Company/Project filters and submit controls, and no longer sends `team_id` from the product flow.
- Current RAG/Vector Stores Company/Project result: managed vector stores persist nullable `project_id`, derive the existing LiteLLM backing `team_id` from the selected Project, validate that Project belongs to the selected Company, and return `company_id`/`company_name` plus `project_id`/`project_name` on create/list/info/update. RAG ingest accepts Company/Project product context in `litellm_vector_store_params`, strips those fields before provider ingestion, and persists the created vector store with the Project backing team.
- Current RAG/Vector Stores OpenAI-compatible managed-resource result: `/v1/vector_stores` requests using `target_model_names` accept product `company_id`/`project_id`, validate the Project belongs to the Company, strip product tenant fields before provider calls, persist the Project on `LiteLLM_ManagedVectorStoreTable.project_id`, and return Company/Project fields on the managed vector store response. The persisted `team_id` remains the existing LiteLLM backing Project team compatibility field.
- Current Server API Key VectorStoreSelector result: key create/edit allowed vector store selection passes selected `company_id` and `project_id` into the existing `/vector_store/list` contract, displays returned Company/Project context in options, and prunes selected vector stores that fall outside the scoped result. Internal UI state may still use LiteLLM Organization-shaped IDs to feed existing Company dropdowns, but product payloads and selector filters use Company/Project fields.
- Current Server API Key allowed vector store enforcement result: key create/update validates `object_permission.vector_stores` against the effective key Company/Project/team context before persisting object permissions. Runtime managed-vector-store access also rejects key-level allowlists that do not match the key Company/Project/team context, so an allowlist cannot bypass tenant mismatch.
- Current Company/Project authorization hardening result: `/key/list` applies Company filters globally across own-key, created-by, team-admin, and team-member visibility branches; non-admin validation again loads the caller's persisted user/membership row before evaluating Company/Project scope. `/spend/logs/v2` and `/spend/logs/ui` authorize Company admins through `LiteLLM_OrganizationMembership.user_role = org_admin` and Project viewers through the Project backing team plus `/spend/logs` permission before removing user-level scoping.
- Current Virtual key Company/Project authorization boundary result: Project/team-scoped key info and delete operations now require the caller to have backing team access or Company admin membership, while proxy admin remains an override. A key owner who no longer belongs to the Project backing team cannot use ownership alone to read/delete that Project key; personal/company-only keys keep the existing owner and Company admin behavior. `organization_id` remains the hidden LiteLLM Company compatibility column, and product callers should use `company_id` plus `project_id`.
- Current Company/Project access-control foundation result: management endpoints can use `build_company_project_access_context` from `management_endpoints/common_utils.py` as the canonical product tenant decision helper. It resolves Company read scope from existing `LiteLLM_OrganizationMembership` rows, Company admin/write scope from `user_role = org_admin`, Project membership/admin from the Project backing team's `members_with_roles`, and explicit Project operator/viewer route grants from existing `team_member_permissions`. `/key/list` now uses this helper for Project-scoped list authorization.
- Current MCP management Company/Project authorization result: persisted MCP server definitions remain global resources because `LiteLLM_MCPServerTable` has no Company or Project ownership columns. Team-scoped MCP discovery (`GET /v1/mcp/server?team_id=...`) now authorizes through `CompanyProjectAccessContext`: proxy admins remain global, Project/team members may read their backing team scope, and Company admins may read teams whose internal `LiteLLM_TeamTable.organization_id` matches their Company membership. Cross-Company team scope is denied.
- Current Chatbots/browser-token Company/Project result: A2A Agents are the existing chatbot surface. Agent create/list/read/update/delete accepts and returns `company_id`/`company_name` plus `project_id`/`project_name`, validates Project ownership through the Project backing team, and authorizes non-proxy access through `CompanyProjectAccessContext`. The dashboard Agents list exposes Company and Project filters and calls `/v1/agents` with `company_id` and `project_id`; create/edit continue to submit Company/Project fields. Browser/API keys created for an agent from the dashboard send the same Company/Project product context to existing key management; runtime key auth rejects agent-bound keys whose internal Company compatibility field or `project_id` does not match the Agent. No separate browser/public web-token table was found for this product surface; the public AI Hub remains a proxy-admin controlled public catalog via `public_agent_groups`, not a tenant-scoped token store. `organization_id` remains only the LiteLLM Company compatibility column and hidden legacy alias.
- Current model access policies/budgets/rate-limit surface result: Budget policy, Policy Templates, and Access Group dashboard surfaces use Company/Project product wording. Budget examples apply `budget_id` through the existing `/project/update` contract with `company_id` and `project_id`; `/budget/new` OpenAPI copy describes Companies/Projects rather than Organizations; request examples use a Project-scoped server API key rather than an end-user/customer tenant. Unified Access Groups remain reusable model/MCP/Agent policy templates assigned to Company/Project-scoped Teams and Server API Keys.
- Current Company member role surface cleanup result: Company member tables and Add Company Member modal display `org_admin` as Company Admin while preserving `org_admin` as the LiteLLM compatibility role value submitted to existing membership endpoints. `/user/filter/ui` scope errors now say company admins instead of organization admins.
- Current final product-facing Organization removal audit result: converted dashboard tenant surfaces render Company/Project wording; provider-specific Organization fields and internal LiteLLM compatibility names remain unchanged. Product OpenAPI surfaces for `/company/info` and `/v2/team/list` expose Company/Project filters and hide `organization_id` as a legacy compatibility alias.
- Current Teams API Organization residue cleanup result: `/team/new`, `/team/update`, `/v2/team/list`, and legacy `/team/list` product docs expose Company/Project tenant wording. `/team/list` now exposes `company_id` and `project_id` query filters while keeping `organization_id` hidden as a compatibility alias that must match `company_id`.
- Current Company/Project migration readiness result: schema copies are identical and all runtime Company/Project persistence is covered by Prisma migrations. A new narrow index migration adds `LiteLLM_SpendLogs(api_key, startTime)` for selected-key usage/log drilldowns; no new table or attribution column is introduced.

## Working Rules

- One approved feature at a time.
- Every feature must include backend, frontend, migration SQL if schema changes, tests, and this runbook update.
- Create new scripts/source files only when the feature is genuinely new and has no existing owner.
- Integrate usage, keys, users, teams, billing, guardrails, and migrations into existing LiteLLM/CavadaLabs modules.
- Do not create parallel modules for behavior already owned by existing files.

## Setup

```bash
git status --short
git branch --show-current
git status -sb
```

Do not run `git pull origin cavadalabs_integration_of_new_features` while restarting this work; that remote branch may still contain the discarded old integration commits.

## Before Each Feature

```bash
git status --short
git fetch origin
git status -sb
```

Confirm the approved feature covers:

- Backend files:
- Frontend files:
- Migration SQL:
- Tests:
- Smoke check:

## Migration

A migration is required for the Chatbots/A2A Agents Company/Project slice because `LiteLLM_AgentsTable` previously had no authoritative Company or Project attribution. Without those columns, list/read/write authorization could not safely distinguish Agents across Companies or Projects.

Current Agent Company/Project migration:

```bash
litellm-proxy-extras/litellm_proxy_extras/migrations/20260518150000_add_agent_company_project_context/migration.sql
```

Migration effect:

- Adds nullable `LiteLLM_AgentsTable.company_id`.
- Adds nullable `LiteLLM_AgentsTable.project_id`.
- Adds indexes on `company_id` and `project_id` for scoped list/read paths.
- Does not backfill historical Agents. Existing unscoped rows remain visible only through legacy/global compatibility rules until an operator assigns Company/Project context explicitly.

No additional migration is required for the Chatbots/A2A Agents list-filter and browser/public token audit slice.

- `LiteLLM_AgentsTable.company_id` and `LiteLLM_AgentsTable.project_id` already exist in all Prisma schema copies.
- `litellm-proxy-extras/litellm_proxy_extras/migrations/20260518150000_add_agent_company_project_context/migration.sql` already adds both columns and indexes.
- `/v1/agents` already accepts `company_id` and `project_id` filters and enforces Company/Project access before returning rows.
- Agent runtime access uses existing server API key context; the internal key Company compatibility field maps to Agent `company_id`, and `project_id` must match when present.

A migration is required for the RAG/Vector Stores Company/Project slice because managed vector stores previously had no Project attribution column. The nullable column preserves legacy vector stores while new product flows require Company + Project selection.

Current vector store Project migration:

```bash
litellm-proxy-extras/litellm_proxy_extras/migrations/20260518120000_add_vector_store_project_id/migration.sql
```

Migration effect:

- Adds nullable `LiteLLM_ManagedVectorStoresTable.project_id`.
- Adds `LiteLLM_ManagedVectorStoresTable(project_id)` index for Project-scoped list/detail operations.
- Does not backfill historical vector stores. Existing rows only have `team_id`; `LiteLLM_ProjectTable.team_id` is not unique enough to derive a deterministic Project for every historical row.

A follow-up migration is required for OpenAI-compatible managed vector stores created through `/v1/vector_stores` with `target_model_names`. That path uses `LiteLLM_ManagedVectorStoreTable` rather than `LiteLLM_ManagedVectorStoresTable`, so Project attribution must be stored on the managed-resource table as well.

Current OpenAI-compatible managed vector store Project migration:

```bash
litellm-proxy-extras/litellm_proxy_extras/migrations/20260518190000_add_managed_vector_store_project_id/migration.sql
```

Migration effect:

- Adds nullable `LiteLLM_ManagedVectorStoreTable.project_id`.
- Adds `LiteLLM_ManagedVectorStoreTable(project_id, created_at DESC)` index for Project-scoped managed-resource lookup/list paths.
- Does not backfill historical unified vector stores. Existing rows keep `team_id` and `created_by` isolation; assign Project context explicitly if a legacy unified vector store must become Company/Project visible.

No new table or persistence column is required for the Users/Teams Company/Project slice.

- User Company context uses existing `LiteLLM_OrganizationMembership` rows; `company_ids` is the product API/UI alias for the existing LiteLLM `organization_id` membership column.
- User Project context uses existing `LiteLLM_ProjectTable.team_id` and LiteLLM team membership. Adding/removing `project_ids` adds/removes the user from the backing project teams through existing team membership logic.
- Team Company context uses existing `LiteLLM_TeamTable.organization_id`; `company_id` is accepted as the product primary field and maps to `organization_id` internally.
- Team Project context is derived from existing `LiteLLM_ProjectTable.team_id`; team list/detail responses return `project_ids` and `project_names` by looking up projects whose backing team is the returned team.

No migration is required for the Users/Teams Product Organization removal slice. It changes product-facing labels, table/filter visibility, and frontend request payload/query names only. The authoritative persistence remains the existing LiteLLM `LiteLLM_OrganizationMembership`, `LiteLLM_TeamTable.organization_id`, and `LiteLLM_ProjectTable.team_id` mapping described above.

No migration is required for the Teams API Organization residue cleanup slice. It changes only FastAPI query schema exposure and endpoint documentation for existing Team list/create/update routes. Persistence remains `LiteLLM_TeamTable.organization_id` as the internal Company compatibility column and `LiteLLM_ProjectTable.team_id` as the Project backing-team link.

No migration is required for the Users/CreateUser Company/Project selector hardening slice. It changes only form behavior and tests. The backend already accepts and returns `company_ids`/`company_names` and `project_ids`/`project_names`; legacy `organizations`/`organization_ids` remain validated compatibility aliases and are not the primary product contract.

No migration is required for the User management CreateUser Company/Project integration slice. It extends request validation and sanitation over existing persistence only:

- Company membership remains `LiteLLM_OrganizationMembership.organization_id` internally.
- Product `company_id` is normalized to `company_ids`/`organizations` before authorization and membership creation.
- Product `project_id` is normalized to `project_ids`; Project membership remains existing backing team membership through `LiteLLM_ProjectTable.team_id`.
- Product-only and legacy alias fields are stripped before user row/key helper persistence.

No migration is required for the User management edit Company/Project integration slice. It uses the same existing persistence as create-user:

- Updating Companies replaces `LiteLLM_OrganizationMembership` rows through the existing membership helper.
- Updating Projects adds/removes existing backing team memberships derived from `LiteLLM_ProjectTable.team_id`.
- `company_id`, `project_id`, and legacy Organization aliases are request aliases only and are stripped before `LiteLLM_UserTable` persistence.

No migration is required for the user create/edit Company/Project assignment hardening slice. It changes UI payload sanitation, Company display fallback, Users list Company filter value normalization, and request-model contract tests only. The authoritative persistence remains `LiteLLM_OrganizationMembership.organization_id` for Company membership and Project backing team membership through `LiteLLM_ProjectTable.team_id`.

No migration is required for the Users management Company/Project membership networking slice. It changes only dashboard request normalization for `/user/new` and `/user/update`; the backend already persists Company memberships in `LiteLLM_OrganizationMembership.organization_id` and Project memberships through existing backing team membership from `LiteLLM_ProjectTable.team_id`.

No migration is required for the Users API Organization residue cleanup slice. It changes only request schema metadata and endpoint documentation so legacy Organization aliases are marked internal/deprecated while product fields remain `company_ids` and `project_ids`. Persistence is unchanged: Company membership remains `LiteLLM_OrganizationMembership.organization_id`, and Project membership remains backing team membership through `LiteLLM_ProjectTable.team_id`.

No migration is required for the Users management Company/Project product cleanup slice. It adds contract coverage over existing runtime behavior only:

- `/user/new` and `/user/update` request models accept `company_id`/`company_ids` and `project_id`/`project_ids`, validate conflicts with hidden legacy Organization aliases, and strip tenant aliases before `LiteLLM_UserTable` persistence.
- `/user/list` filters by product `company_ids` through existing `LiteLLM_OrganizationMembership.organization_id` rows and by product `project_ids` through `LiteLLM_ProjectTable.team_id` backing team membership.
- `/v2/user/info` detail responses return `company_ids`, `company_names`, `project_ids`, and `project_names`; the response schema has no `organization_id`, `organization_ids`, or `organizations` product fields.

No new table or attribution column is required for the Company/Project usage visibility slice. The authoritative usage tables already contain the required tenant attribution; deployment-readiness now also includes the selected-key request-log index:

- `LiteLLM_SpendLogs.organization_id` is the internal Company compatibility column and is indexed with `startTime`.
- `LiteLLM_SpendLogs.project_id` is indexed with `startTime`.
- `LiteLLM_SpendLogs.api_key` is indexed with `startTime` for selected-key usage/log filters.
- `LiteLLM_DailyOrganizationSpend.organization_id` is the existing daily Company rollup storage.
- `LiteLLM_DailyProjectSpend.project_id` is required and indexed for Project rollups.
- Dashboard usage and logs filters call existing `/company/daily/activity`, `/project/daily/activity`, and `/spend/logs/v2` contracts with `company_id`/`company_ids` plus `project_id`/`project_ids`.
- `/spend/logs/ui` is the dashboard request-log path and uses the same product `company_id`/`project_id` query contract. Its `organization_id` query parameter is hidden and accepted only as a compatibility alias for matching `company_id`.
- The current Usage/Billing attribution/filter hardening changes only dashboard request normalization for `/spend/logs/ui`: changing Company clears a stale Project filter unless the request explicitly supplies a new Project. It does not add a new source of truth, ledger, column, or index.
- No runtime code change is required for the Usage/Daily Activity Company/Project filter coherence slice. Project Usage stores the Company filter in `UsagePageView.selectedProjectCompanyId`, filters the Project option list by `project.company_id`, and remounts `EntityUsage` with `key={selectedProjectCompanyId || "all-projects"}` when Company changes. The selected Project filter is local `EntityUsage.selectedTags`, so the remount clears stale Project filters before `/project/daily/activity` is called. Backend `/project/daily/activity` remains authoritative and rejects conflicting product Company filters and hidden LiteLLM `organization_id` compatibility aliases.
- No migration is required for the Company/Project usage authorization contract slice. Authorization reuses existing Company membership (`LiteLLM_OrganizationMembership.organization_id` with `user_role` values `org_admin`, `internal_user`, or `internal_user_viewer`) and Project visibility through `LiteLLM_ProjectTable.team_id` plus the backing `LiteLLM_TeamTable.organization_id` Company link. The slice changes only endpoint authorization and regression coverage; no table, column, index, or frontend contract changes.

No migration or backend change is required for the frontend visible usage proof slice. It adds dashboard test coverage over existing contracts only:

- `uiSpendLogsCall` and request-log filter logic send `company_id`/`project_id` to `/spend/logs/ui` and do not send `organization_id`.
- `companyDailyActivityCall` sends `company_ids` to `/company/daily/activity`.
- `projectDailyActivityCall` sends `project_ids` plus optional `company_ids` to `/project/daily/activity`.
- The Usage Project view filters Project options by selected Company and clears stale Project filters through the existing keyed remount.
- The legacy `EntityUsage` compatibility entity type `organization` maps to the same Company daily activity call used by the product Company usage view, so dashboard runtime usage does not call the hidden `/organization/daily/activity` route.

No migration or backend change is required for the Users list/detail Company/Project surface slice. The authoritative API and persistence already exist:

- `/user/list` accepts product `company_ids` and `project_ids`, validates hidden legacy `organization_ids` conflicts, and returns `company_ids`, `company_names`, `project_ids`, and `project_names`.
- `/v2/user/info` returns the same Company/Project membership fields for detail views.
- Company membership remains `LiteLLM_OrganizationMembership.organization_id` internally, and Project membership remains LiteLLM team membership via `LiteLLM_ProjectTable.team_id`.

No migration is required for the Companies management product-facing slice. It adds product route/API aliases (`/companies` dashboard route and `/company/*` management endpoints) over the existing LiteLLM `LiteLLM_OrganizationTable`, `LiteLLM_OrganizationMembership`, and related budget/object-permission rows. `company_id` maps to existing `organization_id`; `company_name` maps to existing `organization_alias`; product-only aliases are stripped before DB writes.

No new table or persistence column is required for the Virtual Keys Company/Project create-edit slice. `LiteLLM_VerificationToken` already has `organization_id` and `project_id`; `company_id` is the product API/UI alias for the existing LiteLLM `organization_id` column.

No new persistence column is required for Virtual Key tenant names. `company_name` is resolved from `LiteLLM_OrganizationTable.organization_alias`, and `project_name` is resolved from `LiteLLM_ProjectTable.project_alias` when returning key create/update/info/list responses. The key persistence payload stores only canonical LiteLLM DB fields (`organization_id`, `project_id`) and removes product-only `company_id` before DB writes.

No migration is required for the Server API Key Product Organization removal and end-to-end Company/Project canonicalization slices. They change product labels, UI selector behavior, request/response schema metadata, tests, and documentation only. Authoritative persistence still uses the existing LiteLLM key company mapping described above: `LiteLLM_VerificationToken.organization_id`/`org_id` remain internal compatibility aliases for product `company_id`, and `LiteLLM_VerificationToken.project_id` remains the product Project attribution column.

No additional migration is required for the Virtual Keys/API keys Company+Project context slice. The authoritative key table already has `LiteLLM_VerificationToken.organization_id` for Company compatibility and `LiteLLM_VerificationToken.project_id` for Project, with the existing `20260517160000_add_key_company_project_indexes` migration covering list/filter paths. Runtime key persistence strips product-only `company_id` before DB writes and stores `project_id` directly; Project selection derives the backing `team_id` and internal Company `organization_id` from the existing Project backing team. The create-key and edit-key UIs send `company_id`/`project_id` and strip legacy Organization aliases before networking. The list/table UI sends `company_id` and `project_id` query parameters; backend `/key/list` still accepts legacy `organization_id` only as a validated compatibility alias and maps it to the same internal Company filter.

No additional migration is required for the Virtual Keys product-facing Company/Project surface slice. It changes only API/client exposure and contract tests:

- `/key/list` already filters the authoritative `LiteLLM_VerificationToken.organization_id` internal Company column and `LiteLLM_VerificationToken.project_id`.
- The existing `20260517160000_add_key_company_project_indexes` migration covers Company/Project key list filters.
- Legacy `organization_id` stays accepted only as a hidden compatibility alias and is normalized to `company_id`; no new persistence field or backfill is introduced.
- The current Virtual Keys product UI cleanup is frontend-only. Team-scoped key tables use the same `/key/list` response fields and `project_id` filter contract; no new key, Project, Company, or index persistence is required.

No migration is required for the Virtual Keys canonical Company/Project delete authorization slice. It changes only authorization logic over existing rows:

- Company remains stored on `LiteLLM_VerificationToken.organization_id`.
- Project remains stored on `LiteLLM_VerificationToken.project_id` and backed by `LiteLLM_ProjectTable.team_id`.
- Company admin membership already exists in `LiteLLM_OrganizationMembership.user_role = org_admin`.
- Project admin and explicit operator grants already exist on the Project backing `LiteLLM_TeamTable.members_with_roles` and `team_member_permissions`.
- The current Virtual Keys table Project filter hardening is frontend-only. It uses existing `/project/list` data already loaded by `useProjects({ includeNonAdmin: true })`; it does not add a new table, column, index, backend endpoint, or source of truth.

No migration is required for the Virtual Keys product integration cleanup slice. It changes only schema metadata and documentation for existing request/response contracts:

- `GenerateKeyRequest`, `UpdateKeyRequest`, and `GenerateKeyResponse` expose `company_id` and `project_id` as product fields.
- `organization_id` remains accepted only for LiteLLM compatibility and is marked internal/deprecated in schema metadata.
- Key response view compatibility fields such as `organization_alias` and `organization_*` budget/rate-limit values are marked internal/deprecated and mirrored to `company_name`, `company_max_budget`, `company_tpm_limit`, and `company_rpm_limit` for product clients.
- Persistence remains the existing `LiteLLM_VerificationToken.organization_id` internal Company column plus `LiteLLM_VerificationToken.project_id`.

No new migration is required for the Company/Project RBAC slice. Authorization reuses existing LiteLLM persistence:

- Company admin comes from `LiteLLM_OrganizationMembership.user_role = org_admin`.
- Project admin comes from the backing LiteLLM team membership role for `LiteLLM_ProjectTable.team_id`.
- Route-specific project write exceptions use existing `LiteLLM_TeamTable.team_member_permissions`.

No migration is required for the model access policies/budgets/rate-limit surface slice. Existing persistence is authoritative:

- `LiteLLM_BudgetTable` stores reusable budget/rate-limit policy templates; Company assignment uses existing `LiteLLM_OrganizationTable.budget_id`, Project assignment uses existing `LiteLLM_ProjectTable.budget_id`, Team assignment uses existing `LiteLLM_TeamTable` budget/rate-limit fields, and Server API Key assignment uses existing `LiteLLM_VerificationToken` budget/rate-limit fields.
- Model-specific RPM/TPM limits already live on the Company/Project/Team/Key rows that own runtime scope (`model_rpm_limit`, `model_tpm_limit`, `models`, `access_group_ids`, `budget_limits` as applicable).
- `LiteLLM_AccessGroupTable` remains a reusable policy template with `assigned_team_ids` and `assigned_key_ids`; the assigned Team/Key rows carry the Company/Project tenant context. Adding Company/Project columns to access groups would duplicate assignment ownership rather than create a new source of truth.
- The current cleanup changes only product-facing Policy Templates copy and `/budget/new` OpenAPI text. No schema, index, or authoritative query path changes are introduced.

No migration is required for the Deleted Teams product-facing Organization cleanup slice. Deleted Teams reuses existing team rows and already receives `company_id`/`company_name` where available; `LiteLLM_TeamTable.organization_id` remains the internal Company compatibility fallback for legacy rows. The slice changes only dashboard rendering and test coverage.

No migration is required for the Company member role surface cleanup slice. Company admin membership remains the existing `LiteLLM_OrganizationMembership.user_role = org_admin` value because that is the LiteLLM compatibility role used by current endpoints and authorization checks. The slice changes only product-facing labels and an API error message.

A new index migration is required because Virtual Keys list/filter paths now use Company and Project as first-class product filters over the authoritative key tables.

Current Virtual Keys Company/Project index migration:

```bash
litellm-proxy-extras/litellm_proxy_extras/migrations/20260517160000_add_key_company_project_indexes/migration.sql
```

No new table or persistence column is required for the Billing/Logs Company/Project slice. Company uses the existing LiteLLM `organization_id` spend attribution internally, and Project uses `LiteLLM_SpendLogs.project_id` from the Project usage migration below.

A new index migration is required for Company Billing/Logs filters because request-log billing queries now filter the authoritative `LiteLLM_SpendLogs` table by `organization_id` plus time range. Project already has `LiteLLM_SpendLogs(project_id, startTime)` from the Project usage migration.

Current Company Billing/Logs index migration:

```bash
litellm-proxy-extras/litellm_proxy_extras/migrations/20260517143000_add_company_spend_logs_index/migration.sql
```

A new narrow index migration is required for selected-key Usage/Logs filters because `/spend/logs/ui` and `/spend/logs/v2` can filter the authoritative `LiteLLM_SpendLogs` table by `api_key` plus a time range.

Current request-log key/time index migration:

```bash
litellm-proxy-extras/litellm_proxy_extras/migrations/20260518170000_add_spend_logs_api_key_starttime_index/migration.sql
```

No new migration is required for the Usage/Billing visibility route slice. It only adds Company-primary API routing/filter aliases over existing authoritative tables and indexes:

- `LiteLLM_DailyOrganizationSpend.organization_id` remains the internal Company aggregate.
- `LiteLLM_DailyProjectSpend.project_id` remains the Project aggregate.
- `LiteLLM_SpendLogs.organization_id` and `LiteLLM_SpendLogs.project_id` remain the request-level billing source.

No new migration is required for the Usage/Billing Company-admin visibility correction. It only changes authorization over existing persistence:

- Company admin role is read from `LiteLLM_OrganizationMembership.user_role = org_admin`.
- Project-to-Company ownership is read through the existing Project backing team (`LiteLLM_ProjectTable.team_id` -> `LiteLLM_TeamTable.organization_id`) or the serialized `company_id` compatibility field when present.
- Usage and billing request filters continue to use the existing daily spend and spend log indexes listed above.
- Frontend runtime code and static bundle do not change for this correction because the existing Usage filters already call `/company/daily/activity`, `/project/daily/activity`, and `/spend/logs/ui` with `company_id`/`company_ids` and `project_id`/`project_ids`.

Migration remains required for Project usage/spend filters.

Reason: Company usage is already materialized through `organization_id`, but Project usage only exists in request metadata (`metadata.user_api_key_project_id`) and cannot be queried or aggregated safely through current-key joins. The migration adds:

- `LiteLLM_SpendLogs.project_id`, backfilled only from historical spend log metadata when that metadata points to an existing `LiteLLM_ProjectTable.project_id`.
- `LiteLLM_DailyProjectSpend`, matching the existing daily User/Team/Organization aggregate shape.
- A one-time aggregate backfill into `LiteLLM_DailyProjectSpend`, limited to Project rows that still exist.

Current migration:

```bash
litellm-proxy-extras/litellm_proxy_extras/migrations/20260517120000_add_project_spend_usage/migration.sql
```

No additional migration file is required for the historical Project attribution hardening slice. The prepared Project usage migration is the authoritative migration path; it now filters both request-metadata backfill and daily aggregation through existing `LiteLLM_ProjectTable` rows. Historical spend rows that lack both `LiteLLM_SpendLogs.project_id` and request metadata `metadata.user_api_key_project_id` are not deterministically attributable to a Project.

No additional migration file is required for the current Usage/Billing Company/Project visibility slice. The required persistence already exists:

- Company request-log filtering uses `LiteLLM_SpendLogs.organization_id` and `LiteLLM_SpendLogs_organization_id_startTime_idx`.
- Project request-log filtering uses `LiteLLM_SpendLogs.project_id` and `LiteLLM_SpendLogs_project_id_startTime_idx`.
- Company daily usage uses `LiteLLM_DailyOrganizationSpend`.
- Project daily usage uses `LiteLLM_DailyProjectSpend`.
- `/project/daily/activity` Company scoping reads `LiteLLM_ProjectTable.team_id` and the backing `LiteLLM_TeamTable.organization_id`; `organization_id`/`organization_ids` are accepted only as hidden LiteLLM compatibility aliases for the same Company filter.

No migration or backend change is required for the Usage/Logs UI Company/Project surface slice. It changes only runtime dashboard display/search for the existing Company filter component:

- Company filter values still map to the existing LiteLLM `organization_id` compatibility field.
- Product display/search uses `company_name` and `company_id` when present.
- Request-log and Usage networking already send `company_id`/`company_ids` and `project_id`/`project_ids`; no API contract or persistence shape changes.

No migration is required for the Usage/Logs Company/Project authorization hardening slice. Authorization reuses existing persistence:

- Company admin scope comes from `LiteLLM_OrganizationMembership.user_role = org_admin`.
- Project ownership comes from `LiteLLM_ProjectTable.team_id` and the backing `LiteLLM_TeamTable.organization_id`.
- Request-log rows already carry `LiteLLM_SpendLogs.organization_id` for Company compatibility and `LiteLLM_SpendLogs.project_id` for Project filtering.
- No new membership table, ownership column, or index is introduced.
- The current `/spend/logs/ui` Company+Project visibility correction changes only authorization order: Project-scoped users with `/spend/logs` permission may request matching `company_id` and `project_id` together. It does not add a new table, column, index, ledger, or frontend contract.

No migration is required for the Usage/Billing Company+Project correctness slice. The runtime patch only enriches spend-log responses and UI display using existing authoritative tables:

- `LiteLLM_SpendLogs.organization_id` remains the internal Company attribution column and already has the Company/time index from `20260517143000_add_company_spend_logs_index`.
- `LiteLLM_SpendLogs.project_id` remains the Project attribution column and already has the Project/time index from `20260517120000_add_project_spend_usage`.
- `company_name` is resolved from `LiteLLM_OrganizationTable.organization_alias`; `project_name` is resolved from `LiteLLM_ProjectTable.project_alias`.
- No new ledger, ownership column, or backfill is introduced by this slice.

No migration or backend change is required for the Teams UI Company/Project surface slice. It changes runtime dashboard display/search only:

- Team Company persistence remains `LiteLLM_TeamTable.organization_id`; product `company_id` is already accepted by `NewTeamRequest`, `UpdateTeamRequest`, and `/v2/team/list`.
- Team Project context remains derived from `LiteLLM_ProjectTable.team_id`; duplicating Project fields onto team rows would create a second source of truth.
- Team list/detail response enrichment already returns `company_id`, `company_name`, `project_ids`, and `project_names`, covered by backend tests.

If selected Project usage is missing after deploy, first verify the Project usage migration/backfill has run:

```bash
DATABASE_URL="<POSTGRES_URL>" uv run prisma migrate status --schema litellm-proxy-extras/litellm_proxy_extras/schema.prisma
DATABASE_URL="<POSTGRES_URL>" uv run prisma migrate deploy --schema litellm-proxy-extras/litellm_proxy_extras/schema.prisma
DATABASE_URL="<POSTGRES_URL>" uv run prisma migrate status --schema litellm-proxy-extras/litellm_proxy_extras/schema.prisma
```

The required usage/log migrations are:

- `litellm-proxy-extras/litellm_proxy_extras/migrations/20251122125322_Add organization_id to spend logs/migration.sql`
- `litellm-proxy-extras/litellm_proxy_extras/migrations/20260517120000_add_project_spend_usage/migration.sql`
- `litellm-proxy-extras/litellm_proxy_extras/migrations/20260517143000_add_company_spend_logs_index/migration.sql`
- `litellm-proxy-extras/litellm_proxy_extras/migrations/20260518170000_add_spend_logs_api_key_starttime_index/migration.sql`

The Project usage migration backfills only deterministic historical rows where `metadata.user_api_key_project_id` points to an existing `LiteLLM_ProjectTable.project_id`; rows without request-time Project metadata are not safely attributable.

No migration is required for the Teams Company/Project completion slice. The authoritative persistence already exists:

- Team Company context uses `LiteLLM_TeamTable.organization_id`; product `company_id` is validated as an alias and stripped from DB writes.
- Team Project context is derived from `LiteLLM_ProjectTable.team_id`; duplicating `project_id` on the team row would create a second source of truth.
- Team list/detail responses expose `company_id`, `company_name`, `project_ids`, and `project_names` by enrichment from those existing tables.

No migration is required for the Teams management Company/Project networking and UI cleanup slice. It changes request normalization, Company selector/filter values, and tests only:

- Team Company context continues to persist on `LiteLLM_TeamTable.organization_id`; product `company_id` is the only tenant field sent by dashboard team create/update.
- Team Project context continues to be read from `LiteLLM_ProjectTable.team_id`; Team create/update does not write Project membership because that would duplicate Project management as a second source of truth.
- Team list filters already use existing `company_id` and `project_id` query support.
- Team Company selectors and filters use `company_id` as their product value, with `organization_id` only as the fallback internal compatibility ID for legacy Company records.
- Team create/update schema cleanup changes only OpenAPI metadata for the existing `organization_id` compatibility alias; no table, column, index, or backfill changes are needed.

No migration is required for the Users and Teams Company/Project management contract slice. The audit confirms the existing schema is already authoritative for the product contract:

- User Company membership: `LiteLLM_OrganizationMembership(user_id, organization_id, user_role)`, exposed as product `company_ids`/`company_names`.
- User Project membership: existing team membership on Project backing teams resolved through `LiteLLM_ProjectTable.team_id`, exposed as product `project_ids`/`project_names`.
- Team Company scope: `LiteLLM_TeamTable.organization_id`, exposed and filtered as product `company_id`.
- Team Project scope: derived by lookup from `LiteLLM_ProjectTable.team_id`, exposed and filtered as product `project_id`/`project_ids`.
- Legacy `organization_id`/`organization_ids` remains accepted only as hidden compatibility aliases where existing LiteLLM endpoints require it, with conflict validation against product Company aliases.

No migration is required for the Company/Project access-control hardening slice. Authorization reuses existing persistence:

- Company admin is read from `LiteLLM_OrganizationMembership.user_role = org_admin`.
- Project ownership is read from `LiteLLM_ProjectTable.team_id` and the backing `LiteLLM_TeamTable.organization_id`.
- Project list/read/write behavior changes only endpoint authorization and query scoping; no data shape or index changes are introduced.

No migration is required for the Projects product-surface disambiguation slice. The authoritative Project-to-Company mapping already exists:

- `LiteLLM_ProjectTable.team_id` links each Project to its backing LiteLLM team.
- `LiteLLM_TeamTable.organization_id` remains the internal Company compatibility column.
- Product `company_id` is a request/query validation alias and response/display context; it is stripped before `LiteLLM_ProjectTable` persistence.
- Adding a direct Project `company_id` column would create a second source of truth and is intentionally avoided.

No migration is required for the Company/Project RBAC membership slice. The required membership data already exists:

- Company admin membership is `LiteLLM_OrganizationMembership.user_role = org_admin` for the internal Company compatibility row.
- Project admin membership is the backing team's `members_with_roles` entry with `role = admin`.
- Project member/viewer read scope continues to use the backing team membership and route-specific permission helpers; no new role table or ownership column is introduced.

No migration is required for the runtime request attribution slice. The required request and aggregate persistence already exists:

- Virtual key Company context persists on `LiteLLM_VerificationToken.organization_id`; product `company_id` is normalized to the internal auth `org_id` compatibility field.
- Virtual key Project context persists on `LiteLLM_VerificationToken.project_id`.
- Team-backed Company context already persists on `LiteLLM_TeamTable.organization_id`. Runtime auth copies it to the request auth object's internal `org_id` when a key only carries `team_id`.
- Project-backed team context already persists as `LiteLLM_ProjectTable.team_id`. Runtime auth maps it to `project_id` only when the team resolves to exactly one Project; ambiguous legacy teams leave Project attribution empty instead of inventing usage ownership.
- Runtime request setup and failure logging copy Company/Project auth context into spend-log metadata as `user_api_key_org_id`, `user_api_key_project_id`, and `user_api_key_project_alias`; no new persistence field is introduced.
- Request logs persist Company and Project on `LiteLLM_SpendLogs.organization_id` and `LiteLLM_SpendLogs.project_id`; `/spend/logs/ui` is verified with product `company_id` and `project_id` filters.
- Usage aggregation inputs already enqueue `LiteLLM_DailyOrganizationSpend` and `LiteLLM_DailyProjectSpend` updates from the same runtime attribution metadata; `/company/daily/activity` and `/project/daily/activity` are verified with product Company/Project filters and the virtual-key `api_key` hash.
- The end-to-end visibility contract after the migration audit is test-only: the same virtual-key `api_key` hash is present in SpendLogs, DailyOrganizationSpend, and DailyProjectSpend, and all three product endpoints return only the selected Company/Project rows. No new migration is required because the selected fields and indexes already exist in the migration readiness mapping above.

Validation queries for a selected Company/Project after a virtual-key request:

```bash
psql "$DATABASE_URL" -v company_id="$COMPANY_ID" -v project_id="$PROJECT_ID" -c "SELECT request_id, organization_id AS company_id, project_id, metadata->>'user_api_key_project_id' AS metadata_project_id FROM \"LiteLLM_SpendLogs\" WHERE organization_id = :'company_id' AND project_id = :'project_id' ORDER BY \"startTime\" DESC LIMIT 20;"
psql "$DATABASE_URL" -v project_id="$PROJECT_ID" -c "SELECT project_id, date, api_key, spend, api_requests FROM \"LiteLLM_DailyProjectSpend\" WHERE project_id = :'project_id' ORDER BY date DESC LIMIT 20;"
psql "$DATABASE_URL" -v company_id="$COMPANY_ID" -c "SELECT organization_id AS company_id, date, api_key, spend, api_requests FROM \"LiteLLM_DailyOrganizationSpend\" WHERE organization_id = :'company_id' ORDER BY date DESC LIMIT 20;"
```

No migration is required for the product-facing Organization surface cleanup slice. It changes only Company management API wording and targeted tests; persistence remains the existing LiteLLM Organization tables and compatibility aliases.

No migration is required for the runtime UI Organization surface cleanup slice. It changes only frontend copy for an existing provider-specific model parameter; schema, request payloads, and persisted LiteLLM organization compatibility fields are unchanged.

No migration is required for the Safety/Guardrails Company/Project key-context slice. Guardrail ownership already exists as `LiteLLM_GuardrailsTable.team_id`; Project context is resolved through `LiteLLM_ProjectTable.team_id`, and Company context is resolved through the existing team Company field plus Company admin membership rows. Adding direct Company/Project columns to guardrails would duplicate the existing team-backed source of truth. The dashboard must use `/v2/guardrails/list` for Company/Project-scoped requests; the legacy `/guardrails/list` endpoint is kept only for unscoped compatibility.

A migration is required for the Safety/Guardrails Compliance Company/Project submissions slice because new guardrail submissions need an authoritative Product Project attribution. `LiteLLM_GuardrailsTable.team_id` remains the LiteLLM backing team compatibility field, but it is not guaranteed unique to a single Project, so storing only `team_id` is not enough for Project-filtered submissions.

Current guardrail Project migration:

```bash
litellm-proxy-extras/litellm_proxy_extras/migrations/20260518203000_add_guardrail_project_context/migration.sql
```

Migration effect:

- Adds nullable `LiteLLM_GuardrailsTable.project_id`.
- Backfills historical guardrails only when their `team_id` maps to exactly one `LiteLLM_ProjectTable.project_id`.
- Adds `LiteLLM_GuardrailsTable(project_id)` index for Project-scoped submission filters.
- Leaves ambiguous historical team-scoped guardrails without `project_id`; assign a Project explicitly if those rows must appear in Project-filtered product views.

No additional backend or migration change is required for the Server API Key VectorStoreSelector Company/Project slice. The existing `/vector_store/list` networking contract accepts `company_id` and `project_id`, and the RAG/Vector Stores migration above already adds nullable `LiteLLM_ManagedVectorStoresTable.project_id` plus its Project index. This slice changes only the existing selector and key create/edit UI wiring.

No migration or frontend change is required for the Server API Key allowed vector store enforcement slice. The required ownership data already exists:

- Key Company/Project context is persisted on `LiteLLM_VerificationToken.organization_id` and `LiteLLM_VerificationToken.project_id`.
- Managed vector store Project context is persisted on `LiteLLM_ManagedVectorStoresTable.project_id`; legacy team context remains `team_id`.
- Company ownership resolves through `LiteLLM_ProjectTable.team_id` and `LiteLLM_TeamTable.organization_id`.
- Key object permissions already store `vector_stores` in `LiteLLM_ObjectPermissionTable`; this slice only validates those references before persistence and at runtime.

No migration or frontend change is required for the Company/Project authorization hardening slice. Authorization reuses existing authoritative ownership and membership data:

- Key Company scope uses `LiteLLM_VerificationToken.organization_id`; Key Project scope uses `LiteLLM_VerificationToken.project_id`.
- Company admin membership is `LiteLLM_OrganizationMembership.user_role = org_admin`.
- Project/team read scope uses `LiteLLM_ProjectTable.team_id`, `LiteLLM_TeamTable.members_with_roles`, and existing route permission lists such as `/key/list` and `/spend/logs`.
- Usage/log rows already carry `LiteLLM_SpendLogs.organization_id` and `LiteLLM_SpendLogs.project_id`; existing Company/Project spend-log indexes cover the scoped queries.

No migration or frontend change is required for the Virtual key Company/Project authorization boundary slice. It reuses existing key and membership persistence:

- Key Company scope remains `LiteLLM_VerificationToken.organization_id`, exposed to product clients as `company_id`.
- Key Project scope remains `LiteLLM_VerificationToken.project_id`; backing team access resolves through `LiteLLM_VerificationToken.team_id` or `LiteLLM_ProjectTable.team_id`.
- Project/team membership remains `LiteLLM_TeamTable.members_with_roles`; Company admin override remains `LiteLLM_OrganizationMembership.user_role = org_admin`.
- The slice changes only read/delete authorization for Project-scoped keys whose owner no longer has backing team access.

No migration or frontend change is required for the Company/Project access-control foundation slice. It centralizes authorization over the same authoritative persistence:

- Company member/viewer read scope remains existing `LiteLLM_OrganizationMembership.organization_id` membership rows with `org_admin`, `internal_user`, or `internal_user_viewer` role values. This covers current Company admin/member/viewer storage without adding a new role table.
- Company admin remains the existing `LiteLLM_OrganizationMembership.organization_id` plus `user_role = org_admin` compatibility backing.
- Project admin/member/operator remains the existing Project backing team (`LiteLLM_ProjectTable.team_id`) plus `LiteLLM_TeamTable.members_with_roles` and `team_member_permissions`.
- Proxy admin and proxy admin view-only compatibility remains role-based through existing LiteLLM user roles.

No migration or frontend change is required for the MCP management Company/Project authorization slice:

- `LiteLLM_MCPServerTable` has no Company or Project ownership columns, so MCP server create/update/delete/approve/reject remain global proxy-admin workflows rather than fake tenant-scoped workflows.
- Team-scoped MCP discovery already has an authoritative owner path through `LiteLLM_TeamTable.object_permission.mcp_servers`; Company context is the existing `LiteLLM_TeamTable.organization_id` compatibility column and Project context is the existing backing team membership path.
- A future tenant-owned MCP server management slice would need a real persistence change, for example nullable `company_id` and `project_id` ownership columns on `LiteLLM_MCPServerTable` or an explicit ownership join table, plus backfill rules for existing global servers.

No migration is required for the Virtual Keys create/edit Company+Project payload slice. The key persistence columns already exist:

- `LiteLLM_VerificationToken.organization_id` remains the internal Company compatibility column.
- `LiteLLM_VerificationToken.project_id` remains the Project attribution column.
- Backend request models already accept `company_id`/`project_id`, reject conflicting `company_id` and `organization_id`, and strip `company_id` before DB persistence while keeping `organization_id` internally.

No migration is required for the final product-facing Organization removal audit. The runtime patch changes only FastAPI OpenAPI metadata so `/company/info` and `/v2/team/list` keep accepting hidden legacy `organization_id` aliases without exposing them as product API parameters. Persistence remains the existing LiteLLM Organization compatibility tables and Company/Project columns already documented above.

Before applying, verify schema copies are identical:

```bash
diff schema.prisma litellm/proxy/schema.prisma
diff schema.prisma litellm-proxy-extras/litellm_proxy_extras/schema.prisma
```

Focused Projects product-surface verification:

```bash
uv run pytest -q tests/enterprise/litellm_enterprise/proxy/management_endpoints/test_project_endpoints_prisma.py -k "project_admin_from_team_members_can_manage_project or project_member_without_admin_role_cannot_manage_project or project_request_accepts_company_id or project_company_context_rejects or list_projects_accepts_company_filter or list_projects_rejects_conflicting"
cd ui/litellm-dashboard && npx vitest run src/app/'(dashboard)'/hooks/projects/useProjects.test.ts src/app/'(dashboard)'/hooks/projects/useCreateProject.test.ts src/app/'(dashboard)'/hooks/projects/useUpdateProject.test.ts src/components/Projects/ProjectsPage.test.tsx src/components/Projects/ProjectDetailsPage.test.tsx src/components/Projects/ProjectModals/ProjectBaseForm.test.tsx src/components/Projects/ProjectModals/projectFormUtils.test.ts
cd ui/litellm-dashboard && npm run build
rsync -a --delete ui/litellm-dashboard/out/ litellm/proxy/_experimental/out/
rm -rf ui/litellm-dashboard/out
git diff --check
```

Focused runtime request attribution verification:

```bash
uv run pytest -q tests/test_litellm/proxy/test_chat_completion_metadata.py -k "metadata_population"
uv run pytest -q tests/test_litellm/proxy/hooks/test_proxy_track_cost_callback.py -k "enrich_failure_metadata_with_full_key_lookup"
uv run pytest -q tests/test_litellm/proxy/test_litellm_pre_call_utils.py -k "runtime_request_attribution_uses_company_project_context"
uv run pytest -q tests/test_litellm/proxy/auth/test_user_api_key_auth.py -k "usage_attribution_from_project_team or ambiguous_team_project_unattributed"
uv run pytest -q tests/test_litellm/proxy/db/test_db_spend_update_writer.py -k "batch_database_updates_routes_company_project_attribution or add_spend_log_transaction_to_daily_project_transaction_queues_update"
uv run pytest -q tests/test_litellm/proxy/spend_tracking/test_spend_tracking_utils.py -k "get_logging_payload_includes_project_id_from_auth_metadata"
uv run pytest -q tests/test_litellm/proxy/spend_tracking/test_spend_management_endpoints.py -k "virtual_key_company_project_usage_is_visible_in_logs_and_daily_activity or ui_view_spend_logs_with_company_and_project_filters"
uv run pytest -q tests/test_litellm/proxy/management_endpoints/test_activity_tenant_scoping.py -k "project_activity_accepts_project_id_and_company_id_filters"
uv run pytest -q tests/test_litellm/proxy/management_endpoints/test_organization_endpoints.py -k "get_company_daily_activity_accepts_company_id"
uv run pytest -q tests/test_litellm/proxy/management_endpoints/test_common_daily_activity.py -k "runtime_project_spend_for_product_filter or runtime_company_spend_for_product_filter"
uv run python -m compileall litellm/proxy/proxy_server.py litellm/proxy/hooks/proxy_track_cost_callback.py litellm/proxy/_types.py litellm/proxy/litellm_pre_call_utils.py litellm/proxy/spend_tracking/spend_tracking_utils.py litellm/proxy/db/db_spend_update_writer.py tests/test_litellm/proxy/spend_tracking/test_spend_management_endpoints.py
git diff --check
```

Apply with the proxy migrations package:

```bash
DATABASE_URL="<POSTGRES_URL>" uv run prisma migrate status --schema litellm-proxy-extras/litellm_proxy_extras/schema.prisma
DATABASE_URL="<POSTGRES_URL>" uv run prisma migrate deploy --schema litellm-proxy-extras/litellm_proxy_extras/schema.prisma
```

Rollback only before runtime writer/UI changes depend on this schema:

```sql
DROP TABLE IF EXISTS "LiteLLM_DailyProjectSpend";
DROP INDEX IF EXISTS "LiteLLM_VerificationToken_organization_id_idx";
DROP INDEX IF EXISTS "LiteLLM_VerificationToken_project_id_idx";
DROP INDEX IF EXISTS "LiteLLM_DeletedVerificationToken_project_id_idx";
DROP INDEX IF EXISTS "LiteLLM_SpendLogs_project_id_startTime_idx";
DROP INDEX IF EXISTS "LiteLLM_SpendLogs_organization_id_startTime_idx";
DROP INDEX IF EXISTS "LiteLLM_ManagedVectorStoresTable_project_id_idx";
DROP INDEX IF EXISTS "LiteLLM_AgentsTable_company_id_idx";
DROP INDEX IF EXISTS "LiteLLM_AgentsTable_project_id_idx";
ALTER TABLE "LiteLLM_SpendLogs" DROP COLUMN IF EXISTS "project_id";
ALTER TABLE "LiteLLM_ManagedVectorStoresTable" DROP COLUMN IF EXISTS "project_id";
ALTER TABLE "LiteLLM_AgentsTable" DROP COLUMN IF EXISTS "company_id";
ALTER TABLE "LiteLLM_AgentsTable" DROP COLUMN IF EXISTS "project_id";
```

## Backend Tests

Focused Company/Project migration readiness checks:

```bash
uv run pytest -q tests/proxy_unit_tests/test_db_schema_changes.py -k "cavadalabs_company_project_runtime_fields_have_migration_coverage or project_usage_migration_backfill_uses_request_metadata_and_existing_projects"
/usr/bin/env DATABASE_URL=postgresql://litellm:litellm@localhost:5432/litellm uv run prisma validate --schema schema.prisma
/usr/bin/env DATABASE_URL=postgresql://litellm:litellm@localhost:5432/litellm uv run prisma validate --schema litellm/proxy/schema.prisma
/usr/bin/env DATABASE_URL=postgresql://litellm:litellm@localhost:5432/litellm uv run prisma validate --schema litellm-proxy-extras/litellm_proxy_extras/schema.prisma
diff schema.prisma litellm/proxy/schema.prisma
diff schema.prisma litellm-proxy-extras/litellm_proxy_extras/schema.prisma
uv run python -m compileall tests/proxy_unit_tests/test_db_schema_changes.py
git diff --check
```

Focused model access policies/budgets/rate-limit checks:

```bash
uv run pytest -q tests/test_litellm/proxy/management_endpoints/test_budget_endpoints.py
uv run pytest -q tests/test_litellm/proxy/management_endpoints/test_access_group_endpoints.py
uv run python -m compileall litellm/proxy/management_endpoints/budget_management_endpoints.py
git diff --check
```

Focused Chatbots/A2A Agents Company/Project checks:

```bash
uv run python -m compileall litellm/proxy/agent_endpoints/endpoints.py litellm/proxy/agent_endpoints/agent_registry.py litellm/proxy/auth/auth_checks.py litellm/types/agents.py
/usr/bin/env DATABASE_URL=postgresql://litellm:litellm@localhost:5432/litellm uv run prisma validate --schema schema.prisma
diff schema.prisma litellm/proxy/schema.prisma
diff schema.prisma litellm-proxy-extras/litellm_proxy_extras/schema.prisma
uv run pytest -q tests/test_litellm/proxy/agent_endpoints/test_endpoints.py -k "company_scoped_agent or project_scoped_agent or caller_company_scope or outside_company or moving_agent"
uv run pytest -q tests/test_litellm/proxy/auth/test_auth_checks.py -k "agent_key_when_company_project_context_matches or agent_key_when_company_context_mismatches or agent_key_when_project_context_mismatches"
git diff --check
```

Focused RAG/Vector Stores Company/Project checks:

```bash
/usr/bin/env DATABASE_URL=postgresql://litellm:litellm@localhost:5432/litellm uv run prisma validate --schema schema.prisma
/usr/bin/env DATABASE_URL=postgresql://litellm:litellm@localhost:5432/litellm uv run prisma validate --schema litellm/proxy/schema.prisma
/usr/bin/env DATABASE_URL=postgresql://litellm:litellm@localhost:5432/litellm uv run prisma validate --schema litellm-proxy-extras/litellm_proxy_extras/schema.prisma
diff schema.prisma litellm/proxy/schema.prisma
diff schema.prisma litellm-proxy-extras/litellm_proxy_extras/schema.prisma
uv run python -m compileall litellm/proxy/vector_store_endpoints/management_endpoints.py litellm/proxy/vector_store_endpoints/utils.py litellm/proxy/rag_endpoints/endpoints.py enterprise/litellm_enterprise/proxy/hooks/managed_vector_stores.py litellm/types/vector_stores.py
uv run pytest -q tests/test_litellm/proxy/vector_store_endpoints/test_vector_store_endpoints.py -k "company_project or vector_store_project or list_vector_stores_filters"
uv run pytest -q tests/test_litellm/proxy/vector_store_endpoints/test_vector_store_tenant_guard.py -k "rag_ingest_persists_company_project_context"
uv run pytest -q tests/test_litellm/proxy/vector_store_endpoints/test_vector_store_access_control.py
uv run pytest -q tests/test_new_vector_store_endpoints.py -k "managed_vector_store"
git diff --check
```

Focused Usage/Billing Company/Project checks:

```bash
cd ui/litellm-dashboard && npx vitest run src/components/common_components/OrganizationDropdown.test.tsx src/components/view_logs/index.test.tsx src/components/view_logs/LogDetailsDrawer/LogDetailContent.test.tsx src/components/view_logs/log_filter_logic.test.tsx src/components/UsagePage/components/UsageViewSelect/UsageViewSelect.test.tsx src/components/UsagePage/components/EntityUsage/EntityUsage.test.tsx
cd ui/litellm-dashboard && npx vitest run src/components/UsagePage/components/UsagePageView.test.tsx src/components/UsagePage/components/EntityUsage/EntityUsage.test.tsx src/components/networking.test.ts -t "project usage|project daily activity"
cd ui/litellm-dashboard && npm run build
rsync -a --delete ui/litellm-dashboard/out/ litellm/proxy/_experimental/out/
uv run pytest -q tests/test_litellm/proxy/spend_tracking/test_spend_management_endpoints.py -k "company_project_filters_apply_to_raw_sql or with_company_and_project_filters or company_admin_can_view_company_project_scope or company_admin_rejects_outside_company or rejects_project_outside_requested_company or rejects_project_without_project_permission or rejects_conflicting_company_aliases"
uv run pytest -q tests/test_litellm/proxy/spend_tracking/test_spend_management_endpoints.py -k "virtual_key_company_project_usage_is_visible_in_logs_and_daily_activity"
uv run pytest -q tests/test_litellm/proxy/management_endpoints/test_activity_tenant_scoping.py -k "project_activity_accepts_project_id_and_company_id_filters or project_activity_accepts_organization_id_as_company_compat_alias or project_activity_rejects_conflicting_company_and_organization_aliases"
uv run pytest -q tests/enterprise/litellm_enterprise/proxy/management_endpoints/test_project_endpoints_prisma.py -k "project_daily_activity_company_admin"
uv run pytest -q tests/test_litellm/proxy/management_endpoints/test_organization_endpoints.py -k "daily_activity_accepts_company"
git diff --check
```

Focused Company/Project usage authorization contract checks:

```bash
uv run pytest -q tests/test_litellm/proxy/spend_tracking/test_spend_management_endpoints.py -k "ui_view_spend_logs_company_admin_can_view_company_project_scope or ui_view_spend_logs_company_admin_rejects_outside_company or ui_view_spend_logs_rejects_project_outside_requested_company or ui_view_spend_logs_rejects_project_without_project_permission"
uv run pytest -q tests/test_litellm/proxy/spend_tracking/test_spend_management_endpoints.py -k "project_member_with_permission_can_filter_by_company_and_project or spend_logs_v2_project_member_with_permission_is_project_scoped"
uv run pytest -q tests/test_litellm/proxy/management_endpoints/test_organization_endpoints.py -k "company_daily_activity_non_admin_allowed_company_scope or company_daily_activity_company_member_can_read_company_scope or company_daily_activity_non_admin_rejects_cross_company_scope or company_daily_activity_proxy_admin_can_view_any_company_scope or get_organization_daily_activity_non_admin_unauthorized_org_raises"
uv run pytest -q tests/test_litellm/proxy/management_endpoints/test_activity_tenant_scoping.py -k "project_activity_company_admin_can_view_own_company_project or project_activity_company_admin_rejects_project_outside_company_scope or project_activity_accepts_project_id_and_company_id_filters"
uv run pytest -q tests/enterprise/litellm_enterprise/proxy/management_endpoints/test_project_endpoints_prisma.py -k "project_daily_activity_restricts_non_admin_to_user_projects or project_daily_activity_company_admin_can_view_company_projects or project_daily_activity_company_admin_rejects_project_outside_company"
uv run python -m compileall tests/test_litellm/proxy/spend_tracking/test_spend_management_endpoints.py tests/test_litellm/proxy/management_endpoints/test_organization_endpoints.py tests/test_litellm/proxy/management_endpoints/test_activity_tenant_scoping.py
git diff --check
```

Focused Virtual Keys Company/Project checks:

```bash
uv run pytest -q tests/test_litellm/proxy/management_endpoints/test_key_management_endpoints.py -k "company_id or matching_company_and_organization_aliases or project_context or list_key_helper_returns_company_and_project_context or list_keys_accepts_company_id_filter or list_keys_rejects_conflicting_company_and_organization_id or key_request_schema_marks_organization_id_internal_deprecated or key_view_schema_marks_organization_response_fields_internal_deprecated"
cd ui/litellm-dashboard && node_modules/vitest/vitest.mjs run src/components/VirtualKeysPage/VirtualKeysTable.test.tsx -t "should build Project filter options"
uv run python -m compileall litellm/proxy/_types.py litellm/proxy/management_endpoints/key_management_endpoints.py
git diff --check
```

Focused Virtual Keys create/edit Company+Project checks:

```bash
uv run pytest -q tests/test_litellm/proxy/management_endpoints/test_key_management_endpoints.py -k "key_requests_sync_company_project_aliases or generate_key_helper_strips_company_id_and_returns_company_project or prepare_key_update_data_strips_company_id_and_keeps_project_id or project_context_derives_company_and_team_for_key_request or project_context_rejects_conflicting_company_for_key_request"
uv run pytest -q tests/test_litellm/proxy/client/test_keys.py -k "generate_request_full or update_request_company_id or update_request_project_id or list_request_company_filter or list_request_legacy_organization_alias_maps_to_company_filter or list_request_rejects_conflicting_company_and_organization_aliases or list_request_project_filter"
cd ui/litellm-dashboard && node_modules/vitest/vitest.mjs run src/components/networking.test.ts src/components/organisms/create_key_button.test.tsx src/components/templates/key_edit_view.test.tsx
cd ui/litellm-dashboard && npm run build
rsync -a --delete ui/litellm-dashboard/out/ litellm/proxy/_experimental/out/
git diff --check -- ui/litellm-dashboard/src/components/networking.tsx ui/litellm-dashboard/src/components/networking.test.ts docs/CAVADALABS_OPERATIONS.md
```

Focused Company/Project authorization checks:

```bash
uv run pytest -q tests/test_litellm/proxy/management_endpoints/test_common_utils.py -k "CompanyProjectAccessContext"
uv run pytest -q tests/test_litellm/proxy/management_endpoints/test_key_management_endpoints.py -k "validate_key_list_check_team_admin_success or validate_key_list_check_team_admin_fail or list_keys_company_admin_scope_filters_all_visibility_branches or list_keys_project_admin_scope_uses_full_project_visibility or list_keys_project_member_with_route_permission_uses_full_project_visibility or list_keys_project_member_without_route_permission_is_member_scoped or list_keys_rejects_project_scope_for_non_member_outside_company or build_key_filter_project_id or list_keys_accepts_company_project_filters or list_keys_rejects_conflicting_company_and_organization_filters"
uv run pytest -q tests/test_litellm/proxy/management_endpoints/test_key_management_endpoints.py -k "key_info_company_admin_can_read_company_project_key or key_info_project_member_can_read_backing_team_key or key_info_key_owner_without_project_access_is_denied or key_info_proxy_admin_can_read_any_company_project_key or can_delete_verification_token_key_owner_without_project_access_denied or can_delete_verification_token_company_admin_team_key or can_delete_verification_token_team_member_with_explicit_delete_permission or can_delete_verification_token_proxy_admin_team_key"
uv run pytest -q tests/test_litellm/proxy/spend_tracking/test_spend_management_endpoints.py -k "spend_logs_v2_project_member_with_permission_is_project_scoped or spend_logs_v2_company_admin_rejects_outside_company or ui_view_spend_logs_company_admin_can_view_company_project_scope or ui_view_spend_logs_company_admin_rejects_outside_company or ui_view_spend_logs_rejects_project_outside_requested_company or ui_view_spend_logs_rejects_project_without_project_permission"
uv run python -m compileall litellm/proxy/management_endpoints/common_utils.py litellm/proxy/management_endpoints/key_management_endpoints.py litellm/proxy/spend_tracking/spend_management_endpoints.py
git diff --check
```

Focused MCP management Company/Project authorization checks:

```bash
uv run pytest -q tests/test_litellm/proxy/management_endpoints/test_mcp_management_endpoints.py -k "TeamScopedMCPServerAccess"
uv run python -m compileall litellm/proxy/management_endpoints/mcp_management_endpoints.py tests/test_litellm/proxy/management_endpoints/test_mcp_management_endpoints.py
git diff --check
```

Focused Server API Key allowed vector store enforcement checks:

```bash
uv run pytest -q tests/test_litellm/proxy/management_endpoints/test_key_management_endpoints.py -k "vector_store or object_permission"
uv run pytest -q tests/test_litellm/proxy/vector_store_endpoints/test_vector_store_endpoints.py -k "TestCheckVectorStoreAccess or key_object_permission"
uv run python -m compileall litellm/proxy/management_endpoints/key_management_endpoints.py litellm/proxy/vector_store_endpoints/utils.py
git diff --check
```

Focused Safety/Guardrails Company/Project checks:

```bash
uv run pytest -q tests/test_litellm/proxy/guardrails/test_guardrail_endpoints.py -k "list_guardrails_v2_filters_by_project_company_scope or list_guardrails_v2_allows_project_member_project_scope or list_guardrails_v2_allows_company_admin_company_scope or list_guardrails_v2_rejects_project_outside_company_admin_scope or list_guardrails_v2_rejects_conflicting_company_aliases or register_guardrail_with_company_project_persists_project_context or register_guardrail_rejects_project_outside_company or list_guardrail_submissions_filters_by_company_project or guardrail_submissions_schema_uses_product_company_project_filters"
uv run python -m compileall litellm/proxy/guardrails/guardrail_endpoints.py
/usr/bin/env DATABASE_URL=postgresql://litellm:litellm@localhost:5432/litellm uv run prisma validate --schema schema.prisma
/usr/bin/env DATABASE_URL=postgresql://litellm:litellm@localhost:5432/litellm uv run prisma validate --schema litellm/proxy/schema.prisma
/usr/bin/env DATABASE_URL=postgresql://litellm:litellm@localhost:5432/litellm uv run prisma validate --schema litellm-proxy-extras/litellm_proxy_extras/schema.prisma
diff schema.prisma litellm/proxy/schema.prisma
diff schema.prisma litellm-proxy-extras/litellm_proxy_extras/schema.prisma
git diff --check
```

Focused Users and Teams Company/Project management contract checks:

```bash
uv run pytest -q tests/test_litellm/proxy/management_endpoints/test_internal_user_endpoints.py -k "new_user_request_accepts_company_ids_alias or new_user_request_accepts_company_id_alias or new_user_request_rejects_conflicting_company_id_and_organization_id or new_user_and_update_user_request_accept_project_ids or update_user_request_accepts_company_id_and_project_id_aliases or user_info_v2_schema_exposes_company_project_without_organization_aliases or user_info_v2_response_shape or new_user_company_id_alias_maps_to_company_membership or update_user_company_id_alias_maps_to_membership_and_sanitizes_persistence or get_users_filters_and_returns_company_project_context or project_admin_can_update_user_project_context_without_company_admin or project_member_cannot_create_user_project_context_without_admin_role or company_admin_can_create_user_company_context or company_admin_cannot_create_user_outside_company_context or company_admin_can_update_user_company_context or company_admin_cannot_update_user_outside_company_context"
uv run pytest -q tests/test_litellm/proxy/management_endpoints/test_team_endpoints.py -k "team_requests_accept_company_id_alias or team_requests_reject_conflicting_company_and_organization_id or team_request_schema_marks_organization_id_internal_deprecated or team_list_schema_exposes_company_project_and_hides_legacy_organization_alias or team_db_payload_keeps_internal_company_and_drops_product_context_fields or build_team_list_where_conditions_filters_by_project_team_ids or convert_teams_to_response_models_preserves_company_project_fields or enrich_team_dicts_with_company_project_context"
/usr/bin/env DATABASE_URL=postgresql://litellm:litellm@localhost:5432/litellm uv run prisma validate --schema schema.prisma
diff schema.prisma litellm/proxy/schema.prisma
diff schema.prisma litellm-proxy-extras/litellm_proxy_extras/schema.prisma
git diff --check
```

Focused final product-facing Organization removal checks:

```bash
uv run pytest -q tests/test_litellm/proxy/management_endpoints/test_organization_endpoints.py -k "company_info_schema_exposes_company_id_and_hides_legacy_organization_alias"
uv run pytest -q tests/test_litellm/proxy/management_endpoints/test_team_endpoints.py -k "team_list_schema_exposes_company_project_and_hides_legacy_organization_alias"
uv run python -m compileall litellm/proxy/management_endpoints/organization_endpoints.py litellm/proxy/management_endpoints/team_endpoints.py
git diff --check
```

## Frontend Tests

Focused model access policies/budgets/rate-limit UI checks:

```bash
cd ui/litellm-dashboard
node_modules/vitest/vitest.mjs run src/components/budgets/budget_panel.test.tsx src/components/AccessGroups/AccessGroupsPage.test.tsx src/components/policies/policy_templates.test.tsx
npm run build
rsync -a --delete out/ ../../litellm/proxy/_experimental/out/
cd ../..
rm -rf ui/litellm-dashboard/out
git diff --check
```

Focused Chatbots/A2A Agents Company/Project UI checks:

```bash
cd ui/litellm-dashboard
NODE_OPTIONS='--experimental-require-module' node_modules/vitest/vitest.mjs run src/components/networking.test.ts src/components/agents.test.tsx
npm run build
rsync -a --delete out/ ../../litellm/proxy/_experimental/out/
cd ../..
rm -rf ui/litellm-dashboard/out
git diff --check
```

Focused RAG/Vector Stores Company/Project UI checks:

```bash
cd ui/litellm-dashboard
npx vitest run src/components/vector_store_management/CreateVectorStore.test.tsx src/components/vector_store_management/VectorStoreForm.test.tsx src/components/vector_store_management/VectorStoreTable.test.tsx
npm run build
rsync -a --delete out/ ../../litellm/proxy/_experimental/out/
cd ../..
rm -rf ui/litellm-dashboard/out
git diff --check
```

Focused Usage/Billing Company/Project UI checks:

```bash
cd ui/litellm-dashboard
node node_modules/vitest/vitest.mjs run src/components/UsagePage/components/UsagePageView.test.tsx src/components/UsagePage/components/EntityUsage/EntityUsage.test.tsx src/components/view_logs/log_filter_logic.test.tsx src/components/networking.test.ts
cd ../..
git diff --check
```

Focused Virtual Keys Company/Project UI checks:

```bash
cd ui/litellm-dashboard
npx vitest run src/components/vector_store_management/VectorStoreSelector.test.tsx src/components/organisms/create_key_button.test.tsx src/components/templates/key_edit_view.test.tsx src/components/VirtualKeysPage/VirtualKeysTable.test.tsx src/components/team/TeamVirtualKeysTable.test.tsx src/components/key_team_helpers/filter_logic.test.tsx src/components/key_team_helpers/filter_helpers.test.ts src/app/'(dashboard)'/hooks/keys/useKeys.test.ts
npm run build
rsync -a --delete out/ ../../litellm/proxy/_experimental/out/
cd ../..
rm -rf ui/litellm-dashboard/out
git diff --check
```

Focused Safety/Guardrails Company/Project UI checks:

```bash
cd ui/litellm-dashboard
node_modules/vitest/vitest.mjs run src/components/guardrails/GuardrailSelector.test.tsx src/components/guardrails/TeamGuardrailsTab.test.tsx
npm run build
rsync -a --delete out/ ../../litellm/proxy/_experimental/out/
cd ../..
rm -rf ui/litellm-dashboard/out
git diff --check
```

Focused Users and Teams Company/Project management contract UI checks:

```bash
cd ui/litellm-dashboard
node_modules/vitest/vitest.mjs run src/components/networking.test.ts src/components/CreateUserButton.test.tsx src/components/user_edit_view.test.tsx src/components/view_users/table.test.tsx src/components/view_users/user_info_view.test.tsx
node_modules/vitest/vitest.mjs run src/components/networking.test.ts src/app/'(dashboard)'/teams/components/TeamsFilters.test.tsx src/app/'(dashboard)'/teams/components/TeamsTable/TeamsTable.test.tsx src/components/team/TeamInfo.test.tsx
cd ../..
git diff --check
```

Run the dashboard build and sync the static bundle only when frontend source changes in this slice:

```bash
cd ui/litellm-dashboard
npm run build
rsync -a --delete out/ ../../litellm/proxy/_experimental/out/
cd ../..
rm -rf ui/litellm-dashboard/out
```

Frontend RBAC note: Server API Key create/edit keeps Company and Project selectors visible instead of applying incomplete client-side Company/Project write filtering. The backend remains authoritative for proxy admin, Company admin, Project admin, and route-specific team permission checks. Users and Teams views do not receive enough route-level Project permission context to implement reliable client-side RBAC, so their write controls should not be treated as the security boundary.

## Smoke Tests

Required environment:

```bash
export DATABASE_URL="<POSTGRES_URL>"
export COMPANY_ID="<existing_company_id>"
export PROJECT_ID="<existing_project_id>"
export USER_ID="<existing_user_id>"
export VECTOR_STORE_ID="<existing_vector_store_id>"
```

After migration deploy and runtime rollout, verify Project persistence primitives:

```bash
psql "$DATABASE_URL" -c 'SELECT column_name FROM information_schema.columns WHERE table_name = '"'"'LiteLLM_SpendLogs'"'"' AND column_name IN ('"'"'organization_id'"'"', '"'"'project_id'"'"') ORDER BY column_name;'
psql "$DATABASE_URL" -c 'SELECT indexname FROM pg_indexes WHERE tablename IN ('"'"'LiteLLM_SpendLogs'"'"', '"'"'LiteLLM_DailyProjectSpend'"'"') AND indexname IN ('"'"'LiteLLM_SpendLogs_organization_id_startTime_idx'"'"', '"'"'LiteLLM_SpendLogs_project_id_startTime_idx'"'"', '"'"'LiteLLM_SpendLogs_api_key_startTime_idx'"'"', '"'"'LiteLLM_DailyProjectSpend_project_id_date_idx'"'"') ORDER BY indexname;'
psql "$DATABASE_URL" -c 'SELECT COUNT(*) AS spend_logs_with_project_id FROM "LiteLLM_SpendLogs" WHERE "project_id" IS NOT NULL;'
psql "$DATABASE_URL" -c 'SELECT COUNT(*) AS daily_project_rows FROM "LiteLLM_DailyProjectSpend";'
psql "$DATABASE_URL" -v project_id="$PROJECT_ID" -c "SELECT COUNT(*) AS selected_project_daily_rows FROM \"LiteLLM_DailyProjectSpend\" WHERE \"project_id\" = :'project_id';"
```

Diagnose historical Project attribution before and after migration:

```bash
psql "$DATABASE_URL" <<'SQL'
WITH spend AS (
  SELECT
    NULLIF("project_id", '') AS stored_project_id,
    CASE
      WHEN "metadata" IS NOT NULL AND jsonb_typeof("metadata") = 'object'
      THEN NULLIF("metadata"->>'user_api_key_project_id', '')
      ELSE NULL
    END AS metadata_project_id,
    "api_key"
  FROM "LiteLLM_SpendLogs"
)
SELECT
  COUNT(*) FILTER (WHERE stored_project_id IS NOT NULL) AS spend_logs_with_project_id,
  COUNT(*) FILTER (WHERE stored_project_id IS NULL AND metadata_project_id IS NOT NULL) AS metadata_project_candidates,
  COUNT(*) FILTER (WHERE stored_project_id IS NULL AND metadata_project_id IS NOT NULL AND p."project_id" IS NOT NULL) AS metadata_project_candidates_existing_project,
  COUNT(*) FILTER (WHERE stored_project_id IS NULL AND metadata_project_id IS NOT NULL AND p."project_id" IS NULL) AS metadata_project_candidates_missing_project,
  COUNT(*) FILTER (WHERE stored_project_id IS NULL AND metadata_project_id IS NULL) AS unattributable_without_request_project_metadata
FROM spend s
LEFT JOIN "LiteLLM_ProjectTable" p
  ON p."project_id" = s.metadata_project_id;
SQL
```

Rows in `unattributable_without_request_project_metadata` must not be backfilled by joining current keys or current backing teams; that would use mutable state and can rewrite history. This diagnostic only measures the risk:

```bash
psql "$DATABASE_URL" <<'SQL'
SELECT COUNT(*) AS unsafe_current_key_only_candidates
FROM "LiteLLM_SpendLogs" sl
JOIN "LiteLLM_VerificationToken" v
  ON v."token" = sl."api_key"
WHERE NULLIF(sl."project_id", '') IS NULL
  AND (
    sl."metadata" IS NULL
    OR jsonb_typeof(sl."metadata") <> 'object'
    OR NULLIF(sl."metadata"->>'user_api_key_project_id', '') IS NULL
  )
  AND NULLIF(v."project_id", '') IS NOT NULL;
SQL
```

Proxy smoke:

```bash
curl -sS -H "Authorization: Bearer $LITELLM_MASTER_KEY" "http://localhost:4000/company/daily/activity?company_id=$COMPANY_ID&start_date=2026-05-01&end_date=2026-05-17&page_size=10"
curl -sS -H "Authorization: Bearer $LITELLM_MASTER_KEY" "http://localhost:4000/project/daily/activity?company_id=$COMPANY_ID&project_id=$PROJECT_ID&start_date=2026-05-01&end_date=2026-05-17&page_size=10"
curl -sS -H "Authorization: Bearer $LITELLM_MASTER_KEY" "http://localhost:4000/spend/logs/v2?company_id=$COMPANY_ID&project_id=$PROJECT_ID&start_date=2026-05-01&end_date=2026-05-17&page=1&page_size=10"
curl -sS -H "Authorization: Bearer $LITELLM_MASTER_KEY" "http://localhost:4000/spend/logs/ui?company_id=$COMPANY_ID&project_id=$PROJECT_ID&start_date=2026-05-01%2000:00:00&end_date=2026-05-17%2023:59:59&page=1&page_size=10"
curl -sS -H "Authorization: Bearer $LITELLM_MASTER_KEY" "http://localhost:4000/vector_store/list?company_id=$COMPANY_ID&project_id=$PROJECT_ID&page=1&page_size=10"
curl -sS -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H "Content-Type: application/json" -d "{\"vector_store_id\":\"$VECTOR_STORE_ID\"}" "http://localhost:4000/vector_store/info"
```

Dashboard smoke:

- Open Tools > Vector Stores.
- Create a vector store by selecting Company and Project, upload one small document, and verify the resulting row shows the selected Company and Project.
- Open vector store detail/edit and verify Company and Project are visible and remain selected after save.
- Open Usage.
- Select Company Usage and verify company-filtered spend loads.
- Select Project Usage, optionally filter by Company, and verify project-filtered spend loads.
- Open Logs/Billing request logs.
- Filter by Company and Project and verify request rows show Company and Project columns.

## Repair And Backfill

The migration backfills only from `LiteLLM_SpendLogs.metadata->>'user_api_key_project_id'` when that Project still exists in `LiteLLM_ProjectTable`. Do not backfill Project usage by joining current `LiteLLM_VerificationToken.project_id`; keys can move and that would rewrite historical attribution.

If a deploy fails after adding the column but before the aggregate insert completes, inspect `_prisma_migrations` first. Re-run only the idempotent UPDATE/INSERT statements from `20260517120000_add_project_spend_usage/migration.sql` after confirming Prisma will not retry the migration itself.

## Deployment Notes

- Do not deploy without a clean `git status --short` except for the intended feature files.
- Do not run migrations until the migration section above has been updated for the current feature.
- Do not reuse stale commands from prior features.
- When the restarted branch is ready to publish, use an explicit push target decided by the user. If replacing the old remote integration branch, use `--force-with-lease`, not plain `--force`.
