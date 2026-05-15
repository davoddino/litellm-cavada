from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import HTTPException, status

from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.cavadalabs.dispatcher import (
    CavadaLabsDispatcherService,
    _actor_user_id,
    _as_aware_utc,
    _is_unique_violation,
    _now_utc,
)
from litellm.proxy.cavadalabs.prisma_json import serialize_prisma_json_fields
from litellm.proxy.cavadalabs.nodes_shared import (
    _active_gpu_lock_key,
    _parse_response,
)
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsGPULockCreateRequest,
    CavadaLabsGPULockListResponse,
    CavadaLabsGPULockResponse,
    CavadaLabsGPULockStatus,
    CavadaLabsGPUStatus,
    CavadaLabsLoadedModelResponse,
    CavadaLabsLoadedModelUpsertRequest,
    CavadaLabsModelLoadRequestCreateRequest,
    CavadaLabsModelLoadRequestListResponse,
    CavadaLabsModelLoadRequestResponse,
    CavadaLabsModelLoadRequestUpdateRequest,
    CavadaLabsModelRuntimeStatus,
    CavadaLabsNodeModelLoadWorkRequest,
)


class CavadaLabsNodeModelLoadOperations:
    async def create_model_load_request(
        self,
        data: CavadaLabsModelLoadRequestCreateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsModelLoadRequestResponse:
        dispatcher = CavadaLabsDispatcherService(self.prisma_client)
        project = await dispatcher.get_project(data.project_id)
        company_id = data.company_id or project.company_id
        if company_id != project.company_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "Model load request company_id must match project"},
            )
        company = await dispatcher.get_company(company_id)
        dispatcher._ensure_company_active(company, "create model load requests")
        dispatcher._ensure_project_not_archived(project, "create model load requests")
        dispatcher._ensure_model_allowed(project, data.model_alias)

        node_id = data.node_id
        if data.gpu_id is not None:
            gpu = await self._ensure_gpu_belongs_to_node(data.gpu_id, node_id)
            node_id = node_id or gpu.node_id
        if node_id is not None:
            await self._ensure_node_can_run_project(node_id, project.project_id)

        create_data = data.model_dump(mode="python")
        create_data["node_id"] = node_id
        row = await self.db.cavadalabs_modelloadrequesttable.create(
            data=serialize_prisma_json_fields(
                {
                **create_data,
                "company_id": company_id,
                "status": CavadaLabsModelRuntimeStatus.QUEUED.value,
                "requested_by": _actor_user_id(user_api_key_dict),
                }
            )
        )
        response = _parse_response(row, CavadaLabsModelLoadRequestResponse)
        await self._audit_admin(
            user_api_key_dict=user_api_key_dict,
            action="created",
            resource_type="model_load_request",
            resource_id=response.model_load_request_id,
            company_id=response.company_id,
            project_id=response.project_id,
            before_value=None,
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def list_model_load_requests(
        self,
        project_id: Optional[str] = None,
        node_id: Optional[str] = None,
        status_filter: Optional[CavadaLabsModelRuntimeStatus] = None,
        take: int = 100,
        skip: int = 0,
    ) -> CavadaLabsModelLoadRequestListResponse:
        where: Dict[str, Any] = {}
        if project_id is not None:
            where["project_id"] = project_id
        if node_id is not None:
            where["node_id"] = node_id
        if status_filter is not None:
            where["status"] = status_filter.value
        rows = await self.db.cavadalabs_modelloadrequesttable.find_many(
            where=where or None,
            take=take,
            skip=skip,
            order={"created_at": "desc"},
        )
        requests = [
            _parse_response(row, CavadaLabsModelLoadRequestResponse) for row in rows
        ]
        return CavadaLabsModelLoadRequestListResponse(
            model_load_requests=requests,
            count=len(requests),
        )

    async def list_node_model_load_work(
        self,
        node_id: str,
        data: CavadaLabsNodeModelLoadWorkRequest,
    ) -> CavadaLabsModelLoadRequestListResponse:
        await self.get_node(node_id)
        statuses = [
            (
                status_value.value
                if isinstance(status_value, CavadaLabsModelRuntimeStatus)
                else status_value
            )
            for status_value in data.statuses
        ]
        rows = await self.db.cavadalabs_modelloadrequesttable.find_many(
            where={
                "node_id": node_id,
                "status": {"in": statuses},
            },
            take=data.take,
            order={"priority": "asc"},
        )
        requests = [
            _parse_response(row, CavadaLabsModelLoadRequestResponse) for row in rows
        ]
        return CavadaLabsModelLoadRequestListResponse(
            model_load_requests=requests,
            count=len(requests),
        )

    async def update_model_load_request(
        self,
        model_load_request_id: str,
        data: CavadaLabsModelLoadRequestUpdateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsModelLoadRequestResponse:
        before_row = await self.db.cavadalabs_modelloadrequesttable.find_unique(
            where={"model_load_request_id": model_load_request_id}
        )
        if before_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": f"Model load request '{model_load_request_id}' not found"
                },
            )
        before = _parse_response(before_row, CavadaLabsModelLoadRequestResponse)
        update_data = data.model_dump(mode="python", exclude_unset=True)
        if not update_data:
            return before

        next_node_id = update_data.get("node_id", before.node_id)
        if update_data.get("gpu_id") is not None:
            gpu = await self._ensure_gpu_belongs_to_node(
                update_data["gpu_id"],
                next_node_id,
            )
            if next_node_id is None:
                next_node_id = gpu.node_id
                update_data["node_id"] = next_node_id
        if update_data.get("node_id") is not None:
            await self._ensure_node_can_run_project(
                update_data["node_id"], before.project_id
            )

        update_data = serialize_prisma_json_fields(update_data)
        row = await self.db.cavadalabs_modelloadrequesttable.update(
            where={"model_load_request_id": model_load_request_id},
            data=update_data,
        )
        response = _parse_response(row, CavadaLabsModelLoadRequestResponse)
        await self._audit_admin(
            user_api_key_dict=user_api_key_dict,
            action="updated",
            resource_type="model_load_request",
            resource_id=response.model_load_request_id,
            company_id=response.company_id,
            project_id=response.project_id,
            before_value=before.model_dump(mode="json"),
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def upsert_loaded_model(
        self,
        node_id: str,
        data: CavadaLabsLoadedModelUpsertRequest,
    ) -> CavadaLabsLoadedModelResponse:
        await self.get_node(node_id)
        if data.gpu_id is not None:
            await self._ensure_gpu_belongs_to_node(data.gpu_id, node_id)

        existing = None
        if data.loaded_model_id is not None:
            existing = await self.db.cavadalabs_loadedmodeltable.find_unique(
                where={"loaded_model_id": data.loaded_model_id}
            )
            if existing is not None and existing.node_id != node_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": "Loaded model belongs to another node"},
                )
        elif data.load_request_id is not None:
            existing = await self.db.cavadalabs_loadedmodeltable.find_first(
                where={"node_id": node_id, "load_request_id": data.load_request_id}
            )

        payload = data.model_dump(mode="python", exclude={"loaded_model_id"})
        if payload.get("loaded_at") is None and payload["status"] in {
            CavadaLabsModelRuntimeStatus.LOADED.value,
            CavadaLabsModelRuntimeStatus.LOADING.value,
        }:
            payload["loaded_at"] = _now_utc()
        if payload.get("unloaded_at") is None and payload["status"] in {
            CavadaLabsModelRuntimeStatus.RELEASED.value,
            CavadaLabsModelRuntimeStatus.FAILED.value,
            CavadaLabsModelRuntimeStatus.EXPIRED.value,
        }:
            payload["unloaded_at"] = _now_utc()

        payload = serialize_prisma_json_fields(payload)
        if existing is None:
            row = await self.db.cavadalabs_loadedmodeltable.create(
                data={**payload, "node_id": node_id}
            )
        else:
            row = await self.db.cavadalabs_loadedmodeltable.update(
                where={"loaded_model_id": existing.loaded_model_id},
                data=payload,
            )
        loaded_model = _parse_response(row, CavadaLabsLoadedModelResponse)
        await self._sync_gpu_loaded_model_ids(loaded_model)
        await self._sync_model_load_request_from_loaded_model(loaded_model)
        return loaded_model

    async def create_gpu_lock(
        self,
        data: CavadaLabsGPULockCreateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsGPULockResponse:
        if _as_aware_utc(data.expires_at) <= _now_utc():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "GPU lock expires_at must be in the future"},
            )
        project = await CavadaLabsDispatcherService(self.prisma_client).get_project(
            data.project_id
        )
        await self._ensure_node_can_run_project(data.node_id, project.project_id)
        gpu = await self._ensure_gpu_belongs_to_node(data.gpu_id, data.node_id)
        if gpu.status in {
            CavadaLabsGPUStatus.DISABLED.value,
            CavadaLabsGPUStatus.OFFLINE.value,
            CavadaLabsGPUStatus.UNHEALTHY.value,
        }:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": f"GPU '{gpu.gpu_id}' is not lockable"},
            )

        try:
            row = await self.db.cavadalabs_gpulocktable.create(
                data=serialize_prisma_json_fields(
                    {
                    **data.model_dump(mode="python"),
                    "status": CavadaLabsGPULockStatus.ACTIVE.value,
                    "lock_key": _active_gpu_lock_key(data.gpu_id),
                    }
                )
            )
        except Exception as exc:
            if _is_unique_violation(exc):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": f"GPU '{data.gpu_id}' already has an active lock"},
                )
            raise
        response = _parse_response(row, CavadaLabsGPULockResponse)
        await self._audit_admin(
            user_api_key_dict=user_api_key_dict,
            action="created",
            resource_type="gpu_lock",
            resource_id=response.lock_id,
            project_id=response.project_id,
            before_value=None,
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def list_gpu_locks(
        self,
        project_id: Optional[str] = None,
        node_id: Optional[str] = None,
        status_filter: Optional[CavadaLabsGPULockStatus] = None,
        take: int = 100,
        skip: int = 0,
    ) -> CavadaLabsGPULockListResponse:
        where: Dict[str, Any] = {}
        if project_id is not None:
            where["project_id"] = project_id
        if node_id is not None:
            where["node_id"] = node_id
        if status_filter is not None:
            where["status"] = status_filter.value
        rows = await self.db.cavadalabs_gpulocktable.find_many(
            where=where or None,
            take=take,
            skip=skip,
            order={"created_at": "desc"},
        )
        locks = [_parse_response(row, CavadaLabsGPULockResponse) for row in rows]
        return CavadaLabsGPULockListResponse(gpu_locks=locks, count=len(locks))

    async def release_gpu_lock(
        self,
        lock_id: str,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsGPULockResponse:
        before_row = await self.db.cavadalabs_gpulocktable.find_unique(
            where={"lock_id": lock_id}
        )
        if before_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"GPU lock '{lock_id}' not found"},
            )
        before = _parse_response(before_row, CavadaLabsGPULockResponse)
        row = await self.db.cavadalabs_gpulocktable.update(
            where={"lock_id": lock_id},
            data={
                "status": CavadaLabsGPULockStatus.RELEASED.value,
                "released_at": _now_utc(),
                "lock_key": None,
            },
        )
        response = _parse_response(row, CavadaLabsGPULockResponse)
        await self._audit_admin(
            user_api_key_dict=user_api_key_dict,
            action="released",
            resource_type="gpu_lock",
            resource_id=response.lock_id,
            project_id=response.project_id,
            before_value=before.model_dump(mode="json"),
            after_value=response.model_dump(mode="json"),
        )
        return response
