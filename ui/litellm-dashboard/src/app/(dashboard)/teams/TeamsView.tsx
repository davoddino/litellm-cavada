import React, { useState, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { organizationKeys } from "@/app/(dashboard)/hooks/organizations/useOrganizations";
import { teamDeleteCall, Organization, serverRootPath } from "@/components/networking";
import { fetchTeams } from "@/components/common_components/fetch_teams";
import { Form } from "antd";
import TeamInfoView from "@/components/team/TeamInfo";
import TeamSSOSettings from "@/components/TeamSSOSettings";
import { isAdminRole } from "@/utils/roles";
import { Card, Button, Col, Text, Grid, TabPanel } from "@tremor/react";
import AvailableTeamsPanel from "@/components/team/available_teams";
import type { KeyResponse, Team } from "@/components/key_team_helpers/key_list";

import { Member, v2TeamListCall } from "@/components/networking";
import { updateExistingKeys } from "@/utils/dataUtils";
import TeamsHeaderTabs from "@/app/(dashboard)/teams/components/TeamsHeaderTabs";
import TeamsFilters from "@/app/(dashboard)/teams/components/TeamsFilters";
import useFetchTeams from "@/app/(dashboard)/teams/hooks/useFetchTeams";
import TeamsTable from "@/app/(dashboard)/teams/components/TeamsTable/TeamsTable";
import DeleteTeamModal from "@/app/(dashboard)/teams/components/modals/DeleteTeamModal";
import CreateTeamModal from "@/app/(dashboard)/teams/components/modals/CreateTeamModal";
import {
  buildTeamsListScopeParams,
  normalizeTeamsFilterUpdate,
} from "@/app/(dashboard)/teams/components/teamFilterScope";
import { useCavadaLabsKeyContextOptions } from "@/components/cavadalabs/keyContext";
import { resolveCavadaLabsProductContext } from "@/components/cavadalabs/productContext";
import { buildUiPath } from "@/utils/uiRoutes";

interface TeamProps {
  teams: Team[] | null;
  accessToken: string | null;
  setTeams: React.Dispatch<React.SetStateAction<Team[] | null>>;
  userID: string | null;
  userRole: string | null;
  organizations: Organization[] | null;
  premiumUser?: boolean;
}

interface FilterState {
  team_id: string;
  team_alias: string;
  cavadalabs_company_id: string;
  cavadalabs_project_id: string;
  sort_by: string;
  sort_order: "asc" | "desc";
}

interface TeamInfo {
  members_with_roles: Member[];
}

interface PerTeamInfo {
  keys: KeyResponse[];
  team_info: TeamInfo;
}

const TeamsView: React.FC<TeamProps> = ({
  teams,
  accessToken,
  setTeams,
  userID,
  userRole,
  organizations,
  premiumUser = false,
}) => {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [currentOrg, setCurrentOrg] = useState<Organization | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [filters, setFilters] = useState<FilterState>({
    team_id: "",
    team_alias: "",
    cavadalabs_company_id: "",
    cavadalabs_project_id: "",
    sort_by: "created_at",
    sort_order: "desc",
  });
  const cavadalabsContext = useCavadaLabsKeyContextOptions(accessToken);
  const { companies: cavadalabsCompanies, projects: cavadalabsProjects } = cavadalabsContext;

  const [form] = Form.useForm();
  const [memberForm] = Form.useForm();

  const [selectedTeamId, setSelectedTeamId] = useState<string | null>(null);
  const [editTeam, setEditTeam] = useState<boolean>(false);

  const [isTeamModalVisible, setIsTeamModalVisible] = useState(false);
  const [isAddMemberModalVisible, setIsAddMemberModalVisible] = useState(false);
  const [isEditMemberModalVisible, setIsEditMemberModalVisible] = useState(false);
  const [userModels, setUserModels] = useState<string[]>([]);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [teamToDelete, setTeamToDelete] = useState<string | null>(null);
  const [perTeamInfo, setPerTeamInfo] = useState<Record<string, PerTeamInfo>>({});

  const [loggingSettings, setLoggingSettings] = useState<any[]>([]);
  const [modelAliases, setModelAliases] = useState<{ [key: string]: string }>({});
  const cavadalabsProductContext = resolveCavadaLabsProductContext(cavadalabsContext);
  const isCavadaLabsProductContext =
    cavadalabsProductContext.isCavadaLabsProductContext ||
    (Boolean(accessToken) && !cavadalabsProductContext.showLiteLLMCompatibilityFields);
  const { lastRefreshed, onRefreshClick: handleRefreshClick } = useFetchTeams({
    currentOrg,
    setTeams,
    isCavadaLabsProductContext,
  });
  const canManageCavadaLabsProjects =
    isCavadaLabsProductContext &&
    (cavadalabsCompanies.some((company) => company.cavadalabs_can_manage === true) ||
      cavadalabsProjects.some((project) => project.cavadalabs_can_manage === true));
  const canCreateOrManageTeams = isCavadaLabsProductContext
    ? userRole == "Admin" || canManageCavadaLabsProjects
    : userRole == "Admin" || userRole == "Org Admin";
  const openCavadaProject = (projectId: string) => {
    router.push(buildUiPath(`cavadalabs/projects?project_id=${encodeURIComponent(projectId)}`, serverRootPath));
  };

  useEffect(() => {
    const fetchTeamInfo = () => {
      if (!teams) return;

      const newPerTeamInfo = teams.reduce(
        (acc, team) => {
          acc[team.team_id] = {
            keys: team.keys || [],
            team_info: {
              members_with_roles: team.members_with_roles || [],
            },
          };
          return acc;
        },
        {} as Record<string, PerTeamInfo>,
      );

      setPerTeamInfo(newPerTeamInfo);
    };

    fetchTeamInfo();
  }, [teams]);

  const handleOk = () => {
    setIsTeamModalVisible(false);
    form.resetFields();
    setLoggingSettings([]);
    setModelAliases({});
  };

  const handleMemberOk = () => {
    setIsAddMemberModalVisible(false);
    setIsEditMemberModalVisible(false);
    memberForm.resetFields();
  };

  const handleCancel = () => {
    setIsTeamModalVisible(false);
    form.resetFields();
    setLoggingSettings([]);
    setModelAliases({});
  };

  const handleDelete = async (team_id: string) => {
    // Set the team to delete and open the confirmation modal
    setTeamToDelete(team_id);
    setIsDeleteModalOpen(true);
  };

  const confirmDelete = async () => {
    if (teamToDelete == null || teams == null || accessToken == null) {
      return;
    }

    try {
      await teamDeleteCall(accessToken, teamToDelete);
      queryClient.invalidateQueries({ queryKey: organizationKeys.all });
      // Successfully completed the deletion. Update the state to trigger a rerender.
      fetchTeams(accessToken, userID, userRole, currentOrg, setTeams);
    } catch (error) {
      console.error("Error deleting the team:", error);
      // Handle any error situations, such as displaying an error message to the user.
    }

    // Close the confirmation modal and reset the teamToDelete
    setIsDeleteModalOpen(false);
    setTeamToDelete(null);
  };

  const cancelDelete = () => {
    // Close the confirmation modal and reset the teamToDelete
    setIsDeleteModalOpen(false);
    setTeamToDelete(null);
  };

  const is_team_admin = (team: any) => {
    if (team == null || team.members_with_roles == null) {
      return false;
    }
    for (let i = 0; i < team.members_with_roles.length; i++) {
      let member = team.members_with_roles[i];
      if (member.user_id == userID && member.role == "admin") {
        return true;
      }
    }
    return false;
  };

  const handleFilterChange = (update: Partial<FilterState>) => {
    const newFilters = normalizeTeamsFilterUpdate(filters, update, isCavadaLabsProductContext);
    const scopeParams = buildTeamsListScopeParams(newFilters, isCavadaLabsProductContext);
    setFilters(newFilters);
    // Call teamListCall with the new filters
    if (accessToken) {
      v2TeamListCall(
        accessToken,
        null,
        null,
        scopeParams.teamId,
        scopeParams.teamAlias,
        1,
        10,
        newFilters.sort_by || null,
        newFilters.sort_order || null,
        scopeParams.cavadalabsCompanyId,
        scopeParams.cavadalabsProjectId,
      )
        .then((response) => {
          if (response && response.teams) {
            setTeams(response.teams);
          }
        })
        .catch((error) => {
          console.error("Error fetching teams:", error);
        });
    }
  };

  const handleSortChange = (sortBy: string, sortOrder: "asc" | "desc") => {
    const newFilters = normalizeTeamsFilterUpdate(
      filters,
      { sort_by: sortBy, sort_order: sortOrder },
      isCavadaLabsProductContext,
    );
    const scopeParams = buildTeamsListScopeParams(newFilters, isCavadaLabsProductContext);
    setFilters(newFilters);
    // Call teamListCall with the new sort parameters
    if (accessToken) {
      v2TeamListCall(
        accessToken,
        null,
        null,
        scopeParams.teamId,
        scopeParams.teamAlias,
        1,
        10,
        newFilters.sort_by || null,
        newFilters.sort_order || null,
        scopeParams.cavadalabsCompanyId,
        scopeParams.cavadalabsProjectId,
      )
        .then((response) => {
          if (response && response.teams) {
            setTeams(response.teams);
          }
        })
        .catch((error) => {
          console.error("Error fetching teams:", error);
        });
    }
  };

  const handleFilterReset = () => {
    const resetFilters = {
      team_id: "",
      team_alias: "",
      cavadalabs_company_id: "",
      cavadalabs_project_id: "",
      sort_by: "created_at",
      sort_order: "desc",
    } satisfies FilterState;
    const scopeParams = buildTeamsListScopeParams(resetFilters, isCavadaLabsProductContext);
    setFilters(resetFilters);
    // Reset teams list
    if (accessToken) {
      v2TeamListCall(
        accessToken,
        null,
        isCavadaLabsProductContext ? null : userID || null,
        scopeParams.teamId,
        scopeParams.teamAlias,
        1,
        10,
        resetFilters.sort_by,
        resetFilters.sort_order,
        scopeParams.cavadalabsCompanyId,
        scopeParams.cavadalabsProjectId,
      )
        .then((response) => {
          if (response && response.teams) {
            setTeams(response.teams);
          }
        })
        .catch((error) => {
          console.error("Error fetching teams:", error);
        });
    }
  };

  return (
    <div className="w-full mx-4 h-[75vh]">
      <Grid numItems={1} className="gap-2 p-8 w-full mt-2">
        <Col numColSpan={1} className="flex flex-col gap-2">
          {canCreateOrManageTeams && (
            <Button
              className="w-fit"
              onClick={() => {
                if (isCavadaLabsProductContext) {
                  router.push(buildUiPath("cavadalabs/projects", serverRootPath));
                  return;
                }
                setIsTeamModalVisible(true);
              }}
            >
              {isCavadaLabsProductContext ? "+ Create New Project" : "+ Create New Team"}
            </Button>
          )}
          {selectedTeamId && !isCavadaLabsProductContext ? (
            <TeamInfoView
              teamId={selectedTeamId}
              onUpdate={(data) => {
                setTeams((teams) => {
                  if (teams == null) {
                    return teams;
                  }
                  const updated = teams.map((team) => {
                    if (data.team_id === team.team_id) {
                      return updateExistingKeys(team, data);
                    }
                    return team;
                  });
                  if (accessToken) {
                    fetchTeams(accessToken, userID, userRole, currentOrg, setTeams);
                  }
                  return updated;
                });
              }}
              onClose={() => {
                setSelectedTeamId(null);
                setEditTeam(false);
              }}
              accessToken={accessToken}
              is_team_admin={is_team_admin(teams?.find((team) => team.team_id === selectedTeamId))}
              is_proxy_admin={userRole == "Admin"}
              is_org_admin={(() => {
                const team = teams?.find((t) => t.team_id === selectedTeamId);
                if (!team?.organization_id || !organizations || !userID) return false;
                const org = organizations.find((o) => o.organization_id === team.organization_id);
                return org?.members?.some((m: any) => m.user_id === userID && m.user_role === "org_admin") ?? false;
              })()}
              userModels={userModels}
              editTeam={editTeam}
              premiumUser={premiumUser}
            />
          ) : (
            <TeamsHeaderTabs
              lastRefreshed={lastRefreshed}
              onRefresh={handleRefreshClick}
              userRole={userRole}
              isCavadaLabsProductContext={isCavadaLabsProductContext}
            >
              <TabPanel>
                <Text>
                  {isCavadaLabsProductContext
                    ? "Project runtime and membership"
                    : 'Click on "Team ID" to view team details and manage team members.'}
                </Text>
                <Grid numItems={1} className="gap-2 pt-2 pb-2 h-[75vh] w-full mt-2">
                  <Col numColSpan={1}>
                    <Card className="w-full mx-auto flex-auto overflow-hidden overflow-y-auto max-h-[50vh]">
                      <div className="border-b px-6 py-4">
                        <div className="flex flex-col space-y-4">
                          <TeamsFilters
                            filters={filters}
                            companies={cavadalabsCompanies}
                            projects={cavadalabsProjects}
                            isCavadaLabsProductContext={isCavadaLabsProductContext}
                            showFilters={showFilters}
                            onToggleFilters={setShowFilters}
                            onChange={handleFilterChange}
                            onReset={handleFilterReset}
                          />
                        </div>
                      </div>
                      <TeamsTable
                        teams={teams}
                        currentOrg={currentOrg}
                        cavadalabsCompanies={cavadalabsCompanies}
                        cavadalabsProjects={cavadalabsProjects}
                        isCavadaLabsProductContext={isCavadaLabsProductContext}
                        perTeamInfo={perTeamInfo}
                        userRole={userRole}
                        userId={userID}
                        setSelectedTeamId={setSelectedTeamId}
                        setEditTeam={setEditTeam}
                        onDeleteTeam={handleDelete}
                        onOpenCavadaProject={openCavadaProject}
                      />
                      {isDeleteModalOpen && (
                        <DeleteTeamModal
                          teams={teams}
                          teamToDelete={teamToDelete}
                          onCancel={cancelDelete}
                          onConfirm={confirmDelete}
                        />
                      )}
                    </Card>
                  </Col>
                </Grid>
              </TabPanel>
              {!isCavadaLabsProductContext && (
                <TabPanel>
                  <AvailableTeamsPanel accessToken={accessToken} userID={userID} />
                </TabPanel>
              )}
              {isAdminRole(userRole || "") && !isCavadaLabsProductContext && (
                <TabPanel>
                  <TeamSSOSettings accessToken={accessToken} userID={userID || ""} userRole={userRole || ""} />
                </TabPanel>
              )}
            </TeamsHeaderTabs>
          )}
          {canCreateOrManageTeams && !isCavadaLabsProductContext && (
            <CreateTeamModal
              isTeamModalVisible={isTeamModalVisible}
              handleOk={handleOk}
              handleCancel={handleCancel}
              currentOrg={currentOrg}
              organizations={organizations}
              cavadalabsCompanies={cavadalabsCompanies}
              isCavadaLabsProductContext={isCavadaLabsProductContext}
              teams={teams}
              setTeams={setTeams}
              modelAliases={modelAliases}
              setModelAliases={setModelAliases}
              loggingSettings={loggingSettings}
              setLoggingSettings={setLoggingSettings}
              setIsTeamModalVisible={setIsTeamModalVisible}
            />
          )}
        </Col>
      </Grid>
    </div>
  );
};

export default TeamsView;
