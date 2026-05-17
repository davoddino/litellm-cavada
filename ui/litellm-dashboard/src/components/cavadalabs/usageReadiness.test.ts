import { describe, expect, it } from "vitest";
import { cavadaLabsUsageReadinessSummary } from "./usageReadiness";
import type { CavadaLabsUsageDiagnosticsResponse } from "./types";

const responseWithChecks = (
  readinessChecks: CavadaLabsUsageDiagnosticsResponse["readiness_checks"],
): CavadaLabsUsageDiagnosticsResponse => ({
  diagnostics: [],
  migration_name: "20260515161000_backfill_cavadalabs_request_ledger_from_metadata_key_hash",
  migration_command: "uv run prisma migrate deploy",
  schema_status: "ready",
  migration_status: "ready",
  readiness_checks: readinessChecks,
});

describe("usageReadiness", () => {
  it("should classify missing schema as blocked migration readiness", () => {
    const summary = cavadaLabsUsageReadinessSummary({
      response: responseWithChecks([
        {
          code: "usage_schema",
          status: "blocked",
          message: "CavadaLabs usage schema is missing.",
          recommended_action: "run_migration_backfill",
          details: {
            missing_schema: ["CavadaLabs_RequestLedgerTable.company_id"],
          },
        },
      ]),
      entityType: "company",
      entityId: "company-1",
    });

    expect(summary?.type).toBe("error");
    expect(summary?.message).toBe("CavadaLabs usage schema is not ready");
    expect(summary?.details).toContain("Missing schema: CavadaLabs_RequestLedgerTable.company_id");
  });

  it("should classify attributable SpendLogs without ledger rows as repairable", () => {
    const summary = cavadaLabsUsageReadinessSummary({
      response: responseWithChecks([
        {
          code: "usage_schema",
          status: "ready",
          message: "Schema ready.",
        },
        {
          code: "repair_status",
          status: "action_required",
          message: "Scoped repair can copy attributable SpendLogs.",
          entity_type: "company",
          entity_id: "company-1",
          recommended_action: "run_scoped_backfill",
          details: {
            scoped_spend_logs: 3,
            missing_ledger_rows: 2,
          },
        },
      ]),
      entityType: "company",
      entityId: "company-1",
      canManageScope: true,
    });

    expect(summary?.type).toBe("warning");
    expect(summary?.message).toBe("Company usage can be repaired");
    expect(summary?.details).toContain("Missing ledger rows: 2");
  });

  it("should classify empty ledger and empty attribution as real no-data", () => {
    const summary = cavadaLabsUsageReadinessSummary({
      response: responseWithChecks([
        {
          code: "ledger_rows",
          status: "warning",
          message: "No ledger rows.",
          entity_type: "project",
          entity_id: "project-1",
          details: { ledger_rows: 0 },
        },
        {
          code: "spendlogs_attribution",
          status: "warning",
          message: "No attributable SpendLogs.",
          entity_type: "project",
          entity_id: "project-1",
          details: { attributable_spend_logs: 0 },
        },
      ]),
      entityType: "project",
      entityId: "project-1",
    });

    expect(summary?.type).toBe("info");
    expect(summary?.message).toBe("No Project-attributable usage");
    expect(summary?.details).toContain("Ledger rows: 0");
  });

  it("should classify filter and date-range readiness separately", () => {
    const filterSummary = cavadaLabsUsageReadinessSummary({
      response: responseWithChecks([
        {
          code: "filters",
          status: "warning",
          message: "Selected filters exclude usage.",
          entity_type: "company",
          entity_id: "company-1",
          details: { unfiltered_attributable_spend_logs: 4 },
        },
      ]),
      entityType: "company",
      entityId: "company-1",
    });
    const dateSummary = cavadaLabsUsageReadinessSummary({
      response: responseWithChecks([
        {
          code: "date_range",
          status: "warning",
          message: "Usage exists outside the date range.",
          entity_type: "company",
          entity_id: "company-1",
          details: { all_time_attributable_spend_logs: 5 },
        },
      ]),
      entityType: "company",
      entityId: "company-1",
    });

    expect(filterSummary?.message).toBe("Company usage is outside the current filters");
    expect(filterSummary?.details).toContain("Attributable rows outside filters: 4");
    expect(dateSummary?.message).toBe("Company usage is outside the selected date range");
    expect(dateSummary?.details).toContain("Attributable rows outside date range: 5");
  });

  it("should classify all-ready checks as healthy", () => {
    const summary = cavadaLabsUsageReadinessSummary({
      response: responseWithChecks([
        {
          code: "usage_schema",
          status: "ready",
          message: "Schema ready.",
        },
        {
          code: "ledger_rows",
          status: "ready",
          message: "Ledger rows exist.",
          entity_type: "company",
          entity_id: "company-1",
          details: { ledger_rows: 7 },
        },
        {
          code: "repair_status",
          status: "ready",
          message: "No repair required.",
          entity_type: "company",
          entity_id: "company-1",
        },
      ]),
      entityType: "company",
      entityId: "company-1",
    });

    expect(summary?.type).toBe("success");
    expect(summary?.message).toBe("Usage attribution is healthy");
    expect(summary?.details).toContain("Ledger rows: 7");
  });
});
