import type React from "react";

export type CavadaLabsRecord = Record<string, any>;

export type CavadaLabsFieldType =
  | "text"
  | "textarea"
  | "number"
  | "select"
  | "multiSelect"
  | "tags"
  | "json"
  | "switch"
  | "date";

export interface CavadaLabsSelectOption {
  label: string;
  value: string | number | boolean;
}

export interface CavadaLabsFieldConfig {
  name: string;
  label: string;
  type: CavadaLabsFieldType;
  required?: boolean;
  placeholder?: string;
  options?: CavadaLabsSelectOption[];
  defaultValue?: any;
  min?: number;
  max?: number;
  step?: number;
  rows?: number;
  fullWidth?: boolean;
  emptyValue?: "omit" | "null" | "emptyString";
}

export type CavadaLabsColumnType =
  | "text"
  | "id"
  | "status"
  | "tags"
  | "number"
  | "currency"
  | "boolean"
  | "datetime"
  | "json";

export interface CavadaLabsColumnConfig {
  key: string;
  title: string;
  dataIndex?: string;
  type?: CavadaLabsColumnType;
  width?: number;
  render?: (value: any, row: CavadaLabsRecord) => React.ReactNode;
}

export interface CavadaLabsRuntimeContext {
  companies: CavadaLabsRecord[];
  projects: CavadaLabsRecord[];
  chatbots: CavadaLabsRecord[];
  ragCollections: CavadaLabsRecord[];
  nodes: CavadaLabsRecord[];
}

export interface CavadaLabsRequestSpec {
  method: "POST" | "PATCH" | "DELETE";
  path: string;
  body?: CavadaLabsRecord;
}

export interface CavadaLabsRowAction {
  key: string;
  label: string;
  icon?: React.ReactNode;
  danger?: boolean;
  confirmTitle?: string;
  confirmDescription?: string;
  request: (row: CavadaLabsRecord) => CavadaLabsRequestSpec;
}

export interface CavadaLabsToolbarAction {
  key: string;
  label: string;
  icon?: React.ReactNode;
  request: (filters: CavadaLabsRecord) => CavadaLabsRequestSpec;
  disabled?: (filters: CavadaLabsRecord, context: CavadaLabsRuntimeContext) => boolean;
}

export interface CavadaLabsResourceConfig {
  key: string;
  title: string;
  description?: string;
  listPath: string;
  responseKey: string;
  rowKey: string;
  createPath?: string;
  createLabel?: string;
  createFields?: CavadaLabsFieldConfig[];
  filters?: CavadaLabsFieldConfig[];
  requiredFilters?: string[];
  getInitialFilters?: (context: CavadaLabsRuntimeContext) => CavadaLabsRecord;
  columns: CavadaLabsColumnConfig[];
  rowActions?: CavadaLabsRowAction[];
  toolbarActions?: CavadaLabsToolbarAction[];
}
