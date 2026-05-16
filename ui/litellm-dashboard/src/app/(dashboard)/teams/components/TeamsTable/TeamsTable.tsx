import { Button, Icon, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow, Text } from "@tremor/react";
import { Tooltip } from "antd";
import { formatNumberWithCommas } from "@/utils/dataUtils";
import { PencilAltIcon, TrashIcon } from "@heroicons/react/outline";
import React from "react";
import { type KeyResponse, Team } from "@/components/key_team_helpers/key_list";
import { Member, Organization } from "@/components/networking";
import ModelsCell from "@/app/(dashboard)/teams/components/TeamsTable/ModelsCell";
import YourRoleCell from "@/app/(dashboard)/teams/components/TeamsTable/YourRoleCell/YourRoleCell";
import {
  CavadaLabsCompanyOption,
  CavadaLabsProjectOption,
  findCavadaLabsProjectForCompatibilityTeam,
  getCavadaLabsCompanyDisplayName,
  getCavadaLabsCompanyLabelForCompatibilityOrganization,
} from "@/components/cavadalabs/keyContext";

type TeamsTableProps = {
  teams: Team[] | null;
  currentOrg: Organization | null;
  cavadalabsCompanies: CavadaLabsCompanyOption[];
  cavadalabsProjects: CavadaLabsProjectOption[];
  isCavadaLabsProductContext?: boolean;
  perTeamInfo: Record<string, PerTeamInfo>;
  userRole: string | null;
  userId: string | null;
  setSelectedTeamId: (teamId: string) => void;
  setEditTeam: (editTeam: boolean) => void;
  onDeleteTeam: (teamId: string) => void;
  onOpenCavadaProject?: (projectId: string) => void;
};

interface TeamInfo {
  members_with_roles: Member[];
}

interface PerTeamInfo {
  keys: KeyResponse[];
  team_info: TeamInfo;
}

