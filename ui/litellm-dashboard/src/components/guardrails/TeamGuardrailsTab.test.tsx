import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TeamGuardrailsTab } from "./TeamGuardrailsTab";
import {
  listGuardrailSubmissions,
  approveGuardrailSubmission,
  rejectGuardrailSubmission,
  updateGuardrailCall,
} from "@/components/networking";
import { useRegisterGuardrail } from "@/app/(dashboard)/hooks/guardrails/useRegisterGuardrail";

const mockRegisterGuardrail = vi.fn();

vi.mock("@/components/networking", () => ({
  listGuardrailSubmissions: vi.fn(),
  approveGuardrailSubmission: vi.fn(),
  rejectGuardrailSubmission: vi.fn(),
  updateGuardrailCall: vi.fn(),
}));

vi.mock("@/components/molecules/notifications_manager", () => ({
  default: {
    success: vi.fn(),
    fromBackend: vi.fn(),
  },
}));

vi.mock("@/app/(dashboard)/hooks/guardrails/useRegisterGuardrail", () => ({
  useRegisterGuardrail: vi.fn(),
}));

vi.mock("@/app/(dashboard)/hooks/organizations/useOrganizations", () => ({
  useOrganizations: () => ({
    data: [
      {
        organization_id: "company-1",
        company_id: "company-1",
        company_name: "Acme",
        organization_alias: "Acme",
      },
    ],
    isLoading: false,
  }),
}));

vi.mock("@/app/(dashboard)/hooks/projects/useProjects", () => ({
  useProjects: () => ({
    data: [
      {
        project_id: "project-1",
        project_alias: "Risk Review",
        company_id: "company-1",
        team_id: "team-project",
      },
    ],
    isLoading: false,
  }),
}));

vi.mock("@/components/common_components/OrganizationDropdown", () => ({
  default: ({ organizations, value, onChange, disabled }: any) => (
    <select
      aria-label="Company"
      value={value ?? ""}
      disabled={disabled}
      onChange={(event) => onChange?.(event.target.value || undefined)}
    >
      <option value="">All Companies</option>
      {organizations?.map((company: any) => (
        <option key={company.company_id} value={company.company_id}>
          {company.company_name}
        </option>
      ))}
    </select>
  ),
}));

vi.mock("@/components/common_components/ProjectDropdown", () => ({
  default: ({ projects, value, onChange, companyId, disabled }: any) => (
    <select
      aria-label="Project"
      value={value ?? ""}
      disabled={disabled}
      onChange={(event) => onChange?.(event.target.value || undefined)}
    >
      <option value="">All Projects</option>
      {projects
        ?.filter((project: any) => !companyId || project.company_id === companyId)
        .map((project: any) => (
          <option key={project.project_id} value={project.project_id}>
            {project.project_alias}
          </option>
        ))}
    </select>
  ),
}));

describe("TeamGuardrailsTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useRegisterGuardrail).mockReturnValue({
      mutateAsync: mockRegisterGuardrail,
    } as any);
    vi.mocked(listGuardrailSubmissions).mockResolvedValue({
      submissions: [
        {
          guardrail_id: "guardrail-1",
          guardrail_name: "PII policy",
          status: "pending_review",
          company_id: "company-1",
          company_name: "Acme",
          project_id: "project-1",
          project_name: "Risk Review",
          litellm_params: {
            guardrail: "generic_guardrail_api",
            api_base: "https://guardrails.example.com",
            mode: "pre_call",
          },
          guardrail_info: {
            description: "Detects PII",
          },
          submitted_at: "2026-05-18T00:00:00Z",
          submitted_by_email: "alice@example.com",
        },
      ],
      summary: {
        total: 1,
        pending_review: 1,
        active: 0,
        rejected: 0,
      },
    });
    vi.mocked(approveGuardrailSubmission).mockResolvedValue({
      guardrail_id: "guardrail-1",
      status: "active",
      message: "ok",
    });
    vi.mocked(rejectGuardrailSubmission).mockResolvedValue({
      guardrail_id: "guardrail-1",
      status: "rejected",
      message: "ok",
    });
    vi.mocked(updateGuardrailCall).mockResolvedValue({} as any);
    mockRegisterGuardrail.mockResolvedValue({
      guardrail_id: "guardrail-2",
      guardrail_name: "new-policy",
      status: "pending_review",
    });
  });

  it("should show and filter guardrail submissions by Company and Project", async () => {
    render(<TeamGuardrailsTab accessToken="token" />);

    expect(await screen.findByText("Company: Acme")).toBeInTheDocument();
    expect(screen.getByText("Project: Risk Review")).toBeInTheDocument();
    expect(screen.queryByText(/Team:/)).not.toBeInTheDocument();

    await act(async () => {
      fireEvent.change(screen.getAllByLabelText("Company")[0], {
        target: { value: "company-1" },
      });
    });
    await act(async () => {
      fireEvent.change(screen.getAllByLabelText("Project")[0], {
        target: { value: "project-1" },
      });
    });

    await waitFor(() => {
      expect(listGuardrailSubmissions).toHaveBeenLastCalledWith("token", {
        status: undefined,
        company_id: "company-1",
        project_id: "project-1",
        search: undefined,
      });
    });
  });

  it("should submit guardrails with Company and Project payload only", async () => {
    render(<TeamGuardrailsTab accessToken="token" />);
    await screen.findByText("Company: Acme");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /add guardrail/i }));
    });
    await act(async () => {
      fireEvent.change(screen.getAllByLabelText("Company")[1], {
        target: { value: "company-1" },
      });
    });
    await act(async () => {
      fireEvent.change(screen.getAllByLabelText("Project")[1], {
        target: { value: "project-1" },
      });
    });
    await act(async () => {
      fireEvent.change(screen.getByPlaceholderText("e.g. pii-detection"), {
        target: { value: "new-policy" },
      });
      fireEvent.change(
        screen.getByPlaceholderText("https://your-guardrail-api.com/v1/check"),
        {
          target: { value: "https://guardrails.example.com/v1/check" },
        },
      );
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Submit for Review" }));
    });

    await waitFor(() => {
      expect(mockRegisterGuardrail).toHaveBeenCalled();
    });
    const payload = mockRegisterGuardrail.mock.calls[0][0];
    expect(payload.company_id).toBe("company-1");
    expect(payload.project_id).toBe("project-1");
    expect(payload.team_id).toBeUndefined();
  });
});
