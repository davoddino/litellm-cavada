"use client";

import { Alert, Button, Form, Input, Popconfirm, Select, Space, Table, Tag, Typography, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { deleteCavadaLabsResource, listCavadaLabsResource, patchCavadaLabsResource, postCavadaLabsAction } from "./api";
import type { CavadaLabsRecord } from "./types";
import { formatDateTime } from "./utils";

const { Text, Title } = Typography;

type ProjectMemberRole = "project_admin" | "operator" | "viewer";

interface ProjectMember {
  membership_id: string;
  project_id: string;
  company_id: string;
  user_id: string;
  role: ProjectMemberRole;
  created_at?: string;
  updated_at?: string;
}

interface ProjectMemberListResponse {
  project_id: string;
  company_id: string;
  members: ProjectMember[];
  count: number;
}

interface CavadaLabsProjectMembersPanelProps {
  accessToken: string | null;
  project: CavadaLabsRecord;
  canManage?: boolean;
  onMutated?: () => void;
}

const roleOptions: Array<{ label: string; value: ProjectMemberRole }> = [
  { label: "Project admin", value: "project_admin" },
  { label: "Operator", value: "operator" },
  { label: "Viewer", value: "viewer" },
];

const roleColor = (role: ProjectMemberRole) => {
  if (role === "project_admin") return "blue";
  if (role === "operator") return "green";
  return "default";
};

const CavadaLabsProjectMembersPanel: React.FC<CavadaLabsProjectMembersPanelProps> = ({
  accessToken,
  project,
  canManage,
  onMutated,
}) => {
  const [form] = Form.useForm();
  const [messageApi, messageContext] = message.useMessage();
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const projectId = typeof project.project_id === "string" ? project.project_id : "";
  const canManageMembers = canManage ?? project.cavadalabs_can_manage === true;

  const loadMembers = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const response = await listCavadaLabsResource<ProjectMemberListResponse>(
        accessToken,
        `/cavadalabs/projects/${encodeURIComponent(projectId)}/members`,
      );
      setMembers(response.members ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setMembers([]);
    } finally {
      setLoading(false);
    }
  }, [accessToken, projectId]);

  useEffect(() => {
    loadMembers();
  }, [loadMembers]);

  const addMember = async (values: { user_id: string; role: ProjectMemberRole }) => {
    setSubmitting(true);
    setError(null);
    try {
      await postCavadaLabsAction(accessToken, `/cavadalabs/projects/${encodeURIComponent(projectId)}/members`, values);
      form.resetFields();
      messageApi.success("Project member saved");
      await loadMembers();
      onMutated?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  const updateMemberRole = async (member: ProjectMember, role: ProjectMemberRole) => {
    setSubmitting(true);
    setError(null);
    try {
      await patchCavadaLabsResource(
        accessToken,
        `/cavadalabs/projects/${encodeURIComponent(projectId)}/members/${encodeURIComponent(member.user_id)}`,
        { role },
      );
      messageApi.success("Project member updated");
      await loadMembers();
      onMutated?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  const removeMember = async (member: ProjectMember) => {
    setSubmitting(true);
    setError(null);
    try {
      await deleteCavadaLabsResource(
        accessToken,
        `/cavadalabs/projects/${encodeURIComponent(projectId)}/members/${encodeURIComponent(member.user_id)}`,
      );
      messageApi.success("Project member removed");
      await loadMembers();
      onMutated?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  const columns: ColumnsType<ProjectMember> = useMemo(
    () => [
      {
        title: "User ID",
        dataIndex: "user_id",
        key: "user_id",
        render: (value: string) => <Text copyable>{value}</Text>,
      },
      {
        title: "Role",
        dataIndex: "role",
        key: "role",
        render: (role: ProjectMemberRole, member) =>
          canManageMembers ? (
            <Select
              aria-label={`Role for ${member.user_id}`}
              value={role}
              options={roleOptions}
              disabled={submitting}
              style={{ minWidth: 150 }}
              onChange={(nextRole) => updateMemberRole(member, nextRole)}
            />
          ) : (
            <Tag color={roleColor(role)}>{role.replace("_", " ")}</Tag>
          ),
      },
      {
        title: "Updated",
        dataIndex: "updated_at",
        key: "updated_at",
        render: (value?: string) => (value ? formatDateTime(value) : <Text type="secondary">-</Text>),
      },
      {
        title: "Actions",
        key: "actions",
        width: 120,
        render: (_value, member) =>
          canManageMembers ? (
            <Popconfirm
              title="Remove Project member?"
              okText="Remove"
              okButtonProps={{ danger: true }}
              onConfirm={() => removeMember(member)}
            >
              <Button size="small" danger disabled={submitting}>
                Remove
              </Button>
            </Popconfirm>
          ) : null,
      },
    ],
    [canManageMembers, submitting],
  );

  if (!projectId) {
    return <Alert type="warning" showIcon message="Project ID is required to load Project members." />;
  }

  return (
    <section className="mt-4 rounded-md border border-gray-200 bg-white p-4">
      {messageContext}
      <div className="mb-3">
        <Title level={5} className="!mb-1">
          Project members
        </Title>
        <Text type="secondary">Native CavadaLabs membership for this Project.</Text>
      </div>

      {error ? <Alert type="error" showIcon className="mb-3" message={error} /> : null}

      {canManageMembers ? (
        <Form
          form={form}
          layout="inline"
          className="mb-4 gap-y-2"
          initialValues={{ role: "operator" }}
          onFinish={addMember}
        >
          <Form.Item name="user_id" label="User ID" rules={[{ required: true, message: "User ID is required" }]}>
            <Input placeholder="user-123" style={{ width: 220 }} />
          </Form.Item>
          <Form.Item name="role" label="Role" rules={[{ required: true, message: "Role is required" }]}>
            <Select options={roleOptions} style={{ width: 160 }} />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button htmlType="submit" type="primary" loading={submitting}>
                Add member
              </Button>
              <Button onClick={loadMembers} loading={loading}>
                Refresh
              </Button>
            </Space>
          </Form.Item>
        </Form>
      ) : null}

      <Table
        rowKey={(row) => row.membership_id}
        columns={columns}
        dataSource={members}
        loading={loading}
        pagination={false}
        size="small"
        locale={{ emptyText: "No Project members" }}
      />
    </section>
  );
};

export default CavadaLabsProjectMembersPanel;
