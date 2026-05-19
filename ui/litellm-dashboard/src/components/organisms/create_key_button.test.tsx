import { act, fireEvent } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders, screen, waitFor } from "../../../tests/test-utils";
import CreateKey from "./create_key_button";

const {
  formMock,
  setFieldsValueMock,
  radioGroupValueRef,
  formStateRef,
  mockKeyCreateCall,
  mockModelAvailableCall,
  mockNotificationsManager,
  mockSyncKeyModelRoutingPolicies,
} = vi.hoisted(() => {
  const formStateRef = { current: {} as Record<string, any> };
  const mockKeyCreateCall = vi.fn().mockResolvedValue({
    key: "test-api-key",
    soft_budget: null,
  });
  const mockModelAvailableCall = vi.fn().mockResolvedValue({ data: [{ id: "gpt-4" }] });
  const mockSyncKeyModelRoutingPolicies = vi.fn().mockResolvedValue(undefined);
  const mockNotificationsManager = {
    success: vi.fn(),
    fromBackend: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
    clear: vi.fn(),
  };
  const formMock = {
    setFieldsValue: vi.fn((values: Record<string, any>) => {
      Object.assign(formStateRef.current, values);
    }),
    setFieldValue: vi.fn((name: string, value: any) => {
      formStateRef.current[name] = value;
    }),
    getFieldValue: vi.fn((name: string) => formStateRef.current[name]),
    resetFields: vi.fn(() => {
      formStateRef.current = {};
    }),
  };
  const radioGroupValueRef = { current: null as string | null };
  return {
    formMock,
    setFieldsValueMock: formMock.setFieldsValue,
    radioGroupValueRef,
    formStateRef,
    mockKeyCreateCall,
    mockModelAvailableCall,
    mockNotificationsManager,
    mockSyncKeyModelRoutingPolicies,
  };
});

const { cavadalabsKeyContextOptions } = vi.hoisted(() => ({
  cavadalabsKeyContextOptions: {
    companies: [{ company_id: "company-1", legal_name: "Acme Srl", status: "active" }],
    projects: [
      {
        project_id: "project-1",
        company_id: "company-1",
        litellm_team_id: "team-1",
        name: "Support",
        status: "production",
        allowed_models: ["gpt-4"],
      },
    ],
    isLoading: false,
    errorDetail: null as any,
    contextKnown: true,
    isCavadaLabsProductContext: true,
  },
}));

const defaultAuthorizedState = {
  accessToken: "test-token",
  userId: "test-user-id",
  userRole: "Admin",
  premiumUser: false,
};

let authorizedState = { ...defaultAuthorizedState };

vi.mock("@/app/(dashboard)/hooks/useAuthorized", () => ({
  default: () => authorizedState,
}));

vi.mock("@/app/(dashboard)/hooks/keys/useKeys", () => ({
  keyKeys: {
    lists: () => ["keys"],
  },
}));

vi.mock("@ant-design/icons", () => ({
  InfoCircleOutlined: () => null,
}));

vi.mock("react-copy-to-clipboard", () => ({
  CopyToClipboard: ({ children }: { children: any }) => children,
}));

vi.mock("@tremor/react", () => {
  const React = require("react");
  const Stub = ({ children }: { children?: any }) => React.createElement("div", null, children);
  const Button = ({ children, ...props }: { children?: any }) => React.createElement("button", props, children);
  const TextInput = (props: any) => React.createElement("input", props);

  return {
    Accordion: Stub,
    AccordionBody: Stub,
    AccordionHeader: Stub,
    Button,
    Col: Stub,
    Grid: Stub,
    Text: Stub,
    TextInput,
    Title: Stub,
  };
});

