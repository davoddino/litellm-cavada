from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest
from fastapi import HTTPException

from litellm.proxy import proxy_server
from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.cavadalabs.usage import get_cavadalabs_usage_diagnostics
from litellm.proxy.management_endpoints import (
    cavadalabs_company_endpoints as company_endpoints,
)
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsUsageDiagnosticsStatus,
    CavadaLabsUsageReadinessCheck,
    CavadaLabsUsageReadinessCheckStatus,
)


UTC = timezone.utc


def _row(**kwargs: Any) -> SimpleNamespace:
    return SimpleNamespace(**kwargs)


def _company(company_id: str = "company-1") -> SimpleNamespace:
    return _row(
        company_id=company_id,
        litellm_organization_id=f"org-{company_id}",
        legal_name=f"Company {company_id}",
        billing_name=None,
        vat_tax_id=None,
        billing_address={},
        admin_emails=[],
        plan="production",
        status="active",
        monthly_budget=100.0,
        metadata={},
        retention_policy={},
        default_guardrail_policy=None,
        default_billing_settings={},
        created_at=datetime(2026, 5, 1, tzinfo=UTC),
        created_by="admin-user",
        updated_at=datetime(2026, 5, 1, tzinfo=UTC),
        updated_by="admin-user",
    )


def _project(
    project_id: str = "project-1",
    company_id: str = "company-1",
) -> SimpleNamespace:
    return _row(
        project_id=project_id,
        company_id=company_id,
        litellm_team_id=f"team-{project_id}",
        name=f"Project {project_id}",
        status="production",
        allowed_models=[],
        allowed_rag_collections=[],
        default_chatbot_settings={},
        default_guardrail_policy=None,
        budget=None,
        retention_policy_override={},
        metadata={},
        created_at=datetime(2026, 5, 1, tzinfo=UTC),
        created_by="admin-user",
        updated_at=datetime(2026, 5, 1, tzinfo=UTC),
        updated_by="admin-user",
    )


def _ledger(
    *,
    request_id: str,
    company_id: str = "company-1",
    project_id: str = "project-1",
    spend: float,
    created_at: datetime,
) -> SimpleNamespace:
    return _row(
        request_id=request_id,
        company_id=company_id,
        project_id=project_id,
        spend=spend,
        created_at=created_at,
        api_key_hash="hashed-key",
        provider="cavadalabs",
        model="cavadalabs/qwen3-32b",
        status="success",
    )


def _spend_log(
    *,
    request_id: str = "spend-1",
    api_key: str = "hashed-key",
    metadata: Optional[Dict[str, Any]] = None,
    start_time: datetime = datetime(2026, 5, 16, 12, tzinfo=UTC),
) -> SimpleNamespace:
    return _row(
        request_id=request_id,
        api_key=api_key,
        metadata=metadata or {},
        startTime=start_time,
    )


def _field_matches(row: Any, field_name: str, expected: Any) -> bool:
    value = getattr(row, field_name, None)
    if isinstance(expected, dict) and "in" in expected:
        return value in expected["in"]
    return value == expected


def _created_at_matches(row: Any, condition: Dict[str, datetime]) -> bool:
    created_at = getattr(row, "created_at", None)
    if not isinstance(created_at, datetime):
        return False
    if "gte" in condition and created_at < condition["gte"]:
        return False
    if "lt" in condition and created_at >= condition["lt"]:
        return False
    return True


