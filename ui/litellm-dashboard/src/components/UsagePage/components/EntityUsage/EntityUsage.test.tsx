import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import * as networking from "../../../networking";
import EntityUsage from "./EntityUsage";

beforeAll(() => {
  if (typeof window !== "undefined" && !window.ResizeObserver) {
    window.ResizeObserver = class ResizeObserver {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as any;
  }
});

// Mock the networking module
vi.mock("../../../networking", () => ({
  tagDailyActivityCall: vi.fn(),
  teamDailyActivityCall: vi.fn(),
  companyDailyActivityCall: vi.fn(),
  organizationDailyActivityCall: vi.fn(),
  projectDailyActivityCall: vi.fn(),
  customerDailyActivityCall: vi.fn(),
  agentDailyActivityCall: vi.fn(),
  userDailyActivityCall: vi.fn(),
}));

// Mock the child components to simplify testing
vi.mock("../../../activity_metrics", () => ({
  ActivityMetrics: () => <div>Activity Metrics</div>,
  processActivityData: () => ({ data: [], metadata: {} }),
}));

vi.mock("./TopKeyView", () => ({
  default: () => <div>Top Keys</div>,
}));

vi.mock("./TopModelView", () => ({
  default: () => <div>Top Models</div>,
}));

vi.mock("../../../EntityUsageExport/EntityUsageExportModal", () => ({
  default: () => <div>Entity Usage Export Modal</div>,
}));

vi.mock("../../../EntityUsageExport", () => ({
  UsageExportHeader: ({
    filterLabel,
    filterOptions = [],
    selectedFilters = [],
    onFiltersChange,
  }: {
    filterLabel?: string;
    filterOptions?: Array<{ label: string; value: string }>;
    selectedFilters?: string[];
    onFiltersChange?: (filters: string[]) => void;
  }) => (
    <div>
      <div>Usage Export Header</div>
      {filterLabel && <div>{filterLabel}</div>}
      <div data-testid="selected-usage-filters">{selectedFilters.join(",")}</div>
      {filterOptions.map((option) => (
        <button
          key={option.value}
          aria-label={`Filter ${option.label}`}
          type="button"
          onClick={() => onFiltersChange?.([option.value])}
        />
      ))}
    </div>
  ),
}));

vi.mock("../../../common_components/team_multi_select", () => ({
  default: () => <div>Team Multi Select</div>,
}));

// Mock useTeams hook
vi.mock("@/app/(dashboard)/hooks/useTeams", () => ({
  default: vi.fn(() => ({
    teams: [],
    setTeams: vi.fn(),
  })),
}));

describe("EntityUsage", () => {
  const mockTagDailyActivityCall = vi.mocked(networking.tagDailyActivityCall);
  const mockTeamDailyActivityCall = vi.mocked(networking.teamDailyActivityCall);
  const mockCompanyDailyActivityCall = vi.mocked(networking.companyDailyActivityCall);
  const mockOrganizationDailyActivityCall = vi.mocked(networking.organizationDailyActivityCall);
  const mockProjectDailyActivityCall = vi.mocked(networking.projectDailyActivityCall);
  const mockCustomerDailyActivityCall = vi.mocked(networking.customerDailyActivityCall);
  const mockAgentDailyActivityCall = vi.mocked(networking.agentDailyActivityCall);
  const mockUserDailyActivityCall = vi.mocked(networking.userDailyActivityCall);

  const mockSpendData = {
    results: [
      {
        date: "2025-01-01",
        metrics: {
          spend: 100.5,
          api_requests: 1000,
          successful_requests: 950,
          failed_requests: 50,
          total_tokens: 50000,
          prompt_tokens: 30000,
          completion_tokens: 20000,
          cache_read_input_tokens: 0,
          cache_creation_input_tokens: 0,
        },
        breakdown: {
          entities: {
            "tag-1": {
              metrics: {
                spend: 60.3,
                api_requests: 600,
                successful_requests: 570,
                failed_requests: 30,
                total_tokens: 30000,
                prompt_tokens: 18000,
                completion_tokens: 12000,
                cache_read_input_tokens: 0,
                cache_creation_input_tokens: 0,
              },
              metadata: {
                team_alias: "Tag 1",
              },
              api_key_breakdown: {},
            },
          },
          models: {},
          api_keys: {},
          providers: {
            openai: {
              metrics: {
                spend: 100.5,
                api_requests: 1000,
                successful_requests: 950,
                failed_requests: 50,
                total_tokens: 50000,
                prompt_tokens: 30000,
                completion_tokens: 20000,
                cache_read_input_tokens: 0,
                cache_creation_input_tokens: 0,
              },
            },
          },
        },
      },
    ],
    metadata: {
      total_spend: 100.5,
      total_api_requests: 1000,
      total_successful_requests: 950,
      total_failed_requests: 50,
      total_tokens: 50000,
    },
  };

  const mockAgentSpendData = {
    results: [
      {
        date: "2025-01-01",
        metrics: {
          spend: 245.8,
          api_requests: 3200,
          successful_requests: 3100,
          failed_requests: 100,
          total_tokens: 1250000,
          prompt_tokens: 850000,
          completion_tokens: 400000,
          cache_read_input_tokens: 50000,
          cache_creation_input_tokens: 10000,
        },
        breakdown: {
          entities: {
            "agent-code-review": {
              metrics: {
                spend: 120.4,
                api_requests: 1500,
                successful_requests: 1450,
                failed_requests: 50,
                total_tokens: 620000,
                prompt_tokens: 420000,
                completion_tokens: 200000,
                cache_read_input_tokens: 30000,
                cache_creation_input_tokens: 5000,
              },
              metadata: { agent_name: "Code Review Agent" },
              api_key_breakdown: {},
            },
            "agent-customer-support": {
              metrics: {
                spend: 85.2,
                api_requests: 1200,
                successful_requests: 1170,
                failed_requests: 30,
                total_tokens: 430000,
                prompt_tokens: 290000,
                completion_tokens: 140000,
                cache_read_input_tokens: 15000,
                cache_creation_input_tokens: 3000,
              },
              metadata: { agent_name: "Customer Support Agent" },
              api_key_breakdown: {},
            },
            "agent-data-analyst": {
              metrics: {
                spend: 40.2,
                api_requests: 500,
                successful_requests: 480,
                failed_requests: 20,
                total_tokens: 200000,
                prompt_tokens: 140000,
                completion_tokens: 60000,
                cache_read_input_tokens: 5000,
                cache_creation_input_tokens: 2000,
              },
              metadata: { agent_name: "Data Analyst Agent" },
              api_key_breakdown: {},
            },
          },
          models: {
            "gpt-4o": {
              metrics: {
                spend: 180.0,
                api_requests: 2000,
                successful_requests: 1950,
                failed_requests: 50,
                total_tokens: 900000,
                prompt_tokens: 600000,
                completion_tokens: 300000,
                cache_read_input_tokens: 40000,
                cache_creation_input_tokens: 8000,
              },
              metadata: {},
              api_key_breakdown: {},
            },
            "claude-sonnet-4-20250514": {
              metrics: {
                spend: 65.8,
                api_requests: 1200,
                successful_requests: 1150,
                failed_requests: 50,
                total_tokens: 350000,
                prompt_tokens: 250000,
                completion_tokens: 100000,
                cache_read_input_tokens: 10000,
                cache_creation_input_tokens: 2000,
              },
              metadata: {},
              api_key_breakdown: {},
            },
          },
          api_keys: {},
          providers: {
            openai: {
              metrics: {
                spend: 180.0,
                api_requests: 2000,
                successful_requests: 1950,
                failed_requests: 50,
                total_tokens: 900000,
                prompt_tokens: 600000,
                completion_tokens: 300000,
                cache_read_input_tokens: 40000,
                cache_creation_input_tokens: 8000,
              },
            },
            anthropic: {
              metrics: {
                spend: 65.8,
                api_requests: 1200,
                successful_requests: 1150,
                failed_requests: 50,
                total_tokens: 350000,
                prompt_tokens: 250000,
                completion_tokens: 100000,
                cache_read_input_tokens: 10000,
                cache_creation_input_tokens: 2000,
              },
            },
          },
        },
      },
      {
        date: "2025-01-02",
        metrics: {
          spend: 198.5,
          api_requests: 2800,
          successful_requests: 2720,
          failed_requests: 80,
          total_tokens: 980000,
          prompt_tokens: 670000,
          completion_tokens: 310000,
          cache_read_input_tokens: 42000,
          cache_creation_input_tokens: 9000,
        },
        breakdown: {
          entities: {
            "agent-code-review": {
              metrics: {
                spend: 95.3,
                api_requests: 1300,
                successful_requests: 1270,
                failed_requests: 30,
                total_tokens: 510000,
                prompt_tokens: 350000,
                completion_tokens: 160000,
                cache_read_input_tokens: 25000,
                cache_creation_input_tokens: 4000,
              },
              metadata: { agent_name: "Code Review Agent" },
              api_key_breakdown: {},
            },
            "agent-customer-support": {
              metrics: {
                spend: 68.7,
                api_requests: 1000,
                successful_requests: 970,
                failed_requests: 30,
                total_tokens: 320000,
                prompt_tokens: 220000,
                completion_tokens: 100000,
                cache_read_input_tokens: 12000,
                cache_creation_input_tokens: 3000,
              },
              metadata: { agent_name: "Customer Support Agent" },
              api_key_breakdown: {},
            },
            "agent-data-analyst": {
              metrics: {
                spend: 34.5,
                api_requests: 500,
                successful_requests: 480,
                failed_requests: 20,
                total_tokens: 150000,
                prompt_tokens: 100000,
                completion_tokens: 50000,
                cache_read_input_tokens: 5000,
                cache_creation_input_tokens: 2000,
              },
              metadata: { agent_name: "Data Analyst Agent" },
              api_key_breakdown: {},
            },
          },
          models: {},
          api_keys: {},
          providers: {},
        },
      },
    ],
    metadata: {
      total_spend: 444.3,
      total_api_requests: 6000,
      total_successful_requests: 5820,
      total_failed_requests: 180,
      total_tokens: 2230000,
    },
  };

  const defaultProps = {
    accessToken: "test-token",
    entityType: "tag" as const,
    entityId: "test-tag",
    userID: "user-123",
    userRole: "Admin",
    entityList: [
      { label: "Tag 1", value: "tag-1" },
      { label: "Tag 2", value: "tag-2" },
    ],
    premiumUser: true,
    dateValue: {
      from: new Date("2025-01-01"),
      to: new Date("2025-01-31"),
    },
  };

  beforeEach(() => {
    mockTagDailyActivityCall.mockClear();
    mockTeamDailyActivityCall.mockClear();
    mockCompanyDailyActivityCall.mockClear();
    mockOrganizationDailyActivityCall.mockClear();
    mockProjectDailyActivityCall.mockClear();
    mockCustomerDailyActivityCall.mockClear();
    mockAgentDailyActivityCall.mockClear();
    mockUserDailyActivityCall.mockClear();
    mockTagDailyActivityCall.mockResolvedValue(mockSpendData);
    mockTeamDailyActivityCall.mockResolvedValue(mockSpendData);
    mockCompanyDailyActivityCall.mockResolvedValue(mockSpendData);
    mockOrganizationDailyActivityCall.mockResolvedValue(mockSpendData);
    mockProjectDailyActivityCall.mockResolvedValue(mockSpendData);
    mockCustomerDailyActivityCall.mockResolvedValue(mockSpendData);
    mockAgentDailyActivityCall.mockResolvedValue(mockAgentSpendData);
    mockUserDailyActivityCall.mockResolvedValue(mockSpendData);
  });

  it("should render with tag entity type and display spend metrics", async () => {
    render(<EntityUsage {...defaultProps} />);

    await waitFor(() => {
      expect(mockTagDailyActivityCall).toHaveBeenCalled();
    });

    expect(screen.getByText("Tag Spend Overview")).toBeInTheDocument();
    expect(screen.getByText("Total Spend")).toBeInTheDocument();

    await waitFor(() => {
      const spendElements = screen.getAllByText("$100.50");
      expect(spendElements.length).toBeGreaterThan(0);
    });

    expect(screen.getByText("1,000")).toBeInTheDocument(); // Total Requests
  });

  it("should render with team entity type and call team API", async () => {
    render(<EntityUsage {...defaultProps} entityType="team" />);

    await waitFor(() => {
      expect(mockTeamDailyActivityCall).toHaveBeenCalled();
    });

    // Check that it shows team-specific label
    expect(screen.getByText("Team Spend Overview")).toBeInTheDocument();

    await waitFor(() => {
      const spendElements = screen.getAllByText("$100.50");
      expect(spendElements.length).toBeGreaterThan(0);
    });
  });

  it("should render compatibility organization entity type with company product label and company API", async () => {
    render(<EntityUsage {...defaultProps} entityType="organization" />);

    await waitFor(() => {
      expect(mockCompanyDailyActivityCall).toHaveBeenCalled();
    });
    expect(mockOrganizationDailyActivityCall).not.toHaveBeenCalled();

    expect(screen.getByText("Company Spend Overview")).toBeInTheDocument();

    await waitFor(() => {
      const spendElements = screen.getAllByText("$100.50");
      expect(spendElements.length).toBeGreaterThan(0);
    });
  });

  it("should render with company entity type and call company API", async () => {
    render(<EntityUsage {...defaultProps} entityType="company" />);

    await waitFor(() => {
      expect(mockCompanyDailyActivityCall).toHaveBeenCalled();
    });

    expect(screen.getByText("Company Spend Overview")).toBeInTheDocument();

    await waitFor(() => {
      const spendElements = screen.getAllByText("$100.50");
      expect(spendElements.length).toBeGreaterThan(0);
    });
  });

  it("should render with project entity type and call project API", async () => {
    render(<EntityUsage {...defaultProps} entityType="project" />);

    await waitFor(() => {
      expect(mockProjectDailyActivityCall).toHaveBeenCalled();
    });

    expect(screen.getByText("Project Spend Overview")).toBeInTheDocument();

    await waitFor(() => {
      const spendElements = screen.getAllByText("$100.50");
      expect(spendElements.length).toBeGreaterThan(0);
    });
  });

  it("should pass Company filter context to project usage API", async () => {
    render(
      <EntityUsage
        {...defaultProps}
        entityType="project"
        companyIds={["company-123"]}
      />,
    );

    await waitFor(() => {
      expect(mockProjectDailyActivityCall).toHaveBeenCalled();
    });

    const lastCall = mockProjectDailyActivityCall.mock.calls.at(-1);
    expect(lastCall?.[0]).toBe("test-token");
    expect(lastCall?.[3]).toBe(1);
    expect(lastCall?.[4]).toBeNull();
    expect(lastCall?.[5]).toEqual(["company-123"]);
  });

  it("should send selected Company filter to company daily activity", async () => {
    render(
      <EntityUsage
        {...defaultProps}
        entityType="company"
        entityList={[{ label: "Acme Company", value: "company-123" }]}
      />,
    );

    await waitFor(() => {
      expect(mockCompanyDailyActivityCall).toHaveBeenCalled();
    });
    mockCompanyDailyActivityCall.mockClear();

    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "Filter Acme Company" }));
    });

    await waitFor(() => {
      expect(mockCompanyDailyActivityCall).toHaveBeenCalled();
    });

    const lastCall = mockCompanyDailyActivityCall.mock.calls.at(-1);
    expect(lastCall?.[0]).toBe("test-token");
    expect(lastCall?.[3]).toBe(1);
    expect(lastCall?.[4]).toEqual(["company-123"]);
  });

  it("should send selected Project filter with Company context to project daily activity", async () => {
    render(
      <EntityUsage
        {...defaultProps}
        entityType="project"
        companyIds={["company-123"]}
        entityList={[{ label: "Support Project", value: "project-123" }]}
      />,
    );

    await waitFor(() => {
      expect(mockProjectDailyActivityCall).toHaveBeenCalled();
    });
    mockProjectDailyActivityCall.mockClear();

    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "Filter Support Project" }));
    });

    await waitFor(() => {
      expect(mockProjectDailyActivityCall).toHaveBeenCalled();
    });

    const lastCall = mockProjectDailyActivityCall.mock.calls.at(-1);
    expect(lastCall?.[0]).toBe("test-token");
    expect(lastCall?.[3]).toBe(1);
    expect(lastCall?.[4]).toEqual(["project-123"]);
    expect(lastCall?.[5]).toEqual(["company-123"]);
  });

  it("should render with customer entity type and call customer API", async () => {
    render(<EntityUsage {...defaultProps} entityType="customer" />);

    await waitFor(() => {
      expect(mockCustomerDailyActivityCall).toHaveBeenCalled();
    });

    expect(screen.getByText("Customer Spend Overview")).toBeInTheDocument();

    await waitFor(() => {
      const spendElements = screen.getAllByText("$100.50");
      expect(spendElements.length).toBeGreaterThan(0);
    });
  });

  it("should render with agent entity type and call agent API", async () => {
    render(<EntityUsage {...defaultProps} entityType="agent" />);

    await waitFor(() => {
      expect(mockAgentDailyActivityCall).toHaveBeenCalled();
    });

    expect(screen.getByText("Agent Spend Overview")).toBeInTheDocument();

    await waitFor(() => {
      const spendElements = screen.getAllByText("$444.30");
      expect(spendElements.length).toBeGreaterThan(0);
    });
  });

  it("should render with user entity type and call user API", async () => {
    render(<EntityUsage {...defaultProps} entityType="user" />);

    await waitFor(() => {
      expect(mockUserDailyActivityCall).toHaveBeenCalled();
    });

    expect(screen.getByText("User Spend Overview")).toBeInTheDocument();

    await waitFor(() => {
      const spendElements = screen.getAllByText("$100.50");
      expect(spendElements.length).toBeGreaterThan(0);
    });
  });

  it("should switch between tabs", async () => {
    render(<EntityUsage {...defaultProps} />);

    await waitFor(() => {
      expect(mockTagDailyActivityCall).toHaveBeenCalled();
    });

    expect(screen.getByText("Tag Spend Overview")).toBeInTheDocument();

    const modelActivityTab = screen.getByText("Model Activity");
    act(() => {
      fireEvent.click(modelActivityTab);
    });

    expect(screen.getAllByText("Activity Metrics")[0]).toBeInTheDocument();

    const keyActivityTab = screen.getByText("Key Activity");
    act(() => {
      fireEvent.click(keyActivityTab);
    });

    expect(screen.getAllByText("Activity Metrics")[1]).toBeInTheDocument();
  });

  it("should handle empty data gracefully", async () => {
    const emptyData = {
      results: [],
      metadata: {
        total_spend: 0,
        total_api_requests: 0,
        total_successful_requests: 0,
        total_failed_requests: 0,
        total_tokens: 0,
      },
    };

    mockTagDailyActivityCall.mockResolvedValue(emptyData);

    render(<EntityUsage {...defaultProps} />);

    await waitFor(() => {
      expect(mockTagDailyActivityCall).toHaveBeenCalled();
    });

    expect(await screen.findByText("Tag Spend Overview")).toBeInTheDocument();
    expect(await screen.findByText("$0.00")).toBeInTheDocument();
    expect(screen.getByText("Total Spend")).toBeInTheDocument();
    expect(screen.getAllByText("0")[0]).toBeInTheDocument();
  });

  it("should display Model Activity tab for non-agent entity types", async () => {
    render(<EntityUsage {...defaultProps} entityType="tag" />);

    await waitFor(() => {
      expect(mockTagDailyActivityCall).toHaveBeenCalled();
    });

    expect(screen.getByText("Model Activity")).toBeInTheDocument();
  });

  it("should display Request / Token Consumption tab for agent entity type", async () => {
    render(<EntityUsage {...defaultProps} entityType="agent" />);

    await waitFor(() => {
      expect(mockAgentDailyActivityCall).toHaveBeenCalled();
    });

    expect(screen.getByText("Request / Token Consumption")).toBeInTheDocument();
  });

  it("should display Top Models title for non-agent entity types", async () => {
    render(<EntityUsage {...defaultProps} entityType="tag" />);

    await waitFor(() => {
      expect(mockTagDailyActivityCall).toHaveBeenCalled();
    });

    const topModelsElements = screen.getAllByText("Top Models");
    expect(topModelsElements.length).toBeGreaterThan(0);
  });

  it("should display Top Agents title for agent entity type", async () => {
    render(<EntityUsage {...defaultProps} entityType="agent" />);

    await waitFor(() => {
      expect(mockAgentDailyActivityCall).toHaveBeenCalled();
    });

    expect(screen.getByText("Top Agents")).toBeInTheDocument();
  });

  it("should use entityList label when entityList is provided and entity exists", async () => {
    const customEntityList = [
      { label: "Custom Tag Label", value: "tag-1" },
      { label: "Tag 2", value: "tag-2" },
    ];

    render(<EntityUsage {...defaultProps} entityList={customEntityList} />);

    await waitFor(() => {
      expect(mockTagDailyActivityCall).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(screen.getByText("Custom Tag Label")).toBeInTheDocument();
    });
  });

  it("should fallback to team_alias when entityList is provided but entity does not exist", async () => {
    const customEntityList = [{ label: "Tag 2", value: "tag-2" }];

    render(<EntityUsage {...defaultProps} entityList={customEntityList} />);

    await waitFor(() => {
      expect(mockTagDailyActivityCall).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(screen.getByText("Tag 1")).toBeInTheDocument();
    });
  });

  it("should fallback to team_alias when entityList is null", async () => {
    render(<EntityUsage {...defaultProps} entityList={null} />);

    await waitFor(() => {
      expect(mockTagDailyActivityCall).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(screen.getByText("Tag 1")).toBeInTheDocument();
    });
  });

  it("should display Agent Activity tab for team entity type", async () => {
    render(<EntityUsage {...defaultProps} entityType="team" />);

    await waitFor(() => {
      expect(mockTeamDailyActivityCall).toHaveBeenCalled();
    });

    expect(screen.getByText("Agent Activity")).toBeInTheDocument();
  });

  it("should not display Agent Activity tab for non-team entity types", async () => {
    render(<EntityUsage {...defaultProps} entityType="tag" />);

    await waitFor(() => {
      expect(mockTagDailyActivityCall).toHaveBeenCalled();
    });

    expect(screen.queryByText("Agent Activity")).not.toBeInTheDocument();
  });

  it("should display Top Agents Driving Spend card for team entity type", async () => {
    render(<EntityUsage {...defaultProps} entityType="team" />);

    await waitFor(() => {
      expect(mockTeamDailyActivityCall).toHaveBeenCalled();
    });

    expect(screen.getByText("Top Agents Driving Spend")).toBeInTheDocument();
  });

  it("should not display Top Agents Driving Spend card for non-team entity types", async () => {
    render(<EntityUsage {...defaultProps} entityType="tag" />);

    await waitFor(() => {
      expect(mockTagDailyActivityCall).toHaveBeenCalled();
    });

    expect(screen.queryByText("Top Agents Driving Spend")).not.toBeInTheDocument();
  });

  it("should fetch agent activity data when entity type is team", async () => {
    render(<EntityUsage {...defaultProps} entityType="team" />);

    await waitFor(() => {
      expect(mockAgentDailyActivityCall).toHaveBeenCalledWith(
        "test-token",
        expect.any(Date),
        expect.any(Date),
        1,
        null,
      );
    });
  });

  it("should not fetch agent activity data for non-team entity types", async () => {
    render(<EntityUsage {...defaultProps} entityType="tag" />);

    await waitFor(() => {
      expect(mockTagDailyActivityCall).toHaveBeenCalled();
    });

    expect(mockAgentDailyActivityCall).not.toHaveBeenCalled();
  });

  it("should switch to Agent Activity tab for team entity type", async () => {
    render(<EntityUsage {...defaultProps} entityType="team" />);

    await waitFor(() => {
      expect(mockTeamDailyActivityCall).toHaveBeenCalled();
    });

    const agentActivityTab = screen.getByText("Agent Activity");
    act(() => {
      fireEvent.click(agentActivityTab);
    });

    await waitFor(() => {
      expect(screen.getAllByText("Activity Metrics").length).toBeGreaterThan(0);
    });
  });

  it("should fallback to entity value when no entityList and no team_alias", async () => {
    const spendDataWithoutAlias = {
      ...mockSpendData,
      results: [
        {
          ...mockSpendData.results[0],
          breakdown: {
            ...mockSpendData.results[0].breakdown,
            entities: {
              "tag-1": {
                ...mockSpendData.results[0].breakdown.entities["tag-1"],
                metadata: {},
              },
            },
          },
        },
      ],
    };

    mockTagDailyActivityCall.mockResolvedValue(spendDataWithoutAlias);

    render(<EntityUsage {...defaultProps} entityList={null} />);

    await waitFor(() => {
      expect(mockTagDailyActivityCall).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(screen.getByText("tag-1")).toBeInTheDocument();
    });
  });
});
