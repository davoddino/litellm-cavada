import React, { useState, useEffect } from "react";
import {
  Button,
  Card,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
  Badge,
  Text,
} from "@tremor/react";
import { Modal, Alert, Tooltip, Skeleton, Switch, Select } from "antd";
import { CheckCircleOutlined } from "@ant-design/icons";
import { getAgentsList, deleteAgentCall, keyListCall } from "./networking";
import AddAgentForm from "./agents/add_agent_form";
import { isAdminRole } from "@/utils/roles";
import AgentInfoView from "./agents/agent_info";
import NotificationsManager from "./molecules/notifications_manager";
import { Agent, AgentKeyInfo } from "./agents/types";
import { Team } from "./key_team_helpers/key_list";
import { formatNumberWithCommas } from "@/utils/dataUtils";
import TableIconActionButton from "./common_components/IconActionButton/TableIconActionButtons/TableIconActionButton";
import { useOrganizations } from "@/app/(dashboard)/hooks/organizations/useOrganizations";
import { useProjects } from "@/app/(dashboard)/hooks/projects/useProjects";
import ProjectDropdown from "./common_components/ProjectDropdown";
import { getCompanyDisplayId, getCompanyDisplayName } from "./common_components/OrganizationDropdown";

interface AgentsPanelProps {
  accessToken: string | null;
  userRole?: string;
  teams?: Team[] | null;
}

interface AgentsResponse {
  agents: Agent[];
}

interface AgentListFilters {
  company_id?: string | null;
  project_id?: string | null;
}

const emptyAgentListFilters: AgentListFilters = {
  company_id: null,
  project_id: null,
};

