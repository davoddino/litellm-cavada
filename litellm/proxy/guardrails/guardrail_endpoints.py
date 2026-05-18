"""
CRUD ENDPOINTS FOR GUARDRAILS
"""

import concurrent.futures
import inspect
import json
import os
from datetime import datetime, timezone
from typing import (
    Annotated,
    Any,
    Dict,
    List,
    Literal,
    Optional,
    Set,
    Type,
    TypeVar,
    Union,
    cast,
)
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from litellm.proxy.common_utils.path_utils import safe_join

from litellm._logging import verbose_proxy_logger
from litellm.constants import DEFAULT_MAX_RECURSE_DEPTH
from litellm.integrations.custom_guardrail import CustomGuardrail
from litellm.litellm_core_utils.safe_json_dumps import safe_dumps
from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.auth.user_api_key_auth import user_api_key_auth
from litellm.proxy.management_endpoints.common_utils import _user_has_admin_view
from litellm.proxy.guardrails.guardrail_hooks.custom_code.sandbox import (
    build_sandbox_globals,
    compile_sandboxed,
)
from litellm.proxy.guardrails.guardrail_registry import GuardrailRegistry
from litellm.proxy.guardrails.usage_endpoints import router as guardrails_usage_router
from litellm.types.guardrails import (
    PII_ENTITY_CATEGORIES_MAP,
    ApplyGuardrailRequest,
    ApplyGuardrailResponse,
    BaseLitellmParams,
    BedrockGuardrailConfigModel,
    Guardrail,
    GuardrailEventHooks,
    GuardrailInfoResponse,
    GuardrailUIAddGuardrailSettings,
    LakeraV2GuardrailConfigModel,
    ListGuardrailsResponse,
    LitellmParams,
    PatchGuardrailRequest,
    PiiAction,
    PiiEntityType,
    PresidioPresidioConfigModelUserInterface,
    SupportedGuardrailIntegrations,
    ToolPermissionGuardrailConfigModel,
)

#### GUARDRAILS ENDPOINTS ####

router = APIRouter()
GUARDRAIL_REGISTRY = GuardrailRegistry()


def _get_guardrails_list_response(
    guardrails_config: List[Dict],
) -> ListGuardrailsResponse:
    """
    Helper function to get the guardrails list response
    """
    from litellm.litellm_core_utils.litellm_logging import _get_masked_values

    guardrail_configs: List[GuardrailInfoResponse] = []
    for guardrail in guardrails_config:
        litellm_params = guardrail.get("litellm_params") or {}
        masked_params = _get_masked_values(
            litellm_params,
            unmasked_length=4,
            number_of_asterisks=4,
        )
        guardrail_configs.append(
            GuardrailInfoResponse(
                guardrail_name=guardrail.get("guardrail_name"),
                litellm_params=masked_params,
                guardrail_info=guardrail.get("guardrail_info"),
            )
        )
    return ListGuardrailsResponse(guardrails=guardrail_configs)


def _get_field_value(value: Any, field_name: str) -> Any:
    if isinstance(value, dict):
        return value.get(field_name)
    return getattr(value, field_name, None)


def _get_string_field_value(value: Any, field_name: str) -> Optional[str]:
    field_value = _get_field_value(value, field_name)
    return field_value if isinstance(field_value, str) and field_value else None


def _resolve_company_filter_alias(
    *,
    company_id: Optional[str],
    organization_id: Optional[str],
) -> Optional[str]:
    if company_id and organization_id and company_id != organization_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "Conflicting Company filters were provided. "
                "Use company_id for product requests."
            ),
        )
    return company_id or organization_id


def _unique_non_empty(values: List[Optional[str]]) -> List[str]:
    result: List[str] = []
    seen: Set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


async def _company_admin_ids_for_guardrail_user(
    *,
    prisma_client: Any,
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
    return _unique_non_empty(
        [
            _get_field_value(membership, "organization_id")
            for membership in memberships
        ]
    )


async def _team_ids_for_company_ids(
    *,
    prisma_client: Any,
    company_ids: List[str],
) -> List[str]:
    if not company_ids:
        return []

    where: Dict[str, Any]
    if len(company_ids) == 1:
        where = {"organization_id": company_ids[0]}
    else:
        where = {"organization_id": {"in": company_ids}}
    teams = await prisma_client.db.litellm_teamtable.find_many(where=where)
    return _unique_non_empty([_get_field_value(team, "team_id") for team in teams])


async def _project_guardrail_scope(
    *,
    prisma_client: Any,
    project_id: str,
) -> tuple[Optional[str], Optional[str]]:
    project = await prisma_client.db.litellm_projecttable.find_unique(
        where={"project_id": project_id},
        include={"litellm_team_table": True},
    )
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    team_id = _get_field_value(project, "team_id")
    team_obj = _get_field_value(project, "litellm_team_table")
    company_id = _get_field_value(project, "company_id")
    if company_id is None and team_obj is not None:
        company_id = _get_field_value(team_obj, "organization_id")
    if company_id is None and team_id:
        team_obj = await prisma_client.db.litellm_teamtable.find_unique(
            where={"team_id": team_id}
        )
        company_id = _get_field_value(team_obj, "organization_id")

    return team_id, company_id


async def _team_company_id(
    *,
    prisma_client: Any,
    team_id: Optional[str],
) -> Optional[str]:
    if not team_id:
        return None

    team = await prisma_client.db.litellm_teamtable.find_unique(
        where={"team_id": team_id}
    )
    return _get_field_value(team, "organization_id")


async def _resolve_guardrail_registration_scope(
    *,
    prisma_client: Any,
    request: "RegisterGuardrailRequest",
    user_api_key_dict: UserAPIKeyAuth,
) -> tuple[str, Optional[str], Optional[str]]:
    company_id = request.company_id
    project_id = request.project_id
    team_id = request.team_id or user_api_key_dict.team_id

    if project_id:
        project_team_id, project_company_id = await _project_guardrail_scope(
            prisma_client=prisma_client,
            project_id=project_id,
        )
        if (
            company_id is not None
            and project_company_id is not None
            and company_id != project_company_id
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"project_id={project_id} belongs to company_id={project_company_id}; "
                    f"received company_id={company_id}"
                ),
            )
        if team_id and project_team_id and team_id != project_team_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"project_id={project_id} is backed by team_id={project_team_id}; "
                    f"received team_id={team_id}"
                ),
            )
        team_id = project_team_id or team_id
        company_id = company_id or project_company_id
    elif company_id and team_id:
        team_company_id = await _team_company_id(
            prisma_client=prisma_client,
            team_id=team_id,
        )
        if team_company_id and team_company_id != company_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"team_id={team_id} belongs to company_id={team_company_id}; "
                    f"received company_id={company_id}"
                ),
            )

    if not team_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "project_id is required for Company/Project guardrail submissions. "
                "Legacy team-scoped requests must provide team_id or use a team-scoped API key."
            ),
        )

    if user_api_key_dict.user_role == LitellmUserRoles.PROXY_ADMIN:
        return team_id, company_id, project_id

    if company_id:
        company_admin_ids = set(
            await _company_admin_ids_for_guardrail_user(
                prisma_client=prisma_client,
                user_api_key_dict=user_api_key_dict,
            )
        )
        if company_id in company_admin_ids:
            return team_id, company_id, project_id

    if team_id != user_api_key_dict.team_id:
        user_team_ids = await _get_user_team_ids(user_api_key_dict)
        if team_id not in user_team_ids:
            raise HTTPException(
                status_code=403,
                detail=f"You are not authorized to submit guardrails for Project team {team_id!r}",
            )

    return team_id, company_id, project_id


async def _guardrail_scope_team_ids(
    *,
    prisma_client: Any,
    user_api_key_dict: UserAPIKeyAuth,
    company_id: Optional[str],
    project_id: Optional[str],
) -> Optional[Set[str]]:
    requested_team_ids: Optional[Set[str]] = None
    requested_company_id = company_id
    project_team_id: Optional[str] = None
    project_company_id: Optional[str] = None

    if project_id:
        project_team_id, project_company_id = await _project_guardrail_scope(
            prisma_client=prisma_client,
            project_id=project_id,
        )
        if (
            company_id is not None
            and project_company_id is not None
            and company_id != project_company_id
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"project_id={project_id} belongs to company_id={project_company_id}; "
                    f"received company_id={company_id}"
                ),
            )
        requested_company_id = company_id or project_company_id
        requested_team_ids = {project_team_id} if project_team_id else set()
    elif company_id:
        requested_team_ids = set(
            await _team_ids_for_company_ids(
                prisma_client=prisma_client,
                company_ids=[company_id],
            )
        )

    if _user_has_admin_view(user_api_key_dict):
        return requested_team_ids

    caller_team_ids = set(await _get_user_team_ids(user_api_key_dict))
    if user_api_key_dict.team_id:
        caller_team_ids.add(user_api_key_dict.team_id)

    company_admin_ids = set(
        await _company_admin_ids_for_guardrail_user(
            prisma_client=prisma_client,
            user_api_key_dict=user_api_key_dict,
        )
    )

    if project_id:
        if project_company_id in company_admin_ids or project_team_id in caller_team_ids:
            return requested_team_ids
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to list guardrails for this Project",
        )

    if requested_company_id:
        if requested_company_id in company_admin_ids:
            return requested_team_ids

        visible_requested_team_ids = (requested_team_ids or set()) & caller_team_ids
        if visible_requested_team_ids:
            return visible_requested_team_ids
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to list guardrails for this Company",
        )

    company_admin_team_ids = set(
        await _team_ids_for_company_ids(
            prisma_client=prisma_client,
            company_ids=list(company_admin_ids),
        )
    )
    return caller_team_ids | company_admin_team_ids


def _filter_guardrails_for_team_scope(
    guardrails: List[Any],
    team_ids: Optional[Set[str]],
) -> tuple[List[Any], Set[str]]:
    if team_ids is None:
        return guardrails, set()

    allowed: List[Any] = []
    excluded_guardrail_ids: Set[str] = set()
    for guardrail in guardrails:
        guardrail_team_id = _get_field_value(guardrail, "team_id")
        if guardrail_team_id is None or guardrail_team_id in team_ids:
            allowed.append(guardrail)
            continue

        guardrail_id = _get_field_value(guardrail, "guardrail_id")
        if guardrail_id:
            excluded_guardrail_ids.add(guardrail_id)
    return allowed, excluded_guardrail_ids


