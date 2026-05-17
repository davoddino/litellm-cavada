import { InfoCircleOutlined, UserAddOutlined } from "@ant-design/icons";
import { useQueryClient } from "@tanstack/react-query";
import { useOrganizations } from "@/app/(dashboard)/hooks/organizations/useOrganizations";
import { Accordion, AccordionBody, AccordionHeader, SelectItem, TextInput } from "@tremor/react";
import {
  Alert,
  Button,
  Checkbox,
  Form,
  Input,
  Modal,
  Select,
  Select as Select2,
  Space,
  Tooltip,
  Typography,
} from "antd";
import React, { useEffect, useMemo, useState } from "react";
import BulkCreateUsers from "./bulk_create_users_button";
import {
  getCavadaLabsCompanyDisplayName,
  getCavadaLabsProjectDisplayName,
  filterManageableCavadaLabsCompanies,
  filterManageableCavadaLabsProjects,
  useCavadaLabsKeyContextOptions,
} from "./cavadalabs/keyContext";
import { resolveCavadaLabsProductContext } from "./cavadalabs/productContext";
import TeamDropdown from "./common_components/team_dropdown";
import { getModelDisplayName } from "./key_team_helpers/fetch_available_models_team_key";
import NotificationsManager from "./molecules/notifications_manager";
import {
  getProxyBaseUrl,
  getProxyUISettings,
  invitationCreateCall,
  modelAvailableCall,
  userCreateCall,
} from "./networking";
import OnboardingModal, { InvitationLink } from "./onboarding_link";
const { Option } = Select;
const { Text, Link, Title } = Typography;

const normalizeCavadaLabsSelection = (value: unknown): string[] => {
  if (Array.isArray(value)) {
    return value.filter((item): item is string => typeof item === "string" && item.length > 0);
  }
  return typeof value === "string" && value.length > 0 ? [value] : [];
};

// Helper function to generate UUID compatible across all environments
const generateUUID = (): string => {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  // Fallback UUID generation for environments without crypto.randomUUID
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
    const r = (Math.random() * 16) | 0;
    const v = c == "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
};

interface CreateuserProps {
  userID: string;
  accessToken: string;
  teams: any[] | null;
  possibleUIRoles: null | Record<string, Record<string, string>>;
  onUserCreated?: (userId: string) => void;
  isEmbedded?: boolean;
}

// Define an interface for the UI settings
interface UISettings {
  PROXY_BASE_URL: string | null;
  PROXY_LOGOUT_URL: string | null;
  DEFAULT_TEAM_DISABLED: boolean;
  SSO_ENABLED: boolean;
}

