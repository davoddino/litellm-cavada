CREATE OR REPLACE FUNCTION _cavadalabs_safe_jsonb_object(value jsonb)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
    parsed jsonb;
BEGIN
    IF value IS NULL THEN
        RETURN '{}'::jsonb;
    END IF;

    IF jsonb_typeof(value) = 'object' THEN
        RETURN value;
    END IF;

    IF jsonb_typeof(value) = 'string' THEN
        BEGIN
            parsed := (value #>> '{}')::jsonb;
            IF jsonb_typeof(parsed) = 'object' THEN
                RETURN parsed;
            END IF;
        EXCEPTION WHEN others THEN
            RETURN '{}'::jsonb;
        END;
    END IF;

    RETURN '{}'::jsonb;
END;
$$;

WITH normalized_spend_logs AS (
    SELECT
        s.*,
        _cavadalabs_safe_jsonb_object(s."metadata") AS metadata_obj
    FROM "LiteLLM_SpendLogs" s
),
extracted_spend_logs AS (
    SELECT
        s.*,
        key_hash.metadata_api_key_hash
    FROM normalized_spend_logs s
    LEFT JOIN LATERAL (
        SELECT candidate.value AS metadata_api_key_hash
        FROM (
            VALUES
                (NULLIF(s.metadata_obj ->> 'user_api_key_hash', '')),
                (NULLIF(s.metadata_obj ->> 'api_key_hash', '')),
                (NULLIF(s.metadata_obj -> 'cavadalabs' ->> 'user_api_key_hash', '')),
                (NULLIF(s.metadata_obj -> 'cavadalabs' ->> 'api_key_hash', '')),
                (NULLIF(s.metadata_obj -> 'spend_logs_metadata' ->> 'user_api_key_hash', '')),
                (NULLIF(s.metadata_obj -> 'spend_logs_metadata' ->> 'api_key_hash', '')),
                (NULLIF(s.metadata_obj ->> 'user_api_key', '')),
                (NULLIF(s.metadata_obj -> 'cavadalabs' ->> 'user_api_key', '')),
                (NULLIF(s.metadata_obj -> 'spend_logs_metadata' ->> 'user_api_key', ''))
        ) AS candidate(value)
        WHERE candidate.value IS NOT NULL
            AND candidate.value NOT LIKE 'sk-%'
        LIMIT 1
    ) key_hash ON TRUE
),
normalized_keys AS (
    SELECT
        key_rows."token",
        key_rows."team_id",
        key_rows."organization_id",
        key_rows.metadata_obj
    FROM (
        SELECT DISTINCT ON (raw_keys."token")
            raw_keys."token",
            raw_keys."team_id",
            raw_keys."organization_id",
            raw_keys.metadata_obj
        FROM (
            SELECT
                k."token",
                k."team_id",
                k."organization_id",
                _cavadalabs_safe_jsonb_object(k."metadata") AS metadata_obj,
                0 AS source_priority
            FROM "LiteLLM_VerificationToken" k
            UNION ALL
            SELECT
                k."token",
                k."team_id",
                k."organization_id",
                _cavadalabs_safe_jsonb_object(k."metadata") AS metadata_obj,
                1 AS source_priority
            FROM "LiteLLM_DeletedVerificationToken" k
        ) raw_keys
        WHERE raw_keys."token" IS NOT NULL
            AND raw_keys."token" <> ''
        ORDER BY raw_keys."token", raw_keys.source_priority
    ) key_rows
),
key_context AS (
    SELECT
        k."token",
        COALESCE(
            NULLIF(k.metadata_obj ->> 'cavadalabs_company_id', ''),
            NULLIF(k.metadata_obj ->> 'company_id', ''),
            NULLIF(k.metadata_obj -> 'cavadalabs' ->> 'company_id', ''),
            NULLIF(k.metadata_obj -> 'spend_logs_metadata' ->> 'cavadalabs_company_id', ''),
            NULLIF(k.metadata_obj -> 'spend_logs_metadata' ->> 'company_id', '')
        ) AS key_company_id,
        COALESCE(
            NULLIF(k.metadata_obj ->> 'cavadalabs_project_id', ''),
            NULLIF(k.metadata_obj ->> 'project_id', ''),
            NULLIF(k.metadata_obj -> 'cavadalabs' ->> 'project_id', ''),
            NULLIF(k.metadata_obj -> 'spend_logs_metadata' ->> 'cavadalabs_project_id', ''),
            NULLIF(k.metadata_obj -> 'spend_logs_metadata' ->> 'project_id', '')
        ) AS key_project_id,
        COALESCE(
            NULLIF(k.metadata_obj ->> 'cavadalabs_chatbot_id', ''),
            NULLIF(k.metadata_obj ->> 'chatbot_id', ''),
            NULLIF(k.metadata_obj -> 'cavadalabs' ->> 'chatbot_id', ''),
            NULLIF(k.metadata_obj -> 'spend_logs_metadata' ->> 'cavadalabs_chatbot_id', ''),
            NULLIF(k.metadata_obj -> 'spend_logs_metadata' ->> 'chatbot_id', '')
        ) AS key_chatbot_id,
        NULLIF(k."team_id", '') AS key_team_id,
        NULLIF(k."organization_id", '') AS key_organization_id
    FROM normalized_keys k
),
candidates AS (
    SELECT
        s."request_id",
        COALESCE(
            k.key_company_id,
            key_project."company_id",
            key_compat_project."company_id"
        ) AS company_id,
        COALESCE(
            k.key_project_id,
            key_compat_project."project_id"
        ) AS project_id,
        COALESCE(
            key_project."company_id",
            key_compat_project."company_id"
        ) AS project_company_id,
        key_compat_company."company_id" AS key_organization_company_id,
        k.key_chatbot_id AS chatbot_id,
        COALESCE(
            NULLIF(s.metadata_obj ->> 'cavadalabs_web_token_id', ''),
            NULLIF(s.metadata_obj -> 'cavadalabs' ->> 'web_token_id', ''),
            NULLIF(s.metadata_obj -> 'spend_logs_metadata' ->> 'cavadalabs_web_token_id', ''),
            NULLIF(s.metadata_obj -> 'spend_logs_metadata' ->> 'web_token_id', '')
        ) AS web_token_id,
        COALESCE(
            NULLIF(s."session_id", ''),
            NULLIF(s.metadata_obj ->> 'cavadalabs_session_id', ''),
            NULLIF(s.metadata_obj -> 'cavadalabs' ->> 'session_id', ''),
            NULLIF(s.metadata_obj -> 'spend_logs_metadata' ->> 'cavadalabs_session_id', ''),
            NULLIF(s.metadata_obj -> 'spend_logs_metadata' ->> 'session_id', '')
        ) AS session_id,
        COALESCE(
            NULLIF(s.metadata_obj ->> 'cavadalabs_provider', ''),
            NULLIF(s.metadata_obj -> 'cavadalabs' ->> 'provider', ''),
            NULLIF(s.metadata_obj -> 'spend_logs_metadata' ->> 'cavadalabs_provider', ''),
            NULLIF(s.metadata_obj -> 'spend_logs_metadata' ->> 'provider', ''),
            NULLIF(s."custom_llm_provider", ''),
            'unknown'
        ) AS provider,
        COALESCE(
            NULLIF(s.metadata_obj ->> 'cavadalabs_model_alias', ''),
            NULLIF(s.metadata_obj -> 'cavadalabs' ->> 'model_alias', ''),
            NULLIF(s.metadata_obj -> 'spend_logs_metadata' ->> 'cavadalabs_model_alias', ''),
            NULLIF(s.metadata_obj -> 'spend_logs_metadata' ->> 'model_alias', '')
        ) AS model_alias,
        COALESCE(
            NULLIF(s.metadata_obj ->> 'cavadalabs_node_id', ''),
            NULLIF(s.metadata_obj -> 'cavadalabs' ->> 'node_id', ''),
            NULLIF(s.metadata_obj -> 'spend_logs_metadata' ->> 'cavadalabs_node_id', ''),
            NULLIF(s.metadata_obj -> 'spend_logs_metadata' ->> 'node_id', '')
        ) AS node_id,
        COALESCE(
            NULLIF(s.metadata_obj ->> 'cavadalabs_gpu_id', ''),
            NULLIF(s.metadata_obj -> 'cavadalabs' ->> 'gpu_id', ''),
            NULLIF(s.metadata_obj -> 'spend_logs_metadata' ->> 'cavadalabs_gpu_id', ''),
            NULLIF(s.metadata_obj -> 'spend_logs_metadata' ->> 'gpu_id', '')
        ) AS gpu_id,
        COALESCE(
            NULLIF(s.metadata_obj ->> 'cavadalabs_loaded_model_id', ''),
            NULLIF(s.metadata_obj -> 'cavadalabs' ->> 'loaded_model_id', ''),
            NULLIF(s.metadata_obj -> 'spend_logs_metadata' ->> 'cavadalabs_loaded_model_id', ''),
            NULLIF(s.metadata_obj -> 'spend_logs_metadata' ->> 'loaded_model_id', '')
        ) AS loaded_model_id,
        COALESCE(
            NULLIF(s.metadata_obj ->> 'cavadalabs_model_load_request_id', ''),
            NULLIF(s.metadata_obj -> 'cavadalabs' ->> 'model_load_request_id', ''),
            NULLIF(s.metadata_obj -> 'spend_logs_metadata' ->> 'cavadalabs_model_load_request_id', ''),
            NULLIF(s.metadata_obj -> 'spend_logs_metadata' ->> 'model_load_request_id', '')
        ) AS model_load_request_id,
        s.metadata_api_key_hash AS api_key_hash,
        NULLIF(s."model", '') AS model,
        NULLIF(s."model_group", '') AS model_group,
        s."call_type",
        s."request_tags",
        s."prompt_tokens",
        s."completion_tokens",
        s."total_tokens",
        s."spend",
        COALESCE(NULLIF(s."status", ''), NULLIF(s.metadata_obj ->> 'status', ''), 'success') AS status,
        COALESCE(s."startTime", CURRENT_TIMESTAMP) AS created_at,
        s.metadata_obj
    FROM extracted_spend_logs s
    INNER JOIN key_context k
        ON k."token" = s.metadata_api_key_hash
    LEFT JOIN "CavadaLabs_ProjectTable" key_project
        ON key_project."project_id" = k.key_project_id
    LEFT JOIN "CavadaLabs_ProjectTable" key_compat_project
        ON key_compat_project."litellm_team_id" = k.key_team_id
    LEFT JOIN "CavadaLabs_CompanyTable" key_compat_company
        ON key_compat_company."litellm_organization_id" = k.key_organization_id
    WHERE s.metadata_api_key_hash IS NOT NULL
)
INSERT INTO "CavadaLabs_RequestLedgerTable" (
    "ledger_id",
    "request_id",
    "company_id",
    "project_id",
    "chatbot_id",
    "web_token_id",
    "session_id",
    "api_key_hash",
    "provider",
    "model",
    "node_id",
    "gpu_id",
    "loaded_model_id",
    "model_load_request_id",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "spend",
    "status",
    "metadata",
    "created_at"
)
SELECT
    CONCAT('legacy-', md5(c."request_id")),
    c."request_id",
    c.company_id,
    c.project_id,
    c.chatbot_id,
    c.web_token_id,
    c.session_id,
    c.api_key_hash,
    c.provider,
    CASE
        WHEN c.provider = 'cavadalabs' AND c.model_alias IS NOT NULL THEN c.model_alias
        ELSE COALESCE(c.model, c.model_group, 'unknown')
    END,
    c.node_id,
    c.gpu_id,
    c.loaded_model_id,
    c.model_load_request_id,
    COALESCE(c."prompt_tokens", 0),
    COALESCE(c."completion_tokens", 0),
    COALESCE(c."total_tokens", 0),
    COALESCE(c."spend", 0.0),
    c.status,
    jsonb_strip_nulls(
        jsonb_build_object(
            'model_group', c.model_group,
            'call_type', c."call_type",
            'request_tags', c."request_tags",
            'cavadalabs',
                jsonb_strip_nulls(
                    jsonb_build_object(
                        'rag', c.metadata_obj -> 'spend_logs_metadata' -> 'rag',
                        'policy_id', COALESCE(c.metadata_obj -> 'spend_logs_metadata' -> 'policy_id', c.metadata_obj -> 'cavadalabs' -> 'policy_id'),
                        'guardrails', COALESCE(c.metadata_obj -> 'spend_logs_metadata' -> 'guardrails', c.metadata_obj -> 'cavadalabs' -> 'guardrails')
                    )
                )
        )
    ),
    c.created_at
FROM candidates c
WHERE c.company_id IS NOT NULL
    AND c.project_id IS NOT NULL
    AND c.project_company_id IS NOT NULL
    AND c.company_id = c.project_company_id
    AND (
        c.key_organization_company_id IS NULL
        OR c.key_organization_company_id = c.project_company_id
    )
ON CONFLICT ("request_id") DO NOTHING;

DROP FUNCTION IF EXISTS _cavadalabs_safe_jsonb_object(jsonb);
