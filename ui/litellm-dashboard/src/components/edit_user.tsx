import { useEffect, useMemo } from "react";
import { TextInput } from "@tremor/react";

import { Button as Button2, Modal, Form, Select as Select2, InputNumber } from "antd";

import NumericalInput from "./shared/numerical_input";
import BudgetDurationDropdown from "./common_components/budget_duration_dropdown";
import type { CavadaLabsCompanyOption, CavadaLabsProjectOption } from "./cavadalabs/keyContext";
import { getCavadaLabsCompanyDisplayName, getCavadaLabsProjectDisplayName } from "./cavadalabs/keyContext";

interface EditUserModalProps {
  visible: boolean;
  possibleUIRoles: null | Record<string, Record<string, string>>;
  onCancel: () => void;
  user: any;
  onSubmit: (data: any) => void;
  cavadalabsCompanies?: CavadaLabsCompanyOption[];
  cavadalabsProjects?: CavadaLabsProjectOption[];
}

const normalizeCavadaLabsSelection = (value: unknown): string[] => {
  if (Array.isArray(value)) {
    return value.filter((item): item is string => typeof item === "string" && item.length > 0);
  }
  if (typeof value === "string" && value.length > 0) {
    return [value];
  }
  return [];
};

const EditUserModal: React.FC<EditUserModalProps> = ({
  visible,
  possibleUIRoles,
  onCancel,
  user,
  onSubmit,
  cavadalabsCompanies = [],
  cavadalabsProjects = [],
}) => {
  const [form] = Form.useForm();
  const selectedCompanyIds = Form.useWatch("cavadalabs_company_ids", form);
  const hasCavadaLabsContext = cavadalabsCompanies.length > 0 || cavadalabsProjects.length > 0;

  const initialFormValues = useMemo(() => {
    const companyMemberships = Array.isArray(user?.cavadalabs_company_memberships)
      ? user.cavadalabs_company_memberships
      : [];
    const projectMemberships = Array.isArray(user?.cavadalabs_project_memberships)
      ? user.cavadalabs_project_memberships
      : [];
    return {
      ...user,
      cavadalabs_company_ids: companyMemberships
        .map((membership: { company_id?: string }) => membership.company_id)
        .filter(Boolean),
      cavadalabs_company_role: companyMemberships[0]?.role ?? "viewer",
      cavadalabs_project_ids: projectMemberships
        .map((membership: { project_id?: string }) => membership.project_id)
        .filter(Boolean),
      cavadalabs_project_role: projectMemberships[0]?.role ?? "operator",
    };
  }, [user]);

  const selectedCompanyIdSet = useMemo(
    () => new Set(normalizeCavadaLabsSelection(selectedCompanyIds)),
    [selectedCompanyIds],
  );

  const filteredProjects = useMemo(() => {
    if (selectedCompanyIdSet.size === 0) {
      return cavadalabsProjects;
    }
    return cavadalabsProjects.filter((project) => selectedCompanyIdSet.has(project.company_id));
  }, [cavadalabsProjects, selectedCompanyIdSet]);

  useEffect(() => {
    form.resetFields();
    form.setFieldsValue(initialFormValues);
  }, [form, initialFormValues]);

  const handleCancel = async () => {
    form.resetFields();
    onCancel();
  };

  const handleEditSubmit = async (formValues: Record<string, any>) => {
    const values = { ...formValues };
    if (hasCavadaLabsContext) {
      const companyIds = normalizeCavadaLabsSelection(values.cavadalabs_company_ids);
      const projectIds = normalizeCavadaLabsSelection(values.cavadalabs_project_ids);
      const invalidProjectId = projectIds.find((projectId) => {
        const project = cavadalabsProjects.find((item) => item.project_id === projectId);
        return project !== undefined && companyIds.length > 0 && !companyIds.includes(project.company_id);
      });
      if (invalidProjectId) {
        form.setFields([
          {
            name: "cavadalabs_project_ids",
            errors: ["Project must belong to the selected Company."],
          },
        ]);
        return;
      }
      values.cavadalabs_company_memberships = companyIds.map((companyId) => ({
        company_id: companyId,
        role: values.cavadalabs_company_role ?? "viewer",
      }));
      values.cavadalabs_project_memberships = projectIds.map((projectId) => ({
        project_id: projectId,
        role: values.cavadalabs_project_role ?? "operator",
      }));
      delete values.cavadalabs_company_ids;
      delete values.cavadalabs_company_role;
      delete values.cavadalabs_project_ids;
      delete values.cavadalabs_project_role;
      delete values.organizations;
      delete values.organization_id;
      delete values.team_id;
    }
    onSubmit(values);
    form.resetFields();
    onCancel();
  };

  if (!user) {
    return null;
  }

  return (
    <Modal open={visible} onCancel={handleCancel} footer={null} title={"Edit User " + user.user_id} width={1000}>
      <Form
        form={form}
        onFinish={handleEditSubmit}
        initialValues={initialFormValues}
        labelCol={{ span: 8 }}
        wrapperCol={{ span: 16 }}
        labelAlign="left"
      >
        <>
          <Form.Item className="mt-8" label="User Email" tooltip="Email of the User" name="user_email">
            <TextInput />
          </Form.Item>

          <Form.Item label="user_id" name="user_id" hidden={true}>
            <TextInput />
          </Form.Item>

          <Form.Item label="User Role" name="user_role">
            <Select2
              options={
                possibleUIRoles
                  ? Object.entries(possibleUIRoles).map(([role, { ui_label, description }]) => ({
                      value: role,
                      label: (
                        <div className="flex">
                          {ui_label}{" "}
                          <p className="ml-2" style={{ color: "gray", fontSize: "12px" }}>
                            {description}
                          </p>
                        </div>
                      ),
                    }))
                  : []
              }
            />
          </Form.Item>

          <Form.Item
            label="Spend (USD)"
            name="spend"
            tooltip="(float) - Spend of all LLM calls completed by this user"
            help="Across all keys (including keys with team_id)."
          >
            <InputNumber min={0} step={0.01} />
          </Form.Item>

          <Form.Item
            label="User Budget (USD)"
            name="max_budget"
            tooltip="(float) - Maximum budget of this user"
            help="Maximum budget of this user."
          >
            <NumericalInput min={0} step={0.01} />
          </Form.Item>

          <Form.Item label="Reset Budget" name="budget_duration">
            <BudgetDurationDropdown />
          </Form.Item>

          {hasCavadaLabsContext ? (
            <>
              <Form.Item label="Company" name="cavadalabs_company_ids">
                <Select2
                  mode="multiple"
                  placeholder="Select Companies"
                  options={cavadalabsCompanies.map((company) => ({
                    label: getCavadaLabsCompanyDisplayName(company),
                    value: company.company_id,
                  }))}
                  onChange={() => {
                    form.setFieldValue("cavadalabs_project_ids", []);
                  }}
                />
              </Form.Item>

              <Form.Item label="Company Role" name="cavadalabs_company_role">
                <Select2
                  options={[
                    { label: "Company Admin", value: "company_admin" },
                    { label: "Operator", value: "operator" },
                    { label: "Viewer", value: "viewer" },
                  ]}
                />
              </Form.Item>

              <Form.Item label="Project" name="cavadalabs_project_ids">
                <Select2
                  mode="multiple"
                  placeholder="Select Projects"
                  options={filteredProjects.map((project) => ({
                    label: getCavadaLabsProjectDisplayName(project),
                    value: project.project_id,
                  }))}
                />
              </Form.Item>

              <Form.Item label="Project Role" name="cavadalabs_project_role">
                <Select2
                  options={[
                    { label: "Project Admin", value: "project_admin" },
                    { label: "Operator", value: "operator" },
                    { label: "Viewer", value: "viewer" },
                  ]}
                />
              </Form.Item>
            </>
          ) : null}

          <div style={{ textAlign: "right", marginTop: "10px" }}>
            <Button2 htmlType="submit">Save</Button2>
          </div>
        </>
      </Form>
    </Modal>
  );
};

export default EditUserModal;
