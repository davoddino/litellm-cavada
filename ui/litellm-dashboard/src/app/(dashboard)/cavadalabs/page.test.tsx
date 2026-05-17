import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders, screen, waitFor } from "../../../../tests/test-utils";
import CavadaLabsCompaniesPage from "./companies/page";
import CavadaLabsPage from "./page";

const { mockUseSearchParams } = vi.hoisted(() => ({
  mockUseSearchParams: vi.fn(() => new URLSearchParams()),
}));

vi.mock("next/navigation", () => ({
  useSearchParams: mockUseSearchParams,
}));

vi.mock("@/app/(dashboard)/hooks/useAuthorized", () => ({
  default: () => ({
    accessToken: "token-1",
    token: "token-1",
    userRole: "Admin",
    userId: "user-1",
  }),
}));

vi.mock("@/components/networking", () => ({
  getProxyBaseUrl: () => "http://proxy.test",
  getGlobalLitellmHeaderName: () => "Authorization",
  deriveErrorMessage: (errorData: any) => errorData?.detail?.error ?? errorData?.detail ?? "error",
  handleError: vi.fn(),
  modelAvailableCall: vi.fn().mockResolvedValue({
    data: [{ id: "Qwen3.6-35B-A3B" }, { id: "whisper-small" }],
  }),
}));

const jsonResponse = (payload: any) =>
  ({
    ok: true,
    headers: {
      get: () => "application/json",
    },
    json: vi.fn().mockResolvedValue(payload),
    text: vi.fn(),
  }) as any;

const payloadForPath = (path: string) => {
  switch (path) {
    case "/cavadalabs/companies":
      return {
        companies: [{ company_id: "company-1", legal_name: "Acme Srl", status: "active" }],
        count: 1,
      };
    case "/cavadalabs/projects":
      return {
        projects: [
          {
            project_id: "project-1",
            company_id: "company-1",
            name: "Dispatch Project",
            status: "production",
            cavadalabs_can_manage: true,
          },
        ],
        count: 1,
      };
    case "/cavadalabs/projects/project-1/members":
      return {
        project_id: "project-1",
        company_id: "company-1",
        members: [
          {
            membership_id: "membership-1",
            project_id: "project-1",
            company_id: "company-1",
            user_id: "user-1",
            role: "project_admin",
            created_at: "2026-05-15T12:00:00Z",
            updated_at: "2026-05-15T12:00:00Z",
          },
        ],
        count: 1,
      };
    case "/cavadalabs/chatbots":
      return {
        chatbots: [
          {
            chatbot_id: "chatbot-1",
            company_id: "company-1",
            project_id: "project-1",
            name: "Support Bot",
            status: "published",
          },
        ],
        count: 1,
      };
    case "/cavadalabs/rag-collections":
      return {
        rag_collections: [
          {
            collection_id: "collection-1",
            company_id: "company-1",
            project_id: "project-1",
            name: "Docs",
          },
        ],
        count: 1,
      };
    case "/cavadalabs/nodes":
      return {
        nodes: [{ node_id: "node-1", display_name: "GPU Node", status: "online" }],
        count: 1,
      };
    case "/cavadalabs/web-tokens":
      return { web_tokens: [], count: 0 };
    case "/cavadalabs/model-load-requests":
      return { model_load_requests: [], count: 0 };
    case "/cavadalabs/guardrail-policies":
      return {
        guardrail_policies: [{ policy_id: "guardrail-1", name: "Default Safety", status: "active" }],
        count: 1,
      };
    case "/cavadalabs/billing-reports":
      return { billing_reports: [], count: 0 };
    case "/cavadalabs/companies/usage/diagnostics":
      return {
        diagnostics: [
          {
            entity_type: "company",
            entity_id: "company-1",
            status: "visible",
            ledger_rows: 3,
            attributable_spend_logs: 3,
            ledger_gap: 0,
            recommended_action: "none",
            scoped_backfill_available: false,
            missing_mappings: [],
            message: "Company usage is visible in the CavadaLabs request ledger.",
          },
        ],
        migration_name: "20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata",
        migration_command: "uv run prisma migrate deploy",
      };
    case "/cavadalabs/companies/daily/activity":
      return {
        results: [
          {
            date: "2026-05-15",
            metrics: {
              spend: 0.42,
              prompt_tokens: 30,
              completion_tokens: 20,
              total_tokens: 50,
              api_requests: 2,
              successful_requests: 2,
              failed_requests: 0,
              cache_read_input_tokens: 0,
              cache_creation_input_tokens: 0,
            },
            breakdown: {},
          },
        ],
        metadata: {
          total_spend: 0.42,
          total_prompt_tokens: 30,
          total_completion_tokens: 20,
          total_tokens: 50,
          total_api_requests: 2,
          total_successful_requests: 2,
          total_failed_requests: 0,
          page: 1,
          total_pages: 1,
          has_more: false,
        },
      };
    case "/cavadalabs/model-policies":
      return {
        model_policies: [
          {
            policy_id: "policy-1",
            project_id: "project-1",
            model_alias: "cavadalabs/qwen3-32b",
            provider: "cavadalabs",
            enabled: true,
          },
        ],
        count: 1,
      };
    default:
      throw new Error(`Unexpected CavadaLabs request: ${path}`);
  }
};

