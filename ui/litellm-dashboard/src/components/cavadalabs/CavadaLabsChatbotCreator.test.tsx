import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders, screen, waitFor } from "../../../tests/test-utils";
import CavadaLabsChatbotCreator from "./CavadaLabsChatbotCreator";
import type { CavadaLabsRuntimeContext } from "./types";

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

const context: CavadaLabsRuntimeContext = {
  companies: [{ company_id: "company-1", legal_name: "Acme Srl" }],
  projects: [{ project_id: "project-1", company_id: "company-1", name: "Support" }],
  chatbots: [],
  ragCollections: [{ collection_id: "collection-1", name: "Knowledge Base" }],
  nodes: [],
};

describe("CavadaLabsChatbotCreator", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("should create a Chatbot with Company and Project payload", async () => {
    const user = userEvent.setup();
    const onCreated = vi.fn();
    const mockFetch = vi.fn().mockImplementation((url: string, options: RequestInit) => {
      if (url.includes("/cavadalabs/model-policies")) {
        return Promise.resolve(
          jsonResponse({
            model_policies: [{ policy_id: "policy-1", model_alias: "openai/gpt-4.1" }],
            count: 1,
          }),
        );
      }
      if (url.includes("/key/list")) {
        return Promise.resolve(
          jsonResponse({
            keys: [{ token: "hashed-key", key_alias: "Existing Support Key" }],
            total_count: 1,
          }),
        );
      }
      if (url.endsWith("/cavadalabs/chatbots") && options.method === "POST") {
        return Promise.resolve(
          jsonResponse({
            chatbot_id: "chatbot-1",
            company_id: "company-1",
            project_id: "project-1",
            name: "Support Bot",
            status: "draft",
          }),
        );
      }
      if (url.endsWith("/key/generate") && options.method === "POST") {
        return Promise.resolve(
          jsonResponse({
            key: "sk-created",
            key_alias: "Support Bot server key",
            cavadalabs_company_id: "company-1",
            cavadalabs_project_id: "project-1",
          }),
        );
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsChatbotCreator accessToken="token-1" context={context} onCreated={onCreated} />);

    await user.click(screen.getByRole("button", { name: /create chatbot/i }));
    expect(screen.queryByText(/organization/i)).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Name"), "Support Bot");
    await user.type(screen.getByLabelText("System prompt"), "Answer with product context");
    await user.click(screen.getByRole("button", { name: /^ok$/i }));

    await waitFor(() => {
      expect(mockFetch.mock.calls.some((call) => call[1]?.method === "POST")).toBe(true);
    });

    const policyCall = mockFetch.mock.calls.find((call) => String(call[0]).includes("/cavadalabs/model-policies"));
    expect(policyCall?.[0]).toBe("http://proxy.test/cavadalabs/model-policies?project_id=project-1");
    const keyListCall = mockFetch.mock.calls.find((call) => String(call[0]).includes("/key/list"));
    expect(String(keyListCall?.[0])).toContain("cavadalabs_company_id=company-1");
    expect(String(keyListCall?.[0])).toContain("cavadalabs_project_id=project-1");

    const postCall = mockFetch.mock.calls.find((call) => String(call[0]).endsWith("/cavadalabs/chatbots"));
    expect(postCall?.[0]).toBe("http://proxy.test/cavadalabs/chatbots");
    const body = JSON.parse(String(postCall?.[1]?.body));
    expect(body).toEqual(
      expect.objectContaining({
        company_id: "company-1",
        project_id: "project-1",
        name: "Support Bot",
        system_prompt: "Answer with product context",
      }),
    );
    expect(body).not.toHaveProperty("organization_id");
    expect(body).not.toHaveProperty("team_id");
    const keyCreateCall = mockFetch.mock.calls.find((call) => String(call[0]).endsWith("/key/generate"));
    expect(keyCreateCall?.[0]).toBe("http://proxy.test/key/generate");
    const keyBody = JSON.parse(String(keyCreateCall?.[1]?.body));
    expect(keyBody).toEqual(
      expect.objectContaining({
        key_alias: "Support Bot server key",
        cavadalabs_company_id: "company-1",
        cavadalabs_project_id: "project-1",
      }),
    );
    expect(keyBody.metadata).toEqual(
      expect.objectContaining({
        cavadalabs_chatbot_id: "chatbot-1",
        spend_logs_metadata: expect.objectContaining({
          cavadalabs_company_id: "company-1",
          cavadalabs_project_id: "project-1",
          cavadalabs_chatbot_id: "chatbot-1",
        }),
      }),
    );
    expect(onCreated).toHaveBeenCalled();
  });

  it("should disable creation when Company or Project context is missing", () => {
    renderWithProviders(
      <CavadaLabsChatbotCreator
        accessToken="token-1"
        context={{ companies: [], projects: [], chatbots: [], ragCollections: [], nodes: [] }}
      />,
    );

    expect(screen.getByRole("button", { name: /create chatbot/i })).toBeDisabled();
    expect(screen.getByText("Create a Company and Project before creating a chatbot.")).toBeInTheDocument();
  });
});
