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
  availableModels?: string[];
}

export type CavadaLabsUsageDiagnosticsEntityType = "company" | "project";

export type CavadaLabsUsageDiagnosticsStatus =
  | "visible"
  | "backfill_required"
  | "scoped_backfill_available"
  | "missing_compatibility_mapping"
  | "no_attributable_spend"
  | "filters_exclude_usage";

export type CavadaLabsUsageDiagnosticsAction =
  | "none"
  | "run_scoped_backfill"
  | "run_migration_backfill"
  | "fix_compatibility_mapping";

export type CavadaLabsUsageReadinessCheckStatus = "ready" | "warning" | "action_required" | "blocked";

export interface CavadaLabsUsageReadinessCheck {
  code: string;
  status: CavadaLabsUsageReadinessCheckStatus;
  message: string;
  entity_type?: CavadaLabsUsageDiagnosticsEntityType;
  entity_id?: string;
  recommended_action?: CavadaLabsUsageDiagnosticsAction;
  details?: CavadaLabsRecord;
}

export interface CavadaLabsUsageDiagnosticsItem {
  entity_type: CavadaLabsUsageDiagnosticsEntityType;
  entity_id: string;
  status: CavadaLabsUsageDiagnosticsStatus;
  ledger_rows: number;
  attributable_spend_logs: number;
  metadata_spend_logs?: number;
  compatibility_spend_logs?: number;
  key_metadata_spend_logs?: number;
  legacy_keys_missing_metadata?: number;
  legacy_key_spend_logs?: number;
  unmapped_spend_logs?: number;
  unfiltered_attributable_spend_logs?: number;
  all_time_attributable_spend_logs?: number;
  ledger_gap: number;
  missing_ledger_rows?: number;
  recommended_action: CavadaLabsUsageDiagnosticsAction;
  scoped_backfill_available: boolean;
  filters_exclude_usage?: boolean;
  date_range_excludes_usage?: boolean;
  missing_mappings: string[];
  missing_schema?: string[];
  message: string;
}

export type CavadaLabsUsageSchemaStatus = "ready" | "missing_schema";

export type CavadaLabsUsageMigrationStatus = "ready" | "schema_missing" | "backfill_pending" | "backfill_required";

export interface CavadaLabsUsageDiagnosticsResponse {
  diagnostics: CavadaLabsUsageDiagnosticsItem[];
  migration_name: string;
  migration_command: string;
  schema_status?: CavadaLabsUsageSchemaStatus;
  migration_status?: CavadaLabsUsageMigrationStatus;
  missing_schema?: string[];
  migration_names?: string[];
  migration_plan?: {
    name: string;
    purpose: string;
  }[];
  readiness_checks?: CavadaLabsUsageReadinessCheck[];
}

export interface CavadaLabsUsageRepairResponse {
  entity_type: CavadaLabsUsageDiagnosticsEntityType;
  entity_ids: string[];
  attempted: boolean;
  repaired: boolean;
  dry_run?: boolean;
  batch_limit?: number | null;
  scoped_spend_logs: number;
  processed_spend_logs: number;
  batches: number;
  message?: string;
  diagnostics: CavadaLabsUsageDiagnosticsItem[];
  migration_name: string;
  migration_command: string;
  schema_status?: CavadaLabsUsageSchemaStatus;
  migration_status?: CavadaLabsUsageMigrationStatus;
  missing_schema?: string[];
  migration_names?: string[];
  migration_plan?: {
    name: string;
    purpose: string;
  }[];
  readiness_checks?: CavadaLabsUsageReadinessCheck[];
}

export interface CavadaLabsUsageMetrics {
  spend: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  api_requests: number;
  successful_requests: number;
  failed_requests: number;
  cache_read_input_tokens?: number;
  cache_creation_input_tokens?: number;
}

export interface CavadaLabsDailyActivityResult {
  date: string;
  metrics: CavadaLabsUsageMetrics;
  breakdown: CavadaLabsRecord;
}

export interface CavadaLabsDailyActivityResponse {
  results: CavadaLabsDailyActivityResult[];
  metadata: {
    total_spend: number;
    total_prompt_tokens: number;
    total_completion_tokens: number;
    total_tokens: number;
    total_api_requests: number;
    total_successful_requests: number;
    total_failed_requests: number;
    page: number;
    total_pages: number;
    has_more: boolean;
    [key: string]: any;
  };
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
  hidden?: (row: CavadaLabsRecord) => boolean;
  disabled?: (row: CavadaLabsRecord) => boolean;
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
  canCreate?: (context: CavadaLabsRuntimeContext) => boolean;
  updatePath?: (row: CavadaLabsRecord) => string;
  updateLabel?: string;
  updateFields?: CavadaLabsFieldConfig[];
  canUpdate?: (row: CavadaLabsRecord) => boolean;
  filters?: CavadaLabsFieldConfig[];
  requiredFilters?: string[];
  getInitialFilters?: (context: CavadaLabsRuntimeContext) => CavadaLabsRecord;
  columns: CavadaLabsColumnConfig[];
  rowActions?: CavadaLabsRowAction[];
  toolbarActions?: CavadaLabsToolbarAction[];
}
