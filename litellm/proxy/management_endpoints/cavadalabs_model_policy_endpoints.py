from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.auth.user_api_key_auth import user_api_key_auth
from litellm.proxy.management_endpoints.cavadalabs_dispatcher_utils import (
    dispatcher_service,
    require_admin_view,
    require_proxy_admin,
)
from litellm.proxy.management_helpers.utils import management_endpoint_wrapper
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsProjectModelPolicyCreateRequest,
    CavadaLabsProjectModelPolicyListResponse,
    CavadaLabsProjectModelPolicyResponse,
    CavadaLabsProjectModelPolicyUpdateRequest,
)

router = APIRouter(tags=["cavadalabs-model-policies"])


@router.post(
    "/model-policies",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsProjectModelPolicyResponse,
)
@management_endpoint_wrapper
async def create_model_policy(
    data: CavadaLabsProjectModelPolicyCreateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsProjectModelPolicyResponse:
    require_proxy_admin(user_api_key_dict)
    return await dispatcher_service().create_project_model_policy(
        data, user_api_key_dict
    )


@router.get(
    "/model-policies",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsProjectModelPolicyListResponse,
)
@management_endpoint_wrapper
async def list_model_policies(
    http_request: Request,
    project_id: str = Query(...),
    enabled: Optional[bool] = None,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsProjectModelPolicyListResponse:
    require_admin_view(user_api_key_dict)
    model_policies = await dispatcher_service().list_project_model_policies(
        project_id=project_id,
        enabled=enabled,
    )
    return CavadaLabsProjectModelPolicyListResponse(
        model_policies=model_policies, count=len(model_policies)
    )


@router.patch(
    "/model-policies/{policy_id}",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsProjectModelPolicyResponse,
)
@management_endpoint_wrapper
async def update_model_policy(
    policy_id: str,
    data: CavadaLabsProjectModelPolicyUpdateRequest,
    http_request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsProjectModelPolicyResponse:
    require_proxy_admin(user_api_key_dict)
    return await dispatcher_service().update_project_model_policy(
        policy_id, data, user_api_key_dict
    )
