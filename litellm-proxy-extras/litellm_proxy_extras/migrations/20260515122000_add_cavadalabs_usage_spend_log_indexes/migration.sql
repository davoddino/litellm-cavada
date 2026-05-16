CREATE INDEX IF NOT EXISTS "LiteLLM_SpendLogs_api_key_startTime_idx"
    ON "LiteLLM_SpendLogs"("api_key", "startTime");

CREATE INDEX IF NOT EXISTS "LiteLLM_SpendLogs_team_id_startTime_idx"
    ON "LiteLLM_SpendLogs"("team_id", "startTime");

CREATE INDEX IF NOT EXISTS "LiteLLM_SpendLogs_organization_id_startTime_idx"
    ON "LiteLLM_SpendLogs"("organization_id", "startTime");

CREATE INDEX IF NOT EXISTS "LiteLLM_SpendLogs_model_startTime_idx"
    ON "LiteLLM_SpendLogs"("model", "startTime");

CREATE INDEX IF NOT EXISTS "LiteLLM_SpendLogs_model_group_startTime_idx"
    ON "LiteLLM_SpendLogs"("model_group", "startTime");

CREATE INDEX IF NOT EXISTS "LiteLLM_SpendLogs_metadata_gin_idx"
    ON "LiteLLM_SpendLogs" USING GIN ("metadata");
