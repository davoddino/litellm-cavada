import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { normalizeVirtualKeyFilterState, useFilterLogic } from "./filter_logic";
import { keyListCall } from "../networking";

vi.mock("../networking", () => ({
  keyListCall: vi.fn(),
}));

vi.mock("./filter_helpers", () => ({
  fetchAllTeams: vi.fn().mockResolvedValue([]),
  fetchAllOrganizations: vi.fn().mockResolvedValue([]),
}));

const cavadalabsContextFixture = vi.hoisted(() => ({
  companies: [
    {
      company_id: "company-1",
      legal_name: "Acme",
      litellm_organization_id: "org-company-1",
    },
  ],
  projects: [
    {
      project_id: "project-1",
      company_id: "company-1",
      name: "Support",
      litellm_team_id: "team-project-1",
    },
  ],
}));

vi.mock("../cavadalabs/keyContext", () => ({
  getKeyCavadaLabsCompanyId: (key: any) =>
    key.cavadalabs_company_id ??
    key.metadata?.cavadalabs_company_id ??
    key.metadata?.cavadalabs?.company_id ??
    key.metadata?.spend_logs_metadata?.cavadalabs_company_id ??
    null,
  getKeyCavadaLabsProjectId: (key: any) =>
    key.cavadalabs_project_id ??
    key.metadata?.cavadalabs_project_id ??
    key.metadata?.cavadalabs?.project_id ??
    key.metadata?.spend_logs_metadata?.cavadalabs_project_id ??
    null,
  findCavadaLabsCompanyForCompatibilityOrganization: (companies: any[], organizationId: string | null | undefined) =>
    companies.find((company) => company.litellm_organization_id === organizationId) ?? null,
  findCavadaLabsProjectForCompatibilityTeam: (projects: any[], teamId: string | null | undefined) =>
    projects.find((project) => project.litellm_team_id === teamId) ?? null,
  useCavadaLabsKeyContextOptions: () => ({
    companies: cavadalabsContextFixture.companies,
    projects: cavadalabsContextFixture.projects,
    isLoading: false,
  }),
}));

const mockKey = {
  token: "abc123",
  key_alias: "aaaaa",
  team_id: null,
  organization_id: null,
};

const defaultProps = {
  keys: [mockKey] as any[],
  teams: [],
  organizations: [],
  cavadalabsContextOptions: {
    companies: cavadalabsContextFixture.companies,
    projects: cavadalabsContextFixture.projects,
    isLoading: false,
    errorDetail: null,
    contextKnown: true,
    isCavadaLabsProductContext: true,
  },
};

const makeApiResponse = (overrides: { keys?: any[]; total_count?: number; total_pages?: number } = {}) => ({
  keys: overrides.keys ?? [mockKey],
  total_count: overrides.total_count ?? 1,
  current_page: 1,
  total_pages: overrides.total_pages ?? 1,
});

