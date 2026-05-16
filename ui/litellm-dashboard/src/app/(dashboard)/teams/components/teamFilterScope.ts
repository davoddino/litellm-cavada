export interface TeamsListFilterState {
  team_id: string;
  team_alias: string;
  cavadalabs_company_id: string;
  cavadalabs_project_id: string;
  sort_by: string;
  sort_order: "asc" | "desc";
}

export interface TeamsListScopeParams {
  teamId: string | null;
  teamAlias: string | null;
  cavadalabsCompanyId: string | null;
  cavadalabsProjectId: string | null;
}

export const normalizeTeamsFilterUpdate = (
  currentFilters: TeamsListFilterState,
  update: Partial<TeamsListFilterState>,
  isCavadaLabsProductContext: boolean,
): TeamsListFilterState => {
  const nextFilters = { ...currentFilters, ...update };

  if (isCavadaLabsProductContext) {
    return {
      ...nextFilters,
      team_id: "",
    };
  }

  return {
    ...nextFilters,
    cavadalabs_company_id: "",
    cavadalabs_project_id: "",
  };
};

export const buildTeamsListScopeParams = (
  filters: TeamsListFilterState,
  isCavadaLabsProductContext: boolean,
): TeamsListScopeParams => ({
  teamId: isCavadaLabsProductContext ? null : filters.team_id || null,
  teamAlias: filters.team_alias || null,
  cavadalabsCompanyId: isCavadaLabsProductContext ? filters.cavadalabs_company_id || null : null,
  cavadalabsProjectId: isCavadaLabsProductContext ? filters.cavadalabs_project_id || null : null,
});
