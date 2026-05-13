# CavadaLabs AI Platform - SPEC_MASTER

Versione: 0.1
Data: 2026-05-13
Stato: bozza architetturale interna
Destinatari: founder, team tecnico, collaboratori esterni, Codex, consulenti R&D

---

## 0. Scopo del documento

Questo documento definisce la specifica generale della piattaforma AI CavadaLabs e, in modo piu dettagliato, la specifica tecnica del componente CavadaLabs Dispatcher, basato su un fork di LiteLLM.

Il documento serve come riferimento unico per:

- progettare l'architettura generale della piattaforma;
- guidare lo sviluppo tecnico;
- istruire Codex e altri assistenti di sviluppo;
- evitare decisioni incoerenti tra dashboard, dispatcher, Supabase, nodi locali e Orchestra;
- mantenere il fork LiteLLM aggiornabile nel tempo;
- rimuovere ogni dipendenza da codice LiteLLM Enterprise e sviluppare moduli proprietari CavadaLabs;
- documentare scelte R&D, motivazioni tecniche, limiti e roadmap.

Il documento non e un preventivo commerciale, non e una specifica legale e non e una documentazione utente finale. E una specifica di prodotto e architettura.

---

## 1. Visione generale del progetto

CavadaLabs sviluppa una piattaforma proprietaria di AI Model Dispatching, Orchestration e Application Management.

La piattaforma deve ricevere richieste AI da applicazioni, chatbot, siti web, automazioni, RAG system, integrazioni aziendali e moduli verticali, decidendo dinamicamente dove eseguire tali richieste:

- provider AI esterni;
- modelli open source ospitati su nodi CavadaLabs;
- infrastrutture locali o cliente;
- futuri cluster GPU;
- servizi specializzati come embeddings, OCR, speech-to-text, vision, image generation, video generation e tool AI.

L'obiettivo non e costruire da zero tutto cio che esiste gia, ma integrare, adattare ed estendere componenti open source, sviluppando sopra di essi un prodotto proprietario CavadaLabs.

Il cuore operativo della prima versione e il CavadaLabs Dispatcher, basato su un fork di LiteLLM OSS, senza dipendenze da LiteLLM Enterprise.

---

## 2. Obiettivi strategici

La piattaforma deve permettere a CavadaLabs di:

1. ridurre la dipendenza da un singolo provider AI;
2. usare modelli commerciali, open source e locali con una interfaccia comune;
3. controllare consumi, costi, errori, performance e budget per cliente/progetto/app;
4. costruire chatbot, RAG, automazioni e moduli verticali su un backbone comune;
5. integrare progressivamente nodi CavadaLabs con GPU locali;
6. supportare scenari privacy-first e local-first;
7. creare valore proprietario su routing, orchestration, dashboard, nodi, policy, logging, RAG e gestione clienti;
8. mantenere la capacita di aggiornarsi ai progressi di LiteLLM OSS quando possibile;
9. evitare lock-in non necessario verso cloud provider, singoli modelli o singole API;
10. costruire una base tecnica riutilizzabile per futuri progetti AI aziendali.

---

## 3. Principi architetturali

### 3.1 Supabase-first

Supabase viene scelto come piattaforma dati principale per la V1:

- Supabase Postgres come database principale;
- Supabase Auth come identity provider per utenti dashboard;
- Supabase Storage come storage principale iniziale;
- Supabase RLS per viste tenant e accessi controllati dove opportuno;
- Supabase migrations per le tabelle CavadaLabs.

Importante: Supabase-first non significa riscrivere LiteLLM per renderlo Supabase-native. LiteLLM deve continuare a usare Postgres tramite DATABASE_URL. Le tabelle CavadaLabs devono essere aggiunte separatamente.

### 3.2 LiteLLM-core, CavadaLabs-product

LiteLLM deve restare il motore gateway:

- OpenAI-compatible API;
- provider abstraction;
- virtual keys;
- spend tracking;
- budgets;
- rate limits;
- streaming;
- fallbacks;
- model groups;
- callbacks/hooks;
- Docker deployment.

CavadaLabs aggiunge prodotto e logica proprietaria:

- organizzazioni, progetti, app/chatbot;
- Supabase Auth bridge;
- browser session tokens;
- model aliases per progetto;
- routing policy CavadaLabs;
- node registry;
- local node routing;
- request ledger;
- dashboard custom;
- RAG config;
- audit e reporting proprietari.

### 3.3 No Enterprise dependency

Il fork CavadaLabs non deve dipendere da codice LiteLLM Enterprise.

Tutto cio che in LiteLLM e disponibile solo in Enterprise deve essere:

- rimosso;
- ignorato;
- sostituito con moduli proprietari CavadaLabs;
- oppure rimandato.

Questa scelta riduce rischi licenza, ambiguita e dipendenze future.

### 3.4 Fork leggero e aggiornabile

Il fork deve restare aggiornabile da upstream LiteLLM.

Regola:

- preferire configurazione;
- preferire custom auth;
- preferire hook;
- preferire callback;
- preferire custom provider solo se necessario;
- preferire moduli CavadaLabs isolati;
- evitare modifiche al core routing;
- evitare modifiche a schema.prisma in V1;
- evitare modifiche invasive alla dashboard.

### 3.5 Privacy by default

Per default non devono essere salvati prompt e risposte complete.

Devono essere salvati:

