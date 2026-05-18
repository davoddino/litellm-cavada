"""
Endpoints for /project operations

/project/new
/project/update
/project/delete
/project/info
/project/list
"""

#### PROJECT MANAGEMENT ####

import json
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from litellm._logging import verbose_proxy_logger
from litellm._uuid import uuid
from litellm.proxy._types import *
from litellm.proxy.auth.user_api_key_auth import user_api_key_auth
from litellm.proxy.management_endpoints.common_daily_activity import get_daily_activity
from litellm.proxy.management_endpoints.common_utils import (
    _is_user_team_admin,
    _set_object_metadata_field,
    _team_member_has_permission,
    _user_has_admin_view,
    require_caller_user_id_for_non_admin,
)
from litellm.proxy.management_helpers.utils import (
    management_endpoint_wrapper,
)
from litellm.proxy.utils import PrismaClient, handle_exception_on_proxy
from litellm.types.proxy.management_endpoints.common_daily_activity import (
    SpendAnalyticsPaginatedResponse,
)

router = APIRouter()


async def _check_user_permission_for_project(
    user_api_key_dict: UserAPIKeyAuth,
    team_id: Optional[str],
    prisma_client: PrismaClient,
    require_admin: bool = False,
    team_object: Optional[LiteLLM_TeamTable] = None,
) -> bool:
    """
    Check if user has permission to manage a project.

    Returns True if user is proxy admin, team admin, or company admin for the
    team's company (when team_id provided).
    If require_admin=True, only proxy admins are allowed.

    If team_object is provided, it will be used instead of fetching from DB
    (avoids duplicate DB queries when team was already fetched for validation).
    """
    is_proxy_admin = user_api_key_dict.user_role == LitellmUserRoles.PROXY_ADMIN

    if require_admin:
        return is_proxy_admin

    if is_proxy_admin:
        return True

    if not team_id or not user_api_key_dict.user_id:
        return False

    team = team_object
    if team is None:
        team = await prisma_client.db.litellm_teamtable.find_unique(
            where={"team_id": team_id}
        )

    if team is None:
        return False

    if _user_is_project_team_admin(
        user_api_key_dict=user_api_key_dict,
        team=team,
    ):
        return True

    if await _is_user_company_admin_for_team(
        prisma_client=prisma_client,
        user_api_key_dict=user_api_key_dict,
        team=team,
    ):
        return True

    return False


async def _is_user_company_admin_for_team(
    *,
    prisma_client: PrismaClient,
    user_api_key_dict: UserAPIKeyAuth,
    team: Any,
) -> bool:
    company_id = _auth_field(team, "organization_id")
    if not isinstance(company_id, str) or not company_id:
        return False
    return await _is_user_company_admin_for_company(
        prisma_client=prisma_client,
        user_api_key_dict=user_api_key_dict,
        company_id=company_id,
    )


async def _is_user_company_admin_for_company(
    *,
    prisma_client: PrismaClient,
    user_api_key_dict: UserAPIKeyAuth,
    company_id: str,
) -> bool:
    if not user_api_key_dict.user_id:
        return False
    membership = await prisma_client.db.litellm_organizationmembership.find_unique(
        where={
            "user_id_organization_id": {
                "user_id": user_api_key_dict.user_id,
                "organization_id": company_id,
            }
        }
    )
    return (
        membership is not None
        and getattr(membership, "user_role", None) == LitellmUserRoles.ORG_ADMIN.value
    )


def _user_is_project_team_member(
    *,
    user_api_key_dict: UserAPIKeyAuth,
    team: Any,
) -> bool:
    caller_user_id = user_api_key_dict.user_id
    if not caller_user_id:
        return False
    for member in _auth_field(team, "members_with_roles") or []:
        member_user_id = (
            member.get("user_id")
            if isinstance(member, dict)
            else getattr(member, "user_id", None)
        )
        if member_user_id == caller_user_id:
            return True
    return False


def _user_is_project_team_admin(
    *,
    user_api_key_dict: UserAPIKeyAuth,
    team: Any,
) -> bool:
    caller_user_id = user_api_key_dict.user_id
    if not caller_user_id:
        return False

    team_admins = _auth_field(team, "admins") or []
    if caller_user_id in team_admins:
        return True

    for member in _auth_field(team, "members_with_roles") or []:
        member_user_id = (
            member.get("user_id")
            if isinstance(member, dict)
            else getattr(member, "user_id", None)
        )
        member_role = (
            member.get("role")
            if isinstance(member, dict)
            else getattr(member, "role", None)
        )
        if member_user_id == caller_user_id and member_role == "admin":
            return True
    return False


async def _project_team_for_auth(
    *,
    prisma_client: PrismaClient,
    project: Any,
) -> Optional[Any]:
    team = _auth_field(project, "litellm_team_table")
    if team is not None:
        return team
    team_id = _auth_field(project, "team_id")
    if not team_id:
        return None
    return await prisma_client.db.litellm_teamtable.find_unique(
        where={"team_id": team_id}
    )


def _auth_field(obj: Any, field_name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(field_name)
    return getattr(obj, field_name, None)


def _team_company_id(team: Any) -> Optional[str]:
    company_id = _auth_field(team, "company_id")
    if isinstance(company_id, str) and company_id:
        return company_id
    organization_id = _auth_field(team, "organization_id")
    return (
        organization_id
        if isinstance(organization_id, str) and organization_id
        else None
    )


def _validate_project_company_context(
    *,
    requested_company_id: Optional[str],
    team_object: Optional[Any],
) -> None:
    if requested_company_id is None:
        return

    team_company_id = _team_company_id(team_object) if team_object is not None else None
    if team_company_id != requested_company_id:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "company_id must match the Company for the selected Project backing team"
            },
        )


