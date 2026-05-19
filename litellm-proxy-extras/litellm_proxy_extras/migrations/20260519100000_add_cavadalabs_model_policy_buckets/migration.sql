ALTER TABLE "CavadaLabs_ProjectModelPolicyTable"
  ADD COLUMN IF NOT EXISTS "endpoint_type" TEXT NOT NULL DEFAULT 'chat_completion',
  ADD COLUMN IF NOT EXISTS "model_bucket" TEXT NOT NULL DEFAULT 'default';

UPDATE "CavadaLabs_ProjectModelPolicyTable"
SET
  "endpoint_type" = COALESCE(NULLIF("endpoint_type", ''), 'chat_completion'),
  "model_bucket" = COALESCE(NULLIF("model_bucket", ''), 'default');

DROP INDEX IF EXISTS "CavadaLabs_ProjectModelPolicyTable_project_id_priority_key";
DROP INDEX IF EXISTS "CavadaLabs_ProjectModelPolicyTable_company_id_project_id_enabled_priority_idx";

CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_ModelPolicy_project_endpoint_bucket_priority_key"
  ON "CavadaLabs_ProjectModelPolicyTable"("project_id", "endpoint_type", "model_bucket", "priority");

CREATE INDEX IF NOT EXISTS "CavadaLabs_ModelPolicy_co_proj_endpoint_bucket_enabled_idx"
  ON "CavadaLabs_ProjectModelPolicyTable"("company_id", "project_id", "endpoint_type", "model_bucket", "enabled", "priority");