@router.get(
    "/guardrails/list",
    tags=["Guardrails"],
    dependencies=[Depends(user_api_key_auth)],
    response_model=ListGuardrailsResponse,
)
async def list_guardrails():
    """
    List the guardrails that are available on the proxy server

    👉 [Guardrail docs](https://docs.litellm.ai/docs/proxy/guardrails/quick_start)

    Example Request:
    ```bash
    curl -X GET "http://localhost:4000/guardrails/list" -H "Authorization: Bearer <your_api_key>"
    ```

    Example Response:
    ```json
    {
        "guardrails": [
            {
            "guardrail_name": "bedrock-pre-guard",
            "guardrail_info": {
                "params": [
                {
                    "name": "toxicity_score",
                    "type": "float",
                    "description": "Score between 0-1 indicating content toxicity level"
                },
                {
                    "name": "pii_detection",
                    "type": "boolean"
                }
                ]
            }
            }
        ]
    }
    ```
    """
    from litellm.proxy.proxy_server import proxy_config

    config = proxy_config.config

    _guardrails_config = cast(Optional[list[dict]], config.get("guardrails"))

    if _guardrails_config is None:
        return _get_guardrails_list_response([])

    return _get_guardrails_list_response(_guardrails_config)


@router.get(
    "/v2/guardrails/list",
    tags=["Guardrails"],
    response_model=ListGuardrailsResponse,
)
async def list_guardrails_v2(
    company_id: Optional[str] = None,
    project_id: Optional[str] = None,
    organization_id: Annotated[Optional[str], Query(include_in_schema=False)] = None,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    List the guardrails that are available in the database using GuardrailRegistry

    👉 [Guardrail docs](https://docs.litellm.ai/docs/proxy/guardrails/quick_start)

    Example Request:
    ```bash
    curl -X GET "http://localhost:4000/v2/guardrails/list" -H "Authorization: Bearer <your_api_key>"
    ```

    Example Response:
    ```json
    {
        "guardrails": [
            {
                "guardrail_id": "123e4567-e89b-12d3-a456-426614174000",
                "guardrail_name": "my-bedrock-guard",
                "litellm_params": {
                    "guardrail": "bedrock",
                    "mode": "pre_call",
                    "guardrailIdentifier": "ff6ujrregl1q",
                    "guardrailVersion": "DRAFT",
                    "default_on": true
                },
                "guardrail_info": {
                    "description": "Bedrock content moderation guardrail"
                }
            }
        ]
    }
    ```
    """
    from litellm.litellm_core_utils.litellm_logging import _get_masked_values
    from litellm.proxy.guardrails.guardrail_registry import IN_MEMORY_GUARDRAIL_HANDLER
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Prisma client not initialized")

    company_id = _resolve_company_filter_alias(
        company_id=company_id,
        organization_id=organization_id,
    )
    guardrail_scope_team_ids = await _guardrail_scope_team_ids(
        prisma_client=prisma_client,
        user_api_key_dict=user_api_key_dict,
        company_id=company_id,
        project_id=project_id,
    )

    try:
        guardrails = await GUARDRAIL_REGISTRY.get_all_guardrails_from_db(
            prisma_client=prisma_client
        )

        guardrails, excluded_guardrail_ids = _filter_guardrails_for_team_scope(
            guardrails=guardrails,
            team_ids=guardrail_scope_team_ids,
        )

        guardrail_configs: List[GuardrailInfoResponse] = []
        seen_guardrail_ids: set = excluded_guardrail_ids.copy()
        for guardrail in guardrails:
            litellm_params: Optional[Union[LitellmParams, dict]] = guardrail.get(
                "litellm_params"
            )
            litellm_params_dict = (
                litellm_params.model_dump(exclude_none=True)
                if isinstance(litellm_params, LitellmParams)
                else litellm_params
            ) or {}
            masked_litellm_params_dict = _get_masked_values(
                litellm_params_dict,
                unmasked_length=4,
                number_of_asterisks=4,
            )
            masked_litellm_params = (
                BaseLitellmParams(**masked_litellm_params_dict)
                if masked_litellm_params_dict
                else None
            )
            guardrail_configs.append(
                GuardrailInfoResponse(
                    guardrail_id=guardrail.get("guardrail_id"),
                    guardrail_name=guardrail.get("guardrail_name"),
                    litellm_params=masked_litellm_params,
                    guardrail_info=guardrail.get("guardrail_info"),
                    created_at=guardrail.get("created_at"),
                    updated_at=guardrail.get("updated_at"),
                    guardrail_definition_location="db",
                )
            )
            seen_guardrail_ids.add(guardrail.get("guardrail_id"))

        # get guardrails initialized on litellm config.yaml
        in_memory_guardrails = IN_MEMORY_GUARDRAIL_HANDLER.list_in_memory_guardrails()
        for guardrail in in_memory_guardrails:
            gid = guardrail.get("guardrail_id")
            if gid in seen_guardrail_ids:
                continue
            # Skip stale DB-backed entries — the DB row was deleted (likely by
            # another pod) and reconciliation hasn't fired yet on this pod.
            if gid is not None and IN_MEMORY_GUARDRAIL_HANDLER.get_source(gid) == "db":
                continue
            if guardrail_scope_team_ids is not None:
                g_team_id = guardrail.get("team_id")
                if g_team_id is not None and g_team_id not in guardrail_scope_team_ids:
                    continue
            in_memory_litellm_params_raw = guardrail.get("litellm_params")
            in_memory_litellm_params_dict = (
                in_memory_litellm_params_raw.model_dump(exclude_none=True)
                if isinstance(in_memory_litellm_params_raw, LitellmParams)
                else in_memory_litellm_params_raw
            ) or {}
            masked_in_memory_litellm_params = _get_masked_values(
                in_memory_litellm_params_dict,
                unmasked_length=4,
                number_of_asterisks=4,
            )
            masked_in_memory_litellm_params_typed = (
                BaseLitellmParams(**masked_in_memory_litellm_params)
                if masked_in_memory_litellm_params
                else None
            )
            guardrail_configs.append(
                GuardrailInfoResponse(
                    guardrail_id=guardrail.get("guardrail_id"),
                    guardrail_name=guardrail.get("guardrail_name"),
                    litellm_params=masked_in_memory_litellm_params_typed,
                    guardrail_info=dict(guardrail.get("guardrail_info") or {}),
                    guardrail_definition_location="config",
                )
            )
            seen_guardrail_ids.add(gid)

        return ListGuardrailsResponse(guardrails=guardrail_configs)
    except Exception as e:
        verbose_proxy_logger.exception(f"Error getting guardrails from db: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class CreateGuardrailRequest(BaseModel):
    guardrail: Guardrail


@router.post(
    "/guardrails",
    tags=["Guardrails"],
)
async def create_guardrail(
    request: CreateGuardrailRequest,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    Create a new guardrail

    👉 [Guardrail docs](https://docs.litellm.ai/docs/proxy/guardrails/quick_start)

    Example Request:
    ```bash
    curl -X POST "http://localhost:4000/guardrails" \\
        -H "Authorization: Bearer <your_api_key>" \\
        -H "Content-Type: application/json" \\
        -d '{
            "guardrail": {
                "guardrail_name": "my-bedrock-guard",
                "litellm_params": {
                    "guardrail": "bedrock",
                    "mode": "pre_call",
                    "guardrailIdentifier": "ff6ujrregl1q",
                    "guardrailVersion": "DRAFT",
                    "default_on": true
                },
                "guardrail_info": {
                    "description": "Bedrock content moderation guardrail"
                }
            }
        }'
    ```

    Example Response:
    ```json
    {
        "guardrail_id": "123e4567-e89b-12d3-a456-426614174000",
        "guardrail_name": "my-bedrock-guard",
        "litellm_params": {
            "guardrail": "bedrock",
            "mode": "pre_call",
            "guardrailIdentifier": "ff6ujrregl1q",
            "guardrailVersion": "DRAFT",
            "default_on": true
        },
        "guardrail_info": {
            "description": "Bedrock content moderation guardrail"
        },
        "created_at": "2023-11-09T12:34:56.789Z",
        "updated_at": "2023-11-09T12:34:56.789Z"
    }
    ```
    """
    from litellm.proxy.guardrails.guardrail_registry import IN_MEMORY_GUARDRAIL_HANDLER
    from litellm.proxy.proxy_server import prisma_client

    if user_api_key_dict.user_role != LitellmUserRoles.PROXY_ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Admin access required to manage guardrails",
        )

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Prisma client not initialized")

    try:
        result = await GUARDRAIL_REGISTRY.add_guardrail_to_db(
            guardrail=request.guardrail, prisma_client=prisma_client
        )

        guardrail_name = result.get("guardrail_name", "Unknown")
        guardrail_id = result.get("guardrail_id", "Unknown")

        try:
            IN_MEMORY_GUARDRAIL_HANDLER.initialize_guardrail(
                guardrail=cast(Guardrail, result), source="db"
            )
            verbose_proxy_logger.info(
                f"Immediate sync: Successfully initialized guardrail '{guardrail_name}' (ID: {guardrail_id})"
            )
        except (ValueError, TypeError) as init_error:
            # Configuration error — roll back the DB write so the guardrail isn't orphaned
            if prisma_client is not None:
                try:
                    await prisma_client.db.litellm_guardrailstable.delete(
                        where={"guardrail_id": guardrail_id}
                    )
                except Exception as rollback_err:
                    verbose_proxy_logger.warning(
                        f"Rollback failed for guardrail '{guardrail_id}': {rollback_err}"
                    )
            raise HTTPException(
                status_code=400,
                detail=f"Guardrail configuration error: {init_error}",
            )
        except Exception as init_error:
            verbose_proxy_logger.warning(
                f"Immediate sync: Failed to initialize guardrail '{guardrail_name}' (ID: {guardrail_id}) in memory: {init_error}"
            )

        return result
    except Exception as e:
        verbose_proxy_logger.exception(f"Error adding guardrail to db: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class UpdateGuardrailRequest(BaseModel):
    guardrail: Guardrail


@router.put(
    "/guardrails/{guardrail_id}",
    tags=["Guardrails"],
)
async def update_guardrail(
    guardrail_id: str,
    request: UpdateGuardrailRequest,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    Update an existing guardrail

    👉 [Guardrail docs](https://docs.litellm.ai/docs/proxy/guardrails/quick_start)

    Example Request:
    ```bash
    curl -X PUT "http://localhost:4000/guardrails/123e4567-e89b-12d3-a456-426614174000" \\
        -H "Authorization: Bearer <your_api_key>" \\
        -H "Content-Type: application/json" \\
        -d '{
            "guardrail": {
                "guardrail_name": "updated-bedrock-guard",
                "litellm_params": {
                    "guardrail": "bedrock",
                    "mode": "pre_call",
                    "guardrailIdentifier": "ff6ujrregl1q",
                    "guardrailVersion": "1.0",
                    "default_on": true
                },
                "guardrail_info": {
                    "description": "Updated Bedrock content moderation guardrail"
                }
            }
        }'
    ```

    Example Response:
    ```json
    {
        "guardrail_id": "123e4567-e89b-12d3-a456-426614174000",
        "guardrail_name": "updated-bedrock-guard",
        "litellm_params": {
            "guardrail": "bedrock",
            "mode": "pre_call",
            "guardrailIdentifier": "ff6ujrregl1q",
            "guardrailVersion": "1.0",
            "default_on": true
        },
        "guardrail_info": {
            "description": "Updated Bedrock content moderation guardrail"
        },
        "created_at": "2023-11-09T12:34:56.789Z",
        "updated_at": "2023-11-09T13:45:12.345Z"
    }
    ```
    """
    from litellm.proxy.guardrails.guardrail_registry import IN_MEMORY_GUARDRAIL_HANDLER
    from litellm.proxy.proxy_server import prisma_client

    if user_api_key_dict.user_role != LitellmUserRoles.PROXY_ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Admin access required to manage guardrails",
        )

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Prisma client not initialized")

    try:
        # Check if guardrail exists
        existing_guardrail = await GUARDRAIL_REGISTRY.get_guardrail_by_id_from_db(
            guardrail_id=guardrail_id, prisma_client=prisma_client
        )

        if existing_guardrail is None:
            raise HTTPException(
                status_code=404, detail=f"Guardrail with ID {guardrail_id} not found"
            )

        result = await GUARDRAIL_REGISTRY.update_guardrail_in_db(
            guardrail_id=guardrail_id,
            guardrail=request.guardrail,
            prisma_client=prisma_client,
        )

        guardrail_name = result.get("guardrail_name", "Unknown")

        try:
            IN_MEMORY_GUARDRAIL_HANDLER.update_in_memory_guardrail(
                guardrail_id=guardrail_id, guardrail=cast(Guardrail, result)
            )
            verbose_proxy_logger.info(
                f"Immediate sync: Successfully updated guardrail '{guardrail_name}' (ID: {guardrail_id})"
            )
        except Exception as update_error:
            verbose_proxy_logger.warning(
                f"Immediate sync: Failed to update '{guardrail_name}' (ID: {guardrail_id}) in memory: {update_error}"
            )

        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/guardrails/{guardrail_id}",
    tags=["Guardrails"],
)
async def delete_guardrail(
    guardrail_id: str,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    Delete a guardrail

    👉 [Guardrail docs](https://docs.litellm.ai/docs/proxy/guardrails/quick_start)

    Example Request:
    ```bash
    curl -X DELETE "http://localhost:4000/guardrails/123e4567-e89b-12d3-a456-426614174000" \\
        -H "Authorization: Bearer <your_api_key>"
    ```

    Example Response:
    ```json
    {
        "message": "Guardrail 123e4567-e89b-12d3-a456-426614174000 deleted successfully"
    }
    ```
    """
    from litellm.proxy.guardrails.guardrail_registry import IN_MEMORY_GUARDRAIL_HANDLER
    from litellm.proxy.proxy_server import prisma_client

    if user_api_key_dict.user_role != LitellmUserRoles.PROXY_ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Admin access required to manage guardrails",
        )

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Prisma client not initialized")

    try:
        # Check if guardrail exists
        existing_guardrail = await GUARDRAIL_REGISTRY.get_guardrail_by_id_from_db(
            guardrail_id=guardrail_id, prisma_client=prisma_client
        )

        if existing_guardrail is None:
            raise HTTPException(
                status_code=404, detail=f"Guardrail with ID {guardrail_id} not found"
            )

        result = await GUARDRAIL_REGISTRY.delete_guardrail_from_db(
            guardrail_id=guardrail_id, prisma_client=prisma_client
        )

        guardrail_name = result.get("guardrail_name", "Unknown")

        try:
            IN_MEMORY_GUARDRAIL_HANDLER.delete_in_memory_guardrail(
                guardrail_id=guardrail_id,
            )
            verbose_proxy_logger.info(
                f"Immediate sync: Successfully removed guardrail '{guardrail_name}' (ID: {guardrail_id}) from memory"
            )
        except Exception as delete_error:
            verbose_proxy_logger.warning(
                f"Immediate sync: Failed to remove guardrail '{guardrail_name}' (ID: {guardrail_id}) from memory: {delete_error}"
            )

        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Team guardrail registration (Generic Guardrail API spec) ---

GENERIC_GUARDRAIL_API = "generic_guardrail_api"


class RegisterGuardrailRequest(BaseModel):
    """Request body for POST /guardrails/register. Follows Generic Guardrail API config."""

    guardrail_name: str
    litellm_params: Dict[
        str, Any
    ]  # guardrail, mode, api_base required; api_key, headers, etc. optional
    guardrail_info: Optional[Dict[str, Any]] = None
    company_id: Optional[str] = None
    project_id: Optional[str] = None
    team_id: Optional[str] = None

    def get_litellm_params_dict(self) -> Dict[str, Any]:
        return dict(self.litellm_params)


class RegisterGuardrailResponse(BaseModel):
    guardrail_id: str
    guardrail_name: str
    status: str
    company_id: Optional[str] = None
    project_id: Optional[str] = None
    submitted_at: Optional[datetime] = None


class GuardrailSubmissionSummary(BaseModel):
    total: int
    pending_review: int
    active: int
    rejected: int


class GuardrailSubmissionItem(BaseModel):
    guardrail_id: str
    guardrail_name: str
    status: str  # pending_review | active | rejected
    company_id: Optional[str] = None
    company_name: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    team_id: Optional[str] = None
    team_guardrail: bool = (
        False  # True when submitted via team (team_id set); use to distinguish team vs regular guardrails
    )
    litellm_params: Optional[Dict[str, Any]] = None
    guardrail_info: Optional[Dict[str, Any]] = None
    submitted_by_user_id: Optional[str] = None
    submitted_by_email: Optional[str] = None
    submitted_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ListGuardrailSubmissionsResponse(BaseModel):
    submissions: List[GuardrailSubmissionItem]
    summary: GuardrailSubmissionSummary


@router.post(
    "/guardrails/register",
    tags=["Guardrails"],
    response_model=RegisterGuardrailResponse,
)
async def register_guardrail(
    request: RegisterGuardrailRequest,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    Register a guardrail for onboarding (team submission).

    Accepts a guardrail config in the
    [Generic Guardrail API](https://docs.litellm.ai/docs/adding_provider/generic_guardrail_api) format.
    The submission is stored with status `pending_review` until an admin approves it.
    """
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Prisma client not initialized")

    team_id, company_id, project_id = await _resolve_guardrail_registration_scope(
        prisma_client=prisma_client,
        request=request,
        user_api_key_dict=user_api_key_dict,
    )

    params = request.get_litellm_params_dict()
    if params.get("guardrail") != GENERIC_GUARDRAIL_API:
        raise HTTPException(
            status_code=400,
            detail=f"Only guardrails with litellm_params.guardrail={GENERIC_GUARDRAIL_API!r} are accepted for registration",
        )
    api_base = params.get("api_base")
    if not api_base:
        raise HTTPException(
            status_code=400,
            detail="litellm_params.api_base is required for generic_guardrail_api",
        )
    parsed = urlparse(api_base)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=400,
            detail="litellm_params.api_base must use http or https scheme",
        )
    if not parsed.hostname:
        raise HTTPException(
            status_code=400,
            detail="litellm_params.api_base must contain a valid hostname",
        )
    mode = params.get("mode")
    if mode is None:
        raise HTTPException(
            status_code=400,
            detail="litellm_params.mode is required (e.g. pre_call, post_call)",
        )

    try:
        existing = await prisma_client.db.litellm_guardrailstable.find_unique(
            where={"guardrail_name": request.guardrail_name}
        )
        if existing is not None:
            raise HTTPException(
                status_code=400,
                detail=f"Guardrail with name {request.guardrail_name!r} already exists",
            )
    except HTTPException:
        raise
    except Exception as e:
        verbose_proxy_logger.exception(
            "Error checking guardrail name uniqueness: %s", e
        )
        raise HTTPException(status_code=500, detail=str(e))

    now = datetime.now(timezone.utc)
    litellm_params_str = safe_dumps(params)
    guardrail_info = dict(request.guardrail_info or {})
    guardrail_info["submitted_by_user_id"] = user_api_key_dict.user_id
    guardrail_info["submitted_by_email"] = user_api_key_dict.user_email
    guardrail_info["team_guardrail"] = (
        True  # Mark as team submission for filtering/display
    )
    guardrail_info_str = safe_dumps(guardrail_info)

    try:
        created = await prisma_client.db.litellm_guardrailstable.create(
            data={
                "guardrail_name": request.guardrail_name,
                "litellm_params": litellm_params_str,
                "guardrail_info": guardrail_info_str,
                "status": "pending_review",
                "team_id": team_id,
                "project_id": project_id,
                "submitted_at": now,
                "created_at": now,
                "updated_at": now,
            }
        )
        return RegisterGuardrailResponse(
            guardrail_id=created.guardrail_id,
            guardrail_name=created.guardrail_name,
            status=created.status,
            company_id=company_id,
            project_id=project_id,
            submitted_at=created.submitted_at,
        )
    except Exception as e:
        verbose_proxy_logger.exception("Error registering guardrail: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _parse_json_field(value: Any) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return None
    return None


async def _get_user_team_ids(user_api_key_dict: UserAPIKeyAuth) -> List[str]:
    """Return the list of team_ids the caller belongs to (empty list if none)."""
    from litellm.proxy.auth.auth_checks import get_user_object
    from litellm.proxy.proxy_server import (
        prisma_client,
        proxy_logging_obj,
        user_api_key_cache,
    )

    if not user_api_key_dict.user_id or prisma_client is None:
        return []
    user_obj = await get_user_object(
        user_id=user_api_key_dict.user_id,
        prisma_client=prisma_client,
        user_api_key_cache=user_api_key_cache,
        user_id_upsert=False,
        parent_otel_span=user_api_key_dict.parent_otel_span,
        proxy_logging_obj=proxy_logging_obj,
    )
    if user_obj is None or not user_obj.teams:
        return []
    return [t for t in user_obj.teams if t]


async def _maybe_await_db_call(call_result: Any) -> Any:
    if inspect.isawaitable(call_result):
        return await call_result
    return None


async def _guardrail_submission_context_by_id(
    *,
    prisma_client: Any,
    rows: List[Any],
) -> Dict[str, Dict[str, Optional[str]]]:
    project_ids = _unique_non_empty(
        [_get_string_field_value(row, "project_id") for row in rows]
    )
    team_ids = _unique_non_empty(
        [_get_string_field_value(row, "team_id") for row in rows]
    )

    projects: List[Any] = []
    if project_ids or team_ids:
        project_where: Dict[str, Any]
        project_filters: List[Dict[str, Any]] = []
        if project_ids:
            project_filters.append({"project_id": {"in": project_ids}})
        if team_ids:
            project_filters.append({"team_id": {"in": team_ids}})
        project_where = (
            project_filters[0]
            if len(project_filters) == 1
            else {"OR": project_filters}
        )
        project_model = getattr(prisma_client.db, "litellm_projecttable", None)
        find_many = getattr(project_model, "find_many", None)
        if callable(find_many):
            projects = (
                await _maybe_await_db_call(
                    find_many(
                        where=project_where,
                        include={"litellm_team_table": True},
                    )
                )
            ) or []

    teams: List[Any] = []
    if team_ids:
        team_model = getattr(prisma_client.db, "litellm_teamtable", None)
        find_many = getattr(team_model, "find_many", None)
        if callable(find_many):
            teams = (
                await _maybe_await_db_call(
                    find_many(where={"team_id": {"in": team_ids}})
                )
            ) or []

    project_by_id = {
        _get_string_field_value(project, "project_id"): project
        for project in projects
        if _get_string_field_value(project, "project_id")
    }
    projects_by_team: Dict[str, List[Any]] = {}
    for project in projects:
        team_id = _get_string_field_value(project, "team_id")
        if team_id:
            projects_by_team.setdefault(team_id, []).append(project)

    company_by_team: Dict[str, str] = {}
    for team in teams:
        team_id = _get_string_field_value(team, "team_id")
        company_id = _get_string_field_value(team, "organization_id")
        if team_id and company_id:
            company_by_team[team_id] = company_id
    for project in projects:
        team_id = _get_string_field_value(project, "team_id")
        team_obj = _get_field_value(project, "litellm_team_table")
        company_id = _get_string_field_value(team_obj, "organization_id")
        if team_id and company_id:
            company_by_team[team_id] = company_id

    company_ids = _unique_non_empty(list(company_by_team.values()))
    company_names: Dict[str, str] = {}
    if company_ids:
        company_model = getattr(prisma_client.db, "litellm_organizationtable", None)
        find_many = getattr(company_model, "find_many", None)
        if callable(find_many):
            companies = (
                await _maybe_await_db_call(
                    find_many(where={"organization_id": {"in": company_ids}})
                )
            ) or []
            for company in companies:
                company_id = _get_string_field_value(company, "organization_id")
                if company_id:
                    company_names[company_id] = (
                        _get_string_field_value(company, "organization_alias")
                        or company_id
                    )

    context: Dict[str, Dict[str, Optional[str]]] = {}
    for row in rows:
        guardrail_id = _get_string_field_value(row, "guardrail_id")
        if not guardrail_id:
            continue

        row_project_id = _get_string_field_value(row, "project_id")
        row_team_id = _get_string_field_value(row, "team_id")
        project = project_by_id.get(row_project_id)
        if project is None and row_team_id:
            team_projects = projects_by_team.get(row_team_id, [])
            if len(team_projects) == 1:
                project = team_projects[0]

        project_id = (
            _get_string_field_value(project, "project_id")
            if project
            else row_project_id
        )
        project_name = (
            _get_string_field_value(project, "project_alias") or project_id
            if project_id
            else None
        )
        project_team_id = (
            _get_string_field_value(project, "team_id") if project else row_team_id
        )
        company_id = company_by_team.get(project_team_id or "")
        context[guardrail_id] = {
            "company_id": company_id,
            "company_name": company_names.get(company_id or "") or company_id,
            "project_id": project_id,
            "project_name": project_name,
        }
    return context


def _row_to_submission_item(
    row: Any,
    context: Optional[Dict[str, Optional[str]]] = None,
) -> GuardrailSubmissionItem:
    from litellm.litellm_core_utils.litellm_logging import _get_masked_values

    context = context or {}
    guardrail_info = _parse_json_field(_get_field_value(row, "guardrail_info")) or {}
    team_id = _get_string_field_value(row, "team_id")
    team_guardrail = team_id is not None
    raw_params = _parse_json_field(_get_field_value(row, "litellm_params")) or {}
    masked_params = _get_masked_values(
        raw_params, unmasked_length=4, number_of_asterisks=4
    )
    return GuardrailSubmissionItem(
        guardrail_id=_get_string_field_value(row, "guardrail_id") or "",
        guardrail_name=_get_string_field_value(row, "guardrail_name") or "",
        status=_get_string_field_value(row, "status") or "active",
        company_id=context.get("company_id"),
        company_name=context.get("company_name"),
        project_id=context.get("project_id")
        or _get_string_field_value(row, "project_id"),
        project_name=context.get("project_name"),
        team_id=team_id,
        team_guardrail=team_guardrail,
        litellm_params=masked_params,
        guardrail_info=guardrail_info,
        submitted_by_user_id=guardrail_info.get("submitted_by_user_id"),
        submitted_by_email=guardrail_info.get("submitted_by_email"),
        submitted_at=_get_field_value(row, "submitted_at"),
        reviewed_at=_get_field_value(row, "reviewed_at"),
        created_at=_get_field_value(row, "created_at"),
        updated_at=_get_field_value(row, "updated_at"),
    )


@router.get(
    "/guardrails/submissions",
    tags=["Guardrails"],
    response_model=ListGuardrailSubmissionsResponse,
)
async def list_guardrail_submissions(
    status: Optional[str] = None,
    team_id: Optional[str] = None,
    company_id: Optional[str] = None,
    project_id: Optional[str] = None,
    organization_id: Annotated[Optional[str], Query(include_in_schema=False)] = None,
    search: Optional[str] = None,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    List team guardrail submissions. Returns only guardrails with a team_id.

    Admins see all submissions. Non-admin users see submissions for teams they are
    a member of.

    Status values: pending_review (team-registered, awaiting approval), active (approved), rejected.

    Optional filters:
    - status: pending_review | active | rejected
    - company_id: filter by Company
    - project_id: filter by Project
    - search: name/description
    """
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Prisma client not initialized")

    company_id = _resolve_company_filter_alias(
        company_id=company_id,
        organization_id=organization_id,
    )

    is_admin = _user_has_admin_view(user_api_key_dict)
    scoped_team_ids: Optional[Set[str]] = None
    if company_id or project_id:
        scoped_team_ids = await _guardrail_scope_team_ids(
            prisma_client=prisma_client,
            user_api_key_dict=user_api_key_dict,
            company_id=company_id,
            project_id=project_id,
        )
    elif not is_admin:
        visible_team_ids = await _get_user_team_ids(user_api_key_dict)
        if user_api_key_dict.team_id:
            visible_team_ids.append(user_api_key_dict.team_id)
        scoped_team_ids = set(visible_team_ids)

    if scoped_team_ids is not None:
        if team_id is not None and (
            not scoped_team_ids or team_id not in scoped_team_ids
        ):
            raise HTTPException(
                status_code=403,
                detail=f"You are not authorized to list guardrails for team {team_id!r}",
            )

    try:
        where_clause: Dict[str, Any] = {"team_id": {"not": None}}
        if scoped_team_ids is not None:
            if not scoped_team_ids:
                # Non-admin with no team memberships: nothing visible.
                return ListGuardrailSubmissionsResponse(
                    submissions=[],
                    summary=GuardrailSubmissionSummary(
                        total=0, pending_review=0, active=0, rejected=0
                    ),
                )
            where_clause["team_id"] = {"in": sorted(scoped_team_ids)}

        # Single query: fetch team guardrails visible to the caller
        all_team_rows = await prisma_client.db.litellm_guardrailstable.find_many(
            where=where_clause,
            order={"created_at": "desc"},
        )

        if project_id:
            all_team_rows = [
                row
                for row in all_team_rows
                if _get_field_value(row, "project_id") == project_id
            ]

        # Derive summary counts from the full result set
        total = len(all_team_rows)
        pending_review = sum(
            1
            for r in all_team_rows
            if (_get_field_value(r, "status") or "active") == "pending_review"
        )
        active_count = sum(
            1
            for r in all_team_rows
            if (_get_field_value(r, "status") or "active") == "active"
        )
        rejected = sum(
            1
            for r in all_team_rows
            if (_get_field_value(r, "status") or "active") == "rejected"
        )

        # Apply filters to get the submissions list
        rows = all_team_rows
        if status:
            rows = [r for r in rows if _get_field_value(r, "status") == status]
        if team_id:
            rows = [
                r for r in rows if _get_string_field_value(r, "team_id") == team_id
            ]
        if search:
            search_lower = search.lower()
            rows = [
                r
                for r in rows
                if search_lower
                in (_get_field_value(r, "guardrail_name") or "").lower()
                or (
                    isinstance(_get_field_value(r, "guardrail_info"), dict)
                    and search_lower
                    in str(
                        (_get_field_value(r, "guardrail_info") or {}).get(
                            "description", ""
                        )
                    ).lower()
                )
                or (
                    isinstance(_get_field_value(r, "guardrail_info"), str)
                    and search_lower
                    in _get_field_value(r, "guardrail_info").lower()
                )
            ]

        context_by_id = await _guardrail_submission_context_by_id(
            prisma_client=prisma_client,
            rows=rows,
        )
        items = [
            _row_to_submission_item(
                r,
                context_by_id.get(_get_field_value(r, "guardrail_id"), {}),
            )
            for r in rows
        ]
        return ListGuardrailSubmissionsResponse(
            submissions=items,
            summary=GuardrailSubmissionSummary(
                total=total,
                pending_review=pending_review,
                active=active_count,
                rejected=rejected,
            ),
        )
    except Exception as e:
        verbose_proxy_logger.exception("Error listing guardrail submissions: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/guardrails/submissions/{guardrail_id}",
    tags=["Guardrails"],
    response_model=GuardrailSubmissionItem,
)
async def get_guardrail_submission(
    guardrail_id: str,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """Get a single guardrail submission by id. Non-admins may only access submissions for teams they belong to."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Prisma client not initialized")

    is_admin = _user_has_admin_view(user_api_key_dict)

    try:
        row = await prisma_client.db.litellm_guardrailstable.find_unique(
            where={"guardrail_id": guardrail_id}
        )
        if row is None:
            raise HTTPException(
                status_code=404, detail="Guardrail submission not found"
            )
        context_by_id = await _guardrail_submission_context_by_id(
            prisma_client=prisma_client,
            rows=[row],
        )
        context = context_by_id.get(_get_field_value(row, "guardrail_id"), {})
        if not is_admin:
            visible_team_ids = await _get_user_team_ids(user_api_key_dict)
            if user_api_key_dict.team_id:
                visible_team_ids.append(user_api_key_dict.team_id)
            row_team_id = _get_field_value(row, "team_id")
            row_company_id = context.get("company_id")
            company_admin_ids: Set[str] = set()
            if row_company_id:
                company_admin_ids = set(
                    await _company_admin_ids_for_guardrail_user(
                        prisma_client=prisma_client,
                        user_api_key_dict=user_api_key_dict,
                    )
                )
            if (
                row_team_id is None
                or (
                    row_team_id not in set(visible_team_ids)
                    and row_company_id not in company_admin_ids
                )
            ):
                raise HTTPException(
                    status_code=403,
                    detail="You are not authorized to access this guardrail submission",
                )
        return _row_to_submission_item(row, context)
    except HTTPException:
        raise
    except Exception as e:
        verbose_proxy_logger.exception("Error getting guardrail submission: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/guardrails/submissions/{guardrail_id}/approve",
    tags=["Guardrails"],
)
async def approve_guardrail_submission(
    guardrail_id: str,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """Approve a pending guardrail submission: set status to active and initialize in memory (admin only)."""
    from litellm.proxy.guardrails.guardrail_registry import IN_MEMORY_GUARDRAIL_HANDLER
    from litellm.proxy.proxy_server import prisma_client

    if user_api_key_dict.user_role != LitellmUserRoles.PROXY_ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Prisma client not initialized")

    try:
        row = await prisma_client.db.litellm_guardrailstable.find_unique(
            where={"guardrail_id": guardrail_id}
        )
        if row is None:
            raise HTTPException(
                status_code=404, detail="Guardrail submission not found"
            )
        if row.status != "pending_review":
            raise HTTPException(
                status_code=400,
                detail=f"Guardrail is not pending review (status={row.status})",
            )

        now = datetime.now(timezone.utc)
        await prisma_client.db.litellm_guardrailstable.update(
            where={"guardrail_id": guardrail_id},
            data={"status": "active", "reviewed_at": now, "updated_at": now},
        )

        litellm_params = _parse_json_field(row.litellm_params)
        guardrail_info = _parse_json_field(row.guardrail_info)
        if not litellm_params:
            raise HTTPException(
                status_code=500,
                detail="Guardrail litellm_params is missing or invalid",
            )
        guardrail_dict = {
            "guardrail_id": row.guardrail_id,
            "guardrail_name": row.guardrail_name,
            "litellm_params": litellm_params,
            "guardrail_info": guardrail_info or {},
            "team_id": row.team_id,
        }
        try:
            IN_MEMORY_GUARDRAIL_HANDLER.initialize_guardrail(
                guardrail=cast(Guardrail, guardrail_dict), source="db"
            )
            verbose_proxy_logger.info(
                "Approved guardrail %s (ID: %s) and initialized in memory",
                row.guardrail_name,
                guardrail_id,
            )
        except Exception as init_err:
            verbose_proxy_logger.warning(
                "Failed to initialize approved guardrail %s in memory: %s",
                guardrail_id,
                init_err,
            )
            return {
                "guardrail_id": guardrail_id,
                "status": "active",
                "message": "Guardrail approved",
                "warning": f"Guardrail was marked active but failed to initialize in memory: {init_err}. "
                "It will be picked up on the next sync cycle.",
            }

        return {
            "guardrail_id": guardrail_id,
            "status": "active",
            "message": "Guardrail approved",
        }
    except HTTPException:
        raise
    except Exception as e:
        verbose_proxy_logger.exception("Error approving guardrail submission: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/guardrails/submissions/{guardrail_id}/reject",
    tags=["Guardrails"],
)
async def reject_guardrail_submission(
    guardrail_id: str,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """Reject a guardrail submission (admin only)."""
    from litellm.proxy.proxy_server import prisma_client

    if user_api_key_dict.user_role != LitellmUserRoles.PROXY_ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Prisma client not initialized")

    try:
        row = await prisma_client.db.litellm_guardrailstable.find_unique(
            where={"guardrail_id": guardrail_id}
        )
        if row is None:
            raise HTTPException(
                status_code=404, detail="Guardrail submission not found"
            )
        if row.status != "pending_review":
            raise HTTPException(
                status_code=400,
                detail=f"Guardrail is not pending review (status={row.status})",
            )

        now = datetime.now(timezone.utc)
        await prisma_client.db.litellm_guardrailstable.update(
            where={"guardrail_id": guardrail_id},
            data={"status": "rejected", "reviewed_at": now, "updated_at": now},
        )
        return {
            "guardrail_id": guardrail_id,
            "status": "rejected",
            "message": "Guardrail rejected",
        }
    except HTTPException:
        raise
    except Exception as e:
        verbose_proxy_logger.exception("Error rejecting guardrail submission: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch(
    "/guardrails/{guardrail_id}",
    tags=["Guardrails"],
)
async def patch_guardrail(
    guardrail_id: str,
    request: PatchGuardrailRequest,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    Partially update an existing guardrail

    👉 [Guardrail docs](https://docs.litellm.ai/docs/proxy/guardrails/quick_start)

    This endpoint allows updating specific fields of a guardrail without sending the entire object.
    Only the following fields can be updated:
    - guardrail_name: The name of the guardrail
    - default_on: Whether the guardrail is enabled by default
    - guardrail_info: Additional information about the guardrail

    Example Request:
    ```bash
    curl -X PATCH "http://localhost:4000/guardrails/123e4567-e89b-12d3-a456-426614174000" \\
        -H "Authorization: Bearer <your_api_key>" \\
        -H "Content-Type: application/json" \\
        -d '{
            "guardrail_name": "updated-name",
            "default_on": true,
            "guardrail_info": {
                "description": "Updated description"
            }
        }'
    ```

    Example Response:
    ```json
    {
        "guardrail_id": "123e4567-e89b-12d3-a456-426614174000",
        "guardrail_name": "updated-name",
        "litellm_params": {
            "guardrail": "bedrock",
            "mode": "pre_call",
            "guardrailIdentifier": "ff6ujrregl1q",
            "guardrailVersion": "DRAFT",
            "default_on": true
        },
        "guardrail_info": {
            "description": "Updated description"
        },
        "created_at": "2023-11-09T12:34:56.789Z",
        "updated_at": "2023-11-09T14:22:33.456Z"
    }
    ```
    """
    from litellm.proxy.guardrails.guardrail_registry import IN_MEMORY_GUARDRAIL_HANDLER
    from litellm.proxy.proxy_server import prisma_client

    if user_api_key_dict.user_role != LitellmUserRoles.PROXY_ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Admin access required to manage guardrails",
        )

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Prisma client not initialized")

    try:
        # Check if guardrail exists and get current data
        existing_guardrail = await GUARDRAIL_REGISTRY.get_guardrail_by_id_from_db(
            guardrail_id=guardrail_id, prisma_client=prisma_client
        )

        if existing_guardrail is None:
            raise HTTPException(
                status_code=404, detail=f"Guardrail with ID {guardrail_id} not found"
            )

        # Create updated guardrail object
        guardrail_name = (
            request.guardrail_name
            if request.guardrail_name is not None
            else existing_guardrail.get("guardrail_name")
        )

        # Update litellm_params if default_on is provided or pii_entities_config is provided
        litellm_params = LitellmParams(
            **dict(existing_guardrail.get("litellm_params", {}))
        )
        if request.litellm_params is not None:
            requested_litellm_params = request.litellm_params.model_dump(
                exclude_unset=True
            )
            litellm_params_dict = litellm_params.model_dump(exclude_unset=True)
            litellm_params_dict.update(requested_litellm_params)
            litellm_params = LitellmParams(**litellm_params_dict)

        # Update guardrail_info if provided
        guardrail_info = (
            request.guardrail_info
            if request.guardrail_info is not None
            else existing_guardrail.get("guardrail_info", {})
        )

        # Create the guardrail object
        guardrail = Guardrail(
            guardrail_id=guardrail_id,
            guardrail_name=guardrail_name or "",
            litellm_params=litellm_params,
            guardrail_info=guardrail_info,
        )
        result = await GUARDRAIL_REGISTRY.update_guardrail_in_db(
            guardrail_id=guardrail_id,
            guardrail=guardrail,
            prisma_client=prisma_client,
        )

        guardrail_name = result.get("guardrail_name", "Unknown")

        try:
            IN_MEMORY_GUARDRAIL_HANDLER.sync_guardrail_from_db(
                guardrail=guardrail,
            )
            verbose_proxy_logger.info(
                f"Immediate sync: Successfully updated guardrail '{guardrail_name}' (ID: {guardrail_id})"
            )
        except Exception as update_error:
            verbose_proxy_logger.warning(
                f"Immediate sync: Failed to update '{guardrail_name}' (ID: {guardrail_id}) in memory: {update_error}"
            )

        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        verbose_proxy_logger.exception(f"Error updating guardrail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/guardrails/{guardrail_id}",
    tags=["Guardrails"],
    dependencies=[Depends(user_api_key_auth)],
)
@router.get(
    "/guardrails/{guardrail_id}/info",
    tags=["Guardrails"],
    dependencies=[Depends(user_api_key_auth)],
)
async def get_guardrail_info(guardrail_id: str):
    """
    Get detailed information about a specific guardrail by ID

    👉 [Guardrail docs](https://docs.litellm.ai/docs/proxy/guardrails/quick_start)

    Example Request:
    ```bash
    curl -X GET "http://localhost:4000/guardrails/123e4567-e89b-12d3-a456-426614174000/info" \\
        -H "Authorization: Bearer <your_api_key>"
    ```

    Example Response:
    ```json
    {
        "guardrail_id": "123e4567-e89b-12d3-a456-426614174000",
        "guardrail_name": "my-bedrock-guard",
        "litellm_params": {
            "guardrail": "bedrock",
            "mode": "pre_call",
            "guardrailIdentifier": "ff6ujrregl1q",
            "guardrailVersion": "DRAFT",
            "default_on": true
        },
        "guardrail_info": {
            "description": "Bedrock content moderation guardrail"
        },
        "created_at": "2023-11-09T12:34:56.789Z",
        "updated_at": "2023-11-09T12:34:56.789Z"
    }
    ```
    """

    from litellm.litellm_core_utils.litellm_logging import _get_masked_values
    from litellm.proxy.guardrails.guardrail_registry import IN_MEMORY_GUARDRAIL_HANDLER
    from litellm.proxy.proxy_server import prisma_client
    from litellm.types.guardrails import GUARDRAIL_DEFINITION_LOCATION

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Prisma client not initialized")

    try:
        guardrail_definition_location: GUARDRAIL_DEFINITION_LOCATION = (
            GUARDRAIL_DEFINITION_LOCATION.DB
        )
        result = await GUARDRAIL_REGISTRY.get_guardrail_by_id_from_db(
            guardrail_id=guardrail_id, prisma_client=prisma_client
        )
        if result is None:
            in_memory = IN_MEMORY_GUARDRAIL_HANDLER.get_guardrail_by_id(
                guardrail_id=guardrail_id
            )
            # Only return config-loaded entries here. A DB-backed entry that's
            # missing from the DB is stale (deleted on another pod, awaiting
            # reconciliation on this one) and must surface as 404.
            if (
                in_memory is not None
                and IN_MEMORY_GUARDRAIL_HANDLER.get_source(guardrail_id) == "config"
            ):
                result = in_memory
                guardrail_definition_location = GUARDRAIL_DEFINITION_LOCATION.CONFIG

        if result is None:
            raise HTTPException(
                status_code=404, detail=f"Guardrail with ID {guardrail_id} not found"
            )

        litellm_params: Optional[Union[LitellmParams, dict]] = result.get(
            "litellm_params"
        )
        result_litellm_params_dict = (
            litellm_params.model_dump(exclude_none=True)
            if isinstance(litellm_params, LitellmParams)
            else litellm_params
        ) or {}
        masked_litellm_params_dict = _get_masked_values(
            result_litellm_params_dict,
            unmasked_length=4,
            number_of_asterisks=4,
        )
        masked_litellm_params = (
            BaseLitellmParams(**masked_litellm_params_dict)
            if masked_litellm_params_dict
            else None
        )

        return GuardrailInfoResponse(
            guardrail_id=result.get("guardrail_id"),
            guardrail_name=result.get("guardrail_name"),
            litellm_params=masked_litellm_params,
            guardrail_info=dict(result.get("guardrail_info") or {}),
            created_at=result.get("created_at"),
            updated_at=result.get("updated_at"),
            guardrail_definition_location=guardrail_definition_location,
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/guardrails/ui/add_guardrail_settings",
    tags=["Guardrails"],
    dependencies=[Depends(user_api_key_auth)],
)
async def get_guardrail_ui_settings():
    """
    Get the UI settings for the guardrails

    Returns:
    - Supported entities for guardrails
    - Supported modes for guardrails
    - PII entity categories for UI grouping
    - Content filter settings (patterns and categories)
    """
    from litellm.proxy.guardrails.guardrail_hooks.litellm_content_filter.patterns import (
        PATTERN_CATEGORIES,
        get_available_content_categories,
        get_pattern_metadata,
    )

    # Convert the PII_ENTITY_CATEGORIES_MAP to the format expected by the UI
    category_maps = []
    for category, entities in PII_ENTITY_CATEGORIES_MAP.items():
        category_maps.append(
            {
                "category": category.value,
                "entities": [entity.value for entity in entities],
            }
        )

    return GuardrailUIAddGuardrailSettings(
        supported_entities=[entity.value for entity in PiiEntityType],
        supported_actions=[action.value for action in PiiAction],
        supported_modes=[mode.value for mode in GuardrailEventHooks],
        pii_entity_categories=category_maps,
        content_filter_settings={
            "prebuilt_patterns": get_pattern_metadata(),
            "pattern_categories": list(PATTERN_CATEGORIES.keys()),
            "supported_actions": ["BLOCK", "MASK"],
            "content_categories": get_available_content_categories(),
        },
    )


@router.get(
    "/guardrails/ui/category_yaml/{category_name}",
    tags=["Guardrails"],
    dependencies=[Depends(user_api_key_auth)],
)
async def get_category_yaml(category_name: str):
    """
    Get the YAML or JSON content for a specific content filter category.

    Args:
        category_name: The name of the category (e.g., "bias_gender", "harmful_self_harm")

    Returns:
        The raw YAML or JSON content of the category file with file type indicator
    """
    # Get the categories directory path
    categories_dir = os.path.join(
        os.path.dirname(__file__),
        "guardrail_hooks",
        "litellm_content_filter",
        "categories",
    )

    # Try to find the file with either .yaml or .json extension
    try:
        yaml_path = safe_join(categories_dir, f"{category_name}.yaml")
        json_path = safe_join(categories_dir, f"{category_name}.json")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid category name")

    category_file_path = None
    file_type = None

    if os.path.exists(yaml_path):
        category_file_path = yaml_path
        file_type = "yaml"
    elif os.path.exists(json_path):
        category_file_path = json_path
        file_type = "json"
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Category file not found: {category_name} (tried .yaml and .json)",
        )

    try:
        # Read and return the raw content
        with open(category_file_path, "r") as f:
            content = f.read()

        return {
            "category_name": category_name,
            "yaml_content": content,  # Keep key name for backwards compatibility
            "file_type": file_type,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error reading category file: {str(e)}"
        )


@router.get(
    "/guardrails/ui/major_airlines",
    tags=["Guardrails"],
    dependencies=[Depends(user_api_key_auth)],
)
async def get_major_airlines():
    """
    Get the major airlines list from IATA (competitor intent, airline type).
    Returns airline id, match variants (pipe-separated), and tags.
    """
    airlines_path = os.path.join(
        os.path.dirname(__file__),
        "guardrail_hooks",
        "litellm_content_filter",
        "competitor_intent",
        "major_airlines.json",
    )
    if not os.path.exists(airlines_path):
        raise HTTPException(
            status_code=404,
            detail="major_airlines.json not found",
        )
    try:
        with open(airlines_path, "r", encoding="utf-8") as f:
            import json

            airlines = json.load(f)
        return {"airlines": airlines}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error reading major_airlines.json: {str(e)}"
        ) from e


@router.post(
    "/guardrails/validate_blocked_words_file",
    tags=["Guardrails"],
    dependencies=[Depends(user_api_key_auth)],
)
async def validate_blocked_words_file(request: Dict[str, str]):
    """
    Validate a blocked_words YAML file content.

    Args:
        request: Dictionary with 'file_content' key containing the YAML string

    Returns:
        Dictionary with 'valid' boolean and either 'message'/'errors' depending on result

    Example Request:
    ```json
    {
        "file_content": "blocked_words:\\n  - keyword: \\"test\\"\\n    action: \\"BLOCK\\""
    }
    ```

    Example Success Response:
    ```json
    {
        "valid": true,
        "message": "Valid YAML file with 2 blocked words"
    }
    ```

    Example Error Response:
    ```json
    {
        "valid": false,
        "errors": ["Entry 0: missing 'action' field"]
    }
    ```
    """
    import yaml

    try:
        file_content = request.get("file_content", "")
        if not file_content:
            return {"valid": False, "error": "No file content provided"}

        data = yaml.safe_load(file_content)

        if not isinstance(data, dict) or "blocked_words" not in data:
            return {
                "valid": False,
                "error": "Invalid format: file must contain 'blocked_words' key with a list",
            }

        blocked_words_list = data["blocked_words"]
        if not isinstance(blocked_words_list, list):
            return {"valid": False, "error": "'blocked_words' must be a list"}

        # Validate each entry
        errors = []
        for idx, word_data in enumerate(blocked_words_list):
            if not isinstance(word_data, dict):
                errors.append(f"Entry {idx}: must be an object")
                continue

            if "keyword" not in word_data:
                errors.append(f"Entry {idx}: missing 'keyword' field")
            elif not isinstance(word_data["keyword"], str):
                errors.append(f"Entry {idx}: 'keyword' must be a string")

            if "action" not in word_data:
                errors.append(f"Entry {idx}: missing 'action' field")
            elif word_data["action"] not in ["BLOCK", "MASK"]:
                errors.append(
                    f"Entry {idx}: action must be 'BLOCK' or 'MASK', got '{word_data['action']}'"
                )

            if "description" in word_data and not isinstance(
                word_data["description"], str
            ):
                errors.append(f"Entry {idx}: 'description' must be a string")

        if errors:
            return {"valid": False, "errors": errors}

        return {
            "valid": True,
            "message": f"Valid YAML file with {len(blocked_words_list)} blocked word(s)",
        }
    except yaml.YAMLError as e:
        return {"valid": False, "error": f"Invalid YAML syntax: {str(e)}"}
    except Exception as e:
        verbose_proxy_logger.exception("Error validating blocked words file")
        return {"valid": False, "error": f"Validation error: {str(e)}"}


def _get_field_type_from_annotation(field_annotation: Any) -> str:
    """
    Convert a Python type annotation to a UI-friendly type string
    """
    # Handle Union types (like Optional[T])
    if (
        hasattr(field_annotation, "__origin__")
        and field_annotation.__origin__ is Union
        and hasattr(field_annotation, "__args__")
    ):
        # For Optional[T], get the non-None type
        args = field_annotation.__args__
        non_none_args = [arg for arg in args if arg is not type(None)]
        if non_none_args:
            field_annotation = non_none_args[0]

    # Handle List types
    if hasattr(field_annotation, "__origin__") and field_annotation.__origin__ is list:
        return "array"

    # Handle Dict types
    if hasattr(field_annotation, "__origin__") and field_annotation.__origin__ is dict:
        return "dict"

    # Handle Literal types
    if hasattr(field_annotation, "__origin__") and hasattr(
        field_annotation, "__args__"
    ):
        # Check for Literal types (Python 3.8+)
        origin = field_annotation.__origin__
        if hasattr(origin, "__name__") and origin.__name__ == "Literal":
            return "select"  # For dropdown/select inputs

    # Handle basic types
    if field_annotation is str:
        return "string"
    elif field_annotation is int:
        return "number"
    elif field_annotation is float:
        return "number"
    elif field_annotation is bool:
        return "boolean"
    elif field_annotation is dict:
        return "object"
    elif field_annotation is list:
        return "array"

    # Default to string for unknown types
    return "string"


def _extract_literal_values(annotation: Any) -> List[str]:
    """
    Extract literal values from a Literal type annotation
    """
    if hasattr(annotation, "__origin__") and hasattr(annotation, "__args__"):
        origin = annotation.__origin__
        if hasattr(origin, "__name__") and origin.__name__ == "Literal":
            return list(annotation.__args__)
    return []


def _get_dict_key_options(field_annotation: Any) -> Optional[List[str]]:
    """
    Extract key options from Dict[Literal[...], T] types
    """
    if (
        hasattr(field_annotation, "__origin__")
        and field_annotation.__origin__ is dict
        and hasattr(field_annotation, "__args__")
    ):
        args = field_annotation.__args__
        if len(args) >= 2:
            key_type = args[0]
            return _extract_literal_values(key_type)
    return None


def _get_dict_value_type(field_annotation: Any) -> str:
    """
    Get the value type from Dict[K, V] types
    """
    if (
        hasattr(field_annotation, "__origin__")
        and field_annotation.__origin__ is dict
        and hasattr(field_annotation, "__args__")
    ):
        args = field_annotation.__args__
        if len(args) >= 2:
            value_type = args[1]
            return _get_field_type_from_annotation(value_type)
    return "string"


def _get_list_element_options(field_annotation: Any) -> Optional[List[str]]:
    """
    Extract element options from List[Literal[...]] types
    """
    if (
        hasattr(field_annotation, "__origin__")
        and field_annotation.__origin__ is list
        and hasattr(field_annotation, "__args__")
    ):
        args = field_annotation.__args__
        if len(args) >= 1:
            element_type = args[0]
            return _extract_literal_values(element_type)
    return None


def _should_skip_optional_params(field_name: str, field_annotation: Any) -> bool:
    """Check if optional_params field should be skipped (not meaningfully overridden)."""
    if field_name != "optional_params":
        return False

    if field_annotation is None:
        return True

    # Check if the annotation is still a generic TypeVar (not specialized)
    if isinstance(field_annotation, TypeVar) or (
        hasattr(field_annotation, "__origin__")
        and field_annotation.__origin__ is TypeVar
    ):
        return True

    # Also skip if it's a generic type that wasn't specialized
    if hasattr(field_annotation, "__name__") and field_annotation.__name__ in (
        "T",
        "TypeVar",
    ):
        return True

    # Handle Optional[T] where T is still a TypeVar
    if hasattr(field_annotation, "__args__"):
        non_none_args = [
            arg for arg in field_annotation.__args__ if arg is not type(None)
        ]
        if non_none_args and isinstance(non_none_args[0], TypeVar):
            return True

    return False


def _unwrap_optional_type(field_annotation: Any) -> Any:
    """Unwrap Optional types to get the actual type."""
    if (
        hasattr(field_annotation, "__origin__")
        and field_annotation.__origin__ is Union
        and hasattr(field_annotation, "__args__")
    ):
        # For Optional[BaseModel], get the non-None type
        args = field_annotation.__args__
        non_none_args = [arg for arg in args if arg is not type(None)]
        if non_none_args:
            return non_none_args[0]
    return field_annotation


def _build_field_dict(
    field: Any,
    field_annotation: Any,
    description: str,
    required: bool,
) -> Dict[str, Any]:
    """Build field dictionary for non-nested fields."""
    # Determine the field type from annotation
    field_type = _get_field_type_from_annotation(field_annotation)

    # Check for custom UI type override
    field_json_schema_extra = getattr(field, "json_schema_extra", {})
    if field_json_schema_extra and "ui_type" in field_json_schema_extra:
        ui_type = field_json_schema_extra["ui_type"]
        field_type = ui_type.value if hasattr(ui_type, "value") else ui_type
    elif field_json_schema_extra and "type" in field_json_schema_extra:
        field_type = field_json_schema_extra["type"]

    # Add the field to the dictionary
    field_dict = {
        "description": description,
        "required": required,
        "type": field_type,
    }

    # Extract options from type annotations
    if field_type == "dict":
        # For Dict[Literal[...], T] types, extract key options
        dict_key_options = _get_dict_key_options(field_annotation)
        if dict_key_options:
            field_dict["dict_key_options"] = dict_key_options

        # Extract value type for the dict values
        dict_value_type = _get_dict_value_type(field_annotation)
        field_dict["dict_value_type"] = dict_value_type

    elif field_type == "array":
        # For List[Literal[...]] types, extract element options
        list_element_options = _get_list_element_options(field_annotation)
        if list_element_options:
            field_dict["options"] = list_element_options
            field_dict["type"] = "multiselect"

    # Add options if they exist in json_schema_extra (this takes precedence)
    if field_json_schema_extra and "options" in field_json_schema_extra:
        field_dict["options"] = field_json_schema_extra["options"]
    elif field_type == "select":
        # For Literal types, populate options so the UI can render a dropdown
        literal_options = _extract_literal_values(field_annotation)
        if literal_options:
            field_dict["options"] = literal_options

    # Add default value if it exists
    if field.default is not None and field.default is not ...:
        field_dict["default_value"] = field.default

    # Copy min, max, step from json_schema_extra for number/percentage inputs
    if field_json_schema_extra:
        for key in ("min", "max", "step", "default_value"):
            if key in field_json_schema_extra:
                field_dict[key] = field_json_schema_extra[key]

    return field_dict


def _extract_fields_recursive(
    model: Type[BaseModel],
    depth: int = 0,
) -> Dict[str, Any]:
    # Check if we've exceeded the maximum recursion depth
    if depth > DEFAULT_MAX_RECURSE_DEPTH:
        raise HTTPException(
            status_code=400,
            detail=f"Max depth of {DEFAULT_MAX_RECURSE_DEPTH} exceeded while processing model fields. Please check the model structure for excessive nesting.",
        )

    fields = {}

    for field_name, field in model.model_fields.items():
        field_annotation = field.annotation

        # Skip optional_params if it's not meaningfully overridden
        if _should_skip_optional_params(
            field_name=field_name, field_annotation=field_annotation
        ):
            continue

        # Handle Optional types and get the actual type
        if field_annotation is None:
            continue

        field_annotation = _unwrap_optional_type(field_annotation=field_annotation)

        # Get field metadata
        description = field.description or field_name
        required = field.is_required()

        # Check if this is a BaseModel subclass
        is_basemodel_subclass = (
            inspect.isclass(field_annotation)
            and issubclass(field_annotation, BaseModel)
            and field_annotation is not BaseModel
        )

        if is_basemodel_subclass:
            # Recursively get fields from the nested model
            nested_fields = _extract_fields_recursive(
                cast(Type[BaseModel], field_annotation), depth + 1
            )
            fields[field_name] = {
                "description": description,
                "required": required,
                "type": "nested",
                "fields": nested_fields,
            }
        else:
            fields[field_name] = _build_field_dict(
                field=field,
                field_annotation=field_annotation,
                description=description,
                required=required,
            )

    return fields


def _get_fields_from_model(model_class: Type[BaseModel]) -> Dict[str, Any]:
    """
    Get the fields from a Pydantic model as a nested dictionary structure
    """

    return _extract_fields_recursive(model_class, depth=0)


@router.get(
    "/guardrails/ui/provider_specific_params",
    tags=["Guardrails"],
    dependencies=[Depends(user_api_key_auth)],
)
async def get_provider_specific_params():
    """
    Get provider-specific parameters for different guardrail types.

    Returns a dictionary mapping guardrail providers to their specific parameters,
    including parameter names, descriptions, and whether they are required.

    Example Response:
    ```json
    {
        "bedrock": {
            "guardrailIdentifier": {
                "description": "The ID of your guardrail on Bedrock",
                "required": true,
                "type": null
            },
            "guardrailVersion": {
                "description": "The version of your Bedrock guardrail (e.g., DRAFT or version number)",
                "required": true,
                "type": null
            }
        },
        "azure_content_safety_text_moderation": {
            "api_key": {
                "description": "API key for the Azure Content Safety Text Moderation guardrail",
                "required": false,
                "type": null
            },
            "optional_params": {
                "description": "Optional parameters for the Azure Content Safety Text Moderation guardrail",
                "required": true,
                "type": "nested",
                "fields": {
                    "severity_threshold": {
                        "description": "Severity threshold for the Azure Content Safety Text Moderation guardrail across all categories",
                        "required": false,
                        "type": null
                    },
                    "categories": {
                        "description": "Categories to scan for the Azure Content Safety Text Moderation guardrail",
                        "required": false,
                        "type": "multiselect",
                        "options": ["Hate", "SelfHarm", "Sexual", "Violence"],
                        "default_value": None
                    }
                }
            }
        }
    }
    ```
    """
    # Get fields from the models
    bedrock_fields = _get_fields_from_model(BedrockGuardrailConfigModel)
    presidio_fields = _get_fields_from_model(PresidioPresidioConfigModelUserInterface)
    lakera_v2_fields = _get_fields_from_model(LakeraV2GuardrailConfigModel)
    tool_permission_fields = _get_fields_from_model(ToolPermissionGuardrailConfigModel)

    tool_permission_fields["ui_friendly_name"] = (
        ToolPermissionGuardrailConfigModel.ui_friendly_name()
    )

    # Return the provider-specific parameters
    provider_params = {
        SupportedGuardrailIntegrations.BEDROCK.value: bedrock_fields,
        SupportedGuardrailIntegrations.PRESIDIO.value: presidio_fields,
        SupportedGuardrailIntegrations.LAKERA_V2.value: lakera_v2_fields,
        SupportedGuardrailIntegrations.TOOL_PERMISSION.value: tool_permission_fields,
    }

    ### get the config model for the guardrail - go through the registry and get the config model for the guardrail
    from litellm.proxy.guardrails.guardrail_registry import guardrail_class_registry

    for guardrail_name, guardrail_class in guardrail_class_registry.items():
        guardrail_config_model = guardrail_class.get_config_model()

        if guardrail_config_model:
            fields = _get_fields_from_model(guardrail_config_model)
            ui_friendly_name = guardrail_config_model.ui_friendly_name()
            fields["ui_friendly_name"] = ui_friendly_name
            provider_params[guardrail_name] = fields

    return provider_params


class TestCustomCodeGuardrailRequest(BaseModel):
    """Request model for testing custom code guardrails."""

    custom_code: str
    """The Python-like code containing the apply_guardrail function."""

    test_input: Dict[str, Any]
    """The test input to pass to the guardrail. Should contain 'texts', optionally 'images', 'tools', etc."""

    input_type: str = "request"
    """Whether this is a 'request' or 'response' input type."""

    request_data: Optional[Dict[str, Any]] = None
    """Optional mock request_data (model, user_id, team_id, metadata, etc.)."""


class TestCustomCodeGuardrailResponse(BaseModel):
    """Response model for testing custom code guardrails."""

    success: bool
    """Whether the test executed successfully (no errors)."""

    result: Optional[Dict[str, Any]] = None
    """The guardrail result: action (allow/block/modify), reason, modified_texts, etc."""

    error: Optional[str] = None
    """Error message if execution failed."""

    error_type: Optional[str] = None
    """Type of error: 'compilation' or 'execution'."""


@router.post(
    "/guardrails/test_custom_code",
    tags=["Guardrails"],
    response_model=TestCustomCodeGuardrailResponse,
)
async def test_custom_code_guardrail(
    request: TestCustomCodeGuardrailRequest,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    Test custom code guardrail logic without creating a guardrail.

    This endpoint allows admins to experiment with custom code guardrails by:
    1. Compiling the provided code in a sandbox
    2. Executing the apply_guardrail function with test input
    3. Returning the result (allow/block/modify)

    👉 [Custom Code Guardrail docs](https://docs.litellm.ai/docs/proxy/guardrails/custom_code_guardrail)

    Example Request:
    ```bash
    curl -X POST "http://localhost:4000/guardrails/test_custom_code" \\
        -H "Authorization: Bearer <your_api_key>" \\
        -H "Content-Type: application/json" \\
        -d '{
            "custom_code": "def apply_guardrail(inputs, request_data, input_type):\\n    for text in inputs[\\"texts\\"]:\\n        if regex_match(text, r\\"\\\\d{3}-\\\\d{2}-\\\\d{4}\\"):\\n            return block(\\"SSN detected\\")\\n    return allow()",
            "test_input": {
                "texts": ["My SSN is 123-45-6789"]
            },
            "input_type": "request"
        }'
    ```

    Example Success Response (blocked):
    ```json
    {
        "success": true,
        "result": {
            "action": "block",
            "reason": "SSN detected"
        },
        "error": null,
        "error_type": null
    }
    ```

    Example Success Response (allowed):
    ```json
    {
        "success": true,
        "result": {
            "action": "allow"
        },
        "error": null,
        "error_type": null
    }
    ```

    Example Success Response (modified):
    ```json
    {
        "success": true,
        "result": {
            "action": "modify",
            "texts": ["My SSN is [REDACTED]"]
        },
        "error": null,
        "error_type": null
    }
    ```

    Example Error Response (compilation error):
    ```json
    {
        "success": false,
        "result": null,
        "error": "Syntax error in custom code: invalid syntax (<guardrail>, line 1)",
        "error_type": "compilation"
    }
    ```
    """

    if user_api_key_dict.user_role != LitellmUserRoles.PROXY_ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Admin access required to test custom code guardrails",
        )

    EXECUTION_TIMEOUT_SECONDS = 5

    try:
        exec_globals = build_sandbox_globals()

        try:
            compiled = compile_sandboxed(request.custom_code)
            exec(compiled, exec_globals)  # noqa: S102
        except SyntaxError as e:
            return TestCustomCodeGuardrailResponse(
                success=False,
                error=f"Syntax error in custom code: {e}",
                error_type="compilation",
            )
        except Exception as e:
            return TestCustomCodeGuardrailResponse(
                success=False,
                error=f"Failed to compile custom code: {e}",
                error_type="compilation",
            )

        # Step 2: Verify apply_guardrail function exists
        if "apply_guardrail" not in exec_globals:
            return TestCustomCodeGuardrailResponse(
                success=False,
                error="Custom code must define an 'apply_guardrail' function. "
                "Expected signature: apply_guardrail(inputs, request_data, input_type)",
                error_type="compilation",
            )

        apply_fn = exec_globals["apply_guardrail"]
        if not callable(apply_fn):
            return TestCustomCodeGuardrailResponse(
                success=False,
                error="'apply_guardrail' must be a callable function",
                error_type="compilation",
            )

        # Step 3: Prepare test inputs
        test_inputs = request.test_input
        if "texts" not in test_inputs:
            test_inputs["texts"] = []

        # Prepare mock request_data
        mock_request_data = request.request_data or {}
        safe_request_data = {
            "model": mock_request_data.get("model", "test-model"),
            "user_id": mock_request_data.get("user_id"),
            "team_id": mock_request_data.get("team_id"),
            "end_user_id": mock_request_data.get("end_user_id"),
            "metadata": mock_request_data.get("metadata", {}),
        }

        # Step 4: Execute the function with timeout protection

        def execute_guardrail():
            return apply_fn(test_inputs, safe_request_data, request.input_type)

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(execute_guardrail)
                try:
                    result = future.result(timeout=EXECUTION_TIMEOUT_SECONDS)
                except concurrent.futures.TimeoutError:
                    return TestCustomCodeGuardrailResponse(
                        success=False,
                        error=f"Execution timeout: code took longer than {EXECUTION_TIMEOUT_SECONDS} seconds",
                        error_type="execution",
                    )
        except Exception as e:
            return TestCustomCodeGuardrailResponse(
                success=False,
                error=f"Execution error: {e}",
                error_type="execution",
            )

        # Step 5: Validate and return result
        if not isinstance(result, dict):
            return TestCustomCodeGuardrailResponse(
                success=True,
                result={
                    "action": "allow",
                    "warning": f"Expected dict result, got {type(result).__name__}. Treating as allow.",
                },
            )

        return TestCustomCodeGuardrailResponse(
            success=True,
            result=result,
        )

    except Exception as e:
        verbose_proxy_logger.exception(f"Error testing custom code guardrail: {e}")
        return TestCustomCodeGuardrailResponse(
            success=False,
            error=f"Unexpected error: {e}",
            error_type="execution",
        )


@router.post("/guardrails/apply_guardrail", response_model=ApplyGuardrailResponse)
@router.post("/apply_guardrail", response_model=ApplyGuardrailResponse)
async def apply_guardrail(
    request: ApplyGuardrailRequest,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    Apply a guardrail to text input and return the processed result.

    This endpoint allows testing guardrails by applying them to custom text inputs.
    """
    from litellm.proxy.utils import handle_exception_on_proxy

    try:
        active_guardrail: Optional[CustomGuardrail] = (
            GUARDRAIL_REGISTRY.get_initialized_guardrail_callback(
                guardrail_name=request.guardrail_name
            )
        )
        if active_guardrail is None:
            raise HTTPException(
                status_code=404,
                detail=f"Guardrail '{request.guardrail_name}' not found. Please ensure the guardrail is configured in your LiteLLM proxy.",
            )

        request_data: dict = {}
        if request.messages:
            request_data["messages"] = request.messages

        # Auto-detect input_type: if the caller didn't specify "response" but the
        # guardrail only runs post_call (e.g. LLM-as-a-judge), use "response" so
        # the test actually exercises the guardrail logic.
        from litellm.types.guardrails import GuardrailEventHooks

        resolved_input_type = request.input_type
        if resolved_input_type == "request":
            hook = getattr(active_guardrail, "event_hook", None)
            if hook == GuardrailEventHooks.post_call or hook == "post_call":
                resolved_input_type = "response"

        _input_type: Literal["request", "response"] = (
            "response" if resolved_input_type == "response" else "request"
        )
        guardrailed_inputs = await active_guardrail.apply_guardrail(
            inputs={"texts": [request.text]},
            request_data=request_data,
            input_type=_input_type,
        )
        response_text = guardrailed_inputs.get("texts", [])

        return ApplyGuardrailResponse(
            response_text=response_text[0] if response_text else request.text
        )
    except Exception as e:
        raise handle_exception_on_proxy(e)


# Usage (dashboard) endpoints: overview, detail, logs
router.include_router(guardrails_usage_router)
