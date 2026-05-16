import { useEffect, useMemo, useState } from "react";
import { cavadaLabsErrorDetailFromUnknown, listCavadaLabsResource } from "./api";
import type { CavadaLabsStructuredErrorDetail } from "./api";
import type { KeyResponse } from "../key_team_helpers/key_list";

export interface CavadaLabsCompanyOption {
  company_id: string;
  litellm_organization_id?: string | null;
  legal_name?: string;
  status?: string;
  cavadalabs_access_role?: string | null;
  cavadalabs_can_manage?: boolean;
}

export interface CavadaLabsProjectOption {
  project_id: string;
  company_id: string;
  litellm_team_id?: string | null;
  name?: string;
  status?: string;
  allowed_models?: string[];
  cavadalabs_access_role?: string | null;
  cavadalabs_can_manage?: boolean;
}

export interface CavadaLabsKeyContextOptions {
  companies: CavadaLabsCompanyOption[];
  projects: CavadaLabsProjectOption[];
  isLoading: boolean;
  errorDetail: CavadaLabsStructuredErrorDetail | null;
}

export const getKeyCavadaLabsCompanyId = (key: Partial<KeyResponse>): string | null => {
  const metadata = typeof key.metadata === "object" && key.metadata !== null ? key.metadata : {};
  const cavadalabs = metadata.cavadalabs;
  const spendLogsMetadata = metadata.spend_logs_metadata;
  if (typeof key.cavadalabs_company_id === "string" && key.cavadalabs_company_id) {
    return key.cavadalabs_company_id;
  }
  if (typeof metadata.cavadalabs_company_id === "string" && metadata.cavadalabs_company_id) {
    return metadata.cavadalabs_company_id;
  }
  if (typeof cavadalabs === "object" && cavadalabs !== null && "company_id" in cavadalabs) {
    const companyId = cavadalabs.company_id;
    return typeof companyId === "string" && companyId ? companyId : null;
  }
  if (
    typeof spendLogsMetadata === "object" &&
    spendLogsMetadata !== null &&
    "cavadalabs_company_id" in spendLogsMetadata
  ) {
    const companyId = spendLogsMetadata.cavadalabs_company_id;
    return typeof companyId === "string" && companyId ? companyId : null;
  }
  return null;
};

export const getKeyCavadaLabsProjectId = (key: Partial<KeyResponse>): string | null => {
  const metadata = typeof key.metadata === "object" && key.metadata !== null ? key.metadata : {};
  const cavadalabs = metadata.cavadalabs;
  const spendLogsMetadata = metadata.spend_logs_metadata;
  if (typeof key.cavadalabs_project_id === "string" && key.cavadalabs_project_id) {
    return key.cavadalabs_project_id;
  }
  if (typeof metadata.cavadalabs_project_id === "string" && metadata.cavadalabs_project_id) {
    return metadata.cavadalabs_project_id;
  }
  if (typeof cavadalabs === "object" && cavadalabs !== null && "project_id" in cavadalabs) {
    const projectId = cavadalabs.project_id;
    return typeof projectId === "string" && projectId ? projectId : null;
  }
  if (
    typeof spendLogsMetadata === "object" &&
    spendLogsMetadata !== null &&
    "cavadalabs_project_id" in spendLogsMetadata
  ) {
    const projectId = spendLogsMetadata.cavadalabs_project_id;
    return typeof projectId === "string" && projectId ? projectId : null;
  }
  return null;
};

export const getCavadaLabsCompanyDisplayName = (company: CavadaLabsCompanyOption): string => {
  const name = company.legal_name?.trim();
  return name ? `${name} (${company.company_id})` : company.company_id;
};

export const getCavadaLabsProjectDisplayName = (project: CavadaLabsProjectOption): string => {
  const name = project.name?.trim();
  return name ? `${name} (${project.project_id})` : project.project_id;
};

export const findCavadaLabsCompanyForCompatibilityOrganization = (
  companies: CavadaLabsCompanyOption[],
  organizationId: string | null | undefined,
): CavadaLabsCompanyOption | null => {
  if (!organizationId) {
    return null;
  }
  return companies.find((company) => company.litellm_organization_id === organizationId) ?? null;
};

export const findCavadaLabsProjectForCompatibilityTeam = (
  projects: CavadaLabsProjectOption[],
  teamId: string | null | undefined,
): CavadaLabsProjectOption | null => {
  if (!teamId) {
    return null;
  }
  return projects.find((project) => project.litellm_team_id === teamId) ?? null;
};

