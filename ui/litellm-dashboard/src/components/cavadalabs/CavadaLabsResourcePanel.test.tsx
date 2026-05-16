import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { renderWithProviders, screen, waitFor } from "../../../tests/test-utils";
import CavadaLabsResourcePanel from "./CavadaLabsResourcePanel";
import { buildCavadaLabsResourceConfigs } from "./resourceConfigs";
import type { CavadaLabsResourceConfig, CavadaLabsRuntimeContext } from "./types";

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

const context: CavadaLabsRuntimeContext = {
  companies: [],
  projects: [],
  chatbots: [],
  ragCollections: [],
  nodes: [],
};

describe("CavadaLabsResourcePanel", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("should render rows from the configured list endpoint", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      jsonResponse({
        companies: [
          {
            company_id: "company-1",
            legal_name: "Acme Srl",
            status: "active",
            admin_emails: ["admin@example.com"],
          },
        ],
        count: 1,
      }),
    );
    global.fetch = mockFetch as any;

    renderWithProviders(
      <CavadaLabsResourcePanel
        accessToken="token-1"
        config={buildCavadaLabsResourceConfigs(context).companies}
        context={context}
      />,
    );

    expect(await screen.findByText("Acme Srl")).toBeInTheDocument();
    expect(mockFetch).toHaveBeenCalledWith(
      "http://proxy.test/cavadalabs/companies",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("should show migration command when Billing reports list returns missing schema", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      jsonResponse(
        {
          detail: {
            error: "CavadaLabs billing schema is missing required table delegate.",
            schema_status: "missing_schema",
            migration_status: "schema_missing",
            missing_schema: ["cavadalabs_companymembertable"],
            migration_command: "uv run prisma migrate deploy",
          },
        },
        false,
      ),
    );
    global.fetch = mockFetch as any;

    renderWithProviders(
      <CavadaLabsResourcePanel
        accessToken="token-1"
        config={buildCavadaLabsResourceConfigs(context).billingReports}
        context={context}
      />,
    );

    expect(await screen.findByText("CavadaLabs schema is not ready")).toBeInTheDocument();
    expect(screen.getByText("Missing schema: cavadalabs_companymembertable")).toBeInTheDocument();
    expect(screen.getByText("uv run prisma migrate deploy")).toBeInTheDocument();
    expect(screen.queryByText(/0 shown/i)).toBeInTheDocument();
  });

  it("should show migration command when Billing report generation returns missing schema", async () => {
    const user = userEvent.setup();
    const billingContext: CavadaLabsRuntimeContext = {
      ...context,
      companies: [
        {
          company_id: "company-1",
          legal_name: "Acme Srl",
          cavadalabs_can_manage: true,
        },
      ],
    };
    const baseConfig = buildCavadaLabsResourceConfigs(billingContext).billingReports;
    const config: CavadaLabsResourceConfig = {
      ...baseConfig,
      createFields: baseConfig.createFields?.map((field) =>
        field.name === "company_id" ? { ...field, defaultValue: "company-1" } : field,
      ),
    };
    const mockFetch = vi.fn().mockImplementation((_url: string, options: RequestInit) => {
      if (options?.method === "POST") {
        return Promise.resolve(
          jsonResponse(
            {
              detail: {
                error: "CavadaLabs billing schema is missing required ledger columns.",
                schema_status: "missing_schema",
                migration_status: "schema_missing",
                missing_schema: ["CavadaLabs_RequestLedgerTable.company_id"],
                migration_command: "uv run prisma migrate deploy",
              },
            },
            false,
          ),
        );
      }
      return Promise.resolve(jsonResponse({ billing_reports: [], count: 0 }));
    });
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsResourcePanel accessToken="token-1" config={config} context={billingContext} />);

    await user.click(await screen.findByRole("button", { name: /generate report/i }));
    await user.click(screen.getByRole("button", { name: /^ok$/i }));

    expect(await screen.findByText("CavadaLabs schema is not ready")).toBeInTheDocument();
    expect(screen.getByText("Missing schema: CavadaLabs_RequestLedgerTable.company_id")).toBeInTheDocument();
    expect(screen.getByText("uv run prisma migrate deploy")).toBeInTheDocument();
    expect(
      mockFetch.mock.calls.some((call) => {
        const requestUrl = String(call[0]);
        return requestUrl === "http://proxy.test/cavadalabs/billing-reports" && call[1]?.method === "POST";
      }),
    ).toBe(true);
  });

  it("should submit create forms with normalized payloads", async () => {
    const user = userEvent.setup();
    const baseConfig = buildCavadaLabsResourceConfigs(context).companies;
    const createConfig: CavadaLabsResourceConfig = {
      ...baseConfig,
      createFields: [
        { name: "legal_name", label: "Legal name", type: "text", required: true },
        {
          name: "status",
          label: "Status",
          type: "select",
          defaultValue: "active",
          options: [{ label: "active", value: "active" }],
        },
        { name: "metadata", label: "Metadata", type: "json", defaultValue: {} },
      ],
    };
    const mockFetch = vi.fn().mockImplementation((_url: string, options: RequestInit) => {
      if (options?.method === "POST") {
        return Promise.resolve(
          jsonResponse({
            company_id: "company-2",
            legal_name: "Beta Srl",
            status: "active",
          }),
        );
      }
      return Promise.resolve(jsonResponse({ companies: [], count: 0 }));
    });
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsResourcePanel accessToken="token-1" config={createConfig} context={context} />);

    await user.click(screen.getByRole("button", { name: /new company/i }));
    await user.type(screen.getByLabelText("Legal name"), "Beta Srl");
    await user.click(screen.getByRole("button", { name: /^ok$/i }));

    await waitFor(() => {
      expect(mockFetch.mock.calls.some((call) => call[1]?.method === "POST")).toBe(true);
    });

    const postCall = mockFetch.mock.calls.find((call) => call[1]?.method === "POST");
    expect(postCall?.[0]).toBe("http://proxy.test/cavadalabs/companies");
    expect(JSON.parse(String(postCall?.[1]?.body))).toEqual(
      expect.objectContaining({
        legal_name: "Beta Srl",
        status: "active",
        metadata: {},
      }),
    );
  });

  it("should submit company edits through the configured patch endpoint", async () => {
    const user = userEvent.setup();
    const config = buildCavadaLabsResourceConfigs(context).companies;
    const mockFetch = vi.fn().mockImplementation((_url: string, options: RequestInit) => {
      if (options?.method === "PATCH") {
        return Promise.resolve(
          jsonResponse({
            company_id: "company-1",
            legal_name: "Acme Labs Srl",
            status: "active",
          }),
        );
      }
      return Promise.resolve(
        jsonResponse({
          companies: [
            {
              company_id: "company-1",
              legal_name: "Acme Srl",
              status: "active",
              billing_address: {},
              retention_policy: {},
              default_billing_settings: {},
              metadata: {},
            },
          ],
          count: 1,
        }),
      );
    });
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsResourcePanel accessToken="token-1" config={config} context={context} />);

    await screen.findByText("Acme Srl");
    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.clear(screen.getByLabelText("Legal name"));
    await user.type(screen.getByLabelText("Legal name"), "Acme Labs Srl");
    await user.click(screen.getByRole("button", { name: /^ok$/i }));

    await waitFor(() => {
      expect(mockFetch.mock.calls.some((call) => call[1]?.method === "PATCH")).toBe(true);
    });

    const patchCall = mockFetch.mock.calls.find((call) => call[1]?.method === "PATCH");
    expect(patchCall?.[0]).toBe("http://proxy.test/cavadalabs/companies/company-1");
    expect(JSON.parse(String(patchCall?.[1]?.body))).toEqual(
      expect.objectContaining({
        legal_name: "Acme Labs Srl",
        status: "active",
      }),
    );
  });

  it("should hide mutation actions when Company scope is read-only", async () => {
    const config = buildCavadaLabsResourceConfigs(context).companies;
    const mockFetch = vi.fn().mockResolvedValue(
      jsonResponse({
        companies: [
          {
            company_id: "company-1",
            legal_name: "Read Only Srl",
            status: "active",
            cavadalabs_access_role: "viewer",
            cavadalabs_can_manage: false,
          },
        ],
        count: 1,
      }),
    );
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsResourcePanel accessToken="token-1" config={config} context={context} />);

    expect(await screen.findByText("Read Only Srl")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Details" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Archive" })).not.toBeInTheDocument();
  });

  it("should hide create when all Company scopes are read-only", async () => {
    const readOnlyContext: CavadaLabsRuntimeContext = {
      ...context,
      companies: [
        {
          company_id: "company-1",
          legal_name: "Read Only Srl",
          cavadalabs_access_role: "viewer",
          cavadalabs_can_manage: false,
        },
      ],
    };
    const config = buildCavadaLabsResourceConfigs(readOnlyContext).projects;
    const mockFetch = vi.fn().mockResolvedValue(jsonResponse({ projects: [], count: 0 }));
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsResourcePanel accessToken="token-1" config={config} context={readOnlyContext} />);

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "http://proxy.test/cavadalabs/projects",
        expect.objectContaining({ method: "GET" }),
      );
    });
    expect(screen.queryByRole("button", { name: /new project/i })).not.toBeInTheDocument();
  });

  it("should archive projects through the configured delete endpoint", async () => {
    const user = userEvent.setup();
    const config = buildCavadaLabsResourceConfigs(context).projects;
    const mockFetch = vi.fn().mockImplementation((_url: string, options: RequestInit) => {
      if (options?.method === "DELETE") {
        return Promise.resolve(jsonResponse({ project_id: "project-1", status: "archived" }));
      }
      return Promise.resolve(
        jsonResponse({
          projects: [
            {
              project_id: "project-1",
              company_id: "company-1",
              name: "Support",
              status: "production",
              allowed_models: ["cavadalabs/qwen3-32b"],
            },
          ],
          count: 1,
        }),
      );
    });
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsResourcePanel accessToken="token-1" config={config} context={context} />);

    await screen.findByText("Support");
    await user.click(screen.getByRole("button", { name: "Archive" }));
    await user.click(screen.getByRole("button", { name: /^ok$/i }));

    await waitFor(() => {
      expect(mockFetch.mock.calls.some((call) => call[1]?.method === "DELETE")).toBe(true);
    });

    const deleteCall = mockFetch.mock.calls.find((call) => call[1]?.method === "DELETE");
    expect(deleteCall?.[0]).toBe("http://proxy.test/cavadalabs/projects/project-1");
  });

  it("should render Project details without exposing LiteLLM compatibility IDs", async () => {
    const user = userEvent.setup();
    const config = buildCavadaLabsResourceConfigs(context).projects;
    const mockFetch = vi.fn().mockImplementation((url: string) => {
      if (url.endsWith("/cavadalabs/projects/project-1/members")) {
        return Promise.resolve(
          jsonResponse({
            project_id: "project-1",
            company_id: "company-1",
            members: [],
            count: 0,
          }),
        );
      }
      return Promise.resolve(
        jsonResponse({
          projects: [
            {
              project_id: "project-1",
              company_id: "company-1",
              name: "Support",
              status: "production",
              budget: 125,
              allowed_models: ["cavadalabs/qwen3-32b"],
              allowed_rag_collections: ["collection-1"],
              default_guardrail_policy: "policy-1",
              litellm_team_id: "team-compat-1",
              litellm_organization_id: "org-compat-1",
            },
          ],
          count: 1,
        }),
      );
    });
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsResourcePanel accessToken="token-1" config={config} context={context} />);

    await screen.findByText("Support");
    await user.click(screen.getByRole("button", { name: "Details" }));

    expect(await screen.findByText("Project overview")).toBeInTheDocument();
    expect(screen.getByText("Project policy")).toBeInTheDocument();
    expect(screen.getAllByText("Project ID").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Company").length).toBeGreaterThan(0);
    expect(screen.getAllByText("cavadalabs/qwen3-32b").length).toBeGreaterThan(0);
    expect(screen.getByText("collection-1")).toBeInTheDocument();
    expect(screen.getByText("policy-1")).toBeInTheDocument();
    expect(screen.getByText("Project members")).toBeInTheDocument();
    expect(screen.queryByText("litellm_team_id")).not.toBeInTheDocument();
    expect(screen.queryByText("team-compat-1")).not.toBeInTheDocument();
    expect(screen.queryByText("litellm_organization_id")).not.toBeInTheDocument();
    expect(screen.queryByText("org-compat-1")).not.toBeInTheDocument();
  });
});
