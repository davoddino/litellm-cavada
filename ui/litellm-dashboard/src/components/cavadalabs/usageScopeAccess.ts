import type { CavadaLabsRecord, CavadaLabsRuntimeContext, CavadaLabsUsageDiagnosticsEntityType } from "./types";

export const findCavadaLabsUsageScopeRecord = (
  context: CavadaLabsRuntimeContext,
  entityType: CavadaLabsUsageDiagnosticsEntityType,
  entityId?: string,
): CavadaLabsRecord | undefined => {
  if (!entityId) return undefined;
  const rows = entityType === "company" ? context.companies : context.projects;
  const idField = entityType === "company" ? "company_id" : "project_id";
  return rows.find((row) => String(row[idField] ?? "") === entityId);
};

export const canManageCavadaLabsUsageScope = (
  context: CavadaLabsRuntimeContext,
  entityType: CavadaLabsUsageDiagnosticsEntityType,
  entityId?: string,
): boolean => findCavadaLabsUsageScopeRecord(context, entityType, entityId)?.cavadalabs_can_manage === true;
