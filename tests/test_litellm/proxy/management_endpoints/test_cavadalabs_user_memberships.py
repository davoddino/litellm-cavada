from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import ANY

import pytest
from fastapi import HTTPException, Request

from litellm.proxy._types import (
    CavadaLabsCompanyMembershipRequest,
    CavadaLabsProjectMembershipRequest,
    LitellmUserRoles,
    NewUserRequest,
    ProxyException,
    UpdateUserRequest,
    UserAPIKeyAuth,
)
from litellm.proxy.management_endpoints.internal_user_endpoints import (
    _add_user_to_cavadalabs_company_memberships,
    _add_user_to_cavadalabs_project_memberships,
    _check_user_info_v2_access,
    _resolve_user_list_cavadalabs_scope,
    _update_single_user_helper,
    get_users,
    new_user,
    user_info_v2,
)


def _company_row(**kwargs):
    return SimpleNamespace(
        company_id=kwargs.pop("company_id", "company-1"),
        legal_name=kwargs.pop("legal_name", "ACME"),
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
        litellm_organization_id=kwargs.pop("litellm_organization_id", "org-1"),
        created_at=datetime.now(timezone.utc),
        created_by="admin",
        updated_at=datetime.now(timezone.utc),
        updated_by="admin",
        **kwargs,
    )


