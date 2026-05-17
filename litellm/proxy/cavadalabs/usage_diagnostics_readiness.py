from __future__ import annotations

from typing import Any, Dict, List, Optional

from litellm.proxy.cavadalabs.usage_schema_readiness import UsageSchemaState
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsUsageDiagnosticsAction,
    CavadaLabsUsageDiagnosticsItem,
    CavadaLabsUsageDiagnosticsStatus,
    CavadaLabsUsageReadinessCheck,
    CavadaLabsUsageReadinessCheckStatus,
    CavadaLabsUsageSchemaStatus,
)


def _check(
    *,
    code: str,
    status: CavadaLabsUsageReadinessCheckStatus,
    message: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    recommended_action: CavadaLabsUsageDiagnosticsAction = (
        CavadaLabsUsageDiagnosticsAction.NONE
    ),
    details: Optional[Dict[str, Any]] = None,
) -> CavadaLabsUsageReadinessCheck:
    return CavadaLabsUsageReadinessCheck(
        code=code,
        status=status,
        message=message,
        entity_type=entity_type,
        entity_id=entity_id,
        recommended_action=recommended_action,
        details=details or {},
    )


def _schema_readiness_check(
    schema_state: UsageSchemaState,
) -> CavadaLabsUsageReadinessCheck:
    if schema_state.schema_status == CavadaLabsUsageSchemaStatus.MISSING_SCHEMA:
        return _check(
            code="usage_schema",
            status=CavadaLabsUsageReadinessCheckStatus.BLOCKED,
            message=(
                "CavadaLabs usage schema is missing or incomplete. Run the "
                "Prisma migration deploy command before evaluating scoped "
                "Company/Project usage or repair."
            ),
            recommended_action=CavadaLabsUsageDiagnosticsAction.RUN_MIGRATION_BACKFILL,
            details={
                "schema_status": schema_state.schema_status.value,
                "migration_status": schema_state.migration_status.value,
                "missing_schema": schema_state.missing_schema,
            },
        )

    return _check(
        code="usage_schema",
        status=CavadaLabsUsageReadinessCheckStatus.READY,
        message=(
            "CavadaLabs usage schema is available for Company/Project "
            "diagnostics."
        ),
        details={
            "schema_status": schema_state.schema_status.value,
            "migration_status": schema_state.migration_status.value,
        },
    )


def _has_missing_mapping(item: CavadaLabsUsageDiagnosticsItem) -> bool:
    return (
        bool(item.missing_mappings)
        or item.unmapped_spend_logs > 0
        or item.legacy_key_spend_logs > 0
        or item.legacy_keys_missing_metadata > 0
    )


def _ledger_check(
    item: CavadaLabsUsageDiagnosticsItem,
) -> CavadaLabsUsageReadinessCheck:
    if item.missing_schema:
        return _check(
            code="ledger_rows",
            status=CavadaLabsUsageReadinessCheckStatus.BLOCKED,
            message=(
                "Ledger rows cannot be checked because the CavadaLabs request "
                "ledger schema is missing or incomplete."
            ),
            entity_type=item.entity_type,
            entity_id=item.entity_id,
            recommended_action=CavadaLabsUsageDiagnosticsAction.RUN_MIGRATION_BACKFILL,
            details={"missing_schema": item.missing_schema},
        )
    if item.ledger_rows > 0:
        return _check(
            code="ledger_rows",
            status=CavadaLabsUsageReadinessCheckStatus.READY,
            message="CavadaLabs request ledger rows exist for this scope.",
            entity_type=item.entity_type,
            entity_id=item.entity_id,
            details={
                "ledger_rows": item.ledger_rows,
                "ledger_total_spend": item.ledger_total_spend,
                "ledger_min_created_at": item.ledger_min_created_at,
                "ledger_max_created_at": item.ledger_max_created_at,
            },
        )
    if item.attributable_spend_logs > 0:
        return _check(
            code="ledger_rows",
            status=CavadaLabsUsageReadinessCheckStatus.ACTION_REQUIRED,
            message=(
                "No CavadaLabs request ledger rows exist for this scope, but "
                "LiteLLM SpendLogs contain attributable usage."
            ),
            entity_type=item.entity_type,
            entity_id=item.entity_id,
            recommended_action=CavadaLabsUsageDiagnosticsAction.RUN_SCOPED_BACKFILL,
            details={
                "ledger_rows": item.ledger_rows,
                "attributable_spend_logs": item.attributable_spend_logs,
            },
        )

    return _check(
        code="ledger_rows",
        status=CavadaLabsUsageReadinessCheckStatus.WARNING,
        message=(
            "No CavadaLabs request ledger rows exist for this scope and date "
            "range."
        ),
        entity_type=item.entity_type,
        entity_id=item.entity_id,
        details={"ledger_rows": item.ledger_rows},
    )


