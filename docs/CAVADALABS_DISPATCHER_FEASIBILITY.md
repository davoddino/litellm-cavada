# CavadaLabs Dispatcher Feasibility Report

Date: 2026-05-13

Repository inspected: LiteLLM fork at `litellm-cavada`

Working title: CavadaLabs Dispatcher

## A. Executive Summary

### Feasibility verdict

Turning this LiteLLM fork into the first version of a proprietary AI Model Dispatcher and Orchestrator platform is feasible. LiteLLM is a strong base for the online dispatcher because the repository already contains the most difficult generic gateway capabilities:

- OpenAI-compatible proxy endpoints.
- Provider abstraction across many external AI providers.
- Router, model groups, model aliases, fallbacks, cooldowns and health checks.
- Virtual keys, users, teams, organizations, budgets and spend tracking.
- Postgres-backed persistence through Prisma.
- Redis-backed cache, rate limits, cooldowns, locks and temporary state.
- Streaming support.
- Callback and hook system.
- Docker-based production deployment.
- A dashboard that already exposes keys, teams, models, logs, usage and settings.

The recommended approach is not to rewrite LiteLLM into CavadaLabs Dispatcher. Instead, keep the LiteLLM proxy as the dispatching engine and add CavadaLabs-specific product concepts around it through extension points and isolated modules.

### Recommended architecture

Use LiteLLM as the runtime gateway and add a CavadaLabs layer with these responsibilities:

1. Dashboard and admin API
   - Start from the LiteLLM dashboard.
   - Add CavadaLabs-specific admin pages gradually.
   - Use Supabase Auth for dashboard users through a bridge into LiteLLM roles/users.
   - Keep internal admin workflows first, tenant-restricted views later.

2. Runtime auth
   - Use LiteLLM virtual keys for server-to-server project API keys.
   - Add CavadaLabs short-lived browser session tokens for public chatbot widgets.
   - Validate browser session tokens in a custom auth layer before request routing.

3. Model aliases and routing
   - Use LiteLLM `model_list`, model groups, `model_group_alias`, key aliases and team aliases where they are enough.
   - Add CavadaLabs per-project alias and routing policy tables for product-specific rules.
   - Resolve policies in a CavadaLabs pre-call/auth layer that selects a LiteLLM model group or deployment.

4. Local nodes
   - V1 should expose Orchestra/local nodes as OpenAI-compatible endpoints.
   - Register healthy local nodes as LiteLLM deployments using `custom_openai` or OpenAI-compatible provider settings.
   - Add a CavadaLabs node registry and heartbeat system outside LiteLLM core routing internals.
   - Implement a custom LiteLLM provider only after the local node protocol requires non-OpenAI semantics.

5. Logging and cost tracking
   - Keep LiteLLM spend logs and daily spend tables.
   - Add a CavadaLabs request ledger and request attempts table.
   - Keep prompt and response logging disabled by default.
   - Store routing decisions, provider/node target, latency, tokens, cost and error details without raw payloads by default.

6. RAG
   - Keep RAG execution outside the dispatcher for V1.
   - Let the dispatcher handle auth, model routing, model calls and usage logging.
   - Let a separate CavadaLabs RAG service or module call the dispatcher for embeddings and generation.
   - Use the dashboard to manage RAG configuration, prompts and source metadata.

### What should not be modified

Avoid modifying these areas unless an extension point proves insufficient:

- `litellm/router.py`
- `litellm/main.py`
- Existing provider implementations under `litellm/llms/`
- Existing LiteLLM table semantics in `schema.prisma`
- Core request flow in `litellm/proxy/proxy_server.py`
- Core auth checks in `litellm/proxy/auth/auth_checks.py`
- Spend logging internals unless a callback cannot provide the needed ledger data
- Dashboard-wide auth and routing internals until the Supabase Auth integration design is finalized

These files are high-churn upstream areas. Deep edits there would make the fork harder to update.

### Overall upstream update risk

Medium if CavadaLabs code is isolated in new modules and LiteLLM is treated as the underlying gateway.

High if the fork rewrites dashboard auth, changes core Prisma models, modifies `router.py`, or changes the OpenAI-compatible request path.

## B. Repository Architecture Map

### Main backend areas

- `litellm/proxy/proxy_server.py`
  - Main FastAPI application.
  - Defines OpenAI-compatible routes such as `/v1/chat/completions`, `/chat/completions`, embeddings, model management, key management and many admin routes.
  - Loads config, custom auth, custom providers, callbacks, Redis, DB clients and startup jobs.
  - High upstream conflict risk if heavily modified.

- `litellm/proxy/common_request_processing.py`
  - Common request processing path for LLM calls.
  - Handles auth metadata, pre-call hook execution, LiteLLM call dispatch, response handling and streaming wrappers.

- `litellm/proxy/litellm_pre_call_utils.py`
  - Adds LiteLLM metadata to requests.
  - Applies key and team aliases.
  - Sanitizes internal fields.
  - Adds tags, request metadata, user/key/team/project metadata and request snapshots for logging.

- `litellm/proxy/route_llm_request.py`
  - Maps proxy route types to LiteLLM SDK/router calls.

- `litellm/router.py`
  - Core routing engine.
  - Supports model lists, fallbacks, cooldowns, health checks, deployment selection, streaming fallbacks, routing strategies and model group aliases.
  - Should remain mostly untouched.

- `litellm/router_strategy/`
  - Routing strategy implementations such as simple shuffle, latency, cost, least busy, tag-based routing and adaptive routing.

- `litellm/llms/`
  - Provider implementations.
  - Includes `openai_like` support and `custom_llm.py` for custom providers.

### Dashboard/UI areas

- `ui/litellm-dashboard/`
  - Next/React dashboard app.

- `ui/litellm-dashboard/src/app/(dashboard)/`
  - Dashboard pages.
  - Current structure includes pages for virtual keys, playground, models, organizations, teams, usage, logs, settings, policies, prompts, tools, budgets and related admin areas.

