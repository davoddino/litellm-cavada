from __future__ import annotations

from typing import Optional, Type, TypeVar

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, ValidationError

from litellm.proxy.cavadalabs.nodes import CavadaLabsNodeService
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsGPUInventoryRequest,
    CavadaLabsGPUListResponse,
    CavadaLabsLoadedModelResponse,
    CavadaLabsLoadedModelUpsertRequest,
    CavadaLabsModelLoadRequestListResponse,
    CavadaLabsNodeDailyReportRequest,
    CavadaLabsNodeDailyReportResponse,
    CavadaLabsNodeEnrollmentCompleteRequest,
    CavadaLabsNodeEnrollmentCompleteResponse,
    CavadaLabsNodeHeartbeatRequest,
    CavadaLabsNodeModelLoadWorkRequest,
    CavadaLabsNodeResponse,
)

router = APIRouter(prefix="/cavadalabs/nodes", tags=["cavadalabs"])
ModelT = TypeVar("ModelT", bound=BaseModel)


def _service() -> CavadaLabsNodeService:
    from litellm.proxy import proxy_server

    if proxy_server.prisma_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Database is required for CavadaLabs node runtime"},
        )
    return CavadaLabsNodeService(proxy_server.prisma_client)


def _require_node_header(value: Optional[str], header_name: str) -> str:
    if not value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": f"Missing {header_name} header"},
        )
    return value.strip()


async def _signed_payload(
    *,
    request: Request,
    payload_model: Type[ModelT],
    node_id: Optional[str],
    timestamp: Optional[str],
    signature: Optional[str],
) -> tuple[CavadaLabsNodeService, str, ModelT]:
    service = _service()
    raw_body = await request.body()
    resolved_node_id = _require_node_header(node_id, "x-cavadalabs-node-id")
    resolved_timestamp = _require_node_header(timestamp, "x-cavadalabs-node-timestamp")
    resolved_signature = _require_node_header(signature, "x-cavadalabs-node-signature")
    await service.authenticate_node_request(
        node_id=resolved_node_id,
        timestamp=resolved_timestamp,
        signature=resolved_signature,
        method=request.method,
        path=request.url.path,
        body=raw_body,
    )
    try:
        payload = payload_model.model_validate_json(raw_body)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors()
        )
    return service, resolved_node_id, payload


@router.post(
    "/enroll",
    response_model=CavadaLabsNodeEnrollmentCompleteResponse,
    responses={
        200: {"description": "Node enrolled and activated"},
        401: {"description": "Unknown or expired enrollment secret"},
        409: {"description": "Enrollment secret was already used"},
    },
)
async def complete_node_enrollment(
    data: CavadaLabsNodeEnrollmentCompleteRequest,
) -> CavadaLabsNodeEnrollmentCompleteResponse:
    return await _service().complete_enrollment(data)


@router.post(
    "/heartbeat",
    response_model=CavadaLabsNodeResponse,
    responses={
        200: {"description": "Node heartbeat accepted"},
        401: {"description": "Missing or invalid node signature"},
        403: {"description": "Node is disabled or not reportable"},
    },
)
async def heartbeat_node(
    request: Request,
    x_cavadalabs_node_id: Optional[str] = Header(
        default=None, alias="x-cavadalabs-node-id"
    ),
    x_cavadalabs_node_timestamp: Optional[str] = Header(
        default=None, alias="x-cavadalabs-node-timestamp"
    ),
    x_cavadalabs_node_signature: Optional[str] = Header(
        default=None, alias="x-cavadalabs-node-signature"
    ),
) -> CavadaLabsNodeResponse:
    service, node_id, payload = await _signed_payload(
        request=request,
        payload_model=CavadaLabsNodeHeartbeatRequest,
        node_id=x_cavadalabs_node_id,
        timestamp=x_cavadalabs_node_timestamp,
        signature=x_cavadalabs_node_signature,
    )
    return await service.heartbeat_node(node_id=node_id, data=payload)


