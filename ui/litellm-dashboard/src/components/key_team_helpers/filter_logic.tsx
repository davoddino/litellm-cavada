import { useCallback, useEffect, useState, useRef } from "react";
import { KeyResponse } from "../key_team_helpers/key_list";
import { keyListCall } from "../networking";
import { Team } from "../key_team_helpers/key_list";
import { fetchAllOrganizations, fetchAllTeams } from "./filter_helpers";
import { debounce } from "lodash";
import { defaultPageSize } from "../constants";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";
import {
  findCavadaLabsCompanyForCompatibilityOrganization,
  findCavadaLabsProjectForCompatibilityTeam,
  getKeyCavadaLabsCompanyId,
  getKeyCavadaLabsProjectId,
} from "../cavadalabs/keyContext";
import type { CavadaLabsKeyContextOptions } from "../cavadalabs/keyContext";
import { resolveCavadaLabsProductContext } from "../cavadalabs/productContext";

export interface FilterState {
  "Team ID": string;
  "Organization ID": string;
  "Company ID": string;
  "Project ID": string;
  "Key Alias": string;
  "Key Hash": string;
  [key: string]: string;
  "User ID": string;
  "Sort By": string;
  "Sort Order": string;
}

const keyMatchesCavadaLabsCompany = (
  key: KeyResponse,
  companyId: string,
  companies: CavadaLabsKeyContextOptions["companies"],
) => {
  const explicitCompanyId = getKeyCavadaLabsCompanyId(key);
  if (explicitCompanyId) {
    return explicitCompanyId === companyId;
  }

  const compatibilityOrganizationId = key.organization_id ?? (key as any).org_id ?? null;
  const compatibilityCompany = findCavadaLabsCompanyForCompatibilityOrganization(
    companies,
    compatibilityOrganizationId,
  );
  return compatibilityCompany?.company_id === companyId;
};

const keyMatchesCavadaLabsProject = (
  key: KeyResponse,
  projectId: string,
  projects: CavadaLabsKeyContextOptions["projects"],
) => {
  const explicitProjectId = getKeyCavadaLabsProjectId(key);
  if (explicitProjectId) {
    return explicitProjectId === projectId;
  }

  const compatibilityProject = findCavadaLabsProjectForCompatibilityTeam(projects, key.team_id);
  return compatibilityProject?.project_id === projectId;
};

export const normalizeVirtualKeyFilterState = (newFilters: Record<string, string>): FilterState => {
  const companyId = newFilters["Company ID"] || "";
  const projectId = newFilters["Project ID"] || "";
  const hasCavadaLabsProductFilter = Boolean(companyId || projectId);

  return {
    "Team ID": hasCavadaLabsProductFilter ? "" : newFilters["Team ID"] || "",
    "Organization ID": hasCavadaLabsProductFilter ? "" : newFilters["Organization ID"] || "",
    "Company ID": companyId,
    "Project ID": projectId,
    "Key Alias": newFilters["Key Alias"] || "",
    "Key Hash": newFilters["Key Hash"] || "",
    "User ID": newFilters["User ID"] || "",
    "Sort By": newFilters["Sort By"] || "created_at",
    "Sort Order": newFilters["Sort Order"] || "desc",
  };
};

const EMPTY_CAVADALABS_CONTEXT_OPTIONS: CavadaLabsKeyContextOptions = {
  companies: [],
  projects: [],
  isLoading: false,
  errorDetail: null,
  contextKnown: false,
  isCavadaLabsProductContext: false,
};

