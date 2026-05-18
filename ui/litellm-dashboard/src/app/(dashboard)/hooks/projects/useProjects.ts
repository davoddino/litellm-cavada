import { useQuery } from "@tanstack/react-query";
import { createQueryKeys } from "../common/queryKeysFactory";
import {
  getProxyBaseUrl,
  getGlobalLitellmHeaderName,
  deriveErrorMessage,
  handleError,
} from "@/components/networking";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";
import { all_admin_roles } from "@/utils/roles";

// ── Types ────────────────────────────────────────────────────────────────────

export interface ProjectBudget {
  budget_id: string;
  max_budget: number | null;
  soft_budget: number | null;
  max_parallel_requests: number | null;
  tpm_limit: number | null;
  rpm_limit: number | null;
  model_max_budget: Record<string, number> | null;
  budget_duration: string | null;
}

export interface ProjectResponse {
  project_id: string;
  company_id?: string | null;
  project_alias: string | null;
  description: string | null;
  team_id: string | null;
  budget_id: string | null;
  metadata: Record<string, unknown> | null;
  models: string[];
  spend: number;
  model_spend: Record<string, number> | null;
  model_rpm_limit: Record<string, number> | null;
  model_tpm_limit: Record<string, number> | null;
  blocked: boolean;
  object_permission_id: string | null;
  created_at: string;
  created_by: string;
  updated_at: string;
  updated_by: string;
  litellm_budget_table: ProjectBudget | null;
}

// ── Query keys (shared across project hooks) ─────────────────────────────────

export const projectKeys = createQueryKeys("projects");

interface UseProjectsOptions {
  includeNonAdmin?: boolean;
  companyID?: string | null;
  organizationID?: string | null;
}

// ── Fetch function ───────────────────────────────────────────────────────────

export const projectListCall = async (
  accessToken: string,
  options: UseProjectsOptions = {},
): Promise<ProjectResponse[]> => {
  const baseUrl = getProxyBaseUrl();
  const queryParams = new URLSearchParams();
  const companyID = options.companyID ?? options.organizationID;
  if (companyID) {
    queryParams.append("company_id", companyID);
  }
  const url = `${baseUrl}/project/list${queryParams.toString() ? `?${queryParams.toString()}` : ""}`;

  const response = await fetch(url, {
    method: "GET",
    headers: {
      [getGlobalLitellmHeaderName()]: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    const errorData = await response.json();
    const errorMessage = deriveErrorMessage(errorData);
    handleError(errorMessage);
    throw new Error(errorMessage);
  }

  return response.json();
};

export const useProjects = (options: UseProjectsOptions = {}) => {
  const { accessToken, userRole } = useAuthorized();
  const { includeNonAdmin = false } = options;
  const companyID = options.companyID ?? options.organizationID ?? null;

  return useQuery<ProjectResponse[]>({
    queryKey: projectKeys.list(
      companyID ? { filters: { companyID } } : {},
    ),
    queryFn: async () => projectListCall(accessToken!, options),
    enabled:
      Boolean(accessToken) &&
      (includeNonAdmin || all_admin_roles.includes(userRole!)),
  });
};
