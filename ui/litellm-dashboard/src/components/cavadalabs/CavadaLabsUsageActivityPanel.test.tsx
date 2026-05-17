import { act, fireEvent, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders, screen } from "../../../tests/test-utils";
import CavadaLabsUsageActivityPanel from "./CavadaLabsUsageActivityPanel";
import type { CavadaLabsRuntimeContext } from "./types";

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

const usageMetrics = (overrides: Record<string, any> = {}) => ({
  spend: 0.42,
  prompt_tokens: 30,
  completion_tokens: 20,
  total_tokens: 50,
  api_requests: 2,
  successful_requests: 1,
  failed_requests: 1,
  cache_read_input_tokens: 0,
  cache_creation_input_tokens: 0,
  ...overrides,
});

const usageBreakdown = {
  entities: {
    "company-1": {
      metrics: usageMetrics({ spend: 0.42, api_requests: 2, total_tokens: 50 }),
    },
  },
  models: {
    "cavadalabs/qwen3-32b": {
      metrics: usageMetrics({ spend: 0.42, api_requests: 2, total_tokens: 50 }),
    },
  },
  providers: {
    cavadalabs: {
      metrics: usageMetrics({ spend: 0.42, api_requests: 2, total_tokens: 50 }),
    },
  },
  api_keys: {
    "hashed-key": {
      metrics: usageMetrics({ spend: 0.42, api_requests: 2, total_tokens: 50 }),
    },
  },
};

const activityResponse = (overrides: Record<string, any> = {}) => {
  const { metadata, results, ...rest } = overrides;
  return {
    results: results ?? [
      {
        date: "2026-05-15",
        metrics: usageMetrics(),
        breakdown: usageBreakdown,
      },
    ],
    metadata: {
      total_spend: 0.42,
      total_prompt_tokens: 30,
      total_completion_tokens: 20,
      total_tokens: 50,
      total_api_requests: 2,
      total_successful_requests: 1,
      total_failed_requests: 1,
      page: 1,
      total_pages: 1,
      has_more: false,
      ...(metadata ?? {}),
    },
    ...rest,
  };
};

const emptyActivityResponse = {
  results: [],
  metadata: {
    total_spend: 0,
    total_prompt_tokens: 0,
    total_completion_tokens: 0,
    total_tokens: 0,
    total_api_requests: 0,
    total_successful_requests: 0,
    total_failed_requests: 0,
    page: 1,
    total_pages: 1,
    has_more: false,
  },
};

const diagnosticsResponse = (
  recommendedAction = "none",
  entityType: "company" | "project" = "company",
  entityId = entityType === "company" ? "company-1" : "project-1",
  overrides: Record<string, any> = {},
) => {
  const { diagnostics: diagnosticsOverrides, ...responseOverrides } = overrides;
  return {
    diagnostics: [
      {
        entity_type: entityType,
        entity_id: entityId,
        status:
          recommendedAction === "none"
            ? "visible"
            : recommendedAction === "no_attributable_spend"
              ? "no_attributable_spend"
              : "scoped_backfill_available",
        ledger_rows: recommendedAction === "none" ? 1 : 0,
        attributable_spend_logs: recommendedAction === "none" || recommendedAction === "no_attributable_spend" ? 0 : 2,
        ledger_gap: recommendedAction === "run_scoped_backfill" ? 2 : 0,
        recommended_action: recommendedAction === "no_attributable_spend" ? "none" : recommendedAction,
        scoped_backfill_available: recommendedAction === "run_scoped_backfill",
        filters_exclude_usage: false,
        date_range_excludes_usage: false,
        missing_mappings: [],
        missing_schema: [],
        message: `${entityType} usage diagnostics.`,
        ...(diagnosticsOverrides?.[0] ?? {}),
      },
    ],
    migration_name: "20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata",
    migration_command: "uv run prisma migrate deploy",
    schema_status: "ready",
    migration_status: "ready",
    missing_schema: [],
    ...responseOverrides,
  };
};

