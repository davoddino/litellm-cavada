import { describe, expect, it } from "vitest";
import {
  deriveSingleCavadaLabsKeyContextSelection,
  findCavadaLabsCompanyForCompatibilityOrganization,
  findCavadaLabsProjectForCompatibilityTeam,
  getCavadaLabsCompanyDisplayName,
  getCavadaLabsCompanyLabelForCompatibilityOrganization,
  getCavadaLabsProjectDisplayName,
  getCavadaLabsProjectLabelForCompatibilityTeam,
  getKeyCavadaLabsCompanyId,
  getKeyCavadaLabsProjectId,
  canManageCavadaLabsKeyContext,
  filterManageableCavadaLabsCompanies,
  filterManageableCavadaLabsProjects,
  resolveCavadaLabsCompanyCompatibilityOrganizationId,
  resolveCavadaLabsProjectCompatibilityTeamId,
  stripLiteLLMCompatibilityFieldsForCavadaLabsKey,
  validateCavadaLabsKeyContextSelection,
} from "./keyContext";

describe("CavadaLabs key context helpers", () => {
  it("should prefer first-class key context fields", () => {
    const key = {
      cavadalabs_company_id: "company-canonical",
      cavadalabs_project_id: "project-canonical",
      metadata: {
        cavadalabs_company_id: "company-metadata",
        cavadalabs_project_id: "project-metadata",
      },
    };

    expect(getKeyCavadaLabsCompanyId(key)).toBe("company-canonical");
    expect(getKeyCavadaLabsProjectId(key)).toBe("project-canonical");
  });

  it("should read legacy spend log metadata when canonical fields are absent", () => {
    const key = {
      metadata: {
        spend_logs_metadata: {
          cavadalabs_company_id: "company-legacy",
          cavadalabs_project_id: "project-legacy",
        },
      },
    };

    expect(getKeyCavadaLabsCompanyId(key)).toBe("company-legacy");
    expect(getKeyCavadaLabsProjectId(key)).toBe("project-legacy");
  });

  it("should read CavadaLabs Company and Project aliases from key metadata", () => {
    expect(
      getKeyCavadaLabsCompanyId({
        metadata: { cavadalabs: { cavadalabs_company_id: "company-nested" } },
      }),
    ).toBe("company-nested");
    expect(
      getKeyCavadaLabsProjectId({
        metadata: { cavadalabs: { cavadalabs_project_id: "project-nested" } },
      }),
    ).toBe("project-nested");
    expect(
      getKeyCavadaLabsCompanyId({
        metadata: { spend_logs_metadata: { company_id: "company-spend" } },
      }),
    ).toBe("company-spend");
    expect(
      getKeyCavadaLabsProjectId({
        metadata: { spend_logs_metadata: { project_id: "project-spend" } },
      }),
    ).toBe("project-spend");
  });

  it("should format company options with legal name when available", () => {
    expect(
      getCavadaLabsCompanyDisplayName({
        company_id: "company-1",
        legal_name: "My Company",
        litellm_organization_id: "org-1",
      }),
    ).toBe("My Company (company-1)");
    expect(getCavadaLabsCompanyDisplayName({ company_id: "company-2" })).toBe("company-2");
  });

  it("should format project options with project name when available", () => {
    expect(
      getCavadaLabsProjectDisplayName({
        project_id: "project-1",
        company_id: "company-1",
        name: "Support",
        litellm_team_id: "team-1",
      }),
    ).toBe("Support (project-1)");
    expect(getCavadaLabsProjectDisplayName({ project_id: "project-2", company_id: "company-1" })).toBe("project-2");
  });

  it("should resolve compatibility organization IDs through Company mappings", () => {
    const companies = [
      {
        company_id: "company-1",
        legal_name: "My Company",
        litellm_organization_id: "org-1",
      },
    ];

    expect(resolveCavadaLabsCompanyCompatibilityOrganizationId("company-1", companies)).toBe("org-1");
    expect(findCavadaLabsCompanyForCompatibilityOrganization(companies, "org-1")?.company_id).toBe("company-1");
    expect(getCavadaLabsCompanyLabelForCompatibilityOrganization(companies, "org-1")).toBe("My Company (company-1)");
  });

  it("should reject Company options without compatibility mappings", () => {
    expect(() =>
      resolveCavadaLabsCompanyCompatibilityOrganizationId("company-2", [
        {
          company_id: "company-2",
          legal_name: "No Mapping Inc",
          litellm_organization_id: null,
        },
      ]),
    ).toThrow("Company company-2 is missing its compatibility mapping");
  });

  it("should resolve compatibility team IDs through Project mappings", () => {
    const projects = [
      {
        project_id: "project-1",
        company_id: "company-1",
        name: "Support",
        litellm_team_id: "team-1",
      },
    ];

    expect(resolveCavadaLabsProjectCompatibilityTeamId("project-1", projects)).toBe("team-1");
    expect(findCavadaLabsProjectForCompatibilityTeam(projects, "team-1")?.project_id).toBe("project-1");
    expect(getCavadaLabsProjectLabelForCompatibilityTeam(projects, "team-1")).toBe("Support (project-1)");
  });

  it("should not expose internal team IDs when Project compatibility mapping is missing", () => {
    expect(getCavadaLabsProjectLabelForCompatibilityTeam([], "team-unknown")).toBe("Missing Project mapping");
  });

  it("should reject Project options without compatibility mappings", () => {
    expect(() =>
      resolveCavadaLabsProjectCompatibilityTeamId("project-2", [
        {
          project_id: "project-2",
          company_id: "company-1",
          litellm_team_id: null,
        },
      ]),
    ).toThrow("Project project-2 is missing its compatibility mapping");
  });

  it("should strip internal LiteLLM compatibility fields from CavadaLabs key payloads", () => {
    const payload = stripLiteLLMCompatibilityFieldsForCavadaLabsKey({
      cavadalabs_company_id: "company-1",
      cavadalabs_project_id: "project-1",
      organization_id: "org-internal",
      team_id: "team-internal",
      project_id: "litellm-project",
      key_alias: "support-key",
    });

    expect(payload).toEqual({
      cavadalabs_company_id: "company-1",
      cavadalabs_project_id: "project-1",
      key_alias: "support-key",
    });
  });

  it("should keep all Company and Project options when manage flags are not present", () => {
    expect(
      filterManageableCavadaLabsCompanies([{ company_id: "company-1" }, { company_id: "company-2" }]).map(
        (company) => company.company_id,
      ),
    ).toEqual(["company-1", "company-2"]);
    expect(
      filterManageableCavadaLabsProjects([
        { project_id: "project-1", company_id: "company-1" },
        { project_id: "project-2", company_id: "company-2" },
      ]).map((project) => project.project_id),
    ).toEqual(["project-1", "project-2"]);
  });

  it("should keep only manageable Company and Project options when manage flags are present", () => {
    expect(
      filterManageableCavadaLabsCompanies([
        { company_id: "company-admin", cavadalabs_can_manage: true },
        { company_id: "company-viewer", cavadalabs_can_manage: false },
      ]).map((company) => company.company_id),
    ).toEqual(["company-admin"]);
    expect(
      filterManageableCavadaLabsProjects([
        { project_id: "project-admin", company_id: "company-admin", cavadalabs_can_manage: true },
        { project_id: "project-viewer", company_id: "company-viewer", cavadalabs_can_manage: false },
      ]).map((project) => project.project_id),
    ).toEqual(["project-admin"]);
  });

  it("should include parent Company options for manageable Project scopes", () => {
    expect(
      filterManageableCavadaLabsCompanies(
        [
          { company_id: "company-admin", cavadalabs_can_manage: true },
          { company_id: "company-project", cavadalabs_can_manage: false },
          { company_id: "company-viewer", cavadalabs_can_manage: false },
        ],
        [
          { project_id: "project-admin", company_id: "company-project", cavadalabs_can_manage: true },
          { project_id: "project-viewer", company_id: "company-viewer", cavadalabs_can_manage: false },
        ],
      ).map((company) => company.company_id),
    ).toEqual(["company-admin", "company-project"]);
  });

  it("should identify editable CavadaLabs key context from Company or Project manage access", () => {
    const companies = [
      { company_id: "company-admin", cavadalabs_can_manage: true },
      { company_id: "company-viewer", cavadalabs_can_manage: false },
    ];
    const projects = [
      { project_id: "project-admin", company_id: "company-viewer", cavadalabs_can_manage: true },
      { project_id: "project-viewer", company_id: "company-viewer", cavadalabs_can_manage: false },
    ];

    expect(
      canManageCavadaLabsKeyContext({
        companies,
        projects,
        companyId: "company-admin",
        projectId: "project-viewer",
      }),
    ).toBe(true);
    expect(
      canManageCavadaLabsKeyContext({
        companies,
        projects,
        companyId: "company-viewer",
        projectId: "project-admin",
      }),
    ).toBe(true);
    expect(
      canManageCavadaLabsKeyContext({
        companies,
        projects,
        companyId: "company-viewer",
        projectId: "project-viewer",
      }),
    ).toBe(false);
  });

  it("should derive the sole available Company and Project key context", () => {
    expect(
      deriveSingleCavadaLabsKeyContextSelection({
        companyId: null,
        projectId: null,
        companies: [{ company_id: "company-1" }],
        projects: [{ project_id: "project-1", company_id: "company-1" }],
      }),
    ).toEqual({ companyId: "company-1", projectId: "project-1" });
  });

  it("should not derive Company and Project key context when scope is ambiguous", () => {
    expect(
      deriveSingleCavadaLabsKeyContextSelection({
        companyId: null,
        projectId: null,
        companies: [{ company_id: "company-1" }],
        projects: [
          { project_id: "project-1", company_id: "company-1" },
          { project_id: "project-2", company_id: "company-1" },
        ],
      }),
    ).toEqual({ companyId: null, projectId: null });
  });

  it("should validate required Company and Project key context", () => {
    expect(
      validateCavadaLabsKeyContextSelection({
        companyId: null,
        projectId: null,
        projects: [{ project_id: "project-1", company_id: "company-1" }],
        required: true,
        actionLabel: "creating",
      }),
    ).toBe("Select both Company and Project before creating a CavadaLabs key");
  });

  it("should reject mismatched Company and Project key context", () => {
    expect(
      validateCavadaLabsKeyContextSelection({
        companyId: "company-1",
        projectId: "project-2",
        projects: [{ project_id: "project-2", company_id: "company-2" }],
        required: true,
        actionLabel: "saving",
      }),
    ).toBe("Selected Project belongs to a different Company");
  });
});
