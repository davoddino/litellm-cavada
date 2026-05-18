"""
Tests for litellm/proxy/management_endpoints/common_utils.py

Covers the fix for GitHub issue #20304:
Empty guardrails/policies arrays sent by the UI should NOT trigger the
enterprise (premium) license check, but should still be applied so that
users can intentionally clear previously-set fields.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from litellm.proxy._types import (
    Member,
    LiteLLM_OrganizationMembershipTable,
    LiteLLM_TeamTable,
    LiteLLM_UserTable,
    LitellmUserRoles,
    UserAPIKeyAuth,
)
from litellm.proxy.management_endpoints.common_utils import (
    _is_user_team_admin,
    _org_admin_can_invite_user,
    _set_object_metadata_field,
    _team_admin_can_invite_user,
    _update_metadata_fields,
    _user_has_admin_privileges,
    _user_has_admin_view,
    admin_can_invite_user,
    build_company_project_access_context,
)


class TestUpdateMetadataFieldsEmptyCollections:
    """
    Regression tests for issue #20304.

    The UI sends empty arrays (`[]`) for enterprise-only fields like
    guardrails, policies, and logging even when the user hasn't configured
    these features.  The backend must not treat empty collections as an
    intent to use the feature, and therefore must not trigger the premium
    license check.

    However, empty collections must still be written into metadata so that
    users can intentionally clear a previously-set field (e.g. removing all
    guardrails by sending `guardrails: []`).
    """

    @patch("litellm.proxy.management_endpoints.common_utils._premium_user_check")
    def test_empty_list_does_not_trigger_premium_check(self, mock_premium_check):
        """Empty lists for premium fields must not trigger the premium check."""
        updated_kv = {
            "team_id": "test-team",
            "guardrails": [],
            "policies": [],
            "logging": [],
        }
        _update_metadata_fields(updated_kv=updated_kv)
        mock_premium_check.assert_not_called()

    @patch("litellm.proxy.management_endpoints.common_utils._premium_user_check")
    def test_empty_list_still_updates_metadata(self, mock_premium_check):
        """
        Empty lists must still be moved into metadata so users can clear
        previously-set fields (e.g. remove all guardrails).
        """
        updated_kv = {
            "team_id": "test-team",
            "guardrails": [],
            "policies": [],
        }
        _update_metadata_fields(updated_kv=updated_kv)
        # The fields should have been moved into metadata
        assert (
            "guardrails" not in updated_kv
        ), "guardrails should be popped from top-level"
        assert "policies" not in updated_kv, "policies should be popped from top-level"
        assert updated_kv["metadata"]["guardrails"] == []
        assert updated_kv["metadata"]["policies"] == []

    @patch("litellm.proxy.management_endpoints.common_utils._premium_user_check")
    def test_empty_dict_does_not_trigger_premium_check(self, mock_premium_check):
        """Empty dicts for premium fields must not trigger the premium check."""
        updated_kv = {
            "team_id": "test-team",
            "secret_manager_settings": {},
        }
        _update_metadata_fields(updated_kv=updated_kv)
        mock_premium_check.assert_not_called()

    @patch("litellm.proxy.management_endpoints.common_utils._premium_user_check")
    def test_empty_dict_still_updates_metadata(self, mock_premium_check):
        """
        Empty dicts must still be moved into metadata so users can clear
        previously-set fields.
        """
        updated_kv = {
            "team_id": "test-team",
            "secret_manager_settings": {},
        }
        _update_metadata_fields(updated_kv=updated_kv)
        assert (
            "secret_manager_settings" not in updated_kv
        ), "secret_manager_settings should be popped from top-level"
        assert updated_kv["metadata"]["secret_manager_settings"] == {}

    @patch("litellm.proxy.management_endpoints.common_utils._premium_user_check")
    def test_none_value_does_not_trigger_premium_check(self, mock_premium_check):
        """None values for premium fields should be silently ignored."""
        updated_kv = {
            "team_id": "test-team",
            "guardrails": None,
            "policies": None,
        }
        _update_metadata_fields(updated_kv=updated_kv)
        mock_premium_check.assert_not_called()

    @patch("litellm.proxy.management_endpoints.common_utils._premium_user_check")
    def test_absent_fields_do_not_trigger_premium_check(self, mock_premium_check):
        """Fields not present in the dict should not trigger premium check."""
        updated_kv = {
            "team_id": "test-team",
            "team_alias": "example-team",
        }
        _update_metadata_fields(updated_kv=updated_kv)
        mock_premium_check.assert_not_called()

    @patch("litellm.proxy.management_endpoints.common_utils._premium_user_check")
    def test_non_empty_list_triggers_premium_check(self, mock_premium_check):
        """Non-empty lists for premium fields should trigger the premium check."""
        updated_kv = {
            "team_id": "test-team",
            "guardrails": ["my-guardrail"],
        }
        _update_metadata_fields(updated_kv=updated_kv)
        mock_premium_check.assert_called()

    @patch("litellm.proxy.management_endpoints.common_utils._premium_user_check")
    def test_non_empty_value_triggers_premium_check(self, mock_premium_check):
        """Non-empty string values for premium fields should trigger the premium check."""
        updated_kv = {
            "team_id": "test-team",
            "tags": ["production"],
        }
        _update_metadata_fields(updated_kv=updated_kv)
        mock_premium_check.assert_called()

    @patch("litellm.proxy.management_endpoints.common_utils._premium_user_check")
    def test_non_empty_list_updates_metadata(self, mock_premium_check):
        """Non-empty lists should be moved into metadata."""
        updated_kv = {
            "team_id": "test-team",
            "guardrails": ["my-guardrail"],
        }
        _update_metadata_fields(updated_kv=updated_kv)
        assert "guardrails" not in updated_kv
        assert updated_kv["metadata"]["guardrails"] == ["my-guardrail"]

    @patch("litellm.proxy.management_endpoints.common_utils._premium_user_check")
    def test_ui_typical_payload_does_not_trigger_premium_check(
        self, mock_premium_check
    ):
        """
        Simulate the exact payload the UI sends when no enterprise features
        are configured.  This must NOT trigger the premium check.
        """
        # This is the payload structure the UI sends (from issue #20304)
        updated_kv = {
            "team_id": "67848772-1a8b-4343-938c-17e60f1db860",
            "team_alias": "example-team",
            "models": ["gpt-4"],
            "metadata": {
                "guardrails": [],
                "logging": [],
            },
            "policies": [],
        }
        _update_metadata_fields(updated_kv=updated_kv)
        mock_premium_check.assert_not_called()


class TestUserHasAdminView:
    """Tests for _user_has_admin_view function."""

    @pytest.mark.parametrize(
        "user_role,expected",
        [
            (LitellmUserRoles.PROXY_ADMIN, True),
            (LitellmUserRoles.PROXY_ADMIN_VIEW_ONLY, True),
            (LitellmUserRoles.INTERNAL_USER, False),
            (LitellmUserRoles.INTERNAL_USER_VIEW_ONLY, False),
        ],
    )
    def test_user_has_admin_view_by_role(self, user_role, expected):
        """Parametrized test: admin roles return True, non-admin return False."""
        mock_auth = MagicMock()
        mock_auth.user_role = user_role
        assert _user_has_admin_view(mock_auth) == expected

    def test_user_has_admin_view_with_user_api_key_auth(self):
        """Test with actual UserAPIKeyAuth object."""
        auth_admin = UserAPIKeyAuth(
            user_id="u1",
            api_key="sk-xxx",
            user_role=LitellmUserRoles.PROXY_ADMIN,
        )
        auth_user = UserAPIKeyAuth(
            user_id="u2",
            api_key="sk-yyy",
            user_role=LitellmUserRoles.INTERNAL_USER,
        )
        assert _user_has_admin_view(auth_admin) is True
        assert _user_has_admin_view(auth_user) is False


class TestIsUserTeamAdmin:
    """Tests for _is_user_team_admin function."""

    @pytest.mark.parametrize(
        "members_with_roles,user_id,expected",
        [
            (
                [Member(user_id="u1", role="admin")],
                "u1",
                True,
            ),
            (
                [Member(user_id="u1", role="user")],
                "u1",
                False,
            ),
            (
                [
                    Member(user_id="u2", role="admin"),
                    Member(user_id="u1", role="admin"),
                ],
                "u1",
                True,
            ),
            ([], "u1", False),
        ],
    )
    def test_is_user_team_admin_parametrized(
        self, members_with_roles, user_id, expected
    ):
        """Parametrized test: user is team admin only when in members_with_roles with admin role."""
        mock_auth = MagicMock()
        mock_auth.user_id = user_id
        team = LiteLLM_TeamTable(
            team_id="team-1",
            members_with_roles=members_with_roles,
        )
        assert _is_user_team_admin(mock_auth, team) == expected

    def test_is_user_team_admin_user_not_in_team(self):
        """Test returns False when user is not in team members."""
        auth = UserAPIKeyAuth(user_id="u99", api_key="sk-x", user_role=None)
        team = LiteLLM_TeamTable(
            team_id="team-1",
            members_with_roles=[Member(user_id="u1", role="admin")],
        )
        assert _is_user_team_admin(auth, team) is False


class TestCompanyProjectAccessContext:
    """Product tenant authorization over existing LiteLLM membership data."""

    def _membership(self, company_id: str, role: str):
        now = datetime.now(timezone.utc)
        return LiteLLM_OrganizationMembershipTable(
            user_id="caller",
            organization_id=company_id,
            user_role=role,
            created_at=now,
            updated_at=now,
        )

    def _user_info(self, memberships=None):
        return LiteLLM_UserTable(
            user_id="caller",
            organization_memberships=memberships or [],
        )

    def _project_team(
        self,
        *,
        role: str = "user",
        route_permissions=None,
        user_id: str = "caller",
    ):
        return LiteLLM_TeamTable(
            team_id="project-team",
            organization_id="company-1",
            members_with_roles=[Member(user_id=user_id, role=role)],
            team_member_permissions=route_permissions,
        )

    def test_company_admin_can_read_company_and_manage_project(self):
        caller = UserAPIKeyAuth(
            user_id="caller",
            user_role=LitellmUserRoles.INTERNAL_USER,
        )
        context = build_company_project_access_context(
            user_api_key_dict=caller,
            complete_user_info=self._user_info(
                [
                    self._membership(
                        "company-1",
                        LitellmUserRoles.ORG_ADMIN.value,
                    )
                ]
            ),
            project_team_obj=self._project_team(user_id="other-user"),
            project_company_id="company-1",
            route_permission="/key/list",
        )

        assert context.can_read_company("company-1") is True
        assert context.can_read_project() is True
        assert context.can_manage_project() is True

    @pytest.mark.parametrize(
        "company_role",
        [
            LitellmUserRoles.INTERNAL_USER.value,
            LitellmUserRoles.INTERNAL_USER_VIEW_ONLY.value,
        ],
    )
    def test_company_member_or_viewer_can_read_own_company_only(
        self, company_role: str
    ):
        caller = UserAPIKeyAuth(
            user_id="caller",
            user_role=LitellmUserRoles.INTERNAL_USER,
        )
        context = build_company_project_access_context(
            user_api_key_dict=caller,
            complete_user_info=self._user_info(
                [
                    self._membership(
                        "company-1",
                        company_role,
                    )
                ]
            ),
            project_team_obj=self._project_team(user_id="other-user"),
            project_company_id="company-1",
            route_permission="/key/list",
        )

        assert context.can_read_company("company-1") is True
        assert context.can_read_company("company-2") is False
        assert context.can_read_project() is False
        assert context.can_manage_project() is False

    def test_customer_role_membership_does_not_grant_company_read(self):
        caller = UserAPIKeyAuth(
            user_id="caller",
            user_role=LitellmUserRoles.CUSTOMER,
        )
        context = build_company_project_access_context(
            user_api_key_dict=caller,
            complete_user_info=self._user_info(
                [
                    self._membership(
                        "company-1",
                        LitellmUserRoles.CUSTOMER.value,
                    )
                ]
            ),
        )

        assert context.can_read_company("company-1") is False

    def test_company_admin_cannot_read_other_company(self):
        caller = UserAPIKeyAuth(
            user_id="caller",
            user_role=LitellmUserRoles.INTERNAL_USER,
        )
        context = build_company_project_access_context(
            user_api_key_dict=caller,
            complete_user_info=self._user_info(
                [
                    self._membership(
                        "company-1",
                        LitellmUserRoles.ORG_ADMIN.value,
                    )
                ]
            ),
        )

        assert context.can_read_company("company-2") is False

    def test_project_admin_can_manage_project(self):
        caller = UserAPIKeyAuth(
            user_id="caller",
            user_role=LitellmUserRoles.INTERNAL_USER,
        )
        context = build_company_project_access_context(
            user_api_key_dict=caller,
            complete_user_info=self._user_info(),
            project_team_obj=self._project_team(role="admin"),
            project_company_id="company-1",
            route_permission="/key/list",
        )

        assert context.can_read_project() is True
        assert context.can_manage_project() is True

    def test_project_member_with_route_permission_can_manage_project_scope(self):
        caller = UserAPIKeyAuth(
            user_id="caller",
            user_role=LitellmUserRoles.INTERNAL_USER,
        )
        context = build_company_project_access_context(
            user_api_key_dict=caller,
            complete_user_info=self._user_info(),
            project_team_obj=self._project_team(route_permissions=["/key/list"]),
            project_company_id="company-1",
            route_permission="/key/list",
        )

        assert context.can_read_project() is True
        assert context.can_manage_project() is True

    def test_project_member_without_route_permission_is_read_only(self):
        caller = UserAPIKeyAuth(
            user_id="caller",
            user_role=LitellmUserRoles.INTERNAL_USER,
        )
        context = build_company_project_access_context(
            user_api_key_dict=caller,
            complete_user_info=self._user_info(),
            project_team_obj=self._project_team(route_permissions=[]),
            project_company_id="company-1",
            route_permission="/key/list",
        )

        assert context.can_read_project() is True
        assert context.can_manage_project() is False

    def test_proxy_admin_read_and_manage_compatibility(self):
        caller = UserAPIKeyAuth(
            user_id="proxy-admin",
            user_role=LitellmUserRoles.PROXY_ADMIN,
        )
        context = build_company_project_access_context(
            user_api_key_dict=caller,
            complete_user_info=self._user_info(),
            project_team_obj=self._project_team(user_id="other-user"),
            project_company_id="company-1",
            route_permission="/key/list",
        )

        assert context.can_read_company("company-any") is True
        assert context.can_read_project() is True
        assert context.can_manage_project() is True


class TestOrgAdminCanInviteUser:
    """Tests for _org_admin_can_invite_user function."""

    def _make_membership(self, org_id: str, user_role: str):
        now = datetime.now(timezone.utc)
        return LiteLLM_OrganizationMembershipTable(
            user_id="u",
            organization_id=org_id,
            user_role=user_role,
            created_at=now,
            updated_at=now,
        )

    @pytest.mark.parametrize(
        "admin_orgs,target_orgs,expected",
        [
            (["org1"], ["org1"], True),
            (["org1", "org2"], ["org2"], True),
            (["org1"], ["org2"], False),
            ([], ["org1"], False),
            (["org1"], [], False),
        ],
    )
    def test_org_admin_can_invite_user_parametrized(
        self, admin_orgs, target_orgs, expected
    ):
        """Parametrized test: can invite when target is in org where admin has ORG_ADMIN role."""
        admin_user = LiteLLM_UserTable(
            user_id="admin",
            organization_memberships=[
                self._make_membership(oid, LitellmUserRoles.ORG_ADMIN.value)
                for oid in admin_orgs
            ],
        )
        target_user = LiteLLM_UserTable(
            user_id="target",
            organization_memberships=[
                self._make_membership(oid, LitellmUserRoles.INTERNAL_USER.value)
                for oid in target_orgs
            ],
        )
        assert _org_admin_can_invite_user(admin_user, target_user) == expected

    def test_org_admin_can_invite_user_no_shared_org(self):
        """Test returns False when admin has no org admin role."""
        admin_user = LiteLLM_UserTable(
            user_id="admin",
            organization_memberships=[
                self._make_membership("org1", LitellmUserRoles.INTERNAL_USER.value),
            ],
        )
        target_user = LiteLLM_UserTable(
            user_id="target",
            organization_memberships=[
                self._make_membership("org1", LitellmUserRoles.INTERNAL_USER.value),
            ],
        )
        assert _org_admin_can_invite_user(admin_user, target_user) is False


class TestTeamAdminCanInviteUser:
    """Tests for _team_admin_can_invite_user async function."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "admin_teams,target_teams,user_is_admin_in,expected",
        [
            (["t1"], ["t1"], ["t1"], True),
            (["t1", "t2"], ["t2"], ["t1", "t2"], True),
            (["t1"], ["t2"], ["t1"], False),
        ],
    )
    async def test_team_admin_can_invite_user_parametrized(
        self, admin_teams, target_teams, user_is_admin_in, expected
    ):
        """Parametrized test: can invite when target shares a team where user is admin."""
        mock_prisma = MagicMock()
        mock_auth = MagicMock()
        mock_auth.user_id = "admin"

        admin_user = LiteLLM_UserTable(user_id="admin", teams=admin_teams)
        target_user = LiteLLM_UserTable(user_id="target", teams=target_teams)

        def make_team(tid, is_admin):
            m = [{"user_id": "admin", "role": "admin"}] if is_admin else []
            obj = MagicMock()
            obj.team_id = tid
            obj.model_dump = lambda: {"team_id": tid, "members_with_roles": m}
            return obj

        teams = [make_team(tid, tid in user_is_admin_in) for tid in admin_teams]
        mock_prisma.db.litellm_teamtable.find_many = AsyncMock(return_value=teams)

        result = await _team_admin_can_invite_user(
            user_api_key_dict=mock_auth,
            admin_user_obj=admin_user,
            target_user_obj=target_user,
            prisma_client=mock_prisma,
        )
        assert result == expected

    @pytest.mark.asyncio
    async def test_team_admin_can_invite_user_no_shared_team(self):
        """Test returns False when admin and target share no team."""
        mock_prisma = MagicMock()
        mock_auth = MagicMock()
        mock_auth.user_id = "admin"
        admin_user = LiteLLM_UserTable(user_id="admin", teams=[])
        target_user = LiteLLM_UserTable(user_id="target", teams=["t1"])

        result = await _team_admin_can_invite_user(
            user_api_key_dict=mock_auth,
            admin_user_obj=admin_user,
            target_user_obj=target_user,
            prisma_client=mock_prisma,
        )
        assert result is False


