ALTER TABLE "CavadaLabs_ProjectModelPolicyTable"
  ADD COLUMN IF NOT EXISTS "key_id" TEXT;

DROP INDEX IF EXISTS "CavadaLabs_ModelPolicy_project_endpoint_bucket_priority_key";
DROP INDEX IF EXISTS "CavadaLabs_ModelPolicy_project_key_endpoint_bucket_enabled_idx";
DROP INDEX IF EXISTS "CavadaLabs_ModelPolicy_project_endpoint_bucket_priority_null_key";
DROP INDEX IF EXISTS "CavadaLabs_ModelPolicy_project_key_endpoint_bucket_priority_key";

CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_ModelPolicy_project_endpoint_bucket_priority_null_key"
  ON "CavadaLabs_ProjectModelPolicyTable"("project_id", "endpoint_type", "model_bucket", "priority")
  WHERE "key_id" IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_ModelPolicy_project_key_endpoint_bucket_priority_key"
  ON "CavadaLabs_ProjectModelPolicyTable"("project_id", "key_id", "endpoint_type", "model_bucket", "priority")
  WHERE "key_id" IS NOT NULL;

CREATE INDEX IF NOT EXISTS "CavadaLabs_ModelPolicy_project_key_endpoint_bucket_enabled_idx"
  ON "CavadaLabs_ProjectModelPolicyTable"("project_id", "key_id", "endpoint_type", "model_bucket", "enabled", "priority");
