from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.cavadalabs.dispatcher_base import CavadaLabsDispatcherBase
from litellm.proxy.cavadalabs.dispatcher_shared import (
    _actor_user_id,
    _is_unique_violation,
    _parse_response,
)
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsCompanyCreateRequest,
    CavadaLabsCompanyResponse,
    CavadaLabsCompanyUpdateRequest,
    CavadaLabsStatus,
)


class CavadaLabsCompanyOperations(CavadaLabsDispatcherBase):
    async def create_company(
        self,
        data: CavadaLabsCompanyCreateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsCompanyResponse:
        create_data = {
            **data.model_dump(mode="python"),
            "created_by": _actor_user_id(user_api_key_dict),
            "updated_by": _actor_user_id(user_api_key_dict),
        }
        try:
            row = await self.db.cavadalabs_companytable.create(data=create_data)
        except Exception as exc:
            if _is_unique_violation(exc):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": "Company already exists"},
                )
            raise

        response = _parse_response(row, CavadaLabsCompanyResponse)
        await self._audit(
            user_api_key_dict=user_api_key_dict,
            action="created",
            resource_type="company",
            resource_id=response.company_id,
            company_id=response.company_id,
            before_value=None,
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def get_company(self, company_id: str) -> CavadaLabsCompanyResponse:
        row = await self.db.cavadalabs_companytable.find_unique(
            where={"company_id": company_id}
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"Company '{company_id}' not found"},
            )
        return _parse_response(row, CavadaLabsCompanyResponse)

    async def list_companies(
        self,
        status_filter: Optional[CavadaLabsStatus] = None,
        take: int = 100,
        skip: int = 0,
    ) -> List[CavadaLabsCompanyResponse]:
        where: Dict[str, Any] = {}
        if status_filter is not None:
            where["status"] = status_filter.value
        rows = await self.db.cavadalabs_companytable.find_many(
            where=where or None,
            take=take,
            skip=skip,
            order={"created_at": "desc"},
        )
        return [_parse_response(row, CavadaLabsCompanyResponse) for row in rows]

    async def update_company(
        self,
        company_id: str,
        data: CavadaLabsCompanyUpdateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsCompanyResponse:
        before = await self.get_company(company_id)
        update_data = data.model_dump(mode="python", exclude_unset=True)
        if not update_data:
            return before
        update_data["updated_by"] = _actor_user_id(user_api_key_dict)
        row = await self.db.cavadalabs_companytable.update(
            where={"company_id": company_id},
            data=update_data,
        )
        response = _parse_response(row, CavadaLabsCompanyResponse)
        await self._audit(
            user_api_key_dict=user_api_key_dict,
            action="updated",
            resource_type="company",
            resource_id=response.company_id,
            company_id=response.company_id,
            before_value=before.model_dump(mode="json"),
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def archive_company(
        self,
        company_id: str,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsCompanyResponse:
        return await self.update_company(
            company_id=company_id,
            data=CavadaLabsCompanyUpdateRequest(status=CavadaLabsStatus.ARCHIVED),
            user_api_key_dict=user_api_key_dict,
        )
