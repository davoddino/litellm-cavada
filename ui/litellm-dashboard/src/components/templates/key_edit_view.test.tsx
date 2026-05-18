import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "../../../tests/test-utils";
import { KeyResponse } from "../key_team_helpers/key_list";
import { getGuardrailsList, vectorStoreListCall } from "../networking";
import { KeyEditView } from "./key_edit_view";

const { mockUseProjects, mockUseUISettings } = vi.hoisted(() => ({
  mockUseProjects: vi.fn().mockReturnValue({ data: [], isLoading: false }),
  mockUseUISettings: vi.fn().mockReturnValue({
    data: { values: { enable_projects_ui: false } },
    isLoading: false,
  }),
}));

vi.mock("../networking", async () => {
  const actual = await vi.importActual("../networking");
  return {
    ...actual,
    getPromptsList: vi.fn().mockResolvedValue({
      prompts: [{ prompt_id: "prompt-1" }, { prompt_id: "prompt-2" }],
    }),
    modelAvailableCall: vi.fn().mockResolvedValue({
      data: [{ id: "gpt-4" }, { id: "gpt-3.5-turbo" }],
    }),
    tagListCall: vi.fn().mockResolvedValue({
      tag1: { name: "tag1", description: "Test tag 1" },
      tag2: { name: "tag2", description: "Test tag 2" },
    }),
    getGuardrailsList: vi.fn().mockResolvedValue({
      guardrails: [{ guardrail_name: "guardrail-1" }],
    }),
    getPoliciesList: vi.fn().mockResolvedValue({
      policies: [{ policy_name: "policy-1" }],
    }),
    getPassThroughEndpointsCall: vi.fn().mockResolvedValue({
      endpoints: [],
    }),
    vectorStoreListCall: vi.fn().mockResolvedValue({
      data: [],
    }),
    agentListCall: vi.fn().mockResolvedValue({
      data: [],
    }),
    fetchMCPServers: vi.fn().mockResolvedValue([]),
    fetchMCPAccessGroups: vi.fn().mockResolvedValue([]),
    listMCPTools: vi.fn().mockResolvedValue({
      tools: [],
      error: null,
      message: null,
      stack_trace: null,
    }),
    getAgentsList: vi.fn().mockResolvedValue({
      agents: [],
    }),
    getAgentAccessGroups: vi.fn().mockResolvedValue([]),
  };
});

vi.mock("../organisms/create_key_button", () => ({
  fetchTeamModels: vi.fn().mockResolvedValue(["team-model-1", "team-model-2"]),
}));

vi.mock("@/app/(dashboard)/hooks/organizations/useOrganizations", () => ({
  useOrganizations: vi.fn().mockReturnValue({
    data: [
      { organization_id: "org-1", organization_alias: "Engineering" },
      { organization_id: "org-2", organization_alias: "Sales" },
    ],
    isLoading: false,
  }),
}));

vi.mock("@/app/(dashboard)/hooks/projects/useProjects", () => ({
  useProjects: mockUseProjects,
}));

vi.mock("@/app/(dashboard)/hooks/uiSettings/useUISettings", () => ({
  useUISettings: mockUseUISettings,
}));

vi.mock("../common_components/ProjectDropdown", () => ({
  default: ({
    projects = [],
    value,
    onChange,
    companyId,
  }: {
    projects?: Array<{ project_id: string; project_alias?: string | null; company_id?: string | null }>;
    value?: string;
    onChange?: (value?: string) => void;
    companyId?: string | null;
  }) => {
    const filteredProjects = companyId ? projects.filter((project) => project.company_id === companyId) : projects;
    return (
      <select
        data-testid="project-dropdown"
        value={value || ""}
        onChange={(event) => onChange?.(event.target.value || undefined)}
      >
        <option value="">No Project</option>
        {filteredProjects.map((project) => (
          <option key={project.project_id} value={project.project_id}>
            {project.project_alias || project.project_id}
          </option>
        ))}
      </select>
    );
  },
}));

vi.mock("@/app/(dashboard)/hooks/accessGroups/useAccessGroups", () => ({
  useAccessGroups: vi.fn().mockReturnValue({
    data: [
      { access_group_id: "ag-1", access_group_name: "Group 1" },
      { access_group_id: "ag-2", access_group_name: "Group 2" },
    ],
    isLoading: false,
    isError: false,
  }),
}));

