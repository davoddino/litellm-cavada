import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import EditUserModal from "./edit_user";

vi.mock("./common_components/budget_duration_dropdown", () => ({
  default: () => (
    <select aria-label="Reset Budget">
      <option value="">Never</option>
    </select>
  ),
}));

const defaultUser = {
  user_id: "target-user",
  user_email: "target@example.com",
  user_role: "internal_user",
};

const companies = [
  {
    company_id: "company-1",
    legal_name: "ACME",
    litellm_organization_id: "org-1",
  },
  {
    company_id: "company-2",
    legal_name: "Other Company",
    litellm_organization_id: "org-2",
  },
];

const projects = [
  {
    project_id: "project-1",
    company_id: "company-1",
    name: "Support",
    litellm_team_id: "team-1",
  },
  {
    project_id: "project-2",
    company_id: "company-2",
    name: "Backoffice",
    litellm_team_id: "team-2",
  },
];

describe("EditUserModal CavadaLabs memberships", () => {
  it("should submit Company and Project membership without Organization tenant fields", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();

    render(
      <EditUserModal
        visible
        possibleUIRoles={{
          internal_user: { ui_label: "Internal User", description: "Standard user" },
        }}
        onCancel={vi.fn()}
        user={defaultUser}
        onSubmit={onSubmit}
        cavadalabsCompanies={companies}
        cavadalabsProjects={projects}
      />,
    );

    expect(screen.queryByRole("combobox", { name: /organization/i })).not.toBeInTheDocument();

    await user.click(screen.getByRole("combobox", { name: /^company$/i }));
    await user.click(await screen.findByText("ACME (company-1)"));

    await user.click(screen.getByRole("combobox", { name: /^company role$/i }));
    await user.click(await screen.findByText("Company Admin"));

    await user.click(screen.getByRole("combobox", { name: /^project$/i }));
    expect(screen.queryByText("Backoffice (project-2)")).not.toBeInTheDocument();
    await user.click(await screen.findByText("Support (project-1)"));

    await user.click(screen.getByRole("combobox", { name: /^project role$/i }));
    await user.click(await screen.findByText("Project Admin"));

    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          user_id: "target-user",
          user_email: "target@example.com",
          cavadalabs_company_memberships: [
            {
              company_id: "company-1",
              role: "company_admin",
            },
          ],
          cavadalabs_project_memberships: [
            {
              project_id: "project-1",
              role: "project_admin",
            },
          ],
        }),
      );
    });
    const submitted = onSubmit.mock.calls[0][0];
    expect(submitted).not.toHaveProperty("organizations");
    expect(submitted).not.toHaveProperty("organization_id");
    expect(submitted).not.toHaveProperty("team_id");
  });

  it("should initialize existing CavadaLabs memberships in Company and Project fields", () => {
    render(
      <EditUserModal
        visible
        possibleUIRoles={null}
        onCancel={vi.fn()}
        user={{
          ...defaultUser,
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
        }}
        onSubmit={vi.fn()}
        cavadalabsCompanies={companies}
        cavadalabsProjects={projects}
      />,
    );

    expect(screen.getByText("ACME (company-1)")).toBeInTheDocument();
    expect(screen.getByText("Support (project-1)")).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: /organization/i })).not.toBeInTheDocument();
  });
});
