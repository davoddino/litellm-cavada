"use client";

import { ReloadOutlined, SyncOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Col, Empty, Input, Radio, Row, Select, Space, Statistic, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  cavadaLabsErrorDetailFromUnknown,
  cavadalabsMissingSchemaDiagnosticsFromDetail,
  getCavadaLabsDailyActivity,
  getCavadaLabsUsageDiagnostics,
  isCavadaLabsMissingSchemaDetail,
  repairCavadaLabsUsage,
} from "./api";
import type {
  CavadaLabsDailyActivityResponse,
  CavadaLabsDailyActivityResult,
  CavadaLabsRecord,
  CavadaLabsRuntimeContext,
  CavadaLabsUsageDiagnosticsEntityType,
  CavadaLabsUsageDiagnosticsResponse,
  CavadaLabsUsageRepairResponse,
} from "./types";
import { canManageCavadaLabsUsageScope } from "./usageScopeAccess";

const { Text, Title } = Typography;

interface CavadaLabsUsageActivityPanelProps {
  accessToken: string | null;
  context: CavadaLabsRuntimeContext;
}

const emptyActivity: CavadaLabsDailyActivityResponse = {
  results: [],
  metadata: {
    total_spend: 0,
    total_prompt_tokens: 0,
    total_completion_tokens: 0,
    total_tokens: 0,
    total_api_requests: 0,
    total_successful_requests: 0,
    total_failed_requests: 0,
    page: 1,
    total_pages: 1,
    has_more: false,
  },
};

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

const parseOptionalNumber = (value: string): number | undefined => {
  if (!value.trim()) return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
};

const formatCurrency = (value: number | undefined): string => `$${(value ?? 0).toFixed(4)}`;

const formatNumber = (value: number | undefined): string => (value ?? 0).toLocaleString();

const errorMessage = (err: unknown): string => (err instanceof Error ? err.message : String(err));

const detailMessage = (detail: CavadaLabsRecord): string =>
  String(detail.error || detail.message || "The selected Company/Project scope could not be loaded.");

const scopedBackfillDetails = (
  item: NonNullable<CavadaLabsUsageDiagnosticsResponse["diagnostics"]>[number],
): string[] => {
  const details = [`Attributable SpendLogs: ${item.attributable_spend_logs}`, `Ledger gap: ${item.ledger_gap}`];
  if (typeof item.metadata_spend_logs === "number") {
    details.push(`Direct metadata rows: ${item.metadata_spend_logs}`);
  }
  if (typeof item.key_metadata_spend_logs === "number") {
    details.push(`Key metadata rows: ${item.key_metadata_spend_logs}`);
  }
  if (typeof item.compatibility_spend_logs === "number") {
    details.push(`Compatibility mapping rows: ${item.compatibility_spend_logs}`);
  }
  if (typeof item.unmapped_spend_logs === "number") {
    details.push(`Unmapped legacy rows: ${item.unmapped_spend_logs}`);
  }
  return details;
};