- `ui/litellm-dashboard/src/components/`
  - Shared dashboard components.
  - `leftnav.tsx` defines the main navigation groups.
  - Existing navigation already has concepts close to CavadaLabs needs: access control, models, usage, logs, settings and experimental prompts.

- `ui/litellm-dashboard/src/hooks/`
  - Frontend data hooks for models, keys, teams, organizations, projects, logs, router settings and UI config.

- `ui/litellm-dashboard/src/utils/roles.ts`
  - Dashboard role definitions.
  - Current roles include proxy admin, proxy admin viewer, org admin, internal user and internal user viewer.

- `ui/litellm-dashboard/src/components/login/`
  - Current login flow.
  - This is a likely conflict area for Supabase Auth.

### Database and migration areas

- `schema.prisma`
  - Main LiteLLM Prisma schema.
  - Uses Postgres through `DATABASE_URL`.
  - Contains organizations, teams, projects, users, virtual keys, spend logs, error logs, budgets, models, prompts, vector stores, health checks, audit logs and more.

- `litellm/proxy/db/`
  - Prisma client setup, DB utilities and migration support.

- `litellm/proxy/spend_tracking/`
  - Spend logging and async spend update pipeline.

- `litellm/proxy/management_endpoints/`
  - Core management endpoints.

- `enterprise/litellm_enterprise/proxy/management_endpoints/project_endpoints.py`
  - Project endpoints are present in enterprise code, not the core management endpoint folder.
  - This should be reviewed from a licensing and maintainability perspective before depending on it.

### Config areas

- `config.yaml`
  - Main proxy config file convention.

- `litellm/proxy/proxy_server_config.yaml`
  - Example proxy server config.

- `litellm/proxy/example_config_yaml/`
  - Useful examples for custom auth, callbacks, model lists and proxy settings.

- `pyproject.toml`
  - Package metadata and dependencies.
  - Inspected version is `litellm` `1.85.0`.

### Callback and hook areas

- `litellm/proxy/utils.py`
  - `ProxyLogging` implementation.
  - Runs pre-call hooks, post-call hooks, response header hooks, success handlers and failure handlers.

- `litellm/proxy/hooks/`
  - Built-in proxy hooks.
  - Includes spend tracking, budget enforcement and related hooks.

- `litellm/proxy/common_utils/callback_utils.py`
  - Callback initialization.

- `litellm/proxy/example_config_yaml/custom_callbacks.py`
  - Example custom callback implementation.
  - Good starting point for a CavadaLabs request ledger callback.

### Auth areas

- `litellm/proxy/auth/user_api_key_auth.py`
  - Main auth entry point for API keys, JWT/OAuth, virtual keys and custom auth.
  - Supports a user-defined `custom_auth` loaded from config.

- `litellm/proxy/auth/auth_checks.py`
  - Common auth checks for teams, projects, models, budgets, organizations and related access control.

- `litellm/proxy/_types.py`
  - Includes `UserAPIKeyAuth` and LiteLLM user/key/team role types.

- `litellm/proxy/example_config_yaml/custom_auth.py`
  - Example custom auth module.
  - Good starting point for Supabase JWT and CavadaLabs token validation.

### Routing and provider areas

- `litellm/router.py`
  - Main router.

- `litellm/router_strategy/`
  - Routing strategies.

- `litellm/llms/openai_like/`
  - OpenAI-compatible provider support.
  - Includes JSON provider registry support.

- `litellm/llms/custom_llm.py`
  - Custom provider base class.

- `litellm/main.py`
  - LiteLLM SDK request dispatch.
  - High upstream conflict risk.

### Docker and deployment areas

- `Dockerfile`
  - Multi-stage image build.
  - Builds the Python proxy and dashboard.
  - Exposes port `4000`.

- `docker-compose.yml`
  - Local deployment with LiteLLM, Postgres and Prometheus.

- `docker/prod_entrypoint.sh`
  - Runtime entrypoint used by the Dockerfile.

- `docker/entrypoint.sh`
  - Additional entrypoint that includes migration handling.

- `litellm/proxy/prisma_migration.py`
  - Prisma migration helper.

## C. Recommended Implementation Strategy

### Minimal fork approach

Keep the LiteLLM proxy as the gateway engine and add CavadaLabs modules around it:

- Use LiteLLM config for provider credentials, external models and OpenAI-compatible local-node deployments.
- Use LiteLLM virtual keys for long-lived server-to-server project keys.
- Use CavadaLabs short-lived session tokens for browser widgets.
- Use custom auth to validate Supabase dashboard tokens, project tokens and browser sessions.
- Use pre-call hooks or custom callbacks to resolve CavadaLabs routing policy before LiteLLM routing.
- Use LiteLLM router for provider selection, fallbacks, cooldowns and streaming.
- Use LiteLLM spend logs for standard cost and usage accounting.
- Add CavadaLabs request ledger tables for product-specific routing and privacy-safe audit data.
- Add CavadaLabs admin endpoints in a separate router.
- Add CavadaLabs dashboard pages with minimal changes to existing dashboard internals.

### Suggested CavadaLabs backend module layout

Recommended new module area:

```text
litellm/proxy/cavada/
  __init__.py
  admin_endpoints.py
  auth.py
  config.py
  db.py
  ledger.py
  node_registry.py
  node_gateway.py
  routing_policy.py
  sessions.py
  types.py
```

Recommended separate SQL migration area:

```text
supabase/migrations/
  20260513_cavada_dispatcher_core.sql

or

db_scripts/cavada/
  001_cavada_dispatcher_core.sql
```

Recommended dashboard module area:

```text
ui/litellm-dashboard/src/components/cavada/
ui/litellm-dashboard/src/hooks/cavada/
ui/litellm-dashboard/src/app/(dashboard)/cavada/
```

### Extension points to use first

1. `general_settings.custom_auth`
   - Validate CavadaLabs project tokens, Supabase JWTs and browser session tokens.
   - Return `UserAPIKeyAuth` with the correct org/team/project/user metadata.

