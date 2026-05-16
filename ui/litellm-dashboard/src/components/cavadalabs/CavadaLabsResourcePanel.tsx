"use client";

import {
  Alert,
  Button,
  DatePicker,
  Descriptions,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { EditOutlined, EyeOutlined, PlusOutlined, ReloadOutlined, SearchOutlined } from "@ant-design/icons";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  cavadaLabsErrorDetailFromUnknown,
  cavadalabsMissingSchemaDetailLines,
  createCavadaLabsResource,
  cavadalabsRequest,
  deleteCavadaLabsResource,
  isCavadaLabsMissingSchemaDetail,
  listCavadaLabsResource,
  patchCavadaLabsResource,
  postCavadaLabsAction,
} from "./api";
import CavadaLabsProjectMembersPanel from "./CavadaLabsProjectMembersPanel";
import type {
  CavadaLabsColumnConfig,
  CavadaLabsFieldConfig,
  CavadaLabsRecord,
  CavadaLabsResourceConfig,
  CavadaLabsRuntimeContext,
  CavadaLabsRowAction,
  CavadaLabsToolbarAction,
} from "./types";
import {
  extractOperationSecret,
  formatCurrency,
  formatDateTime,
  formatNumber,
  getCreateInitialValues,
  getUpdateInitialValues,
  normalizeFormPayload,
  rowMatchesSearch,
  statusColor,
} from "./utils";

const { Text, Title, Paragraph } = Typography;

interface CavadaLabsResourcePanelProps {
  accessToken: string | null;
  config: CavadaLabsResourceConfig;
  context: CavadaLabsRuntimeContext;
  onMutated?: () => void;
  initialDetailsId?: string | null;
}

interface OperationResult {
  title: string;
  response: any;
}

const emptyFilters = (values: CavadaLabsRecord): CavadaLabsRecord => {
  const cleaned: CavadaLabsRecord = {};
  Object.entries(values).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "" || (Array.isArray(value) && value.length === 0)) {
      return;
    }
    cleaned[key] = value;
  });
  return cleaned;
};

const renderField = (field: CavadaLabsFieldConfig): React.ReactNode => {
  const commonProps = {
    placeholder: field.placeholder,
    style: { width: "100%" },
  };

  switch (field.type) {
    case "textarea":
      return <Input.TextArea rows={field.rows ?? 3} {...commonProps} />;
    case "number":
      return <InputNumber min={field.min} max={field.max} step={field.step} {...commonProps} />;
    case "select":
      return (
        <Select
          allowClear={!field.required}
          showSearch
          optionFilterProp="label"
          options={field.options}
          {...commonProps}
        />
      );
    case "multiSelect":
      return (
        <Select
          allowClear
          mode="multiple"
          showSearch
          optionFilterProp="label"
          options={field.options}
          {...commonProps}
        />
      );
    case "tags":
      return <Select allowClear mode="tags" tokenSeparators={[","]} {...commonProps} />;
    case "json":
      return <Input.TextArea rows={field.rows ?? 5} spellCheck={false} {...commonProps} />;
    case "switch":
      return <Switch />;
    case "date":
      return <DatePicker showTime {...commonProps} />;
    default:
      return <Input {...commonProps} />;
  }
};

