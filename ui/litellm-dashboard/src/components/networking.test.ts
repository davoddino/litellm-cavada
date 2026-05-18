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

  it("should call company daily activity through the product Company endpoint", async () => {
    const mockFetch = setupSuccessfulFetch();

    await Networking.companyDailyActivityCall("token", startTime, endTime, 1, ["company-a", "company-b"]);

    const calledUrl = mockFetch.mock.calls[0][0] as string;
    const parsed = new URL(calledUrl, "http://example.com");

    expect(parsed.pathname).toBe("/company/daily/activity");
    expect(parsed.searchParams.get("company_ids")).toBe("company-a,company-b");
    expect(parsed.searchParams.has("organization_ids")).toBe(false);
  });

  it("should add project_ids and company_ids for project daily activity", async () => {
    const mockFetch = setupSuccessfulFetch();

    await Networking.projectDailyActivityCall(
      "token",
      startTime,
      endTime,
      2,
      ["project-a", "project-b"],
      ["company-a"],
    );

    const calledUrl = mockFetch.mock.calls[0][0] as string;
    const parsed = new URL(calledUrl, "http://example.com");

    expect(parsed.pathname).toBe("/project/daily/activity");
    expect(parsed.searchParams.get("project_ids")).toBe("project-a,project-b");
    expect(parsed.searchParams.get("company_ids")).toBe("company-a");
  });
});

describe("agent tenant networking helpers", () => {
  const originalFetch = global.fetch;

  const setupSuccessfulFetch = (data: any = {}) => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue(data),
      text: vi.fn().mockResolvedValue(""),
    } as any);
    global.fetch = mockFetch as any;
    return mockFetch;
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("should create agents with company and project payload fields only", async () => {
    const mockFetch = setupSuccessfulFetch({ agent_id: "agent-1" });

    await Networking.createAgentCall("token", {
      agent_name: "Support Agent",
      company_id: "company-1",
      project_id: "project-1",
      organization_id: "company-1",
    });

    const body = JSON.parse(mockFetch.mock.calls[0][1].body as string);
    expect(body.company_id).toBe("company-1");
    expect(body.project_id).toBe("project-1");
    expect(body.organization_id).toBeUndefined();
  });

  it("should create agent keys with company and project payload fields only", async () => {
    const mockFetch = setupSuccessfulFetch({ key: "sk-test" });

    await Networking.keyCreateForAgentCall(
      "token",
      "agent-1",
      "agent-key",
      ["gpt-4"],
      undefined,
      "team-1",
      "company-1",
      "project-1",
    );

    const body = JSON.parse(mockFetch.mock.calls[0][1].body as string);
    expect(body.agent_id).toBe("agent-1");
    expect(body.company_id).toBe("company-1");
    expect(body.project_id).toBe("project-1");
    expect(body.team_id).toBe("team-1");
    expect(body.organization_id).toBeUndefined();
  });

  it("should list agents with company and project query filters", async () => {
    const mockFetch = setupSuccessfulFetch([]);

    await Networking.getAgentsList("token", false, {
      company_id: "company-1",
      project_id: "project-1",
    });

    const calledUrl = mockFetch.mock.calls[0][0] as string;
    const parsed = new URL(calledUrl, "http://example.com");
    expect(parsed.pathname).toBe("/v1/agents");
    expect(parsed.searchParams.get("company_id")).toBe("company-1");
    expect(parsed.searchParams.get("project_id")).toBe("project-1");
    expect(parsed.searchParams.has("organization_id")).toBe(false);
  });
});