@router.put(
    "/gpus",
    response_model=CavadaLabsGPUListResponse,
    responses={
        200: {"description": "GPU inventory upserted"},
        401: {"description": "Missing or invalid node signature"},
        403: {"description": "Node is disabled or not reportable"},
    },
)
async def upsert_gpu_inventory(
    request: Request,
    x_cavadalabs_node_id: Optional[str] = Header(
        default=None, alias="x-cavadalabs-node-id"
    ),
    x_cavadalabs_node_timestamp: Optional[str] = Header(
        default=None, alias="x-cavadalabs-node-timestamp"
    ),
    x_cavadalabs_node_signature: Optional[str] = Header(
        default=None, alias="x-cavadalabs-node-signature"
    ),
) -> CavadaLabsGPUListResponse:
    service, node_id, payload = await _signed_payload(
        request=request,
        payload_model=CavadaLabsGPUInventoryRequest,
        node_id=x_cavadalabs_node_id,
        timestamp=x_cavadalabs_node_timestamp,
        signature=x_cavadalabs_node_signature,
    )
    return await service.upsert_gpu_inventory(node_id=node_id, data=payload)


@router.put(
    "/daily-reports",
    response_model=CavadaLabsNodeDailyReportResponse,
    responses={
        200: {"description": "Daily report accepted"},
        401: {"description": "Missing or invalid node signature"},
        403: {"description": "Node is disabled or not reportable"},
    },
)
async def record_daily_report(
    request: Request,
    x_cavadalabs_node_id: Optional[str] = Header(
        default=None, alias="x-cavadalabs-node-id"
    ),
    x_cavadalabs_node_timestamp: Optional[str] = Header(
        default=None, alias="x-cavadalabs-node-timestamp"
    ),
    x_cavadalabs_node_signature: Optional[str] = Header(
        default=None, alias="x-cavadalabs-node-signature"
    ),
) -> CavadaLabsNodeDailyReportResponse:
    service, node_id, payload = await _signed_payload(
        request=request,
        payload_model=CavadaLabsNodeDailyReportRequest,
        node_id=x_cavadalabs_node_id,
        timestamp=x_cavadalabs_node_timestamp,
        signature=x_cavadalabs_node_signature,
    )
    return await service.record_daily_report(node_id=node_id, data=payload)


@router.put(
    "/loaded-models",
    response_model=CavadaLabsLoadedModelResponse,
    responses={
        200: {"description": "Loaded model state accepted"},
        401: {"description": "Missing or invalid node signature"},
        403: {"description": "Node is disabled or not reportable"},
    },
)
async def upsert_loaded_model(
    request: Request,
    x_cavadalabs_node_id: Optional[str] = Header(
        default=None, alias="x-cavadalabs-node-id"
    ),
    x_cavadalabs_node_timestamp: Optional[str] = Header(
        default=None, alias="x-cavadalabs-node-timestamp"
    ),
    x_cavadalabs_node_signature: Optional[str] = Header(
        default=None, alias="x-cavadalabs-node-signature"
    ),
) -> CavadaLabsLoadedModelResponse:
    service, node_id, payload = await _signed_payload(
        request=request,
        payload_model=CavadaLabsLoadedModelUpsertRequest,
        node_id=x_cavadalabs_node_id,
        timestamp=x_cavadalabs_node_timestamp,
        signature=x_cavadalabs_node_signature,
    )
    return await service.upsert_loaded_model(node_id=node_id, data=payload)


@router.post(
    "/model-load-requests",
    response_model=CavadaLabsModelLoadRequestListResponse,
    responses={
        200: {"description": "Assigned model-load work for this node"},
        401: {"description": "Missing or invalid node signature"},
        403: {"description": "Node is disabled or not reportable"},
    },
)
async def list_node_model_load_work(
    request: Request,
    x_cavadalabs_node_id: Optional[str] = Header(
        default=None, alias="x-cavadalabs-node-id"
    ),
    x_cavadalabs_node_timestamp: Optional[str] = Header(
        default=None, alias="x-cavadalabs-node-timestamp"
    ),
    x_cavadalabs_node_signature: Optional[str] = Header(
        default=None, alias="x-cavadalabs-node-signature"
    ),
) -> CavadaLabsModelLoadRequestListResponse:
    service, node_id, payload = await _signed_payload(
        request=request,
        payload_model=CavadaLabsNodeModelLoadWorkRequest,
        node_id=x_cavadalabs_node_id,
        timestamp=x_cavadalabs_node_timestamp,
        signature=x_cavadalabs_node_signature,
    )
    return await service.list_node_model_load_work(node_id=node_id, data=payload)