const renderCell = (column: CavadaLabsColumnConfig, value: any, row: CavadaLabsRecord): React.ReactNode => {
  if (column.render) return column.render(value, row);
  if (value === undefined || value === null || value === "") return <Text type="secondary">-</Text>;

  switch (column.type) {
    case "id":
      return (
        <Text copyable={{ text: String(value) }} style={{ maxWidth: column.width ? column.width - 32 : 220 }} ellipsis>
          {String(value)}
        </Text>
      );
    case "status":
      return <Tag color={statusColor(value)}>{String(value).replaceAll("_", " ")}</Tag>;
    case "tags": {
      const values = Array.isArray(value) ? value : [value];
      const visible = values.slice(0, 4);
      return (
        <Space size={[0, 4]} wrap>
          {visible.map((tagValue) => (
            <Tag key={String(tagValue)}>{String(tagValue)}</Tag>
          ))}
          {values.length > visible.length ? <Tag>+{values.length - visible.length}</Tag> : null}
        </Space>
      );
    }
    case "number":
      return formatNumber(value);
    case "currency":
      return formatCurrency(value, row.currency ?? "EUR");
    case "boolean":
      return <Tag color={value ? "green" : "default"}>{value ? "Yes" : "No"}</Tag>;
    case "datetime":
      return formatDateTime(value);
    case "json":
      return <Text code>{JSON.stringify(value)}</Text>;
    default:
      return (
        <Text style={{ maxWidth: column.width ? column.width - 32 : 260 }} ellipsis>
          {String(value)}
        </Text>
      );
  }
};

const buildColumns = (
  config: CavadaLabsResourceConfig,
  showDetails: (row: CavadaLabsRecord) => void,
  openEdit: (row: CavadaLabsRecord) => void,
  runRowAction: (action: CavadaLabsRowAction, row: CavadaLabsRecord) => void,
): ColumnsType<CavadaLabsRecord> => {
  const columns: ColumnsType<CavadaLabsRecord> = config.columns.map((column) => ({
    title: column.title,
    dataIndex: column.dataIndex ?? column.key,
    key: column.key,
    width: column.width,
    render: (value: any, row: CavadaLabsRecord) => renderCell(column, value, row),
  }));

  columns.push({
    title: "Actions",
    key: "actions",
    fixed: "right",
    width: config.rowActions && config.rowActions.length > 0 ? 190 : 96,
    render: (_value: any, row: CavadaLabsRecord) => (
      <Space size={6}>
        <Tooltip title="Details">
          <Button aria-label="Details" size="small" icon={<EyeOutlined />} onClick={() => showDetails(row)} />
        </Tooltip>
        {config.updatePath && config.updateFields ? (
          config.canUpdate?.(row) === false ? null : (
            <Tooltip title="Edit">
              <Button aria-label="Edit" size="small" icon={<EditOutlined />} onClick={() => openEdit(row)} />
            </Tooltip>
          )
        ) : null}
        {config.rowActions
          ?.filter((action) => !action.hidden?.(row))
          .map((action) => (
            <Button
              key={action.key}
              aria-label={action.label}
              size="small"
              danger={action.danger}
              icon={action.icon}
              disabled={action.disabled?.(row)}
              onClick={() => runRowAction(action, row)}
            >
              {action.label}
            </Button>
          ))}
      </Space>
    ),
  });

  return columns;
};

const requiredFiltersMissing = (config: CavadaLabsResourceConfig, filters: CavadaLabsRecord): string[] =>
  (config.requiredFilters ?? []).filter((field) => !filters[field]);

const ResultModal = ({ result, onClose }: { result: OperationResult | null; onClose: () => void }) => {
  const secret = extractOperationSecret(result?.response);

  return (
    <Modal open={Boolean(result)} title={result?.title} footer={null} onCancel={onClose} width={760}>
      {secret ? (
        <Alert
          type="warning"
          showIcon
          className="mb-4"
          message={secret.label}
          description={<Paragraph copyable>{secret.value}</Paragraph>}
        />
      ) : null}
      <pre className="max-h-80 overflow-auto rounded border border-gray-200 bg-gray-50 p-3 text-xs">
        {JSON.stringify(result?.response ?? {}, null, 2)}
      </pre>
    </Modal>
  );
};

const MissingSchemaDescription = ({ detail }: { detail: CavadaLabsRecord }) => {
  const lines = cavadalabsMissingSchemaDetailLines(detail);

  return (
    <Space direction="vertical" size={4}>
      <span>
        Apply the CavadaLabs Prisma migration before relying on Company/Project usage, billing, diagnostics, or repair.
      </span>
      {lines.map((line) =>
        line.startsWith("Migration command: ") ? (
          <Text key={line} code copyable>
            {line.replace("Migration command: ", "")}
          </Text>
        ) : (
          <Text key={line} type="secondary">
            {line}
          </Text>
        ),
      )}
    </Space>
  );
};

