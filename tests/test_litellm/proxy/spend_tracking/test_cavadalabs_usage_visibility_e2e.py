from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from litellm.proxy.cavadalabs.usage import get_cavadalabs_daily_activity


UTC = timezone.utc


@dataclass
class _FakeDelegate:
    rows: List[Any] = field(default_factory=list)
    calls: List[tuple[str, Dict[str, Any]]] = field(default_factory=list)

    async def find_many(self, **kwargs):
        self.calls.append(("find_many", kwargs))
        rows = [row for row in self.rows if _matches_where(row, kwargs.get("where"))]
        rows = _apply_order(rows, kwargs.get("order"))
        skip = int(kwargs.get("skip") or 0)
        take = kwargs.get("take")
        if take is None:
            return rows[skip:]
        return rows[skip : skip + int(take)]

    async def count(self, **kwargs) -> int:
        self.calls.append(("count", kwargs))
        return len(
            [row for row in self.rows if _matches_where(row, kwargs.get("where"))]
        )


class _FakeLedgerDelegate(_FakeDelegate):
    async def create_many(self, **kwargs):
        self.calls.append(("create_many", kwargs))
        created = 0
        skip_duplicates = bool(kwargs.get("skip_duplicates"))
        existing_request_ids = {_row_value(row, "request_id") for row in self.rows}
        for item in kwargs.get("data") or []:
            request_id = item.get("request_id")
            if skip_duplicates and request_id in existing_request_ids:
                continue
            self.rows.append(SimpleNamespace(**item))
            existing_request_ids.add(request_id)
            created += 1
        return SimpleNamespace(count=created)

    async def update_many(self, **kwargs):
        self.calls.append(("update_many", kwargs))
        updated = 0
        data = kwargs.get("data") or {}
        for row in self.rows:
            if not _matches_where(row, kwargs.get("where")):
                continue
            for key, value in data.items():
                setattr(row, key, value)
            updated += 1
        return SimpleNamespace(count=updated)


@dataclass
class _FakeDb:
    companies: List[Any]
    projects: List[Any]
    keys: List[Any]
    spend_logs: List[Any]
    deleted_keys: Optional[List[Any]] = None

    def __post_init__(self) -> None:
        self.cavadalabs_companytable = _FakeDelegate(self.companies)
        self.cavadalabs_projecttable = _FakeDelegate(self.projects)
        self.litellm_verificationtoken = _FakeDelegate(self.keys)
        self.litellm_deletedverificationtoken = _FakeDelegate(self.deleted_keys or [])
        self.litellm_spendlogs = _FakeDelegate(self.spend_logs)
        self.cavadalabs_requestledgertable = _FakeLedgerDelegate([])


def _company(company_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        company_id=company_id,
        legal_name=f"Company {company_id}",
        litellm_organization_id=f"org-{company_id}",
        status="active",
    )


def _project(project_id: str, company_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        project_id=project_id,
        company_id=company_id,
        name=f"Project {project_id}",
        litellm_team_id=f"team-{project_id}",
        status="production",
    )


def _server_key(
    *,
    token: str = "hashed-key",
    company_id: str = "company-1",
    project_id: str = "project-1",
    metadata: Optional[Dict[str, Any]] = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        token=token,
        key_alias=f"Key {token}",
        team_id=None,
        organization_id=None,
        metadata=metadata
        or {
            "cavadalabs": {"cavadalabs_company_id": company_id},
            "spend_logs_metadata": {
                "project_id": project_id,
                "cavadalabs_chatbot_id": "chatbot-1",
            },
        },
    )


def _spend_log(
    *,
    request_id: str,
    api_key: str = "hashed-key",
    metadata: Optional[Dict[str, Any]] = None,
    spend: float = 0.42,
) -> SimpleNamespace:
    return SimpleNamespace(
        request_id=request_id,
        call_type="acompletion",
        api_key=api_key,
        spend=spend,
        total_tokens=30,
        prompt_tokens=18,
        completion_tokens=12,
        startTime=datetime(2026, 5, 16, 12, tzinfo=UTC),
        endTime=datetime(2026, 5, 16, 12, 0, 1, tzinfo=UTC),
        model="openai/gpt-4.1",
        model_group="gpt-4.1",
        custom_llm_provider="openai",
        metadata=metadata or {},
        team_id=None,
        organization_id=None,
        session_id=None,
        status="success",
        request_tags=[],
    )


def _db_for_visibility(
    *,
    keys: Optional[List[Any]] = None,
    spend_logs: Optional[List[Any]] = None,
) -> _FakeDb:
    return _FakeDb(
        companies=[_company("company-1"), _company("company-2")],
        projects=[
            _project("project-1", "company-1"),
            _project("project-2", "company-2"),
        ],
        keys=keys or [_server_key()],
        spend_logs=spend_logs or [],
    )


