import { Form, Input, InputNumber, Select, Switch, Typography, type FormInstance } from "antd";
import React from "react";
import { CHATBOT_RUNTIME_ROUTE, type CavadaLabsChatbotCreatorValues } from "./chatbotCreatorPayload";
import type { CavadaLabsSelectOption } from "./types";

const { Text } = Typography;

interface CavadaLabsChatbotCreatorFormProps {
  form: FormInstance<CavadaLabsChatbotCreatorValues>;
  companyOptions: CavadaLabsSelectOption[];
  projectOptions: CavadaLabsSelectOption[];
  policyOptions: CavadaLabsSelectOption[];
  serverKeyOptions: CavadaLabsSelectOption[];
  ragOptions: CavadaLabsSelectOption[];
  policyLoading: boolean;
  keyLoading: boolean;
  selectedStatus?: string;
  serverKeyMode?: string;
  issueWebToken?: boolean;
  onCompanyChange: (companyId: string) => void;
}

const CavadaLabsChatbotCreatorForm: React.FC<CavadaLabsChatbotCreatorFormProps> = ({
  form,
  companyOptions,
  projectOptions,
  policyOptions,
  serverKeyOptions,
  ragOptions,
  policyLoading,
  keyLoading,
  selectedStatus,
  serverKeyMode,
  issueWebToken,
  onCompanyChange,
}) => (
  <Form form={form} layout="vertical">
    <div className="grid grid-cols-1 gap-x-4 md:grid-cols-2">
      <Form.Item name="company_id" label="Company" rules={[{ required: true, message: "Company is required" }]}>
        <Select
          aria-label="Company"
          showSearch
          optionFilterProp="label"
          options={companyOptions}
          onChange={onCompanyChange}
        />
      </Form.Item>
      <Form.Item name="project_id" label="Project" rules={[{ required: true, message: "Project is required" }]}>
        <Select aria-label="Project" showSearch optionFilterProp="label" options={projectOptions} />
      </Form.Item>
      <Form.Item name="name" label="Name" rules={[{ required: true, message: "Name is required" }]}>
        <Input />
      </Form.Item>
      <Form.Item name="status" label="Status" rules={[{ required: true, message: "Status is required" }]}>
        <Select
          aria-label="Status"
          options={[
            { value: "draft", label: "draft" },
            { value: "published", label: "published" },
          ]}
        />
      </Form.Item>
      <Form.Item name="default_language" label="Default language">
        <Input />
      </Form.Item>
      <Form.Item name="prompt_version" label="Prompt version">
        <InputNumber min={1} style={{ width: "100%" }} />
      </Form.Item>
      <Form.Item name="model_policy_id" label="Model policy">
        <Select
          aria-label="Model policy"
          allowClear
          showSearch
          loading={policyLoading}
          optionFilterProp="label"
          options={policyOptions}
        />
      </Form.Item>
      <Form.Item name="assigned_rag_collections" label="RAG collections">
        <Select
          aria-label="RAG collections"
          mode="multiple"
          allowClear
          showSearch
          optionFilterProp="label"
          options={ragOptions}
        />
      </Form.Item>
      <Form.Item name="assigned_guardrail_policy" label="Guardrail policy ID">
        <Input />
      </Form.Item>
      <Form.Item name="server_key_mode" label="Server API key">
        <Select
          aria-label="Server API key mode"
          options={[
            { value: "create", label: "Create new key" },
            { value: "existing", label: "Link existing key" },
            { value: "none", label: "Skip server key" },
          ]}
        />
      </Form.Item>
      {serverKeyMode === "existing" ? (
        <Form.Item
          name="existing_server_key"
          label="Existing server API key"
          rules={[{ required: true, message: "Existing server API key is required" }]}
        >
          <Select
            aria-label="Existing server API key"
            showSearch
            loading={keyLoading}
            optionFilterProp="label"
            options={serverKeyOptions}
          />
        </Form.Item>
      ) : null}
      {serverKeyMode === "create" || serverKeyMode === undefined ? (
        <>
          <Form.Item name="server_key_alias" label="Server key alias">
            <Input />
          </Form.Item>
          <Form.Item name="server_key_duration" label="Server key duration">
            <Input placeholder="30d, 12h, or empty for no expiry" />
          </Form.Item>
        </>
      ) : null}
      <Form.Item name="system_prompt" label="System prompt" className="md:col-span-2">
        <Input.TextArea rows={5} />
      </Form.Item>
      <Form.Item name="allowed_domains" label="Allowed domains" className="md:col-span-2">
        <Select aria-label="Allowed domains" mode="tags" tokenSeparators={[","]} />
      </Form.Item>
      <Form.Item name="fallback_message" label="Fallback message" className="md:col-span-2">
        <Input.TextArea rows={3} />
      </Form.Item>
      <Form.Item name="issue_web_token" label="Issue browser web token" valuePropName="checked">
        <Switch aria-label="Issue browser web token" disabled={selectedStatus !== "published"} />
      </Form.Item>
      {issueWebToken ? (
        <>
          <Form.Item name="web_token_name" label="Token name">
            <Input />
          </Form.Item>
          <Form.Item name="allowed_origins" label="Allowed origins" className="md:col-span-2">
            <Select aria-label="Allowed origins" mode="tags" tokenSeparators={[","]} />
          </Form.Item>
          <Form.Item name="expires_in_seconds" label="Token TTL seconds">
            <InputNumber min={60} max={86400} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item label="Runtime route">
            <Text code>{CHATBOT_RUNTIME_ROUTE}</Text>
          </Form.Item>
        </>
      ) : null}
    </div>
  </Form>
);

export default CavadaLabsChatbotCreatorForm;