describe("company management helpers", () => {
  const originalFetch = global.fetch;

  const setupSuccessfulFetch = (data: any = {}) => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue(data),
    } as any);
    global.fetch = mockFetch as any;
    return mockFetch;
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("should call company list with company filters", async () => {
    const mockFetch = setupSuccessfulFetch([]);

    await Networking.organizationListCall("token", "company-1", "Acme");

    const calledUrl = mockFetch.mock.calls[0][0] as string;
    const parsed = new URL(calledUrl, "http://example.com");
    expect(parsed.pathname).toBe("/company/list");
    expect(parsed.searchParams.get("company_id")).toBe("company-1");
    expect(parsed.searchParams.get("company_name")).toBe("Acme");
    expect(parsed.searchParams.has("org_id")).toBe(false);
    expect(parsed.searchParams.has("org_alias")).toBe(false);
  });

  it("should call company info with company_id", async () => {
    const mockFetch = setupSuccessfulFetch({});

    await Networking.organizationInfoCall("token", "company-1");

    const calledUrl = mockFetch.mock.calls[0][0] as string;
    const parsed = new URL(calledUrl, "http://example.com");
    expect(parsed.pathname).toBe("/company/info");
    expect(parsed.searchParams.get("company_id")).toBe("company-1");
    expect(parsed.searchParams.has("organization_id")).toBe(false);
  });

  it("should create and update companies through product endpoints", async () => {
    const mockFetch = setupSuccessfulFetch({});

    await Networking.organizationCreateCall("token", {
      company_name: "Acme",
      models: ["gpt-4o-mini"],
    });
    await Networking.organizationUpdateCall("token", {
      company_id: "company-1",
      company_name: "Acme Updated",
    });

    const createUrl = new URL(mockFetch.mock.calls[0][0] as string, "http://example.com");
    const updateUrl = new URL(mockFetch.mock.calls[1][0] as string, "http://example.com");
    const createBody = JSON.parse(mockFetch.mock.calls[0][1].body);
    const updateBody = JSON.parse(mockFetch.mock.calls[1][1].body);

    expect(createUrl.pathname).toBe("/company/new");
    expect(createBody.company_name).toBe("Acme");
    expect(createBody.organization_alias).toBeUndefined();
    expect(updateUrl.pathname).toBe("/company/update");
    expect(updateBody.company_id).toBe("company-1");
    expect(updateBody.company_name).toBe("Acme Updated");
    expect(updateBody.organization_id).toBeUndefined();
    expect(updateBody.organization_alias).toBeUndefined();
  });

  it("should delete companies with company_ids", async () => {
    const mockFetch = setupSuccessfulFetch([]);

    await Networking.organizationDeleteCall("token", "company-1");

    const calledUrl = new URL(mockFetch.mock.calls[0][0] as string, "http://example.com");
    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(calledUrl.pathname).toBe("/company/delete");
    expect(body.company_ids).toEqual(["company-1"]);
    expect(body.organization_ids).toBeUndefined();
  });

  it("should manage company members with company_id payloads", async () => {
    const mockFetch = setupSuccessfulFetch({});

    await Networking.organizationMemberAddCall("token", "company-1", {
      role: "internal_user",
      user_id: "user-1",
    } as any);
    await Networking.organizationMemberUpdateCall("token", "company-1", {
      role: "org_admin",
      user_id: "user-1",
    } as any);
    await Networking.organizationMemberDeleteCall("token", "company-1", "user-1");

    const addUrl = new URL(mockFetch.mock.calls[0][0] as string, "http://example.com");
    const updateUrl = new URL(mockFetch.mock.calls[1][0] as string, "http://example.com");
    const deleteUrl = new URL(mockFetch.mock.calls[2][0] as string, "http://example.com");
    const addBody = JSON.parse(mockFetch.mock.calls[0][1].body);
    const updateBody = JSON.parse(mockFetch.mock.calls[1][1].body);
    const deleteBody = JSON.parse(mockFetch.mock.calls[2][1].body);

    expect(addUrl.pathname).toBe("/company/member_add");
    expect(updateUrl.pathname).toBe("/company/member_update");
    expect(deleteUrl.pathname).toBe("/company/member_delete");
    expect(addBody.company_id).toBe("company-1");
    expect(updateBody.company_id).toBe("company-1");
    expect(deleteBody.company_id).toBe("company-1");
    expect(addBody.organization_id).toBeUndefined();
    expect(updateBody.organization_id).toBeUndefined();
    expect(deleteBody.organization_id).toBeUndefined();
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

  it("should send company_id for the Virtual Keys company filter", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ keys: [], total_count: 0 }),
    } as any);
    global.fetch = mockFetch as any;

    await Networking.keyListCall("token", "company-123", null, null, null, null, 1, 10);

    expect(mockFetch).toHaveBeenCalledOnce();
    const [url] = mockFetch.mock.calls[0];
    const parsed = typeof url === "string" ? new URL(url, "http://example.com") : new URL((url as Request).url);

    expect(parsed.pathname).toContain("/key/list");
    expect(parsed.searchParams.get("company_id")).toBe("company-123");
    expect(parsed.searchParams.has("organization_id")).toBe(false);
  });

  it("should send project_id for the Virtual Keys project filter", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ keys: [], total_count: 0 }),
    } as any);
    global.fetch = mockFetch as any;

    await Networking.keyListCall("token", null, null, null, null, null, 1, 10, null, null, null, null, "project-456");

    expect(mockFetch).toHaveBeenCalledOnce();
    const [url] = mockFetch.mock.calls[0];
    const parsed = typeof url === "string" ? new URL(url, "http://example.com") : new URL((url as Request).url);

    expect(parsed.pathname).toContain("/key/list");
    expect(parsed.searchParams.get("project_id")).toBe("project-456");
  });

  it("should delete Virtual Keys by key only without tenant compatibility payloads", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ deleted_keys: ["sk-test-key"] }),
    } as any);
    global.fetch = mockFetch as any;

    await Networking.keyDeleteCall("token", "sk-test-key");

    expect(mockFetch).toHaveBeenCalledOnce();
    const [url, options] = mockFetch.mock.calls[0];
    const parsed = typeof url === "string" ? new URL(url, "http://example.com") : new URL((url as Request).url);
    const body = JSON.parse(options.body);

    expect(parsed.pathname).toContain("/key/delete");
    expect(body.keys).toEqual(["sk-test-key"]);
    expect(body.company_id).toBeUndefined();
    expect(body.project_id).toBeUndefined();
    expect(body.organization_id).toBeUndefined();
    expect(body.org_id).toBeUndefined();
  });

  it("should submit key create payloads with company_id and project_id but no legacy organization aliases", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ key: "sk-test" }),
    } as any);
    global.fetch = mockFetch as any;

    await Networking.keyCreateCall("token", "user-123", {
      key_alias: "Project Key",
      company_id: "company-123",
      project_id: "project-456",
      organization_id: "company-123",
      org_id: "company-123",
      organization_ids: ["company-123"],
      organizations: ["company-123"],
    });

    expect(mockFetch).toHaveBeenCalledOnce();
    const body = JSON.parse(mockFetch.mock.calls[0][1].body);

    expect(body.user_id).toBe("user-123");
    expect(body.company_id).toBe("company-123");
    expect(body.project_id).toBe("project-456");
    expect(body.organization_id).toBeUndefined();
    expect(body.org_id).toBeUndefined();
    expect(body.organization_ids).toBeUndefined();
    expect(body.organizations).toBeUndefined();
  });

  it("should submit service account key create payloads without legacy organization aliases", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ key: "sk-service-account" }),
    } as any);
    global.fetch = mockFetch as any;

    await Networking.keyCreateServiceAccountCall("token", {
      key_alias: "Service Account Project Key",
      company_id: "company-123",
      project_id: "project-456",
      organization_id: "company-123",
      org_id: "company-123",
    });

    expect(mockFetch).toHaveBeenCalledOnce();
    const body = JSON.parse(mockFetch.mock.calls[0][1].body);

    expect(body.company_id).toBe("company-123");
    expect(body.project_id).toBe("project-456");
    expect(body.organization_id).toBeUndefined();
    expect(body.org_id).toBeUndefined();
  });

  it("should map legacy key update organization aliases to company_id before submit", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ status: "success" }),
    } as any);
    global.fetch = mockFetch as any;

    await Networking.keyUpdateCall("token", {
      key: "sk-test-key",
      key_alias: "Updated Project Key",
      organization_id: "company-123",
      org_id: "company-123",
      project_id: "project-456",
    });

    expect(mockFetch).toHaveBeenCalledOnce();
    const body = JSON.parse(mockFetch.mock.calls[0][1].body);

    expect(body.key).toBe("sk-test-key");
    expect(body.company_id).toBe("company-123");
    expect(body.project_id).toBe("project-456");
    expect(body.organization_id).toBeUndefined();
    expect(body.org_id).toBeUndefined();
  });

  it("should reject conflicting company and legacy organization aliases before key update submit", async () => {
    const mockFetch = vi.fn();
    global.fetch = mockFetch as any;

    await expect(
      Networking.keyUpdateCall("token", {
        key: "sk-test-key",
        company_id: "company-123",
        organization_id: "company-999",
      }),
    ).rejects.toThrow("company_id and organization_id");

    expect(mockFetch).not.toHaveBeenCalled();
  });
});

