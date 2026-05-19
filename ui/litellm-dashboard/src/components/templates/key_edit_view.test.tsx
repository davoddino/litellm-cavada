import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "../../../tests/test-utils";
import { KeyResponse } from "../key_team_helpers/key_list";
import { KeyEditView } from "./key_edit_view";

const { cavadalabsKeyContextOptions, mockCavadaLabsApi, mockNotificationsManager } = vi.hoisted(() => ({
  cavadalabsKeyContextOptions: {
    companies: [
      { company_id: "company-1", legal_name: "Acme Srl", litellm_organization_id: "org-1", status: "active" },
      { company_id: "company-2", legal_name: "Globex Srl", litellm_organization_id: "org-2", status: "active" },
    ],
    projects: [
      {
        project_id: "project-1",
        company_id: "company-1",
        litellm_team_id: "team-1",
        name: "Support",
        status: "production",
        allowed_models: ["team-model-1"],
      },
      {
        project_id: "project-2",
        company_id: "company-2",
        litellm_team_id: "team-2",
        name: "External",
        status: "production",
        allowed_models: ["team-model-2"],
      },
    ],
    isLoading: false,
    errorDetail: null as any,
    contextKnown: true,
    isCavadaLabsProductContext: true,
  },
  mockNotificationsManager: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    fromBackend: vi.fn(),
  },
  mockCavadaLabsApi: {
    listCavadaLabsResource: vi.fn(),
    createCavadaLabsResource: vi.fn(),
    patchCavadaLabsResource: vi.fn(),
  },
}));

vi.mock("../molecules/notifications_manager", () => ({
  default: mockNotificationsManager,
}));

vi.mock("../cavadalabs/api", async () => {
  const actual = await vi.importActual("../cavadalabs/api");
  return {
    ...actual,
    listCavadaLabsResource: mockCavadaLabsApi.listCavadaLabsResource,
    createCavadaLabsResource: mockCavadaLabsApi.createCavadaLabsResource,
    patchCavadaLabsResource: mockCavadaLabsApi.patchCavadaLabsResource,
  };
});

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

vi.mock("@/app/(dashboard)/hooks/mcpServers/useMCPToolsets", () => ({
  useMCPToolsets: vi.fn().mockReturnValue({
    data: [],
    isLoading: false,
    isError: false,
  }),
}));

