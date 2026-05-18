ALTER TABLE "LiteLLM_GuardrailsTable"
ADD COLUMN IF NOT EXISTS "project_id" TEXT;

UPDATE "LiteLLM_GuardrailsTable" AS g
SET "project_id" = p."project_id"
FROM "LiteLLM_ProjectTable" AS p
WHERE g."project_id" IS NULL
  AND g."team_id" IS NOT NULL
  AND p."team_id" = g."team_id"
  AND NOT EXISTS (
    SELECT 1
    FROM "LiteLLM_ProjectTable" AS p2
    WHERE p2."team_id" = g."team_id"
      AND p2."project_id" <> p."project_id"
  );

CREATE INDEX IF NOT EXISTS "LiteLLM_GuardrailsTable_project_id_idx"
ON "LiteLLM_GuardrailsTable"("project_id");
