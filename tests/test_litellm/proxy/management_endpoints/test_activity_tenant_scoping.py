"""
VERIA-43 regression tests:

- /team/daily/activity must require admin/permission on EVERY requested
  team for the unfiltered "full team view" path. The earlier code set a
  global flag if the caller was admin of any one of the requested teams.
- /agent/daily/activity must scope non-admin callers to the agents they
  may actually see, instead of returning the entire proxy's agent rows.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth


# ---------------------------------------------------------------------------
# /team/daily/activity — per-team admin/permission requirement
# ---------------------------------------------------------------------------


def _make_team(team_id: str, admin_user_ids: list):
    """Build a Prisma-compatible team row. `admin_user_ids` are inserted as
    `members_with_roles[*].role == "admin"` because that's what
    `_is_user_team_admin` checks."""
    members_with_roles = [{"user_id": uid, "role": "admin"} for uid in admin_user_ids]
    row = MagicMock()
    row.team_id = team_id
    row.team_alias = team_id
    row.admins = admin_user_ids
    row.members_with_roles = members_with_roles
    row.model_dump = MagicMock(
        return_value={
            "team_id": team_id,
            "team_alias": team_id,
            "admins": admin_user_ids,
            "members_with_roles": members_with_roles,
            "members": [],
        }
    )
    return row


@pytest.mark.asyncio
async def test_team_activity_requires_admin_on_every_requested_team():
    """If the caller is admin of one team but only a member of another in
    the same request, the response MUST be filtered down to their own
    keys — the previous code returned a full breakdown."""
    from litellm.proxy.management_endpoints import team_endpoints

    user = UserAPIKeyAuth(
        user_id="alice",
        user_role=LitellmUserRoles.INTERNAL_USER.value,
    )

    # Mock prisma client
    prisma = MagicMock()
    prisma.db.litellm_teamtable.find_many = AsyncMock(
        return_value=[
            _make_team("team-A", admin_user_ids=["alice"]),
            _make_team("team-B", admin_user_ids=["bob"]),
        ]
    )
    user_keys = MagicMock(token="alice-key-1")
    prisma.db.litellm_verificationtoken.find_many = AsyncMock(return_value=[user_keys])

    # Mock get_user_object so the non-admin branch passes
    user_info = MagicMock()
    user_info.teams = ["team-A", "team-B"]

    captured = {}

    async def _fake_get_daily_activity(**kwargs):
        captured.update(kwargs)
        return MagicMock()

    with (
        patch.object(team_endpoints, "prisma_client", prisma, create=True),
        patch(
            "litellm.proxy.management_endpoints.team_endpoints.get_user_object",
            new=AsyncMock(return_value=user_info),
        ),
        patch(
            "litellm.proxy.management_endpoints.team_endpoints.get_daily_activity",
            new=AsyncMock(side_effect=_fake_get_daily_activity),
        ),
        patch("litellm.proxy.proxy_server.prisma_client", prisma),
        patch("litellm.proxy.proxy_server.user_api_key_cache", MagicMock()),
        patch("litellm.proxy.proxy_server.proxy_logging_obj", MagicMock()),
    ):
        await team_endpoints.get_team_daily_activity(
            team_ids="team-A,team-B",
            start_date="2026-01-01",
            end_date="2026-01-02",
            user_api_key_dict=user,
        )

    # Caller is only admin of team-A; team-B forces fallback to user-key
    # filtering for the entire request.
    assert captured["api_key"] == ["alice-key-1"]


@pytest.mark.asyncio
async def test_team_activity_full_view_when_admin_of_all_requested_teams():
    """When the caller is admin of *every* team requested, no api_key
    filter is forced — they're allowed the unfiltered breakdown."""
    from litellm.proxy.management_endpoints import team_endpoints

    user = UserAPIKeyAuth(
        user_id="alice",
        user_role=LitellmUserRoles.INTERNAL_USER.value,
    )

    prisma = MagicMock()
    prisma.db.litellm_teamtable.find_many = AsyncMock(
        return_value=[
            _make_team("team-A", admin_user_ids=["alice"]),
            _make_team("team-B", admin_user_ids=["alice"]),
        ]
    )

    user_info = MagicMock()
    user_info.teams = ["team-A", "team-B"]

    captured = {}

    async def _fake_get_daily_activity(**kwargs):
        captured.update(kwargs)
        return MagicMock()

    with (
        patch.object(team_endpoints, "prisma_client", prisma, create=True),
        patch(
            "litellm.proxy.management_endpoints.team_endpoints.get_user_object",
            new=AsyncMock(return_value=user_info),
        ),
        patch(
            "litellm.proxy.management_endpoints.team_endpoints.get_daily_activity",
            new=AsyncMock(side_effect=_fake_get_daily_activity),
        ),
        patch("litellm.proxy.proxy_server.prisma_client", prisma),
        patch("litellm.proxy.proxy_server.user_api_key_cache", MagicMock()),
        patch("litellm.proxy.proxy_server.proxy_logging_obj", MagicMock()),
    ):
        await team_endpoints.get_team_daily_activity(
            team_ids="team-A,team-B",
            start_date="2026-01-01",
            end_date="2026-01-02",
            user_api_key_dict=user,
        )

    assert captured["api_key"] is None


