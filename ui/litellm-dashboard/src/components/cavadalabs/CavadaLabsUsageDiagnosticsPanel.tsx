"use client";

import { ReloadOutlined, SyncOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Col, Empty, Input, Radio, Row, Select, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  cavadaLabsErrorDetailFromUnknown,
  cavadalabsMissingSchemaDiagnosticsFromDetail,
  getCavadaLabsUsageDiagnostics,
  isCavadaLabsMissingSchemaDetail,
  repairCavadaLabsUsage,
} from "./api";
import type {
  CavadaLabsRecord,
  CavadaLabsRuntimeContext,
  CavadaLabsUsageDiagnosticsAction,
  CavadaLabsUsageDiagnosticsEntityType,
  CavadaLabsUsageDiagnosticsItem,
  CavadaLabsUsageDiagnosticsResponse,
  CavadaLabsUsageDiagnosticsStatus,
} from "./types";
import { canManageCavadaLabsUsageScope } from "./usageScopeAccess";
import { statusColor } from "./utils";

const { Text, Title } = Typography;

interface CavadaLabsUsageDiagnosticsPanelProps {
  accessToken: string | null;
  context: CavadaLabsRuntimeContext;
}

const dateInputValue = (date: Date): string => date.toISOString().slice(0, 10);

const defaultDateRange = (): { startDate: string; endDate: string } => {
  const end = new Date();
  const start = new Date(end);
  start.setDate(start.getDate() - 29);
  return {
    startDate: dateInputValue(start),
    endDate: dateInputValue(end),
  };
};

const displayLabel = (value: string): string => value.replaceAll("_", " ");

const entityLabel = (entityType: CavadaLabsUsageDiagnosticsEntityType): string =>
  entityType === "company" ? "Company" : "Project";

const optionLabel = (row: CavadaLabsRecord, entityType: CavadaLabsUsageDiagnosticsEntityType): string => {
  if (entityType === "company") {
    return row.legal_name ? `${row.legal_name} (${row.company_id})` : String(row.company_id);
  }
  return row.name ? `${row.name} (${row.project_id})` : String(row.project_id);
};

const entityOptions = (context: CavadaLabsRuntimeContext, entityType: CavadaLabsUsageDiagnosticsEntityType) =>
  (entityType === "company" ? context.companies : context.projects)
    .map((row) => {
      const value = entityType === "company" ? row.company_id : row.project_id;
      if (!value) return null;
      return {
        label: optionLabel(row, entityType),
        value: String(value),
      };
    })
    .filter((option): option is { label: string; value: string } => option !== null);

const missingMappingLabel = (value: string): string => {
  const normalized = value.toLowerCase();
  if (normalized.includes("company") && normalized.includes("key metadata")) {
    return "Company compatibility mapping or key metadata";
  }
  if (normalized.includes("project") && normalized.includes("key metadata")) {
    return "Project compatibility mapping or key metadata";
  }
  if (normalized.includes("company row")) {
    return "Company record";
  }
  if (normalized.includes("project row")) {
    return "Project record";
  }
  return value
    .replaceAll("litellm_organization_id", "internal company mapping")
    .replaceAll("litellm_team_id", "internal project mapping");
};

const actionLabel = (action: CavadaLabsUsageDiagnosticsAction): string => {
  switch (action) {
    case "run_scoped_backfill":
      return "Run scoped backfill";
    case "run_migration_backfill":
      return "Run migration backfill";
    case "fix_compatibility_mapping":
      return "Fix Company/Project mapping";
    default:
      return "No action";
  }
};

const sanitizedMessage = (item: CavadaLabsUsageDiagnosticsItem): string => {
  switch (item.status) {
    case "visible":
      return `${entityLabel(item.entity_type)} usage is visible for the selected date range.`;
    case "scoped_backfill_available":
      return (
        `${entityLabel(item.entity_type)} usage exists in LiteLLM spend logs, but the CavadaLabs ledger is ` +
        "empty or partial. Daily usage and billing endpoints can run a scoped repair for this selection."
      );
    case "backfill_required":
      return "Run the CavadaLabs usage migration before relying on full-period billing.";
    case "missing_compatibility_mapping":
      return "Fix the Company/Project compatibility mapping or key metadata before usage can be attributed.";
    case "filters_exclude_usage":
      if (item.date_range_excludes_usage) {
        return "Attributable Company/Project spend exists outside the selected date range.";
      }
      return "Attributable Company/Project spend exists, but the selected filters exclude it.";
    default:
      return "No Company/Project-attributable spend exists for the selected date range.";
  }
};

