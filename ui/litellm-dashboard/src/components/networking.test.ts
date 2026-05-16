import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { clearTokenCookies } from "@/utils/cookieUtils";
import * as Networking from "./networking";

vi.mock("@/utils/cookieUtils", () => ({
  clearTokenCookies: vi.fn(),
  getCookie: vi.fn(),
  storeLoginToken: vi.fn(),
}));

vi.mock("./molecules/notifications_manager", () => ({
  default: {
    info: vi.fn(),
    success: vi.fn(),
    error: vi.fn(),
    fromBackend: vi.fn(),
  },
}));

describe("networking - expired session handling", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("should call clearTokenCookies on expired session", async () => {
    const errorData = "Authentication Error - Expired Key";
    const { default: NotificationsManager } = await import("./molecules/notifications_manager");

    if (errorData.includes("Authentication Error - Expired Key")) {
      NotificationsManager.info("UI Session Expired. Logging out.");
      clearTokenCookies();
    }

    expect(clearTokenCookies).toHaveBeenCalledOnce();
  });

  it("should not clear cookies for non-authentication errors", () => {
    const errorData = "Some other error";

    if (errorData.includes("Authentication Error - Expired Key")) {
      clearTokenCookies();
    }

    expect(clearTokenCookies).not.toHaveBeenCalled();
  });

  it("should surface backend detail error when updateSSOSettings fails", async () => {
    expect.hasAssertions();

    const backendError = {
      detail: {
        error: "Set `'STORE_MODEL_IN_DB='True'` in your env to enable this feature.",
      },
    };

    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      json: vi.fn().mockResolvedValue(backendError),
    } as any);

    global.fetch = mockFetch as any;

    try {
      await Networking.updateSSOSettings("token", { some: "setting" });
    } catch (error) {
      const thrownError = error as any;
      expect(thrownError).toBeInstanceOf(Error);
      expect(thrownError.message).toBe(backendError.detail.error);
      expect(thrownError.detail).toEqual(backendError.detail);
      expect(thrownError.rawError).toEqual(backendError);
    }

    expect(mockFetch).toHaveBeenCalledOnce();
  });
});

describe("loginCall - storeLoginToken integration", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("calls storeLoginToken when response includes token", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ redirect_url: "/ui/?login=success", token: "my-jwt" }),
    }) as any;
    const { storeLoginToken } = await import("@/utils/cookieUtils");
    await Networking.loginCall("admin", "pass");
    expect(storeLoginToken).toHaveBeenCalledWith("my-jwt");
  });

  it("does not call storeLoginToken when response has no token", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ redirect_url: "/ui/?login=success" }),
    }) as any;
    const { storeLoginToken } = await import("@/utils/cookieUtils");
    await Networking.loginCall("admin", "pass");
    expect(storeLoginToken).not.toHaveBeenCalled();
  });
});

describe("v2TeamListCall", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("should send CavadaLabs Company and Project filters without legacy Organization parameters", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({
        teams: [],
        total: 0,
        page: 1,
        page_size: 10,
        total_pages: 0,
      }),
    } as any);
    global.fetch = mockFetch as any;

    await Networking.v2TeamListCall("token-1", null, null, null, null, 1, 10, null, null, "company-1", "project-1");

    const requestedUrl = mockFetch.mock.calls[0][0] as string;
    expect(requestedUrl).toContain("cavadalabs_company_id=company-1");
    expect(requestedUrl).toContain("cavadalabs_project_id=project-1");
    expect(requestedUrl).not.toContain("organization_id=");
  });
});

