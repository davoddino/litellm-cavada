from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from inspect import isawaitable
from typing import Any, Dict, List

from fastapi import HTTPException, status

from litellm.proxy.cavadalabs.usage_query_filters import (
    metadata_scope_filters,
    spend_log_repair_where,
)
from litellm.proxy.utils import PrismaClient
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsUsageDiagnosticsAction,
    CavadaLabsUsageDiagnosticsItem,
    CavadaLabsUsageDiagnosticsStatus,
    CavadaLabsUsageMigrationStatus,
    CavadaLabsUsageMigrationStep,
    CavadaLabsUsageSchemaStatus,
)

USAGE_BACKFILL_MIGRATION_STEPS = (
    CavadaLabsUsageMigrationStep(
        name="20260514120000_add_cavadalabs_dispatcher_tables",
        purpose=(
            "Creates CavadaLabs Company, Project, chatbot, web-token, "
            "request-ledger, and audit tables used by product usage."
        ),
    ),
    CavadaLabsUsageMigrationStep(
        name="20260515120000_add_cavadalabs_litellm_membership_mappings",
        purpose=(
            "Adds internal Company-to-LiteLLM Organization and "
            "Project-to-LiteLLM Team compatibility mappings."
        ),
    ),
    CavadaLabsUsageMigrationStep(
        name="20260515122000_add_cavadalabs_usage_spend_log_indexes",
        purpose=(
            "Adds SpendLogs indexes used by scoped Company/Project diagnostics "
            "and repair."
        ),
    ),
    CavadaLabsUsageMigrationStep(
        name="20260515123000_backfill_cavadalabs_request_ledger_from_spend_logs",
        purpose=(
            "Backfills CavadaLabs request ledger rows from SpendLogs metadata "
            "and internal compatibility mappings."
        ),
    ),
    CavadaLabsUsageMigrationStep(
        name="20260515143000_backfill_cavadalabs_request_ledger_from_key_metadata",
        purpose=(
            "Backfills historical SpendLogs from active and deleted key "
            "Company/Project metadata."
        ),
    ),
    CavadaLabsUsageMigrationStep(
        name="20260515161000_backfill_cavadalabs_request_ledger_from_metadata_key_hash",
        purpose=(
            "Backfills historical SpendLogs whose LiteLLM key hash is stored "
            "only in SpendLogs metadata."
        ),
    ),
)
USAGE_BACKFILL_MIGRATION_NAME = USAGE_BACKFILL_MIGRATION_STEPS[-1].name
USAGE_BACKFILL_MIGRATION_COMMAND = (
    "DATABASE_URL='postgresql://USER:PASSWORD@HOST:PORT/DB' "
    "uv run prisma migrate deploy --schema "
    "litellm-proxy-extras/litellm_proxy_extras/schema.prisma"
)

_USAGE_CORE_DELEGATE_METHODS: Dict[str, tuple[str, tuple[str, ...]]] = {
    "cavadalabs_requestledgertable": (
        "CavadaLabs_RequestLedgerTable",
        ("find_many", "count", "create_many"),
    ),
    "cavadalabs_companytable": ("CavadaLabs_CompanyTable", ("find_many",)),
    "cavadalabs_projecttable": ("CavadaLabs_ProjectTable", ("find_many",)),
}
_USAGE_SPEND_LOG_DELEGATE_METHODS: Dict[str, tuple[str, tuple[str, ...]]] = {
    "litellm_spendlogs": ("LiteLLM_SpendLogs", ("count", "find_many")),
}
_USAGE_KEY_CONTEXT_DELEGATE_METHODS: Dict[str, tuple[str, tuple[str, ...]]] = {
    "litellm_verificationtoken": ("LiteLLM_VerificationToken", ("find_many",)),
    "litellm_deletedverificationtoken": (
        "LiteLLM_DeletedVerificationToken",
        ("find_many",),
    ),
}


@dataclass(frozen=True)
class UsageSchemaState:
    schema_status: CavadaLabsUsageSchemaStatus
    migration_status: CavadaLabsUsageMigrationStatus
    missing_schema: List[str]