2. LiteLLM virtual keys
   - Store long-lived server-to-server project API keys.
   - Attach keys to `organization_id`, `team_id` and `project_id` where possible.

3. LiteLLM `model_list`
   - Represent provider models and local node deployments.
   - Keep app-facing names as model groups or aliases.

4. Router `model_group_alias`
   - Map generic aliases to model groups when global aliasing is sufficient.

5. Key/team aliases
   - Use `LiteLLM_VerificationToken.aliases` and team model aliases where existing behavior fits.

6. Custom callback
   - Write CavadaLabs ledger records on success and failure.
   - Capture request id, alias, resolved provider/node, real model, latency, tokens, cost and errors.

7. Pre-call hook
   - Resolve CavadaLabs routing policy into a LiteLLM model group or concrete deployment.
   - Add routing decision metadata before the LiteLLM request is executed.

8. OpenAI-compatible local node endpoints
   - Register each healthy node as a LiteLLM deployment.
   - Avoid custom provider work in V1 if Orchestra can expose OpenAI-compatible APIs.

### What to avoid touching

- Do not replace LiteLLM's router with a CavadaLabs router.
- Do not modify provider internals for local nodes in V1.
- Do not put tenant-specific tables directly into existing LiteLLM models unless there is no other path.
- Do not store raw prompt/response payloads in spend logs by default.
- Do not make the browser widget use a long-lived virtual key.
- Do not place full RAG execution inside the dispatcher for V1.
- Do not deeply fork the dashboard before the product model is stable.

## D. Feature-by-Feature Feasibility Matrix

| Feature | Feasibility | Recommended approach | Expected files/modules | Upstream conflict risk | Estimated hours |
| --- | --- | --- | --- | --- | --- |
| Project and tenant management | Medium | Reuse LiteLLM org/team/project concepts where possible. Add CavadaLabs tables for apps, chatbots and product metadata. Check enterprise licensing before relying on existing project endpoints. | `schema.prisma`, `LiteLLM_OrganizationTable`, `LiteLLM_TeamTable`, `LiteLLM_ProjectTable`, `enterprise/litellm_enterprise/proxy/management_endpoints/project_endpoints.py`, `litellm/proxy/cavada/admin_endpoints.py`, dashboard Cavada pages | Medium | 40-90 |
| Supabase Auth integration | Medium to hard | Validate Supabase JWTs in a CavadaLabs auth bridge. Map `auth.users.id` to LiteLLM users and CavadaLabs memberships. For dashboard, either issue a LiteLLM-compatible session after Supabase login or adapt dashboard API auth. | `litellm/proxy/cavada/auth.py`, `litellm/proxy/auth/user_api_key_auth.py` via config hook, `ui/litellm-dashboard/src/components/login/`, `ui/litellm-dashboard/src/utils/roles.ts` | Medium to high if UI auth is deeply changed | 60-140 |
| Project API keys | Easy | Use LiteLLM virtual keys. Attach keys to organization/team/project. Add CavadaLabs metadata for app/chatbot ownership. | `LiteLLM_VerificationToken`, existing key endpoints, `litellm/proxy/cavada/admin_endpoints.py` | Low | 16-40 |
| Short-lived browser tokens | Medium | Add CavadaLabs session tokens. Mint from trusted backend/admin endpoint. Store session state in Redis with optional DB audit. Validate origin/domain, project, app, alias allowlist and expiry in custom auth. | `litellm/proxy/cavada/sessions.py`, `litellm/proxy/cavada/auth.py`, Redis, `cavada_project_tokens` or `cavada_widget_sessions` | Low to medium | 40-90 |
| Model aliases | Easy to medium | Use `model_list` public names, `model_group_alias`, key aliases and team aliases. Add `cavada_model_aliases` for per-project alias semantics. Resolve before routing. | `config.yaml`, `litellm/router.py` by config only, `litellm/proxy/litellm_pre_call_utils.py` existing behavior, `litellm/proxy/cavada/routing_policy.py` | Low | 24-70 |
| Routing policies | Medium to hard | Add CavadaLabs policy resolver that selects a LiteLLM model group/deployment and attaches decision metadata. Use LiteLLM fallbacks for common provider fallback behavior. | `litellm/proxy/cavada/routing_policy.py`, callback/pre-call config, `cavada_routing_policies`, `cavada_routing_rules` | Low to medium if isolated; high if `router.py` is changed | 80-170 |
| Local node registry | Medium | Add node registration, heartbeat, node models and node health tables. Expose CavadaLabs node endpoints. Cache current node health in Redis. | `litellm/proxy/cavada/node_registry.py`, `cavada_nodes`, `cavada_node_heartbeats`, `cavada_node_models`, Redis | Low | 50-100 |
| Local node routing | Medium | V1: treat each healthy node as an OpenAI-compatible LiteLLM deployment. Update deployment availability based on heartbeat/health. Use local-first policy resolver to choose local model group when available. | `config.yaml`, `litellm/proxy/cavada/routing_policy.py`, `litellm/proxy/cavada/node_registry.py`, LiteLLM router config | Low to medium | 60-140 |
| Orchestra integration | Medium | Require Orchestra to expose OpenAI-compatible chat and embedding endpoints for V1. Implement a custom provider only if Orchestra needs non-OpenAI job semantics. | Orchestra service contract, `litellm/llms/openai_like/`, optional `litellm/proxy/cavada/node_gateway.py` | Low for OpenAI-compatible; medium for custom provider | 40-120 |
| Request ledger | Medium | Add CavadaLabs ledger callback. Store routing decisions, target, latency, tokens, cost and error data. Do not store prompts/responses by default. | `litellm/proxy/cavada/ledger.py`, `litellm/proxy/example_config_yaml/custom_callbacks.py` pattern, `cavada_request_ledger`, `cavada_request_attempts` | Low | 50-100 |
| Dashboard custom pages | Medium to hard | Add CavadaLabs pages/components for projects, apps/chatbots, aliases, routing policies, nodes, ledger and RAG config. Keep existing LiteLLM pages for keys, models, usage and logs initially. | `ui/litellm-dashboard/src/app/(dashboard)/cavada/`, `ui/litellm-dashboard/src/components/cavada/`, `leftnav.tsx`, Cavada API hooks | Medium | 120-280 |
| Tenant dashboard restrictions | Hard | Start with internal admin only. Later add tenant roles, route guards, backend authorization checks and possibly RLS-backed views for tenant read paths. | `ui/litellm-dashboard/src/utils/roles.ts`, Cavada auth, Cavada admin endpoints, Supabase RLS policies | Medium to high | 100-220 |
| RAG configuration | Medium | Store RAG config, sources, prompt settings and embedding/generation aliases in CavadaLabs tables. Keep execution in a separate RAG service/module. | `cavada_rag_sources`, `cavada_prompt_configs`, dashboard Cavada pages, optional separate RAG service | Low to medium | 60-150 |
| Privacy-safe logging | Easy to medium | Set `STORE_PROMPTS_IN_SPEND_LOGS=False`, keep `turn_off_message_logging` available, add ledger with no raw payloads, add project settings for payload retention and redaction. | `litellm/proxy/spend_tracking/`, `litellm/litellm_core_utils/redact_messages.py`, `cavada_request_ledger`, config | Low | 24-60 |
| Cost tracking | Easy to medium | Reuse LiteLLM spend logs and daily spend tables. Add CavadaLabs usage events and ledger rollups only where product reporting needs differ. | `LiteLLM_SpendLogs`, daily spend tables, `litellm/proxy/spend_tracking/`, `cavada_usage_events` | Low | 24-70 |
| Cloudflare deployment | Medium | Run dispatcher as always-warm container for chatbot traffic. Use external Supabase Postgres and Redis. Use Cloudflare DNS/WAF/Tunnel. Validate streaming timeouts and container cold start behavior. | `Dockerfile`, `docker-compose.yml`, `docker/prod_entrypoint.sh`, env config, Cloudflare deployment config | Low | 30-90 |

