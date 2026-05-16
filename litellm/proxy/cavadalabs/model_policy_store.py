from __future__ import annotations

from typing import Any, List

from litellm.proxy.cavadalabs.model_policy_resolution import (
    CavadaLabsModelPolicyCandidate,
    CavadaLabsModelPolicySchemaError,
)

_PROJECT_MODEL_POLICY_DELEGATE = "cavadalabs_projectmodelpolicytable"


class CavadaLabsProjectModelPolicyStore:
    def __init__(self, db: Any):
        self.db = db

    async def list_enabled_project_policies(
        self, *, project_id: str
    ) -> List[CavadaLabsModelPolicyCandidate]:
        delegate = self._delegate()
        try:
            rows = await delegate.find_many(
                where={"project_id": project_id, "enabled": True},
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
        model_alias=str(_row_value(row, "model_alias")),
        provider=str(_row_value(row, "provider")),
        priority=int(_row_value(row, "priority") or 0),
        enabled=bool(_row_value(row, "enabled")),
    )


def _row_value(row: Any, field_name: str) -> Any:
    if isinstance(row, dict):
        return row.get(field_name)
    return getattr(row, field_name, None)


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
