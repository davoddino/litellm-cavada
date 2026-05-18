-- Support Company-centric Billing/Logs filters over authoritative spend logs.
-- Company is stored internally as LiteLLM organization_id for compatibility.

CREATE INDEX IF NOT EXISTS "LiteLLM_SpendLogs_organization_id_startTime_idx"
ON "LiteLLM_SpendLogs"("organization_id", "startTime");