vi.mock("antd", () => {
  const React = require("react");

  const getValueFromEvent = (event: any) => {
    if (event?.target) {
      if (event.target.type === "checkbox") {
        return event.target.checked;
      }
      return event.target.value;
    }
    return event;
  };

  const Form = ({
    children,
    onFinish,
    ...props
  }: {
    children?: any;
    onFinish?: (values: Record<string, any>) => void;
  }) =>
    React.createElement(
      "form",
      {
        ...props,
        onSubmit: (event: Event) => {
          event.preventDefault();
          onFinish?.({ ...formStateRef.current });
        },
      },
      children,
    );

  Form.Item = ({ children, name }: { children?: any; name?: string }) => {
    if (!name || !React.isValidElement(children)) {
      return React.createElement(React.Fragment, null, children);
    }

    return React.cloneElement(children, {
      value: formStateRef.current[name],
      onChange: (event: any) => {
        formStateRef.current[name] = getValueFromEvent(event);
      },
    });
  };

  Form.useForm = () => [formMock];

  const Select = ({
    children,
    onChange,
    options,
    ...props
  }: {
    children?: any;
    onChange?: (value: string) => void;
    options?: Array<{ value: string; label: string }>;
  }) =>
    React.createElement(
      "select",
      {
        ...props,
        onChange: (event: any) => onChange?.(event.target.value),
      },
      children,
      options?.map((opt: any) => React.createElement("option", { key: opt.value, value: opt.value }, opt.label)),
    );

  Select.Option = ({ children, ...props }: { children?: any }) => React.createElement("option", props, children);

  const Input = (props: any) => React.createElement("input", props);
  Input.Password = (props: any) => React.createElement("input", { ...props, type: "password" });
  Input.TextArea = (props: any) => React.createElement("textarea", props);

  const Modal = ({ children, open }: { children?: any; open?: boolean }) =>
    open ? React.createElement("div", null, children) : null;

  const Radio = ({ children, ...props }: { children?: any }) => React.createElement("div", props, children);

  Radio.Group = ({ children, value }: { children?: any; value?: string }) => {
    radioGroupValueRef.current = value ?? null;
    return React.createElement("div", null, children);
  };

  const Switch = (props: any) => React.createElement("input", { ...props, type: "checkbox" });
  const Tag = ({ children }: { children?: any }) => React.createElement("span", null, children);
  const Tooltip = ({ children }: { children?: any }) => React.createElement(React.Fragment, null, children);
  const Alert = ({ message, description }: { message?: any; description?: any }) =>
    React.createElement("div", { role: "alert" }, message, description);

  const Button = ({ children, htmlType, ...props }: { children?: any; htmlType?: string; type?: string }) =>
    React.createElement("button", { ...props, type: htmlType ?? props.type }, children);
  const Card = ({ children, title }: { children?: any; title?: any }) => React.createElement("section", null, title, children);
  const InputNumber = (props: any) => React.createElement("input", { ...props, type: "number" });
  const Space = ({ children }: { children?: any }) => React.createElement("div", null, children);

  const Typography = ({ children, ...props }: { children?: any }) => React.createElement("div", props, children);
  Typography.Text = ({ children, ...props }: { children?: any }) => React.createElement("span", props, children);
  Typography.Paragraph = ({ children, ...props }: { children?: any }) => React.createElement("p", props, children);
  Typography.Title = ({ children, ...props }: { children?: any }) => React.createElement("h1", props, children);

  return {
    Alert,
    Button,
    Card,
    Form,
    Input,
    InputNumber,
    message: {
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn(),
      info: vi.fn(),
    },
    Modal,
    Radio,
    Select,
    Space,
    Switch,
    Tag,
    Tooltip,
    Typography,
  };
});

vi.mock("../networking", () => ({
  keyCreateCall: mockKeyCreateCall,
  modelAvailableCall: mockModelAvailableCall,
  getGuardrailsList: vi.fn().mockResolvedValue({ guardrails: [] }),
  getPoliciesList: vi.fn().mockResolvedValue({ policies: [] }),
  getPromptsList: vi.fn().mockResolvedValue({ prompts: [] }),
  proxyBaseUrl: "http://localhost:4000",
  getPossibleUserRoles: vi.fn().mockResolvedValue({
    Admin: { ui_label: "Admin" },
    User: { ui_label: "User" },
  }),
  userFilterUICall: vi.fn().mockResolvedValue([]),
  keyCreateServiceAccountCall: vi.fn().mockResolvedValue({
    key: "test-service-account-key",
    soft_budget: null,
  }),
  fetchMCPAccessGroups: vi.fn().mockResolvedValue([]),
  getAgentsList: vi.fn().mockResolvedValue({ agents: [] }),
}));

vi.mock("../molecules/notifications_manager", () => ({
  default: mockNotificationsManager,
}));

