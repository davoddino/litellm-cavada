import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import UserInfoView from "./user_info_view";

const mockTeamMemberAddCall = vi.fn();
const mockTeamMemberDeleteCall = vi.fn();
const mockTeamListCall = vi.fn();
const mockUserGetInfoV2 = vi.fn();
const mockTeamInfoCall = vi.fn();

const MOCK_USER_DATA = {
  user_id: "user-123",
  user_email: "test@example.com",
  user_alias: "Test Alias",
  user_role: "admin",
  spend: 0,
  max_budget: 100,
  models: [],
  budget_duration: "30d",
  budget_reset_at: null,
  metadata: {},
  created_at: "2025-01-01T00:00:00.000Z",
  updated_at: "2025-01-02T00:00:00.000Z",
  sso_user_id: null,
  teams: ["team-1", "team-2"],
};

const MOCK_USER_DATA_NO_TEAMS = {
  ...MOCK_USER_DATA,
  teams: [],
};

const MOCK_USER_DATA_CAVADA = {
  ...MOCK_USER_DATA,
  cavadalabs_company_memberships: [{ company_id: "company-1", role: "viewer" }],
  cavadalabs_project_memberships: [{ project_id: "project-1", role: "project_admin" }],
};

vi.mock("../networking", () => {
  return {
    userGetInfoV2: (...args: any[]) => mockUserGetInfoV2(...args),
    userDeleteCall: vi.fn(),
    userUpdateUserCall: vi.fn(),
    modelAvailableCall: vi.fn().mockResolvedValue({ data: [] }),
    invitationCreateCall: vi.fn(),
    teamInfoCall: (...args: any[]) => mockTeamInfoCall(...args),
    teamListCall: (...args: any[]) => mockTeamListCall(...args),
    teamMemberAddCall: (...args: any[]) => mockTeamMemberAddCall(...args),
    teamMemberDeleteCall: (...args: any[]) => mockTeamMemberDeleteCall(...args),
    getProxyBaseUrl: () => "https://litellm.test",
  };
});

