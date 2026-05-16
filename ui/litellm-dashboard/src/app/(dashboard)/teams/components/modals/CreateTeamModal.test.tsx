import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CreateTeamModal, { resolveCavadaLabsCompanyCompatibilityOrganizationId } from "./CreateTeamModal";
import { teamCreateCall } from "@/components/networking";

vi.mock("@/app/(dashboard)/hooks/useAuthorized", () => ({
  default: () => ({
    userId: "user-1",
    userRole: "Admin",
    accessToken: "token-1",
    premiumUser: true,
  }),
}));

vi.mock("@/components/key_team_helpers/fetch_available_models_team_key", () => ({
  fetchAvailableModelsForTeamOrKey: vi.fn().mockResolvedValue(["gpt-4"]),
  getModelDisplayName: (model: string) => model,
  unfurlWildcardModelsInList: (models: string[]) => models,
}));

vi.mock("@/components/networking", async () => {
  const actual = await vi.importActual<any>("@/components/networking");
  return {
    ...actual,
    fetchMCPAccessGroups: vi.fn().mockResolvedValue([]),
    getGuardrailsList: vi.fn().mockResolvedValue({ guardrails: [] }),
    getPoliciesList: vi.fn().mockResolvedValue({ policies: [] }),
    teamCreateCall: vi.fn(),
  };
});

vi.mock("@/components/vector_store_management/VectorStoreSelector", () => ({
  default: () => <div data-testid="vector-store-selector" />,
}));

vi.mock("@/components/mcp_server_management/MCPServerSelector", () => ({
  default: () => <div data-testid="mcp-server-selector" />,
}));

vi.mock("@/components/mcp_server_management/MCPToolPermissions", () => ({
  default: () => <div data-testid="mcp-tool-permissions" />,
}));

vi.mock("@/components/agent_management/AgentSelector", () => ({
  default: () => <div data-testid="agent-selector" />,
}));

vi.mock("@/components/SearchTools/SearchToolSelector", () => ({
  default: () => <div data-testid="search-tool-selector" />,
}));

vi.mock("@/components/common_components/PremiumLoggingSettings", () => ({
  default: () => <div data-testid="premium-logging-settings" />,
}));

vi.mock("@/components/common_components/ModelAliasManager", () => ({
  default: () => <div data-testid="model-alias-manager" />,
}));

const mockTeamCreateCall = vi.mocked(teamCreateCall);

const renderModal = ({
  cavadalabsCompanies = [
    {
      company_id: "company-1",
      legal_name: "Acme Spa",
      litellm_organization_id: "org-1",
    },
  ],
}: {
  cavadalabsCompanies?: any[];
} = {}) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <CreateTeamModal
        isTeamModalVisible
        handleOk={vi.fn()}
        handleCancel={vi.fn()}
        currentOrg={null}
        organizations={[
          {
            organization_id: "org-1",
            organization_alias: "Internal Org",
            models: ["gpt-4"],
          } as any,
        ]}
        cavadalabsCompanies={cavadalabsCompanies}
        teams={[]}
        setTeams={vi.fn()}
        modelAliases={{}}
        setModelAliases={vi.fn()}
        loggingSettings={[]}
        setLoggingSettings={vi.fn()}
        setIsTeamModalVisible={vi.fn()}
      />
    </QueryClientProvider>,
  );
};

describe("CreateTeamModal CavadaLabs tenant UX", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockTeamCreateCall.mockResolvedValue({
      team_id: "team-1",
      team_alias: "Support",
      organization_id: "org-1",
    });
  });

  it("should render Company selection without exposing Organization", async () => {
    renderModal();

    expect(await screen.findByRole("dialog", { name: /create project/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create project/i })).toBeInTheDocument();
    expect(await screen.findByRole("combobox", { name: /company/i })).toBeInTheDocument();
    expect(screen.getByText("Project Member Settings")).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: /organization/i })).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/organization/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: /create team/i })).not.toBeInTheDocument();
  });

  it("should submit Cavada company context with compatibility organization_id derived from selected company", async () => {
    const user = userEvent.setup();
    renderModal();

    await user.type(screen.getByTestId("team-name-input"), "Support");
    await user.click(screen.getByRole("combobox", { name: /company/i }));
    await user.click(screen.getByText("Acme Spa (company-1)"));
    await user.click(screen.getByTestId("create-team-submit"));

    await waitFor(() => {
      expect(mockTeamCreateCall).toHaveBeenCalledWith(
        "token-1",
        expect.objectContaining({
          team_alias: "Support",
          cavadalabs_company_id: "company-1",
          organization_id: "org-1",
        }),
      );
    });
  });

  it("should keep legacy Team labels when Cavada company context is unavailable", async () => {
    renderModal({ cavadalabsCompanies: [] });

    expect(await screen.findByRole("dialog", { name: /create team/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create team/i })).toBeInTheDocument();
    expect(screen.getByText("Team Member Settings")).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: /company/i })).not.toBeInTheDocument();
  });

  it("should reject companies without compatibility mapping", () => {
    expect(() =>
      resolveCavadaLabsCompanyCompatibilityOrganizationId("company-2", [
        {
          company_id: "company-2",
          legal_name: "No Mapping Inc",
          litellm_organization_id: null,
        },
      ]),
    ).toThrow("Company company-2 is missing its compatibility mapping");
  });
});
