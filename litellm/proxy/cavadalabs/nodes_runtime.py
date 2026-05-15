from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from litellm.proxy.cavadalabs.dispatcher import (
    _as_aware_utc,
    _now_utc,
    hash_web_token,
)
from litellm.proxy.cavadalabs.prisma_json import serialize_prisma_json_fields
from litellm.proxy.cavadalabs.nodes_shared import (
    _NODE_SIGNATURE_MAX_SKEW,
    _daily_report_date,
    _decode_signature,
    _load_ed25519_public_key,
    _node_actor,
    _parse_node_timestamp,
    _parse_response,
    canonical_node_signature_payload,
    public_key_fingerprint,
)
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsGPUInventoryRequest,
    CavadaLabsGPUListResponse,
    CavadaLabsGPUResponse,
    CavadaLabsGPUStatus,
    CavadaLabsNodeDailyReportRequest,
    CavadaLabsNodeDailyReportResponse,
    CavadaLabsNodeEnrollmentCompleteResponse,
    CavadaLabsNodeEnrollmentResponse,
    CavadaLabsNodeEnrollmentStatus,
    CavadaLabsNodeHeartbeatRequest,
    CavadaLabsNodeResponse,
    CavadaLabsNodeStatus,
)


from cryptography.exceptions import InvalidSignature


