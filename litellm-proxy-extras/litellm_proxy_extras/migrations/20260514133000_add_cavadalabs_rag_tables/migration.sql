CREATE TABLE IF NOT EXISTS "CavadaLabs_RAGCollectionTable" (
    "collection_id" TEXT NOT NULL,
    "company_id" TEXT NOT NULL,
    "project_id" TEXT,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "scope" TEXT NOT NULL DEFAULT 'project',
    "status" TEXT NOT NULL DEFAULT 'draft',
    "source_type" TEXT,
    "vector_store_provider" TEXT,
    "vector_store_id" TEXT,
    "embedding_model" TEXT,
    "chunking_strategy" JSONB NOT NULL DEFAULT '{}',
    "access_policy" JSONB NOT NULL DEFAULT '{}',
    "retention_policy" JSONB NOT NULL DEFAULT '{}',
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_by" TEXT NOT NULL,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_by" TEXT NOT NULL,
    CONSTRAINT "CavadaLabs_RAGCollectionTable_pkey" PRIMARY KEY ("collection_id")
);

CREATE TABLE IF NOT EXISTS "CavadaLabs_RAGDocumentTable" (
    "document_id" TEXT NOT NULL,
    "collection_id" TEXT NOT NULL,
    "company_id" TEXT NOT NULL,
    "project_id" TEXT,
    "source_uri" TEXT,
    "file_name" TEXT,
    "mime_type" TEXT,
    "status" TEXT NOT NULL DEFAULT 'queued',
    "content_hash" TEXT,
    "byte_size" INTEGER,
    "token_count" INTEGER,
    "chunk_count" INTEGER NOT NULL DEFAULT 0,
    "last_indexed_at" TIMESTAMP(3),
    "failure_reason" TEXT,
    "version" INTEGER NOT NULL DEFAULT 1,
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_by" TEXT NOT NULL,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_by" TEXT NOT NULL,
    CONSTRAINT "CavadaLabs_RAGDocumentTable_pkey" PRIMARY KEY ("document_id")
);