const companyContext: CavadaLabsRuntimeContext = {
  companies: [{ company_id: "company-1", legal_name: "Acme Srl", cavadalabs_can_manage: true }],
  projects: [{ project_id: "project-1", name: "Support", cavadalabs_can_manage: true }],
  chatbots: [],
  ragCollections: [],
  nodes: [],
};

const projectOnlyContext: CavadaLabsRuntimeContext = {
  companies: [],
  projects: [{ project_id: "project-1", name: "Support", cavadalabs_can_manage: true }],
  chatbots: [],
  ragCollections: [],
  nodes: [],
};

const projectMemberContext: CavadaLabsRuntimeContext = {
  companies: [
    {
      company_id: "company-1",
      legal_name: "Acme Srl",
      cavadalabs_can_manage: false,
      cavadalabs_can_view_usage: false,
    },
  ],
  projects: [
    {
      project_id: "project-1",
      company_id: "company-1",
      name: "Support",
      cavadalabs_can_manage: true,
      cavadalabs_can_view_usage: true,
    },
  ],
  chatbots: [],
  ragCollections: [],
  nodes: [],
};

const companyViewerContext: CavadaLabsRuntimeContext = {
  companies: [{ company_id: "company-1", legal_name: "Acme Srl", cavadalabs_can_manage: false }],
  projects: [{ project_id: "project-1", name: "Support", cavadalabs_can_manage: false }],
  chatbots: [],
  ragCollections: [],
  nodes: [],
};

