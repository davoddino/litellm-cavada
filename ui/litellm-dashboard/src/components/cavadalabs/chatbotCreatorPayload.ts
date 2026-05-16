import type { CavadaLabsRecord, CavadaLabsRuntimeContext, CavadaLabsSelectOption } from "./types";

export const CHATBOT_RUNTIME_ROUTE = "/cavadalabs/chatbots/messages";
export const DEFAULT_CHATBOT_LANGUAGE = "it";
export const DEFAULT_WEB_TOKEN_TTL_SECONDS = 3600;

export interface CavadaLabsChatbotCreatorValues {
  company_id?: string;
  project_id?: string;
  name?: string;
  status?: "draft" | "published" | "disabled";
  default_language?: string;
  prompt_version?: number;
  model_policy_id?: string;
  system_prompt?: string;
  assigned_rag_collections?: string[];
  allowed_domains?: string[];
  fallback_message?: string;
  assigned_guardrail_policy?: string;
  server_key_mode?: "create" | "existing" | "none";
  existing_server_key?: string;
  server_key_alias?: string;
  server_key_duration?: string;
  issue_web_token?: boolean;
  web_token_name?: string;
  allowed_origins?: string[];
  expires_in_seconds?: number;
}

export const initialChatbotCreatorValues = (
  context: Pick<CavadaLabsRuntimeContext, "companies" | "projects">,
): CavadaLabsChatbotCreatorValues => {
  const companyId = context.companies[0]?.company_id ? String(context.companies[0].company_id) : undefined;
  const projectId = projectsForCompany(context, companyId)[0]?.project_id
    ? String(projectsForCompany(context, companyId)[0].project_id)
    : undefined;

  return {
    company_id: companyId,
    project_id: projectId,
    status: "draft",
    default_language: DEFAULT_CHATBOT_LANGUAGE,
    prompt_version: 1,
    server_key_mode: "create",
    issue_web_token: false,
    expires_in_seconds: DEFAULT_WEB_TOKEN_TTL_SECONDS,
  };
};

export const extractCreatedChatbotId = (response: CavadaLabsRecord): string => {
  const chatbotId = response.chatbot_id ?? response.chatbot?.chatbot_id;
  if (!chatbotId) {
    throw new Error("Chatbot creation response did not include chatbot_id");
  }
  return String(chatbotId);
};

const cleanStringArray = (value: unknown): string[] => {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item).trim()).filter(Boolean);
};

const putIfPresent = (payload: CavadaLabsRecord, key: string, value: unknown): void => {
  if (value === undefined || value === null || value === "") return;
  if (Array.isArray(value) && value.length === 0) return;
  payload[key] = value;
};

export const projectsForCompany = (
  context: Pick<CavadaLabsRuntimeContext, "projects">,
  companyId?: string,
): CavadaLabsRecord[] => {
  if (!companyId) return context.projects;
  return context.projects.filter((project) => project.company_id === companyId);
};

export const modelPolicyOptions = (policies: CavadaLabsRecord[]): CavadaLabsSelectOption[] =>
  policies
    .filter((policy) => policy.policy_id)
    .map((policy) => ({
      value: String(policy.policy_id),
      label: policy.model_alias ? `${policy.model_alias} (${policy.policy_id})` : String(policy.policy_id),
    }));

export const serverKeyOptions = (keys: CavadaLabsRecord[]): CavadaLabsSelectOption[] =>
  keys
    .filter((key) => key.token || key.key)
    .map((key) => {
      const value = String(key.token ?? key.key);
      const labelBase = key.key_alias || key.key_name || "Server key";
      return {
        value,
        label: `${labelBase} (${value})`,
      };
    });

export const buildChatbotCreatePayload = (values: CavadaLabsChatbotCreatorValues): CavadaLabsRecord => {
  const payload: CavadaLabsRecord = {
    company_id: values.company_id,
    project_id: values.project_id,
    name: values.name?.trim(),
    status: values.status ?? "draft",
    default_language: values.default_language?.trim() || DEFAULT_CHATBOT_LANGUAGE,
    prompt_version: Number(values.prompt_version ?? 1),
    system_prompt: values.system_prompt ?? "",
    assigned_rag_collections: cleanStringArray(values.assigned_rag_collections),
    allowed_domains: cleanStringArray(values.allowed_domains),
  };

  putIfPresent(payload, "model_policy_id", values.model_policy_id?.trim());
  putIfPresent(payload, "fallback_message", values.fallback_message?.trim());
  putIfPresent(payload, "assigned_guardrail_policy", values.assigned_guardrail_policy?.trim());
  return payload;
};

