-- Materialize project spend attribution for CavadaLabs usage surfaces.
-- Company usage can reuse organization_id, but project usage needs a first-class
-- spend log column and a daily aggregate table to avoid JSON scans or current-key joins.

ALTER TABLE "LiteLLM_SpendLogs"
ADD COLUMN IF NOT EXISTS "project_id" TEXT;

UPDATE "LiteLLM_SpendLogs"
SET "project_id" = NULLIF("metadata"->>'user_api_key_project_id', '')
WHERE ("project_id" IS NULL OR "project_id" = '')
  AND "metadata" IS NOT NULL
  AND jsonb_typeof("metadata") = 'object'
  AND NULLIF("metadata"->>'user_api_key_project_id', '') IS NOT NULL
  AND EXISTS (
    SELECT 1
    FROM "LiteLLM_ProjectTable" p
    WHERE p."project_id" = NULLIF("LiteLLM_SpendLogs"."metadata"->>'user_api_key_project_id', '')
  );

CREATE INDEX IF NOT EXISTS "LiteLLM_SpendLogs_project_id_startTime_idx"
ON "LiteLLM_SpendLogs"("project_id", "startTime");

CREATE TABLE IF NOT EXISTS "LiteLLM_DailyProjectSpend" (
    "id" TEXT NOT NULL,
    "project_id" TEXT NOT NULL,
    "date" TEXT NOT NULL,
    "api_key" TEXT NOT NULL,
    "model" TEXT,
    "model_group" TEXT,
    "custom_llm_provider" TEXT,
    "mcp_namespaced_tool_name" TEXT,
    "endpoint" TEXT,
    "prompt_tokens" BIGINT NOT NULL DEFAULT 0,
    "completion_tokens" BIGINT NOT NULL DEFAULT 0,
    "cache_read_input_tokens" BIGINT NOT NULL DEFAULT 0,
    "cache_creation_input_tokens" BIGINT NOT NULL DEFAULT 0,
    "spend" DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    "api_requests" BIGINT NOT NULL DEFAULT 0,
    "successful_requests" BIGINT NOT NULL DEFAULT 0,
    "failed_requests" BIGINT NOT NULL DEFAULT 0,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "LiteLLM_DailyProjectSpend_pkey" PRIMARY KEY ("id")
);

DELETE FROM "LiteLLM_DailyProjectSpend"
WHERE "project_id" IS NULL;

DELETE FROM "LiteLLM_DailyProjectSpend" d
WHERE NOT EXISTS (
    SELECT 1
    FROM "LiteLLM_ProjectTable" p
    WHERE p."project_id" = d."project_id"
);

ALTER TABLE "LiteLLM_DailyProjectSpend"
ALTER COLUMN "project_id" SET NOT NULL;

CREATE INDEX IF NOT EXISTS "LiteLLM_DailyProjectSpend_date_idx"
ON "LiteLLM_DailyProjectSpend"("date");

CREATE INDEX IF NOT EXISTS "LiteLLM_DailyProjectSpend_project_id_date_idx"
ON "LiteLLM_DailyProjectSpend"("project_id", "date");

CREATE INDEX IF NOT EXISTS "LiteLLM_DailyProjectSpend_api_key_idx"
ON "LiteLLM_DailyProjectSpend"("api_key");

CREATE INDEX IF NOT EXISTS "LiteLLM_DailyProjectSpend_model_idx"
ON "LiteLLM_DailyProjectSpend"("model");

CREATE INDEX IF NOT EXISTS "LiteLLM_DailyProjectSpend_mcp_namespaced_tool_name_idx"
ON "LiteLLM_DailyProjectSpend"("mcp_namespaced_tool_name");

CREATE INDEX IF NOT EXISTS "LiteLLM_DailyProjectSpend_endpoint_idx"
ON "LiteLLM_DailyProjectSpend"("endpoint");

CREATE UNIQUE INDEX IF NOT EXISTS "LiteLLM_DailyProjectSpend_project_id_date_api_key_key"
ON "LiteLLM_DailyProjectSpend"("project_id", "date", "api_key", "model", "custom_llm_provider", "mcp_namespaced_tool_name", "endpoint");

