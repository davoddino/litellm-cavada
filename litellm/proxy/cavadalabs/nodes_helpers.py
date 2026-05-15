from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from litellm._logging import verbose_proxy_logger
from litellm.proxy.cavadalabs.dispatcher import (
    _now_utc,
)
from litellm.proxy.cavadalabs.nodes_shared import (
    _node_actor,
    _parse_response,
)
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsGPULockResponse,
    CavadaLabsGPULockStatus,
    CavadaLabsGPUInventoryItem,
    CavadaLabsGPUResponse,
    CavadaLabsLoadedModelResponse,
    CavadaLabsModelRuntimeStatus,
    CavadaLabsNodeResponse,
    CavadaLabsNodeStatus,
)


class CavadaLabsNodeHelperOperations:
    async def _active_lock_gpu_ids(self, gpu_ids: List[str]) -> set[str]:
        if not gpu_ids:
            return set()
        rows = await self.db.cavadalabs_gpulocktable.find_many(
            where={
                "gpu_id": {"in": gpu_ids},
                "status": CavadaLabsGPULockStatus.ACTIVE.value,
                "expires_at": {"gt": _now_utc()},
            }
        )
        locks = [_parse_response(row, CavadaLabsGPULockResponse) for row in rows]
        return {lock.gpu_id for lock in locks}

    async def _loaded_models_by_gpu(
        self,
        *,
        gpu_ids: List[str],
        model_alias: str,
    ) -> Dict[str, CavadaLabsLoadedModelResponse]:
        if not gpu_ids:
            return {}
        rows = await self.db.cavadalabs_loadedmodeltable.find_many(
            where={
                "gpu_id": {"in": gpu_ids},
                "model_alias": model_alias,
                "status": CavadaLabsModelRuntimeStatus.LOADED.value,
            },
            order={"last_used_at": "desc"},
        )
        result: Dict[str, CavadaLabsLoadedModelResponse] = {}
        for row in rows:
            loaded_model = _parse_response(row, CavadaLabsLoadedModelResponse)
            if loaded_model.gpu_id is None or loaded_model.gpu_id in result:
                continue
            result[loaded_model.gpu_id] = loaded_model
        return result

    async def _find_existing_gpu(
        self,
        *,
        node_id: str,
        gpu: CavadaLabsGPUInventoryItem,
    ) -> Optional[CavadaLabsGPUResponse]:
        if gpu.gpu_id is not None:
            row = await self.db.cavadalabs_gputable.find_unique(
                where={"gpu_id": gpu.gpu_id}
            )
            if row is None:
                return None
            parsed = _parse_response(row, CavadaLabsGPUResponse)
            if parsed.node_id != node_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": "GPU belongs to another node"},
                )
            return parsed
        if gpu.uuid is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "GPU inventory entries require uuid unless gpu_id is provided"
                },
            )
        row = await self.db.cavadalabs_gputable.find_first(
            where={"node_id": node_id, "uuid": gpu.uuid}
        )
        if row is None:
            return None
        return _parse_response(row, CavadaLabsGPUResponse)

    async def _ensure_node_can_run_project(
        self,
        node_id: str,
        project_id: str,
    ) -> CavadaLabsNodeResponse:
        node = await self.get_node(node_id)
        if node.status in {
            CavadaLabsNodeStatus.PENDING.value,
            CavadaLabsNodeStatus.DISABLED.value,
        }:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": f"Node '{node_id}' is not schedulable"},
            )
        if node.allowed_project_ids and project_id not in node.allowed_project_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": f"Project '{project_id}' is not allowed on node"},
            )
        return node

    async def _ensure_gpu_belongs_to_node(
        self,
        gpu_id: str,
        node_id: Optional[str],
    ) -> CavadaLabsGPUResponse:
        row = await self.db.cavadalabs_gputable.find_unique(where={"gpu_id": gpu_id})
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"GPU '{gpu_id}' not found"},
            )
        gpu = _parse_response(row, CavadaLabsGPUResponse)
        if node_id is not None and gpu.node_id != node_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "GPU does not belong to the selected node"},
            )
        return gpu

    async def _sync_gpu_loaded_model_ids(
        self,
        loaded_model: CavadaLabsLoadedModelResponse,
    ) -> None:
        if loaded_model.gpu_id is None:
            return
        gpu_row = await self.db.cavadalabs_gputable.find_unique(
            where={"gpu_id": loaded_model.gpu_id}
        )
        if gpu_row is None:
            return
        gpu = _parse_response(gpu_row, CavadaLabsGPUResponse)
        next_ids = list(gpu.loaded_model_ids)
        if loaded_model.status in {
            CavadaLabsModelRuntimeStatus.LOADED.value,
            CavadaLabsModelRuntimeStatus.LOADING.value,
        }:
            if loaded_model.loaded_model_id not in next_ids:
                next_ids.append(loaded_model.loaded_model_id)
        elif loaded_model.loaded_model_id in next_ids:
            next_ids.remove(loaded_model.loaded_model_id)

        if next_ids != gpu.loaded_model_ids:
            await self.db.cavadalabs_gputable.update(
                where={"gpu_id": loaded_model.gpu_id},
                data={
                    "loaded_model_ids": next_ids,
                    "updated_by": _node_actor(loaded_model.node_id),
                },
            )

    async def _sync_model_load_request_from_loaded_model(
        self,
        loaded_model: CavadaLabsLoadedModelResponse,
    ) -> None:
        if loaded_model.load_request_id is None:
            return
        update_data: Dict[str, Any] = {
            "node_id": loaded_model.node_id,
            "gpu_id": loaded_model.gpu_id,
            "loaded_model_id": loaded_model.loaded_model_id,
        }
        if loaded_model.status in {
            CavadaLabsModelRuntimeStatus.LOADED.value,
            CavadaLabsModelRuntimeStatus.FAILED.value,
            CavadaLabsModelRuntimeStatus.EXPIRED.value,
            CavadaLabsModelRuntimeStatus.RELEASED.value,
            CavadaLabsModelRuntimeStatus.UNLOADING.value,
        }:
            update_data["status"] = loaded_model.status
        try:
            await self.db.cavadalabs_modelloadrequesttable.update(
                where={"model_load_request_id": loaded_model.load_request_id},
                data=update_data,
            )
        except Exception as exc:
            verbose_proxy_logger.warning(
                "Failed to sync CavadaLabs model load request %s from loaded model %s: %s",
                loaded_model.load_request_id,
                loaded_model.loaded_model_id,
                exc,
            )
