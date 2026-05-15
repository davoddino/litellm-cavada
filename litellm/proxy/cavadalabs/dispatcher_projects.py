from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.cavadalabs.compatibility import (
    ensure_company_compat_organization,
    ensure_project_compat_team,
)
from litellm.proxy.cavadalabs.dispatcher_companies import CavadaLabsCompanyOperations
from litellm.proxy.cavadalabs.dispatcher_shared import (
    _actor_user_id,
    _is_unique_violation,
    _parse_response,
)
from litellm.proxy.cavadalabs.prisma_json import serialize_prisma_json_fields
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsProjectCreateRequest,
    CavadaLabsProjectResponse,
    CavadaLabsProjectStatus,
    CavadaLabsProjectUpdateRequest,
)


class CavadaLabsProjectOperations(CavadaLabsCompanyOperations):
    async def create_project(
        self,
        data: CavadaLabsProjectCreateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsProjectResponse:
        company = await self.get_company(data.company_id)
        self._ensure_company_active(company, "create projects")
        litellm_organization_id = await ensure_company_compat_organization(
            self.prisma_client,
            company=company,
            user_api_key_dict=user_api_key_dict,
        )
        company = company.model_copy(
            update={"litellm_organization_id": litellm_organization_id}
        )
        create_data = serialize_prisma_json_fields(
            {
                **data.model_dump(mode="python"),
                "created_by": _actor_user_id(user_api_key_dict),
                "updated_by": _actor_user_id(user_api_key_dict),
            }
        )
        try:
            row = await self.db.cavadalabs_projecttable.create(data=create_data)
        except Exception as exc:
            if _is_unique_violation(exc):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": "Project name already exists for this company"},
                )
            raise
        response = _parse_response(row, CavadaLabsProjectResponse)
        litellm_team_id = await ensure_project_compat_team(
            self.prisma_client,
            company=company,
            project=response,
            user_api_key_dict=user_api_key_dict,
        )
        response = response.model_copy(update={"litellm_team_id": litellm_team_id})
        await self._audit(
            user_api_key_dict=user_api_key_dict,
            action="created",
            resource_type="project",
            resource_id=response.project_id,
            company_id=response.company_id,
            project_id=response.project_id,
            before_value=None,
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def get_project(self, project_id: str) -> CavadaLabsProjectResponse:
        row = await self.db.cavadalabs_projecttable.find_unique(
            where={"project_id": project_id}
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"Project '{project_id}' not found"},
            )
        return _parse_response(row, CavadaLabsProjectResponse)

    async def list_projects(
        self,
        company_id: Optional[str] = None,
        project_ids: Optional[List[str]] = None,
        status_filter: Optional[CavadaLabsProjectStatus] = None,
        take: int = 100,
        skip: int = 0,
    ) -> List[CavadaLabsProjectResponse]:
        where: Dict[str, Any] = {}
        if company_id is not None:
            where["company_id"] = company_id
        if project_ids is not None:
            if not project_ids:
                return []
            where["project_id"] = {"in": project_ids}
        if status_filter is not None:
            where["status"] = status_filter.value
        rows = await self.db.cavadalabs_projecttable.find_many(
            where=where or None,
            take=take,
            skip=skip,
            order={"created_at": "desc"},
        )
        return [_parse_response(row, CavadaLabsProjectResponse) for row in rows]

    async def update_project(
        self,
        project_id: str,
        data: CavadaLabsProjectUpdateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsProjectResponse:
        before = await self.get_project(project_id)
        update_data = data.model_dump(mode="python", exclude_unset=True)
        if not update_data:
            return before
        update_data["updated_by"] = _actor_user_id(user_api_key_dict)
        update_data = serialize_prisma_json_fields(update_data)
        row = await self.db.cavadalabs_projecttable.update(
            where={"project_id": project_id},
            data=update_data,
        )
        response = _parse_response(row, CavadaLabsProjectResponse)
        company = await self.get_company(response.company_id)
        litellm_organization_id = await ensure_company_compat_organization(
            self.prisma_client,
            company=company,
            user_api_key_dict=user_api_key_dict,
        )
        company = company.model_copy(
            update={"litellm_organization_id": litellm_organization_id}
        )
        litellm_team_id = await ensure_project_compat_team(
            self.prisma_client,
            company=company,
            project=response,
            user_api_key_dict=user_api_key_dict,
        )
        response = response.model_copy(update={"litellm_team_id": litellm_team_id})
        await self._audit(
            user_api_key_dict=user_api_key_dict,
            action="updated",
            resource_type="project",
            resource_id=response.project_id,
            company_id=response.company_id,
            project_id=response.project_id,
            before_value=before.model_dump(mode="json"),
            after_value=response.model_dump(mode="json"),
        )
        return response
