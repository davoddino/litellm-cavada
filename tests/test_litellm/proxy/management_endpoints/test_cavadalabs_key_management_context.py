from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.management_endpoints.key_management_endpoints import (
    _should_validate_litellm_org_assignment_for_key_generate,
)


def test_cavadalabs_key_generate_context_skips_legacy_org_assignment_gate():
    should_validate = _should_validate_litellm_org_assignment_for_key_generate(
        data_json={
            "organization_id": "org-1",
            "team_id": "team-1",
            "metadata": {
                "cavadalabs_company_id": "company-1",
                "cavadalabs_project_id": "project-1",
            },
        },
        organization_id="org-1",
        user_api_key_dict=UserAPIKeyAuth(
            user_id="project-admin",
            user_role=LitellmUserRoles.INTERNAL_USER.value,
        ),
    )

    assert should_validate is False


def test_legacy_key_generate_context_still_requires_org_assignment_gate():
    should_validate = _should_validate_litellm_org_assignment_for_key_generate(
        data_json={
            "organization_id": "org-1",
            "team_id": "team-1",
            "metadata": {"owner": "support"},
        },
        organization_id="org-1",
        user_api_key_dict=UserAPIKeyAuth(
            user_id="internal-user",
            user_role=LitellmUserRoles.INTERNAL_USER.value,
        ),
    )

    assert should_validate is True


def test_top_level_cavadalabs_key_generate_context_skips_legacy_org_assignment_gate():
    should_validate = _should_validate_litellm_org_assignment_for_key_generate(
        data_json={
            "organization_id": "org-1",
            "team_id": "team-1",
            "cavadalabs_company_id": "company-1",
            "cavadalabs_project_id": "project-1",
            "metadata": {"owner": "support"},
        },
        organization_id="org-1",
        user_api_key_dict=UserAPIKeyAuth(
            user_id="project-admin",
            user_role=LitellmUserRoles.INTERNAL_USER.value,
        ),
    )

    assert should_validate is False


def test_proxy_admin_skips_legacy_org_assignment_gate():
    should_validate = _should_validate_litellm_org_assignment_for_key_generate(
        data_json={
            "organization_id": "org-1",
            "team_id": "team-1",
            "metadata": {"owner": "support"},
        },
        organization_id="org-1",
        user_api_key_dict=UserAPIKeyAuth(
            user_id="proxy-admin",
            user_role=LitellmUserRoles.PROXY_ADMIN.value,
        ),
    )

    assert should_validate is False
