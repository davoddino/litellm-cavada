"""
VECTOR STORE MANAGEMENT

All /vector_store management endpoints

/vector_store/new
/vector_store/delete
/vector_store/list
"""

import copy
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

import litellm
from litellm._logging import verbose_proxy_logger
from litellm.caching.in_memory_cache import InMemoryCache
from litellm.constants import REDACTED_BY_LITELM_STRING
from litellm.litellm_core_utils.safe_json_dumps import safe_dumps
from litellm.litellm_core_utils.sensitive_data_masker import SensitiveDataMasker
from litellm.proxy._types import (
    LiteLLM_ManagedVectorStoresTable,
    LitellmUserRoles,
    ResponseLiteLLM_ManagedVectorStore,
    UserAPIKeyAuth,
)
from litellm.proxy.auth.user_api_key_auth import user_api_key_auth
from litellm.proxy.common_utils.encrypt_decrypt_utils import decrypt_value_helper
from litellm.proxy.common_utils.rbac_utils import check_feature_access_for_user
from litellm.proxy.vector_store_endpoints.utils import can_user_access_vector_store
from litellm.secret_managers.main import get_secret
from litellm.types.vector_stores import (
    LiteLLM_ManagedVectorStore,
    LiteLLM_ManagedVectorStoreListResponse,
    VectorStoreDeleteRequest,
    VectorStoreInfoRequest,
    VectorStoreUpdateRequest,
)
from litellm.vector_stores.vector_store_registry import VectorStoreRegistry

router = APIRouter()

_LITELLM_PARAMS_MASKER = SensitiveDataMasker()


_REDACT_LITELLM_PARAMS_MAX_DEPTH = 10

# Use-time embedding-config resolution runs on every vector-store request
# whose persisted row carries only a model reference (the post-fix shape).
# Without a cache, that's one ``litellm_proxymodeltable.find_first`` per
# request — the no-DB-in-critical-path rule. Hold the resolved config in
# memory for a short TTL so a hot model name pays the DB lookup at most
# once per ``_EMBEDDING_CONFIG_CACHE_TTL`` seconds. Cleartext credentials
# only ever live in process memory (never persisted, never echoed in
# management responses), so the cache doesn't widen the disclosure surface.
_EMBEDDING_CONFIG_CACHE_TTL = 60
_EMBEDDING_CONFIG_CACHE_MAX_SIZE = 256
_embedding_config_cache: Optional[InMemoryCache] = None


def _get_embedding_config_cache() -> InMemoryCache:
    global _embedding_config_cache
    if _embedding_config_cache is None:
        _embedding_config_cache = InMemoryCache(
            max_size_in_memory=_EMBEDDING_CONFIG_CACHE_MAX_SIZE,
            default_ttl=_EMBEDDING_CONFIG_CACHE_TTL,
        )
    return _embedding_config_cache


def _redact_sensitive_litellm_params(litellm_params: Any, _depth: int = 0) -> Any:
    """
    Replace credential-bearing values in ``litellm_params`` with
    ``REDACTED_BY_LITELM`` while preserving non-secret keys (``api_base``,
    ``region``, ``model``, ``api_version``).

    Handles three input shapes:

    * ``dict`` — recurse into nested dicts (e.g. ``litellm_embedding_config``
      which itself carries ``api_key`` / ``aws_*`` / ``vertex_credentials``).
    * ``str`` — the in-memory registry occasionally holds the params as a
      JSON-serialized string. Parse, redact, re-serialize. If parsing
      fails, return the redaction sentinel rather than echo the value
      back verbatim.
    * Anything else, or ``None`` — passed through.

    Recursion depth is bounded by ``_REDACT_LITELLM_PARAMS_MAX_DEPTH`` —
    matching the convention of other allowlisted recursive helpers in the
    repo (see ``tests/code_coverage_tests/recursive_detector.py``).
    """
    if _depth >= _REDACT_LITELLM_PARAMS_MAX_DEPTH:
        return REDACTED_BY_LITELM_STRING
    if litellm_params is None:
        return None
    if isinstance(litellm_params, str):
        try:
            parsed = json.loads(litellm_params)
        except (TypeError, ValueError):
            return REDACTED_BY_LITELM_STRING
        return json.dumps(_redact_sensitive_litellm_params(parsed, _depth + 1))
    if not isinstance(litellm_params, dict):
        return litellm_params
    out: Dict[str, Any] = {}
    for k, v in litellm_params.items():
        if _LITELLM_PARAMS_MASKER.is_sensitive_key(k):
            out[k] = REDACTED_BY_LITELM_STRING
        elif isinstance(v, dict):
            out[k] = _redact_sensitive_litellm_params(v, _depth + 1)
        else:
            out[k] = v
    return out


async def _fetch_and_authorize_vector_store(
    vector_store_id: str,
    user_api_key_dict: UserAPIKeyAuth,
    prisma_client: Any,
) -> "LiteLLM_ManagedVectorStore":
    """
    Look up a vector store by id and confirm the caller can access it.
    Raises HTTPException(404) on miss and HTTPException(403) on access
    denial.
    """
    row = await prisma_client.db.litellm_managedvectorstorestable.find_unique(
        where={"vector_store_id": vector_store_id}
    )
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Vector store with ID {vector_store_id} not found",
        )
    typed = LiteLLM_ManagedVectorStore(**row.model_dump())
    if not await _can_user_access_vector_store_with_company_project(
        vector_store=typed,
        user_api_key_dict=user_api_key_dict,
        prisma_client=prisma_client,
    ):
        raise HTTPException(
            status_code=403,
            detail="Access denied: You do not have permission to access this vector store",
        )
    return typed