class TestUserHasAdminPrivileges:
    """Tests for _user_has_admin_privileges async function."""

    @pytest.mark.asyncio
    async def test_proxy_admin_has_privileges(self):
        """Proxy admin always has admin privileges."""
        auth = UserAPIKeyAuth(
            user_id="admin",
            api_key="sk-x",
            user_role=LitellmUserRoles.PROXY_ADMIN,
        )
        result = await _user_has_admin_privileges(
            user_api_key_dict=auth,
            prisma_client=None,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_non_admin_no_prisma_returns_false(self):
        """Non-admin with no prisma connection has no privileges."""
        auth = UserAPIKeyAuth(
            user_id="user1",
            api_key="sk-x",
            user_role=LitellmUserRoles.INTERNAL_USER,
        )
        result = await _user_has_admin_privileges(
            user_api_key_dict=auth,
            prisma_client=None,
        )
        assert result is False


class TestAdminCanInviteUser:
    """Tests for admin_can_invite_user async function."""

    @pytest.mark.asyncio
    async def test_proxy_admin_can_invite_any_user(self):
        """Proxy admin can invite any user regardless of org/team."""
        auth = UserAPIKeyAuth(
            user_id="admin",
            api_key="sk-x",
            user_role=LitellmUserRoles.PROXY_ADMIN,
        )
        result = await admin_can_invite_user(
            target_user_id="any-user",
            user_api_key_dict=auth,
            prisma_client=None,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_non_admin_cannot_invite_without_prisma(self):
        """Non-admin with no prisma cannot invite."""
        auth = UserAPIKeyAuth(
            user_id="user1",
            api_key="sk-x",
            user_role=LitellmUserRoles.INTERNAL_USER,
        )
        result = await admin_can_invite_user(
            target_user_id="other-user",
            user_api_key_dict=auth,
            prisma_client=None,
        )
        assert result is False


class TestSetObjectMetadataField:
    """Tests for _set_object_metadata_field function."""

    @pytest.mark.parametrize(
        "field_name,value,should_call_premium",
        [
            ("guardrails", ["g1"], True),
            ("model_rpm_limit", {"gpt-4": 10}, False),
        ],
    )
    def test_set_object_metadata_field_parametrized(
        self, field_name, value, should_call_premium
    ):
        """Parametrized test: premium fields trigger _premium_user_check."""
        team = LiteLLM_TeamTable(team_id="t1", metadata={})
        with patch(
            "litellm.proxy.management_endpoints.common_utils._premium_user_check"
        ) as mock_premium:
            _set_object_metadata_field(team, field_name, value)
            if should_call_premium:
                mock_premium.assert_called_once()
            else:
                mock_premium.assert_not_called()
        assert team.metadata[field_name] == value

    def test_set_object_metadata_field_initializes_metadata_if_none(self):
        """Test initializes metadata dict when object has None."""
        team = LiteLLM_TeamTable(team_id="t1", metadata=None)
        with patch(
            "litellm.proxy.management_endpoints.common_utils._premium_user_check"
        ):
            _set_object_metadata_field(team, "model_rpm_limit", {"x": 1})
        assert team.metadata == {"model_rpm_limit": {"x": 1}}


class TestRequireCallerUserIdForNonAdmin:
    """
    Security regression: service-account keys (user_id=None) must not bypass
    the non-admin scoping branch on analytics endpoints.
    """

    def test_returns_user_id_when_present(self):
        from litellm.proxy.management_endpoints.common_utils import (
            require_caller_user_id_for_non_admin,
        )

        key_dict = UserAPIKeyAuth(
            user_id="user-abc",
            user_role=LitellmUserRoles.INTERNAL_USER,
        )
        assert require_caller_user_id_for_non_admin(key_dict) == "user-abc"

    def test_raises_403_when_user_id_is_none(self):
        from fastapi import HTTPException

        from litellm.proxy.management_endpoints.common_utils import (
            require_caller_user_id_for_non_admin,
        )

        # Simulates a service-account key (user_id forced to None at key creation)
        service_account_key = UserAPIKeyAuth(
            user_id=None,
            user_role=LitellmUserRoles.INTERNAL_USER,
        )
        with pytest.raises(HTTPException) as exc_info:
            require_caller_user_id_for_non_admin(service_account_key)

        assert exc_info.value.status_code == 403
        assert "Service-account keys" in str(exc_info.value.detail)
