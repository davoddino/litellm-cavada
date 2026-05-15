import type { CavadaLabsFieldConfig, CavadaLabsRecord, CavadaLabsSelectOption } from "./types";

export const statusColor = (status: unknown): string => {
  switch (String(status ?? "").toLowerCase()) {
    case "active":
    case "online":
    case "available":
    case "loaded":
    case "indexed":
    case "published":
    case "production":
    case "generated":
    case "completed":
    case "allow":
      return "green";
    case "queued":
    case "pending":
    case "draft":
    case "dev":
    case "received":
    case "locking":
    case "loading":
    case "identity_verification":
    case "in_progress":
    case "waiting_customer":
    case "review":
      return "gold";
    case "disabled":
    case "archived":
    case "released":
    case "expired":
    case "deleted":
    case "void":
    case "cancelled":
      return "default";
    case "failed":
    case "offline":
    case "unhealthy":
    case "suspended":
    case "revoked":
    case "rejected":
    case "block":
    case "prohibited":
      return "red";
    case "degraded":
    case "draining":
    case "redact":
    case "log_only":
    case "high":
      return "orange";
    default:
      return "blue";
  }
};

export const formatDateTime = (value: unknown): string => {
  if (!value) return "-";
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
};

export const formatNumber = (value: unknown): string => {
  if (value === null || value === undefined || value === "") return "-";
  const numberValue = Number(value);
  if (Number.isNaN(numberValue)) return String(value);
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 4 }).format(numberValue);
};

export const formatCurrency = (value: unknown, currency = "EUR"): string => {
  if (value === null || value === undefined || value === "") return "-";
  const numberValue = Number(value);
  if (Number.isNaN(numberValue)) return String(value);
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
    maximumFractionDigits: 4,
  }).format(numberValue);
};

export const toOptions = (rows: CavadaLabsRecord[], idKey: string, labelKey: string): CavadaLabsSelectOption[] =>
  rows
    .filter((row) => row[idKey])
    .map((row) => ({
      value: String(row[idKey]),
      label: row[labelKey] ? `${row[labelKey]} (${row[idKey]})` : String(row[idKey]),
    }));

export const enumOptions = (values: string[]): CavadaLabsSelectOption[] =>
  values.map((value) => ({
    value,
    label: value.replaceAll("_", " "),
  }));

const isEmpty = (value: unknown): boolean =>
  value === undefined || value === null || value === "" || (Array.isArray(value) && value.length === 0);

const normalizeDateValue = (value: any): string | undefined => {
  if (!value) return undefined;
  if (typeof value?.toISOString === "function") {
    return value.toISOString();
  }
  const date = new Date(String(value));
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString();
};

const parseJsonValue = (field: CavadaLabsFieldConfig, value: unknown): unknown => {
  if (value === undefined || value === null || value === "") {
    return field.emptyValue === "null" ? null : undefined;
  }
  if (typeof value !== "string") return value;
  return JSON.parse(value);
};

export const normalizeFormPayload = (
  rawValues: CavadaLabsRecord,
  fields: CavadaLabsFieldConfig[],
): CavadaLabsRecord => {
  const payload: CavadaLabsRecord = {};
  const fieldsByName = new Map(fields.map((field) => [field.name, field]));

  Object.entries(rawValues).forEach(([key, rawValue]) => {
    const field = fieldsByName.get(key);
    let value = rawValue;

    if (field?.type === "json") {
      value = parseJsonValue(field, rawValue);
    } else if (field?.type === "date") {
      value = normalizeDateValue(rawValue);
    } else if (field?.type === "number" && rawValue !== undefined && rawValue !== null && rawValue !== "") {
      value = Number(rawValue);
    } else if ((field?.type === "tags" || field?.type === "multiSelect") && Array.isArray(rawValue)) {
      value = rawValue.map((item) => String(item).trim()).filter(Boolean);
    } else if (typeof rawValue === "string") {
      value = rawValue.trim();
    }

    if (field?.emptyValue === "emptyString" && value === undefined) {
      payload[key] = "";
      return;
    }
    if (!isEmpty(value)) {
      payload[key] = value;
    }
  });

  fields.forEach((field) => {
    if (payload[field.name] !== undefined || field.defaultValue === undefined) return;
    if (field.type === "json") {
      payload[field.name] = field.defaultValue;
    }
  });

  return payload;
};

export const getFieldInitialValue = (field: CavadaLabsFieldConfig): any => {
  if (field.defaultValue === undefined) {
    if (field.type === "json") return "";
    return undefined;
  }
  if (field.type === "json") {
    return JSON.stringify(field.defaultValue, null, 2);
  }
  return field.defaultValue;
};

export const getCreateInitialValues = (fields: CavadaLabsFieldConfig[] = []): CavadaLabsRecord => {
  const values: CavadaLabsRecord = {};
  fields.forEach((field) => {
    const value = getFieldInitialValue(field);
    if (value !== undefined) values[field.name] = value;
  });
  return values;
};

export const rowMatchesSearch = (row: CavadaLabsRecord, search: string): boolean => {
  const needle = search.trim().toLowerCase();
  if (!needle) return true;
  return JSON.stringify(row).toLowerCase().includes(needle);
};

export const extractOperationSecret = (response: any): { label: string; value: string } | null => {
  if (typeof response?.token === "string") {
    return { label: "Web token", value: response.token };
  }
  if (typeof response?.enrollment_secret === "string") {
    return { label: "Enrollment secret", value: response.enrollment_secret };
  }
  return null;
};
