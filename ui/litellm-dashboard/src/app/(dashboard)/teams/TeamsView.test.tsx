import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TeamsView from "./TeamsView";
import { v2TeamListCall } from "@/components/networking";

const routerPush = vi.hoisted(() => vi.fn());
interface MockCavadaLabsContext {
  companies: any[];
  projects: any[];
  isLoading: boolean;
  errorDetail: null;
  contextKnown?: boolean;
  isCavadaLabsProductContext?: boolean;
}

const cavadaLabsContext = vi.hoisted(() => ({
  value: {
    companies: [] as any[],
    projects: [] as any[],
    isLoading: false,
    errorDetail: null,
  } as MockCavadaLabsContext,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: routerPush,
  }),
}));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({
    invalidateQueries: vi.fn(),
  }),
}));

vi.mock("@tremor/react", () => {
  const Button = React.forwardRef<HTMLButtonElement, any>(({ children, ...props }, ref) =>
    React.createElement("button", { ...props, ref }, children),
  );
  Button.displayName = "MockTremorButton";

  return {
    Button,
    Card: ({ children }: any) => <div>{children}</div>,
    Col: ({ children }: any) => <div>{children}</div>,
    Grid: ({ children }: any) => <div>{children}</div>,
    TabPanel: ({ children }: any) => <section>{children}</section>,
    Text: ({ children }: any) => <p>{children}</p>,
  };
});

vi.mock("antd", () => ({
  Form: {
    useForm: () => [{}],
  },
}));

vi.mock("@/app/(dashboard)/hooks/organizations/useOrganizations", () => ({
  organizationKeys: {
    all: ["organizations"],
  },
}));

vi.mock("@/components/networking", () => ({
  serverRootPath: "",
  teamDeleteCall: vi.fn(),
  v2TeamListCall: vi.fn(),
}));

vi.mock("@/components/common_components/fetch_teams", () => ({
  fetchTeams: vi.fn(),
}));

vi.mock("@/components/team/TeamInfo", () => ({
  default: () => <div>TeamInfo legacy surface</div>,
}));

vi.mock("@/components/TeamSSOSettings", () => ({
  default: () => <div>Team SSO settings</div>,
}));

vi.mock("@/components/team/available_teams", () => ({
  default: () => <div>Available teams panel</div>,
}));

vi.mock("@/utils/roles", () => ({
  isAdminRole: (role: string) => role === "Admin",
}));

vi.mock("@/utils/dataUtils", () => ({
  updateExistingKeys: (_team: any, data: any) => data,
}));

vi.mock("@/app/(dashboard)/teams/components/TeamsHeaderTabs", () => ({
  default: ({ children }: any) => <div>{children}</div>,
}));

vi.mock("@/app/(dashboard)/teams/components/TeamsFilters", () => ({
  default: ({ isCavadaLabsProductContext, onChange }: any) => (
    <div data-testid="teams-filters" data-cavadalabs={String(isCavadaLabsProductContext)}>
      Teams filters
      <button
        onClick={() =>
          onChange({
            cavadalabs_company_id: "company-1",
            cavadalabs_project_id: "project-1",
          })
        }
      >
        Apply Cavada Project Filter
      </button>
    </div>
  ),
}));

vi.mock("@/app/(dashboard)/teams/hooks/useFetchTeams", () => ({
  default: () => ({
    lastRefreshed: "now",
    onRefreshClick: vi.fn(),
  }),
}));

vi.mock("@/app/(dashboard)/teams/components/TeamsTable/TeamsTable", () => ({
  default: ({ isCavadaLabsProductContext }: any) => (
    <div data-testid="teams-table" data-cavadalabs={String(isCavadaLabsProductContext)}>
      Teams table
    </div>
  ),
}));

vi.mock("@/app/(dashboard)/teams/components/modals/DeleteTeamModal", () => ({
  default: () => <div>Delete team modal</div>,
}));

vi.mock("@/app/(dashboard)/teams/components/modals/CreateTeamModal", () => ({
  default: ({ isTeamModalVisible }: any) => (isTeamModalVisible ? <div>Create team modal</div> : null),
}));

vi.mock("@/components/cavadalabs/keyContext", () => ({
  useCavadaLabsKeyContextOptions: () => cavadaLabsContext.value,
}));

const renderTeamsView = (overrides: Partial<Parameters<typeof TeamsView>[0]> = {}) => {
  const props = {
    teams: [],
    accessToken: "token",
    setTeams: vi.fn(),
    userID: "user-1",
    userRole: "internal_user",
    organizations: [],
    ...overrides,
  };

  render(<TeamsView {...props} />);
};

