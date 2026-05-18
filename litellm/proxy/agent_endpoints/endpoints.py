"""
Agent endpoints for registering + discovering agents via LiteLLM.

Follows the A2A Spec.

1. Register an agent via POST `/v1/agents`
2. Discover agents via GET `/v1/agents`
3. Get specific agent via GET `/v1/agents/{agent_id}`
"""

import asyncio
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

import litellm
from litellm._logging import verbose_proxy_logger
from litellm.llms.custom_httpx.http_handler import get_async_httpx_client
from litellm.proxy._types import CommonProxyErrors, LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.auth.user_api_key_auth import user_api_key_auth
from litellm.proxy.common_utils.rbac_utils import check_feature_access_for_user
from litellm.proxy.management_endpoints.common_utils import (
    build_company_project_access_context,
)
from litellm.proxy.management_endpoints.common_daily_activity import get_daily_activity
from litellm.types.agents import (
    AgentConfig,
    AgentMakePublicResponse,
    AgentResponse,
    MakeAgentsPublicRequest,
    PatchAgentRequest,
)
from litellm.litellm_core_utils.litellm_logging import _get_masked_values
from litellm.types.llms.custom_http import httpxSpecialProvider
from litellm.types.proxy.management_endpoints.common_daily_activity import (
    DailySpendMetadata,
    SpendAnalyticsPaginatedResponse,
)

router = APIRouter()


def _redact_sensitive_agent_fields(
    agents: List[AgentResponse],
) -> List[AgentResponse]:
    """
    Return copies of the given agents with sensitive configuration fields
    redacted.  The original objects are not modified.
    """
    redacted: List[AgentResponse] = []
    for agent in agents:
        copy = agent.model_copy(deep=True)
        copy.static_headers = None
        copy.extra_headers = None
        if copy.litellm_params:
            copy.litellm_params = _get_masked_values(
                copy.litellm_params,
                unmasked_length=4,
                number_of_asterisks=4,
            )
        redacted.append(copy)
    return redacted


def _check_agent_management_permission(user_api_key_dict: UserAPIKeyAuth) -> None:
    """
    Raises HTTP 403 if the caller does not have permission to create, update,
    or delete agents.  Only PROXY_ADMIN users are allowed to perform these
    write operations.
    """
    if not _is_proxy_admin(user_api_key_dict):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "Only proxy admins can create, update, or delete agents. Your role={}".format(
                    user_api_key_dict.user_role
                )
            },
        )


def _is_proxy_admin(user_api_key_dict: UserAPIKeyAuth) -> bool:
    return user_api_key_dict.user_role in (
        LitellmUserRoles.PROXY_ADMIN,
        LitellmUserRoles.PROXY_ADMIN.value,
    )


def _get_field_value(obj: Any, field: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(field)
    return getattr(obj, field, None)


def _agent_row_to_dict(agent: Any) -> Dict[str, Any]:
    if isinstance(agent, dict):
        return dict(agent)
    if hasattr(agent, "model_dump"):
        return agent.model_dump()
    return dict(agent)


async def _get_complete_user_info(
    *,
    user_api_key_dict: UserAPIKeyAuth,
    prisma_client: Any,
) -> Any:
    if user_api_key_dict.user_id is None:
        return None

    from litellm.proxy.auth.auth_checks import get_user_object
    from litellm.proxy.proxy_server import proxy_logging_obj, user_api_key_cache

    return await get_user_object(
        user_id=user_api_key_dict.user_id,
        prisma_client=prisma_client,
        user_api_key_cache=user_api_key_cache,
        user_id_upsert=False,
        proxy_logging_obj=proxy_logging_obj,
    )


async def _resolve_agent_project_context(
    *,
    prisma_client: Any,
    company_id: Optional[str],
    project_id: Optional[str],
) -> tuple[Optional[str], Optional[str], Any]:
    if project_id is None:
        return company_id, None, None

    project = await prisma_client.db.litellm_projecttable.find_unique(
        where={"project_id": project_id},
        include={"litellm_team_table": True},
    )
    if project is None:
        raise HTTPException(
            status_code=404,
            detail={"error": f"Project not found for project_id={project_id}"},
        )

    team = _get_field_value(project, "litellm_team_table")
    team_id = _get_field_value(project, "team_id")
    if team is None and team_id is not None:
        team = await prisma_client.db.litellm_teamtable.find_unique(
            where={"team_id": team_id}
        )

    if team_id is None or team is None:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"Project={project_id} must have a backing team before it can own agents."
            },
        )

    project_company_id = _get_field_value(project, "company_id") or _get_field_value(
        team, "organization_id"
    )
    if project_company_id is None:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"Project={project_id} backing team is not assigned to a company."
            },
        )

    if company_id is not None and company_id != project_company_id:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"project_id={project_id} belongs to company_id={project_company_id}; received company_id={company_id}."
            },
        )

    return project_company_id, project_id, team