## E. Database Proposal

### LiteLLM tables to reuse

Reuse these tables instead of duplicating them:

- `LiteLLM_VerificationToken`
  - Long-lived server-to-server project API keys.
  - Existing fields cover models, aliases, config, metadata, budgets, rate limits, project, team, organization and blocked status.

- `LiteLLM_UserTable`
  - Dashboard/runtime user mapping.
  - `sso_user_id` can map to Supabase Auth user ids.

- `LiteLLM_OrganizationTable`
  - Organization-level grouping if the semantics match CavadaLabs tenant organizations.

- `LiteLLM_TeamTable`
  - Useful for workspaces or tenant groups.
  - Already has budgets, rate limits, model allowlists, metadata and members.

- `LiteLLM_ProjectTable`
  - Useful for CavadaLabs projects if licensing and endpoint availability are acceptable.
  - Already supports `project_id`, `team_id`, models, budget and blocked status.
  - Existing project management endpoints appear under enterprise code, so do not assume unrestricted product use without review.

- `LiteLLM_ProxyModelTable`
  - Model and deployment storage when `STORE_MODEL_IN_DB=True`.

- `LiteLLM_CredentialsTable`
  - Provider credential storage.

- `LiteLLM_SpendLogs`
  - Standard usage/spend records.
  - Prompt/response storage is disabled unless `store_prompts_in_spend_logs` is explicitly enabled.

- `LiteLLM_ErrorLogs`
  - Standard error logging.

- `LiteLLM_AuditLog`
  - Admin and operational audit events.

- `LiteLLM_PromptTable`
  - Potential starting point for prompt records, but CavadaLabs prompt configuration will likely need project/app/RAG-specific fields.

- `LiteLLM_HealthCheckTable`
  - Useful for deployment health, but local-node heartbeats need a CavadaLabs-specific model.

### CavadaLabs tables to add

Prefer adding CavadaLabs-specific tables instead of modifying LiteLLM core tables:

- `cavada_organizations`
  - Optional mapping/extension table for CavadaLabs organization metadata.
  - Fields should include `id`, `litellm_organization_id`, `name`, `slug`, `status`, `metadata`, `created_at`, `updated_at`.

- `cavada_memberships`
  - Maps Supabase Auth users to CavadaLabs organizations, roles and optional LiteLLM users.
  - Fields should include `supabase_user_id`, `litellm_user_id`, `cavada_organization_id`, `role`, `status`.

- `cavada_projects`
  - Product project abstraction.
  - Can map to `LiteLLM_ProjectTable.project_id` if LiteLLM projects are reused.

- `cavada_apps` or `cavada_chatbots`
  - App/widget/chatbot identity under a project.
  - Store allowed domains, default alias, privacy settings and public-session settings.

- `cavada_project_tokens`
  - Metadata for project tokens if additional product-level token fields are needed.
  - Long-lived secrets should still use LiteLLM virtual keys where possible.

- `cavada_widget_sessions`
  - Optional DB audit table for short-lived browser sessions.
  - Hot session validation should live in Redis.

- `cavada_model_aliases`
  - Project/app alias definitions such as `chatbot-default`, `chat-fast`, `chat-private`, `embedding-default`.

- `cavada_routing_policies`
  - Policy header table with project/app/alias scope, priority, enabled status and privacy constraints.

- `cavada_routing_rules`
  - Rule steps such as local-first, external fallback, provider allowlist, node allowlist, region/data-location constraints and budget constraints.

- `cavada_nodes`
  - Local node registry.
  - Includes ownership, endpoint, tunnel information, auth mode, status and capabilities.

- `cavada_node_heartbeats`
  - Recent heartbeats, health, version and resource summaries.

- `cavada_node_models`
  - Models exposed by each node, capabilities and current availability.

- `cavada_request_ledger`
  - One row per logical request.
  - Store request id, org/project/app, requested alias, resolved provider/node/model, status, latency, token counts, cost estimate, routing reason and privacy flags.

