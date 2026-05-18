import React from "react";
import { render, screen, waitFor, act, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import AgentsPanel from "./agents";
import * as networking from "./networking";
import { useOrganizations } from "@/app/(dashboard)/hooks/organizations/useOrganizations";
import { useProjects } from "@/app/(dashboard)/hooks/projects/useProjects";

vi.mock("./networking", () => ({
  getAgentsList: vi.fn().mockResolvedValue({ agents: [] }),
  deleteAgentCall: vi.fn(),
  keyListCall: vi.fn().mockResolvedValue({ keys: [] }),
}));

vi.mock("@/app/(dashboard)/hooks/organizations/useOrganizations", () => ({
  useOrganizations: vi.fn(),
}));

vi.mock("@/app/(dashboard)/hooks/projects/useProjects", () => ({
  useProjects: vi.fn(),
}));

vi.mock("./common_components/ProjectDropdown", () => ({
  default: ({ projects, value, onChange, companyId }: any) => (
    <select
      aria-label="Project"
      value={value || ""}
      data-company-id={companyId || ""}
      onChange={(event) => onChange(event.target.value || undefined)}
    >
      <option value="">All Projects</option>
      {projects
        ?.filter((project: any) => !companyId || project.company_id === companyId)
        .map((project: any) => (
          <option key={project.project_id} value={project.project_id}>
            {project.project_alias || project.project_id} ({project.project_id})
          </option>
        ))}
    </select>
  ),
}));

vi.mock("./agents/add_agent_form", () => ({
  default: () => <div data-testid="add-agent-form" />,
}));

vi.mock("./agents/agent_card_grid", () => ({
  default: ({ isAdmin }: { isAdmin: boolean }) => (
    <div data-testid="agent-card-grid" data-is-admin={String(isAdmin)} />
  ),
}));

// Note: agents.tsx no longer uses AgentCardGrid — it renders a Table directly.

vi.mock("./agents/agent_info", () => ({
  default: () => <div data-testid="agent-info" />,
}));

describe("AgentsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useOrganizations).mockReturnValue({
      data: [
        {
          organization_id: "company-1",
          company_id: "company-1",
          company_name: "Acme Corp",
          organization_alias: "Acme Corp",
        },
        {
          organization_id: "company-2",
          company_id: "company-2",
          company_name: "Globex",
          organization_alias: "Globex",
        },
      ],
      isLoading: false,
    } as any);
    vi.mocked(useProjects).mockReturnValue({
      data: [
        {
          project_id: "project-1",
          project_alias: "Project One",
          company_id: "company-1",
        },
        {
          project_id: "project-2",
          project_alias: "Project Two",
          company_id: "company-2",
        },
      ],
      isLoading: false,
    } as any);
  });

  it("should render the Agents panel title", async () => {
    render(<AgentsPanel accessToken="test-token" userRole="Admin" />);
    expect(screen.getByText("Agents")).toBeInTheDocument();
  });

  it("should show Add New Agent button for admin users", async () => {
    render(<AgentsPanel accessToken="test-token" userRole="Admin" />);
    expect(screen.getByText("+ Add New Agent")).toBeInTheDocument();
  });

  it("should show Add New Agent button for proxy_admin users", async () => {
    render(<AgentsPanel accessToken="test-token" userRole="proxy_admin" />);
    expect(screen.getByText("+ Add New Agent")).toBeInTheDocument();
  });

  it("should not show Add New Agent button for internal_user role", async () => {
    render(<AgentsPanel accessToken="test-token" userRole="Internal User" />);
    expect(screen.queryByText("+ Add New Agent")).not.toBeInTheDocument();
  });

  it("should not show Add New Agent button for internal_user_viewer role", async () => {
    render(<AgentsPanel accessToken="test-token" userRole="Internal Viewer" />);
    expect(screen.queryByText("+ Add New Agent")).not.toBeInTheDocument();
  });

  it("should show Actions column header for admin role", async () => {
    render(<AgentsPanel accessToken="test-token" userRole="Admin" />);
    await waitFor(() => {
      expect(screen.getByRole("columnheader", { name: /actions/i })).toBeInTheDocument();
    });
  });

  it("should not show Actions column header for internal user role", async () => {
    render(<AgentsPanel accessToken="test-token" userRole="Internal User" />);
    await waitFor(() => {
      expect(screen.queryByRole("columnheader", { name: /actions/i })).not.toBeInTheDocument();
      // confirm table is rendered (not still loading)
      expect(screen.getByRole("table")).toBeInTheDocument();
    });
  });

  it("should render the Health Check toggle", async () => {
    render(<AgentsPanel accessToken="test-token" userRole="Admin" />);
    expect(screen.getByText("Health Check")).toBeInTheDocument();
  });

  it("should render the Health Check toggle for non-admin users too", async () => {
    render(<AgentsPanel accessToken="test-token" userRole="Internal User" />);
    expect(screen.getByText("Health Check")).toBeInTheDocument();
  });

  it("should call getAgentsList with health_check=false on initial load", async () => {
    render(<AgentsPanel accessToken="test-token" userRole="Admin" />);
    await waitFor(() => {
      expect(networking.getAgentsList).toHaveBeenCalledWith("test-token", false, {
        company_id: null,
        project_id: null,
      });
    });
  });

  it("should call getAgentsList with health_check=true when toggle is enabled", async () => {
    render(<AgentsPanel accessToken="test-token" userRole="Admin" />);
    await waitFor(() => {
      expect(networking.getAgentsList).toHaveBeenCalledWith("test-token", false, {
        company_id: null,
        project_id: null,
      });
    });

    const toggle = screen.getByRole("switch");
    await act(async () => {
      fireEvent.click(toggle);
    });

    await waitFor(() => {
      expect(networking.getAgentsList).toHaveBeenCalledWith("test-token", true, {
        company_id: null,
        project_id: null,
      });
    });
  });

  it("should filter agents by Company and Project without Organization payloads", async () => {
    render(<AgentsPanel accessToken="test-token" userRole="Admin" />);

    await waitFor(() => {
      expect(networking.getAgentsList).toHaveBeenCalledWith("test-token", false, {
        company_id: null,
        project_id: null,
      });
    });

    expect(screen.getAllByText("Company").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Project").length).toBeGreaterThan(0);
    expect(screen.queryByText("Organization")).not.toBeInTheDocument();

    await act(async () => {
      fireEvent.mouseDown(screen.getByLabelText("Company"));
    });
    await act(async () => {
      fireEvent.click(await screen.findByText("Acme Corp (company-1)"));
    });

    await waitFor(() => {
      expect(networking.getAgentsList).toHaveBeenCalledWith("test-token", false, {
        company_id: "company-1",
        project_id: null,
      });
    });

    expect(screen.getByLabelText("Project")).toHaveAttribute("data-company-id", "company-1");
    await act(async () => {
      fireEvent.change(screen.getByLabelText("Project"), {
        target: { value: "project-1" },
      });
    });

    await waitFor(() => {
      expect(networking.getAgentsList).toHaveBeenCalledWith("test-token", false, {
        company_id: "company-1",
        project_id: "project-1",
      });
    });
  });
});