def _spend_logs_check(
    item: CavadaLabsUsageDiagnosticsItem,
) -> CavadaLabsUsageReadinessCheck:
    if item.missing_schema:
        return _check(
            code="spendlogs_attribution",
            status=CavadaLabsUsageReadinessCheckStatus.BLOCKED,
            message=(
                "SpendLogs attribution cannot be checked because the usage "
                "schema is missing or incomplete."
            ),
            entity_type=item.entity_type,
            entity_id=item.entity_id,
            recommended_action=CavadaLabsUsageDiagnosticsAction.RUN_MIGRATION_BACKFILL,
            details={"missing_schema": item.missing_schema},
        )
    if item.attributable_spend_logs > 0:
        return _check(
            code="spendlogs_attribution",
            status=CavadaLabsUsageReadinessCheckStatus.READY,
            message=(
                "LiteLLM SpendLogs contain Company/Project-attributable usage "
                "for this scope."
            ),
            entity_type=item.entity_type,
            entity_id=item.entity_id,
            details={
                "attributable_spend_logs": item.attributable_spend_logs,
                "metadata_spend_logs": item.metadata_spend_logs,
                "compatibility_spend_logs": item.compatibility_spend_logs,
                "key_metadata_spend_logs": item.key_metadata_spend_logs,
            },
        )
    if _has_missing_mapping(item):
        return _check(
            code="spendlogs_attribution",
            status=CavadaLabsUsageReadinessCheckStatus.ACTION_REQUIRED,
            message=(
                "LiteLLM SpendLogs exist for compatibility scopes, but they "
                "lack enough CavadaLabs Company/Project attribution."
            ),
            entity_type=item.entity_type,
            entity_id=item.entity_id,
            recommended_action=CavadaLabsUsageDiagnosticsAction.FIX_COMPATIBILITY_MAPPING,
            details={
                "missing_mappings": item.missing_mappings,
                "legacy_keys_missing_metadata": item.legacy_keys_missing_metadata,
                "legacy_key_spend_logs": item.legacy_key_spend_logs,
                "unmapped_spend_logs": item.unmapped_spend_logs,
            },
        )

    return _check(
        code="spendlogs_attribution",
        status=CavadaLabsUsageReadinessCheckStatus.WARNING,
        message=(
            "No LiteLLM SpendLogs with CavadaLabs Company/Project attribution "
            "match this scope and date range."
        ),
        entity_type=item.entity_type,
        entity_id=item.entity_id,
        details={
            "attributable_spend_logs": item.attributable_spend_logs,
            "all_time_attributable_spend_logs": item.all_time_attributable_spend_logs,
            "unfiltered_attributable_spend_logs": (
                item.unfiltered_attributable_spend_logs
            ),
        },
    )


