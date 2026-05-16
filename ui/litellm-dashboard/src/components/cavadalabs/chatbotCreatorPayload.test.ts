import { describe, expect, it } from "vitest";
import {
  CHATBOT_RUNTIME_ROUTE,
  buildChatbotCreatePayload,
  buildChatbotKeyMetadata,
  buildChatbotServerKeyCreatePayload,
  buildChatbotServerKeyUpdatePayload,
  buildChatbotWebTokenPayload,
  buildChatbotWebTokenMetadata,
  modelPolicyOptions,
  projectsForCompany,
  serverKeyOptions,
} from "./chatbotCreatorPayload";
import type { CavadaLabsRuntimeContext } from "./types";

const context: CavadaLabsRuntimeContext = {
  companies: [
    { company_id: "company-1", legal_name: "Acme Srl" },
    { company_id: "company-2", legal_name: "Beta Srl" },
  ],
  projects: [
    { project_id: "project-1", company_id: "company-1", name: "Support" },
    { project_id: "project-2", company_id: "company-2", name: "Sales" },
  ],
  chatbots: [],
  ragCollections: [],
  nodes: [],
};

describe("chatbotCreatorPayload", () => {
  it("should filter Projects by selected Company", () => {
    expect(projectsForCompany(context, "company-1").map((project) => project.project_id)).toEqual(["project-1"]);
    expect(projectsForCompany(context, "company-2").map((project) => project.project_id)).toEqual(["project-2"]);
  });

  it("should build Chatbot payload with canonical Company and Project context", () => {
    const payload = buildChatbotCreatePayload({
      company_id: "company-1",
      project_id: "project-1",
      name: " Support Bot ",
      status: "published",
      default_language: "it",
      prompt_version: 2,
      model_policy_id: "policy-1",
      system_prompt: "Be concise",
      assigned_rag_collections: ["collection-1", " "],
      allowed_domains: ["example.com"],
      fallback_message: "Try again later",
    });

    expect(payload).toEqual({
      company_id: "company-1",
      project_id: "project-1",
      name: "Support Bot",
      status: "published",
      default_language: "it",
      prompt_version: 2,
      model_policy_id: "policy-1",
      system_prompt: "Be concise",
      assigned_rag_collections: ["collection-1"],
      allowed_domains: ["example.com"],
      fallback_message: "Try again later",
    });
    expect(payload).not.toHaveProperty("organization_id");
    expect(payload).not.toHaveProperty("team_id");
  });

  it("should build server API key payload with Chatbot ledger metadata", () => {
    const payload = buildChatbotServerKeyCreatePayload(
      {
        company_id: "company-1",
        project_id: "project-1",
        name: "Support Bot",
        server_key_mode: "create",
        server_key_alias: "Support Bot Key",
      },
      "chatbot-1",
      { policy_id: "policy-1", model_alias: "openai/gpt-4.1" },
    );

    expect(payload).toEqual(
      expect.objectContaining({
        key_alias: "Support Bot Key",
        models: ["openai/gpt-4.1"],
        cavadalabs_company_id: "company-1",
        cavadalabs_project_id: "project-1",
      }),
    );
    expect(payload?.metadata).toEqual(
      expect.objectContaining({
        cavadalabs_company_id: "company-1",
        cavadalabs_project_id: "project-1",
        cavadalabs_chatbot_id: "chatbot-1",
        cavadalabs: expect.objectContaining({
          company_id: "company-1",
          project_id: "project-1",
          chatbot_id: "chatbot-1",
        }),
        spend_logs_metadata: expect.objectContaining({
          cavadalabs_company_id: "company-1",
          cavadalabs_project_id: "project-1",
          cavadalabs_chatbot_id: "chatbot-1",
        }),
      }),
    );
    expect(payload).not.toHaveProperty("organization_id");
    expect(payload).not.toHaveProperty("team_id");
  });

  it("should merge Chatbot metadata into an existing server key update payload", () => {
    const payload = buildChatbotServerKeyUpdatePayload(
      {
        company_id: "company-1",
        project_id: "project-1",
        server_key_mode: "existing",
        existing_server_key: "hashed-key",
      },
      "chatbot-1",
      {
        token: "hashed-key",
        metadata: {
          owner: "support",
          spend_logs_metadata: { legacy: "kept" },
        },
      },
    );

    expect(payload).toEqual(
      expect.objectContaining({
        key: "hashed-key",
        cavadalabs_company_id: "company-1",
        cavadalabs_project_id: "project-1",
      }),
    );
    expect(payload?.metadata).toEqual(
      expect.objectContaining({
        owner: "support",
        cavadalabs_chatbot_id: "chatbot-1",
        spend_logs_metadata: expect.objectContaining({
          legacy: "kept",
          cavadalabs_chatbot_id: "chatbot-1",
        }),
      }),
    );
  });

  it("should expose existing server key options from key list rows", () => {
    expect(serverKeyOptions([{ token: "hashed-key", key_alias: "Support key" }])).toEqual([
      { value: "hashed-key", label: "Support key (hashed-key)" },
    ]);
  });

  it("should build web token payload for the Chatbot runtime route", () => {
    const payload = buildChatbotWebTokenPayload(
      {
        company_id: "company-1",
        project_id: "project-1",
        issue_web_token: true,
        web_token_name: " Embed token ",
        allowed_domains: ["example.com"],
        allowed_origins: ["https://example.com"],
        expires_in_seconds: 7200,
      },
      "chatbot-1",
    );

    expect(payload).toEqual({
      company_id: "company-1",
      project_id: "project-1",
      chatbot_id: "chatbot-1",
      name: "Embed token",
      allowed_domains: ["example.com"],
      allowed_origins: ["https://example.com"],
      route_allowlist: [CHATBOT_RUNTIME_ROUTE],
      expires_in_seconds: 7200,
      metadata: expect.objectContaining({
        cavadalabs_company_id: "company-1",
        cavadalabs_project_id: "project-1",
        cavadalabs_chatbot_id: "chatbot-1",
        cavadalabs: expect.objectContaining({
          company_id: "company-1",
          project_id: "project-1",
          chatbot_id: "chatbot-1",
        }),
        spend_logs_metadata: expect.objectContaining({
          cavadalabs_company_id: "company-1",
          cavadalabs_project_id: "project-1",
          cavadalabs_chatbot_id: "chatbot-1",
        }),
      }),
    });
    expect(payload).not.toHaveProperty("organization_id");
    expect(payload).not.toHaveProperty("team_id");
  });

  it("should expose readable model policy options", () => {
    expect(
      buildChatbotKeyMetadata({ company_id: "company-1", project_id: "project-1" }, "chatbot-1").cavadalabs,
    ).toEqual({
      company_id: "company-1",
      project_id: "project-1",
      chatbot_id: "chatbot-1",
    });
    expect(modelPolicyOptions([{ policy_id: "policy-1", model_alias: "openai/gpt-4.1" }])).toEqual([
      { value: "policy-1", label: "openai/gpt-4.1 (policy-1)" },
    ]);
  });

  it("should build browser web token metadata for ledger attribution", () => {
    expect(buildChatbotWebTokenMetadata({ company_id: "company-1", project_id: "project-1" }, "chatbot-1")).toEqual(
      expect.objectContaining({
        cavadalabs_company_id: "company-1",
        cavadalabs_project_id: "project-1",
        cavadalabs_chatbot_id: "chatbot-1",
        spend_logs_metadata: expect.objectContaining({
          cavadalabs_company_id: "company-1",
          cavadalabs_project_id: "project-1",
          cavadalabs_chatbot_id: "chatbot-1",
        }),
      }),
    );
  });
});
