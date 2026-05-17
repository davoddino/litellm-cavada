from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from litellm.proxy import proxy_server
from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.cavadalabs.dispatcher import (
    CavadaLabsDispatcherService,
    CavadaLabsRuntimeContext,
)
from litellm.proxy.cavadalabs.rag import CavadaLabsRAGService
from litellm.proxy.cavadalabs.rag_runtime import (
    CavadaLabsRAGContext,
    CavadaLabsRAGRuntimeService,
    CavadaLabsRAGSource,
)
from litellm.proxy.management_endpoints import (
    cavadalabs_rag_endpoints as rag_endpoints,
)
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsChatCompletionRequest,
    CavadaLabsChatbotRAGAssignmentCreateRequest,
    CavadaLabsChatbotRAGAssignmentUpdateRequest,
    CavadaLabsChatbotResponse,
    CavadaLabsCompanyResponse,
    CavadaLabsProjectModelPolicyResponse,
    CavadaLabsProjectResponse,
    CavadaLabsWebTokenResponse,
    CavadaLabsRAGAssignmentStatus,
    CavadaLabsRAGCollectionCreateRequest,
    CavadaLabsRAGCollectionScope,
    CavadaLabsRAGCollectionStatus,
    CavadaLabsRAGDocumentCreateRequest,
    CavadaLabsRAGDocumentStatus,
)


def _admin() -> UserAPIKeyAuth:
    return UserAPIKeyAuth(
        api_key="sk-test",
        user_id="admin-user",
        user_role=LitellmUserRoles.PROXY_ADMIN,
    )