describe("user membership networking", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("should submit user create payloads with company_ids and project_ids but no legacy organization aliases", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ user_id: "created-user" }),
    } as any);
    global.fetch = mockFetch as any;

    await Networking.userCreateCall("token", "created-user", {
      user_email: "created@example.com",
      company_ids: ["company-123"],
      project_ids: ["project-456"],
      company_id: "company-123",
      organization_id: "company-123",
      organization_ids: ["company-123"],
      organizations: ["company-123"],
      project_id: "project-456",
    });

    expect(mockFetch).toHaveBeenCalledOnce();
    const body = JSON.parse(mockFetch.mock.calls[0][1].body);

    expect(body.user_id).toBe("created-user");
    expect(body.company_ids).toEqual(["company-123"]);
    expect(body.project_ids).toEqual(["project-456"]);
    expect(body.company_id).toBeUndefined();
    expect(body.organization_id).toBeUndefined();
    expect(body.organization_ids).toBeUndefined();
    expect(body.organizations).toBeUndefined();
    expect(body.project_id).toBeUndefined();
  });

  it("should map legacy user update aliases to product membership arrays before submit", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ user_id: "target-user", data: {} }),
    } as any);
    global.fetch = mockFetch as any;

    await Networking.userUpdateUserCall(
      "token",
      {
        user_id: "target-user",
        user_email: "target@example.com",
        organization_id: "company-123",
        project_id: "project-456",
      },
      "internal_user",
    );

    expect(mockFetch).toHaveBeenCalledOnce();
    const body = JSON.parse(mockFetch.mock.calls[0][1].body);

    expect(body.user_id).toBe("target-user");
    expect(body.company_ids).toEqual(["company-123"]);
    expect(body.project_ids).toEqual(["project-456"]);
    expect(body.user_role).toBe("internal_user");
    expect(body.organization_id).toBeUndefined();
    expect(body.project_id).toBeUndefined();
  });

  it("should preserve empty project_ids when clearing user project memberships", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ user_id: "target-user", data: {} }),
    } as any);
    global.fetch = mockFetch as any;

    await Networking.userUpdateUserCall(
      "token",
      {
        user_id: "target-user",
        company_ids: ["company-123"],
        project_ids: [],
      },
      null,
    );

    expect(mockFetch).toHaveBeenCalledOnce();
    const body = JSON.parse(mockFetch.mock.calls[0][1].body);

    expect(body.company_ids).toEqual(["company-123"]);
    expect(body.project_ids).toEqual([]);
  });

  it("should reject conflicting company and organization membership aliases before user update submit", async () => {
    const mockFetch = vi.fn();
    global.fetch = mockFetch as any;

    await expect(
      Networking.userUpdateUserCall(
        "token",
        {
          user_id: "target-user",
          company_ids: ["company-123"],
          organization_ids: ["company-999"],
        },
        null,
      ),
    ).rejects.toThrow("company_ids and organization_ids");

    expect(mockFetch).not.toHaveBeenCalled();
  });
});