# ---------------------------------------------------------------------------
# /agent/daily/activity — non-admin tenant scoping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_activity_admin_unscoped():
    """Proxy admin: agent_ids omitted → no scoping (existing behavior)."""
    from litellm.proxy.agent_endpoints import endpoints

    admin = UserAPIKeyAuth(user_id="root", user_role=LitellmUserRoles.PROXY_ADMIN.value)

    prisma = MagicMock()
    prisma.db.litellm_agentstable.find_many = AsyncMock(return_value=[])

    captured = {}

    async def _fake_get_daily_activity(**kwargs):
        captured.update(kwargs)
        return MagicMock()

    with (
        patch.object(endpoints, "prisma_client", prisma, create=True),
        patch("litellm.proxy.proxy_server.prisma_client", prisma),
        patch(
            "litellm.proxy.agent_endpoints.endpoints.check_feature_access_for_user",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "litellm.proxy.agent_endpoints.endpoints.get_daily_activity",
            new=AsyncMock(side_effect=_fake_get_daily_activity),
        ),
    ):
        await endpoints.get_agent_daily_activity(
            agent_ids=None,
            start_date="2026-01-01",
            end_date="2026-01-02",
            user_api_key_dict=admin,
        )

    assert captured["entity_id"] is None  # no agent_id scoping for admin


# ---------------------------------------------------------------------------
# /project/daily/activity — Company/Project product filters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_project_activity_accepts_project_id_and_company_id_filters():
    from enterprise.litellm_enterprise.proxy.management_endpoints import (
        project_endpoints,
    )

    admin = UserAPIKeyAuth(user_id="root", user_role=LitellmUserRoles.PROXY_ADMIN.value)

    team = MagicMock()
    team.team_id = "team-company"
    team.organization_id = "company-1"

    project = MagicMock()
    project.project_id = "project-1"
    project.project_alias = "Project 1"
    project.company_id = "company-1"
    project.team_id = "team-company"
    project.litellm_team_table = team

    prisma = MagicMock()
    prisma.db.litellm_teamtable.find_many = AsyncMock(return_value=[team])
    prisma.db.litellm_projecttable.find_many = AsyncMock(return_value=[project])

    captured = {}

    async def _fake_get_daily_activity(**kwargs):
        captured.update(kwargs)
        return MagicMock()

    with (
        patch("litellm.proxy.proxy_server.prisma_client", prisma),
        patch(
            "enterprise.litellm_enterprise.proxy.management_endpoints.project_endpoints.get_daily_activity",
            new=AsyncMock(side_effect=_fake_get_daily_activity),
        ),
    ):
        await project_endpoints.get_project_daily_activity(
            project_id="project-1",
            company_id="company-1",
            start_date="2026-01-01",
            end_date="2026-01-02",
            api_key="runtime-key-hash",
            user_api_key_dict=admin,
        )

    project_where = prisma.db.litellm_projecttable.find_many.call_args.kwargs["where"]
    assert project_where["project_id"] == {"in": ["project-1"]}
    assert project_where["team_id"] == {"in": ["team-company"]}
    assert captured["table_name"] == "litellm_dailyprojectspend"
    assert captured["entity_id_field"] == "project_id"
    assert captured["entity_id"] == ["project-1"]
    assert captured["api_key"] == "runtime-key-hash"


