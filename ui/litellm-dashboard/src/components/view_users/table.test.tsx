import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { columns } from "./columns";
import { UserDataTable } from "./table";
import { UserInfo } from "./types";

vi.mock("@tremor/react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@tremor/react")>();
  const React = await import("react");
  return {
    ...actual,
    Select: ({ value, onValueChange, placeholder, children }: any) =>
      React.createElement(
        "select",
        {
          "aria-label": placeholder,
          value,
          onChange: (event: any) => onValueChange?.(event.target.value),
        },
        children,
      ),
    SelectItem: ({ value, children }: any) => React.createElement("option", { value }, children),
  };
});

const defaultFilters = {
  email: "",
  user_id: "",
  user_role: "",
  sso_user_id: "",
  team: "",
  company_id: "",
  project_id: "",
  model: "",
  min_spend: null,
  max_spend: null,
  sort_by: "",
  sort_order: "asc" as const,
};

const getDefaultProps = () => ({
  data: [] as any[],
  columns: [] as any[],
  accessToken: null,
  userRole: "Admin",
  possibleUIRoles: null as Record<string, Record<string, string>> | null,
  filters: defaultFilters,
  updateFilters: vi.fn(),
  initialFilters: defaultFilters,
  teams: [] as any[],
  organizations: [
    {
      organization_id: "legacy-org-1",
      organization_alias: "Legacy Organization Alias",
      company_id: "company-1",
      company_name: "Company One",
    },
  ] as any[],
  projects: [{ project_id: "project-1", project_alias: "Project One", company_id: "company-1" }] as any[],
  handleEdit: vi.fn(),
  handleDelete: vi.fn(),
  handleResetPassword: vi.fn(),
  userListResponse: { users: [], total: 0, page: 1, page_size: 25, total_pages: 1 },
  currentPage: 1,
  handlePageChange: vi.fn(),
});

