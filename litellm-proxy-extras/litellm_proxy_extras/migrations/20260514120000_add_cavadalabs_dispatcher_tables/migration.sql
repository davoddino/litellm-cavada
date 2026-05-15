CREATE TABLE IF NOT EXISTS "CavadaLabs_CompanyTable" (
    "company_id" TEXT NOT NULL,
    "legal_name" TEXT NOT NULL,
    "billing_name" TEXT,
    "vat_tax_id" TEXT,
    "billing_address" JSONB NOT NULL DEFAULT '{}',
    "admin_emails" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "plan" TEXT,
    "status" TEXT NOT NULL DEFAULT 'active',
    "monthly_budget" DOUBLE PRECISION,
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "retention_policy" JSONB NOT NULL DEFAULT '{}',
    "default_guardrail_policy" TEXT,
    "default_billing_settings" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_by" TEXT NOT NULL,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_by" TEXT NOT NULL,
    CONSTRAINT "CavadaLabs_CompanyTable_pkey" PRIMARY KEY ("company_id")
);

CREATE TABLE IF NOT EXISTS "CavadaLabs_ProjectTable" (
    "project_id" TEXT NOT NULL,
    "company_id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'dev',
    "allowed_models" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "allowed_rag_collections" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "default_chatbot_settings" JSONB NOT NULL DEFAULT '{}',
    "default_guardrail_policy" TEXT,
    "budget" DOUBLE PRECISION,
    "retention_policy_override" JSONB NOT NULL DEFAULT '{}',
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_by" TEXT NOT NULL,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_by" TEXT NOT NULL,
    CONSTRAINT "CavadaLabs_ProjectTable_pkey" PRIMARY KEY ("project_id")
);

CREATE TABLE IF NOT EXISTS "CavadaLabs_ChatbotTable" (
    "chatbot_id" TEXT NOT NULL,
    "company_id" TEXT NOT NULL,
    "project_id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'draft',
    "system_prompt" TEXT NOT NULL DEFAULT '',
    "prompt_version" INTEGER NOT NULL DEFAULT 1,
    "default_language" TEXT NOT NULL DEFAULT 'it',
    "model_policy_id" TEXT,
    "assigned_rag_collections" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "assigned_guardrail_policy" TEXT,
    "allowed_domains" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "widget_theme_config" JSONB NOT NULL DEFAULT '{}',
    "fallback_message" TEXT,
    "transcript_retention_policy" JSONB NOT NULL DEFAULT '{}',
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_by" TEXT NOT NULL,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_by" TEXT NOT NULL,
    CONSTRAINT "CavadaLabs_ChatbotTable_pkey" PRIMARY KEY ("chatbot_id")
);

CREATE TABLE IF NOT EXISTS "CavadaLabs_WebTokenTable" (
    "web_token_id" TEXT NOT NULL,
    "company_id" TEXT NOT NULL,
    "project_id" TEXT NOT NULL,
    "chatbot_id" TEXT NOT NULL,
    "name" TEXT,
    "token_prefix" TEXT NOT NULL,
    "token_hash" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'active',
    "allowed_domains" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "allowed_origins" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "route_allowlist" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "ip_rpm_limit" INTEGER,
    "session_rpm_limit" INTEGER,
    "session_budget" DOUBLE PRECISION,
    "expires_at" TIMESTAMP(3) NOT NULL,
    "revoked_at" TIMESTAMP(3),
    "last_used_at" TIMESTAMP(3),
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_by" TEXT NOT NULL,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_by" TEXT NOT NULL,
    CONSTRAINT "CavadaLabs_WebTokenTable_pkey" PRIMARY KEY ("web_token_id")
);

CREATE TABLE IF NOT EXISTS "CavadaLabs_ProjectModelPolicyTable" (
    "policy_id" TEXT NOT NULL,
    "company_id" TEXT NOT NULL,
    "project_id" TEXT NOT NULL,
    "model_alias" TEXT NOT NULL,
    "provider" TEXT NOT NULL,
    "deployment_id" TEXT,
    "priority" INTEGER NOT NULL,
    "enabled" BOOLEAN NOT NULL DEFAULT true,
    "fallback_enabled" BOOLEAN NOT NULL DEFAULT true,
    "require_json_output" BOOLEAN NOT NULL DEFAULT false,
    "require_no_think" BOOLEAN NOT NULL DEFAULT false,
    "prefer_loaded_model" BOOLEAN NOT NULL DEFAULT true,
    "max_cost_input" DOUBLE PRECISION,
    "max_cost_output" DOUBLE PRECISION,
    "required_capabilities" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_by" TEXT NOT NULL,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_by" TEXT NOT NULL,
    CONSTRAINT "CavadaLabs_ProjectModelPolicyTable_pkey" PRIMARY KEY ("policy_id")
);

