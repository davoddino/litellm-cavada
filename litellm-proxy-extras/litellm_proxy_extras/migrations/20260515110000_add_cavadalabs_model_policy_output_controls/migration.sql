ALTER TABLE "CavadaLabs_ProjectModelPolicyTable"
    ADD COLUMN IF NOT EXISTS "force_json_output" BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS "json_schema" JSONB,
    ADD COLUMN IF NOT EXISTS "strict_json" BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS "repair_invalid_json" BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS "retry_on_invalid_json" BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS "no_think" BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS "reasoning_mode" TEXT,
    ADD COLUMN IF NOT EXISTS "hide_reasoning" BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS "strip_thinking_tags" BOOLEAN NOT NULL DEFAULT false;