const formatTagValues = (value: unknown): string[] => {
  if (Array.isArray(value)) {
    return value.map((item) => String(item));
  }
  if (typeof value === "string" && value.trim()) {
    return [value];
  }
  return [];
};

const ProjectDetailsView = ({ project }: { project: CavadaLabsRecord }) => {
  const allowedModels = formatTagValues(project.allowed_models);
  const allowedCollections = formatTagValues(project.allowed_rag_collections);

  return (
    <Space direction="vertical" size={16} className="w-full">
      <Descriptions bordered size="small" column={1} title="Project overview">
        <Descriptions.Item label="Name">{project.name || <Text type="secondary">-</Text>}</Descriptions.Item>
        <Descriptions.Item label="Project ID">
          <Text copyable>{String(project.project_id ?? "-")}</Text>
        </Descriptions.Item>
        <Descriptions.Item label="Company">
          <Text copyable>{String(project.company_id ?? "-")}</Text>
        </Descriptions.Item>
        <Descriptions.Item label="Status">
          {project.status ? <Tag color={statusColor(project.status)}>{String(project.status)}</Tag> : "-"}
        </Descriptions.Item>
        <Descriptions.Item label="Budget">
          {formatCurrency(project.budget, project.currency ?? "EUR")}
        </Descriptions.Item>
        <Descriptions.Item label="Updated">{formatDateTime(project.updated_at)}</Descriptions.Item>
      </Descriptions>

      <Descriptions bordered size="small" column={1} title="Project policy">
        <Descriptions.Item label="Allowed models">
          {allowedModels.length > 0 ? (
            <Space size={[0, 4]} wrap>
              {allowedModels.map((model) => (
                <Tag key={model}>{model}</Tag>
              ))}
            </Space>
          ) : (
            <Text type="secondary">No model restriction</Text>
          )}
        </Descriptions.Item>
        <Descriptions.Item label="Allowed RAG collections">
          {allowedCollections.length > 0 ? (
            <Space size={[0, 4]} wrap>
              {allowedCollections.map((collection) => (
                <Tag key={collection}>{collection}</Tag>
              ))}
            </Space>
          ) : (
            <Text type="secondary">No RAG collection restriction</Text>
          )}
        </Descriptions.Item>
        <Descriptions.Item label="Default guardrail policy">
          {project.default_guardrail_policy || <Text type="secondary">-</Text>}
        </Descriptions.Item>
      </Descriptions>
    </Space>
  );
};