WITH spend_rows AS (
    SELECT
        NULLIF("project_id", '') AS "project_id",
        ("startTime" AT TIME ZONE 'UTC')::date::text AS "date",
        COALESCE("api_key", '') AS "api_key",
        COALESCE("model", '') AS "model",
        COALESCE("model_group", '') AS "model_group",
        COALESCE("custom_llm_provider", '') AS "custom_llm_provider",
        COALESCE("mcp_namespaced_tool_name", '') AS "mcp_namespaced_tool_name",
        CASE "call_type"
            WHEN 'acompletion' THEN '/chat/completions'
            WHEN 'atext_completion' THEN '/completions'
            WHEN 'aembedding' THEN '/embeddings'
            WHEN 'aimage_generation' THEN '/image/generations'
            WHEN 'aspeech' THEN '/audio/speech'
            WHEN 'atranscription' THEN '/audio/transcriptions'
            WHEN 'amoderation' THEN '/moderations'
            WHEN 'arerank' THEN '/rerank'
            WHEN 'aresponses' THEN '/responses'
            WHEN '_aresponses_websocket' THEN '/responses'
            WHEN 'aocr' THEN '/ocr'
            WHEN 'asearch' THEN '/search'
            ELSE COALESCE("call_type", '')
        END AS "endpoint",
        COALESCE("prompt_tokens", 0)::bigint AS "prompt_tokens",
        COALESCE("completion_tokens", 0)::bigint AS "completion_tokens",
        CASE
            WHEN jsonb_typeof("metadata"->'usage_object'->'cache_read_input_tokens') = 'number'
            THEN ("metadata"->'usage_object'->>'cache_read_input_tokens')::bigint
            ELSE 0
        END AS "cache_read_input_tokens",
        CASE
            WHEN jsonb_typeof("metadata"->'usage_object'->'cache_creation_input_tokens') = 'number'
            THEN ("metadata"->'usage_object'->>'cache_creation_input_tokens')::bigint
            ELSE 0
        END AS "cache_creation_input_tokens",
        COALESCE("spend", 0.0) AS "spend",
        COALESCE(NULLIF("status", ''), 'success') AS "status"
    FROM "LiteLLM_SpendLogs"
    WHERE NULLIF("project_id", '') IS NOT NULL
      AND EXISTS (
        SELECT 1
        FROM "LiteLLM_ProjectTable" p
        WHERE p."project_id" = NULLIF("LiteLLM_SpendLogs"."project_id", '')
      )
),
daily_project_spend AS (
    SELECT
        "project_id",
        "date",
        "api_key",
        "model",
        MAX("model_group") AS "model_group",
        "custom_llm_provider",
        "mcp_namespaced_tool_name",
        "endpoint",
        SUM("prompt_tokens")::bigint AS "prompt_tokens",
        SUM("completion_tokens")::bigint AS "completion_tokens",
        SUM("cache_read_input_tokens")::bigint AS "cache_read_input_tokens",
        SUM("cache_creation_input_tokens")::bigint AS "cache_creation_input_tokens",
        SUM("spend") AS "spend",
        COUNT(*)::bigint AS "api_requests",
        COUNT(*) FILTER (WHERE "status" = 'success')::bigint AS "successful_requests",
        COUNT(*) FILTER (WHERE "status" <> 'success')::bigint AS "failed_requests"
    FROM spend_rows
    GROUP BY
        "project_id",
        "date",
        "api_key",
        "model",
        "custom_llm_provider",
        "mcp_namespaced_tool_name",
        "endpoint"
)
INSERT INTO "LiteLLM_DailyProjectSpend" (
    "id",
    "project_id",
    "date",
    "api_key",
    "model",
    "model_group",
    "custom_llm_provider",
    "mcp_namespaced_tool_name",
    "endpoint",
    "prompt_tokens",
    "completion_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "spend",
    "api_requests",
    "successful_requests",
    "failed_requests",
    "created_at",
    "updated_at"
)
SELECT
    md5(CONCAT_WS('|', "project_id", "date", "api_key", "model", "custom_llm_provider", "mcp_namespaced_tool_name", "endpoint")),
    "project_id",
    "date",
    "api_key",
    "model",
    "model_group",
    "custom_llm_provider",
    "mcp_namespaced_tool_name",
    "endpoint",
    "prompt_tokens",
    "completion_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "spend",
    "api_requests",
    "successful_requests",
    "failed_requests",
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM daily_project_spend
ON CONFLICT ("project_id", "date", "api_key", "model", "custom_llm_provider", "mcp_namespaced_tool_name", "endpoint")
DO UPDATE SET
    "model_group" = EXCLUDED."model_group",
    "prompt_tokens" = EXCLUDED."prompt_tokens",
    "completion_tokens" = EXCLUDED."completion_tokens",
    "cache_read_input_tokens" = EXCLUDED."cache_read_input_tokens",
    "cache_creation_input_tokens" = EXCLUDED."cache_creation_input_tokens",
    "spend" = EXCLUDED."spend",
    "api_requests" = EXCLUDED."api_requests",
    "successful_requests" = EXCLUDED."successful_requests",
    "failed_requests" = EXCLUDED."failed_requests",
    "updated_at" = CURRENT_TIMESTAMP;
