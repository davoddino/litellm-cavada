from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List, Optional


from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.cavadalabs.dispatcher import (
    CavadaLabsDispatcherService,
    _as_aware_utc,
    _is_unique_violation,
    _now_utc,
)
from litellm.proxy.cavadalabs.prisma_json import serialize_prisma_json_fields
from litellm.proxy.cavadalabs.nodes_shared import (
    _SCHEDULABLE_GPU_STATUSES,
    _SCHEDULABLE_NODE_STATUSES,
    _active_gpu_lock_key,
    _metadata_int,
    _metadata_string,
    _parse_response,
)
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsGPULockResponse,
    CavadaLabsGPULockStatus,
    CavadaLabsGPUResponse,
    CavadaLabsLoadedModelResponse,
    CavadaLabsModelLoadRequestResponse,
    CavadaLabsModelRuntimeStatus,
    CavadaLabsNodeResponse,
    CavadaLabsSchedulerAssignmentResponse,
    CavadaLabsSchedulerRunRequest,
    CavadaLabsSchedulerRunResponse,
    CavadaLabsSchedulerSkippedRequest,
)


class CavadaLabsNodeSchedulerOperations:
    async def expire_stale_gpu_locks(self) -> List[CavadaLabsGPULockResponse]:
        rows = await self.db.cavadalabs_gpulocktable.find_many(
            where={
                "status": CavadaLabsGPULockStatus.ACTIVE.value,
                "expires_at": {"lte": _now_utc()},
            },
            take=500,
            order={"expires_at": "asc"},
        )
        expired_locks: List[CavadaLabsGPULockResponse] = []
        for row in rows:
            lock = _parse_response(row, CavadaLabsGPULockResponse)
            updated_row = await self.db.cavadalabs_gpulocktable.update(
                where={"lock_id": lock.lock_id},
                data={
                    "status": CavadaLabsGPULockStatus.EXPIRED.value,
                    "released_at": _now_utc(),
                    "lock_key": None,
                },
            )
            expired_locks.append(
                _parse_response(updated_row, CavadaLabsGPULockResponse)
            )
        return expired_locks

    async def schedule_model_load_requests(
        self,
        data: CavadaLabsSchedulerRunRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsSchedulerRunResponse:
        expired_locks = await self.expire_stale_gpu_locks()
        where: Dict[str, Any] = {"status": CavadaLabsModelRuntimeStatus.QUEUED.value}
        if data.project_id is not None:
            where["project_id"] = data.project_id

        rows = await self.db.cavadalabs_modelloadrequesttable.find_many(
            where=where,
            take=data.take,
            order={"priority": "asc"},
        )
        requests = [
            _parse_response(row, CavadaLabsModelLoadRequestResponse) for row in rows
        ]
        requests.sort(key=lambda request: (request.priority, request.created_at))

        scheduled: List[CavadaLabsSchedulerAssignmentResponse] = []
        skipped: List[CavadaLabsSchedulerSkippedRequest] = []
        for request in requests:
            assignment, skip_reason = await self._schedule_model_load_request(
                request=request,
                data=data,
                user_api_key_dict=user_api_key_dict,
            )
            if assignment is not None:
                scheduled.append(assignment)
            elif skip_reason is not None:
                skipped.append(
                    CavadaLabsSchedulerSkippedRequest(
                        model_load_request_id=request.model_load_request_id,
                        reason=skip_reason,
                    )
                )

        return CavadaLabsSchedulerRunResponse(
            scheduled=scheduled,
            skipped=skipped,
            expired_locks=expired_locks,
            count=len(scheduled),
        )

    async def _schedule_model_load_request(
        self,
        *,
        request: CavadaLabsModelLoadRequestResponse,
        data: CavadaLabsSchedulerRunRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> tuple[Optional[CavadaLabsSchedulerAssignmentResponse], Optional[str]]:
        if (
            request.expires_at is not None
            and _as_aware_utc(request.expires_at) <= _now_utc()
        ):
            await self.db.cavadalabs_modelloadrequesttable.update(
                where={"model_load_request_id": request.model_load_request_id},
                data={
                    "status": CavadaLabsModelRuntimeStatus.EXPIRED.value,
                    "last_error": "Model load request expired before scheduling",
                },
            )
            return None, "expired before scheduling"

        dispatcher = CavadaLabsDispatcherService(self.prisma_client)
        project = await dispatcher.get_project(request.project_id)
        dispatcher._ensure_project_not_archived(project, "schedule model load requests")
        dispatcher._ensure_model_allowed(project, request.model_alias)

        nodes = await self._candidate_nodes_for_request(request=request, data=data)
        if not nodes:
            return None, "no schedulable node"

        gpus = await self._candidate_gpus_for_request(
            request=request,
            data=data,
            nodes=nodes,
        )
        if not gpus:
            return None, "no compatible GPU"

        active_lock_gpu_ids = await self._active_lock_gpu_ids(
            [gpu.gpu_id for gpu in gpus]
        )
        available_gpus = [gpu for gpu in gpus if gpu.gpu_id not in active_lock_gpu_ids]
        if not available_gpus:
            return None, "all compatible GPUs are locked"

        loaded_models_by_gpu = await self._loaded_models_by_gpu(
            gpu_ids=[gpu.gpu_id for gpu in available_gpus],
            model_alias=request.model_alias,
        )
        compatible_gpus = [
            gpu
            for gpu in available_gpus
            if not gpu.loaded_model_ids or gpu.gpu_id in loaded_models_by_gpu
        ]
        if not compatible_gpus:
            return None, "compatible GPUs already host different models"

        nodes_by_id = {node.node_id: node for node in nodes}
        compatible_gpus.sort(
            key=lambda gpu: (
                gpu.gpu_id not in loaded_models_by_gpu,
                gpu.vram_total_mb,
                gpu.node_id,
                gpu.gpu_id,
            )
        )

        loaded_assignment = await self._try_reuse_loaded_model(
            request=request,
            loaded_models_by_gpu=loaded_models_by_gpu,
            compatible_gpus=compatible_gpus,
            nodes_by_id=nodes_by_id,
            user_api_key_dict=user_api_key_dict,
        )
        if loaded_assignment is not None:
            return loaded_assignment, None

        for gpu in compatible_gpus:
            node = nodes_by_id.get(gpu.node_id)
            if node is None:
                continue
            assignment = await self._try_create_scheduled_gpu_lock(
                request=request,
                data=data,
                node=node,
                gpu=gpu,
                user_api_key_dict=user_api_key_dict,
            )
            if assignment is not None:
                return assignment, None

        if data.fail_if_no_capacity:
            await self.db.cavadalabs_modelloadrequesttable.update(
                where={"model_load_request_id": request.model_load_request_id},
                data={
                    "status": CavadaLabsModelRuntimeStatus.FAILED.value,
                    "last_error": "No GPU capacity available for scheduling",
                },
            )
            return None, "marked failed: no GPU capacity"
        return None, "no GPU capacity available"

    async def _try_reuse_loaded_model(
        self,
        *,
        request: CavadaLabsModelLoadRequestResponse,
        loaded_models_by_gpu: Dict[str, CavadaLabsLoadedModelResponse],
        compatible_gpus: List[CavadaLabsGPUResponse],
        nodes_by_id: Dict[str, CavadaLabsNodeResponse],
        user_api_key_dict: UserAPIKeyAuth,
    ) -> Optional[CavadaLabsSchedulerAssignmentResponse]:
        for gpu in compatible_gpus:
            loaded_model = loaded_models_by_gpu.get(gpu.gpu_id)
            node = nodes_by_id.get(gpu.node_id)
            if loaded_model is None or node is None:
                continue
            claimed_count = await self.db.cavadalabs_modelloadrequesttable.update_many(
                where={
                    "model_load_request_id": request.model_load_request_id,
                    "status": CavadaLabsModelRuntimeStatus.QUEUED.value,
                },
                data={
                    "status": CavadaLabsModelRuntimeStatus.LOADED.value,
                    "node_id": node.node_id,
                    "gpu_id": gpu.gpu_id,
                    "loaded_model_id": loaded_model.loaded_model_id,
                    "last_error": None,
                },
            )
            if claimed_count == 0:
                return None
            updated_row = await self.db.cavadalabs_modelloadrequesttable.find_unique(
                where={"model_load_request_id": request.model_load_request_id}
            )
            if updated_row is None:
                return None
            updated_request = _parse_response(
                updated_row, CavadaLabsModelLoadRequestResponse
            )
            await self._audit_admin(
                user_api_key_dict=user_api_key_dict,
                action="scheduled_reused_loaded_model",
                resource_type="model_load_request",
                resource_id=updated_request.model_load_request_id,
                company_id=updated_request.company_id,
                project_id=updated_request.project_id,
                before_value=request.model_dump(mode="json"),
                after_value=updated_request.model_dump(mode="json"),
            )
            return CavadaLabsSchedulerAssignmentResponse(
                model_load_request=updated_request,
                node=node,
                gpu=gpu,
                gpu_lock=None,
                loaded_model=loaded_model,
            )
        return None

    async def _try_create_scheduled_gpu_lock(
        self,
        *,
        request: CavadaLabsModelLoadRequestResponse,
        data: CavadaLabsSchedulerRunRequest,
        node: CavadaLabsNodeResponse,
        gpu: CavadaLabsGPUResponse,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> Optional[CavadaLabsSchedulerAssignmentResponse]:
        lock_expires_at = _now_utc() + timedelta(seconds=data.lock_ttl_seconds)
        try:
            lock_row = await self.db.cavadalabs_gpulocktable.create(
                data=serialize_prisma_json_fields(
                    {
                    "node_id": node.node_id,
                    "gpu_id": gpu.gpu_id,
                    "model_id": request.model_alias,
                    "project_id": request.project_id,
                    "owner_type": "model_load_request",
                    "owner_id": request.model_load_request_id,
                    "priority": request.priority,
                    "expires_at": lock_expires_at,
                    "status": CavadaLabsGPULockStatus.ACTIVE.value,
                    "lock_key": _active_gpu_lock_key(gpu.gpu_id),
                    "metadata": {
                        **data.metadata,
                        "scheduler": "cavadalabs",
                        "model_load_request_id": request.model_load_request_id,
                    },
                    }
                )
            )
        except Exception as exc:
            if _is_unique_violation(exc):
                return None
            raise

        lock = _parse_response(lock_row, CavadaLabsGPULockResponse)
        claimed_count = await self.db.cavadalabs_modelloadrequesttable.update_many(
            where={
                "model_load_request_id": request.model_load_request_id,
                "status": CavadaLabsModelRuntimeStatus.QUEUED.value,
            },
            data=serialize_prisma_json_fields(
                {
                "status": CavadaLabsModelRuntimeStatus.LOCKING.value,
                "node_id": node.node_id,
                "gpu_id": gpu.gpu_id,
                "last_error": None,
                "metadata": {
                    **request.metadata,
                    "scheduled_at": _now_utc().isoformat(),
                    "gpu_lock_id": lock.lock_id,
                },
                }
            ),
        )
        if claimed_count == 0:
            await self.db.cavadalabs_gpulocktable.update(
                where={"lock_id": lock.lock_id},
                data={
                    "status": CavadaLabsGPULockStatus.RELEASED.value,
                    "released_at": _now_utc(),
                    "lock_key": None,
                },
            )
            return None

        updated_row = await self.db.cavadalabs_modelloadrequesttable.find_unique(
            where={"model_load_request_id": request.model_load_request_id}
        )
        if updated_row is None:
            return None
        updated_request = _parse_response(
            updated_row, CavadaLabsModelLoadRequestResponse
        )
        await self._audit_admin(
            user_api_key_dict=user_api_key_dict,
            action="scheduled",
            resource_type="model_load_request",
            resource_id=updated_request.model_load_request_id,
            company_id=updated_request.company_id,
            project_id=updated_request.project_id,
            before_value=request.model_dump(mode="json"),
            after_value=updated_request.model_dump(mode="json"),
        )
        return CavadaLabsSchedulerAssignmentResponse(
            model_load_request=updated_request,
            node=node,
            gpu=gpu,
            gpu_lock=lock,
            loaded_model=None,
        )

    async def _candidate_nodes_for_request(
        self,
        *,
        request: CavadaLabsModelLoadRequestResponse,
        data: CavadaLabsSchedulerRunRequest,
    ) -> List[CavadaLabsNodeResponse]:
        if request.node_id is not None:
            nodes = [await self.get_node(request.node_id)]
        elif data.node_ids:
            rows = await self.db.cavadalabs_nodetable.find_many(
                where={"node_id": {"in": data.node_ids}},
                order={"last_heartbeat_at": "desc"},
            )
            nodes = [_parse_response(row, CavadaLabsNodeResponse) for row in rows]
        else:
            rows = await self.db.cavadalabs_nodetable.find_many(
                where={"status": {"in": list(_SCHEDULABLE_NODE_STATUSES)}},
                order={"last_heartbeat_at": "desc"},
            )
            nodes = [_parse_response(row, CavadaLabsNodeResponse) for row in rows]

        required_pool = _metadata_string(request.metadata, "required_pool", "pool")
        filtered_nodes = []
        for node in nodes:
            if node.status not in _SCHEDULABLE_NODE_STATUSES:
                continue
            if (
                node.allowed_project_ids
                and request.project_id not in node.allowed_project_ids
            ):
                continue
            if required_pool is not None and required_pool not in node.pools:
                continue
            filtered_nodes.append(node)
        return filtered_nodes

    async def _candidate_gpus_for_request(
        self,
        *,
        request: CavadaLabsModelLoadRequestResponse,
        data: CavadaLabsSchedulerRunRequest,
        nodes: List[CavadaLabsNodeResponse],
    ) -> List[CavadaLabsGPUResponse]:
        node_ids = [node.node_id for node in nodes]
        if not node_ids:
            return []

        if request.gpu_id is not None:
            rows = [
                await self._ensure_gpu_belongs_to_node(request.gpu_id, request.node_id)
            ]
        else:
            where: Dict[str, Any] = {
                "node_id": {"in": node_ids},
                "status": {"in": list(_SCHEDULABLE_GPU_STATUSES)},
            }
            if data.gpu_ids:
                where["gpu_id"] = {"in": data.gpu_ids}
            rows = await self.db.cavadalabs_gputable.find_many(
                where=where,
                order={"vram_total_mb": "asc"},
            )

        gpus = [
            (
                row
                if isinstance(row, CavadaLabsGPUResponse)
                else _parse_response(row, CavadaLabsGPUResponse)
            )
            for row in rows
        ]
        required_vram_mb = data.min_vram_mb or _metadata_int(
            request.metadata, "required_vram_mb", "min_vram_mb"
        )
        required_vendor = _metadata_string(request.metadata, "required_gpu_vendor")
        required_model = _metadata_string(request.metadata, "required_gpu_model")
        filtered_gpus = []
        for gpu in gpus:
            if gpu.node_id not in node_ids:
                continue
            if gpu.status not in _SCHEDULABLE_GPU_STATUSES:
                continue
            if required_vram_mb is not None and gpu.vram_total_mb < required_vram_mb:
                continue
            if (
                required_vendor is not None
                and gpu.vendor.lower() != required_vendor.lower()
            ):
                continue
            if (
                required_model is not None
                and required_model.lower() not in gpu.model.lower()
            ):
                continue
            filtered_gpus.append(gpu)
        return filtered_gpus