async def _user_can_read_project(
    *,
    prisma_client: PrismaClient,
    user_api_key_dict: UserAPIKeyAuth,
    project: Any,
) -> bool:
    if _user_has_admin_view(user_api_key_dict):
        return True

    team = await _project_team_for_auth(prisma_client=prisma_client, project=project)
    if team is None:
        return False
    if _user_is_project_team_member(user_api_key_dict=user_api_key_dict, team=team):
        return True
    return await _is_user_company_admin_for_team(
        prisma_client=prisma_client,
        user_api_key_dict=user_api_key_dict,
        team=team,
    )


async def _validate_team_exists(
    team_id: str,
    prisma_client: PrismaClient,
):
    """Validate that a team exists. Returns the team row."""
    team = await prisma_client.db.litellm_teamtable.find_unique(
        where={"team_id": team_id},
    )

    if team is None:
        raise ProxyException(
            message=f"Team not found, team_id={team_id}",
            type="not_found",
            code=404,
            param="team_id",
        )

    return team


def _check_team_project_limits(
    team_object: LiteLLM_TeamTable,
    data: Union[NewProjectRequest, UpdateProjectRequest],
) -> None:
    """
    Check that project limits respect its parent Team's limits.

    Mirrors _check_org_team_limits() from team_endpoints.py.

    Validates:
    - Project models are a subset of Team models
    - Project max_budget <= Team max_budget
    - Project tpm_limit <= Team tpm_limit
    - Project rpm_limit <= Team rpm_limit
    - Budget values are non-negative
    - soft_budget < max_budget
    """
    # --- Budget non-negativity checks ---
    if data.max_budget is not None and data.max_budget < 0:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"max_budget cannot be negative. Received: {data.max_budget}"
            },
        )
    if data.soft_budget is not None and data.soft_budget < 0:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"soft_budget cannot be negative. Received: {data.soft_budget}"
            },
        )

    # --- soft_budget < max_budget ---
    if data.soft_budget is not None and data.max_budget is not None:
        if data.soft_budget >= data.max_budget:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": f"soft_budget ({data.soft_budget}) must be strictly lower than max_budget ({data.max_budget})"
                },
            )

    # --- Validate project models are a subset of team models ---
    project_models = getattr(data, "models", None)
    team_models = team_object.models or []
    if project_models and len(team_models) > 0:
        # If team has 'all-proxy-models', skip validation as it allows all models
        if SpecialModelNames.all_proxy_models.value not in team_models:
            for m in project_models:
                if m not in team_models:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error": f"Model '{m}' not in team's allowed models. Team allowed models={team_models}. Team: {team_object.team_id}"
                        },
                    )

    # --- Validate project max_budget <= team max_budget ---
    # Team stores budget fields directly (max_budget, tpm_limit, rpm_limit)
    # unlike Project which uses a separate LiteLLM_BudgetTable relation
    if (
        data.max_budget is not None
        and team_object.max_budget is not None
        and data.max_budget > team_object.max_budget
    ):
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"Project max_budget ({data.max_budget}) exceeds team's max_budget ({team_object.max_budget}). Team: {team_object.team_id}"
            },
        )

    # --- Validate project tpm_limit <= team tpm_limit ---
    if (
        data.tpm_limit is not None
        and team_object.tpm_limit is not None
        and data.tpm_limit > team_object.tpm_limit
    ):
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"Project tpm_limit ({data.tpm_limit}) exceeds team's tpm_limit ({team_object.tpm_limit}). Team: {team_object.team_id}"
            },
        )

    # --- Validate project rpm_limit <= team rpm_limit ---
    if (
        data.rpm_limit is not None
        and team_object.rpm_limit is not None
        and data.rpm_limit > team_object.rpm_limit
    ):
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"Project rpm_limit ({data.rpm_limit}) exceeds team's rpm_limit ({team_object.rpm_limit}). Team: {team_object.team_id}"
            },
        )


async def _create_budget_for_project(
    data: NewProjectRequest,
    user_id: Optional[str],
    litellm_proxy_admin_name: str,
    prisma_client: PrismaClient,
) -> str:
    """Create a budget for the project and return budget_id."""
    budget_params = LiteLLM_BudgetTable.model_fields.keys()
    _json_data = data.json(exclude_none=True)
    _budget_data = {k: v for k, v in _json_data.items() if k in budget_params}
    budget_row = LiteLLM_BudgetTable(**_budget_data)

    new_budget = prisma_client.jsonify_object(budget_row.json(exclude_none=True))

    _budget = await prisma_client.db.litellm_budgettable.create(
        data={
            **new_budget,
            "created_by": user_id or litellm_proxy_admin_name,
            "updated_by": user_id or litellm_proxy_admin_name,
        }
    )

    return _budget.budget_id


async def _set_project_object_permission(
    data: NewProjectRequest,
    prisma_client: Optional[PrismaClient],
) -> Optional[str]:
    """
    Creates the LiteLLM_ObjectPermissionTable record for the project.
    Returns the object_permission_id if created, otherwise None.
    """
    if prisma_client is None:
        return None

    if data.object_permission is not None:
        created_object_permission = (
            await prisma_client.db.litellm_objectpermissiontable.create(
                data=data.object_permission.model_dump(exclude_none=True),
            )
        )
        del data.object_permission
        return created_object_permission.object_permission_id
    return None


def _remove_budget_fields_from_project_data(project_data: dict) -> dict:
    """
    Remove budget fields from project data.
    Budget fields belong to LiteLLM_BudgetTable, not LiteLLM_ProjectTable.
    Keep budget_id as it's a foreign key.

    Following the pattern from organization_endpoints.py
    """
    budget_fields = LiteLLM_BudgetTable.model_fields.keys()
    for field in list(budget_fields):
        if field != "budget_id":  # Keep the foreign key
            project_data.pop(field, None)
    return project_data


def _remove_project_product_alias_fields(project_data: dict) -> dict:
    # company_id is the product request/response alias for the backing team's
    # organization_id; LiteLLM_ProjectTable does not persist it directly.
    project_data.pop("company_id", None)
    return project_data