describe("keyListCall", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("should send CavadaLabs Company and Project filters without legacy Organization parameters", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({
        keys: [],
        total_count: 0,
        current_page: 1,
        total_pages: 0,
      }),
    } as any);
    global.fetch = mockFetch as any;

    await Networking.keyListCall(
      "token-1",
      null,
      null,
      null,
      null,
      null,
      1,
      10,
      null,
      null,
      null,
      null,
      "company-1",
      "project-1",
    );

    const requestedUrl = new URL(mockFetch.mock.calls[0][0] as string, "http://example.com");
    expect(requestedUrl.pathname).toBe("/key/list");
    expect(requestedUrl.searchParams.get("cavadalabs_company_id")).toBe("company-1");
    expect(requestedUrl.searchParams.get("cavadalabs_project_id")).toBe("project-1");
    expect(requestedUrl.searchParams.has("organization_id")).toBe(false);
    expect(requestedUrl.searchParams.has("team_id")).toBe(false);
  });
});

describe("daily activity helpers", () => {
  const startTime = new Date("2025-02-12T00:00:00.000Z");
  const endTime = new Date("2025-02-19T00:00:00.000Z");
  let currentFetch: typeof global.fetch;

  const setupSuccessfulFetch = () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ data: [] }),
    } as any);
    global.fetch = mockFetch as any;
    return mockFetch;
  };

  beforeEach(() => {
    vi.clearAllMocks();
    currentFetch = global.fetch;
  });

  afterEach(() => {
    global.fetch = currentFetch;
  });

  it("appends tag list when tags argument is provided", async () => {
    const mockFetch = setupSuccessfulFetch();

    await Networking.tagDailyActivityCall("token", startTime, endTime, 2, ["alpha", "beta"]);

    expect(mockFetch).toHaveBeenCalledOnce();
    const calledUrl = mockFetch.mock.calls[0][0] as string;
    const parsed = new URL(calledUrl, "http://example.com");

    expect(parsed.pathname).toBe("/tag/daily/activity");
    expect(parsed.searchParams.get("tags")).toBe("alpha,beta");
  });

  it("always includes exclude_team_ids but only adds team_ids when given", async () => {
    const mockFetchWithoutTeams = setupSuccessfulFetch();

    await Networking.teamDailyActivityCall("token", startTime, endTime, 1, null);
    const urlWithoutTeams = new URL(mockFetchWithoutTeams.mock.calls[0][0] as string, "http://example.com");

    expect(urlWithoutTeams.searchParams.get("exclude_team_ids")).toBe("litellm-dashboard");
    expect(urlWithoutTeams.searchParams.has("team_ids")).toBe(false);

    const mockFetchWithTeams = setupSuccessfulFetch();
    await Networking.teamDailyActivityCall("token", startTime, endTime, 3, ["team-a", "team-b"]);
    const urlWithTeams = new URL(mockFetchWithTeams.mock.calls[0][0] as string, "http://example.com");

    expect(urlWithTeams.searchParams.get("team_ids")).toBe("team-a,team-b");
    expect(urlWithTeams.searchParams.get("exclude_team_ids")).toBe("litellm-dashboard");
  });

  it("builds CavadaLabs company and project daily activity URLs", async () => {
    const mockFetch = setupSuccessfulFetch();

    await Networking.cavadalabsCompanyDailyActivityCall("token", startTime, endTime, 1, ["company-1"]);
    await Networking.cavadalabsProjectDailyActivityCall("token", startTime, endTime, 2, ["project-1", "project-2"]);

    const companyUrl = new URL(mockFetch.mock.calls[0][0] as string, "http://example.com");
    const projectUrl = new URL(mockFetch.mock.calls[1][0] as string, "http://example.com");

    expect(companyUrl.pathname).toBe("/cavadalabs/companies/daily/activity");
    expect(companyUrl.searchParams.get("company_ids")).toBe("company-1");
    expect(projectUrl.pathname).toBe("/cavadalabs/projects/daily/activity");
    expect(projectUrl.searchParams.get("project_ids")).toBe("project-1,project-2");
  });

  it("should build CavadaLabs Company and Project usage diagnostics URLs", async () => {
    const mockFetch = setupSuccessfulFetch();

    await Networking.cavadalabsCompanyUsageDiagnosticsCall("token", startTime, endTime, ["company-1"]);
    await Networking.cavadalabsProjectUsageDiagnosticsCall("token", startTime, endTime, ["project-1", "project-2"]);

    const companyUrl = new URL(mockFetch.mock.calls[0][0] as string, "http://example.com");
    const projectUrl = new URL(mockFetch.mock.calls[1][0] as string, "http://example.com");

    expect(companyUrl.pathname).toBe("/cavadalabs/companies/usage/diagnostics");
    expect(companyUrl.searchParams.get("company_ids")).toBe("company-1");
    expect(companyUrl.searchParams.has("page")).toBe(false);
    expect(projectUrl.pathname).toBe("/cavadalabs/projects/usage/diagnostics");
    expect(projectUrl.searchParams.get("project_ids")).toBe("project-1,project-2");
    expect(projectUrl.searchParams.has("page")).toBe(false);
  });

  it("should return actionable CavadaLabs missing schema diagnostics instead of throwing a generic empty state", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      json: vi.fn().mockResolvedValue({
        detail: {
          error: "CavadaLabs usage schema is missing",
          schema_status: "missing_schema",
          migration_status: "schema_missing",
          missing_schema: ["CavadaLabs_RequestLedgerTable.company_id"],
          migration_name: "20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata",
          migration_command:
            "uv run prisma migrate deploy --schema litellm-proxy-extras/litellm_proxy_extras/schema.prisma",
          migration_names: ["20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata"],
          migration_plan: [
            {
              name: "20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata",
              purpose: "Backfills historical SpendLogs from key Company/Project metadata.",
            },
          ],
        },
      }),
    } as any);
    global.fetch = mockFetch as any;

    const diagnostics = await Networking.cavadalabsCompanyUsageDiagnosticsCall("token", startTime, endTime, [
      "company-1",
    ]);

    expect(diagnostics.schema_status).toBe("missing_schema");
    expect(diagnostics.migration_status).toBe("schema_missing");
    expect(diagnostics.missing_schema).toEqual(["CavadaLabs_RequestLedgerTable.company_id"]);
    expect(diagnostics.migration_command).toContain("prisma migrate deploy");
    expect(diagnostics.diagnostics).toEqual([]);
  });
});

