CREATE TABLE IF NOT EXISTS "CavadaLabs_BillingReportTable" (
    "report_id" TEXT NOT NULL,
    "company_id" TEXT NOT NULL,
    "report_version" INTEGER NOT NULL,
    "period_start" TIMESTAMP(3) NOT NULL,
    "period_end" TIMESTAMP(3) NOT NULL,
    "currency" TEXT NOT NULL DEFAULT 'EUR',
    "status" TEXT NOT NULL DEFAULT 'generated',
    "formats" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "total_requests" INTEGER NOT NULL DEFAULT 0,
    "total_tokens" INTEGER NOT NULL DEFAULT 0,
    "total_spend" DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    "provider_cost" DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    "cavadalabs_node_cost" DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    "tax_rate" DOUBLE PRECISION,
    "tax_amount" DOUBLE PRECISION,
    "grand_total" DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    "checksum" TEXT NOT NULL,
    "inputs_snapshot" JSONB NOT NULL DEFAULT '{}',
    "totals" JSONB NOT NULL DEFAULT '{}',
    "breakdowns" JSONB NOT NULL DEFAULT '{}',
    "artifacts" JSONB NOT NULL DEFAULT '{}',
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "generated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "generated_by" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "CavadaLabs_BillingReportTable_pkey" PRIMARY KEY ("report_id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_BillingReportTable_checksum_key" ON "CavadaLabs_BillingReportTable"("checksum");
CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_BillingReportTable_company_id_period_start_period_end_report_version_key" ON "CavadaLabs_BillingReportTable"("company_id", "period_start", "period_end", "report_version");
CREATE INDEX IF NOT EXISTS "CavadaLabs_BillingReportTable_company_id_period_start_period_end_idx" ON "CavadaLabs_BillingReportTable"("company_id", "period_start", "period_end");
CREATE INDEX IF NOT EXISTS "CavadaLabs_BillingReportTable_generated_at_idx" ON "CavadaLabs_BillingReportTable"("generated_at");

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_BillingReportTable_company_id_fkey') THEN
        ALTER TABLE "CavadaLabs_BillingReportTable" ADD CONSTRAINT "CavadaLabs_BillingReportTable_company_id_fkey" FOREIGN KEY ("company_id") REFERENCES "CavadaLabs_CompanyTable"("company_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
END $$;