vi.mock("../common_components/AccessGroupSelector", () => ({
  default: ({ value = [], onChange }: { value?: string[]; onChange?: (v: string[]) => void }) => (
    <input
      data-testid="access-group-selector"
      value={Array.isArray(value) ? value.join(",") : ""}
      onChange={(e) => onChange?.(e.target.value ? e.target.value.split(",").map((s) => s.trim()) : [])}
    />
  ),
}));

describe("KeyEditView", () => {
  const MOCK_KEY_DATA: KeyResponse = {
    token: "test-token-123",
    token_id: "test-token-123",
    key_name: "sk-...TUuw",
    key_alias: "asdasdas",
    spend: 0,
    max_budget: 0,
    expires: "null",
    models: [],
    aliases: {},
    config: {},
    user_id: "default_user_id",
    team_id: null,
    project_id: null,
    max_parallel_requests: 10,
    metadata: {
      logging: [],
      tags: ["test-tag"],
    },
    tpm_limit: 10,
    rpm_limit: 10,
    duration: "30d",
    budget_duration: "30d",
    budget_reset_at: "never",
    allowed_cache_controls: [],
    allowed_routes: [],
    permissions: {},
    model_spend: {},
    model_max_budget: {},
    soft_budget_cooldown: false,
    blocked: false,
    litellm_budget_table: {},
    organization_id: null,
    created_at: "2025-10-29T01:26:41.613000Z",
    updated_at: "2025-10-29T01:47:33.980000Z",
    team_spend: 100,
    team_alias: "",
    team_tpm_limit: 100,
    team_rpm_limit: 100,
    team_max_budget: 100,
    team_models: [],
    team_blocked: false,
    soft_budget: 200,
    team_model_aliases: {},
    team_member_spend: 0,
    team_metadata: {},
    end_user_id: "default_user_id",
    end_user_tpm_limit: 10,
    end_user_rpm_limit: 10,
    end_user_max_budget: 0,
    last_refreshed_at: Date.now(),
    api_key: "sk-...TUuw",
    user_role: "user",
    rpm_limit_per_model: {},
    tpm_limit_per_model: {},
    user_tpm_limit: 10,
    user_rpm_limit: 10,
    user_email: "test@example.com",
    object_permission: {
      object_permission_id: "067002ed-3b01-4bb3-b942-cefa400f0049",
      mcp_servers: [],
      mcp_access_groups: [],
      mcp_tool_permissions: {},
      vector_stores: [],
    },
    auto_rotate: false,
    rotation_interval: undefined,
    last_rotation_at: undefined,
    key_rotation_at: undefined,
  };
  it("should render", async () => {
    const { getByText } = renderWithProviders(
      <KeyEditView
        keyData={MOCK_KEY_DATA}
        onCancel={() => {}}
        onSubmit={async () => {}}
        accessToken={""}
        userID={""}
        userRole={""}
        premiumUser={false}
      />,
    );

    await waitFor(() => {
      expect(getByText("Save Changes")).toBeInTheDocument();
    });
  });

  it("should render tags", async () => {
    const { getByText } = renderWithProviders(
      <KeyEditView
        keyData={MOCK_KEY_DATA}
        onCancel={() => {}}
        onSubmit={async () => {}}
        accessToken={""}
        userID={""}
        userRole={""}
        premiumUser={false}
      />,
    );

    await waitFor(() => {
      expect(getByText("test-tag")).toBeInTheDocument();
    });
  });

  it("should not render tags in metadata textarea", async () => {
    const { getByLabelText } = renderWithProviders(
      <KeyEditView
        keyData={MOCK_KEY_DATA}
        onCancel={() => {}}
        onSubmit={async () => {}}
        accessToken={""}
        userID={""}
        userRole={""}
        premiumUser={false}
      />,
    );

    const metadataTextarea = getByLabelText("Metadata") as HTMLTextAreaElement;
    await waitFor(() => {
      expect(metadataTextarea).toHaveValue("{}");
    });
  });

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseProjects.mockReturnValue({ data: [], isLoading: false });
    mockUseUISettings.mockReturnValue({
      data: { values: { enable_projects_ui: false } },
      isLoading: false,
    });
  });

  it("should call onCancel when cancel button is clicked", async () => {
    const onCancelMock = vi.fn();
    renderWithProviders(
      <KeyEditView
        keyData={MOCK_KEY_DATA}
        onCancel={onCancelMock}
        onSubmit={async () => {}}
        accessToken={""}
        userID={""}
        userRole={""}
        premiumUser={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /cancel/i })).toBeInTheDocument();
    });

    const cancelButton = screen.getByRole("button", { name: /cancel/i });
    await userEvent.click(cancelButton);

    expect(onCancelMock).toHaveBeenCalledTimes(1);
  });

  it("should display key alias input field", async () => {
    renderWithProviders(
      <KeyEditView
        keyData={MOCK_KEY_DATA}
        onCancel={() => {}}
        onSubmit={async () => {}}
        accessToken={""}
        userID={""}
        userRole={""}
        premiumUser={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByLabelText("Key Alias")).toBeInTheDocument();
    });
  });

  it("should display models select field", async () => {
    renderWithProviders(
      <KeyEditView
        keyData={MOCK_KEY_DATA}
        onCancel={() => {}}
        onSubmit={async () => {}}
        accessToken={""}
        userID={""}
        userRole={""}
        premiumUser={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Models")).toBeInTheDocument();
    });
  });

  it("should display max budget input field", async () => {
    renderWithProviders(
      <KeyEditView
        keyData={MOCK_KEY_DATA}
        onCancel={() => {}}
        onSubmit={async () => {}}
        accessToken={""}
        userID={""}
        userRole={""}
        premiumUser={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByLabelText("Max Budget (USD)")).toBeInTheDocument();
    });
  });

  it("should display allowed routes input field", async () => {
    renderWithProviders(
      <KeyEditView
        keyData={MOCK_KEY_DATA}
        onCancel={() => {}}
        onSubmit={async () => {}}
        accessToken={""}
        userID={""}
        userRole={""}
        premiumUser={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByLabelText(/allowed routes/i)).toBeInTheDocument();
    });
  });

  it("should call onSubmit with form values when form is submitted", async () => {
    const onSubmitMock = vi.fn().mockResolvedValue(undefined);
    renderWithProviders(
      <KeyEditView
        keyData={MOCK_KEY_DATA}
        onCancel={() => {}}
        onSubmit={onSubmitMock}
        accessToken={"test-token"}
        userID={"test-user"}
        userRole={"admin"}
        premiumUser={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /save changes/i })).toBeInTheDocument();
    });

    const submitButton = screen.getByRole("button", { name: /save changes/i });
    await userEvent.click(submitButton);

    await waitFor(() => {
      expect(onSubmitMock).toHaveBeenCalled();
    });
  });

  it("should disable models field when management routes are selected", async () => {
    const keyDataWithManagementRoutes = {
      ...MOCK_KEY_DATA,
      allowed_routes: ["management_routes"],
    };

    renderWithProviders(
      <KeyEditView
        keyData={keyDataWithManagementRoutes}
        onCancel={() => {}}
        onSubmit={async () => {}}
        accessToken={""}
        userID={""}
        userRole={""}
        premiumUser={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Models field is disabled for this key type")).toBeInTheDocument();
    });
  });

  it("should disable models field when info routes are selected", async () => {
    const keyDataWithInfoRoutes = {
      ...MOCK_KEY_DATA,
      allowed_routes: ["info_routes"],
    };

    renderWithProviders(
      <KeyEditView
        keyData={keyDataWithInfoRoutes}
        onCancel={() => {}}
        onSubmit={async () => {}}
        accessToken={""}
        userID={""}
        userRole={""}
        premiumUser={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Models field is disabled for this key type")).toBeInTheDocument();
    });
  });

  it("should disable guardrails selector when user is not premium and has no write access role", async () => {
    renderWithProviders(
      <KeyEditView
        keyData={MOCK_KEY_DATA}
        onCancel={() => {}}
        onSubmit={async () => {}}
        accessToken={"test-token"}
        userID={""}
        userRole={""}
        premiumUser={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Guardrails")).toBeInTheDocument();
    });
  });

  it("should load scoped guardrails and vector stores with Company and Project context when editing a key", async () => {
    renderWithProviders(
      <KeyEditView
        keyData={{
          ...MOCK_KEY_DATA,
          company_id: "org-1",
          project_id: "project-1",
        }}
        onCancel={() => {}}
        onSubmit={async () => {}}
        accessToken={"test-token"}
        userID={""}
        userRole={"Admin"}
        premiumUser={true}
      />,
    );

    await waitFor(() => {
      expect(vi.mocked(getGuardrailsList)).toHaveBeenCalledWith("test-token", {
        companyId: "org-1",
        projectId: "project-1",
      });
    });

    await waitFor(() => {
      expect(vi.mocked(vectorStoreListCall)).toHaveBeenCalledWith("test-token", 1, 100, {
        company_id: "org-1",
        project_id: "project-1",
      });
    });
  });

  it("should parse comma-separated allowed routes on submit", async () => {
    const onSubmitMock = vi.fn().mockResolvedValue(undefined);
    renderWithProviders(
      <KeyEditView
        keyData={MOCK_KEY_DATA}
        onCancel={() => {}}
        onSubmit={onSubmitMock}
        accessToken={"test-token"}
        userID={"test-user"}
        userRole={"admin"}
        premiumUser={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByLabelText(/allowed routes/i)).toBeInTheDocument();
    });

    const allowedRoutesInput = screen.getByLabelText(/allowed routes/i);
    await userEvent.clear(allowedRoutesInput);
    await userEvent.type(allowedRoutesInput, "route1, route2, route3");

    const submitButton = screen.getByRole("button", { name: /save changes/i });
    await userEvent.click(submitButton);

    await waitFor(() => {
      expect(onSubmitMock).toHaveBeenCalled();
      const callArgs = onSubmitMock.mock.calls[0][0];
      expect(Array.isArray(callArgs.allowed_routes)).toBe(true);
      expect(callArgs.allowed_routes).toEqual(["route1", "route2", "route3"]);
    });
  });

  it("should handle empty allowed routes string on submit", async () => {
    const onSubmitMock = vi.fn().mockResolvedValue(undefined);
    const keyDataWithRoutes = {
      ...MOCK_KEY_DATA,
      allowed_routes: ["llm_api_routes"],
    };
    renderWithProviders(
      <KeyEditView
        keyData={keyDataWithRoutes}
        onCancel={() => {}}
        onSubmit={onSubmitMock}
        accessToken={"test-token"}
        userID={"test-user"}
        userRole={"admin"}
        premiumUser={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByLabelText(/allowed routes/i)).toBeInTheDocument();
    });

    const allowedRoutesInput = screen.getByLabelText(/allowed routes/i);
    await userEvent.clear(allowedRoutesInput);

    const submitButton = screen.getByRole("button", { name: /save changes/i });
    await userEvent.click(submitButton);

    await waitFor(() => {
      expect(onSubmitMock).toHaveBeenCalled();
      const callArgs = onSubmitMock.mock.calls[0][0];
      expect(callArgs.allowed_routes).toEqual([]);
    });
  });

  it("should omit allowed_routes from submit when value is unchanged", async () => {
    const onSubmitMock = vi.fn().mockResolvedValue(undefined);
    const aiApisKeyData = {
      ...MOCK_KEY_DATA,
      allowed_routes: ["llm_api_routes"],
    };
    renderWithProviders(
      <KeyEditView
        keyData={aiApisKeyData}
        onCancel={() => {}}
        onSubmit={onSubmitMock}
        accessToken={"test-token"}
        userID={"test-user"}
        userRole={"admin"}
        premiumUser={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /save changes/i })).toBeInTheDocument();
    });

    const submitButton = screen.getByRole("button", { name: /save changes/i });
    await userEvent.click(submitButton);

    await waitFor(() => {
      expect(onSubmitMock).toHaveBeenCalled();
      const callArgs = onSubmitMock.mock.calls[0][0];
      expect("allowed_routes" in callArgs).toBe(false);
    });
  });

  it("should omit allowed_routes from submit when keyData.allowed_routes is null and form is untouched", async () => {
    const onSubmitMock = vi.fn().mockResolvedValue(undefined);
    const keyDataNullRoutes = {
      ...MOCK_KEY_DATA,
      allowed_routes: null as unknown as string[],
    };
    renderWithProviders(
      <KeyEditView
        keyData={keyDataNullRoutes}
        onCancel={() => {}}
        onSubmit={onSubmitMock}
        accessToken={"test-token"}
        userID={"test-user"}
        userRole={"admin"}
        premiumUser={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /save changes/i })).toBeInTheDocument();
    });

    const submitButton = screen.getByRole("button", { name: /save changes/i });
    await userEvent.click(submitButton);

    await waitFor(() => {
      expect(onSubmitMock).toHaveBeenCalled();
      const callArgs = onSubmitMock.mock.calls[0][0];
      expect("allowed_routes" in callArgs).toBe(false);
    });
  });

  it("should omit allowed_routes from submit when server returned routes in a different order", async () => {
    const onSubmitMock = vi.fn().mockResolvedValue(undefined);
    const keyDataReordered = {
      ...MOCK_KEY_DATA,
      allowed_routes: ["beta_routes", "alpha_routes"],
    };
    renderWithProviders(
      <KeyEditView
        keyData={keyDataReordered}
        onCancel={() => {}}
        onSubmit={onSubmitMock}
        accessToken={"test-token"}
        userID={"test-user"}
        userRole={"admin"}
        premiumUser={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /save changes/i })).toBeInTheDocument();
    });

    const submitButton = screen.getByRole("button", { name: /save changes/i });
    await userEvent.click(submitButton);

    await waitFor(() => {
      expect(onSubmitMock).toHaveBeenCalled();
      const callArgs = onSubmitMock.mock.calls[0][0];
      expect("allowed_routes" in callArgs).toBe(false);
    });
  });

  it("should pass access_group_ids to onSubmit when saving key with access groups", async () => {
    const onSubmitMock = vi.fn().mockResolvedValue(undefined);
    const keyDataWithAccessGroups = {
      ...MOCK_KEY_DATA,
      access_group_ids: ["ag-1"],
    };

    renderWithProviders(
      <KeyEditView
        keyData={keyDataWithAccessGroups}
        onCancel={() => {}}
        onSubmit={onSubmitMock}
        accessToken="test-token"
        userID="test-user"
        userRole="admin"
        premiumUser={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("access-group-selector")).toBeInTheDocument();
    });

    const accessGroupInput = screen.getByTestId("access-group-selector");
    await userEvent.clear(accessGroupInput);
    await userEvent.type(accessGroupInput, "ag-1,ag-2");

    const submitButton = screen.getByRole("button", { name: /save changes/i });
    await userEvent.click(submitButton);

    await waitFor(() => {
      expect(onSubmitMock).toHaveBeenCalled();
      const callArgs = onSubmitMock.mock.calls[0][0];
      expect(callArgs.access_group_ids).toEqual(["ag-1", "ag-2"]);
    });
  });

  it("should display 'AI APIs' label for the llm_api key type option", async () => {
    const keyDataWithLlmApiRoutes = {
      ...MOCK_KEY_DATA,
      allowed_routes: ["llm_api_routes"],
    };

    renderWithProviders(
      <KeyEditView
        keyData={keyDataWithLlmApiRoutes}
        onCancel={() => {}}
        onSubmit={async () => {}}
        accessToken={""}
        userID={""}
        userRole={""}
        premiumUser={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Key Type")).toBeInTheDocument();
    });

    // The selected key type label should show "AI APIs" (not "LLM API")
    const keyTypeSection = screen.getByText("Key Type").closest(".ant-form-item")!;
    expect(keyTypeSection).toBeInTheDocument();

    // Open the dropdown to see all options
    const selectElement = keyTypeSection.querySelector(".ant-select-selector")!;
    await userEvent.click(selectElement);

    await waitFor(() => {
      // Verify "AI APIs" appears as an option label
      const options = document.querySelectorAll(".ant-select-item-option");
      const optionTexts = Array.from(options).map((el) => el.textContent);
      const hasAIAPIs = optionTexts.some((text) => text?.includes("AI APIs"));
      expect(hasAIAPIs).toBe(true);

      // Verify old "LLM API" label does NOT appear
      const hasLLMAPI = optionTexts.some((text) => text?.includes("LLM API"));
      expect(hasLLMAPI).toBe(false);
    });
  });

  it("should display cancel button during submission", async () => {
    let resolveSubmit: (() => void) | undefined;
    const submitPromise = new Promise<void>((resolve) => {
      resolveSubmit = resolve;
    });
    const onSubmitMock = vi.fn(() => submitPromise);

    renderWithProviders(
      <KeyEditView
        keyData={MOCK_KEY_DATA}
        onCancel={() => {}}
        onSubmit={onSubmitMock}
        accessToken={"test-token"}
        userID={"test-user"}
        userRole={"admin"}
        premiumUser={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /cancel/i })).toBeInTheDocument();
    });

    const submitButton = screen.getByRole("button", { name: /save changes/i });
    await userEvent.click(submitButton);

    // Wait for onSubmit to be called, which means handleSubmit has started and isKeySaving should be true
    await waitFor(() => {
      expect(onSubmitMock).toHaveBeenCalled();
    });

    // Wait for the cancel button to actually be disabled (state update may take a moment)
    await waitFor(
      () => {
        const cancelButton = screen.getByRole("button", { name: /cancel/i });
        expect(cancelButton).toBeDisabled();
      },
      { timeout: 3000 },
    );

    // Clean up: resolve the promise to allow the form to complete
    if (resolveSubmit) {
      resolveSubmit();
    }
  });

  describe("company dropdown", () => {
    it("should render the company dropdown", async () => {
      renderWithProviders(
        <KeyEditView
          keyData={MOCK_KEY_DATA}
          onCancel={() => {}}
          onSubmit={async () => {}}
          accessToken=""
          userID=""
          userRole="Admin"
          premiumUser={false}
        />,
      );

      await waitFor(() => {
        expect(screen.getByText("Company")).toBeInTheDocument();
      });
    });

    it("should leave the company dropdown enabled for server-side RBAC enforcement", async () => {
      const { container } = renderWithProviders(
        <KeyEditView
          keyData={MOCK_KEY_DATA}
          onCancel={() => {}}
          onSubmit={async () => {}}
          accessToken=""
          userID=""
          userRole="Internal User"
          premiumUser={false}
        />,
      );

      await waitFor(() => {
        expect(screen.getByText("Company")).toBeInTheDocument();
      });

      const orgFormItem = screen.getByText("Company").closest(".ant-form-item");
      const disabledSelect = orgFormItem?.querySelector(".ant-select-disabled");
      expect(disabledSelect).toBeFalsy();
    });

    it("should not disable the company dropdown for admin users", async () => {
      const { container } = renderWithProviders(
        <KeyEditView
          keyData={MOCK_KEY_DATA}
          onCancel={() => {}}
          onSubmit={async () => {}}
          accessToken=""
          userID=""
          userRole="Admin"
          premiumUser={false}
        />,
      );

      await waitFor(() => {
        expect(screen.getByText("Company")).toBeInTheDocument();
      });

      const orgFormItem = screen.getByText("Company").closest(".ant-form-item");
      const disabledSelect = orgFormItem?.querySelector(".ant-select-disabled");
      expect(disabledSelect).toBeFalsy();
    });

    it("should initialize company from keyData", async () => {
      const keyWithOrg = {
        ...MOCK_KEY_DATA,
        organization_id: "org-1",
      };

      renderWithProviders(
        <KeyEditView
          keyData={keyWithOrg}
          onCancel={() => {}}
          onSubmit={async () => {}}
          accessToken=""
          userID=""
          userRole="Admin"
          premiumUser={false}
        />,
      );

      await waitFor(() => {
        expect(screen.getByText("Engineering")).toBeInTheDocument();
      });
    });

    it("should submit company_id without legacy organization aliases", async () => {
      const onSubmitMock = vi.fn().mockResolvedValue(undefined);
      const keyWithCompanyAliases = {
        ...MOCK_KEY_DATA,
        company_id: "org-1",
        org_id: "org-1",
        organization_id: "org-1",
        organization_ids: ["org-1"],
        organizations: ["org-1"],
      } as KeyResponse;

      renderWithProviders(
        <KeyEditView
          keyData={keyWithCompanyAliases}
          onCancel={() => {}}
          onSubmit={onSubmitMock}
          accessToken=""
          userID=""
          userRole="Admin"
          premiumUser={false}
        />,
      );

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /save changes/i })).toBeInTheDocument();
      });

      await userEvent.click(screen.getByRole("button", { name: /save changes/i }));

      await waitFor(() => {
        expect(onSubmitMock).toHaveBeenCalled();
      });

      const submittedValues = onSubmitMock.mock.calls[0][0];
      expect(submittedValues.company_id).toBe("org-1");
      expect(submittedValues).not.toHaveProperty("org_id");
      expect(submittedValues).not.toHaveProperty("organization_id");
      expect(submittedValues).not.toHaveProperty("organization_ids");
      expect(submittedValues).not.toHaveProperty("organizations");
    });

    it("should derive company and team from the selected project context", async () => {
      mockUseUISettings.mockReturnValue({
        data: { values: { enable_projects_ui: true } },
        isLoading: false,
      });
      mockUseProjects.mockReturnValue({
        data: [
          {
            project_id: "project-1",
            project_alias: "Support Project",
            company_id: "org-1",
            team_id: "team-1",
            models: [],
          },
        ],
        isLoading: false,
      });

      const keyWithProject = {
        ...MOCK_KEY_DATA,
        project_id: "project-1",
        company_id: "org-2",
        organization_id: "org-2",
        team_id: "team-2",
      };
      const onSubmitMock = vi.fn().mockResolvedValue(undefined);

      renderWithProviders(
        <KeyEditView
          keyData={keyWithProject}
          teams={[
            { team_id: "team-1", team_alias: "Team One", organization_id: "org-1", models: [] },
            { team_id: "team-2", team_alias: "Team Two", organization_id: "org-2", models: [] },
          ]}
          onCancel={() => {}}
          onSubmit={onSubmitMock}
          accessToken=""
          userID=""
          userRole="Admin"
          premiumUser={false}
        />,
      );

      await waitFor(() => {
        expect(screen.getByText("Company is derived from the selected project")).toBeInTheDocument();
        expect(screen.getByText("Team is derived from the selected project")).toBeInTheDocument();
      });

      const companyFormItem = screen.getByText("Company").closest(".ant-form-item");
      const teamFormItem = screen.getByText("Team ID").closest(".ant-form-item");
      const projectFormItem = screen.getByText("Project").closest(".ant-form-item");

      expect(companyFormItem?.querySelector(".ant-select-disabled")).toBeTruthy();
      expect(teamFormItem?.querySelector(".ant-select-disabled")).toBeTruthy();
      expect(projectFormItem?.querySelector(".ant-select-disabled")).toBeFalsy();
      expect(screen.getByText("Support Project")).toBeInTheDocument();

      await userEvent.click(screen.getByRole("button", { name: /save changes/i }));

      await waitFor(() => {
        expect(onSubmitMock).toHaveBeenCalled();
      });

      const submittedValues = onSubmitMock.mock.calls[0][0];
      expect(submittedValues.project_id).toBe("project-1");
      expect(submittedValues.company_id).toBe("org-1");
      expect(submittedValues.team_id).toBe("team-1");
      expect(submittedValues).not.toHaveProperty("organization_id");
      expect(submittedValues).not.toHaveProperty("org_id");
    });

    it("should submit project_id null when an existing project is cleared", async () => {
      mockUseUISettings.mockReturnValue({
        data: { values: { enable_projects_ui: true } },
        isLoading: false,
      });
      mockUseProjects.mockReturnValue({
        data: [
          {
            project_id: "project-1",
            project_alias: "Support Project",
            company_id: "org-1",
            team_id: "team-1",
            models: [],
          },
        ],
        isLoading: false,
      });

      const onSubmitMock = vi.fn().mockResolvedValue(undefined);

      renderWithProviders(
        <KeyEditView
          keyData={{
            ...MOCK_KEY_DATA,
            project_id: "project-1",
            company_id: "org-1",
            organization_id: "org-1",
            team_id: "team-1",
          }}
          teams={[{ team_id: "team-1", team_alias: "Team One", organization_id: "org-1", models: [] }]}
          onCancel={() => {}}
          onSubmit={onSubmitMock}
          accessToken=""
          userID=""
          userRole="Admin"
          premiumUser={false}
        />,
      );

      await waitFor(() => {
        expect(screen.getByTestId("project-dropdown")).toBeInTheDocument();
      });

      await userEvent.selectOptions(screen.getByTestId("project-dropdown"), "");
      await userEvent.click(screen.getByRole("button", { name: /save changes/i }));

      await waitFor(() => {
        expect(onSubmitMock).toHaveBeenCalled();
      });

      const submittedValues = onSubmitMock.mock.calls[0][0];
      expect(submittedValues.project_id).toBeNull();
    });
  });
});
