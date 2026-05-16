import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { act, fireEvent } from "@testing-library/react";
import { renderWithProviders, screen, waitFor } from "../../../tests/test-utils";
import CavadaLabsUsageDiagnosticsPanel from "./CavadaLabsUsageDiagnosticsPanel";
import type { CavadaLabsRuntimeContext } from "./types";

vi.mock("@/components/networking", () => ({
  getProxyBaseUrl: () => "http://proxy.test",
  getGlobalLitellmHeaderName: () => "Authorization",
  deriveErrorMessage: (errorData: any) => errorData?.detail?.error ?? errorData?.detail ?? "error",
  handleError: vi.fn(),
}));

const jsonResponse = (payload: any, ok = true) =>
  ({
    ok,
    headers: {
      get: () => "application/json",
    },
    json: vi.fn().mockResolvedValue(payload),
    text: vi.fn(),
  }) as any;

const context: CavadaLabsRuntimeContext = {
  companies: [{ company_id: "company-1", legal_name: "Acme Srl", cavadalabs_can_manage: true }],
  projects: [{ project_id: "project-1", name: "Support", cavadalabs_can_manage: true }],
  chatbots: [],
  ragCollections: [],
  nodes: [],
};

const viewerContext: CavadaLabsRuntimeContext = {
  companies: [{ company_id: "company-1", legal_name: "Acme Srl", cavadalabs_can_manage: false }],
  projects: [{ project_id: "project-1", name: "Support", cavadalabs_can_manage: false }],
  chatbots: [],
  ragCollections: [],
  nodes: [],
};

