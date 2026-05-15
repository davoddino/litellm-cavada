from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from litellm.types.llms.openai import AllMessageValues


class CavadaLabsStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class CavadaLabsProjectStatus(str, enum.Enum):
    DEV = "dev"
    PRODUCTION = "production"
    ARCHIVED = "archived"


class CavadaLabsChatbotStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DISABLED = "disabled"


class CavadaLabsWebTokenStatus(str, enum.Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class CavadaLabsNodeStatus(str, enum.Enum):
    PENDING = "pending"
    ONLINE = "online"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    DRAINING = "draining"
    DISABLED = "disabled"


class CavadaLabsGPUStatus(str, enum.Enum):
    AVAILABLE = "available"
    ALLOCATED = "allocated"
    LOADING = "loading"
    LOADED = "loaded"
    UNHEALTHY = "unhealthy"
    OFFLINE = "offline"
    DISABLED = "disabled"


class CavadaLabsNodeEnrollmentStatus(str, enum.Enum):
    ACTIVE = "active"
    USED = "used"
    EXPIRED = "expired"
    REVOKED = "revoked"


class CavadaLabsModelRuntimeStatus(str, enum.Enum):
    QUEUED = "queued"
    LOCKING = "locking"
    LOADING = "loading"
    LOADED = "loaded"
    FAILED = "failed"
    EXPIRED = "expired"
    UNLOADING = "unloading"
    RELEASED = "released"


class CavadaLabsGPULockStatus(str, enum.Enum):
    ACTIVE = "active"
    RELEASED = "released"
    EXPIRED = "expired"


class CavadaLabsReasoningMode(str, enum.Enum):
    NONE = "none"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CavadaLabsBillingReportFormat(str, enum.Enum):
    JSON = "json"
    CSV = "csv"
    XLSX = "xlsx"
    PDF = "pdf"


class CavadaLabsBillingReportStatus(str, enum.Enum):
    GENERATED = "generated"
    VOID = "void"


class CavadaLabsGuardrailPolicyScope(str, enum.Enum):
    COMPANY = "company"
    PROJECT = "project"
    CHATBOT = "chatbot"


class CavadaLabsGuardrailPolicyStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    DISABLED = "disabled"
    ARCHIVED = "archived"


class CavadaLabsGuardrailEnforcementMode(str, enum.Enum):
    ENFORCE = "enforce"
    LOG_ONLY = "log_only"


class CavadaLabsGuardrailDecision(str, enum.Enum):
    ALLOW = "allow"
    BLOCK = "block"
    REDACT = "redact"
    REVIEW = "review"
    LOG_ONLY = "log_only"


class CavadaLabsGuardrailPhase(str, enum.Enum):
    PRE_CALL = "pre_call"
    POST_CALL = "post_call"
    RAG_CONTEXT = "rag_context"
    TOOL_CALL = "tool_call"


class CavadaLabsRAGCollectionScope(str, enum.Enum):
    COMPANY = "company"
    PROJECT = "project"


class CavadaLabsRAGCollectionStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class CavadaLabsRAGDocumentStatus(str, enum.Enum):
    QUEUED = "queued"
    INDEXING = "indexing"
    INDEXED = "indexed"
    FAILED = "failed"
    DELETED = "deleted"


class CavadaLabsRAGAssignmentStatus(str, enum.Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class CavadaLabsComplianceFramework(str, enum.Enum):
    GDPR = "gdpr"
    AI_ACT = "ai_act"
    SECURITY = "security"
    INTERNAL = "internal"


class CavadaLabsComplianceStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class CavadaLabsDataSubjectRequestType(str, enum.Enum):
    ACCESS = "access"
    ERASURE = "erasure"
    RECTIFICATION = "rectification"
    EXPORT = "export"
    RESTRICTION = "restriction"
    OBJECTION = "objection"


class CavadaLabsDataSubjectRequestStatus(str, enum.Enum):
    RECEIVED = "received"
    IDENTITY_VERIFICATION = "identity_verification"
    IN_PROGRESS = "in_progress"
    WAITING_CUSTOMER = "waiting_customer"
    COMPLETED = "completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class CavadaLabsAISystemRiskClassification(str, enum.Enum):
    UNKNOWN = "unknown"
    MINIMAL = "minimal"
    LIMITED = "limited"
    HIGH = "high"
    PROHIBITED = "prohibited"


class CavadaLabsBaseModel(BaseModel):
    model_config = ConfigDict(use_enum_values=True, protected_namespaces=())


def _dedupe_clean(values: Optional[List[str]], *, lower: bool = False) -> List[str]:
    if values is None:
        return []
    cleaned: List[str] = []
    seen = set()
    for raw_value in values:
        value = raw_value.strip()
        if lower:
            value = value.lower()
        if value == "" or value in seen:
            continue
        cleaned.append(value)
        seen.add(value)
    return cleaned


def _validate_domain(value: str) -> str:
    if "://" in value or "/" in value or " " in value:
        raise ValueError("allowed_domains must contain hostnames, not URLs")
    if value.startswith("*."):
        domain = value[2:]
    else:
        domain = value
    if "." not in domain:
        raise ValueError("allowed_domains entries must include a registrable domain")
    return value


def _validate_origin(value: str) -> str:
    if not (value.startswith("https://") or value.startswith("http://")):
        raise ValueError("allowed_origins entries must be absolute http(s) origins")
    if "/" in value.removeprefix("https://").removeprefix("http://"):
        raise ValueError("allowed_origins must not include paths")
    return value


class CavadaLabsCompanyCreateRequest(CavadaLabsBaseModel):
    legal_name: str = Field(min_length=1, max_length=256)
    billing_name: Optional[str] = Field(default=None, max_length=256)
    vat_tax_id: Optional[str] = Field(default=None, max_length=128)
    billing_address: Dict[str, Any] = Field(default_factory=dict)
    admin_emails: List[str] = Field(default_factory=list)
    plan: Optional[str] = Field(default=None, max_length=128)
    status: CavadaLabsStatus = CavadaLabsStatus.ACTIVE
    monthly_budget: Optional[float] = Field(default=None, ge=0)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    retention_policy: Dict[str, Any] = Field(default_factory=dict)
    default_guardrail_policy: Optional[str] = Field(default=None, max_length=256)
    default_billing_settings: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("admin_emails")
    @classmethod
    def clean_admin_emails(cls, values: List[str]) -> List[str]:
        return _dedupe_clean(values, lower=True)


class CavadaLabsCompanyUpdateRequest(CavadaLabsBaseModel):
    legal_name: Optional[str] = Field(default=None, min_length=1, max_length=256)
    billing_name: Optional[str] = Field(default=None, max_length=256)
    vat_tax_id: Optional[str] = Field(default=None, max_length=128)
    billing_address: Optional[Dict[str, Any]] = None
    admin_emails: Optional[List[str]] = None
    plan: Optional[str] = Field(default=None, max_length=128)
    status: Optional[CavadaLabsStatus] = None
    monthly_budget: Optional[float] = Field(default=None, ge=0)
    metadata: Optional[Dict[str, Any]] = None
    retention_policy: Optional[Dict[str, Any]] = None
    default_guardrail_policy: Optional[str] = Field(default=None, max_length=256)
    default_billing_settings: Optional[Dict[str, Any]] = None

    @field_validator("admin_emails")
    @classmethod
    def clean_admin_emails(cls, values: Optional[List[str]]) -> Optional[List[str]]:
        if values is None:
            return None
        return _dedupe_clean(values, lower=True)


class CavadaLabsCompanyResponse(CavadaLabsCompanyCreateRequest):
    company_id: str
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


class CavadaLabsCompanyListResponse(CavadaLabsBaseModel):
    companies: List[CavadaLabsCompanyResponse]
    count: int


class CavadaLabsProjectCreateRequest(CavadaLabsBaseModel):
    company_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=256)
    status: CavadaLabsProjectStatus = CavadaLabsProjectStatus.DEV
    allowed_models: List[str] = Field(default_factory=list)
    allowed_rag_collections: List[str] = Field(default_factory=list)
    default_chatbot_settings: Dict[str, Any] = Field(default_factory=dict)
    default_guardrail_policy: Optional[str] = Field(default=None, max_length=256)
    budget: Optional[float] = Field(default=None, ge=0)
    retention_policy_override: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("allowed_models", "allowed_rag_collections")
    @classmethod
    def clean_string_lists(cls, values: List[str]) -> List[str]:
        return _dedupe_clean(values)


class CavadaLabsProjectUpdateRequest(CavadaLabsBaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=256)
    status: Optional[CavadaLabsProjectStatus] = None
    allowed_models: Optional[List[str]] = None
    allowed_rag_collections: Optional[List[str]] = None
    default_chatbot_settings: Optional[Dict[str, Any]] = None
    default_guardrail_policy: Optional[str] = Field(default=None, max_length=256)
    budget: Optional[float] = Field(default=None, ge=0)
    retention_policy_override: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("allowed_models", "allowed_rag_collections")
    @classmethod
    def clean_optional_string_lists(
        cls, values: Optional[List[str]]
    ) -> Optional[List[str]]:
        if values is None:
            return None
        return _dedupe_clean(values)


class CavadaLabsProjectResponse(CavadaLabsProjectCreateRequest):
    project_id: str
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


class CavadaLabsProjectListResponse(CavadaLabsBaseModel):
    projects: List[CavadaLabsProjectResponse]
    count: int


class CavadaLabsChatbotCreateRequest(CavadaLabsBaseModel):
    company_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=256)
    status: CavadaLabsChatbotStatus = CavadaLabsChatbotStatus.DRAFT
    system_prompt: str = ""
    prompt_version: int = Field(default=1, ge=1)
    default_language: str = Field(default="it", min_length=2, max_length=16)
    model_policy_id: Optional[str] = None
    assigned_rag_collections: List[str] = Field(default_factory=list)
    assigned_guardrail_policy: Optional[str] = Field(default=None, max_length=256)
    allowed_domains: List[str] = Field(default_factory=list)
    widget_theme_config: Dict[str, Any] = Field(default_factory=dict)
    fallback_message: Optional[str] = None
    transcript_retention_policy: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("assigned_rag_collections")
    @classmethod
    def clean_assigned_rag_collections(cls, values: List[str]) -> List[str]:
        return _dedupe_clean(values)

    @field_validator("allowed_domains")
    @classmethod
    def clean_allowed_domains(cls, values: List[str]) -> List[str]:
        return [_validate_domain(value) for value in _dedupe_clean(values, lower=True)]

    @model_validator(mode="after")
    def validate_published_chatbot(self) -> "CavadaLabsChatbotCreateRequest":
        if (
            self.status == CavadaLabsChatbotStatus.PUBLISHED.value
            and not self.system_prompt
        ):
            raise ValueError("published chatbots require a system_prompt")
        return self


