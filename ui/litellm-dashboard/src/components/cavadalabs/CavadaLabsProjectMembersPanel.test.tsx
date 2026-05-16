import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders, screen, waitFor } from "../../../tests/test-utils";
import CavadaLabsProjectMembersPanel from "./CavadaLabsProjectMembersPanel";

vi.mock("@/components/networking", () => ({
  getProxyBaseUrl: () => "http://proxy.test",
  getGlobalLitellmHeaderName: () => "Authorization",
  deriveErrorMessage: (errorData: any) => errorData?.detail?.error ?? errorData?.detail ?? "error",
  handleError: vi.fn(),
}));

const jsonResponse = (payload: any, ok = true) =>
  ({
    ok,
    headers: {
      get: () => "application/json",
    },
    json: vi.fn().mockResolvedValue(payload),
    text: vi.fn(),
  }) as any;

const project = {
  project_id: "project-1",
  company_id: "company-1",
  name: "Support",
  cavadalabs_can_manage: true,
};

const memberPayload = {
  project_id: "project-1",
  company_id: "company-1",
  members: [
    {
      membership_id: "membership-1",
      project_id: "project-1",
      company_id: "company-1",
      user_id: "user-1",
      role: "operator",
      created_at: "2026-05-15T12:00:00Z",
      updated_at: "2026-05-15T12:00:00Z",
    },
  ],
  count: 1,
};

describe("CavadaLabsProjectMembersPanel", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("should list native Project members without exposing TeamInfo", async () => {
    const mockFetch = vi.fn().mockResolvedValue(jsonResponse(memberPayload));
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsProjectMembersPanel accessToken="token-1" project={project} canManage={false} />);

    expect(await screen.findByText("Project members")).toBeInTheDocument();
    expect(await screen.findByText("user-1")).toBeInTheDocument();
    expect(screen.getByText("operator")).toBeInTheDocument();
    expect(screen.queryByText("TeamInfo")).not.toBeInTheDocument();
    expect(mockFetch).toHaveBeenCalledWith(
      "http://proxy.test/cavadalabs/projects/project-1/members",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("should add Project members through the CavadaLabs membership endpoint", async () => {
    const user = userEvent.setup();
    const mockFetch = vi.fn().mockImplementation((_url: string, options: RequestInit) => {
      if (options.method === "POST") {
        return Promise.resolve(
          jsonResponse({
            membership_id: "membership-2",
            project_id: "project-1",
            company_id: "company-1",
            user_id: "user-2",
            role: "viewer",
            created_at: "2026-05-15T12:00:00Z",
            updated_at: "2026-05-15T12:00:00Z",
          }),
        );
      }
      return Promise.resolve(jsonResponse(memberPayload));
    });
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsProjectMembersPanel accessToken="token-1" project={project} canManage={true} />);

    await screen.findByText("user-1");
    await user.type(screen.getByLabelText("User ID"), "user-2");
    await user.click(screen.getByRole("button", { name: "Add member" }));

    await waitFor(() => {
      expect(mockFetch.mock.calls.some((call) => call[1]?.method === "POST")).toBe(true);
    });

    const postCall = mockFetch.mock.calls.find((call) => call[1]?.method === "POST");
    expect(postCall?.[0]).toBe("http://proxy.test/cavadalabs/projects/project-1/members");
    expect(JSON.parse(String(postCall?.[1]?.body))).toEqual({
      user_id: "user-2",
      role: "operator",
    });
  });
});