def _serialize_project_response(project: Any) -> LiteLLM_ProjectTable:
    if hasattr(project, "model_dump"):
        project_dict = project.model_dump()
    elif hasattr(project, "dict"):
        project_dict = project.dict()
    else:
        project_dict = dict(project)

    team_obj = project_dict.pop("litellm_team_table", None)
    company_id = project_dict.get("company_id")
    if company_id is None and team_obj is not None:
        if isinstance(team_obj, dict):
            company_id = team_obj.get("organization_id")
        else:
            company_id = getattr(team_obj, "organization_id", None)
    if company_id is not None:
        project_dict["company_id"] = company_id

    return LiteLLM_ProjectTable(**project_dict)


@router.post(
    "/project/new",
    tags=["project management"],
    dependencies=[Depends(user_api_key_auth)],
    response_model=NewProjectResponse,
)
@management_endpoint_wrapper
async def new_project(
    data: NewProjectRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    Create a new project. Projects sit between teams and keys in the hierarchy.

    Only proxy admins, team admins, or company admins can create projects.

    # Parameters

    - project_alias: *Optional[str]* - The name of the project.
    - description: *Optional[str]* - Description of the project's purpose and use case.
    - team_id: *str* - The team id that this project belongs to. Required.
    - models: *List* - The models the project has access to.
    - budget_id: *Optional[str]* - The id for a budget (tpm/rpm/max budget) for the project.
    ### IF NO BUDGET ID - CREATE ONE WITH THESE PARAMS ###
    - max_budget: *Optional[float]* - Max budget for project
    - tpm_limit: *Optional[int]* - Max tpm limit for project
    - rpm_limit: *Optional[int]* - Max rpm limit for project
    - max_parallel_requests: *Optional[int]* - Max parallel requests for project
    - soft_budget: *Optional[float]* - Get a slack alert when this soft budget is reached. Don't block requests.
    - model_max_budget: *Optional[dict]* - Max budget for a specific model. Example: {"gpt-4": 100.0, "gpt-3.5-turbo": 50.0}
    - model_rpm_limit: *Optional[dict]* - RPM limits per model. Example: {"gpt-4": 1000, "gpt-3.5-turbo": 5000}
    - model_tpm_limit: *Optional[dict]* - TPM limits per model. Example: {"gpt-4": 50000, "gpt-3.5-turbo": 100000}
    - budget_duration: *Optional[str]* - Frequency of reseting project budget
    - metadata: *Optional[dict]* - Metadata for project, store information for project. Example metadata - {"use_case_id": "SNOW-12345", "responsible_ai_id": "RAI-67890"}
    - tags: *Optional[list]* - Tags for the project. Example: ["production", "api"]
    - blocked: *bool* - Flag indicating if the project is blocked or not - will stop all calls from keys with this project_id.
    - object_permission: Optional[LiteLLM_ObjectPermissionBase] - project-specific object permission. Example - {"vector_stores": ["vector_store_1", "vector_store_2"]}. IF null or {} then no object permission.

    Example 1: Create new project **without** a budget_id, with model-specific limits

    ```bash
    curl --location 'http://0.0.0.0:4000/project/new' \\
    --header 'Authorization: Bearer sk-1234' \\
    --header 'Content-Type: application/json' \\
    --data '{
        "project_alias": "flight-search-assistant",
        "description": "AI-powered flight search and booking assistant",
        "team_id": "team-123",
        "models": ["gpt-4", "gpt-3.5-turbo"],
        "max_budget": 100,
        "model_rpm_limit": {
            "gpt-4": 1000,
            "gpt-3.5-turbo": 5000
        },
        "model_tpm_limit": {
            "gpt-4": 50000,
            "gpt-3.5-turbo": 100000
        },
        "metadata": {
            "use_case_id": "SNOW-12345",
            "responsible_ai_id": "RAI-67890"
        }
    }'
    ```

    Example 2: Create new project **with** a budget_id

    ```bash
    curl --location 'http://0.0.0.0:4000/project/new' \\
    --header 'Authorization: Bearer sk-1234' \\
    --header 'Content-Type: application/json' \\
    --data '{
        "project_alias": "hotel-recommendations",
        "description": "Personalized hotel recommendation engine",
        "team_id": "team-123",
        "models": ["claude-3-sonnet"],
        "budget_id": "428eeaa8-f3ac-4e85-a8fb-7dc8d7aa8689",
        "metadata": {
            "use_case_id": "SNOW-54321"
        }
    }'
    ```
    """
    from litellm.proxy.proxy_server import (
        litellm_proxy_admin_name,
        premium_user,
        prisma_client,
    )

    try:
        if getattr(data, "tags", None) is not None and not premium_user:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Only premium users can add tags to projects. "
                    + CommonProxyErrors.not_premium_user.value
                },
            )

        if not premium_user:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Project management is an enterprise feature. "
                    + CommonProxyErrors.not_premium_user.value
                },
            )

        # ADD METADATA FIELDS
        for field in LiteLLM_ManagementEndpoint_MetadataFields_Premium:
            if getattr(data, field, None) is not None:
                _set_object_metadata_field(
                    object_data=data,
                    field_name=field,
                    value=getattr(data, field),
                )
                delattr(data, field)

        if prisma_client is None:
            raise HTTPException(
                status_code=500,
                detail={"error": CommonProxyErrors.db_not_connected_error.value},
            )

        # Validate team exists and get team object with budget
        team_object = await _validate_team_exists(
            team_id=data.team_id, prisma_client=prisma_client
        )
        _validate_project_company_context(
            requested_company_id=data.company_id,
            team_object=team_object,
        )

        # Validate project limits against team limits
        _check_team_project_limits(
            team_object=LiteLLM_TeamTable(**team_object.model_dump()),
            data=data,
        )

        # Check if user has permission to create projects for this team.
        has_permission = await _check_user_permission_for_project(
            user_api_key_dict=user_api_key_dict,
            team_id=data.team_id,
            prisma_client=prisma_client,
            team_object=LiteLLM_TeamTable(**team_object.model_dump()),
        )

        if not has_permission:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": f"Only proxy admins, team admins, or company admins can create projects. Your role is {user_api_key_dict.user_role}"
                },
            )

        # Generate project_id if not provided
        if data.project_id is None:
            data.project_id = str(uuid.uuid4())
        else:
            # Check if project_id already exists
            existing_project = await prisma_client.db.litellm_projecttable.find_unique(
                where={"project_id": data.project_id}
            )
            if existing_project is not None:
                raise ProxyException(
                    message=f"Project id = {data.project_id} already exists. Please use a different project id.",
                    type="bad_request",
                    code=400,
                    param="project_id",
                )

        # Create budget if not provided
        if data.budget_id is None:
            data.budget_id = await _create_budget_for_project(
                data=data,
                user_id=user_api_key_dict.user_id,
                litellm_proxy_admin_name=litellm_proxy_admin_name,
                prisma_client=prisma_client,
            )

        ## Handle Object Permission - MCP, Vector Stores etc.
        object_permission_id = await _set_project_object_permission(
            data=data,
            prisma_client=prisma_client,
        )

        # Create project row (following organization_endpoints.py pattern)
        project_row = LiteLLM_ProjectTable(
            **data.json(exclude_none=True),
            object_permission_id=object_permission_id,
            created_by=user_api_key_dict.user_id or litellm_proxy_admin_name,
            updated_by=user_api_key_dict.user_id or litellm_proxy_admin_name,
        )

        for field in LiteLLM_ManagementEndpoint_MetadataFields:
            if getattr(data, field, None) is not None:
                _set_object_metadata_field(
                    object_data=project_row,
                    field_name=field,
                    value=getattr(data, field),
                )

        new_project_row = prisma_client.jsonify_object(
            project_row.json(exclude_none=True)
        )

        # Remove budget fields (following organization_endpoints.py pattern)
        new_project_row = _remove_budget_fields_from_project_data(new_project_row)
        new_project_row = _remove_project_product_alias_fields(new_project_row)

        verbose_proxy_logger.info(
            f"new_project_row: {json.dumps(new_project_row, indent=2)}"
        )
        response = await prisma_client.db.litellm_projecttable.create(
            data={
                **new_project_row,  # type: ignore
            },
            include={"litellm_budget_table": True},
        )

        project_response = _serialize_project_response(response)
        project_response.company_id = _team_company_id(team_object)
        return project_response
    except Exception as e:
        verbose_proxy_logger.exception(
            "litellm.proxy.management_endpoints.project_endpoints.new_project(): Exception occured - {}".format(
                str(e)
            )
        )
        raise handle_exception_on_proxy(e)


@router.post(
    "/project/update",
    tags=["project management"],
    dependencies=[Depends(user_api_key_auth)],
    response_model=LiteLLM_ProjectTable,
)
@management_endpoint_wrapper
async def update_project(  # noqa: PLR0915
    data: UpdateProjectRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    Update a project

    Parameters:
    - project_id: *str* - The project id to update. Required.
    - project_alias: *Optional[str]* - Updated name for the project
    - description: *Optional[str]* - Updated description for the project
    - team_id: *Optional[str]* - Updated team_id for the project
    - metadata: *Optional[dict]* - Updated metadata for project
    - models: *Optional[list]* - Updated list of models for the project
    - blocked: *Optional[bool]* - Updated blocked status
    - max_budget: *Optional[float]* - Updated max budget
    - tpm_limit: *Optional[int]* - Updated tpm limit
    - rpm_limit: *Optional[int]* - Updated rpm limit
    - model_rpm_limit: *Optional[dict]* - Updated RPM limits per model
    - model_tpm_limit: *Optional[dict]* - Updated TPM limits per model
    - budget_duration: *Optional[str]* - Updated budget duration
    - tags: *Optional[list]* - Updated list of tags for the project
    - object_permission: Optional[LiteLLM_ObjectPermissionBase] - Updated object permission

    Example:
    ```bash
    curl --location 'http://0.0.0.0:4000/project/update' \\
    --header 'Authorization: Bearer sk-1234' \\
    --header 'Content-Type: application/json' \\
    --data '{
        "project_id": "project-123",
        "description": "Updated flight search system with enhanced capabilities",
        "max_budget": 200,
        "model_rpm_limit": {
            "gpt-4": 2000,
            "gpt-3.5-turbo": 10000
        },
        "metadata": {
            "use_case_id": "SNOW-12345",
            "status": "active"
        }
    }'
    ```
    """
    from litellm.proxy.proxy_server import (
        litellm_proxy_admin_name,
        premium_user,
        prisma_client,
    )

    try:
        if getattr(data, "tags", None) is not None and not premium_user:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Only premium users can add tags to projects. "
                    + CommonProxyErrors.not_premium_user.value
                },
            )

        if not premium_user:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Project management is an enterprise feature. "
                    + CommonProxyErrors.not_premium_user.value
                },
            )

        # ADD METADATA FIELDS
        for field in LiteLLM_ManagementEndpoint_MetadataFields_Premium:
            if getattr(data, field, None) is not None:
                _set_object_metadata_field(
                    object_data=data,
                    field_name=field,
                    value=getattr(data, field),
                )
                delattr(data, field)

        if prisma_client is None:
            raise HTTPException(
                status_code=500,
                detail={"error": CommonProxyErrors.db_not_connected_error.value},
            )

        if data.project_id is None:
            raise HTTPException(
                status_code=400,
                detail={"error": "project_id is required"},
            )

        # Fetch existing project
        existing_project = await prisma_client.db.litellm_projecttable.find_unique(
            where={"project_id": data.project_id}
        )

        if existing_project is None:
            raise ProxyException(
                message=f"Project not found, project_id={data.project_id}",
                type="not_found",
                code=404,
                param="project_id",
            )

        # Permission to *edit* the project must be evaluated against the
        # project's CURRENT team. Sourcing the team from `data.team_id`
        # would let an admin of any team pass the check by supplying their
        # own team_id, hijacking the project (VERIA-55).
        target_team_id = data.team_id or existing_project.team_id
        target_team_obj = None
        if target_team_id is not None:
            target_team_obj = await _validate_team_exists(
                team_id=target_team_id, prisma_client=prisma_client
            )
        _validate_project_company_context(
            requested_company_id=data.company_id,
            team_object=target_team_obj,
        )

        has_permission = await _check_user_permission_for_project(
            user_api_key_dict=user_api_key_dict,
            team_id=existing_project.team_id,
            prisma_client=prisma_client,
        )

        if not has_permission:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Only proxy admins, team admins, or company admins can update projects"
                },
            )

        # Reassigning to a different team also requires admin rights on the
        # destination team — otherwise a team admin could shed projects into
        # an unsuspecting team's namespace.
        if data.team_id is not None and data.team_id != existing_project.team_id:
            can_assign_to_target = await _check_user_permission_for_project(
                user_api_key_dict=user_api_key_dict,
                team_id=data.team_id,
                prisma_client=prisma_client,
                team_object=(
                    LiteLLM_TeamTable(**target_team_obj.model_dump())
                    if target_team_obj
                    else None
                ),
            )
            if not can_assign_to_target:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "Cannot reassign project to a team whose company or team you do not administer"
                    },
                )

        # Validate project limits against team limits
        if target_team_obj is not None:
            _check_team_project_limits(
                team_object=LiteLLM_TeamTable(**target_team_obj.model_dump()),
                data=data,
            )

        # Prepare update data
        update_data = data.json(exclude_none=True, exclude={"project_id"})
        update_data = prisma_client.jsonify_object(update_data)
        update_data["updated_by"] = (
            user_api_key_dict.user_id or litellm_proxy_admin_name
        )

        # Handle budget updates
        budget_fields = LiteLLM_BudgetTable.model_fields.keys()
        budget_updates = {k: v for k, v in update_data.items() if k in budget_fields}

        if budget_updates and existing_project.budget_id:
            # Update existing budget
            await prisma_client.db.litellm_budgettable.update(
                where={"budget_id": existing_project.budget_id},
                data={
                    **budget_updates,
                    "updated_by": user_api_key_dict.user_id or litellm_proxy_admin_name,
                },
            )
            # Remove budget fields from project update
            for field in budget_updates.keys():
                update_data.pop(field, None)

        # Handle object permissions
        if "object_permission" in update_data:
            object_permission_data = update_data.pop("object_permission")
            if object_permission_data:
                if existing_project.object_permission_id:
                    # Update existing permission
                    await prisma_client.db.litellm_objectpermissiontable.update(
                        where={
                            "object_permission_id": existing_project.object_permission_id
                        },
                        data=object_permission_data,
                    )
                else:
                    # Create new permission
                    created_permission = (
                        await prisma_client.db.litellm_objectpermissiontable.create(
                            data=object_permission_data,
                        )
                    )
                    update_data["object_permission_id"] = (
                        created_permission.object_permission_id
                    )

        # Handle metadata fields
        for field in LiteLLM_ManagementEndpoint_MetadataFields:
            if field in update_data:
                if update_data.get("metadata") is None:
                    update_data["metadata"] = {}
                update_data["metadata"][field] = update_data.pop(field)

        # Remove budget fields (following organization_endpoints.py pattern)
        update_data = _remove_budget_fields_from_project_data(update_data)
        update_data = _remove_project_product_alias_fields(update_data)

        # Update project
        updated_project = await prisma_client.db.litellm_projecttable.update(
            where={"project_id": data.project_id},
            data=update_data,
            include={
                "litellm_budget_table": True,
                "object_permission": True,
                "litellm_team_table": True,
            },
        )

        return _serialize_project_response(updated_project)
    except Exception as e:
        verbose_proxy_logger.exception(
            "litellm.proxy.management_endpoints.project_endpoints.update_project(): Exception occured - {}".format(
                str(e)
            )
        )
        raise handle_exception_on_proxy(e)


