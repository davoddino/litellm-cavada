CREATE TABLE IF NOT EXISTS "CavadaLabs_ComplianceDocumentTable" (
    "document_id" TEXT NOT NULL,
    "company_id" TEXT NOT NULL,
    "project_id" TEXT,
    "chatbot_id" TEXT,
    "collection_id" TEXT,
    "framework" TEXT NOT NULL DEFAULT 'gdpr',
    "document_type" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "version" INTEGER NOT NULL DEFAULT 1,
    "status" TEXT NOT NULL DEFAULT 'draft',
    "locale" TEXT NOT NULL DEFAULT 'en',
    "content" TEXT NOT NULL DEFAULT '',
    "content_format" TEXT NOT NULL DEFAULT 'markdown',
    "checksum" TEXT NOT NULL,
    "generated_from" JSONB NOT NULL DEFAULT '{}',
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "approved_by" TEXT,
    "approved_at" TIMESTAMP(3),
    "published_at" TIMESTAMP(3),
    "valid_from" TIMESTAMP(3),
    "valid_until" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_by" TEXT NOT NULL,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_by" TEXT NOT NULL,
    CONSTRAINT "CavadaLabs_ComplianceDocumentTable_pkey" PRIMARY KEY ("document_id")
);

CREATE TABLE IF NOT EXISTS "CavadaLabs_ComplianceEvidenceTable" (
    "evidence_id" TEXT NOT NULL,
    "company_id" TEXT NOT NULL,
    "project_id" TEXT,
    "chatbot_id" TEXT,
    "collection_id" TEXT,
    "framework" TEXT NOT NULL,
    "evidence_type" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'active',
    "source_type" TEXT,
    "source_id" TEXT,
    "content" JSONB NOT NULL DEFAULT '{}',
    "checksum" TEXT NOT NULL,
    "captured_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "expires_at" TIMESTAMP(3),
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_by" TEXT NOT NULL,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_by" TEXT NOT NULL,
    CONSTRAINT "CavadaLabs_ComplianceEvidenceTable_pkey" PRIMARY KEY ("evidence_id")
);

CREATE TABLE IF NOT EXISTS "CavadaLabs_ProcessingActivityTable" (
    "activity_id" TEXT NOT NULL,
    "company_id" TEXT NOT NULL,
    "project_id" TEXT,
    "name" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'active',
    "controller" TEXT,
    "processor" TEXT,
    "purpose" TEXT NOT NULL,
    "legal_basis" TEXT,
    "data_categories" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "data_subject_categories" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "recipients" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "transfer_countries" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "retention_period" TEXT,
    "security_measures" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_by" TEXT NOT NULL,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_by" TEXT NOT NULL,
    CONSTRAINT "CavadaLabs_ProcessingActivityTable_pkey" PRIMARY KEY ("activity_id")
);

CREATE TABLE IF NOT EXISTS "CavadaLabs_DataSubjectRequestTable" (
    "dsr_id" TEXT NOT NULL,
    "company_id" TEXT NOT NULL,
    "project_id" TEXT,
    "requester_email" TEXT NOT NULL,
    "request_type" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'received',
    "received_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "due_at" TIMESTAMP(3) NOT NULL,
    "identity_verified_at" TIMESTAMP(3),
    "completed_at" TIMESTAMP(3),
    "assigned_to" TEXT,
    "scope" JSONB NOT NULL DEFAULT '{}',
    "result" JSONB NOT NULL DEFAULT '{}',
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_by" TEXT NOT NULL,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_by" TEXT NOT NULL,
    CONSTRAINT "CavadaLabs_DataSubjectRequestTable_pkey" PRIMARY KEY ("dsr_id")
);