async def _authorize_agent_company_project_context(
    *,
    user_api_key_dict: UserAPIKeyAuth,
    prisma_client: Any,
    company_id: Optional[str],
    project_id: Optional[str],
    project_team_obj: Any = None,
    write: bool,
) -> None:
    if _is_proxy_admin(user_api_key_dict):
        return
    if company_id is None and project_id is None:
        if write:
            _check_agent_management_permission(user_api_key_dict)
        return

    complete_user_info = await _get_complete_user_info(
        user_api_key_dict=user_api_key_dict,
        prisma_client=prisma_client,
    )
    context = build_company_project_access_context(
        user_api_key_dict=user_api_key_dict,
        complete_user_info=complete_user_info,
        project_team_obj=project_team_obj,
        project_company_id=company_id,
        route_permission="/v1/agents",
    )
    if project_id is not None:
        allowed = context.can_manage_project() if write else context.can_read_project()
    elif write:
        allowed = (
            context.can_read_company(company_id)
            and company_id in context.company_admin_ids
        )
    else:
        allowed = context.can_read_company(company_id)

    if not allowed:
        action = "manage" if write else "read"
        raise HTTPException(
            status_code=403,
            detail={
                "error": f"Not authorized to {action} agents for company_id={company_id}, project_id={project_id}."
            },
        )


def _agent_tenant_filter(
    agents: List[AgentResponse],
    *,
    company_id: Optional[str],
    project_id: Optional[str],
) -> List[AgentResponse]:
    if company_id is None and project_id is None:
        return agents
    return [
        agent
        for agent in agents
        if (company_id is None or agent.company_id == company_id)
        and (project_id is None or agent.project_id == project_id)
    ]


async def _enrich_agent_tenant_names(
    agents: List[AgentResponse],
    prisma_client: Any,
) -> List[AgentResponse]:
    company_ids = sorted({agent.company_id for agent in agents if agent.company_id})
    project_ids = sorted({agent.project_id for agent in agents if agent.project_id})
    company_names: Dict[str, str] = {}
    project_names: Dict[str, str] = {}

    if company_ids:
        companies = await prisma_client.db.litellm_organizationtable.find_many(
            where={"organization_id": {"in": company_ids}}
        )
        company_names = {
            _get_field_value(company, "organization_id"): _get_field_value(
                company, "organization_alias"
            )
            for company in companies
            if _get_field_value(company, "organization_id")
        }
    if project_ids:
        projects = await prisma_client.db.litellm_projecttable.find_many(
            where={"project_id": {"in": project_ids}}
        )
        project_names = {
            _get_field_value(project, "project_id"): _get_field_value(
                project, "project_alias"
            )
            for project in projects
            if _get_field_value(project, "project_id")
        }

    for agent in agents:
        if agent.company_id and company_names.get(agent.company_id):
            agent.company_name = company_names[agent.company_id]
        if agent.project_id and project_names.get(agent.project_id):
            agent.project_name = project_names[agent.project_id]
    return agents


async def _filter_agents_for_caller_tenant_access(
    *,
    agents: List[AgentResponse],
    prisma_client: Any,
    user_api_key_dict: UserAPIKeyAuth,
) -> List[AgentResponse]:
    if _is_proxy_admin(user_api_key_dict):
        return agents

    visible_agents: List[AgentResponse] = []
    for agent in agents:
        company_id, project_id, project_team_obj = await _resolve_agent_project_context(
            prisma_client=prisma_client,
            company_id=agent.company_id,
            project_id=agent.project_id,
        )
        try:
            await _authorize_agent_company_project_context(
                user_api_key_dict=user_api_key_dict,
                prisma_client=prisma_client,
                company_id=company_id,
                project_id=project_id,
                project_team_obj=project_team_obj,
                write=False,
            )
        except HTTPException:
            continue
        visible_agents.append(agent)
    return visible_agents


async def _normalize_agent_tenant_context(
    *,
    prisma_client: Any,
    agent_payload: Dict[str, Any],
    fallback_agent: Optional[Dict[str, Any]] = None,
) -> tuple[Optional[str], Optional[str], Any]:
    company_id = agent_payload.get("company_id")
    project_id = agent_payload.get("project_id")
    if "company_id" not in agent_payload and fallback_agent is not None:
        company_id = fallback_agent.get("company_id")
    if "project_id" not in agent_payload and fallback_agent is not None:
        project_id = fallback_agent.get("project_id")

    company_id, project_id, project_team_obj = await _resolve_agent_project_context(
        prisma_client=prisma_client,
        company_id=company_id,
        project_id=project_id,
    )
    agent_payload["company_id"] = company_id
    agent_payload["project_id"] = project_id
    return company_id, project_id, project_team_obj


async def _authorize_agent_write_context_change(
    *,
    user_api_key_dict: UserAPIKeyAuth,
    prisma_client: Any,
    existing_agent: Dict[str, Any],
    target_company_id: Optional[str],
    target_project_id: Optional[str],
    target_project_team_obj: Any,
) -> None:
    existing_company_id, existing_project_id, existing_project_team_obj = (
        await _resolve_agent_project_context(
            prisma_client=prisma_client,
            company_id=existing_agent.get("company_id"),
            project_id=existing_agent.get("project_id"),
        )
    )
    await _authorize_agent_company_project_context(
        user_api_key_dict=user_api_key_dict,
        prisma_client=prisma_client,
        company_id=existing_company_id,
        project_id=existing_project_id,
        project_team_obj=existing_project_team_obj,
        write=True,
    )
    if (
        target_company_id,
        target_project_id,
    ) != (existing_company_id, existing_project_id):
        await _authorize_agent_company_project_context(
            user_api_key_dict=user_api_key_dict,
            prisma_client=prisma_client,
            company_id=target_company_id,
            project_id=target_project_id,
            project_team_obj=target_project_team_obj,
            write=True,
        )


