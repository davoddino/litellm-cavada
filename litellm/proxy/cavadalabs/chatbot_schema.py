from __future__ import annotations

from typing import Any, Optional, Type, TypeVar

from fastapi import HTTPException, status
from pydantic import BaseModel

from litellm.proxy.cavadalabs.dispatcher_shared import _parse_response

ModelT = TypeVar("ModelT", bound=BaseModel)

MIGRATION_COMMAND = "uv run prisma migrate deploy"

DELEGATE_MODEL_NAMES = {
    "cavadalabs_chatbottable": "CavadaLabs_ChatbotTable",
    "cavadalabs_webtokentable": "CavadaLabs_WebTokenTable",
    "cavadalabs_projectmodelpolicytable": "CavadaLabs_ProjectModelPolicyTable",
    "cavadalabs_ragcollectiontable": "CavadaLabs_RAGCollectionTable",
    "cavadalabs_guardrailpolicytable": "CavadaLabs_GuardrailPolicyTable",
}


def model_name(delegate_name: str) -> str:
    return DELEGATE_MODEL_NAMES.get(delegate_name, delegate_name)


def looks_like_missing_schema_exception(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "has no attribute",
            "does not exist",
            "no such table",
            "unknown arg",
            "unknown argument",
            "unknown field",
            "column",
            "relation",
        )
    )


def missing_chatbot_schema_error(delegate_name: str, exc: Exception) -> HTTPException:
    schema_name = model_name(delegate_name)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "error": (
                f"CavadaLabs chatbot schema is missing required table/delegate "
                f"'{schema_name}'. Run Prisma migrations before using chatbot "
                "Company/Project scope."
            ),
            "schema_status": "missing_schema",
            "missing_schema": [schema_name],
            "migration_command": MIGRATION_COMMAND,
            "cause": str(exc),
        },
    )


def delegate(db: Any, delegate_name: str) -> Any:
    try:
        return getattr(db, delegate_name)
    except AttributeError as exc:
        raise missing_chatbot_schema_error(delegate_name, exc) from exc


async def find_unique_response(
    db: Any,
    *,
    delegate_name: str,
    where: dict[str, Any],
    response_model: Type[ModelT],
) -> Optional[ModelT]:
    table = delegate(db, delegate_name)
    try:
        row = await table.find_unique(where=where)
    except Exception as exc:
        if looks_like_missing_schema_exception(exc):
            raise missing_chatbot_schema_error(delegate_name, exc) from exc
        raise
    if row is None:
        return None
    return _parse_response(row, response_model)


async def get_required_response(
    db: Any,
    *,
    delegate_name: str,
    where: dict[str, Any],
    response_model: Type[ModelT],
    resource_name: str,
    resource_id: str,
) -> ModelT:
    row = await find_unique_response(
        db,
        delegate_name=delegate_name,
        where=where,
        response_model=response_model,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": f"{resource_name} '{resource_id}' not found"},
        )
    return row
