-- Support request-log and usage drilldown filters by virtual key within a time range.
-- Company/Project filters use organization_id/project_id indexes; this covers the
-- api_key + startTime path used by selected-key usage/log views.

CREATE INDEX IF NOT EXISTS "LiteLLM_SpendLogs_api_key_startTime_idx"
ON "LiteLLM_SpendLogs"("api_key", "startTime");