class _LedgerDelegate:
    def __init__(self, rows: List[SimpleNamespace]) -> None:
        self.rows = rows
        self.count_calls = 0
        self.find_many_calls: List[Dict[str, Any]] = []

    def _matches(self, row: SimpleNamespace, where: Optional[Dict[str, Any]]) -> bool:
        if not where:
            return True
        for field_name in ("company_id", "project_id", "provider", "status"):
            if field_name in where and not _field_matches(
                row, field_name, where[field_name]
            ):
                return False
        if "api_key_hash" in where and not _field_matches(
            row, "api_key_hash", where["api_key_hash"]
        ):
            return False
        created_at = where.get("created_at")
        if isinstance(created_at, dict) and not _created_at_matches(row, created_at):
            return False
        return True

    async def count(self, *, where: Optional[Dict[str, Any]] = None) -> int:
        self.count_calls += 1
        return len([row for row in self.rows if self._matches(row, where)])

    async def create_many(self, **_: Any) -> SimpleNamespace:
        return _row(count=0)

    async def find_many(
        self,
        *,
        where: Optional[Dict[str, Any]] = None,
        take: Optional[int] = None,
        skip: int = 0,
        order: Optional[Dict[str, str]] = None,
        select: Optional[Dict[str, bool]] = None,
    ) -> List[SimpleNamespace]:
        self.find_many_calls.append(
            {
                "where": where,
                "take": take,
                "skip": skip,
                "order": order,
                "select": select,
            }
        )
        if where and where.get("request_id") == "__cavadalabs_schema_probe__":
            return []
        rows = [row for row in self.rows if self._matches(row, where)]
        if order and order.get("created_at") == "asc":
            rows = sorted(rows, key=lambda row: row.created_at)
        if order and order.get("created_at") == "desc":
            rows = sorted(rows, key=lambda row: row.created_at, reverse=True)
        page = rows[skip : skip + take] if take is not None else rows[skip:]
        if select:
            return [
                _row(
                    **{
                        field_name: getattr(row, field_name, None)
                        for field_name, enabled in select.items()
                        if enabled
                    }
                )
                for row in page
            ]
        return page


class _CompanyDelegate:
    def __init__(self, rows: List[SimpleNamespace]) -> None:
        self.rows = rows

    async def find_many(
        self, *, where: Optional[Dict[str, Any]] = None, **_: Any
    ) -> List[SimpleNamespace]:
        if not where or "OR" in where:
            return []
        if "company_id" in where:
            return [
                row
                for row in self.rows
                if _field_matches(row, "company_id", where["company_id"])
            ]
        if "litellm_organization_id" in where:
            return [
                row
                for row in self.rows
                if _field_matches(
                    row, "litellm_organization_id", where["litellm_organization_id"]
                )
            ]
        return self.rows

    async def find_unique(self, *, where: Dict[str, Any]) -> Optional[SimpleNamespace]:
        company_id = where.get("company_id")
        for row in self.rows:
            if row.company_id == company_id:
                return row
        return None


class _ProjectDelegate:
    def __init__(self, rows: List[SimpleNamespace]) -> None:
        self.rows = rows

    async def find_many(
        self, *, where: Optional[Dict[str, Any]] = None, **_: Any
    ) -> List[SimpleNamespace]:
        if not where or "OR" in where:
            return []
        if "company_id" in where:
            return [
                row
                for row in self.rows
                if _field_matches(row, "company_id", where["company_id"])
            ]
        if "project_id" in where:
            return [
                row
                for row in self.rows
                if _field_matches(row, "project_id", where["project_id"])
            ]
        if "litellm_team_id" in where:
            return [
                row
                for row in self.rows
                if _field_matches(row, "litellm_team_id", where["litellm_team_id"])
            ]
        return self.rows

    async def find_unique(self, *, where: Dict[str, Any]) -> Optional[SimpleNamespace]:
        project_id = where.get("project_id")
        for row in self.rows:
            if row.project_id == project_id:
                return row
        return None


class _SpendLogsDelegate:
    def __init__(
        self,
        count: int,
        rows: Optional[List[SimpleNamespace]] = None,
    ) -> None:
        self.count_value = count
        self.rows = rows or []

    async def count(self, *, where: Dict[str, Any]) -> int:
        if where.get("request_id") == "__cavadalabs_schema_probe__":
            return 0
        return self.count_value

    async def find_many(
        self,
        *,
        take: Optional[int] = None,
        skip: int = 0,
        select: Optional[Dict[str, bool]] = None,
        **_: Any,
    ) -> List[SimpleNamespace]:
        page = self.rows[skip : skip + take] if take is not None else self.rows[skip:]
        if select:
            return [
                _row(
                    **{
                        field_name: getattr(row, field_name, None)
                        for field_name, enabled in select.items()
                        if enabled
                    }
                )
                for row in page
            ]
        return page