- request id;
- organizzazione/progetto/app;
- alias richiesto;
- provider/nodo scelto;
- modello reale;
- token input/output se disponibili;
- costo stimato;
- latenza;
- errore normalizzato;
- routing decision;
- fallback attempts;
- metadata privacy-safe.

Il salvataggio di prompt/response deve essere opt-in, configurabile per progetto, con retention e redaction.

### 3.6 V1 semplice, non microservizi prematuri

La V1 deve essere modulare ma non inutilmente distribuita.

Componenti principali:

- CavadaLabs Dispatcher container;
- Dashboard adattata da LiteLLM;
- Supabase;
- Redis;
- Local Agent sui nodi;
- Orchestra sui nodi;
- eventuale RAG service separato, ma non obbligatorio in MVP.

---

## 4. Glossario

### CavadaLabs AI Platform

Piattaforma complessiva proprietaria che include dispatcher, dashboard, nodi, Orchestra, RAG, storage, auth, logging e gestione applicazioni.

### CavadaLabs Dispatcher

Fork/estensione di LiteLLM OSS che gestisce le richieste runtime verso provider esterni e nodi locali.

### LiteLLM OSS Core

Parte open source di LiteLLM usata come motore gateway.

### Control Plane

Livello di gestione: aziende, utenti, progetti, app, policy, nodi, config, dashboard.

### Data Plane

Percorso delle richieste runtime: autenticazione, routing, provider/nodo, risposta.

### Execution Plane

Dove i modelli vengono eseguiti: provider esterni oppure nodi CavadaLabs/locali.

### Observability/Billing Plane

Log, usage, costi, errori, metriche, audit, ledger, report.

### Organization/Tenant

Cliente, azienda o soggetto proprietario di progetti/app.

### Project

Contenitore logico di app, chatbot, RAG, automazioni e configurazioni AI.

### App/Chatbot

Applicazione concreta che usa il dispatcher: sito web, widget, servizio interno, RAG app, automazione.

### Model Alias

Nome astratto usato dalle app, ad esempio chatbot-default, chat-standard, embedding-default. Non coincide necessariamente con il modello reale del provider.

### Routing Policy

Regola che decide quale modello/provider/nodo usare per un alias in un progetto.

### Local Node

Server CavadaLabs o cliente che esegue Local Agent + Orchestra + modelli locali.

### Local Agent

Componente installato sul nodo che registra il nodo, manda heartbeat, espone stato e collega il nodo al dispatcher.

### Orchestra

Componente locale che esegue i modelli e normalizza le risposte. In V1 deve esporre endpoint OpenAI-compatible.

---

## 5. Architettura generale

```text
Clienti / siti / chatbot / RAG / automazioni
        |
        v
Cloudflare DNS / WAF / TLS / protection
        |
        v
CavadaLabs Dispatcher
LiteLLM OSS core + moduli CavadaLabs
        |
        |---- Provider esterni
        |       OpenAI, Anthropic, Mistral, Groq, Azure, ecc.
        |
        |---- Nodi CavadaLabs/locali
                Local Agent
                    |
                    v
                Orchestra
                    |
                    v
                Modelli locali / GPU / servizi AI

A lato:

Dashboard LiteLLM adattata
        |
        v
Supabase Auth + Supabase Postgres + Supabase Storage
        |
        v
Redis per cache, sessioni, rate limit, node state
```

---

## 6. Componenti principali

### 6.1 CavadaLabs Dispatcher

Responsabilita:

- esporre API compatibili OpenAI;
- validare project API keys;
- validare browser session tokens;
- risolvere model aliases;
- applicare routing policy;
- instradare verso provider esterni tramite LiteLLM;
- instradare verso nodi locali trattati come OpenAI-compatible deployments;
- gestire fallback;
- mantenere spend tracking LiteLLM;
- scrivere CavadaLabs request ledger;
- evitare logging di prompt/response per default.

### 6.2 Dashboard CavadaLabs

Base: dashboard LiteLLM adattata.

Priorita V1:

- uso interno CavadaLabs;
- gestione provider;
- gestione chiavi/progetti/app;
- model aliases;
- routing policies;
- richiesta/log/costi/errori;
- stato nodi;
- prompt config e RAG config base.

Tenant dashboard completa: post V1.

### 6.3 Supabase

Ruoli:

- database unico;
- Auth per utenti dashboard;
- Storage per file, documenti, RAG sources, allegati;
- RLS per viste tenant quando necessario;
- migrations CavadaLabs separate dalle migrazioni LiteLLM Prisma.

### 6.4 Redis

Ruoli:

- cache API key/metadata;
- rate limiting;
- browser session tokens;
- node status snapshot;
- cooldown provider/nodi;
- lock per job/background tasks;
- eventuale response cache se consentita.

### 6.5 Local Agent

Componente sul nodo locale:

- registra il nodo;
- invia heartbeat;
- comunica modelli disponibili;
- comunica risorse base;
- verifica health di Orchestra;
- espone o collega endpoint locale;
- gestisce autenticazione nodo;
- in futuro supporta job polling outbound-only.

### 6.6 Orchestra

Componente locale di esecuzione modelli:

- endpoint /health;
- endpoint /v1/models;
- endpoint /v1/chat/completions;
- endpoint /v1/embeddings opzionale;
- normalizzazione risposte;
- metriche minime;
- gestione timeout e concorrenza base;
- wrapper verso motori locali.

---

## 7. Stack V1

### Runtime