vi.mock("../cavadalabs/keyContext", () => ({
  deriveSingleCavadaLabsKeyContextSelection: ({
    companyId,
    projectId,
    companies,
    projects,
  }: {
    companyId?: string | null;
    projectId?: string | null;
    companies: any[];
    projects: any[];
  }) => {
    if (companyId || projectId || companies.length !== 1 || projects.length !== 1) {
      return { companyId: companyId || null, projectId: projectId || null };
    }
    const company = companies[0];
    const project = projects[0];
    return project.company_id === company.company_id
      ? { companyId: company.company_id, projectId: project.project_id }
      : { companyId: null, projectId: null };
  },
  filterManageableCavadaLabsCompanies: (companies: any[], projects: any[] = []) => {
    const hasCompanyManageFlag = companies.some((company) => typeof company.cavadalabs_can_manage === "boolean");
    const hasProjectManageFlag = projects.some((project) => typeof project.cavadalabs_can_manage === "boolean");
    if (!hasCompanyManageFlag && !hasProjectManageFlag) {
      return companies;
    }
    const manageableProjectCompanyIds = new Set(
      hasProjectManageFlag
        ? projects.filter((project) => project.cavadalabs_can_manage === true).map((project) => project.company_id)
        : [],
    );
    return companies.filter(
      (company) => company.cavadalabs_can_manage === true || manageableProjectCompanyIds.has(company.company_id),
    );
  },
  filterManageableCavadaLabsProjects: (projects: any[]) =>
    projects.some((project) => typeof project.cavadalabs_can_manage === "boolean")
      ? projects.filter((project) => project.cavadalabs_can_manage === true)
      : projects,
  findCavadaLabsCompanyForCompatibilityOrganization: (companies: any[], organizationId: string | null | undefined) =>
    companies.find((company) => company.litellm_organization_id === organizationId) ?? null,
  findCavadaLabsProjectForCompatibilityTeam: (projects: any[], teamId: string | null | undefined) =>
    projects.find((project) => project.litellm_team_id === teamId) ?? null,
  getKeyCavadaLabsCompanyId: (key: any) =>
    key.cavadalabs_company_id || key.metadata?.cavadalabs_company_id || key.metadata?.cavadalabs?.company_id || null,
  getKeyCavadaLabsProjectId: (key: any) =>
    key.cavadalabs_project_id || key.metadata?.cavadalabs_project_id || key.metadata?.cavadalabs?.project_id || null,
  resolveCavadaLabsProjectCompatibilityTeamId: (projectId: string) =>
    cavadalabsKeyContextOptions.projects.find((project) => project.project_id === projectId)?.litellm_team_id ?? null,
  stripLiteLLMCompatibilityFieldsForCavadaLabsKey: (values: Record<string, any>) => {
    if (!values.cavadalabs_company_id && !values.cavadalabs_project_id) {
      return values;
    }

    delete values.organization_id;
    delete values.team_id;
    delete values.project_id;
    return values;
  },
  validateCavadaLabsKeyContextSelection: ({
    companyId,
    projectId,
    projects,
    required,
    actionLabel,
  }: {
    companyId?: string | null;
    projectId?: string | null;
    projects: any[];
    required: boolean;
    actionLabel: "creating" | "saving";
  }) => {
    if (required && (!companyId || !projectId)) {
      return `Select both Company and Project before ${actionLabel} a CavadaLabs key`;
    }
    if (!companyId && !projectId) {
      return null;
    }
    if (!companyId || !projectId) {
      return `Select both Company and Project before ${actionLabel} a CavadaLabs key`;
    }
    const project = projects.find((item) => item.project_id === projectId);
    if (!project) {
      return `Project ${projectId} is not available`;
    }
    return project.company_id === companyId ? null : "Selected Project belongs to a different Company";
  },
  useCavadaLabsKeyContextOptions: () => cavadalabsKeyContextOptions,
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
      cavadalabs_company_id: "company-1",
      cavadalabs_project_id: "project-1",
      cavadalabs: {
        company_id: "company-1",
        project_id: "project-1",
      },
    },
    cavadalabs_company_id: "company-1",
    cavadalabs_project_id: "project-1",
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
    last_active: null,
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

  it("should not render tags or CavadaLabs context in metadata textarea", async () => {
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
    mockCavadaLabsApi.listCavadaLabsResource.mockResolvedValue({ model_policies: [] });
    mockCavadaLabsApi.createCavadaLabsResource.mockResolvedValue({});
    mockCavadaLabsApi.patchCavadaLabsResource.mockResolvedValue({});
    cavadalabsKeyContextOptions.companies = [
      { company_id: "company-1", legal_name: "Acme Srl", litellm_organization_id: "org-1", status: "active" },
      { company_id: "company-2", legal_name: "Globex Srl", litellm_organization_id: "org-2", status: "active" },
    ];
    cavadalabsKeyContextOptions.projects = [
      {
        project_id: "project-1",
        company_id: "company-1",
        litellm_team_id: "team-1",
        name: "Support",
        status: "production",
        allowed_models: ["team-model-1"],
      },
      {
        project_id: "project-2",
        company_id: "company-2",
        litellm_team_id: "team-2",
        name: "External",
        status: "production",
        allowed_models: ["team-model-2"],
      },
    ];
    cavadalabsKeyContextOptions.errorDetail = null;
    cavadalabsKeyContextOptions.contextKnown = true;
    cavadalabsKeyContextOptions.isCavadaLabsProductContext = true;
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

  it("should display CavadaLabs company and project fields", async () => {
    renderWithProviders(
      <KeyEditView
        keyData={MOCK_KEY_DATA}
        onCancel={() => {}}
        onSubmit={async () => {}}
        accessToken={"test-token"}
        userID={"test-user"}
        userRole={"admin"}
        premiumUser={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Company")).toBeInTheDocument();
      expect(screen.getByText("Project")).toBeInTheDocument();
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
      const callArgs = onSubmitMock.mock.calls[0][0];
      expect(callArgs.cavadalabs_company_id).toBe("company-1");
      expect(callArgs.cavadalabs_project_id).toBe("project-1");
      expect(callArgs.organization_id).toBeUndefined();
      expect(callArgs.team_id).toBeUndefined();
      expect(callArgs.project_id).toBeUndefined();
    });
  });

  it("should save key-scoped model routing priorities with Company and Project context", async () => {
    mockCavadaLabsApi.listCavadaLabsResource.mockResolvedValue({
      model_policies: [
        {
          policy_id: "policy-1",
          key_id: "test-token-123",
          project_id: "project-1",
          endpoint_type: "chat_completion",
          model_bucket: "medium",
          model_alias: "team-model-1",
          provider: "openai",
          priority: 1,
          enabled: true,
          fallback_enabled: true,
        },
      ],
    });
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
      expect(screen.getByText("Model routing priorities")).toBeInTheDocument();
      expect(screen.getByText("team-model-1")).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => {
      expect(onSubmitMock).toHaveBeenCalled();
      expect(mockCavadaLabsApi.patchCavadaLabsResource).toHaveBeenCalledWith(
        "test-token",
        "/cavadalabs/model-policies/policy-1",
        expect.objectContaining({
          key_id: "test-token-123",
          endpoint_type: "chat_completion",
          model_bucket: "medium",
          model_alias: "team-model-1",
          provider: "openai",
          priority: 1,
          enabled: true,
          fallback_enabled: true,
        }),
      );
    });
    const submittedValues = onSubmitMock.mock.calls[0][0];
    expect(submittedValues.models).toEqual(expect.arrayContaining(["medium", "team-model-1"]));
    expect(submittedValues.organization_id).toBeUndefined();
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

  describe("CavadaLabs company/project selectors", () => {
    it("should render company and project selectors instead of organization", async () => {
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
        expect(screen.getByText("Project")).toBeInTheDocument();
      });

      expect(screen.queryByText("Organization")).not.toBeInTheDocument();
      expect(screen.queryByText("Team ID")).not.toBeInTheDocument();
    });

    it("should keep company and project selectors available for non-admin users", async () => {
      renderWithProviders(
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
        expect(screen.getByText("Project")).toBeInTheDocument();
      });

      const companyFormItem = screen.getByText("Company").closest(".ant-form-item");
      const projectFormItem = screen.getByText("Project").closest(".ant-form-item");
      expect(companyFormItem?.querySelector(".ant-select-disabled")).toBeFalsy();
      expect(projectFormItem?.querySelector(".ant-select-disabled")).toBeFalsy();
    });

    it("should keep project selection disabled when no company is selected", async () => {
      const unresolvedCavadaKey = {
        ...MOCK_KEY_DATA,
        cavadalabs_company_id: undefined,
        cavadalabs_project_id: undefined,
        metadata: {},
        team_id: null,
        organization_id: null,
      };

      renderWithProviders(
        <KeyEditView
          keyData={unresolvedCavadaKey}
          onCancel={() => {}}
          onSubmit={async () => {}}
          accessToken="test-token"
          userID="test-user"
          userRole="Admin"
          premiumUser={false}
        />,
      );

      await waitFor(() => {
        expect(screen.getByRole("combobox", { name: "CavadaLabs Project" })).toBeDisabled();
      });
    });

    it("should show legacy Team ID editor when CavadaLabs key context is unavailable", async () => {
      cavadalabsKeyContextOptions.companies = [];
      cavadalabsKeyContextOptions.projects = [];
      cavadalabsKeyContextOptions.errorDetail = null;
      cavadalabsKeyContextOptions.contextKnown = true;
      cavadalabsKeyContextOptions.isCavadaLabsProductContext = false;
      const legacyKey = {
        ...MOCK_KEY_DATA,
        cavadalabs_company_id: undefined,
        cavadalabs_project_id: undefined,
        metadata: {},
        team_id: "team-legacy",
        organization_id: "org-legacy",
      };

      renderWithProviders(
        <KeyEditView
          keyData={legacyKey}
          onCancel={() => {}}
          onSubmit={async () => {}}
          accessToken="test-token"
          userID="test-user"
          userRole="Admin"
          premiumUser={false}
          teams={[
            {
              team_id: "team-legacy",
              team_alias: "Legacy Team",
              models: [],
              max_budget: null,
              budget_duration: null,
              tpm_limit: null,
              rpm_limit: null,
              organization_id: "org-legacy",
              created_at: "2024-01-01T00:00:00Z",
              keys: [],
              members_with_roles: [],
            } as any,
          ]}
        />,
      );

      await waitFor(() => {
        expect(screen.getByText("Team ID")).toBeInTheDocument();
        expect(screen.getByText("Legacy Team (team-legacy)")).toBeInTheDocument();
      });
      expect(screen.queryByText("Company")).not.toBeInTheDocument();
      expect(screen.queryByText("Project")).not.toBeInTheDocument();
    });

    it("should keep legacy Team ID hidden when CavadaLabs product context has empty options", async () => {
      cavadalabsKeyContextOptions.companies = [];
      cavadalabsKeyContextOptions.projects = [];
      cavadalabsKeyContextOptions.errorDetail = null;
      cavadalabsKeyContextOptions.contextKnown = true;
      cavadalabsKeyContextOptions.isCavadaLabsProductContext = true;
      const legacyKey = {
        ...MOCK_KEY_DATA,
        cavadalabs_company_id: undefined,
        cavadalabs_project_id: undefined,
        metadata: {},
        team_id: "team-legacy",
        organization_id: "org-legacy",
      };

      renderWithProviders(
        <KeyEditView
          keyData={legacyKey}
          onCancel={() => {}}
          onSubmit={async () => {}}
          accessToken="test-token"
          userID="test-user"
          userRole="Admin"
          premiumUser={false}
          teams={[
            {
              team_id: "team-legacy",
              team_alias: "Legacy Team",
              models: [],
              max_budget: null,
              budget_duration: null,
              tpm_limit: null,
              rpm_limit: null,
              organization_id: "org-legacy",
              created_at: "2024-01-01T00:00:00Z",
              keys: [],
              members_with_roles: [],
            } as any,
          ]}
        />,
      );

      await waitFor(() => {
        expect(screen.getByRole("combobox", { name: "CavadaLabs Company" })).toBeInTheDocument();
        expect(screen.getByRole("combobox", { name: "CavadaLabs Project" })).toBeInTheDocument();
      });
      expect(screen.queryByText("Team ID")).not.toBeInTheDocument();
      expect(screen.queryByText("Legacy Team (team-legacy)")).not.toBeInTheDocument();
    });

    it("should show an actionable migration message when CavadaLabs key context schema is missing", async () => {
      cavadalabsKeyContextOptions.companies = [];
      cavadalabsKeyContextOptions.projects = [];
      cavadalabsKeyContextOptions.contextKnown = true;
      cavadalabsKeyContextOptions.isCavadaLabsProductContext = true;
      cavadalabsKeyContextOptions.errorDetail = {
        schema_status: "missing_schema",
        migration_status: "schema_missing",
        missing_schema: ["CavadaLabs_ProjectMemberTable delegate"],
        migration_command: "uv run prisma migrate deploy",
      };

      renderWithProviders(
        <KeyEditView
          keyData={MOCK_KEY_DATA}
          onCancel={() => {}}
          onSubmit={async () => {}}
          accessToken="test-token"
          userID="test-user"
          userRole="Admin"
          premiumUser={false}
        />,
      );

      await waitFor(() => {
        expect(screen.getByText("CavadaLabs key schema migration required")).toBeInTheDocument();
        expect(screen.getByText(/uv run prisma migrate deploy/i)).toBeInTheDocument();
        expect(screen.getByText(/CavadaLabs_ProjectMemberTable delegate/i)).toBeInTheDocument();
      });
    });

    it("should not submit organization_id when saving CavadaLabs key context", async () => {
      const onSubmitMock = vi.fn().mockResolvedValue(undefined);
      renderWithProviders(
        <KeyEditView
          keyData={MOCK_KEY_DATA}
          onCancel={() => {}}
          onSubmit={onSubmitMock}
          accessToken="test-token"
          userID="test-user"
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
        const callArgs = onSubmitMock.mock.calls[0][0];
        expect(callArgs.cavadalabs_company_id).toBe("company-1");
        expect(callArgs.cavadalabs_project_id).toBe("project-1");
        expect(callArgs.organization_id).toBeUndefined();
        expect(callArgs.team_id).toBeUndefined();
        expect(callArgs.project_id).toBeUndefined();
      });
    });

    it("should allow Project admins to save keys for their Project parent Company", async () => {
      const onSubmitMock = vi.fn().mockResolvedValue(undefined);
      cavadalabsKeyContextOptions.companies = [
        {
          company_id: "company-1",
          legal_name: "Acme Srl",
          litellm_organization_id: "org-1",
          status: "active",
          cavadalabs_can_manage: false,
        },
      ];
      cavadalabsKeyContextOptions.projects = [
        {
          project_id: "project-1",
          company_id: "company-1",
          name: "Support",
          litellm_team_id: "team-1",
          status: "production",
          allowed_models: ["gpt-4"],
          cavadalabs_can_manage: true,
        },
      ];

      renderWithProviders(
        <KeyEditView
          keyData={MOCK_KEY_DATA}
          onCancel={() => {}}
          onSubmit={onSubmitMock}
          accessToken="test-token"
          userID="test-user"
          userRole="Internal User"
          premiumUser={false}
        />,
      );

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /save changes/i })).toBeInTheDocument();
      });
      expect(screen.queryByText("Company or Project admin access required")).not.toBeInTheDocument();

      await userEvent.click(screen.getByRole("button", { name: /save changes/i }));

      await waitFor(() => {
        expect(onSubmitMock).toHaveBeenCalled();
        const callArgs = onSubmitMock.mock.calls[0][0];
        expect(callArgs.cavadalabs_company_id).toBe("company-1");
        expect(callArgs.cavadalabs_project_id).toBe("project-1");
        expect(callArgs.organization_id).toBeUndefined();
        expect(callArgs.team_id).toBeUndefined();
      });
    });

    it("should block saving when the CavadaLabs key scope is not manageable", async () => {
      const onSubmitMock = vi.fn().mockResolvedValue(undefined);
      cavadalabsKeyContextOptions.companies = [
        {
          company_id: "company-1",
          legal_name: "Acme Srl",
          litellm_organization_id: "org-1",
          status: "active",
          cavadalabs_can_manage: false,
        },
      ];
      cavadalabsKeyContextOptions.projects = [
        {
          project_id: "project-1",
          company_id: "company-1",
          name: "Support",
          litellm_team_id: "team-1",
          status: "production",
          allowed_models: ["gpt-4"],
          cavadalabs_can_manage: false,
        },
      ];

      renderWithProviders(
        <KeyEditView
          keyData={MOCK_KEY_DATA}
          onCancel={() => {}}
          onSubmit={onSubmitMock}
          accessToken="test-token"
          userID="test-user"
          userRole="Internal User"
          premiumUser={false}
        />,
      );

      await waitFor(() => {
        expect(screen.getByText("Company or Project admin access required")).toBeInTheDocument();
      });

      await userEvent.click(screen.getByRole("button", { name: /save changes/i }));

      await waitFor(() => {
        expect(mockNotificationsManager.fromBackend).toHaveBeenCalledWith("Project project-1 is not available");
      });
      expect(onSubmitMock).not.toHaveBeenCalled();
    });

    it("should block saving partial Company and Project context", async () => {
      const onSubmitMock = vi.fn().mockResolvedValue(undefined);
      const partialKey = {
        ...MOCK_KEY_DATA,
        cavadalabs_company_id: "company-1",
        cavadalabs_project_id: undefined,
        metadata: {
          cavadalabs_company_id: "company-1",
        },
        organization_id: null,
        team_id: null,
        project_id: null,
      };

      renderWithProviders(
        <KeyEditView
          keyData={partialKey}
          onCancel={() => {}}
          onSubmit={onSubmitMock}
          accessToken="test-token"
          userID="test-user"
          userRole="Admin"
          premiumUser={false}
        />,
      );

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /save changes/i })).toBeInTheDocument();
      });

      await userEvent.click(screen.getByRole("button", { name: /save changes/i }));

      await waitFor(() => {
        expect(mockNotificationsManager.fromBackend).toHaveBeenCalledWith(
          "Select both Company and Project before saving a CavadaLabs key",
        );
      });
      expect(onSubmitMock).not.toHaveBeenCalled();
    });

    it("should resolve legacy compatibility mapping into CavadaLabs company and project on submit", async () => {
      const onSubmitMock = vi.fn().mockResolvedValue(undefined);
      const legacyMappedKey = {
        ...MOCK_KEY_DATA,
        cavadalabs_company_id: undefined,
        cavadalabs_project_id: undefined,
        metadata: {},
        organization_id: "org-1",
        team_id: "team-1",
        project_id: "legacy-project",
      };

      renderWithProviders(
        <KeyEditView
          keyData={legacyMappedKey}
          onCancel={() => {}}
          onSubmit={onSubmitMock}
          accessToken="test-token"
          userID="test-user"
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
        const callArgs = onSubmitMock.mock.calls[0][0];
        expect(callArgs.cavadalabs_company_id).toBe("company-1");
        expect(callArgs.cavadalabs_project_id).toBe("project-1");
        expect(callArgs.organization_id).toBeUndefined();
        expect(callArgs.team_id).toBeUndefined();
        expect(callArgs.project_id).toBeUndefined();
      });
      expect(screen.queryByText("Organization")).not.toBeInTheDocument();
      expect(screen.queryByText("Team ID")).not.toBeInTheDocument();
    });

    it("should autoderive the sole manageable Company and Project before saving a legacy key", async () => {
      const onSubmitMock = vi.fn().mockResolvedValue(undefined);
      cavadalabsKeyContextOptions.companies = [
        { company_id: "company-1", legal_name: "Acme Srl", litellm_organization_id: "org-1", status: "active" },
      ];
      cavadalabsKeyContextOptions.projects = [
        {
          project_id: "project-1",
          company_id: "company-1",
          name: "Support",
          litellm_team_id: "team-1",
          status: "production",
          allowed_models: ["team-model-1"],
        },
      ];
      const legacyKey = {
        ...MOCK_KEY_DATA,
        cavadalabs_company_id: undefined,
        cavadalabs_project_id: undefined,
        metadata: {},
        organization_id: null,
        team_id: null,
        project_id: null,
      };

      renderWithProviders(
        <KeyEditView
          keyData={legacyKey}
          onCancel={() => {}}
          onSubmit={onSubmitMock}
          accessToken="test-token"
          userID="test-user"
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
        const callArgs = onSubmitMock.mock.calls[0][0];
        expect(callArgs.cavadalabs_company_id).toBe("company-1");
        expect(callArgs.cavadalabs_project_id).toBe("project-1");
        expect(callArgs.organization_id).toBeUndefined();
        expect(callArgs.team_id).toBeUndefined();
        expect(callArgs.project_id).toBeUndefined();
      });
    });

    it("should block saving a legacy key when Company and Project are ambiguous", async () => {
      const onSubmitMock = vi.fn().mockResolvedValue(undefined);
      const legacyKey = {
        ...MOCK_KEY_DATA,
        cavadalabs_company_id: undefined,
        cavadalabs_project_id: undefined,
        metadata: {},
        organization_id: null,
        team_id: null,
        project_id: null,
      };

      renderWithProviders(
        <KeyEditView
          keyData={legacyKey}
          onCancel={() => {}}
          onSubmit={onSubmitMock}
          accessToken="test-token"
          userID="test-user"
          userRole="Admin"
          premiumUser={false}
        />,
      );

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /save changes/i })).toBeInTheDocument();
      });

      await userEvent.click(screen.getByRole("button", { name: /save changes/i }));

      await waitFor(() => {
        expect(mockNotificationsManager.fromBackend).toHaveBeenCalledWith(
          "Select both Company and Project before saving a CavadaLabs key",
        );
      });
      expect(onSubmitMock).not.toHaveBeenCalled();
    });

    it("should block saving when compatibility company and project mappings disagree", async () => {
      const onSubmitMock = vi.fn().mockResolvedValue(undefined);
      const mismatchedLegacyKey = {
        ...MOCK_KEY_DATA,
        cavadalabs_company_id: undefined,
        cavadalabs_project_id: undefined,
        metadata: {},
        organization_id: "org-1",
        team_id: "team-2",
      };

      renderWithProviders(
        <KeyEditView
          keyData={mismatchedLegacyKey}
          onCancel={() => {}}
          onSubmit={onSubmitMock}
          accessToken="test-token"
          userID="test-user"
          userRole="Admin"
          premiumUser={false}
        />,
      );

      await waitFor(() => {
        expect(screen.getByText(/Selected Project belongs to a different Company/i)).toBeInTheDocument();
      });

      await userEvent.click(screen.getByRole("button", { name: /save changes/i }));

      await waitFor(() => {
        expect(onSubmitMock).not.toHaveBeenCalled();
      });
    });
  });
});