const CavadaLabsResourcePanel: React.FC<CavadaLabsResourcePanelProps> = ({
  accessToken,
  config,
  context,
  onMutated,
  initialDetailsId,
}) => {
  const [filterForm] = Form.useForm();
  const [createForm] = Form.useForm();
  const [updateForm] = Form.useForm();
  const [messageApi, messageContext] = message.useMessage();
  const [modalApi, modalContext] = Modal.useModal();
  const initialFilters = useMemo(() => emptyFilters(config.getInitialFilters?.(context) ?? {}), [config, context]);
  const initialFilterKey = useMemo(() => JSON.stringify(initialFilters), [initialFilters]);
  const [rows, setRows] = useState<CavadaLabsRecord[]>([]);
  const [count, setCount] = useState(0);
  const [filters, setFilters] = useState<CavadaLabsRecord>(() => initialFilters);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorDetail, setErrorDetail] = useState<CavadaLabsRecord | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [updateRow, setUpdateRow] = useState<CavadaLabsRecord | null>(null);
  const [detailsRow, setDetailsRow] = useState<CavadaLabsRecord | null>(null);
  const [operationResult, setOperationResult] = useState<OperationResult | null>(null);
  const mountedRef = useRef(true);
  const consumedInitialDetailsRef = useRef<string | null>(null);

  useEffect(() => {
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (createOpen) {
      createForm.setFieldsValue(getCreateInitialValues(config.createFields));
    }
  }, [config.createFields, createForm, createOpen]);

  useEffect(() => {
    if (updateRow) {
      updateForm.setFieldsValue(getUpdateInitialValues(updateRow, config.updateFields));
    }
  }, [config.updateFields, updateForm, updateRow]);

  useEffect(() => {
    setFilters(initialFilters);
    filterForm.setFieldsValue(initialFilters);
  }, [config.key, filterForm, initialFilterKey, initialFilters]);

  const missingFilters = requiredFiltersMissing(config, filters);

  const loadRows = useCallback(async () => {
    if (!accessToken || missingFilters.length > 0) {
      setRows([]);
      setCount(0);
      return;
    }

    setLoading(true);
    setError(null);
    setErrorDetail(null);
    try {
      const response = await listCavadaLabsResource<Record<string, any>>(accessToken, config.listPath, filters);
      if (!mountedRef.current) return;
      const nextRows = Array.isArray(response?.[config.responseKey]) ? response[config.responseKey] : [];
      setRows(nextRows);
      setCount(Number(response?.count ?? nextRows.length));
    } catch (err) {
      if (!mountedRef.current) return;
      const messageText = err instanceof Error ? err.message : String(err);
      setError(messageText);
      setErrorDetail(cavadaLabsErrorDetailFromUnknown(err));
      setRows([]);
      setCount(0);
    } finally {
      if (mountedRef.current) {
        setLoading(false);
      }
    }
  }, [accessToken, config.listPath, config.responseKey, filters, missingFilters.length]);

  useEffect(() => {
    loadRows();
  }, [loadRows]);

  const visibleRows = useMemo(() => rows.filter((row) => rowMatchesSearch(row, search)), [rows, search]);

  useEffect(() => {
    const requestedId = initialDetailsId?.trim();
    if (!requestedId) {
      consumedInitialDetailsRef.current = null;
      return;
    }

    const marker = `${config.key}:${requestedId}`;
    if (consumedInitialDetailsRef.current === marker || detailsRow) return;

    const matchedRow = rows.find((row) => String(row[config.rowKey]) === requestedId);
    if (!matchedRow) return;

    consumedInitialDetailsRef.current = marker;
    setDetailsRow(matchedRow);
  }, [config.key, config.rowKey, detailsRow, initialDetailsId, rows]);

  const executeRequest = useCallback(
    async (spec: { method: "POST" | "PATCH" | "DELETE"; path: string; body?: CavadaLabsRecord }) => {
      if (spec.method === "POST") return postCavadaLabsAction(accessToken, spec.path, spec.body ?? {});
      if (spec.method === "PATCH") return patchCavadaLabsResource(accessToken, spec.path, spec.body ?? {});
      if (spec.method === "DELETE") return deleteCavadaLabsResource(accessToken, spec.path);
      return cavadalabsRequest(accessToken, spec.path, { method: spec.method, body: spec.body });
    },
    [accessToken],
  );

  const showOperationError = useCallback(
    (err: unknown) => {
      const messageText = err instanceof Error ? err.message : String(err);
      setError(messageText);
      setErrorDetail(cavadaLabsErrorDetailFromUnknown(err));
      messageApi.error(messageText);
    },
    [messageApi],
  );

  const handleCreate = async () => {
    if (!config.createPath || !config.createFields) return;

    try {
      const values = await createForm.validateFields();
      const payload = normalizeFormPayload(values, config.createFields);
      setSubmitting(true);
      const response = await createCavadaLabsResource(accessToken, config.createPath, payload);
      messageApi.success(`${config.title} updated`);
      setCreateOpen(false);
      createForm.resetFields();
      setOperationResult({ title: config.createLabel ?? "Operation result", response });
      await loadRows();
      onMutated?.();
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      showOperationError(err);
    } finally {
      setSubmitting(false);
    }
  };

  const handleUpdate = async () => {
    if (!config.updatePath || !config.updateFields || !updateRow) return;

    try {
      const values = await updateForm.validateFields();
      const payload = normalizeFormPayload(values, config.updateFields);
      setSubmitting(true);
      const response = await patchCavadaLabsResource(accessToken, config.updatePath(updateRow), payload);
      messageApi.success(`${config.title} updated`);
      setUpdateRow(null);
      updateForm.resetFields();
      setOperationResult({ title: config.updateLabel ?? `Update ${config.title}`, response });
      await loadRows();
      onMutated?.();
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      showOperationError(err);
    } finally {
      setSubmitting(false);
    }
  };

  const runRowAction = useCallback(
    (action: CavadaLabsRowAction, row: CavadaLabsRecord) => {
      const execute = async () => {
        try {
          setSubmitting(true);
          const response = await executeRequest(action.request(row));
          messageApi.success(`${action.label} completed`);
          setOperationResult({ title: action.label, response });
          await loadRows();
          onMutated?.();
        } catch (err) {
          showOperationError(err);
        } finally {
          setSubmitting(false);
        }
      };

      if (action.confirmTitle) {
        modalApi.confirm({
          title: action.confirmTitle,
          content: action.confirmDescription,
          okButtonProps: { danger: action.danger },
          onOk: execute,
        });
        return;
      }
      execute();
    },
    [executeRequest, loadRows, messageApi, modalApi, onMutated],
  );

  const runToolbarAction = async (action: CavadaLabsToolbarAction) => {
    try {
      setSubmitting(true);
      const response = await executeRequest(action.request(filters));
      messageApi.success(`${action.label} completed`);
      setOperationResult({ title: action.label, response });
      await loadRows();
      onMutated?.();
    } catch (err) {
      showOperationError(err);
    } finally {
      setSubmitting(false);
    }
  };

  const columns = useMemo(
    () => buildColumns(config, setDetailsRow, setUpdateRow, runRowAction),
    [config, runRowAction],
  );

  const openCreate = () => {
    setCreateOpen(true);
  };

  return (
    <section className="rounded-md border border-gray-200 bg-white p-4">
      {messageContext}
      {modalContext}
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <Title level={4} className="!mb-1">
            {config.title}
          </Title>
          {config.description ? <Text type="secondary">{config.description}</Text> : null}
        </div>
        <Space wrap>
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="Search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            style={{ width: 220 }}
          />
          <Button icon={<ReloadOutlined />} onClick={loadRows} loading={loading}>
            Refresh
          </Button>
          {config.toolbarActions?.map((action) => (
            <Button
              key={action.key}
              icon={action.icon}
              onClick={() => runToolbarAction(action)}
              loading={submitting}
              disabled={action.disabled?.(filters, context)}
            >
              {action.label}
            </Button>
          ))}
          {config.createPath && config.createFields && config.canCreate?.(context) !== false ? (
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              {config.createLabel ?? "Create"}
            </Button>
          ) : null}
        </Space>
      </div>

      {config.filters && config.filters.length > 0 ? (
        <Form
          form={filterForm}
          layout="inline"
          className="mb-4 gap-y-2"
          onFinish={(values) => setFilters(emptyFilters(values))}
          initialValues={filters}
        >
          {config.filters.map((field) => (
            <Form.Item key={field.name} name={field.name} label={field.label}>
              {renderField(field)}
            </Form.Item>
          ))}
          <Form.Item>
            <Space>
              <Button htmlType="submit">Apply</Button>
              <Button
                onClick={() => {
                  filterForm.resetFields();
                  setFilters({});
                }}
              >
                Reset
              </Button>
            </Space>
          </Form.Item>
        </Form>
      ) : null}

      {missingFilters.length > 0 ? (
        <Alert
          type="info"
          showIcon
          className="mb-4"
          message={`Select ${missingFilters.join(", ")} to load ${config.title.toLowerCase()}.`}
        />
      ) : null}

      {error ? (
        <Alert
          type="error"
          showIcon
          className="mb-4"
          message={isCavadaLabsMissingSchemaDetail(errorDetail) ? "CavadaLabs schema is not ready" : error}
          description={
            isCavadaLabsMissingSchemaDetail(errorDetail) ? <MissingSchemaDescription detail={errorDetail} /> : undefined
          }
        />
      ) : null}

      <Table
        rowKey={(row) => String(row[config.rowKey])}
        columns={columns}
        dataSource={visibleRows}
        loading={loading}
        pagination={{ pageSize: 10, showSizeChanger: true, total: visibleRows.length }}
        scroll={{ x: "max-content" }}
        size="middle"
        title={() => (
          <Text type="secondary">
            {visibleRows.length} shown
            {count !== visibleRows.length ? ` of ${count}` : ""}
          </Text>
        )}
      />

      <Modal
        open={createOpen}
        title={config.createLabel ?? `Create ${config.title}`}
        onCancel={() => setCreateOpen(false)}
        onOk={handleCreate}
        confirmLoading={submitting}
        width={920}
        destroyOnHidden
      >
        <Form form={createForm} layout="vertical" initialValues={getCreateInitialValues(config.createFields)}>
          <div className="grid grid-cols-1 gap-x-4 md:grid-cols-2">
            {(config.createFields ?? []).map((field) => (
              <div key={field.name} className={field.fullWidth ? "md:col-span-2" : undefined}>
                <Form.Item
                  name={field.name}
                  label={field.label}
                  valuePropName={field.type === "switch" ? "checked" : "value"}
                  rules={field.required ? [{ required: true, message: `${field.label} is required` }] : undefined}
                >
                  {renderField(field)}
                </Form.Item>
              </div>
            ))}
          </div>
        </Form>
      </Modal>

      <Modal
        open={Boolean(updateRow)}
        title={config.updateLabel ?? `Edit ${config.title}`}
        onCancel={() => setUpdateRow(null)}
        onOk={handleUpdate}
        confirmLoading={submitting}
        width={920}
        destroyOnHidden
      >
        <Form form={updateForm} layout="vertical">
          <div className="grid grid-cols-1 gap-x-4 md:grid-cols-2">
            {(config.updateFields ?? []).map((field) => (
              <div key={field.name} className={field.fullWidth ? "md:col-span-2" : undefined}>
                <Form.Item
                  name={field.name}
                  label={field.label}
                  valuePropName={field.type === "switch" ? "checked" : "value"}
                  rules={field.required ? [{ required: true, message: `${field.label} is required` }] : undefined}
                >
                  {renderField(field)}
                </Form.Item>
              </div>
            ))}
          </div>
        </Form>
      </Modal>

      <Drawer
        open={Boolean(detailsRow)}
        title={`${config.title} details`}
        width={720}
        onClose={() => setDetailsRow(null)}
      >
        {config.key === "projects" && detailsRow ? (
          <ProjectDetailsView project={detailsRow} />
        ) : (
          <pre className="rounded border border-gray-200 bg-gray-50 p-3 text-xs">
            {JSON.stringify(detailsRow ?? {}, null, 2)}
          </pre>
        )}
        {config.key === "projects" && detailsRow ? (
          <CavadaLabsProjectMembersPanel
            accessToken={accessToken}
            project={detailsRow}
            canManage={detailsRow.cavadalabs_can_manage === true}
            onMutated={onMutated}
          />
        ) : null}
      </Drawer>

      <ResultModal result={operationResult} onClose={() => setOperationResult(null)} />
    </section>
  );
};

export default CavadaLabsResourcePanel;
