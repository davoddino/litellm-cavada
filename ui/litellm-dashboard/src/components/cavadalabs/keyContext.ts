import { useEffect, useMemo, useState } from "react";
import { listCavadaLabsResource } from "./api";
import type { KeyResponse } from "../key_team_helpers/key_list";

export interface CavadaLabsCompanyOption {
  company_id: string;
  legal_name?: string;
  status?: string;
}

export interface CavadaLabsProjectOption {
  project_id: string;
  company_id: string;
  name?: string;
  status?: string;
  allowed_models?: string[];
}

export interface CavadaLabsKeyContextOptions {
  companies: CavadaLabsCompanyOption[];
  projects: CavadaLabsProjectOption[];
  isLoading: boolean;
}

export const getKeyCavadaLabsCompanyId = (key: Partial<KeyResponse>): string | null => {
  const metadata = key.metadata ?? {};
  const cavadalabs = metadata.cavadalabs;
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
  return null;
};

export const getKeyCavadaLabsProjectId = (key: Partial<KeyResponse>): string | null => {
  const metadata = key.metadata ?? {};
  const cavadalabs = metadata.cavadalabs;
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
  return null;
};

export const useCavadaLabsKeyContextOptions = (
  accessToken: string | null | undefined,
): CavadaLabsKeyContextOptions => {
  const [companies, setCompanies] = useState<CavadaLabsCompanyOption[]>([]);
  const [projects, setProjects] = useState<CavadaLabsProjectOption[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    let isMounted = true;
    if (!accessToken) {
      setCompanies([]);
      setProjects([]);
      return;
    }

    setIsLoading(true);
    Promise.all([
      listCavadaLabsResource<{ companies?: CavadaLabsCompanyOption[] }>(accessToken, "/cavadalabs/companies"),
      listCavadaLabsResource<{ projects?: CavadaLabsProjectOption[] }>(accessToken, "/cavadalabs/projects"),
    ])
      .then(([companyResponse, projectResponse]) => {
        if (!isMounted) return;
        setCompanies(companyResponse.companies ?? []);
        setProjects(projectResponse.projects ?? []);
      })
      .catch(() => {
        if (!isMounted) return;
        setCompanies([]);
        setProjects([]);
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [accessToken]);

  return useMemo(
    () => ({ companies, projects, isLoading }),
    [companies, projects, isLoading],
  );
};
