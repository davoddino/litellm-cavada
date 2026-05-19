from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.cavadalabs.access_control import (
    require_project_access,
    require_project_admin_access,
)
from litellm.proxy.auth.user_api_key_auth import user_api_key_auth
from litellm.proxy.management_endpoints.cavadalabs_dispatcher_utils import (
    dispatcher_service,
)
from litellm.proxy.management_helpers.utils import management_endpoint_wrapper
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsModelPolicyEndpointType,
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
    service = dispatcher_service()
    await require_project_admin_access(
        service.db,
        project_id=data.project_id,
        user_api_key_dict=user_api_key_dict,
    )
    return await service.create_project_model_policy(data, user_api_key_dict)


@router.get(
    "/model-policies",
    dependencies=[Depends(user_api_key_auth)],
    response_model=CavadaLabsProjectModelPolicyListResponse,
)
@management_endpoint_wrapper
async def list_model_policies(
    http_request: Request,
    project_id: str = Query(...),
    key_id: Optional[str] = Query(default=None, min_length=1),
    enabled: Optional[bool] = None,
    endpoint_type: Optional[CavadaLabsModelPolicyEndpointType] = None,
    model_bucket: Optional[str] = Query(default=None, min_length=1),
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
) -> CavadaLabsProjectModelPolicyListResponse:
    service = dispatcher_service()
    await require_project_access(
        service.db,
        project_id=project_id,
        user_api_key_dict=user_api_key_dict,
    )
    model_policies = await service.list_project_model_policies(
        project_id=project_id,
        enabled=enabled,
        endpoint_type=endpoint_type.value if endpoint_type is not None else None,
        model_bucket=model_bucket.strip().lower()
        if isinstance(model_bucket, str) and model_bucket
        else None,
        key_id=key_id.strip() if isinstance(key_id, str) and key_id else None,
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
    service = dispatcher_service()
    policy = await service.get_project_model_policy(policy_id)
    await require_project_admin_access(
        service.db,
        project_id=policy.project_id,
        user_api_key_dict=user_api_key_dict,
    )
    return await service.update_project_model_policy(policy_id, data, user_api_key_dict)
