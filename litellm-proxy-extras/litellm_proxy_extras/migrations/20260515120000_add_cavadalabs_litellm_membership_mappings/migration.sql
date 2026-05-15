ALTER TABLE "CavadaLabs_CompanyTable"
    ADD COLUMN IF NOT EXISTS "litellm_organization_id" TEXT;

ALTER TABLE "CavadaLabs_ProjectTable"
    ADD COLUMN IF NOT EXISTS "litellm_team_id" TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_CompanyTable_litellm_organization_id_key"
    ON "CavadaLabs_CompanyTable"("litellm_organization_id");

CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_ProjectTable_litellm_team_id_key"
    ON "CavadaLabs_ProjectTable"("litellm_team_id");

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'CavadaLabs_CompanyTable_litellm_organization_id_fkey'
    ) THEN
        ALTER TABLE "CavadaLabs_CompanyTable"
            ADD CONSTRAINT "CavadaLabs_CompanyTable_litellm_organization_id_fkey"
            FOREIGN KEY ("litellm_organization_id")
            REFERENCES "LiteLLM_OrganizationTable"("organization_id")
            ON DELETE SET NULL
            ON UPDATE CASCADE;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'CavadaLabs_ProjectTable_litellm_team_id_fkey'
    ) THEN
        ALTER TABLE "CavadaLabs_ProjectTable"
            ADD CONSTRAINT "CavadaLabs_ProjectTable_litellm_team_id_fkey"
            FOREIGN KEY ("litellm_team_id")
            REFERENCES "LiteLLM_TeamTable"("team_id")
            ON DELETE SET NULL
            ON UPDATE CASCADE;
    END IF;
END $$;