@pytest.mark.asyncio
async def test_project_activity_rejects_conflicting_project_aliases():
    from enterprise.litellm_enterprise.proxy.management_endpoints import (
        project_endpoints,
    )

    admin = UserAPIKeyAuth(user_id="root", user_role=LitellmUserRoles.PROXY_ADMIN.value)
    prisma = MagicMock()

    with patch("litellm.proxy.proxy_server.prisma_client", prisma):
        with pytest.raises(Exception) as exc_info:
            await project_endpoints.get_project_daily_activity(
                project_id="project-1",
                project_ids="project-2",
                start_date="2026-01-01",
                end_date="2026-01-02",
                user_api_key_dict=admin,
            )

    assert getattr(exc_info.value, "status_code", None) == 400
    assert "project_id" in str(getattr(exc_info.value, "detail", ""))


@pytest.mark.asyncio
async def test_project_activity_accepts_organization_id_as_company_compat_alias():
    from enterprise.litellm_enterprise.proxy.management_endpoints import (
        project_endpoints,
    )

    admin = UserAPIKeyAuth(user_id="root", user_role=LitellmUserRoles.PROXY_ADMIN.value)

    team = MagicMock()
    team.team_id = "team-company"
    team.organization_id = "company-1"

    project = MagicMock()
    project.project_id = "project-1"
    project.project_alias = "Project 1"
    project.company_id = "company-1"
    project.team_id = "team-company"
    project.litellm_team_table = team

    prisma = MagicMock()
    prisma.db.litellm_teamtable.find_many = AsyncMock(return_value=[team])
    prisma.db.litellm_projecttable.find_many = AsyncMock(return_value=[project])

    captured = {}

    async def _fake_get_daily_activity(**kwargs):
        captured.update(kwargs)
        return MagicMock()

    with (
        patch("litellm.proxy.proxy_server.prisma_client", prisma),
        patch(
            "enterprise.litellm_enterprise.proxy.management_endpoints.project_endpoints.get_daily_activity",
            new=AsyncMock(side_effect=_fake_get_daily_activity),
        ),
    ):
        await project_endpoints.get_project_daily_activity(
            project_id="project-1",
            organization_id="company-1",
            start_date="2026-01-01",
            end_date="2026-01-02",
            user_api_key_dict=admin,
        )

    project_where = prisma.db.litellm_projecttable.find_many.call_args.kwargs["where"]
    assert project_where["project_id"] == {"in": ["project-1"]}
    assert project_where["team_id"] == {"in": ["team-company"]}
    assert captured["entity_id"] == ["project-1"]
    assert captured["table_name"] == "litellm_dailyprojectspend"


@pytest.mark.asyncio
async def test_project_activity_rejects_conflicting_company_and_organization_aliases():
    from enterprise.litellm_enterprise.proxy.management_endpoints import (
        project_endpoints,
    )

    admin = UserAPIKeyAuth(user_id="root", user_role=LitellmUserRoles.PROXY_ADMIN.value)
    prisma = MagicMock()

    with patch("litellm.proxy.proxy_server.prisma_client", prisma):
        with pytest.raises(Exception) as exc_info:
            await project_endpoints.get_project_daily_activity(
                company_id="company-1",
                organization_id="company-2",
                start_date="2026-01-01",
                end_date="2026-01-02",
                user_api_key_dict=admin,
            )

    assert getattr(exc_info.value, "status_code", None) == 400
    detail = str(getattr(exc_info.value, "detail", ""))
    assert "company_id/company_ids" in detail
    assert "organization_id/organization_ids" in detail


