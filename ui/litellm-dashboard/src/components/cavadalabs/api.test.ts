import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cavadalabsRequest } from "./api";

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
});