describe("TeamsView", () => {
  beforeEach(() => {
    routerPush.mockReset();
    vi.mocked(v2TeamListCall).mockReset();
    vi.mocked(v2TeamListCall).mockResolvedValue({ teams: [] } as any);
    cavadaLabsContext.value = {
      companies: [],
      projects: [],
      isLoading: false,
      errorDetail: null,
    };
  });

  it("should render the CavadaLabs Project list surface", () => {
    cavadaLabsContext.value = {
      companies: [{ company_id: "company-1", legal_name: "Acme", cavadalabs_can_manage: true }],
      projects: [],
      isLoading: false,
      errorDetail: null,
    };

    renderTeamsView();

    expect(screen.getByText("Project runtime and membership")).toBeInTheDocument();
    expect(screen.getByTestId("teams-filters")).toHaveAttribute("data-cavadalabs", "true");
    expect(screen.getByTestId("teams-table")).toHaveAttribute("data-cavadalabs", "true");
    expect(screen.queryByText("Organization")).not.toBeInTheDocument();
  });

  it("should render CavadaLabs Project surface with empty product options", () => {
    cavadaLabsContext.value = {
      companies: [],
      projects: [],
      isLoading: false,
      errorDetail: null,
      contextKnown: true,
      isCavadaLabsProductContext: true,
    };

    renderTeamsView({ userRole: "internal_user_viewer" });

    expect(screen.getByText("Project runtime and membership")).toBeInTheDocument();
    expect(screen.getByTestId("teams-filters")).toHaveAttribute("data-cavadalabs", "true");
    expect(screen.getByTestId("teams-table")).toHaveAttribute("data-cavadalabs", "true");
    expect(screen.queryByRole("button", { name: "+ Create New Team" })).not.toBeInTheDocument();
    expect(screen.queryByText("Organization")).not.toBeInTheDocument();
  });

  it("should allow a CavadaLabs manager to create a Project without legacy Organization admin role", async () => {
    const user = userEvent.setup();
    cavadaLabsContext.value = {
      companies: [{ company_id: "company-1", legal_name: "Acme", cavadalabs_can_manage: true }],
      projects: [],
      isLoading: false,
      errorDetail: null,
    };

    renderTeamsView({ userRole: "internal_user" });

    await user.click(screen.getByRole("button", { name: "+ Create New Project" }));

    expect(routerPush).toHaveBeenCalledWith("/cavadalabs/projects");
    expect(screen.queryByRole("button", { name: "+ Create New Team" })).not.toBeInTheDocument();
  });

  it("should not derive CavadaLabs Project management from legacy Organization admin role", () => {
    cavadaLabsContext.value = {
      companies: [{ company_id: "company-1", legal_name: "Acme", cavadalabs_can_manage: false }],
      projects: [],
      isLoading: false,
      errorDetail: null,
    };

    renderTeamsView({ userRole: "Org Admin" });

    expect(screen.queryByRole("button", { name: "+ Create New Project" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "+ Create New Team" })).not.toBeInTheDocument();
  });

  it("should keep legacy Team creation for non-Cavada Organization admins", async () => {
    const user = userEvent.setup();

    renderTeamsView({ userRole: "Org Admin" });

    await user.click(screen.getByRole("button", { name: "+ Create New Team" }));

    expect(screen.getByText("Create team modal")).toBeInTheDocument();
    expect(routerPush).not.toHaveBeenCalled();
  });

  it("should hide CavadaLabs Project management for viewer-only scope", () => {
    cavadaLabsContext.value = {
      companies: [{ company_id: "company-1", legal_name: "Acme", cavadalabs_can_manage: false }],
      projects: [{ project_id: "project-1", company_id: "company-1", name: "Support", cavadalabs_can_manage: false }],
      isLoading: false,
      errorDetail: null,
    };

    renderTeamsView({ userRole: "internal_user_viewer" });

    expect(screen.queryByRole("button", { name: "+ Create New Project" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "+ Create New Team" })).not.toBeInTheDocument();
    expect(screen.queryByText("Organization")).not.toBeInTheDocument();
  });

  it("should filter CavadaLabs Projects by Company and Project without legacy Team scope", async () => {
    const user = userEvent.setup();
    cavadaLabsContext.value = {
      companies: [{ company_id: "company-1", legal_name: "Acme", cavadalabs_can_manage: true }],
      projects: [{ project_id: "project-1", company_id: "company-1", name: "Support", cavadalabs_can_manage: true }],
      isLoading: false,
      errorDetail: null,
    };

    renderTeamsView({ userRole: "internal_user" });

    await user.click(screen.getByRole("button", { name: "Apply Cavada Project Filter" }));

    expect(v2TeamListCall).toHaveBeenCalledWith(
      "token",
      null,
      null,
      null,
      null,
      1,
      10,
      "created_at",
      "desc",
      "company-1",
      "project-1",
    );
  });
});