def _project_activity_team(team_id: str, company_id: str):
    team = MagicMock()
    team.team_id = team_id
    team.organization_id = company_id
    return team


def _project_activity_project(project_id: str, team):
    project = MagicMock()
    project.project_id = project_id
    project.project_alias = project_id
    project.company_id = getattr(team, "organization_id", None)
    project.team_id = team.team_id
    project.litellm_team_table = team
    return project


def _filter_project_activity_rows(rows, where):
    result = rows
    project_filter = where.get("project_id")
    if isinstance(project_filter, dict) and "in" in project_filter:
        result = [row for row in result if row.project_id in project_filter["in"]]

    team_filter = where.get("team_id")
    if isinstance(team_filter, dict) and "in" in team_filter:
        result = [row for row in result if row.team_id in team_filter["in"]]

    return result


@pytest.mark.asyncio
async def test_project_activity_company_admin_can_view_own_company_project():
    from enterprise.litellm_enterprise.proxy.management_endpoints import (
        project_endpoints,
    )

    auth = UserAPIKeyAuth(
        user_id="company-admin",
        user_role=LitellmUserRoles.INTERNAL_USER.value,
    )
    team = _project_activity_team("team-company", "company-1")
    project = _project_activity_project("project-1", team)

    prisma = MagicMock()
    prisma.db.litellm_teamtable.find_many = AsyncMock(return_value=[team])
    prisma.db.litellm_usertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(teams=[])
    )
    prisma.db.litellm_organizationmembership.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                organization_id="company-1",
                user_role=LitellmUserRoles.ORG_ADMIN.value,
            )
        ]
    )
    prisma.db.litellm_projecttable.find_many = AsyncMock(return_value=[project])

    captured = {}

    async def _fake_get_daily_activity(**kwargs):
        captured.update(kwargs)
        return MagicMock()

    with (
        patch("litellm.proxy.proxy_server.prisma_client", prisma),
        patch(
            "enterprise.litellm_enterprise.proxy.management_endpoints.project_endpoints.get_daily_activity",
            new=AsyncMock(side_effect=_fake_get_daily_activity),
        ),
    ):
        await project_endpoints.get_project_daily_activity(
            project_ids=None,
            project_id="project-1",
            company_ids=None,
            company_id="company-1",
            organization_ids=None,
            organization_id=None,
            start_date="2026-05-18",
            end_date="2026-05-18",
            api_key="runtime-key-hash",
            exclude_project_ids=None,
            exclude_project_id=None,
            user_api_key_dict=auth,
        )

    project_where = prisma.db.litellm_projecttable.find_many.call_args.kwargs["where"]
    assert project_where["project_id"] == {"in": ["project-1"]}
    assert project_where["team_id"] == {"in": ["team-company"]}
    assert captured["table_name"] == "litellm_dailyprojectspend"
    assert captured["entity_id"] == ["project-1"]
    assert captured["api_key"] == "runtime-key-hash"