export function useFilterLogic({
  keys,
  teams,
  cavadalabsContextOptions = EMPTY_CAVADALABS_CONTEXT_OPTIONS,
}: {
  keys: KeyResponse[];
  teams: Team[] | null;
  cavadalabsContextOptions?: CavadaLabsKeyContextOptions;
}) {
  const defaultFilters: FilterState = {
    "Team ID": "",
    "Organization ID": "",
    "Company ID": "",
    "Project ID": "",
    "Key Alias": "",
    "Key Hash": "",
    "User ID": "",
    "Sort By": "created_at",
    "Sort Order": "desc",
  };
  const { accessToken } = useAuthorized();
  const { companies: allCompanies, projects: allProjects } = cavadalabsContextOptions;
  const cavadalabsProductContext = resolveCavadaLabsProductContext(cavadalabsContextOptions);
  const [filters, setFilters] = useState<FilterState>(defaultFilters);
  const [allTeams, setAllTeams] = useState<Team[]>(teams || []);
  const [allOrganizations, setAllOrganizations] = useState<
    Array<{ organization_id: string; organization_alias?: string }>
  >([]);
  const [filteredKeys, setFilteredKeys] = useState<KeyResponse[]>(keys);
  const [filteredTotalCount, setFilteredTotalCount] = useState<number | null>(null);
  const lastSearchTimestamp = useRef(0);
  const debouncedSearch = useCallback(
    debounce(async (filters: FilterState) => {
      if (!accessToken) {
        return;
      }

      const currentTimestamp = Date.now();
      lastSearchTimestamp.current = currentTimestamp;

      try {
        // Make the API call using keyListCall with all filter parameters
        const data = await keyListCall(
          accessToken,
          filters["Organization ID"] || null,
          filters["Team ID"] || null,
          filters["Key Alias"] || null,
          filters["User ID"] || null,
          filters["Key Hash"] || null,
          1, // Reset to first page when searching
          defaultPageSize,
          filters["Sort By"] || null,
          filters["Sort Order"] || null,
          null,
          null,
          filters["Company ID"] || null,
          filters["Project ID"] || null,
        );

        // Only update state if this is the most recent search
        if (currentTimestamp === lastSearchTimestamp.current) {
          if (data) {
            setFilteredKeys(data.keys);
            setFilteredTotalCount(data.total_count ?? null);
            console.log("called from debouncedSearch filters:", JSON.stringify(filters));
            console.log("called from debouncedSearch data:", JSON.stringify(data));
          }
        }
      } catch (error) {
        console.error("Error searching users:", error);
      }
    }, 300),
    [accessToken],
  );
  // Apply filters to keys whenever keys or filters change
  useEffect(() => {
    if (!keys) {
      setFilteredKeys([]);
      return;
    }

    let result = [...keys];

    // Apply Team ID filter
    if (filters["Team ID"]) {
      result = result.filter((key) => key.team_id === filters["Team ID"]);
    }

    if (filters["Organization ID"]) {
      result = result.filter(
        (key) => (key.organization_id ?? (key as any).org_id ?? null) === filters["Organization ID"],
      );
    }

    if (filters["Company ID"]) {
      result = result.filter((key) => keyMatchesCavadaLabsCompany(key, filters["Company ID"], allCompanies));
    }

    if (filters["Project ID"]) {
      result = result.filter((key) => keyMatchesCavadaLabsProject(key, filters["Project ID"], allProjects));
    }

    setFilteredKeys(result);
  }, [keys, filters, allCompanies, allProjects]);

  // Fetch all data for filters when component mounts
  useEffect(() => {
    const loadAllFilterData = async () => {
      // Load LiteLLM compatibility entities; Company/Project context is loaded through CavadaLabs resources.
      const [teamsData, organizationsData] = await Promise.all([
        fetchAllTeams(accessToken),
        fetchAllOrganizations(accessToken),
      ]);
      if (teamsData.length > 0) {
        setAllTeams(teamsData);
      }
      if (organizationsData.length > 0) {
        setAllOrganizations(organizationsData);
      }
    };

    if (accessToken) {
      loadAllFilterData();
    }
  }, [accessToken]);

  // Update teams when props change
  useEffect(() => {
    if (teams && teams.length > 0) {
      setAllTeams((prevTeams) => {
        // Only update if we don't already have a larger set of teams
        return prevTeams.length < teams.length ? teams : prevTeams;
      });
    }
  }, [teams]);

  const handleFilterChange = (newFilters: Record<string, string>, skipDebounce: boolean = false) => {
    const nextFilters = normalizeVirtualKeyFilterState(newFilters);

    // Update filters state
    setFilters(nextFilters);

    // Only trigger debouncedSearch if skipDebounce is false
    // This allows sorting to be handled by the parent component's useKeys hook
    if (!skipDebounce) {
      debouncedSearch(nextFilters);
    }
  };

  const handleFilterReset = () => {
    // Reset filters state
    setFilters(defaultFilters);
    setFilteredTotalCount(null);

    // Reset selections
    debouncedSearch(defaultFilters);
  };

  return {
    filters,
    filteredKeys,
    filteredTotalCount,
    allTeams,
    allOrganizations,
    allCompanies,
    allProjects,
    cavadalabsProductContext,
    handleFilterChange,
    handleFilterReset,
  };
}
