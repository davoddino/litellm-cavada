import type { CavadaLabsRecord, CavadaLabsRuntimeContext, CavadaLabsUsageDiagnosticsEntityType } from "./types";

export const canViewCavadaLabsUsageScopeRecord = (record: CavadaLabsRecord | undefined): boolean =>
  record?.cavadalabs_can_view_usage !== false;

export const cavadaLabsUsageScopeRecords = (
  context: CavadaLabsRuntimeContext,
  entityType: CavadaLabsUsageDiagnosticsEntityType,
): CavadaLabsRecord[] => {
  const rows = entityType === "company" ? context.companies : context.projects;
  return rows.filter(canViewCavadaLabsUsageScopeRecord);
};

export const preferredCavadaLabsUsageEntityType = (
  context: CavadaLabsRuntimeContext,
): CavadaLabsUsageDiagnosticsEntityType => {
  const companyCount = cavadaLabsUsageScopeRecords(context, "company").length;
  const projectCount = cavadaLabsUsageScopeRecords(context, "project").length;
  return companyCount > 0 || projectCount === 0 ? "company" : "project";
};

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
