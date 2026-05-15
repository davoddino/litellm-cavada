from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import HTTPException, status

from litellm._logging import verbose_proxy_logger
from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.cavadalabs.dispatcher_shared import (
    _actor_key_hash,
    _actor_user_id,
)
from litellm.proxy.cavadalabs.prisma_json import serialize_prisma_json_fields
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsCompanyResponse,
    CavadaLabsProjectResponse,
    CavadaLabsProjectStatus,
    CavadaLabsStatus,
)


class CavadaLabsDispatcherBase:
    def __init__(self, prisma_client: Any):
        self.prisma_client = prisma_client

    @property
    def db(self) -> Any:
        return self.prisma_client.db

    async def _audit(
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
        try:
            await self.db.cavadalabs_auditlogtable.create(
                data=serialize_prisma_json_fields(
                    {
                    "actor_user_id": _actor_user_id(user_api_key_dict),
                    "actor_api_key_hash": _actor_key_hash(user_api_key_dict),
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

    @staticmethod
    def _ensure_company_active(
        company: CavadaLabsCompanyResponse, operation: str
    ) -> None:
        if company.status != CavadaLabsStatus.ACTIVE.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": f"Cannot {operation} for company in '{company.status}' status"
                },
            )

    @staticmethod
    def _ensure_project_not_archived(
        project: CavadaLabsProjectResponse, operation: str
    ) -> None:
        if project.status == CavadaLabsProjectStatus.ARCHIVED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": f"Cannot {operation} for archived project"},
            )

    @staticmethod
    def _ensure_model_allowed(
        project: CavadaLabsProjectResponse, model_alias: str
    ) -> None:
        if project.allowed_models and model_alias not in project.allowed_models:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "model_alias is not in the project's allowed_models"},
            )

    @staticmethod
    def _extract_grouped_spend(rows: Any) -> float:
        if not rows:
            return 0.0
        first_row = rows[0]
        sum_row = (
            first_row.get("_sum")
            if isinstance(first_row, dict)
            else getattr(first_row, "_sum", None)
        )
        spend = (
            sum_row.get("spend")
            if isinstance(sum_row, dict)
            else getattr(sum_row, "spend", None)
        )
        return float(spend or 0.0)

    @staticmethod
    def _redact_web_token(data: Dict[str, Any]) -> Dict[str, Any]:
        return {**data, "token": "[redacted]", "token_hash": "[redacted]"}