class _EmptyDelegate:
    async def find_many(self, **_: Any) -> List[SimpleNamespace]:
        return []

    async def find_unique(self, **_: Any) -> None:
        return None


class _CompanyMemberDelegate:
    def __init__(self, company_id: str, role: str) -> None:
        self.company_id = company_id
        self.role = role

    async def find_many(self, *, where: Dict[str, Any]) -> List[SimpleNamespace]:
        if where.get("user_id") != "user-1":
            return []
        return [_row(company_id=self.company_id, user_id="user-1", role=self.role)]

    async def find_unique(self, *, where: Dict[str, Any]) -> Optional[SimpleNamespace]:
        key = where["company_id_user_id"]
        if key["company_id"] == self.company_id and key["user_id"] == "user-1":
            return _row(company_id=self.company_id, user_id="user-1", role=self.role)
        return None


class _UsageDiagnosticsDb:
    def __init__(
        self,
        *,
        ledger_rows: List[SimpleNamespace],
        spend_log_count: int,
        spend_log_rows: Optional[List[SimpleNamespace]] = None,
        company_member_role: str = "viewer",
    ) -> None:
        self.cavadalabs_requestledgertable = _LedgerDelegate(ledger_rows)
        self.cavadalabs_companytable = _CompanyDelegate(
            [_company(), _company("company-2")]
        )
        self.cavadalabs_projecttable = _ProjectDelegate([_project()])
        self.litellm_spendlogs = _SpendLogsDelegate(spend_log_count, spend_log_rows)
        self.litellm_verificationtoken = _EmptyDelegate()
        self.litellm_deletedverificationtoken = _EmptyDelegate()
        self.cavadalabs_companymembertable = _CompanyMemberDelegate(
            "company-1",
            company_member_role,
        )
        self.cavadalabs_projectmembertable = _EmptyDelegate()
        self.litellm_organizationmembership = _EmptyDelegate()
        self.litellm_usertable = _EmptyDelegate()
        self.litellm_teamtable = _EmptyDelegate()


def _prisma(db: _UsageDiagnosticsDb) -> SimpleNamespace:
    return SimpleNamespace(db=db)


def _internal_user() -> UserAPIKeyAuth:
    return UserAPIKeyAuth(
        user_id="user-1",
        user_role=LitellmUserRoles.INTERNAL_USER,
    )


def _readiness_check(
    checks: List[CavadaLabsUsageReadinessCheck],
    *,
    code: str,
    entity_id: Optional[str] = None,
) -> CavadaLabsUsageReadinessCheck:
    matches = [
        check
        for check in checks
        if check.code == code and (entity_id is None or check.entity_id == entity_id)
    ]
    assert len(matches) == 1
    return matches[0]