def _resolve_embedding_config_from_router(
    embedding_model: str, llm_router
) -> Optional[Dict[str, Any]]:
    """
    Resolve embedding config from router's config-defined models.

    Config-defined models (from proxy_config.yaml) are stored in the router's model_list,
    not in the database. This function looks up the model in the router and extracts
    api_key, api_base, and api_version from the deployment's litellm_params.

    Args:
        embedding_model: The embedding model string (e.g., "text-embedding-ada-002" or "azure/text-embedding-3-large")
        llm_router: The LiteLLM router instance

    Returns:
        Dictionary with api_key, api_base, and api_version if model found, None otherwise
    """
    if not embedding_model or llm_router is None:
        return None

    # Extract model name candidates - could be "text-embedding-ada-002" or "azure/text-embedding-3-large"
    # Try exact match first, then try without provider prefix
    model_name_candidates = [embedding_model]
    if "/" in embedding_model:
        # If it has a provider prefix, also try without it
        _, model_name = embedding_model.split("/", 1)
        model_name_candidates.append(model_name)

    # Try to find model in router
    for model_name in model_name_candidates:
        try:
            # Try to get deployment by model group name (model_name in config)
            deployment = llm_router.get_deployment_by_model_group_name(
                model_group_name=model_name
            )

            if deployment is not None and deployment.litellm_params is not None:
                litellm_params = deployment.litellm_params

                # Build embedding config from model params
                embedding_config: Dict[str, Any] = {}

                # Extract api_key
                api_key = getattr(litellm_params, "api_key", None)
                if api_key:
                    # Handle os.environ/ prefix
                    if isinstance(api_key, str) and api_key.startswith("os.environ/"):
                        api_key = get_secret(api_key)
                    embedding_config["api_key"] = api_key

                # Extract api_base
                api_base = getattr(litellm_params, "api_base", None)
                if api_base:
                    # Handle os.environ/ prefix
                    if isinstance(api_base, str) and api_base.startswith("os.environ/"):
                        api_base = get_secret(api_base)
                    embedding_config["api_base"] = api_base

                # Extract api_version
                api_version = getattr(litellm_params, "api_version", None)
                if api_version:
                    embedding_config["api_version"] = api_version

                project_id = getattr(litellm_params, "project_id", None)
                if project_id:
                    embedding_config["project_id"] = project_id

                # Only return config if we have at least api_key or api_base
                if embedding_config:
                    verbose_proxy_logger.debug(
                        f"Resolved embedding config from router model {model_name}: {list(embedding_config.keys())}"
                    )
                    return embedding_config
        except Exception as e:
            verbose_proxy_logger.debug(
                f"Error resolving embedding config from router for model {model_name}: {str(e)}"
            )
            continue

    return None


async def _resolve_embedding_config_from_db(
    embedding_model: str, prisma_client
) -> Optional[Dict[str, Any]]:
    """
    Resolve embedding config from database model configuration.

    If litellm_embedding_model is provided but litellm_embedding_config is not,
    this function looks up the model in the database and extracts api_key, api_base,
    and api_version from the model's litellm_params to build the embedding config.

    Args:
        embedding_model: The embedding model string (e.g., "text-embedding-ada-002" or "azure/text-embedding-3-large")
        prisma_client: The Prisma client instance

    Returns:
        Dictionary with api_key, api_base, and api_version if model found, None otherwise
    """
    if not embedding_model:
        return None

    # Extract model name - could be "text-embedding-ada-002" or "azure/text-embedding-3-large"
    # Try to find model by exact match first, then try without provider prefix
    model_name_candidates = [embedding_model]
    if "/" in embedding_model:
        # If it has a provider prefix, also try without it
        _, model_name = embedding_model.split("/", 1)
        model_name_candidates.append(model_name)

    # Try to find model in database
    for model_name in model_name_candidates:
        try:
            db_model = await prisma_client.db.litellm_proxymodeltable.find_first(
                where={"model_name": model_name}
            )

            if db_model and db_model.litellm_params:
                # Extract litellm_params (could be dict or JSON string)
                model_params = db_model.litellm_params
                if isinstance(model_params, str):
                    model_params = json.loads(model_params)

                # Decrypt values from database (similar to how proxy_server.py does it)
                # Values stored in DB are encrypted, so we need to decrypt them first
                decrypted_params = {}
                if isinstance(model_params, dict):
                    for k, v in model_params.items():
                        if isinstance(v, str):
                            # Decrypt value - returns original value if decryption fails or no key is set
                            decrypted_value = decrypt_value_helper(
                                value=v, key=k, return_original_value=True
                            )
                            decrypted_params[k] = decrypted_value
                        else:
                            decrypted_params[k] = v
                else:
                    decrypted_params = model_params

                # Build embedding config from model params
                embedding_config = {}

                # Extract api_key
                api_key = decrypted_params.get("api_key")
                if api_key:
                    # Handle os.environ/ prefix (after decryption, values may be os.environ/ prefixed)
                    if isinstance(api_key, str) and api_key.startswith("os.environ/"):
                        api_key = get_secret(api_key)
                    embedding_config["api_key"] = api_key

                # Extract api_base
                api_base = decrypted_params.get("api_base")
                if api_base:
                    # Handle os.environ/ prefix (after decryption, values may be os.environ/ prefixed)
                    if isinstance(api_base, str) and api_base.startswith("os.environ/"):
                        api_base = get_secret(api_base)
                    embedding_config["api_base"] = api_base

                # Extract api_version
                api_version = decrypted_params.get("api_version")
                if api_version:
                    embedding_config["api_version"] = api_version

                # Only return config if we have at least api_key or api_base
                if embedding_config:
                    verbose_proxy_logger.debug(
                        f"Resolved embedding config from database model {model_name}: {list(embedding_config.keys())}"
                    )
                    return embedding_config
        except Exception as e:
            verbose_proxy_logger.debug(
                f"Error resolving embedding config for model {model_name}: {str(e)}"
            )
            continue

    return None


