# CavadaLabs Dispatcher Feasibility

Date: 2026-05-14

Repository: LiteLLM fork `litellm-cavada`

Working title: CavadaLabs Dispatcher

## 1. Executive Summary

The project is feasible, but it should not be treated as a small LiteLLM
customization.

LiteLLM should remain the gateway engine: OpenAI-compatible API, provider
translation, routing, spend logging, rate limits, streaming and external model
support.

CavadaLabs should add a product layer around it:

- Companies and Projects instead of LiteLLM Organizations.
- Chatbots that can be published on websites.
- Browser-safe web tokens for chatbot widgets.
- RAG collections owned by companies or projects.
- CavadaLabs GPU nodes with model load/unload control.
- Explicit numeric model priority per project.
- Monthly usage exports suitable for billing.
- CavadaLabs Guardrails as a first-class internal provider.
- GDPR and AI Act compliance evidence, documents and audit trails.

The recommended architecture is `LiteLLM core, CavadaLabs product layer`.
Avoid deep changes to LiteLLM routing internals until an extension point is
proven insufficient.

## 2. Product Model

The platform should expose CavadaLabs concepts, not LiteLLM concepts.

Primary hierarchy:

```text
Company
  -> Project
      -> Chatbots
      -> RAG Collections
      -> Web Tokens
      -> Model Policies
      -> Guardrail Policies
      -> Usage and Billing Reports
```

### Companies

Companies replace Organizations in the CavadaLabs UI and API.

Implementation direction:

- Hide or disable Organizations in the dashboard.
- Add CavadaLabs `companies` tables and admin APIs.
- Do not depend on LiteLLM Enterprise project endpoints.
- Keep compatibility mappings only where LiteLLM internals still need existing
  fields.

Company fields:

- `company_id`
- legal name
- billing name
- VAT/tax id
- billing address
- admin emails
- plan
- status: `active`, `suspended`, `archived`
- monthly budget
- metadata
- retention policy
- default guardrail policy
- default billing settings

### Projects

Projects are the operational unit below a company.

Project fields:

- `project_id`
- `company_id`
- name
- status: `dev`, `production`, `archived`
- allowed models
- numeric model priority policy
- allowed RAG collections
- default chatbot settings
- default guardrail policy
- budget
- retention policy override
- metadata

Every request ledger row should carry:

- `company_id`
- `project_id`
- `chatbot_id`, when applicable
- `web_token_id`, when applicable
- `session_id`, when applicable
- `provider`
- `model`
- `node_id`, when applicable
- `gpu_id`, when applicable

## 3. Chatbots And Web Tokens

Chatbots should be first-class entities, not only prompt presets.

Chatbot fields:

- `chatbot_id`
- `company_id`
- `project_id`
- name
- status: `draft`, `published`, `disabled`
- system prompt
- prompt version
- default language
- model policy reference
- assigned RAG collections
- assigned guardrail policy
- allowed domains
- widget/theme configuration
- fallback message
- transcript retention policy

### Browser-Safe Web Tokens

LiteLLM virtual keys are not suitable for browser widgets.

Add CavadaLabs web tokens:

- short-lived tokens for browser use
- bound to `company_id`, `project_id`, `chatbot_id`
- domain and origin allowlist
- route-limited to chatbot endpoints
- rate-limited by IP and session
- optional budget per session
- revocable
- logged separately from server-to-server API keys

Recommended flow:

```text
Dashboard creates chatbot config
Customer site requests/receives a short-lived web token
Browser widget calls CavadaLabs chatbot endpoint
Dispatcher resolves chatbot -> RAG -> guardrails -> model policy
```

## 4. RAG Strategy

RAG should be modeled as company/project knowledge, then assigned to chatbots,
agents or model workflows.

Core concept:

```text
RAG Collection
  -> Documents
  -> Chunks
  -> Embeddings
  -> Retrieval configuration
  -> Permissions
```

Ownership:

- Company-level RAG: shared knowledge base for a company.
- Project-level RAG: dedicated knowledge base for one project.
- Chatbot assignment: one chatbot can use one or more allowed RAG collections.
- Agent/model assignment: agents or model workflows can also use the same RAG
  collections if permitted.

Example:

