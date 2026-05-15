CREATE TABLE IF NOT EXISTS "CavadaLabs_NodeTable" (
    "node_id" TEXT NOT NULL,
    "display_name" TEXT NOT NULL,
    "hostname" TEXT,
    "location" TEXT,
    "status" TEXT NOT NULL DEFAULT 'pending',
    "public_key" TEXT,
    "public_key_fingerprint" TEXT,
    "agent_version" TEXT,
    "allowed_project_ids" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "pools" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "default_electricity_cost_per_kwh" DOUBLE PRECISION,
    "fixed_hourly_cost" DOUBLE PRECISION,
    "hardware_amortization_hourly_cost" DOUBLE PRECISION,
    "last_heartbeat_at" TIMESTAMP(3),
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_by" TEXT NOT NULL,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_by" TEXT NOT NULL,
    CONSTRAINT "CavadaLabs_NodeTable_pkey" PRIMARY KEY ("node_id")
);

CREATE TABLE IF NOT EXISTS "CavadaLabs_GPUTable" (
    "gpu_id" TEXT NOT NULL,
    "node_id" TEXT NOT NULL,
    "vendor" TEXT NOT NULL,
    "model" TEXT NOT NULL,
    "uuid" TEXT,
    "vram_total_mb" INTEGER NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'available',
    "loaded_model_ids" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_by" TEXT NOT NULL,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_by" TEXT NOT NULL,
    CONSTRAINT "CavadaLabs_GPUTable_pkey" PRIMARY KEY ("gpu_id")
);

CREATE TABLE IF NOT EXISTS "CavadaLabs_NodeEnrollmentTable" (
    "enrollment_id" TEXT NOT NULL,
    "node_id" TEXT NOT NULL,
    "secret_prefix" TEXT NOT NULL,
    "secret_hash" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'active',
    "expires_at" TIMESTAMP(3) NOT NULL,
    "used_at" TIMESTAMP(3),
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_by" TEXT NOT NULL,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_by" TEXT NOT NULL,
    CONSTRAINT "CavadaLabs_NodeEnrollmentTable_pkey" PRIMARY KEY ("enrollment_id")
);

CREATE TABLE IF NOT EXISTS "CavadaLabs_NodeDailyReportTable" (
    "report_id" TEXT NOT NULL,
    "node_id" TEXT NOT NULL,
    "report_date" TIMESTAMP(3) NOT NULL,
    "samples" JSONB NOT NULL DEFAULT '[]',
    "total_kwh" DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    "total_model_runtime_seconds" INTEGER NOT NULL DEFAULT 0,
    "total_loaded_model_seconds" INTEGER NOT NULL DEFAULT 0,
    "total_requests" INTEGER NOT NULL DEFAULT 0,
    "total_tokens" INTEGER NOT NULL DEFAULT 0,
    "node_cost_estimate" DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    "errors" JSONB NOT NULL DEFAULT '[]',
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "CavadaLabs_NodeDailyReportTable_pkey" PRIMARY KEY ("report_id")
);

CREATE TABLE IF NOT EXISTS "CavadaLabs_ModelLoadRequestTable" (
    "model_load_request_id" TEXT NOT NULL,
    "company_id" TEXT,
    "project_id" TEXT NOT NULL,
    "model_alias" TEXT NOT NULL,
    "provider" TEXT NOT NULL DEFAULT 'cavadalabs',
    "node_id" TEXT,
    "gpu_id" TEXT,
    "loaded_model_id" TEXT,
    "status" TEXT NOT NULL DEFAULT 'queued',
    "priority" INTEGER NOT NULL DEFAULT 100,
    "requested_by" TEXT NOT NULL,
    "requested_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "expires_at" TIMESTAMP(3),
    "last_error" TEXT,
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "CavadaLabs_ModelLoadRequestTable_pkey" PRIMARY KEY ("model_load_request_id")
);

CREATE TABLE IF NOT EXISTS "CavadaLabs_LoadedModelTable" (
    "loaded_model_id" TEXT NOT NULL,
    "node_id" TEXT NOT NULL,
    "gpu_id" TEXT,
    "model_alias" TEXT NOT NULL,
    "provider" TEXT NOT NULL DEFAULT 'cavadalabs',
    "status" TEXT NOT NULL DEFAULT 'loading',
    "load_request_id" TEXT,
    "context_window" INTEGER,
    "capabilities" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "loaded_at" TIMESTAMP(3),
    "unloaded_at" TIMESTAMP(3),
    "last_used_at" TIMESTAMP(3),
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "CavadaLabs_LoadedModelTable_pkey" PRIMARY KEY ("loaded_model_id")
);