describe("CavadaLabsUsageDiagnosticsPanel", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("should call Company diagnostics with canonical Company filters and show scoped backfill action", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          diagnostics: [
            {
              entity_type: "company",
              entity_id: "company-1",
              status: "scoped_backfill_available",
              ledger_rows: 0,
              attributable_spend_logs: 2,
              metadata_spend_logs: 1,
              compatibility_spend_logs: 1,
              key_metadata_spend_logs: 1,
              unmapped_spend_logs: 0,
              ledger_gap: 2,
              missing_ledger_rows: 2,
              recommended_action: "run_scoped_backfill",
              scoped_backfill_available: true,
              missing_mappings: [],
              message: "Company usage exists in LiteLLM SpendLogs.",
            },
          ],
          migration_name: "20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata",
          migration_names: [
            "20260515122000_add_cavadalabs_usage_spend_log_indexes",
            "20260515123000_backfill_cavadalabs_request_ledger_from_spend_logs",
            "20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata",
          ],
          migration_plan: [
            {
              name: "20260515122000_add_cavadalabs_usage_spend_log_indexes",
              purpose: "Adds SpendLogs indexes used by scoped Company/Project diagnostics and repair.",
            },
            {
              name: "20260515123000_backfill_cavadalabs_request_ledger_from_spend_logs",
              purpose: "Backfills CavadaLabs request ledger rows from SpendLogs metadata.",
            },
            {
              name: "20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata",
              purpose: "Backfills historical SpendLogs from key Company/Project metadata.",
            },
          ],
          migration_command: "uv run prisma migrate deploy",
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          entity_type: "company",
          entity_ids: ["company-1"],
          attempted: true,
          repaired: true,
          scoped_spend_logs: 2,
          processed_spend_logs: 2,
          batches: 1,
          diagnostics: [
            {
              entity_type: "company",
              entity_id: "company-1",
              status: "visible",
              ledger_rows: 2,
              attributable_spend_logs: 2,
              ledger_gap: 0,
              recommended_action: "none",
              scoped_backfill_available: false,
              missing_mappings: [],
              message: "Company usage is visible.",
            },
          ],
          migration_name: "20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata",
          migration_names: [
            "20260515122000_add_cavadalabs_usage_spend_log_indexes",
            "20260515123000_backfill_cavadalabs_request_ledger_from_spend_logs",
            "20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata",
          ],
          migration_plan: [
            {
              name: "20260515122000_add_cavadalabs_usage_spend_log_indexes",
              purpose: "Adds SpendLogs indexes used by scoped Company/Project diagnostics and repair.",
            },
            {
              name: "20260515123000_backfill_cavadalabs_request_ledger_from_spend_logs",
              purpose: "Backfills CavadaLabs request ledger rows from SpendLogs metadata.",
            },
            {
              name: "20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata",
              purpose: "Backfills historical SpendLogs from key Company/Project metadata.",
            },
          ],
          migration_command: "uv run prisma migrate deploy",
        }),
      );
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsUsageDiagnosticsPanel accessToken="token-1" context={context} />);

    expect(await screen.findByText("Scoped backfill is available")).toBeInTheDocument();
    expect(screen.getAllByText("Direct metadata").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Compat mapping").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Key metadata").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Unmapped candidates").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /run scoped backfill/i })).toBeInTheDocument();
    expect(screen.getByText("20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata")).toBeInTheDocument();
    expect(screen.getByText("uv run prisma migrate deploy")).toBeInTheDocument();

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });

    const url = new URL(String(mockFetch.mock.calls[0][0]));
    expect(url.pathname).toBe("/cavadalabs/companies/usage/diagnostics");
    expect(url.searchParams.get("company_ids")).toBe("company-1");
    expect(url.searchParams.get("project_ids")).toBeNull();
    expect(url.searchParams.get("start_date")).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(url.searchParams.get("end_date")).toMatch(/^\d{4}-\d{2}-\d{2}$/);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /run scoped backfill/i }));
    });

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(2);
    });
    const repairUrl = new URL(String(mockFetch.mock.calls[1][0]));
    const repairInit = mockFetch.mock.calls[1][1];
    expect(repairUrl.pathname).toBe("/cavadalabs/companies/usage/repair");
    expect(repairInit.method).toBe("POST");
    expect(JSON.parse(repairInit.body)).toMatchObject({
      company_ids: ["company-1"],
      start_date: url.searchParams.get("start_date"),
      end_date: url.searchParams.get("end_date"),
    });
    expect(await screen.findByText("Usage attribution is healthy")).toBeInTheDocument();
  });

  it("should present missing mappings as Company and Project problems without exposing Organizations", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      jsonResponse({
        diagnostics: [
          {
            entity_type: "company",
            entity_id: "company-1",
            status: "missing_compatibility_mapping",
            ledger_rows: 0,
            attributable_spend_logs: 0,
            ledger_gap: 0,
            recommended_action: "fix_compatibility_mapping",
            scoped_backfill_available: false,
            missing_mappings: ["company litellm_organization_id or CavadaLabs key metadata"],
            message: "Missing compatibility mapping: company litellm_organization_id or CavadaLabs key metadata.",
          },
        ],
        migration_name: "20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata",
        migration_command: "uv run prisma migrate deploy",
      }),
    );
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsUsageDiagnosticsPanel accessToken="token-1" context={context} />);

    expect(await screen.findByText("Company/Project mapping is incomplete")).toBeInTheDocument();
    expect(screen.getByText("Fix Company/Project mapping")).toBeInTheDocument();
    expect(screen.getByText("Company compatibility mapping or key metadata")).toBeInTheDocument();
    expect(screen.queryByText(/organization/i)).not.toBeInTheDocument();
  });

  it("should show scoped backfill diagnostics without repair action for viewers", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      jsonResponse({
        diagnostics: [
          {
            entity_type: "company",
            entity_id: "company-1",
            status: "scoped_backfill_available",
            ledger_rows: 0,
            attributable_spend_logs: 2,
            ledger_gap: 2,
            recommended_action: "run_scoped_backfill",
            scoped_backfill_available: true,
            missing_mappings: [],
            message: "Company usage exists in LiteLLM SpendLogs.",
          },
        ],
        migration_name: "20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata",
        migration_command: "uv run prisma migrate deploy",
        schema_status: "ready",
        migration_status: "ready",
      }),
    );
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsUsageDiagnosticsPanel accessToken="token-1" context={viewerContext} />);

    expect(await screen.findByText("Scoped backfill is available")).toBeInTheDocument();
    expect(screen.getByText("Admin required")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run scoped backfill/i })).not.toBeInTheDocument();
  });

  it("should show schema migration status without offering scoped repair", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      jsonResponse({
        diagnostics: [
          {
            entity_type: "company",
            entity_id: "company-1",
            status: "backfill_required",
            ledger_rows: 0,
            attributable_spend_logs: 0,
            ledger_gap: 0,
            recommended_action: "run_migration_backfill",
            scoped_backfill_available: false,
            missing_mappings: [],
            missing_schema: ["CavadaLabs_RequestLedgerTable.company_id"],
            message: "CavadaLabs usage schema is missing.",
          },
        ],
        migration_name: "20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata",
        migration_command: "uv run prisma migrate deploy",
        schema_status: "missing_schema",
        migration_status: "schema_missing",
        missing_schema: ["CavadaLabs_RequestLedgerTable.company_id"],
      }),
    );
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsUsageDiagnosticsPanel accessToken="token-1" context={context} />);

    expect(await screen.findByText("CavadaLabs usage schema is not ready")).toBeInTheDocument();
    expect(screen.getByText("uv run prisma migrate deploy")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run scoped backfill/i })).not.toBeInTheDocument();
  });

  it("should not offer repair when schema is missing even if a row looks repairable", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      jsonResponse({
        diagnostics: [
          {
            entity_type: "company",
            entity_id: "company-1",
            status: "scoped_backfill_available",
            ledger_rows: 0,
            attributable_spend_logs: 2,
            ledger_gap: 2,
            recommended_action: "run_scoped_backfill",
            scoped_backfill_available: true,
            missing_mappings: [],
            missing_schema: ["LiteLLM_SpendLogs.metadata"],
            message: "SpendLogs are repairable after schema migration.",
          },
        ],
        migration_name: "20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata",
        migration_command: "uv run prisma migrate deploy",
        schema_status: "missing_schema",
        migration_status: "schema_missing",
        missing_schema: ["LiteLLM_SpendLogs.metadata"],
      }),
    );
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsUsageDiagnosticsPanel accessToken="token-1" context={context} />);

    expect(await screen.findByText("CavadaLabs usage schema is not ready")).toBeInTheDocument();
    expect(screen.getByText("uv run prisma migrate deploy")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run scoped backfill/i })).not.toBeInTheDocument();
  });

  it("should render actionable migration status when diagnostics endpoint returns missing schema", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      jsonResponse(
        {
          detail: {
            error: "CavadaLabs access control schema is missing required table delegate.",
            schema_status: "missing_schema",
            migration_status: "schema_missing",
            missing_schema: ["cavadalabs_companymembertable"],
            migration_command: "uv run prisma migrate deploy",
          },
        },
        false,
      ),
    );
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsUsageDiagnosticsPanel accessToken="token-1" context={context} />);

    expect(await screen.findByText("CavadaLabs usage schema is not ready")).toBeInTheDocument();
    expect(screen.getByText("uv run prisma migrate deploy")).toBeInTheDocument();
    expect(screen.queryByText("No diagnostics returned for this scope")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run scoped backfill/i })).not.toBeInTheDocument();
  });

  it("should distinguish restrictive filters from missing mappings", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      jsonResponse({
        diagnostics: [
          {
            entity_type: "company",
            entity_id: "company-1",
            status: "filters_exclude_usage",
            ledger_rows: 0,
            attributable_spend_logs: 0,
            unfiltered_attributable_spend_logs: 3,
            ledger_gap: 0,
            recommended_action: "none",
            scoped_backfill_available: false,
            filters_exclude_usage: true,
            missing_mappings: [],
            message: "Filters exclude attributable spend.",
          },
        ],
        migration_name: "20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata",
        migration_command: "uv run prisma migrate deploy",
      }),
    );
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsUsageDiagnosticsPanel accessToken="token-1" context={context} />);

    expect(await screen.findByText("Current filters hide attributable usage")).toBeInTheDocument();
    expect(screen.getByText("filters exclude usage")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run scoped backfill/i })).not.toBeInTheDocument();
  });

  it("should show real no-data diagnostics without implying healthy ledger coverage", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      jsonResponse({
        diagnostics: [
          {
            entity_type: "company",
            entity_id: "company-1",
            status: "no_attributable_spend",
            ledger_rows: 0,
            attributable_spend_logs: 0,
            ledger_gap: 0,
            recommended_action: "none",
            scoped_backfill_available: false,
            missing_mappings: [],
            message: "No attributable Company/Project spend found.",
          },
        ],
        migration_name: "20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata",
        migration_command: "uv run prisma migrate deploy",
        schema_status: "ready",
        migration_status: "ready",
      }),
    );
    global.fetch = mockFetch as any;

    renderWithProviders(<CavadaLabsUsageDiagnosticsPanel accessToken="token-1" context={context} />);

    expect(await screen.findByText("No Company/Project-attributable spend")).toBeInTheDocument();
    expect(screen.getByText(/No ledger rows, SpendLogs metadata, key metadata/i)).toBeInTheDocument();
    expect(screen.queryByText("Usage attribution is healthy")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run scoped backfill/i })).not.toBeInTheDocument();
  });
});
