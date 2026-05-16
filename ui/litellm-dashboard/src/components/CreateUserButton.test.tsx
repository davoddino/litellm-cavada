import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { CreateUserButton } from "./CreateUserButton";
import * as keyContext from "./cavadalabs/keyContext";
import * as networking from "./networking";
import NotificationsManager from "./molecules/notifications_manager";

vi.mock("./networking", () => ({
  userCreateCall: vi.fn(),
  modelAvailableCall: vi.fn().mockResolvedValue({ data: [] }),
  invitationCreateCall: vi.fn(),
  organizationMemberAddCall: vi.fn(),
  getProxyUISettings: vi.fn().mockResolvedValue({
    PROXY_BASE_URL: null,
    PROXY_LOGOUT_URL: null,
    DEFAULT_TEAM_DISABLED: false,
    SSO_ENABLED: false,
  }),
  getProxyBaseUrl: vi.fn().mockReturnValue("http://localhost"),
}));

vi.mock("./bulk_create_users_button", () => ({
  default: () => <div data-testid="bulk-create-users">Bulk Create Users</div>,
}));

vi.mock("./common_components/team_dropdown", () => ({
  default: () => (
    <select aria-label="Team">
      <option value="">No team</option>
    </select>
  ),
}));

vi.mock("@/app/(dashboard)/hooks/organizations/useOrganizations", () => ({
  useOrganizations: vi.fn().mockReturnValue({ data: [], isLoading: false }),
}));

vi.mock("./cavadalabs/keyContext", () => ({
  getCavadaLabsCompanyDisplayName: vi.fn((company) =>
    company.legal_name ? `${company.legal_name} (${company.company_id})` : company.company_id,
  ),
  getCavadaLabsProjectDisplayName: vi.fn((project) =>
    project.name ? `${project.name} (${project.project_id})` : project.project_id,
  ),
  useCavadaLabsKeyContextOptions: vi.fn(),
}));

const mockUserCreateCall = vi.mocked(networking.userCreateCall);
const mockInvitationCreateCall = vi.mocked(networking.invitationCreateCall);
const mockGetProxyUISettings = vi.mocked(networking.getProxyUISettings);
const mockOrganizationMemberAddCall = vi.mocked(networking.organizationMemberAddCall);
const mockUseCavadaLabsKeyContextOptions = vi.mocked(keyContext.useCavadaLabsKeyContextOptions);
const mockNotificationsManager = vi.mocked(NotificationsManager);

const createQueryClient = () =>
  new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });

const defaultProps = {
  userID: "123",
  accessToken: "token",
  teams: [],
  possibleUIRoles: null as Record<string, Record<string, string>> | null,
};