describe("UserDataTable", () => {
  it("should render the UserDataTable component", () => {
    render(<UserDataTable {...getDefaultProps()} />);

    expect(screen.getByText("Filters")).toBeInTheDocument();
  });

  it("should call onSortChange when clicking a sortable header", () => {
    const filters = {
      ...defaultFilters,
      sort_by: "created_at",
      sort_order: "desc" as const,
    };

    const onSortChange = vi.fn();

    const possibleUIRoles = {
      admin: { ui_label: "Admin" },
      user: { ui_label: "User" },
    };

    render(
      <UserDataTable
        {...getDefaultProps()}
        possibleUIRoles={possibleUIRoles}
        filters={filters}
        initialFilters={filters}
        onSortChange={onSortChange}
        currentSort={{ sortBy: filters.sort_by, sortOrder: filters.sort_order }}
      />,
    );

    const emailHeader = screen.getByRole("columnheader", { name: /email/i });
    act(() => {
      fireEvent.click(emailHeader);
    });

    expect(onSortChange).toHaveBeenCalledWith("user_email", "desc");
  });

  it("should show skeleton loaders when isLoading is true", () => {
    render(<UserDataTable {...getDefaultProps()} isLoading={true} />);

    expect(screen.queryByText(/Showing/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Previous/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Next/i })).not.toBeInTheDocument();
  });

  it("should show actual content when isLoading is false", () => {
    render(<UserDataTable {...getDefaultProps()} isLoading={false} />);

    expect(screen.getByText(/Showing/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Previous/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Next/i })).toBeInTheDocument();
  });

  it("should render all column headers", () => {
    const possibleUIRoles = {
      admin: { ui_label: "Admin" },
      user: { ui_label: "User" },
    };

    render(<UserDataTable {...getDefaultProps()} possibleUIRoles={possibleUIRoles} />);

    [
      "User ID",
      "Email",
      "Status",
      "Global Proxy Role",
      "Company",
      "Project",
      "User Alias",
      "Spend (USD)",
      "Budget (USD)",
      "SSO ID",
      "Virtual Keys",
      "Created At",
      "Updated At",
      "Actions",
    ].forEach((header) => {
      expect(screen.getByRole("columnheader", { name: header })).toBeInTheDocument();
    });
  });

  it("should render Company filter labels from product fields and no Organization copy", () => {
    render(<UserDataTable {...getDefaultProps()} />);

    act(() => {
      fireEvent.click(screen.getByText("Filters"));
    });

    expect(screen.getByText("Company One")).toBeInTheDocument();
    expect(screen.queryByText("Legacy Organization Alias")).not.toBeInTheDocument();
    expect(screen.queryByText(/Organization/)).not.toBeInTheDocument();
  });

  it("should update Company filters with product company_id and clear stale Project", () => {
    const updateFilters = vi.fn();
    render(<UserDataTable {...getDefaultProps()} updateFilters={updateFilters} />);

    act(() => {
      fireEvent.click(screen.getByText("Filters"));
    });

    act(() => {
      fireEvent.change(screen.getByLabelText("Select Company"), { target: { value: "company-1" } });
    });

    expect(updateFilters).toHaveBeenCalledWith({ company_id: "company-1", project_id: "" });
    expect(updateFilters).not.toHaveBeenCalledWith({ company_id: "legacy-org-1", project_id: "" });
  });

  it("should render the user-row Status cell as Active when scim_active is not set to false", () => {
    const possibleUIRoles = { admin: { ui_label: "Admin" } };
    const handlers = { edit: vi.fn(), del: vi.fn(), reset: vi.fn(), click: vi.fn() };
    const cols = columns(
      possibleUIRoles,
      handlers.edit,
      handlers.del,
      handlers.reset,
      handlers.click,
    );
    const statusCol = cols.find((c) => (c as { id?: string }).id === "status");
    expect(statusCol).toBeDefined();

    const baseUser: UserInfo = {
      user_id: "u-active",
      user_email: "active@example.com",
      user_alias: null,
      user_role: "admin",
      spend: 0,
      max_budget: null,
      models: [],
      key_count: 0,
      created_at: "",
      updated_at: "",
      sso_user_id: null,
      budget_duration: null,
    };

    const cellNoMetadata = (statusCol as any).cell({ row: { original: baseUser } });
    render(<>{cellNoMetadata}</>);
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.queryByText("Inactive")).not.toBeInTheDocument();
  });

  it("should render the user-row Status cell as Inactive when scim_active is false", () => {
    const possibleUIRoles = { admin: { ui_label: "Admin" } };
    const cols = columns(possibleUIRoles, vi.fn(), vi.fn(), vi.fn(), vi.fn());
    const statusCol = cols.find((c) => (c as { id?: string }).id === "status")!;

    const inactiveUser: UserInfo = {
      user_id: "u-inactive",
      user_email: "alex@acme.io",
      user_alias: null,
      user_role: "internal_user",
      spend: 0,
      max_budget: null,
      models: [],
      key_count: 1,
      created_at: "",
      updated_at: "",
      sso_user_id: null,
      budget_duration: null,
      metadata: { scim_active: false },
    };

    const cell = (statusCol as any).cell({ row: { original: inactiveUser } });
    render(<>{cell}</>);
    expect(screen.getByText("Inactive")).toBeInTheDocument();
    expect(screen.queryByText("Active")).not.toBeInTheDocument();
  });

  it("should treat scim_active=true as Active (not Inactive)", () => {
    const possibleUIRoles = { admin: { ui_label: "Admin" } };
    const cols = columns(possibleUIRoles, vi.fn(), vi.fn(), vi.fn(), vi.fn());
    const statusCol = cols.find((c) => (c as { id?: string }).id === "status")!;

    const reactivated: UserInfo = {
      user_id: "u-rehired",
      user_email: "alex@acme.io",
      user_alias: null,
      user_role: "internal_user",
      spend: 0,
      max_budget: null,
      models: [],
      key_count: 1,
      created_at: "",
      updated_at: "",
      sso_user_id: null,
      budget_duration: null,
      metadata: { scim_active: true },
    };

    const cell = (statusCol as any).cell({ row: { original: reactivated } });
    render(<>{cell}</>);
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.queryByText("Inactive")).not.toBeInTheDocument();
  });
});