CREATE TABLE IF NOT EXISTS "CavadaLabs_AISystemAssessmentTable" (
    "assessment_id" TEXT NOT NULL,
    "company_id" TEXT NOT NULL,
    "project_id" TEXT,
    "chatbot_id" TEXT,
    "name" TEXT NOT NULL,
    "version" INTEGER NOT NULL DEFAULT 1,
    "status" TEXT NOT NULL DEFAULT 'draft',
    "risk_classification" TEXT NOT NULL DEFAULT 'unknown',
    "intended_purpose" TEXT NOT NULL,
    "prohibited_practice_review" JSONB NOT NULL DEFAULT '{}',
    "human_oversight" JSONB NOT NULL DEFAULT '{}',
    "transparency_notice" TEXT,
    "model_provider_metadata" JSONB NOT NULL DEFAULT '{}',
    "evaluation_evidence" JSONB NOT NULL DEFAULT '{}',
    "approved_by" TEXT,
    "approved_at" TIMESTAMP(3),
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_by" TEXT NOT NULL,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_by" TEXT NOT NULL,
    CONSTRAINT "CavadaLabs_AISystemAssessmentTable_pkey" PRIMARY KEY ("assessment_id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_ComplianceDocumentTable_scope_version_key" ON "CavadaLabs_ComplianceDocumentTable"("company_id", "project_id", "chatbot_id", "collection_id", "framework", "document_type", "version");
CREATE INDEX IF NOT EXISTS "CavadaLabs_ComplianceDocumentTable_company_id_framework_document_type_idx" ON "CavadaLabs_ComplianceDocumentTable"("company_id", "framework", "document_type");
CREATE INDEX IF NOT EXISTS "CavadaLabs_ComplianceDocumentTable_project_id_framework_idx" ON "CavadaLabs_ComplianceDocumentTable"("project_id", "framework");
CREATE INDEX IF NOT EXISTS "CavadaLabs_ComplianceDocumentTable_chatbot_id_framework_idx" ON "CavadaLabs_ComplianceDocumentTable"("chatbot_id", "framework");
CREATE INDEX IF NOT EXISTS "CavadaLabs_ComplianceDocumentTable_collection_id_framework_idx" ON "CavadaLabs_ComplianceDocumentTable"("collection_id", "framework");
CREATE INDEX IF NOT EXISTS "CavadaLabs_ComplianceDocumentTable_status_published_at_idx" ON "CavadaLabs_ComplianceDocumentTable"("status", "published_at");
CREATE INDEX IF NOT EXISTS "CavadaLabs_ComplianceDocumentTable_checksum_idx" ON "CavadaLabs_ComplianceDocumentTable"("checksum");

CREATE INDEX IF NOT EXISTS "CavadaLabs_ComplianceEvidenceTable_company_id_framework_evidence_type_idx" ON "CavadaLabs_ComplianceEvidenceTable"("company_id", "framework", "evidence_type");
CREATE INDEX IF NOT EXISTS "CavadaLabs_ComplianceEvidenceTable_project_id_framework_idx" ON "CavadaLabs_ComplianceEvidenceTable"("project_id", "framework");
CREATE INDEX IF NOT EXISTS "CavadaLabs_ComplianceEvidenceTable_chatbot_id_framework_idx" ON "CavadaLabs_ComplianceEvidenceTable"("chatbot_id", "framework");
CREATE INDEX IF NOT EXISTS "CavadaLabs_ComplianceEvidenceTable_collection_id_framework_idx" ON "CavadaLabs_ComplianceEvidenceTable"("collection_id", "framework");
CREATE INDEX IF NOT EXISTS "CavadaLabs_ComplianceEvidenceTable_source_type_source_id_idx" ON "CavadaLabs_ComplianceEvidenceTable"("source_type", "source_id");
CREATE INDEX IF NOT EXISTS "CavadaLabs_ComplianceEvidenceTable_status_captured_at_idx" ON "CavadaLabs_ComplianceEvidenceTable"("status", "captured_at");
CREATE INDEX IF NOT EXISTS "CavadaLabs_ComplianceEvidenceTable_checksum_idx" ON "CavadaLabs_ComplianceEvidenceTable"("checksum");

CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_ProcessingActivityTable_company_project_name_key" ON "CavadaLabs_ProcessingActivityTable"("company_id", "project_id", "name");
CREATE INDEX IF NOT EXISTS "CavadaLabs_ProcessingActivityTable_company_id_status_idx" ON "CavadaLabs_ProcessingActivityTable"("company_id", "status");
CREATE INDEX IF NOT EXISTS "CavadaLabs_ProcessingActivityTable_project_id_status_idx" ON "CavadaLabs_ProcessingActivityTable"("project_id", "status");

CREATE INDEX IF NOT EXISTS "CavadaLabs_DataSubjectRequestTable_company_id_status_due_at_idx" ON "CavadaLabs_DataSubjectRequestTable"("company_id", "status", "due_at");
CREATE INDEX IF NOT EXISTS "CavadaLabs_DataSubjectRequestTable_project_id_status_idx" ON "CavadaLabs_DataSubjectRequestTable"("project_id", "status");
CREATE INDEX IF NOT EXISTS "CavadaLabs_DataSubjectRequestTable_requester_email_idx" ON "CavadaLabs_DataSubjectRequestTable"("requester_email");
CREATE INDEX IF NOT EXISTS "CavadaLabs_DataSubjectRequestTable_request_type_status_idx" ON "CavadaLabs_DataSubjectRequestTable"("request_type", "status");

CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_AISystemAssessmentTable_scope_version_key" ON "CavadaLabs_AISystemAssessmentTable"("company_id", "project_id", "chatbot_id", "name", "version");
CREATE INDEX IF NOT EXISTS "CavadaLabs_AISystemAssessmentTable_company_id_status_idx" ON "CavadaLabs_AISystemAssessmentTable"("company_id", "status");
CREATE INDEX IF NOT EXISTS "CavadaLabs_AISystemAssessmentTable_project_id_status_idx" ON "CavadaLabs_AISystemAssessmentTable"("project_id", "status");
CREATE INDEX IF NOT EXISTS "CavadaLabs_AISystemAssessmentTable_chatbot_id_status_idx" ON "CavadaLabs_AISystemAssessmentTable"("chatbot_id", "status");
CREATE INDEX IF NOT EXISTS "CavadaLabs_AISystemAssessmentTable_risk_classification_status_idx" ON "CavadaLabs_AISystemAssessmentTable"("risk_classification", "status");

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_ComplianceDocumentTable_company_id_fkey') THEN
        ALTER TABLE "CavadaLabs_ComplianceDocumentTable" ADD CONSTRAINT "CavadaLabs_ComplianceDocumentTable_company_id_fkey" FOREIGN KEY ("company_id") REFERENCES "CavadaLabs_CompanyTable"("company_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_ComplianceDocumentTable_project_id_fkey') THEN
        ALTER TABLE "CavadaLabs_ComplianceDocumentTable" ADD CONSTRAINT "CavadaLabs_ComplianceDocumentTable_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "CavadaLabs_ProjectTable"("project_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_ComplianceDocumentTable_chatbot_id_fkey') THEN
        ALTER TABLE "CavadaLabs_ComplianceDocumentTable" ADD CONSTRAINT "CavadaLabs_ComplianceDocumentTable_chatbot_id_fkey" FOREIGN KEY ("chatbot_id") REFERENCES "CavadaLabs_ChatbotTable"("chatbot_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_ComplianceDocumentTable_collection_id_fkey') THEN
        ALTER TABLE "CavadaLabs_ComplianceDocumentTable" ADD CONSTRAINT "CavadaLabs_ComplianceDocumentTable_collection_id_fkey" FOREIGN KEY ("collection_id") REFERENCES "CavadaLabs_RAGCollectionTable"("collection_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_ComplianceEvidenceTable_company_id_fkey') THEN
        ALTER TABLE "CavadaLabs_ComplianceEvidenceTable" ADD CONSTRAINT "CavadaLabs_ComplianceEvidenceTable_company_id_fkey" FOREIGN KEY ("company_id") REFERENCES "CavadaLabs_CompanyTable"("company_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_ComplianceEvidenceTable_project_id_fkey') THEN
        ALTER TABLE "CavadaLabs_ComplianceEvidenceTable" ADD CONSTRAINT "CavadaLabs_ComplianceEvidenceTable_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "CavadaLabs_ProjectTable"("project_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_ComplianceEvidenceTable_chatbot_id_fkey') THEN
        ALTER TABLE "CavadaLabs_ComplianceEvidenceTable" ADD CONSTRAINT "CavadaLabs_ComplianceEvidenceTable_chatbot_id_fkey" FOREIGN KEY ("chatbot_id") REFERENCES "CavadaLabs_ChatbotTable"("chatbot_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_ComplianceEvidenceTable_collection_id_fkey') THEN
        ALTER TABLE "CavadaLabs_ComplianceEvidenceTable" ADD CONSTRAINT "CavadaLabs_ComplianceEvidenceTable_collection_id_fkey" FOREIGN KEY ("collection_id") REFERENCES "CavadaLabs_RAGCollectionTable"("collection_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_ProcessingActivityTable_company_id_fkey') THEN
        ALTER TABLE "CavadaLabs_ProcessingActivityTable" ADD CONSTRAINT "CavadaLabs_ProcessingActivityTable_company_id_fkey" FOREIGN KEY ("company_id") REFERENCES "CavadaLabs_CompanyTable"("company_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_ProcessingActivityTable_project_id_fkey') THEN
        ALTER TABLE "CavadaLabs_ProcessingActivityTable" ADD CONSTRAINT "CavadaLabs_ProcessingActivityTable_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "CavadaLabs_ProjectTable"("project_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_DataSubjectRequestTable_company_id_fkey') THEN
        ALTER TABLE "CavadaLabs_DataSubjectRequestTable" ADD CONSTRAINT "CavadaLabs_DataSubjectRequestTable_company_id_fkey" FOREIGN KEY ("company_id") REFERENCES "CavadaLabs_CompanyTable"("company_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_DataSubjectRequestTable_project_id_fkey') THEN
        ALTER TABLE "CavadaLabs_DataSubjectRequestTable" ADD CONSTRAINT "CavadaLabs_DataSubjectRequestTable_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "CavadaLabs_ProjectTable"("project_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_AISystemAssessmentTable_company_id_fkey') THEN
        ALTER TABLE "CavadaLabs_AISystemAssessmentTable" ADD CONSTRAINT "CavadaLabs_AISystemAssessmentTable_company_id_fkey" FOREIGN KEY ("company_id") REFERENCES "CavadaLabs_CompanyTable"("company_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_AISystemAssessmentTable_project_id_fkey') THEN
        ALTER TABLE "CavadaLabs_AISystemAssessmentTable" ADD CONSTRAINT "CavadaLabs_AISystemAssessmentTable_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "CavadaLabs_ProjectTable"("project_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_AISystemAssessmentTable_chatbot_id_fkey') THEN
        ALTER TABLE "CavadaLabs_AISystemAssessmentTable" ADD CONSTRAINT "CavadaLabs_AISystemAssessmentTable_chatbot_id_fkey" FOREIGN KEY ("chatbot_id") REFERENCES "CavadaLabs_ChatbotTable"("chatbot_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
END $$;