export const CreateUserButton: React.FC<CreateuserProps> = ({
  userID,
  accessToken,
  teams,
  possibleUIRoles,
  onUserCreated,
  isEmbedded = false,
}) => {
  const queryClient = useQueryClient();
  const [uiSettings, setUISettings] = useState<UISettings | null>(null);
  const [form] = Form.useForm();
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [apiuser, setApiuser] = useState<boolean>(false);
  const [userModels, setUserModels] = useState<string[]>([]);
  const [isInvitationLinkModalVisible, setIsInvitationLinkModalVisible] = useState(false);
  const [invitationLinkData, setInvitationLinkData] = useState<InvitationLink | null>(null);
  const [baseUrl, setBaseUrl] = useState<string | null>(null);
  const { data: organizations = [] } = useOrganizations();
  const cavadalabsContext = useCavadaLabsKeyContextOptions(accessToken);
  const { companies: cavadalabsCompanies, projects: cavadalabsProjects } = cavadalabsContext;
  const cavadalabsProductContext = resolveCavadaLabsProductContext(cavadalabsContext);
  const hasCavadaLabsProductContext = cavadalabsProductContext.isCavadaLabsProductContext;
  const showLiteLLMCompatibilityFields = cavadalabsProductContext.showLiteLLMCompatibilityFields;
  const manageableCavadaLabsCompanies = useMemo(
    () => filterManageableCavadaLabsCompanies(cavadalabsCompanies),
    [cavadalabsCompanies],
  );
  const manageableCavadaLabsProjects = useMemo(
    () => filterManageableCavadaLabsProjects(cavadalabsProjects),
    [cavadalabsProjects],
  );
  const selectedCavadaLabsCompanyIdsValue = Form.useWatch("cavadalabs_company_ids", form);
  const selectedCavadaLabsCompanyIds = useMemo(
    () => normalizeCavadaLabsSelection(selectedCavadaLabsCompanyIdsValue),
    [selectedCavadaLabsCompanyIdsValue],
  );
  const cavadalabsCompanyById = useMemo(
    () => new Map(cavadalabsCompanies.map((company) => [company.company_id, company])),
    [cavadalabsCompanies],
  );
  const cavadalabsProjectById = useMemo(
    () => new Map(cavadalabsProjects.map((project) => [project.project_id, project])),
    [cavadalabsProjects],
  );
  const filteredCavadaLabsProjects = useMemo(() => {
    if (selectedCavadaLabsCompanyIds.length === 0) {
      return manageableCavadaLabsProjects;
    }
    const selectedCompanyIds = new Set(selectedCavadaLabsCompanyIds);
    return manageableCavadaLabsProjects.filter((project) => selectedCompanyIds.has(project.company_id));
  }, [manageableCavadaLabsProjects, selectedCavadaLabsCompanyIds]);

  useEffect(() => {
    if (!hasCavadaLabsProductContext || selectedCavadaLabsCompanyIds.length === 0) {
      return;
    }

    const currentProjectIds = normalizeCavadaLabsSelection(form.getFieldValue("cavadalabs_project_ids"));
    if (currentProjectIds.length === 0) {
      return;
    }

    const allowedProjectIds = new Set(filteredCavadaLabsProjects.map((project) => project.project_id));
    const nextProjectIds = currentProjectIds.filter((projectId) => allowedProjectIds.has(projectId));
    if (nextProjectIds.length !== currentProjectIds.length) {
      form.setFieldValue("cavadalabs_project_ids", nextProjectIds);
    }
  }, [filteredCavadaLabsProjects, form, hasCavadaLabsProductContext, selectedCavadaLabsCompanyIds]);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const userRole = "any";
        const modelDataResponse = await modelAvailableCall(accessToken, userID, userRole);
        const availableModels = [];
        for (let i = 0; i < modelDataResponse.data.length; i++) {
          const model = modelDataResponse.data[i];
          availableModels.push(model.id);
        }
        setUserModels(availableModels);
        const uiSettingsResponse = await getProxyUISettings(accessToken);
        setUISettings(uiSettingsResponse);
      } catch (error) {
        console.error("Error fetching model data:", error);
      }
    };

    setBaseUrl(getProxyBaseUrl());
    fetchData();
  }, [accessToken, userID]);

  const handleOk = () => {
    setIsModalVisible(false);
    form.resetFields();
  };

  const handleCancel = () => {
    setIsModalVisible(false);
    setApiuser(false);
    form.resetFields();
  };

  const handleCreate = async (formValues: {
    user_id: string;
    models?: string[];
    user_role: string;
    organization_ids?: string[];
    organizations?: string[];
    team_id?: string;
    cavadalabs_company_ids?: string[];
    cavadalabs_company_role?: "company_admin" | "operator" | "viewer";
    cavadalabs_company_memberships?: Array<{
      company_id: string;
      role: "company_admin" | "operator" | "viewer";
    }>;
    cavadalabs_project_ids?: string[];
    cavadalabs_project_role?: "project_admin" | "operator" | "viewer";
    cavadalabs_project_memberships?: Array<{
      project_id: string;
      role: "project_admin" | "operator" | "viewer";
    }>;
    send_invite_email?: boolean;
  }) => {
    try {
      NotificationsManager.info("Making API Call");
      if (!isEmbedded) {
        setIsModalVisible(true);
      }
      if ((!formValues.models || formValues.models.length === 0) && formValues.user_role !== "proxy_admin") {
        formValues.models = ["no-default-models"];
      }
      if (formValues.organization_ids) {
        formValues.organizations = formValues.organization_ids;
        delete formValues.organization_ids;
      }
      if (!formValues.team_id) {
        delete formValues.team_id;
      }
      const selectedCompanyIds = normalizeCavadaLabsSelection(formValues.cavadalabs_company_ids);
      if (selectedCompanyIds.length > 0) {
        formValues.cavadalabs_company_memberships = selectedCompanyIds.map((companyId) => {
          const company = cavadalabsCompanyById.get(companyId);
          if (!company) {
            throw new Error(`Company ${companyId} is not available`);
          }
          return {
            company_id: companyId,
            role: formValues.cavadalabs_company_role || "viewer",
          };
        });
      }
      delete formValues.cavadalabs_company_ids;
      delete formValues.cavadalabs_company_role;
      const selectedCompanyIdSet = new Set(selectedCompanyIds);
      const selectedProjectIds = normalizeCavadaLabsSelection(formValues.cavadalabs_project_ids);
      if (selectedProjectIds.length > 0) {
        formValues.cavadalabs_project_memberships = selectedProjectIds.map((projectId) => {
          const project = cavadalabsProjectById.get(projectId);
          if (!project) {
            throw new Error(`Project ${projectId} is not available`);
          }
          if (selectedCompanyIdSet.size > 0 && !selectedCompanyIdSet.has(project.company_id)) {
            throw new Error(`Project ${projectId} does not belong to the selected Company`);
          }
          return {
            project_id: projectId,
            role: formValues.cavadalabs_project_role || "operator",
          };
        });
      }
      delete formValues.cavadalabs_project_ids;
      delete formValues.cavadalabs_project_role;
      const response = await userCreateCall(accessToken, null, formValues);
      await queryClient.invalidateQueries({ queryKey: ["userList"] });
      setApiuser(true);
      const user_id = response.data?.user_id || response.user_id;

      if (onUserCreated && isEmbedded) {
        onUserCreated(user_id);
        form.resetFields();
        return;
      }

      if (!uiSettings?.SSO_ENABLED) {
        invitationCreateCall(accessToken, user_id).then((data) => {
          data.has_user_setup_sso = false;
          setInvitationLinkData(data);
          setIsInvitationLinkModalVisible(true);
        });
      } else {
        // create an InvitationLink Object for this user for the SSO flow
        // for SSO the invite link is the proxy base url since the User just needs to login
        const invitationLink: InvitationLink = {
          id: generateUUID(), // Generate a unique ID
          user_id: user_id,
          is_accepted: false,
          accepted_at: null,
          expires_at: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000), // Set expiry to 7 days from now
          created_at: new Date(),
          created_by: userID, // Assuming userID is the current user creating the invitation
          updated_at: new Date(),
          updated_by: userID,
          has_user_setup_sso: true,
        };
        setInvitationLinkData(invitationLink);
        setIsInvitationLinkModalVisible(true);
      }

      NotificationsManager.success("API user Created");
      form.resetFields();
      localStorage.removeItem("userData" + userID);
    } catch (error: any) {
      const errorMessage = error.response?.data?.detail || error?.message || "Error creating the user";
      NotificationsManager.fromBackend(errorMessage);
      console.error("Error creating the user:", error);
    }
  };

  const renderCavadaLabsMembershipFields = () => {
    if (!hasCavadaLabsProductContext) {
      return null;
    }

    return (
      <>
        <Form.Item
          label="Company"
          name="cavadalabs_company_ids"
          help="The user will be granted access through CavadaLabs company membership."
        >
          <Select mode="multiple" placeholder="Select Company" style={{ width: "100%" }}>
            {manageableCavadaLabsCompanies.map((company) => (
              <Option key={company.company_id} value={company.company_id}>
                {getCavadaLabsCompanyDisplayName(company)}
              </Option>
            ))}
          </Select>
        </Form.Item>

        <Form.Item label="Company Role" name="cavadalabs_company_role" initialValue="viewer">
          <Select style={{ width: "100%" }} aria-label="Company Role">
            <Option value="viewer">Viewer</Option>
            <Option value="operator">Operator</Option>
            <Option value="company_admin">Company Admin</Option>
          </Select>
        </Form.Item>

        <Form.Item
          label="Project"
          name="cavadalabs_project_ids"
          help="Projects are filtered by the selected Company when one is selected."
        >
          <Select mode="multiple" placeholder="Select Project" style={{ width: "100%" }}>
            {filteredCavadaLabsProjects.map((project) => (
              <Option key={project.project_id} value={project.project_id}>
                {getCavadaLabsProjectDisplayName(project)}
              </Option>
            ))}
          </Select>
        </Form.Item>

        <Form.Item label="Project Role" name="cavadalabs_project_role" initialValue="operator">
          <Select style={{ width: "100%" }} aria-label="Project Role">
            <Option value="viewer">Viewer</Option>
            <Option value="operator">Operator</Option>
            <Option value="project_admin">Project Admin</Option>
          </Select>
        </Form.Item>
      </>
    );
  };

  // Modify the return statement to handle embedded mode
  if (isEmbedded) {
    return (
      <Form
        form={form}
        onFinish={handleCreate}
        labelCol={{ span: 8 }}
        wrapperCol={{ span: 16 }}
        labelAlign="left"
        initialValues={{ user_role: "internal_user_viewer", send_invite_email: true }}
      >
        <Alert
          message="Email invitations"
          description={
            <>
              New users receive an email invite only when an email integration (SMTP, Resend, or SendGrid) is
              configured.{" "}
              <Link href="https://docs.litellm.ai/docs/proxy/email" target="_blank">
                Learn how to set up email notifications
              </Link>
            </>
          }
          type="info"
          showIcon
          className="mb-4"
        />
        <Form.Item label="User Email" name="user_email">
          <TextInput placeholder="" />
        </Form.Item>
        <Form.Item label="User Role" name="user_role">
          <Select2>
            {possibleUIRoles &&
              Object.entries(possibleUIRoles).map(([role, { ui_label, description }]) => (
                <SelectItem key={role} value={role} title={ui_label}>
                  <div className="flex">
                    {ui_label}{" "}
                    <Text className="ml-2" style={{ color: "gray", fontSize: "12px" }}>
                      {description}
                    </Text>
                  </div>
                </SelectItem>
              ))}
          </Select2>
        </Form.Item>
        {showLiteLLMCompatibilityFields && (
          <Form.Item label="Team" name="team_id">
            <TeamDropdown />
          </Form.Item>
        )}

        {renderCavadaLabsMembershipFields()}

        <Form.Item label="Metadata" name="metadata">
          <Input.TextArea rows={4} placeholder="Enter metadata as JSON" />
        </Form.Item>

        <Form.Item label="Send invitation email" name="send_invite_email" valuePropName="checked">
          <Checkbox />
        </Form.Item>

        <div style={{ textAlign: "right", marginTop: "10px" }}>
          <Button htmlType="submit">Create User</Button>
        </div>
      </Form>
    );
  }

  // Original return for standalone mode
  return (
    <div className="flex gap-2">
      <Button type="primary" className="mb-0" onClick={() => setIsModalVisible(true)}>
        + Invite User
      </Button>
      {showLiteLLMCompatibilityFields && (
        <BulkCreateUsers accessToken={accessToken} teams={teams} possibleUIRoles={possibleUIRoles} />
      )}
      <Modal
        title="Invite User"
        open={isModalVisible}
        width={800}
        footer={null}
        onOk={handleOk}
        onCancel={handleCancel}
      >
        <Space direction="vertical" size="middle">
          <Text className="mb-1">Create a User who can own keys</Text>
          <Alert
            message="Email invitations"
            description={
              <>
                New users receive an email invite only when an email integration (SMTP, Resend, or SendGrid) is
                configured.{" "}
                <Link href="https://docs.litellm.ai/docs/proxy/email" target="_blank">
                  Learn how to set up email notifications
                </Link>
              </>
            }
            type="info"
            showIcon
            className="mb-4"
          />
        </Space>
        <Form
          form={form}
          onFinish={handleCreate}
          labelCol={{ span: 8 }}
          wrapperCol={{ span: 16 }}
          labelAlign="left"
          initialValues={{ user_role: "internal_user_viewer", send_invite_email: true }}
        >
          <Form.Item label="User Email" name="user_email">
            <Input />
          </Form.Item>
          <Form.Item
            label={
              <span>
                Global Proxy Role{" "}
                <Tooltip
                  title={
                    hasCavadaLabsProductContext
                      ? "This role is independent of Company and Project memberships."
                      : "This role is independent of any team or company-specific roles. Configure Team / Company Admins in the Settings"
                  }
                >
                  <InfoCircleOutlined />
                </Tooltip>
              </span>
            }
            name="user_role"
          >
            <Select2>
              {possibleUIRoles &&
                Object.entries(possibleUIRoles).map(([role, { ui_label, description }]) => (
                  <SelectItem key={role} value={role} title={ui_label}>
                    <Text>{ui_label}</Text>
                    <Text type="secondary">
                      {" - "}
                      {description}
                    </Text>
                  </SelectItem>
                ))}
            </Select2>
          </Form.Item>

          {showLiteLLMCompatibilityFields && (
            <Form.Item
              label="Team"
              className="gap-2"
              name="team_id"
              help="If selected, user will be added as a 'user' role to the team."
            >
              <TeamDropdown />
            </Form.Item>
          )}

          {showLiteLLMCompatibilityFields && (
            <Form.Item
              label="Organization"
              name="organization_ids"
              help="The user will be added to the selected organization(s)."
            >
              <Select mode="multiple" placeholder="Select Organization" style={{ width: "100%" }}>
                {organizations.map((org) => (
                  <Option key={org.organization_id} value={org.organization_id}>
                    {org.organization_alias} ({org.organization_id})
                  </Option>
                ))}
              </Select>
            </Form.Item>
          )}

          {renderCavadaLabsMembershipFields()}

          <Form.Item label="Metadata" name="metadata">
            <Input.TextArea rows={4} placeholder="Enter metadata as JSON" />
          </Form.Item>
          <Form.Item label="Send invitation email" name="send_invite_email" valuePropName="checked">
            <Checkbox />
          </Form.Item>
          <Accordion>
            <AccordionHeader>
              <Text strong>Personal Key Creation</Text>
            </AccordionHeader>
            <AccordionBody>
              <Form.Item
                className="gap-2"
                label={
                  <span>
                    Models{" "}
                    <Tooltip
                      title={
                        hasCavadaLabsProductContext
                          ? "Models this user can access outside Company and Project memberships."
                          : "Models user has access to, outside of team scope."
                      }
                    >
                      <InfoCircleOutlined style={{ marginLeft: "4px" }} />
                    </Tooltip>
                  </span>
                }
                name="models"
                help={
                  hasCavadaLabsProductContext
                    ? "Models this user can access outside Company and Project memberships."
                    : "Models user has access to, outside of team scope."
                }
              >
                <Select2 mode="multiple" placeholder="Select models" style={{ width: "100%" }}>
                  <Select2.Option key="all-proxy-models" value="all-proxy-models">
                    All Proxy Models
                  </Select2.Option>
                  <Select2.Option key="no-default-models" value="no-default-models">
                    No Default Models
                  </Select2.Option>
                  {userModels.map((model) => (
                    <Select2.Option key={model} value={model}>
                      {getModelDisplayName(model)}
                    </Select2.Option>
                  ))}
                </Select2>
              </Form.Item>
            </AccordionBody>
          </Accordion>

          <div style={{ textAlign: "right", marginTop: "10px" }}>
            <Button type="primary" icon={<UserAddOutlined />} htmlType="submit">
              Invite User
            </Button>
          </div>
        </Form>
      </Modal>
      {apiuser && (
        <OnboardingModal
          isInvitationLinkModalVisible={isInvitationLinkModalVisible}
          setIsInvitationLinkModalVisible={setIsInvitationLinkModalVisible}
          baseUrl={baseUrl || ""}
          invitationLinkData={invitationLinkData}
        />
      )}
    </div>
  );
};