vi.mock("../cavadalabs/KeyModelRoutingEditor", () => ({
  collectKeyModelRoutingModels: (policies: any[]) =>
    policies.flatMap((policy) => (policy.enabled === false ? [] : [policy.model_bucket, policy.model_alias])),
  getKeyModelRoutingKeyId: (keyData: any) => keyData?.token_id ?? keyData?.token ?? null,
  KeyModelRoutingEditor: ({ onChange }: { onChange: (value: any[]) => void }) => (
    <button
      type="button"
      onClick={() =>
        onChange([
          {
            endpoint_type: "chat_completion",
            model_bucket: "medium",
            model_alias: "gpt-4",
            provider: "openai",
            priority: 1,
            enabled: true,
            fallback_enabled: true,
          },
        ])
      }
    >
      Configure model routing
    </button>
  ),
  mergeKeyModelRoutingModels: (models: any, routingModels: string[]) =>
    Array.from(new Set([...(Array.isArray(models) ? models : []), ...routingModels])),
  syncKeyModelRoutingPolicies: mockSyncKeyModelRoutingPolicies,
}));

vi.mock("../agent_management/AgentSelector", () => ({ default: () => null }));
vi.mock("../common_components/budget_duration_dropdown", () => ({ default: () => null }));
vi.mock("../common_components/check_openapi_schema", () => ({ default: () => null }));
vi.mock("../common_components/KeyLifecycleSettings", () => ({ default: () => null }));
vi.mock("../common_components/ModelAliasManager", () => ({ default: () => null }));
vi.mock("../common_components/PassThroughRoutesSelector", () => ({ default: () => null }));
vi.mock("../common_components/PremiumLoggingSettings", () => ({ default: () => null }));
vi.mock("../common_components/RateLimitTypeFormItem", () => ({ default: () => null }));
vi.mock("../common_components/RouterSettingsAccordion", () => ({ default: () => null }));
vi.mock("@/app/(dashboard)/hooks/teams/useTeams", () => ({
  useInfiniteTeams: () => ({
    data: {
      pages: [
        {
          teams: [
            { team_id: "team-1", team_alias: "Team One" },
            { team_id: "team-2", team_alias: "Team Two" },
          ],
          total: 2,
          page: 1,
          page_size: 50,
          total_pages: 1,
        },
      ],
    },
    fetchNextPage: vi.fn(),
    hasNextPage: false,
    isFetchingNextPage: false,
    isLoading: false,
  }),
}));
vi.mock("../common_components/team_dropdown", () => ({
  default: ({ onChange, disabled }: { onChange?: (v: string) => void; disabled?: boolean }) => (
    <select data-testid="team-dropdown" disabled={disabled} onChange={(e) => onChange?.(e.target.value)}>
      <option value="">Select team</option>
      <option value="team-1">Team One</option>
      <option value="team-2">Team Two</option>
    </select>
  ),
}));
vi.mock("../CreateUserButton", () => ({ CreateUserButton: () => null }));
vi.mock("../mcp_server_management/MCPServerSelector", () => ({ default: () => null }));
vi.mock("../mcp_server_management/MCPToolPermissions", () => ({ default: () => null }));
vi.mock("../shared/numerical_input", () => ({ default: () => null }));
vi.mock("../vector_store_management/VectorStoreSelector", () => ({ default: () => null }));
vi.mock("../key_team_helpers/fetch_available_models_team_key", () => ({
  getModelDisplayName: (model: string) => model,
}));

vi.mock("@/app/(dashboard)/hooks/tags/useTags", () => ({
  useTags: vi.fn().mockReturnValue({
    data: [
      { name: "production", description: "Prod tag", models: [], created_at: "2026-01-01", updated_at: "2026-01-01" },
      { name: "staging", description: "Staging tag", models: [], created_at: "2026-01-01", updated_at: "2026-01-01" },
    ],
    isLoading: false,
  }),
}));

vi.mock("../cavadalabs/keyContext", () => ({
  useCavadaLabsKeyContextOptions: () => cavadalabsKeyContextOptions,
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
}));

vi.mock("../common_components/AccessGroupSelector", () => ({
  default: ({ value = [], onChange }: { value?: string[]; onChange?: (v: string[]) => void }) => (
    <input
      data-testid="access-group-selector"
      value={Array.isArray(value) ? value.join(",") : ""}
      onChange={(event) => onChange?.(event.target.value ? event.target.value.split(",").map((v) => v.trim()) : [])}
    />
  ),
}));