describe("CavadaLabsPage", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseSearchParams.mockReturnValue(new URLSearchParams());
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("should render the dashboard with live overview data from the CavadaLabs API", async () => {
    const mockFetch = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://proxy.test");
      return Promise.resolve(jsonResponse(payloadForPath(url.pathname)));
    });
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsPage />);

    expect(await screen.findByRole("heading", { name: "CavadaLabs" })).toBeInTheDocument();
    expect(await screen.findByText("Tenant model")).toBeInTheDocument();
    expect(await screen.findByText("1 companies, 1 projects")).toBeInTheDocument();
    expect(await screen.findByText("1 chatbots, 1 model policies")).toBeInTheDocument();
    expect(await screen.findByText("1 registered nodes")).toBeInTheDocument();
    expect(await screen.findByText("1 guardrail policies")).toBeInTheDocument();

    await waitFor(() => {
      expect(
        mockFetch.mock.calls.some(([url, options]) => {
          const headers = options?.headers as Record<string, string> | undefined;
          return (
            String(url) === "http://proxy.test/cavadalabs/model-policies?project_id=project-1" &&
            headers?.Authorization === "Bearer token-1"
          );
        }),
      ).toBe(true);
    });
  });

  it("should open the tenants tab when a Companies access-control link is requested", async () => {
    mockUseSearchParams.mockReturnValue(new URLSearchParams("tab=tenants&resource=companies"));
    const mockFetch = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://proxy.test");
      return Promise.resolve(jsonResponse(payloadForPath(url.pathname)));
    });
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsPage />);

    const tenantsTab = await screen.findByRole("tab", { name: "Tenants" });
    expect(tenantsTab).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByText("New company")).toBeInTheDocument();
    expect(await screen.findByText("New project")).toBeInTheDocument();
  });

  it("should open CavadaLabs Project details when a Project route is requested", async () => {
    mockUseSearchParams.mockReturnValue(new URLSearchParams("tab=tenants&resource=projects&project_id=project-1"));
    const mockFetch = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://proxy.test");
      return Promise.resolve(jsonResponse(payloadForPath(url.pathname)));
    });
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsPage />);

    expect(await screen.findByRole("tab", { name: "Tenants" })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByText("Projects details")).toBeInTheDocument();
    expect(await screen.findByText("Project overview")).toBeInTheDocument();
    expect(screen.getAllByText("project-1").length).toBeGreaterThan(0);
    expect(screen.getAllByText("company-1").length).toBeGreaterThan(0);
    expect(await screen.findByText("Project members")).toBeInTheDocument();
    expect(await screen.findByText("user-1")).toBeInTheDocument();
  });

  it("should render billing diagnostics with Company scope when the billing tab is requested", async () => {
    mockUseSearchParams.mockReturnValue(new URLSearchParams("tab=billing"));
    const mockFetch = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://proxy.test");
      return Promise.resolve(jsonResponse(payloadForPath(url.pathname)));
    });
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsPage />);

    const billingTab = await screen.findByRole("tab", { name: "Billing" });
    expect(billingTab).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByText("Usage diagnostics")).toBeInTheDocument();
    expect(await screen.findByText("Company/Project usage")).toBeInTheDocument();
    expect(await screen.findByText("2026-05-15")).toBeInTheDocument();
    expect(await screen.findByText("Usage attribution is healthy")).toBeInTheDocument();

    await waitFor(() => {
      expect(
        mockFetch.mock.calls.some(([url]) => {
          const parsed = new URL(String(url), "http://proxy.test");
          return (
            parsed.pathname === "/cavadalabs/companies/usage/diagnostics" &&
            parsed.searchParams.get("company_ids") === "company-1" &&
            parsed.searchParams.get("project_ids") === null
          );
        }),
      ).toBe(true);
      expect(
        mockFetch.mock.calls.some(([url]) => {
          const parsed = new URL(String(url), "http://proxy.test");
          return (
            parsed.pathname === "/cavadalabs/companies/daily/activity" &&
            parsed.searchParams.get("company_ids") === "company-1" &&
            parsed.searchParams.get("project_ids") === null
          );
        }),
      ).toBe(true);
    });
  });

  it("should open the tenants tab from the Companies route", async () => {
    const mockFetch = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://proxy.test");
      return Promise.resolve(jsonResponse(payloadForPath(url.pathname)));
    });
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsCompaniesPage />);

    const tenantsTab = await screen.findByRole("tab", { name: "Tenants" });
    expect(tenantsTab).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByText("New company")).toBeInTheDocument();
    expect(await screen.findByText("New project")).toBeInTheDocument();
  });
});
