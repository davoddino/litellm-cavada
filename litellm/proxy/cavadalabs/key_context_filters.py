from __future__ import annotations

from typing import Any, Dict, Literal, Optional, Tuple

from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.cavadalabs.key_context_metadata import (
    CAVADALABS_COMPANY_METADATA_KEY,
    CAVADALABS_METADATA_ENVELOPE_KEY,
    CAVADALABS_PROJECT_METADATA_KEY,
    CAVADALABS_SPEND_LOGS_METADATA_KEY,
    _optional_str,
)
from litellm.proxy.cavadalabs.key_context_schema import (
    _raise_if_cavadalabs_key_context_schema_exception,
)


def _cavadalabs_key_metadata_filter(
    field: Literal["company_id", "project_id"], value: str
) -> Dict[str, Any]:
    top_level_key = (
        CAVADALABS_COMPANY_METADATA_KEY
        if field == "company_id"
        else CAVADALABS_PROJECT_METADATA_KEY
    )
    return {
        "OR": [
            {"metadata": {"path": [top_level_key], "equals": value}},
            {
                "metadata": {
                    "path": [CAVADALABS_METADATA_ENVELOPE_KEY, field],
                    "equals": value,
                }
            },
            {
                "metadata": {
                    "path": [CAVADALABS_SPEND_LOGS_METADATA_KEY, top_level_key],
                    "equals": value,
                }
            },
        ]
    }


def _cavadalabs_key_context_filter(
    field: Literal["company_id", "project_id"],
    value: str,
    compatibility_value: Optional[str],
) -> Dict[str, Any]:
    filters = [_cavadalabs_key_metadata_filter(field, value)]
    if field == "company_id" and compatibility_value:
        filters.append({"organization_id": compatibility_value})
    if field == "project_id" and compatibility_value:
        filters.append({"team_id": compatibility_value})
    if len(filters) == 1:
        return filters[0]
    return {"OR": filters}


async def _validate_cavadalabs_key_list_filter_access(
    prisma_client: Any,
    user_api_key_dict: UserAPIKeyAuth,
    cavadalabs_company_id: Optional[str],
    cavadalabs_project_id: Optional[str],
) -> None:
    if cavadalabs_company_id is None and cavadalabs_project_id is None:
        return

    from litellm.proxy.cavadalabs.access_control import (
        authorize_cavadalabs_company_project_access,
        require_company_wide_access,
    )

    if cavadalabs_company_id is not None and cavadalabs_project_id is None:
        await require_company_wide_access(
            prisma_client.db,
            company_id=cavadalabs_company_id,
            user_api_key_dict=user_api_key_dict,
        )
        return

    await authorize_cavadalabs_company_project_access(
        prisma_client.db,
        company_id=cavadalabs_company_id,
        project_id=cavadalabs_project_id,
        user_api_key_dict=user_api_key_dict,
        action="view",
    )


async def _resolve_cavadalabs_key_filter_compatibility_mappings(
    prisma_client: Any,
    *,
    cavadalabs_company_id: Optional[str],
    cavadalabs_project_id: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    compatibility_organization_id: Optional[str] = None
    compatibility_team_id: Optional[str] = None
    if cavadalabs_company_id:
        try:
            company = await prisma_client.db.cavadalabs_companytable.find_unique(
                where={"company_id": cavadalabs_company_id}
            )
        except Exception as exc:
            _raise_if_cavadalabs_key_context_schema_exception(
                "cavadalabs_companytable", exc
            )
            raise
        compatibility_organization_id = _optional_str(
            getattr(company, "litellm_organization_id", None)
        )
    if cavadalabs_project_id:
        try:
            project = await prisma_client.db.cavadalabs_projecttable.find_unique(
                where={"project_id": cavadalabs_project_id}
            )
        except Exception as exc:
            _raise_if_cavadalabs_key_context_schema_exception(
                "cavadalabs_projecttable", exc
            )
            raise
        compatibility_team_id = _optional_str(getattr(project, "litellm_team_id", None))
    return compatibility_organization_id, compatibility_team_id