@pytest.mark.asyncio
async def test_should_return_live_company_ledger_stats_and_repair_dry_run_status():
    db = _UsageDiagnosticsDb(
        ledger_rows=[
            _ledger(
                request_id="req-1",
                spend=0.25,
                created_at=datetime(2026, 5, 15, 9, tzinfo=UTC),
            ),
            _ledger(
                request_id="req-2",
                spend=0.75,
                created_at=datetime(2026, 5, 16, 18, tzinfo=UTC),
            ),
        ],
        spend_log_count=3,
    )

    response = await get_cavadalabs_usage_diagnostics(
        prisma_client=_prisma(db),
        entity_type="company",
        entity_id=["company-1"],
        start_date="2026-05-15",
        end_date="2026-05-16",
        timezone_offset_minutes=0,
    )

    item = response.diagnostics[0]
    assert response.ledger_table_available is True
    assert response.spend_logs_table_available is True
    assert response.key_context_available is True
    assert (
        _readiness_check(response.readiness_checks, code="usage_schema").status
        == CavadaLabsUsageReadinessCheckStatus.READY
    )
    assert item.status == CavadaLabsUsageDiagnosticsStatus.SCOPED_BACKFILL_AVAILABLE
    assert item.ledger_rows == 2
    assert item.ledger_total_spend == pytest.approx(1.0)
    assert item.ledger_min_created_at == datetime(2026, 5, 15, 9, tzinfo=UTC)
    assert item.ledger_max_created_at == datetime(2026, 5, 16, 18, tzinfo=UTC)
    assert item.attributable_spend_logs == 3
    assert item.repair_dry_run.attempted is True
    assert item.repair_dry_run.available is True
    assert item.repair_dry_run.would_repair is True
    assert item.repair_dry_run.scoped_spend_logs == 3
    assert item.repair_dry_run.missing_ledger_rows == 1
    assert (
        _readiness_check(
            response.readiness_checks,
            code="repair_status",
            entity_id="company-1",
        ).status
        == CavadaLabsUsageReadinessCheckStatus.ACTION_REQUIRED
    )
    assert any("migrate status" in command for command in response.operator_commands)
    assert any(
        "usage/repair" in command and "dry_run" in command
        for command in response.operator_commands
    )
    commands_blob = "\n".join(response.operator_commands)
    assert "company-1" not in commands_blob
    assert "2026-05-15" not in commands_blob
    assert "REPLACE_WITH_COMPANY_ID" in commands_blob
    assert ":'entity_id'" in commands_blob
    assert '-v entity_id="${CAVADALABS_COMPANY_ID}"' in commands_blob
    assert 'entity_id="CAVADALABS_COMPANY_ID"' not in commands_blob
    assert "--data-urlencode" in commands_blob
    assert '--data-urlencode "company_ids=${CAVADALABS_COMPANY_ID}"' in commands_blob
    assert "company_ids=CAVADALABS_COMPANY_ID" not in commands_blob


@pytest.mark.asyncio
async def test_should_return_live_project_ledger_stats_without_organization_scope():
    db = _UsageDiagnosticsDb(
        ledger_rows=[
            _ledger(
                request_id="req-project",
                spend=0.4,
                created_at=datetime(2026, 5, 16, 12, tzinfo=UTC),
            )
        ],
        spend_log_count=1,
    )

    response = await get_cavadalabs_usage_diagnostics(
        prisma_client=_prisma(db),
        entity_type="project",
        entity_id=["project-1"],
        start_date="2026-05-16",
        end_date="2026-05-16",
        timezone_offset_minutes=0,
    )

    item = response.diagnostics[0]
    assert item.status == CavadaLabsUsageDiagnosticsStatus.VISIBLE
    assert item.ledger_rows == 1
    assert item.ledger_total_spend == pytest.approx(0.4)
    assert (
        _readiness_check(
            response.readiness_checks,
            code="ledger_rows",
            entity_id="project-1",
        ).status
        == CavadaLabsUsageReadinessCheckStatus.READY
    )
    assert (
        _readiness_check(
            response.readiness_checks,
            code="repair_status",
            entity_id="project-1",
        ).status
        == CavadaLabsUsageReadinessCheckStatus.READY
    )
    stats_call = db.cavadalabs_requestledgertable.find_many_calls[-1]
    assert stats_call["where"]["project_id"] == "project-1"
    assert "organization_id" not in stats_call["where"]
    assert "team_id" not in stats_call["where"]