def usage_backfill_migration_steps() -> List[CavadaLabsUsageMigrationStep]:
    return [
        CavadaLabsUsageMigrationStep(name=step.name, purpose=step.purpose)
        for step in USAGE_BACKFILL_MIGRATION_STEPS
    ]


def usage_backfill_migration_names() -> List[str]:
    return [step.name for step in USAGE_BACKFILL_MIGRATION_STEPS]


def usage_backfill_migration_plan_detail() -> List[Dict[str, str]]:
    return [
        {"name": step.name, "purpose": step.purpose}
        for step in USAGE_BACKFILL_MIGRATION_STEPS
    ]


def ready_usage_schema_state() -> UsageSchemaState:
    return UsageSchemaState(
        schema_status=CavadaLabsUsageSchemaStatus.READY,
        migration_status=CavadaLabsUsageMigrationStatus.READY,
        missing_schema=[],
    )


def missing_usage_schema_state(missing_schema: List[str]) -> UsageSchemaState:
    return UsageSchemaState(
        schema_status=CavadaLabsUsageSchemaStatus.MISSING_SCHEMA,
        migration_status=CavadaLabsUsageMigrationStatus.SCHEMA_MISSING,
        missing_schema=missing_schema,
    )


def looks_like_missing_schema_exception(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "does not exist",
            "no such table",
            "unknown arg",
            "unknown argument",
            "unknown field",
            "column",
            "relation",
            "has no attribute",
        )
    )


def _missing_delegate_methods(
    db: Any,
    delegate_methods: Dict[str, tuple[str, tuple[str, ...]]],
) -> List[str]:
    missing_schema: List[str] = []
    for delegate_name, (model_name, method_names) in delegate_methods.items():
        delegate = getattr(db, delegate_name, None)
        if delegate is None:
            missing_schema.append(f"{model_name} delegate")
            continue
        for method_name in method_names:
            if getattr(delegate, method_name, None) is None:
                missing_schema.append(f"{model_name}.{method_name}")
    return missing_schema


async def _probe_schema_query(
    *,
    missing_schema: List[str],
    model_name: str,
    query: Any,
) -> None:
    try:
        result = query()
        if isawaitable(result):
            await result
    except Exception as exc:
        if looks_like_missing_schema_exception(exc):
            missing_schema.append(f"{model_name}: {exc}")
            return
        raise


def _schema_probe_date_range() -> Dict[str, datetime]:
    return {
        "gte": datetime(1970, 1, 1, tzinfo=timezone.utc),
        "lt": datetime(1970, 1, 2, tzinfo=timezone.utc),
    }


def _usage_ledger_schema_probe_where() -> Dict[str, Any]:
    return {
        "request_id": "__cavadalabs_schema_probe__",
        "company_id": "__cavadalabs_schema_probe__",
        "project_id": "__cavadalabs_schema_probe__",
        "created_at": _schema_probe_date_range(),
        "provider": "__cavadalabs_schema_probe__",
        "status": "__cavadalabs_schema_probe__",
        "api_key_hash": "__cavadalabs_schema_probe__",
        "spend": {"gte": 0.0},
        "AND": [
            {
                "OR": [
                    {"model": "__cavadalabs_schema_probe__"},
                    {
                        "metadata": {
                            "path": ["model_group"],
                            "equals": "__cavadalabs_schema_probe__",
                        }
                    },
                ]
            }
        ],
    }


def _spend_logs_schema_probe_where() -> Dict[str, Any]:
    scope_filters = [
        {"team_id": "__cavadalabs_schema_probe__"},
        {"organization_id": "__cavadalabs_schema_probe__"},
        *metadata_scope_filters("company_id", "__cavadalabs_schema_probe__"),
        *metadata_scope_filters("project_id", "__cavadalabs_schema_probe__"),
    ]
    where = spend_log_repair_where(
        date_range=_schema_probe_date_range(),
        filters=scope_filters,
        model="__cavadalabs_schema_probe__",
        provider="__cavadalabs_schema_probe__",
        api_key="__cavadalabs_schema_probe__",
    )
    where["request_id"] = "__cavadalabs_schema_probe__"
    return where


