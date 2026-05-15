import { deriveErrorMessage, getGlobalLitellmHeaderName, getProxyBaseUrl, handleError } from "@/components/networking";
import type { CavadaLabsRecord } from "./types";

interface CavadaLabsApiOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  query?: CavadaLabsRecord;
  body?: CavadaLabsRecord;
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
    const errorMessage = deriveErrorMessage(payload);
    await handleError(errorMessage);
    throw new Error(errorMessage);
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