- `cavada_request_attempts`
  - One row per routing attempt/fallback attempt.
  - Store attempt order, target, status, latency, error code and token/cost data when available.

- `cavada_usage_events`
  - Optional normalized events for product billing/reporting if LiteLLM spend logs are not enough.

- `cavada_error_events`
  - Product-level error events with no raw prompts/responses by default.

- `cavada_audit_events`
  - Product admin audit log if LiteLLM audit logs do not cover all CavadaLabs operations.

- `cavada_rag_sources`
  - RAG source metadata and status, not full RAG execution.

- `cavada_prompt_configs`
  - Prompt and system instruction configuration per project/app/chatbot.

### Migration strategy

For upstream maintainability, avoid editing `schema.prisma` for CavadaLabs tables in the MVP.

Recommended MVP strategy:

1. Keep official LiteLLM Prisma schema intact.
2. Add CavadaLabs SQL migrations in a separate folder such as `supabase/migrations/` or `db_scripts/cavada/`.
3. Use Supabase migration tooling or a simple migration runner outside LiteLLM startup.
4. Access CavadaLabs tables through one of these lower-risk options:
   - Prisma raw SQL calls through the existing Prisma client.
   - A small isolated async DB client in `litellm/proxy/cavada/db.py`.
   - A separate CavadaLabs admin service if dashboard complexity grows.
5. Only add CavadaLabs models to `schema.prisma` later if typed Prisma access becomes worth the upstream merge cost.

Avoid running destructive or automatic schema changes against Supabase on runtime startup. Run migrations deliberately in deployment.

### Supabase Auth to LiteLLM mapping

Recommended mapping:

- Supabase `auth.users.id` maps to `cavada_memberships.supabase_user_id`.
- `cavada_memberships.litellm_user_id` maps to `LiteLLM_UserTable.user_id`.
- `LiteLLM_UserTable.sso_user_id` can store the Supabase user id as a secondary lookup.
- Supabase roles should map to CavadaLabs roles first:
  - `cavada_super_admin`
  - `cavada_operator`
  - `tenant_admin`
  - `tenant_viewer`
- CavadaLabs roles should then map to LiteLLM dashboard/API roles where existing LiteLLM endpoints are used:
  - `proxy_admin`
  - `proxy_admin_viewer`
  - `org_admin`
  - `internal_user`
  - `internal_user_viewer`

Runtime request auth should be separate from dashboard user auth.

### RLS considerations

Supabase RLS is useful for tenant-facing dashboard views if the frontend queries Supabase directly or through PostgREST.

For the dispatcher backend:

- Use service-level DB credentials.
- Enforce tenant/project access in CavadaLabs backend auth and admin endpoints.
- Do not rely on RLS as the only runtime security boundary.

Recommended model:

- Backend service role bypasses RLS for trusted server operations.
- RLS-protected views can be added for tenant dashboard read-only reporting.
- Direct writes to dispatcher-critical tables should go through backend APIs, not directly from tenant browsers.

## F. API Proposal

### Public runtime endpoints

Keep LiteLLM's OpenAI-compatible endpoints as the main runtime surface:

- `POST /v1/chat/completions`
- `POST /chat/completions`
- `POST /v1/embeddings`
- `POST /v1/responses`
- `GET /v1/models`

Runtime behavior:

- Server-to-server calls use long-lived project API keys backed by LiteLLM virtual keys.
- Browser widgets use short-lived CavadaLabs session tokens.
- Apps call model aliases, not real provider model names.
- Frontend-supplied provider/model choices are treated as untrusted input and constrained by project policy.

### Dashboard/admin endpoints

Add a CavadaLabs admin API namespace:

- `GET /cavada/admin/organizations`
- `POST /cavada/admin/organizations`
- `GET /cavada/admin/projects`
- `POST /cavada/admin/projects`
- `GET /cavada/admin/apps`
- `POST /cavada/admin/apps`
- `GET /cavada/admin/model-aliases`
- `POST /cavada/admin/model-aliases`
- `GET /cavada/admin/routing-policies`
- `POST /cavada/admin/routing-policies`
- `GET /cavada/admin/nodes`
- `POST /cavada/admin/nodes`
- `GET /cavada/admin/request-ledger`
- `GET /cavada/admin/usage`
- `GET /cavada/admin/errors`
- `GET /cavada/admin/rag-sources`
- `POST /cavada/admin/rag-sources`
- `GET /cavada/admin/prompt-configs`
- `POST /cavada/admin/prompt-configs`

These endpoints should enforce CavadaLabs roles and tenant scope independent of dashboard UI controls.

### Local node endpoints

Nodes should call dispatcher endpoints for registration and status:

- `POST /cavada/nodes/register`
- `POST /cavada/nodes/heartbeat`
- `POST /cavada/nodes/models`
- `POST /cavada/nodes/status`

V1 inference path should be dispatcher-to-node through OpenAI-compatible Orchestra endpoints:

- `POST {node_base_url}/v1/chat/completions`
- `POST {node_base_url}/v1/embeddings`
- `GET {node_base_url}/v1/models`
- `GET {node_base_url}/health`

If customer/local networks require outbound-only connectivity, add a later pull/job protocol:

- `GET /cavada/nodes/jobs/poll`
- `POST /cavada/nodes/jobs/{job_id}/result`

That pull/job model is more complex and should not be the first V1 path unless required.

### Token and session endpoints

Project API keys:

- Prefer existing LiteLLM key management endpoints for long-lived keys.
- Add CavadaLabs metadata and dashboard wrappers where needed.

Browser sessions:

- `POST /cavada/runtime/sessions`
  - Mint short-lived, project-scoped, app-scoped, domain-limited tokens.
  - Called by a trusted backend or by a controlled public bootstrap flow with strict validation.

- `POST /cavada/runtime/sessions/refresh`
  - Optional refresh endpoint with short TTL and abuse controls.

- `POST /cavada/runtime/sessions/revoke`
  - Optional revoke endpoint.