- LiteLLM OSS forkato come base;
- Python/FastAPI ereditato da LiteLLM;
- Docker;
- Cloudflare per networking e possibilmente container;
- Supabase Postgres;
- Supabase Auth;
- Supabase Storage;
- Redis gestito;
- Local Agent + Orchestra su nodi CavadaLabs.

### Sviluppo

- Git fork con upstream ufficiale LiteLLM;
- branch CavadaLabs main;
- branch integration per update upstream;
- test automatici minimi;
- Codex per analisi, sviluppo e refactoring;
- documentazione in docs/.

### Osservabilita iniziale

- request ledger in Supabase;
- spend logs LiteLLM;
- error logs sintetici;
- audit events CavadaLabs;
- metriche base su dashboard;
- Prometheus/Grafana solo dopo se necessario.

---

## 8. Specifica CavadaLabs Dispatcher

### 8.1 Obiettivo

Trasformare il fork LiteLLM OSS in CavadaLabs Dispatcher, mantenendo LiteLLM come core gateway e aggiungendo moduli proprietari CavadaLabs.

### 8.2 Nome prodotto

Nome tecnico: CavadaLabs Dispatcher

Possibili nomi interni:

- cavada-dispatcher;
- cavada-ai-gateway;
- cavada-model-router;
- cavada-orchestrator-gateway.

### 8.3 Posizione nel sistema

Il dispatcher e l'endpoint centrale runtime per le richieste AI.

Non deve diventare:

- RAG engine completo;
- document processor;
- CRM;
- ERP connector;
- dashboard monolitica totale;
- orchestration engine GPU profondo.

Deve rimanere:

- gateway;
- policy resolver;
- routing engine alto livello;
- usage/cost tracker;
- security boundary;
- bridge verso provider e nodi.

---

## 9. Enterprise removal strategy

### 9.1 Obiettivo

Rimuovere ogni dipendenza da LiteLLM Enterprise e sviluppare equivalenti CavadaLabs dove utili.

### 9.2 Azioni

1. Identificare cartella enterprise/ nel fork.
2. Verificare import da codice OSS verso enterprise/.
3. Rimuovere o neutralizzare riferimenti enterprise.
4. Verificare che Docker build funzioni senza enterprise/.
5. Verificare dashboard senza pagine enterprise-only.
6. Verificare endpoint che puntano a enterprise endpoints.
7. Creare issue CavadaLabs per moduli da ricostruire internamente.

### 9.3 Funzioni da rifare come CavadaLabs modules

- Supabase Auth / SSO bridge;
- RBAC interno e tenant;
- project management avanzato;
- tenant dashboard;
- audit log proprietario;
- secret/credentials policy;
- routing policy per progetto;
- node registry;
- request ledger;
- RAG config management;
- admin/operator workflows;
- eventuale SCIM/OIDC solo se serviranno in futuro.

### 9.4 Regola

Se una feature e presente in LiteLLM Enterprise, non va importata. Va rifatta come feature CavadaLabs oppure esclusa dalla V1.

---

## 10. Upstream sync strategy

### 10.1 Obiettivo

Continuare a ricevere aggiornamenti da LiteLLM OSS senza rendere il fork ingestibile.

### 10.2 Remote e branch

```text
upstream/main
  repository ufficiale LiteLLM

cavada/main
  branch stabile CavadaLabs

cavada/integration/litellm-vX.Y.Z
  branch temporaneo per integrare una release LiteLLM

feature/cavada-*
  feature branches nostre
```

### 10.3 Frequenza update

- update programmato ogni 2-4 settimane;
- update immediato per security fix importanti;
- update su richiesta se serve un provider/modello/fix specifico;
- evitare merge casuale giornaliero da upstream main.

### 10.4 Procedura update

1. Fetch upstream.
2. Scegliere release/tag LiteLLM da integrare.
3. Creare branch integration.
4. Merge della release upstream nel branch integration.
5. Risolvere conflitti.
6. Lanciare test automatici.
7. Deploy in staging.
8. Test manuale dashboard e runtime.
9. Merge in cavada/main.
10. Annotare changelog CavadaLabs.

### 10.5 Aree da proteggere

Evitare modifiche pesanti a:

- litellm/router.py;
- litellm/main.py;
- litellm/proxy/proxy_server.py;
- litellm/proxy/auth/auth_checks.py;
- litellm/proxy/auth/user_api_key_auth.py;
- schema.prisma;
- provider implementations;
- streaming internals;
- spend tracking internals;
- dashboard login core.

### 10.6 Aree CavadaLabs isolate

Preferire nuovi moduli:

```text
litellm/proxy/cavada/
ui/litellm-dashboard/src/app/(dashboard)/cavada/
ui/litellm-dashboard/src/components/cavada/
ui/litellm-dashboard/src/hooks/cavada/
supabase/migrations/cavada/
docs/cavada/
```

---

## 11. Moduli CavadaLabs nel fork

### 11.1 Backend module layout

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
  rag_config.py
  audit.py
```

### 11.2 Dashboard module layout

```text
ui/litellm-dashboard/src/app/(dashboard)/cavada/
  projects/
  apps/
  aliases/
  routing/
  nodes/
  ledger/
  rag/
  prompts/
  settings/

ui/litellm-dashboard/src/components/cavada/
ui/litellm-dashboard/src/hooks/cavada/
```

### 11.3 Database migrations

```text
supabase/migrations/
  001_cavada_core.sql
  002_cavada_auth.sql
  003_cavada_projects_apps.sql
  004_cavada_aliases_routing.sql
  005_cavada_nodes.sql
  006_cavada_ledger.sql
  007_cavada_rag_prompts.sql
  008_cavada_audit.sql
