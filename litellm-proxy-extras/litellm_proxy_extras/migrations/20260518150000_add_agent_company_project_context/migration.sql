ALTER TABLE "LiteLLM_AgentsTable"
ADD COLUMN IF NOT EXISTS "company_id" TEXT;

ALTER TABLE "LiteLLM_AgentsTable"
ADD COLUMN IF NOT EXISTS "project_id" TEXT;

CREATE INDEX IF NOT EXISTS "LiteLLM_AgentsTable_company_id_idx"
ON "LiteLLM_AgentsTable"("company_id");

CREATE INDEX IF NOT EXISTS "LiteLLM_AgentsTable_project_id_idx"
ON "LiteLLM_AgentsTable"("project_id");