CREATE TABLE IF NOT EXISTS "CavadaLabs_GPULockTable" (
    "lock_id" TEXT NOT NULL,
    "node_id" TEXT NOT NULL,
    "gpu_id" TEXT NOT NULL,
    "model_id" TEXT NOT NULL,
    "project_id" TEXT NOT NULL,
    "owner_type" TEXT NOT NULL,
    "owner_id" TEXT NOT NULL,
    "priority" INTEGER NOT NULL,
    "expires_at" TIMESTAMP(3) NOT NULL,
    "released_at" TIMESTAMP(3),
    "status" TEXT NOT NULL DEFAULT 'active',
    "lock_key" TEXT,
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "CavadaLabs_GPULockTable_pkey" PRIMARY KEY ("lock_id")
);

CREATE INDEX IF NOT EXISTS "CavadaLabs_NodeTable_status_idx" ON "CavadaLabs_NodeTable"("status");
CREATE INDEX IF NOT EXISTS "CavadaLabs_NodeTable_location_idx" ON "CavadaLabs_NodeTable"("location");

CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_GPUTable_node_id_uuid_key" ON "CavadaLabs_GPUTable"("node_id", "uuid");
CREATE INDEX IF NOT EXISTS "CavadaLabs_GPUTable_node_id_status_idx" ON "CavadaLabs_GPUTable"("node_id", "status");
CREATE INDEX IF NOT EXISTS "CavadaLabs_GPUTable_vendor_model_idx" ON "CavadaLabs_GPUTable"("vendor", "model");

CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_NodeEnrollmentTable_secret_hash_key" ON "CavadaLabs_NodeEnrollmentTable"("secret_hash");
CREATE INDEX IF NOT EXISTS "CavadaLabs_NodeEnrollmentTable_node_id_status_idx" ON "CavadaLabs_NodeEnrollmentTable"("node_id", "status");
CREATE INDEX IF NOT EXISTS "CavadaLabs_NodeEnrollmentTable_status_expires_at_idx" ON "CavadaLabs_NodeEnrollmentTable"("status", "expires_at");
CREATE INDEX IF NOT EXISTS "CavadaLabs_NodeEnrollmentTable_secret_prefix_idx" ON "CavadaLabs_NodeEnrollmentTable"("secret_prefix");

CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_NodeDailyReportTable_node_id_report_date_key" ON "CavadaLabs_NodeDailyReportTable"("node_id", "report_date");
CREATE INDEX IF NOT EXISTS "CavadaLabs_NodeDailyReportTable_node_id_report_date_idx" ON "CavadaLabs_NodeDailyReportTable"("node_id", "report_date");

CREATE INDEX IF NOT EXISTS "CavadaLabs_ModelLoadRequestTable_company_id_project_id_status_idx" ON "CavadaLabs_ModelLoadRequestTable"("company_id", "project_id", "status");
CREATE INDEX IF NOT EXISTS "CavadaLabs_ModelLoadRequestTable_project_id_status_priority_idx" ON "CavadaLabs_ModelLoadRequestTable"("project_id", "status", "priority");
CREATE INDEX IF NOT EXISTS "CavadaLabs_ModelLoadRequestTable_node_id_gpu_id_status_idx" ON "CavadaLabs_ModelLoadRequestTable"("node_id", "gpu_id", "status");
CREATE INDEX IF NOT EXISTS "CavadaLabs_ModelLoadRequestTable_model_alias_status_idx" ON "CavadaLabs_ModelLoadRequestTable"("model_alias", "status");

CREATE INDEX IF NOT EXISTS "CavadaLabs_LoadedModelTable_node_id_gpu_id_status_idx" ON "CavadaLabs_LoadedModelTable"("node_id", "gpu_id", "status");
CREATE INDEX IF NOT EXISTS "CavadaLabs_LoadedModelTable_model_alias_status_idx" ON "CavadaLabs_LoadedModelTable"("model_alias", "status");
CREATE INDEX IF NOT EXISTS "CavadaLabs_LoadedModelTable_load_request_id_idx" ON "CavadaLabs_LoadedModelTable"("load_request_id");

