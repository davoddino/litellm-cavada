from __future__ import annotations

import inspect
from typing import Any, Iterable, Optional

from fastapi import HTTPException, status

from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.cavadalabs.model_policy_resolution import (
    CavadaLabsModelPolicyResolutionError,
    CavadaLabsModelPolicySchemaError,
    resolve_project_model_priority,
)
from litellm.proxy.cavadalabs.model_policy_store import (
    CavadaLabsProjectModelPolicyStore,
)

_ROUTE_ENDPOINT_TYPES = {
    "acompletion": "chat_completion",
    "atext_completion": "text_completion",
    "aembedding": "embedding",
    "atranscription": "transcription",
}
_DEFAULT_MODEL_BUCKET = "default"


async def apply_cavadalabs_project_model_fallback(
    *,
    data: dict,
    route_type: str,
    user_api_key_dict: UserAPIKeyAuth,
    llm_router: Any,
    prisma_client: Optional[Any] = None,
) -> Optional[str]:
    endpoint_type = _ROUTE_ENDPOINT_TYPES.get(route_type)
    if endpoint_type is None:
        return None

    project_id = _clean_string(
        getattr(user_api_key_dict, "cavadalabs_project_id", None)
    )
    if project_id is None:
        return None

    if prisma_client is None:
        from litellm.proxy import proxy_server

        prisma_client = proxy_server.prisma_client
    if prisma_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "Database is required for CavadaLabs project model fallback",
                "code": "cavadalabs_model_policy_db_required",
            },
        )

    requested_model = _clean_string(data.get("model"))
    model_bucket = _normalize_model_bucket(requested_model or _DEFAULT_MODEL_BUCKET)
    key_id = _clean_string(getattr(user_api_key_dict, "token", None)) or _clean_string(
        getattr(user_api_key_dict, "api_key", None)
    )
    store = CavadaLabsProjectModelPolicyStore(prisma_client.db)
    try:
        policies = await store.list_enabled_project_policies(
            project_id=project_id,
            endpoint_type=endpoint_type,
            model_bucket=model_bucket,
            key_id=key_id,
        )
        if key_id is not None and not policies:
            policies = await store.list_enabled_project_policies(
                project_id=project_id,
                endpoint_type=endpoint_type,
                model_bucket=model_bucket,
                key_id=None,
            )
        if requested_model is not None and not policies:
            return None
        available_models = await _available_model_names_from_router(
            llm_router=llm_router,
            team_id=_clean_string(getattr(user_api_key_dict, "team_id", None)),
        )
        resolution = resolve_project_model_priority(
            project_id=project_id,
            policies=policies,
            available_model_names=available_models,
            endpoint_type=endpoint_type,
            model_bucket=model_bucket,
        )
    except CavadaLabsModelPolicySchemaError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.to_detail(),
        ) from exc
    except CavadaLabsModelPolicyResolutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.to_detail(),
        ) from exc

    data["model"] = resolution.model
    data.pop("fallbacks", None)
    if resolution.fallback_models:
        data["fallbacks"] = list(resolution.fallback_models)
    _write_routing_metadata(data, resolution)
    return resolution.model


async def _available_model_names_from_router(
    *, llm_router: Any, team_id: Optional[str]
) -> set[str]:
    if llm_router is None:
        return set()

    model_names: set[str] = set()
    _extend_strings(
        model_names,
        _call_router_model_names(llm_router=llm_router, team_id=team_id),
    )
    _extend_strings(model_names, getattr(llm_router, "model_names", set()) or set())
    _extend_strings(
        model_names,
        getattr(llm_router, "deployment_names", set()) or set(),
    )
    _extend_strings(model_names, _call_router_model_ids(llm_router=llm_router))
    if not getattr(llm_router, "enable_health_check_routing", False):
        return model_names

    unhealthy_deployment_ids = await _router_unhealthy_deployment_ids(llm_router)
    if not unhealthy_deployment_ids:
        return model_names

    deployments = list(_call_router_model_list(llm_router=llm_router, team_id=team_id))
    if not deployments:
        return model_names

    health_filtered_model_names = _healthy_model_names_from_deployments(
        deployments=deployments,
        unhealthy_deployment_ids=unhealthy_deployment_ids,
    )
    if health_filtered_model_names:
        return health_filtered_model_names
    return set()


