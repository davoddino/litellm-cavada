import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.cavadalabs.compliance import CavadaLabsComplianceService
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsAISystemAssessmentCreateRequest,
    CavadaLabsComplianceDocumentCreateRequest,
    CavadaLabsComplianceEvidenceCreateRequest,
    CavadaLabsComplianceFramework,
    CavadaLabsComplianceStatus,
    CavadaLabsDataSubjectRequestCreateRequest,
    CavadaLabsDataSubjectRequestStatus,
    CavadaLabsDataSubjectRequestType,
    CavadaLabsDataSubjectRequestUpdateRequest,
    CavadaLabsProcessingActivityCreateRequest,
)


def _admin() -> UserAPIKeyAuth:
    return UserAPIKeyAuth(
        api_key="sk-test",
        user_id="admin-user",
        user_role=LitellmUserRoles.PROXY_ADMIN,
    )


def _row(**kwargs):
    defaults = {
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "created_by": "admin-user",
        "updated_by": "admin-user",
    }
    return SimpleNamespace(**{**defaults, **kwargs})


def _company_row(**kwargs):
    return _row(
        company_id=kwargs.pop("company_id", "company-1"),
        legal_name=kwargs.pop("legal_name", "ACME Spa"),
        billing_name=kwargs.pop("billing_name", None),
        vat_tax_id=kwargs.pop("vat_tax_id", None),
        billing_address=kwargs.pop("billing_address", {}),
        admin_emails=kwargs.pop("admin_emails", []),
        plan=kwargs.pop("plan", "production"),
        status=kwargs.pop("status", "active"),
        monthly_budget=kwargs.pop("monthly_budget", None),
        metadata=kwargs.pop("metadata", {}),
        retention_policy=kwargs.pop("retention_policy", {}),
        default_guardrail_policy=kwargs.pop("default_guardrail_policy", None),
        default_billing_settings=kwargs.pop("default_billing_settings", {}),
        **kwargs,
    )