class CavadaLabsChatbotUpdateRequest(CavadaLabsBaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=256)
    status: Optional[CavadaLabsChatbotStatus] = None
    system_prompt: Optional[str] = None
    prompt_version: Optional[int] = Field(default=None, ge=1)
    default_language: Optional[str] = Field(default=None, min_length=2, max_length=16)
    model_policy_id: Optional[str] = None
    assigned_rag_collections: Optional[List[str]] = None
    assigned_guardrail_policy: Optional[str] = Field(default=None, max_length=256)
    allowed_domains: Optional[List[str]] = None
    widget_theme_config: Optional[Dict[str, Any]] = None
    fallback_message: Optional[str] = None
    transcript_retention_policy: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("assigned_rag_collections")
    @classmethod
    def clean_assigned_rag_collections(
        cls, values: Optional[List[str]]
    ) -> Optional[List[str]]:
        if values is None:
            return None
        return _dedupe_clean(values)

    @field_validator("allowed_domains")
    @classmethod
    def clean_allowed_domains(cls, values: Optional[List[str]]) -> Optional[List[str]]:
        if values is None:
            return None
        return [_validate_domain(value) for value in _dedupe_clean(values, lower=True)]


class CavadaLabsChatbotResponse(CavadaLabsChatbotCreateRequest):
    chatbot_id: str
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


class CavadaLabsChatbotListResponse(CavadaLabsBaseModel):
    chatbots: List[CavadaLabsChatbotResponse]
    count: int


class CavadaLabsRAGCollectionCreateRequest(CavadaLabsBaseModel):
    company_id: str = Field(min_length=1)
    project_id: Optional[str] = Field(default=None, min_length=1)
    name: str = Field(min_length=1, max_length=256)
    description: Optional[str] = Field(default=None, max_length=4096)
    scope: CavadaLabsRAGCollectionScope = CavadaLabsRAGCollectionScope.PROJECT
    status: CavadaLabsRAGCollectionStatus = CavadaLabsRAGCollectionStatus.DRAFT
    source_type: Optional[str] = Field(default=None, max_length=128)
    vector_store_provider: Optional[str] = Field(default=None, max_length=128)
    vector_store_id: Optional[str] = Field(default=None, max_length=256)
    embedding_model: Optional[str] = Field(default=None, max_length=256)
    chunking_strategy: Dict[str, Any] = Field(default_factory=dict)
    access_policy: Dict[str, Any] = Field(default_factory=dict)
    retention_policy: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_scope(self) -> "CavadaLabsRAGCollectionCreateRequest":
        if (
            self.scope == CavadaLabsRAGCollectionScope.PROJECT.value
            and not self.project_id
        ):
            raise ValueError("project-scoped RAG collections require project_id")
        if self.scope == CavadaLabsRAGCollectionScope.COMPANY.value and self.project_id:
            raise ValueError("company-scoped RAG collections must not set project_id")
        return self


class CavadaLabsRAGCollectionUpdateRequest(CavadaLabsBaseModel):
    project_id: Optional[str] = Field(default=None, min_length=1)
    name: Optional[str] = Field(default=None, min_length=1, max_length=256)
    description: Optional[str] = Field(default=None, max_length=4096)
    scope: Optional[CavadaLabsRAGCollectionScope] = None
    status: Optional[CavadaLabsRAGCollectionStatus] = None
    source_type: Optional[str] = Field(default=None, max_length=128)
    vector_store_provider: Optional[str] = Field(default=None, max_length=128)
    vector_store_id: Optional[str] = Field(default=None, max_length=256)
    embedding_model: Optional[str] = Field(default=None, max_length=256)
    chunking_strategy: Optional[Dict[str, Any]] = None
    access_policy: Optional[Dict[str, Any]] = None
    retention_policy: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class CavadaLabsRAGCollectionResponse(CavadaLabsRAGCollectionCreateRequest):
    collection_id: str
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


