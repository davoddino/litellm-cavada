import type { CavadaLabsRecord, CavadaLabsUsageDiagnosticsResponse } from "./types";

export interface CavadaLabsStructuredErrorDetail extends CavadaLabsRecord {
  error?: string;
  message?: string;
  schema_status?: string;
  migration_status?: string;
  missing_schema?: string[];
  migration_command?: string;
  migration_name?: string;
  migration_names?: string[];
  migration_plan?: Array<{
    name: string;
    purpose: string;
  }>;
  readiness_checks?: CavadaLabsUsageDiagnosticsResponse["readiness_checks"];
}

const isRecord = (value: unknown): value is CavadaLabsRecord =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export const cavadaLabsErrorDetailFromPayload = (payload: unknown): CavadaLabsStructuredErrorDetail | null => {
  if (!isRecord(payload)) return null;
  if (isRecord(payload.detail)) {
    return payload.detail as CavadaLabsStructuredErrorDetail;
  }
  return payload as CavadaLabsStructuredErrorDetail;
};

export const cavadaLabsErrorDetailFromUnknown = (err: unknown): CavadaLabsStructuredErrorDetail | null => {
  if (isRecord(err) && "payload" in err) {
    return cavadaLabsErrorDetailFromPayload(err.payload);
  }
  if (isRecord(err) && "detail" in err) {
    return cavadaLabsErrorDetailFromPayload(err);
  }
  return null;
};

export const isCavadaLabsMissingSchemaDetail = (
  detail: CavadaLabsStructuredErrorDetail | null | undefined,
): detail is CavadaLabsStructuredErrorDetail =>
  detail?.schema_status === "missing_schema" || detail?.migration_status === "schema_missing";

export const cavadalabsMissingSchemaDiagnosticsFromDetail = (
  detail: CavadaLabsStructuredErrorDetail,
): CavadaLabsUsageDiagnosticsResponse => ({
  diagnostics: [],
  migration_name: typeof detail.migration_name === "string" ? detail.migration_name : "",
  migration_command:
    typeof detail.migration_command === "string" && detail.migration_command
      ? detail.migration_command
      : "uv run prisma migrate deploy",
  schema_status: "missing_schema",
  migration_status: "schema_missing",
  missing_schema: Array.isArray(detail.missing_schema) ? detail.missing_schema : [],
  migration_names: Array.isArray(detail.migration_names) ? detail.migration_names : undefined,
  migration_plan: Array.isArray(detail.migration_plan) ? detail.migration_plan : undefined,
  readiness_checks: Array.isArray(detail.readiness_checks)
    ? detail.readiness_checks
    : [
        {
          code: "usage_schema",
          status: "blocked",
          message: "CavadaLabs usage schema is missing or incomplete.",
          recommended_action: "run_migration_backfill",
          details: {
            missing_schema: Array.isArray(detail.missing_schema) ? detail.missing_schema : [],
          },
        },
      ],
});

export const cavadalabsMissingSchemaDetailLines = (detail: CavadaLabsStructuredErrorDetail): string[] => {
  const lines: string[] = [];
  const missingSchema = Array.isArray(detail.missing_schema) ? detail.missing_schema : [];
  missingSchema.forEach((item) => lines.push(`Missing schema: ${item}`));
  if (detail.migration_command) {
    lines.push(`Migration command: ${detail.migration_command}`);
  }
  return lines;
};