describe("UserInfoView", () => {
  const defaultProps = {
    userId: "user-123",
    onClose: vi.fn(),
    accessToken: "test-token",
    userRole: null as string | null,
    possibleUIRoles: null,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockUserGetInfoV2.mockResolvedValue(MOCK_USER_DATA);
    mockTeamInfoCall.mockImplementation((_token: string, teamId: string) => {
      const teamMap: Record<string, any> = {
        "team-1": { team_id: "team-1", team_info: { team_alias: "Alpha Team" } },
        "team-2": { team_id: "team-2", team_info: { team_alias: "Beta Team" } },
        "team-3": { team_id: "team-3", team_info: { team_alias: "Gamma Team" } },
      };
      return Promise.resolve(teamMap[teamId] || { team_id: teamId, team_info: { team_alias: null } });
    });
    mockTeamListCall.mockResolvedValue([
      { team_id: "team-1", team_alias: "Alpha Team" },
      { team_id: "team-2", team_alias: "Beta Team" },
      { team_id: "team-3", team_alias: "Gamma Team" },
    ]);
    mockTeamMemberAddCall.mockResolvedValue({});
    mockTeamMemberDeleteCall.mockResolvedValue({});
  });

  it("should render the loading state", () => {
    render(<UserInfoView {...defaultProps} />);

    expect(screen.getByText("Loading user data...")).toBeInTheDocument();
  });

  it("should render the user email after loading", async () => {
    render(<UserInfoView {...defaultProps} />);

    const emails = await screen.findAllByText("test@example.com");
    expect(emails.length).toBeGreaterThan(0);
    expect(screen.queryByText("Loading user data...")).not.toBeInTheDocument();
  });

  it("should render the user alias after loading", async () => {
    render(<UserInfoView {...defaultProps} />);

    const aliases = await screen.findAllByText("Test Alias");
    expect(aliases.length).toBeGreaterThan(0);
  });

  it("should render teams in a table with team names", async () => {
    render(<UserInfoView {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Alpha Team")).toBeInTheDocument();
      expect(screen.getByText("Beta Team")).toBeInTheDocument();
    });
  });

  it("should render CavadaLabs Company and Project memberships instead of Teams in product context", async () => {
    mockUserGetInfoV2.mockResolvedValue(MOCK_USER_DATA_CAVADA);

    render(
      <UserInfoView
        {...defaultProps}
        userRole="proxy_admin"
        cavadalabsCompanies={[{ company_id: "company-1", legal_name: "ACME Spa" }]}
        cavadalabsProjects={[{ project_id: "project-1", company_id: "company-1", name: "Support" }]}
        showLiteLLMCompatibilityFields={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Company and Project Access")).toBeInTheDocument();
    });
    expect(screen.getByText("ACME Spa (company-1)")).toBeInTheDocument();
    expect(screen.getByText("Support (project-1)")).toBeInTheDocument();
    expect(screen.getByText("Viewer")).toBeInTheDocument();
    expect(screen.getByText("Project Admin")).toBeInTheDocument();
    expect(screen.queryByText("Teams")).not.toBeInTheDocument();
    expect(screen.queryByText("Add Team")).not.toBeInTheDocument();
    expect(screen.queryByText("Alpha Team")).not.toBeInTheDocument();
    expect(mockTeamInfoCall).not.toHaveBeenCalled();
  });

  it("should keep Teams hidden for empty CavadaLabs product context", async () => {
    render(
      <UserInfoView
        userId="user-123"
        onClose={vi.fn()}
        accessToken="test-token"
        userRole="proxy_admin"
        possibleUIRoles={null}
        cavadalabsCompanies={[]}
        cavadalabsProjects={[]}
        showLiteLLMCompatibilityFields={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Company and Project Access")).toBeInTheDocument();
    });

    expect(screen.getByText("No Company or Project access")).toBeInTheDocument();
    expect(screen.queryByText("Teams")).not.toBeInTheDocument();
    expect(screen.queryByText("Add Team")).not.toBeInTheDocument();
    expect(mockTeamInfoCall).not.toHaveBeenCalled();
  });

  it("should close legacy Team modals when switching into CavadaLabs product context", async () => {
    const user = userEvent.setup();
    const { rerender } = render(
      <UserInfoView {...defaultProps} userRole="proxy_admin" showLiteLLMCompatibilityFields={true} />,
    );

    await waitFor(() => {
      expect(screen.getByText("Add Team")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Add Team"));

    await waitFor(() => {
      expect(screen.getByText("Add User to Team")).toBeInTheDocument();
    });

    rerender(
      <UserInfoView
        {...defaultProps}
        userRole="proxy_admin"
        cavadalabsCompanies={[]}
        cavadalabsProjects={[]}
        showLiteLLMCompatibilityFields={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Company and Project Access")).toBeInTheDocument();
    });

    expect(screen.queryByText("Add User to Team")).not.toBeInTheDocument();
    expect(screen.queryByText("Add Team")).not.toBeInTheDocument();
  });

  it("should show 'No teams' when user has no teams", async () => {
    mockUserGetInfoV2.mockResolvedValue(MOCK_USER_DATA_NO_TEAMS);
    render(<UserInfoView {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("No teams")).toBeInTheDocument();
    });
  });

  it("should show Add Team button for proxy admins", async () => {
    render(<UserInfoView {...defaultProps} userRole="proxy_admin" />);

    await waitFor(() => {
      expect(screen.getByText("Add Team")).toBeInTheDocument();
    });
  });

  it("should not show Add Team button for non-proxy-admins", async () => {
    render(<UserInfoView {...defaultProps} userRole="internal_user" />);

    await waitFor(() => {
      expect(screen.getByText("Alpha Team")).toBeInTheDocument();
    });
    expect(screen.queryByText("Add Team")).not.toBeInTheDocument();
  });

  it("should show delete buttons for proxy admins", async () => {
    render(<UserInfoView {...defaultProps} userRole="proxy_admin" />);

    await waitFor(() => {
      expect(screen.getByText("Alpha Team")).toBeInTheDocument();
    });
    // Should have the Actions column header
    expect(screen.getByText("Actions")).toBeInTheDocument();
  });

  it("should not show delete buttons for non-proxy-admins", async () => {
    render(<UserInfoView {...defaultProps} userRole="internal_user" />);

    await waitFor(() => {
      expect(screen.getByText("Alpha Team")).toBeInTheDocument();
    });
    expect(screen.queryByText("Actions")).not.toBeInTheDocument();
  });

  it("should open the add team modal when Add Team is clicked", async () => {
    const user = userEvent.setup();
    render(<UserInfoView {...defaultProps} userRole="proxy_admin" />);

    await waitFor(() => {
      expect(screen.getByText("Add Team")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Add Team"));

    await waitFor(() => {
      expect(screen.getByText("Add User to Team")).toBeInTheDocument();
    });
    expect(mockTeamListCall).toHaveBeenCalledWith("test-token", null);
  });

  it("should open remove confirmation modal when delete is clicked", async () => {
    const user = userEvent.setup();
    render(<UserInfoView {...defaultProps} userRole="proxy_admin" />);

    await waitFor(() => {
      expect(screen.getByText("Alpha Team")).toBeInTheDocument();
    });

    // Find the row with Alpha Team and click its delete button
    const alphaRow = screen.getByText("Alpha Team").closest("tr")!;
    const deleteButton = within(alphaRow).getByRole("button");
    await user.click(deleteButton);

    await waitFor(() => {
      expect(screen.getByText("Remove from Team")).toBeInTheDocument();
      expect(screen.getByText(/Removing this user from the team will also delete any keys/)).toBeInTheDocument();
    });
  });

  it("should call teamMemberDeleteCall when remove is confirmed", async () => {
    const user = userEvent.setup();
    render(<UserInfoView {...defaultProps} userRole="proxy_admin" />);

    await waitFor(() => {
      expect(screen.getByText("Alpha Team")).toBeInTheDocument();
    });

    // Click delete on Alpha Team
    const alphaRow = screen.getByText("Alpha Team").closest("tr")!;
    const deleteButton = within(alphaRow).getByRole("button");
    await user.click(deleteButton);

    // Confirm deletion
    await waitFor(() => {
      expect(screen.getByText("Remove from Team")).toBeInTheDocument();
    });

    // The DeleteResourceModal's OK button has text "Delete" - find it within the modal
    const modal = screen.getByText("Remove from Team").closest(".ant-modal") as HTMLElement;
    const deleteConfirmButton = within(modal).getByRole("button", { name: /delete/i });
    await user.click(deleteConfirmButton);

    await waitFor(() => {
      expect(mockTeamMemberDeleteCall).toHaveBeenCalledWith("test-token", "team-1", {
        role: "user",
        user_id: "user-123",
      });
    });
  });
});
