import type {
  CavadaLabsUsageDiagnosticsEntityType,
  CavadaLabsUsageDiagnosticsResponse,
  CavadaLabsUsageReadinessCheck,
  CavadaLabsUsageReadinessCheckStatus,
} from "./types";

export interface CavadaLabsUsageReadinessSummary {
  type: "success" | "info" | "warning" | "error";
  message: string;
  description: string;
  details: string[];
}

const entityLabel = (entityType: CavadaLabsUsageDiagnosticsEntityType): string =>
  entityType === "company" ? "Company" : "Project";

export const cavadaLabsReadinessStatusColor = (status: CavadaLabsUsageReadinessCheckStatus): string => {
  switch (status) {
    case "ready":
      return "green";
    case "warning":
      return "gold";
    case "action_required":
      return "orange";
    case "blocked":
      return "red";
    default:
      return "default";
  }
};

export const cavadaLabsReadinessCheckLabel = (check: CavadaLabsUsageReadinessCheck): string =>
  check.code.replaceAll("_", " ");

const hasStatus = (checks: CavadaLabsUsageReadinessCheck[], status: CavadaLabsUsageReadinessCheckStatus): boolean =>
  checks.some((check) => check.status === status);

const findCheck = (
  checks: CavadaLabsUsageReadinessCheck[],
  predicate: (check: CavadaLabsUsageReadinessCheck) => boolean,
): CavadaLabsUsageReadinessCheck | undefined => checks.find(predicate);

const checkDetails = (check: CavadaLabsUsageReadinessCheck | undefined): string[] => {
  if (!check?.details) return [];
  const lines: string[] = [];
  const details = check.details;
  if (Array.isArray(details.missing_schema)) {
    details.missing_schema.forEach((value) => lines.push(`Missing schema: ${value}`));
  }
  if (typeof details.ledger_rows === "number") {
    lines.push(`Ledger rows: ${details.ledger_rows}`);
  }
  if (typeof details.attributable_spend_logs === "number") {
    lines.push(`Attributable SpendLogs: ${details.attributable_spend_logs}`);
  }
  if (typeof details.missing_ledger_rows === "number") {
    lines.push(`Missing ledger rows: ${details.missing_ledger_rows}`);
  }
  if (typeof details.unfiltered_attributable_spend_logs === "number") {
    lines.push(`Attributable rows outside filters: ${details.unfiltered_attributable_spend_logs}`);
  }
  if (typeof details.all_time_attributable_spend_logs === "number") {
    lines.push(`Attributable rows outside date range: ${details.all_time_attributable_spend_logs}`);
  }
  if (Array.isArray(details.missing_mappings)) {
    details.missing_mappings.forEach((value) => lines.push(`Missing mapping: ${value}`));
  }
  return lines;
};

export const cavadaLabsUsageReadinessChecksForScope = (
  response: CavadaLabsUsageDiagnosticsResponse | null,
  entityType?: CavadaLabsUsageDiagnosticsEntityType,
  entityId?: string,
): CavadaLabsUsageReadinessCheck[] => {
  const checks = response?.readiness_checks ?? [];
  if (!entityType && !entityId) return checks;
  return checks.filter((check) => {
    if (!check.entity_type && !check.entity_id) return true;
    if (entityType && check.entity_type && check.entity_type !== entityType) return false;
    if (entityId && check.entity_id && check.entity_id !== entityId) return false;
    return true;
  });
};

export const cavadaLabsUsageReadinessSummary = ({
  response,
  entityType,
  entityId,
  canManageScope,
}: {
  response: CavadaLabsUsageDiagnosticsResponse | null;
  entityType: CavadaLabsUsageDiagnosticsEntityType;
  entityId?: string;
  canManageScope?: boolean;
}): CavadaLabsUsageReadinessSummary | null => {
  const checks = cavadaLabsUsageReadinessChecksForScope(response, entityType, entityId);
  if (checks.length === 0) return null;
  const label = entityLabel(entityType);
  const schemaCheck = findCheck(checks, (check) => check.code === "usage_schema" && check.status === "blocked");
  if (schemaCheck) {
    return {
      type: "error",
      message: "CavadaLabs usage schema is not ready",
      description: schemaCheck.message,
      details: checkDetails(schemaCheck),
    };
  }

  const repairCheck = findCheck(
    checks,
    (check) => check.code === "repair_status" && check.recommended_action === "run_scoped_backfill",
  );
  if (repairCheck) {
    return {
      type: "warning",
      message: `${label} usage can be repaired`,
      description:
        canManageScope === false
          ? "Spend exists for this Company/Project, but scoped backfill requires Company/Project admin access."
          : repairCheck.message,
      details: checkDetails(repairCheck),
    };
  }

  const mappingCheck = findCheck(
    checks,
    (check) =>
      check.recommended_action === "fix_compatibility_mapping" ||
      (check.code === "spendlogs_attribution" && check.status === "action_required"),
  );
  if (mappingCheck) {
    return {
      type: "error",
      message: `${label} usage is not attributable yet`,
      description: mappingCheck.message,
      details: checkDetails(mappingCheck),
    };
  }

  const dateRangeCheck = findCheck(checks, (check) => check.code === "date_range");
  if (dateRangeCheck) {
    return {
      type: "warning",
      message: `${label} usage is outside the selected date range`,
      description: dateRangeCheck.message,
      details: checkDetails(dateRangeCheck),
    };
  }

  const filterCheck = findCheck(checks, (check) => check.code === "filters");
  if (filterCheck) {
    return {
      type: "warning",
      message: `${label} usage is outside the current filters`,
      description: filterCheck.message,
      details: checkDetails(filterCheck),
    };
  }

  const ledgerCheck = findCheck(checks, (check) => check.code === "ledger_rows");
  const spendLogsCheck = findCheck(checks, (check) => check.code === "spendlogs_attribution");
  if (ledgerCheck?.status === "warning" && spendLogsCheck?.status === "warning") {
    return {
      type: "info",
      message: `No ${label}-attributable usage`,
      description: spendLogsCheck.message,
      details: [...checkDetails(ledgerCheck), ...checkDetails(spendLogsCheck)],
    };
  }

  if (!hasStatus(checks, "blocked") && !hasStatus(checks, "action_required") && !hasStatus(checks, "warning")) {
    return {
      type: "success",
      message: "Usage attribution is healthy",
      description: "CavadaLabs ledger data covers the selected Company/Project scope.",
      details: checkDetails(ledgerCheck),
    };
  }

  const warningCheck = findCheck(checks, (check) => check.status === "warning");
  if (warningCheck) {
    return {
      type: "warning",
      message: `${label} usage needs review`,
      description: warningCheck.message,
      details: checkDetails(warningCheck),
    };
  }

  return null;
};
