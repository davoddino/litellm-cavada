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
  cavadalabs_can_view_usage?: boolean;
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
  cavadalabs_can_view_usage?: boolean;
}

export interface CavadaLabsKeyContextOptions {
  companies: CavadaLabsCompanyOption[];
  projects: CavadaLabsProjectOption[];
  isLoading: boolean;
  errorDetail: CavadaLabsStructuredErrorDetail | null;
  contextKnown?: boolean;
  isCavadaLabsProductContext?: boolean;
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
  if (typeof metadata.company_id === "string" && metadata.company_id) {
    return metadata.company_id;
  }
  if (typeof cavadalabs === "object" && cavadalabs !== null) {
    const companyId = cavadalabs.cavadalabs_company_id || cavadalabs.company_id;
    return typeof companyId === "string" && companyId ? companyId : null;
  }
  if (typeof spendLogsMetadata === "object" && spendLogsMetadata !== null) {
    const companyId = spendLogsMetadata.cavadalabs_company_id || spendLogsMetadata.company_id;
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
  if (typeof metadata.project_id === "string" && metadata.project_id) {
    return metadata.project_id;
  }
  if (typeof cavadalabs === "object" && cavadalabs !== null) {
    const projectId = cavadalabs.cavadalabs_project_id || cavadalabs.project_id;
    return typeof projectId === "string" && projectId ? projectId : null;
  }
  if (typeof spendLogsMetadata === "object" && spendLogsMetadata !== null) {
    const projectId = spendLogsMetadata.cavadalabs_project_id || spendLogsMetadata.project_id;
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
  projects: CavadaLabsProjectOption[] = [],
): CavadaLabsCompanyOption[] => {
  const hasCompanyManageFlag = hasExplicitManageFlag(companies);
  const hasProjectManageFlag = hasExplicitManageFlag(projects);
  if (!hasCompanyManageFlag && !hasProjectManageFlag) {
    return companies;
  }

  const manageableProjectCompanyIds = new Set(
    hasProjectManageFlag
      ? projects.filter((project) => project.cavadalabs_can_manage === true).map((project) => project.company_id)
      : [],
  );
  return companies.filter(
    (company) => company.cavadalabs_can_manage === true || manageableProjectCompanyIds.has(company.company_id),
  );
};

export const filterManageableCavadaLabsProjects = (projects: CavadaLabsProjectOption[]): CavadaLabsProjectOption[] => {
  if (!hasExplicitManageFlag(projects)) {
    return projects;
  }

  return projects.filter((project) => project.cavadalabs_can_manage === true);
};

export const canManageCavadaLabsKeyContext = ({
  companies,
  projects,
  companyId,
  projectId,
}: {
  companies: CavadaLabsCompanyOption[];
  projects: CavadaLabsProjectOption[];
  companyId: string | null | undefined;
  projectId: string | null | undefined;
}): boolean => {
  const company = companyId ? companies.find((item) => item.company_id === companyId) : null;
  const project = projectId ? projects.find((item) => item.project_id === projectId) : null;
  return company?.cavadalabs_can_manage === true || project?.cavadalabs_can_manage === true;
};

export const deriveSingleCavadaLabsKeyContextSelection = ({
  companyId,
  projectId,
  companies,
  projects,
}: {
  companyId: string | null | undefined;
  projectId: string | null | undefined;
  companies: CavadaLabsCompanyOption[];
  projects: CavadaLabsProjectOption[];
}): { companyId: string | null; projectId: string | null } => {
  const normalizedCompanyId = companyId || null;
  const normalizedProjectId = projectId || null;
  if (normalizedCompanyId || normalizedProjectId) {
    return { companyId: normalizedCompanyId, projectId: normalizedProjectId };
  }

  if (companies.length !== 1 || projects.length !== 1) {
    return { companyId: normalizedCompanyId, projectId: normalizedProjectId };
  }

  const [company] = companies;
  const [project] = projects;
  if (project.company_id !== company.company_id) {
    return { companyId: normalizedCompanyId, projectId: normalizedProjectId };
  }

  return { companyId: company.company_id, projectId: project.project_id };
};

export const validateCavadaLabsKeyContextSelection = ({
  companyId,
  projectId,
  projects,
  required,
  actionLabel,
}: {
  companyId: string | null | undefined;
  projectId: string | null | undefined;
  projects: CavadaLabsProjectOption[];
  required: boolean;
  actionLabel: "creating" | "saving";
}): string | null => {
  if (required && (!companyId || !projectId)) {
    return `Select both Company and Project before ${actionLabel} a CavadaLabs key`;
  }

  if (!companyId && !projectId) {
    return null;
  }

  if (!companyId || !projectId) {
    return `Select both Company and Project before ${actionLabel} a CavadaLabs key`;
  }

  const selectedProject = projects.find((project) => project.project_id === projectId);
  if (!selectedProject) {
    return `Project ${projectId} is not available`;
  }

  if (selectedProject.company_id !== companyId) {
    return "Selected Project belongs to a different Company";
  }

  return null;
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
  const [contextKnown, setContextKnown] = useState(false);
  const [isCavadaLabsProductContext, setIsCavadaLabsProductContext] = useState(false);

  useEffect(() => {
    let isMounted = true;
    if (!accessToken) {
      setCompanies([]);
      setProjects([]);
      setErrorDetail(null);
      setIsLoading(false);
      setContextKnown(false);
      setIsCavadaLabsProductContext(false);
      return;
    }

    setIsLoading(true);
    setErrorDetail(null);
    setContextKnown(false);
    Promise.all([
      listCavadaLabsResource<{ companies?: CavadaLabsCompanyOption[] }>(accessToken, "/cavadalabs/companies"),
      listCavadaLabsResource<{ projects?: CavadaLabsProjectOption[] }>(accessToken, "/cavadalabs/projects"),
    ])
      .then(([companyResponse, projectResponse]) => {
        if (!isMounted) return;
        setCompanies(companyResponse.companies ?? []);
        setProjects(projectResponse.projects ?? []);
        setContextKnown(true);
        setIsCavadaLabsProductContext(true);
      })
      .catch((error) => {
        if (!isMounted) return;
        setCompanies([]);
        setProjects([]);
        setErrorDetail(cavadaLabsErrorDetailFromUnknown(error));
        setContextKnown(true);
        setIsCavadaLabsProductContext((error as { status?: number })?.status !== 404);
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [accessToken]);

  return useMemo(
    () => ({
      companies,
      projects,
      isLoading,
      errorDetail,
      contextKnown,
      isCavadaLabsProductContext,
    }),
    [companies, projects, isLoading, errorDetail, contextKnown, isCavadaLabsProductContext],
  );
};