class CavadaLabsRAGCollectionListResponse(CavadaLabsBaseModel):
    rag_collections: List[CavadaLabsRAGCollectionResponse]
    count: int


class CavadaLabsRAGDocumentCreateRequest(CavadaLabsBaseModel):
    collection_id: str = Field(min_length=1)
    source_uri: Optional[str] = Field(default=None, max_length=2048)
    file_name: Optional[str] = Field(default=None, max_length=512)
    mime_type: Optional[str] = Field(default=None, max_length=128)
    status: CavadaLabsRAGDocumentStatus = CavadaLabsRAGDocumentStatus.QUEUED
    content_hash: Optional[str] = Field(default=None, max_length=256)
    byte_size: Optional[int] = Field(default=None, ge=0)
    token_count: Optional[int] = Field(default=None, ge=0)
    chunk_count: int = Field(default=0, ge=0)
    last_indexed_at: Optional[datetime] = None
    failure_reason: Optional[str] = Field(default=None, max_length=4096)
    version: int = Field(default=1, ge=1)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_document_identity(self) -> "CavadaLabsRAGDocumentCreateRequest":
        if not (self.source_uri or self.file_name or self.content_hash):
            raise ValueError(
                "RAG documents require at least one of source_uri, file_name, or content_hash"
            )
        if (
            self.status == CavadaLabsRAGDocumentStatus.FAILED.value
            and not self.failure_reason
        ):
            raise ValueError("failed RAG documents require failure_reason")
        return self


class CavadaLabsRAGDocumentUpdateRequest(CavadaLabsBaseModel):
    source_uri: Optional[str] = Field(default=None, max_length=2048)
    file_name: Optional[str] = Field(default=None, max_length=512)
    mime_type: Optional[str] = Field(default=None, max_length=128)
    status: Optional[CavadaLabsRAGDocumentStatus] = None
    content_hash: Optional[str] = Field(default=None, max_length=256)
    byte_size: Optional[int] = Field(default=None, ge=0)
    token_count: Optional[int] = Field(default=None, ge=0)
    chunk_count: Optional[int] = Field(default=None, ge=0)
    last_indexed_at: Optional[datetime] = None
    failure_reason: Optional[str] = Field(default=None, max_length=4096)
    version: Optional[int] = Field(default=None, ge=1)
    metadata: Optional[Dict[str, Any]] = None


class CavadaLabsRAGDocumentResponse(CavadaLabsRAGDocumentCreateRequest):
    document_id: str
    company_id: str
    project_id: Optional[str] = None
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


class CavadaLabsRAGDocumentListResponse(CavadaLabsBaseModel):
    rag_documents: List[CavadaLabsRAGDocumentResponse]
    count: int


class CavadaLabsChatbotRAGAssignmentCreateRequest(CavadaLabsBaseModel):
    chatbot_id: str = Field(min_length=1)
    collection_id: str = Field(min_length=1)
    status: CavadaLabsRAGAssignmentStatus = CavadaLabsRAGAssignmentStatus.ACTIVE
    priority: int = Field(default=100, ge=1)
    retrieval_config: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CavadaLabsChatbotRAGAssignmentUpdateRequest(CavadaLabsBaseModel):
    status: Optional[CavadaLabsRAGAssignmentStatus] = None
    priority: Optional[int] = Field(default=None, ge=1)
    retrieval_config: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class CavadaLabsChatbotRAGAssignmentResponse(
    CavadaLabsChatbotRAGAssignmentCreateRequest
):
    assignment_id: str
    company_id: str
    project_id: str
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


class CavadaLabsChatbotRAGAssignmentListResponse(CavadaLabsBaseModel):
    rag_assignments: List[CavadaLabsChatbotRAGAssignmentResponse]
    count: int


class CavadaLabsComplianceDocumentCreateRequest(CavadaLabsBaseModel):
    company_id: str = Field(min_length=1)
    project_id: Optional[str] = Field(default=None, min_length=1)
    chatbot_id: Optional[str] = Field(default=None, min_length=1)
    collection_id: Optional[str] = Field(default=None, min_length=1)
    framework: CavadaLabsComplianceFramework = CavadaLabsComplianceFramework.GDPR
    document_type: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=512)
    version: int = Field(default=1, ge=1)
    status: CavadaLabsComplianceStatus = CavadaLabsComplianceStatus.DRAFT
    locale: str = Field(default="en", min_length=2, max_length=16)
    content: str = Field(default="", max_length=2_000_000)
    content_format: str = Field(default="markdown", min_length=1, max_length=64)
    generated_from: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    approved_by: Optional[str] = Field(default=None, max_length=256)
    approved_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None

    @field_validator("document_type", "content_format")
    @classmethod
    def clean_slugish_field(cls, value: str) -> str:
        return value.strip().lower()

    @model_validator(mode="after")
    def validate_document_lifecycle(
        self,
    ) -> "CavadaLabsComplianceDocumentCreateRequest":
        if (
            self.status == CavadaLabsComplianceStatus.PUBLISHED.value
            and not self.content
        ):
            raise ValueError("published compliance documents require content")
        if self.valid_from and self.valid_until and self.valid_until <= self.valid_from:
            raise ValueError("valid_until must be later than valid_from")
        return self


class CavadaLabsComplianceDocumentUpdateRequest(CavadaLabsBaseModel):
    project_id: Optional[str] = Field(default=None, min_length=1)
    chatbot_id: Optional[str] = Field(default=None, min_length=1)
    collection_id: Optional[str] = Field(default=None, min_length=1)
    framework: Optional[CavadaLabsComplianceFramework] = None
    document_type: Optional[str] = Field(default=None, min_length=1, max_length=128)
    title: Optional[str] = Field(default=None, min_length=1, max_length=512)
    version: Optional[int] = Field(default=None, ge=1)
    status: Optional[CavadaLabsComplianceStatus] = None
    locale: Optional[str] = Field(default=None, min_length=2, max_length=16)
    content: Optional[str] = Field(default=None, max_length=2_000_000)
    content_format: Optional[str] = Field(default=None, min_length=1, max_length=64)
    generated_from: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    approved_by: Optional[str] = Field(default=None, max_length=256)
    approved_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None

    @field_validator("document_type", "content_format")
    @classmethod
    def clean_optional_slugish_field(cls, value: Optional[str]) -> Optional[str]:
        return value.strip().lower() if value is not None else None


class CavadaLabsComplianceDocumentResponse(CavadaLabsComplianceDocumentCreateRequest):
    document_id: str
    checksum: str
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


class CavadaLabsComplianceDocumentListResponse(CavadaLabsBaseModel):
    compliance_documents: List[CavadaLabsComplianceDocumentResponse]
    count: int


