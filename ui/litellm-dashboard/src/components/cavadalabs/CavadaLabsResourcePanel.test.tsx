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
});
