import { deriveErrorMessage, getGlobalLitellmHeaderName, getProxyBaseUrl, handleError } from "@/components/networking";
import type {
  CavadaLabsDailyActivityResponse,
  CavadaLabsRecord,
  CavadaLabsUsageDiagnosticsEntityType,
  CavadaLabsUsageDiagnosticsResponse,
  CavadaLabsUsageRepairResponse,
} from "./types";
export {
  cavadaLabsErrorDetailFromPayload,
  cavadaLabsErrorDetailFromUnknown,
  cavadalabsMissingSchemaDetailLines,
  cavadalabsMissingSchemaDiagnosticsFromDetail,
  isCavadaLabsMissingSchemaDetail,
} from "./usageErrorHelpers";
export type { CavadaLabsStructuredErrorDetail } from "./usageErrorHelpers";

interface CavadaLabsApiOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  query?: CavadaLabsRecord;
  body?: CavadaLabsRecord;
}

export class CavadaLabsApiError extends Error {
  status: number;
  payload: any;
  detail: any;

  constructor(message: string, status: number, payload: any) {
    super(message);
    this.name = "CavadaLabsApiError";
    this.status = status;
    this.payload = payload;
    this.detail = payload?.detail ?? payload;
  }
}

const buildUrl = (path: string, query?: CavadaLabsRecord): string => {
  const baseUrl = getProxyBaseUrl();
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const url = baseUrl ? `${baseUrl}${normalizedPath}` : normalizedPath;
  const params = new URLSearchParams();

  Object.entries(query ?? {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    if (Array.isArray(value)) {
      if (value.length > 0) params.set(key, value.join(","));
      return;
    }
    params.set(key, String(value));
  });

  const queryString = params.toString();
  if (!queryString) return url;
  return `${url}${url.includes("?") ? "&" : "?"}${queryString}`;
};

const parseResponse = async (response: Response): Promise<any> => {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  const text = await response.text();
  return text ? { detail: text } : {};
};

const structuredErrorMessage = (payload: any): string | undefined => {
  const detail = payload?.detail;
  if (detail && typeof detail === "object") {
    if (typeof detail.error === "string" && detail.error.trim()) return detail.error;
    if (typeof detail.message === "string" && detail.message.trim()) return detail.message;
  }
  if (typeof detail === "string" && detail.trim()) return detail;
  if (typeof payload?.error === "string" && payload.error.trim()) return payload.error;
  if (typeof payload?.message === "string" && payload.message.trim()) return payload.message;
  return undefined;
};