Session token claims should include:

- `session_id`
- `organization_id`
- `project_id`
- `app_id`
- allowed aliases
- allowed origin/domain
- expiry
- rate limit bucket
- privacy settings

## G. Deployment Proposal

### Containers needed

Minimum production deployment:

- CavadaLabs Dispatcher container
  - LiteLLM proxy plus CavadaLabs modules and dashboard.
  - Always warm for chatbot/runtime use cases.

- Redis
  - External managed Redis preferred.
  - Used for cache, rate limits, cooldowns, locks, session tokens, node health snapshots and routing state.

- Supabase Postgres
  - Main database.
  - Use Supabase migration tooling for CavadaLabs SQL migrations.

- Local Agent and Orchestra containers on each local node
  - Separate from online dispatcher.
  - Local Agent handles registration and heartbeat.
  - Orchestra exposes OpenAI-compatible model endpoints.

Optional later:

- RAG service or worker.
- Background billing/rollup worker.
- Observability stack if Cloudflare/Supabase logs are not enough.

### Environment variables

Core LiteLLM:

- `DATABASE_URL`
- `LITELLM_MASTER_KEY`
- `STORE_MODEL_IN_DB=True`
- `REDIS_URL` or `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`
- `CONFIG_FILE_PATH`
- `STORE_PROMPTS_IN_SPEND_LOGS=False`
- `LITELLM_LOG=INFO`

CavadaLabs:

- `CAVADA_SUPABASE_URL`
- `CAVADA_SUPABASE_JWKS_URL`
- `CAVADA_SUPABASE_SERVICE_ROLE_KEY`
- `CAVADA_SESSION_SIGNING_KEY`
- `CAVADA_PUBLIC_BASE_URL`
- `CAVADA_ALLOWED_DASHBOARD_ORIGINS`
- `CAVADA_NODE_SHARED_SECRET` or per-node credential configuration

Production safety:

- Keep provider API keys in environment variables, LiteLLM credentials table, or a secret manager.
- Do not expose provider keys to dashboard clients.
- Disable debug logging in production.
- Keep prompt/response storage disabled by default.

### Supabase/Postgres connection

Use Supabase Postgres as the main database, but be careful with:

- Connection pool limits.
- Prisma connection behavior.
- Supabase pooler mode.
- Runtime migrations.
- Long-running background jobs.

Recommended:

- Run migrations outside the dispatcher startup.
- Use a pooler-compatible connection string for runtime where appropriate.
- Use a direct connection only for migrations if Supabase requires it.
- Tune LiteLLM database pool settings before running multiple replicas.

### Redis usage

Redis should be considered required for production, even if LiteLLM can run without it in smaller setups.

Use Redis for:

- API key cache.
- Rate limits.
- Model cooldowns.
- Routing state.
- Local node health snapshots.
- Short-lived browser session tokens.
- Locks for background jobs.
- Spend update buffering if enabled.
- LLM response cache if product policy allows it.

### Cloudflare considerations

Recommended Cloudflare usage:

- DNS, TLS, WAF and bot protection.
- Rate limiting at the edge for public chatbot/session endpoints.
- Cloudflare Tunnel for local nodes if inbound access is not available.
- Access rules for dashboard admin paths.

Validate before production:

- Server-sent event streaming behavior.
- Timeout limits for long completions.
- Container cold start behavior.
- Request body limits.
- Log volume and privacy.
- Whether chosen Cloudflare container/runtime product supports always-warm instances.

### Always-on versus sleep/wake

Always-on:

- Public dispatcher runtime for chatbot and app traffic.
- Redis.
- Supabase Postgres.
- Any node gateway needed for production local routing.

Can sleep or scale down:

- Internal dashboard-only replicas.
- Development/staging dispatcher.
- RAG ingestion workers when not actively processing.
- Non-critical rollup/reporting workers.
- Local nodes not serving production traffic.

The dispatcher should stay warm for public chatbot traffic. Cold starts will damage first-token latency and streaming user experience.

### Operational notes

LiteLLM is mostly stateless when Postgres and Redis are externalized. Multiple replicas are viable, but background jobs and DB write paths must be configured carefully.

Watch these areas:

- Background health checks.
- Spend update jobs.
- Budget reset jobs.
- Cleanup jobs.
- DB pool pressure.
- Redis lock configuration.
- Streaming connections during deploys.
- Log payload size.

## H. Upstream Update Strategy

### Recommended branching model

Use a simple branch model:

- `upstream/main`
  - Official LiteLLM upstream mirror.

- `cavada/main`
  - Stable CavadaLabs fork branch.

- `cavada/feature/*`
  - Feature branches for CavadaLabs work.

- `cavada/release/*`
  - Stabilization branches for production releases.

Update flow:

1. Add official LiteLLM as `upstream`.
2. Fetch upstream regularly.
3. Merge or rebase selected LiteLLM release tags into an integration branch.
4. Resolve conflicts there.
5. Run CavadaLabs regression tests.
6. Promote to `cavada/main`.

### Keep custom code isolated

Prefer:

- New backend code under `litellm/proxy/cavada/`.
- New dashboard code under `ui/litellm-dashboard/src/components/cavada/` and `src/hooks/cavada/`.
- Separate CavadaLabs SQL migrations.
- Config-driven model/provider changes.
- Small, documented integration patches in `proxy_server.py` only when a router must be mounted.

Avoid:

- Editing `router.py`.
- Editing provider implementations.
- Editing existing LiteLLM Prisma models.
- Replacing existing dashboard route/auth patterns before necessary.

### Tests after upstream updates

Minimum regression suite:

- Proxy starts with CavadaLabs config.
- Supabase JWT auth maps to expected CavadaLabs and LiteLLM roles.
- Project API key auth still works.
- Browser session token auth rejects expired, wrong-origin and wrong-project tokens.
- Alias resolution works per project/app.
- Local-first routing chooses a healthy node.
- Fallback routing chooses external provider when local node is unavailable.
- Streaming works for local and external targets.
- Ledger writes success and failure records without prompts/responses by default.
- LiteLLM spend logs still update.
- Dashboard internal admin pages load.
- Tenant user cannot access internal admin data.
- Docker image starts in production-like config.

