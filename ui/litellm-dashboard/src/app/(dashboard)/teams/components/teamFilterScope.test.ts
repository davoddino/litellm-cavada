import { describe, expect, it } from "vitest";
import { buildTeamsListScopeParams, normalizeTeamsFilterUpdate } from "./teamFilterScope";
import type { TeamsListFilterState } from "./teamFilterScope";

const baseFilters: TeamsListFilterState = {
  team_id: "",
  team_alias: "",
  cavadalabs_company_id: "",
  cavadalabs_project_id: "",
  sort_by: "created_at",
  sort_order: "desc",
};

describe("teamFilterScope", () => {
  it("should clear legacy Team ID when applying CavadaLabs Company and Project filters", () => {
    const filters = normalizeTeamsFilterUpdate(
      { ...baseFilters, team_id: "team-legacy" },
      {
        cavadalabs_company_id: "company-1",
        cavadalabs_project_id: "project-1",
      },
      true,
    );

    expect(filters.team_id).toBe("");
    expect(filters.cavadalabs_company_id).toBe("company-1");
    expect(filters.cavadalabs_project_id).toBe("project-1");
    expect(buildTeamsListScopeParams(filters, true)).toEqual({
      teamId: null,
      teamAlias: null,
      cavadalabsCompanyId: "company-1",
      cavadalabsProjectId: "project-1",
    });
  });

  it("should keep legacy Team filtering outside CavadaLabs product context", () => {
    const filters = normalizeTeamsFilterUpdate(
      baseFilters,
      {
        team_id: "team-legacy",
        cavadalabs_company_id: "company-ignored",
        cavadalabs_project_id: "project-ignored",
      },
      false,
    );

    expect(filters.cavadalabs_company_id).toBe("");
    expect(filters.cavadalabs_project_id).toBe("");
    expect(buildTeamsListScopeParams(filters, false)).toEqual({
      teamId: "team-legacy",
      teamAlias: null,
      cavadalabsCompanyId: null,
      cavadalabsProjectId: null,
    });
  });
});