def _company_schema_probe_where() -> Dict[str, Any]:
    return {
        "OR": [
            {"company_id": "__cavadalabs_schema_probe__"},
            {"litellm_organization_id": "__cavadalabs_schema_probe__"},
        ]
    }


def _project_schema_probe_where() -> Dict[str, Any]:
    return {
        "OR": [
            {"project_id": "__cavadalabs_schema_probe__"},
            {"company_id": "__cavadalabs_schema_probe__"},
            {"litellm_team_id": "__cavadalabs_schema_probe__"},
        ]
    }


def _key_context_schema_probe_where() -> Dict[str, Any]:
    return {
        "OR": [
            {"token": "__cavadalabs_schema_probe__"},
            {"team_id": "__cavadalabs_schema_probe__"},
            {"organization_id": "__cavadalabs_schema_probe__"},
            *metadata_scope_filters("company_id", "__cavadalabs_schema_probe__"),
            *metadata_scope_filters("project_id", "__cavadalabs_schema_probe__"),
        ]
    }


async def probe_usage_schema(
    prisma_client: PrismaClient,
    *,
    include_key_context: bool = False,
    include_spend_logs: bool = True,
) -> UsageSchemaState:
    """Check the Cavada usage read/write schema without mutating data."""

    db = prisma_client.db
    missing_schema = _missing_delegate_methods(db, _USAGE_CORE_DELEGATE_METHODS)
    ledger_delegate = getattr(db, "cavadalabs_requestledgertable", None)
    if ledger_delegate is not None:
        ledger_find_many = getattr(ledger_delegate, "find_many", None)
        if ledger_find_many is not None:
            await _probe_schema_query(
                missing_schema=missing_schema,
                model_name="CavadaLabs_RequestLedgerTable",
                query=lambda: ledger_find_many(
                    where=_usage_ledger_schema_probe_where(),
                    take=1,
                ),
            )

    if include_spend_logs:
        missing_schema.extend(
            _missing_delegate_methods(db, _USAGE_SPEND_LOG_DELEGATE_METHODS)
        )
        spend_logs_delegate = getattr(db, "litellm_spendlogs", None)
        if spend_logs_delegate is not None:
            spend_logs_count = getattr(spend_logs_delegate, "count", None)
            if spend_logs_count is not None:
                await _probe_schema_query(
                    missing_schema=missing_schema,
                    model_name="LiteLLM_SpendLogs",
                    query=lambda: spend_logs_count(
                        where=_spend_logs_schema_probe_where(),
                    ),
                )

    company_delegate = getattr(db, "cavadalabs_companytable", None)
    if company_delegate is not None:
        company_find_many = getattr(company_delegate, "find_many", None)
        if company_find_many is not None:
            await _probe_schema_query(
                missing_schema=missing_schema,
                model_name="CavadaLabs_CompanyTable",
                query=lambda: company_find_many(
                    where=_company_schema_probe_where(),
                    take=1,
                ),
            )

    project_delegate = getattr(db, "cavadalabs_projecttable", None)
    if project_delegate is not None:
        project_find_many = getattr(project_delegate, "find_many", None)
        if project_find_many is not None:
            await _probe_schema_query(
                missing_schema=missing_schema,
                model_name="CavadaLabs_ProjectTable",
                query=lambda: project_find_many(
                    where=_project_schema_probe_where(),
                    take=1,
                ),
            )

    if include_key_context:
        missing_schema.extend(
            _missing_delegate_methods(db, _USAGE_KEY_CONTEXT_DELEGATE_METHODS)
        )
        for delegate_name, model_name in (
            ("litellm_verificationtoken", "LiteLLM_VerificationToken"),
            ("litellm_deletedverificationtoken", "LiteLLM_DeletedVerificationToken"),
        ):
            delegate = getattr(db, delegate_name, None)
            if delegate is None:
                continue
            find_many = getattr(delegate, "find_many", None)
            if find_many is None:
                continue
            await _probe_schema_query(
                missing_schema=missing_schema,
                model_name=model_name,
                query=lambda find_many=find_many: find_many(
                    where=_key_context_schema_probe_where(),
                    take=1,
                ),
            )

    if missing_schema:
        return missing_usage_schema_state(sorted(set(missing_schema)))
    return ready_usage_schema_state()


