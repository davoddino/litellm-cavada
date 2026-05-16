import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { describe, expect, it, vi } from "vitest";
import { Team } from "@/components/key_team_helpers/key_list";
import TeamsTable from "./TeamsTable";

vi.mock("@tremor/react", () => {
  const Button = React.forwardRef<HTMLButtonElement, any>(({ children, ...props }, ref) =>
    React.createElement("button", { ...props, ref }, children),
  );
  Button.displayName = "MockTremorButton";

  return {
    Button,
    Icon: ({ onClick, ...props }: any) => (
      <button data-testid={props["data-testid"] || "icon-btn"} onClick={onClick} aria-label={props["aria-label"]} />
    ),
    Table: ({ children }: any) => <table>{children}</table>,
    TableHead: ({ children }: any) => <thead>{children}</thead>,
    TableBody: ({ children }: any) => <tbody>{children}</tbody>,
    TableRow: ({ children }: any) => <tr>{children}</tr>,
    TableHeaderCell: ({ children }: any) => <th>{children}</th>,
    TableCell: ({ children, ...props }: any) => <td {...props}>{children}</td>,
    Text: ({ children }: any) => <span>{children}</span>,
  };
});

vi.mock("antd", () => ({
  Tooltip: ({ children }: any) => <>{children}</>,
}));

vi.mock("@heroicons/react/outline", () => ({
  PencilAltIcon: () => <svg data-testid="pencil-icon" />,
  TrashIcon: () => <svg data-testid="trash-icon" />,
}));

vi.mock("@/utils/dataUtils", () => ({
  formatNumberWithCommas: (val: number, decimals: number) => (val != null ? val.toFixed(decimals) : "N/A"),
}));

vi.mock("@/app/(dashboard)/teams/components/TeamsTable/ModelsCell", () => ({
  default: ({ team }: any) => <td data-testid="models-cell">{team.models.join(",")}</td>,
}));

vi.mock("@/app/(dashboard)/teams/components/TeamsTable/YourRoleCell/YourRoleCell", () => ({
  default: () => <td data-testid="role-cell">admin</td>,
}));

const makeTeam = (overrides: Partial<Team> = {}): Team => ({
  team_id: "team-abc1234",
  team_alias: "Platform",
  models: ["gpt-4"],
  max_budget: 500,
  budget_duration: null,
  tpm_limit: null,
  rpm_limit: null,
  organization_id: "org-1",
  created_at: "2024-06-01T00:00:00Z",
  keys: [],
  members_with_roles: [],
  spend: 123.4567,
  ...overrides,
});

const defaultPerTeamInfo = {
  "team-abc1234": {
    keys: [{ token: "tok-1" } as any, { token: "tok-2" } as any],
    team_info: {
      members_with_roles: [{ user_id: "u1", role: "admin" } as any],
    },
  },
};

const renderTable = (overrides: Partial<Parameters<typeof TeamsTable>[0]> = {}) => {
  const defaults = {
    teams: [makeTeam()],
    currentOrg: null,
    cavadalabsCompanies: [
      {
        company_id: "company-1",
        legal_name: "Acme Spa",
        litellm_organization_id: "org-1",
      },
    ],
    cavadalabsProjects: [
      {
        project_id: "project-1",
        company_id: "company-1",
        name: "Support",
        litellm_team_id: "team-abc1234",
      },
    ],
    isCavadaLabsProductContext: false,
    perTeamInfo: defaultPerTeamInfo,
    userRole: "Admin",
    userId: "user-1",
    setSelectedTeamId: vi.fn(),
    setEditTeam: vi.fn(),
    onDeleteTeam: vi.fn(),
    onOpenCavadaProject: vi.fn(),
  };
  return render(<TeamsTable {...defaults} {...overrides} />);
};