### Areas most likely to conflict

- `litellm/proxy/proxy_server.py`
  - Route registration, startup, config loading and callback setup.

- `schema.prisma`
  - Any direct schema changes will conflict with upstream schema evolution.

- `litellm/proxy/auth/user_api_key_auth.py`
  - Auth flow changes are likely to conflict.
  - Prefer config-based custom auth.

- `litellm/proxy/auth/auth_checks.py`
  - Access-control internals.
  - Avoid direct edits.

- `litellm/proxy/litellm_pre_call_utils.py`
  - Metadata and alias behavior.
  - Prefer pre-call hooks instead of direct edits.

- `litellm/router.py`
  - Core routing logic.
  - Avoid direct edits.

- `litellm/main.py`
  - SDK dispatch logic.
  - Avoid direct edits.

- `ui/litellm-dashboard/src/components/leftnav.tsx`
  - Navigation customization.

- `ui/litellm-dashboard/src/components/login/`
  - Supabase Auth integration.

- `ui/litellm-dashboard/src/utils/roles.ts`
  - Tenant/internal role separation.

### Upstream contribution opportunities

Potential generic contributions upstream:

- More explicit project-level alias hook.
- Better documented custom auth return metadata.
- Generic request ledger callback hook payload.
- Better dashboard extension/plugin points.
- Generic local deployment heartbeat/provider health source.
- More configurable prompt/response redaction controls.

## I. Work Estimate

These estimates assume a small senior engineering team familiar with Python/FastAPI, React, Postgres and LiteLLM internals after initial ramp-up.

### MVP minimal

Estimated: 320-520 hours.

Scope:

- LiteLLM configured as CavadaLabs Dispatcher.
- External providers through existing LiteLLM provider config.
- Local nodes exposed as OpenAI-compatible endpoints.
- Basic CavadaLabs SQL tables for projects/apps/aliases/routing/nodes/ledger.
- Project API keys using LiteLLM virtual keys.
- Short-lived browser session token MVP.
- Local-first/external-fallback routing for chat.
- Privacy-safe ledger callback.
- Supabase Auth mapping for internal admin users.
- Minimal admin API.
- Minimal dashboard adaptation or internal operator-only pages.
- Docker production config with Supabase Postgres and Redis.

### V1 complete

Estimated: 900-1,500 hours.

Scope:

- Full internal admin dashboard.
- Tenant-visible restricted dashboard views.
- Project/app/chatbot management.
- Configurable routing policies and aliases.
- Node health and model inventory UI.
- Ledger, errors, usage and cost views.
- Prompt and RAG configuration management.
- More complete Supabase Auth integration.
- Robust browser session token lifecycle.
- Local node integration with health-based routing.
- Production deployment hardening.
- Regression test suite for upstream updates.

### Hardening

Estimated: 240-450 hours.

Scope:

- Security review.
- Abuse/rate-limit hardening.
- Streaming edge-case testing.
- Multi-replica testing.
- DB pool and migration hardening.
- Observability dashboards.
- Backup/restore procedures.
- Load testing.
- Failure-mode testing.

### Dashboard adaptation

Estimated: 180-350 hours for internal admin MVP.

Add 180-320 hours for tenant-restricted views.

### Local node integration

Estimated: 160-340 hours.

Lower end assumes Orchestra already exposes OpenAI-compatible chat and embeddings. Higher end assumes custom node auth, tunnel behavior, streaming normalization and model capability reporting need to be built.

### RAG configuration only

Estimated: 80-180 hours.

This includes DB tables, dashboard forms and API endpoints for source/prompt/retriever settings. It does not include full ingestion, retrieval or document processing.

### Full RAG later, separately

Estimated: 400-900 hours.

Scope depends heavily on file types, vector DB choice, chunking strategy, reindexing, permissions, tenant isolation, retrieval quality, source sync and evaluation tooling.

## J. Risks and Open Questions

### Technical risks

- LiteLLM project endpoints appear to live in enterprise code. Legal/product rights must be clarified before relying on them.
- Supabase Auth integration may require dashboard auth changes that conflict with upstream.
- Supabase Postgres plus Prisma requires careful pooling and migration handling.
- Routing policy complexity can grow quickly if local-first, privacy, region, budget, fallback and latency constraints all interact.
- Streaming fallback is harder than non-streaming fallback.
- Local model token counting and cost estimation may be approximate.
- Local node health can become stale unless Redis and heartbeat expiry are reliable.
- Browser session tokens are abuse-prone unless origin, TTL, rate limits and project scope are enforced.
- Dashboard tenant isolation needs backend checks, not just frontend route hiding.
- Background jobs in multiple replicas can create duplicate work if locks are misconfigured.

### Licensing and upstream risks

- LiteLLM is MIT in project metadata, but this repository includes enterprise folders and premium-gated behavior. Review licensing and allowed use before building proprietary features on enterprise-only code.
- Deep changes to dashboard auth, schema, router or proxy startup will create recurring merge conflicts.
- Upstream may change internal hook payloads or dashboard structure.

### Operational risks

- Cloudflare runtime/container products may have timeout or cold-start behavior that is unsuitable for chat streaming.
- Dispatcher cold starts will hurt chatbot UX.
- Long-running streaming responses need graceful deploy behavior.
- Logging must be kept privacy-safe across application logs, provider logs, Cloudflare logs and DB logs.
- Provider API key storage must be locked down.
- Supabase service-role keys must never reach the browser.

### Architectural risks

- Putting RAG execution inside the dispatcher would increase latency, operational complexity and upstream conflict risk.
- Implementing a custom node protocol too early would increase V1 complexity.
- Treating browser widgets as normal API-key clients would expose long-lived credentials.
- Using only frontend controls for tenant access would be insufficient.
- Modifying LiteLLM's core tables for every CavadaLabs concept would make upstream updates expensive.