def diagnostics_migration_status(
    *,
    schema_state: UsageSchemaState,
    diagnostics: List[CavadaLabsUsageDiagnosticsItem],
) -> CavadaLabsUsageMigrationStatus:
    if schema_state.schema_status == CavadaLabsUsageSchemaStatus.MISSING_SCHEMA:
        return CavadaLabsUsageMigrationStatus.SCHEMA_MISSING
    if any(
        item.recommended_action == CavadaLabsUsageDiagnosticsAction.RUN_SCOPED_BACKFILL
        for item in diagnostics
    ):
        return CavadaLabsUsageMigrationStatus.BACKFILL_PENDING
    if any(
        item.recommended_action
        == CavadaLabsUsageDiagnosticsAction.RUN_MIGRATION_BACKFILL
        for item in diagnostics
    ):
        return CavadaLabsUsageMigrationStatus.BACKFILL_REQUIRED
    return CavadaLabsUsageMigrationStatus.READY


def schema_missing_diagnostics(
    *,
    entity_type: str,
    entity_ids: List[str],
    missing_schema: List[str],
) -> List[CavadaLabsUsageDiagnosticsItem]:
    label = "Company" if entity_type == "company" else "Project"
    return [
        CavadaLabsUsageDiagnosticsItem(
            entity_type=entity_type,
            entity_id=entity_id,
            status=CavadaLabsUsageDiagnosticsStatus.BACKFILL_REQUIRED,
            recommended_action=CavadaLabsUsageDiagnosticsAction.RUN_MIGRATION_BACKFILL,
            missing_schema=missing_schema,
            message=(
                f"{label} usage cannot be evaluated because the CavadaLabs "
                "usage schema is missing or incomplete. Run the Prisma "
                "migration deploy command before scoped repair."
            ),
        )
        for entity_id in entity_ids
    ]


def raise_missing_usage_schema_http_exception(
    *,
    schema_state: UsageSchemaState,
    operation: str,
) -> None:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "error": (
                "CavadaLabs usage schema is missing or incomplete. Run the "
                "Prisma migration deploy command before reading Company/Project "
                "usage."
            ),
            "operation": operation,
            "schema_status": schema_state.schema_status.value,
            "migration_status": schema_state.migration_status.value,
            "missing_schema": schema_state.missing_schema,
            "recommended_action": (
                CavadaLabsUsageDiagnosticsAction.RUN_MIGRATION_BACKFILL.value
            ),
            "migration_name": USAGE_BACKFILL_MIGRATION_NAME,
            "migration_command": USAGE_BACKFILL_MIGRATION_COMMAND,
            "migration_names": usage_backfill_migration_names(),
            "migration_plan": usage_backfill_migration_plan_detail(),
        },
    )


async def ensure_cavadalabs_usage_schema_ready(
    *,
    prisma_client: PrismaClient,
    operation: str,
    include_key_context: bool = False,
    include_spend_logs: bool = True,
) -> None:
    schema_state = await probe_usage_schema(
        prisma_client,
        include_key_context=include_key_context,
        include_spend_logs=include_spend_logs,
    )
    if schema_state.schema_status == CavadaLabsUsageSchemaStatus.MISSING_SCHEMA:
        raise_missing_usage_schema_http_exception(
            schema_state=schema_state,
            operation=operation,
        )


async def ensure_cavadalabs_usage_repair_schema_ready(
    *,
    prisma_client: PrismaClient,
    operation: str,
) -> None:
    await ensure_cavadalabs_usage_schema_ready(
        prisma_client=prisma_client,
        operation=operation,
        include_key_context=True,
        include_spend_logs=True,
    )
