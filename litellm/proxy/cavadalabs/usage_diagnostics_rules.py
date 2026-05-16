from __future__ import annotations

from typing import List

from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsUsageDiagnosticsAction,
    CavadaLabsUsageDiagnosticsStatus,
)


def _usage_diagnostics_status(
    *,
    ledger_rows: int,
    attributable_spend_logs: int,
    missing_mappings: List[str],
    unmapped_spend_logs: int,
    filters_exclude_usage: bool,
    date_range_excludes_usage: bool,
) -> CavadaLabsUsageDiagnosticsStatus:
    if attributable_spend_logs > 0:
        if ledger_rows > 0 and ledger_rows >= attributable_spend_logs:
            return CavadaLabsUsageDiagnosticsStatus.VISIBLE
        return CavadaLabsUsageDiagnosticsStatus.SCOPED_BACKFILL_AVAILABLE
    if ledger_rows > 0:
        return CavadaLabsUsageDiagnosticsStatus.VISIBLE
    if filters_exclude_usage or date_range_excludes_usage:
        return CavadaLabsUsageDiagnosticsStatus.FILTERS_EXCLUDE_USAGE
    if missing_mappings or unmapped_spend_logs > 0:
        return CavadaLabsUsageDiagnosticsStatus.MISSING_COMPATIBILITY_MAPPING
    return CavadaLabsUsageDiagnosticsStatus.NO_ATTRIBUTABLE_SPEND


def _usage_diagnostics_action(
    status: CavadaLabsUsageDiagnosticsStatus,
) -> CavadaLabsUsageDiagnosticsAction:
    if status == CavadaLabsUsageDiagnosticsStatus.SCOPED_BACKFILL_AVAILABLE:
        return CavadaLabsUsageDiagnosticsAction.RUN_SCOPED_BACKFILL
    if status == CavadaLabsUsageDiagnosticsStatus.BACKFILL_REQUIRED:
        return CavadaLabsUsageDiagnosticsAction.RUN_MIGRATION_BACKFILL
    if status == CavadaLabsUsageDiagnosticsStatus.MISSING_COMPATIBILITY_MAPPING:
        return CavadaLabsUsageDiagnosticsAction.FIX_COMPATIBILITY_MAPPING
    return CavadaLabsUsageDiagnosticsAction.NONE


def _usage_diagnostics_message(
    *,
    entity_type: str,
    status: CavadaLabsUsageDiagnosticsStatus,
    missing_mappings: List[str],
    unmapped_spend_logs: int = 0,
    filters_exclude_usage: bool = False,
    date_range_excludes_usage: bool = False,
) -> str:
    label = "Company" if entity_type == "company" else "Project"
    if status == CavadaLabsUsageDiagnosticsStatus.VISIBLE:
        return f"{label} usage is visible in the CavadaLabs request ledger."
    if status == CavadaLabsUsageDiagnosticsStatus.SCOPED_BACKFILL_AVAILABLE:
        return (
            f"{label} usage exists in LiteLLM SpendLogs, but matching "
            "CavadaLabs request ledger rows are missing or incomplete for the "
            "selected date range. Selected daily usage and monthly billing "
            "requests will run scoped backfill automatically; apply the "
            "CavadaLabs usage backfill migration for a full historical repair."
        )
    if status == CavadaLabsUsageDiagnosticsStatus.BACKFILL_REQUIRED:
        return (
            f"{label} usage requires the CavadaLabs historical migration "
            "backfill before it can be trusted for full-period reporting."
        )
    if status == CavadaLabsUsageDiagnosticsStatus.MISSING_COMPATIBILITY_MAPPING:
        missing = (
            ", ".join(missing_mappings)
            if missing_mappings
            else "CavadaLabs key metadata or Project compatibility mapping"
        )
        return (
            f"No CavadaLabs-attributable spend was found for this {label}. "
            f"Missing compatibility mapping: {missing}."
        )
    if status == CavadaLabsUsageDiagnosticsStatus.FILTERS_EXCLUDE_USAGE:
        if date_range_excludes_usage:
            return (
                f"This {label} has CavadaLabs-attributable spend outside the "
                "selected date range. Expand the date range before running a "
                "scoped repair."
            )
        if filters_exclude_usage:
            return (
                f"This {label} has CavadaLabs-attributable spend in the "
                "selected date range, but the model/provider/API key filters "
                "exclude it. Relax the filters before running a scoped repair."
            )
    if unmapped_spend_logs > 0:
        return (
            f"{label} SpendLogs were found for the internal compatibility scope, "
            "but some rows are missing enough Company/Project key or project "
            "context to be safely attributed. Add CavadaLabs key metadata or "
            "Project compatibility mappings before repairing historical usage."
        )
    return (
        f"No CavadaLabs-attributable spend exists for this {label} and date "
        "range. Existing legacy LiteLLM spend without Company/Project context "
        "remains hidden from CavadaLabs usage by design."
    )
