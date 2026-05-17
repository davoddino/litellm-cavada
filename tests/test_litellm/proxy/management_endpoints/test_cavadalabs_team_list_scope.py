from types import SimpleNamespace

import pytest
from fastapi import Request

from litellm.proxy import proxy_server
from litellm.proxy._types import LiteLLM_TeamTable, LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.management_endpoints import team_endpoints


class _AsyncDelegate:
    def __init__(self, *, find_many_results=None, count_result=0):
        self.find_many_results = list(find_many_results or [])
        self.count_result = count_result
        self.find_many_calls = []
        self.count_calls = []

    async def find_many(self, **kwargs):
        self.find_many_calls.append(kwargs)
        if self.find_many_results:
            return self.find_many_results.pop(0)
        return []

    async def count(self, **kwargs):
        self.count_calls.append(kwargs)
        return self.count_result


@pytest.mark.asyncio
async def test_list_team_v2_auto_scopes_native_cavadalabs_project_membership_without_legacy_team(
    monkeypatch,
):
    scoped_team = LiteLLM_TeamTable(
        team_id="team-project-1",
        team_alias="Compatibility Team",
        organization_id="org-company-1",
        members_with_roles=[],
    )
    project_row = SimpleNamespace(
        litellm_team_id="team-project-1",
        project_id="project-1",
        company_id="company-1",
        name="Dispatch Project",
        status="production",
    )
    team_delegate = _AsyncDelegate(find_many_results=[[scoped_team]], count_result=1)
    project_delegate = _AsyncDelegate(find_many_results=[[project_row], [project_row]])
    prisma_client = SimpleNamespace(
        db=SimpleNamespace(
            litellm_teamtable=team_delegate,
            cavadalabs_projecttable=project_delegate,
        )
    )

    async def _visible_project_ids_for_user(
        _db, _user_api_key_dict, *, company_id=None
    ):
        assert company_id is None
        return {"project-1"}

    async def _legacy_user_lookup_should_not_run(*_args, **_kwargs):
        raise AssertionError(
            "Native CavadaLabs team scope should not require legacy Team or Organization membership"
        )

    monkeypatch.setattr(proxy_server, "prisma_client", prisma_client)
    monkeypatch.setattr(proxy_server, "user_api_key_cache", object())
    monkeypatch.setattr(proxy_server, "proxy_logging_obj", object())
    monkeypatch.setattr(
        team_endpoints,
        "visible_project_ids_for_user",
        _visible_project_ids_for_user,
    )
    monkeypatch.setattr(
        team_endpoints,
        "get_user_object",
        _legacy_user_lookup_should_not_run,
    )

    response = await team_endpoints.list_team_v2(
        http_request=Request(scope={"type": "http", "path": "/v2/team/list"}),
        user_id=None,
        organization_id=None,
        team_id=None,
        team_alias=None,
        search=None,
        page=1,
        page_size=10,
        sort_by=None,
        sort_order="asc",
        status=None,
        cavadalabs_company_id=None,
        cavadalabs_project_id=None,
        user_api_key_dict=UserAPIKeyAuth(
            user_id="project-viewer",
            user_role=LitellmUserRoles.INTERNAL_USER,
        ),
    )

    assert response["total"] == 1
    assert team_delegate.find_many_calls[0]["where"] == {
        "team_id": {"in": ["team-project-1"]}
    }
    team = response["teams"][0]
    assert team.team_id == "team-project-1"
    assert team.cavadalabs_company_id == "company-1"
    assert team.cavadalabs_project_id == "project-1"
    assert project_delegate.find_many_calls == [
        {"where": {"project_id": {"in": ["project-1"]}}},
        {"where": {"litellm_team_id": {"in": ["team-project-1"]}}},
    ]