describe("CreateKey", () => {
  const defaultProps = {
    team: null,
    teams: [],
    data: [],
    addKey: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    if (typeof window !== "undefined" && window.localStorage && typeof window.localStorage.clear === "function") {
      window.localStorage.clear();
    }
    authorizedState = { ...defaultAuthorizedState };
    cavadalabsKeyContextOptions.companies = [{ company_id: "company-1", legal_name: "Acme Srl", status: "active" }];
    cavadalabsKeyContextOptions.projects = [
      {
        project_id: "project-1",
        company_id: "company-1",
        litellm_team_id: "team-1",
        name: "Support",
        status: "production",
        allowed_models: ["gpt-4"],
      },
    ];
    cavadalabsKeyContextOptions.errorDetail = null;
    cavadalabsKeyContextOptions.contextKnown = true;
    cavadalabsKeyContextOptions.isCavadaLabsProductContext = true;
    radioGroupValueRef.current = null;
    formStateRef.current = {};
    mockKeyCreateCall.mockResolvedValue({
      key: "test-api-key",
      token_id: "test-token-id",
      soft_budget: null,
    });
    mockModelAvailableCall.mockResolvedValue({ data: [{ id: "gpt-4" }] });
  });

  it("should render the CreateKey component", () => {
    renderWithProviders(<CreateKey {...defaultProps} />);
    expect(screen.getByRole("button", { name: /create new key/i })).toBeInTheDocument();
  });

  it("should display 'AI APIs' label for the llm_api key type option", async () => {
    renderWithProviders(<CreateKey {...defaultProps} />);

    act(() => {
      fireEvent.click(screen.getByRole("button", { name: /create new key/i }));
    });

    await waitFor(() => {
      expect(screen.getByText("AI APIs")).toBeInTheDocument();
      expect(screen.queryByText("LLM API")).not.toBeInTheDocument();
    });
  });

  it("should include access_group_ids in keyCreateCall payload when access groups are selected", async () => {
    renderWithProviders(<CreateKey {...defaultProps} />);

    act(() => {
      fireEvent.click(screen.getByRole("button", { name: /create new key/i }));
    });

    await waitFor(() => {
      expect(screen.getByTestId("access-group-selector")).toBeInTheDocument();
    });

    act(() => {
      fireEvent.change(screen.getByTestId("access-group-selector"), { target: { value: "ag-1,ag-2" } });
      formMock.setFieldValue("key_alias", "Test Key");
    });

    act(() => {
      fireEvent.click(screen.getByRole("button", { name: /create key/i }));
    });

    await waitFor(() => {
      expect(mockKeyCreateCall).toHaveBeenCalled();
      const formValues = mockKeyCreateCall.mock.calls[0][2];
      expect(formValues).toHaveProperty("access_group_ids");
      expect(formValues.access_group_ids).toEqual(["ag-1", "ag-2"]);
    });
  });

  it("should prefill models when provided without team_id", async () => {
    renderWithProviders(
      <CreateKey
        {...defaultProps}
        autoOpenCreate={true}
        prefillData={{
          models: ["gpt-4"],
        }}
      />,
    );

    await waitFor(() => {
      expect(setFieldsValueMock).toHaveBeenCalledWith({ models: ["gpt-4"] });
    });
  });

  it("should prefill team_id when it exists in teams", async () => {
    renderWithProviders(
      <CreateKey
        {...defaultProps}
        teams={[{ team_id: "team-1", models: [] } as any]}
        autoOpenCreate={true}
        prefillData={{ team_id: "team-1" }}
      />,
    );

    await waitFor(() => {
      expect(setFieldsValueMock).toHaveBeenCalledWith({ team_id: "team-1" });
    });
  });

  it("should ignore team_id when it does not exist in teams", async () => {
    renderWithProviders(
      <CreateKey
        {...defaultProps}
        teams={[{ team_id: "team-1", models: [] } as any]}
        autoOpenCreate={true}
        prefillData={{ team_id: "team-404", key_alias: "example-key" }}
      />,
    );

    await waitFor(() => {
      expect(setFieldsValueMock).toHaveBeenCalledWith({ key_alias: "example-key" });
    });

    expect(setFieldsValueMock).not.toHaveBeenCalledWith({ team_id: "team-404" });
  });

  it('should fall back to "you" when owned_by is another_user for non-admin', async () => {
    authorizedState = { ...defaultAuthorizedState, userRole: "Internal User" };

    renderWithProviders(
      <CreateKey
        {...defaultProps}
        autoOpenCreate={true}
        prefillData={{ owned_by: "another_user", key_alias: "example-key" }}
      />,
    );

    await waitFor(() => {
      expect(setFieldsValueMock).toHaveBeenCalledWith({ key_alias: "example-key" });
    });

    expect(radioGroupValueRef.current).toBe("you");
  });

  it("should apply owned_by another_user for admin", async () => {
    renderWithProviders(
      <CreateKey {...defaultProps} autoOpenCreate={true} prefillData={{ owned_by: "another_user" }} />,
    );

    await waitFor(() => {
      expect(radioGroupValueRef.current).toBe("another_user");
    });
  });

  it("should prefill key_type when provided", async () => {
    renderWithProviders(<CreateKey {...defaultProps} autoOpenCreate={true} prefillData={{ key_type: "management" }} />);

    await waitFor(() => {
      expect(setFieldsValueMock).toHaveBeenCalledWith({ key_type: "management" });
    });
  });

  describe("CavadaLabs company/project context", () => {
    it("should render company and project options when modal is open", async () => {
      renderWithProviders(<CreateKey {...defaultProps} />);

      act(() => {
        fireEvent.click(screen.getByRole("button", { name: /create new key/i }));
      });

      await waitFor(() => {
        expect(screen.getByText("Acme Srl (company-1)")).toBeInTheDocument();
        expect(screen.getByText("Support (project-1)")).toBeInTheDocument();
      });
    });

    it("should keep LiteLLM team mapping hidden behind company and project selectors", async () => {
      renderWithProviders(<CreateKey {...defaultProps} />);

      act(() => {
        fireEvent.click(screen.getByRole("button", { name: /create new key/i }));
      });

      await waitFor(() => {
        expect(screen.getByText("Acme Srl (company-1)")).toBeInTheDocument();
        expect(screen.getByText("Support (project-1)")).toBeInTheDocument();
      });

      expect(screen.queryByTestId("team-dropdown")).not.toBeInTheDocument();
    });

    it("should only offer manageable Company and Project scopes for CavadaLabs key creation", async () => {
      cavadalabsKeyContextOptions.companies = [
        {
          company_id: "company-1",
          legal_name: "Acme Srl",
          status: "active",
          cavadalabs_can_manage: true,
        },
        {
          company_id: "company-viewer",
          legal_name: "Viewer Srl",
          status: "active",
          cavadalabs_can_manage: false,
        },
      ];
      cavadalabsKeyContextOptions.projects = [
        {
          project_id: "project-1",
          company_id: "company-1",
          litellm_team_id: "team-1",
          name: "Support",
          status: "production",
          allowed_models: ["gpt-4"],
          cavadalabs_can_manage: true,
        },
        {
          project_id: "project-viewer",
          company_id: "company-viewer",
          litellm_team_id: "team-viewer",
          name: "Read Only",
          status: "production",
          allowed_models: ["gpt-4"],
          cavadalabs_can_manage: false,
        },
      ];

      renderWithProviders(<CreateKey {...defaultProps} />);

      act(() => {
        fireEvent.click(screen.getByRole("button", { name: /create new key/i }));
      });

      await waitFor(() => {
        expect(screen.getByText("Acme Srl (company-1)")).toBeInTheDocument();
        expect(screen.getByText("Support (project-1)")).toBeInTheDocument();
      });

      expect(screen.queryByText("Viewer Srl (company-viewer)")).not.toBeInTheDocument();
      expect(screen.queryByText("Read Only (project-viewer)")).not.toBeInTheDocument();

      act(() => {
        formMock.setFieldValue("cavadalabs_company_id", "company-viewer");
        formMock.setFieldValue("cavadalabs_project_id", "project-viewer");
        formMock.setFieldValue("key_alias", "Viewer key");
      });

      act(() => {
        fireEvent.click(screen.getByRole("button", { name: /create key/i }));
      });

      await waitFor(() => {
        expect(mockNotificationsManager.fromBackend).toHaveBeenCalledWith("Project project-viewer is not available");
      });
      expect(mockKeyCreateCall).not.toHaveBeenCalled();
    });

    it("should allow Project admins to create keys for their Project parent Company", async () => {
      cavadalabsKeyContextOptions.companies = [
        {
          company_id: "company-project",
          legal_name: "Project Parent Srl",
          status: "active",
          cavadalabs_can_manage: false,
        },
      ];
      cavadalabsKeyContextOptions.projects = [
        {
          project_id: "project-admin",
          company_id: "company-project",
          litellm_team_id: "team-project-admin",
          name: "Project Admin Scope",
          status: "production",
          allowed_models: ["gpt-4"],
          cavadalabs_can_manage: true,
        },
      ];

      renderWithProviders(<CreateKey {...defaultProps} />);

      act(() => {
        fireEvent.click(screen.getByRole("button", { name: /create new key/i }));
      });

      await waitFor(() => {
        expect(screen.getByText("Project Parent Srl (company-project)")).toBeInTheDocument();
        expect(screen.getByText("Project Admin Scope (project-admin)")).toBeInTheDocument();
      });

      act(() => {
        formMock.setFieldValue("key_alias", "Project admin key");
      });

      act(() => {
        fireEvent.click(screen.getByRole("button", { name: /create key/i }));
      });

      await waitFor(() => {
        expect(mockKeyCreateCall).toHaveBeenCalled();
        const formValues = mockKeyCreateCall.mock.calls[0][2];
        expect(formValues.cavadalabs_company_id).toBe("company-project");
        expect(formValues.cavadalabs_project_id).toBe("project-admin");
        expect(formValues).not.toHaveProperty("organization_id");
        expect(formValues).not.toHaveProperty("team_id");
      });
    });

    it("should keep project selection disabled until a company is selected", async () => {
      renderWithProviders(<CreateKey {...defaultProps} />);

      act(() => {
        fireEvent.click(screen.getByRole("button", { name: /create new key/i }));
      });

      await waitFor(() => {
        expect(screen.getByRole("combobox", { name: "CavadaLabs Project" })).toBeDisabled();
      });
    });

    it("should include CavadaLabs company and project context in keyCreateCall payload", async () => {
      renderWithProviders(<CreateKey {...defaultProps} />);

      act(() => {
        fireEvent.click(screen.getByRole("button", { name: /create new key/i }));
      });

      await waitFor(() => {
        expect(screen.getByText("Acme Srl (company-1)")).toBeInTheDocument();
      });

      act(() => {
        formMock.setFieldValue("cavadalabs_company_id", "company-1");
        formMock.setFieldValue("cavadalabs_project_id", "project-1");
        formMock.setFieldValue("organization_id", "org-internal");
        formMock.setFieldValue("team_id", "team-internal");
        formMock.setFieldValue("project_id", "litellm-project");
        formMock.setFieldValue("key_alias", "Support key");
      });

      act(() => {
        fireEvent.click(screen.getByRole("button", { name: /create key/i }));
      });

      await waitFor(() => {
        expect(mockKeyCreateCall).toHaveBeenCalled();
        const formValues = mockKeyCreateCall.mock.calls[0][2];
        expect(formValues.cavadalabs_company_id).toBe("company-1");
        expect(formValues.cavadalabs_project_id).toBe("project-1");
        expect(formValues).not.toHaveProperty("organization_id");
        expect(formValues).not.toHaveProperty("team_id");
        expect(formValues).not.toHaveProperty("project_id");
      });
    });

    it("should create key-scoped model routing priorities after key creation", async () => {
      renderWithProviders(<CreateKey {...defaultProps} />);

      act(() => {
        fireEvent.click(screen.getByRole("button", { name: /create new key/i }));
      });

      await waitFor(() => {
        expect(screen.getByText("Configure model routing")).toBeInTheDocument();
      });

      act(() => {
        formMock.setFieldValue("cavadalabs_company_id", "company-1");
        formMock.setFieldValue("cavadalabs_project_id", "project-1");
        formMock.setFieldValue("key_alias", "Bucket key");
        fireEvent.click(screen.getByText("Configure model routing"));
      });

      act(() => {
        fireEvent.click(screen.getByRole("button", { name: /create key/i }));
      });

      await waitFor(() => {
        expect(mockKeyCreateCall).toHaveBeenCalled();
        expect(mockSyncKeyModelRoutingPolicies).toHaveBeenCalledWith({
          accessToken: "test-token",
          projectId: "project-1",
          keyId: "test-token-id",
          policies: [
            expect.objectContaining({
              model_bucket: "medium",
              model_alias: "gpt-4",
              priority: 1,
            }),
          ],
        });
      });
      const formValues = mockKeyCreateCall.mock.calls[0][2];
      expect(formValues.models).toEqual(expect.arrayContaining(["medium", "gpt-4"]));
      expect(formValues).not.toHaveProperty("organization_id");
    });

    it("should autoderive the sole manageable Company and Project before creating a key", async () => {
      renderWithProviders(<CreateKey {...defaultProps} />);

      act(() => {
        fireEvent.click(screen.getByRole("button", { name: /create new key/i }));
      });

      await waitFor(() => {
        expect(screen.getByText("Acme Srl (company-1)")).toBeInTheDocument();
      });

      act(() => {
        formMock.setFieldValue("key_alias", "Autoderived support key");
      });

      act(() => {
        fireEvent.click(screen.getByRole("button", { name: /create key/i }));
      });

      await waitFor(() => {
        expect(mockKeyCreateCall).toHaveBeenCalled();
        const formValues = mockKeyCreateCall.mock.calls[0][2];
        expect(formValues.cavadalabs_company_id).toBe("company-1");
        expect(formValues.cavadalabs_project_id).toBe("project-1");
      });
    });

    it("should block creating a CavadaLabs key when Company and Project are ambiguous", async () => {
      cavadalabsKeyContextOptions.companies = [
        { company_id: "company-1", legal_name: "Acme Srl", status: "active" },
        { company_id: "company-2", legal_name: "Globex Srl", status: "active" },
      ];
      cavadalabsKeyContextOptions.projects = [
        {
          project_id: "project-1",
          company_id: "company-1",
          litellm_team_id: "team-1",
          name: "Support",
          status: "production",
          allowed_models: ["gpt-4"],
        },
        {
          project_id: "project-2",
          company_id: "company-2",
          litellm_team_id: "team-2",
          name: "External",
          status: "production",
          allowed_models: ["gpt-4"],
        },
      ];
      renderWithProviders(<CreateKey {...defaultProps} />);

      act(() => {
        fireEvent.click(screen.getByRole("button", { name: /create new key/i }));
      });

      await waitFor(() => {
        expect(screen.getByText("Acme Srl (company-1)")).toBeInTheDocument();
      });

      act(() => {
        formMock.setFieldValue("key_alias", "Ambiguous key");
      });

      act(() => {
        fireEvent.click(screen.getByRole("button", { name: /create key/i }));
      });

      await waitFor(() => {
        expect(mockNotificationsManager.fromBackend).toHaveBeenCalledWith(
          "Select both Company and Project before creating a CavadaLabs key",
        );
      });
      expect(mockKeyCreateCall).not.toHaveBeenCalled();
    });

    it("should reject mismatched Company and Project before creating a key", async () => {
      cavadalabsKeyContextOptions.companies = [
        { company_id: "company-1", legal_name: "Acme Srl", status: "active" },
        { company_id: "company-2", legal_name: "Globex Srl", status: "active" },
      ];
      cavadalabsKeyContextOptions.projects = [
        {
          project_id: "project-2",
          company_id: "company-2",
          litellm_team_id: "team-2",
          name: "External",
          status: "production",
          allowed_models: ["gpt-4"],
        },
      ];

      renderWithProviders(<CreateKey {...defaultProps} />);

      act(() => {
        fireEvent.click(screen.getByRole("button", { name: /create new key/i }));
      });

      await waitFor(() => {
        expect(screen.getByText("Globex Srl (company-2)")).toBeInTheDocument();
      });

      act(() => {
        formMock.setFieldValue("cavadalabs_company_id", "company-1");
        formMock.setFieldValue("cavadalabs_project_id", "project-2");
        formMock.setFieldValue("key_alias", "Mismatched key");
      });

      act(() => {
        fireEvent.click(screen.getByRole("button", { name: /create key/i }));
      });

      await waitFor(() => {
        expect(mockNotificationsManager.fromBackend).toHaveBeenCalledWith(
          "Selected Project belongs to a different Company",
        );
      });
      expect(mockKeyCreateCall).not.toHaveBeenCalled();
    });

    it("should preserve legacy Team ID selection when CavadaLabs context is unavailable", async () => {
      cavadalabsKeyContextOptions.companies = [];
      cavadalabsKeyContextOptions.projects = [];
      cavadalabsKeyContextOptions.contextKnown = true;
      cavadalabsKeyContextOptions.isCavadaLabsProductContext = false;

      renderWithProviders(
        <CreateKey
          {...defaultProps}
          teams={[
            { team_id: "team-1", team_alias: "Team One", models: ["gpt-4"] } as any,
            { team_id: "team-2", team_alias: "Team Two", models: ["gpt-4"] } as any,
          ]}
        />,
      );

      act(() => {
        fireEvent.click(screen.getByRole("button", { name: /create new key/i }));
      });

      await waitFor(() => {
        expect(screen.getByText("Team One (team-1)")).toBeInTheDocument();
      });
      expect(screen.queryByText("Acme Srl (company-1)")).not.toBeInTheDocument();
      expect(screen.queryByText("Support (project-1)")).not.toBeInTheDocument();
    });

    it("should keep Team ID hidden when CavadaLabs product context has no key options", async () => {
      cavadalabsKeyContextOptions.companies = [];
      cavadalabsKeyContextOptions.projects = [];
      cavadalabsKeyContextOptions.contextKnown = true;
      cavadalabsKeyContextOptions.isCavadaLabsProductContext = true;

      renderWithProviders(
        <CreateKey
          {...defaultProps}
          teams={[
            { team_id: "team-1", team_alias: "Team One", models: ["gpt-4"] } as any,
            { team_id: "team-2", team_alias: "Team Two", models: ["gpt-4"] } as any,
          ]}
        />,
      );

      act(() => {
        fireEvent.click(screen.getByRole("button", { name: /create new key/i }));
      });

      await waitFor(() => {
        expect(screen.getByRole("combobox", { name: "CavadaLabs Company" })).toBeInTheDocument();
        expect(screen.getByRole("combobox", { name: "CavadaLabs Project" })).toBeInTheDocument();
      });
      expect(screen.queryByText("Team ID")).not.toBeInTheDocument();
      expect(screen.queryByText("Team One (team-1)")).not.toBeInTheDocument();
      expect(screen.queryByText("Team Two (team-2)")).not.toBeInTheDocument();
    });

    it("should explain Company and Project selection when Cavada key context is required", async () => {
      mockModelAvailableCall.mockResolvedValue({ data: [{ id: "no-default-models" }] });

      renderWithProviders(<CreateKey {...defaultProps} />);

      act(() => {
        fireEvent.click(screen.getByRole("button", { name: /create new key/i }));
      });

      await waitFor(() => {
        expect(screen.getByText(/Select a Company and Project/i)).toBeInTheDocument();
      });
      expect(screen.queryByText(/Please select a team/i)).not.toBeInTheDocument();
    });

    it("should show an actionable migration message when CavadaLabs key context schema is missing", async () => {
      cavadalabsKeyContextOptions.companies = [];
      cavadalabsKeyContextOptions.projects = [];
      cavadalabsKeyContextOptions.contextKnown = true;
      cavadalabsKeyContextOptions.isCavadaLabsProductContext = true;
      cavadalabsKeyContextOptions.errorDetail = {
        schema_status: "missing_schema",
        migration_status: "schema_missing",
        missing_schema: ["CavadaLabs_CompanyMemberTable delegate"],
        migration_command: "uv run prisma migrate deploy",
      };

      renderWithProviders(<CreateKey {...defaultProps} />);

      act(() => {
        fireEvent.click(screen.getByRole("button", { name: /create new key/i }));
      });

      await waitFor(() => {
        expect(screen.getByRole("alert")).toHaveTextContent("CavadaLabs key schema migration required");
        expect(screen.getByRole("alert")).toHaveTextContent("uv run prisma migrate deploy");
        expect(screen.getByRole("alert")).toHaveTextContent("CavadaLabs_CompanyMemberTable delegate");
      });
      expect(screen.queryByText("Team ID")).not.toBeInTheDocument();
    });
  });

  describe("tags dropdown", () => {
    it("should populate tags dropdown with options from useTags hook", async () => {
      renderWithProviders(<CreateKey {...defaultProps} />);

      act(() => {
        fireEvent.click(screen.getByRole("button", { name: /create new key/i }));
      });

      await waitFor(() => {
        expect(screen.getByText("production")).toBeInTheDocument();
        expect(screen.getByText("staging")).toBeInTheDocument();
      });
    });
  });
});