function renderWithProviders(ui: React.ReactElement) {
  const qc = createQueryClient();
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("CreateUserButton", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetProxyUISettings.mockResolvedValue({
      PROXY_BASE_URL: null,
      PROXY_LOGOUT_URL: null,
      DEFAULT_TEAM_DISABLED: false,
      SSO_ENABLED: false,
    });
    mockUseCavadaLabsKeyContextOptions.mockReturnValue({
      companies: [],
      projects: [],
      isLoading: false,
    });
  });

  describe("rendering and visibility", () => {
    it("should render the create user form when embedded", () => {
      renderWithProviders(<CreateUserButton {...defaultProps} isEmbedded />);
      expect(screen.getByRole("button", { name: /create user/i })).toBeInTheDocument();
    });

    it("should render the invite user button when not embedded", async () => {
      renderWithProviders(<CreateUserButton {...defaultProps} />);
      await waitFor(() => {
        expect(screen.getByRole("button", { name: /\+ invite user/i })).toBeInTheDocument();
      });
    });

    it("should open the invite modal when invite user button is clicked", async () => {
      const user = userEvent.setup();
      renderWithProviders(<CreateUserButton {...defaultProps} />);
      await waitFor(() => {
        expect(screen.getByRole("button", { name: /\+ invite user/i })).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: /\+ invite user/i }));
      const dialog = screen.getByRole("dialog", { name: /invite user/i });
      expect(dialog).toBeInTheDocument();
      expect(within(dialog).getByRole("button", { name: /invite user/i })).toBeInTheDocument();
    });

    it("should display email invitations info message in embedded mode", () => {
      renderWithProviders(<CreateUserButton {...defaultProps} isEmbedded />);
      expect(screen.getByText("Email invitations")).toBeInTheDocument();
    });

    it("should display user role options when possibleUIRoles is provided", async () => {
      const possibleUIRoles = {
        proxy_admin: { ui_label: "Admin", description: "Full access" },
        proxy_user: { ui_label: "User", description: "Limited access" },
      };
      renderWithProviders(<CreateUserButton {...defaultProps} possibleUIRoles={possibleUIRoles} isEmbedded />);
      await userEvent.click(screen.getByRole("combobox", { name: /user role/i }));
      expect(screen.getByText("Admin")).toBeInTheDocument();
      expect(screen.getByText("User")).toBeInTheDocument();
    });

    it("should close modal when cancel is clicked in standalone mode", async () => {
      const user = userEvent.setup();
      renderWithProviders(<CreateUserButton {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /\+ invite user/i })).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: /\+ invite user/i }));
      expect(screen.getByRole("dialog", { name: /invite user/i })).toBeInTheDocument();

      const dialog = screen.getByRole("dialog", { name: /invite user/i });
      await user.click(within(dialog).getByRole("button", { name: /close/i }));
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  describe("embedded mode submission", () => {
    it("should call userCreateCall when form is submitted in embedded mode", async () => {
      const user = userEvent.setup();
      mockUserCreateCall.mockResolvedValue({ data: { user_id: "new-user-123" } });
      mockInvitationCreateCall.mockResolvedValue({
        id: "inv-1",
        user_id: "new-user-123",
        has_user_setup_sso: false,
      } as any);

      renderWithProviders(
        <CreateUserButton
          {...defaultProps}
          possibleUIRoles={{ proxy_user: { ui_label: "User", description: "" } }}
          isEmbedded
        />,
      );

      await user.type(screen.getByLabelText(/user email/i), "test@example.com");
      await user.click(screen.getByRole("combobox", { name: /user role/i }));
      await user.click(screen.getByText("User"));
      await user.click(screen.getByRole("button", { name: /create user/i }));

      await waitFor(() => {
        expect(mockUserCreateCall).toHaveBeenCalledWith(
          "token",
          null,
          expect.objectContaining({
            user_email: "test@example.com",
            user_role: "proxy_user",
          }),
        );
      });
    });

    it("should call onUserCreated callback when user is created in embedded mode", async () => {
      const user = userEvent.setup();
      const onUserCreated = vi.fn();
      mockUserCreateCall.mockResolvedValue({ data: { user_id: "new-user-456" } });

      renderWithProviders(
        <CreateUserButton
          {...defaultProps}
          onUserCreated={onUserCreated}
          possibleUIRoles={{ proxy_user: { ui_label: "User", description: "" } }}
          isEmbedded
        />,
      );

      await user.type(screen.getByLabelText(/user email/i), "embedded@example.com");
      await user.click(screen.getByRole("combobox", { name: /user role/i }));
      await user.click(screen.getByText("User"));
      await user.click(screen.getByRole("button", { name: /create user/i }));

      await waitFor(() => {
        expect(onUserCreated).toHaveBeenCalledWith("new-user-456");
      });
    });

    it("should show error notification when user creation fails", async () => {
      const user = userEvent.setup();
      mockUserCreateCall.mockRejectedValue({ response: { data: { detail: "Email already exists" } } });

      renderWithProviders(
        <CreateUserButton
          {...defaultProps}
          possibleUIRoles={{ proxy_user: { ui_label: "User", description: "" } }}
          isEmbedded
        />,
      );

      await user.type(screen.getByLabelText(/user email/i), "duplicate@example.com");
      await user.click(screen.getByRole("combobox", { name: /user role/i }));
      await user.click(screen.getByText("User"));
      await user.click(screen.getByRole("button", { name: /create user/i }));

      await waitFor(() => {
        expect(mockNotificationsManager.fromBackend).toHaveBeenCalledWith("Email already exists");
      });
    });

    it("should show info notification when making API call", async () => {
      const user = userEvent.setup();
      mockUserCreateCall.mockResolvedValue({ data: { user_id: "new-user" } });
      mockInvitationCreateCall.mockResolvedValue({
        id: "inv-3",
        user_id: "new-user",
        has_user_setup_sso: false,
      } as any);

      renderWithProviders(
        <CreateUserButton
          {...defaultProps}
          possibleUIRoles={{ proxy_user: { ui_label: "User", description: "" } }}
          isEmbedded
        />,
      );

      await user.type(screen.getByLabelText(/user email/i), "info@example.com");
      await user.click(screen.getByRole("combobox", { name: /user role/i }));
      await user.click(screen.getByText("User"));
      await user.click(screen.getByRole("button", { name: /create user/i }));

      await waitFor(() => {
        expect(mockNotificationsManager.info).toHaveBeenCalledWith("Making API Call");
      });
    });
  });

  describe("standalone mode submission", () => {
    it("should show success notification when user is created successfully in standalone mode", async () => {
      const user = userEvent.setup();
      mockUserCreateCall.mockResolvedValue({ data: { user_id: "new-user-789" } });
      mockInvitationCreateCall.mockResolvedValue({
        id: "inv-2",
        user_id: "new-user-789",
        has_user_setup_sso: false,
      } as any);

      renderWithProviders(
        <CreateUserButton {...defaultProps} possibleUIRoles={{ proxy_user: { ui_label: "User", description: "" } }} />,
      );

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /\+ invite user/i })).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: /\+ invite user/i }));

      const dialog = screen.getByRole("dialog", { name: /invite user/i });
      await user.type(within(dialog).getByLabelText(/user email/i), "standalone@example.com");
      await user.click(within(dialog).getByRole("combobox", { name: /global proxy role/i }));
      await user.click(screen.getByText("User"));
      await user.click(within(dialog).getByRole("button", { name: /invite user/i }));

      await waitFor(() => {
        expect(mockNotificationsManager.success).toHaveBeenCalledWith("API user Created");
      });
    });

    it("should show onboarding modal when user is created and SSO is disabled", async () => {
      const user = userEvent.setup();
      mockUserCreateCall.mockResolvedValue({ data: { user_id: "sso-user" } });
      mockInvitationCreateCall.mockResolvedValue({
        id: "inv-sso",
        user_id: "sso-user",
        has_user_setup_sso: false,
      } as any);

      renderWithProviders(
        <CreateUserButton {...defaultProps} possibleUIRoles={{ proxy_user: { ui_label: "User", description: "" } }} />,
      );

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /\+ invite user/i })).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: /\+ invite user/i }));

      const dialog = screen.getByRole("dialog", { name: /invite user/i });
      await user.type(within(dialog).getByLabelText(/user email/i), "sso@example.com");
      await user.click(within(dialog).getByRole("combobox", { name: /global proxy role/i }));
      await user.click(screen.getByText("User"));
      await user.click(within(dialog).getByRole("button", { name: /invite user/i }));

      await waitFor(() => {
        expect(mockInvitationCreateCall).toHaveBeenCalledWith("token", "sso-user");
      });
      await waitFor(() => {
        expect(mockNotificationsManager.success).toHaveBeenCalledWith("API user Created");
      });
    });
  });

  describe("company tenant assignment", () => {
    it("should render embedded CavadaLabs membership fields without exposing Team", () => {
      mockUseCavadaLabsKeyContextOptions.mockReturnValue({
        companies: [
          {
            company_id: "company-1",
            legal_name: "My Company",
            litellm_organization_id: "org-1",
          },
        ],
        projects: [
          {
            project_id: "project-1",
            company_id: "company-1",
            name: "Support",
            litellm_team_id: "team-1",
          },
        ],
        isLoading: false,
      });

      renderWithProviders(
        <CreateUserButton
          {...defaultProps}
          possibleUIRoles={{ proxy_user: { ui_label: "User", description: "" } }}
          isEmbedded
        />,
      );

      expect(screen.getByRole("combobox", { name: /^company$/i })).toBeInTheDocument();
      expect(screen.getByRole("combobox", { name: /^project$/i })).toBeInTheDocument();
      expect(screen.queryByRole("combobox", { name: /^team$/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("combobox", { name: /organization/i })).not.toBeInTheDocument();
    });

    it("should render Company assignment without exposing Organization in the invite form", async () => {
      mockUseCavadaLabsKeyContextOptions.mockReturnValue({
        companies: [
          {
            company_id: "company-1",
            legal_name: "My Company",
            litellm_organization_id: "org-1",
          },
        ],
        projects: [],
        isLoading: false,
      });

      const user = userEvent.setup();
      renderWithProviders(
        <CreateUserButton {...defaultProps} possibleUIRoles={{ proxy_user: { ui_label: "User", description: "" } }} />,
      );

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /\+ invite user/i })).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: /\+ invite user/i }));

      const dialog = screen.getByRole("dialog", { name: /invite user/i });
      expect(within(dialog).getByRole("combobox", { name: /^company$/i })).toBeInTheDocument();
      expect(within(dialog).queryByRole("combobox", { name: /^team$/i })).not.toBeInTheDocument();
      expect(within(dialog).queryByRole("combobox", { name: /organization/i })).not.toBeInTheDocument();
      expect(screen.queryByTestId("bulk-create-users")).not.toBeInTheDocument();
    });

    it("should filter Project choices by selected Company and send CavadaLabs memberships", async () => {
      mockUseCavadaLabsKeyContextOptions.mockReturnValue({
        companies: [
          {
            company_id: "company-1",
            legal_name: "My Company",
            litellm_organization_id: "org-1",
          },
          {
            company_id: "company-2",
            legal_name: "Other Company",
            litellm_organization_id: "org-2",
          },
        ],
        projects: [
          {
            project_id: "project-1",
            company_id: "company-1",
            name: "Support",
            litellm_team_id: "team-1",
          },
          {
            project_id: "project-2",
            company_id: "company-2",
            name: "Billing",
            litellm_team_id: "team-2",
          },
        ],
        isLoading: false,
      });

      const user = userEvent.setup();
      mockUserCreateCall.mockResolvedValue({ data: { user_id: "company-project-user" } });
      mockInvitationCreateCall.mockResolvedValue({
        id: "inv-company-project",
        user_id: "company-project-user",
        has_user_setup_sso: false,
      } as any);

      renderWithProviders(
        <CreateUserButton {...defaultProps} possibleUIRoles={{ proxy_user: { ui_label: "User", description: "" } }} />,
      );

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /\+ invite user/i })).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: /\+ invite user/i }));

      const dialog = screen.getByRole("dialog", { name: /invite user/i });
      await user.type(within(dialog).getByLabelText(/user email/i), "company-project@example.com");
      await user.click(within(dialog).getByRole("combobox", { name: /global proxy role/i }));
      await user.click(screen.getByText("User"));

      await user.click(within(dialog).getByRole("combobox", { name: /^company$/i }));
      await user.click(screen.getByText("My Company (company-1)"));

      await user.click(within(dialog).getByRole("combobox", { name: /^project$/i }));
      expect(screen.getByText("Support (project-1)")).toBeInTheDocument();
      expect(screen.queryByText("Billing (project-2)")).not.toBeInTheDocument();
      await user.click(screen.getByText("Support (project-1)"));

      await user.click(within(dialog).getByRole("button", { name: /invite user/i }));

      await waitFor(() => {
        expect(mockUserCreateCall).toHaveBeenCalledWith(
          "token",
          null,
          expect.objectContaining({
            cavadalabs_company_memberships: [
              {
                company_id: "company-1",
                role: "viewer",
              },
            ],
            cavadalabs_project_memberships: [
              {
                project_id: "project-1",
                role: "operator",
              },
            ],
          }),
        );
      });
      expect(mockUserCreateCall.mock.calls[0][2]).not.toHaveProperty("organizations");
      expect(mockUserCreateCall.mock.calls[0][2]).not.toHaveProperty("team_id");
    });

    it("should create CavadaLabs memberships without requiring internal compatibility mappings", async () => {
      mockUseCavadaLabsKeyContextOptions.mockReturnValue({
        companies: [
          {
            company_id: "company-1",
            legal_name: "My Company",
            litellm_organization_id: null,
          },
        ],
        projects: [
          {
            project_id: "project-1",
            company_id: "company-1",
            name: "Support",
            litellm_team_id: null,
          },
        ],
        isLoading: false,
      });

      const user = userEvent.setup();
      mockUserCreateCall.mockResolvedValue({ data: { user_id: "native-membership-user" } });
      mockInvitationCreateCall.mockResolvedValue({
        id: "inv-native-membership",
        user_id: "native-membership-user",
        has_user_setup_sso: false,
      } as any);

      renderWithProviders(
        <CreateUserButton {...defaultProps} possibleUIRoles={{ proxy_user: { ui_label: "User", description: "" } }} />,
      );

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /\+ invite user/i })).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: /\+ invite user/i }));

      const dialog = screen.getByRole("dialog", { name: /invite user/i });
      await user.type(within(dialog).getByLabelText(/user email/i), "native-membership@example.com");
      await user.click(within(dialog).getByRole("combobox", { name: /global proxy role/i }));
      await user.click(screen.getByText("User"));

      await user.click(within(dialog).getByRole("combobox", { name: /^company$/i }));
      await user.click(screen.getByText("My Company (company-1)"));

      await user.click(within(dialog).getByRole("combobox", { name: /^project$/i }));
      await user.click(screen.getByText("Support (project-1)"));

      await user.click(within(dialog).getByRole("button", { name: /invite user/i }));

      await waitFor(() => {
        expect(mockUserCreateCall).toHaveBeenCalledWith(
          "token",
          null,
          expect.objectContaining({
            cavadalabs_company_memberships: [
              {
                company_id: "company-1",
                role: "viewer",
              },
            ],
            cavadalabs_project_memberships: [
              {
                project_id: "project-1",
                role: "operator",
              },
            ],
          }),
        );
      });
      expect(mockUserCreateCall.mock.calls[0][2]).not.toHaveProperty("organizations");
      expect(mockUserCreateCall.mock.calls[0][2]).not.toHaveProperty("organization_id");
      expect(mockUserCreateCall.mock.calls[0][2]).not.toHaveProperty("team_id");
      expect(mockNotificationsManager.fromBackend).not.toHaveBeenCalled();
    });

    it("should send CavadaLabs company membership in POST body when companies are selected", async () => {
      mockUseCavadaLabsKeyContextOptions.mockReturnValue({
        companies: [
          {
            company_id: "company-1",
            legal_name: "My Company",
            litellm_organization_id: "org-1",
          },
        ],
        projects: [],
        isLoading: false,
      });

      const user = userEvent.setup();
      mockUserCreateCall.mockResolvedValue({ data: { user_id: "org-user" } });
      mockInvitationCreateCall.mockResolvedValue({
        id: "inv-org",
        user_id: "org-user",
        has_user_setup_sso: false,
      } as any);

      renderWithProviders(
        <CreateUserButton {...defaultProps} possibleUIRoles={{ proxy_user: { ui_label: "User", description: "" } }} />,
      );

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /\+ invite user/i })).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: /\+ invite user/i }));

      const dialog = screen.getByRole("dialog", { name: /invite user/i });
      await user.type(within(dialog).getByLabelText(/user email/i), "org@example.com");
      await user.click(within(dialog).getByRole("combobox", { name: /global proxy role/i }));
      await user.click(screen.getByText("User"));

      const companySelect = within(dialog).getByRole("combobox", { name: /^company$/i });
      await user.click(companySelect);
      await user.click(screen.getByText("My Company (company-1)"));

      await user.click(within(dialog).getByRole("button", { name: /invite user/i }));

      await waitFor(() => {
        expect(mockUserCreateCall).toHaveBeenCalledWith(
          "token",
          null,
          expect.objectContaining({
            cavadalabs_company_memberships: [
              {
                company_id: "company-1",
                role: "viewer",
              },
            ],
          }),
        );
      });
      expect(mockUserCreateCall.mock.calls[0][2]).not.toHaveProperty("cavadalabs_company_ids");
      expect(mockUserCreateCall.mock.calls[0][2]).not.toHaveProperty("organizations");
    });

    it("should send CavadaLabs project membership with selected role", async () => {
      mockUseCavadaLabsKeyContextOptions.mockReturnValue({
        companies: [],
        projects: [
          {
            project_id: "project-1",
            company_id: "company-1",
            name: "Support",
            litellm_team_id: "team-1",
          },
        ],
        isLoading: false,
      });

      const user = userEvent.setup();
      mockUserCreateCall.mockResolvedValue({ data: { user_id: "project-user" } });
      mockInvitationCreateCall.mockResolvedValue({
        id: "inv-project",
        user_id: "project-user",
        has_user_setup_sso: false,
      } as any);

      renderWithProviders(
        <CreateUserButton {...defaultProps} possibleUIRoles={{ proxy_user: { ui_label: "User", description: "" } }} />,
      );

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /\+ invite user/i })).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: /\+ invite user/i }));

      const dialog = screen.getByRole("dialog", { name: /invite user/i });
      await user.type(within(dialog).getByLabelText(/user email/i), "project@example.com");
      await user.click(within(dialog).getByRole("combobox", { name: /global proxy role/i }));
      await user.click(screen.getByText("User"));
      await user.click(within(dialog).getByRole("combobox", { name: /^project$/i }));
      await user.click(screen.getByText("Support (project-1)"));
      await user.click(within(dialog).getByRole("combobox", { name: /project role/i }));
      await user.click(screen.getByText("Project Admin"));
      await user.click(within(dialog).getByRole("button", { name: /invite user/i }));

      await waitFor(() => {
        expect(mockUserCreateCall).toHaveBeenCalledWith(
          "token",
          null,
          expect.objectContaining({
            cavadalabs_project_memberships: [
              {
                project_id: "project-1",
                role: "project_admin",
              },
            ],
          }),
        );
      });
      expect(mockUserCreateCall.mock.calls[0][2]).not.toHaveProperty("cavadalabs_project_ids");
      expect(mockUserCreateCall.mock.calls[0][2]).not.toHaveProperty("team_id");
    });

    it("should not call organizationMemberAddCall after user creation", async () => {
      const user = userEvent.setup();
      mockUserCreateCall.mockResolvedValue({ data: { user_id: "no-member-add-user" } });
      mockInvitationCreateCall.mockResolvedValue({
        id: "inv-nma",
        user_id: "no-member-add-user",
        has_user_setup_sso: false,
      } as any);

      renderWithProviders(
        <CreateUserButton {...defaultProps} possibleUIRoles={{ proxy_user: { ui_label: "User", description: "" } }} />,
      );

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /\+ invite user/i })).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: /\+ invite user/i }));

      const dialog = screen.getByRole("dialog", { name: /invite user/i });
      await user.type(within(dialog).getByLabelText(/user email/i), "nomemberadd@example.com");
      await user.click(within(dialog).getByRole("combobox", { name: /global proxy role/i }));
      await user.click(screen.getByText("User"));
      await user.click(within(dialog).getByRole("button", { name: /invite user/i }));

      await waitFor(() => {
        expect(mockUserCreateCall).toHaveBeenCalled();
      });
      expect(mockOrganizationMemberAddCall).not.toHaveBeenCalled();
    });
  });

  describe("legacy organization assignment", () => {
    it("should keep legacy bulk user creation available outside CavadaLabs context", () => {
      renderWithProviders(
        <CreateUserButton {...defaultProps} possibleUIRoles={{ proxy_user: { ui_label: "User", description: "" } }} />,
      );

      expect(screen.getByTestId("bulk-create-users")).toBeInTheDocument();
    });

    it("should keep Organization assignment available outside CavadaLabs context", async () => {
      const { useOrganizations } = await import("@/app/(dashboard)/hooks/organizations/useOrganizations");
      vi.mocked(useOrganizations).mockReturnValue({
        data: [{ organization_id: "org-1", organization_alias: "My Org" }],
        isLoading: false,
      });

      const user = userEvent.setup();
      mockUserCreateCall.mockResolvedValue({ data: { user_id: "legacy-org-user" } });
      mockInvitationCreateCall.mockResolvedValue({
        id: "inv-legacy-org",
        user_id: "legacy-org-user",
        has_user_setup_sso: false,
      } as any);

      renderWithProviders(
        <CreateUserButton {...defaultProps} possibleUIRoles={{ proxy_user: { ui_label: "User", description: "" } }} />,
      );

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /\+ invite user/i })).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: /\+ invite user/i }));

      const dialog = screen.getByRole("dialog", { name: /invite user/i });
      await user.type(within(dialog).getByLabelText(/user email/i), "legacy-org@example.com");
      await user.click(within(dialog).getByRole("combobox", { name: /global proxy role/i }));
      await user.click(screen.getByText("User"));
      await user.click(within(dialog).getByRole("combobox", { name: /^organization$/i }));
      await user.click(screen.getByText("My Org (org-1)"));
      await user.click(within(dialog).getByRole("button", { name: /invite user/i }));

      await waitFor(() => {
        expect(mockUserCreateCall).toHaveBeenCalledWith(
          "token",
          null,
          expect.objectContaining({
            organizations: ["org-1"],
          }),
        );
      });
      expect(mockUserCreateCall.mock.calls[0][2]).not.toHaveProperty("organization_ids");
      expect(mockUserCreateCall.mock.calls[0][2]).not.toHaveProperty("cavadalabs_company_memberships");
      expect(mockUserCreateCall.mock.calls[0][2]).not.toHaveProperty("cavadalabs_project_memberships");
    });
  });

  describe("send invitation email toggle", () => {
    it("should send send_invite_email true by default in embedded mode", async () => {
      const user = userEvent.setup();
      mockUserCreateCall.mockResolvedValue({ data: { user_id: "default-on-user" } });

      renderWithProviders(
        <CreateUserButton
          {...defaultProps}
          possibleUIRoles={{ proxy_user: { ui_label: "User", description: "" } }}
          isEmbedded
        />,
      );

      await user.type(screen.getByLabelText(/user email/i), "default@example.com");
      await user.click(screen.getByRole("combobox", { name: /user role/i }));
      await user.click(screen.getByText("User"));
      await user.click(screen.getByRole("button", { name: /create user/i }));

      await waitFor(() => {
        expect(mockUserCreateCall).toHaveBeenCalledWith(
          "token",
          null,
          expect.objectContaining({
            send_invite_email: true,
          }),
        );
      });
    });

    it("should send send_invite_email false when the checkbox is unchecked in embedded mode", async () => {
      const user = userEvent.setup();
      mockUserCreateCall.mockResolvedValue({ data: { user_id: "unchecked-user" } });

      renderWithProviders(
        <CreateUserButton
          {...defaultProps}
          possibleUIRoles={{ proxy_user: { ui_label: "User", description: "" } }}
          isEmbedded
        />,
      );

      await user.type(screen.getByLabelText(/user email/i), "off@example.com");
      await user.click(screen.getByRole("combobox", { name: /user role/i }));
      await user.click(screen.getByText("User"));
      await user.click(screen.getByRole("checkbox", { name: /send invitation email/i }));
      await user.click(screen.getByRole("button", { name: /create user/i }));

      await waitFor(() => {
        expect(mockUserCreateCall).toHaveBeenCalledWith(
          "token",
          null,
          expect.objectContaining({
            send_invite_email: false,
          }),
        );
      });
    });

    it("should send send_invite_email true by default in standalone mode", async () => {
      const user = userEvent.setup();
      mockUserCreateCall.mockResolvedValue({ data: { user_id: "standalone-default-user" } });
      mockInvitationCreateCall.mockResolvedValue({
        id: "inv-default",
        user_id: "standalone-default-user",
        has_user_setup_sso: false,
      } as any);

      renderWithProviders(
        <CreateUserButton {...defaultProps} possibleUIRoles={{ proxy_user: { ui_label: "User", description: "" } }} />,
      );

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /\+ invite user/i })).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: /\+ invite user/i }));

      const dialog = screen.getByRole("dialog", { name: /invite user/i });
      await user.type(within(dialog).getByLabelText(/user email/i), "standalone-default@example.com");
      await user.click(within(dialog).getByRole("combobox", { name: /global proxy role/i }));
      await user.click(screen.getByText("User"));
      await user.click(within(dialog).getByRole("button", { name: /invite user/i }));

      await waitFor(() => {
        expect(mockUserCreateCall).toHaveBeenCalledWith(
          "token",
          null,
          expect.objectContaining({
            send_invite_email: true,
          }),
        );
      });
    });

    it("should send send_invite_email false when the checkbox is unchecked in standalone mode", async () => {
      const user = userEvent.setup();
      mockUserCreateCall.mockResolvedValue({ data: { user_id: "standalone-off-user" } });
      mockInvitationCreateCall.mockResolvedValue({
        id: "inv-off",
        user_id: "standalone-off-user",
        has_user_setup_sso: false,
      } as any);

      renderWithProviders(
        <CreateUserButton {...defaultProps} possibleUIRoles={{ proxy_user: { ui_label: "User", description: "" } }} />,
      );

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /\+ invite user/i })).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: /\+ invite user/i }));

      const dialog = screen.getByRole("dialog", { name: /invite user/i });
      await user.type(within(dialog).getByLabelText(/user email/i), "standalone-off@example.com");
      await user.click(within(dialog).getByRole("combobox", { name: /global proxy role/i }));
      await user.click(screen.getByText("User"));
      await user.click(within(dialog).getByRole("checkbox", { name: /send invitation email/i }));
      await user.click(within(dialog).getByRole("button", { name: /invite user/i }));

      await waitFor(() => {
        expect(mockUserCreateCall).toHaveBeenCalledWith(
          "token",
          null,
          expect.objectContaining({
            send_invite_email: false,
          }),
        );
      });
    });

    it("should keep the checkbox checked by default when the modal is opened in standalone mode", async () => {
      const user = userEvent.setup();

      renderWithProviders(
        <CreateUserButton {...defaultProps} possibleUIRoles={{ proxy_user: { ui_label: "User", description: "" } }} />,
      );

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /\+ invite user/i })).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: /\+ invite user/i }));

      const dialog = screen.getByRole("dialog", { name: /invite user/i });
      expect(within(dialog).getByRole("checkbox", { name: /send invitation email/i })).toBeChecked();
    });
  });
});