describe("useFilterLogic – filteredTotalCount", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(keyListCall).mockResolvedValue(makeApiResponse({ total_count: 509, total_pages: 11 }));
  });

  it("should expose filteredTotalCount as null before any filter search runs", () => {
    const { result } = renderHook(() => useFilterLogic(defaultProps));

    expect(result.current.filteredTotalCount).toBeNull();
  });

  it("should set filteredTotalCount to the API total_count after a Key Alias filter is applied", async () => {
    vi.mocked(keyListCall).mockResolvedValue(makeApiResponse({ keys: [mockKey], total_count: 1, total_pages: 1 }));

    const { result } = renderHook(() => useFilterLogic(defaultProps));

    act(() => {
      result.current.handleFilterChange({ "Key Alias": "aaaaa" });
    });

    await waitFor(
      () => {
        expect(result.current.filteredTotalCount).toBe(1);
      },
      { timeout: 500 },
    );
  });

  it("should reflect the filtered total_count even when it differs from the full key count", async () => {
    vi.mocked(keyListCall).mockResolvedValue(makeApiResponse({ total_count: 7, total_pages: 1 }));

    const { result } = renderHook(() => useFilterLogic(defaultProps));

    act(() => {
      result.current.handleFilterChange({ "Team ID": "team-x" });
    });

    await waitFor(
      () => {
        expect(result.current.filteredTotalCount).toBe(7);
      },
      { timeout: 500 },
    );
  });

  it("should reset filteredTotalCount to null when handleFilterReset is called", async () => {
    vi.mocked(keyListCall).mockResolvedValue(makeApiResponse({ total_count: 1 }));

    const { result } = renderHook(() => useFilterLogic(defaultProps));

    act(() => {
      result.current.handleFilterChange({ "Key Alias": "aaaaa" });
    });

    await waitFor(
      () => {
        expect(result.current.filteredTotalCount).toBe(1);
      },
      { timeout: 500 },
    );

    act(() => {
      result.current.handleFilterReset();
    });

    // filteredTotalCount resets synchronously before the debounced reset search completes
    expect(result.current.filteredTotalCount).toBeNull();
  });

  it("should pass the Key Alias value to keyListCall", async () => {
    vi.mocked(keyListCall).mockResolvedValue(makeApiResponse({ total_count: 2 }));

    const { result } = renderHook(() => useFilterLogic(defaultProps));

    act(() => {
      result.current.handleFilterChange({ "Key Alias": "my-alias" });
    });

    await waitFor(
      () => {
        expect(keyListCall).toHaveBeenLastCalledWith(
          expect.any(String), // accessToken
          null, // organizationID (empty → null)
          null, // teamID (empty → null)
          "my-alias", // selectedKeyAlias ← the filter value
          null, // userID
          null, // keyHash
          1, // page (resets to 1 on filter change)
          expect.any(Number), // pageSize (defaultPageSize)
          expect.anything(), // sortBy
          expect.anything(), // sortOrder
          null, // expand
          null, // status
          null, // cavadalabsCompanyId
          null, // cavadalabsProjectId
        );
      },
      { timeout: 500 },
    );
  });

  it("should pass Company and Project filters to keyListCall without organization scope", async () => {
    vi.mocked(keyListCall).mockResolvedValue(makeApiResponse({ total_count: 1 }));

    const { result } = renderHook(() => useFilterLogic(defaultProps));

    act(() => {
      result.current.handleFilterChange({
        "Company ID": "company-1",
        "Project ID": "project-1",
      });
    });

    await waitFor(
      () => {
        expect(keyListCall).toHaveBeenLastCalledWith(
          expect.any(String),
          null,
          null,
          null,
          null,
          null,
          1,
          expect.any(Number),
          expect.anything(),
          expect.anything(),
          null,
          null,
          "company-1",
          "project-1",
        );
      },
      { timeout: 500 },
    );
  });

  it("should clear stale Organization and Team filters when applying Cavada Company and Project filters", async () => {
    vi.mocked(keyListCall).mockResolvedValue(makeApiResponse({ total_count: 1 }));

    const { result } = renderHook(() => useFilterLogic(defaultProps));

    act(() => {
      result.current.handleFilterChange(
        {
          "Organization ID": "org-company-1",
          "Team ID": "team-project-1",
        },
        true,
      );
    });

    await waitFor(() => {
      expect(result.current.filters["Organization ID"]).toBe("org-company-1");
      expect(result.current.filters["Team ID"]).toBe("team-project-1");
    });

    act(() => {
      result.current.handleFilterChange({
        "Organization ID": "org-company-1",
        "Team ID": "team-project-1",
        "Company ID": "company-1",
        "Project ID": "project-1",
      });
    });

    await waitFor(
      () => {
        expect(keyListCall).toHaveBeenLastCalledWith(
          expect.any(String),
          null,
          null,
          null,
          null,
          null,
          1,
          expect.any(Number),
          expect.anything(),
          expect.anything(),
          null,
          null,
          "company-1",
          "project-1",
        );
        expect(result.current.filters["Organization ID"]).toBe("");
        expect(result.current.filters["Team ID"]).toBe("");
      },
      { timeout: 500 },
    );
  });

  it("should normalize Cavada product filters ahead of stale LiteLLM compatibility filters", () => {
    expect(
      normalizeVirtualKeyFilterState({
        "Organization ID": "org-company-1",
        "Team ID": "team-project-1",
        "Company ID": "company-1",
        "Project ID": "project-1",
        "Key Alias": "alias-1",
      }),
    ).toMatchObject({
      "Organization ID": "",
      "Team ID": "",
      "Company ID": "company-1",
      "Project ID": "project-1",
      "Key Alias": "alias-1",
    });
  });

  it("should locally filter Cavada keys by explicit Company and Project metadata", async () => {
    const explicitKey = {
      ...mockKey,
      token: "explicit-key",
      metadata: {
        cavadalabs_company_id: "company-1",
        cavadalabs_project_id: "project-1",
      },
    };
    const otherKey = {
      ...mockKey,
      token: "other-key",
      metadata: {
        cavadalabs_company_id: "company-2",
        cavadalabs_project_id: "project-2",
      },
    };

    const props = {
      ...defaultProps,
      keys: [explicitKey, otherKey] as any[],
    };
    const { result } = renderHook(() => useFilterLogic(props));

    act(() => {
      result.current.handleFilterChange(
        {
          "Company ID": "company-1",
          "Project ID": "project-1",
        },
        true,
      );
    });

    await waitFor(() => {
      expect(result.current.filteredKeys.map((key) => key.token)).toEqual(["explicit-key"]);
    });
    expect(keyListCall).not.toHaveBeenCalled();
  });

  it("should locally filter legacy Cavada keys through internal organization and team mappings", async () => {
    const legacyKey = {
      ...mockKey,
      token: "legacy-key",
      organization_id: "org-company-1",
      team_id: "team-project-1",
      metadata: {},
    };
    const unmappedKey = {
      ...mockKey,
      token: "unmapped-key",
      organization_id: "org-other",
      team_id: "team-other",
      metadata: {},
    };

    const props = {
      ...defaultProps,
      keys: [legacyKey, unmappedKey] as any[],
    };
    const { result } = renderHook(() => useFilterLogic(props));

    act(() => {
      result.current.handleFilterChange(
        {
          "Company ID": "company-1",
          "Project ID": "project-1",
        },
        true,
      );
    });

    await waitFor(() => {
      expect(result.current.filteredKeys.map((key) => key.token)).toEqual(["legacy-key"]);
    });
    expect(keyListCall).not.toHaveBeenCalled();
  });

  it("should not update filteredTotalCount when keyListCall throws", async () => {
    vi.mocked(keyListCall).mockRejectedValue(new Error("Network error"));

    const { result } = renderHook(() => useFilterLogic(defaultProps));

    act(() => {
      result.current.handleFilterChange({ "Key Alias": "bad-alias" });
    });

    await waitFor(
      () => {
        expect(keyListCall).toHaveBeenCalled();
      },
      { timeout: 500 },
    );

    expect(result.current.filteredTotalCount).toBeNull();
  });

  it("should not trigger a debounced search when skipDebounce is true", async () => {
    const { result } = renderHook(() => useFilterLogic(defaultProps));

    act(() => {
      result.current.handleFilterChange({ "Sort By": "spend", "Sort Order": "asc" }, true);
    });

    await new Promise((resolve) => setTimeout(resolve, 350));

    expect(keyListCall).not.toHaveBeenCalled();
    expect(result.current.filteredTotalCount).toBeNull();
  });
});
