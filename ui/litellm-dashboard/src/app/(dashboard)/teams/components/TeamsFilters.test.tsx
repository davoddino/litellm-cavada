import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { describe, expect, it, vi } from "vitest";
import TeamsFilters from "./TeamsFilters";

type FilterState = {
  team_id: string;
  team_alias: string;
  cavadalabs_company_id: string;
  cavadalabs_project_id: string;
  sort_by: string;
  sort_order: "asc" | "desc";
};

const emptyFilters: FilterState = {
  team_alias: "",
  team_id: "",
  cavadalabs_company_id: "",
  cavadalabs_project_id: "",
  sort_by: "",
  sort_order: "asc",
};

const mockCompanies = [
  { company_id: "company-1", legal_name: "Acme Corp" },
  { company_id: "company-2", legal_name: "Globex" },
];

const mockProjects = [
  { project_id: "project-1", company_id: "company-1", name: "Support" },
  { project_id: "project-2", company_id: "company-2", name: "Billing" },
];

const renderFilters = (overrides: Partial<Parameters<typeof TeamsFilters>[0]> = {}) => {
  const defaults = {
    filters: emptyFilters,
    companies: mockCompanies,
    projects: mockProjects,
    showFilters: false,
    onToggleFilters: vi.fn(),
    onChange: vi.fn(),
    onReset: vi.fn(),
  };
  return render(<TeamsFilters {...defaults} {...overrides} />);
};

describe("TeamsFilters", () => {
  it("should render the team name search input, Filters button, and Reset Filters button", () => {
    renderFilters();

    expect(screen.getByPlaceholderText("Search by Team Name...")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^filters$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reset filters/i })).toBeInTheDocument();
  });

  it("should reflect the current team_alias filter value in the search input", () => {
    renderFilters({ filters: { ...emptyFilters, team_alias: "Platform" } });

    expect(screen.getByPlaceholderText("Search by Team Name...")).toHaveValue("Platform");
  });

  it("should call onChange with team_alias update when the search input changes", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderFilters({ onChange });

    await user.type(screen.getByPlaceholderText("Search by Team Name..."), "Dev");

    expect(onChange).toHaveBeenCalledWith({ team_alias: expect.stringContaining("D") });
  });

  it("should use Project wording and hide Team ID filtering in CavadaLabs product context", () => {
    renderFilters({ isCavadaLabsProductContext: true, showFilters: true });

    expect(screen.getByPlaceholderText("Search by Project Name...")).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("Search by Team Name...")).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText("Enter Team ID")).not.toBeInTheDocument();
    expect(screen.getByText("Company")).toBeInTheDocument();
    expect(screen.getByText("Project")).toBeInTheDocument();
  });

  it("should call onToggleFilters with the inverted boolean when the Filters button is clicked", async () => {
    const user = userEvent.setup();
    const onToggleFilters = vi.fn();
    renderFilters({ showFilters: false, onToggleFilters });

    await user.click(screen.getByRole("button", { name: /^filters$/i }));

    expect(onToggleFilters).toHaveBeenCalledWith(true);
  });

  it("should call onToggleFilters(false) when filters are currently expanded", async () => {
    const user = userEvent.setup();
    const onToggleFilters = vi.fn();
    renderFilters({ showFilters: true, onToggleFilters });

    await user.click(screen.getByRole("button", { name: /^filters$/i }));

    expect(onToggleFilters).toHaveBeenCalledWith(false);
  });

  it("should call onReset when the Reset Filters button is clicked", async () => {
    const user = userEvent.setup();
    const onReset = vi.fn();
    renderFilters({ onReset });

    await user.click(screen.getByRole("button", { name: /reset filters/i }));

    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it("should not show the Team ID input when showFilters is false", () => {
    renderFilters({ showFilters: false });

    expect(screen.queryByPlaceholderText("Enter Team ID")).not.toBeInTheDocument();
  });

  it("should show the Team ID input when showFilters is true", () => {
    renderFilters({ showFilters: true });

    expect(screen.getByPlaceholderText("Enter Team ID")).toBeInTheDocument();
  });

  it("should call onChange with team_id update when the Team ID input changes", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderFilters({ showFilters: true, onChange });

    await user.type(screen.getByPlaceholderText("Enter Team ID"), "abc");

    expect(onChange).toHaveBeenCalledWith({ team_id: expect.stringContaining("a") });
  });

  it("should reflect the current team_id filter value in the Team ID input", () => {
    renderFilters({ showFilters: true, filters: { ...emptyFilters, team_id: "team-xyz" } });

    expect(screen.getByPlaceholderText("Enter Team ID")).toHaveValue("team-xyz");
  });

  it("should show the active filter indicator on the Filters button when team_alias is set", () => {
    renderFilters({ filters: { ...emptyFilters, team_alias: "Platform" } });

    const filtersButton = screen.getByRole("button", { name: /^filters$/i });
    expect(within(filtersButton).getByTestId("active-filter-indicator")).toBeInTheDocument();
  });

  it("should show the active filter indicator on the Filters button when team_id is set", () => {
    renderFilters({ filters: { ...emptyFilters, team_id: "team-123" } });

    const filtersButton = screen.getByRole("button", { name: /^filters$/i });
    expect(within(filtersButton).getByTestId("active-filter-indicator")).toBeInTheDocument();
  });

  it("should show the active filter indicator on the Filters button when company context is set", () => {
    renderFilters({
      isCavadaLabsProductContext: true,
      filters: { ...emptyFilters, cavadalabs_company_id: "company-1" },
    });

    const filtersButton = screen.getByRole("button", { name: /^filters$/i });
    expect(within(filtersButton).getByTestId("active-filter-indicator")).toBeInTheDocument();
  });

  it("should not show the active filter indicator for hidden Cavada filters outside product context", () => {
    renderFilters({ filters: { ...emptyFilters, cavadalabs_company_id: "company-1" } });

    const filtersButton = screen.getByRole("button", { name: /^filters$/i });
    expect(within(filtersButton).queryByTestId("active-filter-indicator")).not.toBeInTheDocument();
  });

  it("should keep legacy filters Team-native outside CavadaLabs product context", () => {
    renderFilters({ showFilters: true });

    expect(screen.getByPlaceholderText("Enter Team ID")).toBeInTheDocument();
    expect(screen.queryByText("Company")).not.toBeInTheDocument();
    expect(screen.queryByText("Project")).not.toBeInTheDocument();
    expect(screen.queryByText("Select Organization")).not.toBeInTheDocument();
  });

  it("should render Company and Project filters only in CavadaLabs product context", () => {
    renderFilters({ isCavadaLabsProductContext: true, showFilters: true });

    expect(screen.getByText("Company")).toBeInTheDocument();
    expect(screen.getByText("Project")).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("Enter Team ID")).not.toBeInTheDocument();
    expect(screen.queryByText("Select Organization")).not.toBeInTheDocument();
  });

  it("should not show the active filter indicator when all filters are empty", () => {
    renderFilters({ filters: emptyFilters });

    const filtersButton = screen.getByRole("button", { name: /^filters$/i });
    expect(within(filtersButton).queryByTestId("active-filter-indicator")).not.toBeInTheDocument();
  });
});
