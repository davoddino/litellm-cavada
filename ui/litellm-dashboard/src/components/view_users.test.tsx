import React from "react";
import { act, render, waitFor, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ViewUserDashboard from "./view_users";
import * as Networking from "./networking";

// Mock the networking module
vi.mock("./networking", () => ({
  userListCall: vi.fn().mockResolvedValue({
    users: [
      {
        user_id: "user-1",
        user_email: "test@example.com",
        user_role: "Admin",
        spend: 100.5,
        max_budget: null,
        key_count: 2,
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T00:00:00Z",
        sso_user_id: null,
        budget_duration: null,
      },
    ],
    total: 1,
    page: 1,
    page_size: 25,
    total_pages: 1,
  }),
  userDeleteCall: vi.fn().mockResolvedValue({}),
  getPossibleUserRoles: vi.fn().mockResolvedValue({
    Admin: { ui_label: "Admin" },
    User: { ui_label: "User" },
  }),
  modelAvailableCall: vi.fn().mockResolvedValue({ data: [] }),
  invitationCreateCall: vi.fn().mockResolvedValue({}),
  userUpdateUserCall: vi.fn().mockResolvedValue({}),
  getProxyBaseUrl: vi.fn().mockReturnValue("http://localhost:4000"),
  getProxyUISettings: vi.fn().mockResolvedValue({
    PROXY_BASE_URL: null,
    PROXY_LOGOUT_URL: null,
    DEFAULT_TEAM_DISABLED: false,
    SSO_ENABLED: false,
  }),
  getInternalUserSettings: vi.fn().mockResolvedValue({}),
}));

vi.mock("./cavadalabs/keyContext", () => ({
  getCavadaLabsCompanyDisplayName: vi.fn((company) =>
    company.legal_name ? `${company.legal_name} (${company.company_id})` : company.company_id,
  ),
  getCavadaLabsProjectDisplayName: vi.fn((project) =>
    project.name ? `${project.name} (${project.project_id})` : project.project_id,
  ),
  useCavadaLabsKeyContextOptions: vi.fn().mockReturnValue({
    companies: [{ company_id: "company-1", legal_name: "Acme Corp" }],
    projects: [{ project_id: "project-1", company_id: "company-1", name: "Support" }],
    isLoading: false,
  }),
}));

// Mock NotificationsManager
vi.mock("./molecules/notifications_manager", () => ({
  default: {
    success: vi.fn(),
    fromBackend: vi.fn(),
  },
}));

const mockUserListCall = vi.mocked(Networking.userListCall);

const createQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });

describe("ViewUserDashboard", () => {
  const defaultProps = {
    accessToken: "test-token",
    token: "test-token",
    keys: null,
    userRole: "Admin",
    userID: "admin-user-id",
    teams: [],
    setKeys: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("should render the ViewUserDashboard component", async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ViewUserDashboard {...defaultProps} />
      </QueryClientProvider>,
    );

    // Wait for the component to load (it shows "Loading..." initially)
    await waitFor(() => {
      expect(screen.getByText("Users")).toBeInTheDocument();
    });

    // Check if main elements are rendered
    expect(screen.getByText("Users")).toBeInTheDocument();
    // Use getAllByText since "Default User Settings" appears multiple times
    const defaultUserSettingsTabs = screen.getAllByText("Default User Settings");
    expect(defaultUserSettingsTabs.length).toBeGreaterThan(0);
  });

  it("should show delete modal after clicking delete user button", async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ViewUserDashboard {...defaultProps} />
      </QueryClientProvider>,
    );

    // Wait for the component to load and the table to render
    await waitFor(() => {
      expect(screen.getByText("Users")).toBeInTheDocument();
    });

    // Wait for the user data to load
    await waitFor(() => {
      expect(screen.getAllByText("test@example.com").length).toBeGreaterThan(0);
    });

    // Initially, the delete modal should not be visible
    expect(screen.queryByText("Delete User?")).not.toBeInTheDocument();

    // Find the row containing the user email (use the first one which is in the table)
    // The email appears in both the table and potentially in modals, so get the first one from the table
    const userEmailCells = screen.getAllByText("test@example.com");
    const userEmailCell = userEmailCells[0]; // First occurrence is in the table
    const userRow = userEmailCell.closest("tr");
    expect(userRow).toBeInTheDocument();

    // Find clickable elements in the actions column (the last column)
    const actionCells = userRow?.querySelectorAll("td");
    const actionsCell = actionCells?.[actionCells.length - 1];
    expect(actionsCell).toBeInTheDocument();

    // Find the action container div with flex gap-2
    const actionContainer =
      actionsCell?.querySelector("div.flex.gap-2") ||
      Array.from(actionsCell?.querySelectorAll("div") || []).find(
        (div) => div.className.includes("flex") && div.className.includes("gap"),
      );

    expect(actionContainer).toBeInTheDocument();

    // Get all direct children of the action container
    // These should be Tooltip components wrapping Icon components
    const tooltipWrappers = Array.from(actionContainer!.children);
    expect(tooltipWrappers.length).toBeGreaterThanOrEqual(2);

    // The delete icon is the second tooltip wrapper (index 1)
    // Edit=0, Delete=1, Reset=2
    const deleteTooltipWrapper = tooltipWrappers[1] as HTMLElement;
    const clickableElement = deleteTooltipWrapper.querySelector("button, [role='button'], svg") as HTMLElement;

    expect(clickableElement).toBeInTheDocument();

    act(() => {
      fireEvent.click(clickableElement);
    });

    await waitFor(() => {
      expect(screen.getByText("Delete User?")).toBeInTheDocument();
    });

    expect(
      screen.getByText("Are you sure you want to delete this user? This action cannot be undone."),
    ).toBeInTheDocument();
    expect(screen.getByText("user-1")).toBeInTheDocument();
    const emailInstances = screen.getAllByText("test@example.com");
    expect(emailInstances.length).toBeGreaterThan(0);
  });

  it("should list users with CavadaLabs Company filter without sending legacy Organization scope", async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ViewUserDashboard
          {...defaultProps}
          userRole="internal_user_viewer"
          orgAdminOrgIds={[{ organization_id: "org-legacy", organization_alias: "Legacy Org" }]}
        />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(mockUserListCall).toHaveBeenCalled();
    });

    act(() => {
      fireEvent.click(screen.getByRole("button", { name: /^filters$/i }));
    });

    const companySelect = screen.getByRole("combobox", { name: /^company$/i });
    act(() => {
      fireEvent.mouseDown(companySelect);
    });

    await waitFor(() => {
      expect(screen.getByText("Acme Corp (company-1)")).toBeInTheDocument();
    });

    act(() => {
      fireEvent.click(screen.getByText("Acme Corp (company-1)"));
    });

    await waitFor(() => {
      expect(mockUserListCall).toHaveBeenCalledWith(
        "test-token",
        null,
        1,
        25,
        null,
        null,
        null,
        null,
        "created_at",
        "desc",
        null,
        ["company-1"],
        null,
      );
    });
  });
});
