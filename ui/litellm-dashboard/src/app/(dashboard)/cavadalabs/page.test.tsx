import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders, screen, waitFor } from "../../../../tests/test-utils";
import CavadaLabsPage from "./page";

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
});