@router.delete(
    "/project/delete",
    tags=["project management"],
    dependencies=[Depends(user_api_key_auth)],
    response_model=List[LiteLLM_ProjectTable],
)
@management_endpoint_wrapper
async def delete_project(
    data: DeleteProjectRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    Delete projects

    Parameters:
    - project_ids: *List[str]* - List of project ids to delete

    Example:
    ```bash
    curl --location --request DELETE 'http://0.0.0.0:4000/project/delete' \\
    --header 'Authorization: Bearer sk-1234' \\
    --header 'Content-Type: application/json' \\
    --data '{
        "project_ids": ["project-123", "project-456"]
    }'
    ```
    """
    from litellm.proxy.proxy_server import premium_user, prisma_client

    try:
        if not premium_user:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Project management is an enterprise feature. "
                    + CommonProxyErrors.not_premium_user.value
                },
            )

        if prisma_client is None:
            raise HTTPException(
                status_code=500,
                detail={"error": CommonProxyErrors.db_not_connected_error.value},
            )

        # Check if user is admin (only admins can delete projects)
        has_permission = await _check_user_permission_for_project(
            user_api_key_dict=user_api_key_dict,
            team_id=None,
            prisma_client=prisma_client,
            require_admin=True,
        )

        if not has_permission:
            raise HTTPException(
                status_code=403,
                detail={"error": "Only admins can delete projects"},
            )

        deleted_projects = []

        for project_id in data.project_ids:
            # Check if project exists
            existing_project = await prisma_client.db.litellm_projecttable.find_unique(
                where={"project_id": project_id}
            )

            if existing_project is None:
                raise ProxyException(
                    message=f"Project not found, project_id={project_id}",
                    type="not_found",
                    code=404,
                    param="project_ids",
                )

            # Check if there are any keys associated with this project
            associated_keys = (
                await prisma_client.db.litellm_verificationtoken.find_many(
                    where={"project_id": project_id}
                )
            )

            if len(associated_keys) > 0:
                raise ProxyException(
                    message=f"Cannot delete project {project_id}. {len(associated_keys)} key(s) are associated with it. Please delete or reassign the keys first.",
                    type="bad_request",
                    code=400,
                    param="project_ids",
                )

            # Delete the project
            deleted_project = await prisma_client.db.litellm_projecttable.delete(
                where={"project_id": project_id}
            )

            deleted_projects.append(deleted_project)

        return deleted_projects
    except Exception as e:
        verbose_proxy_logger.exception(
            "litellm.proxy.management_endpoints.project_endpoints.delete_project(): Exception occured - {}".format(
                str(e)
            )
        )
        raise handle_exception_on_proxy(e)


def _parse_csv_ids(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def _resolve_csv_filter_alias(
    *,
    single_value: Optional[str],
    plural_value: Optional[str],
    single_name: str,
    plural_name: str,
) -> Optional[str]:
    single_value = single_value.strip() if isinstance(single_value, str) else None
    plural_value = plural_value.strip() if isinstance(plural_value, str) else None
    if single_value and plural_value and single_value != plural_value:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "{} and {} refer to the same filter and must match when both are provided.".format(
                    single_name,
                    plural_name,
                )
            },
        )
    return single_value or plural_value


def _resolve_project_company_filter_alias(
    *,
    company_id: Optional[str],
    company_ids: Optional[str],
    organization_id: Optional[str],
    organization_ids: Optional[str],
) -> Optional[str]:
    company_filter = _resolve_csv_filter_alias(
        single_value=company_id,
        plural_value=company_ids,
        single_name="company_id",
        plural_name="company_ids",
    )
    organization_filter = _resolve_csv_filter_alias(
        single_value=organization_id,
        plural_value=organization_ids,
        single_name="organization_id",
        plural_name="organization_ids",
    )
    if company_filter and organization_filter and company_filter != organization_filter:
        raise HTTPException(
            status_code=400,
            detail={
                "error": (
                    "company_id/company_ids and organization_id/organization_ids "
                    "refer to the same tenant filter and must match when both are provided."
                )
            },
        )
    return company_filter or organization_filter


def _apply_team_id_filter(
    project_where: Dict[str, Any],
    team_ids: List[str],
) -> None:
    effective_team_ids = team_ids or ["__litellm_no_project_team_match__"]
    existing_team_filter = project_where.get("team_id")

    if isinstance(existing_team_filter, dict) and isinstance(
        existing_team_filter.get("in"), list
    ):
        existing_team_ids = set(existing_team_filter["in"])
        effective_team_ids = [
            team_id for team_id in effective_team_ids if team_id in existing_team_ids
        ]
    elif isinstance(existing_team_filter, str):
        effective_team_ids = (
            [existing_team_filter] if existing_team_filter in effective_team_ids else []
        )

    project_where["team_id"] = {
        "in": effective_team_ids or ["__litellm_no_project_team_match__"]
    }


async def _team_ids_for_company_filter(
    *,
    prisma_client: PrismaClient,
    company_ids: Optional[List[str]],
) -> Optional[List[str]]:
    if not company_ids:
        return None

    company_teams = await prisma_client.db.litellm_teamtable.find_many(
        where={"organization_id": {"in": company_ids}}
    )
    return [
        team.team_id
        for team in company_teams
        if getattr(team, "team_id", None) is not None
    ]


def _project_company_id(project: Any) -> Optional[str]:
    company_id = getattr(project, "company_id", None)
    if company_id is not None:
        return company_id

    team_obj = getattr(project, "litellm_team_table", None)
    if team_obj is None:
        return None
    if isinstance(team_obj, dict):
        return team_obj.get("organization_id")
    return getattr(team_obj, "organization_id", None)


def _project_team_table(project: Any) -> Optional[LiteLLM_TeamTable]:
    team_obj = getattr(project, "litellm_team_table", None)
    if team_obj is None:
        return None
    if isinstance(team_obj, LiteLLM_TeamTable):
        return team_obj
    if hasattr(team_obj, "model_dump"):
        return LiteLLM_TeamTable(**team_obj.model_dump())
    if hasattr(team_obj, "dict"):
        return LiteLLM_TeamTable(**team_obj.dict())
    if isinstance(team_obj, dict):
        return LiteLLM_TeamTable(**team_obj)
    return None


def _project_metadata(projects: List[Any]) -> Dict[str, dict]:
    metadata: Dict[str, dict] = {}
    for project in projects:
        project_id = getattr(project, "project_id", None)
        if not project_id:
            continue
        metadata[project_id] = {
            "project_alias": getattr(project, "project_alias", None),
            "company_id": _project_company_id(project),
        }
    return metadata


async def _company_admin_ids_for_user(
    *,
    prisma_client: PrismaClient,
    user_api_key_dict: UserAPIKeyAuth,
) -> List[str]:
    if not user_api_key_dict.user_id:
        return []

    memberships = await prisma_client.db.litellm_organizationmembership.find_many(
        where={
            "user_id": user_api_key_dict.user_id,
            "user_role": LitellmUserRoles.ORG_ADMIN.value,
        }
    )
    return [
        membership.organization_id
        for membership in memberships
        if getattr(membership, "organization_id", None)
    ]


def _unique_non_empty(values: List[Optional[str]]) -> List[str]:
    result: List[str] = []
    seen: set = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _user_can_view_project_daily_activity(
    *,
    project: Any,
    user_team_ids: List[str],
    company_admin_ids: List[str],
) -> bool:
    team_id = getattr(project, "team_id", None)
    if team_id in user_team_ids:
        return True

    company_id = _project_company_id(project)
    return company_id is not None and company_id in company_admin_ids


async def _get_project_user_api_key_filter(
    *,
    prisma_client: PrismaClient,
    user_api_key_dict: UserAPIKeyAuth,
    project_records: List[Any],
    api_key: Optional[str],
    company_admin_ids: Optional[List[str]] = None,
) -> Optional[Union[str, List[str]]]:
    if _user_has_admin_view(user_api_key_dict) or not project_records:
        return api_key

    company_admin_ids = company_admin_ids or []
    has_full_project_view = True
    for project in project_records:
        company_id = _project_company_id(project)
        if company_id is not None and company_id in company_admin_ids:
            continue

        team_obj = _project_team_table(project)
        if team_obj is None:
            has_full_project_view = False
            break

        is_admin = _is_user_team_admin(
            user_api_key_dict=user_api_key_dict,
            team_obj=team_obj,
        )
        has_project_perm = _team_member_has_permission(
            user_api_key_dict=user_api_key_dict,
            team_obj=team_obj,
            permission="/project/daily/activity",
        )
        has_team_perm = _team_member_has_permission(
            user_api_key_dict=user_api_key_dict,
            team_obj=team_obj,
            permission="/team/daily/activity",
        )
        if not (is_admin or has_project_perm or has_team_perm):
            has_full_project_view = False
            break

    if has_full_project_view:
        return api_key

    user_keys = await prisma_client.db.litellm_verificationtoken.find_many(
        where={"user_id": user_api_key_dict.user_id}
    )
    user_api_keys = [key.token for key in user_keys if key.token]
    if not user_api_keys:
        user_api_keys = [""]

    if api_key is not None:
        return api_key if api_key in user_api_keys else [""]
    return user_api_keys


@router.get(
    "/project/daily/activity",
    response_model=SpendAnalyticsPaginatedResponse,
    tags=["project management"],
)
async def get_project_daily_activity(
    project_ids: Optional[str] = Query(
        default=None,
        description="Comma-separated project IDs to include.",
    ),
    project_id: Optional[str] = Query(
        default=None,
        description="Single project ID to include.",
    ),
    company_ids: Optional[str] = Query(
        default=None,
        description="Comma-separated company IDs used to scope visible projects.",
    ),
    company_id: Optional[str] = Query(
        default=None,
        description="Single company ID used to scope visible projects.",
    ),
    organization_ids: Optional[str] = Query(
        default=None,
        description="LiteLLM compatibility alias for company_ids.",
        include_in_schema=False,
    ),
    organization_id: Optional[str] = Query(
        default=None,
        description="LiteLLM compatibility alias for company_id.",
        include_in_schema=False,
    ),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
    exclude_project_ids: Optional[str] = Query(
        default=None,
        description="Comma-separated project IDs to exclude.",
    ),
    exclude_project_id: Optional[str] = Query(
        default=None,
        description="Single project ID to exclude.",
    ),
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    Get daily activity for specific projects or all projects visible to the caller.
    """
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(
            status_code=500,
            detail={"error": CommonProxyErrors.db_not_connected_error.value},
        )

    project_ids = _resolve_csv_filter_alias(
        single_value=project_id,
        plural_value=project_ids,
        single_name="project_id",
        plural_name="project_ids",
    )
    company_ids = _resolve_project_company_filter_alias(
        company_id=company_id,
        company_ids=company_ids,
        organization_id=organization_id,
        organization_ids=organization_ids,
    )
    exclude_project_ids = _resolve_csv_filter_alias(
        single_value=exclude_project_id,
        plural_value=exclude_project_ids,
        single_name="exclude_project_id",
        plural_name="exclude_project_ids",
    )

    project_ids_list = _parse_csv_ids(project_ids)
    company_ids_list = _parse_csv_ids(company_ids)
    exclude_project_ids_list = _parse_csv_ids(exclude_project_ids)
    is_admin = _user_has_admin_view(user_api_key_dict)

    project_where: dict = {}
    if project_ids_list:
        project_where["project_id"] = {"in": project_ids_list}

    company_team_ids = await _team_ids_for_company_filter(
        prisma_client=prisma_client,
        company_ids=company_ids_list,
    )
    if company_team_ids is not None:
        _apply_team_id_filter(project_where, company_team_ids)

    if not is_admin:
        caller_user_id = require_caller_user_id_for_non_admin(user_api_key_dict)
        user_record = await prisma_client.db.litellm_usertable.find_unique(
            where={"user_id": caller_user_id}
        )
        if user_record is None:
            raise HTTPException(
                status_code=404,
                detail={"error": f"User= {caller_user_id} not found"},
            )

        user_team_ids = user_record.teams or []
        company_admin_ids = await _company_admin_ids_for_user(
            prisma_client=prisma_client,
            user_api_key_dict=user_api_key_dict,
        )
        if project_ids_list is None:
            company_admin_team_ids = await _team_ids_for_company_filter(
                prisma_client=prisma_client,
                company_ids=company_admin_ids,
            )
            visible_team_ids = _unique_non_empty(
                [*user_team_ids, *(company_admin_team_ids or [])]
            )
            _apply_team_id_filter(project_where, visible_team_ids)
    else:
        company_admin_ids = []

    project_records = await prisma_client.db.litellm_projecttable.find_many(
        where=project_where,
        include={"litellm_team_table": True},
    )

    if not is_admin:
        user_team_ids = user_record.teams or []  # type: ignore[name-defined]
        if project_ids_list is None:
            project_ids_list = [
                project.project_id for project in project_records if project.project_id
            ]
        else:
            found_project_ids = {
                project.project_id for project in project_records if project.project_id
            }
            missing_project_ids = set(project_ids_list) - found_project_ids
            if missing_project_ids:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "error": "Project not found: {}".format(
                            ", ".join(sorted(missing_project_ids))
                        )
                    },
                )
            for project in project_records:
                if not _user_can_view_project_daily_activity(
                    project=project,
                    user_team_ids=user_team_ids,
                    company_admin_ids=company_admin_ids,
                ):
                    raise HTTPException(
                        status_code=403,
                        detail={
                            "error": "User does not belong to Project= {}.".format(
                                project.project_id
                            )
                        },
                    )

    final_api_key_filter = await _get_project_user_api_key_filter(
        prisma_client=prisma_client,
        user_api_key_dict=user_api_key_dict,
        project_records=project_records,
        api_key=api_key,
        company_admin_ids=company_admin_ids,
    )

    return await get_daily_activity(
        prisma_client=prisma_client,
        table_name="litellm_dailyprojectspend",
        entity_id_field="project_id",
        entity_id=project_ids_list,
        entity_metadata_field=_project_metadata(project_records),
        exclude_entity_ids=exclude_project_ids_list,
        start_date=start_date,
        end_date=end_date,
        model=model,
        api_key=final_api_key_filter,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/project/info",
    tags=["project management"],
    dependencies=[Depends(user_api_key_auth)],
    response_model=LiteLLM_ProjectTable,
)
async def project_info(
    project_id: str,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    Get information about a specific project

    Parameters:
    - project_id: *str* - The project id to fetch info for

    Example:
    ```bash
    curl --location 'http://0.0.0.0:4000/project/info?project_id=project-123' \\
    --header 'Authorization: Bearer sk-1234'
    ```
    """
    from litellm.proxy.proxy_server import prisma_client

    try:
        if prisma_client is None:
            raise HTTPException(
                status_code=500,
                detail={"error": CommonProxyErrors.db_not_connected_error.value},
            )

        # Fetch project
        project = await prisma_client.db.litellm_projecttable.find_unique(
            where={"project_id": project_id},
            include={
                "litellm_budget_table": True,
                "object_permission": True,
                "litellm_team_table": True,
            },
        )

        if project is None:
            raise ProxyException(
                message=f"Project not found, project_id={project_id}",
                type="not_found",
                code=404,
                param="project_id",
            )

        if not await _user_can_read_project(
            prisma_client=prisma_client,
            user_api_key_dict=user_api_key_dict,
            project=project,
        ):
            raise HTTPException(
                status_code=403,
                detail={"error": "You don't have access to this project"},
            )

        return _serialize_project_response(project)
    except Exception as e:
        verbose_proxy_logger.exception(
            "litellm.proxy.management_endpoints.project_endpoints.project_info(): Exception occured - {}".format(
                str(e)
            )
        )
        raise handle_exception_on_proxy(e)


@router.get(
    "/project/list",
    tags=["project management"],
    dependencies=[Depends(user_api_key_auth)],
    response_model=List[LiteLLM_ProjectTable],
)
async def list_projects(
    company_ids: Optional[str] = Query(
        default=None,
        description="Comma-separated company IDs used to scope visible Projects.",
    ),
    company_id: Optional[str] = Query(
        default=None,
        description="Single company ID used to scope visible Projects.",
    ),
    organization_ids: Optional[str] = Query(
        default=None,
        description="LiteLLM compatibility alias for company_ids.",
        include_in_schema=False,
    ),
    organization_id: Optional[str] = Query(
        default=None,
        description="LiteLLM compatibility alias for company_id.",
        include_in_schema=False,
    ),
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    List all projects that the user has access to

    Example:
    ```bash
    curl --location 'http://0.0.0.0:4000/project/list' \\
    --header 'Authorization: Bearer sk-1234'
    ```
    """
    from litellm.proxy.proxy_server import prisma_client

    try:
        if prisma_client is None:
            raise HTTPException(
                status_code=500,
                detail={"error": CommonProxyErrors.db_not_connected_error.value},
            )

        company_ids = _resolve_project_company_filter_alias(
            company_id=company_id,
            company_ids=company_ids,
            organization_id=organization_id,
            organization_ids=organization_ids,
        )
        company_ids_list = _parse_csv_ids(company_ids)
        requested_company_team_ids = await _team_ids_for_company_filter(
            prisma_client=prisma_client,
            company_ids=company_ids_list,
        )

        # If proxy admin or proxy-admin-viewer, get all projects.
        if _user_has_admin_view(user_api_key_dict):
            project_where: Dict[str, Any] = {}
            if requested_company_team_ids is not None:
                _apply_team_id_filter(project_where, requested_company_team_ids)
            projects = await prisma_client.db.litellm_projecttable.find_many(
                where=project_where,
                include={
                    "litellm_budget_table": True,
                    "object_permission": True,
                    "litellm_team_table": True,
                },
            )
        else:
            # Look up the user's team memberships via the reverse-index on
            # LiteLLM_UserTable.teams (maintained by team_member_add alongside
            # members_with_roles). This avoids a full scan of all team rows.
            user_record = await prisma_client.db.litellm_usertable.find_unique(
                where={"user_id": user_api_key_dict.user_id},
            )
            user_team_ids = (
                user_record.teams
                if user_record is not None and user_record.teams
                else []
            )
            company_admin_ids = await _company_admin_ids_for_user(
                prisma_client=prisma_client,
                user_api_key_dict=user_api_key_dict,
            )
            company_team_ids = await _team_ids_for_company_filter(
                prisma_client=prisma_client,
                company_ids=company_admin_ids,
            )
            visible_team_ids = _unique_non_empty(
                [*user_team_ids, *(company_team_ids or [])]
            )
            project_where: Dict[str, Any] = {}
            _apply_team_id_filter(project_where, visible_team_ids)
            if requested_company_team_ids is not None:
                _apply_team_id_filter(project_where, requested_company_team_ids)

            projects = await prisma_client.db.litellm_projecttable.find_many(
                where=project_where,
                include={
                    "litellm_budget_table": True,
                    "object_permission": True,
                    "litellm_team_table": True,
                },
            )

        return [_serialize_project_response(project) for project in projects]
    except Exception as e:
        verbose_proxy_logger.exception(
            "litellm.proxy.management_endpoints.project_endpoints.list_projects(): Exception occured - {}".format(
                str(e)
            )
        )
        raise handle_exception_on_proxy(e)
