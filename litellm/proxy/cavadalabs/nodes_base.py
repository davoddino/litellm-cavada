from __future__ import annotations

from typing import Any, Dict, Optional

from litellm._logging import verbose_proxy_logger
from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.cavadalabs.dispatcher import _actor_key_hash, _actor_user_id
from litellm.proxy.cavadalabs.prisma_json import serialize_prisma_json_fields
from litellm.proxy.cavadalabs.nodes_shared import (
    _NODE_SIGNATURE_MAX_SKEW,
)
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsNodeDailyReportRequest,
    CavadaLabsNodeResponse,
)


class CavadaLabsNodeBase:
    def __init__(self, prisma_client: Any):
        self.prisma_client = prisma_client

    @property
    def db(self) -> Any:
        return self.prisma_client.db

    @staticmethod
    def _estimate_node_daily_cost(
        *,
        node: CavadaLabsNodeResponse,
        data: CavadaLabsNodeDailyReportRequest,
    ) -> float:
        electricity_cost = node.default_electricity_cost_per_kwh or 0.0
        fixed_hourly_cost = node.fixed_hourly_cost or 0.0
        amortization_hourly_cost = node.hardware_amortization_hourly_cost or 0.0
        return (
            data.total_kwh * electricity_cost
            + fixed_hourly_cost * 24
            + amortization_hourly_cost * 24
        )

    @staticmethod
    def _runtime_config(node: CavadaLabsNodeResponse) -> Dict[str, Any]:
        return {
            "node_id": node.node_id,
            "allowed_project_ids": node.allowed_project_ids,
            "pools": node.pools,
            "signature": {
                "algorithm": "ed25519",
                "headers": [
                    "x-cavadalabs-node-id",
                    "x-cavadalabs-node-timestamp",
                    "x-cavadalabs-node-signature",
                ],
                "canonical_payload": "timestamp\\nHTTP_METHOD\\nPATH\\nSHA256_HEX_BODY",
                "max_clock_skew_seconds": int(_NODE_SIGNATURE_MAX_SKEW.total_seconds()),
            },
            "endpoints": {
                "heartbeat": "/cavadalabs/nodes/heartbeat",
                "gpu_inventory": "/cavadalabs/nodes/gpus",
                "daily_report": "/cavadalabs/nodes/daily-reports",
                "loaded_models": "/cavadalabs/nodes/loaded-models",
                "model_load_requests": "/cavadalabs/nodes/model-load-requests",
            },
        }

    async def _audit_admin(
        self,
        user_api_key_dict: UserAPIKeyAuth,
        action: str,
        resource_type: str,
        resource_id: str,
        before_value: Optional[Dict[str, Any]],
        after_value: Optional[Dict[str, Any]],
        company_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> None:
        await self._audit_event(
            actor_user_id=_actor_user_id(user_api_key_dict),
            actor_api_key_hash=_actor_key_hash(user_api_key_dict),
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            company_id=company_id,
            project_id=project_id,
            before_value=before_value,
            after_value=after_value,
        )

    async def _audit_event(
        self,
        actor_user_id: Optional[str],
        actor_api_key_hash: Optional[str],
        action: str,
        resource_type: str,
        resource_id: str,
        before_value: Optional[Dict[str, Any]],
        after_value: Optional[Dict[str, Any]],
        company_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> None:
        try:
            await self.db.cavadalabs_auditlogtable.create(
                data=serialize_prisma_json_fields(
                    {
                    "actor_user_id": actor_user_id,
                    "actor_api_key_hash": actor_api_key_hash,
                    "action": action,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "company_id": company_id,
                    "project_id": project_id,
                    "before_value": before_value,
                    "after_value": after_value,
                    }
                )
            )
        except Exception as exc:
            verbose_proxy_logger.warning(
                "Failed to write CavadaLabs audit log for %s/%s: %s",
                resource_type,
                resource_id,
                exc,
            )