const summaryFor = (response: CavadaLabsUsageDiagnosticsResponse | null) => {
  if (response === null) {
    return {
      type: "info" as const,
      message: "Select a Company or Project to inspect usage attribution",
      description: "Diagnostics compare CavadaLabs ledger rows with LiteLLM spend rows for the selected scope.",
    };
  }
  if (response.schema_status === "missing_schema" || response.migration_status === "schema_missing") {
    return {
      type: "error" as const,
      message: "CavadaLabs usage schema is not ready",
      description:
        "The request ledger schema or migration is missing. Run the migration command before scoped repair or billing verification.",
    };
  }
  const diagnostics = response.diagnostics;
  if (diagnostics.length === 0) {
    return {
      type: "info" as const,
      message: "No diagnostics returned for this scope",
      description: "The selected Company/Project scope returned no diagnostic rows for the current date range.",
    };
  }
  if (diagnostics.some((item) => item.recommended_action === "fix_compatibility_mapping")) {
    return {
      type: "error" as const,
      message: "Company/Project mapping is incomplete",
      description:
        "Usage is intentionally hidden until the selected scope has a valid Company/Project compatibility mapping or key metadata.",
    };
  }
  if (diagnostics.some((item) => item.recommended_action === "run_scoped_backfill")) {
    return {
      type: "warning" as const,
      message: "Scoped backfill is available",
      description:
        "Run scoped backfill for this Company/Project date range, or run the migration command for a full historical repair.",
    };
  }
  if (diagnostics.some((item) => item.recommended_action === "run_migration_backfill")) {
    return {
      type: "warning" as const,
      message: "Historical migration backfill is required",
      description: "Run the CavadaLabs usage migration before relying on full historical billing.",
    };
  }
  if (diagnostics.some((item) => item.status === "filters_exclude_usage")) {
    return {
      type: "warning" as const,
      message: "Current filters hide attributable usage",
      description:
        "Company/Project spend is attributable, but the selected date range or filters exclude it. Adjust the scope before running repair.",
    };
  }
  if (diagnostics.some((item) => item.status === "no_attributable_spend")) {
    return {
      type: "info" as const,
      message: "No Company/Project-attributable spend",
      description:
        "No ledger rows, SpendLogs metadata, key metadata, or internal compatibility mapping matched this Company/Project scope.",
    };
  }
  return {
    type: "success" as const,
    message: "Usage attribution is healthy",
    description: "CavadaLabs ledger data covers the selected Company/Project scope.",
  };
};

const migrationPlanFor = (response: CavadaLabsUsageDiagnosticsResponse | null) => {
  const plan = response?.migration_plan ?? [];
  if (plan.length > 0) return plan;
  return (response?.migration_names ?? []).map((name) => ({
    name,
    purpose: "CavadaLabs usage migration",
  }));
};