export const cavadalabsRequest = async <T = any>(
  accessToken: string | null,
  path: string,
  options: CavadaLabsApiOptions = {},
): Promise<T> => {
  if (!accessToken) {
    throw new Error("Missing access token");
  }

  const response = await fetch(buildUrl(path, options.query), {
    method: options.method ?? "GET",
    headers: {
      [getGlobalLitellmHeaderName()]: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  const payload = await parseResponse(response);
  if (!response.ok) {
    const errorMessage = structuredErrorMessage(payload) ?? deriveErrorMessage(payload);
    await handleError(errorMessage);
    throw new CavadaLabsApiError(errorMessage, response.status, payload);
  }
  return payload as T;
};

export const listCavadaLabsResource = async <T = any>(
  accessToken: string | null,
  path: string,
  query?: CavadaLabsRecord,
): Promise<T> => cavadalabsRequest<T>(accessToken, path, { query });

export const createCavadaLabsResource = async <T = any>(
  accessToken: string | null,
  path: string,
  body: CavadaLabsRecord,
): Promise<T> => cavadalabsRequest<T>(accessToken, path, { method: "POST", body });

export const patchCavadaLabsResource = async <T = any>(
  accessToken: string | null,
  path: string,
  body: CavadaLabsRecord,
): Promise<T> => cavadalabsRequest<T>(accessToken, path, { method: "PATCH", body });

export const postCavadaLabsAction = async <T = any>(
  accessToken: string | null,
  path: string,
  body: CavadaLabsRecord = {},
): Promise<T> => cavadalabsRequest<T>(accessToken, path, { method: "POST", body });

export const deleteCavadaLabsResource = async <T = any>(accessToken: string | null, path: string): Promise<T> =>
  cavadalabsRequest<T>(accessToken, path, { method: "DELETE" });

export const getCavadaLabsUsageDiagnostics = async (
  accessToken: string | null,
  {
    entityType,
    entityIds,
    startDate,
    endDate,
    timezone,
    model,
    provider,
    status,
    apiKey,
    minSpend,
    maxSpend,
  }: {
    entityType: CavadaLabsUsageDiagnosticsEntityType;
    entityIds: string[];
    startDate: string;
    endDate: string;
    timezone?: number;
    model?: string;
    provider?: string;
    status?: string;
    apiKey?: string;
    minSpend?: number;
    maxSpend?: number;
  },
): Promise<CavadaLabsUsageDiagnosticsResponse> => {
  const isCompany = entityType === "company";
  return listCavadaLabsResource<CavadaLabsUsageDiagnosticsResponse>(
    accessToken,
    isCompany ? "/cavadalabs/companies/usage/diagnostics" : "/cavadalabs/projects/usage/diagnostics",
    {
      [isCompany ? "company_ids" : "project_ids"]: entityIds,
      start_date: startDate,
      end_date: endDate,
      timezone,
      model,
      provider,
      status,
      api_key: apiKey,
      min_spend: minSpend,
      max_spend: maxSpend,
    },
  );
};

export const getCavadaLabsDailyActivity = async (
  accessToken: string | null,
  {
    entityType,
    entityIds,
    startDate,
    endDate,
    timezone,
    page = 1,
    pageSize = 100,
    model,
    provider,
    status,
    apiKey,
    minSpend,
    maxSpend,
  }: {
    entityType: CavadaLabsUsageDiagnosticsEntityType;
    entityIds: string[];
    startDate: string;
    endDate: string;
    timezone?: number;
    page?: number;
    pageSize?: number;
    model?: string;
    provider?: string;
    status?: string;
    apiKey?: string;
    minSpend?: number;
    maxSpend?: number;
  },
): Promise<CavadaLabsDailyActivityResponse> => {
  const isCompany = entityType === "company";
  return listCavadaLabsResource<CavadaLabsDailyActivityResponse>(
    accessToken,
    isCompany ? "/cavadalabs/companies/daily/activity" : "/cavadalabs/projects/daily/activity",
    {
      [isCompany ? "company_ids" : "project_ids"]: entityIds,
      start_date: startDate,
      end_date: endDate,
      timezone,
      page,
      page_size: pageSize,
      model,
      provider,
      status,
      api_key: apiKey,
      min_spend: minSpend,
      max_spend: maxSpend,
    },
  );
};

export const repairCavadaLabsUsage = async (
  accessToken: string | null,
  {
    entityType,
    entityIds,
    startDate,
    endDate,
    timezone,
    model,
    provider,
    status,
    apiKey,
    minSpend,
    maxSpend,
    dryRun,
    batchLimit,
  }: {
    entityType: CavadaLabsUsageDiagnosticsEntityType;
    entityIds: string[];
    startDate: string;
    endDate: string;
    timezone?: number;
    model?: string;
    provider?: string;
    status?: string;
    apiKey?: string;
    minSpend?: number;
    maxSpend?: number;
    dryRun?: boolean;
    batchLimit?: number;
  },
): Promise<CavadaLabsUsageRepairResponse> => {
  const isCompany = entityType === "company";
  return postCavadaLabsAction<CavadaLabsUsageRepairResponse>(
    accessToken,
    isCompany ? "/cavadalabs/companies/usage/repair" : "/cavadalabs/projects/usage/repair",
    {
      [isCompany ? "company_ids" : "project_ids"]: entityIds,
      start_date: startDate,
      end_date: endDate,
      timezone,
      model,
      provider,
      status,
      api_key: apiKey,
      min_spend: minSpend,
      max_spend: maxSpend,
      dry_run: dryRun,
      batch_limit: batchLimit,
    },
  );
};