AGENT_HEALTH_CHECK_TIMEOUT_SECONDS = float(
    os.environ.get("LITELLM_AGENT_HEALTH_CHECK_TIMEOUT", "5.0")
)
AGENT_HEALTH_CHECK_GATHER_TIMEOUT_SECONDS = float(
    os.environ.get("LITELLM_AGENT_HEALTH_CHECK_GATHER_TIMEOUT", "30.0")
)


async def _check_agent_url_health(
    agent: AgentResponse,
) -> Dict[str, Any]:
    """
    Perform a GET request against the agent's URL and return the health result.

    Returns a dict with ``agent_id``, ``healthy`` (bool), and an optional
    ``error`` message.
    """
    url = (agent.agent_card_params or {}).get("url")
    if not url:
        return {"agent_id": agent.agent_id, "healthy": True}

    try:
        client = get_async_httpx_client(
            llm_provider=httpxSpecialProvider.AgentHealthCheck,
            params={"timeout": AGENT_HEALTH_CHECK_TIMEOUT_SECONDS},
        )
        response = await client.get(url)
        if response.status_code >= 500:
            return {
                "agent_id": agent.agent_id,
                "healthy": False,
                "error": f"HTTP {response.status_code}",
            }
        return {"agent_id": agent.agent_id, "healthy": True}
    except Exception as exc:
        return {
            "agent_id": agent.agent_id,
            "healthy": False,
            "error": str(exc),
        }


