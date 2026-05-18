-- Support Company/Project-centric Virtual Keys list and filter paths.
-- Company is stored internally as organization_id for LiteLLM compatibility.

CREATE INDEX IF NOT EXISTS "LiteLLM_VerificationToken_organization_id_idx"
ON "LiteLLM_VerificationToken"("organization_id");

CREATE INDEX IF NOT EXISTS "LiteLLM_VerificationToken_project_id_idx"
ON "LiteLLM_VerificationToken"("project_id");

CREATE INDEX IF NOT EXISTS "LiteLLM_DeletedVerificationToken_project_id_idx"
ON "LiteLLM_DeletedVerificationToken"("project_id");