async def _daily_activity(
    db: _FakeDb,
    *,
    entity_id_field: str,
    entity_id: str,
):
    return await get_cavadalabs_daily_activity(
        prisma_client=SimpleNamespace(db=db),
        entity_id_field=entity_id_field,
        entity_id=[entity_id],
        start_date="2026-05-16",
        end_date="2026-05-16",
        model=None,
        api_key=None,
        page=1,
        page_size=50,
        timezone_offset_minutes=0,
    )


@pytest.mark.asyncio
async def test_should_repair_missing_company_usage_from_server_key_alias_metadata():
    db = _db_for_visibility(
        spend_logs=[_spend_log(request_id="req-company-key-alias", spend=0.42)]
    )

    response = await _daily_activity(
        db,
        entity_id_field="company_id",
        entity_id="company-1",
    )

    assert response.metadata.total_spend == pytest.approx(0.42)
    assert response.metadata.total_api_requests == 1
    ledger_row = db.cavadalabs_requestledgertable.rows[0]
    assert ledger_row.request_id == "req-company-key-alias"
    assert ledger_row.company_id == "company-1"
    assert ledger_row.project_id == "project-1"
    assert ledger_row.chatbot_id == "chatbot-1"
    assert ledger_row.api_key_hash == "hashed-key"


@pytest.mark.asyncio
async def test_should_repair_missing_project_usage_from_server_key_alias_metadata():
    db = _db_for_visibility(
        spend_logs=[_spend_log(request_id="req-project-key-alias", spend=0.31)]
    )

    response = await _daily_activity(
        db,
        entity_id_field="project_id",
        entity_id="project-1",
    )

    assert response.metadata.total_spend == pytest.approx(0.31)
    assert response.results[0].breakdown.entities["project-1"].metrics.api_requests == 1
    ledger_row = db.cavadalabs_requestledgertable.rows[0]
    assert ledger_row.company_id == "company-1"
    assert ledger_row.project_id == "project-1"


@pytest.mark.asyncio
async def test_should_use_server_key_context_over_conflicting_spend_log_metadata():
    db = _db_for_visibility(
        spend_logs=[
            _spend_log(
                request_id="req-conflicting-client-metadata",
                metadata={
                    "cavadalabs_company_id": "company-2",
                    "cavadalabs_project_id": "project-1",
                },
                spend=0.55,
            )
        ]
    )

    response = await _daily_activity(
        db,
        entity_id_field="company_id",
        entity_id="company-1",
    )

    assert response.metadata.total_spend == pytest.approx(0.55)
    ledger_row = db.cavadalabs_requestledgertable.rows[0]
    assert ledger_row.company_id == "company-1"
    assert ledger_row.project_id == "project-1"
    assert (
        ledger_row.metadata.data["cavadalabs"]["attribution_source"] == "key_metadata"
    )


@pytest.mark.asyncio
async def test_should_not_leak_server_key_usage_to_another_company_scope():
    db = _db_for_visibility(
        spend_logs=[_spend_log(request_id="req-company-leak-check", spend=0.77)]
    )

    response = await _daily_activity(
        db,
        entity_id_field="company_id",
        entity_id="company-2",
    )

    assert response.metadata.total_spend == 0
    assert response.metadata.total_api_requests == 0
    assert db.cavadalabs_requestledgertable.rows == []


def _matches_where(row: Any, where: Optional[Dict[str, Any]]) -> bool:
    if not where:
        return True
    for key, expected in where.items():
        if key == "AND":
            if not all(_matches_where(row, item) for item in expected):
                return False
            continue
        if key == "OR":
            if not any(_matches_where(row, item) for item in expected):
                return False
            continue
        if key == "metadata" and isinstance(expected, dict):
            if not _matches_metadata_path(row, expected):
                return False
            continue
        if not _matches_field(_row_value(row, key), expected):
            return False
    return True


def _matches_metadata_path(row: Any, expected: Dict[str, Any]) -> bool:
    metadata = _normalize_metadata(_row_value(row, "metadata"))
    path = expected.get("path")
    if not isinstance(path, list):
        return False
    value: Any = metadata
    for part in path:
        value = _normalize_metadata(value).get(part)
    return value == expected.get("equals")


def _matches_field(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        if "in" in expected:
            return actual in expected["in"]
        if "not" in expected:
            return actual != expected["not"]
        if "gte" in expected and actual < expected["gte"]:
            return False
        if "lt" in expected and actual >= expected["lt"]:
            return False
        if "lte" in expected and actual > expected["lte"]:
            return False
        return True
    return actual == expected


def _apply_order(rows: List[Any], order: Any) -> List[Any]:
    ordered = list(rows)
    for item in reversed(list(order or [])):
        if not isinstance(item, dict):
            continue
        for field_name, direction in item.items():
            ordered.sort(
                key=lambda row, name=field_name: _row_value(row, name),
                reverse=direction == "desc",
            )
    return ordered


def _normalize_metadata(value: Any) -> Dict[str, Any]:
    data = getattr(value, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(value, dict):
        return value
    return {}


def _row_value(row: Any, field_name: str) -> Any:
    if isinstance(row, dict):
        return row.get(field_name)
    return getattr(row, field_name, None)
