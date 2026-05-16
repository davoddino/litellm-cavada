import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import {
  cavadaLabsErrorDetailFromUnknown,
  cavadalabsMissingSchemaDiagnosticsFromDetail,
  cavadalabsMissingSchemaDetailLines,
  cavadalabsRequest,
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
});