describe("TeamsTable", () => {
  it("should render table headers", () => {
    renderTable();

    expect(screen.getByText("Team Name")).toBeInTheDocument();
    expect(screen.getByText("Team ID")).toBeInTheDocument();
    expect(screen.getByText("Created")).toBeInTheDocument();
    expect(screen.getByText("Spend (USD)")).toBeInTheDocument();
    expect(screen.getByText("Budget (USD)")).toBeInTheDocument();
    expect(screen.getByText("Models")).toBeInTheDocument();
    expect(screen.getByText("Company")).toBeInTheDocument();
    expect(screen.queryByText("Organization")).not.toBeInTheDocument();
    expect(screen.getByText("Your Role")).toBeInTheDocument();
    expect(screen.getByText("Info")).toBeInTheDocument();
  });

  it("should render Project-backed columns in CavadaLabs product context", () => {
    renderTable({ isCavadaLabsProductContext: true });

    expect(screen.getByText("Project Name")).toBeInTheDocument();
    expect(screen.getByText("Project ID")).toBeInTheDocument();
    expect(screen.queryByText("Team Name")).not.toBeInTheDocument();
    expect(screen.queryByText("Team ID")).not.toBeInTheDocument();
    expect(screen.getByText("Support")).toBeInTheDocument();
    expect(screen.getByText("project...")).toBeInTheDocument();
    expect(screen.getByText("Acme Spa (company-1)")).toBeInTheDocument();
    expect(screen.queryByText("org-1")).not.toBeInTheDocument();
    expect(screen.queryByText("team-abc1234")).not.toBeInTheDocument();
  });

  it("should render team rows with team data", () => {
    renderTable();

    expect(screen.getByText("Platform")).toBeInTheDocument();
    expect(screen.getByText("team-ab...")).toBeInTheDocument();
    expect(screen.getByText("Acme Spa (company-1)")).toBeInTheDocument();
    expect(screen.queryByText("org-1")).not.toBeInTheDocument();
  });

  it("should not expose compatibility organization IDs when company mapping is missing", () => {
    renderTable({ cavadalabsCompanies: [] });

    expect(screen.getByText("Missing Company mapping")).toBeInTheDocument();
    expect(screen.queryByText("org-1")).not.toBeInTheDocument();
  });

  it("should show a Project mapping gap without exposing internal team IDs", () => {
    renderTable({ isCavadaLabsProductContext: true, cavadalabsProjects: [] });

    expect(screen.getAllByText("Missing Project mapping").length).toBeGreaterThan(0);
    expect(screen.queryByText("team-abc1234")).not.toBeInTheDocument();
    expect(screen.queryByTestId("project-id-cell")).not.toBeInTheDocument();
  });

  it("should prefer canonical CavadaLabs Project fields from team list payload", async () => {
    const user = userEvent.setup();
    const onOpenCavadaProject = vi.fn();
    renderTable({
      isCavadaLabsProductContext: true,
      cavadalabsCompanies: [],
      cavadalabsProjects: [],
      onOpenCavadaProject,
      teams: [
        makeTeam({
          cavadalabs_company_id: "company-api",
          cavadalabs_project_id: "project-api",
          cavadalabs_project_name: "API Project",
        }),
      ],
    });

    expect(screen.getByText("API Project")).toBeInTheDocument();
    expect(screen.getByText("project...")).toBeInTheDocument();
    expect(screen.getByText("company-api")).toBeInTheDocument();
    expect(screen.queryByText("Missing Project mapping")).not.toBeInTheDocument();
    expect(screen.queryByText("team-abc1234")).not.toBeInTheDocument();

    await user.click(screen.getByTestId("project-id-cell"));

    expect(onOpenCavadaProject).toHaveBeenCalledWith("project-api");
  });

  it("should show edit and delete icons for Admin users", () => {
    renderTable({ userRole: "Admin" });

    expect(screen.getAllByTestId("icon-btn").length).toBeGreaterThanOrEqual(2);
  });

  it("should not show edit and delete icons for non-Admin users", () => {
    renderTable({ userRole: "Internal User" });

    // Only the team ID button should be present, no icon-btn for edit/delete
    const iconBtns = screen.queryAllByTestId("icon-btn");
    expect(iconBtns).toHaveLength(0);
  });

  it("should call setSelectedTeamId when team ID button is clicked", async () => {
    const user = userEvent.setup();
    const setSelectedTeamId = vi.fn();
    renderTable({ setSelectedTeamId });

    await user.click(screen.getByText("team-ab..."));

    expect(setSelectedTeamId).toHaveBeenCalledWith("team-abc1234");
  });

  it("should open the CavadaLabs Project detail instead of TeamInfo in product context", async () => {
    const user = userEvent.setup();
    const setSelectedTeamId = vi.fn();
    const onOpenCavadaProject = vi.fn();
    renderTable({ isCavadaLabsProductContext: true, setSelectedTeamId, onOpenCavadaProject });

    await user.click(screen.getByTestId("project-id-cell"));

    expect(onOpenCavadaProject).toHaveBeenCalledWith("project-1");
    expect(setSelectedTeamId).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("Edit team")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Delete team")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Open project")).toBeInTheDocument();
    expect(screen.queryByText("team-abc1234")).not.toBeInTheDocument();
  });
});