describe("CavadaLabsUsageActivityPanel", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("should call Company daily activity with canonical Company filters and render usage totals", async () => {
    const mockFetch = vi.fn((input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://proxy.test");
      if (url.pathname === "/cavadalabs/companies/daily/activity") {
        return Promise.resolve(jsonResponse(activityResponse()));
      }
      if (url.pathname === "/cavadalabs/companies/usage/diagnostics") {
        return Promise.resolve(jsonResponse(diagnosticsResponse()));
      }
      throw new Error(`Unexpected request: ${url.pathname}`);
    });
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsUsageActivityPanel accessToken="token-1" context={companyContext} />);

    expect(await screen.findByText("Company/Project usage")).toBeInTheDocument();
    expect(await screen.findByText("2026-05-15")).toBeInTheDocument();
    expect((await screen.findAllByText("$0.4200")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("50").length).toBeGreaterThan(0);

    await waitFor(() => {
      expect(
        mockFetch.mock.calls.some(([requestUrl]) => {
          const url = new URL(String(requestUrl), "http://proxy.test");
          return (
            url.pathname === "/cavadalabs/companies/daily/activity" &&
            url.searchParams.get("company_ids") === "company-1" &&
            url.searchParams.get("project_ids") === null &&
            url.searchParams.get("page") === "1" &&
            url.searchParams.get("page_size") === "100"
          );
        }),
      ).toBe(true);
    });
  });

  it("should expose daily usage breakdown without Organization or Team labels", async () => {
    const mockFetch = vi.fn((input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://proxy.test");
      if (url.pathname === "/cavadalabs/companies/daily/activity") {
        return Promise.resolve(jsonResponse(activityResponse()));
      }
      if (url.pathname === "/cavadalabs/companies/usage/diagnostics") {
        return Promise.resolve(jsonResponse(diagnosticsResponse()));
      }
      throw new Error(`Unexpected request: ${url.pathname}`);
    });
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsUsageActivityPanel accessToken="token-1" context={companyContext} />);

    expect(await screen.findByText("2026-05-15")).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /expand row/i }));
    });

    expect(await screen.findByText("cavadalabs/qwen3-32b")).toBeInTheDocument();
    expect(screen.getAllByText("Provider").length).toBeGreaterThan(0);
    expect(screen.getByText("API key")).toBeInTheDocument();
    expect(screen.getAllByText("Company").length).toBeGreaterThan(0);
    expect(screen.queryByText(/organization/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^team$/i)).not.toBeInTheDocument();
  });

  it("should paginate aggregated daily usage pages through CavadaLabs endpoints", async () => {
    const mockFetch = vi.fn((input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://proxy.test");
      if (url.pathname === "/cavadalabs/companies/daily/activity") {
        const page = url.searchParams.get("page");
        if (page === "2") {
          return Promise.resolve(
            jsonResponse(
              activityResponse({
                results: [
                  {
                    date: "2026-05-14",
                    metrics: usageMetrics({ spend: 0.25, total_tokens: 25, api_requests: 1 }),
                    breakdown: usageBreakdown,
                  },
                ],
                metadata: {
                  total_spend: 0.67,
                  total_tokens: 75,
                  total_api_requests: 3,
                  page: 2,
                  total_pages: 2,
                  has_more: false,
                },
              }),
            ),
          );
        }
        return Promise.resolve(
          jsonResponse(
            activityResponse({
              metadata: {
                page: 1,
                total_pages: 2,
                has_more: true,
              },
            }),
          ),
        );
      }
      if (url.pathname === "/cavadalabs/companies/usage/diagnostics") {
        return Promise.resolve(jsonResponse(diagnosticsResponse()));
      }
      throw new Error(`Unexpected request: ${url.pathname}`);
    });
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsUsageActivityPanel accessToken="token-1" context={companyContext} />);

    expect(await screen.findByText("2026-05-15")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTitle("2")).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(screen.getByTitle("2"));
    });

    expect(await screen.findByText("2026-05-14")).toBeInTheDocument();
    await waitFor(() => {
      expect(
        mockFetch.mock.calls.some(([requestUrl]) => {
          const url = new URL(String(requestUrl), "http://proxy.test");
          return (
            url.pathname === "/cavadalabs/companies/daily/activity" &&
            url.searchParams.get("company_ids") === "company-1" &&
            url.searchParams.get("page") === "2" &&
            url.searchParams.get("page_size") === "100"
          );
        }),
      ).toBe(true);
    });
  });

  it("should pass Project usage filters without exposing Organizations", async () => {
    const mockFetch = vi.fn((input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://proxy.test");
      if (url.pathname === "/cavadalabs/projects/daily/activity") {
        return Promise.resolve(jsonResponse(emptyActivityResponse));
      }
      if (url.pathname === "/cavadalabs/projects/usage/diagnostics") {
        return Promise.resolve(jsonResponse(diagnosticsResponse()));
      }
      throw new Error(`Unexpected request: ${url.pathname}`);
    });
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsUsageActivityPanel accessToken="token-1" context={projectOnlyContext} />);

    await screen.findByText("No Project usage for this selection");

    await act(async () => {
      fireEvent.change(screen.getByLabelText("Provider filter"), { target: { value: "openai" } });
      fireEvent.change(screen.getByLabelText("Model filter"), { target: { value: "openai/gpt-4.1" } });
      fireEvent.change(screen.getByLabelText("API key hash filter"), { target: { value: "hashed-key" } });
      fireEvent.change(screen.getByLabelText("Minimum spend filter"), { target: { value: "0.1" } });
      fireEvent.change(screen.getByLabelText("Maximum spend filter"), { target: { value: "1" } });
      fireEvent.click(screen.getByRole("button", { name: /load usage/i }));
    });

    await waitFor(() => {
      expect(
        mockFetch.mock.calls.some(([requestUrl]) => {
          const url = new URL(String(requestUrl), "http://proxy.test");
          return (
            url.pathname === "/cavadalabs/projects/daily/activity" &&
            url.searchParams.get("project_ids") === "project-1" &&
            url.searchParams.get("company_ids") === null &&
            url.searchParams.get("provider") === "openai" &&
            url.searchParams.get("model") === "openai/gpt-4.1" &&
            url.searchParams.get("api_key") === "hashed-key" &&
            url.searchParams.get("min_spend") === "0.1" &&
            url.searchParams.get("max_spend") === "1"
          );
        }),
      ).toBe(true);
      expect(
        mockFetch.mock.calls.some(([requestUrl]) => {
          const url = new URL(String(requestUrl), "http://proxy.test");
          return (
            url.pathname === "/cavadalabs/projects/usage/diagnostics" &&
            url.searchParams.get("project_ids") === "project-1" &&
            url.searchParams.get("provider") === "openai" &&
            url.searchParams.get("model") === "openai/gpt-4.1" &&
            url.searchParams.get("api_key") === "hashed-key" &&
            url.searchParams.get("min_spend") === "0.1" &&
            url.searchParams.get("max_spend") === "1"
          );
        }),
      ).toBe(true);
    });

    expect(screen.queryByText(/organization/i)).not.toBeInTheDocument();
  });

  it("should default project-only members to Project usage when the parent Company record is visible", async () => {
    const mockFetch = vi.fn((input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://proxy.test");
      if (url.pathname === "/cavadalabs/projects/daily/activity") {
        return Promise.resolve(jsonResponse(activityResponse()));
      }
      if (url.pathname === "/cavadalabs/projects/usage/diagnostics") {
        return Promise.resolve(jsonResponse(diagnosticsResponse("none", "project")));
      }
      throw new Error(`Unexpected request: ${url.pathname}`);
    });
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsUsageActivityPanel accessToken="token-1" context={projectMemberContext} />);

    expect(await screen.findByText("2026-05-15")).toBeInTheDocument();
    await waitFor(() => {
      expect(
        mockFetch.mock.calls.some(([requestUrl]) => {
          const url = new URL(String(requestUrl), "http://proxy.test");
          return (
            url.pathname === "/cavadalabs/projects/daily/activity" &&
            url.searchParams.get("project_ids") === "project-1" &&
            url.searchParams.get("company_ids") === null
          );
        }),
      ).toBe(true);
      expect(
        mockFetch.mock.calls.some(([requestUrl]) => {
          const url = new URL(String(requestUrl), "http://proxy.test");
          return url.pathname === "/cavadalabs/companies/daily/activity";
        }),
      ).toBe(false);
    });
  });

  it("should render Project ledger-native usage without running repair", async () => {
    const mockFetch = vi.fn((input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://proxy.test");
      if (url.pathname === "/cavadalabs/projects/daily/activity") {
        return Promise.resolve(jsonResponse(activityResponse()));
      }
      if (url.pathname === "/cavadalabs/projects/usage/diagnostics") {
        return Promise.resolve(jsonResponse(diagnosticsResponse("none", "project")));
      }
      throw new Error(`Unexpected request: ${url.pathname}`);
    });
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsUsageActivityPanel accessToken="token-1" context={projectOnlyContext} />);

    expect(await screen.findByText("2026-05-15")).toBeInTheDocument();
    expect((await screen.findAllByText("$0.4200")).length).toBeGreaterThan(0);

    await waitFor(() => {
      expect(
        mockFetch.mock.calls.some(([requestUrl]) => {
          const url = new URL(String(requestUrl), "http://proxy.test");
          return (
            url.pathname === "/cavadalabs/projects/daily/activity" &&
            url.searchParams.get("project_ids") === "project-1" &&
            url.searchParams.get("company_ids") === null
          );
        }),
      ).toBe(true);
      expect(
        mockFetch.mock.calls.some(([requestUrl]) => {
          const url = new URL(String(requestUrl), "http://proxy.test");
          return url.pathname.includes("/usage/repair");
        }),
      ).toBe(false);
    });
  });

  it("should run scoped Company repair from empty usage diagnostics and refresh activity", async () => {
    const mockFetch = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://proxy.test");
      if (url.pathname === "/cavadalabs/companies/daily/activity") {
        const dailyCalls = mockFetch.mock.calls.filter(([requestUrl]) => {
          const request = new URL(String(requestUrl), "http://proxy.test");
          return request.pathname === "/cavadalabs/companies/daily/activity";
        }).length;
        return Promise.resolve(jsonResponse(dailyCalls === 1 ? emptyActivityResponse : activityResponse()));
      }
      if (url.pathname === "/cavadalabs/companies/usage/diagnostics") {
        const diagnosticsCalls = mockFetch.mock.calls.filter(([requestUrl]) => {
          const request = new URL(String(requestUrl), "http://proxy.test");
          return request.pathname === "/cavadalabs/companies/usage/diagnostics";
        }).length;
        return Promise.resolve(
          jsonResponse(
            diagnosticsCalls === 1
              ? diagnosticsResponse("run_scoped_backfill", "company", "company-1", {
                  diagnostics: [
                    {
                      key_metadata_spend_logs: 2,
                      legacy_keys_missing_metadata: 1,
                      legacy_key_spend_logs: 2,
                    },
                  ],
                })
              : diagnosticsResponse(),
          ),
        );
      }
      if (url.pathname === "/cavadalabs/companies/usage/repair") {
        expect(init?.method).toBe("POST");
        expect(JSON.parse(String(init?.body))).toMatchObject({
          company_ids: ["company-1"],
        });
        return Promise.resolve(
          jsonResponse({
            entity_type: "company",
            entity_ids: ["company-1"],
            attempted: true,
            repaired: true,
            scoped_spend_logs: 2,
            processed_spend_logs: 2,
            batches: 1,
            diagnostics: diagnosticsResponse().diagnostics,
            migration_name: "20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata",
            migration_command: "uv run prisma migrate deploy",
          }),
        );
      }
      throw new Error(`Unexpected request: ${url.pathname}`);
    });
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsUsageActivityPanel accessToken="token-1" context={companyContext} />);

    expect(await screen.findByText("Company usage can be repaired")).toBeInTheDocument();
    expect(screen.getByText(/Spend exists for this Company\/Project/)).toBeInTheDocument();
    expect(screen.getByText("Key metadata rows: 2")).toBeInTheDocument();
    expect(screen.getByText("Legacy keys missing metadata: 1")).toBeInTheDocument();
    expect(screen.getByText("Legacy key spend rows: 2")).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /run scoped backfill/i }));
    });

    await waitFor(() => {
      expect(
        mockFetch.mock.calls.some(([requestUrl]) => {
          const url = new URL(String(requestUrl), "http://proxy.test");
          return url.pathname === "/cavadalabs/companies/usage/repair";
        }),
      ).toBe(true);
    });
    expect(await screen.findByText("2026-05-15")).toBeInTheDocument();
    expect((await screen.findAllByText("$0.4200")).length).toBeGreaterThan(0);
  });

  it("should preview scoped Company backfill without applying ledger writes", async () => {
    const mockFetch = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://proxy.test");
      if (url.pathname === "/cavadalabs/companies/daily/activity") {
        return Promise.resolve(jsonResponse(emptyActivityResponse));
      }
      if (url.pathname === "/cavadalabs/companies/usage/diagnostics") {
        return Promise.resolve(jsonResponse(diagnosticsResponse("run_scoped_backfill")));
      }
      if (url.pathname === "/cavadalabs/companies/usage/repair") {
        expect(init?.method).toBe("POST");
        expect(JSON.parse(String(init?.body))).toMatchObject({
          company_ids: ["company-1"],
          dry_run: true,
        });
        return Promise.resolve(
          jsonResponse({
            entity_type: "company",
            entity_ids: ["company-1"],
            attempted: true,
            repaired: false,
            dry_run: true,
            scoped_spend_logs: 3,
            processed_spend_logs: 0,
            batches: 0,
            message: "Dry run completed.",
            diagnostics: diagnosticsResponse("run_scoped_backfill").diagnostics,
            migration_name: "20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata",
            migration_command: "uv run prisma migrate deploy",
          }),
        );
      }
      throw new Error(`Unexpected request: ${url.pathname}`);
    });
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsUsageActivityPanel accessToken="token-1" context={companyContext} />);

    expect(await screen.findByText("Company usage can be repaired")).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /preview scoped backfill/i }));
    });

    expect(await screen.findByText("Scoped backfill preview")).toBeInTheDocument();
    expect(screen.getByText(/3 attributable SpendLogs match this Company\/Project scope/i)).toBeInTheDocument();
    await waitFor(() => {
      const dailyCalls = mockFetch.mock.calls.filter(([requestUrl]) => {
        const url = new URL(String(requestUrl), "http://proxy.test");
        return url.pathname === "/cavadalabs/companies/daily/activity";
      });
      expect(dailyCalls.length).toBe(1);
    });
  });

  it("should not offer scoped repair CTA to Company viewers", async () => {
    const mockFetch = vi.fn((input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://proxy.test");
      if (url.pathname === "/cavadalabs/companies/daily/activity") {
        return Promise.resolve(jsonResponse(emptyActivityResponse));
      }
      if (url.pathname === "/cavadalabs/companies/usage/diagnostics") {
        return Promise.resolve(jsonResponse(diagnosticsResponse("run_scoped_backfill")));
      }
      throw new Error(`Unexpected request: ${url.pathname}`);
    });
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsUsageActivityPanel accessToken="token-1" context={companyViewerContext} />);

    expect(await screen.findByText("Company usage can be repaired")).toBeInTheDocument();
    expect(screen.getByText("Repair access: Company/Project admin required")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /preview scoped backfill/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run scoped backfill/i })).not.toBeInTheDocument();
    await waitFor(() => {
      expect(
        mockFetch.mock.calls.some(([requestUrl]) => {
          const url = new URL(String(requestUrl), "http://proxy.test");
          return url.pathname.includes("/usage/repair");
        }),
      ).toBe(false);
    });
  });

  it("should run scoped Project repair with current filters and refresh usage", async () => {
    const mockFetch = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://proxy.test");
      if (url.pathname === "/cavadalabs/projects/daily/activity") {
        const dailyCalls = mockFetch.mock.calls.filter(([requestUrl]) => {
          const request = new URL(String(requestUrl), "http://proxy.test");
          return request.pathname === "/cavadalabs/projects/daily/activity";
        }).length;
        return Promise.resolve(jsonResponse(dailyCalls === 1 ? emptyActivityResponse : activityResponse()));
      }
      if (url.pathname === "/cavadalabs/projects/usage/diagnostics") {
        const diagnosticsCalls = mockFetch.mock.calls.filter(([requestUrl]) => {
          const request = new URL(String(requestUrl), "http://proxy.test");
          return request.pathname === "/cavadalabs/projects/usage/diagnostics";
        }).length;
        return Promise.resolve(
          jsonResponse(
            diagnosticsCalls === 1
              ? diagnosticsResponse("run_scoped_backfill", "project")
              : diagnosticsResponse("none", "project"),
          ),
        );
      }
      if (url.pathname === "/cavadalabs/projects/usage/repair") {
        expect(init?.method).toBe("POST");
        expect(JSON.parse(String(init?.body))).toMatchObject({
          project_ids: ["project-1"],
          model: "openai/gpt-4.1",
          provider: "openai",
          api_key: "hashed-key",
        });
        return Promise.resolve(
          jsonResponse({
            entity_type: "project",
            entity_ids: ["project-1"],
            attempted: true,
            repaired: true,
            scoped_spend_logs: 1,
            processed_spend_logs: 1,
            batches: 1,
            diagnostics: diagnosticsResponse("none", "project").diagnostics,
            migration_name: "20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata",
            migration_command: "uv run prisma migrate deploy",
          }),
        );
      }
      throw new Error(`Unexpected request: ${url.pathname}`);
    });
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsUsageActivityPanel accessToken="token-1" context={projectOnlyContext} />);

    expect(await screen.findByText("Project usage can be repaired")).toBeInTheDocument();
    await act(async () => {
      fireEvent.change(screen.getByLabelText("Provider filter"), { target: { value: "openai" } });
      fireEvent.change(screen.getByLabelText("Model filter"), { target: { value: "openai/gpt-4.1" } });
      fireEvent.change(screen.getByLabelText("API key hash filter"), { target: { value: "hashed-key" } });
      fireEvent.click(screen.getByRole("button", { name: /run scoped backfill/i }));
    });

    await waitFor(() => {
      expect(
        mockFetch.mock.calls.some(([requestUrl]) => {
          const url = new URL(String(requestUrl), "http://proxy.test");
          return url.pathname === "/cavadalabs/projects/usage/repair";
        }),
      ).toBe(true);
    });
    expect(await screen.findByText("2026-05-15")).toBeInTheDocument();
  });

  it("should use readiness checks when daily usage is empty and scoped repair is available", async () => {
    const mockFetch = vi.fn((input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://proxy.test");
      if (url.pathname === "/cavadalabs/companies/daily/activity") {
        return Promise.resolve(jsonResponse(emptyActivityResponse));
      }
      if (url.pathname === "/cavadalabs/companies/usage/diagnostics") {
        return Promise.resolve(
          jsonResponse(
            diagnosticsResponse("run_scoped_backfill", "company", "company-1", {
              readiness_checks: [
                {
                  code: "usage_schema",
                  status: "ready",
                  message: "Schema ready.",
                },
                {
                  code: "repair_status",
                  status: "action_required",
                  message: "Scoped repair can copy attributable SpendLogs.",
                  entity_type: "company",
                  entity_id: "company-1",
                  recommended_action: "run_scoped_backfill",
                  details: {
                    scoped_spend_logs: 2,
                    missing_ledger_rows: 2,
                  },
                },
              ],
            }),
          ),
        );
      }
      throw new Error(`Unexpected request: ${url.pathname}`);
    });
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsUsageActivityPanel accessToken="token-1" context={companyContext} />);

    expect(await screen.findByText("Company usage can be repaired")).toBeInTheDocument();
    expect(screen.getByText("Missing ledger rows: 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /preview scoped backfill/i })).toBeInTheDocument();
    expect(screen.queryByText(/organization/i)).not.toBeInTheDocument();
  });

  it("should not offer repair when diagnostics report no attributable spend", async () => {
    const mockFetch = vi.fn((input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://proxy.test");
      if (url.pathname === "/cavadalabs/companies/daily/activity") {
        return Promise.resolve(jsonResponse(emptyActivityResponse));
      }
      if (url.pathname === "/cavadalabs/companies/usage/diagnostics") {
        return Promise.resolve(jsonResponse(diagnosticsResponse("no_attributable_spend")));
      }
      throw new Error(`Unexpected request: ${url.pathname}`);
    });
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsUsageActivityPanel accessToken="token-1" context={companyContext} />);

    expect(await screen.findByText("No Company-attributable usage")).toBeInTheDocument();
    expect(screen.getByText(/No ledger rows, SpendLogs metadata, key metadata/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run scoped backfill/i })).not.toBeInTheDocument();
    await waitFor(() => {
      expect(
        mockFetch.mock.calls.some(([requestUrl]) => {
          const url = new URL(String(requestUrl), "http://proxy.test");
          return url.pathname.includes("/usage/repair");
        }),
      ).toBe(false);
    });
  });

  it("should show migration command when usage schema is missing", async () => {
    const mockFetch = vi.fn((input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://proxy.test");
      if (url.pathname === "/cavadalabs/companies/daily/activity") {
        return Promise.resolve(
          jsonResponse(
            {
              detail: {
                error: "CavadaLabs usage schema is missing or incomplete.",
                schema_status: "missing_schema",
                migration_status: "schema_missing",
                migration_command: "uv run prisma migrate deploy",
              },
            },
            false,
          ),
        );
      }
      if (url.pathname === "/cavadalabs/companies/usage/diagnostics") {
        return Promise.resolve(
          jsonResponse(
            diagnosticsResponse("run_migration_backfill", "company", "company-1", {
              schema_status: "missing_schema",
              migration_status: "schema_missing",
              missing_schema: ["CavadaLabs_RequestLedgerTable.company_id"],
              diagnostics: [
                {
                  status: "backfill_required",
                  recommended_action: "run_migration_backfill",
                  missing_schema: ["CavadaLabs_RequestLedgerTable.company_id"],
                },
              ],
            }),
          ),
        );
      }
      throw new Error(`Unexpected request: ${url.pathname}`);
    });
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsUsageActivityPanel accessToken="token-1" context={companyContext} />);

    expect(await screen.findByText("CavadaLabs usage schema is not ready")).toBeInTheDocument();
    expect(screen.getByText("uv run prisma migrate deploy")).toBeInTheDocument();
    expect(screen.getByText("Missing schema: CavadaLabs_RequestLedgerTable.company_id")).toBeInTheDocument();
    expect(screen.queryByText("CavadaLabs usage schema is missing or incomplete.")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run scoped backfill/i })).not.toBeInTheDocument();
  });

  it("should not offer scoped repair when diagnostics report missing schema", async () => {
    const mockFetch = vi.fn((input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://proxy.test");
      if (url.pathname === "/cavadalabs/companies/daily/activity") {
        return Promise.resolve(jsonResponse(emptyActivityResponse));
      }
      if (url.pathname === "/cavadalabs/companies/usage/diagnostics") {
        return Promise.resolve(
          jsonResponse(
            diagnosticsResponse("run_scoped_backfill", "company", "company-1", {
              schema_status: "missing_schema",
              migration_status: "schema_missing",
              missing_schema: ["LiteLLM_SpendLogs.metadata"],
            }),
          ),
        );
      }
      throw new Error(`Unexpected request: ${url.pathname}`);
    });
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsUsageActivityPanel accessToken="token-1" context={companyContext} />);

    expect(await screen.findByText("CavadaLabs usage schema is not ready")).toBeInTheDocument();
    expect(screen.getByText("uv run prisma migrate deploy")).toBeInTheDocument();
    expect(screen.getByText("Missing schema: LiteLLM_SpendLogs.metadata")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /preview scoped backfill/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run scoped backfill/i })).not.toBeInTheDocument();
  });

  it("should explain restrictive filters without offering scoped repair", async () => {
    const mockFetch = vi.fn((input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://proxy.test");
      if (url.pathname === "/cavadalabs/companies/daily/activity") {
        return Promise.resolve(jsonResponse(emptyActivityResponse));
      }
      if (url.pathname === "/cavadalabs/companies/usage/diagnostics") {
        return Promise.resolve(
          jsonResponse(
            diagnosticsResponse("none", "company", "company-1", {
              diagnostics: [
                {
                  status: "filters_exclude_usage",
                  ledger_rows: 0,
                  attributable_spend_logs: 0,
                  unfiltered_attributable_spend_logs: 2,
                  filters_exclude_usage: true,
                  message: "Filters exclude attributable spend.",
                },
              ],
            }),
          ),
        );
      }
      throw new Error(`Unexpected request: ${url.pathname}`);
    });
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsUsageActivityPanel accessToken="token-1" context={companyContext} />);

    expect(await screen.findByText("Company usage is outside the current filters")).toBeInTheDocument();
    expect(screen.getByText(/model\/provider\/API key filters exclude it/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run scoped backfill/i })).not.toBeInTheDocument();
  });

  it("should show authorization errors instead of an empty Project usage state", async () => {
    const mockFetch = vi.fn((input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://proxy.test");
      if (url.pathname === "/cavadalabs/projects/daily/activity") {
        return Promise.resolve(
          jsonResponse(
            {
              detail: {
                error: "User is not authorized to view this Project usage scope.",
              },
            },
            false,
          ),
        );
      }
      if (url.pathname === "/cavadalabs/projects/usage/diagnostics") {
        return Promise.resolve(
          jsonResponse(
            {
              detail: {
                error: "Project does not belong to an authorized Company scope.",
              },
            },
            false,
          ),
        );
      }
      throw new Error(`Unexpected request: ${url.pathname}`);
    });
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsUsageActivityPanel accessToken="token-1" context={projectOnlyContext} />);

    expect(await screen.findByText("Cannot load Project usage for this scope")).toBeInTheDocument();
    expect(screen.getByText("User is not authorized to view this Project usage scope.")).toBeInTheDocument();
    expect(screen.queryByText("No Project usage for this selection")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run scoped backfill/i })).not.toBeInTheDocument();
  });
});