def _repair_check(
    item: CavadaLabsUsageDiagnosticsItem,
) -> CavadaLabsUsageReadinessCheck:
    if item.missing_schema:
        return _check(
            code="repair_status",
            status=CavadaLabsUsageReadinessCheckStatus.BLOCKED,
            message="Scoped repair is blocked until the usage schema is migrated.",
            entity_type=item.entity_type,
            entity_id=item.entity_id,
            recommended_action=CavadaLabsUsageDiagnosticsAction.RUN_MIGRATION_BACKFILL,
            details={"missing_schema": item.missing_schema},
        )
    if item.scoped_backfill_available or item.repair_dry_run.available:
        return _check(
            code="repair_status",
            status=CavadaLabsUsageReadinessCheckStatus.ACTION_REQUIRED,
            message=(
                "Scoped repair can copy attributable SpendLogs into the "
                "CavadaLabs request ledger for this Company/Project scope."
            ),
            entity_type=item.entity_type,
            entity_id=item.entity_id,
            recommended_action=CavadaLabsUsageDiagnosticsAction.RUN_SCOPED_BACKFILL,
            details={
                "dry_run_available": item.repair_dry_run.available,
                "would_repair": item.repair_dry_run.would_repair,
                "scoped_spend_logs": item.repair_dry_run.scoped_spend_logs,
                "missing_ledger_rows": item.repair_dry_run.missing_ledger_rows,
            },
        )
    if _has_missing_mapping(item):
        return _check(
            code="repair_status",
            status=CavadaLabsUsageReadinessCheckStatus.ACTION_REQUIRED,
            message=(
                "Scoped repair is not safe until missing Company/Project key "
                "metadata or compatibility mappings are fixed."
            ),
            entity_type=item.entity_type,
            entity_id=item.entity_id,
            recommended_action=CavadaLabsUsageDiagnosticsAction.FIX_COMPATIBILITY_MAPPING,
            details={
                "missing_mappings": item.missing_mappings,
                "legacy_key_spend_logs": item.legacy_key_spend_logs,
                "unmapped_spend_logs": item.unmapped_spend_logs,
            },
        )
    if item.status == CavadaLabsUsageDiagnosticsStatus.FILTERS_EXCLUDE_USAGE:
        return _check(
            code="repair_status",
            status=CavadaLabsUsageReadinessCheckStatus.WARNING,
            message=(
                "Scoped repair is not recommended until the date range or "
                "model/provider/API key filters include the attributable usage."
            ),
            entity_type=item.entity_type,
            entity_id=item.entity_id,
            details={
                "filters_exclude_usage": item.filters_exclude_usage,
                "date_range_excludes_usage": item.date_range_excludes_usage,
            },
        )

    return _check(
        code="repair_status",
        status=CavadaLabsUsageReadinessCheckStatus.READY,
        message="No scoped usage repair is currently required for this scope.",
        entity_type=item.entity_type,
        entity_id=item.entity_id,
        details={
            "dry_run_attempted": item.repair_dry_run.attempted,
            "scoped_spend_logs": item.repair_dry_run.scoped_spend_logs,
            "missing_ledger_rows": item.repair_dry_run.missing_ledger_rows,
        },
    )


def _filter_checks(
    item: CavadaLabsUsageDiagnosticsItem,
) -> List[CavadaLabsUsageReadinessCheck]:
    checks: List[CavadaLabsUsageReadinessCheck] = []
    if item.filters_exclude_usage:
        checks.append(
            _check(
                code="filters",
                status=CavadaLabsUsageReadinessCheckStatus.WARNING,
                message=(
                    "The selected model/provider/API key filters exclude "
                    "Company/Project-attributable usage in this date range."
                ),
                entity_type=item.entity_type,
                entity_id=item.entity_id,
                details={
                    "unfiltered_attributable_spend_logs": (
                        item.unfiltered_attributable_spend_logs
                    )
                },
            )
        )
    if item.date_range_excludes_usage:
        checks.append(
            _check(
                code="date_range",
                status=CavadaLabsUsageReadinessCheckStatus.WARNING,
                message=(
                    "This Company/Project has attributable usage outside the "
                    "selected date range."
                ),
                entity_type=item.entity_type,
                entity_id=item.entity_id,
                details={
                    "all_time_attributable_spend_logs": (
                        item.all_time_attributable_spend_logs
                    )
                },
            )
        )
    return checks


def _diagnostic_readiness_checks(
    item: CavadaLabsUsageDiagnosticsItem,
) -> List[CavadaLabsUsageReadinessCheck]:
    return [
        _ledger_check(item),
        _spend_logs_check(item),
        _repair_check(item),
        *_filter_checks(item),
    ]


def build_usage_readiness_checks(
    *,
    schema_state: UsageSchemaState,
    diagnostics: List[CavadaLabsUsageDiagnosticsItem],
) -> List[CavadaLabsUsageReadinessCheck]:
    checks = [_schema_readiness_check(schema_state)]
    for item in diagnostics:
        checks.extend(_diagnostic_readiness_checks(item))
    return checks