class CavadaLabsComplianceEvidenceCreateRequest(CavadaLabsBaseModel):
    company_id: str = Field(min_length=1)
    project_id: Optional[str] = Field(default=None, min_length=1)
    chatbot_id: Optional[str] = Field(default=None, min_length=1)
    collection_id: Optional[str] = Field(default=None, min_length=1)
    framework: CavadaLabsComplianceFramework
    evidence_type: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=512)
    status: CavadaLabsComplianceStatus = CavadaLabsComplianceStatus.ACTIVE
    source_type: Optional[str] = Field(default=None, max_length=128)
    source_id: Optional[str] = Field(default=None, max_length=256)
    content: Dict[str, Any] = Field(default_factory=dict)
    captured_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("evidence_type")
    @classmethod
    def clean_evidence_type(cls, value: str) -> str:
        return value.strip().lower()


class CavadaLabsComplianceEvidenceUpdateRequest(CavadaLabsBaseModel):
    project_id: Optional[str] = Field(default=None, min_length=1)
    chatbot_id: Optional[str] = Field(default=None, min_length=1)
    collection_id: Optional[str] = Field(default=None, min_length=1)
    framework: Optional[CavadaLabsComplianceFramework] = None
    evidence_type: Optional[str] = Field(default=None, min_length=1, max_length=128)
    title: Optional[str] = Field(default=None, min_length=1, max_length=512)
    status: Optional[CavadaLabsComplianceStatus] = None
    source_type: Optional[str] = Field(default=None, max_length=128)
    source_id: Optional[str] = Field(default=None, max_length=256)
    content: Optional[Dict[str, Any]] = None
    captured_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("evidence_type")
    @classmethod
    def clean_optional_evidence_type(cls, value: Optional[str]) -> Optional[str]:
        return value.strip().lower() if value is not None else None


class CavadaLabsComplianceEvidenceResponse(CavadaLabsComplianceEvidenceCreateRequest):
    evidence_id: str
    checksum: str
    captured_at: datetime
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


class CavadaLabsComplianceEvidenceListResponse(CavadaLabsBaseModel):
    compliance_evidence: List[CavadaLabsComplianceEvidenceResponse]
    count: int


class CavadaLabsProcessingActivityCreateRequest(CavadaLabsBaseModel):
    company_id: str = Field(min_length=1)
    project_id: Optional[str] = Field(default=None, min_length=1)
    name: str = Field(min_length=1, max_length=256)
    status: CavadaLabsComplianceStatus = CavadaLabsComplianceStatus.ACTIVE
    controller: Optional[str] = Field(default=None, max_length=512)
    processor: Optional[str] = Field(default=None, max_length=512)
    purpose: str = Field(min_length=1, max_length=4096)
    legal_basis: Optional[str] = Field(default=None, max_length=512)
    data_categories: List[str] = Field(default_factory=list)
    data_subject_categories: List[str] = Field(default_factory=list)
    recipients: List[str] = Field(default_factory=list)
    transfer_countries: List[str] = Field(default_factory=list)
    retention_period: Optional[str] = Field(default=None, max_length=512)
    security_measures: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "data_categories",
        "data_subject_categories",
        "recipients",
        "transfer_countries",
        "security_measures",
    )
    @classmethod
    def clean_processing_lists(cls, values: List[str]) -> List[str]:
        return _dedupe_clean(values)


class CavadaLabsProcessingActivityUpdateRequest(CavadaLabsBaseModel):
    project_id: Optional[str] = Field(default=None, min_length=1)
    name: Optional[str] = Field(default=None, min_length=1, max_length=256)
    status: Optional[CavadaLabsComplianceStatus] = None
    controller: Optional[str] = Field(default=None, max_length=512)
    processor: Optional[str] = Field(default=None, max_length=512)
    purpose: Optional[str] = Field(default=None, min_length=1, max_length=4096)
    legal_basis: Optional[str] = Field(default=None, max_length=512)
    data_categories: Optional[List[str]] = None
    data_subject_categories: Optional[List[str]] = None
    recipients: Optional[List[str]] = None
    transfer_countries: Optional[List[str]] = None
    retention_period: Optional[str] = Field(default=None, max_length=512)
    security_measures: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None

    @field_validator(
        "data_categories",
        "data_subject_categories",
        "recipients",
        "transfer_countries",
        "security_measures",
    )
    @classmethod
    def clean_optional_processing_lists(
        cls, values: Optional[List[str]]
    ) -> Optional[List[str]]:
        return _dedupe_clean(values) if values is not None else None


class CavadaLabsProcessingActivityResponse(CavadaLabsProcessingActivityCreateRequest):
    activity_id: str
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


class CavadaLabsProcessingActivityListResponse(CavadaLabsBaseModel):
    processing_activities: List[CavadaLabsProcessingActivityResponse]
    count: int