const emptyUsageSummary = (
  diagnostics: CavadaLabsUsageDiagnosticsResponse | null,
  entityType: CavadaLabsUsageDiagnosticsEntityType,
  errorDetail: CavadaLabsRecord | null,
  canManageScope: boolean,
) => {
  const item = diagnostics?.diagnostics?.[0];
  const label = entityLabel(entityType);
  if (errorDetail?.schema_status === "missing_schema" || errorDetail?.migration_status === "schema_missing") {
    const missingSchema = Array.isArray(errorDetail.missing_schema)
      ? errorDetail.missing_schema
      : diagnostics?.missing_schema ?? [];
    return {
      type: "error" as const,
      message: "CavadaLabs usage schema is not ready",
      description:
        errorDetail.migration_command ||
        "Run the CavadaLabs Prisma migration deploy before reading or repairing Company/Project usage.",
      details: missingSchema.map((value: string) => `Missing schema: ${value}`),
    };
  }
  if (errorDetail) {
    return {
      type: "error" as const,
      message: `Cannot load ${label} usage for this scope`,
      description: detailMessage(errorDetail),
      details: [] as string[],
    };
  }
  if (diagnostics?.schema_status === "missing_schema" || diagnostics?.migration_status === "schema_missing") {
    return {
      type: "error" as const,
      message: "CavadaLabs usage schema is not ready",
      description:
        diagnostics.migration_command ||
        "Run the CavadaLabs Prisma migration deploy before reading or repairing Company/Project usage.",
      details: diagnostics.missing_schema?.map((value) => `Missing schema: ${value}`) ?? [],
    };
  }
  if (!item) {
    return {
      type: "info" as const,
      message: `No ${label} usage for this selection`,
      description: "No CavadaLabs ledger rows were returned for the selected date range and filters.",
      details: [] as string[],
    };
  }
  if (item.recommended_action === "run_scoped_backfill") {
    return {
      type: "warning" as const,
      message: `${label} usage can be repaired`,
      description: canManageScope
        ? "Spend exists for this Company/Project, but the CavadaLabs ledger is empty or partial. Preview or run scoped backfill for the selected filters."
        : "Spend exists for this Company/Project, but scoped backfill requires Company/Project admin access. Ask an administrator to run repair for this scope.",
      details: canManageScope
        ? scopedBackfillDetails(item)
        : [...scopedBackfillDetails(item), "Repair access: Company/Project admin required"],
    };
  }
  if (item.recommended_action === "fix_compatibility_mapping") {
    return {
      type: "error" as const,
      message: `${label} usage is not attributable yet`,
      description:
        "Fix the Company/Project mapping or key metadata before historical spend can appear in CavadaLabs usage.",
      details: item.missing_mappings.map((value) => `Missing mapping: ${value}`),
    };
  }
  if (item.recommended_action === "run_migration_backfill") {
    return {
      type: "warning" as const,
      message: "Historical backfill is required",
      description:
        diagnostics?.migration_command ||
        "Run the CavadaLabs usage migration before relying on this historical date range.",
      details: item.missing_schema?.map((value) => `Missing schema: ${value}`) ?? [],
    };
  }
  if (item.status === "filters_exclude_usage" || item.filters_exclude_usage || item.date_range_excludes_usage) {
    return {
      type: "warning" as const,
      message: `${label} usage is outside the current filters`,
      description: item.date_range_excludes_usage
        ? "Attributable spend exists outside the selected date range. Expand the date range to inspect it."
        : "Attributable spend exists for this Company/Project, but the model/provider/API key filters exclude it.",
      details: [
        `Attributable SpendLogs outside current filters: ${
          item.unfiltered_attributable_spend_logs ?? item.all_time_attributable_spend_logs ?? 0
        }`,
      ],
    };
  }
  if (item.status === "no_attributable_spend") {
    return {
      type: "info" as const,
      message: `No ${label}-attributable usage`,
      description:
        "No ledger rows, SpendLogs metadata, key metadata, or internal compatibility mapping matched this Company/Project scope.",
      details: [] as string[],
    };
  }
  return {
    type: "info" as const,
    message: `No ${label} usage for this selection`,
    description: "The ledger is healthy, but no usage matched the selected date range and filters.",
    details: [] as string[],
  };
};