const metadataToRecord = (value: unknown): CavadaLabsRecord => {
  if (value && typeof value === "object" && !Array.isArray(value)) return { ...(value as CavadaLabsRecord) };
  if (typeof value === "string" && value.trim()) {
    try {
      const parsed = JSON.parse(value);
      return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
    } catch {
      return {};
    }
  }
  return {};
};

export const buildChatbotKeyMetadata = (
  values: CavadaLabsChatbotCreatorValues,
  chatbotId: string,
  existingMetadata?: unknown,
): CavadaLabsRecord => {
  const companyId = values.company_id;
  const projectId = values.project_id;
  const metadata = metadataToRecord(existingMetadata);
  const cavadalabs = metadataToRecord(metadata.cavadalabs);
  const spendLogsMetadata = metadataToRecord(metadata.spend_logs_metadata);

  return {
    ...metadata,
    cavadalabs_company_id: companyId,
    cavadalabs_project_id: projectId,
    cavadalabs_chatbot_id: chatbotId,
    cavadalabs: {
      ...cavadalabs,
      company_id: companyId,
      project_id: projectId,
      chatbot_id: chatbotId,
    },
    spend_logs_metadata: {
      ...spendLogsMetadata,
      cavadalabs_company_id: companyId,
      cavadalabs_project_id: projectId,
      cavadalabs_chatbot_id: chatbotId,
    },
  };
};

export const buildChatbotWebTokenMetadata = (
  values: CavadaLabsChatbotCreatorValues,
  chatbotId: string,
): CavadaLabsRecord => ({
  cavadalabs_company_id: values.company_id,
  cavadalabs_project_id: values.project_id,
  cavadalabs_chatbot_id: chatbotId,
  cavadalabs: {
    company_id: values.company_id,
    project_id: values.project_id,
    chatbot_id: chatbotId,
  },
  spend_logs_metadata: {
    cavadalabs_company_id: values.company_id,
    cavadalabs_project_id: values.project_id,
    cavadalabs_chatbot_id: chatbotId,
  },
});

export const buildChatbotServerKeyCreatePayload = (
  values: CavadaLabsChatbotCreatorValues,
  chatbotId: string,
  selectedPolicy?: CavadaLabsRecord,
): CavadaLabsRecord | null => {
  if ((values.server_key_mode ?? "create") !== "create") return null;

  const payload: CavadaLabsRecord = {
    key_alias: values.server_key_alias?.trim() || `${values.name?.trim() || "Chatbot"} server key`,
    models: selectedPolicy?.model_alias ? [String(selectedPolicy.model_alias)] : [],
    cavadalabs_company_id: values.company_id,
    cavadalabs_project_id: values.project_id,
    metadata: buildChatbotKeyMetadata(values, chatbotId),
  };

  putIfPresent(payload, "duration", values.server_key_duration?.trim());
  return payload;
};

export const buildChatbotServerKeyUpdatePayload = (
  values: CavadaLabsChatbotCreatorValues,
  chatbotId: string,
  selectedKey: CavadaLabsRecord | undefined,
): CavadaLabsRecord | null => {
  if (values.server_key_mode !== "existing") return null;
  const key = values.existing_server_key?.trim();
  if (!key) {
    throw new Error("Select an existing server API key before linking it to the chatbot.");
  }
  if (!selectedKey) {
    throw new Error("Selected server API key is not available in the current Company/Project scope.");
  }

  return {
    key,
    cavadalabs_company_id: values.company_id,
    cavadalabs_project_id: values.project_id,
    metadata: buildChatbotKeyMetadata(values, chatbotId, selectedKey.metadata),
  };
};

export const buildChatbotWebTokenPayload = (
  values: CavadaLabsChatbotCreatorValues,
  chatbotId: string,
): CavadaLabsRecord | null => {
  if (!values.issue_web_token) return null;

  const payload: CavadaLabsRecord = {
    company_id: values.company_id,
    project_id: values.project_id,
    chatbot_id: chatbotId,
    allowed_domains: cleanStringArray(values.allowed_domains),
    allowed_origins: cleanStringArray(values.allowed_origins),
    route_allowlist: [CHATBOT_RUNTIME_ROUTE],
    expires_in_seconds: Number(values.expires_in_seconds ?? DEFAULT_WEB_TOKEN_TTL_SECONDS),
    metadata: buildChatbotWebTokenMetadata(values, chatbotId),
  };

  putIfPresent(payload, "name", values.web_token_name?.trim());
  return payload;
};