### Open questions

- Which LiteLLM enterprise features are legally and commercially available for this fork?
- Should CavadaLabs reuse `LiteLLM_ProjectTable` directly, or keep a separate `cavada_projects` table mapped to LiteLLM keys?
- Will Orchestra expose fully OpenAI-compatible streaming chat and embeddings in V1?
- Do customer/local nodes need outbound-only job polling, or can they expose a tunnel endpoint?
- Which Cloudflare compute product is intended for the dispatcher, and does it support always-warm streaming workloads?
- What tenant isolation requirements exist for regulated clients?
- Are prompts/responses ever allowed to be stored, and under which explicit consent model?
- Which billing source is authoritative: LiteLLM spend logs, CavadaLabs usage events, or an external billing system?
- Should CavadaLabs dashboard query Supabase directly for some tenant views, or only through dispatcher APIs?
- What is the minimum local-node capability set for V1: chat only, or chat plus embeddings?

## Maintainability Classification by Change Area

| Change area | Recommended category | Likely impacted files/folders | Conflict risk | Lower-risk alternative | Upstream contribution potential |
| --- | --- | --- | --- | --- | --- |
| External provider config | Category 0: configuration only | `config.yaml`, dashboard model settings | Low | Keep all provider setup in config/DB | Not needed |
| Global model aliases | Category 0: configuration only | `model_list`, `router_settings.model_group_alias` | Low | Use existing model groups | Not needed |
| Project API keys | Category 0/1 | Existing key APIs, `LiteLLM_VerificationToken` | Low | Use key metadata, do not add key table first | Not needed |
| Supabase Auth runtime validation | Category 1: extension point | Custom auth module, config | Low | Validate JWT in `custom_auth` and return `UserAPIKeyAuth` | Better auth docs/hooks |
| Supabase dashboard login | Category 2/3 | Dashboard login components, role utils, possibly backend auth endpoints | Medium/high | Issue LiteLLM-compatible dashboard token after Supabase login | Generic external-auth bridge |
| Browser session tokens | Category 2: isolated module | `litellm/proxy/cavada/sessions.py`, Redis, Cavada tables | Low | Use Redis-only sessions for MVP | Generic short-lived public token support |
| Cavada routing policies | Category 2 | `litellm/proxy/cavada/routing_policy.py`, callback/pre-call config | Low/medium | Resolve to existing LiteLLM model groups | Generic policy hook |
| Local node OpenAI-compatible routing | Category 0/2 | `config.yaml`, node registry, model DB | Low | Treat nodes as deployments | Generic dynamic deployment source |
| Custom Cavada provider | Category 1/2 | `custom_provider_map`, `CustomLLM` subclass | Medium | Avoid until OpenAI-compatible path fails | Generic provider example |
| Cavada request ledger | Category 2 | `litellm/proxy/cavada/ledger.py`, Cavada SQL tables | Low | Use custom callback only | Generic structured ledger callback |
| Cavada DB tables | Category 2 | Separate SQL migrations | Low | Avoid `schema.prisma` changes | Not needed |
| Add Cavada models to Prisma schema | Category 3: core patch | `schema.prisma` | High | Use raw SQL or separate DB client | Not likely |
| Dashboard Cavada pages | Category 2/3 | `ui/litellm-dashboard/src/components/cavada/`, `leftnav.tsx` | Medium | Keep pages isolated and minimal nav patch | Dashboard extension slots |
| Tenant dashboard restrictions | Category 3 | Dashboard roles, API auth, endpoint checks | Medium/high | Internal admin first, tenant views later | Generic RBAC improvements |
| RAG config management | Category 2 | Cavada SQL/API/UI modules | Low/medium | Keep RAG execution separate | Not needed |
| Full RAG execution inside dispatcher | Category 4: invasive fork | Proxy request flow, RAG endpoints, DB, workers | High | Separate RAG service calling dispatcher | Not recommended |
| Router internal changes | Category 4 | `litellm/router.py`, strategies | Very high | Pre-call policy resolver plus existing router | Generic router extension points |

## Recommended Top 10 Changes

1. Create a CavadaLabs backend module under `litellm/proxy/cavada/`.
2. Add separate CavadaLabs SQL migrations for product tables instead of editing `schema.prisma`.
3. Use LiteLLM virtual keys for long-lived project API keys.
4. Add short-lived browser session tokens backed by Redis.
5. Resolve CavadaLabs aliases and routing policies before LiteLLM routing.
6. Represent local nodes as OpenAI-compatible LiteLLM deployments in V1.
7. Add a CavadaLabs request ledger callback with prompt/response storage disabled by default.
8. Map Supabase Auth users to LiteLLM users through CavadaLabs memberships.
9. Build internal admin dashboard pages before tenant-restricted views.
10. Keep RAG execution separate from the dispatcher and manage only RAG config in V1.

## Top Files and Folders to Inspect Manually

1. `litellm/proxy/proxy_server.py`
2. `litellm/proxy/auth/user_api_key_auth.py`
3. `litellm/proxy/auth/auth_checks.py`
4. `litellm/proxy/common_request_processing.py`
5. `litellm/proxy/litellm_pre_call_utils.py`
6. `litellm/router.py`
7. `litellm/proxy/spend_tracking/`
8. `schema.prisma`
9. `ui/litellm-dashboard/src/components/leftnav.tsx`
10. `ui/litellm-dashboard/src/components/login/`

## Final Recommendation

Proceed with a minimal fork strategy. LiteLLM should remain the core dispatcher engine, while CavadaLabs product behavior should live in isolated modules, config and callbacks. The first production version should focus on OpenAI-compatible runtime dispatch, project keys, short-lived widget sessions, local-node-as-deployment routing, privacy-safe request ledger, internal admin dashboard and Supabase-backed identity mapping.

Do not start by rewriting routing, auth, provider internals or dashboard architecture. Those changes would turn a feasible medium-risk fork into a high-maintenance invasive fork.
