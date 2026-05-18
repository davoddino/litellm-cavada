import { InfoCircleOutlined } from "@ant-design/icons";
import { Button, SelectItem, TextInput, Textarea } from "@tremor/react";
import { Checkbox, Form, Select, Tooltip } from "antd";
import React, { useState } from "react";
import { useOrganizations } from "@/app/(dashboard)/hooks/organizations/useOrganizations";
import { useProjects } from "@/app/(dashboard)/hooks/projects/useProjects";
import { all_admin_roles } from "../utils/roles";
import BudgetDurationDropdown from "./common_components/budget_duration_dropdown";
import { getModelDisplayName } from "./key_team_helpers/fetch_available_models_team_key";
import NumericalInput from "./shared/numerical_input";
import {
  filterProjectsByCompanyIds,
  pruneProjectIdsForCompanySelection,
} from "./common_components/ProjectDropdown";
import { getCompanyDisplayId, getCompanyDisplayName } from "./common_components/OrganizationDropdown";

interface UserEditViewProps {
  userData: any;
  onCancel: () => void;
  onSubmit: (values: any) => void;
  teams: any[] | null;
  accessToken: string | null;
  userID: string | null;
  userRole: string | null;
  userModels: string[];
  possibleUIRoles: Record<string, Record<string, string>> | null;
  isBulkEdit?: boolean;
}

const sanitizeUserEditTenantValues = (values: any) => {
  const sanitizedValues = { ...values };
  delete sanitizedValues.organization_id;
  delete sanitizedValues.organization_ids;
  delete sanitizedValues.organizations;
  return sanitizedValues;
};