class CavadaLabsDataSubjectRequestCreateRequest(CavadaLabsBaseModel):
    company_id: str = Field(min_length=1)
    project_id: Optional[str] = Field(default=None, min_length=1)
    requester_email: str = Field(min_length=3, max_length=320)
    request_type: CavadaLabsDataSubjectRequestType
    status: CavadaLabsDataSubjectRequestStatus = (
        CavadaLabsDataSubjectRequestStatus.RECEIVED
    )
    received_at: Optional[datetime] = None
    due_at: Optional[datetime] = None
    identity_verified_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    assigned_to: Optional[str] = Field(default=None, max_length=256)
    scope: Dict[str, Any] = Field(default_factory=dict)
    result: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("requester_email")
    @classmethod
    def clean_requester_email(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if "@" not in cleaned:
            raise ValueError("requester_email must be an email address")
        return cleaned


class CavadaLabsDataSubjectRequestUpdateRequest(CavadaLabsBaseModel):
    project_id: Optional[str] = Field(default=None, min_length=1)
    requester_email: Optional[str] = Field(default=None, min_length=3, max_length=320)
    request_type: Optional[CavadaLabsDataSubjectRequestType] = None
    status: Optional[CavadaLabsDataSubjectRequestStatus] = None
    received_at: Optional[datetime] = None
    due_at: Optional[datetime] = None
    identity_verified_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    assigned_to: Optional[str] = Field(default=None, max_length=256)
    scope: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("requester_email")
    @classmethod
    def clean_optional_requester_email(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip().lower()
        if "@" not in cleaned:
            raise ValueError("requester_email must be an email address")
        return cleaned


class CavadaLabsDataSubjectRequestResponse(CavadaLabsDataSubjectRequestCreateRequest):
    dsr_id: str
    received_at: datetime
    due_at: datetime
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


class CavadaLabsDataSubjectRequestListResponse(CavadaLabsBaseModel):
    data_subject_requests: List[CavadaLabsDataSubjectRequestResponse]
    count: int


class CavadaLabsAISystemAssessmentCreateRequest(CavadaLabsBaseModel):
    company_id: str = Field(min_length=1)
    project_id: Optional[str] = Field(default=None, min_length=1)
    chatbot_id: Optional[str] = Field(default=None, min_length=1)
    name: str = Field(min_length=1, max_length=256)
    version: int = Field(default=1, ge=1)
    status: CavadaLabsComplianceStatus = CavadaLabsComplianceStatus.DRAFT
    risk_classification: CavadaLabsAISystemRiskClassification = (
        CavadaLabsAISystemRiskClassification.UNKNOWN
    )
    intended_purpose: str = Field(min_length=1, max_length=4096)
    prohibited_practice_review: Dict[str, Any] = Field(default_factory=dict)
    human_oversight: Dict[str, Any] = Field(default_factory=dict)
    transparency_notice: Optional[str] = Field(default=None, max_length=4096)
    model_provider_metadata: Dict[str, Any] = Field(default_factory=dict)
    evaluation_evidence: Dict[str, Any] = Field(default_factory=dict)
    approved_by: Optional[str] = Field(default=None, max_length=256)
    approved_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CavadaLabsAISystemAssessmentUpdateRequest(CavadaLabsBaseModel):
    project_id: Optional[str] = Field(default=None, min_length=1)
    chatbot_id: Optional[str] = Field(default=None, min_length=1)
    name: Optional[str] = Field(default=None, min_length=1, max_length=256)
    version: Optional[int] = Field(default=None, ge=1)
    status: Optional[CavadaLabsComplianceStatus] = None
    risk_classification: Optional[CavadaLabsAISystemRiskClassification] = None
    intended_purpose: Optional[str] = Field(default=None, min_length=1, max_length=4096)
    prohibited_practice_review: Optional[Dict[str, Any]] = None
    human_oversight: Optional[Dict[str, Any]] = None
    transparency_notice: Optional[str] = Field(default=None, max_length=4096)
    model_provider_metadata: Optional[Dict[str, Any]] = None
    evaluation_evidence: Optional[Dict[str, Any]] = None
    approved_by: Optional[str] = Field(default=None, max_length=256)
    approved_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


class CavadaLabsAISystemAssessmentResponse(CavadaLabsAISystemAssessmentCreateRequest):
    assessment_id: str
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


class CavadaLabsAISystemAssessmentListResponse(CavadaLabsBaseModel):
    ai_system_assessments: List[CavadaLabsAISystemAssessmentResponse]
    count: int


class CavadaLabsWebTokenCreateRequest(CavadaLabsBaseModel):
    company_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    chatbot_id: str = Field(min_length=1)
    name: Optional[str] = Field(default=None, max_length=256)
    allowed_domains: List[str] = Field(default_factory=list)
    allowed_origins: List[str] = Field(default_factory=list)
    route_allowlist: List[str] = Field(
        default_factory=lambda: ["/cavadalabs/chatbots/messages"]
    )
    ip_rpm_limit: Optional[int] = Field(default=None, ge=1)
    session_rpm_limit: Optional[int] = Field(default=None, ge=1)
    session_budget: Optional[float] = Field(default=None, ge=0)
    expires_at: Optional[datetime] = None
    expires_in_seconds: int = Field(default=3600, ge=60, le=86400)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("allowed_domains")
    @classmethod
    def clean_allowed_domains(cls, values: List[str]) -> List[str]:
        return [_validate_domain(value) for value in _dedupe_clean(values, lower=True)]

    @field_validator("allowed_origins")
    @classmethod
    def clean_allowed_origins(cls, values: List[str]) -> List[str]:
        return [_validate_origin(value) for value in _dedupe_clean(values, lower=True)]

    @field_validator("route_allowlist")
    @classmethod
    def clean_route_allowlist(cls, values: List[str]) -> List[str]:
        cleaned = _dedupe_clean(values)
        for value in cleaned:
            if not value.startswith("/"):
                raise ValueError("route_allowlist entries must be absolute paths")
        return cleaned


class CavadaLabsWebTokenResponse(CavadaLabsBaseModel):
    web_token_id: str
    company_id: str
    project_id: str
    chatbot_id: str
    name: Optional[str] = None
    token_prefix: str
    status: CavadaLabsWebTokenStatus
    allowed_domains: List[str]
    allowed_origins: List[str]
    route_allowlist: List[str]
    ip_rpm_limit: Optional[int] = None
    session_rpm_limit: Optional[int] = None
    session_budget: Optional[float] = None
    expires_at: datetime
    revoked_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    metadata: Dict[str, Any]
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


class CavadaLabsWebTokenCreateResponse(CavadaLabsBaseModel):
    web_token: CavadaLabsWebTokenResponse
    token: str


class CavadaLabsWebTokenListResponse(CavadaLabsBaseModel):
    web_tokens: List[CavadaLabsWebTokenResponse]
    count: int


class CavadaLabsProjectModelPolicyCreateRequest(CavadaLabsBaseModel):
    project_id: str = Field(min_length=1)
    model_alias: str = Field(min_length=1, max_length=256)
    provider: str = Field(min_length=1, max_length=128)
    deployment_id: Optional[str] = Field(default=None, max_length=256)
    priority: int = Field(ge=1)
    enabled: bool = True
    fallback_enabled: bool = True
    require_json_output: bool = False
    force_json_output: bool = False
    json_schema: Optional[Dict[str, Any]] = None
    strict_json: bool = False
    repair_invalid_json: bool = False
    retry_on_invalid_json: bool = False
    require_no_think: bool = False
    no_think: bool = False
    reasoning_mode: Optional[CavadaLabsReasoningMode] = None
    hide_reasoning: bool = False
    strip_thinking_tags: bool = False
    prefer_loaded_model: bool = True
    max_cost_input: Optional[float] = Field(default=None, ge=0)
    max_cost_output: Optional[float] = Field(default=None, ge=0)
    required_capabilities: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("required_capabilities")
    @classmethod
    def clean_required_capabilities(cls, values: List[str]) -> List[str]:
        return _dedupe_clean(values, lower=True)


class CavadaLabsProjectModelPolicyUpdateRequest(CavadaLabsBaseModel):
    model_alias: Optional[str] = Field(default=None, min_length=1, max_length=256)
    provider: Optional[str] = Field(default=None, min_length=1, max_length=128)
    deployment_id: Optional[str] = Field(default=None, max_length=256)
    priority: Optional[int] = Field(default=None, ge=1)
    enabled: Optional[bool] = None
    fallback_enabled: Optional[bool] = None
    require_json_output: Optional[bool] = None
    force_json_output: Optional[bool] = None
    json_schema: Optional[Dict[str, Any]] = None
    strict_json: Optional[bool] = None
    repair_invalid_json: Optional[bool] = None
    retry_on_invalid_json: Optional[bool] = None
    require_no_think: Optional[bool] = None
    no_think: Optional[bool] = None
    reasoning_mode: Optional[CavadaLabsReasoningMode] = None
    hide_reasoning: Optional[bool] = None
    strip_thinking_tags: Optional[bool] = None
    prefer_loaded_model: Optional[bool] = None
    max_cost_input: Optional[float] = Field(default=None, ge=0)
    max_cost_output: Optional[float] = Field(default=None, ge=0)
    required_capabilities: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("required_capabilities")
    @classmethod
    def clean_required_capabilities(
        cls, values: Optional[List[str]]
    ) -> Optional[List[str]]:
        if values is None:
            return None
        return _dedupe_clean(values, lower=True)


class CavadaLabsProjectModelPolicyResponse(CavadaLabsProjectModelPolicyCreateRequest):
    policy_id: str
    company_id: str
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


class CavadaLabsProjectModelPolicyListResponse(CavadaLabsBaseModel):
    model_policies: List[CavadaLabsProjectModelPolicyResponse]
    count: int


class CavadaLabsNodeCreateRequest(CavadaLabsBaseModel):
    display_name: str = Field(min_length=1, max_length=256)
    hostname: Optional[str] = Field(default=None, max_length=256)
    location: Optional[str] = Field(default=None, max_length=256)
    status: CavadaLabsNodeStatus = CavadaLabsNodeStatus.PENDING
    public_key: Optional[str] = Field(default=None, min_length=32)
    agent_version: Optional[str] = Field(default=None, max_length=128)
    allowed_project_ids: List[str] = Field(default_factory=list)
    pools: List[str] = Field(default_factory=list)
    default_electricity_cost_per_kwh: Optional[float] = Field(default=None, ge=0)
    fixed_hourly_cost: Optional[float] = Field(default=None, ge=0)
    hardware_amortization_hourly_cost: Optional[float] = Field(default=None, ge=0)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("allowed_project_ids", "pools")
    @classmethod
    def clean_string_lists(cls, values: List[str]) -> List[str]:
        return _dedupe_clean(values)


class CavadaLabsNodeUpdateRequest(CavadaLabsBaseModel):
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=256)
    hostname: Optional[str] = Field(default=None, max_length=256)
    location: Optional[str] = Field(default=None, max_length=256)
    status: Optional[CavadaLabsNodeStatus] = None
    public_key: Optional[str] = Field(default=None, min_length=32)
    agent_version: Optional[str] = Field(default=None, max_length=128)
    allowed_project_ids: Optional[List[str]] = None
    pools: Optional[List[str]] = None
    default_electricity_cost_per_kwh: Optional[float] = Field(default=None, ge=0)
    fixed_hourly_cost: Optional[float] = Field(default=None, ge=0)
    hardware_amortization_hourly_cost: Optional[float] = Field(default=None, ge=0)
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("allowed_project_ids", "pools")
    @classmethod
    def clean_optional_string_lists(
        cls, values: Optional[List[str]]
    ) -> Optional[List[str]]:
        if values is None:
            return None
        return _dedupe_clean(values)


class CavadaLabsNodeResponse(CavadaLabsNodeCreateRequest):
    node_id: str
    public_key_fingerprint: Optional[str] = None
    last_heartbeat_at: Optional[datetime] = None
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


class CavadaLabsNodeListResponse(CavadaLabsBaseModel):
    nodes: List[CavadaLabsNodeResponse]
    count: int


class CavadaLabsNodeEnrollmentCreateRequest(CavadaLabsBaseModel):
    expires_in_seconds: int = Field(default=3600, ge=60, le=604800)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CavadaLabsNodeEnrollmentResponse(CavadaLabsBaseModel):
    enrollment_id: str
    node_id: str
    secret_prefix: str
    status: CavadaLabsNodeEnrollmentStatus
    expires_at: datetime
    used_at: Optional[datetime] = None
    metadata: Dict[str, Any]
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


class CavadaLabsNodeEnrollmentCreateResponse(CavadaLabsBaseModel):
    enrollment: CavadaLabsNodeEnrollmentResponse
    enrollment_secret: str


class CavadaLabsNodeEnrollmentCompleteRequest(CavadaLabsBaseModel):
    enrollment_secret: str = Field(min_length=32)
    public_key: str = Field(min_length=32)
    agent_version: Optional[str] = Field(default=None, max_length=128)
    hostname: Optional[str] = Field(default=None, max_length=256)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CavadaLabsNodeEnrollmentCompleteResponse(CavadaLabsBaseModel):
    node: CavadaLabsNodeResponse
    runtime_config: Dict[str, Any]


class CavadaLabsGPUInventoryItem(CavadaLabsBaseModel):
    gpu_id: Optional[str] = Field(default=None, min_length=1)
    vendor: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=256)
    uuid: Optional[str] = Field(default=None, max_length=256)
    vram_total_mb: int = Field(gt=0)
    status: CavadaLabsGPUStatus = CavadaLabsGPUStatus.AVAILABLE
    loaded_model_ids: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("loaded_model_ids")
    @classmethod
    def clean_loaded_model_ids(cls, values: List[str]) -> List[str]:
        return _dedupe_clean(values)


