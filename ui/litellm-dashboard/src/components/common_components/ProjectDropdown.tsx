import React from "react";
import { Select, Spin } from "antd";
import { LoadingOutlined } from "@ant-design/icons";
import { ProjectResponse } from "@/app/(dashboard)/hooks/projects/useProjects";

interface ProjectDropdownProps {
  projects?: ProjectResponse[] | null;
  value?: string;
  onChange?: (value?: string) => void;
  id?: string;
  disabled?: boolean;
  loading?: boolean;
  /** When set, only show projects belonging to this team */
  teamId?: string | null;
  /** When set, show projects belonging to this company unless teamId is set */
  companyId?: string | null;
}

export const filterProjectsByCompanyIds = (
  projects?: ProjectResponse[] | null,
  companyIds?: string[] | null,
): ProjectResponse[] => {
  const selectedCompanyIds = Array.isArray(companyIds) ? companyIds.filter(Boolean) : [];
  if (selectedCompanyIds.length === 0) {
    return projects || [];
  }

  const selectedCompanyIdSet = new Set(selectedCompanyIds);
  return (projects || []).filter((project) => project.company_id && selectedCompanyIdSet.has(project.company_id));
};

export const pruneProjectIdsForCompanySelection = ({
  projects,
  selectedCompanyIds,
  selectedProjectIds,
  isLoading,
}: {
  projects?: ProjectResponse[] | null;
  selectedCompanyIds?: string[] | null;
  selectedProjectIds?: string[] | null;
  isLoading?: boolean;
}): string[] | null => {
  if (
    isLoading ||
    !Array.isArray(selectedCompanyIds) ||
    selectedCompanyIds.length === 0 ||
    !Array.isArray(selectedProjectIds) ||
    selectedProjectIds.length === 0
  ) {
    return null;
  }

  const availableProjectIds = new Set(
    filterProjectsByCompanyIds(projects, selectedCompanyIds).map((project) => project.project_id),
  );
  const nextProjectIds = selectedProjectIds.filter((projectId) => availableProjectIds.has(projectId));
  return nextProjectIds.length === selectedProjectIds.length ? null : nextProjectIds;
};

const ProjectDropdown: React.FC<ProjectDropdownProps> = ({
  projects,
  value,
  onChange,
  id,
  disabled,
  loading,
  teamId,
  companyId,
}) => {
  const filtered = teamId
    ? projects?.filter((p) => p.team_id === teamId)
    : companyId
      ? filterProjectsByCompanyIds(projects, [companyId])
      : projects;

  return (
    <Select
      id={id}
      showSearch
      placeholder="Search or select a project"
      value={value}
      onChange={onChange}
      disabled={disabled}
      loading={loading}
      allowClear
      notFoundContent={loading ? <Spin indicator={<LoadingOutlined spin />} size="small" /> : undefined}
      filterOption={(input, option) => {
        if (!option) return false;
        const project = filtered?.find((p) => p.project_id === option.key);
        if (!project) return false;

        const searchTerm = input.toLowerCase().trim();
        const alias = (project.project_alias || "").toLowerCase();
        const id = (project.project_id || "").toLowerCase();

        return alias.includes(searchTerm) || id.includes(searchTerm);
      }}
      optionFilterProp="children"
    >
      {!loading &&
        filtered?.map((project) => (
          <Select.Option key={project.project_id} value={project.project_id}>
            <span className="font-medium">{project.project_alias || project.project_id}</span>{" "}
            <span className="text-gray-500">({project.project_id})</span>
          </Select.Option>
        ))}
    </Select>
  );
};

export default ProjectDropdown;