@pytest.mark.asyncio
async def test_should_report_project_spend_logs_with_conflicting_company_metadata():
    db = _UsageDiagnosticsDb(
        ledger_rows=[],
        spend_log_count=1,
        spend_log_rows=[
            _spend_log(
                metadata={
                    "cavadalabs_company_id": "company-2",
                    "cavadalabs_project_id": "project-1",
                }
            )
        ],
    )

    response = await get_cavadalabs_usage_diagnostics(
        prisma_client=_prisma(db),
        entity_type="project",
        entity_id=["project-1"],
        start_date="2026-05-16",
        end_date="2026-05-16",
        timezone_offset_minutes=0,
    )

    item = response.diagnostics[0]
    spendlogs_check = _readiness_check(
        response.readiness_checks,
        code="spendlogs_attribution",
        entity_id="project-1",
    )
    repair_check = _readiness_check(
        response.readiness_checks,
        code="repair_status",
        entity_id="project-1",
    )

    assert item.status == CavadaLabsUsageDiagnosticsStatus.MISSING_COMPATIBILITY_MAPPING
    assert item.ledger_rows == 0
    assert item.attributable_spend_logs == 0
    assert item.metadata_spend_logs == 0
    assert item.unmapped_spend_logs == 1
    assert item.scoped_backfill_available is False
    assert item.repair_dry_run.available is False
    assert item.repair_dry_run.scoped_spend_logs == 0
    assert item.missing_mappings == [
        "SpendLogs metadata with CavadaLabs project_id uses a different "
        "CavadaLabs company_id"
    ]
    assert spendlogs_check.status == CavadaLabsUsageReadinessCheckStatus.ACTION_REQUIRED
    assert repair_check.status == CavadaLabsUsageReadinessCheckStatus.ACTION_REQUIRED


@pytest.mark.asyncio
async def test_should_return_actionable_checks_when_usage_schema_is_missing():
    response = await get_cavadalabs_usage_diagnostics(
        prisma_client=SimpleNamespace(db=SimpleNamespace()),
        entity_type="company",
        entity_id=["company-1"],
        start_date="2026-05-15",
        end_date="2026-05-16",
        timezone_offset_minutes=0,
    )

    schema_check = _readiness_check(response.readiness_checks, code="usage_schema")
    ledger_check = _readiness_check(
        response.readiness_checks,
        code="ledger_rows",
        entity_id="company-1",
    )

    assert schema_check.status == CavadaLabsUsageReadinessCheckStatus.BLOCKED
    assert schema_check.recommended_action == "run_migration_backfill"
    assert response.missing_schema
    assert ledger_check.status == CavadaLabsUsageReadinessCheckStatus.BLOCKED
    assert ledger_check.details["missing_schema"] == response.missing_schema
    assert any("migrate deploy" in command for command in response.operator_commands)


@pytest.mark.asyncio
async def test_should_distinguish_empty_ledger_from_repairable_spend_logs():
    db = _UsageDiagnosticsDb(ledger_rows=[], spend_log_count=0)

    response = await get_cavadalabs_usage_diagnostics(
        prisma_client=_prisma(db),
        entity_type="company",
        entity_id=["company-1"],
        start_date="2026-05-15",
        end_date="2026-05-16",
        timezone_offset_minutes=0,
    )

    item = response.diagnostics[0]
    ledger_check = _readiness_check(
        response.readiness_checks,
        code="ledger_rows",
        entity_id="company-1",
    )
    spendlogs_check = _readiness_check(
        response.readiness_checks,
        code="spendlogs_attribution",
        entity_id="company-1",
    )
    repair_check = _readiness_check(
        response.readiness_checks,
        code="repair_status",
        entity_id="company-1",
    )

    assert item.status == CavadaLabsUsageDiagnosticsStatus.NO_ATTRIBUTABLE_SPEND
    assert ledger_check.status == CavadaLabsUsageReadinessCheckStatus.WARNING
    assert spendlogs_check.status == CavadaLabsUsageReadinessCheckStatus.WARNING
    assert repair_check.status == CavadaLabsUsageReadinessCheckStatus.READY
    assert repair_check.recommended_action == "none"


@pytest.mark.asyncio
async def test_should_reject_cross_company_live_diagnostics_before_ledger_read(
    monkeypatch,
):
    db = _UsageDiagnosticsDb(ledger_rows=[], spend_log_count=0)
    monkeypatch.setattr(proxy_server, "prisma_client", _prisma(db))

    with pytest.raises(HTTPException) as exc_info:
        await company_endpoints.get_company_usage_diagnostics(
            http_request=object(),
            start_date="2026-05-15",
            end_date="2026-05-16",
            company_ids="company-2",
            model=None,
            provider=None,
            api_key=None,
            timezone=0,
            user_api_key_dict=_internal_user(),
        )

    assert exc_info.value.status_code == 403
    assert db.cavadalabs_requestledgertable.count_calls == 0
