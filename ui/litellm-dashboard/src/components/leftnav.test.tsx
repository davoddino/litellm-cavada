import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "../../tests/test-utils";
import Sidebar from "./leftnav";

vi.mock("./UsageIndicator", () => ({
  default: () => <div data-testid="usage-indicator" />,
}));

vi.mock("../utils/roles", () => {
  return {
    all_admin_roles: ["admin", "admin_viewer"],
    internalUserRoles: ["internal"],
    rolesWithWriteAccess: ["admin", "internal"],
    rolesAllowedToViewWriteScopedPages: ["admin", "internal", "admin_viewer"],
    isAdminRole: (role: string) => role === "admin" || role === "admin_viewer",
    isUserTeamAdminForAnyTeam: () => false,
  };
});

const { mockUseAuthorized, mockUseOrganizations, mockCavadaLabsKeyContext } = vi.hoisted(() => {
  const mockUseAuthorized = vi.fn(() => ({
    userId: "test-user-id",
    accessToken: "test-access-token",
    userRole: "admin",
    token: "test-token",
    userEmail: "test@example.com",
    premiumUser: false,
    disabledPersonalKeyCreation: false,
    showSSOBanner: false,
  }));

  const mockUseOrganizations = vi.fn(() => ({
    data: [],
    isLoading: false,
    error: null,
  }));

  const mockCavadaLabsKeyContext = {
    value: {
      companies: [] as any[],
      projects: [] as any[],
      isLoading: false,
      errorDetail: null,
    },
  };

  return { mockUseAuthorized, mockUseOrganizations, mockCavadaLabsKeyContext };
});

vi.mock("@/app/(dashboard)/hooks/useAuthorized", () => ({
  default: mockUseAuthorized,
}));

vi.mock("@/app/(dashboard)/hooks/organizations/useOrganizations", () => ({
  useOrganizations: mockUseOrganizations,
}));

vi.mock("@/app/(dashboard)/hooks/teams/useTeams", () => ({
  useTeams: () => ({ data: [], isLoading: false, error: null }),
}));

vi.mock("@/components/cavadalabs/keyContext", () => ({
  useCavadaLabsKeyContextOptions: () => mockCavadaLabsKeyContext.value,
}));

vi.mock("@/app/(dashboard)/hooks/uiConfig/useUIConfig", () => {
  return {
    useUIConfig: () => ({
      data: { admin_ui_disabled: false },
      isLoading: false,
    }),
  };
});