```text
Company: ACME
RAG Collection: ACME Product Docs
Project: Customer Support
Chatbot: Support Widget
Assigned RAG: ACME Product Docs + Support FAQ
```

Required RAG features:

- upload documents
- source metadata
- ingestion status
- chunking configuration
- embedding model selection
- vector backend selection
- reindex
- delete document
- delete collection
- source citations in answers
- retrieval logs
- permission checks by company/project/chatbot
- GDPR deletion workflow

V1 can keep the RAG execution in a separate CavadaLabs module/service. The
dispatcher should provide auth, model calls, embeddings calls, logging and usage
attribution.

## 5. Model Routing

CavadaLabs preference must not be implicit.

Routing should be explicit through numeric priority.

Example:

```text
Project: ACME Support

priority 10 -> cavadalabs/qwen3-32b on Cavada node pool
priority 20 -> cavadalabs/llama-3.3-70b on Cavada node pool
priority 30 -> openai/gpt-4.1
priority 40 -> anthropic/claude-sonnet
```

Lower number wins.

The dispatcher selects the first candidate that satisfies:

- project access
- model enabled
- node online, if CavadaLabs-hosted
- model loaded or loadable
- GPU lock available, if load is required
- required capabilities: JSON, tools, no-think, context length
- budget and rate limits
- guardrail policy

Suggested table: `cavada_project_model_policies`

Fields:

- `policy_id`
- `project_id`
- `model_alias`
- `provider`
- `deployment_id`
- `priority`
- `enabled`
- `fallback_enabled`
- `require_json_output`
- `require_no_think`
- `prefer_loaded_model`
- `max_cost_input`
- `max_cost_output`
- `metadata`

## 6. CavadaLabs Provider

CavadaLabs-hosted models should be tracked as provider `cavadalabs`, even when
the runtime endpoint is OpenAI-compatible.

Reason:

- separate internal model usage from external providers
- report cost by node/GPU
- support node-specific health and routing
- support model load locks
- support internal pricing
- make dashboard filtering clear

Every CavadaLabs-hosted request should log:

- `custom_llm_provider = cavadalabs`
- `node_id`
- `gpu_id`
- `loaded_model_id`
- `model_load_request_id`, if relevant

## 7. CavadaLabs Nodes

A CavadaLabs node is a server that can host local models and report operational
state to the dispatcher.

Node fields:

- `node_id`
- display name
- hostname
- location/datacenter
- status: `pending`, `online`, `degraded`, `offline`, `draining`, `disabled`
- node public key
- current agent version
- allowed projects or pools
- default electricity cost per kWh
- fixed hourly cost
- hardware amortization hourly cost
- metadata

GPU fields:

- `gpu_id`
- `node_id`
- vendor/model
- UUID
- VRAM total
- status
- loaded models
- metadata

### Node Bootstrap

Node initialization should be done from the online dispatcher.

Recommended flow:

```text
Admin creates node in dashboard
Dispatcher creates a one-time enrollment secret
Admin installs Cavada node agent on the machine
Admin pastes enrollment secret into the node agent
Node agent generates a private/public key pair locally
Node sends public key + enrollment secret to dispatcher
Dispatcher activates the node and stores the public key
Node receives runtime config
```

Security rules:

- enrollment secret must be long, random and single-use
- enrollment secret must expire
- node private key should be generated and kept on the node
- dispatcher stores only the node public key
- runtime communication should be signed or mutually authenticated
- keys must support rotation
- compromised nodes must be revocable from dashboard

This is better than permanently copying one static shared key to all nodes.

### Node Reporting

Live watt reporting is not required for V1.

Node agent should locally sample every 5 minutes:

- timestamp
- GPU utilization
- VRAM usage
- loaded models
- active requests
- queue size
- estimated or measured power/energy for the 5-minute window, if available
- errors

Once per day, the node sends a daily report:

- all 5-minute samples for the day
- total estimated kWh
- total model runtime
- total loaded-model time
- total requests served
- total tokens served
- total node cost estimate

This reduces dispatcher load and is enough for billing and capacity reports.

Cost estimate:

```text
energy_cost = daily_kwh * node_electricity_cost_per_kwh
fixed_cost = fixed_hourly_cost * 24
amortization = hardware_amortization_hourly_cost * 24
node_daily_cost = energy_cost + fixed_cost + amortization
```