def _project_row(**kwargs):
    return _row(
        project_id=kwargs.pop("project_id", "project-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        name=kwargs.pop("name", "Support"),
        status=kwargs.pop("status", "production"),
        allowed_models=kwargs.pop("allowed_models", []),
        allowed_rag_collections=kwargs.pop("allowed_rag_collections", []),
        default_chatbot_settings=kwargs.pop("default_chatbot_settings", {}),
        default_guardrail_policy=kwargs.pop("default_guardrail_policy", None),
        budget=kwargs.pop("budget", None),
        retention_policy_override=kwargs.pop("retention_policy_override", {}),
        metadata=kwargs.pop("metadata", {}),
        **kwargs,
    )


def _chatbot_row(**kwargs):
    return _row(
        chatbot_id=kwargs.pop("chatbot_id", "chatbot-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        project_id=kwargs.pop("project_id", "project-1"),
        name=kwargs.pop("name", "Support Widget"),
        status=kwargs.pop("status", "published"),
        system_prompt=kwargs.pop("system_prompt", "Answer from docs."),
        prompt_version=kwargs.pop("prompt_version", 1),
        default_language=kwargs.pop("default_language", "it"),
        model_policy_id=kwargs.pop("model_policy_id", None),
        assigned_rag_collections=kwargs.pop("assigned_rag_collections", []),
        assigned_guardrail_policy=kwargs.pop("assigned_guardrail_policy", None),
        allowed_domains=kwargs.pop("allowed_domains", ["acme.test"]),
        widget_theme_config=kwargs.pop("widget_theme_config", {}),
        fallback_message=kwargs.pop("fallback_message", None),
        transcript_retention_policy=kwargs.pop("transcript_retention_policy", {}),
        metadata=kwargs.pop("metadata", {}),
        **kwargs,
    )


def _collection_row(**kwargs):
    return _row(
        collection_id=kwargs.pop("collection_id", "collection-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        project_id=kwargs.pop("project_id", "project-1"),
        name=kwargs.pop("name", "Support FAQ"),
        description=kwargs.pop("description", None),
        scope=kwargs.pop("scope", "project"),
        status=kwargs.pop("status", "active"),
        source_type=kwargs.pop("source_type", "upload"),
        vector_store_provider=kwargs.pop("vector_store_provider", "pgvector"),
        vector_store_id=kwargs.pop("vector_store_id", "vs-1"),
        embedding_model=kwargs.pop("embedding_model", "text-embedding-3-large"),
        chunking_strategy=kwargs.pop("chunking_strategy", {}),
        access_policy=kwargs.pop("access_policy", {}),
        retention_policy=kwargs.pop("retention_policy", {}),
        metadata=kwargs.pop("metadata", {}),
        **kwargs,
    )


def _document_row(**kwargs):
    return _row(
        document_id=kwargs.pop("document_id", "document-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        project_id=kwargs.pop("project_id", "project-1"),
        chatbot_id=kwargs.pop("chatbot_id", "chatbot-1"),
        collection_id=kwargs.pop("collection_id", None),
        framework=kwargs.pop("framework", "gdpr"),
        document_type=kwargs.pop("document_type", "dpia"),
        title=kwargs.pop("title", "DPIA"),
        version=kwargs.pop("version", 1),
        status=kwargs.pop("status", "published"),
        locale=kwargs.pop("locale", "en"),
        content=kwargs.pop("content", "DPIA content"),
        content_format=kwargs.pop("content_format", "markdown"),
        checksum=kwargs.pop("checksum", "checksum"),
        generated_from=kwargs.pop("generated_from", {}),
        metadata=kwargs.pop("metadata", {}),
        approved_by=kwargs.pop("approved_by", None),
        approved_at=kwargs.pop("approved_at", None),
        published_at=kwargs.pop("published_at", datetime.now(timezone.utc)),
        valid_from=kwargs.pop("valid_from", None),
        valid_until=kwargs.pop("valid_until", None),
        **kwargs,
    )


def _evidence_row(**kwargs):
    return _row(
        evidence_id=kwargs.pop("evidence_id", "evidence-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        project_id=kwargs.pop("project_id", "project-1"),
        chatbot_id=kwargs.pop("chatbot_id", None),
        collection_id=kwargs.pop("collection_id", "collection-1"),
        framework=kwargs.pop("framework", "gdpr"),
        evidence_type=kwargs.pop("evidence_type", "rag_deletion_certificate"),
        title=kwargs.pop("title", "RAG deletion certificate"),
        status=kwargs.pop("status", "active"),
        source_type=kwargs.pop("source_type", "rag_collection"),
        source_id=kwargs.pop("source_id", "collection-1"),
        content=kwargs.pop("content", {"deleted_documents": 3}),
        checksum=kwargs.pop("checksum", "checksum"),
        captured_at=kwargs.pop("captured_at", datetime.now(timezone.utc)),
        expires_at=kwargs.pop("expires_at", None),
        metadata=kwargs.pop("metadata", {}),
        **kwargs,
    )


def _processing_activity_row(**kwargs):
    return _row(
        activity_id=kwargs.pop("activity_id", "activity-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        project_id=kwargs.pop("project_id", "project-1"),
        name=kwargs.pop("name", "Customer support chatbot"),
        status=kwargs.pop("status", "active"),
        controller=kwargs.pop("controller", "ACME"),
        processor=kwargs.pop("processor", "CavadaLabs"),
        purpose=kwargs.pop("purpose", "Customer support automation"),
        legal_basis=kwargs.pop("legal_basis", "contract"),
        data_categories=kwargs.pop("data_categories", ["support_messages"]),
        data_subject_categories=kwargs.pop("data_subject_categories", ["customers"]),
        recipients=kwargs.pop("recipients", ["CavadaLabs"]),
        transfer_countries=kwargs.pop("transfer_countries", ["IT"]),
        retention_period=kwargs.pop("retention_period", "90 days"),
        security_measures=kwargs.pop("security_measures", ["encryption"]),
        metadata=kwargs.pop("metadata", {}),
        **kwargs,
    )


def _dsr_row(**kwargs):
    return _row(
        dsr_id=kwargs.pop("dsr_id", "dsr-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        project_id=kwargs.pop("project_id", "project-1"),
        requester_email=kwargs.pop("requester_email", "user@example.com"),
        request_type=kwargs.pop("request_type", "erasure"),
        status=kwargs.pop("status", "received"),
        received_at=kwargs.pop("received_at", datetime.now(timezone.utc)),
        due_at=kwargs.pop("due_at", datetime.now(timezone.utc)),
        identity_verified_at=kwargs.pop("identity_verified_at", None),
        completed_at=kwargs.pop("completed_at", None),
        assigned_to=kwargs.pop("assigned_to", None),
        scope=kwargs.pop("scope", {}),
        result=kwargs.pop("result", {}),
        metadata=kwargs.pop("metadata", {}),
        **kwargs,
    )


def _assessment_row(**kwargs):
    return _row(
        assessment_id=kwargs.pop("assessment_id", "assessment-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        project_id=kwargs.pop("project_id", "project-1"),
        chatbot_id=kwargs.pop("chatbot_id", "chatbot-1"),
        name=kwargs.pop("name", "Support chatbot"),
        version=kwargs.pop("version", 1),
        status=kwargs.pop("status", "draft"),
        risk_classification=kwargs.pop("risk_classification", "limited"),
        intended_purpose=kwargs.pop("intended_purpose", "Customer support"),
        prohibited_practice_review=kwargs.pop("prohibited_practice_review", {}),
        human_oversight=kwargs.pop("human_oversight", {"handoff": True}),
        transparency_notice=kwargs.pop("transparency_notice", "AI assistant"),
        model_provider_metadata=kwargs.pop("model_provider_metadata", {}),
        evaluation_evidence=kwargs.pop("evaluation_evidence", {}),
        approved_by=kwargs.pop("approved_by", None),
        approved_at=kwargs.pop("approved_at", None),
        metadata=kwargs.pop("metadata", {}),
        **kwargs,
    )


def _service():
    prisma_client = MagicMock()
    prisma_client.db = MagicMock()
    prisma_client.db.cavadalabs_companytable = MagicMock()
    prisma_client.db.cavadalabs_projecttable = MagicMock()
    prisma_client.db.cavadalabs_chatbottable = MagicMock()
    prisma_client.db.cavadalabs_ragcollectiontable = MagicMock()
    prisma_client.db.cavadalabs_compliancedocumenttable = MagicMock()
    prisma_client.db.cavadalabs_complianceevidencetable = MagicMock()
    prisma_client.db.cavadalabs_processingactivitytable = MagicMock()
    prisma_client.db.cavadalabs_datasubjectrequesttable = MagicMock()
    prisma_client.db.cavadalabs_aisystemassessmenttable = MagicMock()
    prisma_client.db.cavadalabs_auditlogtable = MagicMock()
    prisma_client.db.cavadalabs_auditlogtable.create = AsyncMock()
    return CavadaLabsComplianceService(prisma_client), prisma_client


@pytest.mark.asyncio
async def test_should_create_published_compliance_document_with_checksum_and_audit():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_companytable.find_unique = AsyncMock(
        return_value=_company_row()
    )
    prisma_client.db.cavadalabs_chatbottable.find_unique = AsyncMock(
        return_value=_chatbot_row()
    )

    def _create_document(*, data):
        assert data["project_id"] == "project-1"
        assert data["published_at"] is not None
        assert data["checksum"]
        assert data["content"] == "DPIA content"
        assert json.loads(data["generated_from"]) == {}
        assert json.loads(data["metadata"]) == {}
        return _document_row(**data)

    prisma_client.db.cavadalabs_compliancedocumenttable.create = AsyncMock(
        side_effect=_create_document
    )

    response = await service.create_document(
        CavadaLabsComplianceDocumentCreateRequest(
            company_id="company-1",
            chatbot_id="chatbot-1",
            framework=CavadaLabsComplianceFramework.GDPR,
            document_type="DPIA",
            title="DPIA",
            status=CavadaLabsComplianceStatus.PUBLISHED,
            content="DPIA content",
        ),
        _admin(),
    )

    assert response.project_id == "project-1"
    assert response.status == "published"
    prisma_client.db.cavadalabs_auditlogtable.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_should_serialize_compliance_evidence_content_without_coercing_document_content():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_companytable.find_unique = AsyncMock(
        return_value=_company_row()
    )
    prisma_client.db.cavadalabs_ragcollectiontable.find_unique = AsyncMock(
        return_value=_collection_row()
    )

    def _create_evidence(*, data):
        assert json.loads(data["content"]) == {"deleted_documents": 3}
        assert json.loads(data["metadata"]) == {}
        return _evidence_row(**data)

    prisma_client.db.cavadalabs_complianceevidencetable.create = AsyncMock(
        side_effect=_create_evidence
    )

    response = await service.create_evidence(
        CavadaLabsComplianceEvidenceCreateRequest(
            company_id="company-1",
            collection_id="collection-1",
            framework=CavadaLabsComplianceFramework.GDPR,
            evidence_type="rag_deletion_certificate",
            title="RAG deletion certificate",
            content={"deleted_documents": 3},
        ),
        _admin(),
    )

    assert response.content == {"deleted_documents": 3}
    prisma_client.db.cavadalabs_auditlogtable.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_should_reject_compliance_evidence_for_collection_in_other_company():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_companytable.find_unique = AsyncMock(
        return_value=_company_row(company_id="company-1")
    )
    prisma_client.db.cavadalabs_ragcollectiontable.find_unique = AsyncMock(
        return_value=_collection_row(company_id="company-2")
    )

    with pytest.raises(HTTPException) as exc:
        await service.create_evidence(
            CavadaLabsComplianceEvidenceCreateRequest(
                company_id="company-1",
                collection_id="collection-1",
                framework=CavadaLabsComplianceFramework.GDPR,
                evidence_type="rag_deletion_certificate",
                title="RAG deletion certificate",
                content={"deleted_documents": 3},
            ),
            _admin(),
        )

    assert exc.value.status_code == 400
    prisma_client.db.cavadalabs_complianceevidencetable.create.assert_not_called()


@pytest.mark.asyncio
async def test_should_create_processing_activity_for_project_scope():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_companytable.find_unique = AsyncMock(
        return_value=_company_row()
    )
    prisma_client.db.cavadalabs_projecttable.find_unique = AsyncMock(
        return_value=_project_row()
    )
    prisma_client.db.cavadalabs_processingactivitytable.create = AsyncMock(
        return_value=_processing_activity_row()
    )

    response = await service.create_processing_activity(
        CavadaLabsProcessingActivityCreateRequest(
            company_id="company-1",
            project_id="project-1",
            name="Customer support chatbot",
            purpose="Customer support automation",
            data_categories=["support_messages", "support_messages"],
            data_subject_categories=["customers"],
        ),
        _admin(),
    )

    assert response.activity_id == "activity-1"
    assert response.data_categories == ["support_messages"]


@pytest.mark.asyncio
async def test_should_default_dsr_due_date_and_complete_workflow():
    service, prisma_client = _service()
    received_at = datetime(2026, 5, 15, tzinfo=timezone.utc)
    prisma_client.db.cavadalabs_companytable.find_unique = AsyncMock(
        return_value=_company_row()
    )

    def _create_dsr(*, data):
        assert data["due_at"] == received_at.replace(day=14, month=6)
        assert json.loads(data["scope"]) == {}
        assert json.loads(data["result"]) == {}
        return _dsr_row(**data)

    prisma_client.db.cavadalabs_datasubjectrequesttable.create = AsyncMock(
        side_effect=_create_dsr
    )

    response = await service.create_data_subject_request(
        CavadaLabsDataSubjectRequestCreateRequest(
            company_id="company-1",
            requester_email="USER@EXAMPLE.COM",
            request_type=CavadaLabsDataSubjectRequestType.ERASURE,
            received_at=received_at,
        ),
        _admin(),
    )

    assert response.requester_email == "user@example.com"
    assert response.due_at == received_at.replace(day=14, month=6)

    prisma_client.db.cavadalabs_datasubjectrequesttable.find_unique = AsyncMock(
        return_value=_dsr_row(received_at=received_at, due_at=response.due_at)
    )
    prisma_client.db.cavadalabs_projecttable.find_unique = AsyncMock(
        return_value=_project_row()
    )
    prisma_client.db.cavadalabs_datasubjectrequesttable.update = AsyncMock(
        return_value=_dsr_row(
            status="completed",
            received_at=received_at,
            due_at=response.due_at,
            completed_at=datetime.now(timezone.utc),
        )
    )

    completed = await service.update_data_subject_request(
        "dsr-1",
        CavadaLabsDataSubjectRequestUpdateRequest(
            status=CavadaLabsDataSubjectRequestStatus.COMPLETED,
            result={"deleted_sessions": ["session-1"]},
        ),
        _admin(),
    )

    update_payload = (
        prisma_client.db.cavadalabs_datasubjectrequesttable.update.call_args.kwargs[
            "data"
        ]
    )
    assert update_payload["completed_at"] is not None
    assert json.loads(update_payload["result"]) == {"deleted_sessions": ["session-1"]}
    assert completed.status == "completed"


@pytest.mark.asyncio
async def test_should_reject_ai_assessment_when_chatbot_project_mismatches():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_companytable.find_unique = AsyncMock(
        return_value=_company_row()
    )
    prisma_client.db.cavadalabs_projecttable.find_unique = AsyncMock(
        return_value=_project_row(project_id="project-1")
    )
    prisma_client.db.cavadalabs_chatbottable.find_unique = AsyncMock(
        return_value=_chatbot_row(project_id="project-2")
    )

    with pytest.raises(HTTPException) as exc:
        await service.create_ai_system_assessment(
            CavadaLabsAISystemAssessmentCreateRequest(
                company_id="company-1",
                project_id="project-1",
                chatbot_id="chatbot-1",
                name="Support chatbot",
                intended_purpose="Customer support",
            ),
            _admin(),
        )

    assert exc.value.status_code == 400
    prisma_client.db.cavadalabs_aisystemassessmenttable.create.assert_not_called()
