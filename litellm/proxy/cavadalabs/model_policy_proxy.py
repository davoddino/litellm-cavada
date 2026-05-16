from __future__ import annotations

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

_COMPLETION_ROUTE_TYPES = {"acompletion", "atext_completion"}


async def apply_cavadalabs_project_model_fallback(
    *,
    data: dict,
    route_type: str,
    user_api_key_dict: UserAPIKeyAuth,
    llm_router: Any,
    prisma_client: Optional[Any] = None,
) -> Optional[str]:
    if route_type not in _COMPLETION_ROUTE_TYPES or not _is_missing_model(
        data.get("model")
    ):
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

    available_models = _available_model_names_from_router(
        llm_router=llm_router,
        team_id=_clean_string(getattr(user_api_key_dict, "team_id", None)),
    )
    store = CavadaLabsProjectModelPolicyStore(prisma_client.db)
    try:
        policies = await store.list_enabled_project_policies(project_id=project_id)
        resolution = resolve_project_model_priority(
            project_id=project_id,
            policies=policies,
            available_model_names=available_models,
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
    return resolution.model


def _available_model_names_from_router(
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
    return model_names


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


def _extend_strings(target: set[str], values: Iterable[Any]) -> None:
    for value in values:
        cleaned = _clean_string(value)
        if cleaned is not None:
            target.add(cleaned)


def _is_missing_model(value: Any) -> bool:
    return value is None or value == ""


def _clean_string(value: Any) -> Optional[str]:
    return value.strip() if isinstance(value, str) and value.strip() else None