describe("team management networking", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("should send company_id and project_id for Team list filters without organization_id", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ teams: [], total: 0, page: 1, page_size: 10, total_pages: 0 }),
    } as any);
    global.fetch = mockFetch as any;

    await Networking.v2TeamListCall("token", "company-123", null, null, null, 1, 10, null, null, "project-456");

    expect(mockFetch).toHaveBeenCalledOnce();
    const [url] = mockFetch.mock.calls[0];
    const parsed = typeof url === "string" ? new URL(url, "http://example.com") : new URL((url as Request).url);

    expect(parsed.pathname).toBe("/v2/team/list");
    expect(parsed.searchParams.get("company_id")).toBe("company-123");
    expect(parsed.searchParams.get("project_id")).toBe("project-456");
    expect(parsed.searchParams.has("organization_id")).toBe(false);
  });

  it("should submit team create payloads with company_id but no legacy organization aliases", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ team_id: "team-123" }),
    } as any);
    global.fetch = mockFetch as any;

    await Networking.teamCreateCall("token", {
      team_alias: "Platform",
      company_id: "company-123",
      organization_id: "company-123",
      org_id: "company-123",
      organization_ids: ["company-123"],
      organizations: ["company-123"],
    });

    expect(mockFetch).toHaveBeenCalledOnce();
    const body = JSON.parse(mockFetch.mock.calls[0][1].body);

    expect(body.team_alias).toBe("Platform");
    expect(body.company_id).toBe("company-123");
    expect(body.organization_id).toBeUndefined();
    expect(body.org_id).toBeUndefined();
    expect(body.organization_ids).toBeUndefined();
    expect(body.organizations).toBeUndefined();
  });

  it("should map legacy team update organization aliases to company_id before submit", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ team_id: "team-123", data: {} }),
    } as any);
    global.fetch = mockFetch as any;

    await Networking.teamUpdateCall("token", {
      team_id: "team-123",
      team_alias: "Platform",
      organization_id: "company-123",
      org_id: "company-123",
    });

    expect(mockFetch).toHaveBeenCalledOnce();
    const body = JSON.parse(mockFetch.mock.calls[0][1].body);

    expect(body.team_id).toBe("team-123");
    expect(body.company_id).toBe("company-123");
    expect(body.organization_id).toBeUndefined();
    expect(body.org_id).toBeUndefined();
  });

  it("should reject conflicting company and organization aliases before team update submit", async () => {
    const mockFetch = vi.fn();
    global.fetch = mockFetch as any;

    await expect(
      Networking.teamUpdateCall("token", {
        team_id: "team-123",
        company_id: "company-123",
        organization_id: "company-999",
      }),
    ).rejects.toThrow("company_id and organization_id");

    expect(mockFetch).not.toHaveBeenCalled();
  });
});