const CavadaLabsUsageDiagnosticsPanel: React.FC<CavadaLabsUsageDiagnosticsPanelProps> = ({ accessToken, context }) => {
  const initialDateRange = useMemo(defaultDateRange, []);
  const [entityType, setEntityType] = useState<CavadaLabsUsageDiagnosticsEntityType>(
    context.companies.length > 0 || context.projects.length === 0 ? "company" : "project",
  );
  const [selectedEntityId, setSelectedEntityId] = useState<string | undefined>(undefined);
  const [startDate, setStartDate] = useState(initialDateRange.startDate);
  const [endDate, setEndDate] = useState(initialDateRange.endDate);
  const [response, setResponse] = useState<CavadaLabsUsageDiagnosticsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [repairingEntityId, setRepairingEntityId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const options = useMemo(() => entityOptions(context, entityType), [context, entityType]);

  useEffect(() => {
    if (entityType === "company" && context.companies.length === 0 && context.projects.length > 0) {
      setEntityType("project");
      return;
    }
    if (entityType === "project" && context.projects.length === 0 && context.companies.length > 0) {
      setEntityType("company");
    }
  }, [context.companies.length, context.projects.length, entityType]);

  useEffect(() => {
    if (selectedEntityId && options.some((option) => option.value === selectedEntityId)) return;
    setSelectedEntityId(options[0]?.value);
  }, [options, selectedEntityId]);

  const loadDiagnostics = useCallback(async () => {
    if (!accessToken || !selectedEntityId || !startDate || !endDate) return;
    setLoading(true);
    setError(null);
    try {
      const diagnostics = await getCavadaLabsUsageDiagnostics(accessToken, {
        entityType,
        entityIds: [selectedEntityId],
        startDate,
        endDate,
        timezone: new Date().getTimezoneOffset(),
      });
      setResponse(diagnostics);
    } catch (err) {
      const detail = cavadaLabsErrorDetailFromUnknown(err);
      if (isCavadaLabsMissingSchemaDetail(detail)) {
        setResponse(cavadalabsMissingSchemaDiagnosticsFromDetail(detail));
        setError(null);
      } else {
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      setLoading(false);
    }
  }, [accessToken, endDate, entityType, selectedEntityId, startDate]);

  useEffect(() => {
    loadDiagnostics();
  }, [loadDiagnostics]);

  const runScopedRepair = useCallback(
    async (item: CavadaLabsUsageDiagnosticsItem) => {
      if (!accessToken || !startDate || !endDate) return;
      setRepairingEntityId(item.entity_id);
      setError(null);
      try {
        const repair = await repairCavadaLabsUsage(accessToken, {
          entityType: item.entity_type,
          entityIds: [item.entity_id],
          startDate,
          endDate,
          timezone: new Date().getTimezoneOffset(),
        });
        setResponse({
          diagnostics: repair.diagnostics,
          migration_name: repair.migration_name,
          migration_command: repair.migration_command,
          schema_status: repair.schema_status,
          migration_status: repair.migration_status,
          missing_schema: repair.missing_schema,
          migration_names: repair.migration_names,
          migration_plan: repair.migration_plan,
        });
      } catch (err) {
        const detail = cavadaLabsErrorDetailFromUnknown(err);
        if (isCavadaLabsMissingSchemaDetail(detail)) {
          setResponse(cavadalabsMissingSchemaDiagnosticsFromDetail(detail));
          setError(null);
        } else {
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        setRepairingEntityId(null);
      }
    },
    [accessToken, endDate, startDate],
  );

  const summary = summaryFor(response);
  const migrationPlan = migrationPlanFor(response);
  const diagnostics = response?.diagnostics ?? [];
  const repairSchemaReady =
    response?.schema_status !== "missing_schema" && response?.migration_status !== "schema_missing";
  const selectedScopeCanManage = canManageCavadaLabsUsageScope(context, entityType, selectedEntityId);

  const columns: ColumnsType<CavadaLabsUsageDiagnosticsItem> = [
    {
      title: "Scope",
      dataIndex: "entity_type",
      width: 110,
      render: (value: CavadaLabsUsageDiagnosticsEntityType) => entityLabel(value),
    },
    {
      title: "ID",
      dataIndex: "entity_id",
      width: 220,
      render: (value: string) => <Text code>{value}</Text>,
    },
    {
      title: "Status",
      dataIndex: "status",
      width: 190,
      render: (value: CavadaLabsUsageDiagnosticsStatus) => <Tag color={statusColor(value)}>{displayLabel(value)}</Tag>,
    },
    {
      title: "Ledger rows",
      dataIndex: "ledger_rows",
      width: 120,
    },
    {
      title: "Attributed spend rows",
      dataIndex: "attributable_spend_logs",
      width: 170,
    },
    {
      title: "Direct metadata",
      dataIndex: "metadata_spend_logs",
      width: 140,
      render: (value?: number) => value ?? 0,
    },
    {
      title: "Compat mapping",
      dataIndex: "compatibility_spend_logs",
      width: 145,
      render: (value?: number) => value ?? 0,
    },
    {
      title: "Key metadata",
      dataIndex: "key_metadata_spend_logs",
      width: 135,
      render: (value?: number) => value ?? 0,
    },
    {
      title: "Unmapped candidates",
      dataIndex: "unmapped_spend_logs",
      width: 165,
      render: (value?: number) => value ?? 0,
    },
    {
      title: "Ledger gap",
      dataIndex: "ledger_gap",
      width: 120,
    },
    {
      title: "Recommended action",
      dataIndex: "recommended_action",
      width: 190,
      render: (value: CavadaLabsUsageDiagnosticsAction) => actionLabel(value),
    },
    {
      title: "Missing mappings",
      dataIndex: "missing_mappings",
      width: 260,
      render: (values: string[]) =>
        values.length > 0 ? (
          <Space wrap size={[4, 4]}>
            {values.map((value) => (
              <Tag key={value} color="red">
                {missingMappingLabel(value)}
              </Tag>
            ))}
          </Space>
        ) : (
          "-"
        ),
    },
    {
      title: "Message",
      key: "message",
      render: (_, row) => sanitizedMessage(row),
    },
    {
      title: "Repair",
      key: "repair",
      width: 160,
      render: (_, row) =>
        repairSchemaReady && selectedScopeCanManage && row.recommended_action === "run_scoped_backfill" ? (
          <Button
            size="small"
            icon={<SyncOutlined />}
            loading={repairingEntityId === row.entity_id}
            disabled={!accessToken || !startDate || !endDate}
            onClick={() => runScopedRepair(row)}
          >
            Run scoped backfill
          </Button>
        ) : row.recommended_action === "run_scoped_backfill" && !selectedScopeCanManage ? (
          <Text type="secondary">Admin required</Text>
        ) : (
          "-"
        ),
    },
  ];

  return (
    <Card size="small">
      <Space direction="vertical" size={16} className="w-full">
        <div>
          <Title level={4} className="!mb-1">
            Usage diagnostics
          </Title>
          <Text type="secondary">Inspect Company/Project attribution before relying on usage and billing reports.</Text>
        </div>

        <Row gutter={[12, 12]} align="bottom">
          <Col xs={24} md={6} xl={4}>
            <Text strong>Scope</Text>
            <Radio.Group
              className="mt-2 flex"
              value={entityType}
              onChange={(event) => setEntityType(event.target.value)}
              optionType="button"
              buttonStyle="solid"
              options={[
                { label: "Company", value: "company" },
                { label: "Project", value: "project" },
              ]}
            />
          </Col>
          <Col xs={24} md={10} xl={8}>
            <Text strong>{entityLabel(entityType)}</Text>
            <Select
              aria-label={entityLabel(entityType)}
              className="mt-2 w-full"
              showSearch
              optionFilterProp="label"
              placeholder={`Select ${entityLabel(entityType)}`}
              options={options}
              value={selectedEntityId}
              onChange={setSelectedEntityId}
            />
          </Col>
          <Col xs={12} md={4} xl={3}>
            <Text strong>Start date</Text>
            <Input
              aria-label="Start date"
              className="mt-2"
              type="date"
              value={startDate}
              onChange={(event) => setStartDate(event.target.value)}
            />
          </Col>
          <Col xs={12} md={4} xl={3}>
            <Text strong>End date</Text>
            <Input
              aria-label="End date"
              className="mt-2"
              type="date"
              value={endDate}
              onChange={(event) => setEndDate(event.target.value)}
            />
          </Col>
          <Col xs={24} xl={4}>
            <Button
              icon={<ReloadOutlined />}
              onClick={loadDiagnostics}
              loading={loading}
              disabled={!selectedEntityId || !startDate || !endDate}
            >
              Check diagnostics
            </Button>
          </Col>
        </Row>

        {error ? <Alert type="error" showIcon message={error} /> : null}

        <Alert
          showIcon
          type={summary.type}
          message={summary.message}
          description={
            <Space direction="vertical" size={4}>
              <span>{summary.description}</span>
              {migrationPlan.length > 0 ? (
                <Space direction="vertical" size={2}>
                  {migrationPlan.map((step) => (
                    <span key={step.name}>
                      <Text code>{step.name}</Text>
                      <Text type="secondary"> {step.purpose}</Text>
                    </span>
                  ))}
                </Space>
              ) : null}
              {response?.migration_command ? (
                <Text code copyable>
                  {response.migration_command}
                </Text>
              ) : null}
            </Space>
          }
        />

        {options.length === 0 ? (
          <Empty description={`No ${entityLabel(entityType).toLowerCase()} records available`} />
        ) : (
          <Table
            size="small"
            rowKey={(row) => `${row.entity_type}-${row.entity_id}`}
            columns={columns}
            dataSource={diagnostics}
            loading={loading}
            pagination={false}
            scroll={{ x: 1360 }}
          />
        )}
      </Space>
    </Card>
  );
};

export default CavadaLabsUsageDiagnosticsPanel;
