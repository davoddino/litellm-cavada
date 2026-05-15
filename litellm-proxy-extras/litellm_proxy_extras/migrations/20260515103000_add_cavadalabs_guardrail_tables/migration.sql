CREATE TABLE IF NOT EXISTS "CavadaLabs_GuardrailPolicyTable" (
    "policy_id" TEXT NOT NULL,
    "company_id" TEXT NOT NULL,
    "project_id" TEXT,
    "chatbot_id" TEXT,
    "name" TEXT NOT NULL,
    "version" INTEGER NOT NULL DEFAULT 1,
    "scope" TEXT NOT NULL DEFAULT 'company',
    "status" TEXT NOT NULL DEFAULT 'draft',
    "enforcement_mode" TEXT NOT NULL DEFAULT 'enforce',
    "description" TEXT,
    "categories" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "rules" JSONB NOT NULL DEFAULT '{}',
    "blocked_patterns" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "redaction_patterns" JSONB NOT NULL DEFAULT '{}',
    "pii_detection_enabled" BOOLEAN NOT NULL DEFAULT true,
    "prompt_injection_detection_enabled" BOOLEAN NOT NULL DEFAULT true,
    "log_raw_content" BOOLEAN NOT NULL DEFAULT false,
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_by" TEXT NOT NULL,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_by" TEXT NOT NULL,
    CONSTRAINT "CavadaLabs_GuardrailPolicyTable_pkey" PRIMARY KEY ("policy_id")
);

CREATE TABLE IF NOT EXISTS "CavadaLabs_GuardrailDecisionLogTable" (
    "decision_id" TEXT NOT NULL,
    "policy_id" TEXT,
    "policy_name" TEXT,
    "company_id" TEXT NOT NULL,
    "project_id" TEXT,
    "chatbot_id" TEXT,
    "web_token_id" TEXT,
    "session_id" TEXT,
    "request_id" TEXT,
    "phase" TEXT NOT NULL DEFAULT 'pre_call',
    "decision" TEXT NOT NULL,
    "action" TEXT NOT NULL,
    "confidence" DOUBLE PRECISION,
    "reason_code" TEXT,
    "triggered_rules" JSONB NOT NULL DEFAULT '[]',
    "redaction_summary" JSONB NOT NULL DEFAULT '{}',
    "latency_ms" INTEGER NOT NULL DEFAULT 0,
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "CavadaLabs_GuardrailDecisionLogTable_pkey" PRIMARY KEY ("decision_id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_GuardrailPolicyTable_scope_version_key" ON "CavadaLabs_GuardrailPolicyTable"("company_id", "project_id", "chatbot_id", "name", "version");
CREATE INDEX IF NOT EXISTS "CavadaLabs_GuardrailPolicyTable_company_id_scope_status_idx" ON "CavadaLabs_GuardrailPolicyTable"("company_id", "scope", "status");
CREATE INDEX IF NOT EXISTS "CavadaLabs_GuardrailPolicyTable_project_id_status_idx" ON "CavadaLabs_GuardrailPolicyTable"("project_id", "status");
CREATE INDEX IF NOT EXISTS "CavadaLabs_GuardrailPolicyTable_chatbot_id_status_idx" ON "CavadaLabs_GuardrailPolicyTable"("chatbot_id", "status");
CREATE INDEX IF NOT EXISTS "CavadaLabs_GuardrailPolicyTable_name_version_idx" ON "CavadaLabs_GuardrailPolicyTable"("name", "version");

CREATE INDEX IF NOT EXISTS "CavadaLabs_GuardrailDecisionLogTable_policy_id_created_at_idx" ON "CavadaLabs_GuardrailDecisionLogTable"("policy_id", "created_at");
CREATE INDEX IF NOT EXISTS "CavadaLabs_GuardrailDecisionLogTable_company_id_created_at_idx" ON "CavadaLabs_GuardrailDecisionLogTable"("company_id", "created_at");
CREATE INDEX IF NOT EXISTS "CavadaLabs_GuardrailDecisionLogTable_project_id_created_at_idx" ON "CavadaLabs_GuardrailDecisionLogTable"("project_id", "created_at");
CREATE INDEX IF NOT EXISTS "CavadaLabs_GuardrailDecisionLogTable_chatbot_id_created_at_idx" ON "CavadaLabs_GuardrailDecisionLogTable"("chatbot_id", "created_at");
CREATE INDEX IF NOT EXISTS "CavadaLabs_GuardrailDecisionLogTable_decision_created_at_idx" ON "CavadaLabs_GuardrailDecisionLogTable"("decision", "created_at");
CREATE INDEX IF NOT EXISTS "CavadaLabs_GuardrailDecisionLogTable_request_id_idx" ON "CavadaLabs_GuardrailDecisionLogTable"("request_id");

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_GuardrailPolicyTable_company_id_fkey') THEN
        ALTER TABLE "CavadaLabs_GuardrailPolicyTable" ADD CONSTRAINT "CavadaLabs_GuardrailPolicyTable_company_id_fkey" FOREIGN KEY ("company_id") REFERENCES "CavadaLabs_CompanyTable"("company_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_GuardrailPolicyTable_project_id_fkey') THEN
        ALTER TABLE "CavadaLabs_GuardrailPolicyTable" ADD CONSTRAINT "CavadaLabs_GuardrailPolicyTable_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "CavadaLabs_ProjectTable"("project_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_GuardrailPolicyTable_chatbot_id_fkey') THEN
        ALTER TABLE "CavadaLabs_GuardrailPolicyTable" ADD CONSTRAINT "CavadaLabs_GuardrailPolicyTable_chatbot_id_fkey" FOREIGN KEY ("chatbot_id") REFERENCES "CavadaLabs_ChatbotTable"("chatbot_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_GuardrailDecisionLogTable_policy_id_fkey') THEN
        ALTER TABLE "CavadaLabs_GuardrailDecisionLogTable" ADD CONSTRAINT "CavadaLabs_GuardrailDecisionLogTable_policy_id_fkey" FOREIGN KEY ("policy_id") REFERENCES "CavadaLabs_GuardrailPolicyTable"("policy_id") ON DELETE SET NULL ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_GuardrailDecisionLogTable_company_id_fkey') THEN
        ALTER TABLE "CavadaLabs_GuardrailDecisionLogTable" ADD CONSTRAINT "CavadaLabs_GuardrailDecisionLogTable_company_id_fkey" FOREIGN KEY ("company_id") REFERENCES "CavadaLabs_CompanyTable"("company_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_GuardrailDecisionLogTable_project_id_fkey') THEN
        ALTER TABLE "CavadaLabs_GuardrailDecisionLogTable" ADD CONSTRAINT "CavadaLabs_GuardrailDecisionLogTable_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "CavadaLabs_ProjectTable"("project_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_GuardrailDecisionLogTable_chatbot_id_fkey') THEN
        ALTER TABLE "CavadaLabs_GuardrailDecisionLogTable" ADD CONSTRAINT "CavadaLabs_GuardrailDecisionLogTable_chatbot_id_fkey" FOREIGN KEY ("chatbot_id") REFERENCES "CavadaLabs_ChatbotTable"("chatbot_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_GuardrailDecisionLogTable_web_token_id_fkey') THEN
        ALTER TABLE "CavadaLabs_GuardrailDecisionLogTable" ADD CONSTRAINT "CavadaLabs_GuardrailDecisionLogTable_web_token_id_fkey" FOREIGN KEY ("web_token_id") REFERENCES "CavadaLabs_WebTokenTable"("web_token_id") ON DELETE SET NULL ON UPDATE CASCADE;
    END IF;
END $$;
