ALTER TABLE "LiteLLM_ManagedVectorStoreTable"
ADD COLUMN IF NOT EXISTS "project_id" TEXT;

CREATE INDEX IF NOT EXISTS "LiteLLM_ManagedVectorStoreTable_project_id_created_at_idx"
ON "LiteLLM_ManagedVectorStoreTable"("project_id", "created_at" DESC);