const CavadaLabsUsageActivityPanel: React.FC<CavadaLabsUsageActivityPanelProps> = ({ accessToken, context }) => {
  const initialDateRange = useMemo(defaultDateRange, []);
  const [entityType, setEntityType] = useState<CavadaLabsUsageDiagnosticsEntityType>(
    context.companies.length > 0 || context.projects.length === 0 ? "company" : "project",
  );
  const [selectedEntityId, setSelectedEntityId] = useState<string | undefined>(undefined);
  const [startDate, setStartDate] = useState(initialDateRange.startDate);
  const [endDate, setEndDate] = useState(initialDateRange.endDate);
  const [model, setModel] = useState("");
  const [provider, setProvider] = useState("");
  const [status, setStatus] = useState<string | undefined>(undefined);
  const [apiKey, setApiKey] = useState("");
  const [minSpend, setMinSpend] = useState("");
  const [maxSpend, setMaxSpend] = useState("");
  const [activity, setActivity] = useState<CavadaLabsDailyActivityResponse>(emptyActivity);
  const [diagnostics, setDiagnostics] = useState<CavadaLabsUsageDiagnosticsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [repairing, setRepairing] = useState(false);
  const [previewingRepair, setPreviewingRepair] = useState(false);
  const [repairPreview, setRepairPreview] = useState<CavadaLabsUsageRepairResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorDetail, setErrorDetail] = useState<CavadaLabsRecord | null>(null);

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

  const loadUsage = useCallback(async () => {
    if (!accessToken || !selectedEntityId || !startDate || !endDate) return;
    setLoading(true);
    setError(null);
    setErrorDetail(null);
    try {
      const timezone = new Date().getTimezoneOffset();
      const [dailyActivityResult, diagnosticsResult] = await Promise.allSettled([
        getCavadaLabsDailyActivity(accessToken, {
          entityType,
          entityIds: [selectedEntityId],
          startDate,
          endDate,
          timezone,
          model: model.trim() || undefined,
          provider: provider.trim() || undefined,
          status,
          apiKey: apiKey.trim() || undefined,
          minSpend: parseOptionalNumber(minSpend),
          maxSpend: parseOptionalNumber(maxSpend),
        }),
        getCavadaLabsUsageDiagnostics(accessToken, {
          entityType,
          entityIds: [selectedEntityId],
          startDate,
          endDate,
          timezone,
          model: model.trim() || undefined,
          provider: provider.trim() || undefined,
          apiKey: apiKey.trim() || undefined,
        }),
      ]);

      const usageDiagnostics = diagnosticsResult.status === "fulfilled" ? diagnosticsResult.value : null;
      const dailyErrorDetail =
        dailyActivityResult.status === "rejected" ? cavadaLabsErrorDetailFromUnknown(dailyActivityResult.reason) : null;
      const diagnosticsErrorDetail =
        diagnosticsResult.status === "rejected" ? cavadaLabsErrorDetailFromUnknown(diagnosticsResult.reason) : null;
      setDiagnostics(
        usageDiagnostics ??
          (isCavadaLabsMissingSchemaDetail(diagnosticsErrorDetail)
            ? cavadalabsMissingSchemaDiagnosticsFromDetail(diagnosticsErrorDetail)
            : null),
      );

      if (dailyActivityResult.status === "fulfilled") {
        setActivity(dailyActivityResult.value);
      } else {
        setActivity(emptyActivity);
        const schemaMissing =
          usageDiagnostics?.schema_status === "missing_schema" ||
          usageDiagnostics?.migration_status === "schema_missing" ||
          dailyErrorDetail?.schema_status === "missing_schema" ||
          dailyErrorDetail?.migration_status === "schema_missing";
        if (!schemaMissing) {
          throw dailyActivityResult.reason;
        }
        setErrorDetail(dailyErrorDetail);
      }

      if (diagnosticsResult.status === "rejected") {
        setError(errorMessage(diagnosticsResult.reason));
        setErrorDetail(diagnosticsErrorDetail);
      }
      setRepairPreview(null);
    } catch (err) {
      setError(errorMessage(err));
      setErrorDetail(cavadaLabsErrorDetailFromUnknown(err));
    } finally {
      setLoading(false);
    }
  }, [
    accessToken,
    apiKey,
    endDate,
    entityType,
    maxSpend,
    minSpend,
    model,
    provider,
    selectedEntityId,
    startDate,
    status,
  ]);

  useEffect(() => {
    loadUsage();
  }, [loadUsage]);

  const hasUsage = (activity.metadata.total_api_requests ?? 0) > 0;
  const selectedScopeCanManage = canManageCavadaLabsUsageScope(context, entityType, selectedEntityId);
  const repairSchemaReady =
    diagnostics?.schema_status !== "missing_schema" && diagnostics?.migration_status !== "schema_missing";
  const repairableDiagnostic = repairSchemaReady
    ? diagnostics?.diagnostics.find(
        (item) =>
          item.entity_type === entityType &&
          item.entity_id === selectedEntityId &&
          item.recommended_action === "run_scoped_backfill" &&
          selectedScopeCanManage,
      )
    : undefined;
  const runScopedRepair = useCallback(
    async (dryRun = false) => {
      if (!accessToken || !selectedEntityId || !startDate || !endDate || !repairableDiagnostic) return;
      if (dryRun) {
        setPreviewingRepair(true);
      } else {
        setRepairing(true);
      }
      setError(null);
      setErrorDetail(null);
      try {
        const repair = await repairCavadaLabsUsage(accessToken, {
          entityType,
          entityIds: [selectedEntityId],
          startDate,
          endDate,
          timezone: new Date().getTimezoneOffset(),
          model: model.trim() || undefined,
          provider: provider.trim() || undefined,
          apiKey: apiKey.trim() || undefined,
          dryRun,
        });
        setRepairPreview(repair);
        if (!dryRun) {
          await loadUsage();
        }
      } catch (err) {
        setError(errorMessage(err));
        setErrorDetail(cavadaLabsErrorDetailFromUnknown(err));
      } finally {
        if (dryRun) {
          setPreviewingRepair(false);
        } else {
          setRepairing(false);
        }
      }
    },
    [
      accessToken,
      apiKey,
      endDate,
      entityType,
      loadUsage,
      model,
      provider,
      repairableDiagnostic,
      selectedEntityId,
      startDate,
    ],
  );
  const emptySummary =
    hasUsage || (loading && diagnostics === null && errorDetail === null)
      ? null
      : emptyUsageSummary(diagnostics, entityType, errorDetail, selectedScopeCanManage);

  const columns: ColumnsType<CavadaLabsDailyActivityResult> = [
    {
      title: "Date",
      dataIndex: "date",
      width: 130,
    },
    {
      title: "Spend",
      dataIndex: ["metrics", "spend"],
      width: 130,
      render: (value: number) => formatCurrency(value),
    },
    {
      title: "Requests",
      dataIndex: ["metrics", "api_requests"],
      width: 120,
      render: (value: number) => formatNumber(value),
    },
    {
      title: "Successful",
      dataIndex: ["metrics", "successful_requests"],
      width: 120,
      render: (value: number) => formatNumber(value),
    },
    {
      title: "Errors",
      dataIndex: ["metrics", "failed_requests"],
      width: 100,
      render: (value: number) => formatNumber(value),
    },
    {
      title: "Tokens",
      dataIndex: ["metrics", "total_tokens"],
      width: 130,
      render: (value: number) => formatNumber(value),
    },
    {
      title: "Prompt tokens",
      dataIndex: ["metrics", "prompt_tokens"],
      width: 140,
      render: (value: number) => formatNumber(value),
    },
    {
      title: "Completion tokens",
      dataIndex: ["metrics", "completion_tokens"],
      width: 160,
      render: (value: number) => formatNumber(value),
    },
  ];

  return (
    <Card size="small">
      <Space direction="vertical" size={16} className="w-full">
        <div>
          <Title level={4} className="!mb-1">
            Company/Project usage
          </Title>
          <Text type="secondary">View ledger-native CavadaLabs usage by Company or Project.</Text>
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
              aria-label={`${entityLabel(entityType)} usage scope`}
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
              aria-label="Usage start date"
              className="mt-2"
              type="date"
              value={startDate}
              onChange={(event) => setStartDate(event.target.value)}
            />
          </Col>
          <Col xs={12} md={4} xl={3}>
            <Text strong>End date</Text>
            <Input
              aria-label="Usage end date"
              className="mt-2"
              type="date"
              value={endDate}
              onChange={(event) => setEndDate(event.target.value)}
            />
          </Col>
          <Col xs={24} xl={4}>
            <Button
              icon={<ReloadOutlined />}
              onClick={loadUsage}
              loading={loading}
              disabled={!selectedEntityId || !startDate || !endDate}
            >
              Load usage
            </Button>
          </Col>
        </Row>

        <Row gutter={[12, 12]} align="bottom">
          <Col xs={24} md={8} xl={4}>
            <Text strong>Provider</Text>
            <Input
              aria-label="Provider filter"
              className="mt-2"
              placeholder="cavadalabs, openai..."
              value={provider}
              onChange={(event) => setProvider(event.target.value)}
            />
          </Col>
          <Col xs={24} md={8} xl={5}>
            <Text strong>Model</Text>
            <Input
              aria-label="Model filter"
              className="mt-2"
              placeholder="cavadalabs/qwen3-32b"
              value={model}
              onChange={(event) => setModel(event.target.value)}
            />
          </Col>
          <Col xs={24} md={8} xl={4}>
            <Text strong>Status</Text>
            <Select
              aria-label="Status filter"
              className="mt-2 w-full"
              allowClear
              options={[
                { label: "Success", value: "success" },
                { label: "Failure", value: "failure" },
                { label: "Error", value: "error" },
              ]}
              value={status}
              onChange={setStatus}
            />
          </Col>
          <Col xs={24} md={8} xl={4}>
            <Text strong>API key hash</Text>
            <Input
              aria-label="API key hash filter"
              className="mt-2"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
            />
          </Col>
          <Col xs={12} md={8} xl={3}>
            <Text strong>Min spend</Text>
            <Input
              aria-label="Minimum spend filter"
              className="mt-2"
              type="number"
              min={0}
              value={minSpend}
              onChange={(event) => setMinSpend(event.target.value)}
            />
          </Col>
          <Col xs={12} md={8} xl={3}>
            <Text strong>Max spend</Text>
            <Input
              aria-label="Maximum spend filter"
              className="mt-2"
              type="number"
              min={0}
              value={maxSpend}
              onChange={(event) => setMaxSpend(event.target.value)}
            />
          </Col>
        </Row>

        {error && !emptySummary ? <Alert type="error" showIcon message={error} /> : null}
        {emptySummary ? (
          <Alert
            showIcon
            type={emptySummary.type}
            message={emptySummary.message}
            description={
              <Space direction="vertical" size={8}>
                <span>{emptySummary.description}</span>
                {emptySummary.details.length > 0 ? (
                  <Space direction="vertical" size={2}>
                    {emptySummary.details.map((line) => (
                      <Text key={line} type="secondary">
                        {line}
                      </Text>
                    ))}
                  </Space>
                ) : null}
                {repairableDiagnostic ? (
                  <Space wrap>
                    <Button
                      icon={<SyncOutlined />}
                      onClick={() => runScopedRepair(true)}
                      loading={previewingRepair}
                      disabled={!selectedEntityId || !startDate || !endDate || repairing}
                    >
                      Preview scoped backfill
                    </Button>
                    <Button
                      type="primary"
                      icon={<SyncOutlined />}
                      onClick={() => runScopedRepair(false)}
                      loading={repairing}
                      disabled={!selectedEntityId || !startDate || !endDate || previewingRepair}
                    >
                      Run scoped backfill
                    </Button>
                  </Space>
                ) : null}
              </Space>
            }
          />
        ) : null}
        {repairPreview?.dry_run ? (
          <Alert
            showIcon
            type="info"
            message="Scoped backfill preview"
            description={`${repairPreview.scoped_spend_logs} attributable SpendLogs match this Company/Project scope. Apply scoped backfill to mirror them into the CavadaLabs usage ledger.`}
          />
        ) : null}

        <Row gutter={[12, 12]}>
          <Col xs={12} md={6}>
            <Card size="small">
              <Statistic title="Spend" value={activity.metadata.total_spend ?? 0} precision={4} prefix="$" />
            </Card>
          </Col>
          <Col xs={12} md={6}>
            <Card size="small">
              <Statistic title="Requests" value={activity.metadata.total_api_requests ?? 0} />
            </Card>
          </Col>
          <Col xs={12} md={6}>
            <Card size="small">
              <Statistic title="Tokens" value={activity.metadata.total_tokens ?? 0} />
            </Card>
          </Col>
          <Col xs={12} md={6}>
            <Card size="small">
              <Statistic title="Errors" value={activity.metadata.total_failed_requests ?? 0} />
            </Card>
          </Col>
        </Row>

        {options.length === 0 ? (
          <Empty description={`No ${entityLabel(entityType).toLowerCase()} records available`} />
        ) : (
          <Table
            size="small"
            rowKey={(row) => row.date}
            columns={columns}
            dataSource={activity.results}
            loading={loading}
            pagination={false}
            scroll={{ x: 1030 }}
          />
        )}
      </Space>
    </Card>
  );
};

export default CavadaLabsUsageActivityPanel;
