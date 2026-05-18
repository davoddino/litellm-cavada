import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { CredentialItem } from "../networking";
import { vectorStoreCreateCall } from "../networking";
import VectorStoreForm from "./VectorStoreForm";

vi.mock("../networking", () => ({
  vectorStoreCreateCall: vi.fn(),
}));

vi.mock("../playground/llm_calls/fetch_models", () => ({
  fetchAvailableModels: vi.fn().mockResolvedValue([]),
}));

vi.mock("../common_components/OrganizationDropdown", () => ({
  default: ({ organizations, value, onChange }: any) => (
    <select aria-label="Company" value={value || ""} onChange={(event) => onChange(event.target.value || undefined)}>
      <option value="">Select Company</option>
      {organizations?.map((company: any) => (
        <option key={company.company_id || company.organization_id} value={company.company_id || company.organization_id}>
          {company.company_name || company.organization_alias}
        </option>
      ))}
    </select>
  ),
}));

vi.mock("../common_components/ProjectDropdown", () => ({
  default: ({ projects, value, onChange, companyId, disabled }: any) => (
    <select
      aria-label="Project"
      value={value || ""}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value || undefined)}
    >
      <option value="">Select Project</option>
      {projects
        ?.filter((project: any) => !companyId || project.company_id === companyId)
        .map((project: any) => (
          <option key={project.project_id} value={project.project_id}>
            {project.project_alias || project.project_id}
          </option>
        ))}
    </select>
  ),
}));

describe("VectorStoreForm", () => {
  const companies = [
    {
      company_id: "company-alpha",
      company_name: "Acme Labs",
      organization_id: "company-alpha",
      organization_alias: "Acme Labs",
    },
  ];
  const projects = [
    {
      project_id: "project-alpha",
      company_id: "company-alpha",
      project_alias: "Project Alpha",
    },
  ];

  it("should render the form when visible", () => {
    const mockOnCancel = vi.fn();
    const mockOnSuccess = vi.fn();
    const mockAccessToken = "test-token";
    const mockCredentials: CredentialItem[] = [];

    render(
      <VectorStoreForm
        isVisible={true}
        onCancel={mockOnCancel}
        onSuccess={mockOnSuccess}
        accessToken={mockAccessToken}
        credentials={mockCredentials}
        organizations={companies as any}
        projects={projects as any}
      />,
    );

    expect(screen.getByText("Add New Vector Store")).toBeInTheDocument();
    expect(screen.getByText("Company")).toBeInTheDocument();
    expect(screen.getByText("Project")).toBeInTheDocument();
  });

  it("should submit Company and Project fields without tenant compatibility aliases", async () => {
    vi.mocked(vectorStoreCreateCall).mockResolvedValue(undefined);
    const mockOnCancel = vi.fn();
    const mockOnSuccess = vi.fn();

    render(
      <VectorStoreForm
        isVisible={true}
        onCancel={mockOnCancel}
        onSuccess={mockOnSuccess}
        accessToken="test-token"
        credentials={[]}
        organizations={companies as any}
        projects={projects as any}
      />,
    );

    await act(async () => {
      fireEvent.change(screen.getByPlaceholderText("Enter vector store ID from your provider"), {
        target: { value: "vs_project_alpha" },
      });
      fireEvent.change(screen.getByLabelText("Company"), { target: { value: "company-alpha" } });
      fireEvent.change(screen.getByLabelText("Project"), { target: { value: "project-alpha" } });
      fireEvent.click(screen.getByRole("button", { name: "Create" }));
    });

    await waitFor(() => expect(vectorStoreCreateCall).toHaveBeenCalled());
    const payload = vi.mocked(vectorStoreCreateCall).mock.calls[0][1];
    expect(payload.company_id).toBe("company-alpha");
    expect(payload.project_id).toBe("project-alpha");
    expect(payload.organization_id).toBeUndefined();
    expect(payload.organizations).toBeUndefined();
  });
});