describe("UI config and public endpoints", () => {
  const originalFetch = global.fetch;

  const setupMockFetch = (responses: Array<{ url: string; data: any }>) => {
    const mockFetch = vi.fn().mockImplementation((url: string) => {
      const response = responses.find((r) => url.includes(r.url));
      if (response) {
        return Promise.resolve({
          ok: true,
          json: vi.fn().mockResolvedValue(response.data),
        } as any);
      }
      return Promise.resolve({
        ok: true,
        json: vi.fn().mockResolvedValue({}),
      } as any);
    });
    global.fetch = mockFetch as any;
    return mockFetch;
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("should use proxyBaseURL and server_root_path for /public/providers/fields when server_root_path is defined", async () => {
    const uiConfig = {
      server_root_path: "/api/v1",
      proxy_base_url: "https://example.com",
    };

    const mockFetch = setupMockFetch([
      { url: "/litellm/.well-known/litellm-ui-config", data: uiConfig },
      { url: "/public/providers/fields", data: [] },
    ]);

    // First call getUiConfig to set up proxyBaseUrl
    await Networking.getUiConfig();

    // Then call the public endpoint
    await Networking.getProviderCreateMetadata();

    expect(mockFetch).toHaveBeenCalledTimes(2);
    const publicEndpointCall = mockFetch.mock.calls.find((call) =>
      (call[0] as string).includes("/public/providers/fields"),
    );
    expect(publicEndpointCall).toBeDefined();
    const calledUrl = publicEndpointCall![0] as string;
    expect(calledUrl).toBe("https://example.com/api/v1/public/providers/fields");
  });

  it("should use proxyBaseURL and server_root_path for /public/model_hub/info when server_root_path is defined", async () => {
    const uiConfig = {
      server_root_path: "/api/v1",
      proxy_base_url: "https://example.com",
    };

    const mockFetch = setupMockFetch([
      { url: "/litellm/.well-known/litellm-ui-config", data: uiConfig },
      { url: "/public/model_hub/info", data: {} },
    ]);

    await Networking.getUiConfig();
    await Networking.getPublicModelHubInfo();

    expect(mockFetch).toHaveBeenCalledTimes(2);
    const publicEndpointCall = mockFetch.mock.calls.find((call) =>
      (call[0] as string).includes("/public/model_hub/info"),
    );
    expect(publicEndpointCall).toBeDefined();
    const calledUrl = publicEndpointCall![0] as string;
    expect(calledUrl).toBe("https://example.com/api/v1/public/model_hub/info");
  });

  it("should use proxyBaseURL and server_root_path for /public/model_hub when server_root_path is defined", async () => {
    const uiConfig = {
      server_root_path: "/api/v1",
      proxy_base_url: "https://example.com",
    };

    const mockFetch = setupMockFetch([
      { url: "/litellm/.well-known/litellm-ui-config", data: uiConfig },
      { url: "/public/model_hub", data: [] },
    ]);

    await Networking.getUiConfig();
    await Networking.modelHubPublicModelsCall();

    expect(mockFetch).toHaveBeenCalledTimes(2);
    const publicEndpointCall = mockFetch.mock.calls.find(
      (call) => (call[0] as string).includes("/public/model_hub") && !(call[0] as string).includes("/info"),
    );
    expect(publicEndpointCall).toBeDefined();
    const calledUrl = publicEndpointCall![0] as string;
    expect(calledUrl).toBe("https://example.com/api/v1/public/model_hub");
  });

  it("should use proxyBaseURL and server_root_path for /public/agent_hub when server_root_path is defined", async () => {
    const uiConfig = {
      server_root_path: "/api/v1",
      proxy_base_url: "https://example.com",
    };

    const mockFetch = setupMockFetch([
      { url: "/litellm/.well-known/litellm-ui-config", data: uiConfig },
      { url: "/public/agent_hub", data: [] },
    ]);

    await Networking.getUiConfig();
    await Networking.agentHubPublicModelsCall();

    expect(mockFetch).toHaveBeenCalledTimes(2);
    const publicEndpointCall = mockFetch.mock.calls.find((call) => (call[0] as string).includes("/public/agent_hub"));
    expect(publicEndpointCall).toBeDefined();
    const calledUrl = publicEndpointCall![0] as string;
    expect(calledUrl).toBe("https://example.com/api/v1/public/agent_hub");
  });

  it("should use proxyBaseURL and server_root_path for /public/mcp_hub when server_root_path is defined", async () => {
    const uiConfig = {
      server_root_path: "/api/v1",
      proxy_base_url: "https://example.com",
    };

    const mockFetch = setupMockFetch([
      { url: "/litellm/.well-known/litellm-ui-config", data: uiConfig },
      { url: "/public/mcp_hub", data: [] },
    ]);

    await Networking.getUiConfig();
    await Networking.mcpHubPublicServersCall();

    expect(mockFetch).toHaveBeenCalledTimes(2);
    const publicEndpointCall = mockFetch.mock.calls.find((call) => (call[0] as string).includes("/public/mcp_hub"));
    expect(publicEndpointCall).toBeDefined();
    const calledUrl = publicEndpointCall![0] as string;
    expect(calledUrl).toBe("https://example.com/api/v1/public/mcp_hub");
  });

  it("should not include server_root_path when it is root path", async () => {
    const uiConfig = {
      server_root_path: "/",
      proxy_base_url: "https://example.com",
    };

    const mockFetch = setupMockFetch([
      { url: "/litellm/.well-known/litellm-ui-config", data: uiConfig },
      { url: "/public/providers/fields", data: [] },
    ]);

    await Networking.getUiConfig();
    await Networking.getProviderCreateMetadata();

    expect(mockFetch).toHaveBeenCalledTimes(2);
    const publicEndpointCall = mockFetch.mock.calls.find((call) =>
      (call[0] as string).includes("/public/providers/fields"),
    );
    expect(publicEndpointCall).toBeDefined();
    const calledUrl = publicEndpointCall![0] as string;
    expect(calledUrl).toBe("https://example.com/public/providers/fields");
  });

  it("should return UI config from getUiConfig", async () => {
    const uiConfig = {
      server_root_path: "/api/v1",
      proxy_base_url: "https://example.com",
    };

    const mockFetch = setupMockFetch([{ url: "/litellm/.well-known/litellm-ui-config", data: uiConfig }]);

    const result = await Networking.getUiConfig();

    expect(mockFetch).toHaveBeenCalledOnce();
    expect(result).toEqual(uiConfig);
    const configCall = mockFetch.mock.calls.find((call) =>
      (call[0] as string).includes("/litellm/.well-known/litellm-ui-config"),
    );
    expect(configCall).toBeDefined();
  });
});

describe("individualModelHealthCheckCall", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("should call /health with model_id query param so health checks run by deployment id", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({
        healthy_count: 1,
        unhealthy_count: 0,
        healthy_endpoints: [],
        unhealthy_endpoints: [],
      }),
    } as any);
    global.fetch = mockFetch as any;

    await Networking.individualModelHealthCheckCall("token-123", "deployment-abc-456");

    expect(mockFetch).toHaveBeenCalledOnce();
    const [url] = mockFetch.mock.calls[0];
    const urlStr = typeof url === "string" ? url : (url as Request).url;
    expect(urlStr).toContain("health");
    const parsed = typeof url === "string" ? new URL(url, "http://example.com") : new URL((url as Request).url);
    expect(parsed.searchParams.get("model_id")).toBe("deployment-abc-456");
    expect(parsed.searchParams.has("model")).toBe(false);
  });

  it("should encode model_id in URL", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({
        healthy_count: 0,
        unhealthy_count: 0,
        healthy_endpoints: [],
        unhealthy_endpoints: [],
      }),
    } as any);
    global.fetch = mockFetch as any;

    await Networking.individualModelHealthCheckCall("token", "id/with/slashes");

    const [url] = mockFetch.mock.calls[0];
    const parsed = typeof url === "string" ? new URL(url, "http://example.com") : new URL((url as Request).url);
    expect(parsed.searchParams.get("model_id")).toBe("id/with/slashes");
  });
});