class CavadaLabsNodeRuntimeOperations:
    async def complete_enrollment(
        self,
        data: Any,
    ) -> CavadaLabsNodeEnrollmentCompleteResponse:
        secret_hash = hash_web_token(data.enrollment_secret)
        row = await self.db.cavadalabs_nodeenrollmenttable.find_unique(
            where={"secret_hash": secret_hash}
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "Unknown node enrollment secret"},
            )
        enrollment = _parse_response(row, CavadaLabsNodeEnrollmentResponse)
        if enrollment.status != CavadaLabsNodeEnrollmentStatus.ACTIVE.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "Node enrollment secret is no longer active"},
            )
        if _as_aware_utc(enrollment.expires_at) <= _now_utc():
            await self.db.cavadalabs_nodeenrollmenttable.update(
                where={"enrollment_id": enrollment.enrollment_id},
                data={
                    "status": CavadaLabsNodeEnrollmentStatus.EXPIRED.value,
                    "updated_by": "cavadalabs-dispatcher",
                },
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "Node enrollment secret expired"},
            )

        node_before = await self.get_node(enrollment.node_id)
        if node_before.status == CavadaLabsNodeStatus.DISABLED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "Cannot enroll a disabled node"},
            )

        fingerprint = public_key_fingerprint(data.public_key)
        updated_count = await self.db.cavadalabs_nodeenrollmenttable.update_many(
            where={
                "enrollment_id": enrollment.enrollment_id,
                "status": CavadaLabsNodeEnrollmentStatus.ACTIVE.value,
            },
            data={
                "status": CavadaLabsNodeEnrollmentStatus.USED.value,
                "used_at": _now_utc(),
                "updated_by": _node_actor(enrollment.node_id),
            },
        )
        if updated_count == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "Node enrollment secret was already consumed"},
            )

        update_data: Dict[str, Any] = {
            "public_key": data.public_key,
            "public_key_fingerprint": fingerprint,
            "status": CavadaLabsNodeStatus.ONLINE.value,
            "last_heartbeat_at": _now_utc(),
            "metadata": {**node_before.metadata, **data.metadata},
            "updated_by": _node_actor(enrollment.node_id),
        }
        if data.agent_version is not None:
            update_data["agent_version"] = data.agent_version
        if data.hostname is not None:
            update_data["hostname"] = data.hostname

        node_row = await self.db.cavadalabs_nodetable.update(
            where={"node_id": enrollment.node_id},
            data=serialize_prisma_json_fields(update_data),
        )
        node = _parse_response(node_row, CavadaLabsNodeResponse)
        await self._audit_event(
            actor_user_id=_node_actor(node.node_id),
            actor_api_key_hash=None,
            action="enrolled",
            resource_type="node",
            resource_id=node.node_id,
            company_id=None,
            project_id=None,
            before_value=node_before.model_dump(mode="json"),
            after_value={
                "node_id": node.node_id,
                "public_key_fingerprint": node.public_key_fingerprint,
                "agent_version": node.agent_version,
            },
        )
        return CavadaLabsNodeEnrollmentCompleteResponse(
            node=node,
            runtime_config=self._runtime_config(node),
        )

    async def authenticate_node_request(
        self,
        *,
        node_id: str,
        timestamp: str,
        signature: str,
        method: str,
        path: str,
        body: bytes,
    ) -> CavadaLabsNodeResponse:
        node = await self.get_node(node_id)
        if node.status in {
            CavadaLabsNodeStatus.PENDING.value,
            CavadaLabsNodeStatus.DISABLED.value,
        }:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": f"Node '{node_id}' is not allowed to report"},
            )
        if not node.public_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": f"Node '{node_id}' has no public key"},
            )

        parsed_timestamp = _parse_node_timestamp(timestamp)
        if abs((_now_utc() - parsed_timestamp).total_seconds()) > int(
            _NODE_SIGNATURE_MAX_SKEW.total_seconds()
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "Node signature timestamp outside allowed skew"},
            )

        canonical_payload = canonical_node_signature_payload(
            timestamp=timestamp,
            method=method,
            path=path,
            body=body,
        )
        try:
            _load_ed25519_public_key(node.public_key).verify(
                _decode_signature(signature),
                canonical_payload,
            )
        except InvalidSignature:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "Invalid node request signature"},
            )
        return node

    async def heartbeat_node(
        self,
        node_id: str,
        data: CavadaLabsNodeHeartbeatRequest,
    ) -> CavadaLabsNodeResponse:
        before = await self.get_node(node_id)
        if before.status == CavadaLabsNodeStatus.DISABLED.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "Disabled nodes cannot heartbeat"},
            )
        metadata = {**before.metadata, **data.metadata}
        update_data: Dict[str, Any] = {
            "status": data.status,
            "metadata": metadata,
            "last_heartbeat_at": _now_utc(),
            "updated_by": _node_actor(node_id),
        }
        if data.agent_version is not None:
            update_data["agent_version"] = data.agent_version
        if data.hostname is not None:
            update_data["hostname"] = data.hostname
        row = await self.db.cavadalabs_nodetable.update(
            where={"node_id": node_id},
            data=serialize_prisma_json_fields(update_data),
        )
        return _parse_response(row, CavadaLabsNodeResponse)

    async def list_gpus(
        self,
        node_id: str,
        status_filter: Optional[CavadaLabsGPUStatus] = None,
    ) -> CavadaLabsGPUListResponse:
        await self.get_node(node_id)
        where: Dict[str, Any] = {"node_id": node_id}
        if status_filter is not None:
            where["status"] = status_filter.value
        rows = await self.db.cavadalabs_gputable.find_many(
            where=where,
            order={"created_at": "asc"},
        )
        gpus = [_parse_response(row, CavadaLabsGPUResponse) for row in rows]
        return CavadaLabsGPUListResponse(gpus=gpus, count=len(gpus))

    async def upsert_gpu_inventory(
        self,
        node_id: str,
        data: CavadaLabsGPUInventoryRequest,
    ) -> CavadaLabsGPUListResponse:
        await self.get_node(node_id)
        responses: List[CavadaLabsGPUResponse] = []
        for gpu in data.gpus:
            existing = await self._find_existing_gpu(node_id=node_id, gpu=gpu)
            payload = {
                **gpu.model_dump(mode="python", exclude={"gpu_id"}),
                "updated_by": _node_actor(node_id),
            }
            payload = serialize_prisma_json_fields(payload)
            if existing is not None:
                row = await self.db.cavadalabs_gputable.update(
                    where={"gpu_id": existing.gpu_id},
                    data=payload,
                )
            else:
                row = await self.db.cavadalabs_gputable.create(
                    data={
                        **payload,
                        "node_id": node_id,
                        "created_by": _node_actor(node_id),
                    }
                )
            responses.append(_parse_response(row, CavadaLabsGPUResponse))

        await self.db.cavadalabs_nodetable.update(
            where={"node_id": node_id},
            data={
                "last_heartbeat_at": _now_utc(),
                "updated_by": _node_actor(node_id),
            },
        )
        return CavadaLabsGPUListResponse(gpus=responses, count=len(responses))

    async def record_daily_report(
        self,
        node_id: str,
        data: CavadaLabsNodeDailyReportRequest,
    ) -> CavadaLabsNodeDailyReportResponse:
        node = await self.get_node(node_id)
        report_date = _daily_report_date(data.report_date)
        node_cost_estimate = data.node_cost_estimate
        if node_cost_estimate is None:
            node_cost_estimate = self._estimate_node_daily_cost(node=node, data=data)

        payload = serialize_prisma_json_fields(
            {
            "samples": data.samples,
            "total_kwh": data.total_kwh,
            "total_model_runtime_seconds": data.total_model_runtime_seconds,
            "total_loaded_model_seconds": data.total_loaded_model_seconds,
            "total_requests": data.total_requests,
            "total_tokens": data.total_tokens,
            "node_cost_estimate": node_cost_estimate,
            "errors": data.errors,
            "metadata": data.metadata,
            }
        )
        existing = await self.db.cavadalabs_nodedailyreporttable.find_first(
            where={"node_id": node_id, "report_date": report_date}
        )
        if existing is None:
            row = await self.db.cavadalabs_nodedailyreporttable.create(
                data={
                    **payload,
                    "node_id": node_id,
                    "report_date": report_date,
                }
            )
        else:
            row = await self.db.cavadalabs_nodedailyreporttable.update(
                where={"report_id": existing.report_id},
                data=payload,
            )

        await self.db.cavadalabs_nodetable.update(
            where={"node_id": node_id},
            data={
                "last_heartbeat_at": _now_utc(),
                "updated_by": _node_actor(node_id),
            },
        )
        return _parse_response(row, CavadaLabsNodeDailyReportResponse)