const TeamsTable = ({
  teams,
  currentOrg,
  cavadalabsCompanies,
  cavadalabsProjects,
  isCavadaLabsProductContext = false,
  setSelectedTeamId,
  perTeamInfo,
  userRole,
  userId,
  setEditTeam,
  onDeleteTeam,
  onOpenCavadaProject,
}: TeamsTableProps) => {
  return (
    <Table>
      <TableHead>
        <TableRow>
          <TableHeaderCell>{isCavadaLabsProductContext ? "Project Name" : "Team Name"}</TableHeaderCell>
          <TableHeaderCell>{isCavadaLabsProductContext ? "Project ID" : "Team ID"}</TableHeaderCell>
          <TableHeaderCell>Created</TableHeaderCell>
          <TableHeaderCell>Spend (USD)</TableHeaderCell>
          <TableHeaderCell>Budget (USD)</TableHeaderCell>
          <TableHeaderCell>Models</TableHeaderCell>
          <TableHeaderCell>Company</TableHeaderCell>
          <TableHeaderCell>Your Role</TableHeaderCell>
          <TableHeaderCell>Info</TableHeaderCell>
        </TableRow>
      </TableHead>

      <TableBody>
        {teams && teams.length > 0
          ? teams
              .filter((team) => {
                if (!currentOrg) return true;
                return team.organization_id === currentOrg.organization_id;
              })
              .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
              .map((team: any) => {
                const cavadalabsProject = isCavadaLabsProductContext
                  ? cavadalabsProjects.find((project) => project.project_id === team.cavadalabs_project_id) ??
                    findCavadaLabsProjectForCompatibilityTeam(cavadalabsProjects, team.team_id)
                  : null;
                const cavadalabsProjectId = cavadalabsProject?.project_id ?? team.cavadalabs_project_id ?? null;
                const projectName =
                  cavadalabsProject?.name?.trim() || team.cavadalabs_project_name || cavadalabsProjectId;
                const cavadalabsCompany =
                  isCavadaLabsProductContext && team.cavadalabs_company_id
                    ? cavadalabsCompanies.find((company) => company.company_id === team.cavadalabs_company_id)
                    : null;
                const companyLabel = cavadalabsCompany
                  ? getCavadaLabsCompanyDisplayName(cavadalabsCompany)
                  : team.cavadalabs_company_id ||
                    getCavadaLabsCompanyLabelForCompatibilityOrganization(cavadalabsCompanies, team.organization_id);
                const openProjectDetails = () => {
                  if (isCavadaLabsProductContext) {
                    if (cavadalabsProjectId) {
                      onOpenCavadaProject?.(cavadalabsProjectId);
                    }
                    return;
                  }
                  setSelectedTeamId(team.team_id);
                };

                return (
                  <TableRow key={team.team_id}>
                    <TableCell
                      style={{
                        maxWidth: "4px",
                        whiteSpace: "pre-wrap",
                        overflow: "hidden",
                      }}
                    >
                      {isCavadaLabsProductContext ? projectName || "Missing Project mapping" : team["team_alias"]}
                    </TableCell>
                    <TableCell>
                      <div className="overflow-hidden">
                        {isCavadaLabsProductContext && !cavadalabsProjectId ? (
                          <Text>Missing Project mapping</Text>
                        ) : (
                          <Tooltip title={isCavadaLabsProductContext ? cavadalabsProjectId : team.team_id}>
                            <Button
                              size="xs"
                              variant="light"
                              className="font-mono text-blue-500 bg-blue-50 hover:bg-blue-100 text-xs font-normal px-2 py-0.5 text-left overflow-hidden truncate max-w-[200px]"
                              data-testid={isCavadaLabsProductContext ? "project-id-cell" : "team-id-cell"}
                              onClick={openProjectDetails}
                            >
                              {isCavadaLabsProductContext
                                ? `${cavadalabsProjectId?.slice(0, 7)}...`
                                : `${team.team_id.slice(0, 7)}...`}
                            </Button>
                          </Tooltip>
                        )}
                      </div>
                    </TableCell>
                    <TableCell
                      style={{
                        maxWidth: "4px",
                        whiteSpace: "pre-wrap",
                        overflow: "hidden",
                      }}
                    >
                      {team.created_at ? new Date(team.created_at).toLocaleDateString() : "N/A"}
                    </TableCell>
                    <TableCell
                      style={{
                        maxWidth: "4px",
                        whiteSpace: "pre-wrap",
                        overflow: "hidden",
                      }}
                    >
                      {formatNumberWithCommas(team["spend"], 4)}
                    </TableCell>
                    <TableCell
                      style={{
                        maxWidth: "4px",
                        whiteSpace: "pre-wrap",
                        overflow: "hidden",
                      }}
                    >
                      {team["max_budget"] !== null && team["max_budget"] !== undefined
                        ? team["max_budget"]
                        : "No limit"}
                    </TableCell>
                    <ModelsCell team={team} />
                    <TableCell>{companyLabel}</TableCell>
                    <YourRoleCell team={team} userId={userId} />
                    <TableCell>
                      <Text>
                        {perTeamInfo &&
                          team.team_id &&
                          perTeamInfo[team.team_id] &&
                          perTeamInfo[team.team_id].keys &&
                          perTeamInfo[team.team_id].keys.length}{" "}
                        Keys
                      </Text>
                      <Text>
                        {perTeamInfo &&
                          team.team_id &&
                          perTeamInfo[team.team_id] &&
                          perTeamInfo[team.team_id].team_info &&
                          perTeamInfo[team.team_id].team_info.members_with_roles &&
                          perTeamInfo[team.team_id].team_info.members_with_roles.length}{" "}
                        Members
                      </Text>
                    </TableCell>
                    <TableCell>
                      {userRole == "Admin" ? (
                        isCavadaLabsProductContext ? (
                          cavadalabsProjectId ? (
                            <Icon
                              aria-label="Open project"
                              data-testid="open-project-action"
                              icon={PencilAltIcon}
                              size="sm"
                              onClick={openProjectDetails}
                            />
                          ) : null
                        ) : (
                          <>
                            <Icon
                              aria-label="Edit team"
                              icon={PencilAltIcon}
                              size="sm"
                              onClick={() => {
                                setSelectedTeamId(team.team_id);
                                setEditTeam(true);
                              }}
                            />
                            <Icon
                              aria-label="Delete team"
                              onClick={() => onDeleteTeam(team.team_id)}
                              icon={TrashIcon}
                              size="sm"
                            />
                          </>
                        )
                      ) : null}
                    </TableCell>
                  </TableRow>
                );
              })
          : null}
      </TableBody>
    </Table>
  );
};

export default TeamsTable;
