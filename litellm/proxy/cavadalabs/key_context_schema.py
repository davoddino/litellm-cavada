from __future__ import annotations

from fastapi import HTTPException, status


CAVADALABS_KEY_CONTEXT_MIGRATION_COMMAND = "uv run prisma migrate deploy"


def _cavadalabs_key_context_missing_schema_error(
    table_name: str, exc: Exception
) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "error": (
                "CavadaLabs key context schema is missing or incomplete. "
                f"Run `{CAVADALABS_KEY_CONTEXT_MIGRATION_COMMAND}` before "
                "creating or updating Company/Project-scoped keys."
            ),
            "schema_status": "missing_schema",
            "missing_schema": [table_name],
            "migration_command": CAVADALABS_KEY_CONTEXT_MIGRATION_COMMAND,
        },
    )


def _looks_like_cavadalabs_key_context_schema_exception(exc: Exception) -> bool:
    if isinstance(exc, AttributeError):
        return True
    message = str(exc).lower()
    return any(
        fragment in message
        for fragment in (
            "does not exist",
            "unknown field",
            "has no attribute",
            "no attribute",
            "column",
            "relation",
        )
    )


def _raise_if_cavadalabs_key_context_schema_exception(
    table_name: str,
    exc: Exception,
) -> None:
    if _looks_like_cavadalabs_key_context_schema_exception(exc):
        raise _cavadalabs_key_context_missing_schema_error(table_name, exc) from exc
