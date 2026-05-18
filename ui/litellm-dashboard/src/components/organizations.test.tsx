import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import React from "react";

vi.mock("./vector_store_management/VectorStoreSelector", () => ({
  __esModule: true,
  default: () => null,
}));
vi.mock("./mcp_server_management/MCPServerSelector", () => ({
  __esModule: true,
  default: () => null,
}));

import OrganizationsTable from "./organizations";

describe("OrganizationsTable", () => {
  it("should render the OrganizationsTable component", () => {
    const setOrganizations = vi.fn();

    render(
      <OrganizationsTable
        organizations={[]}
        userRole="Admin"
        userModels={[]}
        accessToken={null}
        setOrganizations={setOrganizations}
        premiumUser={true}
      />,
    );

    expect(screen.getByText("+ Create New Company")).toBeInTheDocument();
  });

  it("should show Companies tenant labels in the management table", () => {
    const setOrganizations = vi.fn();

    render(
      <OrganizationsTable
        organizations={[
          {
            organization_id: "company-1",
            organization_alias: "Acme",
            created_at: "2026-05-17T00:00:00.000Z",
            spend: 0,
            models: [],
            litellm_budget_table: { max_budget: null, tpm_limit: null, rpm_limit: null },
            members: [],
          } as any,
        ]}
        userRole="Admin"
        userModels={[]}
        accessToken="token"
        setOrganizations={setOrganizations}
        premiumUser={true}
      />,
    );

    expect(screen.getByText("Your Companies")).toBeInTheDocument();
    expect(screen.getByText("Company ID")).toBeInTheDocument();
    expect(screen.getByText("Company Name")).toBeInTheDocument();
    expect(screen.queryByText("Organization ID")).not.toBeInTheDocument();
    expect(screen.queryByText("Organization Name")).not.toBeInTheDocument();
  });
});