CREATE TABLE IF NOT EXISTS "CavadaLabs_ChatbotRAGAssignmentTable" (
    "assignment_id" TEXT NOT NULL,
    "company_id" TEXT NOT NULL,
    "project_id" TEXT NOT NULL,
    "chatbot_id" TEXT NOT NULL,
    "collection_id" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'active',
    "priority" INTEGER NOT NULL DEFAULT 100,
    "retrieval_config" JSONB NOT NULL DEFAULT '{}',
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_by" TEXT NOT NULL,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_by" TEXT NOT NULL,
    CONSTRAINT "CavadaLabs_ChatbotRAGAssignmentTable_pkey" PRIMARY KEY ("assignment_id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_RAGCollectionTable_company_id_name_key" ON "CavadaLabs_RAGCollectionTable"("company_id", "name");
CREATE INDEX IF NOT EXISTS "CavadaLabs_RAGCollectionTable_company_id_status_idx" ON "CavadaLabs_RAGCollectionTable"("company_id", "status");
CREATE INDEX IF NOT EXISTS "CavadaLabs_RAGCollectionTable_project_id_status_idx" ON "CavadaLabs_RAGCollectionTable"("project_id", "status");
CREATE INDEX IF NOT EXISTS "CavadaLabs_RAGCollectionTable_vector_store_provider_vector_store_id_idx" ON "CavadaLabs_RAGCollectionTable"("vector_store_provider", "vector_store_id");

CREATE INDEX IF NOT EXISTS "CavadaLabs_RAGDocumentTable_collection_id_status_idx" ON "CavadaLabs_RAGDocumentTable"("collection_id", "status");
CREATE INDEX IF NOT EXISTS "CavadaLabs_RAGDocumentTable_company_id_created_at_idx" ON "CavadaLabs_RAGDocumentTable"("company_id", "created_at");
CREATE INDEX IF NOT EXISTS "CavadaLabs_RAGDocumentTable_project_id_created_at_idx" ON "CavadaLabs_RAGDocumentTable"("project_id", "created_at");
CREATE INDEX IF NOT EXISTS "CavadaLabs_RAGDocumentTable_content_hash_idx" ON "CavadaLabs_RAGDocumentTable"("content_hash");

CREATE UNIQUE INDEX IF NOT EXISTS "CavadaLabs_ChatbotRAGAssignmentTable_chatbot_id_collection_id_key" ON "CavadaLabs_ChatbotRAGAssignmentTable"("chatbot_id", "collection_id");
CREATE INDEX IF NOT EXISTS "CavadaLabs_ChatbotRAGAssignmentTable_company_id_project_id_status_idx" ON "CavadaLabs_ChatbotRAGAssignmentTable"("company_id", "project_id", "status");
CREATE INDEX IF NOT EXISTS "CavadaLabs_ChatbotRAGAssignmentTable_collection_id_status_idx" ON "CavadaLabs_ChatbotRAGAssignmentTable"("collection_id", "status");
CREATE INDEX IF NOT EXISTS "CavadaLabs_ChatbotRAGAssignmentTable_priority_idx" ON "CavadaLabs_ChatbotRAGAssignmentTable"("priority");

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_RAGCollectionTable_company_id_fkey') THEN
        ALTER TABLE "CavadaLabs_RAGCollectionTable" ADD CONSTRAINT "CavadaLabs_RAGCollectionTable_company_id_fkey" FOREIGN KEY ("company_id") REFERENCES "CavadaLabs_CompanyTable"("company_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_RAGCollectionTable_project_id_fkey') THEN
        ALTER TABLE "CavadaLabs_RAGCollectionTable" ADD CONSTRAINT "CavadaLabs_RAGCollectionTable_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "CavadaLabs_ProjectTable"("project_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_RAGDocumentTable_collection_id_fkey') THEN
        ALTER TABLE "CavadaLabs_RAGDocumentTable" ADD CONSTRAINT "CavadaLabs_RAGDocumentTable_collection_id_fkey" FOREIGN KEY ("collection_id") REFERENCES "CavadaLabs_RAGCollectionTable"("collection_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_RAGDocumentTable_company_id_fkey') THEN
        ALTER TABLE "CavadaLabs_RAGDocumentTable" ADD CONSTRAINT "CavadaLabs_RAGDocumentTable_company_id_fkey" FOREIGN KEY ("company_id") REFERENCES "CavadaLabs_CompanyTable"("company_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_RAGDocumentTable_project_id_fkey') THEN
        ALTER TABLE "CavadaLabs_RAGDocumentTable" ADD CONSTRAINT "CavadaLabs_RAGDocumentTable_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "CavadaLabs_ProjectTable"("project_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_ChatbotRAGAssignmentTable_company_id_fkey') THEN
        ALTER TABLE "CavadaLabs_ChatbotRAGAssignmentTable" ADD CONSTRAINT "CavadaLabs_ChatbotRAGAssignmentTable_company_id_fkey" FOREIGN KEY ("company_id") REFERENCES "CavadaLabs_CompanyTable"("company_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_ChatbotRAGAssignmentTable_project_id_fkey') THEN
        ALTER TABLE "CavadaLabs_ChatbotRAGAssignmentTable" ADD CONSTRAINT "CavadaLabs_ChatbotRAGAssignmentTable_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "CavadaLabs_ProjectTable"("project_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_ChatbotRAGAssignmentTable_chatbot_id_fkey') THEN
        ALTER TABLE "CavadaLabs_ChatbotRAGAssignmentTable" ADD CONSTRAINT "CavadaLabs_ChatbotRAGAssignmentTable_chatbot_id_fkey" FOREIGN KEY ("chatbot_id") REFERENCES "CavadaLabs_ChatbotTable"("chatbot_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'CavadaLabs_ChatbotRAGAssignmentTable_collection_id_fkey') THEN
        ALTER TABLE "CavadaLabs_ChatbotRAGAssignmentTable" ADD CONSTRAINT "CavadaLabs_ChatbotRAGAssignmentTable_collection_id_fkey" FOREIGN KEY ("collection_id") REFERENCES "CavadaLabs_RAGCollectionTable"("collection_id") ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
END $$;