@pytest.mark.asyncio
async def test_project_activity_company_admin_rejects_project_outside_company_scope():
    from enterprise.litellm_enterprise.proxy.management_endpoints import (
        project_endpoints,
    )

    auth = UserAPIKeyAuth(
        user_id="company-admin",
        user_role=LitellmUserRoles.INTERNAL_USER.value,
    )
    company_team = _project_activity_team("team-company", "company-1")
    outside_team = _project_activity_team("team-outside", "company-2")
    outside_project = _project_activity_project("project-outside", outside_team)

    async def find_teams(where):
        company_ids = where["organization_id"]["in"]
        return [
            team
            for team in [company_team, outside_team]
            if team.organization_id in company_ids
        ]

    async def find_projects(where, include=None):
        return _filter_project_activity_rows([outside_project], where)

    prisma = MagicMock()
    prisma.db.litellm_teamtable.find_many = AsyncMock(side_effect=find_teams)
    prisma.db.litellm_usertable.find_unique = AsyncMock(
        return_value=SimpleNamespace(teams=[])
    )
    prisma.db.litellm_organizationmembership.find_many = AsyncMock(
        return_value=[
            SimpleNamespace(
                organization_id="company-1",
                user_role=LitellmUserRoles.ORG_ADMIN.value,
            )
        ]
    )
    prisma.db.litellm_projecttable.find_many = AsyncMock(side_effect=find_projects)

    get_daily_activity_mock = AsyncMock(return_value=MagicMock())
    with (
        patch("litellm.proxy.proxy_server.prisma_client", prisma),
        patch(
            "enterprise.litellm_enterprise.proxy.management_endpoints.project_endpoints.get_daily_activity",
            new=get_daily_activity_mock,
        ),
    ):
        with pytest.raises(Exception) as exc_info:
            await project_endpoints.get_project_daily_activity(
                project_ids=None,
                project_id="project-outside",
                company_ids=None,
                company_id="company-1",
                organization_ids=None,
                organization_id=None,
                start_date="2026-05-18",
                end_date="2026-05-18",
                api_key="runtime-key-hash",
                exclude_project_ids=None,
                exclude_project_id=None,
                user_api_key_dict=auth,
            )

    assert getattr(exc_info.value, "status_code", None) == 404
    get_daily_activity_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_agent_activity_non_admin_no_perms_falls_back_to_owned():
    """Non-admin without explicit agent permissions: scope to agents they
    created. An empty `agent_ids` query must NOT return everyone's agents."""
    from litellm.proxy.agent_endpoints import endpoints

    user = UserAPIKeyAuth(
        user_id="alice",
        user_role=LitellmUserRoles.INTERNAL_USER.value,
    )

    owned = [MagicMock(agent_id="agent-alice-1"), MagicMock(agent_id="agent-alice-2")]
    prisma = MagicMock()
    # First call: lookup of owned agents (created_by=alice).
    # Second call: agent_metadata fetch for the resolved set.
    prisma.db.litellm_agentstable.find_many = AsyncMock(side_effect=[owned, owned])

    captured = {}

    async def _fake_get_daily_activity(**kwargs):
        captured.update(kwargs)
        return MagicMock()

    with (
        patch.object(endpoints, "prisma_client", prisma, create=True),
        patch("litellm.proxy.proxy_server.prisma_client", prisma),
        patch(
            "litellm.proxy.agent_endpoints.endpoints.check_feature_access_for_user",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "litellm.proxy.agent_endpoints.auth.agent_permission_handler.AgentRequestHandler.get_allowed_agents",
            new=AsyncMock(return_value=[]),  # no explicit agent permissions
        ),
        patch(
            "litellm.proxy.agent_endpoints.endpoints.get_daily_activity",
            new=AsyncMock(side_effect=_fake_get_daily_activity),
        ),
    ):
        await endpoints.get_agent_daily_activity(
            agent_ids=None,
            start_date="2026-01-01",
            end_date="2026-01-02",
            user_api_key_dict=user,
        )

    # entity_id must be the user's owned agents, not None (which would
    # match every row).
    assert sorted(captured["entity_id"]) == ["agent-alice-1", "agent-alice-2"]