class CavadaLabsGPUInventoryRequest(CavadaLabsBaseModel):
    gpus: List[CavadaLabsGPUInventoryItem] = Field(min_length=1)


class CavadaLabsGPUResponse(CavadaLabsGPUInventoryItem):
    gpu_id: str
    node_id: str
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


class CavadaLabsGPUListResponse(CavadaLabsBaseModel):
    gpus: List[CavadaLabsGPUResponse]
    count: int


class CavadaLabsNodeHeartbeatRequest(CavadaLabsBaseModel):
    status: CavadaLabsNodeStatus = CavadaLabsNodeStatus.ONLINE
    agent_version: Optional[str] = Field(default=None, max_length=128)
    hostname: Optional[str] = Field(default=None, max_length=256)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_admin_only_statuses(self) -> "CavadaLabsNodeHeartbeatRequest":
        if self.status in {
            CavadaLabsNodeStatus.PENDING.value,
            CavadaLabsNodeStatus.DISABLED.value,
        }:
            raise ValueError("node heartbeat cannot set pending or disabled status")
        return self


class CavadaLabsNodeDailyReportRequest(CavadaLabsBaseModel):
    report_date: date
    samples: List[Dict[str, Any]] = Field(default_factory=list)
    total_kwh: float = Field(default=0.0, ge=0)
    total_model_runtime_seconds: int = Field(default=0, ge=0)
    total_loaded_model_seconds: int = Field(default=0, ge=0)
    total_requests: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    node_cost_estimate: Optional[float] = Field(default=None, ge=0)
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CavadaLabsNodeDailyReportResponse(CavadaLabsBaseModel):
    report_id: str
    node_id: str
    report_date: datetime
    samples: List[Dict[str, Any]]
    total_kwh: float
    total_model_runtime_seconds: int
    total_loaded_model_seconds: int
    total_requests: int
    total_tokens: int
    node_cost_estimate: float
    errors: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


class CavadaLabsModelLoadRequestCreateRequest(CavadaLabsBaseModel):
    company_id: Optional[str] = Field(default=None, min_length=1)
    project_id: str = Field(min_length=1)
    model_alias: str = Field(min_length=1, max_length=256)
    provider: str = Field(default="cavadalabs", min_length=1, max_length=128)
    node_id: Optional[str] = Field(default=None, min_length=1)
    gpu_id: Optional[str] = Field(default=None, min_length=1)
    priority: int = Field(default=100, ge=1)
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CavadaLabsModelLoadRequestUpdateRequest(CavadaLabsBaseModel):
    node_id: Optional[str] = Field(default=None, min_length=1)
    gpu_id: Optional[str] = Field(default=None, min_length=1)
    loaded_model_id: Optional[str] = Field(default=None, min_length=1)
    status: Optional[CavadaLabsModelRuntimeStatus] = None
    priority: Optional[int] = Field(default=None, ge=1)
    expires_at: Optional[datetime] = None
    last_error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class CavadaLabsModelLoadRequestResponse(CavadaLabsBaseModel):
    model_load_request_id: str
    company_id: Optional[str] = None
    project_id: str
    model_alias: str
    provider: str
    node_id: Optional[str] = None
    gpu_id: Optional[str] = None
    loaded_model_id: Optional[str] = None
    status: CavadaLabsModelRuntimeStatus
    priority: int
    requested_by: str
    requested_at: datetime
    expires_at: Optional[datetime] = None
    last_error: Optional[str] = None
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