async def _router_unhealthy_deployment_ids(llm_router: Any) -> set[str]:
    health_state_cache = getattr(llm_router, "health_state_cache", None)
    if health_state_cache is None:
        return set()
    getter = getattr(health_state_cache, "async_get_unhealthy_deployment_ids", None)
    if not callable(getter):
        return set()
    unhealthy_ids = getter(parent_otel_span=None)
    if inspect.isawaitable(unhealthy_ids):
        unhealthy_ids = await unhealthy_ids
    return {deployment_id for deployment_id in unhealthy_ids if deployment_id}


def _healthy_model_names_from_deployments(
    *,
    deployments: Iterable[dict],
    unhealthy_deployment_ids: set[str],
) -> set[str]:
    healthy_model_names: set[str] = set()
    for deployment in deployments:
        if not isinstance(deployment, dict):
            continue
        model_info = deployment.get("model_info") or {}
        deployment_id = _clean_string(model_info.get("id"))
        if deployment_id is not None and deployment_id in unhealthy_deployment_ids:
            continue
        _extend_strings(healthy_model_names, [deployment.get("model_name")])
        litellm_params = deployment.get("litellm_params") or {}
        if isinstance(litellm_params, dict):
            _extend_strings(healthy_model_names, [litellm_params.get("model")])
        _extend_strings(healthy_model_names, [deployment_id])
    return healthy_model_names


def _call_router_model_names(
    *, llm_router: Any, team_id: Optional[str]
) -> Iterable[str]:
    get_model_names = getattr(llm_router, "get_model_names", None)
    if not callable(get_model_names):
        return []
    try:
        return get_model_names(team_id=team_id)
    except TypeError:
        return get_model_names()


def _call_router_model_ids(*, llm_router: Any) -> Iterable[str]:
    get_model_ids = getattr(llm_router, "get_model_ids", None)
    if not callable(get_model_ids):
        return []
    return get_model_ids()


def _call_router_model_list(
    *, llm_router: Any, team_id: Optional[str]
) -> Iterable[dict]:
    get_model_list = getattr(llm_router, "get_model_list", None)
    if not callable(get_model_list):
        return getattr(llm_router, "model_list", []) or []
    try:
        return get_model_list(team_id=team_id) or []
    except TypeError:
        return get_model_list() or []


def _extend_strings(target: set[str], values: Iterable[Any]) -> None:
    for value in values:
        cleaned = _clean_string(value)
        if cleaned is not None:
            target.add(cleaned)


def _is_missing_model(value: Any) -> bool:
    return value is None or value == ""


def _clean_string(value: Any) -> Optional[str]:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _normalize_model_bucket(value: str) -> str:
    return value.strip().lower() or _DEFAULT_MODEL_BUCKET


def _write_routing_metadata(
    data: dict,
    resolution: Any,
) -> None:
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        data["metadata"] = metadata
    cavadalabs_metadata = metadata.get("cavadalabs")
    if not isinstance(cavadalabs_metadata, dict):
        cavadalabs_metadata = {}
        metadata["cavadalabs"] = cavadalabs_metadata
    cavadalabs_metadata["routing"] = {
        "endpoint_type": resolution.endpoint_type,
        "model_bucket": resolution.model_bucket,
        "key_id": getattr(resolution.policy, "key_id", None),
        "selected_policy_id": resolution.policy.policy_id,
        "selected_model_alias": resolution.model,
        "fallback_models": list(resolution.fallback_models),
    }
    metadata["cavadalabs_endpoint_type"] = resolution.endpoint_type
    metadata["cavadalabs_model_bucket"] = resolution.model_bucket
    metadata["cavadalabs_policy_id"] = resolution.policy.policy_id
