CREATE TABLE IF NOT EXISTS "CavadaLabs_CompanyMemberTable" (
    "membership_id" TEXT NOT NULL,
    "company_id" TEXT NOT NULL,
    "user_id" TEXT NOT NULL,
    "role" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_by" TEXT,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_by" TEXT,
    CONSTRAINT "CavadaLabs_CompanyMemberTable_pkey" PRIMARY KEY ("membership_id")
);

CREATE TABLE IF NOT EXISTS "CavadaLabs_ProjectMemberTable" (
    "membership_id" TEXT NOT NULL,
    "project_id" TEXT NOT NULL,
    "user_id" TEXT NOT NULL,
    "role" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_by" TEXT,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_by" TEXT,
    CONSTRAINT "CavadaLabs_ProjectMemberTable_pkey" PRIMARY KEY ("membership_id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_CompanyMemberTable_company_id_user_id_key"
    ON "CavadaLabs_CompanyMemberTable"("company_id", "user_id");
CREATE INDEX IF NOT EXISTS "CavadaLabs_CompanyMemberTable_company_id_role_idx"
    ON "CavadaLabs_CompanyMemberTable"("company_id", "role");
CREATE INDEX IF NOT EXISTS "CavadaLabs_CompanyMemberTable_user_id_role_idx"
    ON "CavadaLabs_CompanyMemberTable"("user_id", "role");

CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_ProjectMemberTable_project_id_user_id_key"
    ON "CavadaLabs_ProjectMemberTable"("project_id", "user_id");
CREATE INDEX IF NOT EXISTS "CavadaLabs_ProjectMemberTable_project_id_role_idx"
    ON "CavadaLabs_ProjectMemberTable"("project_id", "role");
CREATE INDEX IF NOT EXISTS "CavadaLabs_ProjectMemberTable_user_id_role_idx"
    ON "CavadaLabs_ProjectMemberTable"("user_id", "role");

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'CavadaLabs_CompanyMemberTable_role_check'
    ) THEN
        ALTER TABLE "CavadaLabs_CompanyMemberTable"
            ADD CONSTRAINT "CavadaLabs_CompanyMemberTable_role_check"
            CHECK ("role" IN ('company_admin', 'operator', 'viewer'));
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'CavadaLabs_ProjectMemberTable_role_check'
    ) THEN
        ALTER TABLE "CavadaLabs_ProjectMemberTable"
            ADD CONSTRAINT "CavadaLabs_ProjectMemberTable_role_check"
            CHECK ("role" IN ('project_admin', 'operator', 'viewer'));
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'CavadaLabs_CompanyMemberTable_company_id_fkey'
    ) THEN
        ALTER TABLE "CavadaLabs_CompanyMemberTable"
            ADD CONSTRAINT "CavadaLabs_CompanyMemberTable_company_id_fkey"
            FOREIGN KEY ("company_id")
            REFERENCES "CavadaLabs_CompanyTable"("company_id")
            ON DELETE CASCADE
            ON UPDATE CASCADE;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'CavadaLabs_CompanyMemberTable_user_id_fkey'
    ) THEN
        ALTER TABLE "CavadaLabs_CompanyMemberTable"
            ADD CONSTRAINT "CavadaLabs_CompanyMemberTable_user_id_fkey"
            FOREIGN KEY ("user_id")
            REFERENCES "LiteLLM_UserTable"("user_id")
            ON DELETE CASCADE
            ON UPDATE CASCADE;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'CavadaLabs_ProjectMemberTable_project_id_fkey'
    ) THEN
        ALTER TABLE "CavadaLabs_ProjectMemberTable"
            ADD CONSTRAINT "CavadaLabs_ProjectMemberTable_project_id_fkey"
            FOREIGN KEY ("project_id")
            REFERENCES "CavadaLabs_ProjectTable"("project_id")
            ON DELETE CASCADE
            ON UPDATE CASCADE;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'CavadaLabs_ProjectMemberTable_user_id_fkey'
    ) THEN
        ALTER TABLE "CavadaLabs_ProjectMemberTable"
            ADD CONSTRAINT "CavadaLabs_ProjectMemberTable_user_id_fkey"
            FOREIGN KEY ("user_id")
            REFERENCES "LiteLLM_UserTable"("user_id")
            ON DELETE CASCADE
            ON UPDATE CASCADE;
    END IF;
END $$;