async def _resolve_embedding_config(
    embedding_model: str, prisma_client, llm_router=None
) -> Optional[Dict[str, Any]]:
    """
    Resolve embedding config from either router (config-defined) or database models.

    This function first checks the router for config-defined models, then falls back
    to the database. This allows users to use models defined in either location.

    Results are cached in process memory for ``_EMBEDDING_CONFIG_CACHE_TTL``
    seconds so the request-handling path doesn't hit the database on every
    vector-store call. Negative results (model not found) are intentionally
    not cached to avoid blocking a freshly-added model behind the TTL.

    Args:
        embedding_model: The embedding model string (e.g., "text-embedding-ada-002" or "azure/text-embedding-3-large")
        prisma_client: The Prisma client instance
        llm_router: The LiteLLM router instance (optional, will be imported if not provided)

    Returns:
        Dictionary with api_key, api_base, and api_version if model found, None otherwise
    """
    if not embedding_model:
        return None

    cache = _get_embedding_config_cache()
    cached = cache.get_cache(embedding_model)
    if cached is not None:
        return cached

    # Import llm_router if not provided
    if llm_router is None:
        try:
            from litellm.proxy.proxy_server import llm_router
        except ImportError:
            llm_router = None

    # First try to resolve from router (config-defined models)
    if llm_router is not None:
        router_config = _resolve_embedding_config_from_router(
            embedding_model=embedding_model, llm_router=llm_router
        )
        if router_config:
            verbose_proxy_logger.debug(
                f"Resolved embedding config from router for model {embedding_model}"
            )
            cache.set_cache(embedding_model, router_config)
            return router_config

    # Fall back to database
    if prisma_client is not None:
        db_config = await _resolve_embedding_config_from_db(
            embedding_model=embedding_model, prisma_client=prisma_client
        )
        if db_config:
            verbose_proxy_logger.debug(
                f"Resolved embedding config from database for model {embedding_model}"
            )
            cache.set_cache(embedding_model, db_config)
            return db_config

    verbose_proxy_logger.debug(
        f"Could not resolve embedding config for model {embedding_model} from router or database"
    )
    return None


########################################################
# Helper Functions
########################################################
async def _check_vector_store_access(
    vector_store: LiteLLM_ManagedVectorStore,
    user_api_key_dict: UserAPIKeyAuth,
) -> bool:
    """
    Check if the user has access to the vector store.

    Delegates to :func:`can_user_access_vector_store`, which honors:
    - PROXY_ADMIN bypass
    - legacy vector stores with no team_id
    - key-level and team-level ``object_permission.vector_stores`` allowlists
    - team_id match between key and store
    """
    return await can_user_access_vector_store(
        vector_store=vector_store, user_api_key_dict=user_api_key_dict
    )


def _get_field_value(value: Any, field_name: str) -> Any:
    if isinstance(value, dict):
        return value.get(field_name)
    return getattr(value, field_name, None)


def _is_proxy_admin(user_api_key_dict: UserAPIKeyAuth) -> bool:
    return user_api_key_dict.user_role in (
        LitellmUserRoles.PROXY_ADMIN,
        LitellmUserRoles.PROXY_ADMIN.value,
    )


def _company_id_from_team(team: Any) -> Optional[str]:
    return _get_field_value(team, "organization_id") if team is not None else None