CREATE TABLE IF NOT EXISTS "CavadaLabs_RequestLedgerTable" (
    "ledger_id" TEXT NOT NULL,
    "request_id" TEXT NOT NULL,
    "company_id" TEXT NOT NULL,
    "project_id" TEXT NOT NULL,
    "chatbot_id" TEXT,
    "web_token_id" TEXT,
    "session_id" TEXT,
    "api_key_hash" TEXT,
    "provider" TEXT NOT NULL,
    "model" TEXT NOT NULL,
    "node_id" TEXT,
    "gpu_id" TEXT,
    "loaded_model_id" TEXT,
    "model_load_request_id" TEXT,
    "prompt_tokens" INTEGER NOT NULL DEFAULT 0,
    "completion_tokens" INTEGER NOT NULL DEFAULT 0,
    "total_tokens" INTEGER NOT NULL DEFAULT 0,
    "spend" DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    "status" TEXT NOT NULL,
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "CavadaLabs_RequestLedgerTable_pkey" PRIMARY KEY ("ledger_id")
);

CREATE TABLE IF NOT EXISTS "CavadaLabs_AuditLogTable" (
    "audit_log_id" TEXT NOT NULL,
    "actor_user_id" TEXT,
    "actor_api_key_hash" TEXT,
    "action" TEXT NOT NULL,
    "resource_type" TEXT NOT NULL,
    "resource_id" TEXT NOT NULL,
    "company_id" TEXT,
    "project_id" TEXT,
    "before_value" JSONB,
    "after_value" JSONB,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "CavadaLabs_AuditLogTable_pkey" PRIMARY KEY ("audit_log_id")
);

CREATE INDEX IF NOT EXISTS "CavadaLabs_CompanyTable_status_idx" ON "CavadaLabs_CompanyTable"("status");
CREATE INDEX IF NOT EXISTS "CavadaLabs_CompanyTable_legal_name_idx" ON "CavadaLabs_CompanyTable"("legal_name");

CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_ProjectTable_company_id_name_key" ON "CavadaLabs_ProjectTable"("company_id", "name");
CREATE INDEX IF NOT EXISTS "CavadaLabs_ProjectTable_company_id_status_idx" ON "CavadaLabs_ProjectTable"("company_id", "status");

CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_ChatbotTable_project_id_name_key" ON "CavadaLabs_ChatbotTable"("project_id", "name");
CREATE INDEX IF NOT EXISTS "CavadaLabs_ChatbotTable_company_id_project_id_status_idx" ON "CavadaLabs_ChatbotTable"("company_id", "project_id", "status");

CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_WebTokenTable_token_hash_key" ON "CavadaLabs_WebTokenTable"("token_hash");
CREATE INDEX IF NOT EXISTS "CavadaLabs_WebTokenTable_company_id_project_id_chatbot_id_idx" ON "CavadaLabs_WebTokenTable"("company_id", "project_id", "chatbot_id");
CREATE INDEX IF NOT EXISTS "CavadaLabs_WebTokenTable_status_expires_at_idx" ON "CavadaLabs_WebTokenTable"("status", "expires_at");
CREATE INDEX IF NOT EXISTS "CavadaLabs_WebTokenTable_token_prefix_idx" ON "CavadaLabs_WebTokenTable"("token_prefix");

CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_ProjectModelPolicyTable_project_id_priority_key" ON "CavadaLabs_ProjectModelPolicyTable"("project_id", "priority");
CREATE INDEX IF NOT EXISTS "CavadaLabs_ProjectModelPolicyTable_company_id_project_id_enabled_priority_idx" ON "CavadaLabs_ProjectModelPolicyTable"("company_id", "project_id", "enabled", "priority");
CREATE INDEX IF NOT EXISTS "CavadaLabs_ProjectModelPolicyTable_provider_model_alias_idx" ON "CavadaLabs_ProjectModelPolicyTable"("provider", "model_alias");

CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_RequestLedgerTable_request_id_key" ON "CavadaLabs_RequestLedgerTable"("request_id");
CREATE INDEX IF NOT EXISTS "CavadaLabs_RequestLedgerTable_company_id_created_at_idx" ON "CavadaLabs_RequestLedgerTable"("company_id", "created_at");
CREATE INDEX IF NOT EXISTS "CavadaLabs_RequestLedgerTable_project_id_created_at_idx" ON "CavadaLabs_RequestLedgerTable"("project_id", "created_at");
CREATE INDEX IF NOT EXISTS "CavadaLabs_RequestLedgerTable_chatbot_id_created_at_idx" ON "CavadaLabs_RequestLedgerTable"("chatbot_id", "created_at");
CREATE INDEX IF NOT EXISTS "CavadaLabs_RequestLedgerTable_web_token_id_created_at_idx" ON "CavadaLabs_RequestLedgerTable"("web_token_id", "created_at");
CREATE INDEX IF NOT EXISTS "CavadaLabs_RequestLedgerTable_provider_model_idx" ON "CavadaLabs_RequestLedgerTable"("provider", "model");
CREATE INDEX IF NOT EXISTS "CavadaLabs_RequestLedgerTable_node_id_gpu_id_idx" ON "CavadaLabs_RequestLedgerTable"("node_id", "gpu_id");

CREATE INDEX IF NOT EXISTS "CavadaLabs_AuditLogTable_company_id_created_at_idx" ON "CavadaLabs_AuditLogTable"("company_id", "created_at");
CREATE INDEX IF NOT EXISTS "CavadaLabs_AuditLogTable_project_id_created_at_idx" ON "CavadaLabs_AuditLogTable"("project_id", "created_at");
CREATE INDEX IF NOT EXISTS "CavadaLabs_AuditLogTable_resource_type_resource_id_idx" ON "CavadaLabs_AuditLogTable"("resource_type", "resource_id");
CREATE INDEX IF NOT EXISTS "CavadaLabs_AuditLogTable_actor_user_id_created_at_idx" ON "CavadaLabs_AuditLogTable"("actor_user_id", "created_at");

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_ProjectTable_company_id_fkey') THEN
        ALTER TABLE "CavadaLabs_ProjectTable" ADD CONSTRAINT "CavadaLabs_ProjectTable_company_id_fkey" FOREIGN KEY ("company_id") REFERENCES "CavadaLabs_CompanyTable"("company_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_ChatbotTable_company_id_fkey') THEN
        ALTER TABLE "CavadaLabs_ChatbotTable" ADD CONSTRAINT "CavadaLabs_ChatbotTable_company_id_fkey" FOREIGN KEY ("company_id") REFERENCES "CavadaLabs_CompanyTable"("company_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_ChatbotTable_project_id_fkey') THEN
        ALTER TABLE "CavadaLabs_ChatbotTable" ADD CONSTRAINT "CavadaLabs_ChatbotTable_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "CavadaLabs_ProjectTable"("project_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_WebTokenTable_company_id_fkey') THEN
        ALTER TABLE "CavadaLabs_WebTokenTable" ADD CONSTRAINT "CavadaLabs_WebTokenTable_company_id_fkey" FOREIGN KEY ("company_id") REFERENCES "CavadaLabs_CompanyTable"("company_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_WebTokenTable_project_id_fkey') THEN
        ALTER TABLE "CavadaLabs_WebTokenTable" ADD CONSTRAINT "CavadaLabs_WebTokenTable_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "CavadaLabs_ProjectTable"("project_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_WebTokenTable_chatbot_id_fkey') THEN
        ALTER TABLE "CavadaLabs_WebTokenTable" ADD CONSTRAINT "CavadaLabs_WebTokenTable_chatbot_id_fkey" FOREIGN KEY ("chatbot_id") REFERENCES "CavadaLabs_ChatbotTable"("chatbot_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_ProjectModelPolicyTable_company_id_fkey') THEN
        ALTER TABLE "CavadaLabs_ProjectModelPolicyTable" ADD CONSTRAINT "CavadaLabs_ProjectModelPolicyTable_company_id_fkey" FOREIGN KEY ("company_id") REFERENCES "CavadaLabs_CompanyTable"("company_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_ProjectModelPolicyTable_project_id_fkey') THEN
        ALTER TABLE "CavadaLabs_ProjectModelPolicyTable" ADD CONSTRAINT "CavadaLabs_ProjectModelPolicyTable_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "CavadaLabs_ProjectTable"("project_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
END $$;
