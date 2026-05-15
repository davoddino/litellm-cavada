import { useCallback, useEffect, useState, useRef } from "react";
import { KeyResponse } from "../key_team_helpers/key_list";
import { keyListCall } from "../networking";
import { Team } from "../key_team_helpers/key_list";
import { fetchAllTeams } from "./filter_helpers";
import { debounce } from "lodash";
import { defaultPageSize } from "../constants";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";
import {
  getKeyCavadaLabsCompanyId,
  getKeyCavadaLabsProjectId,
  useCavadaLabsKeyContextOptions,
} from "../cavadalabs/keyContext";

export interface FilterState {
  "Team ID": string;
  "Company ID": string;
  "Project ID": string;
  "Key Alias": string;
  [key: string]: string;
  "User ID": string;
  "Sort By": string;
  "Sort Order": string;
}

export function useFilterLogic({
  keys,
  teams,
}: {
  keys: KeyResponse[];
  teams: Team[] | null;
}) {
  const defaultFilters: FilterState = {
    "Team ID": "",
    "Company ID": "",
    "Project ID": "",
    "Key Alias": "",
    "User ID": "",
    "Sort By": "created_at",
    "Sort Order": "desc",
  };
  const { accessToken } = useAuthorized();
  const { companies: allCompanies, projects: allProjects } = useCavadaLabsKeyContextOptions(accessToken);
  const [filters, setFilters] = useState<FilterState>(defaultFilters);
  const [allTeams, setAllTeams] = useState<Team[]>(teams || []);
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
          null,
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

    if (filters["Company ID"]) {
      result = result.filter((key) => getKeyCavadaLabsCompanyId(key) === filters["Company ID"]);
    }

    if (filters["Project ID"]) {
      result = result.filter((key) => getKeyCavadaLabsProjectId(key) === filters["Project ID"]);
    }

    setFilteredKeys(result);
  }, [keys, filters]);

  // Fetch all data for filters when component mounts
  useEffect(() => {
    const loadAllFilterData = async () => {
      // Load all teams; Company/Project context is loaded through CavadaLabs resources.
      const teamsData = await fetchAllTeams(accessToken);
      if (teamsData.length > 0) {
        setAllTeams(teamsData);
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
    // Update filters state
    setFilters({
      "Team ID": newFilters["Team ID"] || "",
      "Company ID": newFilters["Company ID"] || "",
      "Project ID": newFilters["Project ID"] || "",
      "Key Alias": newFilters["Key Alias"] || "",
      "User ID": newFilters["User ID"] || "",
      "Sort By": newFilters["Sort By"] || "created_at",
      "Sort Order": newFilters["Sort Order"] || "desc",
    });

    // Only trigger debouncedSearch if skipDebounce is false
    // This allows sorting to be handled by the parent component's useKeys hook
    if (!skipDebounce) {
      // Fetch keys based on new filters
      const updatedFilters = {
        ...filters,
        ...newFilters,
      };
      debouncedSearch(updatedFilters);
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
    allCompanies,
    allProjects,
    handleFilterChange,
    handleFilterReset,
  };
}
