from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, Optional

from fastapi import HTTPException, status

from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.cavadalabs.dispatcher import (
    _actor_user_id,
    _is_unique_violation,
    _now_utc,
)
from litellm.proxy.cavadalabs.prisma_json import serialize_prisma_json_fields
from litellm.proxy.cavadalabs.nodes_shared import (
    _create_node_enrollment_secret,
    _parse_response,
    public_key_fingerprint,
)
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsNodeCreateRequest,
    CavadaLabsNodeEnrollmentCreateRequest,
    CavadaLabsNodeEnrollmentCreateResponse,
    CavadaLabsNodeEnrollmentResponse,
    CavadaLabsNodeEnrollmentStatus,
    CavadaLabsNodeListResponse,
    CavadaLabsNodeResponse,
    CavadaLabsNodeStatus,
    CavadaLabsNodeUpdateRequest,
)


class CavadaLabsNodeAdminOperations:
    async def create_node(
        self,
        data: CavadaLabsNodeCreateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsNodeResponse:
        create_data = data.model_dump(mode="python")
        if create_data.get("public_key"):
            create_data["public_key_fingerprint"] = public_key_fingerprint(
                create_data["public_key"]
            )
        elif create_data["status"] not in {
            CavadaLabsNodeStatus.PENDING.value,
            CavadaLabsNodeStatus.DISABLED.value,
        }:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "Non-pending nodes require a public_key"},
            )

        create_data["created_by"] = _actor_user_id(user_api_key_dict)
        create_data["updated_by"] = _actor_user_id(user_api_key_dict)
        create_data = serialize_prisma_json_fields(create_data)
        try:
            row = await self.db.cavadalabs_nodetable.create(data=create_data)
        except Exception as exc:
            if _is_unique_violation(exc):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": "Node already exists"},
                )
            raise

        response = _parse_response(row, CavadaLabsNodeResponse)
        await self._audit_admin(
            user_api_key_dict=user_api_key_dict,
            action="created",
            resource_type="node",
            resource_id=response.node_id,
            before_value=None,
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def get_node(self, node_id: str) -> CavadaLabsNodeResponse:
        row = await self.db.cavadalabs_nodetable.find_unique(where={"node_id": node_id})
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"Node '{node_id}' not found"},
            )
        return _parse_response(row, CavadaLabsNodeResponse)

    async def list_nodes(
        self,
        status_filter: Optional[CavadaLabsNodeStatus] = None,
        location: Optional[str] = None,
        take: int = 100,
        skip: int = 0,
    ) -> CavadaLabsNodeListResponse:
        where: Dict[str, Any] = {}
        if status_filter is not None:
            where["status"] = status_filter.value
        if location is not None:
            where["location"] = location
        rows = await self.db.cavadalabs_nodetable.find_many(
            where=where or None,
            take=take,
            skip=skip,
            order={"created_at": "desc"},
        )
        nodes = [_parse_response(row, CavadaLabsNodeResponse) for row in rows]
        return CavadaLabsNodeListResponse(nodes=nodes, count=len(nodes))

    async def update_node(
        self,
        node_id: str,
        data: CavadaLabsNodeUpdateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsNodeResponse:
        before = await self.get_node(node_id)
        update_data = data.model_dump(mode="python", exclude_unset=True)
        if not update_data:
            return before

        next_public_key = update_data.get("public_key", before.public_key)
        next_status = update_data.get("status", before.status)
        if next_public_key:
            update_data["public_key_fingerprint"] = public_key_fingerprint(
                next_public_key
            )
        elif next_status not in {
            CavadaLabsNodeStatus.PENDING.value,
            CavadaLabsNodeStatus.DISABLED.value,
        }:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "Online nodes require a public_key"},
            )

        update_data["updated_by"] = _actor_user_id(user_api_key_dict)
        update_data = serialize_prisma_json_fields(update_data)
        row = await self.db.cavadalabs_nodetable.update(
            where={"node_id": node_id},
            data=update_data,
        )
        response = _parse_response(row, CavadaLabsNodeResponse)
        await self._audit_admin(
            user_api_key_dict=user_api_key_dict,
            action="updated",
            resource_type="node",
            resource_id=response.node_id,
            before_value=before.model_dump(mode="json"),
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def disable_node(
        self,
        node_id: str,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsNodeResponse:
        return await self.update_node(
            node_id=node_id,
            data=CavadaLabsNodeUpdateRequest(status=CavadaLabsNodeStatus.DISABLED),
            user_api_key_dict=user_api_key_dict,
        )

    async def create_enrollment_secret(
        self,
        node_id: str,
        data: CavadaLabsNodeEnrollmentCreateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsNodeEnrollmentCreateResponse:
        node = await self.get_node(node_id)
        if node.status == CavadaLabsNodeStatus.DISABLED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "Cannot enroll a disabled node"},
            )

        enrollment_secret, secret_prefix, secret_hash = _create_node_enrollment_secret()
        expires_at = _now_utc() + timedelta(seconds=data.expires_in_seconds)
        row = await self.db.cavadalabs_nodeenrollmenttable.create(
            data=serialize_prisma_json_fields(
                {
                "node_id": node_id,
                "secret_prefix": secret_prefix,
                "secret_hash": secret_hash,
                "status": CavadaLabsNodeEnrollmentStatus.ACTIVE.value,
                "expires_at": expires_at,
                "metadata": data.metadata,
                "created_by": _actor_user_id(user_api_key_dict),
                "updated_by": _actor_user_id(user_api_key_dict),
                }
            )
        )
        enrollment = _parse_response(row, CavadaLabsNodeEnrollmentResponse)
        await self._audit_admin(
            user_api_key_dict=user_api_key_dict,
            action="created",
            resource_type="node_enrollment",
            resource_id=enrollment.enrollment_id,
            before_value=None,
            after_value=enrollment.model_dump(mode="json"),
        )
        return CavadaLabsNodeEnrollmentCreateResponse(
            enrollment=enrollment,
            enrollment_secret=enrollment_secret,
        )