class CavadaLabsModelLoadRequestListResponse(CavadaLabsBaseModel):
    model_load_requests: List[CavadaLabsModelLoadRequestResponse]
    count: int


class CavadaLabsLoadedModelUpsertRequest(CavadaLabsBaseModel):
    loaded_model_id: Optional[str] = Field(default=None, min_length=1)
    gpu_id: Optional[str] = Field(default=None, min_length=1)
    model_alias: str = Field(min_length=1, max_length=256)
    provider: str = Field(default="cavadalabs", min_length=1, max_length=128)
    status: CavadaLabsModelRuntimeStatus = CavadaLabsModelRuntimeStatus.LOADING
    load_request_id: Optional[str] = Field(default=None, min_length=1)
    context_window: Optional[int] = Field(default=None, gt=0)
    capabilities: List[str] = Field(default_factory=list)
    loaded_at: Optional[datetime] = None
    unloaded_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("capabilities")
    @classmethod
    def clean_capabilities(cls, values: List[str]) -> List[str]:
        return _dedupe_clean(values, lower=True)


class CavadaLabsLoadedModelResponse(CavadaLabsLoadedModelUpsertRequest):
    loaded_model_id: str
    node_id: str
    last_used_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class CavadaLabsGPULockCreateRequest(CavadaLabsBaseModel):
    node_id: str = Field(min_length=1)
    gpu_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1, max_length=256)
    project_id: str = Field(min_length=1)
    owner_type: str = Field(min_length=1, max_length=64)
    owner_id: str = Field(min_length=1, max_length=256)
    priority: int = Field(ge=1)
    expires_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CavadaLabsGPULockResponse(CavadaLabsGPULockCreateRequest):
    lock_id: str
    status: CavadaLabsGPULockStatus
    released_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class CavadaLabsGPULockListResponse(CavadaLabsBaseModel):
    gpu_locks: List[CavadaLabsGPULockResponse]
    count: int


class CavadaLabsBillingReportGenerateRequest(CavadaLabsBaseModel):
    company_id: str = Field(min_length=1)
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    formats: List[CavadaLabsBillingReportFormat] = Field(
        default_factory=lambda: [
            CavadaLabsBillingReportFormat.JSON,
            CavadaLabsBillingReportFormat.CSV,
            CavadaLabsBillingReportFormat.XLSX,
            CavadaLabsBillingReportFormat.PDF,
        ]
    )
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    tax_rate: Optional[float] = Field(default=None, ge=0, le=1)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("formats")
    @classmethod
    def clean_formats(
        cls, values: List[CavadaLabsBillingReportFormat]
    ) -> List[CavadaLabsBillingReportFormat]:
        cleaned: List[CavadaLabsBillingReportFormat] = []
        seen = set()
        for value in values:
            raw_value = value.value if isinstance(value, enum.Enum) else value
            if raw_value in seen:
                continue
            cleaned.append(value)
            seen.add(raw_value)
        if not cleaned:
            raise ValueError("formats cannot be empty")
        return cleaned

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class CavadaLabsBillingReportResponse(CavadaLabsBaseModel):
    report_id: str
    company_id: str
    report_version: int
    period_start: datetime
    period_end: datetime
    currency: str
    status: CavadaLabsBillingReportStatus
    formats: List[CavadaLabsBillingReportFormat]
    total_requests: int
    total_tokens: int
    total_spend: float
    provider_cost: float
    cavadalabs_node_cost: float
    tax_rate: Optional[float] = None
    tax_amount: Optional[float] = None
    grand_total: float
    checksum: str
    inputs_snapshot: Dict[str, Any]
    totals: Dict[str, Any]
    breakdowns: Dict[str, Any]
    artifacts: Dict[str, Any]
    metadata: Dict[str, Any]
    generated_at: datetime
    generated_by: str
    created_at: datetime
    updated_at: datetime


class CavadaLabsBillingReportListResponse(CavadaLabsBaseModel):
    billing_reports: List[CavadaLabsBillingReportResponse]
    count: int


class CavadaLabsGuardrailPolicyCreateRequest(CavadaLabsBaseModel):
    company_id: str = Field(min_length=1)
    project_id: Optional[str] = Field(default=None, min_length=1)
    chatbot_id: Optional[str] = Field(default=None, min_length=1)
    name: str = Field(min_length=1, max_length=256)
    version: int = Field(default=1, ge=1)
    scope: CavadaLabsGuardrailPolicyScope = CavadaLabsGuardrailPolicyScope.COMPANY
    status: CavadaLabsGuardrailPolicyStatus = CavadaLabsGuardrailPolicyStatus.DRAFT
    enforcement_mode: CavadaLabsGuardrailEnforcementMode = (
        CavadaLabsGuardrailEnforcementMode.ENFORCE
    )
    description: Optional[str] = Field(default=None, max_length=4096)
    categories: List[str] = Field(default_factory=list)
    rules: Dict[str, Any] = Field(default_factory=dict)
    blocked_patterns: List[str] = Field(default_factory=list)
    redaction_patterns: Dict[str, str] = Field(default_factory=dict)
    pii_detection_enabled: bool = True
    prompt_injection_detection_enabled: bool = True
    log_raw_content: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_scope(self) -> "CavadaLabsGuardrailPolicyCreateRequest":
        if (
            self.scope == CavadaLabsGuardrailPolicyScope.PROJECT
            and self.project_id is None
        ):
            raise ValueError("project-scoped guardrail policies require project_id")
        if self.scope == CavadaLabsGuardrailPolicyScope.CHATBOT:
            if self.project_id is None or self.chatbot_id is None:
                raise ValueError(
                    "chatbot-scoped guardrail policies require project_id and chatbot_id"
                )
        if self.scope == CavadaLabsGuardrailPolicyScope.COMPANY and (
            self.project_id is not None or self.chatbot_id is not None
        ):
            raise ValueError(
                "company-scoped guardrail policies must not set project_id or chatbot_id"
            )
        return self


class CavadaLabsGuardrailPolicyUpdateRequest(CavadaLabsBaseModel):
    status: Optional[CavadaLabsGuardrailPolicyStatus] = None
    enforcement_mode: Optional[CavadaLabsGuardrailEnforcementMode] = None
    description: Optional[str] = Field(default=None, max_length=4096)
    categories: Optional[List[str]] = None
    rules: Optional[Dict[str, Any]] = None
    blocked_patterns: Optional[List[str]] = None
    redaction_patterns: Optional[Dict[str, str]] = None
    pii_detection_enabled: Optional[bool] = None
    prompt_injection_detection_enabled: Optional[bool] = None
    log_raw_content: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None


