import { Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { CavadaLabsRecord } from "./types";

const { Text } = Typography;

export interface CavadaLabsUsageBreakdownRow {
  key: string;
  category: string;
  name: string;
  requests: number;
  spend: number;
  tokens: number;
}

const metricsFor = (value: CavadaLabsRecord): CavadaLabsRecord => {
  const metrics = value?.metrics;
  return metrics && typeof metrics === "object" ? metrics : {};
};

const numberValue = (value: unknown): number => (typeof value === "number" && Number.isFinite(value) ? value : 0);

const formatCurrency = (value: number): string => `$${value.toFixed(4)}`;

const formatNumber = (value: number): string => value.toLocaleString();

export const cavadaLabsUsageBreakdownRows = (
  breakdown: CavadaLabsRecord | undefined,
  entityLabel: string,
): CavadaLabsUsageBreakdownRow[] => {
  const sections: Array<{ key: string; label: string }> = [
    { key: "entities", label: entityLabel },
    { key: "models", label: "Model" },
    { key: "model_groups", label: "Model group" },
    { key: "providers", label: "Provider" },
    { key: "api_keys", label: "API key" },
    { key: "endpoints", label: "Endpoint" },
  ];

  return sections.flatMap((section) => {
    const rows = breakdown?.[section.key];
    if (!rows || typeof rows !== "object") return [];
    return Object.entries(rows)
      .map(([name, value]) => {
        const metrics = metricsFor(value as CavadaLabsRecord);
        return {
          key: `${section.key}:${name}`,
          category: section.label,
          name,
          requests: numberValue(metrics.api_requests),
          spend: numberValue(metrics.spend),
          tokens: numberValue(metrics.total_tokens),
        };
      })
      .sort((left, right) => right.spend - left.spend || left.name.localeCompare(right.name));
  });
};

interface CavadaLabsUsageBreakdownProps {
  breakdown: CavadaLabsRecord | undefined;
  entityLabel: string;
}

const columns: ColumnsType<CavadaLabsUsageBreakdownRow> = [
  {
    title: "Breakdown",
    dataIndex: "category",
    width: 140,
  },
  {
    title: "Name",
    dataIndex: "name",
    render: (value: string, row) => (row.category === "API key" ? <Text code>{value}</Text> : value),
  },
  {
    title: "Spend",
    dataIndex: "spend",
    width: 120,
    render: (value: number) => formatCurrency(value),
  },
  {
    title: "Requests",
    dataIndex: "requests",
    width: 110,
    render: (value: number) => formatNumber(value),
  },
  {
    title: "Tokens",
    dataIndex: "tokens",
    width: 110,
    render: (value: number) => formatNumber(value),
  },
];

const CavadaLabsUsageBreakdown = ({ breakdown, entityLabel }: CavadaLabsUsageBreakdownProps) => {
  const rows = cavadaLabsUsageBreakdownRows(breakdown, entityLabel);
  if (rows.length === 0) {
    return <Text type="secondary">No breakdown data returned for this day.</Text>;
  }

  return <Table size="small" rowKey="key" columns={columns} dataSource={rows} pagination={false} scroll={{ x: 720 }} />;
};

export default CavadaLabsUsageBreakdown;