```

---

## 12. Supabase data model

### 12.1 Principio generale

Lo stesso Supabase Postgres contiene:

1. tabelle LiteLLM originali;
2. tabelle CavadaLabs separate.

Le tabelle LiteLLM non vanno modificate in V1 se non indispensabile.

### 12.2 Tabelle LiteLLM da riusare

- LiteLLM_VerificationToken: API key runtime server-to-server;
- LiteLLM_UserTable: mapping utenti runtime/dashboard dove serve;
- LiteLLM_TeamTable: grouping e budget quando utile;
- LiteLLM_OrganizationTable: grouping organization se OSS disponibile e utile;
- LiteLLM_ProxyModelTable: modelli/deployment se STORE_MODEL_IN_DB;
- LiteLLM_CredentialsTable: credenziali provider se usata;
- LiteLLM_SpendLogs: usage/costi standard;
- LiteLLM_ErrorLogs: errori LiteLLM;
- LiteLLM_AuditLog: audit LiteLLM dove disponibile;
- LiteLLM_HealthCheckTable: health provider/deployment.

### 12.3 Tabelle CavadaLabs core

#### cavada_organizations

Estensione proprietaria delle aziende/tenant.

Campi indicativi:

- id uuid primary key;
- litellm_organization_id text nullable;
- name text;
- slug text unique;
- status text;
- billing_status text;
- data_region text;
- metadata jsonb;
- created_at timestamptz;
- updated_at timestamptz;
- deleted_at timestamptz nullable.

#### cavada_memberships

Mapping tra Supabase Auth users, ruoli CavadaLabs e utenti LiteLLM.

Campi:

- id uuid;
- organization_id uuid;
- supabase_user_id uuid;
- litellm_user_id text nullable;
- role text;
- status text;
- created_at;
- updated_at.

Ruoli iniziali:

- cavada_super_admin;
- cavada_operator;
- tenant_admin;
- tenant_viewer.

#### cavada_projects

Progetti AI.

Campi:

- id uuid;
- organization_id uuid;
- litellm_project_id text nullable;
- name text;
- slug text;
- status text;
- default_app_id uuid nullable;
- default_model_alias text nullable;
- privacy_mode text;
- metadata jsonb;
- created_at;
- updated_at;
- deleted_at.

#### cavada_apps

App, chatbot, widget, automazioni o servizi che chiamano il dispatcher.

Campi:

- id uuid;
- organization_id uuid;
- project_id uuid;
- type text; -- chatbot, rag, automation, api, internal_app
- name text;
- public_id text unique;
- allowed_domains text[];
- default_model_alias text;
- allow_browser_sessions boolean;
- session_ttl_seconds integer;
- store_prompts boolean default false;
- store_responses boolean default false;
- payload_retention_days integer default 0;
- status text;
- metadata jsonb;
- created_at;
- updated_at.

### 12.4 Tabelle auth/session

#### cavada_project_tokens

Metadati aggiuntivi per project keys. La chiave runtime lunga resta preferibilmente LiteLLM virtual key.

Campi:

- id uuid;
- organization_id uuid;
- project_id uuid;
- app_id uuid nullable;
- litellm_key_id text;
- name text;
- status text;
- allowed_aliases text[];
- metadata jsonb;
- created_at;
- revoked_at nullable.

#### cavada_widget_sessions

Audit opzionale delle sessioni browser. Validazione calda in Redis.

Campi:

- id uuid;
- session_id text unique;
- organization_id uuid;
- project_id uuid;
- app_id uuid;
- origin text;
- allowed_aliases text[];
- expires_at timestamptz;
- revoked_at timestamptz nullable;
- metadata jsonb;
- created_at.

### 12.5 Tabelle alias/routing

#### cavada_model_aliases

Alias per progetto/app.

Campi:

- id uuid;
- organization_id uuid;
- project_id uuid;
- app_id uuid nullable;
- alias text;
- modality text; -- chat, embedding, vision, ocr, stt, tts, image, video
- default_policy_id uuid nullable;
- enabled boolean;
- metadata jsonb;
- created_at;
- updated_at.

#### cavada_routing_policies

Policy di routing.

Campi:

- id uuid;
- organization_id uuid;
- project_id uuid;
- app_id uuid nullable;
- alias_id uuid nullable;
- name text;
- strategy text; -- fixed, external_first, local_first, fallback, privacy_first, cost_first
- allow_external boolean;
- allow_local boolean;
- privacy_level text;
- max_latency_ms integer nullable;
- budget_behavior text;
- enabled boolean;
- version integer;
- metadata jsonb;
- created_at;
- updated_at.

#### cavada_routing_rules

Regole ordinate dentro una policy.

Campi:

- id uuid;
- policy_id uuid;
- position integer;
- condition_json jsonb;
- action_json jsonb;
- enabled boolean;
- created_at;
- updated_at.

### 12.6 Tabelle nodi

#### cavada_nodes

Registro nodi locali.

Campi:

- id uuid;
- organization_id uuid nullable;
- name text;
- type text; -- cavada, customer, lab, gpu, edge
- endpoint_url text nullable;
- connection_mode text; -- tunnel, direct, polling
- auth_mode text;
- status text; -- online, offline, degraded, maintenance, disabled
- last_seen_at timestamptz;
- agent_version text;
- orchestra_version text;
- region text;
- metadata jsonb;
- created_at;
- updated_at.

#### cavada_node_heartbeats

Heartbeat storici/sintetici.

Campi:

- id uuid;
- node_id uuid;
- status text;
- cpu_percent numeric;
- ram_used_gb numeric;
- ram_total_gb numeric;
- gpu_summary jsonb;
- models_summary jsonb;
- created_at timestamptz.

#### cavada_node_models

Modelli disponibili su nodi.

Campi:

- id uuid;
- node_id uuid;
- local_model_name text;
- exposed_model_name text;
- modality text;
- engine text; -- orchestra, vllm, ollama, llama_cpp, custom
- status text; -- available, loaded, loading, busy, error, disabled
- context_window integer nullable;
- estimated_vram_gb numeric nullable;
- openai_compatible boolean default true;
- metadata jsonb;
- created_at;
- updated_at.

### 12.7 Tabelle ledger/log

#### cavada_request_ledger

Una riga per richiesta logica.

Campi:

- id uuid;
- external_request_id text;
- organization_id uuid;
- project_id uuid;
- app_id uuid nullable;
- litellm_key_id text nullable;
- session_id text nullable;
- requested_alias text;
- modality text;
- resolved_target_type text; -- provider, node
- resolved_target_id text nullable;
- resolved_model text;
- routing_policy_id uuid nullable;
- routing_policy_version integer nullable;
- routing_reason text nullable;
- status text;
- started_at timestamptz;
- completed_at timestamptz nullable;
- latency_ms integer nullable;
- input_tokens integer nullable;
- output_tokens integer nullable;
- total_tokens integer nullable;
- estimated_cost numeric nullable;
- currency text default 'USD';
- error_code text nullable;
- error_message_safe text nullable;
- prompt_stored boolean default false;
- response_stored boolean default false;
- metadata jsonb;
- created_at.

#### cavada_request_attempts

Una riga per ogni tentativo/fallback.

Campi:

- id uuid;
- request_id uuid;
- attempt_number integer;
- target_type text;
- provider_id text nullable;
- node_id uuid nullable;
- model text;
- status text;
- started_at;
- completed_at nullable;
- latency_ms integer nullable;
- input_tokens integer nullable;
- output_tokens integer nullable;
- estimated_cost numeric nullable;
- error_code text nullable;
- error_message_safe text nullable;
- metadata jsonb;
- created_at.

#### cavada_usage_events

Eventi usage normalizzati per reporting.

#### cavada_error_events

Errori business-level normalizzati.

#### cavada_audit_events

Audit amministrativo CavadaLabs.

### 12.8 Tabelle RAG/prompts

#### cavada_prompt_configs

Prompt/system instructions per progetto/app.

Campi:

- id uuid;
- organization_id uuid;
- project_id uuid;
- app_id uuid nullable;
- name text;
- system_prompt text;
- developer_prompt text nullable;
- version integer;
- active boolean;
- metadata jsonb;
- created_at;
- updated_at.

#### cavada_rag_sources

Metadata fonti RAG.

Campi:

- id uuid;
- organization_id uuid;
- project_id uuid;
- app_id uuid nullable;
- source_type text; -- file, url, database, crm, storage, manual
- storage_path text nullable;
- status text;
- embedding_alias text nullable;
- last_indexed_at timestamptz nullable;
- metadata jsonb;
- created_at;
- updated_at.

---

## 13. Auth model

### 13.1 Tipi di autenticazione

Esistono due mondi separati:

1. dashboard human auth;
2. runtime request auth.

Non devono essere confusi.

### 13.2 Dashboard human auth

Fonte identita: Supabase Auth.

Flusso:

```text
Utente login via Supabase Auth
  -> JWT Supabase
  -> Cavada Auth Bridge
  -> cavada_memberships
  -> ruolo CavadaLabs
  -> permessi dashboard/API