class CavadaLabsGuardrailPolicyResponse(CavadaLabsBaseModel):
    policy_id: str
    company_id: str
    project_id: Optional[str] = None
    chatbot_id: Optional[str] = None
    name: str
    version: int
    scope: CavadaLabsGuardrailPolicyScope
    status: CavadaLabsGuardrailPolicyStatus
    enforcement_mode: CavadaLabsGuardrailEnforcementMode
    description: Optional[str] = None
    categories: List[str]
    rules: Dict[str, Any]
    blocked_patterns: List[str]
    redaction_patterns: Dict[str, str]
    pii_detection_enabled: bool
    prompt_injection_detection_enabled: bool
    log_raw_content: bool
    metadata: Dict[str, Any]
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


class CavadaLabsGuardrailPolicyListResponse(CavadaLabsBaseModel):
    guardrail_policies: List[CavadaLabsGuardrailPolicyResponse]
    count: int


class CavadaLabsGuardrailDecisionLogResponse(CavadaLabsBaseModel):
    decision_id: str
    policy_id: Optional[str] = None
    policy_name: Optional[str] = None
    company_id: str
    project_id: Optional[str] = None
    chatbot_id: Optional[str] = None
    web_token_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    phase: CavadaLabsGuardrailPhase
    decision: CavadaLabsGuardrailDecision
    action: CavadaLabsGuardrailDecision
    confidence: Optional[float] = None
    reason_code: Optional[str] = None
    triggered_rules: List[Dict[str, Any]]
    redaction_summary: Dict[str, Any]
    latency_ms: int
    metadata: Dict[str, Any]
    created_at: datetime


class CavadaLabsGuardrailDecisionLogListResponse(CavadaLabsBaseModel):
    guardrail_decisions: List[CavadaLabsGuardrailDecisionLogResponse]
    count: int


class CavadaLabsGuardrailEvaluateRequest(CavadaLabsBaseModel):
    company_id: str = Field(min_length=1)
    project_id: Optional[str] = Field(default=None, min_length=1)
    chatbot_id: Optional[str] = Field(default=None, min_length=1)
    web_token_id: Optional[str] = Field(default=None, min_length=1)
    session_id: Optional[str] = Field(default=None, min_length=1)
    request_id: Optional[str] = Field(default=None, min_length=1)
    phase: CavadaLabsGuardrailPhase = CavadaLabsGuardrailPhase.PRE_CALL
    text: str = Field(default="", max_length=2_000_000)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CavadaLabsGuardrailEvaluationResult(CavadaLabsBaseModel):
    decision: CavadaLabsGuardrailDecision
    action: CavadaLabsGuardrailDecision
    blocked: bool
    redacted_text: Optional[str] = None
    reason_code: Optional[str] = None
    triggered_rules: List[Dict[str, Any]]
    decisions: List[CavadaLabsGuardrailDecisionLogResponse]


class CavadaLabsSchedulerRunRequest(CavadaLabsBaseModel):
    project_id: Optional[str] = Field(default=None, min_length=1)
    node_ids: Optional[List[str]] = None
    gpu_ids: Optional[List[str]] = None
    take: int = Field(default=10, ge=1, le=100)
    lock_ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    min_vram_mb: Optional[int] = Field(default=None, gt=0)
    fail_if_no_capacity: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("node_ids", "gpu_ids")
    @classmethod
    def clean_optional_string_lists(
        cls, values: Optional[List[str]]
    ) -> Optional[List[str]]:
        if values is None:
            return None
        return _dedupe_clean(values)


class CavadaLabsSchedulerSkippedRequest(CavadaLabsBaseModel):
    model_load_request_id: str
    reason: str


class CavadaLabsSchedulerAssignmentResponse(CavadaLabsBaseModel):
    model_load_request: CavadaLabsModelLoadRequestResponse
    node: CavadaLabsNodeResponse
    gpu: CavadaLabsGPUResponse
    gpu_lock: Optional[CavadaLabsGPULockResponse] = None
    loaded_model: Optional[CavadaLabsLoadedModelResponse] = None


class CavadaLabsSchedulerRunResponse(CavadaLabsBaseModel):
    scheduled: List[CavadaLabsSchedulerAssignmentResponse]
    skipped: List[CavadaLabsSchedulerSkippedRequest]
    expired_locks: List[CavadaLabsGPULockResponse]
    count: int


class CavadaLabsNodeModelLoadWorkRequest(CavadaLabsBaseModel):
    statuses: List[CavadaLabsModelRuntimeStatus] = Field(
        default_factory=lambda: [
            CavadaLabsModelRuntimeStatus.LOCKING,
            CavadaLabsModelRuntimeStatus.LOADING,
        ]
    )
    take: int = Field(default=25, ge=1, le=100)

    @field_validator("statuses")
    @classmethod
    def clean_statuses(
        cls, values: List[CavadaLabsModelRuntimeStatus]
    ) -> List[CavadaLabsModelRuntimeStatus]:
        cleaned: List[CavadaLabsModelRuntimeStatus] = []
        seen = set()
        for status_value in values:
            raw_value = (
                status_value.value
                if isinstance(status_value, CavadaLabsModelRuntimeStatus)
                else status_value
            )
            if raw_value in seen:
                continue
            cleaned.append(status_value)
            seen.add(raw_value)
        if not cleaned:
            raise ValueError("statuses cannot be empty")
        return cleaned


class CavadaLabsWebTokenValidationResult(CavadaLabsBaseModel):
    active: bool
    reason: Optional[str] = None
    company_id: Optional[str] = None
    project_id: Optional[str] = None
    chatbot_id: Optional[str] = None
    web_token_id: Optional[str] = None


class CavadaLabsChatCompletionRequest(CavadaLabsBaseModel):
    model_config = ConfigDict(
        use_enum_values=True,
        protected_namespaces=(),
        extra="forbid",
    )

    messages: List[AllMessageValues] = Field(min_length=1)
    session_id: str = Field(min_length=1, max_length=256)
    client_request_id: Optional[str] = Field(default=None, max_length=256)
    stream: bool = False
    stream_options: Optional[Dict[str, Any]] = None
    temperature: Optional[float] = Field(default=None, ge=0, le=2)
    top_p: Optional[float] = Field(default=None, ge=0, le=1)
    max_tokens: Optional[int] = Field(default=None, gt=0)
    stop: Optional[Union[str, List[str]]] = None
    presence_penalty: Optional[float] = Field(default=None, ge=-2, le=2)
    frequency_penalty: Optional[float] = Field(default=None, ge=-2, le=2)
    response_format: Optional[Dict[str, Any]] = None
    seed: Optional[int] = None
    user: Optional[str] = Field(default=None, max_length=256)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("messages")
    @classmethod
    def reject_browser_control_messages(
        cls, values: List[AllMessageValues]
    ) -> List[AllMessageValues]:
        for message in values:
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            if role in {"system", "developer"}:
                raise ValueError(
                    "browser chatbot requests cannot include system or developer messages"
                )
        return values

    @field_validator("metadata")
    @classmethod
    def reject_reserved_metadata(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        reserved_keys = {
            "cavadalabs",
            "cavadalabs_company_id",
            "cavadalabs_project_id",
            "cavadalabs_chatbot_id",
            "cavadalabs_web_token_id",
            "cavadalabs_provider",
        }
        if any(key in value for key in reserved_keys):
            raise ValueError("metadata contains reserved CavadaLabs keys")
        return value
