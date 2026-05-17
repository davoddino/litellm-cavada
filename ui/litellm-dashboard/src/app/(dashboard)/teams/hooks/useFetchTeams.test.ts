import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import useFetchTeams from "./useFetchTeams";
import { fetchTeams } from "@/components/common_components/fetch_teams";
import { v2TeamListCall } from "@/components/networking";

vi.mock("@/app/(dashboard)/hooks/useAuthorized", () => ({
  default: () => ({
    accessToken: "token",
    userId: "user-1",
    userRole: "internal_user",
  }),
}));

vi.mock("@/components/common_components/fetch_teams", () => ({
  fetchTeams: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("@/components/networking", () => ({
  v2TeamListCall: vi.fn().mockResolvedValue({
    teams: [{ team_id: "team-project-1" }],
  }),
}));

const mockFetchTeams = vi.mocked(fetchTeams);
const mockV2TeamListCall = vi.mocked(v2TeamListCall);

describe("useFetchTeams", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchTeams.mockResolvedValue(undefined);
    mockV2TeamListCall.mockResolvedValue({
      teams: [{ team_id: "team-project-1" }],
      total: 1,
      page: 1,
      page_size: 10,
      total_pages: 1,
    });
  });

  it("should fetch CavadaLabs Projects via v2 team list without legacy Organization or user scope", async () => {
    const setTeams = vi.fn();

    renderHook(() =>
      useFetchTeams({
        currentOrg: { organization_id: "org-legacy" } as any,
        setTeams,
        isCavadaLabsProductContext: true,
      }),
    );

    await waitFor(() => {
      expect(mockV2TeamListCall).toHaveBeenCalledWith(
        "token",
        null,
        null,
        null,
        null,
        1,
        10,
        "created_at",
        "desc",
        null,
        null,
      );
    });
    expect(mockFetchTeams).not.toHaveBeenCalled();
    await waitFor(() => {
      expect(setTeams).toHaveBeenCalledWith([{ team_id: "team-project-1" }]);
    });
  });

  it("should keep legacy team fetching outside CavadaLabs product context", async () => {
    const setTeams = vi.fn();
    const currentOrg = { organization_id: "org-legacy" } as any;

    renderHook(() =>
      useFetchTeams({
        currentOrg,
        setTeams,
        isCavadaLabsProductContext: false,
      }),
    );

    await waitFor(() => {
      expect(mockFetchTeams).toHaveBeenCalledWith("token", "user-1", "internal_user", currentOrg, setTeams);
    });
    expect(mockV2TeamListCall).not.toHaveBeenCalled();
  });
});