```

Ruoli iniziali:

- cavada_super_admin: accesso totale;
- cavada_operator: operativita interna limitata;
- tenant_admin: gestione del proprio tenant/progetti;
- tenant_viewer: sola lettura.

V1: dashboard interna prima. Tenant dashboard dopo.

### 13.3 Runtime server-to-server auth

Per backend, siti server-side, automazioni e servizi interni:

- usare LiteLLM virtual keys;
- ogni key associata a organization/project/app;
- allowed aliases configurabili;
- budgets/rate limits;
- spend tracking attivo;
- key mai esposta in browser.

Header:

```text
Authorization: Bearer sk-cavada-...
```

### 13.4 Runtime browser widget auth

Per chatbot pubblici in browser:

- non esporre long-lived API key;
- usare short-lived browser session token;
- token scoped a project/app/domain/alias;
- TTL breve;
- rate limit severo;
- validazione origin/domain;
- storage caldo in Redis;
- audit opzionale in Supabase.

Header:

```text
Authorization: Bearer cws_...
```

Oppure:

```text
X-Cavada-Session: cws_...
```

### 13.5 Regola frontend

Il frontend non deve poter scegliere provider o modello reale.

Puo inviare:

- project/app public id;
- session token;
- alias consentito.

Non puo decidere:

- provider reale;
- modello costoso non autorizzato;
- nodo locale specifico;
- store prompt/response;
- fallback chain.

---

## 14. Model aliases

### 14.1 Obiettivo

Le applicazioni non devono chiamare modelli reali provider-specific.

Devono chiamare alias stabili:

- chatbot-default;
- chat-standard;
- chat-fast;
- chat-premium;
- chat-private;
- embedding-default;
- rag-default;
- ocr-default;
- vision-default.

### 14.2 Vantaggi

- cambiare provider senza cambiare app;
- applicare policy per progetto;
- fallback trasparente;
- controllo costi;
- privacy local-first;
- routing dinamico;
- dashboard piu semplice.

### 14.3 Risoluzione

Flusso:

```text
request.model = chatbot-default
  -> custom auth identifica org/project/app
  -> routing resolver carica cavada_model_aliases
  -> carica routing policy
  -> sceglie LiteLLM model group o deployment
  -> LiteLLM esegue
