from __future__ import annotations

from typing import Any, List, Optional

from litellm.proxy.cavadalabs.model_policy_resolution import (
    CavadaLabsModelPolicyCandidate,
    CavadaLabsModelPolicySchemaError,
)

_PROJECT_MODEL_POLICY_DELEGATE = "cavadalabs_projectmodelpolicytable"


class CavadaLabsProjectModelPolicyStore:
    def __init__(self, db: Any):
        self.db = db

    async def list_enabled_project_policies(
        self,
        *,
        project_id: str,
        endpoint_type: str = "chat_completion",
        model_bucket: str = "default",
        key_id: Optional[str] = None,
    ) -> List[CavadaLabsModelPolicyCandidate]:
        delegate = self._delegate()
        where: dict[str, Any] = {
            "project_id": project_id,
            "endpoint_type": endpoint_type,
            "model_bucket": model_bucket,
            "enabled": True,
        }
        if key_id is not None:
            where["key_id"] = key_id
        else:
            where["key_id"] = None
        try:
            rows = await delegate.find_many(
                where=where,
                order={"priority": "asc"},
            )
        except Exception as exc:
            if _looks_like_missing_schema_exception(exc):
                raise _missing_model_policy_schema_error(str(exc)) from exc
            raise
        return [_row_to_candidate(row) for row in rows]

    def _delegate(self) -> Any:
        try:
            return getattr(self.db, _PROJECT_MODEL_POLICY_DELEGATE)
        except AttributeError as exc:
            raise _missing_model_policy_schema_error(str(exc)) from exc


def _row_to_candidate(row: Any) -> CavadaLabsModelPolicyCandidate:
    return CavadaLabsModelPolicyCandidate(
        policy_id=str(_row_value(row, "policy_id")),
        company_id=str(_row_value(row, "company_id")),
        project_id=str(_row_value(row, "project_id")),
        key_id=_optional_string(_row_value(row, "key_id")),
        model_alias=str(_row_value(row, "model_alias")),
        provider=str(_row_value(row, "provider")),
        priority=int(_row_value(row, "priority") or 0),
        enabled=bool(_row_value(row, "enabled")),
        endpoint_type=str(_row_value(row, "endpoint_type") or "chat_completion"),
        model_bucket=str(_row_value(row, "model_bucket") or "default"),
        fallback_enabled=bool(_row_value(row, "fallback_enabled", True)),
    )


def _row_value(row: Any, field_name: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(field_name, default)
    return getattr(row, field_name, default)


def _optional_string(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and value else None


def _looks_like_missing_schema_exception(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "has no attribute",
            "does not exist",
            "no such table",
            "unknown field",
            "column",
        )
    )


def _missing_model_policy_schema_error(
    message: str,
) -> CavadaLabsModelPolicySchemaError:
    return CavadaLabsModelPolicySchemaError(
        missing_schema=["CavadaLabs_ProjectModelPolicyTable"],
        message=(
            "CavadaLabs project model policy schema is missing or incomplete. "
            "Run prisma migrate deploy before using model fallback."
        ),
    )