def _project_row(**kwargs):
    return SimpleNamespace(
        project_id=kwargs.pop("project_id", "project-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        name=kwargs.pop("name", "Support"),
        status="production",
        allowed_models=[],
        allowed_rag_collections=[],
        default_chatbot_settings={},
        default_guardrail_policy=None,
        budget=None,
        retention_policy_override={},
        metadata={},
        litellm_team_id=kwargs.pop("litellm_team_id", "team-1"),
        created_at=datetime.now(timezone.utc),
        created_by="admin",
        updated_at=datetime.now(timezone.utc),
        updated_by="admin",
        **kwargs,
    )


def _user_table_row(**kwargs):
    data = {
        "user_id": kwargs.pop("user_id", "target-user"),
        "user_email": kwargs.pop("user_email", "target@example.com"),
        "user_role": kwargs.pop("user_role", LitellmUserRoles.INTERNAL_USER.value),
        "teams": kwargs.pop("teams", []),
        "models": kwargs.pop("models", []),
        "metadata": kwargs.pop("metadata", {}),
        "spend": kwargs.pop("spend", 0.0),
        "created_at": kwargs.pop("created_at", datetime.now(timezone.utc)),
        "updated_at": kwargs.pop("updated_at", datetime.now(timezone.utc)),
        **kwargs,
    }
    row = SimpleNamespace(**data)
    row.model_dump = lambda exclude_none=True: (
        {key: value for key, value in data.items() if value is not None}
        if exclude_none
        else dict(data)
    )
    row.model_dump_json = lambda exclude_none=True: "{}"
    return row


class _FakePrismaDelegate:
    def __init__(
        self,
        *,
        find_unique_result=None,
        find_unique_handler=None,
        find_many_result=None,
        count_result=None,
    ):
        self.find_unique_result = find_unique_result
        self.find_unique_handler = find_unique_handler
        self.find_many_result = [] if find_many_result is None else find_many_result
        self.count_result = count_result

    async def find_unique(self, *, where):
        if self.find_unique_handler is not None:
            return self.find_unique_handler(where)
        return self.find_unique_result

    async def find_many(self, *, where=None):
        return self.find_many_result

    async def count(self):
        return self.count_result


class _AsyncFunctionRecorder:
    def __init__(self, return_value=None):
        self.return_value = return_value
        self.await_count = 0
        self.calls = []

    async def __call__(self, *args, **kwargs):
        self.await_count += 1
        self.calls.append((args, kwargs))
        return self.return_value

    def assert_not_awaited(self):
        assert self.await_count == 0


class _AllowingLicenseCheck:
    def is_over_limit(self, *, total_users):
        return False


async def _noop_duplicate_check(*args, **kwargs):
    return None


def _user_management_prisma_for_cavadalabs_access(
    *,
    company_member=None,
    project_member=None,
):
    def _find_company(where):
        return _company_row(
            company_id=where["company_id"],
            litellm_organization_id=None,
        )

    def _find_project(where):
        return _project_row(
            project_id=where["project_id"],
            company_id="company-1",
            litellm_team_id=None,
        )

    return SimpleNamespace(
        db=SimpleNamespace(
            litellm_usertable=_FakePrismaDelegate(
                count_result=5,
                find_unique_result=SimpleNamespace(user_id="actor-user", teams=[]),
            ),
            cavadalabs_companytable=_FakePrismaDelegate(
                find_unique_handler=_find_company,
            ),
            cavadalabs_projecttable=_FakePrismaDelegate(
                find_unique_handler=_find_project,
            ),
            cavadalabs_companymembertable=_FakePrismaDelegate(
                find_unique_result=company_member,
                find_many_result=[company_member] if company_member is not None else [],
            ),
            cavadalabs_projectmembertable=_FakePrismaDelegate(
                find_unique_result=project_member,
                find_many_result=[project_member] if project_member is not None else [],
            ),
            litellm_organizationmembership=_FakePrismaDelegate(),
            litellm_teamtable=_FakePrismaDelegate(),
        )
    )


@pytest.mark.asyncio
async def test_new_user_accepts_cavadalabs_memberships_without_exposing_internal_scope(
    mocker,
):
    import litellm

    mock_prisma_client = mocker.MagicMock()
    mock_prisma_client.db.litellm_usertable.count = mocker.AsyncMock(return_value=5)
    mock_license_check = mocker.MagicMock()
    mock_license_check.is_over_limit.return_value = False
    mock_generate_key_helper_fn = mocker.AsyncMock(
        return_value={
            "user_id": "cavada-user",
            "token": "sk-cavada",
            "expires": None,
            "max_budget": None,
        }
    )
    mock_company_memberships = mocker.AsyncMock()
    mock_project_memberships = mocker.AsyncMock()
    mock_authorize_memberships = mocker.AsyncMock()
    mock_user_created_hook = mocker.AsyncMock()

    original_default_params = getattr(litellm, "default_internal_user_params", None)
    litellm.default_internal_user_params = None
    try:
        mocker.patch("litellm.proxy.proxy_server.prisma_client", mock_prisma_client)
        mocker.patch("litellm.proxy.proxy_server._license_check", mock_license_check)
        mocker.patch(
            "litellm.proxy.management_endpoints.internal_user_endpoints._check_duplicate_user_email",
            mocker.AsyncMock(),
        )
        mocker.patch(
            "litellm.proxy.management_endpoints.internal_user_endpoints._check_duplicate_user_id",
            mocker.AsyncMock(),
        )
        mocker.patch(
            "litellm.proxy.management_endpoints.internal_user_endpoints.generate_key_helper_fn",
            mock_generate_key_helper_fn,
        )
        mocker.patch(
            "litellm.proxy.management_endpoints.internal_user_endpoints._add_user_to_cavadalabs_company_memberships",
            mock_company_memberships,
        )
        mocker.patch(
            "litellm.proxy.management_endpoints.internal_user_endpoints._add_user_to_cavadalabs_project_memberships",
            mock_project_memberships,
        )
        mocker.patch(
            "litellm.proxy.management_endpoints.internal_user_endpoints._authorize_cavadalabs_user_membership_updates",
            mock_authorize_memberships,
        )
        mocker.patch(
            "litellm.proxy.management_endpoints.internal_user_endpoints.UserManagementEventHooks.async_user_created_hook",
            mock_user_created_hook,
        )

        response = await new_user(
            data=NewUserRequest(
                user_email="cavada@example.com",
                user_role="internal_user",
                cavadalabs_company_memberships=[
                    CavadaLabsCompanyMembershipRequest(
                        company_id="company-1",
                        role="company_admin",
                    )
                ],
                cavadalabs_project_memberships=[
                    CavadaLabsProjectMembershipRequest(
                        project_id="project-1",
                        role="project_admin",
                    )
                ],
            ),
            user_api_key_dict=UserAPIKeyAuth(
                user_id="company-admin",
                user_role=LitellmUserRoles.INTERNAL_USER,
            ),
        )

        call_kwargs = mock_generate_key_helper_fn.call_args.kwargs
        assert "cavadalabs_company_memberships" not in call_kwargs
        assert "cavadalabs_project_memberships" not in call_kwargs
        mock_authorize_memberships.assert_awaited_once()
        mock_company_memberships.assert_awaited_once()
        mock_project_memberships.assert_awaited_once()
        assert response.user_id == "cavada-user"
    finally:
        litellm.default_internal_user_params = original_default_params


@pytest.mark.asyncio
async def test_new_user_preauthorizes_cavadalabs_company_membership_before_create(
    monkeypatch,
):
    import litellm
    from litellm.proxy import proxy_server
    from litellm.proxy.management_endpoints import (
        internal_user_endpoints as user_endpoints,
    )

    fake_prisma_client = _user_management_prisma_for_cavadalabs_access()
    generate_key_helper_fn = _AsyncFunctionRecorder()

    original_default_params = getattr(litellm, "default_internal_user_params", None)
    litellm.default_internal_user_params = None
    try:
        monkeypatch.setattr(proxy_server, "prisma_client", fake_prisma_client)
        monkeypatch.setattr(proxy_server, "_license_check", _AllowingLicenseCheck())
        monkeypatch.setattr(
            user_endpoints,
            "_check_duplicate_user_email",
            _noop_duplicate_check,
        )
        monkeypatch.setattr(
            user_endpoints,
            "_check_duplicate_user_id",
            _noop_duplicate_check,
        )
        monkeypatch.setattr(
            user_endpoints,
            "generate_key_helper_fn",
            generate_key_helper_fn,
        )

        with pytest.raises(ProxyException) as exc_info:
            await new_user(
                data=NewUserRequest(
                    user_email="cross-company@example.com",
                    user_role="internal_user",
                    cavadalabs_company_memberships=[
                        CavadaLabsCompanyMembershipRequest(
                            company_id="company-2",
                            role="viewer",
                        )
                    ],
                ),
                user_api_key_dict=UserAPIKeyAuth(
                    user_id="actor-user",
                    user_role=LitellmUserRoles.INTERNAL_USER,
                ),
            )

        assert exc_info.value.code == "403"
        generate_key_helper_fn.assert_not_awaited()
    finally:
        litellm.default_internal_user_params = original_default_params


@pytest.mark.asyncio
async def test_new_user_preauthorizes_cavadalabs_project_membership_before_create(
    monkeypatch,
):
    import litellm
    from litellm.proxy import proxy_server
    from litellm.proxy.management_endpoints import (
        internal_user_endpoints as user_endpoints,
    )

    fake_prisma_client = _user_management_prisma_for_cavadalabs_access()
    generate_key_helper_fn = _AsyncFunctionRecorder()

    original_default_params = getattr(litellm, "default_internal_user_params", None)
    litellm.default_internal_user_params = None
    try:
        monkeypatch.setattr(proxy_server, "prisma_client", fake_prisma_client)
        monkeypatch.setattr(proxy_server, "_license_check", _AllowingLicenseCheck())
        monkeypatch.setattr(
            user_endpoints,
            "_check_duplicate_user_email",
            _noop_duplicate_check,
        )
        monkeypatch.setattr(
            user_endpoints,
            "_check_duplicate_user_id",
            _noop_duplicate_check,
        )
        monkeypatch.setattr(
            user_endpoints,
            "generate_key_helper_fn",
            generate_key_helper_fn,
        )

        with pytest.raises(ProxyException) as exc_info:
            await new_user(
                data=NewUserRequest(
                    user_email="cross-project@example.com",
                    user_role="internal_user",
                    cavadalabs_project_memberships=[
                        CavadaLabsProjectMembershipRequest(
                            project_id="project-2",
                            role="viewer",
                        )
                    ],
                ),
                user_api_key_dict=UserAPIKeyAuth(
                    user_id="actor-user",
                    user_role=LitellmUserRoles.INTERNAL_USER,
                ),
            )

        assert exc_info.value.code == "403"
        generate_key_helper_fn.assert_not_awaited()
    finally:
        litellm.default_internal_user_params = original_default_params


@pytest.mark.asyncio
async def test_cavadalabs_company_membership_maps_to_internal_organization_role(
    mocker,
):
    mock_prisma_client = mocker.MagicMock()
    mock_prisma_client.db.cavadalabs_companytable.find_unique = mocker.AsyncMock(
        return_value=_company_row()
    )
    mock_prisma_client.db.cavadalabs_companymembertable.upsert = mocker.AsyncMock()
    mock_organization_member_add = mocker.AsyncMock()
    mocker.patch(
        "litellm.proxy.management_endpoints.organization_endpoints.organization_member_add",
        mock_organization_member_add,
    )

    await _add_user_to_cavadalabs_company_memberships(
        user_id="user-1",
        memberships=[
            CavadaLabsCompanyMembershipRequest(
                company_id="company-1",
                role="company_admin",
            )
        ],
        prisma_client=mock_prisma_client,
        user_api_key_dict=UserAPIKeyAuth(
            user_id="proxy-admin",
            user_role=LitellmUserRoles.PROXY_ADMIN,
        ),
    )

    request = mock_organization_member_add.call_args.kwargs["data"]
    assert request.organization_id == "org-1"
    assert request.member[0].role == LitellmUserRoles.ORG_ADMIN
    mock_prisma_client.db.cavadalabs_companymembertable.upsert.assert_awaited_once_with(
        where={
            "company_id_user_id": {
                "company_id": "company-1",
                "user_id": "user-1",
            }
        },
        data={
            "create": {
                "company_id": "company-1",
                "user_id": "user-1",
                "role": "company_admin",
                "created_by": "proxy-admin",
                "updated_by": "proxy-admin",
            },
            "update": {
                "role": "company_admin",
                "updated_by": "proxy-admin",
            },
        },
    )


@pytest.mark.asyncio
async def test_cavadalabs_company_admin_can_assign_company_membership(mocker):
    mock_prisma_client = mocker.MagicMock()
    mock_prisma_client.db.cavadalabs_companytable.find_unique = mocker.AsyncMock(
        return_value=_company_row()
    )
    mock_prisma_client.db.cavadalabs_companymembertable.find_unique = mocker.AsyncMock(
        return_value=SimpleNamespace(
            company_id="company-1",
            user_id="company-admin",
            role="company_admin",
        )
    )
    mock_prisma_client.db.cavadalabs_companymembertable.upsert = mocker.AsyncMock()
    mock_organization_member_add = mocker.AsyncMock()
    mocker.patch(
        "litellm.proxy.management_endpoints.organization_endpoints.organization_member_add",
        mock_organization_member_add,
    )

    await _add_user_to_cavadalabs_company_memberships(
        user_id="target-user",
        memberships=[
            CavadaLabsCompanyMembershipRequest(
                company_id="company-1",
                role="operator",
            )
        ],
        prisma_client=mock_prisma_client,
        user_api_key_dict=UserAPIKeyAuth(
            user_id="company-admin",
            user_role=LitellmUserRoles.INTERNAL_USER,
        ),
    )

    mock_prisma_client.db.cavadalabs_companymembertable.upsert.assert_awaited_once()
    request = mock_organization_member_add.call_args.kwargs["data"]
    assert request.organization_id == "org-1"
    assert request.member[0].role == LitellmUserRoles.INTERNAL_USER


@pytest.mark.asyncio
async def test_cavadalabs_company_viewer_cannot_assign_company_membership(mocker):
    mock_prisma_client = mocker.MagicMock()
    mock_prisma_client.db.cavadalabs_companytable.find_unique = mocker.AsyncMock(
        return_value=_company_row()
    )
    mock_prisma_client.db.cavadalabs_companymembertable.find_unique = mocker.AsyncMock(
        return_value=SimpleNamespace(
            company_id="company-1",
            user_id="viewer-user",
            role="viewer",
        )
    )
    mock_prisma_client.db.cavadalabs_companymembertable.upsert = mocker.AsyncMock()

    with pytest.raises(HTTPException) as exc:
        await _add_user_to_cavadalabs_company_memberships(
            user_id="target-user",
            memberships=[
                CavadaLabsCompanyMembershipRequest(
                    company_id="company-1",
                    role="operator",
                )
            ],
            prisma_client=mock_prisma_client,
            user_api_key_dict=UserAPIKeyAuth(
                user_id="viewer-user",
                user_role=LitellmUserRoles.INTERNAL_USER_VIEW_ONLY,
            ),
        )

    assert exc.value.status_code == 403
    mock_prisma_client.db.cavadalabs_companymembertable.upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_cavadalabs_company_membership_upserts_native_membership_without_compatibility_mapping(
    mocker,
):
    mock_prisma_client = mocker.MagicMock()
    mock_prisma_client.db.cavadalabs_companytable.find_unique = mocker.AsyncMock(
        return_value=_company_row(litellm_organization_id=None)
    )
    mock_prisma_client.db.cavadalabs_companymembertable.upsert = mocker.AsyncMock()
    mock_organization_member_add = mocker.AsyncMock()
    mocker.patch(
        "litellm.proxy.management_endpoints.organization_endpoints.organization_member_add",
        mock_organization_member_add,
    )

    await _add_user_to_cavadalabs_company_memberships(
        user_id="user-1",
        memberships=[
            CavadaLabsCompanyMembershipRequest(
                company_id="company-1",
                role="company_admin",
            )
        ],
        prisma_client=mock_prisma_client,
        user_api_key_dict=UserAPIKeyAuth(
            user_id="proxy-admin",
            user_role=LitellmUserRoles.PROXY_ADMIN,
        ),
    )

    mock_prisma_client.db.cavadalabs_companymembertable.upsert.assert_awaited_once_with(
        where={
            "company_id_user_id": {
                "company_id": "company-1",
                "user_id": "user-1",
            }
        },
        data={
            "create": {
                "company_id": "company-1",
                "user_id": "user-1",
                "role": "company_admin",
                "created_by": "proxy-admin",
                "updated_by": "proxy-admin",
            },
            "update": {
                "role": "company_admin",
                "updated_by": "proxy-admin",
            },
        },
    )
    mock_organization_member_add.assert_not_called()


@pytest.mark.asyncio
async def test_cavadalabs_project_membership_maps_to_internal_team_role(mocker):
    mock_prisma_client = mocker.MagicMock()
    mock_prisma_client.db.cavadalabs_projecttable.find_unique = mocker.AsyncMock(
        return_value=_project_row()
    )
    mock_prisma_client.db.cavadalabs_companytable.find_unique = mocker.AsyncMock(
        return_value=_company_row()
    )
    mock_prisma_client.db.cavadalabs_projectmembertable.upsert = mocker.AsyncMock()
    mock_add_user_to_team = mocker.AsyncMock()
    mocker.patch(
        "litellm.proxy.management_endpoints.internal_user_endpoints._add_user_to_team",
        mock_add_user_to_team,
    )

    await _add_user_to_cavadalabs_project_memberships(
        user_id="user-1",
        user_email="user@example.com",
        memberships=[
            CavadaLabsProjectMembershipRequest(
                project_id="project-1",
                role="project_admin",
            )
        ],
        prisma_client=mock_prisma_client,
        user_api_key_dict=UserAPIKeyAuth(
            user_id="proxy-admin",
            user_role=LitellmUserRoles.PROXY_ADMIN,
        ),
    )

    mock_add_user_to_team.assert_awaited_once_with(
        user_id="user-1",
        team_id="team-1",
        user_api_key_dict=ANY,
        user_email="user@example.com",
        user_role="admin",
    )
    mock_prisma_client.db.cavadalabs_projectmembertable.upsert.assert_awaited_once_with(
        where={
            "project_id_user_id": {
                "project_id": "project-1",
                "user_id": "user-1",
            }
        },
        data={
            "create": {
                "project_id": "project-1",
                "user_id": "user-1",
                "role": "project_admin",
                "created_by": "proxy-admin",
                "updated_by": "proxy-admin",
            },
            "update": {
                "role": "project_admin",
                "updated_by": "proxy-admin",
            },
        },
    )


@pytest.mark.asyncio
async def test_cavadalabs_project_admin_can_assign_project_membership(mocker):
    mock_prisma_client = mocker.MagicMock()
    mock_prisma_client.db.cavadalabs_projecttable.find_unique = mocker.AsyncMock(
        return_value=_project_row()
    )
    mock_prisma_client.db.cavadalabs_companytable.find_unique = mocker.AsyncMock(
        return_value=_company_row()
    )
    mock_prisma_client.db.cavadalabs_projectmembertable.find_unique = mocker.AsyncMock(
        return_value=SimpleNamespace(
            project_id="project-1",
            user_id="project-admin",
            role="project_admin",
        )
    )
    mock_prisma_client.db.cavadalabs_projectmembertable.upsert = mocker.AsyncMock()
    mock_add_user_to_team = mocker.AsyncMock()
    mocker.patch(
        "litellm.proxy.management_endpoints.internal_user_endpoints._add_user_to_team",
        mock_add_user_to_team,
    )

    await _add_user_to_cavadalabs_project_memberships(
        user_id="target-user",
        user_email="target@example.com",
        memberships=[
            CavadaLabsProjectMembershipRequest(
                project_id="project-1",
                role="operator",
            )
        ],
        prisma_client=mock_prisma_client,
        user_api_key_dict=UserAPIKeyAuth(
            user_id="project-admin",
            user_role=LitellmUserRoles.INTERNAL_USER,
        ),
    )

    mock_prisma_client.db.cavadalabs_projectmembertable.upsert.assert_awaited_once()
    mock_add_user_to_team.assert_awaited_once_with(
        user_id="target-user",
        team_id="team-1",
        user_api_key_dict=ANY,
        user_email="target@example.com",
        user_role="user",
    )


@pytest.mark.asyncio
async def test_cavadalabs_project_operator_cannot_assign_project_membership(mocker):
    mock_prisma_client = mocker.MagicMock()
    mock_prisma_client.db.cavadalabs_projecttable.find_unique = mocker.AsyncMock(
        return_value=_project_row()
    )
    mock_prisma_client.db.cavadalabs_projectmembertable.find_unique = mocker.AsyncMock(
        return_value=SimpleNamespace(
            project_id="project-1",
            user_id="operator-user",
            role="operator",
        )
    )
    mock_prisma_client.db.cavadalabs_projectmembertable.upsert = mocker.AsyncMock()

    with pytest.raises(HTTPException) as exc:
        await _add_user_to_cavadalabs_project_memberships(
            user_id="target-user",
            user_email="target@example.com",
            memberships=[
                CavadaLabsProjectMembershipRequest(
                    project_id="project-1",
                    role="viewer",
                )
            ],
            prisma_client=mock_prisma_client,
            user_api_key_dict=UserAPIKeyAuth(
                user_id="operator-user",
                user_role=LitellmUserRoles.INTERNAL_USER,
            ),
        )

    assert exc.value.status_code == 403
    mock_prisma_client.db.cavadalabs_projectmembertable.upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_cavadalabs_project_membership_upserts_native_membership_without_compatibility_mapping(
    mocker,
):
    mock_prisma_client = mocker.MagicMock()
    mock_prisma_client.db.cavadalabs_projecttable.find_unique = mocker.AsyncMock(
        return_value=_project_row(litellm_team_id=None)
    )
    mock_prisma_client.db.cavadalabs_companytable.find_unique = mocker.AsyncMock(
        return_value=_company_row()
    )
    mock_prisma_client.db.cavadalabs_projectmembertable.upsert = mocker.AsyncMock()
    mock_add_user_to_team = mocker.AsyncMock()
    mocker.patch(
        "litellm.proxy.management_endpoints.internal_user_endpoints._add_user_to_team",
        mock_add_user_to_team,
    )

    await _add_user_to_cavadalabs_project_memberships(
        user_id="user-1",
        user_email="user@example.com",
        memberships=[
            CavadaLabsProjectMembershipRequest(
                project_id="project-1",
                role="project_admin",
            )
        ],
        prisma_client=mock_prisma_client,
        user_api_key_dict=UserAPIKeyAuth(
            user_id="proxy-admin",
            user_role=LitellmUserRoles.PROXY_ADMIN,
        ),
    )

    mock_prisma_client.db.cavadalabs_projectmembertable.upsert.assert_awaited_once_with(
        where={
            "project_id_user_id": {
                "project_id": "project-1",
                "user_id": "user-1",
            }
        },
        data={
            "create": {
                "project_id": "project-1",
                "user_id": "user-1",
                "role": "project_admin",
                "created_by": "proxy-admin",
                "updated_by": "proxy-admin",
            },
            "update": {
                "role": "project_admin",
                "updated_by": "proxy-admin",
            },
        },
    )
    mock_add_user_to_team.assert_not_called()


@pytest.mark.asyncio
async def test_user_list_cavadalabs_company_scope_uses_native_authorization(
    mocker,
):
    mock_prisma_client = mocker.MagicMock()
    mock_resolve_filters = mocker.patch(
        "litellm.proxy.management_endpoints.internal_user_endpoints.resolve_cavadalabs_user_list_filters",
        mocker.AsyncMock(return_value=(["org-1"], [])),
    )
    mock_legacy_authorize = mocker.patch(
        "litellm.proxy.management_endpoints.internal_user_endpoints._authorize_user_list_request",
        mocker.AsyncMock(
            side_effect=AssertionError("legacy Organization auth should not run")
        ),
    )

    (
        organization_ids,
        team_ids,
        default_cavadalabs_scope_filter,
    ) = await _resolve_user_list_cavadalabs_scope(
        prisma_client=mock_prisma_client,
        user_api_key_dict=UserAPIKeyAuth(
            user_id="company-admin",
            user_role=LitellmUserRoles.INTERNAL_USER,
        ),
        organization_ids=None,
        cavadalabs_company_ids="company-1",
        cavadalabs_project_ids=None,
        user_api_key_cache=mocker.MagicMock(),
        proxy_logging_obj=mocker.MagicMock(),
    )

    assert organization_ids == "org-1"
    assert team_ids == []
    assert default_cavadalabs_scope_filter is None
    mock_resolve_filters.assert_awaited_once()
    mock_legacy_authorize.assert_not_awaited()


@pytest.mark.asyncio
async def test_user_info_v2_allows_cavadalabs_company_scope_without_team_admin(
    mocker,
):
    target_user = _user_table_row(user_id="target-user")
    mock_prisma_client = mocker.MagicMock()
    mock_prisma_client.db.litellm_usertable.find_first = mocker.AsyncMock(
        return_value=target_user
    )
    mocker.patch("litellm.proxy.proxy_server.prisma_client", mock_prisma_client)
    mocker.patch(
        "litellm.proxy.management_endpoints.internal_user_endpoints.visible_company_wide_ids_for_user",
        mocker.AsyncMock(return_value={"company-1"}),
    )
    mocker.patch(
        "litellm.proxy.management_endpoints.internal_user_endpoints.visible_project_ids_for_user",
        mocker.AsyncMock(return_value=set()),
    )
    mocker.patch(
        "litellm.proxy.management_endpoints.internal_user_endpoints.resolve_cavadalabs_user_list_filters",
        mocker.AsyncMock(return_value=([], [])),
    )

    result = await _check_user_info_v2_access(
        user_api_key_dict=UserAPIKeyAuth(
            user_id="company-viewer",
            user_role=LitellmUserRoles.INTERNAL_USER_VIEW_ONLY,
        ),
        target_user_id="target-user",
    )

    assert result is target_user
    mock_prisma_client.db.litellm_usertable.find_first.assert_awaited_once_with(
        where={
            "user_id": "target-user",
            "AND": [
                {
                    "cavadalabs_company_memberships": {
                        "some": {"company_id": {"in": ["company-1"]}}
                    }
                }
            ],
        }
    )


@pytest.mark.asyncio
async def test_user_info_v2_limits_cavadalabs_project_scope_to_project_membership(
    mocker,
):
    target_user = _user_table_row(user_id="target-user")
    mock_prisma_client = mocker.MagicMock()
    mock_prisma_client.db.litellm_usertable.find_first = mocker.AsyncMock(
        return_value=target_user
    )
    mocker.patch("litellm.proxy.proxy_server.prisma_client", mock_prisma_client)
    mocker.patch(
        "litellm.proxy.management_endpoints.internal_user_endpoints.visible_company_wide_ids_for_user",
        mocker.AsyncMock(return_value=set()),
    )
    mocker.patch(
        "litellm.proxy.management_endpoints.internal_user_endpoints.visible_project_ids_for_user",
        mocker.AsyncMock(return_value={"project-1"}),
    )
    mocker.patch(
        "litellm.proxy.management_endpoints.internal_user_endpoints.resolve_cavadalabs_user_list_filters",
        mocker.AsyncMock(return_value=([], ["team-1"])),
    )

    result = await _check_user_info_v2_access(
        user_api_key_dict=UserAPIKeyAuth(
            user_id="project-admin",
            user_role=LitellmUserRoles.INTERNAL_USER,
        ),
        target_user_id="target-user",
    )

    assert result is target_user
    mock_prisma_client.db.litellm_usertable.find_first.assert_awaited_once_with(
        where={
            "user_id": "target-user",
            "AND": [
                {
                    "OR": [
                        {
                            "cavadalabs_project_memberships": {
                                "some": {"project_id": {"in": ["project-1"]}}
                            }
                        },
                        {"teams": {"hasSome": ["team-1"]}},
                    ]
                }
            ],
        }
    )


@pytest.mark.asyncio
async def test_user_info_v2_returns_native_cavadalabs_memberships(mocker):
    mock_prisma_client = mocker.MagicMock()
    mock_prisma_client.db.litellm_usertable.find_unique = mocker.AsyncMock(
        return_value=_user_table_row(user_id="target-user")
    )
    mock_prisma_client.db.cavadalabs_companymembertable.find_many = mocker.AsyncMock(
        return_value=[
            SimpleNamespace(
                company_id="company-1",
                user_id="target-user",
                role="viewer",
            )
        ]
    )
    mock_prisma_client.db.cavadalabs_projectmembertable.find_many = mocker.AsyncMock(
        return_value=[
            SimpleNamespace(
                project_id="project-1",
                user_id="target-user",
                role="project_admin",
            )
        ]
    )
    mocker.patch("litellm.proxy.proxy_server.prisma_client", mock_prisma_client)

    response = await user_info_v2(
        request=Request(scope={"type": "http", "path": "/v2/user/info"}),
        user_id="target-user",
        user_api_key_dict=UserAPIKeyAuth(
            user_id="proxy-admin",
            user_role=LitellmUserRoles.PROXY_ADMIN,
        ),
    )

    assert response.cavadalabs_company_memberships == [
        CavadaLabsCompanyMembershipRequest(company_id="company-1", role="viewer")
    ]
    assert response.cavadalabs_project_memberships == [
        CavadaLabsProjectMembershipRequest(
            project_id="project-1",
            role="project_admin",
        )
    ]


@pytest.mark.asyncio
async def test_user_list_keeps_legacy_organization_authorization_when_requested(
    mocker,
):
    mock_prisma_client = mocker.MagicMock()
    mocker.patch(
        "litellm.proxy.management_endpoints.internal_user_endpoints.resolve_cavadalabs_user_list_filters",
        mocker.AsyncMock(return_value=(["org-cavada"], [])),
    )
    mock_legacy_authorize = mocker.patch(
        "litellm.proxy.management_endpoints.internal_user_endpoints._authorize_user_list_request",
        mocker.AsyncMock(return_value="org-cavada,org-legacy"),
    )

    (
        organization_ids,
        team_ids,
        default_cavadalabs_scope_filter,
    ) = await _resolve_user_list_cavadalabs_scope(
        prisma_client=mock_prisma_client,
        user_api_key_dict=UserAPIKeyAuth(
            user_id="org-admin",
            user_role=LitellmUserRoles.INTERNAL_USER,
        ),
        organization_ids="org-legacy",
        cavadalabs_company_ids="company-1",
        cavadalabs_project_ids=None,
        user_api_key_cache=mocker.MagicMock(),
        proxy_logging_obj=mocker.MagicMock(),
    )

    assert organization_ids == "org-cavada,org-legacy"
    assert team_ids == []
    assert default_cavadalabs_scope_filter is None
    mock_legacy_authorize.assert_awaited_once()


@pytest.mark.asyncio
async def test_user_list_auto_scopes_cavadalabs_member_without_legacy_organization_filter(
    mocker,
):
    mock_prisma_client = mocker.MagicMock()
    mock_prisma_client.db.litellm_usertable.find_many = mocker.AsyncMock(
        return_value=[]
    )
    mock_prisma_client.db.litellm_usertable.count = mocker.AsyncMock(return_value=0)
    mocker.patch("litellm.proxy.proxy_server.prisma_client", mock_prisma_client)
    mocker.patch("litellm.proxy.proxy_server.user_api_key_cache", mocker.MagicMock())
    mocker.patch("litellm.proxy.proxy_server.proxy_logging_obj", mocker.MagicMock())
    mocker.patch(
        "litellm.proxy.management_endpoints.internal_user_endpoints.visible_company_ids_for_user",
        mocker.AsyncMock(return_value={"company-1"}),
    )
    mocker.patch(
        "litellm.proxy.management_endpoints.internal_user_endpoints.visible_project_ids_for_user",
        mocker.AsyncMock(return_value={"project-1"}),
    )
    mocker.patch(
        "litellm.proxy.management_endpoints.internal_user_endpoints.resolve_cavadalabs_user_list_filters",
        mocker.AsyncMock(return_value=(["org-1"], ["team-1"])),
    )
    mock_legacy_authorize = mocker.patch(
        "litellm.proxy.management_endpoints.internal_user_endpoints._authorize_user_list_request",
        mocker.AsyncMock(
            side_effect=AssertionError("legacy Organization auth should not run")
        ),
    )

    await get_users(
        role=None,
        user_ids=None,
        sso_user_ids=None,
        user_email=None,
        team=None,
        page=1,
        page_size=25,
        sort_by=None,
        sort_order="asc",
        organization_ids=None,
        cavadalabs_company_ids=None,
        cavadalabs_project_ids=None,
        user_api_key_dict=UserAPIKeyAuth(
            user_id="project-admin",
            user_role=LitellmUserRoles.INTERNAL_USER,
        ),
    )

    where = mock_prisma_client.db.litellm_usertable.find_many.call_args.kwargs["where"]
    assert where == {
        "AND": [
            {
                "OR": [
                    {
                        "cavadalabs_company_memberships": {
                            "some": {"company_id": {"in": ["company-1"]}}
                        }
                    },
                    {
                        "organization_memberships": {
                            "some": {"organization_id": {"in": ["org-1"]}}
                        }
                    },
                    {
                        "cavadalabs_project_memberships": {
                            "some": {"project_id": {"in": ["project-1"]}}
                        }
                    },
                    {"teams": {"hasSome": ["team-1"]}},
                ]
            }
        ]
    }
    mock_legacy_authorize.assert_not_awaited()


@pytest.mark.asyncio
async def test_user_list_filters_by_native_cavadalabs_memberships_without_compatibility_mapping(
    mocker,
):
    mock_prisma_client = mocker.MagicMock()
    mock_prisma_client.db.cavadalabs_companytable.find_unique = mocker.AsyncMock(
        return_value=_company_row(litellm_organization_id=None)
    )
    mock_prisma_client.db.cavadalabs_projecttable.find_unique = mocker.AsyncMock(
        return_value=_project_row(litellm_team_id=None)
    )
    mock_prisma_client.db.litellm_usertable.find_many = mocker.AsyncMock(
        return_value=[]
    )
    mock_prisma_client.db.litellm_usertable.count = mocker.AsyncMock(return_value=0)
    mocker.patch("litellm.proxy.proxy_server.prisma_client", mock_prisma_client)
    mocker.patch("litellm.proxy.proxy_server.user_api_key_cache", mocker.MagicMock())
    mocker.patch("litellm.proxy.proxy_server.proxy_logging_obj", mocker.MagicMock())

    await get_users(
        role=None,
        user_ids=None,
        sso_user_ids=None,
        user_email=None,
        team=None,
        page=1,
        page_size=25,
        sort_by=None,
        sort_order="asc",
        organization_ids=None,
        cavadalabs_company_ids="company-1",
        cavadalabs_project_ids="project-1",
        user_api_key_dict=UserAPIKeyAuth(
            user_id="proxy-admin",
            user_role=LitellmUserRoles.PROXY_ADMIN,
        ),
    )

    where = mock_prisma_client.db.litellm_usertable.find_many.call_args.kwargs["where"]
    assert where == {
        "AND": [
            {
                "cavadalabs_company_memberships": {
                    "some": {"company_id": {"in": ["company-1"]}}
                }
            },
            {
                "cavadalabs_project_memberships": {
                    "some": {"project_id": {"in": ["project-1"]}}
                }
            },
        ]
    }


@pytest.mark.asyncio
async def test_user_list_allows_cavadalabs_company_viewer_scope_without_legacy_org_admin(
    mocker,
):
    mock_prisma_client = mocker.MagicMock()
    mock_prisma_client.db.cavadalabs_companytable.find_unique = mocker.AsyncMock(
        return_value=_company_row(litellm_organization_id=None)
    )
    mock_prisma_client.db.cavadalabs_companymembertable.find_unique = mocker.AsyncMock(
        return_value=SimpleNamespace(
            company_id="company-1",
            user_id="viewer-user",
            role="viewer",
        )
    )
    mock_prisma_client.db.litellm_usertable.find_many = mocker.AsyncMock(
        return_value=[]
    )
    mock_prisma_client.db.litellm_usertable.count = mocker.AsyncMock(return_value=0)
    mocker.patch("litellm.proxy.proxy_server.prisma_client", mock_prisma_client)
    mocker.patch("litellm.proxy.proxy_server.user_api_key_cache", mocker.MagicMock())
    mocker.patch("litellm.proxy.proxy_server.proxy_logging_obj", mocker.MagicMock())
    mock_legacy_authorize = mocker.patch(
        "litellm.proxy.management_endpoints.internal_user_endpoints._authorize_user_list_request",
        mocker.AsyncMock(
            side_effect=AssertionError("legacy Organization auth should not run")
        ),
    )

    await get_users(
        role=None,
        user_ids=None,
        sso_user_ids=None,
        user_email=None,
        team=None,
        page=1,
        page_size=25,
        sort_by=None,
        sort_order="asc",
        organization_ids=None,
        cavadalabs_company_ids="company-1",
        cavadalabs_project_ids=None,
        user_api_key_dict=UserAPIKeyAuth(
            user_id="viewer-user",
            user_role=LitellmUserRoles.INTERNAL_USER_VIEW_ONLY,
        ),
    )

    where = mock_prisma_client.db.litellm_usertable.find_many.call_args.kwargs["where"]
    assert where == {
        "AND": [
            {
                "cavadalabs_company_memberships": {
                    "some": {"company_id": {"in": ["company-1"]}}
                }
            }
        ]
    }
    mock_legacy_authorize.assert_not_awaited()


@pytest.mark.asyncio
async def test_user_list_rejects_cavadalabs_viewer_cross_company_scope(mocker):
    mock_prisma_client = mocker.MagicMock()
    mock_prisma_client.db.cavadalabs_companytable.find_unique = mocker.AsyncMock(
        return_value=_company_row(
            company_id="company-2",
            litellm_organization_id=None,
        )
    )
    mock_prisma_client.db.cavadalabs_companymembertable.find_unique = mocker.AsyncMock(
        return_value=None
    )
    mock_prisma_client.db.cavadalabs_companymembertable.find_many = mocker.AsyncMock(
        return_value=[]
    )
    mock_prisma_client.db.cavadalabs_projectmembertable.find_many = mocker.AsyncMock(
        return_value=[]
    )
    mock_prisma_client.db.litellm_organizationmembership.find_many = mocker.AsyncMock(
        return_value=[]
    )
    mock_prisma_client.db.litellm_usertable.find_unique = mocker.AsyncMock(
        return_value=SimpleNamespace(user_id="viewer-user", teams=[])
    )
    mock_prisma_client.db.cavadalabs_projecttable.find_many = mocker.AsyncMock(
        return_value=[]
    )
    mocker.patch("litellm.proxy.proxy_server.prisma_client", mock_prisma_client)
    mocker.patch("litellm.proxy.proxy_server.user_api_key_cache", mocker.MagicMock())
    mocker.patch("litellm.proxy.proxy_server.proxy_logging_obj", mocker.MagicMock())

    with pytest.raises(HTTPException) as exc:
        await get_users(
            role=None,
            user_ids=None,
            sso_user_ids=None,
            user_email=None,
            team=None,
            page=1,
            page_size=25,
            sort_by=None,
            sort_order="asc",
            organization_ids=None,
            cavadalabs_company_ids="company-2",
            cavadalabs_project_ids=None,
            user_api_key_dict=UserAPIKeyAuth(
                user_id="viewer-user",
                user_role=LitellmUserRoles.INTERNAL_USER_VIEW_ONLY,
            ),
        )

    assert exc.value.status_code == 403
    mock_prisma_client.db.litellm_usertable.find_many.assert_not_called()


@pytest.mark.asyncio
async def test_user_list_filters_by_native_or_compatibility_cavadalabs_memberships(
    mocker,
):
    mock_prisma_client = mocker.MagicMock()
    mock_prisma_client.db.cavadalabs_companytable.find_unique = mocker.AsyncMock(
        return_value=_company_row(litellm_organization_id="org-1")
    )
    mock_prisma_client.db.cavadalabs_projecttable.find_unique = mocker.AsyncMock(
        return_value=_project_row(litellm_team_id="team-1")
    )
    mock_prisma_client.db.litellm_usertable.find_many = mocker.AsyncMock(
        return_value=[]
    )
    mock_prisma_client.db.litellm_usertable.count = mocker.AsyncMock(return_value=0)
    mocker.patch("litellm.proxy.proxy_server.prisma_client", mock_prisma_client)
    mocker.patch("litellm.proxy.proxy_server.user_api_key_cache", mocker.MagicMock())
    mocker.patch("litellm.proxy.proxy_server.proxy_logging_obj", mocker.MagicMock())

    await get_users(
        role=None,
        user_ids=None,
        sso_user_ids=None,
        user_email=None,
        team=None,
        page=1,
        page_size=25,
        sort_by=None,
        sort_order="asc",
        organization_ids=None,
        cavadalabs_company_ids="company-1",
        cavadalabs_project_ids="project-1",
        user_api_key_dict=UserAPIKeyAuth(
            user_id="proxy-admin",
            user_role=LitellmUserRoles.PROXY_ADMIN,
        ),
    )

    where = mock_prisma_client.db.litellm_usertable.find_many.call_args.kwargs["where"]
    assert where == {
        "AND": [
            {
                "OR": [
                    {
                        "cavadalabs_company_memberships": {
                            "some": {"company_id": {"in": ["company-1"]}}
                        }
                    },
                    {
                        "organization_memberships": {
                            "some": {"organization_id": {"in": ["org-1"]}}
                        }
                    },
                ]
            },
            {
                "OR": [
                    {
                        "cavadalabs_project_memberships": {
                            "some": {"project_id": {"in": ["project-1"]}}
                        }
                    },
                    {"teams": {"hasSome": ["team-1"]}},
                ]
            },
        ]
    }


@pytest.mark.asyncio
async def test_update_user_accepts_cavadalabs_membership_only_without_legacy_admin(
    mocker,
):
    mock_prisma_client = mocker.MagicMock()
    mock_prisma_client.db.litellm_usertable.find_first = mocker.AsyncMock(
        return_value=_user_table_row()
    )
    mock_prisma_client.update_data = mocker.AsyncMock()
    mock_company_memberships = mocker.AsyncMock()
    mock_project_memberships = mocker.AsyncMock()
    mock_authorize_memberships = mocker.AsyncMock()
    mocker.patch("litellm.proxy.proxy_server.prisma_client", mock_prisma_client)
    mocker.patch(
        "litellm.proxy.management_endpoints.internal_user_endpoints._authorize_cavadalabs_user_membership_updates",
        mock_authorize_memberships,
    )
    mocker.patch(
        "litellm.proxy.management_endpoints.internal_user_endpoints._add_user_to_cavadalabs_company_memberships",
        mock_company_memberships,
    )
    mocker.patch(
        "litellm.proxy.management_endpoints.internal_user_endpoints._add_user_to_cavadalabs_project_memberships",
        mock_project_memberships,
    )

    response = await _update_single_user_helper(
        user_request=UpdateUserRequest(
            user_id="target-user",
            cavadalabs_company_memberships=[
                CavadaLabsCompanyMembershipRequest(
                    company_id="company-1",
                    role="company_admin",
                )
            ],
            cavadalabs_project_memberships=[
                CavadaLabsProjectMembershipRequest(
                    project_id="project-1",
                    role="project_admin",
                )
            ],
        ),
        user_api_key_dict=UserAPIKeyAuth(
            user_id="company-admin",
            user_role=LitellmUserRoles.INTERNAL_USER,
        ),
    )

    mock_prisma_client.update_data.assert_not_awaited()
    mock_authorize_memberships.assert_awaited_once()
    mock_company_memberships.assert_awaited_once()
    mock_project_memberships.assert_awaited_once()
    assert response["user_id"] == "target-user"
    assert response["user_email"] == "target@example.com"


@pytest.mark.asyncio
async def test_update_user_rejects_non_admin_user_field_changes_with_cavadalabs_membership(
    mocker,
):
    mock_prisma_client = mocker.MagicMock()
    mock_prisma_client.db.litellm_usertable.find_first = mocker.AsyncMock(
        return_value=_user_table_row()
    )
    mock_company_memberships = mocker.AsyncMock()
    mock_authorize_memberships = mocker.AsyncMock()
    mocker.patch("litellm.proxy.proxy_server.prisma_client", mock_prisma_client)
    mocker.patch(
        "litellm.proxy.management_endpoints.internal_user_endpoints._authorize_cavadalabs_user_membership_updates",
        mock_authorize_memberships,
    )
    mocker.patch(
        "litellm.proxy.management_endpoints.internal_user_endpoints._add_user_to_cavadalabs_company_memberships",
        mock_company_memberships,
    )

    with pytest.raises(HTTPException) as exc:
        await _update_single_user_helper(
            user_request=UpdateUserRequest(
                user_id="target-user",
                max_budget=25.0,
                cavadalabs_company_memberships=[
                    CavadaLabsCompanyMembershipRequest(
                        company_id="company-1",
                        role="viewer",
                    )
                ],
            ),
            user_api_key_dict=UserAPIKeyAuth(
                user_id="company-admin",
                user_role=LitellmUserRoles.INTERNAL_USER,
            ),
        )

    assert exc.value.status_code == 403
    mock_authorize_memberships.assert_not_awaited()
    mock_company_memberships.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_user_sends_cavadalabs_memberships_as_native_requests(
    mocker,
):
    mock_prisma_client = mocker.MagicMock()
    mock_prisma_client.db.litellm_usertable.find_first = mocker.AsyncMock(
        return_value=_user_table_row()
    )
    mock_company_memberships = mocker.AsyncMock()
    mock_authorize_memberships = mocker.AsyncMock()
    mocker.patch("litellm.proxy.proxy_server.prisma_client", mock_prisma_client)
    mocker.patch(
        "litellm.proxy.management_endpoints.internal_user_endpoints._authorize_cavadalabs_user_membership_updates",
        mock_authorize_memberships,
    )
    mocker.patch(
        "litellm.proxy.management_endpoints.internal_user_endpoints._add_user_to_cavadalabs_company_memberships",
        mock_company_memberships,
    )

    await _update_single_user_helper(
        user_request=UpdateUserRequest(
            user_id="target-user",
            cavadalabs_company_memberships=[
                {
                    "company_id": "company-1",
                    "role": "viewer",
                }
            ],
        ),
        user_api_key_dict=UserAPIKeyAuth(
            user_id="company-admin",
            user_role=LitellmUserRoles.INTERNAL_USER,
        ),
    )

    memberships = mock_company_memberships.call_args.kwargs["memberships"]
    mock_authorize_memberships.assert_awaited_once()
    assert isinstance(memberships[0], CavadaLabsCompanyMembershipRequest)
    assert memberships[0].company_id == "company-1"
    assert memberships[0].role == "viewer"