CREATE INDEX IF NOT EXISTS "CavadaLabs_GPULockTable_node_id_gpu_id_status_idx" ON "CavadaLabs_GPULockTable"("node_id", "gpu_id", "status");
CREATE INDEX IF NOT EXISTS "CavadaLabs_GPULockTable_project_id_status_idx" ON "CavadaLabs_GPULockTable"("project_id", "status");
CREATE INDEX IF NOT EXISTS "CavadaLabs_GPULockTable_expires_at_status_idx" ON "CavadaLabs_GPULockTable"("expires_at", "status");
CREATE INDEX IF NOT EXISTS "CavadaLabs_GPULockTable_owner_type_owner_id_idx" ON "CavadaLabs_GPULockTable"("owner_type", "owner_id");
CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_GPULockTable_lock_key_key" ON "CavadaLabs_GPULockTable"("lock_key");

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_GPUTable_node_id_fkey') THEN
        ALTER TABLE "CavadaLabs_GPUTable" ADD CONSTRAINT "CavadaLabs_GPUTable_node_id_fkey" FOREIGN KEY ("node_id") REFERENCES "CavadaLabs_NodeTable"("node_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_NodeEnrollmentTable_node_id_fkey') THEN
        ALTER TABLE "CavadaLabs_NodeEnrollmentTable" ADD CONSTRAINT "CavadaLabs_NodeEnrollmentTable_node_id_fkey" FOREIGN KEY ("node_id") REFERENCES "CavadaLabs_NodeTable"("node_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_NodeDailyReportTable_node_id_fkey') THEN
        ALTER TABLE "CavadaLabs_NodeDailyReportTable" ADD CONSTRAINT "CavadaLabs_NodeDailyReportTable_node_id_fkey" FOREIGN KEY ("node_id") REFERENCES "CavadaLabs_NodeTable"("node_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_ModelLoadRequestTable_company_id_fkey') THEN
        ALTER TABLE "CavadaLabs_ModelLoadRequestTable" ADD CONSTRAINT "CavadaLabs_ModelLoadRequestTable_company_id_fkey" FOREIGN KEY ("company_id") REFERENCES "CavadaLabs_CompanyTable"("company_id") ON DELETE SET NULL ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_ModelLoadRequestTable_project_id_fkey') THEN
        ALTER TABLE "CavadaLabs_ModelLoadRequestTable" ADD CONSTRAINT "CavadaLabs_ModelLoadRequestTable_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "CavadaLabs_ProjectTable"("project_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_ModelLoadRequestTable_node_id_fkey') THEN
        ALTER TABLE "CavadaLabs_ModelLoadRequestTable" ADD CONSTRAINT "CavadaLabs_ModelLoadRequestTable_node_id_fkey" FOREIGN KEY ("node_id") REFERENCES "CavadaLabs_NodeTable"("node_id") ON DELETE SET NULL ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_ModelLoadRequestTable_gpu_id_fkey') THEN
        ALTER TABLE "CavadaLabs_ModelLoadRequestTable" ADD CONSTRAINT "CavadaLabs_ModelLoadRequestTable_gpu_id_fkey" FOREIGN KEY ("gpu_id") REFERENCES "CavadaLabs_GPUTable"("gpu_id") ON DELETE SET NULL ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_LoadedModelTable_node_id_fkey') THEN
        ALTER TABLE "CavadaLabs_LoadedModelTable" ADD CONSTRAINT "CavadaLabs_LoadedModelTable_node_id_fkey" FOREIGN KEY ("node_id") REFERENCES "CavadaLabs_NodeTable"("node_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_LoadedModelTable_gpu_id_fkey') THEN
        ALTER TABLE "CavadaLabs_LoadedModelTable" ADD CONSTRAINT "CavadaLabs_LoadedModelTable_gpu_id_fkey" FOREIGN KEY ("gpu_id") REFERENCES "CavadaLabs_GPUTable"("gpu_id") ON DELETE SET NULL ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_GPULockTable_node_id_fkey') THEN
        ALTER TABLE "CavadaLabs_GPULockTable" ADD CONSTRAINT "CavadaLabs_GPULockTable_node_id_fkey" FOREIGN KEY ("node_id") REFERENCES "CavadaLabs_NodeTable"("node_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_GPULockTable_gpu_id_fkey') THEN
        ALTER TABLE "CavadaLabs_GPULockTable" ADD CONSTRAINT "CavadaLabs_GPULockTable_gpu_id_fkey" FOREIGN KEY ("gpu_id") REFERENCES "CavadaLabs_GPUTable"("gpu_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_GPULockTable_project_id_fkey') THEN
        ALTER TABLE "CavadaLabs_GPULockTable" ADD CONSTRAINT "CavadaLabs_GPULockTable_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "CavadaLabs_ProjectTable"("project_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
END $$;