export const resolveCavadaLabsCompanyCompatibilityOrganizationId = (
  companyId: string | null | undefined,
  companies: CavadaLabsCompanyOption[],
): string | null => {
  if (!companyId) {
    return null;
  }

  const company = companies.find((item) => item.company_id === companyId);
  if (!company) {
    throw new Error(`Company ${companyId} is not available`);
  }
  if (!company.litellm_organization_id) {
    throw new Error(`Company ${companyId} is missing its compatibility mapping`);
  }
  return company.litellm_organization_id;
};

export const resolveCavadaLabsProjectCompatibilityTeamId = (
  projectId: string | null | undefined,
  projects: CavadaLabsProjectOption[],
): string | null => {
  if (!projectId) {
    return null;
  }

  const project = projects.find((item) => item.project_id === projectId);
  if (!project) {
    throw new Error(`Project ${projectId} is not available`);
  }
  if (!project.litellm_team_id) {
    throw new Error(`Project ${projectId} is missing its compatibility mapping`);
  }
  return project.litellm_team_id;
};

export const getCavadaLabsCompanyLabelForCompatibilityOrganization = (
  companies: CavadaLabsCompanyOption[],
  organizationId: string | null | undefined,
): string => {
  if (!organizationId) {
    return "—";
  }

  const company = findCavadaLabsCompanyForCompatibilityOrganization(companies, organizationId);
  return company ? getCavadaLabsCompanyDisplayName(company) : "Missing Company mapping";
};

export const getCavadaLabsProjectLabelForCompatibilityTeam = (
  projects: CavadaLabsProjectOption[],
  teamId: string | null | undefined,
): string => {
  if (!teamId) {
    return "—";
  }

  const project = findCavadaLabsProjectForCompatibilityTeam(projects, teamId);
  return project ? getCavadaLabsProjectDisplayName(project) : "Missing Project mapping";
};

const hasExplicitManageFlag = <T extends { cavadalabs_can_manage?: boolean }>(options: T[]): boolean =>
  options.some((option) => typeof option.cavadalabs_can_manage === "boolean");

export const filterManageableCavadaLabsCompanies = (
  companies: CavadaLabsCompanyOption[],
): CavadaLabsCompanyOption[] => {
  if (!hasExplicitManageFlag(companies)) {
    return companies;
  }

  return companies.filter((company) => company.cavadalabs_can_manage === true);
};

export const filterManageableCavadaLabsProjects = (projects: CavadaLabsProjectOption[]): CavadaLabsProjectOption[] => {
  if (!hasExplicitManageFlag(projects)) {
    return projects;
  }

  return projects.filter((project) => project.cavadalabs_can_manage === true);
};

export const stripLiteLLMCompatibilityFieldsForCavadaLabsKey = <T extends Record<string, any>>(values: T): T => {
  if (!values.cavadalabs_company_id && !values.cavadalabs_project_id) {
    return values;
  }

  delete values.organization_id;
  delete values.team_id;
  delete values.project_id;
  return values;
};

export const useCavadaLabsKeyContextOptions = (accessToken: string | null | undefined): CavadaLabsKeyContextOptions => {
  const [companies, setCompanies] = useState<CavadaLabsCompanyOption[]>([]);
  const [projects, setProjects] = useState<CavadaLabsProjectOption[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [errorDetail, setErrorDetail] = useState<CavadaLabsStructuredErrorDetail | null>(null);

  useEffect(() => {
    let isMounted = true;
    if (!accessToken) {
      setCompanies([]);
      setProjects([]);
      setErrorDetail(null);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setErrorDetail(null);
    Promise.all([
      listCavadaLabsResource<{ companies?: CavadaLabsCompanyOption[] }>(accessToken, "/cavadalabs/companies"),
      listCavadaLabsResource<{ projects?: CavadaLabsProjectOption[] }>(accessToken, "/cavadalabs/projects"),
    ])
      .then(([companyResponse, projectResponse]) => {
        if (!isMounted) return;
        setCompanies(companyResponse.companies ?? []);
        setProjects(projectResponse.projects ?? []);
      })
      .catch((error) => {
        if (!isMounted) return;
        setCompanies([]);
        setProjects([]);
        setErrorDetail(cavadaLabsErrorDetailFromUnknown(error));
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [accessToken]);

  return useMemo(
    () => ({ companies, projects, isLoading, errorDetail }),
    [companies, projects, isLoading, errorDetail],
  );
};
