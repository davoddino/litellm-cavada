import { Select } from "antd";
import React from "react";
import type { CavadaLabsCompanyOption, CavadaLabsProjectOption } from "@/components/cavadalabs/keyContext";

interface TeamsFiltersProps {
  filters: FilterState;
  companies: CavadaLabsCompanyOption[];
  projects: CavadaLabsProjectOption[];
  isCavadaLabsProductContext?: boolean;
  showFilters: boolean;
  onToggleFilters: (toggle: boolean) => void;
  onChange: (update: Partial<FilterState>) => void;
  onReset: () => void;
}

type FilterState = {
  team_id: string;
  team_alias: string;
  cavadalabs_company_id: string;
  cavadalabs_project_id: string;
  sort_by: string;
  sort_order: "asc" | "desc";
};

const TeamsFilters = ({
  filters,
  companies,
  projects,
  isCavadaLabsProductContext = false,
  showFilters,
  onToggleFilters,
  onChange,
  onReset,
}: TeamsFiltersProps) => {
  const filteredProjects = filters.cavadalabs_company_id
    ? projects.filter((project) => project.company_id === filters.cavadalabs_company_id)
    : projects;
  const hasActiveFilters = isCavadaLabsProductContext
    ? Boolean(filters.team_alias || filters.cavadalabs_company_id || filters.cavadalabs_project_id)
    : Boolean(filters.team_id || filters.team_alias);

  return (
    <div className="flex flex-col space-y-4">
      {/* Search and Filter Controls */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Team Alias Search */}
        <div className="relative w-64">
          <input
            type="text"
            placeholder={isCavadaLabsProductContext ? "Search by Project Name..." : "Search by Team Name..."}
            className="w-full px-3 py-2 pl-8 border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            value={filters.team_alias}
            onChange={(e) => onChange({ team_alias: e.target.value })}
          />
          <svg
            className="absolute left-2.5 top-2.5 h-4 w-4 text-gray-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
        </div>

        {/* Filter Button */}
        <button
          className={`px-3 py-2 text-sm border rounded-md hover:bg-gray-50 flex items-center gap-2 ${showFilters ? "bg-gray-100" : ""}`}
          onClick={() => onToggleFilters(!showFilters)}
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z"
            />
          </svg>
          Filters
          {hasActiveFilters && (
            <span data-testid="active-filter-indicator" className="w-2 h-2 rounded-full bg-blue-500"></span>
          )}
        </button>

        {/* Reset Filters Button */}
        <button
          className="px-3 py-2 text-sm border rounded-md hover:bg-gray-50 flex items-center gap-2"
          onClick={onReset}
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
          Reset Filters
        </button>
      </div>

      {/* Additional Filters */}
      {showFilters && (
        <div className="flex flex-wrap items-center gap-3 mt-3">
          {!isCavadaLabsProductContext && (
            <div className="relative w-64">
              <input
                type="text"
                placeholder="Enter Team ID"
                className="w-full px-3 py-2 pl-8 border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                value={filters.team_id}
                onChange={(e) => onChange({ team_id: e.target.value })}
              />
              <svg
                className="absolute left-2.5 top-2.5 h-4 w-4 text-gray-500"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M5.121 17.804A13.937 13.937 0 0112 16c2.5 0 4.847.655 6.879 1.804M15 10a3 3 0 11-6 0 3 3 0 016 0zm6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
            </div>
          )}

          {isCavadaLabsProductContext && (
            <>
              <div className="w-64">
                <label className="block text-xs font-medium text-gray-600 mb-1">Company</label>
                <Select
                  aria-label="Company"
                  allowClear
                  showSearch
                  value={filters.cavadalabs_company_id || undefined}
                  onChange={(value) => {
                    const nextCompanyId = value || "";
                    const selectedProject = projects.find(
                      (project) => project.project_id === filters.cavadalabs_project_id,
                    );
                    onChange({
                      cavadalabs_company_id: nextCompanyId,
                      cavadalabs_project_id:
                        selectedProject && selectedProject.company_id !== nextCompanyId
                          ? ""
                          : filters.cavadalabs_project_id,
                    });
                  }}
                  placeholder="Select Company"
                  optionFilterProp="label"
                  style={{ width: "100%" }}
                  options={companies.map((company) => ({
                    label: `${company.legal_name || company.company_id} (${company.company_id})`,
                    value: company.company_id,
                  }))}
                />
              </div>

              <div className="w-64">
                <label className="block text-xs font-medium text-gray-600 mb-1">Project</label>
                <Select
                  aria-label="Project"
                  allowClear
                  showSearch
                  value={filters.cavadalabs_project_id || undefined}
                  onChange={(value) => {
                    const projectId = value || "";
                    const selectedProject = projects.find((project) => project.project_id === projectId);
                    onChange({
                      cavadalabs_project_id: projectId,
                      cavadalabs_company_id: selectedProject?.company_id || filters.cavadalabs_company_id,
                    });
                  }}
                  placeholder="Select Project"
                  optionFilterProp="label"
                  style={{ width: "100%" }}
                  options={filteredProjects.map((project) => ({
                    label: `${project.name || project.project_id} (${project.project_id})`,
                    value: project.project_id,
                  }))}
                />
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
};

export default TeamsFilters;