@router.get(
    "/v1/agents",
    tags=["[beta] A2A Agents"],
    dependencies=[Depends(user_api_key_auth)],
    response_model=List[AgentResponse],
)
async def get_agents(
    request: Request,
    health_check: bool = Query(
        False,
        description="When true, performs a GET request to each agent's URL. Agents with reachable URLs (HTTP status < 500) and agents without a URL are returned; unreachable agents are filtered out.",
    ),
    company_id: Optional[str] = Query(
        None,
        description="Filter agents by product company_id.",
    ),
    project_id: Optional[str] = Query(
        None,
        description="Filter agents by product project_id.",
    ),
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),  # Used for auth
):
    """
    Example usage:
    ```
    curl -X GET "http://localhost:4000/v1/agents" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer your-key" \
    ```

    Pass `?health_check=true` to filter out agents whose URL is unreachable:
    ```
    curl -X GET "http://localhost:4000/v1/agents?health_check=true" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer your-key" \
    ```

    Returns: List[AgentResponse]

    """
    await check_feature_access_for_user(user_api_key_dict, "agents")

    from litellm.proxy.agent_endpoints.agent_registry import global_agent_registry
    from litellm.proxy.agent_endpoints.auth.agent_permission_handler import (
        AgentRequestHandler,
    )

    try:
        returned_agents: List[AgentResponse] = []

        # Admin users get all agents
        if (
            user_api_key_dict.user_role == LitellmUserRoles.PROXY_ADMIN
            or user_api_key_dict.user_role == LitellmUserRoles.PROXY_ADMIN.value
        ):
            returned_agents = global_agent_registry.get_agent_list()
        else:
            # Get allowed agents from object_permission (key/team level)
            allowed_agent_ids = await AgentRequestHandler.get_allowed_agents(
                user_api_key_auth=user_api_key_dict
            )

            # If no restrictions (empty list), return all agents
            if len(allowed_agent_ids) == 0:
                returned_agents = global_agent_registry.get_agent_list()
            else:
                # Filter agents by allowed IDs
                all_agents = global_agent_registry.get_agent_list()
                returned_agents = [
                    agent for agent in all_agents if agent.agent_id in allowed_agent_ids
                ]

        from litellm.proxy.proxy_server import prisma_client

        resolved_company_id = company_id
        resolved_project_id = project_id
        resolved_project_team_obj = None
        if prisma_client is None:
            if company_id is not None or project_id is not None:
                raise HTTPException(
                    status_code=500, detail="Prisma client not initialized"
                )
        else:
            resolved_company_id, resolved_project_id, resolved_project_team_obj = (
                await _resolve_agent_project_context(
                    prisma_client=prisma_client,
                    company_id=company_id,
                    project_id=project_id,
                )
            )
            await _authorize_agent_company_project_context(
                user_api_key_dict=user_api_key_dict,
                prisma_client=prisma_client,
                company_id=resolved_company_id,
                project_id=resolved_project_id,
                project_team_obj=resolved_project_team_obj,
                write=False,
            )

        # Fetch current spend and tenant context from DB for all returned agents.
        if prisma_client is not None:
            agent_ids = [agent.agent_id for agent in returned_agents]
            if agent_ids:
                db_agents = await prisma_client.db.litellm_agentstable.find_many(
                    where={"agent_id": {"in": agent_ids}},
                )
                db_agent_map = {
                    _get_field_value(agent, "agent_id"): agent for agent in db_agents
                }
                for agent in returned_agents:
                    db_agent = db_agent_map.get(agent.agent_id)
                    if db_agent is None:
                        continue
                    agent.spend = _get_field_value(db_agent, "spend")
                    agent.company_id = _get_field_value(db_agent, "company_id")
                    agent.project_id = _get_field_value(db_agent, "project_id")

            returned_agents = _agent_tenant_filter(
                returned_agents,
                company_id=resolved_company_id,
                project_id=resolved_project_id,
            )
            returned_agents = await _filter_agents_for_caller_tenant_access(
                agents=returned_agents,
                prisma_client=prisma_client,
                user_api_key_dict=user_api_key_dict,
            )
            returned_agents = await _enrich_agent_tenant_names(
                returned_agents,
                prisma_client=prisma_client,
            )

        # add is_public field to each agent - we do it this way, to allow setting config agents as public
        for agent in returned_agents:
            if agent.litellm_params is None:
                agent.litellm_params = {}
            agent.litellm_params["is_public"] = (
                litellm.public_agent_groups is not None
                and (agent.agent_id in litellm.public_agent_groups)
            )

        # Redact sensitive fields for non-admin users
        is_admin = (
            user_api_key_dict.user_role == LitellmUserRoles.PROXY_ADMIN
            or user_api_key_dict.user_role == LitellmUserRoles.PROXY_ADMIN.value
        )
        if not is_admin:
            returned_agents = _redact_sensitive_agent_fields(returned_agents)

        if health_check:
            agents_with_url = [
                agent
                for agent in returned_agents
                if (agent.agent_card_params or {}).get("url")
            ]
            agents_without_url = [
                agent
                for agent in returned_agents
                if not (agent.agent_card_params or {}).get("url")
            ]
            try:
                health_results = await asyncio.wait_for(
                    asyncio.gather(
                        *[_check_agent_url_health(agent) for agent in agents_with_url]
                    ),
                    timeout=AGENT_HEALTH_CHECK_GATHER_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                verbose_proxy_logger.warning(
                    "Agent health check gather timed out after %s seconds",
                    AGENT_HEALTH_CHECK_GATHER_TIMEOUT_SECONDS,
                )
                health_results = [
                    {
                        "agent_id": agent.agent_id,
                        "healthy": False,
                        "error": "Health check timed out",
                    }
                    for agent in agents_with_url
                ]
            healthy_ids = {
                result["agent_id"] for result in health_results if result["healthy"]
            }
            returned_agents = [
                agent for agent in agents_with_url if agent.agent_id in healthy_ids
            ] + agents_without_url

        return returned_agents
    except HTTPException:
        raise
    except Exception as e:
        verbose_proxy_logger.exception(
            "litellm.proxy.agent_endpoints.get_agents(): Exception occurred - {}".format(
                str(e)
            )
        )
        raise HTTPException(
            status_code=500, detail={"error": f"Internal server error: {str(e)}"}
        )


#### CRUD ENDPOINTS FOR AGENTS ####

from litellm.proxy.agent_endpoints.agent_registry import (
    global_agent_registry as AGENT_REGISTRY,
)


@router.post(
    "/v1/agents",
    tags=["[beta] A2A Agents"],
    dependencies=[Depends(user_api_key_auth)],
    response_model=AgentResponse,
)
async def create_agent(
    request: AgentConfig,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    Create a new agent

    Example Request:
    ```bash
    curl -X POST "http://localhost:4000/agents" \\
        -H "Authorization: Bearer <your_api_key>" \\
        -H "Content-Type: application/json" \\
        -d '{
            "agent": {
                "agent_name": "my-custom-agent",
                "agent_card_params": {
                    "protocolVersion": "1.0",
                    "name": "Hello World Agent",
                    "description": "Just a hello world agent",
                    "url": "http://localhost:9999/",
                    "version": "1.0.0",
                    "defaultInputModes": ["text"],
                    "defaultOutputModes": ["text"],
                    "capabilities": {
                        "streaming": true
                    },
                    "skills": [
                        {
                            "id": "hello_world",
                            "name": "Returns hello world",
                            "description": "just returns hello world",
                            "tags": ["hello world"],
                            "examples": ["hi", "hello world"]
                        }
                    ]
                },
                "litellm_params": {
                    "make_public": true
                }
            }
        }'
    ```
    """
    await check_feature_access_for_user(user_api_key_dict, "agents")

    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        _check_agent_management_permission(user_api_key_dict)
        raise HTTPException(status_code=500, detail="Prisma client not initialized")

    try:
        request_data = dict(request)
        company_id, project_id, project_team_obj = (
            await _normalize_agent_tenant_context(
                prisma_client=prisma_client,
                agent_payload=request_data,
            )
        )
        await _authorize_agent_company_project_context(
            user_api_key_dict=user_api_key_dict,
            prisma_client=prisma_client,
            company_id=company_id,
            project_id=project_id,
            project_team_obj=project_team_obj,
            write=True,
        )

        # Get the user ID from the API key auth
        created_by = user_api_key_dict.user_id or "unknown"

        # check for naming conflicts
        existing_agent = AGENT_REGISTRY.get_agent_by_name(
            agent_name=request.get("agent_name")  # type: ignore
        )
        if existing_agent is not None:
            raise HTTPException(
                status_code=400,
                detail=f"Agent with name {request.get('agent_name')} already exists",
            )

        result = await AGENT_REGISTRY.add_agent_to_db(
            agent=request_data, prisma_client=prisma_client, created_by=created_by
        )
        result = (
            await _enrich_agent_tenant_names([result], prisma_client=prisma_client)
        )[0]

        agent_name = result.agent_name
        agent_id = result.agent_id

        # Also register in memory
        try:
            AGENT_REGISTRY.register_agent(agent_config=result)
            verbose_proxy_logger.info(
                f"Successfully registered agent '{agent_name}' (ID: {agent_id}) in memory"
            )
        except Exception as reg_error:
            verbose_proxy_logger.warning(
                f"Failed to register agent '{agent_name}' (ID: {agent_id}) in memory: {reg_error}"
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        verbose_proxy_logger.exception(f"Error adding agent to db: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/v1/agents/{agent_id}",
    tags=["[beta] A2A Agents"],
    dependencies=[Depends(user_api_key_auth)],
    response_model=AgentResponse,
)
async def get_agent_by_id(
    agent_id: str,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    Get a specific agent by ID

    Example Request:
    ```bash
    curl -X GET "http://localhost:4000/agents/123e4567-e89b-12d3-a456-426614174000" \\
        -H "Authorization: Bearer <your_api_key>"
    ```
    """
    await check_feature_access_for_user(user_api_key_dict, "agents")

    is_admin = (
        user_api_key_dict.user_role == LitellmUserRoles.PROXY_ADMIN
        or user_api_key_dict.user_role == LitellmUserRoles.PROXY_ADMIN.value
    )
    if not is_admin:
        from litellm.proxy.agent_endpoints.auth.agent_permission_handler import (
            AgentRequestHandler,
        )

        is_allowed = await AgentRequestHandler.is_agent_allowed(
            agent_id=agent_id, user_api_key_auth=user_api_key_dict
        )
        if not is_allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Agent '{agent_id}' is not allowed for your key/team. Contact proxy admin for access.",
            )

    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Prisma client not initialized")

    try:
        agent = AGENT_REGISTRY.get_agent_by_id(agent_id=agent_id)
        if agent is None:
            agent_row = await prisma_client.db.litellm_agentstable.find_unique(
                where={"agent_id": agent_id},
                include={"object_permission": True},
            )
            if agent_row is not None:
                agent_dict = agent_row.model_dump()
                if agent_row.object_permission is not None:
                    try:
                        agent_dict["object_permission"] = (
                            agent_row.object_permission.model_dump()
                        )
                    except Exception:
                        agent_dict["object_permission"] = (
                            agent_row.object_permission.dict()
                        )
                agent = AgentResponse(**agent_dict)  # type: ignore
        else:
            # Agent found in memory — refresh spend from DB
            db_row = await prisma_client.db.litellm_agentstable.find_unique(
                where={"agent_id": agent_id}
            )
            if db_row is not None:
                agent.spend = db_row.spend
                agent.company_id = _get_field_value(db_row, "company_id")
                agent.project_id = _get_field_value(db_row, "project_id")

        if agent is None:
            raise HTTPException(
                status_code=404, detail=f"Agent with ID {agent_id} not found"
            )

        company_id, project_id, project_team_obj = await _resolve_agent_project_context(
            prisma_client=prisma_client,
            company_id=agent.company_id,
            project_id=agent.project_id,
        )
        await _authorize_agent_company_project_context(
            user_api_key_dict=user_api_key_dict,
            prisma_client=prisma_client,
            company_id=company_id,
            project_id=project_id,
            project_team_obj=project_team_obj,
            write=False,
        )
        agent = (
            await _enrich_agent_tenant_names([agent], prisma_client=prisma_client)
        )[0]

        # Redact sensitive fields for non-admin users
        is_admin = (
            user_api_key_dict.user_role == LitellmUserRoles.PROXY_ADMIN
            or user_api_key_dict.user_role == LitellmUserRoles.PROXY_ADMIN.value
        )
        if not is_admin:
            agent = _redact_sensitive_agent_fields([agent])[0]

        return agent
    except HTTPException:
        raise
    except Exception as e:
        verbose_proxy_logger.exception(f"Error getting agent from db: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put(
    "/v1/agents/{agent_id}",
    tags=["[beta] A2A Agents"],
    dependencies=[Depends(user_api_key_auth)],
    response_model=AgentResponse,
)
async def update_agent(
    agent_id: str,
    request: AgentConfig,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    Update an existing agent

    Example Request:
    ```bash
    curl -X PUT "http://localhost:4000/agents/123e4567-e89b-12d3-a456-426614174000" \\
        -H "Authorization: Bearer <your_api_key>" \\
        -H "Content-Type: application/json" \\
        -d '{
            "agent": {
                "agent_name": "updated-agent",
                "agent_card_params": {
                    "protocolVersion": "1.0",
                    "name": "Updated Agent",
                    "description": "Updated description",
                    "url": "http://localhost:9999/",
                    "version": "1.1.0",
                    "defaultInputModes": ["text"],
                    "defaultOutputModes": ["text"],
                    "capabilities": {
                        "streaming": true
                    },
                    "skills": []
                },
                "litellm_params": {
                    "make_public": false
                }
            }
        }'
    ```
    """
    await check_feature_access_for_user(user_api_key_dict, "agents")

    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        _check_agent_management_permission(user_api_key_dict)
        raise HTTPException(
            status_code=500, detail=CommonProxyErrors.db_not_connected_error.value
        )

    try:
        # Check if agent exists
        existing_agent = await prisma_client.db.litellm_agentstable.find_unique(
            where={"agent_id": agent_id}
        )
        if existing_agent is not None:
            existing_agent = _agent_row_to_dict(existing_agent)

        if existing_agent is None:
            raise HTTPException(
                status_code=404, detail=f"Agent with ID {agent_id} not found"
            )

        request_data = dict(request)
        target_company_id, target_project_id, target_project_team_obj = (
            await _normalize_agent_tenant_context(
                prisma_client=prisma_client,
                agent_payload=request_data,
                fallback_agent=existing_agent,
            )
        )
        await _authorize_agent_write_context_change(
            user_api_key_dict=user_api_key_dict,
            prisma_client=prisma_client,
            existing_agent=existing_agent,
            target_company_id=target_company_id,
            target_project_id=target_project_id,
            target_project_team_obj=target_project_team_obj,
        )

        # Get the user ID from the API key auth
        updated_by = user_api_key_dict.user_id or "unknown"

        result = await AGENT_REGISTRY.update_agent_in_db(
            agent_id=agent_id,
            agent=request_data,
            prisma_client=prisma_client,
            updated_by=updated_by,
        )
        result = (
            await _enrich_agent_tenant_names([result], prisma_client=prisma_client)
        )[0]

        # deregister in memory
        AGENT_REGISTRY.deregister_agent(agent_name=existing_agent.get("agent_name"))  # type: ignore
        # register in memory
        AGENT_REGISTRY.register_agent(agent_config=result)

        verbose_proxy_logger.info(
            f"Successfully updated agent '{existing_agent.get('agent_name')}' (ID: {agent_id}) in memory"
        )

        return result
    except HTTPException:
        raise
    except Exception as e:
        verbose_proxy_logger.exception(f"Error updating agent: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch(
    "/v1/agents/{agent_id}",
    tags=["[beta] A2A Agents"],
    dependencies=[Depends(user_api_key_auth)],
    response_model=AgentResponse,
)
async def patch_agent(
    agent_id: str,
    request: PatchAgentRequest,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    Update an existing agent

    Example Request:
    ```bash
    curl -X PUT "http://localhost:4000/agents/123e4567-e89b-12d3-a456-426614174000" \\
        -H "Authorization: Bearer <your_api_key>" \\
        -H "Content-Type: application/json" \\
        -d '{
            "agent": {
                "agent_name": "updated-agent",
                "agent_card_params": {
                    "protocolVersion": "1.0",
                    "name": "Updated Agent",
                    "description": "Updated description",
                    "url": "http://localhost:9999/",
                    "version": "1.1.0",
                    "defaultInputModes": ["text"],
                    "defaultOutputModes": ["text"],
                    "capabilities": {
                        "streaming": true
                    },
                    "skills": []
                },
                "litellm_params": {
                    "make_public": false
                }
            }
        }'
    ```
    """
    await check_feature_access_for_user(user_api_key_dict, "agents")

    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        _check_agent_management_permission(user_api_key_dict)
        raise HTTPException(
            status_code=500, detail=CommonProxyErrors.db_not_connected_error.value
        )

    try:
        # Check if agent exists
        existing_agent = await prisma_client.db.litellm_agentstable.find_unique(
            where={"agent_id": agent_id}
        )
        if existing_agent is not None:
            existing_agent = _agent_row_to_dict(existing_agent)

        if existing_agent is None:
            raise HTTPException(
                status_code=404, detail=f"Agent with ID {agent_id} not found"
            )

        request_data = dict(request)
        target_company_id, target_project_id, target_project_team_obj = (
            await _normalize_agent_tenant_context(
                prisma_client=prisma_client,
                agent_payload=request_data,
                fallback_agent=existing_agent,
            )
        )
        await _authorize_agent_write_context_change(
            user_api_key_dict=user_api_key_dict,
            prisma_client=prisma_client,
            existing_agent=existing_agent,
            target_company_id=target_company_id,
            target_project_id=target_project_id,
            target_project_team_obj=target_project_team_obj,
        )

        # Get the user ID from the API key auth
        updated_by = user_api_key_dict.user_id or "unknown"

        result = await AGENT_REGISTRY.patch_agent_in_db(
            agent_id=agent_id,
            agent=request_data,
            prisma_client=prisma_client,
            updated_by=updated_by,
        )
        result = (
            await _enrich_agent_tenant_names([result], prisma_client=prisma_client)
        )[0]

        # deregister in memory
        AGENT_REGISTRY.deregister_agent(agent_name=existing_agent.get("agent_name"))  # type: ignore
        # register in memory
        AGENT_REGISTRY.register_agent(agent_config=result)

        verbose_proxy_logger.info(
            f"Successfully updated agent '{existing_agent.get('agent_name')}' (ID: {agent_id}) in memory"
        )

        return result
    except HTTPException:
        raise
    except Exception as e:
        verbose_proxy_logger.exception(f"Error updating agent: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/v1/agents/{agent_id}",
    tags=["Agents"],
    dependencies=[Depends(user_api_key_auth)],
)
async def delete_agent(
    agent_id: str,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    Delete an agent

    Example Request:
    ```bash
    curl -X DELETE "http://localhost:4000/agents/123e4567-e89b-12d3-a456-426614174000" \\
        -H "Authorization: Bearer <your_api_key>"
    ```

    Example Response:
    ```json
    {
        "message": "Agent 123e4567-e89b-12d3-a456-426614174000 deleted successfully"
    }
    ```
    """
    await check_feature_access_for_user(user_api_key_dict, "agents")

    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        _check_agent_management_permission(user_api_key_dict)
        raise HTTPException(status_code=500, detail="Prisma client not initialized")

    try:
        # Check if agent exists
        existing_agent = await prisma_client.db.litellm_agentstable.find_unique(
            where={"agent_id": agent_id}
        )
        if existing_agent is not None:
            existing_agent = _agent_row_to_dict(existing_agent)

        if existing_agent is None:
            raise HTTPException(
                status_code=404, detail=f"Agent with ID {agent_id} not found in DB."
            )

        company_id, project_id, project_team_obj = await _resolve_agent_project_context(
            prisma_client=prisma_client,
            company_id=existing_agent.get("company_id"),
            project_id=existing_agent.get("project_id"),
        )
        await _authorize_agent_company_project_context(
            user_api_key_dict=user_api_key_dict,
            prisma_client=prisma_client,
            company_id=company_id,
            project_id=project_id,
            project_team_obj=project_team_obj,
            write=True,
        )

        await AGENT_REGISTRY.delete_agent_from_db(
            agent_id=agent_id, prisma_client=prisma_client
        )

        AGENT_REGISTRY.deregister_agent(agent_name=existing_agent.get("agent_name"))  # type: ignore

        return {"message": f"Agent {agent_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        verbose_proxy_logger.exception(f"Error deleting agent: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/v1/agents/{agent_id}/make_public",
    tags=["[beta] A2A Agents"],
    dependencies=[Depends(user_api_key_auth)],
    response_model=AgentMakePublicResponse,
)
async def make_agent_public(
    agent_id: str,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    Make an agent publicly discoverable

    Example Request:
    ```bash
    curl -X POST "http://localhost:4000/v1/agents/123e4567-e89b-12d3-a456-426614174000/make_public" \\
        -H "Authorization: Bearer <your_api_key>" \\
        -H "Content-Type: application/json"
    ```

    Example Response:
    ```json
    {
        "agent_id": "123e4567-e89b-12d3-a456-426614174000",
        "agent_name": "my-custom-agent",
        "litellm_params": {
            "make_public": true
        },
        "agent_card_params": {...},
        "created_at": "2025-11-15T10:30:00Z",
        "updated_at": "2025-11-15T10:35:00Z",
        "created_by": "user123",
        "updated_by": "user123"
    }
    ```
    """
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(
            status_code=500, detail=CommonProxyErrors.db_not_connected_error.value
        )

    try:
        # Update the public model groups
        import litellm
        from litellm.proxy.agent_endpoints.agent_registry import (
            global_agent_registry as AGENT_REGISTRY,
        )
        from litellm.proxy.proxy_server import proxy_config

        # Check if user has admin permissions
        if user_api_key_dict.user_role != LitellmUserRoles.PROXY_ADMIN:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Only proxy admins can update public model groups. Your role={}".format(
                        user_api_key_dict.user_role
                    )
                },
            )

        agent = AGENT_REGISTRY.get_agent_by_id(agent_id=agent_id)
        if agent is None:
            # check if agent exists in DB
            agent = await prisma_client.db.litellm_agentstable.find_unique(
                where={"agent_id": agent_id}
            )
            if agent is not None:
                agent = AgentResponse(**agent.model_dump())  # type: ignore

            if agent is None:
                raise HTTPException(
                    status_code=404, detail=f"Agent with ID {agent_id} not found"
                )

        if litellm.public_agent_groups is None:
            litellm.public_agent_groups = []
        # handle duplicates
        if agent.agent_id in litellm.public_agent_groups:
            raise HTTPException(
                status_code=400,
                detail=f"Agent with name {agent.agent_name} already in public agent groups",
            )
        litellm.public_agent_groups.append(agent.agent_id)

        # Load existing config
        config = await proxy_config.get_config()

        # Update config with new settings
        if "litellm_settings" not in config or config["litellm_settings"] is None:
            config["litellm_settings"] = {}

        config["litellm_settings"]["public_agent_groups"] = litellm.public_agent_groups

        # Save the updated config
        await proxy_config.save_config(new_config=config)

        verbose_proxy_logger.debug(
            f"Updated public agent groups to: {litellm.public_agent_groups} by user: {user_api_key_dict.user_id}"
        )

        return {
            "message": "Successfully updated public agent groups",
            "public_agent_groups": litellm.public_agent_groups,
            "updated_by": user_api_key_dict.user_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        verbose_proxy_logger.exception(f"Error making agent public: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/v1/agents/make_public",
    tags=["[beta] A2A Agents"],
    dependencies=[Depends(user_api_key_auth)],
    response_model=AgentMakePublicResponse,
)
async def make_agents_public(
    request: MakeAgentsPublicRequest,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    Make multiple agents publicly discoverable

    Example Request:
    ```bash
    curl -X POST "http://localhost:4000/v1/agents/make_public" \\
        -H "Authorization: Bearer <your_api_key>" \\
        -H "Content-Type: application/json" \\
        -d '{
            "agent_ids": ["123e4567-e89b-12d3-a456-426614174000", "123e4567-e89b-12d3-a456-426614174001"]
        }'
    ```

    Example Response:
    ```json
    {
        "agent_id": "123e4567-e89b-12d3-a456-426614174000",
        "agent_name": "my-custom-agent",
        "litellm_params": {
            "make_public": true
        },
        "agent_card_params": {...},
        "created_at": "2025-11-15T10:30:00Z",
        "updated_at": "2025-11-15T10:35:00Z",
        "created_by": "user123",
        "updated_by": "user123"
    }
    ```
    """
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(
            status_code=500, detail=CommonProxyErrors.db_not_connected_error.value
        )

    try:
        # Update the public model groups
        import litellm
        from litellm.proxy.agent_endpoints.agent_registry import (
            global_agent_registry as AGENT_REGISTRY,
        )
        from litellm.proxy.proxy_server import proxy_config

        # Load existing config
        config = await proxy_config.get_config()
        # Check if user has admin permissions
        if user_api_key_dict.user_role != LitellmUserRoles.PROXY_ADMIN:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Only proxy admins can update public model groups. Your role={}".format(
                        user_api_key_dict.user_role
                    )
                },
            )

        if litellm.public_agent_groups is None:
            litellm.public_agent_groups = []

        for agent_id in request.agent_ids:
            agent = AGENT_REGISTRY.get_agent_by_id(agent_id=agent_id)
            if agent is None:
                # check if agent exists in DB
                agent = await prisma_client.db.litellm_agentstable.find_unique(
                    where={"agent_id": agent_id}
                )
                if agent is not None:
                    agent = AgentResponse(**agent.model_dump())  # type: ignore

                if agent is None:
                    raise HTTPException(
                        status_code=404, detail=f"Agent with ID {agent_id} not found"
                    )

        litellm.public_agent_groups = request.agent_ids

        # Update config with new settings
        if "litellm_settings" not in config or config["litellm_settings"] is None:
            config["litellm_settings"] = {}

        config["litellm_settings"]["public_agent_groups"] = litellm.public_agent_groups

        # Save the updated config
        await proxy_config.save_config(new_config=config)

        verbose_proxy_logger.debug(
            f"Updated public agent groups to: {litellm.public_agent_groups} by user: {user_api_key_dict.user_id}"
        )

        return {
            "message": "Successfully updated public agent groups",
            "public_agent_groups": litellm.public_agent_groups,
            "updated_by": user_api_key_dict.user_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        verbose_proxy_logger.exception(f"Error making agent public: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/agent/daily/activity",
    tags=["Agent Management"],
    dependencies=[Depends(user_api_key_auth)],
    response_model=SpendAnalyticsPaginatedResponse,
)
async def get_agent_daily_activity(
    agent_ids: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
    exclude_agent_ids: Optional[str] = None,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    Get daily activity for specific agents or all accessible agents.
    """
    await check_feature_access_for_user(user_api_key_dict, "agents")

    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(
            status_code=500,
            detail={"error": CommonProxyErrors.db_not_connected_error.value},
        )

    agent_ids_list = agent_ids.split(",") if agent_ids else None
    exclude_agent_ids_list: Optional[List[str]] = None
    if exclude_agent_ids:
        exclude_agent_ids_list = (
            exclude_agent_ids.split(",") if exclude_agent_ids else None
        )

    # Without scoping, an empty `agent_ids` query returned every agent's
    # spend/token rows on the proxy. Restrict non-admin callers to the
    # agents they're permitted to invoke (or that they created), and
    # intersect their explicit `agent_ids` filter with the same allowlist.
    from litellm.proxy.agent_endpoints.auth.agent_permission_handler import (
        AgentRequestHandler,
    )
    from litellm.proxy.management_endpoints.common_utils import _user_has_admin_view

    where_condition: Dict[str, Any] = {}
    if not _user_has_admin_view(user_api_key_dict):
        permitted_agent_ids = await AgentRequestHandler.get_allowed_agents(
            user_api_key_auth=user_api_key_dict
        )
        # `get_allowed_agents` returns an empty list when the caller's key
        # and team carry no agent restrictions. For activity scoping that's
        # not "see everything" — fall back to the agents the caller
        # created so they cannot enumerate other tenants' agents.
        # Guard against `user_id is None`: a literal None in Prisma
        # `where={"created_by": None}` resolves to ``created_by IS NULL``
        # and would expose every ownerless agent's rows.
        if not permitted_agent_ids:
            if user_api_key_dict.user_id is None:
                permitted_agent_ids = []
            else:
                owned_records = await prisma_client.db.litellm_agentstable.find_many(
                    where={"created_by": user_api_key_dict.user_id}
                )
                permitted_agent_ids = [a.agent_id for a in owned_records]

        if agent_ids_list:
            permitted_agent_id_set = set(permitted_agent_ids)
            agent_ids_list = [
                aid for aid in agent_ids_list if aid in permitted_agent_id_set
            ]
        else:
            agent_ids_list = list(permitted_agent_ids)

        # No accessible agents → return an empty page without querying.
        if not agent_ids_list:
            return SpendAnalyticsPaginatedResponse(
                results=[],
                metadata=DailySpendMetadata(
                    total_spend=0.0,
                    total_prompt_tokens=0,
                    total_completion_tokens=0,
                    total_tokens=0,
                    total_api_requests=0,
                    total_successful_requests=0,
                    total_failed_requests=0,
                    total_cache_read_input_tokens=0,
                    total_cache_creation_input_tokens=0,
                    page=page,
                    total_pages=0,
                    has_more=False,
                ),
            )

    if agent_ids_list:
        where_condition["agent_id"] = {"in": list(agent_ids_list)}

    agent_records = await prisma_client.db.litellm_agentstable.find_many(
        where=where_condition
    )
    agent_metadata = {
        agent.agent_id: {"agent_name": agent.agent_name} for agent in agent_records
    }

    return await get_daily_activity(
        prisma_client=prisma_client,
        table_name="litellm_dailyagentspend",
        entity_id_field="agent_id",
        entity_id=agent_ids_list,
        entity_metadata_field=agent_metadata,
        exclude_entity_ids=exclude_agent_ids_list,
        start_date=start_date,
        end_date=end_date,
        model=model,
        api_key=api_key,
        page=page,
        page_size=page_size,
    )