```

---

## 15. Routing policy

### 15.1 Strategie V1

Strategie iniziali:

- fixed;
- external_first;
- local_first;
- fallback;
- privacy_first;
- cost_first opzionale;
- latency_first opzionale.

### 15.2 Local-first esempio

```text
Alias: chatbot-default
Strategy: local_first

1. Se nodo CavadaLabs con modello compatibile e online:
   usa nodo locale.
2. Se nodo assente o degradato:
   usa provider esterno primario.
3. Se provider primario fallisce:
   usa fallback esterno.
4. Registra routing decision e attempts.
```

### 15.3 Privacy-first esempio

```text
Alias: chat-private
Strategy: privacy_first

1. Usa solo nodi locali approvati.
2. Non inviare dati a provider esterni.
3. Se nodi non disponibili, fallisci in modo esplicito.
```

### 15.4 Costo-first esempio

```text
Alias: chat-cheap
Strategy: cost_first

1. Scegli provider/modello piu economico tra quelli ammessi.
2. Rispetta limiti di latenza massima.
3. Fallback su modello alternativo.
```

### 15.5 Routing decision metadata

Ogni decisione deve registrare:

- policy id/version;
- alias richiesto;
- target scelto;
- ragione sintetica;
- candidati considerati;
- motivo esclusione candidato locale/provider;
- fallback attempt se presenti.

---

## 16. Request lifecycle

```text
1. Client invia richiesta OpenAI-compatible.
2. Dispatcher riceve la richiesta.
3. Custom auth valida API key o session token.
4. Identifica organization/project/app.
5. Verifica allowed aliases, budget, rate limit.
6. Crea record request ledger iniziale.
7. Risolve model alias.
8. Carica routing policy.
9. Verifica nodi/provider disponibili.
10. Sceglie target.
11. Scrive routing decision metadata.
12. Inoltra a LiteLLM router/deployment.
13. LiteLLM chiama provider o nodo OpenAI-compatible.
14. Gestisce streaming o non-streaming.
15. Callback raccoglie usage/cost/error.
16. Scrive ledger finale e attempts.
17. Restituisce risposta al client.
```

---

## 17. Local nodes e Orchestra

### 17.1 Strategia V1

Per V1 Orchestra deve esporre endpoint OpenAI-compatible.

Questo permette di registrare un nodo locale come deployment LiteLLM senza custom provider.

Endpoint minimi Orchestra:

```text
GET  /health
GET  /v1/models
POST /v1/chat/completions
POST /v1/embeddings opzionale
```

### 17.2 Local Agent

Il Local Agent non e il modello. E l'espositore/gestore del nodo.

Fa:

- register node;
- heartbeat;
- model inventory;
- health check Orchestra;
- auth del nodo;
- config pull;
- tunnel/polling in futuro.

### 17.3 Networking nodi

Opzioni:

1. Cloudflare Tunnel verso nodo;
2. endpoint diretto protetto;
3. job polling outbound-only futuro.

V1 preferita:

- Cloudflare Tunnel o endpoint controllato;
- OpenAI-compatible endpoint.

Job polling: post V1 se serve per clienti con rete chiusa.

---

## 18. RAG strategy

### 18.1 Decisione

Il dispatcher non deve contenere tutto il RAG engine in V1.

Ruolo dispatcher:

- auth;
- model calls;
- embeddings calls;
- logging;
- usage/cost;
- routing.

Ruolo RAG service/module:

- ingestion documenti;
- chunking;
- embeddings;
- vector store;
- retrieval;
- prompt assembly;
- citazioni/source tracking;
- evaluation.

### 18.2 Dashboard RAG V1

La dashboard puo gia gestire:

- fonti RAG;
- file/documenti;
- prompt config;
- embedding alias;
- generation alias;
- privacy settings;
- stato indicizzazione.

Ma l'esecuzione completa puo restare in un servizio separato.

---

## 19. Dashboard specification

### 19.1 Principio

Partire dalla dashboard LiteLLM e adattarla.

Non riscrivere tutto.

### 19.2 Priorita V1 interna

Pagine CavadaLabs:

- Organizations;
- Projects;
- Apps/Chatbots;
- API Keys / Project Tokens;
- Browser Sessions;
- Model Aliases;
- Routing Policies;
- Nodes;
- Node Models;
- Request Ledger;
- Usage/Costs;
- Errors;
- Prompt Configs;
- RAG Sources;
- Settings.

### 19.3 Tenant views

Post V1:

- dashboard tenant limitata;
- solo propri progetti;
- solo costi/log consentiti;
- no provider keys;
- no config globale;
- no nodo di altri tenant;
- backend authorization obbligatoria.

### 19.4 Attenzione

Non basta nascondere menu frontend. Ogni endpoint deve applicare auth server-side.

---

## 20. Logging, costi e privacy

### 20.1 Log da mantenere

- LiteLLM spend logs;
- Cavada request ledger;
- Cavada request attempts;
- Cavada usage events se servono;
- Cavada error events;
- Cavada audit events.

### 20.2 Log da evitare per default

- prompt completo;
- response completa;
- secret;
- provider key;
- header raw;
- log per ogni chunk streaming.

### 20.3 Impostazioni progetto

Ogni app/progetto deve poter definire:

- store_prompts;
- store_responses;
- payload_retention_days;
- redaction_enabled;
- debug_logging_enabled;
- allowed_providers;
- allowed_local_nodes;
- data_region;
- privacy_mode.

### 20.4 Retention

Indicazione iniziale:

- ledger sintetico: 12-24 mesi;
- attempts dettagliati: 90-180 giorni;
- error details: 90 giorni;
- debug payload: 0-30 giorni solo opt-in;
- audit: 24+ mesi.

---

## 21. Cloudflare strategy

### 21.1 Ruoli Cloudflare

Cloudflare viene usato per:

- DNS;
- TLS;
- WAF;
- protezione edge;
- rate limiting edge;
- Access per dashboard/admin path;
- Tunnel per nodi locali;
- possibilmente Containers per dispatcher/dashboard.

### 21.2 Dispatcher always-warm

Per chatbot e streaming, il dispatcher dovrebbe restare caldo.

Motivo:

- ridurre cold start;
- migliorare first token latency;
- evitare ritardi su prima richiesta;
- migliorare affidabilita streaming.

### 21.3 Componenti che possono dormire

- dashboard interna;
- staging;
- worker ingestion RAG;
- rollup/report periodici;
- nodi non produttivi.

### 21.4 Costo

La priorita V1 non e scale-to-zero aggressivo del dispatcher, ma:

- logging leggero;
- prompt/response logging off;
- dimensionamento container corretto;
- Redis esterno;
- Supabase pooling corretto;
- spend tracking attivo;
- edge rate limit per endpoint pubblici.

---

## 22. Security baseline

### 22.1 Secret management

Non esporre mai al browser:

- Supabase service role key;
- provider API keys;
- LiteLLM master key;
- Redis credentials;
- node shared secrets.

### 22.2 API keys

- hash o gestione LiteLLM virtual key;
- prefix/last4 visibili;
- revoca;
- scadenza;
- budget;
- allowed aliases;
- audit.

### 22.3 Session tokens

- TTL breve;
- Redis-backed;
- origin validation;
- rate limit;
- app/project scope;
- alias allowlist;
- revoca possibile.

### 22.4 Dashboard

- Supabase Auth;
- ruoli CavadaLabs;
- backend checks;
- audit eventi sensibili;
- Cloudflare Access opzionale per admin interno.

### 22.5 Nodi

- node credentials separate;
- heartbeat firmato o autenticato;
- tunnel protetto;
- endpoint non pubblici dove possibile;
- rotazione credenziali.

---

## 23. API surface

### 23.1 Runtime OpenAI-compatible

Mantenere:

```text
POST /v1/chat/completions
POST /chat/completions
POST /v1/embeddings
GET  /v1/models
```

### 23.2 Cavada admin API

Namespace:

```text
/cavada/admin/*
```

Endpoint indicativi:

```text
GET/POST /cavada/admin/organizations
GET/POST /cavada/admin/projects
GET/POST /cavada/admin/apps
GET/POST /cavada/admin/model-aliases
GET/POST /cavada/admin/routing-policies
GET/POST /cavada/admin/nodes
GET      /cavada/admin/request-ledger
GET      /cavada/admin/usage
GET      /cavada/admin/errors
GET/POST /cavada/admin/rag-sources
GET/POST /cavada/admin/prompt-configs
```

### 23.3 Node API

```text
POST /cavada/nodes/register
POST /cavada/nodes/heartbeat
POST /cavada/nodes/models
POST /cavada/nodes/status
```

### 23.4 Session API

```text
POST /cavada/runtime/sessions
POST /cavada/runtime/sessions/refresh
POST /cavada/runtime/sessions/revoke
```

---

## 24. MVP vertical slice

### 24.1 Obiettivo MVP

Dimostrare end-to-end:

```text
project/app -> token/key -> alias -> routing policy -> provider o nodo -> response -> ledger -> dashboard
```

### 24.2 Scope MVP

- LiteLLM OSS fork senza enterprise;
- Supabase Postgres collegato;
- Redis collegato;
- provider esterno configurato;
- virtual key progetto;
- cavada_projects;
- cavada_apps;
- cavada_model_aliases;
- cavada_routing_policies;
- cavada_nodes;
- cavada_request_ledger;
- custom auth minimo;
- routing resolver minimo;
- ledger callback;
- Orchestra mock o reale OpenAI-compatible;
- dashboard interna minima.

### 24.3 Fuori MVP

- tenant dashboard completa;
- RAG completo;
- job polling nodi;
- billing commerciale;
- multi-GPU advanced orchestration;
- OCR/STT/vision/image/video;
- custom provider Cavada se OpenAI-compatible basta;
- modifiche invasive al router LiteLLM.

---

## 25. V1 complete scope

La V1 completa aggiunge:

- dashboard interna completa;
- gestione app/chatbot;
- routing policy configurabile;
- node health UI;
- node model inventory;
- browser session token robusti;
- prompt config;
- RAG config management;
- usage/cost views;
- error views;
- audit base;
- hardening Cloudflare;
- test regressione upstream;
- documentazione tecnica.

Tenant views limitate solo se non rallentano la V1.

---

## 26. Post V1 roadmap

### V2

- tenant dashboard;
- routing costo/latenza;
- health-based deployment refresh;
- local node fallback avanzato;
- export consumi;
- privacy policy per cliente;
- RLS views tenant.

### V3

- RAG service completo;
- document ingestion;
- vector store;
- connettori storage/CRM/ERP;
- workflow AI;
- OCR/STT/vision;
- evaluation/benchmark.

### V4

- multi-node load balancing;
- GPU scheduling;
- job polling outbound-only;
- autoscaling;
- self-healing;
- SLA/margini/report finanziari;
- SDK pubblici;
- modelli multimodali avanzati.

---

## 27. Work estimates

### MVP tecnico

Stima: 350-550 ore.

### V1 prodotto interna

Stima: 900-1200 ore.

### V1 prudenziale completa

Stima: 1000-1500 ore se include tenant views, hardening esteso, RAG config, test e dashboard piu ricca.

### RAG completo separato

Stima: 400-900 ore a seconda di fonti, vector DB, permessi, qualità retrieval, ingestion e valutazione.

---

## 28. Decision log iniziale

### Decisione 1

Supabase e la piattaforma dati principale.

### Decisione 2

LiteLLM OSS e il core gateway.

### Decisione 3

LiteLLM Enterprise viene rimosso/non usato.

### Decisione 4

Le feature Enterprise-like vengono rifatte come moduli CavadaLabs.

### Decisione 5

schema.prisma non viene modificato in V1 salvo necessita estrema.

### Decisione 6

Le tabelle CavadaLabs usano migration SQL separate Supabase.

### Decisione 7

Orchestra deve esporre API OpenAI-compatible in V1.

### Decisione 8

RAG execution sta fuori dal dispatcher in V1.

### Decisione 9

La dashboard e prima interna CavadaLabs, tenant views dopo.

### Decisione 10

Prompt e response non sono salvati per default.

---

## 29. Open questions

1. Quale prodotto Cloudflare verra usato per il dispatcher sempre caldo?
2. Cloudflare Containers soddisfa timeout e streaming per chat reali?
3. Orchestra puo garantire OpenAI-compatible streaming in V1?
4. I nodi locali saranno sempre raggiungibili via tunnel o serve subito polling?
5. Quale source of truth sara usata per billing commerciale: LiteLLM spend logs, cavada_usage_events o sistema esterno?
6. Quanto tenant dashboard deve entrare nella V1?
7. Useremo Supabase direct client nel frontend tenant o solo API backend?
8. Quale vector store per RAG completo post V1?
9. Quanto conservare ledger e audit per clienti enterprise?
10. Quanto local-first deve essere garantito contrattualmente?

---

## 30. References operative

- LiteLLM virtual keys, spend tracking and DATABASE_URL: https://docs.litellm.ai/docs/proxy/virtual_keys
- LiteLLM custom auth: https://docs.litellm.ai/docs/proxy/custom_auth
- LiteLLM call hooks: https://docs.litellm.ai/docs/proxy/call_hooks
- LiteLLM Enterprise overview: https://docs.litellm.ai/docs/enterprise
- LiteLLM license file: https://github.com/BerriAI/litellm/blob/litellm_internal_staging/LICENSE
- Supabase Row Level Security: https://supabase.com/docs/guides/database/postgres/row-level-security
- Supabase Storage access control: https://supabase.com/docs/guides/storage/security/access-control
- Cloudflare Containers pricing: https://developers.cloudflare.com/containers/pricing/
- Cloudflare Containers FAQ/lifecycle: https://developers.cloudflare.com/containers/faq/

---

## 31. Prompt consigliato per Codex - fase successiva

Usare questo prompt dopo aver salvato il presente file nel repository:

```text
Read docs/CavadaLabs_AI_Platform_SPEC_MASTER.md.
You are working inside the CavadaLabs fork of LiteLLM.
Do not implement everything.
First create a POC implementation plan for the MVP vertical slice.

Focus only on:
1. removing enterprise dependencies safely;
2. creating litellm/proxy/cavada/ module skeleton;
3. adding separate Supabase SQL migrations for Cavada core tables;
4. adding Cavada custom auth MVP;
5. adding model alias/routing resolver MVP;
6. adding request ledger callback MVP;
7. registering a mock/local OpenAI-compatible node deployment;
8. adding one minimal Cavada dashboard page;
9. defining tests for upstream update safety.

For each item provide:
- files to create;
- files to edit;
- expected risk;
- smallest possible implementation;
- test to add;
- rollback strategy.

Do not make invasive changes to router.py, main.py, schema.prisma, provider internals, or dashboard login core unless you prove no lower-risk option exists.
```

---

## 32. Final rule

CavadaLabs Dispatcher deve essere un prodotto proprietario costruito sopra LiteLLM OSS, non una riscrittura disordinata di LiteLLM.

Il valore proprietario deve stare in:

- Supabase-first control plane;
- Auth bridge;
- app/project model;
- browser session tokens;
- model aliases;
- routing policies;
- node registry;
- local-first execution;
- Orchestra integration;
- request ledger;
- privacy controls;
- dashboard CavadaLabs;
- RAG/application management.

Il core LiteLLM va rispettato, isolato e aggiornato quando possibile.