describe("Sidebar (leftnav)", () => {
  const defaultProps = {
    setPage: vi.fn(),
    defaultSelectedKey: "api-keys",
    collapsed: false,
  };

  beforeEach(() => {
    mockCavadaLabsKeyContext.value = {
      companies: [],
      projects: [],
      isLoading: false,
      errorDetail: null,
    };
  });

  const renderSidebar = async () => {
    let result: ReturnType<typeof renderWithProviders> | undefined;
    await act(async () => {
      result = renderWithProviders(<Sidebar {...defaultProps} />);
    });
    if (!result) throw new Error("Sidebar render failed");
    return result;
  };

  it("renders all top-level (non-nested) tabs for admin", async () => {
    await renderSidebar();

    const topLevelLabels = [
      "Virtual Keys",
      "Playground",
      "Models + Endpoints",
      "Agentic",
      "MCP Servers",
      "Guardrails",
      "Policies",
      "CavadaLabs",
      "Tools",
      "Usage",
      "Logs",
      "Guardrails Monitor",
      "Teams",
      "Internal Users",
      "Companies",
      "Projects",
      "Access Groups",
      "Budgets",
      "API Reference",
      "AI Hub",
      "Learning Resources",
      "Experimental",
      "Settings",
    ];

    topLevelLabels.forEach((label) => {
      expect(screen.getByText(label)).toBeInTheDocument();
    });
  });

  it("should route Companies and Projects through CavadaLabs access-control pages", async () => {
    const setPage = vi.fn();
    let result: ReturnType<typeof renderWithProviders> | undefined;
    await act(async () => {
      result = renderWithProviders(<Sidebar {...defaultProps} setPage={setPage} />);
    });
    if (!result) throw new Error("Sidebar render failed");

    act(() => {
      fireEvent.click(screen.getByText("Companies"));
    });
    expect(setPage).toHaveBeenCalledWith("cavadalabs-companies");

    act(() => {
      fireEvent.click(screen.getByText("Projects"));
    });
    expect(setPage).toHaveBeenCalledWith("cavadalabs-projects");
  });

  it("should route the CavadaLabs internal Projects nav to the canonical Projects page", async () => {
    mockUseAuthorized.mockReturnValueOnce({
      userId: "project-admin-user-id",
      accessToken: "test-access-token",
      userRole: "internal",
      token: "test-token",
      userEmail: "project-admin@example.com",
      premiumUser: false,
      disabledPersonalKeyCreation: false,
      showSSOBanner: false,
    });
    mockCavadaLabsKeyContext.value = {
      companies: [{ company_id: "company-1", legal_name: "Acme" }],
      projects: [{ project_id: "project-1", company_id: "company-1", name: "Support" }],
      isLoading: false,
      errorDetail: null,
    };
    const setPage = vi.fn();

    let result: ReturnType<typeof renderWithProviders> | undefined;
    await act(async () => {
      result = renderWithProviders(<Sidebar {...defaultProps} setPage={setPage} />);
    });
    if (!result) throw new Error("Sidebar render failed");

    expect(screen.queryByText("Teams")).not.toBeInTheDocument();
    const projectsLink = screen.getByRole("link", { name: "Projects" });
    expect(projectsLink).toHaveAttribute("href", "/cavadalabs/projects");

    act(() => {
      fireEvent.click(projectsLink);
    });

    expect(setPage).toHaveBeenCalledWith("cavadalabs-projects");
  });

  it("should not expose legacy Teams nav when CavadaLabs context is explicit with empty options", async () => {
    mockUseAuthorized.mockReturnValueOnce({
      userId: "project-viewer-user-id",
      accessToken: "test-access-token",
      userRole: "internal",
      token: "test-token",
      userEmail: "viewer@example.com",
      premiumUser: false,
      disabledPersonalKeyCreation: false,
      showSSOBanner: false,
    });
    mockCavadaLabsKeyContext.value = {
      companies: [],
      projects: [],
      isLoading: false,
      errorDetail: null,
      contextKnown: true,
      isCavadaLabsProductContext: true,
    };

    await renderSidebar();

    expect(screen.queryByText("Teams")).not.toBeInTheDocument();
    const projectsLink = screen.getByRole("link", { name: "Projects" });
    expect(projectsLink).toHaveAttribute("href", "/cavadalabs/projects");
  });

  it("should hide legacy Teams nav for CavadaLabs admins with canonical Projects access", async () => {
    mockCavadaLabsKeyContext.value = {
      companies: [{ company_id: "company-1", legal_name: "Acme" }],
      projects: [{ project_id: "project-1", company_id: "company-1", name: "Support" }],
      isLoading: false,
      errorDetail: null,
    };

    await renderSidebar();

    expect(screen.queryByText("Teams")).not.toBeInTheDocument();
    expect(screen.getByText("Projects")).toBeInTheDocument();
  });

  it("expands a nested tab to reveal its children (Tools > Search Tools)", async () => {
    await renderSidebar();

    expect(screen.queryByText("Search Tools")).not.toBeInTheDocument();
    act(() => {
      fireEvent.click(screen.getByText("Tools"));
    });
    await waitFor(() => {
      expect(screen.getByText("Search Tools")).toBeInTheDocument();
    });
  });
  it("has no duplicate keys among all menu items and their children", async () => {
    // Helper to recursively extract all keys from Ant Design Menu items
    function getAllKeysFromMenu(wrapper: HTMLElement): string[] {
      const allKeys: string[] = [];
      // Ant Design renders key as data-menu-id or inside attributes, but for this case, we look for text as fallback.
      // For a generic check, here we fetch ids from rendered list items, and also descend into submenus
      const items = wrapper.querySelectorAll("[data-menu-id]");
      items.forEach((item) => {
        const dataMenuId = item.getAttribute("data-menu-id");
        if (dataMenuId) {
          allKeys.push(dataMenuId);
        }
      });
      return allKeys;
    }

    const { container } = await renderSidebar();
    const allRenderedKeys = getAllKeysFromMenu(container);

    const keySet = new Set<string>();
    const duplicates: string[] = [];
    for (const key of allRenderedKeys) {
      if (keySet.has(key)) {
        duplicates.push(key);
      }
      keySet.add(key);
    }
    expect(duplicates).toHaveLength(0);
  });

  describe("Admin Viewer parity", () => {
    // Admin Viewer follows a "read parity with Proxy Admin, no writes, no
    // cost-incurring actions" rule. Playground stays hidden (incurs LLM
    // cost); Models + Endpoints and Agents must be visible read-only.
    const adminViewerAuth = {
      userId: "admin-viewer-user-id",
      accessToken: "test-access-token",
      userRole: "admin_viewer",
      token: "test-token",
      userEmail: "viewer@example.com",
      premiumUser: false,
      disabledPersonalKeyCreation: false,
      showSSOBanner: false,
    };

    it("hides Playground from Admin Viewer (cost-incurring action)", async () => {
      mockUseAuthorized.mockReturnValueOnce(adminViewerAuth);
      await renderSidebar();
      expect(screen.queryByText("Playground")).not.toBeInTheDocument();
    });

    it("shows Models + Endpoints to Admin Viewer (read-only)", async () => {
      mockUseAuthorized.mockReturnValueOnce(adminViewerAuth);
      await renderSidebar();
      expect(screen.getByText("Models + Endpoints")).toBeInTheDocument();
    });

    it("shows Agents (under Agentic) to Admin Viewer (read-only)", async () => {
      mockUseAuthorized.mockReturnValueOnce(adminViewerAuth);
      await renderSidebar();
      // Agents is now nested under the "Agentic" submenu — expand parent
      // first to render the children, then assert Agents is visible.
      act(() => {
        fireEvent.click(screen.getByText("Agentic"));
      });
      await waitFor(() => {
        expect(screen.getByText("Agents")).toBeInTheDocument();
      });
    });

    it("shows Logs to Admin Viewer", async () => {
      mockUseAuthorized.mockReturnValueOnce(adminViewerAuth);
      await renderSidebar();
      expect(screen.getByText("Logs")).toBeInTheDocument();
    });
  });

  it("should not show CavadaLabs tenant controls for organization admins without CavadaLabs admin role", async () => {
    mockUseAuthorized.mockReturnValueOnce({
      userId: "org-admin-user-id",
      accessToken: "test-access-token",
      userRole: "viewer",
      token: "test-token",
      userEmail: "orgadmin@example.com",
      premiumUser: false,
      disabledPersonalKeyCreation: false,
      showSSOBanner: false,
    });

    mockUseOrganizations.mockReturnValueOnce({
      data: [
        {
          organization_id: "org-1",
          organization_name: "Test Organization",
          spend: 0,
          max_budget: null,
          models: [],
          tpm_limit: null,
          rpm_limit: null,
          members: [
            {
              user_id: "org-admin-user-id",
              user_role: "org_admin",
            },
          ],
        },
      ],
      isLoading: false,
      error: null,
    } as any);

    await renderSidebar();

    expect(screen.queryByText("Organizations")).not.toBeInTheDocument();
    expect(screen.queryByText("Companies")).not.toBeInTheDocument();
    expect(screen.queryByText("Projects")).not.toBeInTheDocument();
  });
});