The electricity cost per kWh must be editable from dashboard per node or per
datacenter.

## 8. Model Load Requests And GPU Locks

The platform needs explicit model loading, not only passive routing.

Entities:

- `ModelLoadRequest`
- `GpuLock`
- `LoadedModel`

Flow:

```text
Project requests model X
Scheduler checks compatible nodes/GPUs
Scheduler creates GPU lock
Node loads model
Node reports loaded model
Routing can use the loaded model
Lock expires or is released
```

States:

- `queued`
- `locking`
- `loading`
- `loaded`
- `failed`
- `expired`
- `unloading`
- `released`

Lock fields:

- `lock_id`
- `node_id`
- `gpu_id`
- `model_id`
- `project_id`
- `owner_type`
- `owner_id`
- `priority`
- `expires_at`
- `status`

## 9. JSON Output And No-Think

These should be product-level flags, then translated per provider/model.

JSON output:

- `force_json_output`
- `json_schema`
- `strict_json`
- `repair_invalid_json`
- retry on invalid JSON

No-think:

- `no_think`
- `reasoning_mode`: `none`, `minimal`, `low`, `medium`, `high`
- `hide_reasoning`
- `strip_thinking_tags`

Capability checks should be config-driven, not hardcoded per model.

## 10. Billing And Monthly Usage Exports

Add professional billing reports.

Reports should be generated by company and month, with optional breakdowns by:

- project
- chatbot
- model
- provider
- Cavada node
- GPU
- RAG collection
- guardrail policy
- web token

Formats:

- PDF
- CSV
- XLSX
- JSON

The PDF should include:

- CavadaLabs header
- customer legal/billing data
- report period
- report id
- generation timestamp
- totals by company
- totals by project
- tokens and requests
- provider costs
- Cavada node costs
- RAG/embedding costs
- guardrail costs, if priced
- taxes/IVA fields, if applicable
- methodology notes
- immutable checksum

Reports should be saved as `BillingReport` records, not only generated on the
fly. Generated reports should be downloadable later and should preserve the
original inputs used for the calculation.

## 11. Guardrails As CavadaLabs Provider

CavadaLabs Guardrails should be a separate first-class module/provider.

Do not rely only on LiteLLM regex guardrails.

Guardrail pipeline:

```text
input normalization
language detection
deterministic rules
PII/secret detection
prompt injection detection
policy classifier
optional LLM judge
RAG-context checks
tool-call checks
output validation
redaction/block/allow decision
decision logging
```

Guardrail policy scopes:

- global
- company
- project
- chatbot
- web token
- server API key
- agent
- model

Guardrail categories:

- prompt injection
- jailbreak
- PII/secrets
- data exfiltration
- system prompt extraction
- toxic/abusive content
- legal/medical/financial boundaries
- company-specific prohibited content
- GDPR data leakage checks
- AI Act prohibited-practice checks
- JSON/schema output validation
- tool call allow/deny
- RAG source leakage

Guardrail logs should include:

- policy id
- rule ids
- decision: `allow`, `block`, `redact`, `review`, `log_only`
- confidence
- language
- latency
- reason code
- redaction summary
- no raw personal data unless explicitly enabled by policy

Guardrails should also support an external API shape so they can later be sold
or integrated as a standalone CavadaLabs service.

## 12. GDPR And AI Act Compliance Layer

The platform must help CavadaLabs and customers demonstrate compliance. It must
not claim automatic legal compliance without legal review.

### GDPR Features

Required technical capabilities:

- data map by company/project/chatbot/RAG
- retention policies
- configurable raw prompt/response storage
- default minimization of raw payload logging
- data export by data subject/session/customer
- right-to-erasure workflow
- RAG document deletion and reindex
- audit log for admin actions
- processor/sub-processor registry
- DPA document management
- breach log and notification workflow
- encryption at rest and in transit
- access controls and least privilege
- tenant isolation checks
- data residency metadata

Downloadable/customizable GDPR documents:

- Record of Processing Activities template
- Data Processing Agreement template
- Technical and Organizational Measures document
- Sub-processor list
- Data retention schedule
- Data subject request procedure
- Breach response procedure
- DPIA template
- Security overview
- RAG data deletion certificate

### AI Act Features

Required technical capabilities:

- AI system inventory
- use-case risk classification
- chatbot disclosure text
- model cards/provider metadata
- human oversight settings
- logging and traceability
- incident reporting workflow
- prohibited-practice guardrail checks
- output transparency settings
- technical documentation export
- versioned policies and prompts
- eval evidence for guardrails and model behavior

Downloadable/customizable AI Act documents:

- AI system description
- intended purpose
- risk classification worksheet
- technical documentation pack
- human oversight procedure
- transparency notice for chatbot users
- incident report template
- model/provider registry export
- guardrail evaluation report
- post-market monitoring log

## 13. Dashboard Pages

Required CavadaLabs pages:

- Companies
- Projects
- Chatbots
- Web Tokens
- RAG Collections
- Documents/Ingestion
- Model Policies
- Cavada Nodes
- GPU Locks
- Model Load Queue
- Guardrails Studio
- Usage Explorer
- Monthly Billing Reports
- Compliance Center
- Audit Logs
- Settings

Node dashboard:

- node status
- GPUs
- loaded models
- daily reports
- kWh estimate
- cost per kWh
- fixed hourly cost
- daily/monthly cost estimate
- load/unload actions
- errors
- agent version

Compliance Center:

- GDPR document library
- AI Act document library
- company-specific generated documents
- signed/exported versions
- audit evidence
- data deletion certificates
- DPIA records
- processor/sub-processor registry

## 14. Additional Product Suggestions

Add after the core platform is stable:

- budget alerts
- cost anomaly alerts
- node offline alerts
- guardrail spike alerts
- chatbot synthetic monitoring
- prompt version rollback
- dev/staging/prod chatbot environments
- A/B testing between model policies
- customer feedback on answers
- human handoff
- transcript review
- SLA report per company
- cache/semantic cache to reduce cost
- project-level API usage quotas
- model quality scorecards
- customer-facing status page

## 15. Recommended Roadmap

### Phase 1: Foundation

- Add Companies and Projects.
- Hide Organizations in CavadaLabs UI.
- Add request ledger with `company_id` and `project_id`.
- Add server API keys and browser web tokens.
- Add basic chatbot entity.
- Add model policy with numeric priority.

### Phase 2: Cavada Runtime

- Add provider label `cavadalabs`.
- Add node registry.
- Add node bootstrap/enrollment.
- Add daily node report ingestion.
- Add model load requests and GPU locks.
- Add Cavada node dashboard.

### Phase 3: RAG And Billing

- Add RAG collections.
- Add document ingestion metadata.
- Add chatbot/RAG assignment.
- Add monthly usage aggregation.
- Add PDF/CSV/XLSX billing exports.

### Phase 4: Guardrails And Compliance

- Build CavadaLabs Guardrails provider.
- Add Guardrails Studio.
- Add GDPR Compliance Center.
- Add AI Act Compliance Center.
- Add downloadable/customizable compliance documents.
- Add evidence exports and audit trails.

## 16. Feasibility Verdict

Feasible with medium engineering risk if CavadaLabs modules stay isolated.

High-risk areas to avoid:

- rewriting LiteLLM router internals
- depending on LiteLLM Enterprise modules
- changing LiteLLM schema semantics directly
- exposing long-lived API keys in browser widgets
- storing raw prompts/responses by default
- making compliance claims without evidence and legal review

Best approach:

- keep LiteLLM as gateway engine
- build CavadaLabs domain tables separately
- add Cavada request ledger
- implement Cavada auth/web tokens
- implement Cavada node registry and scheduler
- build Cavada dashboard pages incrementally

## 17. Official Reference Points

These sources were checked on 2026-05-14 and should be rechecked before legal
or commercial release:

- EU AI Act overview and timeline:
  https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai
- EU AI Act GPAI obligations:
  https://digital-strategy.ec.europa.eu/en/factpages/general-purpose-ai-obligations-under-ai-act
- EDPB GDPR compliance guidance:
  https://www.edpb.europa.eu/sme-data-protection-guide/be-compliant_en
- EDPB record of processing activities guidance:
  https://www.edpb.europa.eu/sme-data-protection-guide/faq-frequently-asked-questions/answer/do-i-need-record-processing_en
- EDPB controller/processor guidance:
  https://www.edpb.europa.eu/sme-data-protection-guide/data-controller-data-processor_en
