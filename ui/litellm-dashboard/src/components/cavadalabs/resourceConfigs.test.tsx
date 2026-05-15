import { describe, expect, it } from "vitest";
import { buildCavadaLabsResourceConfigs } from "./resourceConfigs";
import type { CavadaLabsFieldConfig, CavadaLabsRuntimeContext } from "./types";

const context: CavadaLabsRuntimeContext = {
  companies: [{ company_id: "company-1", legal_name: "Acme Srl" }],
  projects: [{ project_id: "project-1", name: "Dispatch Project" }],
  chatbots: [{ chatbot_id: "chatbot-1", name: "Support Bot" }],
  ragCollections: [{ collection_id: "collection-1", name: "Knowledge Base" }],
  nodes: [{ node_id: "node-1", display_name: "GPU Node 1" }],
};

const field = (fields: CavadaLabsFieldConfig[] | undefined, name: string): CavadaLabsFieldConfig => {
  const config = fields?.find((item) => item.name === name);
  if (!config) throw new Error(`Missing field ${name}`);
  return config;
};

const values = (fieldConfig: CavadaLabsFieldConfig): Array<string | number | boolean> =>
  fieldConfig.options?.map((option) => option.value) ?? [];

describe("buildCavadaLabsResourceConfigs", () => {
  it("should bind create fields to runtime context options", () => {
    const configs = buildCavadaLabsResourceConfigs(context);

    expect(values(field(configs.projects.createFields, "company_id"))).toContain("company-1");
    expect(values(field(configs.chatbots.createFields, "assigned_rag_collections"))).toContain("collection-1");
    expect(values(field(configs.webTokens.createFields, "chatbot_id"))).toContain("chatbot-1");
    expect(values(field(configs.nodes.createFields, "allowed_project_ids"))).toContain("project-1");
  });

  it("should enforce project scoping for model policies", () => {
    const configs = buildCavadaLabsResourceConfigs(context);

    expect(configs.modelPolicies.requiredFilters).toEqual(["project_id"]);
    expect(configs.modelPolicies.getInitialFilters?.(context)).toEqual({ project_id: "project-1" });
    expect(configs.modelPolicies.filters?.map((item) => item.name)).toContain("project_id");
  });

  it("should configure editable and archivable companies and projects", () => {
    const configs = buildCavadaLabsResourceConfigs(context);

    expect(configs.companies.updatePath?.({ company_id: "company-1" })).toBe("/cavadalabs/companies/company-1");
    expect(configs.companies.updateFields?.map((item) => item.name)).toContain("legal_name");
    expect(
      configs.companies.rowActions?.find((action) => action.key === "archive")?.request({ company_id: "company-1" }),
    ).toEqual({
      method: "DELETE",
      path: "/cavadalabs/companies/company-1",
    });

    expect(configs.projects.updatePath?.({ project_id: "project-1" })).toBe("/cavadalabs/projects/project-1");
    expect(configs.projects.updateFields?.map((item) => item.name)).toContain("allowed_models");
    expect(
      configs.projects.rowActions?.find((action) => action.key === "archive")?.request({ project_id: "project-1" }),
    ).toEqual({
      method: "DELETE",
      path: "/cavadalabs/projects/project-1",
    });
  });

  it("should configure CavadaLabs usage views without legacy organizations", () => {
    const configs = buildCavadaLabsResourceConfigs(context);

    expect(Object.keys(configs)).toContain("companies");
    expect(Object.keys(configs)).toContain("projects");
    expect(Object.keys(configs)).not.toContain("organizations");
  });

  it("should configure runtime scheduler actions with project scoped payloads", () => {
    const configs = buildCavadaLabsResourceConfigs(context);
    const schedulerAction = configs.modelLoadRequests.toolbarActions?.find((action) => action.key === "schedule");

    expect(schedulerAction?.request({ project_id: "project-1", status: "queued" })).toEqual({
      method: "POST",
      path: "/cavadalabs/model-load-requests/schedule",
      body: {
        project_id: "project-1",
        take: 10,
        lock_ttl_seconds: 3600,
      },
    });
  });
});