export function UserEditView({
  userData,
  onCancel,
  onSubmit,
  teams,
  accessToken,
  userID,
  userRole,
  userModels,
  possibleUIRoles,
  isBulkEdit = false,
}: UserEditViewProps) {
  const [form] = Form.useForm();
  const [unlimitedBudget, setUnlimitedBudget] = useState(false);
  const { data: organizations = [] } = useOrganizations();
  const { data: projects = [], isLoading: isProjectsLoading } = useProjects({ includeNonAdmin: true });
  const selectedCompanyIds = Form.useWatch("company_ids", form) || [];
  const selectedProjectIds = Form.useWatch("project_ids", form) || [];
  const availableProjects = React.useMemo(() => {
    return filterProjectsByCompanyIds(projects, selectedCompanyIds);
  }, [projects, selectedCompanyIds]);

  React.useEffect(() => {
    const nextProjectIds = pruneProjectIdsForCompanySelection({
      projects,
      selectedCompanyIds,
      selectedProjectIds,
      isLoading: isProjectsLoading,
    });
    if (nextProjectIds !== null) {
      form.setFieldValue("project_ids", nextProjectIds);
    }
  }, [form, isProjectsLoading, projects, selectedCompanyIds, selectedProjectIds]);

  // Set initial form values
  React.useEffect(() => {
    const maxBudget = userData.user_info?.max_budget;
    const isUnlimited = maxBudget === null || maxBudget === undefined;
    setUnlimitedBudget(isUnlimited);

    form.setFieldsValue({
      user_id: userData.user_id,
      user_email: userData.user_info?.user_email,
      user_alias: userData.user_info?.user_alias,
      user_role: userData.user_info?.user_role,
      models: userData.user_info?.models || [],
      max_budget: isUnlimited ? "" : maxBudget,
      budget_duration: userData.user_info?.budget_duration,
      company_ids: userData.user_info?.company_ids || [],
      project_ids: userData.user_info?.project_ids || [],
      metadata: userData.user_info?.metadata ? JSON.stringify(userData.user_info.metadata, null, 2) : undefined,
    });
  }, [userData, form]);

  const handleUnlimitedBudgetChange = (e: any) => {
    const checked = e.target.checked;
    setUnlimitedBudget(checked);
    if (checked) {
      form.setFieldsValue({ max_budget: "" });
    }
  };

  const handleSubmit = (values: any) => {
    const sanitizedValues = sanitizeUserEditTenantValues(values);

    // Convert metadata back to an object if it exists and is a string
    if (sanitizedValues.metadata && typeof sanitizedValues.metadata === "string") {
      try {
        sanitizedValues.metadata = JSON.parse(sanitizedValues.metadata);
      } catch (error) {
        console.error("Error parsing metadata JSON:", error);
        return;
      }
    }

    if (unlimitedBudget || sanitizedValues.max_budget === "" || sanitizedValues.max_budget === undefined) {
      sanitizedValues.max_budget = null;
    }

    onSubmit(sanitizedValues);
  };

  return (
    <Form form={form} onFinish={handleSubmit} layout="vertical">
      {!isBulkEdit && (
        <Form.Item label="User ID" name="user_id">
          <TextInput disabled />
        </Form.Item>
      )}

      {!isBulkEdit && (
        <Form.Item label="Email" name="user_email">
          <TextInput />
        </Form.Item>
      )}

      <Form.Item label="User Alias" name="user_alias">
        <TextInput />
      </Form.Item>

      <Form.Item label="Company" name="company_ids">
        <Select
          mode="multiple"
          placeholder="Select Company"
          style={{ width: "100%" }}
          disabled={!all_admin_roles.includes(userRole || "")}
        >
          {organizations.map((company) => (
            <Select.Option key={getCompanyDisplayId(company)} value={getCompanyDisplayId(company)}>
              {getCompanyDisplayName(company)} ({getCompanyDisplayId(company)})
            </Select.Option>
          ))}
        </Select>
      </Form.Item>

      <Form.Item label="Project" name="project_ids">
        <Select
          mode="multiple"
          placeholder="Select Project"
          style={{ width: "100%" }}
          loading={isProjectsLoading}
          disabled={isProjectsLoading || !all_admin_roles.includes(userRole || "")}
        >
          {availableProjects.map((project) => (
            <Select.Option key={project.project_id} value={project.project_id}>
              {project.project_alias || project.project_id} ({project.project_id})
            </Select.Option>
          ))}
        </Select>
      </Form.Item>

      <Form.Item
        label={
          <span>
            Global Proxy Role{" "}
            <Tooltip title="This is the role that the user will globally on the proxy. This role is independent of any team/company specific roles.">
              <InfoCircleOutlined />
            </Tooltip>
          </span>
        }
        name="user_role"
      >
        <Select>
          {possibleUIRoles &&
            Object.entries(possibleUIRoles).map(([role, { ui_label, description }]) => (
              <SelectItem key={role} value={role} title={ui_label}>
                <div className="flex">
                  {ui_label}{" "}
                  <p className="ml-2" style={{ color: "gray", fontSize: "12px" }}>
                    {description}
                  </p>
                </div>
              </SelectItem>
            ))}
        </Select>
      </Form.Item>

      <Form.Item
        label={
          <span>
            Personal Models{" "}
            <Tooltip title="Select which models this user can access outside of team-scope. Choose 'All Proxy Models' to grant access to all models available on the proxy.">
              <InfoCircleOutlined style={{ marginLeft: "4px" }} />
            </Tooltip>
          </span>
        }
        name="models"
      >
        <Select
          mode="multiple"
          placeholder="Select models"
          style={{ width: "100%" }}
          disabled={!all_admin_roles.includes(userRole || "")}
        >
          <Select.Option key="all-proxy-models" value="all-proxy-models">
            All Proxy Models
          </Select.Option>
          <Select.Option key="no-default-models" value="no-default-models">
            No Default Models
          </Select.Option>
          {userModels.map((model) => (
            <Select.Option key={model} value={model}>
              {getModelDisplayName(model)}
            </Select.Option>
          ))}
        </Select>
      </Form.Item>

      <Form.Item
        label={
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <span>Max Budget (USD)</span>
            <Checkbox
              checked={unlimitedBudget}
              onChange={handleUnlimitedBudgetChange}
            >
              Unlimited Budget
            </Checkbox>
          </div>
        }
        name="max_budget"
        rules={[
          {
            validator: (_, value) => {
              if (!unlimitedBudget && (value === "" || value === null || value === undefined)) {
                return Promise.reject(new Error("Please enter a budget or select Unlimited Budget"));
              }
              return Promise.resolve();
            },
          },
        ]}
      >
        <NumericalInput
          step={0.01}
          precision={2}
          style={{ width: "100%" }}
          disabled={unlimitedBudget}
        />
      </Form.Item>

      <Form.Item label="Reset Budget" name="budget_duration">
        <BudgetDurationDropdown />
      </Form.Item>

      <Form.Item label="Metadata" name="metadata">
        <Textarea rows={4} placeholder="Enter metadata as JSON" />
      </Form.Item>

      <div className="flex justify-end space-x-2">
        <Button variant="secondary" type="button" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit">Save Changes</Button>
      </div>
    </Form>
  );
}