def _internal_user() -> UserAPIKeyAuth:
    return UserAPIKeyAuth(
        api_key="sk-user",
        user_id="user-1",
        user_role=LitellmUserRoles.INTERNAL_USER,
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


def _web_token_row(**kwargs):
    return _row(
        web_token_id=kwargs.pop("web_token_id", "web-token-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        project_id=kwargs.pop("project_id", "project-1"),
        chatbot_id=kwargs.pop("chatbot_id", "chatbot-1"),
        name=kwargs.pop("name", "widget"),
        token_prefix=kwargs.pop("token_prefix", "clwt-prefix"),
        status=kwargs.pop("status", "active"),
        allowed_domains=kwargs.pop("allowed_domains", ["acme.test"]),
        allowed_origins=kwargs.pop("allowed_origins", ["https://acme.test"]),
        route_allowlist=kwargs.pop(
            "route_allowlist", ["/cavadalabs/chatbots/messages"]
        ),
        ip_rpm_limit=kwargs.pop("ip_rpm_limit", 30),
        session_rpm_limit=kwargs.pop("session_rpm_limit", 10),
        session_budget=kwargs.pop("session_budget", None),
        expires_at=kwargs.pop("expires_at", datetime.now(timezone.utc)),
        revoked_at=kwargs.pop("revoked_at", None),
        last_used_at=kwargs.pop("last_used_at", None),
        metadata=kwargs.pop("metadata", {}),
        **kwargs,
    )


def _model_policy_row(**kwargs):
    return _row(
        policy_id=kwargs.pop("policy_id", "policy-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        project_id=kwargs.pop("project_id", "project-1"),
        model_alias=kwargs.pop("model_alias", "cavadalabs/qwen3-32b"),
        provider=kwargs.pop("provider", "cavadalabs"),
        deployment_id=kwargs.pop("deployment_id", "deploy-1"),
        priority=kwargs.pop("priority", 10),
        enabled=kwargs.pop("enabled", True),
        fallback_enabled=kwargs.pop("fallback_enabled", True),
        require_json_output=kwargs.pop("require_json_output", False),
        require_no_think=kwargs.pop("require_no_think", False),
        prefer_loaded_model=kwargs.pop("prefer_loaded_model", True),
        max_cost_input=kwargs.pop("max_cost_input", None),
        max_cost_output=kwargs.pop("max_cost_output", None),
        required_capabilities=kwargs.pop("required_capabilities", []),
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
        chunking_strategy=kwargs.pop("chunking_strategy", {"max_tokens": 800}),
        access_policy=kwargs.pop("access_policy", {}),
        retention_policy=kwargs.pop("retention_policy", {}),
        metadata=kwargs.pop("metadata", {}),
        **kwargs,
    )


def _document_row(**kwargs):
    return _row(
        document_id=kwargs.pop("document_id", "document-1"),
        collection_id=kwargs.pop("collection_id", "collection-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        project_id=kwargs.pop("project_id", "project-1"),
        source_uri=kwargs.pop("source_uri", "s3://bucket/support.pdf"),
        file_name=kwargs.pop("file_name", "support.pdf"),
        mime_type=kwargs.pop("mime_type", "application/pdf"),
        status=kwargs.pop("status", "indexed"),
        content_hash=kwargs.pop("content_hash", "sha256:abc"),
        byte_size=kwargs.pop("byte_size", 1024),
        token_count=kwargs.pop("token_count", 120),
        chunk_count=kwargs.pop("chunk_count", 4),
        last_indexed_at=kwargs.pop("last_indexed_at", datetime.now(timezone.utc)),
        failure_reason=kwargs.pop("failure_reason", None),
        version=kwargs.pop("version", 1),
        metadata=kwargs.pop("metadata", {}),
        **kwargs,
    )


def _assignment_row(**kwargs):
    return _row(
        assignment_id=kwargs.pop("assignment_id", "assignment-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        project_id=kwargs.pop("project_id", "project-1"),
        chatbot_id=kwargs.pop("chatbot_id", "chatbot-1"),
        collection_id=kwargs.pop("collection_id", "collection-1"),
        status=kwargs.pop("status", "active"),
        priority=kwargs.pop("priority", 10),
        retrieval_config=kwargs.pop("retrieval_config", {"top_k": 6}),
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
    prisma_client.db.cavadalabs_ragdocumenttable = MagicMock()
    prisma_client.db.cavadalabs_chatbotragassignmenttable = MagicMock()
    prisma_client.db.cavadalabs_auditlogtable = MagicMock()
    prisma_client.db.cavadalabs_auditlogtable.create = AsyncMock()
    return CavadaLabsRAGService(prisma_client), prisma_client


def _normalize_prisma_json_row(data):
    return {key: getattr(value, "data", value) for key, value in data.items()}


def _filter_matches(value, filter_value):
    if isinstance(filter_value, dict):
        return value in filter_value.get("in", [])
    return value == filter_value


def _endpoint_project_row(project_id):
    company_id = "company-1" if project_id == "project-1" else "company-2"
    return _project_row(
        project_id=project_id,
        company_id=company_id,
        litellm_team_id=f"team-{project_id}",
    )


def _member_rows(member_type, role):
    if role is None:
        return []
    id_field = f"{member_type}_id"
    id_value = f"{member_type}-1"
    return [SimpleNamespace(**{id_field: id_value, "user_id": "user-1", "role": role})]


def _setup_company_project_tables(db):
    async def _find_company(*, where):
        return _company_row(
            company_id=where["company_id"],
            litellm_organization_id=f"org-{where['company_id']}",
        )

    async def _find_project(*, where):
        return _endpoint_project_row(where["project_id"])

    async def _find_projects(*, where=None):
        where = where or {}
        rows = [_project_row(project_id="project-1", company_id="company-1")]
        if "project_id" in where:
            rows = [
                row
                for row in rows
                if _filter_matches(row.project_id, where["project_id"])
            ]
        if "company_id" in where:
            rows = [
                row
                for row in rows
                if _filter_matches(row.company_id, where["company_id"])
            ]
        return rows

    db.cavadalabs_companytable = MagicMock()
    db.cavadalabs_companytable.find_unique = AsyncMock(side_effect=_find_company)
    db.cavadalabs_companytable.find_many = AsyncMock(return_value=[])
    db.cavadalabs_projecttable = MagicMock()
    db.cavadalabs_projecttable.find_unique = AsyncMock(side_effect=_find_project)
    db.cavadalabs_projecttable.find_many = AsyncMock(side_effect=_find_projects)


def _setup_company_project_membership_tables(db, *, company_role, project_role):
    async def _find_company_member(*, where):
        key = where["company_id_user_id"]
        if key["company_id"] == "company-1" and key["user_id"] == "user-1":
            return next(iter(_member_rows("company", company_role)), None)
        return None

    async def _find_project_member(*, where):
        key = where["project_id_user_id"]
        if key["project_id"] == "project-1" and key["user_id"] == "user-1":
            return next(iter(_member_rows("project", project_role)), None)
        return None

    db.cavadalabs_companymembertable = MagicMock()
    db.cavadalabs_companymembertable.find_unique = AsyncMock(
        side_effect=_find_company_member
    )
    db.cavadalabs_companymembertable.find_many = AsyncMock(
        return_value=_member_rows("company", company_role)
    )
    db.cavadalabs_projectmembertable = MagicMock()
    db.cavadalabs_projectmembertable.find_unique = AsyncMock(
        side_effect=_find_project_member
    )
    db.cavadalabs_projectmembertable.find_many = AsyncMock(
        return_value=_member_rows("project", project_role)
    )


def _setup_litellm_compat_membership_tables(db):
    db.litellm_organizationmembership = MagicMock()
    db.litellm_organizationmembership.find_unique = AsyncMock(return_value=None)
    db.litellm_organizationmembership.find_many = AsyncMock(return_value=[])
    db.litellm_usertable = MagicMock()
    db.litellm_usertable.find_unique = AsyncMock(return_value=None)
    db.litellm_teamtable = MagicMock()
    db.litellm_teamtable.find_unique = AsyncMock(return_value=None)


def _setup_rag_tables(db):
    async def _create_collection(*, data):
        row_data = _normalize_prisma_json_row(data)
        return _collection_row(collection_id="collection-created", **row_data)

    db.cavadalabs_ragcollectiontable = MagicMock()
    db.cavadalabs_ragcollectiontable.create = AsyncMock(side_effect=_create_collection)
    db.cavadalabs_ragcollectiontable.find_unique = AsyncMock(
        return_value=_collection_row()
    )
    db.cavadalabs_ragcollectiontable.find_many = AsyncMock(
        return_value=[_collection_row()]
    )
    db.cavadalabs_ragcollectiontable.update = AsyncMock(
        return_value=_collection_row(status="archived")
    )
    db.cavadalabs_ragdocumenttable = MagicMock()
    db.cavadalabs_ragdocumenttable.find_many = AsyncMock(return_value=[])
    db.cavadalabs_chatbotragassignmenttable = MagicMock()
    db.cavadalabs_chatbotragassignmenttable.find_many = AsyncMock(return_value=[])


def _setup_audit_table(db):
    db.cavadalabs_auditlogtable = MagicMock()
    db.cavadalabs_auditlogtable.create = AsyncMock()


def _rag_endpoint_db(company_role=None, project_role="project_admin"):
    db = MagicMock()
    _setup_company_project_tables(db)
    _setup_company_project_membership_tables(
        db,
        company_role=company_role,
        project_role=project_role,
    )
    _setup_litellm_compat_membership_tables(db)
    _setup_rag_tables(db)
    _setup_audit_table(db)
    return db


def _patch_proxy_prisma(monkeypatch, db):
    monkeypatch.setattr(proxy_server, "prisma_client", SimpleNamespace(db=db))


def _runtime_service(search_client=None):
    prisma_client = MagicMock()
    prisma_client.db = MagicMock()
    prisma_client.db.cavadalabs_chatbotragassignmenttable = MagicMock()
    prisma_client.db.cavadalabs_ragcollectiontable = MagicMock()
    return CavadaLabsRAGRuntimeService(prisma_client, search_client), prisma_client


def _runtime_context() -> CavadaLabsRuntimeContext:
    return CavadaLabsRuntimeContext(
        company=CavadaLabsCompanyResponse.model_validate(vars(_company_row())),
        project=CavadaLabsProjectResponse.model_validate(vars(_project_row())),
        chatbot=CavadaLabsChatbotResponse.model_validate(
            vars(_chatbot_row(assigned_rag_collections=["collection-1"]))
        ),
        web_token=CavadaLabsWebTokenResponse.model_validate(vars(_web_token_row())),
        primary_policy=CavadaLabsProjectModelPolicyResponse.model_validate(
            vars(_model_policy_row())
        ),
        fallback_policies=[],
    )


class _SearchClient:
    def __init__(self, response=None, exc=None):
        self.response = response or {"data": []}
        self.exc = exc
        self.calls = []

    async def search(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc is not None:
            raise self.exc
        return self.response


@pytest.mark.asyncio
async def test_should_create_project_rag_collection_for_native_project_admin(
    monkeypatch,
):
    db = _rag_endpoint_db(company_role=None, project_role="project_admin")
    _patch_proxy_prisma(monkeypatch, db)

    response = await rag_endpoints.create_rag_collection(
        data=CavadaLabsRAGCollectionCreateRequest(
            company_id="company-1",
            project_id="project-1",
            name="Support FAQ",
            scope=CavadaLabsRAGCollectionScope.PROJECT,
            status=CavadaLabsRAGCollectionStatus.DRAFT,
        ),
        http_request=MagicMock(),
        user_api_key_dict=_internal_user(),
    )

    assert response.collection_id == "collection-created"
    create_data = db.cavadalabs_ragcollectiontable.create.call_args.kwargs["data"]
    assert create_data["company_id"] == "company-1"
    assert create_data["project_id"] == "project-1"


@pytest.mark.asyncio
async def test_should_reject_project_rag_collection_create_for_project_viewer(
    monkeypatch,
):
    db = _rag_endpoint_db(company_role=None, project_role="viewer")
    _patch_proxy_prisma(monkeypatch, db)

    with pytest.raises(HTTPException) as exc_info:
        await rag_endpoints.create_rag_collection(
            data=CavadaLabsRAGCollectionCreateRequest(
                company_id="company-1",
                project_id="project-1",
                name="Support FAQ",
                scope=CavadaLabsRAGCollectionScope.PROJECT,
                status=CavadaLabsRAGCollectionStatus.DRAFT,
            ),
            http_request=MagicMock(),
            user_api_key_dict=_internal_user(),
        )

    assert exc_info.value.status_code == 403
    db.cavadalabs_ragcollectiontable.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_should_list_rag_collections_by_visible_project_scope(monkeypatch):
    db = _rag_endpoint_db(company_role=None, project_role="viewer")
    _patch_proxy_prisma(monkeypatch, db)

    response = await rag_endpoints.list_rag_collections(
        http_request=MagicMock(),
        company_id="company-1",
        project_id=None,
        status_filter=None,
        scope_filter=None,
        take=100,
        skip=0,
        user_api_key_dict=_internal_user(),
    )

    assert response.count == 1
    where = db.cavadalabs_ragcollectiontable.find_many.call_args.kwargs["where"]
    assert where == {"project_id": {"in": ["project-1"]}}


@pytest.mark.asyncio
async def test_should_create_project_rag_collection_and_write_audit_log():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_companytable.find_unique = AsyncMock(
        return_value=_company_row()
    )
    prisma_client.db.cavadalabs_projecttable.find_unique = AsyncMock(
        return_value=_project_row()
    )
    prisma_client.db.cavadalabs_ragcollectiontable.create = AsyncMock(
        return_value=_collection_row(status="draft")
    )

    response = await service.create_collection(
        CavadaLabsRAGCollectionCreateRequest(
            company_id="company-1",
            project_id="project-1",
            name="Support FAQ",
            scope=CavadaLabsRAGCollectionScope.PROJECT,
            status=CavadaLabsRAGCollectionStatus.DRAFT,
            vector_store_provider="pgvector",
            vector_store_id="vs-1",
            embedding_model="text-embedding-3-large",
        ),
        _admin(),
    )

    assert response.collection_id == "collection-1"
    create_payload = (
        prisma_client.db.cavadalabs_ragcollectiontable.create.call_args.kwargs["data"]
    )
    assert create_payload["company_id"] == "company-1"
    assert create_payload["project_id"] == "project-1"
    assert create_payload["created_by"] == "admin-user"
    prisma_client.db.cavadalabs_auditlogtable.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_should_reject_rag_collection_project_from_different_company():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_companytable.find_unique = AsyncMock(
        return_value=_company_row(company_id="company-1")
    )
    prisma_client.db.cavadalabs_projecttable.find_unique = AsyncMock(
        return_value=_project_row(company_id="company-2")
    )

    with pytest.raises(HTTPException) as exc:
        await service.create_collection(
            CavadaLabsRAGCollectionCreateRequest(
                company_id="company-1",
                project_id="project-1",
                name="Support FAQ",
            ),
            _admin(),
        )

    assert exc.value.status_code == 400
    prisma_client.db.cavadalabs_ragcollectiontable.create.assert_not_called()


@pytest.mark.asyncio
async def test_should_create_rag_document_with_collection_ownership():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_ragcollectiontable.find_unique = AsyncMock(
        return_value=_collection_row(status="active")
    )

    def _create_document(*, data):
        assert data["company_id"] == "company-1"
        assert data["project_id"] == "project-1"
        assert data["last_indexed_at"] is not None
        return _document_row(
            status=data["status"],
            last_indexed_at=data["last_indexed_at"],
        )

    prisma_client.db.cavadalabs_ragdocumenttable.create = AsyncMock(
        side_effect=_create_document
    )

    response = await service.create_document(
        CavadaLabsRAGDocumentCreateRequest(
            collection_id="collection-1",
            source_uri="s3://bucket/support.pdf",
            file_name="support.pdf",
            content_hash="sha256:abc",
            status=CavadaLabsRAGDocumentStatus.INDEXED,
            chunk_count=4,
        ),
        _admin(),
    )

    assert response.company_id == "company-1"
    assert response.project_id == "project-1"
    assert response.status == "indexed"
    prisma_client.db.cavadalabs_auditlogtable.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_should_assign_rag_collection_to_chatbot_and_sync_indexes():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_ragcollectiontable.find_unique = AsyncMock(
        return_value=_collection_row(status="active")
    )
    prisma_client.db.cavadalabs_chatbottable.find_unique = AsyncMock(
        side_effect=[
            _chatbot_row(assigned_rag_collections=[]),
            _chatbot_row(assigned_rag_collections=[]),
        ]
    )
    prisma_client.db.cavadalabs_projecttable.find_unique = AsyncMock(
        return_value=_project_row(allowed_rag_collections=[])
    )
    prisma_client.db.cavadalabs_chatbotragassignmenttable.create = AsyncMock(
        return_value=_assignment_row(status="active")
    )
    prisma_client.db.cavadalabs_chatbottable.update = AsyncMock(
        return_value=_chatbot_row(assigned_rag_collections=["collection-1"])
    )
    prisma_client.db.cavadalabs_projecttable.update = AsyncMock(
        return_value=_project_row(allowed_rag_collections=["collection-1"])
    )

    response = await service.create_assignment(
        CavadaLabsChatbotRAGAssignmentCreateRequest(
            chatbot_id="chatbot-1",
            collection_id="collection-1",
            priority=10,
            retrieval_config={"top_k": 6},
        ),
        _admin(),
    )

    assert response.assignment_id == "assignment-1"
    prisma_client.db.cavadalabs_chatbottable.update.assert_awaited_once_with(
        where={"chatbot_id": "chatbot-1"},
        data={
            "assigned_rag_collections": ["collection-1"],
            "updated_by": "admin-user",
        },
    )
    prisma_client.db.cavadalabs_projecttable.update.assert_awaited_once_with(
        where={"project_id": "project-1"},
        data={
            "allowed_rag_collections": ["collection-1"],
            "updated_by": "admin-user",
        },
    )


@pytest.mark.asyncio
async def test_should_disable_rag_assignment_and_remove_collection_from_chatbot():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_chatbotragassignmenttable.find_unique = AsyncMock(
        return_value=_assignment_row(status="active")
    )
    prisma_client.db.cavadalabs_chatbotragassignmenttable.update = AsyncMock(
        return_value=_assignment_row(status="disabled")
    )
    prisma_client.db.cavadalabs_chatbottable.find_unique = AsyncMock(
        return_value=_chatbot_row(
            assigned_rag_collections=["collection-1", "collection-2"]
        )
    )
    prisma_client.db.cavadalabs_chatbottable.update = AsyncMock(
        return_value=_chatbot_row(assigned_rag_collections=["collection-2"])
    )

    response = await service.update_assignment(
        "assignment-1",
        CavadaLabsChatbotRAGAssignmentUpdateRequest(
            status=CavadaLabsRAGAssignmentStatus.DISABLED
        ),
        _admin(),
    )

    assert response.status == "disabled"
    prisma_client.db.cavadalabs_chatbottable.update.assert_awaited_once_with(
        where={"chatbot_id": "chatbot-1"},
        data={
            "assigned_rag_collections": ["collection-2"],
            "updated_by": "admin-user",
        },
    )


@pytest.mark.asyncio
async def test_should_retrieve_runtime_rag_context_from_assigned_vector_store():
    search_client = _SearchClient(
        response={
            "data": [
                {
                    "score": 0.91,
                    "file_id": "file-1",
                    "filename": "support.pdf",
                    "attributes": {"document_id": "document-1"},
                    "content": [{"type": "text", "text": "Warranty lasts two years."}],
                }
            ]
        }
    )
    service, prisma_client = _runtime_service(search_client=search_client)
    prisma_client.db.cavadalabs_chatbotragassignmenttable.find_many = AsyncMock(
        return_value=[
            _assignment_row(
                retrieval_config={
                    "top_k": 3,
                    "filters": {"locale": "it"},
                    "max_context_chars": 4000,
                }
            )
        ]
    )
    prisma_client.db.cavadalabs_ragcollectiontable.find_unique = AsyncMock(
        return_value=_collection_row(status="active")
    )

    result = await service.retrieve_context(
        context=_runtime_context(),
        request_data=CavadaLabsChatCompletionRequest(
            session_id="session-1",
            messages=[{"role": "user", "content": "Quanto dura la garanzia?"}],
        ),
    )

    assert result.has_context is True
    assert "Warranty lasts two years." in result.context_text
    assert result.metadata()["document_ids"] == ["document-1"]
    assert search_client.calls[0]["vector_store_id"] == "vs-1"
    assert search_client.calls[0]["custom_llm_provider"] == "pgvector"
    assert search_client.calls[0]["max_num_results"] == 3
    assert search_client.calls[0]["filters"] == {"locale": "it"}


@pytest.mark.asyncio
async def test_should_fail_closed_when_assigned_rag_collection_has_no_vector_store():
    service, prisma_client = _runtime_service(search_client=_SearchClient())
    prisma_client.db.cavadalabs_chatbotragassignmenttable.find_many = AsyncMock(
        return_value=[_assignment_row()]
    )
    prisma_client.db.cavadalabs_ragcollectiontable.find_unique = AsyncMock(
        return_value=_collection_row(status="active", vector_store_id=None)
    )

    with pytest.raises(HTTPException) as exc:
        await service.retrieve_context(
            context=_runtime_context(),
            request_data=CavadaLabsChatCompletionRequest(
                session_id="session-1",
                messages=[{"role": "user", "content": "Quanto dura la garanzia?"}],
            ),
        )

    assert exc.value.status_code == 409


def test_should_build_chatbot_payload_with_runtime_rag_context_metadata():
    service = CavadaLabsDispatcherService(MagicMock())
    rag_context = CavadaLabsRAGContext(
        query="Quanto dura la garanzia?",
        context_text="[1] collection=collection-1 source=support.pdf\nDue anni.",
        sources=[
            CavadaLabsRAGSource(
                collection_id="collection-1",
                vector_store_id="vs-1",
                document_id="document-1",
                file_id="file-1",
                filename="support.pdf",
                score=0.91,
                text="Due anni.",
                attributes={"document_id": "document-1"},
            )
        ],
        collection_ids=["collection-1"],
        skipped_collection_ids=[],
    )

    payload = service.build_chat_completion_payload(
        request_data=CavadaLabsChatCompletionRequest(
            session_id="session-1",
            messages=[{"role": "user", "content": "Quanto dura la garanzia?"}],
        ),
        context=_runtime_context(),
        origin="https://acme.test",
        request_ip="203.0.113.10",
        rag_context=rag_context,
    )

    assert payload["messages"][1]["role"] == "system"
    assert "CavadaLabs RAG context" in payload["messages"][1]["content"]
    assert payload["messages"][2] == {
        "role": "user",
        "content": "Quanto dura la garanzia?",
    }
    rag_metadata = payload["metadata"]["cavadalabs"]["rag"]
    assert rag_metadata["collection_ids"] == ["collection-1"]
    assert rag_metadata["document_ids"] == ["document-1"]
    assert rag_metadata["result_count"] == 1
