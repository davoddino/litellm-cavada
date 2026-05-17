import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import {
  cavadaLabsErrorDetailFromUnknown,
  cavadalabsMissingSchemaDiagnosticsFromDetail,
  cavadalabsMissingSchemaDetailLines,
  cavadalabsRequest,
  getCavadaLabsDailyActivity,
  getCavadaLabsUsageDiagnostics,
  isCavadaLabsMissingSchemaDetail,
} from "./api";

vi.mock("@/components/networking", () => ({
  getProxyBaseUrl: () => "http://proxy.test",
  getGlobalLitellmHeaderName: () => "Authorization",
  deriveErrorMessage: (errorData: any) => errorData?.detail?.error ?? errorData?.detail ?? "error",
  handleError: vi.fn(),
}));

const jsonResponse = (payload: any, ok = true) =>
  ({
    ok,
    headers: {
      get: () => "application/json",
    },
    json: vi.fn().mockResolvedValue(payload),
    text: vi.fn(),
  }) as any;

describe("cavadalabs api client", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("should include auth headers and query parameters", async () => {
    const mockFetch = vi.fn().mockResolvedValue(jsonResponse({ companies: [], count: 0 }));
    global.fetch = mockFetch as any;

    await cavadalabsRequest("token-1", "/cavadalabs/companies", {
      query: { status: "active", ignored: "" },
    });

    expect(mockFetch).toHaveBeenCalledOnce();
    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toBe("http://proxy.test/cavadalabs/companies?status=active");
    expect(options.headers.Authorization).toBe("Bearer token-1");
  });

  it("should raise backend errors", async () => {
    const mockFetch = vi.fn().mockResolvedValue(jsonResponse({ detail: { error: "Forbidden" } }, false));
    global.fetch = mockFetch as any;

    await expect(cavadalabsRequest("token-1", "/cavadalabs/companies")).rejects.toThrow("Forbidden");
  });

  it("should preserve typed missing schema details from backend errors", async () => {
    const missingSchemaPayload = {
      detail: {
        error: "CavadaLabs access control schema is missing required table delegate.",
        schema_status: "missing_schema",
        migration_status: "schema_missing",
        missing_schema: ["cavadalabs_companymembertable"],
        migration_command: "uv run prisma migrate deploy",
      },
    };
    const mockFetch = vi.fn().mockResolvedValue(jsonResponse(missingSchemaPayload, false));
    global.fetch = mockFetch as any;

    let captured: unknown;
    try {
      await cavadalabsRequest("token-1", "/cavadalabs/billing-reports");
    } catch (err) {
      captured = err;
    }

    const detail = cavadaLabsErrorDetailFromUnknown(captured);
    expect(isCavadaLabsMissingSchemaDetail(detail)).toBe(true);
    expect(detail?.missing_schema).toEqual(["cavadalabs_companymembertable"]);
    expect(cavadalabsMissingSchemaDetailLines(detail!)).toContain("Missing schema: cavadalabs_companymembertable");
    expect(cavadalabsMissingSchemaDiagnosticsFromDetail(detail!)).toEqual(
      expect.objectContaining({
        schema_status: "missing_schema",
        migration_status: "schema_missing",
        migration_command: "uv run prisma migrate deploy",
      }),
    );
  });

  it("should call Project daily activity with canonical Project paging filters", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      jsonResponse({
        results: [],
        metadata: {
          total_spend: 0,
          total_prompt_tokens: 0,
          total_completion_tokens: 0,
          total_tokens: 0,
          total_api_requests: 0,
          total_successful_requests: 0,
          total_failed_requests: 0,
          page: 2,
          total_pages: 3,
          has_more: true,
        },
      }),
    );
    global.fetch = mockFetch as any;

    await getCavadaLabsDailyActivity("token-1", {
      entityType: "project",
      entityIds: ["project-1"],
      startDate: "2026-05-01",
      endDate: "2026-05-31",
      page: 2,
      pageSize: 30,
      provider: "cavadalabs",
    });

    expect(mockFetch).toHaveBeenCalledOnce();
    const [url] = mockFetch.mock.calls[0];
    const requestUrl = new URL(String(url));
    expect(requestUrl.pathname).toBe("/cavadalabs/projects/daily/activity");
    expect(requestUrl.searchParams.get("project_ids")).toBe("project-1");
    expect(requestUrl.searchParams.get("company_ids")).toBeNull();
    expect(requestUrl.searchParams.get("page")).toBe("2");
    expect(requestUrl.searchParams.get("page_size")).toBe("30");
    expect(requestUrl.searchParams.get("provider")).toBe("cavadalabs");
  });

  it("should call Project usage diagnostics with the same filters as daily usage", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      jsonResponse({
        diagnostics: [],
        migration_name: "20260515161000_backfill_cavadalabs_request_ledger_from_metadata_key_hash",
        migration_command: "uv run prisma migrate deploy",
      }),
    );
    global.fetch = mockFetch as any;

    await getCavadaLabsUsageDiagnostics("token-1", {
      entityType: "project",
      entityIds: ["project-1"],
      startDate: "2026-05-01",
      endDate: "2026-05-31",
      provider: "cavadalabs",
      model: "cavadalabs/qwen3-32b",
      status: "error",
      apiKey: "hashed-key",
      minSpend: 10,
      maxSpend: 25,
    });

    expect(mockFetch).toHaveBeenCalledOnce();
    const [url] = mockFetch.mock.calls[0];
    const requestUrl = new URL(String(url));
    expect(requestUrl.pathname).toBe("/cavadalabs/projects/usage/diagnostics");
    expect(requestUrl.searchParams.get("project_ids")).toBe("project-1");
    expect(requestUrl.searchParams.get("company_ids")).toBeNull();
    expect(requestUrl.searchParams.get("provider")).toBe("cavadalabs");
    expect(requestUrl.searchParams.get("model")).toBe("cavadalabs/qwen3-32b");
    expect(requestUrl.searchParams.get("status")).toBe("error");
    expect(requestUrl.searchParams.get("api_key")).toBe("hashed-key");
    expect(requestUrl.searchParams.get("min_spend")).toBe("10");
    expect(requestUrl.searchParams.get("max_spend")).toBe("25");
  });
});
