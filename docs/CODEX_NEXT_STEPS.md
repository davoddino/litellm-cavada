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

The active tranche is key-scoped model-bucket routing inside the existing
CavadaLabs model policy path. A product request may use a generic bucket such as
`small`, `medium`, `large`, or `advanced`; the runtime first resolves that
bucket against enabled `CavadaLabs_ProjectModelPolicyTable` rows for the
specific Server API key, Project, and endpoint. If the key has no rows for that
bucket, it falls back to the Project-level bucket rows. The selected concrete
LiteLLM model plus ordered fallbacks are passed into the existing LiteLLM
router/request flow. This is not a separate router.

Current deployment commands for this tranche:

```bash
cd /home/kilolab/Documents/cavadalabs/litellm-cavada
git pull --ff-only origin cavadalabs_integration_of_new_features

export PATH="$PWD/.venv/bin:$HOME/.nvm/versions/node/v24.13.0/bin:$PATH"
export DATABASE_URL="postgresql://llmproxy:dbpassword9090@localhost:5433/litellm"

.venv/bin/prisma migrate deploy --schema litellm-proxy-extras/litellm_proxy_extras/schema.prisma
.venv/bin/prisma generate --schema litellm-proxy-extras/litellm_proxy_extras/schema.prisma

cd ui/litellm-dashboard
npm install
npm run build
cd ../..

rsync -a --delete ui/litellm-dashboard/out/ litellm/proxy/_experimental/out/

pkill -f "litellm --config dev_config.yaml --port 4000" || true
nohup .venv/bin/litellm --config dev_config.yaml --port 4000 > /tmp/litellm-cavada-4000.log 2>&1 &
```

The migration
`20260519100000_add_cavadalabs_model_policy_buckets` adds `endpoint_type` and
`model_bucket` to Project model policies and replaces the old Project/priority
unique index with Project/endpoint/bucket/priority. Existing rows backfill to
`chat_completion/default`, preserving current behavior.

The migration
`20260519150000_add_cavadalabs_key_model_policy_scope` adds nullable `key_id` to
`CavadaLabs_ProjectModelPolicyTable` and replaces the Project/bucket unique
constraint with partial unique indexes:

- `key_id IS NULL`: Project-level fallback policy priority per endpoint/bucket.
- `key_id IS NOT NULL`: Server API key policy priority per Project/endpoint/bucket.

No parallel routing table is used. `key_id` stores the LiteLLM verification
token hash returned as `token_id` by `/key/generate`; the UI never stores the raw
key as a policy foreign key.

Chatbot creation and updates validate that an explicitly selected
`model_policy_id` belongs to the same Project, `chat_completion` endpoint, and
configured model bucket stored in chatbot metadata. The Creator UI fetches model
policies for the selected Project plus bucket, so stale policy selections do not
survive Company/Project/bucket changes.

## Model Bucket Usage

Configure model priority either at Project level from the CavadaLabs Runtime
model-policy panel, or per Server API key from the key create/edit form under
`Model routing priorities`.

Each bucket row uses the same `company_id`, `project_id`, optional `key_id`,
`endpoint_type`, and `model_bucket`. `priority=1` is tried first, followed by
`priority=2`, `priority=3`, and so on. Only enabled policies whose `model_alias`
exists in the LiteLLM router are used.

Example for `endpoint_type=chat_completion` and `model_bucket=medium`:

1. `priority=1`, `model_alias=openai/gpt-4.1`
2. `priority=2`, `model_alias=openai/gpt-4.1-mini`
3. `priority=3`, `model_alias=openai/gpt-4o-mini`

The product request should use the bucket name, for example `model=medium` on a
server API key request or `model_bucket=medium` on a browser chatbot request.
The key create/edit UI automatically includes the bucket aliases and configured
concrete models in the key's allowed model list, so auth can accept the generic
bucket request before the runtime resolves the concrete model.

The runtime resolves the concrete primary model and writes ordered LiteLLM
fallbacks into the existing request path. The same concrete model may appear in
more than one bucket by creating separate policies for each bucket.

Supported policy endpoint values are `chat_completion`, `text_completion`,
`transcription`, and `embedding`. Runtime bucket routing is wired for the
existing LiteLLM chat, text-completion, embedding, and transcription proxy
routes; browser chatbot messages use the `chat_completion` endpoint.

## Guardrail Input Hygiene

Guardrails run before the model call and inspect the raw user input, including
quoted error text and prior conversation content sent with the request. If a user
asks why a phrase was blocked and includes the original blocked phrase inside the
new message, the same denied rule can match again before the model has a chance
to answer.

To troubleshoot a blocked prompt:

1. Start a fresh chat/session if the previous assistant response repeated the
   blocked error.
2. Do not paste the blocked phrase verbatim into the new user prompt.
3. Replace the sensitive part with neutral placeholders such as
   `<blocked phrase>` or `<insult pattern>`.
4. Ask for the explanation using metadata only, for example:
   `Why did denied_insults block a conditional match in my prompt?`
5. If the product needs to explain guardrail denials automatically, render the
   denial reason in UI copy outside the next LLM prompt, or sanitize it before
   sending it back through `/chatbots/messages`.

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