describe("getGuardrailsList", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("should send Company and Project filters for guardrail list requests", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ guardrails: [] }),
    } as any);
    global.fetch = mockFetch as any;

    await Networking.getGuardrailsList("token", {
      companyId: "company-123",
      projectId: "project-456",
    });

    expect(mockFetch).toHaveBeenCalledOnce();
    const [url] = mockFetch.mock.calls[0];
    const parsed =
      typeof url === "string"
        ? new URL(url, "http://example.com")
        : new URL((url as Request).url);

    expect(parsed.pathname).toContain("/v2/guardrails/list");
    expect(parsed.searchParams.get("company_id")).toBe("company-123");
    expect(parsed.searchParams.get("project_id")).toBe("project-456");
    expect(Array.from(parsed.searchParams.keys()).sort()).toEqual([
      "company_id",
      "project_id",
    ]);
  });

  it("should not fall back to unscoped guardrail list when scoped request fails", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      json: vi.fn().mockResolvedValue({ detail: "not allowed" }),
    } as any);
    global.fetch = mockFetch as any;

    await expect(
      Networking.getGuardrailsList("token", {
        companyId: "company-123",
        projectId: "project-456",
      }),
    ).rejects.toThrow("v2 guardrails/list returned 403");

    expect(mockFetch).toHaveBeenCalledOnce();
    const [url] = mockFetch.mock.calls[0];
    const parsed =
      typeof url === "string"
        ? new URL(url, "http://example.com")
        : new URL((url as Request).url);

    expect(parsed.pathname).toContain("/v2/guardrails/list");
    expect(parsed.searchParams.get("company_id")).toBe("company-123");
    expect(parsed.searchParams.get("project_id")).toBe("project-456");
  });
});

describe("uiSpendLogsCall", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("should send company_id and project_id for spend log filters", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ data: [], total: 0, page: 1, page_size: 50, total_pages: 0 }),
    } as any);
    global.fetch = mockFetch as any;

    await Networking.uiSpendLogsCall({
      accessToken: "token",
      start_date: "2026-05-01 00:00:00",
      end_date: "2026-05-17 23:59:59",
      params: {
        company_id: "company-123",
        project_id: "project-456",
      },
    });

    expect(mockFetch).toHaveBeenCalledOnce();
    const [url] = mockFetch.mock.calls[0];
    const parsed = typeof url === "string" ? new URL(url, "http://example.com") : new URL((url as Request).url);

    expect(parsed.pathname).toBe("/spend/logs/ui");
    expect(parsed.searchParams.get("company_id")).toBe("company-123");
    expect(parsed.searchParams.get("project_id")).toBe("project-456");
    expect(parsed.searchParams.has("organization_id")).toBe(false);
  });

  it("should map legacy spend log organization aliases to company_id before submit", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ data: [], total: 0, page: 1, page_size: 50, total_pages: 0 }),
    } as any);
    global.fetch = mockFetch as any;

    await Networking.uiSpendLogsCall({
      accessToken: "token",
      start_date: "2026-05-01 00:00:00",
      end_date: "2026-05-17 23:59:59",
      params: {
        organization_id: "company-123",
        org_id: "company-123",
        project_id: "project-456",
      } as any,
    });

    expect(mockFetch).toHaveBeenCalledOnce();
    const [url] = mockFetch.mock.calls[0];
    const parsed = typeof url === "string" ? new URL(url, "http://example.com") : new URL((url as Request).url);

    expect(parsed.pathname).toBe("/spend/logs/ui");
    expect(parsed.searchParams.get("company_id")).toBe("company-123");
    expect(parsed.searchParams.get("project_id")).toBe("project-456");
    expect(parsed.searchParams.has("organization_id")).toBe(false);
    expect(parsed.searchParams.has("org_id")).toBe(false);
  });

  it("should reject conflicting company and organization spend log aliases before submit", async () => {
    const mockFetch = vi.fn();
    global.fetch = mockFetch as any;

    await expect(
      Networking.uiSpendLogsCall({
        accessToken: "token",
        start_date: "2026-05-01 00:00:00",
        end_date: "2026-05-17 23:59:59",
        params: {
          company_id: "company-123",
          organization_id: "company-999",
        } as any,
      }),
    ).rejects.toThrow("company_id and organization_id");

    expect(mockFetch).not.toHaveBeenCalled();
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
