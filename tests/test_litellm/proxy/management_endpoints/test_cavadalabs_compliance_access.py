from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Iterable

import pytest
from fastapi import HTTPException

from litellm.proxy import proxy_server
from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.cavadalabs.compliance import CavadaLabsComplianceService
from litellm.proxy.management_endpoints.cavadalabs_compliance_endpoints import (
    _require_compliance_scope_access,
    _resolve_compliance_list_filters,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _row(**kwargs: Any) -> SimpleNamespace:
    return SimpleNamespace(**kwargs)


def _company(company_id: str) -> SimpleNamespace:
    return _row(
        company_id=company_id,
        legal_name=f"{company_id} Legal",
        billing_name=None,
        vat_tax_id=None,
        billing_address={},
        admin_emails=[],
        plan="production",
        status="active",
        monthly_budget=None,
        metadata={},
        retention_policy={},
        default_guardrail_policy=None,
        default_billing_settings={},
        litellm_organization_id=None,
        created_at=_now(),
        created_by="system",
        updated_at=_now(),
        updated_by="system",
    )


def _project(project_id: str, company_id: str) -> SimpleNamespace:
    return _row(
        project_id=project_id,
        company_id=company_id,
        name=f"{project_id} Name",
        status="production",
        allowed_models=[],
        allowed_rag_collections=[],
        default_chatbot_settings={},
        default_guardrail_policy=None,
        budget=None,
        retention_policy_override={},
        metadata={},
        litellm_team_id=None,
        created_at=_now(),
        created_by="system",
        updated_at=_now(),
        updated_by="system",
    )


def _document(document_id: str, company_id: str, project_id: str | None) -> SimpleNamespace:
    return _row(
        document_id=document_id,
        company_id=company_id,
        project_id=project_id,
        chatbot_id=None,
        collection_id=None,
        framework="gdpr",
        document_type="dpia",
        title=f"{document_id} Title",
        version=1,
        status="draft",
        locale="en",
        content="",
        content_format="markdown",
        checksum="checksum",
        generated_from={},
        metadata={},
        approved_by=None,
        approved_at=None,
        published_at=None,
        valid_from=None,
        valid_until=None,
        created_at=_now(),
        created_by="system",
        updated_at=_now(),
        updated_by="system",
    )


def _user(user_id: str) -> UserAPIKeyAuth:
    return UserAPIKeyAuth(
        api_key=f"sk-{user_id}",
        user_id=user_id,
        user_role=LitellmUserRoles.INTERNAL_USER,
    )


def _matches(row: SimpleNamespace, where: dict[str, Any] | None) -> bool:
    if not where:
        return True
    for key, expected in where.items():
        if key == "OR":
            if not any(_matches(row, item) for item in expected):
                return False
            continue
        actual = getattr(row, key, None)
        if isinstance(expected, dict) and "in" in expected:
            if actual not in expected["in"]:
                return False
        elif actual != expected:
            return False
    return True


class _Table:
    def __init__(self, rows: Iterable[SimpleNamespace], unique_key: str | None = None):
        self.rows = list(rows)
        self.unique_key = unique_key
        self.find_many_calls: list[dict[str, Any] | None] = []

    async def find_unique(self, *, where: dict[str, Any]) -> SimpleNamespace | None:
        if self.unique_key is not None and self.unique_key in where:
            expected = where[self.unique_key]
            return next(
                (row for row in self.rows if getattr(row, self.unique_key, None) == expected),
                None,
            )
        if where:
            _, composite = next(iter(where.items()))
            if isinstance(composite, dict):
                return next((row for row in self.rows if _matches(row, composite)), None)
        return None

    async def find_many(self, *, where: dict[str, Any] | None = None, **_: Any) -> list[SimpleNamespace]:
        self.find_many_calls.append(where)
        return [row for row in self.rows if _matches(row, where)]


class _UserTable:
    async def find_unique(self, *, where: dict[str, Any]) -> SimpleNamespace:
        return _row(user_id=where.get("user_id"), teams=[])


class _FakeDB:
    def __init__(self) -> None:
        self.cavadalabs_companytable = _Table(
            [_company("company-1"), _company("company-2")],
            unique_key="company_id",
        )
        self.cavadalabs_projecttable = _Table(
            [
                _project("project-1", "company-1"),
                _project("project-2", "company-1"),
                _project("project-3", "company-2"),
            ],
            unique_key="project_id",
        )
        self.cavadalabs_companymembertable = _Table(
            [
                _row(company_id="company-1", user_id="company-admin", role="company_admin"),
                _row(company_id="company-1", user_id="company-viewer", role="viewer"),
            ]
        )
        self.cavadalabs_projectmembertable = _Table(
            [
                _row(project_id="project-1", user_id="project-admin", role="project_admin"),
                _row(project_id="project-1", user_id="project-viewer", role="viewer"),
                _row(project_id="project-3", user_id="other-project-viewer", role="viewer"),
            ]
        )
        self.litellm_organizationmembership = _Table([])
        self.litellm_usertable = _UserTable()
        self.litellm_teamtable = _Table([], unique_key="team_id")
        self.cavadalabs_compliancedocumenttable = _Table(
            [
                _document("company-doc", "company-1", None),
                _document("project-doc", "company-1", "project-1"),
                _document("other-doc", "company-2", "project-3"),
            ],
            unique_key="document_id",
        )


@pytest.fixture
def fake_prisma(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    prisma = SimpleNamespace(db=_FakeDB())
    monkeypatch.setattr(proxy_server, "prisma_client", prisma)
    return prisma


@pytest.mark.asyncio
async def test_should_allow_company_viewer_to_read_company_scope_and_deny_mutation(fake_prisma: SimpleNamespace):
    await _require_compliance_scope_access(
        company_id="company-1",
        project_id=None,
        user_api_key_dict=_user("company-viewer"),
        require_admin=False,
    )

    with pytest.raises(HTTPException) as exc:
        await _require_compliance_scope_access(
            company_id="company-1",
            project_id=None,
            user_api_key_dict=_user("company-viewer"),
            require_admin=True,
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_should_allow_project_admin_to_manage_only_project_scope(fake_prisma: SimpleNamespace):
    await _require_compliance_scope_access(
        company_id="company-1",
        project_id="project-1",
        user_api_key_dict=_user("project-admin"),
        require_admin=True,
    )

    with pytest.raises(HTTPException) as exc:
        await _require_compliance_scope_access(
            company_id="company-1",
            project_id=None,
            user_api_key_dict=_user("project-admin"),
            require_admin=True,
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_should_reject_compliance_scope_when_project_belongs_to_other_company(fake_prisma: SimpleNamespace):
    with pytest.raises(HTTPException) as exc:
        await _require_compliance_scope_access(
            company_id="company-1",
            project_id="project-3",
            user_api_key_dict=_user("other-project-viewer"),
            require_admin=False,
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_should_scope_company_filter_to_visible_projects_for_project_member(fake_prisma: SimpleNamespace):
    scoped_filters = await _resolve_compliance_list_filters(
        company_id="company-1",
        project_id=None,
        user_api_key_dict=_user("project-viewer"),
    )

    assert scoped_filters == (None, None, None, ["project-1"])


@pytest.mark.asyncio
async def test_should_apply_compliance_list_filters_for_company_and_project_members(fake_prisma: SimpleNamespace):
    service = CavadaLabsComplianceService(fake_prisma)

    rows = await service.list_documents(
        company_ids=["company-1"],
        project_ids=["project-3"],
    )

    assert [row.document_id for row in rows] == [
        "company-doc",
        "project-doc",
        "other-doc",
    ]
    assert fake_prisma.db.cavadalabs_compliancedocumenttable.find_many_calls[-1] == {
        "OR": [
            {"company_id": {"in": ["company-1"]}},
            {"project_id": {"in": ["project-3"]}},
        ]
    }