@pytest.mark.asyncio
async def test_agent_activity_non_admin_intersects_explicit_agent_ids():
    """When the caller passes `agent_ids`, the result is intersected with
    their permitted set rather than trusting the request."""
    from litellm.proxy.agent_endpoints import endpoints

    user = UserAPIKeyAuth(
        user_id="alice",
        user_role=LitellmUserRoles.INTERNAL_USER.value,
    )

    prisma = MagicMock()
    prisma.db.litellm_agentstable.find_many = AsyncMock(return_value=[])

    captured = {}

    async def _fake_get_daily_activity(**kwargs):
        captured.update(kwargs)
        return MagicMock()

    with (
        patch.object(endpoints, "prisma_client", prisma, create=True),
        patch("litellm.proxy.proxy_server.prisma_client", prisma),
        patch(
            "litellm.proxy.agent_endpoints.endpoints.check_feature_access_for_user",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "litellm.proxy.agent_endpoints.auth.agent_permission_handler.AgentRequestHandler.get_allowed_agents",
            new=AsyncMock(return_value=["agent-permitted"]),
        ),
        patch(
            "litellm.proxy.agent_endpoints.endpoints.get_daily_activity",
            new=AsyncMock(side_effect=_fake_get_daily_activity),
        ),
    ):
        await endpoints.get_agent_daily_activity(
            agent_ids="agent-permitted,agent-someone-elses",
            start_date="2026-01-01",
            end_date="2026-01-02",
            user_api_key_dict=user,
        )

    # Only the permitted agent survives the intersection.
    assert captured["entity_id"] == ["agent-permitted"]


@pytest.mark.asyncio
async def test_agent_activity_keyless_caller_does_not_query_created_by_null():
    """Guard against the `WHERE created_by IS NULL` pitfall: a non-admin
    caller without a user_id (e.g. a service-account key with no
    explicit agent allowlist) must NOT trigger a fallback DB query that
    would expose every ownerless agent."""
    from litellm.proxy.agent_endpoints import endpoints

    user = UserAPIKeyAuth(
        api_key="sk-svc",
        # NOTE: no user_id
        user_role=LitellmUserRoles.INTERNAL_USER.value,
    )

    prisma = MagicMock()
    prisma.db.litellm_agentstable.find_many = AsyncMock(return_value=[])

    fake_get_daily = AsyncMock()

    with (
        patch.object(endpoints, "prisma_client", prisma, create=True),
        patch("litellm.proxy.proxy_server.prisma_client", prisma),
        patch(
            "litellm.proxy.agent_endpoints.endpoints.check_feature_access_for_user",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "litellm.proxy.agent_endpoints.auth.agent_permission_handler.AgentRequestHandler.get_allowed_agents",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "litellm.proxy.agent_endpoints.endpoints.get_daily_activity",
            new=fake_get_daily,
        ),
    ):
        result = await endpoints.get_agent_daily_activity(
            agent_ids=None,
            start_date="2026-01-01",
            end_date="2026-01-02",
            user_api_key_dict=user,
        )

    # Empty page; the owned-agents fallback must NOT have been queried.
    assert result.results == []
    prisma.db.litellm_agentstable.find_many.assert_not_called()
    fake_get_daily.assert_not_awaited()


@pytest.mark.asyncio
async def test_agent_activity_non_admin_no_access_returns_empty_page():
    """Non-admin with no permitted agents and no owned agents must get an
    empty paginated response without an unscoped DB query."""
    from litellm.proxy.agent_endpoints import endpoints

    user = UserAPIKeyAuth(
        user_id="alice",
        user_role=LitellmUserRoles.INTERNAL_USER.value,
    )

    prisma = MagicMock()
    prisma.db.litellm_agentstable.find_many = AsyncMock(return_value=[])

    fake_get_daily = AsyncMock()

    with (
        patch.object(endpoints, "prisma_client", prisma, create=True),
        patch("litellm.proxy.proxy_server.prisma_client", prisma),
        patch(
            "litellm.proxy.agent_endpoints.endpoints.check_feature_access_for_user",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "litellm.proxy.agent_endpoints.auth.agent_permission_handler.AgentRequestHandler.get_allowed_agents",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "litellm.proxy.agent_endpoints.endpoints.get_daily_activity",
            new=fake_get_daily,
        ),
    ):
        result = await endpoints.get_agent_daily_activity(
            agent_ids=None,
            start_date="2026-01-01",
            end_date="2026-01-02",
            user_api_key_dict=user,
        )

    assert result.results == []
    fake_get_daily.assert_not_awaited()
