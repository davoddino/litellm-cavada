ALTER TABLE "LiteLLM_ManagedVectorStoresTable"
ADD COLUMN IF NOT EXISTS "project_id" TEXT;

CREATE INDEX IF NOT EXISTS "LiteLLM_ManagedVectorStoresTable_project_id_idx"
ON "LiteLLM_ManagedVectorStoresTable"("project_id");