async def _resolve_vector_store_project_context(
    *,
    prisma_client: Any,
    project_id: Optional[str],
    company_id: Optional[str],
    user_api_key_dict: UserAPIKeyAuth,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    if project_id is None:
        if company_id is not None:
            raise HTTPException(
                status_code=400,
                detail="project_id is required when company_id is provided",
            )
        return None, company_id, None

    project = await prisma_client.db.litellm_projecttable.find_unique(
        where={"project_id": project_id},
        include={"litellm_team_table": True},
    )
    if project is None:
        raise HTTPException(
            status_code=404,
            detail=f"Project not found: {project_id}",
        )

    team = _get_field_value(project, "litellm_team_table")
    team_id = _get_field_value(project, "team_id")
    if team is None and team_id is not None:
        team = await prisma_client.db.litellm_teamtable.find_unique(
            where={"team_id": team_id}
        )

    if team_id is None:
        raise HTTPException(
            status_code=400,
            detail="Project must have a backing team before it can own vector stores",
        )

    project_company_id = _get_field_value(project, "company_id") or _company_id_from_team(
        team
    )
    if company_id is not None and project_company_id != company_id:
        raise HTTPException(
            status_code=400,
            detail=(
                f"project_id={project_id} belongs to company_id={project_company_id}; "
                f"received company_id={company_id}"
            ),
        )

    if _is_proxy_admin(user_api_key_dict) or user_api_key_dict.team_id == team_id:
        return team_id, project_company_id, _get_field_value(project, "project_alias")

    if user_api_key_dict.user_id and project_company_id:
        membership = (
            await prisma_client.db.litellm_organizationmembership.find_unique(
                where={
                    "user_id_organization_id": {
                        "user_id": user_api_key_dict.user_id,
                        "organization_id": project_company_id,
                    }
                }
            )
        )
        if (
            membership is not None
            and _get_field_value(membership, "user_role")
            == LitellmUserRoles.ORG_ADMIN.value
        ):
            return team_id, project_company_id, _get_field_value(
                project, "project_alias"
            )

    raise HTTPException(
        status_code=403,
        detail="Access denied: You do not have permission to manage vector stores for this Project",
    )


async def _get_vector_store_company_id(
    *,
    vector_store: LiteLLM_ManagedVectorStore,
    prisma_client: Any,
) -> Optional[str]:
    project_id = _get_field_value(vector_store, "project_id")
    if project_id:
        project = await prisma_client.db.litellm_projecttable.find_unique(
            where={"project_id": project_id},
            include={"litellm_team_table": True},
        )
        if project is not None:
            team = _get_field_value(project, "litellm_team_table")
            return _get_field_value(project, "company_id") or _company_id_from_team(
                team
            )

    team_id = _get_field_value(vector_store, "team_id")
    if not team_id:
        return None
    team = await prisma_client.db.litellm_teamtable.find_unique(
        where={"team_id": team_id}
    )
    return _company_id_from_team(team)


async def _can_user_access_vector_store_with_company_project(
    *,
    vector_store: LiteLLM_ManagedVectorStore,
    user_api_key_dict: UserAPIKeyAuth,
    prisma_client: Any,
) -> bool:
    if await _check_vector_store_access(vector_store, user_api_key_dict):
        return True
    if _is_proxy_admin(user_api_key_dict):
        return True

    company_id = await _get_vector_store_company_id(
        vector_store=vector_store,
        prisma_client=prisma_client,
    )
    if not company_id or not user_api_key_dict.user_id:
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
        and _get_field_value(membership, "user_role")
        == LitellmUserRoles.ORG_ADMIN.value
    )


async def _enrich_vector_store_contexts(
    *,
    vector_stores: List[LiteLLM_ManagedVectorStore],
    prisma_client: Any,
) -> List[LiteLLM_ManagedVectorStore]:
    if not vector_stores:
        return vector_stores

    project_ids = sorted(
        {
            project_id
            for project_id in (
                _get_field_value(vector_store, "project_id")
                for vector_store in vector_stores
            )
            if project_id
        }
    )
    team_ids = sorted(
        {
            team_id
            for team_id in (
                _get_field_value(vector_store, "team_id")
                for vector_store in vector_stores
            )
            if team_id
        }
    )

    projects_by_id: Dict[str, Any] = {}
    if project_ids:
        projects = await prisma_client.db.litellm_projecttable.find_many(
            where={"project_id": {"in": project_ids}},
            include={"litellm_team_table": True},
        )
        projects_by_id = {
            _get_field_value(project, "project_id"): project for project in projects
        }

    teams_by_id: Dict[str, Any] = {}
    if team_ids:
        teams = await prisma_client.db.litellm_teamtable.find_many(
            where={"team_id": {"in": team_ids}}
        )
        teams_by_id = {_get_field_value(team, "team_id"): team for team in teams}

    company_ids = set()
    for project in projects_by_id.values():
        team = _get_field_value(project, "litellm_team_table")
        company_id = _get_field_value(project, "company_id") or _company_id_from_team(
            team
        )
        if company_id:
            company_ids.add(company_id)
    for team in teams_by_id.values():
        company_id = _company_id_from_team(team)
        if company_id:
            company_ids.add(company_id)

    companies_by_id: Dict[str, Any] = {}
    if company_ids:
        companies = await prisma_client.db.litellm_organizationtable.find_many(
            where={"organization_id": {"in": sorted(company_ids)}}
        )
        companies_by_id = {
            _get_field_value(company, "organization_id"): company
            for company in companies
        }

    enriched: List[LiteLLM_ManagedVectorStore] = []
    for vector_store in vector_stores:
        vector_store_dict = LiteLLM_ManagedVectorStore(**dict(vector_store))
        project = projects_by_id.get(vector_store_dict.get("project_id"))
        team = None
        company_id = None

        if project is not None:
            vector_store_dict["project_name"] = _get_field_value(
                project, "project_alias"
            )
            team = _get_field_value(project, "litellm_team_table")
            company_id = _get_field_value(project, "company_id") or _company_id_from_team(
                team
            )

        if company_id is None:
            team = teams_by_id.get(vector_store_dict.get("team_id")) or team
            company_id = _company_id_from_team(team)

        if company_id is not None:
            vector_store_dict["company_id"] = company_id
            company = companies_by_id.get(company_id)
            company_name = _get_field_value(
                company, "organization_alias"
            ) or _get_field_value(company, "company_name")
            if company_name:
                vector_store_dict["company_name"] = company_name

        enriched.append(vector_store_dict)

    return enriched