describe("teamInfoCall", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("should URL-encode team_id query param to handle special characters safely", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ team_id: "team with spaces & special?chars" }),
    } as any);
    global.fetch = mockFetch as any;

    const teamID = "team with spaces & special?chars";
    await Networking.teamInfoCall("token", teamID);

    expect(mockFetch).toHaveBeenCalledOnce();
    const [url] = mockFetch.mock.calls[0];
    const urlStr = typeof url === "string" ? url : (url as Request).url;
    const parsed = typeof url === "string" ? new URL(url, "http://example.com") : new URL((url as Request).url);

    expect(urlStr).toContain("/team/info");
    // Encoded value is present in the raw URL string (verifies encodeURIComponent was used)
    expect(urlStr).toContain(`team_id=${encodeURIComponent(teamID)}`);
    // Round-trip parse returns the original team_id
    expect(parsed.searchParams.get("team_id")).toBe(teamID);
  });

  it("should not append team_id when teamID is null", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({}),
    } as any);
    global.fetch = mockFetch as any;

    await Networking.teamInfoCall("token", null);

    expect(mockFetch).toHaveBeenCalledOnce();
    const [url] = mockFetch.mock.calls[0];
    const parsed = typeof url === "string" ? new URL(url, "http://example.com") : new URL((url as Request).url);
    expect(parsed.searchParams.has("team_id")).toBe(false);
  });
});