const AgentsPanel: React.FC<AgentsPanelProps> = ({ accessToken, userRole, teams }) => {
  const { data: companies = [], isLoading: isCompaniesLoading } = useOrganizations();
  const { data: projects = [], isLoading: isProjectsLoading } = useProjects({ includeNonAdmin: true });
  const [agentsList, setAgentsList] = useState<Agent[]>([]);
  const [keyInfoMap, setKeyInfoMap] = useState<Record<string, AgentKeyInfo>>({});
  const [isAddModalVisible, setIsAddModalVisible] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [agentToDelete, setAgentToDelete] = useState<{ id: string; name: string } | null>(null);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [healthCheckEnabled, setHealthCheckEnabled] = useState(false);
  const [agentFilters, setAgentFilters] = useState<AgentListFilters>(emptyAgentListFilters);

  const isAdmin = userRole ? isAdminRole(userRole) : false;

  const fetchAgents = async (
    healthCheck?: boolean,
    filters: AgentListFilters = agentFilters,
  ) => {
    if (!accessToken) {
      return;
    }

    setIsLoading(true);
    try {
      const response: AgentsResponse = await getAgentsList(
        accessToken,
        healthCheck ?? healthCheckEnabled,
        filters,
      );
      setAgentsList(response.agents || []);
    } catch (error) {
      console.error("Error fetching agents:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const fetchKeysForAgents = async () => {
    if (!accessToken) return;
    try {
      const { keys = [] } = await keyListCall(
        accessToken,
        null,
        null,
        null,
        null,
        null,
        1,
        500
      );
      const map: Record<string, AgentKeyInfo> = {};
      for (const key of keys) {
        const agentId = (key as { agent_id?: string }).agent_id;
        if (agentId && !map[agentId]) {
          map[agentId] = {
            has_key: true,
            key_alias: (key as { key_alias?: string }).key_alias,
            token_prefix: (key as { token?: string }).token
              ? `${(key as { token: string }).token.slice(0, 8)}…`
              : undefined,
          };
        }
      }
      setKeyInfoMap(map);
    } catch (error) {
      console.error("Error fetching keys for agents:", error);
    }
  };

  useEffect(() => {
    fetchAgents();
  }, [accessToken]);

  useEffect(() => {
    if (accessToken && agentsList.length > 0) {
      fetchKeysForAgents();
    } else if (agentsList.length === 0) {
      setKeyInfoMap({});
    }
  }, [accessToken, agentsList.length]);

  const handleHealthCheckToggle = (checked: boolean) => {
    setHealthCheckEnabled(checked);
    fetchAgents(checked, agentFilters);
  };

  const handleCompanyFilterChange = (companyId?: string) => {
    const nextFilters = {
      company_id: companyId || null,
      project_id: null,
    };
    setAgentFilters(nextFilters);
    fetchAgents(undefined, nextFilters);
  };

  const handleProjectFilterChange = (projectId?: string) => {
    const nextFilters = {
      ...agentFilters,
      project_id: projectId || null,
    };
    setAgentFilters(nextFilters);
    fetchAgents(undefined, nextFilters);
  };

  const handleClearFilters = () => {
    setAgentFilters(emptyAgentListFilters);
    fetchAgents(undefined, emptyAgentListFilters);
  };

  const handleAddAgent = () => {
    if (selectedAgentId) {
      setSelectedAgentId(null);
    }
    setIsAddModalVisible(true);
  };

  const handleCloseModal = () => {
    setIsAddModalVisible(false);
  };

  const handleSuccess = () => {
    fetchAgents(undefined, agentFilters);
  };

  const handleDeleteClick = (agentId: string, agentName: string) => {
    setAgentToDelete({ id: agentId, name: agentName });
  };

  const handleDeleteConfirm = async () => {
    if (!agentToDelete || !accessToken) return;

    setIsDeleting(true);
    try {
      await deleteAgentCall(accessToken, agentToDelete.id);
      NotificationsManager.success(`Agent "${agentToDelete.name}" deleted successfully`);
      fetchAgents(undefined, agentFilters);
    } catch (error) {
      console.error("Error deleting agent:", error);
      NotificationsManager.fromBackend("Failed to delete agent");
    } finally {
      setIsDeleting(false);
      setAgentToDelete(null);
    }
  };

  const handleDeleteCancel = () => {
    setAgentToDelete(null);
  };

  const sortedAgents = [...agentsList].sort((a, b) => {
    const dateA = a.created_at ? new Date(a.created_at).getTime() : 0;
    const dateB = b.created_at ? new Date(b.created_at).getTime() : 0;
    return dateB - dateA;
  });

  const columnCount = isAdmin ? 9 : 8;

  return (
    <div className="w-full mx-auto flex-auto overflow-y-auto m-8 p-2">
      <div className="flex flex-col gap-2 mb-4">
        <h1 className="text-2xl font-bold">Agents</h1>
        <p className="text-sm text-gray-600">List of A2A-spec agents available for your Company and Project context. Go to AI Hub to make agents public.</p>
        <Alert
          message="Why do agents need keys?"
          description="Keys scope access to an agent and allow it to call MCP tools. Assign a key when creating an agent or from the Virtual Keys page."
          type="info"
          showIcon
          className="mb-3"
        />
        <div className="mt-2 flex items-center gap-4">
          {isAdmin && (
            <Button onClick={handleAddAgent} disabled={!accessToken}>
              + Add New Agent
            </Button>
          )}
          <Tooltip title="When enabled, only agents with reachable URLs are shown">
            <div className="flex items-center gap-2">
              <CheckCircleOutlined className={healthCheckEnabled ? "text-green-500" : "text-gray-400"} />
              <span className="text-sm text-gray-600">Health Check</span>
              <Switch
                size="small"
                checked={healthCheckEnabled}
                onChange={handleHealthCheckToggle}
                loading={isLoading && healthCheckEnabled}
              />
            </div>
          </Tooltip>
        </div>
        <div className="mt-2 flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1">
            <label htmlFor="agent-company-filter" className="text-sm font-medium text-gray-700">
              Company
            </label>
            <Select
              id="agent-company-filter"
              showSearch
              placeholder="All Companies"
              value={agentFilters.company_id || undefined}
              onChange={handleCompanyFilterChange}
              disabled={!accessToken}
              loading={isCompaniesLoading}
              allowClear
              style={{ minWidth: 280 }}
              filterOption={(input, option) => {
                const company = companies.find((item) => getCompanyDisplayId(item) === option?.value);
                if (!company) return false;
                const searchTerm = input.toLowerCase().trim();
                return (
                  getCompanyDisplayName(company).toLowerCase().includes(searchTerm) ||
                  getCompanyDisplayId(company).toLowerCase().includes(searchTerm)
                );
              }}
            >
              {companies.map((company) => {
                const companyId = getCompanyDisplayId(company);
                return (
                  <Select.Option key={companyId} value={companyId}>
                    {getCompanyDisplayName(company)} ({companyId})
                  </Select.Option>
                );
              })}
            </Select>
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="agent-project-filter" className="text-sm font-medium text-gray-700">
              Project
            </label>
            <ProjectDropdown
              id="agent-project-filter"
              projects={projects}
              value={agentFilters.project_id || undefined}
              onChange={handleProjectFilterChange}
              disabled={!accessToken}
              loading={isProjectsLoading}
              companyId={agentFilters.company_id}
            />
          </div>
          {(agentFilters.company_id || agentFilters.project_id) && (
            <Button variant="light" onClick={handleClearFilters}>
              Clear filters
            </Button>
          )}
        </div>
      </div>

      {selectedAgentId ? (
        <AgentInfoView
          agentId={selectedAgentId}
          onClose={() => setSelectedAgentId(null)}
          accessToken={accessToken}
          isAdmin={isAdmin}
        />
      ) : (
        <Card>
          {isLoading ? (
            <Skeleton active paragraph={{ rows: 3 }} />
          ) : (
            <Table>
              <TableHead>
                <TableRow>
                  <TableHeaderCell>Agent Name</TableHeaderCell>
                  <TableHeaderCell>Agent ID</TableHeaderCell>
                  <TableHeaderCell>Company</TableHeaderCell>
                  <TableHeaderCell>Project</TableHeaderCell>
                  <TableHeaderCell>Spend (USD)</TableHeaderCell>
                  <TableHeaderCell>Model</TableHeaderCell>
                  <TableHeaderCell>Created</TableHeaderCell>
                  <TableHeaderCell>Status</TableHeaderCell>
                  {isAdmin && <TableHeaderCell>Actions</TableHeaderCell>}
                </TableRow>
              </TableHead>
              <TableBody>
                {sortedAgents.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={columnCount}>
                      <Text className="text-center">No agents found. Click &quot;+ Add New Agent&quot; to create one.</Text>
                    </TableCell>
                  </TableRow>
                ) : (
                  sortedAgents.map((agent) => (
                    <TableRow key={agent.agent_id}>
                      <TableCell>
                        <Text>{agent.agent_name}</Text>
                      </TableCell>
                      <TableCell>
                        <Tooltip title={agent.agent_id}>
                          <Button
                            size="xs"
                            variant="light"
                            className="font-mono text-blue-500 bg-blue-50 hover:bg-blue-100 text-xs font-normal px-2 py-0.5 text-left overflow-hidden truncate max-w-[200px]"
                            onClick={() => setSelectedAgentId(agent.agent_id)}
                          >
                            {agent.agent_id.slice(0, 7)}...
                          </Button>
                        </Tooltip>
                      </TableCell>
                      <TableCell>
                        <Text>{agent.company_name || agent.company_id || "N/A"}</Text>
                      </TableCell>
                      <TableCell>
                        <Text>{agent.project_name || agent.project_id || "N/A"}</Text>
                      </TableCell>
                      <TableCell>
                        <Text>{formatNumberWithCommas(agent.spend, 4)}</Text>
                      </TableCell>
                      <TableCell>
                        <Badge size="xs" color="blue">
                          {agent.litellm_params?.model || "N/A"}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Text>
                          {agent.created_at
                            ? new Date(agent.created_at).toLocaleDateString()
                            : "N/A"}
                        </Text>
                      </TableCell>
                      <TableCell>
                        {keyInfoMap[agent.agent_id]?.has_key ? (
                          <Badge color="green">Active</Badge>
                        ) : (
                          <Badge color="yellow">Needs Setup</Badge>
                        )}
                      </TableCell>
                      {isAdmin && (
                        <TableCell>
                          <TableIconActionButton
                            variant="Delete"
                            onClick={() => handleDeleteClick(agent.agent_id, agent.agent_name)}
                          />
                        </TableCell>
                      )}
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          )}
        </Card>
      )}

      <AddAgentForm
        visible={isAddModalVisible}
        onClose={handleCloseModal}
        accessToken={accessToken}
        onSuccess={handleSuccess}
        teams={teams}
      />

      {agentToDelete && (
        <Modal
          title="Delete Agent"
          open={agentToDelete !== null}
          onOk={handleDeleteConfirm}
          onCancel={handleDeleteCancel}
          confirmLoading={isDeleting}
          okText="Delete"
          okButtonProps={{ danger: true }}
        >
          <p>Are you sure you want to delete agent: {agentToDelete.name}?</p>
          <p>This action cannot be undone.</p>
        </Modal>
      )}
    </div>
  );
};

export default AgentsPanel;