async def _enrich_vector_store_context(
    *,
    vector_store: LiteLLM_ManagedVectorStore,
    prisma_client: Any,
) -> LiteLLM_ManagedVectorStore:
    enriched = await _enrich_vector_store_contexts(
        vector_stores=[vector_store],
        prisma_client=prisma_client,
    )
    return enriched[0]


async def create_vector_store_in_db(
    vector_store_id: str,
    custom_llm_provider: str,
    prisma_client,
    vector_store_name: Optional[str] = None,
    vector_store_description: Optional[str] = None,
    vector_store_metadata: Optional[Dict] = None,
    litellm_params: Optional[Dict] = None,
    litellm_credential_name: Optional[str] = None,
    team_id: Optional[str] = None,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> LiteLLM_ManagedVectorStore:
    """
    Helper function to create a vector store in the database.

    This function handles:
    - Checking if vector store already exists
    - Creating the vector store in the database
    - Adding it to the vector store registry

    Returns:
        LiteLLM_ManagedVectorStore: The created vector store object

    Raises:
        HTTPException: If vector store already exists or database error occurs
    """
    from litellm.types.router import GenericLiteLLMParams

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    # Check if vector store already exists
    existing_vector_store = (
        await prisma_client.db.litellm_managedvectorstorestable.find_unique(
            where={"vector_store_id": vector_store_id}
        )
    )
    if existing_vector_store is not None:
        raise HTTPException(
            status_code=400,
            detail=f"Vector store with ID {vector_store_id} already exists",
        )

    # Prepare data for database
    data_to_create: Dict[str, Any] = {
        "vector_store_id": vector_store_id,
        "custom_llm_provider": custom_llm_provider,
    }

    if vector_store_name is not None:
        data_to_create["vector_store_name"] = vector_store_name
    if vector_store_description is not None:
        data_to_create["vector_store_description"] = vector_store_description
    if vector_store_metadata is not None:
        data_to_create["vector_store_metadata"] = safe_dumps(vector_store_metadata)
    if litellm_credential_name is not None:
        data_to_create["litellm_credential_name"] = litellm_credential_name
    if team_id is not None:
        data_to_create["team_id"] = team_id
    if project_id is not None:
        data_to_create["project_id"] = project_id
    if user_id is not None:
        data_to_create["user_id"] = user_id

    # Handle litellm_params - always provide at least an empty dict.
    # The earlier behaviour resolved ``litellm_embedding_config`` from the
    # admin-configured router/DB model and persisted the cleartext result
    # (``api_key``, ``api_base``, ``api_version``) into this row. That
    # exposed every env-stored embedding-model credential on the
    # ``/vector_store/{new,info,update,list}`` responses. Keep the user's
    # raw ``litellm_embedding_model`` reference; resolution now happens in
    # ``_update_request_data_with_litellm_managed_vector_store_registry``
    # at request-handling time so the cleartext config exists only in
    # per-request memory and never reaches the database.
    if litellm_params:
        litellm_params_dict = GenericLiteLLMParams(**litellm_params).model_dump(
            exclude_none=True
        )
        data_to_create["litellm_params"] = safe_dumps(litellm_params_dict)
    else:
        # Provide empty dict if no litellm_params provided
        data_to_create["litellm_params"] = safe_dumps({})

    # Create in database
    _new_vector_store = await prisma_client.db.litellm_managedvectorstorestable.create(
        data=data_to_create
    )

    new_vector_store: LiteLLM_ManagedVectorStore = LiteLLM_ManagedVectorStore(
        **_new_vector_store.model_dump()
    )

    # Add vector store to registry
    if litellm.vector_store_registry is not None:
        litellm.vector_store_registry.add_vector_store_to_registry(
            vector_store=new_vector_store
        )

    verbose_proxy_logger.info(
        f"Vector store {vector_store_id} created in database successfully"
    )

    return new_vector_store


########################################################
# Management Endpoints
########################################################
@router.post(
    "/vector_store/new",
    tags=["vector store management"],
    dependencies=[Depends(user_api_key_auth)],
)
async def new_vector_store(
    vector_store: LiteLLM_ManagedVectorStore,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    Create a new vector store.

    Parameters:
    - vector_store_id: str - Unique identifier for the vector store
    - custom_llm_provider: str - Provider of the vector store
    - vector_store_name: Optional[str] - Name of the vector store
    - vector_store_description: Optional[str] - Description of the vector store
    - vector_store_metadata: Optional[Dict] - Additional metadata for the vector store
    """
    await check_feature_access_for_user(user_api_key_dict, "vector_stores")

    from litellm.proxy.proxy_server import prisma_client

    try:
        vector_store_id = vector_store.get("vector_store_id")
        custom_llm_provider = vector_store.get("custom_llm_provider")
        company_id = vector_store.get("company_id")
        project_id = vector_store.get("project_id")

        if not vector_store_id or not custom_llm_provider:
            raise HTTPException(
                status_code=400,
                detail="vector_store_id and custom_llm_provider are required",
            )

        project_team_id, _, _ = await _resolve_vector_store_project_context(
            prisma_client=prisma_client,
            project_id=project_id,
            company_id=company_id,
            user_api_key_dict=user_api_key_dict,
        )

        # Extract and validate metadata
        metadata = vector_store.get("vector_store_metadata")
        validated_metadata: Optional[Dict] = None
        if metadata is not None and isinstance(metadata, dict):
            validated_metadata = metadata

        new_vector_store = await create_vector_store_in_db(
            vector_store_id=vector_store_id,
            custom_llm_provider=custom_llm_provider,
            prisma_client=prisma_client,
            vector_store_name=vector_store.get("vector_store_name"),
            vector_store_description=vector_store.get("vector_store_description"),
            vector_store_metadata=validated_metadata,
            litellm_params=vector_store.get("litellm_params"),
            litellm_credential_name=vector_store.get("litellm_credential_name"),
            team_id=project_team_id or user_api_key_dict.team_id,
            project_id=project_id,
            user_id=user_api_key_dict.user_id,
        )

        # Apply the same litellm_params redaction the list / info / update
        # endpoints already use, so a caller-supplied credential or a
        # cleartext value persisted by an earlier proxy version doesn't
        # come back in the response.
        response_vs = LiteLLM_ManagedVectorStore(**new_vector_store)
        response_vs["litellm_params"] = _redact_sensitive_litellm_params(
            new_vector_store.get("litellm_params")
        )
        response_vs = await _enrich_vector_store_context(
            vector_store=response_vs,
            prisma_client=prisma_client,
        )

        return {
            "status": "success",
            "message": f"Vector store {vector_store.get('vector_store_id')} created successfully",
            "vector_store": response_vs,
        }
    except HTTPException:
        raise
    except Exception as e:
        verbose_proxy_logger.exception(f"Error creating vector store: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/vector_store/list",
    tags=["vector store management"],
    dependencies=[Depends(user_api_key_auth)],
    response_model=LiteLLM_ManagedVectorStoreListResponse,
)
@router.get(
    "/v1/vector_store/list",
    tags=["vector store management"],
    dependencies=[Depends(user_api_key_auth)],
    response_model=LiteLLM_ManagedVectorStoreListResponse,
)
async def list_vector_stores(
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
    page: int = 1,
    page_size: int = 100,
    company_id: Optional[str] = None,
    project_id: Optional[str] = None,
):
    """
    List all available vector stores with optional filtering and pagination.
    Combines both in-memory vector stores and those stored in the database.
    Database is the source of truth - deleted stores are removed from memory, updated stores sync to memory.

    Parameters:
    - page: int - Page number for pagination (default: 1)
    - page_size: int - Number of items per page (default: 100)
    """
    await check_feature_access_for_user(user_api_key_dict, "vector_stores")

    from litellm.proxy.proxy_server import prisma_client

    vector_store_map: Dict[str, LiteLLM_ManagedVectorStore] = {}
    db_vector_store_ids: set = set()

    try:
        if project_id is not None:
            await _resolve_vector_store_project_context(
                prisma_client=prisma_client,
                project_id=project_id,
                company_id=company_id,
                user_api_key_dict=user_api_key_dict,
            )

        # Get vector stores from database first (source of truth)
        vector_stores_from_db = await VectorStoreRegistry._get_vector_stores_from_db(
            prisma_client=prisma_client
        )

        # Build map from database vector stores
        for vector_store in vector_stores_from_db:
            vector_store_id = vector_store.get("vector_store_id", None)
            if vector_store_id:
                vector_store_map[vector_store_id] = vector_store
                db_vector_store_ids.add(vector_store_id)

        # Process in-memory vector stores
        if litellm.vector_store_registry is not None:
            in_memory_vector_stores = copy.deepcopy(
                litellm.vector_store_registry.vector_stores
            )

            vector_stores_to_delete_from_memory: List[str] = []

            for vector_store in in_memory_vector_stores:
                vector_store_id = vector_store.get("vector_store_id", None)
                if not vector_store_id:
                    continue

                # If vector store is in memory but NOT in database, it was deleted
                if vector_store_id not in db_vector_store_ids:
                    verbose_proxy_logger.info(
                        f"Vector store {vector_store_id} exists in memory but not in database - marking for deletion from cache"
                    )
                    vector_stores_to_delete_from_memory.append(vector_store_id)
                # If not in our map yet, add it (only in-memory, not in DB)
                elif vector_store_id not in vector_store_map:
                    vector_store_map[vector_store_id] = vector_store

            # Synchronize in-memory registry with database
            # 1. Remove deleted vector stores from memory
            for vs_id in vector_stores_to_delete_from_memory:
                litellm.vector_store_registry.delete_vector_store_from_registry(
                    vector_store_id=vs_id
                )
                verbose_proxy_logger.debug(
                    f"Removed deleted vector store {vs_id} from in-memory registry"
                )

            # 2. Update in-memory registry with database versions (for updates)
            for vector_store in vector_stores_from_db:
                vector_store_id = vector_store.get("vector_store_id", None)
                if vector_store_id:
                    litellm.vector_store_registry.update_vector_store_in_registry(
                        vector_store_id=vector_store_id, updated_data=vector_store
                    )

        # Filter vector stores based on access control
        accessible_vector_stores = []
        for vs in vector_store_map.values():
            if await _can_user_access_vector_store_with_company_project(
                vector_store=vs,
                user_api_key_dict=user_api_key_dict,
                prisma_client=prisma_client,
            ):
                redacted = LiteLLM_ManagedVectorStore(**vs)
                redacted["litellm_params"] = _redact_sensitive_litellm_params(
                    vs.get("litellm_params")
                )
                accessible_vector_stores.append(redacted)

        accessible_vector_stores = await _enrich_vector_store_contexts(
            vector_stores=accessible_vector_stores,
            prisma_client=prisma_client,
        )
        if company_id is not None:
            accessible_vector_stores = [
                vs
                for vs in accessible_vector_stores
                if _get_field_value(vs, "company_id") == company_id
            ]
        if project_id is not None:
            accessible_vector_stores = [
                vs
                for vs in accessible_vector_stores
                if _get_field_value(vs, "project_id") == project_id
            ]

        total_count = len(accessible_vector_stores)
        total_pages = (total_count + page_size - 1) // page_size

        # Format response using LiteLLM_ManagedVectorStoreListResponse
        response = LiteLLM_ManagedVectorStoreListResponse(
            object="list",
            data=accessible_vector_stores,
            total_count=total_count,
            current_page=page,
            total_pages=total_pages,
        )

        return response
    except HTTPException:
        raise
    except Exception as e:
        verbose_proxy_logger.exception(f"Error listing vector stores: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/vector_store/delete",
    tags=["vector store management"],
    dependencies=[Depends(user_api_key_auth)],
)
async def delete_vector_store(
    data: VectorStoreDeleteRequest,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    Delete a vector store from both database and in-memory registry.

    Parameters:
    - vector_store_id: str - ID of the vector store to delete
    """
    await check_feature_access_for_user(user_api_key_dict, "vector_stores")

    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    try:
        # Check if vector store exists in database or in-memory registry
        db_vector_store_exists = False
        memory_vector_store_exists = False
        vector_store_to_check = None

        existing_vector_store = (
            await prisma_client.db.litellm_managedvectorstorestable.find_unique(
                where={"vector_store_id": data.vector_store_id}
            )
        )
        if existing_vector_store is not None:
            db_vector_store_exists = True
            vector_store_to_check = LiteLLM_ManagedVectorStore(
                **existing_vector_store.model_dump()
            )

        # Check in-memory registry
        if litellm.vector_store_registry is not None:
            memory_vector_store = litellm.vector_store_registry.get_litellm_managed_vector_store_from_registry(
                vector_store_id=data.vector_store_id
            )
            if memory_vector_store is not None:
                memory_vector_store_exists = True
                if vector_store_to_check is None:
                    vector_store_to_check = memory_vector_store

        # If not found in either location, raise 404
        if not db_vector_store_exists and not memory_vector_store_exists:
            raise HTTPException(
                status_code=404,
                detail=f"Vector store with ID {data.vector_store_id} not found",
            )

        # Check access control
        if vector_store_to_check and not await _can_user_access_vector_store_with_company_project(
            vector_store=vector_store_to_check,
            user_api_key_dict=user_api_key_dict,
            prisma_client=prisma_client,
        ):
            raise HTTPException(
                status_code=403,
                detail="Access denied: You do not have permission to delete this vector store",
            )

        # Delete from database if exists
        if db_vector_store_exists:
            await prisma_client.db.litellm_managedvectorstorestable.delete(
                where={"vector_store_id": data.vector_store_id}
            )

        # Delete from in-memory registry if exists
        if memory_vector_store_exists and litellm.vector_store_registry is not None:
            litellm.vector_store_registry.delete_vector_store_from_registry(
                vector_store_id=data.vector_store_id
            )

        return {
            "status": "success",
            "message": f"Vector store {data.vector_store_id} deleted successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        verbose_proxy_logger.exception(f"Error deleting vector store: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/vector_store/info",
    tags=["vector store management"],
    dependencies=[Depends(user_api_key_auth)],
    response_model=ResponseLiteLLM_ManagedVectorStore,
)
async def get_vector_store_info(
    data: VectorStoreInfoRequest,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """Return a single vector store's details"""
    await check_feature_access_for_user(user_api_key_dict, "vector_stores")

    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    try:
        if litellm.vector_store_registry is not None:
            vector_store = litellm.vector_store_registry.get_litellm_managed_vector_store_from_registry(
                vector_store_id=data.vector_store_id
            )
            if vector_store is not None:
                # Check access control
                if not await _can_user_access_vector_store_with_company_project(
                    vector_store=vector_store,
                    user_api_key_dict=user_api_key_dict,
                    prisma_client=prisma_client,
                ):
                    raise HTTPException(
                        status_code=403,
                        detail="Access denied: You do not have permission to access this vector store",
                    )

                vector_store_metadata = vector_store.get("vector_store_metadata")
                # Parse metadata if it's a JSON string
                parsed_metadata: Optional[dict] = None
                if isinstance(vector_store_metadata, str):
                    parsed_metadata = json.loads(vector_store_metadata)
                elif isinstance(vector_store_metadata, dict):
                    parsed_metadata = vector_store_metadata

                vector_store_payload = LiteLLM_ManagedVectorStore(
                    vector_store_id=vector_store.get("vector_store_id") or "",
                    custom_llm_provider=vector_store.get("custom_llm_provider") or "",
                    vector_store_name=vector_store.get("vector_store_name") or None,
                    vector_store_description=vector_store.get(
                        "vector_store_description"
                    )
                    or None,
                    vector_store_metadata=parsed_metadata,
                    created_at=vector_store.get("created_at") or None,
                    updated_at=vector_store.get("updated_at") or None,
                    litellm_credential_name=vector_store.get("litellm_credential_name"),
                    litellm_params=_redact_sensitive_litellm_params(
                        vector_store.get("litellm_params")
                    ),
                    team_id=vector_store.get("team_id") or None,
                    project_id=vector_store.get("project_id") or None,
                    user_id=vector_store.get("user_id") or None,
                )
                vector_store_payload = await _enrich_vector_store_context(
                    vector_store=vector_store_payload,
                    prisma_client=prisma_client,
                )
                vector_store_pydantic_obj = LiteLLM_ManagedVectorStoresTable(
                    **vector_store_payload
                )
                return {"vector_store": vector_store_pydantic_obj}

        vector_store_typed = await _fetch_and_authorize_vector_store(
            vector_store_id=data.vector_store_id,
            user_api_key_dict=user_api_key_dict,
            prisma_client=prisma_client,
        )
        vector_store_dict = dict(vector_store_typed)
        if "litellm_params" in vector_store_dict:
            vector_store_dict["litellm_params"] = _redact_sensitive_litellm_params(
                vector_store_dict["litellm_params"]
            )
        vector_store_dict = await _enrich_vector_store_context(
            vector_store=LiteLLM_ManagedVectorStore(**vector_store_dict),
            prisma_client=prisma_client,
        )
        return {"vector_store": vector_store_dict}
    except HTTPException:
        # Preserve 403/404 from the access-control / not-found checks above;
        # the catch-all below would otherwise rewrite them as 500.
        raise
    except Exception as e:
        verbose_proxy_logger.exception(f"Error getting vector store info: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/vector_store/update",
    tags=["vector store management"],
    dependencies=[Depends(user_api_key_auth)],
)
async def update_vector_store(
    data: VectorStoreUpdateRequest,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """
    Update vector store details in both database and in-memory registry.
    The updated data is immediately synchronized to the in-memory registry.
    """
    await check_feature_access_for_user(user_api_key_dict, "vector_stores")

    from litellm.proxy.proxy_server import prisma_client
    from litellm.types.router import GenericLiteLLMParams

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    try:
        update_data = data.model_dump(exclude_unset=True)
        vector_store_id = update_data.pop("vector_store_id")
        company_id = update_data.pop("company_id", None)
        project_id_was_set = "project_id" in update_data
        project_id = update_data.get("project_id")

        # Per-store access control: anyone authenticated who passes the
        # premium-feature gate could otherwise update *any* vector store —
        # including stores belonging to other teams.
        await _fetch_and_authorize_vector_store(
            vector_store_id=vector_store_id,
            user_api_key_dict=user_api_key_dict,
            prisma_client=prisma_client,
        )

        if company_id is not None and not project_id_was_set:
            raise HTTPException(
                status_code=400,
                detail="project_id is required when company_id is provided",
            )
        if project_id_was_set:
            if project_id is None:
                raise HTTPException(
                    status_code=400,
                    detail="project_id is required to update vector store Project context",
                )
            project_team_id, _, _ = await _resolve_vector_store_project_context(
                prisma_client=prisma_client,
                project_id=project_id,
                company_id=company_id,
                user_api_key_dict=user_api_key_dict,
            )
            update_data["team_id"] = project_team_id

        # Handle metadata serialization
        if update_data.get("vector_store_metadata") is not None:
            update_data["vector_store_metadata"] = safe_dumps(
                update_data["vector_store_metadata"]
            )

        # Handle litellm_params if provided. As with the create path, the
        # embedding-config auto-resolve previously persisted cleartext
        # credentials into the row; resolution now happens at request-
        # handling time in
        # ``_update_request_data_with_litellm_managed_vector_store_registry``
        # so this row only ever stores the user-supplied
        # ``litellm_embedding_model`` reference.
        if "litellm_params" in update_data:
            _input_litellm_params: dict = update_data.get("litellm_params", {}) or {}
            litellm_params_dict = GenericLiteLLMParams(
                **_input_litellm_params
            ).model_dump(exclude_none=True)
            update_data["litellm_params"] = safe_dumps(litellm_params_dict)

        # Update in database
        updated = await prisma_client.db.litellm_managedvectorstorestable.update(
            where={"vector_store_id": vector_store_id},
            data=update_data,
        )

        updated_vs = LiteLLM_ManagedVectorStore(**updated.model_dump())

        # Immediately update in-memory registry to keep it in sync
        if litellm.vector_store_registry is not None:
            litellm.vector_store_registry.update_vector_store_in_registry(
                vector_store_id=vector_store_id,
                updated_data=updated_vs,
            )
            verbose_proxy_logger.debug(
                f"Updated vector store {vector_store_id} in both database and in-memory registry"
            )

        # The DB row is returned in full, so the response would otherwise
        # echo the persisted ``litellm_params`` (including provider
        # credentials) back to the caller — even when the caller only
        # changed unrelated fields like ``vector_store_description``.
        response_vs = LiteLLM_ManagedVectorStore(**updated_vs)
        response_vs["litellm_params"] = _redact_sensitive_litellm_params(
            updated_vs.get("litellm_params")
        )
        response_vs = await _enrich_vector_store_context(
            vector_store=response_vs,
            prisma_client=prisma_client,
        )
        return {
            "status": "success",
            "message": f"Vector store {vector_store_id} updated successfully",
            "vector_store": response_vs,
        }
    except HTTPException:
        # Preserve 403/404 responses from the access-control / not-found
        # checks above; the catch-all below would otherwise rewrite them
        # as 500 with the original status code embedded in the detail.
        raise
    except Exception as e:
        verbose_proxy_logger.exception(f"Error updating vector store: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
