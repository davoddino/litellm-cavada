# Cavada LiteLLM Codex Next Steps

## Current Mission

Build the CavadaLabs Chatbot Creator as a product flow inside the existing LiteLLM/CavadaLabs system. It must not be a side module. The creator must use Company and Project as the product tenant context, while legacy LiteLLM Organization/Team concepts remain internal compatibility only.

## Required Product Flow

The Chatbot Creator must support this end-to-end path:

1. Select or create the Company context.
2. Select a Project filtered by the selected Company.
3. Create a Chatbot owned by that Company and Project.
4. Configure model policy and allowed models using existing policy surfaces where possible.
5. Create or select a server API key linked to Company, Project, and Chatbot.
6. Create a browser/web token scoped to the Chatbot for embedding it into websites.
7. Configure prompt/system instructions.
8. Configure guardrails through real safety/model policy wiring, not mocks.
9. Attach RAG/knowledge references through existing resource models if present.
10. Ensure usage attribution reaches the CavadaLabs request ledger with company_id, project_id, and chatbot_id.

## Integration Rules

- Use existing CavadaLabs schema, access control, usage ledger, key context, and runtime auth modules before adding new abstractions.
- Do not duplicate key creation, token creation, policy, usage, or access logic in a parallel service.
- If a missing capability is discovered, add the smallest modular backend surface that fits the existing system.
- Keep Organizations hidden from the product UX unless the field is explicitly labelled as internal compatibility.
- Provider-specific "organization" fields must not be renamed or repurposed.
- No mock creator, fake RAG, fake guardrails, placeholder embed code, or TODO-driven implementation.

## Minimum Next Tranche

The active tranche is model-bucket routing inside the existing CavadaLabs model
policy path. A product request may use a generic bucket such as `default`,
`medium`, or `fast`; the runtime resolves that bucket to enabled
`CavadaLabs_ProjectModelPolicyTable` rows for the selected Project and endpoint,
then passes the selected concrete LiteLLM model plus ordered fallbacks into the
existing LiteLLM router/request flow. This is not a separate router.

Current deployment commands for this tranche:

```bash
export DATABASE_URL="postgresql://llmproxy:<password>@<host>:<port>/litellm"
uv run prisma migrate deploy --schema litellm-proxy-extras/litellm_proxy_extras/schema.prisma
uv run prisma generate --schema litellm-proxy-extras/litellm_proxy_extras/schema.prisma
uv run litellm --config dev_config.yaml --port 4000
```

The migration
`20260519100000_add_cavadalabs_model_policy_buckets` adds `endpoint_type` and
`model_bucket` to Project model policies and replaces the old Project/priority
unique index with Project/endpoint/bucket/priority. Existing rows backfill to
`chat_completion/default`, preserving current behavior.

Chatbot creation and updates validate that an explicitly selected
`model_policy_id` belongs to the same Project, `chat_completion` endpoint, and
configured model bucket stored in chatbot metadata. The Creator UI fetches model
policies for the selected Project plus bucket, so stale policy selections do not
survive Company/Project/bucket changes.

The next useful tranche after model-bucket routing is the smallest
production-ready creator path that can create a usable website chatbot:

1. Audit backend contracts for Chatbot, WebToken, server API key, model policy, guardrails, and RAG references.
2. Add a Creator UI flow instead of only generic CRUD panels.
3. Ensure Project selection is filtered by Company.
4. Ensure model_policy_id is selected from real policy data or validated against a real backend surface.
5. Wire server key and web token creation into the creator flow.
6. Persist prompt instructions and guardrail/RAG associations if existing schema supports them.
7. Add tests for the creator payload and the Company/Project scoping behavior.

## Verification

Required checks for the tranche:

- Backend tests for create/update/list access and request attribution where touched.
- Frontend tests for Company -> Project filtering and creator payload construction.
- Migration validation if schema changes are needed.
- `git diff --check`.
- No generated UI artifacts such as `.next`, `out`, or `tsconfig.tsbuildinfo` left dirty.

## Current Risks

- Chatbot and WebToken resources may exist only as generic resource panels, not as one cohesive creator.
- model_policy_id may be a free-text field instead of a real selected policy.
- Web token creation may be disconnected from key creation and embed use.
- Guardrails and RAG may have partial schema/runtime support; do not fake completion if wiring is incomplete.
